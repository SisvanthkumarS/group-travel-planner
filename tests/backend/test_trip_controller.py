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
    "timezone": "America/New_York",
}
ENDPOINTS = [
    ("POST", "/api/v1/trips", CREATE_BODY),
    ("GET", "/api/v1/trips", None),
    ("GET", "/api/v1/trips/12", None),
    ("DELETE", "/api/v1/trips/12", None),
    ("PATCH", "/api/v1/trips/12", {"name": "Updated trip"}),
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
        with TestClient(app, headers={"X-CSRF-Protection": "1"}) as client:
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


@pytest.mark.parametrize(
    "changes",
    [
        {"name": " "},
        {"destination": " "},
        {"end_date": "2026-10-31"},
        {"start_date": "invalid-date"},
        {"timezone": "Not/A_Timezone"},
        {"timezone": "../America/New_York"},
        {"timezone": " "},
    ],
)
def test_create_trip_validates_body(authenticated_client, changes):
    response = authenticated_client.post("/api/v1/trips", json=CREATE_BODY | changes)
    assert response.status_code == 422


def test_create_trip_requires_explicit_timezone(authenticated_client):
    body = {key: value for key, value in CREATE_BODY.items() if key != "timezone"}
    response = authenticated_client.post("/api/v1/trips", json=body)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "timezone"]


@pytest.mark.parametrize("method", ["GET", "DELETE", "PATCH"])
def test_trip_id_must_be_positive(authenticated_client, method):
    assert authenticated_client.request(method, "/api/v1/trips/0").status_code == 422


def test_controllers_delegate_identity_and_map_success_responses(authenticated_client):
    trip = TripResponse(
        trip_id=12,
        name="NYC Trip",
        destination="New York",
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 3),
        timezone="America/New_York",
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
    assert created.json()["timezone"] == "America/New_York"
    body, actor = service.create_trip.call_args.args
    assert body.name == "NYC Trip" and body.destination == "New York"
    assert body.timezone == "America/New_York"
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


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": " "},
        {"destination": " "},
        {"name": None},
        {"start_date": None},
        {"end_date": "2026-02-30"},
        {"organizer_id": 8},
        {"name": "Updated", "trip_id": 99},
        {"timezone": "Not/A_Timezone"},
        {"timezone": "../America/New_York"},
        {"timezone": " "},
        {"timezone": None},
    ],
)
def test_patch_trip_rejects_invalid_or_unsupported_fields(authenticated_client, body):
    service = Mock(spec=TripService)
    app.dependency_overrides[get_trip_service] = lambda: service
    response = authenticated_client.patch("/api/v1/trips/12", json=body)
    assert response.status_code == 422
    service.update_trip.assert_not_called()


def test_patch_controller_delegates_authenticated_identity(authenticated_client):
    service = Mock(spec=TripService)
    service.update_trip.return_value = TripResponse(
        trip_id=12,
        name="Updated",
        destination="New York",
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 3),
        timezone="America/New_York",
        organizer_id=7,
    )
    app.dependency_overrides[get_trip_service] = lambda: service
    response = authenticated_client.patch(
        "/api/v1/trips/12", json={"name": " Updated "}
    )
    assert response.status_code == 200
    trip_id, body, actor_id = service.update_trip.call_args.args
    assert (trip_id, actor_id) == (12, 7)
    assert body.model_dump(exclude_unset=True) == {"name": "Updated"}


@pytest.mark.parametrize("timezone", ["UTC", "Asia/Shanghai", " America/Los_Angeles "])
def test_patch_trip_accepts_a_valid_timezone(authenticated_client, timezone):
    service = Mock(spec=TripService)
    service.update_trip.return_value = TripResponse(
        trip_id=12,
        name="NYC",
        destination="New York",
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 3),
        timezone=timezone.strip(),
        organizer_id=7,
    )
    app.dependency_overrides[get_trip_service] = lambda: service
    response = authenticated_client.patch(
        "/api/v1/trips/12", json={"timezone": timezone}
    )
    assert response.status_code == 200
    trip_id, body, actor = service.update_trip.call_args.args
    assert (trip_id, actor) == (12, 7)
    assert body.model_dump(exclude_unset=True) == {"timezone": timezone.strip()}
    assert response.json()["timezone"] == timezone.strip()
