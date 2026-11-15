"""Drain the durable SMTP outbox with short claims and recoverable leases."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, or_, select, update

from backend.app.core.database import SessionLocal
from backend.app.models import Notification, NotificationEmail, User
from backend.app.services.EmailService import EmailDeliveryError, EmailService

logger = logging.getLogger(__name__)


def due(now):
    return or_(
        and_(NotificationEmail.status == "PENDING", NotificationEmail.next_attempt_at <= now),
        and_(NotificationEmail.status == "SENDING", NotificationEmail.lease_expires_at <= now),
    )


def claim_email(settings, session_factory, notification_id, user_id):
    with session_factory() as session, session.begin():
        # Short locks in the same order as preference updates and event publication.
        user = session.scalar(
            select(User).where(User.user_id == user_id).with_for_update(skip_locked=True)
        )
        if user is None:
            return None
        delivery = session.scalar(
            select(NotificationEmail)
            .where(NotificationEmail.notification_id == notification_id, due(datetime.now(UTC)))
            .with_for_update(skip_locked=True)
        )
        if delivery is None:
            return None
        delivery.lease_token = delivery.lease_expires_at = None
        if not user.email_notifications_enabled:
            delivery.status = "CANCELED"
            return None
        if delivery.attempts >= settings.notification_email_max_attempts:
            delivery.status = "FAILED"
            delivery.last_error = "Delivery attempt limit reached."
            return None
        notification = session.get(Notification, notification_id)
        delivery.status = "SENDING"
        delivery.attempts += 1
        delivery.lease_token = str(uuid4())
        delivery.lease_expires_at = datetime.now(UTC) + timedelta(
            seconds=settings.notification_email_lease_seconds
        )
        return {
            "token": delivery.lease_token,
            "attempt": delivery.attempts,
            "recipient": user.email,
            "subject": f"Group Travel Planner: {notification.title}",
            "body": (
                f"{notification.message}\n\nTrip: {notification.trip_name}\n\n"
                "Manage notification preferences in Group Travel Planner.\n"
            ),
        }


def process_pending_emails(settings, session_factory=SessionLocal, sender=None, stop=None):
    if not settings.email_enabled or not settings.notification_email_worker_enabled:
        return 0
    sender = sender or EmailService(settings)
    with session_factory() as session:
        candidates = list(
            session.execute(
                select(NotificationEmail.notification_id, Notification.user_id)
                .join(
                    Notification, Notification.notification_id == NotificationEmail.notification_id
                )
                .where(due(datetime.now(UTC)))
                .order_by(NotificationEmail.next_attempt_at, NotificationEmail.notification_id)
                .limit(settings.notification_email_batch_size)
            )
        )
    processed = 0
    for notification_id, user_id in candidates:
        if stop is not None and stop.is_set():
            break
        try:
            claim = claim_email(settings, session_factory, notification_id, user_id)
            if claim is None:
                continue
            # Recheck after claiming; disabling a channel cancels leased jobs too.
            with session_factory() as session:
                active = session.scalar(
                    select(NotificationEmail.notification_id).where(
                        NotificationEmail.notification_id == notification_id,
                        NotificationEmail.status == "SENDING",
                        NotificationEmail.lease_token == claim["token"],
                    )
                )
            if active is None:
                continue
            # No database transaction or lock is held during SMTP network I/O.
            try:
                sender.send(
                    recipient=claim["recipient"], subject=claim["subject"], body=claim["body"]
                )
            except EmailDeliveryError:
                values = {"last_error": "SMTP submission failed."}
                if claim["attempt"] >= settings.notification_email_max_attempts:
                    values["status"] = "FAILED"
                else:
                    delay = min(
                        3600,
                        settings.notification_email_retry_seconds * 2 ** (claim["attempt"] - 1),
                    )
                    values.update(
                        status="PENDING",
                        next_attempt_at=datetime.now(UTC) + timedelta(seconds=delay),
                    )
            else:
                values = {"status": "SENT", "sent_at": datetime.now(UTC), "last_error": None}
            with session_factory() as session, session.begin():
                session.execute(
                    update(NotificationEmail)
                    .where(
                        NotificationEmail.notification_id == notification_id,
                        NotificationEmail.status == "SENDING",
                        NotificationEmail.lease_token == claim["token"],
                    )
                    .values(**values, lease_token=None, lease_expires_at=None)
                )
            processed += 1
        except Exception as exc:
            # A crashed/failed claim is recovered after its lease expires. Avoid PII in logs.
            logger.warning("Notification email transaction failed (%s).", type(exc).__name__)
    return processed


async def run_notification_worker(stop: asyncio.Event, settings):
    while not stop.is_set():
        try:
            await asyncio.wait_for(
                stop.wait(), timeout=settings.notification_email_interval_seconds
            )
            return
        except TimeoutError:
            pass
        try:
            await asyncio.to_thread(process_pending_emails, settings, stop=stop)
        except Exception as exc:
            logger.warning("Notification email scan failed (%s).", type(exc).__name__)
