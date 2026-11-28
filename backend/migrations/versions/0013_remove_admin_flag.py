"""Take administrator features offline: drop users.is_admin.

Attractions are now maintained only through backend/data/attractions.json and
scripts/seed_attractions.py. Downgrading restores the column with every user
set to non-administrator.
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("users", "is_admin")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
