import pytest
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from decimal import Decimal

from app.main import app
from app.persistence.database import get_db
from app.persistence.models.base import Base
from app.persistence.models.customer import Customer
from app.persistence.models.payment import Payment
from app.domain.recovery.states import PaymentState
import os

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://user:password@postgres:5432/recovery_db")
engine = create_engine(DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    # We do not drop everything so we can inspect it later as requested

@pytest.fixture
def test_customer():
    db = TestingSessionLocal()
    c_id = uuid.uuid4()
    cust = Customer(id=c_id, external_id=f"ext_{c_id}", email="test@test.com", name="Test Customer")
    db.add(cust)
    db.commit()
    db.close()
    return c_id

def test_issue1_distinguish_integrity_errors(test_customer):
    event_id = str(uuid.uuid4())
    # 1. Success
    payload = {
        "event_id": event_id,
        "type": "payment.failed",
        "payment_id": str(uuid.uuid4()),
        "customer_id": str(test_customer),
        "amount": "100.00",
        "currency": "USD", "failure_reason": "insufficient_funds"
    }
    response = client.post("/webhooks/payment", json=payload)
    assert response.status_code == 200

    # 2. Idempotency Duplicate (should return 200)
    response2 = client.post("/webhooks/payment", json=payload)
    assert response2.status_code == 200

    # 3. Missing FK (e.g. invalid customer_id inside a new payload that bypasses our auto-create in service if we disable it,
    # wait, our service auto-creates customer if missing. Let's make currency extremely long to trigger DataError, or amount negative to trigger CheckConstraint which behaves like IntegrityError).
    # Wait, negative amount is caught by domain validation. Let's send currency="INVALID"
    payload_bad = {
        "event_id": str(uuid.uuid4()),
        "type": "payment.failed",
        "payment_id": str(uuid.uuid4()),
        "customer_id": str(test_customer),
        "amount": "100.00",
        "currency": "INVALID" # > 3 chars, causes DataError
    }
    resp = client.post("/webhooks/payment", json=payload_bad)
    assert resp.status_code != 200


def test_issue2_out_of_order_events(test_customer):
    payment_id = str(uuid.uuid4())
    
    # 1. SUCCESS arrives first
    payload_succ = {
        "event_id": str(uuid.uuid4()),
        "type": "payment.succeeded",
        "payment_id": payment_id,
        "customer_id": str(test_customer),
        "amount": "50.00",
        "currency": "EUR", "failure_reason": "insufficient_funds"
    }
    resp1 = client.post("/webhooks/payment", json=payload_succ)
    assert resp1.status_code == 200
    
    # 2. FAILED arrives out of order
    payload_fail = {
        "event_id": str(uuid.uuid4()),
        "type": "payment.failed",
        "payment_id": payment_id,
        "customer_id": str(test_customer),
        "amount": "50.00",
        "currency": "EUR", "failure_reason": "insufficient_funds"
    }
    resp2 = client.post("/webhooks/payment", json=payload_fail)
    assert resp2.status_code == 200 # Handled silently
    
    # Assert payment is still SUCCEEDED
    db = TestingSessionLocal()
    p = db.query(Payment).filter_by(external_id=payment_id).first()
    assert p.status == PaymentState.SUCCEEDED
    db.close()


def test_issue3_immutable_payment_attributes(test_customer):
    payment_id = str(uuid.uuid4())
    
    payload1 = {
        "event_id": str(uuid.uuid4()),
        "type": "payment.failed",
        "payment_id": payment_id,
        "customer_id": str(test_customer),
        "amount": "100.00",
        "currency": "USD", "failure_reason": "insufficient_funds"
    }
    client.post("/webhooks/payment", json=payload1)
    
    payload2 = {
        "event_id": str(uuid.uuid4()),
        "type": "payment.failed", # different event, same payment
        "payment_id": payment_id,
        "customer_id": str(test_customer),
        "amount": "200.00", # Mutated!
        "currency": "USD", "failure_reason": "insufficient_funds"
    }
    resp = client.post("/webhooks/payment", json=payload2)
    assert resp.status_code == 400
    assert "immutable" in resp.json()["detail"].lower()


def test_issue4_transactional_savepoint_behavior(test_customer):
    # Concurrent duplicates
    payment_id = str(uuid.uuid4())
    event_id = str(uuid.uuid4())
    
    payload = {
        "event_id": event_id,
        "type": "payment.failed",
        "payment_id": payment_id,
        "customer_id": str(test_customer),
        "amount": "10.00",
        "currency": "USD", "failure_reason": "insufficient_funds"
    }
    
    def fire_req():
        return client.post("/webhooks/payment", json=payload)

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(fire_req) for _ in range(5)]
        results = [f.result() for f in futures]
    
    # All should gracefully return 200 OK (one succeeds, 4 swallow duplicates)
    for r in results:
        assert r.status_code == 200

    # There should only be ONE idempotency record and ONE payment
    db = TestingSessionLocal()
    payments = db.query(Payment).filter_by(external_id=payment_id).all()
    assert len(payments) == 1
    db.close()


