"""Shared ISO-8601 timestamp parsing/rendering primitives.

The TKG store and the forecast registry both accept strict UTC ISO-8601
timestamps (``requires-python >=3.10``). Python 3.10's
``datetime.fromisoformat`` only accepts fractional seconds with exactly 3 or 6
digits (3.11+ relaxed this to 1-9 digits), so a value such as
``2024-01-01T00:00:00.5Z`` raises ``ValueError`` on 3.10 while working on
3.11+. The parsing helper here normalises any 1-9 digit fraction to exactly 6
digits (right-padded, truncated past microsecond precision) *before* calling
``fromisoformat``, so behaviour is identical on every supported interpreter.

Rendering is the other half of the contract: every stored/comparison timestamp
uses fixed-width 6-digit microseconds so that lexicographic order equals
chronological order (``'Z' > '.'`` would otherwise break same-second cuts).
"""

from __future__ import annotations

import re
from datetime import datetime

# Fractional-seconds group: 1-9 digits (each extra digit is sub-microsecond and
# is truncated). Anchored on a literal dot, which ISO-8601 only uses for the
# fractional second in the timestamp shapes accepted here.
_FRACTION = re.compile(r"\.(\d{1,9})")
_MICROSECOND_DIGITS = 6


def normalize_fraction(text: str) -> str:
    """Pad/truncate a fractional-second field to exactly 6 digits.

    ``'.5'`` -> ``'.500000'``, ``'.1234'`` -> ``'.123400'``,
    ``'.1234567'`` -> ``'.123456'`` (sub-microsecond digits are truncated, not
    rounded). Strings without a fraction are returned unchanged.
    """
    return _FRACTION.sub(
        lambda match: "." + (match.group(1) + "0" * _MICROSECOND_DIGITS)[:_MICROSECOND_DIGITS],
        text,
    )


def parse_iso8601(text: str) -> datetime:
    """Parse an ISO-8601 timestamp with py3.10-3.13-identical fraction handling.

    Accepts a trailing ``Z`` (normalised to ``+00:00``) and 1-9 fractional
    digits. Offsets and other shapes are left to ``datetime.fromisoformat``;
    ``ValueError`` is re-raised unchanged so callers keep their own error type
    and message.
    """
    return datetime.fromisoformat(normalize_fraction(text.replace("Z", "+00:00")))


def render_moment(utc: datetime) -> str:
    """Render an aware UTC datetime in the canonical fixed-width form."""
    return f"{utc:%Y-%m-%dT%H:%M:%S}.{utc.microsecond:06d}Z"
