import logging
from typing import Annotated, Literal

import pymongo
from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel
from pymongo.errors import PyMongoError

from app import __version__
from app.db import Database, get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unreachable"]
    environment: str
    version: str


@router.get("/health", responses={503: {"model": HealthResponse}})
async def health(
    request: Request, response: Response, db: Annotated[Database, Depends(get_db)]
) -> HealthResponse:
    try:
        with pymongo.timeout(2):
            await db.command("ping")
        database: Literal["ok", "unreachable"] = "ok"
    except PyMongoError as exc:
        logger.warning("MongoDB ping failed: %s: %s", type(exc).__name__, exc)
        database = "unreachable"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(
        status="ok" if database == "ok" else "degraded",
        database=database,
        environment=request.app.state.settings.environment,
        version=__version__,
    )
