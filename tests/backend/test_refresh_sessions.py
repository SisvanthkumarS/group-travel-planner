"""Refresh session lifecycle, cookie authentication, and outage behavior."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.orm import Session

from backend.app.controllers.TripController import get_trip_service
from backend.app.core import filter as authentication
from backend.app.core import security
from backend.app.core.config import Settings, get_settings
from backend.app.core.database import get_session
from backend.app.core.refresh_sessions import get_refresh_store
from backend.app.main import app
from backend.app.models import User


def test_store_hashes_tokens_and_revokes_only_one_session(refresh_store):
    first = refresh_store.create(7)
    second = refresh_store.create(7)
    assert len(first.token) == 64 and first.token != second.token
    key = refresh_store.key(first.token)
    assert first.token not in key and first.token not in refresh_store.client.get(key)
    assert 0 < refresh_store.client.ttl(key) <= 7 * 86400
    assert refresh_store.renew(first.token).user_id == 7
    refresh_store.revoke(first.token)
    refresh_store.revoke(first.token)
    with pytest.raises(HTTPException) as error:
        refresh_store.renew(first.token)
    assert error.value.status_code == 401
    assert refresh_store.renew(second.token).user_id == 7


def test_renew_slides_idle_timeout_but_obeys_absolute_deadline(refresh_store):
    grant = refresh_store.create(7)
    key = refresh_store.key(grant.token)
    record = json.loads(refresh_store.client.get(key))
    record["absolute_exp"] = int(datetime.now(UTC).timestamp()) + 120
    refresh_store.client.set(key, json.dumps(record), ex=10)
    renewed = refresh_store.renew(grant.token)
    assert 110 <= renewed.max_age <= 120
    assert 110 <= refresh_store.client.ttl(key) <= 120
    record["absolute_exp"] = 1
    refresh_store.client.set(key, json.dumps(record), ex=120)
    with pytest.raises(HTTPException) as error:
        refresh_store.renew(grant.token)
    assert error.value.status_code == 401


def test_expired_redis_session_cannot_be_recreated(refresh_store):
    grant = refresh_store.create(7)
    refresh_store.client.delete(refresh_store.key(grant.token))
    with pytest.raises(HTTPException) as error:
        refresh_store.renew(grant.token)
    assert error.value.status_code == 401
    assert not refresh_store.client.exists(refresh_store.key(grant.token))


def test_parallel_refresh_keeps_all_requests_and_logout_consistent(refresh_store):
    grant = refresh_store.create(7)
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(
            executor.map(lambda _: refresh_store.renew(grant.token), range(4))
        )
    assert {result.token for result in results} == {grant.token}
    refresh_store.revoke(grant.token)
    assert not refresh_store.client.exists(refresh_store.key(grant.token))


@pytest.fixture
def auth_client(monkeypatch, refresh_store):
    settings = Settings(
        _env_file=None,
        jwt_secret="refresh-tests-secret-" * 4,
        poll_scheduler_enabled=False,
    )
    refresh_store.settings = settings
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    monkeypatch.setattr(authentication, "get_settings", lambda: settings)
    session = Mock(spec=Session)
    user = User(
        user_id=7,
        user_name="KC",
        email="kc@example.com",
        password_hash=security.hash_password("password"),
        created_at=datetime.now(UTC),
    )
    session.scalar.return_value = user
    session.get.return_value = user
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_refresh_store] = lambda: refresh_store
    trips = Mock()
    trips.list_trips.return_value = []
    app.dependency_overrides[get_trip_service] = lambda: trips
    try:
        with TestClient(
            app, raise_server_exceptions=False, headers={"X-CSRF-Protection": "1"}
        ) as client:
            yield client, refresh_store, session, settings, trips
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def login(client):
    response = client.post(
        "/api/v1/auth/login", json={"email": "kc@example.com", "password": "password"}
    )
    assert response.status_code == 200, response.text
    return response.cookies.get("access_token"), response.cookies.get("refresh_token")


def cookies(client, access, refresh):
    client.cookies.clear()
    if access:
        client.cookies.set("access_token", access, domain="testserver.local", path="/")
    if refresh:
        client.cookies.set(
            "refresh_token", refresh, domain="testserver.local", path="/"
        )


def expired_access(settings, **overrides):
    now = datetime.now(UTC)
    claims = {
        "sub": "7",
        "iat": now - timedelta(hours=1),
        "exp": now - timedelta(minutes=1),
        "token_type": "access",
    }
    return jwt.encode(
        claims | overrides, settings.jwt_secret, algorithm=settings.jwt_algorithm
    )


def test_login_issues_two_httponly_cookies_without_returning_credentials(auth_client):
    client, store, _, _, _ = auth_client
    access, refresh = login(client)
    assert security.parse_access_token(access)["token_type"] == "access"
    assert store.renew(refresh).user_id == 7
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 200
    assert set(response.json()) == {"user_id", "user_name", "email", "created_at"}
    for header in response.headers.get_list("set-cookie"):
        assert "HttpOnly" in header and "SameSite=lax" in header and "Path=/" in header
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "access_state", ["expired", "absent", "tampered", "nearly-expired"]
)
def test_filter_renews_without_frontend_retry(auth_client, access_state):
    client, _, _, settings, trips = auth_client
    _, refresh = login(client)
    access = expired_access(settings)
    if access_state == "absent":
        access = None
    elif access_state == "tampered":
        access = "invalid-jwt"
    elif access_state == "nearly-expired":
        access = expired_access(settings, exp=datetime.now(UTC) + timedelta(seconds=20))
    cookies(client, access, refresh)
    response = client.get("/api/v1/trips")
    assert response.status_code == 200, response.text
    assert (
        security.parse_access_token(response.cookies.get("access_token"))["sub"] == "7"
    )
    assert response.cookies.get("refresh_token") == refresh
    trips.list_trips.assert_called_once_with(7)


@pytest.mark.parametrize("status", [204, 403])
def test_automatic_renewal_survives_explicit_and_error_responses(auth_client, status):
    client, _, _, _, trips = auth_client
    _, refresh = login(client)
    cookies(client, None, refresh)
    if status == 403:
        trips.delete_trip.side_effect = HTTPException(
            status_code=403, detail="Organizer required."
        )
    response = client.delete("/api/v1/trips/12")
    assert response.status_code == status
    assert response.cookies.get("access_token")
    assert response.cookies.get("refresh_token") == refresh


def test_logout_revokes_refresh_and_clears_both_cookies(auth_client):
    client, store, _, _, _ = auth_client
    _, refresh = login(client)
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 204 and response.content == b""
    assert len(response.headers.get_list("set-cookie")) == 2
    assert all(
        "Max-Age=0" in header for header in response.headers.get_list("set-cookie")
    )
    assert not store.client.exists(store.key(refresh))
    cookies(client, None, refresh)
    assert client.post("/api/v1/auth/refresh").status_code == 401
    assert client.get("/api/v1/trips").status_code == 401


def test_missing_or_invalid_refresh_cannot_authenticate(auth_client):
    client, _, _, settings, _ = auth_client
    assert client.post("/api/v1/auth/refresh").status_code == 401
    for token in ("bad", "A" * 64):
        cookies(client, expired_access(settings), token)
        assert client.get("/api/v1/trips").status_code == 401


def test_deleted_user_cannot_refresh(auth_client):
    client, store, session, _, _ = auth_client
    _, refresh = login(client)
    session.get.return_value = None
    assert client.post("/api/v1/auth/refresh").status_code == 401
    assert not store.client.exists(store.key(refresh))


def test_redis_outage_preserves_valid_access_but_not_refresh(auth_client):
    client, store, _, settings, _ = auth_client
    _, refresh = login(client)
    broken = Mock()
    broken.set.side_effect = RedisConnectionError("not available")
    broken.pipeline.side_effect = RedisConnectionError("not available")
    broken.delete.side_effect = RedisConnectionError("not available")
    store.client = broken
    # Redis is not needed to validate a still-valid access JWT.
    assert client.get("/api/v1/trips").status_code == 200
    cookies(
        client,
        expired_access(settings, exp=datetime.now(UTC) + timedelta(seconds=20)),
        refresh,
    )
    assert client.get("/api/v1/trips").status_code == 200
    cookies(client, expired_access(settings), refresh)
    response = client.get("/api/v1/trips")
    assert response.status_code == 503 and response.headers["retry-after"] == "5"
    response = client.post(
        "/api/v1/auth/login", json={"email": "kc@example.com", "password": "password"}
    )
    assert response.status_code == 503 and "set-cookie" not in response.headers
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 503
    assert len(response.headers.get_list("set-cookie")) == 2
    assert client.cookies.get("access_token") is None
    assert client.cookies.get("refresh_token") is None


def test_wrong_token_type_cannot_be_used_as_access(auth_client):
    _, _, _, settings, _ = auth_client
    wrong = expired_access(
        settings, exp=datetime.now(UTC) + timedelta(minutes=1), token_type="refresh"
    )
    with pytest.raises(HTTPException) as error:
        security.parse_access_token(wrong)
    assert error.value.status_code == 401


def test_secure_and_custom_cookie_names(auth_client):
    from fastapi import Response

    from backend.app.core.auth_cookies import set_auth_cookies

    settings = Settings(
        _env_file=None,
        jwt_cookie_name="custom_access",
        jwt_refresh_cookie_name="custom_refresh",
        jwt_cookie_secure=True,
    )
    response = Response()
    set_auth_cookies(response, "access", "refresh", 10, settings)
    headers = response.headers.getlist("set-cookie")
    assert headers[0].startswith("custom_access=") and headers[1].startswith(
        "custom_refresh="
    )
    assert all("Secure" in header and "HttpOnly" in header for header in headers)


def test_refreshed_access_cannot_outlive_absolute_session_deadline(auth_client):
    client, store, _, _, _ = auth_client
    _, refresh = login(client)
    key = store.key(refresh)
    record = json.loads(store.client.get(key))
    deadline = int(datetime.now(UTC).timestamp()) + 120
    record["absolute_exp"] = deadline
    store.client.set(key, json.dumps(record), ex=120)
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 200
    payload = security.parse_access_token(response.cookies.get("access_token"))
    assert payload["exp"] <= deadline
    assert 0 < payload["exp"] - int(datetime.now(UTC).timestamp()) <= 120


def test_logout_between_read_and_expire_cannot_resurrect_session(
    refresh_store, monkeypatch
):
    grant = refresh_store.create(7)
    factory = refresh_store.client.pipeline
    revoked = False

    def pipeline(*args, **kwargs):
        instance = factory(*args, **kwargs)
        execute = instance.execute

        def execute_after_logout(*args, **kwargs):
            nonlocal revoked
            if not revoked:
                revoked = True
                refresh_store.revoke(grant.token)
            return execute(*args, **kwargs)

        instance.execute = execute_after_logout
        return instance

    monkeypatch.setattr(refresh_store.client, "pipeline", pipeline)
    with pytest.raises(HTTPException) as error:
        refresh_store.renew(grant.token)
    assert error.value.status_code == 401
    assert not refresh_store.client.exists(refresh_store.key(grant.token))
