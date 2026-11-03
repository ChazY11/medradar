"""Benchmark: arm-agnostic runner, scorer and (honest) report writer."""

from __future__ import annotations

from .metrics import DEFAULT_SCORING_CONFIG, TAXONOMY_KEYS, score_predictions
from .report import NOT_MEASURED, SYNTHETIC_BANNER, write_report
from .runner import (
    RUNNER_VERSION,
    BenchmarkRun,
    canonical_json,
    peak_rss_mb,
    run_benchmark,
    sha256_json,
    sha256_text,
)

__all__ = [
    "BenchmarkRun",
    "DEFAULT_SCORING_CONFIG",
    "NOT_MEASURED",
    "RUNNER_VERSION",
    "SYNTHETIC_BANNER",
    "TAXONOMY_KEYS",
    "canonical_json",
    "peak_rss_mb",
    "run_benchmark",
    "score_predictions",
    "sha256_json",
    "sha256_text",
    "write_report",
]
