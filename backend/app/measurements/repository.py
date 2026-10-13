"""Database access for measurements (one document per measurement, attached to a position)."""

from pymongo.asynchronous.client_session import AsyncClientSession

from app.db import Database

COLLECTION = "measurements"


async def delete_for_positions(
    db: Database, session: AsyncClientSession, barcode: str, positions: set[str]
) -> None:
    """Remove the measurements of cleared positions (only possible before they were executed)."""
    if positions:
        await db[COLLECTION].delete_many(
            {"frame": barcode, "position": {"$in": sorted(positions)}}, session=session
        )
