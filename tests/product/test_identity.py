"""Identity and attribution rules (DATA_CONTRACT section 4)."""
from __future__ import annotations

from medradar.product import identity


def test_registry_loads_and_has_organizations():
    registry = identity.registry()
    assert len(registry.organizations) >= 50
    keys = [org.key for org in registry.organizations]
    assert len(keys) == len(set(keys)), "organization keys must be unique"


def test_no_applicant_spelling_is_claimed_by_two_organizations():
    registry = identity.registry()
    seen: dict[str, str] = {}
    for org in registry.organizations:
        for decision in org.accept_exact:
            normalised = identity.normalise_applicant(decision.applicant_name)
            assert normalised not in seen, "spelling claimed twice: " + decision.applicant_name
            seen[normalised] = org.key


def test_no_spelling_is_both_accepted_and_rejected():
    registry = identity.registry()
    for org in registry.organizations:
        accepted = {identity.normalise_applicant(item.applicant_name) for item in org.accept_exact}
        rejected = {identity.normalise_applicant(item.applicant_name) for item in org.reject_exact}
        assert not (accepted & rejected), "spelling both accepted and rejected for " + org.key


def test_attribution_is_exact_after_case_and_whitespace_normalisation():
    registry = identity.registry()
    org = registry.organization("medtronic")
    assert org is not None
    first = org.accept_exact[0].applicant_name
    decision, rejection = registry.decide(first.upper().replace(" ", "   "))
    assert decision is not None and decision.organization_key == "medtronic"
    assert rejection is None
    unknown, unknown_rejection = registry.decide("NOT A REAL APPLICANT XYZ")
    assert unknown is None and unknown_rejection is None


def test_fuzzy_variant_is_not_attributed():
    """A near-miss spelling must not be attributed: no fuzzy matching is allowed."""
    registry = identity.registry()
    decision, _ = registry.decide("Medtronik Vascular")
    assert decision is None


def test_pending_review_attributions_are_labelled():
    registry = identity.registry()
    pending = [item for org in registry.organizations for item in org.accept_exact if item.review == "pending_review"]
    assert pending, "expected auto-proposed spellings to be marked pending_review"
    for item in pending:
        assert item.source, "a pending-review spelling must carry its evidence source"


def test_rejected_spelling_has_a_reason():
    registry = identity.registry()
    rejections = [item for org in registry.organizations for item in org.reject_exact]
    assert rejections
    for item in rejections:
        assert len(item.reason) > 10


def test_search_prefers_exact_brand_over_substring():
    hits, _ = identity.search_organizations("stryker", [])
    assert hits and hits[0].organization.key == "stryker"
    assert hits[0].match_field in ("brand", "legal_name", "alias")


def test_short_query_does_not_match_unrelated_applicant_strings():
    hits, applicants = identity.search_organizations("ge", [])
    assert applicants == [], "a two-letter query must not surface applicant strings"
    assert hits and hits[0].organization.key == "ge_healthcare"


def test_ticker_search():
    hits, _ = identity.search_organizations("MDT", [])
    assert hits and hits[0].organization.key == "medtronic"
    assert hits[0].match_field == "ticker"
