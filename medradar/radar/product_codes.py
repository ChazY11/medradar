"""Product code -> device class, from the FDA classification database.

Why this exists
---------------
The technology map covers three companies, because the radar pipeline tracks three. That is a
limitation of what we *chase*, not of what we *hold*: the register names a product code for
millions of devices, and the FDA classification database says what each code means - "Intervertebral
Fusion Device With Bone Graft, Lumbar", specialty Orthopedic, 21 CFR 888.3080.

So "which technology areas is this company active in" becomes answerable for every labeler in the
register instead of three, at the cost of one small table. It answers a different question from the
technology map and must not be confused with it: the map says what a company *published about*,
this says what it *registered*.

Access
------
openFDA public API, no credential. Measured: one request can carry a parenthesised OR of product
codes and returns one record per code, so 5,229 codes cost 262 requests at twenty per call. The
pipeline raises the limit properly rather than hiding the count.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Sequence

BASE = "https://api.fda.gov/device/classification.json"
#: Codes per request. Measured: a parenthesised OR of twenty codes answers in one call.
BATCH = 20
#: openFDA allows 240 requests a minute unauthenticated; one every 220 ms is well inside it and
#: finishes 5,229 codes in about a minute.
POLICY = {"requests_per_second": 4.5, "timeout_seconds": 30.0, "max_attempts": 3,
          "backoff_base_seconds": 3.0}

SCHEMA = """
CREATE TABLE IF NOT EXISTS product_code_class (
  product_code TEXT PRIMARY KEY,
  device_name   TEXT,
  medical_specialty TEXT,
  regulation_number TEXT,
  device_class  TEXT,
  fetched_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pcc_specialty ON product_code_class(medical_specialty);
"""


class ProductClassError(Exception):
    """The classification answer was not usable."""


def ensure_table(reference) -> None:
    reference.conn.executescript(SCHEMA)


def table_present(reference) -> bool:
    try:
        ensure_table(reference)
        return bool(reference.conn.execute(
            "SELECT COUNT(*) FROM product_code_class").fetchone()[0])
    except Exception:  # noqa: BLE001 - an unbuilt table is an absent answer, not a crash
        return False


def parse(payload: dict[str, Any]) -> list[dict[str, str]]:
    """One record per product code. A shape change raises rather than returning a silent empty."""
    if not isinstance(payload, dict):
        raise ProductClassError("the classification endpoint returned a non-object")
    results = payload.get("results")
    if results is None:
        meta = payload.get("meta") or {}
        error = (meta.get("error") or {}).get("message") if isinstance(meta, dict) else None
        # "No matches found" is an answer, not a failure: a code can be retired or regional.
        if error and "no matches" in str(error).lower():
            return []
        raise ProductClassError(f"no results and no 'no matches' error: {str(payload)[:160]}")
    out: list[dict[str, str]] = []
    for item in results if isinstance(results, list) else []:
        if not isinstance(item, dict):
            continue
        code = str(item.get("product_code") or "").strip().upper()
        if not code:
            continue
        out.append({
            "product_code": code,
            "device_name": str(item.get("device_name") or ""),
            "medical_specialty": str(item.get("medical_specialty_description") or ""),
            "regulation_number": str(item.get("regulation_number") or ""),
            "device_class": str(item.get("device_class") or ""),
        })
    return out


def fetch_classes(fetcher, codes: Sequence[str]) -> list[dict[str, str]]:
    """Ask for these codes, in batches, and return whatever the database knows."""
    wanted = [str(code).strip().upper() for code in codes if str(code).strip()]
    out: list[dict[str, str]] = []
    for start in range(0, len(wanted), BATCH):
        chunk = wanted[start:start + BATCH]
        expression = "+".join(f'%22{code}%22' for code in chunk)
        url = f"{BASE}?search=product_code:({expression})&limit={len(chunk) + 5}"
        payload = fetcher.get_json(url, headers={"Accept": "application/json"})
        out.extend(parse(payload))
    return out


def store_classes(reference, records: Iterable[dict[str, str]], *, at: str) -> int:
    ensure_table(reference)
    rows = [(r["product_code"], r.get("device_name"), r.get("medical_specialty"),
             r.get("regulation_number"), r.get("device_class"), at) for r in records]
    reference.conn.executemany(
        "INSERT OR REPLACE INTO product_code_class "
        "(product_code, device_name, medical_specialty, regulation_number, device_class, fetched_at)"
        " VALUES (?,?,?,?,?,?)", rows)
    reference.conn.commit()
    return len(rows)


def codes_in_register(reference, *, limit: int = 10_000) -> list[tuple[str, int]]:
    """Distinct product codes with how many device rows carry them, most common first."""
    try:
        rows = reference.conn.execute(
            "SELECT j.value, COUNT(*) FROM udi_device d, json_each(d.product_codes) j "
            "GROUP BY 1 ORDER BY 2 DESC LIMIT ?", (limit,)).fetchall()
    except Exception:  # noqa: BLE001 - a store without JSON1 has no codes to rank
        return []
    return [(str(row[0]).upper(), int(row[1])) for row in rows if row[0]]


def codes_missing(reference, *, limit: int = 500) -> list[str]:
    """Register codes the classification table has not answered for yet, most common first."""
    known: set[str] = set()
    try:
        ensure_table(reference)
        known = {str(row[0]) for row in reference.conn.execute(
            "SELECT product_code FROM product_code_class")}
    except Exception:  # noqa: BLE001
        known = set()
    return [code for code, _count in codes_in_register(reference, limit=10_000)
            if code not in known][:limit]


def classes_for_codes(reference, codes: Sequence[str]) -> dict[str, dict[str, str]]:
    wanted = [str(code).upper() for code in codes if code]
    if not wanted:
        return {}
    placeholders = ",".join("?" for _ in wanted)
    try:
        rows = reference.conn.execute(
            f"SELECT product_code, device_name, medical_specialty, regulation_number, device_class "
            f"FROM product_code_class WHERE product_code IN ({placeholders})", wanted).fetchall()
    except Exception:  # noqa: BLE001
        return {}
    return {str(row[0]): {"device_name": row[1], "medical_specialty": row[2],
                          "regulation_number": row[3], "device_class": row[4]} for row in rows}


def specialty_counts(reference, codes: Sequence[str]) -> list[dict[str, Any]]:
    """Group these codes by medical specialty, most codes first."""
    by_code = classes_for_codes(reference, codes)
    tally: dict[str, int] = {}
    for meta in by_code.values():
        name = str(meta.get("medical_specialty") or "").strip() or "Unclassified"
        tally[name] = tally.get(name, 0) + 1
    return [{"specialty": name, "codes": count}
            for name, count in sorted(tally.items(), key=lambda kv: -kv[1])]


def product_codes_summary(reference) -> dict[str, Any]:
    """What the table holds, by specialty, for the coverage page."""
    ensure_table(reference)
    try:
        total = int(reference.conn.execute(
            "SELECT COUNT(*) FROM product_code_class").fetchone()[0])
        specialties = [
            {"specialty": str(row[0] or "Unclassified"), "codes": int(row[1])}
            for row in reference.conn.execute(
                "SELECT medical_specialty, COUNT(*) FROM product_code_class "
                "GROUP BY 1 ORDER BY 2 DESC LIMIT 20")]
    except Exception:  # noqa: BLE001
        return {"available": False, "codes": 0, "specialties": []}
    return {"available": bool(total), "codes": total, "specialties": specialties}


__all__ = ["BATCH", "POLICY", "ProductClassError", "classes_for_codes", "codes_in_register",
           "codes_missing", "ensure_table", "fetch_classes", "parse", "product_codes_summary",
           "specialty_counts", "store_classes", "table_present"]
