"""ORCID OAuth 2.0 / OpenID Connect login (authorization code flow).

Docs: https://info.orcid.org/documentation/integration-guide/
The token response already contains the authenticated ORCID iD and (if public) the name. It
comes straight from ORCID over HTTPS in exchange for our client secret, so it is trusted as is.
"""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from pymongo import ASCENDING

from app.config import Settings
from app.db import Database

LOGIN_STATE_COLLECTION = "login_states"
LOGIN_STATE_LIFETIME = timedelta(minutes=10)


class OrcidError(Exception):
    pass


@dataclass(frozen=True)
class OrcidIdentity:
    orcid: str
    name: str | None


async def ensure_indexes(db: Database) -> None:
    await db[LOGIN_STATE_COLLECTION].create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)


def authorize_url(settings: Settings, state: str) -> str:
    query = urlencode(
        {
            "client_id": settings.orcid_client_id,
            "response_type": "code",
            "scope": "openid",
            "redirect_uri": settings.orcid_redirect_uri,
            "state": state,
        }
    )
    return f"{settings.orcid_base_url}/oauth/authorize?{query}"


async def exchange_code(settings: Settings, http: httpx.AsyncClient, code: str) -> OrcidIdentity:
    assert settings.orcid_client_secret is not None
    try:
        response = await http.post(
            f"{settings.orcid_base_url}/oauth/token",
            data={
                "client_id": settings.orcid_client_id,
                "client_secret": settings.orcid_client_secret.get_secret_value(),
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.orcid_redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
    except httpx.HTTPError as exc:
        raise OrcidError(f"ORCID token request failed: {exc}") from exc
    if response.status_code != 200:
        raise OrcidError(f"ORCID token request returned HTTP {response.status_code}")

    body = response.json()
    orcid = body.get("orcid")
    if not orcid:
        raise OrcidError("ORCID token response contains no ORCID iD")
    name = (body.get("name") or "").strip() or None
    return OrcidIdentity(orcid=orcid, name=name)


async def create_login_state(db: Database, return_to: str) -> str:
    """Remember a login attempt; the random state ties ORCID's callback to it."""
    state = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    await db[LOGIN_STATE_COLLECTION].insert_one(
        {"_id": state, "return_to": return_to, "expires_at": now + LOGIN_STATE_LIFETIME}
    )
    return state


async def consume_login_state(db: Database, state: str) -> str | None:
    """Return the stored return_to path, or None if the state is unknown or expired."""
    doc = await db[LOGIN_STATE_COLLECTION].find_one_and_delete(
        {"_id": state, "expires_at": {"$gt": datetime.now(UTC)}}
    )
    return doc["return_to"] if doc else None
