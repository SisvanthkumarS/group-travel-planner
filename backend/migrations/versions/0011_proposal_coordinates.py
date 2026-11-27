"""Add optional coordinates to activity proposals."""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("proposals", sa.Column("latitude", sa.Double(), nullable=True))
    op.add_column("proposals", sa.Column("longitude", sa.Double(), nullable=True))
    op.create_check_constraint(
        "ck_proposals_coordinates",
        "proposals",
        "(latitude IS NULL AND longitude IS NULL) OR "
        "(latitude IS NOT NULL AND longitude IS NOT NULL "
        "AND latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_proposals_coordinates", "proposals", type_="check")
    op.drop_column("proposals", "longitude")
    op.drop_column("proposals", "latitude")
