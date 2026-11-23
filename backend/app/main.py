"""Application entry point.

Creates the FastAPI app, wires middleware and routers.
Run with: uvicorn app.main:app --reload (from the backend directory).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router, root_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    """Application factory so tests can build isolated app instances."""
    settings = get_settings()
    application = FastAPI(title=settings.app_name, version=settings.app_version)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Public endpoints at root path (e.g. GET /health).
    application.include_router(root_router)
    # Business endpoints under /api (add future routers to api_router).
    application.include_router(api_router)

    return application


app = create_app()