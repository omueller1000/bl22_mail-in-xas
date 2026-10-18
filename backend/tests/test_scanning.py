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


async def test_lookup_explains_receiving_each_frame(client: AsyncClient, raw_db: Any) -> None:
    [ready] = await frames_in(client, raw_db, "shipped_to_user", **SAFE, locked=True)
    [unlocked] = await frames_in(client, raw_db, "shipped_to_user", **SAFE)
    [unsafe] = await frames_in(client, raw_db, "shipped_to_user")
    [not_shipped] = await frames_in(client, raw_db, "issued")

    codes = [ready, unlocked, unsafe, not_shipped, "ZZZZ-ZZZZ"]
    response = await client.post(f"{API}/scans/lookup", json={"barcodes": codes})
    receive = {
        f["barcode"]: next(a for a in f["actions"] if a["action"] == "receive")
        for f in response.json()
    }
    assert receive[ready]["target_state"] == "received" and receive[ready]["warning"] is None
    assert receive[unlocked]["target_state"] == "received"
    assert receive[unlocked]["warning"] == "Not locked"
    assert receive[unsafe]["target_state"] == "received_on_hold"
    assert receive[not_shipped]["target_state"] is None
    assert "issued" in receive[not_shipped]["problem"]
    assert receive["ZZZZ-ZZZZ"]["problem"] == "Unknown barcode"
    owners = {f["barcode"]: f["owner"] for f in response.json()}
    assert owners[ready] == "Ada Test"
    notes = {f["barcode"]: f["note"] for f in response.json()}
    assert notes[ready] == "" and notes["ZZZZ-ZZZZ"] == ""
    # Checking changes nothing.
    assert await state_of(client, ready) == "shipped_to_user"


async def test_lookup_shows_the_frame_note(client: AsyncClient, raw_db: Any) -> None:
    [code] = await frames_in(client, raw_db, "shipped_to_user")
    await raw_db.frames.update_one({"_id": code}, {"$set": {"note": "Box 3, iron oxides"}})
    [frame] = (await client.post(f"{API}/scans/lookup", json={"barcodes": [code]})).json()
    assert frame["note"] == "Box 3, iron oxides"


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


async def test_lookup_reports_every_action(client: AsyncClient, raw_db: Any) -> None:
    [unsafe] = await frames_in(client, raw_db, "shipped_to_user")
    [stored] = await frames_in(client, raw_db, "internal_storage", **SAFE, locked=True)

    response = await client.post(f"{API}/scans/lookup", json={"barcodes": [unsafe, stored]})
    assert response.status_code == 200
    by_code = {f["barcode"]: f for f in response.json()}

    actions = {a["action"]: a for a in by_code[unsafe]["actions"]}
    assert list(actions) == ["receive", "external_storage", "return", "void"]
    assert actions["receive"]["target_state"] == "received_on_hold"
    assert actions["receive"]["warning"] == "Not declared safe: put on hold"
    assert actions["return"]["target_state"] is None
    assert actions["void"]["target_state"] == "void"

    stored_actions = {a["action"]: a["target_state"] for a in by_code[stored]["actions"]}
    assert stored_actions == {
        "receive": None,
        "external_storage": "external_storage",
        "return": "returning_to_user",
        "void": "void",
    }
    assert by_code[stored]["safe"] is True and by_code[stored]["locked"] is True
    assert await state_of(client, unsafe) == "shipped_to_user"  # nothing changed


async def test_users_cannot_scan(client: AsyncClient) -> None:
    await login_as(client, orcid(1))
    lookup = {"barcodes": ["AAAA-AAAA"]}
    assert (await client.post(f"{API}/scans/lookup", json=lookup)).status_code == 403
    body = {"action": "receive", "barcodes": ["AAAA-AAAA"]}
    assert (await client.post(f"{API}/scans/apply", json=body)).status_code == 403


# --- other group actions ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("action", "start", "end"),
    [
        ("external_storage", "received", "external_storage"),
        ("return", "received_on_hold", "returning_to_user"),
        ("return", "external_storage", "returning_to_user"),
        # Undo "mark as returning to user".
        ("external_storage", "returning_to_user", "external_storage"),
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
        ("return", "returning_to_user"),
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
    storage = response.json()["storage"]
    assert (storage["container"], storage["slot"]) == (1, 7)
    assert storage["since"] is not None


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

    stored_since = (await client.get(f"{API}/frames/{code}")).json()["storage"]["since"]
    response = await client.post(f"{API}/frames/{code}/release")
    assert response.status_code == 200
    assert response.json()["state"] == "internal_storage"
    storage = response.json()["storage"]
    assert (storage["container"], storage["slot"]) == (1, 3)
    assert storage["since"] == stored_since  # releasing does not restart the clock
    # Only scheduled or loaded frames can be released.
    assert (await client.post(f"{API}/frames/{code}/release")).status_code == 409


async def test_storage_overview(client: AsyncClient, raw_db: Any) -> None:
    a, b = await frames_in(client, raw_db, "received", count=2)
    await store(client, a, 1, 0)
    await store(client, b, 0, 5)
    await raw_db.frames.update_one({"_id": a}, {"$set": {"state": "scheduled"}})
    measured = [
        ("Left-B", 2, "Ta", "L1", "error", "Edge step too small"),
        ("Left-A", 1, "Ta", "L3", "done", None),
        ("Left-A", 2, "Cu", "K", "error", None),
        ("Left-B", 1, "Cu", "K", "pending", None),
    ]
    await raw_db.measurements.insert_many(
        [
            {
                "frame": a,
                "position": position,
                "number": number,
                "technique": "xanes",
                "element": element,
                "edge": edge,
                "status": status,
                "error_message": message,
            }
            for position, number, element, edge, status, message in measured
        ]
    )

    rows = (await client.get(f"{API}/storage/internal")).json()
    assert [(r["barcode"], r["container"], r["slot"]) for r in rows] == [(b, 0, 5), (a, 1, 0)]
    assert rows[1]["state"] == "scheduled"  # keeps its slot while scheduled
    assert rows[0]["since"] is not None
    # Each edge once, by atomic number and then K, L1, L2, L3.
    assert rows[1]["edges"] == ["Cu K", "Ta L1", "Ta L3"]
    assert rows[0]["edges"] == []
    assert rows[1]["owner"]["name"] == "Ada Test"
    assert rows[1]["measurements"] == {"pending": 1, "done": 1, "error": 2}
    assert [(f["position"], f["number"], f["message"]) for f in rows[1]["failed"]] == [
        ("Left-A", 2, None),
        ("Left-B", 2, "Edge step too small"),
    ]
    assert rows[1]["failed"][1]["element"] == "Ta"
    assert rows[0]["measurements"] == {"pending": 0, "done": 0, "error": 0}
    assert rows[0]["failed"] == []


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
