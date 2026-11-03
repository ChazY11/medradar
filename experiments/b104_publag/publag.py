"""B-104: publication knowledge-lag sensitivity of the hist_v1 fusion comparison (backlog B-041).

Frozen design: research/protocols/b104_publag_preregistration.md

For L in {0, 14, 30, 90} days, a publication year y is usable at quarter t iff
date(y+1, 1, 1) + L days <= last day of quarter t.  The three publication features use the most
recent usable year y*.  Everything else in the hist_v1 C-vs-D comparison is unchanged.  The script
imports the frozen hist_v1 evaluator (no code duplication of the model/metrics) and only replaces the
publication-lag rule.

Output: experiments/b104_publag/publag.json
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import experiments.hist_v1.eval as E  # noqa: E402

PANEL = ROOT / "out" / "hist_v1" / "panel.json"
DATA = ROOT / "data"
OUT = ROOT / "experiments" / "b104_publag" / "publag.json"
LAGS = (0, 14, 30, 90)


def quarter_end(year: int, quarter: int) -> date:
    last_month = quarter * 3
    if last_month == 12:
        return date(year, 12, 31)
    return date(year, last_month + 1, 1) - timedelta(days=1)


def usable_years(year: int, quarter: int, lag_days: int) -> list[int]:
    end = quarter_end(year, quarter)
    usable = []
    for candidate in range(year - 4, year + 1):
        knowledge = date(candidate + 1, 1, 1) + timedelta(days=lag_days)
        if knowledge <= end:
            usable.append(candidate)
    return usable


def publication_features(works: dict[int, int], y_star: int | None) -> tuple:
    """(pub_prev_year, pub_3y, pub_growth) from the most recent usable year, or (None, None, None)."""
    if y_star is None:
        return (None, None, None)
    previous = works.get(y_star)
    three = [works.get(y_star - k) for k in (0, 1, 2)]
    prev_value = E._log1p(previous) if previous is not None else None
    three_value = E._log1p(sum(three)) if all(value is not None for value in three) else None
    growth = (previous / (works[y_star - 1] + 0.5)) if (
        previous is not None and works.get(y_star - 1) is not None) else None
    return (prev_value, three_value, growth)


class LaggedFusionLanes(E.FusionLanes):
    """FusionLanes with the publication knowledge lag as a parameter."""

    def __init__(self, data_root: Path, panel: E.Panel, lag_days: int):
        super().__init__(data_root, panel)
        self.lag_days = lag_days

    def most_recent_usable_year(self, company: str, t: int) -> int | None:
        """The publication year the frozen hist_v1 definition uses: ``year(t)-1``, and only if usable.

        The lag rule can make ``year-1`` unusable at a first-quarter origin (90-day lag in a non-leap year);
        in that case the publication features are missing rather than forward-filled to an older year, so the
        lag-0/14/30 runs reproduce the hist_v1 definition exactly.
        """
        panel = self.panel
        candidate = panel.quarter_year[t] - 1
        if candidate not in usable_years(panel.quarter_year[t], panel.quarter_number[t], self.lag_days):
            return None
        works = self.publications.get(company, {})
        return candidate if works.get(candidate) is not None else None

    def values(self, company: str, track: str, t: int) -> tuple:
        panel = self.panel
        # ---- trial features: identical to the frozen evaluator ----
        track_values = self.trial_track_q.get(track, [])
        low = t - 8
        track_count = (E.bisect.bisect_right(track_values, t) - E.bisect.bisect_right(track_values, low))
        category = panel.track_category[track]
        category_values = self.trial_category_q.get(category, [])
        category_count = (E.bisect.bisect_right(category_values, t) - E.bisect.bisect_right(category_values, low))
        adjacent = category_count - track_count
        # ---- publication features with the lag rule ----
        works = self.publications.get(company, {})
        y_star = self.most_recent_usable_year(company, t)
        return (
            E._log1p(track_count),
            E._log1p(adjacent),
            *publication_features(works, y_star),
        )


def run_lag(panel: E.Panel, lag_days: int) -> dict:
    lanes = LaggedFusionLanes(DATA, panel, lag_days)
    if not lanes.available:
        return {"lag_days": lag_days, "status": "NOT_EVALUABLE", "reason": lanes.reason}
    data = E.RiskHorizonData(panel, True, 8, lanes)
    fusion_start = panel.qidx.get("2016-Q1")
    origins = [origin for origin in data.test_origins if fusion_start is not None and origin >= fusion_start]
    coverage = lanes.coverage(data, origins)
    config = E.run_config(data, {"C": set(origins), "D": set(origins)})
    per_origin = []
    for row in config["per_origin"]:
        models = row["models"]
        if "M1C" not in models or "M1D" not in models:
            continue                      # origin outside the fusion origin set: baselines only
        c = models["M1C"]["average_precision"]
        d = models["M1D"]["average_precision"]
        per_origin.append({"origin": panel.quarters[row["origin"]], "ap_c": c, "ap_d": d,
                           "delta": (d - c) if (c is not None and d is not None) else None})
    deltas = [row["delta"] for row in per_origin if row["delta"] is not None]
    mean_c = sum(row["ap_c"] for row in per_origin if row["ap_c"] is not None) / len(deltas)
    mean_d = sum(row["ap_d"] for row in per_origin if row["ap_d"] is not None) / len(deltas)
    return {
        "lag_days": lag_days,
        "status": "EVALUATED",
        "publication_join_rate": coverage["publication_join_rate"],
        "trial_track_present_rate": coverage["trial_track_present_rate"],
        "n_origins": len(origins),
        "mean_ap_c": mean_c,
        "mean_ap_d": mean_d,
        "delta_ap_d_minus_c": mean_d - mean_c,
        "origins_with_positive_delta": sum(1 for value in deltas if value > 0),
        "per_origin": per_origin,
    }


def main() -> int:
    panel = E.load_panel(PANEL)
    rows = [run_lag(panel, lag) for lag in LAGS]
    evaluated = [row for row in rows if row["status"] == "EVALUATED"]
    positive = [row for row in evaluated if row["delta_ap_d_minus_c"] > 0]
    if positive:
        verdict = {
            "conclusion": "lag-dependent, not robust",
            "reason": ("at least one knowledge lag makes the fusion feature set D rank better than C; the hist_v1 "
                       "fusion conclusion is marked sensitive to the publication knowledge lag"),
            "lags_with_positive_delta": [row["lag_days"] for row in positive],
        }
    else:
        verdict = {
            "conclusion": "unchanged",
            "reason": "fusion (D) does not rank better than C at any of the four knowledge lags",
            "largest_delta": max((row["delta_ap_d_minus_c"] for row in evaluated), default=None),
        }
    payload = {
        "schema": "b104.publag.v1",
        "protocol": "research/protocols/b104_publag_preregistration.md",
        "panel_sha256": panel.sha256,
        "seed_note": "no new sampling: the frozen hist_v1 evaluator is reused (seed 20261103 inside it)",
        "lags_days": list(LAGS),
        "results": rows,
        "verdict": verdict,
        "not_claimed": [
            "any upgrade of the hist_v1 fusion conclusion to a positive result",
            "that publication counts are the only possible scientific signal",
            "any causal reading",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for row in rows:
        if row["status"] == "EVALUATED":
            print(f"lag {row['lag_days']:3d}d: join {row['publication_join_rate']:.3f} "
                  f"AP(C) {row['mean_ap_c']:.4f} AP(D) {row['mean_ap_d']:.4f} "
                  f"delta {row['delta_ap_d_minus_c']:+.4f} positive-origins {row['origins_with_positive_delta']}"
                  f"/{len(row['per_origin'])}")
        else:
            print(f"lag {row['lag_days']:3d}d: {row['status']} {row.get('reason')}")
    print("verdict:", verdict["conclusion"])
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
