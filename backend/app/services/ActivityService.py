from collections import defaultdict
from datetime import UTC, datetime
from functools import wraps
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.app.models import EligibleVoter, ItineraryItem, Poll, Proposal, Vote, VoteHistory
from backend.app.repositories.ActivityRepository import ActivityRepository
from backend.app.schemas.activity import (
    CreateProposalRequest,
    ItineraryItemResponse,
    OpenPollRequest,
    PollResolution,
    PollResponse,
    ProposalResponse,
    ResolvePollRequest,
    VoteRequest,
    VoteResponse,
)


def transaction(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        try:
            response = method(self, *args, **kwargs)
            self.session.commit()
            return response
        except Exception:
            self.session.rollback()
            raise

    return wrapped


class ActivityService:
    def __init__(self, session: Session):
        self.session = session
        self.repository = ActivityRepository(session)

    @staticmethod
    def _invalid(field, message):
        raise HTTPException(
            422,
            detail=[
                {
                    "loc": ["body", field],
                    "msg": message,
                    "type": "value_error",
                }
            ],
        )

    def _trip(self, trip_id, user_id, *, organizer=False):
        trip = self.repository.trip(trip_id, lock=True)
        if trip is None:
            raise HTTPException(404, "Trip not found.")
        if organizer:
            if trip.organizer_id != user_id:
                raise HTTPException(403, "Trip organizer required.")
        elif not self.repository.is_member(trip_id, user_id):
            raise HTTPException(403, "Trip membership required.")
        return trip

    def _proposal(self, proposal_id, user_id, *, organizer=False):
        proposal = self.repository.proposal(proposal_id)
        if proposal is None:
            raise HTTPException(404, "Proposal not found.")
        self._trip(proposal.trip_id, user_id, organizer=organizer)
        # Refresh after acquiring the trip lock: a competing request may have committed.
        proposal = self.repository.proposal(proposal_id)
        if proposal is None:
            raise HTTPException(404, "Proposal not found.")
        return proposal

    def _poll(self, poll_id, user_id, *, organizer=False):
        poll = self.repository.poll(poll_id)
        if poll is None:
            raise HTTPException(404, "Poll not found.")
        proposal = self._proposal(poll.proposal_id, user_id, organizer=organizer)
        poll = self.repository.poll(poll_id)
        if poll is None:
            raise HTTPException(404, "Poll not found.")
        return poll, proposal

    def _poll_responses(self, polls):
        if not polls:
            return {}
        ids = [poll.poll_id for poll in polls]
        voters, votes, history = defaultdict(list), defaultdict(list), defaultdict(list)
        for voter in self.repository.eligible_voters(ids):
            voters[voter.poll_id].append(voter.user_id)
        for vote in self.repository.votes(ids):
            votes[vote.poll_id].append(VoteResponse.model_validate(vote))
        for event in self.repository.history(ids):
            history[event.poll_id].append(VoteResponse.model_validate(event))
        responses = {}
        for poll in polls:
            current = votes[poll.poll_id]
            yes = sum(vote.choice == "YES" for vote in current)
            resolution = None
            if poll.decision is not None:
                resolution = PollResolution(
                    decision=poll.decision,
                    resolved_by_user_id=poll.resolved_by_user_id,
                    resolved_at=poll.resolved_at,
                )
            responses[poll.proposal_id] = PollResponse(
                poll_id=poll.poll_id,
                proposal_id=poll.proposal_id,
                status=poll.status,
                deadline=poll.deadline,
                opened_at=poll.opened_at,
                closed_at=poll.closed_at,
                outcome=poll.outcome,
                eligible_voter_ids=voters[poll.poll_id],
                votes=current,
                voting_history=history[poll.poll_id],
                resolution=resolution,
                yes_count=yes,
                no_count=len(current) - yes,
                total_votes=len(current),
            )
        return responses

    def _responses(self, proposals):
        polls = self._poll_responses(self.repository.polls([p.proposal_id for p in proposals]))
        return [
            ProposalResponse.model_validate(p).model_copy(update={"poll": polls.get(p.proposal_id)})
            for p in proposals
        ]

    @transaction
    def create_proposal(self, trip_id: int, body: CreateProposalRequest, user_id: int):
        trip = self._trip(trip_id, user_id)
        starts_at, ends_at = body.starts_at.astimezone(UTC), body.ends_at.astimezone(UTC)
        if starts_at <= datetime.now(UTC):
            self._invalid("starts_at", "starts_at must be later than the current time.")
        trip_timezone = ZoneInfo(trip.timezone)
        if not trip.start_date <= starts_at.astimezone(trip_timezone).date() <= trip.end_date:
            self._invalid(
                "starts_at",
                "Activity start must fall within the travel dates in the trip's timezone.",
            )
        if not trip.start_date <= ends_at.astimezone(trip_timezone).date() <= trip.end_date:
            self._invalid(
                "ends_at", "Activity end must fall within the travel dates in the trip's timezone."
            )
        if self.repository.proposal_count(trip_id) >= 100:
            raise HTTPException(409, "Trip has reached its limit of 100 proposals.")
        proposal = self.repository.add(
            Proposal(
                **body.model_dump(exclude={"starts_at", "ends_at"}),
                starts_at=starts_at,
                ends_at=ends_at,
                trip_id=trip_id,
                author_id=user_id,
                status="PENDING",
            )
        )
        return ProposalResponse.model_validate(proposal)

    @transaction
    def list_proposals(self, trip_id: int, user_id: int):
        self._trip(trip_id, user_id)
        return self._responses(self.repository.proposals(trip_id))

    @transaction
    def withdraw(self, proposal_id: int, user_id: int):
        proposal = self._proposal(proposal_id, user_id)
        if proposal.author_id != user_id:
            raise HTTPException(403, "Only the proposal author can withdraw it.")
        if proposal.status not in ("PENDING", "OPEN"):
            raise HTTPException(409, "Only PENDING or OPEN proposals can be withdrawn.")
        polls = self.repository.polls([proposal_id])
        now = datetime.now(UTC)
        if polls:
            poll = polls[0]
            if poll.status != "OPEN" or poll.deadline <= now:
                raise HTTPException(409, "Poll has already closed or reached its deadline.")
            poll.status, poll.closed_at = "CANCELED", now
        proposal.status = "WITHDRAWN"
        self.session.flush()
        return self._responses([proposal])[0]

    @transaction
    def open_poll(self, proposal_id: int, body: OpenPollRequest, user_id: int):
        proposal = self._proposal(proposal_id, user_id, organizer=True)
        if proposal.status != "PENDING" or self.repository.polls([proposal_id]):
            raise HTTPException(409, "Proposal must be PENDING and have no existing poll.")
        now = datetime.now(UTC)
        if not now < body.deadline < proposal.starts_at:
            self._invalid("deadline", "deadline must be after now and before the activity start.")
        poll = self.repository.add(
            Poll(
                proposal_id=proposal_id,
                deadline=body.deadline,
                opened_at=now,
                status="OPEN",
            )
        )
        for user in self.repository.member_ids(proposal.trip_id):
            self.session.add(EligibleVoter(poll_id=poll.poll_id, user_id=user))
        proposal.status = "OPEN"
        self.session.flush()
        return self._poll_responses([poll])[proposal_id]

    @transaction
    def vote(self, poll_id: int, body: VoteRequest, user_id: int):
        poll, proposal = self._poll(poll_id, user_id)
        if not self.repository.eligible(poll_id, user_id):
            raise HTTPException(
                403, "You were not recorded as an eligible voter when this poll opened."
            )
        now = datetime.now(UTC)
        if poll.status != "OPEN" or proposal.status != "OPEN" or now >= poll.deadline:
            raise HTTPException(409, "Voting has closed or the deadline has been reached.")
        vote = self.repository.vote(poll_id, user_id)
        if vote is not None and vote.choice == body.choice:
            return VoteResponse.model_validate(vote)
        if vote is None:
            vote = Vote(poll_id=poll_id, user_id=user_id)
            self.session.add(vote)
        vote.choice, vote.updated_at = body.choice, now
        self.session.add(
            VoteHistory(
                poll_id=poll_id,
                user_id=user_id,
                choice=body.choice,
                updated_at=now,
            )
        )
        self.session.flush()
        return VoteResponse.model_validate(vote)

    def _approve(self, proposal):
        proposal.status = "APPROVED"
        self.session.add(ItineraryItem(proposal_id=proposal.proposal_id, status="ACTIVE"))

    @transaction
    def resolve(self, poll_id: int, body: ResolvePollRequest, user_id: int):
        poll, proposal = self._poll(poll_id, user_id, organizer=True)
        if poll.status != "CLOSED" or proposal.status != "TIED" or poll.decision is not None:
            raise HTTPException(409, "Only an unresolved tied proposal can be resolved.")
        poll.decision, poll.resolved_by_user_id = body.decision, user_id
        poll.resolved_at = datetime.now(UTC)
        if body.decision == "APPROVE":
            self._approve(proposal)
        else:
            proposal.status = "REJECTED"
        self.session.flush()
        return self._responses([proposal])[0]

    @transaction
    def itinerary(self, trip_id: int, user_id: int):
        self._trip(trip_id, user_id)
        return [
            ItineraryItemResponse(
                item_id=item.item_id,
                trip_id=trip_id,
                proposal_id=proposal.proposal_id,
                title=proposal.title,
                description=proposal.description,
                location=proposal.location,
                estimated_cost=proposal.estimated_cost,
                starts_at=proposal.starts_at,
                ends_at=proposal.ends_at,
                status=item.status,
            )
            for item, proposal in self.repository.itinerary(trip_id)
        ]

    @transaction
    def cancel(self, trip_id: int, item_id: int, user_id: int):
        self._trip(trip_id, user_id, organizer=True)
        item = self.repository.item(trip_id, item_id)
        if item is None:
            raise HTTPException(404, "Itinerary item not found in this trip.")
        if item.status == "ACTIVE":
            item.status, item.canceled_at = "CANCELLED", datetime.now(UTC)
            self.repository.proposal(item.proposal_id).status = "CANCELLED"
            self.session.flush()

    @transaction
    def close_due_for_trip(self, trip_id: int):
        """Internal scheduler entry point; safe across processes and repeated scans."""
        if self.repository.trip(trip_id, lock=True, skip_locked=True) is None:
            return 0
        now = datetime.now(UTC)
        due = self.repository.due_polls(trip_id, now)
        for poll, proposal in due:
            votes = self.repository.votes([poll.poll_id])
            yes = sum(vote.choice == "YES" for vote in votes)
            no = len(votes) - yes
            poll.status, poll.closed_at = "CLOSED", now
            if yes > no:
                poll.outcome = "APPROVED"
                self._approve(proposal)
            elif yes == no and yes > 0:
                poll.outcome = proposal.status = "TIED"
            else:
                poll.outcome = proposal.status = "REJECTED"
        self.session.flush()
        return len(due)
