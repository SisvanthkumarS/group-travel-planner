import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.core.csrf import CSRFMiddleware
from backend.app.main import app


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("header", [None, "", "wrong"])
def test_unsafe_requests_require_csrf_header(method, header):
    headers = {} if header is None else {"X-CSRF-Protection": header}
    with TestClient(app) as client:
        response = client.request(method, "/api/v1/trips", headers=headers)
    assert response.status_code == 403
    assert response.json() == {"detail": "CSRF validation failed."}


@pytest.mark.parametrize("action", ["login", "register", "logout"])
def test_public_auth_routes_are_protected(action):
    with TestClient(app) as client:
        response = client.post(f"/api/v1/auth/{action}", data={"password": "example"})
    assert response.status_code == 403
    assert "set-cookie" not in response.headers


@pytest.mark.parametrize(
    "origin", ["https://evil.example", "null", "http://localhost:5173.evil.example"]
)
def test_untrusted_origin_is_rejected_even_with_header(origin):
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/logout",
            headers={"Origin": origin, "X-CSRF-Protection": "1"},
        )
    assert response.status_code == 403
    assert "set-cookie" not in response.headers


@pytest.mark.parametrize("origin", [None, "http://localhost:5173"])
def test_valid_request_reaches_handler(origin):
    headers = {"X-CSRF-Protection": "1"}
    if origin:
        headers["Origin"] = origin
    with TestClient(app) as client:
        response = client.post("/api/v1/auth/logout", headers=headers)
    assert response.status_code == 204


def test_cors_preflight_allows_csrf_header_only_for_trusted_origin():
    with TestClient(app) as client:
        for origin, expected in [
            ("http://localhost:5173", 200),
            ("https://evil.example", 400),
        ]:
            response = client.options(
                "/api/v1/auth/logout",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "X-CSRF-Protection, Content-Type",
                },
            )
            assert response.status_code == expected


def test_safe_requests_and_csrf_errors_keep_cors_headers():
    with TestClient(app) as client:
        assert client.get("/api/v1/openapi.json").status_code == 200
        response = client.post(
            "/api/v1/auth/logout", headers={"Origin": "http://localhost:5173"}
        )
    assert response.status_code == 403
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


@pytest.mark.parametrize("origin", ["*", "null"])
def test_insecure_origin_configuration_is_rejected(origin):
    with pytest.raises(ValueError, match="explicit trusted"):
        CSRFMiddleware(FastAPI(), allowed_origins=[origin])
