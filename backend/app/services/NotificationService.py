from backend.app.models.user import User
from backend.app.services.EmailService import EmailService


class NotificationService:
    def __init__(self, email: EmailService):
        self.email = email

    def send_test(self, user: User) -> str:
        """The first notification event: a user explicitly requests a test email."""
        return self.email.send(
            recipient=user.email,
            subject="Group Travel Planner: test notification",
            body=(
                f"Hi {user.user_name},\n\n"
                "This is your test email notification from Group Travel Planner.\n"
                "You requested it while signed in to your account.\n\n"
                "If you can read this, email sending is working.\n"
            ),
        )
