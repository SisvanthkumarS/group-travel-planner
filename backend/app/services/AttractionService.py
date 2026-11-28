from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models.attraction import Attraction
from backend.app.repositories.AttractionRepository import AttractionRepository, natural_key
from backend.app.schemas.attraction import (
    AttractionResponse,
    AttractionSeedFile,
    AttractionSummaryResponse,
)

MAX_MAP_RESULTS = 200


@dataclass(frozen=True)
class SeedResult:
    created: int
    updated: int


class AttractionService:
    def __init__(self, session: Session):
        self.session = session
        self.repository = AttractionRepository(session)

    def search_active(
        self,
        *,
        bounds: tuple[float, float, float, float] | None,
        category: str | None,
        city: str | None,
        q: str | None,
        limit: int,
    ) -> list[AttractionSummaryResponse]:
        rows = self.repository.search(
            bounds=bounds,
            category=category,
            city=city,
            q=q,
            limit=min(limit, MAX_MAP_RESULTS),
        )
        return [AttractionSummaryResponse.model_validate(row) for row in rows]

    def get_active(self, attraction_id: int) -> AttractionResponse:
        attraction = self.active_for_proposal(attraction_id)
        if attraction is None:
            raise HTTPException(404, "Attraction not found.")
        return AttractionResponse.model_validate(attraction)

    def active_for_proposal(self, attraction_id: int) -> Attraction | None:
        """Return an active attraction, or None. The caller owns the transaction."""
        attraction = self.repository.get(attraction_id)
        if attraction is None or not attraction.is_active:
            return None
        return attraction

    def seed(self, file: AttractionSeedFile) -> SeedResult:
        """Create or update attractions matched by case-insensitive name and city.

        Used by scripts/seed_attractions.py; there is no HTTP route. Raises
        ValueError for duplicates in the file or a conflicting concurrent write.
        """
        keys = [natural_key(item.name, item.city) for item in file.attractions]
        seen: dict[tuple[str, str], int] = {}
        for index, key in enumerate(keys):
            if key in seen:
                raise ValueError(
                    f"Entry {index} duplicates entry {seen[key]} (same name and city)."
                )
            seen[key] = index
        now = datetime.now(UTC)
        created = updated = 0
        try:
            existing = {
                natural_key(row.name, row.city): row
                for row in self.repository.by_keys(keys, lock=True)
            }
            for item, key in zip(file.attractions, keys, strict=True):
                values = item.model_dump()
                attraction = existing.get(key)
                if attraction is None:
                    self.repository.add(Attraction(**values))
                    created += 1
                else:
                    for field, value in values.items():
                        setattr(attraction, field, value)
                    attraction.updated_at = now
                    updated += 1
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ValueError("An attraction with the same name and city already exists.") from exc
        except Exception:
            self.session.rollback()
            raise
        return SeedResult(created=created, updated=updated)
