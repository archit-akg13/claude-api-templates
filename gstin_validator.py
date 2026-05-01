"""
gstin_validator.py — GSTIN format and checksum validator.

GSTIN is the 15-character Goods and Services Tax Identification Number used in India.

Format: <state_code(2)><PAN(10)><entity_code(1)>Z<checksum(1)>
- positions 1-2: state code (digits 01-37)
- positions 3-12: 10-character PAN (5 letters + 4 digits + 1 letter)
- position 13: entity number for the same PAN holder in a state
- position 14: always 'Z'
- position 15: checksum (digit or uppercase letter)

The checksum is computed using a base-36 weighted scheme published by GSTN.

Usage:
    python gstin_validator.py 27AAAPL1234C1Z5
    python gstin_validator.py < gstins.txt   # one per line

Exit codes: 0 = all valid, 1 = at least one invalid, 2 = usage error.
"""
import re
import sys
from typing import Iterable

GSTIN_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]$")
ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
CODE_POINT = {c: i for i, c in enumerate(ALPHABET)}


def _checksum(first_14: str) -> str:
    """Return the GSTN checksum character for the first 14 characters."""
    factor, total, mod = 0, 0, 36
    for i, ch in enumerate(first_14):
        factor = 2 if (i % 2 == 0) else 1
        digit = CODE_POINT[ch] * factor
        digit = (digit // mod) + (digit % mod)
        total += digit
    remainder = total % mod
    check_code = (mod - remainder) % mod
    return ALPHABET[check_code]


def is_valid_gstin(value: str) -> bool:
    """Return True iff value is a syntactically and checksum-valid GSTIN."""
    if not value or not GSTIN_RE.match(value):
        return False
    return _checksum(value[:14]) == value[14]


def validate_many(values: Iterable[str]) -> list[tuple[str, bool]]:
    return [(v.strip(), is_valid_gstin(v.strip())) for v in values if v.strip()]


def _read_inputs(argv: list[str]) -> list[str]:
    if len(argv) > 1:
        return argv[1:]
    if not sys.stdin.isatty():
        return [line for line in sys.stdin.read().splitlines() if line.strip()]
    return []


def main(argv: list[str]) -> int:
    items = _read_inputs(argv)
    if not items:
        print("usage: gstin_validator.py <GSTIN> [GSTIN ...]   or pipe via stdin", file=sys.stderr)
        return 2
    results = validate_many(items)
    bad = 0
    for gstin, ok in results:
        print(f"{'OK  ' if ok else 'BAD '} {gstin}")
        bad += 0 if ok else 1
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

