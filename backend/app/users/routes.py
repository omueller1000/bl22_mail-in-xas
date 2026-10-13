"""Account endpoints (requirements §4): registration, own profile, user list, roles."""

from fastapi import APIRouter, HTTPException, status

from app.auth import sessions
from app.auth.dependencies import Admin, AppSettings, CurrentSession, CurrentUser, Db, Operator
from app.roles import Role
from app.users import repository as users
from app.users.models import Profile, Registration, RoleUpdate, User

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def register(
    body: Registration, session: CurrentSession, db: Db, settings: AppSettings
) -> User:
    """Create the account for the ORCID iD confirmed by the current session."""
    if session.user_id is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Account already exists")

    # The ORCID name wins and is not editable; a name is only asked for when ORCID has none.
    name = session.orcid_name or body.name
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Name is required")

    if session.orcid in settings.bootstrap_admin_orcids:
        role = Role.ADMIN
    else:
        role = session.requested_role or Role.USER

    try:
        doc = await users.create(
            db,
            orcid=session.orcid,
            name=name,
            role=role,
            profile=Profile.model_validate(body.model_dump(exclude={"name"})),
        )
    except users.OrcidAlreadyRegistered:
        raise HTTPException(status.HTTP_409_CONFLICT, "Account already exists") from None
    await sessions.attach_user(db, session, doc["_id"])
    return users.to_model(doc)


@router.get("/me")
async def get_me(user: CurrentUser) -> User:
    return users.to_model(user)


@router.put("/me")
async def update_me(body: Profile, user: CurrentUser, db: Db) -> User:
    doc = await users.update_profile(db, user["_id"], body)
    assert doc is not None
    return users.to_model(doc)


@router.get("")
async def list_users(_: Operator, db: Db) -> list[User]:
    return [users.to_model(doc) for doc in await users.list_all(db)]


@router.get("/{user_id}")
async def get_user(user_id: str, _: Operator, db: Db) -> User:
    oid = users.parse_id(user_id)
    doc = await users.get_by_id(db, oid) if oid else None
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return users.to_model(doc)


@router.put("/{user_id}/role")
async def set_role(user_id: str, body: RoleUpdate, admin: Admin, db: Db) -> User:
    oid = users.parse_id(user_id)
    if oid == admin["_id"]:
        # Prevents the last admin from locking everyone out by accident.
        raise HTTPException(status.HTTP_409_CONFLICT, "You cannot change your own role")
    doc = await users.set_role(db, oid, body.role) if oid else None
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return users.to_model(doc)
