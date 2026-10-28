from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app.controllers.AuthController import get_auth_service
from backend.app.core.config import Settings, get_settings
from backend.app.main import app
from backend.app.schemas.auth import UserResponse
from backend.app.services.AuthService import LoginResult


@pytest.fixture
def client():
    settings = Settings(
        _env_file=None, jwt_cookie_name="test_session", jwt_cookie_secure=True
    )
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as client:
        try:
            yield client
        finally:
            app.dependency_overrides.pop(get_settings, None)
            app.dependency_overrides.pop(get_auth_service, None)


def test_failed_login_does_not_set_cookie(client):
    class RejectingAuthService:
        def login(self, request):
            raise HTTPException(status_code=401, detail="Invalid login credentials.")

    app.dependency_overrides[get_auth_service] = RejectingAuthService
    response = client.post(
        "/api/v1/auth/login", json={"email": "user@example.com", "password": "example"}
    )
    assert response.status_code == 401
    assert "set-cookie" not in response.headers


@pytest.mark.parametrize("action", ["register", "login"])
def test_auth_requires_a_nonempty_password(client, action):
    response = client.post(
        f"/api/v1/auth/{action}",
        json={"user_name": "KC", "email": "user@example.com", "password": ""},
    )
    assert response.status_code == 422


def test_controller_delegates_and_sets_cookie_only_after_success(client):
    user = UserResponse(
        user_id=1,
        user_name="KC",
        email="user@example.com",
        created_at=datetime.now(UTC),
    )

    class FakeAuthService:
        def register(self, request):
            assert request.user_name == user.user_name
            assert request.email == user.email
            assert request.password.get_secret_value() == "example"
            return user

        def login(self, request):
            assert request.email == user.email
            return LoginResult(user=user, access_token="test-token")

    app.dependency_overrides[get_auth_service] = FakeAuthService
    payload = {"user_name": "KC", "email": " user@example.com ", "password": "example"}
    registered = client.post("/api/v1/auth/register", json=payload)
    assert registered.status_code == 201
    assert set(registered.json()) == {"user_id", "user_name", "email", "created_at"}
    logged_in = client.post("/api/v1/auth/login", json=payload)
    assert logged_in.status_code == 200
    assert logged_in.json() == registered.json()
    cookie = logged_in.headers["set-cookie"]
    for attribute in [
        "test_session=test-token",
        "HttpOnly",
        "Secure",
        "SameSite=lax",
        "Path=/",
    ]:
        assert attribute in cookie


def test_logout_expires_the_same_cookie_and_is_idempotent(client):
    for _ in range(2):
        response = client.post("/api/v1/auth/logout")
        assert response.status_code == 204
        assert response.content == b""
        cookie = response.headers["set-cookie"]
        for attribute in ["test_session=", "Max-Age=0", "Path=/", "Secure", "HttpOnly"]:
            assert attribute in cookie
