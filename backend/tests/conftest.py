import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from dotenv import dotenv_values
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pymongo import AsyncMongoClient

from app.config import Settings
from app.csrf import CSRF_HEADER, CSRF_VALUE
from app.main import create_app


def _test_mongodb_uri() -> str | None:
    """From the environment, or from backend/.env.test (git-ignored)."""
    if uri := os.environ.get("HT_XAS_TEST_MONGODB_URI"):
        return uri
    env_file = Path(__file__).parents[1] / ".env.test"
    if env_file.exists():
        return dotenv_values(env_file).get("HT_XAS_TEST_MONGODB_URI")
    return None


# Tests marked "db" run against this MongoDB (database ht_xas_test, wiped before each test).
TEST_MONGODB_URI = _test_mongodb_uri()
TEST_DB = "ht_xas_test"

# Nothing listens on port 1, so connections fail fast.
UNREACHABLE_MONGODB_URI = "mongodb://127.0.0.1:1/?serverSelectionTimeoutMS=200"

API = "/mail-in-xas/api"


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "environment": "local",
        "mongodb_uri": TEST_MONGODB_URI or UNREACHABLE_MONGODB_URI,
        "mongodb_db": TEST_DB,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


@asynccontextmanager
async def app_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Run the app's lifespan and yield an HTTP client that talks to it in-process.

    The client sends the CSRF header by default, like the real frontend.
    """
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers={CSRF_HEADER: CSRF_VALUE}
        ) as client:
            yield client


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if TEST_MONGODB_URI:
        return
    skip = pytest.mark.skip(reason="HT_XAS_TEST_MONGODB_URI not set (env or backend/.env.test)")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
async def clean_db() -> AsyncIterator[None]:
    """Empty the test database before the test."""
    assert TEST_MONGODB_URI and TEST_DB.endswith("_test")  # never wipe a real database
    client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(TEST_MONGODB_URI)
    try:
        await client.drop_database(TEST_DB)
    finally:
        await client.close()
    yield


@pytest.fixture
async def client(clean_db: None) -> AsyncIterator[AsyncClient]:
    """Client for an app with dev login enabled, on an empty test database."""
    app = create_app(make_settings(dev_login_enabled=True))
    async with app_client(app) as c:
        yield c


def orcid(serial: int) -> str:
    """A valid (checksummed) test ORCID iD, e.g. orcid(1) -> '0000-0000-0000-001X'."""
    base = f"{serial:015d}"
    total = 0
    for digit in base:
        total = (total + int(digit)) * 2
    check = (12 - total % 11) % 11
    raw = base + ("X" if check == 10 else str(check))
    return "-".join(raw[i : i + 4] for i in range(0, 16, 4))


PROFILE: dict[str, Any] = {
    "email": "ada@example.org",
    "phone": "+1 650 555 0100",
    "affiliation": "Example University",
    "shipping_address": {
        "care_of": "Chemistry Dept.",
        "street1": "1 Example Way",
        "city": "Example City",
        "region": "CA",
        "postal_code": "94025",
        "country": "USA",
    },
}


async def dev_login(
    client: AsyncClient, orcid_id: str, *, name: str | None = "Ada Test", role: str | None = None
) -> dict[str, Any]:
    response = await client.post(
        f"{API}/auth/dev-login", json={"orcid": orcid_id, "name": name, "role": role}
    )
    assert response.status_code == 200, response.text
    return response.json()


async def register(client: AsyncClient, **overrides: Any) -> dict[str, Any]:
    response = await client.post(f"{API}/users", json={**PROFILE, **overrides})
    assert response.status_code == 201, response.text
    return response.json()


async def login_as(client: AsyncClient, orcid_id: str, role: str = "user") -> dict[str, Any]:
    """Dev-login (registering the account if it is new) with the given role; returns the user."""
    me = await dev_login(client, orcid_id, role=role)
    if me["status"] == "authenticated":
        return me["user"]
    return await register(client)
