"""Measurements (requirements §8.3): attached to a position, several per position."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict

from app.measurements.options import ELEMENTS, Beam, Detection, Edge, Technique


class MeasurementStatus(StrEnum):
    PENDING = "pending"
    DONE = "done"
    ERROR = "error"


def _check_element(symbol: str) -> str:
    if symbol not in ELEMENTS:
        raise ValueError("element must be one of Ti to Bi")
    return symbol


ElementSymbol = Annotated[str, AfterValidator(_check_element)]


class MeasurementInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The frame's version (measurement changes bump it, like any frame change).
    version: int
    technique: Technique
    element: ElementSymbol
    edge: Edge
    detection: Detection
    beam: Beam = Beam.UNFOCUSED


class Measurement(BaseModel):
    id: str
    frame: str
    position: str
    # 1, 2, 3, ... per position; never reused (requirements §8.3, §11.5).
    number: int
    technique: Technique
    element: str
    edge: Edge
    detection: Detection
    beam: Beam
    status: MeasurementStatus
    error_message: str | None
    # Has left "pending" at least once; executed measurements cannot be deleted.
    executed: bool
    created_at: datetime
    updated_at: datetime
    changed_by: str


def to_model(doc: dict[str, Any]) -> Measurement:
    return Measurement(
        id=str(doc["_id"]),
        frame=doc["frame"],
        position=doc["position"],
        number=doc["number"],
        technique=doc["technique"],
        element=doc["element"],
        edge=doc["edge"],
        detection=doc["detection"],
        beam=doc["beam"],
        status=doc["status"],
        error_message=doc.get("error_message"),
        executed=doc.get("executed", False),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
        changed_by=doc["changed_by"]["name"],
    )
