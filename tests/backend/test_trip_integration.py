"""Verify committed trip creation and atomic rollback using real PostgreSQL."""

import os
from datetime import date
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import Session

from backend.app.core import filter as authentication
from backend.app.core import security
from backend.app.core.config import Settings
from backend.app.core.database import get_session
from backend.app.main import app
from backend.app.models import Invitation, Trip, TripMember, User
from backend.app.repositories.TripRepository import TripRepository

BODY = {
    "name": " NYC Trip ",
    "destination": " New York ",
    "start_date": "2026-11-01",
    "end_date": "2026-11-03",
    "organizer_id": 999,
}


@pytest.fixture
def database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(url)
    with Session(engine) as session:
        actor = User(
            user_name=uuid4().hex[:20],
            email=f"{uuid4().hex}@example.com",
            password_hash="unused: tests authenticate with a signed cookie",
        )
        session.add(actor)
        session.flush()
        user_id = actor.user_id
        session.commit()
    try:
        yield engine, user_id
    finally:
        # Delete only this fixture's account; cascades clean up its test trips.
        with engine.begin() as connection:
            connection.execute(delete(User).where(User.user_id == user_id))
        engine.dispose()


@pytest.fixture
def client(database, monkeypatch):
    engine, user_id = database
    settings = Settings(_env_file=None, jwt_secret="trip-integration-test-key-" * 3)
    monkeypatch.setattr(authentication, "get_settings", lambda: settings)
    monkeypatch.setattr(security, "get_settings", lambda: settings)

    def database_session():
        with Session(engine) as session:
            yield session

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_session] = database_session
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            client.cookies.set("access_token", security.create_access_token(user_id))
            yield client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def test_trip_and_organizer_are_committed_together(client, database):
    engine, user_id = database
    response = client.post("/api/v1/trips", json=BODY)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["organizer_id"] == user_id
    assert data["name"] == "NYC Trip"

    # A new connection must see both rows after the request Session has closed.
    with Session(engine) as session:
        trip = session.get(Trip, data["trip_id"])
        member = session.get(TripMember, (data["trip_id"], user_id))
        assert trip is not None and trip.organizer_id == user_id
        assert member is not None and member.role == "ORGANIZER"
        assert (
            session.scalar(
                select(func.count())
                .select_from(TripMember)
                .where(TripMember.trip_id == trip.trip_id)
            )
            == 1
        )


def test_failure_after_member_flush_rolls_back_everything(client, database):
    engine, user_id = database
    original = TripRepository.add_member

    def fail_after_insert(repository, member):
        original(repository, member)
        raise RuntimeError("Simulated failure after membership insertion")

    with patch.object(TripRepository, "add_member", fail_after_insert):
        response = client.post("/api/v1/trips", json=BODY)
    assert response.status_code == 500
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(Trip)
                .where(Trip.organizer_id == user_id)
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(TripMember)
                .where(TripMember.user_id == user_id)
            )
            == 0
        )
    assert client.post("/api/v1/trips", json=BODY).status_code == 201


@pytest.fixture
def trip_with_members(client, database):
    engine, organizer_id = database
    response = client.post("/api/v1/trips", json=BODY)
    assert response.status_code == 201
    trip = response.json()
    with Session(engine) as session:
        guest = User(
            user_name=uuid4().hex[:20],
            email=f"{uuid4()}@example.com",
            password_hash="unused",
        )
        outsider = User(
            user_name=uuid4().hex[:20],
            email=f"{uuid4()}@example.com",
            password_hash="unused",
        )
        session.add_all([guest, outsider])
        session.flush()
        guest_id, outsider_id = guest.user_id, outsider.user_id
        # The outsider belongs to a different trip. That must not grant access.
        other = Trip(
            name="Other trip",
            destination="Boston",
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 3),
            organizer_id=outsider_id,
        )
        session.add(other)
        session.flush()
        session.add_all(
            [
                TripMember(trip_id=trip["trip_id"], user_id=guest_id, role="MEMBER"),
                TripMember(
                    trip_id=other.trip_id, user_id=outsider_id, role="ORGANIZER"
                ),
            ]
        )
        session.commit()
    try:
        yield trip, organizer_id, guest_id, outsider_id
    finally:
        with engine.begin() as connection:
            connection.execute(
                delete(User).where(User.user_id.in_([guest_id, outsider_id]))
            )


@pytest.mark.parametrize("actor", ["organizer", "member"])
def test_trip_details_include_all_and_only_its_members(
    client, trip_with_members, actor
):
    trip, organizer_id, guest_id, _ = trip_with_members
    current_id = organizer_id if actor == "organizer" else guest_id
    client.cookies.set("access_token", security.create_access_token(current_id))
    response = client.get(f"/api/v1/trips/{trip['trip_id']}")
    assert response.status_code == 200, response.text
    data = response.json()
    assert {key: data[key] for key in trip} == trip
    assert {member["user_id"]: member["role"] for member in data["members"]} == {
        organizer_id: "ORGANIZER",
        guest_id: "MEMBER",
    }
    for member in data["members"]:
        assert set(member) == {"user_id", "user_name", "role", "joined_at"}
        assert member["user_name"] and member["joined_at"]


def test_membership_in_another_trip_does_not_grant_access(client, trip_with_members):
    trip, _, _, outsider_id = trip_with_members
    client.cookies.set("access_token", security.create_access_token(outsider_id))
    assert client.get(f"/api/v1/trips/{trip['trip_id']}").status_code == 403


def test_missing_trip_returns_404(client):
    assert client.get("/api/v1/trips/9223372036854775807").status_code == 404


def test_user_with_no_memberships_gets_empty_trip_list(client):
    response = client.get("/api/v1/trips")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("actor", ["organizer", "member"])
def test_list_includes_only_accessible_trips(client, trip_with_members, actor):
    trip, organizer_id, guest_id, _ = trip_with_members
    user_id = organizer_id if actor == "organizer" else guest_id
    client.cookies.set("access_token", security.create_access_token(user_id))
    response = client.get("/api/v1/trips")
    assert response.status_code == 200
    assert response.json() == [trip]


def test_trip_list_orders_by_start_date_then_id(client, database):
    payloads = [
        BODY | {"name": "Late", "start_date": "2026-12-01", "end_date": "2026-12-03"},
        BODY | {"name": "Early A"},
        BODY | {"name": "Early B"},
    ]
    trips = []
    for payload in payloads:
        response = client.post("/api/v1/trips", json=payload)
        assert response.status_code == 201
        trips.append(response.json())
    response = client.get("/api/v1/trips")
    assert response.status_code == 200
    assert [trip["trip_id"] for trip in response.json()] == [
        trips[1]["trip_id"],
        trips[2]["trip_id"],
        trips[0]["trip_id"],
    ]


def test_organizer_delete_cascades_without_affecting_another_trip(
    client, database, trip_with_members
):
    trip, organizer_id, guest_id, outsider_id = trip_with_members
    engine, _ = database
    with Session(engine) as session:
        other_trip = session.scalar(
            select(Trip).where(Trip.organizer_id == outsider_id)
        )
        other_trip_id = other_trip.trip_id
        target_invitation = Invitation(
            trip_id=trip["trip_id"],
            invited_user_id=outsider_id,
            invited_by_user_id=organizer_id,
        )
        other_invitation = Invitation(
            trip_id=other_trip_id,
            invited_user_id=guest_id,
            invited_by_user_id=outsider_id,
        )
        session.add_all([target_invitation, other_invitation])
        session.flush()
        target_id, other_id = (
            target_invitation.invitation_id,
            other_invitation.invitation_id,
        )
        session.commit()
    response = client.delete(f"/api/v1/trips/{trip['trip_id']}")
    assert response.status_code == 204 and response.content == b""
    with Session(engine) as session:
        assert session.get(Trip, trip["trip_id"]) is None
        assert (
            session.scalar(
                select(func.count())
                .select_from(TripMember)
                .where(TripMember.trip_id == trip["trip_id"])
            )
            == 0
        )
        assert session.get(Invitation, target_id) is None
        assert session.get(Trip, other_trip_id) is not None
        assert session.get(TripMember, (other_trip_id, outsider_id)) is not None
        assert session.get(Invitation, other_id) is not None
        assert all(
            session.get(User, user_id) is not None
            for user_id in [organizer_id, guest_id, outsider_id]
        )
    assert client.delete(f"/api/v1/trips/{trip['trip_id']}").status_code == 404


@pytest.mark.parametrize("actor", ["member", "outsider"])
def test_non_organizer_cannot_delete_trip(client, database, trip_with_members, actor):
    trip, _, guest_id, outsider_id = trip_with_members
    engine, _ = database
    user_id = guest_id if actor == "member" else outsider_id
    client.cookies.set("access_token", security.create_access_token(user_id))
    response = client.delete(f"/api/v1/trips/{trip['trip_id']}")
    assert response.status_code == 403
    assert response.json()["detail"] == "Only the Organizer can delete this trip."
    with Session(engine) as session:
        assert session.get(Trip, trip["trip_id"]) is not None


def test_delete_missing_trip_returns_404(client):
    assert client.delete("/api/v1/trips/9223372036854775807").status_code == 404


def test_failure_after_delete_restores_trip_members_and_invitations(
    client, database, trip_with_members
):
    trip, organizer_id, _, outsider_id = trip_with_members
    engine, _ = database
    with Session(engine) as session:
        invitation = Invitation(
            trip_id=trip["trip_id"],
            invited_user_id=outsider_id,
            invited_by_user_id=organizer_id,
        )
        session.add(invitation)
        session.flush()
        invitation_id = invitation.invitation_id
        session.commit()
    original = TripRepository.delete

    def fail_after_delete(repository, target):
        original(repository, target)
        raise RuntimeError("Simulated failure after DELETE and cascading deletes")

    with patch.object(TripRepository, "delete", fail_after_delete):
        response = client.delete(f"/api/v1/trips/{trip['trip_id']}")
    assert response.status_code == 500
    with Session(engine) as session:
        assert session.get(Trip, trip["trip_id"]) is not None
        assert (
            session.scalar(
                select(func.count())
                .select_from(TripMember)
                .where(TripMember.trip_id == trip["trip_id"])
            )
            == 2
        )
        assert session.get(Invitation, invitation_id) is not None
    assert client.delete(f"/api/v1/trips/{trip['trip_id']}").status_code == 204
