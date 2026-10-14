"""Service clients (e.g. the beamline control software) and their API keys (requirements §3.4).

A key is shown once when created; the database stores only its SHA-256 hash and a short prefix
for display. Keys are sent as "Authorization: Bearer <key>" and can be revoked one by one.

service_clients: {_id, name, created_at, created_by: {orcid, name}}
api_keys:        {_id, client_id, prefix, hash, created_at, created_by, last_used_at, revoked_at}
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from bson import ObjectId
from fastapi import Depends, Header, HTTPException, status
from pymongo import ASCENDING

from app.auth.dependencies import Db
from app.db import Database

CLIENTS = "service_clients"
KEYS = "api_keys"

KEY_PREFIX = "htxas_"
SHOWN_PREFIX_LENGTH = len(KEY_PREFIX) + 6
# Recording "last used" on every request would mean a write per call; once a minute is enough.
_LAST_USED_RESOLUTION = timedelta(minutes=1)


async def ensure_indexes(db: Database) -> None:
    await db[KEYS].create_index([("hash", ASCENDING)], unique=True)
    await db[KEYS].create_index([("client_id", ASCENDING)])
    await db[CLIENTS].create_index([("name", ASCENDING)], unique=True)


def new_key() -> str:
    """A random key, e.g. htxas_3fJ...; 40 URL-safe characters after the prefix."""
    return KEY_PREFIX + secrets.token_urlsafe(30)


def hash_key(key: str) -> str:
    # Keys are long and random, so a plain (unsalted) SHA-256 is safe and allows lookup by hash.
    return hashlib.sha256(key.encode()).hexdigest()


async def create_key(db: Database, client_id: ObjectId, by: dict[str, str]) -> tuple[str, dict]:
    key = new_key()
    doc = {
        "client_id": client_id,
        "prefix": key[:SHOWN_PREFIX_LENGTH],
        "hash": hash_key(key),
        "created_at": datetime.now(UTC),
        "created_by": by,
        "last_used_at": None,
        "revoked_at": None,
    }
    doc["_id"] = (await db[KEYS].insert_one(doc)).inserted_id
    return key, doc


async def current_client(
    db: Db, authorization: Annotated[str | None, Header()] = None
) -> dict[str, Any]:
    """The service client authenticated by the request's API key (401 otherwise)."""
    scheme, _, key = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not key.startswith(KEY_PREFIX):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "API key required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    key_doc = await db[KEYS].find_one({"hash": hash_key(key.strip()), "revoked_at": None})
    client = await db[CLIENTS].find_one({"_id": key_doc["client_id"]}) if key_doc else None
    if client is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid or revoked API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    now = datetime.now(UTC)
    last = key_doc.get("last_used_at")
    if last is None or now - last > _LAST_USED_RESOLUTION:
        await db[KEYS].update_one({"_id": key_doc["_id"]}, {"$set": {"last_used_at": now}})
    return client


Instrument = Annotated[dict[str, Any], Depends(current_client)]


def client_actor(client: dict[str, Any]) -> dict[str, str]:
    """How a service client appears in frame histories and "changed by" fields."""
    return {"orcid": f"service:{client['_id']}", "name": client["name"]}
