"""Database access for measured data.

sweeps:    {_id, measurement_id, frame, position, number, sample_id, owner_id,
            batch_no, sweep_no, measured: {technique, element, edge, detection, beam},
            metadata, channels: [{name, unit, values}], uploaded_at, uploaded_by}
processed: {_id, sweep_id, measurement_id, frame, batch_no, sweep_no, metadata,
            mu: {x, y}, chi: {x, y} | None, uploaded_at, uploaded_by}

The backend copies frame, position, sample and owner from the measurement when a sweep is
uploaded (they are never taken from the uploader), and snapshots the measurement's settings,
so the data keeps saying what was measured even if the measurement is edited later.
Raw sweeps are never changed or deleted; processed results are replaced on re-upload.
"""

from bson import ObjectId
from pymongo import ASCENDING

from app.db import Database

SWEEPS = "sweeps"
PROCESSED = "processed"


async def ensure_indexes(db: Database) -> None:
    await db[SWEEPS].create_index(
        [("measurement_id", ASCENDING), ("batch_no", ASCENDING), ("sweep_no", ASCENDING)],
        unique=True,
    )
    # A sweep number exists only once per measurement, across batches.
    await db[SWEEPS].create_index(
        [("measurement_id", ASCENDING), ("sweep_no", ASCENDING)], unique=True
    )
    await db[SWEEPS].create_index([("frame", ASCENDING)])
    await db[SWEEPS].create_index([("sample_id", ASCENDING)])
    await db[SWEEPS].create_index([("owner_id", ASCENDING)])
    await db[PROCESSED].create_index([("sweep_id", ASCENDING)], unique=True)
    await db[PROCESSED].create_index([("measurement_id", ASCENDING)])


async def last_numbers(
    db: Database, measurement_ids: list[ObjectId]
) -> dict[ObjectId, tuple[int, int]]:
    """{measurement_id: (last batch_no, last sweep_no)} for measurements that have data."""
    pipeline = [
        {"$match": {"measurement_id": {"$in": measurement_ids}}},
        {
            "$group": {
                "_id": "$measurement_id",
                "batch": {"$max": "$batch_no"},
                "sweep": {"$max": "$sweep_no"},
            }
        },
    ]
    return {
        row["_id"]: (row["batch"], row["sweep"])
        async for row in await db[SWEEPS].aggregate(pipeline)
    }


async def frames_having_data(db: Database, barcodes: list[str]) -> set[str]:
    """The given frames that have at least one sweep."""
    return set(await db[SWEEPS].distinct("frame", {"frame": {"$in": barcodes}}))


async def frames_with_data(db: Database, sample_ids: list[ObjectId]) -> dict[ObjectId, list[str]]:
    """{sample_id: sorted barcodes of the frames with data of that sample}."""
    pipeline = [
        {"$match": {"sample_id": {"$in": sample_ids}}},
        {"$group": {"_id": "$sample_id", "frames": {"$addToSet": "$frame"}}},
    ]
    return {row["_id"]: sorted(row["frames"]) async for row in await db[SWEEPS].aggregate(pipeline)}


async def sample_has_data(db: Database, sample_id: ObjectId) -> bool:
    return await db[SWEEPS].count_documents({"sample_id": sample_id}, limit=1) > 0
