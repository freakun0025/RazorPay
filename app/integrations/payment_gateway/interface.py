from abc import ABC, abstractmethod

class PaymentGateway(ABC):
    @abstractmethod
    async def retry_payment(self, payment_id: str, idempotency_key: str) -> dict:
        pass
        
    @abstractmethod
    async def verify_payment_status(self, attempt_id: str) -> dict:
        pass
