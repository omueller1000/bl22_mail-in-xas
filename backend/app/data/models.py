"""Measured data (requirements §11): raw sweeps. Processing is computed on request."""

from datetime import datetime
from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.data import spectra
from app.measurements.options import Beam, Detection, Edge, Technique

MAX_NUMBER = 999  # batch and sweep numbers: 1-999

ChannelName = Annotated[
    str, StringConstraints(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_]+$")
]


class Channel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ChannelName  # e.g. energy, encoder, i0, roi1_3
    unit: Annotated[str, StringConstraints(max_length=20)] = ""
    values: list[float] = Field(min_length=1)


class SweepUpload(BaseModel):
    """One raw sweep as sent by the control software after measuring it."""

    model_config = ConfigDict(extra="forbid")

    batch_no: int = Field(ge=1, le=MAX_NUMBER)
    sweep_no: int = Field(ge=1, le=MAX_NUMBER)
    # Free-form: what was measured, calibrations, ROI bins, ...
    metadata: dict[str, Any] = {}
    channels: list[Channel] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _check(self) -> Self:
        names = [c.name for c in self.channels]
        if len(set(names)) != len(names):
            raise ValueError("channel names must be unique")
        if "energy" not in names:
            raise ValueError("an 'energy' channel is required")
        if len({len(c.values) for c in self.channels}) != 1:
            raise ValueError("all channels must have the same number of values")
        return self


class Measured(BaseModel):
    """What was actually measured: the measurement's settings when the sweep was uploaded."""

    technique: Technique
    element: str
    edge: Edge
    detection: Detection
    beam: Beam


class SweepInfo(BaseModel):
    id: str
    measurement_id: str
    frame: str
    position: str
    number: int  # measurement number on the position
    batch_no: int
    sweep_no: int
    measured: Measured
    points: int
    channels: list[str]
    # Derived spectra that can be computed from the channels (§11.3).
    spectra: list[str]
    uploaded_at: datetime


def sweep_info(doc: dict[str, Any]) -> SweepInfo:
    """From a sweep document with its channels, or with `channel_names` and `points` instead."""
    if "channel_names" in doc:
        names, points = doc["channel_names"], doc["points"]
    else:
        names = [c["name"] for c in doc["channels"]]
        points = len(doc["channels"][0]["values"]) if doc["channels"] else 0
    return SweepInfo(
        id=str(doc["_id"]),
        measurement_id=str(doc["measurement_id"]),
        frame=doc["frame"],
        position=doc["position"],
        number=doc["number"],
        batch_no=doc["batch_no"],
        sweep_no=doc["sweep_no"],
        measured=Measured(**doc["measured"]),
        points=points,
        channels=names,
        spectra=spectra.available(names),
        uploaded_at=doc["uploaded_at"],
    )
