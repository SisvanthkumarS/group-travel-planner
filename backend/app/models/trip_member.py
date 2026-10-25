from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class TripMember(Base):
    __tablename__ = "trip_members"

    trip_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("trips.trip_id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(Text)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )

    __table_args__ = (
        CheckConstraint("role IN ('ORGANIZER', 'MEMBER')", name="ck_trip_members_role"),
        Index("idx_trip_members_user_id", "user_id"),
    )
