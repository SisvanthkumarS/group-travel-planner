from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.AiChat import (
    AiChatDraft,
    AiChatDraftProposal,
    AiChatMessage,
    AiChatSession,
)


class AiChatRepository:
    """Database operations; the Service owns membership checks and transactions."""

    def __init__(self, session: Session):
        self.session = session

    def add_chat(self, chat: AiChatSession) -> AiChatSession:
        self.session.add(chat)
        self.session.flush()
        return chat

    def find_chat(self, chat_id: int, user_id: int, *, lock: bool = False) -> AiChatSession | None:
        statement = select(AiChatSession).where(
            AiChatSession.chat_id == chat_id, AiChatSession.user_id == user_id
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return self.session.scalar(statement)

    def list_chats(self, trip_id: int, user_id: int) -> list[AiChatSession]:
        statement = (
            select(AiChatSession)
            .where(AiChatSession.trip_id == trip_id, AiChatSession.user_id == user_id)
            .order_by(AiChatSession.updated_at.desc(), AiChatSession.chat_id.desc())
        )
        return list(self.session.scalars(statement))

    def add_message(self, message: AiChatMessage) -> AiChatMessage:
        self.session.add(message)
        self.session.flush()
        return message

    def find_message(self, chat_id: int, message_id: int) -> AiChatMessage | None:
        return self.session.scalar(
            select(AiChatMessage)
            .where(AiChatMessage.chat_id == chat_id, AiChatMessage.message_id == message_id)
            .execution_options(populate_existing=True)
        )

    def list_messages(
        self, chat_id: int, user_id: int, *, limit: int, before_id: int | None = None
    ) -> list[AiChatMessage]:
        """Read newest first; callers can request one extra row to detect another page."""
        statement = (
            select(AiChatMessage)
            .join(AiChatSession)
            .where(AiChatMessage.chat_id == chat_id, AiChatSession.user_id == user_id)
            .order_by(AiChatMessage.message_id.desc())
            .limit(limit)
        )
        if before_id is not None:
            statement = statement.where(AiChatMessage.message_id < before_id)
        return list(self.session.scalars(statement))

    def add_draft(self, draft: AiChatDraft) -> AiChatDraft:
        self.session.add(draft)
        self.session.flush()
        return draft

    def _owned_drafts(self, chat_id: int, user_id: int):
        return (
            select(AiChatDraft)
            .join(AiChatMessage)
            .join(AiChatSession)
            .where(AiChatMessage.chat_id == chat_id, AiChatSession.user_id == user_id)
        )

    def list_drafts(
        self, chat_id: int, user_id: int, message_ids: Sequence[int]
    ) -> list[AiChatDraft]:
        return list(
            self.session.scalars(
                self._owned_drafts(chat_id, user_id).where(AiChatDraft.message_id.in_(message_ids))
            )
        )

    def find_draft(
        self, chat_id: int, draft_id: int, user_id: int, *, lock: bool = False
    ) -> AiChatDraft | None:
        statement = self._owned_drafts(chat_id, user_id).where(AiChatDraft.draft_id == draft_id)
        if lock:
            statement = statement.with_for_update(of=AiChatDraft).execution_options(
                populate_existing=True
            )
        return self.session.scalar(statement)

    def add_proposal_links(self, draft_id: int, proposal_ids: Sequence[int]) -> None:
        self.session.add_all(
            AiChatDraftProposal(draft_id=draft_id, proposal_id=proposal_id)
            for proposal_id in proposal_ids
        )
        self.session.flush()

    def list_proposal_ids(self, draft_id: int) -> list[int]:
        return self.list_proposal_ids_by_draft([draft_id]).get(draft_id, [])

    def list_proposal_ids_by_draft(self, draft_ids: Sequence[int]) -> dict[int, list[int]]:
        if not draft_ids:
            return {}
        statement = (
            select(AiChatDraftProposal.draft_id, AiChatDraftProposal.proposal_id)
            .where(AiChatDraftProposal.draft_id.in_(draft_ids))
            .order_by(AiChatDraftProposal.draft_id, AiChatDraftProposal.proposal_id)
        )
        result: dict[int, list[int]] = {}
        for draft_id, proposal_id in self.session.execute(statement):
            result.setdefault(draft_id, []).append(proposal_id)
        return result

    def delete_chat(self, chat: AiChatSession) -> None:
        self.session.delete(chat)
        self.session.flush()
