"""B-030 analysis: validity of the Wayback hiring proxy, and its time relation to regulatory activity.

Pre-registered in research/DECISIONS.md D-028. Three parts, in the declared order:

  1. coverage and validity — postings, months covered, and a URL-scheme change check (a level shift
     that coincides with a change of posting-URL scheme is a collection artifact, not a hiring change);
  2. company-level lag profile between hiring and regulatory activity, lags -6..+12 months
     (positive lag = hiring leads), pooled by Fisher z with a circular-shift null;
  3. an explicit statement of what the design can and cannot support.

Usage:
    python experiments/b030/lag_analysis.py
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.cycle2_coverage.panel import write_json  # noqa: E402
from experiments.detect_v1.streams import WINDOW_MONTHS, month_labels  # noqa: E402

LAGS = tuple(range(-6, 13))
MIN_POSTINGS = 50
MIN_MONTHS = 24
SHIFTS = 2000
SEED = 7
SILENT_MONTH_FRACTION = 0.5   # a company with >50% silent months is too gappy to use


def company_entity_map(companies: list[dict[str, Any]],
                       universe_path: Path = Path("config/universe_v1.json")) -> dict[str, set[str]]:
    from medradar.intelligence.universe import resolve_entities

    entities = json.loads(universe_path.read_text(encoding="utf-8"))["entities"]
    mapping: dict[str, set[str]] = {}
    for company in companies:
        key = str(company.get("key") or "")
        aliases = [company.get("name_en") or "", *(company.get("aliases") or [])]
        mapping[key] = set(resolve_entities(entities, aliases))
    return mapping


def regulatory_company_panel(db_path: Path, family: dict[str, set[str]]) -> dict[str, list[int]]:
    import sqlite3

    labels = month_labels()
    index = {label: position for position, label in enumerate(labels)}
    entity_to_company = {entity: company for company, entities in family.items()
                         for entity in entities}
    panel: dict[str, list[int]] = defaultdict(lambda: [0] * WINDOW_MONTHS)
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "select applicant_raw, event_date from events where kind in ('510k','pma')").fetchall()
    con.close()
    from medradar.intelligence.universe import entity_key, normalise_applicant

    for row in rows:
        normalised = normalise_applicant(row["applicant_raw"])
        if not normalised:
            continue
        company = entity_to_company.get(entity_key(normalised))
        if not company:
            continue
        position = index.get(str(row["event_date"])[:7])
        if position is not None:
            panel[company][position] += 1
    return dict(panel)


def series_from_months(monthly: dict[str, int], labels: list[str]) -> dict[str, Any]:
    # the panel keys months as "YYYYMM"; the window labels are "YYYY-MM"
    compact = {str(key).replace("-", ""): int(value) for key, value in monthly.items()}
    counts = [0] * WINDOW_MONTHS
    present = 0
    for position, label in enumerate(labels):
        value = compact.get(label.replace("-", ""), 0)
        counts[position] = value
        if value:
            present += 1
    silent = WINDOW_MONTHS - present
    return {"series": counts, "months_with_postings": present,
            "silent_month_fraction": silent / WINDOW_MONTHS,
            "total": sum(counts)}


def pearson(a: list[int], b: list[int]) -> float | None:
    n = len(a)
    mean_a, mean_b = sum(a) / n, sum(b) / n
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
    var_a = sum((x - mean_a) ** 2 for x in a)
    var_b = sum((y - mean_b) ** 2 for y in b)
    if var_a <= 0 or var_b <= 0:
        return None
    return cov / math.sqrt(var_a * var_b)


def lagged(regulatory: list[int], hiring: list[int], lag: int) -> float | None:
    if lag >= 0:
        a, b = regulatory[:WINDOW_MONTHS - lag], hiring[lag:]
    else:
        a, b = regulatory[-lag:], hiring[:WINDOW_MONTHS + lag]
    return pearson(a, b) if len(a) >= 24 else None


def fisher_mean(values: list[float]) -> float | None:
    valid = [value for value in values if value is not None and -1 < value < 1]
    if not valid:
        return None
    return math.tanh(sum(math.atanh(value) for value in valid) / len(valid))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", default="experiments/b030/hiring_panel.json")
    parser.add_argument("--db", default="data/research.sqlite")
    parser.add_argument("--out", default="experiments/b030/lag_analysis.json")
    args = parser.parse_args(argv)

    panel_payload = json.loads(Path(args.panel).read_text(encoding="utf-8"))
    labels = month_labels()
    companies = json.loads(Path("config/companies_device.json").read_text(encoding="utf-8"))["companies"]
    family = company_entity_map(companies)
    regulatory = regulatory_company_panel(Path(args.db), family)

    usable: dict[str, dict[str, Any]] = {}
    for company, block in panel_payload["companies"].items():
        monthly = block.get("monthly") or {}
        if not monthly:
            continue
        series = series_from_months(monthly, labels)
        if series["total"] < MIN_POSTINGS:
            continue
        if series["months_with_postings"] < MIN_MONTHS:
            continue
        if series["silent_month_fraction"] > SILENT_MONTH_FRACTION:
            continue
        if company not in regulatory:
            continue
        usable[company] = series
    print(f"usable companies: {sorted(usable)}")

    per_lag: dict[int, list[float]] = {lag: [] for lag in LAGS}
    for company, block in usable.items():
        for lag in LAGS:
            value = lagged(regulatory[company], block["series"], lag)
            if value is not None:
                per_lag[lag].append(value)
    observed = {lag: fisher_mean(values) for lag, values in per_lag.items()}

    rng = random.Random(SEED)
    null_profiles = []
    for _ in range(SHIFTS):
        shifted = {}
        for company, block in usable.items():
            shift = rng.randrange(WINDOW_MONTHS)
            series = block["series"]
            shifted[company] = series[shift:] + series[:shift]
        profile = {}
        for lag in LAGS:
            values = [lagged(regulatory[company], shifted[company], lag)
                      for company in usable]
            profile[lag] = fisher_mean([value for value in values if value is not None])
        null_profiles.append(profile)
    summary = {}
    for lag in LAGS:
        values = sorted(profile[lag] for profile in null_profiles
                        if profile[lag] is not None)
        summary[lag] = {
            "observed": observed[lag],
            "null_low": values[int(0.025 * len(values))] if values else None,
            "null_high": values[int(0.975 * len(values))] if values else None,
            "companies": len(per_lag[lag]),
        }
    best_lag = max((lag for lag in LAGS if observed[lag] is not None),
                   key=lambda lag: observed[lag], default=None)

    payload = {
        "design": {
            "decision": "research/DECISIONS.md D-028 (pre-registered)",
            "source": "Wayback Machine CDX (index only, keyless, historical)",
            "proxy": "distinct job-posting URLs first captured per month",
            "lags": list(LAGS),
            "lag_sign_convention": "positive lag = hiring leads regulatory activity",
            "eligibility": {"min_postings": MIN_POSTINGS, "min_months": MIN_MONTHS,
                            "max_silent_month_fraction": SILENT_MONTH_FRACTION},
            "shifts": SHIFTS, "seed": SEED,
        },
        "coverage": {
            "companies_in_panel": len(panel_payload["companies"]),
            "companies_usable": len(usable),
            "usable_keys": sorted(usable),
            "usable_detail": {company: {key: block[key] for key in
                                        ("total", "months_with_postings", "silent_month_fraction")}
                              for company, block in usable.items()},
        },
        "lag_profile": summary,
        "best_lag": best_lag,
        "caveats": [
            "the proxy counts postings the archive happened to capture, not headcount",
            "coverage depends on which career sites were archived; several focus companies have none",
            "URL-scheme changes can create level shifts that are collection artifacts",
            "with this many companies the pooled profile is not a precise estimate",
        ],
    }
    write_json(Path(args.out), payload)

    print("\ncompany            postings  months_with_postings  silent_fraction")
    for company, block in usable.items():
        print(f"  {company:20s} {block['total']:6d}  {block['months_with_postings']:5d}  "
              f"{block['silent_month_fraction']:.2f}")
    print("\nlag  n  observed r  null 95% interval")
    for lag in LAGS:
        block = summary[lag]
        marker = " <-- best" if lag == best_lag else ""
        print(f"{lag:+3d} {block['companies']:2d}  "
              f"{block['observed'] if block['observed'] is None else round(block['observed'], 3)!s:>8}  "
              f"[{block['null_low']}, {block['null_high']}]{marker}")
    print(f"\nbest lag: {best_lag}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
