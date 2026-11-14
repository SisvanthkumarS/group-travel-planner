from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.app.repositories.NotificationRepository import NotificationRepository
from backend.app.schemas.notification import (
    NotificationPage,
    NotificationPreferences,
    NotificationResponse,
)


class NotificationInboxService:
    def __init__(self, session: Session):
        self.session = session
        self.repository = NotificationRepository(session)

    @staticmethod
    def response(notification):
        path = None
        if notification.trip_id is not None:
            if notification.event_type == "INVITATION_RECEIVED":
                path = "/trips"
            else:
                path = f"/trips/{notification.trip_id}"
                if notification.event_type in {"ACTIVITY_APPROVED", "ACTIVITY_CANCELLED"}:
                    path += "/itinerary"
        return NotificationResponse(
            **{
                name: getattr(notification, name)
                for name in NotificationResponse.model_fields
                if name != "action_url"
            },
            action_url=path,
        )

    def list(self, user_id, *, unread_only=False, before_id=None, limit=20):
        rows = self.repository.page(
            user_id, unread_only=unread_only, before_id=before_id, limit=limit
        )
        return NotificationPage(
            items=[self.response(row) for row in rows[:limit]],
            next_before_id=rows[limit - 1].notification_id if len(rows) > limit else None,
        )

    def mark_read(self, user_id, notification_id):
        try:
            row = self.repository.mark_read(user_id, notification_id)
            if row is None:
                raise HTTPException(404, "Notification not found.")
            response = self.response(row)
            self.session.commit()
            return response
        except Exception:
            self.session.rollback()
            raise

    def unread_count(self, user_id):
        return self.repository.unread_count(user_id)

    def mark_all_read(self, user_id, through_id):
        try:
            count = self.repository.mark_all_read(user_id, through_id)
            self.session.commit()
            return count
        except Exception:
            self.session.rollback()
            raise

    def preferences(self, user_id):
        user = self.repository.user(user_id)
        if user is None:
            raise HTTPException(401, "Authentication required.")
        return NotificationPreferences(
            in_app_enabled=user.in_app_notifications_enabled,
            email_enabled=user.email_notifications_enabled,
        )

    def update_preferences(self, user_id, preferences):
        try:
            user = self.repository.user(user_id, lock=True)
            if user is None:
                raise HTTPException(401, "Authentication required.")
            user.in_app_notifications_enabled = preferences.in_app_enabled
            user.email_notifications_enabled = preferences.email_enabled
            if not preferences.email_enabled:
                self.repository.cancel_pending_emails(user_id)
            self.session.commit()
            return preferences
        except Exception:
            self.session.rollback()
            raise
