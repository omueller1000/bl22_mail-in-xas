"""X-ray absorption spectroscopy: edge normalisation, background removal and EXAFS extraction.

The algorithms follow the standard approaches in the XAFS literature: Newville's AUTOBK for
background removal and the usual pre-edge/post-edge polynomial scheme for normalisation, as in
Athena and ParSeq-XAS. Written from the published methods; only numpy and scipy are used.

Conventions: energy in eV, k in 1/Å, R in Å. The Fourier transform follows the usual XAFS
convention

    chi(R) = 1/sqrt(pi) * integral chi(k) W(k) k^w exp(2ikR) dk
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.interpolate import BSpline

Array = NDArray[np.float64]

#: hbar^2 / (2 m_e), in eV * Å^2. k = sqrt((E - E0) / this).
ENERGY_TO_K = 3.8099821161548593


class ProcessingError(ValueError):
    """The data cannot be processed with these parameters; the message says why."""


def etok(energy: Array | float, e0: float) -> Array:
    """Photoelectron wavenumber; energies below the edge are clamped to k = 0."""
    return np.sqrt(np.maximum(np.asarray(energy, dtype=float) - e0, 0.0) / ENERGY_TO_K)


def ktoe(k: Array, e0: float) -> Array:
    """The inverse of etok."""
    return e0 + ENERGY_TO_K * np.asarray(k, dtype=float) ** 2


def hanning_window(k: Array, kmin: float, kmax: float, dk: float) -> Array:
    """A Hanning window with cosine tapers of width dk at each end.

    The taper straddles kmin and kmax, so the window is 1/2 at each and the plateau runs from
    kmin + dk/2 to kmax - dk/2.
    """
    window = np.zeros_like(k)
    dk = max(float(dk), 1e-9)
    rise = (k >= kmin - dk / 2) & (k < kmin + dk / 2)
    window[rise] = 0.5 * (1 - np.cos(np.pi * (k[rise] - kmin + dk / 2) / dk))
    window[(k >= kmin + dk / 2) & (k <= kmax - dk / 2)] = 1.0
    fall = (k > kmax - dk / 2) & (k <= kmax + dk / 2)
    window[fall] = 0.5 * (1 + np.cos(np.pi * (k[fall] - kmax + dk / 2) / dk))
    return window


def xftf(chi: Array, kstep: float, nfft: int = 2048) -> tuple[Array, NDArray[np.complex128]]:
    """Forward Fourier transform of an already windowed, k-weighted chi(k).

    chi must be on a uniform k grid of spacing kstep starting at zero. Returns the R grid and
    the complex chi(R).
    """
    padded = np.zeros(nfft, dtype=complex)
    n = min(chi.size, nfft)
    padded[:n] = chi[:n]
    chir = np.fft.fft(padded)[: nfft // 2] * kstep / np.sqrt(np.pi)
    r = np.arange(nfft // 2) * np.pi / (kstep * nfft)
    return r, chir


def _polyfit_region(
    x: Array, y: Array, lo: float, hi: float, order: int, what: str
) -> NDArray[np.float64]:
    """Least-squares polynomial over a sub-range, with a legible failure."""
    region = (x >= lo) & (x <= hi)
    if region.sum() < order + 1:
        raise ProcessingError(
            f"The {what} range {lo:.0f}-{hi:.0f} eV contains {int(region.sum())} point(s), "
            f"too few for an order-{order} polynomial."
        )
    return np.polyfit(x[region], y[region], order)


# --- normalisation ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Normalization:
    edge_step: float
    pre_edge: Array  # pre-edge polynomial, evaluated on the energy grid
    post_edge: Array  # post-edge polynomial, evaluated on the energy grid
    pre_range: tuple[float, float]
    post_range: tuple[float, float]


def normalize(
    energy: Array,
    mu: Array,
    e0: float,
    *,
    pre_range: tuple[float, float],
    post_range: tuple[float, float],
    pre_order: int,
    post_order: int,
) -> Normalization:
    """Fit the pre-edge and post-edge polynomials; the edge step is their difference at E0.

    energy must be increasing.
    """
    if energy.size < 10:
        raise ProcessingError("At least 10 points are needed to normalise a spectrum.")
    if not energy[0] < e0 < energy[-1]:
        raise ProcessingError(
            f"E0 = {e0:g} eV lies outside the data range {energy[0]:.0f}-{energy[-1]:.0f} eV."
        )
    pre = _polyfit_region(energy, mu, *pre_range, pre_order, "pre-edge")
    post = _polyfit_region(energy, mu, *post_range, post_order, "post-edge")
    edge_step = float(np.polyval(post, e0) - np.polyval(pre, e0))
    if edge_step <= 0:
        raise ProcessingError(
            f"The edge step came out as {edge_step:.3g}, which is not physical. "
            "Check the element and edge of the measurement."
        )
    return Normalization(
        edge_step=edge_step,
        pre_edge=np.polyval(pre, energy),
        post_edge=np.polyval(post, energy),
        pre_range=pre_range,
        post_range=post_range,
    )


# --- background and chi(k) -------------------------------------------------------------------


@dataclass(frozen=True)
class Exafs:
    k: Array  # uniform grid from 0
    chi: Array  # chi(k), not k-weighted
    background_energy: Array  # energies at and above E0
    background: Array  # mu0(E) on background_energy
    n_spline_coefficients: int


def _spline_basis(kgrid: Array, lo: float, hi: float, rbkg: float) -> Array:
    """Cubic B-spline basis over [lo, hi], evaluated on kgrid.

    The coefficient count follows the information content of the region being suppressed: a
    background able to follow structure below R_bkg needs about 2*R_bkg*dk/pi degrees of
    freedom. More would let it eat real EXAFS.
    """
    n_coeff = max(4, int(2 * rbkg * (hi - lo) / np.pi) + 1)
    n_breaks = max(2, n_coeff - 2)
    breaks = np.linspace(lo, hi, n_breaks)
    knots = np.concatenate([np.full(3, lo), breaks, np.full(3, hi)])
    return BSpline.design_matrix(np.clip(kgrid, lo, hi), knots, 3).toarray()


def extract_exafs(
    energy: Array,
    mu: Array,
    e0: float,
    edge_step: float,
    *,
    rbkg: float,
    kmin: float,
    kmax: float | None,
    fit_kweight: int,
    window_dk: float,
    kstep: float,
    nfft: int,
) -> Exafs:
    """Remove the atomic background (AUTOBK idea) and return chi(k).

    The background mu0 is a cubic spline in k whose coefficients minimise the Fourier
    components of chi below R_bkg; since spline and transform are both linear in the
    coefficients, this is one linear least-squares problem. Raw mu(E) works as well as
    normalised; the edge step enters only at the final division. energy must be increasing.
    """
    above = energy >= e0
    if above.sum() < 20:
        raise ProcessingError(
            f"Only {int(above.sum())} point(s) lie above E0 = {e0:g} eV; "
            "there is no EXAFS region to extract."
        )
    k_data_max = float(etok(energy[-1], e0))
    # The grid stops at or below the last measured point (overshooting puts a spike on chi).
    kgrid = np.arange(int(np.floor(k_data_max / kstep)) + 1) * kstep
    mu_k = np.interp(ktoe(kgrid, e0), energy, mu)

    kmin = max(0.0, kmin)
    kmax = min(kmax if kmax is not None else k_data_max, k_data_max)
    if kmax - kmin < 1.0:
        raise ProcessingError(
            f"The background fit range k = {kmin:g}-{kmax:.2f} 1/Å is shorter than 1 1/Å; "
            f"the data reach k = {k_data_max:.2f} 1/Å."
        )
    # The spline lives exactly on the window's support, so every coefficient is constrained.
    dkw = max(window_dk, 1e-6)
    fit_lo = max(0.0, kmin - dkw / 2)
    fit_hi = min(k_data_max, kmax + dkw / 2)
    support = (kgrid >= fit_lo) & (kgrid <= fit_hi)
    if support.sum() < 10:
        raise ProcessingError("The background fit window spans fewer than 10 grid points.")

    basis_sub = _spline_basis(kgrid[support], fit_lo, fit_hi, rbkg)
    basis = np.zeros((kgrid.size, basis_sub.shape[1]))
    basis[support] = basis_sub
    weight = hanning_window(kgrid, kmin, kmax, dkw) * kgrid**fit_kweight

    n_r = max(2, int(np.ceil(rbkg * nfft * kstep / np.pi)))

    def low_r(values: Array) -> Array:
        _, chir = xftf(values * weight / edge_step, kstep, nfft)
        return np.concatenate([chir[:n_r].real, chir[:n_r].imag])

    design = np.column_stack([low_r(basis[:, j]) for j in range(basis.shape[1])])
    coeffs, *_ = np.linalg.lstsq(design, low_r(mu_k), rcond=None)

    # Outside the window no EXAFS is claimed: the background follows the data, chi is zero.
    mu0_k = mu_k.copy()
    mu0_k[support] = basis_sub @ coeffs
    chi = (mu_k - mu0_k) / edge_step
    background = np.interp(energy[above], ktoe(kgrid, e0), mu0_k)
    return Exafs(
        k=kgrid,
        chi=chi,
        background_energy=energy[above],
        background=background,
        n_spline_coefficients=basis.shape[1],
    )


# --- Fourier transform -----------------------------------------------------------------------


@dataclass(frozen=True)
class FourierTransform:
    r: Array
    chir: NDArray[np.complex128]
    window: Array  # on the k grid
    kmin: float
    kmax: float


def fourier_transform(
    k: Array, chi: Array, *, kweight: int, kmin: float, kmax: float, dk: float, nfft: int
) -> FourierTransform:
    """chi(R) of k^w chi(k) through a Hanning window; k must be uniform from 0."""
    if kmax - kmin <= dk:
        raise ProcessingError(
            f"The Fourier transform range k = {kmin:g}-{kmax:.2f} 1/Å is too short "
            f"for a window taper of {dk:g} 1/Å."
        )
    kstep = float(k[1] - k[0])
    window = hanning_window(k, kmin, kmax, dk)
    r, chir = xftf(chi * k**kweight * window, kstep, nfft)
    return FourierTransform(r=r, chir=chir, window=window, kmin=kmin, kmax=kmax)
