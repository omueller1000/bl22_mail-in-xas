import pytest
from pydantic import ValidationError

from tests.conftest import make_settings, orcid


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


@pytest.mark.parametrize("raw", ["/", "/api", "/mail-in-xas"])
def test_invalid_api_prefix_rejected(raw: str) -> None:
    with pytest.raises(ValidationError):
        make_settings(api_prefix=raw)


def test_frontend_base_and_redirect_uri() -> None:
    settings = make_settings(
        api_prefix="/mail-in-xas/dev/api", public_origin="https://example.org/"
    )
    assert settings.frontend_base == "/mail-in-xas/dev/"
    assert settings.orcid_redirect_uri == (
        "https://example.org/mail-in-xas/dev/api/auth/orcid/callback"
    )


def test_mongodb_uri_hidden_in_repr() -> None:
    settings = make_settings(mongodb_uri="mongodb://user:s3cret@host/")
    assert "s3cret" not in repr(settings)


def test_bootstrap_admins_from_comma_separated_string() -> None:
    settings = make_settings(bootstrap_admin_orcids=f" {orcid(1)} ,{orcid(2)},")
    assert settings.bootstrap_admin_orcids == [orcid(1), orcid(2)]


def test_bootstrap_admins_must_be_valid() -> None:
    with pytest.raises(ValidationError, match="invalid ORCID"):
        make_settings(bootstrap_admin_orcids="0000-0000-0000-0000")


def test_session_cookie_differs_per_environment() -> None:
    names = {make_settings(environment=env).session_cookie_name for env in ("local", "dev", "prod")}
    assert len(names) == 3


def test_cookies_secure_only_in_prod() -> None:
    assert make_settings(environment="prod").cookie_secure
    assert not make_settings(environment="dev").cookie_secure
