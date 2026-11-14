from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.app.core.config import Settings, get_settings
from backend.app.schemas.notification import TestEmailResponse
from backend.app.services.EmailService import EmailDeliveryError, EmailDisabledError, EmailService
from backend.app.services.NotificationService import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notifications"])
SettingsDependency = Annotated[Settings, Depends(get_settings)]


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
