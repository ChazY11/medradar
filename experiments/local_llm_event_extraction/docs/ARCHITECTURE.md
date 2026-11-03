# ARCHITECTURE — the local small-LM research foundation

**Status:** describes an **experimental** package (`experiments/local_llm_event_extraction/`). Nothing in it has been run
on a model: no weights loaded, no training executed, no evaluation executed. Where a module is *not yet present* in this
checkout, the table says so instead of describing it as if it existed (`benchmark/runner.py` is WP4's remaining piece at
the time of writing; the frozen contract for it is already in `contracts.py`).

The package is a research instrument, not a product. Its design goal is that a *number* it produces can be trusted:
every step is either frozen or explicitly experimental, every artefact records the versions that produced it, and every
expensive or network-touching capability is refused by default.

---

## 1. Layering and component map

```
                     frozen contracts (do not edit)
  schema.py ── contracts.py ── safety.py ── adapters/base.py
       │            │              │             │
       │            │              │             └── adapter protocol (A/B/C, gates)
       │            │              └── four default-closed gates
       │            └── label tiers, dataset/manifest/metric contracts
       └── the event shape + JSON Schema (v1)

  ── evaluation pipeline (experimental) ──────────────────────────────────────────
  SourceDocument → prompting.build_prompt → adapter.generate → parsing.parse
                 → validation.validate_extraction → benchmark (runner/metrics/report)
                 → RunManifest + report (status: RESEARCH_GRADE | SYNTHETIC_FIXTURE_ONLY)

  ── data + training readiness (experimental, never executed in this phase) ──────
  labels.py (read-only over the 69 packets) → DatasetManifest/DatasetCase
                 → training/dataset_builder.build_sft_records → SFTBundle
                 → training/guard.assess_readiness → (refuse) → training/run_train.py (exit 2/3/4)
```

| Path | Role | Status |
|---|---|---|
| `schema.py` | Event contract: `ExtractionResult`, `EventExtraction`, `EvidenceSpan`, `TimestampQuality`, closed vocabularies, JSON Schema | **FROZEN** |
| `contracts.py` | `DatasetCase`, `DatasetManifest`, `GoldEvent`, `RunManifest`, `MetricReport`, `ResourceMeasurement`, `ValidationConfig`, `LABEL_TIERS`, `RESEARCH_GRADE_TIERS`, `is_research_grade`, `require_consistent_run_status` | **FROZEN** |
| `safety.py` | `GATES`, `gate_open`, `require_gate`, `gate_report`, `all_gates_closed` — `model_load`, `training`, `network`, `remote_api`, all default-closed | **FROZEN** |
| `adapters/base.py` | `AdapterDescriptor`, `ModelAdapter`, `AdapterRegistry`, `ExtractionRequest`, `AdapterResponse`, `Prompt` | **FROZEN** |
| `adapters/` (`rule_based`, `hf_local`, `openai_compat`, `mock`) | Arm implementations + `config/models.example.json` descriptors | experimental |
| `prompting.py` | the one versioned prompt (`build_prompt`, `prompt_fingerprint`, truncation marker) shared by arms B and C | experimental |
| `parsing.py` | model text → contracted payload; strict, never repairs, reports `parse_status` | experimental |
| `validation/` (`validator`, `schema_validator`, `evidence`, `entities`, `timefields`, `dedup`) | verbatim-quote location, entity roster, temporal consistency, duplicate detection, quarantine | experimental |
| `validation/validator.py` | frozen entry point `validate_extraction(...)` (see §3) | experimental module, frozen signature |
| `benchmark/` (`runner`, `metrics`, `report`) | arm-agnostic runner, scorer, report writer. `metrics.py` present; `runner.py`/`report.py` in progress | experimental, partially present |
| `datasets/` (`synthetic`, `splits`) | fixtures (`SYNTHETIC_FIXTURE_ONLY`) and grouped split assignment | experimental |
| `labels.py` | **read-only** adapter over the 69 evidence packets; derives `DATA_READY`/`PIT_READY` mechanically | experimental |
| `training/guard.py` | readiness assessment, 10 named blockers, warnings, `TrainingRefused` | experimental |
| `training/qlora_config.py` | `QLoRAConfig` draft + validation + pin rule + `load_draft`/`load_document` | experimental |
| `training/dataset_builder.py` | `build_sft_records` → `SFTBundle`; refuses weak tiers instead of filtering | experimental |
| `training/runlog.py` | append-only JSONL run log (`RunLog`), UTC timestamps, path-escape refusal | experimental |
| `training/checkpoint.py` | `ResumePlan`, `plan_resume`, `write_state`, path-traversal refusal | experimental |
| `training/vram_guard.py` | `VramBudget.decide` — deterministic continue/warn/abort at measured VRAM | experimental |
| `training/run_train.py` | refusal CLI: exit 2 (gate closed), 3 (not ready), **4 = phase guard (deliberate)** | experimental, intentionally inert |
| `training/configs/qlora_qwen3_4b.draft.json` | the QLoRA draft: `enabled=false`, `executed=false`, `revision=PENDING-A-PIN`, provenance `_notes` | data |
| `scripts/env_probe.py` | read-only hardware/software inventory, never installs | experimental |
| `tests/test_llm_research_training.py` | offline proof of every refusal path and the ready path | test |
| `docs/` | this file + protocol, readiness, risks, hardware, install, audit, data adapter | documentation |

## 2. Data flow, in the order it happens

1. **Document** — `schema.SourceDocument(doc_id, source_type, text, title, published_at, first_seen_at, retrieved_at,
   url, publisher, metadata)`. Three time fields are kept distinct on purpose: `event_date` (when it happened),
   `published_at` (when the source published it), `first_seen_at` (when *our collector* saw it). Availability is
   `PIT_NOT_READY`/partial and is not treated as a publication date.
2. **Prompt** — `prompting.build_prompt(document, *, max_input_chars=..., company_hint=None) -> Prompt`. The prompt knows
   nothing about the arm, so arms B and C are comparable by construction; its version and template sha are recorded in the
   run manifest.
3. **Adapter** — `ModelAdapter.generate(ExtractionRequest) -> AdapterResponse`. `load()` must call `check_gate()` first;
   a missing gate raises `AdapterGateClosed`, never a silent fallback.
4. **Parse** — `parsing.py` turns response text into the contracted payload shape or reports a `parse_status`
   (`invalid_json`/`refused`/`empty`). No repair.
5. **Validate** — `validation.validate_extraction(result, document=doc, roster=..., taxonomy=...,
   config=ValidationConfig()) -> ValidationResult`. Quotes are located verbatim, entities checked against the roster, the
   three timestamps checked for consistency, duplicates found, and bad events are **quarantined, not deleted**.
6. **Score** — the benchmark computes `contracts.MetricReport` under the frozen matching protocol (see `PROTOCOL.md` §9).
7. **Record** — `contracts.RunManifest` (adapter, dataset, config sha, git commit/branch/dirty, seeds, environment,
   status) + `ResourceMeasurement` (measured values only; `None` = not measured). The status is checked with
   `require_consistent_run_status`, so a fixture run cannot claim `RESEARCH_GRADE`.
8. **Training readiness (separate, later path)** — `DatasetManifest`/`DatasetCase` labels → `build_sft_records`
   (refuses non-research tiers, empty splits, leakage) → `assess_readiness` (blocks, with reasons) → `run_train` (refuses).

## 3. Frozen signatures

```python
# validation/validator.py
validate_extraction(result: ExtractionResult, *, document, roster: EntityRoster,
                    taxonomy: Taxonomy,
                    config: ValidationConfig = ValidationConfig()) -> ValidationResult

# benchmark/runner.py (contract frozen in contracts.py; module in progress)
run_benchmark(dataset, adapters, output_dir=..., seeds=(...)) -> BenchmarkRun

# safety.py
gate_open(gate: str, environ: Mapping[str, str] | None = None) -> bool
require_gate(gate: str, *, reason: str = "", environ=None) -> None
gate_report(environ=None) -> dict[str, dict[str, object]]
all_gates_closed(environ=None) -> bool

# contracts.py
is_research_grade(tiers) -> bool
require_consistent_run_status(status: str, tiers) -> str

# training/guard.py
assess_readiness(*, dataset=None, checkpoint_root=None, config=None, environ=None,
                 explicit_flag=False, require_human_labels=True,
                 min_train_cases=48, min_validation_cases=12, min_test_cases=24,
                 min_disk_gb=20.0, max_vram_budget_mb=14336) -> TrainingReadiness
require_ready(readiness: TrainingReadiness) -> None        # raises TrainingRefused

# training/qlora_config.py
QLoRAConfig.from_dict(payload) -> QLoRAConfig
QLoRAConfig.validate(*, draft: bool = True) -> QLoRAConfig  # raises ConfigError
load_draft(path=None) -> QLoRAConfig
load_document(path=None) -> ConfigDocument                  # config + "_" metadata + sha256

# training/dataset_builder.py
build_sft_records(manifest, *, allowed_tiers=RESEARCH_GRADE_TIERS,
                  prompt_builder=None) -> SFTBundle        # raises DataNotReady

# training/runlog.py / checkpoint.py / vram_guard.py
RunLog(root, name="runlog.jsonl").append(event, payload) -> dict ; .read_all() ; .latest_status() ; .to_json()
plan_resume(root, run_id) -> ResumePlan | None ; write_state(root, run_id, payload) -> Path
VramBudget(total_mb, warn_at_mb, abort_at_mb).decide(used_mb, reserved_mb) -> Decision

# training/run_train.py  (CLI)
python -m experiments.local_llm_event_extraction.training.run_train \
    --config <json> --dataset-manifest <json> --checkpoint-root <dir> \
    [--enable-training] [--i-understand]        # exit 2 | 3 | 4; never trains
```

## 4. Frozen vs experimental

**Frozen** (changing one is a schema/protocol event, not a refactor): `schema.py`, `contracts.py`, `safety.py`,
`adapters/base.py`, and the `validate_extraction`/`run_benchmark` entry-point signatures documented in `contracts.py`.

**Experimental** (can change, but every change must keep the frozen contracts and the offline suite green): everything
under `adapters/` except `base.py`, `prompting.py`, `parsing.py`, `validation/` internals, `benchmark/` internals,
`datasets/`, `training/`, `scripts/`, `docs/`.

**Never modified by this package:** `medradar/`, `research/`, `data/*.sqlite`, existing tests and frozen results. The
experiment reads them read-only at most.

## 5. How to add a new model adapter

1. Implement `ModelAdapter` (`adapters/base.py`): `descriptor`, `is_loaded`, `load()` (call `check_gate()` first),
   `generate()`. Import heavy libraries **inside** `load()`, never at module scope.
2. Declare an `AdapterDescriptor` with a stable `adapter_id`, `model_id`, a **pinned** `model_revision`, `backend`,
   `device`, `requires_gpu`/`requires_network`, `load_gate`, `deterministic`, `enabled_by_default=False`.
3. Register a factory in `adapters/__init__.py` (`AdapterRegistry.register`). Nothing is instantiated at import time.
4. Add the descriptor to `adapters/config/models.example.json` (environment-variable references, never absolute paths).
5. If it is a training arm, reference the adapter id from the QLoRA config (`base_adapter_id`) instead of a path.
6. Add an offline refusal test: with the gate closed the adapter must raise `AdapterGateClosed`, and importing the module
   must not put `torch`/`transformers` in `sys.modules`.
7. If it becomes an arm of the protocol, add it to `PROTOCOL.md` **before** any result is seen.

## 6. How a run is reproduced

A run is reproducible only from its artefacts, and the artefacts are fixed by `contracts.RunManifest`:

1. `run_id` + `created_at` + `status` (`RESEARCH_GRADE` / `SYNTHETIC_FIXTURE_ONLY` / `NOT_RUN` / `FAILED`).
2. `adapter` (id, model id, **pinned revision**, quantisation, decoding, prompt version).
3. `dataset` (name, version, `source_sha256`, label tiers) and `config` + `config_sha256` + `seeds`.
4. `git.commit` / `git.branch` / `git.dirty` — a dirty tree is recorded, never hidden.
5. `environment` (Python, library versions, hardware) and `resources` (measured latency / peak VRAM / tokens; `None`
   means not measured).
6. The append-only `training/runlog.py` JSONL and, for training, `training/checkpoint.py` state
   (`plan_resume(root, run_id)` → `latest_step`, adapter path, rng state) so a resumed run continues rather than
   restarts.

To reproduce: read the manifest, recreate the environment, restore the dataset by sha, run the same arms with the same
seeds, and compare the primary metric within the pre-registered tolerance. A run without a pinned revision is **not**
reproducible, which is why `training/guard.py` blocks `MODEL_NOT_PINNED`.

## 7. The three boundaries (why this package cannot surprise you)

| Boundary | Mechanism | Failure mode it prevents |
|---|---|---|
| **Gates** (`safety.py`) | four capability gates, default closed, truthy-only open | a test, import or stray CLI call loading a model / training / using the network |
| **Readiness** (`training/guard.py`) | 10 named blockers + warnings, pure and injectable, `require_ready` raises `TrainingRefused` | training on weak labels, tiny splits, leaked groups, unpinned weights, unsafe paths, no disk |
| **Phase guard** (`training/run_train.py`) | exit 4 with `PHASE_GUARD: training is not executed in this phase` after printing the full plan | this phase silently becoming the phase that trained a model |

A later phase replaces the exit-4 branch with the launcher; it does not remove any gate, blocker or refusal.

## 8. Deliberately out of scope

* Prediction, forecasting, calibration claims — the project's five retractions and the rolling-origin null stand.
* Any use of AI pre-annotation as ground truth; any automatic labelling by the agent.
* Model downloads, package installation, network access, remote API calls, GPU execution, training — all gated off.
* Writes to `data/`, `research/`, other worktrees, or any `.sqlite` file.
* Any study number, registration, or claim of a finding: this phase produces infrastructure and a protocol draft.
