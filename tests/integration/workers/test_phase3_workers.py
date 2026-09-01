import pytest
import uuid
import time
import importlib
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.persistence.database import get_db
from app.persistence.models.base import Base
from app.persistence.models.customer import Customer
from app.persistence.models.payment import Payment, PaymentState
from app.persistence.models.recovery import RecoveryCase, RecoveryJob, RecoveryAttempt, RecoveryState, JobState, AttemptState
from app.workers.executor.execution_service import ExecutionService
from app.integrations.payment_gateway.mock_client import MockGatewayClient
from app.persistence.repositories.job_repo import StaleWorkerError
import os

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://user:password@postgres:5432/recovery_db")
engine = create_engine(DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    MockGatewayClient.reset()

@pytest.fixture(autouse=True)
def reset_gateway():
    MockGatewayClient.reset()

def create_job_scenario(session):
    c_id = uuid.uuid4()
    p_id = uuid.uuid4()
    
    cust = Customer(id=c_id, external_id=f"ext_{c_id}", email="test@test.com", name="Test Customer")
    session.add(cust)
    
    pay = Payment(
        id=p_id,
        external_id=f"pay_{p_id}",
        customer_id=c_id,
        amount=100.0,
        currency="USD",
        status=PaymentState.FAILED,
        attempt_count=0
    )
    session.add(pay)
    
    case = RecoveryCase(
        payment_id=p_id,
        customer_id=c_id,
        amount_at_risk=100.0,
        currency="USD",
        status=RecoveryState.OPEN,
        failure_reason="insufficient_funds",
        attempt_count=0,
        max_attempts=3
    )
    session.add(case)
    session.flush()
    
    job = RecoveryJob(
        recovery_case_id=case.id,
        job_type="EXECUTE_CHARGE",
        status=JobState.PENDING,
        scheduled_for=datetime.utcnow(),
        available_at=datetime.utcnow(),
        max_attempts=3
    )
    session.add(job)
    session.commit()
    
    return job.id, pay.external_id

def test_concurrent_job_claiming():
    session = TestingSessionLocal()
    job_id, _ = create_job_scenario(session)
    session.close()
    
    def claim_job(worker_id):
        sess = TestingSessionLocal()
        service = ExecutionService(sess, worker_id)
        sess.begin()
        job = service.job_repo.claim_job(worker_id)
        sess.commit()
        jid = job.id if job else None
        sess.close()
        return jid

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(claim_job, "worker_1")
        f2 = executor.submit(claim_job, "worker_2")
        job1 = f1.result()
        job2 = f2.result()
    
    claimed = [j for j in (job1, job2) if j is not None]
    assert len(claimed) == 1
    assert claimed[0] == job_id

def test_zombie_worker_protection():
    session = TestingSessionLocal()
    job_id, pay_ext = create_job_scenario(session)
    session.close()
    
    sess1 = TestingSessionLocal()
    service1 = ExecutionService(sess1, "worker_A")
    sess1.begin()
    jobA = service1.job_repo.claim_job("worker_A")
    attempt_id = jobA.attempt_id
    sess1.commit() 
    
    sess2 = TestingSessionLocal()
    sess2.execute(text("UPDATE recovery_jobs SET locked_at = locked_at - interval '61 seconds' WHERE id = :id"), {"id": job_id})
    sess2.commit()
    
    service2 = ExecutionService(sess2, "worker_B")
    sess2.begin()
    jobB = service2.job_repo.claim_job("worker_B")
    sess2.commit()
    
    assert jobB is not None
    assert jobB.locked_by == "worker_B"
    
    sess1.begin()
    with pytest.raises(StaleWorkerError):
        service1.job_repo.safe_update_status(job_id, "worker_A", JobState.SUCCEEDED)
    sess1.rollback()
    
    # Reload and verify no corruption!
    sess_verify = TestingSessionLocal()
    job_verify = sess_verify.query(RecoveryJob).filter_by(id=job_id).first()
    pay_verify = sess_verify.query(Payment).filter_by(external_id=pay_ext).first()
    assert job_verify.locked_by == "worker_B"
    assert job_verify.status == JobState.RUNNING # worker B has it
    assert pay_verify.status == PaymentState.FAILED # Not accidentally SUCCEEDED!
    sess_verify.close()
    
    sess1.close()
    sess2.close()

def test_gateway_timeout_and_reconciliation_404():
    session = TestingSessionLocal()
    job_id, pay_ext = create_job_scenario(session)
    session.close()
    
    sess = TestingSessionLocal()
    service = ExecutionService(sess, "worker_1")
    
    idem_key = f"{pay_ext}_attempt_1"
    MockGatewayClient.set_behavior(idem_key, "timeout_drop")
    
    service.process_next_job()
    
    session = TestingSessionLocal()
    job = session.query(RecoveryJob).filter_by(id=job_id).first()
    assert job.status == JobState.PENDING 
    attempt = session.query(RecoveryAttempt).filter_by(id=job.attempt_id).first()
    assert attempt.status == AttemptState.AMBIGUOUS
    session.close()
    
    MockGatewayClient.set_behavior(idem_key, "success") 
    
    sess2 = TestingSessionLocal()
    service2 = ExecutionService(sess2, "worker_2")
    service2.process_next_job()
    
    session = TestingSessionLocal()
    attempt = session.query(RecoveryAttempt).filter_by(id=job.attempt_id).first()
    assert attempt.status == AttemptState.SUCCEEDED
    assert attempt.attempt_number == 1 
    session.close()

def test_hard_crash_reconciliation_retains_idempotency_key():
        session = TestingSessionLocal()
        job_id, pay_ext = create_job_scenario(session)
        session.close()
    
        sess1 = TestingSessionLocal()
        service1 = ExecutionService(sess1, "worker_A")
        
        idem_key = f"{pay_ext}_attempt_1"
        class HardCrashException(BaseException): pass
        
        original_charge = service1.gateway.charge
        def crashing_charge(*args, **kwargs):
            raise HardCrashException("Worker dies instantly")
        service1.gateway.charge = crashing_charge
        
        try:
            service1.process_next_job()
        except HardCrashException:
            sess1.rollback()
            sess1.close() # Simulated death!
            
        # At this point, job is RUNNING and Attempt is RUNNING (Tx1 committed, Tx2 never ran)
        sess2 = TestingSessionLocal()
        sess2.execute(text("UPDATE recovery_jobs SET locked_at = locked_at - interval '61 seconds' WHERE id = :id"), {"id": job_id})
        sess2.commit()
    
        MockGatewayClient.set_behavior(idem_key, "success") 
        service2 = ExecutionService(sess2, "worker_B")
        service2.process_next_job()
        
        sess_verify = TestingSessionLocal()
        job = sess_verify.query(RecoveryJob).filter_by(id=job_id).first()
        attempt_verify = sess_verify.query(RecoveryAttempt).filter_by(id=job.attempt_id).first()
        assert attempt_verify.status == AttemptState.SUCCEEDED
        assert attempt_verify.attempt_number == 1 
        sess_verify.close()


def test_concurrent_idempotent_requests():
    # Demonstrates delayed packet arriving exactly as retry
    client = MockGatewayClient()
    idem_key = f"concurrent_key_{uuid.uuid4()}"
    
    def shoot():
        return client.charge(idem_key, 100.0, "USD", "cust_123")
        
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(shoot) for _ in range(5)]
        results = [f.result() for f in futures]
        
    # All 5 should get the exact same transaction ID and success result
    first_tx_id = results[0]["transaction_id"]
    for r in results:
        assert r["status"] == "succeeded"
        assert r["transaction_id"] == first_tx_id

def test_payment_succeeds_during_worker_execution():
    session = TestingSessionLocal()
    job_id, pay_ext = create_job_scenario(session)
    session.close()
    
    sess = TestingSessionLocal()
    service = ExecutionService(sess, "worker_1")
    
    original_charge = service.gateway.charge
    def hooked_charge(*args, **kwargs):
        sess_wh = TestingSessionLocal()
        pay = sess_wh.query(Payment).filter_by(external_id=pay_ext).first()
        pay.status = PaymentState.SUCCEEDED 
        sess_wh.commit()
        sess_wh.close()
        return original_charge(*args, **kwargs)
        
    service.gateway.charge = hooked_charge
    service.process_next_job()
    
    session = TestingSessionLocal()
    pay = session.query(Payment).filter_by(external_id=pay_ext).first()
    assert pay.status == PaymentState.SUCCEEDED
    session.close()

def test_jit_validation_aborts_if_succeeded():
    session = TestingSessionLocal()
    job_id, pay_ext = create_job_scenario(session)
    
    pay = session.query(Payment).filter_by(external_id=pay_ext).first()
    pay.status = PaymentState.SUCCEEDED
    session.commit()
    session.close()
    
    sess = TestingSessionLocal()
    service = ExecutionService(sess, "worker_1")
    res = service.process_next_job()
    
    assert res == True
    
    session = TestingSessionLocal()
    job = session.query(RecoveryJob).filter_by(id=job_id).first()
    assert job.status == JobState.CANCELLED 
    session.close()

def test_timeout_hierarchy_validation(monkeypatch):
    import app.config.settings
    from app.config.settings import ImproperlyConfigured
    import importlib
    
    monkeypatch.setenv("GATEWAY_HTTP_TIMEOUT", "60")
    monkeypatch.setenv("WORKER_LEASE_TIMEOUT", "30")
    
    try:
        importlib.reload(app.config.settings)
        assert False, "Should have raised"
    except Exception as e:
        assert "Gateway timeout" in str(e)
    
    monkeypatch.setenv("GATEWAY_HTTP_TIMEOUT", "30")
    monkeypatch.setenv("WORKER_LEASE_TIMEOUT", "60")
    importlib.reload(app.config.settings)










