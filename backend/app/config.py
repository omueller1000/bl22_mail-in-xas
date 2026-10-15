"""Application settings, read from environment variables (prefix HT_XAS_) or a .env file."""

from datetime import timedelta
from enum import StrEnum
from functools import lru_cache
from typing import Annotated

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.orcid_id import is_valid_orcid


class Environment(StrEnum):
    LOCAL = "local"  # developer machine
    DEV = "dev"  # dev environment on the app VM
    PROD = "prod"


SESSION_LIFETIME = timedelta(days=7)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HT_XAS_", env_file=".env", extra="ignore")

    environment: Environment = Environment.LOCAL

    # Path under which all API routes are served. Proxies (nginx, Vite) forward requests
    # unchanged, so this must match the public URL path, e.g. /mail-in-xas/api.
    # The frontend lives one level up (e.g. /mail-in-xas/).
    api_prefix: str = "/mail-in-xas/api"

    # Scheme + host the browser uses, e.g. https://www-ssrl.slac.stanford.edu.
    # Used to build the ORCID callback URL and redirects back to the frontend.
    public_origin: str = "http://localhost:5180"

    # Contains credentials; never log it.
    mongodb_uri: SecretStr
    mongodb_db: str

    # ORCID OAuth client. https://orcid.org for production, https://sandbox.orcid.org for testing.
    # ORCID login is disabled while client id or secret is missing.
    orcid_base_url: str = "https://orcid.org"
    orcid_client_id: str | None = None
    orcid_client_secret: SecretStr | None = None

    # ORCID iDs that become Admin on registration or login (comma-separated).
    bootstrap_admin_orcids: Annotated[list[str], NoDecode] = []

    # Fake ORCID login for development and tests. Forbidden in production.
    dev_login_enabled: bool = False

    # Outgoing mail (requirements §6.8). Without smtp_host and mail_from_address nothing is sent;
    # emails stay in the outbox as failed with the reason.
    smtp_host: str | None = None
    smtp_port: int = 25
    smtp_starttls: bool = False
    # Used only if the server offers authentication.
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    mail_from_address: str | None = None
    mail_from_name: str = "BL22"
    # Outside production, mail never reaches real recipients: it goes to this address, or is
    # not sent at all if unset (it is still recorded, with its text, on the Admin -> Email page).
    mail_dev_redirect: str | None = None
    # Background sender that delivers the outbox; tests switch it off and deliver explicitly.
    mail_sender_enabled: bool = True

    @field_validator("api_prefix")
    @classmethod
    def _normalize_prefix(cls, value: str) -> str:
        value = "/" + value.strip("/")
        if not value.endswith("/api") or value == "/api":
            raise ValueError("api_prefix must be a sub-path ending in /api, e.g. /mail-in-xas/api")
        return value

    @field_validator("public_origin", "orcid_base_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("bootstrap_admin_orcids", mode="before")
    @classmethod
    def _split_orcids(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("bootstrap_admin_orcids")
    @classmethod
    def _check_orcids(cls, value: list[str]) -> list[str]:
        invalid = [orcid for orcid in value if not is_valid_orcid(orcid)]
        if invalid:
            raise ValueError(f"invalid ORCID iD(s): {', '.join(invalid)}")
        return value

    @model_validator(mode="after")
    def _forbid_dev_login_in_prod(self) -> "Settings":
        if self.environment is Environment.PROD and self.dev_login_enabled:
            raise ValueError("dev_login_enabled must not be set in the production environment")
        return self

    @property
    def docs_enabled(self) -> bool:
        return self.environment is not Environment.PROD

    @property
    def frontend_base(self) -> str:
        """Frontend path with trailing slash, e.g. /mail-in-xas/."""
        return self.api_prefix.removesuffix("api")

    @property
    def portal_url(self) -> str:
        """Public URL of the frontend, e.g. https://www-ssrl.slac.stanford.edu/mail-in-xas/."""
        return f"{self.public_origin}{self.frontend_base}"

    @property
    def orcid_login_enabled(self) -> bool:
        return bool(self.orcid_client_id and self.orcid_client_secret)

    @property
    def orcid_redirect_uri(self) -> str:
        return f"{self.public_origin}{self.api_prefix}/auth/orcid/callback"

    @property
    def session_cookie_name(self) -> str:
        # Different names per environment, so prod and dev sessions never mix.
        if self.environment is Environment.PROD:
            return "ht_xas_session"
        return f"ht_xas_{self.environment}_session"

    @property
    def cookie_secure(self) -> bool:
        # Production is HTTPS-only; dev (internal VM hostname) and local run over plain HTTP.
        return self.environment is Environment.PROD


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # required values come from the environment
