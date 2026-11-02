"""B-068: score the frozen forecast set when data allow, and report what is still pending.

This script never edits the forecast set. It loads the frozen predictions, computes each forecast's outcome from
the lane as it stands, scores whatever has matured, and prints the pending count. When nothing has matured it says
so and exits 0 — a pending forecast is a correct state, not a failure.

Usage:
    python experiments/b068/maturate_forecasts.py [--set research/forecasts/FORECAST_SET_2026-11-03.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.b027.build_profiles import LANE, load_families  # noqa: E402
from experiments.cycle2_coverage.panel import write_json  # noqa: E402
from medradar.intelligence.forecasts import (  # noqa: E402
    BASELINE_QUARTERS,
    quarter_to_index,
    score,
)
from medradar.intelligence.snapshot import content_hash  # noqa: E402


def quarter_counts() -> tuple[dict[tuple[str, str], dict[int, int]], int]:
    """(company, track) -> quarter index -> event count, plus the latest quarter available."""
    from experiments.cycle2_coverage.panel import load_regulatory_events
    from experiments.detect_v1.streams import month_index
    from medradar.intelligence.universe import entity_key, normalise_applicant

    families = load_families()
    entity_to_company = {entity: key for key, family in families.items()
                         for entity in family["entities"]}
    cells: dict[tuple[str, str], dict[int, int]] = defaultdict(lambda: defaultdict(int))
    latest = 0
    for event in load_regulatory_events(LANE):
        normalised = normalise_applicant(event.get("applicant_raw"))
        track = event.get("track_id")
        index = month_index(event["day"])
        if not normalised or not track or index is None:
            continue
        company = entity_to_company.get(entity_key(normalised))
        if company is None:
            continue
        # month_index 0 is 2016-11, so the absolute quarter index needs the 2016 epoch added back;
        # the forecast windows are absolute labels ("2027-Q1"), which is why this must not stay relative
        years_since_window_start, month_of_year = divmod(index + 10, 12)
        quarter = (2016 + years_since_window_start) * 4 + month_of_year // 3
        cells[(company, track)][quarter] += 1
        latest = max(latest, quarter)
    return {key: dict(value) for key, value in cells.items()}, latest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", dest="set_path",
                        default="research/forecasts/FORECAST_SET_2026-11-03.json")
    parser.add_argument("--out", default="experiments/b068/maturation.json")
    args = parser.parse_args(argv)

    payload = json.loads(Path(args.set_path).read_text(encoding="utf-8"))
    recorded_hash = payload.pop("forecast_set_hash", None)
    actual_hash = content_hash(payload)
    if recorded_hash and recorded_hash != actual_hash:
        print(f"REFUSING to score: the forecast set was modified after registration "
              f"(recorded {recorded_hash[:16]}..., actual {actual_hash[:16]}...)")
        return 1
    payload["forecast_set_hash"] = recorded_hash

    cells, latest = quarter_counts()
    from medradar.intelligence.forecasts import index_to_quarter
    print(f"lane data through {index_to_quarter(latest)}")

    observed: dict[str, bool] = {}
    not_yet: list[str] = []
    for record in payload["forecasts"]:
        company, track, alert_quarter = record["id"].split("|")
        windows = record["windows"]
        maturity = quarter_to_index(windows["matures_when_data_through"])
        if latest < maturity:
            not_yet.append(record["id"])
            continue
        counts = cells.get((company, track), {})
        origin = quarter_to_index(alert_quarter)
        history = [counts.get(quarter, 0)
                   for quarter in range(origin - BASELINE_QUARTERS, origin)]
        baseline = sum(history) / len(history) if history else 0.0
        first = quarter_to_index(windows["outcome"].split("..")[0])
        last = quarter_to_index(windows["outcome"].split("..")[1])
        window = [counts.get(quarter, 0) for quarter in range(first, last + 1)]
        if baseline <= 0 or not window:
            not_yet.append(record["id"])
            continue
        observed[record["id"]] = (sum(window) / len(window)) >= baseline

    result = score(payload["forecasts"], observed)
    payload_out: dict[str, Any] = {
        "forecast_set": str(Path(args.set_path)).replace("\\", "/"),
        "forecast_set_hash": recorded_hash,
        "lane_data_through": index_to_quarter(latest),
        "scoring": result,
        "pending_ids": sorted(not_yet),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    write_json(Path(args.out), payload_out)

    print(f"resolved {result['resolved']} of {len(payload['forecasts'])}; pending {result['pending']}")
    if result["resolved"]:
        print(f"brier={result['brier']:.4f} log_loss={result['log_loss']:.4f} "
              f"accuracy={result['accuracy']:.3f}")
        for decision, block in result["by_decision"].items():
            print(f"  {decision}: n={block['n']} mean_p={block['mean_probability']:.3f} "
                  f"mean_outcome={block['mean_outcome']:.3f}")
    else:
        earliest = min(record["windows"]["matures_when_data_through"]
                       for record in payload["forecasts"])
        print(f"nothing matured yet; earliest maturation {earliest} — a pending forecast is the correct "
              f"state, not a failure")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
