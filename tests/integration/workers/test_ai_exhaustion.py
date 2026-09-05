import pytest
import os
from uuid import uuid4
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.persistence.database import Base
from app.persistence.models.audit import AuditEvent
from app.persistence.models.payment import Payment
from app.persistence.models.customer import Customer
from app.persistence.models.recovery import RecoveryCase, RecoveryJob
from app.domain.recovery.states import JobState, RecoveryState, PaymentState
from app.workers.executor.execution_service import ExecutionService
from app.ai.exceptions import AIDecisionError

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://user:password@postgres:5432/recovery_db")
engine = create_engine(DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield

def test_ai_exhaustion_nameerror_fix(monkeypatch):
    db = TestingSessionLocal()
    
    # Setup data
    cust_id = uuid4()
    cust = Customer(id=cust_id, external_id=f"ext_{cust_id}", email="test@test.com", name="Test")
    db.add(cust)
    
    pay_id = uuid4()
    pay = Payment(
        id=pay_id, 
        customer_id=cust_id, 
        external_id=f"ext_pay_{pay_id}",
        amount=100.0, 
        currency="USD", 
        status=PaymentState.FAILED
    )
    db.add(pay)
    
    case = RecoveryCase(
        payment_id=pay_id, 
        customer_id=cust_id,
        amount_at_risk=100.0,
        currency="USD",
        status=RecoveryState.OPEN, 
        failure_reason="insufficient_funds",
        max_attempts=3
    )
    db.add(case)
    db.commit()
    
    # Create a job that is already at max_attempts
    job = RecoveryJob(
        recovery_case_id=case.id,
        job_type="EVALUATE_RECOVERY",
        status=JobState.PENDING,
        scheduled_for=datetime.utcnow(),
        available_at=datetime.utcnow(),
        max_attempts=3,
        attempt_count=3,
        payload={"correlation_id": "test-exhaustion-123"}
    )
    db.add(job)
    db.commit()
    
    worker_id = "worker-exhaustion-test"
    
    # Mock the NemotronProvider to raise an exception
    class MockProvider:
        def decide(self, context):
            raise AIDecisionError("Simulated AI Failure")
    
    monkeypatch.setattr("app.workers.executor.execution_service.NemotronProvider", MockProvider)
    
    service = ExecutionService(db, worker_id)
    processed = service.process_next_job()
    
    assert processed is True
    
    # Verify job is failed
    db.refresh(job)
    assert job.status == JobState.FAILED
    assert job.last_error == "Simulated AI Failure"
    
    # Verify case is stopped
    db.refresh(case)
    assert case.status == RecoveryState.STOPPED
    
    # Verify audit event is created and has error
    audit = db.query(AuditEvent).filter_by(event_type="AI_EVALUATION_FAILED", entity_id=str(job.id)).first()
    assert audit is not None
    assert audit.payload["error"] == "Simulated AI Failure"
    
    db.close()
