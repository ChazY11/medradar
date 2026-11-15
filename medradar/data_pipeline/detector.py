"""Source update detection.

The detector answers one question only: does the official endpoint advertise a version
that is not the one represented by the active MedRadar snapshot? It does not collect data
and it never changes the active snapshot.

Important limits:

* openFDA's ``meta.last_updated`` is endpoint-level. It is not a per-record revision
  timestamp, and it is not the date a regulatory event happened.
* A 404 on an unfiltered probe is not "no records"; it is a failed check.
* An HTTP failure is never reported as NO_CHANGE.
* If no trustworthy baseline exists, the answer is UNKNOWN (which authorises one
  reconciliation), not NO_CHANGE.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from .db import StateStore
from .model import CheckStatus, SOURCES, SourceSpec, iso_now, parse_iso
from .openfda import OpenFDAError, OpenFDAClient


def _view_version(manifest: dict[str, Any] | None, source_id: str) -> str | None:
    if not manifest:
        return None
    sources = manifest.get("sources") or {}
    if isinstance(sources, dict) and source_id in sources:
        value = (sources.get(source_id) or {}).get("official_last_updated")
        return str(value) if value else None
    # Legacy snapshots only had one global openfda.last_updated, taken from whichever
    # request happened to be last. It is retained for provenance, never used as a
    # per-source version.
    return None


def _view_total(manifest: dict[str, Any] | None, source_id: str) -> int | None:
    if not manifest:
        return None
    sources = manifest.get("sources") or {}
    if isinstance(sources, dict) and source_id in sources:
        value = (sources.get(source_id) or {}).get("official_total")
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None
    return None


def _is_date(value: str | None) -> bool:
    if not value:
        return False
    try:
        date.fromisoformat(value[:10])
    except ValueError:
        return False
    return True


def _too_far_in_future(value: str | None, now: datetime) -> bool:
    moment = parse_iso(value)
    if moment is None:
        return False
    return moment.date() > now.date()


def check_source(
    store: StateStore,
    client: OpenFDAClient,
    source: SourceSpec,
    active_manifest: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    moment = now or datetime.now(timezone.utc)
    checked_at = iso_now()
    previous = store.get_source(source.source_id) or {}
    previous_failures = int(previous.get("consecutive_failures") or 0)
    previous_update_available = bool(previous.get("update_available"))
    baseline_version = _view_version(active_manifest, source.source_id)
    baseline_total = _view_total(active_manifest, source.source_id)
    active_snapshot = str((active_manifest or {}).get("id") or "") or None

    def record(
        status: CheckStatus,
        message: str,
        *,
        evidence: dict[str, Any],
        last_updated: str | None = None,
        total: int | None = None,
        http_status: int | None = None,
        update_available: bool = False,
        failures: int = 0,
        success_check_at: str | None = previous.get("last_success_check_at"),
        failed_at: str | None = previous.get("last_failed_at"),
        export_date: str | None = None,
    ) -> dict[str, Any]:
        store.record_check(
            source_id=source.source_id,
            endpoint=source.endpoint,
            display_name=source.display_name,
            status=status.value,
            message=message,
            checked_at=checked_at,
            http_status=http_status,
            evidence=evidence,
            official_last_updated=last_updated,
            official_total=total,
            official_export_date=export_date,
            update_available=update_available,
            active_snapshot_id=active_snapshot,
            consecutive_failures=failures,
            last_success_check_at=success_check_at,
            last_failed_at=failed_at,
        )
        return {
            "source_id": source.source_id,
            "status": status.value,
            "message": message,
            "checked_at": checked_at,
            "http_status": http_status,
            "official_last_updated": last_updated,
            "official_total": total,
            "baseline_last_updated": baseline_version,
            "baseline_total": baseline_total,
            "update_available": update_available,
            "consecutive_failures": failures,
            "active_snapshot_id": active_snapshot,
            "declared_frequency": source.official_frequency,
            "check_interval_hours": source.check_interval_hours,
        }

    try:
        probe = client.probe(source)
    except OpenFDAError as error:
        failures = previous_failures + 1
        status = CheckStatus.SOURCE_DEGRADED if failures >= 3 else CheckStatus.CHECK_FAILED
        message = (
            "source check failed "
            + str(failures)
            + " consecutive time(s): "
            + str(error)
        )
        evidence = dict(error.evidence)
        evidence.update({"checked_at": checked_at, "error": str(error)})
        return record(
            status,
            message,
            evidence=evidence,
            last_updated=previous.get("official_last_updated"),
            total=previous.get("official_total"),
            http_status=error.status if isinstance(error.status, int) else None,
            update_available=previous_update_available,
            failures=failures,
            failed_at=checked_at,
        )

    last_updated = probe.get("last_updated")
    total = probe.get("total")
    evidence = {
        "url": probe.get("url"),
        "http_status": probe.get("http_status"),
        "checked_at": checked_at,
        "last_updated": last_updated,
        "total": total,
        "bytes": probe.get("bytes"),
        "elapsed_ms": probe.get("elapsed_ms"),
        "baseline_last_updated": baseline_version,
        "baseline_total": baseline_total,
    }

    if not _is_date(last_updated):
        return record(
            CheckStatus.SOURCE_DEGRADED,
            "the endpoint did not expose a trustworthy meta.last_updated",
            evidence=evidence,
            last_updated=last_updated,
            total=total,
            http_status=int(probe.get("http_status") or 200),
            update_available=False,
            failures=0,
            success_check_at=checked_at,
        )
    if _too_far_in_future(str(last_updated), moment):
        return record(
            CheckStatus.SOURCE_DEGRADED,
            "meta.last_updated is in the future; refusing to treat the source as synchronised",
            evidence=evidence,
            last_updated=str(last_updated),
            total=total,
            http_status=int(probe.get("http_status") or 200),
            update_available=False,
            failures=0,
            success_check_at=checked_at,
        )
    if baseline_version is None:
        return record(
            CheckStatus.UNKNOWN,
            "no per-source official version is recorded in the active snapshot; one reconciliation is required",
            evidence=evidence,
            last_updated=str(last_updated),
            total=total,
            http_status=int(probe.get("http_status") or 200),
            update_available=True,
            failures=0,
            success_check_at=checked_at,
        )
    if str(last_updated) < baseline_version:
        return record(
            CheckStatus.SOURCE_DEGRADED,
            "the official version moved backwards (" + str(last_updated) + " < " + baseline_version + ")",
            evidence=evidence,
            last_updated=str(last_updated),
            total=total,
            http_status=int(probe.get("http_status") or 200),
            update_available=False,
            failures=0,
            success_check_at=checked_at,
        )
    if total is not None and baseline_total is not None and baseline_total > 0:
        drop = (baseline_total - int(total)) / float(baseline_total)
        if drop >= 0.05:
            return record(
                CheckStatus.SOURCE_DEGRADED,
                "official total dropped by " + format(drop * 100.0, ".1f") + "%; automatic sync blocked for review",
                evidence=evidence,
                last_updated=str(last_updated),
                total=total,
                http_status=int(probe.get("http_status") or 200),
                update_available=False,
                failures=0,
                success_check_at=checked_at,
            )
    if str(last_updated) > baseline_version:
        return record(
            CheckStatus.UPDATE_AVAILABLE,
            "official version advanced from " + baseline_version + " to " + str(last_updated),
            evidence=evidence,
            last_updated=str(last_updated),
            total=total,
            http_status=int(probe.get("http_status") or 200),
            update_available=True,
            failures=0,
            success_check_at=checked_at,
        )
    if baseline_total is not None and total is not None and int(total) != baseline_total:
        return record(
            CheckStatus.UPDATE_AVAILABLE,
            "official record total changed from " + str(baseline_total) + " to " + str(total)
            + " while meta.last_updated stayed the same",
            evidence=evidence,
            last_updated=str(last_updated),
            total=total,
            http_status=int(probe.get("http_status") or 200),
            update_available=True,
            failures=0,
            success_check_at=checked_at,
        )
    return record(
        CheckStatus.NO_CHANGE,
        "official version and total match the active snapshot",
        evidence=evidence,
        last_updated=str(last_updated),
        total=total,
        http_status=int(probe.get("http_status") or 200),
        update_available=False,
        failures=0,
        success_check_at=checked_at,
    )


def check_sources(
    store: StateStore,
    client: OpenFDAClient,
    active_manifest: dict[str, Any] | None,
    source_ids: list[str] | None = None,
    *,
    due_only: bool = False,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    moment = now or datetime.now(timezone.utc)
    wanted = source_ids or list(SOURCES)
    results = []
    for source_id in wanted:
        source = SOURCES[source_id]
        row = store.get_source(source_id) or {}
        if due_only and not source.is_due(
            row.get("last_checked_at"), moment, last_status=row.get("last_check_status")
        ):
            results.append({
                "source_id": source_id,
                "status": "SKIPPED_NOT_DUE",
                "message": "next check is not due",
                "checked_at": row.get("last_checked_at"),
                "official_last_updated": row.get("official_last_updated"),
                "official_total": row.get("official_total"),
                "update_available": bool(row.get("update_available")),
            })
            continue
        results.append(check_source(store, client, source, active_manifest, now=moment))
    return results
