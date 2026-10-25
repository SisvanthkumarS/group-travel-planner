from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.repositories.TripRepository import TripRepository
from backend.app.schemas.trip import CreateTripRequest, TripDetailResponse, TripResponse


class TripService:
    """Trip business rules and transaction boundaries, ready for implementation."""

    def __init__(self, session: Session):
        self.session = session
        self.repository = TripRepository(session)
        # The JWT filter's user lookup already opens a transaction in this Session.
        # For writes, commit once on success and rollback on failure. Do not start
        # another session.begin() around an already-active transaction.

    def create_trip(self, request: CreateTripRequest, current_user_id: int) -> TripResponse:
        # TODO: create Trip with organizer_id=current_user_id, then add its
        # ORGANIZER membership. Commit both writes together; rollback on failure.
        # Return TripResponse.model_validate(trip), loaded before commit or refreshed.
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Trip creation business logic is not implemented yet.",
        )

    def list_trips(self, current_user_id: int) -> list[TripResponse]:
        # TODO: query repository.list_for_user and map results to TripResponse.
        # Return [] when the authenticated user has no accessible trips.
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Trip listing business logic is not implemented yet.",
        )

    def get_trip(self, trip_id: int, current_user_id: int) -> TripDetailResponse:
        # TODO: find trip (404 if absent), verify membership (403 if not a member),
        # load members with users, and build TripDetailResponse with the member list.
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Trip details business logic is not implemented yet.",
        )

    def delete_trip(self, trip_id: int, current_user_id: int) -> None:
        # TODO: find trip (404 if absent); require organizer_id=current_user_id
        # (otherwise 403). Delete it and commit; rollback on failure. Existing
        # foreign-key cascades remove memberships/invitations. Include planning
        # records when their models and deletion rules are implemented.
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Trip deletion business logic is not implemented yet.",
        )
