"""Source status, detection latency and backlog - the monitoring view of the radar.

Every field here answers a question an operator actually asks, and each answer is a measured
value or an explicit unknown. In particular:

* **Detection latency** is only computed from records whose publication timestamp has
  ``datetime`` precision. A date-precision publication date is anchored at 00:00 for
  arithmetic, so it is reported separately as approximate instead of being mixed into an
  exact median. When no exact sample exists the field is ``None``, never zero.
* **Last observed update** is the last time a source actually produced a NEW or UPDATED
  observation. A source that answers "no change" every day has a fresh ``last_checked_at``
  and an old ``last_observed_update_at`` - which is the point.
* **A blocked source is not a failing source.** It has no check times at all, and it is
  labelled as an access-policy state rather than "unknown freshness".
* **Backlog** counts observations that have been observed but not yet published, so a slow
  AI stage is visible and cannot hide behind a green health light.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

from .ledger import ObservationLedger
from .records import (
    CHANGE_NEW,
    CHANGE_UPDATED,
    PHASE_BACKFILL,
    PHASE_INCREMENTAL,
    PHASE_INITIAL,
    PROC_PUBLISHED,
    SOURCE_STATUS_BLOCKED,
    SOURCE_STATUS_DEGRADED,
    SOURCE_STATUS_FAILED,
    SOURCE_STATUS_NEVER_RUN,
    SOURCE_STATUS_OK,
    SOURCE_STATUS_PAUSED,
    hours_between,
    parse_moment,
)
from .resources import snapshot as resource_snapshot


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(value: Any) -> datetime | None:
    return parse_moment(value)


def detection_latency(ledger: ObservationLedger, *, source: str | None = None,
                      limit: int = 5000) -> dict[str, Any]:
    """Measured hours from a source-stated publication time to first observation.

    Only ``datetime``-precision publication timestamps produce an exact sample. Everything
    else is counted as approximate and kept out of the exact median.
    """
    clause = " AND source=?" if source else ""
    params: tuple[Any, ...] = (source,) if source else ()
    rows = ledger.raw(
        "SELECT first_observed_at, published_at, published_at_precision, discovery_phase"
        f" FROM observation WHERE published_at IS NOT NULL{clause}"
        " ORDER BY first_observed_at DESC LIMIT ?",
        (*params, int(limit)),
    )
    exact: list[float] = []
    approximate: list[float] = []
    for row in rows:
        delta = hours_between(row["published_at"], row["first_observed_at"])
        if delta is None:
            continue
        if row["published_at_precision"] == "datetime":
            exact.append(delta)
        else:
            approximate.append(delta)
    return {
        "source": source,
        "exact_samples": len(exact),
        "approximate_samples": len(approximate),
        "exact_median_hours": round(statistics.median(exact), 2) if exact else None,
        "exact_p90_hours": round(_percentile(exact, 0.9), 2) if exact else None,
        "exact_min_hours": round(min(exact), 2) if exact else None,
        "exact_max_hours": round(max(exact), 2) if exact else None,
        "approximate_median_hours": round(statistics.median(approximate), 2) if approximate else None,
        "note": (
            "Detection latency is first_observed_at - published_at. It is only exact when the "
            "source states a timestamp with time-of-day. Date-only publication dates are "
            "reported separately as approximate and are never mixed into the exact figure."
        ),
        "cannot_do": (
            "Latency is not a measure of the source's speed alone: it also includes MedRadar's "
            "own check interval, and a record first loaded with its source's history has no "
            "meaningful latency."
        ),
    }


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(fraction * (len(ordered) - 1)))))
    return ordered[index]


def source_status(ledger: ObservationLedger, taxonomy=None) -> list[dict[str, Any]]:
    """One row per registered source, with measured status and explicit unknowns."""
    rows: list[dict[str, Any]] = []
    now = _now()
    counters = {
        row["source"]: row
        for row in ledger.raw(
            "SELECT source, COUNT(*) AS total, MAX(first_observed_at) AS newest,"
            " SUM(CASE WHEN processing_state IN ('RAW','CLASSIFIED','LINKED') THEN 1 ELSE 0 END)"
            "   AS publish_backlog,"
            " SUM(CASE WHEN processing_state = 'AI_PENDING' THEN 1 ELSE 0 END) AS ai_backlog"
            " FROM observation GROUP BY source"
        )
    }
    phases = {
        (row["source"], row["discovery_phase"]): int(row["n"])
        for row in ledger.raw(
            "SELECT source, discovery_phase, COUNT(*) AS n FROM observation GROUP BY source, discovery_phase"
        )
    }
    for state in ledger.list_sources():
        source_id = state["source_id"]
        spec = taxonomy.source(source_id) if taxonomy is not None else None
        latency = detection_latency(ledger, source=source_id)
        counter = counters.get(source_id, {})
        enabled = bool(state.get("enabled", 1))
        access_state = str(state.get("access_state") or "UNVERIFIED")
        last_checked = _parse(state.get("last_checked_at"))
        last_success = _parse(state.get("last_success_check_at"))
        failures = int(state.get("consecutive_failures") or 0)
        if access_state == "BLOCKED":
            status = SOURCE_STATUS_BLOCKED
        elif not enabled:
            status = SOURCE_STATUS_PAUSED
        elif last_checked is None:
            status = SOURCE_STATUS_NEVER_RUN
        elif failures >= 3:
            status = SOURCE_STATUS_FAILED
        elif failures > 0:
            status = SOURCE_STATUS_DEGRADED
        else:
            status = SOURCE_STATUS_OK
        cadence = float(state.get("cadence_hours") or 12.0)
        next_due = None
        if last_checked is not None:
            next_due = (last_checked + timedelta(hours=cadence)).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows.append({
            "source_id": source_id,
            "label": state.get("label"),
            "enabled": enabled,
            "access_state": access_state,
            "access_reason": state.get("access_reason"),
            "status": status,
            "cadence_hours": cadence,
            "declared_cadence_basis": (spec or {}).get("cadence_basis"),
            "licence": (spec or {}).get("licence"),
            "last_checked_at": state.get("last_checked_at"),
            "last_success_check_at": state.get("last_success_check_at"),
            "last_observed_update_at": state.get("last_observed_update_at"),
            "watermark": state.get("watermark"),
            "cursor": state.get("cursor"),
            "consecutive_failures": failures,
            "last_failure_at": state.get("last_failure_at"),
            "last_failure_message": state.get("last_failure_message"),
            "last_run_outcome": state.get("last_run_outcome"),
            "next_due_at": next_due,
            "due": bool(last_checked is None or (now - last_checked).total_seconds() >= cadence * 3600),
            "observations_total": int(counter.get("total") or 0),
            "newest_observation_at": counter.get("newest"),
            "backlog": int(counter.get("publish_backlog") or 0),
            "ai_backlog": int(counter.get("ai_backlog") or 0),
            "detection_latency": latency,
            "discovery_phases": {
                "initial": phases.get((source_id, PHASE_INITIAL), 0),
                "incremental": phases.get((source_id, PHASE_INCREMENTAL), 0),
                "backfill": phases.get((source_id, PHASE_BACKFILL), 0),
            },
            "adapter_version": state.get("adapter_version"),
        })
    return rows


def change_stream(ledger: ObservationLedger, *, since: str | None = None,
                  limit: int = 30) -> dict[str, Any]:
    clause = " AND observed_at > ?" if since else ""
    params: tuple[Any, ...] = (since,) if since else ()
    rows = ledger.raw(
        "SELECT observation_id, source, change_state, observed_at, first_observed_at, title, url,"
        " record_type, published_at, event_at, changed_fields, discovery_phase, run_id"
        " FROM observation_change WHERE change_state IN ('NEW','UPDATED','REMOVED_OR_UNAVAILABLE')"
        f"{clause} ORDER BY observed_at DESC LIMIT ?",
        (*params, int(limit)),
    )
    return {
        "since": since,
        "items": rows,
        "count": len(rows),
        "note": (
            "This is a change MedRadar observed. A NEW row whose first_observed_at is in the "
            "INITIAL_DISCOVERY phase is a historical record that was already public when the "
            "source was switched on - it is not a new event."
        ),
    }


def system_status(ledger: ObservationLedger, graph=None, taxonomy=None, *,
                  data_dir: str | None = None) -> dict[str, Any]:
    sources = source_status(ledger, taxonomy)
    queue = ledger.queue_summary()
    counts = ledger.counts()
    blocking = [row["source_id"] for row in sources if row["status"] == SOURCE_STATUS_BLOCKED]
    degraded = [row["source_id"] for row in sources
                if row["status"] in (SOURCE_STATUS_DEGRADED, SOURCE_STATUS_FAILED)]
    never = [row["source_id"] for row in sources if row["status"] == SOURCE_STATUS_NEVER_RUN]
    if degraded:
        overall = "degraded"
    elif never:
        overall = "warming_up"
    elif blocking and len(blocking) == len(sources):
        overall = "blocked"
    else:
        overall = "ok"
    ai_state = ledger.get_runtime("ai_state", {}) or {}
    last_cycle = ledger.get_runtime("last_cycle", {}) or {}
    payload = {
        "state": overall,
        "generated_at": _now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "counts": {
            "observations": counts.observations,
            "versions": counts.versions,
            "change_events": counts.change_events,
            "sources": counts.sources,
            "ai_candidates": counts.ai_candidates,
        },
        "sources": sources,
        "blocked_sources": blocking,
        "degraded_sources": degraded,
        "never_checked_sources": never,
        "backlog": queue,
        "resources": resource_snapshot(data_dir).as_dict() if data_dir else resource_snapshot().as_dict(),
        "ai": ai_state,
        "last_cycle": last_cycle,
        "consistency": ledger.consistency_check(),
        "change_counts": ledger.change_counts(),
        "terminology": {
            "continuously_monitored": any(row["status"] == SOURCE_STATUS_OK for row in sources),
            "real_time_claim": False,
            "statement": (
                "MedRadar can only discover a source update after that source publishes it and "
                "a scheduled check runs. No real-time or pre-publication access is claimed."
            ),
        },
    }
    if graph is not None:
        summary = graph.summary()
        payload["graph"] = {
            "nodes": summary["nodes"],
            "edges": summary["edges"],
            "edges_by_type": summary["edges_by_type"],
            "confirmations": summary["confirmations"],
            "graph_version": summary["graph_version"],
            "taxonomy_version": summary["taxonomy_version"],
        }
    if blocking:
        payload["blocked_explanation"] = (
            "A blocked source is one whose operator refuses anonymous automated access. It is "
            "not a failing connector and it is not 'no results': the restriction is reported, "
            "and no attempt is made to bypass it."
        )
    return payload
