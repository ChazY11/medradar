# Local small-language-model research foundation

**Status: infrastructure only. No model has been run, no training has been started, and this
directory contains no scientific result.**

This is the isolated experimental module for one question:

> Can a locally hosted 1B–8B open model — untuned, or tuned with QLoRA — extract
> **time- and evidence-grounded** medical-device industry technical-development events from public
> documents more reliably than MedRadar's existing rule-based extraction?

The question is open. Nothing here asserts an answer, and nothing here may be cited as if it did.
What exists is the machinery that would make an answer measurable, plus the honest preconditions
under which the measurement is not yet possible.

## Why the question is asked this way

MedRadar's recorded position (`research/MISSION.md`, `research/RESULTS/README.md`) is that the
programme has **negative results** on prediction and **no validated change detector at the corpus'
resolution**: five findings were retracted, no forecast has matured, and there is zero prospective
calibration evidence. The binding constraint is *information*, not modelling. So the defensible
next step is not a bigger forecaster — it is a better **extractor**: if events cannot be pulled
out of documents with correct company, category, date and a locatable quote, every downstream
measurement inherits that error.

Consequently the order is fixed: **extraction first, prediction only if extraction is shown to be
measurable.**

## What is in the box

| Component | Path | What it does |
|---|---|---|
| Event contract + JSON Schema | `schema.py`, `schema/event.schema.json` | one closed-vocabulary event shape; three separate timestamps; abstention is a first-class outcome |
| Cross-module contracts | `contracts.py` | label tiers, validation verdicts, dataset/manifest/metric records, run statuses |
| Run gates | `safety.py` | four environment gates, all **closed by default** |
| Read-only label adapter | `labels.py` | reads the 69 evidence packets and reports what is actually labelled |
| Model adapter interface | `adapters/base.py` | one protocol for rules / local HF / remote API / scripted backends |
| Adapters | `adapters/` | rule-based arm (runnable offline), gated local HF arm, gated remote arm, scripted fixture arm |
| Prompt builder | `prompting.py` | one versioned prompt shared by the untuned and tuned arms |
| Response parser | `parsing.py` | strict decode; refuses to repair, refuses to guess |
| Evidence validator | `validation/` | JSON-Schema checks, verbatim quote location, entity and timestamp consistency, duplicate detection, quarantine |
| Benchmark harness | `benchmark/` | arm-agnostic, resumable runner; metrics; a report writer that cannot stamp a fixture run as a result |
| Synthetic fixtures | `datasets/` | 14 fabricated medtech documents to exercise the harness; **never** an empirical result |
| Training readiness | `training/` | QLoRA configuration draft, readiness guard, resume/logging, VRAM guard, a CLI that refuses to train |
| Environment probe | `scripts/env_probe.py` | read-only hardware/software inventory, no installs |
| Documentation | `docs/` | audit, protocol, hardware compatibility, install guide, readiness checklist, risk register, architecture |

## The three comparison arms

Everything goes through `adapters/base.ModelAdapter`, so no arm can influence the scorer:

| Arm | Adapter id | Runs today? |
|---|---|---|
| A — existing rule system | `rules-baseline` | **yes**, offline, deterministic |
| B — untuned local model | `hf-qwen3-4b` (weights not downloaded) | no — gate closed, weights absent |
| C — QLoRA-tuned model | same adapter class, different checkpoint config | no — same gate, and no human labels exist |

A missing arm is recorded as `NOT_RUN` with a reason. It is never scored as zero and never
reported as a tie.

## What "gated" means here

| Gate | Environment variable | Default |
|---|---|---|
| Load any model weights | `MEDRADAR_LOCAL_LLM_ALLOW_MODEL_LOAD` | closed |
| Run training | `MEDRADAR_LOCAL_LLM_ALLOW_TRAINING` | closed |
| Outbound network | `MEDRADAR_LOCAL_LLM_ALLOW_NETWORK` | closed |
| Remote comparison API | `MEDRADAR_LOCAL_LLM_ALLOW_REMOTE_API` | closed |

A gate opens only for an explicit truthy value; a typo fails closed. The offline test suite proves
the default posture is inert, and that importing every module does not import `torch` or
`transformers`.

## Measured current state (2026-11-04)

| Fact | Value | How it is measured |
|---|---|---|
| Evidence packets | 69 | `labels.py` over `HUMAN_REVIEW_WORKSHEET.csv` |
| Human-confirmed labels | **0** | `human_label` empty on all 69 rows |
| Machine rubric pre-annotations | 69 | `agent_preliminary_label` (45 Uncertain / 18 Routine / 6 Not assessable) — not event labels |
| Deep-case companies represented | 4 of 5 | Dräger contributes 0 packets |
| `DATA` readiness | `NOT_READY` | `NO_HUMAN_CONFIRMED_LABELS`, `COMPANY_UNDER_REPRESENTED(draeger=0<6)` |
| `PIT` readiness | `PARTIAL` | 5 unresolved availability issues in `EVIDENCE_TIME_AUDIT.json` |

Run it yourself: `python -m experiments.local_llm_event_extraction.labels --pretty`

## Hardware (measured on this machine)

RTX 5080 Laptop, 16 GB VRAM, driver 581.42, CUDA 13.0 runtime capability, Blackwell sm_120;
Core Ultra 9 285H, 32 GB RAM; **WSL2 is not installed**. Blackwell support requires a CUDA 12.8+
PyTorch build, and the desktop already holds ~3.9 GB of VRAM at idle, so the practical training
budget is below 16 GB. Details, including which numbers are measured and which are assumed:
`docs/HARDWARE_COMPATIBILITY.md`; installation: `docs/INSTALL_WSL2_RTX5080.md`.

## How to use it (offline, no GPU, no weights)

```bash
# the whole offline test suite for this module (no GPU, no weights, no network)
python -m pytest tests -k llm_research -q

# what is actually labelled
python -m experiments.local_llm_event_extraction.labels --pretty

# read-only environment inventory (no installs, no writes unless --out is given)
python experiments/local_llm_event_extraction/scripts/env_probe.py

# exercise the benchmark harness on the synthetic fixtures (writes only to a temp dir)
python -c "import tempfile; from experiments.local_llm_event_extraction.datasets import load_cases, assign_grouped_splits; \
from experiments.local_llm_event_extraction.adapters import build_registry; \
from experiments.local_llm_event_extraction.benchmark import run_benchmark; \
run_benchmark(assign_grouped_splits(load_cases()), build_registry(), output_dir=tempfile.mkdtemp())"

# prove training cannot start
python -m experiments.local_llm_event_extraction.training.run_train \
    --config  experiments/local_llm_event_extraction/training/configs/qlora_qwen3_4b.draft.json \
    --dataset-manifest /nonexistent.json --checkpoint-root /tmp/ckpt ; echo "exit=$?"
```

## What this phase deliberately did not do

- No model weights downloaded, no tokeniser loaded, no CUDA context created.
- No inference, no training, no benchmark against a real model or real labels.
- No synthetic score presented as a finding: every fixture run is stamped
  `SYNTHETIC_FIXTURE_ONLY`.
- No change to `medradar/` product code, `data/*.sqlite`, `research/studies/**` or any existing
  research artifact; no rewrite of prior results.
- No new formal study number (there is no "S-030") and no claim of a scientific contribution.

## Integration and isolation

- Nothing in this directory is packaged into the `medradar` distribution
  (`[tool.setuptools.packages.find] include = ["medradar*"]`), so `pip install medradar` is
  unaffected. The optional dependency group `local-llm` in `pyproject.toml` carries the GPU stack
  and is not installed by default.
- The module was developed in an isolated git worktree on branch `research/local-llm-foundation`,
  created from `main`, precisely so that a concurrent evidence-review task in another worktree
  could not be disturbed.

## Documentation index

| Document | Purpose |
|---|---|
| `docs/EXISTING_SYSTEM_AUDIT.md` | what may be reused, what is broken, what must not be touched |
| `docs/PROTOCOL.md` | pre-registered experiment protocol draft (needs human sign-off) |
| `docs/DATA_ADAPTER.md` | how existing artifacts map to labels, and why they are not ready |
| `docs/ARCHITECTURE.md` | component map, data flow, how to add a model |
| `docs/HARDWARE_COMPATIBILITY.md` | Blackwell / 16 GB feasibility with measured vs assumed numbers |
| `docs/INSTALL_WSL2_RTX5080.md` | WSL2 + PyTorch CUDA install guide (written, not executed) |
| `docs/READINESS_CHECKLIST.md` | gate-by-gate status and what unblocks each |
| `docs/RISK_REGISTER.md` | risks, mitigations, early-warning triggers |
