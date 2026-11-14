import smtplib
import ssl
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.app.core import filter as authentication
from backend.app.core import security
from backend.app.core.config import Settings, get_settings
from backend.app.core.database import get_session
from backend.app.main import app
from backend.app.models.user import User
from backend.app.services.EmailService import (
    EmailDeliveryError,
    EmailDisabledError,
    EmailService,
)

ENDPOINT = "/api/v1/notifications/test-email"


def email_settings(**changes):
    return Settings(
        _env_file=None,
        **(
            {
                "email_enabled": True,
                "email_test_enabled": True,
                "smtp_host": "smtp.example.com",
                "smtp_username": "test-user",
                "smtp_password": "test-password",
                "email_from_address": "notifications@example.com",
                "jwt_secret": "email-test-secret-" * 4,
                "poll_scheduler_enabled": False,
            }
            | changes
        ),
    )


@pytest.fixture
def smtp(monkeypatch):
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    connection.send_message.return_value = {}
    plain = Mock(return_value=connection)
    implicit_tls = Mock(return_value=connection)
    monkeypatch.setattr(smtplib, "SMTP", plain)
    monkeypatch.setattr(smtplib, "SMTP_SSL", implicit_tls)
    return connection, plain, implicit_tls


@pytest.mark.parametrize("encryption", ["starttls", "ssl", "none"])
def test_transport_encryption_and_message(smtp, encryption):
    connection, plain, implicit_tls = smtp
    credentials = (
        {"smtp_username": "", "smtp_password": ""} if encryption == "none" else {}
    )
    settings = email_settings(smtp_encryption=encryption, **credentials)
    message_id = EmailService(settings).send(
        recipient="traveler@example.com",
        subject="Test notification",
        body="Hello traveler!",
    )
    factory = implicit_tls if encryption == "ssl" else plain
    assert factory.call_args.kwargs["timeout"] == 10
    assert factory.call_args.kwargs["host"] == settings.smtp_host
    assert factory.call_args.kwargs["port"] == settings.smtp_port
    if encryption == "ssl":
        plain.assert_not_called()
        context = factory.call_args.kwargs["context"]
    elif encryption == "starttls":
        implicit_tls.assert_not_called()
        context = connection.starttls.call_args.kwargs["context"]
        assert [call[0] for call in connection.method_calls] == [
            "starttls",
            "login",
            "send_message",
        ]
    if encryption != "none":
        assert context.check_hostname
        assert context.verify_mode == ssl.CERT_REQUIRED
        connection.login.assert_called_once_with("test-user", "test-password")
    else:
        connection.login.assert_not_called()
    if encryption != "starttls":
        connection.starttls.assert_not_called()
    message = connection.send_message.call_args.args[0]
    assert message["To"] == "traveler@example.com"
    assert message["From"] == "Group Travel Planner <notifications@example.com>"
    assert message["Subject"] == "Test notification"
    assert message["Message-ID"] == message_id
    assert message["Date"]
    assert "Hello traveler!" in message.get_content()
    assert connection.send_message.call_args.kwargs == {
        "from_addr": "notifications@example.com",
        "to_addrs": ["traveler@example.com"],
    }


def test_disabled_email_never_connects(smtp):
    with pytest.raises(EmailDisabledError):
        EmailService(email_settings(email_enabled=False)).send(
            recipient="user@example.com", subject="Test", body="Test"
        )
    smtp[1].assert_not_called()
    smtp[2].assert_not_called()


@pytest.mark.parametrize(
    "changes",
    [
        {"smtp_host": " "},
        {"email_from_address": None},
        {"email_from_address": "invalid"},
        {"email_from_name": "App\r\nBcc: victim@example.com"},
        {"smtp_password": ""},
        {"smtp_username": ""},
        {"smtp_port": 0},
        {"email_timeout_seconds": 0},
        {"smtp_encryption": "invalid"},
        {"smtp_encryption": "none"},
        {
            "smtp_encryption": "none",
            "smtp_username": "",
            "smtp_password": "",
            "app_env": "production",
        },
    ],
)
def test_invalid_email_configuration(changes):
    with pytest.raises(ValidationError):
        email_settings(**changes)


def test_tls_failure_never_sends_credentials_or_message(smtp):
    smtp[0].starttls.side_effect = smtplib.SMTPNotSupportedError("No STARTTLS")
    with pytest.raises(EmailDeliveryError):
        EmailService(email_settings()).send(
            recipient="user@example.com", subject="Test", body="Test"
        )
    smtp[0].login.assert_not_called()
    smtp[0].send_message.assert_not_called()


@pytest.fixture
def api(monkeypatch, smtp):
    settings = email_settings()
    monkeypatch.setattr(authentication, "get_settings", lambda: settings)
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    session = Mock(spec=Session)
    session.get.return_value = User(
        user_id=7, user_name="Traveler", email="traveler@example.com"
    )
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_session] = lambda: session
    # No lifespan: these tests need neither the scheduler nor a real database.
    client = TestClient(app, headers={"X-CSRF-Protection": "1"})
    try:
        yield client, settings, session
    finally:
        client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def sign_in(client):
    client.cookies.set("access_token", security.create_access_token(7))


def test_test_event_uses_authenticated_recipient(api, smtp):
    client, _, session = api
    sign_in(client)
    response = client.post(ENDPOINT, json={"email": "someone-else@example.com"})
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    session.get.assert_called_once_with(User, 7)
    message = smtp[0].send_message.call_args.args[0]
    assert message["To"] == "traveler@example.com"
    assert "test notification" in message["Subject"]
    assert "Hi Traveler" in message.get_content()
    assert response.json()["message_id"] == message["Message-ID"]


@pytest.mark.parametrize(
    "case,expected", [("anonymous", 401), ("csrf", 403), ("missing-user", 401)]
)
def test_test_event_security(api, smtp, case, expected):
    client, _, session = api
    if case != "anonymous":
        sign_in(client)
    if case == "missing-user":
        session.get.return_value = None
    if case == "csrf":
        client.headers.pop("X-CSRF-Protection")
    assert client.post(ENDPOINT).status_code == expected
    smtp[1].assert_not_called()


@pytest.mark.parametrize(
    "setting,expected", [("email_test_enabled", 404), ("email_enabled", 503)]
)
def test_disabled_event_or_transport(api, smtp, setting, expected):
    client, settings, _ = api
    sign_in(client)
    setattr(settings, setting, False)
    assert client.post(ENDPOINT).status_code == expected
    smtp[1].assert_not_called()


@pytest.mark.parametrize(
    "failure",
    [
        TimeoutError("secret-provider-details"),
        smtplib.SMTPAuthenticationError(535, b"secret-provider-details"),
        smtplib.SMTPRecipientsRefused(
            {"traveler@example.com": (550, b"secret-provider-details")}
        ),
    ],
)
def test_delivery_failure_is_reported_without_sensitive_details(
    api, smtp, caplog, failure
):
    client, _, _ = api
    sign_in(client)
    smtp[0].send_message.side_effect = failure
    response = client.post(ENDPOINT)
    assert response.status_code == 502
    assert response.json() == {
        "detail": "Email could not be submitted to the mail provider."
    }
    assert "secret-provider-details" not in caplog.text
    assert "traveler@example.com" not in caplog.text


def test_refused_recipient_result_is_not_reported_as_success(api, smtp):
    client, _, _ = api
    sign_in(client)
    smtp[0].send_message.return_value = {"traveler@example.com": (550, b"Rejected")}
    assert client.post(ENDPOINT).status_code == 502
