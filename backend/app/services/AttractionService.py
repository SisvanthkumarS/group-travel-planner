from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models.attraction import Attraction
from backend.app.repositories.AttractionRepository import AttractionRepository, natural_key
from backend.app.schemas.attraction import (
    AdminAttractionResponse,
    AttractionResponse,
    AttractionSummaryResponse,
    CreateAttractionRequest,
    ImportAttractionsRequest,
    ImportAttractionsResponse,
    UpdateAttractionRequest,
)

DUPLICATE_DETAIL = "An attraction with this name already exists in this city."
MAX_MAP_RESULTS = 200


class AttractionService:
    def __init__(self, session: Session):
        self.session = session
        self.repository = AttractionRepository(session)

    def _commit(self) -> None:
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise HTTPException(409, DUPLICATE_DETAIL) from exc

    def _require(self, attraction_id: int, *, lock: bool = False) -> Attraction:
        attraction = self.repository.get(attraction_id, lock=lock)
        if attraction is None:
            raise HTTPException(404, "Attraction not found.")
        return attraction

    # Traveler-facing reads -------------------------------------------------

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
            active_only=True,
            bounds=bounds,
            category=category,
            city=city,
            q=q,
            limit=min(limit, MAX_MAP_RESULTS),
        )
        return [AttractionSummaryResponse.model_validate(row) for row in rows]

    def get_active(self, attraction_id: int) -> AttractionResponse:
        attraction = self._require(attraction_id)
        if not attraction.is_active:
            raise HTTPException(404, "Attraction not found.")
        return AttractionResponse.model_validate(attraction)

    def active_for_proposal(self, attraction_id: int) -> Attraction | None:
        """Return an active attraction, or None. The caller owns the transaction."""
        attraction = self.repository.get(attraction_id)
        if attraction is None or not attraction.is_active:
            return None
        return attraction

    # Administration -------------------------------------------------------

    def admin_list(
        self, *, category: str | None, city: str | None, q: str | None, is_active: bool | None
    ) -> list[AdminAttractionResponse]:
        rows = self.repository.search(active_only=False, category=category, city=city, q=q)
        if is_active is not None:
            rows = [row for row in rows if row.is_active is is_active]
        return [AdminAttractionResponse.model_validate(row) for row in rows]

    def admin_get(self, attraction_id: int) -> AdminAttractionResponse:
        return AdminAttractionResponse.model_validate(self._require(attraction_id))

    def create(self, body: CreateAttractionRequest, admin_id: int) -> AdminAttractionResponse:
        try:
            attraction = self.repository.add(
                Attraction(**body.model_dump(), created_by_user_id=admin_id)
            )
            response = AdminAttractionResponse.model_validate(attraction)
        except IntegrityError as exc:
            self.session.rollback()
            raise HTTPException(409, DUPLICATE_DETAIL) from exc
        except Exception:
            self.session.rollback()
            raise
        self._commit()
        return response

    def update(self, attraction_id: int, body: UpdateAttractionRequest) -> AdminAttractionResponse:
        try:
            attraction = self._require(attraction_id, lock=True)
            changes = body.model_dump(include=body.model_fields_set)
            for field, value in changes.items():
                setattr(attraction, field, value)
            attraction.updated_at = datetime.now(UTC)
            self.session.flush()
            response = AdminAttractionResponse.model_validate(attraction)
        except IntegrityError as exc:
            self.session.rollback()
            raise HTTPException(409, DUPLICATE_DETAIL) from exc
        except Exception:
            self.session.rollback()
            raise
        self._commit()
        return response

    def deactivate(self, attraction_id: int) -> None:
        try:
            attraction = self._require(attraction_id, lock=True)
            if attraction.is_active:
                attraction.is_active = False
                attraction.updated_at = datetime.now(UTC)
        except Exception:
            self.session.rollback()
            raise
        self._commit()

    def import_many(
        self, body: ImportAttractionsRequest, admin_id: int | None
    ) -> ImportAttractionsResponse:
        """Create or update attractions matched by case-insensitive name and city."""
        keys = [natural_key(item.name, item.city) for item in body.attractions]
        seen: dict[tuple[str, str], int] = {}
        for index, key in enumerate(keys):
            if key in seen:
                raise HTTPException(
                    422,
                    detail=[
                        {
                            "loc": ["body", "attractions", index, "name"],
                            "msg": f"Duplicates attraction {seen[key]} in this import.",
                            "type": "value_error",
                        }
                    ],
                )
            seen[key] = index
        now = datetime.now(UTC)
        created = updated = 0
        results: list[Attraction] = []
        try:
            existing = {
                natural_key(row.name, row.city): row
                for row in self.repository.by_keys(keys, lock=True)
            }
            for item, key in zip(body.attractions, keys, strict=True):
                values = item.model_dump()
                attraction = existing.get(key)
                if attraction is None:
                    attraction = self.repository.add(
                        Attraction(**values, created_by_user_id=admin_id)
                    )
                    created += 1
                else:
                    for field, value in values.items():
                        setattr(attraction, field, value)
                    attraction.updated_at = now
                    updated += 1
                results.append(attraction)
            self.session.flush()
            response = ImportAttractionsResponse(
                created=created,
                updated=updated,
                attractions=[AdminAttractionResponse.model_validate(row) for row in results],
            )
        except IntegrityError as exc:
            self.session.rollback()
            raise HTTPException(409, DUPLICATE_DETAIL) from exc
        except Exception:
            self.session.rollback()
            raise
        self._commit()
        return response
