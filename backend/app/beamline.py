"""The beamline's energy range: which elements and edges can be measured (Admin -> Beamline).

An edge can be measured if its energy E0 lies within the range (requirements §5.3). The defaults
are those of BL 2-2; admins can change them without a restart. Only values that differ from the
defaults are stored, like the XAS parameters (app.processing.settings).
"""

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict

from app.auth.dependencies import Admin, Db
from app.db import Database
from app.processing.edges import EDGE_ENERGIES

COLLECTION = "settings"
DOC_ID = "beamline"

DEFAULT_ENERGY_MIN = 4700.0  # eV
DEFAULT_ENERGY_MAX = 33000.0  # eV
# What the form accepts at all.
LIMIT_LOW = 100.0
LIMIT_HIGH = 200000.0


class EnergyRange(BaseModel):
    energy_min: float
    energy_max: float

    def contains(self, energy: float) -> bool:
        return self.energy_min <= energy <= self.energy_max


DEFAULTS = EnergyRange(energy_min=DEFAULT_ENERGY_MIN, energy_max=DEFAULT_ENERGY_MAX)


async def energy_range(db: Database) -> EnergyRange:
    doc = await db[COLLECTION].find_one({"_id": DOC_ID}) or {}
    return EnergyRange(
        energy_min=doc.get("energy_min", DEFAULT_ENERGY_MIN),
        energy_max=doc.get("energy_max", DEFAULT_ENERGY_MAX),
    )


def edge_energy(element: str, edge: str) -> float | None:
    return EDGE_ENERGIES.get(element, {}).get(edge)


def out_of_range_message(element: str, edge: str, allowed: EnergyRange) -> str | None:
    """Why the edge cannot be measured, or None if it can."""
    energy = edge_energy(element, edge)
    if energy is None:
        return f"No edge energy known for {element} {edge}"
    if allowed.contains(energy):
        return None
    return (
        f"{element} {edge} ({energy:g} eV) is outside the beamline's energy range "
        f"{allowed.energy_min / 1000:g}–{allowed.energy_max / 1000:g} keV"
    )


# --- Admin page --------------------------------------------------------------------------------

router = APIRouter(prefix="/admin/beamline", tags=["beamline"])


class BeamlineSettings(BaseModel):
    energy_min: float
    energy_max: float
    default_min: float
    default_max: float
    # How many element/edge combinations the range allows (out of all in the table).
    edges_available: int
    edges_total: int


class BeamlineUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    energy_min: float
    energy_max: float


@router.get("")
async def get_beamline(_: Admin, db: Db) -> BeamlineSettings:
    return _settings(await energy_range(db))


@router.put("")
async def set_beamline(body: BeamlineUpdate, _: Admin, db: Db) -> BeamlineSettings:
    """Change the energy range; applies to new and changed measurements from now on."""
    if not LIMIT_LOW <= body.energy_min < body.energy_max <= LIMIT_HIGH:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"The minimum must be below the maximum, both between {LIMIT_LOW:g} and "
            f"{LIMIT_HIGH:g} eV",
        )
    changed: dict[str, Any] = {
        key: value
        for key, value, default in (
            ("energy_min", body.energy_min, DEFAULT_ENERGY_MIN),
            ("energy_max", body.energy_max, DEFAULT_ENERGY_MAX),
        )
        if value != default
    }
    await db[COLLECTION].replace_one({"_id": DOC_ID}, changed, upsert=True)
    return _settings(await energy_range(db))


@router.delete("")
async def restore_beamline(_: Admin, db: Db) -> BeamlineSettings:
    """Back to the BL 2-2 defaults in the code."""
    await db[COLLECTION].delete_one({"_id": DOC_ID})
    return _settings(DEFAULTS)


def _settings(allowed: EnergyRange) -> BeamlineSettings:
    energies = [e for edges in EDGE_ENERGIES.values() for e in edges.values()]
    return BeamlineSettings(
        energy_min=allowed.energy_min,
        energy_max=allowed.energy_max,
        default_min=DEFAULT_ENERGY_MIN,
        default_max=DEFAULT_ENERGY_MAX,
        edges_available=sum(allowed.contains(e) for e in energies),
        edges_total=len(energies),
    )
