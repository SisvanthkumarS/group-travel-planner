"""Notification contracts, event wiring and outbox concurrency on real PostgreSQL.

All mail delivery is mocked; no test sends to an external SMTP server.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker

from backend.app.core import filter as authentication
from backend.app.core import security
from backend.app.core.config import Settings, get_settings
from backend.app.core.database import get_session
from backend.app.core.notification_worker import process_pending_emails
from backend.app.main import app
from backend.app.models import (
    Notification,
    NotificationEmail,
    Poll,
    Trip,
    TripMember,
    User,
)
from backend.app.schemas.notification import NotificationPreferences
from backend.app.services.EmailService import EmailDeliveryError
from backend.app.services.NotificationInboxService import NotificationInboxService
from backend.app.services.NotificationPublisher import NotificationPublisher

BASE = "/api/v1/notifications"


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
            name="Notification test",
            destination="NYC",
            timezone="UTC",
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
                    role="ORGANIZER" if index == 0 else "MEMBER",
                )
                for index, user_id in enumerate(ids[:3])
            ]
        )
        session.commit()

    settings = Settings(
        _env_file=None,
        jwt_secret="notification-test-secret-" * 3,
        email_enabled=False,
        poll_scheduler_enabled=False,
        notification_email_worker_enabled=False,
    )
    monkeypatch.setattr(authentication, "get_settings", lambda: settings)
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    previous = app.dependency_overrides.copy()

    def session_dependency():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = session_dependency
    app.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(app, headers={"X-CSRF-Protection": "1"})
    data = {
        "client": client,
        "factory": factory,
        "ids": ids,
        "trip_id": trip_id,
        "now": now,
    }
    try:
        yield data
    finally:
        client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        with factory() as session:
            session.execute(delete(Trip).where(Trip.trip_id == trip_id))
            session.execute(delete(User).where(User.user_id.in_(ids)))
            session.commit()
        engine.dispose()


def sign_in(s, index=0):
    s["client"].cookies.clear()
    s["client"].cookies.set(
        "access_token", security.create_access_token(s["ids"][index])
    )
    return s["client"]


def emit(s, *, key=None, recipient=1, session=None):
    def publish(db):
        trip = db.get(Trip, s["trip_id"])
        NotificationPublisher(db).publish(
            event_key=key or str(uuid4()),
            event_type="PROPOSAL_CREATED",
            recipients=[s["ids"][recipient]],
            actor_id=s["ids"][0],
            trip=trip,
            title="New proposal",
            message="A new proposal is ready.",
        )

    if session is not None:
        publish(session)
    else:
        with s["factory"]() as db:
            publish(db)
            db.commit()


def preferences(s, index=1, in_app=True, email=True):
    with s["factory"]() as session:
        NotificationInboxService(session).update_preferences(
            s["ids"][index],
            NotificationPreferences(in_app_enabled=in_app, email_enabled=email),
        )


def rows(s, model=Notification):
    with s["factory"]() as session:
        query = select(model).order_by(model.notification_id)
        if model is Notification:
            query = query.where(Notification.user_id.in_(s["ids"]))
        else:
            query = query.join(Notification).where(Notification.user_id.in_(s["ids"]))
        return list(session.scalars(query))


def worker_settings(**changes):
    return Settings(
        _env_file=None,
        email_enabled=True,
        smtp_host="test.invalid",
        email_from_address="sender@example.com",
        **changes,
    )


def test_default_preferences_and_private_api(scenario):
    s = scenario
    assert s["client"].get(BASE).status_code == 401
    client = sign_in(s, 1)
    assert client.get(BASE + "/preferences").json() == {
        "in_app_enabled": True,
        "email_enabled": False,
    }
    emit(s)
    listing = client.get(BASE).json()
    notification = listing["items"][0]
    assert notification["action_url"] == f"/trips/{s['trip_id']}"
    assert notification["read_at"] is None
    assert client.get(BASE + "/unread-count").json() == {"unread_count": 1}
    sign_in(s, 2)
    assert client.get(BASE).json()["items"] == []
    assert (
        client.patch(f"{BASE}/{notification['notification_id']}/read").status_code
        == 404
    )
    assert client.get(BASE + "/unread-count").json()["unread_count"] == 0
    sign_in(s, 1)
    first = client.patch(f"{BASE}/{notification['notification_id']}/read").json()
    assert first["read_at"] is not None
    assert (
        client.patch(f"{BASE}/{notification['notification_id']}/read").json() == first
    )
    assert client.get(BASE + "/unread-count").json()["unread_count"] == 0
    assert client.get(BASE, params={"unread_only": True}).json()["items"] == []


@pytest.mark.parametrize(
    "in_app,email", [(True, True), (True, False), (False, True), (False, False)]
)
def test_channel_preferences_persist_and_control_visibility(scenario, in_app, email):
    s = scenario
    client = sign_in(s, 1)
    body = {"in_app_enabled": in_app, "email_enabled": email}
    assert client.put(BASE + "/preferences", json=body).json() == body
    assert client.get(BASE + "/preferences").json() == body
    emit(s)
    assert len(client.get(BASE).json()["items"]) == int(in_app)
    assert client.get(BASE + "/unread-count").json()["unread_count"] == int(in_app)
    assert len(rows(s, NotificationEmail)) == int(email)
    if email and not in_app:
        assert (
            client.patch(f"{BASE}/{rows(s)[0].notification_id}/read").status_code == 404
        )
    sign_in(s, 2)
    assert client.get(BASE + "/preferences").json() == {
        "in_app_enabled": True,
        "email_enabled": False,
    }


def test_pagination_and_bounded_mark_all(scenario):
    s = scenario
    client = sign_in(s, 1)
    for _ in range(3):
        emit(s)
    first = client.get(BASE, params={"limit": 2}).json()
    ids = [row["notification_id"] for row in first["items"]]
    assert ids == sorted(ids, reverse=True)
    second = client.get(
        BASE, params={"before_id": first["next_before_id"], "limit": 2}
    ).json()
    assert len(second["items"]) == 1 and second["next_before_id"] is None
    emit(s)
    assert client.post(BASE + "/read-all", json={"through_id": ids[0]}).json() == {
        "updated_count": 3
    }
    assert client.post(BASE + "/read-all", json={"through_id": ids[0]}).json() == {
        "updated_count": 0
    }
    assert client.get(BASE + "/unread-count").json()["unread_count"] == 1
    assert client.post(BASE + "/read-all", json={}).json()["updated_count"] == 1


def test_preferences_retain_history_cancel_queue_and_do_not_backfill(scenario):
    s = scenario
    preferences(s)
    emit(s)
    preferences(s, in_app=False, email=False)
    emit(s)
    assert len(rows(s)) == 1
    assert rows(s, NotificationEmail)[0].status == "CANCELED"
    assert len(sign_in(s, 1).get(BASE).json()["items"]) == 1
    preferences(s)
    sender = Mock()
    assert process_pending_emails(worker_settings(), s["factory"], sender) == 0
    sender.send.assert_not_called()
    assert len(rows(s)) == 1
    emit(s)
    assert process_pending_emails(worker_settings(), s["factory"], sender) == 1
    sender.send.assert_called_once()


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"in_app_enabled": True},
        {"in_app_enabled": None, "email_enabled": True},
        {"in_app_enabled": "false", "email_enabled": False},
        {"in_app_enabled": True, "email_enabled": False, "user_id": 1},
    ],
)
def test_invalid_preferences_are_rejected(scenario, body):
    assert sign_in(scenario).put(BASE + "/preferences", json=body).status_code == 422


def test_mutations_require_csrf_and_query_limits_are_validated(scenario):
    client = sign_in(scenario)
    client.headers.pop("X-CSRF-Protection")
    assert (
        client.put(
            BASE + "/preferences", json={"in_app_enabled": True, "email_enabled": True}
        ).status_code
        == 403
    )
    assert client.patch(BASE + "/1/read").status_code == 403
    assert client.post(BASE + "/read-all", json={}).status_code == 403
    for params in [{"limit": 0}, {"limit": 101}, {"before_id": -1}]:
        assert client.get(BASE, params=params).status_code == 422


def test_event_deduplication_self_exclusion_and_rollback(scenario):
    s = scenario
    preferences(s)
    emit(s, key="once")
    emit(s, key="once")
    emit(s, recipient=0)
    assert len(rows(s)) == 1 and len(rows(s, NotificationEmail)) == 1
    with s["factory"]() as session:
        emit(s, key="rolled-back", session=session)
        session.rollback()
    assert len(rows(s)) == 1 and len(rows(s, NotificationEmail)) == 1


def test_business_transaction_rolls_back_if_notification_write_fails(scenario):
    s = scenario
    from unittest.mock import patch

    client = sign_in(s)
    with (
        patch.object(
            NotificationPublisher, "publish", side_effect=RuntimeError("write failed")
        ),
        pytest.raises(RuntimeError, match="write failed"),
    ):
        client.delete(f"/api/v1/trips/{s['trip_id']}")
    with s["factory"]() as session:
        assert session.get(Trip, s["trip_id"]) is not None


def test_trip_delete_preserves_history_and_removes_links(scenario):
    s = scenario
    emit(s)
    assert sign_in(s).delete(f"/api/v1/trips/{s['trip_id']}").status_code == 204
    items = sign_in(s, 1).get(BASE).json()["items"]
    assert {item["event_type"] for item in items} == {
        "PROPOSAL_CREATED",
        "TRIP_DELETED",
    }
    assert all(item["trip_id"] is None and item["action_url"] is None for item in items)
    assert all(item["trip_name"] == "Notification test" for item in items)


@pytest.mark.parametrize("decision", ["ACCEPT", "DECLINE"])
def test_invitation_events(scenario, decision):
    s = scenario
    client = sign_in(s)
    with s["factory"]() as session:
        email = session.get(User, s["ids"][3]).email
    response = client.post(
        f"/api/v1/trips/{s['trip_id']}/invitations", json={"email": email}
    )
    assert response.status_code == 201, response.text
    invitation_id = response.json()["invitation_id"]
    recipient_items = sign_in(s, 3).get(BASE).json()["items"]
    assert recipient_items[0]["event_type"] == "INVITATION_RECEIVED"
    assert recipient_items[0]["action_url"] == "/trips"
    assert (
        client.patch(
            "/api/v1/invitations",
            json={"invitation_id": invitation_id, "decision": decision},
        ).status_code
        == 200
    )
    assert sign_in(s).get(BASE).json()["items"][0]["event_type"] == "INVITATION_" + (
        "ACCEPTED" if decision == "ACCEPT" else "DECLINED"
    )


def make_poll(s):
    client = sign_in(s, 1)
    payload = {
        "title": "Museum",
        "description": "Visit museum",
        "location": "NYC",
        "estimated_cost": "15",
        "starts_at": (s["now"] + timedelta(days=2)).isoformat(),
        "ends_at": (s["now"] + timedelta(days=2, hours=1)).isoformat(),
    }
    response = client.post(f"/api/v1/trips/{s['trip_id']}/proposals", json=payload)
    assert response.status_code == 201, response.text
    proposal_id = response.json()["proposal_id"]
    assert rows(s)[0].event_type == "PROPOSAL_CREATED"
    assert rows(s)[0].user_id == s["ids"][0]
    response = sign_in(s).post(
        f"/api/v1/proposals/{proposal_id}/poll",
        json={"deadline": (s["now"] + timedelta(days=1)).isoformat()},
    )
    assert response.status_code == 201, response.text
    poll_id = response.json()["poll_id"]
    opened = [row for row in rows(s) if row.event_type == "POLL_OPENED"]
    assert {row.user_id for row in opened} == set(s["ids"][1:3])
    return proposal_id, poll_id


@pytest.mark.parametrize("outcome", ["APPROVED", "REJECTED", "TIED"])
def test_poll_outcome_events_and_cancellation(scenario, outcome):
    from backend.app.services.ActivityService import ActivityService

    s = scenario
    _proposal_id, poll_id = make_poll(s)
    if outcome != "REJECTED":
        assert (
            sign_in(s, 1)
            .put(f"/api/v1/polls/{poll_id}/vote", json={"choice": "YES"})
            .status_code
            == 200
        )
    if outcome == "TIED":
        assert (
            sign_in(s, 2)
            .put(f"/api/v1/polls/{poll_id}/vote", json={"choice": "NO"})
            .status_code
            == 200
        )
    with s["factory"]() as session:
        poll = session.get(Poll, poll_id)
        poll.opened_at = s["now"] - timedelta(hours=2)
        poll.deadline = s["now"] - timedelta(hours=1)
        session.commit()
        service = ActivityService(session)
        assert service.close_due_for_trip(s["trip_id"]) == 1
        assert service.close_due_for_trip(s["trip_id"]) == 0
    event_type = "POLL_TIED" if outcome == "TIED" else f"ACTIVITY_{outcome}"
    notices = [row for row in rows(s) if row.event_type == event_type]
    assert {row.user_id for row in notices} == (
        {s["ids"][0]} if outcome == "TIED" else set(s["ids"][:3])
    )
    if outcome == "TIED":
        assert (
            sign_in(s)
            .post(f"/api/v1/polls/{poll_id}/resolve", json={"decision": "APPROVE"})
            .status_code
            == 200
        )
        assert {
            row.user_id for row in rows(s) if row.event_type == "ACTIVITY_APPROVED"
        } == set(s["ids"][1:3])
    if outcome != "REJECTED":
        client = sign_in(s)
        item = client.get(f"/api/v1/trips/{s['trip_id']}/itinerary").json()[0]
        path = f"/api/v1/trips/{s['trip_id']}/itinerary/{item['item_id']}"
        assert client.delete(path).status_code == 204
        assert client.delete(path).status_code == 204
        assert {
            row.user_id for row in rows(s) if row.event_type == "ACTIVITY_CANCELLED"
        } == set(s["ids"][1:3])


def test_worker_retry_backoff_and_terminal_failure(scenario):
    s = scenario
    preferences(s)
    emit(s)
    sender = Mock()
    sender.send.side_effect = EmailDeliveryError("failure")
    settings = worker_settings(notification_email_max_attempts=2)
    assert process_pending_emails(settings, s["factory"], sender) == 1
    delivery = rows(s, NotificationEmail)[0]
    assert delivery.status == "PENDING" and delivery.attempts == 1
    assert delivery.next_attempt_at > datetime.now(UTC)
    assert process_pending_emails(settings, s["factory"], sender) == 0
    with s["factory"]() as session:
        session.get(NotificationEmail, delivery.notification_id).next_attempt_at = s[
            "now"
        ]
        session.commit()
    assert process_pending_emails(settings, s["factory"], sender) == 1
    assert rows(s, NotificationEmail)[0].status == "FAILED"
    assert process_pending_emails(settings, s["factory"], sender) == 0


def test_worker_rechecks_opt_out_and_global_pause(scenario):
    s = scenario
    preferences(s)
    emit(s)
    sender = Mock()
    settings = worker_settings()
    settings.email_enabled = False
    assert process_pending_emails(settings, s["factory"], sender) == 0
    settings.email_enabled = True
    with s["factory"]() as session:
        session.get(User, s["ids"][1]).email_notifications_enabled = False
        session.commit()
    assert process_pending_emails(settings, s["factory"], sender) == 0
    assert rows(s, NotificationEmail)[0].status == "CANCELED"
    sender.send.assert_not_called()


def test_concurrent_workers_do_not_submit_twice(scenario):
    s = scenario
    preferences(s)
    emit(s)
    entered, release = Event(), Event()
    sender = Mock()

    def send(**kwargs):
        entered.set()
        assert release.wait(5)

    sender.send.side_effect = send
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(
            process_pending_emails, worker_settings(), s["factory"], sender
        )
        try:
            assert entered.wait(5)
            second = pool.submit(
                process_pending_emails, worker_settings(), s["factory"], sender
            )
            assert second.result(timeout=5) == 0
        finally:
            release.set()
        assert first.result(timeout=5) == 1
    sender.send.assert_called_once()
    assert rows(s, NotificationEmail)[0].status == "SENT"


def test_slow_smtp_does_not_block_preferences_or_new_events(scenario):
    s = scenario
    preferences(s)
    emit(s)
    entered, release = Event(), Event()
    sender = Mock()

    def send(**kwargs):
        entered.set()
        assert release.wait(10)

    sender.send.side_effect = send
    with ThreadPoolExecutor(max_workers=2) as pool:
        sending = pool.submit(
            process_pending_emails, worker_settings(), s["factory"], sender
        )
        try:
            assert entered.wait(5)
            pool.submit(emit, s).result(timeout=3)
            pool.submit(preferences, s, email=False).result(timeout=3)
            assert all(row.status == "CANCELED" for row in rows(s, NotificationEmail))
        finally:
            release.set()
        sending.result(timeout=5)
    # An already submitted message cannot be recalled, but no queued retry survives.
    sender.send.assert_called_once()
    assert all(row.status == "CANCELED" for row in rows(s, NotificationEmail))


def test_worker_recovers_expired_lease_and_recovers_from_smtp_failure(scenario):
    from backend.app.core.notification_worker import claim_email

    s = scenario
    preferences(s)
    emit(s)
    notification_id = rows(s)[0].notification_id
    settings = worker_settings()
    claim = claim_email(settings, s["factory"], notification_id, s["ids"][1])
    assert claim is not None
    sender = Mock()
    assert process_pending_emails(settings, s["factory"], sender) == 0
    with s["factory"]() as session:
        session.get(NotificationEmail, notification_id).lease_expires_at = s["now"]
        session.commit()
    sender.send.side_effect = EmailDeliveryError("temporary")
    assert process_pending_emails(settings, s["factory"], sender) == 1
    with s["factory"]() as session:
        delivery = session.get(NotificationEmail, notification_id)
        assert delivery.status == "PENDING" and delivery.attempts == 2
        delivery.next_attempt_at = s["now"]
        session.commit()
    sender.send.side_effect = None
    assert process_pending_emails(settings, s["factory"], sender) == 1
    delivery = rows(s, NotificationEmail)[0]
    assert delivery.status == "SENT" and delivery.attempts == 3
    assert delivery.last_error is None and delivery.sent_at is not None
