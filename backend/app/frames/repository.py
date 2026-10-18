"""Database access for frames. A frame document exists from the moment its barcode is reserved.

Document: {_id: barcode, state, owner_id, request_id, note, plates: {left, right},
           positions: [{position, sample_id}], safety_declared: {at, by} | None, locked,
           version, history: [{state, at, actor}], created_at, updated_at}
"""

import re
import secrets
import string
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from pymongo import ASCENDING
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import BulkWriteError

from app.db import Database
from app.frames.states import FrameState

COLLECTION = "frames"

BARCODE_PATTERN = re.compile(r"[A-Z]{4}-[A-Z]{4}")


def new_barcode() -> str:
    """Random v1-style barcode XXXX-XXXX (uppercase letters; 26^8 ≈ 2·10^11 combinations)."""
    letters = "".join(secrets.choice(string.ascii_uppercase) for _ in range(8))
    return f"{letters[:4]}-{letters[4:]}"


def normalize_barcode(value: str) -> str:
    return value.strip().upper()


def actor(user: dict[str, Any]) -> dict[str, str]:
    """Who triggered a change, as stored in the frame history."""
    return {"orcid": user["orcid"], "name": user["name"]}


async def ensure_indexes(db: Database) -> None:
    await db[COLLECTION].create_index([("state", ASCENDING), ("owner_id", ASCENDING)])
    await db[COLLECTION].create_index([("owner_id", ASCENDING)])


async def reserve(db: Database, count: int, by: dict[str, Any]) -> list[dict[str, Any]]:
    """Create `count` new frames in state reserved, with barcodes never used before."""
    now = datetime.now(UTC)
    created: list[dict[str, Any]] = []
    while len(created) < count:
        docs = [
            {
                "_id": new_barcode(),
                "state": FrameState.RESERVED.value,
                "owner_id": None,
                "request_id": None,
                "note": "",
                "plates": {"left": None, "right": None},
                "positions": [],
                "safety_declared": None,
                "locked": False,
                "version": 0,
                "history": [{"state": FrameState.RESERVED.value, "at": now, "actor": actor(by)}],
                "created_at": now,
                "updated_at": now,
            }
            for _ in range(count - len(created))
        ]
        try:
            await db[COLLECTION].insert_many(docs, ordered=False)
            created.extend(docs)
        except BulkWriteError as exc:
            # Extremely rare collision with an existing barcode: keep the rest, retry the clashes.
            failed = {error["index"] for error in exc.details["writeErrors"]}
            created.extend(doc for i, doc in enumerate(docs) if i not in failed)
    return created


async def get(
    db: Database, barcode: str, session: AsyncClientSession | None = None
) -> dict[str, Any] | None:
    return await db[COLLECTION].find_one({"_id": barcode}, session=session)


async def find(db: Database, query: dict[str, Any]) -> list[dict[str, Any]]:
    return await db[COLLECTION].find(query).sort("_id", ASCENDING).to_list()


async def transition(
    db: Database,
    session: AsyncClientSession,
    barcodes: list[str],
    *,
    from_state: FrameState,
    to_state: FrameState,
    by: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> int:
    """Move frames from one state to another; returns how many were in `from_state`."""
    now = datetime.now(UTC)
    result = await db[COLLECTION].update_many(
        {"_id": {"$in": barcodes}, "state": from_state.value},
        {
            "$set": {"state": to_state.value, "updated_at": now, **(extra or {})},
            "$push": {"history": {"state": to_state.value, "at": now, "actor": actor(by)}},
        },
        session=session,
    )
    return result.modified_count


# What leaves with the next shipment to a user: new frames and frames going back.
TO_SHIP = (FrameState.ISSUED, FrameState.RETURNING_TO_USER)


async def to_ship_by_owner(db: Database) -> dict[ObjectId, list[dict[str, Any]]]:
    """Frames waiting to be shipped (issued or returning), grouped by owner."""
    groups: dict[ObjectId, list[dict[str, Any]]] = {}
    for doc in await find(db, {"state": {"$in": [s.value for s in TO_SHIP]}}):
        groups.setdefault(doc["owner_id"], []).append(doc)
    return groups
