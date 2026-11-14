from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from sqlalchemy.orm import Session

from backend.app.core.config import Settings, get_settings
from backend.app.core.database import get_session
from backend.app.schemas.notification import (
    MarkAllReadRequest,
    MarkAllReadResponse,
    NotificationPage,
    NotificationPreferences,
    NotificationResponse,
    TestEmailResponse,
    UnreadCountResponse,
)
from backend.app.services.EmailService import EmailDeliveryError, EmailDisabledError, EmailService
from backend.app.services.NotificationInboxService import NotificationInboxService
from backend.app.services.NotificationService import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notifications"])
SettingsDependency = Annotated[Settings, Depends(get_settings)]


def get_inbox_service(
    session: Annotated[Session, Depends(get_session)],
) -> NotificationInboxService:
    return NotificationInboxService(session)


InboxDependency = Annotated[NotificationInboxService, Depends(get_inbox_service)]


@router.get(
    "",
    response_model=NotificationPage,
    responses={401: {"description": "Authentication required."}},
)
def list_notifications(
    request: Request,
    service: InboxDependency,
    unread_only: bool = False,
    before_id: Annotated[int | None, Query(gt=0)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> NotificationPage:
    """List only your in-app history, newest ID first. Reads do not mark items read.

    Pass next_before_id as before_id for the next page. Existing history remains
    available after opting out. Email-only records are never exposed here.
    """
    return service.list(
        request.state.current_user.user_id,
        unread_only=unread_only,
        before_id=before_id,
        limit=limit,
    )


@router.get(
    "/unread-count",
    response_model=UnreadCountResponse,
    responses={401: {"description": "Authentication required."}},
)
def unread_count(request: Request, service: InboxDependency) -> UnreadCountResponse:
    """Count all your unread in-app notifications, independently of pagination."""
    return UnreadCountResponse(
        unread_count=service.unread_count(request.state.current_user.user_id)
    )


@router.get(
    "/preferences",
    response_model=NotificationPreferences,
    responses={401: {"description": "Authentication required."}},
)
def get_preferences(request: Request, service: InboxDependency) -> NotificationPreferences:
    """Return your saved preferences. Defaults: in-app on, email off."""
    return service.preferences(request.state.current_user.user_id)


@router.put(
    "/preferences",
    response_model=NotificationPreferences,
    responses={
        401: {"description": "Authentication required."},
        403: {"description": "CSRF validation failed."},
    },
)
def update_preferences(
    body: NotificationPreferences, request: Request, service: InboxDependency
) -> NotificationPreferences:
    """Replace both preferences. Disabling email also cancels pending deliveries.

    Changes apply to future events; enabling a channel never backfills past events.
    In-app history is retained. An email already submitted cannot be recalled.
    SMTP must also be enabled by the server operator for email delivery.
    """
    return service.update_preferences(request.state.current_user.user_id, body)


@router.post(
    "/read-all",
    response_model=MarkAllReadResponse,
    responses={
        401: {"description": "Authentication required."},
        403: {"description": "CSRF validation failed."},
    },
)
def mark_all_read(
    body: MarkAllReadRequest, request: Request, service: InboxDependency
) -> MarkAllReadResponse:
    """Mark your unread items read, optionally only through the newest loaded ID.

    Send {} to mark all currently visible items. Repeating the request is safe.
    """
    return MarkAllReadResponse(
        updated_count=service.mark_all_read(request.state.current_user.user_id, body.through_id)
    )


@router.patch(
    "/{notification_id}/read",
    response_model=NotificationResponse,
    responses={
        401: {"description": "Authentication required."},
        403: {"description": "CSRF validation failed."},
        404: {"description": "Notification absent or not in your in-app inbox."},
    },
)
def mark_read(
    notification_id: Annotated[int, Path(gt=0)], request: Request, service: InboxDependency
) -> NotificationResponse:
    """Mark one item read. Repeating the request preserves its original read time."""
    return service.mark_read(request.state.current_user.user_id, notification_id)


def get_notification_service(settings: SettingsDependency) -> NotificationService:
    return NotificationService(EmailService(settings))


@router.post(
    "/test-email",
    response_model=TestEmailResponse,
    responses={
        401: {"description": "Authentication required."},
        403: {"description": "CSRF validation failed."},
        404: {"description": "Test email event is disabled."},
        502: {"description": "Email submission failed; delivery may be uncertain after a timeout."},
        503: {"description": "Email sending is disabled."},
    },
)
def send_test_email(
    request: Request,
    settings: SettingsDependency,
    service: Annotated[NotificationService, Depends(get_notification_service)],
) -> TestEmailResponse:
    """Email the signed-in user's stored address. No request body is needed.

    Enable EMAIL_TEST_ENABLED temporarily to use this diagnostic event.
    Success means provider acceptance, not confirmed inbox delivery.
    """
    if not settings.email_test_enabled:
        raise HTTPException(status_code=404, detail="Test email event is disabled.")
    try:
        message_id = service.send_test(request.state.current_user)
    except EmailDisabledError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except EmailDeliveryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return TestEmailResponse(message_id=message_id)
