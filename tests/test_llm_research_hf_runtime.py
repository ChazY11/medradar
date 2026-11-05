"""Offline tests for the real-model adapter path: pin, chat template, measurement.

Nothing here loads a model, imports torch, or touches a GPU.  Each test covers a
defect that the pre-GPU audit found in ``adapters/hf_local.py`` and that would
otherwise only surface on the machine with the GPU (where it is expensive and easy
to rationalise away).

Covered:
* F-01 - a Qwen3 hybrid-thinking template must be rendered with
  ``enable_thinking=False``; a non-thinking template must not receive the kwarg.
* F-03 - a placeholder/moving revision must be refused *before* any heavy import,
  and the override must be explicit and recorded.
* F-04 - the dtype kwarg name must follow the installed transformers major version.
* F-20 - the weights fingerprint must identify the bytes that would be loaded.
"""

from __future__ import annotations

import sys
import types

import pytest

from experiments.local_llm_event_extraction.adapters.base import AdapterDescriptor
from experiments.local_llm_event_extraction.adapters.hf_local import (
    HFLocalAdapter,
    _dtype_kwarg,
    _fingerprint_weights,
    _truthy,
    render_chat_prompt,
)


def _descriptor(**overrides) -> AdapterDescriptor:
    payload = {
        "adapter_id": "hf-test",
        "display_name": "test",
        "backend": "hf_local",
        "model_id": "Qwen/Qwen3-4B-Instruct-2507",
        "model_revision": "cdbee75f17c01a7cc42f958dc650907174af0554",
        "quantization": "nf4",
        "device": "cuda",
        "max_new_tokens": 32,
        "load_gate": "model_load",
    }
    payload.update(overrides)
    return AdapterDescriptor(**payload)


def _adapter(descriptor: AdapterDescriptor | None = None, *, environ=None) -> HFLocalAdapter:
    return HFLocalAdapter(
        descriptor or _descriptor(),
        weights_path=r"C:\nonexistent-weights",
        environ=environ or {},
    )


# --------------------------------------------------------------- F-01 thinking
class _RecordingTokenizer:
    def __init__(self, template: str) -> None:
        self.chat_template = template
        self.calls: list[dict[str, object]] = []

    def apply_chat_template(self, messages, **kwargs):
        self.calls.append(dict(kwargs))
        return "RENDERED"


_THINKING_TEMPLATE = (
    "{% if enable_thinking is defined and enable_thinking is false %}<think></think>"
    "{% endif %}{{ messages[0].content }}"
)
_PLAIN_TEMPLATE = "{{ messages[0].content }}"


def test_thinking_template_is_rendered_with_thinking_disabled() -> None:
    tokenizer = _RecordingTokenizer(_THINKING_TEMPLATE)
    rendered, info = render_chat_prompt(tokenizer, "SYS", "USER")
    assert rendered == "RENDERED"
    assert info["thinking_supported"] is True
    assert info["enable_thinking"] is False
    call = tokenizer.calls[0]
    assert call["enable_thinking"] is False
    assert call["tokenize"] is False
    assert call["add_generation_prompt"] is True


def test_non_thinking_template_does_not_receive_the_kwarg() -> None:
    tokenizer = _RecordingTokenizer(_PLAIN_TEMPLATE)
    _, info = render_chat_prompt(tokenizer, "SYS", "USER")
    assert info["thinking_supported"] is False
    assert info["enable_thinking"] is None
    assert "enable_thinking" not in tokenizer.calls[0]


def test_template_sha256_is_recorded_and_stable() -> None:
    first = render_chat_prompt(_RecordingTokenizer(_THINKING_TEMPLATE), "S", "U")[1]["template_sha256"]
    second = render_chat_prompt(_RecordingTokenizer(_THINKING_TEMPLATE), "S", "U")[1]["template_sha256"]
    other = render_chat_prompt(_RecordingTokenizer(_PLAIN_TEMPLATE), "S", "U")[1]["template_sha256"]
    assert first == second
    assert first != other
    assert len(first) == 64


# ----------------------------------------------------------------- F-03 pinning
def test_placeholder_revision_is_refused_before_torch_is_imported(monkeypatch) -> None:
    monkeypatch.setenv("MEDRADAR_LOCAL_LLM_ALLOW_MODEL_LOAD", "1")
    adapter = _adapter(_descriptor(model_revision="PENDING-A-PIN"))
    with pytest.raises(Exception) as excinfo:
        adapter.load()
    assert "not an immutable pin" in str(excinfo.value)
    assert type(excinfo.value).__name__ == "AdapterUnavailable"
    assert "torch" not in sys.modules


def test_missing_revision_is_refused(monkeypatch) -> None:
    monkeypatch.setenv("MEDRADAR_LOCAL_LLM_ALLOW_MODEL_LOAD", "1")
    adapter = _adapter(_descriptor(model_revision=None))
    with pytest.raises(Exception) as excinfo:
        adapter.load()
    assert "not an immutable pin" in str(excinfo.value)
    assert "torch" not in sys.modules


def test_unpinned_override_is_explicit_and_recorded(monkeypatch) -> None:
    monkeypatch.setenv("MEDRADAR_LOCAL_LLM_ALLOW_MODEL_LOAD", "1")
    adapter = _adapter(
        _descriptor(model_revision="PENDING-A-PIN"),
        environ={"MEDRADAR_LOCAL_LLM_ALLOW_UNPINNED": "1"},
    )
    # It gets past the pin gate and then fails on the deliberately missing weights
    # directory -- i.e. the refusal is no longer about the pin.
    with pytest.raises(Exception) as excinfo:
        adapter.load()
    assert "not an immutable pin" not in str(excinfo.value)
    assert "does not exist" in str(excinfo.value) or "no local weights" in str(excinfo.value)
    assert adapter._unpinned_override is True


def test_pinned_revision_returns_the_pin() -> None:
    adapter = _adapter()
    assert adapter._pinned_revision() == "cdbee75f17c01a7cc42f958dc650907174af0554"
    assert adapter._unpinned_override is False


# ------------------------------------------------------- F-04 dtype compatibility
def test_dtype_kwarg_follows_transformers_major_version() -> None:
    fake_five = types.SimpleNamespace(__version__="5.22.1")
    fake_four = types.SimpleNamespace(__version__="4.57.0")
    assert _dtype_kwarg(fake_five) == "dtype"
    assert _dtype_kwarg(fake_four) == "torch_dtype"


# ------------------------------------------------------- F-20 weights fingerprint
def test_weights_fingerprint_identifies_the_bytes(tmp_path) -> None:
    root = tmp_path / "snapshot"
    root.mkdir()
    (root / "config.json").write_text('{"model_type": "qwen3"}', encoding="utf-8")
    (root / "model.safetensors").write_bytes(b"0" * 32)
    first = _fingerprint_weights(root)
    assert first is not None and len(first) == 64

    (root / "model.safetensors").write_bytes(b"1" * 33)
    assert _fingerprint_weights(root) != first

    same = tmp_path / "copy"
    same.mkdir()
    (same / "config.json").write_text('{"model_type": "qwen3"}', encoding="utf-8")
    (same / "model.safetensors").write_bytes(b"1" * 33)
    assert _fingerprint_weights(same) == _fingerprint_weights(root)


# ------------------------------------------------------------------- helpers
@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, False), ("", False), ("0", False), ("off", False), ("1", True), ("true", True), ("YES", True), (" on ", True)],
)
def test_truthy_uses_the_project_gate_convention(value, expected) -> None:
    assert _truthy(value) is expected
