import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
import json
from uuid import uuid4

from app.main import app
from app.persistence.database import Base
from app.persistence.models.audit import AuditEvent
from app.persistence.models.payment import Payment
from app.persistence.models.customer import Customer
from app.domain.recovery.states import PaymentState
from app.utils.logger import JSONFormatter

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://user:password@postgres:5432/recovery_db")
engine = create_engine(DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_ready_endpoint():
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}

def test_correlation_id_middleware():
    custom_id = "test-correlation-12345"
    response = client.get("/health", headers={"X-Correlation-ID": custom_id})
    assert response.status_code == 200
    assert response.headers.get("X-Correlation-ID") == custom_id

def test_correlation_id_generated():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("X-Correlation-ID") is not None
    assert len(response.headers.get("X-Correlation-ID")) > 10

def test_logging_scrubs_secrets():
    import logging
    formatter = JSONFormatter()
    record = logging.LogRecord("test", logging.INFO, "test.py", 10, "Bearer sk-or-v1-abcdef", (), None)
    formatted = formatter.format(record)
    data = json.loads(formatted)
    assert "sk-" not in data["message"]
    assert data["message"] == "Bearer [SCRUBBED]"

def test_audit_event_created_on_webhook():
    db = TestingSessionLocal()
    c_id = uuid4()
    cust = Customer(id=c_id, external_id=f"ext_{c_id}_audit", email="audit@test.com", name="Audit Customer")
    db.add(cust)
    db.commit()

    payment_id = f"pay_audit_{uuid4()}"
    event_id = f"evt_{uuid4()}"
    
    payload = {
        "event_id": event_id,
        "type": "payment.failed",
        "payment_id": payment_id,
        "customer_id": str(c_id),
        "amount": "250.00",
        "currency": "USD",
        "failure_reason": "insufficient_funds"
    }

    # Process webhook
    response = client.post(
        "/webhooks/payment",
        json=payload,
        headers={"X-Razorpay-Signature": "dummy", "X-Correlation-ID": "webhook-correlation-555"}
    )
    assert response.status_code == 200

    # Check audit log
    audit = db.query(AuditEvent).filter_by(event_type="WEBHOOK_PROCESSED_PAYMENT.FAILED").order_by(AuditEvent.created_at.desc()).first()
    assert audit is not None
    assert audit.actor_type == "WEBHOOK"
    assert audit.payload["amount"] == 250.0
    # The correlation ID should have propagated
    assert audit.correlation_id == "webhook-correlation-555"
    
    db.close()
