import pytest
from pydantic import ValidationError

from tests.conftest import make_settings


def test_dev_login_forbidden_in_prod() -> None:
    with pytest.raises(ValidationError, match="dev_login_enabled"):
        make_settings(environment="prod", dev_login_enabled=True)


def test_dev_login_allowed_outside_prod() -> None:
    assert make_settings(environment="dev", dev_login_enabled=True).dev_login_enabled


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("/mail-in-xas/api", "/mail-in-xas/api"),
        ("mail-in-xas/dev/api/", "/mail-in-xas/dev/api"),
    ],
)
def test_api_prefix_is_normalized(raw: str, expected: str) -> None:
    assert make_settings(api_prefix=raw).api_prefix == expected


def test_empty_api_prefix_rejected() -> None:
    with pytest.raises(ValidationError):
        make_settings(api_prefix="/")


def test_mongodb_uri_hidden_in_repr() -> None:
    settings = make_settings(mongodb_uri="mongodb://user:s3cret@host/")
    assert "s3cret" not in repr(settings)
