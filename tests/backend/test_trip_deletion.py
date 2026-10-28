from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.app.models import Trip
from backend.app.repositories.TripRepository import TripRepository
from backend.app.services.TripService import TripService


@pytest.mark.parametrize("case, expected", [("missing", 404), ("not-organizer", 403)])
def test_rejected_deletion_does_not_write(case, expected):
    session = Mock(spec=Session)
    service = TripService(session)
    service.repository = Mock(spec=TripRepository)
    service.repository.find_by_id.return_value = (
        None if case == "missing" else Trip(organizer_id=8)
    )
    with pytest.raises(HTTPException) as error:
        service.delete_trip(12, 7)
    assert error.value.status_code == expected
    service.repository.delete.assert_not_called()
    session.commit.assert_not_called()
    session.rollback.assert_called_once()


def test_delete_commit_failure_rolls_back():
    session = Mock(spec=Session)
    session.commit.side_effect = RuntimeError("Commit failed")
    service = TripService(session)
    service.repository = Mock(spec=TripRepository)
    trip = Trip(trip_id=12, organizer_id=7)
    service.repository.find_by_id.return_value = trip
    with pytest.raises(RuntimeError, match="Commit failed"):
        service.delete_trip(12, 7)
    service.repository.delete.assert_called_once_with(trip)
    session.rollback.assert_called_once()
