"""Database access for material requests shared with other modules."""

from datetime import UTC, datetime

from bson import ObjectId
from pymongo.asynchronous.client_session import AsyncClientSession

from app.db import Database
from app.frames import repository as frames
from app.frames.states import FrameState
from app.material_requests.models import RequestState

COLLECTION = "material_requests"


async def fulfil_if_shipped(
    db: Database, session: AsyncClientSession, request_ids: set[ObjectId]
) -> None:
    """Mark issued requests as fulfilled once none of their frames is still waiting to ship."""
    waiting = await db[frames.COLLECTION].distinct(
        "request_id",
        {"request_id": {"$in": list(request_ids)}, "state": FrameState.ISSUED.value},
        session=session,
    )
    done = request_ids - set(waiting)
    if done:
        await db[COLLECTION].update_many(
            {"_id": {"$in": list(done)}, "state": RequestState.ISSUED.value},
            {"$set": {"state": RequestState.FULFILLED.value, "fulfilled_at": datetime.now(UTC)}},
            session=session,
        )
