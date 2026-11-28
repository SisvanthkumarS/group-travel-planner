from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    field_serializer,
    model_validator,
)


def _blank_to_none(value):
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _upper(value):
    return value.strip().upper() if isinstance(value, str) else value


Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Summary = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
OptionalText = Annotated[
    Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None,
    BeforeValidator(_blank_to_none),
]
LongText = Annotated[
    Annotated[str, StringConstraints(strip_whitespace=True, max_length=10000)] | None,
    BeforeValidator(_blank_to_none),
]
Currency = Annotated[
    Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")] | None,
    BeforeValidator(_blank_to_none),
    BeforeValidator(_upper),
]
OptionalUrl = Annotated[HttpUrl | None, BeforeValidator(_blank_to_none)]
Latitude = Annotated[float, Field(ge=-90, le=90, strict=True, allow_inf_nan=False)]
Longitude = Annotated[float, Field(ge=-180, le=180, strict=True, allow_inf_nan=False)]
Duration = Annotated[int, Field(gt=0, le=1440, description="Typical visit length in minutes.")]
Cost = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]


class AttractionFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    latitude: Latitude
    longitude: Longitude
    summary: Summary = Field(description="Short introduction shown in the map pop-up.")
    city: OptionalText = None
    country: OptionalText = None
    address: OptionalText = None
    category: OptionalText = None
    description: LongText = Field(default=None, description="Full introduction.")
    image_url: OptionalUrl = None
    opening_hours: OptionalText = None
    suggested_duration_minutes: Duration | None = None
    typical_cost: Cost | None = Field(
        default=None, description="Approximate cost per person, in `currency`."
    )
    currency: Currency = Field(default=None, description="ISO 4217 code, for example USD.")

    @field_serializer("image_url")
    def serialize_url(self, value: HttpUrl | None) -> str | None:
        return None if value is None else str(value)


class CreateAttractionRequest(AttractionFields):
    is_active: bool = True


class UpdateAttractionRequest(BaseModel):
    """Partial update. Optional details may be cleared with null."""

    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    summary: Summary | None = None
    city: OptionalText = None
    country: OptionalText = None
    address: OptionalText = None
    category: OptionalText = None
    description: LongText = None
    image_url: OptionalUrl = None
    opening_hours: OptionalText = None
    suggested_duration_minutes: Duration | None = None
    typical_cost: Cost | None = None
    currency: Currency = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError("Provide at least one attraction field to update.")
        for field in ("name", "latitude", "longitude", "summary", "is_active"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null.")
        return self

    @field_serializer("image_url")
    def serialize_url(self, value: HttpUrl | None) -> str | None:
        return None if value is None else str(value)


class ImportAttractionsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attractions: list[CreateAttractionRequest] = Field(min_length=1, max_length=500)


class AttractionSummaryResponse(BaseModel):
    """Lightweight map marker."""

    model_config = ConfigDict(from_attributes=True)

    attraction_id: int
    name: str
    latitude: float
    longitude: float
    category: str | None
    city: str | None
    summary: str


class AttractionResponse(AttractionSummaryResponse):
    country: str | None
    address: str | None
    description: str | None
    image_url: str | None
    opening_hours: str | None
    suggested_duration_minutes: int | None
    typical_cost: Decimal | None
    currency: str | None


class AdminAttractionResponse(AttractionResponse):
    is_active: bool
    created_by_user_id: int | None
    created_at: datetime
    updated_at: datetime


class ImportAttractionsResponse(BaseModel):
    created: int
    updated: int
    attractions: list[AdminAttractionResponse]
