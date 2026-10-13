from datetime import datetime
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

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


class Frame(BaseModel):
    barcode: str
    state: FrameState
    owner: UserRef | None
    created_at: datetime
    updated_at: datetime
    history: list[FrameEvent]


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


class ShippingGroup(BaseModel):
    user: Recipient
    barcodes: list[str]


def user_ref(user: dict[str, Any] | None) -> UserRef | None:
    if user is None:
        return None
    return UserRef(id=str(user["_id"]), name=user["name"], orcid=user["orcid"])


def to_model(doc: dict[str, Any], owner: dict[str, Any] | None) -> Frame:
    return Frame(
        barcode=doc["_id"],
        state=doc["state"],
        owner=user_ref(owner),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
        history=[
            FrameEvent(state=e["state"], at=e["at"], by=e["actor"]["name"]) for e in doc["history"]
        ],
    )
