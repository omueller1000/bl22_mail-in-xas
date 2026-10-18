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
    # Marked for return; leaves with the next shipment to the user (Shipping page).
    RETURNING_TO_USER = "returning_to_user"
    RETURNED = "returned"
    VOID = "void"


S = FrameState
TERMINAL = {S.RETURNED, S.VOID}

# Allowed moves; who may trigger them is checked by the endpoints.
TRANSITIONS: dict[FrameState, set[FrameState]] = {
    S.RESERVED: {S.ISSUED, S.VOID},
    S.ISSUED: {S.SHIPPED_TO_USER, S.VOID},
    S.SHIPPED_TO_USER: {S.RECEIVED, S.RECEIVED_ON_HOLD, S.VOID},
    S.RECEIVED_ON_HOLD: {S.RECEIVED, S.RETURNING_TO_USER, S.VOID},
    S.RECEIVED: {S.EXTERNAL_STORAGE, S.INTERNAL_STORAGE, S.RETURNING_TO_USER, S.VOID},
    S.EXTERNAL_STORAGE: {S.INTERNAL_STORAGE, S.RETURNING_TO_USER, S.VOID},
    S.INTERNAL_STORAGE: {S.EXTERNAL_STORAGE, S.SCHEDULED, S.RETURNING_TO_USER, S.VOID},
    S.SCHEDULED: {S.INTERNAL_STORAGE, S.LOADED, S.VOID},
    S.LOADED: {S.INTERNAL_STORAGE, S.VOID},
    # Shipped back; or taken out again if marked by mistake.
    S.RETURNING_TO_USER: {S.RETURNED, S.EXTERNAL_STORAGE, S.VOID},
    S.RETURNED: set(),
    S.VOID: set(),
}


def can_transition(current: FrameState, target: FrameState) -> bool:
    return target in TRANSITIONS[current]
