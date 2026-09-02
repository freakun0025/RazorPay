import pytest
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
        headers={"X-Admin-API-Key": "admin-secret-dev-key-123"}
    )
    assert response.status_code == 404
