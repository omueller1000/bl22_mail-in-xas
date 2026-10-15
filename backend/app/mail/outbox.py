"""The outbox: emails waiting to be sent, and a record of those that were (requirements §6.8).

mail_outbox: {_id, kind, to: [{name, email}], data, status, send_after, attempts,
              created_at, sent_at, claimed_at, error, subject, text, delivered_to,
              group_key (only while collecting)}

status: collecting (arrivals of one user, gathered before sending) -> queued -> sending ->
        sent | failed | suppressed (switched off on Admin -> Email) | not_sent (outside
        production without a redirect address)
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.db import Database

COLLECTION = "mail_outbox"
# Arrivals of one user's frames are collected for this long and sent as one email.
ARRIVAL_WINDOW = timedelta(minutes=60)


async def ensure_indexes(db: Database) -> None:
    await db[COLLECTION].create_index([("status", ASCENDING), ("send_after", ASCENDING)])
    await db[COLLECTION].create_index([("created_at", DESCENDING)])
    await db[COLLECTION].create_index(
        [("group_key", ASCENDING)],
        unique=True,
        partialFilterExpression={"status": "collecting"},
    )


def recipient(user: dict[str, Any]) -> dict[str, str]:
    return {"name": user["name"], "email": user["email"]}


async def enqueue(db: Database, kind: str, to: list[dict[str, str]], data: dict[str, Any]) -> None:
    """Queue an email for immediate sending; nothing happens without recipients."""
    if not to:
        return
    now = datetime.now(UTC)
    await db[COLLECTION].insert_one(
        {
            "kind": kind,
            "to": to,
            "data": data,
            "status": "queued",
            "send_after": now,
            "attempts": 0,
            "created_at": now,
        }
    )


async def collect_arrival(db: Database, user: dict[str, Any], barcode: str) -> None:
    """Add an arrived frame to the user's arrival email, which is sent ARRIVAL_WINDOW after
    the first arrival."""
    key = f"arrived:{user['_id']}"
    for _ in range(2):  # a second try if another request created the email meanwhile
        updated = await db[COLLECTION].find_one_and_update(
            {"group_key": key, "status": "collecting"},
            {"$addToSet": {"data.frames": barcode}},
            return_document=ReturnDocument.AFTER,
        )
        if updated:
            return
        now = datetime.now(UTC)
        try:
            await db[COLLECTION].insert_one(
                {
                    "kind": "arrived",
                    "to": [recipient(user)],
                    "data": {"name": user["name"], "frames": [barcode]},
                    "status": "collecting",
                    "group_key": key,
                    "send_after": now + ARRIVAL_WINDOW,
                    "attempts": 0,
                    "created_at": now,
                }
            )
            return
        except DuplicateKeyError:
            continue


async def recent(db: Database, limit: int = 50) -> list[dict[str, Any]]:
    return await db[COLLECTION].find().sort("created_at", DESCENDING).limit(limit).to_list()
