"""Data viewer, processing and export endpoints (requirements §11.3-§11.5)."""

import io
import zipfile
from typing import Any

import numpy as np
import pytest
from httpx import AsyncClient

from tests.conftest import API, issue_frames, login_as, orcid
from tests.test_instrument import ready_frame, sweep
from tests.test_processing import SHELL_R, synthetic_mu

pytestmark = pytest.mark.db


def exafs_sweep(batch: int, number: int, noise: float = 0.0) -> dict[str, Any]:
    """A realistic Cu K sweep (transmission): ln(i0/i1) is the synthetic mu(E)."""
    energy, mu = synthetic_mu(height=2.0)
    mu = mu + noise * np.random.default_rng(number).standard_normal(mu.size)
    return {
        "batch_no": batch,
        "sweep_no": number,
        "metadata": {},
        "channels": [
            {"name": "energy", "unit": "eV", "values": energy.tolist()},
            {"name": "i0", "unit": "counts", "values": [1.0] * energy.size},
            {"name": "i1", "unit": "counts", "values": np.exp(-mu).tolist()},
        ],
    }


async def measured_frame(
    client: AsyncClient, raw_db: Any, instrument: AsyncClient
) -> dict[str, str]:
    """A frame with two tiny sweeps in batch 1 and one in batch 2."""
    ready = await ready_frame(client, raw_db)
    url = f"{API}/instrument/measurements/{ready['measurement']}/sweeps"
    await instrument.post(url, json=sweep(1, 1))
    second = sweep(1, 2)
    second["channels"][2]["values"] = [0.25] * 5  # i1
    await instrument.post(url, json=second)
    await instrument.post(url, json=sweep(2, 3))
    await login_as(client, orcid(1))
    return ready


async def exafs_frame(client: AsyncClient, raw_db: Any, instrument: AsyncClient) -> dict[str, str]:
    """A frame with three realistic sweeps in batch 1."""
    ready = await ready_frame(client, raw_db)
    url = f"{API}/instrument/measurements/{ready['measurement']}/sweeps"
    for number in (1, 2, 3):
        response = await instrument.post(url, json=exafs_sweep(1, number, noise=0.001))
        assert response.status_code == 201, response.text
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


async def test_sweep_detail_and_curves(
    client: AsyncClient, raw_db: Any, instrument: AsyncClient
) -> None:
    ready = await measured_frame(client, raw_db, instrument)
    base = f"{API}/sweeps/{(await first_sweep(client, ready['code']))['id']}"

    detail = (await client.get(base)).json()
    assert detail["metadata"] == {"lattice_spacing": 1.920156}

    async def curve(**params: str) -> Any:
        return await client.get(f"{base}/curve", params=params)

    raw = (await curve(view="raw", name="i1")).json()
    assert raw["x"][0] == 8900.0 and raw["y"] == [0.5] * 5
    trans = (await curve(view="spectrum", name="sample_trans")).json()
    assert trans["y"][0] == pytest.approx(0.6931, abs=1e-4)  # ln(1 / 0.5)

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


async def test_process_a_single_sweep_and_a_merge(
    client: AsyncClient, raw_db: Any, instrument: AsyncClient
) -> None:
    ready = await exafs_frame(client, raw_db, instrument)
    url = f"{API}/measurements/{ready['measurement']}/batches/1/process"

    single = await client.get(url, params={"spectrum": "sample_trans", "sweeps": [2]})
    assert single.status_code == 200, single.text
    p = single.json()
    assert p["sweeps"] == [2]
    assert (p["element"], p["edge"], p["e0"]) == ("Cu", "K", 8979.0)
    assert p["edge_step"] == pytest.approx(2.0, rel=0.05)
    assert p["problems"] == []
    assert len(p["mu"]["x"]) == len(p["pre_edge"]["y"]) == len(p["background"]["y"])
    assert p["pre_edge"]["y"][-1] is not None  # drawn over the whole energy range
    assert p["chi"]["x"][0] == 0
    assert p["ft_window"]["x"] == p["chi"]["x"] and max(p["ft_window"]["y"]) == 1
    magnitude = p["chir"]["magnitude"]
    peak = p["chir"]["r"][magnitude.index(max(magnitude))]
    assert peak == pytest.approx(SHELL_R, abs=0.1)
    assert p["parameters"]["pre_order"] == 2 and p["parameters"]["post_order"] == 3

    merged = await client.get(url, params={"spectrum": "sample_trans", "sweeps": [1, 2, 3]})
    assert merged.json()["sweeps"] == [1, 2, 3]

    unavailable = await client.get(url, params={"spectrum": "fy_norm", "sweeps": [1]})
    assert unavailable.status_code == 404


async def test_processing_problems_are_reported(
    client: AsyncClient, raw_db: Any, instrument: AsyncClient
) -> None:
    ready = await measured_frame(client, raw_db, instrument)  # 5 points around 8900 eV
    url = f"{API}/measurements/{ready['measurement']}/batches/1/process"
    p = (await client.get(url, params={"spectrum": "sample_trans", "sweeps": [1]})).json()
    assert p["edge_step"] is None and p["chi"] is None
    assert p["problems"]


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
    process = f"{API}/measurements/{ready['measurement']}/batches/1/process"
    params = {"spectrum": "sample_trans", "sweeps": [1]}

    await login_as(client, orcid(2))
    assert (await client.get(f"{API}/frames/{ready['code']}/sweeps")).status_code == 404
    assert (await client.get(f"{API}/sweeps/{sweep_id}")).status_code == 404
    assert (await client.get(process, params=params)).status_code == 404
    assert (await client.get(f"{API}/frames/{ready['code']}/export.zip")).status_code == 404

    await login_as(client, orcid(3), role="operator")
    assert (await client.get(f"{API}/sweeps/{sweep_id}")).status_code == 200


async def test_export_zip(client: AsyncClient, raw_db: Any, instrument: AsyncClient) -> None:
    ready = await exafs_frame(client, raw_db, instrument)
    response = await client.get(f"{API}/frames/{ready['code']}/export.zip")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert f"{ready['code']}.zip" in response.headers["content-disposition"]

    archive = zipfile.ZipFile(io.BytesIO(response.content))
    stem = f"Left-A_CuO/{ready['code']}_1_Left-A_Cu_K_EXAFS_1"
    assert archive.namelist() == [
        f"{stem}_{n:03d}{kind}.xdi"
        for n in (1, 2, 3)
        for kind in ("", "_proc_mu", "_proc_chi", "_proc_chir")
    ]
    text = archive.read(f"{stem}_001_proc_mu.xdi").decode()
    assert "# Processing.e0: 8979.0" in text
    assert "# Processing.spectrum: sample_trans" in text
    assert "# Column.5: background" in text
    assert "# Sample.name: CuO" in text


async def test_export_skips_processing_that_is_not_possible(
    client: AsyncClient, raw_db: Any, instrument: AsyncClient
) -> None:
    ready = await measured_frame(client, raw_db, instrument)  # tiny sweeps
    response = await client.get(f"{API}/frames/{ready['code']}/export.zip")
    names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
    assert len(names) == 3 and not any("_proc_" in n for n in names)


async def test_export_without_data(
    client: AsyncClient, raw_db: Any, instrument: AsyncClient
) -> None:
    ready = await ready_frame(client, raw_db)
    response = await client.get(f"{API}/frames/{ready['code']}/export.zip")
    assert response.status_code == 404
