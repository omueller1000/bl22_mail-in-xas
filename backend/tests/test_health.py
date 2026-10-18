import pytest

from app import __version__
from app.main import create_app
from tests.conftest import UNREACHABLE_MONGODB_URI, app_client, make_settings


async def test_health_reports_unreachable_database() -> None:
    app = create_app(make_settings(mongodb_uri=UNREACHABLE_MONGODB_URI))
    async with app_client(app) as client:
        response = await client.get("/mail-in-xas/api/health")

    assert response.status_code == 503
    assert response.json()["database"] == "unreachable"
    assert response.json()["status"] == "degraded"


@pytest.mark.db
async def test_health_ok_with_database() -> None:
    app = create_app(make_settings())
    async with app_client(app) as client:
        response = await client.get("/mail-in-xas/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "environment": "local",
        "version": __version__,
    }


async def test_routes_follow_api_prefix() -> None:
    app = create_app(make_settings(api_prefix="/mail-in-xas/dev/api"))
    async with app_client(app) as client:
        assert (await client.get("/mail-in-xas/dev/api/health")).status_code in (200, 503)
        assert (await client.get("/mail-in-xas/api/health")).status_code == 404


async def test_docs_disabled_in_prod() -> None:
    app = create_app(make_settings(environment="prod"))
    async with app_client(app) as client:
        assert (await client.get("/mail-in-xas/api/openapi.json")).status_code == 404
        assert (await client.get("/mail-in-xas/api/docs")).status_code == 404


async def test_docs_enabled_outside_prod() -> None:
    app = create_app(make_settings())
    async with app_client(app) as client:
        assert (await client.get("/mail-in-xas/api/openapi.json")).status_code == 200
