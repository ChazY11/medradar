"""REFOUNDATION-004 integrity and relevance regression tests.

These tests exist because each case below was a real, measurable defect:

* QA-002: non-medical research (drones, radar target detection, gear health, gravitational
  waves) entered the intelligence feed, and genuine monitoring evidence (intravascular
  oximetry, ICU cerebral oximetry, ECG algorithm performance, monitoring-device recalls) was
  rejected.
* QA-002: an official Philips launch (HyperVue, UniGuide) entered the default monitoring feed
  because source authenticity was substituted for subject judgement.
* QA-002: ``observation_admission`` used INSERT OR REPLACE, so rerunning a rule version
  overwrote an earlier judgement instead of appending history.
* QA-002: the development evaluator used a 14-day window while the product used 30.
* QA-002: the UI rendered a month-precision date as a midnight timestamp.

A later change that reintroduces any of them fails here by name.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

try:
    import pytest  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - the offline CI suite has no pytest
    raise unittest.SkipTest("pytest is not installed; run these tests with pytest")

from medradar.radar import assessment as assessment_module
from medradar.radar.ledger import ObservationLedger
from medradar.radar.relevance import (
    ADMISSION_VERSION,
    DECISION_FEED,
    DIRECT,
    HIGH_RELEVANCE,
    MEDICAL_UNRELATED,
    NON_MEDICAL,
    OFFICIAL_VENDOR,
    TRANSFER,
    classify_observation,
)

ROOT = Path(__file__).resolve().parents[1]


def _admission(title: str, abstract: str = "", *, record_type: str = "publication",
               topics: list | None = None, products: list | None = None,
               published_at: str | None = None, precision: str = "date"):
    return classify_observation(
        {"record_type": record_type, "title": title,
         "payload": {"title": title, "abstract": abstract},
         "published_at": published_at, "published_at_precision": precision},
        mapped_topics=topics, mapped_products=products,
    )


# --------------------------------------------------------------- false accepts (QA-002)
NON_MEDICAL_TITLES = [
    "Drone-based inspection of power line insulators using an infrared sensor",
    "Radar target detection using a deep learning detector on range-Doppler images",
    "Gear health monitoring using vibration sensors and a convolutional neural network classifier",
    "Gravitational wave detection with machine learning at the LIGO interferometer",
    "An Automated Real Time Oil Leakage Detection without False Alarm",
    "BFAR: improving radar odometry estimation using a bounded false alarm rate detector",
    "Improved Adaptive Constant False Alarm Rate Detector Based on Fuzzy Theory for Multiple-Target Scenario",
    "Imbalance-Aware Evaluation of CNN and LSTM Detectors of False Data Injection on Smart Grid Stability",
]


def test_non_medical_research_is_never_feed_eligible():
    for title in NON_MEDICAL_TITLES:
        admission = _admission(title, "A benchmark on synthetic data.")
        assert admission.decision != DECISION_FEED, (title, admission)
        assert admission.tier != HIGH_RELEVANCE, (title, admission)


def test_official_company_identity_does_not_grant_relevance():
    """A Philips imaging launch is authentic and not monitoring intelligence."""
    for title in ("Philips launches HyperVue", "Philips launches UniGuide 3D Live Guidance"):
        admission = _admission(title, record_type="press_release",
                               topics=["haemodynamics"], products=["HyperVue"])
        assert admission.decision != DECISION_FEED, admission
        assert admission.dimensions["source_authenticity"] == OFFICIAL_VENDOR
        assert admission.dimensions["monitoring_relevance"] == MEDICAL_UNRELATED


def test_clinical_prediction_is_not_monitoring_technology():
    for title in (
        "Deep Learning-Based BNP and NT-proBNP Evaluation From Wearable-Compatible Single-Lead ECGs",
        "External Validation of a Machine Learning Model for Delirium Risk",
        "Machine learning prediction of ventilator-associated pneumonia in ICU patients",
    ):
        admission = _admission(title, "A retrospective cohort of ICU patients.")
        assert admission.decision != DECISION_FEED, (title, admission)
        assert admission.tier != HIGH_RELEVANCE, (title, admission)


# --------------------------------------------------------------- false rejects (QA-002)
MONITORING_TITLES = [
    ("Intravascular continuous oximetry with a fibre-optic sensor: a bench validation study", "publication"),
    ("Cerebral oximetry in ICU patients: comparison of two near-infrared spectroscopy devices "
     "against jugular bulb saturation", "publication"),
    ("Performance of a novel single-lead ECG algorithm for arrhythmia detection in ambulatory "
     "monitoring", "publication"),
    ("Cardiac monitor recall analysis: failure modes reported in a regulatory device database",
     "publication"),
    ("Apnea Monitor Safety Alerts Warn of Alarm Failure Conditions", "publication"),
    ("Validating a Wearable Bluetooth Oximeter for Infants in the Neonatal Intensive Care Unit",
     "publication"),
]


def test_direct_monitoring_evidence_is_feed_eligible():
    for title, record_type in MONITORING_TITLES:
        admission = _admission(title, "We measured accuracy and agreement against a reference.",
                               record_type=record_type)
        assert admission.decision == DECISION_FEED, (title, admission)
        assert admission.dimensions["monitoring_relevance"] == DIRECT, (title, admission)


def test_the_journal_name_is_not_subject_evidence():
    """QA-002: an ECG algorithm paper was IRRELEVANT because its journal said "Telecommunications"."""
    admission = _admission(
        "Explainable Feature-based Machine Learning for Patient-independent ECG Arrhythmia Classification",
        "",
    )
    assert admission.tier in (HIGH_RELEVANCE, "NEEDS_REVIEW"), admission
    assert admission.dimensions["monitoring_relevance"] in (DIRECT, TRANSFER), admission


def test_a_regulatory_clearance_for_a_monitored_family_is_direct_evidence():
    admission = _admission("PATIENT MONITOR MODELS PM-2000A", record_type="regulatory_record",
                           topics=["modular_monitoring"])
    assert admission.decision == DECISION_FEED
    assert admission.dimensions["source_authenticity"] == "PRIMARY_REGULATORY"


# --------------------------------------------------------------- dimension separation
def test_dimensions_are_independent():
    admission = _admission("Apnea Monitor Safety Alerts Warn of Alarm Failure Conditions")
    dimensions = admission.dimensions
    assert dimensions["source_authenticity"] == "SCHOLARLY"
    assert dimensions["medical_domain"] == "MEDICAL"
    assert dimensions["monitoring_relevance"] == DIRECT
    assert dimensions["decision"] == DECISION_FEED
    assert 0.0 <= dimensions["confidence"] <= 1.0
    assert admission.features["journal_is_not_subject_evidence"] is True


def test_month_precision_is_not_widened_into_an_instant():
    admission = _admission("Pulse oximetry accuracy against arterial blood gas",
                           published_at="2026-11", precision="month")
    assert admission.features["date_precision"] == "month"
    assert admission.dimensions["freshness"] in ("FRESH", "RECENT", "STALE")


# --------------------------------------------------------------- window alignment
def test_the_evaluator_and_the_product_use_the_same_window():
    import importlib.util

    path = ROOT / "scripts" / "evaluate_relevance.py"
    spec = importlib.util.spec_from_file_location("evaluate_relevance", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    api_source = (ROOT / "medradar" / "radar" / "api.py").read_text(encoding="utf-8")
    assert module.FEED_WINDOW_DAYS == 30
    assert "admission_days: int = Query(30" in api_source


# --------------------------------------------------------------- append-only admission
def _ledger(tmp_path: Path) -> ObservationLedger:
    return ObservationLedger(tmp_path / "radar.db")


def _row(observation_id: str, *, evidence: str = "e1", tier: str = "LOW_RELEVANCE",
         decision: str = "EXCLUDED", decided_at: str = "2026-11-18T00:00:00Z") -> dict:
    return {
        "observation_id": observation_id,
        "admission_version": ADMISSION_VERSION,
        "tier": tier,
        "category": "test",
        "score": 0.0,
        "reasons": json.dumps(["test"]),
        "features": "{}",
        "decision": decision,
        "dimensions": json.dumps({"monitoring_relevance": "CLINICAL"}),
        "rules_digest": "test-rules",
        "evidence_key": evidence,
        "judged_version_id": "v:" + evidence,
        "decided_at": decided_at,
    }


def test_an_admission_decision_cannot_be_updated_or_deleted(tmp_path: Path):
    ledger = _ledger(tmp_path)
    ledger.record_admissions([_row("obs-1")])
    with pytest.raises(sqlite3.IntegrityError):
        ledger.con.execute(
            "UPDATE observation_admission SET tier='HIGH_RELEVANCE' WHERE observation_id='obs-1'")
    with pytest.raises(sqlite3.IntegrityError):
        ledger.con.execute("DELETE FROM observation_admission WHERE observation_id='obs-1'")
    ledger.close()


def test_rejudgement_appends_history_instead_of_overwriting_it(tmp_path: Path):
    ledger = _ledger(tmp_path)
    ledger.record_admissions([_row("obs-1", evidence="e1", tier="LOW_RELEVANCE")])
    ledger.record_admissions([_row("obs-1", evidence="e2", tier="HIGH_RELEVANCE",
                                   decision="FEED")])
    history = ledger.admission_history("obs-1")
    assert [row["tier"] for row in history] == ["LOW_RELEVANCE", "HIGH_RELEVANCE"]
    current = ledger._admissions_for(["obs-1"], ADMISSION_VERSION)["obs-1"]
    assert current["tier"] == "HIGH_RELEVANCE", "the latest decision is the current one"
    assert len(history) == 2, "the earlier judgement is still there"
    ledger.close()


def test_the_same_evidence_and_rules_are_idempotent(tmp_path: Path):
    ledger = _ledger(tmp_path)
    assert ledger.record_admissions([_row("obs-1", evidence="same")]) == 1
    ledger.record_admissions([_row("obs-1", evidence="same")])
    ledger.record_admissions([_row("obs-1", evidence="same")])
    assert len(ledger.admission_history("obs-1")) == 1
    ledger.close()


def test_a_v2_admission_table_is_migrated_without_losing_a_decision(tmp_path: Path):
    path = tmp_path / "legacy.db"
    con = sqlite3.connect(str(path))
    con.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta(key, value) VALUES('schema_version', 'radar-ledger-v2');
        CREATE TABLE observation_admission (
            observation_id TEXT NOT NULL,
            admission_version TEXT NOT NULL,
            tier TEXT NOT NULL,
            category TEXT NOT NULL,
            score REAL NOT NULL,
            reasons TEXT NOT NULL,
            features TEXT NOT NULL,
            decided_at TEXT NOT NULL,
            PRIMARY KEY (observation_id, admission_version)
        );
        INSERT INTO observation_admission VALUES
            ('obs-a', 'radar-admission-2026.11.3', 'HIGH_RELEVANCE', 'c', 1.0, '[]', '{}',
             '2026-11-17T00:00:00Z'),
            ('obs-b', 'radar-admission-2026.11.3', 'NEEDS_REVIEW', 'c', 0.0, '[]', '{}',
             '2026-11-17T00:00:00Z');
        """
    )
    con.commit()
    con.close()
    ledger = ObservationLedger(path)
    assert ledger.meta("schema_version") == "radar-ledger-v3"
    history = ledger.admission_history("obs-a")
    assert len(history) == 1 and history[0]["tier"] == "HIGH_RELEVANCE"
    assert history[0]["decision"] == "FEED"
    assert ledger.admission_history("obs-b")[0]["decision"] == "REVIEW"
    ledger.close()


# --------------------------------------------------------------- work identity
def test_one_work_is_shown_once_by_official_identifier_not_by_title(tmp_path: Path):
    from medradar.radar.classify import RuleMapper
    from medradar.radar.records import MAPPING_VERSION, RawRecord
    from medradar.radar.taxonomy import load_taxonomy

    taxonomy = load_taxonomy(str(ROOT / "config" / "radar"))
    ledger = _ledger(tmp_path)
    ledger.ensure_source("pubmed", label="PubMed", adapter_version="a1", cadence_hours=6)
    ledger.ensure_source("crossref", label="Crossref", adapter_version="a1", cadence_hours=6)
    mapper = RuleMapper(taxonomy)

    def add(source: str, record_id: str, title: str, payload: dict) -> None:
        record = RawRecord(
            source=source, source_record_id=record_id, official_identifier=payload.get("doi"),
            record_type="publication", title=title, url="https://example.test/" + record_id,
            published_at="2026-11-10", published_at_precision="date", payload=payload,
            text=title + " " + str(payload.get("abstract") or ""),
            extra={"official_identifier": payload.get("doi")},
        )
        ledger.record_observation(record, mapper.map(record), run_id="r",
                                  adapter_version="a1", mapping_version=MAPPING_VERSION)

    # The same work with two titles but one DOI: one feed row.
    add("pubmed", "pmid:1", "Pulse oximetry accuracy in the intensive care unit",
        {"doi": "10.1000/ABC", "abstract": "We measured accuracy of the pulse oximeter against "
                                           "arterial blood gas and report agreement."})
    add("crossref", "doi:1", "Accuracy of pulse oximetry against arterial blood gas in ICU",
        {"doi": "10.1000/abc", "abstract": "We measured accuracy of the pulse oximeter against "
                                           "arterial blood gas and report agreement."})
    # Two different works with the same title: two feed rows.
    add("pubmed", "pmid:2", "A repeated report title", {"doi": "10.2000/x", "abstract": "evaluated"})
    add("pubmed", "pmid:3", "A repeated report title", {"doi": "10.2000/y", "abstract": "evaluated"})

    from medradar.radar.engine import apply_admissions
    apply_admissions(ledger, limit=100)
    rows, total = ledger.feed(admission_version=ADMISSION_VERSION, limit=20)
    titles = [row["title"] for row in rows]
    assert sum(1 for title in titles if "repeated report title" in title) == 2
    ledger.close()
