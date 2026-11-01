import asyncio
import logging
from datetime import UTC, datetime

from backend.app.core.database import SessionLocal
from backend.app.repositories.ActivityRepository import ActivityRepository
from backend.app.services.ActivityService import ActivityService

logger = logging.getLogger(__name__)


def close_due_polls(session_factory=SessionLocal):
    """Recover overdue polls after restart; each trip commits independently."""
    with session_factory() as session:
        trip_ids = ActivityRepository(session).due_trip_ids(datetime.now(UTC))
    closed = 0
    for trip_id in trip_ids:
        try:
            with session_factory() as session:
                closed += ActivityService(session).close_due_for_trip(trip_id)
        except Exception:
            logger.exception("Could not close due polls for trip %s; will retry next scan", trip_id)
    return closed


async def run_poll_scheduler(stop: asyncio.Event, interval: float):
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
            return
        except TimeoutError:
            pass
        try:
            await asyncio.to_thread(close_due_polls)
        except Exception:
            logger.exception("Poll deadline scan failed; will retry next scan")
