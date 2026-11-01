"""Exercise real registration, login and cookies against a migrated PostgreSQL DB."""

import os
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.core import security
from backend.app.core.config import Settings, get_settings
from backend.app.core.database import get_session
from backend.app.main import app
from backend.app.repositories.AuthRepository import AuthRepository


@pytest.fixture
def client(monkeypatch):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    settings = Settings(_env_file=None, jwt_secret="integration-test-only-secret-" * 3)
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    engine = create_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()

        def isolated_session():
            # Service commits only release savepoints; the outer transaction
            # rolls back every account created during the test.
            with Session(
                bind=connection, join_transaction_mode="create_savepoint"
            ) as session:
                yield session

        previous = app.dependency_overrides.copy()
        app.dependency_overrides[get_session] = isolated_session
        app.dependency_overrides[get_settings] = lambda: settings
        try:
            with TestClient(app) as client:
                yield client
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)
            transaction.rollback()
    engine.dispose()


def register(client, name=None):
    payload = {
        "user_name": name or uuid4().hex[:10],
        "email": f"{uuid4().hex}@example.com",
        "password": "test-password-2026",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    return payload, response.json()


@pytest.mark.parametrize("identifier", ["email", "user_name"])
@pytest.mark.parametrize("empty", [None, "", "   "])
def test_login_by_one_identifier_and_logout(client, identifier, empty):
    account, user = register(client)
    other = "user_name" if identifier == "email" else "email"
    response = client.post(
        "/api/v1/auth/login",
        json={
            identifier: account[identifier],
            other: empty,
            "password": account["password"],
        },
    )
    assert response.status_code == 200
    assert response.json() == user
    assert "password_hash" not in response.json()
    assert "access_token" not in response.json()
    token = response.cookies.get("access_token")
    assert security.parse_access_token(token)["sub"] == str(user["user_id"])
    assert "HttpOnly" in response.headers["set-cookie"]
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.cookies.get("access_token") is None


def test_duplicate_username_is_rejected(client):
    account, _ = register(client)
    response = client.post(
        "/api/v1/auth/register",
        json={**account, "email": f"{uuid4().hex}@example.com"},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Username is already registered."
    assert "set-cookie" not in response.headers


def test_username_index_conflict_returns_409_after_precheck(client):
    account, _ = register(client)
    # Reproduce the insert conflict that can occur after concurrent prechecks.
    with patch.object(AuthRepository, "find_by_user_name", return_value=None):
        response = client.post(
            "/api/v1/auth/register",
            json={**account, "email": f"{uuid4().hex}@example.com"},
        )
    assert response.status_code == 409
    assert response.json()["detail"] == "Username is already registered."
    register(client)


@pytest.mark.parametrize("length, expected", [(11, 201), (30, 201), (31, 422)])
def test_registration_username_length(client, length, expected):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "user_name": "x" * length,
            "email": f"{uuid4().hex}@example.com",
            "password": "test-password-2026",
        },
    )
    assert response.status_code == expected
    if expected == 201:
        login = client.post(
            "/api/v1/auth/login",
            json={"user_name": "x" * length, "password": "test-password-2026"},
        )
        assert login.status_code == 200
        assert login.json()["user_id"] == response.json()["user_id"]


def test_both_identifiers_use_email(client):
    account, user = register(client)
    other, _ = register(client)
    response = client.post(
        "/api/v1/auth/login",
        json={**account, "user_name": other["user_name"]},
    )
    assert response.status_code == 200
    assert response.json()["user_id"] == user["user_id"]


@pytest.mark.parametrize(
    "case", ["wrong-password", "unknown-email", "unknown-username"]
)
def test_invalid_credentials_return_401_without_cookie(client, case):
    account, _ = register(client)
    payload = {"email": account["email"], "password": account["password"]}
    if case == "wrong-password":
        payload["password"] = "wrong-password"
    elif case == "unknown-email":
        payload["email"] = f"{uuid4().hex}@example.com"
    else:
        payload = {"user_name": uuid4().hex[:10], "password": account["password"]}
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 401
    assert "set-cookie" not in response.headers
