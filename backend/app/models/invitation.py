from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class Invitation(Base):
    __tablename__ = "invitations"

    invitation_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    trip_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("trips.trip_id", ondelete="CASCADE")
    )
    invited_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE")
    )
    invited_by_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(Text, server_default=text("'PENDING'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'ACCEPTED', 'DECLINED')", name="ck_invitations_status"
        ),
        CheckConstraint(
            "(status = 'PENDING' AND responded_at IS NULL) OR "
            "(status IN ('ACCEPTED', 'DECLINED') AND responded_at IS NOT NULL)",
            name="ck_invitation_response_time",
        ),
        Index(
            "uq_pending_invitation",
            "trip_id",
            "invited_user_id",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
        ),
        Index("idx_invitations_invited_user", "invited_user_id"),
    )
