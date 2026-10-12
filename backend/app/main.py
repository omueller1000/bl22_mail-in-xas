"""FastAPI application factory.

Run locally with:  uv run uvicorn app.main:create_app --factory --reload
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__, health
from app.config import Settings, get_settings
from app.db import create_client


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client = create_client(settings)
        app.state.db = client[settings.mongodb_db]
        try:
            yield
        finally:
            await client.close()

    prefix = settings.api_prefix
    app = FastAPI(
        title="Mail-in XAS Portal API",
        version=__version__,
        lifespan=lifespan,
        openapi_url=f"{prefix}/openapi.json" if settings.docs_enabled else None,
        docs_url=f"{prefix}/docs" if settings.docs_enabled else None,
        redoc_url=None,
    )
    app.state.settings = settings

    app.include_router(health.router, prefix=prefix)

    return app
