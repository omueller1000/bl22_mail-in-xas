"""What a user can choose for a measurement (requirements §5.3). Fixed presets for now."""

from enum import StrEnum

from pydantic import BaseModel


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


# Ti (Z = 22) to Bi (Z = 83); may be restricted to the beamline's energy range later.
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


class Element(BaseModel):
    symbol: str
    z: int


class MeasurementOptions(BaseModel):
    techniques: list[Option]
    elements: list[Element]
    edges: list[Option]
    detections: list[Option]
    beams: list[Option]


OPTIONS = MeasurementOptions(
    techniques=[
        Option(value=Technique.XANES, label="XANES"),
        Option(value=Technique.EXAFS, label="EXAFS"),
    ],
    elements=[Element(symbol=s, z=z) for s, z in ELEMENTS.items()],
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
)
