"""Point-in-time publication and patent features.

Publications (OpenAlex annual counts)
-------------------------------------
OpenAlex gives publication-year counts, not publication timestamps, so the
feature builder uses only **complete years whose records are known at the
cutoff**. A year ``y`` is treated as complete by 15 February of ``y+1``
(conservative lag for indexing/deduplication), i.e. the knowledge time is
``date(y+1, 2, 15)``. At cutoff ``t`` the usable years are::

    {y : y <= t.year - 1 and date(y+1, 2, 15) <= t}

Therefore a 2024 paper (or the 2024 annual count) never affects a 2024-10-01
cutoff, and even a 2025-01-01 cutoff can only see 2023 data. The current
calendar year is never used.

Features (all appended to ``example["features"]``):

* ``pub_count_prev_year`` — works in the most recent usable year.
* ``pub_count_3y`` — works in the three most recent usable years.
* ``pub_growth_prev_year`` — ``(prev - prev_2) / prev_2``, ``None`` when the
  prior year is unknown or zero (no divide-by-zero, no invented growth).
* ``pub_intensity_vs_company`` — ``prev / max(3y_total / 3, 1)``: the latest
  year's output relative to the company's own 3-year annual mean (1.0 = in line
  with its recent baseline). This is a within-company normalisation, not a
  share of industry output.
* ``pub_missing`` — 1.0 when the company has no persisted publication counts (or
  no usable year), else 0.0. Missing is flagged, never zero-filled silently.

Patents (USPTO ODP or JSONL import)
-----------------------------------
Patent knowledge time is the **publication date**, never the filing date. The
patent features are defined for the same convention so the path is testable and
ready once a key/export exists; no patent ablation is reported here because no
live USPTO data is available in this environment.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable

from ...util import parse_date
from ..sources.patents import load_publications
from ..sources.publications import load_counts

PUBLICATION_FEATURES = (
    "pub_count_prev_year", "pub_count_3y", "pub_growth_prev_year",
    "pub_intensity_vs_company", "pub_missing",
)
PUBLICATION_START_YEAR = 2014
PUBLICATION_KNOWLEDGE_MONTH = 2
PUBLICATION_KNOWLEDGE_DAY = 15
PATENT_FEATURES = ("pat_apps_pub_12m", "pat_apps_pub_3y", "pat_missing")


def publication_knowledge_date(year: int) -> date:
    """Conservative date on which a complete publication year is usable."""
    return date(year + 1, PUBLICATION_KNOWLEDGE_MONTH, PUBLICATION_KNOWLEDGE_DAY)


def usable_publication_years(cutoff: Any, start_year: int = PUBLICATION_START_YEAR) -> list[int]:
    """Complete publication years whose knowledge date is on or before ``cutoff``."""
    day = parse_date(cutoff)
    if day is None:
        return []
    return [year for year in range(int(start_year), day.year) if publication_knowledge_date(year) <= day]


def publication_features(counts: dict[int, int] | None, cutoff: Any) -> dict[str, float | None]:
    """Compute the five publication features for one company at one cutoff."""
    years = usable_publication_years(cutoff)
    if not counts or not years:
        return {name: None for name in PUBLICATION_FEATURES} | {"pub_missing": 1.0}
    latest = years[-1]
    window = [latest - 2, latest - 1, latest]
    previous_year = float(counts.get(latest, 0))
    two_years_ago = counts.get(latest - 1)
    three_year_total = float(sum(counts.get(year, 0) for year in window))
    growth = None
    if two_years_ago is not None and two_years_ago > 0:
        growth = (previous_year - float(two_years_ago)) / float(two_years_ago)
    intensity = previous_year / max(three_year_total / 3.0, 1.0) if three_year_total > 0 else None
    return {
        "pub_count_prev_year": previous_year,
        "pub_count_3y": three_year_total,
        "pub_growth_prev_year": growth,
        "pub_intensity_vs_company": intensity,
        "pub_missing": 0.0,
    }


def attach_publication_features(store: Any, examples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Append the publication features to every example's feature mapping.

    Only persisted ``publication_counts`` are used; the function makes no
    network calls and never uses a partial or future year.
    """
    counts_by_company = load_counts(store)
    for example in examples:
        features = example.setdefault("features", {})
        features.update(publication_features(
            counts_by_company.get(example.get("company_key")), example.get("cutoff")))
    return examples


def publication_feature_coverage(examples: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Coverage summary for artifacts: how many examples actually have pub data."""
    rows = list(examples)
    matched = sum(1 for row in rows if (row.get("features") or {}).get("pub_missing") == 0.0)
    companies = {str(row.get("company_key")) for row in rows if row.get("company_key")}
    companies_with_data = {
        str(row.get("company_key")) for row in rows
        if (row.get("features") or {}).get("pub_missing") == 0.0}
    return {
        "examples": len(rows),
        "examples_with_publication_data": matched,
        "examples_without_publication_data": len(rows) - matched,
        "companies_in_examples": len(companies),
        "companies_with_publication_data": len(companies_with_data),
    }


def patent_features(publication_days: list[date] | None, cutoff: Any) -> dict[str, float | None]:
    """Point-in-time patent publication counts; knowledge time = publication date."""
    day = parse_date(cutoff)
    if day is None or not publication_days:
        return {name: None for name in PATENT_FEATURES} | {"pat_missing": 1.0}
    twelve_month = sum(1 for published in publication_days
                       if day - timedelta(days=365) < published <= day)
    three_year = sum(1 for published in publication_days
                     if day - timedelta(days=1095) < published <= day)
    return {
        "pat_apps_pub_12m": float(twelve_month),
        "pat_apps_pub_3y": float(three_year),
        "pat_missing": 0.0,
    }


def attach_patent_features(store: Any, examples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Append patent features from imported applications (no rows -> missing flag).

    When no patent data has been imported (the default in this environment, as
    the USPTO key is absent) every patent feature is ``None`` with
    ``pat_missing=1.0`` -- never a fabricated zero.
    """
    publications = load_publications(store)
    for example in examples:
        features = example.setdefault("features", {})
        features.update(patent_features(
            publications.get(example.get("company_key")), example.get("cutoff")))
    return examples


def patent_feature_coverage(examples: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(examples)
    matched = sum(1 for row in rows if (row.get("features") or {}).get("pat_missing") == 0.0)
    return {
        "examples": len(rows),
        "examples_with_patent_data": matched,
        "evaluated": False,
        "note": "No patent ablation is reported: USPTO ODP requires an API key and none was available.",
    }
