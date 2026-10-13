"""Material requests (requirements §7): plates by type plus a number of frames."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.catalog import MAX_FRAMES_PER_REQUEST, PLATE_TYPES, frame_range
from app.frames.models import Barcode, UserRef


class Requester(UserRef):
    """The requesting user, with the email operators need to contact them."""

    email: str


class RequestState(StrEnum):
    SUBMITTED = "submitted"
    # Barcodes issued; frames are being packed.
    ISSUED = "issued"
    # All frames of the request have been shipped.
    FULFILLED = "fulfilled"
    REJECTED = "rejected"


class PlateQuantity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plate_type: str
    quantity: int = Field(ge=1, le=MAX_FRAMES_PER_REQUEST * 2)


Comment = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]


class MaterialRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plates: list[PlateQuantity] = Field(default_factory=list, max_length=len(PLATE_TYPES))
    frames: int = Field(ge=1, le=MAX_FRAMES_PER_REQUEST)
    comment: Comment | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        types = [p.plate_type for p in self.plates]
        unknown = [t for t in types if t not in PLATE_TYPES]
        if unknown:
            raise ValueError(f"unknown plate type(s): {', '.join(unknown)}")
        if len(set(types)) != len(types):
            raise ValueError("each plate type may appear only once")
        low, high = frame_range(self.plate_counts())
        if not low <= self.frames <= high:
            raise ValueError(f"for these plates, request between {low} and {high} frames")
        return self

    def plate_counts(self) -> dict[str, int]:
        return {p.plate_type: p.quantity for p in self.plates}


class Reject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Comment | None = None


class IssueBarcodes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    barcodes: list[Barcode] = Field(min_length=1, max_length=MAX_FRAMES_PER_REQUEST)


class MaterialRequest(BaseModel):
    id: str
    number: int
    user: Requester
    plates: list[PlateQuantity]
    frames: int
    comment: str | None
    state: RequestState
    reject_reason: str | None
    barcodes: list[str]
    created_at: datetime
    # When/by whom the request was issued or rejected.
    decided_at: datetime | None
    decided_by: str | None
    fulfilled_at: datetime | None


def to_model(doc: dict[str, Any], owner: dict[str, Any]) -> MaterialRequest:
    return MaterialRequest(
        id=str(doc["_id"]),
        number=doc["number"],
        user=Requester(
            id=str(owner["_id"]), name=owner["name"], orcid=owner["orcid"], email=owner["email"]
        ),
        plates=doc["plates"],
        frames=doc["frames"],
        comment=doc.get("comment"),
        state=doc["state"],
        reject_reason=doc.get("reject_reason"),
        barcodes=doc.get("barcodes", []),
        created_at=doc["created_at"],
        decided_at=doc.get("decided_at"),
        decided_by=(doc.get("decided_by") or {}).get("name"),
        fulfilled_at=doc.get("fulfilled_at"),
    )
