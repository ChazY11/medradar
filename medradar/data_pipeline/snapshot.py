"""Immutable snapshot construction.

The builder writes only into a private staging directory. It computes every file hash and
a deterministic content hash, then renames the complete directory into ``snapshots/``.
A final snapshot directory is never reopened for writing; publication is a separate,
atomic pointer switch in ``publisher.py``.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .config import PIPELINE_VERSION, Settings
from .model import SOURCES
from .normalize import (
    build_applicants,
    compact_event,
    snapshot_hash,
)

SNAPSHOT_SCHEMA = "medradar.snapshot.v2"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_jsonl_gz(path: Path, rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = ("\n".join(_canonical(row) for row in rows) + ("\n" if rows else "")).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    with path.open("wb") as handle:
        with gzip.GzipFile(filename="", mode="wb", fileobj=handle, mtime=0) as gz:
            gz.write(raw)
    return {"sha256": digest, "bytes": path.stat().st_size, "records": len(rows), "encoding": "gzip", "uncompressed_bytes": len(raw)}


def prepare_events(events: Mapping[str, dict[str, Any]], now: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
    quality = {
        "records": len(events),
        "implausible_event_date": 0,
        "missing_first_observed": 0,
        "missing_content_hash": 0,
    }
    prepared: list[dict[str, Any]] = []
    for event_id in sorted(events):
        event = dict(events[event_id])
        if not event.get("first_observed_at"):
            event["first_observed_at"] = now
            quality["missing_first_observed"] += 1
        if not event.get("last_synced_at"):
            event["last_synced_at"] = now
        if not event.get("content_hash"):
            quality["missing_content_hash"] += 1
        compacted, flags = compact_event(event)
        if flags:
            quality["implausible_event_date"] += 1
        compacted["snapshot_hash"] = snapshot_hash(compacted)
        prepared.append(compacted)
    return prepared, quality


def build_snapshot(
    settings: Settings,
    *,
    events: Mapping[str, dict[str, Any]],
    classifications: Sequence[dict[str, Any]],
    source_versions: Mapping[str, dict[str, Any]],
    collection_audit: Mapping[str, Any],
    change_summary: Mapping[str, int],
    scope: Mapping[str, Any],
    source_outcomes: Mapping[str, Any] | None = None,
    previous_snapshot_id: str | None,
    collection_started_at: str,
    now: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    settings.ensure()
    moment = now or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    prepared, quality = prepare_events(events, moment)
    applicants = build_applicants([dict(event) for event in events.values()])
    ordered_classifications = sorted(classifications, key=lambda item: str(item.get("product_code") or ""))

    staging = settings.staging_dir / ("pending-" + uuid.uuid4().hex)
    staging.mkdir(parents=True)
    try:
        files = {
            "events.jsonl.gz": write_jsonl_gz(staging / "events.jsonl.gz", prepared),
            "applicants.jsonl.gz": write_jsonl_gz(staging / "applicants.jsonl.gz", applicants),
            "classifications.jsonl.gz": write_jsonl_gz(staging / "classifications.jsonl.gz", ordered_classifications),
        }
        by_source: dict[str, int] = {}
        by_type: dict[str, int] = {}
        dates: list[str] = []
        for event in prepared:
            source_id = str(event.get("source_id") or "")
            by_source[source_id] = by_source.get(source_id, 0) + 1
            event_type = str(event.get("event_type") or "")
            by_type[event_type] = by_type.get(event_type, 0) + 1
            if event.get("event_date"):
                dates.append(str(event["event_date"]))
        counts = {
            "records": len(prepared),
            "applicant_strings": len(applicants),
            "product_codes": len(ordered_classifications),
            "by_source": by_source,
            "by_event_type": by_type,
        }
        coverage = {
            "min_event_date": min(dates) if dates else None,
            "max_event_date": max(dates) if dates else None,
            "records_with_event_date": len(dates),
            "records_without_event_date": len(prepared) - len(dates),
        }
        source_payload: dict[str, Any] = {}
        for source_id in sorted(source_versions):
            item = dict(source_versions[source_id] or {})
            item.setdefault("source_id", source_id)
            source_payload[source_id] = item
        content_basis = {
            "files": {name: {"sha256": meta["sha256"], "records": meta["records"]} for name, meta in sorted(files.items())},
            "counts": counts,
            "source_versions": {
                key: {
                    "official_last_updated": (value or {}).get("official_last_updated"),
                    "official_total": (value or {}).get("official_total"),
                }
                for key, value in sorted(source_payload.items())
            },
            "scope_hash": scope.get("scope_hash"),
            "schema": SNAPSHOT_SCHEMA,
        }
        content_hash = hashlib.sha256(_canonical(content_basis).encode("utf-8")).hexdigest()
        stamp = datetime.fromisoformat(moment.replace("Z", "+00:00")).strftime("%Y%m%dT%H%M%SZ")
        snapshot_id = "fda-snapshot-" + stamp + "-" + content_hash[:12]

        organizations: list[dict[str, Any]] = []
        audit_by_org: dict[str, dict[str, Any]] = {}
        for source_id, audits in (collection_audit.get("sources") or {}).items():
            for audit in audits:
                org_key = str(audit.get("org_key") or "")
                entry = audit_by_org.setdefault(org_key, {
                    "key": org_key,
                    "display_name": scope.get("organizations", {}).get(org_key),
                    "queries": [],
                    "records": 0,
                })
                entry["queries"].append({
                    "source_id": source_id,
                    "query": audit.get("query"),
                    "pages": audit.get("pages"),
                    "records": audit.get("records"),
                    "unique_records": audit.get("unique_records"),
                    "reported_total": audit.get("reported_total"),
                    "complete": audit.get("complete"),
                    "partitions": audit.get("partitions") or [],
                    "urls": audit.get("urls") or [],
                    "errors": audit.get("errors") or [],
                })
                entry["records"] += int(audit.get("unique_records") or 0)
        organizations = [audit_by_org[key] for key in sorted(audit_by_org)]

        openfda_versions = {
            key: (value or {}).get("official_last_updated")
            for key, value in source_payload.items()
            if (value or {}).get("official_last_updated")
        }
        openfda_last_updated = max(openfda_versions.values()) if openfda_versions else None
        manifest = {
            "schema": SNAPSHOT_SCHEMA,
            "id": snapshot_id,
            "collected_at": moment,
            "collection_started_at": collection_started_at,
            "collector": {
                "name": PIPELINE_VERSION,
                "api_base": settings.api_base,
                "user_agent": settings.user_agent,
            },
            "openfda": {
                "last_updated": openfda_last_updated,
                "per_source": openfda_versions,
                "note": "meta.last_updated is an endpoint-level version, not a per-record revision time.",
            },
            "sources": source_payload,
            "source_outcomes": dict(source_outcomes or {}),
            "scope": dict(scope),
            "files": files,
            "counts": counts,
            "coverage": coverage,
            "data_quality": quality,
            "request_count": int(collection_audit.get("request_count") or 0),
            "response_bytes": int(collection_audit.get("response_bytes") or 0),
            "organization_count": len(scope.get("organization_keys") or []),
            "collection_audit": dict(collection_audit),
            "organizations": organizations,
            "errors": list(collection_audit.get("errors") or []),
            "change_summary": dict(change_summary),
            "lineage": {
                "previous_snapshot_id": previous_snapshot_id,
                "content_hash": content_hash,
                "builder_version": PIPELINE_VERSION,
            },
            "time_semantics": [
                {"field": "event_date", "meaning": "The regulatory event date stated by FDA; never replaced by discovery time."},
                {"field": "published_at", "meaning": "A source publication date only where the source states it (recall posting date)."},
                {"field": "first_observed_at", "meaning": "When MedRadar first observed this official identity; preserved across snapshots."},
                {"field": "last_synced_at", "meaning": "Most recent successful reconciliation of this record; not a regulatory event date."},
                {"field": "source_updated_at", "meaning": "The endpoint-level official version used for this record; not a per-record revision time."},
            ],
            "notes": [
                "Records are scoped to the reviewed organization roster. Absence from this snapshot is not evidence about the global FDA universe.",
                "Request and response counts describe the collection work recorded in collection_audit; source query evidence is retained per organization.",
                "The source update version can advance without a record-level change; such a run still records a new snapshot and zero ADDED/UPDATED rows.",
                "A record missing from one complete sweep is retained as MISSING_ON_RECHECK and requires repeat evidence plus an exact-ID recheck before removal.",
            ],
        }
        manifest_bytes = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
        (staging / "snapshot.json").write_bytes(manifest_bytes)
        _fsync_file(staging / "snapshot.json")
        _fsync_dir(staging)

        destination = settings.snapshots_dir / snapshot_id
        if destination.exists():
            if not (destination / "snapshot.json").is_file():
                raise RuntimeError("snapshot destination exists without a manifest: " + str(destination))
            existing = json.loads((destination / "snapshot.json").read_text(encoding="utf-8"))
            if (existing.get("lineage") or {}).get("content_hash") != content_hash:
                raise RuntimeError("snapshot id collision with different content: " + snapshot_id)
            shutil.rmtree(staging)
            return destination, existing
        staging.rename(destination)
        _fsync_dir(settings.snapshots_dir)
        return destination, manifest
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise


def _fsync_file(path: Path) -> None:
    try:
        with path.open("rb") as handle:
            os.fsync(handle.fileno())
    except OSError:
        pass


def _fsync_dir(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        descriptor = os.open(str(path), os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        pass
