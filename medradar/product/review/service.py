"""Review queue, case detail, risk flags and impact accounting for identity review.

The queue is derived from the loaded dataset plus the review ledger, so what a reviewer sees is
exactly what the product currently counts. Nothing here writes: writes go through ReviewStore.

Design rules
------------
* Ordering is by affected record count (default), because a wrong high-volume mapping matters more
  than a wrong one-record mapping. Other orderings are explicit.
* A case always carries the evidence the product already has: the verbatim applicant string, the
  current attribution, the rule that produced it, the FDA records that depend on it, and the
  ownership relations that mention the entity.
* Risk flags are *hypotheses for the reviewer*, never conclusions. A flag says "look here", not
  "this is wrong".
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Mapping, Sequence

from ..attribution import ownership as ownership_module
from ..attribution import status as status_module
from .store import ReviewDecision, ReviewStore, normalise_applicant

RISK_FLAGS: dict[str, str] = {
    "unmatched_string": "The applicant string is not attributed to any tracked organization.",
    "proposed_mapping": "The mapping exists but has no rule and no evidence behind it.",
    "corporate_relation": "The mapping depends on a corporate relation (subsidiary/division/historical name) that needs documentary evidence.",
    "multi_org_scope": "The string was retrieved while querying more than one tracked organization; it may belong to either.",
    "cross_org_token": "The string contains another tracked organization's distinctive token: possible same-name or cross-company confusion.",
    "foreign_parent_us_operator": "The organization is not US-based but the applicant string names a US operating entity.",
    "predecessor_entity": "The string matches an acquired/predecessor entity: the current-group mapping may be right while the event-time owner was different.",
    "high_volume": "At least 1,000 records depend on this mapping: an error here moves a headline number.",
    "low_volume": "Three records or fewer depend on this mapping: an error is possible but its effect is small.",
    "name_variant": "Another spelling of the same organization is lexically equivalent; check the legal form rather than the brand.",
    "ambiguous_organization": "Another tracked organization shares a distinctive search token with this one.",
    "rejected_or_unresolved": "This string was reviewed before and rejected or left unresolved.",
}


def _org_tokens(registry: Any, organization_key: str) -> list[str]:
    organization = registry.organization(organization_key)
    if organization is None:
        return []
    tokens = [token for token in organization.search_tokens if len(token) > 5]
    tokens.extend(brand for brand in organization.brands if len(brand) > 5)
    return tokens


def _cross_org_tokens(registry: Any, organization_key: str, applicant_name: str) -> list[str]:
    words = status_module.words(applicant_name)
    hits = []
    for other in registry.organizations:
        if other.key == organization_key:
            continue
        for token in _org_tokens(registry, other.key):
            if status_module.contains_token_sequence(words, status_module.words(token)):
                hits.append(other.key + ":" + token)
    return sorted(set(hits))


def _lexical_variants(registry: Any, organization_key: str, applicant_name: str) -> list[str]:
    key = status_module.lexical_key(applicant_name)
    variants = []
    for decision in registry.accepted_spellings_by_org.get(organization_key, ()):
        if normalise_applicant(decision.applicant_name) == normalise_applicant(applicant_name):
            continue
        if status_module.lexical_key(decision.applicant_name) == key:
            variants.append(decision.applicant_name)
    return variants


def risk_flags(dataset: Any, applicant_name: str) -> list[dict[str, str]]:
    decision, rejection = dataset.registry.decide(applicant_name)
    row = dataset.applicant_by_name.get(applicant_name) or {}
    records = int(row.get("records") or 0)
    scope = sorted((row.get("by_org_scope") or {}).keys())
    flags: list[dict[str, str]] = []
    organization_key = decision.organization_key if decision else (scope[0] if len(scope) == 1 else None)
    organization = dataset.registry.organization(organization_key) if organization_key else None

    def add(code: str) -> None:
        flags.append({"code": code, "meaning": RISK_FLAGS[code]})

    if decision is None:
        add("unmatched_string")
    if decision is not None and decision.provisional:
        add("proposed_mapping")
    if decision is not None and decision.basis in ("subsidiary", "division", "historical_name"):
        add("corporate_relation")
    if len(scope) > 1:
        add("multi_org_scope")
    if organization_key and _cross_org_tokens(dataset.registry, organization_key, applicant_name):
        add("cross_org_token")
    if organization is not None and organization.country and organization.country.upper() not in ("US", "USA"):
        upper = applicant_name.upper()
        if any(token in upper for token in ("USA", "U.S.", "UNITED STATES", "AMERICA", "NORTH AMERICA")):
            add("foreign_parent_us_operator")
    for relation in ownership_module.ownership().all_for_applicant(applicant_name):
        flag = {"code": "predecessor_entity", "meaning": RISK_FLAGS["predecessor_entity"], "relation_id": relation.relation_id, "relation_status": relation.status}
        flags.append(flag)
        break
    if records >= 1000:
        add("high_volume")
    if records <= 3:
        add("low_volume")
    if organization_key and _lexical_variants(dataset.registry, organization_key, applicant_name):
        add("name_variant")
    if organization_key and dataset._ambiguous(organization_key):
        add("ambiguous_organization")
    if rejection is not None:
        add("rejected_or_unresolved")
    if decision is not None and decision.status == status_module.UNRESOLVED:
        if not any(flag["code"] == "rejected_or_unresolved" for flag in flags):
            add("rejected_or_unresolved")
    return flags


def _decision_public(decision: ReviewDecision | None) -> dict[str, Any] | None:
    return decision.to_public() if decision else None


def build_case(dataset: Any, store: ReviewStore, applicant_name: str) -> dict[str, Any]:
    decision, rejection = dataset.registry.decide(applicant_name)
    row = dataset.applicant_by_name.get(applicant_name) or {}
    scope = sorted((row.get("by_org_scope") or {}).keys())
    organization = dataset.registry.organization(decision.organization_key) if decision else None
    events = [
        event
        for event in dataset.events
        if normalise_applicant(event.applicant_name) == normalise_applicant(applicant_name)
    ]
    events.sort(key=lambda event: (event.event_date is None, event.event_date or ""), reverse=True)
    samples = [
        {
            "event_id": event.event_id,
            "official_id": event.official_id,
            "event_type": event.event_type,
            "event_date": event.event_date,
            "device_name": event.device_name,
            "product_code": event.product_code,
            "organization_key": event.organization_key,
            "verification": event.attribution_verification,
            "official_url": event.official_url,
        }
        for event in events[:8]
    ]
    candidates = []
    words = status_module.words(applicant_name)
    for org in dataset.registry.organizations:
        matched = [
            token
            for token in _org_tokens(dataset.registry, org.key)
            if status_module.contains_token_sequence(words, status_module.words(token))
        ]
        if matched:
            stats = dataset.org_stats.get(org.key)
            candidates.append(
                {
                    "organization_key": org.key,
                    "display_name": org.display_name,
                    "matched_tokens": matched,
                    "records": stats.counts["records"] if stats else 0,
                    "in_collection_scope": org.key in scope,
                }
            )
    candidates.sort(key=lambda item: (-item["records"], item["display_name"]))
    ownership_relations = [
        relation.to_public() for relation in ownership_module.ownership().all_for_applicant(applicant_name)
    ]
    history = store.history(applicant_name)
    return {
        "applicant_name": applicant_name,
        "applicant_key": normalise_applicant(applicant_name),
        "record_count": len(events),
        "by_source": row.get("by_source") or {},
        "collection_scope": scope,
        "current": {
            "status": decision.status if decision else ("rejected" if rejection else status_module.PROPOSED),
            "organization_key": decision.organization_key if decision else None,
            "organization_display": organization.display_name if organization else None,
            "basis": decision.basis if decision else None,
            "rule": decision.rule if decision else None,
            "rule_detail": decision.rule_detail if decision else None,
            "provenance": decision.provenance if decision else None,
            "verified": decision.verified if decision else False,
            "evidence": [item.to_public() for item in (decision.evidence if decision else ())],
            "reviewer": decision.reviewer if decision else None,
            "reviewer_kind": decision.reviewer_kind if decision else None,
            "decision_uid": decision.decision_uid if decision else None,
            "rejection_reason": rejection.reason if rejection else None,
        },
        "risk_flags": risk_flags(dataset, applicant_name),
        "candidate_organizations": candidates[:8],
        "ownership_relations": ownership_relations,
        "sample_records": samples,
        "history": [item.to_public() for item in history],
        "queue_hints": {
            "sort_key_records": len(events),
            "reviewer_kinds": ["human", "agent"],
            "allowed_statuses": list(status_module.DECISION_STATUSES),
        },
    }


def build_queue(
    dataset: Any,
    store: ReviewStore,
    *,
    status: str | None = None,
    organization: str | None = None,
    risk: str | None = None,
    query: str | None = None,
    sort: str = "records_desc",
    page: int = 1,
    page_size: int = 25,
    include_verified: bool = False,
) -> dict[str, Any]:
    rows = []
    needle = (query or "").strip().casefold()
    for applicant in dataset.applicants:
        applicant_name = str(applicant.get("applicant_name") or "")
        records = int(applicant.get("records") or 0)
        if not applicant_name:
            continue
        decision, rejection = dataset.registry.decide(applicant_name)
        if decision is None and rejection is None:
            current_status = "unresolved" if normalise_applicant(applicant_name) in dataset.registry.unresolved_strings else "unmatched"
        elif rejection is not None:
            current_status = status_module.REJECTED
        else:
            current_status = decision.status
        if status and current_status != status:
            continue
        if not include_verified and decision is not None and decision.verified:
            continue
        if organization:
            keys = set((applicant.get("by_org_scope") or {}).keys())
            if decision is not None:
                keys.add(decision.organization_key)
            if organization not in keys:
                continue
        if needle and needle not in applicant_name.casefold():
            continue
        flags = risk_flags(dataset, applicant_name)
        if risk and not any(flag["code"] == risk for flag in flags):
            continue
        rows.append(
            {
                "applicant_name": applicant_name,
                "record_count": records,
                "status": current_status,
                "organization_key": decision.organization_key if decision else None,
                "basis": decision.basis if decision else None,
                "rule": decision.rule if decision else None,
                "reviewer": decision.reviewer if decision else None,
                "reviewer_kind": decision.reviewer_kind if decision else None,
                "decision_uid": decision.decision_uid if decision else None,
                "collection_scope": sorted((applicant.get("by_org_scope") or {}).keys()),
                "sources": sorted((applicant.get("by_source") or {}).keys()),
                "risk_flags": [flag["code"] for flag in flags],
            }
        )
    if sort == "records_asc":
        rows.sort(key=lambda item: (item["record_count"], item["applicant_name"]))
    elif sort == "name_asc":
        rows.sort(key=lambda item: item["applicant_name"].casefold())
    elif sort == "risk_desc":
        rows.sort(key=lambda item: (-len(item["risk_flags"]), -item["record_count"]))
    else:
        rows.sort(key=lambda item: (-item["record_count"], item["applicant_name"].casefold()))
    total = len(rows)
    page_size = max(1, min(int(page_size), 200))
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(int(page), total_pages))
    start = (page - 1) * page_size
    payload_rows = rows[start:start + page_size]
    for row in payload_rows:
        row["risk_flags"] = [
            {"code": code, "meaning": RISK_FLAGS.get(code, "")} for code in row["risk_flags"]
        ]
    return {
        "items": payload_rows,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "total_records_affected": sum(item["record_count"] for item in rows),
        "sort": sort,
        "filters": {"status": status, "organization": organization, "risk": risk, "query": query},
        "definitions": {
            "queue": "Applicant strings whose current mapping is not evidence-verified or human-reviewed. Verified mappings are hidden unless include_verified=true.",
            "records_affected": "Attributed records that would change if this string were remapped or rejected.",
        },
    }


def queue_summary(dataset: Any, store: ReviewStore) -> dict[str, Any]:
    queue = build_queue(dataset, store, page_size=200, include_verified=False)
    # build_queue caps the page; recompute the aggregate without paging
    all_rows = []
    for applicant in dataset.applicants:
        applicant_name = str(applicant.get("applicant_name") or "")
        decision, rejection = dataset.registry.decide(applicant_name)
        if decision is None and rejection is None:
            status = "unresolved" if normalise_applicant(applicant_name) in dataset.registry.unresolved_strings else "unmatched"
        else:
            status = status_module.REJECTED if rejection is not None else decision.status
        all_rows.append((status, int(applicant.get("records") or 0)))
    by_status: dict[str, int] = {}
    records_by_status: dict[str, int] = {}
    for status, records in all_rows:
        by_status[status] = by_status.get(status, 0) + 1
        records_by_status[status] = records_by_status.get(status, 0) + records
    awaiting = sum(records for status, records in all_rows if status in (status_module.PROPOSED, "unmatched", status_module.UNRESOLVED))
    return {
        "queue_strings": len(all_rows),
        "awaiting_review_strings": sum(1 for status, _ in all_rows if status in (status_module.PROPOSED, "unmatched", status_module.UNRESOLVED)),
        "awaiting_review_records": awaiting,
        "by_status_strings": by_status,
        "by_status_records": records_by_status,
        "ledger": store.stats(),
    }


def attribution_impact(baseline_dataset: Any, current_dataset: Any) -> dict[str, Any]:
    """Prove which organizations changed and which did not after review decisions."""
    changed = []
    unchanged = 0
    all_keys = sorted(
        {org.key for org in baseline_dataset.registry.organizations}
        | {org.key for org in current_dataset.registry.organizations}
    )
    for key in all_keys:
        before = baseline_dataset.org_stats.get(key)
        after = current_dataset.org_stats.get(key)
        before_records = before.counts["records"] if before else 0
        after_records = after.counts["records"] if after else 0
        before_verified = before.verified_records if before else 0
        after_verified = after.verified_records if after else 0
        if before_records != after_records or before_verified != after_verified:
            changed.append(
                {
                    "organization_key": key,
                    "records_before": before_records,
                    "records_after": after_records,
                    "records_delta": after_records - before_records,
                    "verified_before": before_verified,
                    "verified_after": after_verified,
                }
            )
        else:
            unchanged += 1
    return {
        "changed_organizations": changed,
        "unchanged_organizations": unchanged,
        "statement": "Only organizations whose record or verification counts changed are listed; every other tracked organization is byte-identical in count terms.",
    }