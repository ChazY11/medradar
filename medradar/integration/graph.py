"""Cross-source knowledge graph built on ATLAS relation semantics.

Promotion rules
---------------
The only thing that may create an ``AUTHORITATIVE_ID_MATCH`` is the **same
official identifier value in the same namespace on two different sources**:

``di``          a GUDID UDI-DI that also appears as a validated GTIN-14 in
                Health Canada's MDALL identifier field → the same device.
``doi``         the same DOI carried by Crossref / OpenAlex / Openaire / … →
                the same work, *not* two independent findings.
``510k``/``pma`` the same FDA clearance number → the same clearance.
``pct_*``       the same PCT application/publication number → the same patent
                family, which is a family link, not a same-invention claim.

Everything else is demoted by construction:

* a manufacturer name that matches a firm alias is a ``SOURCE_ASSERTED_RELATION``
  (the source says so) and is never an identity match;
* a patent applicant hint is a ``CANDIDATE_RELATION`` — HORIZON itself calls
  those ``applicant_group_candidate``;
* a shared classification (HS code, FDA product code, IPC subclass) is a
  ``CANDIDATE_RELATION`` about a *technology theme*, never a statement that two
  devices are the same product.  This is the rule that stops "every paper about
  infusion pumps is bound to every infusion pump".

The builder writes graded candidates to ``conv_relation_candidates`` and the
confirmable ones to ATLAS's own ``entity_relations`` through
:meth:`AtlasStore.add_relation`, so the integration does not maintain a second,
divergent graph.
"""

from __future__ import annotations

import collections
import json
from typing import Any, Iterable, Mapping

from medradar.atlas.evidence.timeq import utc_iso
from medradar.atlas.identity.resolver import MatchDecision

from .contract import IDENTITY_GRADE_EFFECTS
from .staging import ConvergenceStore

#: Identifier schemes that may establish an authoritative cross-source link, and
#: the relation type each produces.  Deliberately small.
AUTHORITATIVE_SCHEMES: dict[str, str] = {
    "di": "SAME_DEVICE_IDENTITY",
    "520k": "SAME_CLEARANCE",
    "510k": "SAME_CLEARANCE",
    "pma": "SAME_CLEARANCE",
    "doi": "SAME_WORK",
    "nct": "SAME_TRIAL",
}

#: Schemes that link publications of one patent family without claiming they are
#: the same publication or independent inventions.
FAMILY_SCHEMES: frozenset[str] = frozenset(
    {"pct_application_number", "pct_publication_number"}
)

#: The five pre-declared firms from ATLAS's configuration.  Company linkage is
#: restricted to these; a free-text manufacturer string never invents a company.
DEFAULT_FIRM_ALIASES: dict[str, tuple[str, ...]] = {
    "medtronic": ("medtronic",),
    "ge_healthcare": ("ge healthcare", "ge medical", "general electric", "ge healthcare technologies"),
    "philips": ("philips",),
    "draeger": ("draeger", "dräger", "draegerwerk"),
    "mindray": ("mindray", "shenzhen mindray"),
}


def _latest_identifiers(store: ConvergenceStore) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Map (scheme, value) → the evidence records carrying it, latest versions only."""
    rows = store.atlas.query(
        "SELECT i.scheme AS scheme, i.value AS value, e.evidence_id AS evidence_id,"
        " e.source_id AS source_id, e.evidence_type AS evidence_type,"
        " e.canonical_key AS canonical_key"
        " FROM evidence_identifiers i"
        " JOIN evidence_head h ON h.evidence_id = i.evidence_id AND h.latest_version = i.version"
        " JOIN evidence e ON e.evidence_id = i.evidence_id AND e.version = i.version"
    )
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = collections.defaultdict(list)
    for row in rows:
        grouped[(row["scheme"], row["value"])].append(dict(row))
    return grouped


def build_authoritative_links(
    store: ConvergenceStore, *, run_id: str
) -> dict[str, Any]:
    """Create identity relations from shared official identifiers across sources."""
    grouped = _latest_identifiers(store)
    created: list[dict[str, Any]] = []
    stats = collections.Counter()
    for (scheme, value), holders in grouped.items():
        stats[f"identifiers_{scheme}"] += 1
        if scheme in FAMILY_SCHEMES:
            if len({h["source_id"] for h in holders}) < 2:
                continue
            # Family link: asserted by the patent office for its own documents,
            # but not a claim that two publications are one invention.
            for i in range(len(holders)):
                for j in range(i + 1, len(holders)):
                    a, b = holders[i], holders[j]
                    if a["source_id"] == b["source_id"]:
                        continue
                    stats["family_links"] += 1
                    created.append(
                        _emit(
                            store,
                            run_id=run_id,
                            left=a,
                            right=b,
                            relation_type="SAME_PATENT_FAMILY",
                            grade="SOURCE_ASSERTED_RELATION",
                            basis={"shared_scheme": scheme, "shared_value": value},
                            confidence=0.9,
                        )
                    )
            continue
        relation_type = AUTHORITATIVE_SCHEMES.get(scheme)
        if not relation_type:
            continue
        # Only a cross-source shared identifier is evidence of identity.
        by_source = collections.defaultdict(list)
        for holder in holders:
            by_source[holder["source_id"]].append(holder)
        if len(by_source) < 2:
            continue
        source_ids = sorted(by_source)
        for i in range(len(source_ids)):
            for j in range(i + 1, len(source_ids)):
                left = by_source[source_ids[i]][0]
                right = by_source[source_ids[j]][0]
                stats[f"cross_source_{scheme}"] += 1
                created.append(
                    _emit(
                        store,
                        run_id=run_id,
                        left=left,
                        right=right,
                        relation_type=relation_type,
                        grade="AUTHORITATIVE_ID_MATCH",
                        basis={"shared_scheme": scheme, "shared_value": value},
                        confidence=0.99,
                    )
                )
    return {"created": len(created), "by_relation": dict(collections.Counter(c["relation_type"] for c in created)), "stats": dict(stats), "sample": created[:20]}


def _emit(
    store: ConvergenceStore,
    *,
    run_id: str,
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    relation_type: str,
    grade: str,
    basis: Mapping[str, Any],
    confidence: float,
) -> dict[str, Any]:
    """Record one graded link in both the staging log and ATLAS's relation store."""
    effects = IDENTITY_GRADE_EFFECTS[grade]
    decision = MatchDecision(
        left_ref=str(left["evidence_id"]),
        right_ref=str(right["evidence_id"]),
        relation_type=relation_type,
        # ATLAS's graph status vocabulary is CONFIRMED / CANDIDATE / REJECTED.
        # The finer convergence grade is preserved in conv_relation_candidates,
        # so the two vocabularies never get confused with each other.
        status=str(effects["atlas_db_status"]),
        method=effects["atlas_method"],
        authority="cross_source_official_identifier"
        if grade == "AUTHORITATIVE_ID_MATCH"
        else "source_declared",
        confidence=confidence,
        basis=dict(basis),
        contradictions=[],
        rejection_reason="",
    )
    relation_id = store.atlas.add_relation(
        decision,
        from_type=str(left.get("evidence_type") or "evidence"),
        to_type=str(right.get("evidence_type") or "evidence"),
        evidence_ids=[str(left["evidence_id"]), str(right["evidence_id"])],
        run_id=run_id,
        graph_relation=relation_type,
    )
    store.record_relation_candidate(
        run_id=run_id,
        relation_id=relation_id,
        from_ref=decision.left_ref,
        from_type=str(left.get("evidence_type") or "evidence"),
        to_ref=decision.right_ref,
        to_type=str(right.get("evidence_type") or "evidence"),
        relation_type=relation_type,
        grade=grade,
        atlas_relation_status=effects["atlas_relation_status"],
        may_set_confirmed_identity=bool(effects["may_set_confirmed_identity"]),
        basis=dict(basis),
    )
    return {
        "relation_id": relation_id,
        "relation_type": relation_type,
        "grade": grade,
        "left": decision.left_ref,
        "right": decision.right_ref,
        "basis": dict(basis),
    }


def build_company_links(
    store: ConvergenceStore,
    *,
    run_id: str,
    firm_aliases: Mapping[str, Iterable[str]] | None = None,
) -> dict[str, Any]:
    """Link evidence to the five pre-declared firms by exact alias containment.

    This is a source assertion about who made/registered something — never an
    identity match, and never extended to firms outside the declared set.
    """
    aliases = {
        key: tuple(value) for key, value in (firm_aliases or DEFAULT_FIRM_ALIASES).items()
    }
    rows = store.atlas.query(
        "SELECT e.evidence_id, e.source_id, e.evidence_type, e.canonical_key, e.payload_json"
        " FROM evidence e JOIN evidence_head h ON h.evidence_id=e.evidence_id"
        " AND h.latest_version=e.version"
    )
    links: list[dict[str, Any]] = []
    ambiguous = 0
    for row in rows:
        payload = json.loads(row["payload_json"])
        horizon = (payload.get("normalized") or {}).get("horizon") or {}
        manufacturer = str(horizon.get("manufacturer") or "")
        attributes = horizon.get("attributes") or {}
        haystacks = [manufacturer]
        for key in ("company_name", "applicant", "applicants", "org_name"):
            value = attributes.get(key)
            if isinstance(value, str):
                haystacks.append(value)
            elif isinstance(value, (list, tuple)):
                haystacks.extend(str(v) for v in value if v)
        text = " | ".join(h for h in haystacks if h).lower()
        if not text.strip():
            continue
        hits = [firm for firm, names in aliases.items() if any(name in text for name in names)]
        if len(hits) > 1:
            ambiguous += 1
            continue
        if not hits:
            continue
        firm = hits[0]
        relation_type = "APPLIED_BY" if row["evidence_type"] == "patent" else "MANUFACTURED_BY"
        link = {
            "evidence_id": row["evidence_id"],
            "firm": firm,
            "relation_type": relation_type,
            "grade": "SOURCE_ASSERTED_RELATION",
            "confidence": 0.9,
            "basis": {"matched_text": text[:200]},
        }
        # Persist as a graded candidate attached to the evidence record and to a
        # company node.  It is deliberately NOT written to ATLAS entity_relations:
        # a free-text manufacturer match is a source assertion about a company,
        # not an established device/company identity edge.
        store.record_relation_candidate(
            run_id=run_id,
            relation_id=f"cl_{row['evidence_id']}_{firm}",
            from_ref=row["evidence_id"],
            from_type=str(row["evidence_type"]),
            to_ref=f"company:{firm}",
            to_type="company",
            relation_type=relation_type,
            grade="SOURCE_ASSERTED_RELATION",
            atlas_relation_status="asserted_by_source",
            may_set_confirmed_identity=False,
            basis={"matched_text": text[:200], "firm": firm},
        )
        links.append(link)
    by_firm = collections.Counter(link["firm"] for link in links)
    return {
        "links": len(links),
        "ambiguous_skipped": ambiguous,
        "by_firm": dict(by_firm),
        "by_relation": dict(collections.Counter(link["relation_type"] for link in links)),
        "sample": links[:20],
    }


def build_graph(store: ConvergenceStore, *, run_id: str) -> dict[str, Any]:
    """Build every relation layer and return a reproducible summary."""
    authoritative = build_authoritative_links(store, run_id=run_id)
    company = build_company_links(store, run_id=run_id)
    relations = store.atlas.list_relations()
    return {
        "generated_at": utc_iso(),
        "run_id": run_id,
        "authoritative_links": authoritative,
        "company_links": company,
        "atlas_relations_total": len(relations),
        "atlas_relations_by_status": dict(
            collections.Counter(str(r["status"]) for r in relations)
        ),
        "atlas_relations_by_type": dict(
            collections.Counter(str(r["relation_type"]) for r in relations)
        ),
    }


__all__ = [
    "AUTHORITATIVE_SCHEMES",
    "DEFAULT_FIRM_ALIASES",
    "build_authoritative_links",
    "build_company_links",
    "build_graph",
]
