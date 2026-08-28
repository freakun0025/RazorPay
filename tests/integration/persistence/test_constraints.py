import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
import os

from app.persistence.models.base import Base
from app.persistence.models.idempotency import IdempotencyRecord
from app.persistence.models.recovery import RecoveryCase, RecoveryAttempt
from app.persistence.models.payment import Payment
from app.persistence.models.customer import Customer
from app.domain.recovery.states import RecoveryState, AttemptState, PaymentState

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://user:password@postgres:5432/recovery_db")

@pytest.fixture(scope="module")
def engine():
    engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(engine)
    yield engine
    # Base.metadata.drop_all(engine) # keep it for inspection

@pytest.fixture
def session(engine):
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()

def test_idempotency_key_uniqueness(session):
    record1 = IdempotencyRecord(idempotency_key="key_123", request_hash="hash1", response_status=200)
    session.add(record1)
    session.commit()

    record2 = IdempotencyRecord(idempotency_key="key_123", request_hash="hash2", response_status=200)
    session.add(record2)
    
    with pytest.raises(IntegrityError):
        session.commit()

def test_active_recovery_case_uniqueness(session):
    # Setup customer and payment
    customer = Customer(external_id="cust_1", email="test@test.com", name="Test")
    session.add(customer)
    session.commit()

    payment = Payment(
        external_id="pay_1", customer_id=customer.id, 
        amount=100.0, currency="USD", status=PaymentState.FAILED
    )
    session.add(payment)
    session.commit()

    # Active Case 1
    case1 = RecoveryCase(
        payment_id=payment.id, customer_id=customer.id,
        amount_at_risk=100.0, currency="USD", status=RecoveryState.OPEN,
        failure_reason="insufficient_funds", max_attempts=3
    )
    session.add(case1)
    session.commit()

    # Active Case 2 (Should Fail)
    case2 = RecoveryCase(
        payment_id=payment.id, customer_id=customer.id,
        amount_at_risk=100.0, currency="USD", status=RecoveryState.DECISION_PENDING,
        failure_reason="insufficient_funds", max_attempts=3
    )
    session.add(case2)
    with pytest.raises(IntegrityError):
        session.commit()
    
    session.rollback()

    # Terminal Case (Should Succeed since the constraint ignores STOPPED/RECOVERED/ESCALATED)
    # Wait, case1 is still OPEN, so ANY new case should fail if the constraint applies to the new row?
    # Actually, the partial index prevents multiple rows where status is active.
    # If case1 is OPEN, and case3 is STOPPED, the index DOES NOT INCLUDE case3.
    # But wait, does the index prevent inserting a STOPPED case if an OPEN case exists?
    # Postgres partial unique index: UNIQUE (payment_id) WHERE status NOT IN (...)
    # Since case1 is in the index, inserting case3 (STOPPED) doesn't enter the index, so it doesn't conflict!
    case3 = RecoveryCase(
        payment_id=payment.id, customer_id=customer.id,
        amount_at_risk=100.0, currency="USD", status=RecoveryState.STOPPED,
        failure_reason="insufficient_funds", max_attempts=3
    )
    session.add(case3)
    session.commit() # Should succeed!

def test_recovery_attempt_uniqueness(session):
    # Need customer, payment, case
    customer = Customer(external_id="cust_2", email="test2@test.com", name="Test")
    session.add(customer)
    session.commit()

    payment = Payment(
        external_id="pay_2", customer_id=customer.id, 
        amount=100.0, currency="USD", status=PaymentState.FAILED
    )
    session.add(payment)
    session.commit()

    case = RecoveryCase(
        payment_id=payment.id, customer_id=customer.id,
        amount_at_risk=100.0, currency="USD", status=RecoveryState.OPEN,
        failure_reason="insufficient_funds", max_attempts=3
    )
    session.add(case)
    session.commit()

    attempt1 = RecoveryAttempt(
        recovery_case_id=case.id, attempt_number=1,
        action_type="RETRY", status=AttemptState.RUNNING
    )
    session.add(attempt1)
    session.commit()

    attempt2 = RecoveryAttempt(
        recovery_case_id=case.id, attempt_number=1,
        action_type="SEND_EMAIL", status=AttemptState.SCHEDULED
    )
    session.add(attempt2)
    with pytest.raises(IntegrityError):
        session.commit()
