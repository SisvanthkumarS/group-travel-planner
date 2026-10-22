from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_documentation_and_empty_contract():
    schema = client.get("/api/v1/openapi.json")
    assert schema.status_code == 200
    assert schema.json()["paths"] == {}
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
