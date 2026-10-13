"""ORCID login flow, with ORCID's token endpoint simulated."""

from collections.abc import AsyncIterator, Callable
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from httpx import AsyncClient

from app.main import create_app
from tests.conftest import API, app_client, make_settings, orcid, register

pytestmark = pytest.mark.db

ORCID_BASE = "https://sandbox.orcid.org"
FRONTEND = "http://localhost:5180/mail-in-xas"

TokenHandler = Callable[[httpx.Request], httpx.Response]


def token_response(orcid_id: str, name: str | None = "Ada Lovelace") -> TokenHandler:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == f"{ORCID_BASE}/oauth/token"
        form = parse_qs(request.content.decode())
        assert form["grant_type"] == ["authorization_code"]
        assert form["code"] == ["the-code"]
        assert form["client_secret"] == ["secret"]
        assert form["redirect_uri"] == [f"{FRONTEND}/api/auth/orcid/callback"]
        return httpx.Response(
            200, json={"access_token": "x", "orcid": orcid_id, "name": name, "scope": "openid"}
        )

    return handler


class OrcidSim:
    """Holds the handler the simulated ORCID token endpoint answers with."""

    def __init__(self) -> None:
        self.handler: TokenHandler = token_response(orcid(1))

    def __call__(self, request: httpx.Request) -> httpx.Response:
        return self.handler(request)


@pytest.fixture
def sim() -> OrcidSim:
    return OrcidSim()


@pytest.fixture
async def client(clean_db: None, sim: OrcidSim) -> AsyncIterator[AsyncClient]:
    settings = make_settings(
        orcid_base_url=ORCID_BASE, orcid_client_id="APP-TEST", orcid_client_secret="secret"
    )
    app = create_app(settings, orcid_transport=httpx.MockTransport(sim))
    async with app_client(app) as c:
        yield c


async def start_login(client: AsyncClient, return_to: str = "/") -> str:
    """Begin a login; return the state ORCID would send back."""
    response = await client.get(f"{API}/auth/orcid/login", params={"return_to": return_to})
    assert response.status_code == 302
    location = urlparse(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == (
        f"{ORCID_BASE}/oauth/authorize"
    )
    query = parse_qs(location.query)
    assert query["client_id"] == ["APP-TEST"]
    assert query["scope"] == ["openid"]
    assert query["redirect_uri"] == [f"{FRONTEND}/api/auth/orcid/callback"]
    return query["state"][0]


async def callback(client: AsyncClient, **params: str) -> httpx.Response:
    return await client.get(f"{API}/auth/orcid/callback", params=params)


async def test_orcid_login_disabled_without_credentials(clean_db: None) -> None:
    async with app_client(create_app(make_settings())) as c:
        assert (await c.get(f"{API}/auth/orcid/login")).status_code == 404


async def test_new_user_is_sent_to_registration(client: AsyncClient) -> None:
    state = await start_login(client)
    response = await callback(client, code="the-code", state=state)

    assert response.status_code == 302
    assert response.headers["location"] == f"{FRONTEND}/register"
    me = (await client.get(f"{API}/auth/me")).json()
    assert me["status"] == "registration_required"
    assert me["orcid"] == orcid(1)
    assert me["orcid_name"] == "Ada Lovelace"


async def test_existing_user_returns_to_requested_page(client: AsyncClient) -> None:
    await callback(client, code="the-code", state=await start_login(client))
    await register(client)
    await client.post(f"{API}/auth/logout")

    state = await start_login(client, return_to="/frames/ABCD-EFGH")
    response = await callback(client, code="the-code", state=state)
    assert response.headers["location"] == f"{FRONTEND}/frames/ABCD-EFGH"
    assert (await client.get(f"{API}/auth/me")).json()["status"] == "authenticated"


@pytest.mark.parametrize("return_to", ["https://evil.example", "//evil.example", "/\\evil"])
async def test_return_to_must_be_local(client: AsyncClient, return_to: str) -> None:
    await callback(client, code="the-code", state=await start_login(client))
    await register(client)
    await client.post(f"{API}/auth/logout")

    response = await callback(
        client, code="the-code", state=await start_login(client, return_to=return_to)
    )
    assert response.headers["location"] == f"{FRONTEND}/"


async def test_private_orcid_name(client: AsyncClient, sim: OrcidSim) -> None:
    sim.handler = token_response(orcid(1), name=None)
    await callback(client, code="the-code", state=await start_login(client))
    assert (await client.get(f"{API}/auth/me")).json()["orcid_name"] is None


async def test_unknown_state_is_rejected(client: AsyncClient) -> None:
    await start_login(client)
    response = await callback(client, code="the-code", state="forged")
    assert response.headers["location"] == f"{FRONTEND}/login?error=login_expired"
    assert (await client.get(f"{API}/auth/me")).json()["status"] == "anonymous"


async def test_state_from_another_browser_is_rejected(client: AsyncClient) -> None:
    state = await start_login(client)
    client.cookies.clear()  # the callback arrives in a browser that did not start the login
    response = await callback(client, code="the-code", state=state)
    assert response.headers["location"] == f"{FRONTEND}/login?error=login_expired"


async def test_state_can_be_used_only_once(client: AsyncClient) -> None:
    state = await start_login(client)
    await callback(client, code="the-code", state=state)
    await client.post(f"{API}/auth/logout")
    client.cookies.set("ht_xas_login_state", state, path=f"{API}/auth/orcid")
    response = await callback(client, code="the-code", state=state)
    assert response.headers["location"] == f"{FRONTEND}/login?error=login_expired"


async def test_user_cancels_at_orcid(client: AsyncClient) -> None:
    state = await start_login(client)
    response = await callback(client, error="access_denied", state=state)
    assert response.headers["location"] == f"{FRONTEND}/login?error=orcid_cancelled"


async def test_token_exchange_failure(client: AsyncClient, sim: OrcidSim) -> None:
    sim.handler = lambda request: httpx.Response(400, json={"error": "invalid_grant"})
    response = await callback(client, code="the-code", state=await start_login(client))
    assert response.headers["location"] == f"{FRONTEND}/login?error=orcid_failed"
    assert (await client.get(f"{API}/auth/me")).json()["status"] == "anonymous"
