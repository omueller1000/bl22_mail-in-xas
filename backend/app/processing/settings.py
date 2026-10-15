"""The processing parameters in use: the code defaults (parameters.py) plus admin overrides.

Admins can change the scientific parameters on the XAS parameters page. Only values that differ
from the defaults are stored, so a parameter nobody changed follows the code default. Every
processing request reads the current set, so changes apply immediately.
"""

from dataclasses import dataclass, replace
from typing import Any

from app.db import Database
from app.processing.parameters import DEFAULTS, Parameters

COLLECTION = "settings"
DOC_ID = "xas_parameters"


@dataclass(frozen=True)
class Editable:
    name: str
    group: str
    label: str
    unit: str
    minimum: float
    maximum: float
    integer: bool = False
    # None is allowed and means what `none_means` says.
    none_means: str | None = None


# The scientific parameters an admin may change, with their allowed ranges. Technical and
# display settings (k grid, FFT size, plotted ranges) are changed in the code only.
EDITABLE: tuple[Editable, ...] = (
    Editable(
        "pre_start_after_first",
        "Normalisation",
        "Pre-edge starts after the first point",
        "eV",
        0,
        500,
    ),
    Editable("pre_end_below_e0", "Normalisation", "Pre-edge ends below E0", "eV", 0, 500),
    Editable("pre_order", "Normalisation", "Pre-edge polynomial order", "", 0, 3, integer=True),
    Editable("post_start_above_e0", "Normalisation", "Post-edge starts above E0", "eV", 0, 2000),
    Editable(
        "post_end_before_last",
        "Normalisation",
        "Post-edge ends before the last point",
        "eV",
        0,
        500,
    ),
    Editable("post_order", "Normalisation", "Post-edge polynomial order", "", 0, 3, integer=True),
    Editable("rbkg", "Background", "R_bkg", "Å", 0.2, 5),
    Editable("bkg_kmin", "Background", "Fit from k", "1/Å", 0, 10),
    Editable("bkg_kmax", "Background", "Fit to k", "1/Å", 1, 30, none_means="end of the data"),
    Editable("bkg_kweight", "Background", "k-weight of the fit", "", 0, 3, integer=True),
    Editable("bkg_window_dk", "Background", "Window taper dk", "1/Å", 0, 5),
    Editable("kweight", "χ(k)", "k-weight of χ(k) and the transform", "", 0, 3, integer=True),
    Editable("ft_kmin", "Fourier transform", "Window from k", "1/Å", 0, 10),
    Editable(
        "ft_kmax_before_end", "Fourier transform", "Window ends before the last k", "1/Å", 0, 10
    ),
    Editable("ft_dk", "Fourier transform", "Window taper dk", "1/Å", 0, 5),
)
BY_NAME = {e.name: e for e in EDITABLE}


def check(values: dict[str, Any]) -> dict[str, float | int | None]:
    """Validated editable values; raises ValueError with a readable message."""
    result: dict[str, float | int | None] = {}
    for name, value in values.items():
        spec = BY_NAME.get(name)
        if spec is None:
            raise ValueError(f"{name} cannot be changed")
        if value is None:
            if spec.none_means is None:
                raise ValueError(f"{spec.label}: a value is required")
            result[name] = None
            continue
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError(f"{spec.label}: a number is required")
        if spec.integer and value != int(value):
            raise ValueError(f"{spec.label}: a whole number is required")
        if not spec.minimum <= value <= spec.maximum:
            raise ValueError(f"{spec.label}: must be between {spec.minimum:g} and {spec.maximum:g}")
        result[name] = int(value) if spec.integer else float(value)
    return result


async def overrides(db: Database) -> dict[str, Any]:
    doc = await db[COLLECTION].find_one({"_id": DOC_ID})
    # Ignore values for parameters that are no longer editable (the code changed).
    return {k: v for k, v in (doc or {}).get("overrides", {}).items() if k in BY_NAME}


async def current(db: Database) -> Parameters:
    return replace(DEFAULTS, **await overrides(db))


async def save(db: Database, values: dict[str, Any]) -> None:
    """Store the given editable values; only those that differ from the defaults are kept."""
    changed = {k: v for k, v in check(values).items() if v != getattr(DEFAULTS, k)}
    merged = {**await overrides(db), **changed}
    for k in values:
        if k not in changed:
            merged.pop(k, None)  # back to the default
    await db[COLLECTION].replace_one({"_id": DOC_ID}, {"overrides": merged}, upsert=True)


async def restore_defaults(db: Database) -> None:
    await db[COLLECTION].delete_one({"_id": DOC_ID})
