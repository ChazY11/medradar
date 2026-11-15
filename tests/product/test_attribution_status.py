"""Verification status must never be laundered into a stronger claim.

These tests pin the honesty rules of PRODUCT-002:

* a machine proposal is not a review;
* a deterministic name rule is not independent evidence and not human review;
* evidence-verified requires a recorded documentary source with a URL;
* human_reviewed requires a human reviewer (an agent can never award it to itself);
* the review ledger can override a status, and every published number follows the ledger.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from medradar.product.attribution import status as status_module
from medradar.product.identity import registry, registry_with_overlay


def _decision(applicant: str, organization_key: str | None = None):
    active = registry()
    decision, _rejection = active.decide(applicant)
    if organization_key is not None:
        assert decision is not None, "expected an attributed spelling: " + applicant
        assert decision.organization_key == organization_key, (applicant, decision.organization_key)
    return decision


def test_proposed_spelling_is_not_verified() -> None:
    decision = _decision("Medtronic Cardiac Rhythm Disease Management")
    assert decision is not None
    assert decision.status == status_module.PROPOSED
    assert decision.verified is False
    assert decision.rule == status_module.RULE_MACHINE_PROPOSAL


def test_curated_legal_name_is_rule_verified_not_reviewed() -> None:
    decision = _decision("MEDTRONIC", "medtronic")
    assert decision is not None
    assert decision.status == status_module.RULE_VERIFIED
    assert decision.rule == status_module.RULE_NAME_IDENTITY
    assert decision.verified is False, "a deterministic rule must never count as curated"
    assert decision.reviewer_kind is None


def test_corporate_relation_without_evidence_stays_proposed() -> None:
    decision = _decision("Cochlear Americas", "cochlear")
    assert decision is not None
    assert decision.status == status_module.PROPOSED
    assert decision.verified is False


def test_verified_ownership_evidence_upgrades_status() -> None:
    decision = _decision("COVIDIEN LP", "medtronic")
    assert decision is not None
    assert decision.status == status_module.EVIDENCE_VERIFIED
    assert decision.verified is True
    assert decision.rule == status_module.RULE_OWNERSHIP_EVIDENCE
    assert decision.evidence, "evidence_verified must carry the evidence references"
    assert any(item.url for item in decision.evidence)
    assert decision.reviewer_kind == "agent", "an agent-collected decision stays labelled as an agent decision"


def test_unresolved_relation_does_not_upgrade() -> None:
    # REL-0003 (TYCO HEALTHCARE) is deliberately unresolved: no independent source was collected.
    decision = _decision("TYCO HEALTHCARE", "medtronic")
    assert decision is not None
    assert decision.status != status_module.EVIDENCE_VERIFIED
    assert decision.verified is False


def test_status_vocabulary_is_exposed_with_meanings() -> None:
    counts = registry().status_counts()
    rows = status_module.status_summary(counts)
    ids = [row["status"] for row in rows]
    assert ids == list(status_module.DECISION_STATUSES)
    for row in rows:
        assert row["label_en"] and row["label_zh"] and row["meaning_en"]
    curated = status_module.CURATED_STATUSES
    assert curated == {status_module.EVIDENCE_VERIFIED, status_module.HUMAN_REVIEWED}
    assert status_module.RULE_VERIFIED not in curated


def test_registry_status_counts_are_consistent() -> None:
    active = registry()
    counts = active.status_counts()
    assert sum(counts.values()) == len(active.decisions) + len(active.rejections)
    assert counts[status_module.HUMAN_REVIEWED] == 0, "no human reviewer has recorded a decision in this release"


def test_overlay_cannot_claim_human_review_without_authority() -> None:
    """A ledger file is not a human authority: a human_reviewed claim degrades to evidence_verified."""
    applicant = "Medtronic Neuromodulation"
    evidence = json.dumps([{"evidence_type": "regulator_record", "url": "https://example.org/x"}])
    agent_claim = registry_with_overlay(
        ((applicant.casefold(), "medtronic", "approve", "human_reviewed", "agent:lead", "agent", evidence, "uid-1", "checked", applicant),)
    )
    decision, _ = agent_claim.decide(applicant)
    assert decision is not None
    assert decision.status == status_module.EVIDENCE_VERIFIED, "an agent claim must never survive as human_reviewed"
    assert decision.status != status_module.HUMAN_REVIEWED


def test_lexical_equivalence_is_rule_verified_not_reviewed() -> None:
    # "Philips OY" differs from the accepted "PHILIPS" only by a trailing legal form.
    decision = _decision("Philips OY", "philips")
    assert decision is not None
    assert decision.status == status_module.RULE_VERIFIED
    assert decision.rule == status_module.RULE_LEXICAL_EQUIVALENCE
    assert decision.verified is False, "a lexical rule is not evidence and not human review"


def test_rejected_spelling_never_counts_as_attributed() -> None:
    active = registry()
    rejections = list(active.rejections.values())
    assert rejections, "the registry declares rejected spellings"
    for rejection in rejections:
        decision, found = active.decide(rejection.applicant_name)
        assert decision is None and found is not None
