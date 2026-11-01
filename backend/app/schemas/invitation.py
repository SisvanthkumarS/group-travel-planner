from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from backend.app.schemas.auth import UserNameInput


class CreateInvitationRequest(BaseModel):
    # The recipient must already have an account; this is not an email delivery API.
    email: EmailStr | None = None
    user_name: UserNameInput | None = None

    @field_validator("email", "user_name", mode="before")
    @classmethod
    def normalize_optional_identifier(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value

    @model_validator(mode="after")
    def require_recipient_identifier(self):
        if self.email is None and self.user_name is None:
            raise ValueError("Provide the recipient's email or user_name.")
        return self


class RespondInvitationRequest(BaseModel):
    invitation_id: Annotated[int, Field(gt=0)]
    # Request actions differ from the stored ACCEPTED / DECLINED states.
    decision: Literal["ACCEPT", "DECLINE"]


class InvitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    invitation_id: int
    trip_id: int
    invited_user_id: int
    invited_by_user_id: int
    status: Literal["PENDING", "ACCEPTED", "DECLINED"]
    created_at: datetime
    responded_at: datetime | None
