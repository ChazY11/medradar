"""Arm B/C local backend: a gated Hugging Face causal-LM adapter.

The adapter class is shared by the untuned model (arm B) and the QLoRA-tuned
checkpoint (arm C); only the descriptor and the optional ``peft_adapter_path``
differ.  That is deliberate: if arm C had its own class, a difference in score
could be a difference in code.

Hard rules implemented here
---------------------------
1. ``load()`` calls :meth:`ModelAdapter.check_gate` first.  With the default-closed
   ``model_load`` gate, the adapter refuses before importing ``torch`` or
   ``transformers`` -- a test can prove ``torch`` never entered ``sys.modules``.
2. Weights are resolved from an explicit path or an **already-populated** local
   cache.  There is no download path: if neither exists, ``AdapterUnavailable`` is
   raised and nothing is fetched.
3. Measurement fields are ``None`` unless actually measured.  Token counts need a
   tokenizer; peak VRAM needs a live CUDA allocator.
4. Decoding is greedy (temperature 0) with a fixed seed, and the descriptor only
   claims ``deterministic=True`` for that configuration.

Nothing in this module imports a model library at import time.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Mapping

from .base import (
    AdapterDescriptor,
    AdapterResponse,
    AdapterUnavailable,
    ExtractionRequest,
    ModelAdapter,
)

_QUANT_ALIASES: Mapping[str, str] = {
    "none": "none",
    "": "none",
    "nf4": "bnb-4bit",
    "bnb4bit": "bnb-4bit",
    "bnb-4bit": "bnb-4bit",
    "4bit": "bnb-4bit",
}

_PINNED_PLACEHOLDER = "PENDING-A-PIN"


class HFLocalAdapter(ModelAdapter):
    """Gated local causal-LM backend (transformers; optional bitsandbytes + peft)."""

    def __init__(
        self,
        descriptor: AdapterDescriptor,
        *,
        weights_path: str | None = None,
        cache_dir: str | None = None,
        peft_adapter_path: str | None = None,
        seed: int = 0,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        if descriptor.backend != "hf_local":
            raise ValueError("HFLocalAdapter requires a descriptor with backend='hf_local'")
        self._descriptor = descriptor
        self._weights_path = _clean_path(weights_path)
        self._cache_dir = _clean_path(cache_dir)
        self._peft_adapter_path = _clean_path(peft_adapter_path)
        self._seed = int(seed)
        self._environ = dict(os.environ if environ is None else environ)
        requested = (descriptor.quantization or "none").strip().lower()
        if requested not in _QUANT_ALIASES:
            raise ValueError(
                f"unsupported quantization {descriptor.quantization!r}; "
                f"supported: {sorted(set(_QUANT_ALIASES.values()))}"
            )
        self._quantization = _QUANT_ALIASES[requested]
        self._loaded = False
        self._weights_source: str | None = None
        self._model: Any = None
        self._tokenizer: Any = None
        self._torch: Any = None
        self._vram_method: str | None = None

    # ------------------------------------------------------------- protocol
    @property
    def descriptor(self) -> AdapterDescriptor:
        return self._descriptor

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def weights_source(self) -> str | None:
        return self._weights_source

    @property
    def quantization(self) -> str:
        return self._quantization

    def describe(self) -> dict[str, Any]:
        payload = super().describe()
        payload.update(
            {
                "quantization_effective": self._quantization,
                "weights_source": self._weights_source,
                "peft_adapter_path": self._peft_adapter_path,
                "seed": self._seed,
                "decoding": {
                    "temperature": 0,
                    "do_sample": False,
                    "seed": self._seed,
                    "max_new_tokens": self._descriptor.max_new_tokens,
                },
            }
        )
        return payload

    # ------------------------------------------------------------- resolving
    def _cache_roots(self) -> list[Path]:
        roots: list[Path] = []
        if self._cache_dir:
            roots.append(Path(self._cache_dir))
        env = self._environ
        if env.get("HF_HUB_CACHE"):
            roots.append(Path(env["HF_HUB_CACHE"]))
        if env.get("HF_HOME"):
            roots.append(Path(env["HF_HOME"]) / "hub")
        if env.get("TRANSFORMERS_CACHE"):
            roots.append(Path(env["TRANSFORMERS_CACHE"]))
        if env.get("XDG_CACHE_HOME"):
            roots.append(Path(env["XDG_CACHE_HOME"]) / "huggingface" / "hub")
        roots.append(Path.home() / ".cache" / "huggingface" / "hub")
        unique: list[Path] = []
        seen: set[str] = set()
        for root in roots:
            key = str(root)
            if key not in seen:
                seen.add(key)
                unique.append(root)
        return unique

    def resolve_weights(self) -> str:
        """Return a local model directory, or raise ``AdapterUnavailable``.

        Never downloads.  An explicit path wins; otherwise a populated HF hub
        cache is accepted when it already contains a snapshot of ``model_id``.
        """
        if self._weights_path:
            path = Path(self._weights_path)
            if path.exists():
                return str(path)
            raise AdapterUnavailable(
                f"{self._descriptor.adapter_id}: configured weights path does not exist: {path}. "
                "Refusing to download anything."
            )
        model_id = self._descriptor.model_id
        if not model_id:
            raise AdapterUnavailable(
                f"{self._descriptor.adapter_id}: no model_id and no weights_path configured"
            )
        hub_dir = "models--" + model_id.replace("/", "--")
        for root in self._cache_roots():
            snapshot = _find_snapshot(root / hub_dir)
            if snapshot is not None:
                return str(snapshot)
        raise AdapterUnavailable(
            f"{self._descriptor.adapter_id}: no local weights for {model_id!r} and no populated cache. "
            "Set an explicit weights path (e.g. MEDRADAR_LOCAL_LLM_WEIGHTS_*) or place the checkpoint "
            "in the HF cache. This adapter never downloads weights."
        )

    # ------------------------------------------------------------- loading
    def load(self) -> None:
        if self._loaded:
            return
        # Gate first: no torch import, no disk scan of model weights before this.
        self.check_gate()
        source = self.resolve_weights()

        try:
            import torch  # noqa: F401  (heavy import, deliberately inside load)
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - optional dependency group
            raise AdapterUnavailable(
                f"{self._descriptor.adapter_id}: transformers/torch are not installed "
                f"(install the 'local-llm' extra): {exc}"
            ) from exc

        if self._descriptor.device.startswith("cuda") and not torch.cuda.is_available():
            raise AdapterUnavailable(
                f"{self._descriptor.adapter_id}: device={self._descriptor.device!r} requires CUDA, "
                "which is not available in this process"
            )

        revision = self._descriptor.model_revision
        if revision and revision.startswith(_PINNED_PLACEHOLDER):
            revision = None
        model_kwargs: dict[str, Any] = {"local_files_only": True}
        if revision:
            model_kwargs["revision"] = revision
        if self._cache_dir:
            model_kwargs["cache_dir"] = self._cache_dir

        if self._quantization == "bnb-4bit":
            try:
                import bitsandbytes  # noqa: F401  # imported for its availability error
                from transformers import BitsAndBytesConfig
            except ImportError as exc:  # pragma: no cover - optional dependency group
                raise AdapterUnavailable(
                    f"{self._descriptor.adapter_id}: quantization='nf4' needs bitsandbytes: {exc}"
                ) from exc
            model_kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=torch.float16,
            )
            model_kwargs["device_map"] = "auto"
        else:
            model_kwargs["device_map"] = self._descriptor.device
            model_kwargs["torch_dtype"] = torch.float16 if torch.cuda.is_available() else torch.float32

        tokenizer = AutoTokenizer.from_pretrained(source, local_files_only=True, **(
            {"cache_dir": self._cache_dir} if self._cache_dir else {}
        ))
        model = AutoModelForCausalLM.from_pretrained(source, **model_kwargs)
        if self._peft_adapter_path:
            adapter_path = Path(self._peft_adapter_path)
            if not adapter_path.exists():
                raise AdapterUnavailable(
                    f"{self._descriptor.adapter_id}: QLoRA adapter path does not exist: {adapter_path}. "
                    "Refusing to download anything."
                )
            try:
                from peft import PeftModel
            except ImportError as exc:  # pragma: no cover - optional dependency group
                raise AdapterUnavailable(
                    f"{self._descriptor.adapter_id}: a QLoRA checkpoint needs peft: {exc}"
                ) from exc
            model = PeftModel.from_pretrained(model, str(adapter_path))
        model.eval()
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        self._torch = torch
        self._tokenizer = tokenizer
        self._model = model
        self._weights_source = source
        self._loaded = True
        if torch.cuda.is_available():
            self._vram_method = "torch.cuda.max_memory_allocated()"

    def unload(self) -> None:
        self._model = None
        self._tokenizer = None
        self._torch = None
        self._loaded = False

    # ------------------------------------------------------------- inference
    def generate(self, request: ExtractionRequest) -> AdapterResponse:
        if not self._loaded:
            raise AdapterUnavailable(
                f"{self._descriptor.adapter_id}: generate() called before load(); refusing implicit load"
            )
        if request.prompt is None:
            raise AdapterUnavailable(
                f"{self._descriptor.adapter_id}: this adapter needs request.prompt (built by prompting.py)"
            )
        torch = self._torch
        tokenizer = self._tokenizer
        model = self._model
        system = request.prompt.system
        user = request.prompt.user

        if getattr(tokenizer, "chat_template", None):
            rendered = tokenizer.apply_chat_template(
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                tokenize=False,
                add_generation_prompt=True,
            )
        else:  # pragma: no cover - only for tokenizer/cache shapes without a template
            rendered = f"<|system|>\n{system}\n<|user|>\n{user}\n<|assistant|>\n"

        started = time.perf_counter()
        torch.manual_seed(self._seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(self._seed)
        encoded = tokenizer(rendered, return_tensors="pt", truncation=False)
        input_ids = encoded["input_ids"]
        if torch.cuda.is_available():
            input_ids = input_ids.to("cuda")
            encoded = {key: value.to("cuda") for key, value in encoded.items()}
        tokens_in = int(input_ids.shape[-1])
        with torch.no_grad():
            output = model.generate(
                **encoded,
                max_new_tokens=self._descriptor.max_new_tokens,
                do_sample=False,  # greedy; temperature 0 is implicit, not passed
                pad_token_id=tokenizer.pad_token_id,
            )
        generated = output[0][tokens_in:]
        text = tokenizer.decode(generated, skip_special_tokens=True)
        elapsed = time.perf_counter() - started
        tokens_out = int(generated.shape[-1])
        finish_reason = "length" if tokens_out >= self._descriptor.max_new_tokens else "stop"

        peak_vram_mb: float | None = None
        if torch.cuda.is_available():
            peak_vram_mb = float(torch.cuda.max_memory_allocated()) / (1024.0 * 1024.0)

        return AdapterResponse(
            text=text,
            finish_reason=finish_reason,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            wall_time_s=elapsed,
            peak_vram_mb=peak_vram_mb,
            metadata={
                "backend": "hf_local",
                "model_id": self._descriptor.model_id,
                "model_revision": self._descriptor.model_revision,
                "quantization": self._quantization,
                "decoding": {"temperature": 0, "do_sample": False, "seed": self._seed},
                "peak_vram_measurement_method": self._vram_method,
                "weights_source": self._weights_source,
            },
        )


def _clean_path(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _find_snapshot(hub_model_dir: Path) -> Path | None:
    """A local snapshot directory with a config file, if one exists."""
    snapshots = hub_model_dir / "snapshots"
    if not snapshots.is_dir():
        return None
    for candidate in sorted(snapshots.iterdir()):
        if candidate.is_dir() and (candidate / "config.json").is_file():
            return candidate
    return None


__all__ = ["HFLocalAdapter"]
