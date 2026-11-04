"""QLoRA configuration for a *future* local Qwen3-4B event extractor (never executed here).

What this file is, and what it deliberately is not
--------------------------------------------------
It is a **configuration contract**: every number a 4-bit QLoRA run would need is
declared in one frozen dataclass, validated, serialised to JSON and referenced by
adapter id + pinned model revision (see ``adapters/base.py`` -- a training config
that hardcodes a checkpoint path instead of an adapter id + revision cannot be
reproduced, because nobody can tell which weights it meant).

It is **not** a training launcher.  Nothing in this module imports ``torch``,
``transformers``, ``peft``, ``bitsandbytes`` or downloads anything.  The committed
draft (``configs/qlora_qwen3_4b.draft.json``) has ``"enabled": false`` and
``"executed": false``; :func:`load_draft` refuses any file that claims otherwise.

Why two validation modes
------------------------
A *draft* is a proposal written before anyone is allowed to run it, so it may
carry a declared placeholder revision (``PENDING-A-PIN``) and must not be
enabled.  A *run* config is what a later phase would authorise, and it must carry
a real pin.  :meth:`QLoRAConfig.validate` therefore takes ``draft: bool``:

* ``draft=True``  -- ``enabled`` must be ``False``, ``resume_from`` must be
  ``None``; a placeholder revision is tolerated *as a readiness blocker* (the
  readiness guard reports ``MODEL_NOT_PINNED``) but a **floating** revision
  (``main``, ``latest``, ``HEAD`` ...) is always an error, because a floating ref
  silently changes what would be trained.
* ``draft=False`` -- ``enabled`` may be ``True``; the revision must be a real pin.

Ranges are not decoration: a learning rate above ``1e-2``, ``r=0`` or
``abort_at_vram_mb <= vram_budget_mb`` are the kind of typo that wastes a
multi-hour GPU session, so they fail before any gate is even consulted.

The estimate caveat
-------------------
``vram_budget_mb``/``abort_at_vram_mb`` are *budgets*, not measurements.  The
measured facts of this machine (16 GB VRAM, ~3.9 GB already used by desktop
applications, measured by the Team Lead) are recorded in the draft JSON's
``_notes`` object; the peak-memory number there is explicitly **assumed** and
must be replaced by a measured dry run before a training phase is authorised.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "configs" / "qlora_qwen3_4b.draft.json"

_ALLOWED_QUANTIZATION = ("nf4",)
_ALLOWED_COMPUTE_DTYPES = ("bfloat16", "float16")
_ALLOWED_BIAS = ("none", "all", "lora_only")
_ALLOWED_SCHEDULERS = ("cosine", "linear", "constant", "constant_with_warmup")
_TARGET_MODULE_PATTERN = re.compile(r"^[A-Za-z0-9_.\-]+(,[A-Za-z0-9_.\-]+)*$")
_ADAPTER_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._\-]{0,63}$")

#: Revisions that move over time.  Never acceptable: a run must name bytes.
FLOATING_REFS = frozenset(
    {"main", "master", "latest", "head", "default", "trunk", "develop", "dev", "nightly"}
)

#: Substrings that mark a revision as not yet a pin (declared placeholder).
PLACEHOLDER_TOKENS = (
    "pending",
    "todo",
    "tbd",
    "placeholder",
    "replace",
    "changeme",
    "fixme",
    "unpinned",
    "none",
    "null",
)


class ConfigError(ValueError):
    """A QLoRA configuration is structurally or numerically unusable."""

    def __init__(self, message: str, issues: tuple[str, ...] = ()) -> None:
        self.issues = tuple(issues)
        super().__init__(message)


def is_floating_revision(revision: Any) -> bool:
    """True for a branch/tag-like ref that cannot pin what was trained."""
    if not isinstance(revision, str):
        return False
    return revision.strip().lower() in FLOATING_REFS


def is_placeholder_revision(revision: Any) -> bool:
    """True when the revision is absent or a declared placeholder (``PENDING-A-PIN``)."""
    if revision is None:
        return True
    if not isinstance(revision, str):
        return True
    text = revision.strip().lower()
    if not text:
        return True
    if is_floating_revision(text):
        return True
    return any(token in text for token in PLACEHOLDER_TOKENS)


def is_pinned(revision: Any) -> bool:
    """True only for a concrete revision string: not empty, not floating, not a placeholder."""
    if not isinstance(revision, str):
        return False
    text = revision.strip()
    if len(text) < 6:
        return False
    return not is_placeholder_revision(text)


def _as_int(name: str, value: Any, issues: list[str]) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        issues.append(f"{name} must be an integer, got {type(value).__name__}")
        return 0
    return value


def _as_float(name: str, value: Any, issues: list[str]) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        issues.append(f"{name} must be a number, got {type(value).__name__}")
        return 0.0
    return float(value)


def _as_bool(name: str, value: Any, issues: list[str]) -> bool:
    if not isinstance(value, bool):
        issues.append(f"{name} must be a boolean, got {type(value).__name__}")
        return False
    return value


def _as_str(name: str, value: Any, issues: list[str]) -> str:
    if not isinstance(value, str):
        issues.append(f"{name} must be a string, got {type(value).__name__}")
        return ""
    return value


def _as_optional_str(name: str, value: Any, issues: list[str]) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        issues.append(f"{name} must be a string or null, got {type(value).__name__}")
        return None
    return value


def _as_str_tuple(name: str, value: Any, issues: list[str]) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
        return tuple(value)
    issues.append(f"{name} must be a string or a list of strings")
    return ()


@dataclass(frozen=True)
class QLoRAConfig:
    """Every knob of the (not yet authorised) 4-bit QLoRA run, in one place."""

    base_adapter_id: str = "hf-qwen3-4b"
    model_id: str = "Qwen/Qwen3-4B"
    revision: str = ""
    quantization: str = "nf4"
    double_quant: bool = True
    compute_dtype: str = "bfloat16"
    r: int = 16
    alpha: int = 32
    dropout: float = 0.05
    target_modules: str = "all-linear"
    bias: str = "none"
    learning_rate: float = 2e-4
    lr_scheduler: str = "cosine"
    warmup_ratio: float = 0.03
    num_epochs: int = 1
    max_seq_len: int = 2048
    per_device_batch_size: int = 1
    gradient_accumulation_steps: int = 16
    gradient_checkpointing: bool = True
    paged_optimizer: bool = True
    seed: int = 20261104
    vram_budget_mb: int = 14336
    abort_at_vram_mb: int = 15360
    save_steps: int = 50
    eval_steps: int = 50
    resume_from: str | None = None
    enabled: bool = False
    executed: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)

    # ------------------------------------------------------------------ (de)coding
    def to_dict(self) -> dict[str, Any]:
        return {
            "base_adapter_id": self.base_adapter_id,
            "model_id": self.model_id,
            "revision": self.revision,
            "quantization": self.quantization,
            "double_quant": self.double_quant,
            "compute_dtype": self.compute_dtype,
            "r": self.r,
            "alpha": self.alpha,
            "dropout": self.dropout,
            "target_modules": self.target_modules,
            "bias": self.bias,
            "learning_rate": self.learning_rate,
            "lr_scheduler": self.lr_scheduler,
            "warmup_ratio": self.warmup_ratio,
            "num_epochs": self.num_epochs,
            "max_seq_len": self.max_seq_len,
            "per_device_batch_size": self.per_device_batch_size,
            "gradient_accumulation_steps": self.gradient_accumulation_steps,
            "gradient_checkpointing": self.gradient_checkpointing,
            "paged_optimizer": self.paged_optimizer,
            "seed": self.seed,
            "vram_budget_mb": self.vram_budget_mb,
            "abort_at_vram_mb": self.abort_at_vram_mb,
            "save_steps": self.save_steps,
            "eval_steps": self.eval_steps,
            "resume_from": self.resume_from,
            "enabled": self.enabled,
            "executed": self.executed,
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, payload: Any) -> "QLoRAConfig":
        """Strict decode: unknown keys are an error, ``_``-prefixed metadata is ignored.

        The committed draft carries a ``_notes`` object explaining provenance.  It is
        metadata for a reader, not a configuration field, so it is skipped here and
        returned separately by :func:`load_document`.
        """
        if not isinstance(payload, Mapping):
            raise ConfigError(f"config must be a JSON object, got {type(payload).__name__}")
        known = set(cls.__dataclass_fields__)
        unknown = sorted(key for key in payload if key not in known and not str(key).startswith("_"))
        if unknown:
            raise ConfigError(f"config has unknown key(s): {', '.join(unknown)}")

        issues: list[str] = []
        config = cls(
            base_adapter_id=_as_str("base_adapter_id", payload.get("base_adapter_id", cls.base_adapter_id), issues),
            model_id=_as_str("model_id", payload.get("model_id", cls.model_id), issues),
            revision=_as_str("revision", payload.get("revision", ""), issues),
            quantization=_as_str("quantization", payload.get("quantization", cls.quantization), issues),
            double_quant=_as_bool("double_quant", payload.get("double_quant", cls.double_quant), issues),
            compute_dtype=_as_str("compute_dtype", payload.get("compute_dtype", cls.compute_dtype), issues),
            r=_as_int("r", payload.get("r", cls.r), issues),
            alpha=_as_int("alpha", payload.get("alpha", cls.alpha), issues),
            dropout=_as_float("dropout", payload.get("dropout", cls.dropout), issues),
            target_modules=_as_str("target_modules", payload.get("target_modules", cls.target_modules), issues),
            bias=_as_str("bias", payload.get("bias", cls.bias), issues),
            learning_rate=_as_float("learning_rate", payload.get("learning_rate", cls.learning_rate), issues),
            lr_scheduler=_as_str("lr_scheduler", payload.get("lr_scheduler", cls.lr_scheduler), issues),
            warmup_ratio=_as_float("warmup_ratio", payload.get("warmup_ratio", cls.warmup_ratio), issues),
            num_epochs=_as_int("num_epochs", payload.get("num_epochs", cls.num_epochs), issues),
            max_seq_len=_as_int("max_seq_len", payload.get("max_seq_len", cls.max_seq_len), issues),
            per_device_batch_size=_as_int(
                "per_device_batch_size", payload.get("per_device_batch_size", cls.per_device_batch_size), issues
            ),
            gradient_accumulation_steps=_as_int(
                "gradient_accumulation_steps",
                payload.get("gradient_accumulation_steps", cls.gradient_accumulation_steps),
                issues,
            ),
            gradient_checkpointing=_as_bool(
                "gradient_checkpointing", payload.get("gradient_checkpointing", cls.gradient_checkpointing), issues
            ),
            paged_optimizer=_as_bool("paged_optimizer", payload.get("paged_optimizer", cls.paged_optimizer), issues),
            seed=_as_int("seed", payload.get("seed", cls.seed), issues),
            vram_budget_mb=_as_int("vram_budget_mb", payload.get("vram_budget_mb", cls.vram_budget_mb), issues),
            abort_at_vram_mb=_as_int("abort_at_vram_mb", payload.get("abort_at_vram_mb", cls.abort_at_vram_mb), issues),
            save_steps=_as_int("save_steps", payload.get("save_steps", cls.save_steps), issues),
            eval_steps=_as_int("eval_steps", payload.get("eval_steps", cls.eval_steps), issues),
            resume_from=_as_optional_str("resume_from", payload.get("resume_from"), issues),
            enabled=_as_bool("enabled", payload.get("enabled", cls.enabled), issues),
            executed=_as_bool("executed", payload.get("executed", cls.executed), issues),
            notes=_as_str_tuple("notes", payload.get("notes"), issues),
        )
        if issues:
            raise ConfigError("config decode failed: " + "; ".join(issues), tuple(issues))
        return config

    # -------------------------------------------------------------- validation
    def validate(self, *, draft: bool = True) -> "QLoRAConfig":
        """Raise :class:`ConfigError` listing every problem; return ``self`` when valid.

        ``draft=True`` (the default) is the posture of this phase: the config must
        not be enabled, and a declared placeholder revision is tolerated because the
        readiness guard -- not this validator -- is what turns it into
        ``MODEL_NOT_PINNED``.  A floating ref is an error in *both* modes.
        """
        issues: list[str] = []

        if not _ADAPTER_ID_PATTERN.match(self.base_adapter_id or ""):
            issues.append(
                "base_adapter_id must be a lower-case adapter id (e.g. 'hf-qwen3-4b'), "
                f"got {self.base_adapter_id!r}"
            )
        if not (self.model_id or "").strip():
            issues.append("model_id is required (a Hugging Face repo id such as 'Qwen/Qwen3-4B')")

        revision = (self.revision or "").strip()
        if not revision:
            if draft:
                issues.append("revision is empty; a draft must at least declare PENDING-A-PIN")
            else:
                issues.append("revision is required and must be a concrete pin (commit sha or immutable tag)")
        elif is_floating_revision(revision):
            issues.append(
                f"revision {self.revision!r} is a floating ref; a run must name immutable bytes "
                "(a commit sha), never a moving branch or tag"
            )
        elif not draft and is_placeholder_revision(revision):
            issues.append(
                f"revision {self.revision!r} is a declared placeholder; an authorised run config "
                "requires a real pin"
            )

        if self.quantization not in _ALLOWED_QUANTIZATION:
            issues.append(f"quantization must be one of {list(_ALLOWED_QUANTIZATION)}, got {self.quantization!r}")
        if self.compute_dtype not in _ALLOWED_COMPUTE_DTYPES:
            issues.append(f"compute_dtype must be one of {list(_ALLOWED_COMPUTE_DTYPES)}, got {self.compute_dtype!r}")
        if not 1 <= self.r <= 256:
            issues.append(f"r must be in [1, 256], got {self.r}")
        if not 1 <= self.alpha <= 512:
            issues.append(f"alpha must be in [1, 512], got {self.alpha}")
        if not 0.0 <= self.dropout <= 0.5:
            issues.append(f"dropout must be in [0.0, 0.5], got {self.dropout}")
        target_modules = (self.target_modules or "").strip()
        if target_modules != "all-linear" and not _TARGET_MODULE_PATTERN.match(target_modules):
            issues.append(
                "target_modules must be 'all-linear' or a comma-separated list of module names, "
                f"got {self.target_modules!r}"
            )
        if self.bias not in _ALLOWED_BIAS:
            issues.append(f"bias must be one of {list(_ALLOWED_BIAS)}, got {self.bias!r}")
        if not 0.0 < self.learning_rate <= 1e-2:
            issues.append(f"learning_rate must be in (0, 1e-2], got {self.learning_rate}")
        if self.lr_scheduler not in _ALLOWED_SCHEDULERS:
            issues.append(f"lr_scheduler must be one of {list(_ALLOWED_SCHEDULERS)}, got {self.lr_scheduler!r}")
        if not 0.0 <= self.warmup_ratio < 0.5:
            issues.append(f"warmup_ratio must be in [0.0, 0.5), got {self.warmup_ratio}")
        if not 1 <= self.num_epochs <= 20:
            issues.append(f"num_epochs must be in [1, 20], got {self.num_epochs}")
        if not 128 <= self.max_seq_len <= 8192:
            issues.append(f"max_seq_len must be in [128, 8192], got {self.max_seq_len}")
        if not 1 <= self.per_device_batch_size <= 64:
            issues.append(f"per_device_batch_size must be in [1, 64], got {self.per_device_batch_size}")
        if not 1 <= self.gradient_accumulation_steps <= 1024:
            issues.append(
                f"gradient_accumulation_steps must be in [1, 1024], got {self.gradient_accumulation_steps}"
            )
        if not 0 <= self.seed < 2**32:
            issues.append(f"seed must be in [0, 2**32), got {self.seed}")
        if not 1 <= self.vram_budget_mb <= 16384:
            issues.append(f"vram_budget_mb must be in [1, 16384], got {self.vram_budget_mb}")
        if not self.vram_budget_mb < self.abort_at_vram_mb <= 16384:
            issues.append(
                "abort_at_vram_mb must be greater than vram_budget_mb and at most 16384, "
                f"got budget={self.vram_budget_mb}, abort={self.abort_at_vram_mb}"
            )
        if not 1 <= self.save_steps <= 100_000:
            issues.append(f"save_steps must be in [1, 100000], got {self.save_steps}")
        if not 1 <= self.eval_steps <= 100_000:
            issues.append(f"eval_steps must be in [1, 100000], got {self.eval_steps}")

        if self.executed:
            issues.append(
                "executed=True is refused: this phase never executes training, and a config that "
                "claims a completed run cannot be re-validated as a plan"
            )
        if draft and self.enabled:
            issues.append(
                "enabled=True in a draft config: a draft must stay disabled until a named human "
                "signs the protocol amendment and the readiness gates pass"
            )
        if draft and self.resume_from is not None:
            issues.append("resume_from must be None in a draft config: there is nothing to resume yet")
        if self.resume_from is not None and not str(self.resume_from).strip():
            issues.append("resume_from must be null or a non-empty path")

        if issues:
            raise ConfigError(
                "QLoRA config is not usable: " + "; ".join(issues),
                tuple(issues),
            )
        return self


@dataclass(frozen=True)
class ConfigDocument:
    """A loaded config file: the config plus its ``_``-prefixed provenance metadata."""

    config: QLoRAConfig
    metadata: Mapping[str, Any]
    source_path: str
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "metadata": dict(self.metadata),
            "source_path": self.source_path,
            "sha256": self.sha256,
        }


def load_document(path: str | Path | None = None) -> ConfigDocument:
    """Load a config file for readiness assessment, validating in the mode it claims.

    A config that says ``enabled=false`` is validated as a **draft**; a config that
    says ``enabled=true`` is validated as a **run** (real pin required).  Nothing is
    executed; this function only reads JSON.
    """
    source = Path(DEFAULT_CONFIG_PATH if path is None else path)
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise ConfigError(f"cannot read config {str(source)!r}: {exc}") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"config {str(source)!r} is not valid UTF-8 JSON: {exc}") from exc
    config = QLoRAConfig.from_dict(payload)
    config.validate(draft=not config.enabled)
    metadata = {str(key): value for key, value in payload.items() if str(key).startswith("_")}
    return ConfigDocument(
        config=config,
        metadata=metadata,
        source_path=str(source.resolve()),
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def load_draft(path: str | Path | None = None) -> QLoRAConfig:
    """Load the committed draft and enforce *draft* invariants (never enabled).

    This is deliberately stricter than :func:`load_document`: a file passed to
    ``load_draft`` must be a draft, so ``enabled=true`` is an error even though
    :func:`load_document` would accept it as a run config.
    """
    source = Path(DEFAULT_CONFIG_PATH if path is None else path)
    document = load_document(source)
    if document.config.enabled:
        raise ConfigError(
            f"{str(source)!r} declares enabled=true; load_draft() only accepts a disabled draft"
        )
    document.config.validate(draft=True)
    return document.config


__all__ = [
    "DEFAULT_CONFIG_PATH",
    "FLOATING_REFS",
    "PLACEHOLDER_TOKENS",
    "ConfigDocument",
    "ConfigError",
    "QLoRAConfig",
    "is_floating_revision",
    "is_pinned",
    "is_placeholder_revision",
    "load_document",
    "load_draft",
]
