import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import Settings

# Tests marked "db" run against this MongoDB (database ht_xas_test, wiped by tests).
TEST_MONGODB_URI = os.environ.get("HT_XAS_TEST_MONGODB_URI")

# Nothing listens on port 1, so connections fail fast.
UNREACHABLE_MONGODB_URI = "mongodb://127.0.0.1:1/?serverSelectionTimeoutMS=200"


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "environment": "local",
        "mongodb_uri": TEST_MONGODB_URI or UNREACHABLE_MONGODB_URI,
        "mongodb_db": "ht_xas_test",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


@asynccontextmanager
async def app_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Run the app's lifespan and yield an HTTP client that talks to it in-process."""
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if TEST_MONGODB_URI:
        return
    skip = pytest.mark.skip(reason="HT_XAS_TEST_MONGODB_URI not set")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)
