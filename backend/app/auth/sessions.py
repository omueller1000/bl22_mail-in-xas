"""Server-side sessions (requirements §3.2).

The browser holds only a random token in an HttpOnly cookie; the database stores its SHA-256
hash, so a leaked database does not leak usable sessions. A session starts as soon as ORCID
(or the dev login) has confirmed an ORCID iD. Until the account is created it has no user_id
("registration required").
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from bson import ObjectId
from pymongo import ASCENDING

from app.config import SESSION_LIFETIME
from app.db import Database
from app.roles import Role

COLLECTION = "sessions"

# Sliding expiry is extended at most once per this interval, to avoid a write per request.
_RENEW_AFTER = timedelta(days=1)


@dataclass(frozen=True)
class Session:
    token_hash: str
    orcid: str
    # Name as provided by ORCID; None if the user keeps it private.
    orcid_name: str | None
    user_id: ObjectId | None
    # Dev login only: role to grant when the account is created.
    requested_role: Role | None


async def ensure_indexes(db: Database) -> None:
    await db[COLLECTION].create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)
    await db[COLLECTION].create_index([("user_id", ASCENDING)])


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _from_doc(doc: dict[str, Any]) -> Session:
    role = doc.get("requested_role")
    return Session(
        token_hash=doc["_id"],
        orcid=doc["orcid"],
        orcid_name=doc.get("orcid_name"),
        user_id=doc.get("user_id"),
        requested_role=Role(role) if role else None,
    )


async def create(
    db: Database,
    *,
    orcid: str,
    orcid_name: str | None,
    user_id: ObjectId | None,
    requested_role: Role | None = None,
) -> str:
    """Create a session and return the token for the cookie."""
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    await db[COLLECTION].insert_one(
        {
            "_id": _hash(token),
            "orcid": orcid,
            "orcid_name": orcid_name,
            "user_id": user_id,
            "requested_role": requested_role.value if requested_role else None,
            "created_at": now,
            "renewed_at": now,
            "expires_at": now + SESSION_LIFETIME,
        }
    )
    return token


async def get(db: Database, token: str) -> Session | None:
    now = datetime.now(UTC)
    doc = await db[COLLECTION].find_one({"_id": _hash(token), "expires_at": {"$gt": now}})
    if doc is None:
        return None
    if now - doc["renewed_at"] > _RENEW_AFTER:
        await db[COLLECTION].update_one(
            {"_id": doc["_id"]},
            {"$set": {"renewed_at": now, "expires_at": now + SESSION_LIFETIME}},
        )
    return _from_doc(doc)


async def attach_user(db: Database, session: Session, user_id: ObjectId) -> None:
    await db[COLLECTION].update_one({"_id": session.token_hash}, {"$set": {"user_id": user_id}})


async def delete(db: Database, token: str) -> None:
    await db[COLLECTION].delete_one({"_id": _hash(token)})
