"""B-042: technology-ENTRY events as the unit of analysis.

Every previous cycle hit the same wall: at (entity, track, month) granularity the lane is
~0.2 events/month, so cell-level statistics are starved. This module changes the unit of
analysis to the event that matters for the mission — **a company entering a technology track
it has not been active in** — and asks the two questions the monthly panels could not answer
with any power:

  A. **Industry clustering**: do entries into a track bunch in time across companies
     (a technology wave), or are they spread evenly given how many companies were eligible?
  B. **Firm clustering**: does one company enter several tracks at once (a strategic
     redirection episode), or is entry a steady drip?

Both are tested against the same style of null used in the co-movement analysis: preserve the
number of entries in each unit, distribute them over months with probability proportional to
the **at-risk** count in that month, and ask whether the observed temporal dispersion exceeds
that null. This conditions out both the growth of the lane and the changing size of the risk
set, which is exactly what the naive tests got wrong in earlier cycles.

Definitions (pre-registered in DECISIONS D-024 before this ran):
  * observation window: the lane's 119 complete months
  * risk, for (entity, track) at month m: the entity has >=1 event in ANY track before m
    (it is an observable filer), it has no event in this track in [m - 36, m), and
    m >= 24 (so at least two years of observed absence precede the entry)
  * entry: the first month in which a cell that is at risk produces >=1 event

Usage:
    python experiments/detect_v1/entries.py --db data/research.sqlite
"""
from __future__ import annotations

import argparse
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.cycle2_coverage.panel import write_json  # noqa: E402
from experiments.detect_v1.streams import WINDOW_MONTHS, month_labels  # noqa: E402
from experiments.detect_v1.widths import resolve_events  # noqa: E402

# ---------------------------------------------------------------- pre-registered
DORMANCY_MONTHS = 36
MIN_ENTRY_MONTH = 24          # >= 2 years of observed absence before an entry counts
PERMUTATIONS = 2000
SEED = 7
BH_Q = 0.10
MIN_ENTRIES_PER_UNIT = 3      # a unit with fewer entries cannot show dispersion


def resolve_events_with_codes(db_path: Path, churn_cutoff: str | None) -> list[dict[str, Any]]:
    """Resolve (entity, track, month) and optionally drop events on late-created product codes.

    ``churn_cutoff`` is an ISO month (e.g. "2022-01"). When given, events whose product code
    first appears in the lane on or after that month are removed — the taxonomy-churn control
    used in the level panels. A new product code appearing in a track can make many firms look
    like they "entered" it at once, which would manufacture a fake technology wave.
    """
    from experiments.cycle2_coverage.panel import load_regulatory_events
    from experiments.detect_v1.streams import load_product_codes, month_index
    from medradar.intelligence.universe import entity_key, normalise_applicant

    events = load_regulatory_events(db_path)
    codes = load_product_codes(db_path)
    first_seen: dict[str, int] = {}
    for event in events:
        code = codes.get(str(event.get("event_id")), "")
        index = month_index(event["day"])
        if not code or index is None:
            continue
        if code not in first_seen or index < first_seen[code]:
            first_seen[code] = index
    cutoff_index = None
    if churn_cutoff is not None:
        for index, label in enumerate(month_labels()):
            if label >= churn_cutoff:
                cutoff_index = index
                break
    recent_codes = ({code for code, index in first_seen.items() if index >= cutoff_index}
                    if cutoff_index is not None else set())

    resolved: list[dict[str, Any]] = []
    dropped = 0
    for event in events:
        normalised = normalise_applicant(event.get("applicant_raw"))
        track = event.get("track_id")
        index = month_index(event["day"])
        if not normalised or not track or index is None:
            continue
        code = codes.get(str(event.get("event_id")), "")
        if code in recent_codes:
            dropped += 1
            continue
        resolved.append({"entity": entity_key(normalised), "track": track, "month": index})
    if churn_cutoff is not None:
        print(f"churn filter ({churn_cutoff}): dropped {dropped} events on "
              f"{len(recent_codes)} recently-created product codes")
    return resolved


def dispersion(counts: list[int]) -> float | None:
    """Variance-to-mean ratio of monthly counts (1 = Poisson-like)."""
    if not counts:
        return None
    mean = sum(counts) / len(counts)
    if mean <= 0:
        return None
    variance = sum((value - mean) ** 2 for value in counts) / len(counts)
    return variance / mean


def at_risk_and_entries(resolved: list[dict[str, Any]], *,
                        require_prior_filer: bool = False) -> dict[str, Any]:
    """Build risk sets and first-entry events for both units of analysis.

    Only *first* event months matter, which makes the risk sets exact and cheap:

    * first_entry(entity, track) = the month of the entity's first event in that track,
      provided it is >= MIN_ENTRY_MONTH (so at least two years of observed absence precede it).
    * A cell is at risk of a first entry in month m iff the entity is an observable filer by
      m (has some event before m) and its first event in that track is >= m (no event yet,
      or the entry happens this month).
    * Entries into a track the entity never touches stay at risk for the rest of the window —
      that is what a first-entry risk set means, and it is why the risk set shrinks over time
      as firms exhaust unexplored tracks.
    """
    first_in_track: dict[tuple[str, str], int] = {}
    first_month: dict[str, int] = {}
    entity_months: dict[str, set[int]] = defaultdict(set)
    for row in resolved:
        month = row["month"]
        if not (0 <= month < WINDOW_MONTHS):
            continue
        key = (row["entity"], row["track"])
        if key not in first_in_track or month < first_in_track[key]:
            first_in_track[key] = month
        if row["entity"] not in first_month or month < first_month[row["entity"]]:
            first_month[row["entity"]] = month
        entity_months[row["entity"]].add(month)

    all_tracks = sorted({track for _, track in first_in_track})
    track_count = len(all_tracks)

    # entries: first observed touch of a track, at least MIN_ENTRY_MONTH into the window.
    # With ``require_prior_filer`` an entry only counts when the entity was already an
    # observable filer (had some event in another track before the entry month). Without it,
    # a brand-new legal entity appearing in the lane is scored as a technology entry, which is
    # a different phenomenon (entity appearance, not firm-level technology entry) and is the
    # first artifact the ivd_immuno wave must be tested against.
    entries: list[dict[str, Any]] = []
    new_entity_entries = 0
    entered_by_month: dict[str, list[int]] = defaultdict(lambda: [0] * WINDOW_MONTHS)
    for (entity, track), month in first_in_track.items():
        entered_by_month[track][month] += 1
        if month < MIN_ENTRY_MONTH:
            continue
        prior_filer = first_month.get(entity, month) < month
        if require_prior_filer and not prior_filer:
            new_entity_entries += 1
            continue
        entries.append({"entity": entity, "track": track, "month": month,
                        "date": month_labels()[month], "prior_filer": prior_filer})

    # risk sets via prefix counts
    filers_before = [0] * (WINDOW_MONTHS + 1)
    for month in range(WINDOW_MONTHS):
        filers_before[month + 1] = filers_before[month] + sum(
            1 for entity, first in first_month.items() if first == month)
    risk_track: dict[str, list[int]] = {}
    for track in all_tracks:
        per_month = entered_by_month[track]
        entered_prefix = [0] * (WINDOW_MONTHS + 1)
        for month in range(WINDOW_MONTHS):
            entered_prefix[month + 1] = entered_prefix[month] + per_month[month]
        risk_track[track] = [
            max(0, filers_before[month] - entered_prefix[month])
            for month in range(WINDOW_MONTHS)
        ]

    risk_entity: dict[str, list[int]] = {}
    for entity, first in first_month.items():
        per_month = [0] * WINDOW_MONTHS
        for track in all_tracks:
            month = first_in_track.get((entity, track))
            if month is not None:
                per_month[month] += 1
        entered_prefix = [0] * (WINDOW_MONTHS + 1)
        for month in range(WINDOW_MONTHS):
            entered_prefix[month + 1] = entered_prefix[month] + per_month[month]
        risk_entity[entity] = [
            (track_count - entered_prefix[month]) if month > first else 0
            for month in range(WINDOW_MONTHS)
        ]

    return {
        "entries": entries,
        "risk_track": risk_track,
        "risk_entity": risk_entity,
        "first_month": first_month,
        "track_count": track_count,
        "new_entity_entries_excluded": new_entity_entries,
    }


def cluster_test(unit_entries: list[int], risk: list[int], *, permutations: int,
                 rng: random.Random, label: str) -> dict[str, Any]:
    """One-sided test that entries cluster in time more than the risk-weighted null."""
    observed_counts = [0] * WINDOW_MONTHS
    for month in unit_entries:
        observed_counts[month] += 1
    observed = dispersion(observed_counts)
    if observed is None or len(unit_entries) < MIN_ENTRIES_PER_UNIT:
        return {"unit": label, "entries": len(unit_entries), "status": "insufficient"}
    weights = [max(value, 0) for value in risk]
    total_weight = sum(weights)
    if total_weight <= 0:
        return {"unit": label, "entries": len(unit_entries), "status": "no risk set"}

    def draw() -> list[int]:
        counts = [0] * WINDOW_MONTHS
        for _ in range(len(unit_entries)):
            draw_value = rng.random() * total_weight
            accumulated = 0.0
            for month, weight in enumerate(weights):
                accumulated += weight
                if accumulated >= draw_value:
                    counts[month] += 1
                    break
            else:
                counts[-1] += 1
        return counts

    null_values = []
    for _ in range(permutations):
        value = dispersion(draw())
        if value is not None:
            null_values.append(value)
    if not null_values:
        return {"unit": label, "entries": len(unit_entries), "status": "degenerate null"}
    null_values.sort()
    mean = sum(null_values) / len(null_values)
    variance = sum((value - mean) ** 2 for value in null_values) / len(null_values)
    sd = math.sqrt(variance) if variance > 0 else 0.0
    exceed = sum(1 for value in null_values if value >= observed)
    return {
        "unit": label,
        "entries": len(unit_entries),
        "observed_dispersion": observed,
        "null_mean_dispersion": mean,
        "null_sd": sd,
        "zscore": (observed - mean) / sd if sd > 0 else None,
        "pvalue_one_sided": (exceed + 1) / (len(null_values) + 1),
        "permutations": len(null_values),
    }


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/research.sqlite")
    parser.add_argument("--out", default="experiments/detect_v1/entries.json")
    parser.add_argument("--require-prior-filer", action="store_true",
                        help="score only entries by entities already observable before the entry")
    parser.add_argument("--churn-cutoff", default=None,
                        help="ISO month; drop events on product codes first seen on/after it")
    args = parser.parse_args(argv)

    if args.churn_cutoff:
        resolved = resolve_events_with_codes(Path(args.db), args.churn_cutoff)
    else:
        resolved = resolve_events(Path(args.db))
    bundle = at_risk_and_entries(resolved, require_prior_filer=args.require_prior_filer)
    entries = bundle["entries"]
    print(f"entry events: {len(entries)}  (dormancy {DORMANCY_MONTHS}m, min entry month "
          f"{MIN_ENTRY_MONTH}; prior-filer required={bool(args.require_prior_filer)}; "
          f"new-entity entries excluded={bundle['new_entity_entries_excluded']})")

    by_track: dict[str, list[int]] = defaultdict(list)
    by_entity: dict[str, list[int]] = defaultdict(list)
    for entry in entries:
        by_track[entry["track"]].append(entry["month"])
        by_entity[entry["entity"]].append(entry["month"])

    rng = random.Random(SEED)
    track_results = []
    for track, months in sorted(by_track.items()):
        result = cluster_test(months, bundle["risk_track"].get(track, [0] * WINDOW_MONTHS),
                              permutations=PERMUTATIONS, rng=rng, label=track)
        track_results.append(result)
    entity_results = []
    for entity, months in sorted(by_entity.items(),
                                 key=lambda item: -len(item[1]))[:60]:
        result = cluster_test(months, bundle["risk_entity"].get(entity, [0] * WINDOW_MONTHS),
                              permutations=PERMUTATIONS, rng=rng, label=entity)
        entity_results.append(result)

    def collect(results: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        usable = [row for row in results if "pvalue_one_sided" in row]
        fdr = benjamini_hochberg([(row["unit"], row["pvalue_one_sided"]) for row in usable])
        return usable, fdr

    track_usable, track_fdr = collect(track_results)
    entity_usable, entity_fdr = collect(entity_results)

    year_counts = Counter(str(entry["date"])[:4] for entry in entries)
    payload = {
        "design": {
            "decision": "research/DECISIONS.md D-024 (pre-registered before this run)",
            "unit": "technology-entry event (company, track, first observed month)",
            "dormancy_months": DORMANCY_MONTHS,
            "min_entry_month": MIN_ENTRY_MONTH,
            "null": ("entry months for a unit are drawn with probability proportional to the "
                     "unit's at-risk count in that month, preserving the number of entries and "
                     "conditioning out lane growth and risk-set size"),
            "statistic": "variance/mean of monthly entry counts (dispersion index)",
            "permutations": PERMUTATIONS, "seed": SEED, "fdr_q": BH_Q,
            "min_entries_per_unit": MIN_ENTRIES_PER_UNIT,
            "require_prior_filer": bool(args.require_prior_filer),
            "require_prior_filer_note": (
                "when set, an entry only counts if the entity was already an observable filer "
                "(some event in another track before the entry month); this separates firm-level "
                "technology entry from a brand-new legal entity appearing in the lane"),
        },
        "counts": {
            "entries": len(entries),
            "new_entity_entries_excluded": bundle["new_entity_entries_excluded"],
            "entities_with_entries": len(by_entity),
            "tracks_with_entries": len(by_track),
            "by_year": dict(sorted(year_counts.items())),
            "entries_per_track_top": dict(Counter(
                {track: len(months) for track, months in by_track.items()}).most_common(12)),
        },
        "industry_clustering": {"tests": track_usable, "fdr": track_fdr},
        "firm_clustering": {"tests": entity_usable, "fdr": entity_fdr},
        "entries_sample": entries[:200],
        "entries": entries,
    }
    write_json(Path(args.out), payload)

    print(f"\nentries per year: {dict(sorted(year_counts.items()))}")
    print(f"\n== industry clustering (per track) ==")
    for row in sorted(track_usable, key=lambda item: item["pvalue_one_sided"])[:12]:
        print(f"  {row['unit']:22s} n={row['entries']:3d} D={row['observed_dispersion']:.2f} "
              f"null={row['null_mean_dispersion']:.2f} z={row['zscore'] if row['zscore'] is None else round(row['zscore'],2)} "
              f"p={row['pvalue_one_sided']:.4f}")
    print(f"  BH: {track_fdr['rejected']} of {track_fdr['tests']} tracks rejected; "
          f"{track_fdr['rejected_keys']}")
    print(f"\n== firm clustering (per entity, top 60 by entries) ==")
    for row in sorted(entity_usable, key=lambda item: item["pvalue_one_sided"])[:8]:
        print(f"  {row['unit'][:40]:40s} n={row['entries']:3d} D={row['observed_dispersion']:.2f} "
              f"p={row['pvalue_one_sided']:.4f}")
    print(f"  BH: {entity_fdr['rejected']} of {entity_fdr['tests']} entities rejected; "
          f"{entity_fdr['rejected_keys'][:6]}")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())





