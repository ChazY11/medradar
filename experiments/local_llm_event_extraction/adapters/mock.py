"""Two deliberately non-model adapters: a scripted replay and a refusal stub.

They exist so the benchmark harness can be tested *without* a model:

* :class:`ScriptedAdapter` replays a fixed ``doc_id -> response text`` mapping.
  It is fully deterministic, it records every call, and it reports no token
  counts (nothing was tokenised).  Harness tests use it to exercise parsing,
  scoring, the error taxonomy, resume and report writing end to end.
* :class:`RefusingAdapter` raises a chosen adapter error, either at ``load()`` or
  at ``generate()``, so gate/refusal paths can be tested directly.

Neither of these is a model and neither may be reported as an arm.  Their
descriptors carry that warning in ``notes``, and the synthetic-fixture banner on
the report applies to whatever they produce.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from .base import (
    AdapterDescriptor,
    AdapterError,
    AdapterResponse,
    AdapterUnavailable,
    ExtractionRequest,
    ModelAdapter,
)


def scripted_descriptor(
    adapter_id: str = "scripted-fixture",
    *,
    display_name: str = "Harness test double - scripted fixture replay",
    max_input_chars: int = 12_000,
    enabled_by_default: bool = True,
    notes: str = "Replays canned responses. NOT a model; output is NOT an empirical result.",
) -> AdapterDescriptor:
    return AdapterDescriptor(
        adapter_id=adapter_id,
        display_name=display_name,
        backend="scripted",
        model_id=None,
        model_revision=None,
        quantization=None,
        device="cpu",
        max_input_chars=max_input_chars,
        max_new_tokens=0,
        prompt_version=None,
        requires_network=False,
        requires_gpu=False,
        deterministic=True,
        load_gate=None,
        enabled_by_default=enabled_by_default,
        notes=notes,
    )


@dataclass(frozen=True)
class ScriptedCall:
    """One recorded call, so tests can prove what the adapter was asked to do."""

    doc_id: str
    source_type: str
    has_prompt: bool

    def to_dict(self) -> dict[str, Any]:
        return {"doc_id": self.doc_id, "source_type": self.source_type, "has_prompt": self.has_prompt}


class ScriptedAdapter(ModelAdapter):
    """Replay canned responses keyed by ``doc_id``; deterministic and call-recording."""

    def __init__(
        self,
        descriptor: AdapterDescriptor | None = None,
        responses: Mapping[str, str] | None = None,
        *,
        default_response: str | None = None,
        raise_on_missing: bool = True,
    ) -> None:
        self._descriptor = descriptor or scripted_descriptor()
        if self._descriptor.backend != "scripted":
            raise AdapterError("ScriptedAdapter requires a descriptor with backend='scripted'")
        self._responses = dict(responses or {})
        self._default_response = default_response
        self._raise_on_missing = raise_on_missing
        self._loaded = False
        self._calls: list[ScriptedCall] = []

    @property
    def descriptor(self) -> AdapterDescriptor:
        return self._descriptor

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def calls(self) -> tuple[ScriptedCall, ...]:
        return tuple(self._calls)

    @property
    def responses(self) -> Mapping[str, str]:
        return dict(self._responses)

    def load(self) -> None:
        # Nothing to load: the replay table is already in memory.  No gate applies
        # because no model, weights or network are involved.
        self._loaded = True

    def unload(self) -> None:
        self._loaded = False

    def generate(self, request: ExtractionRequest) -> AdapterResponse:
        if not self._loaded:
            raise AdapterUnavailable(
                f"{self._descriptor.adapter_id}: generate() called before load(); refusing implicit load"
            )
        self._calls.append(
            ScriptedCall(
                doc_id=request.doc_id,
                source_type=request.source_type,
                has_prompt=request.prompt is not None,
            )
        )
        started = time.perf_counter()
        if request.doc_id in self._responses:
            text = self._responses[request.doc_id]
        elif self._default_response is not None:
            text = self._default_response
        elif self._raise_on_missing:
            raise AdapterUnavailable(
                f"{self._descriptor.adapter_id}: no scripted response for doc {request.doc_id!r}"
            )
        else:
            text = ""
        elapsed = time.perf_counter() - started
        return AdapterResponse(
            text=text,
            finish_reason="scripted",
            tokens_in=None,  # nothing tokenised: not measured, not zero
            tokens_out=None,
            wall_time_s=elapsed,
            peak_vram_mb=None,
            metadata={"scripted": True, "response_chars": len(text)},
        )


class RefusingAdapter(ModelAdapter):
    """An adapter that always fails with a chosen error, for gate/refusal tests."""

    def __init__(
        self,
        descriptor: AdapterDescriptor | None = None,
        error: AdapterError | None = None,
        *,
        raise_on_load: bool = False,
    ) -> None:
        self._descriptor = descriptor or scripted_descriptor(
            adapter_id="refusing-stub",
            display_name="Refusal test stub",
            enabled_by_default=False,
            notes="Always raises a chosen adapter error. NOT a model.",
        )
        self._error = error or AdapterUnavailable(f"{self._descriptor.adapter_id}: refusing by configuration")
        self._raise_on_load = raise_on_load
        self._loaded = False

    @property
    def descriptor(self) -> AdapterDescriptor:
        return self._descriptor

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def error(self) -> AdapterError:
        return self._error

    def load(self) -> None:
        if self._raise_on_load:
            raise self._error
        self._loaded = True

    def unload(self) -> None:
        self._loaded = False

    def generate(self, request: ExtractionRequest) -> AdapterResponse:
        raise self._error


__all__ = [
    "RefusingAdapter",
    "ScriptedAdapter",
    "ScriptedCall",
    "scripted_descriptor",
]
