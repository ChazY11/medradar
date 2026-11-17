"""QUALITY-001: admission rules and their append-only projection.

The evaluation set in ``config/radar/quality_eval.json`` is independent of these unit tests: it
is a human-labelled sample used to measure the rules, not to restate them.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

try:
    import pytest  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - the offline CI suite has no pytest
    raise unittest.SkipTest("pytest is not installed; run these tests with pytest")

from medradar.radar.engine import advance
from medradar.radar.graph import open_graph
from medradar.radar.ledger import ObservationLedger
from medradar.radar.relevance import (
    ADMISSION_VERSION,
    HIGH_RELEVANCE,
    IRRELEVANT,
    LOW_RELEVANCE,
    NEEDS_REVIEW,
    classify_observation,
    classify_publication,
)
from medradar.radar.records import RawRecord
from medradar.radar.taxonomy import load_taxonomy

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "radar"


def _admission(title: str, abstract: str = "", *, record_type: str = "publication",
               payload_extra: dict | None = None, topics: list[str] | None = None):
    payload = {"title": title, "abstract": abstract, **(payload_extra or {})}
    return classify_observation(
        {"record_type": record_type, "title": title, "payload": payload},
        mapped_topics=topics, mapped_products=None,
    )


def test_clinical_risk_scores_are_not_monitoring_intelligence():
    for title in (
        "CLINICAL UTILITY AND EVALUATION OF TIMI RISK SCORE FOR EARLY RISK STRATIFICATION",
        "Early Prediction of Noninvasive Ventilation Failure in Critically Ill Patients",
        "TimeSHAP-LSTM: An Interpretable Temporal Deep Learning Framework for Early Sepsis Prediction",
        "Clinical Determinants and Machine Learning Prediction of Exercise Induced ST-Segment Depression",
    ):
        admission = _admission(title, "A retrospective cohort study using electronic health records.")
        assert admission.tier == LOW_RELEVANCE, (title, admission)
        assert admission.category in {
            "clinical_prediction_model", "clinical_study_without_device_focus",
        }, (title, admission)


def test_non_medical_and_veterinary_domains_are_irrelevant_with_a_reason():
    horse = _admission("Wearable sensing technologies and machine learning for fatigue assessment in sport horses")
    assert horse.tier == IRRELEVANT and horse.category == "non_human_subject"
    grid = _admission("Imbalance-Aware Evaluation of CNN and LSTM Detectors of False Data Injection on Smart Grid Stability")
    assert grid.tier == IRRELEVANT and grid.category == "non_medical_domain"


def test_a_device_validation_study_is_high_relevance():
    admission = _admission(
        "Validating a Wearable Bluetooth Oximeter for Infants in the Neonatal Intensive Care Unit",
        "We compared the wearable pulse oximeter with arterial blood gas reference values and "
        "report accuracy and agreement in 120 infants.",
    )
    assert admission.tier == HIGH_RELEVANCE, admission
    assert admission.category == "monitoring_technology_evaluation"


def test_a_clinical_accuracy_study_of_an_index_is_not_a_device_study():
    admission = _admission(
        "Peripheral perfusion index for differentiating cardiac and pulmonary dyspnea",
        "Pulse oximetry was used and the perfusion index was compared between groups; sensitivity "
        "and specificity were calculated for the diagnosis.",
    )
    assert admission.tier != HIGH_RELEVANCE, admission


def test_a_vendor_claim_is_only_admitted_when_the_mapping_places_it_in_a_monitored_topic():
    unmapped = _admission("Philips to nominate three candidates to the supervisory board",
                          record_type="press_release")
    assert unmapped.tier == LOW_RELEVANCE and unmapped.category == "primary_record_unmapped"
    mapped = _admission("Philips introduces a modular patient monitor with SpO2",
                        record_type="press_release", topics=["oxygenation"])
    assert mapped.tier == HIGH_RELEVANCE


def test_missing_abstract_is_judged_from_the_title_and_says_so():
    admission = classify_publication(
        title="Haemodynamic Monitoring",
        payload={"title": "Haemodynamic Monitoring", "abstract": ""},
    )
    assert any("no abstract" in reason for reason in admission.reasons)


# --- the projection over the ledger -----------------------------------------------------------

def _taxonomy():
    return load_taxonomy(str(CONFIG_DIR))


def _ledger(tmp_path: Path) -> ObservationLedger:
    handle = ObservationLedger(tmp_path / "radar.db")
    handle.ensure_source("openfda_device", label="FDA", adapter_version="a1", cadence_hours=24)
    handle.ensure_source("pubmed", label="PubMed", adapter_version="a1", cadence_hours=6)
    handle.ensure_source("philips_official", label="Philips", adapter_version="a1", cadence_hours=12)
    return handle


def _record(ledger: ObservationLedger, *, source: str, record_id: str, title: str,
            record_type: str, published_at: str, abstract: str = "", extra: dict | None = None):
    from medradar.radar.classify import RuleMapper
    from medradar.radar.records import MAPPING_VERSION

    record = RawRecord(
        source=source, source_record_id=record_id, official_identifier=record_id,
        record_type=record_type, title=title, url=f"https://example.test/{record_id}",
        published_at=published_at, published_at_precision="date",
        payload={"title": title, "abstract": abstract, **({"pmid": record_id} if source == "pubmed" else {})},
        text=title + " " + abstract,
        extra={"official_identifier": record_id, **(extra or {})},
    )
    return ledger.record_observation(
        record, RuleMapper(_taxonomy()).map(record), run_id="r", adapter_version="a1",
        mapping_version=MAPPING_VERSION,
    )


def test_admissions_drive_the_feed_views_without_touching_the_observations(tmp_path: Path):
    ledger = _ledger(tmp_path)
    _record(ledger, source="pubmed", record_id="pmid:1",
            title="Validating a Wearable Oximeter in the Neonatal Intensive Care Unit",
            record_type="publication", published_at="2026-11-10",
            abstract="We evaluated accuracy and agreement of a wearable pulse oximeter device.")
    _record(ledger, source="pubmed", record_id="pmid:2",
            title="TIMI Risk Score for Early Risk Stratification in ACS",
            record_type="publication", published_at="2026-11-11",
            abstract="A retrospective cohort of patients; mortality was the outcome.")
    _record(ledger, source="philips_official", record_id="philips:1",
            title="Philips introduces a modular patient monitor with SpO2",
            record_type="press_release", published_at="2026-11-12",
            extra={"organization_hint": "Royal Philips", "organization_role": "official_publisher",
                   "publisher_hint": "Royal Philips", "product_hint": "Modular Monitor 9000"})

    graph = open_graph(tmp_path / "graph.db", _taxonomy())
    try:
        result = advance(ledger, graph, _taxonomy(), enqueue_ai=False, log=lambda *_a: None)
    finally:
        graph.store.close()
    assert result["admitted"] == 3

    before = ledger.con.execute(
        "SELECT observation_id, first_observed_at, version_count FROM observation ORDER BY 1"
    ).fetchall()
    rows, total = ledger.feed(admission_version=ADMISSION_VERSION, tiers=[HIGH_RELEVANCE],
                              scope="latest", scope_days=3650, order="published")
    assert total == 2, "the device validation and the mapped vendor claim"
    assert all(row["admission"]["tier"] == HIGH_RELEVANCE for row in rows)

    review_rows, review_total = ledger.feed(admission_version=ADMISSION_VERSION,
                                           tiers=[NEEDS_REVIEW])
    assert review_total == 0
    excluded = ledger.con.execute(
        "SELECT tier FROM observation_admission WHERE admission_version=? AND tier=?",
        (ADMISSION_VERSION, LOW_RELEVANCE),
    ).fetchone()
    assert excluded is not None, "the clinical risk paper is retained with its rejection reason"

    after = ledger.con.execute(
        "SELECT observation_id, first_observed_at, version_count FROM observation ORDER BY 1"
    ).fetchall()
    assert [tuple(row) for row in before] == [tuple(row) for row in after], (
        "re-projection must not modify the observation history")
    ledger.close()


def test_the_historical_scope_separates_new_publications_from_old_documents_seen_today(tmp_path: Path):
    ledger = _ledger(tmp_path)
    _record(ledger, source="pubmed", record_id="pmid:10",
            title="Accuracy of a Wearable Pulse Oximeter in the Intensive Care Unit",
            record_type="publication", published_at="2019-05-01",
            abstract="Validation study of the device against arterial blood gas, reporting accuracy.")
    _record(ledger, source="pubmed", record_id="pmid:11",
            title="Agreement of a New Patient Monitor SpO2 Sensor with Reference Oximetry",
            record_type="publication", published_at="2026-11-01",
            abstract="Bench evaluation of the sensor performance and agreement.")
    graph = open_graph(tmp_path / "graph.db", _taxonomy())
    try:
        advance(ledger, graph, _taxonomy(), enqueue_ai=False, log=lambda *_a: None)
    finally:
        graph.store.close()

    latest, latest_total = ledger.feed(admission_version=ADMISSION_VERSION,
                                        tiers=[HIGH_RELEVANCE], scope="latest", scope_days=30)
    observed, observed_total = ledger.feed(admission_version=ADMISSION_VERSION,
                                           tiers=[HIGH_RELEVANCE, NEEDS_REVIEW], scope="observed",
                                           scope_days=30)
    assert latest_total == 1 and latest[0]["title"].startswith("Agreement of a New Patient Monitor")
    assert observed_total == 2, "both were first observed today"

    summary = ledger.admission_summary(ADMISSION_VERSION, days=30)
    assert summary["latest"] == 1 and summary["observed"] == 2 and summary["archive"] == 2
    ledger.close()


def test_the_facet_list_merges_one_company_into_one_filter(tmp_path: Path):
    ledger = _ledger(tmp_path)
    _record(ledger, source="pubmed", record_id="pmid:20",
            title="Alarm algorithm accuracy in the Intensive Care Unit",
            record_type="publication", published_at="2026-11-01",
            abstract="We evaluated the alarm algorithm false alarm rate and accuracy.",
            extra={"organization_hint": "Philips Research", "organization_role": "publication_affiliation",
                   "affiliations": ["Philips Research"]})
    _record(ledger, source="openfda_device", record_id="K1",
            title="INTELLIVUE MX800 PATIENT MONITOR", record_type="regulatory_record",
            published_at="2026-11-02",
            extra={"organization_hint": "Philips Medical Systems",
                   "organization_role": "regulatory_applicant", "product_codes": ["MHX"],
                   "product_hint": "INTELLIVUE MX800 PATIENT MONITOR", "product_identifier": "K1"})
    facets = ledger.feed_facets()
    names = [row["organization_id"] for row in facets["organizations"]]
    assert len(names) == len(set(names)), "one row per company"
    ledger.close()
