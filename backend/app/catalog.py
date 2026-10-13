"""Plate type catalog (requirements §5.1). Fixed for now; maintained in code."""

from enum import StrEnum

from fastapi import APIRouter
from pydantic import BaseModel

from app.auth.dependencies import CurrentUser

MAX_FRAMES_PER_REQUEST = 100


class Side(StrEnum):
    LEFT = "left"
    RIGHT = "right"


class PlateType(BaseModel):
    id: str
    name: str
    positions: list[str]
    # Sides of the frame the plate can be mounted on.
    sides: list[Side]
    # True if the plate spans the whole frame, so the other side must stay empty.
    blocks_other_side: bool


PLATE_TYPES: dict[str, PlateType] = {
    plate.id: plate
    for plate in [
        PlateType(
            id="8-circle",
            name="8-Circle",
            positions=list("ABCDEFGH"),
            sides=[Side.LEFT, Side.RIGHT],
            blocks_other_side=False,
        ),
        PlateType(
            id="8-slot",
            name="8-Slot",
            positions=list("ABCDEFGH"),
            sides=[Side.LEFT, Side.RIGHT],
            blocks_other_side=False,
        ),
        PlateType(
            id="6-circle-gas",
            name="6-Circle-Gas",
            positions=list("ABCDEF"),
            sides=[Side.LEFT],
            blocks_other_side=True,
        ),
    ]
}


def frame_range(plates: dict[str, int]) -> tuple[int, int]:
    """Allowed number of frames for a set of plates (requirements §7).

    Plates that block the other side need a frame each; the others fit two per frame.
    Without plates, any number of frames (at least one) may be requested.
    """
    blocking = sum(n for type_id, n in plates.items() if PLATE_TYPES[type_id].blocks_other_side)
    others = sum(plates.values()) - blocking
    total = blocking + others
    if total == 0:
        return 1, MAX_FRAMES_PER_REQUEST
    return blocking + -(-others // 2), total


router = APIRouter(tags=["catalog"])


@router.get("/plate-types")
async def list_plate_types(_: CurrentUser) -> list[PlateType]:
    return list(PLATE_TYPES.values())
