"""Six research queries that the integrated substrate can actually answer.

Every answer carries the evidence that produced it: the ATLAS evidence id, the
originating source and its own record id, the source URL, the four clocks, the
licence status and the grade of any inferred link.  A query that cannot cite its
evidence is a query this module refuses to return.

The six correspond to the CONVERGENCE acceptance queries:

1. company → product → official regulatory evidence
2. company → patent candidate → publication time
3. product → clinical trial or paper candidate
4. company → historical subsidiary → patent applicant
5. technology theme → independent evidence from several sources
6. a historical date → what was observed, what was merely public, what is unprovable
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Iterable, Mapping

from medradar.atlas.evidence.timeq import parse_date, utc_iso

from .graph import DEFAULT_FIRM_ALIASES
from .staging import ConvergenceStore

#: How many rows a demo query returns before it says it truncated.
DEFAULT_LIMIT = 25


def _evidence(store: ConvergenceStore, evidence_id: str) -> dict[str, Any] | None:
    rows = store.atlas.query(
        "SELECT payload_json FROM evidence WHERE evidence_id=?"
        " ORDER BY version DESC LIMIT 1",
        (evidence_id,),
    )
    if not rows:
        return None
    payload = json.loads(rows[0]["payload_json"])
    return payload


def _cite(record: Mapping[str, Any]) -> dict[str, Any]:
    """A compact, auditable citation block for one evidence record."""
    horizon = ((record.get("normalized") or {}).get("horizon")) or {}
    time_block = record.get("time") or {}
    return {
        "evidence_id": record.get("evidence_id"),
        "source_id": record.get("source_id"),
        "source_record_id": record.get("source_record_id"),
        "source_url": record.get("source_url"),
        "evidence_type": record.get("evidence_type"),
        "name": horizon.get("original_name"),
        "manufacturer": horizon.get("manufacturer"),
        "identifiers": record.get("identifiers"),
        "time": {
            "event_at": time_block.get("event_at"),
            "source_public_at": time_block.get("source_public_at"),
            "first_observed_at": time_block.get("first_observed_at"),
            "fetched_at": time_block.get("fetched_at"),
            "source_public_at_quality": time_block.get("source_public_at_quality"),
        },
        "licence_status": record.get("licence_status"),
        "identity_resolution_status": record.get("identity_resolution_status"),
        "relation_status": record.get("relation_status"),
        "quality_flags": record.get("quality_flags"),
        "source_record_status": (
            (record.get("normalized") or {}).get("convergence") or {}
        ).get("source_record_status"),
    }


def _firm_evidence_ids(store: ConvergenceStore, firm: str) -> list[str]:
    # basis_json is serialised with compact separators, so match the exact form
    # ATLAS wrote rather than a pretty-printed variant.
    rows = store.atlas.query(
        "SELECT DISTINCT from_ref FROM conv_relation_candidates"
        " WHERE relation_type IN ('MANUFACTURED_BY','APPLIED_BY') AND basis_json LIKE ?",
        (f'%"firm":"{firm}"%',),
    )
    return [row["from_ref"] for row in rows]


# ---------------------------------------------------------------- query 1
def q1_company_product_regulatory(
    store: ConvergenceStore, firm: str = "medtronic", *, limit: int = DEFAULT_LIMIT
) -> dict[str, Any]:
    """company → product (UDI-DI) → the official GUDID record that states it."""
    evidence_ids = _firm_evidence_ids(store, firm)
    products: list[dict[str, Any]] = []
    licences: list[dict[str, Any]] = []
    for evidence_id in evidence_ids[: limit * 4]:
        record = _evidence(store, evidence_id)
        if not record:
            continue
        ids = record.get("identifiers") or []
        schemes = {str(i.get("scheme")) for i in ids}
        if "di" in schemes and len(products) < limit:
            products.append(_cite(record))
        elif "licence_no" in schemes and len(licences) < limit:
            licences.append(_cite(record))
        if len(products) >= limit and len(licences) >= limit:
            break
    return {
        "query": "company → product → official regulatory evidence",
        "firm": firm,
        "product_identifiers_found": len(products),
        "licence_records_found": len(licences),
        "products": products,
        "canada_licences": licences,
        "note": (
            "Products are cited by their UDI-DI as published by the source; the "
            "source_record_id and source_url resolve to the official record."
        ),
        "generated_at": utc_iso(),
    }


# ---------------------------------------------------------------- query 2
def q2_company_patent_publication(
    store: ConvergenceStore, firm: str = "medtronic", *, limit: int = DEFAULT_LIMIT
) -> dict[str, Any]:
    """company → patent applicant candidate → publication time."""
    rows = store.atlas.query(
        "SELECT DISTINCT from_ref, basis_json FROM conv_relation_candidates"
        " WHERE relation_type='APPLIED_BY' AND basis_json LIKE ? LIMIT ?",
        (f'%"firm":"{firm}"%', limit * 4),
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        record = _evidence(store, row["from_ref"])
        if not record:
            continue
        citation = _cite(record)
        citation["relation_grade"] = "SOURCE_ASSERTED_RELATION"
        citation["relation_basis"] = json.loads(row["basis_json"])
        out.append(citation)
        if len(out) >= limit:
            break
    return {
        "query": "company → patent applicant candidate → publication time",
        "firm": firm,
        "found": len(out),
        "patents": out,
        "note": (
            "Applicant attribution is a source assertion derived from the office "
            "record; it is not proof that the current corporate group owns the "
            "patent today."
        ),
        "generated_at": utc_iso(),
    }


# ---------------------------------------------------------------- query 3
def q3_product_trial_or_paper(
    store: ConvergenceStore, keyword: str = "infusion", *, limit: int = DEFAULT_LIMIT
) -> dict[str, Any]:
    """product/technology keyword → clinical trial or paper **candidate**."""
    like = f"%{keyword.lower()}%"
    rows = store.atlas.query(
        "SELECT e.evidence_id, e.evidence_type, e.source_id FROM evidence e"
        " JOIN evidence_head h ON h.evidence_id=e.evidence_id AND h.latest_version=e.version"
        " WHERE e.evidence_type IN ('clinical_trial','publication')"
        "   AND lower(e.payload_json) LIKE ? LIMIT ?",
        (like, limit * 3),
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        record = _evidence(store, row["evidence_id"])
        if not record:
            continue
        citation = _cite(record)
        # A keyword hit is a candidate link, never a confirmed product binding.
        citation["link_grade"] = "CANDIDATE_RELATION"
        out.append(citation)
        if len(out) >= limit:
            break
    return {
        "query": "product/technology keyword → trial or paper candidate",
        "keyword": keyword,
        "found": len(out),
        "records": out,
        "note": (
            "Keyword overlap is a CANDIDATE link only. No trial or paper is bound "
            "to a specific FDA device on the strength of a word."
        ),
        "generated_at": utc_iso(),
    }


# ---------------------------------------------------------------- query 4
def q4_historical_subsidiary(
    store: ConvergenceStore, firm: str = "medtronic", *, limit: int = DEFAULT_LIMIT
) -> dict[str, Any]:
    """company → historically-named applicant (subsidiary vs parent vs acquired).

    This is the query the whole identity model exists for.  A patent prints the
    applicant name *as it was at publication*.  Medtronic's own portfolio in this
    corpus includes patents applied for by Tyco Healthcare, Covidien, St. Jude
    Medical and Arterial Vascular Engineering — companies that at the time of
    filing were not necessarily Medtronic.  The answer therefore reports the
    historical applicant string and explicitly refuses to assert present-day
    ownership or an acquisition date, neither of which this evidence contains.
    """
    rows = store.atlas.query(
        "SELECT e.evidence_id, e.payload_json FROM evidence e"
        " JOIN evidence_head h ON h.evidence_id=e.evidence_id AND h.latest_version=e.version"
        " WHERE e.evidence_type='patent' AND lower(e.payload_json) LIKE ?",
        (f"%{firm.lower()}%",),
    )
    applicants: dict[str, dict[str, Any]] = {}
    for row in rows:
        record = json.loads(row["payload_json"])
        horizon = ((record.get("normalized") or {}).get("horizon")) or {}
        attributes = horizon.get("attributes") or {}
        names = attributes.get("applicants") or []
        if isinstance(names, str):
            names = [names]
        time_block = record.get("time") or {}
        first_id = (record.get("identifiers") or [{}])[0]
        for name in names:
            name = str(name).strip()
            if not name:
                continue
            entry = applicants.setdefault(
                name,
                {
                    "applicant_name": name,
                    "records": 0,
                    "first_publication_seen": None,
                    "example_evidence_id": record.get("evidence_id"),
                    "example_source_id": record.get("source_id"),
                    "example_publication_number": first_id.get("value"),
                    "example_source_url": record.get("source_url"),
                    "differs_from_group_name": firm.lower() not in name.lower(),
                },
            )
            entry["records"] += 1
            published = time_block.get("source_public_at")
            if published and (
                entry["first_publication_seen"] is None
                or str(published) < str(entry["first_publication_seen"])
            ):
                entry["first_publication_seen"] = published
    ordered = sorted(
        applicants.values(), key=lambda e: (-e["records"], e["applicant_name"])
    )
    return {
        "query": "company → historical applicant name → patent publications",
        "firm": firm,
        "patents_mentioning_firm": len(rows),
        "distinct_applicant_names": len(applicants),
        "applicants": ordered[:limit],
        "not_asserted": [
            "that the applicant still belongs to this corporate group",
            "any acquisition or divestiture date",
            "that a patent in this list is a medical device patent merely because "
            "the applicant name matches",
        ],
        "note": (
            "Each applicant string is the name the patent office printed at "
            "publication time. Group affiliation today is a separate claim that "
            "this evidence does not support; it requires a corporate-history "
            "source, which the integrated corpus does not yet carry."
        ),
        "generated_at": utc_iso(),
    }


# ---------------------------------------------------------------- query 5
def q5_technology_theme_independent_evidence(
    store: ConvergenceStore,
    scheme: str = "fda_product_code",
    value: str = "MHX",
    *,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """technology theme → independent evidence across sources, measured honestly.

    Two different things get called "independent evidence" and this query keeps
    them apart:

    * **Several official registers about one theme.**  An FDA product code that
      appears in the 510(k) register, the classification register and the
      establishment-registration register is three different official records
      with three different identifiers, so they are genuinely distinct evidence,
      not duplicates.
    * **One work republished by several aggregators.**  A DOI carried by Crossref,
      OpenAlex, Openaire, EuropePMC, PubMed and Semantic Scholar is *one* work
      seen six times, and counting it as six independent findings would be
      exactly the inflation this integration exists to prevent.  The query
      therefore reports the raw source count and the collapsed work count.
    """
    rows = store.atlas.query(
        "SELECT e.evidence_id, e.source_id, e.evidence_type FROM evidence e"
        " JOIN evidence_identifiers i ON i.evidence_id=e.evidence_id AND i.version=e.version"
        " WHERE i.scheme=? AND i.value=?", (scheme, value)
    )
    by_source: dict[str, dict[str, Any]] = {}
    works: set[str] = set()
    for row in rows:
        record = _evidence(store, row["evidence_id"])
        if not record:
            continue
        entry = by_source.setdefault(
            str(row["source_id"]),
            {"records": 0, "record_types": set(), "examples": []},
        )
        entry["records"] += 1
        entry["record_types"].add(str(row["evidence_type"]))
        if len(entry["examples"]) < 3:
            entry["examples"].append(_cite(record))
        if record.get("canonical_key"):
            works.add(str(record["canonical_key"]))
    source_count = len(by_source)
    records_total = sum(entry["records"] for entry in by_source.values())
    return {
        "query": "technology theme → independent evidence from several sources",
        "theme": {"scheme": scheme, "value": value},
        "records_total": records_total,
        "distinct_sources": source_count,
        "distinct_canonical_works": len(works),
        "independence_statement": (
            "Distinct official registers are independent evidence. Records that "
            "share a canonical identifier are one work regardless of how many "
            "aggregators republished them, so the independent count is the "
            "smaller of (distinct sources, distinct canonical works) only after "
            "the identity layer has collapsed cross-source republication."
        ),
        "sources": {
            source: {
                "records": entry["records"],
                "record_types": sorted(entry["record_types"]),
                "examples": entry["examples"],
            }
            for source, entry in sorted(by_source.items())
        },
        "generated_at": utc_iso(),
    }


# ---------------------------------------------------------------- query 6
def q6_as_of(store: ConvergenceStore, as_of: str, *, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    """What was knowable on a date: observed, merely public, or unprovable."""
    cutoff = parse_date(as_of)
    if cutoff is None:
        raise ValueError(f"unparseable as_of date: {as_of!r}")
    rows = store.atlas.query(
        "SELECT e.evidence_id FROM evidence e"
        " JOIN evidence_head h ON h.evidence_id=e.evidence_id AND h.latest_version=e.version"
    )
    buckets: dict[str, list[dict[str, Any]]] = {
        "observed_by_cutoff": [],
        "public_by_cutoff_not_yet_observed": [],
        "not_knowable_by_cutoff": [],
    }
    for row in rows:
        record = _evidence(store, row["evidence_id"])
        if not record:
            continue
        time_block = record.get("time") or {}
        public = parse_date(time_block.get("source_public_at"))
        observed = parse_date(time_block.get("first_observed_at"))
        # An unknown observation clock is NOT treated as "observed early".
        if observed is not None and observed <= cutoff:
            buckets["observed_by_cutoff"].append(_cite(record))
        elif public is not None and public <= cutoff:
            buckets["public_by_cutoff_not_yet_observed"].append(_cite(record))
        else:
            buckets["not_knowable_by_cutoff"].append(_cite(record))
    return {
        "query": "historical as-of: observed / public-inferred / unprovable",
        "as_of": as_of,
        "counts": {key: len(value) for key, value in buckets.items()},
        "observed_by_cutoff": buckets["observed_by_cutoff"][:limit],
        "public_by_cutoff_not_yet_observed": buckets["public_by_cutoff_not_yet_observed"][:limit],
        "not_knowable_by_cutoff": buckets["not_knowable_by_cutoff"][:limit],
        "note": (
            "A record whose first_observed_at is unknown is never counted as "
            "observed by the cutoff; the earliest defensible claim about it is "
            "its source_public_at, labelled retrospective discovery."
        ),
        "generated_at": utc_iso(),
    }


def run_all(
    store: ConvergenceStore,
    *,
    firm: str = "medtronic",
    keyword: str = "infusion",
    theme: tuple[str, str] = ("fda_product_code", "MHX"),
    as_of: str = "2020-01-01",
) -> dict[str, Any]:
    """Run the whole demonstration and return one JSON document."""
    return {
        "generated_at": utc_iso(),
        "firm": firm,
        "queries": {
            "q1_company_product_regulatory": q1_company_product_regulatory(store, firm),
            "q2_company_patent_publication": q2_company_patent_publication(store, firm),
            "q3_product_trial_or_paper": q3_product_trial_or_paper(store, keyword),
            "q4_historical_subsidiary": q4_historical_subsidiary(store, firm),
            "q5_technology_theme_independent_evidence": q5_technology_theme_independent_evidence(
                store, theme[0], theme[1]
            ),
            "q6_as_of": q6_as_of(store, as_of),
        },
    }


__all__ = [
    "q1_company_product_regulatory",
    "q2_company_patent_publication",
    "q3_product_trial_or_paper",
    "q4_historical_subsidiary",
    "q5_technology_theme_independent_evidence",
    "q6_as_of",
    "run_all",
]
