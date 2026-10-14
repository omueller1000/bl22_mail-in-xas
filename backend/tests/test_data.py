"""Data viewer and export endpoints (requirements §11.3-§11.5)."""

import io
import zipfile
from typing import Any

import pytest
from httpx import AsyncClient

from tests.conftest import API, issue_frames, login_as, orcid
from tests.test_instrument import ready_frame, sweep

pytestmark = pytest.mark.db

PROCESSED = {
    "metadata": {"e0": 8979.0, "rbkg": 1.0},
    "mu": {"x": [8900.0, 8901.0], "y": [0.1, 0.2]},
    "chi": {"x": [2.0, 2.1], "y": [0.01, 0.02]},
}


async def measured_frame(
    client: AsyncClient, raw_db: Any, instrument: AsyncClient
) -> dict[str, str]:
    """A frame with two sweeps in batch 1 and one in batch 2; sweep 1 is processed."""
    ready = await ready_frame(client, raw_db)
    url = f"{API}/instrument/measurements/{ready['measurement']}/sweeps"
    await instrument.post(url, json=sweep(1, 1))
    second = sweep(1, 2)
    second["channels"][2]["values"] = [0.25] * 5  # i1
    await instrument.post(url, json=second)
    await instrument.post(url, json=sweep(2, 3))
    await instrument.put(f"{url}/1/1/processed", json=PROCESSED)
    await login_as(client, orcid(1))
    return ready


async def first_sweep(client: AsyncClient, code: str) -> dict[str, Any]:
    return (await client.get(f"{API}/frames/{code}/sweeps")).json()[0]


async def test_list_sweeps(client: AsyncClient, raw_db: Any, instrument: AsyncClient) -> None:
    ready = await measured_frame(client, raw_db, instrument)
    listed = (await client.get(f"{API}/frames/{ready['code']}/sweeps")).json()
    assert [(s["batch_no"], s["sweep_no"]) for s in listed] == [(1, 1), (1, 2), (2, 3)]
    first = listed[0]
    assert first["points"] == 5
    assert first["channels"] == ["energy", "i0", "i1"]
    assert first["spectra"] == ["sample_trans"]
    assert first["measured"]["element"] == "Cu"
    assert [s["has_processed"] for s in listed] == [True, False, False]


async def test_sweep_detail_and_curves(
    client: AsyncClient, raw_db: Any, instrument: AsyncClient
) -> None:
    ready = await measured_frame(client, raw_db, instrument)
    base = f"{API}/sweeps/{(await first_sweep(client, ready['code']))['id']}"

    detail = (await client.get(base)).json()
    assert detail["metadata"] == {"lattice_spacing": 1.920156}
    assert detail["processed"]["metadata"]["e0"] == 8979.0
    assert detail["processed"]["has_chi"] is True

    async def curve(**params: str) -> Any:
        return await client.get(f"{base}/curve", params=params)

    raw = (await curve(view="raw", name="i1")).json()
    assert raw["x"][0] == 8900.0 and raw["y"] == [0.5] * 5
    trans = (await curve(view="spectrum", name="sample_trans")).json()
    assert trans["y"][0] == pytest.approx(0.6931, abs=1e-4)  # ln(1 / 0.5)
    assert (await curve(view="chi")).json() == PROCESSED["chi"]

    assert (await curve(view="raw", name="fy")).status_code == 404
    assert (await curve(view="spectrum", name="fy_norm")).status_code == 404


async def test_merge_within_a_batch(
    client: AsyncClient, raw_db: Any, instrument: AsyncClient
) -> None:
    ready = await measured_frame(client, raw_db, instrument)
    url = f"{API}/measurements/{ready['measurement']}/batches/1/merge"
    merged = await client.get(url, params={"view": "raw", "name": "i1", "sweeps": [1, 2]})
    assert merged.status_code == 200, merged.text
    assert merged.json()["y"] == [0.375] * 5
    # Sweep 3 belongs to batch 2.
    other_batch = await client.get(url, params={"view": "raw", "name": "i1", "sweeps": [3]})
    assert other_batch.status_code == 404


async def test_frames_say_whether_they_have_data(
    client: AsyncClient, raw_db: Any, instrument: AsyncClient
) -> None:
    ready = await measured_frame(client, raw_db, instrument)
    assert (await client.get(f"{API}/frames/{ready['code']}")).json()["has_data"] is True
    [other] = await issue_frames(client, orcid(1))
    listed = {f["barcode"]: f["has_data"] for f in (await client.get(f"{API}/frames")).json()}
    assert listed == {ready["code"]: True, other: False}


async def test_samples_list_the_frames_with_their_data(
    client: AsyncClient, raw_db: Any, instrument: AsyncClient
) -> None:
    ready = await measured_frame(client, raw_db, instrument)
    sample = (await client.get(f"{API}/samples/{ready['sample']}")).json()
    assert sample["frames"] == [ready["code"]]
    assert sample["data_frames"] == [ready["code"]]


async def test_only_owner_and_operators_see_data(
    client: AsyncClient, raw_db: Any, instrument: AsyncClient
) -> None:
    ready = await measured_frame(client, raw_db, instrument)
    sweep_id = (await first_sweep(client, ready["code"]))["id"]

    await login_as(client, orcid(2))
    assert (await client.get(f"{API}/frames/{ready['code']}/sweeps")).status_code == 404
    assert (await client.get(f"{API}/sweeps/{sweep_id}")).status_code == 404
    assert (await client.get(f"{API}/frames/{ready['code']}/export.zip")).status_code == 404

    await login_as(client, orcid(3), role="operator")
    assert (await client.get(f"{API}/sweeps/{sweep_id}")).status_code == 200


async def test_export_zip(client: AsyncClient, raw_db: Any, instrument: AsyncClient) -> None:
    ready = await measured_frame(client, raw_db, instrument)
    response = await client.get(f"{API}/frames/{ready['code']}/export.zip")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert f"{ready['code']}.zip" in response.headers["content-disposition"]

    archive = zipfile.ZipFile(io.BytesIO(response.content))
    stem = f"Left-A_CuO/{ready['code']}_1_Left-A_Cu_K_EXAFS"
    assert archive.namelist() == [
        f"{stem}_1_001.xdi",
        f"{stem}_1_001_proc_mu.xdi",
        f"{stem}_1_001_proc_chi.xdi",
        f"{stem}_1_002.xdi",
        f"{stem}_2_003.xdi",
    ]
    text = archive.read(f"{stem}_1_001_proc_mu.xdi").decode()
    assert "# Processing.e0: 8979.0" in text
    assert "# Sample.name: CuO" in text


async def test_export_without_data(
    client: AsyncClient, raw_db: Any, instrument: AsyncClient
) -> None:
    ready = await ready_frame(client, raw_db)
    response = await client.get(f"{API}/frames/{ready['code']}/export.zip")
    assert response.status_code == 404
