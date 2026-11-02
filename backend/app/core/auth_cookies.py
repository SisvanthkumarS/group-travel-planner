from fastapi import Response

from backend.app.core.config import Settings


def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
    refresh_max_age: int,
    settings: Settings,
) -> None:
    common = {
        "httponly": True,
        "secure": settings.jwt_cookie_secure,
        "samesite": "lax",
        "path": "/",
    }
    response.set_cookie(
        settings.jwt_cookie_name,
        access_token,
        max_age=min(settings.jwt_access_token_expire_minutes * 60, refresh_max_age),
        **common,
    )
    # Path=/ is needed because business endpoints also perform automatic refresh.
    response.set_cookie(
        settings.jwt_refresh_cookie_name, refresh_token, max_age=refresh_max_age, **common
    )
    response.headers["Cache-Control"] = "no-store"


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    for name in (settings.jwt_cookie_name, settings.jwt_refresh_cookie_name):
        response.delete_cookie(
            name, path="/", httponly=True, secure=settings.jwt_cookie_secure, samesite="lax"
        )
    response.headers["Cache-Control"] = "no-store"


class AuthenticationCookiesMiddleware:
    """Attach renewal cookies even to explicit Responses and HTTP error responses."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_with_cookies(message):
            renewed = scope.get("state", {}).get("renewed_authentication")
            if message["type"] == "http.response.start" and renewed:
                access, grant, settings = renewed
                response = Response()
                set_auth_cookies(response, access, grant.token, grant.max_age, settings)
                headers = [
                    (key, value) for key, value in message["headers"] if key != b"cache-control"
                ]
                headers.extend(
                    (key, value)
                    for key, value in response.raw_headers
                    if key in (b"set-cookie", b"cache-control")
                )
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_cookies)
