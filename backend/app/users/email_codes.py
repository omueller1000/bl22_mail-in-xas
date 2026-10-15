"""Email confirmation with a 6-digit code (requirements §4.3).

users.email_code: {hash, email, expires_at, attempts, sent_at}: the open confirmation, for the
address in `email` (a new account's email, or the requested new address in pending_email).
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo import ReturnDocument

from app.db import Database
from app.mail import outbox
from app.users.repository import COLLECTION

CODE_LIFETIME = timedelta(minutes=60)
MAX_ATTEMPTS = 5
RESEND_AFTER = timedelta(seconds=60)


class CodeError(Exception):
    """Why a code cannot be sent or accepted; the message is shown to the user."""


def _hash(user_id: Any, code: str) -> str:
    return hashlib.sha256(f"{user_id}:{code}".encode()).hexdigest()


def address_to_confirm(user: dict[str, Any]) -> str | None:
    if user.get("pending_email"):
        return user["pending_email"]
    if user.get("email_confirmed") is False:
        return user["email"]
    return None


async def send_code(db: Database, user: dict[str, Any], *, force: bool = False) -> None:
    """Send a new code to the address waiting for confirmation (replacing an older code)."""
    email = address_to_confirm(user)
    if email is None:
        raise CodeError("There is no email address to confirm")
    now = datetime.now(UTC)
    previous = user.get("email_code")
    if not force and previous and previous.get("email") == email:
        wait = previous["sent_at"].replace(tzinfo=UTC) + RESEND_AFTER - now
        if wait > timedelta(0):
            raise CodeError(f"Please wait {int(wait.total_seconds()) + 1} s before asking again")
    code = f"{secrets.randbelow(1_000_000):06d}"
    await db[COLLECTION].update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "email_code": {
                    "hash": _hash(user["_id"], code),
                    "email": email,
                    "expires_at": now + CODE_LIFETIME,
                    "attempts": 0,
                    "sent_at": now,
                }
            }
        },
    )
    await outbox.enqueue(
        db,
        "email_code",
        [{"name": user["name"], "email": email}],
        {"name": user["name"], "code": code},
    )


async def confirm(db: Database, user: dict[str, Any], code: str) -> dict[str, Any]:
    """Accept the code: the address becomes the account's confirmed email."""
    pending = user.get("email_code")
    email = address_to_confirm(user)
    if not pending or email is None or pending.get("email") != email:
        raise CodeError("No code was sent for this address; ask for a new one")
    now = datetime.now(UTC)
    if pending["expires_at"].replace(tzinfo=UTC) < now:
        raise CodeError("The code has expired; ask for a new one")
    if pending["attempts"] >= MAX_ATTEMPTS:
        raise CodeError("Too many wrong codes; ask for a new one")
    if not secrets.compare_digest(pending["hash"], _hash(user["_id"], code.strip())):
        await db[COLLECTION].update_one({"_id": user["_id"]}, {"$inc": {"email_code.attempts": 1}})
        left = MAX_ATTEMPTS - pending["attempts"] - 1
        raise CodeError(
            f"Wrong code ({left} attempt(s) left)" if left else "Wrong code; ask for a new one"
        )
    updated = await db[COLLECTION].find_one_and_update(
        {"_id": user["_id"]},
        {
            "$set": {"email": email, "email_confirmed": True, "updated_at": now},
            "$unset": {"email_code": "", "pending_email": ""},
        },
        return_document=ReturnDocument.AFTER,
    )
    assert updated is not None
    return updated
