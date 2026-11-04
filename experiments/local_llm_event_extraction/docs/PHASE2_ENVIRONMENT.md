# Phase 2 environment record — Windows native CUDA 12.8 on Blackwell (sm_120)

**Status of this document:** every claim below is either **MEASURED** on this machine on
2026-11-04 or **DOCUMENTED** with a source. Nothing here is an estimate dressed up as a
measurement. The experiment code that uses this environment is
`experiments/local_llm_event_extraction/`.

This file replaces the *plan* in [`INSTALL_WSL2_RTX5080.md`](INSTALL_WSL2_RTX5080.md):
that guide proposed WSL2 + CUDA, and this phase did **not** use WSL2. Section 1 explains
why, with the measurement that decided it.

---

## 1. The decision: Windows-native cu128 wheel, not WSL2

| Option | Verdict here | Evidence |
| --- | --- | --- |
| **Windows native + `torch==2.9.1+cu128` wheel** | **CHOSEN, WORKING** | Real CUDA matmul, bf16, autograd and a 4-bit model load all ran (§4, §5) |
| WSL2 Ubuntu + CUDA | **REJECTED for this phase** | `wsl.exe --status` exits 50 and `wsl -l -v` exits 1: WSL2 is not installed. Installing it needs administrator rights, a reboot, and a kernel/feature change to global Windows configuration — the task explicitly forbids doing that unannounced, and a reboot would have destroyed a running experiment. |
| CPU-only inference | **REJECTED** | A 4B model in 4-bit on 16 CPU threads is single-digit tokens/s; the measurement of interest is GPU inference. |

The risk with a Windows-native Blackwell stack was real: sm_120 needs a CUDA 12.8+ build,
and the Windows wheel ecosystem is thinner than Linux. It is now settled by measurement,
not by assumption: the wheel exists, loads, and computes correctly.

**No system configuration was changed.** No driver install, no reboot, no
`nvidia-smi` tweak, no Windows security setting touched, no `PATH` edit, no CUDA toolkit
install. The only writes are an isolated virtual environment and caches, all on `D:`.

---

## 2. Isolation and layout

| What | Where | Note |
| --- | --- | --- |
| Virtual environment | `D:\DEPPSKK\mlenv` | `venv`, Python 3.12.10, **not** on the system Python |
| Hugging Face cache | `D:\DEPPSKK\ml-cache\hf` (`HF_HOME`) | off the system drive |
| pip cache | `D:\DEPPSKK\ml-cache\pip` (`PIP_CACHE_DIR`) | |
| Torch wheel | `D:\DEPPSKK\ml-cache\wheels\torch-2.9.1+cu128-cp312-cp312-win_amd64.whl` | 2,862,033,275 bytes, SHA-256 `3a01f0b64c10a82d444d9fd06b3e8c567b1158b76b2764b8f51bfd8f535064b0` (from the wheel index metadata) |
| Model snapshot | `D:\DEPPSKK\ml-models\Qwen3-4B-Instruct-2507` | verified per-file in `model_download.json` |
| Run artifacts | `D:\DEPPSKK\ml-work\runs` | never committed |

The MedRadar default install is untouched: no dependency was added to the `medradar`
distribution, and `pyproject.toml`'s deliberately separate `local-llm` extra is still the
only declaration. The offline test suite still runs without torch installed
(`test_importing_every_training_module_pulls_in_no_ml_library`).

---

## 3. Pinned versions (MEASURED from `pip freeze`)

| Component | Version | Why this one |
| --- | --- | --- |
| Python | 3.12.10 | only interpreter on the machine; all pins have cp312 wheels |
| torch | **2.9.1+cu128** | `cu128` is the build line that ships sm_120 kernels; 2.9.1 is the current patch of that line with a `win_amd64` cp312 wheel |
| torch (built-in) CUDA | 12.8 | reported by `torch.version.cuda`; driver 581.42 exposes CUDA 13.0 runtime capability, which is backward-compatible |
| cuDNN | 91002 | `torch.backends.cudnn.version()` |
| transformers | 5.22.1 | Qwen3 support; the audit confirmed `torch_dtype` BC, `BitsAndBytesConfig` export and `apply_chat_template` behaviour against this exact version |
| peft | 0.21.2 | `PeftModel.from_pretrained(..., is_trainable=True)` and `prepare_model_for_kbit_training` present |
| bitsandbytes | **0.50.2** | ships an official `py3-none-win_amd64` wheel; NF4 kernels ran on sm_120 (§5) |
| accelerate | 1.15.0 | `device_map` support |
| datasets | 5.1.0 | installed for completeness; the research path does not require it |
| tokenizers | 0.23.3 | |
| safetensors | 0.8.0 | |
| numpy | 2.5.4 | |
| huggingface_hub | 2.4.0 | used only by the (system-python) download helper |
| jsonschema | 4.26.0 | test-time cross-check of the project's own schema engine |

Full lock file: the run log's `pip freeze` is preserved with the run artifacts
(`requirements-freeze.txt`). The install is reproducible from
`setup_ml_env.ps1` + `install_stack.ps1` (paths at the bottom of this file).

---

## 4. CUDA verification by computation, not by `nvidia-smi`

`scripts/verify_cuda.py` allocates on the device, runs kernels and compares results with a
CPU reference. Full output: `gpu_verification.json`.

| Check | Result | Meaning |
| --- | --- | --- |
| `torch.cuda.is_available()` | **True** | a real CUDA context initialised |
| compute capability | **reported [12, 0] == expected [12, 0]** | the wheel carries sm_120 kernels |
| device | `NVIDIA GeForce RTX 5080 Laptop GPU`, 16,303 MiB, 60 SMs | matches the hardware contract |
| 1024×1024 fp32 matmul vs CPU | **PASS**, max abs error `1.22e-4` | kernels execute and produce correct numbers |
| bf16 matmul | **PASS**, mean relative error `1.78e-2` | bf16 works (needed for 4-bit compute dtype) |
| autograd + Adam step | **PASS**, grad norm `4.917`, parameter delta `0.256` | backward and optimizer kernels work — the training prerequisite |
| fp32 matmul throughput | **13.81 TFLOP/s** median over 20 synchronised runs | sanity check, not a benchmark claim |
| peak allocated during the check | 33.5 MiB | the check is small and left no memory behind |

`nvidia-smi` alone would have proven none of the middle rows. This is the evidence that
the "CUDA environment" is real rather than a driver banner.

---

## 5. Real model load and 4-bit inference (VERIFIED)

`Qwen/Qwen3-4B-Instruct-2507` at revision `cdbee75f17c01a7cc42f958dc650907174af0554`,
loaded 4-bit NF4 (double quant, bf16 compute) from the local snapshot on `cuda:0`.

The exact numbers (load time, allocated VRAM, decode tokens/s, peak VRAM per call) are in
the Phase-2 experiment report; they come from `adapter_metadata` recorded per prediction,
not from a separate estimate. The key qualitative fact for this environment record is:

* the NF4 path **did** execute on sm_120 through the official Windows bitsandbytes wheel;
  it was not assumed to work because the wheel installed.

At the time of the verification run the desktop was holding **3.7–4.9 GB** of the
16,303 MiB, so the usable budget was ~11.6–12.6 GiB. Every real experiment therefore starts
with a measured free-VRAM check rather than a fixed theoretical figure.

---

## 6. Known limitations of this environment

1. **WDDM shared memory.** The desktop compositor, browsers and other applications share
   the 15.92 GiB; free VRAM is volatile between runs. Measurements record the value at
   run time and never assume it.
2. **No MIG.** The card is not partitioned, so a crashed process releases its memory on
   exit but nothing protects the desktop from an over-allocation; the harness refuses to
   start below 5,500 MiB free (training) and pins all layers to one device so an
   over-budget configuration raises OOM rather than silently spilling to CPU.
3. **`pynvml` deprecation warning.** torch 2.9.1 emits a `FutureWarning` about the
   `pynvml` package. The package comes with bitsandbytes' dependency chain; it is a
   warning, not a functional problem, and it is left unpinned rather than fighting the
   dependency resolver.
4. **Windows has no fork.** Every measurement is in-process; there is no clean way to
   reset a CUDA context, so "peak VRAM" is reset per generation call explicitly
   (`reset_peak_memory_stats`) rather than relying on a fresh process.
5. **The wheel download path is not a mirror.** The PyTorch CDN was reachable directly
   (4–6 MB/s). If it is not reachable, the `cu128` wheel must be fetched elsewhere; no
   fallback is claimed.

---

## 7. Reproduction commands

```powershell
# 1. isolated environment + wheel (both scripts are idempotent)
powershell -NoProfile -ExecutionPolicy Bypass -File D:\DEPPSKK\ml-work\setup_ml_env.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File D:\DEPPSKK\ml-work\install_stack.ps1

# 2. prove the GPU computes, not just exists
D:\DEPPSKK\mlenv\Scripts\python.exe `
  D:\DEPPSKK\worktrees\local-llm-research\experiments\local_llm_event_extraction\scripts\verify_cuda.py `
  --out D:\DEPPSKK\ml-work\gpu_verification.json

# 3. verify the pinned weights
D:\DEPPSKK\mlenv\Scripts\python.exe D:\DEPPSKK\ml-work\verify_model.py

# 4. one-document end-to-end inference
$env:MEDRADAR_LOCAL_LLM_ALLOW_MODEL_LOAD = "1"
D:\DEPPSKK\mlenv\Scripts\python.exe `
  ...\scripts\model_smoke.py --doc-id fda510k-k260579
```
