"""Safety declaration and lock (requirements §6.4).

- The owner declares the frame safe once it is complete (§6.5); this freezes plates, sample
  placement and the samples themselves. A frame on hold at the facility becomes "received".
- Locking needs the safety declaration and freezes the measurements. Owner or Operator may lock
  and unlock; nobody can unlock while the frame is scheduled or loaded.
"""

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict
from pymongo.asynchronous.client_session import AsyncClientSession

from app.auth.dependencies import CurrentUser, Db
from app.frames.configuration import missing_for_declaration
from app.frames.models import Frame
from app.frames.repository import actor
from app.frames.states import TERMINAL, FrameState
from app.frames.versioning import in_transaction, save_versioned
from app.frames.views import frame_model
from app.measurements import repository as measurements
from app.measurements.routes import load_frame
from app.samples import repository as samples

router = APIRouter(prefix="/frames", tags=["safety and lock"])

DECLARABLE_STATES = {FrameState.ISSUED, FrameState.SHIPPED_TO_USER, FrameState.RECEIVED_ON_HOLD}
NO_UNLOCK_STATES = {FrameState.SCHEDULED, FrameState.LOADED, *TERMINAL}


class DeclareSafe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    # The ticked checkbox: "I declare that all samples on this frame are solid and non-hazardous."
    confirm: Literal[True]


class VersionOnly(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int


@router.post("/{barcode}/declare-safe")
async def declare_safe(barcode: str, body: DeclareSafe, user: CurrentUser, db: Db) -> Frame:
    frame = await load_frame(db, barcode, user)
    if frame.get("owner_id") != user["_id"]:
        # Nobody, not even an Admin, may declare safety on the owner's behalf.
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the frame's owner can declare it safe")
    if frame.get("safety_declared"):
        raise HTTPException(status.HTTP_409_CONFLICT, "The frame is already declared safe")
    if frame["state"] not in DECLARABLE_STATES:
        raise HTTPException(status.HTTP_409_CONFLICT, "The frame can no longer be declared safe")
    await _ensure_complete(db, frame)

    now = datetime.now(UTC)
    by = actor(user)
    changes: dict[str, Any] = {"safety_declared": {"at": now, "by": by}}
    push = None
    if frame["state"] == FrameState.RECEIVED_ON_HOLD:
        # The hold is lifted automatically (§6.3).
        changes["state"] = FrameState.RECEIVED.value
        push = {"history": {"state": FrameState.RECEIVED.value, "at": now, "actor": by}}
    sample_ids = list({p["sample_id"] for p in frame.get("positions", [])})

    async def apply(session: AsyncClientSession) -> dict[str, Any]:
        updated = await save_versioned(db, frame["_id"], body.version, changes, session, push=push)
        await db[samples.COLLECTION].update_many(
            {"_id": {"$in": sample_ids}}, {"$set": {"frozen": True}}, session=session
        )
        return updated

    return await frame_model(db, await in_transaction(db, apply))


@router.post("/{barcode}/lock")
async def lock(barcode: str, body: VersionOnly, user: CurrentUser, db: Db) -> Frame:
    frame = await load_frame(db, barcode, user)
    if not frame.get("safety_declared"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Declare the frame safe before locking it")
    if frame["state"] in TERMINAL:
        raise HTTPException(status.HTTP_409_CONFLICT, "The frame is no longer active")
    # Measurements may have changed while unlocked.
    await _ensure_complete(db, frame)
    changes = {"locked": True, "lock_changed": {"at": datetime.now(UTC), "by": actor(user)}}
    return await frame_model(db, await save_versioned(db, frame["_id"], body.version, changes))


@router.post("/{barcode}/unlock")
async def unlock(barcode: str, body: VersionOnly, user: CurrentUser, db: Db) -> Frame:
    frame = await load_frame(db, barcode, user)
    if frame["state"] in NO_UNLOCK_STATES:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "The frame cannot be unlocked while it is being measured"
        )
    changes = {"locked": False, "lock_changed": {"at": datetime.now(UTC), "by": actor(user)}}
    return await frame_model(db, await save_versioned(db, frame["_id"], body.version, changes))


async def _ensure_complete(db: Db, frame: dict[str, Any]) -> None:
    counts = await measurements.counts_by_position(db, [frame["_id"]])
    missing = missing_for_declaration(frame, counts.get(frame["_id"], {}))
    if missing:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "; ".join(missing))
