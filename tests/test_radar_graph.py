"""The Company Technology Graph: confirmation levels, evidence and the two clocks.

The product claim under test is narrow and checkable: every branch in the technology map is
produced from assertions that carry an evidence id, and the confirmation level of an edge is
never higher than the evidence supports. A regulatory clearance must not become an algorithm
claim; a paper affiliation must not become a product capability.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path


import unittest

try:  # the repository's `medradar selftest` runs under unittest without pytest installed
    import pytest
except ModuleNotFoundError:  # pragma: no cover
    raise unittest.SkipTest("pytest is not installed; run these tests with pytest")

from medradar.radar.graph import (
    EDGE_CANDIDATE_PRODUCT,
    EDGE_COMPANY_PRODUCT,
    EDGE_DOCUMENT_COMPANY,
    EDGE_IDENTIFIER_MATCH,
    EDGE_PRODUCT_CAPABILITY,
    EDGE_PUBLICATION_TOPIC,
    EDGE_REGULATORY_PRODUCT,
    GRAPH_VERSION,
    NODE_COMPANY,
    TechnologyGraph,
    company_node_id,
    topic_node_id,
)
from medradar.radar.ledger import ObservationLedger
from medradar.radar.records import MAPPING_VERSION, RawRecord
from medradar.radar.taxonomy import load_taxonomy
from medradar.tkg import TKGStore

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "radar"


def _taxonomy():
    return load_taxonomy(str(CONFIG_DIR))


def _ledger(tmp_path: Path) -> ObservationLedger:
    handle = ObservationLedger(tmp_path / "radar.db")
    handle.ensure_source("openfda_device", label="FDA", adapter_version="a1", cadence_hours=24)
    handle.ensure_source("pubmed", label="PubMed", adapter_version="a1", cadence_hours=6)
    handle.ensure_source("philips_official", label="Philips", adapter_version="a1", cadence_hours=12)
    return handle


def _fda(ledger: ObservationLedger, *, applicant="Philips Medical Systems",
         device="INTELLIVUE MX800 PATIENT MONITOR", code="MHX", k="K240001"):
    record = RawRecord(
        source="openfda_device", source_record_id=f"510k:{k}", official_identifier=k,
        record_type="regulatory_record", title=device,
        url=f"https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID={k}",
        event_at="2026-03-04", event_at_precision="date",
        payload={"k_number": k, "device_name": device, "applicant": applicant,
                 "product_code": code, "decision_date": "2026-03-04"},
        text=device,
        extra={"organization_hint": applicant, "organization_role": "regulatory_applicant",
               "product_codes": [code], "product_hint": device, "product_identifier": k},
    )
    from medradar.radar.classify import RuleMapper

    return ledger.record_observation(record, RuleMapper(_taxonomy()).map(record),
                                     run_id="r-fda", adapter_version="a1",
                                     mapping_version=MAPPING_VERSION)


def _publication(ledger: ObservationLedger, *, pmid="40000001", title="Alarm fatigue in the ICU"):
    record = RawRecord(
        source="pubmed", source_record_id=f"pmid:{pmid}", official_identifier=f"PMID:{pmid}",
        record_type="publication", title=title,
        url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        published_at="2026-02-01", published_at_precision="date",
        payload={"pmid": pmid, "title": title,
                 "abstract": "Alarm fatigue and signal quality in intensive care monitoring."},
        text=title + " Alarm fatigue and signal quality in intensive care monitoring.",
        extra={"organization_hint": "Philips Research",
               "organization_role": "publication_affiliation",
               "affiliations": ["Philips Research"]},
    )
    from medradar.radar.classify import RuleMapper

    return ledger.record_observation(record, RuleMapper(_taxonomy()).map(record),
                                     run_id="r-pub", adapter_version="a1",
                                     mapping_version=MAPPING_VERSION)


def _press(ledger: ObservationLedger, *, title="Philips introduces modular monitor with SpO2"):
    record = RawRecord(
        source="philips_official", source_record_id="philips:2026:modular",
        official_identifier="https://www.philips.com/press/modular",
        record_type="press_release", title=title,
        url="https://www.philips.com/press/modular",
        published_at="2026-04-01T09:00:00+00:00", published_at_precision="datetime",
        payload={"title": title, "description": "A modular patient monitor with SpO2."},
        text=title + " A modular patient monitor with SpO2.",
        extra={"organization_hint": "Royal Philips", "organization_role": "official_publisher",
               "publisher_hint": "Royal Philips", "product_hint": "Modular Monitor 9000"},
    )
    from medradar.radar.classify import RuleMapper

    return ledger.record_observation(record, RuleMapper(_taxonomy()).map(record),
                                     run_id="r-press", adapter_version="a1",
                                     mapping_version=MAPPING_VERSION)


def _graph(tmp_path: Path, *, clock=None) -> TechnologyGraph:
    store = TKGStore(str(tmp_path / "graph.db")) if clock is None else TKGStore(":memory:", clock=clock)
    return TechnologyGraph(store, _taxonomy())


def _edges(graph: TechnologyGraph, edge_type: str) -> list[dict]:
    snapshot = graph.query.snapshot()
    return [edge for edge in snapshot["edges"] if edge["edge_type"] == edge_type]


def test_materialisation_is_idempotent_and_evidence_bearing(tmp_path: Path):
    ledger = _ledger(tmp_path)
    _fda(ledger)
    graph = _graph(tmp_path)
    first = graph.materialize(ledger, limit=50, log=lambda _m: None)
    assert first["materialized"] == 1 and first["errors"] == []
    second = graph.materialize(ledger, limit=50, log=lambda _m: None)
    assert second["materialized"] == 0  # nothing pending after the same version
    edges = _edges(graph, EDGE_DOCUMENT_COMPANY)
    assert edges and all(edge["attrs"]["evidence_id"] for edge in edges)
    assert all(edge["attrs"]["source"] == "openfda_device" for edge in edges)
    ledger.close()
    graph.store.close()


def test_an_fda_clearance_creates_a_company_product_link_but_never_a_capability(tmp_path: Path):
    ledger = _ledger(tmp_path)
    _fda(ledger)
    graph = _graph(tmp_path)
    graph.materialize(ledger, limit=50, log=lambda _m: None)
    company_product = _edges(graph, EDGE_COMPANY_PRODUCT)
    assert company_product, "a confirmed applicant alias must support COMPANY_HAS_PRODUCT"
    assert company_product[0]["attrs"]["confirmation"] == "CONFIRMED"
    regulatory_product = _edges(graph, EDGE_REGULATORY_PRODUCT)
    assert regulatory_product
    # No capability edge is produced by a regulatory record.
    assert _edges(graph, EDGE_PRODUCT_CAPABILITY) == []
    ledger.close()
    graph.store.close()


def test_a_broad_legal_name_only_produces_a_candidate_product_relation(tmp_path: Path):
    ledger = _ledger(tmp_path)
    _fda(ledger, applicant="General Electric Co.", device="GE CARESCAPE MONITOR", k="K240002")
    graph = _graph(tmp_path)
    graph.materialize(ledger, limit=50, log=lambda _m: None)
    assert _edges(graph, EDGE_COMPANY_PRODUCT) == []
    candidates = _edges(graph, EDGE_CANDIDATE_PRODUCT)
    assert candidates and candidates[0]["attrs"]["confirmation"] == "CANDIDATE"
    ledger.close()
    graph.store.close()


def test_a_vendor_document_can_support_a_reported_capability(tmp_path: Path):
    ledger = _ledger(tmp_path)
    _press(ledger)
    graph = _graph(tmp_path)
    graph.materialize(ledger, limit=50, log=lambda _m: None)
    capability = _edges(graph, EDGE_PRODUCT_CAPABILITY)
    assert capability, "a vendor press release that states a capability may assert it"
    assert all(edge["attrs"]["confirmation"] == "CONFIRMED" for edge in capability)
    assert all(edge["attrs"]["basis"] == "vendor_document_states_topic" for edge in capability)
    ledger.close()
    graph.store.close()


def test_a_publication_discloses_a_topic_but_creates_no_product_or_capability(tmp_path: Path):
    ledger = _ledger(tmp_path)
    _publication(ledger)
    graph = _graph(tmp_path)
    graph.materialize(ledger, limit=50, log=lambda _m: None)
    assert _edges(graph, EDGE_PUBLICATION_TOPIC)
    assert _edges(graph, EDGE_PRODUCT_CAPABILITY) == []
    assert _edges(graph, EDGE_COMPANY_PRODUCT) == []
    # The affiliation is a document-mentions-company edge, nothing stronger.
    mentions = _edges(graph, EDGE_DOCUMENT_COMPANY)
    assert mentions and mentions[0]["dst"]["node_id"] == company_node_id("philips")
    ledger.close()
    graph.store.close()


def test_the_same_official_identifier_across_two_sources_is_a_confirmed_match(tmp_path: Path):
    ledger = _ledger(tmp_path)
    a = _publication(ledger, pmid="40000002", title="SpO2 monitoring study")
    # A second source publishing the same identifier (a DOI-style cross-source duplicate).
    record = RawRecord(
        source="crossref", source_record_id="doi:10.1/x", official_identifier="PMID:40000002",
        record_type="publication", title="SpO2 monitoring study",
        url="https://doi.org/10.1/x", published_at="2026-02-01", published_at_precision="date",
        payload={"doi": "10.1/x", "title": "SpO2 monitoring study"},
        text="SpO2 monitoring study",
        extra={"affiliations": []},
    )
    from medradar.radar.classify import RuleMapper

    ledger.record_observation(record, RuleMapper(_taxonomy()).map(record), run_id="r-cr",
                              adapter_version="a1", mapping_version=MAPPING_VERSION)
    graph = _graph(tmp_path)
    graph.materialize(ledger, limit=50, log=lambda _m: None)
    matches = _edges(graph, EDGE_IDENTIFIER_MATCH)
    assert matches, "two sources publishing the same identifier must be joined"
    assert matches[0]["attrs"]["confirmation"] == "CONFIRMED"
    ledger.close()
    graph.store.close()


def test_knowledge_time_excludes_evidence_discovered_later_while_public_time_does_not(tmp_path: Path):
    ledger = _ledger(tmp_path)
    clock = {"now": datetime(2026, 5, 1, tzinfo=timezone.utc)}
    graph = _graph(tmp_path, clock=lambda: clock["now"])
    _fda(ledger, k="K900001", device="MONITOR A")
    graph.materialize(ledger, limit=50, log=lambda _m: None)
    first_knowledge = graph.query.snapshot()["known_at"]

    # A second record is discovered a month later.
    clock["now"] = datetime(2026, 6, 1, tzinfo=timezone.utc)
    _fda(ledger, k="K900002", device="MONITOR B", code="DPS")
    graph.materialize(ledger, limit=50, log=lambda _m: None)

    earlier = graph.technology_map(known_at="2026-05-15T00:00:00Z")
    later = graph.technology_map()
    assert earlier["mode"] == "knowledge_time"
    assert earlier["valid_at"] is None
    # The June discovery cannot appear in the May knowledge view, even though the monitor it
    # describes may have been cleared earlier: knowledge time is when we learned about it.
    assert earlier["counts"]["edges"] < later["counts"]["edges"]
    assert "actually recorded at the cutoff" in earlier["time_semantics"]["statement"]

    reconstructed = graph.technology_map(valid_at="2026-05-15T00:00:00Z")
    assert reconstructed["mode"] == "public_time_reconstruction"
    assert reconstructed["reconstructed"] is True
    assert "reconstructed from today's knowledge" in reconstructed["time_semantics"]["statement"]
    assert first_knowledge
    ledger.close()
    graph.store.close()


def test_company_comparison_distinguishes_no_evidence_from_no_technology(tmp_path: Path):
    ledger = _ledger(tmp_path)
    _fda(ledger)
    graph = _graph(tmp_path)
    graph.materialize(ledger, limit=50, log=lambda _m: None)
    payload = graph.company_compare(companies=["philips", "draeger"])
    assert "does not mean the company lacks" in payload["no_evidence_means"]
    assert "does not rank companies" in payload["not_comparable_warning"]
    states = {
        (row["topic_id"], cell["organization_id"]): cell["state"]
        for row in payload["rows"] for cell in row["cells"]
    }
    assert states[("smart_alarms", "philips")] == "EVIDENCE_PRESENT"
    assert states[("smart_alarms", "draeger")] == "NO_EVIDENCE_FOUND"
    ledger.close()
    graph.store.close()


def test_a_shared_normalised_doi_joins_two_sources_even_with_different_titles(tmp_path: Path):
    """PMID and DOI are different official identifiers, so identifier equality cannot join them.

    The DOI that PubMed itself states is the bridge. The titles below are deliberately
    different: the relation must come from the normalised DOI, never from title similarity.
    """
    from medradar.radar.classify import RuleMapper

    ledger = _ledger(tmp_path)
    ledger.ensure_source("crossref", label="Crossref", adapter_version="a1", cadence_hours=12)
    shared_doi = "10.1097/CCM.0000000000005001"
    pubmed = RawRecord(
        source="pubmed", source_record_id="pmid:40000077", official_identifier="PMID:40000077",
        record_type="publication", title="Alarm fatigue in a modular intensive care monitor",
        url="https://pubmed.ncbi.nlm.nih.gov/40000077/",
        published_at="2026-02-01", published_at_precision="date",
        payload={"pmid": "40000077", "title": "Alarm fatigue in a modular intensive care monitor",
                 "abstract": "Alarm fatigue and signal quality in intensive care monitoring.",
                 "doi": shared_doi.upper()},
        text="Alarm fatigue and signal quality in intensive care monitoring.",
        extra={"affiliations": [], "doi": shared_doi.upper()},
    )
    crossref = RawRecord(
        source="crossref", source_record_id=f"doi:{shared_doi.lower()}",
        official_identifier=f"DOI:{shared_doi.lower()}",
        record_type="publication", title="A completely different running head",
        url=f"https://doi.org/{shared_doi}",
        published_at="2026-02-01", published_at_precision="date",
        payload={"doi": shared_doi.lower(), "title": "A completely different running head",
                 "abstract": "SpO2 and ECG monitoring in the ICU."},
        text="SpO2 and ECG monitoring in the ICU.",
        extra={"affiliations": [], "doi": shared_doi.lower()},
    )
    for record in (pubmed, crossref):
        ledger.record_observation(record, RuleMapper(_taxonomy()).map(record), run_id="r",
                                  adapter_version="a1", mapping_version=MAPPING_VERSION)
    graph = _graph(tmp_path)
    graph.materialize(ledger, limit=50, log=lambda _m: None)
    doi_edges = [edge for edge in _edges(graph, EDGE_IDENTIFIER_MATCH)
                 if edge["attrs"].get("method") == "doi_exact_match"]
    assert len(doi_edges) == 1
    edge = doi_edges[0]
    assert edge["attrs"]["confirmation"] == "CONFIRMED"
    assert edge["attrs"]["identifier_kind"] == "DOI"
    assert edge["attrs"]["identifier_value"] == shared_doi.lower()
    assert edge["attrs"]["other_source"] in ("pubmed", "crossref")
    ledger.close()
    graph.store.close()


def test_a_late_arriving_doi_peer_joins_without_waiting_for_its_own_revisit(tmp_path: Path):
    """The corroboration case: Crossref states a DOI long after the PubMed row was materialised.

    The already-materialised side must be invalidated when the new identifier arrives, otherwise
    the joining edge is only written if the *new* record happens to sort first.
    """
    from medradar.radar.classify import RuleMapper

    ledger = _ledger(tmp_path)
    ledger.ensure_source("crossref", label="Crossref", adapter_version="a1", cadence_hours=12)
    doi = "10.1093/ajhp/zxag364"
    pubmed = RawRecord(
        source="pubmed", source_record_id="pmid:40000099", official_identifier="PMID:40000099",
        record_type="publication", title="Alarm fatigue and signal quality in ICU monitoring",
        url="https://pubmed.ncbi.nlm.nih.gov/40000099/",
        published_at="2026-02-01", published_at_precision="date",
        payload={"pmid": "40000099", "title": "Alarm fatigue and signal quality in ICU monitoring",
                 "abstract": "Alarm fatigue and signal quality in intensive care monitoring.",
                 "doi": doi},
        text="Alarm fatigue and signal quality in intensive care monitoring.",
        extra={"affiliations": [], "doi": doi},
    )
    ledger.record_observation(pubmed, RuleMapper(_taxonomy()).map(pubmed), run_id="r",
                              adapter_version="a1", mapping_version=MAPPING_VERSION)
    graph = _graph(tmp_path)
    graph.materialize(ledger, limit=50, log=lambda _m: None)
    assert _edges(graph, EDGE_IDENTIFIER_MATCH) == []

    crossref = RawRecord(
        source="crossref", source_record_id=f"doi:{doi}", official_identifier=f"DOI:{doi}",
        record_type="publication", title="Alarm fatigue and signal quality in ICU monitoring",
        url=f"https://doi.org/{doi}", published_at="2026-02-01", published_at_precision="date",
        payload={"doi": doi, "title": "Alarm fatigue and signal quality in ICU monitoring",
                 "abstract": "SpO2 and ECG monitoring in the ICU."},
        text="SpO2 and ECG monitoring in the ICU.", extra={"affiliations": [], "doi": doi},
    )
    ledger.record_observation(crossref, RuleMapper(_taxonomy()).map(crossref), run_id="r",
                              adapter_version="a1", mapping_version=MAPPING_VERSION)
    graph.materialize(ledger, limit=50, log=lambda _m: None)
    matches = [edge for edge in _edges(graph, EDGE_IDENTIFIER_MATCH)
               if edge["attrs"].get("method") == "doi_exact_match"]
    assert len(matches) == 1
    ledger.close()
    graph.store.close()


def test_a_different_doi_never_joins_two_publications(tmp_path: Path):
    from medradar.radar.classify import RuleMapper

    ledger = _ledger(tmp_path)
    ledger.ensure_source("crossref", label="Crossref", adapter_version="a1", cadence_hours=12)
    for source, identifier, doi in (
        ("pubmed", "PMID:40000078", "10.1097/ccm.0000000000005002"),
        ("crossref", "DOI:10.1097/ccm.0000000000005003", "10.1097/ccm.0000000000005003"),
    ):
        record = RawRecord(
            source=source, source_record_id=identifier.lower(), official_identifier=identifier,
            record_type="publication", title="SpO2 oximetry in intensive care monitoring",
            url="https://example.test/x", published_at="2026-02-01", published_at_precision="date",
            payload={"doi": doi, "title": "SpO2 oximetry in intensive care monitoring",
                     "abstract": "pulse oximetry oxygen saturation"},
            text="pulse oximetry oxygen saturation", extra={"affiliations": [], "doi": doi},
        )
        ledger.record_observation(record, RuleMapper(_taxonomy()).map(record), run_id="r",
                                  adapter_version="a1", mapping_version=MAPPING_VERSION)
    graph = _graph(tmp_path)
    graph.materialize(ledger, limit=50, log=lambda _m: None)
    assert _edges(graph, EDGE_IDENTIFIER_MATCH) == []
    ledger.close()
    graph.store.close()


def test_changes_between_two_knowledge_times_reports_the_added_assertions(tmp_path: Path):
    ledger = _ledger(tmp_path)
    clock = {"now": datetime(2026, 5, 1, tzinfo=timezone.utc)}
    graph = _graph(tmp_path, clock=lambda: clock["now"])
    _fda(ledger, k="K900010")
    graph.materialize(ledger, limit=50, log=lambda _m: None)
    # An explicit knowledge cutoff: ``snapshot()`` with no cutoff uses the real wall clock,
    # which is not what an injected test clock is asserting about.
    before = "2026-05-01T12:00:00Z"
    clock["now"] = datetime(2026, 5, 2, tzinfo=timezone.utc)
    _publication(ledger, pmid="40000009")
    graph.materialize(ledger, limit=50, log=lambda _m: None)
    diff = graph.changes_between(earlier=before)
    assert diff["counts"]["added"] > 0
    assert "does not mean the underlying event happened" in diff["note"]
    ledger.close()
    graph.store.close()


def test_node_detail_carries_a_citable_source_url(tmp_path: Path):
    ledger = _ledger(tmp_path)
    outcome = _fda(ledger)
    graph = _graph(tmp_path)
    graph.materialize(ledger, limit=50, log=lambda _m: None)
    detail = graph.node_detail(node_type=NODE_COMPANY, node_id=company_node_id("philips"))
    assert detail["node"] is not None
    urls = [edge["source_url"] for edge in detail["incoming"] + detail["outgoing"]]
    assert any(url and "accessdata.fda.gov" in url for url in urls)
    assert detail["earliest_evidence"] is not None
    ledger.close()
    graph.store.close()


def test_an_empty_graph_reports_empty_rather_than_inventing_branches(tmp_path: Path):
    graph = _graph(tmp_path)
    payload = graph.technology_map()
    assert payload["topics"] == []
    summary = graph.summary()
    assert summary["nodes"] == 0 and summary["edges"] == 0
    graph.store.close()
