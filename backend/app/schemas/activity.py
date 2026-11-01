from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from backend.app.schemas.trip import NonBlankText


class CreateProposalRequest(BaseModel):
    title: NonBlankText
    description: NonBlankText
    estimated_cost: Decimal = Field(ge=0, allow_inf_nan=False)
    location: NonBlankText
    starts_at: AwareDatetime
    ends_at: AwareDatetime

    @model_validator(mode="after")
    def validate_times(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at.")
        return self


class OpenPollRequest(BaseModel):
    deadline: AwareDatetime = Field(description="Future deadline; voting stops at this instant.")


class VoteRequest(BaseModel):
    choice: Literal["YES", "NO"]


class ResolvePollRequest(BaseModel):
    decision: Literal["APPROVE", "REJECT"]


class VoteResponse(VoteRequest):
    model_config = ConfigDict(from_attributes=True)
    poll_id: int
    user_id: int
    updated_at: datetime


class PollResolution(ResolvePollRequest):
    resolved_by_user_id: int
    resolved_at: datetime


class PollResponse(BaseModel):
    poll_id: int
    proposal_id: int
    status: Literal["OPEN", "CLOSED", "CANCELED"]
    deadline: datetime
    opened_at: datetime
    closed_at: datetime | None
    outcome: Literal["APPROVED", "REJECTED", "TIED"] | None = Field(
        description="Original automatic poll outcome, retained after resolution and cancellation."
    )
    yes_count: int
    no_count: int
    total_votes: int
    eligible_voter_ids: list[int]
    votes: list[VoteResponse] = Field(description="One current counted choice per voter.")
    voting_history: list[VoteResponse] = Field(description="All changed choices in event order.")
    resolution: PollResolution | None


class ProposalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    proposal_id: int
    trip_id: int
    author_id: int
    title: str
    description: str
    estimated_cost: Decimal
    location: str
    starts_at: datetime
    ends_at: datetime
    status: Literal["PENDING", "OPEN", "TIED", "APPROVED", "REJECTED", "WITHDRAWN", "CANCELLED"]
    created_at: datetime
    poll: PollResponse | None = None


class ItineraryItemResponse(BaseModel):
    item_id: int
    trip_id: int
    proposal_id: int
    title: str
    description: str
    estimated_cost: Decimal
    location: str
    starts_at: datetime
    ends_at: datetime
    status: Literal["ACTIVE"]
