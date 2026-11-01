"""Temporal leakage checks for persisted examples and source facts."""
from __future__ import annotations

from typing import Any

from ...util import parse_date


def audit_examples(store: Any, dataset_version: str) -> dict[str, Any]:
    rows = [dict(row) for row in store.conn.execute(
        "SELECT * FROM forecast_examples WHERE dataset_version = ?", (dataset_version,))]
    violations = []
    for row in rows:
        cutoff = parse_date(row["cutoff"])
        available = parse_date(row["feature_available_at"])
        if not cutoff or not available or available > cutoff:
            violations.append({"example_id": row["example_id"], "reason": "feature availability after cutoff"})
        if row["label"] is not None and row["maturity"] != "mature":
            violations.append({"example_id": row["example_id"], "reason": "label on immature origin"})
    procurement = store.conn.execute(
        "SELECT COUNT(*) FROM procurement_awards WHERE pit_usable=1 AND data_quality LIKE '%first_publication_unknown%'"
    ).fetchone()[0]
    if procurement:
        violations.append({"reason": "snapshot procurement incorrectly marked point-in-time usable", "rows": procurement})
    return {"checked_examples": len(rows), "violations": violations, "ok": not violations}
