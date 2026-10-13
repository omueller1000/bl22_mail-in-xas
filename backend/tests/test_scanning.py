"""Barcode scans, internal storage, release and warnings (requirements §6.3, §6.7, §9)."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import AsyncClient
from pymongo import AsyncMongoClient

from tests.conftest import API, TEST_DB, TEST_MONGODB_URI, issue_frames, login_as, orcid

pytestmark = pytest.mark.db

OPERATOR = orcid(50)


@pytest.fixture
async def raw_db() -> AsyncIterator[Any]:
    client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(TEST_MONGODB_URI)
    yield client[TEST_DB]
    await client.close()


async def frames_in(
    client: AsyncClient, raw_db: Any, state: str, count: int = 1, **fields: Any
) -> list[str]:
    """Frames of user orcid(1) put directly into `state` (and other fields); logs in an operator."""
    codes = await issue_frames(client, orcid(1), count)
    await raw_db.frames.update_many({"_id": {"$in": codes}}, {"$set": {"state": state, **fields}})
    await login_as(client, OPERATOR, role="operator")
    return codes


SAFE = {"safety_declared": {"at": "2026-10-13", "by": {"orcid": "x", "name": "Ada"}}}


async def scan(client: AsyncClient, step: str, action: str, codes: list[str]) -> list[dict]:
    response = await client.post(f"{API}/scans/{step}", json={"action": action, "barcodes": codes})
    assert response.status_code == 200, response.text
    return response.json()


async def state_of(client: AsyncClient, code: str) -> str:
    return (await client.get(f"{API}/frames/{code}")).json()["state"]


# --- receive ---------------------------------------------------------------------------------


async def test_check_receive_explains_each_frame(client: AsyncClient, raw_db: Any) -> None:
    [ready] = await frames_in(client, raw_db, "shipped_to_user", **SAFE, locked=True)
    [unlocked] = await frames_in(client, raw_db, "shipped_to_user", **SAFE)
    [unsafe] = await frames_in(client, raw_db, "shipped_to_user")
    [not_shipped] = await frames_in(client, raw_db, "issued")

    results = await scan(
        client, "check", "receive", [ready, unlocked, unsafe, not_shipped, "ZZZZ-ZZZZ"]
    )
    by_code = {r["barcode"]: r for r in results}
    assert by_code[ready]["target_state"] == "received" and by_code[ready]["warning"] is None
    assert by_code[unlocked]["target_state"] == "received"
    assert by_code[unlocked]["warning"] == "Not locked"
    assert by_code[unsafe]["target_state"] == "received_on_hold"
    assert by_code[not_shipped]["target_state"] is None
    assert "issued" in by_code[not_shipped]["problem"]
    assert by_code["ZZZZ-ZZZZ"]["problem"] == "Unknown barcode"
    assert by_code[ready]["owner"] == "Ada Test"
    # Checking changes nothing.
    assert await state_of(client, ready) == "shipped_to_user"


async def test_apply_moves_valid_frames_only(client: AsyncClient, raw_db: Any) -> None:
    [ready] = await frames_in(client, raw_db, "shipped_to_user", **SAFE, locked=True)
    [unsafe] = await frames_in(client, raw_db, "shipped_to_user")
    [not_shipped] = await frames_in(client, raw_db, "issued")
    version = (await client.get(f"{API}/frames/{ready}")).json()["version"]

    results = await scan(client, "apply", "receive", [ready, unsafe, not_shipped])
    assert {r["barcode"]: r["moved"] for r in results} == {
        ready: True,
        unsafe: True,
        not_shipped: False,
    }
    frame = (await client.get(f"{API}/frames/{ready}")).json()
    assert frame["state"] == "received"
    assert frame["history"][-1]["state"] == "received"
    assert frame["history"][-1]["by"] == "Ada Test"
    assert frame["version"] == version + 1
    assert await state_of(client, unsafe) == "received_on_hold"
    assert await state_of(client, not_shipped) == "issued"


async def test_users_cannot_scan(client: AsyncClient) -> None:
    await login_as(client, orcid(1))
    body = {"action": "receive", "barcodes": ["AAAA-AAAA"]}
    assert (await client.post(f"{API}/scans/check", json=body)).status_code == 403
    assert (await client.post(f"{API}/scans/apply", json=body)).status_code == 403


# --- other group actions ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("action", "start", "end"),
    [
        ("external_storage", "received", "external_storage"),
        ("return", "received_on_hold", "returned"),
        ("return", "external_storage", "returned"),
        ("void", "reserved", "void"),
        ("void", "scheduled", "void"),
    ],
)
async def test_group_actions(
    client: AsyncClient, raw_db: Any, action: str, start: str, end: str
) -> None:
    [code] = await frames_in(client, raw_db, start)
    [result] = await scan(client, "apply", action, [code])
    assert result["moved"] is True
    assert await state_of(client, code) == end


@pytest.mark.parametrize(
    ("action", "start"),
    [
        ("external_storage", "shipped_to_user"),
        ("return", "issued"),
        ("void", "returned"),
        ("void", "void"),
    ],
)
async def test_group_actions_refuse_wrong_states(
    client: AsyncClient, raw_db: Any, action: str, start: str
) -> None:
    [code] = await frames_in(client, raw_db, start)
    [result] = await scan(client, "apply", action, [code])
    assert result["moved"] is False
    assert result["problem"]


# --- internal storage ------------------------------------------------------------------------


async def store(client: AsyncClient, code: str, container: int, slot: int) -> Any:
    return await client.post(
        f"{API}/frames/{code}/internal-storage", json={"container": container, "slot": slot}
    )


async def test_move_to_internal_storage(client: AsyncClient, raw_db: Any) -> None:
    [code] = await frames_in(client, raw_db, "received")
    response = await store(client, code, 1, 7)
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "internal_storage"
    assert response.json()["storage"] == {"container": 1, "slot": 7}


async def test_slot_must_be_free(client: AsyncClient, raw_db: Any) -> None:
    first, second = await frames_in(client, raw_db, "external_storage", count=2)
    await store(client, first, 0, 0)
    response = await store(client, second, 0, 0)
    assert response.status_code == 409
    assert first in response.json()["detail"]
    assert await state_of(client, second) == "external_storage"


@pytest.mark.parametrize("slot", [{"container": 3, "slot": 0}, {"container": 0, "slot": 11}])
async def test_slot_range(client: AsyncClient, raw_db: Any, slot: dict[str, int]) -> None:
    [code] = await frames_in(client, raw_db, "received")
    response = await client.post(f"{API}/frames/{code}/internal-storage", json=slot)
    assert response.status_code == 422


async def test_internal_storage_only_from_received_or_external(
    client: AsyncClient, raw_db: Any
) -> None:
    [code] = await frames_in(client, raw_db, "shipped_to_user")
    assert (await store(client, code, 0, 1)).status_code == 409


@pytest.mark.parametrize("action", ["external_storage", "return", "void"])
async def test_leaving_internal_storage_frees_the_slot(
    client: AsyncClient, raw_db: Any, action: str
) -> None:
    first, second = await frames_in(client, raw_db, "received", count=2)
    await store(client, first, 2, 10)
    await scan(client, "apply", action, [first])
    assert (await client.get(f"{API}/frames/{first}")).json()["storage"] is None
    assert (await store(client, second, 2, 10)).status_code == 200


async def test_release_returns_frame_to_its_slot(client: AsyncClient, raw_db: Any) -> None:
    [code] = await frames_in(client, raw_db, "received")
    await store(client, code, 1, 3)
    await raw_db.frames.update_one({"_id": code}, {"$set": {"state": "loaded"}})

    response = await client.post(f"{API}/frames/{code}/release")
    assert response.status_code == 200
    assert response.json()["state"] == "internal_storage"
    assert response.json()["storage"] == {"container": 1, "slot": 3}
    # Only scheduled or loaded frames can be released.
    assert (await client.post(f"{API}/frames/{code}/release")).status_code == 409


async def test_storage_overview(client: AsyncClient, raw_db: Any) -> None:
    a, b = await frames_in(client, raw_db, "received", count=2)
    await store(client, a, 1, 0)
    await store(client, b, 0, 5)
    await raw_db.frames.update_one({"_id": a}, {"$set": {"state": "scheduled"}})
    await raw_db.measurements.insert_many(
        [
            {"frame": a, "position": "Left-A", "number": 1, "status": "pending"},
            {"frame": a, "position": "Left-A", "number": 2, "status": "done"},
        ]
    )

    rows = (await client.get(f"{API}/storage/internal")).json()
    assert [(r["barcode"], r["container"], r["slot"]) for r in rows] == [(b, 0, 5), (a, 1, 0)]
    assert rows[1]["state"] == "scheduled"  # keeps its slot while scheduled
    assert rows[1]["pending_measurements"] == 1
    assert rows[1]["owner"]["name"] == "Ada Test"


async def test_storage_overview_requires_operator(client: AsyncClient) -> None:
    await login_as(client, orcid(1))
    assert (await client.get(f"{API}/storage/internal")).status_code == 403


# --- warnings --------------------------------------------------------------------------------


async def test_warnings(client: AsyncClient, raw_db: Any) -> None:
    [on_hold] = await frames_in(client, raw_db, "received_on_hold")
    [unlocked] = await frames_in(client, raw_db, "internal_storage", **SAFE)
    await frames_in(client, raw_db, "received", **SAFE, locked=True)  # fine
    await frames_in(client, raw_db, "shipped_to_user")  # not at the facility yet

    everyone = (await client.get(f"{API}/warnings", params={"all_users": True})).json()
    assert {(w["barcode"], w["kind"]) for w in everyone} == {
        (on_hold, "on_hold"),
        (unlocked, "not_locked"),
    }

    await login_as(client, orcid(1))
    own = (await client.get(f"{API}/warnings")).json()
    assert {w["barcode"] for w in own} == {on_hold, unlocked}
    assert (await client.get(f"{API}/warnings", params={"all_users": True})).status_code == 403

    await login_as(client, orcid(2))
    assert (await client.get(f"{API}/warnings")).json() == []
