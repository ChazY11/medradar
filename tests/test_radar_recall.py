"""The monitoring-recall channel: screening, row/event identity and the adapter contract.

V1-001 adds the FDA recall read path that the radar lane never implemented. These tests hold the
three promises that make the channel trustworthy:

* the screen has four explicit tiers and does not let a firm name or a keyword decide on its own;
* one recall EVENT is one identity, however many product rows it has;
* the adapter records what the source said, with the publication date and the action date kept
  apart, and it never re-requests its whole inventory when nothing changed.

The network is never touched: a fake fetcher serves recorded openFDA payload shapes.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from medradar.radar.adapter import CollectContext, run_source, usable_incremental_watermark
from medradar.radar.adapters.openfda_recall import (
    BACKFILL_START,
    OpenFDARecallAdapter,
    _window_start,
)
from medradar.radar.intelligence import event_identity
from medradar.radar.ledger import ObservationLedger
from medradar.radar.recall import (
    BASIS_DEVICE_TEXT,
    BASIS_OUT_OF_SCOPE,
    BASIS_PRODUCT_CODE,
    BASIS_UNCONFIRMED,
    RECALL_EVENT_IDENTIFIER,
    event_groups,
    monitoring_codes,
    screen_recall,
)
from medradar.radar.taxonomy import load_taxonomy

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "radar"


def _row(**overrides):
    base = {
        "cfres_id": "1",
        "product_res_number": "Z-0001-2026",
        "res_event_number": "90001",
        "recalling_firm": "Example Medical",
        "product_code": "MHX",
        "product_description": "Example Patient Monitor, model X",
        "reason_for_recall": "The device may fail to alarm on a low oxygen saturation",
        "root_cause_description": "Software design",
        "action": "Customer letter",
        "recall_status": "Open, Classified",
        "event_date_initiated": "2026-06-01",
        "event_date_posted": "2026-06-02",
        "event_date_terminated": None,
        "k_numbers": ["K123456"],
        "distribution_pattern": "Nationwide",
        "code_info": "serial 1",
        "product_quantity": "10",
        "city": "Springfield",
        "state": "IL",
        "openfda": {"device_name": "Monitor, Physiological, Patient(With Arrhythmia Detection Or Alarms)",
                    "device_class": "2", "medical_specialty_description": "Cardiovascular",
                    "regulation_number": "870.1025"},
    }
    base.update(overrides)
    return base


# ------------------------------------------------------------------ screening tiers
def test_a_monitored_product_code_confirms_a_monitoring_device():
    taxonomy = load_taxonomy(str(CONFIG_DIR))
    verdict = screen_recall(_row(product_code="MHX"), taxonomy=taxonomy)
    assert verdict["basis"] == BASIS_PRODUCT_CODE
    assert verdict["in_scope"] is True
    assert verdict["needs_review"] is False
    assert verdict["code_topics"], "the taxonomy topics for the code must be reported"


def test_an_unlisted_code_with_a_monitoring_device_name_goes_to_review():
    taxonomy = load_taxonomy(str(CONFIG_DIR))
    verdict = screen_recall(
        _row(product_code="ZZZ", product_description="ACME Patient Monitor, model 9",
             reason_for_recall="Display freezes"),
        taxonomy=taxonomy,
    )
    assert verdict["basis"] == BASIS_DEVICE_TEXT
    assert verdict["in_scope"] is True
    assert verdict["needs_review"] is True, "our own text classification must never be auto-confirmed"


def test_a_vendor_name_alone_never_confirms_a_monitoring_device():
    taxonomy = load_taxonomy(str(CONFIG_DIR))
    verdict = screen_recall(
        _row(product_code="ZZZ", recalling_firm="Philips",
             product_description="Surgical navigation system", reason_for_recall="monitor issue"),
        taxonomy=taxonomy,
    )
    assert verdict["basis"] == BASIS_UNCONFIRMED
    assert verdict["needs_review"] is True
    assert verdict["in_scope"] is True, "an uncertain row is kept for review, never deleted"


def test_an_unrelated_device_is_out_of_scope_with_a_reason():
    taxonomy = load_taxonomy(str(CONFIG_DIR))
    verdict = screen_recall(
        _row(product_code="FRC", product_description="VERIFY Biological Challenge Pack",
             reason_for_recall="Reagent contamination"),
        taxonomy=taxonomy,
    )
    assert verdict["basis"] == BASIS_OUT_OF_SCOPE
    assert verdict["in_scope"] is False
    assert "reagent" in verdict["reason"] or "not a monitoring device" in verdict["reason"]


def test_the_screen_never_invents_a_classification_without_a_registry():
    verdict = screen_recall(_row(product_code="MHX"), codes={})
    assert verdict["basis"] in (BASIS_DEVICE_TEXT, BASIS_OUT_OF_SCOPE)


# ------------------------------------------------------------------ identity
def test_two_product_rows_of_one_recall_event_share_one_event_identity():
    first = _row(product_res_number="Z-0001-2026", res_event_number="90001")
    second = _row(product_res_number="Z-0002-2026", res_event_number="90001")
    assert event_identity({"payload": first}) == event_identity({"payload": second})
    assert event_identity({"payload": first}) == "FDA_RECALL_EVENT:90001"


def test_two_different_events_do_not_collapse():
    first = _row(res_event_number="90001")
    second = _row(res_event_number="90002")
    assert event_identity({"payload": first}) != event_identity({"payload": second})


def test_event_groups_reports_one_entry_per_event():
    rows = [{"payload": _row(res_event_number="90001")},
            {"payload": _row(res_event_number="90001", product_res_number="Z-2")},
            {"payload": _row(res_event_number="90002")}]
    groups = event_groups(rows)
    assert len(groups) == 2
    assert [len(group["products"]) for group in groups] == [2, 1]


# ------------------------------------------------------------------ adapter
class FakeFetcher:
    """Serves recorded openFDA payload shapes and counts requests."""

    stats = {"requests": 0, "bytes": 0, "retries": 0, "refusals": 0, "rate_limited": 0,
             "not_found": 0, "failures": 0}

    def __init__(self, rows, *, total=None, version="2026-11-14"):
        self.rows = list(rows)
        self.total = len(self.rows) if total is None else int(total)
        self.version = version
        self.urls: list[str] = []

    @property
    def requests_remaining(self) -> int:
        return 100

    def get_json(self, url, **_kwargs):
        self.urls.append(url)
        self.stats["requests"] += 1
        if "limit=1" in url and "search" not in url:
            return {"meta": {"last_updated": self.version, "results": {"total": 1}}, "results": []}
        start = 0
        for part in url.split("&"):
            if part.startswith("skip="):
                start = int(part.split("=", 1)[1])
        limit = 1000
        for part in url.split("&"):
            if part.startswith("limit="):
                limit = int(part.split("=", 1)[1])
        window = self.rows[start:start + limit]
        return {"meta": {"last_updated": self.version, "results": {"total": self.total}},
                "results": window}



def test_the_adapter_keeps_the_action_date_and_the_publication_date_apart():
    taxonomy = load_taxonomy(str(CONFIG_DIR))
    adapter = OpenFDARecallAdapter(taxonomy, product_codes=("MHX",))
    record = adapter._record(_row())
    assert record.event_at == "2026-06-01" and record.event_at_precision == "date"
    assert record.published_at == "2026-06-02" and record.published_at_precision == "date"
    assert record.record_type == "regulatory_record"
    assert record.source_record_id == "recall:Z-0001-2026"
    kinds = dict(record.extra["identifiers"])
    assert kinds[RECALL_EVENT_IDENTIFIER] == "90001"
    assert record.payload["openfda_device"]["device_class"] == "2"
    assert "registration_number" not in record.payload["openfda_device"]


def test_a_row_without_an_official_number_is_not_recorded():
    taxonomy = load_taxonomy(str(CONFIG_DIR))
    adapter = OpenFDARecallAdapter(taxonomy, product_codes=("MHX",))
    assert adapter._record(_row(product_res_number="", cfres_id="")) is None


def test_the_window_without_a_watermark_depends_on_the_declared_intent():
    today = date.today()
    assert _window_start(None, backfill=True) == BACKFILL_START
    assert _window_start(None, backfill=False) == (today - timedelta(days=90)).isoformat()
    assert _window_start("2026-06-10", backfill=False) == "2026-05-11"


def test_a_coarse_watermark_is_widened_before_the_adapter_uses_it():
    value, adjustment = usable_incremental_watermark("2027-02")
    assert value != "2027-02"
    assert adjustment is not None
    assert _window_start(value, backfill=False) < date.today().isoformat()


def test_a_first_run_collects_the_inventory_and_the_window(tmp_path: Path):
    taxonomy = load_taxonomy(str(CONFIG_DIR))
    adapter = OpenFDARecallAdapter(taxonomy, product_codes=("MHX",))
    ledger = ObservationLedger(tmp_path / "radar.db")
    try:
        fetcher = FakeFetcher([_row(event_date_posted="2026-10-01")])
        ctx = CollectContext(fetcher=fetcher, ledger=ledger,
                            adapter_version=adapter.adapter_version, log=lambda _m: None,
                            origin="BACKFILLED",
                            backfill_reason="test import of the recall inventory")
        result = run_source(adapter, ctx)
        assert result["status"] == "OK"
        assert result["counters"]["records_new"] == 1
        assert ledger.counts().observations == 1
        state = ledger.get_source_state("openfda_recall")
        assert state["watermark"] == "2026-10-01"
        assert state["enabled"] == 1
    finally:
        ledger.close()


def test_a_second_run_does_not_repeat_the_inventory(tmp_path: Path):
    taxonomy = load_taxonomy(str(CONFIG_DIR))
    adapter = OpenFDARecallAdapter(taxonomy, product_codes=("MHX", "DQA"))
    ledger = ObservationLedger(tmp_path / "radar.db")
    try:
        rows = [_row(product_code="MHX", product_res_number="Z-1", res_event_number="1",
                     event_date_posted="2026-10-01")]
        first = FakeFetcher(rows)
        run_source(adapter, CollectContext(fetcher=first, ledger=ledger,
                                          adapter_version=adapter.adapter_version,
                                          log=lambda _m: None))
        inventory_requests = sum(1 for url in first.urls if 'product_code' in url)
        assert inventory_requests >= 1
        second = FakeFetcher(rows)
        result = run_source(adapter, CollectContext(fetcher=second, ledger=ledger,
                                                    adapter_version=adapter.adapter_version,
                                                    log=lambda _m: None))
        assert result["counters"]["records_new"] == 0
        assert sum(1 for url in second.urls if "product_code" in url) == 0, (
            "a completed inventory must not be repeated until the official version changes"
        )
    finally:
        ledger.close()


def test_the_same_row_recorded_twice_is_one_observation(tmp_path: Path):
    taxonomy = load_taxonomy(str(CONFIG_DIR))
    adapter = OpenFDARecallAdapter(taxonomy, product_codes=("MHX",))
    ledger = ObservationLedger(tmp_path / "radar.db")
    try:
        rows = [_row()]
        for _ in range(2):
            run_source(adapter, CollectContext(fetcher=FakeFetcher(rows), ledger=ledger,
                                               adapter_version=adapter.adapter_version,
                                               log=lambda _m: None))
        assert ledger.counts().observations == 1
        assert ledger.counts().versions == 1
    finally:
        ledger.close()


def test_the_ledger_stores_the_event_identifier_for_an_event_level_count(tmp_path: Path):
    taxonomy = load_taxonomy(str(CONFIG_DIR))
    adapter = OpenFDARecallAdapter(taxonomy, product_codes=("MHX",))
    ledger = ObservationLedger(tmp_path / "radar.db")
    try:
        rows = [_row(product_res_number="Z-1", res_event_number="90001"),
                _row(product_res_number="Z-2", res_event_number="90001")]
        run_source(adapter, CollectContext(fetcher=FakeFetcher(rows), ledger=ledger,
                                           adapter_version=adapter.adapter_version,
                                           log=lambda _m: None))
        assert ledger.counts().observations == 2, "two product records are two observations"
        events = ledger.raw(
            "SELECT value, COUNT(*) AS n FROM observation_identifier"
            " WHERE kind = ? GROUP BY value", (RECALL_EVENT_IDENTIFIER,))
        assert len(events) == 1 and int(events[0]["n"]) == 2, (
            "an event-level count must collapse the rows of one recall event"
        )
    finally:
        ledger.close()
