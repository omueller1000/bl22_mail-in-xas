"""Login, logout and "who am I" endpoints (requirements §3.2, §3.3)."""

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict

from app.auth import orcid as orcid_login
from app.auth import sessions
from app.auth.dependencies import (
    AppSettings,
    Db,
    OptionalSession,
    clear_session_cookie,
    set_session_cookie,
)
from app.config import Settings
from app.db import Database
from app.orcid_id import OrcidId
from app.roles import Role
from app.users import repository as users
from app.users.models import Name, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Registered only when dev login is enabled; otherwise the endpoint does not exist (§3.3).
dev_router = APIRouter(prefix="/auth", tags=["auth"])

LOGIN_STATE_COOKIE = "ht_xas_login_state"


class Me(BaseModel):
    status: Literal[
        "anonymous", "registration_required", "email_confirmation_required", "authenticated"
    ]
    orcid_login_enabled: bool
    dev_login_enabled: bool
    # Set once ORCID (or the dev login) has confirmed an iD.
    orcid: str | None = None
    # Name from ORCID; None if private (the registration form then asks for it).
    orcid_name: str | None = None
    user: User | None = None


class DevLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    orcid: OrcidId
    name: Name | None = None
    # Role for the account; changes an existing account's role (dev login only).
    role: Role | None = None


@router.get("/me")
async def me(db: Db, settings: AppSettings, session: OptionalSession) -> Me:
    base = {
        "orcid_login_enabled": settings.orcid_login_enabled,
        "dev_login_enabled": settings.dev_login_enabled,
    }
    if session is None:
        return Me(status="anonymous", **base)
    user = await users.get_by_id(db, session.user_id) if session.user_id else None
    return Me(
        status=(
            "registration_required"
            if user is None
            else "authenticated"
            if users.email_confirmed(user)
            else "email_confirmation_required"
        ),
        orcid=session.orcid,
        orcid_name=session.orcid_name,
        user=users.to_model(user) if user else None,
        **base,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, db: Db, settings: AppSettings) -> None:
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        await sessions.delete(db, token)
    clear_session_cookie(response, settings)


@dev_router.post("/dev-login")
async def dev_login(body: DevLogin, response: Response, db: Db, settings: AppSettings) -> Me:
    token = await _start_session(db, settings, body.orcid, body.name, body.role)
    set_session_cookie(response, settings, token)
    session = await sessions.get(db, token)
    return await me(db, settings, session)


@router.get("/orcid/login")
async def orcid_login_start(db: Db, settings: AppSettings, return_to: str = "/") -> Response:
    if not settings.orcid_login_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ORCID login is not configured")
    state = await orcid_login.create_login_state(db, _safe_path(return_to))
    response = RedirectResponse(orcid_login.authorize_url(settings, state), status.HTTP_302_FOUND)
    # Binds the login to this browser, so nobody can push their own ORCID login into it.
    response.set_cookie(
        LOGIN_STATE_COOKIE,
        state,
        max_age=int(orcid_login.LOGIN_STATE_LIFETIME.total_seconds()),
        path=f"{settings.api_prefix}/auth/orcid",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/orcid/callback")
async def orcid_login_callback(
    request: Request,
    db: Db,
    settings: AppSettings,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> Response:
    if not settings.orcid_login_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ORCID login is not configured")

    if error or not code or not state:
        # e.g. the user clicked "Deny" at ORCID
        return _frontend_redirect(settings, "login?error=orcid_cancelled", clear_state=True)

    return_to = None
    if request.cookies.get(LOGIN_STATE_COOKIE) == state:
        return_to = await orcid_login.consume_login_state(db, state)
    if return_to is None:
        return _frontend_redirect(settings, "login?error=login_expired", clear_state=True)

    try:
        identity = await orcid_login.exchange_code(settings, request.app.state.http, code)
    except orcid_login.OrcidError as exc:
        logger.warning("ORCID login failed: %s", exc)
        return _frontend_redirect(settings, "login?error=orcid_failed", clear_state=True)

    token = await _start_session(db, settings, identity.orcid, identity.name, None)
    session = await sessions.get(db, token)
    assert session is not None
    target = "register" if session.user_id is None else return_to.lstrip("/")
    response = _frontend_redirect(settings, target, clear_state=True)
    set_session_cookie(response, settings, token)
    return response


async def _start_session(
    db: Database,
    settings: Settings,
    orcid: str,
    orcid_name: str | None,
    requested_role: Role | None,
) -> str:
    """Create a session for a confirmed ORCID iD and apply role rules to an existing account."""
    user = await users.get_by_orcid(db, orcid)
    if user is not None:
        role = Role(user["role"])
        if orcid in settings.bootstrap_admin_orcids:
            role = Role.ADMIN
        elif requested_role is not None:  # dev login only
            role = requested_role
        if role != user["role"]:
            await users.set_role(db, user["_id"], role)
    return await sessions.create(
        db,
        orcid=orcid,
        orcid_name=orcid_name,
        user_id=user["_id"] if user else None,
        requested_role=requested_role,
    )


def _safe_path(path: str) -> str:
    """Only allow local paths as return targets (no open redirects to other sites)."""
    if not path.startswith("/") or path.startswith("//") or "\\" in path:
        return "/"
    return path


def _frontend_redirect(settings: Settings, path: str, *, clear_state: bool) -> RedirectResponse:
    response = RedirectResponse(
        f"{settings.public_origin}{settings.frontend_base}{path}", status.HTTP_302_FOUND
    )
    if clear_state:
        response.delete_cookie(LOGIN_STATE_COOKIE, path=f"{settings.api_prefix}/auth/orcid")
    return response
