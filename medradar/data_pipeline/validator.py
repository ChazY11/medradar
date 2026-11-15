"""Candidate snapshot validation.

A snapshot is not publishable because it exists. It is publishable only when the manifest,
every file hash, every record identity, the coverage evidence, the change summary and the
product/device read path all agree. A sudden record drop blocks publication; it is never
silently accepted as a correction.
"""
from __future__ import annotations

import gc
import gzip
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from .config import Settings
from .model import SOURCES, parse_iso
from .normalize import compact_event, snapshot_hash

REQUIRED_FILES = ("events.jsonl.gz", "applicants.jsonl.gz", "classifications.jsonl.gz")
REQUIRED_MANIFEST = (
    "schema", "id", "collected_at", "collection_started_at", "sources", "files",
    "counts", "coverage", "collection_audit", "change_summary", "lineage", "scope",
)
ALLOWED_TYPES = {
    "openfda_510k": {"510k"},
    "openfda_pma": {"pma", "pma_supplement"},
    "openfda_recall": {"recall"},
}


@dataclass
class ValidationIssue:
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_public(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


@dataclass
class ValidationReport:
    ok: bool
    checks: dict[str, Any]
    errors: list[ValidationIssue]
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_public(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "checks": self.checks,
            "errors": [error.to_public() for error in self.errors],
            "metrics": self.metrics,
        }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_gzip_lines(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _file_content_hash(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with gzip.open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _hash_file_state(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    return _sha256_file(path)


def validate_snapshot(
    snapshot_dir: Path | str,
    *,
    settings: Settings,
    previous_dir: Path | str | None = None,
    allow_record_drop: bool = False,
    validate_product: bool = True,
) -> ValidationReport:
    base = Path(snapshot_dir)
    checks: dict[str, Any] = {}
    errors: list[ValidationIssue] = []
    metrics: dict[str, Any] = {}

    def fail(code: str, message: str, **details: Any) -> None:
        errors.append(ValidationIssue(code, message, details))

    manifest_path = base / "snapshot.json"
    if not manifest_path.is_file():
        return ValidationReport(False, {"manifest_present": False}, [ValidationIssue("manifest_missing", "snapshot.json is missing")], {})
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return ValidationReport(False, {"manifest_parse": False}, [ValidationIssue("manifest_invalid", str(error))], {})
    checks["manifest_present"] = True
    missing = [key for key in REQUIRED_MANIFEST if key not in manifest]
    if missing:
        fail("manifest_required_keys", "manifest is missing required keys", missing=missing)
    if manifest.get("schema") != "medradar.snapshot.v2":
        fail("manifest_schema", "unexpected snapshot schema", schema=manifest.get("schema"))
    snapshot_id = str(manifest.get("id") or "")
    if not snapshot_id.startswith("fda-snapshot-"):
        fail("snapshot_id_format", "snapshot id does not use the fda-snapshot prefix", id=snapshot_id)
    for field_name in ("collected_at", "collection_started_at"):
        if parse_iso(str(manifest.get(field_name) or "")) is None:
            fail("manifest_time", field_name + " is not an ISO-8601 timestamp", value=manifest.get(field_name))

    files = manifest.get("files") or {}
    event_rows: list[dict[str, Any]] = []
    for name in REQUIRED_FILES:
        path = base / name
        if not path.is_file():
            fail("file_missing", "required snapshot file is missing", file=name)
            continue
        stored = files.get(name) or {}
        try:
            content_digest, content_size = _file_content_hash(path)
        except (OSError, EOFError, gzip.BadGzipFile) as error:
            fail("file_unreadable", "snapshot file cannot be read", file=name, error=str(error))
            continue
        if stored.get("sha256") != content_digest:
            fail("file_hash", "snapshot file hash does not match the manifest", file=name,
                 expected=stored.get("sha256"), actual=content_digest)
        if int(stored.get("uncompressed_bytes") or 0) and int(stored["uncompressed_bytes"]) != content_size:
            fail("file_size", "snapshot file uncompressed size does not match the manifest", file=name,
                 expected=stored.get("uncompressed_bytes"), actual=content_size)
        if int(stored.get("bytes") or 0) and int(stored["bytes"]) != path.stat().st_size:
            fail("compressed_size", "snapshot file compressed size does not match the manifest", file=name,
                 expected=stored.get("bytes"), actual=path.stat().st_size)
        if name == "events.jsonl.gz":
            try:
                event_rows = _read_gzip_lines(path)
            except (OSError, ValueError) as error:
                fail("events_unreadable", "events file cannot be parsed", error=str(error))
        if int(stored.get("records") or 0) != len(_read_count(path)):
            fail("file_record_count", "file record count does not match the manifest", file=name,
                 expected=stored.get("records"), actual=len(_read_count(path)))

    checks["files_parsed"] = bool(event_rows)
    if not event_rows:
        fail("events_empty", "snapshot has no records")
    if len(event_rows) != int((manifest.get("counts") or {}).get("records") or -1):
        fail("record_count", "event count does not match manifest counts",
             expected=(manifest.get("counts") or {}).get("records"), actual=len(event_rows))

    ids: set[str] = set()
    identities: set[tuple[str, str]] = set()
    by_source: dict[str, int] = {}
    by_type: dict[str, int] = {}
    dates: list[str] = []
    first_seen_min: str | None = None
    first_seen_max: str | None = None
    for index, event in enumerate(event_rows):
        event_id = str(event.get("event_id") or "")
        source_id = str(event.get("source_id") or "")
        official_id = str(event.get("official_id") or "")
        if not event_id or not official_id:
            fail("record_identity", "record is missing event_id or official_id", row=index)
            continue
        if event_id in ids:
            fail("duplicate_event_id", "duplicate event_id", event_id=event_id)
        ids.add(event_id)
        identity = (source_id, official_id)
        if identity in identities:
            fail("duplicate_official_id", "duplicate official identity within a source", source_id=source_id, official_id=official_id)
        identities.add(identity)
        spec = SOURCES.get(source_id)
        if spec is None or spec.is_support_source:
            fail("unknown_source", "record uses an unknown product source", source_id=source_id, event_id=event_id)
            continue
        if event.get("event_type") not in ALLOWED_TYPES.get(source_id, set()):
            fail("event_type", "event type is not valid for its source", source_id=source_id, event_type=event.get("event_type"))
        if not event.get("applicant_name"):
            fail("applicant_missing", "record has no applicant string", event_id=event_id)
        if not event.get("content_hash") or len(str(event["content_hash"])) != 64:
            fail("content_hash", "record has no valid content hash", event_id=event_id)
        expected_snapshot_hash = snapshot_hash(compact_event(event)[0])
        if event.get("snapshot_hash") != expected_snapshot_hash:
            fail("snapshot_hash", "record snapshot hash does not match its content", event_id=event_id)
        first = str(event.get("first_observed_at") or "")
        moment = parse_iso(first)
        if moment is None:
            fail("first_observed", "record has no valid first_observed_at", event_id=event_id)
        else:
            if moment.tzinfo is None:
                fail("first_observed_timezone", "first_observed_at has no timezone", event_id=event_id)
            if moment > datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=1):
                fail("first_observed_future", "first_observed_at is in the future", event_id=event_id)
            first_seen_min = min(filter(None, [first_seen_min, first])) if first_seen_min else first
            first_seen_max = max(filter(None, [first_seen_max, first])) if first_seen_max else first
        event_date = event.get("event_date")
        if event_date:
            try:
                year = int(str(event_date)[:4])
                if not 1900 <= year <= 2100:
                    fail("event_date", "event date year is implausible", event_id=event_id, event_date=event_date)
                dates.append(str(event_date))
            except ValueError:
                fail("event_date_format", "event date is not a date", event_id=event_id, event_date=event_date)
        by_source[source_id] = by_source.get(source_id, 0) + 1
        by_type[str(event.get("event_type"))] = by_type.get(str(event.get("event_type")), 0) + 1

    checks["unique_event_ids"] = len(ids)
    checks["unique_official_identities"] = len(identities)
    checks["first_observed_range"] = {"min": first_seen_min, "max": first_seen_max}
    metrics["by_source"] = by_source
    metrics["by_type"] = by_type
    if by_source != (manifest.get("counts") or {}).get("by_source"):
        fail("source_counts", "manifest by_source counts do not match the records",
             expected=(manifest.get("counts") or {}).get("by_source"), actual=by_source)
    if by_type != (manifest.get("counts") or {}).get("by_event_type"):
        fail("type_counts", "manifest by_event_type counts do not match the records",
             expected=(manifest.get("counts") or {}).get("by_event_type"), actual=by_type)
    coverage = manifest.get("coverage") or {}
    if dates and (coverage.get("min_event_date") != min(dates) or coverage.get("max_event_date") != max(dates)):
        fail("coverage_dates", "manifest coverage dates do not match the records",
             expected=(min(dates), max(dates)),
             actual=(coverage.get("min_event_date"), coverage.get("max_event_date")))

    # Every scoped query must be complete. A partial partition is a failed candidate.
    audit = manifest.get("collection_audit") or {}
    incomplete = []
    for source_id, rows in (audit.get("sources") or {}).items():
        for row in rows:
            if not row.get("complete") or row.get("errors"):
                incomplete.append({"source_id": source_id, "org_key": row.get("org_key"), "errors": row.get("errors")})
    if incomplete:
        fail("collection_incomplete", "one or more source queries were incomplete", queries=incomplete[:20])
    classification_audit = audit.get("classification") or {}
    if classification_audit and not classification_audit.get("complete"):
        fail("classification_incomplete", "classification dictionary collection was incomplete", audit=classification_audit)
    source_versions = manifest.get("sources") or {}
    unknown_versions: list[str] = []
    for source_id in ALLOWED_TYPES:
        if source_id not in source_versions:
            fail("source_version_missing", "manifest has no source version entry", source_id=source_id)
        elif not (source_versions.get(source_id) or {}).get("official_last_updated"):
            # Unknown freshness does not corrupt the records, but it must be visible and the
            # detector will keep asking for a reconciliation. It is not reported as NO_CHANGE.
            unknown_versions.append(source_id)
    checks["unknown_source_versions"] = unknown_versions

    # The record-level checks are complete. Free the raw event list before loading the
    # product dataset; the validator only needs the persisted files from here on.
    record_count = len(event_rows)
    metrics["records"] = record_count
    del event_rows
    gc.collect()

    # Product read path: identity overlay is read-only; device index must build completely.
    review_hash_before = _hash_file_state(settings.review_db)
    if validate_product:
        try:
            from medradar.product.dataset import load_dataset

            dataset = load_dataset(base, review_db=settings.review_db)
            checks["product_dataset"] = {
                "snapshot_id": dataset.snapshot_id,
                "events": len(dataset.events),
                "organizations": len(dataset.registry.organizations),
                "global_records": dataset.global_counts.get("records"),
            }
            if len(dataset.events) != record_count:
                fail("product_event_count", "product loader read a different number of events",
                     expected=record_count, actual=len(dataset.events))
            try:
                device_index = dataset.device_index()
                checks["device_index"] = {
                    "applications": len(device_index.applications),
                    "devices": len(device_index.devices),
                    "families": len(device_index.families),
                    "relations": len(device_index.relations),
                    "stats": device_index.stats,
                }
                if not device_index.applications:
                    fail("device_index_empty", "device index built but contains no applications")
                for application in device_index.applications.values():
                    if application.kind == "pma_supplement" and application.parent_application_id:
                        # A supplement may refer to a parent outside the tracked scope; that is an
                        # explicit candidate gap, not a build failure. The relation is still recorded.
                        if application.parent_application_id not in device_index.applications:
                            metrics.setdefault("pma_supplements_with_untracked_parent", 0)
                            metrics["pma_supplements_with_untracked_parent"] += 1
            except Exception as error:
                fail("device_index_build", "device index could not be built: " + str(error))
        except Exception as error:
            fail("product_load", "product dataset could not be loaded: " + str(error))
    review_hash_after = _hash_file_state(settings.review_db)
    if review_hash_before != review_hash_after:
        fail("review_db_mutated", "validation changed the identity review database")
    checks["review_db_unchanged"] = review_hash_before == review_hash_after

    # Retention comparison and sudden-drop gate.
    if previous_dir is not None:
        previous_path = Path(previous_dir)
        previous_manifest_path = previous_path / "snapshot.json"
        if previous_manifest_path.is_file():
            previous_manifest = json.loads(previous_manifest_path.read_text(encoding="utf-8"))
            previous_count = int((previous_manifest.get("counts") or {}).get("records") or 0)
            metrics["previous_records"] = previous_count
            if previous_count:
                drop = (previous_count - record_count) / float(previous_count)
                metrics["record_drop_ratio"] = round(drop, 6)
                floor = int(settings.max_record_drop_floor)
                if drop > settings.max_record_drop_ratio and (previous_count - record_count) > floor:
                    if not allow_record_drop:
                        fail(
                            "record_drop",
                            "record count fell by " + format(drop * 100.0, ".2f")
                            + "% from the previous snapshot; publication requires explicit review",
                            previous=previous_count, current=record_count,
                        )
                    else:
                        checks["record_drop_override"] = True
            previous_sources = (previous_manifest.get("counts") or {}).get("by_source") or {}
            for source_id, previous_source_count in previous_sources.items():
                current_source_count = by_source.get(source_id, 0)
                if previous_source_count and current_source_count < previous_source_count:
                    source_drop = (previous_source_count - current_source_count) / float(previous_source_count)
                    if source_drop > settings.max_record_drop_ratio:
                        metrics.setdefault("source_drops", {})[source_id] = round(source_drop, 6)
                        if not allow_record_drop:
                            fail(
                                "source_record_drop",
                                "source " + source_id + " record count dropped by "
                                + format(source_drop * 100.0, ".2f") + "%",
                                source_id=source_id, previous=previous_source_count, current=current_source_count,
                            )
        else:
            fail("previous_snapshot", "previous snapshot has no manifest", path=str(previous_path))

    checks["errors"] = len(errors)
    return ValidationReport(ok=not errors, checks=checks, errors=errors, metrics=metrics)


def _read_count(path: Path) -> list[str]:
    if not path.is_file():
        return []
    try:
        if path.suffix == ".gz":
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                return [line for line in handle if line.strip()]
        return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, UnicodeDecodeError):
        return []
