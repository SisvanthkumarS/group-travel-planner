"""Create the users, trips, memberships and invitations from Database_Setup.docx."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint("LENGTH(TRIM(email)) > 0", name="ck_users_email_not_blank"),
    )
    op.create_index("uq_users_email_lower", "users", [sa.text("LOWER(TRIM(email))")], unique=True)
    op.create_table(
        "trips",
        sa.Column("trip_id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("destination", sa.Text(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column(
            "organizer_id",
            sa.BigInteger(),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.CheckConstraint("LENGTH(TRIM(name)) > 0", name="ck_trips_name_not_blank"),
        sa.CheckConstraint("LENGTH(TRIM(destination)) > 0", name="ck_trips_destination_not_blank"),
        sa.CheckConstraint("start_date <= end_date", name="ck_trips_dates"),
    )
    op.create_table(
        "trip_members",
        sa.Column(
            "trip_id",
            sa.BigInteger(),
            sa.ForeignKey("trips.trip_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint("role IN ('ORGANIZER', 'MEMBER')", name="ck_trip_members_role"),
    )
    op.create_index("idx_trip_members_user_id", "trip_members", ["user_id"])
    op.create_table(
        "invitations",
        sa.Column("invitation_id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "trip_id",
            sa.BigInteger(),
            sa.ForeignKey("trips.trip_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "invited_user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "invited_by_user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'PENDING'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("responded_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('PENDING', 'ACCEPTED', 'DECLINED')", name="ck_invitations_status"
        ),
        sa.CheckConstraint(
            "(status = 'PENDING' AND responded_at IS NULL) OR "
            "(status IN ('ACCEPTED', 'DECLINED') AND responded_at IS NOT NULL)",
            name="ck_invitation_response_time",
        ),
    )
    op.create_index(
        "uq_pending_invitation",
        "invitations",
        ["trip_id", "invited_user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_index("idx_invitations_invited_user", "invitations", ["invited_user_id"])


def downgrade() -> None:
    op.drop_table("invitations")
    op.drop_table("trip_members")
    op.drop_table("trips")
    op.drop_table("users")
