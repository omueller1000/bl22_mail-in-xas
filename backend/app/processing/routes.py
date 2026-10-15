"""Admin page for the XAS processing parameters (app.processing.settings)."""

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict

from app.auth.dependencies import Admin, Db
from app.processing import settings
from app.processing.parameters import DEFAULTS

router = APIRouter(prefix="/admin/xas-parameters", tags=["xas parameters"])


class XasParameter(BaseModel):
    name: str
    group: str
    label: str
    unit: str
    minimum: float
    maximum: float
    integer: bool
    # If set, the value may be empty (null), meaning this.
    none_means: str | None
    value: float | None
    default: float | None


class XasParametersUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    values: dict[str, float | None]


@router.get("")
async def get_xas_parameters(_: Admin, db: Db) -> list[XasParameter]:
    return await _listing(db)


@router.put("")
async def set_xas_parameters(body: XasParametersUpdate, _: Admin, db: Db) -> list[XasParameter]:
    """Change parameters; they apply to all processing from now on."""
    try:
        await settings.save(db, body.values)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    return await _listing(db)


@router.delete("")
async def restore_xas_parameters(_: Admin, db: Db) -> list[XasParameter]:
    """Back to the defaults in the code."""
    await settings.restore_defaults(db)
    return await _listing(db)


async def _listing(db: Db) -> list[XasParameter]:
    params = await settings.current(db)

    def number(value: Any) -> float | None:
        return None if value is None else float(value)

    return [
        XasParameter(
            name=e.name,
            group=e.group,
            label=e.label,
            unit=e.unit,
            minimum=e.minimum,
            maximum=e.maximum,
            integer=e.integer,
            none_means=e.none_means,
            value=number(getattr(params, e.name)),
            default=number(getattr(DEFAULTS, e.name)),
        )
        for e in settings.EDITABLE
    ]
