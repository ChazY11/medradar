"""The scheduler: cadence, the single-writer lease and safe AI deferral.

The acceptance property is "discovery never waits for AI and never claims a quiet period it did
not observe". These tests drive one cycle with a fixture adapter and a stubbed AI stage.
"""

from __future__ import annotations

import json
from pathlib import Path

import unittest

try:  # the repository's `medradar selftest` runs under unittest without pytest installed
    import pytest
except ModuleNotFoundError:  # pragma: no cover
    raise unittest.SkipTest("pytest is not installed; run these tests with pytest")

from medradar.radar import adapters as adapters_module
from medradar.radar.adapters.fixture import FixtureAdapter, write_pages
from medradar.radar.graph import open_graph
from medradar.radar.ledger import ObservationLedger
from medradar.radar.paths import radar_paths
from medradar.radar.scheduler import RadarScheduler
from medradar.radar.taxonomy import load_taxonomy

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "radar"

PAGE = {
    "watermark": "2026-05-01",
    "records": [
        {
            "id": "fixture-1",
            "title": "A modular patient monitor reduced alarm fatigue in intensive care",
            "published_at": "2026-05-01",
            "url": "https://fixture.test/1",
            "payload": {"title": "A modular patient monitor reduced alarm fatigue"},
            "extra": {"organization_hint": "Philips Medical Systems",
                      "organization_role": "publication_affiliation"},
        }
    ],
}


@pytest.fixture()
def scheduler(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    taxonomy = load_taxonomy(str(CONFIG_DIR))
    paths = radar_paths(tmp_path / "radar").ensure()
    write_pages(tmp_path / "fixture", [PAGE])
    ledger = ObservationLedger(paths.ledger)
    graph = open_graph(paths.graph, taxonomy)

    def build(taxonomy_arg, source_ids=None):
        return [FixtureAdapter(taxonomy_arg, tmp_path / "fixture")]

    monkeypatch.setattr(adapters_module, "build_adapters", build)
    instance = RadarScheduler(paths, ledger, graph, taxonomy, ai_enabled=True,
                             log=lambda _m: None)
    yield instance
    graph.store.close()
    ledger.close()


def test_a_cycle_ingests_advances_and_reports_new_records(scheduler):
    result = scheduler.cycle()
    assert result.status == "OK"
    assert result.ingested["new_records"] == 1
    assert result.advanced["graph"]["materialized"] >= 1
    state = scheduler.ledger.get_source_state("fixture_isolated")
    assert state["watermark"] == "2026-05-01"
    assert state["last_success_check_at"]


def test_a_second_cycle_reports_no_change_rather_than_inventing_events(scheduler):
    scheduler.cycle()
    again = scheduler.cycle(force=False)
    # The cadence says the source is not due yet, so nothing is claimed.
    assert again.status == "IDLE"
    assert "Nothing was due" in again.note
    forced = scheduler.cycle(force=True)
    assert forced.ingested["new_records"] == 0
    assert forced.ingested["no_change"] is True
    assert "no change" in forced.ingested["statement"]


def test_a_failed_source_cycle_does_not_report_a_quiet_period(scheduler, monkeypatch):
    def build(taxonomy_arg, source_ids=None):
        return [FixtureAdapter(taxonomy_arg, scheduler.paths.root.parent / "missing")]

    monkeypatch.setattr(adapters_module, "build_adapters", build)
    result = scheduler.cycle(force=True)
    assert result.status == "FAILED"
    assert result.ingested["no_change"] is False
    assert "did not observe a quiet period" in result.ingested["statement"]


def test_ai_is_deferred_under_pressure_while_discovery_still_runs(scheduler):
    class Deny:
        def evaluate(self, *_args, **_kwargs):
            from medradar.radar.resources import GuardDecision

            return GuardDecision(False, "available memory 100 MB is below the 900 MB floor",
                                 {"available_mb": 100})

    scheduler.guard = Deny()
    result = scheduler.cycle(force=True)
    assert result.status in ("OK", "PARTIAL")
    assert result.ingested["new_records"] == 1, "discovery must not wait for AI"
    assert result.ai["state"] == "deferred"
    assert "Discovery is unaffected" in result.ai["statement"]
    assert scheduler.ledger.queue_summary()["backlog"] >= 1


def test_the_cycle_is_recorded_for_the_status_endpoint(scheduler):
    scheduler.cycle(force=True)
    recorded = scheduler.ledger.get_runtime("last_cycle")
    assert recorded and recorded["status"] in ("OK", "PARTIAL")
    assert scheduler.ledger.get_runtime("cycle_counter") == 1


def test_a_disabled_source_is_never_due(scheduler):
    scheduler.ledger.ensure_source("gehealthcare_official", label="GE", adapter_version="a1",
                                   cadence_hours=24, access_state="BLOCKED",
                                   access_reason="403", enabled=False)
    assert scheduler._is_due("gehealthcare_official") is False
    assert scheduler._is_due("never_seen_source") is True


def test_an_idle_cycle_still_drains_pending_pipeline_work(scheduler):
    """Regression for the production restart that interrupted graph materialisation.

    A kill during ``advance`` leaves observations pending. The next scheduler cycle finds no
    source due and used to return before touching the pipeline, so the graph stayed partial for
    hours. An idle cycle must still drain whatever is pending, without claiming a source check.
    """
    scheduler.cycle(force=True)          # ingest + advance
    pending_before = scheduler.ledger.raw(
        "SELECT observation_id FROM observation WHERE processing_state IN ('RAW','CLASSIFIED','LINKED')"
    )
    assert pending_before == []
    # Simulate an interrupted materialisation: the observation exists, but the graph does not
    # know it was materialised (exactly the state a SIGKILL between write and commit leaves).
    scheduler.ledger.con.execute("DELETE FROM graph_materialization")
    idle = scheduler.cycle(force=False)
    assert idle.status == "IDLE"
    assert idle.ingested["sources"] == [], "an idle cycle sends no request"
    assert idle.advanced["graph"]["materialized"] >= 1
    assert "did not observe" not in idle.note


def test_the_watch_loop_runs_a_bounded_number_of_cycles(scheduler):
    result = scheduler.watch(interval_seconds=0.01, max_cycles=2)
    assert result["cycles"] == 2
    assert len(result["results"]) == 2
    assert scheduler.ledger.get_runtime("cycle_counter") == 2


def test_the_cycle_degrades_gracefully_when_the_ai_worker_cannot_start(scheduler, monkeypatch):
    class Allow:
        def evaluate(self, *_args, **_kwargs):
            from medradar.radar.resources import GuardDecision

            return GuardDecision(True, "ok", {})

    scheduler.guard = Allow()
    scheduler.cycle(force=True)  # queue a task
    monkeypatch.setattr(scheduler, "_spawn_worker",
                        lambda *, limit: (_ for _ in ()).throw(RuntimeError("no python")))
    result = scheduler.cycle(force=True)
    assert result.ai["state"] == "failed"
    assert result.ingested["new_records"] >= 0
