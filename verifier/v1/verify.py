#!/usr/bin/env python3
"""Run the v1 acceptance checks and emit a machine-readable summary."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    test = subprocess.run(
        [sys.executable, "-m", "pytest"], cwd=ROOT, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    print(test.stdout)
    checks = {"legacy_and_new_tests": test.returncode == 0}
    experiment = ROOT / "experiments" / "reverse_rd_v1" / "metrics.json"
    if experiment.exists():
        payload = json.loads(experiment.read_text(encoding="utf-8"))
        checks["rolling_origins_at_least_4"] = len(payload.get("origins", [])) >= 4
        checks["holdout_present"] = bool(payload.get("holdout"))
        required = {"pr_auc", "brier", "ece", "false_positive_rate", "precision_at_k", "mean_lead_time_days"}
        checks["required_metrics"] = all(
            required.issubset((model.get("holdout_metrics") or {}).keys())
            for model in payload.get("models", [])
        )
        checks["real_data_provenance"] = bool((payload.get("data_provenance") or {}).get("retrieved_at"))
    else:
        checks["experiment_artifact"] = False
    forecast = ROOT / "experiments" / "reverse_rd_v1" / "forecasts.json"
    checks["forecast_artifact"] = forecast.exists()
    ok = all(checks.values())
    print(json.dumps({"version": "v1", "ok": ok, "checks": checks}, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
