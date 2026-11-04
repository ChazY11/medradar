# Local 4B model on real job text — Phase 4 WP1/WP3 experiment

**Status**: executed 2026-11-04 (Asia/Shanghai) with the RTX 5080 Laptop GPU and the local
`Qwen3-4B-Instruct-2507` weights. No training, no downloads, no network during inference.
**Owner**: `llm-jobtext` (subagent) · **Lead**: Phase 4 programme lead.
**Branch/worktree**: `research/innovation-signals-observatory` · `D:\DEPPSKK\worktrees\phase4`.
**Schema**: `medradar.job_text_extraction.v1` · **Prompt**: `job-extract-v2`.

---

## 0. TL;DR (the numbers are machine-copied from `results/2026-11-04/llm/ARM_TABLE.md`)

* **Both arms are schema-perfect on the delivered sample** (20 items: 12 primary + 8 negative
  controls; JSON-valid 1.000, schema-pass 1.000). That is a *format* result, not a capability result.
* **Evidence is mostly locatable**: arm A 79/84 claim quotes found verbatim (0.940); arm B 59/66
  (0.894). Neither is 1.0, and the misses are informative (see §9).
* **The negative-control result is a split decision**: arm A false-positived 0/8; arm B
  false-positived **1/8 (0.125)** — it turned the business-unit phrase "Endovenous (EV) business"
  into a `peripheral_vascular` technology track for a Marketing Specialist.
* **Arm B is internally inconsistent on 4/20 items (0.200)**: it attached a technology track to a
  posting it itself classified `SALES_ADMIN_OTHER` (EP mapping → ep_pfa; Regional Sales Manager →
  neurovascular; OR Sales Rep → respiratory; Marketing Specialist → peripheral_vascular). Arm A:
  0/20, because its track gate refuses those assignments.
* **Arm B never abstains (0/20)**, including on every negative control. Its protection against
  inventing a direction comes entirely from its function-class choices, and that protection failed once.
* **Latency is the deployment problem**: arm B median 20.9 s, mean 36.4 s, p95 159.6 s, max
  **193.0 s**; 2 of 20 items exceeded the declared 90 s per-item budget (both non-English postings).
  Arm A median 0.005 s. Peak VRAM 13 199 MiB of 16 303 MiB.
* **No Precision/Recall/F1**, because there is no human gold standard. The A/B comparison is an
  agreement table, not accuracy.
* **Fine-tuning on job text is not justified yet** — see §11: the failure this run exposes
  (product-context track overreach + no abstention) is a *data/label* problem, and the programme
  still has no human labels. The next useful step is a small labelled adjudication set, not training.

## 1. The question, and what this experiment does not answer

The mission asks whether public technical hiring activity can provide credible, traceable early
evidence of a medtech company's emerging R&D directions (`research/MISSION.md` Layer 2). This work
package measures one link in that chain: **given a real public job posting, can a locally hosted 4B
model produce a structured record whose every claim is checkable against the posting text?**

This experiment does **not** answer, and must not be read as answering:

* whether the company is "moving towards" any technology — that needs at least two time-separated
  snapshots plus independent evidence (`PROTOCOL.md` §5, §7);
* whether the company's R&D investment increased — posting counts are not investment and capture
  coverage is unknown;
* any **Precision / Recall / F1** figure — there is no human gold standard for this corpus, so those
  numbers are `NOT_EVALUABLE` by construction, not "not computed yet";
* whether a model confidence is a probability — the contract has no confidence field.
* **what a stock of currently-live postings says about hiring flow**: `source_posted_at` spans
  2025-11-07 … 2026-11-04, i.e. these are postings that are *currently open*, not a sample of
  postings published in a recent window. The sample is a draw from currently-open postings.

## 2. Prior evidence this experiment inherits (PR #19 / #20)

(`docs/EXISTING_CAPABILITY_AUDIT.md` §3, treated as constraints here)

1. 4B QLoRA training runs locally (60 steps, 1200 s GPU wall-clock, real updates).
2. Structured-output format compliance improved with weak supervision
   (JSON-valid 0.750 → 0.950, schema-pass 0.650 → 0.850 on the event task).
3. Near-zero train loss is not capability: the 0.706 → 1.000 "agreement" was against **silver labels
   derived from source records**, not human truth.
4. **Negative-control false positives got worse after fine-tuning** — B 0.000 → C 0.667. This is the
   programme's headline risk; abstention and negative controls are therefore headline measures here.
5. Template/synthetic documents do not demonstrate ability on human-written text; this experiment is
   the first measurement on real postings.

## 3. Data and sample

**Snapshot**: `results/2026-11-04/jobs_medtronic.jsonl` — real public Medtronic job descriptions
collected from the Workday careers site by the Lead. Verified facts used here:

* 994 JSON lines, **994 distinct posting ids**, 0 duplicate rows;
* `source_posted_at` spans **2025-11-07 … 2026-11-04**, all `SOURCE_DATE` quality;
* description availability 1.00, median description 5 722 characters (range ~2.5k–18k);
* collection report `results/2026-11-04/collection_medtronic.json`: `listings_seen` 994,
  `details_ok` 994, `details_failed` 0, `truncated_at_ceiling` false, robots HTTP 200,
  1 045 requests at ≥0.8 s/host;
* file SHA-256 `2ca362ee758407d11ba23c52eba5c031802a1628bd35a402d9d01ca58470dd82`
  (recorded in both run manifests).

The raw file is never modified.

**Declared sampling rule** (fixed before any model output was seen; code in `llm/subset.py`,
recorded verbatim in `subset_{A,B}.json` and in every manifest):

* sort all postings by `sha256("phase4-jobsplit-v1\x00" + posting_id)` ascending;
* **primary sample** = first 12 postings whose title does **not** match the negative-title pattern;
* **negative controls** = first 8 postings whose title **does** match it;
* the two sets are disjoint by construction;
* the pattern is a fixed, title-level declaration of real non-technical occupations (Buyer/Planner,
  customer service, warehouse, administrative/executive assistant, finance/accounting, legal,
  payroll, non-technical co-op/intern, marketing); it is deliberately narrow and is not a model
  judgement;
* **final n = 20 (12 primary + 8 negative controls)**, not the originally planned 32+10. The reason
  is recorded and is itself a result: the 4B model's wall-clock tail made a larger sample
  incompatible with a usable delivery window (§13, §14). The negative-control set was **not** dropped.

**Negative-control postings actually used**:

| posting_id | title |
|---|---|
| 44592d8ebc0c100b91fbdb5b94630000 | Customer Service Rep II |
| 6e581deda778103b9fb75ccdd43f0001 | Sr. Principal Legal Counsel, GCC (excl. UAE) |
| f8066f25276f102846e1242a54450000 | Associate Customer Service Specialist with Spanish |
| dde5ac4d025f101d32ccce55cec30001 | Co-op/Apprentice (Non-Tech) |
| bf8f5ca312e110332dbb1a132d210002 | Intern: Graduate (Non-Tech) |
| ae2b9a49c998101301c7e1a3e6c10001 | Senior Marketing Specialist, EndoVenous (EV) |
| 2e1ef6324d1810343465ff43a2230000 | Principal Financial Analyst – Service & Repair Finance |
| 41c07ef5017b100bb5a77fb095370001 | Group Purchasing Organization (GPOs) Commercial Enablement |

**Declared input budget (applied identically to both arms): 3 000 characters** of the description.
The budget was reduced twice for a *measured* deployment reason, and both reductions are disclosed:

* 8 000 chars (~5.2k-token prompt): PyTorch's SDPA path allocated quadratic attention buffers, the
  Windows/WDDM driver began paging, and one item did not finish in 15 minutes;
* 5 000 chars: median ~25 s but the tail exploded (26 s, 60 s, 133 s, 204 s, 185 s across nine
  items, unrelated to output length); a 42-item run could not finish;
* **3 000 chars** (final): the whole 20-item run finished; latency is nonetheless still the reported
  problem. Truncation is marked in-band (`[TRUNCATED: …]`) and every one of the 20 items was
  truncated (median omitted ≈ 2 800 chars) — this is a real limitation, not a cosmetic detail.

## 4. Arms

| Arm | What it is | Status |
|---|---|---|
| **A** rules | `medradar.recruitment.taxonomy.classify_rules` (teammate `job-identity`): deterministic title/description cue matching, existing track keyword table, track gate that refuses a track for commercial/administrative postings; emits matched spans and rule-derived (non-probability) confidence basis. | RUN |
| **B** base model | `Qwen/Qwen3-4B-Instruct-2507`, local weights `D:\DEPPSKK\ml-models\Qwen3-4B-Instruct-2507`, bf16, batch 1, greedy, seed 0, `max_new_tokens` **320**, description budget **3 000 chars**. Untuned model. | RUN |
| **C** existing QLoRA adapter | The only adapter in the programme was trained on regulatory-event text under the frozen event schema. | **NOT_RUN** |

**C = NOT_RUN.** Reason (verbatim in `metrics.json`): the existing QLoRA adapter is event-specific —
it was trained on regulatory-event text with the frozen event schema (event category, three
timestamps, company entity, product). Job text is a different task with a different output contract,
and the adapter has never seen a job posting. Running it would measure schema/task incompatibility,
not job-text capability. **The absence of C is a statement about the experiment design, not a
capability claim about the model, and it is not evidence that fine-tuning would not help.**

## 5. Task schema (`medradar.job_text_extraction.v1`)

One record per posting; every field that is a claim carries a verbatim quote:

| field | meaning |
|---|---|
| `abstain` (bool) / `abstain_reason` | the extractor declines to assert anything; closed reasons incl. `no_technical_content` |
| `function_class` | closed mission vocabulary: `CORE_R&D`, `CLINICAL_R&D`, `PRODUCT_ENGINEERING`, `ALGORITHM_SOFTWARE`, `HARDWARE_SYSTEMS`, `MANUFACTURING_PROCESS`, `QUALITY_REGULATORY`, `SALES_ADMIN_OTHER`, `UNCLASSIFIED` |
| `function_evidence_quote` | required iff `function_class != UNCLASSIFIED` |
| `technology_track` | `UNCLASSIFIED` or an id from the existing `config/tracks_device.json` (50 tracks; no invented technology) |
| `track_evidence_quote` | required iff a track is named |
| `capability_phrases` | 0–2 requested (schema allows 4) `{text, evidence_quote}` pairs; an empty list is valid |
| `r_and_d_evidence` (bool) / `r_and_d_evidence_quote` | true only with a verbatim quote of development work |
| `uncertainty_note` | qualitative, optional; deliberately **not** a probability |

Structural invariants enforced by the decoder (covered by offline tests):

* a label without a matching non-empty quote is a contract error, never a low-confidence result;
* `abstain=true` must assert nothing (all `UNCLASSIFIED`, no phrases, no affirmative R&D);
* unknown function classes / track ids / keys are contract errors (the model cannot invent a technology);
* an empty string for an optional quote is accepted as `null`; an empty quote for an asserted label is rejected;
* a generation that hits the output cap is recorded as **`truncated`**, not as `invalid_json`
  (the two have different fixes and the distinction is enforced in the parser).

The semantic rule "a commercial/administrative posting must not carry a technology track" is **not** a
schema constraint. A payload that violates it is structurally valid and is counted as an
internal contradiction / negative-control false positive. Making it a schema error would hide exactly
the failure the prior fine-tuning run made worse.

## 6. Measurements

Per arm, on the same 20 postings:

1. **JSON-valid rate** and **schema-pass rate**, plus exact failure classes
   (`invalid_json`, `refused`, `empty`, `truncated`, `TIMEOUT`).
2. **Verbatim evidence locatability** using the existing harness matcher (NFC + whitespace collapse
   only; no fuzzy matching), per field.
3. **Evidence support**: deterministic conservative check that the located quote contains the assigned
   track's keyword family or function class's cue phrase, plus a manual adjudication table. A `False`
   means "declared cue absent from the quote", **not** "label wrong". Arm A's support is circular.
4. **Correct abstention / negative-control false positives**: false positive = a technology track
   **or** an R&D function class emitted for a title-declared non-technical posting.
5. **Internal consistency** (requested by the Lead, no labels needed): fraction of structurally valid
   items where function class and track contradict (track on `SALES_ADMIN_OTHER`/`UNCLASSIFIED`, or
   `r_and_d_evidence=true` for such a class).
6. **Measured wall-clock latency** per item (median/mean/p95/max, plus per-item TIMEOUT at >90 s) and
   peak VRAM.
7. **Error taxonomy** with counts.

**No Precision/Recall/F1** — no human gold standard exists. The A/B table is agreement, not accuracy.
**No confidence calibration** — rule strength and `uncertainty_note` are not probabilities.

## 7. Results

### 7.1 Arm table (verbatim from `ARM_TABLE.md`)

| Arm | n | items | JSON valid | Schema pass | Claim-quote locatability | Function cue-support (field/any) | Track cue-support (field/any) | Abstain rate | Neg-control FP | Median latency | Peak VRAM |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A rules | 20 | 12/8 | 1.000 | 1.000 | 0.940 (79/84) | 1.000 / 1.000 | 1.000 / 1.000 | 0.100 | 0.000 (0/8) | 0.005 s | n/a |
| B model | 20 | 12/8 | 1.000 | 1.000 | 0.894 (59/66) | 0.588 / 0.650 | 0.500 / 0.500 | 0.000 | **0.125 (1/8)** | 20.856 s | 13 199 MiB |
| C QLoRA | — | — | — | — | — | — | — | — | — | — | — |

Arm C = NOT_RUN (reason in §4; this row is not a capability comparison).

Arm B locatability by field: function 17/20, track 8/8, capability phrases 33/37, R&D 1/1.
Peak VRAM per item stayed in 11.6–13.2 GB of the 16.3 GB card; no item OOM'd.

### 7.2 Negative controls (headline, not a footnote)

| Arm | n | FP (track or R&D class) | FP track only | FP R&D function only | Abstained | UNCLASSIFIED both | Correct rejection |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 8 | 0 | 0 | 0 | 0 | 0 | 8 |
| B | 8 | **1** | **1** | 0 | **0** | 0 | 7 |

Arm B's false positive: **Senior Marketing Specialist, EndoVenous (EV)** → `SALES_ADMIN_OTHER` +
`peripheral_vascular`, quoting *"Endovenous (EV) business"*. This is the same failure mode the
programme's prior fine-tuning run made worse; the untuned model shows it once in eight controls.
Neither arm abstains on negative controls: both answer `SALES_ADMIN_OTHER` instead. That is a correct
rejection by the metric but it means the model **never used the abstain mechanism at all**, so its
negative-control protection is incidental rather than instructed behaviour.

### 7.3 Internal consistency (no gold standard needed)

| Arm | schema-ok items | contradictions | contradiction rate | track-on-commercial | R&D-flag-on-commercial |
|---|---:|---:|---:|---:|---:|
| A | 20 | 0 | 0.000 | 0 | 0 |
| B | 20 | **4** | **0.200** | 4 | 0 |

Arm B contradictions: Regional Sales Manager → `neurovascular`; EP Mapping Specialist → `ep_pfa`;
OR Sales Representative → `respiratory`; Marketing Specialist → `peripheral_vascular`. In every case
the model correctly called the posting commercial and then attached the product line being
sold/supported as if it were a technology track.

### 7.4 Error taxonomy

| Arm | Error counts |
|---|---|
| A | `quote_not_located` = 5 (all the plural-cue span `budget`, see §9.5) |
| B | `TIMEOUT` = 2, `function_label_without_located_quote` = 3, `function_quote_lacks_class_cue` = 7, `internal_contradiction` = 4, `negative_control_false_positive` = 1, `quote_not_located` = 7, `track_on_non_technical_function` = 4, `track_quote_lacks_track_keyword` = 4 |

### 7.5 Latency distribution (the deployment finding)

| Arm | n | median | mean | p95 | max | >90 s (TIMEOUT) |
|---|---:|---:|---:|---:|---:|---:|
| A | 20 | 0.005 s | 0.005 s | 0.008 s | 0.013 s | 0 |
| B | 20 | **20.856 s** | 36.368 s | **159.645 s** | **193.011 s** | **2** (193.0 s; 159.6 s) |

Both timeout items are non-English postings (Brazilian-Portuguese HR-intern; Japanese customer
service), but with n=2 no causal claim is made. The 193 s item produced only 190 output tokens and
finished normally — the cost was not long rambling, it was unpredictable slow decoding on a shared
laptop GPU. **A 30-second information-extraction task is not a predictable-latency component at this
model/stack size; any ingestion pipeline needs a hard per-item budget and a recorded TIMEOUT.**

### 7.6 Arm A vs arm B agreement on the shared 12 primary postings

| Relation | Count |
|---|---:|
| both arms UNCLASSIFIED (no direction claimed) | 0 |
| A UNCLASSIFIED / B labelled | 2 |
| A labelled / B UNCLASSIFIED | 0 |
| both labelled | 10 |
| same function class | 8 |
| same non-UNCLASSIFIED track | 1 (neurostimulation, Principal Quality Engineer) |

Reading: the arms agree on the function class of 8/12 primary postings, but on **tracks they agree on
1/12**. Arm B's much wider track coverage (8/20 vs A 2/20) is bought by reading product-portfolio
context as a technology track — the manual review calls 4 of B's 8 track claims overreach, plus the
negative-control case. Arm A's narrow coverage (6.1% of the 994 postings carry a track) is a
measured transfer problem, not evidence that the company has no such roles: e.g. the Lead's
`track_coverage_diagnostic.json` shows `surgical_robotics` mentioned in 80 postings but assigned 0
tracks, `medical_ai` 141 mentioned / 25 assigned, `ep_pfa` 117 / 8.

## 8. Manual adjudication (author review; NOT human gold truth)

Full table: `results/2026-11-04/llm/MANUAL_ADJUDICATION.md` (single author, after seeing outputs,
not blind). Summary of what it adds beyond the automatic metrics:

* B's negative-control track false positive is real and visible (Marketing Specialist → peripheral_vascular).
* **B invented no R&D function class for any negative control (0/8)**, but it misclassified 2/8
  non-R&D roles as `QUALITY_REGULATORY` (Legal Counsel, Financial Analyst). The headline false-positive
  metric rightly does not count this, so the report states it separately.
* **4 of B's 8 track claims are product-context overreach** on the primary sample; this is counted by
  `internal_consistency` without needing labels.
* B's function cue-support (0.588) is too harsh on non-English/paraphrased quotes: adjudicated function
  verdicts are mostly `AGREE`. Cue-support is reported as a lower bound, never as accuracy.
* A's 5 unlocated quotes have a single cause (plural-cue span construction, §9.5), not hallucination.

## 9. Five concrete failure examples (with quotes)

### 9.1 Negative-control false positive: business-unit name becomes a technology track

Posting **`ae2b9a49c998101301c7e1a3e6c10001` — "Senior Marketing Specialist, EndoVenous (EV)"**
(negative control). Arm B output:

> `function_class: SALES_ADMIN_OTHER`, `technology_track: peripheral_vascular`,
> `track_evidence_quote: "Endovenous (EV) business"`, `function_evidence_quote: "The Senior Marketing
> Specialist is expected to coordinate and support all aspects of marketing and sales efforts by
> actively colla…"` (the latter is **not** verbatim in the posting).

A marketing role is not evidence of a peripheral-vascular technology direction; the model converted a
business-unit name into a track. This is the exact pattern the programme's prior fine-tuning run
amplified. Arm A on the same posting: `SALES_ADMIN_OTHER`, track `UNCLASSIFIED`.

### 9.2 Internal contradiction: says "sales" and "technology track" in the same payload

Posting **`571f03758bae1018a52945f77ac50001` — "EP Mapping Specialist, CAS - Long Island"**. Arm B output:

> `function_class: SALES_ADMIN_OTHER` … `technology_track: ep_pfa`,
> `track_evidence_quote: "Cardiac Ablation Solutions offers cardiac mapping and ablation solutions to
> treat patients with abnormal heart rhythms."`

The quote describes the product portfolio the commercial role supports. The payload contradicts itself
(4 such items in 20; A: 0).

### 9.3 Paraphrased "evidence" fails the verbatim check

Posting **`332333b1059c102f0e353d24e11f0000` — "Product Manager/Associate Product Manager"**. Arm B output:

> `function_evidence_quote: "Market Development & Procedure Adoption: Develop the bone metastasis
> ablation market by defining the market development strategy, …"`

The posting does not contain that sentence; the model condensed a heading plus a sentence. It is a
locatability failure, not a support failure — and it is exactly why the quote matcher is strict.

(This pattern appears in 3/20 function quotes and 4/37 capability quotes for B.)

### 9.4 Product-context overreach: a software engineer gets a cardiac-rhythm track

Posting **`e7c298c178cb10018da5c0f808170000` — "Senior Principal Software Engineer"**. Arm B output:

> `function_class: ALGORITHM_SOFTWARE`, `technology_track: cardiac_rhythm`,
> `track_evidence_quote: "working with software teams in Cardiaovascular, Medical Surgical and
> Neuroscience portfolios at MEIC"`

The quote names the business portfolios the software teams sit in, not a cardiac-rhythm technology. The
deterministic track-keyword support check returns `False`, and the manual review classifies it
`OVERREACH`.

### 9.5 The A arm's own evidence defect (reported, not patched)

Five of arm A's function evidence spans are the bare word `budget`, e.g. posting
**`6e581deda778103b9fb75ccdd43f0001` — "Sr. Principal Legal Counsel, GCC"**. The cue list contains
`budget`; the posting says `budgets`; the plural-tolerant match emits a span whose text is `budget`,
which is **not** a verbatim substring. Hence A's locatability is 0.940, not 1.000. This is a
span-construction defect in the deterministic arm (owner: `job-identity`), not a hallucination, and it
is exactly the kind of thing the locatability metric exists to catch.

## 10. What a 4B model can and cannot be trusted to do on job text

**Can (on this evidence)**: produce contract-valid JSON reliably at this prompt size (20/20 both with
the compact v2 prompt); quote posting text verbatim most of the time (89% of B's claim quotes located,
100% of its track quotes); copy non-English text verbatim when it quotes it; classify commercial vs
engineering function broadly in line with the rules arm (8/12 same function on the primary sample).

**Cannot (on this evidence)**: be trusted to decide **whether a technology mention is the role's work
or the product being sold** — that distinction is exactly where B failed (4/20 internal contradictions,
1/8 negative-control false positive); abstain when it should (0 abstentions in 20 items, including all
negative controls); keep its own payload coherent; or behave with predictable latency (p95 160 s,
max 193 s on a 30-second task). Its track coverage looks much better than the rules arm (40% vs 10% on
this sample) but the manual review says half of those track claims are product-context overreach, so
**coverage is not accuracy**. With no human labels, this experiment cannot say which arm is "right" on
the 10 primary postings where both labelled; it can only say they disagree on 2/12 function classes
and 11/12 track decisions.

## 11. Is job-text fine-tuning justified yet?

**No.** This experiment did not produce the thing fine-tuning would need: human labels. What it
produced is a precise statement of the failure modes:

1. **Track overreach from product-portfolio context** (the dominant error, 4/20 contradictions + 1
   negative-control FP). A model fine-tuned on strong labels of this distinction could plausibly learn
   it, but the fix is *supervision about role-vs-product*, not format training.
2. **Abstention is absent from the untuned model's behaviour** (0/20). This is the same mechanism the
   prior run made worse after fine-tuning; without abstention examples in the training data, tuning
   would likely repeat that mistake.
3. **Latency** is a deployment constraint, unchanged by fine-tuning at this stack size.

What a justified fine-tuning attempt would need (none of which exists yet):

* a **human-labelled job-text set** (even 200–400 postings) with, at minimum, function class, whether
  each technology mention is the role's work vs the product sold, and **abstention** examples
  (including real non-technical postings);
* a held-out **negative-control set** drawn and frozen before training, scored after;
* a fixed evaluation harness (this one is reusable: schema + locatability + negative controls +
  internal consistency are all label-free measures that can gate a training run);
* a decision rule written before training (e.g. "tuning is justified only if it improves
  negative-control FP and internal consistency without regressing locatability").

Until then, the honest recommendation is: **use arm A for anything that needs auditability and
volume, use arm B only as an evidence-candidate generator with quote verification, never as an
autonomous labeller, and spend the next cycle on labels rather than on training.**

## 12. Reproduction

From the repo root (`D:\DEPPSKK\worktrees\phase4`):

```powershell
# Offline tests (no torch, no network): 27 tests for this work package
python -m pytest tests/test_innovation_signals_llm.py -q

# Arm A (deterministic rules; seconds)
python -m experiments.innovation_signals_observatory.llm.run_job_text_experiment `
  --arm A --data experiments/innovation_signals_observatory/results/2026-11-04/jobs_medtronic.jsonl `
  --out experiments/innovation_signals_observatory/results/2026-11-04/llm `
  --n-primary 12 --n-negative 8 --max-input-chars 3000

# Arm B (local model; loads the 4B weights onto the GPU)
$env:HF_HUB_OFFLINE='1'; $env:TRANSFORMERS_OFFLINE='1'
D:\DEPPSKK\mlenv\Scripts\python.exe -u -m experiments.innovation_signals_observatory.llm.run_job_text_experiment `
  --arm B --data experiments/innovation_signals_observatory/results/2026-11-04/jobs_medtronic.jsonl `
  --out experiments/innovation_signals_observatory/results/2026-11-04/llm `
  --n-primary 12 --n-negative 8 --max-input-chars 3000 --max-new-tokens 320 `
  --time-budget-s 480 --resume --allow-model-load

# Re-score whatever predictions exist in a run directory (offline)
python -m experiments.innovation_signals_observatory.llm.evaluate `
  --run-dir experiments/innovation_signals_observatory/results/2026-11-04/llm `
  --data experiments/innovation_signals_observatory/results/2026-11-04/jobs_medtronic.jsonl
```

The B run is resumable: predictions are written incrementally and `--resume` skips completed
posting ids. The delivered run was executed as a first pass plus one resume after the declared
wall-clock budget; `manifest_B.json` records `completion.resumed_from_previous_predictions`, the
per-item latencies and the two TIMEOUT items.

## 13. Deviations from the original plan (disclosed)

| Planned | Delivered | Why |
|---|---|---|
| 32 primary + 10 negative (42 items) | **12 primary + 8 negative (20 items)** | the model's wall-clock tail made 42 items incompatible with a usable delivery window; the Lead approved reducing n rather than dropping the negative-control set or latency measurement |
| description budget 12k/8k chars | **3 000 chars**, applied to both arms | measured VRAM/paging at 8k and severe latency variance at 5k (§3) |
| `max_new_tokens` 768 / 700 | **320** | output cap; at 280 the JSON was cut mid-array, so prompt v2 asks for ≤2 capability phrases and the cap is 320 |
| prompt `job-extract-v1` | **`job-extract-v2`** | v2 = ≤2 capability phrases + "drop optional phrases rather than truncate"; the schema is unchanged |
| 20-minute single B run | first pass + one `--resume` pass | a 193 s item consumed the first wall-clock budget; recorded in `manifest_B.json` |
| one `refused`/`invalid_json` error class | adds `truncated` and `TIMEOUT` classes | different causes, different fixes |

## 14. Artefacts and integrity

| Path | Content |
|---|---|
| `experiments/innovation_signals_observatory/llm/job_text_schema.py` | job-text contract, strict decoder, JSON Schema, parser |
| `.../llm/prompt_job_v1.py` | versioned prompt family (v1 → v2 history in the module docstring) |
| `.../llm/subset.py` | declared sampling rule |
| `.../llm/run_job_text_experiment.py` | bounded runner (A/B/C/stub), resume, per-item TIMEOUT, wall-clock budget |
| `.../llm/evaluate.py` | arm-agnostic scorer, ARM_TABLE, internal consistency, adjudication candidates |
| `.../results/2026-11-04/llm/predictions_{A,B}.jsonl` | per-posting predictions, including raw arm outputs |
| `.../results/2026-11-04/llm/subset_{A,B}.json` | selection + rule + per-item metadata |
| `.../results/2026-11-04/llm/manifest_{A,B}.json` | run manifest: data hash + collection reports, model id/weights fingerprint, prompt hash, schema version, subset rule, budget, latency, environment |
| `.../results/2026-11-04/llm/metrics.json` | all measured metrics, caveats, A/B comparison, arm C NOT_RUN |
| `.../results/2026-11-04/llm/evaluation_items.json` | per-item scorer output (quotes, location, support, errors) |
| `.../results/2026-11-04/llm/ARM_TABLE.md` | the arm table with provenance header |
| `.../results/2026-11-04/llm/MANUAL_ADJUDICATION.md` | the author's per-item review table |
| `tests/test_innovation_signals_llm.py` | 27 offline tests (no model, no network) |

Each manifest records: data SHA-256 + collection report hash, model id + weights fingerprint
(revision: local weights directory is not HF-pinned; the unpinned override is recorded explicitly),
rendered prompt template SHA-256, schema version, subset rule and salt, input budget, max new tokens
and the environment. Two runs are comparable only when these match.

## 15. Limitations and threats to validity

* **Single snapshot (T0) of currently-open postings** (dates 2025-11-07 … 2026-11-04). No trend, no
  lag test, no direction claim.
* **No human gold standard.** A/B agreement is not accuracy; cue-support is a conservative lower
  bound; the manual adjudication is single-author and not blind.
* **Small sample (n=20)** and **small negative-control set (8)**: one false positive is 0.125 because
  the denominator is 8. The direction of the result is informative; the exact rate is not precise.
* **Every input was truncated at 3 000 characters** (median omitted ≈ 2 800). A model that saw less
  text may under- or over-classify; the budget is declared, marked in-band and applied to both arms.
* **The two arms did not see identical raw input**: A received the same truncated description text
  and the full title; B received the title and the same truncated description inside the prompt.
  Differences in prompt context (instructions, vocabulary lists) remain and are part of the arm.
* **One model, one prompt, one decode budget, one machine.** Latency is machine- and load-specific;
  the desktop compositor shares the same GPU.
* **Manual review was done after seeing outputs** and by the experiment author; it is a sanity check,
  not ground truth.
