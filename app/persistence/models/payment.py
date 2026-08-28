from sqlalchemy import CheckConstraint
import uuid
from sqlalchemy import Column, String, DateTime, Numeric, Enum as SQLEnum, Integer, text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.persistence.models.base import Base
from app.domain.recovery.states import PaymentState

class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_id = Column(String, unique=True, nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.id"), nullable=True)
    amount = Column(Numeric(precision=12, scale=4), nullable=False)
    currency = Column(String(3), nullable=False)
    status = Column(SQLEnum(PaymentState, name="payment_state_enum"), nullable=False)
    failure_code = Column(String, nullable=True)
    failure_message = Column(String, nullable=True)
    attempt_count = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    updated_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), onupdate=text("CURRENT_TIMESTAMP"), nullable=False)

    __table_args__ = (
        CheckConstraint('amount >= 0', name='chk_payment_amount_positive'),
    )

