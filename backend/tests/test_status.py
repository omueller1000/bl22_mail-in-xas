"""Admin -> Status (app.status)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient

from tests.conftest import ADMIN, API, login_as, orcid

pytestmark = pytest.mark.db

URL = f"{API}/admin/status"


async def test_only_admins(client: AsyncClient) -> None:
    await login_as(client, orcid(5), role="operator")
    assert (await client.get(URL)).status_code == 403


async def test_reports_disk_and_collection_sizes(client: AsyncClient) -> None:
    await login_as(client, ADMIN, role="admin")
    response = await client.get(URL)
    assert response.status_code == 200
    body = response.json()
    assert body["environment"]
    database = body["database"]
    assert database["mongodb_version"]
    assert 0 < database["disk"]["used_bytes"] <= database["disk"]["total_bytes"]
    users = next(c for c in database["collections"] if c["name"] == "users")
    assert users["documents"] == 1
    assert users["storage_bytes"] > 0
    assert database["growth"] == {
        "days": 30,
        "sweeps": 0,
        "bytes": 0,
        "days_until_full": None,
    }


async def test_growth_counts_recent_sweeps_only(client: AsyncClient, raw_db: Any) -> None:
    now = datetime.now(UTC)
    await raw_db["sweeps"].insert_many(
        [
            {"sweep_no": n, "uploaded_at": now - timedelta(days=age), "channels": [0.0] * 1000}
            for n, age in enumerate([1, 29, 31], start=1)
        ]
    )
    await login_as(client, ADMIN, role="admin")
    growth = (await client.get(URL)).json()["database"]["growth"]
    assert growth["sweeps"] == 2
    assert growth["bytes"] > 0
    assert growth["days_until_full"] > 0
