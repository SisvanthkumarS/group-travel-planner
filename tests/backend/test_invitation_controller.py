from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.controllers.InvitationController import get_invitation_service
from backend.app.core import filter as authentication
from backend.app.core import security
from backend.app.core.config import Settings
from backend.app.core.database import get_session
from backend.app.main import app
from backend.app.models.user import User
from backend.app.schemas.invitation import InvitationResponse
from backend.app.services.InvitationService import InvitationService

ENDPOINTS = [
    ("POST", "/api/v1/trips/12/invitations", {"email": "friend@example.com"}),
    ("GET", "/api/v1/invitations", None),
    ("PATCH", "/api/v1/invitations", {"invitation_id": 9, "decision": "ACCEPT"}),
]


@pytest.fixture
def client(monkeypatch):
    settings = Settings(
        _env_file=None, jwt_secret="invitation-controller-test-key-" * 3
    )
    monkeypatch.setattr(authentication, "get_settings", lambda: settings)
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    session = Mock(spec=Session)
    session.get.return_value = User(user_id=7, user_name="KC")
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_session] = lambda: session
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


@pytest.fixture
def authenticated_client(client):
    client.cookies.set("access_token", security.create_access_token(7))
    return client


@pytest.mark.parametrize(("method", "path", "body"), ENDPOINTS)
def test_invitation_routes_require_authentication(client, method, path, body):
    assert client.request(method, path, json=body).status_code == 401


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/api/v1/trips/0/invitations", {"email": "friend@example.com"}),
        ("POST", "/api/v1/trips/12/invitations", {"email": "invalid"}),
        ("POST", "/api/v1/trips/12/invitations", {}),
        ("POST", "/api/v1/trips/12/invitations", {"email": None, "user_name": " "}),
        ("POST", "/api/v1/trips/12/invitations", {"email": " ", "user_name": ""}),
        ("POST", "/api/v1/trips/12/invitations", {"user_name": "x" * 31}),
        ("PATCH", "/api/v1/invitations", {"invitation_id": 0, "decision": "ACCEPT"}),
        ("PATCH", "/api/v1/invitations", {"invitation_id": 9, "decision": "ACCEPTED"}),
        ("PATCH", "/api/v1/invitations", {"invitation_id": 9}),
    ],
)
def test_invitation_input_validation(authenticated_client, method, path, body):
    assert authenticated_client.request(method, path, json=body).status_code == 422


@pytest.mark.parametrize(
    "payload, expected_email, expected_name",
    [
        ({"email": " friend@example.com "}, "friend@example.com", None),
        ({"email": "friend@example.com", "user_name": " "}, "friend@example.com", None),
        ({"user_name": " KC "}, None, "KC"),
        ({"email": None, "user_name": "KC"}, None, "KC"),
        ({"email": " ", "user_name": "KC"}, None, "KC"),
        ({"user_name": "x" * 30}, None, "x" * 30),
        (
            {"email": "friend@example.com", "user_name": "KC"},
            "friend@example.com",
            "KC",
        ),
    ],
)
def test_create_invitation_accepts_recipient_identifiers(
    authenticated_client, payload, expected_email, expected_name
):
    service = Mock(spec=InvitationService)
    service.create_invitation.return_value = InvitationResponse(
        invitation_id=9,
        trip_id=12,
        invited_user_id=8,
        invited_by_user_id=7,
        status="PENDING",
        created_at=datetime.now(UTC),
        responded_at=None,
    )
    app.dependency_overrides[get_invitation_service] = lambda: service
    response = authenticated_client.post("/api/v1/trips/12/invitations", json=payload)
    assert response.status_code == 201
    trip_id, request, actor = service.create_invitation.call_args.args
    assert (trip_id, actor) == (12, 7)
    assert (request.email, request.user_name) == (expected_email, expected_name)


@pytest.mark.parametrize(
    "decision, state", [("ACCEPT", "ACCEPTED"), ("DECLINE", "DECLINED")]
)
def test_controllers_delegate_authenticated_identity(
    authenticated_client, decision, state
):
    invitation = InvitationResponse(
        invitation_id=9,
        trip_id=12,
        invited_user_id=8,
        invited_by_user_id=7,
        status="PENDING",
        created_at=datetime.now(UTC),
        responded_at=None,
    )
    service = Mock(spec=InvitationService)
    service.create_invitation.return_value = invitation
    service.list_invitations.return_value = [invitation]
    service.respond_to_invitation.return_value = invitation.model_copy(
        update={"status": state, "responded_at": datetime.now(UTC)}
    )
    app.dependency_overrides[get_invitation_service] = lambda: service

    created = authenticated_client.post(
        "/api/v1/trips/12/invitations",
        json={"email": " friend@example.com ", "invited_by_user_id": 999},
    )
    assert created.status_code == 201
    trip_id, body, actor = service.create_invitation.call_args.args
    assert (trip_id, body.email, actor) == (12, "friend@example.com", 7)
    listed = authenticated_client.get("/api/v1/invitations?user_id=999")
    assert listed.status_code == 200 and listed.json() == [created.json()]
    service.list_invitations.assert_called_once_with(7)
    answered = authenticated_client.patch(
        "/api/v1/invitations", json={"invitation_id": 9, "decision": decision}
    )
    assert answered.status_code == 200 and answered.json()["status"] == state
    body, actor = service.respond_to_invitation.call_args.args
    assert (body.invitation_id, body.decision, actor) == (9, decision, 7)
