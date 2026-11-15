from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class AiChatSession(Base):
    __tablename__ = "chat_sessions"

    chat_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    trip_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("trips.trip_id", ondelete="CASCADE")
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("length(btrim(title)) BETWEEN 1 AND 120", name="ck_chat_sessions_title"),
        Index(
            "idx_chat_sessions_trip_owner_updated",
            trip_id,
            user_id,
            updated_at.desc(),
            chat_id.desc(),
        ),
        Index("idx_chat_sessions_user", "user_id"),
    )


class AiChatMessage(Base):
    __tablename__ = "chat_messages"

    message_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    chat_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chat_sessions.chat_id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="COMPLETED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("role IN ('USER', 'ASSISTANT')", name="ck_chat_messages_role"),
        CheckConstraint(
            "status IN ('PENDING', 'GENERATING', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name="ck_chat_messages_status",
        ),
        CheckConstraint(
            "role <> 'USER' OR status = 'COMPLETED'", name="ck_chat_messages_user_status"
        ),
        CheckConstraint(
            "status <> 'COMPLETED' OR length(btrim(content)) > 0",
            name="ck_chat_messages_completed_content",
        ),
        Index("idx_chat_messages_chat_message", "chat_id", "message_id"),
    )


class AiChatDraft(Base):
    __tablename__ = "chat_drafts"

    draft_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    message_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chat_messages.message_id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(Text)
    proposals: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text, server_default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("message_id", name="uq_chat_drafts_message"),
        CheckConstraint("kind IN ('PROPOSAL', 'ITINERARY')", name="ck_chat_drafts_kind"),
        CheckConstraint(
            """CASE WHEN jsonb_typeof(proposals) = 'array' THEN
                (kind = 'PROPOSAL' AND jsonb_array_length(proposals) = 1)
                OR (kind = 'ITINERARY' AND jsonb_array_length(proposals) BETWEEN 2 AND 100)
                ELSE FALSE END""",
            name="ck_chat_drafts_proposal_count",
        ),
        CheckConstraint(
            "(status = 'PENDING' AND decided_at IS NULL) OR "
            "(status IN ('ACCEPTED', 'REJECTED') AND decided_at IS NOT NULL)",
            name="ck_chat_drafts_decision",
        ),
    )


class AiChatDraftProposal(Base):
    """Links a confirmed draft to the proposals it created, without owning them."""

    __tablename__ = "chat_draft_proposals"

    draft_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chat_drafts.draft_id", ondelete="CASCADE"), primary_key=True
    )
    proposal_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("proposals.proposal_id", ondelete="CASCADE"), primary_key=True
    )

    __table_args__ = (UniqueConstraint("proposal_id", name="uq_chat_draft_proposals_proposal"),)
