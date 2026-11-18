"""A watermark in the future must not stop discovery silently.

Each case below is a measured defect, not a hypothesis:

* The production-shaped ledger copied on 2026-11-18 carried a Crossref watermark of 2027-02.
  Crossref is queried with filter=from-created-date:<watermark - 2d>, so every Crossref scope
  asked for deposits created after 2027-01 and the source could not discover another record
  until that month arrived. The run still reported OK.
* Nothing in the health report noticed, because the only watermark check asked whether a
  successful run existed, not whether the watermark was possible.

The rule these tests protect: the stored state is never rewritten (it is evidence), but the
value handed to an adapter is clamped to today, and the disagreement is reported.
"""

from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

try:  # the repository selftest runs under unittest without pytest installed
    import pytest
except ModuleNotFoundError:  # pragma: no cover
    raise unittest.SkipTest("pytest is not installed; run these tests with pytest")

from medradar.radar.adapter import CollectContext, run_source, usable_incremental_watermark
from medradar.radar.ledger import ObservationLedger
from medradar.radar.records import MappingResult, Page, RawRecord, Scope


class _NoopFetcher:
    stats = {"requests": 0, "bytes": 0, "retries": 0, "refusals": 0,
             "rate_limited": 0, "not_found": 0, "failures": 0}

    @property
    def requests_remaining(self) -> int:
        return 100


class _RecordingAdapter:
    """An adapter that records the watermark the engine handed it."""

    source_id = "recording"
    label = "Recording source"
    adapter_version = "recording-1"
    declared_cadence_hours = 1.0
    record_types = ("publication",)
    enabled = True
    access_state = "ENABLED"
    access_reason = None

    def __init__(self) -> None:
        self.seen_watermarks: list[str | None] = []

    def plan(self, ctx: CollectContext) -> list[Scope]:
        self.seen_watermarks.append(ctx.watermark)
        return [Scope("q1")]

    def fetch_page(self, ctx: CollectContext, scope: Scope, cursor: str | None) -> Page:
        self.seen_watermarks.append(ctx.watermark)
        return Page(records=[], next_cursor=None, watermark=ctx.watermark)

    def map_record(self, record: RawRecord, ctx: CollectContext) -> MappingResult:
        return MappingResult()


@pytest.fixture()
def ledger(tmp_path: Path):
    handle = ObservationLedger(tmp_path / "radar.db")
    yield handle
    handle.close()


def _run(adapter, ledger: ObservationLedger) -> dict:
    ctx = CollectContext(fetcher=_NoopFetcher(), ledger=ledger,
                         adapter_version=adapter.adapter_version, log=lambda _m: None)
    return run_source(adapter, ctx)


def test_an_impossible_watermark_is_repaired_for_the_query_only():
    today = date(2026, 11, 18).isoformat()
    # future + coarse: widened to the start of its period, then clamped to today
    usable, adjustment = usable_incremental_watermark("2027-02", today=today)
    assert usable == today
    assert adjustment["clamped_from_future"] is True
    assert adjustment["coarsened_to_period_start"] is True
    # past + coarse: widened, never clamped. Before the fix this fell back to 2018-01-01.
    assert usable_incremental_watermark("2026-03", today=today) == (
        "2026-03-01", {"from": "2026-03", "to": "2026-03-01",
                       "coarsened_to_period_start": True, "clamped_from_future": False})
    # already a usable date: untouched
    assert usable_incremental_watermark("2026-11-17", today=today) == ("2026-11-17", None)
    assert usable_incremental_watermark("2026-11-18", today=today) == ("2026-11-18", None)
    assert usable_incremental_watermark(None, today=today) == (None, None)
    assert usable_incremental_watermark("not-a-date", today=today) == ("not-a-date", None)


def _seed_watermark(ledger: ObservationLedger, value: str) -> None:
    # set_watermark only updates an existing source row; a source appears on first run.
    ledger.ensure_source("recording", label="Recording source", adapter_version="recording-1",
                         cadence_hours=1.0)
    ledger.set_watermark("recording", value)


def test_a_future_watermark_does_not_stop_discovery(ledger):
    _seed_watermark(ledger, "2027-02")
    adapter = _RecordingAdapter()
    result = _run(adapter, ledger)
    today = date.today().isoformat()
    assert adapter.seen_watermarks
    assert all(value == today for value in adapter.seen_watermarks), adapter.seen_watermarks
    assert result["watermark_adjustment"]["clamped_from_future"] is True
    assert result["watermark_adjustment"]["from"] == "2027-02"
    stored = ledger.ensure_source("recording", label="Recording source",
                                  adapter_version="recording-1", cadence_hours=1.0)
    assert stored["watermark"] == "2027-02"


def test_a_past_watermark_is_used_as_stored(ledger):
    _seed_watermark(ledger, "2026-01-05")
    adapter = _RecordingAdapter()
    result = _run(adapter, ledger)
    assert adapter.seen_watermarks[0] == "2026-01-05"
    assert result["watermark_adjustment"] is None


def test_health_reports_a_watermark_in_the_future(ledger):
    _seed_watermark(ledger, "2027-02")
    report = ledger.consistency_check()
    assert report["ok"] is False
    kinds = {problem["kind"] for problem in report["problems"]}
    assert "watermark_in_future" in kinds
    entry = [p for p in report["problems"] if p["kind"] == "watermark_in_future"][0]
    assert entry["count"] == 1 and entry["sources"] == ["recording"]