from pydantic import BaseModel, constr
from decimal import Decimal
from uuid import UUID
from typing import Optional

class WebhookEvent(BaseModel):
    event_id: str
    type: str
    payment_id: str
    customer_id: UUID
    amount: Decimal
    currency: constr(min_length=3, max_length=3)
    failure_reason: Optional[str] = None
