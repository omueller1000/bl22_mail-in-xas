"""Derived spectra, merging and XDI export (requirements §11.3, §11.5); no database needed."""

import io
import math
import zipfile
from datetime import UTC, datetime

import numpy as np

from app.data import export, spectra


def test_available_spectra_depend_on_channels() -> None:
    assert spectra.available(["energy", "i0", "i1", "i2", "fy"]) == [
        "sample_trans",
        "ref_trans",
        "fy_norm",
    ]
    assert spectra.available(["energy", "i0", "roi1_1", "roi1_2"]) == ["sdd_roi1"]
    assert spectra.available(["energy", "roi1_1"]) == []  # no i0


def test_compute_spectra() -> None:
    c = {
        "i0": np.array([2.0, 4.0]),
        "i1": np.array([1.0, 0.0]),
        "roi1_1": np.array([1.0, 1.0]),
        "roi1_2": np.array([3.0, 1.0]),
    }
    trans = spectra.compute("sample_trans", c)
    assert math.isclose(trans[0], math.log(2))
    assert math.isnan(trans[1])  # i1 = 0
    assert list(spectra.compute("sdd_roi1", c)) == [2.0, 0.5]
    assert spectra.to_list(trans)[1] is None


def test_merge_averages_on_the_common_range() -> None:
    a = (np.array([0.0, 1.0, 2.0, 3.0]), np.array([0.0, 1.0, 2.0, 3.0]))
    b = (np.array([3.5, 2.5, 1.5, 0.5]), np.array([5.5, 4.5, 3.5, 2.5]))  # descending x
    x, y = spectra.merge([a, b])
    assert list(x) == [1.0, 2.0, 3.0]  # first curve's grid within [0.5, 3.0]
    assert list(y) == [2.0, 3.0, 4.0]


SWEEP = {
    "frame": "AAAA-AABC",
    "position": "Left-G",
    "number": 7,
    "batch_no": 1,
    "sweep_no": 2,
    "measured": {
        "technique": "exafs",
        "element": "V",
        "edge": "K",
        "detection": "transmission",
        "beam": "unfocused",
    },
    "metadata": {"lattice_spacing": 1.92, "encoder": {"offset": 25.3}, "note": "a\nb"},
    "channels": [
        {"name": "energy", "unit": "eV", "values": [5400.0, 5401.0]},
        {"name": "i0", "unit": "counts", "values": [1.0, 2.0]},
    ],
    "uploaded_at": datetime(2026, 10, 1, tzinfo=UTC),
}


def test_file_and_folder_names() -> None:
    assert export.file_stem(SWEEP) == "AAAA-AABC_7_Left-G_V_K_EXAFS_1_002"
    assert export.folder_name("Left-G", "V2O5 / batch #3") == "Left-G_V2O5_batch_3"
    assert export.folder_name("Left-A", "///") == "Left-A_sample"


def test_raw_xdi() -> None:
    lines = export.raw_xdi(SWEEP, "V2O5").splitlines()
    assert lines[0].startswith("# XDI/1.0 ")
    assert "# Column.1: energy eV" in lines
    assert "# Element.symbol: V" in lines
    assert "# Mono.d_spacing: 1.92" in lines
    assert "# Metadata.encoder_offset: 25.3" in lines
    assert "# Metadata.note: a b" in lines  # kept on one line
    assert lines[-3:] == ["# energy  i0", "5400  1", "5401  2"]


def test_zip_contains_raw_and_processed_files() -> None:
    processed = {
        "metadata": {"e0": 5465.0},
        "mu": {"x": [5400.0], "y": [0.1]},
        "chi": None,
        "uploaded_at": datetime(2026, 10, 2, tzinfo=UTC),
    }
    archive = export.FrameZip()
    archive.add_sweep(SWEEP, processed, "V2O5")
    names = zipfile.ZipFile(io.BytesIO(archive.close())).namelist()
    assert names == [
        "Left-G_V2O5/AAAA-AABC_7_Left-G_V_K_EXAFS_1_002.xdi",
        "Left-G_V2O5/AAAA-AABC_7_Left-G_V_K_EXAFS_1_002_proc_mu.xdi",
    ]
