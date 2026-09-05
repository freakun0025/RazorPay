import pytest
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

from app.main import app
from app.persistence.database import Base
from app.persistence.models.payment import Payment
from app.persistence.models.recovery import RecoveryCase
from app.persistence.models.customer import Customer
from app.domain.recovery.states import PaymentState, RecoveryState

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

def test_admin_get_case():
    db = TestingSessionLocal()
    c_id = uuid4()
    cust = Customer(id=c_id, external_id=f"ext_{c_id}", email="test@test.com", name="Test Customer")
    db.add(cust)
    
    payment = Payment(
        id=uuid4(), external_id=f"pay_read_{uuid4()}", customer_id=c_id,
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
    db.commit()

    response = client.get(f"/admin/cases/{case.id}", headers=HEADERS)
    assert response.status_code == 200
    data = response.json()
    
    assert data["id"] == str(case.id)
    assert data["status"] == "OPEN"
    assert "AI_API_KEY" not in str(data)
    db.close()
