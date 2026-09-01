import os

class ImproperlyConfigured(Exception):
    pass

def validate_timeouts(gateway_timeout, lease_timeout):
    if gateway_timeout >= lease_timeout:
        raise ImproperlyConfigured(
            f"Gateway timeout ({gateway_timeout}s) must be strictly less than worker lease ({lease_timeout}s)"
        )

GATEWAY_HTTP_TIMEOUT = int(os.environ.get("GATEWAY_HTTP_TIMEOUT", 30))
WORKER_LEASE_TIMEOUT = int(os.environ.get("WORKER_LEASE_TIMEOUT", 60))

validate_timeouts(GATEWAY_HTTP_TIMEOUT, WORKER_LEASE_TIMEOUT)
