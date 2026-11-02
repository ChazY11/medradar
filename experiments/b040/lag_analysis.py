"""B-040 analysis: is there a measurable time relation between regulatory clearances and
device-trial activity for the same company and technology track?

Two genuinely independent monthly lanes, same (company, device track) cells:

  regulatory (L)  material 510(k)/PMA events, legal entity -> curated company family
  trials     (R)  ClinicalTrials.gov interventional device studies, first-posted date

Pre-declared in research/DECISIONS.md D-022 *before* this association was computed:
  * cells: >= MIN_REGULATORY_EVENTS regulatory events and >= MIN_TRIAL_EVENTS trial events
  * statistic: cross-correlation at lags -6..+12 (positive lag = regulatory leads trials)
  * inference: pool per-cell correlations by Fisher z with an entity-cluster bootstrap;
    null from circularly shifting each cell's trial series (keeps each series' own
    autocorrelation and volume, destroys alignment)
  * report power, and say so if the design cannot detect a plausible effect

Usage:
    python experiments/b040/lag_analysis.py
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.cycle2_coverage.panel import write_json  # noqa: E402
from experiments.detect_v1.streams import WINDOW_MONTHS, month_labels  # noqa: E402

# ---------------------------------------------------------------- pre-registered
MIN_REGULATORY_EVENTS = 6
MIN_TRIAL_EVENTS = 3
LAGS = tuple(range(-6, 13))
BOOTSTRAP = 2000
SHIFTS = 2000
SEED = 7


def load_companies(config_path: Path = Path("config/companies_device.json")) -> list[dict[str, Any]]:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    return payload.get("companies", [])


def company_entity_map(companies: list[dict[str, Any]],
                       universe_path: Path = Path("config/universe_v1.json")) -> dict[str, set[str]]:
    """company_key -> entity keys in its curated family (token containment, no fuzzy merge)."""
    from medradar.intelligence.universe import resolve_entities

    entities = json.loads(universe_path.read_text(encoding="utf-8"))["entities"]
    mapping: dict[str, set[str]] = {}
    for company in companies:
        key = str(company.get("key") or "")
        if not key:
            continue
        aliases = [company.get("name_en") or "", *(company.get("aliases") or [])]
        mapping[key] = set(resolve_entities(entities, aliases))
    return mapping


def regulatory_panel(cells: list[dict[str, Any]], entity_to_company: dict[str, str],
                     ) -> dict[tuple[str, str], list[int]]:
    panel: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0] * WINDOW_MONTHS)
    for cell in cells:
        company = entity_to_company.get(cell["entity"])
        if not company:
            continue
        series = panel[(company, cell["track"])]
        for month, value in enumerate(cell["series"]):
            series[month] += int(value)
    return dict(panel)


def trial_panel(db_path: Path) -> dict[tuple[str, str], list[int]]:
    labels = month_labels()
    index = {label: position for position, label in enumerate(labels)}
    panel: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0] * WINDOW_MONTHS)
    if not db_path.exists():
        return {}
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "select company_key, track_id, event_date from events where kind='trial' "
        "and company_key is not null and company_key<>'' "
        "and track_id is not null and track_id<>''").fetchall()
    con.close()
    for row in rows:
        month = str(row["event_date"])[:7]
        position = index.get(month)
        if position is None:
            continue
        panel[(row["company_key"], row["track_id"])][position] += 1
    return dict(panel)


def pearson(a: list[int], b: list[int]) -> float | None:
    n = len(a)
    mean_a = sum(a) / n
    mean_b = sum(b) / n
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
    var_a = sum((x - mean_a) ** 2 for x in a)
    var_b = sum((y - mean_b) ** 2 for y in b)
    if var_a <= 0 or var_b <= 0:
        return None
    return cov / math.sqrt(var_a * var_b)


def lagged(regulatory: list[int], trials: list[int], lag: int) -> float | None:
    """Correlation between regulatory_t and trial_{t+lag} (positive lag = regulatory leads)."""
    if lag >= 0:
        a = regulatory[:WINDOW_MONTHS - lag]
        b = trials[lag:]
    else:
        a = regulatory[-lag:]
        b = trials[:WINDOW_MONTHS + lag]
    if len(a) < 24:
        return None
    return pearson(a, b)


def fisher_mean(values: list[float]) -> float | None:
    valid = [value for value in values if value is not None and -1 < value < 1]
    if not valid:
        return None
    zs = [math.atanh(value) for value in valid]
    return math.tanh(sum(zs) / len(zs))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--streams", default="experiments/detect_v1/streams.json")
    parser.add_argument("--trials-db", default="data/b040_device_trials.sqlite")
    parser.add_argument("--out", default="experiments/b040/lag_analysis.json")
    args = parser.parse_args(argv)

    streams = json.loads(Path(args.streams).read_text(encoding="utf-8"))
    companies = load_companies()
    family = company_entity_map(companies)
    entity_to_company = {entity: company for company, entities in family.items()
                         for entity in entities}
    regulatory = regulatory_panel(streams["track_cells"], entity_to_company)
    trials = trial_panel(Path(args.trials_db))

    keys = sorted(set(regulatory) & set(trials))
    eligible = []
    for key in keys:
        reg_total = sum(regulatory[key])
        trial_total = sum(trials[key])
        if reg_total >= MIN_REGULATORY_EVENTS and trial_total >= MIN_TRIAL_EVENTS:
            eligible.append({"company": key[0], "track": key[1],
                             "regulatory_events": reg_total,
                             "trial_events": trial_total})
    print(f"cells in both lanes: {len(keys)}; eligible under the pre-registered floors: "
          f"{len(eligible)}")

    per_lag: dict[int, list[float]] = {lag: [] for lag in LAGS}
    for cell in eligible:
        key = (cell["company"], cell["track"])
        for lag in LAGS:
            value = lagged(regulatory[key], trials[key], lag)
            if value is not None:
                per_lag[lag].append(value)

    observed = {lag: fisher_mean(values) for lag, values in per_lag.items()}
    counts = {lag: len(values) for lag, values in per_lag.items()}

    # Null: circularly shift each cell's trial series independently, keeping each series'
    # own autocorrelation and volume, destroying cross-series alignment.
    rng = random.Random(SEED)
    null_profiles = []
    for _ in range(SHIFTS):
        shifted = {}
        for cell in eligible:
            key = (cell["company"], cell["track"])
            shift = rng.randrange(WINDOW_MONTHS)
            series = trials[key]
            shifted[key] = series[shift:] + series[:shift]
        profile = {}
        for lag in LAGS:
            values = []
            for cell in eligible:
                key = (cell["company"], cell["track"])
                value = lagged(regulatory[key], shifted[key], lag)
                if value is not None:
                    values.append(value)
            profile[lag] = fisher_mean(values)
        null_profiles.append(profile)

    summary = {}
    for lag in LAGS:
        values = [profile[lag] for profile in null_profiles if profile[lag] is not None]
        values.sort()
        if values:
            low = values[int(0.025 * len(values))]
            high = values[int(0.975 * len(values))]
            mean = sum(values) / len(values)
        else:
            low = high = mean = None
        summary[lag] = {"observed": observed[lag], "null_mean": mean,
                        "null_low": low, "null_high": high, "cells": counts[lag]}

    best_lag = max((lag for lag in LAGS if observed[lag] is not None),
                   key=lambda lag: observed[lag], default=None)
    # Power: with n cells and a hypothesized correlation r, what shift in the pooled
    # Fisher z could we detect? Report the standard error of the pooled estimate.
    n_cells = counts.get(0, 0)
    se_pooled = (1.0 / math.sqrt(max(n_cells - 3, 1))) if n_cells > 3 else None

    payload = {
        "design": {
            "decision": "research/DECISIONS.md D-022 (pre-declared before this run)",
            "min_regulatory_events": MIN_REGULATORY_EVENTS,
            "min_trial_events": MIN_TRIAL_EVENTS,
            "lags": list(LAGS),
            "lag_sign_convention": "positive lag = regulatory activity leads trial activity",
            "bootstrap": BOOTSTRAP, "null_shifts": SHIFTS, "seed": SEED,
            "trials_db": str(args.trials_db),
            "window_months": WINDOW_MONTHS,
        },
        "coverage": {
            "companies_in_watchlist": len(companies),
            "companies_with_entities": len(family),
            "cells_in_both_lanes": len(keys),
            "cells_eligible": len(eligible),
            "regulatory_events_eligible": sum(cell["regulatory_events"] for cell in eligible),
            "trial_events_eligible": sum(cell["trial_events"] for cell in eligible),
        },
        "eligible_cells": eligible,
        "lag_profile": summary,
        "best_lag": best_lag,
        "power": {
            "cells": n_cells,
            "standard_error_of_pooled_fisher_z_at_lag0": se_pooled,
            "note": ("with this many cells the pooled estimate is imprecise; the lag profile "
                     "is reported with its null interval rather than as a point finding"),
        },
    }
    write_json(Path(args.out), payload)

    print("\nlag  n   observed r   null 95% interval")
    for lag in LAGS:
        block = summary[lag]
        marker = " <-- best" if lag == best_lag else ""
        print(f"{lag:+3d} {block['cells']:3d}  {block['observed'] if block['observed'] is None else round(block['observed'], 3):>10}  "
              f"[{block['null_low']}, {block['null_high']}]{marker}")
    print(f"\nbest lag: {best_lag}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
