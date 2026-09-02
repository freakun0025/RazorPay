import os

class ImproperlyConfigured(Exception):
    pass

def validate_timeouts(gateway_timeout, lease_timeout, ai_timeout):
    if gateway_timeout >= lease_timeout:
        raise ImproperlyConfigured(
            f"Gateway timeout ({gateway_timeout}s) must be strictly less than worker lease ({lease_timeout}s)"
        )
    if ai_timeout >= lease_timeout:
        raise ImproperlyConfigured(
            f"AI timeout ({ai_timeout}s) must be strictly less than worker lease ({lease_timeout}s)"
        )

GATEWAY_HTTP_TIMEOUT = float(os.environ.get("GATEWAY_HTTP_TIMEOUT", 30))
WORKER_LEASE_TIMEOUT = float(os.environ.get("WORKER_LEASE_TIMEOUT", 60))
AI_TIMEOUT = float(os.environ.get("AI_TIMEOUT", 10))

validate_timeouts(GATEWAY_HTTP_TIMEOUT, WORKER_LEASE_TIMEOUT, AI_TIMEOUT)

AI_PROVIDER = os.environ.get("AI_PROVIDER", "openrouter")
AI_BASE_URL = os.environ.get("AI_BASE_URL", "https://openrouter.ai/api/v1")
AI_MODEL = os.environ.get("AI_MODEL", "nvidia/nemotron-3.5-lightning:free")
AI_API_KEY = os.environ.get("AI_API_KEY", "dummy-key")


ADMIN_API_KEY = os.environ.get('ADMIN_API_KEY', 'default-insecure-admin-key')
