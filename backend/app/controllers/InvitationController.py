from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, status
from sqlalchemy.orm import Session

from backend.app.core.database import get_session
from backend.app.schemas.invitation import (
    CreateInvitationRequest,
    InvitationResponse,
    RespondInvitationRequest,
)
from backend.app.services.InvitationService import InvitationService

# No prefix here: this controller serves both /trips/.../invitations and /invitations.
router = APIRouter(
    tags=["Invitations"],
    responses={
        401: {"description": "Authentication required."},
    },
)


def get_invitation_service(
    session: Annotated[Session, Depends(get_session)],
) -> InvitationService:
    return InvitationService(session)


InvitationServiceDependency = Annotated[InvitationService, Depends(get_invitation_service)]
TripId = Annotated[int, Path(gt=0, description="Trip ID")]


@router.post(
    "/trips/{trip_id}/invitations",
    response_model=InvitationResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        403: {"description": "Organizer required."},
        404: {"description": "Trip or registered recipient not found."},
        409: {"description": "Already a member or invitation already pending."},
    },
)
def create_invitation(
    trip_id: TripId,
    body: CreateInvitationRequest,
    request: Request,
    service: InvitationServiceDependency,
) -> InvitationResponse:
    """Create a pending invitation by email or user_name; Organizer only."""
    return service.create_invitation(trip_id, body, request.state.current_user.user_id)


@router.get(
    "/invitations",
    response_model=list[InvitationResponse],
)
def list_invitations(
    request: Request, service: InvitationServiceDependency
) -> list[InvitationResponse]:
    """List all invitations received by the current user, newest first."""
    return service.list_invitations(request.state.current_user.user_id)


@router.patch(
    "/invitations",
    response_model=InvitationResponse,
    responses={
        403: {"description": "Only the recipient can respond."},
        404: {"description": "Invitation or trip not found."},
        409: {"description": "Already answered, already a member, or trip is full."},
    },
)
def respond_to_invitation(
    body: RespondInvitationRequest,
    request: Request,
    service: InvitationServiceDependency,
) -> InvitationResponse:
    """Accept or decline a pending invitation; only its recipient can respond."""
    return service.respond_to_invitation(body, request.state.current_user.user_id)
