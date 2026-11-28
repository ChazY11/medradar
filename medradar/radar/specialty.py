"""How the register splits across medical specialties, and who leads each.

Why this is a table and not a query
------------------------------------
The aggregation joins 5.2M device rows against their JSON product codes and the FDA classification
table. Measured: 29 s. That is a job, not a request, so it is computed by the nightly pass and read
from here.

What it does and does not say
-----------------------------
This counts what manufacturers **registered**. A company with many devices in a specialty covers that
field broadly; it says nothing about whether its technology leads. Devices carry several product
codes, so a row's count repeats a device across every specialty it touches, and the rows sum to more
than the register holds - the page says so rather than presenting the column as a census.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS specialty_stats (
  specialty     TEXT PRIMARY KEY,
  codes         INTEGER NOT NULL DEFAULT 0,
  devices       INTEGER NOT NULL DEFAULT 0,
  companies     INTEGER NOT NULL DEFAULT 0,
  top_companies TEXT,
  updated_at    TEXT NOT NULL
);

-- Who is in one specialty, ranked. Kept as rows rather than JSON in the row above so a single
-- specialty page can page through its own leaders without reading nineteen others.
CREATE TABLE IF NOT EXISTS specialty_company (
  specialty    TEXT NOT NULL,
  company_name TEXT NOT NULL,
  devices      INTEGER NOT NULL,
  rank         INTEGER NOT NULL,
  updated_at   TEXT NOT NULL,
  PRIMARY KEY (specialty, company_name)
);
CREATE INDEX IF NOT EXISTS idx_spec_company ON specialty_company(specialty, rank);
"""

#: Leaders kept per specialty. Deeper than the five shown on /areas, and enough to fill a page.
LEADERS_KEPT = 50

BY_SPECIALTY = """
SELECT pcc.medical_specialty AS sp,
       COUNT(DISTINCT pcc.product_code) AS codes,
       COUNT(DISTINCT d.device_key) AS devices,
       COUNT(DISTINCT d.labeler_duns) AS companies
  FROM udi_device d, json_each(d.product_codes) j
  JOIN product_code_class pcc ON pcc.product_code = UPPER(j.value)
 GROUP BY sp
"""

BY_COMPANY = """
SELECT pcc.medical_specialty AS sp, d.company_name AS company, COUNT(*) AS devices
  FROM udi_device d, json_each(d.product_codes) j
  JOIN product_code_class pcc ON pcc.product_code = UPPER(j.value)
 WHERE d.company_name IS NOT NULL AND d.company_name <> ''
 GROUP BY sp, company
"""


def ensure_table(reference) -> None:
    reference.conn.executescript(SCHEMA)


def refresh(reference, *, leaders: int = 5) -> dict[str, Any]:
    ensure_table(reference)
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    totals = {str(row[0]): {"codes": int(row[1]), "devices": int(row[2]),
                            "companies": int(row[3])}
              for row in reference.conn.execute(BY_SPECIALTY)}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for specialty, company, devices in reference.conn.execute(BY_COMPANY):
        grouped.setdefault(str(specialty), []).append(
            {"company": str(company), "devices": int(devices)})
    rows = []
    ranking_rows = []
    for specialty, data in totals.items():
        ordered = sorted(grouped.get(specialty, []), key=lambda item: -int(item["devices"]))
        top = ordered[:leaders]
        rows.append((specialty, data["codes"], data["devices"], data["companies"],
                     json.dumps(top, ensure_ascii=False), at))
        for position, item in enumerate(ordered[:LEADERS_KEPT], start=1):
            ranking_rows.append((specialty, item["company"], int(item["devices"]), position, at))
    reference.conn.execute("DELETE FROM specialty_stats")
    reference.conn.executemany(
        "INSERT OR REPLACE INTO specialty_stats "
        "(specialty, codes, devices, companies, top_companies, updated_at) VALUES (?,?,?,?,?,?)",
        rows)
    reference.conn.execute("DELETE FROM specialty_company")
    reference.conn.executemany(
        "INSERT OR REPLACE INTO specialty_company "
        "(specialty, company_name, devices, rank, updated_at) VALUES (?,?,?,?,?)",
        ranking_rows)
    reference.conn.commit()
    return {"updated_at": at, "specialties": len(rows), "ranked_rows": len(ranking_rows)}


def failure_shape(reference, specialty: str, *, limit: int = 6) -> dict[str, Any]:
    """MAUDE reports by product code within one specialty, plus the event-type split.

    Measured 2026-11-28 on the live store: Dental 12,428 reports across its 295 product codes, DZE
    alone 1,653 - the same code the device page shows as a shelf of 321 registered devices, so a
    reader can see that one code carries both scale and reports. With idx_failure_code this is 3+7 ms;
    without it the same pair was two full scans of 348,742 rows at 100 ms each.

    MAUDE is voluntary reporting, so these are counts of what was reported, not failure rates. The page
    says so; this function only returns the numbers.
    """
    codes = [str(row[0]) for row in reference.conn.execute(
        "SELECT product_code FROM product_code_class WHERE medical_specialty = ?",
        (specialty,)).fetchall()]
    if not codes:
        return {"codes": 0, "total": 0, "by_code": [], "by_event": {}, "names": {}}
    marks = ",".join("?" * len(codes))
    try:
        by_code = [{"code": str(row[0]), "reports": int(row[1] or 0)} for row in reference.conn.execute(
            f"SELECT product_code, COUNT(*) AS n FROM maude_failure_index"
            f" WHERE product_code IN ({marks}) GROUP BY 1 ORDER BY n DESC LIMIT ?",
            (*codes, int(limit))).fetchall()]
        by_event = {str(row[0] or "未标注"): int(row[1] or 0) for row in reference.conn.execute(
            f"SELECT event_type, COUNT(*) FROM maude_failure_index"
            f" WHERE product_code IN ({marks}) GROUP BY 1", codes).fetchall()}
        total = int(reference.conn.execute(
            f"SELECT COUNT(*) FROM maude_failure_index WHERE product_code IN ({marks})",
            codes).fetchone()[0] or 0)
    except Exception:  # noqa: BLE001 - no failure index yet is a stated gap
        return {"codes": len(codes), "total": 0, "by_code": [], "by_event": {}, "names": {}}
    names: dict[str, str] = {}
    try:
        for row in reference.conn.execute(
                f"SELECT product_code, device_name FROM product_code_class"
                f" WHERE product_code IN ({marks})", codes):
            names[str(row[0])] = str(row[1] or "")
    except Exception:  # noqa: BLE001
        names = {}
    return {"codes": len(codes), "total": total, "by_code": by_code, "by_event": by_event,
            "names": names}


def companies_in_specialty(reference, specialty: str, *, limit: int = LEADERS_KEPT
                           ) -> list[dict[str, Any]]:
    """The leaders of one specialty, in order, with how many devices each holds there."""
    try:
        ensure_table(reference)
        rows = reference.conn.execute(
            "SELECT company_name, devices, rank FROM specialty_company "
            "WHERE specialty = ? ORDER BY rank LIMIT ?", (specialty, limit)).fetchall()
    except Exception:  # noqa: BLE001 - an unbuilt table is an absent answer, not a crash
        return []
    return [{"company_name": str(row[0]), "devices": int(row[1]), "rank": int(row[2])}
            for row in rows]


def one(reference, specialty: str) -> dict[str, Any] | None:
    """The summary row for one specialty."""
    try:
        ensure_table(reference)
        row = reference.conn.execute(
            "SELECT specialty, codes, devices, companies, top_companies, updated_at "
            "FROM specialty_stats WHERE specialty = ?", (specialty,)).fetchone()
    except Exception:  # noqa: BLE001
        return None
    if not row:
        return None
    try:
        top = json.loads(row[4] or "[]")
    except ValueError:
        top = []
    return {"specialty": str(row[0]), "codes": int(row[1]), "devices": int(row[2]),
            "companies": int(row[3]), "top_companies": top, "updated_at": str(row[5] or "")}


def read(reference) -> dict[str, Any]:
    try:
        ensure_table(reference)
        rows = reference.conn.execute(
            "SELECT specialty, codes, devices, companies, top_companies, updated_at "
            "FROM specialty_stats ORDER BY devices DESC").fetchall()
    except Exception:  # noqa: BLE001 - an unbuilt table is an absent answer, not a crash
        return {"available": False, "items": [], "updated_at": None}
    items = []
    stamps: list[str] = []
    for specialty, codes, devices, companies, top, at in rows:
        try:
            leaders = json.loads(top or "[]")
        except ValueError:
            leaders = []
        if at:
            stamps.append(str(at))
        items.append({"specialty": str(specialty), "codes": int(codes), "devices": int(devices),
                      "companies": int(companies), "top_companies": leaders})
    return {"available": bool(items), "items": items,
            "updated_at": max(stamps) if stamps else None}


__all__ = ["LEADERS_KEPT", "SCHEMA", "companies_in_specialty", "ensure_table",
           "failure_shape", "one", "read",
           "refresh"]
