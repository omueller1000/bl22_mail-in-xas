"""Sample endpoints (requirements §8.2)."""

from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Response, UploadFile, status
from gridfs.errors import NoFile
from pymongo.asynchronous.client_session import AsyncClientSession

from app.auth.dependencies import CurrentUser, Db, is_operator
from app.frames import repository as frames
from app.frames.states import TERMINAL
from app.measurements import repository as measurements
from app.samples import repository as samples
from app.samples.models import MSDS_MAX_BYTES, ArchiveUpdate, Sample, SampleInput
from app.users import repository as users

router = APIRouter(prefix="/samples", tags=["samples"])


@router.get("")
async def list_samples(user: CurrentUser, db: Db, include_archived: bool = False) -> list[Sample]:
    """Own samples, newest first."""
    docs = await samples.list_for_owner(db, user["_id"], include_archived)
    return await samples.to_models(db, docs)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_sample(body: SampleInput, user: CurrentUser, db: Db) -> Sample:
    doc = await samples.create(db, user["_id"], body)
    return (await samples.to_models(db, [doc]))[0]


@router.get("/{sample_id}")
async def get_sample(sample_id: str, user: CurrentUser, db: Db) -> Sample:
    doc = await _load(db, sample_id, user, allow_operator=True)
    return (await samples.to_models(db, [doc]))[0]


@router.put("/{sample_id}")
async def update_sample(sample_id: str, body: SampleInput, user: CurrentUser, db: Db) -> Sample:
    doc = await _load(db, sample_id, user)
    _ensure_not_frozen(doc)
    updated = await samples.update(db, doc["_id"], body.model_dump())
    assert updated is not None
    return (await samples.to_models(db, [updated]))[0]


@router.put("/{sample_id}/archived")
async def set_archived(sample_id: str, body: ArchiveUpdate, user: CurrentUser, db: Db) -> Sample:
    """Archiving only hides a sample from the picker and the default list."""
    doc = await _load(db, sample_id, user)
    updated = await samples.update(db, doc["_id"], {"archived": body.archived})
    assert updated is not None
    return (await samples.to_models(db, [updated]))[0]


@router.delete("/{sample_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sample(sample_id: str, user: CurrentUser, db: Db) -> None:
    """Permanently delete a sample without data that is not on a declared, unreturned frame."""
    doc = await _load(db, sample_id, user)
    if await samples.has_data(db, doc["_id"]):
        raise HTTPException(status.HTTP_409_CONFLICT, "Sample has data; archive it instead")

    async def remove(session: AsyncClientSession) -> None:
        placed = await samples.frames_with(db, [doc["_id"]], session=session)
        blocking = [f["_id"] for f in placed if samples.blocks_deletion(f)]
        if blocking:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Sample is on a frame declared safe: {', '.join(blocking)}",
            )
        # Free its positions on frames still being assembled (returned/void frames keep their
        # history). Measurements of those positions go with them (none can have been executed).
        for frame in placed:
            if frame["state"] in TERMINAL:
                continue
            freed = {p["position"] for p in frame["positions"] if p["sample_id"] == doc["_id"]}
            await db[frames.COLLECTION].update_one(
                {"_id": frame["_id"]},
                {"$pull": {"positions": {"sample_id": doc["_id"]}}, "$inc": {"version": 1}},
                session=session,
            )
            await measurements.delete_for_positions(db, session, frame["_id"], freed)
        await db[samples.COLLECTION].delete_one({"_id": doc["_id"]}, session=session)

    async with db.client.start_session() as session:
        await session.with_transaction(remove)
    if doc.get("msds"):
        await _delete_msds_file(db, doc["msds"]["file_id"])


# --- MSDS ----------------------------------------------------------------------------------


@router.put("/{sample_id}/msds")
async def upload_msds(sample_id: str, file: UploadFile, user: CurrentUser, db: Db) -> Sample:
    """Attach or replace the sample's material safety data sheet (PDF, < 1 MB)."""
    doc = await _load(db, sample_id, user)
    _ensure_not_frozen(doc)
    content = await file.read(MSDS_MAX_BYTES + 1)
    if len(content) > MSDS_MAX_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "MSDS must be smaller than 1 MB")
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "MSDS must be a PDF file")

    filename = _clean_filename(file.filename)
    file_id = await samples.msds_bucket(db).upload_from_stream(
        filename, content, metadata={"sample_id": doc["_id"], "content_type": "application/pdf"}
    )
    msds = {
        "file_id": file_id,
        "filename": filename,
        "size": len(content),
        "uploaded_at": datetime.now(UTC),
    }
    updated = await samples.update(db, doc["_id"], {"msds": msds})
    assert updated is not None
    if doc.get("msds"):
        await _delete_msds_file(db, doc["msds"]["file_id"])
    return (await samples.to_models(db, [updated]))[0]


@router.get(
    "/{sample_id}/msds",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def download_msds(sample_id: str, user: CurrentUser, db: Db) -> Response:
    doc = await _load(db, sample_id, user, allow_operator=True)
    if not doc.get("msds"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sample has no MSDS")
    stream = await samples.msds_bucket(db).open_download_stream(doc["msds"]["file_id"])
    content = await stream.read()
    filename = doc["msds"]["filename"]
    return Response(
        content,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.delete("/{sample_id}/msds")
async def delete_msds(sample_id: str, user: CurrentUser, db: Db) -> Sample:
    doc = await _load(db, sample_id, user)
    _ensure_not_frozen(doc)
    if doc.get("msds"):
        await _delete_msds_file(db, doc["msds"]["file_id"])
    updated = await samples.update(db, doc["_id"], {"msds": None})
    assert updated is not None
    return (await samples.to_models(db, [updated]))[0]


# --- helpers -------------------------------------------------------------------------------


async def _load(
    db: Db, sample_id: str, user: dict[str, Any], *, allow_operator: bool = False
) -> dict[str, Any]:
    """The sample, if it belongs to the user (or the user is an Operator, for reading)."""
    oid = users.parse_id(sample_id)
    doc = await samples.get(db, oid) if oid else None
    if doc is None or (
        doc["owner_id"] != user["_id"] and not (allow_operator and is_operator(user))
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sample not found")
    return doc


def _ensure_not_frozen(doc: dict[str, Any]) -> None:
    if doc["frozen"]:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Sample is on a frame declared safe and can no longer be changed",
        )


async def _delete_msds_file(db: Db, file_id: ObjectId) -> None:
    try:
        await samples.msds_bucket(db).delete(file_id)
    except NoFile:
        pass


def _clean_filename(name: str | None) -> str:
    name = (name or "msds.pdf").replace("\\", "/").rsplit("/", 1)[-1].strip() or "msds.pdf"
    return name[:200]
