"""Frame and barcode endpoints: reserve, list, look up, ship (requirements §6, §9.3)."""

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status

from app.auth.dependencies import CurrentUser, Db, Operator, ensure_operator, is_operator
from app.frames import repository as frames
from app.frames.models import Frame, ReserveBarcodes
from app.frames.states import FrameState
from app.frames.views import frame_model, frame_models
from app.pagination import (
    Page,
    PageNumber,
    PageSize,
    Search,
    SortOrder,
    contains,
    find_page,
    search_text,
    starts_with,
)
from app.users import repository as users

router = APIRouter(prefix="/frames", tags=["frames"])


@router.post("/reserve", status_code=status.HTTP_201_CREATED)
async def reserve_barcodes(body: ReserveBarcodes, operator: Operator, db: Db) -> list[Frame]:
    """Generate new barcodes for printing labels (state reserved)."""
    docs = await frames.reserve(db, body.count, operator)
    return await frame_models(db, sorted(docs, key=lambda d: d["_id"]))


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
    return await frame_models(db, await frames.find(db, query))


@router.get("/all")
async def list_all_frames(
    _: Operator,
    db: Db,
    page: PageNumber = 1,
    page_size: PageSize = 50,
    q: Search = None,
    state: FrameState | None = None,
    sort: Literal["barcode"] = "barcode",
    order: SortOrder = "asc",
) -> Page[Frame]:
    """All users' frames, one page at a time (§9.5). Without `state`, reserved barcodes are left
    out (they have no owner yet). `q` matches the start of the barcode, the owner's name or the
    note."""
    query: dict[str, Any] = (
        {"state": state.value} if state else {"state": {"$ne": FrameState.RESERVED.value}}
    )
    text = search_text(q)
    if text:
        query["$or"] = [
            {"_id": starts_with(frames.normalize_barcode(text))},
            {"owner_id": {"$in": await users.ids_with_name(db, text)}},
            {"note": contains(text)},
        ]
    sort_field = {"barcode": "_id"}[sort]
    docs, total = await find_page(
        db[frames.COLLECTION], query, sort=sort_field, order=order, page=page, page_size=page_size
    )
    return Page(items=await frame_models(db, docs), total=total, page=page, page_size=page_size)


@router.get("/{barcode}")
async def get_frame(barcode: str, user: CurrentUser, db: Db) -> Frame:
    doc = await frames.get(db, frames.normalize_barcode(barcode))
    if doc is None or (doc["owner_id"] != user["_id"] and not is_operator(user)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Frame not found")
    return await frame_model(db, doc)
