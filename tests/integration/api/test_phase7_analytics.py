from sqlalchemy import text
import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.persistence.database import Base
from app.persistence.models.recovery import RecoveryCase, RecoveryAttempt
from app.domain.recovery.states import RecoveryState, AttemptState

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://user:password@postgres:5432/recovery_db")
engine = create_engine(DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        conn.execute(text("TRUNCATE TABLE recovery_attempts, recovery_jobs, recovery_cases CASCADE"))
        conn.commit()
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

def create_mock_case(db, cid, amount, currency, status, created_at, payment_id=None, customer_id=None):
    from app.persistence.models.payment import Payment
    from app.persistence.models.customer import Customer
    from app.domain.recovery.states import PaymentState
    if not customer_id:
        customer_id = uuid4()
        db.add(Customer(id=customer_id, external_id=f"ext_{customer_id}", email="test@test.com", name="Test"))
        db.flush()
    if not payment_id:
        payment_id = uuid4()
        db.add(Payment(id=payment_id, external_id=f"ext_{payment_id}", customer_id=customer_id, amount=amount, currency=currency, status=PaymentState.FAILED))
        db.flush()
    case = RecoveryCase(
        id=cid,
        payment_id=payment_id,
        customer_id=customer_id,
        amount_at_risk=amount,
        currency=currency,
        status=status,
        failure_reason="test",
        max_attempts=3,
        created_at=created_at
    )
    db.add(case)
    db.commit()
    return case

def create_mock_attempt(db, cid, case_id, status, attempt_num=1):
    a = RecoveryAttempt(
        id=cid,
        recovery_case_id=case_id,
        attempt_number=attempt_num,
        action_type="CHARGE",
        status=status
    )
    db.add(a)
    db.commit()

@pytest.mark.anyio
async def test_empty_batch_returns_zero_metrics(client):
    headers = {"X-Admin-API-Key": "admin-secret-dev-key-123"}
    resp = await client.get("/admin/analytics/recovery?start_at=1999-01-01T00:00:00&end_at=1999-02-01T00:00:00", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["metrics_by_currency"] == {}

@pytest.mark.anyio
async def test_admin_auth_required(client):
    resp = await client.get("/admin/analytics/recovery?start_at=1999-01-01T00:00:00&end_at=1999-02-01T00:00:00")
    assert resp.status_code == 401

@pytest.mark.anyio
async def test_invalid_time_range_rejected(client):
    headers = {"X-Admin-API-Key": "admin-secret-dev-key-123"}
    resp = await client.get("/admin/analytics/recovery?start_at=1999-02-01T00:00:00&end_at=1999-01-01T00:00:00", headers=headers)
    assert resp.status_code == 400

@pytest.mark.anyio
async def test_recovery_analytics_calculations(client):
    db = TestingSessionLocal()
    
    t_mid = datetime(1999, 1, 15)
    
    # Case 1: USD, Recovered
    c1 = uuid4()
    create_mock_case(db, c1, 100.0, "USD", RecoveryState.RECOVERED, t_mid)
    create_mock_attempt(db, uuid4(), c1, AttemptState.FAILED)
    create_mock_attempt(db, uuid4(), c1, AttemptState.SUCCEEDED, 2)
    
    # Case 2: USD, Stopped
    c2 = uuid4()
    create_mock_case(db, c2, 50.0, "USD", RecoveryState.STOPPED, t_mid)
    create_mock_attempt(db, uuid4(), c2, AttemptState.FAILED)
    
    # Case 3: EUR, Recovered
    c3 = uuid4()
    create_mock_case(db, c3, 200.0, "EUR", RecoveryState.RECOVERED, t_mid)
    create_mock_attempt(db, uuid4(), c3, AttemptState.SUCCEEDED)

    db.close()
    
    headers = {"X-Admin-API-Key": "admin-secret-dev-key-123"}
    resp = await client.get("/admin/analytics/recovery?start_at=1999-01-01T00:00:00&end_at=1999-02-01T00:00:00", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    metrics = data["metrics_by_currency"]
    
    # Test multiple currencies are not combined
    assert "USD" in metrics
    assert "EUR" in metrics
    
    usd = metrics["USD"]
    assert usd["total_recovery_cases"] == 2
    assert usd["successful_recovery_cases"] == 1
    assert usd["failed_or_stopped_recovery_cases"] == 1
    assert usd["total_recovery_attempts"] == 3
    assert usd["successful_recovery_attempts"] == 1
    assert usd["failed_recovery_attempts"] == 2
    assert usd["amount_attempted"] == 150.0
    assert usd["amount_recovered"] == 100.0
    assert usd["amount_unrecovered"] == 50.0
    assert usd["recovery_rate"] == 100.0 / 150.0
    assert usd["success_rate"] == 0.5
    
    eur = metrics["EUR"]
    assert eur["amount_attempted"] == 200.0
    assert eur["amount_recovered"] == 200.0
    assert eur["recovery_rate"] == 1.0

@pytest.mark.anyio
async def test_time_range_boundaries(client):
    db = TestingSessionLocal()
    c1 = uuid4()
    create_mock_case(db, c1, 100.0, "USD", RecoveryState.RECOVERED, datetime(1998, 1, 1))
    c2 = uuid4()
    create_mock_case(db, c2, 100.0, "USD", RecoveryState.RECOVERED, datetime(1998, 1, 31, 23, 59, 59))
    c3 = uuid4()
    create_mock_case(db, c3, 100.0, "USD", RecoveryState.RECOVERED, datetime(1998, 2, 1)) # Outside range
    db.close()
    
    headers = {"X-Admin-API-Key": "admin-secret-dev-key-123"}
    resp = await client.get("/admin/analytics/recovery?start_at=1998-01-01T00:00:00&end_at=1998-02-01T00:00:00", headers=headers)
    assert resp.status_code == 200
    usd = resp.json()["metrics_by_currency"]["USD"]
    assert usd["total_recovery_cases"] == 2

@pytest.mark.anyio
async def test_zero_denominator_does_not_produce_nan(client):
    db = TestingSessionLocal()
    # Create case with 0 amount
    c1 = uuid4()
    create_mock_case(db, c1, 0.0, "USD", RecoveryState.OPEN, datetime(1999, 1, 15))
    db.close()
    
    headers = {"X-Admin-API-Key": "admin-secret-dev-key-123"}
    resp = await client.get("/admin/analytics/recovery?start_at=1999-01-01T00:00:00&end_at=1999-02-01T00:00:00", headers=headers)
    usd = resp.json()["metrics_by_currency"]["USD"]
    assert usd["recovery_rate"] == 0.0
    assert usd["success_rate"] == 0.0

@pytest.mark.anyio
async def test_analytics_does_not_mutate_state(client):
    db = TestingSessionLocal()
    c1 = uuid4()
    case = create_mock_case(db, c1, 100.0, "USD", RecoveryState.OPEN, datetime(1999, 1, 15))
    old_updated = case.updated_at
    db.close()
    
    headers = {"X-Admin-API-Key": "admin-secret-dev-key-123"}
    resp = await client.get("/admin/analytics/recovery?start_at=1999-01-01T00:00:00&end_at=1999-02-01T00:00:00", headers=headers)
    assert resp.status_code == 200
    
    db = TestingSessionLocal()
    case = db.query(RecoveryCase).filter_by(id=c1).first()
    assert case.status == RecoveryState.OPEN
    assert case.updated_at == old_updated
    db.close()

@pytest.mark.anyio
async def test_audit_event_is_atomic(client):
    db = TestingSessionLocal()
    from app.persistence.models.audit import AuditEvent
    initial_count = db.query(AuditEvent).filter_by(event_type="ANALYTICS_ACCESSED").count()
    db.close()
    
    headers = {"X-Admin-API-Key": "admin-secret-dev-key-123"}
    resp = await client.get("/admin/analytics/recovery?start_at=1999-01-01T00:00:00&end_at=1999-02-01T00:00:00", headers=headers)
    assert resp.status_code == 200
    
    db = TestingSessionLocal()
    final_count = db.query(AuditEvent).filter_by(event_type="ANALYTICS_ACCESSED").count()
    assert final_count == initial_count + 1
    db.close()





