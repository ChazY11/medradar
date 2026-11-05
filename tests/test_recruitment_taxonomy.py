"""Offline tests for the deterministic (A-arm) function/track classifier (WP2b, deliverable 2).

What these tests protect:

* the documented interface ``classify_rules(job)`` and its evidence/confidence shape;
* evidence spans are verifiable substrings of the normalised field text;
* a commercial/administrative posting is **never** given a technology track even
  when its description is full of device keywords (the explicit failing case the
  mission names);
* ``UNCLASSIFIED`` is reachable by construction (no cue, below-floor description,
  ambiguous description) and is counted, not swept into a default class;
* every output carries the rules version, the function-map version/fingerprint and
  the existing versioned taxonomy regime;
* record-based ratios on the real collected sample (rates, not hard-coded counts,
  because the snapshot is replaceable by a larger collection run).

All tests are offline and read the committed sample without modifying it.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

import pytest

from medradar.intelligence import taxonomy as intelligence_taxonomy
from medradar.recruitment import records as rec
from medradar.recruitment import taxonomy

ROOT = Path(__file__).resolve().parents[1]
REAL_SAMPLE = ROOT / "experiments" / "innovation_signals_observatory" / "results" / "2026-11-04" / "jobs_medtronic.jsonl"


# --------------------------------------------------------------------- helpers
def job(title: str = "", description: str = "", location: str = "Galway, Ireland") -> dict:
    return {
        "company_key": "medtronic",
        "source_platform": "workday",
        "posting_id": "P1",
        "job_title": title,
        "job_description": description,
        "job_location": location,
        "source_url": "https://example.invalid/job",
        "raw": {},
    }


@lru_cache(maxsize=1)
def _real_rows_cached() -> tuple[dict, ...]:
    if not REAL_SAMPLE.exists():
        return ()
    with REAL_SAMPLE.open(encoding="utf-8") as handle:
        return tuple(json.loads(line) for line in handle if line.strip())


def real_rows() -> list[dict]:
    return list(_real_rows_cached())


@lru_cache(maxsize=1)
def real_classifications() -> list[dict]:
    """The sample classified once; the report/evidence tests reuse it."""
    return [taxonomy.classify_rules(row) for row in _real_rows_cached()]


@lru_cache(maxsize=1)
def real_summary() -> dict:
    return taxonomy.summarise_classifications(real_classifications())


def find_real(needle: str) -> dict | None:
    needle = needle.lower()
    for row in real_rows():
        if needle in (row.get("job_title") or "").lower():
            return row
    return None


def require_real(needle: str) -> dict:
    row = find_real(needle)
    if row is None:
        pytest.skip(f"posting {needle!r} not present in the current committed snapshot")
    return row


# ------------------------------------------------------------------ interface
class TestInterface:
    def test_contract_keys_and_closed_vocabulary(self):
        out = taxonomy.classify_rules(job("R&D Engineer", "Design and development of new devices."))
        for key in ("function_class", "track_id", "evidence_spans", "confidence_basis"):
            assert key in out
        assert out["function_class"] in taxonomy.FUNCTION_CLASSES
        assert out["track_id"] is None or out["track_id"] in taxonomy.track_ids()
        assert isinstance(out["evidence_spans"], list)
        assert out["function_class"] == "CORE_R&D"

    def test_accepts_a_jsonl_row_dict_and_a_job_observation(self):
        rows = real_rows()
        if not rows:
            pytest.skip("real sample not present in this checkout")
        row = rows[0]
        from_dict = taxonomy.classify_rules(row)
        from_object = taxonomy.classify_rules(rec.JobObservation.from_dict(row))
        assert from_dict["function_class"] == from_object["function_class"]
        assert from_dict["track_id"] == from_object["track_id"]

    def test_track_id_is_none_when_undecided_never_the_string_unclassified(self):
        out = taxonomy.classify_rules(job("Associate", "Join our team in a dynamic environment."))
        assert out["function_class"] == "UNCLASSIFIED"
        assert out["track_id"] is None
        assert out["track_id"] != "UNCLASSIFIED"


# ---------------------------------------------------------------- evidence spans
class TestEvidence:
    def test_evidence_spans_are_verbatim_substrings_of_the_normalised_field(self):
        title = "Principal R&D Engineer"
        description = "Work on new concepts and prototypes."
        out = taxonomy.classify_rules(job(title, description))
        assert out["evidence_spans"], "a classified posting must carry evidence"
        for span in out["evidence_spans"]:
            source = title if span["field"] == "job_title" else description
            normalised = taxonomy.normalise_field(source)
            assert span["field"] in {"job_title", "job_description"}
            assert span["quote"] == span["text"]
            assert normalised[span["start"]:span["end"]] == span["text"]

    def test_every_real_span_is_verifiable(self):
        rows = real_rows()
        if not rows:
            pytest.skip("real sample not present in this checkout")
        for row, out in zip(rows, real_classifications()):
            for span in out["evidence_spans"]:
                field_text = taxonomy.normalise_field(
                    row["job_title"] if span["field"] == "job_title" else row["job_description"]
                )
                assert field_text[span["start"]:span["end"]] == span["text"] == span["quote"]
                assert span["kind"] in {"function", "track"}
                if span["kind"] == "function":
                    assert span["target"] == out["function_class"]

    def test_title_cue_outranks_any_number_of_description_cues(self):
        # A research title stays research even in a description full of commercial words.
        description = "sales quota customer marketing territory financial budget " * 5
        out = taxonomy.classify_rules(job("R&D Engineer", description))
        assert out["function_class"] == "CORE_R&D"
        assert out["function_evidence"]["decision_basis"] == "title_phrases"

    def test_more_specific_title_phrase_wins_within_a_title(self):
        # 'clinical research' and 'research scientist' both match; the head of the
        # title phrase ('clinical research') decides.
        out = taxonomy.classify_rules(job("Clinical Research Scientist", "Clinical trial design."))
        assert out["function_class"] == "CLINICAL_R&D"


# ------------------------------------------------------------- the sales/tech trap
class TestSalesNeverForcedIntoTrack:
    def test_synthetic_sales_role_with_heavy_device_keywords_gets_no_track(self):
        description = (
            "Sell cardiac ablation and electrophysiology products. Support pacemaker and defibrillator "
            "cases, pulsed field ablation procedures and mapping catheter workflows in the territory."
        )
        out = taxonomy.classify_rules(job("Territory Manager - CRM", description))

        assert out["function_class"] == "SALES_ADMIN_OTHER"
        assert out["track_id"] is None
        assert out["track_evidence"]["track_status"] == taxonomy.TRACK_SUPPRESSED
        # The keyword logic WOULD have matched (this is the failing case the mission
        # names); the gate is what prevents it from becoming a technology label.
        track_spans = out["track_evidence"]["spans"]
        assert track_spans, "expected device keywords in the synthetic description"
        candidate = out["track_evidence"]["candidate"]
        assert candidate is not None
        assert candidate["track_id"] in taxonomy.track_ids()
        assert candidate["title_specific_keywords"] == []

    def test_real_territory_manager_with_many_cardiac_keywords_is_suppressed(self):
        row = find_real("Territory Manager - CRM")
        if row is None:
            pytest.skip("Territory Manager - CRM posting not present in the current snapshot")
        out = taxonomy.classify_rules(row)
        assert out["function_class"] == "SALES_ADMIN_OTHER"
        assert out["track_id"] is None
        assert out["track_evidence"]["track_status"] == taxonomy.TRACK_SUPPRESSED
        # the candidate evidence really was present and refused
        candidate = out["track_evidence"]["candidate"]
        assert candidate is not None
        assert candidate["description_specific_keywords"], candidate

    def test_real_financial_analyst_in_a_neuromodulation_business_is_suppressed(self):
        row = find_real("Principal Financial Analyst")
        if row is None:
            pytest.skip("financial analyst posting not present in the current snapshot")
        out = taxonomy.classify_rules(row)
        assert out["function_class"] == "SALES_ADMIN_OTHER"
        assert out["track_id"] is None
        assert out["track_evidence"]["track_status"] == taxonomy.TRACK_SUPPRESSED

    def test_field_clinical_specialist_is_commercial_not_a_clinical_research_role(self):
        row = find_real("Clinical Specialist")
        if row is None:
            pytest.skip("a Clinical Specialist posting is not present in the current snapshot")
        out = taxonomy.classify_rules(row)
        assert out["function_class"] == "SALES_ADMIN_OTHER", out["function_class"]
        assert out["track_id"] is None

    def test_ep_mapping_specialist_is_not_mapped_to_the_ep_pfa_track(self):
        row = find_real("EP Mapping Specialist")
        if row is None:
            pytest.skip("an EP Mapping Specialist posting is not present in the current snapshot")
        out = taxonomy.classify_rules(row)
        assert out["function_class"] == "SALES_ADMIN_OTHER"
        assert out["track_id"] is None
        assert out["track_evidence"]["track_status"] == taxonomy.TRACK_SUPPRESSED

    def test_every_real_sales_posting_has_no_track_and_a_positive_cue(self):
        if not real_rows():
            pytest.skip("real sample not present in this checkout")
        sales = [out for out in real_classifications() if out["function_class"] == "SALES_ADMIN_OTHER"]
        assert sales, "expected commercial roles in the Medtronic sample"
        for out in sales:
            assert out["track_id"] is None
            assert out["track_evidence"]["track_status"] == taxonomy.TRACK_SUPPRESSED
            # Positive cues, never default assignment: a title or description phrase fired.
            assert out["function_evidence"]["decision_basis"] in {"title_phrases", "description_phrases"}
            assert out["function_evidence"]["spans"]


# ------------------------------------------------------------------- UNCLASSIFIED
class TestUnclassified:
    def test_unclassified_when_no_cue_fires(self):
        out = taxonomy.classify_rules(job("Associate", "Join our team in a dynamic environment."))
        assert out["function_class"] == "UNCLASSIFIED"
        assert out["unclassified_reason"] == "no_cue_in_title_or_description"
        assert out["track_id"] is None
        assert out["track_evidence"]["track_status"] in {
            taxonomy.TRACK_SUPPRESSED, taxonomy.TRACK_AMBIENT_ONLY, taxonomy.TRACK_NO_EVIDENCE
        }

    def test_unclassified_when_description_evidence_is_below_floor(self):
        out = taxonomy.classify_rules(job("Engineer I", "We do product development work."))
        assert out["function_class"] == "UNCLASSIFIED"
        assert out["unclassified_reason"] == "description_below_min_hits"

    def test_unclassified_when_two_description_classes_tie(self):
        description = (
            "You will own product development, design verification and test method work, while the "
            "quality system, regulatory and audit processes govern release."
        )
        out = taxonomy.classify_rules(job("Engineer I", description))
        assert out["function_class"] == "UNCLASSIFIED"
        assert out["unclassified_reason"] == "description_tie"

    def test_unclassified_is_never_given_a_technology_track(self):
        out = taxonomy.classify_rules(job("Associate", "We offer dental and vision benefits and support "
                                                        "teams with procurement and inventory."))
        assert out["function_class"] == "UNCLASSIFIED"
        assert out["track_id"] is None

    def test_real_sample_rates_are_reported_and_internally_consistent(self):
        rows = real_rows()
        if not rows:
            pytest.skip("real sample not present in this checkout")
        summary = real_summary()
        n = summary["n"]
        assert n == len(rows)
        assert sum(summary["function_class_counts"].values()) == n
        assert summary["unclassified_count"] == summary["function_class_counts"]["UNCLASSIFIED"]
        assert summary["unclassified_rate"] == round(summary["unclassified_count"] / n, 4)
        assert 0.0 <= summary["unclassified_rate"] <= 1.0
        assert sum(summary["track_status_counts"].values()) == n
        assert summary["track_assigned_rate"] == round(summary["track_assigned_count"] / n, 4)
        for count in summary["function_class_counts"].values():
            assert 0 <= count <= n
        assert json.dumps(summary, sort_keys=True)

    def test_real_unclassified_rows_carry_a_reason_and_no_track(self):
        if not real_rows():
            pytest.skip("real sample not present in this checkout")
        unclassified = [out for out in real_classifications() if out["function_class"] == "UNCLASSIFIED"]
        for out in unclassified:
            assert out["unclassified_reason"] in {
                "no_cue_in_title_or_description", "description_below_min_hits", "description_tie"
            }
            assert out["track_id"] is None
        # The mechanism either fires on the real distribution or it does not; if it
        # fires, the reasons must be counted, and the title-vs-description basis of
        # every *classified* row must be reported so a reader can see it is not a
        # default assignment.
        summary = real_summary()
        if unclassified:
            assert sum(summary["unclassified_reasons"].values()) == len(unclassified)
        assert set(summary["function_decision_basis"]) <= {"title_phrases", "description_phrases", "abstain"}
        assert summary["function_decision_basis"].get("abstain", 0) == len(unclassified)


# ------------------------------------------------------------------ track rules
class TestTracks:
    def test_only_existing_taxonomy_track_ids_are_emitted(self):
        if not real_rows():
            pytest.skip("real sample not present in this checkout")
        known = set(taxonomy.track_ids())
        for out in real_classifications():
            assert out["track_id"] is None or out["track_id"] in known

    def test_generic_keywords_never_assign_a_track_alone(self):
        out = taxonomy.classify_rules(
            job(
                "Product Development Engineer",
                "We offer dental and vision benefits. Our next generation software platform is used by "
                "hospitals to schedule work.",
            )
        )
        assert out["function_class"] == "PRODUCT_ENGINEERING"
        assert out["track_id"] is None
        assert out["track_evidence"]["track_status"] == taxonomy.TRACK_AMBIENT_ONLY
        assert any(span.get("generic") for span in out["track_evidence"]["spans"])

    def test_a_frontier_keyword_can_carry_a_track_on_its_own(self):
        out = taxonomy.classify_rules(
            job("Mechanical Engineer", "Design fixtures for pulsed field ablation (PFA) catheters.")
        )
        assert out["function_class"] == "PRODUCT_ENGINEERING"
        assert out["track_id"] == "ep_pfa"
        assert out["track_evidence"]["track_status"] == taxonomy.TRACK_MAPPED

    def test_single_description_keyword_is_ambient_not_a_classification(self):
        out = taxonomy.classify_rules(job("R&D Engineer", "Develop new surgical instruments and fixtures."))
        assert out["function_class"] == "CORE_R&D"
        assert out["track_id"] is None
        assert out["track_evidence"]["track_status"] in {
            taxonomy.TRACK_AMBIENT_ONLY, taxonomy.TRACK_NO_EVIDENCE
        }

    def test_technical_role_can_receive_a_track(self):
        out = taxonomy.classify_rules(
            job("Senior Reliability Engineer",
                "Post-market surveillance for pacemakers, defibrillators and leads.")
        )
        assert out["function_class"] == "HARDWARE_SYSTEMS"
        assert out["track_id"] == "cardiac_rhythm"

    def test_real_sample_track_coverage_is_reported_not_forced(self):
        if not real_rows():
            pytest.skip("real sample not present in this checkout")
        summary = real_summary()
        assert "track_assigned_rate" in summary
        assert "track_status_counts" in summary
        assert set(summary["track_status_counts"]) == set(taxonomy.TRACK_STATUSES)
        # The device taxonomy was built for product-code text, not job adverts; the
        # baseline is deliberately conservative, so it must not assign a track to
        # every posting.
        assert summary["track_assigned_rate"] < 1.0
        # Every assignment is rule-strength labelled and its evidence strength is
        # reported, so a reader can gate on WEAK rather than being forced to trust it.
        assert sum(summary["track_rule_strength_counts"].values()) == summary["track_assigned_count"]
        assert sum(summary["track_assignment_basis"].values()) == summary["track_assigned_count"]
        for out in real_classifications():
            if not out["track_id"]:
                continue
            candidate = out["track_evidence"]["candidate"]
            assert candidate is not None
            strength = out["confidence_basis"]["track"]["rule_strength"]
            if candidate["title_specific_keywords"]:
                # a title keyword is the strong basis; it is never labelled WEAK
                assert strength in {taxonomy.STRENGTH_MODERATE, taxonomy.STRENGTH_STRONG}
            else:
                # description-only assignments are allowed but must be visible as
                # weaker evidence, not presented as a confident classification
                assert strength in {taxonomy.STRENGTH_WEAK, taxonomy.STRENGTH_MODERATE}


# --------------------------------------------------------- confidence and versions
class TestConfidence:
    def test_confidence_basis_is_explicitly_not_a_probability(self):
        out = taxonomy.classify_rules(job("R&D Engineer", "Design and development of new devices."))
        confidence = out["confidence_basis"]
        assert confidence["kind"] == "rule_derived_not_probability"
        assert confidence["calibrated_probability"] is False
        assert "NOT a calibrated probability" in confidence["statement"]
        assert confidence["function"]["rule_strength"] in {
            taxonomy.STRENGTH_STRONG, taxonomy.STRENGTH_MODERATE, taxonomy.STRENGTH_WEAK, taxonomy.STRENGTH_NONE
        }
        assert confidence["track"]["rule_strength"] in {
            taxonomy.STRENGTH_STRONG, taxonomy.STRENGTH_MODERATE, taxonomy.STRENGTH_WEAK, taxonomy.STRENGTH_NONE
        }
        # counts, not estimated probabilities
        for key in ("title_score", "title_distinct_phrases", "title_hits", "margin"):
            assert isinstance(confidence["function"][key], int)

    def test_description_only_classification_is_labelled_weaker(self):
        by_title = taxonomy.classify_rules(job("Marketing Specialist", "Plan campaigns."))
        by_description = taxonomy.classify_rules(
            job("Associate", "Plan campaigns, marketing events, customer meetings and sales support.")
        )
        assert by_title["function_evidence"]["decision_basis"] == "title_phrases"
        assert by_description["function_evidence"]["decision_basis"] == "description_phrases"
        assert by_description["confidence_basis"]["function"]["rule_strength"] in {
            taxonomy.STRENGTH_WEAK, taxonomy.STRENGTH_MODERATE
        }
        assert by_title["confidence_basis"]["function"]["rule_strength"] in {
            taxonomy.STRENGTH_STRONG, taxonomy.STRENGTH_MODERATE
        }

    def test_every_output_is_stamped_with_all_label_versions(self):
        out = taxonomy.classify_rules(job("R&D Engineer", "Design and development of new devices."))
        assert out["rules_version"] == taxonomy.RULES_VERSION
        assert out["function_map_version"] == taxonomy.function_map_version()
        assert out["taxonomy"]["version"] == intelligence_taxonomy.TAXONOMY_VERSION
        assert out["taxonomy"]["effective_from"] == intelligence_taxonomy.EFFECTIVE_FROM
        assert len(out["function_map_fingerprint"]) == 64
        assert len(out["taxonomy"]["track_list_fingerprint"]) == 64

    def test_function_map_fingerprint_hashes_the_committed_file(self):
        expected = hashlib.sha256(taxonomy.FUNCTION_MAP_PATH.read_bytes()).hexdigest()
        assert taxonomy.function_map_fingerprint() == expected

    def test_map_version_is_declared_in_the_config(self):
        document = json.loads(taxonomy.FUNCTION_MAP_PATH.read_text(encoding="utf-8"))
        assert document["map_version"] == taxonomy.function_map_version()
        assert document["schema"] == 1
        # the mission vocabulary is not extended or renamed by this config
        assert set(document["classes"]) == set(taxonomy.FUNCTION_CLASSES)


# ------------------------------------------------------------------ real sample
class TestRealSample:
    def test_all_real_postings_receive_a_closed_vocabulary_class(self):
        rows = real_rows()
        if not rows:
            pytest.skip("real sample not present in this checkout")
        for row, out in zip(rows, real_classifications()):
            assert out["function_class"] in taxonomy.FUNCTION_CLASSES
            assert out["track_id"] is None or out["track_id"] in taxonomy.track_ids()
            if out["function_class"] != "UNCLASSIFIED":
                assert out["evidence_spans"], f"classified posting without evidence: {row.get('job_title')}"
            else:
                assert out["evidence_spans"] == [] or out["unclassified_reason"]

    def test_real_sample_mechanism_is_cue_based_not_default(self):
        if not real_rows():
            pytest.skip("real sample not present in this checkout")
        outputs = real_classifications()
        classified = [out for out in outputs if out["function_class"] != "UNCLASSIFIED"]
        assert classified
        # Every classified posting fired at least one rule and carries its span.
        for out in classified:
            assert out["function_evidence"]["decision_basis"] in {"title_phrases", "description_phrases"}
            assert out["function_evidence"]["spans"]
        # A catch-all cannot be 'everything that did not match something else':
        # SALES_ADMIN_OTHER must be reached by its own positive cues.
        for out in outputs:
            if out["function_class"] == "SALES_ADMIN_OTHER":
                assert out["function_evidence"]["spans"]
                assert out["function_evidence"]["decision_basis"] != "abstain"

    def test_real_sample_has_both_commercial_and_technical_postings(self):
        if not real_rows():
            pytest.skip("real sample not present in this checkout")
        summary = real_summary()
        assert summary["function_class_counts"]["SALES_ADMIN_OTHER"] >= 1
        assert sum(
            summary["function_class_counts"][cls]
            for cls in ("CORE_R&D", "CLINICAL_R&D", "PRODUCT_ENGINEERING", "ALGORITHM_SOFTWARE",
                        "HARDWARE_SYSTEMS", "MANUFACTURING_PROCESS", "QUALITY_REGULATORY")
        ) >= 1
