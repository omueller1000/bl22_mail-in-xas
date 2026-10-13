import pytest

from app.catalog import MAX_FRAMES_PER_REQUEST, PLATE_TYPES, Side, frame_range


@pytest.mark.parametrize(
    ("plates", "expected"),
    [
        ({"8-circle": 1}, (1, 1)),
        ({"8-circle": 4}, (2, 4)),
        ({"8-circle": 3, "8-slot": 2}, (3, 5)),
        # Gas plates take a whole frame each (requirements §7).
        ({"6-circle-gas": 2}, (2, 2)),
        ({"6-circle-gas": 2, "8-circle": 2}, (3, 4)),
        ({"6-circle-gas": 1, "8-circle": 3}, (3, 4)),
        # Frames only
        ({}, (1, MAX_FRAMES_PER_REQUEST)),
    ],
)
def test_frame_range(plates: dict[str, int], expected: tuple[int, int]) -> None:
    assert frame_range(plates) == expected


def test_gas_plate_is_left_only_and_blocks_right() -> None:
    gas = PLATE_TYPES["6-circle-gas"]
    assert gas.sides == [Side.LEFT]
    assert gas.blocks_other_side
    assert gas.positions == list("ABCDEF")


def test_obsolete_8_circle_gas_not_offered() -> None:
    assert set(PLATE_TYPES) == {"8-circle", "8-slot", "6-circle-gas"}
