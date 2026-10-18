"""Shipping page: everything that goes to a user in one box (requirements §9.3).

A box holds the user's issued material (frames and plates of their material requests) and the
frames marked "returning to user". Marking it shipped moves all of them at once.
"""

from typing import Any

from bson import ObjectId
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from pymongo.asynchronous.client_session import AsyncClientSession

from app.auth.dependencies import Db, Operator
from app.frames import repository as frames
from app.frames.models import BarcodeList, Frame, Plates, Recipient
from app.frames.states import FrameState
from app.frames.views import frame_models
from app.mail import notify
from app.material_requests import repository as material_requests
from app.material_requests.models import PlateQuantity
from app.measurements import repository as measurements
from app.measurements.models import MeasurementProgress
from app.users import repository as users

router = APIRouter(prefix="/frames", tags=["shipping"])

# Where each kind of frame goes when its box ships.
SHIPPED_STATE = {
    FrameState.ISSUED: FrameState.SHIPPED_TO_USER,
    FrameState.RETURNING_TO_USER: FrameState.RETURNED,
}


class ShipmentRequest(BaseModel):
    """A material request's part of a shipment: its plates and its issued frames."""

    id: str | None  # None: issued frames without a request
    number: int | None
    plates: list[PlateQuantity]
    barcodes: list[str]


class ReturningFrame(BaseModel):
    barcode: str
    plates: Plates
    measurements: MeasurementProgress


class ShippingGroup(BaseModel):
    user: Recipient
    requests: list[ShipmentRequest]
    returning: list[ReturningFrame]


@router.get("/shipping")
async def shipping_list(_: Operator, db: Db) -> list[ShippingGroup]:
    """Per user: issued material and returning frames still to be shipped."""
    groups = await frames.to_ship_by_owner(db)
    owners = await users.get_many(db, set(groups))
    docs = [doc for group in groups.values() for doc in group]
    request_ids = {d["request_id"] for d in docs if d["state"] == FrameState.ISSUED.value}
    request_ids.discard(None)
    requests = {
        r["_id"]: r
        async for r in db[material_requests.COLLECTION].find({"_id": {"$in": list(request_ids)}})
    }
    returning = [d["_id"] for d in docs if d["state"] == FrameState.RETURNING_TO_USER.value]
    progress = await measurements.progress_by_frame(db, returning)

    result = [
        ShippingGroup(
            user=Recipient(id=str(owner_id), **owners[owner_id]),
            requests=_requests(group, requests),
            returning=[
                ReturningFrame(
                    barcode=d["_id"],
                    plates=Plates(**d.get("plates", {})),
                    measurements=MeasurementProgress.of(progress.get(d["_id"], ({}, []))[0]),
                )
                for d in group
                if d["state"] == FrameState.RETURNING_TO_USER.value
            ],
        )
        for owner_id, group in groups.items()
    ]
    return sorted(result, key=lambda g: g.user.name)


def _requests(
    group: list[dict[str, Any]], requests: dict[ObjectId, dict[str, Any]]
) -> list[ShipmentRequest]:
    by_request: dict[ObjectId | None, list[str]] = {}
    for d in group:
        if d["state"] == FrameState.ISSUED.value:
            by_request.setdefault(d.get("request_id"), []).append(d["_id"])
    result = []
    for request_id, barcodes in by_request.items():
        request = requests.get(request_id) if request_id else None
        result.append(
            ShipmentRequest(
                id=str(request_id) if request else None,
                number=request["number"] if request else None,
                plates=request["plates"] if request else [],
                barcodes=sorted(barcodes),
            )
        )
    return sorted(result, key=lambda r: r.number or 0)


@router.post("/ship")
async def mark_shipped(body: BarcodeList, operator: Operator, db: Db) -> list[Frame]:
    """Ship a box, all or nothing: issued frames become shipped to the user, returning frames
    returned. Material requests whose frames have all shipped become fulfilled. The user gets one
    email listing the whole shipment."""
    barcodes = list(dict.fromkeys(body.barcodes))

    async def ship(session: AsyncClientSession) -> None:
        found = (
            await db[frames.COLLECTION].find({"_id": {"$in": barcodes}}, session=session).to_list()
        )
        states = {doc["_id"]: doc["state"] for doc in found}
        problems = [
            f"{code}: {states.get(code, 'unknown barcode')}"
            for code in barcodes
            if states.get(code) not in {s.value for s in SHIPPED_STATE}
        ]
        if problems:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Not ready to ship: " + "; ".join(problems)
            )
        moved = 0
        for from_state, to_state in SHIPPED_STATE.items():
            codes = [c for c in barcodes if states[c] == from_state.value]
            if codes:
                moved += await frames.transition(
                    db, session, codes, from_state=from_state, to_state=to_state, by=operator
                )
        if moved != len(barcodes):
            raise HTTPException(status.HTTP_409_CONFLICT, "Frames changed, please reload")
        await material_requests.fulfil_if_shipped(
            db,
            session,
            {
                doc["request_id"]
                for doc in found
                if doc.get("request_id") and doc["state"] == FrameState.ISSUED.value
            },
        )

    async with db.client.start_session() as session:
        await session.with_transaction(ship)
    shipped = await frames.find(db, {"_id": {"$in": barcodes}})
    await notify.shipped(db, shipped)
    return await frame_models(db, shipped)
