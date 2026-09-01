import pytest
import uuid
import time
import json
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os

from app.persistence.database import get_db
from app.persistence.models.base import Base
from app.persistence.models.customer import Customer
from app.persistence.models.payment import Payment, PaymentState
from app.persistence.models.recovery import RecoveryCase, RecoveryJob, RecoveryAttempt, RecoveryState, JobState, AttemptState, RecoveryDecision
from app.workers.executor.execution_service import ExecutionService
from app.ai.contracts import RecoveryDecisionContext, RecoveryDecision as AIDecision
from app.ai.gateway.provider import NemotronProvider
from app.ai.exceptions import AIDecisionError

DATABASE_URL = "postgresql://user:password@postgres:5432/recovery_db"
engine = create_engine(DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function", autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield

def create_evaluate_job(session):
    c_id = uuid.uuid4()
    p_id = uuid.uuid4()
    
    cust = Customer(id=c_id, external_id=f"ext_{c_id}", email="test_ai@test.com", name="AI Customer")
    session.add(cust)
    
    pay = Payment(
        id=p_id,
        external_id=f"pay_{p_id}",
        customer_id=c_id,
        amount=50.0,
        currency="USD",
        status=PaymentState.FAILED
    )
    session.add(pay)
    
    case = RecoveryCase(
        id=uuid.uuid4(),
        payment_id=p_id,
        customer_id=c_id,
        amount_at_risk=50.0,
        currency="USD",
        status=RecoveryState.OPEN,
        failure_reason="insufficient_funds",
        max_attempts=3,
        started_at=datetime.utcnow() - timedelta(days=2)
    )
    session.add(case)
    
    job = RecoveryJob(
        id=uuid.uuid4(),
        recovery_case_id=case.id,
        job_type="EVALUATE_RECOVERY",
        status=JobState.PENDING,
        scheduled_for=datetime.utcnow(),
        available_at=datetime.utcnow() - timedelta(minutes=1),
        max_attempts=3
    )
    session.add(job)
    session.commit()
    
    return job.id, pay.external_id

class MockMessage:
    def __init__(self, content):
        self.content = content

class MockChoice:
    def __init__(self, content):
        self.message = MockMessage(content)

class MockResponse:
    def __init__(self, content):
        self.choices = [MockChoice(content)]

class MockCompletions:
    def __init__(self):
        self.next_response = None
        self.next_error = None
        self.last_messages = None
        
    def create(self, model, messages, response_format):
        self.last_messages = messages
        if self.next_error:
            raise self.next_error
        return MockResponse(self.next_response)

class MockChat:
    def __init__(self):
        self.completions = MockCompletions()

class MockClient:
    def __init__(self, *args, **kwargs):
        self.chat = MockChat()

@pytest.fixture
def mock_openai(monkeypatch):
    import openai
    
    mock_instance = MockClient()
    def mock_init(*args, **kwargs):
        return mock_instance
        
    monkeypatch.setattr(openai, "OpenAI", mock_init)
    return mock_instance

def test_ai_provider_valid_decision(mock_openai):
    mock_openai.chat.completions.next_response = '{"action": "CHARGE", "reason": "Looks good", "confidence": 0.9}'
    provider = NemotronProvider()
    context = RecoveryDecisionContext(failure_reason="test", attempt_count=1, days_since_failure=1, amount=10.0, currency="USD")
    decision = provider.decide(context)
    
    assert decision.action == "CHARGE"
    assert decision.confidence == 0.9
    
    user_msg = mock_openai.chat.completions.last_messages[1]["content"]
    assert "amount" in user_msg
    assert "payment_id" not in user_msg

def test_ai_provider_invalid_action(mock_openai):
    mock_openai.chat.completions.next_response = '{"action": "REFUND", "reason": "Refund it", "confidence": 0.9}'
    provider = NemotronProvider()
    context = RecoveryDecisionContext(failure_reason="test", attempt_count=1, days_since_failure=1, amount=10.0, currency="USD")
    with pytest.raises(AIDecisionError) as e:
        provider.decide(context)
    assert "Invalid structured output" in str(e.value)
    
def test_ai_provider_invalid_confidence(mock_openai):
    mock_openai.chat.completions.next_response = '{"action": "CHARGE", "reason": "Refund it", "confidence": 1.5}'
    provider = NemotronProvider()
    context = RecoveryDecisionContext(failure_reason="test", attempt_count=1, days_since_failure=1, amount=10.0, currency="USD")
    with pytest.raises(AIDecisionError) as e:
        provider.decide(context)
    assert "Invalid structured output" in str(e.value)
    
def test_ai_provider_timeout(mock_openai):
    import openai
    mock_openai.chat.completions.next_error = openai.APITimeoutError(request=None)
    provider = NemotronProvider()
    context = RecoveryDecisionContext(failure_reason="test", attempt_count=1, days_since_failure=1, amount=10.0, currency="USD")
    with pytest.raises(AIDecisionError):
        provider.decide(context)

def test_routing_charge(mock_openai):
    mock_openai.chat.completions.next_response = '{"action": "CHARGE", "reason": "Try again", "confidence": 0.8}'
    session = TestingSessionLocal()
    job_id, _ = create_evaluate_job(session)
    session.close()
    
    sess = TestingSessionLocal()
    service = ExecutionService(sess, "worker_1")
    service.process_next_job()
    
    sess2 = TestingSessionLocal()
    eval_job = sess2.query(RecoveryJob).filter_by(id=job_id).first()
    assert eval_job.status == JobState.SUCCEEDED
    
    charge_job = sess2.query(RecoveryJob).filter_by(recovery_case_id=eval_job.recovery_case_id, job_type="EXECUTE_CHARGE").first()
    assert charge_job is not None
    assert charge_job.status == JobState.PENDING
    
    dec = sess2.query(RecoveryDecision).filter_by(recovery_case_id=eval_job.recovery_case_id).first()
    assert dec.action_type == "CHARGE"
    sess2.close()
    
def test_routing_abort(mock_openai):
    mock_openai.chat.completions.next_response = '{"action": "ABORT", "reason": "Too risky", "confidence": 0.95}'
    session = TestingSessionLocal()
    job_id, _ = create_evaluate_job(session)
    session.close()
    
    sess = TestingSessionLocal()
    service = ExecutionService(sess, "worker_1")
    service.process_next_job()
    
    sess2 = TestingSessionLocal()
    eval_job = sess2.query(RecoveryJob).filter_by(id=job_id).first()
    assert eval_job.status == JobState.SUCCEEDED
    
    case = sess2.query(RecoveryCase).filter_by(id=eval_job.recovery_case_id).first()
    assert case.status == RecoveryState.STOPPED
    sess2.close()
    
def test_routing_delay(mock_openai):
    mock_openai.chat.completions.next_response = '{"action": "DELAY", "reason": "Wait a bit", "confidence": 0.95}'
    session = TestingSessionLocal()
    job_id, _ = create_evaluate_job(session)
    session.close()
    
    sess = TestingSessionLocal()
    service = ExecutionService(sess, "worker_1")
    service.process_next_job()
    
    sess2 = TestingSessionLocal()
    eval_job = sess2.query(RecoveryJob).filter_by(id=job_id).first()
    assert eval_job.status == JobState.SUCCEEDED
    
    delay_job = sess2.query(RecoveryJob).filter(
        RecoveryJob.recovery_case_id == eval_job.recovery_case_id,
        RecoveryJob.id != job_id
    ).first()
    assert delay_job is not None
    assert delay_job.job_type == "EVALUATE_RECOVERY"
    assert delay_job.available_at > datetime.utcnow() + timedelta(hours=23)
    sess2.close()
    
def test_payment_succeeded_during_evaluation(mock_openai, monkeypatch):
    mock_openai.chat.completions.next_response = '{"action": "CHARGE", "reason": "Go", "confidence": 0.95}'
    session = TestingSessionLocal()
    job_id, pay_ext = create_evaluate_job(session)
    session.close()
    
    sess = TestingSessionLocal()
    service = ExecutionService(sess, "worker_1")
    
    real_decide = NemotronProvider.decide
    def hooked_decide(self, context):
        sess_wh = TestingSessionLocal()
        pay = sess_wh.query(Payment).filter_by(external_id=pay_ext).first()
        pay.status = PaymentState.SUCCEEDED 
        sess_wh.commit()
        sess_wh.close()
        return real_decide(self, context)
        
    monkeypatch.setattr(NemotronProvider, "decide", hooked_decide)
    
    service.process_next_job()
    
    sess2 = TestingSessionLocal()
    eval_job = sess2.query(RecoveryJob).filter_by(id=job_id).first()
    assert eval_job.status == JobState.CANCELLED
    
    charge_job = sess2.query(RecoveryJob).filter_by(recovery_case_id=eval_job.recovery_case_id, job_type="EXECUTE_CHARGE").first()
    assert charge_job is None
    sess2.close()

