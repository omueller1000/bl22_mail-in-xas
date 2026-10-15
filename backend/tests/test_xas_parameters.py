"""Admin page for the XAS processing parameters (app.processing.settings)."""

import io
import zipfile
from typing import Any

import pytest
from httpx import AsyncClient

from tests.conftest import ADMIN, API, login_as, orcid
from tests.test_data import exafs_frame

pytestmark = pytest.mark.db

URL = f"{API}/admin/xas-parameters"


def by_name(listing: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {p["name"]: p for p in listing}


async def test_only_admins(client: AsyncClient) -> None:
    await login_as(client, orcid(5), role="operator")
    assert (await client.get(URL)).status_code == 403
    assert (await client.put(URL, json={"values": {"rbkg": 1.2}})).status_code == 403


async def test_lists_the_scientific_parameters_with_defaults(client: AsyncClient) -> None:
    await login_as(client, ADMIN, role="admin")
    params = by_name((await client.get(URL)).json())
    assert params["pre_order"] == {
        "name": "pre_order",
        "group": "Normalisation",
        "label": "Pre-edge polynomial order",
        "unit": "",
        "minimum": 0,
        "maximum": 3,
        "integer": True,
        "none_means": None,
        "value": 2,
        "default": 2,
    }
    assert params["bkg_kmax"]["none_means"] == "end of the data"
    # Technical and display settings are not editable here.
    assert not {"kstep", "nfft", "curve_overlap", "rmax"} & params.keys()


async def test_change_and_restore(client: AsyncClient, raw_db: Any) -> None:
    await login_as(client, ADMIN, role="admin")
    changed = await client.put(URL, json={"values": {"rbkg": 1.2, "pre_order": 1}})
    assert changed.status_code == 200, changed.text
    params = by_name(changed.json())
    assert (params["rbkg"]["value"], params["rbkg"]["default"]) == (1.2, 1.0)
    assert params["pre_order"]["value"] == 1

    # Only values that differ from the defaults are stored.
    await client.put(URL, json={"values": {"rbkg": 1.0, "bkg_kmax": 14}})
    doc = await raw_db.settings.find_one({"_id": "xas_parameters"})
    assert doc["overrides"] == {"pre_order": 1, "bkg_kmax": 14.0}

    restored = by_name((await client.delete(URL)).json())
    assert restored["pre_order"]["value"] == 2 and restored["bkg_kmax"]["value"] is None
    assert await raw_db.settings.find_one({"_id": "xas_parameters"}) is None


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"rbkg": 9}, "between 0.2 and 5"),
        ({"pre_order": 1.5}, "whole number"),
        ({"rbkg": None}, "value is required"),
        ({"nfft": 4096}, "cannot be changed"),
    ],
)
async def test_invalid_values_are_refused(
    client: AsyncClient, values: dict[str, Any], message: str
) -> None:
    await login_as(client, ADMIN, role="admin")
    response = await client.put(URL, json={"values": values})
    assert response.status_code == 422
    assert message in response.json()["detail"]


async def test_changes_apply_to_processing_and_export(
    client: AsyncClient, raw_db: Any, instrument: AsyncClient
) -> None:
    ready = await exafs_frame(client, raw_db, instrument)
    await login_as(client, ADMIN, role="admin")
    await client.put(URL, json={"values": {"rbkg": 1.3, "ft_kmin": 3}})

    await login_as(client, orcid(1))
    process = f"{API}/measurements/{ready['measurement']}/batches/1/process"
    result = await client.get(process, params={"spectrum": "sample_trans", "sweeps": [1]})
    assert result.json()["parameters"]["rbkg"] == 1.3
    assert result.json()["parameters"]["ft_kmin"] == 3

    archive = zipfile.ZipFile(
        io.BytesIO((await client.get(f"{API}/frames/{ready['code']}/export.zip")).content)
    )
    header = archive.read(next(n for n in archive.namelist() if "_proc_chi." in n)).decode()
    assert "# Processing.rbkg: 1.3" in header
    assert "# Processing.ft_kmin: 3.0" in header
