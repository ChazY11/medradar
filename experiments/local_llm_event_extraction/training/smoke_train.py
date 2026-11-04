"""QLoRA **technical** smoke test: prove the training pipeline runs, nothing more.

What this script is
-------------------
A deliberately small, fully instrumented QLoRA run on the project's *synthetic*
fixtures.  It answers one engineering question -- "can a real forward/backward pass,
a LoRA update and a checkpoint round-trip happen on this GPU?" -- and it is **not** a
capability experiment.

What this script is not
-----------------------
* It is not the formal fine-tuning run.  Formal training requires independent human
  event labels, a licence, frozen splits and a pre-registered metric; none of those
  exist, so ``run_train.py`` refuses and this script stays on synthetic fixtures.
* A falling loss here says the optimiser works.  It says **nothing** about whether the
  model extracts events better.  Every artifact carries ``TECHNICAL_SMOKE_TEST_ONLY``.

Two phases, two processes
-------------------------
An earlier single-process version was killed during development: keeping the base
model, the resumed model and a fresh inference model alive in one process drove the
GPU to 15.8 GB and WDDM paging.  The fix is structural -- the run is two invocations:

1. ``--phase train``  : load, LoRA, real forward/backward/Adam for the first half of
   the steps, save adapter + optimiser state, exit (process exit releases VRAM).
2. ``--phase resume`` : **from a new process**, reload the base model and the adapter
   from disk, restore the optimiser state, train the remaining steps, save the final
   adapter, then reload it and generate one sample.

That makes the checkpoint claim stronger than an in-process ``del``: the resume
crosses a process boundary, so it proves the files on disk are sufficient.

Measured and recorded: trainable parameter count, per-step loss and gradient norm,
step time, tokens/s, peak VRAM per phase, and the exact commands.

Exit codes: 0 ok, 2 gate closed / bad arguments, 3 insufficient VRAM, 4 runtime error.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

GATE_ENV = "MEDRADAR_LOCAL_LLM_ALLOW_TRAINING"
PURPOSE = "TECHNICAL_SMOKE_TEST_ONLY"
DEFAULT_WEIGHTS = r"D:\DEPPSKK\ml-models\Qwen3-4B-Instruct-2507"
DEFAULT_OUT = r"D:\DEPPSKK\ml-work\training\smoke-qwen3-4b-qlora"
DEFAULT_REVISION = "cdbee75f17c01a7cc42f958dc650907174af0554"
MIN_FREE_VRAM_MIB = 5_500
_MIB = 1024.0 * 1024.0


# --------------------------------------------------------------------- utilities
def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _fingerprint_weights(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.iterdir()):
        if path.is_file():
            digest.update(path.name.encode("utf-8"))
            digest.update(str(path.stat().st_size).encode("ascii"))
    config = root / "config.json"
    if config.is_file():
        digest.update(hashlib.sha256(config.read_bytes()).digest())
    return digest.hexdigest()


def _release(torch: Any, *objects: Any) -> dict[str, Any]:
    """Drop references, collect, empty the cache; report the resulting allocation."""
    for obj in objects:
        del obj
    gc.collect()
    torch.cuda.synchronize()
    torch.cuda.empty_cache()
    return {
        "vram_allocated_after_free_mib": round(torch.cuda.memory_allocated(0) / _MIB, 1),
        "vram_reserved_after_free_mib": round(torch.cuda.memory_reserved(0) / _MIB, 1),
    }


# ------------------------------------------------------------------------ data
def build_smoke_data(tokenizer: Any, max_seq_len: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """SFT tensors from the synthetic fixtures, with an explicit provenance block."""
    import torch

    from experiments.local_llm_event_extraction.datasets.synthetic import (
        assign_grouped_splits,
        load_cases,
    )
    from experiments.local_llm_event_extraction.training.dataset_builder import build_sft_records

    manifest = assign_grouped_splits(load_cases())
    bundle = build_sft_records(manifest, allowed_tiers=("synthetic_fixture",))
    records = list(bundle.train) + list(bundle.validation)
    samples: list[dict[str, Any]] = []
    for record in records:
        system = str(record["system"])
        user = str(record["user"])
        target = str(record["target_json"])
        # Render to text, then tokenize: transformers 5 changed what
        # apply_chat_template(return_tensors=...) returns (tokenizers can hand back
        # Encoding objects), so the two-step form is the portable one.
        rendered = tokenizer.apply_chat_template(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            tokenize=False,
            add_generation_prompt=True,
        )
        prompt_ids = tokenizer(rendered, add_special_tokens=False, return_tensors="pt")["input_ids"][0]
        target_ids = tokenizer(target, add_special_tokens=False, return_tensors="pt")["input_ids"][0]
        eos = tokenizer.eos_token_id
        if isinstance(eos, int):
            target_ids = torch.cat([target_ids, torch.tensor([eos], dtype=target_ids.dtype)])
        input_ids = torch.cat([prompt_ids, target_ids])
        labels = torch.cat([torch.full_like(prompt_ids, -100), target_ids.clone()])
        if input_ids.shape[0] > max_seq_len:
            input_ids = input_ids[:max_seq_len]
            labels = labels[:max_seq_len]
        supervised = int((labels != -100).sum())
        if supervised == 0:
            # A prompt longer than max_seq_len truncates away every target token; the
            # loss is then computed over zero tokens and comes out NaN.  That is a
            # configuration bug and must never be recorded as a training run.
            raise ValueError(
                f"case {record.get('case_id')!r}: prompt is {int(prompt_ids.shape[0])} tokens, "
                f"so max_seq_len={max_seq_len} truncates the whole {int(target_ids.shape[0])}-token "
                "target and leaves no supervised token. Raise --max-seq-len."
            )
        samples.append(
            {
                "input_ids": input_ids,
                "labels": labels,
                "attention_mask": torch.ones_like(input_ids),
                "case_id": record.get("case_id"),
                "prompt_tokens": int(prompt_ids.shape[0]),
                "target_tokens": int(target_ids.shape[0]),
                "supervised_tokens": supervised,
            }
        )
    provenance = {
        "dataset": "synthetic_event_extraction_v0",
        "label_tier": "synthetic_fixture",
        "records": len(samples),
        "splits_used": ["train", "validation"],
        "bundle_sha256": getattr(bundle, "sha256", None),
        "prompt_version_note": "prompt rendered by training.dataset_builder via prompting.build_prompt",
        "targets_are": "hand-authored synthetic gold events, never real documents",
        "prompt_tokens_min": min(s["prompt_tokens"] for s in samples),
        "prompt_tokens_max": max(s["prompt_tokens"] for s in samples),
        "supervised_tokens_min": min(s["supervised_tokens"] for s in samples),
        "supervised_tokens_max": max(s["supervised_tokens"] for s in samples),
    }
    return samples, provenance


# --------------------------------------------------------------- model plumbing
def _load_base(args: argparse.Namespace, torch: Any, transformers: Any) -> tuple[Any, Any]:
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    compute_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    tokenizer = AutoTokenizer.from_pretrained(args.weights_path, local_files_only=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=compute_dtype,
    )
    dtype_kwarg = "dtype" if int(str(transformers.__version__).split(".")[0]) >= 5 else "torch_dtype"
    model = AutoModelForCausalLM.from_pretrained(
        args.weights_path,
        local_files_only=True,
        quantization_config=quantization,
        device_map={"": 0},
        **{dtype_kwarg: compute_dtype},
    )
    model.config.use_cache = False
    return model, tokenizer


def _attach_lora(model: Any, args: argparse.Namespace) -> tuple[Any, dict[str, Any]]:
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    lora = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )
    model = get_peft_model(model, lora)
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    return model, {
        "trainable_parameters": int(trainable),
        "total_parameters": int(total),
        "trainable_fraction": round(trainable / total, 8) if total else None,
        "lora_r": args.lora_r,
        "lora_alpha": args.lora_alpha,
        "lora_dropout": args.lora_dropout,
        "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    }


def _new_optimiser(model: Any, torch: Any, lr: float) -> Any:
    return torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad], lr=lr, weight_decay=0.0
    )


def _run_steps(
    *,
    model: Any,
    optimiser: Any,
    samples: Sequence[dict[str, Any]],
    torch: Any,
    start: int,
    stop: int,
    grad_accum: int,
    device: str,
) -> list[dict[str, Any]]:
    """Real forward/backward/Adam steps.  No closure keeps the model alive."""
    records: list[dict[str, Any]] = []
    optimiser.zero_grad(set_to_none=True)
    for step in range(start, stop):
        step_started = time.perf_counter()
        sample = samples[step % len(samples)]
        batch = {
            "input_ids": sample["input_ids"].unsqueeze(0).to(device),
            "labels": sample["labels"].unsqueeze(0).to(device),
            "attention_mask": sample["attention_mask"].unsqueeze(0).to(device),
        }
        loss = model(**batch).loss
        loss_value = float(loss.detach().item())
        if not (loss_value == loss_value and abs(loss_value) != float("inf")):
            raise RuntimeError(
                f"loss is not finite at step {step} (loss={loss_value!r}); refusing to record "
                "this as a training run. Check label masking, max_seq_len and learning rate."
            )
        (loss / grad_accum).backward()
        grad_norm = None
        if (step + 1) % grad_accum == 0:
            grad_norm = float(
                torch.nn.utils.clip_grad_norm_(
                    [p for p in model.parameters() if p.requires_grad], 1.0
                )
            )
            optimiser.step()
            optimiser.zero_grad(set_to_none=True)
        torch.cuda.synchronize()
        step_time = time.perf_counter() - step_started
        tokens = int(batch["attention_mask"].sum().item())
        records.append(
            {
                "step": step,
                "loss": round(loss_value, 6),
                "grad_norm": None if grad_norm is None else round(grad_norm, 6),
                "step_time_s": round(step_time, 4),
                "tokens": tokens,
                "tokens_per_s": round(tokens / step_time, 2) if step_time > 0 else None,
                "vram_allocated_mib": round(float(torch.cuda.memory_allocated(0) / _MIB), 1),
            }
        )
        print(
            f"step {step}: loss={loss_value:.4f} "
            f"norm={grad_norm if grad_norm is None else round(grad_norm, 3)} "
            f"{step_time:.2f}s vram={records[-1]['vram_allocated_mib']:.0f}MiB",
            flush=True,
        )
    return records


# ------------------------------------------------------------------- preflight
def _preflight(args: argparse.Namespace) -> Any:
    import bitsandbytes
    import peft
    import torch
    import transformers

    free_bytes, total_bytes = torch.cuda.mem_get_info(0)
    free_mib, total_mib = free_bytes / _MIB, total_bytes / _MIB
    print(f"GPU: {torch.cuda.get_device_name(0)} free={free_mib:.0f} MiB / {total_mib:.0f} MiB")
    if free_mib < MIN_FREE_VRAM_MIB:
        print(
            f"REFUSED: only {free_mib:.0f} MiB VRAM free, need {MIN_FREE_VRAM_MIB} MiB.",
            file=sys.stderr,
        )
        return 3
    environment = {
        "python": sys.version.split()[0],
        "torch": torch.__version__,
        "torch_cuda": torch.version.cuda,
        "transformers": transformers.__version__,
        "peft": peft.__version__,
        "bitsandbytes": getattr(bitsandbytes, "__version__", "unknown"),
        "gpu": torch.cuda.get_device_name(0),
        "compute_capability": list(torch.cuda.get_device_capability(0)),
        "vram_total_mib": round(total_mib, 0),
        "vram_free_at_start_mib": round(free_mib, 0),
    }
    return torch, transformers, environment


def _common_record(args: argparse.Namespace, environment: dict[str, Any]) -> dict[str, Any]:
    return {
        "purpose": PURPOSE,
        "claim": (
            "Proves the QLoRA pipeline executes on this GPU: real forward and backward "
            "passes, LoRA parameter updates, checkpoint save, reload across a process "
            "boundary, resume, and adapter inference. It is NOT evidence that training "
            "improves extraction: the data is synthetic and there is no evaluation."
        ),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "phase": args.phase,
        "gate_env": {GATE_ENV: "1"},
        "environment": environment,
        "model": {
            "weights_path": args.weights_path,
            "weights_fingerprint": _fingerprint_weights(Path(args.weights_path)),
            "model_revision": DEFAULT_REVISION,
            "quantization": "nf4",
        },
        "config": {
            "steps": args.steps,
            "max_seq_len": args.max_seq_len,
            "grad_accum": args.grad_accum,
            "learning_rate": args.lr,
            "seed": args.seed,
            "lora_r": args.lora_r,
            "lora_alpha": args.lora_alpha,
            "lora_dropout": args.lora_dropout,
        },
    }


# ----------------------------------------------------------------------- phases
def phase_train(args: argparse.Namespace) -> int:
    preflight = _preflight(args)
    if isinstance(preflight, int):
        return preflight
    torch, transformers, environment = preflight

    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    midpoint = max(1, args.steps // 2)

    started = time.perf_counter()
    model, tokenizer = _load_base(args, torch, transformers)
    load_s = time.perf_counter() - started
    model, lora_info = _attach_lora(model, args)
    model.train()
    torch.cuda.synchronize()
    samples, data_provenance = build_smoke_data(tokenizer, args.max_seq_len)
    optimiser = _new_optimiser(model, torch, args.lr)
    torch.cuda.reset_peak_memory_stats()
    steps = _run_steps(
        model=model, optimiser=optimiser, samples=samples, torch=torch,
        start=0, stop=midpoint, grad_accum=args.grad_accum, device="cuda",
    )
    peak_mib = float(torch.cuda.max_memory_allocated(0) / _MIB)

    checkpoint_dir = out_dir / f"checkpoint-step-{midpoint}"
    state_path = out_dir / f"trainer-state-step-{midpoint}.pt"
    model.save_pretrained(str(checkpoint_dir))
    torch.save(
        {"step": midpoint, "optimizer": optimiser.state_dict(), "seed": args.seed, "config": vars(args)},
        state_path,
    )
    record = _common_record(args, environment)
    record.update(
        {
            "lora": lora_info,
            "data": data_provenance,
            "measurements": {
                "load_seconds": round(load_s, 2),
                "steps": steps,
                "peak_vram_train_mib": round(peak_mib, 1),
                "vram_measurement_method": "torch.cuda.max_memory_allocated()/MiB, reset at phase start",
            },
            "checkpoint": {
                "checkpoint_dir": str(checkpoint_dir),
                "trainer_state": str(state_path),
                "trainer_state_bytes": state_path.stat().st_size,
                "adapter_files": sorted(p.name for p in checkpoint_dir.glob("*")),
                "adapter_sha256": {
                    p.name: _sha256_file(p) for p in sorted(checkpoint_dir.glob("*.safetensors"))
                },
            },
            "next_phase": (
                f"--phase resume --checkpoint {checkpoint_dir} --steps {args.steps} "
                f"--max-seq-len {args.max_seq_len} --grad-accum {args.grad_accum}"
            ),
            "wall_time_s": round(time.time() - started, 1),
        }
    )
    path = out_dir / "phase_train.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\ntrain phase done: checkpoint={checkpoint_dir} record={path}")
    return 0


def phase_resume(args: argparse.Namespace) -> int:
    preflight = _preflight(args)
    if isinstance(preflight, int):
        return preflight
    torch, transformers, environment = preflight
    from peft import PeftModel, prepare_model_for_kbit_training

    if args.checkpoint is None or not Path(args.checkpoint).is_dir():
        print("REFUSED: --checkpoint must point at the adapter saved by --phase train", file=sys.stderr)
        return 2
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    midpoint = max(1, args.steps // 2)
    state_path = out_dir / f"trainer-state-step-{midpoint}.pt"
    if not state_path.is_file():
        print(f"REFUSED: trainer state not found: {state_path}", file=sys.stderr)
        return 2

    started = time.perf_counter()
    # ---- fresh process: base model and adapter are loaded from disk --------------
    model, tokenizer = _load_base(args, torch, transformers)
    # These two calls are NOT optional on the resume path.  `prepare_model_for_kbit_training`
    # is what enables gradient checkpointing and input-require-grads; loading only the
    # adapter recreates a k-bit model with checkpointing OFF, which was measured at a
    # 30 GB peak and 87-172 s per step (WDDM oversubscription) versus 2-3 s per step here.
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    model = PeftModel.from_pretrained(model, args.checkpoint, is_trainable=True)
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
    model.train()
    torch.cuda.synchronize()
    reloaded_mib = float(torch.cuda.memory_allocated(0) / _MIB)
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    samples, data_provenance = build_smoke_data(tokenizer, args.max_seq_len)
    optimiser = _new_optimiser(model, torch, args.lr)
    state = torch.load(state_path, map_location="cpu", weights_only=False)
    optimiser.load_state_dict(state["optimizer"])
    torch.cuda.reset_peak_memory_stats()
    steps = _run_steps(
        model=model, optimiser=optimiser, samples=samples, torch=torch,
        start=int(state["step"]), stop=args.steps, grad_accum=args.grad_accum, device="cuda",
    )
    peak_train_mib = float(torch.cuda.max_memory_allocated(0) / _MIB)

    final_dir = out_dir / "adapter-final"
    model.save_pretrained(str(final_dir))
    tokenizer.save_pretrained(str(final_dir))
    adapter_sha = {p.name: _sha256_file(p) for p in sorted(final_dir.glob("*.safetensors"))}
    del optimiser
    free_after_train = _release(torch, model)

    # ---- inference from the saved adapter, after freeing the training model ------
    torch.cuda.reset_peak_memory_stats()
    base, tokenizer = _load_base(args, torch, transformers)
    inference_model = PeftModel.from_pretrained(base, str(final_dir))
    inference_model.eval()
    prompt = (
        "You extract medtech technical-development events from public documents.\n\n"
        "DOCUMENT TEXT\nACME Medical announced FDA 510(k) clearance for the TestGuard "
        "monitor on 3 March 2025.\n\nReturn JSON only."
    )
    rendered = tokenizer.apply_chat_template(
        [{"role": "user", "content": prompt}], tokenize=False, add_generation_prompt=True
    )
    encoded = tokenizer(rendered, return_tensors="pt")
    encoded = {key: value.to("cuda") for key, value in encoded.items()}
    with torch.no_grad():
        generated = inference_model.generate(
            **encoded, max_new_tokens=args.max_new_tokens, do_sample=False,
            pad_token_id=tokenizer.pad_token_id,
        )
    completion = tokenizer.decode(generated[0][encoded["input_ids"].shape[1]:], skip_special_tokens=True)
    peak_inference_mib = float(torch.cuda.max_memory_allocated(0) / _MIB)

    record = _common_record(args, environment)
    record.update(
        {
            "data": data_provenance,
            "measurements": {
                "vram_after_adapter_reload_mib": round(reloaded_mib, 1),
                "trainable_parameters_after_reload": int(trainable),
                "steps": steps,
                "peak_vram_resume_train_mib": round(peak_train_mib, 1),
                "release_after_train": free_after_train,
                "peak_vram_inference_mib": round(peak_inference_mib, 1),
                "vram_measurement_method": "torch.cuda.max_memory_allocated()/MiB, reset per phase segment",
            },
            "resume": {
                "performed": True,
                "process_boundary": True,
                "resumed_from_step": int(state["step"]),
                "checkpoint": args.checkpoint,
                "optimizer_state_restored": True,
                "adapter_reloaded_into_fresh_base": True,
            },
            "checkpoint": {
                "final_adapter_dir": str(final_dir),
                "final_adapter_files": sorted(p.name for p in final_dir.glob("*")),
                "final_adapter_sha256": adapter_sha,
            },
            "inference_after_reload": {
                "prompt_chars": len(rendered),
                "completion_chars": len(completion),
                "completion": completion[:800],
            },
            "wall_time_s": round(time.time() - started, 1),
        }
    )
    path = out_dir / "smoke_run.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: record[k] for k in ("purpose", "resume", "measurements")}, indent=2)[:4000])
    print(f"\nresume phase done: record={path}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["train", "resume"], required=True)
    parser.add_argument("--checkpoint", default=None)
    parser.add_argument("--weights-path", default=DEFAULT_WEIGHTS)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--steps", type=int, default=6)
    parser.add_argument("--max-seq-len", type=int, default=2048)
    parser.add_argument("--grad-accum", type=int, default=2)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-new-tokens", type=int, default=64)
    args = parser.parse_args(argv)

    if not _truthy(os.environ.get(GATE_ENV)):
        print(f"REFUSED: {GATE_ENV} is closed; this script does real training.", file=sys.stderr)
        return 2
    if not Path(args.weights_path).is_dir():
        print(f"REFUSED: weights directory not found: {args.weights_path}", file=sys.stderr)
        return 2
    try:
        if args.phase == "train":
            return phase_train(args)
        return phase_resume(args)
    except RuntimeError as exc:
        print(f"STOPPED: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
