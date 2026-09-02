import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from uuid import uuid4
from datetime import datetime, timedelta

from app.main import app
from app.persistence.database import Base
from app.persistence.models.audit import AuditEvent
from app.persistence.models.payment import Payment
from app.persistence.models.customer import Customer
from app.persistence.models.recovery import RecoveryCase, RecoveryJob, RecoveryAttempt
from app.domain.recovery.states import PaymentState, RecoveryState, JobState, AttemptState
from app.domain.observability.audit import _scrub_payload
from app.utils.context import get_correlation_id, set_correlation_id, reset_correlation_id

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://user:password@postgres:5432/recovery_db")
engine = create_engine(DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

client = TestClient(app)

def test_malicious_correlation_id():
    malicious_id = "A" * 100 + "\n\r" + "B" * 50
    response = client.get("/health", headers={"X-Correlation-ID": malicious_id})
    assert response.status_code == 200
    
    returned_id = response.headers.get("X-Correlation-ID")
    assert len(returned_id) <= 72
    assert "\n" not in returned_id
    assert "\r" not in returned_id
    assert returned_id == "A" * 72

def test_audit_nested_secret_scrubbing():
    payload = {
        "user": "safe_user",
        "nested": {
            "api_key": "sk-123456789",
            "gateway_token": "secret_abc",
            "deep": [
                {"authorization": "Bearer xyz"},
                {"safe_field": 123}
            ]
        },
        "list_of_hidden": ["sk-abcdef", "safe_val"]
    }
    
    scrubbed = _scrub_payload(payload)
    
    assert scrubbed["user"] == "safe_user"
    assert scrubbed["nested"]["api_key"] == "[SCRUBBED SENSITIVE DATA]"
    assert scrubbed["nested"]["gateway_token"] == "[SCRUBBED SENSITIVE DATA]"
    assert scrubbed["nested"]["deep"][0]["authorization"] == "[SCRUBBED SENSITIVE DATA]"
    assert scrubbed["nested"]["deep"][1]["safe_field"] == 123
    assert scrubbed["list_of_hidden"][0] == "[SCRUBBED SENSITIVE DATA]"
    assert scrubbed["list_of_hidden"][1] == "safe_val"
    
    # Original untouched? dict() shallow copy means deep elements could mutate 
    # but we built a new dict inside recursive function, so original should be completely safe
    assert payload["nested"]["api_key"] == "sk-123456789"
