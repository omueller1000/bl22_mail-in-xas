"""Frame configuration: plates, note and sample positions (requirements §5.1, §6.6, §8.1)."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import AsyncClient
from pymongo import AsyncMongoClient

from tests.conftest import API, TEST_DB, TEST_MONGODB_URI, issue_frames, login_as, orcid

pytestmark = pytest.mark.db


@pytest.fixture
async def raw_db() -> AsyncIterator[Any]:
    client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(TEST_MONGODB_URI)
    yield client[TEST_DB]
    await client.close()


async def frame(client: AsyncClient, code: str) -> dict[str, Any]:
    response = await client.get(f"{API}/frames/{code}")
    assert response.status_code == 200, response.text
    return response.json()


async def set_plates(
    client: AsyncClient,
    code: str,
    left: str | None,
    right: str | None,
    version: int | None = None,
) -> Any:
    if version is None:
        version = (await frame(client, code))["version"]
    return await client.put(
        f"{API}/frames/{code}/plates", json={"version": version, "left": left, "right": right}
    )


async def new_sample(client: AsyncClient, name: str = "Fe2O3") -> str:
    response = await client.post(f"{API}/samples", json={"name": name})
    return response.json()["id"]


async def assign(client: AsyncClient, code: str, position: str, sample_id: str) -> Any:
    version = (await frame(client, code))["version"]
    return await client.put(
        f"{API}/frames/{code}/positions/{position}",
        json={"version": version, "sample_id": sample_id},
    )


async def test_new_frame_is_empty(client: AsyncClient) -> None:
    [code] = await issue_frames(client, orcid(1))
    f = await frame(client, code)
    assert f["plates"] == {"left": None, "right": None}
    assert f["positions"] == []
    assert f["note"] == ""
    assert f["safety"] is None
    assert f["locked"] is False


async def test_mount_plates(client: AsyncClient) -> None:
    [code] = await issue_frames(client, orcid(1))
    response = await set_plates(client, code, "8-circle", "8-slot")
    assert response.status_code == 200, response.text
    assert response.json()["plates"] == {"left": "8-circle", "right": "8-slot"}
    assert response.json()["version"] == 1


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (None, "6-circle-gas"),  # gas plate only on the left
        ("6-circle-gas", "8-circle"),  # gas plate blocks the right side
        ("8-circle-gas", None),  # obsolete type
        ("nonsense", None),
    ],
)
async def test_invalid_plate_combinations(
    client: AsyncClient, left: str | None, right: str | None
) -> None:
    [code] = await issue_frames(client, orcid(1))
    assert (await set_plates(client, code, left, right)).status_code == 422


async def test_gas_plate_alone_and_one_sided_frames_are_fine(client: AsyncClient) -> None:
    [code] = await issue_frames(client, orcid(1))
    assert (await set_plates(client, code, "6-circle-gas", None)).status_code == 200
    assert (await set_plates(client, code, None, "8-slot")).status_code == 200


async def test_assign_replace_and_clear_samples(client: AsyncClient) -> None:
    [code] = await issue_frames(client, orcid(1))
    await set_plates(client, code, "8-circle", None)
    fe = await new_sample(client, "Fe2O3")
    cu = await new_sample(client, "CuO")

    response = await assign(client, code, "Left-A", fe)
    assert response.status_code == 200, response.text
    assert (await assign(client, code, "Left-A", fe)).status_code == 200  # same place again
    # A sample is placed only once per frame.
    twice = await assign(client, code, "Left-B", fe)
    assert twice.status_code == 409
    assert "already at Left-A" in twice.json()["detail"]
    await assign(client, code, "Left-A", cu)  # replace
    await assign(client, code, "Left-B", fe)  # Fe2O3 is no longer elsewhere on the frame
    positions = {p["position"]: p["sample_name"] for p in (await frame(client, code))["positions"]}
    assert positions == {"Left-A": "CuO", "Left-B": "Fe2O3"}

    sample = (await client.get(f"{API}/samples/{fe}")).json()
    assert sample["frames"] == [code]

    version = (await frame(client, code))["version"]
    response = await client.delete(
        f"{API}/frames/{code}/positions/Left-B", params={"version": version}
    )
    assert [p["position"] for p in response.json()["positions"]] == ["Left-A"]


async def test_position_must_exist_on_mounted_plates(client: AsyncClient) -> None:
    [code] = await issue_frames(client, orcid(1))
    await set_plates(client, code, "6-circle-gas", None)
    sample = await new_sample(client)
    assert (await assign(client, code, "Left-F", sample)).status_code == 200
    assert (await assign(client, code, "Left-G", sample)).status_code == 422  # only A-F
    assert (await assign(client, code, "Right-A", sample)).status_code == 422


async def test_only_own_samples(client: AsyncClient) -> None:
    await login_as(client, orcid(2))
    others = await new_sample(client)
    [code] = await issue_frames(client, orcid(1))
    await set_plates(client, code, "8-circle", None)
    assert (await assign(client, code, "Left-A", others)).status_code == 422
    assert (await assign(client, code, "Left-A", "not-an-id")).status_code == 422


async def test_changing_a_plate_clears_that_side(client: AsyncClient, raw_db: Any) -> None:
    [code] = await issue_frames(client, orcid(1))
    await set_plates(client, code, "8-circle", "8-circle")
    await assign(client, code, "Left-A", await new_sample(client, "Fe2O3"))
    await assign(client, code, "Right-A", await new_sample(client, "CuO"))
    await raw_db.measurements.insert_many(
        [{"frame": code, "position": "Left-A"}, {"frame": code, "position": "Right-A"}]
    )

    response = await set_plates(client, code, "8-circle", "8-slot")  # right side changes
    assert [p["position"] for p in response.json()["positions"]] == ["Left-A"]
    remaining = await raw_db.measurements.find({"frame": code}).to_list()
    assert [m["position"] for m in remaining] == ["Left-A"]

    # A gas plate on the left removes the right plate and clears everything.
    response = await set_plates(client, code, "6-circle-gas", None)
    assert response.json()["positions"] == []


async def test_note(client: AsyncClient) -> None:
    [code] = await issue_frames(client, orcid(1))
    response = await client.put(
        f"{API}/frames/{code}/note", json={"version": 0, "note": "  batch 2, Fe catalysts "}
    )
    assert response.json()["note"] == "batch 2, Fe catalysts"
    too_long = await client.put(f"{API}/frames/{code}/note", json={"version": 1, "note": "x" * 501})
    assert too_long.status_code == 422


async def test_stale_version_is_rejected(client: AsyncClient) -> None:
    [code] = await issue_frames(client, orcid(1))
    assert (await set_plates(client, code, "8-circle", None, version=0)).status_code == 200
    response = await set_plates(client, code, "8-slot", None, version=0)  # outdated
    assert response.status_code == 409
    assert "changed elsewhere" in response.json()["detail"]
    assert (await frame(client, code))["plates"]["left"] == "8-circle"


async def test_only_owner_configures(client: AsyncClient) -> None:
    [code] = await issue_frames(client, orcid(1))
    await login_as(client, orcid(2))
    assert (await set_plates(client, code, "8-circle", None, version=0)).status_code == 404
    await login_as(client, orcid(3), role="operator")
    assert (await set_plates(client, code, "8-circle", None, version=0)).status_code == 404


@pytest.mark.parametrize(
    "change",
    [{"safety_declared": {"at": "now", "by": {"name": "x"}}}, {"state": "received"}],
    ids=["declared safe", "at the facility"],
)
async def test_no_configuration_after_declaration_or_shipping_back(
    client: AsyncClient, raw_db: Any, change: dict[str, Any]
) -> None:
    [code] = await issue_frames(client, orcid(1))
    await raw_db.frames.update_one({"_id": code}, {"$set": change})
    response = await client.put(
        f"{API}/frames/{code}/plates", json={"version": 0, "left": "8-circle", "right": None}
    )
    assert response.status_code == 409


async def test_deleting_a_sample_frees_its_positions(client: AsyncClient, raw_db: Any) -> None:
    [code] = await issue_frames(client, orcid(1))
    await set_plates(client, code, "8-circle", None)
    sample = await new_sample(client)
    await assign(client, code, "Left-A", sample)
    await raw_db.measurements.insert_one({"frame": code, "position": "Left-A"})
    version = (await frame(client, code))["version"]

    assert (await client.delete(f"{API}/samples/{sample}")).status_code == 204
    after = await frame(client, code)
    assert after["positions"] == []
    assert after["version"] == version + 1
    assert await raw_db.measurements.count_documents({"frame": code}) == 0
