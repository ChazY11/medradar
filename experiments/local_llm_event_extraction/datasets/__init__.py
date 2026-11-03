"""Datasets: synthetic fixtures, grouped splits and leakage guards."""

from __future__ import annotations

from .splits import (
    DEFAULT_RATIOS,
    DEFAULT_SEED,
    SPLITS,
    assign_grouped_splits,
    assert_no_leakage,
    near_duplicate_pairs,
)
from .synthetic import (
    CASES_PATH,
    DATASET_NAME,
    DATASET_VERSION,
    LABEL_TIER,
    RESPONSES_PATH,
    ROSTER_ALIASES,
    build_dataset,
    dataset_sha256,
    describe_fixture,
    load_cases,
    load_responses,
)

__all__ = [
    "CASES_PATH",
    "DATASET_NAME",
    "DATASET_VERSION",
    "DEFAULT_RATIOS",
    "DEFAULT_SEED",
    "LABEL_TIER",
    "RESPONSES_PATH",
    "ROSTER_ALIASES",
    "SPLITS",
    "assign_grouped_splits",
    "assert_no_leakage",
    "build_dataset",
    "dataset_sha256",
    "describe_fixture",
    "load_cases",
    "load_responses",
    "near_duplicate_pairs",
]
