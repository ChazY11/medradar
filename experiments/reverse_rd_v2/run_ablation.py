#!/usr/bin/env python3
"""Regenerate one feature-group ablation cell of the reverse_rd_v2 experiment.

Each invocation evaluates exactly one (target, specification) cell with the shared
purged rolling-origin protocol (``holdouts=3`` by default) so that several cells can
run in parallel on a multi-core machine. Results are merged into
``experiments/reverse_rd_v2/ablation_metrics.json`` by ``merge_ablation.py``.

Targets
-------
* ``continuation`` (``reverse_rd_v1``): v1's already-active-pair target.
* ``entry`` (``first_entry_v1``): dormant -> active track-entry target. Its model
  inputs are the shared R&D features **plus the six entry-specific features**;
  specs A/B repeat the frozen Phase 1 configuration (shared features only) for
  comparison, and spec D is the corrected entry baseline.

Specifications
--------------
continuation: A rd_only, B +financial, C +market, D +publication,
              E all available (financial + market + publication).
entry:        A shared R&D only, B shared + financial,
              C shared + entry-specific, D shared + entry + financial,
              E D + market, F D + publication, G D + market + publication.

Procurement is excluded from historical gain claims (current snapshot is not
point-in-time usable) and patents are not evaluated (USPTO ODP needs an API key),
so the honest "all available" cell is financial + market + publication only.

Usage
-----
    python experiments/reverse_rd_v2/run_ablation.py --db data/medradar.sqlite \
        --target continuation --spec C --out .ablation/continuation_C.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from medradar.config import load_companies  # noqa: E402
from medradar.db import DB  # noqa: E402
from medradar.intelligence.evaluation.backtesting import (  # noqa: E402
    DEFAULT_HORIZON_MONTHS,
    PURGE_RULE,
    run_backtest,
)
from medradar.intelligence.features.market_features import (  # noqa: E402
    FEATURES as MARKET_FEATURES,
    attach_market_features,
)
from medradar.intelligence.features.publication_features import (  # noqa: E402
    PUBLICATION_FEATURES,
    attach_publication_features,
)
from medradar.intelligence.features.research_features import (  # noqa: E402
    BASE_FEATURES,
    FINANCIAL_FEATURES,
)
from medradar.intelligence.storage import IntelligenceStore  # noqa: E402
from medradar.util import read_json, utc_now_iso, write_json  # noqa: E402

DATASET = {"continuation": "reverse_rd_v1", "entry": "first_entry_v1"}


def _examples(store: IntelligenceStore, dataset_version: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in store.conn.execute(
            "SELECT * FROM forecast_examples WHERE dataset_version=? ORDER BY cutoff", (dataset_version,)):
        row = dict(raw)
        row["features"] = json.loads(row["features"])
        rows.append(row)
    return rows


def _config() -> dict[str, Any]:
    return read_json(ROOT / "experiments" / "reverse_rd_v2" / "config.json", {}) or {}


def specifications(target: str, config: dict[str, Any]) -> dict[str, tuple[str, list[str]]]:
    entry_config = config["targets"]["entry"]
    shared = list(BASE_FEATURES)
    financial = list(FINANCIAL_FEATURES)
    entry_specific = list(entry_config["features"]["entry_specific"])
    market = list(MARKET_FEATURES)
    publication = list(PUBLICATION_FEATURES)
    if target == "continuation":
        return {
            "A": ("A: R&D history only", shared),
            "B": ("B: A + consolidated SEC financials", shared + financial),
            "C": ("C: A + market (equity/benchmark) features", shared + market),
            "D": ("D: A + publication (OpenAlex) features", shared + publication),
            "E": ("E: A + financial + market + publication", shared + financial + market + publication),
        }
    return {
        "A": ("A: shared R&D history only (Phase 1 parity)", shared),
        "B": ("B: A + consolidated SEC financials (Phase 1 parity)", shared + financial),
        "C": ("C: A + entry-specific features", shared + entry_specific),
        "D": ("D: C + financial (corrected entry baseline)", shared + entry_specific + financial),
        "E": ("E: D + market features", shared + entry_specific + financial + market),
        "F": ("F: D + publication features", shared + entry_specific + financial + publication),
        "G": ("G: D + market + publication (all available sources)",
              shared + entry_specific + financial + market + publication),
    }


def run_cell(db: Path, target: str, spec: str, holdouts: int, horizon: int) -> dict[str, Any]:
    config = _config()
    specs = specifications(target, config)
    if spec not in specs:
        raise SystemExit(f"unknown spec {spec!r}; choose from {sorted(specs)}")
    name, features = specs[spec]
    dataset_version = DATASET[target]
    companies = [dict(row) for row in load_companies("device").all()]

    started = time.time()
    store = IntelligenceStore(DB(db))
    try:
        examples = _examples(store, dataset_version)
        if not examples:
            raise SystemExit(f"no {dataset_version} examples in {db}; run Phase 1 first")
        market_coverage = attach_market_features(store, examples, companies) if target in ("continuation", "entry") else {}
        attach_publication_features(store, examples)
        report = run_backtest(
            examples, features, [], min_train_origins=int(config.get("min_train_origins", 5)),
            horizon_months=horizon, holdouts=holdouts,
            specifications=[(f"{target}_{spec}", name, features)],
            experiment=f"reverse_rd_v2_{target}_{spec}")
    finally:
        store.close()
    cell = {
        "target": target,
        "dataset_version": dataset_version,
        "spec": spec,
        "spec_name": name,
        "features": features,
        "feature_group_sizes": {
            "total_features": len(features),
            "market_features": len([f for f in features if f in MARKET_FEATURES]),
            "publication_features": len([f for f in features if f in PUBLICATION_FEATURES]),
        },
        "market_coverage": market_coverage,
        "generated_at": utc_now_iso(),
        "purge_rule": PURGE_RULE,
        "holdouts": holdouts,
        "horizon_months": horizon,
        "runtime_seconds": round(time.time() - started, 1),
        "report": report,
    }
    return cell


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(ROOT / "data" / "medradar.sqlite"))
    parser.add_argument("--target", choices=("continuation", "entry"), required=True)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--holdouts", type=int, default=3)
    parser.add_argument("--horizon", type=int, default=DEFAULT_HORIZON_MONTHS)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    cell = run_cell(Path(args.db), args.target, args.spec, args.holdouts, args.horizon)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.out, cell)
    summary = {
        "target": cell["target"], "spec": cell["spec"], "features": len(cell["features"]),
        "holdout": cell["report"]["holdout"], "holdout_origins": cell["report"]["holdout_origins"],
        "model": [(m["name"], m["holdout_metrics"].get("pr_auc") if m["holdout_metrics"] else None)
                  for m in cell["report"]["models"]],
        "windows_ap": [window["model_metrics"][cell["report"]["models"][0]["name"]].get("pr_auc")
                       for window in cell["report"]["holdout_windows"]],
        "runtime_seconds": cell["runtime_seconds"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
