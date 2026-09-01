from pydantic import BaseModel, Field
from typing import Literal

class RecoveryDecisionContext(BaseModel):
    failure_reason: str
    attempt_count: int
    days_since_failure: int
    amount: float
    currency: str

class RecoveryDecision(BaseModel):
    action: Literal["CHARGE", "ABORT", "DELAY"]
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)
