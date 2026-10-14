"""Fake beamline control software, for testing the instrument API without the beamline.

It talks to the portal exactly like the real control software: with an API key, over the
instrument endpoints. Sweeps are read from legacy BL22 ASCII files (one file per sweep):

    <BARCODE>_<POSITION>_<BATCH>_<ELEMENT>_<EDGE>_<TECHNIQUE>_<SWEEP>.txt
    e.g. AAAA-AACT_Right-A_01_Cu_K_EXAFS_0001.txt

with "#"-prefixed header lines ("# Key:<TAB>Value"); the last header line names the
tab-separated columns: Encoder, Energy, ADC_01..ADC_08, Time, Gate.

Configuration (environment variables):
    HT_XAS_INSTRUMENT_KEY   API key of a service client (required)
    HT_XAS_INSTRUMENT_URL   API base, default http://127.0.0.1:8010/mail-in-xas/api

Usage (from backend/, which provides httpx and numpy):
    uv run python ../tools/fake_instrument.py queue
    uv run python ../tools/fake_instrument.py run AAAA-AACT path/to/folder-with-sweeps
    uv run python ../tools/fake_instrument.py process AAAA-AACT path/to/folder-with-sweeps

"run" uploads the raw sweeps and a crude processed result of each; "process" uploads only the
processed results (again) for sweeps that were already uploaded. The processing is a rough
stand-in for testing the portal, not a real EXAFS analysis.
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any

import httpx
import numpy as np

FILENAME = re.compile(
    r"^(?P<barcode>[A-Z]{4}-[A-Z]{4})_(?P<position>(Left|Right)-[A-Z])_(?P<batch>\d+)_"
    r"(?P<element>[A-Z][a-z]?)_(?P<edge>K|L1|L2|L3)_(?P<technique>[A-Z]+)_(?P<sweep>\d+)\.txt$"
)

# Legacy column -> (channel name, unit). ADC_01..ADC_04 are i0, i1, i2, fy in counts;
# ADC_05..ADC_08 are not connected but kept. Time and Gate are in microseconds.
COLUMNS = {
    "Energy": ("energy", "eV"),
    "Encoder": ("encoder", "counts"),
    "ADC_01": ("i0", "counts"),
    "ADC_02": ("i1", "counts"),
    "ADC_03": ("i2", "counts"),
    "ADC_04": ("fy", "counts"),
    "ADC_05": ("adc_05", "counts"),
    "ADC_06": ("adc_06", "counts"),
    "ADC_07": ("adc_07", "counts"),
    "ADC_08": ("adc_08", "counts"),
    "Time": ("time", "us"),
    "Gate": ("gate", "us"),
}


def read_legacy_sweep(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """(metadata, channels) from one legacy ASCII file."""
    header: list[str] = []
    rows: list[list[float]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("#"):
            header.append(line[1:].strip())
        elif line.strip():
            rows.append([float(v) for v in line.split("\t")])
    if not header or not rows:
        raise ValueError(f"{path.name}: no header or no data")

    columns = header[-1].split("\t")
    metadata: dict[str, Any] = {"source_file": path.name, "source_format": "legacy BL22 ASCII"}
    for line in header[:-1]:
        key, _, value = line.partition(":")
        key = re.sub(r"[^a-z0-9]+", "_", key.strip().lower()).strip("_")
        value = value.strip()
        try:
            metadata[key] = float(value)
        except ValueError:
            metadata[key] = value

    channels = []
    for index, column in enumerate(columns):
        name, unit = COLUMNS.get(column, (re.sub(r"\W+", "_", column.lower()), ""))
        channels.append({"name": name, "unit": unit, "values": [row[index] for row in rows]})
    return metadata, channels


def crude_processing(channels: list[dict[str, Any]]) -> dict[str, Any]:
    """A rough mu(E) and k^2 chi(k) from i0/i1 (transmission), only for testing the portal."""
    c = {ch["name"]: np.asarray(ch["values"], dtype=float) for ch in channels}
    order = np.argsort(c["energy"])
    energy = c["energy"][order]
    with np.errstate(divide="ignore", invalid="ignore"):
        mu = np.log(c["i0"][order] / c["i1"][order])
    ok = np.isfinite(mu)
    # Continuous scans can repeat an energy value; keep the first.
    energy, first = np.unique(energy[ok], return_index=True)
    mu = mu[ok][first]

    # E0: steepest rise of the smoothed spectrum, ignoring the first and last 10 %.
    smooth = np.convolve(mu, np.ones(5) / 5, mode="same")
    slope = np.gradient(smooth, energy)
    inner = slice(len(energy) // 10, -len(energy) // 10)
    e0 = float(energy[inner][np.argmax(slope[inner])])

    pre = energy < e0 - 30
    post = energy > e0 + 50
    pre_line = np.polyval(np.polyfit(energy[pre], mu[pre], 1), energy)
    post_fit = np.polyfit(energy[post], mu[post], 2)
    step = float(np.polyval(post_fit, e0) - np.interp(e0, energy, pre_line))
    norm = (mu - pre_line) / step

    # chi(k): normalized mu above E0 minus a smooth polynomial background in k.
    above = energy > e0 + 5
    k = np.sqrt(0.262468 * (energy[above] - e0))
    background = np.polyval(np.polyfit(k, norm[above], 4), k)
    k_grid = np.arange(np.ceil(k[0] * 20) / 20, k[-1], 0.05)
    chi = np.interp(k_grid, k, norm[above] - background)

    return {
        "metadata": {
            "e0": round(e0, 2),
            "edge_step": round(step, 5),
            "kweight": 2,
            "method": "fake_instrument crude processing (testing only)",
        },
        "mu": {"x": energy.tolist(), "y": mu.tolist()},
        "chi": {"x": k_grid.round(4).tolist(), "y": (k_grid**2 * chi).tolist()},
    }


class Instrument:
    def __init__(self, base_url: str, key: str) -> None:
        self.http = httpx.Client(
            base_url=base_url.rstrip("/") + "/instrument",
            headers={"Authorization": f"Bearer {key}"},
            timeout=60,
        )

    def call(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self.http.request(method, path, **kwargs)
        if response.is_error:
            raise SystemExit(f"{method} {path}: HTTP {response.status_code} {response.text}")
        return response.json()

    def queue(self) -> list[dict[str, Any]]:
        return self.call("GET", "/queue")

    def frame(self, barcode: str) -> dict[str, Any]:
        return self.call("GET", f"/frames/{barcode}")

    def set_state(self, barcode: str, state: str) -> dict[str, Any]:
        return self.call("POST", f"/frames/{barcode}/state", json={"state": state})

    def set_status(self, measurement_id: str, status: str, error: str | None = None) -> None:
        body = {"status": status, "error_message": error}
        self.call("PUT", f"/measurements/{measurement_id}/status", json=body)

    def upload_sweep(self, measurement_id: str, sweep: dict[str, Any]) -> dict[str, Any]:
        return self.call("POST", f"/measurements/{measurement_id}/sweeps", json=sweep)

    def upload_processed(
        self, measurement_id: str, batch: int, sweep: int, processed: dict[str, Any]
    ) -> None:
        path = f"/measurements/{measurement_id}/sweeps/{batch}/{sweep}/processed"
        self.call("PUT", path, json=processed)


def find_measurement(frame: dict[str, Any], position: str, element: str, edge: str, technique: str):
    for p in frame["positions"]:
        if p["position"] != position:
            continue
        for m in p["measurements"]:
            if (m["element"], m["edge"], m["technique"]) == (element, edge, technique.lower()):
                return m
    return None


def sweep_files(folder: Path) -> list[Path]:
    files = sorted(p for p in folder.iterdir() if FILENAME.match(p.name))
    if not files:
        raise SystemExit(f"No sweep files in {folder}")
    return files


def process(instrument: Instrument, barcode: str, folder: Path) -> None:
    """Upload (or replace) the crude processed result of already uploaded sweeps."""
    frame = instrument.frame(barcode)
    for path in sweep_files(folder):
        name = FILENAME.match(path.name)
        assert name is not None
        if name["barcode"] != barcode:
            continue
        measurement = find_measurement(
            frame, name["position"], name["element"], name["edge"], name["technique"]
        )
        if measurement is None:
            raise SystemExit(f"{path.name}: no matching measurement on {barcode}")
        _, channels = read_legacy_sweep(path)
        processed = crude_processing(channels)
        instrument.upload_processed(
            measurement["id"], int(name["batch"]), int(name["sweep"]), processed
        )
        print(f"  {path.name}: processed, E0 {processed['metadata']['e0']} eV")


def run(instrument: Instrument, barcode: str, folder: Path) -> None:
    """Schedule, load, upload all sweeps of the folder, mark done, return to storage."""
    files = sweep_files(folder)
    frame = instrument.frame(barcode)
    print(f"{barcode}: {frame['state']}, slot {frame['storage']}")

    instrument.set_state(barcode, "scheduled")
    instrument.set_state(barcode, "loaded")
    print(f"{barcode}: scheduled and loaded")

    done: set[str] = set()
    for path in files:
        name = FILENAME.match(path.name)
        assert name is not None
        if name["barcode"] != barcode:
            print(f"  skip {path.name}: other frame")
            continue
        measurement = find_measurement(
            frame, name["position"], name["element"], name["edge"], name["technique"]
        )
        if measurement is None:
            raise SystemExit(f"{path.name}: no matching measurement on {barcode}")
        metadata, channels = read_legacy_sweep(path)
        info = instrument.upload_sweep(
            measurement["id"],
            {
                "batch_no": int(name["batch"]),
                "sweep_no": int(name["sweep"]),
                "metadata": metadata,
                "channels": channels,
            },
        )
        instrument.upload_processed(
            measurement["id"], info["batch_no"], info["sweep_no"], crude_processing(channels)
        )
        done.add(measurement["id"])
        print(
            f"  {path.name}: batch {info['batch_no']}, sweep {info['sweep_no']}, "
            f"{info['points']} points"
        )

    for measurement_id in done:
        instrument.set_status(measurement_id, "done")
    instrument.set_state(barcode, "internal_storage")
    print(f"{barcode}: {len(done)} measurement(s) done, back in internal storage")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("queue", help="list frames waiting to be measured")
    run_parser = commands.add_parser("run", help="measure one frame using sweep files")
    run_parser.add_argument("barcode")
    run_parser.add_argument("folder", type=Path)
    process_parser = commands.add_parser("process", help="upload processed data of a frame")
    process_parser.add_argument("barcode")
    process_parser.add_argument("folder", type=Path)
    args = parser.parse_args()

    key = os.environ.get("HT_XAS_INSTRUMENT_KEY")
    if not key:
        sys.exit("Set HT_XAS_INSTRUMENT_KEY to a service client's API key")
    url = os.environ.get("HT_XAS_INSTRUMENT_URL", "http://127.0.0.1:8010/mail-in-xas/api")
    instrument = Instrument(url, key)

    if args.command == "queue":
        for frame in instrument.queue():
            pending = [
                f"{p['position']} {m['element']} {m['edge']} {m['technique']}"
                for p in frame["positions"]
                for m in p["measurements"]
                if m["status"] == "pending"
            ]
            slot = frame["storage"]
            print(
                f"{frame['barcode']}  container {slot['container']} slot {slot['slot']}: {pending}"
            )
    elif args.command == "process":
        process(instrument, args.barcode.upper(), args.folder)
    else:
        run(instrument, args.barcode.upper(), args.folder)


if __name__ == "__main__":
    main()
