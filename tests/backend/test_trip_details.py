from datetime import UTC, date, datetime
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.app.models import Trip, TripMember, User
from backend.app.repositories.TripRepository import TripRepository
from backend.app.services.TripService import TripService


def test_details_maps_all_fields_without_committing():
    session = Mock(spec=Session)
    service = TripService(session)
    service.repository = Mock(spec=TripRepository)
    service.repository.find_by_id.return_value = Trip(
        trip_id=12,
        name="NYC",
        destination="New York",
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 3),
        organizer_id=7,
    )
    member = TripMember(
        trip_id=12, user_id=7, role="ORGANIZER", joined_at=datetime.now(UTC)
    )
    service.repository.find_membership.return_value = member
    service.repository.list_members_with_users.return_value = [
        (member, User(user_id=7, user_name="KC"))
    ]
    result = service.get_trip(12, 7)
    assert result.trip_id == 12 and result.destination == "New York"
    assert result.members[0].user_name == "KC"
    service.repository.find_membership.assert_called_once_with(12, 7)
    session.commit.assert_not_called()
    session.flush.assert_not_called()


@pytest.mark.parametrize("trip_exists, expected", [(False, 404), (True, 403)])
def test_unauthorized_details_never_load_member_list(trip_exists, expected):
    service = TripService(Mock(spec=Session))
    service.repository = Mock(spec=TripRepository)
    service.repository.find_by_id.return_value = (
        Trip(trip_id=12) if trip_exists else None
    )
    service.repository.find_membership.return_value = None
    with pytest.raises(HTTPException) as error:
        service.get_trip(12, 7)
    assert error.value.status_code == expected
    service.repository.list_members_with_users.assert_not_called()
