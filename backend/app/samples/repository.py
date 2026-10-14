"""Database access for samples and their MSDS files.

Sample document: {_id, owner_id, name, description, msds: {file_id, filename, size, uploaded_at}
                  | None, archived, frozen, created_at, updated_at}
Placements live on the frames: frame.positions = [{position: "Left-A", sample_id}, ...].
"""

from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from gridfs import AsyncGridFSBucket
from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession

from app.data import repository as data
from app.db import Database
from app.frames import repository as frames
from app.frames.states import TERMINAL
from app.samples.models import Msds, Sample, SampleInput

COLLECTION = "samples"
MSDS_BUCKET = "msds"


async def ensure_indexes(db: Database) -> None:
    await db[COLLECTION].create_index([("owner_id", ASCENDING), ("created_at", DESCENDING)])
    await db[frames.COLLECTION].create_index([("positions.sample_id", ASCENDING)])


def msds_bucket(db: Database) -> AsyncGridFSBucket:
    return AsyncGridFSBucket(db, bucket_name=MSDS_BUCKET)


async def create(db: Database, owner_id: ObjectId, data: SampleInput) -> dict[str, Any]:
    now = datetime.now(UTC)
    doc = {
        "owner_id": owner_id,
        "name": data.name,
        "description": data.description,
        "msds": None,
        "archived": False,
        "frozen": False,
        "created_at": now,
        "updated_at": now,
    }
    doc["_id"] = (await db[COLLECTION].insert_one(doc)).inserted_id
    return doc


async def get(db: Database, sample_id: ObjectId) -> dict[str, Any] | None:
    return await db[COLLECTION].find_one({"_id": sample_id})


async def list_for_owner(
    db: Database, owner_id: ObjectId, include_archived: bool
) -> list[dict[str, Any]]:
    query: dict[str, Any] = {"owner_id": owner_id}
    if not include_archived:
        query["archived"] = False
    # Newest first, as in the sample picker (§8.1).
    return await db[COLLECTION].find(query).sort("created_at", DESCENDING).to_list()


async def update(db: Database, sample_id: ObjectId, changes: dict[str, Any]) -> dict | None:
    return await db[COLLECTION].find_one_and_update(
        {"_id": sample_id},
        {"$set": {**changes, "updated_at": datetime.now(UTC)}},
        return_document=ReturnDocument.AFTER,
    )


async def frames_with(
    db: Database, sample_ids: list[ObjectId], session: AsyncClientSession | None = None
) -> list[dict[str, Any]]:
    return (
        await db[frames.COLLECTION]
        .find(
            {"positions.sample_id": {"$in": sample_ids}},
            {"state": 1, "safety_declared": 1, "positions": 1},
            session=session,
        )
        .to_list()
    )


def blocks_deletion(frame: dict[str, Any]) -> bool:
    """A frame that is declared safe and not yet back (returned/void) holds on to its samples.

    The portal has no "in transit to the facility" state, and a frame cannot be shipped back
    without the safety declaration, so this covers frames in transit and at the facility (§8.2).
    """
    return bool(frame.get("safety_declared")) and frame["state"] not in TERMINAL


async def has_data(db: Database, sample_id: ObjectId) -> bool:
    return await data.sample_has_data(db, sample_id)


def to_model(doc: dict[str, Any], placed_on: list[dict[str, Any]], with_data: bool) -> Sample:
    msds = doc.get("msds")
    return Sample(
        id=str(doc["_id"]),
        name=doc["name"],
        description=doc["description"],
        msds=Msds(**{k: msds[k] for k in ("filename", "size", "uploaded_at")}) if msds else None,
        archived=doc["archived"],
        frozen=doc["frozen"],
        deletable=not with_data and not any(blocks_deletion(f) for f in placed_on),
        frames=sorted(f["_id"] for f in placed_on),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


async def to_models(db: Database, docs: list[dict[str, Any]]) -> list[Sample]:
    placed = await frames_with(db, [d["_id"] for d in docs])
    result = []
    for doc in docs:
        on = [f for f in placed if any(p["sample_id"] == doc["_id"] for p in f["positions"])]
        result.append(to_model(doc, on, await has_data(db, doc["_id"])))
    return result
