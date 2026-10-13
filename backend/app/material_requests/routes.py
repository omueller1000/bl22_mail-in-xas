"""Material request endpoints (requirements §7)."""

from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, HTTPException, status
from pymongo import DESCENDING, ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession

from app import counters
from app.auth.dependencies import CurrentUser, Db, Operator, ensure_operator
from app.frames import repository as frames
from app.frames.repository import actor
from app.frames.states import FrameState
from app.material_requests.models import (
    IssueBarcodes,
    MaterialRequest,
    MaterialRequestCreate,
    Reject,
    RequestState,
    to_model,
)
from app.material_requests.repository import COLLECTION
from app.users import repository as users

router = APIRouter(prefix="/material-requests", tags=["material requests"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_request(body: MaterialRequestCreate, user: CurrentUser, db: Db) -> MaterialRequest:
    doc = {
        "number": await counters.next_value(db, COLLECTION),
        "user_id": user["_id"],
        "plates": [p.model_dump() for p in body.plates],
        "frames": body.frames,
        "comment": body.comment or None,
        "state": RequestState.SUBMITTED.value,
        "barcodes": [],
        "created_at": datetime.now(UTC),
    }
    result = await db[COLLECTION].insert_one(doc)
    doc["_id"] = result.inserted_id
    return to_model(doc, user)


@router.get("")
async def list_requests(
    user: CurrentUser, db: Db, state: RequestState | None = None, all_users: bool = False
) -> list[MaterialRequest]:
    """Own requests; Operators may list everyone's with `all_users=true`."""
    query: dict[str, Any] = {}
    if all_users:
        ensure_operator(user)
    else:
        query["user_id"] = user["_id"]
    if state:
        query["state"] = state.value
    docs = await db[COLLECTION].find(query).sort("number", DESCENDING).to_list()
    owners = await users.get_many(db, {doc["user_id"] for doc in docs})
    return [to_model(doc, owners[doc["user_id"]]) for doc in docs]


@router.get("/{request_id}")
async def get_request(request_id: str, user: CurrentUser, db: Db) -> MaterialRequest:
    doc = await _load(db, request_id)
    if doc["user_id"] != user["_id"]:
        ensure_operator(user)
    owner = await users.get_by_id(db, doc["user_id"])
    assert owner is not None
    return to_model(doc, owner)


@router.post("/{request_id}/reject")
async def reject_request(
    request_id: str, body: Reject, operator: Operator, db: Db
) -> MaterialRequest:
    doc = await db[COLLECTION].find_one_and_update(
        {"_id": _oid(request_id), "state": RequestState.SUBMITTED.value},
        {
            "$set": {
                "state": RequestState.REJECTED.value,
                "reject_reason": body.reason or None,
                "decided_at": datetime.now(UTC),
                "decided_by": actor(operator),
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    if doc is None:
        await _load(db, request_id)  # 404 if missing
        raise HTTPException(status.HTTP_409_CONFLICT, "Request is no longer open")
    owner = await users.get_by_id(db, doc["user_id"])
    assert owner is not None
    return to_model(doc, owner)


@router.post("/{request_id}/issue")
async def issue_barcodes(
    request_id: str, body: IssueBarcodes, operator: Operator, db: Db
) -> MaterialRequest:
    """Issue exactly the requested number of reserved barcodes to the requester (all or nothing).

    The request becomes fulfilled once its frames are marked shipped (frames/ship).
    """
    barcodes = body.barcodes
    if len(set(barcodes)) != len(barcodes):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Barcodes scanned twice")

    async def apply(session: AsyncClientSession) -> dict[str, Any]:
        doc = await db[COLLECTION].find_one({"_id": _oid(request_id)}, session=session)
        if doc is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
        if doc["state"] != RequestState.SUBMITTED.value:
            raise HTTPException(status.HTTP_409_CONFLICT, "Request is no longer open")
        if len(barcodes) != doc["frames"]:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Request needs exactly {doc['frames']} frames, {len(barcodes)} scanned",
            )

        found = (
            await db[frames.COLLECTION].find({"_id": {"$in": barcodes}}, session=session).to_list()
        )
        states = {f["_id"]: f["state"] for f in found}
        problems = [
            f"{code}: {'unknown barcode' if code not in states else 'already ' + states[code]}"
            for code in barcodes
            if states.get(code) != FrameState.RESERVED.value
        ]
        if problems:
            raise HTTPException(status.HTTP_409_CONFLICT, "; ".join(problems))

        moved = await frames.transition(
            db,
            session,
            barcodes,
            from_state=FrameState.RESERVED,
            to_state=FrameState.ISSUED,
            by=operator,
            extra={"owner_id": doc["user_id"], "request_id": doc["_id"]},
        )
        if moved != len(barcodes):  # changed concurrently
            raise HTTPException(status.HTTP_409_CONFLICT, "Barcodes changed, please rescan")

        update = {
            "state": RequestState.ISSUED.value,
            "barcodes": barcodes,
            "decided_at": datetime.now(UTC),
            "decided_by": actor(operator),
        }
        await db[COLLECTION].update_one({"_id": doc["_id"]}, {"$set": update}, session=session)
        return {**doc, **update}

    async with db.client.start_session() as session:
        doc = await session.with_transaction(apply)
    owner = await users.get_by_id(db, doc["user_id"])
    assert owner is not None
    return to_model(doc, owner)


def _oid(request_id: str) -> ObjectId:
    oid = users.parse_id(request_id)
    if oid is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    return oid


async def _load(db: Db, request_id: str) -> dict[str, Any]:
    doc = await db[COLLECTION].find_one({"_id": _oid(request_id)})
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    return doc
