from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app, headers={"X-CSRF-Protection": "1"})


def test_documentation_and_api_contract():
    schema = client.get("/api/v1/openapi.json")
    assert schema.status_code == 200
    assert set(schema.json()["paths"]) == {
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
        "/api/v1/auth/refresh",
        "/api/v1/notifications/test-email",
        "/api/v1/trips",
        "/api/v1/trips/{trip_id}",
        "/api/v1/trips/{trip_id}/invitations",
        "/api/v1/invitations",
        "/api/v1/trips/{trip_id}/proposals",
        "/api/v1/proposals/{proposal_id}/withdraw",
        "/api/v1/proposals/{proposal_id}/poll",
        "/api/v1/polls/{poll_id}/vote",
        "/api/v1/polls/{poll_id}/resolve",
        "/api/v1/trips/{trip_id}/itinerary",
        "/api/v1/trips/{trip_id}/itinerary/{item_id}",
    }
    assert client.get("/docs").status_code == 200


def test_allowed_cors_origin():
    response = client.options(
        "/api/v1/openapi.json",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_untrusted_cors_origin():
    response = client.options(
        "/api/v1/openapi.json",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
