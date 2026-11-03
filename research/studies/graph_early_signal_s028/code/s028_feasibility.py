"""S-028 Phase-0 feasibility census + fidelity self-check.

Computes every number in DATA_FEASIBILITY.md. It runs NO predictive model.

The fidelity self-check is mandatory before any S-028 result may be reported:
with the frozen label rule (any material event), horizon 12 months and
``company_key`` entities, this reimplementation must reproduce the frozen
cycle-2 P1 panel exactly (41,003 examples / 503 positives / 24 origins).
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from s028_lib import (  # noqa: E402
    B3_FEATURES, DORMANCY_MONTHS, G1_FEATURES, build_entry_panel, load_events,
    original_pma, sha256_file, traditional_510k, verify_frozen_db, write_json,
)

STUDY = Path(__file__).resolve().parents[1]
DB = Path(r"D:\DEPPSKK\worktrees\integration-v2\data\research.sqlite")
OUT = STUDY / "artifacts" / "feasibility.json"

FROZEN_P1 = {"n_examples": 41003, "n_positives": 503, "origins": 24,
             "coverage_start": "2016-11-01", "coverage_end": "2026-10-15"}


def main() -> int:
    record = verify_frozen_db(DB, strict=False)
    events = load_events(DB)
    report: dict = {"input": record, "event_counts": {}}

    material = events
    qualifying = [e for e in events if e["qualifying"]]
    report["event_counts"] = {
        "material_events_total": len(material),
        "qualifying_events_total": len(qualifying),
        "qualifying_share": len(qualifying) / len(material) if material else None,
        "by_kind_material": dict(Counter(e["kind"] for e in material)),
        "by_kind_qualifying": dict(Counter(e["kind"] for e in qualifying)),
    }

    # --- composition of the lane: how much is maintenance?)
    comp = Counter()
    for event in material:
        if event["kind"] == "510k":
            label = (event["clearance_type"] or "MISSING").strip() or "MISSING"
            comp[f"510k:{label}"] += 1
            if event["qualifying"]:
                comp["510k:QUALIFYING(traditional)"] += 1
        else:
            supp = (event["supplement_number"] or "").strip().upper()
            if supp in ("", "0", "S0"):
                comp["pma:original(PMA)"] += 1
            else:
                comp["pma:supplement"] += 1
            if event["qualifying"]:
                comp["pma:QUALIFYING(original)"] += 1
    report["lane_composition"] = dict(sorted(comp.items(), key=lambda kv: -kv[1]))

    # --- coverage / mapping coverage
    report["coverage"] = {
        "events_with_company_key": sum(1 for e in material if e.get("company_key")),
        "events_with_track_id": sum(1 for e in material if e.get("track_id")),
        "events_with_both": sum(1 for e in material if e.get("company_key") and e.get("track_id")),
        "distinct_companies": len({e["company_key"] for e in material if e.get("company_key")}),
        "distinct_tracks": len({e["track_id"] for e in material if e.get("track_id")}),
        "date_min": min(e["day"] for e in material).isoformat(),
        "date_max": max(e["day"] for e in material).isoformat(),
    }
    report["coverage"]["share_with_both"] = (
        report["coverage"]["events_with_both"] / len(material) if material else None)

    # --- knowledge-clock audit
    gaps = Counter()
    for event in material:
        gaps[(event["available"] - event["day"]).days] += 1
    same = gaps.get(0, 0)
    report["knowledge_clock"] = {
        "available_at_minus_event_date_days": {str(k): v for k, v in sorted(gaps.items())},
        "available_at_equals_event_date": same,
        "share": same / len(material) if material else None,
        "interpretation": (
            "available_at is event_date/decision_date + 14 days for every row: a documented "
            "ESTIMATE of the bulk-lane publication lag, not a measured first-publication time. "
            "It is a historical_proxy_asof. first_seen_at and as_of are single bulk-fetch dates "
            "(2026-11-01) for all historical rows and therefore carry no point-in-time information."),
    }

    # --- fidelity self-check against the frozen P1 benchmark
    frozen = build_entry_panel(events, entity_field="company_key", horizon_months=12,
                               label_kind="material", dataset_version="first_entry_v1")
    checks = {
        "n_examples": [FROZEN_P1["n_examples"], frozen["n_examples"]],
        "n_positives": [FROZEN_P1["n_positives"], frozen["n_positives"]],
        "origins": [FROZEN_P1["origins"], len(frozen["cutoffs"])],
        "coverage_start": [FROZEN_P1["coverage_start"], frozen["coverage_start"]],
        "coverage_end": [FROZEN_P1["coverage_end"], frozen["coverage_end"]],
    }
    report["fidelity_self_check"] = {
        "rule": "label=material, horizon=12m, entity=company_key must equal frozen cycle-2 P1",
        "checks": {name: {"expected": pair[0], "observed": pair[1], "ok": pair[0] == pair[1]}
                   for name, pair in checks.items()},
        "ok": all(pair[0] == pair[1] for pair in checks.values()),
        "candidates_by_origin": frozen["candidates_by_origin"],
        "positives_by_origin": frozen["positives_by_origin"],
        "frozen_candidates_by_origin": frozen["candidates_by_origin"],
    }

    # --- S-028 primary target feasibility: qualifying-event entry target
    panels = {}
    for horizon_quarters, label in ((4, "primary_H4q"), (2, "secondary_H2q")):
        horizon_months = horizon_quarters * 3
        for label_kind in ("qualifying", "material"):
            panel = build_entry_panel(events, entity_field="company_key",
                                      horizon_months=horizon_months,
                                      label_kind=label_kind,
                                      dataset_version=f"s028_{label}_{label_kind}")
            key = f"{label}_{label_kind}"
            origins = panel["cutoffs"]
            rows_by_origin = {o: sum(1 for r in panel["examples"] if r["cutoff"] == o)
                              for o in origins}
            panels[key] = {
                "horizon_months": horizon_months, "label_kind": label_kind,
                "n_examples": panel["n_examples"], "n_positives": panel["n_positives"],
                "base_rate": (panel["n_positives"] / panel["n_examples"]
                              if panel["n_examples"] else None),
                "origins": len(origins), "first_origin": origins[0] if origins else None,
                "last_origin": origins[-1] if origins else None,
                "coverage_start": panel["coverage_start"], "coverage_end": panel["coverage_end"],
                "mean_candidates_per_origin": (sum(panel["candidates_by_origin"].values())
                                               / len(origins) if origins else None),
                "mean_positives_per_origin": (sum(panel["positives_by_origin"].values())
                                              / len(origins) if origins else None),
                "by_origin": {o: {"rows": rows_by_origin[o],
                                  "positives": panel["positives_by_origin"].get(o, 0)}
                              for o in origins},
            }
    report["panels"] = panels

    # --- first-entry event census (pair-level, qualifying)
    pair_first: dict[tuple[str, str], date] = {}
    for event in qualifying:
        if not (event.get("company_key") and event.get("track_id")):
            continue
        pair = (event["company_key"], event["track_id"])
        if pair not in pair_first or event["day"] < pair_first[pair]:
            pair_first[pair] = event["day"]
    by_year = Counter(day.year for day in pair_first.values())
    report["first_qualifying_entry_census"] = {
        "distinct_company_track_pairs_with_qualifying_event": len(pair_first),
        "observed_pairs_material": frozen["observed_pair_count"],
        "possible_pairs": frozen["entity_count"] * frozen["track_count"],
        "bipartite_density_observed": (frozen["observed_pair_count"]
                                       / (frozen["entity_count"] * frozen["track_count"])),
        "entries_by_year": dict(sorted(by_year.items())),
        "entries_in_coverage_window_2016on": sum(v for y, v in by_year.items() if y >= 2016),
        "left_truncation_note": ("a pair's first qualifying event inside 2016-11..2026-10 is a "
                                 "first *observed* activity, not a first-ever activity"),
    }

    # --- left truncation / already-active share at the first origin
    first_origin = panels["primary_H4q_qualifying"]["first_origin"]
    cutoff = date.fromisoformat(first_origin)
    active_before = {(e["company_key"], e["track_id"]) for e in material
                     if e.get("company_key") and e.get("track_id") and e["day"] <= cutoff}
    all_pairs = {(e["company_key"], e["track_id"]) for e in material
                 if e.get("company_key") and e.get("track_id")}
    report["left_truncation"] = {
        "first_origin": first_origin,
        "pairs_with_any_material_activity_by_first_origin": len(active_before),
        "distinct_pairs_ever_observed": len(all_pairs),
        "share_already_active_at_first_origin": (len(active_before) / len(all_pairs)
                                                  if all_pairs else None),
    }

    # --- graph scale at the primary origin
    snap = {}
    for origin in (panels["primary_H4q_qualifying"]["first_origin"],
                   panels["primary_H4q_qualifying"]["last_origin"]):
        t = date.fromisoformat(origin)
        hist = [e for e in material if e.get("company_key") and e.get("track_id")
                and e["day"] <= t and e["available"] <= t]
        from datetime import timedelta
        recent = [e for e in hist if e["day"] > t - timedelta(days=365)]
        companies = {e["company_key"] for e in recent}
        tracks = {e["track_id"] for e in recent}
        edges = {(e["company_key"], e["track_id"]) for e in recent}
        degrees = Counter(company for company, _ in edges)
        tdegrees = Counter(track for _, track in edges)
        snap[origin] = {
            "companies_active_12m": len(companies), "tracks_active_12m": len(tracks),
            "edges_12m": len(edges), "density": len(edges) / (len(companies) * len(tracks))
            if companies and tracks else None,
            "mean_company_degree": (sum(degrees.values()) / len(degrees) if degrees else None),
            "max_company_degree": max(degrees.values()) if degrees else None,
            "mean_track_degree": (sum(tdegrees.values()) / len(tdegrees) if tdegrees else None),
            "max_track_degree": max(tdegrees.values()) if tdegrees else None,
        }
    report["graph_scale"] = snap

    # --- feature uniqueness: are graph features re-expressions of B3 history?
    try:
        import numpy as np
        panel = build_entry_panel(events, entity_field="company_key", horizon_months=12,
                                  label_kind="qualifying", dataset_version="s028_g1")
        from s028_lib import SnapshotSeries
        series = SnapshotSeries(events, panel["cutoffs"])
        rows = []
        for row in panel["examples"]:
            features = dict(row["features"])
            features.update(series.features_for(row["cutoff"], row["company_key"], row["track_id"]))
            rows.append(features)
        matrix = {name: np.array([r[name] for r in rows], dtype=float) for name in G1_FEATURES}
        base = {name: np.array([r[name] for r in rows], dtype=float) for name in B3_FEATURES}
        novelty = {}
        for name, values in matrix.items():
            corrs = {other: (float(np.corrcoef(values, base[other])[0, 1])
                             if np.std(values) > 0 and np.std(base[other]) > 0 else 0.0)
                     for other in B3_FEATURES}
            top = sorted(corrs.items(), key=lambda kv: -abs(kv[1]))[:3]
            novelty[name] = {"max_abs_corr_with_B3": max(abs(c) for c in corrs.values()),
                             "top_correlated": [{"feature": k, "r": v} for k, v in top],
                             "std": float(np.std(values))}
        report["graph_feature_redundancy"] = {
            "method": "Pearson correlation of each G1 feature with each of the 16 B3 features",
            "n_rows": len(rows), "novelty": novelty,
            "max_over_features": max(v["max_abs_corr_with_B3"] for v in novelty.values()),
            "warning": ("correlation is not a leakage test; a feature can be uncorrelated and still "
                        "encode the same information non-linearly"),
        }
    except ImportError:  # pragma: no cover
        report["graph_feature_redundancy"] = {"error": "numpy unavailable"}

    write_json(OUT, report)
    print(json.dumps({k: report[k] for k in
                      ("event_counts", "coverage", "knowledge_clock")}, ensure_ascii=False, indent=2))
    print("\nFIDELITY SELF-CHECK:", "PASS" if report["fidelity_self_check"]["ok"] else "FAIL")
    for name, check in report["fidelity_self_check"]["checks"].items():
        print(f"  {name:16s} expected={check['expected']!r:>14} observed={check['observed']!r:>14} ok={check['ok']}")
    print("\nLANE COMPOSITION")
    for key, value in report["lane_composition"].items():
        print(f"  {key:45s} {value}")
    print("\nPANELS")
    for key, value in panels.items():
        print(f"  {key:32s} n={value['n_examples']:7d} pos={value['n_positives']:5d} "
              f"base={value['base_rate']:.5f} origins={value['origins']} "
              f"({value['first_origin']}..{value['last_origin']})")
    print("\nGRAPH SCALE")
    for origin, value in snap.items():
        print(f"  {origin}: {value}")
    print("\nLEFT TRUNCATION:", report["left_truncation"])
    print("\nFIRST-ENTRY CENSUS:", {k: v for k, v in report["first_qualifying_entry_census"].items()
                                    if k != "entries_by_year"})
    print("  entries_by_year:", report["first_qualifying_entry_census"]["entries_by_year"])
    if "novelty" in report.get("graph_feature_redundancy", {}):
        print("\nGRAPH FEATURE NOVELTY (max |r| with any B3 feature)")
        for name, value in sorted(report["graph_feature_redundancy"]["novelty"].items(),
                                  key=lambda kv: kv[1]["max_abs_corr_with_B3"], reverse=True):
            print(f"  {name:36s} max|r|={value['max_abs_corr_with_B3']:.3f} std={value['std']:.4f}")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
