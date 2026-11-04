# PROTOCOL — local small-LM event extraction (pre-registered research protocol draft)

**Status:** DRAFT — requires named human sign-off; not a registered study; no S-030. No study number has been assigned,
and none may be invented. Nothing in this document is a result, and nothing in this repository is currently authorised to
produce one under this protocol.

**Scope of this phase:** infrastructure and a protocol draft only. No model has been loaded, no training has run, no
evaluation has been executed, and no human-confirmed label exists yet. Where this document states a status, it is the
status measured today, not an aspiration.

**Owners:** the protocol is drafted by the implementation work packages and requires a *named human* reviewer signature
before any confirmatory analysis. The AI agent that wrote this file may not sign it, may not adjudicate labels, and may
not authorise a run.

---

## 1. The single primary research question

> **Can a locally hosted open-weight model in the 1B–8B range, tuned or untuned, extract time- and evidence-grounded
> medtech technical-development events from public documents more reliably than MedRadar's existing rule-based
> extraction?**

Everything below serves this one question. The question is deliberately about *extraction reliability*, not about
forecasting, investment value, or clinical meaning. If the answer turns out to be "no", that is a publishable negative
result under §12, not a failure of the study.

## 2. Why event extraction precedes prediction

MedRadar's existing science has already produced a clear verdict on prediction, and this protocol must not quietly
pretend otherwise:

* **Five findings were retracted**, each with the control that killed it (`research/RESULTS/cycle17_paper_2026-11-03.md`,
  `research/RESULTS/cycle7_retraction_2026-11-02.md`; summarised in `research/RESULTS/cycle33_round_end_2026-11-03.md`
  as "exactly one decision rule was confirmed against five retractions"). The **rolling-origin null stands** and is not
  rescued by later work (`research/RESULTS/cycle20_confirmation_2026-11-03.md`).
* There is **zero prospective calibration evidence**: the prospective forecast set was registered
  (`research/forecasts/FORECAST_SET_2026-11-03_prospective.json`) but has not matured, so no probability claim has been
  validated prospectively; no predictive skill above baseline has been demonstrated.

The current frontier is therefore **event extraction**: before any question about what an event predicts can be asked,
the event itself must be measurable — with a date, with a citation, and with an honest abstention when the document does
not say. This protocol addresses only that prerequisite. It explicitly does not re-open any retracted finding, and it
cannot reverse one.

## 3. Hypotheses (directional, pre-registered, falsifiable)

All hypotheses are stated before any label exists. Arms are defined in §4; the primary metric in §10.

**H-E1 — tuned model beats the rule baseline on extraction quality.**
*Direction:* Arm C (QLoRA-tuned Qwen3-4B) will have a higher event-level micro-F1 than Arm A (`rules-baseline`) on the
independent test set, with the 95 % paired-bootstrap CI of the difference excluding zero.
*Also confirmatory:* H-E1b — Arm C will beat Arm B (untuned Qwen3-4B) on the same metric and test set.
*Falsified if:* the CI of either difference includes zero, or is entirely below zero.

**H-E2 — the gain is not bought with invented evidence.**
*Direction:* Arm C's citation-correctness rate (verbatim-verified evidence, §10) will be non-inferior to Arm A's.
*Falsified if:* the paired CI lower bound for (C − A) on citation correctness is below −0.05 absolute.

**H-E3 — the model separates event time from publication time.**
*Direction:* on test events whose `published_at` differs from `event_date` by more than 30 days, Arm C's `event_date`
accuracy will exceed Arm A's by at least 0.10 absolute.
*Falsified if:* the difference is below 0.10, or the CI includes zero, or too few such events exist to evaluate
(the category is then reported `NOT_EVALUABLE`, not silently dropped).

**H-E4 — tuning does not teach the model to always assert an event.**
*Direction:* Arm C's wrong-abstention rate on documents with gold events ≤ 0.15 **and** its false-assertion rate on
negative-control documents ≤ 0.10 (pre-registered ceilings).
*Falsified if:* either ceiling is exceeded on the test set, with the paired CI excluding the ceiling.

H-E2, H-E3 and H-E4 are **guardrails**: they cannot create a success claim by themselves, but H-E2 can veto one (§11).

## 4. Arms, defined by adapter id (not by prose)

| Arm | Adapter id (must be registered under exactly this id) | Backend | Runs in this phase? |
|---|---|---|---|
| **A** — existing rule system | `rules-baseline` | `rule_based` | yes, offline, deterministic |
| **B** — untuned local model | `hf-qwen3-4b` | `hf_local` | no — model gate closed, weights absent |
| **C** — QLoRA-tuned local model | `hf-qwen3-4b-qlora` | `hf_local` | no — training gate closed, no human labels |

The ids are fixed here *before* any result is seen so that a run cannot silently swap in a different checkpoint. Arm C is
the same backend class as Arm B; only the adapter checkpoint/config differs
(`experiments/local_llm_event_extraction/training/configs/qlora_qwen3_4b.draft.json`). Every run manifest records the
adapter id, `model_id`, and a concrete `model_revision`. A floating revision (`main`, `latest`) is not a valid pin and is
refused by `training/qlora_config.py`.

A remote API arm (`remote-openai-compat`) exists in the registry for a future comparison. It is **not** part of this
protocol: no confirmatory comparison may be added without an amendment (§13).

## 5. Unit of analysis and data flow

**Unit of analysis:** one source document (`SourceDocument` / `DatasetCase`). Events are nested in documents and are what
the metric counts, but the *statistical* resampling unit is the document (§10), because events in one document are not
independent. **Frozen pipeline:** `schema.py` → `prompting.py` → adapter → `parsing.py` → `validation/` → `benchmark/` →
run manifest + report; the training path consumes the same `DatasetCase`/`GoldEvent` objects via
`training/dataset_builder.py`.

## 6. Dataset requirements

1. **Human-confirmed labels only.** Allowed label tiers are exactly `contracts.RESEARCH_GRADE_TIERS` =
   `human_confirmed`, `expert_adjudicated`. `ai_preliminary`, `synthetic_fixture` and `unlabelled` data may test the
   *harness* (and are then stamped `SYNTHETIC_FIXTURE_ONLY`) but may never be used as ground truth. The AI
   pre-adjudication of the 69 packets (`ADJUDICATION_AGENT_V1.md`) is **not** human truth and is not admissible here.
2. **Current status: `DATA_NOT_READY`.** 0 of 69 evidence packets are human-confirmed; all 69 are
   `PENDING_HUMAN_REVIEW` with `final_label` null. Real labels = 0. This status is derived mechanically by
   `experiments/local_llm_event_extraction/labels.py`, not remembered.
3. **Minimum counts (pre-registered).** 48 train / 12 validation / 24 test human-confirmed cases (84 total), enforced by
   `training/guard.py` (`min_train_cases`, `min_validation_cases`, `min_test_cases`).
4. **Minimum category coverage.** For each of the 16 pre-registered `schema.EVENT_CATEGORIES`: at least 3 human-confirmed
   events across the dataset and at least 1 in the test split. A category that fails is reported `NOT_EVALUABLE`; it is
   never merged into another category after seeing results.
5. **Independent test set.** The test split is frozen before any tuning, is never used for prompt selection, threshold
   selection, early stopping, or hyper-parameter search, and is scored once per pre-registered comparison. Reuse of the
   test split for anything else is a protocol violation (§10 risks R-10 in `docs/RISK_REGISTER.md`).
6. **Source mix.** Cases must record `source_type` from the closed list in `schema.SOURCE_TYPES`. A test set dominated by
   one source type cannot support a claim about "public documents" generally; the achieved mix is reported with every
   metric.
7. **Negative controls.** Documents with no event (`expected_abstain=True`, no gold events) are required in train,
   validation and test; without them a model that always asserts an event cannot be detected (H-E4).

## 7. Grouped split design and leakage rules

* Splits are assigned **by group, never by case**. The group key is the company (`company_canonical_id` via the roster)
  or, where a company would make a split unusable, a document family such as a repeated press-release series. The
  concrete key is recorded in `DatasetCase.group`.
* **A group appears in exactly one split.** `training/guard.py:SPLIT_LEAKAGE` refuses when a group crosses splits, and
  also refuses when a case carries no group (because then leakage cannot be excluded).
* A case with `split="unassigned"` is a blocker (`DATA_NOT_READY`), never silently assigned.
* The same document, or a near-duplicate above the validator's Jaccard threshold (`ValidationConfig.duplicate_jaccard_threshold`),
  may not appear in two splits.
* Company-level leakage is checked again at report time and recorded in the run manifest; a run whose leakage audit fails
  is `FAILED`, not "approximate".

## 8. Pre-registered gates (what "ready" means)

A gate is a precondition with a name, a verifier and an owner (`docs/READINESS_CHECKLIST.md`). Gates are never waived by
enthusiasm.

| Gate | Requires | Status today |
|---|---|---|
| `DATA_NOT_READY` | ≥84 human-confirmed cases, ≥3 events per category, negative controls, frozen test split | **NOT_READY** (0/69 human-confirmed) |
| `PIT_NOT_READY` | `event_date`, `published_at` and `first_seen_at` recorded separately with their qualities per event; source availability basis recorded | **PARTIAL** (fields and validator exist; historical availability only partially reconstructed; no Tier A source) |
| `EVAL_NOT_READY` | frozen matching protocol, scorer, validator and offline fixture run | **READY** (harness + validator accept offline fixtures; owned by WP3/WP4) |
| `TRAINING` | environment gate open + explicit intent flags + readiness pass + named-human phase authorisation | **BLOCKED** (gate closed; draft config disabled; revision unpinned; `run_train.py` exits 4 by design) |

No metric may be computed from a dataset whose `DATA` gate is not `READY`. A model may not be tuned while `PIT` is
`PARTIAL` **if** the protocol making the claim depends on availability time — which is why this protocol makes no lead-time
claim at all (§17).

## 9. Metric definitions (frozen before any run)

### 9.1 Primary metric — event-level micro-F1, gated on verbatim-verified evidence

Computed once per (arm, dataset) over the independent test split, using the frozen matching protocol:

1. **Candidate matching predicate** for predicted event *p* and gold event *g*:
   `p.company.canonical_id == g.company_canonical_id` (both non-null) **and**
   `p.event_category == g.event_category` **and** the date fields agree at the coarsest non-null granularity
   (if `g.event_date` is null, the date condition is waived and the comparison is counted as `date_not_required`).
2. **Evidence gate:** *p* counts as a true positive only if at least one of its `EvidenceSpan.quote` values is located
   **verbatim** in the source document by the validator's locator. An event whose evidence is absent or unverifiable
   counts as a false positive even if its fields match; it is additionally counted in `unverified_evidence_rate`.
3. **Matching:** maximum-cardinality one-to-one bipartite matching under the predicate, deterministic tie-break by
   sorting gold `event_id` then predicted `client_ref`. An abstained prediction never matches; a gold event with no match
   is a false negative.
4. **Micro-F1:** `TP, FP, FN` are pooled over all test documents, then
   `precision = TP/(TP+FP)`, `recall = TP/(TP+FN)`, `F1 = 2PR/(P+R)`; undefined denominators are reported as `null`
   with a reason, never as zero.
5. **What is excluded:** quarantined predictions are counted as FP (the error taxonomy of `validation/` explains why),
   parse failures count as FP for gold-positive documents and are reported in `parse_failure_rate`, and events in
   categories reported `NOT_EVALUABLE` are excluded from the primary metric with the exclusion recorded.

The scorer is frozen in `benchmark/` and its identity recorded in the run manifest
(`scoring_protocol_version`, `config_sha256`). Changing the predicate, the evidence gate, the matching rule or the
pooling unit after a run is a protocol amendment, not a bug fix.

### 9.2 Secondary metrics (reported with CIs, not used for the success claim)

| Metric | Definition |
|---|---|
| Entity accuracy | share of matched events whose `company.canonical_id` equals the gold canonical id |
| `event_date` accuracy | equality at the recorded granularity, over events where gold `event_date` is non-null |
| `published_at` accuracy | equality at the recorded granularity, over events where gold `published_at` is non-null |
| Citation correctness rate | share of predicted events whose quote is verbatim-verified in the document |
| Abstention rate | share of documents where the arm abstains |
| Wrong-abstention rate | share of documents with gold events where the arm abstains (H-E4 ceiling 0.15) |
| False-assertion rate | share of negative-control documents where the arm asserts an event (H-E4 ceiling 0.10) |
| Parse-failure rate | share of responses that do not parse into the contracted shape |
| Latency | per-document wall time, measured (`contracts.ResourceMeasurement`), never estimated |
| Peak VRAM | measured by the adapter at run time, in MiB; `None` when the backend cannot measure it |
| Cost | marginal USD: **0 for the local arms by construction** (no API call). Wall time and peak VRAM are the real cost; electricity is not measured and must not be reported as a dollar figure |

## 10. Statistical plan

* **Paired bootstrap over documents.** The test documents are the resampling unit (cluster bootstrap); both arms are
  evaluated on the same resampled documents each iteration. `B = 10 000` resamples, seed fixed and recorded
  (default `20261104`), percentile 95 % CI.
* **Confirmatory comparisons are exactly two:** C − A and C − B on the primary metric, each tested at α = 0.05. If the
  family grows beyond two (only by amendment, §13), **Holm–Bonferroni** applies to the whole family and the smallest
  p-value must clear its Holm threshold.
* **Minimum detectable effect.** Pre-registered formula: `MDE ≈ 2.802 · sd(d) / sqrt(n_docs)` (two-sided α = 0.05,
  power 0.80). The paired sd `sd(d)` is **not known today**; for planning, an *assumed* range of 0.35–0.60 F1 is used
  with n = 60 test documents, giving an assumed MDE of roughly 0.13–0.22 F1. This is an assumption, not a measurement,
  and it is labelled as such in every report. After the run, the realised MDE is computed from the observed `sd(d)` at
  the realised n and reported; no claim may be made of a difference smaller than the realised MDE.
* **No metric switching.** The primary metric and the two confirmatory comparisons are fixed. Any additional analysis is
  labelled *exploratory* in the report and cannot support a success claim.
* **Missing arms are `NOT_RUN`, never zero.** An arm that could not be executed is recorded with its reason and the
  comparison is reported as not evaluable.
* **Immutability.** Metric reports are written once per run with `config_sha256` and `dataset.source_sha256`; a corrected
  analysis is a new run with a new id, and the superseded report stays on disk.

## 11. Pre-registered success criteria

The study **succeeds** only if **all** hold:

1. **S1 (primary):** Arm C beats Arm A on the test-set primary metric, with the paired-bootstrap 95 % CI lower bound > 0.
2. **S2 (guardrail):** Arm C's citation correctness is non-inferior to Arm A's: paired CI lower bound ≥ −0.05 absolute.
3. **S3 (integrity):** every reported run is `RESEARCH_GRADE` under `contracts.require_consistent_run_status`; labels are
   human-confirmed; the leakage audit passes.
4. **S4 (traceability):** every artefact needed to reproduce the numbers exists: pinned model revision, config sha,
   dataset sha, seeds, prompt version, scorer version.

**If S1 holds but S2 fails, no success may be claimed** — the model would have gained F1 by inventing evidence, which is
worse than abstaining. If S1 fails, the result is reported as a negative result (§12), not buried. A result that is
"directionally right but the CI includes zero" is reported as **inconclusive**, and the phrase "the model works" is
forbidden.

## 12. Stopping, futility, and the negative-result obligation

* **Stop before running** if any of: `DATA_NOT_READY`, `PIT_NOT_READY` for a claim that needs availability time,
  no pinned model revision, unverified CUDA/software path, unsafe checkpoint root, or < 20 GiB free disk. The readiness
  guard refuses these automatically (`training/guard.py`).
* **Futility:** if the realised MDE exceeds 0.15 F1 (too few human-labeled documents or too much variance), the study is
  classified **INCONCLUSIVE** and no positive or negative claim about C vs A is made from it.
* **Hardware futility:** if a QLoRA step cannot be run on the measured 16 GiB laptop even at micro-batch 1 with
  gradient checkpointing, the result is reported as `NOT_RUN (hardware ceiling)` — a real, reportable engineering
  finding. It is never converted into "the model does not help".
* **Negative-result obligation:** every pre-registered comparison is reported whatever direction it points, with n, CI
  and the realised MDE. Null results are first-class artefacts. Suppressing or re-scoping a comparison after seeing it
  is misconduct under this protocol.
* **No reversal of prior records.** Nothing in this protocol may be used to un-retract a retracted finding or to
  reinterpret a frozen prior result (`research/RESULTS/`, `research/DECISIONS.md`).

## 13. Amendment procedure

1. An amendment is a **new file** under `experiments/local_llm_event_extraction/docs/` (e.g. `AMENDMENT_001.md`), never an in-place edit of this protocol.
2. It states: what changes (metric / arm / data / split / threshold / gate), why, the expected effect on conclusions, and the **date and name of the human signer**.
3. It must be recorded **before** the analysis it affects is unblinded; a change made after seeing the relevant result is recorded as *post-hoc* exploration and cannot support the success claim.
4. Amendments that relax a gate (e.g. accepting AI pre-labels) are **not permitted at all** — gates exist because the failure they prevent is unrecoverable.
5. The amendment log is append-only; superseded text is struck through in the log, never deleted.

## 14. Threats to validity

| Threat | Why it bites here | Pre-registered mitigation |
|---|---|---|
| Pre-training contamination | the base model may have seen the test press releases during pre-training; a high score may be recall, not extraction | report the contamination risk with every result; add a supplementary post-cutoff test slice where documents are demonstrably newer than the model's data; never claim generalisation from a contaminated split alone |
| Data scarcity | 0/69 human labels today; the private test set is small | gates + futility rule; report CIs, never point estimates alone |
| Circular validation | AI pre-annotation labelling the model that is then scored on it | only human-confirmed tiers; `is_research_grade` enforced in code |
| Leakage by company/family | firms recur across documents | grouped splits, `SPLIT_LEAKAGE` blocker, leakage audit recorded per run |
| Taxonomy drift | category bounds shift across history, and product-code remaps mimic events | fixed 16-category vocabulary; a taxonomy change is a schema version bump; remapped codes are flagged |
| Prompt overfitting | iterating the prompt until fixtures pass | one versioned prompt; fixture results are `SYNTHETIC_FIXTURE_ONLY`; test set untouched |
| Test-set reuse | the convenient independent set slowly becomes a dev set | frozen test split, one scoring per comparison, reuse recorded and reported |
| Reproducibility drift | unpinned revisions, non-deterministic kernels, unpinned seeds | revision pin enforced (`MODEL_NOT_PINNED`), seeds recorded, decoding recorded, `deterministic` declared per adapter |
| Shortcut learning | press-release boilerplate looks like a launch | negative controls + error taxonomy inspection, reported |
| Selection bias of documents | cases are a convenience sample of five firms | scope claims to the recorded source/firm mix; no "medtech in general" claim |

## 15. What this protocol does **not** licence

This section is binding, and it is deliberately the last word of the document.

1. **No predictive claim.** Nothing here licences a statement that an extracted event predicts a stock move, a regulatory decision, a product's success, or anything else. Prediction remains at the retracted/null frontier described in §2.
2. **No use of AI pre-labels as truth.** The AI pre-adjudication of the 69 packets, any agent-generated label, and any score computed against them are not evidence. They may be reported only as machine-annotation agreement.
3. **No reversal of recorded prior results.** The five retractions stand; frozen results stay frozen; no rewrite through this protocol.
4. **No capability from fixtures.** A passing fixture test proves the harness runs, nothing about model quality. Fixture runs are stamped `SYNTHETIC_FIXTURE_ONLY` and may never be quoted as a result.
5. **No generalisation beyond the measured mix.** No claim about models outside the 1B–8B family tested, other languages, other source types, or documents of a different genre.
6. **No clinical, regulatory or investment advice.** Extracted events are research data, not guidance.
7. **No study number.** This is a draft protocol; it has not been registered and no identifier may be invented for it.
8. **No training in this phase.** The presence of a QLoRA config, a readiness guard and a refusal CLI is the authorisation boundary, not an authorisation.

---

*Drafted by the implementation agent as part of the local small-LM research foundation. It is not signed, not registered, and not a finding. A named human must sign it, and the gates in `docs/READINESS_CHECKLIST.md` must be met, before any number is produced under it.*
