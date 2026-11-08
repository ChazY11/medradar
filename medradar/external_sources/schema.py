"""External Evidence Schema v1 (medradar.external.evidence.v1).

Design goals, in order:

1. **Traceable** — every normalised record points at immutable raw bytes by
   content hash, and at the collection run that produced it.
2. **Bitemporal** — the time something happened, the time it became public, the
   time we first observed it, and the time we fetched it are four different
   facts.  Collapsing them is the single most common source of look-ahead bias.
3. **Idempotent** — ``evidence_id`` is a deterministic function of the source
   record identity, so re-fetching the same record does not create a second
   evidence item.  Content changes create new *versions* under the same id.
4. **De-duplicable across sources** — an aggregator re-publishing another
   source's record must not count as independent evidence.  ``canonical_key``
   is derived from authoritative identifiers only (DI, NCT, DOI, patent number,
   contract id), never from a keyword.
5. **Uncertainty-preserving** — a semantic guess is a *candidate*, stored
   separately from a deterministic link, and never silently promoted.

The record is a plain ``dict`` on purpose: it is written to JSON, checked by
:func:`validate_evidence`, and must remain stable against a JSON round trip.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_ID = "medradar.external.evidence.v1"

#: Evidence kinds.  One record = one *documented external fact*.
EVIDENCE_KINDS: frozenset[str] = frozenset(
    {
        "device_registration",  # UDI/listing/registration record (GUDID, MDALL, EUDAMED…)
        "regulatory_clearance",  # 510(k) / PMA / De Novo / CE certificate decision
        "postmarket_event",  # MAUDE / vigilance / adverse event report
        "recall",  # field safety corrective action / recall
        "import_alert",  # FDA import alert
        "shortage",  # device shortage entry
        "patent",  # patent document
        "publication",  # scholarly work
        "clinical_trial",  # trial registration
        "procurement_notice",  # tender / opportunity
        "procurement_award",  # contract award / award notice
        "grant",  # research funding award
        "job_posting",  # hiring requisition
        "shipment",  # company-level bill-of-lading / shipment record
        # Company-identifiable trade statistics WITHOUT shipment detail, e.g. UK
        # HMRC trader-level aggregates: a named trader, an HS code, a period, no
        # value.  Kept distinct from `shipment` so that "this trader moved goods
        # under this HS code" can never be read as "this consignment existed".
        "trade_by_trader",
        "trade_aggregate",  # country-level trade statistics (NOT company-level)
        "company_registry",  # legal-entity / registration datum
    }
)

#: Quality of the *publication* timestamp, not of the event.
#:
#: ``exact``      — source publishes a full timestamp (or a date at day precision)
#: ``day``        — calendar date only, day precision, unambiguous
#: ``coarse``     — month/year or a range; usable only for descriptive work
#: ``derived``    — we inferred it (e.g. from the first of a month); must be flagged
#: ``unknown``    — not published
TIME_QUALITIES: frozenset[str] = frozenset({"exact", "day", "coarse", "derived", "unknown"})

#: How a record was linked to a MedRadar entity.
#:
#: Only the first three are deterministic enough to count as a confirmed link.
#: ``candidate`` is the semantic tier and must be reported separately, always.
RESOLUTION_METHODS: frozenset[str] = frozenset(
    {
        "official_id",  # an authoritative identifier was matched
        "exact_alias",  # registry alias matched exactly after normalisation
        "multi_field",  # >=2 independent fields agreed (e.g. name + country + model)
        "candidate",  # semantic / fuzzy suggestion — NOT a confirmed link
        "none",  # no link attempted or none found
    }
)

CONFIRMED_METHODS: frozenset[str] = frozenset({"official_id", "exact_alias", "multi_field"})

#: Licence / redistribution posture of a source, as far as a *record* can say.
LICENCE_STATUSES: frozenset[str] = frozenset(
    {"public_domain", "open_licence", "open_no_explicit_licence", "restricted", "unknown"}
)

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class EvidenceError(ValueError):
    """Raised when a record does not satisfy the v1 contract."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def canonical_json(payload: Any) -> str:
    """Deterministic JSON used for every hash in this package."""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(payload: Any) -> str:
    return sha256_text(canonical_json(payload))


def deterministic_id(prefix: str, *parts: str) -> str:
    """Stable id from a prefix and ordered parts (no randomness, no clock)."""
    if not parts:
        raise EvidenceError("deterministic_id needs at least one part")
    digest = sha256_text("|".join(parts))[:32]
    return f"{prefix}_{digest}"


def make_evidence_id(source_id: str, source_record_id: str, kind: str) -> str:
    """Identity of a *record*, independent of its content and of fetch time."""
    return deterministic_id("ev", source_id, kind, source_record_id)


def canonical_key(identifiers: Sequence[Mapping[str, Any]]) -> str | None:
    """Cross-source de-duplication key from authoritative identifiers only.

    Order of preference is fixed: a UDI/DI beats a regulatory number, which
    beats a trial/DOI/patent/contract id.  Returns ``None`` when no
    authoritative identifier exists — in which case the record can never be
    de-duplicated across sources, and callers must not pretend otherwise.
    """
    priority = [
        "di",  # GUDID device identifier
        "basic_udi_di",  # EUDAMED Basic UDI-DI
        "licence_no",  # national licence / registration number
        "510k",  # FDA 510(k) number
        "pma",  # FDA PMA number
        "denovo",
        "recall_number",
        "nct",  # ClinicalTrials.gov id
        "doi",  # DOI (lower-cased)
        "pmid",
        "patent_no",  # normalised patent number
        "award_id",  # procurement/grant award id
        "ocid",  # OCDS open contracting id: one purchase, many releases
        "accession",  # regulator accession
    ]
    by_scheme: dict[str, str] = {}
    for ident in identifiers:
        scheme = str(ident.get("scheme", "")).strip().lower()
        value = str(ident.get("value", "")).strip()
        if not scheme or not value:
            continue
        if scheme == "doi":
            value = value.lower()
        by_scheme.setdefault(scheme, value)
    for scheme in priority:
        if scheme in by_scheme:
            return f"{scheme}:{by_scheme[scheme]}"
    return None


def make_evidence(
    *,
    source_id: str,
    kind: str,
    source_record_id: str,
    source_url: str,
    normalized: Mapping[str, Any],
    raw: Mapping[str, Any],
    time: Mapping[str, Any],
    identifiers: Iterable[Mapping[str, Any]] = (),
    entity_refs: Iterable[Mapping[str, Any]] = (),
    provenance: Mapping[str, Any] | None = None,
    collection_run_id: str = "",
    fetched_at: str = "",
) -> dict[str, Any]:
    """Build one v1 evidence record.

    ``raw`` must contain at least ``{"content_hash": <sha256>, "bytes": <n>}``.
    ``time`` must contain the four clocks described in :mod:`timeq`.
    """
    if kind not in EVIDENCE_KINDS:
        raise EvidenceError(f"unknown evidence kind: {kind!r}")
    if not source_id:
        raise EvidenceError("source_id is required")
    if not source_record_id:
        raise EvidenceError("source_record_id is required")

    ids = [dict(i) for i in identifiers]
    refs = [dict(r) for r in entity_refs]
    prov = dict(provenance or {})

    evidence_id = make_evidence_id(source_id, source_record_id, kind)
    normalized_hash = sha256_json(normalized)
    record: dict[str, Any] = {
        "schema": SCHEMA_ID,
        "evidence_id": evidence_id,
        "kind": kind,
        "source_id": source_id,
        "source_record_id": source_record_id,
        "source_url": source_url,
        "collection_run_id": collection_run_id,
        "fetched_at": fetched_at,
        "normalized": dict(normalized),
        "identifiers": ids,
        "entity_refs": refs,
        "time": dict(time),
        "provenance": {
            "source_name": prov.get("source_name", source_id),
            "licence_status": prov.get("licence_status", "unknown"),
            "redistribution": prov.get("redistribution", "unknown"),
            "attribution": prov.get("attribution", ""),
            "evidence_reference": prov.get("evidence_reference", ""),
            "raw_path": raw.get("path", ""),
            "raw_content_hash": raw.get("content_hash", ""),
            "normalized_content_hash": normalized_hash,
            "source_time_quality": prov.get("source_time_quality", ""),
        },
        "canonical_key": canonical_key(ids),
        "content_hash": normalized_hash,
        "raw": dict(raw),
    }
    return record


def validate_evidence(record: Mapping[str, Any]) -> list[str]:
    """Return a list of contract violations (empty == valid).

    Deliberately strict about the things that cause silent research error:
    missing clocks, unknown time quality, un-hashed raw content, and a
    ``candidate`` link that has been given a confirmed-looking confidence.
    """
    problems: list[str] = []
    if record.get("schema") != SCHEMA_ID:
        problems.append(f"schema must be {SCHEMA_ID}")
    kind = record.get("kind")
    if kind not in EVIDENCE_KINDS:
        problems.append(f"unknown kind: {kind!r}")
    for field in ("evidence_id", "source_id", "source_record_id", "content_hash"):
        if not record.get(field):
            problems.append(f"{field} is required")

    time_block = record.get("time")
    if not isinstance(time_block, Mapping):
        problems.append("time block missing")
    else:
        for clock in ("event_at", "source_public_at", "first_observed_at", "fetched_at"):
            if clock not in time_block:
                problems.append(f"time.{clock} missing")
        if not time_block.get("source_public_at_quality"):
            problems.append("time.source_public_at_quality missing")
        elif time_block["source_public_at_quality"] not in TIME_QUALITIES:
            problems.append(
                f"time.source_public_at_quality invalid: {time_block['source_public_at_quality']!r}"
            )

    raw = record.get("raw")
    if not isinstance(raw, Mapping):
        problems.append("raw block missing")
    else:
        digest = str(raw.get("content_hash", ""))
        if not _HEX64.match(digest):
            problems.append("raw.content_hash must be a lowercase sha256 hex digest")
        if not isinstance(raw.get("bytes"), int) or raw.get("bytes", -1) < 0:
            problems.append("raw.bytes must be a non-negative int")

    prov = record.get("provenance")
    if not isinstance(prov, Mapping):
        problems.append("provenance block missing")
    else:
        if prov.get("licence_status") not in LICENCE_STATUSES:
            problems.append(f"provenance.licence_status invalid: {prov.get('licence_status')!r}")
        if prov.get("normalized_content_hash") != record.get("content_hash"):
            problems.append("provenance.normalized_content_hash must equal content_hash")

    for ref in record.get("entity_refs", []) or []:
        method = ref.get("method")
        if method not in RESOLUTION_METHODS:
            problems.append(f"entity_ref method invalid: {method!r}")
            continue
        confidence = ref.get("confidence")
        if not isinstance(confidence, (int, float)) or not (0.0 <= float(confidence) <= 1.0):
            problems.append("entity_ref confidence must be within [0, 1]")
        if method == "candidate" and float(confidence) >= 0.9:
            problems.append("candidate links must not carry confirmed-level confidence")
        if method in CONFIRMED_METHODS and not ref.get("evidence"):
            problems.append(f"confirmed link ({method}) must record its evidence")
    return problems


def require_valid(record: Mapping[str, Any]) -> Mapping[str, Any]:
    problems = validate_evidence(record)
    if problems:
        raise EvidenceError("; ".join(problems))
    return record


def is_independent(record_a: Mapping[str, Any], record_b: Mapping[str, Any]) -> bool:
    """True only when two records are genuinely different evidence.

    Same ``canonical_key`` from the same *upstream* authority is a duplicate,
    not a second observation.  We treat an identical canonical key as a
    duplicate regardless of source, because the key is built from authoritative
    identifiers: if two sources agree on the DI of a device they are describing
    the same device listing.
    """
    if record_a.get("evidence_id") == record_b.get("evidence_id"):
        return False
    key_a = record_a.get("canonical_key")
    key_b = record_b.get("canonical_key")
    if key_a and key_b and key_a == key_b:
        return False
    return True
