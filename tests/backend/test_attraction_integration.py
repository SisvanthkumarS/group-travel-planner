"""Curated attractions and attraction-based proposals against PostgreSQL."""

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import sessionmaker

from backend.app.core import filter as authentication
from backend.app.core import security
from backend.app.core.config import Settings
from backend.app.core.database import get_session
from backend.app.main import app
from backend.app.main import settings as app_settings
from backend.app.models import Attraction, Proposal, Trip, TripMember, User
from backend.app.schemas.attraction import AttractionSeedFile
from backend.app.services.AttractionService import AttractionService


@pytest.fixture
def s(monkeypatch):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(url)
    factory = sessionmaker(engine, autoflush=False)
    now = datetime.now(UTC)
    city = f"Test City {uuid4().hex[:8]}"
    with factory() as session:
        user = User(
            user_name=uuid4().hex[:20],
            email=f"{uuid4()}@example.com",
            password_hash="unused",
        )
        session.add(user)
        session.flush()
        user_id = user.user_id
        trip = Trip(
            name="Attraction test",
            destination=city,
            start_date=now.date(),
            end_date=(now + timedelta(days=10)).date(),
            organizer_id=user_id,
        )
        session.add(trip)
        session.flush()
        trip_id = trip.trip_id
        session.add(TripMember(trip_id=trip_id, user_id=user_id, role="ORGANIZER"))
        session.commit()
    settings = Settings(_env_file=None, jwt_secret="attraction-tests-" * 8)
    monkeypatch.setattr(authentication, "get_settings", lambda: settings)
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    monkeypatch.setattr(app_settings, "poll_scheduler_enabled", False)

    def sessions():
        with factory() as session:
            yield session

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_session] = sessions
    starts = now + timedelta(days=2)
    data = {
        "factory": factory,
        "trip": trip_id,
        "city": city,
        "times": {
            "starts_at": starts.isoformat(),
            "ends_at": (starts + timedelta(hours=2)).isoformat(),
        },
    }
    try:
        with TestClient(
            app, raise_server_exceptions=False, headers={"X-CSRF-Protection": "1"}
        ) as client:
            client.cookies.set("access_token", security.create_access_token(user_id))
            data["client"] = client
            yield data
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        with engine.begin() as connection:
            connection.execute(delete(Trip).where(Trip.trip_id == trip_id))
            connection.execute(delete(Attraction).where(Attraction.city == city))
            connection.execute(delete(User).where(User.user_id == user_id))
        engine.dispose()


def entry(s, **changes):
    return {
        "name": "Harbor Tower",
        "city": s["city"],
        "latitude": 40.7,
        "longitude": -74.0,
        "summary": "Observation deck above the harbor.",
        "description": "Long introduction.",
        "suggested_duration_minutes": 90,
        "typical_cost": "42.50",
        "currency": "usd",
        "category": "Landmark",
    } | changes


def seed(s, *entries):
    with s["factory"]() as session:
        return AttractionService(session).seed(
            AttractionSeedFile(attractions=list(entries))
        )


def attraction_id(s, name):
    with s["factory"]() as session:
        return session.scalar(
            select(Attraction.attraction_id).where(
                Attraction.city == s["city"],
                func.lower(Attraction.name) == name.lower(),
            )
        )


def create_attraction(s, **changes):
    body = entry(s, **changes)
    seed(s, body)
    return attraction_id(s, body["name"])


def update_attraction(s, attraction_id, **values):
    with s["factory"]() as session:
        attraction = session.get(Attraction, attraction_id)
        for field, value in values.items():
            setattr(attraction, field, value)
        session.commit()


def propose(s, body):
    return s["client"].post(
        f"/api/v1/trips/{s['trip']}/proposals", json=s["times"] | body
    )


def test_attraction_routes_require_login_and_admin_routes_are_gone(s):
    client = s["client"]
    assert client.get("/api/v1/admin/attractions").status_code == 404
    client.cookies.clear()
    assert client.get("/api/v1/attractions").status_code == 401
    assert client.get("/api/v1/attractions/1").status_code == 401


def test_seed_upserts_by_name_and_city_and_hides_inactive(s):
    first = seed(s, entry(s))
    assert (first.created, first.updated) == (1, 0)
    existing = attraction_id(s, "Harbor Tower")

    second = seed(
        s,
        entry(s, name="HARBOR tower", summary="Updated by seed"),
        entry(s, name="River Walk", latitude=40.71, longitude=-74.01),
    )
    assert (second.created, second.updated) == (1, 1)
    detail = s["client"].get(f"/api/v1/attractions/{existing}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["summary"] == "Updated by seed"
    assert detail.json()["currency"] == "USD"
    assert detail.json()["typical_cost"] == "42.50"
    assert "is_active" not in detail.json()

    seed(s, entry(s, is_active=False))
    assert s["client"].get(f"/api/v1/attractions/{existing}").status_code == 404
    listed = s["client"].get("/api/v1/attractions", params={"city": s["city"]})
    assert [row["name"] for row in listed.json()] == ["River Walk"]

    with pytest.raises(ValueError, match="duplicates entry 0"):
        seed(s, entry(s), entry(s, name=" harbor tower "))


def test_map_bounds_search_and_limits(s):
    inside = create_attraction(s, name="Inside", latitude=10.0, longitude=20.0)
    create_attraction(s, name="Outside", latitude=30.0, longitude=20.0)
    dateline = create_attraction(s, name="Dateline 100%", latitude=0.0, longitude=179.5)
    get = s["client"].get

    bounded = get(
        "/api/v1/attractions",
        params={
            "min_lat": 5,
            "max_lat": 15,
            "min_lng": 15,
            "max_lng": 25,
            "city": s["city"],
        },
    )
    assert bounded.status_code == 200
    assert [row["attraction_id"] for row in bounded.json()] == [inside]
    assert set(bounded.json()[0]) == {
        "attraction_id",
        "name",
        "latitude",
        "longitude",
        "category",
        "city",
        "summary",
    }

    crossing = get(
        "/api/v1/attractions",
        params={
            "min_lat": -5,
            "max_lat": 5,
            "min_lng": 170,
            "max_lng": -170,
            "city": s["city"],
        },
    )
    assert [row["attraction_id"] for row in crossing.json()] == [dateline]

    assert get("/api/v1/attractions", params={"min_lat": 1}).status_code == 422
    inverted = {"min_lat": 5, "max_lat": 1, "min_lng": 0, "max_lng": 1}
    assert get("/api/v1/attractions", params=inverted).status_code == 422
    assert get("/api/v1/attractions", params={"limit": 201}).status_code == 422

    searched = get("/api/v1/attractions", params={"q": "100%", "city": s["city"]})
    assert [row["name"] for row in searched.json()] == ["Dateline 100%"]
    wildcard = get("/api/v1/attractions", params={"q": "%", "city": s["city"]})
    assert [row["name"] for row in wildcard.json()] == ["Dateline 100%"]
    limited = get("/api/v1/attractions", params={"city": s["city"], "limit": 2})
    assert [row["name"] for row in limited.json()] == ["Dateline 100%", "Inside"]


def test_proposal_from_attraction_uses_defaults_and_snapshots_coordinates(s):
    attraction = create_attraction(s)
    response = propose(s, {"attraction_id": attraction})
    assert response.status_code == 201, response.text
    proposal = response.json()
    assert proposal["attraction_id"] == attraction
    assert proposal["title"] == "Harbor Tower"
    assert proposal["location"] == "Harbor Tower"
    assert proposal["description"] == "Observation deck above the harbor."
    assert proposal["estimated_cost"] == "42.50"
    assert (proposal["latitude"], proposal["longitude"]) == (40.7, -74.0)

    custom = propose(
        s,
        {
            "attraction_id": attraction,
            "location": "Harbor Tower",
            "title": "Sunset at the tower",
            "description": "Go before dinner",
            "estimated_cost": "0",
        },
    )
    assert custom.status_code == 201, custom.text
    assert custom.json()["title"] == "Sunset at the tower"
    assert custom.json()["estimated_cost"] == "0"

    update_attraction(s, attraction, latitude=1.0, longitude=2.0)
    with s["factory"]() as session:
        saved = session.get(Proposal, proposal["proposal_id"])
        assert (saved.latitude, saved.longitude) == (40.7, -74.0)


def test_attraction_without_typical_cost_defaults_to_zero(s):
    attraction = create_attraction(s, typical_cost=None)
    response = propose(s, {"attraction_id": attraction})
    assert response.status_code == 201, response.text
    assert response.json()["estimated_cost"] == "0"


@pytest.mark.parametrize(
    "changes,field",
    [
        ({"location": "Somewhere else"}, "location"),
        ({"latitude": 1.0, "longitude": 2.0}, None),
        ({"attraction_id": 9223372036854775807}, "attraction_id"),
    ],
)
def test_attraction_proposal_rejects_conflicting_input(s, changes, field):
    attraction = create_attraction(s)
    response = propose(s, {"attraction_id": attraction} | changes)
    assert response.status_code == 422, response.text
    if field:
        assert response.json()["detail"][0]["loc"] == ["body", field]
    with s["factory"]() as session:
        assert (
            session.scalars(select(Proposal).where(Proposal.trip_id == s["trip"])).all()
            == []
        )


def test_hidden_attraction_cannot_be_proposed(s):
    attraction = create_attraction(s, is_active=False)
    response = propose(s, {"attraction_id": attraction})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "attraction_id"]


def test_custom_place_requires_details_and_accepts_optional_pin(s):
    details = {
        "title": "Picnic",
        "description": "Bring snacks",
        "estimated_cost": "5",
        "location": "Riverside lawn",
    }
    for field in details:
        missing = propose(
            s, {key: value for key, value in details.items() if key != field}
        )
        assert missing.status_code == 422, field
        assert missing.json()["detail"][0]["loc"] == ["body", field]

    named = propose(s, details)
    assert named.status_code == 201, named.text
    assert (named.json()["latitude"], named.json()["attraction_id"]) == (None, None)

    pinned = propose(s, details | {"latitude": 0.0, "longitude": 0.0})
    assert pinned.status_code == 201, pinned.text
    assert (pinned.json()["latitude"], pinned.json()["longitude"]) == (0.0, 0.0)
    assert pinned.json()["attraction_id"] is None
