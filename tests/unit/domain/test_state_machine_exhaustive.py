import pytest
from app.domain.recovery.states import RecoveryState, AttemptState, PaymentState
from app.domain.recovery.state_machine import (
    validate_transition,
    InvalidStateTransition,
    RECOVERY_CASE_TRANSITIONS,
    ATTEMPT_TRANSITIONS,
    PAYMENT_TRANSITIONS
)

def test_exhaustive_recovery_case():
    terminals = [RecoveryState.RECOVERED, RecoveryState.ESCALATED, RecoveryState.STOPPED]
    for state in terminals:
        # Terminal states should have no valid transitions
        assert len(RECOVERY_CASE_TRANSITIONS.get(state, [])) == 0

    # Ensure we cannot go from terminal to active
    for state in terminals:
        with pytest.raises(InvalidStateTransition):
            validate_transition(state, RecoveryState.OPEN, RECOVERY_CASE_TRANSITIONS)

def test_exhaustive_attempt_state():
    # AMBIGUOUS transitions
    assert validate_transition(AttemptState.AMBIGUOUS, AttemptState.RUNNING, ATTEMPT_TRANSITIONS) == True
    assert validate_transition(AttemptState.AMBIGUOUS, AttemptState.SUCCEEDED, ATTEMPT_TRANSITIONS) == True
    assert validate_transition(AttemptState.AMBIGUOUS, AttemptState.FAILED, ATTEMPT_TRANSITIONS) == True

    # AMBIGUOUS cannot go to SCHEDULED or CANCELLED
    with pytest.raises(InvalidStateTransition):
        validate_transition(AttemptState.AMBIGUOUS, AttemptState.SCHEDULED, ATTEMPT_TRANSITIONS)
    with pytest.raises(InvalidStateTransition):
        validate_transition(AttemptState.AMBIGUOUS, AttemptState.CANCELLED, ATTEMPT_TRANSITIONS)

    # CANCELLED is terminal
    assert len(ATTEMPT_TRANSITIONS.get(AttemptState.CANCELLED, [])) == 0
