from collections.abc import Sequence

from sqlalchemy import func, or_, select, tuple_
from sqlalchemy.orm import Session

from backend.app.models.attraction import Attraction


def natural_key(name: str, city: str | None) -> tuple[str, str]:
    """Mirror uq_attractions_name_city: case-insensitive name within a city."""
    return name.strip().lower(), (city or "").strip().lower()


_KEY = tuple_(
    func.lower(func.trim(Attraction.name)),
    func.lower(func.trim(func.coalesce(Attraction.city, ""))),
)


class AttractionRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, attraction_id: int, *, lock: bool = False) -> Attraction | None:
        query = select(Attraction).where(Attraction.attraction_id == attraction_id)
        if lock:
            query = query.with_for_update()
        return self.session.scalar(query)

    def by_keys(self, keys: Sequence[tuple[str, str]], *, lock: bool = False) -> list[Attraction]:
        if not keys:
            return []
        query = select(Attraction).where(_KEY.in_(list(keys)))
        if lock:
            query = query.with_for_update()
        return list(self.session.scalars(query))

    def search(
        self,
        *,
        active_only: bool,
        bounds: tuple[float, float, float, float] | None = None,
        category: str | None = None,
        city: str | None = None,
        q: str | None = None,
        limit: int | None = None,
    ) -> list[Attraction]:
        query = select(Attraction)
        if active_only:
            query = query.where(Attraction.is_active.is_(True))
        if bounds is not None:
            min_lat, max_lat, min_lng, max_lng = bounds
            query = query.where(Attraction.latitude.between(min_lat, max_lat))
            if min_lng <= max_lng:
                query = query.where(Attraction.longitude.between(min_lng, max_lng))
            else:
                # The viewport crosses the antimeridian.
                query = query.where(
                    or_(Attraction.longitude >= min_lng, Attraction.longitude <= max_lng)
                )
        if category:
            query = query.where(func.lower(Attraction.category) == category.strip().lower())
        if city:
            query = query.where(func.lower(Attraction.city) == city.strip().lower())
        if q:
            escaped = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            query = query.where(
                or_(
                    Attraction.name.ilike(pattern, escape="\\"),
                    Attraction.city.ilike(pattern, escape="\\"),
                    Attraction.address.ilike(pattern, escape="\\"),
                )
            )
        query = query.order_by(Attraction.name, Attraction.attraction_id)
        if limit is not None:
            query = query.limit(limit)
        return list(self.session.scalars(query))

    def add(self, attraction: Attraction) -> Attraction:
        self.session.add(attraction)
        self.session.flush()
        self.session.refresh(attraction)
        return attraction
