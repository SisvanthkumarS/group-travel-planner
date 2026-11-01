from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models.trip import Trip
from backend.app.models.trip_member import TripMember


class TripInvitationRepository:
    """Trip locking and member counts used by the invitation acceptance flow."""

    def __init__(self, session: Session):
        self.session = session

    def find_trip_for_update(self, trip_id: int) -> Trip | None:
        statement = (
            select(Trip)
            .where(Trip.trip_id == trip_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return self.session.scalar(statement)

    def count_members(self, trip_id: int) -> int:
        statement = (
            select(func.count()).select_from(TripMember).where(TripMember.trip_id == trip_id)
        )
        return self.session.scalar(statement)
