"""Frame configuration by its owner: plates, note, sample positions (requirements §8.1).

Every change sends the frame's `version`; if someone else changed the frame meanwhile, the
request fails with 409 instead of silently overwriting (requirements §12).
"""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession

from app.auth.dependencies import CurrentUser, Db
from app.frames import configuration as config
from app.frames import repository as frames
from app.frames.models import Frame, NoteUpdate, PlatesUpdate, PositionAssign
from app.frames.views import frame_model
from app.measurements import repository as measurements
from app.samples import repository as samples
from app.users import repository as users

router = APIRouter(prefix="/frames", tags=["frame configuration"])


@router.put("/{barcode}/plates")
async def set_plates(barcode: str, body: PlatesUpdate, user: CurrentUser, db: Db) -> Frame:
    """Mount plates. Positions on a side whose plate changes are cleared with their measurements."""
    doc = await _load_configurable(db, barcode, user)
    try:
        config.check_plates(body.left, body.right)
    except config.ConfigurationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None

    new_plates = {"left": body.left, "right": body.right}
    changed = config.changed_sides(doc.get("plates") or {}, new_plates)
    kept = [p for p in doc.get("positions", []) if config.side_of(p["position"]) not in changed]
    cleared = {p["position"] for p in doc.get("positions", [])} - {p["position"] for p in kept}

    async def apply(session: AsyncClientSession) -> dict[str, Any]:
        updated = await _save(
            db, doc["_id"], body.version, {"plates": new_plates, "positions": kept}, session
        )
        await measurements.delete_for_positions(db, session, doc["_id"], cleared)
        return updated

    return await frame_model(db, await _in_transaction(db, apply))


@router.put("/{barcode}/note")
async def set_note(barcode: str, body: NoteUpdate, user: CurrentUser, db: Db) -> Frame:
    doc = await _load_configurable(db, barcode, user)
    return await frame_model(db, await _save(db, doc["_id"], body.version, {"note": body.note}))


@router.put("/{barcode}/positions/{position}")
async def assign_sample(
    barcode: str, position: str, body: PositionAssign, user: CurrentUser, db: Db
) -> Frame:
    """Place one of the user's samples at a position (or replace the sample there)."""
    doc = await _load_configurable(db, barcode, user)
    _ensure_position_exists(doc, position)
    sample_id = users.parse_id(body.sample_id)
    sample = await samples.get(db, sample_id) if sample_id else None
    if sample is None or sample["owner_id"] != user["_id"]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown sample")

    positions = [p for p in doc.get("positions", []) if p["position"] != position]
    positions.append({"position": position, "sample_id": sample["_id"]})
    positions.sort(key=lambda p: p["position"])
    return await frame_model(
        db, await _save(db, doc["_id"], body.version, {"positions": positions})
    )


@router.delete("/{barcode}/positions/{position}")
async def clear_position(
    barcode: str, position: str, version: int, user: CurrentUser, db: Db
) -> Frame:
    """Remove the sample from a position, together with the position's measurements."""
    doc = await _load_configurable(db, barcode, user)
    positions = [p for p in doc.get("positions", []) if p["position"] != position]

    async def apply(session: AsyncClientSession) -> dict[str, Any]:
        updated = await _save(db, doc["_id"], version, {"positions": positions}, session)
        await measurements.delete_for_positions(db, session, doc["_id"], {position})
        return updated

    return await frame_model(db, await _in_transaction(db, apply))


# --- helpers -------------------------------------------------------------------------------


async def _load_configurable(db: Db, barcode: str, user: dict[str, Any]) -> dict[str, Any]:
    doc = await frames.get(db, frames.normalize_barcode(barcode))
    if doc is None or doc.get("owner_id") != user["_id"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Frame not found")
    reason = config.why_not_configurable(doc)
    if reason:
        raise HTTPException(status.HTTP_409_CONFLICT, reason)
    return doc


def _ensure_position_exists(doc: dict[str, Any], position: str) -> None:
    if position not in config.positions_of(doc.get("plates") or {}):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Position {position} is not on this frame"
        )


async def _save(
    db: Db,
    barcode: str,
    version: int,
    changes: dict[str, Any],
    session: AsyncClientSession | None = None,
) -> dict[str, Any]:
    """Apply changes if the frame still has the given version; bump the version."""
    # Frames created before versioning have no version field; treat that as 0.
    version_filter: Any = version if version else {"$in": [0, None]}
    updated = await db[frames.COLLECTION].find_one_and_update(
        {"_id": barcode, "version": version_filter},
        {"$set": {**changes, "updated_at": datetime.now(UTC)}, "$inc": {"version": 1}},
        return_document=ReturnDocument.AFTER,
        session=session,
    )
    if updated is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "The frame was changed elsewhere; please reload"
        )
    return updated


async def _in_transaction(db: Db, fn: Any) -> dict[str, Any]:
    async with db.client.start_session() as session:
        return await session.with_transaction(fn)
