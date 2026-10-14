"""Process one input spectrum: normalisation, background, chi(k) and its Fourier transform.

The input is mu(E) as selected in the data viewer: one sweep's spectrum, or the merge of
several sweeps of a batch. All parameters are automatic (app.processing.parameters).
"""

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from app.processing.edges import EDGE_ENERGIES, SOURCE
from app.processing.parameters import DEFAULTS, Parameters
from app.processing.xas import (
    Array,
    Exafs,
    FourierTransform,
    Normalization,
    ProcessingError,
    extract_exafs,
    fourier_transform,
    normalize,
)


@dataclass
class Result:
    e0: float
    energy: Array
    mu: Array
    normalization: Normalization | None = None
    exafs: Exafs | None = None
    ft: FourierTransform | None = None
    # Why a step could not be done (e.g. a XANES scan has no EXAFS region).
    problems: list[str] = field(default_factory=list)


def edge_energy(element: str, edge: str) -> float:
    try:
        return float(EDGE_ENERGIES[element][edge])
    except KeyError:
        raise ProcessingError(f"No tabulated {element} {edge} edge ({SOURCE}).") from None


def process(
    energy: Array, mu: Array, element: str, edge: str, params: Parameters = DEFAULTS
) -> Result:
    """Run all steps that the data allows; later steps are skipped once one fails."""
    order = np.argsort(energy, kind="stable")
    energy, mu = energy[order], mu[order]
    valid = np.isfinite(energy) & np.isfinite(mu)
    energy, mu = energy[valid], mu[valid]
    # Continuous scans can repeat an energy; keep the first value.
    energy, first = np.unique(energy, return_index=True)
    mu = mu[first]

    result = Result(e0=edge_energy(element, edge), energy=energy, mu=mu)
    e0 = result.e0
    try:
        result.normalization = normalize(
            energy,
            mu,
            e0,
            pre_range=(energy[0] + params.pre_start_after_first, e0 - params.pre_end_below_e0),
            post_range=(
                e0 + params.post_start_above_e0,
                energy[-1] - params.post_end_before_last,
            ),
            pre_order=params.pre_order,
            post_order=params.post_order,
        )
        result.exafs = extract_exafs(
            energy,
            mu,
            e0,
            result.normalization.edge_step,
            rbkg=params.rbkg,
            kmin=params.bkg_kmin,
            kmax=params.bkg_kmax,
            fit_kweight=params.bkg_kweight,
            window_dk=params.bkg_window_dk,
            kstep=params.kstep,
            nfft=params.nfft,
        )
        k = result.exafs.k
        result.ft = fourier_transform(
            k,
            result.exafs.chi,
            kweight=params.kweight,
            kmin=params.ft_kmin,
            kmax=float(k[-1]) - params.ft_kmax_before_end,
            dk=params.ft_dk,
            nfft=params.nfft,
        )
    except ProcessingError as exc:
        result.problems.append(str(exc))
    return result


@dataclass(frozen=True)
class Curves:
    """What is plotted and exported. Fitted functions are NaN where they are not drawn."""

    energy: Array
    mu: Array
    pre_edge: Array | None  # drawn from the start up to E0 + curve_overlap
    post_edge: Array | None  # drawn from E0 - curve_overlap to the end
    background: Array | None  # at and above E0
    k: Array | None
    chi_weighted: Array | None  # k^kweight chi(k)
    ft_window: Array | None  # the Fourier transform's window on the k grid (0..1)
    r: Array | None  # up to rmax
    chir: NDArray[np.complex128] | None


def curves(result: Result, params: Parameters = DEFAULTS) -> Curves:
    energy, e0 = result.energy, result.e0
    pre = post = background = None
    if (n := result.normalization) is not None:
        pre = np.where(energy <= e0 + params.curve_overlap, n.pre_edge, np.nan)
        post = np.where(energy >= e0 - params.curve_overlap, n.post_edge, np.nan)
    k = chi = window = r = chir = None
    if (x := result.exafs) is not None:
        background = np.full_like(energy, np.nan)
        background[energy >= e0] = x.background
        k, chi = x.k, x.chi * x.k**params.kweight
    if (ft := result.ft) is not None:
        shown = ft.r <= params.rmax
        r, chir, window = ft.r[shown], ft.chir[shown], ft.window
    return Curves(energy, result.mu, pre, post, background, k, chi, window, r, chir)
