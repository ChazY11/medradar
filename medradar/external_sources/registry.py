"""The global data-source register: one record per candidate source.

Two inputs are merged, and they are deliberately kept apart:

* ``research/data_expansion/registry/sources/<source_id>.json`` — what the
  *documentation* claims (official docs, licence pages, pricing pages), written
  by the source-audit pass.  Every field here is a claim with an ``evidence_url``.
* ``research/data_expansion/probes/<source_id>/PROBE_RESULT.json`` — what a real
  request actually returned, written by the probe pass.

The merged register keeps both, so the report can say "the docs claim an API"
and "the API returned 401 without a key" without either statement overwriting
the other.  ``connection_status`` always comes from the probe when a probe
exists; documentation alone can never produce ``VERIFIED_*``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA_ID = "medradar.external.source_register.v1"

REQUIRED_FIELDS: tuple[str, ...] = (
    "source_id",
    "source_name",
    "official_url",
    "country_or_region",
    "category",
    "official_or_commercial",
    "api_available",
    "bulk_download_available",
    "authentication",
    "free_tier",
    "rate_limits",
    "licence",
    "redistribution_allowed",
    "update_frequency",
    "historical_coverage",
    "entity_identifiers",
    "timestamp_fields",
    "known_limitations",
    "connection_status",
    "research_value",
    "evidence_urls",
    "verified_at",
)

TRISTATE = {"YES", "NO", "UNKNOWN", "PARTIAL"}

STATUS_RANK: dict[str, int] = {
    "VERIFIED_API": 6,
    "VERIFIED_BULK_DOWNLOAD": 6,
    "VERIFIED_PUBLIC_QUERY": 5,
    "REQUIRES_REGISTRATION": 4,
    "PAID_ONLY": 3,
    "BLOCKED_BY_POLICY": 2,
    "UNAVAILABLE": 1,
    "NOT_TESTED": 0,
}

VALID_STATUSES = frozenset(STATUS_RANK)


def blank_record(source_id: str) -> dict[str, Any]:
    return {field: "UNKNOWN" for field in REQUIRED_FIELDS} | {
        "source_id": source_id,
        "entity_identifiers": [],
        "timestamp_fields": [],
        "known_limitations": [],
        "evidence_urls": [],
        "verified_at": "",
        "connection_status": "NOT_TESTED",
    }


def validate_record(record: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in record:
            problems.append(f"{record.get('source_id', '?')}: missing field {field}")
    status = record.get("connection_status")
    if status not in VALID_STATUSES:
        problems.append(f"{record.get('source_id', '?')}: invalid connection_status {status!r}")
    for field in ("api_available", "bulk_download_available", "redistribution_allowed"):
        value = record.get(field)
        if value not in TRISTATE and value is not None:
            problems.append(f"{record.get('source_id', '?')}: {field} must be YES/NO/PARTIAL/UNKNOWN")
    if status in {"VERIFIED_API", "VERIFIED_BULK_DOWNLOAD", "VERIFIED_PUBLIC_QUERY"}:
        if not record.get("verified_at"):
            problems.append(f"{record.get('source_id', '?')}: verified status needs verified_at")
        if not record.get("evidence_urls"):
            problems.append(f"{record.get('source_id', '?')}: verified status needs evidence_urls")
    return problems


def load_source_records(registry_dir: Path) -> dict[str, dict[str, Any]]:
    """Load every ``sources/*.json`` record, keyed by ``source_id``."""
    records: dict[str, dict[str, Any]] = {}
    sources_dir = Path(registry_dir) / "sources"
    if not sources_dir.is_dir():
        return records
    for path in sorted(sources_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            items = payload
        else:
            items = [payload]
        for item in items:
            source_id = str(item.get("source_id", "")).strip()
            if not source_id:
                raise ValueError(f"{path}: record without source_id")
            if source_id in records:
                raise ValueError(f"duplicate source_id {source_id!r} (also in {path.name})")
            records[source_id] = item
    return records


def load_probe_results(root: Path) -> dict[str, dict[str, Any]]:
    """Load every ``probes/<source_id>/PROBE_RESULT.json``."""
    results: dict[str, dict[str, Any]] = {}
    probes_dir = Path(root) / "probes"
    if not probes_dir.is_dir():
        return results
    for path in sorted(probes_dir.glob("*/PROBE_RESULT.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        source_id = str(payload.get("source_id") or path.parent.name)
        results[source_id] = payload
    return results


def merge_record(record: Mapping[str, Any], probe: Mapping[str, Any] | None) -> dict[str, Any]:
    """Overlay empirical probe facts on the documented record."""
    merged = dict(record)
    merged.setdefault("documentation_claim", {})
    merged["documentation_claim"] = {
        "api_available": record.get("api_available"),
        "bulk_download_available": record.get("bulk_download_available"),
        "authentication": record.get("authentication"),
        "documented_at": record.get("verified_at", ""),
    }
    if probe:
        status = str(probe.get("status", "NOT_TESTED"))
        merged["connection_status"] = status
        merged["verified_at"] = probe.get("verified_at", "")
        merged["probe"] = {
            "status": status,
            "requests": probe.get("requests", 0),
            "notes": probe.get("notes", ""),
            "error": probe.get("error", ""),
            "n_probes": len(probe.get("probes", []) or []),
        }
        urls = list(merged.get("evidence_urls") or [])
        for url in probe.get("evidence_urls", []) or []:
            if url not in urls:
                urls.append(url)
        merged["evidence_urls"] = urls
        if status.startswith("VERIFIED_"):
            merged["verified_by"] = "live_probe"
        elif status in {"UNAVAILABLE", "REQUIRES_REGISTRATION", "PAID_ONLY", "BLOCKED_BY_POLICY"}:
            merged["verified_by"] = "live_probe_negative"
        else:
            merged["verified_by"] = "documentation_only"
    else:
        merged["verified_by"] = "documentation_only"
    return merged


def build_register(root: Path) -> dict[str, Any]:
    root = Path(root)
    documentation = load_source_records(root / "registry")
    probes = load_probe_results(root)
    merged = [merge_record(doc, probes.get(source_id)) for source_id, doc in documentation.items()]
    merged.sort(key=lambda r: (-STATUS_RANK.get(str(r.get("connection_status")), 0), str(r["source_id"])))
    problems: list[str] = []
    for record in merged:
        problems.extend(validate_record(record))
    probe_only = sorted(set(probes) - set(documentation))
    by_status: dict[str, int] = {}
    for record in merged:
        key = str(record.get("connection_status", "NOT_TESTED"))
        by_status[key] = by_status.get(key, 0) + 1
    by_domain: dict[str, int] = {}
    for record in merged:
        key = str(record.get("domain", "UNSET"))
        by_domain[key] = by_domain.get(key, 0) + 1
    register = {
        "schema": SCHEMA_ID,
        "generated_from": {
            "documentation_records": len(documentation),
            "probe_results": len(probes),
            "probe_without_record": probe_only,
        },
        "counts": {
            "sources": len(merged),
            "by_connection_status": by_status,
            "by_domain": by_domain,
        },
        "validation_problems": problems,
        "sources": merged,
    }
    return register


def write_register(root: Path, out_path: Path) -> dict[str, Any]:
    register = build_register(root)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(register, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return register


def status_counts(records: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        key = str(record.get("connection_status", "NOT_TESTED"))
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))
