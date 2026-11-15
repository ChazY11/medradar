"""Organization identity, applicant attribution and organization search.

The registry (medradar/product/identity/organizations.json) is the reviewed source of truth for
which applicant spellings belong to which tracked organization. This module loads it, enforces its
integrity rules, derives each decision's *verification status*, and exposes the attribution
function the rest of the product uses.

Rules enforced here (see docs/product/DATA_CONTRACT.md section 4):

* exact match only, after Unicode NFC + casefold + whitespace collapse;
* the verbatim applicant string is preserved for evidence;
* one applicant string cannot be accepted by two organizations (load-time error);
* one string cannot be both accepted and rejected (load-time error);
* unattributed strings stay unattributed; nothing is guessed.

Verification status (PRODUCT-002)
---------------------------------
The registry's historical flag (curated | pending_review) is NOT a verification status. Each
decision also carries a *status* derived from an explicit rule or an explicit evidence record:

  proposed -> rule_verified -> evidence_verified -> human_reviewed

and the negative statuses rejected / unresolved. "Curated" in the product metrics means only
evidence_verified or human_reviewed; a deterministic name rule is reported separately and is never
presented as review. See medradar/product/attribution/status.py for the definitions.

A review-ledger overlay (medradar.product.review) can override any decision; the overlay is applied
here so every consumer of the registry - the API, the exports, the metrics - sees the same
effective mapping.
"""
from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

from .attribution import ownership as ownership_module
from .attribution import status as status_module
from .attribution.status import (
    CURATED_STATUSES,
    EVIDENCE_VERIFIED,
    EvidenceRef,
    HUMAN_REVIEWED,
    PROPOSED,
    REJECTED,
    RULE_LEXICAL_EQUIVALENCE,
    RULE_NAME_IDENTITY,
    RULE_OWNERSHIP_EVIDENCE,
    RULE_REGISTRY_AUTHORING,
    RULE_MACHINE_PROPOSAL,
    UNRESOLVED,
    coerce_evidence,
    lexical_key,
    name_identity_rule,
)

REGISTRY_PATH = Path(__file__).with_name("identity") / "organizations.json"

BASIS_LABELS = {
    "legal_name": "legal name",
    "brand": "brand name",
    "subsidiary": "subsidiary or operating entity",
    "historical_name": "historical name",
    "division": "division",
}


def normalise_applicant(value: str) -> str:
    text = unicodedata.normalize("NFC", value or "")
    return " ".join(text.casefold().split())


@dataclass(frozen=True)
class Decision:
    applicant_name: str
    organization_key: str
    basis: str
    review: str
    source: str
    status: str = PROPOSED
    rule: str | None = None
    rule_detail: str | None = None
    evidence: tuple[EvidenceRef, ...] = ()
    provenance: str = "registry_authoring"
    decision_uid: str | None = None
    reviewer: str | None = None
    reviewer_kind: str | None = None

    @property
    def verified(self) -> bool:
        return self.status in CURATED_STATUSES

    @property
    def rule_verified(self) -> bool:
        return self.status == status_module.RULE_VERIFIED

    @property
    def provisional(self) -> bool:
        return self.status in status_module.PROVISIONAL_STATUSES

    def to_public(self) -> dict[str, Any]:
        return {
            "applicant_name": self.applicant_name,
            "organization_key": self.organization_key,
            "basis": self.basis,
            "basis_label": BASIS_LABELS.get(self.basis, self.basis),
            "registry_review_legacy": self.review,
            "status": self.status,
            "status_label_en": status_module.STATUS_LABELS_EN.get(self.status, self.status),
            "status_label_zh": status_module.STATUS_LABELS_ZH.get(self.status, self.status),
            "verified": self.verified,
            "rule_verified": self.rule_verified,
            "provisional": self.provisional,
            "rule": self.rule,
            "rule_detail": self.rule_detail,
            "provenance": self.provenance,
            "source": self.source,
            "evidence": [item.to_public() for item in self.evidence],
            "decision_uid": self.decision_uid,
            "reviewer": self.reviewer,
            "reviewer_kind": self.reviewer_kind,
            "review_required": self.status == PROPOSED,
        }


@dataclass(frozen=True)
class Rejection:
    applicant_name: str
    organization_key: str
    reason: str
    status: str = REJECTED
    reviewer: str | None = None
    reviewer_kind: str | None = None
    decision_uid: str | None = None


@dataclass(frozen=True)
class Organization:
    key: str
    display_name: str
    display_name_zh: str | None
    legal_name: str | None
    ticker: str | None
    exchange: str | None
    country: str | None
    country_name: str | None
    organization_type: str
    featured: bool
    description: str
    brands: tuple[str, ...]
    registry_review: str
    metadata_source: str
    ownership_note: str
    accept_exact: tuple[Decision, ...]
    reject_exact: tuple[Rejection, ...]
    search_tokens: tuple[str, ...]

    def to_public(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "display_name": self.display_name,
            "display_name_zh": self.display_name_zh,
            "legal_name": self.legal_name,
            "ticker": self.ticker,
            "exchange": self.exchange,
            "country": self.country,
            "country_name": self.country_name,
            "organization_type": self.organization_type,
            "featured": self.featured,
            "description": self.description,
            "brands": list(self.brands),
            "registry_review": self.registry_review,
            "metadata_source": self.metadata_source,
            "ownership_note": self.ownership_note,
            "search_tokens": list(self.search_tokens),
        }


@dataclass
class Registry:
    updated_at: str
    matching_rule: str
    organizations: tuple[Organization, ...]
    by_key: dict[str, Organization]
    decisions: dict[str, Decision]
    rejections: dict[str, Rejection]
    accepted_spellings_by_org: dict[str, tuple[Decision, ...]]
    warnings: list[str] = field(default_factory=list)
    overlay_applied: int = 0
    unresolved_strings: dict[str, str] = field(default_factory=dict)

    def organization(self, key: str) -> Organization | None:
        return self.by_key.get(key)

    def decide(self, applicant_name: str) -> tuple[Decision | None, Rejection | None]:
        normalised = normalise_applicant(applicant_name)
        return self.decisions.get(normalised), self.rejections.get(normalised)

    def all_keys(self) -> list[str]:
        return [org.key for org in self.organizations]

    def status_counts(self) -> dict[str, int]:
        counts = {name: 0 for name in status_module.DECISION_STATUSES}
        for decision in self.decisions.values():
            counts[decision.status] = counts.get(decision.status, 0) + 1
        counts[REJECTED] += len(self.rejections)
        return counts


def _derive_status(decision: Decision, organization: Organization) -> Decision:
    """Derive the verification status of one accepted spelling from explicit fields only."""
    basis = decision.basis
    if decision.review == "pending_review":
        return Decision(
            applicant_name=decision.applicant_name,
            organization_key=decision.organization_key,
            basis=basis,
            review=decision.review,
            source=decision.source,
            status=PROPOSED,
            rule=RULE_MACHINE_PROPOSAL,
            rule_detail="proposed by the collection-scope token rule; no review recorded",
            provenance="machine_proposal",
        )
    if decision.review == "curated" and basis in ("legal_name", "brand"):
        result = name_identity_rule(
            decision.applicant_name,
            legal_names=[organization.legal_name or ""],
            brands=organization.brands or (organization.display_name,),
        )
        if result.ok:
            return Decision(
                applicant_name=decision.applicant_name,
                organization_key=decision.organization_key,
                basis=basis,
                review=decision.review,
                source=decision.source,
                status=status_module.RULE_VERIFIED,
                rule=result.rule,
                rule_detail=result.detail,
                provenance="name_identity_rule",
            )
        return Decision(
            applicant_name=decision.applicant_name,
            organization_key=decision.organization_key,
            basis=basis,
            review=decision.review,
            source=decision.source,
            status=PROPOSED,
            rule=RULE_REGISTRY_AUTHORING,
            rule_detail="authored with the registry but the deterministic name-identity rule does not confirm it: " + result.detail,
            provenance="registry_authoring",
        )
    # subsidiary / division / historical_name: acceptance is a corporate relation, which needs
    # evidence. Without an evidence record it is a working assumption.
    return Decision(
        applicant_name=decision.applicant_name,
        organization_key=decision.organization_key,
        basis=basis,
        review=decision.review,
        source=decision.source,
        status=PROPOSED,
        rule=RULE_REGISTRY_AUTHORING,
        rule_detail="corporate relation authored with the registry; no independent evidence recorded",
        provenance="registry_authoring",
    )


def _upgrade_with_evidence(decision: Decision, organization: Organization) -> Decision:
    """Upgrade to evidence_verified when a verified ownership relation covers the spelling."""
    if decision.status in (REJECTED, UNRESOLVED):
        return decision
    relations = ownership_module.ownership().verified_for(organization.key, decision.applicant_name)
    if not relations:
        return decision
    evidence: list[EvidenceRef] = []
    for relation in relations:
        evidence.extend(relation.evidence)
    return Decision(
        applicant_name=decision.applicant_name,
        organization_key=decision.organization_key,
        basis=decision.basis,
        review=decision.review,
        source=decision.source,
        status=EVIDENCE_VERIFIED,
        rule=RULE_OWNERSHIP_EVIDENCE,
        rule_detail="covered by verified ownership relation(s): "
        + ", ".join(relation.relation_id for relation in relations),
        evidence=tuple(evidence),
        provenance="ownership_evidence",
        decision_uid=decision.decision_uid,
        reviewer=relations[0].reviewer,
        reviewer_kind=relations[0].reviewer_kind,
    )


def _apply_lexical_equivalence(decisions: list[Decision]) -> list[Decision]:
    """Promote proposals that differ from a stronger sibling only by case/punctuation/legal form."""
    stronger_keys: dict[str, str] = {}
    for decision in decisions:
        if decision.status in (status_module.RULE_VERIFIED, EVIDENCE_VERIFIED, HUMAN_REVIEWED):
            stronger_keys.setdefault(lexical_key(decision.applicant_name), decision.applicant_name)
    out: list[Decision] = []
    for decision in decisions:
        if decision.status != PROPOSED:
            out.append(decision)
            continue
        key = lexical_key(decision.applicant_name)
        sibling = stronger_keys.get(key)
        if sibling and normalise_applicant(sibling) != normalise_applicant(decision.applicant_name):
            out.append(
                Decision(
                    applicant_name=decision.applicant_name,
                    organization_key=decision.organization_key,
                    basis=decision.basis,
                    review=decision.review,
                    source=decision.source,
                    status=status_module.RULE_VERIFIED,
                    rule=RULE_LEXICAL_EQUIVALENCE,
                    rule_detail="lexically equivalent to the verified spelling " + repr(sibling) + " (case/punctuation/legal-form suffix only)",
                    provenance="lexical_equivalence_rule",
                )
            )
            continue
        out.append(decision)
    return out


def _build_registry(payload: dict[str, Any], overlay: Mapping[str, Mapping[str, Any]] | None = None) -> Registry:
    organizations: list[Organization] = []
    decisions: dict[str, Decision] = {}
    rejections: dict[str, Rejection] = {}
    accepted_by_org: dict[str, list[Decision]] = {}
    warnings: list[str] = []
    overlay = overlay or {}
    overlay_applied = 0
    unresolved_strings: dict[str, str] = {}

    for raw in payload.get("organizations") or []:
        key = str(raw["key"]).strip()
        provisional: list[Decision] = []
        for item in raw.get("accept_exact") or []:
            value = str(item["value"]).strip()
            if not value:
                continue
            normalised = normalise_applicant(value)
            base = Decision(
                applicant_name=value,
                organization_key=key,
                basis=str(item.get("basis") or "brand"),
                review=str(item.get("review") or "pending_review"),
                source=str(item.get("source") or ""),
            )
            existing = decisions.get(normalised)
            if existing is not None:
                if existing.organization_key != key:
                    raise ValueError(
                        "applicant spelling claimed by two organizations: "
                        + repr(value)
                        + " -> "
                        + existing.organization_key
                        + " and "
                        + key
                    )
                warnings.append("duplicate applicant spelling inside " + key + ": " + repr(value))
                continue
            provisional.append(base)
        reject: list[Rejection] = []
        for item in raw.get("reject_exact") or []:
            value = str(item["value"]).strip()
            if not value:
                continue
            normalised = normalise_applicant(value)
            if normalised in decisions:
                raise ValueError("applicant spelling both accepted and rejected: " + repr(value))
            rejection = Rejection(
                applicant_name=value,
                organization_key=key,
                reason=str(item.get("reason") or "rejected by registry review"),
            )
            rejections[normalised] = rejection
            reject.append(rejection)
        accepted_by_org[key] = provisional
        organizations.append(
            Organization(
                key=key,
                display_name=str(raw.get("display_name") or key),
                display_name_zh=raw.get("display_name_zh"),
                legal_name=raw.get("legal_name"),
                ticker=raw.get("ticker"),
                exchange=raw.get("exchange"),
                country=raw.get("country"),
                country_name=raw.get("country_name"),
                organization_type=str(raw.get("organization_type") or "unknown"),
                featured=bool(raw.get("featured")),
                description=str(raw.get("description") or ""),
                brands=tuple(raw.get("brands") or [raw.get("display_name") or key]),
                registry_review=str(raw.get("registry_review") or "pending_review"),
                metadata_source=str(raw.get("metadata_source") or ""),
                ownership_note=str(raw.get("ownership_note") or ""),
                accept_exact=(),
                reject_exact=tuple(reject),
                search_tokens=tuple(raw.get("search_tokens") or ()),
            )
        )

    organization_by_key = {org.key: org for org in organizations}

    # pass 1: derive a status from explicit registry fields and verified ownership evidence
    derived: list[Decision] = []
    for raw in payload.get("organizations") or []:
        key = str(raw["key"]).strip()
        organization = organization_by_key[key]
        for base in accepted_by_org.get(key, []):
            decision = _derive_status(base, organization)
            decision = _upgrade_with_evidence(decision, organization)
            derived.append(decision)

    # pass 2: lexical-equivalence promotion inside each organization
    promoted: list[Decision] = []
    for key in {decision.organization_key for decision in derived}:
        promoted.extend(_apply_lexical_equivalence([item for item in derived if item.organization_key == key]))

    # pass 3: review-ledger overlay (highest precedence: a recorded decision)
    final: list[Decision] = []
    accepted_final: dict[str, list[Decision]] = {}
    for decision in promoted:
        normalised = normalise_applicant(decision.applicant_name)
        override = overlay.get(normalised)
        if override is not None:
            overlay_applied += 1
            decision = _apply_overlay(decision, override)
        final.append(decision)
        accepted_final.setdefault(decision.organization_key, []).append(decision)

    for decision in final:
        decisions[normalise_applicant(decision.applicant_name)] = decision

    # overlay rejections/unresolved for strings that were previously unattributed
    for normalised, override in overlay.items():
        if normalised in decisions or normalised in rejections:
            continue
        action = str(override.get("action") or "")
        organization_key = override.get("organization_key")
        applicant_name = str(override.get("applicant_name") or normalised)
        if action == "reject":
            rejections[normalised] = Rejection(
                applicant_name=applicant_name,
                organization_key=str(organization_key or ""),
                reason=str(override.get("note") or "rejected by identity review"),
                reviewer=override.get("reviewer"),
                reviewer_kind=override.get("reviewer_kind"),
                decision_uid=override.get("decision_uid"),
            )
        elif action == "unresolved":
            unresolved_strings[normalised] = str(override.get("note") or "reviewed and not determinable")
            overlay_applied += 1
        elif action in ("approve", "reassign") and organization_key in organization_by_key:
            decision = Decision(
                applicant_name=applicant_name,
                organization_key=str(organization_key),
                basis="review_decision",
                review="curated",
                source="review_ledger",
                status=str(override.get("status") or HUMAN_REVIEWED),
                rule="review_ledger_v1",
                rule_detail="recorded in the internal identity review ledger",
                evidence=coerce_evidence(override.get("evidence")),
                provenance="review_ledger",
                decision_uid=override.get("decision_uid"),
                reviewer=override.get("reviewer"),
                reviewer_kind=override.get("reviewer_kind"),
            )
            decisions[normalised] = decision
            accepted_final.setdefault(str(organization_key), []).append(decision)
            overlay_applied += 1

    pending = sum(1 for org in organizations if org.registry_review == "pending_review")
    if pending:
        warnings.append(str(pending) + " organization(s) have pending-review registry metadata and are labelled provisional in the UI")

    # rebuild organizations with their final decision tuples
    organizations_out = []
    for organization in organizations:
        organizations_out.append(
            Organization(
                key=organization.key,
                display_name=organization.display_name,
                display_name_zh=organization.display_name_zh,
                legal_name=organization.legal_name,
                ticker=organization.ticker,
                exchange=organization.exchange,
                country=organization.country,
                country_name=organization.country_name,
                organization_type=organization.organization_type,
                featured=organization.featured,
                description=organization.description,
                brands=organization.brands,
                registry_review=organization.registry_review,
                metadata_source=organization.metadata_source,
                ownership_note=organization.ownership_note,
                accept_exact=tuple(accepted_final.get(organization.key, [])),
                reject_exact=organization.reject_exact,
                search_tokens=organization.search_tokens,
            )
        )

    return Registry(
        updated_at=str(payload.get("updated_at") or ""),
        matching_rule=str(payload.get("matching_rule") or ""),
        organizations=tuple(organizations_out),
        by_key={org.key: org for org in organizations_out},
        decisions=decisions,
        rejections=rejections,
        accepted_spellings_by_org={key: tuple(values) for key, values in accepted_final.items()},
        warnings=warnings,
        overlay_applied=overlay_applied,
        unresolved_strings=unresolved_strings,
    )


def _overlay_status(override: Mapping[str, Any]) -> str:
    """A ledger overlay cannot claim human review without a human authority.

    The store refuses to write human_reviewed, but the overlay is also built from an imported file,
    so the rule is enforced here too: without reviewer_kind="human" the claim degrades to
    evidence_verified (when evidence exists) or unresolved. Nothing is silently upgraded.
    """
    status = str(override.get("status") or HUMAN_REVIEWED)
    if status == HUMAN_REVIEWED and str(override.get("reviewer_kind") or "") != "human":
        return EVIDENCE_VERIFIED if coerce_evidence(override.get("evidence")) else UNRESOLVED
    return status


def _apply_overlay(decision: Decision, override: Mapping[str, Any]) -> Decision:
    action = str(override.get("action") or "")
    status = str(override.get("status") or "")
    organization_key = override.get("organization_key") or decision.organization_key
    if action == "reject":
        return Decision(
            applicant_name=decision.applicant_name,
            organization_key=str(organization_key),
            basis=decision.basis,
            review="rejected",
            source="review_ledger",
            status=REJECTED,
            rule="review_ledger_v1",
            rule_detail="rejected in the internal identity review ledger",
            evidence=coerce_evidence(override.get("evidence")),
            provenance="review_ledger",
            decision_uid=override.get("decision_uid"),
            reviewer=override.get("reviewer"),
            reviewer_kind=override.get("reviewer_kind"),
        )
    return Decision(
        applicant_name=decision.applicant_name,
        organization_key=str(organization_key),
        basis=str(override.get("basis") or decision.basis),
        review="curated" if status in (EVIDENCE_VERIFIED, HUMAN_REVIEWED) else decision.review,
        source="review_ledger",
        status=_overlay_status(override),
        rule="review_ledger_v1",
        rule_detail="recorded in the internal identity review ledger",
        evidence=coerce_evidence(override.get("evidence")),
        provenance="review_ledger",
        decision_uid=override.get("decision_uid"),
        reviewer=override.get("reviewer"),
        reviewer_kind=override.get("reviewer_kind"),
    )


@lru_cache(maxsize=1)
def _payload() -> dict[str, Any]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=2)
def registry() -> Registry:
    return _build_registry(_payload())


def registry_with_overlay(overlay_items: tuple) -> Registry:
    """Registry with review-ledger decisions applied.

    overlay_items is a hashable tuple of (applicant_key, organization_key, action, status,
    reviewer, reviewer_kind, evidence_fingerprint, decision_uid, note) so it can be memoised.
    """
    if not overlay_items:
        return registry()
    overlay: dict[str, dict[str, Any]] = {}
    for item in overlay_items:
        (
            applicant_key,
            organization_key,
            action,
            status,
            reviewer,
            reviewer_kind,
            evidence_json,
            decision_uid,
            note,
            applicant_name,
        ) = item
        overlay[applicant_key] = {
            "organization_key": organization_key,
            "action": action,
            "status": status,
            "reviewer": reviewer,
            "reviewer_kind": reviewer_kind,
            "evidence": json.loads(evidence_json) if evidence_json else None,
            "decision_uid": decision_uid,
            "note": note,
            "applicant_name": applicant_name,
        }
    return _build_registry(_payload(), overlay)


# --------------------------------------------------------------------------- search
MATCH_RANK = {
    "legal_name": 0,
    "brand": 1,
    "ticker": 2,
    "alias": 3,
    "substring": 4,
    "applicant": 5,
}

MATCH_FIELD_ORDER = tuple(MATCH_RANK)

SHORT_QUERY_CHARS = 4


@dataclass
class SearchHit:
    organization: Organization
    match_field: str
    match_value: str
    rank: int


def search_organizations(
    query: str,
    applicant_names: Iterable[str],
    active_registry: Registry | None = None,
) -> tuple[list[SearchHit], list[str]]:
    """Rank tracked organizations for a query, with explicit match precedence.

    Precedence: exact legal name, exact brand, exact ticker, exact or prefix alias / brand,
    substring of the organization's own names, then substring of an attributed applicant name.

    Substring matching over *applicant strings* is disabled for very short queries because a
    two-letter query otherwise matches unrelated legal names. That is a deliberate anti-noise
    rule, documented in the API contract.
    """
    data = active_registry or registry()
    needle = normalise_applicant(query)
    if not needle:
        return [], []
    allow_applicant_substring = len(needle) >= SHORT_QUERY_CHARS
    hits: list[SearchHit] = []
    matched_applicants: list[str] = []
    for org in data.organizations:
        best: SearchHit | None = None

        def consider(field: str, value: str) -> None:
            nonlocal best
            rank = MATCH_RANK[field]
            if best is None or rank < best.rank:
                best = SearchHit(organization=org, match_field=field, match_value=value, rank=rank)

        if org.legal_name and normalise_applicant(org.legal_name) == needle:
            consider("legal_name", org.legal_name)
        if normalise_applicant(org.display_name) == needle:
            consider("brand", org.display_name)
        if org.display_name_zh and normalise_applicant(org.display_name_zh) == needle:
            consider("brand", org.display_name_zh)
        if org.ticker and org.ticker.casefold() == needle:
            consider("ticker", org.ticker)

        if best is None:
            for decision in org.accept_exact:
                if normalise_applicant(decision.applicant_name) == needle:
                    consider("alias", decision.applicant_name)
                    break
        if best is None:
            own_names = [org.display_name, org.legal_name or "", *(org.brands or ())]
            for value in own_names:
                if value and normalise_applicant(value).startswith(needle):
                    consider("alias", value)
                    break
        if best is None:
            own_names = [org.display_name, org.legal_name or "", org.display_name_zh or "", *(org.brands or ())]
            for value in own_names:
                if value and needle in normalise_applicant(value):
                    consider("substring", value)
                    break
        if best is None and allow_applicant_substring:
            for decision in org.accept_exact:
                if needle in normalise_applicant(decision.applicant_name):
                    consider("applicant", decision.applicant_name)
                    break
        if best is not None:
            hits.append(best)
    hits.sort(key=lambda hit: (hit.rank, hit.organization.display_name.casefold()))

    if allow_applicant_substring:
        for name in applicant_names:
            if needle in normalise_applicant(name):
                matched_applicants.append(name)

    attributed = {
        normalise_applicant(decision.applicant_name)
        for hit in hits
        for decision in hit.organization.accept_exact
    }
    applicant_only = [name for name in matched_applicants if normalise_applicant(name) not in attributed]
    return hits, applicant_only