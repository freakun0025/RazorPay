from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime
from uuid import UUID

class RecoveryJobResponse(BaseModel):
    id: UUID
    job_type: str
    status: str
    attempts: int
    max_attempts: int
    scheduled_for: datetime
    available_at: datetime
    locked_by: Optional[str]
    locked_at: Optional[datetime]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class RecoveryCaseResponse(BaseModel):
    id: UUID
    payment_id: UUID
    customer_id: UUID
    amount_at_risk: float
    currency: str
    status: str
    failure_reason: str
    created_at: datetime
    updated_at: datetime
    jobs: List[RecoveryJobResponse] = []

    model_config = ConfigDict(from_attributes=True)

class AdminActionResponse(BaseModel):
    status: str
    message: str
    case_id: UUID
    case_status: str

class PaymentResponse(BaseModel):
    id: UUID
    external_id: str
    customer_id: UUID
    amount: float
    currency: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
