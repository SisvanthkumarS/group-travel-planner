from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.security import create_access_token, hash_password, verify_password
from backend.app.models.user import User
from backend.app.repositories.AuthRepository import AuthRepository
from backend.app.schemas.auth import LoginRequest, RegisterRequest, UserResponse


@dataclass(frozen=True)
class LoginResult:
    user: UserResponse
    access_token: str


class AuthService:
    def __init__(self, session: Session):
        self.session = session
        self.repository = AuthRepository(session)

    def register(self, request: RegisterRequest) -> UserResponse:
        email = request.email.strip().lower()

        try:
            with self.session.begin():
                existing_user = self.repository.find_by_email(email)
                if existing_user is not None:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Email is already registered.",
                    )
                if self.repository.find_by_user_name(request.user_name) is not None:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Username is already registered.",
                    )
                user = User(
                    user_name=request.user_name,
                    email=email,
                    password_hash=hash_password(request.password.get_secret_value()),
                )
                saved_user = self.repository.add(user)

                response = UserResponse.model_validate(saved_user)

            return response

        except IntegrityError as exc:
            constraint = getattr(
                getattr(exc.orig, "diag", None),
                "constraint_name",
                None,
            )

            conflicts = {
                "uq_users_email_lower": "Email is already registered.",
                "uq_users_user_name": "Username is already registered.",
            }
            if constraint in conflicts:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=conflicts[constraint],
                ) from exc

            raise

    def login(self, request: LoginRequest) -> LoginResult:
        if request.email is not None:
            user = self.repository.find_by_email(request.email)
        else:
            user = self.repository.find_by_user_name(request.user_name)

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid login credentials.",
            )
        if not verify_password(request.password.get_secret_value(), user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid login credentials.",
            )

        return LoginResult(
            user=UserResponse.model_validate(user),
            access_token=create_access_token(user.user_id),
        )
