"""Derived spectra and merging (requirements §11.3). Computed on request, never stored."""

import re
from collections.abc import Callable, Mapping

import numpy as np
from numpy.typing import NDArray

Array = NDArray[np.float64]

_ROI = {1: re.compile(r"^roi1_\d+$"), 2: re.compile(r"^roi2_\d+$")}


def _log_ratio(a: Array, b: Array) -> Array:
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.log(a / b)


def _ratio(a: Array, b: Array) -> Array:
    with np.errstate(divide="ignore", invalid="ignore"):
        return a / b


def _roi_sum(n: int) -> Callable[[Mapping[str, Array]], Array]:
    def compute(channels: Mapping[str, Array]) -> Array:
        rois = [v for name, v in channels.items() if _ROI[n].match(name)]
        return _ratio(np.sum(rois, axis=0), channels["i0"])

    return compute


# name -> (label, needed channels or None for "i0 and at least one ROI channel", formula)
SPECTRA: dict[str, tuple[str, tuple[str, ...] | int, Callable[[Mapping[str, Array]], Array]]] = {
    "sample_trans": ("ln(i0/i1)", ("i0", "i1"), lambda c: _log_ratio(c["i0"], c["i1"])),
    "ref_trans": ("ln(i1/i2)", ("i1", "i2"), lambda c: _log_ratio(c["i1"], c["i2"])),
    "fy_norm": ("fy/i0", ("fy", "i0"), lambda c: _ratio(c["fy"], c["i0"])),
    "sdd_roi1": ("Σ roi1/i0", 1, _roi_sum(1)),
    "sdd_roi2": ("Σ roi2/i0", 2, _roi_sum(2)),
}


def available(channel_names: list[str]) -> list[str]:
    """The derived spectra that can be computed from these channels."""
    names = set(channel_names)
    result = []
    for spectrum, (_, needs, _) in SPECTRA.items():
        if isinstance(needs, int):
            ok = "i0" in names and any(_ROI[needs].match(n) for n in names)
        else:
            ok = names.issuperset(needs)
        if ok:
            result.append(spectrum)
    return result


def compute(spectrum: str, channels: Mapping[str, Array]) -> Array:
    """One derived spectrum; NaN where it is undefined (e.g. log of a non-positive ratio)."""
    _, _, formula = SPECTRA[spectrum]
    y = np.asarray(formula(channels), dtype=np.float64)
    y[~np.isfinite(y)] = np.nan
    return y


def merge(curves: list[tuple[Array, Array]]) -> tuple[Array, Array]:
    """Average curves on a common grid: the first curve's x within the range all curves cover.

    Each curve is sorted by x and linearly interpolated; undefined points (NaN) are dropped
    before interpolating.
    """
    prepared = []
    for x, y in curves:
        order = np.argsort(x, kind="stable")
        x, y = x[order], y[order]
        valid = np.isfinite(x) & np.isfinite(y)
        if valid.sum() < 2:
            continue
        prepared.append((x[valid], y[valid]))
    if not prepared:
        return np.array([]), np.array([])
    low = max(x[0] for x, _ in prepared)
    high = min(x[-1] for x, _ in prepared)
    grid = prepared[0][0]
    grid = grid[(grid >= low) & (grid <= high)]
    stacked = np.vstack([np.interp(grid, x, y) for x, y in prepared])
    return grid, stacked.mean(axis=0)


def to_list(values: Array) -> list[float | None]:
    """JSON-safe values: NaN and infinity become null."""
    return [float(v) if np.isfinite(v) else None for v in values]
