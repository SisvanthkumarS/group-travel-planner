from sqlalchemy.orm import Session

from backend.app.models.trip import Trip
from backend.app.models.trip_member import TripMember
from backend.app.models.user import User


class TripRepository:
    """Database operations only; the Service owns commit and rollback."""

    def __init__(self, session: Session):
        self.session = session

    def add(self, trip: Trip) -> Trip:
        # TODO: session.add + flush, obtaining trip_id without committing.
        raise NotImplementedError("Implement inserting a trip.")

    def add_member(self, member: TripMember) -> TripMember:
        # TODO: add and flush the membership in the same transaction as the trip.
        raise NotImplementedError("Implement inserting a trip member.")

    def list_for_user(self, user_id: int) -> list[Trip]:
        # TODO: join trips and trip_members; only return this user's trips.
        raise NotImplementedError("Implement listing accessible trips.")

    def find_by_id(self, trip_id: int) -> Trip | None:
        raise NotImplementedError("Implement finding a trip by primary key.")

    def find_membership(self, trip_id: int, user_id: int) -> TripMember | None:
        raise NotImplementedError("Implement finding a user's trip membership.")

    def list_members_with_users(self, trip_id: int) -> list[tuple[TripMember, User]]:
        # TODO: join trip_members and users; Service maps results to response DTOs.
        raise NotImplementedError("Implement listing trip members with user details.")

    def delete(self, trip: Trip) -> None:
        # TODO: delete and flush; existing database cascades remove members/invites.
        raise NotImplementedError("Implement deleting a trip.")
