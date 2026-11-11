"""Single source of truth for UDI-DI / GTIN-14 handling in the P0-B reconciliation.

`normalize_di` and `is_gtin_like` are byte-for-byte copies of
`medradar/atlas/identity/normalize.py` (ATLAS's own definitions, so the
reconciliation measures the same class ATLAS measured). `gtin14_check_digit_ok`
is new: ATLAS never validates the GS1 check digit, and this report does.

Kept dependency-free so the analysis scripts and the tests agree exactly.
"""

from __future__ import annotations

import re
from typing import Any

GTIN14_RE = re.compile(r"^\d{14}$")
# Identical to medradar/atlas/identity/normalize.py::_DI_SEP
DI_SEP_RE = re.compile(r"[\s\-]")


def normalize_di(value: Any) -> str:
    """UDI-DI: digits only, separators removed. Leading zeros are kept."""
    if value is None:
        return ""
    return DI_SEP_RE.sub("", str(value)).strip()


def is_gtin_like(value: Any) -> bool:
    """ATLAS's class: separator-normalised value is exactly 14 digits (no check digit)."""
    text = normalize_di(value)
    return len(text) == 14 and text.isdigit()


def gtin14_check_digit_ok(value: Any) -> bool:
    """GS1 GTIN-14 Mod-10 check digit.

    For digits d1..d14, weight d1..d13 by 3,1,3,1,... starting at 3, sum, and
    require d14 to be the value that rounds the sum up to the next multiple of 10.
    Returns False for anything that is not exactly 14 digits.
    """
    text = normalize_di(value)
    if not GTIN14_RE.match(text):
        return False
    total = sum((ord(c) - 48) * (3 if i % 2 == 0 else 1) for i, c in enumerate(text[:13]))
    return ((10 - total % 10) % 10) == (ord(text[13]) - 48)


__all__ = ["GTIN14_RE", "DI_SEP_RE", "normalize_di", "is_gtin_like", "gtin14_check_digit_ok"]
