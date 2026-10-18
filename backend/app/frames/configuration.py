"""Rules for configuring a frame: plates per side and sample positions (§5, §6.6, §8.1)."""

from typing import Any

from app.catalog import PLATE_TYPES, Side
from app.frames.states import FrameState

# Plates and sample placement can change only before the frame is shipped back (and declared).
CONFIGURABLE_STATES = {FrameState.ISSUED, FrameState.SHIPPED_TO_USER}


class ConfigurationError(ValueError):
    pass


def position_id(side: Side, label: str) -> str:
    """E.g. (Side.LEFT, "A") -> "Left-A"."""
    return f"{side.value.capitalize()}-{label}"


def check_plates(left: str | None, right: str | None) -> None:
    """Raise ConfigurationError unless the plates fit the frame (side rules of §5.1)."""
    for side, type_id in ((Side.LEFT, left), (Side.RIGHT, right)):
        if type_id is None:
            continue
        plate = PLATE_TYPES.get(type_id)
        if plate is None:
            raise ConfigurationError(f"Unknown plate type {type_id}")
        if side not in plate.sides:
            raise ConfigurationError(f"{plate.name} cannot be mounted on the {side.value} side")
        other = right if side is Side.LEFT else left
        if plate.blocks_other_side and other is not None:
            raise ConfigurationError(
                f"{plate.name} spans the whole frame; the other side must be empty"
            )


def positions_of(plates: dict[str, Any]) -> set[str]:
    """All position ids offered by the mounted plates."""
    result = set()
    for side in Side:
        type_id = plates.get(side.value)
        if type_id:
            result |= {position_id(side, label) for label in PLATE_TYPES[type_id].positions}
    return result


def changed_sides(old: dict[str, Any], new: dict[str, Any]) -> set[Side]:
    return {side for side in Side if old.get(side.value) != new.get(side.value)}


def side_of(position: str) -> Side:
    return Side(position.split("-", 1)[0].lower())


def why_not_configurable(frame: dict[str, Any]) -> str | None:
    """None if plates, note and positions may change; otherwise the reason."""
    if frame.get("safety_declared"):
        return "The frame has been declared safe; plates and samples can no longer change"
    if frame["state"] not in CONFIGURABLE_STATES:
        return "The frame is no longer with you"
    return None


# Measurements cannot change while the frame is with the beamline's scheduler or finished.
MEASUREMENTS_FROZEN_STATES = {
    FrameState.SCHEDULED,
    FrameState.LOADED,
    FrameState.RETURNING_TO_USER,
    FrameState.RETURNED,
    FrameState.VOID,
}


def why_measurements_frozen(frame: dict[str, Any]) -> str | None:
    """None if measurements may be added, edited or deleted; otherwise the reason (§6.6)."""
    if frame["state"] in MEASUREMENTS_FROZEN_STATES:
        return "Measurements cannot change while the frame is being measured or after it is done"
    if frame.get("locked"):
        return "The frame is locked; unlock it to change measurements"
    return None


def missing_for_declaration(frame: dict[str, Any], measurement_counts: dict[str, int]) -> list[str]:
    """What is still missing before the frame can be declared safe (§6.5); empty = complete."""
    plates = frame.get("plates") or {}
    occupied = {p["position"] for p in frame.get("positions", [])}
    problems = []
    if not any(plates.get(side.value) for side in Side):
        problems.append("Mount at least one plate")
    for side in Side:
        if plates.get(side.value) and not any(side_of(p) is side for p in occupied):
            problems.append(f"Place at least one sample on the {side.value} plate")
    for position in sorted(occupied):
        if not measurement_counts.get(position):
            problems.append(f"Add a measurement to {position}")
    return problems
