"""Service clients, API keys and the control-software endpoints (requirements §3.4, §10.2)."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import AsyncClient
from pymongo import AsyncMongoClient

from tests.conftest import API, TEST_DB, TEST_MONGODB_URI, issue_frames, login_as, orcid

pytestmark = pytest.mark.db

ADMIN = orcid(70)
CU_K = {"technique": "exafs", "element": "Cu", "edge": "K", "detection": "transmission"}


@pytest.fixture
async def raw_db() -> AsyncIterator[Any]:
    client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(TEST_MONGODB_URI)
    yield client[TEST_DB]
    await client.close()


async def new_key(client: AsyncClient, name: str = "BL22 control software") -> tuple[str, str]:
    """As an admin, create a service client and a key; returns (client id, key)."""
    await login_as(client, ADMIN, role="admin")
    created = await client.post(f"{API}/service-clients", json={"name": name})
    assert created.status_code == 201, created.text
    client_id = created.json()["id"]
    key = await client.post(f"{API}/service-clients/{client_id}/keys")
    assert key.status_code == 201, key.text
    return client_id, key.json()["key"]


@pytest.fixture
async def instrument(client: AsyncClient) -> AsyncIterator[AsyncClient]:
    """A client authenticated with an API key (no session cookie)."""
    _, key = await new_key(client)
    async with AsyncClient(
        transport=client._transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {key}"},
    ) as c:
        yield c


async def ready_frame(
    client: AsyncClient, raw_db: Any, *, locked: bool = True, slot: int = 4
) -> dict[str, str]:
    """A declared, (locked) frame in internal storage with a pending Cu K measurement."""
    [code] = await issue_frames(client, orcid(1))
    await client.put(
        f"{API}/frames/{code}/plates", json={"version": 0, "left": "8-circle", "right": None}
    )
    sample = (await client.post(f"{API}/samples", json={"name": "CuO"})).json()["id"]
    await client.put(
        f"{API}/frames/{code}/positions/Left-A", json={"version": 1, "sample_id": sample}
    )
    measurement = await client.post(
        f"{API}/frames/{code}/positions/Left-A/measurements", json={"version": 2, **CU_K}
    )
    await client.post(f"{API}/frames/{code}/declare-safe", json={"version": 3, "confirm": True})
    if locked:
        await client.post(f"{API}/frames/{code}/lock", json={"version": 4})
    await raw_db.frames.update_one(
        {"_id": code},
        {"$set": {"state": "internal_storage", "storage": {"container": 0, "slot": slot}}},
    )
    return {"code": code, "sample": sample, "measurement": measurement.json()["id"]}


def sweep(batch: int = 1, number: int = 1, points: int = 5, **extra: Any) -> dict[str, Any]:
    energy = [8900.0 + i for i in range(points)]
    return {
        "batch_no": batch,
        "sweep_no": number,
        "metadata": {"lattice_spacing": 1.920156},
        "channels": [
            {"name": "energy", "unit": "eV", "values": energy},
            {"name": "i0", "unit": "counts", "values": [1.0] * points},
            {"name": "i1", "unit": "counts", "values": [0.5] * points},
        ],
        **extra,
    }


# --- service clients and keys ----------------------------------------------------------------


async def test_admin_manages_clients_and_keys(client: AsyncClient) -> None:
    client_id, key = await new_key(client)
    assert key.startswith("htxas_") and len(key) > 40

    listed = (await client.get(f"{API}/service-clients")).json()
    [entry] = listed
    assert entry["name"] == "BL22 control software"
    [shown] = entry["keys"]
    assert key.startswith(shown["prefix"]) and len(shown["prefix"]) < 20  # never the full key
    assert shown["revoked_at"] is None

    duplicate = await client.post(f"{API}/service-clients", json={"name": "BL22 control software"})
    assert duplicate.status_code == 409

    revoked = await client.delete(f"{API}/service-clients/{client_id}/keys/{shown['id']}")
    assert revoked.json()["revoked_at"] is not None


async def test_only_admins_manage_clients(client: AsyncClient) -> None:
    await login_as(client, orcid(2), role="operator")
    assert (await client.get(f"{API}/service-clients")).status_code == 403
    assert (await client.post(f"{API}/service-clients", json={"name": "x"})).status_code == 403


async def test_key_authentication(client: AsyncClient, instrument: AsyncClient) -> None:
    assert (await instrument.get(f"{API}/instrument/queue")).status_code == 200
    # Records when the key was last used.
    [entry] = (await client.get(f"{API}/service-clients")).json()
    assert entry["keys"][0]["last_used_at"] is not None

    for header in ({}, {"Authorization": "Bearer htxas_wrong"}, {"Authorization": "Basic x"}):
        async with AsyncClient(
            transport=client._transport, base_url="http://test", headers=header
        ) as anonymous:
            assert (await anonymous.get(f"{API}/instrument/queue")).status_code == 401

    # A logged-in user (session cookie) is not an instrument ...
    assert (await client.get(f"{API}/instrument/queue")).status_code == 401
    # ... and a key does not log anyone into the portal.
    assert (await instrument.get(f"{API}/users")).status_code == 401


async def test_revoked_key_stops_working(client: AsyncClient) -> None:
    client_id, key = await new_key(client)
    headers = {"Authorization": f"Bearer {key}"}
    async with AsyncClient(
        transport=client._transport, base_url="http://test", headers=headers
    ) as c:
        assert (await c.get(f"{API}/instrument/queue")).status_code == 200
        key_id = (await client.get(f"{API}/service-clients")).json()[0]["keys"][0]["id"]
        await client.delete(f"{API}/service-clients/{client_id}/keys/{key_id}")
        assert (await c.get(f"{API}/instrument/queue")).status_code == 401


# --- reading ---------------------------------------------------------------------------------


async def test_queue_lists_locked_frames_with_pending_work(
    client: AsyncClient, raw_db: Any, instrument: AsyncClient
) -> None:
    ready = await ready_frame(client, raw_db)
    await ready_frame(client, raw_db, locked=False, slot=5)  # not locked: not in the queue

    [entry] = (await instrument.get(f"{API}/instrument/queue")).json()
    assert entry["barcode"] == ready["code"]
    assert entry["storage"]["container"] == 0
    [position] = entry["positions"]
    assert position["position"] == "Left-A" and position["sample_name"] == "CuO"
    [m] = position["measurements"]
    assert (m["element"], m["edge"], m["status"]) == ("Cu", "K", "pending")
    assert m["last_batch"] is None and m["last_sweep"] is None

    # Done measurements leave the queue.
    await instrument.put(f"{API}/instrument/measurements/{m['id']}/status", json={"status": "done"})
    assert (await instrument.get(f"{API}/instrument/queue")).json() == []


async def test_frame_and_storage(client: AsyncClient, raw_db: Any, instrument: AsyncClient) -> None:
    ready = await ready_frame(client, raw_db)
    frame = (await instrument.get(f"{API}/instrument/frames/{ready['code'].lower()}")).json()
    assert frame["barcode"] == ready["code"] and frame["locked"] and frame["safe"]
    storage = (await instrument.get(f"{API}/instrument/storage/internal")).json()
    assert storage == [
        {
            "barcode": ready["code"],
            "container": 0,
            "slot": 4,
            "state": "internal_storage",
            "locked": True,
        }
    ]
    assert (await instrument.get(f"{API}/instrument/frames/ZZZZ-ZZZZ")).status_code == 404


# --- frame states ----------------------------------------------------------------------------


async def set_state(instrument: AsyncClient, code: str, state: str) -> Any:
    return await instrument.post(f"{API}/instrument/frames/{code}/state", json={"state": state})


async def test_schedule_load_and_return(
    client: AsyncClient, raw_db: Any, instrument: AsyncClient
) -> None:
    ready = await ready_frame(client, raw_db)
    code = ready["code"]
    assert (await set_state(instrument, code, "loaded")).status_code == 409  # not scheduled yet
    assert (await set_state(instrument, code, "scheduled")).json()["state"] == "scheduled"
    assert (await set_state(instrument, code, "loaded")).json()["state"] == "loaded"
    back = await set_state(instrument, code, "internal_storage")
    assert back.json()["state"] == "internal_storage"
    assert back.json()["storage"]["slot"] == 4  # kept its slot

    await login_as(client, orcid(1))
    history = (await client.get(f"{API}/frames/{code}")).json()["history"]
    assert [h["by"] for h in history[-3:]] == ["BL22 control software"] * 3


async def test_only_locked_frames_are_scheduled(
    client: AsyncClient, raw_db: Any, instrument: AsyncClient
) -> None:
    ready = await ready_frame(client, raw_db, locked=False)
    response = await set_state(instrument, ready["code"], "scheduled")
    assert response.status_code == 409
    assert "locked" in response.json()["detail"]


# --- measurement status ----------------------------------------------------------------------


async def test_status_changes_and_remeasure(
    client: AsyncClient, raw_db: Any, instrument: AsyncClient
) -> None:
    ready = await ready_frame(client, raw_db)
    url = f"{API}/instrument/measurements/{ready['measurement']}/status"

    error = await instrument.put(url, json={"status": "error", "error_message": "beam lost"})
    assert error.json()["status"] == "error" and error.json()["error_message"] == "beam lost"
    again = await instrument.put(url, json={"status": "pending"})  # re-measure
    assert again.json()["status"] == "pending" and again.json()["error_message"] is None

    measurement = await raw_db.measurements.find_one({"frame": ready["code"]})
    assert measurement["executed"] is True  # has run once; can no longer be deleted
    assert measurement["changed_by"]["name"] == "BL22 control software"


# --- data ------------------------------------------------------------------------------------


async def test_upload_sweeps(client: AsyncClient, raw_db: Any, instrument: AsyncClient) -> None:
    ready = await ready_frame(client, raw_db)
    url = f"{API}/instrument/measurements/{ready['measurement']}/sweeps"

    first = await instrument.post(url, json=sweep(1, 1))
    assert first.status_code == 201, first.text
    assert first.json()["points"] == 5
    assert first.json()["channels"] == ["energy", "i0", "i1"]
    assert first.json()["frame"] == ready["code"]
    await instrument.post(url, json=sweep(2, 2))  # a re-run: next batch, sweeps continue

    # Duplicates are refused: same sweep number, also in another batch.
    assert (await instrument.post(url, json=sweep(1, 1))).status_code == 409
    assert (await instrument.post(url, json=sweep(3, 2))).status_code == 409

    frame = (await instrument.get(f"{API}/instrument/frames/{ready['code']}")).json()
    m = frame["positions"][0]["measurements"][0]
    assert (m["last_batch"], m["last_sweep"]) == (2, 2)


async def test_sweep_references_come_from_the_database(
    client: AsyncClient, raw_db: Any, instrument: AsyncClient
) -> None:
    ready = await ready_frame(client, raw_db)
    await instrument.post(
        f"{API}/instrument/measurements/{ready['measurement']}/sweeps", json=sweep()
    )

    doc = await raw_db.sweeps.find_one({"frame": ready["code"]})
    owner = await raw_db.users.find_one({"orcid": orcid(1)})
    assert doc["owner_id"] == owner["_id"]
    assert str(doc["sample_id"]) == ready["sample"]
    assert (doc["position"], doc["number"]) == ("Left-A", 1)
    assert doc["measured"] == {**CU_K, "beam": "unfocused"}
    assert doc["uploaded_by"]["name"] == "BL22 control software"


@pytest.mark.parametrize(
    "bad",
    [
        sweep(batch=1000),
        sweep(number=0),
        {**sweep(), "channels": [{"name": "i0", "values": [1.0]}]},  # no energy channel
        {
            **sweep(),
            "channels": [
                {"name": "energy", "values": [1.0, 2.0]},
                {"name": "i0", "values": [1.0]},  # different length
            ],
        },
        {
            **sweep(),
            "channels": [{"name": "energy", "values": [1.0]}, {"name": "energy", "values": [2.0]}],
        },
    ],
    ids=["batch 1000", "sweep 0", "no energy", "lengths differ", "duplicate names"],
)
async def test_invalid_sweeps(
    client: AsyncClient, raw_db: Any, instrument: AsyncClient, bad: dict[str, Any]
) -> None:
    ready = await ready_frame(client, raw_db)
    url = f"{API}/instrument/measurements/{ready['measurement']}/sweeps"
    assert (await instrument.post(url, json=bad)).status_code == 422


async def test_data_protects_sample_and_measurement(
    client: AsyncClient, raw_db: Any, instrument: AsyncClient
) -> None:
    ready = await ready_frame(client, raw_db)
    await instrument.post(
        f"{API}/instrument/measurements/{ready['measurement']}/sweeps", json=sweep()
    )

    await login_as(client, orcid(1))
    sample = (await client.get(f"{API}/samples/{ready['sample']}")).json()
    assert sample["deletable"] is False
    measurement = await raw_db.measurements.find_one({"frame": ready["code"]})
    assert measurement["executed"] is True


async def test_processed_data_replaces_previous(
    client: AsyncClient, raw_db: Any, instrument: AsyncClient
) -> None:
    ready = await ready_frame(client, raw_db)
    base = f"{API}/instrument/measurements/{ready['measurement']}/sweeps"
    processed = {
        "metadata": {"e0": 8979.0},
        "mu": {"x": [8900.0, 8901.0], "y": [0.1, 0.2]},
        "chi": {"x": [2.0, 2.1], "y": [0.01, 0.02]},
    }
    assert (await instrument.put(f"{base}/1/1/processed", json=processed)).status_code == 404

    await instrument.post(base, json=sweep())
    first = await instrument.put(f"{base}/1/1/processed", json=processed)
    assert first.status_code == 200 and first.json()["has_processed"] is True
    replaced = {**processed, "metadata": {"e0": 8980.0}}
    await instrument.put(f"{base}/1/1/processed", json=replaced)

    docs = await raw_db.processed.find({"frame": ready["code"]}).to_list()
    assert len(docs) == 1 and docs[0]["metadata"]["e0"] == 8980.0

    bad = {**processed, "mu": {"x": [1.0, 2.0], "y": [1.0]}}
    assert (await instrument.put(f"{base}/1/1/processed", json=bad)).status_code == 422


async def test_oversized_requests_are_refused(client: AsyncClient, instrument: AsyncClient) -> None:
    response = await instrument.post(
        f"{API}/instrument/measurements/000000000000000000000000/sweeps",
        content=b"x" * (12 * 1024 * 1024 + 1),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
