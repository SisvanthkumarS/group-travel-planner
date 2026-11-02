import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.controllers import router
from backend.app.core.config import get_settings
from backend.app.core.csrf import CSRFMiddleware
from backend.app.core.filter import require_authentication
from backend.app.core.poll_scheduler import run_poll_scheduler

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    stop = asyncio.Event()
    task = None
    if settings.poll_scheduler_enabled:
        task = asyncio.create_task(
            run_poll_scheduler(stop, settings.poll_scheduler_interval_seconds)
        )
    try:
        yield
    finally:
        stop.set()
        if task is not None:
            await task


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    openapi_url="/api/v1/openapi.json",
    docs_url="/docs",
    dependencies=[Depends(require_authentication)],
    lifespan=lifespan,
)
# CORS wraps CSRF so preflights and readable error responses retain CORS headers.
app.add_middleware(CSRFMiddleware, allowed_origins=settings.cors_origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Protection"],
)
app.include_router(router)
