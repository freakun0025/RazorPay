from fastapi import APIRouter

router = APIRouter()

@router.post("/webhooks/payment")
async def payment_webhook():
    # TODO: Implement idempotency and event storage
    raise NotImplementedError
