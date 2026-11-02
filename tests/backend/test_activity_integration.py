"""Critical activity API rules against a migrated PostgreSQL test database."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from importlib import import_module
from threading import Barrier, Event
from unittest.mock import patch
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import sessionmaker

from backend.app.core import filter as authentication
from backend.app.core import poll_scheduler, security
from backend.app.core.config import Settings
from backend.app.core.database import get_session
from backend.app.core.poll_scheduler import close_due_polls
from backend.app.main import app
from backend.app.main import settings as app_settings
from backend.app.models import (
    ItineraryItem,
    Poll,
    Proposal,
    Trip,
    TripMember,
    User,
    Vote,
)
from backend.app.repositories.ActivityRepository import ActivityRepository

service_module = import_module("backend.app.services.ActivityService")


@pytest.mark.parametrize(
    "timezone,travel_date,starts_at,ends_at,invalid_field",
    [
        # Final-day evenings may already be tomorrow in UTC.
        (
            "America/New_York",
            "2030-07-01",
            "2030-07-02T02:00:00Z",
            "2030-07-02T03:00:00Z",
            None,
        ),
        (
            "America/New_York",
            "2030-01-01",
            "2030-01-01T21:00:00-05:00",
            "2030-01-01T22:00:00-05:00",
            None,
        ),
        # DST skips an hour in spring and repeats one in autumn. Compare instants.
        (
            "America/New_York",
            "2030-03-10",
            "2030-03-10T01:30:00-05:00",
            "2030-03-10T03:30:00-04:00",
            None,
        ),
        (
            "America/New_York",
            "2030-11-03",
            "2030-11-03T01:30:00-04:00",
            "2030-11-03T01:15:00-05:00",
            None,
        ),
        # UTC date is inside the trip, but the local start date is too early.
        (
            "America/New_York",
            "2030-07-01",
            "2030-07-01T03:00:00Z",
            "2030-07-01T03:30:00Z",
            "starts_at",
        ),
        # Local end date extends past the last travel day.
        (
            "America/New_York",
            "2030-07-01",
            "2030-07-02T03:30:00Z",
            "2030-07-02T04:30:00Z",
            "ends_at",
        ),
        # Positive offsets can place the first local day on the previous UTC day.
        (
            "Pacific/Kiritimati",
            "2030-07-01",
            "2030-06-30T10:30:00Z",
            "2030-06-30T11:30:00Z",
            None,
        ),
        ("UTC", "2030-07-01", "2030-07-01T22:00:00Z", "2030-07-01T23:00:00Z", None),
    ],
)
def test_proposal_uses_trip_local_dates(
    scenario,
    timezone,
    travel_date,
    starts_at,
    ends_at,
    invalid_field,
):
    s = scenario
    with s["factory"]() as session:
        trip = session.get(Trip, s["trip"])
        trip.timezone = timezone
        trip.start_date = trip.end_date = date.fromisoformat(travel_date)
        session.commit()

    class BeforeTrip(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2029, 1, 1, tzinfo=UTC)

    with patch.object(service_module, "datetime", BeforeTrip):
        response = s["client"].post(
            f"/api/v1/trips/{s['trip']}/proposals",
            json=s["payload"] | {"starts_at": starts_at, "ends_at": ends_at},
        )
    if invalid_field:
        assert response.status_code == 422, response.text
        assert response.json()["detail"][0]["loc"] == ["body", invalid_field]
        assert proposals(s) == []
    else:
        assert response.status_code == 201, response.text
        with s["factory"]() as session:
            saved = session.get(Proposal, response.json()["proposal_id"])
            assert saved.starts_at.astimezone(UTC) == datetime.fromisoformat(
                starts_at
            ).astimezone(UTC)
            assert saved.ends_at.astimezone(UTC) == datetime.fromisoformat(
                ends_at
            ).astimezone(UTC)


@pytest.fixture
def scenario(monkeypatch):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(url)
    factory = sessionmaker(engine, autoflush=False)
    now = datetime.now(UTC)
    with factory() as session:
        users = [
            User(
                user_name=uuid4().hex[:20],
                email=f"{uuid4()}@example.com",
                password_hash="unused",
            )
            for _ in range(4)
        ]
        session.add_all(users)
        session.flush()
        ids = [user.user_id for user in users]
        trip = Trip(
            name="Activity test",
            destination="NYC",
            start_date=now.date(),
            end_date=(now + timedelta(days=10)).date(),
            organizer_id=ids[0],
        )
        session.add(trip)
        session.flush()
        trip_id = trip.trip_id
        session.add_all(
            [
                TripMember(
                    trip_id=trip_id,
                    user_id=user_id,
                    role="ORGANIZER" if i == 0 else "MEMBER",
                )
                for i, user_id in enumerate(ids[:3])
            ]
        )
        session.commit()
    settings = Settings(_env_file=None, jwt_secret="activity-tests-" * 8)
    monkeypatch.setattr(authentication, "get_settings", lambda: settings)
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    monkeypatch.setattr(app_settings, "poll_scheduler_enabled", False)

    def sessions():
        with factory() as session:
            yield session

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_session] = sessions
    data = {
        "factory": factory,
        "trip": trip_id,
        "users": ids,
        "settings": settings,
        "payload": {
            "title": "Museum",
            "description": "Visit the collection",
            "location": "NYC",
            "estimated_cost": "12.50",
            "starts_at": (now + timedelta(days=2)).isoformat(),
            "ends_at": (now + timedelta(days=2, hours=1)).isoformat(),
        },
        "deadline": (now + timedelta(hours=1)).isoformat(),
    }
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            data["client"] = client
            login(data, 0)
            yield data
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        with engine.begin() as connection:
            connection.execute(delete(Trip).where(Trip.trip_id == trip_id))
            connection.execute(delete(User).where(User.user_id.in_(ids)))
        engine.dispose()


def login(s, index):
    s["client"].cookies.set(
        "access_token", security.create_access_token(s["users"][index])
    )


def create(s, **changes):
    response = s["client"].post(
        f"/api/v1/trips/{s['trip']}/proposals", json=s["payload"] | changes
    )
    assert response.status_code == 201, response.text
    return response.json()


def open_poll(s, proposal_id):
    response = s["client"].post(
        f"/api/v1/proposals/{proposal_id}/poll", json={"deadline": s["deadline"]}
    )
    assert response.status_code == 201, response.text
    return response.json()


def vote(s, poll_id, choice):
    return s["client"].put(f"/api/v1/polls/{poll_id}/vote", json={"choice": choice})


def proposals(s):
    response = s["client"].get(f"/api/v1/trips/{s['trip']}/proposals")
    assert response.status_code == 200, response.text
    return response.json()


def itinerary(s):
    response = s["client"].get(f"/api/v1/trips/{s['trip']}/itinerary")
    assert response.status_code == 200, response.text
    return response.json()


def expire(s, poll_id):
    with s["factory"]() as session:
        poll = session.get(Poll, poll_id)
        poll.opened_at = datetime.now(UTC) - timedelta(hours=2)
        poll.deadline = datetime.now(UTC) - timedelta(hours=1)
        session.commit()


def test_vote_updates_snapshot_and_cancellation_preserve_history(scenario):
    s = scenario
    proposal = create(s)
    poll = open_poll(s, proposal["proposal_id"])
    pid = poll["poll_id"]
    assert poll["eligible_voter_ids"] == s["users"][:3]
    assert vote(s, pid, "NO").status_code == 200
    assert vote(s, pid, "YES").status_code == 200
    assert vote(s, pid, "YES").status_code == 200  # Retry does not add another event.
    current = proposals(s)[0]["poll"]
    assert (current["yes_count"], current["no_count"], current["total_votes"]) == (
        1,
        0,
        1,
    )
    assert [event["choice"] for event in current["voting_history"]] == ["NO", "YES"]
    with s["factory"]() as session:
        session.add(TripMember(trip_id=s["trip"], user_id=s["users"][3], role="MEMBER"))
        session.commit()
    login(s, 3)
    assert vote(s, pid, "YES").status_code == 403  # Joined after snapshot.
    login(s, 0)
    assert (
        s["client"]
        .post(
            f"/api/v1/proposals/{proposal['proposal_id']}/poll",
            json={"deadline": s["deadline"]},
        )
        .status_code
        == 409
    )
    expire(s, pid)
    assert vote(s, pid, "NO").status_code == 409  # Scheduler has not run yet.
    assert close_due_polls(s["factory"]) == 1
    assert close_due_polls(s["factory"]) == 0
    item = itinerary(s)[0]
    login(s, 1)
    path = f"/api/v1/trips/{s['trip']}/itinerary/{item['item_id']}"
    assert s["client"].delete(path).status_code == 403
    login(s, 0)
    assert s["client"].delete(path).status_code == 204
    assert s["client"].delete(path).status_code == 204
    assert itinerary(s) == []
    result = proposals(s)[0]
    assert result["status"] == "CANCELLED"
    assert result["poll"]["outcome"] == "APPROVED"
    assert result["poll"]["voting_history"] == current["voting_history"]
    assert (
        s["client"]
        .post(f"/api/v1/proposals/{proposal['proposal_id']}/withdraw")
        .status_code
        == 409
    )


@pytest.mark.parametrize(
    "choices,outcome,decision",
    [
        ([], "REJECTED", None),
        (["NO"], "REJECTED", None),
        (["YES", "NO"], "TIED", "APPROVE"),
        (["YES", "NO"], "TIED", "REJECT"),
    ],
)
def test_automatic_outcomes_and_organizer_tie_resolution(
    scenario, choices, outcome, decision
):
    s = scenario
    poll = open_poll(s, create(s)["proposal_id"])
    pid = poll["poll_id"]
    for index, choice in enumerate(choices):
        login(s, index)
        assert vote(s, pid, choice).status_code == 200
    login(s, 0)
    path = f"/api/v1/polls/{pid}/resolve"
    assert s["client"].post(path, json={"decision": "APPROVE"}).status_code == 409
    expire(s, pid)
    close_due_polls(s["factory"])
    assert proposals(s)[0]["status"] == outcome
    assert itinerary(s) == []
    if decision:
        login(s, 1)
        assert s["client"].post(path, json={"decision": decision}).status_code == 403
        login(s, 0)
        response = s["client"].post(path, json={"decision": decision})
        assert response.status_code == 200, response.text
        assert response.json()["poll"]["outcome"] == "TIED"
        assert response.json()["poll"]["resolution"]["decision"] == decision
        assert len(itinerary(s)) == (1 if decision == "APPROVE" else 0)
    assert s["client"].post(path, json={"decision": "APPROVE"}).status_code == 409


@pytest.mark.parametrize("with_poll", [False, True])
def test_only_author_can_withdraw_and_no_later_action_is_allowed(scenario, with_poll):
    s = scenario
    login(s, 1)
    proposal = create(s)
    login(s, 0)
    poll = open_poll(s, proposal["proposal_id"]) if with_poll else None
    path = f"/api/v1/proposals/{proposal['proposal_id']}/withdraw"
    assert (
        s["client"].post(path).status_code == 403
    )  # Even organizer cannot withdraw another's.
    if poll:
        assert vote(s, poll["poll_id"], "YES").status_code == 200
    login(s, 1)
    response = s["client"].post(path)
    assert response.status_code == 200 and response.json()["status"] == "WITHDRAWN"
    assert s["client"].post(path).status_code == 409
    if poll:
        assert response.json()["poll"]["outcome"] is None
        assert response.json()["poll"]["total_votes"] == 1
        assert vote(s, poll["poll_id"], "NO").status_code == 409
        expire(s, poll["poll_id"])
        assert close_due_polls(s["factory"]) == 0
    login(s, 0)
    assert (
        s["client"]
        .post(
            f"/api/v1/proposals/{proposal['proposal_id']}/poll",
            json={"deadline": s["deadline"]},
        )
        .status_code
        == 409
    )


def test_membership_validation_and_deadline_boundary(scenario):
    s = scenario
    path = f"/api/v1/trips/{s['trip']}/proposals"
    login(s, 3)
    assert s["client"].get(path).status_code == 403
    assert s["client"].get(f"/api/v1/trips/{s['trip']}/itinerary").status_code == 403
    assert s["client"].post(path, json=s["payload"]).status_code == 403
    login(s, 0)
    for changes in (
        {"estimated_cost": -1},
        {"description": " "},
        {"title": " "},
        {"starts_at": (datetime.now(UTC) - timedelta(days=1)).isoformat()},
        {"ends_at": s["payload"]["starts_at"]},
        {"ends_at": (datetime.now(UTC) + timedelta(days=20)).isoformat()},
        {"starts_at": "2030-01-01T12:00:00"},
    ):
        assert s["client"].post(path, json=s["payload"] | changes).status_code == 422
    missing = s["payload"].copy()
    del missing["estimated_cost"]
    assert s["client"].post(path, json=missing).status_code == 422
    assert proposals(s) == []
    proposal = create(s)
    poll_path = f"/api/v1/proposals/{proposal['proposal_id']}/poll"
    login(s, 1)
    assert (
        s["client"].post(poll_path, json={"deadline": s["deadline"]}).status_code == 403
    )
    login(s, 0)
    for deadline in (s["payload"]["starts_at"], datetime.now(UTC).isoformat()):
        assert (
            s["client"].post(poll_path, json={"deadline": deadline}).status_code == 422
        )
    poll = open_poll(s, proposal["proposal_id"])
    deadline = datetime.fromisoformat(s["deadline"])

    class AtDeadline(datetime):
        @classmethod
        def now(cls, tz=None):
            return deadline

    with patch.object(service_module, "datetime", AtDeadline):
        assert vote(s, poll["poll_id"], "YES").status_code == 409
        assert (
            s["client"]
            .post(f"/api/v1/proposals/{proposal['proposal_id']}/withdraw")
            .status_code
            == 409
        )
    assert proposals(s)[0]["poll"]["total_votes"] == 0


@pytest.mark.parametrize("token_kind", ["missing", "malformed", "expired"])
def test_all_activity_endpoints_require_valid_authentication(scenario, token_kind):
    s = scenario
    s["client"].cookies.clear()
    if token_kind == "malformed":
        s["client"].cookies.set("access_token", "not-a-jwt")
    elif token_kind == "expired":
        token = jwt.encode(
            {
                "sub": str(s["users"][0]),
                "iat": datetime.now(UTC) - timedelta(hours=2),
                "exp": datetime.now(UTC) - timedelta(hours=1),
            },
            s["settings"].jwt_secret,
            algorithm="HS256",
        )
        s["client"].cookies.set("access_token", token)
    for method, path, body in [
        ("POST", f"/trips/{s['trip']}/proposals", s["payload"]),
        ("GET", f"/trips/{s['trip']}/proposals", None),
        ("POST", "/proposals/1/withdraw", None),
        ("POST", "/proposals/1/poll", {"deadline": s["deadline"]}),
        ("PUT", "/polls/1/vote", {"choice": "YES"}),
        ("POST", "/polls/1/resolve", {"decision": "APPROVE"}),
        ("GET", f"/trips/{s['trip']}/itinerary", None),
        ("DELETE", f"/trips/{s['trip']}/itinerary/1", None),
    ]:
        response = s["client"].request(method, "/api/v1" + path, json=body)
        assert response.status_code == 401, (path, response.text)


def test_concurrent_creation_enforces_hundred_proposal_limit(scenario):
    s = scenario
    with s["factory"]() as session:
        session.add_all(
            [
                Proposal(
                    **(
                        s["payload"]
                        | {
                            "starts_at": datetime.fromisoformat(
                                s["payload"]["starts_at"]
                            ),
                            "ends_at": datetime.fromisoformat(s["payload"]["ends_at"]),
                        }
                    ),
                    trip_id=s["trip"],
                    author_id=s["users"][0],
                    status="PENDING",
                )
                for _ in range(99)
            ]
        )
        session.commit()
    barrier = Barrier(2)

    def submit():
        client = TestClient(app)
        client.cookies.set("access_token", security.create_access_token(s["users"][0]))
        barrier.wait(timeout=10)
        try:
            return client.post(
                f"/api/v1/trips/{s['trip']}/proposals", json=s["payload"]
            ).status_code
        finally:
            client.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(submit) for _ in range(2)]
        assert sorted(f.result(timeout=20) for f in futures) == [201, 409]
    assert len(proposals(s)) == 100


def test_failed_poll_open_rolls_back_and_concurrent_closure_is_exactly_once(scenario):
    s = scenario
    proposal = create(s)
    original = ActivityRepository.member_ids

    def fail_after_insert(repository, trip_id):
        original(repository, trip_id)
        raise RuntimeError("Failure after poll INSERT")

    with patch.object(ActivityRepository, "member_ids", fail_after_insert):
        response = s["client"].post(
            f"/api/v1/proposals/{proposal['proposal_id']}/poll",
            json={"deadline": s["deadline"]},
        )
        assert response.status_code == 500
    assert proposals(s)[0]["status"] == "PENDING"
    assert proposals(s)[0]["poll"] is None
    poll = open_poll(s, proposal["proposal_id"])
    assert vote(s, poll["poll_id"], "YES").status_code == 200
    expire(s, poll["poll_id"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(close_due_polls, s["factory"]) for _ in range(2)]
        assert sum(f.result(timeout=20) for f in futures) == 1
    with s["factory"]() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(ItineraryItem)
                .where(ItineraryItem.proposal_id == proposal["proposal_id"])
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(Vote)
                .where(Vote.poll_id == poll["poll_id"])
            )
            == 1
        )


def test_scheduler_lifespan_recovers_overdue_poll_after_failed_approval(
    scenario, monkeypatch
):
    s = scenario
    poll = open_poll(s, create(s)["proposal_id"])
    assert vote(s, poll["poll_id"], "YES").status_code == 200
    expire(s, poll["poll_id"])
    original = service_module.ActivityService._approve

    def fail_after_approval(service, proposal):
        original(service, proposal)
        service.session.flush()
        raise RuntimeError("Failure after itinerary INSERT")

    with patch.object(service_module.ActivityService, "_approve", fail_after_approval):
        assert close_due_polls(s["factory"]) == 0
    assert proposals(s)[0]["status"] == "OPEN"
    assert proposals(s)[0]["poll"]["closed_at"] is None
    assert itinerary(s) == []
    completed = Event()

    def scan():
        result = close_due_polls(s["factory"])
        completed.set()
        return result

    monkeypatch.setattr(poll_scheduler, "close_due_polls", scan)
    monkeypatch.setattr(app_settings, "poll_scheduler_enabled", True)
    monkeypatch.setattr(app_settings, "poll_scheduler_interval_seconds", 0.01)
    with TestClient(app):
        assert completed.wait(timeout=5), (
            "Lifespan did not schedule deadline processing"
        )
    assert proposals(s)[0]["status"] == "APPROVED"
    assert len(itinerary(s)) == 1


def test_itinerary_order_and_cross_trip_cancellation(scenario):
    s = scenario
    later = create(s)
    earlier_start = datetime.fromisoformat(s["payload"]["starts_at"]) - timedelta(
        hours=2
    )
    earlier = create(
        s,
        starts_at=earlier_start.isoformat(),
        ends_at=(earlier_start + timedelta(hours=1)).isoformat(),
    )
    for proposal in (later, earlier):
        poll = open_poll(s, proposal["proposal_id"])
        assert vote(s, poll["poll_id"], "YES").status_code == 200
        expire(s, poll["poll_id"])
    close_due_polls(s["factory"])
    items = itinerary(s)
    assert [item["proposal_id"] for item in items] == [
        earlier["proposal_id"],
        later["proposal_id"],
    ]
    response = s["client"].post(
        "/api/v1/trips",
        json={
            "name": "Other trip",
            "destination": "NYC",
            "start_date": datetime.now(UTC).date().isoformat(),
            "end_date": (datetime.now(UTC) + timedelta(days=10)).date().isoformat(),
            "timezone": "UTC",
        },
    )
    assert response.status_code == 201, response.text
    other_trip = response.json()["trip_id"]
    try:
        path = f"/api/v1/trips/{other_trip}/itinerary/{items[0]['item_id']}"
        assert s["client"].delete(path).status_code == 404
        assert len(itinerary(s)) == 2
    finally:
        assert s["client"].delete(f"/api/v1/trips/{other_trip}").status_code == 204
