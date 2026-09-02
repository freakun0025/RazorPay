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
    """
    Creates an AuditEvent in the given database session.
    It deliberately DOES NOT commit the session.
    The caller is responsible for committing the session so the state change
    and audit log are atomically coupled.
    """
    # Scrub sensitive payload keys just in case
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

def _scrub_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    safe_copy = dict(payload)
    sensitive_keys = {"api_key", "password", "secret", "authorization", "sk-"}
    
    for key, value in safe_copy.items():
        if any(sec_key in key.lower() for sec_key in sensitive_keys):
            safe_copy[key] = "[SCRUBBED SENSITIVE DATA]"
        elif isinstance(value, str) and ("sk-" in value or "Bearer " in value):
            safe_copy[key] = "[SCRUBBED SENSITIVE DATA]"
            
    return safe_copy
