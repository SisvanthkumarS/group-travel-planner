"""Require unique usernames of one to ten characters."""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing invalid names must be corrected explicitly, never truncated or renamed.
    op.create_check_constraint(
        "ck_users_user_name_length",
        "users",
        "char_length(user_name) BETWEEN 1 AND 10 AND length(trim(user_name)) > 0",
    )
    op.create_index("uq_users_user_name", "users", ["user_name"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_users_user_name", table_name="users")
    op.drop_constraint("ck_users_user_name_length", "users", type_="check")
