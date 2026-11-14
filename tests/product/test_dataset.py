"""Measurement-layer semantics (DATA_CONTRACT sections 3, 5, 6, 7)."""
from __future__ import annotations

from medradar.product.dataset import aggregate


def test_every_record_is_accounted_for(dataset):
    attributed = sum(1 for event in dataset.events if event.organization_key)
    assert attributed == dataset.global_counts["records"]
    assert len(dataset.events) - attributed < len(dataset.events) * 0.05, "unattributed share should be small and visible"


def test_event_types_are_never_merged(dataset):
    by_type = {row["event_type"]: row["count"] for row in dataset.global_counts["by_type"]}
    assert set(by_type).issubset({"510k", "pma", "pma_supplement", "recall"})
    assert sum(by_type.values()) == dataset.global_counts["records"]


def test_pma_originals_and_supplements_are_distinct(dataset):
    pma = dataset.filter_events(event_types=["pma"], org_keys=["medtronic"])
    supplements = dataset.filter_events(event_types=["pma_supplement"], org_keys=["medtronic"])
    assert pma and supplements
    for event in pma:
        assert ":" not in event.official_id or event.source_id != "openfda_pma"
    for event in supplements:
        assert ":" in event.official_id


def test_undated_records_are_excluded_from_year_series(dataset):
    events = dataset.filter_events(event_types=["510k"])
    aggregations = aggregate(events)
    dated = sum(row["total"] for row in aggregations["by_year"])
    assert dated == len([event for event in events if event.event_date]) 
    assert aggregations["undated_records"] == len([event for event in events if not event.event_date])


def test_event_dates_are_plausible(dataset):
    for event in dataset.events:
        if event.event_date:
            year = int(event.event_date[:4])
            assert 1900 <= year <= 2100, "implausible event date was not quarantined: " + event.event_id


def test_published_at_is_never_backfilled(dataset):
    for event in dataset.events:
        if event.source_id in ("openfda_510k", "openfda_pma"):
            assert event.published_at is None
            assert event.published_at_status == "not_published_by_source"
        else:
            assert event.published_at_status in ("from_source", "not_published_by_source")


def test_first_observed_is_the_snapshot_time(dataset):
    for event in dataset.events:
        assert event.first_observed_at == dataset.collected_at
        if event.published_at:
            assert event.available_at == event.published_at
        else:
            assert event.available_at == dataset.collected_at


def test_category_comes_from_the_fda_dictionary(dataset):
    categories = {category.id for category in dataset.categories}
    assert "unclassified" not in categories
    for event in dataset.events:
        if event.category is not None:
            assert event.category.id in categories
            assert event.category.label


def test_unclassified_records_are_counted_not_dropped(dataset):
    events = dataset.filter_events(event_types=["510k"])
    unclassified = [event for event in events if event.category is None]
    counts = dataset.counts(events)
    assert counts["unmapped_category"] == len(unclassified)
    assert counts["records"] == len(events)


def test_organization_counts_equal_its_filtered_events(dataset):
    for key in ("medtronic", "ge_healthcare", "philips", "draeger", "mindray"):
        events = dataset.filter_events(org_keys=[key])
        assert dataset.org_stats[key].counts["records"] == len(events)


def test_coverage_reports_a_date_range_per_source(dataset):
    profile = dataset.organization_profile("philips")
    sources = profile["coverage"]["sources"]
    assert len(sources) == 3
    for row in sources:
        assert row["records"] >= 0
        if row["records"]:
            assert row["min_event_date"] and row["max_event_date"]
            assert row["min_event_date"] <= row["max_event_date"]


def test_resolve_event_by_official_identifier(dataset):
    event = next(iter(dataset.events))
    assert dataset.resolve_event(event.official_id) is not None
    assert dataset.resolve_event(event.event_id) is event
    assert dataset.resolve_event("K000000-NOT-REAL") is None


def test_search_returns_record_counts_and_ranges(dataset):
    payload = dataset.search("medtronic")
    assert payload["results"]
    top = payload["results"][0]
    assert top["key"] == "medtronic"
    assert top["event_count"] > 1000
    assert top["event_range"]["from"] and top["event_range"]["to"]


def test_no_result_search_is_not_an_error(dataset):
    payload = dataset.search("zzzz-not-a-company")
    assert payload["results"] == []
    assert payload["coverage"]["tracked_organizations"] >= 50


def test_metadata_states_the_limits(dataset):
    meta = dataset.meta()
    fields = {row["field"] for row in meta["time_semantics"]}
    assert {"event_date", "published_at", "first_observed_at", "available_at"} <= fields
    assert any("De Novo" in item["item"] for item in meta["out_of_scope"])
    assert meta["coverage"]["total_records"] >= meta["coverage"]["attributed_records"]
