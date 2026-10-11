"""FastAPI application entrypoint with lifespan, middleware and routers."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import BASE_DIR, get_settings
from app.database.init_db import init_db
from app.database.seed import seed_demo_data
from app.logging_config import setup_logging
from app.routers import accounts as accounts_router
from app.routers import ai, dashboard, groups, health, logs, pages, posts, products
from app.routers import automation as automation_router
from app.routers import facebook as facebook_router
from app.routers import settings as settings_router
from app.routers import stats as stats_router
from app.routers import system as system_router
from app.services.scheduler import automation


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Handle application startup and shutdown events."""
    setup_logging()
    logger = logging.getLogger("pod-automation")
    settings = get_settings()

    data_dir: Path = BASE_DIR / "data"
    logs_dir: Path = BASE_DIR / "logs"
    data_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Starting %s in %s environment.",
        settings.APP_NAME,
        settings.APP_ENV,
    )
    if settings.APP_ENV.lower() == "development":
        init_db()
        logger.info("Database initialized.")
        seed_demo_data()
        logger.info("Demo data seeded.")
    if settings.FACEBOOK_DRY_RUN:
        logger.info("Facebook dry-run mode is ON: publishing is simulated.")
    else:
        logger.warning("LIVE MODE: posts will be published to Facebook")
    if settings.SCHEDULER_ENABLED:
        automation.start()
        logger.info("Automation scheduler started.")
    else:
        logger.info("Automation scheduler is disabled.")
    yield
    await automation.stop()
    logger.info("Shutting down %s.", settings.APP_NAME)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    settings = get_settings()

    app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

    app.mount(
        "/static",
        StaticFiles(directory=str(BASE_DIR / "app" / "static")),
        name="static",
    )

    app.include_router(health.router)
    app.include_router(pages.router)
    app.include_router(products.router)
    app.include_router(posts.router)
    app.include_router(ai.router)
    app.include_router(logs.router)
    app.include_router(settings_router.router)
    app.include_router(dashboard.router)
    app.include_router(facebook_router.router)
    app.include_router(automation_router.router)
    app.include_router(groups.router)
    app.include_router(groups.leads_router)
    app.include_router(groups.safety_router)
    app.include_router(stats_router.router)
    app.include_router(system_router.router)
    app.include_router(accounts_router.router)

    # Local-only CORS hardening: never use "*". Browsers calling the API
    # must come from 127.0.0.1 / localhost origins listed in settings.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Confirm-Delete"],
        max_age=600,
    )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        """Return HTTP 400 for service-layer validation errors."""
        return JSONResponse(
            status_code=400,
            content={"detail": str(exc)},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Return a clean JSON error for unhandled exceptions."""
        logger = logging.getLogger("pod-automation")
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error."},
        )

    return app


app: FastAPI = create_app()
"""Application instance served by Uvicorn."""
