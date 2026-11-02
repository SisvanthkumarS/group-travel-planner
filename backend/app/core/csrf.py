from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class CSRFMiddleware:
    """Require a non-simple header that browsers can only send after CORS approval."""

    def __init__(self, app: ASGIApp, allowed_origins: list[str]) -> None:
        self.app = app
        self.allowed_origins = frozenset(allowed_origins)
        if self.allowed_origins.intersection({"*", "null"}):
            raise ValueError("CSRF protection requires explicit trusted CORS origins.")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] not in SAFE_METHODS:
            headers = Headers(scope=scope)
            origin = headers.get("origin")
            if headers.get("x-csrf-protection") != "1" or (
                origin is not None and origin not in self.allowed_origins
            ):
                response = JSONResponse({"detail": "CSRF validation failed."}, status_code=403)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
