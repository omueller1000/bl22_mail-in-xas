"""Email confirmation (§4.3) and notification emails (§6.8)."""

from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Any

import pytest
from httpx import AsyncClient

from app.mail import sender, templates
from app.mail.outbox import ARRIVAL_WINDOW
from tests.conftest import (
    ADMIN,
    API,
    PROFILE,
    confirm_email,
    dev_login,
    issue_frames,
    last_code,
    login_as,
    make_settings,
    orcid,
    register,
)
from tests.test_instrument import ready_frame, sweep

pytestmark = pytest.mark.db

EMAIL = PROFILE["email"]


async def outbox(raw_db: Any, kind: str | None = None) -> list[dict[str, Any]]:
    query = {"kind": kind} if kind else {}
    return await raw_db.mail_outbox.find(query).sort("_id", 1).to_list()


# --- email confirmation ------------------------------------------------------------------


async def test_registration_needs_the_emailed_code(client: AsyncClient) -> None:
    await dev_login(client, orcid(1))
    user = await register(client, confirm=False)
    assert user["email_confirmed"] is False
    me = (await client.get(f"{API}/auth/me")).json()
    assert me["status"] == "email_confirmation_required"
    # The portal cannot be used yet.
    assert (await client.get(f"{API}/frames")).status_code == 403

    wrong = await client.post(f"{API}/users/me/email/confirm", json={"code": "000000"})
    if (await last_code(EMAIL)) != "000000":
        assert wrong.status_code == 422 and "4 attempt(s) left" in wrong.json()["detail"]

    confirmed = await confirm_email(client, EMAIL)
    assert confirmed["email_confirmed"] is True
    assert (await client.get(f"{API}/auth/me")).json()["status"] == "authenticated"
    assert (await client.get(f"{API}/frames")).status_code == 200


async def test_codes_expire_and_resending_is_limited(client: AsyncClient, raw_db: Any) -> None:
    await dev_login(client, orcid(1))
    await register(client, confirm=False)
    assert (await client.post(f"{API}/users/me/email/code")).status_code == 409  # too soon

    await raw_db.users.update_one(
        {"orcid": orcid(1)},
        {"$set": {"email_code.expires_at": datetime.now(UTC) - timedelta(seconds=1)}},
    )
    code = await last_code(EMAIL)
    expired = await client.post(f"{API}/users/me/email/confirm", json={"code": code})
    assert expired.status_code == 422 and "expired" in expired.json()["detail"]

    await raw_db.users.update_one(
        {"orcid": orcid(1)},
        {"$set": {"email_code.sent_at": datetime.now(UTC) - timedelta(minutes=2)}},
    )
    assert (await client.post(f"{API}/users/me/email/code")).status_code == 204
    await confirm_email(client, EMAIL)


async def test_changing_the_email_needs_confirmation(client: AsyncClient) -> None:
    await login_as(client, orcid(1))
    new = "new@example.org"
    changed = (await client.put(f"{API}/users/me", json={**PROFILE, "email": new})).json()
    assert (changed["email"], changed["pending_email"]) == (EMAIL, new)
    # Still usable with the old, confirmed address.
    assert (await client.get(f"{API}/frames")).status_code == 200

    confirmed = await confirm_email(client, new)
    assert (confirmed["email"], confirmed["pending_email"]) == (new, None)

    await client.put(f"{API}/users/me", json={**PROFILE, "email": "other@example.org"})
    cancelled = (await client.delete(f"{API}/users/me/email/pending")).json()
    assert (cancelled["email"], cancelled["pending_email"]) == (new, None)


# --- events ---------------------------------------------------------------------------------


async def test_material_request_notifies_operators(client: AsyncClient, raw_db: Any) -> None:
    await login_as(client, orcid(2), role="operator")
    await login_as(client, orcid(1))
    await client.post(f"{API}/material-requests", json={"plates": [], "frames": 2})
    [mail] = await outbox(raw_db, "material_request")
    assert [r["email"] for r in mail["to"]] == [EMAIL]  # the operator's (test) address
    assert mail["data"]["frames"] == 2


async def test_frame_journey_emails(client: AsyncClient, raw_db: Any) -> None:
    codes = await issue_frames(client, orcid(1), count=3)
    await login_as(client, orcid(9), role="operator")
    await client.post(f"{API}/frames/ship", json={"barcodes": codes})
    [shipped] = await outbox(raw_db, "shipped")
    assert shipped["data"]["frames"] == sorted(codes)

    # Two declared frames arrive: one email collects both. The third is on hold.
    declared = {"at": datetime.now(UTC), "by": {"orcid": orcid(1), "name": "Ada Test"}}
    await raw_db.frames.update_many(
        {"_id": {"$in": codes[:2]}}, {"$set": {"safety_declared": declared}}
    )
    for code in codes:
        await client.post(f"{API}/scans/apply", json={"action": "receive", "barcodes": [code]})
    [arrived] = await outbox(raw_db, "arrived")
    assert arrived["status"] == "collecting"
    assert sorted(arrived["data"]["frames"]) == sorted(codes[:2])
    assert len(await outbox(raw_db, "on_hold")) == 1
    assert len(await outbox(raw_db, "on_hold_staff")) == 1

    # Marking a frame as returning sends nothing; shipping it does, in the shipment email.
    await client.post(f"{API}/scans/apply", json={"action": "return", "barcodes": [codes[0]]})
    assert await outbox(raw_db, "returned") == []
    await client.post(f"{API}/frames/ship", json={"barcodes": [codes[0]]})
    shipments = await outbox(raw_db, "shipped")
    assert len(shipments) == 2
    back = next(s for s in shipments if s["data"].get("returned"))
    assert back["data"]["returned"] == [codes[0]]
    assert back["data"]["frames"] == [] and back["data"]["plates"] == []


def test_shipment_email_lists_new_material_and_returned_frames() -> None:
    data = {
        "name": "Ada",
        "frames": ["AAAA-AAAB"],
        "plates": [{"plate_type": "8-circle", "quantity": 2}],
        "returned": ["AAAA-AACT"],
    }
    email = templates.render("shipped", data, "https://host/mail-in-xas/")
    assert email.subject == "BL22 mail-in XAS: 1 new and 1 returned frame(s) shipped to you"
    assert "  - Frame AAAA-AAAB (new)" in email.text
    assert "  - 2 × 8-Circle plate" in email.text
    assert "  - Frame AAAA-AACT with your samples (returned)" in email.text
    only_back = templates.render(
        "shipped", {"name": "Ada", "returned": ["AAAA-AACT"]}, "https://host/mail-in-xas/"
    )
    assert only_back.subject == "BL22 mail-in XAS: 1 frame(s) returned to you"
    assert "new material" not in only_back.text


async def test_frame_complete_email(
    client: AsyncClient, raw_db: Any, instrument: AsyncClient
) -> None:
    ready = await ready_frame(client, raw_db)
    url = f"{API}/instrument/measurements/{ready['measurement']}"
    await instrument.post(f"{url}/sweeps", json=sweep())
    await instrument.put(f"{url}/status", json={"status": "done"})
    await instrument.put(f"{url}/status", json={"status": "done"})  # unchanged: no new email
    assert len(await outbox(raw_db, "frame_complete")) == 1
    assert len(await outbox(raw_db, "frame_complete_staff")) == 1

    # Re-measured and complete again: sent again.
    await instrument.put(f"{url}/status", json={"status": "pending"})
    await instrument.post(f"{url}/sweeps", json=sweep(2, 2))
    await instrument.put(f"{url}/status", json={"status": "done"})
    assert len(await outbox(raw_db, "frame_complete")) == 2


async def test_no_complete_email_without_data(
    client: AsyncClient, raw_db: Any, instrument: AsyncClient
) -> None:
    ready = await ready_frame(client, raw_db)
    url = f"{API}/instrument/measurements/{ready['measurement']}/status"
    await instrument.put(url, json={"status": "done"})
    assert await outbox(raw_db, "frame_complete") == []


# --- delivery -------------------------------------------------------------------------------


class FakeTransport:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[EmailMessage] = []
        self.fail = fail

    def __call__(self, message: EmailMessage) -> None:
        if self.fail:
            raise ConnectionRefusedError("no server")
        self.sent.append(message)


PROD = {
    "environment": "prod",
    "dev_login_enabled": False,
    "smtp_host": "smtp.invalid",
    "mail_from_address": "noreply@example.org",
}


async def queue(raw_db: Any, kind: str = "returned", **data: Any) -> None:
    now = datetime.now(UTC)
    await raw_db.mail_outbox.insert_one(
        {
            "kind": kind,
            "to": [{"name": "Ada", "email": "ada@example.org"}],
            "data": {"name": "Ada", "barcode": "AAAA-AAAA", **data},
            "status": "queued",
            "send_after": now,
            "attempts": 0,
            "created_at": now,
        }
    )


async def test_outside_production_mail_is_redirected_or_kept(clean_db: None, raw_db: Any) -> None:
    transport = FakeTransport()
    await queue(raw_db)
    await sender.deliver_due(raw_db, make_settings(), transport)
    [mail] = await outbox(raw_db)
    assert mail["status"] == "not_sent" and "Frame AAAA-AAAA" in mail["text"]
    assert transport.sent == []

    await queue(raw_db)
    settings = make_settings(
        mail_dev_redirect="me@example.org",
        **{k: v for k, v in PROD.items() if k.startswith(("smtp", "mail"))},
    )
    await sender.deliver_due(raw_db, settings, transport)
    [message] = transport.sent
    assert message["To"] == "me@example.org"
    assert message["Subject"].startswith("[local → ada@example.org]")
    assert message["From"] == "BL22 <noreply@example.org>"


async def test_production_switch_and_redirect(clean_db: None, raw_db: Any) -> None:
    settings = make_settings(**PROD)
    transport = FakeTransport()
    await raw_db.settings.insert_one({"_id": "mail", "enabled": False, "redirect_to": None})
    await queue(raw_db)
    await queue(raw_db, "email_code", code="123456")
    await sender.deliver_due(raw_db, settings, transport)
    statuses = {m["kind"]: m["status"] for m in await outbox(raw_db)}
    assert statuses == {"returned": "suppressed", "email_code": "sent"}
    [code_mail] = transport.sent
    assert (
        code_mail["To"] == "ada@example.org"
        and "123456" in code_mail.get_body(("plain",)).get_content()
    )
    # The delivered code is not kept readable.
    stored = (await outbox(raw_db, "email_code"))[0]
    assert stored["data"]["code"] is None and "123456" not in stored["text"]

    await raw_db.settings.replace_one(
        {"_id": "mail"}, {"enabled": True, "redirect_to": "debug@example.org"}
    )
    await queue(raw_db)
    await sender.deliver_due(raw_db, settings, transport)
    assert transport.sent[-1]["To"] == "debug@example.org"
    assert transport.sent[-1]["Subject"].startswith("[→ ada@example.org]")


async def test_arrivals_wait_for_the_window(client: AsyncClient, raw_db: Any) -> None:
    [code] = await issue_frames(client, orcid(1))
    await login_as(client, orcid(9), role="operator")
    await client.post(f"{API}/frames/ship", json={"barcodes": [code]})
    await raw_db.frames.update_one(
        {"_id": code}, {"$set": {"safety_declared": {"at": datetime.now(UTC)}}}
    )
    await client.post(f"{API}/scans/apply", json={"action": "receive", "barcodes": [code]})

    settings, transport = make_settings(**PROD), FakeTransport()
    await sender.deliver_due(raw_db, settings, transport)
    assert not any("arrived" in m["Subject"] for m in transport.sent)
    later = datetime.now(UTC) + ARRIVAL_WINDOW + timedelta(seconds=1)
    await sender.deliver_due(raw_db, settings, transport, now=later)
    assert "1 frame(s) arrived" in transport.sent[-1]["Subject"]


async def test_failures_are_retried_then_reported(clean_db: None, raw_db: Any) -> None:
    settings, transport = make_settings(**PROD), FakeTransport(fail=True)
    await queue(raw_db)
    now = datetime.now(UTC)
    for attempt in range(len(sender.RETRY_DELAYS) + 1):
        await sender.deliver_due(raw_db, settings, transport, now=now + timedelta(days=attempt))
    [mail] = await outbox(raw_db)
    assert mail["status"] == "failed" and "ConnectionRefusedError" in mail["error"]
    assert mail["attempts"] == len(sender.RETRY_DELAYS) + 1


# --- admin page -------------------------------------------------------------------------------


async def test_admin_mail_page(client: AsyncClient, raw_db: Any) -> None:
    await login_as(client, orcid(4), role="operator")
    assert (await client.get(f"{API}/admin/mail")).status_code == 403

    await login_as(client, ADMIN, role="admin")
    status = (await client.get(f"{API}/admin/mail")).json()
    assert status["switches"] == {"enabled": True, "redirect_to": None}
    assert status["environment"] == "local" and status["configured"] is False

    changed = await client.put(
        f"{API}/admin/mail", json={"enabled": False, "redirect_to": "debug@example.org"}
    )
    assert changed.json()["switches"] == {"enabled": False, "redirect_to": "debug@example.org"}

    assert (
        await client.post(f"{API}/admin/mail/test", json={"to": "x@example.org"})
    ).status_code == 204
    listed = (await client.get(f"{API}/admin/mail/outbox")).json()
    assert listed[0]["kind"] == "test" and listed[0]["to"] == ["x@example.org"]
