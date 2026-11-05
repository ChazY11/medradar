"""Validator hardening tests: the two false-positive classes the audit reproduced.

* **Wrong company accepted (F-05).**  The validator used to accept the extractor's own
  ``raw_text`` as proof that the document named the claimed company.  A model could
  assert ``canonical_id='medtronic'`` while quoting text about a different firm and be
  accepted.  Identity must be established by the *roster*, not by the claimant.
* **A status that a corpus cannot support.**  Covered in
  ``test_llm_research_real_corpus.py``.

These tests use the shipped roster configuration, so they also check that the five
study firms are resolvable at all.
"""

from __future__ import annotations

import pytest

from experiments.local_llm_event_extraction.validation.entities import EntityRoster

DOCUMENT = (
    "NovaPulse Medical, a business unit of NovaPulse Medical, said today that the US "
    "Food and Drug Administration granted 510(k) clearance for the RhythmGuard X2 "
    "insertable cardiac monitor on 18 February 2025."
)


@pytest.fixture(scope="module")
def roster() -> EntityRoster:
    return EntityRoster.from_config()


def test_extractor_raw_text_cannot_self_certify_a_wrong_company(roster) -> None:
    # The document does contain this raw_text -- but it names a different company.
    assert roster.alias_in_text("NovaPulse Medical", DOCUMENT) is True
    assert (
        roster.canonical_id_named_in_document(
            "medtronic", DOCUMENT, raw_text="NovaPulse Medical"
        )
        is False
    )


def test_correct_company_is_still_accepted_by_its_real_alias(roster) -> None:
    document = "Medtronic announced that its MiniMed 780G system received clearance."
    assert roster.canonical_id_named_in_document("medtronic", document) is True
    assert (
        roster.canonical_id_named_in_document("medtronic", document, raw_text="MiniMed")
        is True
    )


def test_raw_text_resolving_to_the_claimed_company_is_accepted(roster) -> None:
    document = "Medtronic MiniMed announced a new sensor."
    assert (
        roster.canonical_id_named_in_document(
            "medtronic", document, raw_text="Medtronic MiniMed"
        )
        is True
    )


def test_five_study_firms_are_resolvable(roster) -> None:
    expected = {
        "Medtronic": "medtronic",
        "Philips": "philips",
        "Siemens Healthineers": "siemens_healthineers",
        "GE HealthCare": "ge_healthcare",
        "Draeger": "draeger",
    }
    for text, canonical in expected.items():
        assert roster.resolve_alias(text) == canonical, f"{text!r} did not resolve to {canonical!r}"
