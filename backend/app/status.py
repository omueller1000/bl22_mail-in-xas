"""Admin -> Status: the state of the system, for now the MongoDB capacity.

Uses only commands the app's own database user may run (dbStats, $collStats, buildInfo):
the disk figures are those of the filesystem holding MongoDB's data directory, which other
databases on that server share.
"""

import logging
from datetime import UTC, datetime, timedelta

import pymongo
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from pymongo.errors import PyMongoError

from app import __version__
from app.auth.dependencies import Admin, AppSettings, Db
from app.data.repository import SWEEPS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/status", tags=["status"])

GROWTH_DAYS = 30


class Disk(BaseModel):
    used_bytes: int
    total_bytes: int


class CollectionSize(BaseModel):
    name: str
    documents: int
    # Uncompressed size of the documents, and what they and the indexes take on disk.
    data_bytes: int
    storage_bytes: int
    index_bytes: int


class Growth(BaseModel):
    days: int
    sweeps: int
    # Estimated disk space those sweeps take (average stored size per sweep).
    bytes: int
    # At that rate, until the disk is full; None if nothing was uploaded.
    days_until_full: float | None


class DatabaseStatus(BaseModel):
    name: str
    mongodb_version: str
    disk: Disk
    data_bytes: int
    storage_bytes: int
    index_bytes: int
    collections: list[CollectionSize]
    growth: Growth


class SystemStatus(BaseModel):
    version: str
    environment: str
    checked_at: datetime
    database: DatabaseStatus


@router.get("")
async def get_status(_: Admin, db: Db, settings: AppSettings) -> SystemStatus:
    try:
        with pymongo.timeout(10):
            database = await _database(db)
    except PyMongoError as exc:
        logger.warning("MongoDB status failed: %s: %s", type(exc).__name__, exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"MongoDB: {type(exc).__name__}: {exc}"
        ) from None
    return SystemStatus(
        version=__version__,
        environment=settings.environment.value,
        checked_at=datetime.now(UTC),
        database=database,
    )


async def _database(db: Db) -> DatabaseStatus:
    stats = await db.command("dbStats")
    build = await db.command("buildInfo")
    collections = [await _collection(db, name) for name in await _collection_names(db)]
    collections.sort(key=lambda c: c.storage_bytes + c.index_bytes, reverse=True)
    disk = Disk(used_bytes=int(stats["fsUsedSize"]), total_bytes=int(stats["fsTotalSize"]))
    return DatabaseStatus(
        name=db.name,
        mongodb_version=build["version"],
        disk=disk,
        data_bytes=int(stats["dataSize"]),
        storage_bytes=int(stats["storageSize"]),
        index_bytes=int(stats["indexSize"]),
        collections=collections,
        growth=await _growth(db, collections, disk),
    )


async def _collection_names(db: Db) -> list[str]:
    cursor = await db.list_collections(filter={"type": "collection"})
    return [c["name"] async for c in cursor]


async def _collection(db: Db, name: str) -> CollectionSize:
    cursor = await db[name].aggregate([{"$collStats": {"storageStats": {}}}])
    storage = (await cursor.to_list())[0]["storageStats"]
    return CollectionSize(
        name=name,
        documents=int(storage["count"]),
        data_bytes=int(storage["size"]),
        storage_bytes=int(storage["storageSize"]),
        index_bytes=int(storage["totalIndexSize"]),
    )


async def _growth(db: Db, collections: list[CollectionSize], disk: Disk) -> Growth:
    """Space taken by the sweeps uploaded recently; the measured data is what fills the disk."""
    since = datetime.now(UTC) - timedelta(days=GROWTH_DAYS)
    recent = await db[SWEEPS].count_documents({"uploaded_at": {"$gte": since}})
    sweeps = next((c for c in collections if c.name == SWEEPS), None)
    per_sweep = (
        (sweeps.storage_bytes + sweeps.index_bytes) / sweeps.documents
        if sweeps and sweeps.documents
        else 0
    )
    grown = round(recent * per_sweep)
    free = max(disk.total_bytes - disk.used_bytes, 0)
    return Growth(
        days=GROWTH_DAYS,
        sweeps=recent,
        bytes=grown,
        days_until_full=free / (grown / GROWTH_DAYS) if grown else None,
    )
