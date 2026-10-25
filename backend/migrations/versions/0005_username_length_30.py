"""Increase the username limit from ten to thirty characters."""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def set_username_limit(limit: int) -> None:
    op.drop_constraint("ck_users_user_name_length", "users", type_="check")
    op.create_check_constraint(
        "ck_users_user_name_length",
        "users",
        f"char_length(user_name) BETWEEN 1 AND {limit} AND length(trim(user_name)) > 0",
    )


def upgrade() -> None:
    set_username_limit(30)


def downgrade() -> None:
    # PostgreSQL rejects this if longer names exist; never truncate account names.
    set_username_limit(10)
