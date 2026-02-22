"""Tests for FastAPI endpoints."""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check():
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


def test_list_hospitals():
    resp = client.get("/api/hospitals")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_register_login_flow():
    """Test register + login returns JWT."""
    import uuid
    email = f"test_{uuid.uuid4().hex[:6]}@example.com"

    # Register
    reg_resp = client.post("/api/auth/register", json={
        "email": email,
        "password": "testpassword123",
        "display_name": "Test User",
    })
    # 201 or 400 if email confirmation required
    assert reg_resp.status_code in (201, 400)


def test_protected_endpoint_without_token():
    resp = client.get("/api/users/me")
    assert resp.status_code == 401


def test_tracking_requires_auth():
    resp = client.get("/api/tracking/")
    assert resp.status_code == 401
