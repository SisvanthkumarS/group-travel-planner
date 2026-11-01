from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

NonBlankText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class CreateTripRequest(BaseModel):
    # organizer_id comes from the authenticated user, never from this request.
    name: NonBlankText
    destination: NonBlankText
    start_date: date
    end_date: date

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
    organizer_id: int


class TripMemberResponse(BaseModel):
    user_id: int
    user_name: str
    role: Literal["ORGANIZER", "MEMBER"]
    joined_at: datetime


class TripDetailResponse(TripResponse):
    members: list[TripMemberResponse]
