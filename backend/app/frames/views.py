"""Turn frame documents into API models (with owner and sample names looked up in bulk)."""

from typing import Any

from app.data import repository as data
from app.db import Database
from app.frames.configuration import missing_for_declaration
from app.frames.models import Frame, to_model
from app.measurements import repository as measurements
from app.samples import repository as samples
from app.users import repository as users


async def frame_models(db: Database, docs: list[dict[str, Any]]) -> list[Frame]:
    owners = await users.get_many(db, {d["owner_id"] for d in docs if d.get("owner_id")})
    sample_ids = {p["sample_id"] for d in docs for p in d.get("positions", [])}
    names = {
        s["_id"]: s["name"]
        async for s in db[samples.COLLECTION].find({"_id": {"$in": list(sample_ids)}}, {"name": 1})
    }
    barcodes = [d["_id"] for d in docs]
    counts = await measurements.counts_by_position(db, barcodes)
    with_data = await data.frames_having_data(db, barcodes)
    return [
        to_model(
            doc,
            owners.get(doc.get("owner_id")),
            names,
            missing_for_declaration(doc, counts.get(doc["_id"], {})),
            doc["_id"] in with_data,
        )
        for doc in docs
    ]


async def frame_model(db: Database, doc: dict[str, Any]) -> Frame:
    return (await frame_models(db, [doc]))[0]
