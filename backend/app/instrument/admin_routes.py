"""Admin endpoints to manage service clients and their API keys (requirements §3.4)."""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, StringConstraints
from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.auth.dependencies import Admin, Db
from app.frames.repository import actor
from app.instrument import keys
from app.users import repository as users

router = APIRouter(prefix="/service-clients", tags=["service clients"])


class ClientCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class ApiKey(BaseModel):
    id: str
    # First characters of the key, to recognize it; the full key is shown only once.
    prefix: str
    created_at: datetime
    created_by: str
    last_used_at: datetime | None
    revoked_at: datetime | None


class ServiceClient(BaseModel):
    id: str
    name: str
    created_at: datetime
    created_by: str
    keys: list[ApiKey]


class NewKey(BaseModel):
    """Returned once when a key is created."""

    key: str
    info: ApiKey


@router.get("")
async def list_clients(_: Admin, db: Db) -> list[ServiceClient]:
    clients = await db[keys.CLIENTS].find().sort("name", ASCENDING).to_list()
    all_keys = await db[keys.KEYS].find().sort("created_at", ASCENDING).to_list()
    return [_client_model(c, [k for k in all_keys if k["client_id"] == c["_id"]]) for c in clients]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_client(body: ClientCreate, admin: Admin, db: Db) -> ServiceClient:
    doc = {"name": body.name, "created_at": datetime.now(UTC), "created_by": actor(admin)}
    try:
        doc["_id"] = (await db[keys.CLIENTS].insert_one(doc)).inserted_id
    except DuplicateKeyError:
        raise HTTPException(status.HTTP_409_CONFLICT, "A client with this name exists") from None
    return _client_model(doc, [])


@router.post("/{client_id}/keys", status_code=status.HTTP_201_CREATED)
async def create_key(client_id: str, admin: Admin, db: Db) -> NewKey:
    client = await _load(db, client_id)
    key, doc = await keys.create_key(db, client["_id"], actor(admin))
    return NewKey(key=key, info=_key_model(doc))


@router.delete("/{client_id}/keys/{key_id}")
async def revoke_key(client_id: str, key_id: str, _: Admin, db: Db) -> ApiKey:
    client = await _load(db, client_id)
    oid = users.parse_id(key_id)
    doc = (
        await db[keys.KEYS].find_one_and_update(
            {"_id": oid, "client_id": client["_id"], "revoked_at": None},
            {"$set": {"revoked_at": datetime.now(UTC)}},
            return_document=ReturnDocument.AFTER,
        )
        if oid
        else None
    )
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Active key not found")
    return _key_model(doc)


async def _load(db: Db, client_id: str) -> dict[str, Any]:
    oid = users.parse_id(client_id)
    client = await db[keys.CLIENTS].find_one({"_id": oid}) if oid else None
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Service client not found")
    return client


def _key_model(doc: dict[str, Any]) -> ApiKey:
    return ApiKey(
        id=str(doc["_id"]),
        prefix=doc["prefix"],
        created_at=doc["created_at"],
        created_by=doc["created_by"]["name"],
        last_used_at=doc.get("last_used_at"),
        revoked_at=doc.get("revoked_at"),
    )


def _client_model(doc: dict[str, Any], key_docs: list[dict[str, Any]]) -> ServiceClient:
    return ServiceClient(
        id=str(doc["_id"]),
        name=doc["name"],
        created_at=doc["created_at"],
        created_by=doc["created_by"]["name"],
        keys=[_key_model(k) for k in key_docs],
    )
