"""Optimistic concurrency for frames (requirements §12).

Every change to a frame (configuration, measurements, safety declaration, lock) sends the
frame's `version`; if someone else changed the frame meanwhile, the change fails with 409
instead of silently overwriting.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession

from app.db import Database
from app.frames import repository as frames


async def save_versioned(
    db: Database,
    barcode: str,
    version: int,
    changes: dict[str, Any],
    session: AsyncClientSession | None = None,
    *,
    increment: dict[str, int] | None = None,
    push: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply changes if the frame still has the given version; bump the version.

    Returns the updated frame document.
    """
    # Frames created before versioning have no version field; treat that as 0.
    version_filter: Any = version if version else {"$in": [0, None]}
    update: dict[str, Any] = {
        "$set": {**changes, "updated_at": datetime.now(UTC)},
        "$inc": {"version": 1, **(increment or {})},
    }
    if push:
        update["$push"] = push
    updated = await db[frames.COLLECTION].find_one_and_update(
        {"_id": barcode, "version": version_filter},
        update,
        return_document=ReturnDocument.AFTER,
        session=session,
    )
    if updated is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "The frame was changed elsewhere; please reload"
        )
    return updated


async def in_transaction(
    db: Database, fn: Callable[[AsyncClientSession], Awaitable[dict[str, Any]]]
) -> dict[str, Any]:
    async with db.client.start_session() as session:
        return await session.with_transaction(fn)
