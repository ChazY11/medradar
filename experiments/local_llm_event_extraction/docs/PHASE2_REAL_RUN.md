# Phase 2 — the first real local-model extraction run (Qwen3-4B on an RTX 5080 Laptop)

**Research question this phase serves**

> Can publicly observable evidence provide reliable early signals of meaningful changes in
> medical technology development?

This phase answers a strictly smaller question that has to be answered first:

> Can a locally hosted ~4B open model extract **time- and evidence-grounded** medical-device
> technical-development events from real public documents, and is that extraction
> *measurable* against the existing rule system?

It does **not** claim that any model predicts medical technology development. Nothing in this
document is a forecast.

---

## 0. Status vocabulary (strictly applied)

| Label | Meaning in this report |
| --- | --- |
| **VERIFIED** | actually executed on this machine and verified (environment, model load, inference, checkpoint round-trip) |
| **MEASURED** | a number read from an instrumented run, reproducible from the committed artifacts |
| **EXPLORATORY** | computed, but from silver labels or unlabelled documents — not a scientific accuracy claim |
| **ASSUMED** | an engineering estimate, never presented as a measurement |
| **BLOCKED** | the preconditions for the step do not exist |
| **NOT_RUN** | the step was not executed, with the reason given |

The distinction between the four model questions is kept everywhere:

1. did the model **load** — VERIFIED, §3;
2. did it emit **valid JSON** — measured per document, §6;
3. did the output pass **evidence validation** — measured per document, §6;
4. is the extracted content **factually correct** — not answered by 2 or 3; only the
   silver-label comparison in §7 gives a weak, explicitly exploratory signal.

---

## 1. What was run

| Arm | Backend | What it is |
| --- | --- | --- |
| **A** | `rules-baseline` | MedRadar's deterministic rule extractor, given the same corpus, the same entity roster and the same prompt-independent input |
| **B** | `hf-qwen3-4b-instruct` | `Qwen/Qwen3-4B-Instruct-2507` @ `cdbee75f17c01a7cc42f958dc650907174af0554`, 4-bit NF4, greedy decoding, local GPU |
| **C** | QLoRA-tuned arm | **NOT_RUN** — no human labels exist; see §8. A *technical* QLoRA smoke test was run instead, and it proves the pipeline, not the capability. |

Baseline model choice: the task named "official Qwen3-4B". `Qwen/Qwen3-4B` is the
*pretrained base* checkpoint — it was trained to continue text, not to follow instructions,
and it is not the right artifact for a structured JSON extraction task. The instruction-tuned
4B checkpoint of the same family, `Qwen/Qwen3-4B-Instruct-2507`, was used instead, and the
revision is pinned. This substitution is recorded here rather than hidden: **all results below
are for the instruct checkpoint, never for the base model**, and no number is presented as a
"base model" result.

---

## 2. Corpus — real, public, hashed, frozen

19 documents from openFDA and ClinicalTrials.gov, covering all five MedRadar study firms.

| Property | Value |
| --- | --- |
| Documents | 19 (SHA-256 verified at load time; a post-collection edit fails the run) |
| Companies | Medtronic 4, Philips 4, Siemens Healthineers 4, GE HealthCare 4, Dräger 3 |
| Source families | FDA 510(k) 5, FDA PMA 4, FDA recall 5, ClinicalTrials.gov registration 5 |
| Text styles | `prose` 10 (sponsor/firm-authored text from the source record), `field_value_rendering` 9 (510(k)/PMA records contain no narrative, so the body is an honest `field: value` rendering, not a written document) |
| Provenance | per document: API endpoint, retrieval timestamp, source publication date, the source field the event date came from, `content_sha256`, `raw_sha256` |
| Frozen copy | `datasets/real/corpus/2026-11-04/` in this repository |
| Splits | every document `split="test"` — evaluation only, **never** training data |

**Limitation stated up front.** These are real records, but they are not press releases or
papers. Ten are prose assembled from the record's own narrative fields; nine are structured
renderings because the source has no prose at all. A result on this corpus does not transfer
to arbitrary web documents, and the `field_value_rendering` half is closer to
reading-comprehension of a record than to document extraction. The two styles are reported
separately in §7.

---

## 3. Model load — VERIFIED

The adapter refuses to load anything unless the revision is an immutable pin
(`MEDRADAR_LOCAL_LLM_ALLOW_UNPINNED` is a recorded diagnostic override, not a default). On
load it records the resolved revision, a weights fingerprint of the snapshot directory, the
chat-template hash and the decision about thinking mode.

Qwen3 hybrid-thinking templates must be rendered with `enable_thinking=False`, otherwise
reasoning tokens share the decode budget and the trace can restate the output skeleton that
the system prompt prints — which the strict parser would decode as the answer. The 2507
Instruct checkpoint used here is a **non-thinking** model: its template has no
`enable_thinking` variable, and the adapter therefore passes no such flag. It records
`thinking_supported: false` instead of pretending it disabled something.

Measured numbers (load time, allocated VRAM, decode rate) are in §6, taken from the run
artifacts.

---

## 4. How the two arms are kept comparable

Both arms receive the **same** `ExtractionRequest` built by the same `prompting.build_prompt`,
the same entity roster (canonical ids and aliases), and the same validator. The rule arm
ignores the prompt and parses the document text; that is its documented behaviour, and its
output goes through the same strict parser and validator. No arm can influence the scorer.

The company hint supplied in the prompt is `"<display name> [canonical_id: <roster id>]"`,
because the task is *closed-roster* extraction, not open-set entity linking. This makes the
company-attribution question easier than in production, and it is recorded as a limitation.

---

## 5. What "measured" means for an unlabelled corpus

With no human labels, the only defensible metrics are harness-level:

* **JSON validity** — `parse_status == "ok"` after strict decoding (no repair, no unknown keys);
* **schema/validation outcome** — the evidence validator's document verdict and per-event
  issues (verbatim quote location, entity identity resolved from the roster, timestamp
  consistency, deduplication);
* **abstention rate** — a first-class outcome, not an error;
* **resources** — wall time, tokens in/out, tokens/s, per-call peak VRAM, process peak RSS;
* **event-level agreement** against *silver* labels derived from each source record —
  **EXPLORATORY only**, because the record and the document come from the same source.

No precision, recall or F1 is reported. The harness refuses to compute one: a run whose label
tiers are not human-confirmed cannot be marked `RESEARCH_GRADE`
(`contracts.require_consistent_run_status`), and this corpus's status is
`REAL_DOCUMENT_UNLABELLED`.

---

## 6. Results — arms A and B

**Run identity:** `phase2-2026-11-04`, status `REAL_DOCUMENT_UNLABELLED`, dataset SHA-256
`92a41a66…`, 19 cases, model revision `cdbee75f…`, prompt `extract-v1`.
Artifacts: `results/phase2-2026-11-04/experiment/`.

### 6.1 Harness-level measurements — VERIFIED

| Measurement | **A — rules** | **B — Qwen3-4B-Instruct (NF4)** |
| --- | --- | --- |
| Documents processed | 19 | 19 |
| Valid JSON after strict parse | **19/19 (100 %)** | **19/19 (100 %)** |
| Documents with a **verbatim quote located** in the source | 5/19 (26.3 %) | **19/19 (100 %)** |
| Events extracted | 5 | 20 |
| Abstentions | **14** | 0 |
| Validation: documents accepted / quarantined | 18 / 1 | 12 / 7 |
| Validation: events accepted / quarantined | 18 / 1 | 12 / 8 |
| Median latency per document | **0.010 s** | 25.90 s |
| Mean / max latency per document | 0.014 s / 0.066 s | 27.52 s / 52.33 s |
| Total wall time (incl. load) | 0.29 s | 546.1 s (23.2 s load) |
| Tokens in / out (mean per doc) | not measured (no tokenizer) | 1,619 / 275 (max 512) |
| Decode throughput (median) | n/a | **9.95 tokens/s** |
| Peak VRAM per call (mean / max) | none (CPU) | 3,699 / **5,020 MiB** |
| Process peak RSS | 34 MiB | **2,324 MiB** |
| Estimated cost | $0 (CPU) | $0 (own hardware) |

The model's per-call peak VRAM is a *per-generation* figure: the adapter resets the
allocator's peak counter before every decode and synchronises CUDA before stopping the
clock. The run-level manifest records the maximum of those per-call peaks (5,020 MiB).

### 6.2 Silver-label agreement — EXPLORATORY, not accuracy

The corpus carries one silver label per document, copied from the source record's own
`decision_date` (and the field it came from is recorded per label). Agreement:

| Field | **A — rules** | **B — Qwen3-4B** |
| --- | --- | --- |
| Company (canonical id) | 5/19 (26.3 %) | **19/19 (100 %)** |
| Event category | 2/19 (10.5 %) | **17/19 (89.5 %)** |
| Event date | 1/19 (5.3 %) | **17/19 (89.5 %)** |
| Product string | not computable (no gold product) | not computable |

`product_or_technology` agreement is reported as **not computable**, not as 0 %: the source
records do not carry a product string that could serve as a label. Treating the missing
label as a mismatch would have invented a failure.

### 6.3 Split by document style — the result is not uniform

| Style | n | A category | A date | B category | B date |
| --- | --- | --- | --- | --- | --- |
| `prose` (sponsor/firm narrative) | 10 | 2/10 | 1/10 | **10/10** | **10/10** |
| `field_value_rendering` (510(k)/PMA records) | 9 | 0/9 | 0/9 | 7/9 | 7/9 |

This is the single most important table in the report. The model is perfect on the ten
prose documents and 7/9 on the structured ones, while the rule system — designed for
prose keywords — collapses on the structured renderings and mostly abstains on prose. It
would be wrong to report the pooled 89.5 % without this split, and it would be wrong to
report 100 % as "the model's accuracy": it is agreement with a silver label on ten
documents that were assembled from the same source record.

Both of the model's two misses are FDA **PMA supplements** (`pma-p060005-s027`,
`pma-p980035-s848`) labelled `manufacturing_change` with a different date instead of
`regulatory_approval`. That is a genuine disagreement about category granularity: a PMA
supplement for a manufacturing change arguably *is* both. It is recorded as a miss, not
explained away.

### 6.4 What the comparison does and does not show

* **It does show** that a locally hosted 4B model can produce schema-valid, evidence-quoting
  extractions from these real public documents at 100 % parse validity, where the rule
  baseline abstains on 74 % of them.
* **It does not show** that the model is "89.5 % accurate". That number measures agreement
  with a label derived from the same record the document text came from.
* **It does not show** anything about arbitrary web documents, about prediction, or about
  the research question in §0.
* **The cost is not free**: ~2,000× the per-document latency and ~3.7 GB of VRAM, against
  34 MiB of RSS for the rules. Any downstream use has to justify that.

---

## 7. Error analysis and failure cases

8 of 20 extracted events were quarantined (7 of 19 documents). The issue codes overlap, so
they are listed with the document that produced them:

| Code | Count | What it means | Is the model wrong? |
| --- | --- | --- | --- |
| `DOMAIN_UNKNOWN` | 8 | model emitted `technology_domains` values outside the 23-domain / 50-track taxonomy | **Partly a prompt defect** — the prompt shows `"technology_domains": []` but never says the field is a closed vocabulary or what it contains. The model guessed reasonable-sounding strings (`cardiology`, `interventional cardiology`, `robotic-assisted surgery`). |
| `DATE_NOT_IN_EVIDENCE` | 5 | the asserted date does not appear in the quoted span **at that precision** | **No — the validator is being literal.** The model extracted the right date, but quoted the source's US-format prose (`10/06/2026`, `7/31/26`). The ISO date is present in the document header (`event_date_initiated: 2026-10-06`), just not in the chosen span. |
| `DATE_ORDER_VIOLATION` | 5 (all 5 trial registrations) | `event_date` is after `published_at` | **No — the rule is wrong for prospective registrations.** A ClinicalTrials.gov record is posted *before* the trial starts; "document published before the event" is normal there. 3 of these 5 were still accepted (warning severity), 2 quarantined. |

Concrete failure cases, quoted from `predictions.jsonl`:

1. `fdarecall-z-0292-2027` — event `safety_recall`, date `2026-10-06` (correct), quote
   `"Philips Medical notified consignees on about 10/06/2026 via certified mailed letter…"`.
   Quarantined: the date is in the quote but not in ISO form.
2. `ctgov-NCT04950192` — event `clinical_trial_start`, date `2021-10-25`, quote
   `"protocolSection.statusModule.startDateStruct.date: 2021-10-25"`. The *extraction is
   correct*; quarantine is caused by the date-order rule plus two unknown domains.
3. `ctgov-NCT05634538` — **hit the 512-token decode limit** (`finish_reason: length`). Its
   second event (`clinical_trial_result` from `overallStatus: TERMINATED`) is unsupported
   by its own quote and is contaminated by truncation. This is a real budget failure, not a
   validator quibble.
4. `fdapma-p060005-s027` / `pma-p980035-s848` — category granularity disagreement (see
   §6.3), the only two silver-label misses.

**Two validator defects found by the run** (both reproduced above, neither fixed in this
phase to avoid changing the measurement mid-run):

* the date-in-evidence check only recognises ISO-formatted dates, so a correct extraction
  that quotes the source's own prose format is quarantined;
* the "published before event" rule is invalid for prospective registrations, where it is
  expected and correct.

**One prompt defect found by the run:** the `technology_domains` field is a closed
vocabulary in the schema but is not shown to the model, so compliance is impossible. The
fix is a prompt amendment (render the 23 domains), which is a protocol change and must be
declared before the next evaluation.

---

## 8. QLoRA: technical test run, formal fine-tuning BLOCKED

**Formal research fine-tuning: `RESEARCH_TRAINING_BLOCKED`.**

The preconditions from the protocol are not met, and none of them can be met by writing code:

| Precondition | Status | Evidence |
| --- | --- | --- |
| Independent human event-extraction labels | **absent** | the study's 69 packets have 0 human-confirmed labels; `human_label` is empty on all 69 rows |
| Licence / terms for training use | partially available for the public records, but not for a labelled extraction task | n/a |
| Train/validation/test isolation over real documents | not possible without labels | every corpus document is evaluation-only |
| Pre-registered metric and baseline | the metric is defined, but it cannot be computed without labels | §5 |
| Reproducible training configuration | exists (config + seed + hashes) but has no valid data | |

Therefore arm C is **NOT_RUN**, and no "trained model is better" claim is made anywhere. What
*was* run is a **technical smoke test** on explicitly synthetic fixtures (see §9). Its only
purpose is to prove that a real forward pass, backward pass, LoRA update and checkpoint
round-trip execute on this GPU.

---

## 9. QLoRA technical smoke test — VERIFIED

Run in two processes (the first single-process version was killed at 15.8 GB of VRAM; see
§10). Artifacts: `results/phase2-2026-11-04/training/`.

| Item | Value |
| --- | --- |
| Base model | Qwen3-4B-Instruct-2507, 4-bit NF4, pinned revision, weights fingerprint recorded |
| LoRA | r=16, α=32, dropout 0.05, 7 projection modules, no bias |
| Trainable parameters | **33,030,144 = 1.4753 %** of the model |
| Data | 12 SFT records from the **synthetic fixtures** (`label_tier: synthetic_fixture`) |
| Sequence | 2048 tokens; prompt 1,029–1,118 tokens; supervised target 75–469 tokens |
| Optimisation | AdamW lr 2e-4, batch 1, grad-accum 2, clip 1.0, gradient checkpointing |
| Steps | 6 (3 in process 1, 3 in process 2) |
| Loss | 1.967, 1.897, 2.849 → **1.246, 0.867, 0.546** |
| Step time | 1.82–3.41 s (median ≈ 2.7 s), 1,124–1,531 tokens per step |
| Peak VRAM — train phase | **6,425 MiB** |
| Peak VRAM — resume phase | **7,036 MiB** |
| Peak VRAM — inference from reloaded adapter | 6,248 MiB |
| Checkpoint | `checkpoint-step-3/adapter_model.safetensors` sha256 `0dc51528…` + optimiser state (264 MB) |
| Resume | **across a process boundary**: fresh process reloaded base + adapter, restored AdamW state, continued from step 3 |
| Final adapter | sha256 `ceb450d8…` (different from the midpoint adapter, i.e. training continued) |
| Adapter inference | reloaded from disk and generated 114 characters |

The adapter's own completion is honest evidence of what six steps can do — nothing:

```json
{"event": "FDA 510(k) clearance", "product": "TestGuard monitor",
 "company": "ACME Medical", "date": "2025-03-03"}
```

It is JSON, and it is **not** the project's event schema. Six optimiser steps on twelve
synthetic records cannot teach a 16-way schema; this run proves the *machinery*, and the
completion is included precisely so nobody mistakes it for a capability result.

**Verdict:** training pipeline `VERIFIED` (real forward/backward/Adam, LoRA update,
checkpoint save, reload across a process boundary, resume, adapter inference). Model
capability change: `NOT_RUN` / not measurable.

---

## 10. Negative results and failures (kept, not tidied away)

1. **The rule baseline is the wrong instrument for structured records.** 0/9 on
   `field_value_rendering` documents, 14/19 abstentions overall. Its precision on the five
   documents it did extract is not scored (no human labels), but its coverage is poor.
2. **The model over-extracts and never abstains** on this corpus: 0 abstentions in 19
   documents. On documents with no target event it would have no mechanism to stay silent.
   The corpus is all-positive, so this is a warning, not a measured false-positive rate.
3. **`technology_domains` compliance is 12/20 events.** The prompt does not give the closed
   vocabulary (see §7); this is a prompt defect the harness exposed.
4. **Date-format and date-order validator defects** (§7) inflate the model's apparent
   quarantine rate: 10 of the 18 issue instances are validator strictness, not extraction
   error.
5. **A real training-memory bug was found by running the smoke test, not by reading it.**
   The first version kept three model copies alive in one process and drove the GPU to
   **15.8 GB** with 100 % utilisation and no progress; it was killed. Then the resume path
   was found to have silently lost gradient checkpointing (loading a k-bit base + adapter
   without `prepare_model_for_kbit_training`), measured at a **30,887 MiB peak and
   87–172 s per step**; after the fix it is **7,036 MiB and ~2.7 s per step**. Both are
   recorded in the smoke-test docstring so the next person does not rediscover them.
6. **A NaN-loss trap was found and closed.** With `max_seq_len=512` the ~1.1 k-token prompt
   truncated away every target token, leaving all labels `-100` and a NaN loss. The trainer
   now refuses such a configuration explicitly and refuses to record a non-finite loss.
7. **Not run, and not claimed:** formal QLoRA fine-tuning, arm C, multi-seed variance,
   per-class precision/recall, prediction/forecast evaluation, point-in-time backtest.

---

## 11. Reproduction

```powershell
$env:MEDRADAR_LOCAL_LLM_ALLOW_MODEL_LOAD = "1"
D:\DEPPSKK\mlenv\Scripts\python.exe `
  D:\DEPPSKK\worktrees\local-llm-research\experiments\local_llm_event_extraction\scripts\run_real_document_experiment.py `
  --weights-path D:\DEPPSKK\ml-models\Qwen3-4B-Instruct-2507 `
  --out D:\DEPPSKK\ml-work\runs --run-id phase2-2026-11-04
```

Environment and version record: [`PHASE2_ENVIRONMENT.md`](PHASE2_ENVIRONMENT.md).
Model provenance: `model_download.json` (per-file SHA-256 against the HF tree API).
Corpus provenance: `datasets/real/corpus/2026-11-04/MANIFEST.json`.

---

## 12. Limitations that would invalidate an over-reading of this report

1. **19 documents, one point in time.** This is a functional experiment, not a benchmark.
2. **Half the corpus is a structured rendering.** Prose results and rendering results must not
   be pooled silently.
3. **Silver labels are not independent of the documents.** Agreement numbers in §7 are a
   reading-fidelity check, not accuracy against human annotation.
4. **Closed-roster company hint.** Company attribution is easier here than in production.
5. **Single GPU, single seed, greedy decoding.** No variance estimate is claimed; a second
   seed would repeat the same greedy output and would be theatre.
6. **No point-in-time backtest.** The corpus is what the APIs returned on 2026-11-04. Using it
   as if it were what was observable in the past is exactly the error the programme forbids.

---

## 13. Known issues deliberately left open in this phase

These are real defects the pre-GPU audit found, confirmed still present, and **not fixed
here** because fixing them would change the measurement this report is built on, or because
they need a protocol decision first. They are recorded so the next phase starts from a known
state rather than a clean-looking one.

| Issue | Why it is still open |
| --- | --- |
| `benchmark/runner.py` has no split filter; a hand-built manifest with train cases is scored as one number | this corpus is entirely `split="test"`, so it does not affect these numbers; it does affect the synthetic-fixture harness and must be fixed before any real train/test evaluation |
| `assert_no_leakage` is still not called by the runner | same reason; no leakage was possible here because every case is one split |
| the validator cannot check that a quote *supports the category* | needs a lexical oracle decision; today a quote only has to be verbatim and contain the date |
| validation verdicts are recorded per prediction but do not feed the metric calculation | scoring is gold-vs-prediction; adding validation to scoring is a scoring-protocol change |
| dedup key ignores `product_or_technology` | two same-day clearances with different products would collapse; did not occur in this corpus |
| `vram_guard.decide()` has no caller; the training budget is still a config constant | the smoke trainer measures free VRAM directly instead; the formal trainer still uses the old path |
| schema `$ref` is not resolvable by stock `jsonschema`; `extracted` + null category accepted by Python | schema-contract work, not measurement-blocking |
| one prompt defect and two validator defects found by the run (§7) | each changes the measured quarantine rate; they must be fixed **together with a declared prompt/validator version bump** and re-run, not patched mid-report |
