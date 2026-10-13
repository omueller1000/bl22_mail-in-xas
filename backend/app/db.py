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
    uri = settings.mongodb_uri.get_secret_value()
    options: dict[str, Any] = {"appname": "ht-xas-backend", "tz_aware": True}
    # Keyword options override the URI; only set the timeout if the URI does not.
    if "serverselectiontimeoutms" not in uri.lower():
        options["serverSelectionTimeoutMS"] = 5000
    return AsyncMongoClient(uri, **options)


def get_db(request: Request) -> Database:
    return request.app.state.db
