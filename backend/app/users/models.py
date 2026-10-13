"""API models for user accounts (requirements §4)."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.roles import Role


def _text(min_length: int, max_length: int) -> object:
    return StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length)


Name = Annotated[str, _text(1, 200)]
OptionalText = Annotated[str, _text(0, 200)] | None


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Address(_Model):
    """Shipping address; must accept international formats."""

    care_of: OptionalText = None
    street1: Annotated[str, _text(1, 200)]
    street2: OptionalText = None
    city: Annotated[str, _text(1, 100)]
    region: Annotated[str, _text(0, 100)] | None = Field(None, description="State or province")
    postal_code: Annotated[str, _text(0, 20)] | None = None
    country: Annotated[str, _text(2, 100)]


class Profile(_Model):
    """The fields a user can edit after registration."""

    email: EmailStr
    phone: Annotated[str, _text(5, 40)]
    affiliation: Annotated[str, _text(1, 200)]
    shipping_address: Address


class Registration(Profile):
    # Only used when ORCID did not provide a name; ignored otherwise.
    name: Name | None = None


class User(BaseModel):
    id: str
    orcid: str
    name: str
    role: Role
    email: EmailStr
    phone: str
    affiliation: str
    shipping_address: Address
    created_at: datetime


class RoleUpdate(_Model):
    role: Role
