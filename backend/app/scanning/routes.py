"""Barcode scanning, internal storage and warnings (requirements §6.3, §6.7, §9)."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ASCENDING, ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import DuplicateKeyError

from app.auth.dependencies import CurrentUser, Db, Operator, ensure_operator
from app.db import Database
from app.frames import repository as frames
from app.frames.models import Barcode, Frame, UserRef, user_ref
from app.frames.repository import actor
from app.frames.states import FrameState
from app.frames.versioning import in_transaction
from app.frames.views import frame_model
from app.measurements import repository as measurements
from app.scanning.rules import ScanAction, leaves_slot, outcome
from app.users import repository as users

router = APIRouter(tags=["scanning and storage"])

CONTAINERS = 3  # containerId 0-2
SLOTS = 11  # slotId 0-10


async def ensure_indexes(db: Database) -> None:
    # One frame per internal-storage slot.
    await db[frames.COLLECTION].create_index(
        [("storage.container", ASCENDING), ("storage.slot", ASCENDING)],
        unique=True,
        partialFilterExpression={"storage.container": {"$exists": True}},
        name="unique_storage_slot",
    )


# --- group scans -----------------------------------------------------------------------------


class ScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: ScanAction
    barcodes: list[Barcode] = Field(min_length=1, max_length=200)


class ScanResult(BaseModel):
    barcode: str
    current_state: FrameState | None
    owner: str | None
    safe: bool
    locked: bool
    # State the frame moves (or would move) to; None if it cannot make this move.
    target_state: FrameState | None
    problem: str | None
    warning: str | None
    moved: bool


@router.post("/scans/check")
async def check_scan(body: ScanRequest, _: Operator, db: Db) -> list[ScanResult]:
    """What the action would do to each scanned frame (nothing is changed)."""
    codes = list(dict.fromkeys(body.barcodes))
    docs = {d["_id"]: d for d in await frames.find(db, {"_id": {"$in": codes}})}
    owners = await _owners(db, docs.values())
    return [_result(body.action, code, docs.get(code), owners, moved=False) for code in codes]


@router.post("/scans/apply")
async def apply_scan(body: ScanRequest, operator: Operator, db: Db) -> list[ScanResult]:
    """Move every scanned frame that may make the move; report the others with the reason."""
    codes = list(dict.fromkeys(body.barcodes))
    now = datetime.now(UTC)

    async def apply(session: AsyncClientSession) -> dict[str, Any]:
        found = await db[frames.COLLECTION].find({"_id": {"$in": codes}}, session=session).to_list()
        docs = {d["_id"]: d for d in found}
        moved = set()
        for code in codes:
            frame = docs.get(code)
            target = outcome(body.action, frame).target
            if frame is None or target is None:
                continue
            update: dict[str, Any] = {
                "$set": {"state": target.value, "updated_at": now},
                "$push": {"history": {"state": target.value, "at": now, "actor": actor(operator)}},
                "$inc": {"version": 1},
            }
            if leaves_slot(target):
                update["$unset"] = {"storage": ""}
            result = await db[frames.COLLECTION].update_one(
                {"_id": code, "state": frame["state"]}, update, session=session
            )
            if result.modified_count:
                moved.add(code)
        return {"before": docs, "moved": moved}

    applied = await in_transaction(db, apply)
    before: dict[str, Any] = applied["before"]
    owners = await _owners(db, before.values())
    return [
        _result(body.action, code, before.get(code), owners, moved=code in applied["moved"])
        for code in codes
    ]


def _result(
    action: ScanAction,
    code: str,
    frame: dict[str, Any] | None,
    owners: dict[Any, dict[str, Any]],
    *,
    moved: bool,
) -> ScanResult:
    result = outcome(action, frame)
    owner = owners.get(frame.get("owner_id")) if frame else None
    return ScanResult(
        barcode=code,
        current_state=frame["state"] if frame else None,
        owner=owner["name"] if owner else None,
        safe=bool(frame and frame.get("safety_declared")),
        locked=bool(frame and frame.get("locked")),
        target_state=result.target,
        problem=result.problem,
        warning=result.warning,
        moved=moved,
    )


async def _owners(db: Db, docs: Any) -> dict[Any, dict[str, Any]]:
    return await users.get_many(db, {d["owner_id"] for d in docs if d.get("owner_id")})


# --- internal storage ------------------------------------------------------------------------


class StorageSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    container: int = Field(ge=0, lt=CONTAINERS)
    slot: int = Field(ge=0, lt=SLOTS)


@router.post("/frames/{barcode}/internal-storage")
async def move_to_internal_storage(
    barcode: str, body: StorageSlot, operator: Operator, db: Db
) -> Frame:
    """Put one frame into a free container/slot (no batch scanning here, §9.2)."""
    frame = await _load(db, barcode)
    if frame["state"] not in {FrameState.RECEIVED, FrameState.EXTERNAL_STORAGE}:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Not possible from state {frame['state']}")
    now = datetime.now(UTC)
    try:
        updated = await db[frames.COLLECTION].find_one_and_update(
            {"_id": frame["_id"], "state": frame["state"]},
            {
                "$set": {
                    "state": FrameState.INTERNAL_STORAGE.value,
                    "storage": {"container": body.container, "slot": body.slot},
                    "updated_at": now,
                },
                "$push": {
                    "history": {
                        "state": FrameState.INTERNAL_STORAGE.value,
                        "at": now,
                        "actor": actor(operator),
                    }
                },
                "$inc": {"version": 1},
            },
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:
        occupant = await db[frames.COLLECTION].find_one(
            {"storage.container": body.container, "storage.slot": body.slot}, {"_id": 1}
        )
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Container {body.container}, slot {body.slot} is occupied"
            + (f" by {occupant['_id']}" if occupant else ""),
        ) from None
    if updated is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "The frame changed; please rescan")
    return await frame_model(db, updated)


@router.post("/frames/{barcode}/release")
async def release(barcode: str, operator: Operator, db: Db) -> Frame:
    """Put a scheduled or loaded frame back into its slot, e.g. after a control-software crash."""
    frame = await _load(db, barcode)
    if frame["state"] not in {FrameState.SCHEDULED, FrameState.LOADED}:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only scheduled or loaded frames")
    now = datetime.now(UTC)
    updated = await db[frames.COLLECTION].find_one_and_update(
        {"_id": frame["_id"], "state": frame["state"]},
        {
            "$set": {"state": FrameState.INTERNAL_STORAGE.value, "updated_at": now},
            "$push": {
                "history": {
                    "state": FrameState.INTERNAL_STORAGE.value,
                    "at": now,
                    "actor": actor(operator),
                }
            },
            "$inc": {"version": 1},
        },
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "The frame changed; please reload")
    return await frame_model(db, updated)


class StoredFrame(BaseModel):
    barcode: str
    container: int
    slot: int
    state: FrameState
    owner: UserRef | None
    safe: bool
    locked: bool
    pending_measurements: int


@router.get("/storage/internal")
async def internal_storage(_: Operator, db: Db) -> list[StoredFrame]:
    """Frames occupying internal-storage slots (incl. scheduled/loaded ones), by position."""
    docs = await db[frames.COLLECTION].find({"storage.container": {"$exists": True}}).to_list()
    owners = await _owners(db, docs)
    pending = await measurements.pending_counts(db, [d["_id"] for d in docs])
    rows = [
        StoredFrame(
            barcode=d["_id"],
            container=d["storage"]["container"],
            slot=d["storage"]["slot"],
            state=d["state"],
            owner=user_ref(owners.get(d.get("owner_id"))),
            safe=bool(d.get("safety_declared")),
            locked=bool(d.get("locked")),
            pending_measurements=pending.get(d["_id"], 0),
        )
        for d in docs
    ]
    return sorted(rows, key=lambda r: (r.container, r.slot))


# --- warnings (§6.7) -------------------------------------------------------------------------


class WarningKind(StrEnum):
    ON_HOLD = "on_hold"
    NOT_LOCKED = "not_locked"


class FrameWarning(BaseModel):
    barcode: str
    owner: UserRef | None
    kind: WarningKind
    message: str


AT_FACILITY_UNLOCKED_STATES = {
    FrameState.RECEIVED,
    FrameState.EXTERNAL_STORAGE,
    FrameState.INTERNAL_STORAGE,
}


@router.get("/warnings")
async def list_warnings(user: CurrentUser, db: Db, all_users: bool = False) -> list[FrameWarning]:
    """Frames at the facility that need the user's attention; Operators may list everyone's."""
    query: dict[str, Any] = {
        "$or": [
            {"state": FrameState.RECEIVED_ON_HOLD.value},
            {
                "state": {"$in": [s.value for s in AT_FACILITY_UNLOCKED_STATES]},
                "locked": {"$ne": True},
            },
        ]
    }
    if all_users:
        ensure_operator(user)
    else:
        query["owner_id"] = user["_id"]
    docs = await frames.find(db, query)
    owners = await _owners(db, docs)
    result = []
    for d in docs:
        on_hold = d["state"] == FrameState.RECEIVED_ON_HOLD
        result.append(
            FrameWarning(
                barcode=d["_id"],
                owner=user_ref(owners.get(d.get("owner_id"))),
                kind=WarningKind.ON_HOLD if on_hold else WarningKind.NOT_LOCKED,
                message=(
                    "Received but not declared safe: on hold, will not be measured"
                    if on_hold
                    else "At the facility but not locked: will not be measured until locked"
                ),
            )
        )
    return result


async def _load(db: Db, barcode: str) -> dict[str, Any]:
    frame = await frames.get(db, frames.normalize_barcode(barcode))
    if frame is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown barcode")
    return frame
