"""B-068: register a FROZEN prospective forecast set from the current snapshot.

The objective requires frozen forecasts, and the legacy registry's nowcasts are all blocked until 2027. This
script registers a forecast set that can be scored as soon as the lane advances:

  * every alert in the frozen policy-v2 snapshot becomes one forecast: probability that activity in the outcome
    window (four quarters after the two-quarter confirmation window) stays at or above the alert-time baseline;
  * the probabilities are the measured end-to-end pipeline rates (D-065), not guesses;
  * the set is written under research/forecasts/ with a content hash, so a later scoring run can prove the
    predictions were not edited after the outcome arrived.

Usage:
    python experiments/b068/register_forecasts.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from medradar.intelligence.forecasts import (  # noqa: E402
    FORECAST_SCHEMA,
    build_forecast,
    quarter_to_index,
    validate_forecast_set,
)
from medradar.intelligence.snapshot import content_hash  # noqa: E402

SNAPSHOT = Path("experiments/b027/snapshots/2026-11-03-policy-v2")
OUT = Path("research/forecasts/FORECAST_SET_2026-11-03.json")
AS_OF = "2026-11-03"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", default=str(SNAPSHOT))
    parser.add_argument("--out", default=str(OUT))
    parser.add_argument("--lane-through", default="",
                        help="latest available lane quarter; with it, only alerts whose outcome window is "
                             "entirely in the future are registered and backfilled ones are counted separately")
    args = parser.parse_args(argv)

    snapshot = Path(args.snapshot)
    payload = json.loads((snapshot / "profiles.json").read_text(encoding="utf-8"))
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))

    records = []
    backfilled = 0
    lane_through = quarter_to_index(args.lane_through) if args.lane_through else None
    for company, profile in sorted(payload["profiles"].items()):
        deployment = profile.get("momentum", {}).get("deployment_alerts") or {}
        for alert in deployment.get("flagged") or []:
            promotion = alert.get("promotion") or {}
            record = build_forecast(
                company=company,
                track=str(alert.get("track")),
                alert_quarter=str(alert.get("quarter")),
                promoted=promotion.get("verdict") == "promote_pending_signoff",
                policy_version=str(promotion.get("policy_version") or "unknown"),
                shape=str(promotion.get("shape") or "unknown"),
            )
            if lane_through is not None:
                maturity = quarter_to_index(record["windows"]["matures_when_data_through"])
                if maturity <= lane_through:
                    # the outcome is already observed, so this is a label, not a forecast (D-066)
                    backfilled += 1
                    continue
            records.append(record)

    forecast_set = {
        "schema": FORECAST_SCHEMA,
        "registered_at_utc": "2026-11-03T00:00:00+00:00",
        "as_of": AS_OF,
        "source_snapshot": str(snapshot).replace("\\", "/"),
        "source_manifest_hash": manifest.get("manifest_hash"),
        "probability_source": "end-to-end pipeline persistence rates measured in DECISIONS D-065",
        "maturation": "each forecast names its maturation quarter; scoring requires lane data through it",
        "lane_through_at_registration": args.lane_through or None,
        "backfilled_alerts_excluded": backfilled,
        "prospective_only": lane_through is not None,
        "forecasts": records,
    }
    problems = validate_forecast_set(forecast_set)
    if problems:
        print("forecast set invalid:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    forecast_set["forecast_set_hash"] = content_hash(
        {key: value for key, value in forecast_set.items() if key != "forecast_set_hash"})

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(forecast_set, indent=2, ensure_ascii=False) + "\n",
                              encoding="utf-8", newline="\n")
    promoted = sum(1 for record in records if record["decision"] == "promoted")
    print(f"registered {len(records)} forecasts ({promoted} promoted, {len(records) - promoted} not promoted)")
    print(f"source snapshot manifest {str(manifest.get('manifest_hash'))[:16]}...")
    print(f"forecast set hash {forecast_set['forecast_set_hash'][:16]}...")
    print(f"earliest maturation: {min(record['windows']['matures_when_data_through'] for record in records)}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
