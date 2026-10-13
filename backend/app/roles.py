from enum import StrEnum


class Role(StrEnum):
    """Person roles, in increasing order of privilege."""

    USER = "user"
    OPERATOR = "operator"
    ADMIN = "admin"

    def includes(self, required: "Role") -> bool:
        return _RANK[self] >= _RANK[required]


_RANK = {Role.USER: 0, Role.OPERATOR: 1, Role.ADMIN: 2}
