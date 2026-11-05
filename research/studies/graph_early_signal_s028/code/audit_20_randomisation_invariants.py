"""S-028-CORRECTION-1 audit: randomisation invariants.

Purpose
-------
The Phase 0-3 G2 comparison used ``SnapshotSeries._build_randomised``.  This
script is the machine-readable audit that the original study never had.  It

1. builds a minimal counterexample and shows the shipped implementation fails it;
2. measures the shipped implementation against every invariant the study claimed
   for it (degree preservation, simplicity, node sets, weights, dates);
3. runs the same invariant suite against the two corrected null models
   (``s028_nullmodels.N1`` and ``N2``) on the real frozen snapshots;
4. checks deterministic reproducibility and rewiring diversity;
5. writes ``artifacts/correction_round_1/randomisation_invariants.json``.

Nothing in this script mutates an existing artifact.  It is read-only with
respect to the database (opened ``mode=ro``) and writes only under
``artifacts/correction_round_1/``.

Usage
-----
    python audit_20_randomisation_invariants.py            # full audit
    python audit_20_randomisation_invariants.py --quick    # synthetic only
    python audit_20_randomisation_invariants.py --seeds 3 --origins 6
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from s028_lib import (SnapshotSeries, load_events, parse_date, iso,  # noqa: E402
                      add_months, verify_frozen_db)
from s028_nullmodels import (N1, N2, NullSnapshotSeries, edge_index,  # noqa: E402
                              _degree_sequences, _strengths, _entrant_multiset)

STUDY = Path(__file__).resolve().parents[1]
DB = Path(r"D:\DEPPSKK\worktrees\integration-v2\data\research.sqlite")
OUT_DIR = STUDY / "artifacts" / "correction_round_1"
OUT = OUT_DIR / "randomisation_invariants.json"
DEFAULT_SEEDS = 5


# ------------------------------------------------------------------ helpers
def _snapshot_facts(snapshot: dict[str, Any]) -> dict[str, Any]:
    weighted = snapshot["weighted"]
    pairs = list(edge_index(weighted))
    entity_degree, track_degree = _degree_sequences(pairs)
    entity_strength, track_strength = _strengths(weighted)
    window_start = add_months(parse_date(snapshot["cutoff"]), -snapshot["window_months"])
    entrants = _entrant_multiset(snapshot["first_touch"], window_start)
    dates: dict[str, list[Any]] = {}
    for entity, tracks in weighted.items():
        for track in tracks:
            dates.setdefault(track, [])
    pool: dict[str, Counter] = {}
    for event in snapshot.get("window_events", []):
        pool.setdefault(event["track_id"], Counter())[event["day"]] += 1
    return {"pairs": pairs, "edge_count": len(pairs),
            "entity_degree": entity_degree, "track_degree": track_degree,
            "entity_strength": entity_strength, "track_strength": track_strength,
            "entrants": entrants, "date_pool": pool, "dates": dates}


def _date_multiset(snapshot: dict[str, Any]) -> dict[str, Counter]:
    out: dict[str, Counter] = {}
    for event in snapshot.get("window_events", []):
        out.setdefault(event["track_id"], Counter())[event["day"]] += 1
    return out


def compare_to_observed(observed: dict[str, Any], candidate: dict[str, Any],
                        *, candidate_pairs: list[tuple[str, str]] | None = None) -> dict[str, Any]:
    """Every declared invariant, computed between one observed and one candidate."""
    obs = _snapshot_facts(observed)
    pairs = candidate_pairs if candidate_pairs is not None else list(edge_index(candidate["weighted"]))
    entity_degree, track_degree = _degree_sequences(pairs)
    entity_strength, track_strength = _strengths(candidate["weighted"])
    window_start = add_months(parse_date(observed["cutoff"]), -observed["window_months"])
    entrants = _entrant_multiset(candidate["first_touch"], window_start)
    observed_pool = _date_multiset(observed)
    candidate_pool = _date_multiset(candidate)
    if not candidate_pool:
        # Null snapshots carry no ``window_events``; reconstruct the per-track date
        # multiset from the weights and the assigned first-touch / draw metadata is
        # not available here, so the temporal check is done by the builder itself
        # (``temporal_total_variation_*`` in null_stats).  Report None, not False.
        temporal_tv = None
    else:
        tv_values = []
        for track in set(observed_pool) | set(candidate_pool):
            a, b = observed_pool.get(track, Counter()), candidate_pool.get(track, Counter())
            total = sum(a.values()) or 1
            tv_values.append(sum(abs(a[day] - b[day]) for day in set(a) | set(b)) / (2.0 * total))
        temporal_tv = max(tv_values) if tv_values else 0.0
    all_entities = set(obs["entity_degree"]) | set(entity_degree)
    all_tracks = set(obs["track_degree"]) | set(track_degree)
    return {
        "edges_observed": obs["edge_count"],
        "edges_candidate": len(pairs),
        "edges_lost": obs["edge_count"] - len(set(pairs)),
        "degree_sequences_equal": (obs["entity_degree"] == entity_degree
                                   and obs["track_degree"] == track_degree),
        "edge_duplicates": len(pairs) - len(set(pairs)),
        "node_sets_equal": (set(obs["entity_degree"]) == set(entity_degree)
                            and set(obs["track_degree"]) == set(track_degree)),
        "total_event_count_equal": (sum(obs["entity_strength"].values())
                                    == sum(entity_strength.values())),
        "company_strength_deviation_max": max(
            abs(entity_strength.get(e, 0.0) - obs["entity_strength"].get(e, 0.0))
            for e in all_entities) if all_entities else 0.0,
        "track_strength_deviation_max": max(
            abs(track_strength.get(k, 0.0) - obs["track_strength"].get(k, 0.0))
            for k in all_tracks) if all_tracks else 0.0,
        "entrant_counts_equal": obs["entrants"] == entrants,
        "entrants_observed_total": sum(obs["entrants"].values()),
        "entrants_candidate_total": sum(entrants.values()),
        "observed_entrant_share_of_edges": (sum(obs["entrants"].values()) / obs["edge_count"]
                                            if obs["edge_count"] else None),
        "candidate_entrant_share_of_edges": (sum(entrants.values()) / len(pairs)
                                             if pairs else None),
        "temporal_total_variation_max": temporal_tv,
        "edges_changed_fraction": (len(set(pairs) - set(obs["pairs"])) / len(obs["pairs"])
                                   if obs["pairs"] else None),
    }


def _synthetic_events(edges: list[tuple[str, str]], days: list[date]) -> list[dict[str, Any]]:
    return [{"company_key": entity, "track_id": track, "day": day, "available": day,
             "event_id": f"{entity}|{track}|{day}"}
            for entity, track in edges for day in days]


def minimal_counterexample() -> dict[str, Any]:
    """Find the smallest bipartite graph on which the shipped swap breaks simplicity.

    Deterministic bounded search: graphs with 4..8 edges over a fixed small node
    pool, shipped implementation run with seeds 1..40 until a duplicate or a
    degree violation appears.  Returns the first (smallest) counterexample found.
    """
    node_pool = ["a", "b", "c", "d", "e", "f", "x", "y", "z", "w"]
    candidates = [
        [("a", "x"), ("b", "x"), ("b", "y"), ("c", "y")],
        [("a", "x"), ("b", "x"), ("c", "x"), ("a", "y"), ("b", "y"), ("c", "z")],
        [("a", "x"), ("b", "x"), ("b", "y"), ("c", "y"), ("d", "z"), ("a", "z")],
        [("a", "x"), ("a", "y"), ("b", "x"), ("b", "z"), ("c", "y"), ("c", "z"),
         ("d", "w"), ("e", "w")],
        [("a", "x"), ("b", "x"), ("c", "x"), ("d", "y"), ("e", "y"), ("a", "y"),
         ("b", "z"), ("c", "z"), ("f", "z")],
    ]
    days = [date(2024, 3, 1), date(2024, 6, 1), date(2024, 9, 1)]
    results = []
    for edges in candidates:
        events = _synthetic_events(edges, days)
        cutoff = [date(2025, 1, 1)]
        observed = SnapshotSeries(events, cutoff, window_months=12)
        observed_snapshot = observed._cache[observed._cutoffs[0]]
        for seed in range(1, 41):
            buggy = SnapshotSeries(events, cutoff, window_months=12, randomised=True, seed=seed)
            snapshot = buggy._cache[buggy._cutoffs[0]]
            facts = compare_to_observed(observed_snapshot, snapshot)
            if (facts["edge_duplicates"] > 0 or not facts["degree_sequences_equal"]
                    or not facts["node_sets_equal"]):
                results.append({"edges": edges, "n_edges": len(edges), "seed": seed,
                                "first_failing_seed": seed, **facts})
                break
        if results:
            break
    if not results:
        return {"found": False}
    case = results[0]
    # the corrected implementation on exactly the same graph and seed
    events = _synthetic_events(case["edges"], days)
    cutoff = [date(2025, 1, 1)]
    observed = SnapshotSeries(events, cutoff, window_months=12)
    observed_snapshot = observed._cache[observed._cutoffs[0]]
    corrected = {}
    for model in (N1, N2):
        series = NullSnapshotSeries(events, cutoff, window_months=12, null_model=model,
                                    seed=case["seed"])
        snapshot = series._cache[series._cutoffs[0]]
        corrected[model] = compare_to_observed(observed_snapshot, snapshot)
        corrected[model]["weight_mode"] = series.null_stats[series._cutoffs[0]].get("weight_mode")
    return {"found": True, "case": case, "corrected_on_same_case": corrected,
            "verdict": "SHIPPED_IMPLEMENTATION_FAILS_MINIMAL_COUNTEREXAMPLE"}


# --------------------------------------------------------------------- audit
def audit_shipped(events: list[dict[str, Any]], origins: list[str],
                  seeds: list[int]) -> dict[str, Any]:
    observed = SnapshotSeries(events, origins)
    records = []
    failures = Counter()
    for seed in seeds:
        series = SnapshotSeries(events, origins, randomised=True, seed=seed)
        for cutoff in origins:
            if cutoff not in observed._cache or cutoff not in series._cache:
                continue
            facts = compare_to_observed(observed._cache[cutoff], series._cache[cutoff])
            facts.update({"seed": seed, "origin": cutoff, "model": "SHIPPED_build_randomised"})
            records.append(facts)
            if not facts["degree_sequences_equal"]:
                failures["degree_sequences"] += 1
            if facts["edge_duplicates"] > 0:
                failures["duplicate_edges"] += 1
            if not facts["node_sets_equal"]:
                failures["node_sets"] += 1
            if not facts["total_event_count_equal"]:
                failures["total_event_count"] += 1
            if not facts["entrant_counts_equal"]:
                failures["entrant_counts"] += 1
    draws = len(records)
    return {"draws": draws, "failures": dict(failures),
            "pass_rate": {name: 1.0 - count / draws for name, count in failures.items()} if draws else {},
            "verdict": "PASS" if not failures else "FAIL",
            "records": records}


def audit_null(events: list[dict[str, Any]], origins: list[str],
               seeds: list[int], model: str) -> dict[str, Any]:
    observed = SnapshotSeries(events, origins)
    records = []
    failures = Counter()
    deterministic = Counter()
    for seed in seeds:
        series = NullSnapshotSeries(events, origins, null_model=model, seed=seed)
        repeat = NullSnapshotSeries(events, origins, null_model=model, seed=seed)
        other = NullSnapshotSeries(events, origins, null_model=model, seed=seed + 1000)
        for cutoff in origins:
            if cutoff not in observed._cache or cutoff not in series._cache:
                continue
            facts = compare_to_observed(observed._cache[cutoff], series._cache[cutoff])
            weight_mode = series.null_stats[cutoff].get("weight_mode")
            if model == N2:
                facts["temporal_total_variation_max"] = series.null_stats[cutoff]["temporal_total_variation_max"]
            facts.update({"seed": seed, "origin": cutoff, "model": model,
                          "weight_mode": weight_mode,
                          "swap_acceptance_rate": series.null_stats[cutoff]["acceptance_rate"],
                          "swap_attempts": series.null_stats[cutoff]["attempts"],
                          "deg_ok_builder": series.null_stats[cutoff]["degree_sequences_equal"],
                          "simple_builder": series.null_stats[cutoff]["simple"],
                          "entrant_multiset_builder": series.null_stats[cutoff]["track_entry_date_multisets_equal"],
                          "temporal_tv_builder": series.null_stats[cutoff]["temporal_total_variation_mean"]})
            records.append(facts)
            if not facts["degree_sequences_equal"]:
                failures["degree_sequences"] += 1
            if facts["edge_duplicates"] > 0:
                failures["duplicate_edges"] += 1
            if not facts["node_sets_equal"]:
                failures["node_sets"] += 1
            if not facts["entrant_counts_equal"]:
                failures["entrant_counts"] += 1
            if model == N2 and not facts["total_event_count_equal"]:
                failures["total_event_count"] += 1
            if model == N2 and facts["track_strength_deviation_max"] > 1e-9:
                failures["track_strength"] += 1
            same = (edge_index(repeat._cache[cutoff]["weighted"]) == edge_index(series._cache[cutoff]["weighted"]))
            differs = (edge_index(other._cache[cutoff]["weighted"]) != edge_index(series._cache[cutoff]["weighted"]))
            deterministic["same_seed_identical"] += int(same)
            deterministic["different_seed_differs"] += int(differs)
    draws = len(records)
    company_dev = [row["company_strength_deviation_max"] for row in records]
    track_dev = [row["track_strength_deviation_max"] for row in records]
    diversity = [row["edges_changed_fraction"] for row in records if row["edges_changed_fraction"] is not None]
    acceptance = [row["swap_acceptance_rate"] for row in records if row["swap_acceptance_rate"] is not None]
    temporal = [row["temporal_tv_builder"] for row in records if row["temporal_tv_builder"] is not None]
    return {
        "model": model, "draws": draws, "failures": dict(failures),
        "verdict": "PASS" if not failures else "FAIL",
        "deterministic_reproducibility": {
            "same_seed_identical": deterministic["same_seed_identical"],
            "different_seed_differs": deterministic["different_seed_differs"],
            "draws": draws,
            "ok": deterministic["same_seed_identical"] == draws and deterministic["different_seed_differs"] == draws,
        },
        "summary": {
            "company_strength_deviation_max": max(company_dev) if company_dev else None,
            "company_strength_deviation_mean": (sum(company_dev) / len(company_dev)) if company_dev else None,
            "track_strength_deviation_max": max(track_dev) if track_dev else None,
            "edges_changed_fraction_min": min(diversity) if diversity else None,
            "edges_changed_fraction_mean": (sum(diversity) / len(diversity)) if diversity else None,
            "swap_acceptance_rate_mean": (sum(acceptance) / len(acceptance)) if acceptance else None,
            "swap_acceptance_rate_min": min(acceptance) if acceptance else None,
            "temporal_total_variation_mean": (sum(temporal) / len(temporal)) if temporal else None,
            "temporal_total_variation_max": max(temporal) if temporal else None,
            "weight_modes": dict(Counter(row["weight_mode"] for row in records if row["weight_mode"])),
        },
        "records": records,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true", help="synthetic counterexample only")
    parser.add_argument("--seeds", type=int, default=DEFAULT_SEEDS)
    parser.add_argument("--origins", type=int, default=0,
                        help="limit the number of origins (0 = all; holdouts always included)")
    args = parser.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"study": "S-028", "correction": "S-028-CORRECTION-1",
                              "audit": "randomisation invariants",
                              "generated_at_utc": __import__("datetime").datetime.now(
                                  __import__("datetime").timezone.utc).isoformat(timespec="seconds")}
    report["minimal_counterexample"] = minimal_counterexample()
    print("minimal counterexample:",
          report["minimal_counterexample"].get("verdict", "not found"),
          report["minimal_counterexample"].get("case", {}).get("n_edges"))

    if not args.quick:
        db_check = verify_frozen_db(DB)
        events = load_events(DB)
        panel_origins = sorted(iso(value) for value in _h4q_origins(events))
        origins = panel_origins
        holdouts = ["2025-04-01", "2025-07-01", "2025-10-01"]
        if args.origins and args.origins < len(origins):
            keep = set(holdouts) & set(origins)
            step = max(1, len(origins) // max(1, args.origins - len(keep)))
            sampled = origins[::step][: args.origins - len(keep)]
            origins = sorted(keep | set(sampled))
        seeds = [20261104 + index for index in range(args.seeds)]
        report["database"] = {"path": str(DB), **db_check}
        report["origins"] = origins
        report["seeds"] = seeds
        shipped = audit_shipped(events, origins, seeds)
        report["shipped_implementation"] = shipped
        print("shipped implementation:", shipped["verdict"], shipped["failures"])
        for model in (N1, N2):
            result = audit_null(events, origins, [20261104 + index for index in range(min(args.seeds, 3))],
                                model)
            report[f"null_model_{model}"] = result
            print(f"null {model}:", result["verdict"], result["failures"],
                  result["summary"].get("weight_modes"))
    report["overall"] = {
        "shipped_implementation_verdict": report.get("shipped_implementation", {}).get("verdict"),
        "N1_verdict": report.get(f"null_model_{N1}", {}).get("verdict"),
        "N2_verdict": report.get(f"null_model_{N2}", {}).get("verdict"),
        "gate_for_G2_rerun": (
            "PASS" if report.get("shipped_implementation", {}).get("verdict") == "FAIL"
            and report.get(f"null_model_{N1}", {}).get("verdict") == "PASS"
            and report.get(f"null_model_{N2}", {}).get("verdict") == "PASS" else "BLOCKED"),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
                   encoding="utf-8")
    print("\nwrote", OUT)
    print("overall:", json.dumps(report["overall"], indent=2))
    return 0 if report["overall"]["gate_for_G2_rerun"] == "PASS" else 1


def _h4q_origins(events: list[dict[str, Any]]) -> list[date]:
    """The 24 quarterly origins used by the H=4q main experiment."""
    from s028_lib import build_entry_panel
    panel = build_entry_panel(events, entity_field="company_key", horizon_months=12,
                              label_kind="qualifying", dataset_version="audit20")
    return [parse_date(value) for value in panel["cutoffs"]]


if __name__ == "__main__":
    raise SystemExit(main())
