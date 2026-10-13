"""Measurements, safety declaration and lock (requirements §6.4-6.6, §8.3)."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import AsyncClient
from pymongo import AsyncMongoClient

from tests.conftest import API, TEST_DB, TEST_MONGODB_URI, issue_frames, login_as, orcid

pytestmark = pytest.mark.db

XANES_FE = {"technique": "xanes", "element": "Fe", "edge": "K", "detection": "transmission"}


@pytest.fixture
async def raw_db() -> AsyncIterator[Any]:
    client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(TEST_MONGODB_URI)
    yield client[TEST_DB]
    await client.close()


async def version(client: AsyncClient, code: str) -> int:
    return (await client.get(f"{API}/frames/{code}")).json()["version"]


async def frame(client: AsyncClient, code: str) -> dict[str, Any]:
    return (await client.get(f"{API}/frames/{code}")).json()


async def configured_frame(client: AsyncClient, user_orcid: str = orcid(1)) -> tuple[str, str]:
    """An issued frame with an 8-Circle on the left and a sample at Left-A; returns (code, id)."""
    [code] = await issue_frames(client, user_orcid)
    await client.put(
        f"{API}/frames/{code}/plates", json={"version": 0, "left": "8-circle", "right": None}
    )
    sample = (await client.post(f"{API}/samples", json={"name": "Fe2O3"})).json()["id"]
    await client.put(
        f"{API}/frames/{code}/positions/Left-A", json={"version": 1, "sample_id": sample}
    )
    return code, sample


async def add(client: AsyncClient, code: str, position: str = "Left-A", **settings: Any) -> Any:
    body = {"version": await version(client, code), **XANES_FE, **settings}
    return await client.post(f"{API}/frames/{code}/positions/{position}/measurements", json=body)


async def declare(client: AsyncClient, code: str) -> Any:
    return await client.post(
        f"{API}/frames/{code}/declare-safe",
        json={"version": await version(client, code), "confirm": True},
    )


async def lock(client: AsyncClient, code: str, action: str = "lock") -> Any:
    return await client.post(
        f"{API}/frames/{code}/{action}", json={"version": await version(client, code)}
    )


# --- options ---------------------------------------------------------------------------------


async def test_options(client: AsyncClient) -> None:
    await login_as(client, orcid(1))
    options = (await client.get(f"{API}/measurement-options")).json()
    symbols = [e["symbol"] for e in options["elements"]]
    assert symbols[0] == "Ti" and symbols[-1] == "Bi"
    assert len(symbols) == 83 - 22 + 1
    assert next(e["z"] for e in options["elements"] if e["symbol"] == "Fe") == 26
    assert [e["value"] for e in options["edges"]] == ["K", "L1", "L2", "L3"]
    assert len(options["detections"]) == 3


# --- measurements ----------------------------------------------------------------------------


async def test_add_and_number_measurements_per_position(client: AsyncClient) -> None:
    code, _ = await configured_frame(client)
    first = await add(client, code)
    assert first.status_code == 201, first.text
    assert first.json()["number"] == 1
    assert first.json()["status"] == "pending"
    assert first.json()["beam"] == "unfocused"  # default
    second = await add(client, code, technique="exafs", detection="transmission_sdd")
    assert second.json()["number"] == 2

    listed = (await client.get(f"{API}/frames/{code}/measurements")).json()
    assert [(m["position"], m["number"]) for m in listed] == [("Left-A", 1), ("Left-A", 2)]


async def test_numbers_are_never_reused(client: AsyncClient) -> None:
    code, _ = await configured_frame(client)
    await add(client, code)
    second = (await add(client, code)).json()
    await client.delete(
        f"{API}/measurements/{second['id']}", params={"version": await version(client, code)}
    )
    assert (await add(client, code)).json()["number"] == 3


@pytest.mark.parametrize(
    "settings",
    [{"element": "Sc"}, {"element": "Po"}, {"edge": "M1"}, {"technique": "imaging"}],
)
async def test_invalid_settings(client: AsyncClient, settings: dict[str, Any]) -> None:
    code, _ = await configured_frame(client)
    assert (await add(client, code, **settings)).status_code == 422


async def test_position_needs_a_sample(client: AsyncClient) -> None:
    code, _ = await configured_frame(client)
    response = await add(client, code, position="Left-B")
    assert response.status_code == 422
    assert "Place a sample at Left-B first" in response.json()["detail"]


async def test_edit_measurement(client: AsyncClient) -> None:
    code, _ = await configured_frame(client)
    measurement = (await add(client, code)).json()
    body = {
        "version": await version(client, code),
        **XANES_FE,
        "element": "Cu",
        "beam": "focused",
    }
    response = await client.put(f"{API}/measurements/{measurement['id']}", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["element"] == "Cu"
    assert response.json()["number"] == 1


async def test_measurement_changes_check_the_frame_version(client: AsyncClient) -> None:
    code, _ = await configured_frame(client)
    stale = await version(client, code)
    await add(client, code)
    body = {"version": stale, **XANES_FE}
    response = await client.post(f"{API}/frames/{code}/positions/Left-A/measurements", json=body)
    assert response.status_code == 409


async def test_executed_measurement_cannot_be_deleted(client: AsyncClient, raw_db: Any) -> None:
    code, _ = await configured_frame(client)
    measurement = (await add(client, code)).json()
    await raw_db.measurements.update_one(
        {"frame": code, "number": 1}, {"$set": {"executed": True, "status": "done"}}
    )
    response = await client.delete(
        f"{API}/measurements/{measurement['id']}", params={"version": await version(client, code)}
    )
    assert response.status_code == 409


async def test_operator_edits_measurements_others_cannot(client: AsyncClient) -> None:
    code, _ = await configured_frame(client)
    await login_as(client, orcid(2))
    assert (await client.get(f"{API}/frames/{code}/measurements")).status_code == 404
    stranger = await client.post(
        f"{API}/frames/{code}/positions/Left-A/measurements", json={"version": 2, **XANES_FE}
    )
    assert stranger.status_code == 404

    await login_as(client, orcid(3), role="operator")
    response = await add(client, code)
    assert response.status_code == 201
    assert response.json()["changed_by"] == "Ada Test"


# --- safety declaration ----------------------------------------------------------------------


async def test_missing_items_listed_until_complete(client: AsyncClient) -> None:
    [code] = await issue_frames(client, orcid(1))
    assert (await frame(client, code))["missing"] == ["Mount at least one plate"]

    await client.put(
        f"{API}/frames/{code}/plates", json={"version": 0, "left": "8-circle", "right": "8-slot"}
    )
    assert (await frame(client, code))["missing"] == [
        "Place at least one sample on the left plate",
        "Place at least one sample on the right plate",
    ]

    sample = (await client.post(f"{API}/samples", json={"name": "Fe2O3"})).json()["id"]
    for position in ("Left-A", "Right-C"):
        await client.put(
            f"{API}/frames/{code}/positions/{position}",
            json={"version": await version(client, code), "sample_id": sample},
        )
    assert (await frame(client, code))["missing"] == [
        "Add a measurement to Left-A",
        "Add a measurement to Right-C",
    ]
    await add(client, code, "Left-A")
    await add(client, code, "Right-C")
    assert (await frame(client, code))["missing"] == []


async def test_declare_safe_freezes_frame_and_samples(client: AsyncClient) -> None:
    code, sample = await configured_frame(client)
    assert (await declare(client, code)).status_code == 422  # no measurement yet
    await add(client, code)

    response = await declare(client, code)
    assert response.status_code == 200, response.text
    assert response.json()["safety"]["by"] == "Ada Test"
    assert (await client.get(f"{API}/samples/{sample}")).json()["frozen"] is True
    plates = await client.put(
        f"{API}/frames/{code}/plates",
        json={"version": await version(client, code), "left": "8-slot", "right": None},
    )
    assert plates.status_code == 409
    # Measurements stay editable while unlocked.
    assert (await add(client, code)).status_code == 201
    # Declaring is final.
    assert (await declare(client, code)).status_code == 409


async def test_declaration_requires_confirmation(client: AsyncClient) -> None:
    code, _ = await configured_frame(client)
    await add(client, code)
    response = await client.post(
        f"{API}/frames/{code}/declare-safe",
        json={"version": await version(client, code), "confirm": False},
    )
    assert response.status_code == 422


async def test_only_owner_declares_safe(client: AsyncClient) -> None:
    code, _ = await configured_frame(client)
    await add(client, code)
    await login_as(client, orcid(2), role="admin")
    assert (await declare(client, code)).status_code == 403


async def test_declaring_lifts_the_hold(client: AsyncClient, raw_db: Any) -> None:
    code, _ = await configured_frame(client)
    await add(client, code)
    await raw_db.frames.update_one({"_id": code}, {"$set": {"state": "received_on_hold"}})

    response = await declare(client, code)
    assert response.json()["state"] == "received"
    assert response.json()["history"][-1]["state"] == "received"


# --- lock ------------------------------------------------------------------------------------


async def test_lock_requires_safety_and_freezes_measurements(client: AsyncClient) -> None:
    code, _ = await configured_frame(client)
    measurement = (await add(client, code)).json()
    assert (await lock(client, code)).status_code == 409  # not declared yet

    await declare(client, code)
    response = await lock(client, code)
    assert response.status_code == 200
    assert response.json()["locked"] is True
    assert (await add(client, code)).status_code == 409
    delete = await client.delete(
        f"{API}/measurements/{measurement['id']}", params={"version": await version(client, code)}
    )
    assert delete.status_code == 409

    assert (await lock(client, code, "unlock")).json()["locked"] is False
    assert (await add(client, code)).status_code == 201


async def test_operator_can_lock_and_unlock(client: AsyncClient) -> None:
    code, _ = await configured_frame(client)
    await add(client, code)
    await declare(client, code)
    await login_as(client, orcid(3), role="operator")
    assert (await lock(client, code)).json()["locked"] is True
    assert (await lock(client, code, "unlock")).json()["locked"] is False


@pytest.mark.parametrize("state", ["scheduled", "loaded"])
async def test_no_unlock_while_being_measured(client: AsyncClient, raw_db: Any, state: str) -> None:
    code, _ = await configured_frame(client)
    await add(client, code)
    await declare(client, code)
    await lock(client, code)
    await raw_db.frames.update_one({"_id": code}, {"$set": {"state": state}})
    assert (await lock(client, code, "unlock")).status_code == 409


async def test_relocking_needs_a_complete_frame(client: AsyncClient) -> None:
    code, _ = await configured_frame(client)
    measurement = (await add(client, code)).json()
    await declare(client, code)
    await client.delete(
        f"{API}/measurements/{measurement['id']}", params={"version": await version(client, code)}
    )
    response = await lock(client, code)
    assert response.status_code == 422
    assert "Add a measurement to Left-A" in response.json()["detail"]
