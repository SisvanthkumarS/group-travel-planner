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
)
from backend.app.services.ActivityService import ActivityService
from backend.app.services.TripService import TripService

logger = logging.getLogger(__name__)


class AiChatService:
    """Manage private trip chat sessions."""

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

        rows = self.repository.list_messages(
            chat_id, current_user_id, before_id=before_id, limit=limit + 1
        )
        messages = rows[:limit]
        if not messages:
            return AiChatMessagePage(messages=[], next_before_id=None)

        drafts = self.repository.list_drafts(
            chat_id, current_user_id, [message.message_id for message in messages]
        )
        # A draft read as pending must not expose links from a concurrent acceptance.
        proposal_ids = self.repository.list_proposal_ids_by_draft(
            [draft.draft_id for draft in drafts if draft.status == "ACCEPTED"]
        )
        drafts_by_message = {
            draft.message_id: AiChatDraftResponse(
                draft_id=draft.draft_id,
                message_id=draft.message_id,
                kind=draft.kind,
                proposals=draft.proposals,
                status=draft.status,
                created_at=draft.created_at,
                decided_at=draft.decided_at,
                proposal_ids=proposal_ids.get(draft.draft_id, []),
            )
            for draft in drafts
        }
        return AiChatMessagePage(
            messages=[
                AiChatMessageResponse.model_validate(message).model_copy(
                    update={"draft": drafts_by_message.get(message.message_id)}
                )
                for message in messages
            ],
            next_before_id=messages[-1].message_id if len(rows) > limit else None,
        )

    def send_message(
        self, chat_id: int, body: AiChatSendMessageRequest, current_user_id: int
    ) -> AiChatSendMessageResponse:
        try:
            chat = self._lock_owned_chat(chat_id, current_user_id)
            trip = self.trip_service.require_trip_member(chat.trip_id, current_user_id)
            if self.client is None:
                raise HTTPException(503, detail="AI provider is not configured.")

            history = self.repository.list_messages(chat_id, current_user_id, limit=20)
            now = datetime.now(UTC)
            if history and history[0].status == "GENERATING":
                previous = history[0]
                stale_after = timedelta(seconds=max(300, get_settings().openai_timeout_seconds * 2))
                if now - previous.created_at < stale_after:
                    raise HTTPException(409, detail="Wait for the previous AI reply to finish.")
                # Recover an orphaned placeholder before starting a new turn.
                previous.status = "FAILED"

            # Snapshot plain data before commit so generation never reads expired ORM objects.
            trip_context = self._build_chat_context(trip, now).model_dump(mode="json")
            messages = [
                {"role": message.role.lower(), "content": message.content}
                for message in reversed(history)
                if message.status == "COMPLETED"
            ]
            messages.append({"role": "user", "content": body.content})
            user_message = self.repository.add_message(
                AiChatMessage(
                    chat_id=chat_id, role="USER", content=body.content, status="COMPLETED"
                )
            )
            assistant = self.repository.add_message(
                AiChatMessage(chat_id=chat_id, role="ASSISTANT", content="", status="GENERATING")
            )
            chat.updated_at = datetime.now(UTC)
            user_response = AiChatMessageResponse.model_validate(user_message)
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
            self._mark_generation_failed(chat_id, assistant_id, current_user_id)
            raise HTTPException(504, detail="AI provider timed out.") from None
        except Exception:
            self._mark_generation_failed(chat_id, assistant_id, current_user_id)
            raise HTTPException(
                502, detail="AI provider could not generate a valid reply."
            ) from None

        try:
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
                draft_response = AiChatDraftResponse(
                    draft_id=draft.draft_id,
                    message_id=draft.message_id,
                    kind=draft.kind,
                    proposals=draft.proposals,
                    status=draft.status,
                    created_at=draft.created_at,
                    decided_at=draft.decided_at,
                    proposal_ids=[],
                )
            assistant.content = reply.content
            assistant.status = "COMPLETED"
            chat.updated_at = datetime.now(UTC)
            response = AiChatSendMessageResponse(
                user_message=user_response,
                assistant_message=AiChatMessageResponse.model_validate(assistant).model_copy(
                    update={"draft": draft_response}
                ),
            )
            self.session.commit()
            return response
        except Exception:
            self.session.rollback()
            self._mark_generation_failed(chat_id, assistant_id, current_user_id)
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

    def _mark_generation_failed(self, chat_id: int, message_id: int, user_id: int) -> None:
        """Best-effort cleanup of this request's already committed placeholder."""
        try:
            chat = self.repository.find_chat(chat_id, user_id, lock=True)
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
        try:
            chat = self.repository.find_chat(chat_id, current_user_id)
            if chat is None:
                raise HTTPException(404, detail="Chat not found.")

            # Serialize capacity checks with manual proposal creation, then lock the draft.
            trip = self.trip_service.require_trip_member(chat.trip_id, current_user_id, lock=True)
            self._lock_owned_chat(chat_id, current_user_id)
            draft = self.repository.find_draft(chat_id, draft_id, current_user_id, lock=True)
            if draft is None:
                raise HTTPException(404, detail="Draft not found.")

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

            response = AiChatDraftResponse(
                draft_id=draft.draft_id,
                message_id=draft.message_id,
                kind=draft.kind,
                proposals=draft.proposals,
                status=draft.status,
                created_at=draft.created_at,
                decided_at=draft.decided_at,
                proposal_ids=proposal_ids,
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
