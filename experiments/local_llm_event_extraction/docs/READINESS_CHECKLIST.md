# READINESS CHECKLIST — what is actually true today, gate by gate

**Measured on:** 2026-11-04 (Asia/Shanghai) · **Status semantics:** `READY` = precondition met and verified;
`PARTIAL` = some evidence exists but a claim may not rest on it; `NOT_READY` = not met; `BLOCKED` = met by policy
(a refusal), not by accident; `CONDITIONAL` = depends on an unverified environment.

**How to read this:** every row names the artefact that decides it and the owner who can unblock it. A status is never
"probably fine". Where this document says something is measured, it names who measured it. Where nothing was measured, it
says so.

**Attribution.** Hardware values were measured by the **Team Lead** on 2026-11-04 (`nvidia-smi` and system queries) and
are used here as supplied; this checklist did not re-measure them. Free disk space was measured by the WP5 agent with
`shutil.disk_usage` on 2026-11-04. Label counts are read mechanically by `experiments/local_llm_event_extraction/labels.py`.

---

## 1. Gate table

| Gate | Question | How it is verified | Status (measured today) | What is needed to unblock | Owner |
|---|---|---|---|---|---|
| **DATA** | Do enough *human-confirmed* labels exist to train and to evaluate? | `labels.py` reads `research/studies/early_signal_5firms/HUMAN_REVIEW_WORKSHEET.csv` (69 rows), `CASE_CANDIDATES.json` (60), `CASE_PACKETS_SMALL_SAMPLE_V2.json` (9); `training/guard.py:CODE_DATA_NOT_READY`. Run on 2026-11-04: `n_packets=69`, `human_confirmed=0`, `unlabelled=69`, `machine_preannotated=69`, blockers `NO_HUMAN_CONFIRMED_LABELS`, `COMPANY_UNDER_REPRESENTED(draeger=0<6)` | **NOT_READY** — 0 of 69 packets are human-confirmed; all 69 are `PENDING_HUMAN_REVIEW`, `final_label` null. The AI pre-adjudication is *not* human truth. | A named human adjudicates the packets and new documents: ≥84 human-confirmed cases (48/12/24), ≥3 events per category (≥1 in test), negative controls present | Named human reviewer + study owner |
| **PIT** | Can the *availability* time of each document be reconstructed, distinct from event and publication time? | `schema.TIMESTAMP_FIELDS` + `TimestampQuality`; `validation/timefields.py`; `EVIDENCE_TIME_AUDIT.json`; `labels.assess_pit_readiness()` (run 2026-11-04: status `PARTIAL`, blocker `UNRESOLVED_AVAILABILITY_COUNT(5)`, warning `TIER_B_LAGS_ARE_ASSUMPTIONS`) | **PARTIAL** — the three timestamps are separate fields with qualities and are validated; historical availability is only partially reconstructed (no source reaches Tier A: `first_seen_at` is the collection date, not a publication date) | A recorded availability basis per source family and per document for the documents actually used; a statement of which claims are availability-dependent (this protocol makes none) | Owner + data work package |
| **EVAL** | Do the validator, the frozen matching protocol and an offline end-to-end run exist? | `validation/`, `benchmark/`, `prompting.py`, `parsing.py` exist; offline suites owned by WP3/WP4. WP5 ran only its own suite (`tests/test_llm_research_training.py`, 107 passed) and imported the frozen contracts; it did **not** run the WP3/WP4 suites | **READY** (per phase brief; harness + validator exist and run offline on fixtures) | Re-run the full offline suite at integration time and attach the log as evidence | WP3 / WP4 |
| **TRAINING** | Can a QLoRA run start? | `training/guard.py` (10 blockers), `safety.gate_open("training")`, `training/run_train.py`; CLI evidence: exit 2 (gate closed), exit 3 (not ready), exit 4 (`PHASE_GUARD: training is not executed in this phase`) | **BLOCKED** — phase guard by design; env gate closed by default; draft config `enabled=false`, `executed=false`; `revision=PENDING-A-PIN` | A later phase: sign the protocol, meet every gate, implement the launcher behind the same gates, and replace the exit-4 branch | Owner + later phase |
| **HARDWARE** | Can this laptop run 4-bit QLoRA for a 4B model at all? | Team-Lead measurements + `scripts/env_probe.py` + `docs/HARDWARE_COMPATIBILITY.md` | **CONDITIONAL** — measured: RTX 5080 Laptop GPU, 16 GB VRAM, driver 581.42, ~3.9 GB VRAM already used by desktop apps, 32 GB RAM. WSL2 not installed; CUDA path (sm_120 kernels) **unverified**. | Install WSL2 per `docs/INSTALL_WSL2_RTX5080.md`, verify PyTorch/CUDA/bitsandbytes versions and a sm_120 kernel, record the versions | Owner |
| **MODEL PIN** | Is the exact model artefact pinned? | `training/qlora_config.py:is_pinned`; `adapters/config/models.example.json` | **BLOCKED** — `revision = PENDING-A-PIN` in both the training config and the adapter descriptors; a floating ref is rejected as an error | Record a concrete commit sha (or immutable tag) for `Qwen/Qwen3-4B` once weights exist locally; re-run readiness | Owner |
| **SOFTWARE STACK** | Are torch/transformers/bitsandbytes/peft available and compatible? | `scripts/env_probe.py`; import checks (none installed in the current environment: no `torch`, `transformers`, `peft`, `bitsandbytes`, `datasets`) | **UNVERIFIED** — nothing installed; every training module is deliberately torch-free | Version-pinned install inside WSL2 (a later phase; package installation is out of scope now) | Owner |
| **DISK** | Is there room for weights, checkpoints and logs outside the repository? | `training/guard.py:CODE_DISK_INSUFFICIENT` (`shutil.disk_usage`, min 20 GiB) | **READY** — measured by WP5 on 2026-11-04: `C:\` = 393.8 GiB free, `D:\` = 598.2 GiB free | Keep the checkpoint root outside the repository; re-measure at run time (the guard does) | WP5 (done) |
| **DEFAULT POSTURE** | Are all four capability gates closed unless deliberately opened? | `safety.py:gate_report` / `all_gates_closed`; `tests/test_llm_research_training.py` asserts the closed-gate refusal | **READY** — `model_load`, `training`, `network`, `remote_api` all default closed; a typo fails closed | Nothing; keep it that way | WP2 / WP5 |
| **LEAKAGE CONTROL** | Can group-level leakage be refused before training? | `training/guard.py:CODE_SPLIT_LEAKAGE`; `datasets/splits.py`; `DatasetCase.group` | **READY in code** — refuses when a group crosses splits or a case has no group; exercised on synthetic manifests | Exercise with the real human-labelled documents and record the audit in the run manifest | WP4 / WP5 |
| **REPRODUCIBILITY** | Can a run be reproduced from its artefacts? | `RunManifest` (config sha, dataset sha, git commit, seeds, adapter revision); `training/runlog.py` (append-only JSONL); `training/checkpoint.py` (resume plan) | **PARTIAL** — the machinery exists and is tested offline; nothing has been run, and the model revision is unpinned, so no run is reproducible yet | Pin the revision, produce one frozen run manifest, verify a re-run reproduces its primary metric within the pre-registered tolerance | WP4 / later phase |
| **PROTOCOL** | Is the study pre-registered and signed? | `docs/PROTOCOL.md` status line | **DRAFT** — "DRAFT — requires named human sign-off; not a registered study; no S-030" | A named human signs it; the five prior retractions and the prediction null are acknowledged in the signature | Owner |
| **RISK** | Are the known ways this project could fool itself written down? | `docs/RISK_REGISTER.md` | **READY** — 18 risks with mitigations, triggers and owners | Keep it updated when a mitigation lands or a trigger fires | WP5 |

---

## 2. What must be true before the first GPU experiment

A numbered, checkable list. Every item needs *evidence*, not an assertion.

1. [ ] **WSL2 installed and verified** (`wsl --status`), following `docs/INSTALL_WSL2_RTX5080.md`, with the exact
   `wsl --version` output recorded. Today: not installed (measured by the Team Lead).
2. [ ] **CUDA path verified for sm_120**: a minimal PyTorch program on the GPU prints device name and capability
   `(12.0)`, with the PyTorch/CUDA/bitsandbytes versions recorded. Today: unverified.
3. [ ] **Measured peak VRAM** for Qwen3-4B at 4-bit NF4 with the draft config, recorded as a measurement, replacing the
   `ASSUMED` estimate in `training/configs/qlora_qwen3_4b.draft.json`. If the desktop's ~3.9 GB cannot be reclaimed, the
   VRAM budgets in the draft are lowered to the measured free VRAM minus headroom (an amendment, not a silent edit).
4. [ ] **Protocol signed** by a named human, with the draft status line replaced and an amendment that authorises the
   phase.
5. [ ] **DATA gate passed**: ≥84 human-confirmed cases (48/12/24), ≥3 events per category (≥1 in test), negative controls
   in all three splits. Today: 0 human-confirmed.
6. [ ] **Grouped splits frozen** and their `sha256` recorded; leakage audit passes with the real documents.
7. [ ] **Pinned model revision** (`revision != PENDING-A-PIN`), adapter ids `hf-qwen3-4b` / `hf-qwen3-4b-qlora`
   registered, and the weights present locally without an implicit download.
8. [ ] **Evaluation harness frozen**: matching protocol, scorer and validator versions recorded in the run manifest;
   validator acceptance rate on real documents inspected.
9. [ ] **PIT fields populated** for every document used: `event_date`, `published_at`, `first_seen_at` with qualities.
10. [ ] **Checkpoint root outside the repository** with ≥20 GiB free, measured at run time by the readiness guard.
11. [ ] **Readiness passes**: `run_train.py` prints the plan and exits 4. (Exit 4 *is* the pre-flight pass in this phase;
    a later phase replaces it with the launcher.)
12. [ ] **Both intent flags and the environment gate** are passed deliberately for that session
    (`MEDRADAR_LOCAL_LLM_ALLOW_TRAINING=1`, `--enable-training`, `--i-understand`), and the session is recorded in the
    run log.

---

## 3. Reproduce these statuses

```bash
# offline refusal + readiness suite (no model, no GPU, no network)
python -m pytest tests/test_llm_research_training.py -q

# what the readiness guard thinks of the committed draft today (gate closed -> exit 2)
python -m experiments.local_llm_event_extraction.training.run_train \
  --config experiments/local_llm_event_extraction/training/configs/qlora_qwen3_4b.draft.json \
  --dataset-manifest <a-manifest.json> --checkpoint-root <outside-the-repo-dir>

# label status, derived from the files rather than remembered
python -m experiments.local_llm_event_extraction.labels
```

The exit codes are part of the contract: `2` = gate closed, `3` = not ready (blockers listed), `4` =
`PHASE_GUARD: training is not executed in this phase`. Reaching 4 with the committed draft is impossible on purpose.
