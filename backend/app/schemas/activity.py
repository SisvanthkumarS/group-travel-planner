from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from backend.app.schemas.trip import NonBlankText


class ProposalDetails(BaseModel):
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


Latitude = Annotated[float | None, Field(ge=-90, le=90, strict=True, allow_inf_nan=False)]
Longitude = Annotated[float | None, Field(ge=-180, le=180, strict=True, allow_inf_nan=False)]


class LocatedProposal(ProposalDetails):
    """Fully resolved proposal values persisted by the service."""

    latitude: Latitude = None
    longitude: Longitude = None
    attraction_id: int | None = None


class CreateProposalRequest(BaseModel):
    """Create a proposal at a curated attraction, a pinned place, or a named place.

    With `attraction_id`, the server copies the attraction's coordinates; omit
    `latitude`/`longitude`. `location` may be omitted or must equal the attraction
    name, and omitted `title`, `description` and `estimated_cost` default to the
    attraction's name, summary and typical cost (or 0). Without `attraction_id`,
    `title`, `description`, `estimated_cost` and `location` are required, and a
    pinned `latitude`/`longitude` pair is optional.
    """

    title: NonBlankText | None = None
    description: NonBlankText | None = None
    estimated_cost: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    location: NonBlankText | None = None
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    latitude: Latitude = None
    longitude: Longitude = None
    attraction_id: int | None = Field(
        default=None,
        gt=0,
        le=9223372036854775807,
        description="Active attraction selected on the map.",
    )

    @model_validator(mode="after")
    def validate_request(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at.")
        has_coordinates = self.latitude is not None or self.longitude is not None
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Provide latitude and longitude together.")
        if self.attraction_id is not None and has_coordinates:
            raise ValueError(
                "Omit latitude and longitude with attraction_id; "
                "the attraction's coordinates are used."
            )
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
    latitude: float | None = None
    longitude: float | None = None
    attraction_id: int | None = None
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
    latitude: float | None = None
    longitude: float | None = None
    attraction_id: int | None = None
    starts_at: datetime
    ends_at: datetime
    status: Literal["ACTIVE"]
