from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models import Invitation, TripMember
from backend.app.repositories.AuthRepository import AuthRepository
from backend.app.repositories.InvitationRepository import InvitationRepository
from backend.app.repositories.TripInvitationRepository import TripInvitationRepository
from backend.app.repositories.TripRepository import TripRepository
from backend.app.schemas.invitation import (
    CreateInvitationRequest,
    InvitationResponse,
    RespondInvitationRequest,
)


class InvitationService:
    """Invitation creation, inbox queries, and atomic invitation responses."""

    def __init__(self, session: Session):
        self.session = session
        self.repository = InvitationRepository(session)
        self.trip_repository = TripRepository(session)
        self.user_repository = AuthRepository(session)
        self.trip_invitation_repository = TripInvitationRepository(session)
        # The JWT filter already starts this shared Session's transaction.
        # Writes should commit once or rollback on failure, without another begin().

    def create_invitation(
        self, trip_id: int, request: CreateInvitationRequest, current_user_id: int
    ) -> InvitationResponse:
        try:
            # Share the trip lock with the future acceptance flow so a recipient
            # cannot become a member between our membership check and insertion.
            trip = self.trip_invitation_repository.find_trip_for_update(trip_id)
            if trip is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found.")
            if trip.organizer_id != current_user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only the Organizer can invite users to this trip.",
                )

            if request.email is not None:
                recipient = self.user_repository.find_by_email(request.email)
            else:
                recipient = self.user_repository.find_by_user_name(request.user_name)
            if recipient is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Registered recipient not found.",
                )
            if recipient.user_id == current_user_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail="You cannot invite yourself."
                )
            if self.trip_repository.find_membership(trip_id, recipient.user_id) is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="User is already a member of this trip.",
                )
            if self.repository.find_pending(trip_id, recipient.user_id) is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="An invitation is already pending for this user and trip.",
                )

            invitation = Invitation(
                trip_id=trip_id,
                invited_user_id=recipient.user_id,
                invited_by_user_id=current_user_id,
                status="PENDING",
                responded_at=None,
            )
            saved_invitation = self.repository.add(invitation)
            response = InvitationResponse.model_validate(saved_invitation)
            self.session.commit()
            return response
        except IntegrityError as exc:
            self.session.rollback()
            constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            if constraint == "uq_pending_invitation":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="An invitation is already pending for this user and trip.",
                ) from exc
            raise
        except Exception:
            self.session.rollback()
            raise

    def list_invitations(self, current_user_id: int) -> list[InvitationResponse]:
        invitations = self.repository.list_for_user(current_user_id)
        return [InvitationResponse.model_validate(invitation) for invitation in invitations]

    def respond_to_invitation(
        self, request: RespondInvitationRequest, current_user_id: int
    ) -> InvitationResponse:
        try:
            invitation = self.repository.find_by_id(request.invitation_id)
            if invitation is None:
                raise HTTPException(status_code=404, detail="Invitation not found.")
            if invitation.invited_user_id != current_user_id:
                raise HTTPException(status_code=403, detail="Only the recipient can respond.")

            # Serialize membership changes for the trip, then refresh the invitation:
            # another request may have answered it while we waited for the trip lock.
            trip = self.trip_invitation_repository.find_trip_for_update(invitation.trip_id)
            if trip is None:
                raise HTTPException(status_code=404, detail="Trip not found.")
            invitation = self.repository.find_by_id_for_update(request.invitation_id)
            if invitation is None:
                raise HTTPException(status_code=404, detail="Invitation not found.")
            if invitation.invited_user_id != current_user_id:
                raise HTTPException(status_code=403, detail="Only the recipient can respond.")
            if invitation.status != "PENDING":
                raise HTTPException(status_code=409, detail="Invitation has already been answered.")

            if request.decision == "ACCEPT":
                if self.trip_repository.find_membership(trip.trip_id, current_user_id) is not None:
                    raise HTTPException(
                        status_code=409, detail="User is already a member of this trip."
                    )
                if self.trip_invitation_repository.count_members(trip.trip_id) >= 8:
                    raise HTTPException(status_code=409, detail="Trip is full (maximum 8 members).")
                self.trip_repository.add_member(
                    TripMember(trip_id=trip.trip_id, user_id=current_user_id, role="MEMBER")
                )
                invitation.status = "ACCEPTED"
            else:
                invitation.status = "DECLINED"

            invitation.responded_at = datetime.now(UTC)
            saved_invitation = self.repository.save_response(invitation)
            response = InvitationResponse.model_validate(saved_invitation)
            self.session.commit()
            return response
        except Exception:
            self.session.rollback()
            raise
