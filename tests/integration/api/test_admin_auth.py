import pytest

import os
import importlib
from app.config import settings

def test_admin_api_key_valid_configuration():
    # If the app booted, this should be true
    assert settings.ADMIN_API_KEY is not None
    assert settings.ADMIN_API_KEY != 'default-insecure-admin-key'

def test_admin_api_key_missing_fails_closed(monkeypatch):
    monkeypatch.delenv('ADMIN_API_KEY', raising=False)
    with pytest.raises(Exception) as exc_info:
        importlib.reload(settings)
    assert 'ADMIN_API_KEY environment variable must be set securely' in str(exc_info.value)
    
    # Restore for other tests
    monkeypatch.setenv('ADMIN_API_KEY', 'test-admin-key')
    importlib.reload(settings)


from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_admin_unauthenticated():
    response = client.get("/admin/cases/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 401

def test_admin_invalid_auth():
    response = client.get(
        "/admin/cases/00000000-0000-0000-0000-000000000000",
        headers={"X-Admin-API-Key": "wrong-key"}
    )
    assert response.status_code == 403

def test_admin_authorized_not_found():
    response = client.get(
        "/admin/cases/00000000-0000-0000-0000-000000000000",
        headers={"X-Admin-API-Key": "test-admin-key"}
    )
    assert response.status_code == 404
