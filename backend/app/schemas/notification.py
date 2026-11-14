from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool


class TestEmailResponse(BaseModel):
    status: Literal["accepted"] = "accepted"
    message_id: str


NotificationType = Literal[
    "INVITATION_RECEIVED",
    "INVITATION_ACCEPTED",
    "INVITATION_DECLINED",
    "PROPOSAL_CREATED",
    "POLL_OPENED",
    "POLL_TIED",
    "ACTIVITY_APPROVED",
    "ACTIVITY_REJECTED",
    "ACTIVITY_CANCELLED",
    "TRIP_DELETED",
]


class NotificationPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    in_app_enabled: StrictBool = Field(
        description="Create future in-app notifications. Initially true."
    )
    email_enabled: StrictBool = Field(
        description="Queue future notification emails. Initially false."
    )


class NotificationResponse(BaseModel):
    notification_id: int
    event_type: NotificationType
    title: str
    message: str
    trip_name: str
    trip_id: int | None
    proposal_id: int | None
    invitation_id: int | None
    created_at: datetime
    read_at: datetime | None
    action_url: str | None = Field(
        description=(
            "Relative app path; null when the trip was deleted. "
            "Use resource IDs to focus a proposal/invitation."
        )
    )


class NotificationPage(BaseModel):
    items: list[NotificationResponse]
    next_before_id: int | None


class UnreadCountResponse(BaseModel):
    unread_count: int


class MarkAllReadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    through_id: int | None = Field(
        default=None,
        gt=0,
        description=(
            "Optional newest loaded ID; newer notifications remain unread. "
            "Omit to mark all currently visible rows."
        ),
    )


class MarkAllReadResponse(BaseModel):
    updated_count: int
