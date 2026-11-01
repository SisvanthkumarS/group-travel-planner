from fastapi import APIRouter

from backend.app.controllers.AuthController import router as auth_router
from backend.app.controllers.InvitationController import router as invitation_router
from backend.app.controllers.TripController import router as trip_router

router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(trip_router)
router.include_router(invitation_router)
