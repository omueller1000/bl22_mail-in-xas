"""Database access for measurements (one document per measurement, attached to a position).

Document: {_id, frame, position, number, technique, element, edge, detection, beam, status,
           error_message, executed, created_at, updated_at, changed_by: {orcid, name}}
The per-position number counter lives on the frame (measurement_counters.<position>), so
numbers are never reused, even after a measurement is deleted.
"""

from typing import Any

from bson import ObjectId
from pymongo import ASCENDING
from pymongo.asynchronous.client_session import AsyncClientSession

from app.db import Database

COLLECTION = "measurements"


async def ensure_indexes(db: Database) -> None:
    await db[COLLECTION].create_index(
        [("frame", ASCENDING), ("position", ASCENDING), ("number", ASCENDING)], unique=True
    )


async def list_for_frame(db: Database, barcode: str) -> list[dict[str, Any]]:
    return (
        await db[COLLECTION]
        .find({"frame": barcode})
        .sort([("position", ASCENDING), ("number", ASCENDING)])
        .to_list()
    )


async def get(db: Database, measurement_id: ObjectId) -> dict[str, Any] | None:
    return await db[COLLECTION].find_one({"_id": measurement_id})


async def counts_by_position(db: Database, barcodes: list[str]) -> dict[str, dict[str, int]]:
    """{barcode: {position: number of measurements}}."""
    result: dict[str, dict[str, int]] = {}
    pipeline = [
        {"$match": {"frame": {"$in": barcodes}}},
        {"$group": {"_id": {"frame": "$frame", "position": "$position"}, "n": {"$sum": 1}}},
    ]
    async for row in await db[COLLECTION].aggregate(pipeline):
        result.setdefault(row["_id"]["frame"], {})[row["_id"]["position"]] = row["n"]
    return result


async def pending_counts(db: Database, barcodes: list[str]) -> dict[str, int]:
    """{barcode: number of pending measurements}."""
    pipeline = [
        {"$match": {"frame": {"$in": barcodes}, "status": "pending"}},
        {"$group": {"_id": "$frame", "n": {"$sum": 1}}},
    ]
    return {row["_id"]: row["n"] async for row in await db[COLLECTION].aggregate(pipeline)}


async def delete_for_positions(
    db: Database, session: AsyncClientSession, barcode: str, positions: set[str]
) -> None:
    """Remove the measurements of cleared positions (only possible before they were executed)."""
    if positions:
        await db[COLLECTION].delete_many(
            {"frame": barcode, "position": {"$in": sorted(positions)}}, session=session
        )
