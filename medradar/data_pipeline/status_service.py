"""Read-only data freshness and change-feed projections for the public API.

If the pipeline has not been configured, the response says so. It does not invent check
times, zero change counts or a "real-time" status. A snapshot can be served with
``synchronization.state = "not_configured"`` and unknown source freshness; that is an
honest product state.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from medradar.product.data_dir import read_active_pointer, resolve_snapshot_dir

from .config import Settings
from .db import StateStore
from .model import SOURCES

PRODUCT_SOURCE_ORDER = ("openfda_510k", "openfda_pma", "openfda_recall", "openfda_classification")


def default_pipeline_db(data_dir: Path | str | None = None) -> Path | None:
    configured = os.environ.get("MEDRADAR_PIPELINE_DB")
    if configured:
        return Path(configured)
    root = os.environ.get("MEDRADAR_PIPELINE_ROOT")
    if root:
        return Path(root) / "pipeline.db"
    if data_dir is not None:
        path = Path(data_dir)
        if (path / "pipeline.db").is_file():
            return path / "pipeline.db"
        if (path / "active.json").is_file() and (path / "pipeline.db").is_file():
            return path / "pipeline.db"
    return None


def _active_manifest(data_dir: Path | str | None) -> tuple[Path | None, dict[str, Any] | None, dict[str, Any] | None]:
    if data_dir is None:
        return None, None, None
    root = Path(data_dir)
    try:
        pointer = read_active_pointer(root)
        resolved = resolve_snapshot_dir(root)
        manifest_path = resolved / "snapshot.json"
        if not manifest_path.is_file():
            return None, None, pointer
        return resolved, json.loads(manifest_path.read_text(encoding="utf-8")), pointer
    except Exception:
        return None, None, None


def _age_days(value: str | None) -> int | None:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return max(0, (datetime.now(timezone.utc) - moment).days)


def _records_by_source(manifest: dict[str, Any] | None) -> dict[str, int]:
    return dict(((manifest or {}).get("counts") or {}).get("by_source") or {})


def _base_sources(manifest: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = []
    versions = (manifest or {}).get("sources") or {}
    counts = _records_by_source(manifest)
    for source_id in PRODUCT_SOURCE_ORDER:
        spec = SOURCES[source_id]
        version = versions.get(source_id) or {}
        rows.append({
            "source_id": source_id,
            "source_name": spec.display_name,
            "endpoint": spec.endpoint,
            "is_support_source": spec.is_support_source,
            "declared_frequency": spec.official_frequency,
            "check_interval_hours": spec.check_interval_hours,
            "official_last_updated": version.get("official_last_updated"),
            "official_total": version.get("official_total"),
            "record_count": counts.get(source_id, 0),
            "last_checked_at": None,
            "last_success_check_at": None,
            "last_success_sync_at": None,
            "last_success_official_last_updated": None,
            "last_success_official_total": None,
            "last_failed_at": None,
            "last_full_reconciliation_at": None,
            "last_full_reconciliation_snapshot_id": None,
            "consecutive_failures": 0,
            "status": "UNKNOWN",
            "message": "No check has been recorded for this source.",
            "update_available": False,
            "added_since_previous": None,
            "updated_since_previous": None,
            "removed_confirmed_since_previous": None,
            "missing_on_recheck_since_previous": None,
            "unresolved_since_previous": None,
            "freshness_age_days": _age_days(version.get("official_last_updated")),
            "freshness_basis": "official endpoint version (not per-record revision time)",
            "note": spec.note,
        })
    return rows


def _source_rows(store: StateStore, manifest: dict[str, Any] | None) -> list[dict[str, Any]]:
    base = _base_sources(manifest)
    by_id = {row["source_id"]: row for row in base}
    records = _records_by_source(manifest)
    active_id = str((manifest or {}).get("id") or "")
    counts = store.change_counts_by_source(active_id) if active_id else {}
    for row in store.list_sources():
        target = by_id.get(str(row.get("source_id")))
        if target is None:
            continue
        source_counts = counts.get(target["source_id"], {})
        target.update({
            "last_checked_at": row.get("last_checked_at"),
            "last_success_check_at": row.get("last_success_check_at"),
            "last_success_sync_at": row.get("last_success_sync_at"),
            "last_success_official_last_updated": row.get("last_success_official_last_updated"),
            "last_success_official_total": row.get("last_success_official_total"),
            "last_failed_at": row.get("last_failed_at"),
            "last_full_reconciliation_at": row.get("last_full_reconciliation_at"),
            "last_full_reconciliation_snapshot_id": row.get("last_full_reconciliation_snapshot_id"),
            "sync_status": ((manifest or {}).get("sources") or {}).get(target["source_id"], {}).get("sync_status"),
            "reconciliation_mode": ((manifest or {}).get("sources") or {}).get(target["source_id"], {}).get("reconciliation_mode"),
            "consecutive_failures": int(row.get("consecutive_failures") or 0),
            "status": row.get("last_check_status") or "UNKNOWN",
            "message": row.get("last_check_message"),
            "update_available": bool(row.get("update_available")),
            "official_last_updated": row.get("official_last_updated") or target.get("official_last_updated"),
            "official_total": row.get("official_total") if row.get("official_total") is not None else target.get("official_total"),
            "record_count": records.get(target["source_id"], target.get("record_count", 0)),
            "freshness_age_days": _age_days(row.get("official_last_updated") or target.get("official_last_updated")),
            "added_since_previous": int(source_counts.get("ADDED", 0)),
            "updated_since_previous": int(source_counts.get("UPDATED", 0)),
            "removed_confirmed_since_previous": int(source_counts.get("REMOVED_CONFIRMED", 0)),
            "missing_on_recheck_since_previous": int(source_counts.get("MISSING_ON_RECHECK", 0)),
            "unresolved_since_previous": int(source_counts.get("UNRESOLVED", 0)),
        })
    return base


def _sync_health(
    sources: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    incidents: list[dict[str, Any]],
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    latest_run = runs[0] if runs else None
    failed = [row["source_id"] for row in sources if row["status"] in ("CHECK_FAILED", "SOURCE_DEGRADED")]
    pending = [row["source_id"] for row in sources if row["update_available"]]
    unknown = [row["source_id"] for row in sources if row["status"] == "UNKNOWN"]
    last_check = max((row.get("last_checked_at") or "" for row in sources), default="")
    last_success = max((row.get("last_success_sync_at") or "" for row in sources), default="")
    latest_status = str((latest_run or {}).get("status") or "UNKNOWN")
    consecutive_deferred = 0
    for row in runs:
        if str(row.get("status") or "") == "DEFERRED":
            consecutive_deferred += 1
        else:
            break
    deferral = None
    if latest_status == "DEFERRED" and latest_run:
        metrics = latest_run.get("metrics") or {}
        deferral = {
            "reason": str(metrics.get("reason") or "DEFERRED_RESOURCE_PRESSURE"),
            "reasons": list(metrics.get("reasons") or []),
            "phase": metrics.get("phase"),
            "consecutive": consecutive_deferred,
            "escalated": consecutive_deferred >= 3,
            "guard": metrics.get("guard"),
            "retry": metrics.get("retry"),
        }
    if failed or latest_status in ("FAILED", "BLOCKED", "PARTIAL"):
        state = "degraded"
    elif latest_status == "RUNNING" and latest_run:
        started = latest_run.get("started_at")
        try:
            started_at = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
            state = "stale" if (now - started_at).total_seconds() > 7200 else "running"
        except (TypeError, ValueError):
            state = "running"
    elif latest_status == "DEFERRED":
        # The host guard refused to start a reconciliation. Nothing was collected and no source
        # state advanced, so this is a visible wait, not a failure and not a success.
        state = "deferred"
    elif pending:
        # An available official update is not "stale" until the scheduled attempt is overdue.
        state = "update_pending"
    elif unknown:
        state = "unknown"
    else:
        state = "ok"
    return {
        "state": state,
        "latest_run_status": latest_status,
        "latest_run_id": (latest_run or {}).get("run_id"),
        "last_check_at": last_check or None,
        "last_successful_sync_at": last_success or None,
        "failed_sources": failed,
        "pending_sources": pending,
        "unknown_sources": unknown,
        "latest_incident": incidents[0] if incidents else None,
        "deferral": deferral,
        "note": "A web process being alive is not a successful synchronization; this is the sync-specific state.",
    }


def _pipeline_freshness(sources: list[dict[str, Any]], manifest: dict[str, Any] | None) -> dict[str, Any]:
    official_dates = [str(row.get("official_last_updated")) for row in sources if row.get("official_last_updated")]
    latest_official = max(official_dates) if official_dates else None
    official_age = _age_days(latest_official)
    snapshot_age = _age_days((manifest or {}).get("collected_at"))
    pending = [row["source_id"] for row in sources if row["update_available"]]
    failed = [row["source_id"] for row in sources if row["status"] in ("CHECK_FAILED", "SOURCE_DEGRADED")]
    if failed:
        state = "degraded"
    elif pending:
        state = "update_pending"
    elif any(row.get("status") == "UNKNOWN" for row in sources):
        state = "unknown"
    else:
        state = "current"
    return {
        "state": state,
        "latest_official_version": latest_official,
        "official_version_age_days": official_age,
        "snapshot_age_days": snapshot_age,
        "pending_sources": pending,
        "failed_sources": failed,
        "note": (
            "Official version age is not staleness by itself: FDA publishes monthly/weekly. "
            "A pending update or a failed check is what can make synchronization stale."
        ),
    }


def data_status(
    *,
    data_dir: Path | str | None = None,
    pipeline_db: Path | str | None = None,
) -> dict[str, Any]:
    resolved, manifest, pointer = _active_manifest(data_dir)
    db_path = Path(pipeline_db) if pipeline_db is not None else default_pipeline_db(data_dir)
    configured = db_path is not None and db_path.is_file()
    snapshot_payload = None
    if manifest is not None:
        snapshot_payload = {
            "id": manifest.get("id"),
            "schema": manifest.get("schema"),
            "collected_at": manifest.get("collected_at"),
            "published_at": (pointer or {}).get("published_at"),
            "previous_snapshot_id": (manifest.get("lineage") or {}).get("previous_snapshot_id"),
            "content_hash": (manifest.get("lineage") or {}).get("content_hash"),
            "openfda_last_updated": (manifest.get("openfda") or {}).get("last_updated"),
            "counts": manifest.get("counts"),
            "change_summary": manifest.get("change_summary"),
            "source_versions": manifest.get("sources"),
            "path": str(resolved) if resolved else None,
            "time_semantics": manifest.get("time_semantics") or [],
        }

    if not configured:
        return {
            "schema": "medradar.data_status.v1",
            "configured": False,
            "state": "not_configured",
            "message": (
                "The continuous pipeline has not been configured on this deployment. "
                "This snapshot is immutable and was produced by a manual collection; no automatic "
                "check or sync time exists to report."
            ),
            "terminology": {
                "continuously_monitored": False,
                "automatically_synchronized": False,
                "real_time_claim": False,
                "labels": ["Data Snapshot", "Source Freshness", "Last Successful Sync"],
            },
            "snapshot": snapshot_payload,
            "synchronization": {
                "state": "not_configured",
                "last_successful_sync": None,
                "last_check_attempt": None,
                "active_snapshot_id": (manifest or {}).get("id"),
                "change_feed_available": False,
                "note": "No pipeline database is present. Dates below are the snapshot's own timestamps, not synchronization times.",
            },
            "sources": _base_sources(manifest),
            "health": {
                "data": {"state": "available" if manifest else "unavailable", "using_fallback": False},
                "sync": {"state": "not_configured"},
                "freshness": _pipeline_freshness(_base_sources(manifest), manifest),
            },
            "change_counts": {},
            "recent_runs": [],
            "incidents": [],
            "request_usage_today": None,
            "change_feed": [],
            "latency": {
                "official_source_version": (manifest or {}).get("openfda", {}).get("last_updated") if manifest else None,
                "last_checked_by_medradar": None,
                "last_successful_sync": None,
                "sync_lag_hours": None,
                "statement": "MedRadar can only synchronise records after FDA publishes them. No pre-publication access is implied.",
            },
        }

    store = StateStore(db_path, read_only=True)
    sources = _source_rows(store, manifest)
    runs = store.recent_runs(12)
    incidents = store.incidents(12)
    latest = store.latest_publication()
    active_id = str((manifest or {}).get("id") or "")
    change_counts = store.change_counts(active_id) if active_id else {}
    feed, _total = store.list_changes(limit=12, offset=0)
    degraded = [row for row in sources if row["status"] in ("CHECK_FAILED", "SOURCE_DEGRADED")]
    update_available = [row for row in sources if row["update_available"]]
    unverified = [row for row in sources if row["status"] == "UNKNOWN"]
    latest_run_status = str((runs[0] if runs else {}).get("status") or "")
    sync_health = _sync_health(sources, runs, incidents)
    if not latest:
        state = "configured_no_publication"
    elif degraded or latest_run_status in ("FAILED", "BLOCKED"):
        state = "degraded"
    elif latest_run_status == "PARTIAL":
        state = "partial"
    elif latest_run_status == "DEFERRED":
        state = "deferred"
    elif update_available:
        state = "update_available"
    elif unverified:
        state = "unverified"
    else:
        state = "ok"
    last_sync = (latest or {}).get("published_at")
    last_check = max((row.get("last_checked_at") or "" for row in sources), default="")
    lag = None
    if last_sync:
        try:
            synced = datetime.fromisoformat(str(last_sync).replace("Z", "+00:00"))
            official = max(
                (row.get("official_last_updated") or "" for row in sources),
                default="",
            )
            if official:
                official_date = datetime.fromisoformat(str(official)[:10]).replace(tzinfo=timezone.utc)
                lag = round((synced - official_date).total_seconds() / 3600.0, 2)
        except ValueError:
            lag = None
    return {
        "schema": "medradar.data_status.v1",
        "configured": True,
        "state": state,
        "message": {
            "ok": "Sources are monitored and the active snapshot is the latest successful publication.",
            "update_available": "An official update is available; the next synchronization has not completed.",
            "degraded": "At least one source check or synchronization failed. The previous snapshot remains active for the affected source.",
            "partial": "A partial publication succeeded: healthy sources were updated while at least one source retained its previous version.",
            "unverified": "One or more sources have no recorded check yet. The snapshot is being served, but source freshness is unknown.",
            "configured_no_publication": "The pipeline is configured but no publication has been recorded.",
            "deferred": (
                "Synchronization was deferred to protect host memory (DEFERRED_RESOURCE_PRESSURE). "
                "Nothing was collected, the active snapshot is unchanged and the next scheduled run retries."
            ),
        }.get(state, state),
        "terminology": {
            "continuously_monitored": True,
            "automatically_synchronized": True,
            "real_time_claim": False,
            "labels": ["Continuously Monitored", "Automatically Synchronized", "Last Successful Sync", "Source Freshness", "Data Snapshot"],
        },
        "snapshot": snapshot_payload,
        "synchronization": {
            "state": state,
            "last_successful_sync": last_sync,
            "last_check_attempt": last_check or None,
            "active_snapshot_id": active_id or None,
            "change_feed_available": True,
            "action": (latest or {}).get("action"),
            "actor": (latest or {}).get("actor"),
            "updated_sources": [row["source_id"] for row in update_available],
            "deferral": sync_health.get("deferral"),
        },
        "sources": sources,
        "health": {
            "data": {
                "state": "available" if snapshot_payload else "unavailable",
                "using_fallback": False,
                "snapshot_id": (manifest or {}).get("id"),
            },
            "sync": sync_health,
            "freshness": _pipeline_freshness(sources, manifest),
        },
        "change_counts": change_counts,
        "recent_runs": runs,
        "incidents": incidents,
        "request_usage_today": store.request_usage(datetime.now(timezone.utc).strftime("%Y-%m-%d")),
        "change_feed": feed,
        "latency": {
            "official_source_version": (manifest or {}).get("openfda", {}).get("last_updated") if manifest else None,
            "last_checked_by_medradar": last_check or None,
            "last_successful_sync": last_sync,
            "sync_lag_hours": lag,
            "statement": (
                "Official version dates are endpoint-level source markers. MedRadar checks them on a schedule, "
                "then publishes only after a complete scoped collection and validation. A record's regulatory "
                "event date is never replaced by either time."
            ),
        },
    }


def changes_feed(
    *,
    source_id: str | None = None,
    change_type: str | None = None,
    organization_key: str | None = None,
    limit: int = 50,
    offset: int = 0,
    pipeline_db: Path | str | None = None,
    data_dir: Path | str | None = None,
) -> dict[str, Any]:
    db_path = Path(pipeline_db) if pipeline_db is not None else default_pipeline_db(data_dir)
    if db_path is None or not db_path.is_file():
        return {
            "configured": False,
            "items": [],
            "total": 0,
            "filters": {"source_id": source_id, "change_type": change_type, "organization_key": organization_key},
            "message": "No pipeline database is configured; no change feed exists.",
        }
    store = StateStore(db_path, read_only=True)
    items, total = store.list_changes(
        source_id=source_id, change_type=change_type, organization_key=organization_key,
        limit=limit, offset=offset,
    )
    return {
        "configured": True,
        "items": items,
        "total": total,
        "page": (offset // limit) + 1 if limit else 1,
        "page_size": limit,
        "filters": {"source_id": source_id, "change_type": change_type, "organization_key": organization_key},
        "note": "A change is a change MedRadar detected in an official source; it is not by itself a new regulatory event.",
    }
