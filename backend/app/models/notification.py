from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class Notification(Base):
    __tablename__ = "notifications"

    notification_id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE")
    )
    event_key: Mapped[str] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    trip_name: Mapped[str] = mapped_column(Text)
    trip_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("trips.trip_id", ondelete="SET NULL")
    )
    proposal_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("proposals.proposal_id", ondelete="SET NULL")
    )
    invitation_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("invitations.invitation_id", ondelete="SET NULL")
    )
    in_app_visible: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("user_id", "event_key", name="uq_notification_recipient_event"),
        Index("idx_notifications_inbox", "user_id", "in_app_visible", "notification_id"),
        Index(
            "idx_notifications_unread",
            "user_id",
            "notification_id",
            postgresql_where=text("in_app_visible AND read_at IS NULL"),
        ),
    )


class NotificationEmail(Base):
    __tablename__ = "notification_emails"

    notification_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("notifications.notification_id", ondelete="CASCADE"),
        primary_key=True,
    )
    status: Mapped[str] = mapped_column(Text, server_default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    lease_token: Mapped[str | None] = mapped_column(Text)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'SENDING', 'SENT', 'FAILED', 'CANCELED')",
            name="ck_notification_email_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_notification_email_attempts"),
        Index("idx_notification_emails_due", "status", "next_attempt_at"),
    )
