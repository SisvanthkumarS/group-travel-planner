from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from sqlalchemy.orm import Session

from backend.app.core.AiChatClient import AiChatClient, get_ai_chat_client
from backend.app.core.database import get_session
from backend.app.schemas.AiChat import (
    AiChatContextResponse,
    AiChatCreateRequest,
    AiChatDraftDecisionRequest,
    AiChatDraftResponse,
    AiChatMessagePage,
    AiChatSendMessageRequest,
    AiChatSendMessageResponse,
    AiChatSessionResponse,
    AiChatSharedMessagePage,
    AiChatSharedMessageResponse,
    AiChatSharedReply,
)
from backend.app.services.AiChatService import AiChatService

router = APIRouter(
    tags=["AI Chat"],
    responses={
        401: {"description": "Authentication required."},
        403: {"description": "Trip membership or chat ownership required."},
        404: {"description": "Trip, chat, or draft not found."},
    },
)


def get_ai_chat_service(
    session: Annotated[Session, Depends(get_session)],
    client: Annotated[AiChatClient | None, Depends(get_ai_chat_client)],
) -> AiChatService:
    return AiChatService(session, client)


AiChatServiceDependency = Annotated[AiChatService, Depends(get_ai_chat_service)]
AiChatId = Annotated[int, Path(gt=0, le=2**63 - 1)]
AiChatBeforeId = Annotated[int | None, Query(gt=0, le=2**63 - 1)]
AiChatPageSize = Annotated[int, Query(ge=1, le=100)]


@router.get("/trips/{trip_id}/chat/context", response_model=AiChatContextResponse)
def get_shared_context(
    trip_id: AiChatId, request: Request, service: AiChatServiceDependency
) -> AiChatContextResponse:
    """Read the Trip and active itinerary used to answer AI questions."""
    return service.get_shared_context(trip_id, request.state.current_user.user_id)


@router.get("/trips/{trip_id}/chat/messages", response_model=AiChatSharedMessagePage)
def list_shared_messages(
    trip_id: AiChatId,
    request: Request,
    service: AiChatServiceDependency,
    before_id: AiChatBeforeId = None,
    limit: AiChatPageSize = 30,
) -> AiChatSharedMessagePage:
    """Read the Trip's shared messages in newest-first order."""
    return service.list_shared_messages(
        trip_id, request.state.current_user.user_id, before_id=before_id, limit=limit
    )


@router.post(
    "/trips/{trip_id}/chat/messages",
    response_model=AiChatSharedMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_shared_message(
    trip_id: AiChatId,
    body: AiChatSendMessageRequest,
    request: Request,
    service: AiChatServiceDependency,
) -> AiChatSharedMessageResponse:
    """Post a group message without calling AI."""
    return service.post_shared_message(trip_id, body, request.state.current_user.user_id)


@router.post(
    "/trips/{trip_id}/chat/ask-ai",
    response_model=AiChatSharedReply,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {"description": "Generation conflict or the trip proposal limit is reached."},
        502: {"description": "The AI provider failed or returned an invalid reply."},
        503: {"description": "No AI provider is configured."},
        504: {"description": "The AI provider timed out."},
    },
)
def ask_shared_chat(
    trip_id: AiChatId,
    body: AiChatSendMessageRequest,
    request: Request,
    service: AiChatServiceDependency,
) -> AiChatSharedReply:
    """Ask AI using the preceding group messages and the current itinerary."""
    return service.ask_shared_chat(trip_id, body, request.state.current_user.user_id)


@router.patch(
    "/trips/{trip_id}/chat/drafts/{draft_id}",
    response_model=AiChatDraftResponse,
    responses={
        409: {"description": "Draft decision conflicts or the trip proposal limit is reached."},
        422: {"description": "Invalid decision or draft proposals."},
    },
)
def decide_shared_draft(
    trip_id: AiChatId,
    draft_id: AiChatId,
    body: AiChatDraftDecisionRequest,
    request: Request,
    service: AiChatServiceDependency,
) -> AiChatDraftResponse:
    """Accept or reject a draft as the member who asked AI."""
    return service.decide_shared_draft(trip_id, draft_id, body, request.state.current_user.user_id)


@router.post(
    "/trips/{trip_id}/chats",
    deprecated=True,
    response_model=AiChatSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_chat(
    trip_id: AiChatId,
    body: AiChatCreateRequest,
    request: Request,
    service: AiChatServiceDependency,
) -> AiChatSessionResponse:
    """Create a private chat in a trip the current user belongs to."""
    return service.create_chat(trip_id, body, request.state.current_user.user_id)


@router.get("/trips/{trip_id}/chats", response_model=list[AiChatSessionResponse], deprecated=True)
def list_chats(
    trip_id: AiChatId, request: Request, service: AiChatServiceDependency
) -> list[AiChatSessionResponse]:
    """List the current user's chats in the trip, most recently updated first."""
    return service.list_chats(trip_id, request.state.current_user.user_id)


@router.get("/chats/{chat_id}/context", response_model=AiChatContextResponse, deprecated=True)
def get_chat_context(
    chat_id: AiChatId, request: Request, service: AiChatServiceDependency
) -> AiChatContextResponse:
    """Read the current trip and active itinerary used as AI chat context."""
    return service.get_chat_context(chat_id, request.state.current_user.user_id)


@router.get("/chats/{chat_id}/messages", response_model=AiChatMessagePage, deprecated=True)
def list_messages(
    chat_id: AiChatId,
    request: Request,
    service: AiChatServiceDependency,
    before_id: AiChatBeforeId = None,
    limit: AiChatPageSize = 30,
) -> AiChatMessagePage:
    """Read messages and their drafts, newest first, with an exclusive before_id cursor."""
    return service.list_messages(
        chat_id, request.state.current_user.user_id, before_id=before_id, limit=limit
    )


@router.post(
    "/chats/{chat_id}/messages",
    deprecated=True,
    response_model=AiChatSendMessageResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {"description": "Generation conflict or the trip proposal limit is reached."},
        502: {"description": "The AI provider failed or returned an invalid reply."},
        503: {"description": "No AI provider is configured."},
        504: {"description": "The AI provider timed out."},
    },
)
def send_message(
    chat_id: AiChatId,
    body: AiChatSendMessageRequest,
    request: Request,
    service: AiChatServiceDependency,
) -> AiChatSendMessageResponse:
    """Send a message and receive an AI reply that can contain a draft."""
    return service.send_message(chat_id, body, request.state.current_user.user_id)


@router.patch(
    "/chats/{chat_id}/drafts/{draft_id}",
    deprecated=True,
    response_model=AiChatDraftResponse,
    responses={
        409: {"description": "Draft decision conflicts or the trip proposal limit is reached."},
        422: {"description": "Invalid decision or draft proposals."},
    },
)
def decide_draft(
    chat_id: AiChatId,
    draft_id: AiChatId,
    body: AiChatDraftDecisionRequest,
    request: Request,
    service: AiChatServiceDependency,
) -> AiChatDraftResponse:
    """Accept or reject a draft. Accepted proposals enter the existing PENDING workflow."""
    return service.decide_draft(chat_id, draft_id, body, request.state.current_user.user_id)


@router.delete("/chats/{chat_id}", status_code=status.HTTP_204_NO_CONTENT, deprecated=True)
def delete_chat(chat_id: AiChatId, request: Request, service: AiChatServiceDependency) -> Response:
    """Delete a chat and its drafts while preserving submitted proposals."""
    service.delete_chat(chat_id, request.state.current_user.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
