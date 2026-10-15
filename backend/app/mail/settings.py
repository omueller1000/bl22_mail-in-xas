"""Admin -> Email switches: notifications on/off and an optional redirect address (§6.8)."""

from typing import Any

from pydantic import BaseModel, EmailStr

from app.db import Database

COLLECTION = "settings"
DOC_ID = "mail"


class MailSwitches(BaseModel):
    # Off: no notification emails are sent (confirmation codes still are).
    enabled: bool = True
    # Set: every notification goes to this address instead of its recipients.
    redirect_to: EmailStr | None = None


async def get(db: Database) -> MailSwitches:
    doc: dict[str, Any] = await db[COLLECTION].find_one({"_id": DOC_ID}) or {}
    return MailSwitches(**{k: v for k, v in doc.items() if k != "_id"})


async def save(db: Database, switches: MailSwitches) -> MailSwitches:
    await db[COLLECTION].replace_one({"_id": DOC_ID}, switches.model_dump(mode="json"), upsert=True)
    return switches
