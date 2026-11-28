"""Is a materialised table absent, empty, stale or unreadable - and which?

Every reader page reads at least one table the nightly rebuilds. Each of those reads is wrapped in
`except Exception` so a missing table degrades instead of failing, and for years that meant four different
states collapsed into one: the page printed a dash, or "no data", or nothing at all.

Audit 13 found the shape on `field_trend` (an unreadable table reported as 从未算过) and audit 14's first
question was which other materialised tables have the same blind spot. This module answers for all of them in
one place, by probing with **the columns the reader actually selects** - `COUNT(*)` succeeds on a table whose
schema moved, which is exactly the case that needs catching.

The caller decides what to print; this only reports what is true.
"""

from __future__ import annotations

from typing import Any, Mapping

#: The tables a reader page depends on, with the columns its read touches and the column holding the rebuild
#: time. Kept here rather than at the call site so a schema change has one place to update.
MATERIALISED: dict[str, dict[str, Any]] = {
    "store_stats": {"columns": ("key", "value", "updated_at"), "stamp": "updated_at",
                    "what": "首页与 /areas 的库存计数"},
    "specialty_stats": {"columns": ("specialty", "codes", "devices", "companies", "top_companies",
                                    "updated_at"), "stamp": "updated_at",
                        "what": "/areas 的领域规模"},
    "field_trend": {"columns": ("specialty", "term", "recent", "baseline", "lift", "computed_at",
                                "recent_total", "baseline_total"), "stamp": "computed_at",
                    "what": "/areas、设备页、公司页、导出的上升词"},
    "paper_field": {"columns": ("paper_id", "specialty", "added_at"), "stamp": "added_at",
                    "what": "论文与领域的关联（领域页、近两周发表）"},
}


def table_status(reference: Any, table: str) -> dict[str, Any]:
    """Read state of one materialised table: present, readable, rows, last stamp, and the reason if broken."""
    spec = MATERIALISED.get(table)
    if spec is None:
        return {"table": table, "present": False, "readable": False, "rows": 0, "stamp": "",
                "error": "unknown table", "what": ""}
    columns = ", ".join(spec["columns"])
    try:
        # The same shape of read the pages perform. COUNT(*) is not used for the probe: it answers on a table
        # whose schema moved, which is the failure this function exists to name.
        reference.conn.execute(f"SELECT {columns} FROM {table} LIMIT 1").fetchall()
    except Exception as error:  # noqa: BLE001 - the reason is the payload
        message = str(error) or type(error).__name__
        missing = "no such table" in message.lower()
        return {"table": table, "present": not missing, "readable": False, "rows": 0, "stamp": "",
                "error": "" if missing else message, "what": spec["what"]}
    rows = 0
    try:
        row = reference.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        rows = int(row[0]) if row else 0
    except Exception:  # noqa: BLE001 - counted as zero below; the read above already succeeded
        rows = 0
    stamp = ""
    try:
        column = spec["stamp"]
        row = reference.conn.execute(f"SELECT MAX({column}) FROM {table}").fetchone()
        stamp = str(row[0] or "") if row else ""
    except Exception:  # noqa: BLE001 - a table without its stamp column is still readable
        stamp = ""
    return {"table": table, "present": True, "readable": True, "rows": rows, "stamp": stamp,
            "error": "", "what": spec["what"]}


def all_status(reference: Any) -> list[dict[str, Any]]:
    """Every table a page depends on, in a stable order."""
    return [table_status(reference, name) for name in MATERIALISED]


def worst(statuses: Mapping[str, Any] | list[dict[str, Any]]) -> str:
    """`broken` if any table exists but cannot be read, `missing` if any is absent, else `ok`.

    One broken table is enough to make a page's number wrong, so the summary takes the worst state rather
    than an average of them.
    """
    rows = list(statuses.values()) if isinstance(statuses, Mapping) else list(statuses or [])
    if any(item.get("present") and not item.get("readable") for item in rows):
        return "broken"
    if any(not item.get("present") for item in rows):
        return "missing"
    return "ok"
