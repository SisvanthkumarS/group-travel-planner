from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Numeric,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class Proposal(Base):
    __tablename__ = "proposals"

    proposal_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    trip_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("trips.trip_id", ondelete="CASCADE")
    )
    author_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id"))
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    estimated_cost: Mapped[Decimal] = mapped_column(Numeric)
    location: Mapped[str] = mapped_column(Text)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, server_default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("length(trim(title)) > 0", name="ck_proposals_title"),
        CheckConstraint("length(trim(location)) > 0", name="ck_proposals_location"),
        CheckConstraint("length(trim(description)) > 0", name="ck_proposals_description"),
        CheckConstraint("estimated_cost >= 0", name="ck_proposals_cost"),
        CheckConstraint("ends_at > starts_at", name="ck_proposals_times"),
        CheckConstraint(
            "status IN ('PENDING', 'OPEN', 'TIED', 'APPROVED', 'REJECTED', "
            "'WITHDRAWN', 'CANCELLED')",
            name="ck_proposals_status",
        ),
        Index("idx_proposals_trip", "trip_id"),
    )


class Poll(Base):
    __tablename__ = "polls"

    poll_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    proposal_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("proposals.proposal_id", ondelete="CASCADE"), unique=True
    )
    status: Mapped[str] = mapped_column(Text, server_default="OPEN")
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str | None] = mapped_column(Text)
    resolved_by_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.user_id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('OPEN', 'CLOSED', 'CANCELED')", name="ck_polls_status"),
        CheckConstraint("deadline > opened_at", name="ck_polls_deadline"),
        CheckConstraint(
            "(status = 'CLOSED' AND outcome IS NOT NULL AND "
            "outcome IN ('APPROVED', 'REJECTED', 'TIED')) OR "
            "(status IN ('OPEN', 'CANCELED') AND outcome IS NULL)",
            name="ck_polls_outcome",
        ),
        CheckConstraint(
            "(status = 'OPEN' AND closed_at IS NULL) OR "
            "(status IN ('CLOSED', 'CANCELED') AND closed_at IS NOT NULL)",
            name="ck_polls_closed_at",
        ),
        CheckConstraint(
            "(decision IS NULL AND resolved_by_user_id IS NULL AND resolved_at IS NULL) OR "
            "(decision IS NOT NULL AND decision IN ('APPROVE', 'REJECT') AND "
            "resolved_by_user_id IS NOT NULL AND resolved_at IS NOT NULL AND status = 'CLOSED')",
            name="ck_polls_resolution",
        ),
        Index("idx_polls_status_deadline", "status", "deadline"),
    )


class EligibleVoter(Base):
    __tablename__ = "eligible_voters"

    poll_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("polls.poll_id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id"), primary_key=True)


class Vote(Base):
    __tablename__ = "votes"

    poll_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    choice: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["poll_id", "user_id"],
            ["eligible_voters.poll_id", "eligible_voters.user_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("choice IN ('YES', 'NO')", name="ck_votes_choice"),
    )


class VoteHistory(Base):
    __tablename__ = "vote_history"

    event_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    poll_id: Mapped[int] = mapped_column(BigInteger)
    user_id: Mapped[int] = mapped_column(BigInteger)
    choice: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["poll_id", "user_id"],
            ["eligible_voters.poll_id", "eligible_voters.user_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("choice IN ('YES', 'NO')", name="ck_vote_history_choice"),
        Index("idx_vote_history_poll", "poll_id", "event_id"),
    )


class ItineraryItem(Base):
    __tablename__ = "itinerary_items"

    item_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    proposal_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("proposals.proposal_id", ondelete="CASCADE"), unique=True
    )
    status: Mapped[str] = mapped_column(Text, server_default="ACTIVE")
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "(status = 'ACTIVE' AND canceled_at IS NULL) OR "
            "(status = 'CANCELLED' AND canceled_at IS NOT NULL)",
            name="ck_itinerary_items_status",
        ),
    )
