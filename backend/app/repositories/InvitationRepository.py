from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.invitation import Invitation


class InvitationRepository:
    """Invitation queries and persistence; the Service owns transactions."""

    def __init__(self, session: Session):
        self.session = session

    def add(self, invitation: Invitation) -> Invitation:
        self.session.add(invitation)
        self.session.flush()
        return invitation

    def list_for_user(self, user_id: int) -> list[Invitation]:
        statement = (
            select(Invitation)
            .where(Invitation.invited_user_id == user_id)
            .order_by(Invitation.created_at.desc(), Invitation.invitation_id.desc())
        )
        return list(self.session.scalars(statement).all())

    def find_by_id(self, invitation_id: int) -> Invitation | None:
        return self.session.get(Invitation, invitation_id)

    def find_pending(self, trip_id: int, invited_user_id: int) -> Invitation | None:
        statement = select(Invitation).where(
            Invitation.trip_id == trip_id,
            Invitation.invited_user_id == invited_user_id,
            Invitation.status == "PENDING",
        )
        return self.session.scalar(statement)

    def find_by_id_for_update(self, invitation_id: int) -> Invitation | None:
        statement = (
            select(Invitation)
            .where(Invitation.invitation_id == invitation_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return self.session.scalar(statement)

    def save_response(self, invitation: Invitation) -> Invitation:
        self.session.flush()
        return invitation
