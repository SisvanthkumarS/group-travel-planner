"""Real Redis checks; isolated keys only, never FLUSHDB/FLUSHALL."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi import HTTPException
from redis import Redis

from backend.app.core.config import Settings
from backend.app.core.refresh_sessions import RefreshSessionStore


@pytest.fixture
def store():
    url = os.environ.get("TEST_REDIS_URL")
    if not url:
        pytest.skip("TEST_REDIS_URL is required for real Redis integration tests")
    client = Redis.from_url(
        url, decode_responses=True, socket_connect_timeout=3, socket_timeout=3
    )
    settings = Settings(
        _env_file=None, redis_key_prefix="travel:test:refresh:" + uuid4().hex + ":"
    )
    instance = RefreshSessionStore(client, settings)
    try:
        assert client.ping()
        yield instance
    finally:
        keys = list(client.scan_iter(match=settings.redis_key_prefix + "*"))
        if keys:
            client.delete(*keys)
        client.close()


def test_real_redis_session_hash_ttl_and_revocation(store):
    grant = store.create(7)
    key = store.key(grant.token)
    assert grant.token not in key
    assert grant.token not in store.client.get(key)
    assert 0 < store.client.ttl(key) <= 7 * 86400
    store.client.expire(key, 30)
    assert store.renew(grant.token).user_id == 7
    assert store.client.ttl(key) > 30
    store.revoke(grant.token)
    with pytest.raises(HTTPException) as error:
        store.renew(grant.token)
    assert error.value.status_code == 401
    assert not store.client.exists(key)


def test_real_redis_concurrent_renew_and_absolute_expiry(store):
    grant = store.create(7)
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: store.renew(grant.token), range(4)))
    assert all(result.token == grant.token for result in results)
    key = store.key(grant.token)
    record = json.loads(store.client.get(key))
    record["absolute_exp"] = 1
    store.client.set(key, json.dumps(record), ex=30)
    with pytest.raises(HTTPException) as error:
        store.renew(grant.token)
    assert error.value.status_code == 401
