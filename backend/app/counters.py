"""Human-friendly sequence numbers (e.g. material request #12)."""

from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession

from app.db import Database

COLLECTION = "counters"


async def next_value(db: Database, name: str, session: AsyncClientSession | None = None) -> int:
    doc = await db[COLLECTION].find_one_and_update(
        {"_id": name},
        {"$inc": {"value": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
        session=session,
    )
    assert doc is not None
    return int(doc["value"])
