import pytest

from app.orcid_id import is_valid_orcid
from tests.conftest import orcid


@pytest.mark.parametrize(
    "value",
    # Examples from ORCID's documentation, incl. one with check character X.
    ["0000-0002-1825-0097", "0000-0001-5109-3700", "0000-0002-1694-233X"],
)
def test_valid(value: str) -> None:
    assert is_valid_orcid(value)


@pytest.mark.parametrize(
    "value",
    [
        "0000-0002-1825-0098",  # wrong check digit
        "0000000218250097",  # no dashes
        "0000-0002-1825-009",  # too short
        "https://orcid.org/0000-0002-1825-0097",
    ],
)
def test_invalid(value: str) -> None:
    assert not is_valid_orcid(value)


def test_test_helper_generates_valid_ids() -> None:
    assert all(is_valid_orcid(orcid(n)) for n in range(1, 50))
