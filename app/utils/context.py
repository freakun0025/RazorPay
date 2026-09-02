import contextvars
import uuid

_correlation_id = contextvars.ContextVar("correlation_id", default=None)

def get_correlation_id() -> str:
    """Get the current correlation ID, or generate a new one if not set."""
    cid = _correlation_id.get()
    if not cid:
        cid = str(uuid.uuid4())
        _correlation_id.set(cid)
    return cid

def set_correlation_id(correlation_id: str) -> contextvars.Token:
    """Set the current correlation ID."""
    return _correlation_id.set(correlation_id)

def reset_correlation_id(token: contextvars.Token) -> None:
    """Reset the correlation ID to the previous value."""
    _correlation_id.reset(token)
