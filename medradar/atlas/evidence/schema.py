"""ATLAS Evidence Record v1 (``medradar.atlas.evidence.v1``).

One record = one documented external fact, bound to immutable raw bytes.

Every record answers six questions before it may enter the store:

1. **Who said it?** ``source_id`` + ``source_record_id`` + ``source_url``.
2. **What exactly did they say?** ``source_content_hash`` (raw bytes) and
   ``normalized_content_hash`` (the projection ATLAS actually uses).
3. **When did it happen, when was it public, when did we see it, when did we
   fetch it?** Four separate clocks; missing values are explicit, never filled
   with a convenient date.
4. **Which entity is it about, and how sure are we?** ``identity_resolution``
   with a tier; candidates are stored apart from confirmed links.
5. **What relation status does it support?** ``relation_status`` describes
   whether the record asserts a relation, is only a candidate, or is a negative
   control — never a claim of causality.
6. **May we store/redistribute it?** ``licence_status`` + ``quality_flags``.

The record is a plain ``dict`` so it round-trips through JSON unchanged and can
be hashed deterministically.  ``make_evidence`` is the only constructor;
``validate_evidence`` is the only gate.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_ID = "medradar.atlas.evidence.v1"
SCHEMA_VERSION = "1.0.0"

EVIDENCE_TYPES: frozenset[str] = frozenset(
    {
        "device_registration",
        "regulatory_clearance",
        "regulatory_approval",
        "postmarket_event",
        "recall",
        "patent",
        "publication",
        "clinical_trial",
        "procurement_event",
        "grant",
        "trade_statistic",
        "company_registry",
        "product_identifier",
    }
)

TIME_QUALITIES: frozenset[str] = frozenset({"exact", "day", "coarse", "derived", "unknown"})
LICENCE_STATUSES: frozenset[str] = frozenset(
    {"public_domain", "open_licence", "open_no_explicit_licence", "restricted", "unknown"}
)
IDENTITY_STATUSES: frozenset[str] = frozenset(
    {"confirmed", "candidate", "none", "not_attempted", "ambiguous"}
)
RELATION_STATUSES: frozenset[str] = frozenset(
    {"asserted_by_source", "candidate", "none", "contradicted", "unknown"}
)
QUALITY_FLAGS: frozenset[str] = frozenset(
    {
        "missing_primary_identifier",
        "missing_company",
        "missing_time",
        "coarse_time",
        "derived_time",
        "duplicate_across_sources",
        "identifier_conflict",
        "schema_drift",
        "truncated_payload",
        "unverified_identity",
        "licence_restricted",
        "source_unavailable",
    }
)

CONFIRMED_METHODS = frozenset({"official_id", "exact_alias", "multi_field"})
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class EvidenceError(ValueError):
    """Raised when a record does not satisfy the v1 contract."""


# --------------------------------------------------------------------- hashing
def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(payload: Any) -> str:
    return sha256_text(canonical_json(payload))


def deterministic_id(prefix: str, *parts: str) -> str:
    if not parts:
        raise EvidenceError("deterministic_id needs at least one part")
    return f"{prefix}_{sha256_text('|'.join(parts))[:32]}"


def make_evidence_id(source_id: str, source_record_id: str, evidence_type: str) -> str:
    """Record identity, independent of content and of fetch time."""
    return deterministic_id("ev", source_id, evidence_type, source_record_id)


def canonical_key(identifiers: Sequence[Mapping[str, Any]]) -> str | None:
    """Cross-source duplicate key from *authoritative* identifiers only.

    A DI beats a national licence number, which beats a clearance number, which
    beats a DOI.  Two records that share a canonical key describe the same
    underlying object and must not be counted as independent evidence.
    """
    priority = [
        "di", "basic_udi_di", "licence_no", "510k", "pma", "denovo",
        "recall_number", "nct", "doi", "pmid", "patent_no", "ocid",
    ]
    by_scheme: dict[str, str] = {}
    for ident in identifiers:
        scheme = str(ident.get("scheme", "")).strip().lower()
        value = str(ident.get("value", "")).strip()
        if scheme and value:
            by_scheme.setdefault(scheme, value.lower() if scheme == "doi" else value)
    for scheme in priority:
        if scheme in by_scheme:
            return f"{scheme}:{by_scheme[scheme]}"
    return None


# ------------------------------------------------------------------- construct
def make_evidence(
    *,
    source_id: str,
    source_record_id: str,
    evidence_type: str,
    source_url: str,
    raw_content_hash: str,
    raw_bytes: int,
    normalized: Mapping[str, Any],
    time: Mapping[str, Any],
    identifiers: Iterable[Mapping[str, Any]] = (),
    entity_refs: Iterable[Mapping[str, Any]] = (),
    canonical_entity_id: str = "",
    identity_resolution_status: str = "not_attempted",
    relation_status: str = "none",
    licence_status: str = "unknown",
    quality_flags: Iterable[str] = (),
    provenance: Mapping[str, Any] | None = None,
    collection_run_id: str = "",
) -> dict[str, Any]:
    """Build one v1 record.  Callers must pass real hashes, never placeholders."""
    if evidence_type not in EVIDENCE_TYPES:
        raise EvidenceError(f"unknown evidence_type: {evidence_type!r}")
    if not source_id or not source_record_id:
        raise EvidenceError("source_id and source_record_id are required")
    if not _HEX64.match(str(raw_content_hash)):
        raise EvidenceError("raw_content_hash must be a lowercase sha256 digest")
    if licence_status not in LICENCE_STATUSES:
        raise EvidenceError(f"unknown licence_status: {licence_status!r}")
    if identity_resolution_status not in IDENTITY_STATUSES:
        raise EvidenceError(f"unknown identity_resolution_status: {identity_resolution_status!r}")
    if relation_status not in RELATION_STATUSES:
        raise EvidenceError(f"unknown relation_status: {relation_status!r}")

    ids = [dict(i) for i in identifiers if i]
    refs = [dict(r) for r in entity_refs if r]
    prov = dict(provenance or {})
    normalized_payload = dict(normalized)
    normalized_hash = sha256_json(normalized_payload)
    evidence_id = make_evidence_id(source_id, source_record_id, evidence_type)
    flags = sorted({str(f) for f in quality_flags if f})
    unknown_flags = [f for f in flags if f not in QUALITY_FLAGS]
    if unknown_flags:
        raise EvidenceError(f"unknown quality flags: {unknown_flags}")

    return {
        "schema": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "evidence_id": evidence_id,
        "evidence_type": evidence_type,
        "source_id": source_id,
        "source_record_id": str(source_record_id),
        "source_url": source_url,
        "canonical_entity_id": canonical_entity_id,
        "source_content_hash": raw_content_hash,
        "normalized_content_hash": normalized_hash,
        "collection_run_id": collection_run_id,
        "time": dict(time),
        "normalized": normalized_payload,
        "identifiers": ids,
        "entity_refs": refs,
        "identity_resolution_status": identity_resolution_status,
        "relation_status": relation_status,
        "licence_status": licence_status,
        "quality_flags": flags,
        "provenance": {
            "source_name": prov.get("source_name", source_id),
            "attribution": prov.get("attribution", ""),
            "evidence_reference": prov.get("evidence_reference", ""),
            "source_time_quality": prov.get("source_time_quality", ""),
            "raw_bytes": int(raw_bytes),
            "raw_path": prov.get("raw_path", ""),
            "upstream_authority": prov.get("upstream_authority", source_id),
        },
        "canonical_key": canonical_key(ids),
        "content_hash": normalized_hash,
    }


# --------------------------------------------------------------------- validate
def validate_evidence(record: Mapping[str, Any]) -> list[str]:
    """Return every contract violation; an empty list means valid."""
    problems: list[str] = []
    if record.get("schema") != SCHEMA_ID:
        problems.append(f"schema must be {SCHEMA_ID}")
    if record.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"schema_version must be {SCHEMA_VERSION}")
    if record.get("evidence_type") not in EVIDENCE_TYPES:
        problems.append(f"unknown evidence_type: {record.get('evidence_type')!r}")
    for field in ("evidence_id", "source_id", "source_record_id", "normalized_content_hash",
                  "source_content_hash"):
        if not record.get(field):
            problems.append(f"{field} is required")
    for field in ("source_content_hash", "normalized_content_hash"):
        if record.get(field) and not _HEX64.match(str(record[field])):
            problems.append(f"{field} must be a lowercase sha256 digest")
    if record.get("normalized_content_hash") and record.get("content_hash") != record.get(
        "normalized_content_hash"
    ):
        problems.append("content_hash must equal normalized_content_hash")
    # Recompute the hash from the payload: a record whose hash does not cover
    # its own normalized content cannot be trusted as immutable evidence, and
    # silently editing ``normalized`` must fail validation rather than look like
    # an unchanged re-fetch.
    if isinstance(record.get("normalized"), Mapping):
        recomputed = sha256_json(record["normalized"])
        if record.get("normalized_content_hash") and recomputed != record["normalized_content_hash"]:
            problems.append("normalized_content_hash does not match the normalized payload")

    time_block = record.get("time")
    if not isinstance(time_block, Mapping):
        problems.append("time block missing")
    else:
        for clock in ("event_at", "source_public_at", "first_observed_at", "fetched_at"):
            if clock not in time_block:
                problems.append(f"time.{clock} missing")
        quality = time_block.get("source_public_at_quality")
        if quality not in TIME_QUALITIES:
            problems.append(f"time.source_public_at_quality invalid: {quality!r}")
        if time_block.get("source_public_at") and not time_block.get("observation_basis"):
            problems.append("time.observation_basis missing when a public date exists")

    if record.get("licence_status") not in LICENCE_STATUSES:
        problems.append(f"licence_status invalid: {record.get('licence_status')!r}")
    if record.get("identity_resolution_status") not in IDENTITY_STATUSES:
        problems.append(
            f"identity_resolution_status invalid: {record.get('identity_resolution_status')!r}"
        )
    if record.get("relation_status") not in RELATION_STATUSES:
        problems.append(f"relation_status invalid: {record.get('relation_status')!r}")
    unknown_flags = [f for f in record.get("quality_flags", []) if f not in QUALITY_FLAGS]
    if unknown_flags:
        problems.append(f"unknown quality flags: {unknown_flags}")

    for ref in record.get("entity_refs", []) or []:
        method = ref.get("method")
        if method not in {"official_id", "exact_alias", "multi_field", "candidate", "none"}:
            problems.append(f"entity_ref method invalid: {method!r}")
            continue
        confidence = ref.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0.0 <= float(confidence) <= 1.0:
            problems.append("entity_ref confidence must be within [0, 1]")
        if method == "candidate" and float(confidence) >= 0.9:
            problems.append("candidate links must not carry confirmed-level confidence")
        if method in CONFIRMED_METHODS and not ref.get("matched_alias") and not ref.get("firm_key"):
            problems.append(f"confirmed link ({method}) must record its basis")
    return problems


def require_valid(record: Mapping[str, Any]) -> Mapping[str, Any]:
    problems = validate_evidence(record)
    if problems:
        raise EvidenceError("; ".join(problems))
    return record


def is_independent(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    """True only when two records are genuinely independent observations.

    Same canonical key means the same underlying record (possibly republished by
    an aggregator) and is not a second observation.
    """
    if a.get("evidence_id") == b.get("evidence_id"):
        return False
    key_a, key_b = a.get("canonical_key"), b.get("canonical_key")
    return not (key_a and key_b and key_a == key_b)


__all__ = [
    "EvidenceError",
    "CONFIRMED_METHODS",
    "EVIDENCE_TYPES",
    "IDENTITY_STATUSES",
    "LICENCE_STATUSES",
    "QUALITY_FLAGS",
    "RELATION_STATUSES",
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "TIME_QUALITIES",
    "canonical_json",
    "canonical_key",
    "deterministic_id",
    "is_independent",
    "make_evidence",
    "make_evidence_id",
    "require_valid",
    "sha256_bytes",
    "sha256_json",
    "sha256_text",
    "validate_evidence",
]
