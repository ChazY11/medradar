"""Historical and current ownership relations (who owned what, when, on what evidence).

Three concepts the product must keep apart
------------------------------------------
1. **Original applicant** - the exact string FDA recorded on the record. It is evidence, not an
   interpretation, and every product screen can show it verbatim.
2. **Historical owner at event time** - who controlled the filing entity when the regulatory event
   happened. Only stated where an independent source with an effective date exists; otherwise
   UNKNOWN.
3. **Current group** - which tracked organization the entity belongs to today. This is the
   registry attribution the product counts by default, and it is a *current-group* statement: a
   2010 Covidien record is counted under Medtronic today even though Covidien was an independent
   company in 2010. That difference is never hidden.

The relations live in identity/ownership.json. A relation without independent documentary
evidence stays "unresolved" and is never used to upgrade an attribution status or to claim a
historical owner.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Sequence

from .status import EvidenceRef, coerce_evidence, contains_token_sequence, words

OWNERSHIP_PATH = Path(__file__).with_name("ownership.json")

RELATION_TYPES = (
    "subsidiary",
    "acquired_subsidiary",
    "divested_business_unit",
    "historical_name",
    "joint_venture",
    "brand_transfer",
)

VERIFIED = "evidence_verified"
UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class Relation:
    relation_id: str
    organization_key: str
    entity: str
    relation_type: str
    patterns: tuple[str, ...]
    effective_from: str | None
    effective_to: str | None
    historical_owner_before: str | None
    status: str
    reviewer: str
    reviewer_kind: str
    reviewed_at: str | None
    caveat: str
    notes: tuple[str, ...]
    evidence: tuple[EvidenceRef, ...]

    @property
    def verified(self) -> bool:
        return self.status == VERIFIED

    def matches(self, applicant_name: str) -> bool:
        applicant_words = words(applicant_name)
        for pattern in self.patterns:
            pattern_words = words(pattern)
            if pattern_words and contains_token_sequence(applicant_words, pattern_words):
                return True
        return False

    def to_public(self) -> dict[str, Any]:
        return {
            "relation_id": self.relation_id,
            "organization_key": self.organization_key,
            "entity": self.entity,
            "relation_type": self.relation_type,
            "patterns": list(self.patterns),
            "effective_from": self.effective_from,
            "effective_to": self.effective_to,
            "historical_owner_before": self.historical_owner_before,
            "status": self.status,
            "verified": self.verified,
            "reviewer": self.reviewer,
            "reviewer_kind": self.reviewer_kind,
            "reviewed_at": self.reviewed_at,
            "caveat": self.caveat,
            "notes": list(self.notes),
            "evidence": [item.to_public() for item in self.evidence],
        }


@dataclass(frozen=True)
class Ownership:
    updated_at: str
    note: str
    relations: tuple[Relation, ...]

    def for_organization(self, organization_key: str) -> list[Relation]:
        return [relation for relation in self.relations if relation.organization_key == organization_key]

    def verified_for(self, organization_key: str, applicant_name: str) -> list[Relation]:
        """Verified relations covering this applicant spelling for this organization."""
        return [
            relation
            for relation in self.for_organization(organization_key)
            if relation.verified and relation.matches(applicant_name)
        ]

    def all_for_applicant(self, applicant_name: str) -> list[Relation]:
        return [relation for relation in self.relations if relation.matches(applicant_name)]

    def predecessor_relations(self, organization_key: str) -> list[Relation]:
        """Verified relations that describe a predecessor entity with a verified start date."""
        return [
            relation
            for relation in self.for_organization(organization_key)
            if relation.verified and relation.effective_from
        ]


def _build(document: dict[str, Any]) -> Ownership:
    relations = []
    for raw in document.get("relations") or []:
        relations.append(
            Relation(
                relation_id=str(raw.get("relation_id") or ""),
                organization_key=str(raw.get("organization_key") or ""),
                entity=str(raw.get("entity") or ""),
                relation_type=str(raw.get("relation_type") or "subsidiary"),
                patterns=tuple(str(item) for item in (raw.get("applicant_token_patterns") or [])),
                effective_from=raw.get("effective_from"),
                effective_to=raw.get("effective_to"),
                historical_owner_before=raw.get("historical_owner_before"),
                status=str(raw.get("status") or UNRESOLVED),
                reviewer=str(raw.get("reviewer") or "unknown"),
                reviewer_kind=str(raw.get("reviewer_kind") or "agent"),
                reviewed_at=raw.get("reviewed_at"),
                caveat=str(raw.get("caveat") or ""),
                notes=tuple(str(item) for item in (raw.get("notes") or [])),
                evidence=coerce_evidence(raw.get("evidence")),
            )
        )
    return Ownership(
        updated_at=str(document.get("updated_at") or ""),
        note=str(document.get("note") or ""),
        relations=tuple(relations),
    )


@lru_cache(maxsize=1)
def ownership() -> Ownership:
    if not OWNERSHIP_PATH.is_file():
        return Ownership(updated_at="", note="no ownership relation file", relations=())
    return _build(json.loads(OWNERSHIP_PATH.read_text(encoding="utf-8")))


# ---------------------------------------------------------------------------
# product-facing summaries
# ---------------------------------------------------------------------------

def organization_ownership_summary(organization_key: str, *, events: Sequence[Any] | None = None) -> dict[str, Any]:
    """The ownership block shown on an organization page.

    historical_split is produced only from verified relations with an effective date: it counts
    attributed records filed before and after that date by the predecessor entity. Everything else
    is explicitly UNKNOWN.
    """
    registry = ownership()
    relations = registry.for_organization(organization_key)
    verified = [relation for relation in relations if relation.verified]
    unresolved = [relation for relation in relations if not relation.verified]
    split_rows = []
    events = list(events or [])
    for relation in verified:
        if not relation.effective_from:
            continue
        bucket = {"before": 0, "after": 0, "unknown_date": 0}
        for event in events:
            if not relation.matches(getattr(event, "applicant_name", "") or ""):
                continue
            event_date = getattr(event, "event_date", None)
            if not event_date:
                bucket["unknown_date"] += 1
            elif str(event_date) < relation.effective_from:
                bucket["before"] += 1
            else:
                bucket["after"] += 1
        split_rows.append(
            {
                "relation_id": relation.relation_id,
                "entity": relation.entity,
                "relation_type": relation.relation_type,
                "effective_from": relation.effective_from,
                "historical_owner_before": relation.historical_owner_before,
                "records_before_effective_date": bucket["before"],
                "records_on_or_after_effective_date": bucket["after"],
                "records_without_event_date": bucket["unknown_date"],
                "evidence_count": len(relation.evidence),
                "caveat": relation.caveat,
            }
        )
    covered_patterns = [pattern for relation in verified for pattern in relation.patterns]
    return {
        "schema": "medradar.ownership.v1",
        "updated_at": registry.updated_at,
        "concepts": {
            "original_applicant": "The exact applicant string FDA recorded. Evidence, not interpretation; shown verbatim on every record.",
            "historical_owner": "Who controlled the filing entity when the event happened. Stated only where an independent source with an effective date exists; otherwise UNKNOWN.",
            "current_group": "The tracked organization the entity belongs to today. This is what the product counts by default, and it is a current-group statement, not a historical one.",
        },
        "current_group_policy": "Counts on this page use the CURRENT GROUP: a record is counted under the organization whose registry mapping covers its applicant string today, even when a different company owned the business when the record was filed.",
        "relations": [relation.to_public() for relation in relations],
        "verified_relation_count": len(verified),
        "unresolved_relation_count": len(unresolved),
        "covered_applicant_patterns": covered_patterns,
        "historical_split": split_rows,
        "uncertainty": (
            "Historical group ownership is only stated where an independent filing is cited. "
            + (
                str(len(unresolved))
                + " relation(s) for this organization are UNRESOLVED and are not used to justify any attribution."
                if unresolved
                else "No unresolved relations are recorded for this organization."
            )
        ),
    }


def applicability_note(organization_key: str) -> str:
    summary = organization_ownership_summary(organization_key)
    if summary["verified_relation_count"] == 0:
        return "No verified ownership relation is recorded for this organization: every historical statement about it is UNKNOWN."
    return (
        str(summary["verified_relation_count"])
        + " verified ownership relation(s); "
        + str(summary["unresolved_relation_count"])
        + " unresolved. See the ownership block for dates and sources."
    )


def is_predecessor_applicant(organization_key: str, applicant_name: str) -> bool:
    """True when the applicant string belongs to an acquired/predecessor entity of the group."""
    for relation in ownership().for_organization(organization_key):
        if relation.relation_type in ("acquired_subsidiary", "divested_business_unit", "historical_name", "brand_transfer"):
            if relation.matches(applicant_name):
                return True
    return False


def applies_to(applicant_name: str, patterns: Iterable[str]) -> bool:
    applicant_words = words(applicant_name)
    for pattern in patterns:
        pattern_words = words(pattern)
        if pattern_words and contains_token_sequence(applicant_words, pattern_words):
            return True
    return False
