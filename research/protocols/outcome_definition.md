# Outcome definition (frozen) — all prediction targets in the MedRadar programme

**Status:** binding. This document states the outcome (label) definitions that every prediction experiment in
this repository must use. It may not be edited to fit a model result. A new target requires a new entry with
a new ID; an existing definition may be superseded only by appending a supersession note that says what was
wrong and whether any result had been seen.

**Last updated:** 2026-11-03 (hist_v1 freeze). **Owner:** Principal Research Agent.

This file exists to answer the seven questions the research directive requires of a target definition
(§6 of the directive). Each requirement is answered for every target currently in use.

---

## 0. Targets in force

| ID | Target | Experiment | Status |
|---|---|---|---|
| **T-FIRSTENTRY** | first observed public regulatory clearance by company `c` in technology track `k`, within a horizon | `experiments/reverse_rd_v2` (`first_entry_v1`), `experiments/hist_v1` | frozen |
| **T-CONT** | continuation of an already-active `(c,k)` pair: ≥1 material event in the horizon | `experiments/reverse_rd_v1`/`v2` (`continuation`), `experiments/b050`, `experiments/b067` | frozen |
| **T-SUSTAIN** | a *sustained* change in a `(c,k)` filing rate (two consecutive confirmation quarters), not a single pulse | `medradar/intelligence/promotion.py`, `experiments/b026` | frozen |
| **T-SHIFT-HUMAN** | an adjudicated "confirmed shift" in a company's technology position | `research/studies/early_signal_5firms` (Target B) | **not usable yet**: no human labels exist |

`T-SHIFT-HUMAN` has **no labels**. It is listed so that no later analysis can silently treat the agent
pre-adjudication (`ADJUDICATION_AGENT_V1.json`) as ground truth: that file is explicitly a non-human tier.

---

## 1. Requirement: the definition cannot change with model results

Every target is written down before the model is fitted, in the experiment's own pre-registration:

* `experiments/reverse_rd_v2` — `docs/REVERSE_RD.md` (targets fixed at v1; v2 adds a harder target without
  redefining v1) and `data_provenance.json.material_event_rules`.
* `experiments/b026` — pre-registration decisions D-040 and D-042 in `research/DECISIONS.md`.
* `experiments/hist_v1` — `research/protocols/hist_v1_preregistration.md`, frozen with amendments A1–A4
  logged before any fit or metric.
* `research/studies/early_signal_5firms` — `LABELING_PROTOCOL.md` and `PROTOCOL.md`, frozen before packets.

If a definition has to change, the new one is a **new target ID** and the old results stay attached to the
old ID. Precedent: `TODO`/`backlog` items that were re-specified are recorded as retractions in
`research/DECISIONS.md`, not edited away.

## 2. Requirement: positives and negatives have a traceable judgment basis

* **T-FIRSTENTRY / T-CONT** are machine labels read from public regulatory records. The basis is
  `data/medradar.sqlite.events` (or the frozen lane `data/research.sqlite.events`), with
  `source`, `event_id`, `event_date`, `available_at` and the materiality rule recorded in
  `experiments/hist_v1/manifest.json` / `data_provenance.json`. Every positive cell can be traced to the
  event row(s) that make it positive; every negative cell to the absence of such rows in the horizon.
* **T-SUSTAIN** is a rule over the same event stream, implemented and unit-tested in
  `medradar/intelligence/promotion.py`; its thresholds (quarterly, rolling z ≥ 3.5, two-quarter
  confirmation) are declared in the deployment decision D-044/D-045 and carry measured error rates.
* **T-SHIFT-HUMAN** is a human judgement with a written reason and an independent confirmation field,
  validated by `experiments/b098/ingest_human_review.py`, which **refuses to write** on an empty label,
  unknown label, missing reviewer, missing reason, or a `Confirmed Shift` without an independent
  confirmation. No such file exists yet; therefore no human labels exist.

## 3. Requirement: true negatives vs not-yet-observed (right censoring)

The distinction is **explicit in every target's maturity flag**:

* `T-FIRSTENTRY` (reverse_rd_v2): an example is `matur*` only if `cutoff + horizon ≤ coverage_end`;
  pending examples are skipped and counted (`skipped_pending_examples = 0` in that run by construction).
* `hist_v1`: a cell is label-mature iff `t + h ≤ 2026-Q2`; immature cells are excluded and their count is
  reported in `results.json.dataset` and in the report. A pair that never enters is a **candidate** every
  quarter, not a negative "forever"; only its matured windows contribute a 0.
* `T-CONT` (b050/b067): the outcome window is closed before the origin; cells whose window crosses the data
  end are excluded, not treated as zero.
* `T-SUSTAIN`: a missing confirmation quarter is `PENDING`, never `rejected`; promotion policy has no
  automated path.

A zero therefore means "the horizon closed and no qualifying event occurred", not "we did not look".

## 4. Requirement: handle right censoring at the end of the study window

* The last complete quarter is **2026-Q2** for openFDA device data in this store (2026-Q3 is partial and is
  excluded; the store's event dates run to 2026-10-18).
* Every origin `t` used for a horizon `h` satisfies `t + h ≤ 2026-Q2`; the code asserts this and the
  evaluator records the excluded counts.
* Pooled/mean metrics are computed only over matured cells. No metric extrapolates beyond 2026-Q2.
* The prospective forecast registry (`research/forecasts/`) is the only genuine out-of-window device; it is
  scored only when its window closes (`experiments/b068/maturate_forecasts.py`), and 25 sets are pending.

## 5. Requirement: historical entered vs first entered

Targets that use "entry" must state which of the two they mean:

* `first_entry_v1` (reverse_rd_v2): candidate pairs have **zero** material events in
  `(t − 36 months, t]`; the label is a first event in the horizon. Because the lane starts in 2016, this is
  "first observed in the lane", and the left-censoring is stated in that report.
* `hist_v1`: candidate pairs have **zero** material events in the whole observed history up to `t`
  (store starts 1976). The outcome is the **first ever observed** clearance in the track; a pair that
  entered before 1976 is indistinguishable from one that never entered and is declared left-censored.
  Re-entry (a second entry after dormancy) is a **different** target and is not used in hist_v1.
* `early_signal_5firms`: `novel_entry` means no event in the track for ≥12 months before the event — a
  **re-entry-like** definition. It is labelled as such and is not comparable to a first-ever entry.

No analysis may compare a first-ever-entry estimate with a dormancy-restricted estimate without saying so.

## 6. Requirement: no feature may be generated from information that only exists after the label event

* Feature availability is enforced by a recorded event clock: `event_date` (when it happened),
  `available_at` (when it became usable), `first_seen_at` (when this programme collected it), `fetched_at`
  (retrieval time). Features use `available_at ≤ cutoff`; label windows open strictly after the cutoff;
  training cells are purged when their label window overlaps the test origin.
* Independently audited, not asserted: reverse_rd_v2 recomputed 1,107,081 feature values in an as-of replay
  with 0 mismatches; hist_v1 is required to run a seeded 300-cell replay (`protocol §12`).
* The known residual risks are documented rather than denied: the product-code→track taxonomy is current
  and unversioned (applying it to history can make a track look newer than it was), and
  `available_at = decision_date` is an estimate of public availability for historical FDA records.

## 7. Requirement: one event may not be counted as several independent targets

* Entry targets are **single-use**: after a pair's first entry, the pair leaves the risk set, so a single
  event can contribute to at most `h` positive cells (the horizon window), never to two independent
  entries.
* Continuation targets use non-overlapping outcome windows where possible; b050's overlapping horizons are
  reported as "not independent replications".
* Public events that appear in two sources are deduplicated by `event_id` and by the materiality rule, and
  a PMA supplement is not counted as a new approval.
* The five-company study collapses 17 trial–clearance pairs into 9 distinct later clearances before
  computing any distribution (`LEAD_TIME_SMALL_SAMPLE.md`).

---

## 8. What is explicitly **not** an outcome

* An internal R&D decision, an unannounced project, or "company X is secretly developing Y". The store
  cannot observe these and no label may claim to.
* Stock returns or market capitalisation. Market data is an auxiliary explanatory variable only
  (directive §4E; `research/MISSION.md` §7.4).
* An agent-produced label. The grading rubric of `ADJUDICATION_AGENT_V1` is a triage instrument, not truth.

## 9. Change log

| date | target | change | result seen before change? |
|---|---|---|---|
| 2026-11-02 | T-FIRSTENTRY | created (reverse_rd_v2 `first_entry_v1`) | no |
| 2026-11-03 | T-FIRSTENTRY | hist_v1 adds a full-history variant; the reverse_rd_v2 definition is unchanged | no |
| 2026-11-03 | T-SUSTAIN | policy v2 withholds the ramp label below 1.0 event/series-month (D-061); the binary sustained label is unchanged | yes (density experiment) — declared in D-061 |
