"""Samples, MSDS files, archiving and delete rules (requirements §8.2)."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from bson import ObjectId
from httpx import AsyncClient
from pymongo import AsyncMongoClient

from tests.conftest import API, TEST_DB, TEST_MONGODB_URI, login_as, orcid

pytestmark = pytest.mark.db

PDF = b"%PDF-1.4\n% test file\n%%EOF\n"


@pytest.fixture
async def raw_db() -> AsyncIterator[Any]:
    """Direct database access, for setting up frames before frame configuration exists (M3b)."""
    client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(TEST_MONGODB_URI)
    yield client[TEST_DB]
    await client.close()


async def create(client: AsyncClient, name: str = "Fe2O3", **body: Any) -> dict[str, Any]:
    response = await client.post(f"{API}/samples", json={"name": name, **body})
    assert response.status_code == 201, response.text
    return response.json()


async def place_on_frame(
    raw_db: Any,
    sample_id: str,
    *,
    barcode: str = "AAAA-AAAA",
    state: str = "shipped_to_user",
    safe: bool = False,
) -> None:
    await raw_db.frames.update_one(
        {"_id": barcode},
        {
            "$set": {
                "state": state,
                "safety_declared": {"at": "now"} if safe else None,
            },
            "$push": {"positions": {"position": "Left-A", "sample_id": ObjectId(sample_id)}},
        },
        upsert=True,
    )


async def freeze(raw_db: Any, sample_id: str) -> None:
    await raw_db.samples.update_one({"_id": ObjectId(sample_id)}, {"$set": {"frozen": True}})


# --- create, list, edit ----------------------------------------------------------------------


async def test_create_and_list_newest_first(client: AsyncClient) -> None:
    await login_as(client, orcid(1))
    first = await create(client, "  Fe2O3 ", description="hematite, ground")
    second = await create(client, "Fe2O3")  # names need not be unique

    assert first["name"] == "Fe2O3"
    assert first["description"] == "hematite, ground"
    assert first["msds"] is None
    assert first["deletable"] is True
    listed = (await client.get(f"{API}/samples")).json()
    assert [s["id"] for s in listed] == [second["id"], first["id"]]


async def test_samples_are_private(client: AsyncClient) -> None:
    await login_as(client, orcid(1))
    sample = await create(client)
    await login_as(client, orcid(2))
    assert (await client.get(f"{API}/samples")).json() == []
    assert (await client.get(f"{API}/samples/{sample['id']}")).status_code == 404
    assert (
        await client.put(f"{API}/samples/{sample['id']}", json={"name": "x"})
    ).status_code == 404

    await login_as(client, orcid(3), role="operator")  # operators may read
    assert (await client.get(f"{API}/samples/{sample['id']}")).status_code == 200


async def test_edit(client: AsyncClient) -> None:
    await login_as(client, orcid(1))
    sample = await create(client)
    response = await client.put(
        f"{API}/samples/{sample['id']}", json={"name": "Fe3O4", "description": "magnetite"}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Fe3O4"


@pytest.mark.parametrize("body", [{"name": ""}, {"name": "x" * 201}, {"name": "ok", "x": 1}])
async def test_invalid_input(client: AsyncClient, body: dict[str, Any]) -> None:
    await login_as(client, orcid(1))
    assert (await client.post(f"{API}/samples", json=body)).status_code == 422


async def test_frozen_sample_cannot_be_edited(client: AsyncClient, raw_db: Any) -> None:
    await login_as(client, orcid(1))
    sample = await create(client)
    await freeze(raw_db, sample["id"])

    url = f"{API}/samples/{sample['id']}"
    assert (await client.put(url, json={"name": "other"})).status_code == 409
    files = {"file": ("sds.pdf", PDF, "application/pdf")}
    assert (await client.put(f"{url}/msds", files=files)).status_code == 409
    # Archiving is still allowed.
    response = await client.put(f"{url}/archived", json={"archived": True})
    assert response.status_code == 200


# --- archive ---------------------------------------------------------------------------------


async def test_archive_hides_from_default_list(client: AsyncClient) -> None:
    await login_as(client, orcid(1))
    sample = await create(client)
    url = f"{API}/samples/{sample['id']}/archived"

    assert (await client.put(url, json={"archived": True})).json()["archived"] is True
    assert (await client.get(f"{API}/samples")).json() == []
    all_samples = (await client.get(f"{API}/samples", params={"include_archived": True})).json()
    assert [s["id"] for s in all_samples] == [sample["id"]]

    await client.put(url, json={"archived": False})
    assert len((await client.get(f"{API}/samples")).json()) == 1


# --- MSDS ------------------------------------------------------------------------------------


async def test_msds_upload_download_replace_delete(client: AsyncClient) -> None:
    await login_as(client, orcid(1))
    sample = await create(client)
    url = f"{API}/samples/{sample['id']}/msds"

    uploaded = await client.put(
        url, files={"file": ("C:\\docs\\Fe2O3 SDS.pdf", PDF, "application/pdf")}
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["msds"]["filename"] == "Fe2O3 SDS.pdf"
    assert uploaded.json()["msds"]["size"] == len(PDF)

    download = await client.get(url)
    assert download.status_code == 200
    assert download.content == PDF
    assert download.headers["content-type"] == "application/pdf"
    assert "Fe2O3%20SDS.pdf" in download.headers["content-disposition"]

    newer = PDF + b"% v2\n"
    await client.put(url, files={"file": ("v2.pdf", newer, "application/pdf")})
    assert (await client.get(url)).content == newer

    deleted = await client.delete(url)
    assert deleted.json()["msds"] is None
    assert (await client.get(url)).status_code == 404


async def test_msds_must_be_small_pdf(client: AsyncClient) -> None:
    await login_as(client, orcid(1))
    sample = await create(client)
    url = f"{API}/samples/{sample['id']}/msds"

    not_pdf = await client.put(url, files={"file": ("x.pdf", b"hello", "application/pdf")})
    assert not_pdf.status_code == 415
    too_big = PDF + b"0" * (1024 * 1024)
    big = await client.put(url, files={"file": ("big.pdf", too_big, "application/pdf")})
    assert big.status_code == 413


async def test_operator_can_download_msds(client: AsyncClient) -> None:
    await login_as(client, orcid(1))
    sample = await create(client)
    await client.put(
        f"{API}/samples/{sample['id']}/msds", files={"file": ("sds.pdf", PDF, "application/pdf")}
    )
    await login_as(client, orcid(2), role="operator")
    assert (await client.get(f"{API}/samples/{sample['id']}/msds")).content == PDF


# --- delete ----------------------------------------------------------------------------------


async def test_delete_unplaced_sample(client: AsyncClient) -> None:
    await login_as(client, orcid(1))
    sample = await create(client)
    await client.put(
        f"{API}/samples/{sample['id']}/msds", files={"file": ("sds.pdf", PDF, "application/pdf")}
    )
    assert (await client.delete(f"{API}/samples/{sample['id']}")).status_code == 204
    assert (await client.get(f"{API}/samples/{sample['id']}")).status_code == 404


async def test_delete_frees_positions_on_frames_being_assembled(
    client: AsyncClient, raw_db: Any
) -> None:
    await login_as(client, orcid(1))
    sample = await create(client)
    await place_on_frame(raw_db, sample["id"], safe=False)
    assert (await client.get(f"{API}/samples/{sample['id']}")).json()["frames"] == ["AAAA-AAAA"]

    assert (await client.delete(f"{API}/samples/{sample['id']}")).status_code == 204
    frame = await raw_db.frames.find_one({"_id": "AAAA-AAAA"})
    assert frame["positions"] == []


@pytest.mark.parametrize("state", ["shipped_to_user", "received", "internal_storage"])
async def test_no_delete_while_on_declared_frame(
    client: AsyncClient, raw_db: Any, state: str
) -> None:
    await login_as(client, orcid(1))
    sample = await create(client)
    await place_on_frame(raw_db, sample["id"], state=state, safe=True)

    assert (await client.get(f"{API}/samples/{sample['id']}")).json()["deletable"] is False
    response = await client.delete(f"{API}/samples/{sample['id']}")
    assert response.status_code == 409
    assert "AAAA-AAAA" in response.json()["detail"]


@pytest.mark.parametrize("state", ["returned", "void"])
async def test_delete_allowed_after_frame_is_back(
    client: AsyncClient, raw_db: Any, state: str
) -> None:
    await login_as(client, orcid(1))
    sample = await create(client)
    await place_on_frame(raw_db, sample["id"], state=state, safe=True)
    assert (await client.get(f"{API}/samples/{sample['id']}")).json()["deletable"] is True
    assert (await client.delete(f"{API}/samples/{sample['id']}")).status_code == 204
    # Returned frames keep their history.
    frame = await raw_db.frames.find_one({"_id": "AAAA-AAAA"})
    assert len(frame["positions"]) == 1
