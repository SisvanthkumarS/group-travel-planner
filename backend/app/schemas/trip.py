from datetime import date, datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

NonBlankText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def validate_trip_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("timezone must be a valid IANA timezone, e.g. America/New_York.") from exc
    return value


TripTimezone = Annotated[NonBlankText, AfterValidator(validate_trip_timezone)]


class CreateTripRequest(BaseModel):
    # organizer_id comes from the authenticated user, never from this request.
    name: NonBlankText
    destination: NonBlankText
    start_date: date
    end_date: date
    timezone: TripTimezone = Field(
        description="IANA timezone used for the trip's calendar dates, e.g. America/New_York."
    )

    @model_validator(mode="after")
    def validate_dates(self):
        if self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date.")
        return self


class TripResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    trip_id: int
    name: str
    destination: str
    start_date: date
    end_date: date
    timezone: str
    organizer_id: int


class UpdateTripRequest(BaseModel):
    """Partial trip-update request VO; fields match CreateTripRequest."""

    model_config = ConfigDict(extra="forbid")

    name: NonBlankText | None = None
    destination: NonBlankText | None = None
    start_date: date | None = None
    end_date: date | None = None
    timezone: TripTimezone | None = Field(
        default=None,
        description="IANA timezone used for the trip's calendar dates, e.g. America/New_York.",
    )

    @model_validator(mode="after")
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError("Provide at least one trip field to update.")
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null.")
        # Validate the effective dates with CreateTripRequest in the Service:
        # an omitted date must be taken from the current persisted trip.
        return self


class TripMemberResponse(BaseModel):
    user_id: int
    user_name: str
    role: Literal["ORGANIZER", "MEMBER"]
    joined_at: datetime


class TripDetailResponse(TripResponse):
    members: list[TripMemberResponse]
