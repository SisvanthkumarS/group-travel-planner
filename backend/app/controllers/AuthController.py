from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from backend.app.core.config import Settings, get_settings
from backend.app.core.database import get_session
from backend.app.schemas.auth import LoginRequest, RegisterRequest, UserResponse
from backend.app.services.AuthService import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


def get_auth_service(session: Annotated[Session, Depends(get_session)]) -> AuthService:
    return AuthService(session)


AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]


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
    responses={401: {"description": "Invalid login credentials."}},
)
def login(
    request: LoginRequest,
    response: Response,
    service: AuthServiceDependency,
    settings: SettingsDependency,
) -> UserResponse:
    """Sign in with email or a unique username and set an HttpOnly JWT cookie."""
    result = service.login(request)
    response.set_cookie(
        key=settings.jwt_cookie_name,
        value=result.access_token,
        httponly=True,
        secure=settings.jwt_cookie_secure,
        samesite="lax",
        max_age=settings.jwt_access_token_expire_minutes * 60,
        path="/",
    )
    return result.user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(settings: SettingsDependency) -> Response:
    """Clear the browser cookie; a previously issued JWT is not revoked server-side."""
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    # Cookie name, path and domain must match the cookie set during login.
    response.delete_cookie(
        key=settings.jwt_cookie_name,
        path="/",
        httponly=True,
        secure=settings.jwt_cookie_secure,
        samesite="lax",
    )
    return response
