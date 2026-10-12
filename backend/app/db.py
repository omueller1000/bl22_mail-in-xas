"""MongoDB client lifecycle and the request dependency that hands out the database."""

from typing import Any

from fastapi import Request
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.config import Settings

type Database = AsyncDatabase[dict[str, Any]]


def create_client(settings: Settings) -> AsyncMongoClient[dict[str, Any]]:
    # The client connects lazily, so the app starts even when MongoDB is down;
    # the health endpoint reports the database state.
    return AsyncMongoClient(
        settings.mongodb_uri.get_secret_value(),
        appname="ht-xas-backend",
        tz_aware=True,
        serverSelectionTimeoutMS=5000,
    )


def get_db(request: Request) -> Database:
    return request.app.state.db
