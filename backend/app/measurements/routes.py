"""Measurement endpoints (requirements §8.3). Owner or Operator, while the frame is unlocked."""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pymongo.asynchronous.client_session import AsyncClientSession

from app import beamline
from app.auth.dependencies import CurrentUser, Db, is_operator
from app.frames import configuration as config
from app.frames import repository as frames
from app.frames.repository import actor
from app.frames.versioning import in_transaction, save_versioned
from app.measurements import repository as measurements
from app.measurements.models import Measurement, MeasurementInput, MeasurementStatus, to_model
from app.measurements.options import MeasurementOptions, options_for
from app.users import repository as users

router = APIRouter(tags=["measurements"])


@router.get("/measurement-options")
async def measurement_options(_: CurrentUser, db: Db) -> MeasurementOptions:
    allowed = await beamline.energy_range(db)
    return options_for(allowed.energy_min, allowed.energy_max)


async def _ensure_measurable(db: Db, element: str, edge: str) -> None:
    problem = beamline.out_of_range_message(element, edge, await beamline.energy_range(db))
    if problem:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, problem)


@router.get("/frames/{barcode}/measurements")
async def list_measurements(barcode: str, user: CurrentUser, db: Db) -> list[Measurement]:
    frame = await load_frame(db, barcode, user)
    return [to_model(doc) for doc in await measurements.list_for_frame(db, frame["_id"])]


@router.post(
    "/frames/{barcode}/positions/{position}/measurements",
    status_code=status.HTTP_201_CREATED,
)
async def add_measurement(
    barcode: str, position: str, body: MeasurementInput, user: CurrentUser, db: Db
) -> Measurement:
    frame = await load_frame(db, barcode, user)
    _ensure_editable(frame)
    await _ensure_measurable(db, body.element, body.edge.value)
    if not any(p["position"] == position for p in frame.get("positions", [])):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Place a sample at {position} first"
        )
    now = datetime.now(UTC)

    async def apply(session: AsyncClientSession) -> dict[str, Any]:
        updated = await save_versioned(
            db,
            frame["_id"],
            body.version,
            {},
            session,
            increment={f"measurement_counters.{position}": 1},
        )
        doc = {
            "frame": frame["_id"],
            "position": position,
            "number": updated["measurement_counters"][position],
            **_settings(body),
            "status": MeasurementStatus.PENDING.value,
            "error_message": None,
            "executed": False,
            "created_at": now,
            "updated_at": now,
            "changed_by": actor(user),
        }
        doc["_id"] = (
            await db[measurements.COLLECTION].insert_one(doc, session=session)
        ).inserted_id
        return doc

    return to_model(await in_transaction(db, apply))


@router.put("/measurements/{measurement_id}")
async def update_measurement(
    measurement_id: str, body: MeasurementInput, user: CurrentUser, db: Db
) -> Measurement:
    """Change a measurement's settings. Data already collected keeps its own metadata."""
    doc, frame = await _load_measurement(db, measurement_id, user)
    _ensure_editable(frame)
    # Measurements made before the range changed stay valid as long as their edge is kept.
    if (body.element, body.edge.value) != (doc["element"], doc["edge"]):
        await _ensure_measurable(db, body.element, body.edge.value)
    changes = {**_settings(body), "updated_at": datetime.now(UTC), "changed_by": actor(user)}

    async def apply(session: AsyncClientSession) -> dict[str, Any]:
        await save_versioned(db, frame["_id"], body.version, {}, session)
        await db[measurements.COLLECTION].update_one(
            {"_id": doc["_id"]}, {"$set": changes}, session=session
        )
        return {**doc, **changes}

    return to_model(await in_transaction(db, apply))


@router.delete("/measurements/{measurement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_measurement(measurement_id: str, version: int, user: CurrentUser, db: Db) -> None:
    doc, frame = await _load_measurement(db, measurement_id, user)
    _ensure_editable(frame)
    if doc.get("executed"):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This measurement has been executed and cannot be deleted"
        )

    async def apply(session: AsyncClientSession) -> dict[str, Any]:
        updated = await save_versioned(db, frame["_id"], version, {}, session)
        await db[measurements.COLLECTION].delete_one({"_id": doc["_id"]}, session=session)
        return updated

    await in_transaction(db, apply)


# --- helpers -------------------------------------------------------------------------------


async def load_frame(db: Db, barcode: str, user: dict[str, Any]) -> dict[str, Any]:
    """The frame, if the user owns it or is an Operator."""
    frame = await frames.get(db, frames.normalize_barcode(barcode))
    if frame is None or (frame.get("owner_id") != user["_id"] and not is_operator(user)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Frame not found")
    return frame


async def _load_measurement(
    db: Db, measurement_id: str, user: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    oid = users.parse_id(measurement_id)
    doc = await measurements.get(db, oid) if oid else None
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Measurement not found")
    return doc, await load_frame(db, doc["frame"], user)


def _ensure_editable(frame: dict[str, Any]) -> None:
    reason = config.why_measurements_frozen(frame)
    if reason:
        raise HTTPException(status.HTTP_409_CONFLICT, reason)


def _settings(body: MeasurementInput) -> dict[str, Any]:
    return body.model_dump(mode="json", exclude={"version"})
