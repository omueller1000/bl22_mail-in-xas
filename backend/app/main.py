"""FastAPI application factory.

Run locally with:  uv run uvicorn app.main:create_app --factory --reload --port 8010
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.routing import APIRoute
from pymongo.errors import PyMongoError

from app import __version__, catalog, health
from app import status as status_routes
from app.auth import orcid, sessions
from app.auth import routes as auth_routes
from app.config import Settings, get_settings
from app.csrf import csrf_middleware
from app.data import repository as data
from app.data import routes as data_routes
from app.db import Database, create_client
from app.frames import config_routes as frame_config_routes
from app.frames import repository as frames
from app.frames import routes as frames_routes
from app.frames import safety_routes
from app.instrument import admin_routes as service_client_routes
from app.instrument import keys as api_keys
from app.instrument import routes as instrument_routes
from app.limits import limit_body_size
from app.mail import outbox as mail_outbox
from app.mail import routes as mail_routes
from app.mail import sender as mail_sender
from app.material_requests import routes as material_requests_routes
from app.measurements import repository as measurements
from app.measurements import routes as measurements_routes
from app.processing import routes as xas_parameter_routes
from app.samples import repository as samples
from app.samples import routes as samples_routes
from app.scanning import routes as scanning_routes
from app.users import repository as users
from app.users import routes as users_routes

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    *,
    orcid_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    """Build the app. `orcid_transport` lets tests replace the network calls to ORCID."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client = create_client(settings)
        app.state.db = client[settings.mongodb_db]
        app.state.http = httpx.AsyncClient(transport=orcid_transport, timeout=10)
        await _ensure_indexes(app.state.db)
        sender = (
            asyncio.create_task(mail_sender.run(app.state.db, settings))
            if settings.mail_sender_enabled
            else None
        )
        try:
            yield
        finally:
            if sender:
                sender.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await sender
            await app.state.http.aclose()
            await client.close()

    prefix = settings.api_prefix
    app = FastAPI(
        title="Mail-in XAS Portal API",
        version=__version__,
        lifespan=lifespan,
        openapi_url=f"{prefix}/openapi.json" if settings.docs_enabled else None,
        docs_url=f"{prefix}/docs" if settings.docs_enabled else None,
        redoc_url=None,
        # Operation IDs = function names, so generated client code stays readable.
        generate_unique_id_function=_operation_id,
    )
    app.state.settings = settings
    app.middleware("http")(csrf_middleware(prefix))
    app.middleware("http")(limit_body_size)

    app.include_router(health.router, prefix=prefix)
    app.include_router(auth_routes.router, prefix=prefix)
    if settings.dev_login_enabled:
        app.include_router(auth_routes.dev_router, prefix=prefix)
    app.include_router(users_routes.router, prefix=prefix)
    app.include_router(catalog.router, prefix=prefix)
    app.include_router(frames_routes.router, prefix=prefix)
    app.include_router(frame_config_routes.router, prefix=prefix)
    app.include_router(safety_routes.router, prefix=prefix)
    app.include_router(measurements_routes.router, prefix=prefix)
    app.include_router(scanning_routes.router, prefix=prefix)
    app.include_router(service_client_routes.router, prefix=prefix)
    app.include_router(instrument_routes.router, prefix=prefix)
    app.include_router(material_requests_routes.router, prefix=prefix)
    app.include_router(samples_routes.router, prefix=prefix)
    app.include_router(data_routes.router, prefix=prefix)
    app.include_router(xas_parameter_routes.router, prefix=prefix)
    app.include_router(mail_routes.router, prefix=prefix)
    app.include_router(status_routes.router, prefix=prefix)

    return app


async def _ensure_indexes(db: Database) -> None:
    # Idempotent. If MongoDB is down at startup the app still starts (health reports it);
    # indexes are then created on the next start.
    try:
        await users.ensure_indexes(db)
        await sessions.ensure_indexes(db)
        await orcid.ensure_indexes(db)
        await frames.ensure_indexes(db)
        await samples.ensure_indexes(db)
        await measurements.ensure_indexes(db)
        await scanning_routes.ensure_indexes(db)
        await data.ensure_indexes(db)
        await api_keys.ensure_indexes(db)
        await mail_outbox.ensure_indexes(db)
    except PyMongoError as exc:
        logger.error("Could not create MongoDB indexes: %s: %s", type(exc).__name__, exc)


def _operation_id(route: APIRoute) -> str:
    return route.name
