"""QLoRA **technical** smoke test: prove the training pipeline runs, nothing more.

What this script is
-------------------
A deliberately small, fully instrumented QLoRA run on the project's *synthetic*
fixtures.  It exists to answer one engineering question -- "can a real
forward/backward pass, a LoRA adapter and a checkpoint round-trip happen on this
GPU?" -- and it is **not** a capability experiment.

What this script is not
-----------------------
* It is not the formal fine-tuning run.  Formal training requires independent human
  event labels, a licence, frozen splits and a pre-registered metric; none of those
  exist, so ``run_train.py`` refuses and this script stays on synthetic fixtures.
* A falling loss here says the optimiser works. It says **nothing** about whether the
  model extracts events better.  Every artifact it writes carries
  ``"purpose": "TECHNICAL_SMOKE_TEST_ONLY"``.

What it actually does
---------------------
1. Pre-flight: refuses unless the training gate is open and the GPU has enough free
   VRAM *measured now* (not a hard-coded budget).
2. Loads the pinned base model 4-bit NF4, applies ``prepare_model_for_kbit_training``
   and a LoRA adapter; records trainable parameter counts.
3. Tokenises the SFT records (prompt tokens masked with ``-100``) and runs a manual
   AdamW loop with gradient accumulation and gradient checkpointing.
4. At the midpoint it **saves** the adapter + optimiser state, destroys the model,
   reloads the base from disk, re-applies the adapter from the checkpoint and
   **resumes** -- proving checkpoint save/restore, not asserting it.
5. Generates one sample from the reloaded adapter (proving it can be used for
   inference) and writes a machine-readable run record with measured VRAM, timings
   and losses.

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


def build_smoke_data(max_seq_len: int, tokenizer: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """SFT tensors from the synthetic fixtures, with an explicit provenance block."""
    from experiments.local_llm_event_extraction.datasets.synthetic import (
        assign_grouped_splits,
        load_cases,
    )
    from experiments.local_llm_event_extraction.training.dataset_builder import build_sft_records

    import torch

    manifest = assign_grouped_splits(load_cases())
    # Explicitly declared: the only tiers this smoke test is allowed to train on.
    bundle = build_sft_records(manifest, allowed_tiers=("synthetic_fixture",))
    records = list(bundle.train) + list(bundle.validation)
    samples: list[dict[str, Any]] = []
    for record in records:
        system = str(record["system"])
        user = str(record["user"])
        target = str(record["target_json"])
        prompt_ids = tokenizer.apply_chat_template(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt",
        )[0]
        target_ids = tokenizer(target, add_special_tokens=False, return_tensors="pt")["input_ids"][0]
        eos = tokenizer.eos_token_id
        if isinstance(eos, int):
            target_ids = torch.cat([target_ids, torch.tensor([eos], dtype=target_ids.dtype)])
        input_ids = torch.cat([prompt_ids, target_ids])
        labels = torch.cat(
            [torch.full_like(prompt_ids, -100), target_ids.clone()]
        )
        if input_ids.shape[0] > max_seq_len:
            input_ids = input_ids[:max_seq_len]
            labels = labels[:max_seq_len]
        attention_mask = torch.ones_like(input_ids)
        samples.append(
            {
                "input_ids": input_ids,
                "labels": labels,
                "attention_mask": attention_mask,
                "case_id": record.get("case_id"),
                "prompt_tokens": int(prompt_ids.shape[0]),
                "target_tokens": int(target_ids.shape[0]),
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
    }
    return samples, provenance


def _batch(samples: Sequence[dict[str, Any]], index: int, device: str, pad_id: int) -> dict[str, Any]:
    import torch

    sample = samples[index % len(samples)]
    # batch size is 1: pad nothing, hand the sample over as-is
    length = int(sample["input_ids"].shape[0])
    max_len = length
    input_ids = torch.nn.functional.pad(sample["input_ids"], (0, max_len - length), value=pad_id)
    labels = torch.nn.functional.pad(sample["labels"], (0, max_len - length), value=-100)
    attention = torch.nn.functional.pad(sample["attention_mask"], (0, max_len - length), value=0)
    return {
        "input_ids": input_ids.unsqueeze(0).to(device),
        "labels": labels.unsqueeze(0).to(device),
        "attention_mask": attention.unsqueeze(0).to(device),
    }


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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights-path", default=DEFAULT_WEIGHTS)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--steps", type=int, default=6)
    parser.add_argument("--max-seq-len", type=int, default=512)
    parser.add_argument("--grad-accum", type=int, default=2)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-new-tokens", type=int, default=64)
    parser.add_argument("--skip-resume", action="store_true")
    args = parser.parse_args(argv)

    if not _truthy(os.environ.get(GATE_ENV)):
        print(f"REFUSED: {GATE_ENV} is closed; this script does real training.", file=sys.stderr)
        return 2
    weights = Path(args.weights_path)
    if not weights.is_dir():
        print(f"REFUSED: weights directory not found: {weights}", file=sys.stderr)
        return 2

    started_wall = time.time()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        import torch
        import transformers
        import peft
        import bitsandbytes
    except ImportError as exc:
        print(f"REFUSED: the local-llm environment is incomplete: {exc}", file=sys.stderr)
        return 2

    if not torch.cuda.is_available():
        print("REFUSED: CUDA is not available to torch", file=sys.stderr)
        return 2
    free_bytes, total_bytes = torch.cuda.mem_get_info(0)
    free_mib, total_mib = free_bytes / _MIB, total_bytes / _MIB
    print(f"GPU: {torch.cuda.get_device_name(0)} free={free_mib:.0f} MiB / {total_mib:.0f} MiB")
    if free_mib < MIN_FREE_VRAM_MIB:
        print(
            f"REFUSED: only {free_mib:.0f} MiB VRAM free, need {MIN_FREE_VRAM_MIB} MiB. "
            "Close GPU-using applications and retry.",
            file=sys.stderr,
        )
        return 3

    device = "cuda"
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)

    print("loading base model (4-bit NF4) ...", flush=True)
    load_started = time.perf_counter()
    model, tokenizer = _load_base(args, torch, transformers)
    load_s = time.perf_counter() - load_started
    model, lora_info = _attach_lora(model, args)
    model.train()
    torch.cuda.synchronize()
    after_load_mib = torch.cuda.memory_allocated(0) / _MIB
    print(f"loaded in {load_s:.1f}s; allocated {after_load_mib:.0f} MiB; "
          f"trainable {lora_info['trainable_parameters']:,} ({lora_info['trainable_fraction']:.4%})", flush=True)

    samples, data_provenance = build_smoke_data(args.max_seq_len, tokenizer)
    optimiser = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad], lr=args.lr, weight_decay=0.0
    )
    torch.cuda.reset_peak_memory_stats()
    losses: list[dict[str, Any]] = []
    step_times: list[float] = []
    midpoint = max(1, args.steps // 2)
    resume_proof: dict[str, Any] = {"performed": False}
    checkpoint_dir = out_dir / f"checkpoint-step-{midpoint}"
    state_path = out_dir / f"trainer-state-step-{midpoint}.pt"

    def run_steps(start: int, stop: int) -> None:
        optimiser.zero_grad(set_to_none=True)
        for step in range(start, stop):
            step_started = time.perf_counter()
            batch = _batch(samples, step, device, int(tokenizer.pad_token_id))
            outputs = model(**batch)
            loss = outputs.loss
            (loss / args.grad_accum).backward()
            grad_norm = None
            if (step + 1) % args.grad_accum == 0:
                grad_norm = float(torch.nn.utils.clip_grad_norm_(
                    [p for p in model.parameters() if p.requires_grad], 1.0
                ))
                optimiser.step()
                optimiser.zero_grad(set_to_none=True)
            torch.cuda.synchronize()
            step_time = time.perf_counter() - step_started
            step_times.append(step_time)
            tokens = int(batch["attention_mask"].sum().item())
            losses.append(
                {
                    "step": step,
                    "loss": float(loss.detach().item()),
                    "grad_norm": grad_norm,
                    "step_time_s": round(step_time, 4),
                    "tokens": tokens,
                    "tokens_per_s": round(tokens / step_time, 2) if step_time > 0 else None,
                    "vram_allocated_mib": float(torch.cuda.memory_allocated(0) / _MIB),
                }
            )
            print(
                f"step {step}: loss={losses[-1]['loss']:.4f} "
                f"norm={grad_norm if grad_norm is None else round(grad_norm, 3)} "
                f"{step_time:.2f}s vram={losses[-1]['vram_allocated_mib']:.0f}MiB",
                flush=True,
            )

    run_steps(0, midpoint)

    print(f"saving checkpoint at step {midpoint} ...", flush=True)
    model.save_pretrained(str(checkpoint_dir))
    torch.save(
        {
            "step": midpoint,
            "optimizer": optimiser.state_dict(),
            "seed": args.seed,
            "config": vars(args),
        },
        state_path,
    )
    peak_train_mib = torch.cuda.max_memory_allocated(0) / _MIB

    if not args.skip_resume and midpoint < args.steps:
        print("destroying model and resuming from checkpoint ...", flush=True)
        del model, optimiser
        gc.collect()
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        model, tokenizer = _load_base(args, torch, transformers)
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, str(checkpoint_dir), is_trainable=True)
        model.train()
        optimiser = torch.optim.AdamW(
            [p for p in model.parameters() if p.requires_grad], lr=args.lr, weight_decay=0.0
        )
        state = torch.load(state_path, map_location="cpu", weights_only=False)
        optimiser.load_state_dict(state["optimizer"])
        resume_proof = {
            "performed": True,
            "resumed_from_step": int(state["step"]),
            "checkpoint_dir": str(checkpoint_dir),
            "optimizer_state_restored": True,
            "adapter_reloaded_into_fresh_base": True,
        }
        run_steps(midpoint, args.steps)
        peak_train_mib = max(peak_train_mib, torch.cuda.max_memory_allocated(0) / _MIB)

    final_dir = out_dir / "adapter-final"
    model.save_pretrained(str(final_dir))
    tokenizer.save_pretrained(str(final_dir))

    # Prove the saved adapter can be used for inference (reload from disk).
    print("reloading adapter for an inference smoke check ...", flush=True)
    del model
    gc.collect()
    torch.cuda.empty_cache()
    base, tokenizer = _load_base(args, torch, transformers)
    from peft import PeftModel

    inference_model = PeftModel.from_pretrained(base, str(final_dir))
    inference_model.eval()
    torch.cuda.reset_peak_memory_stats()
    prompt = (
        "You extract medtech technical-development events from public documents.\n\n"
        "DOCUMENT TEXT\nACME Medical announced FDA 510(k) clearance for the TestGuard "
        "monitor on 3 March 2025.\n\nReturn JSON only."
    )
    rendered = tokenizer.apply_chat_template(
        [{"role": "user", "content": prompt}], tokenize=False, add_generation_prompt=True
    )
    encoded = tokenizer(rendered, return_tensors="pt")
    encoded = {key: value.to(device) for key, value in encoded.items()}
    with torch.no_grad():
        generated = inference_model.generate(
            **encoded, max_new_tokens=args.max_new_tokens, do_sample=False,
            pad_token_id=tokenizer.pad_token_id,
        )
    completion = tokenizer.decode(generated[0][encoded["input_ids"].shape[1]:], skip_special_tokens=True)
    peak_inference_mib = torch.cuda.max_memory_allocated(0) / _MIB

    record = {
        "purpose": PURPOSE,
        "claim": (
            "This run proves the QLoRA pipeline executes on this GPU: real forward and "
            "backward passes, LoRA parameter updates, checkpoint save, reload and resume, "
            "and adapter inference. It is NOT evidence that training improves extraction, "
            "because the data is synthetic and there is no evaluation."
        ),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "gate_env": {GATE_ENV: "1"},
        "environment": {
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
        },
        "model": {
            "weights_path": str(weights),
            "weights_fingerprint": _fingerprint_weights(weights),
            "model_revision": DEFAULT_REVISION,
            "quantization": "nf4",
        },
        "data": data_provenance,
        "lora": lora_info,
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
        "measurements": {
            "load_seconds": round(load_s, 2),
            "steps": losses,
            "step_time_s_median": round(sorted(step_times)[len(step_times) // 2], 4) if step_times else None,
            "peak_vram_training_mib": round(peak_train_mib, 1),
            "peak_vram_inference_mib": round(peak_inference_mib, 1),
            "vram_measurement_method": "torch.cuda.max_memory_allocated()/MiB, reset before each phase",
        },
        "resume": resume_proof,
        "checkpoint": {
            "midpoint_dir": str(checkpoint_dir),
            "final_adapter_dir": str(final_dir),
            "final_adapter_files": sorted(p.name for p in final_dir.glob("*")),
            "final_adapter_sha256": {
                p.name: _sha256_file(p) for p in sorted(final_dir.glob("*.safetensors"))
            },
        },
        "inference_after_reload": {
            "prompt_chars": len(rendered),
            "completion_chars": len(completion),
            "completion": completion[:600],
        },
        "wall_time_s": round(time.time() - started_wall, 1),
    }
    record_path = out_dir / "smoke_run.json"
    record_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: record[k] for k in ("purpose", "measurements", "resume")}, indent=2)[:4000])
    print(f"\nrun record -> {record_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
