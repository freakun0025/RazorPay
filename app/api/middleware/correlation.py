from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from app.utils.context import get_correlation_id, set_correlation_id, reset_correlation_id
import uuid
import re

class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        req_correlation_id = request.headers.get("X-Correlation-ID")
        
        # Validate and sanitize correlation ID
        if req_correlation_id:
            # Strip non-printable/control characters
            req_correlation_id = re.sub(r'[^\x20-\x7E]', '', req_correlation_id)
            # Truncate to 72 chars maximum
            req_correlation_id = req_correlation_id[:72].strip()
            
        if not req_correlation_id:
            req_correlation_id = str(uuid.uuid4())
            
        token = set_correlation_id(req_correlation_id)
        
        try:
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = req_correlation_id
            return response
        finally:
            reset_correlation_id(token)
