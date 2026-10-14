"""ZIP export of a frame's data as XDI files (requirements §11.5).

One folder per position and sample (<Location>_<SampleName>), one XDI file per raw sweep and
two per processed sweep (μ(E) and k²χ(k)), named
<Barcode>_<MeasNo>_<Location>_<Element>_<Edge>_<Type>_<BatchNo>_<SweepNo3>[_proc_mu|_proc_chi].xdi
"""

import io
import re
import zipfile
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from app import __version__

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
_TAG = re.compile(r"[^A-Za-z0-9_]+")


def safe_name(value: str, fallback: str = "sample") -> str:
    """A file-system-safe folder or file name part."""
    return _UNSAFE.sub("_", value).strip("._-") or fallback


def folder_name(position: str, sample_name: str) -> str:
    return f"{position}_{safe_name(sample_name)}"


def file_stem(sweep: dict[str, Any]) -> str:
    m = sweep["measured"]
    return "_".join(
        [
            sweep["frame"],
            str(sweep["number"]),
            sweep["position"],
            m["element"],
            m["edge"],
            m["technique"].upper(),
            str(sweep["batch_no"]),
            f"{sweep['sweep_no']:03d}",
        ]
    )


def _value(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return " ".join(str(value).split())  # one line


def _flatten(data: dict[str, Any], prefix: str = "") -> Iterable[tuple[str, Any]]:
    for key, value in data.items():
        tag = _TAG.sub("_", f"{prefix}{key}").strip("_") or "value"
        if isinstance(value, dict):
            yield from _flatten(value, f"{tag}_")
        else:
            yield tag, value


def _number(value: float | None) -> str:
    return "nan" if value is None else f"{value:.10g}"


def xdi(
    columns: list[tuple[str, str, list[float | None]]],
    fields: list[tuple[str, Any]],
    comment: str,
) -> str:
    """An XDI 1.0 file: columns are (name, unit, values); fields are ("Namespace.tag", value)."""
    lines = [f"# XDI/1.0 BL22-Mail-in-XAS/{__version__}"]
    for index, (name, unit, _) in enumerate(columns, start=1):
        lines.append(f"# Column.{index}: {name} {unit}".rstrip())
    lines += [f"# {key}: {_value(value)}" for key, value in fields if value not in (None, "")]
    lines += ["# ///", f"# {comment}", "#----", "# " + "  ".join(name for name, _, _ in columns)]
    for row in zip(*(values for _, _, values in columns), strict=True):
        lines.append("  ".join(_number(v) for v in row))
    return "\n".join(lines) + "\n"


def _common_fields(sweep: dict[str, Any], sample_name: str) -> list[tuple[str, Any]]:
    m = sweep["measured"]
    return [
        ("Element.symbol", m["element"]),
        ("Element.edge", m["edge"]),
        ("Facility.name", "SSRL"),
        ("Beamline.name", "BL22"),
        ("Sample.name", sample_name),
        ("Portal.barcode", sweep["frame"]),
        ("Portal.position", sweep["position"]),
        ("Portal.measurement_no", sweep["number"]),
        ("Portal.technique", m["technique"]),
        ("Portal.detection", m["detection"]),
        ("Portal.beam", m["beam"]),
        ("Portal.batch_no", sweep["batch_no"]),
        ("Portal.sweep_no", sweep["sweep_no"]),
        ("Portal.uploaded_at", sweep["uploaded_at"]),
    ]


def raw_xdi(sweep: dict[str, Any], sample_name: str) -> str:
    metadata = sweep.get("metadata", {})
    fields = _common_fields(sweep, sample_name)
    if isinstance(metadata.get("lattice_spacing"), int | float):
        fields.append(("Mono.d_spacing", metadata["lattice_spacing"]))
    fields += [(f"Metadata.{tag}", value) for tag, value in _flatten(metadata)]
    columns = [(c["name"], c.get("unit", ""), c["values"]) for c in sweep["channels"]]
    return xdi(columns, fields, f"Raw sweep, {sweep['frame']} {sweep['position']}")


def processed_xdis(
    sweep: dict[str, Any], processed: dict[str, Any], sample_name: str
) -> dict[str, str]:
    """{"mu": text, "chi": text}; chi only if the processed result has one."""
    fields = _common_fields(sweep, sample_name)
    fields += [(f"Processing.{tag}", v) for tag, v in _flatten(processed.get("metadata", {}))]
    fields.append(("Processing.uploaded_at", processed["uploaded_at"]))
    where = f"{sweep['frame']} {sweep['position']}"
    mu = processed["mu"]
    result = {
        "mu": xdi(
            [("energy", "eV", mu["x"]), ("mu", "", mu["y"])], fields, f"Processed mu(E), {where}"
        )
    }
    chi = processed.get("chi")
    if chi:
        result["chi"] = xdi(
            [("k", "1/Angstrom", chi["x"]), ("k2chi", "", chi["y"])],
            fields,
            f"Processed k^2-weighted chi(k), {where}",
        )
    return result


class FrameZip:
    """Collects the files of one frame's export in memory (typically well below 10 MB)."""

    def __init__(self) -> None:
        self.buffer = io.BytesIO()
        self.zip = zipfile.ZipFile(self.buffer, "w", compression=zipfile.ZIP_DEFLATED)

    def add_sweep(
        self, sweep: dict[str, Any], processed: dict[str, Any] | None, sample_name: str
    ) -> None:
        folder = folder_name(sweep["position"], sample_name)
        stem = f"{folder}/{file_stem(sweep)}"
        self.zip.writestr(f"{stem}.xdi", raw_xdi(sweep, sample_name))
        if processed:
            for kind, text in processed_xdis(sweep, processed, sample_name).items():
                self.zip.writestr(f"{stem}_proc_{kind}.xdi", text)

    def close(self) -> bytes:
        self.zip.close()
        return self.buffer.getvalue()
