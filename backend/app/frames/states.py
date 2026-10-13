"""Frame states and allowed transitions (requirements §6.2, §6.3)."""

from enum import StrEnum


class FrameState(StrEnum):
    RESERVED = "reserved"
    ISSUED = "issued"
    SHIPPED_TO_USER = "shipped_to_user"
    RECEIVED = "received"
    RECEIVED_ON_HOLD = "received_on_hold"
    EXTERNAL_STORAGE = "external_storage"
    INTERNAL_STORAGE = "internal_storage"
    SCHEDULED = "scheduled"
    LOADED = "loaded"
    RETURNED = "returned"
    VOID = "void"


S = FrameState
TERMINAL = {S.RETURNED, S.VOID}

# Allowed moves; who may trigger them is checked by the endpoints.
TRANSITIONS: dict[FrameState, set[FrameState]] = {
    S.RESERVED: {S.ISSUED, S.VOID},
    S.ISSUED: {S.SHIPPED_TO_USER, S.VOID},
    S.SHIPPED_TO_USER: {S.RECEIVED, S.RECEIVED_ON_HOLD, S.VOID},
    S.RECEIVED_ON_HOLD: {S.RECEIVED, S.RETURNED, S.VOID},
    S.RECEIVED: {S.EXTERNAL_STORAGE, S.INTERNAL_STORAGE, S.RETURNED, S.VOID},
    S.EXTERNAL_STORAGE: {S.INTERNAL_STORAGE, S.RETURNED, S.VOID},
    S.INTERNAL_STORAGE: {S.EXTERNAL_STORAGE, S.SCHEDULED, S.RETURNED, S.VOID},
    S.SCHEDULED: {S.INTERNAL_STORAGE, S.LOADED, S.VOID},
    S.LOADED: {S.INTERNAL_STORAGE, S.VOID},
    S.RETURNED: set(),
    S.VOID: set(),
}


def can_transition(current: FrameState, target: FrameState) -> bool:
    return target in TRANSITIONS[current]
