# Data adapter: from existing MedRadar artifacts to extraction labels

**Status:** design + a working read-only implementation (`labels.py`). No label has been
converted into a training target, because no human label exists yet.

**Scope.** This document answers three questions:

1. What does the adapter read today, and what does it *find*? (measured, not remembered)
2. Why can the 69 evidence packets not be dropped into the extraction benchmark as-is?
3. What exactly must be true before `DATA_READY` is allowed to be true?

---

## 1. The adapter that exists

`experiments/local_llm_event_extraction/labels.py` is a strictly read-only bridge over
`research/studies/early_signal_5firms/`. It opens four artifacts for reading and nothing else:

| Artifact | What it is used for |
|---|---|
| `HUMAN_REVIEW_WORKSHEET.csv` | the 69-packet review sheet; `human_label` is the human decision column |
| `CASE_CANDIDATES.json` | the 60 pre-declared candidate cases and their stratum |
| `CASE_PACKETS_SMALL_SAMPLE_V2.json` | the 9-packet small sample and its `human_review_status` |
| `EVIDENCE_TIME_AUDIT.json` | per-source availability tier and the assumed lags (the point-in-time audit) |
| `ai_review/AI_EVIDENCE_REVIEW.jsonl` | optional: the separate AI review tier, if it is present in this checkout |

It never writes, never migrates, never "fixes" a row, and refuses to follow a path that escapes
the study directory (`_contained()`). Run it with:

```
python -m experiments.local_llm_event_extraction.labels --pretty
```

The report is JSON, is marked `"read_only": true`, and contains separate `data_readiness`
and `pit_readiness` blocks rather than one convenient summary score.

## 2. Current state (measured 2026-11-04)

| Quantity | Value | Where it comes from |
|---|---:|---|
| Evidence packets | 69 | `HUMAN_REVIEW_WORKSHEET.csv` rows |
| — candidate stratum | 60 | `origin=candidate` |
| — small sample | 9 | `origin=small_sample` |
| **Human-confirmed labels** | **0** | `human_label` is empty on all 69 rows |
| Machine rubric pre-annotations | 69 | `agent_preliminary_label`: 45 × "Uncertain", 18 × "Routine Iteration", 6 × "Not Assessable" |
| AI review records (separate tier, other branch) | 69 | `AI_EVIDENCE_REVIEW.jsonl`, each `status=AI_ADJUDICATED` |
| Companies represented | 4 of 5 | Medtronic 21 · Philips 23 · GE HealthCare 16 · Mindray 9 · **Dräger 0** |
| `DATA` readiness | `NOT_READY` | blockers: `NO_HUMAN_CONFIRMED_LABELS`, `COMPANY_UNDER_REPRESENTED(draeger=0<6)` |
| `PIT` readiness | `PARTIAL` | 5 unresolved availability issues (§5) |

Two consequences that the rest of the experiment must live with:

* **A machine rubric label is not an event label.** "Uncertain (agent-preliminary)" cannot be
  mapped onto `event_category`; it is a triage decision. Counting it as a label would inflate
  coverage by 69 while adding zero usable supervision.
* **An AI adjudication is not human truth.** The AI review is a real, audited tier and is useful
  as a *prior* or as a *disagreement detector*. It may never be the gold set for evaluating a
  model, because then the model would be graded by its own kind.

## 3. Why the 69 packets are not yet an extraction benchmark

1. **A packet is a case, not a document.** Each packet records company × technology track × a
   later clearance plus a representative trial. The extraction task needs the *document text*
   (press release, 510(k) summary, trial record) verbatim, and that text is not stored in the
   packet. Producing it requires a read-only join back to the frozen stores — a different step
   that has not been built.
2. **`evidence_summary` is a summary, not a span.** Citation correctness is measured by locating
   an exact quote in the source document. A summary cannot be located, so scoring against it
   would measure agreement with a summary rather than grounding.
3. **The sample was selected for feasibility, not for representativeness.** Sixty cases across
   five firms cannot support a population-level claim, and Dräger contributes zero packets.
4. **The labels are pending**, so the current state is `unlabelled` (not "weakly labelled").
5. **Case selection used later knowledge.** The packets were built *from* the later clearance
   backwards. That is fine for describing a case; it is not a point-in-time sample, and it must
   never be described as one.

## 4. Field mapping (for the future derivation step)

| Study artifact field | Experiment contract field | Caveat |
|---|---|---|
| `company` | `GoldEvent.company_canonical_id` | must resolve through the roster; Dräger/Mindray have no `company_key` |
| `technology_track` | `GoldEvent.technology_domains` | current taxonomy is applied to history unversioned |
| `event_or_trial_date` | `GoldEvent.event_date` | event date, **not** publication date |
| `clearance_or_record` | `GoldEvent.event_category` (candidate) | `510k/pma` maps to `regulatory_clearance`/`regulatory_approval` only after reading the record type |
| `third_source_lead_days` | not a label — context only | negative leads exist (source after clearance) |
| `evidence_summary` | **rejected** as `evidence_quote` | not verbatim; must be re-derived from source text |
| `human_label` | `GoldEvent.label_tier` | empty today ⇒ `unlabelled` |
| `agent_preliminary_label` | none | machine rubric text; never a tier |
| AI review `review.label` | `label_tier="ai_preliminary"` | never `human_confirmed` |

## 5. Readiness criteria (pre-registered, not negotiable after seeing results)

### `DATA_READY` requires all of

- **≥ 60 human-confirmed documents** (not packets) across **≥ 4 categories**, with **≥ 5
  documents per evaluated category**;
- **≥ 6 human-confirmed documents per deep-case company**, all five companies present;
- an **independent test set of ≥ 24 documents**, grouped by company and by document family, never
  used for prompt development, model selection or threshold tuning;
- a **document-level provenance chain**: source store, record id, retrieval timestamp, and the
  exact span a human selected as evidence;
- a recorded **label agreement check** (two raters on a subset, with disagreements adjudicated),
  because a single annotator's labels are a measurement with unknown error.

### `PIT_READY` requires all of

- every source used by a predictive claim has either a recorded publication timestamp or a
  declared, sensitivity-tested lag;
- `first_seen_at` is never used as a publication date (it records *our* collection time);
- the entity resolution for the four alias-resolved firms is audited.

**Current `PIT` state is `PARTIAL`**, because the audit itself records five unresolved items:

1. no recorded per-record publication timestamp for openFDA bulk extracts: availability must be
   reconstructed from the event date with a declared lag and sensitivity analysis;
2. the roster has no `company_key` for Dräger or Mindray: their events are alias-resolved, which
   requires an entity-resolution audit before any firm-level claim;
3. `procurement_awards` records `announcement_date`/`award_date` as NULL for all rows and
   `data_quality` says `first_publication_unknown`, so that source is Tier C for this study;
4. patents are absent from all frozen stores (upstream access blocked); no patent claim can be
   made;
5. `publication_counts` is annual, company-level and limited to 616 rows, so it cannot supply
   quarterly lead-time evidence.

These are quoted from `EVIDENCE_TIME_AUDIT.json` via `assess_pit_readiness()` rather than typed
from memory; the function returns them in `evidence.unresolved_reasons`.

## 6. Read-only guarantees (enforced by code, not by intention)

- Paths are resolved and must remain under the study directory; otherwise `ValueError`.
- Files are opened with mode `"r"`; the test suite hashes and `stat`s the study artifacts before
  and after a load and asserts nothing changed.
- There is no function that accepts an output path, and no option on the CLI that writes.
- A missing artifact yields an empty state plus an explicit blocker; it never yields a default
  that looks like data.

## 7. What this adapter deliberately does not do

- It does not extract documents from the frozen stores (that is the derivation step, and it must
  also be read-only).
- It does not build training targets. `training/dataset_builder.py` accepts only research-grade
  tiers and will refuse the current state with `DataNotReady`.
- It does not decide that the study is feasible. It reports what is missing, so a human can
  decide.
