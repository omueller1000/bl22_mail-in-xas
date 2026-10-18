"""Frame barcodes (requirements §6.1).

New codes look like KQZ-TBM: five random letters and a check letter (Luhn mod 26), shown as
3 + 3. The check letter catches every single mistyped letter and almost every swap of two
neighbouring letters, without asking the database. Codes of the old format ABCD-EFGH (eight
letters, no check letter) are already printed on frames and stay valid; they are no longer
generated.
"""

import re
import secrets
import string

ALPHABET = string.ascii_uppercase
N = len(ALPHABET)

NEW_PATTERN = re.compile(r"[A-Z]{3}-[A-Z]{3}")
OLD_PATTERN = re.compile(r"[A-Z]{4}-[A-Z]{4}")


def check_letter(payload: str) -> str:
    """Luhn mod 26 check letter for the given letters."""
    total = 0
    factor = 2
    for char in reversed(payload):
        addend = factor * ALPHABET.index(char)
        total += addend // N + addend % N
        factor = 1 if factor == 2 else 2
    return ALPHABET[(N - total % N) % N]


def new_barcode() -> str:
    """A random new-format barcode, e.g. KQZ-TBM (26^5 ≈ 11.9 million codes)."""
    payload = "".join(secrets.choice(ALPHABET) for _ in range(5))
    code = payload + check_letter(payload)
    return f"{code[:3]}-{code[3:]}"


def problem(code: str) -> str | None:
    """Why the (normalised) code is not a valid barcode, or None if it is."""
    if OLD_PATTERN.fullmatch(code):
        return None
    if not NEW_PATTERN.fullmatch(code):
        return "barcode must look like ABC-DEF"
    letters = code.replace("-", "")
    if check_letter(letters[:5]) != letters[5]:
        return "check letter does not match: mistyped barcode?"
    return None
