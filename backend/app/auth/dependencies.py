"""FastAPI dependencies for the current session, the current user and role checks."""

from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, Response, status

from app.auth import sessions
from app.auth.sessions import Session
from app.config import SESSION_LIFETIME, Settings
from app.db import Database, get_db
from app.roles import Role
from app.users import repository as users

Db = Annotated[Database, Depends(get_db)]


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


AppSettings = Annotated[Settings, Depends(get_settings)]


async def get_session(request: Request, db: Db, settings: AppSettings) -> Session | None:
    token = request.cookies.get(settings.session_cookie_name)
    return await sessions.get(db, token) if token else None


OptionalSession = Annotated[Session | None, Depends(get_session)]


async def require_session(session: OptionalSession) -> Session:
    if session is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not logged in")
    return session


CurrentSession = Annotated[Session, Depends(require_session)]


async def current_user(session: CurrentSession, db: Db) -> dict[str, Any]:
    if session.user_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Registration required")
    user = await users.get_by_id(db, session.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not logged in")
    return user


CurrentUser = Annotated[dict[str, Any], Depends(current_user)]


def require_role(role: Role) -> Callable[..., Awaitable[dict[str, Any]]]:
    async def dependency(user: CurrentUser) -> dict[str, Any]:
        if not Role(user["role"]).includes(role):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires role {role.value}")
        return user

    return dependency


Operator = Annotated[dict[str, Any], Depends(require_role(Role.OPERATOR))]
Admin = Annotated[dict[str, Any], Depends(require_role(Role.ADMIN))]


def is_operator(user: dict[str, Any]) -> bool:
    return Role(user["role"]).includes(Role.OPERATOR)


def ensure_operator(user: dict[str, Any]) -> None:
    """For endpoints open to users that offer extra options to Operators."""
    if not is_operator(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires role {Role.OPERATOR.value}")


def set_session_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        path=settings.api_prefix,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        settings.session_cookie_name,
        path=settings.api_prefix,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
