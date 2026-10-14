"""Measured data (requirements §11): raw sweeps and their processed results."""

from datetime import datetime
from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

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


class Curve(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: list[float] = Field(min_length=1)
    y: list[float] = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if len(self.x) != len(self.y):
            raise ValueError("x and y must have the same length")
        return self


class ProcessedUpload(BaseModel):
    """Processed result of one sweep; uploading again replaces the previous version."""

    model_config = ConfigDict(extra="forbid")

    # E0, processing parameters, ...
    metadata: dict[str, Any] = {}
    # mu(E): x = energy (eV), y = mu
    mu: Curve
    # k^2-weighted chi(k): x = k (1/Å), y = k^2 chi; not every measurement has one (e.g. XANES)
    chi: Curve | None = None


class SweepInfo(BaseModel):
    id: str
    measurement_id: str
    frame: str
    position: str
    number: int  # measurement number on the position
    batch_no: int
    sweep_no: int
    points: int
    channels: list[str]
    uploaded_at: datetime
    has_processed: bool


def sweep_info(doc: dict[str, Any], has_processed: bool) -> SweepInfo:
    return SweepInfo(
        id=str(doc["_id"]),
        measurement_id=str(doc["measurement_id"]),
        frame=doc["frame"],
        position=doc["position"],
        number=doc["number"],
        batch_no=doc["batch_no"],
        sweep_no=doc["sweep_no"],
        points=len(doc["channels"][0]["values"]) if doc["channels"] else 0,
        channels=[c["name"] for c in doc["channels"]],
        uploaded_at=doc["uploaded_at"],
        has_processed=has_processed,
    )
