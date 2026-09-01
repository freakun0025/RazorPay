from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import Dict

from app.api.schemas.webhooks import WebhookEvent
from app.domain.payments.service import WebhookService
from app.domain.payments.exceptions import ImmutableAttributeError, InvalidFinancialPayload
from app.persistence.database import get_db

router = APIRouter()

@router.post("/webhooks/payment")
async def receive_payment_webhook(event: WebhookEvent, db: Session = Depends(get_db)):
    # Note: Webhook signature verification is strictly required for production security,
    # but is deferred for this MVP phase as explicitly documented.
    
    if event.type not in ["payment.failed", "payment.succeeded"]:
        return {"status": "ignored", "reason": "unsupported_event_type"}
        
    service = WebhookService(db)
    
    try:
        service.process_webhook(event)
        return {"status": "success"}
    except (ImmutableAttributeError, InvalidFinancialPayload) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # 500 will be caught by FastAPI's default exception handler
        raise
