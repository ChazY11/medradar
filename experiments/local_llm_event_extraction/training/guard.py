"""Training-readiness assessment: the single place that says "not yet, and here is why".

Why a guard module exists
-------------------------
The most expensive accident this project can have is not a crash; it is a QLoRA
run that starts before the labels exist, on data that is partly AI pre-annotation,
with a model revision nobody pinned, and produces numbers that later get quoted as
a result.  Each of those is a *precondition*, not a bug, so each one is checked
here, named with a stable blocker code, and printed with a human explanation.

The rules (and why each exists)
-------------------------------
============================  ===============================================
blocker code                  what it means
============================  ===============================================
``GATE_CLOSED``               ``safety.gate_open("training")`` is false.  The
                              environment gate is the last line of defence and
                              it defaults closed; a test, a stray CLI call or an
                              import must never be enough to train.
``NO_EXPLICIT_FLAG``          The operator did not pass the explicit intent
                              flags.  Intent is never inferred.
``DATA_NOT_READY``            No dataset, no cases, cases whose label tier is
                              not research grade, or cases with no split.
                              AI pre-annotation is *not* human truth; training on
                              it would make the evaluation circular.
``SPLIT_TOO_SMALL``           Fewer than the pre-registered minimum cases in
                              train/validation/test.  A model tuned on 3
                              documents measures noise.
``SPLIT_LEAKAGE``             A leakage group (company / document family) appears
                              in more than one split, or a case has no group, so
                              leakage cannot be excluded.
``MODEL_NOT_PINNED``          The config has no concrete model revision (a
                              placeholder such as ``PENDING-A-PIN``, a floating
                              ref, or nothing at all).  Unpinned weights cannot
                              be reproduced.
``CHECKPOINT_ROOT_UNSAFE``    The checkpoint root is not an absolute path or
                              lies inside this repository.  Weights and optimiser
                              states are large binaries; they must not be able to
                              land in the working tree.
``DISK_INSUFFICIENT``         ``shutil.disk_usage`` on the injected checkpoint
                              root reports less free space than the pre-registered
                              minimum.  Checkpoints are written *during* a run;
                              running out mid-run wastes the whole session.
``VRAM_BUDGET_TOO_HIGH``      The config's own VRAM budget exceeds the machine's
                              allowed budget (default 14336 MB, leaving headroom
                              under the measured 16 GB ceiling).
``CONFIG_DISABLED``           The config is absent or ``enabled`` is false.  The
                              committed draft is disabled on purpose.
============================  ===============================================

Design notes
------------
* **Pure and offline.**  The only I/O is ``shutil.disk_usage`` on a caller-supplied
  path.  No model, no network, no database, no clock-dependent behaviour.
* **Everything injectable.**  ``environ`` and ``checkpoint_root`` are parameters,
  never globals, so every blocker is unit-testable on CPU in milliseconds.
* **Tri-state checks.**  ``checks[name]["ok"]`` is ``True`` (passed), ``False``
  (blocked) or ``None`` (not evaluated because an upstream input was missing).
  ``None`` never becomes a blocker, so one missing input does not masquerade as
  five failures.
* **Warnings do not block.**  Missing provenance (no hardware report, unverified
  peak-memory estimate) is logged so that an eventual run manifest records it;
  it must not be silently "fixed" by inventing a measurement.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from ..contracts import is_research_grade
from ..safety import ENV_TRAINING, GATE_TRAINING, gate_open
from .qlora_config import is_pinned

#: Repository root, used to refuse checkpoint roots inside the working tree.
#: ``guard.py`` sits at ``<repo>/experiments/local_llm_event_extraction/training/``.
REPO_ROOT = Path(__file__).resolve().parents[3]

# ------------------------------------------------------------------ blocker codes
CODE_GATE_CLOSED = "GATE_CLOSED"
CODE_NO_EXPLICIT_FLAG = "NO_EXPLICIT_FLAG"
CODE_DATA_NOT_READY = "DATA_NOT_READY"
CODE_SPLIT_TOO_SMALL = "SPLIT_TOO_SMALL"
CODE_SPLIT_LEAKAGE = "SPLIT_LEAKAGE"
CODE_MODEL_NOT_PINNED = "MODEL_NOT_PINNED"
CODE_CHECKPOINT_ROOT_UNSAFE = "CHECKPOINT_ROOT_UNSAFE"
CODE_DISK_INSUFFICIENT = "DISK_INSUFFICIENT"
CODE_VRAM_BUDGET_TOO_HIGH = "VRAM_BUDGET_TOO_HIGH"
CODE_CONFIG_DISABLED = "CONFIG_DISABLED"

#: Stable order: readiness output is deterministic, so a diff between two runs is
#: meaningful and a report can be compared field by field.
CHECKS: tuple[tuple[str, str], ...] = (
    ("environment_gate", CODE_GATE_CLOSED),
    ("explicit_intent", CODE_NO_EXPLICIT_FLAG),
    ("dataset", CODE_DATA_NOT_READY),
    ("split_sizes", CODE_SPLIT_TOO_SMALL),
    ("split_leakage", CODE_SPLIT_LEAKAGE),
    ("model_revision", CODE_MODEL_NOT_PINNED),
    ("checkpoint_root", CODE_CHECKPOINT_ROOT_UNSAFE),
    ("disk_space", CODE_DISK_INSUFFICIENT),
    ("vram_budget", CODE_VRAM_BUDGET_TOO_HIGH),
    ("config_enabled", CODE_CONFIG_DISABLED),
)

WARNING_PEAK_MEMORY_UNVERIFIED = "W_PEAK_MEMORY_UNVERIFIED"
WARNING_HARDWARE_REPORT_MISSING = "W_HARDWARE_REPORT_MISSING"
WARNING_LABELS_NOT_RESEARCH_GRADE = "W_LABELS_NOT_RESEARCH_GRADE"

_WARNING_ORDER: tuple[str, ...] = (
    WARNING_LABELS_NOT_RESEARCH_GRADE,
    WARNING_PEAK_MEMORY_UNVERIFIED,
    WARNING_HARDWARE_REPORT_MISSING,
)

#: Markers a config's ``notes`` may carry to declare that a value is *not measured*.
_ASSUMED_MARKERS = ("assumed", "estimated", "not measured", "unverified")
_MEASURED_MARKER = "measured"

_GIB = 1024**3


class TrainingRefused(RuntimeError):
    """Raised by :func:`require_ready`; carries the full readiness assessment."""

    def __init__(self, readiness: "TrainingReadiness") -> None:
        self.readiness = readiness
        blockers = ", ".join(readiness.blockers)
        super().__init__(f"training refused: {blockers or 'readiness did not pass'}")


@dataclass(frozen=True)
class TrainingReadiness:
    """Machine-readable verdict plus the evidence each check saw."""

    ready: bool
    blockers: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    checks: Mapping[str, dict] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "checks": {name: dict(entry) for name, entry in self.checks.items()},
        }


# ------------------------------------------------------------------ small helpers
def _entry(check: str, code: str, ok: bool | None, detail: str, evidence: Mapping[str, Any] | None = None) -> dict:
    return {
        "check": check,
        "blocker_code": code,
        "ok": ok,
        "detail": detail,
        "evidence": dict(evidence or {}),
    }


def _case_split_counts(dataset: Any) -> dict[str, int]:
    counts = {"train": 0, "validation": 0, "test": 0, "unassigned": 0}
    for case in getattr(dataset, "cases", ()):
        split = getattr(case, "split", "unassigned")
        counts[str(split)] = counts.get(str(split), 0) + 1
    return counts


def _groups_by_split(dataset: Any) -> dict[str, set[str]]:
    mapping: dict[str, set[str]] = {}
    for case in getattr(dataset, "cases", ()):
        split = str(getattr(case, "split", "unassigned"))
        mapping.setdefault(split, set()).add(str(getattr(case, "group", "")))
    return mapping


def _existing_ancestor(path: Path) -> Path | None:
    candidate = path
    while True:
        if candidate.exists():
            return candidate
        parent = candidate.parent
        if parent == candidate:
            return None
        candidate = parent


def _warnings_for_config(config: Any, *, require_human_labels: bool) -> tuple[str, ...]:
    found: list[str] = []
    if not require_human_labels:
        found.append(WARNING_LABELS_NOT_RESEARCH_GRADE)
    notes = getattr(config, "notes", ()) if config is not None else ()
    joined = " ".join(str(note) for note in (notes or ())).lower()
    if any(marker in joined for marker in _ASSUMED_MARKERS):
        found.append(WARNING_PEAK_MEMORY_UNVERIFIED)
    if _MEASURED_MARKER not in joined or "hardware" not in joined:
        found.append(WARNING_HARDWARE_REPORT_MISSING)
    return tuple(name for name in _WARNING_ORDER if name in found)


# ------------------------------------------------------------------- the checks
def _check_gate(environ: Mapping[str, str]) -> dict:
    open_ = gate_open(GATE_TRAINING, environ)
    raw = environ.get(ENV_TRAINING) if environ is not None else None
    detail = (
        f"training gate is open ({ENV_TRAINING}={raw!r})"
        if open_
        else (
            f"training gate is closed: {ENV_TRAINING} is not one of 1/true/yes/on "
            f"(raw value {raw!r}). Closed by default so a test, import or dry run cannot train."
        )
    )
    return _entry(
        "environment_gate",
        CODE_GATE_CLOSED,
        open_,
        detail,
        {"env_var": ENV_TRAINING, "raw_value": raw, "open": open_},
    )


def _check_explicit_flag(explicit_flag: bool) -> dict:
    ok = bool(explicit_flag)
    return _entry(
        "explicit_intent",
        CODE_NO_EXPLICIT_FLAG,
        ok,
        (
            "operator passed both explicit intent flags"
            if ok
            else "operator did not pass both explicit intent flags (--enable-training and "
            "--i-understand); intent is never inferred"
        ),
        {"explicit_flag": ok},
    )


def _check_dataset(dataset: Any, *, require_human_labels: bool) -> dict:
    if dataset is None:
        return _entry(
            "dataset",
            CODE_DATA_NOT_READY,
            False,
            "no dataset manifest supplied: there are no training cases to build from",
            {"cases": 0, "label_tiers": [], "require_human_labels": require_human_labels},
        )
    cases = tuple(getattr(dataset, "cases", ()))
    tiers = tuple(getattr(dataset, "label_tiers", ())) or tuple(
        sorted({str(getattr(case, "label_tier", "unlabelled")) for case in cases})
    )
    problems: list[str] = []
    if not cases:
        problems.append("the dataset contains no cases")
    if require_human_labels and not is_research_grade(tiers):
        problems.append(
            f"label tiers {list(tiers)} are not all research grade; AI pre-annotation is not human truth"
        )
    unassigned = [str(getattr(case, "case_id", "?")) for case in cases if str(getattr(case, "split", "")) == "unassigned"]
    if unassigned:
        problems.append(f"{len(unassigned)} case(s) have split='unassigned' (e.g. {unassigned[0]!r})")
    ok = not problems
    detail = (
        f"{len(cases)} case(s) across splits {_case_split_counts(dataset)}, tiers {list(tiers)}"
        if ok
        else "; ".join(problems)
    )
    return _entry(
        "dataset",
        CODE_DATA_NOT_READY,
        ok,
        detail,
        {
            "cases": len(cases),
            "label_tiers": list(tiers),
            "require_human_labels": require_human_labels,
        },
    )


def _check_split_sizes(
    dataset: Any,
    *,
    min_train_cases: int,
    min_validation_cases: int,
    min_test_cases: int,
) -> dict:
    if dataset is None:
        return _entry(
            "split_sizes",
            CODE_SPLIT_TOO_SMALL,
            None,
            "not evaluated: no dataset manifest supplied",
            {},
        )
    counts = _case_split_counts(dataset)
    required = {
        "train": min_train_cases,
        "validation": min_validation_cases,
        "test": min_test_cases,
    }
    short = {split: counts.get(split, 0) for split, minimum in required.items() if counts.get(split, 0) < minimum}
    ok = not short
    if ok:
        detail = "split sizes meet the pre-registered minimums: " + ", ".join(
            f"{split} {counts.get(split, 0)}>={required[split]}" for split in required
        )
    else:
        detail = "; ".join(
            f"{split} has {counts.get(split, 0)} case(s), pre-registered minimum is {required[split]}"
            for split in required
            if split in short
        )
        if counts.get("unassigned"):
            detail += f"; {counts['unassigned']} case(s) are unassigned"
    return _entry("split_sizes", CODE_SPLIT_TOO_SMALL, ok, detail, {"counts": counts, "required": required})


def _check_split_leakage(dataset: Any) -> dict:
    if dataset is None:
        return _entry(
            "split_leakage",
            CODE_SPLIT_LEAKAGE,
            None,
            "not evaluated: no dataset manifest supplied",
            {},
        )
    by_split = _groups_by_split(dataset)
    group_splits: dict[str, set[str]] = {}
    for split, groups in by_split.items():
        for group in groups:
            group_splits.setdefault(group, set()).add(split)
    crossers = {
        group: sorted(splits)
        for group, splits in group_splits.items()
        if group and len(splits) > 1
    }
    empty_groups = [str(getattr(case, "case_id", "?")) for case in getattr(dataset, "cases", ()) if not str(getattr(case, "group", "")).strip()]
    problems: list[str] = []
    if crossers:
        sample = ", ".join(f"{group!r} in {splits}" for group, splits in sorted(crossers.items())[:3])
        problems.append(
            f"{len(crossers)} leakage group(s) appear in more than one split ({sample}); "
            "splits are assigned by group, never by case"
        )
    if empty_groups:
        problems.append(
            f"{len(empty_groups)} case(s) have no leakage group (e.g. {empty_groups[0]!r}), "
            "so cross-split leakage cannot be excluded"
        )
    ok = not problems
    detail = (
        f"no leakage group crosses a split ({len(group_splits)} group(s) checked)"
        if ok
        else "; ".join(problems)
    )
    return _entry(
        "split_leakage",
        CODE_SPLIT_LEAKAGE,
        ok,
        detail,
        {"groups": len(group_splits), "crossing_groups": sorted(crossers)},
    )


def _check_model_pin(config: Any) -> dict:
    if config is None:
        return _entry(
            "model_revision",
            CODE_MODEL_NOT_PINNED,
            False,
            "no training config supplied, so there is no model revision to pin",
            {"revision": None},
        )
    revision = getattr(config, "revision", None)
    pinned = is_pinned(revision)
    return _entry(
        "model_revision",
        CODE_MODEL_NOT_PINNED,
        pinned,
        (
            f"model revision is pinned: {revision!r}"
            if pinned
            else f"model revision {revision!r} is not a concrete pin; a run must name immutable bytes"
        ),
        {"revision": revision, "pinned": pinned},
    )


def _check_checkpoint_root(checkpoint_root: str | Path | None) -> dict:
    if checkpoint_root is None:
        return _entry(
            "checkpoint_root",
            CODE_CHECKPOINT_ROOT_UNSAFE,
            False,
            "no checkpoint root supplied",
            {"path": None},
        )
    path = Path(checkpoint_root)
    resolved = path.expanduser().resolve()
    problems: list[str] = []
    if not path.is_absolute():
        problems.append("checkpoint root must be an absolute path")
    if resolved.is_relative_to(REPO_ROOT):
        problems.append(f"checkpoint root {str(resolved)!r} is inside the repository ({str(REPO_ROOT)!r})")
    ok = not problems
    return _entry(
        "checkpoint_root",
        CODE_CHECKPOINT_ROOT_UNSAFE,
        ok,
        (
            f"checkpoint root {str(resolved)!r} is absolute and outside the repository"
            if ok
            else "; ".join(problems)
        ),
        {"path": str(resolved), "absolute": path.is_absolute(), "inside_repository": resolved.is_relative_to(REPO_ROOT)},
    )


def _check_disk(checkpoint_root: str | Path | None, min_disk_gb: float) -> dict:
    if checkpoint_root is None:
        return _entry(
            "disk_space",
            CODE_DISK_INSUFFICIENT,
            None,
            "not evaluated: no checkpoint root supplied",
            {"required_gib": min_disk_gb},
        )
    path = Path(checkpoint_root)
    if not path.is_absolute():
        return _entry(
            "disk_space",
            CODE_DISK_INSUFFICIENT,
            None,
            "not evaluated: checkpoint root is not an absolute path",
            {"required_gib": min_disk_gb},
        )
    ancestor = _existing_ancestor(path.expanduser().resolve())
    if ancestor is None:
        return _entry(
            "disk_space",
            CODE_DISK_INSUFFICIENT,
            False,
            f"no existing ancestor of {str(path)!r} could be found, so free space cannot be measured",
            {"required_gib": min_disk_gb},
        )
    try:
        usage = shutil.disk_usage(ancestor)
    except OSError as exc:  # pragma: no cover - platform dependent
        return _entry(
            "disk_space",
            CODE_DISK_INSUFFICIENT,
            False,
            f"could not measure free space on {str(ancestor)!r}: {exc}",
            {"required_gib": min_disk_gb},
        )
    free_gib = usage.free / _GIB
    ok = free_gib >= min_disk_gb
    evidence = {
        "path": str(ancestor),
        "free_gib": round(free_gib, 2),
        "total_gib": round(usage.total / _GIB, 2),
        "required_gib": min_disk_gb,
    }
    return _entry(
        "disk_space",
        CODE_DISK_INSUFFICIENT,
        ok,
        (
            f"{free_gib:.2f} GiB free on {str(ancestor)!r} (minimum {min_disk_gb:.2f} GiB)"
            if ok
            else f"only {free_gib:.2f} GiB free on {str(ancestor)!r}; a run requires {min_disk_gb:.2f} GiB"
        ),
        evidence,
    )


def _check_vram_budget(config: Any, max_vram_budget_mb: int) -> dict:
    if config is None:
        return _entry(
            "vram_budget",
            CODE_VRAM_BUDGET_TOO_HIGH,
            None,
            "not evaluated: no training config supplied",
            {"max_vram_budget_mb": max_vram_budget_mb},
        )
    budget = getattr(config, "vram_budget_mb", None)
    if isinstance(budget, bool) or not isinstance(budget, int):
        return _entry(
            "vram_budget",
            CODE_VRAM_BUDGET_TOO_HIGH,
            False,
            f"config vram_budget_mb is not an integer ({budget!r})",
            {"max_vram_budget_mb": max_vram_budget_mb},
        )
    ok = budget <= max_vram_budget_mb
    return _entry(
        "vram_budget",
        CODE_VRAM_BUDGET_TOO_HIGH,
        ok,
        (
            f"config VRAM budget {budget} MB is within the allowed {max_vram_budget_mb} MB"
            if ok
            else f"config VRAM budget {budget} MB exceeds the allowed {max_vram_budget_mb} MB"
        ),
        {"config_budget_mb": budget, "max_vram_budget_mb": max_vram_budget_mb},
    )


def _check_config_enabled(config: Any) -> dict:
    if config is None:
        return _entry(
            "config_enabled",
            CODE_CONFIG_DISABLED,
            False,
            "no training config supplied",
            {"enabled": None},
        )
    enabled = bool(getattr(config, "enabled", False))
    return _entry(
        "config_enabled",
        CODE_CONFIG_DISABLED,
        enabled,
        (
            "the config is explicitly enabled"
            if enabled
            else "the config is a disabled draft; a draft must never be sufficient to train"
        ),
        {"enabled": enabled},
    )


def assess_readiness(
    *,
    dataset: Any = None,
    checkpoint_root: str | Path | None = None,
    config: Any = None,
    environ: Mapping[str, str] | None = None,
    explicit_flag: bool = False,
    require_human_labels: bool = True,
    min_train_cases: int = 48,
    min_validation_cases: int = 12,
    min_test_cases: int = 24,
    min_disk_gb: float = 20.0,
    max_vram_budget_mb: int = 14336,
) -> TrainingReadiness:
    """Assess whether a training run could be authorised.  Pure; never trains.

    The default minimums are the pre-registered thresholds: 48 train / 12
    validation / 24 test human-confirmed cases (84 total), 20 GiB free disk and a
    VRAM budget at most 14336 MB -- i.e. 2 GiB of headroom under the measured
    16 GB laptop ceiling.  They are parameters so a test can drive each blocker
    without touching hardware; changing them for a real run is a protocol
    amendment, not a tuning knob.
    """
    env = {} if environ is None else environ
    checks: dict[str, dict] = {
        "environment_gate": _check_gate(env),
        "explicit_intent": _check_explicit_flag(explicit_flag),
        "dataset": _check_dataset(dataset, require_human_labels=require_human_labels),
        "split_sizes": _check_split_sizes(
            dataset,
            min_train_cases=min_train_cases,
            min_validation_cases=min_validation_cases,
            min_test_cases=min_test_cases,
        ),
        "split_leakage": _check_split_leakage(dataset),
        "model_revision": _check_model_pin(config),
        "checkpoint_root": _check_checkpoint_root(checkpoint_root),
        "disk_space": _check_disk(checkpoint_root, min_disk_gb),
        "vram_budget": _check_vram_budget(config, max_vram_budget_mb),
        "config_enabled": _check_config_enabled(config),
    }

    blockers = tuple(code for name, code in CHECKS if checks[name]["ok"] is False)
    warnings = _warnings_for_config(config, require_human_labels=require_human_labels)
    return TrainingReadiness(
        ready=not blockers,
        blockers=blockers,
        warnings=warnings,
        checks=checks,
    )


def require_ready(readiness: TrainingReadiness) -> None:
    """The only sanctioned way to act on a readiness verdict: refuse, or proceed."""
    if not readiness.ready:
        raise TrainingRefused(readiness)


__all__ = [
    "CHECKS",
    "CODE_CHECKPOINT_ROOT_UNSAFE",
    "CODE_CONFIG_DISABLED",
    "CODE_DATA_NOT_READY",
    "CODE_DISK_INSUFFICIENT",
    "CODE_GATE_CLOSED",
    "CODE_MODEL_NOT_PINNED",
    "CODE_NO_EXPLICIT_FLAG",
    "CODE_SPLIT_LEAKAGE",
    "CODE_SPLIT_TOO_SMALL",
    "CODE_VRAM_BUDGET_TOO_HIGH",
    "REPO_ROOT",
    "WARNING_HARDWARE_REPORT_MISSING",
    "WARNING_LABELS_NOT_RESEARCH_GRADE",
    "WARNING_PEAK_MEMORY_UNVERIFIED",
    "TrainingReadiness",
    "TrainingRefused",
    "assess_readiness",
    "require_ready",
]
