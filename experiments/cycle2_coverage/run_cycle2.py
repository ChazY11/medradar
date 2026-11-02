"""Cycle 2: does widening the entity universe change measured entry predictability?

Pre-registered design: research/CYCLE2_DESIGN.md
Protocol:               research/PREDICTION_PROTOCOL.md

Two panels, ONE protocol:

  P1  curated corporate parents (company_key)          -- reproduces cycle 1
  P2  deterministic legal applicant entities (cohort)  -- new

Nothing else changes: same material-event rule, same 36-month dormancy, same
12-month label, same quarterly origins, same purge, same model, same
hyperparameters, same holdout windows, same metrics.

Usage:
    python experiments/cycle2_coverage/run_cycle2.py --db data/research.sqlite \
        --panel p2 --cohort-size 200 --holdouts 3
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from medradar.intelligence.evaluation.backtesting import run_backtest  # noqa: E402
from medradar.intelligence.features.research_features import (  # noqa: E402
    BASE_FEATURES,
    ENTRY_FEATURES,
)
from medradar.intelligence.universe import (  # noqa: E402
    DEFAULT_MAX_COHORT,
    DEFAULT_MIN_ACTIVE_YEARS,
    DEFAULT_MIN_MATERIAL_EVENTS,
    FOCUS_COMPANIES,
    build_universe,
    entity_key,
    normalise_applicant,
    select_cohort,
)
from experiments.cycle2_coverage.panel import (  # noqa: E402
    P1_DATASET_VERSION,
    P2_DATASET_VERSION,
    assign_entity,
    build_entry_panel,
    load_regulatory_events,
    write_json,
)

#: Feature specification shared by both panels. Financial features are excluded
#: because the entity cohort is not CIK-mapped; including them would compare a
#: panel with financial coverage against one without, confounding the design.
SPEC_NAME = "rd_plus_entry_history"
SPEC_FEATURES = list(BASE_FEATURES) + list(ENTRY_FEATURES)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def coverage_stats(panel: dict[str, Any]) -> dict[str, Any]:
    examples = panel["examples"]
    by_origin: dict[str, dict[str, int]] = {}
    for origin in panel["cutoffs"]:
        rows = [row for row in examples if row["cutoff"] == origin]
        by_origin[origin] = {"rows": len(rows),
                             "positives": sum(int(row["label"]) for row in rows)}
    return {
        "n_examples": len(examples),
        "n_positives": sum(int(row["label"]) for row in examples),
        "base_rate": (sum(int(row["label"]) for row in examples) / len(examples)
                      if examples else None),
        "origins": len(panel["cutoffs"]),
        "by_origin": by_origin,
        "candidates_by_origin": panel["candidates_by_origin"],
        "positives_by_origin": panel["positives_by_origin"],
        "entity_count": panel["entity_count"],
        "track_count": panel["track_count"],
        "observed_pair_count": panel["observed_pair_count"],
        "event_count": panel["event_count"],
        "coverage_start": panel["coverage_start"],
        "coverage_end": panel["coverage_end"],
        "skipped_pending_examples": panel["skipped_pending_examples"],
    }


def required_focus_entities(universe: list[dict[str, Any]]) -> dict[str, str]:
    """Single largest universe entity per mandated focus company.

    Deterministic: among entities whose normalised name contains every token of a
    focus alias (token containment, the same rule ``universe.resolve_normalised``
    uses), keep the one with the largest ``n_material``; ties broken by
    ``entity_key`` ascending. Returns ``{focus_key: entity_key}``.
    """
    chosen: dict[str, str] = {}
    for focus_key, focus in sorted(FOCUS_COMPANIES.items()):
        alias_tokens = [tuple(normalise_applicant(alias).split())
                        for alias in focus["aliases"]]
        alias_tokens = [tokens for tokens in alias_tokens if tokens]
        matches = []
        for record in universe:
            name_tokens = set(str(record["normalised_name"]).split())
            if any(all(token in name_tokens for token in tokens) for tokens in alias_tokens):
                matches.append(record)
        if matches:
            matches.sort(key=lambda record: (-int(record["n_material"]),
                                             -int(record["n_events"]),
                                             str(record["entity_key"])))
            chosen[focus_key] = str(matches[0]["entity_key"])
    return chosen


def build_cohort(universe: list[dict[str, Any]], *, cohort_size: int, min_material: int,
                 min_active_years: int) -> tuple[list[str], dict[str, str], dict[str, Any]]:
    """Ranked activity cohort with the mandated focus companies pinned in.

    Rule (deterministic, matches ``config/universe_v1.json``):
      1. rank eligible entities by (n_material desc, n_events desc, entity_key asc);
      2. take the first ``cohort_size``;
      3. if a mandated focus company's largest entity is missing, replace the
         lowest-ranked non-required entity.
    """
    ranked = select_cohort(universe, max_entities=cohort_size,
                           min_material_events=min_material,
                           min_active_years=min_active_years)
    required = required_focus_entities(universe)
    required_keys = set(required.values())
    cohort = list(ranked)
    missing = [key for key in sorted(required_keys) if key not in set(cohort)]
    replaced: list[str] = []
    for key in missing:
        # drop the lowest-ranked entity that is not itself required
        for index in range(len(cohort) - 1, -1, -1):
            if cohort[index] not in required_keys:
                replaced.append(cohort[index])
                cohort[index] = key
                break
    detail = {"required_focus_entity_keys": sorted(required_keys),
              "focus_to_entity": required,
              "entities_replaced_by_focus": sorted(replaced)}
    return cohort, required, detail


def build_p2(db_path: Path, *, cohort_size: int, min_material: int,
             min_active_years: int) -> tuple[dict[str, Any], dict[str, Any]]:
    events = load_regulatory_events(db_path)
    # Pin every curated/focus company's applicant strings so the universe record
    # is complete even for firms below the activity floor.
    pinned: list[str] = []
    for focus in FOCUS_COMPANIES.values():
        for alias in focus["aliases"]:
            normalised = normalise_applicant(alias)
            if normalised:
                pinned.append(normalised)
    universe = build_universe(events, min_events=2, pinned_normalised=pinned)
    cohort, _required, cohort_detail = build_cohort(
        universe, cohort_size=cohort_size, min_material=min_material,
        min_active_years=min_active_years)
    cohort_set = set(cohort)
    by_key = {record["entity_key"]: record for record in universe}

    assigned = assign_entity(events, normalise_applicant, entity_key)
    panel_events = [event for event in assigned if event["entity"] in cohort_set]
    panel = build_entry_panel(panel_events, entity_field="entity",
                              dataset_version=P2_DATASET_VERSION,
                              coverage_end_reference="2026-10-15")

    focus_rows = {}
    for key, focus in FOCUS_COMPANIES.items():
        matched = [record for record in universe
                   if any(alias in record["normalised_name"]
                          for alias in (normalise_applicant(a) for a in focus["aliases"]))]
        focus_rows[key] = {
            "display_name": focus["display_name"],
            "universe_entities": [{"entity_key": record["entity_key"],
                                   "display_name": record["display_name"],
                                   "n_material": record["n_material"],
                                   "in_cohort": record["entity_key"] in cohort_set}
                                  for record in matched],
        }

    artifact_check: dict[str, Any] = {"artifact": "config/universe_v1.json", "present": False}
    artifact = Path("config/universe_v1.json")
    if artifact.exists():
        try:
            payload = json.loads(artifact.read_text(encoding="utf-8"))
            artifact_keys = set(payload.get("cohort", {}).get("entity_keys", []))
            artifact_check.update({
                "present": True,
                "artifact_cohort_size": len(artifact_keys),
                "identical": artifact_keys == cohort_set,
                "only_in_artifact": sorted(artifact_keys - cohort_set)[:20],
                "only_computed": sorted(cohort_set - artifact_keys)[:20],
            })
        except (OSError, ValueError) as exc:  # pragma: no cover - defensive
            artifact_check["error"] = str(exc)

    detail = {
        "universe": {
            "entities_total": len(universe),
            "entities_with_material_ge_3": sum(1 for r in universe if r["n_material"] >= 3),
            "entities_with_material_ge_5": sum(1 for r in universe if r["n_material"] >= 5),
            "cohort_rule": (f"n_material>={min_material} AND active_years>={min_active_years}; "
                            f"rank by (n_material desc, n_events desc, entity_key asc); "
                            f"first {cohort_size}; then pin one entity per mandated focus company"),
            "cohort_size": len(cohort),
            "cohort_entity_keys": cohort,
            "cohort_focus": cohort_detail,
            "cohort_artifact_crosscheck": artifact_check,
            "material_rule_note": (
                "cohort eligibility uses the universe module's n_material (510k + original PMA, "
                "supplements excluded); panel labels use the frozen target rule (510k + PMA with "
                "empty/0/S0 supplement_number or PANEL TRACK supplement_type), which is a superset"),
            "top_cohort": [{"entity_key": key, "display_name": by_key[key]["display_name"],
                            "n_material": by_key[key]["n_material"],
                            "n_events": by_key[key]["n_events"],
                            "active_years": by_key[key]["active_years"],
                            "tracks": len(by_key[key]["tracks"])}
                           for key in cohort[:25]],
            "focus_companies": focus_rows,
            "events_in_cohort": len(panel_events),
            "events_total_material": len(events),
            "events_in_cohort_with_track": sum(1 for e in panel_events if e["track_id"]),
        },
        "panel": coverage_stats(panel),
    }
    return panel, detail


def build_p1(db_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    events = load_regulatory_events(db_path)
    panel = build_entry_panel(events, entity_field="company_key",
                              dataset_version=P1_DATASET_VERSION,
                              coverage_end_reference="2026-10-15")
    return panel, {"panel": coverage_stats(panel)}


def run_panel_backtest(panel: dict[str, Any], *, holdouts: int, experiment: str,
                       provenance: dict[str, Any]) -> dict[str, Any]:
    return run_backtest(
        panel["examples"], list(BASE_FEATURES), [],
        min_train_origins=3, horizon_months=12, holdouts=holdouts,
        specifications=[(SPEC_NAME,
                         "R&D history + entry-specific history, no financial features "
                         "(shared by both panels)", SPEC_FEATURES)],
        experiment=experiment, data_provenance=provenance)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/research.sqlite")
    parser.add_argument("--out", default="experiments/cycle2_coverage")
    parser.add_argument("--panel", choices=["p2", "p1", "both"], default="p2")
    parser.add_argument("--cohort-size", type=int, default=DEFAULT_MAX_COHORT)
    parser.add_argument("--min-material", type=int, default=DEFAULT_MIN_MATERIAL_EVENTS)
    parser.add_argument("--min-active-years", type=int, default=DEFAULT_MIN_ACTIVE_YEARS)
    parser.add_argument("--holdouts", type=int, default=3)
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()

    captured = {
        "generated_at_unix": int(time.time()),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "db": {"path": str(db_path), "sha256": sha256_file(db_path),
               "size_bytes": db_path.stat().st_size},
        "specification": {"name": SPEC_NAME, "features": SPEC_FEATURES,
                          "n_features": len(SPEC_FEATURES)},
        "protocol": {
            "dormancy_months": 36, "horizon_months": 12,
            "purge_rule": "cutoff + 12 months <= origin",
            "holdouts": args.holdouts,
            "model": "LogisticBaseline(epochs=180, learning_rate=0.15, l2=1.0)",
            "metric_primary": "pr_auc (average precision)",
            "entity_determinism": "normalise_applicant (no fuzzy matching)",
        },
        "timings": {},
    }

    if args.panel in ("p1", "both"):
        tick = time.time()
        panel_p1, detail_p1 = build_p1(db_path)
        captured["timings"]["build_p1_seconds"] = round(time.time() - tick, 1)
        write_json(out_dir / "panel_p1.json", detail_p1)
        print(f"P1: {panel_p1['n_examples']} examples, {panel_p1['n_positives']} positives")
        tick = time.time()
        backtest_p1 = run_panel_backtest(
            panel_p1, holdouts=args.holdouts, experiment="cycle2_p1_curated_parents",
            provenance={"panel": "P1 curated corporate parents (company_key)",
                        "entity_field": "company_key"})
        captured["timings"]["backtest_p1_seconds"] = round(time.time() - tick, 1)
        write_json(out_dir / "backtest_p1_same_spec.json", backtest_p1)
        print(f"P1 backtest done in {captured['timings']['backtest_p1_seconds']}s")

    if args.panel in ("p2", "both"):
        tick = time.time()
        panel_p2, detail_p2 = build_p2(db_path, cohort_size=args.cohort_size,
                                       min_material=args.min_material,
                                       min_active_years=args.min_active_years)
        captured["timings"]["build_p2_seconds"] = round(time.time() - tick, 1)
        write_json(out_dir / "panel_p2.json", detail_p2)
        print(f"P2: {panel_p2['n_examples']} examples, {panel_p2['n_positives']} positives, "
              f"{panel_p2['entity_count']} entities, {panel_p2['track_count']} tracks")
        print(f"    cohort {detail_p2['universe']['cohort_size']} of "
              f"{detail_p2['universe']['entities_total']} universe entities; "
              f"{detail_p2['universe']['events_in_cohort']}/"
              f"{detail_p2['universe']['events_total_material']} material events covered")
        tick = time.time()
        backtest_p2 = run_panel_backtest(
            panel_p2, holdouts=args.holdouts, experiment="cycle2_p2_legal_entities",
            provenance={"panel": "P2 deterministic legal applicant entities",
                        "entity_field": "entity",
                        "cohort_rule": detail_p2["universe"]["cohort_rule"]})
        captured["timings"]["backtest_p2_seconds"] = round(time.time() - tick, 1)
        write_json(out_dir / "backtest_p2.json", backtest_p2)
        print(f"P2 backtest done in {captured['timings']['backtest_p2_seconds']}s")

    captured["timings"]["total_seconds"] = round(time.time() - started, 1)
    write_json(out_dir / "run_config.json", captured)
    print(f"total {captured['timings']['total_seconds']}s -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
