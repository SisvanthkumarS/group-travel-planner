from datetime import date
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from backend.app.repositories.TripRepository import TripRepository
from backend.app.schemas.trip import CreateTripRequest
from backend.app.services.TripService import TripService


def test_commit_failure_rolls_back_both_writes():
    session = Mock(spec=Session)
    service = TripService(session)
    service.repository = Mock(spec=TripRepository)

    def assign_trip_id(trip):
        trip.trip_id = 12
        return trip

    service.repository.add.side_effect = assign_trip_id
    session.commit.side_effect = RuntimeError("Commit failed")
    request = CreateTripRequest(
        name="NYC",
        destination="New York",
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 3),
    )
    with pytest.raises(RuntimeError, match="Commit failed"):
        service.create_trip(request, 7)
    session.commit.assert_called_once()
    session.rollback.assert_called_once()
    member = service.repository.add_member.call_args.args[0]
    assert (member.trip_id, member.user_id, member.role) == (12, 7, "ORGANIZER")
