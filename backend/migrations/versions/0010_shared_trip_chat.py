"""Allow one shared chat per trip with attributed messages."""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("chat_sessions", "user_id", existing_type=sa.BigInteger(), nullable=True)
    op.create_index(
        "uq_chat_sessions_shared_trip",
        "chat_sessions",
        ["trip_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NULL"),
    )
    op.add_column(
        "chat_messages",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.user_id", ondelete="SET NULL")),
    )
    op.add_column(
        "chat_messages",
        sa.Column(
            "reply_to_message_id",
            sa.BigInteger(),
            sa.ForeignKey("chat_messages.message_id", ondelete="SET NULL"),
        ),
    )
    op.execute("""
        UPDATE chat_messages AS message
        SET user_id = chat.user_id
        FROM chat_sessions AS chat
        WHERE message.chat_id = chat.chat_id AND message.role = 'USER'
    """)


def downgrade() -> None:
    op.execute("DELETE FROM chat_sessions WHERE user_id IS NULL")
    op.drop_column("chat_messages", "reply_to_message_id")
    op.drop_column("chat_messages", "user_id")
    op.drop_index("uq_chat_sessions_shared_trip", table_name="chat_sessions")
    op.alter_column("chat_sessions", "user_id", existing_type=sa.BigInteger(), nullable=False)
