"""VRAM budget decisions: deterministic, testable, and honest about boundaries.

A 16 GB laptop GPU that is already running a desktop is not a 16 GB training
device.  The measured facts of *this* machine (16 GB VRAM, ~3.9 GB already used by
desktop applications before any model is loaded -- measured by the Team Lead) are
the reason the draft config's budgets sit below the card's nominal size rather
than at it.

This module contains **no measurement and no device query**.  It is the pure
decision function that a future training loop calls after *measuring* memory; the
measurement itself belongs to that loop (and its numbers must be recorded as
measured, never inferred here).

Boundary convention (deliberate, and tested at the exact thresholds)
--------------------------------------------------------------------
``projected = used_mb + reserved_mb`` is compared with ``>=``:

===========================  ========  =========================================
projected vs thresholds      action    rationale
===========================  ========  =========================================
``projected >= abort_at_mb``  abort     fail closed: reaching the abort threshold
                                        is already an abort, not "almost"
``projected >= warn_at_mb``   warn      log loudly, keep the session alive
otherwise                     continue
===========================  ========  =========================================

A negative ``used_mb`` or ``reserved_mb`` is a programmer error and raises
``ValueError``: silently clamping it to zero would mask a broken measurement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ACTION_CONTINUE = "continue"
ACTION_WARN = "warn"
ACTION_ABORT = "abort"

ACTIONS: tuple[str, ...] = (ACTION_CONTINUE, ACTION_WARN, ACTION_ABORT)


@dataclass(frozen=True)
class VramBudget:
    """Thresholds in mebibytes.  ``total_mb`` is the card's nominal size."""

    total_mb: int
    warn_at_mb: int
    abort_at_mb: int

    def __post_init__(self) -> None:
        for name in ("total_mb", "warn_at_mb", "abort_at_mb"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be an integer, got {type(value).__name__}")
        if self.total_mb <= 0:
            raise ValueError(f"total_mb must be positive, got {self.total_mb}")
        if not 0 < self.warn_at_mb < self.abort_at_mb <= self.total_mb:
            raise ValueError(
                "VRAM thresholds must satisfy 0 < warn_at_mb < abort_at_mb <= total_mb, got "
                f"warn={self.warn_at_mb}, abort={self.abort_at_mb}, total={self.total_mb}"
            )

    def decide(self, used_mb: int, reserved_mb: int = 0) -> "Decision":
        """Decide what to do for a *measured* ``used_mb`` plus a ``reserved_mb`` allocation."""
        for name, value in (("used_mb", used_mb), ("reserved_mb", reserved_mb)):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be an integer measurement, got {type(value).__name__}")
            if value < 0:
                raise ValueError(f"{name} must not be negative, got {value}")
        projected = used_mb + reserved_mb
        if projected >= self.abort_at_mb:
            action = ACTION_ABORT
            reason = (
                f"projected {projected} MB >= abort threshold {self.abort_at_mb} MB "
                f"(used {used_mb} MB + reserved {reserved_mb} MB)"
            )
        elif projected >= self.warn_at_mb:
            action = ACTION_WARN
            reason = (
                f"projected {projected} MB >= warn threshold {self.warn_at_mb} MB "
                f"(used {used_mb} MB + reserved {reserved_mb} MB); abort threshold is {self.abort_at_mb} MB"
            )
        else:
            action = ACTION_CONTINUE
            reason = (
                f"projected {projected} MB < warn threshold {self.warn_at_mb} MB "
                f"(used {used_mb} MB + reserved {reserved_mb} MB)"
            )
        return Decision(
            action=action,
            reason=reason,
            used_mb=used_mb,
            reserved_mb=reserved_mb,
            projected_mb=projected,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_mb": self.total_mb,
            "warn_at_mb": self.warn_at_mb,
            "abort_at_mb": self.abort_at_mb,
        }


@dataclass(frozen=True)
class Decision:
    """The outcome of one budget check, with the numbers that produced it."""

    action: str
    reason: str
    used_mb: int
    reserved_mb: int
    projected_mb: int

    def __post_init__(self) -> None:
        if self.action not in ACTIONS:
            raise ValueError(f"unknown VRAM action {self.action!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "used_mb": self.used_mb,
            "reserved_mb": self.reserved_mb,
            "projected_mb": self.projected_mb,
        }


def decide(budget: VramBudget, used_mb: int, reserved_mb: int = 0) -> Decision:
    """Module-level convenience wrapper around :meth:`VramBudget.decide`."""
    return budget.decide(used_mb=used_mb, reserved_mb=reserved_mb)


def budget_from_config(config: Any, *, total_mb: int = 16384) -> VramBudget:
    """Build a budget from a training config's declared ``vram_budget_mb``/``abort_at_vram_mb``.

    ``total_mb`` defaults to the *measured* 16 GB of the target laptop; passing a
    different card's size is a configuration change, not a code change.
    """
    return VramBudget(
        total_mb=total_mb,
        warn_at_mb=int(config.vram_budget_mb),
        abort_at_mb=int(config.abort_at_vram_mb),
    )


__all__ = [
    "ACTION_ABORT",
    "ACTION_CONTINUE",
    "ACTION_WARN",
    "ACTIONS",
    "Decision",
    "VramBudget",
    "budget_from_config",
    "decide",
]
