"""Samples (requirements §8.2): owned by a user, reusable in several positions."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

SampleName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]

MSDS_MAX_BYTES = 1024 * 1024  # "PDF only, < 1 MB"


class SampleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: SampleName
    description: Description = ""


class ArchiveUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    archived: bool


class Msds(BaseModel):
    filename: str
    size: int
    uploaded_at: datetime


class Sample(BaseModel):
    id: str
    name: str
    description: str
    msds: Msds | None
    archived: bool
    # Placed on a frame that was declared safe: name, description and MSDS can no longer change.
    frozen: bool
    # Whether the delete rules currently allow deleting the sample.
    deletable: bool
    # Frames the sample is placed on (at most one position per frame).
    frames: list[str]
    # Of those, the frames that have measured data of this sample.
    data_frames: list[str]
    created_at: datetime
    updated_at: datetime
