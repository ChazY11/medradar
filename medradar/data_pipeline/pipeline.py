"""End-to-end orchestration: check -> collect -> diff -> build -> validate -> publish."""
from __future__ import annotations

import gc
import gzip
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from medradar.product.data_dir import read_active_pointer

from .changes import build_change_set
from .collector import AllCollection, CollectionError, Collector
from .config import PIPELINE_VERSION, Settings
from .db import StateStore
from .detector import check_sources
from .lock import PipelineLock
from .model import ALL_SOURCE_IDS, PRODUCT_SOURCE_IDS, SOURCES, CheckStatus, RunStatus
from .openfda import OpenFDAClient, OpenFDAError
from .publisher import active_snapshot, commit_publication, recover_publication, rollback as publisher_rollback
from .snapshot import build_snapshot
from .validator import validate_snapshot

DEFAULT_SCOPE_NOTE = (
    "Queries cover the reviewed organization roster and its exact search tokens. "
    "This is not the complete FDA applicant universe."
)


class PipelineError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_jsonl_gz(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _read_manifest(path: Path) -> dict[str, Any]:
    return json.loads((path / "snapshot.json").read_text(encoding="utf-8"))


def _scope_from_registry(registry: dict[str, Any]) -> dict[str, Any]:
    organizations = registry.get("organizations") or []
    items = []
    display = {}
    for org in organizations:
        key = str(org.get("key") or "")
        if not key:
            continue
        tokens = sorted({str(token) for token in (org.get("search_tokens") or []) if str(token).strip()})
        items.append({"key": key, "tokens": tokens})
        display[key] = org.get("display_name")
    basis = json.dumps({
        "organizations": sorted(items, key=lambda item: item["key"]),
        "matching_rule": registry.get("matching_rule"),
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "organization_count": len(items),
        "organizations": display,
        "organization_keys": sorted(item["key"] for item in items),
        "scope_hash": hashlib.sha256(basis.encode("utf-8")).hexdigest(),
        "matching_rule": registry.get("matching_rule"),
        "note": DEFAULT_SCOPE_NOTE,
    }


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        *,
        store: StateStore | None = None,
        client: OpenFDAClient | None = None,
        recover: bool = True,
    ) -> None:
        self.settings = settings.ensure()
        self.store = store or StateStore(self.settings.state_db)
        self.client = client or OpenFDAClient(self.settings, self.store)
        registry_path = self.settings.registry_path or (
            Path(__file__).resolve().parents[1] / "product" / "identity" / "organizations.json"
        )
        self.registry = json.loads(Path(registry_path).read_text(encoding="utf-8"))
        self.scope = _scope_from_registry(self.registry)
        if recover:
            try:
                recover_publication(self.store, self.settings)
            except Exception as error:
                self.store.record_incident("publication_recovery_failed", {"error": str(error)})

    # ------------------------------------------------------------------ helpers
    def _active(self) -> tuple[Path, dict[str, Any], dict[str, Any]]:
        active = active_snapshot(self.settings)
        if active is None:
            raise PipelineError("no active snapshot; run bootstrap first")
        return active

    def _previous_events(self, path: Path) -> dict[str, dict[str, Any]]:
        events = _read_jsonl_gz(path / "events.jsonl.gz")
        return {str(event["event_id"]): event for event in events}

    def _previous_classifications(self, path: Path) -> list[dict[str, Any]]:
        return _read_jsonl_gz(path / "classifications.jsonl.gz")

    def _check_locked(self, source_ids: Sequence[str], *, due_only: bool) -> list[dict[str, Any]]:
        active = active_snapshot(self.settings)
        manifest = active[1] if active else None
        return check_sources(
            self.store, self.client, manifest, list(source_ids), due_only=due_only
        )

    def _targets(
        self, requested: Sequence[str], *, force: bool, allow_degraded: bool,
        ignore_failures: bool = False, include_sources: Sequence[str] = (),
    ) -> tuple[list[str], list[dict[str, Any]]]:
        targets: list[str] = []
        include = set(include_sources)
        problems: list[dict[str, Any]] = []
        for source_id in requested:
            row = self.store.get_source(source_id) or {}
            status = str(row.get("last_check_status") or "")
            if status in (CheckStatus.CHECK_FAILED.value, CheckStatus.SOURCE_DEGRADED.value):
                problems.append({"source_id": source_id, "status": status, "message": row.get("last_check_message")})
                if ignore_failures:
                    continue
                if allow_degraded and force:
                    targets.append(source_id)
                continue
            if force or bool(row.get("update_available")) or source_id in include:
                targets.append(source_id)
        if problems and not (allow_degraded or ignore_failures):
            raise PipelineError(
                "source checks failed or degraded; automatic sync blocked: "
                + json.dumps(problems, ensure_ascii=False)
            )
        return targets, problems

    def _full_reconciliation_due(self, *, exclude: set[str] | None = None) -> list[str]:
        """Return the oldest product sources due for a content reconciliation.

        This is deliberately capped. A version check can miss a corrected record when the
        endpoint version and total do not change. A rolling low-frequency full sweep closes
        that gap without collecting every source in one 4 GB process.
        """
        exclude = exclude or set()
        now = datetime.now(timezone.utc)
        due: list[tuple[str, str]] = []
        for source_id in PRODUCT_SOURCE_IDS:
            if source_id in exclude:
                continue
            row = self.store.get_source(source_id) or {}
            if str(row.get("last_check_status") or "") in (
                CheckStatus.CHECK_FAILED.value, CheckStatus.SOURCE_DEGRADED.value
            ):
                continue
            last = row.get("last_full_reconciliation_at")
            if not last:
                due.append((source_id, ""))
                continue
            try:
                moment = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
            except ValueError:
                due.append((source_id, ""))
                continue
            if (now - moment).total_seconds() >= self.settings.full_reconciliation_interval_hours * 3600:
                due.append((source_id, str(last)))
        due.sort(key=lambda item: (item[1] or "", item[0]))
        return [source_id for source_id, _ in due[: self.settings.full_reconciliation_max_sources_per_run]]

    def _full_reconciliation_budget_ok(self, sources: Sequence[str]) -> tuple[bool, str | None]:
        usage = self.store.request_usage(datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        used = int(usage.get("total_requests") or 0)
        limit = int(self.settings.daily_request_limit or 900)
        # Keep reserve for normal checks and retries; a full sweep must not consume the
        # whole daily budget and leave the scheduler unable to check other sources.
        reserve = max(20, int(limit * 0.05))
        remaining = limit - used - reserve
        active = active_snapshot(self.settings)
        audit = ((active[1] if active else {}) or {}).get("collection_audit") or {}
        estimates = audit.get("by_source_requests") or {}
        estimate = sum(max(1, int(estimates.get(source_id) or 120)) for source_id in sources)
        if remaining < estimate:
            return False, (
                "full reconciliation deferred: need about " + str(estimate)
                + " requests, only " + str(max(0, remaining)) + " remain after reserve"
            )
        return True, None

    def _source_versions(
        self,
        active_manifest: dict[str, Any],
        *,
        successful_sources: Sequence[str],
        failed_sources: dict[str, dict[str, Any]],
        checked_at: str,
        not_attempted: Sequence[str] = (),
        full_sources: Sequence[str] = (),
    ) -> dict[str, Any]:
        """Build the per-source manifest even when only some sources were reconciled.

        A failed source keeps the official version represented by its old events. The
        manifest records the check/sync outcome separately so a partial snapshot is never
        presented as if every source had been refreshed.
        """
        versions = dict(active_manifest.get("sources") or {})
        successful = set(successful_sources)
        skipped = set(not_attempted) - successful - set(failed_sources)
        full_set = set(full_sources)
        for source_id in ALL_SOURCE_IDS:
            previous = dict(versions.get(source_id) or {})
            base = {
                "source_id": source_id,
                "endpoint": SOURCES[source_id].endpoint,
                "display_name": SOURCES[source_id].display_name,
                "official_last_updated": None,
                "official_total": None,
                "declared_frequency": SOURCES[source_id].official_frequency,
            }
            base.update(previous)
            row = self.store.get_source(source_id) or {}
            if row:
                base.update({
                    "official_last_updated": row.get("official_last_updated"),
                    "official_total": row.get("official_total"),
                    "last_checked_at": row.get("last_checked_at") or checked_at,
                    "last_check_status": row.get("last_check_status"),
                    "last_check_message": row.get("last_check_message"),
                    "last_success_sync_at": row.get("last_success_sync_at"),
                    "last_full_reconciliation_at": row.get("last_full_reconciliation_at"),
                    "last_full_reconciliation_snapshot_id": row.get("last_full_reconciliation_snapshot_id"),
                    "consecutive_failures": int(row.get("consecutive_failures") or 0),
                })
            base.update({
                "declared_frequency": SOURCES[source_id].official_frequency,
                "check_interval_hours": SOURCES[source_id].check_interval_hours,
                "note": SOURCES[source_id].note,
            })
            if source_id not in successful:
                # The advertised version is not represented by the active events unless
                # this source actually reconciled. Preserve the old event version for failed,
                # deferred and intentionally unchanged sources.
                base.update({
                    "official_last_updated": previous.get("official_last_updated"),
                    "official_total": previous.get("official_total"),
                    "reconciliation_mode": "UNCHANGED",
                })
            if source_id in failed_sources:
                failure = failed_sources[source_id]
                base.update({
                    "sync_status": "FAILED",
                    "reconciliation_mode": "FAILED",
                    "last_sync_error": str(failure.get("message") or failure.get("error") or ""),
                    "last_sync_attempt_at": checked_at,
                })
            elif source_id in successful:
                mode = "FULL" if source_id in full_set else "VERSION_TRIGGERED"
                if source_id == "openfda_classification":
                    mode = "SUPPORT_REFRESH"
                base.update({
                    "sync_status": "SYNCED",
                    "reconciliation_mode": mode,
                    "last_sync_error": None,
                    "last_sync_attempt_at": checked_at,
                })
            elif source_id in skipped:
                base.update({
                    "sync_status": "UNCHANGED",
                    "last_sync_error": None,
                })
            else:
                base["sync_status"] = "UNCHANGED"
            versions[source_id] = base
        return versions

    def _stamp_changes(self, changes: list[dict[str, Any]], snapshot_id: str) -> None:
        for row in changes:
            row["candidate_snapshot_id"] = snapshot_id
            evidence = dict(row.get("evidence") or {})
            evidence["candidate_snapshot_id"] = snapshot_id
            row["evidence"] = evidence

    def _assign_organizations(self, changes: list[dict[str, Any]], review_db: Path | None) -> None:
        try:
            from medradar.product.identity import registry_with_overlay
            from medradar.product.review.store import ReviewStore

            overlay: tuple = ()
            if review_db is not None and Path(review_db).is_file():
                overlay = ReviewStore(Path(review_db)).overlay_items()
            registry = registry_with_overlay(overlay)
            for row in changes:
                applicant = str(row.get("applicant_name") or "")
                decision, _rejection = registry.decide(applicant)
                row["organization_key"] = decision.organization_key if decision is not None else None
        except Exception:
            for row in changes:
                row.setdefault("organization_key", None)

    def _audit_for_snapshot(
        self,
        active_manifest: dict[str, Any],
        product_targets: Sequence[str],
        collection: Any,
        *,
        classification_audit: dict[str, Any] | None,
        requests: int,
        response_bytes: int,
    ) -> dict[str, Any]:
        previous = dict(active_manifest.get("collection_audit") or {})
        audits = dict(previous.get("sources") or {})
        by_source_requests = dict(previous.get("by_source_requests") or {})
        by_source_bytes = dict(previous.get("by_source_bytes") or {})
        for source_id in product_targets:
            audits[source_id] = collection.source_audits.get(source_id) or []
            by_source_requests[source_id] = int(getattr(collection, "requests_by_source", {}).get(source_id, 0))
            by_source_bytes[source_id] = int(getattr(collection, "bytes_by_source", {}).get(source_id, 0))
        classification = classification_audit if classification_audit is not None else (previous.get("classification") or {})
        if classification_audit is not None:
            by_source_requests["openfda_classification"] = int(classification_audit.get("requests") or 0)
            by_source_bytes["openfda_classification"] = int(classification_audit.get("response_bytes") or 0)
        errors = list(collection.errors or [])
        return {
            "sources": audits,
            "classification": classification,
            "by_source_requests": by_source_requests,
            "by_source_bytes": by_source_bytes,
            "request_count": sum(int(value or 0) for value in by_source_requests.values()),
            "response_bytes": sum(int(value or 0) for value in by_source_bytes.values()),
            "errors": errors,
            "complete": not errors,
            "scope_note": DEFAULT_SCOPE_NOTE,
        }

    # ------------------------------------------------------------------ bootstrap
    def bootstrap(self, from_snapshot: Path | str, *, actor: str = "bootstrap") -> dict[str, Any]:
        source = Path(from_snapshot)
        if not (source / "snapshot.json").is_file():
            raise PipelineError("bootstrap source has no snapshot.json: " + str(source))
        with PipelineLock(self.settings.lock_path):
            if active_snapshot(self.settings) is not None:
                raise PipelineError("an active snapshot already exists; bootstrap refuses to overwrite it")
            old = _read_manifest(source)
            old_events = _read_jsonl_gz(source / "events.jsonl.gz")
            old_classifications = _read_jsonl_gz(source / "classifications.jsonl.gz")
            collected = str(old.get("collected_at") or _now())
            now = _now()
            events: dict[str, dict[str, Any]] = {}
            for raw_event in old_events:
                event = dict(raw_event)
                event.setdefault("first_observed_at", collected)
                event.setdefault("last_synced_at", collected)
                event.setdefault("source_updated_at", None)
                event.setdefault("record_state", "ACTIVE")
                event.setdefault("missing_count", 0)
                event.setdefault("collection_scopes", [])
                if not event.get("content_hash"):
                    from .normalize import content_hash
                    event["content_hash"] = content_hash(event)
                events[event["event_id"]] = event
            source_versions = {}
            for source_id in ALL_SOURCE_IDS:
                source_versions[source_id] = {
                    "source_id": source_id,
                    "endpoint": SOURCES[source_id].endpoint,
                    "display_name": SOURCES[source_id].display_name,
                    "official_last_updated": None,
                    "official_total": None,
                    "declared_frequency": SOURCES[source_id].official_frequency,
                    "note": "Bootstrapped from a legacy snapshot; no per-source official version was recorded by that release.",
                }
            collection_started = str(old.get("collection_started_at") or collected)
            path, manifest = build_snapshot(
                self.settings,
                events=events,
                classifications=old_classifications,
                source_versions=source_versions,
                collection_audit={
                    "sources": {},
                    "classification": {},
                    "by_source_requests": {},
                    "by_source_bytes": {},
                    "request_count": 0,
                    "response_bytes": 0,
                    "errors": [],
                    "complete": True,
                    "bootstrap_legacy_snapshot": str(source),
                },
                change_summary={
                    "added": 0, "updated": 0, "removed_confirmed": 0, "unchanged": len(events),
                    "missing_on_recheck": 0, "unresolved": 0, "records_seen": len(events),
                    "baseline_import": True, "first_reconciliation": False,
                },
                scope=self.scope,
                previous_snapshot_id=None,
                collection_started_at=collection_started,
                now=now,
            )
            observations = []
            for event in events.values():
                observations.append({
                    "source_id": event["source_id"], "event_id": event["event_id"],
                    "official_record_id": str(event.get("official_id") or ""),
                    "first_observed_at": event["first_observed_at"], "last_seen_at": now,
                    "last_seen_snapshot_id": manifest["id"], "last_content_hash": event["content_hash"],
                    "state": "ACTIVE", "missing_count": 0, "last_missing_at": None,
                    "organization_key": None, "applicant_name": event.get("applicant_name"),
                    "event_type": event.get("event_type"), "event_date": event.get("event_date"),
                })
            # The on-disk snapshot is complete. Drop the full in-memory event map before
            # validation loads the product dataset, so peak RSS is max(candidate, product)
            # rather than the sum of both representations.
            del events
            gc.collect()
            report = validate_snapshot(
                path, settings=self.settings, previous_dir=None, validate_product=True
            )
            if not report.ok:
                raise PipelineError("bootstrap snapshot failed validation: " + json.dumps(report.to_public()["errors"][:5]))
            manifest_sha = hashlib.sha256((path / "snapshot.json").read_bytes()).hexdigest()
            self.store.register_snapshot(
                snapshot_id=str(manifest["id"]), path=str(path), content_hash=(manifest.get("lineage") or {}).get("content_hash"),
                created_at=now, status="staged", parent_snapshot_id=None, source_versions=source_versions,
                counts=manifest.get("counts") or {}, manifest_sha256=manifest_sha, validation=report.to_public(),
            )
            commit_publication(
                self.store, self.settings, snapshot_dir=path, manifest=manifest, run_id=None,
                previous_snapshot_id=None, action="bootstrap", actor=actor,
                note="Bootstrap from legacy immutable snapshot; no changes were fabricated.",
            )
            self.store.upsert_observations(observations)
            return {"bootstrap": True, "snapshot_id": manifest["id"], "path": str(path), "validation": report.to_public()}

    # ------------------------------------------------------------------ check
    def check(self, *, sources: Sequence[str] | None = None, due_only: bool = False) -> dict[str, Any]:
        requested = list(sources or ALL_SOURCE_IDS)
        unknown = [source for source in requested if source not in SOURCES]
        if unknown:
            raise PipelineError("unknown source(s): " + ", ".join(unknown))
        with PipelineLock(self.settings.lock_path):
            recover_publication(self.store, self.settings)
            results = self._check_locked(requested, due_only=due_only)
        return {
            "checked_at": _now(),
            "results": results,
            "update_available": any(bool(row.get("update_available")) for row in results),
            "request_usage": self.store.request_usage(datetime.now(timezone.utc).strftime("%Y-%m-%d")),
        }

    # ------------------------------------------------------------------ sync
    def sync(
        self,
        *,
        sources: Sequence[str] | None = None,
        force: bool = False,
        allow_record_drop: bool = False,
        allow_degraded: bool = False,
        dry_run: bool = False,
        actor: str = "pipeline",
        assume_checked: bool = False,
    ) -> dict[str, Any]:
        requested = list(sources or ALL_SOURCE_IDS)
        unknown = [source for source in requested if source not in SOURCES]
        if unknown:
            raise PipelineError("unknown source(s): " + ", ".join(unknown))
        with PipelineLock(self.settings.lock_path):
            recover_publication(self.store, self.settings)
            if not assume_checked:
                self._check_locked(requested, due_only=False)
            return self._sync_locked(
                requested, force=force, allow_record_drop=allow_record_drop,
                allow_degraded=allow_degraded, dry_run=dry_run, actor=actor,
            )

    def run(self, *, force: bool = False, allow_record_drop: bool = False,
            allow_degraded: bool = False, actor: str = "pipeline") -> dict[str, Any]:
        """Run due checks, then reconcile each healthy source independently.

        A failed/degraded source is recorded and omitted from this attempt. It must not
        prevent another source with a real update from being published. The resulting
        snapshot is explicitly partial and still goes through the normal validation gate.
        """
        with PipelineLock(self.settings.lock_path):
            recover_publication(self.store, self.settings)
            checks = self._check_locked(ALL_SOURCE_IDS, due_only=True)
            failed: dict[str, dict[str, Any]] = {}
            healthy_updates: list[str] = []
            healthy_other: list[str] = []
            for row in checks:
                source_id = str(row.get("source_id") or "")
                status = str(row.get("status") or "")
                if status in (CheckStatus.CHECK_FAILED.value, CheckStatus.SOURCE_DEGRADED.value):
                    failed[source_id] = row
                elif bool(row.get("update_available")):
                    healthy_updates.append(source_id)
                else:
                    healthy_other.append(source_id)

            if force:
                # Explicit --force reconciles healthy sources even when the detector says
                # no change; failed/degraded sources are still excluded.
                forced_healthy = [
                    str(row.get("source_id") or "") for row in checks
                    if str(row.get("status") or "") not in (
                        CheckStatus.CHECK_FAILED.value, CheckStatus.SOURCE_DEGRADED.value
                    )
                ]
                product_updates = [sid for sid in forced_healthy if sid in PRODUCT_SOURCE_IDS]
                support_updates = [sid for sid in forced_healthy if sid not in PRODUCT_SOURCE_IDS]
            else:
                product_updates = [
                    source_id for source_id in healthy_updates if source_id in PRODUCT_SOURCE_IDS
                ]
                support_updates = [
                    source_id for source_id in healthy_updates if source_id not in PRODUCT_SOURCE_IDS
                ]
            room = max(0, self.settings.max_product_sources_per_run)
            selected_product = product_updates[:room]
            # Keep the rest pending for the next hourly run; they are not failures.
            deferred_updates = product_updates[room:]
            full_due = []
            if len(selected_product) < room:
                full_due = self._full_reconciliation_due(
                    exclude=set(failed) | set(healthy_updates)
                )
                full_due = full_due[: room - len(selected_product)]
            full_deferred: str | None = None
            if full_due:
                budget_ok, full_deferred = self._full_reconciliation_budget_ok(full_due)
                if not budget_ok:
                    self.store.record_incident("full_reconciliation_deferred", {
                        "sources": full_due, "reason": full_deferred,
                    })
                    full_due = []
            attempt = selected_product + support_updates + full_due
            if not attempt:
                if failed and healthy_other:
                    status = RunStatus.PARTIAL.value
                elif failed:
                    status = RunStatus.BLOCKED.value
                elif full_deferred or deferred_updates:
                    status = RunStatus.PARTIAL.value
                else:
                    status = RunStatus.NO_CHANGE.value
                return {
                    "status": status,
                    "checks": checks,
                    "sync": None,
                    "problems": list(failed.values()),
                    "failed_sources": sorted(failed),
                    "full_reconciliation_deferred": full_deferred,
                    "deferred_update_sources": sorted(deferred_updates),
                    "message": (
                        full_deferred or
                        "no healthy source has an available update"
                    ),
                }

            healthy_other = [source_id for source_id in healthy_other if source_id not in full_due]
            sync = self._sync_locked(
                attempt,
                force=force,
                allow_record_drop=allow_record_drop,
                allow_degraded=True,
                dry_run=False,
                actor=actor,
                isolate_sources=True,
                failed_sources=failed,
                not_attempted=healthy_other,
                include_sources=full_due,
                full_sources=full_due,
                deferred_sources=deferred_updates,
            )
            sync_status = str(sync.get("status") or "")
            all_failed = dict(failed)
            for source_id in sync.get("failed_sources") or []:
                all_failed.setdefault(source_id, {
                    "source_id": source_id, "status": "CHECK_FAILED",
                    "message": "collection or source state failed during the sync attempt",
                })
            if (all_failed or deferred_updates) and sync_status == RunStatus.SUCCEEDED.value:
                overall = RunStatus.PARTIAL.value
            elif all_failed and sync_status in (RunStatus.BLOCKED.value, RunStatus.FAILED.value):
                overall = RunStatus.BLOCKED.value
            else:
                overall = sync_status
            return {
                "status": overall,
                "checks": checks,
                "sync": sync,
                "problems": list(all_failed.values()),
                "failed_sources": sorted(all_failed),
                "full_reconciliation_sources": sorted(full_due),
                "full_reconciliation_deferred": full_deferred,
                "deferred_update_sources": sorted(deferred_updates),
            }

    def _sync_locked(
        self,
        requested: Sequence[str],
        *,
        force: bool,
        allow_record_drop: bool,
        allow_degraded: bool,
        dry_run: bool,
        actor: str,
        isolate_sources: bool = False,
        failed_sources: dict[str, dict[str, Any]] | None = None,
        not_attempted: Sequence[str] = (),
        include_sources: Sequence[str] = (),
        full_sources: Sequence[str] = (),
        deferred_sources: Sequence[str] = (),
    ) -> dict[str, Any]:
        active = active_snapshot(self.settings)
        if active is None:
            raise PipelineError("no active snapshot; run bootstrap first")
        active_path, active_manifest, _pointer = active
        if active_manifest.get("schema") != "medradar.snapshot.v2":
            raise PipelineError("active snapshot is a legacy snapshot; run bootstrap before syncing")
        failed_sources = dict(failed_sources or {})
        targets, problems = self._targets(
            requested, force=force, allow_degraded=allow_degraded,
            ignore_failures=isolate_sources, include_sources=include_sources,
        )
        if not targets:
            return {
                "status": RunStatus.NO_CHANGE.value,
                "message": "no requested source has an available update",
                "problems": problems,
                "active_snapshot_id": active_manifest.get("id"),
            }
        free = shutil.disk_usage(self.settings.root).free
        if free < self.settings.min_free_bytes:
            raise PipelineError(
                "free disk space " + str(free) + " is below the configured minimum " + str(self.settings.min_free_bytes)
            )
        run_id = self.store.begin_run(targets, str(active_manifest.get("id") or ""))
        collection_started = _now()
        candidate_path: Path | None = None
        try:
            organizations = self.registry.get("organizations") or []
            attempted_product = [source_id for source_id in targets if not SOURCES[source_id].is_support_source]
            collector = Collector(self.client)
            collection = AllCollection()
            successful_product: list[str] = []
            for source_id in attempted_product:
                try:
                    source_collection = collector.collect_source(source_id, organizations)
                except (CollectionError, OpenFDAError) as error:
                    if not isolate_sources:
                        raise
                    record = {
                        "source_id": source_id,
                        "status": "CHECK_FAILED",
                        "message": str(error),
                        "error": str(error),
                    }
                    failed_sources[source_id] = record
                    collection.errors.append({"source_id": source_id, "message": str(error)})
                    try:
                        self.store.mark_source_attempt_failed(source_id, str(error), _now())
                    except Exception as state_error:
                        collection.errors.append({
                            "source_id": source_id,
                            "message": "could not persist source failure: " + str(state_error),
                        })
                    self.store.record_incident("source_collection_failed", {
                        "run_id": run_id, "source_id": source_id, "error": str(error),
                    })
                    continue
                successful_product.append(source_id)
                collection.source_audits[source_id] = source_collection.audits
                collection.requests += source_collection.requests
                collection.response_bytes += source_collection.response_bytes
                collection.requests_by_source[source_id] = source_collection.requests
                collection.bytes_by_source[source_id] = source_collection.response_bytes
                collection.errors.extend(source_collection.errors)
                collection.events.update(source_collection.events)

            classification_target = "openfda_classification" in targets
            classification_audit: dict[str, Any] | None = None
            classification_success = False
            if classification_target or successful_product:
                # The classification dictionary is small (7k rows); refresh it whenever a
                # product source is reconciled. Its official version is recorded separately.
                try:
                    classifications, classification_audit = collector.collect_classifications()
                    classification_success = True
                except (CollectionError, OpenFDAError) as error:
                    if not isolate_sources:
                        raise
                    failed_sources["openfda_classification"] = {
                        "source_id": "openfda_classification",
                        "status": "CHECK_FAILED",
                        "message": str(error),
                        "error": str(error),
                    }
                    collection.errors.append({"source_id": "openfda_classification", "message": str(error)})
                    try:
                        self.store.mark_source_attempt_failed("openfda_classification", str(error), _now())
                    except Exception as state_error:
                        collection.errors.append({
                            "source_id": "openfda_classification",
                            "message": "could not persist source failure: " + str(state_error),
                        })
                    classifications = self._previous_classifications(active_path)
            else:
                classifications = self._previous_classifications(active_path)

            if not successful_product and not classification_success:
                message = "all requested source collections failed; active snapshot was left unchanged"
                self.store.finish_run(
                    run_id, RunStatus.BLOCKED.value,
                    error=message,
                    metrics={"failed_sources": sorted(failed_sources)},
                )
                return {
                    "status": RunStatus.BLOCKED.value,
                    "run_id": run_id,
                    "active_snapshot_id": active_manifest.get("id"),
                    "failed_sources": sorted(failed_sources),
                    "message": message,
                }

            previous_events = self._previous_events(active_path)
            candidate_events = dict(previous_events)
            for source_id in successful_product:
                for event_id in [key for key, event in candidate_events.items() if event.get("source_id") == source_id]:
                    candidate_events.pop(event_id, None)
            candidate_events.update(collection.events)

            checked_at = _now()
            successful_sources = successful_product + (
                ["openfda_classification"] if classification_success else []
            )
            sources_for_change = list(successful_product)
            source_versions = self._source_versions(
                active_manifest,
                successful_sources=successful_sources,
                failed_sources=failed_sources,
                checked_at=checked_at,
                not_attempted=not_attempted,
                full_sources=full_sources,
            )
            if classification_success and classification_audit:
                classification_version = source_versions.get("openfda_classification") or {}
                classification_version.update({
                    "official_last_updated": classification_audit.get("official_last_updated")
                    or classification_version.get("official_last_updated"),
                    "official_total": classification_audit.get("official_total")
                    if classification_audit.get("official_total") is not None
                    else classification_version.get("official_total"),
                })
                source_versions["openfda_classification"] = classification_version
            observations = self.store.observations_for_sources(sources_for_change)
            previous_scope_hash = str((active_manifest.get("scope") or {}).get("scope_hash") or "")
            scope_changed = bool(previous_scope_hash and previous_scope_hash != self.scope["scope_hash"])

            missing: list[dict[str, Any]] = []
            for source_id in sources_for_change:
                previous_ids = {key for key, event in previous_events.items() if event.get("source_id") == source_id}
                candidate_ids = {key for key, event in candidate_events.items() if event.get("source_id") == source_id}
                missing.extend(previous_events[key] for key in sorted(previous_ids - candidate_ids))

            recheck_found: dict[str, dict[str, Any]] = {}
            unresolved_reason: str | None = None
            if missing:
                if scope_changed:
                    unresolved_reason = "query_scope_changed"
                elif len(missing) > self.settings.missing_recheck_cap:
                    unresolved_reason = "exact_recheck_cap_exceeded"
                else:
                    by_source: dict[str, list[dict[str, Any]]] = {}
                    for event in missing:
                        by_source.setdefault(str(event.get("source_id") or ""), []).append(event)
                    recheck_errors: list[dict[str, Any]] = []
                    for source_id, rows in by_source.items():
                        found, errors = collector.recheck_missing(
                            source_id, rows, self.settings.missing_recheck_cap
                        )
                        recheck_found.update(found)
                        recheck_errors.extend(errors)
                    if recheck_errors:
                        unresolved_reason = "exact_recheck_failed"

            first_reconciliation = any(
                not ((active_manifest.get("sources") or {}).get(source_id) or {}).get("official_last_updated")
                for source_id in sources_for_change
            )
            provisional_id = "fda-snapshot-pending"
            change_set = build_change_set(
                previous_events=previous_events,
                candidate_events=candidate_events,
                changed_sources=sources_for_change,
                previous_snapshot_id=str(active_manifest.get("id") or "") or None,
                candidate_snapshot_id=provisional_id,
                detected_at=checked_at,
                source_versions=source_versions,
                observations=observations,
                previous_collected_at=str(active_manifest.get("collected_at") or "") or None,
                scope_changed=scope_changed,
                recheck_found=recheck_found,
                removal_confirmations=self.settings.removal_confirmations,
                unresolved_reason=unresolved_reason,
                rebaseline=first_reconciliation,
            )
            summary = dict(change_set.summary)
            source_outcomes = {
                source_id: {
                    "sync_status": (value or {}).get("sync_status"),
                    "reconciliation_mode": (value or {}).get("reconciliation_mode"),
                    "last_check_status": (value or {}).get("last_check_status"),
                    "last_check_message": (value or {}).get("last_check_message"),
                    "last_sync_error": (value or {}).get("last_sync_error"),
                    "official_last_updated": (value or {}).get("official_last_updated"),
                }
                for source_id, value in source_versions.items()
            }
            summary.update({
                "first_reconciliation": first_reconciliation,
                "scope_changed": scope_changed,
                "missing_retained": summary.get("missing_on_recheck", 0) + summary.get("unresolved", 0),
                "changed_sources": sorted(set(sources_for_change)),
                "successful_sources": sorted(set(successful_sources)),
                "failed_sources": sorted(failed_sources),
                "deferred_sources": sorted(set(deferred_sources)),
                "full_reconciliation_sources": sorted(set(full_sources)),
                "partial": bool(failed_sources or deferred_sources),
            })

            collection_audit = self._audit_for_snapshot(
                active_manifest,
                sources_for_change,
                collection,
                classification_audit=classification_audit,
                requests=collection.requests if collection is not None else 0,
                response_bytes=collection.response_bytes if collection is not None else 0,
            )

            candidate_path, candidate_manifest = build_snapshot(
                self.settings,
                events=change_set.events,
                classifications=classifications,
                source_versions=source_versions,
                collection_audit=collection_audit,
                change_summary=summary,
                scope=self.scope,
                source_outcomes=source_outcomes,
                previous_snapshot_id=str(active_manifest.get("id") or "") or None,
                collection_started_at=collection_started,
                now=_now(),
            )
            self._stamp_changes(change_set.changes, str(candidate_manifest["id"]))
            self._assign_organizations(change_set.changes, self.settings.review_db)

            # Release the collector/candidate representations before loading the product
            # dataset for validation. Peak memory then comes from one large model, not two.
            change_set.events = {}
            candidate_events = {}
            previous_events = {}
            collection = None
            gc.collect()

            report = validate_snapshot(
                candidate_path,
                settings=self.settings,
                previous_dir=active_path,
                allow_record_drop=allow_record_drop,
                validate_product=True,
            )
            validation = report.to_public()
            counts = {
                "records": (candidate_manifest.get("counts") or {}).get("records"),
                "changes": summary,
                "requests": collection_audit.get("request_count"),
                "response_bytes": collection_audit.get("response_bytes"),
            }
            if not report.ok:
                self.store.record_incident("candidate_validation_failed", {
                    "run_id": run_id, "snapshot_id": candidate_manifest["id"],
                    "errors": validation["errors"][:20],
                })
                self.store.finish_run(run_id, RunStatus.BLOCKED.value, candidate_after=str(candidate_manifest["id"]),
                                      counts=counts, error="candidate validation failed", metrics=validation)
                return {
                    "status": RunStatus.BLOCKED.value,
                    "run_id": run_id,
                    "candidate_snapshot_id": candidate_manifest["id"],
                    "candidate_path": str(candidate_path),
                    "validation": validation,
                    "active_snapshot_id": active_manifest.get("id"),
                    "failed_sources": sorted(failed_sources),
                    "partial": bool(failed_sources),
                }
            if dry_run:
                self.store.finish_run(run_id, RunStatus.SUCCEEDED.value, candidate_after=str(candidate_manifest["id"]),
                                      counts=counts, metrics={"dry_run": True, "validation": validation})
                return {
                    "status": "DRY_RUN_VALIDATED",
                    "run_id": run_id,
                    "candidate_snapshot_id": candidate_manifest["id"],
                    "candidate_path": str(candidate_path),
                    "validation": validation,
                    "active_snapshot_id": active_manifest.get("id"),
                    "failed_sources": sorted(failed_sources),
                    "partial": bool(failed_sources),
                }

            manifest_sha = hashlib.sha256((candidate_path / "snapshot.json").read_bytes()).hexdigest()
            self.store.register_snapshot(
                snapshot_id=str(candidate_manifest["id"]), path=str(candidate_path),
                content_hash=(candidate_manifest.get("lineage") or {}).get("content_hash"),
                created_at=str(candidate_manifest.get("collected_at") or _now()),
                status="staged", parent_snapshot_id=str(active_manifest.get("id") or "") or None,
                source_versions=source_versions, counts=candidate_manifest.get("counts") or {},
                manifest_sha256=manifest_sha, validation=validation,
            )
            inserted = self.store.add_changes(run_id, str(candidate_manifest["id"]), change_set.changes)
            post_publication_warning: str | None = None
            try:
                commit_publication(
                    self.store, self.settings, snapshot_dir=candidate_path, manifest=candidate_manifest,
                    run_id=run_id, previous_snapshot_id=str(active_manifest.get("id") or "") or None,
                    action="sync", actor=actor,
                    note=(
                        "sources=" + ",".join(sorted(successful_sources))
                        + "; failed=" + ",".join(sorted(failed_sources))
                        + "; inserted_changes=" + str(inserted)
                    ),
                )
            except Exception as commit_error:
                # If the pointer was written but the DB commit failed, recovery will finish
                # the DB side now. The snapshot must not be discarded: users already see it.
                active_after = active_snapshot(self.settings)
                if active_after is None or str(active_after[1].get("id")) != str(candidate_manifest["id"]):
                    raise
                recover_publication(self.store, self.settings)
                post_publication_warning = "publication DB commit recovered after: " + str(commit_error)

            try:
                self.store.upsert_observations(change_set.observations)
            except Exception as error:
                post_publication_warning = (post_publication_warning or "") + " observation write failed: " + str(error)
                self.store.record_incident("post_publication_observation_failure", {
                    "snapshot_id": candidate_manifest["id"], "error": str(error),
                })
            for source_id in successful_sources:
                try:
                    version = source_versions.get(source_id) or {}
                    self.store.mark_source_synced(
                        source_id, str(candidate_manifest["id"]), _now(),
                        version.get("official_last_updated"), version.get("official_total"),
                    )
                    if source_id in PRODUCT_SOURCE_IDS:
                        # A successful scoped reconciliation is a full content sweep, whether
                        # it was version-triggered or due on the rolling schedule.
                        self.store.mark_source_full_reconciled(
                            source_id, str(candidate_manifest["id"]), _now()
                        )
                except Exception as error:
                    post_publication_warning = (post_publication_warning or "") + " source state write failed: " + str(error)
            final_status = RunStatus.PARTIAL.value if failed_sources else RunStatus.SUCCEEDED.value
            try:
                self.store.finish_run(
                    run_id, final_status, candidate_after=str(candidate_manifest["id"]),
                    counts=counts, metrics={
                        "validation": validation, "inserted_changes": inserted,
                        "post_publication_warning": post_publication_warning,
                        "failed_sources": sorted(failed_sources),
                    },
                )
            except Exception:
                pass
            return {
                "status": final_status,
                "run_id": run_id,
                "previous_snapshot_id": active_manifest.get("id"),
                "active_snapshot_id": candidate_manifest["id"],
                "snapshot_path": str(candidate_path),
                "counts": counts,
                "validation": validation,
                "added": summary.get("added", 0),
                "updated": summary.get("updated", 0),
                "removed_confirmed": summary.get("removed_confirmed", 0),
                "missing_on_recheck": summary.get("missing_on_recheck", 0),
                "unresolved": summary.get("unresolved", 0),
                "failed_sources": sorted(failed_sources),
                "successful_sources": sorted(successful_sources),
                "full_reconciliation_sources": sorted(set(full_sources)),
                "partial": bool(failed_sources),
                "post_publication_warning": post_publication_warning,
            }
        except Exception as error:
            try:
                self.store.discard_staged_changes(run_id)
            except Exception:
                pass
            try:
                self.store.finish_run(run_id, RunStatus.FAILED.value, error=str(error))
            except Exception:
                pass
            try:
                self.store.record_incident("sync_failed", {
                    "run_id": run_id, "targets": targets, "error": str(error),
                    "candidate": str(candidate_path) if candidate_path else None,
                })
            except Exception:
                pass
            raise

    # ------------------------------------------------------------------ status
    def status(self) -> dict[str, Any]:
        active = active_snapshot(self.settings)
        payload: dict[str, Any] = {
            "pipeline_version": PIPELINE_VERSION,
            "root": str(self.settings.root),
            "active": None,
            "sources": self.store.list_sources(),
            "recent_runs": self.store.recent_runs(10),
            "incidents": self.store.incidents(10),
            "request_usage_today": self.store.request_usage(datetime.now(timezone.utc).strftime("%Y-%m-%d")),
        }
        if active:
            path, manifest, pointer = active
            payload["active"] = {
                "snapshot_id": manifest.get("id"),
                "path": str(path),
                "pointer": pointer,
                "counts": manifest.get("counts"),
                "change_summary": manifest.get("change_summary"),
                "source_versions": manifest.get("sources"),
                "published_at": pointer.get("published_at"),
            }
            payload["change_counts"] = self.store.change_counts(str(manifest.get("id")))
        return payload

    def rollback(self, snapshot_id: str, *, actor: str = "operator") -> dict[str, Any]:
        with PipelineLock(self.settings.lock_path):
            return publisher_rollback(self.store, self.settings, snapshot_id, actor=actor)

    def prune(self, keep: int | None = None) -> dict[str, Any]:
        keep = keep or self.settings.retention_snapshots
        active = active_snapshot(self.settings)
        active_id = str(active[1].get("id")) if active else None
        snapshots = sorted(
            [path for path in self.settings.snapshots_dir.iterdir() if path.is_dir()],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        removed = []
        for path in snapshots[keep:]:
            if path.name == active_id:
                continue
            shutil.rmtree(path, ignore_errors=True)
            removed.append(path.name)
        return {"kept": [path.name for path in snapshots[:keep]], "removed": removed}
