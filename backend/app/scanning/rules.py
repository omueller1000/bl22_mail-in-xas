"""What a barcode scan does to a frame (requirements §6.3, §9.1).

Group scan actions move every scanned frame that may make the move; the others are reported
with the reason and stay where they are.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.frames.states import TERMINAL, FrameState, can_transition

S = FrameState


class ScanAction(StrEnum):
    RECEIVE = "receive"
    EXTERNAL_STORAGE = "external_storage"
    RETURN = "return"
    VOID = "void"


# States from which each action may start (on top of the general transition table).
_ALLOWED_FROM: dict[ScanAction, set[FrameState]] = {
    ScanAction.RECEIVE: {S.SHIPPED_TO_USER},
    ScanAction.EXTERNAL_STORAGE: {S.RECEIVED, S.INTERNAL_STORAGE},
    ScanAction.RETURN: {S.RECEIVED, S.RECEIVED_ON_HOLD, S.EXTERNAL_STORAGE, S.INTERNAL_STORAGE},
    ScanAction.VOID: set(FrameState) - TERMINAL,
}

# States in which a frame occupies an internal-storage slot.
SLOT_STATES = {S.INTERNAL_STORAGE, S.SCHEDULED, S.LOADED}


@dataclass(frozen=True)
class Outcome:
    target: FrameState | None  # None: the frame cannot make this move
    problem: str | None = None
    warning: str | None = None


def outcome(action: ScanAction, frame: dict[str, Any] | None) -> Outcome:
    if frame is None:
        return Outcome(None, problem="Unknown barcode")
    current = FrameState(frame["state"])
    if current not in _ALLOWED_FROM[action]:
        return Outcome(None, problem=f"Not possible from state {current.value}")

    if action is ScanAction.RECEIVE:
        if not frame.get("safety_declared"):
            return Outcome(S.RECEIVED_ON_HOLD, warning="Not declared safe: put on hold")
        if not frame.get("locked"):
            return Outcome(S.RECEIVED, warning="Not locked")
        return Outcome(S.RECEIVED)

    target = {
        ScanAction.EXTERNAL_STORAGE: S.EXTERNAL_STORAGE,
        ScanAction.RETURN: S.RETURNED,
        ScanAction.VOID: S.VOID,
    }[action]
    assert can_transition(current, target)
    return Outcome(target)


def leaves_slot(target: FrameState) -> bool:
    return target not in SLOT_STATES
