"""Name suggestions for a query that found nothing.

A miss on /device costs a second of scanning and then says "not in the register", which is true and
useless: measured 2026-11-28, `Clydesdal` (one letter short) matched three registered brands by substring
and the page offered none of them.

Three ways to get these were measured on the production store:

    LIKE '%term%'   1,537 ms   full scan, no index can help
    LIKE 'term%'      681 ms   still scans: idx_udi_brand is on a normalised expression, not raw text
    in memory          0.05 ms  339,101 distinct brand names, built once in 1.3 s, bisected after that

So the list is built once per store revision and kept: a miss pays 1.3 s the first time and nothing after.
The suggestions are **registered brand strings**, not guesses - a reader clicks one and the register answers.
"""

from __future__ import annotations

import bisect
import os
from typing import Any

_CACHE: dict[tuple[str, float], tuple[list[str], list[str]]] = {}


def _brand_table(reference: Any) -> tuple[list[str], list[str]]:
    """Sorted uppercase keys and the original strings, cached against the store's path and mtime."""
    try:
        path = str(reference.path)
        key = (path, os.path.getmtime(path))
    except Exception:  # noqa: BLE001 - no cache key, still answer
        key = None
    if key is not None:
        hit = _CACHE.get(key)
        if hit is not None:
            return hit
    try:
        rows = reference.conn.execute(
            "SELECT DISTINCT brand_name FROM udi_device"
            " WHERE brand_name IS NOT NULL AND brand_name <> ''").fetchall()
    except Exception:  # noqa: BLE001 - no table, no suggestions
        return [], []
    pairs = sorted((str(row[0]).upper(), str(row[0])) for row in rows if row[0])
    keys = [pair[0] for pair in pairs]
    values = [pair[1] for pair in pairs]
    if key is not None:
        _CACHE.clear()
        _CACHE[key] = (keys, values)
    return keys, values


def suggest_brands(reference: Any, query: str, *, limit: int = 5) -> list[str]:
    """Registered brand names that contain the query, prefix matches first.

    Prefix first because that is what a truncated word looks like; substring second because a reader may
    have dropped the middle of a long name. Both return the register's own spelling.
    """
    text = " ".join(str(query or "").split())
    if len(text) < 3:
        return []
    keys, values = _brand_table(reference)
    if not keys:
        return []
    needle = text.upper()
    found: list[str] = []
    seen: set[str] = set()

    start = bisect.bisect_left(keys, needle)
    while start < len(keys) and keys[start].startswith(needle) and len(found) < limit:
        value = values[start]
        if value not in seen:
            seen.add(value)
            found.append(value)
        start += 1
    if len(found) >= limit:
        return found
    for key, value in zip(keys, values):
        if needle in key and value not in seen:
            seen.add(value)
            found.append(value)
            if len(found) >= limit:
                break
    return found
