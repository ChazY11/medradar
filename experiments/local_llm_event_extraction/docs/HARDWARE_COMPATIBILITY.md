# Hardware compatibility: RTX 5080 Laptop 16 GB (Blackwell, sm_120)

**Status:** assessed, no model was loaded. Written 2026-11-04 by the environment
work package (`wp2-env`) for the MedRadar "local small-LM research foundation".
Companion documents:

- [`INSTALL_WSL2_RTX5080.md`](INSTALL_WSL2_RTX5080.md) — the install guide (not executed)
- [`../scripts/env_probe.py`](../scripts/env_probe.py) — the probe that produced the measured facts
- `tests/test_llm_research_env_probe.py` — the offline probe test suite

Every number below carries one of four labels. They are not decoration: the
project's own contract (`contracts.ResourceMeasurement`) already forbids
rendering "not measured" as zero, and this document follows the same rule.

| Label | Meaning |
| --- | --- |
| **MEASURED** | observed on this machine, today, by a command whose invocation is shown |
| **DOCUMENTED** | stated by an upstream source; URL and retrieval date given |
| **DERIVED** | arithmetic over a DOCUMENTED or MEASURED input; the inputs are shown |
| **ASSUMED** | an engineering estimate, not measured; the assumption is stated |

All URLs were retrieved on **2026-11-04** (Asia/Shanghai).

---

## 1. Verdict

| Scenario | Estimated peak VRAM | Verdict on this machine |
| --- | --- | --- |
| Qwen3-4B, NF4 4-bit, inference, 2k context, batch 1 | **4.4 – 5.6 GiB** | **Comfortable** — about half the free VRAM measured today |
| Qwen3-4B, bf16, inference, 2k context, batch 1 | **10.0 – 10.8 GiB** | **Tight** — fits, but only with the desktop's GPU use small |
| Qwen3-4B, NF4 4-bit + QLoRA (r=16, bs=1, seq 2048, grad-accum 16, grad-checkpointing) | **4.9 – 6.8 GiB** | **Comfortable** — the recommended training configuration |
| Qwen3-4B, bf16 + LoRA (same recipe, no 4-bit base) | **10.2 – 11.4 GiB** | **Tight → will not fit reliably** — one browser tab or a 4k sequence pushes it into OOM |

**Software verdict: the GPU is not the problem; the software stack is.** Today the
machine has no PyTorch, no CUDA toolkit and no WSL2 (MEASURED, §3), so *no*
scenario is currently executable. The hardware is capable of all four; the
constraint is that this is a Windows 11 WDDM laptop, and the best-tested path for
QLoRA on sm_120 is WSL2 + a CUDA 12.8 PyTorch wheel (§4).

The hardware question in one sentence: **yes, a 16 GB RTX 5080 Laptop is
sufficient for Qwen3-4B NF4 inference and for QLoRA at 2k context with
gradient checkpointing, but it is not sufficient for full-precision bf16
fine-tuning of the same model, and 16 GB is a marketing figure — ~4 GiB is
already spent by the Windows desktop before any model starts.**

---

## 2. What the probe measured

Command (from the worktree root, only writes the file it is told to write):

```text
python experiments/local_llm_event_extraction/scripts/env_probe.py --out probe.json --json
```

Probe run: `probe_version = 1.0.0`, `schema_version = env_probe.v1`,
`generated_at = 2026-11-04T07:33:56+08:00`, probe duration 3.5 s, `read_only = true`,
`limitations = []` (every probe was measured).

### 2.1 Machine facts

| Fact | Value | Label |
| --- | --- | --- |
| Host name | `WIN-QBJ1E1UD41B` | MEASURED |
| OS | Windows 11, build **26200.9711**, display version **25H2**, edition ID `CoreCountrySpecific` | MEASURED |
| OS registry quirk | `ProductName` = "Windows 10 Home China" although the build is a Windows 11 build; Windows does not update `ProductName` | MEASURED (probe emits a note about it rather than "fixing" it) |
| CPU | **Intel(R) Core(TM) Ultra 9 285H**, **16 physical / 16 logical** cores, 2900 MHz max clock | MEASURED |
| CPU identifier | `Intel64 Family 6 Model 197 Stepping 2, GenuineIntel` | MEASURED |
| RAM total | **33,752,924,160 B = 31.43 GiB** | MEASURED (`ctypes kernel32.GlobalMemoryStatusEx`) |
| RAM available at probe | 2,433,572,864 B = **2.27 GiB (93 % used)** — *volatile*: four agents were running | MEASURED |
| Disk C: | total 992.29 GB (924.14 GiB), free **422.8 GB (393.8 GiB)** | MEASURED (`shutil.disk_usage`) |
| Disk D: | total 4000.77 GB (3726.01 GiB), free **642.3 GB (598.2 GiB)** | MEASURED |
| GPU 0 | **NVIDIA GeForce RTX 5080 Laptop GPU**, driver **581.42**, VRAM **16303 MiB total**, **4269 MiB used**, **11647 MiB free** | MEASURED (`nvidia-smi --query-gpu=...`) |
| GPU compute capability | **12.0 → sm_120** (`compute_cap` field) | MEASURED |
| CUDA version reported by driver | **13.0** (`nvidia-smi` banner) — this is the runtime the driver exposes, *not* an installed toolkit | MEASURED |
| iGPU | Intel(R) Arc(TM) 140T GPU (16 GB), driver 32.0.101.8132 | MEASURED (`Get-CimInstance Win32_VideoController`) |
| NVIDIA Windows driver version (CIM form) | `32.0.15.8142` | MEASURED |
| MIG | `MIG M.: N/A` — the GPU is not partitioned, so there is no compute slice to reserve | MEASURED (`nvidia-smi` banner) |
| WSL | **not installed**: `wsl.exe --status` exits **50**, `wsl -l -v` exits 1, message (UTF-16, Chinese locale) "未安装适用于 Linux 的 Windows 子系统…" | MEASURED |
| Python | CPython **3.12.10**, MSC v.1943 64-bit, `%USERPROFILE%\AppData\Local\Programs\Python\Python312\python.exe`, not a venv | MEASURED |
| Packages present | `tokenizers 0.23.1`, `huggingface_hub 1.23.0`, `numpy 2.5.1`, `pandas 3.0.3`, `pytest 9.1.1` | MEASURED (metadata only, nothing imported) |
| Packages absent | `torch`, `transformers`, `peft`, `trl`, `accelerate`, `bitsandbytes`, `datasets`, `safetensors`, `psutil` | MEASURED |
| Safety gates | `model_load`, `training`, `network`, `remote_api` — **all closed**, raw values absent | MEASURED (`safety.gate_report()`) |
| CUDA toolkit | `nvcc` not on PATH (`Get-Command nvcc` → `CommandNotFoundException`, exit 1); `$env:CUDA_PATH` and `$env:CUDA_HOME` empty | MEASURED (separate command; the probe does not query the toolkit) |

Volatile fields: free RAM, free disk and GPU `memory.used` move between runs
across today's five probe runs, `nvidia-smi` reported **3974–4901 MiB** in use by
desktop processes. Treat the numbers above as "at 07:33 local", not as constants.

### 2.2 Why 16 GB is not 16 GiB and is not all ours

- The card reports **16303 MiB = 15.92 GiB = 17.09 GB** (1 GiB = 1024 MiB;
  1 GB = 10⁹ B). "16 GB" is the marketing name for 16303 MiB.
- On Windows WDDM there is no separate compute partition: the desktop
  compositor, Edge/WebView2, media players and *every other agent's* process
  share the same 15.92 GiB. The probe measured **4269 MiB (4.17 GiB)** in use by
  `msedgewebview2.exe` and `QQMusic.exe` alone.
- Therefore the useful number is **not** 15.92 GiB; it is `total − already used`.
  At probe time that was **11647 MiB = 11.37 GiB**.

---

## 3. Blackwell / sm_120 software support

### 3.1 Minimum NVIDIA driver

The RTX 5080 Laptop is `sm_120`. A CUDA runtime version is only usable if the
installed driver is at least the version that CUDA release shipped with.

| Claim | Value | Label / source |
| --- | --- | --- |
| CUDA 12.8 GA toolkit driver, Windows x86-64 | **≥ 570.65** | DOCUMENTED — [CUDA 12.8 Release Notes, Table 3](https://docs.nvidia.com/cuda/archive/12.8.0/cuda-toolkit-release-notes/index.html) |
| CUDA 12.8 ships Windows driver | 571.96 | DOCUMENTED — same page, Table 1 |
| CUDA 12.x minor-version compatibility, Windows | ≥ 528.33 | DOCUMENTED — same page, Table 2 |
| Installed driver | **581.42** | MEASURED |
| Verdict | 581.42 ≫ 570.65, so every CUDA 12.8 / 13.x runtime is supported | DERIVED |

Also DOCUMENTED on the CUDA 12.8 release-notes page: "This release adds compiler
support for the following Nvidia Blackwell GPU architectures: SM_100, SM_101,
**SM_120**". That is the primary source for "CUDA 12.8 is the first CUDA that
compiles for this GPU".

### 3.2 PyTorch versions that ship sm_120 kernels

| Claim | Value | Label / source |
| --- | --- | --- |
| Blackwell support added to PyTorch | **2.7.0** (released 2025-04-23) | DOCUMENTED — [PyTorch 2.7.0 release notes](https://github.com/pytorch/pytorch/releases/tag/v2.7.0): highlights "NVIDIA Blackwell Architecture Support"; CUDA section "Blackwell support added across native kernels, CUDA math libraries, and torch.compile (#145270)"; bug-fix list includes "Fix backward launch bounds again for sm100, sm120 (#150640)" |
| CUDA 12.8 builds for 2.7.0 | added in CI/CD for 2.7.0 | DOCUMENTED — same release notes, "Added support for CUDA 12.8 in CI/CD" |
| `cu128` wheel index exists | yes | DOCUMENTED — [download.pytorch.org/whl/cu128](https://download.pytorch.org/whl/cu128/) |
| `cu130` wheel index exists | yes | DOCUMENTED — [download.pytorch.org/whl/cu130](https://download.pytorch.org/whl/cu130/) |
| Pinned CUDA 12.8 build for the install guide | `torch-2.10.0+cu128-cp312-cp312-manylinux_2_28_x86_64.whl` and `...-win_amd64.whl` are both listed | DOCUMENTED — [cu128 torch index](https://download.pytorch.org/whl/cu128/torch/) |
| Latest `torch` on PyPI at retrieval | **2.15.0** (2026-10-28) | DOCUMENTED — [pypi.org/project/torch](https://pypi.org/project/torch/) |
| Which arches a given wheel contains | **not verified here** | UNVERIFIED — release notes establish Blackwell support from 2.7.0 and the index establishes the wheel exists, but the per-wheel cubin list is not published on those pages. Verify at install time with §3.3. |

### 3.3 What `torch.cuda.get_device_capability()` should return

`(12, 0)`.

- MEASURED: `nvidia-smi --query-gpu=compute_cap` reports `12.0`.
- DOCUMENTED: PyTorch's `get_device_capability()` returns the `(major, minor)`
  compute capability of the active device; `sm_120` is the architecture name for
  `(12, 0)`.
- DERIVED: therefore the verification print
  `torch.__version__, torch.version.cuda, torch.cuda.get_device_capability()`
  must show a `+cu128`/`+cu13x` build, a `12.8`/`13.x` runtime, and `(12, 0)`.
  Anything else — `(12, 0)` with a CPU-only wheel is impossible, so a wrong
  capability line means the wrong wheel was installed, not a wrong GPU.

### 3.4 Windows-native vs WSL2 for this GPU

Neither path is measured yet — WSL2 is not installed and no CUDA context has ever
been created on this machine. The comparison below is DOCUMENTED where cited and
labelled ASSUMED otherwise.

| Aspect | Windows-native | WSL2 (Ubuntu 24.04) |
| --- | --- | --- |
| PyTorch wheel | `+cu128`/`+cu13x` `win_amd64` exists (DOCUMENTED, cu128 index) | `+cu128`/`+cu13x` `manylinux_2_28_x86_64` exists (DOCUMENTED, same index) |
| bitsandbytes QLoRA | official Windows x86-64 wheel exists (DOCUMENTED, §3.5) | official Linux wheel exists |
| flash-attn | no official Windows wheel; upstream says Windows compilation "still requires more testing" (DOCUMENTED, §3.6) | still compiles from source, but the Linux path is the one upstream tests |
| Triton / `torch.compile` | Windows support is narrower (ASSUMED — not verified here) | Linux is the reference platform (ASSUMED) |
| VRAM accounting | WDDM + desktop sharing, ~4 GiB already used (MEASURED) | the same physical memory and still the same Windows desktop; the compositor does **not** disappear (ASSUMED — WSL2 does not create a second GPU memory pool) |
| File-system | native NTFS | `/mnt/d` for caches is slower than the ext4 VHD (DOCUMENTED general WSL behaviour; magnitude not measured here) |
| Kernel/extension builds | MSVC + CUDA toolkit required; none installed (MEASURED) | `build-essential` + CUDA toolkit inside WSL; nothing installed yet |
| Risk | least-known path for the HF training stack | the path the ecosystem tests, at the cost of one WSL install |

**Recommendation:** WSL2. Not because it creates VRAM, but because it removes the
Windows-only gaps in `flash-attn`, Triton and the CUDA-toolkit toolchain, and
because it matches the environment the QLoRA stack is regression-tested on. The
install is reviewed in [`INSTALL_WSL2_RTX5080.md`](INSTALL_WSL2_RTX5080.md) and
has not been executed.

### 3.5 `bitsandbytes` on Windows: current state and the real limitation

The older blanket claim "bitsandbytes does not work on Windows" is **out of date**
and must not be repeated in this project. What is documented today:

- bitsandbytes publishes **Windows 11 / Windows Server 2022+ x86-64** support for
  NVIDIA GPUs, with **LLM.int8(), QLoRA 4-bit and 8-bit optimizers all marked
  supported**. DOCUMENTED — [HF bitsandbytes installation guide](https://huggingface.co/docs/bitsandbytes/main/en/installation), retrieved 2026-11-04.
- The distributed Windows x86-64 wheels are built with **CUDA Toolkit 12.8 →
  targets sm70, sm75, sm80, sm86, sm89, sm90, sm100, sm120** and with **CUDA 13.0–13.2
  → sm75…sm120**. So a current wheel *does* contain sm_120 code. DOCUMENTED — same
  page, "Installation via PyPI" configuration table.
- Current release on PyPI: **0.50.2** (2026-08-27), with a
  `bitsandbytes-0.50.2-py3-none-win_amd64.whl` (39.1 MB). DOCUMENTED — [pypi.org/project/bitsandbytes](https://pypi.org/project/bitsandbytes/).
- Minimum requirements: Python ≥ 3.10, PyTorch ≥ 2.4. DOCUMENTED — same install guide.

Remaining Windows limitations that matter for this project:

1. **The wheel must match the CUDA runtime family.** Installing a bnb wheel whose
   build does not include sm_120 produces
   `CUDA error: no kernel image is available for execution on the device` at the
   first 4-bit matmul, not at import. This is a build/target mismatch, and it is
   the most likely failure mode on a new Blackwell laptop (ASSUMED mechanism,
   DOCUMENTED symptom class).
2. **No CUDA toolkit is installed** (MEASURED), so the fallback "compile
   bitsandbytes from source for sm_120" is *not available on this machine today*;
   only the prebuilt wheel route works without new software.
3. The rest of the stack (`transformers`, `peft`, `trl`, `accelerate`) is
   pure-Python and version-compatible across OSes; the OS-specific risk is
   concentrated in the CUDA extension packages (`bitsandbytes`, `flash-attn`,
   `xformers`).

WSL2 remains the recommendation because it gives a Linux-pinned wheel for every
one of those extension packages and because it is the platform the QLoRA stack is
developed and tested on — **not** because 4-bit does not work on Windows.

### 3.6 `flash-attn` caveats

- Upstream lists **Linux** first in its requirements and says: "Might work for
  Windows starting v2.3.2 (we've seen a few positive reports) but **Windows
  compilation still requires more testing**." DOCUMENTED — [flash-attention README](https://raw.githubusercontent.com/Dao-AILab/flash-attention/main/README.md), retrieved 2026-11-04.
- Installation requires a **CUDA toolkit**, PyTorch ≥ 2.2, `packaging`, `psutil`,
  `ninja`, and builds from source; upstream documents 3–5 min on a 64-core
  machine with `ninja` and up to **2 h without it**, and warns that too many
  parallel build jobs can exhaust RAM. DOCUMENTED — same README. This machine has
  **no nvcc** (MEASURED), so a flash-attn source build is impossible today.
- FlashAttention-2's documented supported GPU list is **"Ampere, Ada, or Hopper"** —
  Blackwell / sm_120 is **not listed**. FlashAttention-3 requires **H100/H800** and
  CUDA ≥ 12.3. FlashAttention-4 is described as "optimized for Hopper and
  Blackwell GPUs (e.g. H100, B200)" and installs with `pip install flash-attn-4`;
  whether it covers **sm_120** (consumer Blackwell) is **not stated**. DOCUMENTED
  absence + UNVERIFIED sm_120 coverage — same README.
- Consequence for this project: **do not put flash-attn in the phase-1 critical
  path.** PyTorch's `scaled_dot_product_attention` (SDPA, used by default by
  transformers) already selects a Flash-Attention-class kernel where available and
  has a memory-efficient fallback; the 2k-context budgets in §5 already assume no
  flash-attn. Revisit `flash-attn-4` only after the base pipeline runs.

### 3.7 Support matrix summary

| Component | Needed version | Why | Status on this machine |
| --- | --- | --- | --- |
| NVIDIA Windows driver | ≥ 570.65 (CUDA 12.8 GA) | sm_120 support | **581.42 — OK** (MEASURED) |
| CUDA runtime | 12.8+ (13.0 reported by driver) | sm_120 kernels | driver exposes 13.0 (MEASURED); toolkit not installed (MEASURED) |
| PyTorch | ≥ 2.7.0, `+cu128` or `+cu13x` | sm_120 kernels | not installed (MEASURED) |
| bitsandbytes | current release with sm120 build (0.50.2 at retrieval) | NF4 4-bit + 8-bit paged optimizer | not installed (MEASURED) |
| transformers / peft / trl / accelerate / datasets | 5.22.1 / 0.21.2 / 1.17.1 / 1.15.0 / 5.1.0 at retrieval | QLoRA stack | not installed (MEASURED) |
| WSL2 | 2.x with a current kernel | best-tested Linux path | **not installed** (MEASURED, exit 50) |
| flash-attn | — | optional speed/memory | not installable today (no nvcc); sm_120 support unverified |
| Display / desktop | — | shares the 15.92 GiB | ~4.17 GiB in use (MEASURED) |

---

## 4. Model facts used by the budget

Qwen3-4B (`Qwen/Qwen3-4B`) configuration, DOCUMENTED —
[config.json](https://huggingface.co/Qwen/Qwen3-4B/raw/main/config.json), retrieved 2026-11-04:

```text
hidden_size 2560 · num_hidden_layers 36 · num_attention_heads 32
num_key_value_heads 8 · head_dim 128 · intermediate_size 9728
vocab_size 151936 · tie_word_embeddings true · max_position_embeddings 40960
torch_dtype bfloat16 · architectures ["Qwen3ForCausalLM"]
```

Parameter count, DERIVED from that config (this is the arithmetic, not a quoted
spec sheet — the two happen to agree):

```text
per layer, attention : q 2560·(32·128)=10,485,760  k 2560·(8·128)=2,621,440
                       v 2,621,440                o (32·128)·2560=10,485,760   -> 26,214,400
per layer, MLP       : 3 · 2560 · 9728                                        -> 74,711,040
per layer, norms     : 2·2560 + 2·128                                              ->   5,376
per layer, total                                                              -> 100,930,816
36 layers                                                                     -> 3,633,509,376
tied embedding       : 151936 · 2560                                           ->   388,956,160
final norm                                                                    ->         2,560
TOTAL                                                                         -> 4,022,468,096  ≈ 4.022 B
non-embedding                                                                   3,633,511,936 ≈ 3.633 B
```

---

## 5. VRAM budget (formulas, assumptions, verdicts)

Units: **GiB** for VRAM (nvidia-smi reports MiB; 16303 MiB = 15.92 GiB). Where an
item is naturally expressed in GB (10⁹ B), both are given. Every line is either
DOCUMENTED/DERIVED from §4 or ASSUMED with the assumption written down.

### 5.1 Shared-VRAM ceiling

```text
physical VRAM                = 16303 MiB                       = 15.92 GiB   (MEASURED)
desktop/compositor in use    = 4269 MiB at probe time          =  4.17 GiB   (MEASURED; 3.88–4.79 GiB across runs)
free at probe time           = 11647 MiB                       = 11.37 GiB   (MEASURED)
```

**Practical budget used by the training config (ASSUMED, justified):**

```text
planning ceiling   14.3 GB  = 13.32 GiB   (reserve 2.79 GB = 2.60 GiB for the desktop)
hard abort         15.3 GB  = 14.25 GiB   (reserve 1.79 GB = 1.67 GiB)
```

Why these numbers: 14.3 GB is ~84 % of the 17.09 GB physical ceiling. That leaves
2.79 GB for the Windows compositor plus whatever else is open — which is only
enough if the heavy GPU apps seen at probe time (Edge/WebView2 and QQMusic,
4.17 GiB together) are closed. **The 14.3 GB budget is a planning ceiling, not a
promise about free memory**: today free memory is 11.37 GiB, and a QLoRA run
needs ~6 GiB, so it fits today either way; a bf16 LoRA run would not. The 15.3 GB
abort exists so that a runaway configuration pages/kills the process instead of
destabilising the desktop.

Guards the training config must implement (SPECIFIED, not yet executed):

```python
free_bytes, total_bytes = torch.cuda.mem_get_info()
required = {"qlora": 9 * 2**30, "bf16_lora": 13 * 2**30, "inference_4bit": 7 * 2**30}[mode]
assert free_bytes >= required, "refusing to start: not enough free VRAM"
torch.cuda.set_per_process_memory_fraction(15.3e9 / total_bytes)  # hard abort at 15.3 GB
```

### 5.2 Budget items

| Item | Formula | Size | Label |
| --- | --- | --- | --- |
| **bf16 weights** | 4,022,468,096 × 2 B | 8.045 GB = **7.49 GiB** | DERIVED |
| **NF4 weights, quantized linears** | 3,633,315,840 × (0.5 + 4/64) B (`nf4` 0.5 B/param + fp32 absmax per 64-block) | 2.045 GB = **1.90 GiB** | DERIVED; block size 64 and double-quant of absmax (negligible, 0.0009 GB) are ASSUMED defaults |
| **Tied embedding, left bf16** | 388,956,160 × 2 B (bitsandbytes quantizes `Linear` layers, not `nn.Embedding`) | 0.778 GB = **0.72 GiB** | DERIVED; "embedding is not quantized" is ASSUMED for the default `BitsAndBytesConfig` |
| **NF4 total weights** | 1.90 + 0.72 | 2.823 GB = **2.63 GiB** | DERIVED |
| **KV cache per 1k tokens** | 2 × 36 layers × 8 kv-heads × 128 head_dim × 2 B × 1000 | 147.46 MB = **0.137 GiB** | DERIVED from config; per-token = 73,728 elements = 144 KiB |
| KV cache, 2k context | × 2048 | 302.0 MB = **0.281 GiB** | DERIVED |
| KV cache, 4k context | × 4096 | 604.0 MB = **0.562 GiB** | DERIVED |
| **Stored activations, grad-checkpointing, seq 2048, bs 1** | 36 × 2048 × 2560 × 2 B (one layer input per layer) | 377.5 MB = **0.352 GiB** | DERIVED |
| Recompute scratch, one layer | MLP 2048×9728 bf16 ≈ 39.8 MB × ~3 buffers + attention Q/K/V ≈ 25 MB; SDPA does not materialise 32×2048×2048 scores | ≈ 0.15–0.25 GB = **0.2 GiB** | ASSUMED |
| **Logits / loss buffer, seq 2048** | 2048 × 151936 × 2 B (bf16) / × 4 B (fp32 upcast for cross-entropy) | 0.622 GB / 1.245 GB = **0.58 / 1.16 GiB** | DERIVED; "transformers computes cross-entropy over all 2048 positions in fp32" is ASSUMED and is the single largest avoidable item |
| **LoRA, attention-only (r=16)** | per layer 16·[(2560+4096)+(2560+1024)+(2560+1024)+(4096+2560)] = 327,680; ×36 | 11.80 M params = **0.293 %** of the model | DERIVED |
| **LoRA, all-linear (r=16)** | attention 327,680 + MLP 16·[(2560+9728)+(2560+9728)+(9728+2560)] = 589,824 → 917,504/layer ×36 | 33.03 M params = **0.821 %** | DERIVED |
| LoRA weights + grads (bf16) | 33.03 M × 2 B × 2 | 0.132 GB = **0.123 GiB** | DERIVED |
| Paged AdamW 8-bit states | 33.03 M × ~2.05 B (two blockwise-8-bit states + fp32 absmax per 256-block) | 0.068 GB = **0.063 GiB** | DERIVED; "paged optimizer does not add VRAM while it fits" ASSUMED |
| **LoRA overhead total (all-linear)** | weights + grads + optimizer | ≈ 0.20 GB = **0.19 GiB** | DERIVED |
| **CUDA context + cuBLAS/cuDNN handles + allocator fragmentation** | — | **0.8 GiB** | ASSUMED — not measured, because no CUDA context has been created on this machine. Replaced by a measurement in the install verification step |
| Transient dequantization buffers for NF4 matmuls | bnb dequantizes tiles, not whole layers | **0.2–0.3 GiB** | ASSUMED |

Target modules for the LoRA arithmetic: `q_proj, k_proj, v_proj, o_proj` for the
"attention-only" row and additionally `gate_proj, up_proj, down_proj` for the
"all-linear" row; rank `r = 16`, `lora_alpha = 32`, dropout 0.05 (alpha and dropout
do not change the parameter count). These are the targets the training config is
expected to use; the arithmetic above is exact for any other choice of targets on
this architecture, because `params = r·(in_features + out_features)` per module.

### 5.3 Scenario (a): NF4 4-bit inference, 2k context, batch 1

| Line | GiB |
| --- | --- |
| NF4 weights | 2.63 |
| KV cache 2k | 0.28 |
| Prefill activations + logits (worst case fp32 logits) | 1.45 |
| CUDA context + allocator | 0.80 |
| **Total (prefill peak)** | **5.16** |
| Steady-state decode (logits for 1 position) | ≈ 4.0 |

**Verdict: comfortable.** 5.2 GiB against 11.37 GiB free today; headroom > 6 GiB.
A 4k context adds only 0.28 GiB of KV and roughly 0.6 GiB more logits.

### 5.4 Scenario (b): QLoRA training — NF4 base, r=16 all-linear, bs=1, grad-accum 16, grad-checkpointing, seq 2048

| Line | GiB |
| --- | --- |
| NF4 weights (frozen) | 2.63 |
| Stored activations (checkpointed) | 0.35 |
| Recompute scratch + logits/loss | 1.36 |
| LoRA weights + grads + paged 8-bit optimizer | 0.19 |
| CUDA context + allocator | 0.80 |
| Transient dequant buffers | 0.25 |
| **Total** | **5.58** |
| Plausible range (logits bf16 instead of fp32 / fragmentation) | 4.9 – 6.8 |

**Verdict: comfortable** against both the 13.32 GiB planning ceiling and the
11.37 GiB measured free memory. Gradient accumulation does not increase VRAM
(it only lengthens the step); batch size 2 would add ~0.7 GiB of activations and
would still be comfortable.

### 5.5 Sensitivities

| Change | Δ peak | New verdict |
| --- | --- | --- |
| seq 2048 → 4096 (training) | +≈0.4 GiB stored activations, +≈0.6 GiB logits | still comfortable (~6.6 GiB) |
| batch 1 → 2 (training) | +≈0.7 GiB | still comfortable (~6.3 GiB) |
| bf16 LoRA instead of QLoRA | 2.63 → 7.49 GiB (+4.86) | **tight → will not fit reliably** |
| 8-bit KV cache (inference) | −0.14 GiB at 2k | comfortable |
| training with `use_cache=True` by mistake | +0.28 GiB per 2k | waste, not fatal |

### 5.6 Scenario (c) and (d): why full precision is the line

| Scenario | Estimate | Verdict |
| --- | --- | --- |
| bf16 inference, 2k context | 7.49 + 0.28 + 1.45 + 0.80 = **10.02 GiB** | **tight** — fits the 11.37 GiB measured free, but a browser window or a 4k prompt can OOM it |
| bf16 LoRA training, seq 2048, grad-ckpt, bs 1 | 7.49 + 0.35 + 1.36 + 0.19 + 0.80 + 0.25 = **10.44 GiB** (range 9.8–11.4) | **tight → will not fit reliably** — no margin for the desktop, no margin for a 4k sequence, and AdamW on a larger trainable set would push it over. QLoRA is the required training mode, not a preference |

---

## 6. What we did NOT do

Explicit, because a compatibility document that hides its scope is a liability:

- **No model weights were downloaded.** No Qwen3 checkpoint, tokenizer, adapter
  or dataset exists on this machine as a result of this work.
- **No CUDA context was initialised.** PyTorch is not installed (MEASURED); the
  probe only *looks* for it with `importlib.util.find_spec` and never imports it.
  `nvidia-smi` queries the driver; that is not a CUDA context.
- **No training, no fine-tuning, no inference run.**
- **No benchmark and no throughput measurement.** Tokens/second, step time and
  wall-clock training time are **not measured** and are not quoted anywhere in
  this document.
- **No VRAM measurement of a real workload.** Every GiB figure in §5 is an
  arithmetic estimate (DERIVED/ASSUMED), and the only MEASURED VRAM numbers are
  `nvidia-smi` totals/used/free while no workload was running.
- **No installation, no `wsl --install`, no driver change, no elevation, no
  network access from the probe.**
- **No flash-attn, xformers or Triton check** — none is installed and no toolchain
  exists to build them.
- The probe writes nothing unless `--out` is given; the JSON snapshot used for §2
  was written to a temp directory outside the repository.

## 7. What would change the verdict

1. A measured QLoRA run (peak `torch.cuda.max_memory_allocated()` +
   `nvidia-smi memory.used`) — replaces every ASSUMED line in §5 with a
   MEASURED one. This is the first thing to do after installation.
2. Confirming that the installed wheel really contains sm_120 cubins
   (`torch.cuda.get_device_capability() == (12, 0)` plus one real 4-bit matmul).
3. The desktop's VRAM footprint at run time: if it stays near 4 GiB, the bf16
   scenarios stay closed; if it drops below 1 GiB, bf16 inference becomes
   workable.
4. A future consumer-Blackwell `flash-attn` build — could lower the attention
   memory term, but no line in §5 depends on it.
