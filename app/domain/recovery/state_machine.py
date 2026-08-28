from app.domain.recovery.states import RecoveryState, AttemptState, JobState, PaymentState

class InvalidStateTransition(Exception):
    pass

RECOVERY_CASE_TRANSITIONS = {
    RecoveryState.OPEN: [RecoveryState.DECISION_PENDING, RecoveryState.STOPPED],
    RecoveryState.DECISION_PENDING: [RecoveryState.ACTION_SCHEDULED, RecoveryState.STOPPED, RecoveryState.ESCALATED],
    RecoveryState.ACTION_SCHEDULED: [RecoveryState.ACTION_EXECUTING, RecoveryState.STOPPED, RecoveryState.DECISION_PENDING],
    RecoveryState.ACTION_EXECUTING: [RecoveryState.RECOVERED, RecoveryState.DECISION_PENDING, RecoveryState.STOPPED, RecoveryState.ESCALATED],
    RecoveryState.RECOVERED: [],
    RecoveryState.ESCALATED: [],
    RecoveryState.STOPPED: []
}

ATTEMPT_TRANSITIONS = {
    AttemptState.SCHEDULED: [AttemptState.RUNNING, AttemptState.CANCELLED],
    AttemptState.RUNNING: [AttemptState.SUCCEEDED, AttemptState.FAILED, AttemptState.AMBIGUOUS],
    AttemptState.AMBIGUOUS: [AttemptState.SUCCEEDED, AttemptState.FAILED, AttemptState.RUNNING],  # Can be resolved
    AttemptState.SUCCEEDED: [],
    AttemptState.FAILED: [],
    AttemptState.CANCELLED: []
}

PAYMENT_TRANSITIONS = {
    PaymentState.PENDING: [PaymentState.SUCCEEDED, PaymentState.FAILED],
    PaymentState.FAILED: [PaymentState.RECOVERY_PENDING, PaymentState.ABANDONED],
    PaymentState.RECOVERY_PENDING: [PaymentState.RECOVERED, PaymentState.ABANDONED],
    PaymentState.RECOVERED: [],
    PaymentState.SUCCEEDED: [],
    PaymentState.ABANDONED: []
}

def validate_transition(current_state, next_state, transitions_map):
    if next_state not in transitions_map.get(current_state, []):
        raise InvalidStateTransition(f"Cannot transition from {current_state} to {next_state}")
    return True
