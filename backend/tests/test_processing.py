"""XAS processing (requirements §11.3) on a synthetic spectrum with known answers."""

import numpy as np
import pytest

from app.processing import pipeline
from app.processing.edges import EDGE_ENERGIES
from app.processing.xas import ENERGY_TO_K, ProcessingError, hanning_window

CU_K = 8979.0
SHELL_R = 2.5  # Å
STEP = 0.8


def synthetic_mu(
    e0: float = CU_K, start: float = -200.0, end: float = 1000.0, height: float = STEP
) -> tuple[np.ndarray, np.ndarray]:
    """A linear pre-edge, a smooth edge of the given height, gentle post-edge decay and one
    EXAFS shell at SHELL_R (without phase shift); 0.5 eV spacing."""
    energy = np.arange(e0 + start, e0 + end, 0.5)
    k = np.sqrt(np.clip(energy - e0, 0, None) / ENERGY_TO_K)
    pre = 0.3 + 1e-5 * (energy - e0)
    edge = height * (0.5 + np.arctan((energy - e0) / 2.0) / np.pi)
    decay = -height * 1e-4 * np.clip(energy - e0, 0, None)
    chi = 0.1 * np.sin(2 * k * SHELL_R) * np.exp(-2 * k**2 * 0.003) / np.maximum(k, 1)
    return energy, pre + edge + decay + height * chi * (energy > e0)


def test_e0_comes_from_the_table() -> None:
    assert EDGE_ENERGIES["Cu"]["K"] == CU_K
    assert pipeline.edge_energy("Pb", "L3") == 13035
    with pytest.raises(ProcessingError):
        pipeline.edge_energy("Cu", "M1")


def test_full_processing_recovers_step_and_shell() -> None:
    energy, mu = synthetic_mu()
    result = pipeline.process(energy, mu, "Cu", "K")
    assert result.problems == []
    assert result.e0 == CU_K
    assert result.normalization is not None
    assert result.normalization.edge_step == pytest.approx(STEP, rel=0.05)

    curves = pipeline.curves(result)
    assert curves.chir is not None and curves.r is not None
    peak = curves.r[np.argmax(np.abs(curves.chir))]
    assert peak == pytest.approx(SHELL_R, abs=0.1)
    # The background removes the slow part: little is left below R_bkg = 1 Å.
    low = np.abs(curves.chir[curves.r < 0.8]).max()
    assert low < 0.1 * np.abs(curves.chir).max()
    # The FT window lives on the k grid, between 0 and 1.
    assert curves.ft_window is not None and curves.k is not None
    assert curves.ft_window.shape == curves.k.shape
    assert curves.ft_window.max() == 1 and curves.ft_window[curves.k < 1].max() == 0


def test_where_fitted_curves_are_drawn() -> None:
    energy, mu = synthetic_mu()
    curves = pipeline.curves(pipeline.process(energy, mu, "Cu", "K"))
    assert curves.pre_edge is not None and curves.post_edge is not None
    assert curves.background is not None
    assert not np.isnan(curves.pre_edge).any()  # the whole energy range
    assert np.isnan(curves.post_edge[energy < CU_K - 60]).all()
    assert np.isnan(curves.background[energy < CU_K]).all()
    assert np.isfinite(curves.background[energy > CU_K]).all()


def test_unsorted_input_with_repeated_energies() -> None:
    energy, mu = synthetic_mu()
    order = np.random.default_rng(1).permutation(energy.size)
    energy = np.concatenate([energy[order], energy[:5]])
    mu = np.concatenate([mu[order], mu[:5]])
    assert pipeline.process(energy, mu, "Cu", "K").problems == []


def test_xanes_scan_is_normalised_but_has_no_exafs() -> None:
    # Ends 160 eV above E0: the post-edge range (E0+150 to end-10) has no points.
    energy, mu = synthetic_mu(end=160.0)
    result = pipeline.process(energy, mu, "Cu", "K")
    assert result.normalization is None
    assert "post-edge" in result.problems[0]


def test_wrong_edge_is_reported() -> None:
    energy, mu = synthetic_mu()
    result = pipeline.process(energy, mu, "Ni", "K")  # 8333 eV: below this scan
    assert result.normalization is None
    assert "outside the data range" in result.problems[0]


def test_hanning_window_shape() -> None:
    k = np.arange(0, 10, 0.05)
    w = hanning_window(k, 2.0, 8.0, 1.0)
    assert w[k < 1.5].max() == 0
    assert w[(k > 2.5) & (k < 7.5)].min() == 1
    assert w[np.isclose(k, 2.0)][0] == pytest.approx(0.5)
