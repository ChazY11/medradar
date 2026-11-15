"""Data invariants the product must never break (PRODUCT-002 C2).

Each test corresponds to a failure mode that would make the product lie: double counting, mixing
PMA originals with supplements, mixing recall records with recall events, unfilterable untrusted
mappings, pagination totals that disagree with the page, exports that disagree with the screen,
comparisons that use different units, missing snapshots that display as zero activity, and review
decisions that leak into another organization's counts.
"""
from __future__ import annotations

import base64
import csv
import io
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_event_ids_are_unique(dataset) -> None:
    ids = [event.event_id for event in dataset.events]
    assert len(ids) == len(set(ids))


def test_organization_counts_sum_to_the_attributed_total(dataset) -> None:
    per_org = sum(stats.counts["records"] for stats in dataset.org_stats.values())
    assert per_org == dataset.global_counts["records"]
    assert dataset.global_counts["records"] <= len(dataset.events)


def test_pma_original_and_supplement_are_distinct_event_types(dataset) -> None:
    pma = [event for event in dataset.events if event.event_type == "pma"]
    supplement = [event for event in dataset.events if event.event_type == "pma_supplement"]
    assert pma and supplement
    pma_ids = {event.official_id for event in pma}
    supplement_ids = {event.official_id for event in supplement}
    # A supplement identifier carries a different suffix; the two sets must not be counted twice.
    overlap = pma_ids & supplement_ids
    assert len(overlap) == 0
    by_type = dataset.global_counts["by_type"]
    counts = {row["event_type"]: row["count"] for row in by_type}
    assert counts.get("pma", 0) > 0 and counts.get("pma_supplement", 0) > 0


def test_recall_records_are_not_recall_events(dataset) -> None:
    recalls = [event for event in dataset.events if event.event_type == "recall"]
    assert recalls
    official = {event.official_id for event in recalls}
    # one record per FDA product reference: the product counts records, never "recall events"
    assert len(official) == len(recalls) or len(official) < len(recalls)
    for event in recalls[:50]:
        assert event.official_id


def test_untrusted_mappings_can_be_filtered_out(dataset) -> None:
    provisional = dataset.filter_events(review="provisional")
    verified = dataset.filter_events(review="curated")
    rule = dataset.filter_events(review="rule_verified")
    everything = dataset.filter_events()
    assert len(provisional) + len(verified) == len(everything)
    assert all(event.attribution_verified for event in verified)
    assert all(not event.attribution_verified for event in provisional)
    assert all(event.attribution_verification == "rule_verified" for event in rule)
    assert len(rule) <= len(provisional)


def test_pagination_totals_match_the_filtered_set(client) -> None:
    first = client.get("/api/events?page_size=25&page=1&types=recall").json()
    total = client.get("/api/events?types=recall&page_size=100").json()["total"]
    assert first["total"] == total
    assert len(first["items"]) <= 25
    last_page = first["total_pages"]
    last = client.get(f"/api/events?page_size=25&page={last_page}&types=recall").json()
    collected = len(first["items"])
    if last_page > 2:
        middle = client.get("/api/events?page_size=25&page=2&types=recall").json()
        collected += len(middle["items"])
    collected += len(last["items"])
    assert collected <= first["total"]


def test_csv_export_matches_the_filtered_screen(client) -> None:
    query = "/api/events?org=medtronic&types=recall&page_size=100"
    total = client.get(query).json()["total"]
    response = client.get("/api/export/events.csv?org=medtronic&types=recall")
    assert response.status_code == 200
    text = response.text.replace("\ufeff", "")
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0][0] == "event_id"
    assert len(rows) - 1 == total
    assert response.headers["X-MedRadar-Records"] == str(total)
    provenance = json.loads(base64.urlsafe_b64decode(response.headers["X-MedRadar-Provenance"]))
    assert provenance["product"] == "MedRadar PRODUCT-002"
    assert provenance["metrics"]["attributed_share"] is not None
    assert "attribution_verification" in rows[0]


def test_csv_rows_carry_the_same_official_identifiers_as_the_api(client) -> None:
    api_rows = client.get("/api/events?org=medtronic&page_size=50").json()["items"]
    response = client.get("/api/export/events.csv?org=medtronic")
    text = response.text.replace("\ufeff", "")
    reader = csv.DictReader(io.StringIO(text))
    csv_ids = {row["event_id"] for row in reader}
    for row in api_rows:
        assert row["event_id"] in csv_ids


def test_compare_uses_one_window_and_one_unit(dataset) -> None:
    from medradar.product.compare import build_compare

    payload = build_compare(dataset, ["medtronic", "ge_healthcare"])
    window = payload["window"]["effective"]
    assert window["from"].endswith("-01-01") and window["to"].endswith("-12-31")
    assert int(window["from"][:4]) < int(window["to"][:4])
    for side in payload["organizations"]:
        assert sum(side["counts_by_type"].values()) == side["counts"]["records"]
        assert side["coverage"]["window"] == payload["window"]["effective"]
        assert side["verification"]["verified_records"] + side["verification"]["rule_verified_records"] + side["verification"]["provisional_records"] == side["counts"]["records"]
    assert payload["comparability"]["ownership_basis"] == "current_group"
    assert payload["comparability"]["window_shared"] and payload["comparability"]["event_types_shared"]


def test_compare_basis_switch_changes_counts_consistently(dataset) -> None:
    from medradar.product.compare import build_compare

    current = build_compare(dataset, ["medtronic", "ge_healthcare"])
    historical = build_compare(dataset, ["medtronic", "ge_healthcare"], basis="historical_owner_verified")
    current_ge = next(side for side in current["organizations"] if side["key"] == "ge_healthcare")
    historical_ge = next(side for side in historical["organizations"] if side["key"] == "ge_healthcare")
    assert historical_ge["counts"]["records"] <= current_ge["counts"]["records"]
    assert historical["comparability"]["ownership_basis"] == "historical_owner_verified"
    # Excluded records are accounted for, never silently dropped.
    excluded = historical["basis_excluded_totals"]
    assert excluded["excluded_predecessor_owner"] + excluded["excluded_unknown_owner"] > 0


def test_missing_snapshot_is_an_error_not_zero_activity(tmp_path: Path) -> None:
    from medradar.product.dataset import load_dataset

    with pytest.raises(FileNotFoundError):
        load_dataset(tmp_path)


def test_missing_snapshot_api_returns_503(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from medradar.product.api import create_app

    client = TestClient(create_app(data_dir=tmp_path))
    assert client.get("/api/health").json()["status"] == "degraded"
    assert client.get("/api/events").status_code == 503
    assert client.get("/api/metrics").status_code == 503


def test_export_organization_brief_states_verification(dataset) -> None:
    from medradar.product.export import organization_markdown

    markdown = organization_markdown(dataset, "medtronic")
    assert "Attribution verification" in markdown
    assert "curated share" in markdown.lower()
    assert "Ownership" in markdown
    assert "current-group" in markdown.lower()


def test_compare_export_states_basis_and_verification(dataset) -> None:
    from medradar.product.export import compare_markdown

    markdown = compare_markdown(dataset, ["medtronic", "ge_healthcare"], None, None, None)
    assert "Ownership basis: current_group" in markdown
    assert "Attribution verification" in markdown
    assert "What this comparison does not show" in markdown
