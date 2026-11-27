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


def detection_latencies(ledger: ObservationLedger, sources: Sequence[str], *,
                        limit_per_source: int = 500) -> dict[str, dict[str, Any]]:
    """Publication-to-observation latency for many sources in one pass.

    Called once per source it cost 27 ms each - twelve of those was 324 ms of a page that reads a
    status table. The plans showed why: `source=?` uses ix_obs_source and then sorts in a temp B-tree,
    because there is no composite (source, first_observed_at) index.

    One ordered read of the newest samples, then bucketed in Python, is a single scan instead of twelve.
    The window is 500 samples per source rather than 5,000: measured on the live ledger, the SQL was
    107 ms and the remaining 220 ms was Python parsing 47,756 publication dates - the median of the
    newest 500 readings describes recent behaviour at least as well as the median of 5,000.
    """
    wanted = {str(item) for item in sources}
    rows = ledger.raw(
        "SELECT source, first_observed_at, published_at, published_at_precision"
        " FROM observation WHERE published_at IS NOT NULL"
        " ORDER BY first_observed_at DESC LIMIT ?",
        (int(limit_per_source) * max(1, len(wanted) or 1),),
    )
    buckets: dict[str, list[dict[str, Any]]] = {name: [] for name in wanted}
    for row in rows:
        name = str(row.get("source") or "")
        if name in buckets and len(buckets[name]) < limit_per_source:
            buckets[name].append(row)
    return {name: _latency_from_rows(name, bucket) for name, bucket in buckets.items()}


def _latency_from_rows(source: str | None, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The statistics half of detection_latency, so both entry points agree by construction."""
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
    }


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
    return _latency_from_rows(source, rows)


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
    # One pass for all sources instead of one query each: twelve per-source reads cost 324 ms of a
    # page that only displays a status table, because `source=?` needs a temp B-tree sort.
    latencies = detection_latencies(ledger, [str(item["source_id"]) for item in ledger.list_sources()])
    for state in ledger.list_sources():
        source_id = state["source_id"]
        spec = taxonomy.source(source_id) if taxonomy is not None else None
        latency = latencies.get(source_id) or _latency_from_rows(source_id, [])
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


# ------------------------------------------------------------------ health verdicts
# Four verdicts, and only four. The defect this replaces was not that the checks were missing -
# consistency problems, watermarks and per-source failures were all computed - but that they were
# displayed next to a green light instead of changing it.
HEALTHY = "HEALTHY"
DEGRADED = "DEGRADED"
UNHEALTHY = "UNHEALTHY"
UNKNOWN = "UNKNOWN"

SEVERITY_CRITICAL = "CRITICAL"
SEVERITY_MAJOR = "MAJOR"
SEVERITY_MINOR = "MINOR"

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"
UNDETERMINED = "UNKNOWN"

# Which sources the narrowed V1 product cannot serve without. A fault in one of these is a
# product fault; a fault anywhere else is still reported, weighted MAJOR so it degrades the
# verdict. The list is explicit because how much a source matters is a product decision, not a
# property of the connector, and hard-coding "everything is equal" is what made a stalled core
# channel look like background noise.
V1_CRITICAL_SOURCES = frozenset({
    "openfda_recall",    # the safety-event channel: recalls are the product first promise
    "openfda_device",    # the regulatory record behind a device performance claim
    "pubmed",            # device performance literature
    "crossref",          # the second, independent copy of the same literature
})

# Problems that mean the stored history itself is inconsistent, as opposed to incomplete.
_STRUCTURAL_PROBLEMS = frozenset({
    "orphan_versions",
    "orphan_changes",
    "latest_version_missing",
    "first_observed_at_drift",
})
_WATERMARK_PROBLEMS = frozenset({
    "watermark_in_future",
    "watermark_without_successful_run",
})

# A source that has completed successful checks but produced nothing for this many of its own
# cadence intervals is worth showing to an operator. It is NOT a fault: a quiet source and a
# broken source must stay distinguishable, because treating quiet as broken trains people to
# ignore the light.
# A watermark can legitimately lead the UTC date by a day: a source that timestamps in its own
# timezone can report tomorrow before UTC reaches it (measured on production: PubMed
# advanced to 2026-11-19 at 2026-11-18T18:24Z). The adapter clamps a future watermark to
# today, so a small lead costs overlap, not discovery capability - it is reported as a
# warning. A lead beyond this window is a broken coverage claim and is a failure.
WATERMARK_FUTURE_GRACE_DAYS = 1
QUIET_INTERVALS_BEFORE_NOTE = 12
# A scheduler heartbeat older than this is not "between cycles".
HEARTBEAT_INTERVALS = 3
MIN_HEARTBEAT_SECONDS = 1800.0


def _check(check_id: str, status: str, severity: str, detail: str, **observed: Any) -> dict[str, Any]:
    return {"id": check_id, "status": status, "severity": severity, "detail": detail,
            "observed": observed}


def _seconds_since(value: Any, now: datetime) -> float | None:
    moment = _parse(value)
    return None if moment is None else (now - moment).total_seconds()


def _ledger_writable(ledger: ObservationLedger) -> dict[str, Any]:
    """Does the ledger still accept a write? Answered by taking and releasing a write lock.

    A full, locked or read-only database can still serve a cached page while it silently stops
    recording what it observes. That loses evidence, so it is a critical check. A connection that
    was opened read-only on purpose cannot answer the question, which is reported as UNKNOWN
    rather than as a failure.
    """
    if getattr(ledger, "read_only", False):
        return _check("ledger_writable", UNDETERMINED, SEVERITY_CRITICAL,
                      "This connection was opened read-only, so writability was not probed.")
    if ledger.con.in_transaction:
        return _check("ledger_writable", UNDETERMINED, SEVERITY_CRITICAL,
                      "A transaction is already open on this connection, so writability was not probed.")
    try:
        ledger.con.execute("BEGIN IMMEDIATE")
        ledger.con.execute("ROLLBACK")
        return _check("ledger_writable", PASS, SEVERITY_CRITICAL,
                      "The ledger accepted a write lock and released it.")
    except Exception as error:  # noqa: BLE001 - any refusal is the finding
        try:
            ledger.con.execute("ROLLBACK")
        except Exception:  # pragma: no cover - nothing left to roll back
            pass
        return _check("ledger_writable", FAIL, SEVERITY_CRITICAL,
                      f"The ledger refused a write lock: {type(error).__name__}: {str(error)[:200]}")


def health_checks(ledger: ObservationLedger, sources: list[dict[str, Any]],
                  consistency: Mapping[str, Any], *, last_cycle: Mapping[str, Any] | None = None,
                  now: datetime | None = None) -> list[dict[str, Any]]:
    """Every reason the top-level verdict is what it is, as a measured value.

    Each check answers one question an operator asks. A question that cannot be answered is
    reported as UNKNOWN with the reason, never as PASS.
    """
    now = now or _now()
    checks: list[dict[str, Any]] = [_ledger_writable(ledger)]
    problems = list(consistency.get("problems") or [])

    # ---- the stored history does not contradict itself
    structural = [item for item in problems if item.get("kind") in _STRUCTURAL_PROBLEMS]
    if structural:
        checks.append(_check(
            "ledger_integrity", FAIL, SEVERITY_CRITICAL,
            "The stored history contradicts itself; no derived view can be trusted until this is"
            " explained.", problems=structural))
    else:
        checks.append(_check(
            "ledger_integrity", PASS, SEVERITY_CRITICAL,
            "No orphan version, orphan change, broken version chain or drifted first-observed"
            " timestamp was found.",
            observations=consistency.get("counts", {}).get("observations")))

    # ---- every watermark is a coverage claim that can actually be served
    watermark = [item for item in problems if item.get("kind") in _WATERMARK_PROBLEMS]
    future = [item for item in watermark if item.get("kind") == "watermark_in_future"]
    unbacked = [item for item in watermark if item.get("kind") == "watermark_without_successful_run"]
    affected = sorted({str(name) for item in watermark for name in (item.get("sources") or [])})
    # How far ahead is the worst offender? The adapter clamps to today, so the cost of a small
    # lead is overlap rather than discovery; a large lead means the stored claim is meaningless.
    today = now.date()
    lead_days = 0
    for row in sources:
        moment = parse_moment(row.get("watermark"))
        if moment is not None:
            lead_days = max(lead_days, (moment.date() - today).days)
    if unbacked or (future and lead_days > WATERMARK_FUTURE_GRACE_DAYS):
        critical_hit = bool(set(affected) & V1_CRITICAL_SOURCES)
        # Name the sources and the values. Measured while auditing this: the detail said "at least
        # one source" and an operator had to open three layers of JSON to learn which one and what
        # date - which is the difference between an alert and a puzzle.
        detail_rows = []
        for row in sources:
            source_id = str(row.get("source_id"))
            if source_id not in affected:
                continue
            moment = parse_moment(row.get("watermark"))
            lead = None if moment is None else (moment.date() - today).days
            detail_rows.append(
                f"{source_id}: watermark={row.get('watermark') or 'none'}"
                f" last_success={str(row.get('last_success_check_at') or 'never')[:19]}"
                + (f" lead={lead}d" if lead is not None else ""))
        checks.append(_check(
            "watermark_legal", FAIL,
            SEVERITY_CRITICAL if critical_hit else SEVERITY_MAJOR,
            "At least one source states a coverage watermark it cannot have covered by more than"
            f" {WATERMARK_FUTURE_GRACE_DAYS} day(s), or holds a watermark with no successful run"
            " behind it. Discovery on that source cannot be trusted even though its checks still"
            " succeed. "
            + ("; ".join(detail_rows[:4]) if detail_rows else ""),
            problems=watermark, sources=affected, max_lead_days=lead_days,
            critical_sources=sorted(set(affected) & V1_CRITICAL_SOURCES)))
    elif future:
        checks.append(_check(
            "watermark_legal", WARN, SEVERITY_MAJOR,
            f"A watermark leads the UTC date by {lead_days} day(s), inside the"
            f" {WATERMARK_FUTURE_GRACE_DAYS}-day grace for source clock skew. The adapter clamps it"
            " for the query, so this costs overlap rather than discovery; the stored claim is still"
            " wrong and is reported.",
            problems=watermark, sources=affected, max_lead_days=lead_days))
    else:
        checks.append(_check(
            "watermark_legal", PASS, SEVERITY_MAJOR,
            "Every stored watermark is in the past or present and is backed by a successful run.",
            sources_with_watermark=sum(1 for row in sources if row.get("watermark"))))

    # ---- the sources the product depends on are actually being collected
    monitored = [row for row in sources
                 if row.get("enabled") and row.get("access_state") != "BLOCKED"]
    cadences = [float(row.get("cadence_hours") or 12.0) for row in monitored] or [12.0]
    critical_failures: list[dict[str, Any]] = []
    critical_warnings: list[dict[str, Any]] = []
    quiet: list[dict[str, Any]] = []
    for row in monitored:
        source_id = str(row.get("source_id"))
        critical = source_id in V1_CRITICAL_SOURCES
        cadence = float(row.get("cadence_hours") or 12.0)
        failures = int(row.get("consecutive_failures") or 0)
        since_check = _seconds_since(row.get("last_checked_at"), now)
        since_update = _seconds_since(row.get("last_observed_update_at"), now)
        entry = {"source_id": source_id, "status": row.get("status"),
                 "hours_since_check": None if since_check is None else round(since_check / 3600, 2),
                 "hours_since_observed_update": (None if since_update is None
                                                 else round(since_update / 3600, 2)),
                 "consecutive_failures": failures, "critical": critical}
        if since_check is None:
            target = critical_failures if critical else critical_warnings
            target.append({**entry, "reason": "never checked since this ledger was created"})
        elif failures >= 3:
            target = critical_failures if critical else critical_warnings
            target.append({**entry, "reason": f"{failures} consecutive failed checks"})
        elif failures > 0:
            critical_warnings.append({**entry, "reason": f"{failures} consecutive failed check(s)"})
        elif since_check > 3.0 * cadence * 3600:
            target = critical_failures if critical else critical_warnings
            target.append({**entry, "reason": f"last check was {round(since_check / 3600, 1)} h ago"
                                                 f" but the declared cadence is {cadence:g} h"})
        elif since_update is not None and since_update > QUIET_INTERVALS_BEFORE_NOTE * cadence * 3600:
            # Not a fault, and deliberately not in any failure list.
            quiet.append({**entry, "reason": "no new or updated record for many cadence intervals"})
    # A ledger that has never completed a single check is warming up, not broken. Reporting it as
    # a failure on the first day is exactly the false alarm that teaches operators to ignore the
    # light, so the question is left open until there is something to measure.
    first_check_pending = not any(row.get("last_success_check_at") for row in sources)
    if first_check_pending:
        checks.append(_check(
            "critical_sources", UNDETERMINED, SEVERITY_CRITICAL,
            "No source has completed a successful check on this ledger yet, so whether the core"
            " channels are being collected is unknown rather than assumed.",
            monitored_sources=sorted(str(row.get("source_id")) for row in monitored)))
    elif critical_failures:
        checks.append(_check(
            "critical_sources", FAIL, SEVERITY_CRITICAL,
            "A source the product cannot serve without is failing, or has not been checked for far"
            " longer than its cadence. The system is not collecting the evidence its output claims"
            " to rest on.", sources=critical_failures))
    elif critical_warnings:
        checks.append(_check(
            "critical_sources", WARN, SEVERITY_MAJOR,
            "A monitored source has failed at least once or has never run; one successful cycle may"
            " clear it.", sources=critical_warnings))
    else:
        checks.append(_check(
            "critical_sources", PASS, SEVERITY_CRITICAL,
            "Every monitored source was checked inside its declared cadence.",
            monitored_sources=sorted(str(row.get("source_id")) for row in monitored)))

    # ---- something has to be moving, but "no new records" is not a fault
    progressing = [row for row in sources if row.get("last_observed_update_at")]
    if not progressing:
        checks.append(_check(
            "acquisition_progress", UNDETERMINED, SEVERITY_MINOR,
            "No source has recorded a new or updated observation yet, so there is no evidence"
            " either way about whether collection progresses."))
    else:
        newest = max(str(row.get("last_observed_update_at")) for row in progressing)
        checks.append(_check(
            "acquisition_progress", WARN if quiet else PASS, SEVERITY_MINOR,
            ("At least one source has been quiet for many of its own intervals. A quiet source is"
             " not a failing one; this line exists so the two can be told apart.") if quiet else
            "At least one source produced a new or updated observation recently.",
            newest_observed_update_at=newest, quiet_sources=quiet))

    # ---- the scheduler is alive
    cycle = dict(last_cycle or {})
    heartbeat = _seconds_since(cycle.get("finished_at") or cycle.get("started_at"), now)
    min_cadence = min(cadences) if cadences else 12.0
    budget = max(MIN_HEARTBEAT_SECONDS, HEARTBEAT_INTERVALS * min_cadence * 3600)
    if heartbeat is None:
        checks.append(_check(
            "scheduler_heartbeat", UNDETERMINED, SEVERITY_CRITICAL,
            "No cycle has been recorded on this ledger yet, so whether the scheduler is running is"
            " unknown rather than assumed.", last_cycle=cycle or None))
    elif heartbeat > budget:
        checks.append(_check(
            "scheduler_heartbeat", FAIL, SEVERITY_CRITICAL,
            f"The last recorded cycle finished {round(heartbeat / 3600, 2)} h ago, past the"
            f" {round(budget / 3600, 2)} h liveness budget. Sources are not being polled.",
            seconds_since_cycle=round(heartbeat, 1), budget_seconds=round(budget, 1),
            last_cycle=cycle))
    else:
        checks.append(_check(
            "scheduler_heartbeat", PASS, SEVERITY_CRITICAL,
            "The scheduler recorded a cycle inside its liveness budget.",
            seconds_since_cycle=round(heartbeat, 1), budget_seconds=round(budget, 1)))
    return checks


def verdict(checks: Iterable[Mapping[str, Any]], *, observations: int,
            ever_checked: bool) -> str:
    """Collapse the checks into one of four verdicts.

    Order matters: a critical failure outranks missing evidence. An unreadable history is not
    "unknown", it is broken.
    """
    checked = list(checks)
    if any(item["status"] == FAIL and item["severity"] == SEVERITY_CRITICAL for item in checked):
        return UNHEALTHY
    if not ever_checked or observations <= 0:
        return UNKNOWN
    if any(item["status"] == FAIL for item in checked):
        return DEGRADED
    if any(item["status"] == WARN and item["severity"] in (SEVERITY_CRITICAL, SEVERITY_MAJOR)
           for item in checked):
        return DEGRADED
    return HEALTHY


def _legacy_state(state: str) -> str:
    """The pre-PILOT vocabulary, kept so a reader of the old strings keeps its meaning."""
    return {HEALTHY: "ok", DEGRADED: "degraded", UNHEALTHY: "blocked",
            UNKNOWN: "warming_up"}.get(state, state)


def system_status(ledger: ObservationLedger, graph=None, taxonomy=None, *,
                  data_dir: str | None = None) -> dict[str, Any]:
    sources = source_status(ledger, taxonomy)
    queue = ledger.queue_summary()
    counts = ledger.counts()
    consistency = ledger.consistency_check()
    last_cycle = ledger.get_runtime("last_cycle", {}) or {}
    now = _now()
    ever_checked = any(row.get("last_success_check_at") for row in sources)
    checks = health_checks(ledger, sources, consistency, last_cycle=last_cycle, now=now)
    state = verdict(checks, observations=counts.observations, ever_checked=ever_checked)
    blocking = [row["source_id"] for row in sources if row["status"] == SOURCE_STATUS_BLOCKED]
    degraded = [row["source_id"] for row in sources
                if row["status"] in (SOURCE_STATUS_DEGRADED, SOURCE_STATUS_FAILED)]
    never = [row["source_id"] for row in sources if row["status"] == SOURCE_STATUS_NEVER_RUN]
    ai_state = ledger.get_runtime("ai_state", {}) or {}
    payload = {
        "state": state,
        "legacy_state": _legacy_state(state),
        "verdict": {
            "state": state,
            "critical_sources": sorted(V1_CRITICAL_SOURCES),
            "reasons": [item for item in checks if item["status"] in (FAIL, WARN, UNDETERMINED)],
            "checks": checks,
            "statement": (
                "The verdict is derived from the checks below, not from the absence of an error."
                " A quiet source is not a failing one; a failing core source is never reported as"
                " healthy."),
        },
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
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
        "resources": (resource_snapshot(data_dir).as_dict() if data_dir
                      else resource_snapshot().as_dict()),
        "ai": ai_state,
        "last_cycle": last_cycle,
        "consistency": consistency,
        "change_counts": ledger.change_counts(),
        "terminology": {
            "continuously_monitored": any(row["status"] == SOURCE_STATUS_OK for row in sources),
            "real_time_claim": False,
            "statement": (
                "MedRadar can only discover a source update after that source publishes it and"
                " a scheduled check runs. No real-time or pre-publication access is claimed."),
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
            "not a failing connector and it is not no results: the restriction is reported, and"
            " no attempt is made to bypass it.")
    return payload
