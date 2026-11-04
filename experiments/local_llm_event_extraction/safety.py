"""Run gates: the experiment cannot load a model, download weights or train by accident.

Every heavyweight or network-touching capability in this package sits behind an
environment gate that defaults to **closed**.  The gates exist because a test run,
a stray CLI invocation or an import side effect must never start a 4B-parameter
model on a laptop that is also being used for other work.

Naming
------
``MEDRADAR_LOCAL_LLM_ALLOW_MODEL_LOAD``   allow loading any model weights
``MEDRADAR_LOCAL_LLM_ALLOW_TRAINING``     allow a (QLoRA) training run
``MEDRADAR_LOCAL_LLM_ALLOW_NETWORK``      allow outbound HTTP from this package
``MEDRADAR_LOCAL_LLM_ALLOW_REMOTE_API``   allow a remote comparison API call

A gate is open only for the literal values ``1``, ``true``, ``yes`` or ``on``
(case-insensitive).  Any other value — including absent — is closed.  This is the
opposite of the usual "presence means yes" convention on purpose: a typo in a
shell must fail closed.

The gates are *not* a security boundary against a determined operator; they are a
guard rail against an accidental one.
"""

from __future__ import annotations

import os
from typing import Mapping

ENV_MODEL_LOAD = "MEDRADAR_LOCAL_LLM_ALLOW_MODEL_LOAD"
ENV_TRAINING = "MEDRADAR_LOCAL_LLM_ALLOW_TRAINING"
ENV_NETWORK = "MEDRADAR_LOCAL_LLM_ALLOW_NETWORK"
ENV_REMOTE_API = "MEDRADAR_LOCAL_LLM_ALLOW_REMOTE_API"

GATE_MODEL_LOAD = "model_load"
GATE_TRAINING = "training"
GATE_NETWORK = "network"
GATE_REMOTE_API = "remote_api"

GATES: Mapping[str, str] = {
    GATE_MODEL_LOAD: ENV_MODEL_LOAD,
    GATE_TRAINING: ENV_TRAINING,
    GATE_NETWORK: ENV_NETWORK,
    GATE_REMOTE_API: ENV_REMOTE_API,
}

TRUTHY = frozenset({"1", "true", "yes", "on"})
FALSY = frozenset({"0", "false", "no", "off", ""})


class GateClosed(RuntimeError):
    """Raised when a capability was requested while its gate is closed."""

    def __init__(self, gate: str, message: str | None = None) -> None:
        self.gate = gate
        env_var = GATES.get(gate, gate)
        super().__init__(
            message
            or (
                f"{gate!r} is disabled by default. Set {env_var}=1 to enable it, "
                "and only in a session where that cost is intended."
            )
        )


def gate_open(gate: str, environ: Mapping[str, str] | None = None) -> bool:
    """True only when the gate's environment variable is explicitly truthy."""
    if gate not in GATES:
        raise KeyError(f"unknown gate {gate!r}; known gates: {sorted(GATES)}")
    env = os.environ if environ is None else environ
    return str(env.get(GATES[gate], "")).strip().lower() in TRUTHY


def require_gate(gate: str, *, reason: str = "", environ: Mapping[str, str] | None = None) -> None:
    """Raise :class:`GateClosed` unless the gate is open."""
    if not gate_open(gate, environ):
        env_var = GATES[gate]
        suffix = f" ({reason})" if reason else ""
        raise GateClosed(
            gate,
            f"{gate!r} requires {env_var}=1{suffix}. It is closed by default so that "
            "tests, imports and dry runs cannot start a model, download weights or train.",
        )


def gate_report(environ: Mapping[str, str] | None = None) -> dict[str, dict[str, object]]:
    """Machine-readable state of every gate (used by the env probe and manifests)."""
    env = os.environ if environ is None else environ
    report: dict[str, dict[str, object]] = {}
    for gate, env_var in GATES.items():
        raw = env.get(env_var)
        report[gate] = {
            "env_var": env_var,
            "raw_value": raw,
            "open": gate_open(gate, env),
        }
    return report


def all_gates_closed(environ: Mapping[str, str] | None = None) -> bool:
    """Used by the offline test suite to prove the default posture is inert."""
    env = os.environ if environ is None else environ
    return not any(gate_open(gate, env) for gate in GATES)
