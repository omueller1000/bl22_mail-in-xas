"""Barcode format and check letter (app.frames.barcodes)."""

import string

import pytest

from app.frames.barcodes import NEW_PATTERN, check_letter, new_barcode, problem


def test_new_codes_have_a_valid_check_letter() -> None:
    for _ in range(200):
        code = new_barcode()
        assert NEW_PATTERN.fullmatch(code)
        assert problem(code) is None


def test_check_letter_is_luhn_mod_26() -> None:
    # A=0 ... Z=25. From the right, every other value is doubled and its two base-26 digits
    # added: B 2, T 19, Z 50 -> 1 + 24 = 25, Q 16, K 20; sum 82, 82 mod 26 = 4, 26 - 4 = 22 = W.
    assert check_letter("AAAAA") == "A"
    assert check_letter("KQZTB") == "W"


def test_every_single_mistyped_letter_is_caught() -> None:
    letters = "KQZTBW"
    for i in range(6):
        for char in string.ascii_uppercase:
            if char == letters[i]:
                continue
            typo = letters[:i] + char + letters[i + 1 :]
            assert problem(f"{typo[:3]}-{typo[3:]}") is not None, typo


@pytest.mark.parametrize(
    ("code", "message"),
    [
        ("KQZ-TBW", None),
        ("KQZ-TBM", "check letter does not match: mistyped barcode?"),
        ("ABCD-EFGH", None),  # old format, already printed on frames
        ("KQZTBW", "barcode must look like ABC-DEF"),
        ("KQ-ZTBW", "barcode must look like ABC-DEF"),
        ("ABC-DE1", "barcode must look like ABC-DEF"),
    ],
)
def test_formats(code: str, message: str | None) -> None:
    assert problem(code) == message
