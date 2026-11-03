"""Tier A/B tests for MedRadar 2.0 measurement correctness.

Tier A tests pure arithmetic (period boundaries, complete windows, LQ,
approval-type classification) with no database.

Tier B tests run the *production* measurement code against a synthetic SQLite
fixture built in ``tests/product_fixture.py``. Expected values are constructed
independently (hand arithmetic / explicit fixture counts), never by calling the
function under test and asserting it equals itself.
"""
from __future__ import annotations

from datetime import date

import pytest

from medradar.product import store
from medradar.product.store import (
    approval_classification,
    comparison_windows,
    complete_window,
    is_period_partial,
    location_quotient,
    period_bounds,
    period_flags,
    window_completeness,
)

from tests.product_fixture import build_fixture


# --------------------------------------------------------------------- Tier A
@pytest.mark.parametrize(
    "period, granularity, expected",
    [
        ("2021-Q4", "quarter", (date(2021, 10, 1), date(2021, 12, 31))),
        ("2022-Q1", "quarter", (date(2022, 1, 1), date(2022, 3, 31))),
        ("2024", "year", (date(2024, 1, 1), date(2024, 12, 31))),
        ("2024-02", "month", (date(2024, 2, 1), date(2024, 2, 29))),
        ("2023-02", "month", (date(2023, 2, 1), date(2023, 2, 28))),
    ],
)
def test_period_bounds(period, granularity, expected):
    assert period_bounds(period, granularity) == expected


def test_partial_period_at_both_window_edges():
    start, end = "2021-10-16", "2026-10-15"
    assert is_period_partial("2021-Q4", "quarter", start, end) is True  # clipped at start
    assert is_period_partial("2026-Q4", "quarter", start, end) is True  # clipped at end
    assert is_period_partial("2022-Q1", "quarter", start, end) is False
    assert is_period_partial("2026-Q3", "quarter", start, end) is False
    # 2026-Q3 is calendar-complete but only 15 days from the data edge
    flags = period_flags("2026-Q3", "quarter", start, end, "2026-10-15")
    assert flags["complete"] is True
    assert flags["source_lag_risk"] is True
    assert is_period_partial("2021", "year", start, end) is True
    assert is_period_partial("2026", "year", start, end) is True
    assert is_period_partial("2021-10", "month", start, end) is True
    assert is_period_partial("2026-10", "month", start, end) is True


def test_complete_window_quarter_year_month():
    assert complete_window("2021-10-16", "2026-10-15", "quarter") == ("2022-01-01", "2026-09-30")
    assert complete_window("2021-10-16", "2026-10-15", "year") == ("2022-01-01", "2025-12-31")
    assert complete_window("2021-10-16", "2026-10-15", "month") == ("2021-11-01", "2026-09-30")
    assert complete_window("2026-10-01", "2026-10-15", "quarter") is None
    assert complete_window("2022-01-01", "2022-12-31", "year") == ("2022-01-01", "2022-12-31")


def test_comparison_windows_are_contiguous_and_equal_length():
    windows = comparison_windows("2021-10-16", "2026-10-15", "quarter")
    assert windows["comparable"] is True
    assert windows["analysis_start"] == "2022-01-01"
    assert windows["analysis_end"] == "2026-09-30"
    # prior window is the *same number* of complete quarters immediately before
    assert windows["periods"] == 19
    assert windows["prior_analysis_end"] == "2021-12-31"
    assert windows["prior_analysis_start"] == "2017-04-01"
    # no overlap and no gap between the two windows
    assert windows["prior_analysis_end"] < windows["analysis_start"]
    prior_end = date.fromisoformat(windows["prior_analysis_end"])
    recent_start = date.fromisoformat(windows["analysis_start"])
    assert (recent_start - prior_end).days == 1


def test_window_with_no_complete_period_is_not_comparable():
    windows = comparison_windows("2026-10-01", "2026-10-15", "quarter")
    assert windows["comparable"] is False
    assert windows["analysis_start"] is None
    assert "无法进行完整周期比较" in windows["reason_zh"]


def test_lq_uses_mapped_denominators_not_all_records():
    # company: 30 of 40 mapped records are in the track; 10 unmapped records exist
    # industry: 50 of 120 mapped records are in the same track
    value, status = location_quotient(30, 40, 50, 120)
    assert status == "ok"
    assert value == pytest.approx(1.8)
    old_wrong = (30 / 50) / (50 / 120)  # company denominator used *all* records
    assert value != pytest.approx(old_wrong)
    assert value == pytest.approx(1.8, abs=1e-9)


def test_lq_not_applicable_when_denominator_or_sample_is_too_small():
    assert location_quotient(0, 40, 50, 120) == (None, "zero_company_track")
    assert location_quotient(3, 4, 50, 120) == (None, "low_company_mapped_sample")
    assert location_quotient(3, 40, 4, 120) == (None, "low_industry_track_sample")
    assert location_quotient(1, 0, 10, 120) == (None, "zero_denominator")


def test_approval_classification_from_payload_fields():
    import json

    original = approval_classification("pma", json.dumps({"pma_number": "P1", "supplement_number": ""}))
    supplement = approval_classification(
        "pma",
        json.dumps({"pma_number": "P1", "supplement_number": "S001", "supplement_type": "30-Day Notice"}),
    )
    unknown = approval_classification("pma", "{not-json")
    traditional = approval_classification("510k", json.dumps({"k_number": "K1", "clearance_type": "Traditional"}))
    special = approval_classification("510k", json.dumps({"k_number": "K1", "clearance_type": "Special"}))
    assert original["approval_type"] == "pma_original" and original["is_first_entry_candidate"] is True
    assert supplement["approval_type"] == "pma_supplement" and supplement["is_first_entry_candidate"] is False
    assert supplement["classification_detail"] == "30-Day Notice"
    assert unknown["approval_type"] == "pma_unknown" and unknown["classification_available"] is False
    assert traditional["approval_type"] == "510k_traditional" and traditional["is_first_entry_candidate"] is True
    assert special["approval_type"] == "510k_special" and special["is_first_entry_candidate"] is False


# --------------------------------------------------------------------- Tier B
@pytest.fixture()
def fixture(tmp_path):
    expected = build_fixture(tmp_path / "synthetic_medradar.sqlite")
    with store.use_database(expected["path"]):
        yield expected


def _assert_close(actual, expected, tolerance=1e-9):
    assert actual == pytest.approx(expected, abs=tolerance)


def test_fixture_compare_lq_uses_consistent_denominators(fixture):
    result = store.company_compare(("medtronic", "philips", "draeger"), "approvals", 5, "quarter")
    analysis = result["analysis_window"]
    assert analysis["analysis_start"] == fixture["analysis"]["start"]
    assert analysis["analysis_end"] == fixture["analysis"]["end"]
    assert analysis["prior_analysis_start"] == fixture["analysis"]["prior_start"]
    assert analysis["prior_analysis_end"] == fixture["analysis"]["prior_end"]
    assert analysis["periods"] == fixture["analysis"]["periods"]

    by_key = {company["key"]: company for company in result["companies"]}
    expectations = fixture["companies"]
    for key in ("medtronic", "philips", "draeger"):
        company = by_key[key]
        assert company["total_all"] == expectations[key]["recent_all"]
        assert company["total_mapped"] == expectations[key]["recent_mapped"]
        assert company["prior_total_all"] == expectations[key]["prior_all"]
        _assert_close(company["mapping_coverage"], expectations[key]["mapping_coverage"])

    rows = {row["track"]: row for row in result["track_table"]}
    cardiac = rows["cardiac_rhythm"]
    assert cardiac["industry_total"] == fixture["industry"]["track_counts_recent"]["cardiac_rhythm"]
    med = next(cell for cell in cardiac["companies"] if cell["key"] == "medtronic")
    assert med["n"] == 30
    _assert_close(med["location_quotient"], fixture["lq"]["medtronic_cardiac"])
    # explicitly demonstrate that the old, inconsistent formula would have produced a different value
    assert med["location_quotient"] != pytest.approx(fixture["old_wrong_lq"]["medtronic_cardiac"])
    assert med["lq_status"] == "ok"

    draeger_resp = rows["respiratory"]
    draeger = next(cell for cell in draeger_resp["companies"] if cell["key"] == "draeger")
    assert draeger["n"] == 8
    assert draeger["location_quotient"] is None
    assert draeger["lq_status"] == "low_company_mapped_sample"

    med_monitor = next(
        cell for cell in rows["patient_monitoring"]["companies"] if cell["key"] == "medtronic"
    )
    assert med_monitor["n"] == 0
    assert med_monitor["location_quotient"] is None
    assert med_monitor["lq_status"] == "zero_company_track"


def test_fixture_industry_coverage_is_disclosed(fixture):
    result = store.company_compare(("medtronic", "philips"), "approvals", 5, "quarter")
    coverage = result["comparability"]["industry_records"]
    assert coverage["mapped_records"] == fixture["industry"]["recent_mapped"]
    assert coverage["all_records"] == fixture["industry"]["recent_all"]
    assert coverage["unmapped_records"] == fixture["industry"]["recent_unmapped"]
    _assert_close(coverage["mapping_coverage"], fixture["industry"]["mapping_coverage"])
    # each company's own coverage is reported separately
    assert result["comparability"]["company_mapping_coverage"]["medtronic"] == pytest.approx(0.8)
    assert result["comparability"]["company_mapping_coverage"]["philips"] == pytest.approx(1.0)


def test_fixture_complete_period_totals_exclude_partial_edges(fixture):
    table = store.company_track_table("medtronic", "approvals", fixture["window"]["start"], fixture["window"]["end"])
    cardiac = next(row for row in table["rows"] if row["track"] == "cardiac_rhythm")
    # complete window has 30; exact window adds the two partial-edge events (2021-Q4, 2026-Q4)
    assert cardiac["recent"] == 30
    assert cardiac["recent_all"] == 32
    assert table["total_recent"] == 40
    assert table["total_recent_all"] == 43
    assert table["analysis_window"]["start"] == fixture["analysis"]["start"]
    assert table["analysis_window"]["end"] == fixture["analysis"]["end"]

    series = store.company_series("medtronic", "approvals", fixture["window"]["start"], fixture["window"]["end"], "quarter")
    points = {point["period"]: point for point in series["points"]}
    assert points["2021-Q4"]["partial"] is True
    assert points["2026-Q4"]["partial"] is True
    assert points["2022-Q1"]["complete"] is True
    assert points["2026-Q3"]["complete"] is True
    assert points["2026-Q3"]["source_lag_risk"] is True
    assert series["total_complete"] < series["total"]
    assert series["partial_periods"] == 2


def test_fixture_pathway_is_window_based_and_all_time_is_separate(fixture):
    result = store.company_compare(("medtronic", "philips"), "approvals", 5, "quarter")
    med = next(company for company in result["companies"] if company["key"] == "medtronic")
    assert med["pathway"]["basis"] == "complete_window_approvals_only"
    assert med["pathway"]["window"]["start"] == fixture["analysis"]["start"]
    assert med["pathway"]["pma_original"] == 3
    assert med["pathway"]["pma_supplement"] == 34
    assert med["pathway_all_time"] is None  # not computed unless explicitly requested

    with_all_time = store.company_compare(
        ("medtronic", "philips"), "approvals", 5, "quarter", include_all_time=True
    )
    med_all = next(company for company in with_all_time["companies"] if company["key"] == "medtronic")
    assert med_all["pathway_all_time"]["pma_original"] == 5
    assert med_all["pathway_all_time"]["pma_supplement"] == 48
    assert med_all["pathway_all_time"]["pma_original"] != med_all["pathway"]["pma_original"]


def test_fixture_pma_first_entry_ignores_supplements_and_special_510k(fixture):
    profile = store.company_profile("medtronic", 5)
    rows = {row["track"]: row for row in profile["tracks"]["rows"]}
    respiratory = rows["respiratory"]
    # earliest record is a 2016 supplement; the first *original* approval is 2018-09-01
    assert respiratory["first_any_approval"] == "2015-05-01"
    assert respiratory["first_approval"] == "2016-09-01"
    assert respiratory["new_in_window"] is False

    milestones = profile["milestones"]
    entry_labels = [item for item in milestones if item.get("approval_type") == "first_entry_candidate"]
    assert entry_labels, "fixture should produce first-entry milestones"
    assert all("数据覆盖期内首次观察到原始批准" in item["label_zh"] for item in entry_labels)

    # draeger is roster-absent and only matched through the exact alias set
    evidence = store.evidence_search(companies=("draeger",), limit=5)
    assert evidence["total"] > 0
    assert all(item["company_match"] == "exact_alias" for item in evidence["items"])


def test_fixture_claims_use_complete_windows_and_recompute(fixture):
    payload = store.company_claims("medtronic", 5)
    assert payload["window"]["start"] == fixture["analysis"]["start"]
    assert payload["window"]["end"] == fixture["analysis"]["end"]
    assert payload["claims"], "fixture medtronic should produce claims"
    claim = payload["claims"][0]
    assert claim["metrics"]["basis"] == "complete_quarters"
    assert claim["window"]["recent_start"] == fixture["analysis"]["start"]
    recomputed = store.claim_evidence(claim["evidence_params"])
    assert recomputed["recomputed"]["recent"] == claim["metrics"]["recent"]
    assert recomputed["recomputed"]["prior"] == claim["metrics"]["prior"]
    # PMA supplements must be disclosed next to the count
    if claim["metrics"]["pma_supplement_recent"]:
        assert any("PMA 补充申请" in caveat for caveat in claim["caveats"])


def test_fixture_radar_uses_complete_windows_and_discloses_attribution(fixture):
    detail = store.radar_track("respiratory", 5)
    assert detail["totals"]["recent"] == 10
    assert detail["totals"]["prior"] == 3
    assert detail["totals"]["recent_all"] == 11
    assert detail["totals"]["partial_total"] == 1
    assert detail["window"]["analysis_start"] == fixture["analysis"]["start"]
    assert detail["attribution"]["attributed_recent"] + detail["attribution"]["unattributed_recent"] == detail["totals"]["recent"]
    # draeger records are attributed through the exact alias index
    draeger = next((company for company in detail["companies"] if company["company"] == "draeger"), None)
    assert draeger is not None and draeger["n"] == 8
    # entrants are based on first *original* approval, not supplements
    assert all(entry["first_date"] >= fixture["analysis"]["start"] for entry in detail["entrants"])


def test_fixture_meta_reports_classification_unavailable(fixture):
    meta = store.dataset_meta()
    audit = meta["dataset"]["approval_classification"]
    assert audit["pma_total"] > 0
    assert audit["pma_unknown"] == fixture["classification_unknown"]
    assert audit["pma_classification_available"] is False
    assert audit["k510_classification_available"] is True
    assert "supplement_number" in audit["rule_zh"]


def test_fixture_event_detail_exposes_approval_type(fixture):
    search = store.evidence_search(track="imaging_us", metric="pma", limit=50)
    types = set()
    for item in search["items"]:
        detail = store.event_detail(item["event_id"])
        approval = detail["approval"]
        types.add(approval["approval_type"])
        assert approval["approval_type_label_zh"]
        assert approval["classification_available"] in (True, False)
        # list and detail endpoints must agree on the classification
        assert item["approval_type"] == approval["approval_type"]
        assert item["is_first_entry_candidate"] == approval["is_first_entry_candidate"]
    assert "pma_original" in types
    assert "pma_supplement" in types
    assert "pma_unknown" in types
