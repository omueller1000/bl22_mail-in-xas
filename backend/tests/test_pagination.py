"""Paged staff lists: All Frames, All Users, Material Requests (app.pagination)."""

from typing import Any

import pytest
from httpx import AsyncClient

from tests.conftest import API, issue_frames, login_as, orcid

pytestmark = pytest.mark.db

OPERATOR = orcid(999)


async def rename(raw_db: Any, orcid_id: str, name: str) -> None:
    await raw_db["users"].update_one({"orcid": orcid_id}, {"$set": {"name": name}})


async def get(client: AsyncClient, path: str, **params: Any) -> dict[str, Any]:
    response = await client.get(f"{API}{path}", params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def test_staff_only(client: AsyncClient) -> None:
    await login_as(client, orcid(1))
    for path in ("/frames/all", "/users", "/material-requests/all"):
        assert (await client.get(f"{API}{path}")).status_code == 403


async def test_frames_pages_and_total(client: AsyncClient) -> None:
    codes = sorted(await issue_frames(client, orcid(1), 5))
    await login_as(client, OPERATOR, role="operator")

    first = await get(client, "/frames/all", page_size=2)
    assert first["total"] == 5
    assert [f["barcode"] for f in first["items"]] == codes[:2]
    last = await get(client, "/frames/all", page_size=2, page=3)
    assert [f["barcode"] for f in last["items"]] == codes[4:]
    beyond = await get(client, "/frames/all", page_size=2, page=4)
    assert beyond == {"items": [], "total": 5, "page": 4, "page_size": 2}
    desc = await get(client, "/frames/all", page_size=2, order="desc")
    assert [f["barcode"] for f in desc["items"]] == codes[::-1][:2]


async def test_frames_leave_out_reserved_unless_asked(client: AsyncClient) -> None:
    await issue_frames(client, orcid(1), 1)
    await login_as(client, OPERATOR, role="operator")
    await client.post(f"{API}/frames/reserve", json={"count": 3})

    assert (await get(client, "/frames/all"))["total"] == 1
    assert (await get(client, "/frames/all", state="reserved"))["total"] == 3
    assert (await get(client, "/frames/all", state="issued"))["total"] == 1


async def test_frames_search_by_barcode_owner_and_note(client: AsyncClient, raw_db: Any) -> None:
    [ada_code] = await issue_frames(client, orcid(1), 1)
    [bob_code] = await issue_frames(client, orcid(2), 1)
    await rename(raw_db, orcid(1), "Ada Lovelace")
    await rename(raw_db, orcid(2), "Bob Builder")
    await raw_db["frames"].update_one({"_id": bob_code}, {"$set": {"note": "Battery cathodes"}})
    await login_as(client, OPERATOR, role="operator")

    async def found(q: str) -> list[str]:
        return [f["barcode"] for f in (await get(client, "/frames/all", q=q))["items"]]

    assert await found(ada_code[:6].lower()) == [ada_code]
    assert await found("lovel") == [ada_code]
    assert await found("CATHODE") == [bob_code]
    assert await found("a.*") == []  # regex characters are taken literally
    assert sorted(await found("  ")) == sorted([ada_code, bob_code])


async def test_users_search_filter_and_sort(client: AsyncClient, raw_db: Any) -> None:
    await login_as(client, orcid(1))
    await login_as(client, orcid(2))
    await login_as(client, OPERATOR, role="operator")
    await rename(raw_db, orcid(1), "Zoe Zed")
    await rename(raw_db, orcid(2), "Ann Able")
    await rename(raw_db, OPERATOR, "Mia Mid")

    names = [u["name"] for u in (await get(client, "/users"))["items"]]
    assert names == ["Ann Able", "Mia Mid", "Zoe Zed"]
    desc = await get(client, "/users", order="desc", page_size=1)
    assert [u["name"] for u in desc["items"]] == ["Zoe Zed"]
    assert desc["total"] == 3
    assert [u["name"] for u in (await get(client, "/users", q="zed"))["items"]] == ["Zoe Zed"]
    assert [u["orcid"] for u in (await get(client, "/users", q=orcid(2)))["items"]] == [orcid(2)]
    operators = await get(client, "/users", role="operator")
    assert [u["name"] for u in operators["items"]] == ["Mia Mid"]
    assert (await client.get(f"{API}/users", params={"page_size": 201})).status_code == 422
    assert (await client.get(f"{API}/users", params={"page": 0})).status_code == 422


async def test_requests_newest_first_search_and_state(client: AsyncClient, raw_db: Any) -> None:
    await issue_frames(client, orcid(1), 1)
    await login_as(client, orcid(2))
    open_request = await client.post(f"{API}/material-requests", json={"plates": [], "frames": 1})
    number = open_request.json()["number"]
    await rename(raw_db, orcid(2), "Bob Builder")
    await login_as(client, OPERATOR, role="operator")

    listed = await get(client, "/material-requests/all")
    assert listed["total"] == 2
    assert listed["items"][0]["number"] == number
    submitted = await get(client, "/material-requests/all", state="submitted")
    assert [r["number"] for r in submitted["items"]] == [number]
    by_number = await get(client, "/material-requests/all", q=str(number))
    assert [r["number"] for r in by_number["items"]] == [number]
    by_name = await get(client, "/material-requests/all", q="builder")
    assert [r["user"]["name"] for r in by_name["items"]] == ["Bob Builder"]
