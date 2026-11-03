"""``python -m experiments.local_llm_event_extraction.training.run_train`` -- refusal CLI.

What this command does
----------------------
It performs the *pre-flight* of a QLoRA run and then refuses.  In full::

    parse -> load config -> if the training gate is closed: print blockers JSON to
    stderr and exit 2 -> load dataset manifest -> assess readiness -> if not ready:
    print blockers JSON to stderr and exit 3 -> if ready: print the exact plan of
    what would be trained (base model + pinned revision, every config value, the
    estimated peak VRAM with its provenance, dataset sizes, output directories) and
    exit 4 with ``PHASE_GUARD: training is not executed in this phase``.

**Exit 4 is the deliberate boundary of this phase.**  It is not a bug, a TODO or a
placeholder for a missing code path: the assertion that a run *passed every gate*
is itself the deliverable, and the launcher that would consume the plan does not
exist yet.  A later phase replaces the exit-4 branch with the training launcher
**behind the same gates** (environment gate, explicit intent flags, readiness
assessment, phase-guard policy sign-off); it does not relax any of them.

Exit codes are part of the contract because scripts must branch on them:

====  =======================================================================
2     refused: no config could be loaded, or the environment training gate is
      closed (``MEDRADAR_LOCAL_LLM_ALLOW_TRAINING`` unset or not truthy).
3     refused: the gate is open but readiness is not satisfied (missing/weak
      labels, splits too small or leaking, unpinned revision, unsafe checkpoint
      root, insufficient disk, VRAM budget too high, disabled config).
4     the plan would have been executable but this phase does not execute
      training.  Reaching 4 with the committed draft is impossible on purpose:
      the draft is disabled and its revision is a declared placeholder.
====  =======================================================================

No model library is imported anywhere in this module or in anything it imports.
It reads JSON, measures free disk space, and writes two streams.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..safety import ENV_TRAINING, GATE_TRAINING, gate_open
from .checkpoint import ADAPTER_DIR, STATE_NAME
from .dataset_builder import DataNotReady, SFTBundle, build_sft_records, load_manifest
from .guard import TrainingReadiness, assess_readiness
from .qlora_config import ConfigDocument, ConfigError, load_document
from .runlog import DEFAULT_LOG_NAME

EXIT_GATE_CLOSED = 2
EXIT_NOT_READY = 3
EXIT_PHASE_GUARD = 4

PHASE_GUARD_MESSAGE = "PHASE_GUARD: training is not executed in this phase"

PROG = "python -m experiments.local_llm_event_extraction.training.run_train"

PROGRAM_DESCRIPTION = (
    "Assess training readiness and refuse. This command never trains, never loads a model "
    "and never downloads anything. Exit 2 = gate closed, 3 = not ready, 4 = plan printed "
    "and phase guard reached."
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=PROG, description=PROGRAM_DESCRIPTION)
    parser.add_argument(
        "--config",
        required=True,
        help="Path to a QLoRA JSON config (the committed draft lives in training/configs/).",
    )
    parser.add_argument(
        "--dataset-manifest",
        required=True,
        help="Path to the dataset manifest JSON that would be trained on.",
    )
    parser.add_argument(
        "--checkpoint-root",
        required=True,
        help="Absolute directory OUTSIDE this repository where checkpoints would be written.",
    )
    parser.add_argument(
        "--enable-training",
        action="store_true",
        help="First explicit intent flag. Without it readiness reports NO_EXPLICIT_FLAG.",
    )
    parser.add_argument(
        "--i-understand",
        action="store_true",
        help="Second explicit intent flag (this phase still refuses with exit 4).",
    )
    return parser


# ------------------------------------------------------------------------- reporting
def _write_json(stream: Any, payload: Mapping[str, Any]) -> None:
    stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    stream.flush()


def _readiness_payload(readiness: TrainingReadiness) -> dict[str, Any]:
    return {
        "ready": readiness.ready,
        "blockers": list(readiness.blockers),
        "warnings": list(readiness.warnings),
        "checks": {
            name: {
                "blocker_code": entry["blocker_code"],
                "ok": entry["ok"],
                "detail": entry["detail"],
                "evidence": entry["evidence"],
            }
            for name, entry in readiness.checks.items()
        },
    }


def _refuse_gate_closed(readiness: TrainingReadiness, stderr: Any) -> int:
    first = (
        "REFUSED (2): training gate is closed -- "
        f"{ENV_TRAINING} is not one of 1/true/yes/on"
    )
    stderr.write(first + "\n")
    _write_json(
        stderr,
        {
            "exit_code": EXIT_GATE_CLOSED,
            "decision": "REFUSED_GATE_CLOSED",
            "message": first,
            "blockers": list(readiness.blockers),
            "readiness": _readiness_payload(readiness),
        },
    )
    return EXIT_GATE_CLOSED


def _refuse_not_ready(readiness: TrainingReadiness, stderr: Any) -> int:
    first = "REFUSED (3): readiness blockers: " + ", ".join(readiness.blockers)
    stderr.write(first + "\n")
    _write_json(
        stderr,
        {
            "exit_code": EXIT_NOT_READY,
            "decision": "REFUSED_NOT_READY",
            "message": first,
            "blockers": list(readiness.blockers),
            "warnings": list(readiness.warnings),
            "readiness": _readiness_payload(readiness),
        },
    )
    return EXIT_NOT_READY


def _refuse_config(reason: str, stderr: Any) -> int:
    first = f"REFUSED (2): config unusable -- {reason}"
    stderr.write(first + "\n")
    _write_json(
        stderr,
        {
            "exit_code": EXIT_GATE_CLOSED,
            "decision": "REFUSED_CONFIG_INVALID",
            "message": reason,
            "blockers": ["CONFIG_INVALID"],
        },
    )
    return EXIT_GATE_CLOSED


def _refuse_dataset(reasons: Sequence[str], stderr: Any) -> int:
    first = "REFUSED (3): dataset manifest unusable -- " + (reasons[0] if reasons else "unknown reason")
    stderr.write(first + "\n")
    _write_json(
        stderr,
        {
            "exit_code": EXIT_NOT_READY,
            "decision": "REFUSED_DATA_NOT_READY",
            "message": first,
            "blockers": ["DATA_NOT_READY"],
            "reasons": list(reasons),
        },
    )
    return EXIT_NOT_READY


# --------------------------------------------------------------------------- the plan
def _estimated_peak(document: ConfigDocument) -> Mapping[str, Any]:
    notes = document.metadata.get("_notes")
    if isinstance(notes, Mapping):
        assumed = notes.get("assumed_or_estimated")
        if isinstance(assumed, Mapping) and isinstance(assumed.get("peak_process_vram_mb"), Mapping):
            return dict(assumed["peak_process_vram_mb"])
    return {
        "value": None,
        "provenance": "NOT MEASURED - the config declares no peak-memory estimate",
    }


def _measured_hardware(document: ConfigDocument) -> Mapping[str, Any]:
    notes = document.metadata.get("_notes")
    if isinstance(notes, Mapping) and isinstance(notes.get("measured_by_the_team_lead"), Mapping):
        return dict(notes["measured_by_the_team_lead"])
    return {"provenance": "no measured hardware values are recorded in this config"}


def _plan(
    *,
    config_document: ConfigDocument,
    manifest: Any,
    bundle: SFTBundle,
    readiness: TrainingReadiness,
    checkpoint_root: str,
    dataset_manifest_path: str,
) -> dict[str, Any]:
    root = Path(checkpoint_root).expanduser().resolve()
    config = config_document.config
    return {
        "phase_guard": PHASE_GUARD_MESSAGE,
        "exit_code": EXIT_PHASE_GUARD,
        "message": (
            "every gate and readiness check passed; the training launcher is deliberately absent "
            "in this phase, so the plan below is printed and the process exits 4 without training"
        ),
        "base_model": {
            "base_adapter_id": config.base_adapter_id,
            "model_id": config.model_id,
            "revision": config.revision,
            "quantization": config.quantization,
            "compute_dtype": config.compute_dtype,
            "provenance": "config values; revision must be a concrete pin for a real run",
        },
        "training_config": {
            "source_path": config_document.source_path,
            "sha256": config_document.sha256,
            "values": config.to_dict(),
        },
        "resources": {
            "vram_budget_mb": config.vram_budget_mb,
            "abort_at_vram_mb": config.abort_at_vram_mb,
            "estimated_peak_vram_mb": _estimated_peak(config_document),
            "measured_hardware": _measured_hardware(config_document),
            "measured_here": {
                "free_disk_gib": readiness.checks.get("disk_space", {}).get("evidence", {}).get("free_gib"),
                "disk_path_measured": readiness.checks.get("disk_space", {}).get("evidence", {}).get("path"),
                "peak_vram_mb": None,
                "peak_vram_note": "not measured: this command never loads a model",
            },
        },
        "dataset": {
            "manifest_path": str(Path(dataset_manifest_path).expanduser().resolve()),
            "name": bundle.manifest_name,
            "version": bundle.manifest_version,
            "label_tiers": list(bundle.label_tiers),
            "allowed_tiers": list(bundle.allowed_tiers),
            "counts": dict(bundle.counts),
            "rejected": dict(bundle.rejected),
            "bundle_sha256": bundle.sha256,
        },
        "output": {
            "checkpoint_root": str(root),
            "run_log": str(root / DEFAULT_LOG_NAME),
            "run_id_rule": "qlora-<seed>-<UTC timestamp at launch>",
            "state_file": f"{str(root)}/<run_id>/{STATE_NAME}",
            "adapter_dir": f"{str(root)}/<run_id>/{ADAPTER_DIR}",
            "note": "a later phase writes these; this command writes nothing to them",
        },
        "readiness": {
            "warnings": list(readiness.warnings),
            "checks": {name: entry["detail"] for name, entry in readiness.checks.items()},
        },
        "next_step": (
            "a later phase must implement the launcher behind these same gates and replace the exit-4 "
            "branch; it must also replace the ASSUMED peak-memory estimate with a measured dry run"
        ),
    }


# ----------------------------------------------------------------------------- main
def main(argv: Sequence[str] | None = None) -> int:
    """Run the pre-flight.  Returns 2, 3 or 4; never returns after training."""
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    environ = os.environ
    explicit_flag = bool(args.enable_training and args.i_understand)
    stderr = sys.stderr
    stdout = sys.stdout

    try:
        config_document = load_document(args.config)
    except (ConfigError, OSError) as exc:
        return _refuse_config(str(exc), stderr)
    config = config_document.config

    # The gate is checked before the dataset is read: a closed gate must not even
    # touch the label files.
    if not gate_open(GATE_TRAINING, environ):
        readiness = assess_readiness(
            config=config,
            checkpoint_root=args.checkpoint_root,
            environ=environ,
            explicit_flag=explicit_flag,
        )
        return _refuse_gate_closed(readiness, stderr)

    try:
        manifest = load_manifest(args.dataset_manifest)
    except DataNotReady as exc:
        return _refuse_dataset(exc.reasons, stderr)

    readiness = assess_readiness(
        dataset=manifest,
        config=config,
        checkpoint_root=args.checkpoint_root,
        environ=environ,
        explicit_flag=explicit_flag,
    )
    if not readiness.ready:
        return _refuse_not_ready(readiness, stderr)

    try:
        bundle = build_sft_records(manifest)
    except DataNotReady as exc:
        return _refuse_dataset(exc.reasons, stderr)

    plan = _plan(
        config_document=config_document,
        manifest=manifest,
        bundle=bundle,
        readiness=readiness,
        checkpoint_root=args.checkpoint_root,
        dataset_manifest_path=args.dataset_manifest,
    )
    stdout.write(PHASE_GUARD_MESSAGE + "\n")
    stdout.write(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    stdout.flush()
    return EXIT_PHASE_GUARD


if __name__ == "__main__":  # pragma: no cover - exercised through main() in tests
    sys.exit(main())
