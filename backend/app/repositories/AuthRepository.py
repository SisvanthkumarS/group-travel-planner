from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models.user import User


class AuthRepository:
    def __init__(self, session: Session):
        self.session = session

    def find_by_email(self, email: str) -> User | None:
        statement = select(User).where(func.lower(func.trim(User.email)) == email.strip().lower())
        return self.session.scalar(statement)

    def add(self, user: User) -> User:
        self.session.add(user)
        self.session.flush()
        return user

    def find_by_user_name(self, user_name: str) -> User | None:
        statement = select(User).where(User.user_name == user_name.strip())
        return self.session.scalar(statement)
