import fakeredis
import pytest

from backend.app.core.config import Settings
from backend.app.core.refresh_sessions import RefreshSessionStore


@pytest.fixture
def refresh_store():
    return RefreshSessionStore(
        fakeredis.FakeRedis(decode_responses=True), Settings(_env_file=None)
    )
