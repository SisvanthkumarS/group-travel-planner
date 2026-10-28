"""Invitation creation and inbox queries with actual PostgreSQL persistence."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import Session

from backend.app.core import filter as authentication
from backend.app.core import security
from backend.app.core.config import Settings
from backend.app.core.database import get_session
from backend.app.main import app
from backend.app.models import Invitation, Trip, TripMember, User
from backend.app.repositories.InvitationRepository import InvitationRepository
from backend.app.schemas.invitation import (
    CreateInvitationRequest,
    RespondInvitationRequest,
)
from backend.app.services.InvitationService import InvitationService


@pytest.fixture
def database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(url)
    with Session(engine) as session:
        users = [
            User(
                user_name="u" + uuid4().hex[:19],
                email=f"{uuid4()}@example.com",
                password_hash="unused",
            )
            for _ in range(3)
        ]
        session.add_all(users)
        session.flush()
        organizer, recipient, other = users
        data = {
            "organizer": organizer.user_id,
            "recipient": recipient.user_id,
            "other": other.user_id,
            "email": recipient.email,
            "user_name": recipient.user_name,
            "organizer_email": organizer.email,
        }
        trip = Trip(
            name="Invitation test",
            destination="NYC",
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 3),
            organizer_id=organizer.user_id,
        )
        session.add(trip)
        session.flush()
        data["trip_id"] = trip.trip_id
        session.add(
            TripMember(
                trip_id=trip.trip_id, user_id=organizer.user_id, role="ORGANIZER"
            )
        )
        session.commit()
    try:
        yield engine, data
    finally:
        with engine.begin() as connection:
            connection.execute(
                delete(User).where(
                    User.user_id.in_(
                        [data["organizer"], data["recipient"], data["other"]]
                    )
                )
            )
        engine.dispose()


@pytest.fixture
def client(database, monkeypatch):
    engine, data = database
    settings = Settings(
        _env_file=None, jwt_secret="invitation-integration-test-key-" * 3
    )
    monkeypatch.setattr(authentication, "get_settings", lambda: settings)
    monkeypatch.setattr(security, "get_settings", lambda: settings)

    def session_dependency():
        with Session(engine) as session:
            yield session

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_session] = session_dependency
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            client.cookies.set(
                "access_token", security.create_access_token(data["organizer"])
            )
            yield client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def post_invitation(client, data, payload=None):
    return client.post(
        f"/api/v1/trips/{data['trip_id']}/invitations",
        json=payload or {"email": data["email"]},
    )


def test_list_invitations_empty_inbox(client):
    response = client.get("/api/v1/invitations")
    assert response.status_code == 200
    assert response.json() == []


def test_list_invitations_includes_history_and_isolates_recipient(client, database):
    engine, data = database
    now = datetime.now(UTC)
    with Session(engine) as session:
        invitations = [
            Invitation(
                trip_id=data["trip_id"],
                invited_user_id=data["recipient"],
                invited_by_user_id=data["organizer"],
                status=state,
                created_at=now if state != "ACCEPTED" else now - timedelta(days=1),
                responded_at=None if state == "PENDING" else now,
            )
            for state in ("ACCEPTED", "DECLINED", "PENDING")
        ]
        session.add_all(invitations)
        session.flush()
        expected_ids = [
            invitation.invitation_id for invitation in reversed(invitations)
        ]
        session.add(
            Invitation(
                trip_id=data["trip_id"],
                invited_user_id=data["other"],
                invited_by_user_id=data["recipient"],
                status="PENDING",
            )
        )
        session.commit()

    client.cookies.set("access_token", security.create_access_token(data["recipient"]))
    response = client.get(f"/api/v1/invitations?user_id={data['other']}")
    assert response.status_code == 200, response.text
    results = response.json()
    assert [item["invitation_id"] for item in results] == expected_ids
    assert [item["status"] for item in results] == ["PENDING", "DECLINED", "ACCEPTED"]
    assert all(item["invited_user_id"] == data["recipient"] for item in results)
    assert results[0]["responded_at"] is None
    assert all(item["responded_at"] is not None for item in results[1:])

    # The organizer sent invitations but has not received any.
    client.cookies.set("access_token", security.create_access_token(data["organizer"]))
    assert client.get("/api/v1/invitations").json() == []


@pytest.mark.parametrize("identifier", ["email", "user_name", "blank-email", "both"])
def test_invitation_is_committed_for_resolved_recipient(client, database, identifier):
    engine, data = database
    payload = (
        {"email": data["email"]}
        if identifier == "email"
        else {"user_name": data["user_name"]}
    )
    if identifier == "blank-email":
        payload["email"] = " "
    elif identifier == "both":
        payload = {"email": data["email"], "user_name": "nonexistent"}
    payload["invited_by_user_id"] = data["other"]
    response = post_invitation(client, data, payload)
    assert response.status_code == 201, response.text
    result = response.json()
    assert (result["invited_user_id"], result["invited_by_user_id"]) == (
        data["recipient"],
        data["organizer"],
    )
    assert (
        result["status"] == "PENDING"
        and result["responded_at"] is None
        and result["created_at"]
    )
    with Session(engine) as session:
        saved = session.get(Invitation, result["invitation_id"])
        assert saved is not None and saved.trip_id == data["trip_id"]
        assert session.get(TripMember, (data["trip_id"], data["recipient"])) is None


@pytest.mark.parametrize(
    "case,expected",
    [
        ("missing-trip", 404),
        ("non-organizer", 403),
        ("unknown-email", 404),
        ("unknown-name", 404),
        ("email-no-fallback", 404),
        ("self", 409),
        ("member", 409),
    ],
)
def test_rejected_invites_leave_no_records(client, database, case, expected):
    engine, data = database
    payload = {"email": data["email"]}
    if case == "missing-trip":
        data = data | {"trip_id": 9223372036854775807}
    elif case == "non-organizer":
        client.cookies.set("access_token", security.create_access_token(data["other"]))
    elif case == "unknown-email":
        payload = {"email": "missing@example.com"}
    elif case == "unknown-name":
        payload = {"user_name": data["user_name"].upper()}
    elif case == "email-no-fallback":
        payload = {"email": "missing@example.com", "user_name": data["user_name"]}
    elif case == "self":
        payload = {"email": data["organizer_email"]}
    else:
        with Session(engine) as session:
            session.add(
                TripMember(
                    trip_id=data["trip_id"], user_id=data["recipient"], role="MEMBER"
                )
            )
            session.commit()
    response = post_invitation(client, data, payload)
    assert response.status_code == expected, response.text
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(Invitation)
                .where(Invitation.trip_id == data["trip_id"])
            )
            == 0
        )


def test_duplicate_pending_invitation_uses_database_safeguard(client, database):
    engine, data = database
    assert post_invitation(client, data).status_code == 201
    assert post_invitation(client, data).status_code == 409
    with patch.object(InvitationRepository, "find_pending", return_value=None):
        assert post_invitation(client, data).status_code == 409
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(Invitation)
                .where(Invitation.trip_id == data["trip_id"])
            )
            == 1
        )


def test_declined_invitation_does_not_block_new_invite(client, database):
    engine, data = database
    with Session(engine) as session:
        session.add(
            Invitation(
                trip_id=data["trip_id"],
                invited_user_id=data["recipient"],
                invited_by_user_id=data["organizer"],
                status="DECLINED",
                responded_at=datetime.now(UTC),
            )
        )
        session.commit()
    assert post_invitation(client, data).status_code == 201


def test_failed_insert_is_rolled_back(client, database):
    engine, data = database
    original = InvitationRepository.add

    def fail_after_flush(repository, invitation):
        original(repository, invitation)
        raise RuntimeError("Simulated error after invitation INSERT")

    with patch.object(InvitationRepository, "add", fail_after_flush):
        assert post_invitation(client, data).status_code == 500
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(Invitation)
                .where(Invitation.trip_id == data["trip_id"])
            )
            == 0
        )
    assert post_invitation(client, data).status_code == 201


def test_concurrent_duplicate_invites_create_one_record(database):
    engine, data = database
    barrier = Barrier(2)

    def create():
        with Session(engine) as session:
            session.get(User, data["organizer"])
            barrier.wait(timeout=10)
            try:
                InvitationService(session).create_invitation(
                    data["trip_id"],
                    CreateInvitationRequest(email=data["email"]),
                    data["organizer"],
                )
                return 201
            except HTTPException as error:
                return error.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(create) for _ in range(2)]
        results = [future.result(timeout=20) for future in futures]
    assert sorted(results) == [201, 409]
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(Invitation)
                .where(Invitation.trip_id == data["trip_id"])
            )
            == 1
        )


@pytest.fixture
def fill_trip(database):
    engine, data = database
    extra_user_ids = []

    def fill(count):
        with Session(engine) as session:
            for _ in range(count):
                user = User(
                    user_name="u" + uuid4().hex[:19],
                    email=f"{uuid4()}@example.com",
                    password_hash="unused",
                )
                session.add(user)
                session.flush()
                extra_user_ids.append(user.user_id)
                session.add(
                    TripMember(
                        trip_id=data["trip_id"], user_id=user.user_id, role="MEMBER"
                    )
                )
            session.commit()

    yield fill
    with engine.begin() as connection:
        connection.execute(delete(User).where(User.user_id.in_(extra_user_ids)))


def pending_invitation(client, data):
    response = post_invitation(client, data)
    assert response.status_code == 201, response.text
    client.cookies.set("access_token", security.create_access_token(data["recipient"]))
    return response.json()["invitation_id"]


@pytest.mark.parametrize(
    "decision,state", [("ACCEPT", "ACCEPTED"), ("DECLINE", "DECLINED")]
)
def test_response_commits_status_and_membership(client, database, decision, state):
    engine, data = database
    invitation_id = pending_invitation(client, data)
    response = client.patch(
        "/api/v1/invitations",
        json={"invitation_id": invitation_id, "decision": decision},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == state
    assert response.json()["responded_at"] is not None
    with Session(engine) as session:
        invitation = session.get(Invitation, invitation_id)
        assert invitation.status == state and invitation.responded_at.tzinfo is not None
        member = session.get(TripMember, (data["trip_id"], data["recipient"]))
        if decision == "ACCEPT":
            assert member is not None and member.role == "MEMBER"
        else:
            assert member is None
    for next_decision in ("ACCEPT", "DECLINE"):
        assert (
            client.patch(
                "/api/v1/invitations",
                json={"invitation_id": invitation_id, "decision": next_decision},
            ).status_code
            == 409
        )


@pytest.mark.parametrize(
    "case,expected",
    [("missing", 404), ("other-user", 403), ("member", 409), ("full", 409)],
)
def test_rejected_response_preserves_pending_invitation(
    client, database, fill_trip, case, expected
):
    engine, data = database
    invitation_id = pending_invitation(client, data)
    target_id = invitation_id
    if case == "missing":
        target_id = 9223372036854775807
    elif case == "other-user":
        client.cookies.set("access_token", security.create_access_token(data["other"]))
    elif case == "member":
        with Session(engine) as session:
            session.add(
                TripMember(
                    trip_id=data["trip_id"], user_id=data["recipient"], role="MEMBER"
                )
            )
            session.commit()
    else:
        fill_trip(7)
    response = client.patch(
        "/api/v1/invitations", json={"invitation_id": target_id, "decision": "ACCEPT"}
    )
    assert response.status_code == expected, response.text
    with Session(engine) as session:
        invitation = session.get(Invitation, invitation_id)
        assert invitation.status == "PENDING" and invitation.responded_at is None
        if case != "member":
            assert session.get(TripMember, (data["trip_id"], data["recipient"])) is None


def test_full_trip_can_still_be_declined(client, database, fill_trip):
    engine, data = database
    invitation_id = pending_invitation(client, data)
    fill_trip(7)
    response = client.patch(
        "/api/v1/invitations",
        json={"invitation_id": invitation_id, "decision": "DECLINE"},
    )
    assert response.status_code == 200 and response.json()["status"] == "DECLINED"
    with Session(engine) as session:
        assert session.get(TripMember, (data["trip_id"], data["recipient"])) is None


def test_failed_response_rolls_back_both_changes(client, database):
    engine, data = database
    invitation_id = pending_invitation(client, data)
    original = InvitationRepository.save_response

    def fail_after_flush(repository, invitation):
        original(repository, invitation)
        raise RuntimeError("Simulated failure after membership and response writes")

    payload = {"invitation_id": invitation_id, "decision": "ACCEPT"}
    with patch.object(InvitationRepository, "save_response", fail_after_flush):
        assert client.patch("/api/v1/invitations", json=payload).status_code == 500
    with Session(engine) as session:
        invitation = session.get(Invitation, invitation_id)
        assert invitation.status == "PENDING" and invitation.responded_at is None
        assert session.get(TripMember, (data["trip_id"], data["recipient"])) is None
    assert client.patch("/api/v1/invitations", json=payload).status_code == 200


@pytest.mark.parametrize("same_invitation", [True, False])
def test_concurrent_acceptance_is_serialized(
    client, database, fill_trip, same_invitation
):
    engine, data = database
    first_id = pending_invitation(client, data)
    fill_trip(6)  # Organizer + six members leaves exactly one place.
    second_id = first_id
    second_user = data["recipient"]
    if not same_invitation:
        with Session(engine) as session:
            invitation = Invitation(
                trip_id=data["trip_id"],
                invited_user_id=data["other"],
                invited_by_user_id=data["organizer"],
                status="PENDING",
            )
            session.add(invitation)
            session.flush()
            second_id = invitation.invitation_id
            session.commit()
        second_user = data["other"]
    barrier = Barrier(2)

    def accept(invitation_id, user_id):
        with Session(engine) as session:
            # Force both Sessions to cache PENDING before either obtains the lock.
            cached = session.get(Invitation, invitation_id)
            assert cached.status == "PENDING"
            barrier.wait(timeout=10)
            try:
                InvitationService(session).respond_to_invitation(
                    RespondInvitationRequest(
                        invitation_id=invitation_id, decision="ACCEPT"
                    ),
                    user_id,
                )
                return 200
            except HTTPException as error:
                return error.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(accept, first_id, data["recipient"]),
            pool.submit(accept, second_id, second_user),
        ]
        results = [future.result(timeout=20) for future in futures]
    assert sorted(results) == [200, 409]
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(TripMember)
                .where(TripMember.trip_id == data["trip_id"])
            )
            == 8
        )
        invitations = session.scalars(
            select(Invitation).where(
                Invitation.invitation_id.in_([first_id, second_id])
            )
        ).all()
        assert sum(invitation.status == "ACCEPTED" for invitation in invitations) == 1
        if not same_invitation:
            assert (
                sum(invitation.status == "PENDING" for invitation in invitations) == 1
            )
