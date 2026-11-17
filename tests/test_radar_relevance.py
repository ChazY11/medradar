"""Relevance of a publication to monitoring *technology*, not to monitoring use.

The first batch admitted papers that used ICU monitoring data to predict deterioration: a
clinical study, not device research. These tests pin the gate that separates the two, and pin
that a decision-support-only paper produces no product-capability evidence at all.
"""

from __future__ import annotations

from pathlib import Path

import unittest

try:  # the repository's `medradar selftest` runs under unittest without pytest installed
    import pytest
except ModuleNotFoundError:  # pragma: no cover
    raise unittest.SkipTest("pytest is not installed; run these tests with pytest")

from medradar.radar.classify import RuleMapper, publication_relevance
from medradar.radar.records import MAPPING_VERSION, RawRecord
from medradar.radar.taxonomy import load_taxonomy

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "radar"


def _mapper() -> RuleMapper:
    return RuleMapper(load_taxonomy(str(CONFIG_DIR)))


def _paper(text: str, *, affiliations=(), title: str | None = None) -> RawRecord:
    title = title or text[:80]
    return RawRecord(
        source="pubmed", source_record_id="pmid:1", official_identifier="PMID:1",
        record_type="publication", title=title, url="https://pubmed.ncbi.nlm.nih.gov/1/",
        published_at="2026-02-01", published_at_precision="date",
        payload={"pmid": "1", "title": title, "abstract": text},
        text=f"{title} {text}", extra={"affiliations": list(affiliations)},
    )


def test_a_clinical_study_that_only_consumes_monitoring_data_is_out_of_scope():
    record = _paper(
        "A machine learning model predicted clinical deterioration of ICU patients from "
        "electronic health record data. Early warning score performance was compared."
    )
    mapping = _mapper().map(record)
    accepted, reason = publication_relevance(mapping)
    assert accepted is False
    assert "clinical study" in reason
    assert "predictive_deterioration" in reason


def test_a_monitoring_technology_study_is_in_scope():
    record = _paper(
        "We developed a new algorithm for arrhythmia detection from 12-lead ECG signals "
        "and evaluated its false alarm rate on a patient monitor."
    )
    mapping = _mapper().map(record)
    accepted, _reason = publication_relevance(mapping)
    assert accepted is True
    assert any(topic["family"] == "electrocardiography" for topic in mapping.technology_topics)


def test_a_vendor_affiliation_admits_a_decision_support_paper():
    record = _paper(
        "We evaluated deterioration prediction from ICU vital signs.",
        affiliations=["Philips Research, Eindhoven, the Netherlands"],
    )
    mapping = _mapper().map(record)
    accepted, _reason = publication_relevance(mapping)
    assert accepted is True
    assert any(candidate["role"] == "publication_affiliation"
               for candidate in mapping.organization_candidates)


def test_generic_model_words_no_longer_create_a_decision_support_topic():
    """`machine learning` alone used to match the decision-support topic in any paper."""
    record = _paper("A machine learning pipeline for hospital bed demand forecasting.")
    mapping = _mapper().map(record)
    assert [topic["topic_id"] for topic in mapping.technology_topics] == []


def test_a_decision_support_publication_produces_no_capability_edge(tmp_path: Path):
    from medradar.radar.graph import (EDGE_PRODUCT_CAPABILITY, TechnologyGraph, open_graph)
    from medradar.radar.ledger import ObservationLedger
    from medradar.tkg import TKGStore

    taxonomy = load_taxonomy(str(CONFIG_DIR))
    ledger = ObservationLedger(tmp_path / "radar.db")
    ledger.ensure_source("pubmed", label="PubMed", adapter_version="a1", cadence_hours=6)
    record = _paper(
        "Deep learning predicted sepsis from electronic health record data in the ICU."
    )
    ledger.record_observation(record, _mapper().map(record), run_id="r", adapter_version="a1",
                              mapping_version=MAPPING_VERSION)
    graph = TechnologyGraph(TKGStore(str(tmp_path / "graph.db")), taxonomy)
    graph.materialize(ledger, limit=50, log=lambda _m: None)
    snapshot = graph.query.snapshot()
    assert not [edge for edge in snapshot["edges"] if edge["edge_type"] == EDGE_PRODUCT_CAPABILITY]
    ledger.close()
    graph.store.close()
