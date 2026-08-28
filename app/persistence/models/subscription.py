import uuid
from sqlalchemy import Column, String, DateTime, Numeric, Enum as SQLEnum, text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.persistence.models.base import Base
from app.domain.recovery.states import SubscriptionState

class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    external_id = Column(String, unique=True, nullable=False)
    status = Column(SQLEnum(SubscriptionState, name="subscription_state_enum"), nullable=False)
    amount = Column(Numeric(precision=12, scale=4), nullable=False)
    currency = Column(String(3), nullable=False)
    billing_interval = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    updated_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), onupdate=text("CURRENT_TIMESTAMP"), nullable=False)
