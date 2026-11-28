"""Add administrators, curated attractions, and proposal attraction links."""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_table(
        "attractions",
        sa.Column("attraction_id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("city", sa.Text()),
        sa.Column("country", sa.Text()),
        sa.Column("address", sa.Text()),
        sa.Column("latitude", sa.Double(), nullable=False),
        sa.Column("longitude", sa.Double(), nullable=False),
        sa.Column("category", sa.Text()),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("image_url", sa.Text()),
        sa.Column("opening_hours", sa.Text()),
        sa.Column("suggested_duration_minutes", sa.Integer()),
        sa.Column("typical_cost", sa.Numeric()),
        sa.Column("currency", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_by_user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_attractions_name"),
        sa.CheckConstraint("length(trim(summary)) > 0", name="ck_attractions_summary"),
        sa.CheckConstraint(
            "latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180",
            name="ck_attractions_coordinates",
        ),
        sa.CheckConstraint(
            "suggested_duration_minutes IS NULL OR suggested_duration_minutes > 0",
            name="ck_attractions_duration",
        ),
        sa.CheckConstraint("typical_cost IS NULL OR typical_cost >= 0", name="ck_attractions_cost"),
        sa.CheckConstraint(
            "currency IS NULL OR currency ~ '^[A-Z]{3}$'", name="ck_attractions_currency"
        ),
    )
    op.create_index(
        "uq_attractions_name_city",
        "attractions",
        [
            sa.text("lower(TRIM(BOTH FROM name))"),
            sa.text("lower(TRIM(BOTH FROM COALESCE(city, ''::text)))"),
        ],
        unique=True,
    )
    op.create_index("idx_attractions_coordinates", "attractions", ["latitude", "longitude"])
    op.add_column(
        "proposals",
        sa.Column(
            "attraction_id",
            sa.BigInteger(),
            sa.ForeignKey("attractions.attraction_id", ondelete="SET NULL"),
        ),
    )
    op.create_index("idx_proposals_attraction", "proposals", ["attraction_id"])


def downgrade() -> None:
    op.drop_index("idx_proposals_attraction", table_name="proposals")
    op.drop_column("proposals", "attraction_id")
    op.drop_index("idx_attractions_coordinates", table_name="attractions")
    op.drop_index("uq_attractions_name_city", table_name="attractions")
    op.drop_table("attractions")
    op.drop_column("users", "is_admin")
