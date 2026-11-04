"""Read adapter descriptors from a JSON configuration file, never from code.

The harness must be usable on a different machine with a different checkpoint or
remote endpoint without editing Python.  Everything that varies by machine or by
model lives in ``models.example.json``: model id, revision, quantisation, device,
context budget, weights directory, cache directory, endpoint, key variable, price.

Environment expansion
---------------------
Any string value in the JSON may reference an environment variable:

``${NAME}``            -> the variable's value, or ``""`` when unset
``${NAME:-default}``   -> the variable's value, or ``default`` when unset/empty

That is the only mechanism by which a machine path enters the harness.  A missing
weights directory therefore becomes ``None`` and the local adapter later raises
``AdapterUnavailable`` instead of downloading anything.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

from .. import base as _base
from ...prompting import PROMPT_VERSION
from ...schema import ContractError
from ...safety import GATE_MODEL_LOAD, GATE_REMOTE_API

CONFIG_DIR = Path(__file__).resolve().parent
DEFAULT_MODELS_CONFIG = CONFIG_DIR / "models.example.json"

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")

_BACKEND_WITH_PROMPT = frozenset({"hf_local", "openai_compat"})


def expand_env(value: Any, environ: Mapping[str, str] | None = None) -> Any:
    """Recursively expand ``${NAME}`` / ``${NAME:-default}`` in strings and lists."""
    env = os.environ if environ is None else environ
    if isinstance(value, str):
        def _replace(match: re.Match[str]) -> str:
            name = match.group(1)
            default = match.group(2)
            current = str(env.get(name, "")).strip()
            if current:
                return current
            return default if default is not None else ""

        return _ENV_PATTERN.sub(_replace, value)
    if isinstance(value, list):
        return [expand_env(item, env) for item in value]
    if isinstance(value, dict):
        return {key: expand_env(item, env) for key, item in value.items()}
    return value


def _env_or_none(value: Any, environ: Mapping[str, str] | None) -> str | None:
    expanded = expand_env(value, environ) if value is not None else None
    if expanded is None:
        return None
    expanded = str(expanded).strip()
    return expanded or None


def load_config(
    path: str | Path | None = None, *, environ: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """Load and environment-expand the adapter configuration file."""
    config_path = Path(path) if path is not None else DEFAULT_MODELS_CONFIG
    try:
        raw = config_path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - defensive
        raise ContractError(f"cannot read adapter config {config_path}: {exc}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ContractError(f"adapter config is not valid JSON ({config_path}): {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("adapters"), list):
        raise ContractError("adapter config must be an object with an 'adapters' list")
    expanded = expand_env(payload, environ)
    assert isinstance(expanded, dict)
    return expanded


def load_entries(
    path: str | Path | None = None, *, environ: Mapping[str, str] | None = None
) -> tuple[dict[str, Any], ...]:
    """Expanded adapter entries, in file order."""
    payload = load_config(path, environ=environ)
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, entry in enumerate(payload["adapters"]):
        if not isinstance(entry, dict):
            raise ContractError(f"adapters[{index}] must be an object")
        adapter_id = entry.get("adapter_id")
        if not adapter_id:
            raise ContractError(f"adapters[{index}] is missing 'adapter_id'")
        if adapter_id in seen:
            raise ContractError(f"duplicate adapter_id {adapter_id!r}")
        seen.add(adapter_id)
        entries.append(entry)
    return tuple(entries)


def descriptor_from_entry(
    entry: Mapping[str, Any],
    *,
    prompt_version: str = PROMPT_VERSION,
    environ: Mapping[str, str] | None = None,
) -> _base.AdapterDescriptor:
    """Turn one JSON entry into a frozen :class:`AdapterDescriptor`.

    Defaults are derived from the backend, never from a checkpoint name: a model
    id may only come from the entry (which, in the shipped example, comes from an
    environment variable for the remote arm).
    """
    backend = entry.get("backend")
    if backend not in _base.BACKENDS:
        raise ContractError(
            f"adapter {entry.get('adapter_id')!r} has unknown backend {backend!r}; "
            f"known backends: {list(_base.BACKENDS)}"
        )
    if backend == "openai_compat" and not entry.get("load_gate"):
        load_gate: str | None = GATE_REMOTE_API
    elif backend == "hf_local" and not entry.get("load_gate"):
        load_gate = GATE_MODEL_LOAD
    else:
        load_gate = entry.get("load_gate") or None

    if load_gate is not None:
        from ...safety import GATES

        if load_gate not in GATES:
            raise ContractError(f"unknown load_gate {load_gate!r} for adapter {entry.get('adapter_id')!r}")

    requires_network = bool(entry.get("requires_network", backend == "openai_compat"))
    requires_gpu = bool(entry.get("requires_gpu", backend == "hf_local"))
    if requires_network and load_gate is None:
        raise ContractError(
            f"network adapter {entry.get('adapter_id')!r} must declare load_gate"
        )

    temperature = entry.get("temperature", 0 if backend in _BACKEND_WITH_PROMPT else None)
    if "deterministic" in entry:
        deterministic = bool(entry["deterministic"])
    elif backend in ("rule_based", "scripted"):
        deterministic = True
    elif backend == "hf_local":
        # Declared reproducible only for greedy decoding (temperature 0).
        deterministic = temperature is not None and float(temperature) == 0.0
    else:
        # A hosted endpoint is not ours to reproduce: server-side nondeterminism,
        # hidden model revisions and rate-shaping mean no determinism claim.
        deterministic = False

    entry_prompt = entry.get("prompt_version")
    if entry_prompt is not None:
        resolved_prompt = str(entry_prompt)
    elif backend in _BACKEND_WITH_PROMPT:
        resolved_prompt = prompt_version
    else:
        resolved_prompt = None

    device = str(entry.get("device") or "cpu")
    max_input_chars = int(entry.get("max_input_chars", 12_000))
    max_new_tokens = int(entry.get("max_new_tokens", 768 if backend in _BACKEND_WITH_PROMPT else 0))

    return _base.AdapterDescriptor(
        adapter_id=str(entry["adapter_id"]),
        display_name=str(entry.get("display_name") or entry["adapter_id"]),
        backend=str(backend),
        model_id=_env_or_none(entry.get("model_id"), environ),
        model_revision=_env_or_none(entry.get("revision"), environ),
        quantization=_env_or_none(entry.get("quantization"), environ),
        device=device,
        max_input_chars=max_input_chars,
        max_new_tokens=max_new_tokens,
        prompt_version=resolved_prompt,
        requires_network=requires_network,
        requires_gpu=requires_gpu,
        deterministic=deterministic,
        load_gate=load_gate,
        enabled_by_default=bool(entry.get("enabled_by_default", False)),
        notes=str(entry.get("notes") or ""),
    )


def models_config_path() -> Path:
    """Where the shipped example configuration lives."""
    return DEFAULT_MODELS_CONFIG


__all__ = [
    "CONFIG_DIR",
    "DEFAULT_MODELS_CONFIG",
    "descriptor_from_entry",
    "expand_env",
    "load_config",
    "load_entries",
    "models_config_path",
]
