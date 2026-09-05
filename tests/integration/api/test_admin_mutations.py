import pytest
from uuid import uuid4
from fastapi.testclient import TestClient
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

from app.main import app
from app.persistence.database import Base
from app.persistence.models.payment import Payment
from app.persistence.models.recovery import RecoveryCase, RecoveryJob
from app.domain.recovery.states import PaymentState, RecoveryState, JobState
from app.persistence.models.customer import Customer

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://user:password@postgres:5432/recovery_db")
engine = create_engine(DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield

client = TestClient(app)
HEADERS = {"X-Admin-API-Key": "test-admin-key"}

def get_test_db():
    db = TestingSessionLocal()
    return db

def test_admin_stop_case():
    db = get_test_db()
    c_id = uuid4()
    cust = Customer(id=c_id, external_id=f"ext_{c_id}", email="test@test.com", name="Test Customer")
    db.add(cust)
    
    payment = Payment(
        id=uuid4(), external_id=f"pay_stop_{uuid4()}", customer_id=c_id,
        amount=100.0, currency="USD", status=PaymentState.FAILED
    )
    db.add(payment)
    db.flush()
    
    case = RecoveryCase(
        id=uuid4(), payment_id=payment.id, customer_id=c_id,
        amount_at_risk=100.0, currency="USD", status=RecoveryState.OPEN,
        failure_reason="test", max_attempts=3
    )
    db.add(case)
    
    job = RecoveryJob(
        id=uuid4(), recovery_case_id=case.id, job_type="EVALUATE_RECOVERY",
        scheduled_for=datetime.utcnow(), status=JobState.PENDING, max_attempts=3, available_at=datetime.utcnow()
    )
    db.add(job)
    db.commit()

    response = client.post(f"/admin/cases/{case.id}/stop", headers=HEADERS)
    
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    
    db.expire_all()
    assert case.status == RecoveryState.STOPPED
    assert job.status == JobState.CANCELLED
    db.close()

def test_admin_retry_case():
    db = get_test_db()
    c_id = uuid4()
    cust = Customer(id=c_id, external_id=f"ext_{c_id}_retry", email="test@test.com", name="Test Customer")
    db.add(cust)
    
    payment = Payment(
        id=uuid4(), external_id=f"pay_retry_{uuid4()}", customer_id=c_id,
        amount=100.0, currency="USD", status=PaymentState.FAILED
    )
    db.add(payment)
    db.flush()
    
    case = RecoveryCase(
        id=uuid4(), payment_id=payment.id, customer_id=c_id,
        amount_at_risk=100.0, currency="USD", status=RecoveryState.STOPPED,
        failure_reason="test", max_attempts=3
    )
    db.add(case)
    db.commit()

    response = client.post(f"/admin/cases/{case.id}/retry", headers=HEADERS)
    
    assert response.status_code == 200
    
    db.expire_all()
    assert case.status == RecoveryState.OPEN
    jobs = db.query(RecoveryJob).filter_by(recovery_case_id=case.id).all()
    assert len(jobs) == 1
    assert jobs[0].status == JobState.PENDING
    db.close()

def test_admin_mutation_terminal_dominance():
    db = get_test_db()
    c_id = uuid4()
    cust = Customer(id=c_id, external_id=f"ext_{c_id}_term", email="test@test.com", name="Test Customer")
    db.add(cust)
    
    payment = Payment(
        id=uuid4(), external_id=f"pay_term_{uuid4()}", customer_id=c_id,
        amount=100.0, currency="USD", status=PaymentState.SUCCEEDED
    )
    db.add(payment)
    db.flush()
    
    case = RecoveryCase(
        id=uuid4(), payment_id=payment.id, customer_id=c_id,
        amount_at_risk=100.0, currency="USD", status=RecoveryState.OPEN,
        failure_reason="test", max_attempts=3
    )
    db.add(case)
    db.commit()

    response = client.post(f"/admin/cases/{case.id}/retry", headers=HEADERS)
    assert response.status_code == 409
    assert "SUCCEEDED" in response.json()["detail"]

    response = client.post(f"/admin/cases/{case.id}/stop", headers=HEADERS)
    assert response.status_code == 409
    assert "SUCCEEDED" in response.json()["detail"]
    db.close()

def test_admin_retry_conflict_with_running_job():
    db = get_test_db()
    c_id = uuid4()
    cust = Customer(id=c_id, external_id=f"ext_{c_id}_conf", email="test@test.com", name="Test Customer")
    db.add(cust)
    
    payment = Payment(
        id=uuid4(), external_id=f"pay_conf_{uuid4()}", customer_id=c_id,
        amount=100.0, currency="USD", status=PaymentState.FAILED
    )
    db.add(payment)
    db.flush()
    
    case = RecoveryCase(
        id=uuid4(), payment_id=payment.id, customer_id=c_id,
        amount_at_risk=100.0, currency="USD", status=RecoveryState.OPEN,
        failure_reason="test", max_attempts=3
    )
    db.add(case)
    
    job = RecoveryJob(
        id=uuid4(), recovery_case_id=case.id, job_type="EVALUATE_RECOVERY",
        scheduled_for=datetime.utcnow(), status=JobState.RUNNING, max_attempts=3, available_at=datetime.utcnow(),
        locked_by="worker-1"
    )
    db.add(job)
    db.commit()

    response = client.post(f"/admin/cases/{case.id}/retry", headers=HEADERS)
    assert response.status_code == 409
    assert "active pending or running" in response.json()["detail"]
    db.close()
