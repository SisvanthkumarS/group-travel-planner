"""Store the timezone that defines each trip's local calendar dates."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing trips use Eastern time, as agreed for this migration.
    op.add_column(
        "trips", sa.Column("timezone", sa.Text(), nullable=False, server_default="America/New_York")
    )
    # API clients must supply a timezone. Keep UTC for legacy direct database inserts.
    op.alter_column("trips", "timezone", server_default="UTC")


def downgrade() -> None:
    op.drop_column("trips", "timezone")
