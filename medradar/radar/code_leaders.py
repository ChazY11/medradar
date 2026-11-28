"""Who else registers under the same product code, materialised.

The question a reader asks about one device - "who else sells in this category, and how big are they" - is
answerable from the register, but not from a page: grouping 5.2M devices by (code, company) takes 12.4 s on the
production store (measured 2026-11-29, 73,462 pairs), and a per-code lookup is worse at 14.6 s because it cannot
use the grouping.

So the night computes it and the page reads one indexed row per code. Same rule as the counts and the trend
table: a number needed on every visit is computed when nobody is waiting, and the page prints when.

Only the top few companies per code are kept - the list answers "who is big here", not "list everyone".
"""

from __future__ import annotations

import os
from typing import Any, Iterable, Mapping, Sequence

_TABLE = """
CREATE TABLE IF NOT EXISTS code_leader (
    code         TEXT NOT NULL,
    rank         INTEGER NOT NULL,
    company_name TEXT NOT NULL,
    devices      INTEGER NOT NULL,
    computed_at  TEXT NOT NULL,
    PRIMARY KEY (code, rank)
)
"""


def store_leaders(reference: Any, *, top: int = 5, at: str | None = None) -> dict[str, Any]:
    """Rebuild the leader table: the biggest registrants per product code.

    The grouping is one pass over the register with `json_each` over the product-code array. It is the only
    query in this module, and it is why the result is materialised rather than computed per request.
    """
    from .watermark import utc_today

    stamp = str(at or utc_today())
    reference.conn.executescript(_TABLE)
    try:
        # Joined to udi_premarket like `product_code_census`, so a leader's device count and a code's device
        # count measure the same population. Without the join the field page showed "DZE 321 台" beside
        # "头名 2,157" on one row - the leader appearing to own more devices than the code contains.
        rows = reference.conn.execute(
            "SELECT j.value AS code, d.company_name, COUNT(*) AS n"
            " FROM udi_premarket p"
            " JOIN udi_device d ON d.device_key = p.device_key, json_each(d.product_codes) j"
            " WHERE d.company_name IS NOT NULL AND d.company_name <> ''"
            " GROUP BY code, d.company_name").fetchall()
    except Exception:  # noqa: BLE001 - no json1 or no table: an empty leader table, reported by the caller
        return {"codes": 0, "rows": 0, "computed_at": stamp}
    best: dict[str, list[tuple[str, int]]] = {}
    for code, company, count in rows:
        key = str(code)
        bucket = best.setdefault(key, [])
        bucket.append((str(company), int(count or 0)))
        if len(bucket) > top * 4:
            bucket.sort(key=lambda item: -item[1])
            del bucket[top:]
    reference.conn.execute("DELETE FROM code_leader")
    written = 0
    for code, bucket in best.items():
        bucket.sort(key=lambda item: -item[1])
        for rank, (company, count) in enumerate(bucket[:top], start=1):
            reference.conn.execute(
                "INSERT OR REPLACE INTO code_leader (code, rank, company_name, devices, computed_at)"
                " VALUES (?,?,?,?,?)", (code, rank, company, count, stamp))
            written += 1
    reference.conn.commit()
    return {"codes": len(best), "rows": written, "computed_at": stamp}


def leaders_for(reference: Any, codes: Iterable[str], *,
                limit: int = 5) -> dict[str, list[dict[str, Any]]]:
    """The leaders of each code, in rank order. An unbuilt table yields an empty mapping."""
    wanted = [str(code) for code in codes if str(code).strip()]
    if not wanted:
        return {}
    marks = ",".join("?" for _ in wanted)
    try:
        rows = reference.conn.execute(
            f"SELECT code, rank, company_name, devices, computed_at FROM code_leader"
            f" WHERE code IN ({marks}) ORDER BY code, rank", tuple(wanted)).fetchall()
    except Exception:  # noqa: BLE001 - not built yet is a state, not a crash
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for code, rank, company, devices, stamp in rows:
        out.setdefault(str(code), [])
        if len(out[str(code)]) < limit:
            out[str(code)].append({"rank": int(rank), "company_name": str(company),
                                   "devices": int(devices or 0), "computed_at": str(stamp or "")})
    return out


def ranks_for_company(reference: Any, company_name: str,
                       codes: Iterable[str] | None = None) -> dict[str, dict[str, Any]]:
    """This company's rank inside each of its own product codes.

    The table keeps the top five per code, so a company outside the top five of a code it registers in is
    absent - which means "not in the top five", not "not there". The caller says so; this returns only what it
    knows.
    """
    name = str(company_name or "").strip()
    if not name:
        return {}
    params: list[Any] = [name]
    clause = ""
    wanted = [str(code) for code in (codes or []) if str(code).strip()]
    if wanted:
        clause = f" AND code IN ({','.join('?' for _ in wanted)})"
        params.extend(wanted)
    try:
        rows = reference.conn.execute(
            "SELECT code, rank, devices, computed_at FROM code_leader"
            f" WHERE company_name = ? COLLATE NOCASE{clause} ORDER BY rank", tuple(params)).fetchall()
    except Exception:  # noqa: BLE001 - no table, nothing to rank
        return {}
    return {str(code): {"rank": int(rank), "devices": int(devices or 0),
                        "computed_at": str(stamp or "")}
            for code, rank, devices, stamp in rows}


def status(reference: Any) -> dict[str, Any]:
    """Present, readable, rows, stamp - the same question `materialised.py` asks of every table."""
    try:
        row = reference.conn.execute(
            "SELECT COUNT(*), MAX(computed_at) FROM code_leader").fetchone()
        return {"present": True, "readable": True, "rows": int(row[0] or 0),
                "stamp": str(row[1] or "")}
    except Exception as error:  # noqa: BLE001 - the reason is the payload
        message = str(error) or type(error).__name__
        return {"present": "no such table" not in message.lower(), "readable": False, "rows": 0,
                "stamp": "", "error": "" if "no such table" in message.lower() else message}
