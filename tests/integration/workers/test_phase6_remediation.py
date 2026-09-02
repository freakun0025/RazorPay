import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from uuid import uuid4
from datetime import datetime, timedelta

from app.persistence.database import Base
from app.persistence.models.audit import AuditEvent
from app.persistence.models.payment import Payment
from app.persistence.models.customer import Customer
from app.persistence.models.recovery import RecoveryCase, RecoveryJob, RecoveryAttempt
from app.domain.recovery.states import PaymentState, RecoveryState, JobState, AttemptState
from app.workers.executor.execution_service import ExecutionService
from app.utils.context import get_correlation_id, set_correlation_id

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://user:password@postgres:5432/recovery_db")
engine = create_engine(DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def setup_test_data(db):
    cid = uuid4()
    cust = Customer(id=cid, external_id=f"ext_{cid}", email="test@test.com", name="Test")
    db.add(cust)
    db.flush()
    
    pay = Payment(external_id=f"pay_{uuid4()}", customer_id=cid, amount=100.0, currency="USD", status=PaymentState.FAILED)
    db.add(pay)
    db.flush()
    
    case = RecoveryCase(
        payment_id=pay.id,
        customer_id=cid,
        amount_at_risk=100.0,
        currency="USD",
        status=RecoveryState.OPEN,
        failure_reason="test",
        max_attempts=3
    )
    db.add(case)
    db.commit()
    return case.id

class MockGateway:
    def verify_payment_status(self, key):
        return {"status": "failed"}
    def charge(self, key, amount, cur, cust):
        return {"status": "failed", "error": "insufficient_funds"}

def test_correlation_id_propagation_across_jobs():
    db = TestingSessionLocal()
    case_id = setup_test_data(db)
    
    token = set_correlation_id("test-corr-999")
    
    job1 = RecoveryJob(
        recovery_case_id=case_id,
        job_type="EVALUATE_RECOVERY",
        scheduled_for=datetime.utcnow(),
        status=JobState.PENDING,
        max_attempts=3,
        available_at=datetime.utcnow(),
        payload={"correlation_id": "test-corr-999"}
    )
    db.add(job1)
    db.commit()
    job1_id = job1.id
    db.close()
    
    db = TestingSessionLocal()
    svc = ExecutionService(db, "worker_1")
    
    class MockDecision:
        action = "CHARGE"
        confidence = 0.9
        reason = "test"
        
    import app.ai.gateway.provider as provider_module
    provider_module.NemotronProvider.decide = lambda self, context: MockDecision()
    
    while svc.process_next_job(): pass
    
    charge_job = db.query(RecoveryJob).filter_by(job_type="EXECUTE_CHARGE", recovery_case_id=case_id).first()
    assert charge_job is not None
    assert charge_job.payload.get("correlation_id") == "test-corr-999"
    db.close()

def test_worker_charge_exhaustion():
    db = TestingSessionLocal()
    case_id = setup_test_data(db)
    
    job = RecoveryJob(
        recovery_case_id=case_id,
        job_type="EXECUTE_CHARGE",
        scheduled_for=datetime.utcnow(),
        status=JobState.PENDING,
        max_attempts=3,
        attempt_count=2,  # Going to attempt 3
        available_at=datetime.utcnow(),
        payload={"correlation_id": "test-corr-exhaustion"}
    )
    db.add(job)
    db.commit()
    job_id = job.id
    db.close()
    
    db = TestingSessionLocal()
    svc = ExecutionService(db, "worker_1")
    svc.gateway = MockGateway()
    while svc.process_next_job(): pass
    
    job = db.query(RecoveryJob).filter_by(id=job_id).first()
    assert job.status == JobState.SUCCEEDED, f"JOB WAS PENDING. ERROR: {job.last_error}" 
    
    case = db.query(RecoveryCase).filter_by(id=case_id).first()
    assert case.status == RecoveryState.STOPPED
    
    audit = db.query(AuditEvent).filter_by(event_type="CHARGE_EXHAUSTED").first()
    assert audit is not None
    assert audit.correlation_id == "test-corr-exhaustion"
    db.close()
