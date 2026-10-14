"""Endpoints for the beamline control software (requirements §10.2).

Authenticated with an API key (app.instrument.keys); only reachable on the internal network
(the public proxy blocks /api/instrument/). The control software reads what to measure,
reports frame and measurement progress, and uploads raw and processed data.
"""

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.auth.dependencies import Db
from app.data import repository as data
from app.data.models import ProcessedUpload, SweepInfo, SweepUpload, sweep_info
from app.frames import repository as frames
from app.frames.models import StorageLocation
from app.frames.states import FrameState
from app.instrument.keys import Instrument, client_actor
from app.measurements import repository as measurements
from app.measurements.models import MeasurementStatus
from app.measurements.options import Beam, Detection, Edge, Technique
from app.samples import repository as samples
from app.users import repository as users

router = APIRouter(prefix="/instrument", tags=["instrument"])

S = FrameState


# --- reading what to measure -----------------------------------------------------------------


class InstrumentMeasurement(BaseModel):
    id: str
    number: int
    technique: Technique
    element: str
    edge: Edge
    detection: Detection
    beam: Beam
    status: MeasurementStatus
    error_message: str | None
    # Numbers of the last uploaded batch and sweep (None before the first upload). A re-run
    # uses last_batch + 1 and continues the sweep numbers.
    last_batch: int | None
    last_sweep: int | None


class InstrumentPosition(BaseModel):
    position: str
    sample_id: str
    sample_name: str
    measurements: list[InstrumentMeasurement]


class InstrumentFrame(BaseModel):
    barcode: str
    state: FrameState
    locked: bool
    safe: bool
    storage: StorageLocation | None
    owner: str | None
    positions: list[InstrumentPosition]


class StoredFrameSummary(BaseModel):
    barcode: str
    container: int
    slot: int
    state: FrameState
    locked: bool


@router.get("/frames/{barcode}")
async def instrument_frame(barcode: str, _: Instrument, db: Db) -> InstrumentFrame:
    """Everything to measure on one frame."""
    frame = await _load_frame(db, barcode)
    return (await _frame_models(db, [frame]))[0]


@router.get("/storage/internal")
async def instrument_storage(_: Instrument, db: Db) -> list[StoredFrameSummary]:
    """All frames occupying internal-storage slots (incl. scheduled and loaded ones)."""
    docs = await db[frames.COLLECTION].find({"storage.container": {"$exists": True}}).to_list()
    rows = [
        StoredFrameSummary(
            barcode=d["_id"],
            container=d["storage"]["container"],
            slot=d["storage"]["slot"],
            state=d["state"],
            locked=bool(d.get("locked")),
        )
        for d in docs
    ]
    return sorted(rows, key=lambda r: (r.container, r.slot))


@router.get("/queue")
async def instrument_queue(_: Instrument, db: Db) -> list[InstrumentFrame]:
    """Locked frames in internal storage that have pending measurements.

    The scheduler of the control software decides what to measure when.
    """
    pending_frames = await db[measurements.COLLECTION].distinct(
        "frame", {"status": MeasurementStatus.PENDING.value}
    )
    docs = (
        await db[frames.COLLECTION]
        .find(
            {
                "_id": {"$in": pending_frames},
                "state": S.INTERNAL_STORAGE.value,
                "locked": True,
            }
        )
        .sort([("storage.container", ASCENDING), ("storage.slot", ASCENDING)])
        .to_list()
    )
    return await _frame_models(db, docs)


async def _frame_models(db: Db, docs: list[dict[str, Any]]) -> list[InstrumentFrame]:
    barcodes = [d["_id"] for d in docs]
    all_measurements = (
        await db[measurements.COLLECTION]
        .find({"frame": {"$in": barcodes}})
        .sort([("position", ASCENDING), ("number", ASCENDING)])
        .to_list()
    )
    last = await data.last_numbers(db, [m["_id"] for m in all_measurements])
    sample_ids = {p["sample_id"] for d in docs for p in d.get("positions", [])}
    names = {
        s["_id"]: s["name"]
        async for s in db[samples.COLLECTION].find({"_id": {"$in": list(sample_ids)}}, {"name": 1})
    }
    owners = await users.get_many(db, {d["owner_id"] for d in docs if d.get("owner_id")})

    result = []
    for d in docs:
        positions = []
        for p in d.get("positions", []):
            ms = [
                m
                for m in all_measurements
                if m["frame"] == d["_id"] and m["position"] == p["position"]
            ]
            positions.append(
                InstrumentPosition(
                    position=p["position"],
                    sample_id=str(p["sample_id"]),
                    sample_name=names.get(p["sample_id"], "(deleted sample)"),
                    measurements=[
                        InstrumentMeasurement(
                            id=str(m["_id"]),
                            number=m["number"],
                            technique=m["technique"],
                            element=m["element"],
                            edge=m["edge"],
                            detection=m["detection"],
                            beam=m["beam"],
                            status=m["status"],
                            error_message=m.get("error_message"),
                            last_batch=last.get(m["_id"], (None, None))[0],
                            last_sweep=last.get(m["_id"], (None, None))[1],
                        )
                        for m in ms
                    ],
                )
            )
        owner = owners.get(d.get("owner_id"))
        result.append(
            InstrumentFrame(
                barcode=d["_id"],
                state=d["state"],
                locked=bool(d.get("locked")),
                safe=bool(d.get("safety_declared")),
                storage=StorageLocation(**d["storage"]) if d.get("storage") else None,
                owner=owner["name"] if owner else None,
                positions=positions,
            )
        )
    return result


# --- reporting progress ----------------------------------------------------------------------


class StateChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal["scheduled", "loaded", "internal_storage"]


# Moves the control software may make (requirements §6.3).
_INSTRUMENT_MOVES: dict[FrameState, set[FrameState]] = {
    S.INTERNAL_STORAGE: {S.SCHEDULED},
    S.SCHEDULED: {S.LOADED, S.INTERNAL_STORAGE},
    S.LOADED: {S.INTERNAL_STORAGE},
}


@router.post("/frames/{barcode}/state")
async def instrument_set_frame_state(
    barcode: str, body: StateChange, client: Instrument, db: Db
) -> InstrumentFrame:
    """Scheduled -> loaded -> back to internal storage (the frame keeps its slot)."""
    frame = await _load_frame(db, barcode)
    current, target = FrameState(frame["state"]), FrameState(body.state)
    if target not in _INSTRUMENT_MOVES.get(current, set()):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Cannot move from {current.value} to {target.value}"
        )
    if target is S.SCHEDULED and not frame.get("locked"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Only locked frames can be scheduled")
    now = datetime.now(UTC)
    updated = await db[frames.COLLECTION].find_one_and_update(
        {"_id": frame["_id"], "state": current.value},
        {
            "$set": {"state": target.value, "updated_at": now},
            "$push": {"history": {"state": target.value, "at": now, "actor": client_actor(client)}},
            "$inc": {"version": 1},
        },
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "The frame changed; please reload")
    return (await _frame_models(db, [updated]))[0]


class StatusChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # "pending" again = re-measure; the next upload then starts a new batch.
    status: MeasurementStatus
    error_message: str | None = Field(default=None, max_length=2000)


@router.put("/measurements/{measurement_id}/status")
async def instrument_set_status(
    measurement_id: str, body: StatusChange, client: Instrument, db: Db
) -> InstrumentMeasurement:
    measurement = await _load_measurement(db, measurement_id)
    changes: dict[str, Any] = {
        "status": body.status.value,
        "error_message": body.error_message if body.status is MeasurementStatus.ERROR else None,
        "updated_at": datetime.now(UTC),
        "changed_by": client_actor(client),
    }
    if body.status is not MeasurementStatus.PENDING:
        changes["executed"] = True  # has run at least once; can no longer be deleted
    updated = await db[measurements.COLLECTION].find_one_and_update(
        {"_id": measurement["_id"]}, {"$set": changes}, return_document=ReturnDocument.AFTER
    )
    assert updated is not None
    last = await data.last_numbers(db, [updated["_id"]])
    batch, sweep = last.get(updated["_id"], (None, None))
    return InstrumentMeasurement(
        id=str(updated["_id"]),
        number=updated["number"],
        technique=updated["technique"],
        element=updated["element"],
        edge=updated["edge"],
        detection=updated["detection"],
        beam=updated["beam"],
        status=updated["status"],
        error_message=updated.get("error_message"),
        last_batch=batch,
        last_sweep=sweep,
    )


# --- uploading data --------------------------------------------------------------------------


@router.post("/measurements/{measurement_id}/sweeps", status_code=status.HTTP_201_CREATED)
async def upload_sweep(
    measurement_id: str, body: SweepUpload, client: Instrument, db: Db
) -> SweepInfo:
    """Store one raw sweep. A sweep number exists only once per measurement (1-999)."""
    measurement = await _load_measurement(db, measurement_id)
    frame = await frames.get(db, measurement["frame"])
    assert frame is not None
    placed = next(
        (p for p in frame.get("positions", []) if p["position"] == measurement["position"]), None
    )
    now = datetime.now(UTC)
    doc = {
        "measurement_id": measurement["_id"],
        # Copied from the database, never from the uploader.
        "frame": frame["_id"],
        "position": measurement["position"],
        "number": measurement["number"],
        "sample_id": placed["sample_id"] if placed else None,
        "owner_id": frame.get("owner_id"),
        "batch_no": body.batch_no,
        "sweep_no": body.sweep_no,
        # What was measured at upload time.
        "measured": {
            key: measurement[key] for key in ("technique", "element", "edge", "detection", "beam")
        },
        "metadata": body.metadata,
        "channels": [c.model_dump() for c in body.channels],
        "uploaded_at": now,
        "uploaded_by": client_actor(client),
    }
    try:
        doc["_id"] = (await db[data.SWEEPS].insert_one(doc)).inserted_id
    except DuplicateKeyError:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Sweep {body.sweep_no} already exists for this measurement",
        ) from None
    await db[measurements.COLLECTION].update_one(
        {"_id": measurement["_id"]}, {"$set": {"executed": True}}
    )
    return sweep_info(doc, has_processed=False)


@router.put("/measurements/{measurement_id}/sweeps/{batch_no}/{sweep_no}/processed")
async def upload_processed(
    measurement_id: str,
    batch_no: int,
    sweep_no: int,
    body: ProcessedUpload,
    client: Instrument,
    db: Db,
) -> SweepInfo:
    """Store (or replace) the processed result of an uploaded sweep."""
    measurement = await _load_measurement(db, measurement_id)
    sweep = await db[data.SWEEPS].find_one(
        {"measurement_id": measurement["_id"], "batch_no": batch_no, "sweep_no": sweep_no},
    )
    if sweep is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Upload the raw sweep first")
    await db[data.PROCESSED].replace_one(
        {"sweep_id": sweep["_id"]},
        {
            "sweep_id": sweep["_id"],
            "measurement_id": measurement["_id"],
            "frame": sweep["frame"],
            "batch_no": batch_no,
            "sweep_no": sweep_no,
            "metadata": body.metadata,
            "mu": body.mu.model_dump(),
            "chi": body.chi.model_dump() if body.chi else None,
            "uploaded_at": datetime.now(UTC),
            "uploaded_by": client_actor(client),
        },
        upsert=True,
    )
    return sweep_info(sweep, has_processed=True)


# --- helpers ---------------------------------------------------------------------------------


async def _load_frame(db: Db, barcode: str) -> dict[str, Any]:
    frame = await frames.get(db, frames.normalize_barcode(barcode))
    if frame is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown barcode")
    return frame


async def _load_measurement(db: Db, measurement_id: str) -> dict[str, Any]:
    oid = users.parse_id(measurement_id)
    doc = await measurements.get(db, oid) if oid else None
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Measurement not found")
    return doc
