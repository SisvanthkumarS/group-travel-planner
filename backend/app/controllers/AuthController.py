from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.app.core.auth_cookies import clear_auth_cookies, set_auth_cookies
from backend.app.core.config import Settings, get_settings
from backend.app.core.database import get_session
from backend.app.core.refresh_sessions import RefreshSessionStore, get_refresh_store
from backend.app.schemas.auth import LoginRequest, RegisterRequest, UserResponse
from backend.app.services.AuthService import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


def get_auth_service(
    session: Annotated[Session, Depends(get_session)],
    store: Annotated[RefreshSessionStore, Depends(get_refresh_store)],
) -> AuthService:
    return AuthService(session, store)


AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
RefreshStoreDependency = Annotated[RefreshSessionStore, Depends(get_refresh_store)]


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "Email or username is already registered."}},
)
def register(request: RegisterRequest, service: AuthServiceDependency) -> UserResponse:
    return service.register(request)


@router.post(
    "/login",
    response_model=UserResponse,
    responses={
        401: {"description": "Invalid login credentials."},
        503: {"description": "Redis authentication storage unavailable."},
    },
)
def login(
    request: LoginRequest,
    response: Response,
    service: AuthServiceDependency,
    settings: SettingsDependency,
) -> UserResponse:
    """Set an access JWT and a Redis-backed opaque refresh credential in HttpOnly cookies."""
    result = service.login(request)
    set_auth_cookies(
        response, result.access_token, result.refresh_token, result.refresh_token_max_age, settings
    )
    return result.user


@router.post(
    "/refresh",
    response_model=UserResponse,
    responses={
        401: {"description": "Refresh credential absent, invalid, revoked or expired."},
        503: {"description": "Redis authentication storage unavailable."},
    },
)
def refresh(
    request: Request,
    response: Response,
    service: AuthServiceDependency,
    settings: SettingsDependency,
) -> UserResponse:
    """Renew the access token and sliding session using the refresh cookie; no body required."""
    result = service.refresh(request.cookies.get(settings.jwt_refresh_cookie_name, ""))
    set_auth_cookies(
        response, result.access_token, result.refresh_token, result.refresh_token_max_age, settings
    )
    return result.user


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={503: {"description": "Cookies cleared but Redis revocation failed."}},
)
def logout(
    request: Request, settings: SettingsDependency, store: RefreshStoreDependency
) -> Response:
    """Revoke this browser's refresh session and clear both authentication cookies."""
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    try:
        store.revoke(request.cookies.get(settings.jwt_refresh_cookie_name, ""))
    except HTTPException as error:
        response = JSONResponse(
            status_code=error.status_code, content={"detail": error.detail}, headers=error.headers
        )
    clear_auth_cookies(response, settings)
    return response
