from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.controllers import router
from backend.app.core.config import get_settings
from backend.app.core.filter import require_authentication

settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    openapi_url="/api/v1/openapi.json",
    docs_url="/docs",
    dependencies=[Depends(require_authentication)],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(router)
