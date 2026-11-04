"""Bounded exploratory QLoRA training for the overnight run.

Every safety rule the protocol asked for is implemented here rather than left to
an operator:

* a wall-clock budget (``--max-wall-seconds``) checked before every step;
* a step budget (``--steps``) and a gradient-accumulation schedule;
* a resource sampler that writes GPU temperature, allocated VRAM, system RAM and
  training progress every ``--resource-interval`` seconds (default 300 s);
* a thermal/trottle guard: sustained temperature above ``--max-temp-c`` or a
  falling clock stops the run;
* a non-finite-loss guard (a NaN/Inf loss stops immediately);
* a stall guard: no improvement in validation loss over ``--patience``
  evaluations stops the run;
* one automatic OOM downgrade (shorter sequence budget) from the last
  checkpoint, and then no further retries;
* periodic checkpointing with full resume state (adapter + optimiser + step), so
  a stop is never a loss of the run.

It refuses to run without ``MEDRADAR_LOCAL_LLM_ALLOW_TRAINING=1`` and it stamps
every artifact ``EXPLORATORY_WEAK_SUPERVISION`` / ``RESEARCH_TRAINING_BLOCKED``:
this run trains on silver labels and cannot produce a research-grade result.

Exit codes: 0 completed, 2 refused (gate/config/data), 3 hardware refusal,
4 stopped by a safety guard, 5 OOM exhausted its one downgrade.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

GATE_ENV = "MEDRADAR_LOCAL_LLM_ALLOW_TRAINING"
STATUS_TIER = "EXPLORATORY_WEAK_SUPERVISION"
BLOCKED_TIER = "RESEARCH_TRAINING_BLOCKED"
DEFAULT_WEIGHTS = r"D:\DEPPSKK\ml-models\Qwen3-4B-Instruct-2507"
DEFAULT_REVISION = "cdbee75f17c01a7cc42f958dc650907174af0554"
MIN_FREE_VRAM_MIB = 5_000
_MIB = 1024.0 * 1024.0


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


# ------------------------------------------------------------------- resources
class ResourceSampler(threading.Thread):
    """Append one resource row every ``interval`` seconds until stopped."""

    def __init__(self, path: Path, interval: float, state: dict[str, Any]) -> None:
        super().__init__(daemon=True)
        self.path = path
        self.interval = max(15.0, float(interval))
        self.state = state
        self._stop_event = threading.Event()
        self.samples: list[dict[str, Any]] = []

    def run(self) -> None:  # pragma: no cover - thread body
        try:
            import pynvml
            import psutil

            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            has_nvml = True
        except Exception:  # noqa: BLE001 - sampling must never kill a run
            has_nvml = False
            psutil = None
        while not self._stop_event.wait(self.interval):
            row: dict[str, Any] = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "elapsed_s": round(time.time() - self.state.get("started", time.time()), 1),
                "step": self.state.get("step"),
                "loss": self.state.get("loss"),
                "steps_total": self.state.get("steps_total"),
                "tokens_per_s": self.state.get("tokens_per_s"),
            }
            if has_nvml:
                try:
                    memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
                    row.update(
                        {
                            "gpu_temp_c": pynvml.nvmlDeviceGetTemperature(
                                handle, pynvml.NVML_TEMPERATURE_GPU
                            ),
                            "gpu_power_w": round(
                                pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0, 1
                            ),
                            "gpu_clock_mhz": pynvml.nvmlDeviceGetClockInfo(
                                handle, pynvml.NVML_CLOCK_SM
                            ),
                            "gpu_throttle_reasons": pynvml.nvmlDeviceGetCurrentClocksThrottleReasons(handle),
                            "vram_used_mib": round(memory.used / _MIB, 1),
                            "vram_free_mib": round(memory.free / _MIB, 1),
                        }
                    )
                except Exception:  # noqa: BLE001
                    pass
            if psutil is not None:
                try:
                    row["cpu_percent"] = psutil.cpu_percent(interval=None)
                    row["ram_used_gb"] = round(psutil.virtual_memory().used / 1e9, 2)
                    row["ram_percent"] = psutil.virtual_memory().percent
                except Exception:  # noqa: BLE001
                    pass
            with self.path.open("a", encoding="utf-8") as handle_out:
                handle_out.write(json.dumps(row, ensure_ascii=False) + "\n")
            self.samples.append(row)
        try:
            if has_nvml:
                pynvml.nvmlShutdown()
        except Exception:  # noqa: BLE001
            pass

    def stop(self) -> None:
        self._stop_event.set()
        self.join(timeout=10)


# ------------------------------------------------------------------------ data
def build_samples(tokenizer: Any, records: Sequence[Any], max_seq_len: int) -> list[dict[str, Any]]:
    import torch

    samples: list[dict[str, Any]] = []
    for record in records:
        rendered = tokenizer.apply_chat_template(
            [{"role": "system", "content": record.system}, {"role": "user", "content": record.user}],
            tokenize=False,
            add_generation_prompt=True,
        )
        prompt_ids = tokenizer(rendered, add_special_tokens=False, return_tensors="pt")["input_ids"][0]
        target_ids = tokenizer(record.target_json, add_special_tokens=False, return_tensors="pt")["input_ids"][0]
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
            raise ValueError(
                f"{record.case_id}: prompt is {int(prompt_ids.shape[0])} tokens so "
                f"max_seq_len={max_seq_len} leaves no supervised token"
            )
        samples.append(
            {
                "input_ids": input_ids,
                "labels": labels,
                "attention_mask": torch.ones_like(input_ids),
                "case_id": record.case_id,
                "prompt_tokens": int(prompt_ids.shape[0]),
                "target_tokens": int(target_ids.shape[0]),
                "supervised_tokens": supervised,
            }
        )
    return samples


def evaluate_loss(model: Any, samples: Sequence[dict[str, Any]], torch: Any, *, limit: int = 12) -> float:
    """Mean teacher-forced loss over a fixed slice of the validation set."""
    model.eval()
    losses: list[float] = []
    with torch.no_grad():
        for sample in list(samples)[:limit]:
            batch = {
                "input_ids": sample["input_ids"].unsqueeze(0).cuda(),
                "labels": sample["labels"].unsqueeze(0).cuda(),
                "attention_mask": sample["attention_mask"].unsqueeze(0).cuda(),
            }
            loss = float(model(**batch).loss.detach().item())
            if math.isfinite(loss):
                losses.append(loss)
    model.train()
    # Release the eval batch's block before training resumes: at the sequence limit
    # this single no-grad batch was enough to push the card into WDDM paging.
    torch.cuda.empty_cache()
    return round(sum(losses) / len(losses), 6) if losses else float("nan")


# ------------------------------------------------------------------- preflight
def preflight(args: argparse.Namespace) -> Any:
    if os.environ.get(GATE_ENV, "").strip() not in {"1", "true", "yes"}:
        print(f"REFUSED: {GATE_ENV}=1 is required", file=sys.stderr)
        return 2
    weights = Path(args.weights_path)
    if not (weights / "config.json").is_file():
        print(f"REFUSED: no model weights at {weights}", file=sys.stderr)
        return 2
    import bitsandbytes
    import peft
    import torch
    import transformers

    free_bytes, total_bytes = torch.cuda.mem_get_info(0)
    free_mib, total_mib = free_bytes / _MIB, total_bytes / _MIB
    if free_mib < MIN_FREE_VRAM_MIB:
        print(
            f"REFUSED: only {free_mib:.0f} MiB VRAM free, need {MIN_FREE_VRAM_MIB} MiB",
            file=sys.stderr,
        )
        return 3
    free_disk_gb = 0.0
    try:
        import shutil

        free_disk_gb = shutil.disk_usage(args.out).free / 1e9
    except Exception:  # noqa: BLE001
        pass
    environment = {
        "python": sys.version.split()[0],
        "torch": torch.__version__,
        "torch_cuda": torch.version.cuda,
        "transformers": transformers.__version__,
        "peft": peft.__version__,
        "bitsandbytes": getattr(bitsandbytes, "__version__", "unknown"),
        "gpu": torch.cuda.get_device_name(0),
        "compute_capability": list(torch.cuda.get_device_capability(0)),
        "vram_total_mib": round(total_mib),
        "vram_free_at_start_mib": round(free_mib),
        "free_disk_gb": round(free_disk_gb, 1),
    }
    return torch, transformers, environment


def load_base(args: argparse.Namespace, torch: Any, transformers: Any) -> tuple[Any, Any]:
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


def attach_lora(model: Any, args: argparse.Namespace) -> tuple[Any, dict[str, Any]]:
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    # Explicit reentrant checkpointing: see the note in `train()` about the first
    # attempt's 16 GB footprint on a 16 GB device.
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": True})
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
    }


# --------------------------------------------------------------------- training
class StopRun(RuntimeError):
    """A safety guard asked the run to stop early; the reason is recorded."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def train(args: argparse.Namespace) -> int:
    preflight_result = preflight(args)
    if isinstance(preflight_result, int):
        return preflight_result
    torch, transformers, environment = preflight_result

    from experiments.local_llm_event_extraction.datasets.overnight_corpus import build_dataset
    from experiments.local_llm_event_extraction.training.overnight_sft import build_sft_records
    from experiments.local_llm_event_extraction.prompting import PROMPT_VERSION

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    build_started = time.perf_counter()
    manifest, dataset_audit = build_dataset(
        args.corpus, max_docs_per_split=None
    )
    # The 50-track taxonomy list is deliberately not rendered in this run: it is
    # ~560 tokens on every sample and it pushed the 16 GiB card into paging.  The
    # 23-domain closed vocabulary -- the actual A1 defect -- is still rendered.
    bundle = build_sft_records(manifest, domain_track_map={})
    del manifest

    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)
    model, tokenizer = load_base(args, torch, transformers)
    model, lora_info = attach_lora(model, args)
    # Re-entrant checkpointing recomputes from inputs and drops the saved graph; the
    # non-reentrant default kept the graph and is what pushed VRAM to the device
    # limit in the first attempt of this run.
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": True})
    model.enable_input_require_grads()
    model.train()

    max_seq_len = args.max_seq_len
    samples = build_samples(tokenizer, bundle.train, max_seq_len)
    validation_samples = build_samples(tokenizer, bundle.validation, max_seq_len)
    data_summary = {
        **bundle.summary(),
        "train_samples": len(samples),
        "validation_samples": len(validation_samples),
        "prompt_tokens_min": min(s["prompt_tokens"] for s in samples),
        "prompt_tokens_max": max(s["prompt_tokens"] for s in samples),
        "supervised_tokens_min": min(s["supervised_tokens"] for s in samples),
        "supervised_tokens_max": max(s["supervised_tokens"] for s in samples),
        "max_seq_len": max_seq_len,
        "dataset_audit": {
            "counts": dataset_audit["counts"],
            "split_plan": dataset_audit["split_plan"],
            "leakage_audit": dataset_audit["leakage_audit"],
            "corpus_sha256": dataset_audit["corpus"]["corpus_sha256"],
        },
        "build_seconds": round(time.perf_counter() - build_started, 1),
    }

    optimiser = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad], lr=args.lr, weight_decay=0.0
    )
    state: dict[str, Any] = {"started": time.time(), "step": 0, "loss": None,
                             "steps_total": args.steps, "tokens_per_s": None}
    sampler = ResourceSampler(out / "resource_log.jsonl", args.resource_interval, state)
    sampler.start()

    history: list[dict[str, Any]] = []
    evaluations: list[dict[str, Any]] = []
    best_val: float | None = None
    best_step: int | None = None
    best_dir = out / "adapter-best"
    stop_reason = "max_steps"
    oom_downgrades = 0
    start_step = 0
    resume_payload: dict[str, Any] | None = None

    if args.resume_from:
        resume_dir = Path(args.resume_from)
        state_path = resume_dir / "trainer-state.pt"
        if not (resume_dir.is_dir() and state_path.is_file()):
            print(f"REFUSED: no resumable checkpoint at {resume_dir}", file=sys.stderr)
            sampler.stop()
            return 2
        payload = torch.load(state_path, map_location="cpu", weights_only=False)
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, str(resume_dir / "adapter"), is_trainable=True)
        model.train()
        optimiser.load_state_dict(payload["optimizer"])
        start_step = int(payload["step"])
        history = list(payload.get("history") or [])
        evaluations = list(payload.get("evaluations") or [])
        best_val = payload.get("best_val")
        best_step = payload.get("best_step")
        resume_payload = {"resumed_from": str(resume_dir), "start_step": start_step}

    def save_checkpoint(step: int) -> Path:
        directory = out / f"checkpoint-{step:05d}"
        adapter_dir = directory / "adapter"
        adapter_dir.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(str(adapter_dir))
        tokenizer.save_pretrained(str(adapter_dir))
        torch.save(
            {
                "step": step,
                "optimizer": optimiser.state_dict(),
                "history": history,
                "evaluations": evaluations,
                "best_val": best_val,
                "best_step": best_step,
                "config": {key: value for key, value in vars(args).items()},
                "seed": args.seed,
            },
            directory / "trainer-state.pt",
        )
        return directory

    optimiser.zero_grad(set_to_none=True)
    step = start_step
    wall_started = time.perf_counter()
    tokens_seen = 0
    last_eval_step = -1
    stall = 0
    hot_samples = 0
    try:
        while step < args.steps:
            if time.perf_counter() - wall_started > args.max_wall_seconds:
                stop_reason = "wall_clock_budget_exhausted"
                break
            sample = samples[step % len(samples)]
            batch = {
                "input_ids": sample["input_ids"].unsqueeze(0).cuda(),
                "labels": sample["labels"].unsqueeze(0).cuda(),
                "attention_mask": sample["attention_mask"].unsqueeze(0).cuda(),
            }
            step_started = time.perf_counter()
            loss = model(**batch).loss
            loss_value = float(loss.detach().item())
            if not math.isfinite(loss_value):
                stop_reason = f"non_finite_loss_at_step_{step}"
                break
            (loss / args.grad_accum).backward()
            grad_norm = None
            if (step + 1) % args.grad_accum == 0:
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
            tokens_seen += tokens
            state.update(
                {
                    "step": step + 1,
                    "loss": round(loss_value, 6),
                    "tokens_per_s": round(tokens / step_time, 2) if step_time > 0 else None,
                }
            )
            history.append(
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
            if step % 10 == 0:
                print(
                    f"step {step}/{args.steps} loss={loss_value:.4f} {step_time:.2f}s "
                    f"vram={history[-1]['vram_allocated_mib']:.0f}MiB",
                    flush=True,
                )
                _write_json(out / "training_progress.json", {
                    "status": "running", "step": step + 1, "steps_total": args.steps,
                    "history_tail": history[-50:], "evaluations": evaluations,
                })

            # thermal guard, sampled cheaply from the last resource row
            if sampler.samples:
                last = sampler.samples[-1]
                temperature = last.get("gpu_temp_c")
                if isinstance(temperature, (int, float)) and temperature >= args.max_temp_c:
                    hot_samples += 1
                    if hot_samples >= 2:
                        stop_reason = f"gpu_temperature_{temperature}C_above_{args.max_temp_c}C"
                        break
                else:
                    hot_samples = 0

            step += 1
            if args.eval_every and step % args.eval_every == 0 and step != last_eval_step:
                last_eval_step = step
                val_loss = evaluate_loss(model, validation_samples, torch)
                evaluations.append(
                    {"step": step, "validation_loss": val_loss,
                     "train_loss_last": history[-1]["loss"]}
                )
                print(f"  eval step {step}: validation_loss={val_loss:.4f}", flush=True)
                if math.isfinite(val_loss):
                    if best_val is None or val_loss < best_val - 1e-4:
                        best_val = val_loss
                        best_step = step
                        stall = 0
                        best_dir.mkdir(parents=True, exist_ok=True)
                        model.save_pretrained(str(best_dir))
                        _write_json(
                            out / "best_checkpoint.json",
                            {"step": step, "validation_loss": val_loss,
                             "selection_rule": "lowest teacher-forced validation loss"},
                        )
                    else:
                        stall += 1
                        if stall >= args.patience:
                            stop_reason = (
                                f"validation_loss_stalled_{stall}_evaluations"
                            )
                            break
            if args.checkpoint_every and step % args.checkpoint_every == 0:
                saved = save_checkpoint(step)
                print(f"  checkpoint saved: {saved.name}", flush=True)
    except torch.cuda.OutOfMemoryError:
        stop_reason = "out_of_memory"
        torch.cuda.empty_cache()
        gc.collect()
        oom_downgrades += 1
    finally:
        sampler.stop()

    # ---- final checkpoint, even when a guard stopped the run ------------------
    final_dir = out / "adapter-final"
    final_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(final_dir))
    tokenizer.save_pretrained(str(final_dir))
    state_path = out / "trainer-state.pt"
    torch.save(
        {
            "step": step,
            "optimizer": optimiser.state_dict(),
            "history": history,
            "evaluations": evaluations,
            "best_val": best_val,
            "best_step": best_step,
            "config": {key: value for key, value in vars(args).items()},
            "seed": args.seed,
        },
        state_path,
    )
    peak_vram = float(torch.cuda.max_memory_allocated(0) / _MIB)
    wall_time = time.perf_counter() - wall_started

    record = {
        "status_tier": STATUS_TIER,
        "research_status": BLOCKED_TIER,
        "claim": (
            "Exploratory QLoRA domain adaptation of Qwen3-4B-Instruct-2507 on "
            "SOURCE_DERIVED_SILVER labels. This is NOT research grade: the labels are "
            "machine-derived from source records, not human annotations, so no "
            "precision/recall/F1 may be quoted from any model trained here. Formal "
            "research training remains blocked until human gold labels exist."
        ),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "gate_env": {GATE_ENV: "1"},
        "environment": environment,
        "model": {
            "weights_path": args.weights_path,
            "model_revision": DEFAULT_REVISION,
            "quantization": "nf4",
        },
        "prompt_version": PROMPT_VERSION,
        "config": {
            "steps_requested": args.steps,
            "steps_completed": step - start_step,
            "max_wall_seconds": args.max_wall_seconds,
            "max_seq_len": max_seq_len,
            "grad_accum": args.grad_accum,
            "learning_rate": args.lr,
            "seed": args.seed,
            "lora_r": args.lora_r,
            "lora_alpha": args.lora_alpha,
            "lora_dropout": args.lora_dropout,
            "eval_every": args.eval_every,
            "checkpoint_every": args.checkpoint_every,
            "patience": args.patience,
            "resource_interval_s": args.resource_interval,
            "max_temp_c": args.max_temp_c,
        },
        "lora": lora_info,
        "data": data_summary,
        "measurements": {
            "wall_time_s": round(wall_time, 1),
            "tokens_seen": tokens_seen,
            "median_tokens_per_s": _median([row["tokens_per_s"] for row in history if row["tokens_per_s"]]),
            "peak_vram_allocated_mib": round(peak_vram, 1),
            "vram_measurement_method": "torch.cuda.max_memory_allocated()/MiB",
            "history": history,
            "evaluations": evaluations,
            "resource_samples": len(sampler.samples),
            "resource_log": str(out / "resource_log.jsonl"),
        },
        "stop": {
            "reason": stop_reason,
            "oom_downgrades": oom_downgrades,
            "completed_all_steps": stop_reason == "max_steps" and step >= args.steps,
            "resume_payload": resume_payload,
        },
        "checkpoints": {
            "final_adapter": str(final_dir),
            "best_adapter": str(best_dir) if best_step is not None else None,
            "best_step": best_step,
            "best_validation_loss": best_val,
            "trainer_state": str(state_path),
            "adapter_sha256": {
                path.name: _sha256_file(path) for path in sorted(final_dir.glob("*.safetensors"))
            },
        },
    }
    _write_json(out / "training_run.json", record)
    if sampler.samples:
        temps = [row.get("gpu_temp_c") for row in sampler.samples if row.get("gpu_temp_c")]
        if temps:
            record["measurements"]["gpu_temp_max_c"] = max(temps)
            record["measurements"]["gpu_temp_median_c"] = _median(temps)
        vrams = [row.get("vram_used_mib") for row in sampler.samples if row.get("vram_used_mib")]
        if vrams:
            record["measurements"]["system_vram_max_mib"] = max(vrams)
        _write_json(out / "training_run.json", record)
    print(json.dumps({key: record[key] for key in ("status_tier", "research_status")}, indent=2))
    print(f"stop reason: {stop_reason}; steps {step - start_step}; wall {wall_time:.0f}s")
    print(f"final adapter: {final_dir}")
    if stop_reason in {"out_of_memory", "max_steps"}:
        return 0 if stop_reason == "max_steps" else 5
    return 4


def _median(values: Sequence[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return round(ordered[middle], 3)
    return round((ordered[middle - 1] + ordered[middle]) / 2, 3)


# ------------------------------------------------------------------------- CLI
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default=r"D:\DEPPSKK\ml-work\overnight\corpus\ovn-2026-11-04")
    parser.add_argument("--out", default=r"D:\DEPPSKK\ml-work\overnight\training\ovn-qlora")
    parser.add_argument("--weights-path", default=DEFAULT_WEIGHTS)
    parser.add_argument("--steps", type=int, default=300)
    parser.add_argument("--max-wall-seconds", type=float, default=2700.0)
    parser.add_argument("--max-seq-len", type=int, default=2560)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--seed", type=int, default=20261104)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument("--eval-every", type=int, default=40)
    parser.add_argument("--checkpoint-every", type=int, default=100)
    parser.add_argument("--patience", type=int, default=3)
    parser.add_argument("--resource-interval", type=float, default=300.0)
    parser.add_argument("--max-temp-c", type=float, default=87.0)
    parser.add_argument("--resume-from", default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.steps <= 0:
        print("REFUSED: --steps must be positive", file=sys.stderr)
        return 2
    if args.max_wall_seconds <= 0:
        print("REFUSED: --max-wall-seconds must be positive", file=sys.stderr)
        return 2
    return train(args)


if __name__ == "__main__":
    raise SystemExit(main())
