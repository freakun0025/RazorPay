import uuid
from sqlalchemy import Column, String, DateTime, text as sql_text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.persistence.models.base import Base

class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type = Column(String, nullable=False, index=True)
    entity_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    event_type = Column(String, nullable=False)
    actor_type = Column(String, nullable=False) # SYSTEM, AI, WORKER, USER
    actor_id = Column(String, nullable=True)
    payload = Column(JSONB, nullable=False)
    correlation_id = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, server_default=sql_text("CURRENT_TIMESTAMP"), nullable=False)
