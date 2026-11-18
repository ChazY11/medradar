"""Archive / candidate / intelligence separation, importance grading and the weekly brief.

The measured problems these tests hold shut:

* 7,360 of 8,593 admitted observations were FEED and 95.6% of them were older than 24 months, so
  "the feed has a lot of records" looked like "there is news";
* importance was a constant (8,590 MEDIUM / 3 HIGH);
* an openFDA 510(k) row (decision date, no publication date) was labelled undated because the
  novelty rule read published_at_precision first;
* one recall event with several product rows would have become several brief items.

Everything here runs on a temporary ledger; no network and no production data.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from medradar.radar.assessment import (
    IMPORTANCE_CRITICAL,
    IMPORTANCE_HIGH,
    IMPORTANCE_LOW,
    IMPORTANCE_MEDIUM,
    assess_observation,
    grade_importance,
)
from medradar.radar.intelligence import (
    ARCHIVE,
    CANDIDATE,
    FIRST_DISCOVERED_HISTORICAL,
    INTELLIGENCE,
    NEW_EVENT,
    REVIEW_AGENT_VERIFIED,
    REVIEW_NOT_REVIEWED,
    UNDATED_FIRST_DISCOVERY,
    UPDATED_EVENT,
    build_brief,
    distinguish_novelty,
    evaluate,
    event_identity,
    render_markdown,
    view_for,
)
from medradar.radar.ledger import ObservationLedger
from medradar.radar.records import MappingResult, RawRecord
from medradar.radar.taxonomy import load_taxonomy

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "radar"
WINDOW = ("2026-10-19", "2026-11-18")


# --------------------------------------------------------------------- fixtures
def _admission(ledger, observation_id, *, decision="FEED", dimensions=None, version="radar-assessment-test"):
    ledger.record_admissions([{
        "observation_id": observation_id,
        "admission_version": version,
        "tier": "HIGH_RELEVANCE",
        "category": "monitoring_technology_evaluation",
        "score": 5.0,
        "reasons": json.dumps(["a stated reason"], ensure_ascii=False),
        "features": "{}",
        "decision": decision,
        "dimensions": json.dumps(dimensions or {
            "monitoring_relevance": "DIRECT",
            "medical_domain": "MEDICAL",
            "importance": IMPORTANCE_HIGH,
            "importance_reasons": ["a stated importance reason"],
            "decision": decision,
        }, ensure_ascii=False),
        "rules_digest": "test",
        "evidence_key": observation_id[:8] + version,
        "judged_version_id": None,
        "decided_at": "2026-11-18T00:00:00Z",
    }])


def _publication(ledger, index, *, title=None, published="2026-11-10", first_observed="2026-11-16T00:00:00+00:00",
                 record_id=None, url="https://pubmed.ncbi.nlm.nih.gov/1/"):
    record = RawRecord(
        source="pubmed",
        source_record_id=record_id or "pmid:" + str(index),
        official_identifier="PMID:" + str(index),
        record_type="publication",
        title=title or ("Study " + str(index)),
        url=url,
        published_at=published,
        published_at_precision="date",
        payload={"abstract": "SpO2 monitoring"},
        text="SpO2 monitoring",
    )
    outcome = ledger.record_observation(record, MappingResult(), run_id="run-1",
                                       adapter_version="test-1", seen_at=first_observed)
    return outcome.observation_id


def _recall(ledger, *, product, event, published, first_observed="2026-11-16T00:00:00+00:00",
            reason="The device may fail to alarm on a low oxygen saturation"):
    payload = {
        "cfres_id": product,
        "product_res_number": product,
        "res_event_number": event,
        "recalling_firm": "Example Medical",
        "product_code": "MHX",
        "product_description": "Example Patient Monitor, model " + product,
        "reason_for_recall": reason,
        "root_cause_description": "Software design",
        "action": "Customer letter",
        "recall_status": "Open, Classified",
        "event_date_initiated": published,
        "event_date_posted": published,
        "openfda_device": {"device_name": "Monitor, Physiological, Patient", "device_class": "2"},
    }
    record = RawRecord(
        source="openfda_recall",
        source_record_id="recall:" + product,
        official_identifier=product,
        record_type="regulatory_record",
        title=payload["product_description"],
        url="https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfRes/res.cfm?id=" + event,
        event_at=published,
        event_at_precision="date",
        published_at=published,
        published_at_precision="date",
        payload=payload,
        extra={"identifiers": [("FDA_RECALL_EVENT", event), ("FDA_RECALL_PRODUCT", product)]},
    )
    outcome = ledger.record_observation(record, MappingResult(), run_id="run-1",
                                       adapter_version="test-1", seen_at=first_observed)
    return outcome.observation_id


@pytest.fixture()
def ledger(tmp_path: Path) -> ObservationLedger:
    handle = ObservationLedger(tmp_path / "radar.db")
    yield handle
    handle.close()


# --------------------------------------------------------------------- novelty
def test_a_record_published_inside_the_window_is_a_new_event():
    row = {"published_at": "2026-11-10", "published_at_precision": "date",
           "first_observed_at": "2026-11-16T00:00:00+00:00"}
    novelty, _ = distinguish_novelty(row, start=_day(WINDOW[0]), end=_day(WINDOW[1]))
    assert novelty == NEW_EVENT


def test_an_old_record_first_collected_now_is_a_historical_supplement_not_news():
    row = {"published_at": "2024-03-01", "published_at_precision": "date",
           "first_observed_at": "2026-11-16T00:00:00+00:00", "version_count": 1}
    novelty, reasons = distinguish_novelty(row, start=_day(WINDOW[0]), end=_day(WINDOW[1]))
    assert novelty == FIRST_DISCOVERED_HISTORICAL
    assert any("historical" in reason for reason in reasons)


def test_a_510k_row_with_a_decision_date_and_no_publication_date_is_not_undated():
    # Regression: the real ledger had 6,967 such rows labelled undated because the rule read
    # published_at_precision ('unknown') before event_at_precision ('date').
    row = {"published_at": None, "published_at_precision": "unknown",
           "event_at": "2026-11-02", "event_at_precision": "date",
           "first_observed_at": "2026-11-16T00:00:00+00:00"}
    novelty, _ = distinguish_novelty(row, start=_day(WINDOW[0]), end=_day(WINDOW[1]))
    assert novelty == NEW_EVENT


def test_a_record_with_no_date_at_all_is_undated_and_never_called_new():
    row = {"published_at": None, "event_at": None, "published_at_precision": "unknown",
           "event_at_precision": "unknown", "first_observed_at": "2026-11-16T00:00:00+00:00"}
    novelty, _ = distinguish_novelty(row, start=_day(WINDOW[0]), end=_day(WINDOW[1]))
    assert novelty == UNDATED_FIRST_DISCOVERY


def test_a_content_change_inside_the_window_is_an_update_not_a_new_event():
    row = {"published_at": "2025-01-01", "published_at_precision": "date",
           "first_observed_at": "2026-01-01T00:00:00+00:00", "version_count": 2,
           "current_change_state": "UPDATED", "last_change_at": "2026-11-01T00:00:00+00:00"}
    novelty, _ = distinguish_novelty(row, start=_day(WINDOW[0]), end=_day(WINDOW[1]))
    assert novelty == UPDATED_EVENT


def _day(value):
    from datetime import date

    return date.fromisoformat(value)


# --------------------------------------------------------------------- views
def _row(**overrides):
    base = {
        "observation_id": "o1", "source_url": "https://example.test/1",
        "official_identifier": "ID-1", "decision": "FEED",
        "dimensions": json.dumps({"monitoring_relevance": "DIRECT", "medical_domain": "MEDICAL",
                                  "importance": IMPORTANCE_HIGH}),
        "admission_reasons": json.dumps(["a reason"]),
        "payload": {},
    }
    base.update(overrides)
    return base


def test_an_unchanged_record_is_archive():
    view, _ = view_for(_row(), novelty="ARCHIVE_ONLY")
    assert view == ARCHIVE


def test_an_excluded_record_is_archive_and_keeps_its_reason():
    view, reasons = view_for(_row(decision="EXCLUDED"), novelty=NEW_EVENT)
    assert view == ARCHIVE
    assert "outside the monitoring scope" in reasons[0]


def test_a_fresh_monitoring_record_with_evidence_is_deliverable_intelligence():
    view, _ = view_for(_row(), novelty=NEW_EVENT)
    assert view == INTELLIGENCE


def test_a_row_without_a_source_url_is_only_a_candidate():
    view, reasons = view_for(_row(source_url=None), novelty=NEW_EVENT)
    assert view == CANDIDATE
    assert any("URL" in reason for reason in reasons)


def test_an_important_historical_record_is_a_candidate_supplement():
    dimensions = json.dumps({"monitoring_relevance": "DIRECT", "medical_domain": "MEDICAL",
                             "importance": IMPORTANCE_CRITICAL})
    view, reasons = view_for(_row(dimensions=dimensions), novelty=FIRST_DISCOVERED_HISTORICAL)
    assert view == CANDIDATE
    assert any("historical" in reason for reason in reasons)


def test_a_low_importance_historical_record_stays_in_the_archive():
    dimensions = json.dumps({"monitoring_relevance": "DIRECT", "medical_domain": "MEDICAL",
                             "importance": IMPORTANCE_LOW})
    view, _ = view_for(_row(dimensions=dimensions), novelty=FIRST_DISCOVERED_HISTORICAL)
    assert view == ARCHIVE


# --------------------------------------------------------------------- importance
def test_an_open_safety_action_with_a_stated_consequence_is_critical():
    level, reasons = grade_importance(
        record_type="regulatory_record", category="monitoring_safety_action", decision="FEED",
        relevance="DIRECT", freshness="FRESH",
        payload={"reason_for_recall": "The monitor may freeze and cause loss of monitoring",
                 "recall_status": "Open, Classified"},
        recall_verdict={"in_scope": True, "reason": "product code MHX"},
    )
    assert level == IMPORTANCE_CRITICAL
    assert any("patient-safety consequence" in reason for reason in reasons)


def test_a_terminated_action_is_not_critical():
    level, _ = grade_importance(
        record_type="regulatory_record", category="monitoring_safety_action", decision="FEED",
        relevance="DIRECT", freshness="STALE",
        payload={"reason_for_recall": "The monitor may freeze and cause loss of monitoring",
                 "recall_status": "Terminated"},
        recall_verdict={"in_scope": True, "reason": "product code MHX"},
    )
    assert level in (IMPORTANCE_MEDIUM, IMPORTANCE_HIGH)


def test_a_routine_clearance_inside_the_year_is_medium_not_high():
    level, _ = grade_importance(
        record_type="regulatory_record", category="regulatory_monitoring_device", decision="FEED",
        relevance="DIRECT", freshness="RECENT",
    )
    assert level == IMPORTANCE_MEDIUM


def test_a_stale_record_is_low():
    level, reasons = grade_importance(
        record_type="publication", category="monitoring_technology_evaluation", decision="FEED",
        relevance="DIRECT", freshness="STALE",
    )
    assert level == IMPORTANCE_LOW
    assert any("historical archive" in reason for reason in reasons)


def test_a_single_patient_study_cannot_be_high():
    level, _ = grade_importance(
        record_type="publication", category="monitoring_technology_evaluation", decision="FEED",
        relevance="DIRECT", freshness="FRESH", strict_evaluation=True,
        title="Feasibility of bracelet oximetry: a single-patient case study",
    )
    assert level == IMPORTANCE_MEDIUM


def test_the_grade_is_not_a_constant_across_a_realistic_mix():
    taxonomy = load_taxonomy(str(CONFIG_DIR))
    fresh = assess_observation({
        "record_type": "publication",
        "title": "Accuracy of non-invasive blood pressure monitoring in critically ill adults",
        "payload": {"abstract": "We evaluated agreement against the reference standard in ICU patients."},
        "published_at": "2026-11-10", "published_at_precision": "date",
    }, taxonomy=taxonomy)
    stale = assess_observation({
        "record_type": "publication",
        "title": "Accuracy of non-invasive blood pressure monitoring in critically ill adults",
        "payload": {"abstract": "We evaluated agreement against the reference standard in ICU patients."},
        "published_at": "2019-01-10", "published_at_precision": "date",
    }, taxonomy=taxonomy)
    assert fresh.dimensions["importance"] == IMPORTANCE_HIGH
    assert stale.dimensions["importance"] == IMPORTANCE_LOW
    assert fresh.dimensions["importance_reasons"], "every grade must carry its reasons"


def test_a_narrative_review_cannot_be_high_on_the_word_accuracy():
    level, reasons = grade_importance(
        record_type="publication", category="monitoring_technology_evaluation", decision="FEED",
        relevance="DIRECT", freshness="FRESH", strict_evaluation=True,
        title="Beyond classification accuracy: trustworthy AI for clinical EEG",
    )
    assert level == IMPORTANCE_MEDIUM
    assert any("review" in reason for reason in reasons)


def test_a_systematic_review_still_counts_as_primary_synthesis():
    level, _ = grade_importance(
        record_type="publication", category="monitoring_technology_evaluation", decision="FEED",
        relevance="DIRECT", freshness="FRESH", strict_evaluation=True,
        title="Accuracy of non-invasive arterial pressure monitoring: a systematic review and meta-analysis",
    )
    assert level == IMPORTANCE_HIGH


def test_every_grade_records_reasons():
    for level_payload in ({}, {"recall_status": "Open, Classified"}):
        level, reasons = grade_importance(
            record_type="publication", category="x", decision="REVIEW",
            relevance="TRANSFER", freshness="RECENT", payload=level_payload,
        )
        assert level in (IMPORTANCE_CRITICAL, IMPORTANCE_HIGH, IMPORTANCE_MEDIUM, IMPORTANCE_LOW)
        assert reasons


# --------------------------------------------------------------------- the brief
def test_the_brief_delivers_recent_items_and_keeps_old_ones_in_the_archive(ledger):
    new_id = _publication(ledger, 1, title="A fresh monitoring study", published="2026-11-10")
    old_id = _publication(ledger, 2, title="An old monitoring study", published="2020-01-10")
    _admission(ledger, new_id)
    _admission(ledger, old_id, dimensions={
        "monitoring_relevance": "DIRECT", "medical_domain": "MEDICAL",
        "importance": IMPORTANCE_LOW, "importance_reasons": ["historical archive"],
        "decision": "FEED",
    })
    brief = build_brief(ledger, start=WINDOW[0], end=WINDOW[1],
                        generated_at="2026-11-18T00:00:00Z")
    titles = [item["title"] for item in brief.items]
    assert titles == ["A fresh monitoring study"], titles
    assert brief.counts["views"][ARCHIVE] >= 1


def test_one_recall_event_with_several_product_rows_is_one_item(ledger):
    first = _recall(ledger, product="Z-1", event="90001", published="2026-11-05")
    second = _recall(ledger, product="Z-2", event="90001", published="2026-11-05")
    _admission(ledger, first)
    _admission(ledger, second)
    brief = build_brief(ledger, start=WINDOW[0], end=WINDOW[1],
                        generated_at="2026-11-18T00:00:00Z")
    assert len(brief.items) == 1
    assert brief.items[0]["event_identity"] == "FDA_RECALL_EVENT:90001"
    assert list(brief.index) == ["FDA_RECALL_EVENT:90001"], (
        "the event index must use the stored recall event identifier, not the row work key"
    )
    assert brief.counts["events_collapsed_from_rows"] == 1
    assert brief.duplicate_events


def test_an_important_historical_recall_is_a_supplement_not_a_headline(ledger):
    old = _recall(ledger, product="Z-9", event="80001", published="2024-05-05")
    _admission(ledger, old, dimensions={
        "monitoring_relevance": "DIRECT", "medical_domain": "MEDICAL",
        "importance": IMPORTANCE_CRITICAL, "importance_reasons": ["stated"],
        "decision": "FEED",
    })
    brief = build_brief(ledger, start=WINDOW[0], end=WINDOW[1],
                        generated_at="2026-11-18T00:00:00Z")
    assert brief.items == []
    assert len(brief.historical) == 1
    assert brief.historical[0]["novelty"] == FIRST_DISCOVERED_HISTORICAL


def test_a_backfilled_recent_event_is_labelled_with_its_import(ledger):
    from medradar.radar.records import ORIGIN_BACKFILLED

    record = RawRecord(
        source="openfda_recall", source_record_id="recall:Z-77", official_identifier="Z-77",
        record_type="regulatory_record", title="Example Patient Monitor",
        url="https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfRes/res.cfm?id=70001",
        event_at="2026-11-01", event_at_precision="date",
        published_at="2026-11-01", published_at_precision="date",
        payload={"res_event_number": "70001", "product_res_number": "Z-77",
                 "product_code": "MHX", "reason_for_recall": "Display freezes",
                 "recall_status": "Open, Classified"},
    )
    outcome = ledger.record_observation(record, MappingResult(), run_id="run-b",
                                        adapter_version="test-1", origin=ORIGIN_BACKFILLED,
                                        backfill_reason="test import")
    _admission(ledger, outcome.observation_id)
    brief = build_brief(ledger, start=WINDOW[0], end=WINDOW[1],
                        generated_at="2026-11-18T00:00:00Z")
    row = [item for item in brief.items if item["event_identity"].endswith("70001")]
    assert row, brief.items
    assert row[0]["discovery_phase"] == "HISTORICAL_BACKFILL"
    assert row[0]["observation_origin"] == "BACKFILLED"


def test_the_brief_marks_unreviewed_items_as_unreviewed(ledger):
    observation = _publication(ledger, 3, title="A fresh monitoring study", published="2026-11-10")
    _admission(ledger, observation)
    brief = build_brief(ledger, start=WINDOW[0], end=WINDOW[1],
                        generated_at="2026-11-18T00:00:00Z")
    assert brief.items[0]["review_status"] == REVIEW_NOT_REVIEWED
    reviewed = build_brief(ledger, start=WINDOW[0], end=WINDOW[1],
                           generated_at="2026-11-18T00:00:00Z",
                           review={brief.items[0]["event_identity"]: REVIEW_AGENT_VERIFIED})
    assert reviewed.items[0]["review_status"] == REVIEW_AGENT_VERIFIED


def test_the_markdown_brief_carries_every_required_field(ledger):
    observation = _publication(ledger, 4, title="A fresh monitoring study", published="2026-11-10")
    _admission(ledger, observation)
    brief = build_brief(ledger, start=WINDOW[0], end=WINDOW[1],
                        generated_at="2026-11-18T00:00:00Z")
    markdown = render_markdown(brief)
    for fragment in ("窗口 / window", "重要性 / importance", "事件日期 / event date",
                     "公开日期 / published", "系统发现 / first observed", "原始链接 / source URL",
                     "为什么与监护安全或性能有关", "研发关注点", "不确定性", "复核状态",
                     "字段依据", "方法与限制"):
        assert fragment in markdown, fragment
    assert "No item passed the deliverable gate" not in markdown


def test_the_metrics_report_their_denominators(ledger):
    observation = _publication(ledger, 5, title="A fresh monitoring study", published="2026-11-10")
    _admission(ledger, observation)
    brief = build_brief(ledger, start=WINDOW[0], end=WINDOW[1],
                        generated_at="2026-11-18T00:00:00Z")
    reference = [{"ref_id": "R1", "official_identifier": "PMID:5"},
                 {"ref_id": "R2", "official_identifier": "PMID:999"}]
    metrics = evaluate(brief, reference)
    assert metrics["reference_events"] == 2
    assert metrics["reference_matched"] == 1
    assert metrics["reference_delivered_in_brief"] == 1
    assert metrics["recall"] == 0.5
    assert metrics["reference_unmatched"] == 1
    assert metrics["reference_unmatched_entries"][0]["ref_id"] == "R2"
    assert metrics["review_coverage"] == 0.0
    assert metrics["limitations"]
