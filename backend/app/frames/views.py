"""Turn frame documents into API models (with owner and sample names looked up in bulk)."""

from typing import Any

from app.db import Database
from app.frames.models import Frame, to_model
from app.samples import repository as samples
from app.users import repository as users


async def frame_models(db: Database, docs: list[dict[str, Any]]) -> list[Frame]:
    owners = await users.get_many(db, {d["owner_id"] for d in docs if d.get("owner_id")})
    sample_ids = {p["sample_id"] for d in docs for p in d.get("positions", [])}
    names = {
        s["_id"]: s["name"]
        async for s in db[samples.COLLECTION].find({"_id": {"$in": list(sample_ids)}}, {"name": 1})
    }
    return [to_model(doc, owners.get(doc.get("owner_id")), names) for doc in docs]


async def frame_model(db: Database, doc: dict[str, Any]) -> Frame:
    return (await frame_models(db, [doc]))[0]
