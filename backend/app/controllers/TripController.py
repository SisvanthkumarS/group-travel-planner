from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response, status
from sqlalchemy.orm import Session

from backend.app.core.database import get_session
from backend.app.schemas.trip import CreateTripRequest, TripDetailResponse, TripResponse
from backend.app.services.TripService import TripService

router = APIRouter(
    prefix="/trips",
    tags=["Trip Management"],
    responses={
        401: {"description": "Authentication required."},
        501: {"description": "Trip business logic is not implemented yet."},
    },
)


def get_trip_service(session: Annotated[Session, Depends(get_session)]) -> TripService:
    return TripService(session)


TripServiceDependency = Annotated[TripService, Depends(get_trip_service)]
TripId = Annotated[int, Path(gt=0, description="Trip ID")]


@router.post("", response_model=TripResponse, status_code=status.HTTP_201_CREATED)
def create_trip(
    body: CreateTripRequest,
    request: Request,
    service: TripServiceDependency,
) -> TripResponse:
    """Create a trip and its Organizer membership. Scaffold currently returns 501."""
    # The global JWT filter already loaded this user; never accept the actor's
    # identity from a request body or query parameter.
    return service.create_trip(body, request.state.current_user.user_id)


@router.get("", response_model=list[TripResponse])
def list_trips(request: Request, service: TripServiceDependency) -> list[TripResponse]:
    """List trips accessible to the current user. Scaffold currently returns 501."""
    return service.list_trips(request.state.current_user.user_id)


@router.get(
    "/{trip_id}",
    response_model=TripDetailResponse,
    responses={
        403: {"description": "Trip membership required."},
        404: {"description": "Trip not found."},
    },
)
def get_trip(
    trip_id: TripId, request: Request, service: TripServiceDependency
) -> TripDetailResponse:
    """Get trip details and members. Scaffold currently returns 501."""
    return service.get_trip(trip_id, request.state.current_user.user_id)


@router.delete(
    "/{trip_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        403: {"description": "Organizer required."},
        404: {"description": "Trip not found."},
    },
)
def delete_trip(trip_id: TripId, request: Request, service: TripServiceDependency) -> Response:
    """Delete a trip as its Organizer. Scaffold currently returns 501."""
    service.delete_trip(trip_id, request.state.current_user.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
