"""Adapter interface: one shape for the rule system, a local model and a remote API.

The benchmark must be able to compare:

* **A** the existing deterministic/rule pipeline,
* **B** an untuned small language model running locally,
* **C** a QLoRA-tuned version of the same model,

without any of the three leaking its own conventions into the scoring code.  The
adapter protocol is deliberately small: describe yourself, load (gated), turn one
document into one text response, report what it cost.

Rules for implementers
----------------------
1. **Never import a heavy library at module import time.**  ``transformers``,
   ``torch``, ``bitsandbytes`` and HTTP clients are imported inside ``load()``
   after the corresponding gate has been checked.
2. **Never download anything implicitly.**  A local adapter resolves weights from
   an explicitly configured path or an already-populated cache and must fail
   loudly if neither exists.
3. **Report only what you measured.**  ``tokens_*`` and ``peak_vram_mb`` are
   ``None`` when the backend cannot measure them; ``None`` means "not measured",
   never "zero".
4. **Determinism is a declared property.**  ``descriptor.deterministic`` is True
   only when the backend is reproducible given the same seed and inputs.

Prompt construction lives in ``prompting.py``; adapters receive an
:class:`ExtractionRequest` and are responsible only for turning it into a call.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from ..safety import GATE_MODEL_LOAD, GATE_NETWORK, GATE_REMOTE_API, require_gate

BACKENDS: tuple[str, ...] = ("rule_based", "hf_local", "openai_compat", "scripted")


class AdapterError(RuntimeError):
    """Base class for adapter failures that are *not* model-quality failures."""


class AdapterUnavailable(AdapterError):
    """The backend cannot run here (missing weights, wrong hardware, no key)."""


class AdapterGateClosed(AdapterError):
    """The run was refused because a safety gate is closed."""


@dataclass(frozen=True)
class Prompt:
    """A rendered prompt.  ``prompt_version`` is recorded in every run manifest."""

    system: str
    user: str
    prompt_version: str
    template_sha256: str | None = None


@dataclass(frozen=True)
class AdapterDescriptor:
    """Static, serialisable description of a backend.

    Everything that could differ between machines or model checkpoints is a
    *field*, not a constant in code: model id, revision, quantisation, device,
    context budget.  Swapping Qwen3-4B for a 1.5B model or for a remote
    comparison API is a configuration change, never a code edit.
    """

    adapter_id: str
    display_name: str
    backend: str
    model_id: str | None = None
    model_revision: str | None = None
    quantization: str | None = None
    device: str = "cpu"
    max_input_chars: int = 12_000
    max_new_tokens: int = 768
    prompt_version: str | None = None
    requires_network: bool = False
    requires_gpu: bool = False
    deterministic: bool = False
    load_gate: str | None = None
    enabled_by_default: bool = False
    notes: str = ""

    def __post_init__(self) -> None:
        if self.backend not in BACKENDS:
            raise ValueError(f"unknown backend {self.backend!r}")
        if not self.adapter_id:
            raise ValueError("adapter_id is required")
        if self.requires_network and self.load_gate is None:
            raise ValueError("a network adapter must declare load_gate")

    @property
    def gate(self) -> str | None:
        """The gate that must be open before this adapter may do anything costly."""
        if self.load_gate:
            return self.load_gate
        if self.backend == "openai_compat":
            return GATE_REMOTE_API
        if self.backend == "hf_local":
            return GATE_MODEL_LOAD
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "display_name": self.display_name,
            "backend": self.backend,
            "model_id": self.model_id,
            "model_revision": self.model_revision,
            "quantization": self.quantization,
            "device": self.device,
            "max_input_chars": self.max_input_chars,
            "max_new_tokens": self.max_new_tokens,
            "prompt_version": self.prompt_version,
            "requires_network": self.requires_network,
            "requires_gpu": self.requires_gpu,
            "deterministic": self.deterministic,
            "load_gate": self.gate,
            "enabled_by_default": self.enabled_by_default,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ExtractionRequest:
    """One document handed to an adapter."""

    doc_id: str
    text: str
    source_type: str
    company_hint: str | None = None
    prompt: Prompt | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AdapterResponse:
    """Raw response plus measured cost.  Unmeasured values stay ``None``."""

    text: str
    finish_reason: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    wall_time_s: float | None = None
    peak_vram_mb: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


class ModelAdapter(ABC):
    """Protocol every backend implements.  Loading is explicit and gated."""

    @property
    @abstractmethod
    def descriptor(self) -> AdapterDescriptor:
        ...

    @property
    @abstractmethod
    def is_loaded(self) -> bool:
        ...

    def check_gate(self, *, environ: Mapping[str, str] | None = None) -> None:
        gate = self.descriptor.gate
        if gate is None:
            return
        try:
            require_gate(gate, reason=self.descriptor.adapter_id, environ=environ)
        except Exception as exc:  # re-raised as an adapter-specific error
            raise AdapterGateClosed(
                f"{self.descriptor.adapter_id}: {exc}"
            ) from exc
        if self.descriptor.requires_network:
            require_gate(GATE_NETWORK, reason="network adapter", environ=environ)

    @abstractmethod
    def load(self) -> None:
        """Acquire the backend.  Must call :meth:`check_gate` first."""

    def unload(self) -> None:
        """Release the backend; safe to call when not loaded."""

    @abstractmethod
    def generate(self, request: ExtractionRequest) -> AdapterResponse:
        """Run one document.  Must not perform any implicit load."""

    def close(self) -> None:
        self.unload()

    @property
    def system(self) -> str:
        return self.descriptor.backend

    def describe(self) -> dict[str, Any]:
        payload = self.descriptor.to_dict()
        payload["loaded"] = self.is_loaded
        return payload

    def __enter__(self) -> "ModelAdapter":
        self.load()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


AdapterFactory = Callable[..., ModelAdapter]


class AdapterRegistry:
    """adapter_id -> factory.  Nothing is instantiated until requested."""

    def __init__(self) -> None:
        self._factories: dict[str, AdapterFactory] = {}
        self._descriptors: dict[str, AdapterDescriptor] = {}

    def register(self, descriptor: AdapterDescriptor, factory: AdapterFactory) -> None:
        if descriptor.adapter_id in self._factories:
            raise ValueError(f"adapter {descriptor.adapter_id!r} is already registered")
        self._factories[descriptor.adapter_id] = factory
        self._descriptors[descriptor.adapter_id] = descriptor

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))

    def default_ids(self) -> tuple[str, ...]:
        return tuple(
            key for key in self.ids() if self._descriptors[key].enabled_by_default
        )

    def descriptor(self, adapter_id: str) -> AdapterDescriptor:
        try:
            return self._descriptors[adapter_id]
        except KeyError as exc:
            raise AdapterUnavailable(
                f"unknown adapter {adapter_id!r}; registered: {list(self.ids())}"
            ) from exc

    def create(self, adapter_id: str, **kwargs: Any) -> ModelAdapter:
        try:
            factory = self._factories[adapter_id]
        except KeyError as exc:
            raise AdapterUnavailable(
                f"unknown adapter {adapter_id!r}; registered: {list(self.ids())}"
            ) from exc
        return factory(**kwargs)

    def describe_all(self) -> list[dict[str, Any]]:
        return [self._descriptors[key].to_dict() for key in self.ids()]


__all__ = [
    "BACKENDS",
    "AdapterError",
    "AdapterUnavailable",
    "AdapterGateClosed",
    "Prompt",
    "AdapterDescriptor",
    "ExtractionRequest",
    "AdapterResponse",
    "ModelAdapter",
    "AdapterFactory",
    "AdapterRegistry",
    "GATE_MODEL_LOAD",
    "GATE_NETWORK",
    "GATE_REMOTE_API",
]
