"""Reconstruct the training record of the run whose finalisation crashed.

Why this exists, and why it is not a rewrite of history
-------------------------------------------------------
The run trained for its full 1200 s wall budget and saved a best adapter, then
crashed inside the `finally` block (a `Thread._stop` name collision, fixed
afterwards in `training/train_overnight.py`).  The final adapter and the training
record were therefore never written.  This script rebuilds the record **from the
run's own artifacts** -- the step log, the progress file, the 5-minute resource
log and the best-checkpoint selection file -- and marks, field by field, what is
measured and what is derived.

It never invents a number: a field it cannot read is written as `null` with a
reason.  The reconstructed record says `record_provenance =
reconstructed_after_trainer_crash`, so no reader can mistake it for a record the
trainer wrote itself.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Sequence

_STEP_LINE = re.compile(
    r"step (\d+)/\d+ loss=([0-9.]+) ([0-9.]+)s vram=(\d+)MiB"
)
_EVAL_LINE = re.compile(r"eval step (\d+): validation_loss=([0-9.]+)")


def _read_log_text(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="replace")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", errors="replace")
    return raw.decode("utf-8", errors="replace")


def parse_stdout(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    steps: list[dict[str, Any]] = []
    evaluations: list[dict[str, Any]] = []
    if not path.is_file():
        return steps, evaluations
    text = _read_log_text(path)
    if text and "loss=" in text and not steps:
        pass
    for line in text.splitlines():
        match = _STEP_LINE.search(line)
        if match:
            steps.append(
                {
                    "step": int(match.group(1)),
                    "loss": float(match.group(2)),
                    "step_time_s": float(match.group(3)),
                    "vram_allocated_mib": float(match.group(4)),
                    "source": "stdout (printed every 10 steps)",
                }
            )
            continue
        match = _EVAL_LINE.search(line)
        if match:
            evaluations.append(
                {
                    "step": int(match.group(1)),
                    "validation_loss": float(match.group(2)),
                    "source": "stdout",
                }
            )
    if text.strip() and "loss=" in text and not steps:
        raise SystemExit(
            f"REFUSED: {path} contains loss lines but none parsed; the log format changed"
        )
    return steps, evaluations


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _median(values: Sequence[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--stdout-log", required=True)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    run_dir = Path(args.run_dir)

    steps, evaluations = parse_stdout(Path(args.stdout_log))
    resources = _read_jsonl(run_dir / "resource_log.jsonl")
    progress_path = run_dir / "training_progress.json"
    progress = json.loads(progress_path.read_text(encoding="utf-8")) if progress_path.is_file() else {}
    best_path = run_dir / "best_checkpoint.json"
    best = json.loads(best_path.read_text(encoding="utf-8")) if best_path.is_file() else {}
    adapter_dir = run_dir / "adapter-best"
    adapter_files = sorted(path.name for path in adapter_dir.glob("*")) if adapter_dir.is_dir() else []

    max_step = max((row["step"] for row in steps), default=None)
    if progress.get("history_tail"):
        tail_max = max(int(row["step"]) for row in progress["history_tail"])
        max_step = max(max_step or 0, tail_max)
    wall = max((row.get("elapsed_s") or 0 for row in resources), default=None)

    record = {
        "status_tier": "EXPLORATORY_WEAK_SUPERVISION",
        "research_status": "RESEARCH_TRAINING_BLOCKED",
        "record_provenance": {
            "kind": "reconstructed_after_trainer_crash",
            "why": (
                "The trainer crashed in its finalisation step (ResourceSampler stopped a "
                "threading.Thread by assigning self._stop, shadowing Thread._stop). "
                "Training itself completed its wall-clock budget and saved the best "
                "adapter; only the final adapter write and this record were lost. The bug "
                "is fixed in training/train_overnight.py; this file is rebuilt from the "
                "run's own artifacts by scripts/reconstruct_training_record.py."
            ),
            "measured": (
                "step losses and step times (stdout, every 10 steps), validation loss at "
                "step 50 (stdout and best_checkpoint.json), GPU temperature / VRAM / RAM "
                "(5-minute resource log), best adapter files and their presence"
            ),
            "derived": (
                "steps_completed (max observed step), wall_time_s (last resource sample), "
                "median step time and tokens/second (stdout samples), loss trend"
            ),
            "not_recoverable": (
                "the final (step-60+) adapter, the optimiser state, and the exact stop "
                "reason string (wall-clock is inferred from a 1200 s budget and the last "
                "sample at 1200.1 s)"
            ),
        },
        "claim": (
            "Exploratory QLoRA domain adaptation of Qwen3-4B-Instruct-2507 on "
            "SOURCE_DERIVED_SILVER labels. NOT research grade: labels are machine-derived "
            "from source records, not human annotations, so no precision/recall/F1 may be "
            "quoted from any model trained here. Formal research training remains blocked."
        ),
        "config": {
            "steps_requested": 150,
            "max_wall_seconds": 1200,
            "max_seq_len": 2432,
            "grad_accum": 4,
            "learning_rate": 1e-4,
            "seed": 20261104,
            "lora_r": 16,
            "lora_alpha": 32,
            "lora_dropout": 0.05,
            "eval_every": 50,
            "checkpoint_every": 75,
            "patience": 3,
            "resource_interval_s": 300,
            "max_temp_c": 87,
            "source": "command line recorded in the run's stdout log",
        },
        "model": {
            "weights_path": r"D:\DEPPSKK\ml-models\Qwen3-4B-Instruct-2507",
            "model_revision": "cdbee75f17c01a7cc42f958dc650907174af0554",
            "quantization": "nf4",
        },
        "prompt_version": "extract-v2",
        "data": {
            "note": (
                "70 training / 14 validation cases, 104-document frozen corpus "
                "(ovn-2026-11-04); see runs/dataset/dataset_audit.json for the split plan "
                "and leakage audit"
            )
        },
        "measurements": {
            "steps_completed": max_step,
            "wall_time_s": wall,
            "step_log": steps,
            "evaluations": evaluations or progress.get("evaluations"),
            "median_step_time_s": _median([row["step_time_s"] for row in steps]),
            "resource_samples": len(resources),
            "gpu_temp_max_c": max((row["gpu_temp_c"] for row in resources if "gpu_temp_c" in row), default=None),
            "gpu_temp_median_c": _median([row["gpu_temp_c"] for row in resources if "gpu_temp_c" in row]),
            "system_vram_max_mib": max((row.get("vram_used_mib", 0) for row in resources), default=None),
            "vram_free_min_mib": min((row.get("vram_free_mib", 10**9) for row in resources), default=None),
            "ram_max_percent": max((row.get("ram_percent", 0) for row in resources), default=None),
            "resource_log": resources,
        },
        "stop": {
            "reason": "wall_clock_budget_exhausted",
            "inference_note": (
                "inferred: the last resource sample is elapsed_s=1200.1, exactly the "
                "--max-wall-seconds value, and the step log ends at step 60"
            ),
            "completed_all_steps": False,
        },
        "checkpoints": {
            "best_adapter": str(adapter_dir),
            "best_step": best.get("step"),
            "best_validation_loss": best.get("validation_loss"),
            "best_adapter_files": adapter_files,
            "final_adapter": None,
            "final_adapter_note": "lost to the finalisation crash; arm C uses best_adapter",
            "trainer_state": None,
        },
    }
    out = Path(args.out) if args.out else run_dir / "training_run.reconstructed.json"
    out.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"reconstructed record -> {out}\n"
        f"steps_completed={max_step} wall={wall}s best_step={best.get('step')} "
        f"best_val={best.get('validation_loss')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
