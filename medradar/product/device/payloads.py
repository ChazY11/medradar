"""API payloads for the device module.

Kept out of the FastAPI routes so tests can exercise the same code the API returns, and so every
payload can state what it does and does not represent.
"""
from __future__ import annotations

import csv
import io
from typing import Any, Iterable, Sequence

from .identifiers import NOT_MODELLED, RELATION_TYPES
from .model import EVENT_KINDS, RELATION_STATUSES, STATUS_LABELS_EN, STATUS_LABELS_ZH

DEFINITIONS = {
    "regulatory_record": "one row in an FDA dataset: a 510(k) clearance, a PMA approval, a PMA supplement or a device recall",
    "regulatory_application": "an official FDA application identified by a K number, PMA number or PMA supplement number",
    "device_identity": "the specific device an application cleared or approved; MedRadar identifiers are internal and never impersonate an FDA identifier",
    "product_family": "a set of devices or versions whose relationship is evidenced; in this release only the PMA application hierarchy qualifies",
    "confirmed": "an official identifier or official record field establishes the relation",
    "candidate": "a deterministic similarity rule suggests the relation; it is NOT established",
    "unlinked": "no relation was established; the record remains visible and is counted",
}

APPLICANT_NOTE = (
    "The applicant is the string FDA recorded. Its organization attribution carries the PRODUCT-002 "
    "verification status; a device page never upgrades that status."
)


def applicant_block(dataset: Any, applicant_name: str) -> dict[str, Any]:
    decision, rejection = dataset.registry.decide(applicant_name)
    if decision is not None:
        return {
            "applicant_name": applicant_name,
            "state": "attributed",
            "organization_key": decision.organization_key,
            "organization_display": dataset.organization(decision.organization_key).display_name
            if dataset.organization(decision.organization_key)
            else None,
            "verification": decision.status,
            "verification_label_en": __import__("medradar.product.attribution.status", fromlist=["STATUS_LABELS_EN"]).STATUS_LABELS_EN.get(decision.status, decision.status),
            "verified": decision.verified,
            "rule": decision.rule,
            "note": APPLICANT_NOTE,
        }
    if rejection is not None:
        return {
            "applicant_name": applicant_name,
            "state": "rejected",
            "organization_key": None,
            "organization_display": None,
            "verification": "rejected",
            "verified": False,
            "note": APPLICANT_NOTE,
        }
    return {
        "applicant_name": applicant_name,
        "state": "unattributed",
        "organization_key": None,
        "organization_display": None,
        "verification": "unattributed",
        "verified": False,
        "note": APPLICANT_NOTE,
    }


def _device_counts(index: Any, device: Any) -> dict[str, int]:
    """Precomputed at build time: the explorer filters 24k devices, so per-device scans are not allowed."""
    return index.device_stats.get(
        device.device_id,
        {"applications": 1, "versions": 0, "recalls": 0, "confirmed_relations": 0, "candidate_relations": 0},
    )


def _matches_query(index: Any, device: Any, needle: str) -> bool:
    if not needle:
        return True
    needle = needle.casefold().strip()
    haystack = " ".join(
        [
            device.name or "",
            device.official_id or "",
            device.applicant_name or "",
            device.product_code or "",
            " ".join(device.models),
        ]
    ).casefold()
    if needle in haystack:
        return True
    # official-number search: allow "K123456", "k123456", "P980016"
    application = index.applications.get(device.application_id)
    if application and needle in application.official_id.casefold():
        return True
    return False


def explorer(
    dataset: Any,
    *,
    q: str | None = None,
    organization: str | None = None,
    product_code: str | None = None,
    category: str | None = None,
    pathway: str | None = None,
    relation: str | None = None,
    page: int = 1,
    page_size: int = 25,
    sort: str = "relevance",
) -> dict[str, Any]:
    index = dataset.device_index()
    needle = (q or "").strip()
    ids: Iterable[str]
    if organization:
        ids = index._devices_by_org.get(organization, [])
    elif category:
        ids = index._devices_by_category.get(category, [])
    elif product_code:
        ids = index._devices_by_product_code.get(product_code, [])
    else:
        ids = index.devices.keys()
    rows = []
    for device_identifier in ids:
        device = index.devices[device_identifier]
        if pathway and device.kind != pathway:
            continue
        if product_code and device.product_code != product_code.upper():
            continue
        if category and device.category_id != category:
            continue
        if not _matches_query(index, device, needle):
            continue
        counts = _device_counts(index, device)
        if relation == "confirmed" and counts["confirmed_relations"] == 0:
            continue
        if relation == "candidate" and counts["candidate_relations"] == 0:
            continue
        if relation == "none" and (counts["confirmed_relations"] or counts["candidate_relations"]):
            continue
        rows.append(
            {
                "device": device,
                "counts": counts,
                "organization_display": (
                    dataset.organization(device.organization_key).display_name
                    if device.organization_key and dataset.organization(device.organization_key)
                    else None
                ),
            }
        )
    if sort == "name_asc":
        rows.sort(key=lambda item: (item["device"].name or "").casefold())
    elif sort == "date_desc":
        rows.sort(key=lambda item: (item["device"].first_event_date is None, item["device"].first_event_date or ""), reverse=True)
    else:
        rows.sort(
            key=lambda item: (
                -item["counts"]["confirmed_relations"],
                -(item["device"].first_event_date or "").__len__() if False else False,
                (item["device"].first_event_date is None, item["device"].first_event_date or ""),
                (item["device"].name or "").casefold(),
            )
        )
    total = len(rows)
    page_size = max(1, min(int(page_size), 100))
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(int(page), total_pages))
    start = (page - 1) * page_size
    items = []
    for row in rows[start:start + page_size]:
        device_payload = row["device"].to_public()
        device_payload["counts"] = row["counts"]
        device_payload["organization_display"] = row["organization_display"]
        items.append(device_payload)
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "filters": {
            "q": needle,
            "organization": organization,
            "product_code": product_code,
            "category": category,
            "pathway": pathway,
            "relation": relation,
            "sort": sort,
        },
        "definitions": DEFINITIONS,
        "pathway_counts": index.stats.get("applications_by_kind", {}),
        "categories": index.categories(),
        "quality_summary": {
            "devices": index.stats.get("devices", 0),
            "devices_with_confirmed_relation": None,
            "recalls_without_any_official_reference": index.stats.get("recalls_without_any_reference", 0),
        },
        "index_build_ms": round(dataset.device_index_build_ms or 0.0, 1),
        "snapshot": dataset.snapshot_ref(),
    }


def _timeline(dataset: Any, index: Any, device: Any, versions: Sequence[Any], recalls: Sequence[Any]) -> list[dict[str, Any]]:
    items = []
    application = index.applications.get(device.application_id)
    if application is not None:
        items.append(
            {
                "kind": application.kind,
                "kind_label": EVENT_KINDS.get(application.kind, application.kind),
                "official_id": application.official_id,
                "date": application.decision_date,
                "event_date": application.decision_date,
                "first_observed_at": dataset.collected_at,
                "date_note": "FDA decision date",
                "official_url": application.official_url,
                "relation_status": "confirmed",
                "detail": application.decision_code,
                "event_id": application.event_id,
            }
        )
    for version in versions:
        items.append(
            {
                "kind": "pma_supplement",
                "kind_label": EVENT_KINDS["pma_supplement"],
                "official_id": version.official_id,
                "date": version.decision_date,
                "event_date": version.decision_date,
                "first_observed_at": dataset.collected_at,
                "date_note": "FDA decision date",
                "official_url": version.official_url,
                "relation_status": "confirmed",
                "detail": version.supplement_type or version.supplement_reason,
                "event_id": version.event_id,
                "version_of": device.official_id,
            }
        )
    for recall in recalls:
        items.append(
            {
                "kind": "recall",
                "kind_label": EVENT_KINDS["recall"],
                "official_id": recall.official_id,
                "date": recall.initiated_date,
                "event_date": recall.initiated_date,
                "first_observed_at": dataset.collected_at,
                "date_note": "recall initiation date (FDA posting date: " + str(recall.posted_date or "unknown") + ")",
                "official_url": recall.official_url,
                "relation_status": "confirmed",
                "detail": (recall.reason_for_recall or "")[:200],
                "event_id": recall.event_id,
            }
        )
    items.sort(key=lambda item: (item["date"] is None, item["date"] or "", item["kind"], item["official_id"]))
    return items


def detail(dataset: Any, device_identifier: str) -> dict[str, Any] | None:
    index = dataset.device_index()
    device = index.device(device_identifier)
    if device is None:
        return None
    application = index.applications.get(device.application_id)
    family = index.families.get(device.family_id) if device.family_id else None
    versions = index.family_versions(device.family_id) if device.family_id else []
    relation_list = index.relations_for(device.device_id)
    confirmed = [relation.to_public() for relation in relation_list if relation.status == "confirmed"]
    # device_has_version is derived from the family hierarchy (same official PMA number) rather than
    # stored: the evidence is identical and the edge is only meaningful on the device page.
    if device.family_id:
        family = index.families.get(device.family_id)
        if family:
            for version in versions:
                confirmed.append(
                    {
                        "relation_id": "rel:derived_version:" + version.official_id,
                        "relation_type": "device_has_version",
                        "status": "confirmed",
                        "status_label_en": STATUS_LABELS_EN["confirmed"],
                        "status_label_zh": STATUS_LABELS_ZH["confirmed"],
                        "source_id": device.device_id,
                        "source_kind": "device",
                        "target_id": version.application_id,
                        "target_kind": "application",
                        "rule": "same_official_pma_number_v1",
                        "evidence": [
                            {
                                "kind": "official_identifier",
                                "field": "pma_number",
                                "value": version.pma_number or "",
                                "official_url": version.official_url,
                                "event_id": version.event_id,
                                "note": None,
                            }
                        ],
                        "snapshot_id": index.snapshot_id,
                        "target_in_snapshot": True,
                        "score": None,
                        "note": "derived from the family's official PMA number",
                    }
                )
    candidates = [relation.to_public() for relation in relation_list if relation.status == "candidate"]
    recalls: list[Any] = []
    for version in [application] + list(versions):
        if version is not None:
            recalls.extend(index.recalls_referencing(version.application_id))
    recalls.sort(key=lambda item: (item.initiated_date is None, item.initiated_date or ""), reverse=True)
    candidate_recalls = [
        relation.to_public()
        for version in [application] + list(versions)
        if version is not None
        for relation in index.relations_for(version.application_id)
        if relation.relation_type == "candidate_recall_application" and relation.status == "candidate"
    ]
    evidence = []
    if application is not None:
        evidence.append({"label": "Application record", "official_url": application.official_url, "official_id": application.official_id})
    for recall in recalls[:10]:
        evidence.append({"label": "Recall record", "official_url": recall.official_url, "official_id": recall.official_id})
    return {
        "device": device.to_public(),
        "counts": _device_counts(index, device),
        "identity": {
            "basis": device.identity_basis,
            "basis_text": device.to_public()["identity_basis_text"],
            "what_this_page_represents": (
                "a specific device identified from its own FDA application"
                if device.identity_basis == "510k_clearance"
                else "a device identified from its own FDA PMA approval; its supplements are versions of this device"
            ),
            "not_impersonating_fda": "MedRadar identifiers are internal; the FDA identifier is shown separately and links to the official page",
            "name_is_not_unique": True,
        },
        "applicant": applicant_block(dataset, device.applicant_name),
        "application": application.to_public() if application else None,
        "versions": [version.to_public() for version in versions],
        "family": family.to_public() if family else None,
        "timeline": _timeline(dataset, index, device, versions, recalls),
        "relations": {
            "confirmed": confirmed,
            "candidate": candidates,
            "relation_types": RELATION_TYPES,
            "status_labels": {"en": STATUS_LABELS_EN, "zh": STATUS_LABELS_ZH},
        },
        "related_recalls": {
            "confirmed": [recall.to_public() for recall in recalls],
            "candidate": candidate_recalls,
            "note": "A recall is linked only through its official K-number field. Recalls without that field are listed in the unlinked browser, not attached here.",
        },
        "evidence": evidence,
        "disclosures": {
            "confirmed_relations_rule": "official identifier or official record field only",
            "predicate_relations": NOT_MODELLED["application_references_predicate"],
            "family_basis": family.basis if family else "no evidenced product family for this device",
            "candidates_not_established": "candidate relations are hypotheses; the product never presents them as established",
        },
        "definitions": DEFINITIONS,
        "snapshot": dataset.snapshot_ref(),
    }


def family_payload(dataset: Any, family_identifier: str) -> dict[str, Any] | None:
    index = dataset.device_index()
    family = index.family(family_identifier)
    if family is None:
        return None
    versions = index.family_versions(family_identifier)
    device = index.devices.get(family.device_id) if family.device_id else None
    application = index.applications.get(family.application_id) if family.application_id else None
    recalls: list[Any] = []
    for version in versions:
        recalls.extend(index.recalls_referencing(version.application_id))
    if application is not None:
        recalls.extend(index.recalls_referencing(application.application_id))
    return {
        "family": family.to_public(),
        "device": device.to_public() if device else None,
        "application": application.to_public() if application else None,
        "versions": [version.to_public() for version in versions],
        "versions_count": len(versions),
        "related_recalls": [recall.to_public() for recall in recalls],
        "applicant": applicant_block(dataset, family.applicant_name),
        "disclosures": {
            "basis": family.basis,
            "original_missing": (
                "the original PMA approval is not in this snapshot, so the family is shown from its supplements only"
                if not family.original_in_snapshot
                else None
            ),
            "not_a_commercial_brand_family": "the family is the FDA application hierarchy, not proof that the devices are one commercial product line",
            "causal_caution": "supplements are ordered by decision date; a later supplement does not cause a later event such as a recall",
        },
        "timeline": _timeline(dataset, index, device, versions, recalls) if device is not None else [],
        "definitions": DEFINITIONS,
        "snapshot": dataset.snapshot_ref(),
    }


def unlinked_recalls(dataset: Any, *, page: int = 1, page_size: int = 25) -> dict[str, Any]:
    index = dataset.device_index()
    rows = []
    for recall in index.recalls.values():
        if index.recall_k_references.get(recall.event_id):
            continue
        external = index.external_k_references.get(recall.event_id)
        rows.append(
            {
                "recall": recall.to_public(),
                "reason": (
                    "references an application that is not in this snapshot (official K number recorded)"
                    if external
                    else "the record has no official K-number reference, so no application can be linked"
                ),
                "official_url": recall.official_url,
            }
        )
    rows.sort(key=lambda item: (item["recall"]["initiated_date"] is None, item["recall"]["initiated_date"] or ""), reverse=True)
    total = len(rows)
    page_size = max(1, min(int(page_size), 100))
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(int(page), total_pages))
    start = (page - 1) * page_size
    return {
        "items": rows[start:start + page_size],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "note": "These records are not deleted and not guessed. They are the honest unlinked set.",
        "definitions": DEFINITIONS,
    }


def devices_csv(dataset: Any, rows: Sequence[dict[str, Any]]) -> str:
    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(
        [
            "device_id",
            "identity_basis",
            "kind",
            "official_id",
            "name",
            "applicant_name",
            "organization_key",
            "organization_display",
            "product_code",
            "category",
            "device_class",
            "first_event_date",
            "applications",
            "versions",
            "recalls",
            "confirmed_relations",
            "candidate_relations",
            "family_id",
            "official_url",
            "snapshot_id",
        ]
    )
    for row in rows:
        device = row["device"]
        writer.writerow(
            [
                device.device_id,
                device.identity_basis,
                device.kind,
                device.official_id,
                device.name,
                device.applicant_name,
                device.organization_key or "",
                row.get("organization_display") or "",
                device.product_code or "",
                device.category_label or "",
                device.device_class or "",
                device.first_event_date or "",
                row["counts"]["applications"],
                row["counts"]["versions"],
                row["counts"]["recalls"],
                row["counts"]["confirmed_relations"],
                row["counts"]["candidate_relations"],
                device.family_id or "",
                "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/" + ("cfpmn/pmn.cfm?ID=" if device.kind == "510k" else "cfpma/pma.cfm?id=") + device.official_id,
                dataset.snapshot_id,
            ]
        )
    return buffer.getvalue()


def device_markdown(dataset: Any, device_identifier: str) -> str | None:
    payload = detail(dataset, device_identifier)
    if payload is None:
        return None
    device = payload["device"]
    lines = []
    lines.append("# MedRadar device brief: " + device["name"])
    lines.append("")
    lines.append("- Device identity: " + device["device_id"] + " (" + payload["identity"]["basis_text"] + ")")
    lines.append("- FDA identifier: " + device["official_id"] + " - " + payload["application"]["official_url"])
    lines.append("- Applicant (as recorded): " + device["applicant_name"])
    applicant = payload["applicant"]
    lines.append(
        "- Registry attribution: "
        + (applicant.get("organization_display") or "not attributed")
        + " (verification: "
        + str(applicant.get("verification"))
        + ")"
    )
    lines.append("- Product code: " + str(device.get("product_code") or "-") + " / category: " + str(device.get("category_label") or "-"))
    lines.append("- Snapshot: " + str(payload["snapshot"]["id"]))
    lines.append("")
    lines.append("> " + payload["identity"]["basis_text"] + ". " + payload["identity"]["not_impersonating_fda"] + ".")
    lines.append("")
    lines.append("## Regulatory timeline (chronological; ordering is not causation)")
    lines.append("")
    for item in payload["timeline"]:
        lines.append(
            "- " + str(item["date"] or "undated") + " - " + item["kind_label"] + " - " + item["official_id"] + " - " + (item["detail"] or "") + " - " + str(item["official_url"])
        )
    lines.append("")
    lines.append("## Confirmed relations (" + str(len(payload["relations"]["confirmed"])) + ")")
    lines.append("")
    for relation in payload["relations"]["confirmed"]:
        lines.append("- " + relation["relation_type"] + " -> " + relation["target_id"] + " [" + relation["rule"] + "]")
    lines.append("")
    lines.append("## Candidate relations (not established) (" + str(len(payload["relations"]["candidate"])) + ")")
    lines.append("")
    for relation in payload["relations"]["candidate"]:
        lines.append("- " + relation["relation_type"] + " -> " + relation["target_id"] + " [" + relation["rule"] + ", score " + str(relation.get("score")) + "]")
    lines.append("")
    lines.append("## Related recalls (official K-number reference only)")
    lines.append("")
    for recall in payload["related_recalls"]["confirmed"]:
        lines.append("- " + str(recall["initiated_date"] or "undated") + " - " + recall["official_id"] + " - " + str(recall["reason_for_recall"] or "")[:160] + " - " + recall["official_url"])
    return "\n".join(lines)
