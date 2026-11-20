"""Human judgement over HTTP: watchlists, review decisions, audit and export.

The claim under test: a person can save what they care about, record what they concluded, and take
the result out of the product - while the evidence ledger stays untouched and every write leaves a
trace.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:  # pragma: no cover
    raise unittest.SkipTest("fastapi is not installed")

from medradar.product.api import create_app
from medradar.radar.classify import RuleMapper
from medradar.radar.engine import apply_admissions
from medradar.radar.human import HumanStore, REVIEW_STATES
from medradar.radar.ledger import ObservationLedger
from medradar.radar.records import MAPPING_VERSION, RawRecord
from medradar.radar.taxonomy import load_taxonomy

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "radar"

#: The feed scopes are windows over first_observed_at, so seeded records must look freshly
#: observed or the "observed" scope correctly hides them.
_NOW = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
_TODAY = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def _seed(radar_dir: Path) -> list[str]:
    radar_dir.mkdir(parents=True, exist_ok=True)
    taxonomy = load_taxonomy(str(CONFIG_DIR))
    mapper = RuleMapper(taxonomy)
    ledger = ObservationLedger(radar_dir / "radar.db")
    ledger.ensure_source("crossref", label="Crossref", adapter_version="a1", cadence_hours=6)
    ledger.ensure_source("openfda_recall", label="FDA recalls", adapter_version="a1", cadence_hours=24)
    ids: list[str] = []
    for key, title, source, record_type in (
        ("10.1/aa", "Patient monitor SpO2 algorithm accuracy in critical care", "crossref", "publication"),
        ("10.1/bb", "Sourdough fermentation of rye flour and crumb texture", "crossref", "publication"),
        ("Z-0001-2026", "Patient monitor battery may fail during use", "openfda_recall", "regulatory_record"),
    ):
        record = RawRecord(
            source=source, source_record_id=source + ":" + key, official_identifier=key,
            record_type=record_type, title=title,
            url="https://example.invalid/" + key,
            published_at=_TODAY, published_at_precision="date",
            payload={"id": key, "title": title, "abstract": "Monitoring study."},
            text=title + " Monitoring study.",
            extra={"organization_hint": "Philips Medical Systems",
                   "organization_role": "regulatory_applicant",
                   "product_codes": ["MHX"], "product_hint": "Patient monitor"},
        )
        outcome = ledger.record_observation(
            record, mapper.map(record), run_id="r-human", adapter_version="a1",
            mapping_version=MAPPING_VERSION, seen_at=_NOW)
        ids.append(outcome.observation_id)
    apply_admissions(ledger, limit=50)
    ledger.close()
    return ids


@pytest.fixture()
def client(tmp_path: Path):
    radar_dir = tmp_path / "radar"
    ids = _seed(radar_dir)
    web_dir = tmp_path / "web"
    web_dir.mkdir()
    (web_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    app = create_app(data_dir=tmp_path / "data", web_dir=web_dir, radar_dir=radar_dir)
    return TestClient(app), ids, radar_dir


def test_a_watchlist_round_trips_and_is_audited(tmp_path: Path):
    store = HumanStore(str(tmp_path / "human.db"))
    saved = store.save_watchlist("My recalls", {"source": "openfda_recall", "scope": "observed"})
    assert saved["name"] == "My recalls"
    assert saved["filter"]["source"] == "openfda_recall"
    assert [item["id"] for item in store.list_watchlists()] == [saved["id"]]

    updated = store.save_watchlist("Renamed", {"source": "crossref"}, watchlist_id=saved["id"])
    assert updated["name"] == "Renamed"
    assert updated["filter"]["source"] == "crossref"

    assert store.delete_watchlist(saved["id"]) is True
    assert store.list_watchlists() == []
    actions = [row["action"] for row in store.audit_log()]
    assert "watchlist.create" in actions and "watchlist.update" in actions and "watchlist.delete" in actions
    store.close()


def test_a_saved_filter_cannot_smuggle_unknown_keys(tmp_path: Path):
    store = HumanStore(str(tmp_path / "human.db"))
    saved = store.save_watchlist("x", {"source": "pubmed", "evil": "DROP TABLE observation"})
    assert "evil" not in saved["filter"]
    store.close()


def test_review_transitions_are_append_only_and_validated(tmp_path: Path):
    store = HumanStore(str(tmp_path / "human.db"))
    first = store.set_review("obs-1", status="REVIEWING", assignee="me", note="look at this")
    assert first["status"] == "REVIEWING"
    second = store.set_review("obs-1", status="CONFIRMED", note="verified against FDA")
    assert second["status"] == "CONFIRMED"
    assert second["assignee"] == "me", "an omitted field keeps its previous value"
    history = store.review_history("obs-1")
    assert len(history) == 2
    assert history[0]["from_status"] == "REVIEWING" and history[0]["to_status"] == "CONFIRMED"
    with pytest.raises(ValueError):
        store.set_review("obs-1", status="NOT_A_STATE")
    assert store.stats()["reviews"] == 1
    store.close()


def test_watchlists_over_http_are_counted_against_the_ledger(client):
    http, ids, _radar = client
    created = http.post("/api/radar/watchlists", json={
        "name": "Recalls", "filter": {"source": "openfda_recall", "scope": "observed"}}).json()
    assert created["watchlist"]["name"] == "Recalls"
    listed = http.get("/api/radar/watchlists", params={"counts": "1"}).json()
    assert listed["count"] == 1
    assert listed["items"][0]["count"] is not None
    removed = http.delete("/api/radar/watchlists/" + created["watchlist"]["id"]).json()
    assert removed["deleted"] == created["watchlist"]["id"]
    assert http.get("/api/radar/watchlists").json()["count"] == 0


def test_review_over_http_persists_and_feeds_the_queue(client):
    http, ids, _radar = client
    target = ids[0]
    response = http.post("/api/radar/review/" + target,
                         json={"status": "CONFIRMED", "note": "checked"}).json()
    assert response["review"]["status"] == "CONFIRMED"
    fetched = http.get("/api/radar/review/" + target).json()
    assert fetched["review"]["note"] == "checked"
    queue = http.get("/api/radar/review/queue", params={"status": "CONFIRMED"}).json()
    assert queue["count"] == 1
    assert queue["items"][0]["title"], "the queue carries the record title, not just an id"
    bad = http.post("/api/radar/review/" + target, json={"status": "NOPE"})
    assert bad.status_code == 400
    audit = http.get("/api/radar/audit").json()
    assert any(row["action"].startswith("review.") for row in audit["items"])


def test_export_emits_the_columns_a_reader_needs(client):
    http, ids, _radar = client
    http.post("/api/radar/review/" + ids[0], json={"status": "CONFIRMED"})
    response = http.get("/api/radar/export", params={"format": "csv", "scope": "observed"})
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    lines = response.text.strip().splitlines()
    header = lines[0].split(",")
    assert "observation_id" in header and "review_status" in header and "decision" in header
    assert len(lines) >= 2, "the export contains the records the reader was looking at"
    as_json = http.get("/api/radar/export", params={"format": "json", "scope": "observed"}).json()
    assert as_json["count"] >= 1
    assert any(record["review_status"] == "CONFIRMED" for record in as_json["records"])


def test_a_company_page_answers_in_the_readers_unit(client):
    http, ids, _radar = client
    companies = http.get("/api/radar/companies").json()
    assert companies["available"] is True
    assert companies["count"] >= 1
    organization_id = companies["items"][0]["organization_id"]
    page = http.get("/api/radar/company/" + organization_id).json()
    assert page["company"]["organization_id"] == organization_id
    assert page["totals"]["observations"] >= 1
    assert isinstance(page["recent"], list) and page["recent"]
    assert http.get("/api/radar/company/does-not-exist").status_code == 404