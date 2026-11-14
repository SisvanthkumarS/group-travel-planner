"""Publish notifications inside the caller's business transaction; never sends SMTP."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.app.models import Notification, NotificationEmail, TripMember, User


class NotificationPublisher:
    def __init__(self, session: Session):
        self.session = session

    def member_ids(self, trip_id: int) -> list[int]:
        return list(
            self.session.scalars(select(TripMember.user_id).where(TripMember.trip_id == trip_id))
        )

    def publish(
        self,
        *,
        event_key: str,
        event_type: str,
        recipients,
        actor_id: int | None,
        trip,
        title: str,
        message: str,
        proposal_id: int | None = None,
        invitation_id: int | None = None,
    ) -> None:
        # Serialize preference changes with event creation, in a stable lock order.
        users = self.session.scalars(
            select(User)
            .where(User.user_id.in_(set(recipients) - {actor_id}))
            .order_by(User.user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).all()
        for user in users:
            if not user.in_app_notifications_enabled and not user.email_notifications_enabled:
                continue
            notification_id = self.session.scalar(
                insert(Notification)
                .values(
                    user_id=user.user_id,
                    event_key=event_key,
                    event_type=event_type,
                    title=title,
                    message=message,
                    trip_name=trip.name,
                    trip_id=trip.trip_id,
                    proposal_id=proposal_id,
                    invitation_id=invitation_id,
                    in_app_visible=user.in_app_notifications_enabled,
                )
                .on_conflict_do_nothing(constraint="uq_notification_recipient_event")
                .returning(Notification.notification_id)
            )
            if notification_id is not None and user.email_notifications_enabled:
                self.session.add(NotificationEmail(notification_id=notification_id))
        self.session.flush()
