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
"""

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
    for specialty, data in totals.items():
        top = sorted(grouped.get(specialty, []), key=lambda item: -int(item["devices"]))[:leaders]
        rows.append((specialty, data["codes"], data["devices"], data["companies"],
                     json.dumps(top, ensure_ascii=False), at))
    reference.conn.execute("DELETE FROM specialty_stats")
    reference.conn.executemany(
        "INSERT OR REPLACE INTO specialty_stats "
        "(specialty, codes, devices, companies, top_companies, updated_at) VALUES (?,?,?,?,?,?)",
        rows)
    reference.conn.commit()
    return {"updated_at": at, "specialties": len(rows)}


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


__all__ = ["SCHEMA", "ensure_table", "read", "refresh"]
