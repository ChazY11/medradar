"""Four dedupe layers, deliberately kept apart.

Conflating them is how a pipeline reports inflated evidence counts or, worse,
deletes real records.  Each layer answers a different question and is allowed to
collapse a different amount:

``record_identity``
    *Is this the same source publication of the same record?*  Collapsing this is
    always safe: it is the same bytes from the same source id.
``entity_identity``
    *Do two records describe the same real-world object?*  Collapsed only through
    an authoritative identifier (:func:`medradar.atlas.evidence.schema.canonical_key`).
    Two sources carrying the same DOI are one work, not two independent
    observations — but they are still two *records*.
``event_identity``
    *Is this the same official event?*  For an award notice that names several
    suppliers, the event is shared but each supplier's award is a distinct fact.
    The party is therefore part of the key: collapsing on the notice id alone
    would silently delete co-awarded suppliers, which is a defect HORIZON already
    observed once.
``relation_identity``
    *Is this the same asserted link?*  ``(from, to, type, method)``, so a
    confirmed link and a candidate link between the same pair are distinct facts.

Patent families get one extra consideration: publications of the same invention in
several jurisdictions share a family but are not the same publication, and are not
independent inventions either.  :func:`patent_family_key` exposes the family so a
study can group without either double-counting or deleting.
"""

from __future__ import annotations

import collections
from typing import Any, Iterable, Mapping

from medradar.atlas.evidence.schema import canonical_key, is_independent

from .contract import (
    DEDUPE_LAYER_ENTITY,
    DEDUPE_LAYER_EVENT,
    DEDUPE_LAYER_RECORD,
    DEDUPE_LAYER_RELATION,
    PARTY_BEARING_EVENT_SOURCES,
    event_identity_key,
)

#: Attribute keys that may carry the party name of an event record, in priority
#: order.  Kept explicit rather than fuzzy-matching every field.
_PARTY_ATTRIBUTE_KEYS: tuple[str, ...] = (
    "supplier_name",
    "awardee_name",
    "recipient_name",
    "vendor_name",
    "winner_name",
    "party_name",
    "contractor_name",
    "tenderer_name",
)

#: Attribute keys that identify a patent family, in priority order.
_FAMILY_ATTRIBUTE_KEYS: tuple[str, ...] = (
    "pct_application_number",
    "priority_claims",
    "priority_application_number",
    "earliest_priority_number",
)

#: Values that sources emit in place of a missing field.  Treated as absent so a
#: family of ``"NULL"`` is never counted as a real family (HORIZON does this).
_MISSING_SENTINELS: frozenset[str] = frozenset({"NULL", "NONE", "NAN", "N/A", "NA", "-"})


def record_identity(evidence: Mapping[str, Any]) -> str:
    """Layer 1 key: the ATLAS evidence id already encodes (source, record, type)."""
    return str(evidence.get("evidence_id") or "")


def entity_identity(evidence: Mapping[str, Any]) -> str | None:
    """Layer 2 key: authoritative cross-source identifier, or ``None``.

    ``None`` is a real answer: 40% of the HORIZON export carries no
    authoritative identifier, and those records cannot be de-duplicated on
    identity at all.  Pretending otherwise by hashing the title would manufacture
    matches.
    """
    key = evidence.get("canonical_key")
    if key:
        return str(key)
    return canonical_key(evidence.get("identifiers") or [])


def party_of(evidence: Mapping[str, Any]) -> str | None:
    """Best available party name for an event record, if the source has one."""
    source_id = str(evidence.get("source_id") or "")
    if source_id not in PARTY_BEARING_EVENT_SOURCES:
        return None
    horizon = (evidence.get("normalized") or {}).get("horizon") or {}
    attributes = horizon.get("attributes") or {}
    for key in _PARTY_ATTRIBUTE_KEYS:
        value = attributes.get(key)
        if value:
            return str(value).strip()
    # Some sources carry the party as an identifier rather than a name.
    for ident in evidence.get("identifiers") or []:
        if str(ident.get("scheme")) in {"ocds_party_id", "sam_uei"}:
            return str(ident.get("value") or "").strip() or None
    return None


def event_identity(evidence: Mapping[str, Any]) -> str:
    """Layer 3 key: official event id **plus** the party for party-bearing sources."""
    horizon = (evidence.get("normalized") or {}).get("horizon") or {}
    return event_identity_key(
        str(evidence.get("source_id") or ""),
        str(horizon.get("source_record_id") or evidence.get("source_record_id") or ""),
        party_of(evidence),
    )


def relation_identity(from_ref: str, to_ref: str, relation_type: str, method: str) -> str:
    """Layer 4 key: a specific asserted link, not merely a pair of entities."""
    return f"{from_ref}|{to_ref}|{relation_type}|{method}"


def patent_family_key(evidence: Mapping[str, Any]) -> str | None:
    """Family key for a patent publication, or ``None`` if no family field exists.

    A family is *not* a publication and *not* an independent invention.  Two
    national publications of one PCT application share this key; they must be
    grouped by it, neither merged into one record nor counted as two inventions.
    """
    if str(evidence.get("evidence_type")) != "patent":
        return None
    horizon = (evidence.get("normalized") or {}).get("horizon") or {}
    attributes = horizon.get("attributes") or {}
    for key in _FAMILY_ATTRIBUTE_KEYS:
        value = attributes.get(key)
        if not value:
            continue
        if isinstance(value, (list, tuple)):
            for item in value:
                candidate = str(item).strip() if item is not None else ""
                if candidate and candidate.upper() not in _MISSING_SENTINELS:
                    return f"family:{candidate}"
            continue
        candidate = str(value).strip()
        if candidate and candidate.upper() not in _MISSING_SENTINELS:
            return f"family:{candidate}"
    # Fall back to the PCT/publication number already present as an identifier.
    for ident in evidence.get("identifiers") or []:
        if str(ident.get("scheme")) in {"pct_application_number", "pct_publication_number"}:
            return f"family:{ident.get('value')}"
    return None


def dedupe_report(
    evidence_records: Iterable[Mapping[str, Any]],
    *,
    relations: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Measure every dedupe layer without deleting anything.

    Returning *measurements* rather than a reduced list is deliberate: the caller
    decides what to collapse, and the report makes clear how much any collapse
    would remove.  ``relations`` is the asserted-link list; the relation layer
    cannot be measured from evidence records because a relation is not a record.
    """
    records = [r for r in evidence_records if r]
    relation_rows = [r for r in relations if r]
    layer_record = collections.Counter(record_identity(r) for r in records)
    indexable = [r for r in records if entity_identity(r)]
    layer_entity = collections.Counter(entity_identity(r) for r in indexable)
    layer_event = collections.Counter(event_identity(r) for r in records)
    layer_relation = collections.Counter(
        relation_identity(
            str(r.get("from_ref")),
            str(r.get("to_ref")),
            str(r.get("relation_type")),
            str(r.get("method")),
        )
        for r in relation_rows
    )

    # Same payload republished by different sources: the strongest duplicate
    # signal available, because it compares bytes rather than names.
    by_hash: dict[str, set[str]] = collections.defaultdict(set)
    for r in records:
        digest = str(r.get("source_content_hash") or "")
        if digest:
            by_hash[digest].add(str(r.get("source_id")))
    cross_source_payload_dupes = {
        digest: sorted(sources) for digest, sources in by_hash.items() if len(sources) > 1
    }

    # Genuine independence: same canonical key from several records is one
    # observation, not several.  Reported as a pair count because that is what a
    # study's n depends on.
    independent_pairs = 0
    compared = 0
    by_key: dict[str, list[Mapping[str, Any]]] = collections.defaultdict(list)
    for r in indexable:
        by_key[entity_identity(r) or ""].append(r)
    for group in by_key.values():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                compared += 1
                if is_independent(group[i], group[j]):
                    independent_pairs += 1

    families = collections.Counter(
        key for key in (patent_family_key(r) for r in records) if key
    )

    return {
        "records_total": len(records),
        "layers": {
            DEDUPE_LAYER_RECORD: {
                "distinct": len(layer_record),
                "duplicates": len(records) - len(layer_record),
            },
            DEDUPE_LAYER_ENTITY: {
                "records_with_authoritative_key": len(indexable),
                "records_without_authoritative_key": len(records) - len(indexable),
                "distinct_entities": len(layer_entity),
                "records_collapsed_into_shared_entity": len(indexable) - len(layer_entity),
                "groups": {k: v for k, v in layer_entity.items() if v > 1},
            },
            DEDUPE_LAYER_EVENT: {
                "distinct_events_with_party": len(layer_event),
                "shared_event_groups": {
                    k: v for k, v in layer_event.items() if v > 1 and "party=" in k
                },
            },
            DEDUPE_LAYER_RELATION: {
                "distinct_relation_rows": len(layer_relation),
            },
        },
        "cross_source_payload_duplicates": len(cross_source_payload_dupes),
        "cross_source_payload_duplicate_detail": dict(
            list(cross_source_payload_dupes.items())[:50]
        ),
        "entity_key_pair_comparisons": compared,
        "independent_pairs_same_key": independent_pairs,
        "patent_families": {
            "distinct_families": len(families),
            "publications_in_families": sum(families.values()),
            "largest_families": families.most_common(10),
        },
    }


__all__ = [
    "dedupe_report",
    "entity_identity",
    "event_identity",
    "patent_family_key",
    "party_of",
    "record_identity",
    "relation_identity",
]
