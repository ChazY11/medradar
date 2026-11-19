"""The daily digest: what arrived today and what deserves a look.

The claim under test is narrow: the digest reports what the ledger actually recorded, ranks it by
the stored admission, collapses the same work recorded twice, never presents a future-dated record
as today's news, and says so plainly when nothing arrived.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from medradar.radar.classify import RuleMapper
from medradar.radar.digest import digest
from medradar.radar.engine import apply_admissions
from medradar.radar.ledger import ObservationLedger
from medradar.radar.records import MAPPING_VERSION, RawRecord
from medradar.radar.taxonomy import load_taxonomy

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "radar"
NOW = dt.datetime(2026, 5, 20, 12, 0, tzinfo=dt.timezone.utc)


def _ledger(tmp_path: Path) -> ObservationLedger:
    handle = ObservationLedger(tmp_path / "radar.db")
    handle.ensure_source("crossref", label="Crossref", adapter_version="a1", cadence_hours=6)
    handle.ensure_source("openfda_recall", label="FDA recalls", adapter_version="a1",
                         cadence_hours=24)
    return handle


def _record(ledger: ObservationLedger, *, source: str, key: str, title: str,
            published: str | None = None, record_type: str = "publication",
            seen_at: str | None = None):
    record = RawRecord(
        source=source, source_record_id=f"{source}:{key}", official_identifier=key,
        record_type=record_type, title=title,
        url=f"https://example.invalid/{key}",
        published_at=published,
        **({"published_at_precision": "date"} if published else {}),
        payload={"id": key, "title": title, "abstract": "Monitoring study."},
        text=title + " Monitoring study.",
        extra={"organization_hint": "Philips Medical Systems",
               "organization_role": "regulatory_applicant",
               "product_codes": ["MHX"], "product_hint": "Patient monitor"},
    )
    return ledger.record_observation(
        record, RuleMapper(load_taxonomy(str(CONFIG_DIR))).map(record),
        run_id="r-digest", adapter_version="a1", mapping_version=MAPPING_VERSION,
        seen_at=seen_at or "2026-05-20T06:00:00+00:00")


def test_a_quiet_day_says_so_instead_of_inventing_items(tmp_path: Path):
    ledger = _ledger(tmp_path)
    payload = digest(ledger, hours=24, now=NOW)
    assert payload["empty"] is True
    assert payload["totals"]["arrived"] == 0
    assert payload["items"] == []
    assert any(warning["code"] == "quiet_day" for warning in payload["warnings"])
    ledger.close()


def test_the_digest_counts_what_arrived_and_lists_only_the_admitted_items(tmp_path: Path):
    ledger = _ledger(tmp_path)
    _record(ledger, source="crossref", key="10.1/aa",
            title="Accuracy of a patient monitor SpO2 algorithm in critical care")
    _record(ledger, source="crossref", key="10.1/bb",
            title="Sourdough fermentation of rye flour and crumb texture",
            published="2026-05-19")
    apply_admissions(ledger, limit=50)

    payload = digest(ledger, hours=24, now=NOW)
    assert payload["totals"]["arrived"] == 2
    listed = [item["title"] for item in payload["items"]]
    assert any("SpO2" in title for title in listed)
    assert not any("Sourdough" in title for title in listed), "excluded records must not be listed"
    ledger.close()


def test_the_same_work_recorded_twice_is_listed_once(tmp_path: Path):
    ledger = _ledger(tmp_path)
    title = "Patient monitor SpO2 algorithm accuracy in critical care"
    _record(ledger, source="crossref", key="10.1/dup-a", title=title)
    _record(ledger, source="crossref", key="10.1/dup-b", title="Abstract TH125: " + title)
    apply_admissions(ledger, limit=50)

    payload = digest(ledger, hours=24, now=NOW)
    matches = [item for item in payload["items"] if "SpO2 algorithm" in (item["title"] or "")]
    assert len(matches) == 1
    assert matches[0]["duplicates"] == 2
    assert not (matches[0]["title"] or "").startswith("Abstract")
    ledger.close()


def test_a_future_dated_record_is_flagged_and_ranked_last(tmp_path: Path):
    ledger = _ledger(tmp_path)
    _record(ledger, source="crossref", key="10.1/future",
            title="Patient monitor alarm algorithm performance benchmark in intensive care",
            published="2026-12-01")
    _record(ledger, source="crossref", key="10.1/today",
            title="Wearable sensor accuracy for patient monitor alarm validation in the ICU",
            published="2026-05-18")
    apply_admissions(ledger, limit=50)

    payload = digest(ledger, hours=24, now=NOW)
    future = [item for item in payload["items"] if item["future_dated"]]
    assert len(future) == 1
    assert payload["items"][-1]["future_dated"] is True, "future-dated items sort last"
    assert any(warning["code"] == "future_dated" for warning in payload["warnings"])
    ledger.close()


def test_a_recall_is_reported_as_safety_not_as_a_reading_recommendation(tmp_path: Path):
    ledger = _ledger(tmp_path)
    _record(ledger, source="openfda_recall", key="Z-0001-2026",
            title="Patient monitor battery may fail during use", record_type="regulatory_record",
            published="2026-05-19")
    apply_admissions(ledger, limit=50)

    payload = digest(ledger, hours=24, now=NOW)
    assert payload["totals"]["safety"] >= 1
    ledger.close()