"""Sessions, dev login, registration, profile and roles."""

import pytest
from httpx import AsyncClient

from app.main import create_app
from tests.conftest import (
    API,
    PROFILE,
    app_client,
    dev_login,
    login_as,
    make_settings,
    orcid,
    register,
)

pytestmark = pytest.mark.db


async def test_anonymous_me(client: AsyncClient) -> None:
    me = (await client.get(f"{API}/auth/me")).json()
    assert me["status"] == "anonymous"
    assert me["dev_login_enabled"] is True
    assert me["orcid_login_enabled"] is False


async def test_new_orcid_requires_registration(client: AsyncClient) -> None:
    me = await dev_login(client, orcid(1), name="Ada Test")
    assert me["status"] == "registration_required"
    assert me["orcid"] == orcid(1)
    assert me["orcid_name"] == "Ada Test"
    assert me["user"] is None

    # Account endpoints need a registered user.
    assert (await client.get(f"{API}/users/me")).status_code == 403


async def test_register_creates_user_with_orcid_name(client: AsyncClient) -> None:
    await dev_login(client, orcid(1), name="Ada Test")
    user = await register(client, name="Ignored Because ORCID Has One")

    assert user["orcid"] == orcid(1)
    assert user["name"] == "Ada Test"
    assert user["role"] == "user"
    assert user["shipping_address"]["country"] == "USA"
    me = (await client.get(f"{API}/auth/me")).json()
    assert me["status"] == "authenticated"
    assert me["user"]["id"] == user["id"]


async def test_name_required_when_orcid_has_none(client: AsyncClient) -> None:
    await dev_login(client, orcid(1), name=None)
    response = await client.post(f"{API}/users", json=PROFILE)
    assert response.status_code == 422

    user = await register(client, name="Grace Test")
    assert user["name"] == "Grace Test"


async def test_register_twice_conflicts(client: AsyncClient) -> None:
    await dev_login(client, orcid(1))
    await register(client)
    response = await client.post(f"{API}/users", json=PROFILE)
    assert response.status_code == 409


async def test_register_requires_session(client: AsyncClient) -> None:
    assert (await client.post(f"{API}/users", json=PROFILE)).status_code == 401


async def test_register_validates_profile(client: AsyncClient) -> None:
    await dev_login(client, orcid(1))
    bad = {**PROFILE, "email": "not-an-email"}
    assert (await client.post(f"{API}/users", json=bad)).status_code == 422
    missing_country = {
        **PROFILE,
        "shipping_address": {
            k: v for k, v in PROFILE["shipping_address"].items() if k != "country"
        },
    }
    assert (await client.post(f"{API}/users", json=missing_country)).status_code == 422


async def test_international_address_without_region_or_postal_code(client: AsyncClient) -> None:
    await dev_login(client, orcid(1))
    user = await register(
        client,
        shipping_address={"street1": "Rue Example 5", "city": "Geneva", "country": "Switzerland"},
    )
    assert user["shipping_address"]["region"] is None


async def test_login_again_finds_existing_account(client: AsyncClient) -> None:
    user = await login_as(client, orcid(1))
    await client.post(f"{API}/auth/logout")

    me = await dev_login(client, orcid(1))
    assert me["status"] == "authenticated"
    assert me["user"]["id"] == user["id"]


async def test_logout(client: AsyncClient) -> None:
    await login_as(client, orcid(1))
    assert (await client.post(f"{API}/auth/logout")).status_code == 204
    assert (await client.get(f"{API}/auth/me")).json()["status"] == "anonymous"


async def test_session_cookie_attributes(client: AsyncClient) -> None:
    response = await client.post(f"{API}/auth/dev-login", json={"orcid": orcid(1)})
    cookie = response.headers["set-cookie"].lower()
    assert "ht_xas_local_session=" in cookie
    assert f"path={API}" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


async def test_update_own_profile(client: AsyncClient) -> None:
    await login_as(client, orcid(1))
    changed = {**PROFILE, "phone": "+41 22 555 0000", "affiliation": "Other Institute"}
    response = await client.put(f"{API}/users/me", json=changed)
    assert response.status_code == 200
    assert response.json()["affiliation"] == "Other Institute"
    assert response.json()["name"] == "Ada Test"


async def test_name_and_role_not_editable_via_profile(client: AsyncClient) -> None:
    await login_as(client, orcid(1))
    response = await client.put(f"{API}/users/me", json={**PROFILE, "name": "X", "role": "admin"})
    assert response.status_code == 422


async def test_state_changes_require_csrf_header(client: AsyncClient) -> None:
    response = await client.post(
        f"{API}/auth/dev-login", json={"orcid": orcid(1)}, headers={"X-Requested-With": ""}
    )
    assert response.status_code == 403


async def test_dev_login_absent_when_disabled(clean_db: None) -> None:
    app = create_app(make_settings(dev_login_enabled=False))
    async with app_client(app) as c:
        response = await c.post(f"{API}/auth/dev-login", json={"orcid": orcid(1)})
        assert response.status_code == 404
        assert (await c.get(f"{API}/auth/me")).json()["dev_login_enabled"] is False


async def test_dev_login_rejects_invalid_orcid(client: AsyncClient) -> None:
    response = await client.post(f"{API}/auth/dev-login", json={"orcid": "1234"})
    assert response.status_code == 422


# --- roles ---------------------------------------------------------------------------------


async def test_user_list_requires_operator(client: AsyncClient) -> None:
    assert (await client.get(f"{API}/users")).status_code == 401
    await login_as(client, orcid(1), role="user")
    assert (await client.get(f"{API}/users")).status_code == 403


async def test_operator_lists_and_reads_users(client: AsyncClient) -> None:
    user = await login_as(client, orcid(1), role="user")
    await login_as(client, orcid(2), role="operator")

    listed = (await client.get(f"{API}/users")).json()
    assert {u["orcid"] for u in listed} == {orcid(1), orcid(2)}
    single = await client.get(f"{API}/users/{user['id']}")
    assert single.json()["email"] == PROFILE["email"]
    assert (await client.get(f"{API}/users/not-an-id")).status_code == 404


async def test_only_admin_changes_roles(client: AsyncClient) -> None:
    user = await login_as(client, orcid(1), role="user")
    await login_as(client, orcid(2), role="operator")
    url = f"{API}/users/{user['id']}/role"
    assert (await client.put(url, json={"role": "operator"})).status_code == 403

    await login_as(client, orcid(3), role="admin")
    response = await client.put(url, json={"role": "operator"})
    assert response.status_code == 200
    assert response.json()["role"] == "operator"


async def test_admin_cannot_change_own_role(client: AsyncClient) -> None:
    admin = await login_as(client, orcid(1), role="admin")
    response = await client.put(f"{API}/users/{admin['id']}/role", json={"role": "user"})
    assert response.status_code == 409


async def test_role_change_takes_effect_immediately(client: AsyncClient) -> None:
    user = await login_as(client, orcid(1), role="operator")
    assert (await client.get(f"{API}/users")).status_code == 200

    # Same browser session, role changed in the database by another admin.
    other = AsyncClient(transport=client._transport, base_url="http://test", headers=client.headers)
    async with other:
        await login_as(other, orcid(2), role="admin")
        await other.put(f"{API}/users/{user['id']}/role", json={"role": "user"})

    assert (await client.get(f"{API}/users")).status_code == 403


async def test_bootstrap_admin_on_registration(clean_db: None) -> None:
    app = create_app(make_settings(dev_login_enabled=True, bootstrap_admin_orcids=orcid(1)))
    async with app_client(app) as c:
        # Bootstrap wins over the requested role.
        assert (await login_as(c, orcid(1), role="user"))["role"] == "admin"


async def test_bootstrap_admin_on_login_of_existing_account(clean_db: None) -> None:
    # Account created while the ORCID iD was not yet configured as bootstrap admin ...
    async with app_client(create_app(make_settings(dev_login_enabled=True))) as c:
        assert (await login_as(c, orcid(1)))["role"] == "user"

    # ... becomes admin at the next login once it is.
    app = create_app(make_settings(dev_login_enabled=True, bootstrap_admin_orcids=orcid(1)))
    async with app_client(app) as c:
        me = await dev_login(c, orcid(1))
        assert me["user"]["role"] == "admin"
