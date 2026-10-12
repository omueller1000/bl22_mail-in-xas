"""Application settings, read from environment variables (prefix HT_XAS_) or a .env file."""

from enum import StrEnum
from functools import lru_cache

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"  # developer machine
    DEV = "dev"  # dev environment on the app VM
    PROD = "prod"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HT_XAS_", env_file=".env", extra="ignore")

    environment: Environment = Environment.LOCAL

    # Path under which all API routes are served. Proxies (nginx, Vite) forward requests
    # unchanged, so this must match the public URL path, e.g. /mail-in-xas/api.
    api_prefix: str = "/mail-in-xas/api"

    # Contains credentials; never log it.
    mongodb_uri: SecretStr
    mongodb_db: str

    # Fake ORCID login for development and tests. Forbidden in production.
    dev_login_enabled: bool = False

    @field_validator("api_prefix")
    @classmethod
    def _normalize_prefix(cls, value: str) -> str:
        value = "/" + value.strip("/")
        if value == "/":
            raise ValueError("api_prefix must not be empty")
        return value

    @model_validator(mode="after")
    def _forbid_dev_login_in_prod(self) -> "Settings":
        if self.environment is Environment.PROD and self.dev_login_enabled:
            raise ValueError("dev_login_enabled must not be set in the production environment")
        return self

    @property
    def docs_enabled(self) -> bool:
        return self.environment is not Environment.PROD


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # required values come from the environment
