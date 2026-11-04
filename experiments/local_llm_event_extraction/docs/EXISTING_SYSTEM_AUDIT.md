# Existing-system audit — what the local small-LM module may reuse, must leave alone, and must never re-describe as success

**Scope.** The MedRadar scientific stack as it exists at `research/local-llm-foundation` (HEAD `b2a14c0`,
merge of PR #11; base `main`), plus read-only views of the two result branches `research/s028-temporal-graph-early-signal`
and `research/s029-evidence-based-relations`, the concurrent review branch `research/ai-evidence-review`, and the
documentation draft branch `maintenance/repository-consolidation`.
**Date of audit:** 2026-11-04. **Method:** read-only. No repository test suite, no medradar CLI, no network, no
model, no GPU. Other branches were read with `git show`, `git ls-tree`, `git grep` and `git log --all` only.
**Deliverable:** this file. Nothing else was written.

The audit exists to answer four questions for the new module and for the PR description: what can be reused,
what is broken, what must not be touched, and what must never be presented as a success.

---

## 1. Executive summary

1. **The scientific position today is a measurement apparatus, not a predictive system.** The temporal foundation
   is audited (bitemporal store, deterministic point-in-time export, immutable forecast registry, leakage replay);
   OBSERVE has one detector validated *at a named resolution* and exactly one confirmed decision rule
   (`research/MISSION.md:225-228`); ANTICIPATE was tested four times and failed each time for a diagnosed reason
   (`research/MISSION.md:234-237`); there is **zero** prospective calibration evidence (`research/MISSION.md:244-245`);
   and five findings were retracted (`papers/PAPER_v1.md:195-218`).
2. **What the LLM work may claim:** that it builds an extraction/validation/benchmark harness over frozen inputs,
   that the harness is deterministic and leakage-audited, and that it preserves the label-tier distinction. That is
   engineering and methodological work. It has **no** empirical result yet.
3. **What the LLM work may not claim:** predictive skill, detection accuracy, extraction accuracy, any
   "human-confirmed" label set, or that a local 4B model reproduces or beats the existing `medradar/llm.py` judge.
   There is no labelled data to support any of those, and the only existing label set is explicitly declared not
   to be human truth.
4. **The single biggest data blocker is labelled evidence, not compute.** All 69 review packets carry empty human
   columns (`research/studies/early_signal_5firms/HUMAN_REVIEW_WORKSHEET.csv`: 69 rows, `human_label` 0/69).
   The AI tier that exists is `AI_EVIDENCE_REVIEW` on a separate branch, and its own summary says it "is not human
   adjudication, not expert truth, and not a gold-standard label set"
   (`AI_REVIEW_SUMMARY.md` §preamble). Until a human labels, any supervised metric is either synthetic or circular.
5. **The reusable assets are four and they all sit in unmodified modules:** the six-term timing vocabulary
   (`research/DATA_PROVENANCE.md:9-20`), the canonical-JSON + SHA-256 + idempotency + clock-regression patterns
   (`medradar/tkg/store.py`, `medradar/forecast_registry.py`), the read-only SQLite opener
   (`medradar/tkg/adapter.py:47-61`), and the deterministic applicant normalisation plus focus-company keys
   (`medradar/intelligence/universe.py:73,150-162,197-233`, `config/universe_v1.json`). None needs modification.
6. **The second blocker is information density.** ~0.2 events per cell-month, 91.8 % zero cell-months
   (`research/RESULTS/README.md` R151), 0 patent rows and 0 hiring rows in the research lane
   (`research/DATA_PROVENANCE.md:32-33`), 17,308 lane events without a `track_id`, and no independent source that can
   confirm a detected change (`research/EXPERIMENTS.md` E23). An LLM adds *reading* capacity; it does not add events.

---

## 2. Reusable capabilities

Everything below exists on the audited branch, is exercised by committed tests or artifacts, and can be wrapped
without editing it.

| Capability | File:line | How the new module reuses it | Caveat |
|---|---|---|---|
| **Six-term timing vocabulary** (`event_date`, `published_at`, `first_seen_at`, `available_at`, `fetched_at`, knowledge cut-off τ) | `research/DATA_PROVENANCE.md:9-20`; `docs/METHODS.md:14-27`; `research/PREDICTION_PROTOCOL.md:31-42` | The new schema already names three of them (`experiments/local_llm_event_extraction/schema.py:127`, `:233-238`); take the remaining three from this table verbatim. `available_at` is the only timestamp a backtest may use (`docs/METHODS.md:22`). | Only three terms are first-class fields in `schema.py`; `available_at`, `fetched_at` and τ must be carried in the run manifest. The research lane has no real `published_at`: 510(k)/PMA get `decision_date + 14 days` marked `estimated` (`research/DATA_PROVENANCE.md:26-27`). |
| **Canonical JSON + SHA-256** | `medradar/tkg/store.py:192-202`; `medradar/forecast_registry.py:230-236` | Hash datasets, configs and run manifests with the same rule (`sort_keys`, compact separators, `allow_nan=False`). | The pattern is already duplicated in two modules. Import one of them; do **not** write a third implementation. |
| **Content-addressed idempotency** | `medradar/tkg/store.py:412-429`; `medradar/forecast_registry.py:512,620-640` | Derive `run_id` / `prediction_id` from canonical content so a re-run is an idempotent duplicate, not a new result. | Registry semantics are specific: an exact retry returns the original record *without* consuming the write clock (`docs/FORECAST_REGISTRY.md:118-122`). A benchmark re-run must record `duplicate`, not a second result. |
| **Clock-regression guard** | `medradar/tkg/store.py:365-383`; `medradar/forecast_registry.py:433-445`; errors at `store.py:64` / `forecast_registry.py:96` | Order run records monotonically; refuse a write whose timestamp is earlier than the last. | Single-writer assumption (`docs/TKG.md:98`). An injected test clock is accepted only on `:memory:` (`forecast_registry.py:415-417`). |
| **Read-only SQLite open** | `medradar/tkg/adapter.py:47-49` (`SourceReadOnlyError`), `:51-61` (`mode=ro` + `PRAGMA query_only`) | Every adapter that reads `data/*.sqlite` must open the store this way. | `mode=ro` prevents *this* connection from writing; it does not freeze the file for other processes. The freeze is a repo invariant (`research/STATE.json` → `invariants`), not an OS lock. |
| **Applicant normalisation `applicant_normalise_v1`** | `medradar/intelligence/universe.py:19-58` (rules), `:73` (version string), `:197-217` (`normalise_applicant`), `:220-233` (`entity_key`) | Map any model-proposed company string to a canonical entity id with a deterministic, rule-ordered fold (NFKD → upper → substitutions → punctuation → clause cut → suffix strip). | The only documented merge is suffix-only (`universe.py:49-55`); two names differing in a substantive token stay two entities. Fuzzy/substring matching elsewhere is a measured error source: the `ES5-048` "first use" packet is an entity artefact because "Given Imaging" cannot be seen as Medtronic by substring alias (`AI_REVIEW_SUMMARY.md` F3). |
| **Focus companies and canonical keys** | `medradar/intelligence/universe.py:150-162`; `config/universe_v1.json` (`focus_companies`, `cohort.required_focus_entity_keys`) | Use the five deep-case keys, never re-derive them. | Three of five are in the curated roster; Dräger and Mindray are not (`config/universe_v1.json` → `roster_status`). `canonical_entity_key` is `null` for those two and covers 1 of 349 Philips events — see §3.12. |
| **Human-review workbook and refusal paths** | `research/studies/early_signal_5firms/HUMAN_REVIEW_WORKSHEET.md:1-20,96-97`; `LABELING_PROTOCOL.md:7-15`; `experiments/b098/ingest_human_review.py` (referenced, not run) | Reuse the worksheet shape for LLM extraction labels: five human columns that stay empty, an ingest step that refuses to write without reviewer name and reason. | The ingest script was **not run** here (`AI_REVIEW_SUMMARY.md` §preamble); its refusal behaviour is documented, not verified by this audit. |
| **Integrity regression tests** | `tests/test_research_integrity.py:18-42` (regulatory taxonomy), `:70-141` (public-time semantics) | These five tests encode the semantics any new adapter must not break: `event_date` is never silently promoted to public time (`:71-86`), estimated timestamps never enter a study (`:122-130`). | The suite was not executed in this audit (constraint: no repository test suite). |
| **Verifier gate** | `verifier/README.md:1-3`; `verifier/v1/verify.py:1-8,34-42`; `docs/round_end` equivalent `tools/round_end.py` (10 steps, `research/RESULTS/README.md` R146) | The gate that must pass before any claim ships: it re-runs tests, re-parses artifacts and recomputes numbers instead of trusting prose. | `verifier/v1/verify.py` runs the whole pytest suite in a subprocess (`:34-42`) — it cannot be run inside this work package. Not verified here. |
| **Citation discipline in the research agent** | `medradar/research_agent.py:11-31` (rules), `:269-283` (`_cite`), `:1493-1504` (`_citations_for_claims`) | Copy the rule: every claim declared `observed`/`derived` carries at least one locator that resolves; a missing claim is *listed*, never silently dropped. | The agent contains **no model calls** by design (`research_agent.py:21-22`); it is not an LLM interface and must not be relabelled as one. |

---

## 3. Defects and negative results that may never be rewritten as success

Each item is a statement that a reader of the new module's PR might be tempted to soften. The artifact reference is
the authority; this list only indexes it.

1. **Five findings were retracted, each by a named control** (`papers/PAPER_v1.md:195-218`):
   (i) an entry-prediction signal with measurable skill — killed by the persistence baseline and an interval covering
   zero; (ii) cross-firm co-movement of technology entry — 3 of 32 cells survived a lane-volume null, **0 of 32** a
   track-volume null; (iii) trial activity confirms clearance activity — the whole lag profile inside the null band,
   largest correlation 0.036 on 16 eligible cells; (iv) an industry entry wave in one IVD track — 3,804 of 4,814
   entries (79 %) were first-ever appearances of a legal entity, p collapsed to 1.0 under a prior-filer control;
   (v) a replicated entry wave after split-sample testing — the candidate had been nominated with the "holdout"
   included, and the clean design nominated 3, confirmed 0. Records: `research/DECISIONS.md` D-021, D-023, D-025,
   D-027; `research/RESULTS/README.md` R28/R31/R37/R41.
2. **"Supported (modest)" is not "skill", and the two documents that describe the entry result are not scoped
   against each other.** `research/RESULTS/README.md` R11 records the entity-cohort entry model as
   supported (ΔAP +0.0973, 3/3 windows, above MDE 0.0877), while `papers/PAPER_v1.md:201` lists "an entry-prediction
   signal with measurable skill" among the five retractions. The reconciliation (R11 is scoped to the entity panel,
   the retraction to the cycle-1 claim) is implied by `research/RESULTS/README.md:45-56` but is not stated as such in
   either document. No document may quote R11 without the absolute size (AP 0.129 at a 0.68 % base rate) and the
   admission that part of the gain is the persistence baseline getting weaker (`README.md:52-56`).
3. **Zero prospective calibration evidence.** 25 genuinely prospective forecasts mature 2026-Q4 … 2028-Q1
   (`research/MISSION.md:238`; `research/ROADMAP.md:66-68`); the 25 legacy nowcasts mature 2027-10
   (`research/ROADMAP.md:68`); 0 matured as of this audit. The only scored forecasts are the 7 that had already
   matured at registration; they are excluded from the prospective set and score Brier 0.337 / accuracy 0.429, which
   the record explicitly calls "a sanity check that failed to reassure, not as evidence"
   (`research/RESULTS/README.md` R130–R131; `research/STATE.json` → `forecasts`).
4. **No demonstrated predictive skill above baseline.** Rolling-origin benchmark: 376 cells, 12 origins, 717
   observations, **no** predictor's 95 % interval excludes 1 (`research/RESULTS/README.md` R67). Quote the corrected
   lift 1.22 (CI 0.95–1.53), never the pre-correction 0.49, which was an artefact of comparing the future block with
   the same recent block that raised the flag (`research/DECISIONS.md` D-036).
5. **`event_date != published_at`, and the canonical knowledge clock is backfill time.** The registry's clock is the
   time the row was written, not the historical publication time (`research/DATA_PROVENANCE.md:91-94`); the TKG
   import sets `recorded_at` to the actual import observation time (`medradar/tkg/adapter.py:6-14`), so a
   `known_at` gate before 2026-11-02 returns 0 nodes / 0 edges (`docs/PHASE3.md:77-79`). Any "as-of 2020" statement
   built on this store is a backfill, not a point-in-time record.
6. **The taxonomy is applied to history unversioned — a semantic-leakage channel an as-of SQL replay cannot
   detect** (`research/DATA_PROVENANCE.md:79-82`; `research/STATE.json` → `known_measurement_defects` #2). A
   versioned taxonomy module now exists (`research/RESULTS/README.md` R148, version + effective date + SHA-256 of
   both mapping files), but it versions *going forward*; the historical product-code→track mapping is still
   present-day.
7. **All 69 packets are `PENDING_HUMAN_REVIEW`; 0 human-confirmed labels exist.** Measured on the CSV: 69 rows, and
   each of the five human columns (`human_label`, `human_reason`, `independent_confirmation`, `reviewer`,
   `reviewed_at`) is non-empty in 0/69. `CASE_CANDIDATES.md:9-10` and `LABELING_PROTOCOL.md:14-15` state the rule;
   the PR must state the count.
8. **The AI pre-annotation is a separate, explicitly non-human tier.** On `research/ai-evidence-review` the committed
   record has 69 entries with `review.label_authority = ai_evidence_review_v1` (69/69) and
   `review.not_human_truth = true` (69/69); labels are Routine Iteration 48, False Signal 14, Uncertain 4,
   Insufficient Observation 3, **Confirmed Shift 0**; status AI_ADJUDICATED 62 / AI_UNRESOLVED 7. That summary's own
   rules: it "may not be used as ground truth or to score the study's own detectors"
   (`AI_REVIEW_SUMMARY.md` §preamble, §4). An earlier tier (`AGENT_PRE_ADJUDICATION`, rubric `agent_rubric_v1`) is
   also barred from scoring (`AI_REVIEW_SUMMARY.md` §1). The new module's `contracts.py:50-65` already encodes this
   distinction; the PR must not collapse it.
9. **Patents and hiring lanes are uncollected or access-blocked.** Adapter implemented, 0 rows, no API key
   (`research/DATA_PROVENANCE.md:32-33`); PatentsView 403 and Common Crawl 504 (`research/DECISIONS.md` D-029,
   `research/RESULTS/README.md` R47); the hiring lane covers **1 of the 5** mandated deep-case companies
   (`research/RESULTS/README.md` R53, `research/DECISIONS.md` D-031). No patent or hiring claim is licensed.
10. **Event density is the binding constraint, and it is measured.** ~0.2 events per cell-month
    (`research/MISSION.md:248-250`; `research/STATE.json` → `observe_layer.resolution_justification`); the lane is
    91.8 % zeros and a seasonal adjustment touches 9 of 39,151 cell-months (`research/RESULTS/README.md` R151); the
    five-firm study saw 0.85 events per cell-quarter and 9 positives across 6 cells
    (`research/studies/early_signal_5firms/PILOT_RESULTS.md:46-48`).
11. **Detector ranking is resolution-dependent, so every detector claim must carry its resolution — and detection at
    a matched false-alarm rate is not earlier warning.** Quarterly aggregation reverses the monthly ranking
    (`research/DECISIONS.md` D-018; `research/RESULTS/README.md` R19), the quarterly winner was itself confounded by
    bin-parameterised memory (`README.md` R25), and no detector is identifiable across resolutions (`README.md` R88:
    winners cycle naive→CUSUM→z→CUSUM→z, Kendall τ vs monthly −1.0). The deployment choice (quarterly, rolling
    z-score, threshold 3.5, FAR 0.0179, sensitivity 0.147) is a decision at one resolution, not a ranking
    (`research/STATE.json` → `observe_layer`). Separately, "detection at matched FAR" was pre-registered as not being
    "earlier warning" (`research/DECISIONS.md` D-009), and the matched-FAR lead-time hypothesis was **refuted**: the
    lead-time delta is negative in four of six windows down to −31 days (`research/HYPOTHESES.md:397`;
    `research/RESULTS/README.md` R13).
12. **Entity granularity is an unresolved measurement decision, and the focus-company canonical keys do not cover
    the firms they name.** Measured from `config/universe_v1.json`: Medtronic canonical `medtronic-4bdceace` covers
    3,140 of 6,281 events (50.0 %); GE HealthCare canonical `ge-healthcare-06263bf9` 55 of 297 (18.5 %); Philips
    canonical `philips-e75dd829` **1 of 349 (0.3 %)**; Dräger and Mindray have `canonical_entity_key = null` because
    they are absent from the curated roster (the cohort carries representative keys
    `draeger-medical-systems-18043856` = 12 events and `shenzhen-mindray-bio-medical-electronics-b4ea0e74` = 84). A
    module that "uses the canonical focus entity" therefore uses an entity covering between 0.3 % and 50 % of the
    firm's lane events, unless it says otherwise.
13. **Two artifacts of the same study disagree about source availability tiers.** `COVERAGE_MATRIX.md:79-86` assigns
    Tier A to all six sources ("records both `published_at` and `available_at`"); `PHASE0_REPORT.md:35-49` prints
    Tier B/C/D for the same sources and states "**No source reaches Tier A**"; `PILOT_RESULTS.md:17` uses Tier B
    (`event_date + 30 days`). This audit cannot resolve which is correct — the artifacts describe different stores
    with different timestamp contracts (`docs/METHODS.md:20-27` vs `research/DATA_PROVENANCE.md:19-27`) — so it
    records the conflict. The new module must not inherit the words "Tier A" without naming the artifact it follows.
14. **Published verification counts are not mutually consistent.** The leakage replay is reported as "0 mismatches
    over 656,048 values" (`research/MISSION.md:200-202`) and as "0 mismatches on 1,107,081 entry values / 140,721
    continuation values" (`research/EXPERIMENTS.md:15`). Test counts are 829 (`research/RESULTS/README.md` R57),
    910 (`research/ROADMAP.md:32`) and 1,074 (`docs/PROJECT_STATUS.md`). These may be legitimate snapshots of
    different rounds, but no document maps them, so neither figure may be quoted as current.

---

## 4. Modules that must not be modified

This is a *do-not-touch* list based on what is frozen by convention or by committed evidence, not on importance.

| Path | Why | Evidence it is used (test, importer, or artifact) |
|---|---|---|
| `medradar/llm.py` | The existing network LLM judge; documented API, prompt version, cache table and honest-degradation contract. Changing it changes a shipped product path and invalidates its calibration note. | Imported by the live/case pipeline; calibration artifacts under `data/calibration/**` (`docs/PROJECT_STATUS.md`); `PROMPT_VERSION` at `:38` is part of the cache key at `:256`. |
| `medradar/forecast_registry.py` | Immutable, content-addressed forecast ledger; the audit chain (id, hash, window, cohort separation) is the programme's strongest reproducibility claim. | `tests/test_forecast_registry.py` (`docs/TKG.md:107`); `medradar/intelligence/forecasting/registry_adapter.py` (`docs/PHASE3.md:31-38`); 25 nowcasts registered (`docs/PHASE3.md:40-44`). |
| `medradar/tkg/*` | Append-only store, bitemporal query and deterministic export; SQL triggers physically reject rewrites, and schema-version gating rejects old files. | `tests/test_tkg.py`; import report `experiments/reverse_rd_v2/tkg_import_report.json` (E8); 171,800 assertions / 57,381 nodes / 114,419 edges (`docs/PHASE3.md:60-79`). |
| `data/*.sqlite` (any) | Frozen experimental inputs pinned by SHA-256; the pin is the study definition. | `research/STATE.json` → `invariants`; `docs/DATA_ASSET_REGISTER.md` §1 (branch) pins `research.sqlite` sha256 `dd241bfe…`; `research/DATA_PROVENANCE.md:22-34` row counts. |
| `config/*.json` | Human-curated knowledge base; regenerating `universe_v1.json` from a different database produces a different universe. | `medradar/config.py` loads them for every collector; `config/universe_v1.json` is the E11/cycle-2 panel (`research/EXPERIMENTS.md` E11). |
| `research/studies/**` | Frozen study records; corrections are appended as new files, never rewrites. | `research/RESULTS/README.md:8-9` ("a superseded result gets a new entry and a pointer, not a rewrite"); `AI_REVIEW_SUMMARY.md` §8 frozen-material check. |
| `tests/test_research_integrity.py` | Encodes the temporal semantics (no `event_date`→public-time promotion) that every new adapter can silently break. | `tests/` collection; the behaviours it asserts are cited by `docs/METHODS.md:20-27` and `research/DATA_PROVENANCE.md:8-20`. |
| `medradar/research_agent.py` | Deterministic, no-model-call agent whose citation rule is the reference behaviour; adding an LLM call to it would change its guarantees and its tests. | `experiments/reverse_rd_v2/agent_demo.json` (E9: 55 claims, 224 cited ids, 0 missing); `docs/PHASE3_AGENT.md`. |
| `verifier/v1/` criteria + `verify.py` | Independent gate; its checks are recomputed, not trusted. | `verifier/runs/010-013` acceptance transcripts; R43/R146 round-end steps. |

---

## 5. Reuse map for the new module

| New component | Existing capability it wraps | What it must **not** duplicate |
|---|---|---|
| **Schema** (`schema.py`) | The six-term timing vocabulary (`research/DATA_PROVENANCE.md:9-20`) and the `timestamp_quality` ladder (`docs/METHODS.md:23`); company identity from `applicant_normalise_v1` (`medradar/intelligence/universe.py:197`). | Its own timestamp names, its own company-id scheme, or an implicit `available_at = event_date` fallback. |
| **Validator** (`validation/`) | `contracts.ValidationConfig` (pre-registered thresholds, `contracts.py:192-211`), the quarantine-not-drop rule (`contracts.py:153-166`), and the semantics in `tests/test_research_integrity.py:70-141`. | A second threshold set, or a "repair" path that rewrites a quote/date to make it validate — `ValidationResult.normalizations` exists to prove only formatting changed (`contracts.py:156-160`). Note: the frozen entry point `validation.validator.validate_extraction` named at `contracts.py:24` did **not** exist in the package at audit time. |
| **Adapters** (`adapters/`) | Read-only SQLite open (`medradar/tkg/adapter.py:47-61`), content-addressed idempotency keys (`adapter.py:131-140`), and the adapter contract already declared in `adapters/base.py:39-108`. | A second read-only opener, a second adapter registry, or any adapter that imports `torch`/`transformers` at module import (`adapters/base.py:15-17`). |
| **Benchmark runner** (`benchmark/`) | Canonical JSON + SHA-256 + idempotent run id (`medradar/tkg/store.py:192-202`, `medradar/forecast_registry.py:230-236,512`), clock guard (`store.py:365-383`), and the results-ledger discipline of `research/RESULTS/README.md:1-9`. | A second hashing/canonicalisation scheme; a second metrics definition (precision/recall/abstention already fixed in `contracts.MetricReport`, `contracts.py:351-396`). `benchmark.runner.run_benchmark` (`contracts.py:31-33`) likewise did not exist at audit time — a PR must not describe the harness as implemented. |
| **Training / tuning contract** | Label tiers and the hard refusal to score machine labels as research grade (`contracts.py:50-94`); the human-sign-off gate from the promotion policy (`medradar/intelligence/promotion.py:26-46,74-147`; `research/PREDICTION_PROTOCOL.md:124-152`). | A new label vocabulary; an "auto-promote" path; any QLoRA run whose data tier is `ai_preliminary`. |
| **Environment probe** | `safety.py` gates and `gate_report()` (`experiments/local_llm_event_extraction/safety.py:65-102`), plus the rule that unmeasured values stay `None` (`contracts.py:317-348`). | A second gate naming scheme, or a probe that reports 0 MB VRAM when VRAM was not measured. |

---

## 6. Leakage and validity risks specific to adding an LLM

1. **Circularity: the same model producing labels and being evaluated.** If a local model pre-annotates and is then
   scored against those annotations, the number is a self-consistency check. The programme has already retracted a
   finding whose confirmation came from the same signal family that raised it (`LABELING_PROTOCOL.md:56-68`;
   `research/DECISIONS.md` D-025). `contracts.is_research_grade` (`contracts.py:75-78`) is the guard; the run status
   (`contracts.py:67-72`) must be `SYNTHETIC_FIXTURE_ONLY` until human labels exist.
2. **Prompt fitting on test documents.** Prompt iteration on the same documents that will be scored is tuning on the
   test set. The programme's pre-registration rule (`research/PREDICTION_PROTOCOL.md:7,113-120`,
   `research/MISSION.md:171-173`) applies to prompts as much as to windows; prompt version and template hash are
   already fields in the run manifest (`contracts.py:403-419`; `adapters/base.py:54-61`).
3. **Taxonomy applied to history.** A model asked to classify a 2019 clearance into a 2026 track inherits the
   present-day mapping (`research/DATA_PROVENANCE.md:79-82`). Extraction must record the taxonomy version it used, and
   a taxonomy-version change must be visible as a new run, not folded into an old one (R148 pattern).
4. **`first_seen_at` misuse.** It is our collection date, not a publication date
   (`research/DATA_PROVENANCE.md:14`; `EVIDENCE_TIME_AUDIT.json:42`; `research/studies/early_signal_5firms/PROTOCOL.md:61`).
   A model must never be asked to produce or infer it (`schema.py:21`, and the validator flag
   `reject_model_invented_first_seen = True` at `contracts.py:205`). All 55,090 historical rows share one
   `first_seen_at` value; the S-029 clock audit found 0 strict point-in-time observations
   (`research/studies/relation_network_s029/TEMPORAL_PROVENANCE.md:619`).
5. **Quote-equivalence temptation as silent repair.** A model that returns a near-quote (normalised whitespace,
   punctuation, or a paraphrase) invites a validator that "matches approximately". That is data editing. The frozen
   contract requires verbatim quotes (`contracts.py:201`) and keeps formatting-only changes visible
   (`contracts.py:156-160`); an approximate match must be a **recorded quarantine**, never an accept.
6. **The 69-sample ceiling, on top of class imbalance.** 69 packets (60 candidate + 9 lead-time pairs) cannot support
   per-category accuracy, calibration or a meaningful test/validation split, especially with the label distribution
   skewed 48/14/4/3/0 (`AI_REVIEW_SUMMARY.md` §3.1). The existing evidence for what small positives do: 26 positives in
   1,716 holdout rows produced `AP = 1.0` for single-positive subgroups and the pre-declared firm-scale split was
   degenerate (`research/HYPOTHESES.md:167-176,396`). Any metric needs its interval and its MDE
   (`research/PREDICTION_PROTOCOL.md:76-81`); "not estimable" is a valid output.
7. **Train/test contamination through company grouping.** Cases share companies and product families, so splits must
   be by group, not by case (`contracts.py:254-275`); overlapping label windows are not independent replications
   (`research/PREDICTION_PROTOCOL.md:44-49`).
8. **Contradiction-evidence shortcut.** The profile engine rejects any profile without contradictory evidence
   (`research/RESULTS/README.md` R55), and the promotion gate cannot be skipped silently
   (`research/PREDICTION_PROTOCOL.md:140-144`). An extraction schema that treats "no counter-evidence found" as
   support repeats a defect the record already names.
9. **Over-reading the AI tier's 0 `Confirmed Shift`.** Zero can mean "no packet meets the bar" or "the rubric cannot
   see a shift"; the AI summary states it means the former for this set only, and warns it is not evidence that no
   technology shift exists (`AI_REVIEW_SUMMARY.md` §4). Either reading is a claim the new module may not make.

---

## 7. Measured-facts appendix

All figures below were computed during this audit; none is copied from prose unless the citation says so.

### 7.1 Module sizes (lines, `python` line count over the file)

| File | Lines |
|---|---:|
| `medradar/llm.py` | 320 |
| `medradar/forecast_registry.py` | 1,271 |
| `medradar/research_agent.py` | 1,900 |
| `medradar/tkg/store.py` / `adapter.py` / `query.py` / `export.py` / `__main__.py` / `_time.py` / `__init__.py` | 675 / 232 / 168 / 122 / 260 / 55 / 44 |
| `medradar/intelligence/universe.py` / `promotion.py` | 849 / 221 |
| `tests/test_research_integrity.py` | 145 |
| `verifier/v1/verify.py` | 347 |
| `research/DECISIONS.md` | 2,936 |
| `research/STATE.json` | 1,380 |
| `research/RESULTS/README.md` | 211 |
| `papers/PAPER_v1.md` / `PAPER_METHODS_v1.md` | 508 / 161 |
| `experiments/local_llm_event_extraction/schema.py` / `contracts.py` / `safety.py` / `adapters/base.py` | 618 / 469 / 102 / 273 |

### 7.2 Focus companies and canonical coverage (`config/universe_v1.json`)

Five focus companies (`focus_companies`, 5 keys). Universe totals: 9,412 entities
(`counts.entities_total`), 4,632 detailed records, 10,309 raw applicant strings, 55,090 events accounted (100 %).

| Focus key | canonical_entity_key | canonical events / firm events | roster_status |
|---|---|---|---|
| `medtronic` | `medtronic-4bdceace` | 3,140 / 6,281 (50.0 %) | in roster |
| `ge_healthcare` | `ge-healthcare-06263bf9` | 55 / 297 (18.5 %) | in roster |
| `philips` | `philips-e75dd829` | 1 / 349 (0.3 %) | in roster |
| `draeger` | `null` | 0 / 30 (cohort key `draeger-medical-systems-18043856` = 12) | absent from roster |
| `mindray` | `null` | 0 / 90 (cohort key `shenzhen-mindray-bio-medical-electronics-b4ea0e74` = 84) | absent from roster |

### 7.3 The 69-packet label state

| Quantity | Value | Source |
|---|---:|---|
| Packets | 69 (60 candidate + 9 lead-time pairs) | `AI_EVIDENCE_REVIEW.jsonl` → `origin` |
| Human-labelled rows | 0 / 69 | `HUMAN_REVIEW_WORKSHEET.csv`, five human columns each 0/69 |
| AI label authority | `ai_evidence_review_v1` 69/69, and `not_human_truth = true` 69/69 | same JSONL |
| AI status | AI_ADJUDICATED 62 / AI_UNRESOLVED 7 | same JSONL |
| Labels | Routine Iteration 48 · False Signal 14 · Uncertain 4 · Insufficient Observation 3 · **Confirmed Shift 0** | same JSONL |
| Reviewer agreement | 64 agree / 5 `disagree_resolved` | same JSONL, `review.agreement` |
| Flagged for external expert | 27 true / 42 false | same JSONL, `review.needs_external_expert` |

### 7.4 Retraction and negative-result counts

| Quantity | Value | Source |
|---|---:|---|
| Findings listed as retracted | 5 | `papers/PAPER_v1.md:195-218` |
| Result rows tagged retraction/correction in the index | 7 (R19, R25, R35, R37, R40, R48, R59) | `research/RESULTS/README.md` |
| Result rows / negative rows / decision records | 152 / 27 / 74 (D-001 … D-074) | `research/STATE.json` → `completion.record`; `research/DECISIONS.md` headings |
| Matured prospective forecasts | 0 of 25 | `research/STATE.json` → `forecasts` |
| Patents rows in the research lane | 0 | `research/DATA_PROVENANCE.md:32` |
| Hiring rows in the research lane | 0 | `research/DATA_PROVENANCE.md:33` |

### 7.5 External records checked read-only

| Item | Verdict / state | Quoted authority |
|---|---|---|
| S-028 (`research/s028-temporal-graph-early-signal`) | **Outcome B — no incremental information**, later downgraded by its own Correction 1 | `GRAPH_RESULTS.md:48`: "**H1 判定：NULL（well-powered），outcome B。**"; `NEGATIVE_RESULTS.md` N1 records that the "well-powered" label was **invalidated** in `S-028-CORRECTION-1` (power 16.3 % for the effect it reported) |
| S-029 (`research/s029-evidence-based-relations`) | **`NO-GO FOR PREDICTION`** (pre-registered rule) | `NETWORK_FEASIBILITY.md:89`: "**`NO-GO FOR PREDICTION`** — the relations are reconstructable and individually traceable, but they are not point-in-time evidence and they are not human-validated"; machine record `artifacts/prereg_decision.json:14` |
| 69-packet AI review (`research/ai-evidence-review`) | AI tier only, 0 human labels, 0 `Confirmed Shift` (§7.3) | `AI_REVIEW_SUMMARY.md` §2–§4 |
| `docs/PROJECT_STATUS.md`, `docs/DATA_ASSET_REGISTER.md` | **Do not exist on `main` or any research branch.** Only commit touching them is `3cc0f16` on `maintenance/repository-consolidation` | `git log --all --oneline -- docs/PROJECT_STATUS.md docs/DATA_ASSET_REGISTER.md` → one commit; `git branch -a --contains 3cc0f16` → `maintenance/repository-consolidation` (+ `origin`) |

What those two draft documents add: a status page with a four-bucket capability taxonomy (implemented / experimental /
under validation / *not demonstrated*) and a fixed research-index vocabulary; a warning that decision-log IDs
`S-001…S-033` collide with programme study IDs `S-028`/`S-029`; and a data-asset register that names five different
files called "the database", pins each by size and SHA-256, and records that the study numbers are **not reproducible
from a clone** because the 289 MB research store lives outside the repository.

### 7.6 Commands used

```powershell
git status --short; git branch --show-current; git log --oneline -3; git for-each-ref --format='%(refname:short)'
git ls-tree -r --name-only <branch> | Select-String '<s028|s029>'   # locate study paths on a branch
git grep -n -i "verdict" <branch> -- '<study>/*.md'                 # verdict lines on a branch
git log --all --oneline -- docs/PROJECT_STATUS.md docs/DATA_ASSET_REGISTER.md
git show <branch>:<path>                                            # every branch read (status, AI review, register)
Select-String -Path research\DECISIONS.md -Pattern '^#{1,4} '      # headings only (file is 185 KB); same for RESULTS/README.md
python  # one small script per item: line counts (§7.1); STATE.json defects/forecasts/completion fields;
        # universe_v1.json counts and focus_companies; CSV non-empty counts; JSONL label/status counts
```

---

## 8. What this audit does NOT establish

- **No model and no hardware were used.** No local model was loaded, no prompt was issued, no inference was measured,
  no GPU/VRAM/throughput figure was measured or inferred; the resource contract keeps those fields `None` until
  measured (`contracts.py:317-348`).
- **No label is confirmed.** Zero human labels exist anywhere in the audited material and the AI tier is explicitly not
  truth; no precision, recall, calibration or agreement number here is a quality estimate of any model.
- **No test suite or CLI was executed.** The repository suite, the medradar CLI and `verifier/v1/verify.py` were not
  run (work-package constraint), so all statements about tests are statements about *code that exists*, not about
  tests that pass.
- **Store contents were not opened.** `data/*.sqlite` files were not queried in this audit; all row and event counts
  come from committed documents (`research/DATA_PROVENANCE.md`, `research/STATE.json`, `docs/PHASE3.md`) and are
  quoted as such.
- **Two published inconsistencies remain unresolved** and are recorded rather than repaired: the source-tier conflict
  (§3.13) and the verification/test counts (§3.14).
- **The draft-branch documents were read at one commit.** `maintenance/repository-consolidation` is a draft; its
  contents may change, and nothing here should be cited as if it were on `main`.
