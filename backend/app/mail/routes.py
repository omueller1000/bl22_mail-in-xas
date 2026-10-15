"""Admin -> Email: switches, the recent emails and a test email (requirements §6.8)."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, EmailStr

from app.auth.dependencies import Admin, AppSettings, Db
from app.config import Environment
from app.mail import outbox
from app.mail import settings as mail_settings
from app.mail.settings import MailSwitches

router = APIRouter(prefix="/admin/mail", tags=["mail"])


class MailStatus(BaseModel):
    switches: MailSwitches
    environment: str
    # Whether the server has what it needs to send (SMTP host and sender address).
    configured: bool
    from_address: str | None
    # Outside production: where all mail goes (None: nothing is sent).
    dev_redirect: str | None


class OutboxEmail(BaseModel):
    id: str
    kind: str
    to: list[str]
    subject: str | None
    status: str
    attempts: int
    error: str | None
    created_at: datetime
    send_after: datetime
    sent_at: datetime | None
    delivered_to: list[str] | None
    # The text, outside production only (so codes can be read where nothing is sent).
    text: str | None


class TestEmail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: EmailStr


@router.get("")
async def get_mail_status(_: Admin, db: Db, settings: AppSettings) -> MailStatus:
    return await _status(db, settings)


@router.put("")
async def set_mail_switches(
    body: MailSwitches, _: Admin, db: Db, settings: AppSettings
) -> MailStatus:
    await mail_settings.save(db, body)
    return await _status(db, settings)


@router.get("/outbox")
async def list_outbox(_: Admin, db: Db, settings: AppSettings) -> list[OutboxEmail]:
    show_text = settings.environment is not Environment.PROD
    return [_email(doc, show_text) for doc in await outbox.recent(db)]


@router.post("/test", status_code=204)
async def send_test_email(body: TestEmail, admin: Admin, db: Db) -> None:
    """Queue a test email to the given address (ignores the switch and redirect)."""
    await outbox.enqueue(db, "test", [{"name": admin["name"], "email": str(body.to)}], {})


async def _status(db: Db, settings: AppSettings) -> MailStatus:
    return MailStatus(
        switches=await mail_settings.get(db),
        environment=settings.environment.value,
        configured=bool(settings.smtp_host and settings.mail_from_address),
        from_address=settings.mail_from_address,
        dev_redirect=settings.mail_dev_redirect
        if settings.environment is not Environment.PROD
        else None,
    )


def _email(doc: dict[str, Any], show_text: bool) -> OutboxEmail:
    return OutboxEmail(
        id=str(doc["_id"]),
        kind=doc["kind"],
        to=[r["email"] for r in doc["to"]],
        subject=doc.get("subject"),
        status=doc["status"],
        attempts=doc.get("attempts", 0),
        error=doc.get("error"),
        created_at=doc["created_at"],
        send_after=doc["send_after"],
        sent_at=doc.get("sent_at"),
        delivered_to=doc.get("delivered_to"),
        text=doc.get("text") if show_text else None,
    )
