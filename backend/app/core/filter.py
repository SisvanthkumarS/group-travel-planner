import time
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.database import get_session
from backend.app.core.refresh_sessions import RefreshGrant, RefreshSessionStore, get_refresh_store
from backend.app.core.security import parse_access_token
from backend.app.models.user import User
from backend.app.services.AuthService import AuthService

PUBLIC_ROUTES = {
    ("POST", "/api/v1/auth/register"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/logout"),
    ("POST", "/api/v1/auth/refresh"),
}


def require_authentication(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    store: Annotated[RefreshSessionStore, Depends(get_refresh_store)],
) -> None:
    if (request.method, request.url.path) in PUBLIC_ROUTES:
        return
    settings = get_settings()
    token = request.cookies.get(settings.jwt_cookie_name)
    refresh_token = request.cookies.get(settings.jwt_refresh_cookie_name)
    payload = None
    if token:
        try:
            payload = parse_access_token(token)
        except HTTPException:
            if not refresh_token:
                raise
    if payload is not None:
        user = session.get(User, int(payload["sub"]))
        if user is None:
            raise HTTPException(status_code=401, detail="Authentication required.")
        request.state.current_user = user
        # Redis outages must not invalidate an otherwise valid access JWT.
        if not refresh_token or payload["exp"] - time.time() > settings.jwt_refresh_window_seconds:
            return
        try:
            result = AuthService(session, store).refresh(refresh_token)
        except HTTPException as error:
            if error.status_code in (401, 503):
                return
            raise
        if result.user.user_id != user.user_id:
            return
    else:
        if not refresh_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required."
            )
        result = AuthService(session, store).refresh(refresh_token)
        request.state.current_user = session.get(User, result.user.user_id)

    # The middleware attaches cookies even if the controller returns an explicit
    # Response (e.g. DELETE's 204) or raises an HTTPException after authentication.
    request.state.renewed_authentication = (
        result.access_token,
        RefreshGrant(result.user.user_id, result.refresh_token, result.refresh_token_max_age),
        settings,
    )
