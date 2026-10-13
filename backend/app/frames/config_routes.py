"""Frame configuration by its owner: plates, note, sample positions (requirements §8.1).

Every change carries the frame's `version` (see app.frames.versioning).
"""

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pymongo.asynchronous.client_session import AsyncClientSession

from app.auth.dependencies import CurrentUser, Db
from app.frames import configuration as config
from app.frames import repository as frames
from app.frames.models import Frame, NoteUpdate, PlatesUpdate, PositionAssign
from app.frames.versioning import in_transaction, save_versioned
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
        updated = await save_versioned(
            db, doc["_id"], body.version, {"plates": new_plates, "positions": kept}, session
        )
        await measurements.delete_for_positions(db, session, doc["_id"], cleared)
        return updated

    return await frame_model(db, await in_transaction(db, apply))


@router.put("/{barcode}/note")
async def set_note(barcode: str, body: NoteUpdate, user: CurrentUser, db: Db) -> Frame:
    doc = await _load_configurable(db, barcode, user)
    return await frame_model(
        db, await save_versioned(db, doc["_id"], body.version, {"note": body.note})
    )


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
        db, await save_versioned(db, doc["_id"], body.version, {"positions": positions})
    )


@router.delete("/{barcode}/positions/{position}")
async def clear_position(
    barcode: str, position: str, version: int, user: CurrentUser, db: Db
) -> Frame:
    """Remove the sample from a position, together with the position's measurements."""
    doc = await _load_configurable(db, barcode, user)
    positions = [p for p in doc.get("positions", []) if p["position"] != position]

    async def apply(session: AsyncClientSession) -> dict[str, Any]:
        updated = await save_versioned(db, doc["_id"], version, {"positions": positions}, session)
        await measurements.delete_for_positions(db, session, doc["_id"], {position})
        return updated

    return await frame_model(db, await in_transaction(db, apply))


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
