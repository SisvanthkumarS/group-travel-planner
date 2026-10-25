from datetime import UTC, date, datetime
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.controllers.TripController import get_trip_service
from backend.app.core import filter as authentication
from backend.app.core import security
from backend.app.core.config import Settings
from backend.app.core.database import get_session
from backend.app.main import app
from backend.app.models.user import User
from backend.app.schemas.trip import (
    TripDetailResponse,
    TripMemberResponse,
    TripResponse,
)
from backend.app.services.TripService import TripService

CREATE_BODY = {
    "name": " NYC Trip ",
    "destination": " New York ",
    "start_date": "2026-11-01",
    "end_date": "2026-11-03",
}
ENDPOINTS = [
    ("POST", "/api/v1/trips", CREATE_BODY),
    ("GET", "/api/v1/trips", None),
    ("GET", "/api/v1/trips/12", None),
    ("DELETE", "/api/v1/trips/12", None),
]


@pytest.fixture
def client(monkeypatch):
    settings = Settings(_env_file=None, jwt_secret="trip-controller-test-secret-" * 3)
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
def test_trip_routes_require_authentication(client, method, path, body):
    response = client.request(method, path, json=body)
    assert response.status_code == 401


@pytest.mark.parametrize(("method", "path", "body"), ENDPOINTS)
def test_trip_scaffold_returns_501_after_authentication(
    authenticated_client, method, path, body
):
    response = authenticated_client.request(method, path, json=body)
    assert response.status_code == 501
    assert "not implemented" in response.json()["detail"]


@pytest.mark.parametrize(
    "changes",
    [
        {"name": " "},
        {"destination": " "},
        {"end_date": "2026-10-31"},
        {"start_date": "invalid-date"},
    ],
)
def test_create_trip_validates_body(authenticated_client, changes):
    response = authenticated_client.post("/api/v1/trips", json=CREATE_BODY | changes)
    assert response.status_code == 422


@pytest.mark.parametrize("method", ["GET", "DELETE"])
def test_trip_id_must_be_positive(authenticated_client, method):
    assert authenticated_client.request(method, "/api/v1/trips/0").status_code == 422


def test_controllers_delegate_identity_and_map_success_responses(authenticated_client):
    trip = TripResponse(
        trip_id=12,
        name="NYC Trip",
        destination="New York",
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 3),
        organizer_id=7,
    )
    detail = TripDetailResponse(
        **trip.model_dump(),
        members=[
            TripMemberResponse(
                user_id=7, user_name="KC", role="ORGANIZER", joined_at=datetime.now(UTC)
            )
        ],
    )
    service = Mock(spec=TripService)
    service.create_trip.return_value = trip
    service.list_trips.return_value = [trip]
    service.get_trip.return_value = detail
    service.delete_trip.return_value = None
    app.dependency_overrides[get_trip_service] = lambda: service

    created = authenticated_client.post(
        "/api/v1/trips", json=CREATE_BODY | {"organizer_id": 999}
    )
    assert created.status_code == 201
    assert created.json()["organizer_id"] == 7
    body, actor = service.create_trip.call_args.args
    assert body.name == "NYC Trip" and body.destination == "New York"
    assert actor == 7

    assert authenticated_client.get("/api/v1/trips").json() == [created.json()]
    service.list_trips.assert_called_once_with(7)
    details = authenticated_client.get("/api/v1/trips/12")
    assert details.status_code == 200
    assert details.json()["members"][0]["user_id"] == 7
    service.get_trip.assert_called_once_with(12, 7)
    deleted = authenticated_client.delete("/api/v1/trips/12")
    assert deleted.status_code == 204 and deleted.content == b""
    service.delete_trip.assert_called_once_with(12, 7)
