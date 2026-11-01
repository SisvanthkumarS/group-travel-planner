from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models import (
    EligibleVoter,
    ItineraryItem,
    Poll,
    Proposal,
    Trip,
    TripMember,
    Vote,
    VoteHistory,
)


class ActivityRepository:
    """Activity persistence. All mutations serialize on the parent trip lock."""

    def __init__(self, session: Session):
        self.session = session

    def trip(self, trip_id, *, lock=False, skip_locked=False):
        statement = select(Trip).where(Trip.trip_id == trip_id)
        if lock:
            statement = statement.with_for_update(skip_locked=skip_locked)
        return self.session.scalar(statement.execution_options(populate_existing=True))

    def is_member(self, trip_id, user_id):
        return self.session.get(TripMember, (trip_id, user_id)) is not None

    def member_ids(self, trip_id):
        return list(
            self.session.scalars(
                select(TripMember.user_id)
                .where(TripMember.trip_id == trip_id)
                .order_by(TripMember.user_id)
            )
        )

    def proposal(self, proposal_id):
        return self.session.get(Proposal, proposal_id, populate_existing=True)

    def poll(self, poll_id):
        return self.session.get(Poll, poll_id, populate_existing=True)

    def proposal_count(self, trip_id):
        return self.session.scalar(
            select(func.count()).select_from(Proposal).where(Proposal.trip_id == trip_id)
        )

    def proposals(self, trip_id):
        return list(
            self.session.scalars(
                select(Proposal)
                .where(Proposal.trip_id == trip_id)
                .order_by(Proposal.created_at, Proposal.proposal_id)
            )
        )

    def polls(self, proposal_ids):
        return list(self.session.scalars(select(Poll).where(Poll.proposal_id.in_(proposal_ids))))

    def eligible_voters(self, poll_ids):
        return list(
            self.session.scalars(
                select(EligibleVoter)
                .where(EligibleVoter.poll_id.in_(poll_ids))
                .order_by(EligibleVoter.user_id)
            )
        )

    def votes(self, poll_ids):
        return list(
            self.session.scalars(
                select(Vote).where(Vote.poll_id.in_(poll_ids)).order_by(Vote.user_id)
            )
        )

    def history(self, poll_ids):
        return list(
            self.session.scalars(
                select(VoteHistory)
                .where(VoteHistory.poll_id.in_(poll_ids))
                .order_by(VoteHistory.event_id)
            )
        )

    def eligible(self, poll_id, user_id):
        return self.session.get(EligibleVoter, (poll_id, user_id)) is not None

    def vote(self, poll_id, user_id):
        return self.session.get(Vote, (poll_id, user_id), populate_existing=True)

    def itinerary(self, trip_id):
        return list(
            self.session.execute(
                select(ItineraryItem, Proposal)
                .join(Proposal)
                .where(
                    Proposal.trip_id == trip_id,
                    Proposal.status == "APPROVED",
                    ItineraryItem.status == "ACTIVE",
                )
                .order_by(Proposal.starts_at, ItineraryItem.item_id)
            )
        )

    def item(self, trip_id, item_id):
        return self.session.scalar(
            select(ItineraryItem)
            .join(Proposal)
            .where(Proposal.trip_id == trip_id, ItineraryItem.item_id == item_id)
            .execution_options(populate_existing=True)
        )

    def due_trip_ids(self, now):
        return list(
            self.session.scalars(
                select(Proposal.trip_id)
                .join(Poll)
                .where(Poll.status == "OPEN", Poll.deadline <= now)
                .distinct()
                .order_by(Proposal.trip_id)
            )
        )

    def due_polls(self, trip_id, now):
        return list(
            self.session.execute(
                select(Poll, Proposal)
                .join(Proposal)
                .where(Proposal.trip_id == trip_id, Poll.status == "OPEN", Poll.deadline <= now)
                .order_by(Poll.poll_id)
                .execution_options(populate_existing=True)
            )
        )

    def add(self, entity):
        self.session.add(entity)
        self.session.flush()
        return entity
