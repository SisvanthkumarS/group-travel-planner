"""User notification preferences, inbox history, and durable email outbox."""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "in_app_notifications_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "email_notifications_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_table(
        "notifications",
        sa.Column("notification_id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_key", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("trip_name", sa.Text(), nullable=False),
        sa.Column("trip_id", sa.BigInteger(), sa.ForeignKey("trips.trip_id", ondelete="SET NULL")),
        sa.Column(
            "proposal_id",
            sa.BigInteger(),
            sa.ForeignKey("proposals.proposal_id", ondelete="SET NULL"),
        ),
        sa.Column(
            "invitation_id",
            sa.BigInteger(),
            sa.ForeignKey("invitations.invitation_id", ondelete="SET NULL"),
        ),
        sa.Column("in_app_visible", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "event_key", name="uq_notification_recipient_event"),
    )
    op.create_index(
        "idx_notifications_inbox", "notifications", ["user_id", "in_app_visible", "notification_id"]
    )
    op.create_index(
        "idx_notifications_unread",
        "notifications",
        ["user_id", "notification_id"],
        postgresql_where=sa.text("in_app_visible AND read_at IS NULL"),
    )
    op.create_table(
        "notification_emails",
        sa.Column(
            "notification_id",
            sa.BigInteger(),
            sa.ForeignKey("notifications.notification_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("lease_token", sa.Text()),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('PENDING', 'SENDING', 'SENT', 'FAILED', 'CANCELED')",
            name="ck_notification_email_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_notification_email_attempts"),
    )
    op.create_index(
        "idx_notification_emails_due", "notification_emails", ["status", "next_attempt_at"]
    )


def downgrade() -> None:
    op.drop_table("notification_emails")
    op.drop_table("notifications")
    op.drop_column("users", "email_notifications_enabled")
    op.drop_column("users", "in_app_notifications_enabled")
