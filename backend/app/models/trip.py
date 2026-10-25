from datetime import date

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Identity, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class Trip(Base):
    __tablename__ = "trips"

    trip_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    destination: Mapped[str] = mapped_column(Text)
    start_date: Mapped[date]
    end_date: Mapped[date]
    organizer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE")
    )

    __table_args__ = (
        CheckConstraint("LENGTH(TRIM(name)) > 0", name="ck_trips_name_not_blank"),
        CheckConstraint("LENGTH(TRIM(destination)) > 0", name="ck_trips_destination_not_blank"),
        CheckConstraint("start_date <= end_date", name="ck_trips_dates"),
    )
