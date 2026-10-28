from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.models import TripMember
from backend.app.models.trip import Trip
from backend.app.repositories.TripRepository import TripRepository
from backend.app.schemas.trip import (
    CreateTripRequest,
    TripDetailResponse,
    TripMemberResponse,
    TripResponse,
)


class TripService:
    """Trip business rules and transaction boundaries, ready for implementation."""

    def __init__(self, session: Session):
        self.session = session
        self.repository = TripRepository(session)
        # The JWT filter's user lookup already opens a transaction in this Session.
        # For writes, commit once on success and rollback on failure. Do not start
        # another session.begin() around an already-active transaction.

    def create_trip(self, request: CreateTripRequest, current_user_id: int) -> TripResponse:
        try:
            trip = Trip(
                name=request.name,
                destination=request.destination,
                start_date=request.start_date,
                end_date=request.end_date,
                organizer_id=current_user_id,
            )
            created_trip = self.repository.add(trip)
            trip_member = TripMember(
                trip_id=created_trip.trip_id,
                user_id=current_user_id,
                role="ORGANIZER",
            )
            self.repository.add_member(trip_member)

            # Build the DTO before commit expires the ORM object's attributes.
            response = TripResponse.model_validate(created_trip)
            self.session.commit()  # Persist trip and Organizer membership together.
            return response
        except Exception:
            self.session.rollback()
            raise

    def list_trips(self, current_user_id: int) -> list[TripResponse]:
        trips = self.repository.list_for_user(current_user_id)
        return [TripResponse.model_validate(trip) for trip in trips]

    def get_trip(self, trip_id: int, current_user_id: int) -> TripDetailResponse:
        trip = self.repository.find_by_id(trip_id)
        if trip is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found.")

        membership = self.repository.find_membership(trip_id, current_user_id)
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Trip membership required.",
            )

        members = [
            TripMemberResponse(
                user_id=member.user_id,
                user_name=user.user_name,
                role=member.role,
                joined_at=member.joined_at,
            )
            for member, user in self.repository.list_members_with_users(trip_id)
        ]
        return TripDetailResponse(
            **TripResponse.model_validate(trip).model_dump(),
            members=members,
        )

    def delete_trip(self, trip_id: int, current_user_id: int) -> None:
        # Existing foreign-key cascades delete this trip's members and invitations.
        try:
            trip = self.repository.find_by_id(trip_id)
            if trip is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found.")
            if trip.organizer_id != current_user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only the Organizer can delete this trip.",
                )
            self.repository.delete(trip)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
