"""Frame and barcode endpoints for M2: reserve, list, look up, ship (requirements §6, §9.3)."""

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pymongo.asynchronous.client_session import AsyncClientSession

from app.auth.dependencies import CurrentUser, Db, Operator, ensure_operator, is_operator
from app.frames import repository as frames
from app.frames.models import (
    BarcodeList,
    Frame,
    Recipient,
    ReserveBarcodes,
    ShippingGroup,
    to_model,
)
from app.frames.states import FrameState
from app.material_requests import repository as material_requests
from app.users import repository as users

router = APIRouter(prefix="/frames", tags=["frames"])


@router.post("/reserve", status_code=status.HTTP_201_CREATED)
async def reserve_barcodes(body: ReserveBarcodes, operator: Operator, db: Db) -> list[Frame]:
    """Generate new barcodes for printing labels (state reserved)."""
    docs = await frames.reserve(db, body.count, operator)
    return [to_model(doc, None) for doc in sorted(docs, key=lambda d: d["_id"])]


@router.get("")
async def list_frames(
    user: CurrentUser, db: Db, state: FrameState | None = None, all_users: bool = False
) -> list[Frame]:
    """Own frames; Operators may list all frames with `all_users=true`."""
    query: dict[str, Any] = {}
    if all_users:
        ensure_operator(user)
    else:
        query["owner_id"] = user["_id"]
    if state:
        query["state"] = state.value
    docs = await frames.find(db, query)
    owners = await users.get_many(db, {d["owner_id"] for d in docs if d["owner_id"]})
    return [to_model(doc, owners.get(doc["owner_id"])) for doc in docs]


@router.get("/shipping")
async def shipping_list(_: Operator, db: Db) -> list[ShippingGroup]:
    """Issued but not yet shipped frames, grouped by user, with shipping details (§9.3)."""
    groups = await frames.issued_by_owner(db)
    owners = await users.get_many(db, set(groups))
    result = [
        ShippingGroup(
            user=Recipient(id=str(owner_id), **owners[owner_id]),
            barcodes=[doc["_id"] for doc in docs],
        )
        for owner_id, docs in groups.items()
    ]
    return sorted(result, key=lambda group: group.user.name)


@router.post("/ship")
async def mark_shipped(body: BarcodeList, operator: Operator, db: Db) -> list[Frame]:
    """Mark issued frames as shipped to their users (all or nothing).

    Material requests whose frames have all shipped become fulfilled.
    """
    barcodes = list(dict.fromkeys(body.barcodes))

    async def ship(session: AsyncClientSession) -> None:
        found = (
            await db[frames.COLLECTION].find({"_id": {"$in": barcodes}}, session=session).to_list()
        )
        states = {doc["_id"]: doc["state"] for doc in found}
        problems = [
            f"{code}: {'unknown barcode' if code not in states else states[code]}"
            for code in barcodes
            if states.get(code) != FrameState.ISSUED.value
        ]
        if problems:
            raise HTTPException(status.HTTP_409_CONFLICT, "Not issued: " + "; ".join(problems))
        moved = await frames.transition(
            db,
            session,
            barcodes,
            from_state=FrameState.ISSUED,
            to_state=FrameState.SHIPPED_TO_USER,
            by=operator,
        )
        if moved != len(barcodes):
            raise HTTPException(status.HTTP_409_CONFLICT, "Frames changed, please reload")
        await material_requests.fulfil_if_shipped(
            db, session, {doc["request_id"] for doc in found if doc.get("request_id")}
        )

    async with db.client.start_session() as session:
        await session.with_transaction(ship)
    docs = await frames.find(db, {"_id": {"$in": barcodes}})
    owners = await users.get_many(db, {d["owner_id"] for d in docs})
    return [to_model(doc, owners.get(doc["owner_id"])) for doc in docs]


@router.get("/{barcode}")
async def get_frame(barcode: str, user: CurrentUser, db: Db) -> Frame:
    doc = await frames.get(db, frames.normalize_barcode(barcode))
    if doc is None or (doc["owner_id"] != user["_id"] and not is_operator(user)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Frame not found")
    owner = await users.get_by_id(db, doc["owner_id"]) if doc["owner_id"] else None
    return to_model(doc, owner)
