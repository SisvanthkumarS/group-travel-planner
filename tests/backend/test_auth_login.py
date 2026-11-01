from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import jwt
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.app.core import security
from backend.app.core.config import Settings
from backend.app.models.user import User
from backend.app.repositories.AuthRepository import AuthRepository
from backend.app.schemas.auth import LoginRequest
from backend.app.services.AuthService import AuthService


@pytest.fixture
def jwt_settings(monkeypatch):
    settings = Settings(_env_file=None, jwt_secret="test-only-secret-" * 4)
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    return settings


@pytest.fixture(scope="module")
def user():
    return User(
        user_id=123,
        user_name="KC",
        email="kc@example.com",
        password_hash=security.hash_password("correct-password"),
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def service():
    service = AuthService(Mock(spec=Session))
    service.repository = Mock(spec=AuthRepository)
    return service


@pytest.mark.parametrize("missing", [None, "", "   "])
def test_email_login_accepts_empty_username(service, user, jwt_settings, missing):
    service.repository.find_by_email.return_value = user
    result = service.login(
        LoginRequest(
            user_name=missing, email="kc@example.com", password="correct-password"
        )
    )
    service.repository.find_by_email.assert_called_once_with("kc@example.com")
    service.repository.find_by_user_name.assert_not_called()
    assert security.parse_access_token(result.access_token)["sub"] == "123"
    assert result.user.user_id == 123


@pytest.mark.parametrize("missing", [None, "", "   "])
def test_username_login_accepts_empty_email(service, user, jwt_settings, missing):
    service.repository.find_by_user_name.return_value = user
    result = service.login(
        LoginRequest(user_name=" KC ", email=missing, password="correct-password")
    )
    service.repository.find_by_user_name.assert_called_once_with("KC")
    service.repository.find_by_email.assert_not_called()
    assert result.user.email == "kc@example.com"


def test_email_takes_precedence_without_username_fallback(service, user, jwt_settings):
    service.repository.find_by_email.return_value = None
    service.repository.find_by_user_name.return_value = user
    with pytest.raises(HTTPException) as error:
        service.login(
            LoginRequest(user_name="KC", email="wrong@example.com", password="correct")
        )
    assert error.value.status_code == 401
    service.repository.find_by_user_name.assert_not_called()


def test_wrong_password_returns_401(service, user, jwt_settings):
    service.repository.find_by_email.return_value = user
    with pytest.raises(HTTPException) as error:
        service.login(LoginRequest(email="kc@example.com", password="wrong-password"))
    assert error.value.status_code == 401


def test_unknown_username_does_not_verify_password(service, jwt_settings):
    service.repository.find_by_user_name.return_value = None
    with (
        patch("backend.app.services.AuthService.verify_password") as verify,
        pytest.raises(HTTPException) as error,
    ):
        service.login(LoginRequest(user_name="missing", password="password"))
    assert error.value.status_code == 401
    verify.assert_not_called()


def test_username_login_checks_password(service, user, jwt_settings):
    service.repository.find_by_user_name.return_value = user
    with pytest.raises(HTTPException) as error:
        service.login(LoginRequest(user_name="KC", password="wrong-password"))
    assert error.value.status_code == 401


@pytest.mark.parametrize(
    "payload",
    [
        {"password": "example"},
        {"email": " ", "user_name": None, "password": "example"},
        {"email": "invalid-email", "password": "example"},
        {"email": "kc@example.com"},
        {"email": "kc@example.com", "password": None},
        {"email": "kc@example.com", "password": ""},
        {"user_name": "x" * 31, "password": "example"},
    ],
)
def test_invalid_login_input(payload):
    with pytest.raises(ValidationError):
        LoginRequest.model_validate(payload)


def test_token_expiry_matches_configuration(jwt_settings):
    payload = security.parse_access_token(security.create_access_token(123))
    assert (
        payload["exp"] - payload["iat"]
        == jwt_settings.jwt_access_token_expire_minutes * 60
    )


@pytest.mark.parametrize(
    "case",
    [
        "expired",
        "bad-signature",
        "wrong-algorithm",
        "missing-exp",
        "missing-iat",
        "bad-sub",
        "zero-sub",
    ],
)
def test_invalid_tokens_return_401(jwt_settings, case):
    now = datetime.now(UTC)
    claims = {"sub": "123", "iat": now, "exp": now + timedelta(minutes=30)}
    key, algorithm = jwt_settings.jwt_secret, "HS256"
    if case == "expired":
        claims["exp"] = now - timedelta(minutes=1)
    elif case == "bad-signature":
        key = "different-test-only-secret-" * 4
    elif case == "wrong-algorithm":
        algorithm = "HS384"
    elif case == "missing-exp":
        del claims["exp"]
    elif case == "missing-iat":
        del claims["iat"]
    elif case == "bad-sub":
        claims["sub"] = "not-a-user-id"
    elif case == "zero-sub":
        claims["sub"] = "0"
    with pytest.raises(HTTPException) as error:
        security.parse_access_token(jwt.encode(claims, key, algorithm=algorithm))
    assert error.value.status_code == 401


def test_malformed_token_returns_401(jwt_settings):
    with pytest.raises(HTTPException) as error:
        security.parse_access_token("not-a-jwt")
    assert error.value.status_code == 401
