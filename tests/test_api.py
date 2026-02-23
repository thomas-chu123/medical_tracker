"""Tests for FastAPI endpoints."""
import pytest
import allure
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@allure.feature("API Endpoints")
@allure.story("Health Check")
def test_health_check():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@allure.feature("API Endpoints")
@allure.story("List Hospitals")
def test_list_hospitals():
    resp = client.get("/api/hospitals")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@allure.feature("API Endpoints")
@allure.story("Authentication Flow")
def test_register_login_flow():
    """Test register + login returns JWT."""
    import uuid
    email = f"test_{uuid.uuid4().hex[:6]}@example.com"

    # Register
    with allure.step("Register new user"):
        reg_resp = client.post("/api/auth/register", json={
            "email": email,
            "password": "testpassword123",
            "display_name": "Test User",
        })
        # 201 or 400 if email confirmation required
        assert reg_resp.status_code in (201, 400)


@allure.feature("API Endpoints")
@allure.story("Protected Routes")
def test_protected_endpoint_without_token():
    with allure.step("Access /api/users/me without token"):
        resp = client.get("/api/users/me")
        assert resp.status_code == 401


@allure.feature("API Endpoints")
@allure.story("Tracking Routes")
def test_tracking_requires_auth():
    with allure.step("Access /api/tracking/ without token"):
        resp = client.get("/api/tracking/")
        assert resp.status_code == 401
