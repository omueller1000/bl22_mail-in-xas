"""Barcode reservation, material requests, issuing and shipping (requirements §6, §7, §9.3)."""

from typing import Any

import pytest
from httpx import AsyncClient

from app.frames.repository import BARCODE_PATTERN
from tests.conftest import API, login_as, orcid

pytestmark = pytest.mark.db


async def reserve(client: AsyncClient, count: int) -> list[str]:
    response = await client.post(f"{API}/frames/reserve", json={"count": count})
    assert response.status_code == 201, response.text
    return [frame["barcode"] for frame in response.json()]


async def submit(client: AsyncClient, **body: Any) -> dict[str, Any]:
    payload = {"plates": [{"plate_type": "8-circle", "quantity": 2}], "frames": 1, **body}
    response = await client.post(f"{API}/material-requests", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# --- barcodes ------------------------------------------------------------------------------


async def test_operator_reserves_unique_barcodes(client: AsyncClient) -> None:
    await login_as(client, orcid(1), role="operator")
    codes = await reserve(client, 25)

    assert len(set(codes)) == 25
    assert all(BARCODE_PATTERN.fullmatch(code) for code in codes)
    listed = await client.get(f"{API}/frames", params={"all_users": True, "state": "reserved"})
    assert {f["barcode"] for f in listed.json()} == set(codes)


async def test_users_cannot_reserve_or_list_all(client: AsyncClient) -> None:
    await login_as(client, orcid(1))
    assert (await client.post(f"{API}/frames/reserve", json={"count": 1})).status_code == 403
    assert (await client.get(f"{API}/frames", params={"all_users": True})).status_code == 403


async def test_reserve_limits(client: AsyncClient) -> None:
    await login_as(client, orcid(1), role="operator")
    for count in (0, 201):
        assert (
            await client.post(f"{API}/frames/reserve", json={"count": count})
        ).status_code == 422


# --- requests --------------------------------------------------------------------------------


async def test_user_submits_and_lists_own_requests(client: AsyncClient) -> None:
    user = await login_as(client, orcid(1))
    first = await submit(client, comment="  for beamtime in May ")
    second = await submit(client, plates=[], frames=3)

    assert first["state"] == "submitted"
    assert first["user"]["id"] == user["id"]
    assert first["comment"] == "for beamtime in May"
    assert second["number"] == first["number"] + 1

    listed = (await client.get(f"{API}/material-requests")).json()
    assert [r["number"] for r in listed] == [second["number"], first["number"]]


@pytest.mark.parametrize(
    ("plates", "frames"),
    [
        ([{"plate_type": "8-circle", "quantity": 4}], 1),  # needs at least 2 frames
        ([{"plate_type": "8-circle", "quantity": 4}], 5),  # at most 4
        (
            [
                {"plate_type": "6-circle-gas", "quantity": 2},
                {"plate_type": "8-circle", "quantity": 2},
            ],
            2,
        ),
        ([{"plate_type": "8-circle-gas", "quantity": 1}], 1),  # obsolete type
        ([{"plate_type": "8-circle", "quantity": 1}, {"plate_type": "8-circle", "quantity": 1}], 1),
        ([], 0),
    ],
)
async def test_invalid_requests_rejected(
    client: AsyncClient, plates: list[dict[str, Any]], frames: int
) -> None:
    await login_as(client, orcid(1))
    response = await client.post(
        f"{API}/material-requests", json={"plates": plates, "frames": frames}
    )
    assert response.status_code == 422


async def test_users_see_only_their_own_requests(client: AsyncClient) -> None:
    await login_as(client, orcid(1))
    mine = await submit(client)
    await login_as(client, orcid(2))
    assert (await client.get(f"{API}/material-requests")).json() == []
    assert (await client.get(f"{API}/material-requests/{mine['id']}")).status_code == 403
    assert (await client.get(f"{API}/material-requests/all")).status_code == 403


async def test_operator_rejects_request(client: AsyncClient) -> None:
    await login_as(client, orcid(1))
    request = await submit(client)
    await login_as(client, orcid(2), role="operator")

    url = f"{API}/material-requests/{request['id']}/reject"
    response = await client.post(url, json={"reason": "Duplicate of #1"})
    assert response.status_code == 200
    assert response.json()["state"] == "rejected"
    assert response.json()["reject_reason"] == "Duplicate of #1"
    assert response.json()["decided_by"] == "Ada Test"
    assert (await client.post(url, json={})).status_code == 409  # no longer open


# --- issuing -----------------------------------------------------------------------------------


async def test_issue_barcodes_to_requester(client: AsyncClient) -> None:
    user = await login_as(client, orcid(1))
    request = await submit(client, plates=[{"plate_type": "8-circle", "quantity": 4}], frames=2)
    await login_as(client, orcid(2), role="operator")
    codes = await reserve(client, 3)

    response = await client.post(
        f"{API}/material-requests/{request['id']}/issue",
        json={"barcodes": [codes[0].lower(), codes[1]]},  # scanners may send lower case
    )
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "issued"
    assert response.json()["barcodes"] == codes[:2]

    frame = (await client.get(f"{API}/frames/{codes[0]}")).json()
    assert frame["state"] == "issued"
    assert frame["owner"]["id"] == user["id"]
    assert [event["state"] for event in frame["history"]] == ["reserved", "issued"]
    still_reserved = (await client.get(f"{API}/frames/{codes[2]}")).json()
    assert still_reserved["state"] == "reserved"


@pytest.mark.parametrize("scanned", [1, 3])
async def test_issue_needs_exact_frame_count(client: AsyncClient, scanned: int) -> None:
    await login_as(client, orcid(1))
    request = await submit(client, plates=[{"plate_type": "8-circle", "quantity": 4}], frames=2)
    await login_as(client, orcid(2), role="operator")
    codes = await reserve(client, scanned)

    response = await client.post(
        f"{API}/material-requests/{request['id']}/issue", json={"barcodes": codes}
    )
    assert response.status_code == 409
    assert "exactly 2" in response.json()["detail"]


async def test_issue_is_all_or_nothing(client: AsyncClient) -> None:
    await login_as(client, orcid(1))
    first = await submit(client)
    second = await submit(client, plates=[{"plate_type": "8-circle", "quantity": 2}], frames=2)
    await login_as(client, orcid(2), role="operator")
    codes = await reserve(client, 2)
    await client.post(f"{API}/material-requests/{first['id']}/issue", json={"barcodes": [codes[0]]})

    # codes[0] is already issued -> nothing changes, codes[1] stays reserved
    response = await client.post(
        f"{API}/material-requests/{second['id']}/issue", json={"barcodes": codes}
    )
    assert response.status_code == 409
    assert f"{codes[0]}: already issued" in response.json()["detail"]
    assert (await client.get(f"{API}/frames/{codes[1]}")).json()["state"] == "reserved"
    second_now = (await client.get(f"{API}/material-requests/{second['id']}")).json()
    assert second_now["state"] == "submitted"


async def test_issue_rejects_unknown_and_duplicate_barcodes(client: AsyncClient) -> None:
    await login_as(client, orcid(1))
    request = await submit(client, plates=[{"plate_type": "8-circle", "quantity": 2}], frames=2)
    await login_as(client, orcid(2), role="operator")
    codes = await reserve(client, 1)
    url = f"{API}/material-requests/{request['id']}/issue"

    unknown = await client.post(url, json={"barcodes": [codes[0], "ZZZZ-ZZZZ"]})
    assert unknown.status_code == 409
    assert "ZZZZ-ZZZZ: unknown barcode" in unknown.json()["detail"]
    twice = await client.post(url, json={"barcodes": [codes[0], codes[0]]})
    assert twice.status_code == 422
    malformed = await client.post(url, json={"barcodes": ["not-a-code"]})
    assert malformed.status_code == 422


# --- shipping --------------------------------------------------------------------------------


async def issue_to(client: AsyncClient, user_orcid: str, frames: int) -> list[str]:
    """As the given user request `frames` frames, then issue them as an operator."""
    await login_as(client, user_orcid)
    request = await submit(client, plates=[], frames=frames)
    await login_as(client, orcid(99), role="operator")
    codes = await reserve(client, frames)
    response = await client.post(
        f"{API}/material-requests/{request['id']}/issue", json={"barcodes": codes}
    )
    assert response.status_code == 200, response.text
    return codes


async def test_shipping_list_groups_issued_frames_by_user(client: AsyncClient) -> None:
    ada = await issue_to(client, orcid(1), 2)
    bob = await issue_to(client, orcid(2), 1)

    groups = (await client.get(f"{API}/frames/shipping")).json()
    by_orcid = {group["user"]["orcid"]: group for group in groups}
    assert sorted(by_orcid[orcid(1)]["barcodes"]) == sorted(ada)
    assert by_orcid[orcid(2)]["barcodes"] == bob
    assert by_orcid[orcid(1)]["user"]["shipping_address"]["city"] == "Example City"


async def test_mark_group_shipped(client: AsyncClient) -> None:
    codes = await issue_to(client, orcid(1), 2)

    response = await client.post(f"{API}/frames/ship", json={"barcodes": codes})
    assert response.status_code == 200, response.text
    assert {f["state"] for f in response.json()} == {"shipped_to_user"}
    assert (await client.get(f"{API}/frames/shipping")).json() == []

    again = await client.post(f"{API}/frames/ship", json={"barcodes": codes})
    assert again.status_code == 409


async def test_ship_is_all_or_nothing(client: AsyncClient) -> None:
    codes = await issue_to(client, orcid(1), 1)
    reserved = await reserve(client, 1)
    response = await client.post(f"{API}/frames/ship", json={"barcodes": codes + reserved})
    assert response.status_code == 409
    assert (await client.get(f"{API}/frames/{codes[0]}")).json()["state"] == "issued"


async def test_user_sees_own_frames_only(client: AsyncClient) -> None:
    codes = await issue_to(client, orcid(1), 2)
    await login_as(client, orcid(1))  # existing account: dev login only
    mine = (await client.get(f"{API}/frames")).json()
    assert sorted(f["barcode"] for f in mine) == sorted(codes)

    await login_as(client, orcid(2))
    assert (await client.get(f"{API}/frames")).json() == []
    assert (await client.get(f"{API}/frames/{codes[0]}")).status_code == 404


async def test_shipping_requires_operator(client: AsyncClient) -> None:
    await login_as(client, orcid(1))
    assert (await client.get(f"{API}/frames/shipping")).status_code == 403
    assert (
        await client.post(f"{API}/frames/ship", json={"barcodes": ["AAAA-AAAA"]})
    ).status_code == 403


# --- request completion --------------------------------------------------------------------


async def requests_of(client: AsyncClient, user_orcid: str) -> list[dict[str, Any]]:
    response = await client.get(f"{API}/material-requests/all")
    return [r for r in response.json()["items"] if r["user"]["orcid"] == user_orcid]


async def test_request_fulfilled_when_its_frames_ship(client: AsyncClient) -> None:
    codes = await issue_to(client, orcid(1), 2)
    [request] = await requests_of(client, orcid(1))
    assert request["state"] == "issued"
    assert request["fulfilled_at"] is None

    # Shipping only part of the frames keeps the request open ...
    await client.post(f"{API}/frames/ship", json={"barcodes": codes[:1]})
    [request] = await requests_of(client, orcid(1))
    assert request["state"] == "issued"

    # ... until the last one ships.
    await client.post(f"{API}/frames/ship", json={"barcodes": codes[1:]})
    [request] = await requests_of(client, orcid(1))
    assert request["state"] == "fulfilled"
    assert request["fulfilled_at"] is not None


async def test_shipping_a_group_fulfils_all_its_requests(client: AsyncClient) -> None:
    first = await issue_to(client, orcid(1), 1)
    second = await issue_to(client, orcid(1), 2)
    [group] = (await client.get(f"{API}/frames/shipping")).json()
    assert sorted(group["barcodes"]) == sorted(first + second)

    await client.post(f"{API}/frames/ship", json={"barcodes": group["barcodes"]})
    assert {r["state"] for r in await requests_of(client, orcid(1))} == {"fulfilled"}


async def test_issued_request_can_no_longer_be_rejected(client: AsyncClient) -> None:
    await issue_to(client, orcid(1), 1)
    [request] = await requests_of(client, orcid(1))
    response = await client.post(f"{API}/material-requests/{request['id']}/reject", json={})
    assert response.status_code == 409


async def test_request_includes_requester_email(client: AsyncClient) -> None:
    await login_as(client, orcid(1))
    request = await submit(client)
    assert request["user"]["email"] == "ada@example.org"
