"""Contract and adapter guarantees.

These tests are the executable form of the integration's honest-conversion rules.
Each one corresponds to a way a naive field-renaming adapter would silently
corrupt the science:

* a source status becoming a confirmed identity,
* a catalogue token becoming a UDI-DI,
* a missing observation clock being filled with an event date,
* a restricted record being ingested because it "looks fine".
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from medradar.integration import contract  # noqa: E402
from medradar.integration.adapter import HorizonToAtlasAdapter  # noqa: E402
from medradar.integration.clock import BASIS_UNKNOWN, build_time_block  # noqa: E402
from medradar.integration.licence import LicencePolicy  # noqa: E402

EXPORT = REPO_ROOT / "research/horizon/exports/horizon-2026-11-10"


# --------------------------------------------------------------------- GTIN
@pytest.mark.parametrize(
    "value,valid",
    [
        ("00885074528007", True),
        ("00195278070265", True),
        ("00000000000000", True),
        ("00885074528008", False),  # wrong check digit
        ("6102F-PA00017", False),   # MDALL catalogue token
        ("1234567890123", False),   # 13 digits
        ("0088507452800", False),   # 13 digits, GTIN-13 shape
        ("", False),
        (None, False),
    ],
)
def test_gtin14_validation(value, valid):
    assert contract.is_gtin14(value) is valid


def test_mdall_catalogue_token_is_never_promoted():
    scheme, note = contract.classify_identifier("hc_mdall_device_identifier", "6102F-PA00017")
    assert scheme == "hc_device_identifier"
    assert note["derivation"] == "mdall_catalogue_token_not_a_udi"
    assert note["gtin14_valid"] is False


def test_mdall_gtin_is_promoted_only_with_a_valid_check_digit():
    promoted, note = contract.classify_identifier("hc_mdall_device_identifier", "00195278070265")
    assert promoted == "di"
    assert note["gtin14_valid"] is True
    shaped, note2 = contract.classify_identifier("hc_mdall_device_identifier", "00195278070264")
    assert shaped == "hc_device_identifier"
    assert "check_digit_invalid" in note2["derivation"]


def test_classification_schemes_are_not_identities():
    assert "hs_code" in contract.CLASSIFICATION_SCHEMES
    assert "fda_product_code" in contract.CLASSIFICATION_SCHEMES
    scheme, note = contract.classify_identifier("hs_code", "9018")
    assert scheme == "hs_code"
    assert note["role"] == "classification"


# ------------------------------------------------------------------ identity
def test_only_authoritative_grade_may_confirm_identity():
    for grade, effects in contract.IDENTITY_GRADE_EFFECTS.items():
        if effects["may_set_confirmed_identity"]:
            assert grade == "AUTHORITATIVE_ID_MATCH"
            assert effects["requires_official_identifier"] is True
    assert contract.IDENTITY_GRADE_EFFECTS["CANDIDATE_RELATION"]["may_set_confirmed_identity"] is False
    assert (
        contract.IDENTITY_GRADE_EFFECTS["SOURCE_ASSERTED_RELATION"]["may_set_confirmed_identity"]
        is False
    )


def test_applicant_group_candidate_cannot_be_promoted():
    assert "applicant_group_candidate" in contract.NON_PROMOTABLE_RELATION_TYPES
    assert contract.RELATION_TYPE_GRADE["applicant_group_candidate"] == "CANDIDATE_RELATION"
    assert contract.RELATION_TYPE_GRADE["priority_claim"] == "SOURCE_ASSERTED_RELATION"


def test_atlas_db_status_vocabulary_is_valid():
    allowed = {"CONFIRMED", "CANDIDATE", "REJECTED"}
    for grade, effects in contract.IDENTITY_GRADE_EFFECTS.items():
        assert effects["atlas_db_status"] in allowed, grade


# --------------------------------------------------------------------- clock
def test_first_observed_at_is_never_backfilled():
    record = {
        "event_at": "1999-10-04",
        "source_public_at": None,
        "first_observed_at": None,
        "fetched_at": "2026-11-09T23:17:02Z",
        "attributes": {},
    }
    block, warnings = build_time_block(record, import_run_started_at="2026-11-11T00:00:00Z")
    assert block["first_observed_at"] == ""
    assert block["observation_basis"] == BASIS_UNKNOWN
    assert "first_observed_at_unknown_source_ran_no_observation_log" in warnings
    # the event date must not leak into the observation or publication clock
    assert block["source_public_at"] == ""
    assert block["fetched_at"].startswith("2026-11-09")


def test_event_equals_public_is_recorded_not_reclassified():
    record = {
        "event_at": "2024-01-02",
        "source_public_at": "2024-01-02",
        "first_observed_at": "2026-11-09T23:00:00Z",
        "fetched_at": "2026-11-09T23:00:00Z",
        "attributes": {},
    }
    block, _ = build_time_block(record, import_run_started_at="2026-11-11T00:00:00Z")
    assert block["clock_relation"] == "event_equals_public"


def test_public_before_event_is_flagged():
    record = {
        "event_at": "2018-12-18",
        "source_public_at": "2018-11-05",
        "first_observed_at": None,
        "fetched_at": "2026-11-09T23:00:00Z",
        "attributes": {},
    }
    _, warnings = build_time_block(record, import_run_started_at="2026-11-11T00:00:00Z")
    assert "source_public_at_precedes_event_at" in warnings


# ------------------------------------------------------------------- adapter
def _first_record(source_file: str) -> dict:
    path = EXPORT / source_file
    with path.open(encoding="utf-8") as handle:
        return json.loads(handle.readline())


@pytest.fixture(scope="module")
def adapter() -> HorizonToAtlasAdapter:
    return HorizonToAtlasAdapter(LicencePolicy.load())


def test_real_record_converts_and_never_claims_identity(adapter):
    record = _first_record("canada_mdall.jsonl")
    result = adapter.adapt(record, run_id="test", raw_line=json.dumps(record).encode())
    assert result.ok, result.reason
    evidence = result.evidence
    # The source says identity_status=CONFIRMED for this record; the adapter must
    # not translate a record-level source status into an entity identity match.
    assert record.get("identity_status") == "CONFIRMED"
    assert evidence["identity_resolution_status"] == "not_attempted"
    source_status = evidence["normalized"]["convergence"]["source_record_status"]
    assert source_status["identity_status"] == "CONFIRMED"


def test_conversion_is_lossless(adapter):
    record = _first_record("accessgudid.jsonl")
    result = adapter.adapt(record, run_id="test")
    assert result.ok
    preserved = result.evidence["normalized"]["horizon"]
    for field, value in record.items():
        assert preserved[field] == value, f"field {field} changed during conversion"


def test_udi_di_scheme_is_mapped(adapter):
    record = _first_record("accessgudid.jsonl")
    result = adapter.adapt(record, run_id="test")
    schemes = {ident["scheme"] for ident in result.evidence["identifiers"]}
    assert "di" in schemes


def test_restricted_source_is_refused(adapter):
    record = {
        "schema_version": contract.SOURCE_SCHEMA,
        "source_id": "un_comtrade",
        "source_record_id": "comtrade:1",
        "entity_type": "trade_flow",
        "identifiers": [],
        "licence_status": "terms_restricted",
        "quality_flags": [],
        "relations": [],
        "fetched_at": "2026-11-09T23:00:00Z",
        "attributes": {},
    }
    result = adapter.adapt(record, run_id="test")
    assert not result.ok
    assert result.reason.startswith("licence_blocked")
    assert result.evidence is None


def test_unknown_source_fails_closed():
    policy = LicencePolicy.load()
    if not policy.is_known_source("some_unlisted_source"):
        adapter = HorizonToAtlasAdapter(policy)
        record = {
            "schema_version": contract.SOURCE_SCHEMA,
            "source_id": "some_unlisted_source",
            "source_record_id": "x:1",
            "entity_type": "publication",
            "identifiers": [{"scheme": "doi", "value": "10.1/x", "is_primary": True}],
            "licence_status": "open_no_explicit_licence",
            "quality_flags": [],
            "relations": [],
            "fetched_at": "2026-11-09T23:00:00Z",
            "attributes": {},
        }
        assert not adapter.adapt(record, run_id="test").ok


def test_unsupported_schema_is_refused(adapter):
    result = adapter.adapt({"schema_version": "horizon.evidence.v0", "source_id": "x"}, run_id="t")
    assert not result.ok
    assert result.reason.startswith("unsupported_source_schema")


def test_relation_aggregation_takes_the_weakest_grade(adapter):
    record = _first_record("cipo_canada.jsonl")
    result = adapter.adapt(record, run_id="test")
    assert result.ok
    if result.relation_claims:
        grades = {claim["grade"] for claim in result.relation_claims}
        if "CANDIDATE_RELATION" in grades:
            assert result.evidence["relation_status"] == "candidate"


def test_party_bearing_event_key_includes_the_party():
    from medradar.integration.dedupe import event_identity

    def fake(party: str) -> dict:
        return {
            "source_id": "eu_ted",
            "source_record_id": "ted:1:supplier",
            "normalized": {"horizon": {"attributes": {"supplier_name": party}}},
        }

    assert event_identity(fake("A")) != event_identity(fake("B"))
    assert event_identity(fake("A")) == event_identity(fake("A"))
