import logging
from datetime import UTC, datetime, timedelta
from typing import TypeGuard

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.app.core.AiChatClient import AiChatClient
from backend.app.core.config import get_settings
from backend.app.models.AiChat import AiChatDraft, AiChatMessage, AiChatSession
from backend.app.models.trip import Trip
from backend.app.repositories.ActivityRepository import ActivityRepository
from backend.app.repositories.AiChatRepository import AiChatRepository
from backend.app.schemas.AiChat import (
    AiChatContextResponse,
    AiChatCreateRequest,
    AiChatDraftContent,
    AiChatDraftDecisionRequest,
    AiChatDraftResponse,
    AiChatItineraryActivity,
    AiChatMessagePage,
    AiChatMessageResponse,
    AiChatModelReply,
    AiChatSendMessageRequest,
    AiChatSendMessageResponse,
    AiChatSessionResponse,
    AiChatSharedDraftResponse,
    AiChatSharedMessagePage,
    AiChatSharedMessageResponse,
    AiChatSharedReply,
)
from backend.app.services.ActivityService import ActivityService
from backend.app.services.TripService import TripService

logger = logging.getLogger(__name__)


class AiChatService:
    """Manage Trip chats and their AI replies."""

    def __init__(self, session: Session, client: AiChatClient | None = None):
        self.session = session
        self.repository = AiChatRepository(session)
        self.trip_service = TripService(session)
        self.client = client

    def create_chat(
        self, trip_id: int, body: AiChatCreateRequest, current_user_id: int
    ) -> AiChatSessionResponse:
        try:
            self.trip_service.require_trip_member(trip_id, current_user_id)
            chat = self.repository.add_chat(
                AiChatSession(trip_id=trip_id, user_id=current_user_id, title=body.title)
            )
            # Flush populates the database-generated ID and timestamps before commit.
            response = AiChatSessionResponse.model_validate(chat)
            self.session.commit()
            return response
        except Exception:
            self.session.rollback()
            raise

    def list_chats(self, trip_id: int, current_user_id: int) -> list[AiChatSessionResponse]:
        self.trip_service.require_trip_member(trip_id, current_user_id)
        chats = self.repository.list_chats(trip_id, current_user_id)
        return [AiChatSessionResponse.model_validate(chat) for chat in chats]

    def get_chat_context(self, chat_id: int, current_user_id: int) -> AiChatContextResponse:
        chat = self.repository.find_chat(chat_id, current_user_id)
        if chat is None:
            raise HTTPException(404, detail="Chat not found")
        trip = self.trip_service.require_trip_member(chat.trip_id, current_user_id)
        return self._build_chat_context(trip, datetime.now(UTC))

    def get_shared_context(self, trip_id: int, user_id: int) -> AiChatContextResponse:
        trip = self.trip_service.require_trip_member(trip_id, user_id)
        return self._build_chat_context(trip, datetime.now(UTC))

    def _build_chat_context(self, trip: Trip, now: datetime) -> AiChatContextResponse:
        return AiChatContextResponse(
            current_time=now,
            name=trip.name,
            destination=trip.destination,
            start_date=trip.start_date,
            end_date=trip.end_date,
            timezone=trip.timezone,
            itinerary=[
                AiChatItineraryActivity.model_validate(proposal)
                for _, proposal in ActivityRepository(self.session).itinerary(trip.trip_id)
            ],
        )

    def list_messages(
        self, chat_id: int, current_user_id: int, *, before_id: int | None, limit: int
    ) -> AiChatMessagePage:
        chat = self.repository.find_chat(chat_id, current_user_id)
        if chat is None:
            raise HTTPException(404, detail="Chat not found")
        self.trip_service.require_trip_member(chat.trip_id, current_user_id)

        return self._message_page(chat_id, current_user_id, before_id=before_id, limit=limit)

    def list_shared_messages(
        self, trip_id: int, user_id: int, *, before_id: int | None, limit: int
    ) -> AiChatSharedMessagePage:
        self.trip_service.require_trip_member(trip_id, user_id)
        chat = self.repository.find_shared_chat(trip_id)
        if chat is None:
            return AiChatSharedMessagePage(messages=[], next_before_id=None)
        return self._message_page(chat.chat_id, None, before_id=before_id, limit=limit)

    def _message_page(
        self, chat_id: int, owner_id: int | None, *, before_id: int | None, limit: int
    ) -> AiChatMessagePage:
        page_type = AiChatSharedMessagePage if owner_id is None else AiChatMessagePage
        message_type = AiChatSharedMessageResponse if owner_id is None else AiChatMessageResponse
        rows = self.repository.list_messages(
            chat_id, owner_id, before_id=before_id, limit=limit + 1
        )
        messages = rows[:limit]
        if not messages:
            return page_type(messages=[], next_before_id=None)

        drafts = self.repository.list_drafts(
            chat_id, owner_id, [message.message_id for message in messages]
        )
        # A draft read as pending must not expose links from a concurrent acceptance.
        proposal_ids = self.repository.list_proposal_ids_by_draft(
            [draft.draft_id for draft in drafts if draft.status == "ACCEPTED"]
        )
        shared = owner_id is None
        authors = (
            self.repository.question_authors(chat_id, [draft.message_id for draft in drafts])
            if shared
            else {}
        )
        drafts_by_message = {
            draft.message_id: self._draft_response(
                draft,
                proposal_ids.get(draft.draft_id, []),
                shared=shared,
                asked_by_user_id=authors.get(draft.message_id),
            )
            for draft in drafts
        }
        return page_type(
            messages=[
                message_type.model_validate(message).model_copy(
                    update={"draft": drafts_by_message.get(message.message_id)}
                )
                for message in messages
            ],
            next_before_id=messages[-1].message_id if len(rows) > limit else None,
        )

    @staticmethod
    def _draft_response(
        draft: AiChatDraft,
        proposal_ids: list[int],
        *,
        shared: bool,
        asked_by_user_id: int | None = None,
    ) -> AiChatDraftResponse:
        fields = {
            "draft_id": draft.draft_id,
            "message_id": draft.message_id,
            "kind": draft.kind,
            "proposals": draft.proposals,
            "status": draft.status,
            "created_at": draft.created_at,
            "decided_at": draft.decided_at,
            "proposal_ids": proposal_ids,
        }
        if shared:
            fields["asked_by_user_id"] = asked_by_user_id
            return AiChatSharedDraftResponse.model_validate(fields)
        return AiChatDraftResponse.model_validate(fields)

    def _get_or_create_shared_chat(self, trip_id: int) -> AiChatSession:
        # The caller holds the Trip lock, including when the room does not exist yet.
        chat = self.repository.find_shared_chat(trip_id, lock=True)
        if chat is None:
            chat = self.repository.add_chat(AiChatSession(trip_id=trip_id, title="Trip chat"))
        return chat

    def _add_user_message(self, chat_id: int, user_id: int, content: str) -> AiChatMessage:
        return self.repository.add_message(
            AiChatMessage(
                chat_id=chat_id, user_id=user_id, role="USER", content=content, status="COMPLETED"
            )
        )

    def post_shared_message(
        self, trip_id: int, body: AiChatSendMessageRequest, user_id: int
    ) -> AiChatSharedMessageResponse:
        try:
            self.trip_service.require_trip_member(trip_id, user_id, lock=True)
            chat = self._get_or_create_shared_chat(trip_id)
            message = self._add_user_message(chat.chat_id, user_id, body.content)
            chat.updated_at = datetime.now(UTC)
            response = AiChatSharedMessageResponse.model_validate(message)
            self.session.commit()
            return response
        except Exception:
            self.session.rollback()
            raise

    def ask_shared_chat(
        self, trip_id: int, body: AiChatSendMessageRequest, user_id: int
    ) -> AiChatSharedReply:
        return self._generate_reply(trip_id, body, user_id, shared=True)

    def send_message(
        self, chat_id: int, body: AiChatSendMessageRequest, current_user_id: int
    ) -> AiChatSendMessageResponse:
        return self._generate_reply(chat_id, body, current_user_id, shared=False)

    def _generate_reply(
        self, target_id: int, body: AiChatSendMessageRequest, current_user_id: int, *, shared: bool
    ) -> AiChatSendMessageResponse:
        chat_scope = None if shared else current_user_id
        message_type = AiChatSharedMessageResponse if shared else AiChatMessageResponse
        reply_type = AiChatSharedReply if shared else AiChatSendMessageResponse
        try:
            if shared:
                trip = self.trip_service.require_trip_member(target_id, current_user_id, lock=True)
                chat = self._get_or_create_shared_chat(target_id)
            else:
                chat = self._lock_owned_chat(target_id, current_user_id)
                trip = self.trip_service.require_trip_member(chat.trip_id, current_user_id)
            if self.client is None:
                raise HTTPException(503, detail="AI provider is not configured.")

            chat_id = chat.chat_id
            now = datetime.now(UTC)
            history = self.repository.list_messages(
                chat_id, chat_scope, limit=20, completed_only=shared
            )
            generating = (
                self.repository.generating_messages(chat_id)
                if shared
                else [history[0]]
                if history and self._is_generating(history[0])
                else []
            )
            for previous in generating:
                stale_after = timedelta(seconds=max(300, get_settings().openai_timeout_seconds * 2))
                if now - previous.created_at < stale_after:
                    raise HTTPException(409, detail="Wait for the previous AI reply to finish.")
                # Recover an orphaned placeholder before starting a new turn.
                previous.status = "FAILED"

            # Snapshot plain data before commit so generation never reads expired ORM objects.
            trip_context = self._build_chat_context(trip, now).model_dump(mode="json")
            messages = [
                {
                    "role": message.role.lower(),
                    "content": (
                        f"Trip member {message.user_id}: {message.content}"
                        if shared and message.role == "USER" and message.user_id is not None
                        else message.content
                    ),
                }
                for message in reversed(history)
                if message.status == "COMPLETED"
            ]
            messages.append({"role": "user", "content": body.content})
            user_message = self._add_user_message(chat_id, current_user_id, body.content)
            assistant = self.repository.add_message(
                AiChatMessage(
                    chat_id=chat_id,
                    role="ASSISTANT",
                    content="",
                    status="GENERATING",
                    reply_to_message_id=user_message.message_id,
                )
            )
            chat.updated_at = datetime.now(UTC)
            user_response = message_type.model_validate(user_message)
            assistant_id = assistant.message_id
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        try:
            reply = AiChatModelReply.model_validate(
                self.client.generate(messages=messages, trip_context=trip_context)
            )
        except TimeoutError:
            self._mark_generation_failed(chat_id, assistant_id, chat_scope)
            raise HTTPException(504, detail="AI provider timed out.") from None
        except Exception:
            self._mark_generation_failed(chat_id, assistant_id, chat_scope)
            raise HTTPException(
                502, detail="AI provider could not generate a valid reply."
            ) from None

        try:
            if shared:
                trip = self.trip_service.require_trip_member(target_id, current_user_id, lock=True)
                chat = self.repository.find_shared_chat(target_id, lock=True)
                if chat is None or chat.chat_id != chat_id:
                    raise HTTPException(404, detail="Chat not found")
            else:
                chat = self._lock_owned_chat(chat_id, current_user_id)
                trip = self.trip_service.require_trip_member(chat.trip_id, current_user_id)
            assistant = self.repository.find_message(chat_id, assistant_id)
            if not self._is_generating(assistant):
                raise HTTPException(409, detail="AI reply is no longer being generated.")

            draft_response = None
            if reply.draft is not None:
                activity_service = ActivityService(self.session)
                now = datetime.now(UTC)
                try:
                    for proposal in reply.draft.proposals:
                        activity_service.validate_proposal_schedule(trip, proposal, now)
                    self._validate_draft_overlaps(trip.trip_id, reply.draft)
                except HTTPException:
                    raise HTTPException(
                        502, detail="AI provider generated a draft with an invalid schedule."
                    ) from None
                activity_service.validate_proposal_capacity(
                    trip.trip_id, len(reply.draft.proposals)
                )
                draft = self.repository.add_draft(
                    AiChatDraft(
                        message_id=assistant_id,
                        status="PENDING",
                        **reply.draft.model_dump(mode="json"),
                    )
                )
                draft_response = self._draft_response(
                    draft, [], shared=shared, asked_by_user_id=current_user_id
                )
            assistant.content = reply.content
            assistant.status = "COMPLETED"
            chat.updated_at = datetime.now(UTC)
            response = reply_type(
                user_message=user_response,
                assistant_message=message_type.model_validate(assistant).model_copy(
                    update={"draft": draft_response}
                ),
            )
            self.session.commit()
            return response
        except Exception:
            self.session.rollback()
            self._mark_generation_failed(chat_id, assistant_id, chat_scope)
            raise

    def _lock_owned_chat(self, chat_id: int, current_user_id: int) -> AiChatSession:
        chat = self.repository.find_chat(chat_id, current_user_id, lock=True)
        if chat is None:
            raise HTTPException(404, detail="Chat not found")
        return chat

    def _validate_draft_overlaps(self, trip_id: int, draft: AiChatDraftContent) -> None:
        proposed = sorted(draft.proposals, key=lambda proposal: proposal.starts_at)
        if any(left.ends_at > right.starts_at for left, right in zip(proposed, proposed[1:])):
            raise HTTPException(422, detail="Activities in the draft overlap.")

        itinerary = ActivityRepository(self.session).itinerary(trip_id)
        if any(
            proposal.starts_at < existing.ends_at and existing.starts_at < proposal.ends_at
            for proposal in proposed
            for _, existing in itinerary
        ):
            raise HTTPException(422, detail="A draft activity overlaps the existing itinerary.")

    @staticmethod
    def _is_generating(message: AiChatMessage | None) -> TypeGuard[AiChatMessage]:
        return (
            message is not None and message.role == "ASSISTANT" and message.status == "GENERATING"
        )

    def _mark_generation_failed(self, chat_id: int, message_id: int, owner_id: int | None) -> None:
        """Best-effort cleanup of this request's already committed placeholder."""
        try:
            chat = self.repository.find_chat(chat_id, owner_id, lock=True)
            if chat is not None:
                message = self.repository.find_message(chat_id, message_id)
                if self._is_generating(message):
                    message.status = "FAILED"
                    chat.updated_at = datetime.now(UTC)
                    self.session.commit()
                    return
            self.session.rollback()
        except Exception:
            self.session.rollback()
            logger.warning("Unable to mark AI chat message %s as failed.", message_id)

    def decide_draft(
        self, chat_id: int, draft_id: int, body: AiChatDraftDecisionRequest, current_user_id: int
    ) -> AiChatDraftResponse:
        return self._decide_draft(chat_id, draft_id, body, current_user_id, shared=False)

    def decide_shared_draft(
        self, trip_id: int, draft_id: int, body: AiChatDraftDecisionRequest, user_id: int
    ) -> AiChatSharedDraftResponse:
        return self._decide_draft(trip_id, draft_id, body, user_id, shared=True)

    def _decide_draft(
        self,
        target_id: int,
        draft_id: int,
        body: AiChatDraftDecisionRequest,
        current_user_id: int,
        *,
        shared: bool,
    ) -> AiChatDraftResponse:
        try:
            # Serialize capacity checks with manual proposal creation, then lock the draft.
            if shared:
                trip = self.trip_service.require_trip_member(target_id, current_user_id, lock=True)
                chat = self.repository.find_shared_chat(target_id, lock=True)
                if chat is None:
                    raise HTTPException(404, detail="Draft not found.")
            else:
                chat = self.repository.find_chat(target_id, current_user_id)
                if chat is None:
                    raise HTTPException(404, detail="Chat not found.")
                trip = self.trip_service.require_trip_member(
                    chat.trip_id, current_user_id, lock=True
                )
                chat = self._lock_owned_chat(target_id, current_user_id)
            draft = self.repository.find_draft(
                chat.chat_id, draft_id, None if shared else current_user_id, lock=True
            )
            if draft is None:
                raise HTTPException(404, detail="Draft not found.")
            asked_by_user_id = None
            if shared:
                authors = self.repository.question_authors(chat.chat_id, [draft.message_id])
                asked_by_user_id = authors.get(draft.message_id)
                if asked_by_user_id != current_user_id:
                    raise HTTPException(
                        403, detail="Only the member who asked AI can decide this draft."
                    )

            target_status = "ACCEPTED" if body.decision == "ACCEPT" else "REJECTED"
            proposal_ids = []
            if draft.status == target_status:
                if target_status == "ACCEPTED":
                    proposal_ids = self.repository.list_proposal_ids(draft_id)
            elif draft.status != "PENDING":
                raise HTTPException(409, detail="Draft has already been decided.")
            else:
                if target_status == "ACCEPTED":
                    try:
                        content = AiChatDraftContent.model_validate(
                            {"kind": draft.kind, "proposals": draft.proposals}
                        )
                    except ValidationError as exc:
                        raise HTTPException(
                            422, detail="Draft contains invalid proposals."
                        ) from exc
                    self._validate_draft_overlaps(trip.trip_id, content)
                    proposals = ActivityService(self.session).add_pending_proposals(
                        trip, content.proposals, current_user_id
                    )
                    proposal_ids = [proposal.proposal_id for proposal in proposals]
                    self.repository.add_proposal_links(draft_id, proposal_ids)

                draft.status = target_status
                draft.decided_at = datetime.now(UTC)

            response = self._draft_response(
                draft, proposal_ids, shared=shared, asked_by_user_id=asked_by_user_id
            )
            self.session.commit()
            return response
        except Exception:
            self.session.rollback()
            raise

    def delete_chat(self, chat_id: int, current_user_id: int) -> None:
        try:
            chat = self.repository.find_chat(chat_id, current_user_id)
            if chat is None:
                raise HTTPException(404, detail="Chat not found")

            # Use the same Trip-before-chat lock order as draft decisions.
            self.trip_service.require_trip_member(chat.trip_id, current_user_id, lock=True)
            chat = self._lock_owned_chat(chat_id, current_user_id)
            self.repository.delete_chat(chat)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
