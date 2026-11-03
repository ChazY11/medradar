"""Measured source lag — how long after publication did MedRadar actually see it?

The number this module refuses to fake is important: a source that publishes only
a *date* cannot produce an hour-level latency, and a source that publishes no
availability time at all cannot produce any latency. In both cases the answer is
"无法测量" plus the reason, never an estimate dressed up as a measurement.
"""

from __future__ import annotations

from typing import Any, Mapping

from .records import PRECISION_DATE, PRECISION_DATETIME, hours_between


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 3)
    index = (len(ordered) - 1) * pct
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = index - lower
    value = ordered[lower] + (ordered[upper] - ordered[lower]) * fraction
    return round(value, 3)


def measure_lag(ledger: Any, source: str | None = None) -> dict[str, Any]:
    """Publication → first observation latency, honest about precision."""
    where = " WHERE published_at IS NOT NULL"
    params: list[Any] = []
    if source:
        where += " AND source = ?"
        params.append(source)
    rows = ledger.con.execute(
        "SELECT source, first_seen_at, published_at, published_at_precision,"
        " event_at, event_at_precision FROM observation" + where,
        params,
    ).fetchall()
    precise: list[float] = []
    approximate: list[float] = []
    event_to_seen: list[float] = []
    by_source: dict[str, dict[str, list[float]]] = {}
    for row in rows:
        publish_lag = hours_between(row["published_at"], row["first_seen_at"])
        if publish_lag is not None and publish_lag >= 0:
            bucket = by_source.setdefault(
                row["source"], {"precise": [], "approximate": [], "event_to_seen": []}
            )
            if row["published_at_precision"] == PRECISION_DATETIME:
                precise.append(publish_lag)
                bucket["precise"].append(publish_lag)
            else:
                approximate.append(publish_lag)
                bucket["approximate"].append(publish_lag)
        event_lag = hours_between(row["event_at"], row["first_seen_at"])
        if event_lag is not None and event_lag >= 0:
            event_to_seen.append(event_lag)
            by_source.setdefault(
                row["source"], {"precise": [], "approximate": [], "event_to_seen": []}
            )["event_to_seen"].append(event_lag)

    def _shape(values: list[float], approximate_values: list[float]) -> dict[str, Any]:
        if values:
            return {
                "measurable": True,
                "note_zh": "来源提供可用时间戳，按“来源发布 → MedRadar 首次观察”计算",
                "p50_hours": _percentile(values, 0.5),
                "p90_hours": _percentile(values, 0.9),
                "max_hours": round(max(values), 3),
                "n": len(values),
                "precision": "datetime",
                "approximate_n": len(approximate_values),
            }
        if approximate_values:
            return {
                "measurable": False,
                "note_zh": "来源只提供日期（无时间），无法测量小时级延迟；不推算",
                "p50_hours": None,
                "p90_hours": None,
                "max_hours": None,
                "n": 0,
                "precision": "date_only",
                "approximate_n": len(approximate_values),
            }
        return {
            "measurable": False,
            "note_zh": "没有可用的来源发布时间，无法测量",
            "p50_hours": None,
            "p90_hours": None,
            "max_hours": None,
            "n": 0,
            "precision": "unknown",
            "approximate_n": 0,
        }

    overall = _shape(precise, approximate)
    overall["event_to_first_seen"] = _shape(event_to_seen, [])
    per_source = {
        key: _shape(values["precise"], values["approximate"])
        for key, values in by_source.items()
    }
    for key, values in by_source.items():
        per_source[key]["event_to_first_seen"] = _shape(values["event_to_seen"], [])
    if source:
        return {"source": source, **per_source.get(source, _shape([], []))}
    return {"overall": overall, "by_source": per_source}


def observation_lag(row: Mapping[str, Any]) -> dict[str, Any]:
    """Per-record lag block used by the Live Observatory event rows."""
    event_at = row.get("event_at") or row.get("o_event_at")
    event_precision = row.get("event_at_precision") or row.get("o_event_precision")
    published_at = row.get("published_at") or row.get("o_published_at")
    published_precision = row.get("published_at_precision") or row.get("o_published_precision")
    first_seen = row.get("first_seen_at") or row.get("o_first_seen_at")
    event_to_publish = hours_between(event_at, published_at)
    publish_to_seen = hours_between(published_at, first_seen)
    event_to_seen = hours_between(event_at, first_seen)
    measurable = bool(published_at) and published_precision == PRECISION_DATETIME
    if published_at and published_precision == PRECISION_DATE:
        reason = "来源只提供日期精度，发布时间到首次观察的间隔无法精确到小时"
    elif not published_at:
        reason = "来源未提供公开时间，无法测量发布到观察的延迟"
    else:
        reason = ""
    return {
        "event_to_publish_hours": event_to_publish,
        "publish_to_first_seen_hours": publish_to_seen,
        "event_to_first_seen_hours": event_to_seen,
        "measurable": measurable,
        "note_zh": reason,
        "event_precision": event_precision,
        "published_precision": published_precision,
        "observed_later_than_event": bool(
            event_to_seen is not None and event_to_seen > 0.5
        ),
    }


__all__ = ["measure_lag", "observation_lag"]
