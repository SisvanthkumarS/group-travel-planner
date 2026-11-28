from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.security import APIKeyCookie
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.database import get_session
from backend.app.schemas.attraction import AttractionResponse, AttractionSummaryResponse
from backend.app.services.AttractionService import MAX_MAP_RESULTS, AttractionService

router = APIRouter(
    responses={401: {"description": "Authentication required."}},
    # Authentication is enforced globally; this dependency also documents the cookie.
    dependencies=[
        Depends(
            APIKeyCookie(
                name=get_settings().jwt_cookie_name,
                scheme_name="CookieAuth",
                auto_error=False,
            )
        )
    ],
)
Id = Annotated[int, Path(gt=0, le=9223372036854775807)]
FilterText = Annotated[str | None, Query(min_length=1, max_length=200)]


def get_attraction_service(session: Annotated[Session, Depends(get_session)]) -> AttractionService:
    return AttractionService(session)


Service = Annotated[AttractionService, Depends(get_attraction_service)]


@router.get(
    "/attractions",
    tags=["Attractions"],
    response_model=list[AttractionSummaryResponse],
    responses={422: {"description": "Incomplete or invalid map bounds."}},
)
def list_attractions(
    service: Service,
    min_lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    max_lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    min_lng: Annotated[float | None, Query(ge=-180, le=180)] = None,
    max_lng: Annotated[float | None, Query(ge=-180, le=180)] = None,
    category: FilterText = None,
    city: FilterText = None,
    q: FilterText = None,
    limit: Annotated[int, Query(ge=1, le=MAX_MAP_RESULTS)] = 100,
):
    """Map markers for active attractions, ordered by name.

    Send all four bounds for the visible map area, or none of them. When
    `min_lng` is greater than `max_lng` the area crosses the antimeridian.
    `category` and `city` match case-insensitively; `q` searches name, city
    and address. Results contain the short `summary` for the marker pop-up.
    """
    values = (min_lat, max_lat, min_lng, max_lng)
    if all(value is None for value in values):
        bounds = None
    elif any(value is None for value in values):
        raise HTTPException(422, "Provide min_lat, max_lat, min_lng and max_lng together.")
    elif min_lat > max_lat:
        raise HTTPException(422, "min_lat must not exceed max_lat.")
    else:
        bounds = values
    return service.search_active(bounds=bounds, category=category, city=city, q=q, limit=limit)


@router.get(
    "/attractions/{attraction_id}",
    tags=["Attractions"],
    response_model=AttractionResponse,
    responses={404: {"description": "Attraction not found or no longer available."}},
)
def get_attraction(attraction_id: Id, service: Service):
    """Full introduction and visiting details for an active attraction.

    Use `suggested_duration_minutes` and `typical_cost` to pre-fill a proposal.
    """
    return service.get_active(attraction_id)
