from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import HTTPException, status
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash

from backend.app.core.config import get_settings

password_hasher = PasswordHash.recommended()


def hash_password(plain_password: str) -> str:
    return password_hasher.hash(plain_password)


def verify_password(plain_password: str, stored_hash: str) -> bool:
    return password_hasher.verify(plain_password, stored_hash)


def create_access_token(user_id: int, *, max_age_seconds: int | None = None) -> str:
    settings = get_settings()
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET must be configured.")
    if user_id <= 0:
        raise ValueError("user_id must be positive.")
    now = datetime.now(UTC)
    lifetime = settings.jwt_access_token_expire_minutes * 60
    if max_age_seconds is not None:
        if max_age_seconds <= 0:
            raise ValueError("Token lifetime must be positive.")
        lifetime = min(lifetime, max_age_seconds)
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(seconds=lifetime),
            "token_type": "access",
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def parse_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET must be configured.")
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "iat", "exp", "token_type"]},
        )
        if not payload["sub"].isascii() or not payload["sub"].isdigit():
            raise ValueError("Invalid token subject.")
        if not 0 < int(payload["sub"]) <= 9223372036854775807:
            raise ValueError("Invalid token subject.")
        if payload["token_type"] != "access":
            raise ValueError("Invalid token type.")
        return payload
    except (InvalidTokenError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
        ) from exc
