# Installing WSL2 + PyTorch (CUDA 12.8) for the RTX 5080 Laptop

> **NOT EXECUTED. This document is a reviewed plan, not a report of work done.**
> Nothing in this guide has been run on this machine. At the time of writing,
> WSL is not installed (`wsl.exe --status` exits 50 — measured by
> [`../scripts/env_probe.py`](../scripts/env_probe.py)), there is no CUDA toolkit,
> no PyTorch, and no virtual environment. Every command below is written for the
> **future operator** to run by hand, in order, on a day when the machine is free
> to reboot and to spend ~30–60 minutes on setup plus a multi-GB download.
>
> The documenting agent did not install anything, did not download anything, and
> did not run any of these commands. Where a claim about upstream behaviour is
> made, a URL and a retrieval date are given. Where a value is specific to this
> laptop, it is labelled MEASURED.

Companion documents:

- [`HARDWARE_COMPATIBILITY.md`](HARDWARE_COMPATIBILITY.md) — the VRAM budget and
  why QLoRA (not bf16 LoRA) is the training mode
- [`../scripts/env_probe.py`](../scripts/env_probe.py) — read-only environment probe

All URLs retrieved **2026-11-04**. Units: `GiB` for memory, `GB` for disk.

---

## 0. Baseline: what the machine is today (measured)

| Fact | Value | Label |
| --- | --- | --- |
| OS | Windows 11 build 26200.9711 (25H2), Chinese-locale | MEASURED |
| CPU | Intel Core Ultra 9 285H, 16 physical / 16 logical cores | MEASURED |
| RAM | 31.43 GiB total (33,752,924,160 B) | MEASURED |
| GPU | NVIDIA GeForce RTX 5080 Laptop GPU, 16303 MiB, driver **581.42**, compute capability **12.0 (sm_120)**, CUDA version reported by driver **13.0** | MEASURED |
| Desktop VRAM in use | 4269 MiB at probe time (3.88–4.79 GiB across runs) | MEASURED |
| WSL | **not installed**, no distributions; `wsl.exe --status` exit 50 | MEASURED |
| Python | CPython 3.12.10 at `%USERPROFILE%\AppData\Local\Programs\Python\Python312\python.exe` (no venv) | MEASURED |
| Python packages | no torch/transformers/peft/trl/accelerate/bitsandbytes/datasets; numpy/pandas/pytest/huggingface_hub/tokenizers present | MEASURED |
| CUDA toolkit | `nvcc` not found, `CUDA_PATH`/`CUDA_HOME` empty | MEASURED |
| Disk C: | 992.29 GB total, **422.8 GB free (393.8 GiB)** | MEASURED |
| Disk D: | 4000.77 GB total, **642.3 GB free (598.2 GiB)** | MEASURED |

Driver check, before anything else: **581.42 ≥ 570.65**, the CUDA 12.8 GA minimum
for Windows (DOCUMENTED — [CUDA 12.8 Release Notes](https://docs.nvidia.com/cuda/archive/12.8.0/cuda-toolkit-release-notes/index.html)),
so no driver update is needed for a `cu128` PyTorch build. If a future `cu13x`
build is chosen, re-check the minimum driver of that CUDA release first.

**Do not, at any point:**

- install an NVIDIA *Linux* driver inside WSL (DOCUMENTED prohibition — [CUDA on WSL User Guide](https://docs.nvidia.com/cuda/wsl-user-guide/index.html): "This is the only driver you need to install. Do not install any Linux display driver in WSL");
- install the `cuda`, `cuda-12-x` or `cuda-drivers` metapackages in WSL (they
  attempt to install a Linux driver — same source);
- touch the existing Windows Python environment
  (`%USERPROFILE%\AppData\Local\Programs\Python\Python312`). All Python work
  happens inside the WSL venv;
- run any of this while the evidence-validation agent is running a long job: the
  install reboots Windows, and the training step competes with it for RAM.

---

## 1. Enable the WSL2 optional features (elevated, one reboot)

Run in **PowerShell as Administrator**. This is the only step that requires
elevation.

### 1a. The single-command route (recommended)

```powershell
wsl.exe --install -d Ubuntu-24.04
```

DOCUMENTED — [Install WSL](https://learn.microsoft.com/en-us/windows/wsl/install):
`wsl --install` enables the required optional features, installs the default
Ubuntu distribution, and requires **one restart**; `-d <Distro>` selects the
distribution, and `wsl --list --online` lists the exact names available. The
guide also documents the fallback when the command prints help text instead of
installing: `wsl --list --online`, then `wsl --install -d <DistroName>`, and
`wsl --install --web-download -d <DistroName>` if the download stalls at 0.0 %.

Confirm `Ubuntu-24.04` with `wsl --list --online` **before** running the install:
the distribution name must match exactly, and the online list is the authority
for what this Windows build can fetch.

### 1b. The manual route (if 1a is unavailable on this build)

```powershell
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
```

Then **reboot**, then:

```powershell
wsl.exe --set-default-version 2
wsl.exe --install -d Ubuntu-24.04
```

`wsl --set-default-version 2` is documented on the same page; new installs via
`wsl --install` are WSL 2 by default, but an older inbox WSL may default to 1.

### 1c. Check after reboot

```powershell
wsl.exe --status
wsl.exe --version
wsl.exe -l -v
```

Expected: `--status` exits 0, `-l -v` shows `Ubuntu-24.04` with `VERSION 2`, and
`--version` prints a WSL version and a kernel version. If `--version` is not
recognised (old inbox WSL), update it:

```powershell
wsl.exe --update
```

DOCUMENTED — the CUDA-on-WSL guide's Step 2 is exactly "install WSL" then "ensure
you have the latest WSL kernel: `wsl.exe --update`".

---

## 2. Ubuntu first run

```powershell
wsl.exe -d Ubuntu-24.04
```

Create the Linux user and password when prompted (this is the account that owns
the venv and the caches; it is not a Windows account). Then, inside Ubuntu:

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y build-essential git curl ca-certificates python3-venv python3-pip
python3 --version          # expect Python 3.12.x on Ubuntu 24.04
```

`build-essential` is only needed if a CUDA extension is later compiled; the pip
wheels in this guide do not compile anything.

---

## 3. `.wslconfig`: cap the VM so Windows and the other agents keep working

Create `%UserProfile%\.wslconfig` on the **Windows** side (for this machine:
`%USERPROFILE%\.wslconfig`). The file does not exist by default and is per-user,
not per-distribution (DOCUMENTED — [Advanced settings configuration in WSL](https://learn.microsoft.com/en-us/windows/wsl/wsl-config)).

```ini
# %UserProfile%\.wslconfig  — global settings for all WSL2 distributions
[general]
# Put the distro's virtual disk on D: (598 GiB free) instead of C:
distributionInstallPath=D:\\wsl

[wsl2]
# Ceiling for the WSL VM, not a reservation: the VM grows on demand.
memory=24GB
# Leave 4 of the 16 logical cores for Windows and the other agents.
processors=12
# Disk-backed overflow instead of the WSL VM being OOM-killed. Slow: never a
# substitute for fitting the model in VRAM.
swap=16GB
swapFile=D:\\wsl\\swap.vhdx
# Cap the distro's VHD; it starts small and grows only as needed.
defaultVhdSize=150GB

[experimental]
# Return cached memory to Windows gradually when the VM is idle.
autoMemoryReclaim=gradual
```

Why `memory=24GB`:

- Windows sees **31.43 GiB** total (MEASURED). The `.wslconfig` default is 50 % of
  RAM (DOCUMENTED — same page), i.e. ~15.7 GiB, which is too tight for the
  training step's CPU-side work (tokenising, dataloader buffers, page cache).
  24 GB (~22.4 GiB) leaves **~9 GiB** for Windows, the compositor and the other
  agents while still giving the VM room.
- It is a **ceiling that is only consumed on demand**; with
  `autoMemoryReclaim=gradual`, cached pages are returned to Windows when idle.
  During a concurrent long validation job, the operator should consider lowering
  it to `memory=16GB` and running `wsl --shutdown` — coordination beats
  over-committing 32 GB.
- Do **not** set 28–30 GB: Windows itself needs 2–4 GiB, and this laptop was
  measured with only 2.27 GiB RAM available while four agents were working.

Why `swap=16GB` on `D:`: the default swap is 25 % of RAM; 16 GB is enough to
survive a brief spike without thrashing, and `D:` has more free space than `C:`.
Swap is a safety net, **not** a performance feature: it is disk-backed and will
make a too-large training step crawl rather than crash.

Apply the settings (WSL must fully stop — DOCUMENTED "8 second rule"):

```powershell
wsl.exe --shutdown
```

then start the distribution again, and verify inside WSL:

```bash
free -h            # total should be ≈22–24 GiB, not ≈16 GiB
nproc              # expect 12
df -h /            # the distro VHD
```

Note: `[general]`/`[experimental]` keys require a recent Store WSL. If
`wsl --version` shows an old inbox build, run `wsl --update` first; keys an old
WSL does not know are ignored (DOCUMENTED, same page — a malformed or unknown
configuration is ignored and WSL still starts).

---

## 4. GPU passthrough: the driver stays on Windows

Nothing is installed inside WSL for the GPU. The Windows driver is stubbed into
the VM as `libcuda.so` (DOCUMENTED — [CUDA on WSL User Guide](https://docs.nvidia.com/cuda/wsl-user-guide/index.html)).
Verify from **inside** Ubuntu:

```bash
nvidia-smi
```

Expected: the same `NVIDIA GeForce RTX 5080 Laptop GPU`, driver **581.42**, CUDA
version **13.0**, 16303 MiB total. If `nvidia-smi` is not on `PATH`:

```bash
/usr/lib/wsl/lib/nvidia-smi
```

The NVIDIA guide documents that root on bare metal (not containers) will not find
`nvidia-smi` at the expected location and that `/usr/lib/wsl/lib/` may need to be
added to `PATH`. `nvidia-smi` inside WSL has a **limited feature set** (the same
guide lists GPU utilisation and active-process queries as unsupported); for a
full process list, run `nvidia-smi` on the Windows side.

Then confirm the GPU is visible to the WSL GPU stack:

```bash
ls -l /dev/dxg              # the WSL GPU device node
```

---

## 5. Put the Hugging Face cache on D:

Model weights, tokeniser files and dataset caches are the big, disposable
downloads. Keep them on the Windows D: drive (598.2 GiB free, MEASURED) instead
of growing the WSL virtual disk.

```bash
mkdir -p /mnt/d/hf_cache
echo 'export HF_HOME=/mnt/d/hf_cache' >> ~/.bashrc
source ~/.bashrc
```

`HF_HOME` is the documented cache root for the Hugging Face stack (DOCUMENTED —
[Understand caching](https://huggingface.co/docs/huggingface_hub/guides/manage-cache));
setting the single `HF_HOME` variable keeps `huggingface_hub`, `transformers` and
`datasets` pointing at the same place, which avoids the older per-library cache
variables drifting apart. Verify:

```bash
python3 -c "import os; print(os.environ['HF_HOME'])"
```

Trade-off to accept knowingly: `/mnt/d` is DrvFs, i.e. a Windows filesystem seen
through WSL, and is slower for many small files than the ext4 VHD. Two
consequences: (a) keep the venv and any actively-written checkpoints on ext4
(`~/...`), not on `/mnt/d`; (b) if model load time is dominated by the cache read,
move the cache into ext4 and accept the larger VHD.

---

## 6. Isolated virtual environment (never touch the existing environments)

Ubuntu 24.04's system Python is externally managed (PEP 668), and the Windows
Python installation must not be touched either. Everything lives in one venv:

```bash
python3 -m venv ~/venvs/medradar-llm
source ~/venvs/medradar-llm/bin/activate
python -m pip install --upgrade pip setuptools wheel
```

Never use `sudo pip`, `pip install --user`, `--break-system-packages`, or the
Windows `python` for this work. To leave the environment: `deactivate`. To delete
it completely: `rm -rf ~/venvs/medradar-llm` (see §9).

---

## 7. Install PyTorch for sm_120 (CUDA 12.8 wheels)

Inside the activated venv:

```bash
# Pinned CUDA 12.8 build. The exact wheel for CPython 3.12 + glibc 2.28+ is listed
# in the official index (DOCUMENTED):
#   torch-2.10.0+cu128-cp312-cp312-manylinux_2_28_x86_64.whl
python -m pip install "torch==2.10.0+cu128" --index-url https://download.pytorch.org/whl/cu128
```

- The index URL is the documented CUDA 12.8 wheel index, and it exists as a
  package listing: <https://download.pytorch.org/whl/cu128/torch/> (DOCUMENTED,
  retrieved 2026-11-04). The listing contains `torch-2.10.0+cu128-cp312-cp312-manylinux_2_28_x86_64.whl`,
  which matches Ubuntu 24.04's Python 3.12 and glibc.
- Blackwell (`sm_120`) support in PyTorch starts at **2.7.0**, which added CUDA
  12.8 builds (DOCUMENTED — [PyTorch 2.7.0 release notes](https://github.com/pytorch/pytorch/releases/tag/v2.7.0)),
  so the 2.10.0 line is well inside the supported range.
- If a newer build is wanted, the same index also lists `2.11.0+cu128`; check the
  listing and pin whatever is chosen (`pip index versions torch --index-url
  https://download.pytorch.org/whl/cu128`). Pinning an exact `+cu128` version is
  deliberate: "latest" cannot be reproduced in a run manifest.
- `cu130` wheels also exist (<https://download.pytorch.org/whl/cu130/>) but the
  installed driver is reported as CUDA 13.0 by `nvidia-smi`, not necessarily as a
  full CUDA 13 toolkit; `cu128` is the narrower, better-tested assumption. Revisit
  only if a measured reason appears.

Do **not** install a CUDA toolkit just to use these wheels: the pip wheels bundle
the CUDA runtime they need, and the Windows driver is older-compatible with it.
A toolkit is only needed to *compile* extensions (`flash-attn`, custom kernels),
which this phase does not do.

---

## 8. Install the pinned training stack

Still inside the venv, from PyPI:

```bash
python -m pip install \
  "transformers==5.22.1" \
  "peft==0.21.2" \
  "trl==1.17.1" \
  "accelerate==1.15.0" \
  "bitsandbytes==0.50.2" \
  "datasets==5.1.0"
```

Versions and their release dates at retrieval (DOCUMENTED — PyPI project pages,
retrieved 2026-11-04):

| Package | Pinned version | Released | Note |
| --- | --- | --- | --- |
| `torch` | `2.10.0+cu128` | in the cu128 index (2.10.0 line) | must be a `+cu128`/`+cu13x` build; a CPU wheel silently kills the GPU path |
| `transformers` | `5.22.1` | 2026-10-30 | requires PyTorch ≥ 2.6 and Python ≥ 3.11 |
| `peft` | `0.21.2` | 2026-10-01 | LoRA/QLoRA adapters |
| `trl` | `1.17.1` | 2026-10-30 | `SFTTrainer`; requires Python ≥ 3.11 |
| `accelerate` | `1.15.0` | 2026-09-09 | device placement / mixed precision |
| `bitsandbytes` | `0.50.2` | 2026-08-27 | NF4 4-bit + 8-bit paged optimizers; Windows **and** Linux wheels published |
| `datasets` | `5.1.0` | 2026-10-05 | dataset loading / preprocessing |

Why `bitsandbytes==0.50.2` specifically: its distributed Linux x86-64 build
configuration lists **sm120** among the targets for CUDA 12.8 and CUDA 13.0–13.2
builds (DOCUMENTED — [bitsandbytes installation guide](https://huggingface.co/docs/bitsandbytes/main/en/installation)).
That is the property that matters on this GPU; an older bnb wheel built without
sm_120 fails at the first 4-bit matmul (see §10).

After installing, verify that pip did **not** replace the CUDA build of torch:

```bash
python -m pip list | grep -Ei 'torch|transformers|peft|trl|accelerate|bitsandbytes|datasets'
```

Optional, not part of phase 1: `flash-attn`. Upstream documents Linux-only
requirements, a source build requiring a CUDA toolkit, and a supported-GPU list
that does not include Blackwell for FlashAttention-2; `flash-attn-4` mentions
Blackwell but not sm_120 (see `HARDWARE_COMPATIBILITY.md` §3.6). Skip it until the
pipeline runs; PyTorch SDPA is the default attention path and is what the VRAM
budget assumes.

---

## 9. Verification gates (all run inside WSL by the operator)

Run these in order and **record the output**; they are the evidence that turns
the ASSUMED lines of `HARDWARE_COMPATIBILITY.md` into MEASURED ones.

### 9.1 GPU visible, driver correct

```bash
nvidia-smi
```

Expected: RTX 5080 Laptop GPU, driver 581.42, CUDA version 13.0, 16303 MiB.

### 9.2 Torch sees sm_120

```bash
python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available(), torch.cuda.get_device_capability())"
```

Expected: `2.10.0+cu128 12.8 True (12, 0)`.

Failure interpretation: `torch.version.cuda` empty/`None` → a CPU wheel was
installed; capability not `(12, 0)` → the wheel is not the CUDA 12.8 one, or WSL
is falling back to a different adapter.

### 9.3 One-step tiny allocation test with an explicit memory cap

```bash
python - <<'PY'
import torch

# Explicit cap: never more than 25% of the 15.92 GiB card for this test.
torch.cuda.set_per_process_memory_fraction(0.25)
assert torch.cuda.is_available()

a = torch.zeros((2048, 2048), dtype=torch.bfloat16, device="cuda")
b = a @ a.T
torch.cuda.synchronize()

free_b, total_b = torch.cuda.mem_get_info()
print("torch        :", torch.__version__, "cuda:", torch.version.cuda)
print("capability   :", torch.cuda.get_device_capability())
print("allocated MiB:", round(torch.cuda.memory_allocated() / 2**20, 1))
print("peak MiB     :", round(torch.cuda.max_memory_allocated() / 2**20, 1))
print("free GiB     :", round(free_b / 2**30, 2), "of", round(total_b / 2**30, 2))
PY
```

Expected: `capability (12, 0)`, allocated a few tens of MiB, and free memory
≈ 11–12 GiB depending on what the Windows desktop is using.

### 9.4 The bitsandbytes NF4 kernel actually runs on sm_120

This is the gate that catches a bnb wheel built without sm_120 — it fails with
`CUDA error: no kernel image is available for execution on the device`.

```bash
python - <<'PY'
import torch, bitsandbytes as bnb

print("bitsandbytes", bnb.__version__)
layer = bnb.nn.Linear4bit(64, 64, quant_type="nf4", compute_dtype=torch.bfloat16).cuda()
x = torch.randn(2, 64, dtype=torch.bfloat16, device="cuda")
y = layer(x)
print("nf4 forward OK", tuple(y.shape), y.dtype)
PY
```

### 9.5 Re-run the environment probe under Linux

The probe is stdlib-only and OS-agnostic, so running it inside WSL produces the
same JSON schema with Linux values (probes that do not apply degrade to
`"status": "unavailable"` with a reason, by design):

```bash
cd /mnt/d/DEPPSKK/worktrees/local-llm-research   # path as seen from WSL
python experiments/local_llm_event_extraction/scripts/env_probe.py --json --out /tmp/probe-wsl.json
```

Keep that JSON next to the run manifest; it is the "environment" block the run
manifest expects.

### 9.6 Before every training run

- On the **Windows** side: `nvidia-smi` — check `memory.used` by the desktop
  (measured 3.88–4.79 GiB today) and close GPU-heavy apps (browser, media player).
- Inside WSL: `free -h` — check that the WSL VM is not swapping before it starts.
- The training config must refuse to start unless
  `torch.cuda.mem_get_info()` reports enough free VRAM (9 GiB for QLoRA, 13 GiB
  for bf16 LoRA, 7 GiB for 4-bit inference) and must set
  `torch.cuda.set_per_process_memory_fraction(15.3e9 / total_bytes)` as a hard
  abort. See `HARDWARE_COMPATIBILITY.md` §5.1.

---

## 10. Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `wsl --install` prints the help text instead of installing | WSL already partly installed, or the distro name is wrong | `wsl --list --online`, then `wsl --install -d Ubuntu-24.04` (DOCUMENTED) |
| Install stalls at 0.0 % | store/download path blocked | `wsl --install --web-download -d Ubuntu-24.04` (DOCUMENTED) |
| "WSL 2 requires an update to its kernel component" / kernel too old | inbox kernel | `wsl --update`; check `wsl cat /proc/version` (DOCUMENTED, CUDA-on-WSL guide) |
| `wsl --version` unknown command | old inbox WSL | `wsl --update`; then re-apply `.wslconfig` (§3) |
| `.wslconfig` changes ignored | VM was still running | `wsl --shutdown`, wait ~8 s, restart (DOCUMENTED "8 second rule") |
| `nvidia-smi` not found inside WSL | not on `PATH` | `/usr/lib/wsl/lib/nvidia-smi`, or add `/usr/lib/wsl/lib` to `PATH` (DOCUMENTED) |
| Driver too old for the wheel | Windows driver below the CUDA release's minimum | update the **Windows** driver (≥ 570.65 for CUDA 12.8); never install a Linux driver in WSL |
| `torch.cuda.is_available()` is `False` | CPU wheel installed, or WSL 1 | check `torch.version.cuda`; reinstall from the cu128 index; `wsl -l -v` must show `VERSION 2` |
| `torch.cuda.get_device_capability()` ≠ `(12, 0)` | wrong wheel / wrong adapter | reinstall `torch==2.10.0+cu128` from the cu128 index |
| `CUDA error: no kernel image is available for execution on the device` | bitsandbytes (or another extension) built without sm_120 | confirm `bnb.__version__`, reinstall `bitsandbytes==0.50.2` (build targets include sm120); do not install an old pinned bnb |
| CUDA OOM during training | sequence too long, batch too large, desktop holding VRAM | close GPU apps; seq 2048 + bs 1 + grad-checkpointing; `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`; note gradient accumulation does **not** save VRAM |
| Training crawls | WSL is swapping, or the dataset/cache is on `/mnt/d` | check `free -h` and `vmstat 1`; move the actively-read data into ext4 |
| Windows becomes sluggish / other agents stall | WSL VM took its full `memory=` ceiling | lower `memory=16GB` in `.wslconfig`, `wsl --shutdown`, coordinate with the other agents |
| `pip install` wants to "build wheel from source" for torch/bnb | wrong index or wrong platform tag | check `pip --version`/Python version; use the exact commands in §7–§8; never `--no-binary :all:` |
| `externally-managed-environment` error | pip run outside the venv on Ubuntu 24.04 | activate the venv (§6); never use `--break-system-packages` |

---

## 11. Rollback / uninstall

Everything is reversible; none of it is shared with the existing Windows Python
environment.

```powershell
# 1. Stop the VM.
wsl.exe --shutdown

# 2. Destroy the Ubuntu distribution and its virtual disk (this deletes the venv
#    and everything inside the distro). Ask for confirmation; there is no undo.
wsl.exe --unregister Ubuntu-24.04

# 3. Remove the Windows-side artefacts (only if they are ours).
#    D:\wsl           -> distro VHD, swap file
#    D:\hf_cache      -> model/dataset cache
#    %UserProfile%\.wslconfig
Remove-Item -Recurse -Force D:\wsl, D:\hf_cache
Remove-Item -Force $env:USERPROFILE\.wslconfig
```

To disable the optional features as well (only if nothing else uses them —
Docker Desktop, Windows Sandbox and WSA can depend on `VirtualMachinePlatform`):

```powershell
dism.exe /online /disable-feature /featurename:VirtualMachinePlatform /norestart
dism.exe /online /disable-feature /featurename:Microsoft-Windows-Subsystem-Linux /norestart
# reboot
```

Notes:

- **Keep the NVIDIA Windows driver 581.42.** Do not roll it back unless a specific
  regression is attributed to it; it is the driver that makes sm_120 work.
- Unregistering the distribution is enough to remove the Python venv and all
  packages; no `pip uninstall` sweep is needed.
- `wsl --unregister` deletes data permanently; export anything worth keeping
  (`wsl --export Ubuntu-24.04 <file>.tar`) before unregistering.

---

## 12. 中文快速开始（供后续操作者使用）

本节是上面英文步骤的压缩版，供操作者快速执行与核对；技术细节以英文正文为准。
**本阶段未执行**：没有安装 WSL、没有安装任何 Python 包、没有下载模型权重。

1. **前置检查**（Windows）：`nvidia-smi` 应显示 RTX 5080 Laptop、驱动 **581.42**、
   显存 16303 MiB、`CUDA Version: 13.0`；`wsl --status` 当前返回“未安装 WSL”，属预期。
2. **管理员 PowerShell** 执行 `wsl --install -d Ubuntu-24.04`，然后**重启一次**；
   重启后 `wsl --update` 更新内核，`wsl -l -v` 应显示 `Ubuntu-24.04`、`VERSION 2`。
3. **写 `%USERPROFILE%\.wslconfig`**：`[general] distributionInstallPath=D:\\wsl`；
   `[wsl2] memory=24GB`、`processors=12`、`swap=16GB`、`swapFile=D:\\wsl\\swap.vhdx`、
   `defaultVhdSize=150GB`；`[experimental] autoMemoryReclaim=gradual`。
   改完后 `wsl --shutdown`，等约 8 秒再启动。
   （24 GB 是上限不是预占：32 GB 内存要给 Windows 和正在并发工作的其他 agent 留出约 9 GB；
   并发高峰期可临时改成 16 GB。）
4. **驱动只在 Windows 装**：绝对不要在 WSL 里装 NVIDIA Linux 驱动；
   也不要装 `cuda` / `cuda-drivers` 元包。WSL 内 `nvidia-smi` 若找不到，用
   `/usr/lib/wsl/lib/nvidia-smi`。
5. **Ubuntu 内**：`sudo apt update && sudo apt install -y build-essential python3-venv`。
6. **缓存放 D 盘**：`mkdir -p /mnt/d/hf_cache`，并在 `~/.bashrc` 加
   `export HF_HOME=/mnt/d/hf_cache`。
7. **独立虚拟环境**：`python3 -m venv ~/venvs/medradar-llm && source ~/venvs/medradar-llm/bin/activate`；
   不碰 Windows 自带 Python，不用 `sudo pip`、不用 `--break-system-packages`。
8. **装 PyTorch（CUDA 12.8）**：
   `python -m pip install "torch==2.10.0+cu128" --index-url https://download.pytorch.org/whl/cu128`
9. **装固定版本训练栈**：`transformers==5.22.1`、`peft==0.21.2`、`trl==1.17.1`、
   `accelerate==1.15.0`、`bitsandbytes==0.50.2`、`datasets==5.1.0`。
10. **验证**（缺一不可）：
    - `nvidia-smi`；
    - `python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.get_device_capability())"`
      期望 `2.10.0+cu128 12.8 (12, 0)`；
    - 带显存上限（`set_per_process_memory_fraction(0.25)`）的小矩阵乘法测试；
    - bitsandbytes 的 NF4 小层前向（验证 sm_120 kernel 存在）。
11. **训练前**：Windows 侧 `nvidia-smi` 查看桌面占用并关闭占显存的应用；
    训练脚本必须检查 `torch.cuda.mem_get_info()` 的可用显存，
    并以 15.3 GB 作为硬性上限（QLoRA 规划预算 14.3 GB）。
12. **回滚**：`wsl --shutdown` → `wsl --unregister Ubuntu-24.04` → 删除
    `D:\wsl`、`D:\hf_cache`、`.wslconfig`；需要时再用 `dism` 关闭可选功能。
    **不要卸载 Windows 显卡驱动。**

---

## 13. What this guide does not claim

- It is **not executed**. No step has been run; there is no evidence yet that the
  install works on this specific laptop, only that each step matches upstream
  documentation.
- It does **not** measure tokens/second, step time, or peak VRAM. Those come from
  the first real run, and until then the budget in `HARDWARE_COMPATIBILITY.md` is
  arithmetic.
- It does **not** install `flash-attn`, `xformers` or a CUDA toolkit; none is
  required for the QLoRA phase, and all three need a compiler toolchain.
- It does **not** download model weights. That is a separate, deliberate step
  after the verification gates in §9 pass.
