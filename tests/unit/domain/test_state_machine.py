import pytest
from app.domain.recovery.states import RecoveryState, AttemptState, PaymentState
from app.domain.recovery.state_machine import (
    validate_transition,
    InvalidStateTransition,
    RECOVERY_CASE_TRANSITIONS,
    ATTEMPT_TRANSITIONS,
    PAYMENT_TRANSITIONS
)

def test_valid_recovery_case_transition():
    # OPEN -> DECISION_PENDING
    assert validate_transition(RecoveryState.OPEN, RecoveryState.DECISION_PENDING, RECOVERY_CASE_TRANSITIONS) == True

def test_invalid_recovery_case_transition():
    # OPEN -> RECOVERED is invalid
    with pytest.raises(InvalidStateTransition):
        validate_transition(RecoveryState.OPEN, RecoveryState.RECOVERED, RECOVERY_CASE_TRANSITIONS)

def test_attempt_ambiguous_resolution():
    # RUNNING -> AMBIGUOUS
    assert validate_transition(AttemptState.RUNNING, AttemptState.AMBIGUOUS, ATTEMPT_TRANSITIONS) == True
    # AMBIGUOUS -> RUNNING (re-queue/retry network check)
    assert validate_transition(AttemptState.AMBIGUOUS, AttemptState.RUNNING, ATTEMPT_TRANSITIONS) == True
    # AMBIGUOUS -> FAILED (reconciled as failed)
    assert validate_transition(AttemptState.AMBIGUOUS, AttemptState.FAILED, ATTEMPT_TRANSITIONS) == True

def test_invalid_attempt_transition():
    # CANCELLED -> SUCCEEDED is invalid
    with pytest.raises(InvalidStateTransition):
        validate_transition(AttemptState.CANCELLED, AttemptState.SUCCEEDED, ATTEMPT_TRANSITIONS)

def test_payment_transitions():
    assert validate_transition(PaymentState.PENDING, PaymentState.FAILED, PAYMENT_TRANSITIONS) == True
    assert validate_transition(PaymentState.FAILED, PaymentState.RECOVERY_PENDING, PAYMENT_TRANSITIONS) == True
    
    with pytest.raises(InvalidStateTransition):
        validate_transition(PaymentState.RECOVERED, PaymentState.FAILED, PAYMENT_TRANSITIONS)
