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


def email_confirmed(doc: dict[str, Any]) -> bool:
    # Accounts created before email confirmation existed have no flag: they count as confirmed.
    return doc.get("email_confirmed", True) is not False


def to_model(doc: dict[str, Any]) -> User:
    return User(id=str(doc["_id"]), **{k: v for k, v in doc.items() if k != "_id"})


def parse_id(user_id: str) -> ObjectId | None:
    try:
        return ObjectId(user_id)
    except InvalidId:
        return None


async def get_by_id(db: Database, user_id: ObjectId) -> dict[str, Any] | None:
    return await db[COLLECTION].find_one({"_id": user_id})


async def get_many(db: Database, user_ids: set[ObjectId]) -> dict[ObjectId, dict[str, Any]]:
    docs = await db[COLLECTION].find({"_id": {"$in": list(user_ids)}}).to_list()
    return {doc["_id"]: doc for doc in docs}


async def get_by_orcid(db: Database, orcid: str) -> dict[str, Any] | None:
    return await db[COLLECTION].find_one({"orcid": orcid})


async def create(db: Database, *, orcid: str, name: str, role: Role, profile: Profile) -> dict:
    now = datetime.now(UTC)
    doc = {
        "orcid": orcid,
        "name": name,
        "role": role.value,
        **profile.model_dump(mode="json"),
        # Confirmed with a code before the account can be used (§4.3).
        "email_confirmed": False,
        "created_at": now,
        "updated_at": now,
    }
    try:
        result = await db[COLLECTION].insert_one(doc)
    except DuplicateKeyError as exc:
        raise OrcidAlreadyRegistered(orcid) from exc
    doc["_id"] = result.inserted_id
    return doc


async def update_profile(db: Database, user: dict[str, Any], profile: Profile) -> dict | None:
    """Save the profile. A new email of a confirmed account waits in pending_email until it is
    confirmed; an unconfirmed account (still registering) simply gets the new address."""
    changes = profile.model_dump(mode="json")
    unset: dict[str, str] = {}
    new_email = changes.pop("email")
    if not email_confirmed(user):
        changes["email"] = new_email
    elif new_email.lower() == user["email"].lower():
        unset = {"pending_email": "", "email_code": ""}  # a requested change is withdrawn
    else:
        changes["pending_email"] = new_email
    update: dict[str, Any] = {"$set": {**changes, "updated_at": datetime.now(UTC)}}
    if unset:
        update["$unset"] = unset
    return await db[COLLECTION].find_one_and_update(
        {"_id": user["_id"]}, update, return_document=ReturnDocument.AFTER
    )


async def clear_pending_email(db: Database, user_id: ObjectId) -> dict | None:
    return await db[COLLECTION].find_one_and_update(
        {"_id": user_id},
        {"$unset": {"pending_email": "", "email_code": ""}},
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
