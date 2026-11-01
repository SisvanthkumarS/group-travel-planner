from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Identity, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class User(Base):
    __tablename__ = "users"
    user_name: Mapped[str] = mapped_column(Text)
    user_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    email: Mapped[str] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )

    __table_args__ = (
        CheckConstraint(
            "char_length(user_name) BETWEEN 1 AND 30 AND length(trim(user_name)) > 0",
            name="ck_users_user_name_length",
        ),
        Index("uq_users_user_name", "user_name", unique=True),
        CheckConstraint("LENGTH(TRIM(email)) > 0", name="ck_users_email_not_blank"),
        Index("uq_users_email_lower", text("lower(TRIM(BOTH FROM email))"), unique=True),
    )
