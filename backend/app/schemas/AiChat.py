from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from backend.app.schemas.activity import CreateProposalRequest

AiChatDraftKind = Literal["PROPOSAL", "ITINERARY"]
AiChatDraftStatus = Literal["PENDING", "ACCEPTED", "REJECTED"]
AiChatMessageStatus = Literal["PENDING", "GENERATING", "COMPLETED", "FAILED", "CANCELLED"]
AiChatRole = Literal["USER", "ASSISTANT"]


class AiChatCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
    ] = "New chat"


class AiChatSendMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class AiChatDraftDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["ACCEPT", "REJECT"]


class AiChatDraftContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: AiChatDraftKind
    proposals: list[CreateProposalRequest] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_proposal_count(self):
        if self.kind == "PROPOSAL" and len(self.proposals) != 1:
            raise ValueError("A proposal draft must contain exactly one proposal.")
        if self.kind == "ITINERARY" and len(self.proposals) < 2:
            raise ValueError("An itinerary draft must contain at least two proposals.")
        return self


class AiChatModelReply(BaseModel):
    """Structured output expected from an AI provider."""

    model_config = ConfigDict(extra="forbid")

    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    draft: AiChatDraftContent | None = None


class AiChatDraftResponse(AiChatDraftContent):
    model_config = ConfigDict(from_attributes=True)

    draft_id: int
    message_id: int
    status: AiChatDraftStatus
    created_at: datetime
    decided_at: datetime | None
    proposal_ids: list[int]


class AiChatSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chat_id: int
    trip_id: int
    user_id: int
    title: str
    created_at: datetime
    updated_at: datetime


class AiChatItineraryActivity(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    description: str
    location: str
    estimated_cost: Decimal
    starts_at: datetime
    ends_at: datetime


class AiChatContextResponse(BaseModel):
    current_time: datetime
    name: str
    destination: str
    start_date: date
    end_date: date
    timezone: str
    itinerary: list[AiChatItineraryActivity]


class AiChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message_id: int
    chat_id: int
    role: AiChatRole
    content: str
    status: AiChatMessageStatus
    created_at: datetime
    draft: AiChatDraftResponse | None = None


class AiChatMessagePage(BaseModel):
    messages: list[AiChatMessageResponse]
    next_before_id: int | None


class AiChatSendMessageResponse(BaseModel):
    user_message: AiChatMessageResponse
    assistant_message: AiChatMessageResponse
