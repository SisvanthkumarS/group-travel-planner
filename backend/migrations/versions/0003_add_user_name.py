"""Add the user_name field to existing users without removing their data."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Adopt the column too if it was already added manually in the database IDE.
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS user_name TEXT")
    # Existing accounts have no display name yet; use their email as a fallback.
    op.execute("UPDATE users SET user_name = email WHERE user_name IS NULL")
    op.alter_column("users", "user_name", existing_type=sa.Text(), type_=sa.Text(), nullable=False)


def downgrade() -> None:
    op.drop_column("users", "user_name")
