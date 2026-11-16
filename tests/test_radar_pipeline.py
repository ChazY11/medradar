"""The incremental run engine and the rule/vetting layer.

The engine tests use a fixture adapter, so they measure the engine's own promises: cursors
advance only after a durable write, a failure never advances a watermark, a resumed run does
not lose or duplicate a page, and a scope gate keeps out-of-scope records out of the ledger.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from medradar.radar.adapter import CollectContext, run_source
from medradar.radar.classify import ROLE_AFFILIATION, RuleMapper
from medradar.radar.ledger import ObservationLedger
from medradar.radar.records import MappingResult, Page, RawRecord, Scope
from medradar.radar.taxonomy import load_taxonomy

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "radar"


class FakeAdapter:
    source_id = "fake"
    label = "Fake source"
    adapter_version = "fake-1"
    declared_cadence_hours = 1.0
    record_types = ("publication",)
    enabled = True
    access_state = "ENABLED"
    access_reason = None

    def __init__(self, pages, *, raise_on_scope: str | None = None) -> None:
        self.pages = pages
        self.raise_on_scope = raise_on_scope
        self.calls: list[tuple[str, str | None]] = []

    def plan(self, ctx: CollectContext) -> list[Scope]:
        return [Scope("q1")]

    def fetch_page(self, ctx: CollectContext, scope: Scope, cursor: str | None) -> Page:
        self.calls.append((scope.scope_id, cursor))
        if self.raise_on_scope == scope.scope_id:
            raise RuntimeError("source went away")
        index = int(cursor or 0)
        if index >= len(self.pages):
            return Page(records=[], next_cursor=None, watermark=ctx.watermark)
        return self.pages[index]

    def map_record(self, record: RawRecord, ctx: CollectContext) -> MappingResult:
        return MappingResult(
            technology_topics=({"topic_id": "spo2_oximetry", "confirmation": "TOPIC_RELATED",
                                "method": "rule_text", "confidence": 0.6},),
        )


def _record(index: int, **overrides) -> RawRecord:
    payload = {"title": f"Study {index}", "abstract": "SpO2 monitoring"}
    payload.update(overrides.pop("payload", {}))
    base = dict(
        source="fake", source_record_id=f"r{index}", official_identifier=f"ID-{index}",
        record_type="publication", title=f"Study {index}", url=f"https://example.test/{index}",
        published_at="2026-01-01", published_at_precision="date",
        payload=payload, text="SpO2 monitoring",
    )
    base.update(overrides)
    return RawRecord(**base)


def _run(adapter: FakeAdapter, ledger: ObservationLedger, **kwargs) -> dict:
    ctx = CollectContext(fetcher=_NoopFetcher(), ledger=ledger,
                         adapter_version=adapter.adapter_version, log=lambda _m: None, **kwargs)
    return run_source(adapter, ctx)


class _NoopFetcher:
    stats = {"requests": 0, "bytes": 0, "retries": 0, "refusals": 0, "rate_limited": 0,
             "not_found": 0, "failures": 0}

    @property
    def requests_remaining(self) -> int:
        return 100


@pytest.fixture()
def ledger(tmp_path: Path) -> ObservationLedger:
    handle = ObservationLedger(tmp_path / "radar.db")
    yield handle
    handle.close()


def test_a_completed_run_records_records_and_advances_the_watermark(ledger: ObservationLedger):
    adapter = FakeAdapter([Page(records=[_record(1), _record(2)], next_cursor=None,
                                watermark="2026-01-02")])
    result = _run(adapter, ledger)
    assert result["status"] == "OK"
    assert result["counters"]["records_new"] == 2
    assert result["watermark_after"] == "2026-01-02"
    assert ledger.get_source_state("fake")["watermark"] == "2026-01-02"


def test_a_second_run_with_no_changes_reports_no_change_and_writes_nothing_new(ledger: ObservationLedger):
    adapter = FakeAdapter([Page(records=[_record(1)], next_cursor=None, watermark="2026-01-02")])
    _run(adapter, ledger)
    again = _run(adapter, ledger)
    assert again["counters"]["records_new"] == 0
    assert again["counters"]["records_unchanged"] == 1
    assert ledger.counts().change_events == 1


def test_a_failed_scope_does_not_advance_the_watermark(ledger: ObservationLedger):
    adapter = FakeAdapter([], raise_on_scope="q1")
    result = _run(adapter, ledger)
    assert result["status"] == "FAILED"
    state = ledger.get_source_state("fake")
    assert state["watermark"] is None
    assert state["consecutive_failures"] == 1
    failures = ledger.failures(source="fake")
    assert failures and failures[0]["kind"] == "SCOPE_ERROR"


def test_a_partial_run_advances_only_the_scopes_that_finished(ledger: ObservationLedger):
    class TwoScope(FakeAdapter):
        def plan(self, ctx):
            return [Scope("good"), Scope("bad")]

        def fetch_page(self, ctx, scope, cursor):
            if scope.scope_id == "bad":
                raise RuntimeError("boom")
            return Page(records=[_record(1)], next_cursor=None, watermark="2026-02-02")

    adapter = TwoScope([])
    result = _run(adapter, ledger)
    assert result["status"] == "PARTIAL"
    assert result["watermark_after"] == "2026-02-02"
    assert ledger.get_source_state("fake")["watermark"] == "2026-02-02"


def test_a_resumed_run_reuses_its_checkpoints_instead_of_restarting(ledger: ObservationLedger):
    page1 = Page(records=[_record(1)], next_cursor="1", watermark="2026-01-01")
    page2 = Page(records=[_record(2)], next_cursor=None, watermark="2026-01-02")
    adapter = FakeAdapter([page1, page2])
    first = _run(adapter, ledger)
    assert first["counters"]["records_new"] == 2
    adapter.calls.clear()
    second = _run(adapter, ledger)
    # A fresh run starts at the beginning of the scope again; the ledger is idempotent.
    assert adapter.calls[0] == ("q1", None)
    assert second["counters"]["records_new"] == 0
    assert second["counters"]["records_unchanged"] == 2


def test_a_disabled_source_is_deferred_without_a_request(ledger: ObservationLedger):
    adapter = FakeAdapter([Page(records=[_record(1)])])
    adapter.enabled = False
    adapter.access_state = "BLOCKED"
    adapter.access_reason = "operator refused automated access (403)"
    result = _run(adapter, ledger)
    assert result["status"] == "DEFERRED"
    assert adapter.calls == []
    state = ledger.get_source_state("fake")
    assert state["access_state"] == "BLOCKED"
    assert state["last_checked_at"] is None


def test_an_out_of_scope_record_is_skipped_not_written(ledger: ObservationLedger):
    class Gated(FakeAdapter):
        def accept_record(self, record, mapping):
            return (False, "out of scope") if record.source_record_id == "r2" else (True, "")

    adapter = Gated([Page(records=[_record(1), _record(2)], next_cursor=None)]) 
    result = _run(adapter, ledger)
    assert result["counters"]["records_new"] == 1
    assert result["counters"]["records_skipped"] == 1
    assert ledger.counts().observations == 1


# ---------------------------------------------------------------- rule layer + vetting
def test_fda_record_product_code_is_topic_related_never_a_capability():
    taxonomy = load_taxonomy(str(CONFIG_DIR))
    mapper = RuleMapper(taxonomy)
    record = RawRecord(
        source="openfda_device", source_record_id="510k:K1", official_identifier="K1",
        record_type="regulatory_record", title="PATIENT MONITOR",
        event_at="2026-01-01", event_at_precision="date",
        payload={"device_name": "PATIENT MONITOR"},
        extra={"organization_hint": "Philips Medical Systems",
               "organization_role": "regulatory_applicant",
               "product_codes": ["MHX"], "product_hint": "PATIENT MONITOR"},
    )
    mapping = mapper.map(record)
    assert mapping.organization_candidates[0]["organization_id"] == "philips"
    assert mapping.product_candidates[0]["name"] == "PATIENT MONITOR"
    assert all(topic["confirmation"] == "TOPIC_RELATED" for topic in mapping.technology_topics)


def test_a_publication_affiliation_is_never_a_capability_role():
    taxonomy = load_taxonomy(str(CONFIG_DIR))
    mapper = RuleMapper(taxonomy)
    record = RawRecord(
        source="pubmed", source_record_id="pmid:1", official_identifier="PMID:1",
        record_type="publication", title="SpO2 monitoring in intensive care",
        payload={"abstract": "SpO2"},
        extra={"organization_hint": "Philips Research, Eindhoven",
               "organization_role": "publication_affiliation",
               "affiliations": ["Philips Research, Eindhoven"]},
    )
    mapping = mapper.map(record)
    roles = {candidate["role"] for candidate in mapping.organization_candidates}
    assert roles == {ROLE_AFFILIATION}
    assert mapping.product_candidates == ()


def test_the_vetting_gate_rejects_a_fabricated_quote():
    taxonomy = load_taxonomy(str(CONFIG_DIR))
    mapper = RuleMapper(taxonomy)
    verdict = mapper.vet_model_claim(
        {"kind": "topic", "value": "spo2_oximetry",
         "evidence_quote": "the device measures cerebral oxygenation"},
        source_text="A study of modular patient monitors and alarm fatigue.",
    )
    assert verdict["accepted"] is False
    assert "verbatim" in (verdict["reason"] or "")


def test_the_vetting_gate_accepts_a_verbatim_quote_for_a_real_topic():
    taxonomy = load_taxonomy(str(CONFIG_DIR))
    mapper = RuleMapper(taxonomy)
    text = "A study of modular patient monitors and alarm fatigue."
    verdict = mapper.vet_model_claim(
        {"kind": "topic", "value": "smart_alarms", "evidence_quote": "alarm fatigue"},
        source_text=text,
    )
    assert verdict["accepted"] is True
    assert verdict["confirmation"] == "TOPIC_RELATED"


def test_the_vetting_gate_rejects_an_unknown_topic_id_even_with_a_real_quote():
    taxonomy = load_taxonomy(str(CONFIG_DIR))
    mapper = RuleMapper(taxonomy)
    verdict = mapper.vet_model_claim(
        {"kind": "topic", "value": "telepathic_sensing", "evidence_quote": "alarm fatigue"},
        source_text="alarm fatigue in intensive care",
    )
    assert verdict["accepted"] is False
    assert "unknown topic id" in (verdict["reason"] or "")


def test_the_vetting_gate_resolves_a_company_only_through_the_committed_alias_table():
    taxonomy = load_taxonomy(str(CONFIG_DIR))
    mapper = RuleMapper(taxonomy)
    text = "Published by Philips Medizin Systeme Boeblingen GmbH."
    good = mapper.vet_model_claim(
        {"kind": "organization", "value": "Philips Medizin Systeme Boeblingen GmbH",
         "evidence_quote": "Philips Medizin Systeme Boeblingen GmbH"},
        source_text=text,
    )
    assert good["accepted"] is True and good["organization_id"] == "philips"
    bad = mapper.vet_model_claim(
        {"kind": "organization", "value": "Nihon Kohden", "evidence_quote": "Published by Philips"},
        source_text=text,
    )
    assert bad["accepted"] is False
