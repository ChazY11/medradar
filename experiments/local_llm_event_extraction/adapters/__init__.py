"""Model backends.  See :mod:`experiments.local_llm_event_extraction.adapters.base`.

The registry is built from ``adapters/config/models.example.json`` (or a path /
environment supplied by the caller).  Two properties matter:

* **Nothing is instantiated until requested.**  A registry entry is a descriptor
  plus a factory; creating a registry cannot load a model or open a socket.
* **Heavy backends stay default-disabled.**  ``hf-qwen3-4b`` and
  ``remote-openai-compat`` are registered but ``enabled_by_default=False`` and
  their gates are closed, so a harness run records ``NOT_RUN`` with the gate
  reason instead of pretending an arm produced a score.

The shipped descriptors are:

=======================  ==============  =============  ============================
adapter_id               backend         enabled        load gate
=======================  ==============  =============  ============================
``rules-baseline``       rule_based      yes            none (offline)
``scripted-fixture``     scripted        yes            none (test double)
``hf-qwen3-4b``          hf_local        no             ``model_load`` (GPU)
``hf-qwen3-4b-qlora``    hf_local        no             ``model_load`` (GPU, PEFT)
``remote-openai-compat`` openai_compat   no             ``remote_api`` + ``network``
=======================  ==============  =============  ============================

The ``hf-qwen3-4b-qlora`` entry is arm C: the *same* adapter class as arm B, with a
different checkpoint (``peft_adapter_path``) and therefore a different descriptor,
never a code fork.  It is an example config entry; a real run pins it.

Heavy libraries are never imported here.  ``hf_local`` imports transformers/torch
inside ``load()`` after its gate is checked, so importing this package on a machine
without torch works and is covered by an offline test.
"""

from __future__ import annotations

from typing import Any, Mapping

from .base import (  # noqa: F401  (re-exported for convenience)
    AdapterDescriptor,
    AdapterError,
    AdapterFactory,
    AdapterGateClosed,
    AdapterRegistry,
    AdapterResponse,
    AdapterUnavailable,
    ExtractionRequest,
    ModelAdapter,
    Prompt,
)
from .config import (
    CONFIG_DIR,
    DEFAULT_MODELS_CONFIG,
    descriptor_from_entry,
    expand_env,  # noqa: F401  (documented helper for scripts)
    load_entries,
    models_config_path,
)
from .hf_local import HFLocalAdapter
from .mock import RefusingAdapter, ScriptedAdapter, ScriptedCall, scripted_descriptor
from .openai_compat import DEFAULT_API_KEY_ENV, RemoteOpenAIAdapter
from .rule_based import RULES_VERSION, RuleBasedAdapter, rules_descriptor


def _default_alias_map() -> Mapping[str, str]:
    """Synthetic-fixture roster aliases, as a best-effort convenience default.

    The rule adapter is decoupled from any roster type: it accepts a plain
    ``Mapping[str, str]``.  For the bundled synthetic fixtures the mapping lives
    with the dataset, so a caller who does not pass one still gets a runnable arm A
    on that dataset.  A real run passes the roster-derived mapping explicitly.
    """
    try:  # local import: adapters must not depend on the dataset package at import time
        from ..datasets.synthetic import ROSTER_ALIASES

        return dict(ROSTER_ALIASES)
    except Exception:  # pragma: no cover - dataset package unavailable in a stripped install
        return {}


def _default_scripted_responses() -> Mapping[str, str]:
    try:
        from ..datasets.synthetic import load_responses

        return load_responses()
    except Exception:  # pragma: no cover - dataset package unavailable in a stripped install
        return {}


def _rule_factory(descriptor: AdapterDescriptor, aliases: Mapping[str, str]) -> AdapterFactory:
    def factory(**kwargs: Any) -> RuleBasedAdapter:
        kwargs.setdefault("alias_map", aliases)
        return RuleBasedAdapter(descriptor, **kwargs)

    return factory


def _scripted_factory(
    descriptor: AdapterDescriptor, responses: Mapping[str, str]
) -> AdapterFactory:
    def factory(**kwargs: Any) -> ScriptedAdapter:
        kwargs.setdefault("responses", responses)
        return ScriptedAdapter(descriptor, **kwargs)

    return factory


def _hf_factory(descriptor: AdapterDescriptor, entry: Mapping[str, Any]) -> AdapterFactory:
    def factory(**kwargs: Any) -> HFLocalAdapter:
        kwargs.setdefault("weights_path", _clean(entry.get("weights_path")))
        kwargs.setdefault("cache_dir", _clean(entry.get("cache_dir")))
        kwargs.setdefault("peft_adapter_path", _clean(entry.get("peft_adapter_path")))
        kwargs.setdefault("seed", int(entry.get("seed", 0)))
        return HFLocalAdapter(descriptor, **kwargs)

    return factory


def _remote_factory(descriptor: AdapterDescriptor, entry: Mapping[str, Any]) -> AdapterFactory:
    def factory(**kwargs: Any) -> RemoteOpenAIAdapter:
        kwargs.setdefault("base_url", _clean(entry.get("base_url")))
        kwargs.setdefault("api_key_env", entry.get("api_key_env") or DEFAULT_API_KEY_ENV)
        kwargs.setdefault("price_per_1k_tokens_in_usd", entry.get("price_per_1k_tokens_in_usd"))
        kwargs.setdefault("price_per_1k_tokens_out_usd", entry.get("price_per_1k_tokens_out_usd"))
        kwargs.setdefault("max_retries", int(entry.get("max_retries", 0)))
        kwargs.setdefault("seed", int(entry.get("seed", 0)))
        return RemoteOpenAIAdapter(descriptor, **kwargs)

    return factory


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def build_descriptors(
    entries: tuple[Mapping[str, Any], ...] | None = None,
    *,
    config_path: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> tuple[AdapterDescriptor, ...]:
    """Descriptor objects from config, without instantiating any adapter."""
    if entries is None:
        entries = load_entries(config_path, environ=environ)
    return tuple(descriptor_from_entry(entry, environ=environ) for entry in entries)


def build_registry(
    alias_map: Mapping[str, str] | None = None,
    *,
    config_path: str | None = None,
    environ: Mapping[str, str] | None = None,
    scripted_responses: Mapping[str, str] | None = None,
) -> AdapterRegistry:
    """Build the adapter registry from configuration.

    Parameters
    ----------
    alias_map:
        Alias text -> canonical company id, injected into the rule baseline.  When
        omitted, the bundled synthetic-fixture aliases are used if available.
    config_path:
        Override the descriptor configuration file (default:
        ``adapters/config/models.example.json``).
    scripted_responses:
        Override the canned responses used by the ``scripted-fixture`` test double
        (default: the bundled ``datasets/fixtures/responses_v0.json`` if present).

    No adapter is instantiated here and nothing is loaded; a missing optional
    dependency cannot break importing or building the registry.
    """
    entries = load_entries(config_path, environ=environ)
    aliases = dict(alias_map) if alias_map is not None else dict(_default_alias_map())
    responses = (
        dict(scripted_responses)
        if scripted_responses is not None
        else dict(_default_scripted_responses())
    )
    registry = AdapterRegistry()
    for entry in entries:
        descriptor = descriptor_from_entry(entry, environ=environ)
        backend = descriptor.backend
        if backend == "rule_based":
            registry.register(descriptor, _rule_factory(descriptor, aliases))
        elif backend == "scripted":
            registry.register(descriptor, _scripted_factory(descriptor, responses))
        elif backend == "hf_local":
            registry.register(descriptor, _hf_factory(descriptor, entry))
        elif backend == "openai_compat":
            registry.register(descriptor, _remote_factory(descriptor, entry))
        else:  # pragma: no cover - descriptor_from_entry already rejects unknown backends
            raise ValueError(f"no factory for backend {backend!r}")
    return registry


__all__ = [
    "CONFIG_DIR",
    "DEFAULT_API_KEY_ENV",
    "DEFAULT_MODELS_CONFIG",
    "RULES_VERSION",
    "AdapterDescriptor",
    "AdapterError",
    "AdapterFactory",
    "AdapterGateClosed",
    "AdapterRegistry",
    "AdapterResponse",
    "AdapterUnavailable",
    "ExtractionRequest",
    "HFLocalAdapter",
    "ModelAdapter",
    "Prompt",
    "RefusingAdapter",
    "RemoteOpenAIAdapter",
    "RuleBasedAdapter",
    "ScriptedAdapter",
    "ScriptedCall",
    "build_descriptors",
    "build_registry",
    "descriptor_from_entry",
    "expand_env",
    "load_entries",
    "models_config_path",
    "rules_descriptor",
    "scripted_descriptor",
]
