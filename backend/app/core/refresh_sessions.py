"""Opaque refresh credentials; Redis stores only their SHA-256 hashes.

A browser session keeps one random credential until logout/expiry. Renewing it is
atomic and extends the idle timeout, never the absolute session deadline. Keeping
that credential stable lets parallel browser requests refresh without races.
"""

import hashlib
import json
import re
import secrets
import time
from dataclasses import dataclass
from functools import lru_cache

from fastapi import Depends, HTTPException
from redis import Redis
from redis.backoff import NoBackoff
from redis.exceptions import RedisError, WatchError
from redis.retry import Retry

from backend.app.core.config import Settings, get_settings


@dataclass(frozen=True)
class RefreshGrant:
    user_id: int
    token: str
    max_age: int


@lru_cache(maxsize=8)
def redis_client(url: str, timeout: float) -> Redis:
    return Redis.from_url(
        url,
        decode_responses=True,
        socket_connect_timeout=timeout,
        socket_timeout=timeout,
        retry=Retry(NoBackoff(), 0),
    )


def unavailable() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail="Authentication service temporarily unavailable. Please retry.",
        headers={"Retry-After": "5"},
    )


class RefreshSessionStore:
    def __init__(self, client: Redis, settings: Settings):
        self.client = client
        self.settings = settings

    def key(self, token: str) -> str:
        return self.settings.redis_key_prefix + hashlib.sha256(token.encode()).hexdigest()

    def create(self, user_id: int) -> RefreshGrant:
        now = int(time.time())
        ttl = (
            min(self.settings.jwt_refresh_token_expire_days, self.settings.jwt_session_max_days)
            * 86400
        )
        value = json.dumps(
            {"user_id": user_id, "absolute_exp": now + self.settings.jwt_session_max_days * 86400}
        )
        try:
            for _ in range(3):
                token = secrets.token_urlsafe(48)
                if self.client.set(self.key(token), value, ex=ttl, nx=True):
                    return RefreshGrant(user_id, token, ttl)
        except RedisError:
            raise unavailable() from None
        raise unavailable()

    def renew(self, token: str) -> RefreshGrant:
        if not re.fullmatch(r"[A-Za-z0-9_-]{64}", token):
            raise HTTPException(status_code=401, detail="Invalid or expired refresh token.")
        key = self.key(token)
        try:
            # WATCH prevents logout/deletion between reading the session and
            # extending its TTL. EXPIRE never recreates a revoked session.
            for _ in range(5):
                with self.client.pipeline() as pipeline:
                    try:
                        pipeline.watch(key)
                        raw = pipeline.get(key)
                        if raw is None:
                            raise HTTPException(
                                status_code=401, detail="Invalid or expired refresh token."
                            )
                        try:
                            record = json.loads(raw)
                            user_id = int(record["user_id"])
                            remaining = int(record["absolute_exp"]) - int(time.time())
                            if not 0 < user_id <= 9223372036854775807 or remaining <= 0:
                                raise ValueError("Expired session")
                        except (ValueError, TypeError, KeyError) as exc:
                            raise HTTPException(
                                status_code=401, detail="Invalid or expired refresh token."
                            ) from exc
                        ttl = min(self.settings.jwt_refresh_token_expire_days * 86400, remaining)
                        pipeline.multi()
                        pipeline.expire(key, ttl)
                        if pipeline.execute()[0]:
                            return RefreshGrant(user_id, token, ttl)
                    except WatchError:
                        continue
        except RedisError:
            raise unavailable() from None
        raise unavailable()

    def revoke(self, token: str) -> None:
        if not token:
            return
        try:
            self.client.delete(self.key(token))
        except RedisError:
            raise unavailable() from None


def get_refresh_store(settings: Settings = Depends(get_settings)) -> RefreshSessionStore:
    return RefreshSessionStore(
        redis_client(settings.redis_url.get_secret_value(), settings.redis_timeout_seconds),
        settings,
    )
