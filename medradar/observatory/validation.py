"""Seven-day continuous observation validation — protocol and live metrics.

The single most important rule in this module: **it never claims more time than has
actually elapsed.** ``validation_status`` is derived from real ``sync_run`` rows
inside a real wall-clock window; a session that ran for an hour is
``VALIDATION_IN_PROGRESS`` with ~28 planned slots and a handful executed, never
``VALIDATION_PASSED``.

Vocabulary (docs/RELIABILITY_DESIGN.md §0):
  VALIDATION_NOT_STARTED / VALIDATION_IN_PROGRESS / VALIDATION_PASSED / VALIDATION_FAILED
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from .ledger import ObservationLedger
from .lag import measure_lag
from .records import (
    PRECISION_DATETIME,
    VALIDATION_FAILED,
    VALIDATION_IN_PROGRESS,
    VALIDATION_NOT_STARTED,
    VALIDATION_PASSED,
)

PROTOCOL_VERSION = "obs-validation-v1"
DEFAULT_DAYS = 7
DEFAULT_INTERVAL_HOURS = 6.0
#: A slot counts as executed if a run started within this window around it.
#: Real schedulers (cron/Task Scheduler/systemd timers) jitter; the tolerance is
#: capped at half the interval so one run can never satisfy two adjacent slots.
SLOT_TOLERANCE_MINUTES = 60.0


def slot_tolerance(interval_hours: float) -> timedelta:
    minutes = min(SLOT_TOLERANCE_MINUTES, max(5.0, float(interval_hours) * 60.0 / 2.0))
    return timedelta(minutes=minutes)


# ----------------------------------------------------------------------- helpers
def _now(now: datetime | None = None) -> datetime:
    return now or datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _parse(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def expected_interval_hours(declared_cadence_zh: str | None) -> float:
    """Parse the declared cadence text ('默认每 6 小时轮询') into hours."""
    text = str(declared_cadence_zh or "")
    match = re.search(r"每\s*(\d+(?:\.\d+)?)\s*小时", text)
    if match:
        try:
            return max(0.25, float(match.group(1)))
        except ValueError:
            pass
    match = re.search(r"每\s*(\d+(?:\.\d+)?)\s*分钟", text)
    if match:
        try:
            return max(0.05, float(match.group(1)) / 60.0)
        except ValueError:
            pass
    return 24.0


# ------------------------------------------------------------------------ start
def start_validation(ledger: ObservationLedger, *, days: int = DEFAULT_DAYS,
                     interval_hours: float = DEFAULT_INTERVAL_HOURS,
                     started_at: datetime | None = None,
                     note_zh: str | None = None) -> dict[str, Any]:
    moment = _now(started_at)
    existing = ledger.get_validation()
    if existing.get("started_at") and existing.get("status") == VALIDATION_IN_PROGRESS:
        return {"already_started": True, **existing}
    if existing.get("status") in (VALIDATION_PASSED, VALIDATION_FAILED):
        return {"already_finished": True, **existing}
    days = max(1, int(days))
    interval_hours = max(0.05, float(interval_hours))
    ends_at = moment + timedelta(days=days)
    planned_slots = int(round((days * 24.0) / interval_hours))
    payload = {
        "protocol_version": PROTOCOL_VERSION,
        "status": VALIDATION_IN_PROGRESS,
        "started_at": _iso(moment),
        "ends_at": _iso(ends_at),
        "target_days": days,
        "interval_hours": interval_hours,
        "planned_slots": planned_slots,
        "note_zh": note_zh or (
            "七天连续观察验证：按声明周期轮询三个官方来源；"
            "只有真实经过的时间与真实运行记录才计入，缺失的轮次记为 missed，不当作成功。"
        ),
    }
    ledger.set_validation(payload)
    ledger.record_ops_metric(
        "validation_started",
        {"started_at": payload["started_at"], "ends_at": payload["ends_at"],
         "planned_slots": planned_slots, "interval_hours": interval_hours},
    )
    return payload


def stop_validation(ledger: ObservationLedger, *, outcome: str,
                    now: datetime | None = None) -> dict[str, Any]:
    """Only allowed once the window really ended (or explicitly as a failure)."""
    state = ledger.get_validation()
    if not state:
        raise RuntimeError("validation was never started")
    if state.get("status") != VALIDATION_IN_PROGRESS:
        return {"already_finished": True, **state}
    moment = _now(now)
    ends_at = _parse(state.get("ends_at"))
    if outcome == VALIDATION_PASSED:
        if ends_at is None or moment < ends_at:
            raise RuntimeError(
                "cannot mark the seven-day validation PASSED before its window ends; "
                "report VALIDATION_IN_PROGRESS instead"
            )
        metrics = compute_metrics(ledger, state, now=moment)
        if metrics["integrity"]["violations"] or metrics["duplicates"]["rate"] > 0:
            outcome = VALIDATION_FAILED
    if outcome not in (VALIDATION_PASSED, VALIDATION_FAILED):
        raise ValueError("outcome must be VALIDATION_PASSED or VALIDATION_FAILED")
    state = {
        **state,
        "status": outcome,
        "ended_at": _iso(moment),
        "final_metrics": compute_metrics(ledger, state, now=moment),
    }
    ledger.set_validation(state)
    ledger.record_ops_metric("validation_stopped", {"status": outcome, "at": _iso(moment)})
    return state


# ----------------------------------------------------------------------- metrics
def _planned_slots(state: Mapping[str, Any]) -> list[datetime]:
    started = _parse(state.get("started_at"))
    interval = float(state.get("interval_hours") or DEFAULT_INTERVAL_HOURS)
    planned = int(state.get("planned_slots") or 0)
    if started is None or planned <= 0:
        return []
    return [started + timedelta(hours=interval * (index + 1)) for index in range(planned)]


def _runs_in_window(ledger: ObservationLedger, start: datetime, end: datetime) -> list[dict[str, Any]]:
    rows = ledger.con.execute(
        "SELECT run_id, source, status, started_at, finished_at, requests, records_seen,"
        " records_new, records_updated, records_unchanged, records_failed, notes_zh,"
        " error_detail, trigger FROM sync_run WHERE started_at >= ? AND started_at <= ?"
        " ORDER BY started_at",
        (_iso(start), _iso(end)),
    ).fetchall()
    return [dict(row) for row in rows]


def _duplicate_stats(ledger: ObservationLedger, start: datetime, end: datetime) -> dict[str, Any]:
    duplicate_rows = ledger.con.execute(
        "SELECT source, source_record_id, COUNT(*) AS n FROM observation"
        " GROUP BY source, source_record_id HAVING COUNT(*) > 1"
    ).fetchall()
    in_window = ledger.con.execute(
        "SELECT COUNT(*) FROM observation WHERE first_seen_at >= ? AND first_seen_at <= ?",
        (_iso(start), _iso(end)),
    ).fetchone()[0]
    replayed_versions = ledger.con.execute(
        "SELECT COUNT(*) FROM (SELECT observation_id, payload_hash, COUNT(*) AS n"
        " FROM observation_version GROUP BY observation_id, payload_hash HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    total = max(1, int(in_window))
    return {
        "duplicate_observations": len(duplicate_rows),
        "replayed_versions": int(replayed_versions),
        "observations_in_window": int(in_window),
        "rate": round((len(duplicate_rows) + int(replayed_versions)) / total, 6),
        "target": 0,
    }


def _latency_stats(ledger: ObservationLedger, start: datetime, end: datetime) -> dict[str, Any]:
    rows = ledger.con.execute(
        "SELECT source, first_seen_at, published_at, published_at_precision FROM observation"
        " WHERE first_seen_at >= ? AND first_seen_at <= ? AND published_at IS NOT NULL",
        (_iso(start), _iso(end)),
    ).fetchall()
    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        source = row["source"]
        bucket = buckets.setdefault(source, {"precise": [], "approx": 0, "total": 0})
        bucket["total"] += 1
        if row["published_at_precision"] != PRECISION_DATETIME:
            bucket["approx"] += 1
            continue
        published = _parse(row["published_at"])
        seen = _parse(row["first_seen_at"])
        if published is None or seen is None:
            continue
        hours = (seen - published).total_seconds() / 3600.0
        if hours >= 0:
            bucket["precise"].append(hours)
    result: dict[str, Any] = {}
    for source, bucket in buckets.items():
        values = sorted(bucket["precise"])
        if values:
            result[source] = {
                "measurable": True,
                "n": len(values),
                "p50_hours": round(values[len(values) // 2], 3),
                "max_hours": round(values[-1], 3),
                "date_only_records": bucket["approx"],
                "total_records": bucket["total"],
            }
        else:
            result[source] = {
                "measurable": False,
                "n": 0,
                "p50_hours": None,
                "max_hours": None,
                "date_only_records": bucket["approx"],
                "total_records": bucket["total"],
                "note_zh": "来源只提供日期精度或无发布时间，无法测量小时级延迟（不推算）",
            }
    return result


def _recovery_stats(ledger: ObservationLedger, start: datetime, end: datetime) -> dict[str, Any]:
    rows = _runs_in_window(ledger, start, end)
    interrupted = [row for row in rows if row["status"] == "INTERRUPTED"]
    recovered = [
        row for row in rows
        if row["status"] == "OK" and "检查点继续" in str(row.get("notes_zh") or "")
    ]
    denominator = len(interrupted)
    return {
        "interrupted_runs": denominator,
        "recovered_runs": len(recovered),
        "success_rate": round(min(1.0, len(recovered) / denominator), 4) if denominator else None,
        "note_zh": (
            "窗口内没有发生中断运行，无法据此证明恢复能力（恢复能力由合成故障注入测试单独证明）"
            if denominator == 0 else None
        ),
    }


def _integrity_stats(ledger: ObservationLedger) -> dict[str, Any]:
    check = ledger.consistency_check()
    violations = int(check.get("issue_count") or 0)
    return {
        "violations": violations,
        "issue_kinds": sorted((check.get("issues") or {}).keys()),
        "trigger_present": all(
            ledger.con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='trigger' AND name=?", (name,)
            ).fetchone()
            for name in ("trg_observation_first_seen_immutable", "trg_version_no_update",
                         "trg_phase_no_update")
        ),
        "checked_at": check.get("checked_at"),
        "target": 0,
    }


def _storage_growth(ledger: ObservationLedger, start: datetime, end: datetime) -> dict[str, Any]:
    series = ledger.ops_metric_series("daily_snapshot", days=90)
    points = []
    for item in reversed(series):
        value = item.get("value") if isinstance(item.get("value"), dict) else {}
        points.append({"day": item["day"], **value})
    counts = ledger.counts()
    observations_in_window = ledger.con.execute(
        "SELECT COUNT(*) FROM observation WHERE first_seen_at >= ? AND first_seen_at <= ?",
        (_iso(start), _iso(end)),
    ).fetchone()[0]
    days = max(0.001, (end - start).total_seconds() / 86400.0)
    return {
        "ledger_bytes": counts["db_bytes"],
        "observations_total": counts["observations"],
        "observations_in_window": int(observations_in_window),
        "new_observations_per_day": round(int(observations_in_window) / days, 2),
        "ledger_bytes_per_day": round(counts["db_bytes"] / max(1.0, days), 1),
        "daily_snapshots": points[-14:],
    }


def compute_metrics(ledger: ObservationLedger, state: Mapping[str, Any], *,
                    now: datetime | None = None) -> dict[str, Any]:
    moment = _now(now)
    started = _parse(state.get("started_at"))
    ends_at = _parse(state.get("ends_at"))
    if started is None:
        return {"status": VALIDATION_NOT_STARTED, "note_zh": "验证尚未开始"}
    window_end = min(moment, ends_at) if ends_at else moment
    slots = _planned_slots(state)
    due_slots = [slot for slot in slots if slot <= window_end]
    tolerance = slot_tolerance(float(state.get("interval_hours") or DEFAULT_INTERVAL_HOURS))
    interval = timedelta(hours=float(state.get("interval_hours") or DEFAULT_INTERVAL_HOURS))
    runs = _runs_in_window(ledger, started, window_end)
    run_starts = [(_parse(row["started_at"]), row) for row in runs]
    executed_slots = 0
    slot_rows = []
    used_runs: set[str] = set()
    for slot in due_slots:
        matched = []
        for start, row in run_starts:
            if start is None or row["run_id"] in used_runs:
                continue
            if (slot - tolerance) <= start < (slot + interval):
                matched.append(row)
        if matched:
            executed_slots += 1
            used_runs.add(matched[0]["run_id"])
        slot_rows.append({"slot_at": _iso(slot), "executed": bool(matched)})
    planned_due = len(due_slots)
    ok_runs = [row for row in runs if row["status"] == "OK"]
    partial_runs = [row for row in runs if row["status"] == "PARTIAL"]
    failed_runs = [row for row in runs if row["status"] in ("FAILED", "INTERRUPTED")]
    per_source: dict[str, dict[str, Any]] = {}
    for row in runs:
        source = row["source"]
        bucket = per_source.setdefault(source, {"attempts": 0, "ok": 0, "partial": 0,
                                                "failed": 0, "new": 0, "updated": 0})
        bucket["attempts"] += 1
        if row["status"] == "OK":
            bucket["ok"] += 1
        elif row["status"] == "PARTIAL":
            bucket["partial"] += 1
        else:
            bucket["failed"] += 1
        bucket["new"] += int(row["records_new"] or 0)
        bucket["updated"] += int(row["records_updated"] or 0)
    for source, bucket in per_source.items():
        bucket["success_rate"] = round(bucket["ok"] / bucket["attempts"], 4) if bucket["attempts"] else None
    freshness: dict[str, Any] = {}
    for row in ledger.con.execute(
        "SELECT source, last_success_at, last_attempt_at FROM source_state"
    ).fetchall():
        last = _parse(row["last_success_at"])
        freshness[row["source"]] = {
            "last_success_at": row["last_success_at"],
            "last_attempt_at": row["last_attempt_at"],
            "freshness_hours": round((moment - last).total_seconds() / 3600.0, 2) if last else None,
        }
    days_elapsed = max(0.0, (window_end - started).total_seconds() / 86400.0)
    remaining = max(0.0, (ends_at - moment).total_seconds() / 86400.0) if ends_at else 0.0
    status = state.get("status")
    if status == VALIDATION_IN_PROGRESS and ends_at is not None and moment >= ends_at:
        status = VALIDATION_IN_PROGRESS  # still not PASSED until an explicit stop
    return {
        "protocol_version": state.get("protocol_version", PROTOCOL_VERSION),
        "status": status,
        "started_at": state.get("started_at"),
        "ends_at": state.get("ends_at"),
        "computed_at": _iso(moment),
        "days_elapsed": round(days_elapsed, 4),
        "days_remaining": round(remaining, 4),
        "window_ended": bool(ends_at is not None and moment >= ends_at),
        "slots": {
            "planned_total": len(slots),
            "due": planned_due,
            "executed": executed_slots,
            "missed": max(0, planned_due - executed_slots),
            "detail": slot_rows,
        },
        "runs": {
            "launched": len(runs),
            "ok": len(ok_runs),
            "partial": len(partial_runs),
            "failed": len(failed_runs),
            "scheduler_success_rate": round(len(ok_runs) / planned_due, 4) if planned_due else None,
            "attempt_success_rate": round(len(ok_runs) / len(runs), 4) if runs else None,
        },
        "sources": per_source,
        "freshness": freshness,
        "latency": _latency_stats(ledger, started, window_end),
        "duplicates": _duplicate_stats(ledger, started, window_end),
        "integrity": _integrity_stats(ledger),
        "recovery": _recovery_stats(ledger, started, window_end),
        "storage": _storage_growth(ledger, started, window_end),
        "notes_zh": [
            "计划轮次按真实经过时间计算；未执行的轮次记为 missed，绝不计为成功。",
            "只有来源提供可精确到时刻的发布时间时才计算小时级延迟；其余标记为无法测量。",
            "VALIDATION_PASSED 只能在七天窗口真实结束后由 validate stop 显式写入。",
        ],
    }


def validation_status(ledger: ObservationLedger, *, now: datetime | None = None) -> dict[str, Any]:
    state = ledger.get_validation()
    if not state:
        return {
            "status": VALIDATION_NOT_STARTED,
            "started_at": None,
            "ends_at": None,
            "planned_slots": 0,
            "note_zh": "七天连续观察验证尚未开始（不会把未开始的任务报告为通过）",
        }
    metrics = compute_metrics(ledger, state, now=now)
    merged = {**dict(state), **metrics}
    merged["status"] = state.get("status") if state.get("status") in (
        VALIDATION_PASSED, VALIDATION_FAILED) else metrics.get("status")
    return merged


__all__ = [
    "DEFAULT_DAYS",
    "DEFAULT_INTERVAL_HOURS",
    "PROTOCOL_VERSION",
    "compute_metrics",
    "expected_interval_hours",
    "start_validation",
    "stop_validation",
    "validation_status",
]
