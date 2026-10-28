from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.trip import Trip
from backend.app.models.trip_member import TripMember
from backend.app.models.user import User


class TripRepository:
    """Database operations only; the Service owns commit and rollback."""

    def __init__(self, session: Session):
        self.session = session

    def add(self, trip: Trip) -> Trip:
        self.session.add(trip)
        self.session.flush()
        return trip

    def add_member(self, member: TripMember) -> TripMember:
        self.session.add(member)
        self.session.flush()
        return member

    def list_for_user(self, user_id: int) -> list[Trip]:
        statement = (
            select(Trip)
            .join(TripMember, Trip.trip_id == TripMember.trip_id)
            .where(TripMember.user_id == user_id)
            .order_by(Trip.start_date, Trip.trip_id)
        )
        return list(self.session.scalars(statement).all())

    def find_by_id(self, trip_id: int) -> Trip | None:
        return self.session.get(Trip, trip_id)

    def find_membership(self, trip_id: int, user_id: int) -> TripMember | None:
        statement = select(TripMember).where(
            TripMember.trip_id == trip_id,
            TripMember.user_id == user_id,
        )
        return self.session.scalar(statement)

    def list_members_with_users(self, trip_id: int) -> list[tuple[TripMember, User]]:
        statement = (
            select(TripMember, User)
            .join(User, TripMember.user_id == User.user_id)
            .where(TripMember.trip_id == trip_id)
            .order_by(TripMember.joined_at, TripMember.user_id)
        )
        return [(member, user) for member, user in self.session.execute(statement)]

    def delete(self, trip: Trip) -> None:
        # The Service commits; database cascades delete members and invitations.
        self.session.delete(trip)
        self.session.flush()
