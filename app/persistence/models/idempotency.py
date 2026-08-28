import uuid
from sqlalchemy import Column, String, DateTime, Integer, text as sql_text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.persistence.models.base import Base

class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    idempotency_key = Column(String, unique=True, nullable=False, index=True)
    request_hash = Column(String, nullable=False)
    response_status = Column(Integer, nullable=False)
    response_body = Column(JSONB, nullable=True)
    created_at = Column(DateTime, server_default=sql_text("CURRENT_TIMESTAMP"), nullable=False)
    expires_at = Column(DateTime, nullable=True)
