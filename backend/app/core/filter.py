from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.database import get_session
from backend.app.core.security import parse_access_token
from backend.app.models.user import User

PUBLIC_ROUTES = {
    ("POST", "/api/v1/auth/register"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/logout"),
}


def require_authentication(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> None:

    if (request.method, request.url.path) in PUBLIC_ROUTES:
        return
    settings = get_settings()
    token = request.cookies.get(settings.jwt_cookie_name)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    payload = parse_access_token(token)
    user = session.get(User, int(payload["sub"]))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    request.state.current_user = user
