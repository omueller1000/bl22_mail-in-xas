"""Delivers the outbox: a background task in the backend, retrying when the server fails.

Where an email really goes is decided when it is sent:
- outside production, only to HT_XAS_MAIL_DEV_REDIRECT (or nowhere, recorded as not_sent);
- in production, as addressed, unless notifications are switched off (suppressed) or redirected
  on Admin -> Email. Confirmation codes always go to the address being confirmed.
"""

import asyncio
import logging
import smtplib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any

from pymongo import ASCENDING, ReturnDocument

from app.config import Environment, Settings
from app.db import Database
from app.mail import outbox
from app.mail import settings as mail_settings
from app.mail.templates import render

logger = logging.getLogger(__name__)

Transport = Callable[[EmailMessage], None]

# Kinds that ignore the switch and redirect on Admin -> Email.
ALWAYS_SENT = {"email_code", "test"}
# Wait before the 2nd, 3rd, ... attempt; after the last one the email is marked failed.
RETRY_DELAYS = [timedelta(minutes=m) for m in (1, 5, 15, 60)]
POLL_SECONDS = 5


def smtp_transport(settings: Settings) -> Transport:
    def send(message: EmailMessage) -> None:
        assert settings.smtp_host
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
            server.ehlo()
            if settings.smtp_starttls:
                server.starttls()
                server.ehlo()
            if settings.smtp_username and server.has_extn("auth"):
                password = (
                    settings.smtp_password.get_secret_value() if settings.smtp_password else ""
                )
                server.login(settings.smtp_username, password)
            server.send_message(message)

    return send


async def deliver_due(
    db: Database, settings: Settings, transport: Transport, now: datetime | None = None
) -> int:
    """Send every email that is due; returns how many were handled."""
    now = now or datetime.now(UTC)
    handled = 0
    while True:
        doc = await db[outbox.COLLECTION].find_one_and_update(
            {"status": {"$in": ["queued", "collecting"]}, "send_after": {"$lte": now}},
            {"$set": {"status": "sending", "claimed_at": now}, "$unset": {"group_key": ""}},
            sort=[("send_after", ASCENDING)],
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:
            return handled
        await _deliver(db, settings, transport, doc, now)
        handled += 1


async def _deliver(
    db: Database, settings: Settings, transport: Transport, doc: dict[str, Any], now: datetime
) -> None:
    rendered = render(doc["kind"], doc["data"], settings.portal_url)
    to = [r["email"] for r in doc["to"]]
    subject = rendered.subject
    record: dict[str, Any] = {"subject": subject, "text": rendered.text}

    async def finish(status: str, **extra: Any) -> None:
        changes = {**record, "status": status, **extra}
        if status == "sent" and doc["kind"] == "email_code":
            # The code was delivered; do not keep it readable in the database.
            changes["text"] = "(confirmation code removed after sending)"
            changes["data.code"] = None
        await db[outbox.COLLECTION].update_one({"_id": doc["_id"]}, {"$set": changes})

    if settings.environment is not Environment.PROD:
        if not settings.mail_dev_redirect:
            await finish("not_sent", error="Not production and no HT_XAS_MAIL_DEV_REDIRECT set")
            return
        subject = f"[{settings.environment.value} → {', '.join(to)}] {subject}"
        to = [settings.mail_dev_redirect]
    elif doc["kind"] not in ALWAYS_SENT:
        switch = await mail_settings.get(db)
        if not switch.enabled:
            await finish("suppressed", error="Notifications are switched off")
            return
        if switch.redirect_to:
            subject = f"[→ {', '.join(to)}] {subject}"
            to = [switch.redirect_to]

    if not (settings.smtp_host and settings.mail_from_address):
        await finish("failed", error="Mail is not configured (SMTP host or sender address)")
        return

    message = EmailMessage()
    message["From"] = formataddr((settings.mail_from_name, settings.mail_from_address))
    message["To"] = ", ".join(to)
    message["Subject"] = subject
    message["Auto-Submitted"] = "auto-generated"
    message.set_content(rendered.text)
    message.add_alternative(rendered.html, subtype="html")
    record["subject"] = subject
    try:
        await asyncio.to_thread(transport, message)
    except Exception as exc:  # noqa: BLE001 - any delivery problem is retried, then reported
        attempts = doc.get("attempts", 0) + 1
        error = f"{type(exc).__name__}: {exc}"
        if attempts > len(RETRY_DELAYS):
            await finish("failed", attempts=attempts, error=error)
        else:
            await finish(
                "queued",
                attempts=attempts,
                error=error,
                send_after=now + RETRY_DELAYS[attempts - 1],
            )
        logger.warning("Email %s not sent (attempt %d): %s", doc["_id"], attempts, error)
        return
    await finish("sent", sent_at=datetime.now(UTC), delivered_to=to, error=None)


async def run(db: Database, settings: Settings) -> None:
    """Deliver the outbox forever (started by the app; cancelled when it stops)."""
    # Emails claimed by a backend that stopped while sending are sent again.
    await db[outbox.COLLECTION].update_many({"status": "sending"}, {"$set": {"status": "queued"}})
    transport = smtp_transport(settings)
    while True:
        try:
            await deliver_due(db, settings, transport)
        except Exception:
            logger.exception("Mail sender failed; retrying")
        await asyncio.sleep(POLL_SECONDS)
