import uuid
import threading
from typing import Dict, Any

class GatewayTimeoutError(Exception):
    pass

class MockGatewayClient:
    _store: Dict[str, Any] = {}
    _simulate_behaviors: Dict[str, str] = {}
    _lock = threading.Lock()

    @classmethod
    def reset(cls):
        with cls._lock:
            cls._store.clear()
            cls._simulate_behaviors.clear()

    @classmethod
    def set_behavior(cls, idempotency_key: str, behavior: str):
        with cls._lock:
            cls._simulate_behaviors[idempotency_key] = behavior

    def charge(self, idempotency_key: str, amount: float, currency: str, source_id: str) -> Dict[str, Any]:
        with self._lock:
            if idempotency_key in self._store:
                return self._store[idempotency_key]

            behavior = self._simulate_behaviors.get(idempotency_key, "success")
            
            if behavior == "timeout_drop":
                raise GatewayTimeoutError("Gateway connection timed out and request was dropped")
            elif behavior == "timeout_success":
                # Simulated: We time out locally, but the remote side processed it as a success
                self._store[idempotency_key] = {"status": "succeeded", "transaction_id": str(uuid.uuid4())}
                raise GatewayTimeoutError("Gateway connection timed out but succeeded remotely")

            # Default behavior
            result = {"status": "succeeded" if behavior == "success" else "failed", "transaction_id": str(uuid.uuid4())}
            self._store[idempotency_key] = result
            return result

    def verify_payment_status(self, idempotency_key: str) -> Dict[str, Any]:
        with self._lock:
            if idempotency_key in self._store:
                return self._store[idempotency_key]
            
            return {"status": "not_found"}
