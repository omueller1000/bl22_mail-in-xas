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

Usage (from backend/, which provides httpx):
    uv run python ../tools/fake_instrument.py queue
    uv run python ../tools/fake_instrument.py run AAAA-AACT path/to/folder-with-sweeps

Only raw sweeps are uploaded; the portal processes them itself.
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any

import httpx

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
    else:
        run(instrument, args.barcode.upper(), args.folder)


if __name__ == "__main__":
    main()
