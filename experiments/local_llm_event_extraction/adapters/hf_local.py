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

import hashlib
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
_MIB = 1024.0 * 1024.0


def _dtype_kwarg(transformers: Any) -> str:
    """Name of the model-load dtype argument for the installed transformers.

    transformers 5 renamed ``torch_dtype`` to ``dtype``; both older 4.x and 5.x are
    supported, so the choice is made from the installed major version and *recorded*
    rather than guessed.  Passing the wrong one is not suppressed: a 4.x build that
    still accepts ``torch_dtype`` is used as-is, and a genuine TypeError surfaces.
    """
    version = str(getattr(transformers, "__version__", "0"))
    try:
        major = int(version.split(".")[0])
    except (ValueError, IndexError):  # pragma: no cover - unparsable version
        major = 4
    return "dtype" if major >= 5 else "torch_dtype"


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
        self._load_stats: dict[str, Any] = {}
        self._weights_fingerprint: str | None = None
        self._revision_resolved: str | None = None
        self._unpinned_override = False

    def _pinned_revision(self) -> str | None:
        """The immutable revision to load, or ``AdapterUnavailable``.

        A placeholder or absent revision is not a pin.  Refusing here means an
        unpinned run cannot be produced by accident; ``MEDRADAR_LOCAL_LLM_ALLOW_UNPINNED``
        is a recorded diagnostic override, never a default.
        """
        revision = self._descriptor.model_revision
        allow_unpinned = _truthy(self._environ.get("MEDRADAR_LOCAL_LLM_ALLOW_UNPINNED"))
        if not revision or revision.startswith(_PINNED_PLACEHOLDER):
            if not allow_unpinned:
                raise AdapterUnavailable(
                    f"{self._descriptor.adapter_id}: model_revision={revision!r} is not an "
                    "immutable pin. Set a concrete commit sha, or set "
                    "MEDRADAR_LOCAL_LLM_ALLOW_UNPINNED=1 for a diagnostic run."
                )
            self._unpinned_override = True
            return None
        return str(revision)

    def _device_index(self) -> int:
        """CUDA ordinal named by the descriptor's ``device`` (``cuda`` -> 0)."""
        device = str(self._descriptor.device or "cuda").strip()
        if ":" in device:
            try:
                return int(device.split(":", 1)[1])
            except ValueError:  # pragma: no cover - malformed descriptor
                return 0
        return 0

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
        # Pin discipline is pure configuration, so it is checked *before* the heavy
        # import: an unpinned run must be refusable on a machine without torch too,
        # and the refusal must be unit-testable offline.
        revision = self._pinned_revision()
        self._revision_resolved = revision
        source = self.resolve_weights()

        try:
            import torch  # noqa: F401  (heavy import, deliberately inside load)
            import transformers
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
            compute_dtype = (
                torch.bfloat16
                if torch.cuda.is_available() and torch.cuda.is_bf16_supported()
                else torch.float16
            )
            model_kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=compute_dtype,
            )
            # ``device_map="auto"`` may silently spread layers to CPU once the GPU is
            # full, which turns a 20 s generation into a 20 min one and makes the VRAM
            # measurement meaningless.  Pin every layer to the requested CUDA device so
            # an over-budget configuration raises CUDA OOM instead of quietly crawling.
            model_kwargs["device_map"] = {"": self._device_index()}
        else:
            model_kwargs["device_map"] = self._descriptor.device
            model_kwargs[_dtype_kwarg(transformers)] = (
                torch.float16 if torch.cuda.is_available() else torch.float32
            )

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
        self._weights_fingerprint = _fingerprint_weights(Path(source))
        self._loaded = True
        self._load_stats = {
            "transformers_version": str(getattr(transformers, "__version__", "unknown")),
            "torch_version": str(getattr(torch, "__version__", "unknown")),
            "torch_cuda_version": getattr(getattr(torch, "version", None), "cuda", None),
            "device": self._descriptor.device,
            "quantization_effective": self._quantization,
            "dtype_kwarg": _dtype_kwarg(transformers) if self._quantization != "bnb-4bit" else None,
        }
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            self._vram_method = (
                "torch.cuda.max_memory_allocated()/MiB, reset before every generate() call"
            )
            self._load_stats.update(
                {
                    "cuda_device_name": torch.cuda.get_device_name(self._device_index()),
                    "cuda_compute_capability": list(
                        torch.cuda.get_device_capability(self._device_index())
                    ),
                    "vram_allocated_after_load_mib": torch.cuda.memory_allocated(self._device_index()) / _MIB,
                    "vram_reserved_after_load_mib": torch.cuda.memory_reserved(self._device_index()) / _MIB,
                    "vram_total_mib": torch.cuda.get_device_properties(self._device_index()).total_memory / _MIB,
                }
            )

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
        rendered, chat_template_info = render_chat_prompt(tokenizer, system, user)
        thinking_supported = chat_template_info["thinking_supported"]

        cuda = bool(torch.cuda.is_available())
        encoded = tokenizer(rendered, return_tensors="pt", truncation=False)
        tokens_in = int(encoded["input_ids"].shape[-1])
        max_positions = int(getattr(getattr(model, "config", None), "max_position_embeddings", 0) or 0)
        if max_positions and tokens_in >= max_positions:
            # Truncating here would silently hand the model a different document than
            # the one the manifest records.  The prompt builder owns truncation and
            # marks it in the text; this is the last line of defence.
            raise AdapterUnavailable(
                f"{self._descriptor.adapter_id}: prompt is {tokens_in} tokens but the model "
                f"accepts at most {max_positions - 1}. Lower max_input_chars instead of "
                "truncating silently here."
            )
        if cuda:
            encoded = {key: value.to("cuda") for key, value in encoded.items()}
            torch.manual_seed(self._seed)
            torch.cuda.manual_seed_all(self._seed)
            # Peak VRAM is per-call: without the reset the number would be the
            # process-lifetime high-water mark and would grow monotonically.
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.synchronize()
        tokens_in = int(encoded["input_ids"].shape[-1])

        started = time.perf_counter()
        with torch.no_grad():
            output = model.generate(
                **encoded,
                max_new_tokens=self._descriptor.max_new_tokens,
                do_sample=False,  # greedy; temperature 0 is implicit, not passed
                pad_token_id=tokenizer.pad_token_id,
            )
        if cuda:
            torch.cuda.synchronize()  # kernels are async; stop the clock after they finish
        elapsed = time.perf_counter() - started
        generated = output[0][tokens_in:]
        text = tokenizer.decode(generated, skip_special_tokens=True)
        tokens_out = int(generated.shape[-1])

        eos_ids: set[int] = set()
        generation_eos = getattr(getattr(model, "generation_config", None), "eos_token_id", None)
        for candidate in (generation_eos, getattr(tokenizer, "eos_token_id", None)):
            if isinstance(candidate, int):
                eos_ids.add(candidate)
            elif isinstance(candidate, (list, tuple)):
                eos_ids.update(int(value) for value in candidate if isinstance(value, int))
        stopped_on_eos = tokens_out > 0 and eos_ids and int(generated[-1].item()) in eos_ids
        if stopped_on_eos:
            finish_reason = "stop"
        elif tokens_out >= self._descriptor.max_new_tokens:
            finish_reason = "length"
        else:
            finish_reason = "stop"

        peak_allocated_mib: float | None = None
        peak_reserved_mib: float | None = None
        if cuda:
            peak_allocated_mib = float(torch.cuda.max_memory_allocated()) / _MIB
            peak_reserved_mib = float(torch.cuda.max_memory_reserved()) / _MIB
        peak_vram_mb = peak_allocated_mib

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
                "chat_template": {
                    "thinking_supported": bool(thinking_supported),
                    "enable_thinking": False if thinking_supported else None,
                    "template_sha256": chat_template_info["template_sha256"],
                },
                "revision_resolved": self._revision_resolved,
                "unpinned_override": bool(self._unpinned_override),
                "weights_fingerprint": self._weights_fingerprint,
                "peak_vram_measurement_method": self._vram_method,
                "peak_vram_reserved_mib": peak_reserved_mib,
                "tokens_per_second": (tokens_out / elapsed) if elapsed > 0 else None,
                "prompt_chars": len(rendered),
                "weights_source": self._weights_source,
                "load": dict(self._load_stats),
            },
        )


def _clean_path(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _truthy(value: str | None) -> bool:
    """The project's gate convention: only explicit truthy values open anything."""
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _fingerprint_weights(root: Path) -> str | None:
    """Cheap, deterministic identity of a local snapshot directory.

    ``(name, size)`` for every file plus the sha256 of ``config.json``.  This is not a
    full weight hash (that would mean re-reading 8 GB at every load, and the download
    manifest already carries per-file sha256); it is enough to notice that the
    directory under a pinned revision is not the directory that was reviewed.
    """
    try:
        digest = hashlib.sha256()
        for path in sorted(root.iterdir()):
            if path.is_file():
                digest.update(path.name.encode("utf-8"))
                digest.update(str(path.stat().st_size).encode("ascii"))
        config_path = root / "config.json"
        if config_path.is_file():
            digest.update(hashlib.sha256(config_path.read_bytes()).digest())
        return digest.hexdigest()
    except OSError:  # pragma: no cover - unreadable snapshot
        return None


def _find_snapshot(hub_model_dir: Path) -> Path | None:
    """A local snapshot directory with a config file, if one exists."""
    snapshots = hub_model_dir / "snapshots"
    if not snapshots.is_dir():
        return None
    for candidate in sorted(snapshots.iterdir()):
        if candidate.is_dir() and (candidate / "config.json").is_file():
            return candidate
    return None


__all__ = ["HFLocalAdapter", "render_chat_prompt"]

def render_chat_prompt(tokenizer: Any, system: str, user: str) -> tuple[str, dict[str, Any]]:
    """Render the chat prompt and report how thinking mode was handled.

    Qwen3 "hybrid thinking" checkpoints share the decode budget with a reasoning
    trace, and that trace can restate the output skeleton the system prompt prints --
    which the strict parser would then decode as the answer.  The ``enable_thinking``
    switch only exists on templates that implement it (the 2507 Instruct checkpoints
    are non-thinking and their template has no such variable), so the flag is passed
    only when the template supports it, and the decision is returned for the record.

    Kept as a module function so the behaviour is unit-testable with a fake tokenizer
    and no torch/transformers installed.
    """
    template = getattr(tokenizer, "chat_template", None) or ""
    kwargs: dict[str, Any] = {}
    thinking_supported = "enable_thinking" in template
    if thinking_supported:
        kwargs["enable_thinking"] = False
    if template:
        rendered = tokenizer.apply_chat_template(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            tokenize=False,
            add_generation_prompt=True,
            **kwargs,
        )
    else:  # pragma: no cover - only for tokenizer shapes without a template
        rendered = f"<|system|>\n{system}\n<|user|>\n{user}\n<|assistant|>\n"
    info = {
        "thinking_supported": thinking_supported,
        "enable_thinking": False if thinking_supported else None,
        "template_sha256": hashlib.sha256(str(template).encode("utf-8")).hexdigest(),
        "add_generation_prompt": True,
        "used_chat_template": bool(template),
    }
    return rendered, info
