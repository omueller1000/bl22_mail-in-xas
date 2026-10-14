"""Data viewer and export endpoints (requirements §11.3-§11.5). Owner or Operator."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

import numpy as np
from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel

from app.auth.dependencies import CurrentUser, Db
from app.data import repository as data
from app.data import spectra
from app.data.export import FrameZip
from app.data.models import SweepInfo, sweep_info
from app.measurements.routes import load_frame
from app.samples import repository as samples
from app.users import repository as users

router = APIRouter(tags=["data"])


class View(StrEnum):
    RAW = "raw"  # one channel vs energy
    SPECTRUM = "spectrum"  # a derived spectrum vs energy
    MU = "mu"  # processed mu(E)
    CHI = "chi"  # processed k^2 chi(k)


class PlotCurve(BaseModel):
    x: list[float | None]
    y: list[float | None]


class ProcessedInfo(BaseModel):
    metadata: dict[str, Any]
    has_chi: bool
    uploaded_at: datetime


class SweepDetail(BaseModel):
    sweep: SweepInfo
    metadata: dict[str, Any]
    processed: ProcessedInfo | None


@router.get("/frames/{barcode}/sweeps")
async def list_frame_sweeps(barcode: str, user: CurrentUser, db: Db) -> list[SweepInfo]:
    """All sweeps of a frame, without their values (for choosing what to plot)."""
    frame = await load_frame(db, barcode, user)
    pipeline: list[dict[str, Any]] = [
        {"$match": {"frame": frame["_id"]}},
        {
            "$project": {
                "measurement_id": 1,
                "frame": 1,
                "position": 1,
                "number": 1,
                "batch_no": 1,
                "sweep_no": 1,
                "measured": 1,
                "uploaded_at": 1,
                "channel_names": "$channels.name",
                "points": {"$size": {"$ifNull": [{"$first": "$channels.values"}, []]}},
            }
        },
        {"$sort": {"position": 1, "number": 1, "batch_no": 1, "sweep_no": 1}},
    ]
    docs = [doc async for doc in await db[data.SWEEPS].aggregate(pipeline)]
    processed = {
        doc["sweep_id"]
        async for doc in db[data.PROCESSED].find({"frame": frame["_id"]}, {"sweep_id": 1})
    }
    return [sweep_info(doc, has_processed=doc["_id"] in processed) for doc in docs]


@router.get("/sweeps/{sweep_id}")
async def get_sweep(sweep_id: str, user: CurrentUser, db: Db) -> SweepDetail:
    """A sweep's metadata and, if processed, the processing metadata (E0, parameters, ...)."""
    sweep = await _load_sweep(db, sweep_id, user)
    processed = await db[data.PROCESSED].find_one({"sweep_id": sweep["_id"]}, {"mu": 0})
    return SweepDetail(
        sweep=sweep_info(sweep, has_processed=processed is not None),
        metadata=sweep.get("metadata", {}),
        processed=ProcessedInfo(
            metadata=processed.get("metadata", {}),
            has_chi=processed.get("chi") is not None,
            uploaded_at=processed["uploaded_at"],
        )
        if processed
        else None,
    )


@router.get("/sweeps/{sweep_id}/curve")
async def get_sweep_curve(
    sweep_id: str, view: View, user: CurrentUser, db: Db, name: str | None = None
) -> PlotCurve:
    """One curve of a sweep: a raw channel or derived spectrum vs energy, or processed data."""
    sweep = await _load_sweep(db, sweep_id, user)
    x, y = await _curve(db, sweep, view, name)
    return PlotCurve(x=spectra.to_list(x), y=spectra.to_list(y))


@router.get("/measurements/{measurement_id}/batches/{batch_no}/merge")
async def merge_sweeps(
    measurement_id: str,
    batch_no: int,
    view: View,
    sweeps: Annotated[list[int], Query(min_length=1, max_length=999)],
    user: CurrentUser,
    db: Db,
    name: str | None = None,
) -> PlotCurve:
    """Average of the selected sweeps (by sweep number) of one batch; not stored (§11.3)."""
    oid = users.parse_id(measurement_id)
    query = {"measurement_id": oid, "batch_no": batch_no, "sweep_no": {"$in": sweeps}}
    docs = [doc async for doc in db[data.SWEEPS].find(query)] if oid else []
    if not docs:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such sweeps")
    await load_frame(db, docs[0]["frame"], user)
    x, y = spectra.merge([await _curve(db, doc, view, name) for doc in docs])
    return PlotCurve(x=spectra.to_list(x), y=spectra.to_list(y))


@router.get(
    "/frames/{barcode}/export.zip",
    response_class=Response,
    responses={200: {"content": {"application/zip": {}}}},
)
async def export_frame(barcode: str, user: CurrentUser, db: Db) -> Response:
    """All raw and processed sweeps of a frame as XDI files in one ZIP (§11.5)."""
    frame = await load_frame(db, barcode, user)
    if not await db[data.SWEEPS].count_documents({"frame": frame["_id"]}, limit=1):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This frame has no data yet")
    processed = {
        doc["sweep_id"]: doc async for doc in db[data.PROCESSED].find({"frame": frame["_id"]})
    }
    names: dict[Any, str] = {}
    archive = FrameZip()
    cursor = (
        db[data.SWEEPS]
        .find({"frame": frame["_id"]})
        .sort([("position", 1), ("number", 1), ("batch_no", 1), ("sweep_no", 1)])
    )
    async for sweep in cursor:
        sample_id = sweep.get("sample_id")
        if sample_id not in names:
            sample = await samples.get(db, sample_id) if sample_id else None
            names[sample_id] = sample["name"] if sample else "sample"
        archive.add_sweep(sweep, processed.get(sweep["_id"]), names[sample_id])
    return Response(
        archive.close(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{frame["_id"]}.zip"'},
    )


# --- helpers ---------------------------------------------------------------------------------


async def _load_sweep(db: Db, sweep_id: str, user: dict[str, Any]) -> dict[str, Any]:
    oid = users.parse_id(sweep_id)
    sweep = await db[data.SWEEPS].find_one({"_id": oid}) if oid else None
    if sweep is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sweep not found")
    await load_frame(db, sweep["frame"], user)
    return sweep


async def _curve(
    db: Db, sweep: dict[str, Any], view: View, name: str | None
) -> tuple[spectra.Array, spectra.Array]:
    if view in (View.MU, View.CHI):
        processed = await db[data.PROCESSED].find_one({"sweep_id": sweep["_id"]})
        curve = processed and processed.get(view.value)
        if not curve:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"No processed {view.value} data")
        return np.asarray(curve["x"], dtype=np.float64), np.asarray(curve["y"], dtype=np.float64)

    channels = {c["name"]: np.asarray(c["values"], dtype=np.float64) for c in sweep["channels"]}
    if view is View.RAW:
        if name not in channels:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"No channel {name!r}")
        return channels["energy"], channels[name]
    if name not in spectra.available(list(channels)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Spectrum {name!r} is not available")
    return channels["energy"], spectra.compute(name, channels)
