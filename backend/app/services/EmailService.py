"""Email composition and transport shared by notification events."""

import logging
import smtplib
import ssl
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import format_datetime, formataddr, make_msgid

from pydantic import EmailStr, TypeAdapter

from backend.app.core.config import Settings

logger = logging.getLogger(__name__)


class EmailDisabledError(Exception):
    pass


class EmailDeliveryError(Exception):
    pass


class EmailService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def send(self, *, recipient: str, subject: str, body: str) -> str:
        """Return our Message-ID after provider acceptance, not proof of delivery."""
        settings = self.settings
        if not settings.email_enabled:
            raise EmailDisabledError("Email sending is disabled.")

        try:
            recipient = str(TypeAdapter(EmailStr).validate_python(recipient))
            sender = str(settings.email_from_address)
            message = EmailMessage()
            message["From"] = formataddr((settings.email_from_name, sender))
            message["To"] = recipient
            message["Subject"] = subject
            message["Date"] = format_datetime(datetime.now(UTC))
            message_id = make_msgid(domain=sender.rsplit("@", 1)[1])
            message["Message-ID"] = message_id
            message.set_content(body)

            connection_options = {
                "host": settings.smtp_host,
                "port": settings.smtp_port,
                "timeout": settings.email_timeout_seconds,
            }
            if settings.smtp_encryption == "ssl":
                connection = smtplib.SMTP_SSL(
                    **connection_options, context=ssl.create_default_context()
                )
            else:
                connection = smtplib.SMTP(**connection_options)
            with connection as smtp:
                if settings.smtp_encryption == "starttls":
                    smtp.starttls(context=ssl.create_default_context())
                if settings.smtp_username:
                    smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
                refused = smtp.send_message(message, from_addr=sender, to_addrs=[recipient])
                if refused:
                    raise smtplib.SMTPRecipientsRefused(refused)
            return message_id
        except (smtplib.SMTPException, OSError, ValueError) as exc:
            # Provider errors can contain addresses, message contents, or credentials.
            logger.warning("Email submission failed (%s).", type(exc).__name__)
            raise EmailDeliveryError("Email could not be submitted to the mail provider.") from exc
