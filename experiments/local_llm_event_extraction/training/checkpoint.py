"""Checkpoint layout and resume planning -- with path safety as a first-class rule.

Layout (every path resolved under ``root``, never a caller-provided absolute path)::

    <root>/<run_id>/state.json      last completed step, rng state, timestamp
    <root>/<run_id>/adapter/        QLoRA adapter weights for that step
    <root>/<run_id>/optimizer/      paged optimiser state (if saved)

Why the paranoid path handling
------------------------------
Checkpoint roots are configuration, and configuration gets copied between
machines.  ``run_id="../../etc"`` must not be able to write anywhere.  Every
public function here therefore:

1. rejects a ``run_id`` that is not a single lower-case-ish path segment
   (``.``, ``..``, absolute paths, separators, drive letters, NUL bytes);
2. resolves the resulting path and requires ``is_relative_to(root)``;
3. raises :class:`PathEscapeError` (from :mod:`.runlog`) rather than clamping or
   "helpfully" rewriting the caller's path.

Nothing here resumes anything by itself: :func:`plan_resume` only *describes* what
a later phase would resume from, and returns ``None`` when there is no state.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .runlog import PathEscapeError

STATE_NAME = "state.json"
ADAPTER_DIR = "adapter"
OPTIMIZER_DIR = "optimizer"

_SEGMENT_FORBIDDEN = ("/", "\\", ":", "\x00")


class CheckpointError(RuntimeError):
    """Checkpoint state exists but is unusable (bad JSON, missing step, wrong type)."""


@dataclass(frozen=True)
class ResumePlan:
    """What a later phase would resume from.  Describes state; resumes nothing."""

    run_id: str
    latest_step: int
    state_path: str
    adapter_path: str
    rng_state: Mapping[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "latest_step": self.latest_step,
            "state_path": self.state_path,
            "adapter_path": self.adapter_path,
            "rng_state": dict(self.rng_state) if self.rng_state is not None else None,
        }


def _segment(value: Any, *, what: str) -> str:
    text = str(value).strip()
    if not text:
        raise PathEscapeError(f"{what} must be a non-empty path segment")
    if text in (".", ".."):
        raise PathEscapeError(f"{what} must not be {text!r}")
    if any(marker in text for marker in _SEGMENT_FORBIDDEN):
        raise PathEscapeError(f"{what} {text!r} must be a single path segment")
    return text


def _run_dir(root: str | Path, run_id: str) -> Path:
    root_path = Path(root).expanduser().resolve()
    segment = _segment(run_id, what="run_id")
    candidate = (root_path / segment).resolve()
    if not candidate.is_relative_to(root_path):
        raise PathEscapeError(f"run directory {str(candidate)!r} escapes root {str(root_path)!r}")
    return candidate


def plan_resume(root: str | Path, run_id: str) -> ResumePlan | None:
    """Return the resume plan for ``run_id``, or ``None`` when no state exists.

    ``adapter_path`` is reported even when the adapter directory is absent; the
    caller must check ``Path(plan.adapter_path).is_dir()`` before claiming a resume
    is possible.  That check lives with the future trainer, not with the planner.
    """
    run_dir = _run_dir(root, run_id)
    state_path = run_dir / STATE_NAME
    if not state_path.exists():
        return None
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CheckpointError(f"cannot read {str(state_path)!r}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CheckpointError(f"{str(state_path)!r} is not valid JSON: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise CheckpointError(f"{str(state_path)!r} must contain a JSON object")
    latest_step = payload.get("latest_step")
    if isinstance(latest_step, bool) or not isinstance(latest_step, int) or latest_step < 0:
        raise CheckpointError(
            f"{str(state_path)!r} has an unusable latest_step {latest_step!r} (expected a non-negative integer)"
        )
    rng_state = payload.get("rng_state")
    if rng_state is not None and not isinstance(rng_state, Mapping):
        raise CheckpointError(
            f"{str(state_path)!r} has an unusable rng_state ({type(rng_state).__name__}); expected an object or null"
        )
    adapter_path = run_dir / ADAPTER_DIR
    return ResumePlan(
        run_id=_segment(run_id, what="run_id"),
        latest_step=latest_step,
        state_path=str(state_path.resolve()),
        adapter_path=str(adapter_path.resolve()),
        rng_state=dict(rng_state) if rng_state is not None else None,
    )


def write_state(root: str | Path, run_id: str, payload: Mapping[str, Any]) -> Path:
    """Atomically write ``state.json`` for a run and return its path.

    The write is ``temp file + os.replace`` so a crash cannot leave a half-written
    state that a later ``plan_resume`` would misread as a completed step.
    """
    if not isinstance(payload, Mapping):
        raise CheckpointError(f"state payload must be a mapping, got {type(payload).__name__}")
    latest_step = payload.get("latest_step")
    if isinstance(latest_step, bool) or not isinstance(latest_step, int) or latest_step < 0:
        raise CheckpointError(
            f"payload.latest_step must be a non-negative integer, got {latest_step!r}"
        )
    run_dir = _run_dir(root, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    state_path = run_dir / STATE_NAME
    temp_path = run_dir / (STATE_NAME + ".tmp")
    try:
        temp_path.write_text(
            json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temp_path, state_path)
    except OSError as exc:
        raise CheckpointError(f"cannot write {str(state_path)!r}: {exc}") from exc
    return state_path


__all__ = [
    "ADAPTER_DIR",
    "OPTIMIZER_DIR",
    "STATE_NAME",
    "CheckpointError",
    "PathEscapeError",
    "ResumePlan",
    "plan_resume",
    "write_state",
]
