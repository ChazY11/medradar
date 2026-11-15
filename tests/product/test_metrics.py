"""The product must report four different things as four different numbers.

These tests pin the distinction between Attributed Share, Rule-verified Share, Curated Share,
Estimated Attribution Precision and Retrieval Coverage, at record, applicant and organization level.
"""
from __future__ import annotations

import math

import pytest

from medradar.product.attribution import status as status_module


def test_metric_definitions_are_complete_and_distinct() -> None:
    definitions = {item["id"]: item for item in status_module.metric_definitions()}
    assert set(definitions) == {
        "attributed_share",
        "rule_verified_share",
        "curated_share",
        "estimated_attribution_precision",
        "retrieval_coverage",
    }
    for item in definitions.values():
        assert item["name_en"] and item["name_zh"]
        assert item["definition_en"] and item["definition_zh"]
        assert item["is_not"]
    assert "NOT match precision" in definitions["attributed_share"]["is_not"]
    assert "UNKNOWN" in definitions["estimated_attribution_precision"]["definition_en"]


def test_record_level_shares_partition_the_attributed_records(dataset) -> None:
    metrics = dataset.metrics()
    record = metrics["levels"]["record"]
    attributed = record["attributed_records"]
    assert attributed == dataset.global_counts["records"]
    assert record["verified_records"] + record["rule_verified_records"] + record["provisional_records"] == attributed
    assert math.isclose(
        record["curated_share"] + record["rule_verified_share"] + record["provisional_share"],
        1.0,
        abs_tol=1e-5,
    )
    assert sum(record["by_status"].values()) == attributed


def test_attributed_share_is_not_curated_share(dataset) -> None:
    record = dataset.metrics()["levels"]["record"]
    assert record["attributed_share"] > 0.99
    assert record["curated_share"] < record["attributed_share"] / 2
    assert record["provisional_records"] > 0


def test_precision_is_never_derived_from_the_attributed_share(dataset) -> None:
    metrics = dataset.metrics()
    precision = metrics["estimated_attribution_precision"]
    assert precision["state"] in ("unknown", "estimated")
    if precision["state"] == "unknown":
        assert precision["estimate"] is None
        assert precision["confidence_interval_95"] is None
        assert "no completed independent sample" in precision["reason"].lower()
    else:
        # An estimate may only exist when a pre-registered sample review is on disk, and it must
        # carry its reviewer class and its interval. It is never a copy of the attributed share.
        assert precision["sample_size"] > 0
        assert precision["decidable_sample_size"] <= precision["sample_size"]
        assert precision["confidence_interval_95"] is not None
        assert precision["reviewer_kind"] in ("human", "agent")
        assert precision["estimate"] != metrics["levels"]["record"]["attributed_share"]
        assert precision["human_review_completed"] is False or precision["reviewer_kind"] == "human"
        assert precision.get("decision_rule"), "an estimate must publish the rule that produced it"
        assert precision.get("caveats")
        assert precision["undecidable"] == precision["sample_size"] - precision["decidable_sample_size"]
    retrieval = metrics["retrieval_coverage"]
    assert retrieval["state"] == "unknown"
    assert retrieval["value"] is None
    assert retrieval["what_would_be_needed"]
    assert "Attributed Share" in retrieval["not_the_same_as"]


def test_applicant_level_metrics_are_reported_separately(dataset) -> None:
    applicant = dataset.metrics()["levels"]["applicant"]
    assert applicant["applicant_strings_observed"] > 1000
    assert applicant["attributed_applicant_strings"] <= applicant["applicant_strings_observed"]
    assert applicant["accepted_spellings_in_registry"] >= applicant["attributed_applicant_strings"]
    assert 0 < applicant["largest_applicant_record_share"] < 0.2
    assert applicant["top10_applicant_record_share"] > applicant["largest_applicant_record_share"]
    assert "applicant-level" in applicant["concentration_note"]


def test_organization_level_metrics_resist_a_single_dominant_applicant(dataset) -> None:
    organization = dataset.metrics()["levels"]["organization"]
    assert organization["tracked_organizations"] == 59
    assert organization["organizations_with_records"] == 59
    assert organization["median_curated_share"] is not None
    assert organization["organizations_with_zero_verified_records"] > 0
    assert "median" in organization["note"]


def test_empty_selection_returns_unknown_not_zero(dataset) -> None:
    counts = dataset.counts([])
    assert counts["records"] == 0
    assert counts["curated_share"] is None
    assert counts["rule_verified_share"] is None
    assert counts["provisional_share"] is None
    assert counts["by_verification"] == {}


def test_review_ledger_state_is_reported_in_metrics(dataset) -> None:
    metrics = dataset.metrics()
    assert "review_ledger" in metrics
    assert "decisions_applied" in metrics["review_ledger"]
