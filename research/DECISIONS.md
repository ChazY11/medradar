# Decision record

ADR-style. Each decision states the alternatives considered and the evidence that
settled it. Superseded decisions stay in the file with a pointer.

---

## D-001 — Build new work on `integration/market-to-rd-v2`, not on `main`

**Date:** 2026-11-02. **Status:** accepted.

`main` is frozen at `7a639f7` (v0.2.2). The audited, integrated research foundation
plus Phases 1–3 live on `integration/market-to-rd-v2` at `1749bd5` (v0.5.0), with
679 offline tests green and all real-data artifacts committed there.

*Alternatives:* merge the integration branch into `main` first (rejected for now —
the branch has an open PR #4 whose CI status is unverified; merging an unverified
head moves the stable reference point); restart from the foundation commit `dedfd68`
(rejected — it would discard Phases 1–3, which are the actual scientific content).

*Consequence:* cycle 2 branches from `1749bd5` as `research/cycle2-coverage-power`.
`main` stays untouched until an independent verification pass on an exact commit.

---

## D-002 — No fuzzy entity matching; deterministic legal-entity universe

**Date:** 2026-11-02. **Status:** accepted.

The 510(k) lane links to a curated company only 16.9% of the time. The tempting fix
is fuzzy name matching to raise recall. Rejected: a false merge silently relabels a
competitor's milestone as the target company's, which poisons *labels* rather than
features, and no amount of leakage auditing detects it.

*Decision:* build a deterministic universe of legal applicant entities via
documented suffix normalisation with **no** cross-name fuzzy merging, then compare
entity granularity explicitly (E12: legal applicant vs corporate parent). Precision
is auditable; recall loss is visible as many small entities instead of silent
contamination.

---

## D-003 — A negative result about added data sources is a result, not a failure

**Date:** 2026-11-02. **Status:** accepted.

E4–E6 found no statistically detectable ranking gain from consolidated SEC
financials, point-in-time market features or OpenAlex publication counts. The
temptation is to keep adding model capacity until something "wins". Rejected as
p-hacking by another name.

*Decision:* publish the nulls, then test whether they are *underpowered* nulls via
minimum detectable effect (E13). "No effect detectable at this power" and "no
effect" are different sentences and must not be conflated.

---

## D-004 — Durability for the 8-K lane until CIK-based linking is verified

**Date:** 2026-11-02. **Status:** provisional.

In the legacy full-history DB, 19,616 of 20,976 `8k_catalyst` events have no
`company_key` even though EDGAR filings carry a CIK and the company registry already
has CIK identifiers. This is a deterministic linking opportunity (not fuzzy), and it
is assigned to a later cycle rather than this one, so that cycle 2 keeps a single
explanatory variable (entity universe size). Recorded so it is not silently forgotten.

---

## D-005 — Frozen artifacts are immutable inputs

**Date:** 2026-11-02. **Status:** accepted.

`experiments/reverse_rd_v1/`, `experiments/reverse_rd_v2/` and the three
`data/*.sqlite` stores are treated as frozen. Cycle 2 writes only new directories and
new tables. Re-running a frozen experiment must reproduce its committed numbers
byte-for-byte; if it does not, that is a defect to report, not a number to update.

---

## D-006 — Pre-register the test windows before modelling

**Date:** 2026-11-02. **Status:** accepted.

The entry target has 24 quarterly origins. Holdout windows and the primary metric
(PR-AUC / average precision) are fixed before any cycle-2 model is fitted. Reporting
the window that "works" (v2 found one of three excludes zero) is exactly the failure
mode this prevents. All windows are reported; the window mean and per-window values
are both published.

---

## D-007 — Cycle-2 primary spec excludes financial features, for both panels

**Date:** 2026-11-02. **Status:** accepted.

The entity cohort is not CIK-mapped, so consolidated SEC features exist for only a
handful of cohort entities. Including them would compare a panel with financial
coverage against one without, confounding the entity-universe change with a feature
change. Both panels therefore run the identical 16-feature R&D+entry specification
(the `rd_only` cycle-1 headline used 10 features; the 16-feature number is therefore
not directly the frozen number and both are reported).

---

## D-008 — Cohort is ranked by material-event count, not all-row activity

**Date:** 2026-11-02. **Status:** accepted, with a documented reproducibility gap.

The committed `config/universe_v1.json` ranks entities by activity over all
510(k)/PMA rows (PMA supplements included), while the cycle-2 panel builds its
universe over the material event set (the same rule the labels use) and ranks by
material count. The two 200-entity cohorts differ by 5 boundary entities (2.5%),
with the same five focus companies pinned and the same minimum material count.

*Why not silently swap to the artifact cohort:* it would substitute a rule that is
inconsistent with the labels for one that is consistent. *Why not silently keep it:*
a reader comparing the panel to the artifact deserves to know they differ. The
discrepancy is stated in `experiments/cycle2_coverage/REPORT.md` §2 and a sensitivity
run on the artifact cohort is backlog item B-017.

---

## D-009 — "Detection at matched FAR" is not "earlier warning"

**Date:** 2026-11-02. **Status:** accepted as a reporting rule.

Cycle 2 found a large matched-FAR detection advantage (+0.30…+0.44 more positives
detected at the same false-alarm budget) but lead-time deltas that are negative in
four of six windows. Future reports must separate these two claims: detecting more
entries and detecting them earlier are different capabilities, and only the first is
supported here.

---

## D-010 — No merge to `main` in cycle 2

**Date:** 2026-11-02. **Status:** accepted.

Cycle 2 ships on `research/cycle2-coverage-power` and a PR. `main` stays at
`7a639f7` pending an independent verification pass on the exact commit; the accepted
run was performed by the same agent that wrote the pipeline, so cross-verification is
still outstanding.

---

## D-011 — Strategic realignment: Observe → Understand → Anticipate

**Date:** 2026-11-02. **Status:** accepted (owner instruction). Supersedes the previous framing in
which forecasting-model research was the organising principle.

MedRadar is now **Global MedTech Intelligence & Foresight**, organised as three ascending layers:
Observe (notice real change early), Understand (explain it with traceable evidence), Anticipate
(identify forming trends, then forecast verifiable events). Priorities become P0 scientific
reliability, P1 technology-change detection, P2 AI research intelligence, P3 forecasting research,
P4 advanced algorithms.

*What this changes:* the next cycles target change **detection**, not forecasting; the Observe layer
is now the frontier because it is the weakest part relative to mission.

*What this does not change:* no restart, no deletion, no blind refactor. The cycle-1/2 forecasting
work, the bitemporal store, the forecast registry and the ablation program are **preserved intact**
as the Anticipate (Level B) program at P3. The epistemic rules in `MISSION.md` §7 are unchanged and
still bind everything. Architecture mapping of every existing module: `LAYERS.md`.

*Consequence for scope:* the previously open idea of a general cross-industry forecasting platform is
explicitly out of scope; the object of study is the leading medtech firms.

---

## D-012 — Anticipate Level B is preserved, frozen and demoted to P3

**Date:** 2026-11-02. **Status:** accepted.

Cycle-2 artifacts, the frozen cycle-1 benchmark, the 25 registered nowcasts and the forecast
registry are kept and remain runnable. They are **not** extended in the current phase, and they must
not outrank P0–P2 work in the backlog. Any future extension must first satisfy an Observe-layer
requirement or an explicit owner request.

*Why not delete:* the work is scientifically valid and independently audited; it is the largest
existing body of evidence about the predictability of this data, and deleting it would lose the
baseline that future claims must beat.

---

## D-013 — Detection is pre-registered before the benchmark runs

**Date:** 2026-11-02. **Status:** accepted.

The change-detection cycle is pre-registered as follows, before any result is seen:

- **Streams:** monthly material-event counts per (entity, technology track), 2016-11…2026-10,
  built on the deterministic legal-entity universe.
- **Detectors:** naive rate-multiplier (baseline comparator), rolling z-score, Poisson CUSUM,
  Poisson Bayes factor — identical streams, identical evaluation.
- **Evaluation A (controlled truth):** inject a known step change (seeded grid over magnitude and
  onset) into real monthly stream shapes; report detection probability, detection delay in months
  and false alarms per stream-year; run leave-company-out.
- **Evaluation B (real data):** Benjamini–Hochberg FDR across tested cells; for each alert, test
  whether an independent source shows elevated activity in the following 12 months relative to
  matched non-alert control periods.
- **Guards:** minimum baseline and total events, month-of-year seasonality, product-code
  reassignment audit, explicit spike-vs-level-shift distinction.
- **Decision rule:** the likelihood-based detectors are declared better only if they dominate the
  naive baseline on the delay-vs-false-alarm frontier across the seeded grid *and* keep that
  ordering under leave-company-out. A tie or a loss is reported as such.

*What a positive result licenses:* that the detector finds rate changes in this data earlier at the
same false-alarm budget. *What it does not license:* that the change is strategically important, or
that the company intends anything. Those are Understand-layer judgements, not detection outputs.

---

## D-014 — Detection design amendments, declared before any result was computed

**Date:** 2026-11-02. **Status:** accepted. These amend D-013 **before** the benchmark was run;
no detector output existed at the time of writing. They are recorded separately so that a reader
can verify the ordering from the commit history rather than take it on trust.

1. **Two granularities, one primary and one secondary.** The legal-entity universe groups activity
   at the curated *technology track* level (38 tracks in the lane) and the taxonomy also exposes a
   coarser *domain* level (23 domains). The pre-registered primary remains **entity × track**.
   Entity × domain is added as a **pre-declared secondary** because it is denser (124 cells vs 107,
   4,162 vs 3,404 events) and closer to the "technology area" language of the mission. Both are
   reported; the primary is not swapped after the fact.
2. **Quarterly sensitivity.** The lane is far sparser than expected: eligible cells have a median of
   25 material events across 120 months and are zero in 98 of those 120 months. Monthly detection
   therefore has very low power by construction. A quarterly aggregation is added as a
   **pre-declared sensitivity** so the report can distinguish "the detector is weak" from "the
   monthly resolution is underpowered on this lane".
3. **Out-of-sample threshold calibration is mandatory.** Detector sensitivity knobs are tuned on a
   calibration half of the cells (split deterministically by entity hash) to a fixed target false
   alarm rate, then frozen and applied unchanged to the held-out half. Reporting a threshold tuned
   on the same data it is evaluated on would invalidate the comparison.
4. **Spike injections are added to the controlled-truth design.** Besides sustained level shifts, a
   single-month spike is injected and the detector's response recorded. The OBSERVE layer's purpose
   is to surface *sustained* technology change, so a detector that cannot distinguish a one-month
   spike from a level shift is not fit for the mission even if its delay looks good.
5. **Matched false-alarm rates are realised, not assumed.** Detectors are compared at the
   *achieved* false alarm rate on the held-out half, with the delay measured on detections inside a
   pre-declared 12-month horizon. If two detectors sit at different realised FARs, the comparison
   states both numbers rather than claiming a match.

6. **Track-assignment provenance is a first-class guard.** Audited before the benchmark: the
   explicit `{product_code: track_id}` map assigns **17,754 of 18,889** material events with a
   track (94.0 %); the remaining **1,135 (6.0 %)** are assigned by device-text keyword matching,
   and every one of the 72 product codes that lands in more than one track is in that fallback
   set. Keyword assignment is not deterministic per code, so a wording change can move events
   between cells and manufacture an apparent change. The primary benchmark therefore uses all
   material events, and a **pre-declared clean variant** (`track_clean`, 100 cells / 3,222 events)
   restricting to deterministically assigned events is reported alongside it. Evidence:
   `experiments/detect_v1/track_assignment_audit.json` and `reassignment_audit.json`.

---

## D-015 — Detection calibration corrections, made after a partial run and fully disclosed

**Date:** 2026-11-02. **Status:** accepted, with superseded numbers recorded.

Two structural defects were found in the first pass of the benchmark. Both were in the
*evaluation harness*, not in the detectors, and both are recorded here rather than quietly fixed.

1. **Unreachable false-alarm target.** The first draft calibrated to "alarms per cell-year" with a
   target of 0.25, but detectors emit at most one alarm per stream and a stream spans ten years, so
   the maximum achievable value is 0.10. Every knob therefore "passed" and the selection rule
   (which then picked the *least* sensitive knob) was inverted. Superseded partial output on the
   `track` and `track_clean` levels: naive 0.305, z-score 0.374, CUSUM 0.335, Bayes factor 0.040
   detection probability. Those numbers are **not** results and must not be cited.
2. **Knob grid too narrow to reach the budget.** With the corrected metric (fraction of uninjected
   cells alarmed, target 5 %) none of the three conventional detectors could reach the budget: their
   least sensitive grid points still alarmed on 15-32 % of streams, because scanning 120 months for
   a change is a multiple-testing problem. The grids were extended (naive multiplier to 25,
   z-score to 15, CUSUM to 80, Bayes factor to 120) so that every detector can be placed inside the
   same alarm budget. Partial output with the narrow grid is likewise superseded.

**Why this does not invalidate the comparison.** All four detectors are calibrated by the same rule
on the same calibration half and evaluated on the same held-out half; the correction changes the
operating point, not the terms of the contest. The final numbers report both the calibration and the
realised false-alarm rate, so a reader can check that detectors are compared inside a similar budget
rather than at their individually flattering thresholds.

**What it does establish as a finding in its own right:** an alarm budget of 5 % per stream is not
reachable by conventional CUSUM/z-score scanning on this lane without widening the threshold so far
that detection collapses. The sparsity of the lane, not the choice of algorithm, is the binding
constraint — which is exactly the kind of conclusion the OBSERVE layer needed to learn before
investing in more detectors.

---

## D-016 — Frontier replaces single-point calibration; partial month excluded; onset tolerance

**Date:** 2026-11-02. **Status:** accepted. All three changes were forced by evidence found while
running the cycle; each is recorded with what it supersedes.

1. **Single-point calibration abandoned for a full frontier.** The first working design tuned one
   sensitivity knob per detector on a calibration half of ~50 cells to a false-alarm budget, then
   froze it. That proved unstable: on the domain panel it selected a threshold whose calibration
   false-alarm rate was 0.000 yet whose held-out detection collapsed to 0.04, while the same
   detector at a different knob reached 0.22 — the choice of knob, not the detector, was driving
   the conclusion. The benchmark now reports the **entire false-alarm/detection frontier** for
   every detector (one point per knob) and reads it out at fixed budgets. Superseded numbers:
   an earlier calibrated run that reported the Bayes factor as best (P≈0.23–0.25 at ~3 %
   realised false-alarm rate). Those numbers are **not** results.
2. **The final calendar month is excluded.** The lane ends 2026-10-15, so the last month is about
   half a normal month and manufactures an apparent volume drop (flagged independently in
   `docs/research/DETECTION_DESIGN_REVIEW.md`). The window is truncated to complete months
   (2016-11 … 2026-09, 119 months). Cell counts therefore changed slightly (107 → 104 track
   cells; 124 → 121 domain cells); earlier cell counts in D-014 are superseded.
3. **One-month pre-onset tolerance.** The detector implementer reported that the Poisson Bayes
   factor returns its *estimated change point*, which legitimately lands one month before the true
   onset; without tolerance its detections were miscounted as misses. A detection is now credited
   in `[onset − 1, onset + horizon]`, identically for every detector.

**Reinterpretation forced by the independent design review.** A step change injected into a
Poisson rate is the alternative a matched rate-ratio test is optimal for, and the review correctly
argues that a likelihood detector winning under it would be close to a theorem. The observed
outcome is the opposite — the naive rate-multiplier is best — so the injection acts as a **positive
control** and the licensed claim is narrow: *for abrupt, permanent, multiplicative rate shifts on
this lane, a matched simple test is at least as good as the likelihood detectors.* Ramp, transient
and heterogeneous alternatives remain untested (B-026), and no claim is made about detectors in
general.
