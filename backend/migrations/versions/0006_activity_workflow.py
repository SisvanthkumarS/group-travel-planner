"""Persist proposals, voter snapshots, voting history and itinerary activities."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "proposals",
        sa.Column("proposal_id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("trip_id", sa.BigInteger(), nullable=False),
        sa.Column("author_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("estimated_cost", sa.Numeric(), nullable=False),
        sa.Column("location", sa.Text(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), server_default="PENDING", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'OPEN', 'TIED', 'APPROVED', 'REJECTED', "
            "'WITHDRAWN', 'CANCELLED')",
            name="ck_proposals_status",
        ),
        sa.CheckConstraint("ends_at > starts_at", name="ck_proposals_times"),
        sa.CheckConstraint("estimated_cost >= 0", name="ck_proposals_cost"),
        sa.CheckConstraint("length(trim(description)) > 0", name="ck_proposals_description"),
        sa.CheckConstraint("length(trim(location)) > 0", name="ck_proposals_location"),
        sa.CheckConstraint("length(trim(title)) > 0", name="ck_proposals_title"),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.user_id"],
        ),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.trip_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("proposal_id"),
    )
    op.create_index("idx_proposals_trip", "proposals", ["trip_id"], unique=False)
    op.create_table(
        "itinerary_items",
        sa.Column("item_id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("proposal_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), server_default="ACTIVE", nullable=False),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(status = 'ACTIVE' AND canceled_at IS NULL) OR "
            "(status = 'CANCELLED' AND canceled_at IS NOT NULL)",
            name="ck_itinerary_items_status",
        ),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.proposal_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("item_id"),
        sa.UniqueConstraint("proposal_id"),
    )
    op.create_table(
        "polls",
        sa.Column("poll_id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("proposal_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), server_default="OPEN", nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision", sa.Text(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("resolved_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(decision IS NULL AND resolved_by_user_id IS NULL AND resolved_at IS NULL) OR "
            "(decision IS NOT NULL AND decision IN ('APPROVE', 'REJECT') AND "
            "resolved_by_user_id IS NOT NULL AND resolved_at IS NOT NULL AND status = 'CLOSED')",
            name="ck_polls_resolution",
        ),
        sa.CheckConstraint(
            "(status = 'CLOSED' AND outcome IS NOT NULL AND "
            "outcome IN ('APPROVED', 'REJECTED', 'TIED')) OR "
            "(status IN ('OPEN', 'CANCELED') AND outcome IS NULL)",
            name="ck_polls_outcome",
        ),
        sa.CheckConstraint(
            "(status = 'OPEN' AND closed_at IS NULL) OR "
            "(status IN ('CLOSED', 'CANCELED') AND closed_at IS NOT NULL)",
            name="ck_polls_closed_at",
        ),
        sa.CheckConstraint("status IN ('OPEN', 'CLOSED', 'CANCELED')", name="ck_polls_status"),
        sa.CheckConstraint("deadline > opened_at", name="ck_polls_deadline"),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.proposal_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["resolved_by_user_id"],
            ["users.user_id"],
        ),
        sa.PrimaryKeyConstraint("poll_id"),
        sa.UniqueConstraint("proposal_id"),
    )
    op.create_index("idx_polls_status_deadline", "polls", ["status", "deadline"], unique=False)
    op.create_table(
        "eligible_voters",
        sa.Column("poll_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["poll_id"], ["polls.poll_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
        ),
        sa.PrimaryKeyConstraint("poll_id", "user_id"),
    )
    op.create_table(
        "vote_history",
        sa.Column("event_id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("poll_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("choice", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("choice IN ('YES', 'NO')", name="ck_vote_history_choice"),
        sa.ForeignKeyConstraint(
            ["poll_id", "user_id"],
            ["eligible_voters.poll_id", "eligible_voters.user_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index("idx_vote_history_poll", "vote_history", ["poll_id", "event_id"], unique=False)
    op.create_table(
        "votes",
        sa.Column("poll_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("choice", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("choice IN ('YES', 'NO')", name="ck_votes_choice"),
        sa.ForeignKeyConstraint(
            ["poll_id", "user_id"],
            ["eligible_voters.poll_id", "eligible_voters.user_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("poll_id", "user_id"),
    )


def downgrade():
    op.drop_table("votes")
    op.drop_table("vote_history")
    op.drop_table("eligible_voters")
    op.drop_table("polls")
    op.drop_table("itinerary_items")
    op.drop_table("proposals")
