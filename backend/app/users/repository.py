"""Database access for the users collection."""

from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.db import Database
from app.roles import Role
from app.users.models import Profile, User

COLLECTION = "users"


class OrcidAlreadyRegistered(Exception):
    pass


async def ensure_indexes(db: Database) -> None:
    await db[COLLECTION].create_index([("orcid", ASCENDING)], unique=True)


def to_model(doc: dict[str, Any]) -> User:
    return User(id=str(doc["_id"]), **{k: v for k, v in doc.items() if k != "_id"})


def parse_id(user_id: str) -> ObjectId | None:
    try:
        return ObjectId(user_id)
    except InvalidId:
        return None


async def get_by_id(db: Database, user_id: ObjectId) -> dict[str, Any] | None:
    return await db[COLLECTION].find_one({"_id": user_id})


async def get_by_orcid(db: Database, orcid: str) -> dict[str, Any] | None:
    return await db[COLLECTION].find_one({"orcid": orcid})


async def create(db: Database, *, orcid: str, name: str, role: Role, profile: Profile) -> dict:
    now = datetime.now(UTC)
    doc = {
        "orcid": orcid,
        "name": name,
        "role": role.value,
        **profile.model_dump(mode="json"),
        "created_at": now,
        "updated_at": now,
    }
    try:
        result = await db[COLLECTION].insert_one(doc)
    except DuplicateKeyError as exc:
        raise OrcidAlreadyRegistered(orcid) from exc
    doc["_id"] = result.inserted_id
    return doc


async def update_profile(db: Database, user_id: ObjectId, profile: Profile) -> dict | None:
    return await db[COLLECTION].find_one_and_update(
        {"_id": user_id},
        {"$set": {**profile.model_dump(mode="json"), "updated_at": datetime.now(UTC)}},
        return_document=ReturnDocument.AFTER,
    )


async def set_role(db: Database, user_id: ObjectId, role: Role) -> dict | None:
    return await db[COLLECTION].find_one_and_update(
        {"_id": user_id},
        {"$set": {"role": role.value, "updated_at": datetime.now(UTC)}},
        return_document=ReturnDocument.AFTER,
    )


async def list_all(db: Database) -> list[dict[str, Any]]:
    return await db[COLLECTION].find().sort("name", ASCENDING).to_list()
