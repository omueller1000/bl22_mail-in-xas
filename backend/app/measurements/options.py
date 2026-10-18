"""What a user can choose for a measurement (requirements §5.3). Fixed presets, except that
elements and edges are limited to the beamline's energy range (app.beamline)."""

from enum import StrEnum

from pydantic import BaseModel

from app.processing.edges import EDGE_ENERGIES


class Technique(StrEnum):
    XANES = "xanes"
    EXAFS = "exafs"


class Edge(StrEnum):
    K = "K"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


class Detection(StrEnum):
    TRANSMISSION = "transmission"
    TRANSMISSION_TFY = "transmission_tfy"
    TRANSMISSION_SDD = "transmission_sdd"


class Beam(StrEnum):
    UNFOCUSED = "unfocused"
    FOCUSED = "focused"


# Ti (Z = 22) to Bi (Z = 83), further limited by the beamline's energy range.
_SYMBOLS = (
    "Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb "
    "Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl "
    "Pb Bi"
).split()
FIRST_Z = 22
ELEMENTS: dict[str, int] = {symbol: FIRST_Z + i for i, symbol in enumerate(_SYMBOLS)}


class Option(BaseModel):
    value: str
    label: str


class ElementEdge(BaseModel):
    edge: Edge
    energy: float  # eV


class Element(BaseModel):
    symbol: str
    z: int
    # The element's edges within the beamline's energy range (at least one).
    edges: list[ElementEdge]


class MeasurementOptions(BaseModel):
    techniques: list[Option]
    # Only elements with an edge in the beamline's energy range.
    elements: list[Element]
    edges: list[Option]
    detections: list[Option]
    beams: list[Option]
    energy_min: float  # eV
    energy_max: float  # eV


def options_for(energy_min: float, energy_max: float) -> MeasurementOptions:
    elements = []
    for symbol, z in ELEMENTS.items():
        energies = EDGE_ENERGIES.get(symbol, {})
        edges = [
            ElementEdge(edge=edge, energy=energies[edge.value])
            for edge in Edge
            if edge.value in energies and energy_min <= energies[edge.value] <= energy_max
        ]
        if edges:
            elements.append(Element(symbol=symbol, z=z, edges=edges))
    return _PRESETS.model_copy(
        update={"elements": elements, "energy_min": energy_min, "energy_max": energy_max}
    )


_PRESETS = MeasurementOptions(
    techniques=[
        Option(value=Technique.XANES, label="XANES"),
        Option(value=Technique.EXAFS, label="EXAFS"),
    ],
    elements=[],
    edges=[Option(value=e, label=e.value) for e in Edge],
    detections=[
        Option(value=Detection.TRANSMISSION, label="Transmission"),
        Option(value=Detection.TRANSMISSION_TFY, label="Transmission + TFY"),
        Option(value=Detection.TRANSMISSION_SDD, label="Transmission + SDD"),
    ],
    beams=[
        Option(value=Beam.UNFOCUSED, label="Unfocused"),
        Option(value=Beam.FOCUSED, label="Focused"),
    ],
    energy_min=0,
    energy_max=0,
)
