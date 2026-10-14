"""Processing parameters. Automatic for now: change the defaults here to change them everywhere.

Energies are in eV, k in 1/Å, R in Å. E0 is not a parameter: it is the tabulated edge energy
of the measured element and edge (app.processing.edges).
"""

from dataclasses import asdict, dataclass
from typing import Any

# Bump when the algorithm or a default changes, so stored or exported results can be told apart.
ALGORITHM_VERSION = 1


@dataclass(frozen=True)
class Parameters:
    # --- Normalisation: pre-edge and post-edge polynomials ---------------------------------
    # Pre-edge from this far into the spectrum (above its first point) ...
    pre_start_after_first: float = 10.0
    # ... up to this far below E0.
    pre_end_below_e0: float = 40.0
    pre_order: int = 2
    # Post-edge from this far above E0 ...
    post_start_above_e0: float = 150.0
    # ... up to this far before the end of the spectrum.
    post_end_before_last: float = 10.0
    post_order: int = 3
    # For display only: how far past E0 the fitted pre-/post-edge curves are drawn.
    curve_overlap: float = 50.0

    # --- Background: AUTOBK-like cubic spline in k ------------------------------------------
    # Fourier components of chi below this distance are minimised by the background.
    rbkg: float = 1.0
    # Range of the background fit; kmax None = end of the data.
    bkg_kmin: float = 0.5
    bkg_kmax: float | None = None
    # k-weight used while fitting the background (not the output weight).
    bkg_kweight: int = 1
    # Taper width of the Hanning window over the fit range.
    bkg_window_dk: float = 1.0
    # Spacing of the uniform k grid.
    kstep: float = 0.05

    # --- chi(k) ------------------------------------------------------------------------------
    # chi(k) is shown and exported k-weighted.
    kweight: int = 2

    # --- Fourier transform (Hanning window) --------------------------------------------------
    ft_kmin: float = 2.0
    # The window ends this far before the last k of the data, so the taper fits.
    ft_kmax_before_end: float = 1.0
    ft_dk: float = 1.0
    nfft: int = 2048
    # |chi(R)| is returned up to this distance.
    rmax: float = 6.0

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "algorithm_version": ALGORITHM_VERSION}


DEFAULTS = Parameters()
