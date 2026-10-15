"""Data viewer and export endpoints (requirements §11.3-§11.5). Owner or Operator."""

from enum import StrEnum
from typing import Annotated, Any

import numpy as np
from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.auth.dependencies import CurrentUser, Db
from app.data import repository as data
from app.data import spectra
from app.data.export import FrameZip
from app.data.models import SweepInfo, sweep_info
from app.measurements.routes import load_frame
from app.processing import pipeline, settings
from app.processing.edges import SOURCE as E0_SOURCE
from app.processing.xas import ProcessingError
from app.samples import repository as samples
from app.users import repository as users

router = APIRouter(tags=["data"])


class View(StrEnum):
    RAW = "raw"  # one channel vs energy
    SPECTRUM = "spectrum"  # a derived spectrum vs energy


class PlotCurve(BaseModel):
    x: list[float | None]
    y: list[float | None]


class ChiR(BaseModel):
    r: list[float | None]
    magnitude: list[float | None]
    real: list[float | None]
    imaginary: list[float | None]


class SweepDetail(BaseModel):
    sweep: SweepInfo
    metadata: dict[str, Any]


class ProcessedSpectrum(BaseModel):
    """Processing of one input: a sweep's spectrum, or the merge of several sweeps (§11.3)."""

    spectrum: str
    sweeps: list[int]  # sweep numbers that went into the input
    element: str
    edge: str
    e0: float
    e0_source: str
    edge_step: float | None
    # mu(E) and the fitted functions on the same energies (null where not drawn).
    mu: PlotCurve
    pre_edge: PlotCurve | None
    post_edge: PlotCurve | None
    background: PlotCurve | None
    chi: PlotCurve | None  # k-weighted, see parameters.kweight
    ft_window: PlotCurve | None  # Fourier transform window (0..1) on the same k grid
    chir: ChiR | None
    parameters: dict[str, Any]
    # Steps that could not be done and why (e.g. a XANES scan has no EXAFS region).
    problems: list[str]


@router.get("/frames/{barcode}/sweeps")
async def list_frame_sweeps(barcode: str, user: CurrentUser, db: Db) -> list[SweepInfo]:
    """All sweeps of a frame, without their values (for choosing what to plot)."""
    frame = await load_frame(db, barcode, user)
    stages: list[dict[str, Any]] = [
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
    return [sweep_info(doc) async for doc in await db[data.SWEEPS].aggregate(stages)]


@router.get("/sweeps/{sweep_id}")
async def get_sweep(sweep_id: str, user: CurrentUser, db: Db) -> SweepDetail:
    """A sweep's metadata (as uploaded by the control software)."""
    sweep = await _load_sweep(db, sweep_id, user)
    return SweepDetail(sweep=sweep_info(sweep), metadata=sweep.get("metadata", {}))


@router.get("/sweeps/{sweep_id}/curve")
async def get_sweep_curve(
    sweep_id: str, view: View, name: str, user: CurrentUser, db: Db
) -> PlotCurve:
    """One curve of a sweep: a raw channel or a derived spectrum vs energy."""
    sweep = await _load_sweep(db, sweep_id, user)
    x, y = _curve(sweep, view, name)
    return PlotCurve(x=spectra.to_list(x), y=spectra.to_list(y))


@router.get("/measurements/{measurement_id}/batches/{batch_no}/merge")
async def merge_sweeps(
    measurement_id: str,
    batch_no: int,
    view: View,
    name: str,
    sweeps: Annotated[list[int], Query(min_length=1, max_length=999)],
    user: CurrentUser,
    db: Db,
) -> PlotCurve:
    """Average of the selected sweeps (by sweep number) of one batch; not stored (§11.3)."""
    docs = await _load_batch_sweeps(db, measurement_id, batch_no, sweeps, user)
    x, y = spectra.merge([_curve(doc, view, name) for doc in docs])
    return PlotCurve(x=spectra.to_list(x), y=spectra.to_list(y))


@router.get("/measurements/{measurement_id}/batches/{batch_no}/process")
async def process_sweeps(
    measurement_id: str,
    batch_no: int,
    spectrum: str,
    sweeps: Annotated[list[int], Query(min_length=1, max_length=999)],
    user: CurrentUser,
    db: Db,
) -> ProcessedSpectrum:
    """Normalisation, background, chi(k) and chi(R) of a spectrum; with several sweeps, of
    their merge. Computed on request with the current parameters, not stored."""
    docs = await _load_batch_sweeps(db, measurement_id, batch_no, sweeps, user)
    measured = docs[0]["measured"]
    parts = [_curve(doc, View.SPECTRUM, spectrum) for doc in docs]
    energy, mu = spectra.merge(parts) if len(parts) > 1 else parts[0]
    params = await settings.current(db)
    try:
        result = await run_in_threadpool(
            pipeline.process, energy, mu, measured["element"], measured["edge"], params
        )
    except ProcessingError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    c = pipeline.curves(result, params)

    def on_energy(values: np.ndarray | None) -> PlotCurve | None:
        return None if values is None else PlotCurve(x=_list(c.energy), y=_list(values))

    return ProcessedSpectrum(
        spectrum=spectrum,
        sweeps=sorted(doc["sweep_no"] for doc in docs),
        element=measured["element"],
        edge=measured["edge"],
        e0=result.e0,
        e0_source=E0_SOURCE,
        edge_step=result.normalization.edge_step if result.normalization else None,
        mu=PlotCurve(x=_list(c.energy), y=_list(c.mu)),
        pre_edge=on_energy(c.pre_edge),
        post_edge=on_energy(c.post_edge),
        background=on_energy(c.background),
        chi=PlotCurve(x=_list(c.k), y=_list(c.chi_weighted)) if c.k is not None else None,
        ft_window=PlotCurve(x=_list(c.k), y=_list(c.ft_window))
        if c.k is not None and c.ft_window is not None
        else None,
        chir=ChiR(
            r=_list(c.r),
            magnitude=_list(np.abs(c.chir)),
            real=_list(c.chir.real),
            imaginary=_list(c.chir.imag),
        )
        if c.r is not None and c.chir is not None
        else None,
        parameters=params.as_dict(),
        problems=result.problems,
    )


@router.get(
    "/frames/{barcode}/export.zip",
    response_class=Response,
    responses={200: {"content": {"application/zip": {}}}},
)
async def export_frame(barcode: str, user: CurrentUser, db: Db) -> Response:
    """All sweeps of a frame as XDI files in one ZIP, raw and processed (§11.5)."""
    frame = await load_frame(db, barcode, user)
    if not await db[data.SWEEPS].count_documents({"frame": frame["_id"]}, limit=1):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This frame has no data yet")
    names: dict[Any, str] = {}
    archive = FrameZip(await settings.current(db))
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
        await run_in_threadpool(archive.add_sweep, sweep, names[sample_id])
    return Response(
        await run_in_threadpool(archive.close),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{frame["_id"]}.zip"'},
    )


# --- helpers ---------------------------------------------------------------------------------


def _list(values: np.ndarray | None) -> list[float | None]:
    return [] if values is None else spectra.to_list(values)


async def _load_sweep(db: Db, sweep_id: str, user: dict[str, Any]) -> dict[str, Any]:
    oid = users.parse_id(sweep_id)
    sweep = await db[data.SWEEPS].find_one({"_id": oid}) if oid else None
    if sweep is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sweep not found")
    await load_frame(db, sweep["frame"], user)
    return sweep


async def _load_batch_sweeps(
    db: Db, measurement_id: str, batch_no: int, sweep_numbers: list[int], user: dict[str, Any]
) -> list[dict[str, Any]]:
    oid = users.parse_id(measurement_id)
    query = {"measurement_id": oid, "batch_no": batch_no, "sweep_no": {"$in": sweep_numbers}}
    docs = [doc async for doc in db[data.SWEEPS].find(query).sort("sweep_no", 1)] if oid else []
    if not docs:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such sweeps")
    await load_frame(db, docs[0]["frame"], user)
    return docs


def _curve(sweep: dict[str, Any], view: View, name: str) -> tuple[spectra.Array, spectra.Array]:
    channels = {c["name"]: np.asarray(c["values"], dtype=np.float64) for c in sweep["channels"]}
    if view is View.RAW:
        if name not in channels:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"No channel {name!r}")
        return channels["energy"], channels[name]
    if name not in spectra.available(list(channels)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Spectrum {name!r} is not available")
    return channels["energy"], spectra.compute(name, channels)
