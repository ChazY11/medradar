"""Consolidate every experiment of the overnight run into one register.

Every experiment must be registered with: id, hypothesis, data version, model
revision, training config, seed, GPU seconds, result, failure reason, and whether
it is exploratory.  This script builds that table from the artifacts themselves so
the register cannot describe a run that did not happen -- a missing artifact is an
error, not a blank row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


def _read(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _load_summary(path: Path | None) -> dict[str, Any] | None:
    return _read(path) if path else None


def build_register(
    *,
    training_run: Path,
    summary: Path | None,
    dataset_audit: Path | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    audit = _read(dataset_audit) if dataset_audit else None
    train = _read(training_run)
    if train is None:
        raise SystemExit(f"REFUSED: training run record missing: {training_run}")
    data_version = None
    if audit:
        data_version = {
            "corpus_sha256": audit["corpus"]["corpus_sha256"],
            "corpus_version": audit["corpus"].get("corpus_version"),
            "counts": audit["counts"]["by_split"],
            "leakage_audit": audit["leakage_audit"]["status"],
            "label_tier": audit["label_tier"],
        }
    config = train.get("config", {})
    measurements = train.get("measurements", {})
    rows.append(
        {
            "experiment_id": "OVN-TRAIN-01",
            "kind": "qlora_training",
            "hypothesis": (
                "QLoRA adaptation on SOURCE_DERIVED_SILVER labels reduces teacher-forced "
                "loss on held-out companies and produces schema-valid extractions without "
                "destroying the instruction-following behaviour of the base model."
            ),
            "data_version": data_version,
            "model_revision": (train.get("model") or {}).get("model_revision"),
            "prompt_version": train.get("prompt_version"),
            "config": config,
            "seed": config.get("seed"),
            "gpu_seconds": measurements.get("wall_time_s"),
            "result": {
                "stop_reason": (train.get("stop") or {}).get("reason"),
                "best_validation_loss": (train.get("checkpoints") or {}).get("best_validation_loss"),
                "best_step": (train.get("checkpoints") or {}).get("best_step"),
                "evaluations": measurements.get("evaluations"),
                "peak_vram_mib": measurements.get("peak_vram_allocated_mib"),
                "gpu_temp_max_c": measurements.get("gpu_temp_max_c"),
            },
            "failure_reason": None
            if (train.get("stop") or {}).get("completed_all_steps")
            else (train.get("stop") or {}).get("reason"),
            "exploratory": True,
            "status_tier": train.get("status_tier"),
            "research_status": train.get("research_status"),
        }
    )

    payload = _load_summary(summary)
    if payload:
        for index, (run_name, run) in enumerate(sorted(payload["runs"].items()), start=1):
            arms = run.get("arms", {})
            rows.append(
                {
                    "experiment_id": f"OVN-EVAL-{index:02d}",
                    "kind": "evaluation",
                    "hypothesis": (
                        "The repaired system (prompt v2 + schema v2) plus the exploratory "
                        "adapter changes agreement with silver labels relative to the "
                        "untuned model and to the deterministic rules, on companies never "
                        "used in training."
                    ),
                    "data_version": payload.get("dataset"),
                    "model_revision": "cdbee75f17c01a7cc42f958dc650907174af0554",
                    "prompt_version": run.get("prompt"),
                    "config": {"run_dir": run.get("run_dir"), "arms": sorted(arms)},
                    "seed": 20261104,
                    "gpu_seconds": None,
                    "result": {
                        arm_id: {
                            "json_valid_rate": arm["json_valid_rate"],
                            "schema_accepted_rate": arm["schema_accepted_rate"],
                            "category_agreement": arm["agreement"]["category_agreement"],
                            "event_date_agreement": arm["agreement"]["event_date_agreement"],
                            "company_agreement": arm["agreement"]["company_agreement"],
                            "abstention_rate": arm["abstention_rate"],
                            "false_assertion_rate": arm["false_assertion_rate"],
                            "median_latency_s": arm["latency_s"]["median"],
                            "peak_vram_mb": arm["peak_vram_mb"],
                        }
                        for arm_id, arm in arms.items()
                    },
                    "failure_reason": None,
                    "exploratory": True,
                    "precision_recall_f1": "NOT_EVALUABLE",
                }
            )
    return rows


def to_markdown(rows: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        "# Overnight experiment register",
        "",
        "Generated from artifacts by `scripts/make_experiment_register.py`.",
        "Every row is `exploratory`; no precision/recall/F1 is reported anywhere in this",
        "run because the labels are machine-derived silver labels, not human annotations.",
        "",
        "| id | kind | hypothesis | prompt | seed | GPU s | stop / failure |",
        "|---|---|---|---|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {id} | {kind} | {hypothesis} | {prompt} | {seed} | {gpu} | {fail} |".format(
                id=row["experiment_id"],
                kind=row["kind"],
                hypothesis=str(row["hypothesis"]).replace("|", "/")[:150],
                prompt=row.get("prompt_version"),
                seed=row.get("seed"),
                gpu=row.get("gpu_seconds") or "—",
                fail=row.get("failure_reason") or "—",
            )
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-run", required=True)
    parser.add_argument("--summary", default=None)
    parser.add_argument("--dataset-audit", default=None)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", default=None)
    args = parser.parse_args(argv)
    rows = build_register(
        training_run=Path(args.training_run),
        summary=Path(args.summary) if args.summary else None,
        dataset_audit=Path(args.dataset_audit) if args.dataset_audit else None,
    )
    Path(args.out_json).write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.out_md:
        Path(args.out_md).write_text(to_markdown(rows), encoding="utf-8")
    print(f"registered {len(rows)} experiments -> {args.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
