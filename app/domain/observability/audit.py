from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.persistence.models.audit import AuditEvent
from app.utils.context import get_correlation_id

def create_audit_event(
    session: Session,
    entity_type: str,
    entity_id: str,
    event_type: str,
    actor_type: str,
    payload: Dict[str, Any],
    actor_id: Optional[str] = None
) -> None:
    '''
    Creates an AuditEvent in the given database session.
    It deliberately DOES NOT commit the session.
    The caller is responsible for committing the session so the state change
    and audit log are atomically coupled.
    '''
    safe_payload = _scrub_payload(payload)
    
    audit = AuditEvent(
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        actor_type=actor_type,
        actor_id=actor_id,
        payload=safe_payload,
        correlation_id=get_correlation_id()
    )
    session.add(audit)

def _scrub_payload(payload: Any) -> Any:
    sensitive_keys = {"api_key", "password", "secret", "authorization", "sk-", "token"}
    
    if isinstance(payload, dict):
        safe_copy = {}
        for key, value in payload.items():
            if any(sec_key in str(key).lower() for sec_key in sensitive_keys):
                safe_copy[key] = "[SCRUBBED SENSITIVE DATA]"
            else:
                safe_copy[key] = _scrub_payload(value)
        return safe_copy
    elif isinstance(payload, list):
        return [_scrub_payload(item) for item in payload]
    elif isinstance(payload, str):
        if "sk-" in payload or "Bearer " in payload:
            return "[SCRUBBED SENSITIVE DATA]"
        return payload
    else:
        return payload
