from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class Attraction(Base):
    """Curated point of interest maintained by administrators."""

    __tablename__ = "attractions"

    attraction_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float] = mapped_column(Double)
    longitude: Mapped[float] = mapped_column(Double)
    category: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    opening_hours: Mapped[str | None] = mapped_column(Text)
    suggested_duration_minutes: Mapped[int | None] = mapped_column(Integer)
    typical_cost: Mapped[Decimal | None] = mapped_column(Numeric)
    currency: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="ck_attractions_name"),
        CheckConstraint("length(trim(summary)) > 0", name="ck_attractions_summary"),
        CheckConstraint(
            "latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180",
            name="ck_attractions_coordinates",
        ),
        CheckConstraint(
            "suggested_duration_minutes IS NULL OR suggested_duration_minutes > 0",
            name="ck_attractions_duration",
        ),
        CheckConstraint("typical_cost IS NULL OR typical_cost >= 0", name="ck_attractions_cost"),
        CheckConstraint(
            "currency IS NULL OR currency ~ '^[A-Z]{3}$'", name="ck_attractions_currency"
        ),
        Index(
            "uq_attractions_name_city",
            text("lower(TRIM(BOTH FROM name))"),
            text("lower(TRIM(BOTH FROM COALESCE(city, ''::text)))"),
            unique=True,
        ),
        Index("idx_attractions_coordinates", "latitude", "longitude"),
    )
