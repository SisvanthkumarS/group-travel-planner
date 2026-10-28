"""PostgreSQL integration checks; set TEST_DATABASE_URL to a migrated test database."""

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError


@pytest.fixture
def db():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            yield connection
        finally:
            transaction.rollback()
    engine.dispose()


def user(db, email=None, user_name=None):
    return db.scalar(
        text(
            "INSERT INTO users (user_name, email, password_hash) "
            "VALUES (:name, :email, 'test-hash') RETURNING user_id"
        ),
        {
            "email": email or f"{uuid4()}@example.com",
            "name": user_name or uuid4().hex[:10],
        },
    )


def trip(db, organizer):
    return db.scalar(
        text(
            "INSERT INTO trips (name, destination, start_date, end_date, organizer_id) "
            "VALUES ('NYC trip', 'New York', '2026-11-01', '2026-11-03', :organizer) "
            "RETURNING trip_id"
        ),
        {"organizer": organizer},
    )


@pytest.fixture
def scenario(db):
    organizer, guest, third = user(db), user(db), user(db)
    own, other = trip(db, organizer), trip(db, third)
    for trip_id, user_id, role in [
        (own, organizer, "ORGANIZER"),
        (own, guest, "MEMBER"),
        (other, organizer, "MEMBER"),
        (other, third, "ORGANIZER"),
    ]:
        db.execute(
            text(
                "INSERT INTO trip_members (trip_id, user_id, role) VALUES (:t, :u, :r)"
            ),
            {"t": trip_id, "u": user_id, "r": role},
        )
    return {
        "organizer": organizer,
        "guest": guest,
        "third": third,
        "own": own,
        "other": other,
    }


def invite(db, trip_id, invited, inviter):
    return db.scalar(
        text(
            "INSERT INTO invitations (trip_id, invited_user_id, invited_by_user_id) "
            "VALUES (:t, :u, :by) RETURNING invitation_id"
        ),
        {"t": trip_id, "u": invited, "by": inviter},
    )


def test_email_uniqueness_ignores_case_and_spaces(db):
    email = f"{uuid4()}@example.com"
    user(db, email)
    with pytest.raises(IntegrityError), db.begin_nested():
        user(db, f"  {email.upper()}  ")


def test_username_is_unique(db):
    name = uuid4().hex[:10]
    user(db, user_name=name)
    with pytest.raises(IntegrityError), db.begin_nested():
        user(db, user_name=name)


@pytest.mark.parametrize("name", ["", "   ", "x" * 31])
def test_username_length_is_enforced_in_database(db, name):
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(
            text(
                "INSERT INTO users (user_name,email,password_hash) "
                "VALUES (:name,:email,'test-hash')"
            ),
            {"name": name, "email": f"{uuid4()}@example.com"},
        )


def test_database_accepts_thirty_character_username(db):
    assert user(db, user_name="x" * 30) is not None


@pytest.mark.parametrize(
    ("sql", "params"),
    [
        (
            "INSERT INTO users (user_name, email, password_hash) VALUES ('Test User', '   ', 'hash')",
            {},
        ),
        ("UPDATE trips SET name = ' ' WHERE trip_id = :own", None),
        ("UPDATE trips SET destination = ' ' WHERE trip_id = :own", None),
        ("UPDATE trips SET end_date = '2026-10-31' WHERE trip_id = :own", None),
        ("UPDATE trip_members SET role = 'ADMIN' WHERE trip_id = :own", None),
        (
            "INSERT INTO trip_members (trip_id, user_id, role) VALUES (:own, :organizer, 'MEMBER')",
            None,
        ),
        (
            "INSERT INTO trip_members (trip_id, user_id, role) VALUES (:own, -1, 'MEMBER')",
            None,
        ),
    ],
)
def test_invalid_values_are_rejected(db, scenario, sql, params):
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(text(sql), scenario if params is None else params)


def test_invitation_defaults_and_pending_uniqueness(db, scenario):
    s = scenario
    invitation = invite(db, s["own"], s["guest"], s["organizer"])
    row = db.execute(
        text(
            "SELECT status, created_at, responded_at FROM invitations WHERE invitation_id = :id"
        ),
        {"id": invitation},
    ).one()
    assert row.status == "PENDING"
    assert row.created_at.tzinfo is not None
    assert row.responded_at is None
    with pytest.raises(IntegrityError), db.begin_nested():
        invite(db, s["own"], s["guest"], s["organizer"])
    db.execute(
        text(
            "UPDATE invitations SET status = 'DECLINED', responded_at = CURRENT_TIMESTAMP "
            "WHERE invitation_id = :id"
        ),
        {"id": invitation},
    )
    assert invite(db, s["own"], s["guest"], s["organizer"]) != invitation


@pytest.mark.parametrize(
    "assignment",
    [
        "status = 'INVALID'",
        "status = 'ACCEPTED'",
        "status = 'DECLINED'",
        "responded_at = CURRENT_TIMESTAMP",
    ],
)
def test_invitation_response_consistency(db, scenario, assignment):
    s = scenario
    invitation = invite(db, s["own"], s["guest"], s["organizer"])
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(
            text(f"UPDATE invitations SET {assignment} WHERE invitation_id = :id"),
            {"id": invitation},
        )


def test_deleting_organizer_cascades_and_preserves_others_trips(db, scenario):
    s = scenario
    invite(db, s["own"], s["guest"], s["organizer"])
    invite(db, s["other"], s["organizer"], s["third"])
    invite(db, s["other"], s["guest"], s["organizer"])
    db.execute(text("DELETE FROM users WHERE user_id = :id"), {"id": s["organizer"]})
    assert (
        db.scalar(
            text("SELECT count(*) FROM trips WHERE trip_id = :id"), {"id": s["own"]}
        )
        == 0
    )
    assert (
        db.scalar(
            text("SELECT count(*) FROM trips WHERE trip_id = :id"), {"id": s["other"]}
        )
        == 1
    )
    assert (
        db.scalar(
            text("SELECT count(*) FROM trip_members WHERE trip_id = :id"),
            {"id": s["other"]},
        )
        == 1
    )
    assert (
        db.scalar(
            text("SELECT count(*) FROM invitations WHERE trip_id IN (:own, :other)"),
            s,
        )
        == 0
    )
