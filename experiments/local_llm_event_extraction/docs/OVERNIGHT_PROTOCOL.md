# Overnight exploratory QLoRA run — protocol and scope

Run date: 2026-11-04 (Asia/Shanghai). Branch: `research/overnight-qlora-s030`.
Baseline: PR #19, `research/local-llm-foundation`.

This document is the pre-registration for the overnight run. It was written
before the training run finished and is committed with it; where the run departed
from this plan, the departure is recorded in the morning report rather than
edited back into this file.

---

## 1. Question

> Can a 4B-parameter instruction-tuned model be adapted, with QLoRA and only
> automatically derivable labels, to emit MedRadar's event-extraction schema with
> verbatim evidence — and does that adaptation measurably improve extraction over
> the same model untuned, on companies and documents it never saw?

A secondary question, forced by the Phase 2 defect report:

> How much of Phase 2's measured failure was the *system* (prompt, validator,
> date semantics, benchmark plumbing) rather than the *model*?

## 2. What tier this run is, and is not

| | |
|---|---|
| Label tier of training and evaluation data | `SOURCE_DERIVED_SILVER` |
| Run tier | `EXPLORATORY_WEAK_SUPERVISION` |
| Research-grade training | `RESEARCH_TRAINING_BLOCKED` — unchanged |
| Precision / recall / F1 | `NOT_EVALUABLE` — no human labels exist |

The labels are copied from the same public records the documents were rendered
from. They are independent of every model, which is what makes them usable as a
training signal at all, but they are **not independent of the document** and they
are **not human annotations**. Therefore:

* no precision, recall or F1 may be quoted from this run;
* what is reported is *exploratory agreement* — category, event date, company and
  product agreement on documents that carry a silver event;
* harness-level facts (JSON validity, schema acceptance, verbatim-quote location,
  abstention, latency, VRAM) are measured facts and are reported as such.

Phase 2's negative and blocked results stand as recorded. Nothing here re-opens
them.

## 3. Data

### 3.1 Source records

104 public records, collected once and frozen:

| source | records | licence basis |
|---|---:|---|
| openFDA 510(k) | 24 | U.S. Government work (public domain) |
| openFDA PMA | 24 | U.S. Government work (public domain) |
| openFDA recall | 24 | U.S. Government work (public domain) |
| ClinicalTrials.gov study records | 29 | public NLM data |
| openFDA device classification (negative controls) | 3 | U.S. Government work |

Twelve companies from the project's own entity roster. No press releases, no news
articles, no copyrighted full text: every `text` field is either a deterministic
rendering of that record's declared fields (`structural_rendering`) or
template-generated prose over the same fields (`synthetic_narrative`). The
per-record `text_origin` field says which, and every report stratifies by it.

### 3.2 Why the text is rendered rather than downloaded

Downloading real press releases would import a licence question that the project
cannot settle at 3 a.m., and would silently mix "model fails on prose" with
"model fails on marketing speak". Rendering the *public structured record* gives
full provenance, zero licence risk, and a clean two-stratum design: can the model
read a field rendering, and can it read prose generated over the same facts?

The cost is stated plainly: `synthetic_narrative` is not human-written prose, so
prose generalisation to real press releases remains **untested**.

### 3.3 Splits

Grouped, seeded, and assigned over **near-duplicate leakage components** rather
than raw companies: structural renderings of the same source type share >80% of
their 5-character shingles across companies, so a company-only split would carry
the template across the boundary. The transitive closure of companies linked by a
near-duplicate pair is the split unit. The audit is executed by the benchmark
runner (it was not, in Phase 2) and its result is stored with the run.

Result: train 70 / validation 14 / test 20 cases, no component in two splits.

Negative controls are test-only. Training therefore contains **no abstention
examples**; abstention on the negative controls is a zero-shot behaviour
measurement, not a memorisation check. This is a deliberate, recorded limitation.

## 4. Arms

| arm | system | notes |
|---|---|---|
| A0 | Phase 2 deterministic rules | unchanged |
| A1 | A0 + locale-declared numeric dates + declared `event_date_kind` | exactly two declared changes |
| B | Qwen3-4B-Instruct-2507, untuned, prompt v2 | same weights, same decoding |
| C | B + exploratory QLoRA adapter, prompt v2 | the training output |

All arms see the same documents, the same task definition and the same available
input metadata. The company-canonical-id hint is part of the *closed-roster*
condition and is declared as such; entity agreement under it measures
transcription, not open-set linking.

## 5. Training configuration (fixed before the run)

| parameter | value |
|---|---|
| base weights | `D:\DEPPSKK\ml-models\Qwen3-4B-Instruct-2507`, revision `cdbee75f17c01a7cc42f958dc650907174af0554` |
| quantisation | 4-bit NF4, double quant, bf16 compute |
| LoRA | r=16, alpha=32, dropout=0.05, q/k/v/o/gate/up/down |
| optimiser | AdamW, lr 1e-4, no weight decay |
| batching | micro-batch 1, gradient accumulation 4 |
| sequence budget | 3328 tokens (measured: prompt ≤2750, target ≤349) |
| epochs | ≤300 optimiser steps (≈4 passes over 70 records) |
| eval | teacher-forced validation loss every 40 steps, 14 records |
| checkpoint | every 100 steps + final; resume state includes optimiser and RNG |
| seed | 20261104 |
| wall budget | 2400 s, hard stop |

## 6. Safety limits (enforced in code, not by an operator)

GPU wall time ≤ 2400 s for this phase (the 7-hour figure is the project's
overnight envelope, of which this single run may consume only a bounded slice);
step cap; 5-minute resource sampling of GPU temperature, VRAM, CPU and RAM;
automatic stop on non-finite loss, on sustained GPU temperature ≥87 °C, and on
three consecutive validation-loss evaluations without improvement; a single
automatic OOM downgrade at most; periodic checkpoints so a stop is never data
loss. No unbounded retry loop exists anywhere in the training script.

## 7. Metrics and what may be claimed

Reported per arm, always stratified by `text_origin`, source type and
`event_date_kind`:

* JSON validity and **schema acceptance** (the real validator, not a JSON parse);
* verbatim-quote location rate;
* extracted event count, abstention rate, wrong-abstention rate;
* false-assertion rate on the negative controls;
* **exploratory agreement** for category / event date / company / product;
* error taxonomy by validator code;
* latency, peak VRAM, throughput.

Never reported: precision, recall, F1. Those require human labels and are marked
`NOT_EVALUABLE` in every artifact this run writes.

## 8. Ablations in scope

* **prompt v1 vs prompt v2** with the same checkpoint and the same split — isolates
  the closed-vocabulary and date-semantics fixes from the model.
* **untuned vs adapted** — isolates the training effect.
* **A0 vs A1** — isolates the deterministic date/date-kind fixes.

Out of scope tonight, and why: negative-control training samples (would need a
disjoint negative corpus to avoid contaminating the abstention metric), LoRA rank
sweeps (no independent human-labelled signal to select on), and any change that
would make the evaluation set smaller or the leakage audit weaker.

## 9. Deliverables

* this protocol;
* the frozen corpus with per-record provenance and content hashes;
* the dataset builder with its audit;
* the training run record, resource log, loss/eval history and adapter hashes;
* the evaluation run directories with per-document predictions;
* a machine-readable summary and an artifact index;
* the Chinese morning report (`OVERNIGHT_RESEARCH_REPORT.zh-CN.md`);
* a draft PR that does **not** merge and does **not** contain weights.
