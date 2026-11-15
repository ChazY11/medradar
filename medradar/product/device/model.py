"""Entities and relations of the device model (PRODUCT-003).

Nothing here is inferred from a name alone. A relation is created only by a documented rule, carries
its evidence (the source field and value that produced it) and its status. The status vocabulary is
the same one the product shows to users:

* confirmed         an official identifier or an official record field establishes the link;
* evidence_supported an official free-text field names the link but not as a structured identifier;
* candidate         a deterministic similarity rule suggests the link; it is NOT established;
* unlinked          no relation; the record stays visible and is counted as unlinked.

In this release the only confirmed device-level relations are the PMA application hierarchy, the
supplement-as-version relation, and a recall's official K-number reference. Candidate relations are
never promoted by the model or by the UI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

RELATION_STATUSES = ("confirmed", "evidence_supported", "candidate", "unlinked")

STATUS_LABELS_EN = {
    "confirmed": "confirmed by an official identifier or record field",
    "evidence_supported": "supported by an official free-text field",
    "candidate": "candidate only - not established",
    "unlinked": "no relation established",
}

STATUS_LABELS_ZH = {
    "confirmed": "由官方标识或字段确认",
    "evidence_supported": "由官方文本字段支持",
    "candidate": "仅为候选，尚未确认",
    "unlinked": "未建立关系",
}

EVENT_KINDS = {
    "510k": "510(k) clearance",
    "pma": "PMA original approval",
    "pma_supplement": "PMA supplement",
    "recall": "Recall",
}


@dataclass(frozen=True)
class EvidenceRef:
    """One concrete piece of evidence: which field, which value, which official page."""

    kind: str                 # "official_identifier" | "record_field" | "similarity_rule"
    field: str                # e.g. "pma_number", "k_numbers", "device_name"
    value: str
    official_url: str | None = None
    event_id: str | None = None
    note: str | None = None

    def to_public(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "field": self.field,
            "value": self.value,
            "official_url": self.official_url,
            "event_id": self.event_id,
            "note": self.note,
        }


@dataclass(frozen=True)
class Application:
    application_id: str
    source_id: str
    official_id: str
    kind: str                       # "510k" | "pma" | "pma_supplement"
    official_url: str
    event_id: str
    applicant_name: str
    organization_key: str | None
    product_code: str | None
    advisory_committee: str | None
    device_name: str | None         # generic/classification name
    trade_name: str | None          # product/brand names as reported by FDA
    decision_date: str | None
    decision_code: str | None
    pma_number: str | None = None
    supplement_number: str | None = None
    supplement_type: str | None = None
    supplement_reason: str | None = None
    parent_application_id: str | None = None

    @property
    def is_supplement(self) -> bool:
        return self.kind == "pma_supplement"

    @property
    def display_name(self) -> str:
        return (self.trade_name or self.device_name or self.official_id).strip()

    def to_public(self) -> dict[str, Any]:
        return {
            "application_id": self.application_id,
            "source_id": self.source_id,
            "official_id": self.official_id,
            "kind": self.kind,
            "kind_label": EVENT_KINDS.get(self.kind, self.kind),
            "official_url": self.official_url,
            "event_id": self.event_id,
            "applicant_name": self.applicant_name,
            "organization_key": self.organization_key,
            "product_code": self.product_code,
            "advisory_committee": self.advisory_committee,
            "device_name": self.device_name,
            "trade_name": self.trade_name,
            "decision_date": self.decision_date,
            "decision_code": self.decision_code,
            "pma_number": self.pma_number,
            "supplement_number": self.supplement_number,
            "supplement_type": self.supplement_type,
            "supplement_reason": self.supplement_reason,
            "parent_application_id": self.parent_application_id,
        }


@dataclass(frozen=True)
class DeviceIdentity:
    """A device MedRadar can identify from an official application.

    identity_basis says what the identification rests on. "510k_clearance" means the device model
    cleared by that K number; "pma_approval" means the device approved under that PMA number (its
    supplements are versions, not new devices). No identity is created for a recall record alone.
    """

    device_id: str
    identity_basis: str
    application_id: str
    kind: str
    official_id: str
    name: str
    applicant_name: str
    organization_key: str | None
    product_code: str | None
    category_id: str | None
    category_label: str | None
    device_class: str | None
    first_event_date: str | None
    application_ids: tuple[str, ...] = ()
    models: tuple[str, ...] = ()
    family_id: str | None = None
    record_count: int = 0

    def to_public(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "identity_basis": self.identity_basis,
            "identity_basis_text": {
                "510k_clearance": "identified by the FDA 510(k) clearance that cleared this device model",
                "pma_approval": "identified by the FDA PMA approval (supplements are versions of this device, not new devices)",
            }.get(self.identity_basis, self.identity_basis),
            "application_id": self.application_id,
            "kind": self.kind,
            "official_id": self.official_id,
            "name": self.name,
            "applicant_name": self.applicant_name,
            "organization_key": self.organization_key,
            "product_code": self.product_code,
            "category_id": self.category_id,
            "category_label": self.category_label,
            "device_class": self.device_class,
            "first_event_date": self.first_event_date,
            "application_ids": list(self.application_ids),
            "models": list(self.models),
            "family_id": self.family_id,
            "record_count": self.record_count,
        }


@dataclass(frozen=True)
class ProductFamily:
    family_id: str
    kind: str                     # "pma_application"
    name: str
    organization_key: str | None
    applicant_name: str
    device_id: str | None          # the device identity the family belongs to (None when original missing)
    application_id: str | None
    version_application_ids: tuple[str, ...]
    supplement_count: int
    first_event_date: str | None
    last_event_date: str | None
    models: tuple[str, ...]
    original_in_snapshot: bool
    basis: str

    def to_public(self) -> dict[str, Any]:
        return {
            "family_id": self.family_id,
            "kind": self.kind,
            "name": self.name,
            "organization_key": self.organization_key,
            "applicant_name": self.applicant_name,
            "device_id": self.device_id,
            "application_id": self.application_id,
            "version_application_ids": list(self.version_application_ids),
            "supplement_count": self.supplement_count,
            "first_event_date": self.first_event_date,
            "last_event_date": self.last_event_date,
            "models": list(self.models),
            "original_in_snapshot": self.original_in_snapshot,
            "basis": self.basis,
        }


@dataclass(frozen=True)
class DeviceRelation:
    relation_id: str
    relation_type: str
    status: str
    source_id: str
    source_kind: str
    target_id: str
    target_kind: str
    rule: str
    evidence: tuple[EvidenceRef, ...]
    snapshot_id: str
    target_in_snapshot: bool = True
    score: float | None = None
    note: str | None = None

    def to_public(self) -> dict[str, Any]:
        return {
            "relation_id": self.relation_id,
            "relation_type": self.relation_type,
            "status": self.status,
            "status_label_en": STATUS_LABELS_EN.get(self.status, self.status),
            "status_label_zh": STATUS_LABELS_ZH.get(self.status, self.status),
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "target_id": self.target_id,
            "target_kind": self.target_kind,
            "rule": self.rule,
            "evidence": [item.to_public() for item in self.evidence],
            "snapshot_id": self.snapshot_id,
            "target_in_snapshot": self.target_in_snapshot,
            "score": self.score,
            "note": self.note,
        }


@dataclass(frozen=True)
class RecallRecord:
    event_id: str
    official_id: str
    official_url: str
    applicant_name: str
    organization_key: str | None
    product_code: str | None
    product_description: str | None
    reason_for_recall: str | None
    root_cause: str | None
    recall_status: str | None
    initiated_date: str | None
    posted_date: str | None
    res_event_number: str | None
    product_res_number: str | None
    k_numbers: tuple[str, ...]

    def to_public(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "official_id": self.official_id,
            "official_url": self.official_url,
            "applicant_name": self.applicant_name,
            "organization_key": self.organization_key,
            "product_code": self.product_code,
            "product_description": self.product_description,
            "reason_for_recall": self.reason_for_recall,
            "root_cause": self.root_cause,
            "recall_status": self.recall_status,
            "initiated_date": self.initiated_date,
            "posted_date": self.posted_date,
            "res_event_number": self.res_event_number,
            "product_res_number": self.product_res_number,
            "k_numbers": list(self.k_numbers),
        }
