from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
from app.config.settings import ADMIN_API_KEY

api_key_header = APIKeyHeader(name="X-Admin-API-Key", auto_error=False)

def get_admin_user(api_key: str = Security(api_key_header)):
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
        )
    if api_key != ADMIN_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid administrative credentials",
        )
    return "admin"
