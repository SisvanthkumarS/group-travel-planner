from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from backend.app.models import Notification, NotificationEmail, User


class NotificationRepository:
    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def visible(user_id):
        return (Notification.user_id == user_id, Notification.in_app_visible.is_(True))

    def page(self, user_id, *, unread_only, before_id, limit):
        query = select(Notification).where(*self.visible(user_id))
        if unread_only:
            query = query.where(Notification.read_at.is_(None))
        if before_id is not None:
            query = query.where(Notification.notification_id < before_id)
        return list(
            self.session.scalars(
                query.order_by(Notification.notification_id.desc()).limit(limit + 1)
            )
        )

    def unread_count(self, user_id):
        return self.session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(*self.visible(user_id), Notification.read_at.is_(None))
        )

    def mark_read(self, user_id, notification_id):
        return self.session.scalar(
            update(Notification)
            .where(*self.visible(user_id), Notification.notification_id == notification_id)
            .values(read_at=func.coalesce(Notification.read_at, datetime.now(UTC)))
            .returning(Notification)
        )

    def mark_all_read(self, user_id, through_id):
        query = update(Notification).where(*self.visible(user_id), Notification.read_at.is_(None))
        if through_id is not None:
            query = query.where(Notification.notification_id <= through_id)
        return self.session.execute(query.values(read_at=datetime.now(UTC))).rowcount

    def user(self, user_id, *, lock=False):
        query = (
            select(User).where(User.user_id == user_id).execution_options(populate_existing=True)
        )
        if lock:
            query = query.with_for_update()
        return self.session.scalar(query)

    def cancel_pending_emails(self, user_id):
        self.session.execute(
            update(NotificationEmail)
            .where(
                NotificationEmail.notification_id.in_(
                    select(Notification.notification_id).where(Notification.user_id == user_id)
                ),
                NotificationEmail.status.in_(["PENDING", "SENDING"]),
            )
            .values(status="CANCELED", lease_token=None, lease_expires_at=None)
        )
