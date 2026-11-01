from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response
from fastapi.security import APIKeyCookie
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.database import get_session
from backend.app.schemas.activity import (
    CreateProposalRequest,
    ItineraryItemResponse,
    OpenPollRequest,
    PollResponse,
    ProposalResponse,
    ResolvePollRequest,
    VoteRequest,
    VoteResponse,
)
from backend.app.services.ActivityService import ActivityService

router = APIRouter(
    responses={
        401: {"description": "Authentication required."},
        403: {
            "description": "Required membership, authorship, organizer role, or eligibility missing"
        },
        404: {"description": "Requested resource not found in this trip."},
    },
    # Authentication is enforced globally; this dependency also documents the cookie.
    dependencies=[
        Depends(
            APIKeyCookie(
                name=get_settings().jwt_cookie_name,
                scheme_name="CookieAuth",
                auto_error=False,
            )
        )
    ],
)
Id = Annotated[int, Path(gt=0, le=9223372036854775807)]


def get_activity_service(session: Annotated[Session, Depends(get_session)]) -> ActivityService:
    return ActivityService(session)


Service = Annotated[ActivityService, Depends(get_activity_service)]


@router.post(
    "/trips/{trip_id}/proposals",
    tags=["Activity Proposals"],
    response_model=ProposalResponse,
    status_code=201,
    responses={409: {"description": "Trip already contains 100 proposals."}},
)
def create_proposal(trip_id: Id, body: CreateProposalRequest, request: Request, service: Service):
    """Submit a PENDING proposal as a trip participant.

    Activity times must be in the future and within the trip's UTC travel dates.
    Description and non-negative estimated cost are required. At most 100 proposals
    are allowed per trip, including withdrawn and canceled proposals.
    """
    return service.create_proposal(trip_id, body, request.state.current_user.user_id)


@router.get(
    "/trips/{trip_id}/proposals",
    tags=["Activity Proposals"],
    response_model=list[ProposalResponse],
)
def list_proposals(trip_id: Id, request: Request, service: Service):
    """List all proposals, statuses, counts, poll outcomes and voting history; members only.

    Includes WITHDRAWN, REJECTED and CANCELLED proposals. Poll outcomes and tie
    decisions are retained after cancellation. Returns an empty array when none exist.
    """
    return service.list_proposals(trip_id, request.state.current_user.user_id)


@router.post(
    "/proposals/{proposal_id}/withdraw",
    tags=["Activity Proposals"],
    response_model=ProposalResponse,
    responses={409: {"description": "Proposal is not PENDING/OPEN or poll deadline has passed."}},
)
def withdraw_proposal(proposal_id: Id, request: Request, service: Service):
    """Author only: withdraw a PENDING or OPEN proposal before the poll deadline.

    An open poll is canceled without an outcome. Existing votes and history remain,
    and further voting, opening a poll, or resolution is prohibited.
    """
    return service.withdraw(proposal_id, request.state.current_user.user_id)


@router.post(
    "/proposals/{proposal_id}/poll",
    tags=["Polls and Voting"],
    response_model=PollResponse,
    status_code=201,
    responses={409: {"description": "Proposal is not PENDING or already has a poll."}},
)
def open_poll(proposal_id: Id, body: OpenPollRequest, request: Request, service: Service):
    """Organizer only: open a pending proposal's poll and snapshot all current participants.

    The organizer and proposal author are eligible. Deadline must be after now and
    before the activity start. The internal scheduler closes polls automatically:
    more YES than NO approves and adds an itinerary item exactly once; more NO or
    zero votes rejects; equal nonzero counts produces TIED. No quorum is required.
    There is no public poll-closing endpoint.
    """
    return service.open_poll(proposal_id, body, request.state.current_user.user_id)


@router.put(
    "/polls/{poll_id}/vote",
    tags=["Polls and Voting"],
    response_model=VoteResponse,
    responses={409: {"description": "Poll/proposal is not OPEN or deadline reached."}},
)
def vote(poll_id: Id, body: VoteRequest, request: Request, service: Service):
    """Cast or update one YES/NO vote as an eligible participant strictly before the deadline.

    Eligibility is fixed at poll opening. Changed choices preserve the old choice in
    history; repeating the current choice is idempotent. Votes are rejected at the
    deadline even if the scheduler has not yet processed the poll.
    """
    return service.vote(poll_id, body, request.state.current_user.user_id)


@router.post(
    "/polls/{poll_id}/resolve",
    tags=["Polls and Voting"],
    response_model=ProposalResponse,
    responses={409: {"description": "Poll has no unresolved TIED proposal."}},
)
def resolve_poll(poll_id: Id, body: ResolvePollRequest, request: Request, service: Service):
    """Organizer only: approve or reject an automatically closed, tied proposal.

    Approval adds the activity to the itinerary exactly once. The original TIED
    outcome and the organizer's resolution are both retained. Does not close polls.
    """
    return service.resolve(poll_id, body, request.state.current_user.user_id)


@router.get(
    "/trips/{trip_id}/itinerary",
    tags=["Shared Itinerary"],
    response_model=list[ItineraryItemResponse],
)
def get_itinerary(trip_id: Id, request: Request, service: Service):
    """Members only: retrieve active approved activities ordered by starts_at then item_id.

    Canceled activities are excluded. Returns an empty array when no active items exist.
    """
    return service.itinerary(trip_id, request.state.current_user.user_id)


@router.delete(
    "/trips/{trip_id}/itinerary/{item_id}",
    tags=["Shared Itinerary"],
    status_code=204,
)
def cancel_itinerary_item(trip_id: Id, item_id: Id, request: Request, service: Service) -> Response:
    """Organizer only: cancel an approved activity belonging to this trip.

    Sets the proposal and itinerary item to CANCELLED, preserving poll outcomes and
    voting history. Already canceled items also return an empty 204 response.
    """
    service.cancel(trip_id, item_id, request.state.current_user.user_id)
    return Response(status_code=204)
