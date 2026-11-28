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


def _company_table(reference: Any) -> tuple[list[str], list[str]]:
    """Same shape as _brand_table, for company names. Measured: 12,392 names in 1.5 s."""
    try:
        path = str(reference.path)
        key = ("company", path, os.path.getmtime(path))
    except Exception:  # noqa: BLE001
        key = None
    if key is not None:
        hit = _CACHE.get(key)
        if hit is not None:
            return hit
    try:
        rows = reference.conn.execute(
            "SELECT DISTINCT company_name FROM udi_device"
            " WHERE company_name IS NOT NULL AND company_name <> ''").fetchall()
    except Exception:  # noqa: BLE001
        return [], []
    pairs = sorted((str(row[0]).upper(), str(row[0])) for row in rows if row[0])
    keys = [pair[0] for pair in pairs]
    values = [pair[1] for pair in pairs]
    if key is not None:
        _CACHE[key] = (keys, values)
    return keys, values


def _match(keys: list[str], values: list[str], needle: str, limit: int) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    start = bisect.bisect_left(keys, needle)
    while start < len(keys) and keys[start].startswith(needle) and len(found) < limit:
        if values[start] not in seen:
            seen.add(values[start])
            found.append(values[start])
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


def suggest_companies(reference: Any, query: str, *, limit: int = 5) -> list[str]:
    """Registered company names close to the query.

    Substring first, then near-misses by edit distance. Measured 2026-11-28: `Medtron` already resolves
    through the page's own contains-scan, so substring adds nothing there - but `Medtronix` (a typo) matches
    no registered name as a substring, and that is the case a reader needs help with. Twelve thousand names
    make difflib affordable; the 339,101 brand names do not, so brands stay substring-only.
    """
    text = " ".join(str(query or "").split())
    if len(text) < 3:
        return []
    keys, values = _company_table(reference)
    if not keys:
        return []
    found = _match(keys, values, text.upper(), limit)
    if found:
        return found
    import difflib

    # A legal name carries a suffix ("MEDTRONIC, INC."), which drags the ratio down: `Medtronix` scored under
    # 0.72 against every real name and over 0.6 against several unrelated ones, and difflib's own ordering put
    # METALOGIX above MEDTRONIC. So take a wider net at 0.6 and rank by similarity to the *head* of the name,
    # which is the part a reader is typing.
    needle = text.upper()
    candidates = difflib.get_close_matches(needle, keys, n=max(limit * 6, 12), cutoff=0.6)
    scored = []
    for key in candidates:
        head = key[: len(needle) + 4]
        scored.append((difflib.SequenceMatcher(None, needle, head).ratio(), key))
    scored.sort(reverse=True)
    return [values[keys.index(key)] for _score, key in scored[:limit]]


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
    return _match(keys, values, text.upper(), limit)
