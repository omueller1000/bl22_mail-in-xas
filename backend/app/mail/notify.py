"""Notification emails for frame and request events (requirements §6.8).

Called after the change has been saved. Only confirmed addresses receive notifications.
"""

from collections import defaultdict
from typing import Any

from app.data import repository as data
from app.db import Database
from app.frames import repository as frames
from app.mail import outbox
from app.measurements import repository as measurements
from app.users import repository as users


def _confirmed(user: dict[str, Any] | None) -> bool:
    return bool(user) and users.email_confirmed(user)  # type: ignore[arg-type]


async def _operators(db: Database) -> list[dict[str, str]]:
    """All Operator and Admin accounts with a confirmed address."""
    docs = await db[users.COLLECTION].find({"role": {"$in": ["operator", "admin"]}}).to_list()
    return [outbox.recipient(u) for u in docs if _confirmed(u)]


async def _owner(db: Database, frame: dict[str, Any]) -> dict[str, Any] | None:
    owner = await users.get_by_id(db, frame["owner_id"]) if frame.get("owner_id") else None
    return owner if _confirmed(owner) else None


async def material_request_submitted(
    db: Database, request: dict[str, Any], user: dict[str, Any]
) -> None:
    await outbox.enqueue(
        db,
        "material_request",
        await _operators(db),
        {
            "request_id": str(request["_id"]),
            "number": request["number"],
            "user_name": user["name"],
            "frames": request["frames"],
            "plates": request["plates"],
            "comment": request.get("comment"),
        },
    )


async def shipped(db: Database, frames: list[dict[str, Any]]) -> None:
    """One email per user, listing all of their frames in this shipment."""
    by_owner: dict[Any, list[str]] = defaultdict(list)
    for frame in frames:
        by_owner[frame.get("owner_id")].append(frame["_id"])
    for owner_id, barcodes in by_owner.items():
        owner = await users.get_by_id(db, owner_id) if owner_id else None
        if _confirmed(owner):
            assert owner is not None
            await outbox.enqueue(
                db,
                "shipped",
                [outbox.recipient(owner)],
                {"name": owner["name"], "frames": sorted(barcodes)},
            )


async def received(db: Database, frame: dict[str, Any]) -> None:
    """The frame arrived: collected into one arrival email per user."""
    if owner := await _owner(db, frame):
        await outbox.collect_arrival(db, owner, frame["_id"])


async def on_hold(db: Database, frame: dict[str, Any]) -> None:
    owner = await users.get_by_id(db, frame["owner_id"]) if frame.get("owner_id") else None
    owner_name = owner["name"] if owner else "unknown user"
    if owner and _confirmed(owner):
        await outbox.enqueue(
            db,
            "on_hold",
            [outbox.recipient(owner)],
            {"name": owner["name"], "barcode": frame["_id"]},
        )
    await outbox.enqueue(
        db,
        "on_hold_staff",
        await _operators(db),
        {"barcode": frame["_id"], "owner_name": owner_name},
    )


async def returned(db: Database, frame: dict[str, Any]) -> None:
    if owner := await _owner(db, frame):
        await outbox.enqueue(
            db,
            "returned",
            [outbox.recipient(owner)],
            {"name": owner["name"], "barcode": frame["_id"]},
        )


async def measurement_done(db: Database, barcode: str) -> None:
    """A measurement became done: if every measurement on the frame is done and has data, the
    frame is complete. Sent again when a re-measured frame completes again."""
    docs = await measurements.list_for_frame(db, barcode)
    if not docs or any(m["status"] != "done" for m in docs):
        return
    with_data = set(await db[data.SWEEPS].distinct("measurement_id", {"frame": barcode}))
    if any(m["_id"] not in with_data for m in docs):
        return
    frame = await frames.get(db, barcode)
    if frame is None:
        return
    owner = await users.get_by_id(db, frame["owner_id"]) if frame.get("owner_id") else None
    owner_name = owner["name"] if owner else "unknown user"
    if owner and _confirmed(owner):
        await outbox.enqueue(
            db,
            "frame_complete",
            [outbox.recipient(owner)],
            {"name": owner["name"], "barcode": barcode, "measurements": len(docs)},
        )
    await outbox.enqueue(
        db,
        "frame_complete_staff",
        await _operators(db),
        {"barcode": barcode, "owner_name": owner_name, "measurements": len(docs)},
    )
