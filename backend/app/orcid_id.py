"""ORCID iD format and checksum (ISO 7064 MOD 11-2), see
https://support.orcid.org/hc/en-us/articles/360006897674
"""

import re
from typing import Annotated

from pydantic import AfterValidator

_ORCID_PATTERN = re.compile(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]")


def is_valid_orcid(value: str) -> bool:
    if not _ORCID_PATTERN.fullmatch(value):
        return False
    total = 0
    for digit in value.replace("-", "")[:-1]:
        total = (total + int(digit)) * 2
    check = (12 - total % 11) % 11
    return value[-1] == ("X" if check == 10 else str(check))


def _validate(value: str) -> str:
    value = value.strip().upper()
    if not is_valid_orcid(value):
        raise ValueError("not a valid ORCID iD (format 0000-0000-0000-0000)")
    return value


OrcidId = Annotated[str, AfterValidator(_validate)]
