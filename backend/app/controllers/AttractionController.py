from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from fastapi.security import APIKeyCookie
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.database import get_session
from backend.app.core.filter import require_admin
from backend.app.models.user import User
from backend.app.schemas.attraction import (
    AdminAttractionResponse,
    AttractionResponse,
    AttractionSummaryResponse,
    CreateAttractionRequest,
    ImportAttractionsRequest,
    ImportAttractionsResponse,
    UpdateAttractionRequest,
)
from backend.app.services.AttractionService import MAX_MAP_RESULTS, AttractionService

cookie_auth = Depends(
    APIKeyCookie(name=get_settings().jwt_cookie_name, scheme_name="CookieAuth", auto_error=False)
)
router = APIRouter(
    responses={401: {"description": "Authentication required."}},
    # Authentication is enforced globally; this dependency also documents the cookie.
    dependencies=[cookie_auth],
)
admin_router = APIRouter(
    prefix="/admin/attractions",
    tags=["Admin: Attractions"],
    responses={
        401: {"description": "Authentication required."},
        403: {"description": "Administrator access required."},
    },
    dependencies=[cookie_auth],
)

Id = Annotated[int, Path(gt=0, le=9223372036854775807)]
FilterText = Annotated[str | None, Query(min_length=1, max_length=200)]


def get_attraction_service(session: Annotated[Session, Depends(get_session)]) -> AttractionService:
    return AttractionService(session)


Service = Annotated[AttractionService, Depends(get_attraction_service)]
Admin = Annotated[User, Depends(require_admin)]


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


@admin_router.get("", response_model=list[AdminAttractionResponse])
def admin_list_attractions(
    _: Admin,
    service: Service,
    category: FilterText = None,
    city: FilterText = None,
    q: FilterText = None,
    is_active: bool | None = None,
):
    """Administrators only: list all attractions, including deactivated ones."""
    return service.admin_list(category=category, city=city, q=q, is_active=is_active)


@admin_router.post(
    "",
    response_model=AdminAttractionResponse,
    status_code=201,
    responses={409: {"description": "Same name already exists in this city."}},
)
def admin_create_attraction(body: CreateAttractionRequest, admin: Admin, service: Service):
    """Administrators only: add an attraction. Names are unique per city, ignoring case."""
    return service.create(body, admin.user_id)


@admin_router.post(
    "/import",
    response_model=ImportAttractionsResponse,
    responses={409: {"description": "A concurrent change created a duplicate attraction."}},
)
def admin_import_attractions(body: ImportAttractionsRequest, admin: Admin, service: Service):
    """Administrators only: create or update up to 500 attractions in one transaction.

    Rows are matched by case-insensitive name and city. Matched rows are replaced
    with the supplied values; omitted optional fields become null.
    """
    return service.import_many(body, admin.user_id)


@admin_router.get(
    "/{attraction_id}",
    response_model=AdminAttractionResponse,
    responses={404: {"description": "Attraction not found."}},
)
def admin_get_attraction(attraction_id: Id, _: Admin, service: Service):
    """Administrators only: read an attraction, including a deactivated one."""
    return service.admin_get(attraction_id)


@admin_router.patch(
    "/{attraction_id}",
    response_model=AdminAttractionResponse,
    responses={
        404: {"description": "Attraction not found."},
        409: {"description": "Same name already exists in this city."},
    },
)
def admin_update_attraction(
    attraction_id: Id, body: UpdateAttractionRequest, _: Admin, service: Service
):
    """Administrators only: partially update an attraction.

    Omitted fields stay unchanged; optional details can be cleared with null.
    Set `is_active` to true to restore a deactivated attraction. Existing
    proposals keep the coordinates copied when they were created.
    """
    return service.update(attraction_id, body)


@admin_router.delete(
    "/{attraction_id}",
    status_code=204,
    responses={404: {"description": "Attraction not found."}},
)
def admin_deactivate_attraction(attraction_id: Id, _: Admin, service: Service) -> Response:
    """Administrators only: hide an attraction from travelers (soft delete).

    Linked proposals are unaffected. Repeating the request also returns 204.
    """
    service.deactivate(attraction_id)
    return Response(status_code=204)
