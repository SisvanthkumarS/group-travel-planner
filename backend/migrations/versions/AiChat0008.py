"""Create private AI chat sessions, messages, drafts, and proposal links."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("chat_id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "trip_id",
            sa.BigInteger(),
            sa.ForeignKey("trips.trip_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("length(btrim(title)) BETWEEN 1 AND 120", name="ck_chat_sessions_title"),
    )
    op.create_index(
        "idx_chat_sessions_trip_owner_updated",
        "chat_sessions",
        ["trip_id", "user_id", sa.text("updated_at DESC"), sa.text("chat_id DESC")],
    )
    op.create_index("idx_chat_sessions_user", "chat_sessions", ["user_id"])

    op.create_table(
        "chat_messages",
        sa.Column("message_id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "chat_id",
            sa.BigInteger(),
            sa.ForeignKey("chat_sessions.chat_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="COMPLETED"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("role IN ('USER', 'ASSISTANT')", name="ck_chat_messages_role"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'GENERATING', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name="ck_chat_messages_status",
        ),
        sa.CheckConstraint(
            "role <> 'USER' OR status = 'COMPLETED'", name="ck_chat_messages_user_status"
        ),
        sa.CheckConstraint(
            "status <> 'COMPLETED' OR length(btrim(content)) > 0",
            name="ck_chat_messages_completed_content",
        ),
    )
    op.create_index("idx_chat_messages_chat_message", "chat_messages", ["chat_id", "message_id"])

    op.create_table(
        "chat_drafts",
        sa.Column("draft_id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "message_id",
            sa.BigInteger(),
            sa.ForeignKey("chat_messages.message_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("proposals", JSONB(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="PENDING"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("message_id", name="uq_chat_drafts_message"),
        sa.CheckConstraint("kind IN ('PROPOSAL', 'ITINERARY')", name="ck_chat_drafts_kind"),
        sa.CheckConstraint(
            """CASE WHEN jsonb_typeof(proposals) = 'array' THEN
                (kind = 'PROPOSAL' AND jsonb_array_length(proposals) = 1)
                OR (kind = 'ITINERARY' AND jsonb_array_length(proposals) BETWEEN 2 AND 100)
                ELSE FALSE END""",
            name="ck_chat_drafts_proposal_count",
        ),
        sa.CheckConstraint(
            "(status = 'PENDING' AND decided_at IS NULL) OR "
            "(status IN ('ACCEPTED', 'REJECTED') AND decided_at IS NOT NULL)",
            name="ck_chat_drafts_decision",
        ),
    )

    op.create_table(
        "chat_draft_proposals",
        sa.Column(
            "draft_id",
            sa.BigInteger(),
            sa.ForeignKey("chat_drafts.draft_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "proposal_id",
            sa.BigInteger(),
            sa.ForeignKey("proposals.proposal_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.UniqueConstraint("proposal_id", name="uq_chat_draft_proposals_proposal"),
    )


def downgrade() -> None:
    op.drop_table("chat_draft_proposals")
    op.drop_table("chat_drafts")
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
