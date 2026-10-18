from datetime import datetime
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from app.frames.repository import BARCODE_PATTERN, normalize_barcode
from app.frames.states import FrameState
from app.users.models import Address


def _validate_barcode(value: str) -> str:
    value = normalize_barcode(value)
    if not BARCODE_PATTERN.fullmatch(value):
        raise ValueError("barcode must look like ABCD-EFGH")
    return value


Barcode = Annotated[str, AfterValidator(_validate_barcode)]


class UserRef(BaseModel):
    id: str
    name: str
    orcid: str


class FrameEvent(BaseModel):
    state: FrameState
    at: datetime
    by: str


class Plates(BaseModel):
    """Plate type ids mounted on each side; None = empty side."""

    left: str | None = None
    right: str | None = None


class PlacedSample(BaseModel):
    position: str  # e.g. "Left-A"
    sample_id: str
    sample_name: str


class StorageLocation(BaseModel):
    container: int
    slot: int
    # When the frame was put into the slot.
    since: datetime | None = None


class SafetyDeclaration(BaseModel):
    at: datetime
    by: str


class Frame(BaseModel):
    barcode: str
    state: FrameState
    owner: UserRef | None
    note: str
    plates: Plates
    positions: list[PlacedSample]
    safety: SafetyDeclaration | None
    locked: bool
    # Internal-storage slot while the frame is in internal storage, scheduled or loaded.
    storage: StorageLocation | None
    # What is still missing before the frame can be declared safe; empty = complete.
    missing: list[str]
    # Whether measured data exists for the frame (the data viewer has something to show).
    has_data: bool
    # Incremented on every configuration change; sent back with changes to detect conflicts.
    version: int
    created_at: datetime
    updated_at: datetime
    history: list[FrameEvent]


class PlatesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    left: str | None = None
    right: str | None = None


class NoteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class PositionAssign(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    sample_id: str


class ReserveBarcodes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int = Field(ge=1, le=200)


class BarcodeList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    barcodes: list[Barcode] = Field(min_length=1, max_length=200)


class Recipient(BaseModel):
    """Contact details an operator needs to ship to a user."""

    id: str
    name: str
    orcid: str
    email: str
    phone: str
    affiliation: str
    shipping_address: Address


def user_ref(user: dict[str, Any] | None) -> UserRef | None:
    if user is None:
        return None
    return UserRef(id=str(user["_id"]), name=user["name"], orcid=user["orcid"])


def to_model(
    doc: dict[str, Any],
    owner: dict[str, Any] | None,
    sample_names: dict[Any, str],
    missing: list[str],
    has_data: bool,
) -> Frame:
    safety = doc.get("safety_declared")
    return Frame(
        barcode=doc["_id"],
        state=doc["state"],
        owner=user_ref(owner),
        note=doc.get("note", ""),
        plates=Plates(**(doc.get("plates") or {})),
        positions=[
            PlacedSample(
                position=p["position"],
                sample_id=str(p["sample_id"]),
                sample_name=sample_names.get(p["sample_id"], "(deleted sample)"),
            )
            for p in doc.get("positions", [])
        ],
        safety=SafetyDeclaration(at=safety["at"], by=safety["by"]["name"]) if safety else None,
        locked=doc.get("locked", False),
        storage=StorageLocation(**doc["storage"]) if doc.get("storage") else None,
        missing=missing,
        has_data=has_data,
        version=doc.get("version", 0),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
        history=[
            FrameEvent(state=e["state"], at=e["at"], by=e["actor"]["name"]) for e in doc["history"]
        ],
    )
