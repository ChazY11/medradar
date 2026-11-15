"""Relationship quality report (PRODUCT-003 Phase 7).

The report answers "what does MedRadar actually know about device relationships", not "how big is the
graph". It separates four verification levels that must never be merged:

1. **rule consistency** - the relation was produced by a deterministic rule from official fields;
2. **documentary evidence** - the official identifier/field and URL are recorded with the relation;
3. **human review** - a human checked it (zero in this release);
4. **accuracy estimate** - a measured correctness figure (UNKNOWN in this release).

It also counts what could not be linked, so a low linkage rate cannot be hidden by deleting records.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from .identifiers import NOT_MODELLED, RELATION_TYPES
from .model import RELATION_STATUSES


def _relation_counts(index: Any) -> dict[str, Any]:
    """Evidence completeness is reported per status, because a candidate's evidence is a rule, not a document."""
    by_type: dict[str, Counter] = {}
    by_status: Counter = Counter()
    official_evidence = 0
    rule_evidence_only = 0
    missing_evidence = 0
    for relation in index.relations:
        bucket = by_type.setdefault(relation.relation_type, Counter())
        bucket[relation.status] += 1
        by_status[relation.status] += 1
        if not relation.evidence or not all(item.field for item in relation.evidence):
            missing_evidence += 1
            continue
        if all(item.kind in ("official_identifier", "record_field") for item in relation.evidence):
            official_evidence += 1
        else:
            rule_evidence_only += 1
    confirmed_total = by_status.get("confirmed", 0)
    return {
        "total": len(index.relations),
        "by_status": {status: by_status.get(status, 0) for status in RELATION_STATUSES},
        "by_type": {
            relation_type: {status: bucket.get(status, 0) for status in RELATION_STATUSES}
            for relation_type, bucket in sorted(by_type.items())
        },
        "confirmed_with_official_evidence": official_evidence,
        "confirmed_official_evidence_share": round(official_evidence / confirmed_total, 6) if confirmed_total else None,
        "candidate_with_rule_evidence": rule_evidence_only,
        "relations_missing_evidence": missing_evidence,
        "note": (
            "Confirmed relations cite an official identifier or record field with its URL. Candidate relations cite the "
            "similarity rule that produced them; that is rule evidence, not documentary evidence."
        ),
    }


def _family_counts(index: Any) -> dict[str, Any]:
    families = list(index.families.values())
    supplement_types: Counter = Counter()
    for application in index.applications.values():
        if application.kind == "pma_supplement" and application.supplement_type:
            supplement_types[application.supplement_type] += 1
    return {
        "families": len(families),
        "with_original_in_snapshot": sum(1 for family in families if family.original_in_snapshot),
        "without_original_in_snapshot": sum(1 for family in families if not family.original_in_snapshot),
        "with_supplements": sum(1 for family in families if family.supplement_count),
        "largest_families": sorted(
            [
                {"family_id": family.family_id, "name": family.name[:80], "supplements": family.supplement_count}
                for family in families
            ],
            key=lambda item: -item["supplements"],
        )[:5],
        "supplement_type_distribution": dict(supplement_types.most_common(12)),
        "basis": "FDA PMA number: the original approval and every supplement that carries the same PMA number",
    }


def _recall_counts(index: Any) -> dict[str, Any]:
    total = len(index.recalls)
    confirmed = len(index.recall_k_references)
    external_only = sum(1 for event_id in index.external_k_references if event_id not in index.recall_k_references)
    unlinked = total - confirmed - external_only
    return {
        "recalls": total,
        "with_confirmed_application_reference_in_snapshot": confirmed,
        "only_referencing_applications_outside_snapshot": external_only,
        "without_any_official_reference": unlinked,
        "confirmed_reference_share": round(confirmed / total, 6) if total else None,
        "external_reference_edges": sum(len(values) for values in index.external_k_references.values()),
        "note": "A recall without a K-number reference is not deleted or guessed: it is listed as unlinked and counted here.",
    }


def _conflicts(index: Any) -> dict[str, Any]:
    product_code_mismatch = 0
    multi_application_recalls = 0
    external_only = 0
    for recall in index.recalls.values():
        targets = index.recall_k_references.get(recall.event_id, ())
        if len(targets) > 1:
            multi_application_recalls += 1
        if not targets:
            continue
        codes = {
            index.applications[target].product_code
            for target in targets
            if target in index.applications
        }
        if recall.product_code and codes and recall.product_code not in codes:
            product_code_mismatch += 1
    # ambiguity: one normalised device name shared by several applicants (never merged, but flagged)
    name_applicants: dict[str, set[str]] = {}
    for device in index.devices.values():
        key = " ".join(str(device.name or "").casefold().split())
        if not key:
            continue
        name_applicants.setdefault(key, set()).add(str(device.applicant_name or "").casefold())
    shared_names = sum(1 for applicants in name_applicants.values() if len(applicants) > 1)
    return {
        "product_code_mismatch_between_recall_and_referenced_application": product_code_mismatch,
        "recalls_referencing_multiple_applications": multi_application_recalls,
        "device_names_shared_by_multiple_applicants": shared_names,
        "note": "A shared or mismatching name is reported, never merged. These records keep their own identity and their own evidence.",
    }


def _coverage(index: Any) -> dict[str, Any]:
    """Per-device counts come from the precomputed stats, so a relation about the device's own
    application (for example a recall K-number reference) is credited to the device."""
    devices = list(index.devices.values())
    stats = index.device_stats
    with_confirmed = sum(1 for device in devices if stats.get(device.device_id, {}).get("confirmed_relations", 0) > 0)
    candidate_only = sum(
        1
        for device in devices
        if stats.get(device.device_id, {}).get("confirmed_relations", 0) == 0
        and stats.get(device.device_id, {}).get("candidate_relations", 0) > 0
    )
    none = len(devices) - with_confirmed - candidate_only
    return {
        "devices": len(devices),
        "devices_with_confirmed_relation": with_confirmed,
        "devices_with_candidate_relation_only": candidate_only,
        "devices_with_no_relation": none,
        "identity_basis": dict(Counter(device.identity_basis for device in devices)),
        "note": "A confirmed relation includes an official reference to the device's own application (for example a recall K-number reference). Most 510(k) devices still have no family or predicate relation: openFDA exposes no identifier for those.",
    }


def quality_report(index: Any) -> dict[str, Any]:
    relations = _relation_counts(index)
    report = {
        "schema": "medradar.device_quality.v1",
        "snapshot_id": index.snapshot_id,
        "builder_version": "product-003.device_index.v1",
        "applications": index.stats.get("applications", len(index.applications)),
        "applications_by_kind": index.stats.get("applications_by_kind", {}),
        "devices": index.stats.get("devices", len(index.devices)),
        "families": _family_counts(index),
        "recalls": _recall_counts(index),
        "relations": relations,
        "candidates": {
            "device_clusters": index.stats.get("candidate_device_clusters", 0),
            "recall_application_relations": index.stats.get("candidate_recall_relations", 0),
            "rules": {
                "candidate_same_device": "same applicant + product code + normalised device name",
                "candidate_recall_application": "recall without an official K reference, same tracked group + product code (bounded to 3 candidates)",
            },
            "statement": "Candidates are hypotheses generated by a deterministic rule. They are never counted as established relations and the product never promotes them.",
        },
        "coverage": _coverage(index),
        "conflicts_and_ambiguity": _conflicts(index),
        "relation_types": RELATION_TYPES,
        "not_modelled": NOT_MODELLED,
        "verification_levels": {
            "rule_consistency": {
                "value": "every confirmed relation is produced by a named deterministic rule over official fields",
                "rules": sorted({relation.rule for relation in index.relations if relation.status == "confirmed"}),
            },
            "documentary_evidence": {
                "value": relations["confirmed_with_official_evidence"],
                "confirmed_relations": relations["by_status"].get("confirmed", 0),
                "share": relations["confirmed_official_evidence_share"],
                "candidate_rule_evidence": relations["candidate_with_rule_evidence"],
                "missing_evidence": relations["relations_missing_evidence"],
                "note": "only confirmed relations are counted here; a candidate's rule is not documentary evidence",
            },
            "human_review": {
                "value": 0,
                "note": "No human has reviewed a device relation in this release.",
            },
            "accuracy_estimate": {
                "value": None,
                "state": "unknown",
                "note": "No independent sample of device relations has been reviewed, so no accuracy figure is claimed. Rule consistency is not accuracy.",
            },
        },
        "limitations": [
            "openFDA exposes no predicate identifier for 510(k) submissions, so predicate relationships are not modelled.",
            "A recall record does not identify a device; it is linked to applications only through its official K-number field.",
            "PMA supplements are versions of the approved device, not separate devices; the family is the official application hierarchy, not proof of a commercial product family.",
            "Device names are not unique: the same normalised name can belong to different applicants, and it is never merged.",
            "The applicant field is a record claim; manufacturer and current ownership are shown through their own attribution status, not invented here.",
        ],
    }
    return report
