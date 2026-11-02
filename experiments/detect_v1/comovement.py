"""Cross-company co-movement in technology activity (B-025).

The mission's Observe layer asks a question the single-cell detector cannot answer:
**are several competitors becoming active in the same technology track at the same time?**
A single firm accelerating is one thing; three independent firms accelerating in the same
track within a few months is a different, stronger claim about the industry.

Design
------
Presence panel: for every (entity, track) pair in the lane, a binary series over the 119
complete months — 1 if the entity filed at least one material event in that track-month.

Statistic: T = sum over months of C(O_m, 2), the number of co-active firm pairs, where O_m
is the number of firms active in that track-month. This counts how often firms *overlap*.

Null model: each firm is modelled independently, keeping its own number of active months
(so firm size/activity is preserved) but drawing those months with probability proportional
to the **lane-wide monthly volume** (so industry-wide volume swings and seasonality are
absorbed). Drawing each firm's active months from this weighted distribution and recomputing
T gives the distribution of co-movement expected from firm activity levels plus lane volume
alone. Co-movement beyond that is what we test for.

Why this null is the right one: it preserves (a) each firm's activity level, (b) the
industry's monthly volume profile. It therefore cannot be satisfied by "everyone filed more
that month" — which is exactly the confound that would make naive co-movement meaningless.

A detection of no excess co-movement is a perfectly good result: it would say that in this
lane, technology activity is essentially firm-specific, and "the whole industry moved" is not
a phenomenon the data supports.

Usage:
    python experiments/detect_v1/comovement.py --db data/research.sqlite
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.cycle2_coverage.panel import write_json  # noqa: E402
from experiments.detect_v1.widths import resolve_events  # noqa: E402
from experiments.detect_v1.streams import WINDOW_MONTHS  # noqa: E402

#: Pre-declared eligibility for the co-movement analysis.
MIN_ACTIVE_MONTHS_PER_ENTITY = 6
MIN_ENTITIES_PER_TRACK = 3
PERMUTATIONS = 1000
SEED = 7
BH_Q = 0.10


def build_presence(resolved: list[dict[str, Any]]) -> dict[str, dict[str, list[int]]]:
    """track -> entity -> binary presence series over the window."""
    presence: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0] * WINDOW_MONTHS))
    for row in resolved:
        month = row["month"]
        if 0 <= month < WINDOW_MONTHS:
            presence[row["track"]][row["entity"]][month] = 1
    return {track: dict(entities) for track, entities in presence.items()}


def lane_volume(resolved: list[dict[str, Any]]) -> list[int]:
    volume = [0] * WINDOW_MONTHS
    for row in resolved:
        if 0 <= row["month"] < WINDOW_MONTHS:
            volume[row["month"]] += 1
    return volume


def coactivity(series_list: list[list[int]]) -> int:
    """Sum over months of C(active firms, 2)."""
    total = 0
    for month in range(len(series_list[0])):
        active = sum(1 for series in series_list if series[month])
        total += active * (active - 1) // 2
    return total


def weighted_months(weights: list[float], count: int, rng: random.Random) -> set[int]:
    """Draw ``count`` distinct months with probability proportional to ``weights``.

    Uses a cumulative table plus rejection on duplicates, which is O(count log n) and
    keeps the permutation loop affordable (the naive re-normalising sampler is O(n) per
    draw and made the sweep take minutes).
    """
    if count <= 0:
        return set()
    total = sum(weights)
    if total <= 0:
        return set(range(min(count, len(weights))))
    cumulative = []
    running = 0.0
    for weight in weights:
        running += weight
        cumulative.append(running)
    chosen: set[int] = set()
    guard = 0
    while len(chosen) < min(count, len(weights)):
        draw = rng.random() * cumulative[-1]
        index = bisect.bisect_left(cumulative, draw)
        if index >= len(weights):
            index = len(weights) - 1
        if index not in chosen:
            chosen.add(index)
        guard += 1
        if guard > 10000:
            break
    return chosen


def analyse_track(entities: dict[str, list[int]], weights_source: list[int], *,
                  permutations: int = PERMUTATIONS, seed: int = SEED) -> dict[str, Any]:
    names = sorted(entities)
    series_list = [entities[name] for name in names]
    active_counts = [sum(series) for series in series_list]
    observed = coactivity(series_list)

    weights = [max(value, 1) for value in weights_source]
    rng = random.Random(seed + hash_track(names))
    null_values = []
    for _ in range(permutations):
        simulated = []
        for count in active_counts:
            months = weighted_months(weights, count, rng)
            simulated.append([1 if month in months else 0 for month in range(WINDOW_MONTHS)])
        null_values.append(coactivity(simulated))
    null_values.sort()
    mean = sum(null_values) / len(null_values)
    variance = sum((value - mean) ** 2 for value in null_values) / len(null_values)
    sd = math.sqrt(variance) if variance > 0 else 0.0
    exceed = sum(1 for value in null_values if value >= observed)
    pvalue = (exceed + 1) / (len(null_values) + 1)
    zscore = (observed - mean) / sd if sd > 0 else 0.0

    # Per-pair synchrony. Under the volume-weighted null, P(firm i active in month m) is
    # approximately r_i * w_m / sum(w), so the expected overlap of a pair is
    # r_i * r_j * sum(w^2) / sum(w)^2. Using this (rather than r_i r_j / M) means that a
    # lane-wide volume spike that makes everyone file does not masquerade as synchrony.
    weight_sq_ratio = (sum(weight * weight for weight in weights) / (sum(weights) ** 2))
    pairs = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            overlap = sum(1 for month in range(WINDOW_MONTHS)
                          if series_list[i][month] and series_list[j][month])
            expected = active_counts[i] * active_counts[j] * weight_sq_ratio
            pairs.append({"entity_a": names[i], "entity_b": names[j],
                          "overlap": overlap, "expected_under_null": expected,
                          "excess": overlap - expected})
    pairs.sort(key=lambda row: -row["excess"])
    return {
        "entities": len(names),
        "active_months_total": sum(active_counts),
        "observed_coactivity": observed,
        "null_mean": mean,
        "null_sd": sd,
        "zscore": zscore,
        "pvalue_one_sided": pvalue,
        "permutations": len(null_values),
        "top_pairs": pairs[:5],
    }


def hash_track(names: list[str]) -> int:
    import hashlib
    digest = hashlib.sha256("|".join(names).encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def benjamini_hochberg(rows: list[tuple[str, float]], q: float = BH_Q) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda item: item[1])
    m = len(ordered)
    cutoff = 0
    for rank, (_, pvalue) in enumerate(ordered, start=1):
        if pvalue <= rank / m * q:
            cutoff = rank
    return {"q": q, "tests": m, "rejected": cutoff,
            "cutoff_pvalue": ordered[cutoff - 1][1] if cutoff else None,
            "rejected_keys": [key for key, _ in ordered[:cutoff]]}


def track_volumes(resolved: list[dict[str, Any]]) -> dict[str, list[int]]:
    volumes: dict[str, list[int]] = defaultdict(lambda: [0] * WINDOW_MONTHS)
    for row in resolved:
        month = row["month"]
        if 0 <= month < WINDOW_MONTHS:
            volumes[row["track"]][month] += 1
    return dict(volumes)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/research.sqlite")
    parser.add_argument("--out", default="experiments/detect_v1/comovement.json")
    args = parser.parse_args(argv)

    resolved = resolve_events(Path(args.db))
    volume = lane_volume(resolved)
    per_track_volume = track_volumes(resolved)
    presence = build_presence(resolved)
    print(f"lane volume: mean {sum(volume)/len(volume):.1f} events/month, "
          f"min {min(volume)}, max {max(volume)}")

    results: dict[str, Any] = {
        "design": {
            "panel": "binary presence per (entity, track) month, 119 complete months",
            "statistic": "sum over months of C(active firms, 2) within a track",
            "null_primary": ("each firm keeps its own number of active months and draws them "
                             "with probability proportional to the TRACK's own monthly event "
                             "volume, so firm activity and the track's growth/seasonality are "
                             "both preserved; only the cross-firm timing pattern is free"),
            "null_secondary": ("same, but weighted by LANE-wide monthly volume only — reported "
                               "to show how much of an apparent co-movement is track growth "
                               "rather than synchronisation"),
            "eligibility": {"min_active_months_per_entity": MIN_ACTIVE_MONTHS_PER_ENTITY,
                            "min_entities_per_track": MIN_ENTITIES_PER_TRACK},
            "permutations": PERMUTATIONS, "seed": SEED, "fdr_q": BH_Q,
            "lane_volume": {"mean": sum(volume) / len(volume), "min": min(volume),
                            "max": max(volume), "by_month": volume},
        },
        "tracks": {},
    }
    primary_pvalues: list[tuple[str, float]] = []
    secondary_pvalues: list[tuple[str, float]] = []
    for track in sorted(presence):
        entities = {name: series for name, series in presence[track].items()
                    if sum(series) >= MIN_ACTIVE_MONTHS_PER_ENTITY}
        if len(entities) < MIN_ENTITIES_PER_TRACK:
            continue
        primary = analyse_track(entities, per_track_volume.get(track, volume))
        secondary = analyse_track(entities, volume, seed=SEED + 1)
        results["tracks"][track] = {
            "entities": primary["entities"],
            "observed_coactivity": primary["observed_coactivity"],
            "null_track_volume": {key: primary[key] for key in
                                  ("null_mean", "null_sd", "zscore", "pvalue_one_sided")},
            "null_lane_volume": {key: secondary[key] for key in
                                 ("null_mean", "null_sd", "zscore", "pvalue_one_sided")},
            "top_pairs": primary["top_pairs"],
        }
        primary_pvalues.append((track, primary["pvalue_one_sided"]))
        secondary_pvalues.append((track, secondary["pvalue_one_sided"]))
        print(f"  {track:22s} n={primary['entities']:2d} obs={primary['observed_coactivity']:5d} "
              f"| track-volume null={primary['null_mean']:7.1f} z={primary['zscore']:+6.2f} "
              f"p={primary['pvalue_one_sided']:.4f} "
              f"| lane-volume null z={secondary['zscore']:+6.2f} p={secondary['pvalue_one_sided']:.4f}")
    results["fdr_track_volume"] = benjamini_hochberg(primary_pvalues)
    results["fdr_lane_volume"] = benjamini_hochberg(secondary_pvalues)
    for key in ("fdr_track_volume", "fdr_lane_volume"):
        block = results[key]
        print(f"\nBH on {key}: {block['rejected']} of {block['tests']} tracks rejected at "
              f"q={BH_Q} -> {block['rejected_keys']}")
    write_json(Path(args.out), results)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


