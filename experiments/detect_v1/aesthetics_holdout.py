"""B-046: pre-registered split-sample test of the `aesthetics` entry-clustering candidate.

Pre-registration: research/DECISIONS.md D-026, written before this script was first run.

  hypothesis  first entries into `aesthetics` by already-observable filers are temporally
              clustered beyond the risk-weighted null
  statistic   dispersion index (variance/mean) of monthly first-entry counts
  null        entries distributed over months with probability proportional to the at-risk count
  split       estimation 2016-09..2022-12 (first 76 months); holdout 2023-01..2026-09
  decision    REPLICATED iff holdout p <= 0.05 and estimation p <= 0.20 (same direction)
              REJECTED iff holdout p > 0.05
              NOT RESOLVABLE only if power < 50% at the effect implied by the estimation window
  power       simulate waves concentrating 30/50/70% of holdout entries in a random 6-month block

Usage:
    python experiments/detect_v1/aesthetics_holdout.py
"""
from __future__ import annotations

import argparse
import math
import random
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.cycle2_coverage.panel import write_json  # noqa: E402
from experiments.detect_v1.entries import (  # noqa: E402
    PERMUTATIONS,
    SEED,
    at_risk_and_entries,
    dispersion,
)
from experiments.detect_v1.streams import month_labels  # noqa: E402
from experiments.detect_v1.widths import resolve_events  # noqa: E402

TRACK = "aesthetics"
SPLIT_LABEL = "2022-12"
ALPHA = 0.05
ESTIMATION_P_CEILING = 0.20
WAVE_BLOCK_MONTHS = 6
WAVE_SHARES = (0.3, 0.5, 0.7)
POWER_SIMS = 1000


def percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return float("nan")
    index = min(len(sorted_values) - 1, max(0, int(q * len(sorted_values))))
    return sorted_values[index]


def windowed_dispersion(entries: list[int], risk: list[int], lo: int, hi: int,
                        rng: random.Random, permutations: int) -> dict[str, Any]:
    """Dispersion test restricted to [lo, hi), with the risk profile sliced identically."""
    sub_risk = [max(value, 0) for value in risk[lo:hi]]
    sub_entries = [month - lo for month in entries if lo <= month < hi]
    counts = [0] * (hi - lo)
    for month in sub_entries:
        counts[month] += 1
    observed = dispersion(counts)
    total_weight = sum(sub_risk)
    if observed is None or len(sub_entries) < 3 or total_weight <= 0:
        return {"entries": len(sub_entries), "status": "insufficient",
                "observed_dispersion": observed}
    draws = []
    for _ in range(permutations):
        simulated = [0] * (hi - lo)
        for _ in range(len(sub_entries)):
            value = rng.random() * total_weight
            accumulated = 0.0
            for month, weight in enumerate(sub_risk):
                accumulated += weight
                if accumulated >= value:
                    simulated[month] += 1
                    break
            else:
                simulated[-1] += 1
        measured = dispersion(simulated)
        if measured is not None:
            draws.append(measured)
    draws.sort()
    exceed = sum(1 for value in draws if value >= observed)
    return {
        "window": [lo, hi],
        "months": hi - lo,
        "entries": len(sub_entries),
        "observed_dispersion": observed,
        "null_mean_dispersion": sum(draws) / len(draws),
        "null_p95": percentile(draws, 0.95),
        "pvalue_one_sided": (exceed + 1) / (len(draws) + 1),
        "permutations": len(draws),
    }


def power_at_wave_share(entries_count: int, risk: list[int], null_p95: float, share: float,
                        rng: random.Random, sims: int) -> dict[str, Any]:
    """Probability of rejecting the null when ``share`` of entries lies in one 6-month block."""
    months = len(risk)
    if entries_count < 3 or sum(risk) <= 0:
        return {"share": share, "status": "insufficient"}
    total_weight = sum(risk)
    threshold = null_p95
    hits = 0
    for _ in range(sims):
        block_start = rng.randrange(0, max(1, months - WAVE_BLOCK_MONTHS + 1))
        block = set(range(block_start, min(months, block_start + WAVE_BLOCK_MONTHS)))
        wave_count = max(1, int(round(share * entries_count)))
        plain_count = entries_count - wave_count
        counts = [0] * months
        for _ in range(wave_count):
            counts[rng.choice(sorted(block))] += 1
        for _ in range(plain_count):
            value = rng.random() * total_weight
            accumulated = 0.0
            for month, weight in enumerate(risk):
                accumulated += weight
                if accumulated >= value:
                    counts[month] += 1
                    break
            else:
                counts[-1] += 1
        measured = dispersion(counts)
        if measured is not None and measured >= threshold:
            hits += 1
    return {"share": share, "sims": sims, "detection_probability": hits / sims,
            "threshold_dispersion": threshold}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/research.sqlite")
    parser.add_argument("--out", default="experiments/detect_v1/aesthetics_holdout.json")
    args = parser.parse_args(argv)

    labels = month_labels()
    split_index = labels.index(SPLIT_LABEL) + 1          # holdout starts the next month
    resolved = resolve_events(Path(args.db))
    bundle = at_risk_and_entries(resolved, require_prior_filer=True)
    print(f"prior-filer entries: {len(bundle['entries'])}  "
          f"(excluded new-entity appearances: {bundle['new_entity_entries_excluded']})")
    print(f"split: estimation [0,{split_index}) = {labels[0]}..{labels[split_index - 1]}  "
          f"holdout [{split_index},{len(labels)}) = {labels[split_index]}..{labels[-1]}")

    entries = [row["month"] for row in bundle["entries"] if row["track"] == TRACK]
    risk = bundle["risk_track"].get(TRACK, [0] * len(labels))
    print(f"{TRACK}: {len(entries)} entries, risk set mean {sum(risk)/len(risk):.1f}"
          f"  ({sum(1 for m in entries if m < split_index)} early, "
          f"{sum(1 for m in entries if m >= split_index)} late)")

    rng = random.Random(SEED)
    estimation = windowed_dispersion(entries, risk, 0, split_index, rng, PERMUTATIONS)
    holdout = windowed_dispersion(entries, risk, split_index, len(labels), rng, PERMUTATIONS)
    full = windowed_dispersion(entries, risk, 0, len(labels), rng, PERMUTATIONS)

    power = []
    if "pvalue_one_sided" in holdout:
        holdout_rng = random.Random(SEED + 11)
        for share in WAVE_SHARES:
            power.append(power_at_wave_share(holdout["entries"], risk[split_index:],
                                             holdout["null_p95"], share, holdout_rng, POWER_SIMS))

    # ------------------------------------------------------------------ clean design
    # The candidate `aesthetics` was nominated in cycle 7 using the FULL window, which includes
    # the holdout months. Its split-sample result above is therefore NOT confirmatory: the
    # holdout was already used to pick the track. The clean design below nominates tracks using
    # the estimation window ONLY (all tracks, BH-corrected) and then tests the nominee(s) out of
    # sample. This is the only design here whose holdout p-value is a valid confirmatory test.
    from experiments.detect_v1.entries import benjamini_hochberg

    by_track: dict[str, list[int]] = {}
    for row in bundle["entries"]:
        by_track.setdefault(row["track"], []).append(row["month"])
    nomination_rng = random.Random(SEED + 23)
    early_tests = []
    for track, months in sorted(by_track.items()):
        result = windowed_dispersion(months, bundle["risk_track"].get(track, [0] * len(labels)),
                                     0, split_index, nomination_rng, PERMUTATIONS)
        if "pvalue_one_sided" in result:
            early_tests.append((track, result["pvalue_one_sided"], result))
    nomination_fdr = benjamini_hochberg([(track, pvalue) for track, pvalue, _ in early_tests])
    nominated = list(nomination_fdr["rejected_keys"])
    confirmations = {}
    for track in nominated:
        months = by_track[track]
        holdout_result = windowed_dispersion(
            months, bundle["risk_track"].get(track, [0] * len(labels)),
            split_index, len(labels), random.Random(SEED + 31), PERMUTATIONS)
        early = next(result for name, _, result in early_tests if name == track)
        confirms = ("pvalue_one_sided" in holdout_result
                    and holdout_result["pvalue_one_sided"] <= ALPHA)
        confirmations[track] = {
            "estimation": early, "holdout": holdout_result,
            "confirms": bool(confirms),
        }
    clean = {
        "design": ("nominate tracks on the estimation window only (BH q=0.10), then test the "
                   "nominee(s) on the untouched holdout window at alpha=0.05"),
        "tracks_tested_in_estimation": len(early_tests),
        "fdr": nomination_fdr,
        "nominated": nominated,
        "confirmations": confirmations,
        "outcome": ("NO TRACK NOMINATED: nothing can be confirmed under a clean design"
                    if not nominated else
                    ("CONFIRMED: " + ", ".join(track for track, block in confirmations.items()
                                               if block["confirms"]))
                    if any(block["confirms"] for block in confirmations.values()) else
                    "NOMINATED BUT NOT CONFIRMED on the holdout"),
    }

    verdict = "UNKNOWN"
    if "pvalue_one_sided" in holdout:
        replicated = (holdout["pvalue_one_sided"] <= ALPHA
                      and estimation.get("pvalue_one_sided", 1.0) <= ESTIMATION_P_CEILING)
        max_power = max((row.get("detection_probability") or 0.0) for row in power) if power else 0.0
        if replicated:
            verdict = "REPLICATED"
        elif max_power < 0.5:
            verdict = "NOT RESOLVABLE (power < 50% at 70% wave concentration)"
        else:
            verdict = "REJECTED"

    payload = {
        "design": {
            "decision": "research/DECISIONS.md D-026 (written before this run)",
            "track": TRACK,
            "statistic": "dispersion index of monthly first-entry counts",
            "null": "entries allocated proportional to the at-risk count per month",
            "split_label": SPLIT_LABEL,
            "estimation_window": [labels[0], labels[split_index - 1]],
            "holdout_window": [labels[split_index], labels[-1]],
            "alpha": ALPHA,
            "estimation_p_ceiling": ESTIMATION_P_CEILING,
            "wave_block_months": WAVE_BLOCK_MONTHS,
            "wave_shares": list(WAVE_SHARES),
            "power_sims": POWER_SIMS,
            "seed": SEED,
            "prior_filer_control": True,
            "note": ("entries restricted to entities already observable in another track, per "
                     "D-025; this is the specification in which the candidate was selected"),
        },
        "counts": {"entries_total": len(entries),
                   "entries_estimation": estimation.get("entries"),
                   "entries_holdout": holdout.get("entries"),
                   "risk_mean": sum(risk) / len(risk)},
        "full_window": full,
        "estimation_window": estimation,
        "holdout_window": holdout,
        "power": power,
        "clean_nomination_design": clean,
        "verdict": verdict,
    }
    write_json(Path(args.out), payload)

    print("\n== full window ==")
    print(" ", {key: full.get(key) for key in
                 ("entries", "observed_dispersion", "null_mean_dispersion", "pvalue_one_sided")})
    print("== estimation window ==")
    print(" ", {key: estimation.get(key) for key in
                 ("entries", "observed_dispersion", "null_p95", "pvalue_one_sided")})
    print("== holdout window ==")
    print(" ", {key: holdout.get(key) for key in
                 ("entries", "observed_dispersion", "null_p95", "pvalue_one_sided")})
    print("== power (holdout) ==")
    for row in power:
        print(" ", row)
    print("\n== clean nomination design (the confirmatory one) ==")
    print("  tracks tested:", clean["tracks_tested_in_estimation"],
          "nominated:", clean["nominated"], "->", clean["outcome"])
    for track, block in clean["confirmations"].items():
        early_p = block["estimation"].get("pvalue_one_sided")
        holdout_p = block["holdout"].get("pvalue_one_sided")
        print(f"    {track}: early p={early_p} holdout p={holdout_p} "
              f"confirms={block['confirms']}")
    print(f"\nVERDICT (post-hoc candidate, NOT confirmatory): {verdict}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

