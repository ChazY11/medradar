"""PILOT-READY-001 P0-02: the top-level verdict must follow the evidence.

The defect this pins down: consistency_check already reported a future watermark (the measured
Crossref 2027-02 case) and the per-source rows already carried failures, but system_status
returned a hard-coded "ok" whenever no source row happened to be DEGRADED. An operator reading the
top line was told the system was fine while a core discovery channel could not advance.

What is asserted here is the contract, not the implementation:

* a failing core source never leaves the verdict healthy;
* an illegal watermark on a core source never leaves it healthy;
* a ledger that cannot be written, or a scheduler that stopped, is UNHEALTHY;
* a source that is merely quiet is NOT a fault - telling them apart is the whole point;
* a lens with no evidence says UNKNOWN rather than inventing a green light.
"""

from __future__ import annotations

from pathlib import Path

try:
    import pytest  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - the offline CI suite has no pytest
    raise unittest.SkipTest("pytest is not installed; run these tests with pytest")

from medradar.radar.classify import RuleMapper
from medradar.radar.health import (
    DEGRADED,
    HEALTHY,
    UNHEALTHY,
    UNKNOWN,
    V1_CRITICAL_SOURCES,
    system_status,
)
from medradar.radar.ledger import ObservationLedger, utc_now_iso
from medradar.radar.records import MAPPING_VERSION, RawRecord
from medradar.radar.taxonomy import load_taxonomy

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "radar"


def _taxonomy():
    return load_taxonomy(str(CONFIG_DIR))


def _add(ledger: ObservationLedger, index: int = 0) -> str:
    record = RawRecord(
        source="pubmed", source_record_id=f"rec-{index}", official_identifier=f"rec-{index}",
        record_type="publication", title="Accuracy of a bedside patient monitor",
        url=f"https://example.test/rec-{index}", published_at="2026-11-10",
        published_at_precision="date",
        payload={"title": "Accuracy of a bedside patient monitor",
                 "abstract": "We evaluated monitor accuracy against reference oximetry."},
        text="accuracy monitor oximetry", extra={"official_identifier": f"rec-{index}"},
    )
    return ledger.record_observation(
        record, RuleMapper(_taxonomy()).map(record), run_id="r1", adapter_version="a1",
        mapping_version=MAPPING_VERSION,
    ).observation_id


def _healthy_ledger(tmp_path: Path) -> ObservationLedger:
    ledger = ObservationLedger(tmp_path / "radar.db")
    ledger.ensure_source("openfda_device", label="FDA", adapter_version="a1", cadence_hours=24)
    ledger.ensure_source("pubmed", label="PubMed", adapter_version="a1", cadence_hours=6)
    ledger.ensure_source("philips_official", label="Philips", adapter_version="a1", cadence_hours=12)
    _add(ledger)
    for source in ("openfda_device", "pubmed", "philips_official"):
        ledger.note_source_success(source, run_id=f"{source}:run", observed_update=True)
    ledger.set_runtime("last_cycle", {"finished_at": utc_now_iso(), "status": "OK"})
    return ledger


def _status(ledger: ObservationLedger) -> dict:
    return system_status(ledger, None, _taxonomy())


def _check(payload: dict, check_id: str) -> dict:
    for item in payload["verdict"]["checks"]:
        if item["id"] == check_id:
            return item
    raise AssertionError(f"no check named {check_id}")


def test_a_quiet_but_working_system_is_healthy(tmp_path: Path):
    ledger = _healthy_ledger(tmp_path)
    payload = _status(ledger)
    assert payload["state"] == HEALTHY, payload["verdict"]["reasons"]
    assert payload["legacy_state"] == "ok"
    ledger.close()


def test_no_new_records_is_not_a_fault(tmp_path: Path):
    ledger = _healthy_ledger(tmp_path)
    # Every source keeps succeeding but has produced nothing for weeks. A quiet source is not a
    # broken one: the check is reported, and it must not change the verdict.
    ledger.con.execute(
        "UPDATE source_state SET last_observed_update_at='2026-10-01T00:00:00+00:00'")
    ledger.con.commit()
    payload = _status(ledger)
    assert payload["state"] == HEALTHY, payload["verdict"]["reasons"]
    progress = _check(payload, "acquisition_progress")
    assert progress["status"] == "WARN"
    assert progress["severity"] == "MINOR"
    assert progress["observed"]["quiet_sources"], "the quiet source is named"
    ledger.close()


def test_a_core_source_that_keeps_failing_is_never_reported_healthy(tmp_path: Path):
    ledger = _healthy_ledger(tmp_path)
    for attempt in range(3):
        ledger.note_source_failure("pubmed", run_id=f"f{attempt}", message="HTTP 503 from eutils")
    payload = _status(ledger)
    assert payload["state"] == UNHEALTHY, payload["verdict"]["reasons"]
    assert payload["legacy_state"] != "ok"
    check = _check(payload, "critical_sources")
    assert check["status"] == "FAIL"
    assert check["severity"] == "CRITICAL"
    assert any(row["source_id"] == "pubmed" for row in check["observed"]["sources"])
    ledger.close()


def test_one_failed_core_check_degrades_even_before_the_third_failure(tmp_path: Path):
    ledger = _healthy_ledger(tmp_path)
    ledger.note_source_failure("pubmed", run_id="f1", message="timeout")
    payload = _status(ledger)
    assert payload["state"] == DEGRADED, payload["verdict"]["reasons"]
    assert _check(payload, "critical_sources")["status"] == "WARN"
    ledger.close()


def test_a_core_source_that_is_silently_not_checked_is_unhealthy(tmp_path: Path):
    ledger = _healthy_ledger(tmp_path)
    # The scheduler keeps a fresh heartbeat and the source row still says OK, but the core channel
    # has not been polled for a week. Nothing in the old aggregation looked at this.
    ledger.con.execute(
        "UPDATE source_state SET last_checked_at='2026-11-01T00:00:00+00:00',"
        " last_success_check_at='2026-11-01T00:00:00+00:00' WHERE source_id='pubmed'")
    ledger.con.commit()
    payload = _status(ledger)
    assert payload["state"] == UNHEALTHY, payload["verdict"]["reasons"]
    check = _check(payload, "critical_sources")
    assert any(row["source_id"] == "pubmed" for row in check["observed"]["sources"])
    ledger.close()


def test_a_future_watermark_on_a_core_source_is_not_healthy(tmp_path: Path):
    ledger = _healthy_ledger(tmp_path)
    ledger.ensure_source("crossref", label="Crossref", adapter_version="a1", cadence_hours=12)
    ledger.note_source_success("crossref", run_id="crossref:run", observed_update=True)
    assert _status(ledger)["state"] == HEALTHY
    # The measured 2027-02 case: a month-precision watermark that cannot have been covered, which
    # the adapter cannot use and which therefore stops discovery while every check returns 200.
    ledger.set_watermark("crossref", "2027-02")
    payload = _status(ledger)
    assert payload["state"] != HEALTHY, payload["verdict"]["reasons"]
    assert payload["state"] == UNHEALTHY
    check = _check(payload, "watermark_legal")
    assert check["status"] == "FAIL"
    assert check["severity"] == "CRITICAL"
    assert "crossref" in check["observed"]["sources"]
    assert payload["consistency"]["ok"] is False, "the integrity report agrees with the verdict"
    ledger.close()


def test_a_future_watermark_on_a_peripheral_source_degrades_only(tmp_path: Path):
    ledger = _healthy_ledger(tmp_path)
    ledger.set_watermark("philips_official", "2027-02")
    payload = _status(ledger)
    assert payload["state"] == DEGRADED, payload["verdict"]["reasons"]
    check = _check(payload, "watermark_legal")
    assert check["status"] == "FAIL"
    assert check["severity"] == "MAJOR"
    ledger.close()


def test_a_stalled_scheduler_is_unhealthy(tmp_path: Path):
    ledger = _healthy_ledger(tmp_path)
    ledger.set_runtime("last_cycle", {"finished_at": "2026-11-01T00:00:00+00:00", "status": "OK"})
    payload = _status(ledger)
    assert payload["state"] == UNHEALTHY, payload["verdict"]["reasons"]
    assert _check(payload, "scheduler_heartbeat")["status"] == "FAIL"
    ledger.close()


def test_a_broken_version_chain_is_unhealthy(tmp_path: Path):
    ledger = _healthy_ledger(tmp_path)
    ledger.con.execute("UPDATE observation SET latest_version_id='not-a-real-version'")
    ledger.con.commit()
    payload = _status(ledger)
    assert payload["state"] == UNHEALTHY, payload["verdict"]["reasons"]
    assert _check(payload, "ledger_integrity")["status"] == "FAIL"
    ledger.close()


def test_an_empty_deployment_is_unknown_rather_than_healthy(tmp_path: Path):
    ledger = ObservationLedger(tmp_path / "radar.db")
    ledger.ensure_source("pubmed", label="PubMed", adapter_version="a1", cadence_hours=6)
    payload = _status(ledger)
    assert payload["state"] == UNKNOWN, payload["verdict"]["reasons"]
    assert payload["legacy_state"] == "warming_up"
    ledger.close()


def test_a_read_only_connection_reports_the_probe_as_unknown_not_failed(tmp_path: Path):
    ledger = _healthy_ledger(tmp_path)
    ledger.close()
    read_only = ObservationLedger(tmp_path / "radar.db", create=False, read_only=True)
    try:
        payload = system_status(read_only, None, _taxonomy())
        writable = _check(payload, "ledger_writable")
        assert writable["status"] == "UNKNOWN"
        assert writable["severity"] == "CRITICAL"
        assert "read-only" in writable["detail"]
        assert payload["state"] == HEALTHY, "an unprobed question is not a failure"
    finally:
        read_only.close()


def test_the_critical_source_list_names_the_v1_dependencies():
    assert {"pubmed", "crossref", "openfda_device", "openfda_recall"} <= V1_CRITICAL_SOURCES

def _successful_run(ledger: ObservationLedger, source: str) -> None:
    """A watermark is only credible when a successful run stands behind it."""
    ledger.con.execute(
        "INSERT OR REPLACE INTO sync_run(run_id, source, trigger, adapter_version,"
        " status, started_at, finished_at) VALUES(?,?,?,?,?,'2026-11-18T00:00:00Z',"
        " '2026-11-18T00:00:01Z')",
        (source + ":test", source, "test", "test-adapter", "OK"))
    ledger.con.commit()


def _future_watermark(days_ahead: int) -> str:
    from datetime import timedelta

    from medradar.radar.ledger import utc_now

    return (utc_now().date() + timedelta(days=days_ahead)).isoformat()


def test_a_one_day_lead_is_a_warning_because_the_adapter_clamps_it(tmp_path: Path):
    # Measured on production: PubMed advanced its watermark to 2026-11-19 at 2026-11-18T18:24Z,
    # one day ahead of UTC. The adapter clamps a future watermark to today, so the cost is
    # overlap, not discovery. Reporting that as UNHEALTHY on the day of deployment would train
    # an operator to ignore the light.
    ledger = _healthy_ledger(tmp_path)
    _successful_run(ledger, "pubmed")
    ledger.set_watermark("pubmed", _future_watermark(1))
    payload = _status(ledger)
    check = _check(payload, "watermark_legal")
    assert check["status"] == "WARN"
    assert check["severity"] == "MAJOR"
    assert check["observed"]["max_lead_days"] == 1
    assert payload["state"] == DEGRADED, payload["verdict"]["reasons"]
    ledger.close()


def test_a_lead_beyond_the_grace_window_is_a_failure(tmp_path: Path):
    ledger = _healthy_ledger(tmp_path)
    _successful_run(ledger, "pubmed")
    ledger.set_watermark("pubmed", _future_watermark(3))
    payload = _status(ledger)
    check = _check(payload, "watermark_legal")
    assert check["status"] == "FAIL"
    assert check["severity"] == "CRITICAL"
    assert payload["state"] == UNHEALTHY
    ledger.close()
