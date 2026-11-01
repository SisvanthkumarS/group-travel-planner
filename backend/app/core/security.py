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


def create_access_token(user_id: int) -> str:
    settings = get_settings()
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET must be configured.")
    if user_id <= 0:
        raise ValueError("user_id must be positive.")
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
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
            options={"require": ["sub", "iat", "exp"]},
        )
        if not payload["sub"].isascii() or not payload["sub"].isdigit():
            raise ValueError("Invalid token subject.")
        if int(payload["sub"]) <= 0:
            raise ValueError("Invalid token subject.")
        return payload
    except (InvalidTokenError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
        ) from exc
