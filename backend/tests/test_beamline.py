"""Admin -> Beamline: the energy range that limits elements and edges (app.beamline)."""

from typing import Any

import pytest
from httpx import AsyncClient

from tests.conftest import ADMIN, API, login_as, orcid

pytestmark = pytest.mark.db

URL = f"{API}/admin/beamline"


async def test_only_admins(client: AsyncClient) -> None:
    await login_as(client, orcid(5), role="operator")
    assert (await client.get(URL)).status_code == 403
    body = {"energy_min": 5000, "energy_max": 30000}
    assert (await client.put(URL, json=body)).status_code == 403
    assert (await client.delete(URL)).status_code == 403


async def test_defaults_change_and_restore(client: AsyncClient, raw_db: Any) -> None:
    await login_as(client, ADMIN, role="admin")
    defaults = (await client.get(URL)).json()
    assert defaults["energy_min"] == defaults["default_min"] == 4700
    assert defaults["energy_max"] == defaults["default_max"] == 33000
    assert 0 < defaults["edges_available"] < defaults["edges_total"]

    changed = await client.put(URL, json={"energy_min": 4700, "energy_max": 20000})
    assert changed.status_code == 200
    assert changed.json()["energy_max"] == 20000
    assert changed.json()["edges_available"] < defaults["edges_available"]
    # Only values that differ from the defaults are stored.
    assert await raw_db["settings"].find_one({"_id": "beamline"}) == {
        "_id": "beamline",
        "energy_max": 20000,
    }
    options = (await client.get(f"{API}/measurement-options")).json()
    assert options["energy_max"] == 20000
    assert "Sb" not in [e["symbol"] for e in options["elements"]]  # K 30.5 keV, L below 4.7

    restored = (await client.delete(URL)).json()
    assert (restored["energy_min"], restored["energy_max"]) == (4700, 33000)
    assert await raw_db["settings"].find_one({"_id": "beamline"}) is None


@pytest.mark.parametrize(
    "body",
    [
        {"energy_min": 30000, "energy_max": 5000},
        {"energy_min": 5000, "energy_max": 5000},
        {"energy_min": 0, "energy_max": 5000},
        {"energy_min": 5000, "energy_max": 500000},
    ],
)
async def test_invalid_ranges_are_refused(client: AsyncClient, body: dict[str, float]) -> None:
    await login_as(client, ADMIN, role="admin")
    response = await client.put(URL, json=body)
    assert response.status_code == 422
    assert "minimum must be below the maximum" in response.json()["detail"]
