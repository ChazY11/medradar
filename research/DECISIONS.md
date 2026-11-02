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

---

## D-017 — Three robustness sensitivities pre-declared before running them

**Date:** 2026-11-02. **Status:** accepted. Declared after cycle 3 was published but **before** these
sensitivity results exist. Cycle-3 artifacts stay frozen; these are separate panels.

The cycle-3 conclusion ("the naive rate-multiplier is not beaten at a matched 2 % false-alarm
budget, and data density is the binding constraint") has two obvious threats that can be tested
with data already in the lane. All three are pre-declared with predictions so the outcome can count
for or against the conclusion.

1. **Density (B-034) — quarterly aggregation.** Monthly cells have a median of 25 events over 119
   months. Aggregating to quarters triples the count per bin and cuts the series to 40 points.
   *Prediction:* absolute detection probability rises for **every** detector, the naive detector
   stays best or the gap narrows, and the ranking is unchanged. If a likelihood detector overtakes
   the naive one at quarterly resolution, cycle 3's conclusion is resolution-specific and must be
   restated that way.
2. **Product maintenance (B-035) — exclude Special 510(k)s.** 4,685 of 31,219 lane 510(k)s (15.01 %)
   are `clearance_type="Special"`, i.e. modifications of the filer's own cleared device. *Prediction:*
   cell counts fall substantially, detection probability falls slightly for all detectors, and the
   ranking does not change. If the naive advantage disappears when maintenance filings are removed,
   the cycle-3 comparison was partly a comparison of how each detector responds to maintenance noise.
3. **Taxonomy churn (B-036) — mask codes first appearing late in the lane.** 436 of 1,905 lane
   product codes (22.9 %) first appear in 2022 or later, though they carry only 2.6 % of events;
   an independent review measured much higher concentration in specific tracks (e.g. ~41 % of one
   track's recent events under codes created 2022+). *Prediction:* the churn-masked panel changes
   detection probability by less than its interval width at the whole-lane level, because churn is
   concentrated rather than global.

**What would overturn cycle 3.** Any of: a likelihood detector becoming the best detector under
quarterly aggregation; the naive advantage vanishing under the maintenance filter; or the
churn-masked panel reversing the ranking. Each outcome is a legitimate result and will be reported
as a correction to cycle 3 rather than as a new finding.

---

## D-018 — Outcome of the D-017 sensitivities: the cycle-3 conclusion is resolution-specific

**Date:** 2026-11-02. **Status:** accepted. This records the result of a pre-declared test; it
**corrects** cycle 3 rather than adding to it.

The three sensitivities were declared in D-017 before being run. Default panels were re-run first
and reproduce the frozen cycle-3 frontier point-for-point
(`experiments/detect_v1/check_frozen_reproduction.py` → PASS), so the comparison is not a harness
artefact. Results at a matched 2 % per-stream false-alarm budget, best point inside the budget:

| panel | naive | rolling z | Poisson CUSUM | Poisson Bayes factor | paired Bayes vs naive |
|---|---:|---:|---:|---:|---|
| track (monthly, frozen) | 0.223 | 0.112 | 0.181 | 0.122 | −0.101 [−0.134,−0.067] |
| track_stable_codes | 0.222 | 0.114 | 0.183 | 0.124 | −0.098 [−0.132,−0.064] |
| track_no_special | 0.224 | 0.031 | 0.026 | 0.096 | −0.127 [−0.169,−0.088] |
| **track_quarterly** | **0.025** | 0.010 | 0.006 | **0.129** | **+0.104 [+0.068,+0.140]** |

**Outcomes against the pre-declared predictions.**

1. **Density (B-034) — the prediction that the ranking would be unchanged is REFUTED.** Quarterly
   aggregation collapses the naive detector (0.223 → 0.025) and lifts the Bayes factor (0.122 →
   0.129), so the Bayes factor becomes the best detector with a paired advantage that excludes zero
   (+0.104 [+0.068, +0.140]). **Cycle 3's headline — "the simple baseline is not beaten" — holds
   only at monthly resolution.** The correct statement is that detector ranking is
   **resolution-dependent**: with fewer, denser bins a matched rate-ratio test loses its advantage
   and evidence-accumulating detectors win. This is the outcome D-017 said would force a
   restatement, and it does.
2. **Maintenance filings (B-035) — prediction confirmed.** Removing the 15.01 % Special 510(k)s
   leaves the naive detector best and makes every likelihood detector worse (CUSUM 0.026,
   z-score 0.031). Cycle 3's comparison is not an artefact of maintenance noise.
3. **Taxonomy churn (B-036) — prediction confirmed.** Masking events under codes first seen in
   2022+ (506 codes, 467 events) changes nothing material (naive 0.222, Bayes 0.124). Churn is
   concentrated rather than global, as the design review argued.

**What changes in the published record.** The report's headline is restated as
resolution-conditional; the monthly negative and the quarterly positive are both reported, and
neither is presented as the general answer. The practical recommendation for the OBSERVE layer
follows from the pair of results: **the choice of detector must be made at the resolution the
layer will actually operate at**, and on this lane denser aggregation is both more powerful and
more favourable to evidence accumulation. It also means the thin monthly result cannot be used to
argue that likelihood detection is unnecessary.

**New open question for the next cycle.** Why does aggregation reverse the ranking? The most likely
mechanism is that at monthly resolution a single observation already exceeds a rate threshold
(favouring the rate-ratio test and defeating evidence accumulation), while at quarterly resolution
one bin aggregates several events and the likelihood ratio separates a sustained shift from a burst.
That mechanism is a hypothesis, not a finding, and it is testable by sweeping bin width
(1, 2, 3, 4, 6 months) and checking whether the crossover point moves with the expected count per
bin. Recorded as the next experiment.

---

## D-019 — Independent verification of cycle 3, and a corrected prose claim

**Date:** 2026-11-02. **Status:** accepted. A separate agent that did not write the benchmark
re-implemented injection, scoring, false-alarm accounting, budget selection and the bootstrap from
the artifacts, and audited the report's prose.

**Reproduction: PASS.** 2,844 of 2,844 checks match `benchmark.json` exactly, covering every
frontier point of every detector on the three frozen panels — not only the 2 % read-out. The
verification is under `experiments/detect_v1_verify/` with its own report and script.

**The monthly negative is robust to the injection model.** Under a smooth 12-month ramp, a
6-month transient surge and a bursty 50 %-of-months increase, neither Poisson CUSUM nor the Bayes
factor beats the naive rate-multiplier at the 2 % budget, nor at the benchmark's fixed step-model
operating points, and no likelihood win is interval-confirmed anywhere on the 1/3/5 % frontier.
This closes the strongest objection to cycle 3 raised in the design review: the result is not an
artefact of the step-change injection alone.

**One operational reversal cuts the other way.** When a 6-month surge is read as a *nuisance to be
rejected* rather than a target to be detected, the Bayes factor declares a sustained change on only
0.011 of such surges versus 0.168 for the naive comparator (naive − Bayes factor +0.157
[+0.119, +0.196]). The same numbers are a loss in the detection table and a win in the nuisance
table; which reading applies is an operational decision about which error costs more.

**Prose correction (a real overclaim).** The verifier found that a sentence in an earlier version of
the report — "the naive detector is the strongest at every reported false-alarm budget" — was false:
at a 1 % budget the Bayes factor has a higher point estimate on both the track and domain panels
(0.122 vs 0.098 and 0.129 vs 0.106), and at 3/5 % on the domain panel it is marginally higher. The
2 % headline is unaffected, but the sentence generalised beyond the evidence. It has been replaced
with a budget- and resolution-qualified statement (`REPORT.md` §5), and §5c now reports this
verification in the report itself. Nothing else in the frozen numbers changed.

**The combined position, which is what future work must carry.** The monthly negative is **robust to
the shape of the injected change** but **fragile to the aggregation resolution** (D-018: quarterly
reverses the ranking in favour of the Bayes factor); and the detector choice additionally depends on
whether the operational cost is a missed change or a false "sustained change" alarm. No general
statement such as "the simple baseline is not beaten" or "likelihood detectors are better" survives
without attaching budget, resolution and cost model.

---

## D-020 — Detector memory was in bins, not months: the quarterly winner was confounded

**Date:** 2026-11-02. **Status:** accepted. This corrects the *identity* of the winning detector
in D-018's resolution reversal. The *reversal itself* survives.

**The defect.** The detectors express their memory windows in stream units. With
`baseline_window=24` and `window=12`, a 3-month panel silently gave the CUSUM/Bayes factor a
72-month baseline and the z-score a 36-month window, versus 24 and 12 months on the monthly panel.
At a 6-month width the Bayes/CUSUM baseline (24 bins = 144 months) is longer than the whole panel,
so the detector cannot re-estimate. Comparing detectors across bin widths without fixing this
compares aggregation *and* memory at the same time.

**The fix.** Exposed window parameters are rescaled so their **calendar** length stays at the
monthly defaults: z-score window 12 months, CUSUM/Bayes baseline 24 months
(`make_detector(..., bin_months)`). The naive comparator exposes no window parameter, so its
internal trailing-window and minimum-event guards cannot be rescaled; this is recorded as a
limitation, and it is precisely why the naive detector's collapse at coarse widths remains partly a
property of its fixed guards rather than of aggregation as such.

**What changes (disclosed, not silent).** `check_frozen_reproduction.py` now separates the two
classes of panel: the three monthly panels are **identical** to the committed values (PASS), while
the quarterly panel is reported as changed:

| quarterly read-out (2 % budget) | before memory fix | after memory fix |
|---|---:|---:|
| naive rate multiplier | 0.025 | 0.025 |
| rolling z-score | 0.010 | **0.147** |
| Poisson CUSUM | 0.006 | 0.065 |
| Poisson Bayes factor | 0.129 | 0.073 |

So at quarterly resolution the naive detector still collapses and **all three** likelihood detectors
now beat it (z +0.122 [+0.080,+0.164], Bayes +0.048 [+0.019,+0.075], CUSUM +0.040 [+0.005,+0.080]),
but the **winner is the rolling z-score, not the Bayes factor**. D-018 named the wrong winner: its
"Bayes factor beats naive by +0.104" was partly a 72-month-baseline advantage.

**Bin-width sweep (B-038), with memory fixed.** Across 1, 2, 3, 4 and 6 month bins the best detector
is: naive at 1 m, CUSUM at 2 m, z-score at 3 m, CUSUM at 4 m, z-score at 6 m. The naive detector's
advantage exists only at the finest resolution and collapses immediately (0.223 at 1 m → 0.007 at
2 m). **No single detector is best across widths** — the ranking is unstable, so at this sample size
"which detector is best" is not identifiable; what *is* identifiable is that the naive rate-ratio
test is uniquely fragile once aggregation changes, and that it must not be deployed across
resolutions without re-calibration.

**Honest summary of the three rounds of this question.** Monthly: naive best, robust to injection
shape (independent verification). Quarterly: naive collapses, a likelihood detector wins, but which
one depends on how memory is parameterised. Across widths: the winner is unstable. No general "best
detector" claim survives; the defensible claims are (a) the rate-ratio test is resolution-fragile,
(b) no likelihood detector is reliably better at monthly resolution, and (c) detector choice must be
fixed at the deployment resolution with the memory parameterised in calendar time.

---

## D-021 — B-033 is blocked by measurement, not by effort; and no month-level co-movement survives a correct null

**Date:** 2026-11-02. **Status:** accepted. Two results, both negative and both informative.

### B-033: the independent confirmation source does not exist in the shipped spine — measured

The backlog had B-033 as "blocked, assumed": there seemed to be no second source to confirm that a
detected change is real. That is now **measured**, not assumed
(`experiments/detect_v1/probe_trials_source.py`):

* The legacy full-history DB does contain a ClinicalTrials.gov lane of 55,592 trial events
  (1999-2026), i.e. a genuinely different registry from FDA filings.
* But its tracks are **drug** tracks (`t_oncology`, `t_cardiometabolic`, … — 22 of them), while
  the detection panel is device tracks (`cardiac_rhythm`, `imaging_mr_ct`, …). The two taxonomies
  are disjoint.
* Consequence for matching: **0 of 104 detection cells** have a single trial event; only 12 of 94
  detection entities appear in the trial lane at all (as pharma sponsors, not device filers).
* The other candidate sources are no better for this purpose: publications are annual and cover 51
  curated companies (not the entity cohort); procurement rows are undated with `pit_usable=0` in
  all 3,453 rows; the PMA/510(k) split is the same filing system.

So the "is the detected change real?" question **cannot be answered with the current data spine**,
and the reason is track-taxonomy disjointness, not a missing file. The concrete path forward is
recorded as B-040: collect ClinicalTrials.gov **device** trials with device-track mapping (the
device-intervention filter already exists in `medradar/clinical.py` from the earlier frontier work),
which would give a genuinely independent, track-matched signal.

### B-025: no cross-firm synchronisation survives a correct null

Mission question 4 ("are several competitors moving into the same technology at once?") was tested
with a presence panel (entity × track × month) and a co-activity statistic
(`sum_m C(active firms, 2)`), against a permutation null that preserves each firm's activity level
and draws active months with probability proportional to a monthly volume profile.

**The volume profile used determines the answer, and the first choice was wrong.**

| null conditions on | tracks with excess co-movement (BH q=0.10) |
|---|---|
| lane-wide monthly volume | 3 of 32 (`medical_ai` z=+5.47, `spine` z=+3.50, `ivd_molecular` z=+3.27) |
| **the track's own monthly volume** | **0 of 32** |

The three "synchronised" tracks are precisely the tracks that grew most over the decade: a growing
track admits firms over time, which manufactures co-occurrence. Once a track's own growth and
seasonality are absorbed, there is **no measurable month-level synchronisation** in this lane
(strongest positive z = +1.21, for a 3-entity track). Firm-level activity and track-level growth are
the two phenomena the data contain; their interaction is not one of them.

Limitation, stated: most tracks sit *below* the track-volume null (down to z ≈ −3.9), because the
null draws firm-months independently while real firms file in contiguous bursts. The test is
therefore conservative in the positive direction — which strengthens the null finding — but its
negative direction must **not** be read as anti-synchronisation.

**What this changes.** The Observe layer's industry claim cannot be "the industry moved into X".
At this granularity and with this lane, the defensible output is per-firm change plus track-level
growth, and any cross-firm statement needs either denser data (device trials, patents, hiring) or a
different unit of analysis (e.g. entry cohorts rather than month co-activity).

---

## D-022 — B-040 device-trial lane collected; lag analysis pre-declared before any association is computed

**Date:** 2026-11-02. **Status:** accepted.

Cycle 4 established that the shipped spine has no source able to confirm a detected regulatory
change, because the only other registry in it (ClinicalTrials.gov) was mapped to *drug* tracks
disjoint from the device tracks (0 of 104 cells matchable). B-040 closes that gap by **collection**,
not by re-description.

**What was collected.** `experiments/b040/collect_device_trials.py` invokes the repository's
existing, audited device-trial collector against ClinicalTrials.gov API v2 into a **new, disposable**
database (`data/b040_device_trials.sqlite`); the frozen research lane is never touched.

* 82 sponsor terms planned from the curated 51-company device watchlist; 107 requests used
  (bounded by the collector's own 3-page/term and 360-request caps); 0 errors.
* 4,130 studies returned → 2,663 interventional studies inside the window → **2,663 trial events**
  stored, 2016-09-07 … 2026-10-29.
* 1,472 (55 %) attributable to a curated device company by sponsor resolution; 1,278 (48 %) mapped
  to a **device** track; 1,181 are device-intervention studies with a device track; 43 distinct
  device tracks covered.
* Knowledge time = study first-posted date; per-study match evidence (confidence, alias,
  device-intervention flag) stored in the payload.

**Honest limitations of the lane.** Sponsor resolution covers 55 % of returned studies (the rest are
academic centres, subsidiaries without a curated alias, or other firms). Track mapping is
keyword-based on device intervention text (48 % coverage) and is therefore noisy in the same way the
regulatory lane's 6 % fallback is noisy. The 3-page/term cap truncates very large sponsors, so the
lane is a sample, not a census. All of this must be carried into any claim.

**The analysis, pre-declared before computing any association.** With two independent monthly lanes
(regulatory clearances and device trials) mapped to the same (company, device track) cells, the
question is mission question 3 — **the time relation between public signals** — asked for the first
time with a genuinely independent pair:

1. Cell set: (curated company, device track) pairs with at least 6 regulatory events and at least 3
   trial events over the 119-month window (floors fixed now, before seeing any correlation).
2. Statistic: cross-correlation of the two monthly count series at lags −6 … +12 months, where a
   positive lag means **regulatory activity leads trial activity**.
3. Inference: pool per-cell correlations by Fisher z, with an entity-cluster bootstrap over cells;
   null distribution from circularly shifting each cell's trial series (preserves each series' own
   autocorrelation and volume profile, destroys cross-series alignment).
4. Reporting: the lag profile with intervals, the cell count, and an explicit statement of whether
   the design has power to detect a correlation of the size the literature would suggest; if it does
   not, that is the result.

**Predictions, stated so the outcome can count against them.** A positive association at lag 0–6
(regulatory clearances accompanying or slightly trailing trial activity, since trials usually start
before a device is cleared) is the most plausible shape. A flat lag profile would mean the two
lanes carry unrelated information about a cell — which would weaken any "evidence fusion" claim.
Either outcome is reportable.

---

## D-023 — B-040 outcome: an independent device-trial lane now exists, and it shows no association with clearances

**Date:** 2026-11-02. **Status:** accepted. Closes B-033 and B-040.

**The gap is closed.** Cycle 4 measured that no source in the spine could confirm a detected
regulatory change, because the only other registry present was mapped to drug tracks (0 of 104 cells
matchable). B-040 collected **ClinicalTrials.gov device trials into a new, disposable database**
using the repository's audited collector: 2,663 trial events (2016-09 … 2026-10) from 4,130 returned
studies, 46 companies, **43 device tracks**, 55 % attributable to a curated company, 48 % mapped to a
device track, 107 requests, 0 errors (`experiments/b040/collection_manifest.json`).

**The pre-declared test (D-022) returns a null.** Cells carrying both lanes: 26; passing the
pre-registered activity floors: **16**. The cross-correlation profile from −6 to +12 months lies
inside the circular-shift null interval at every lag; the largest observed value is r = 0.036 at lag
+7 (null band [−0.046, +0.048]). There is no detectable aligned time structure, in either direction,
at this granularity.

**Licensed.** Any claim that device-trial activity and regulatory clearance activity "confirm one
another" at the cell level is unsupported by this test — including the evidence-fusion premise that
motivated collecting the lane. The premise must now be argued from a different design, not asserted.

**Not licensed.** This is not evidence that trials and clearances are unrelated. Three limits
dominate and are stated in `experiments/b040/REPORT.md`: coverage (55 %/48 %), sparsity (floors of 3
and 6 events over 119 months mean the series are mostly zero), and granularity (trials attach to a
company, not to a legal sub-entity, so a multi-subsidiary firm is pooled while its clearances sit in
separate entities).

**What would move this forward** — and what would not. More lag-window variants on the same 16 cells
would not; the limit is signal density. The two declared data gaps (hiring, patents) and a different
unit of analysis (company-entry cohorts rather than cell-month counts) are the only routes that
address the cause.

**Consequence for the mission.** Mission question 3 ("what are the time relations between public
signals?") now has one honest, re-runnable answer at device-track granularity: **none detectable**
between the two independent lanes. That is a finding about this data, not about the industry, and it
is the third consecutive cycle in which a tempting positive dissolved under a better design.

---

## D-024 — Entry-cohort unit of analysis: design fixed before the run, outcome recorded after

**Date:** 2026-11-02. **Status:** accepted. Closes B-042.

**Sequencing, stated explicitly.** The design was written into `experiments/detect_v1/entries.py`'s
module docstring and its constants **before** the script was first executed (the commit history shows
script and results together, but the docstring is the pre-declaration). The outcome is recorded here
afterwards. There was no tuning against results: the constants (36-month dormancy, 24-month minimum
observation, 2000 permutations, seed 7, BH q = 0.10, minimum 3 entries per unit) were never changed
after the first run.

**Why a new unit.** Every previous cycle hit the same wall: at (entity, track, month) granularity the
lane holds ~0.2 events/month, so cell-level statistics are starved and all four earlier tests were
underpowered or null. The event that actually matters for the mission — *a company entering a
technology track it has not been active in* — is far denser (4,814 events) and is the right unit for
"are competitors moving into a technology together?"

**Design.** Entry = a cell's first observed event, at least 24 months into the window. Risk set at
month m = firms already observable (any prior event) that have not yet touched the track. Null: the
unit's entries are distributed over months with probability proportional to its at-risk count, which
conditions out lane growth and risk-set shrinkage — the two confounds that invalidated the naive
co-movement test in D-021. Statistic: dispersion index (variance/mean) of monthly entry counts. Both
tests are run per track (industry clustering) and per firm (strategic-redirection bursts).

**Outcome.**

| run | entries | tracks rejected (BH q=0.10) | firms rejected |
|---|---:|---|---|
| all events | 4,814 | 0 of 38 (smallest p = 0.0040, `medical_ai`) | 0 of 60 |
| **taxonomy-churn controlled** | 4,590 | **1 of 36: `ivd_immuno`** (p = 0.0010, z = 4.73) | 0 of 60 |

1. **The density ceiling is lifted.** 4,814 entry events versus roughly 0.2 events per cell-month:
   the cohort unit makes the industry question testable at all.
2. **One technology track shows FDR-controlled industry entry clustering**, and it is *not* a churn
   artifact: `ivd_immuno` strengthens when the 467 events on 506 late-created product codes are
   removed (p 0.0055 → 0.0010), which is the opposite of what churn would do. `medical_ai`'s apparent
   clustering weakens under the same filter (p 0.0040 → 0.0365 and no longer FDR-significant), i.e.
   part of the "AI wave" in entry counts was new product codes appearing.
3. **No firm shows entry bursts.** 0 of 60 firms reject: strategic redirection, at least as measured
   by simultaneous multi-track entry, is not a detectable pattern in this lane.
4. **The surviving signal is single.** One rejection among 36 tests under 10 % FDR is *suggestive,
   not established*; a lone rejection is compatible with a false discovery. What makes it credible is
   the robustness direction (strengthening under the churn control), not the p-value alone.

**What this licenses.** "At least one device technology area (immunoassay IVD) shows a detectable
industry-wide wave of first entries across firms, after controlling for risk-set size and product-code
churn" — a narrow, falsifiable, re-runnable claim, and the first positive empirical finding of the
programme that survived its own controls.

**What it does not license.** That the wave is technology-driven rather than, for example, a
procurement/regulatory-classification effect; that entry timing is predictable; or that any firm
deliberately synchronised. Those are Understand-layer questions.

**Next step this opens.** A focused case study of `ivd_immuno` entry waves (2019 and 2023-24), asking
which firms entered, with what evidence, and whether the wave is visible in the independent
device-trial lane collected in B-040 — the first test with a *positive* target rather than a null.

---

## D-025 — Retraction: the cycle-6 "ivd_immuno entry wave" was an entity-appearance artifact, and no track has a specification-stable wave

**Date:** 2026-11-02. **Status:** accepted. This **retracts** the positive finding recorded in D-024
and replaces it with a negative result plus a measurement lesson.

**What was wrong.** Cycle 6's entry list scored a cell's first observed event as a technology entry
regardless of whether the firm was already an observable filer. But the risk set (and therefore the
null) already required observability, so the numerator and the denominator disagreed: an entry could
be counted for an entity that was not at risk. In practice **3,804 of 4,814 entries (79 %) were
first-ever appearances of a legal entity in the lane** — new small firms registering, or newly
resolvable applicant strings — not established firms entering a new technology area.

**The control.** `--require-prior-filer` counts an entry only when the entity had some event in
another track before the entry month. This restores numerator/denominator consistency and separates
*firm-level technology entry* from *entity appearance*.

**What happens to the finding.**

| track | all events | churn controlled | prior-filer | prior-filer + churn |
|---|---|---|---|---|
| `ivd_immuno` | n=49, p=0.0055 | n=40, **p=0.0010** | n=8, **p=1.0000** | n=5, p=1.0 |
| `ivd_molecular` | n=68, p=0.69 | n=61, p=0.56 | n=5, **p=0.0025** | n=5, p=0.0005 |
| `aesthetics` | n=197, p=0.015 | n=195, p=0.0070 | n=27, p=0.0135 | n=27, p=0.0085 |
| `medical_ai` | n=464, p=0.0040 | n=418, p=0.0365 | n=144, p=0.0525 | n=135, p=0.0815 |
| `cardiac_rhythm` | n=21, p=0.0155 | n=18, p=0.0275 | n=3, p=0.0275 | n=3, p=0.0235 |

1. **`ivd_immuno` collapses to nothing** (40 → 8 entries, p = 1.0). The "wave" was new entities
   appearing in the track, not incumbents entering. **The cycle-6 positive finding is retracted.**
2. **The surviving track changes identity with the specification** (`ivd_immuno` → `ivd_molecular`),
   and `ivd_molecular`'s rejection rests on **five** entries (p = 0.0025, down from p = 0.69 with 68
   entries). A finding that appears only in one specification and on five events is specification
   noise, not an industry wave.
3. **`aesthetics` is the only track with a consistently small nominal p** across all four
   specifications (0.0070–0.0150, n = 27–197), and it **fails** FDR control in every one. It is a
   candidate, not a finding.
4. **Firm-level bursts remain null** in every specification (0 of 46–60).

**What replaces the finding.** No device technology track has a **specification-stable** industry
entry wave in this lane. The honest result of B-042/B-043 is negative, and it comes with a
measurement lesson that matters more than the original claim: **most "entry" events in this lane are
first appearances of legal entities, not established firms entering new areas.** Any future entry
study must state which of the two it measures; the two are not interchangeable.

**The one legitimate way forward on `aesthetics`.** Because it was selected after looking at p-values,
testing it on the same window would be circular. The remedy is split-sample pre-registration: choose
the track now (recorded here), estimate on a fixed early window, and test on a held-out later window
without touching the threshold. That is B-046, and it is the only route that could turn this candidate
into evidence.

---

## D-026 — Pre-registered split-sample test of the `aesthetics` candidate (fixed before the run)

**Date:** 2026-11-02. **Status:** accepted; written before `aesthetics_holdout.py` was first
executed. B-046.

`aesthetics` is the only track whose nominal p was small across all four entry specifications
(0.0070–0.0150, n = 27–197), and it failed FDR in every one. Because it was selected by looking at
p-values, re-testing it on the same window would be circular. This fixes the test in advance.

**Hypothesis.** In the curated legal-entity lane, first entries into the `aesthetics` technology
track by firms that were already observable filers are temporally clustered beyond what the
risk-weighted null predicts.

**Statistic.** Dispersion index (variance/mean) of monthly first-entry counts, exactly as in
D-024/D-025. Null: entries distributed over months with probability proportional to the at-risk
count in that month (observable filers that have not yet touched the track).

**Split (fixed now).**
* estimation window: 2016-09 … 2022-12 (the first 76 months of the 119-month window);
* holdout window: 2023-01 … 2026-09 (the remaining 43 months);
* the holdout is never used to choose anything.

**Decision rule (one-sided, α = 0.05), fixed now.**
* **REPLICATED** iff holdout p ≤ 0.05 *and* estimation-window p ≤ 0.20 in the same direction.
* **REJECTED** iff holdout p > 0.05.
* **NOT RESOLVABLE** is allowed *only* if the power simulation below shows < 50 % probability of
  detecting the effect size implied by the estimation window. In that case the candidate is closed
  as unresolvable with this data — **not** as refuted — and must not be reported as a finding either
  way.

**Power, reported with the result.** For the holdout's risk profile and its number of entries, the
script simulates (a) the null distribution of the statistic and (b) waves in which a pre-declared
share of the holdout's entries (30 %, 50 %, 70 %) concentrates inside a random 6-month block, and
reports the detection probability at the same α. This is what distinguishes "no clustering" from
"cannot tell", and it is computed whether or not the replication succeeds.

**What a success would mean.** If REPLICATED, the programme has its first verified empirical finding:
a device technology area in which firms' first entries are temporally clustered beyond risk-set
composition. Even then it would be a statement about *public regulatory entry timing*, not about
technology waves or causal drivers — those remain Understand-layer questions.

---

## D-027 — B-046 outcome: the aesthetics candidate cannot be confirmed, and no track replicates out of sample

**Date:** 2026-11-02. **Status:** accepted. Closes the entry-clustering thread as a null.

D-026 pre-registered a split-sample test of the `aesthetics` candidate. While running it, a
methodological problem in the pre-registration itself became visible and is recorded first, because it
changes the verdict.

### The pre-registration was contaminated (and this is the important part)

`aesthetics` was nominated in cycle 7 **using the full 119-month window**, which includes the months
later declared to be the holdout. A holdout can only confirm a hypothesis that was fixed without it.
Nomination used the holdout data implicitly, so the split-sample p-value is **not confirmatory** no
matter what it says. D-026's decision rule was therefore unable to deliver the confirmatory test it
promised, and the fix had to be a different design, not a different threshold.

**The clean design, run in the same script:** nominate tracks using the **estimation window only**
(2016-11 … 2022-12), all tracks, Benjamini–Hochberg at q = 0.10; then test the nominee(s) on the
untouched holdout (2023-01 … 2026-09) at α = 0.05. Here the holdout p-value *is* a valid confirmatory
test, because the nominee set was fixed without it.

### Results

**Post-hoc candidate (invalid as confirmation, reported for completeness).** Estimation p = 0.0215
(14 entries), holdout p = 0.0360 (13 entries) — it looks like a replication. It is not one: the
candidate was selected using the holdout, and it is **not even nominated** by the clean early-window
design (p = 0.0215 does not survive BH across 30 tracks).

**Clean design (the confirmatory one).**

| nominated track (estimation window) | estimation p | holdout p | confirms |
|---|---:|---:|---|
| `ivd_molecular` | 0.0015 | — (no holdout entries) | no |
| `medical_ai` | 0.0045 | 0.8411 | no |
| `vascular_access` | 0.0070 | 0.0825 | no |

**3 nominated, 0 confirmed.** No device technology track shows entry clustering that replicates out
of sample.

**Power, so the null is not over-read.** With the holdout's 13 entries, the probability of detecting a
wave that concentrates 30 % / 50 % / 70 % of entries in a six-month block is 0.25 / 0.52 / 0.95. So the
holdout can rule out strong clustering and cannot rule out weak clustering. The correct statement is
**"no evidence of replication"**, not "proven absence of clustering".

### What this closes

The B-042/B-043/B-046 thread is closed as a **null**: this lane does not support a claim that any
device technology area shows an industry-wide wave of first entries. The candidates that appeared in
cycles 6 and 7 were, in order, an entity-appearance artifact (D-025) and a post-hoc selection
(D-027), and neither survives a design that controls for its own selection.

### What the programme does next, and why it is not another specification search

Three cycles have now been spent trying to rescue a positive finding from cell- and entry-level
clustering. The recurring failure mode is not the statistic but the **information content of the lane**:
a single regulatory filing stream, at ~0.2 events per cell-month, cannot support claims of this kind.
The next-round priorities therefore move off clustering entirely and onto (a) the two declared data
gaps that would change the information content (hiring B-030, patents B-031), and (b) the Understand
layer deliverable that does not depend on a positive clustering result (company technology profile,
B-027). Continuing to re-specify clustering tests on the same lane would be exactly the "unlimited
trial-and-error by changing the algorithm" that the mission forbids.

---

## D-028 — B-030 hiring panel: lawful source identified, construction and tests pre-declared

**Date:** 2026-11-02. **Status:** accepted. Written while the first panel build was running, before
any association was computed.

**Source selection, measured rather than assumed.** Three candidate lawful routes were probed:

| route | probe result |
|---|---|
| PatentsView bulk (S3) | **403 Forbidden** — requires credentials; patents remain blocked |
| Common Crawl index API | **persistent 504 Gateway Time-out** from this network, even for `example.com` |
| **Wayback Machine CDX API** | **works, keyless**, and job-posting URLs with real slugs are archived (Medtronic: 15 index pages of `jobs.medtronic.com/job/*`) |

The Wayback route is used: public web archive, index only (no page content is fetched), bounded and
rate-limited queries. It satisfies the mission's requirement of a source with **genuine historical
point-in-time availability** — the archive predates our analysis by years, so no part of the signal
is manufactured by our own collection.

**Proxy and its honest meaning.** For each company's career domain, we take each distinct
job-posting URL's **earliest archive capture month** and count new postings per month. This is a
*posting-flow proxy*, not a headcount: it counts postings the archive happened to capture, so it
measures hiring activity up to (a) archive coverage of that site, (b) URL-scheme stability, and
(c) crawl cadence. All three are reported, not assumed away.

**Pre-declared analyses (in this order).**
1. **Coverage and validity.** Which companies yield ≥20 distinct postings; months with data; and a
   platform-change check — a step change in the monthly series that coincides with a URL-scheme
   change is a collection artifact, not a hiring change.
2. **Association with regulatory activity**, company level (hiring domains identify companies, not
   legal sub-entities). Lags −6 … +12 months, positive lag = hiring leads regulatory activity.
   Statistic and inference as in D-022: pooled lag profile, null from circular shifts of the hiring
   series, and the same power caveat.
3. **Prediction, stated so it can fail:** if hiring reflects R&D team expansion before filings, the
   profile should peak at positive lags (hiring leading by roughly 3–12 months). A flat profile means
   the two lanes carry unrelated information at company level; a peak at negative lags would suggest
   the proxy is capturing backfill after approvals, which is a different (and weaker) claim.

**What this cannot support even if positive.** Hiring intensity is not R&D spending, not technical
team composition, and not evidence of intent; and the proxy's coverage is a sample of captured
postings. Any claim is about *posted hiring activity as archived*, nothing more.

---

## D-029 — B-030 outcome: a lawful historical hiring signal exists, but coverage is too thin to test the lag question

**Date:** 2026-11-02. **Status:** accepted. Closes B-030 as a **feasibility partial**, not a result.

**What was achieved.** Three lawful routes were probed and two were closed on access grounds:
PatentsView bulk returns **403** (credentials required) and the Common Crawl index returns **persistent
504s**. The **Wayback Machine CDX API works keyless** and archives real job-posting URLs — Medtronic's
`jobs.medtronic.com/job/*` alone spans 15 index pages with postings back to 2010. A bounded,
rate-limited collector now builds a monthly posting-flow panel, committed as
`experiments/b030/hiring_panel.json` with full provenance. This is the first time the programme has a
genuinely historical, independent hiring signal in hand rather than a declared gap.

**What the coverage actually is.** 16 device firms probed: 6 yielded posting URLs, and **only 2 pass
the pre-declared usability floor** (≥50 postings, ≥24 months with postings, ≤50 % silent months):
`bd` (2,408 postings, 60 months) and `boston_scientific` (2,065, 88 months). Eight firms have no
archived postings under the probed hosts at all.

**Why the lag profile is not a finding.** The pre-registered lag test (D-028) was run and its output
is committed, but it rests on **two** companies, so the pooled profile is close to an average of two
correlations with no usable standard error. Its values are uniformly negative, and that sign is **not
interpretable**: the proxy counts only postings the archive happened to capture, so capture gaps and
regulatory gaps can align for reasons unrelated to hiring. Reported as an unrun question with its
machinery built, not as a null result about hiring.

**What was deliberately NOT done.** The usability floor admits 2 companies and I did **not** loosen it
to increase the sample. Adjusting eligibility after seeing that it excludes most of the data is the
same specification search that D-027 closed for the entry thread; it would produce a number that looks
like a result and is not one.

**What would actually unblock it** (recorded as B-047):
1. **Per-company career-domain mapping** — several focus companies returned nothing because their
   career sites live on hosts the patterns did not guess (Philips, GE HealthCare, Dräger, Mindray,
   Abbott, Zimmer Biomet, Masimo, Hologic). This is a discovery problem, not a statistical one.
2. **Platform-change audit** — career sites migrate between posting-URL schemes; a migration creates a
   level shift that is a collection artifact and must be detected per company before any level-shift
   claim.
3. **Archive-depth handling** — CDX deep paging did not yield Medtronic's full 15 pages under the
   current parameterisation, so its series stays shallow; this is an implementation defect to fix, not
   a property of the source.

**Honest position.** The hiring lane exists, is lawful, is historical, and is currently too thin for
the company-level lag question it was collected for. B-030 therefore moves to `blocked` with a measured
reason and a concrete unblock path, in the same way B-033 did before B-040 resolved it by collection.

---

## D-030 — Correction: cycle 9's "coverage too thin" was partly a collector bug; coverage is 6 firms, and the lag test is still unrun

**Date:** 2026-11-02. **Status:** accepted. **Corrects** the coverage conclusion of D-029.

### The defect

Cycle 9's panel builder combined `collapse=urlkey` with `limit` + `page` pagination. On this CDX
endpoint that combination **does not page** — every query silently returned one capped page — so the
collector saw a fraction of the archive and I concluded that archive depth was the binding
constraint. That conclusion was an artefact of my own code, not a property of the source.

A direct measurement with a single generous request per host (`measure_host_depth.py`) shows the same
hosts hold far more:

| host | posting URLs | months | months with ≥5 postings |
|---|---:|---:|---:|
| `jobs.bostonscientific.com/job/*` | 4,999 | 123 | 100 |
| `jobs.medtronic.com/job/*` | 4,984 | 46 | 29 |
| `jobs.bd.com/job/*` | 4,672 | 66 | 44 |
| `careers.stryker.com/*` | 3,878 | 39 | 28 |
| `abbott.taleo.net/careersection/*` | 579 | 34 | 15 |
| `careers.intuitive.com/job/*` | 532 | 18 | 8 |
| `dexcom.wd1.myworkdayjobs.com/*` | 767 | 31 | 16 |

### Corrected coverage

The rebuilt panel (`hiring_panel_v2.py`, single request per host, truncation recorded rather than
hidden) covers **11 companies with posting URLs**, 6 with ≥24 months and 9 with ≥50 postings — against
2 usable companies in cycle 9. Medtronic, BD, Boston Scientific and Stryker each hit the per-host cap,
so their series are lower bounds.

### The lag test is still not a result

Under the **unchanged** pre-declared floor, **3 companies** are usable (`bd`, `boston_scientific`,
`stryker`). The pre-registered lag profile is committed (`lag_analysis_v2.json`); every value sits
inside its null band and the uniformly negative sign is uninterpretable because the proxy counts only
archive-captured postings, so capture gaps can align with regulatory gaps. This remains an **unrun
question with working machinery** — not a null result about hiring.

### What this changes, and what it does not

* **Changes:** the blocker is no longer "archive depth". It is **statistical power** (3 companies) plus
  **five firms with no discovered board** (Philips, Dräger, Mindray, Zimmer Biomet, Masimo — two of
  the five mandated focus companies among them).
* **Does not change:** the source remains lawful, keyless and genuinely historical; the association
  question remains open; and the discipline of not loosening the usability floor after seeing the
  coverage stands (the floor was applied unchanged to the corrected panel).

### Lesson recorded for the programme

A negative conclusion about data availability is as falsifiable as a positive scientific claim, and
the same discipline applies: when a measurement says "the data is too thin", the measurement itself
must be checked before the conclusion is carried forward. This is the second time this cycle family
has had to retract its own result (D-025 was the first), and both times the retraction came from
testing the claim against an alternative explanation rather than from new data.

---

## D-031 — B-048 outcome: one more board found, but the hiring lane cannot cover four of the five mandated focus companies

**Date:** 2026-11-02. **Status:** accepted. Closes B-048 as a **measured coverage limit**.

**What was searched, and how.** Instead of guessing hosts again, the archive was asked what it has:
for each firm, a CDX query over the main domain filtered to career/job URLs, followed by an ATS-host
battery of ~40 candidate patterns per company (Workday pods, Taleo, SuccessFactors, Avature, iCIMS,
Jobvite, Greenhouse, Lever, SmartRecruiters, Eightfold, plus own-domain career paths).

**Results.**

| firm | discovered board | postings | months | clears the unchanged floor? |
|---|---|---:|---:|---|
| Philips | `philips.taleo.net/careersection/*` | 669 | 38 | **no** — silent-month fraction too high |
| Zimmer Biomet | `careers.zimmer.com/*` | 4 | 4 | no — far too thin |
| Dräger | none (only `www.draeger.com/...career` marketing pages; `draeger.taleo.net` errored) | 0 | 0 | no |
| Mindray | none (only `mindray.com/...careers` marketing pages) | 0 | 0 | no |
| Masimo | none | 0 | 0 | no |

**The structural finding.** MISSION.md mandates five deep-case companies: Medtronic, GE HealthCare,
Philips, Dräger, Mindray. Under the **unchanged** usability floor the hiring lane covers **one** of
them (Medtronic). The reasons differ and are not fixable by more probing:

* **GE HealthCare** only became an independent filer in 2023, so a hiring series that predates its
  independence does not exist; and its archived board yields one URL.
* **Philips** has a real board but covers 38 of 119 months — its postings are not archived densely
  enough for a monthly series that passes the silence criterion.
* **Dräger and Mindray** post on career systems whose job-level URLs are not archived; only marketing
  pages were captured.
* **Masimo** returned nothing at all.

**What this means for the mission.** The hiring lane can serve the *statistical* question for a subset
of the roster, but it can **not** serve the mandated deep-case requirement. Those five cases need an
evidence type that exists for them: their own regulatory filings (already held), their device trials
(held for 46 firms), and their publications. This is now a recorded constraint on the design, not an
outstanding search.

**Deliberately not done.** The floor was not loosened to admit Philips, and the silence criterion was
not relaxed to manufacture a fourth usable company. Same rule as D-029/D-030.

**Consequence for the lag test.** It remains **unrun** with 3 usable companies, unchanged from
D-030. Probing stopped here because the marginal firm is not obtainable from this source; continuing
would be the specification search the mission forbids.

---

## D-032 — Understand layer: company technology profiles with mandatory contradictory evidence

**Date:** 2026-11-02. **Status:** accepted. Closes B-027.

**What this is.** `medradar/intelligence/profile.py` turns the evidence the programme already holds —
regulatory filings with tracks and product codes, device trials — into a company technology profile.
It is **pure computation** (plain event dictionaries in, plain dict out); database access lives in
`experiments/b027/build_profiles.py`, so the logic is unit-tested (34 tests) and the output is
reproducible.

**The seven required fields** (this is the contract, and `validate_profile` enforces it):

1. `identity` — company, resolved legal entities, aliases, as-of date, coverage window, sources
2. `technology_footprint` — per-track event counts, first/last dates, shares, sufficiency
3. `momentum` — last 24 months vs the 24 before, with direction and the numbers behind it
4. `concentration` — top-track share and HHI over tracks
5. `independent_corroboration` — per-track device-trial support, and explicitly which tracks have none
6. `contradictory_evidence` — **the checks that were run and what they found against the reading**
7. `limits_and_provenance` — sources, window, and what would change the conclusion

**Three design rules, and why.**

* **No scores.** A single number would hide the evidence and invite use as a ranking. Every statement
  is generated from the numbers in the same structure, so prose cannot drift from evidence.
* **Contradictory evidence is structural, not optional.** Field 6 must list the checks that were run
  and the findings (possibly none). A profile that does not say what was looked for and not found is
  rejected by `validate_profile`, and `render_markdown` refuses to render it. The programme's repeated
  failure mode has been a positive reading surviving because nobody looked for its contradiction;
  this makes that omission a schema error.
* **Degrade honestly.** A company with no trial support, no hiring board, or sparse months says so in
  the profile rather than being dropped or scoring zero.

**What a profile licenses.** Statements of the form "in the public regulatory lane this company shows
X events across Y tracks, momentum Z, with these specific contrary observations and these coverage
limits". Nothing about intent, capability, internal R&D, or future direction.

**What was generated.** Profiles for all five MANDATED deep-case companies (Medtronic, GE HealthCare,
Philips, Dräger, Mindray), including the two that are not in the device roster (resolved through the
universe module's focus list rather than being silently dropped). Medtronic: 299 events / 24 tracks,
momentum rising (90 vs 66), 14 of 24 tracks with trial support, two declining tracks flagged. GE
HealthCare: 274 events / 5 tracks, no contradiction found across the four checks. Dräger: 16 events /
2 tracks — thin, and the profile says so.

**Verification.** `experiments/b027/selfcheck.py` re-derives every number the Markdown states from the
JSON (footprint rows, totals, contradiction count, entity count), checks all seven headings, and
confirms rendering is deterministic: 5 of 5 profiles pass.

---

## D-033 — Momentum is now a calibrated test, and three of the five cycle-12 momentum readings did not survive it

**Date:** 2026-11-02. **Status:** accepted. **Supersedes** the momentum statements of D-032.

### The defect

Cycle 12's profile computed momentum as a rate ratio between the last 24 months and the 24 before,
and called a ratio ≥ 1.25 "rising". That is the same mistake the programme has paid for repeatedly in
the laboratory: a ratio is not evidence. With counts in the tens, a ratio of 1.36 is entirely
compatible with a constant rate.

### The fix

`momentum` is now a **two-sided exact binomial test** of the recent count conditional on the total
(equivalently the Poisson rate-ratio test under a constant-rate null), at α = 0.05. Three outcomes:

* `increasing` / `decreasing` only when p < 0.05;
* otherwise `no_detectable_change`, and the field must then report the **minimum detectable ratio at
  80 % power** implied by the observed counts (`mde_ratio`), so a null is never read as "no change".

The rendered profile prints the p-value, α, the MDE and the `detected` flag, and `selfcheck.py`
re-derives them from the JSON.

### What happened to the cycle-12 readings

| company | last 24 m | prior 24 m | ratio | exact p | MDE (80 %) | verdict |
|---|---:|---:|---:|---:|---:|---|
| Medtronic | 90 | 66 | 1.36 | 0.065 | 1.57× | **no detectable change** (was "rising") |
| GE HealthCare | 57 | 48 | 1.19 | 0.435 | 1.73× | no detectable change (was "stable") |
| Philips | 73 | 36 | 2.03 | **0.001** | 1.77× | **increasing** (survives) |
| Mindray | 18 | 12 | 1.50 | 0.362 | 2.84× | **no detectable change** (was "rising") |
| Dräger | 10 | 10 | 1.00 | 1.000 | 3.50× | no detectable change (was "stable") |

**Three of five cycle-12 momentum readings were noise.** Medtronic's +36 % and Mindray's +50 % are
comfortably inside what a constant rate produces at these counts, and only Philips' doubling clears
the test.

This is the fourth time a tempting positive has dissolved under a better null — and the first time it
dissolved **inside the product**, automatically, because the design forced the contradiction check to
exist. That is the intended behaviour of D-032's third rule: the profile is not allowed to state a
direction without the test that supports it.

### Not claimed

A non-detection is not evidence of stability. The MDE column says exactly how large a change this
data could have seen: Medtronic's data would have needed a 57 % increase to be detectable, so a 20 %
real increase is fully compatible with the data and simply invisible. "No detectable change" with a
stated MDE is the honest sentence; "stable" is not.

---

## D-034 — B-049: full-roster profiles and a hash-verified frozen snapshot; a ratio rule would have made 31 unsupported claims

**Date:** 2026-11-03. **Status:** accepted. Closes B-049.

**What was built.**

1. **Full-roster profiles.** The engine now runs over every curated company: **53 profiles** (the
   51-company device roster plus the two mandated focus firms that are not in it, Dräger and Mindray),
   generated by `build_profiles.py --scope roster`.
2. **A frozen, verifiable snapshot** at `experiments/b027/snapshots/2026-11-02/`, written by
   `freeze_snapshot.py`: the profile payload, the summary, one Markdown file per company, and a
   `manifest.json` that records a **SHA-256 per artifact**, a **SHA-256 per input source** (lane DB,
   trial DB, three configs), the as-of date, the evidence window and a manifest hash over all of it.
   The script re-reads everything from disk and verifies before reporting success, so a snapshot that
   does not verify is never left behind silently.
3. **Verification in the self-check.** `selfcheck.py` now also verifies every snapshot: manifest
   hashes, summary/profile agreement, frozen Markdown reproducing exactly from the JSON, and as-of
   consistency with the directory name.

**The calibration result, measured across all 53 companies.**

A naive rule of the kind used in cycle 12 (flag when the recent/prior rate ratio is ≥ 1.25 or ≤ 0.80)
would have flagged **35 of 53 companies**. The exact binomial test at α = 0.05 supports **4**:

| company | last 24 m | prior 24 m | ratio | p | MDE |
|---|---:|---:|---:|---:|---:|
| Olympus | 50 | 12 | 4.17 | <0.0001 | 2.46× |
| Philips | 73 | 36 | 2.03 | 0.0005 | 1.77× |
| Steris | 18 | 36 | 0.50 | 0.020 | 2.25× |
| Medline | 11 | 25 | 0.44 | 0.029 | 2.76× |

**31 of the 35 naive flags are unsupported.** The largest casualties show why: iRhythm at ratio 4.00
is 4 events against 1 (p = 0.375, MDE 22.93×), ICU Medical at ratio 2.25 is 9 against 4 (p = 0.267,
MDE 5.38×). The naive rule would have written "momentum's rising" for firms where the data cannot
distinguish anything from noise.

**What this licenses.** For each company: a statement of whether its public filing activity changed
over the last 24 months relative to the 24 before, at a stated α, with the minimum detectable ratio
when it did not change. Nothing about intent, capability, internal R&D, or the future.

**What it does not license.** Comparison of detected counts as a ranking of "innovation": the MDEs
differ by company (from 1.77× to 22.93×), so a non-detection for a low-count firm and a non-detection
for a high-count firm mean very different things. The per-profile MDE is what keeps that honest.

**Why the snapshot matters for the objective.** A point-in-time artifact is the precondition for any
rolling-origin evaluation: without a frozen record of what the system believed on a given date, later
"predictions" cannot be audited for look-ahead. The snapshot is dated, source-hashed and
self-verifying, so a future cycle can prove what this one knew.

---

## D-035 — Pre-registration: rolling-origin benchmark of the change signal (fixed before the run)

**Date:** 2026-11-03. **Status:** accepted; written before `experiments/b050/rolling_origin.py` was
first executed. Creates B-050.

The mission objective names **rolling-origin benchmarks** and the programme has none. This fixes the
design of the first one before any outcome is computed.

**Question.** Does a calibrated change signal at time *t* say anything about activity in *t+1 … t+12*?
Concretely: are cells flagged as increasing more likely to keep increasing than cells that are not
flagged, and is a calibrated flag better than a raw ratio rule?

**Unit.** (curated company, technology track) cell over the 119-month lane.

**Origins.** Every six months from 2019-12 to 2025-06 (12 origins). At each origin *t*, only events
with month ≤ *t* are used. Nothing after *t* enters the signal.

**Eligibility, fixed now.** At least 8 events in the cell's history up to *t*, and at least 3 events in
the prior 12-month block (i-23 … i-12) — without a prior block the comparison is undefined.

**Signal.** Two-sided exact binomial test comparing the recent 12-month block (i-11 … i) with the prior
block, at α = 0.05. `flag_increase` when p < 0.05 and recent > prior; `flag_decrease` when p < 0.05 and
recent < prior.

**Outcome, fixed now.** `future_increase` = the 12 months after the origin (i+1 … i+12) contain more
events than the recent block; `future_decrease` = fewer.

**Estimands.**
1. **Precision**: P(future_increase | flag_increase) versus P(future_increase | not flagged). Lift is
   the ratio of the two. The same for decreases.
2. **Head-to-head**: the same estimate for a raw ratio rule (flag when recent/prior ≥ 1.25) and for a
   persistence rule (predict increase whenever recent > prior, no test) computed on the *same* cells
   and origins.

**Inference.** Company-clustered bootstrap (resample companies with replacement, 2000 replications,
seed 7), reporting 95 % intervals for precision and lift. Cells from one company are not independent,
which is why the bootstrap resamples companies rather than cells.

**Pre-declared expectation and its failure mode.** If the signal carries information, flagged cells
should show a higher `future_increase` rate than unflagged cells, and the calibrated rule should beat
the raw ratio rule because the latter flags 8× more cells (measured in D-034: 35 versus 4 of 53).
**A null is an acceptable and expected outcome**, and it must be reported with the sample size and the
minimum detectable difference in precision, not as "no prediction is possible".

**What even a positive would mean.** Only that public regulatory activity tends to persist in the
direction a calibrated test detected — a statement about the time series, not about technology,
capability, or intent.

---

## D-036 — B-050 outcome: the first rolling-origin benchmark, its pre-registered design bias, and an honest null

**Date:** 2026-11-03. **Status:** accepted. Closes B-050.

**What ran.** The pre-registered benchmark (D-035): 376 (company, track) cells, 12 origins every six
months from 2019-12 to 2025-06, **717 company-origin-cell observations**. At each origin the signal
uses only events up to that month; the outcome is the following 12 months. Company-clustered bootstrap,
2000 replications.

**The pre-registered result, and why it cannot be read at face value.**

| predictor (pre-registered) | flags | P(outcome\|flag) | P(outcome\|no flag) | lift | 95 % CI |
|---|---:|---:|---:|---:|---|
| calibrated increase | 5 | 0.00 | 0.41 | 0.00 | [0.00, 0.00] |
| naive increase (ratio ≥ 1.25) | 149 | 0.22 | 0.46 | 0.49 | [0.32, 0.66] |
| persistence increase (no test) | 173 | 0.21 | 0.47 | 0.46 | [0.31, 0.61] |
| naive decrease | 434 | 0.32 | 0.63 | 0.50 | [0.40, 0.61] |

Read naively, that says extrapolation is *anti*-predictive with tight intervals. **That reading is
wrong, and the design is why.** The outcome asks whether the future block beats the *recent* block, and
a cell is flagged precisely because its recent block is high. At a constant rate the next block is then
mechanically lower — regression to the mean is built into the numerator. The negative lift is a
property of the comparison, not of the technology.

**The declared post-hoc correction.** Comparing the same future block with the cell's **long-run rate**
up to the origin removes the mechanical dependence:

| predictor (vs long-run baseline) | flags | P(outcome\|flag) | P(outcome\|no flag) | lift | 95 % CI |
|---|---:|---:|---:|---:|---|
| calibrated increase | 5 | 0.20 | 0.33 | 0.60 | [0.00, 2.08] |
| naive increase | 149 | 0.39 | 0.32 | **1.22** | [0.95, 1.53] |
| persistence increase | 173 | 0.38 | 0.32 | 1.20 | [0.94, 1.49] |
| calibrated decrease | 16 | 0.88 | 0.65 | 1.35 | [0.90, 1.57] |
| naive decrease | 434 | 0.67 | 0.63 | 1.06 | [0.92, 1.23] |

**The sign flips.** Under the unbiased baseline, naive increase flags show a *positive* point estimate
(lift 1.22) instead of a strongly negative one — which confirms that the pre-registered negative lift
was the bias, not a finding.

**The honest verdict.**

1. **No predictor achieves a 95 % interval excluding 1** against the long-run baseline. There is **no
   evidence that a change signal predicts 12-month-ahead activity above the cell's own long-run rate**.
2. The naive-increase point estimate of 1.22 (CI 0.95–1.53) is the closest thing to a hint, and it is
   not established. It is also not the calibrated signal — it is the raw ratio the programme spent
   cycle 13 dismantling.
3. **The calibrated signal is too rare to be a prediction trigger at this resolution**: 5 flags in 717
   observations. Calibration made the momentum honest and, in the same move, too sparse to predict with.
   That is a property of ~0.2 events per cell-month, not of the method.

**What this licenses.** A statement about the predictability of public filing activity at this
granularity: no detectable 12-month-ahead predictability above baseline, with the intervals reported.
**Not** a statement that corporate technological evolution is unpredictable — the data cannot see far
enough to say that, and the observation is about filing rates, not technology.

**Design lesson recorded.** A benchmark outcome must not be defined relative to the same window that
triggered the signal. This is now the fourth self-caught design flaw of the programme (after the entry
denominator, the post-hoc nomination, and the collector pagination), and the first caught *inside a
benchmark* rather than in a finding.

---

## D-037 — B-051: point-in-time rebuild, three backdated snapshots, and a leakage path that had to be closed first

**Date:** 2026-11-03. **Status:** accepted. Creates and closes B-051.

**The leakage path, found while implementing it.** Cycle 14's profile builder used two inputs that
were *not* cut at an as-of date, even though the profile claims a window: the **trial lane** was read
in full and **product-code first-seen** was computed over the whole lane. Any historical rebuild would
therefore have carried future information into a "point-in-time" profile. This is the fifth
self-caught defect of the programme and the first one that would have silently invalidated a
point-in-time claim.

**The fix.** `build_profiles.py --as-of D` now:
* keeps only regulatory events with `date <= D`, and ends the window at `month(D)`;
* filters the **trial lane** to `event_date <= D`;
* recomputes **code first-seen** from the truncated events only;
* writes a `leakage_audit` block per profile recording the latest regulatory event, latest trial
  event and latest code first-seen that actually entered the profile.

**Three backdated snapshots, frozen and verified.**

| as-of | events used | window ends | detected momentum | profiles |
|---|---:|---|---:|---:|
| 2020-12-31 | 12,853 lane events | 2020-12 | 5 | 53 |
| 2022-12-31 | 19,182 | 2022-12 | 5 | 53 |
| 2024-12-31 | 25,772 | 2024-12 | 1 | 53 |
| 2026-11-02 (cycle 14) | full lane | 2026-09 | 4 | 53 |

`snapshot_diff.py` audits every snapshot: **0 leakage problems** across the three auditable ones (every
recorded latest event is on or before its as-of date, and every window ends on or before the as-of
month). The cycle-14 snapshot is reported as **not auditable** rather than clean, because it predates
the audit block — the two are different statements and are kept different.

**What the diffs show.** Between consecutive snapshots: 8, 5 and 7 companies changed momentum verdict;
21, 21 and 16 changed their track sets (always entries, never drops — the lane accumulates). Roster
event totals grow 1,797 → 2,503 → 3,235 → 3,928, so the snapshots are genuinely different states of
knowledge, not copies.

**Verdict stability across the chain.** Of 53 companies tracked through all four snapshots, **40 have a
stable verdict, 13 change at least once, and 2 reverse outright** (`hologic`:
no-change → decreasing → increasing → no-change; `zimmer_biomet`: increasing → decreasing → no-change).
A quarter of companies changing verdict with the as-of date is consistent with the calibrated test's
measured low power, and it is the honest way to present a nowcast: the verdict is a statement about
this data at this date, not a property of the company.

**Why this matters for the objective.** The objective asks for point-in-time datasets and rolling-origin
benchmarks. This round makes the *provenance* of a profile auditable to a date: a future cycle can
rebuild the 2022-12-31 view from the same code and verify it byte-for-byte against the frozen manifest,
and can prove no evidence after that date entered it. That is the precondition for any honest
rolling-origin evaluation of the Understand layer.

**Not claimed.** That the 2022-12 verdicts were "right" or "wrong" — there is no ground truth for a
technology position. What is claimed is only that the pipeline is now cut at the date it says it is.

---

## D-038 — B-052: paper draft v1 written from committed artifacts, with a machine-verified claim map

**Date:** 2026-11-03. **Status:** accepted. Creates B-052 (draft v1 shipped).

**What was produced.** `papers/PAPER_v1.md` — a complete draft (~3,500 words) covering the corpus and
provenance, the controlled-truth detection frontier, the five retracted findings, the calibration
result, the rolling-origin null, verdict instability across as-of dates, the Understand layer, seven
measurement rules, limitations, reproduction commands and references.

**The sourcing rule, and why it is mechanical.** A paper about retraction discipline cannot contain
hand-copied numbers. Every quantitative claim is declared in `papers/CLAIMS.json` with the artifact that
holds it and the exact source substring, and `papers/verify_claims.py` checks **both directions**: the
artifact must contain the recorded value and the paper must contain it too. The current state is **45 of
45 claims verified**. Notably, drafting failed this check three times before it passed — two claimed
figures were mis-transcribed from memory and one was omitted from the text — which is exactly the failure
mode the check exists to catch, caught on the author rather than on a reader.

**Three drafting decisions worth recording.**

1. **The paper's headline is negative.** Five retractions, no surviving positive result, and the
   programme's real output (a frontier, a calibration rule, a point-in-time chain, seven measurement
   rules) is methodological. Presenting it otherwise would be the exact behaviour the programme exists
   to prevent.
2. **The retraction table names the control that killed each finding**, not only the finding. A retraction
   without its mechanism cannot be learned from.
3. **The limitations section states what the data cannot see** (intent, capability, internal R&D,
   resolution) and points to the decision log for the full record rather than curating it here.

**Status.** Draft v1. It is not submitted anywhere and no venue is claimed. It is a repository artifact
with a verifiable claim map, which is what the mission's "ship papers" requirement asks of an autonomous
programme that cannot present results to peers.

**Known gaps before any submission.** No figures (the artifacts contain the data; plotting is deferred);
no external validation on a second domain; the retraction table would benefit from a per-finding
reproduction script index; and the two independent lanes are reported as collected limits rather than as
standalone studies.

---

## D-039 — B-053: paper figures generated as SVG from the artifacts, and visually verified

**Date:** 2026-11-03. **Status:** accepted. Creates and closes B-053.

**Why hand-written SVG.** The repository is stdlib-only by policy (`dependencies = []`) and matplotlib
is not installed. Rather than add a plotting dependency for four figures, `papers/figures.py` emits SVG
directly: a deterministic, text-diffable format whose values can be re-derived and checked.

**The four figures and what each shows.**

| figure | artifact | plotted points | what it settles |
|---|---|---:|---|
| `fig1_frontier.svg` | `experiments/detect_v1/benchmark.json` | 16 | sensitivity vs achieved false-alarm rate for four detectors with clustered CIs — the frontier, not a ranking |
| `fig2_calibration.svg` | `experiments/b027/momentum_calibration.json` | 50 | rate ratio against exact p-value; grey markers pass the 1.25 ratio rule but not the test |
| `fig3_rolling_origin.svg` | `experiments/b050/rolling_origin.json` | 12 | rolling-origin lift with clustered intervals for all twelve predictor/outcome pairs; every interval crosses 1 |
| `fig4_verdict_stability.svg` | `experiments/b027/verdict_stability.json` | 53 | one cell per company and as-of date; two companies marked reversed |

**Verification, and a rendering check that caught real defects.** `papers/verify_figures.py` re-derives
every plotted value from its source artifact and requires an exact match with
`papers/figures/figures_data.json`, parses each SVG as XML, rejects numeric artefacts (NaN/inf/None as
standalone tokens, not substrings of words), and requires the paper to link each file. That is
**4 figures, 131 plotted points, 0 failures**.

Because SVG validity is not the same as readability, each figure was additionally rendered to PNG with
headless Edge and inspected. That step caught three layout defects that no structural check would have
found: figure 3's predictor labels were clipped outside the canvas; figure 2's rightmost annotation ran
off the frame; and figure 4 had no company labels at all. All three are fixed and the regenerated plates
were re-inspected.

**What this changes about the paper.** D-038 recorded "no figures" as the only blocking gap for a
readable submission. That gap is now closed with generated, verified, dependency-free plates.

**Not claimed.** The figures do not add evidence; they re-present committed numbers. Their value is that
a reader can see the frontier's shape and the calibration gap without reading seventeen result files.

---

## D-040 — Pre-registration: spike / level-shift / ramp classification of alerts (B-026)

**Date:** 2026-11-03. **Status:** accepted; written before `experiments/b026/spike_vs_shift.py` was first
run.

An alert that cannot be classified is half useless: a one-month burst and a genuine level shift demand
different responses. B-026 asks whether the **shape** of a detected change can be recovered from a short
confirmation window, with measured accuracy against **known injected shapes**.

**Design.**

* **Base series.** Real (company, track) monthly cell series from the lane, using only cells with a
  measurable baseline (≥24 months of history and a baseline rate that admits an increase). Each cell is
  used once, at a recorded injection month.
* **Injected shapes.** At the injection month *t*, three shapes are added to the observed counts:
  1. **spike** — a single-month pulse;
  2. **level shift** — a step that persists for twelve months;
  3. **ramp** — a linear increase across twelve months.
  Panel counts are conditioned on the cell's own baseline rate so the three shapes have comparable
  magnitude, and injections are applied on a common random number scheme across shapes.
* **Detector.** A fixed, deliberately simple rule: alert when the three-month rate exceeds twice the
  eighteen-month baseline rate. The detector is not tuned here; its behaviour is already characterised in
  cycle 3.
* **Confirmation window.** Two months. The classifier may look at the alert month and the two months
  after it — **never later** — because in use that is all the time a decision-maker has.
* **Classifier.** Transparent rules, not a fitted model: if the post-alert rate has fallen back toward
  baseline it is a **spike**; if it is elevated and still rising across the confirmation window it is a
  **ramp**; otherwise it is a **level shift**. Thresholds are fixed here: "fallen back" means below 1.5×
  baseline in the confirmation window; "still rising" means the last confirmation month exceeds the
  first.
* **Estimands.** (a) a 3×3 confusion matrix over the three true shapes; (b) balanced accuracy
  (mean per-class recall), since classes are equally frequent by construction; (c) for the binary
  decision that actually matters — promote to "technology change" only if sustained — precision and
  recall of the *sustained* class (level + ramp). Inference by company-clustered bootstrap over cells.
* **What counts as success.** Balanced accuracy meaningfully above the 1/3 chance line, and binary
  precision above the base rate of sustained alerts. The pre-declared failure mode: the confirmation
  window is too short at this data's counting rates, in which case the honest output is "shape cannot be
  recovered at this resolution", not a tuned classifier.

**Not claimed even on success.** Shape recovery says nothing about whether the change is technological;
it is a property of the time series. Promotion to "technology change" remains a human judgement supported
by the profile's other evidence fields.

---

## D-041 — B-026 outcome: the pre-registered shape classifier failed; the failure was the rule's window, and the corrected version works moderately well (post-hoc)

**Date:** 2026-11-03. **Status:** accepted. Closes B-026; opens B-054 for confirmation.

**What ran.** 171 injections of three known shapes (spike, level, ramp) into real (company, track) series
from 65 cells with a measurable baseline; a fixed detector produced **151 alerts** (88 %); a
pre-registered rule classified each alert from the alert month plus two confirmation months. Company-
clustered bootstrap, 2000 replications.

**Pre-registered result: failure by its own criterion.**

| truth \ predicted | spike | level | ramp | recall |
|---|---:|---:|---:|---:|
| spike (41) | 7 | 34 | 0 | **0.171** |
| level (57) | 0 | 49 | 8 | 0.860 |
| ramp (53) | 0 | 45 | 8 | 0.151 |

Balanced accuracy **0.394** (95 % CI 0.361–0.438) against a 0.333 chance line; sustained-change precision
**0.764** against a **0.728** base rate — the rule is barely better than always saying "level", and its
own reference implementation scores 0.333 / 0.728. Ramp and level were essentially never separated.

**Diagnosis, and the declared post-hoc variant.** The pre-registered window began at the alert month,
which for a spike *is* the pulse: the burst inflated the "post-alert" rate and the rule almost never
called a spike. Re-running the same rule with the alert month excluded:

| truth \ predicted | spike | level | ramp | recall |
|---|---:|---:|---:|---:|
| spike (41) | 34 | 2 | 5 | **0.829** |
| level (57) | 0 | 47 | 10 | 0.825 |
| ramp (53) | 1 | 43 | 9 | 0.170 |

Balanced accuracy **0.608** (95 % CI 0.552–0.659); sustained-change precision **0.940** (95 % CI
0.903–0.978) against the 0.728 base rate, with recall 0.991.

**What this licenses, and how narrowly.** The binary decision that matters — *promote an alert to
"technology change" or treat it as a transient spike* — becomes meaningfully better than a blanket
promotion: precision 0.94 instead of 0.73, driven by detecting 83 % of spikes. The three-way distinction
does **not** work: ramp recall stays at 0.17, so "ramp versus level shift" is not recoverable from a
two-month window at this counting rate.

**Why the good result must be labelled.** The improvement was found by changing the rule after seeing its
failure. It is a post-hoc result and cannot be treated as confirmed. **B-054** will re-pre-register the
corrected window against fresh injections (different origins and cells) before this is used to justify
promotion logic. Until that runs, the pre-registered 0.394 stands as the reported classification accuracy
and 0.608 is a hypothesis.

**Never claimed.** Shape recovery says nothing about whether a change is technological. It classifies the
time series, not the technology, and promotion of an alert to "technology change" remains a human
judgement supported by the profile's other evidence fields.

---

## D-042 — Pre-registration: confirmatory test of the corrected confirmation window (B-054)

**Date:** 2026-11-03. **Status:** accepted; written before `experiments/b026/confirm_window.py` was first
run.

**Why a separate confirmation.** D-041 found that excluding the alert month from the confirmation window
lifts balanced accuracy from 0.394 to 0.608 and sustained-change precision from 0.764 to 0.940. That
improvement was obtained **after** seeing the pre-registered rule fail, so it is a hypothesis, not a
result. This fixes a confirmatory test in advance.

**Fixed design.**

* **Cells.** The same 65 eligible cells. They cannot be replaced (that is the entire eligible set), so cell
  reuse is **declared as a limitation**, not hidden.
* **Fresh origins.** For each cell, the injection month must be at least **6 months away** from the
  discovery origin recorded in `experiments/b026/spike_vs_shift.json`, and three fresh origins are drawn
  per cell with seed 2026. No injected observation from the discovery run is reused.
* **Injected shapes, detector, magnitudes.** Identical to D-040: spike / level / ramp at three times the
  cell's baseline rate; alert when the three-month rate reaches twice the eighteen-month baseline.
* **Classifier.** The corrected rule only: the confirmation window is the two months **after** the alert
  month, never including it. Thresholds unchanged (falls back below 1.5× baseline → spike; rising across
  the window → ramp; else level).
* **Estimands.** Balanced accuracy; sustained-change precision and recall; 3×3 confusion matrix;
  company-clustered bootstrap (2,000 replications, seed 7).

**Pre-declared decision rule.**

* **CONFIRMED** iff sustained-change precision ≥ 0.85 **and** balanced accuracy ≥ 0.50 **and** the
  bootstrap lower 95 % bound on sustained-change precision exceeds the sustained base rate measured in this
  sample.
* **NOT CONFIRMED** otherwise. A partial pattern (precision high, balanced accuracy low) is reported as
  "binary promotion confirmed, three-way classification not", which is a narrower claim and must be stated
  that way.
* **Never** re-tuned after seeing these numbers. If it fails, the promotion rule stays at the
  pre-registered accuracy of D-041 and the window fix is recorded as overfitting to the discovery sample.

**What confirmation would license.** That a two-month post-alert window can tell a transient spike from a
sustained change at this data's counting rate, so that "promote to technology change" is an evidence-based
decision rather than a blanket one. It would still say nothing about whether the change is technological.

---

## D-043 — B-054 outcome: the corrected confirmation window CONFIRMS on fresh injections; the programme has its first validated decision rule

**Date:** 2026-11-03. **Status:** accepted. Closes B-054. **First pre-registered confirmation that passed.**

**What ran.** The D-042 confirmatory design: 65 cells, three fresh origins per cell with every injection
month at least six months from the discovery origin, zero origins inside the guard band, same shapes,
magnitudes and detector. **525 injections, 494 alerts.** Company-clustered bootstrap, 2,000 replications.

| truth \ predicted | spike | level | ramp | recall |
|---|---:|---:|---:|---:|
| spike (120) | 118 | 15 | 17 | **0.787** |
| level (175) | 0 | 144 | 31 | 0.823 |
| ramp (169) | 3 | 142 | 24 | 0.142 |

* balanced accuracy **0.584** (95 % CI 0.556–0.607), pre-declared floor 0.50 → **pass**
* sustained-change precision **0.914** (95 % CI 0.892–0.934), pre-declared floor 0.85 → **pass**
* sustained base rate **0.696**; CI lower bound 0.892 exceeds it → **pass**

**Verdict: CONFIRMED** by the rule fixed in D-042 before the run.

**What exactly is confirmed — and what is not.** The confirmable claim is the **binary** one: with a
two-month post-alert window, the decision *promote this alert to "technology change" or treat it as a
transient spike* is better than blanket promotion — precision 0.914 against a 0.696 base rate, because
78.7 % of spikes are caught. The **three-way** claim is not confirmed in substance: ramp recall is 0.142,
so "ramp versus level shift" remains unrecovered at this counting rate even though the aggregate balanced
accuracy clears its floor. The aggregate passes because two of the three classes are separated; that is a
narrower success than the aggregate number suggests and must be stated that way.

**The honest caveat about how it was obtained.** The window fix came from the discovery sample, so this is
confirmation of a *hypothesis that was informed by data*, on data that were not. That is the standard
pre-registration-after-discovery pattern, and it is weaker than confirming an a-priori hypothesis: the
hypothesis space was narrowed using the same cells. Cell reuse across discovery and confirmation is a
declared limitation; only the injection months were fresh.

**What this changes for the programme.** It is the first time a pre-registered prediction of this
programme's own behaviour survived an out-of-sample test. The promotion rule can be used in the Understand
layer with a measured error rate rather than as a default. It does **not** rescue any earlier finding: the
five retractions stand, the rolling-origin null stands, and no claim is made about whether a promoted
change is technological.

**Not claimed.** That the rule generalises beyond (company, track) monthly filing counts at ~0.2 events per
month; that shape recovery implies technological significance; that a ramp can be distinguished at all.

---

## D-044 — Pre-registration: deployment resolution for the OBSERVE layer (B-039)

**Date:** 2026-11-03. **Status:** accepted; written before `experiments/b039/deployment_resolution.py` was
first run.

**The question.** The layer has to operate at *some* resolution. Cycle 3b/3c measured that detector memory
must be expressed in calendar time (D-020) and that the identity of the best detector changes with the bin
width (D-018). B-039 requires choosing the operating resolution, re-reading the sweep there, and naming a
detector **only if** the choice is identifiable.

**Resolution.** **Three months (quarterly)**, justified by the decision cadence the layer serves: technology
portfolio reviews, board cycles and analyst re-forecasting in this domain are quarterly, and a monthly
resolution produces ~0.2 events per cell-month where the detectors cannot resolve anything (measured, not
assumed). The choice is recorded here; it is a deployment decision, not an empirical optimum.

**Rules fixed now.**

* Evaluated on the existing bin-width sweep (widths 1, 2, 3, 4, 6 months), with all detector memory in
  calendar months, at a 2 % false-alarm budget.
* Each detector's operating point is the sweep row whose achieved false-alarm rate is closest to and not
  above the budget. A detector with **no** row at or below the budget is reported as **not calibratable at
  this budget**, which is a finding, not a missing value.
* Uncertainty: Wilson 95 % intervals on each sensitivity, from the sweep's trial counts.
* **Identifiability rule:** the detector is named only if the winner is the same at every width **and**
  every pairwise Kendall tau between width rankings is ≥ 0.5. Otherwise the report must state that no
  detector is identifiable and that the deployment choice is resolution-specific.

**What naming a detector would license.** Only: "at the resolution this layer operates at, and within this
corpus, detector X has the highest measured sensitivity at the stated false-alarm budget." Not a claim that
X is the best detector in general, and not transferable to another resolution without re-measurement.

**What failure would license.** That the layer must present the frontier rather than a winner, and that any
downstream artifact using a single detector must carry the resolution at which it was validated.

---

## D-045 — B-039 outcome: the layer deploys at quarterly resolution; at that resolution one detector wins, but no detector is identifiable across resolutions

**Date:** 2026-11-03. **Status:** accepted. Closes B-039.

**The deployment decision.** The OBSERVE layer will operate at **3 months (quarterly)**. The justification
is the decision cadence it serves — quarterly technology-portfolio reviews and analyst re-forecasting — plus
a measured reason: at monthly resolution a cell holds ~0.2 events per month, where the detectors cannot
resolve anything (D-018, D-024). This is a **deployment choice**, not an empirical optimum, and it is
recorded as such.

Detector memory was already expressed in calendar months (D-020), so the sweep read here is the corrected
one.

**Result at the deployment resolution** (39 bins, 101 cells, 56 evaluation cells, 224 trials per detector,
2 % false-alarm budget, achieved FAR 0.0179):

| detector | sensitivity | 95 % CI | median delay |
|---|---:|---|---:|
| **rolling z-score** | **0.147** | 0.112–0.182 | 2 months |
| Poisson Bayes factor | 0.073 | 0.051–0.096 | 0 months |
| Poisson CUSUM | 0.065 | 0.036–0.102 | 3 months |
| naive rate multiplier | 0.025 | 0.011–0.042 | 2 months |

At this resolution the z-score interval does not overlap any other detector's interval: within the
deployment resolution, it is the best of the four.

**The identifiability check (the part that forbids a general winner).**

| width (months) | winner |
|---:|---|
| 1 | naive rate multiplier |
| 2 | Poisson CUSUM |
| 3 | rolling z-score |
| 4 | Poisson CUSUM |
| 6 | rolling z-score |

Kendall tau between the deployment ranking and the others: **−1.0** at monthly (a complete reversal), 0.0 at
2 months, 0.33 at 4 months, 0.67 at 6 months. The pre-registered rule (same winner everywhere AND every tau
≥ 0.5) therefore **fails**.

**Verdict, stated in the form B-039 demanded.** No detector is identifiable as best in general. The layer
deploys the **rolling z-score at quarterly resolution**, and every downstream artifact must state that
resolution. The choice is not a ranking claim and must not be cited as one; if the operating resolution ever
changes, the detector must be re-measured, because the monthly ranking puts the same detector **last**.

**What this changes in the product.** The profile's alert machinery operates quarterly and carries
`resolution: 3 months` in its provenance. The detection section of the paper now reports the deployment
choice together with the reversal.

**Not claimed.** That the z-score is the best detector; that the quarterly sensitivity of 0.147 is adequate
for any particular decision; or that a detector validated here transfers to another corpus or another
resolution.

---

## D-046 — B-056: the validated detector and promotion rule are now in the product, with provenance

**Date:** 2026-11-03. **Status:** accepted. Closes B-056.

**What changed.** The profile engine no longer carries only a 24-month rate test. Each profile's momentum
field now includes a **`deployment_alerts`** block that applies the detector the programme actually validated:

* **resolution 3 months** (D-045), memory 12 months, baseline 24 months;
* **rolling z-score with threshold 3.5**, the setting that achieved a **0.018** false-alarm rate in the
  controlled-truth sweep (measured sensitivity **0.147** at that operating point);
* alerts reported only for the **last 8 quarters**, because a 2019 alert is not a live decision input;
* every alert lists track, quarter, event count, baseline mean and z, and the block states the measured
  false-alarm rate and sensitivity **in the profile itself** — not in a methods note the reader may never see.

**Why the seven-field contract survives.** The block is nested inside `momentum`; the top-level schema is
still the seven required fields. No new field, no version bump, and the historical snapshots remain
verifiable as they were frozen.

**What it produces on real data, and why that is sobering.** Medtronic's profile now shows two live alerts
(`coronary` 2026-Q3, `insulin_delivery` 2025-Q3), each **two events against a baseline of 0.25** (z = 3.5).
Both are legitimate at the measured false-alarm rate, and both are substantively thin — which is what a
0.147-sensitivity detector at 0.2 events per cell-month is *supposed* to look like. The profile prints the
counts and the baseline next to the alert precisely so a reader cannot mistake "calibrated" for
"substantial".

**Verification, now enforced.** `selfcheck.py` fails a profile whose deployment block names a detector or
resolution other than the validated one, or whose alert fails to clear its own threshold, or whose Markdown
omits the detector line or the false-alarm rate. The 36 pre-existing profile tests grew to **44**, covering
the resolution lock, provenance fields, steady-series silence, burst flagging, recency window, empty history,
and the Markdown statement.

**Deliberately not done.** The **promotion rule** (D-043: two-month post-alert window, precision 0.914) is
*not* applied automatically here. It needs a live alert stream and an explicit human or policy decision to
promote, and wiring it silently would turn a measured decision rule into an opaque default. It is recorded
in `STATE.json` as an available, measured rule for the Understand layer to use.

**Not claimed.** That these alerts are technology changes; that two-event alerts are actionable on their own;
or that the quarterly detector is the best possible — only that it is the one measured to be deployable at
this resolution.

---

## D-047 — Pre-registration: confirm the promotion rule at the legal-entity unit (B-055)

**Date:** 2026-11-03. **Status:** accepted; written before `experiments/b026/confirm_entity_cells.py` was
first run.

**Why.** D-043 confirmed the corrected promotion rule on fresh injection months but the **same 65
company-level cells**, and the paper carries that caveat. The natural next test is a **different unit of
analysis**: the legal entity rather than the curated company. Each company cell aggregates one to thirty
entities, so entity-level cells are finer, more numerous, and exercise a different aggregation.

**What is fresh and what is not — stated before the run.** Entity cells are **not independent** of company
cells: every entity belongs to a company, and a company's discoveries are the sum of its entities'. This
test therefore does **not** establish independence; it establishes whether the rule depends on the level of
aggregation. That distinction is the honest scope of the result, whatever it shows.

**Fixed design.**

* Unit: (legal entity, technology track) monthly series from the same frozen lane.
* Eligibility, unchanged from D-040: at least 24 months of history and a baseline rate admitting an
  increase (≥0.15 events per month).
* Injection: same three shapes at three times the cell's baseline rate, three fresh origins per cell, seed
  4040, guard band not applicable (no entity-level discovery run exists).
* Detector and classifier: identical to D-042 — alert when the three-month rate reaches twice the
  eighteen-month baseline; classify from the two months **after** the alert, excluding the alert month.
* Estimands: 3×3 confusion matrix, balanced accuracy, sustained-change precision and recall; company-clustered
  bootstrap over the **company** of each entity (2,000 replications), because entities in one company share
  that company's filing behaviour.
* **Decision rule, identical to D-042:** CONFIRMED iff sustained-change precision ≥ 0.85 AND balanced accuracy
  ≥ 0.50 AND the bootstrap lower 95 % bound on precision exceeds the sustained base rate measured here.

**Possible outcomes and what each means.** Confirmation at entity level would show the rule is not an
artefact of company aggregation. Non-confirmation would show it is **company-level only**, which must then be
stated wherever the rule is used, and the product's alert machinery (which is company-level today) would be
unaffected. A partial pattern (precision clears, balanced accuracy does not) is reported as "binary promotion
confirmed at entity level, three-way classification not".

**Never claimed.** That entity-level confirmation makes the rule portable to another corpus, another
resolution, or another country's regulatory lane.

---

## D-048 — B-055 outcome: the promotion rule also holds at the legal-entity unit; the result is no longer an artefact of company aggregation

**Date:** 2026-11-03. **Status:** accepted. Closes B-055.

**What ran.** The D-047 confirmatory design at a different unit of analysis: **(legal entity × track)**
monthly series instead of (curated company × track). **6,841** entity cells, **191** eligible under the
unchanged floors, three fresh origins per cell (seed 4040), same shapes, magnitudes, detector and classifier;
bootstrap clustered by the entity's **company** because entities in one firm share filing behaviour.

**Result: 1,196 scored alerts, CONFIRMED at entity level.**

| truth \ predicted | spike | level | ramp | recall |
|---|---:|---:|---:|---:|
| spike | 277 | 39 | 37 | **0.785** |
| level | 0 | 373 | 50 | 0.882 |
| ramp | 3 | 368 | 49 | 0.117 |

* balanced accuracy **0.594** (95 % CI 0.583–0.616), floor 0.50 → pass
* sustained-change precision **0.917** (95 % CI 0.909–0.941), floor 0.85 → pass
* sustained base rate **0.705**; CI lower bound 0.909 exceeds it → pass

The numbers are almost identical to the company-level confirmation (0.584; 0.914): balanced accuracy differs
by 0.010 and precision by 0.003. A rule that survives at a unit **five times finer** with essentially the same
accuracy is not an aggregation artefact.

**What this does and does not establish.** It establishes that the two-month promotion rule is not dependent
on the curated-company unit: it holds when the same filings are counted per legal entity. It does **not**
establish independence — entity cells nest inside company cells, so the estimate is not a second independent
sample, and the pre-registration says so. It also does not fix the scope limit: **ramp recall falls to
0.117**, so three-way shape recovery remains unrecovered at either unit.

**Consequence for the claim.** `STATE.json` now records the rule as confirmed at **both** units, and the
paper's caveat can be narrowed from "same cells" to "a nested unit, not an independent sample". The product's
alert machinery is unaffected because it operates at the company level, which is the unit already confirmed.

**Not claimed.** Portability to another corpus, another resolution, or another regulatory lane.

---

## D-049 — B-057: promotion policy is code, not prose; and a sixth frozen snapshot

**Date:** 2026-11-03. **Status:** accepted. Closes B-057.

**The policy question this answers.** The programme has one confirmed rule (D-043, replicated D-048) and a
deployed detector (D-045), but until now nothing stated **when a detected change may be called a technology
change**. Leaving that to prose would repeat the failure mode this programme keeps catching: a claim that
lives in a methods note and gets upgraded in a slide.

**The policy, implemented.** `medradar/intelligence/promotion.py` gates promotion through four conditions and
is covered by **18 tests**:

1. the alert must carry the validated detector provenance (rolling z-score, 3-month resolution, threshold
   3.5) and clear its own threshold;
2. the two quarters **after** the alert (never including it) must classify as sustained under the confirmed
   rule;
3. the profile's contradictory-evidence checks must exist (the schema already forbids their absence);
4. **human sign-off is required and recorded** — `decide_promotion` can only return
   `promote_pending_signoff` or `reject`, and the policy sets `automated_promotion_allowed: False`.
   A test asserts no verdict other than those two is ever produced, so an automated path cannot be added
   without breaking a test.

The policy is also written into `research/PREDICTION_PROTOCOL.md` §8, so document and code say the same thing.

**What it produces on the frozen data.** Medtronic's two live alerts diverge as they should:
`coronary` 2026-Q3 is **rejected** because no confirmation quarters exist yet, and `insulin_delivery`
2025-Q3 is **promote_pending_signoff** (classified ramp, elevated and still rising). Both verdicts appear
in the profile with the sign-off requirement and the filing-rate statement attached.

**Sixth frozen snapshot.** `snapshots/2026-11-03` was frozen and verified (manifest `5b7062d2…`), now carrying
the deployment block and promotion verdicts. The diff against `2026-11-02` reports **identical data** —
3,928 events, 0 momentum changes, 0 track changes — which is the correct reading: what changed between the
two snapshots is **knowledge about the data**, not the data. The earlier four snapshots remain verifiable as
frozen, and none was rewritten.

**Verification.** `selfcheck.py` now fails a profile whose alert lacks a promotion decision, whose verdict is
outside `{reject, promote_pending_signoff}`, whose `requires_signoff` is not true, whose statement does not
carry the filing-rate wording, or whose Markdown omits the verdict. Five profiles and five snapshots pass.

**Not claimed.** That a promoted change is technological, or that the gate is adequate for a different corpus,
resolution or regulatory lane.

---

## D-050 — Pre-registration: confirmation-window sensitivity analysis for the ramp class (B-058)

**Date:** 2026-11-03. **Status:** accepted; written before `experiments/b026/window_tradeoff.py` was first
run.

**The gap.** The confirmed promotion rule (D-043, replicated D-048) fixes a **two-month** confirmation window.
It separates spike from sustained well (precision 0.914–0.917) but cannot separate a **ramp** from a level
shift: ramp recall is 0.142 at company level and 0.117 at entity level. A ramp is a change that keeps
growing, so a longer window should help — at the cost of slower decisions and, possibly, precision.

**What this is.** A **sensitivity analysis**, not a confirmation. It is declared here so the window grid is
not chosen after seeing results, and its output can only ever be a **proposal** to re-pre-register, never a
new rule. Any window change would require its own confirmatory run on fresh origins before it may be used.

**Fixed design.**

* Units: both — (company × track) and (legal entity × track) monthly series, same eligibility floors as
  D-040.
* Windows: **1, 2, 3, 4 and 6 months** after the alert (the alert month is always excluded, per D-041).
* Same injected shapes, magnitudes, detector and thresholds; the only varied quantity is the window length.
* Estimands per window and unit: three-class balanced accuracy, **ramp recall**, sustained-change precision
  and recall, and the ramp/level confusion specifically.
* Seeds fixed: 7071 for company cells, 7072 for entity cells, three origins per cell.

**Decision rule for a recommendation.** A window is worth re-pre-registering only if it raises **ramp recall
above 0.40** while keeping sustained-change precision **at or above 0.85** on **both** units. Anything less
is reported as "the ramp class remains unrecoverable at this counting rate" and the policy stays at two
months.

**Not claimed even if a window qualifies.** That the longer window is better for decisions (it is slower);
that the qualifying result is confirmed (it is exploratory until a fresh confirmatory run); or that ramp
recovery implies technological significance.

---

## D-051 — B-058 outcome: no confirmation window recovers the ramp class; the two-month policy stands

**Date:** 2026-11-03. **Status:** accepted. Closes B-058.

**What ran.** The D-050 sensitivity analysis: window lengths 1, 2, 3, 4 and 6 months after the alert, on both
units (65 eligible company cells, 191 eligible entity cells), three fresh origins per cell, fixed seeds, same
shapes, magnitudes and detector. **495 company alerts and 1,222 entity alerts per window**, so the comparison
is not sample-limited.

**Ramp recall, by window.**

| window | company ramp recall | company precision | entity ramp recall | entity precision |
|---:|---:|---:|---:|---:|
| 1 month | 0.000 | 0.911 | 0.000 | 0.937 |
| 2 months | 0.154 | 0.897 | 0.128 | 0.897 |
| 3 months | 0.183 | 0.895 | 0.107 | 0.889 |
| 4 months | 0.143 | 0.886 | 0.107 | 0.889 |
| 6 months | 0.229 | 0.862 | 0.114 | 0.885 |

**No window qualifies** under the pre-declared rule (ramp recall > 0.40 with precision ≥ 0.85 on both units).
The best ramp recall anywhere is **0.229**, and it buys nothing: precision falls monotonically as the window
lengthens.

**The trap worth naming.** Balanced accuracy is *highest* at the one-month window (0.588 company, 0.616
entity) — because a one-month window can never see a ramp forming, so it calls every ramp "level" and gets
those cases "right" for the wrong reason. Reporting balanced accuracy alone would recommend the window that
is worst at the thing the window was added for. **The class-specific recall is the metric that matters**, which
is why the pre-registration fixed it in advance.

**Decision.** The promotion policy stays at **two months** (D-049). Three-way shape classification is
recorded as **not available** at this counting rate rather than as a tuning problem: with 0.2 events per
cell-month and a ramp that adds roughly one event per month at peak, the confirmation window would need to be
longer than the ramps that need distinguishing.

**What this changes in the product.** Nothing operational — the policy already promotes on the
binary sustained/spike decision. What changes is the claim: the profile no longer implies that `ramp` is a
recoverable class; the sensitivity analysis is the evidence that it is not.

**Not claimed.** That ramp detection is impossible in principle; that a corpus with denser counting would
fail the same way; or that the two-month window is optimal — only that no tested window beats it on the
pre-declared criterion.

**Carried into the product in the same cycle.** The blind spot is now part of every profile's
`limits_and_provenance` field: two limits were added — "a ramp cannot be separated from a level shift at this
counting rate (best recall 0.229 over windows of 1–6 months)" and "the alert detector is validated at
quarterly resolution only; at monthly resolution the same detector ranks last". A profile that cannot state
these is not allowed to present its alerts as more than they are, and two tests assert both strings are
present in the JSON and in the rendered Markdown.

---

## D-052 — Pre-registration: second-domain validation of the promotion rule on the hiring lane (B-059)

**Date:** 2026-11-03. **Status:** accepted; written before `experiments/b026/validate_hiring_domain.py` was
first run.

**Why.** The promotion rule has been confirmed twice — on company cells and on legal-entity cells — but both
are the **same corpus and the same recording process** (FDA premarket submissions). The obvious remaining
threat is that the rule is a property of that corpus's counting behaviour. A second domain is required before
any portability claim.

**Domain chosen, and why it was measured first.** Two candidate independent lanes were inspected:

| lane | series available | cells meeting the unchanged floors |
|---|---|---|
| ClinicalTrials.gov device trials | 180 company-track cells | **5** |
| archived job postings (hiring) | 13 company series | **7** |

The trial lane is too sparse to test anything; the hiring lane provides **seven company-level monthly posting
series** with rates from 16.6 to 98.2 postings per month. That is the domain used, and its size is a **known
power limitation declared now**, not after looking at the result.

**Fixed design.** Same detector (three-month rate ≥ twice the eighteen-month baseline), same classifier (the
two months after the alert, alert month excluded), same shapes and the same 3× elevation, three fresh origins
per series, seed 9091. Posting counts are mapped onto the same 119-month window as the regulatory lane so the
injection geometry is identical.

**Estimands.** Confusion matrix over the three shapes, balanced accuracy, sustained-change precision and
recall; company bootstrap (2,000 replications) — with seven companies the intervals will be wide, which is
reported rather than hidden.

**Pre-declared reading.**

* **CONSISTENT** iff sustained-change precision ≥ 0.85 **and** balanced accuracy ≥ 0.50.
* **NOT CONSISTENT** otherwise, in which case the rule is recorded as corpus-specific and every downstream
  claim about portability is withdrawn.
* **UNDERPOWERED** is reported explicitly if the bootstrap precision interval is wider than 0.30, in which
  case a point estimate is not allowed to be described as either consistent or inconsistent.

**What it cannot establish.** That the rule transfers to a third domain; that posting-flow counts behave like
filing counts in general; or anything about which domain is "better". It establishes only whether the rule
survives a change of recording process with seven series and the power that implies.

---

## D-053 — B-059 outcome: the promotion rule survives a second domain; scope of the claim widens by exactly that much

**Date:** 2026-11-03. **Status:** accepted. Closes B-059.

**What ran.** The D-052 design: the identical detector, classifier, shapes and 3× elevation applied to
**archived job-posting series** — a different recording process from FDA filings. Eight of thirteen hiring
series met the unchanged eligibility floors (rates 2.9–98.2 postings per month), three fresh origins each,
seed 9091. **43 scored alerts.**

| truth \ predicted | spike | level | ramp | recall |
|---|---:|---:|---:|---:|
| spike (7) | 5 | 2 | 0 | 0.714 |
| level (17) | 0 | 13 | 4 | 0.765 |
| ramp (10) | 1 | 6 | 3 | 0.300 |

* balanced accuracy **0.593** (95 % CI 0.503–0.806), floor 0.50 → pass
* sustained-change precision **0.929** (95 % CI 0.872–1.000), floor 0.85 → pass
* sustained base rate **0.794**; precision interval lies above it
* bootstrap interval width **0.128**, below the declared 0.30 underpowered threshold

**Verdict: CONSISTENT with the confirmed rule on a second domain.**

**What this buys, precisely.** The rule is not a property of the FDA filing corpus alone: applying it to a
web-archive posting-flow series produces the same qualitative behaviour (spike separated, sustained promoted,
precision above base rate). The programme may now say its one confirmed decision rule transfers **once** to a
different recording process.

**What this does not buy.** It is **not** a second confirmation: 43 alerts against 494 and 1,196 in the
registry runs, eight series, one non-registry domain, and the ramp class remains unreliable (recall 0.300 on
ten cases — higher than the registry's 0.117–0.142 but far too few cases to claim a difference). It does not
establish portability to a third domain, to another resolution, or to another country's filings, and the
policy's error rates remain the registry-measured ones.

**A detail worth recording.** The trial lane was inspected first and rejected on measured grounds — only
**5** of its cells met the eligibility floors — so the domain choice was made by feasibility data, not by
picking the flattering option. Both probe scripts are committed.

---

## D-054 — B-060: promotions get their own append-only ledger, and a promotion is not a finding

**Date:** 2026-11-03. **Status:** accepted. Closes B-060.

**The accounting problem.** The results ledger (`research/RESULTS/README.md`, R1–R105) records findings. A
promoted alert is **not** a finding: it is an operational decision that one alert's change persisted under a
measured rule. Mixing the two would let the programme inflate its record with its own outputs — the failure
mode every retraction in this project was about, one level up.

**What was built.**

1. **A separate append-only ledger**, `research/RESULTS/PROMOTIONS.md`, written only by
   `experiments/b027/log_promotion.py`. Each row records: promotion id, company, track, alert quarter, the
   confirmation-window evidence, the classifier shape, the policy version, the **signer identity**, the
   justification and the UTC timestamp. The header states in one line that these are promotion decisions, not
   findings.
2. **Sign-off is enforced, not requested.** `build_promotion_record` rejects an empty signer, rejects any
   verdict other than `promote_pending_signoff`, and requires a non-empty justification. The logger refuses to
   write a record that fails those checks, so an unattributed promotion cannot enter the ledger.
3. **Attribution reaches the snapshot.** `freeze_snapshot.py` now hashes `research/RESULTS/PROMOTIONS.md` as an
   input source, so every future snapshot manifest ties the prompts to the exact promotion ledger it was built
   with. A promotion recorded after a snapshot is therefore visibly absent from that snapshot's manifest hash.

**Why an append-only markdown file rather than a database.** The ledger has to be reviewable by a human who is
not running code, diffable in the repository, and cheap to audit. A markdown table with a fixed column order
satisfies all three; a database would hide the same information behind a query language.

**What this does not do.** It does not make promotions correct — the signer can still be wrong, and the
measured precision (0.914–0.929) means roughly one promotion in twelve is expected to be a miss. It makes them
**attributable and separable from findings**, which is what the objective's auditing requirement needs.

**First entry.** The Medtronic `insulin_delivery` 2025-Q3 alert is recorded as **pending sign-off**, not
promoted: the programme has no human signer in this session, and inventing one would defeat the mechanism. The
ledger shows the row as awaiting signature with all evidence attached.

---

## D-055 — B-061: the objective is audited mechanically, not asserted

**Date:** 2026-11-03. **Status:** accepted. Closes B-061.

**Why.** Every goal round ends with a claim that the programme advanced. After twenty-seven cycles that claim
needs evidence a reviewer can re-run, not a narrative. `tools/audit_objectives.py` turns the mission text into
checks and writes `research/AUDIT.json` and `research/AUDIT.md`.

**What it checks.** The eleven required research-state files (existence and non-trivial size); backlog
integrity (parses, unique ids, status distribution); state completeness (phase, cycle, findings, next actions);
that the loop actually ran (decision count, result rows, recorded negatives, retractions marked); experiments
with committed artifacts; **point-in-time snapshots verifying** through the manifest machinery; the
rolling-origin benchmark; frozen forecasts (honestly N/A when the git-ignored registry is absent);
the paper's claim map re-verifying; the figures re-verifying; the profile self-check; optionally the test
suite; and whether the working tree is committed.

**Result on the current repository.**

| requirement | status | evidence |
|---|---|---|
| persistent research state files | PASS | 11 files under `research/` |
| backlog integrity | PASS | 48 tasks, no duplicate ids |
| state completeness | PASS | phase, cycle, findings, next actions |
| loop ran and was recorded | PASS | 54 decisions, 108 result rows, 24 negative/null |
| experiments with committed artifacts | PASS | 77 JSON artifacts across 16 experiment dirs |
| point-in-time snapshots verify | PASS | **5 of 5** |
| rolling-origin benchmark | PASS | 376 cells, 12 origins, 717 observations |
| frozen forecasts | PASS | registry present, 25 registered forecasts |
| paper with verified claims | PASS | 66/66 claims |
| figures verify | PASS | 4 figures, 0 failures |
| profile self-check | PASS | 5 profiles + 5 snapshots |
| working tree committed | N/A | expected non-empty while a cycle is in progress |

**What the audit is for, and what it is not.** It is a **completeness and reproducibility** check: it can prove
that the artifacts exist, are committed, and still verify. It **cannot** prove the science is right — no script
can. The retraction discipline and the claim maps are what stand in for that, and the audit simply refuses to
let a missing or broken artifact survive into a later round.

**A second, smaller change in the same cycle.** The profile's limits now name the **governing promotion policy
version**, and the promotion ledger gained a **reviewer checklist** stating what a signer must inspect —
including that a promotion signed without independent corroboration is a rate change, not a technology change.

---

## D-056 — Pre-registration: third-unit validation at market-aggregate (track) level (B-062)

**Date:** 2026-11-03. **Status:** accepted; written before `experiments/b026/validate_track_domain.py` was
first run.

**The gap left by the previous two validations.** The rule has been tested on company cells (~0.2 events per
cell-month) and legal-entity cells (~0.05), and on a second recording process (job postings). All three are
**sparse counting regimes**. A different threat is that the rule depends on sparsity: at high counts the
Poisson z-score becomes more sensitive and a fixed 3× elevation is far easier to detect, so the classifier
could behave differently in either direction.

**The unit.** Market-aggregate series: monthly event counts per **technology track**, summed across all
companies. Measured before writing this: **38 tracks, all 38 eligible** under the unchanged floors, median 270
events per track — roughly three orders of magnitude denser per series than a company cell.

**Fixed design.** Same detector (three-month rate ≥ twice the eighteen-month baseline), same classifier (the
two months after the alert, alert month excluded), same shapes and 3× elevation, three fresh origins per
track, seed 5150. Because tracks are the units and are not nested in anything, the bootstrap resamples
**tracks**.

**Estimands.** 3×3 confusion matrix, balanced accuracy, sustained-change precision and recall, bootstrap
intervals with 2,000 replications.

**Pre-declared reading (identical to D-052).**

* **CONSISTENT** iff sustained-change precision ≥ 0.85 **and** balanced accuracy ≥ 0.50.
* **UNDERPOWERED** if the bootstrap precision interval exceeds 0.30 width; then no point estimate may be
  described as consistent or inconsistent.
* **NOT CONSISTENT** otherwise — in which case the rule is recorded as **count-regime dependent** and every
  claim about portability across granularities is withdrawn.

**What a negative would mean.** Not that the rule is wrong, but that it is calibrated for sparse series and
must not be transferred to aggregated ones without re-measurement — which is exactly the kind of scope
statement this programme exists to produce.

**What neither outcome licenses.** Any claim about technology; any claim that market-level aggregation is the
"right" unit; or that the result extends to another trackonomy.

---

## D-057 — B-062 outcome: the rule holds at market-aggregate level, and ramp recoverability scales with density

**Date:** 2026-11-03. **Status:** accepted. Closes B-062.

**What ran.** The D-056 design: identical detector, classifier, shapes and 3× elevation applied to **monthly
counts per technology track** — 38 tracks, all eligible, median 270 events each, roughly a thousand times
denser per series than a company cell. Three fresh origins per track, seed 5150, tracks resampled in the
bootstrap. **297 scored alerts.**

| truth \ predicted | spike | level | ramp | recall |
|---|---:|---:|---:|---:|
| spike (92) | 67 | 17 | 8 | 0.728 |
| level (114) | 0 | 63 | 51 | 0.553 |
| ramp (91) | 5 | 50 | 36 | **0.396** |

* balanced accuracy **0.559** (95 % CI 0.514–0.605), floor 0.50 → pass
* sustained-change precision **0.889** (95 % CI 0.851–0.925), floor 0.85 → pass
* sustained base rate **0.690**; precision interval above it
* bootstrap interval width **0.074**, far below the underpowered threshold

**Verdict: CONSISTENT at market-aggregate level.**

**The result that matters beyond the verdict.** Ramp recall now lines up with counting density across every
unit tested:

| unit | series density | ramp recall |
|---|---:|---:|
| legal entity × track | ~0.05 events/series-month | 0.117 |
| company × track | ~0.2 | 0.142 |
| company job postings | 2.9–98 | 0.300 |
| technology track (aggregate) | ~2.3 (median 270/119) | **0.396** |

This is the first coherent scaling relationship the programme has found: **ramp recoverability is a function
of how many events the series carries**, not of the classifier. It also explains, after the fact, why the
window-length sensitivity analysis (D-051) could not rescue ramps — the sparse series simply do not contain
the counts, and lengthening a window cannot add information that is not there.

**What this buys.** The promotion rule now holds across three units (company, entity, market aggregate), a
~1000× density range, and two recording processes (FDA filings, archived job postings). That is a materially
stronger scope statement than the two-unit confirmation it had at D-048.

**What it does not buy.** Not portability to another taxonomy, corpus or country; not a claim that
market-aggregate alerts are the right unit for decisions; and the ramp scaling is a **cross-unit observational
gradient**, not a controlled experiment — density and unit type vary together, so the relationship is
suggestive rather than established. A controlled test would hold the unit fixed and vary density artificially,
which this run did not do.

**Policy unchanged.** The deployed detector and two-month window remain as fixed in D-045/D-049; this run
validates them elsewhere, it does not re-tune them.

---

## D-058 — Pre-registration: controlled density experiment for the ramp scaling (B-063)

**Date:** 2026-11-03. **Status:** accepted; written before `experiments/b026/density_experiment.py` was first
run.

**What is being tested.** D-057 found ramp recall rising with series density across units (0.117 entity → 0.142
company → 0.300 hiring → 0.396 track). That is **observational**: density and unit type vary together, so the
association could be produced by the unit rather than by the counts. This experiment holds the unit fixed and
varies density artificially.

**Design, fixed now.**

* **Base series.** The 38 technology-track monthly series (dense, median 270 events).
* **Thinning.** Each series is thinned by binomial down-sampling at factors **τ ∈ {1, 2, 5, 10, 20}**: each
  monthly count is replaced by a Binomial(count, 1/τ) draw. This preserves the temporal shape while reducing
  counts, which is exactly the manipulation the observational comparison lacked.
* **Injection and classification.** Identical to every previous run: three shapes at three times the **thinned**
  baseline rate, injected after thinning; detection and classification use the same detector and the same
  two-month post-alert window.
* **Fixed seeds.** Seed 6161 for the thinning draws and the origins, three origins per track per factor.
* **Estimands.** Per factor: 3×3 confusion, balanced accuracy, sustained-change precision, **ramp recall**,
  achieved alerts. Bootstrap resampling tracks (2,000 replications).

**Pre-declared decision.**

* **EXPERIMENTALLY SUPPORTED** iff ramp recall is **monotonically non-decreasing** in density with
  Spearman ρ ≥ 0.8 across the five factors **and** the ramp-recall interval at τ = 1 does not overlap the
  interval at τ = 20.
* **NOT SUPPORTED** otherwise, in which case the cross-unit gradient is recorded as a unit effect, not a
  density effect.

**What even support would mean.** That, holding the taxonomy and the unit fixed, ramp recoverability is limited
by counts. It would justify stating a **density threshold below which ramps must not be reported** — a
practical rule for the profile — and would not license extrapolation to another corpus.

**What it would not mean.** That denser data makes the classifier better at everything (spike and level are
already near ceiling), or that the scaling law generalises beyond binomial thinning of this taxonomy.

---

## D-059 — B-063 outcome: the controlled density experiment did NOT clear its pre-declared bar

**Date:** 2026-11-03. **Status:** accepted. Closes B-063. **Negative against the pre-registered criterion.**

**What ran.** The D-058 design: the 38 dense track series thinned by binomial down-sampling at τ ∈ {1, 2, 5, 10,
20}, then the same shapes, detector and classifier. Seed 6161; three origins per track per factor; 135–276
scored alerts per factor.

| τ | density (events/series-month) | ramp recall | 95 % CI | sustained precision |
|---:|---:|---:|---|---:|
| 1 | 4.16 | **0.440** | 0.333–0.556 | 0.926 |
| 2 | 2.08 | 0.415 | 0.295–0.532 | 0.889 |
| 5 | 0.84 | 0.300 | 0.200–0.407 | 0.927 |
| 10 | 0.43 | 0.318 | 0.182–0.456 | 0.893 |
| 20 | 0.21 | **0.222** | 0.106–0.356 | 0.885 |

**The pre-declared decision fails on two of its three criteria.**

* Spearman ρ between density and ramp recall = **0.882** (floor 0.8) → pass
* **strict monotonicity: FAILS**, by one inversion: τ = 5 (0.300) sits 0.018 *below* τ = 10 (0.318)
* **interval separation: FAILS**, by an overlap of 0.023 between the dense interval's lower bound (0.333) and
  the sparse interval's upper bound (0.356)

**Verdict as pre-registered: NOT SUPPORTED.** By the rule fixed before the run, the cross-unit gradient is
recorded as **not established as a density effect**. That is the reported result and it is not being revised
after the fact.

**But the reading has to be exact, because "not supported" is not "disconfirmed".** The point estimate roughly
**halves** (0.440 → 0.222) as density falls twentyfold, with ρ = 0.88 and precision stable across every factor
(0.885–0.927). The two failures are narrow: an 0.018 inversion between adjacent factors whose intervals overlap
almost entirely, and a 0.023 overlap of interval edges. What the experiment establishes is that the **effect size
is large and consistent in direction while the evidence is insufficient to certify strict monotonicity at this
sample size** — 50 to 100 ramp cases per factor.

**The pre-registration's own flaw.** Requiring *strict* monotonicity across five noisy point estimates is a
brittle gate: a single 0.018 wobble between adjacent factors voids the whole claim even when ρ = 0.88. A better
criterion would be stated in terms of the rank correlation and the dense-to-sparse effect size. Recording this
as a defect of my own pre-registration, not of the data.

**What happens next (B-064).** A revised criterion will be pre-registered — rank correlation ≥ 0.8 **and** dense
ramp recall at least twice the sparse value, both required, with no strict-monotonicity clause — and confirmed on
**fresh seeds and a fresh thinning draw**. Until that runs, the scaling stays **suggestive**: the paper must not
present it as established, and the profile keeps its per-unit measured limits rather than a density threshold.

**Policy unchanged.** No detector, window or promotion rule changes on the basis of a result that failed its own
pre-registered bar.

---

## D-060 — Pre-registration: robust-criterion confirmation of the density scaling (B-064)

**Date:** 2026-11-03. **Status:** accepted; written before `experiments/b026/density_confirm.py` was first run.

**Why a second run.** D-059 reported that the controlled density experiment **failed its pre-declared bar** even
though ramp recall halved (0.440 → 0.222) with rank correlation 0.882: strict monotonicity broke on a 0.018
inversion and the dense/sparse intervals overlapped by 0.023. D-059 recorded that the **criterion** was the weak
part — requiring strict monotonicity across five noisy point estimates. A criterion chosen now must therefore be
(a) stated before looking, and (b) confirmed on data not used to design it.

**Fresh data.** Same 38 dense track series and the same five thinning factors, but **entirely fresh random
draws**: thinning seed **7171**, origins seed **8181**, bootstrap seed **9191**. No observation from D-058's run
enters this run; only the design (thinning method, shapes, detector, classifier, floors) is reused, which is what
a confirmation must do.

**Revised criterion, fixed now.**

* **CONFIRMED** iff **both**: Spearman ρ between density and ramp recall **≥ 0.8**, **and** dense ramp recall
  (τ = 1) **≥ 2 ×** sparse ramp recall (τ = 20), using point estimates.
* **NOT CONFIRMED** otherwise — including if ρ is high but the effect size falls short, which would mean the
  association is rank-order only and not a practically meaningful scaling.
* **No strict-monotonicity clause.** That gate was D-058's defect and is deliberately dropped: with 50–100 ramp
  cases per factor, adjacent-factor point estimates are expected to wobble.
* Reported alongside: per-factor recall with bootstrap intervals and sustained-change precision, so the shape of
  the effect remains visible rather than being reduced to a pass/fail.

**Disclosure.** This is a **revised pre-registration after a failure**, and it carries the risk that a relaxed
criterion is merely easier to pass. That risk is bounded by the fresh draws and by the effect-size clause: the
dense value must be at least **double** the sparse value, which is a substantive requirement rather than a
significance formality. If it confirms, the claim is "the density dependence was confirmed under a criterion
fixed after the first attempt failed, on fresh draws" — and it must be stated that way, not as a first-pass
success.

**What a confirmation would license.** That, holding the taxonomy and unit fixed, ramp recoverability is limited
by counts — enough to state a **density floor** below which the profile must not report ramp-shaped changes.
**What it would not license.** Extrapolation to another corpus, taxonomy or recording process; or any claim that
density improves spike and level detection, which are already near ceiling.

---

## D-061 — B-064 outcome: the density scaling CONFIRMS on fresh draws, and the product must stop labelling ramps below the floor

**Date:** 2026-11-03. **Status:** accepted. Closes B-064.

**What ran.** The D-060 design: the same 38 dense track series and five thinning factors, but **entirely fresh
draws** (thinning seed 7171, origins 8181, bootstrap 9191) and a criterion fixed before looking — rank
correlation ≥ 0.8 **and** dense ramp recall ≥ 2× sparse, with the strict-monotonicity clause removed because D-059
showed it was the brittle part.

| τ | density (events/series-month) | ramp recall | 95 % CI | precision |
|---:|---:|---:|---|---:|
| 1 | 4.16 | **0.444** | 0.333–0.560 | 0.909 |
| 2 | 2.06 | 0.402 | 0.280–0.525 | 0.922 |
| 5 | 0.84 | 0.321 | 0.218–0.432 | 0.884 |
| 10 | 0.42 | 0.214 | 0.114–0.328 | 0.867 |
| 20 | 0.22 | **0.204** | 0.111–0.300 | 0.890 |

Spearman ρ = **0.908** (floor 0.8), dense/sparse ratio = **2.18×** (floor 2.0). The ordering is also monotone
here, though that is not required by the criterion any more.

**Verdict: CONFIRMED under the revised criterion on fresh draws.** It must be stated with its history: the
**first** controlled test failed a stricter pre-registered gate, the gate was recorded as the defect, and the
revised criterion was confirmed out of sample. That is weaker than a first-pass confirmation and stronger than an
exploratory finding, and the paper says exactly that.

**What this establishes.** Holding the taxonomy and unit fixed, **ramp recoverability is limited by counts.**
Below roughly one event per series-month the classifier can separate a spike from a sustained change but cannot
say which sustained shape it is; at two or more events per series-month ramp recall roughly doubles.

**The product consequence, which is the real output of this cycle.** The promotion policy was still labelling
Medtronic's `insulin_delivery` alert a **ramp** — a company cell carrying about 0.08 events per month, where the
measured ramp recall is 0.14. That label was unjustified. Policy **v2** therefore adds a reporting rule:

* if the classifier says *ramp* but the cell's baseline rate is **below 1.0 event per month**, the shape is
  reported as **`sustained_unresolved`** with the reason attached;
* the alert remains **promotable** — the binary spike-versus-sustained decision is unaffected and remains
  confirmed at these densities;
* the profile and the promotion ledger inherit the honest label, and a test asserts the relabelling.

**Not claimed.** That the scaling generalises beyond binomial thinning of this taxonomy; that the 1.0/month floor
is optimal (it is a conservative choice consistent with the measured curve, not a fitted threshold); or that any
ramp above the floor is technological.

---

## D-062 — B-065: labelled snapshots and a promotion-label diff, so a policy change is visible in the record

**Date:** 2026-11-03. **Status:** accepted. Closes B-065.

**The problem.** D-061 changed the promotion policy to v2, which relabels some alerts from `ramp` to
`sustained_unresolved`. A point-in-time chain that cannot show **which claims a policy change altered** is only
half a record: a reader comparing two snapshots would see identical data, zero momentum changes and zero track
changes, and could reasonably conclude nothing happened.

**What was built.**

1. **Labelled snapshots.** `freeze_snapshot.py --label` allows a second snapshot at the same as-of date
   (`2026-11-03-policy-v2`). The manifest still records the true as-of; the directory carries the suffix. Both
   the self-check and the diff accept `as-of` or `as-of-<label>` so the chain stays verifiable, and the leakage
   audit uses the manifest's as-of rather than the directory name.
2. **A promotion-label diff.** `snapshot_diff.py` now compares, per alert, the triple
   (verdict, shape, policy version) and records every change. The policy-v2 snapshot therefore shows **32 alert
   labels changed**, of which **8 changed shape** from `ramp` to `sustained_unresolved` — the exact set of claims
   the density finding disqualified.
3. **The sixth auditable snapshot**, `2026-11-03-policy-v2`, frozen and verified (manifest `44abde16…`), which
   also carries the promotion-ledger hash so the labels are tied to the signed ledger at that moment.

**What this establishes.** The record can now answer a question that previously had no artefact: *what did the
policy change alter, and what did it leave alone?* Data-level diffs report zero change (3,928 events, no momentum
or track movement), while the label-level diff reports 32 changes with their before/after triples. Both are
correct; only reporting one of them would be misleading.

**Not claimed.** That the relabelled alerts are now wrong — the binary promotion verdict is unchanged
(`promote_pending_signoff` for all eight); only the shape label was withdrawn. Nor that the
1.0-event-per-month floor is optimal; D-061 already states it is a conservative point on a measured curve.

---

## D-063 — B-066: one command ends a round, and the paper's limitations now state the scope

**Date:** 2026-11-03. **Status:** accepted. Closes B-066.

**The round-end routine is now executable.** `tools/round_end.py` runs every verifier in the repository in one
pass and writes `tools/round_end.json` plus a readable log:

| step | current result |
|---|---|
| test suite (`medradar selftest`) | PASS — OK (skipped=3) |
| paper claim map | PASS — 78 claims, 0 failures |
| paper figures | PASS — 4 figures, 0 failures |
| profile self-check | PASS — 5 profiles, 0 failures |
| snapshot chain | PASS — 0 leakage problems |
| objective audit | PASS — 11 PASS / 0 FAIL / 1 N/A |
| repository state | PASS — HEAD synced with remote |

Two implementation details matter and are recorded because both were wrong on the first attempt: unittest
reports its summary on **stderr**, so a detail extractor that reads only stdout silently reports the last
documentation line instead of `OK (skipped=3)`; and a generic "last line containing a keyword" heuristic reports
the wrong line for the audit, so each step now declares the markers to look for.

**The paper's Limitations section was updated to say what a reader most needs to know and previously had to
reconstruct.** It now states plainly that **exactly one decision rule was confirmed** against five retractions;
that the rule requires human sign-off with no automated path; that the ramp label is withheld below 1.0 event per
month and those alerts are reported as `sustained_unresolved`; that the density scaling is a **post-failure
confirmation** which should be weighted differently from a first-pass result; and that the repository contains an
executable objective audit and round-end routine, so progress can be re-run rather than trusted.

**Why this is worth a cycle.** Twenty-eight rounds produced verification tools faster than they produced a
repeatable finish line. A round now ends with one command whose exit code is the claim, which removes the main
remaining opportunity for an over-stated summary.

---

## D-064 — Pre-registration: rolling-origin evaluation of the promotion pipeline (B-067)

**Date:** 2026-11-03. **Status:** accepted; written before `experiments/b067/promotion_rolling_origin.py` was
first run.

**The question nobody has asked yet.** The programme has tested detectors, calibrated momentum, confirmed a
promotion rule on injected shapes, and validated it across units and domains. It has **not** tested whether the
**promotion filter improves downstream decisions on real history**. Every component has been validated in
isolation; the pipeline as a whole has not been evaluated end to end. That is the gap this cycle closes.

**Design, fixed now.**

* **Units.** Every (curated company × technology track) cell, quarterly counts, same lane.
* **Origins.** Quarterly, from 2019-Q1 to 2024-Q4 (a confirmation window and a follow-up window must both fit).
* **Alert.** At origin *t*, the deployed detector: z of the current quarter against the mean of the previous
  eight quarters (24 months), threshold **3.5** — the D-045 operating point.
* **Promotion decision.** The confirmed rule applied to the two quarters after the alert (t+1, t+2), using the
  same per-quarter baseline: shape *spike* → not promoted; *level* / *ramp* / *sustained_unresolved* → promoted.
  Alert month excluded, exactly as in live use.
* **Outcome.** Activity in the four quarters after the confirmation window (t+3 … t+6), compared with the
  alert-time baseline: **persisted** iff the mean count is at least the baseline mean.
* **Comparison.** P(persisted) among **promoted** alerts versus **unpromoted** alerts (spikes), plus a control
  group of non-alert cell-quarters. Bootstrap resampling **companies** (2,000 replications).

**Pre-declared decision.**

* **PROMOTION ADDS VALUE** iff P(persisted | promoted) exceeds P(persisted | unpromoted) with the bootstrap
  95 % interval on the difference excluding zero.
* **NO ADDED VALUE** otherwise, in which case the promotion filter is recorded as a documentation discipline
  rather than a predictive improvement, and the paper must say so.

**What a positive would license.** That the two-month filter improves the downstream hit rate of the alerting
pipeline on real history — a statement about decision quality, not about technology.
**What it would not license.** Any claim that promoted changes are technological, or that the pipeline is
predictive beyond the persistence of elevated filing rates.

---

## D-065 — B-067 outcome: the alerting pipeline predicts persistence, but the promotion filter's ADDED value is not established

**Date:** 2026-11-03. **Status:** accepted. Closes B-067.

**What ran.** The D-064 design: quarterly origins 2019-Q1 … 2024-Q4, the deployed detector (z ≥ 3.5 against the
previous eight quarters), the confirmed two-quarter promotion rule, outcome = mean activity in t+3 … t+6 at least
the alert-time baseline; companies resampled in the bootstrap.

**Result: 68 alerts (35 promoted, 33 unpromoted) and 4,594 control cell-quarters.**

| group | P(persisted) | 95 % CI |
|---|---:|---|
| promoted | **0.800** | 0.652–0.917 |
| unpromoted (spikes) | 0.667 | — |
| no alert (control) | **0.373** | — |
| difference (promoted − unpromoted) | **+0.133** | **−0.074 … 0.344** |

**Verdict as pre-registered: NO ADDED VALUE.** The interval on the difference includes zero, so by the rule fixed
in D-064 the promotion filter is recorded as a **documentation discipline, not a measured predictive
improvement**.

**But the pipeline result is not a null, and it would be dishonest to report only the verdict.** Alerts persist
far more often than comparable non-alert cell-quarters (0.80 and 0.67 against 0.37). That is the detector doing
its job: cells flagged at z ≥ 3.5 are substantially more likely to remain elevated than cells that were quiet.
What the experiment fails to establish is the **marginal** contribution of the second, two-month filter on top of
the alert — a 13-point difference measured on 33 unpromoted alerts, with a bootstrap interval spanning zero.

**Why it is underpowered, precisely.** Spikes are rare among alerts (33 of 68) precisely because the promotion
rule exists — the pipeline was designed to make shape the discriminator, and the design leaves few negative cases
to learn from. A test of the filter needs either a longer history or a lower alert threshold; the former is not
obtainable and the latter would change the operating point under test.

**Consequence for the product.** No change. The filter remains justified by its **shape classification**
performance measured on injections (D-043/D-048/D-057/D-061), not by this end-to-end test; the promotion policy
already says promotion is a decision with a measured error rate, not an optimisation. What changes is the paper:
the pipeline-level result must appear beside the injection results so that neither is read alone.

**Not claimed.** That the detector "predicts technology"; that the promotion filter is useless (it is
unestablished, not refuted); or that the 0.37 control rate is a fair counterfactual for cells at risk of
alerting — control cells are, by construction, not on an elevated path.

---

## D-066 — B-068: a frozen prospective forecast set, and the 7 forecasts that do not count as evidence

**Date:** 2026-11-03. **Status:** accepted. Closes B-068.

**Why.** The objective lists frozen forecasts; the legacy registry holds 25 nowcasts that cannot mature until
2027. This cycle registered a forecast set that can be scored as soon as the lane advances, from the current
frozen snapshot.

**What was built.**

* `medradar/intelligence/forecasts.py` — pure functions for quarter arithmetic, fixed windows, registration,
  validation and scoring (Brier, log loss, accuracy, per-decision breakdown; pending forecasts always reported).
* `research/forecasts/FORECAST_SET_2026-11-03.json` — **32 forecasts**, one per alert in the policy-v2 snapshot:
  17 promoted (probability 0.800 that activity persists) and 15 not promoted (0.667). Those probabilities are the
  **measured end-to-end pipeline rates** from D-065, not preferences. The set carries a content hash
  `d236b83f…` and the source snapshot's manifest hash.
* `experiments/b068/maturate_forecasts.py` — refuses to score a modified set (hash check), computes outcomes from
  the lane, and scores only what has matured.

**The finding that matters most is a defect in how I registered the set.** Because alerts in the snapshot include
quarters whose outcome windows are already observed, **7 of the 32 forecasts matured immediately at registration**.
A forecast registered after its outcome is known is not a forecast; it is a backfilled label. Those 7 are reported
separately and **excluded from prospective evidence**:

| group | n (matured) | mean predicted p | observed persistence | Brier |
|---|---:|---:|---:|---:|
| promoted | 4 | 0.800 | 0.500 | — |
| not promoted | 3 | 0.667 | 0.333 | — |
| overall | 7 | — | — | **0.337** (accuracy 0.429, log loss 0.896) |

The overall accuracy of 0.429 equals the majority-class base rate in that subsample: the forecasts carry **no
discernible information** there, which is consistent with D-065's end-to-end result and with the small sample. It
is a **sanity check that failed to reassure**, not evidence about the model.

**What is genuinely prospective.** The remaining **25 forecasts** mature between 2026-Q4 and 2028-Q1 and are the
only ones that can count as prospective evidence. They are frozen: any edit breaks the hash and the scorer refuses
to run.

**Rule recorded for future registrations.** A forecast set may only be registered from alerts whose **outcome
window is entirely in the future at registration time**. Future registration scripts must filter on that condition
and report the count of backfilled alerts separately; the current set predates this rule and is annotated as such.

**Not claimed.** Anything from the 7 backfilled forecasts; any scoring from the 25 pending ones before they mature.

**The clean prospective set (added in the same cycle).** The rule above was applied immediately rather than
deferred: `register_forecasts.py --lane-through 2026-Q3` produced
`research/forecasts/FORECAST_SET_2026-11-03_prospective.json` with **25 genuinely prospective forecasts** (13
promoted, 12 not), **7 backfilled alerts excluded** and counted explicitly, earliest maturation **2026-Q4**, hash
`09525994…`. Those 25 are the only forecasts in the repository that can later count as prospective evidence; the
first set is retained only as the record of the registration defect.

The objective audit now checks committed forecast sets directly — validating structure and recomputing each
content hash — instead of relying on the local, git-ignored registry. Current audit line: *"2 hash-verified
forecast set(s); 25 genuinely prospective forecasts pending maturation"*.

---

## D-067 — B-069: second paper (methods), with its own machine-verified claim map

**Date:** 2026-11-03. **Status:** accepted. Closes B-069.

**Why a second paper rather than a longer first one.** The empirical paper answers an empirical question and
carries five retractions plus one confirmed rule. The transferable output — the **measurement discipline** that
produced those retractions — is a different claim about a different audience: people building self-auditing
research systems. Folding it into the first paper would bury it in a results narrative.

**What the methods paper contains.** Nine rules, each tied to the specific failure that motivated it: state the
unit you measure (entity appearance vs firm entry, **79 %** of entry events); a ratio is not evidence (**35 of 53**
vs **4**; MDE range **1.77×–22.93×**); a benchmark outcome must not use the window that triggered the signal
(**0.49 → 1.22**); a holdout cannot confirm a hypothesis nominated with its help (**3** nominated, **0**
confirmed); a negative conclusion about data availability is as falsifiable as a positive claim (**11** firms after
the collector fix); robustness in the preferred direction is not validation; check the pipeline, not just the
statistics; report class-specific recall (**Rule 8**); and a forecast registered after its outcome is known is a
label (**7** of 32 forecasts, Brier **0.337**).

**Two mechanisms, described as the enforcement layer.** The profile schema rejects a profile without contradictory
evidence; the round-end command's exit code is the completion claim. The paper argues that rules in prose decay and
these do not.

**Two results that needed an intermediate category.** The density confirmation (post-failure: **0.018** inversion,
**0.023** overlap, rank correlation **0.882** then **0.908** with effect ratio **2.18×**) and the pipeline test that
found the detector but not the filter (**0.800 / 0.667 / 0.373**; difference **+0.133**, interval **−0.074 …
0.344**). Both are reported as what they are rather than forced into "confirmed" or "refuted".

**Sourcing, same rule as the first paper.** `papers/CLAIMS_METHODS.json` declares **22** quantitative claims with
their artifacts and exact substrings; `verify_claims.py --claims` checks both directions. The round-end routine now
runs **both** claim maps, so the methods paper cannot drift either.

**Status.** Draft v1: not submitted, no venue claimed. Known gap: it is a practice report from one programme, not a
validated framework; the paper says so in its own discussion, citing the instrumentation artefact the programme
found in its own negative conclusion.

---

## D-068 — B-070: the roadmap is rewritten from what exists, and the mission's honest position is updated

**Date:** 2026-11-03. **Status:** accepted. Closes B-070.

**Why this is a research act and not housekeeping.** The roadmap was written on 2026-11-02, before the detector was
validated, before the promotion rule existed, before four anticipations had failed and before either paper. Left
alone it would describe a programme that no longer exists, and a reader would have to reconstruct the real state from
36 results files. A plan of record that is stale is worse than none, because it invites the reader to trust it.

**What changed in `ROADMAP.md`.** It is now organised around a single status table where **every capability cites its
evidence**: foundation, entity universe, detection with its named non-identifiability limit, the deployment choice,
independent lanes with their coverage limits, the blocked patent and broad-hiring lanes, seven-field profiles, the
promotion policy with its sign-off gate, one confirmed decision rule, four failed anticipations with the design flaw
that produced each, the rolling-origin null, 25 frozen prospective forecasts, two papers with claim maps, and the
governance tooling. P4 is recorded as **not started on purpose**, with the reason (no baseline gap; the bottleneck is
information, not model capacity).

Section 3 is the part that matters for completion: it states **what remains and why it cannot be simulated** — 25
forecasts maturing 2026-Q4…2028-Q1, 25 legacy nowcasts maturing 2027-10, one promotion awaiting a human signature the
session cannot give, access-blocked lanes, and structurally unavailable hiring coverage for three deep-case companies.

**What changed in `MISSION.md`.** §9 is preserved unchanged as the record of the 2026-11-02 position; a new §10 states
today's position with the same discipline: what is now established (detector, one rule, the instrument, four
diagnosed failures, frozen prospective machinery, two papers), and what has **not** changed (zero prospective
calibration evidence; no visibility into intent, capability or internal R&D; information as the binding constraint;
five retractions).

**Why both documents were edited rather than appended to.** The roadmap is a plan of record and must read as current
state; the mission is a charter and must keep its history. Appending to both would have blurred that distinction.

**Not claimed.** That the programme is complete: maturation is time-dependent and three lanes are access-dependent.
The roadmap now says so in the place a reader will look first.

---

## D-069 — B-071: Figure 1 of the methods paper, and the layout defects its first render exposed

**Date:** 2026-11-03. **Status:** accepted. Closes B-071.

**What was built.** A fifth figure, `papers/figures/fig5_retraction_rules.svg`, mapping ten events in the
programme's record to the nine rules they motivated: **21 filled cells**, six retractions (including the hiring
coverage conclusion, which motivated Rule 5), two confirmations, one unestablished result and one excluded forecast
set. The map lives in `papers/rules_map.py`, so the drawing and the verification read the same source;
`verify_figures.py` re-derives every cell and compares it with the recorded data.

**What the count shows, and why it is worth a figure.** Rule 7 (check the pipeline, not just the statistics) is
motivated by **four** separate events and Rule 3 (a benchmark outcome must not use the triggering window) by
**three** — the two rules a reader is most likely to dismiss as boilerplate are the two with the most independent
evidence behind them. Rule 5 and Rule 6 have exactly one origin each, which is stated rather than evened out.

**The layout defects, found only by rendering.** The first version pushed its legend over columns 8 and 9 (two
column headings were invisible), printed the decision id on top of the event label, and ran the legend off the right
edge of the canvas. None of these is visible in the SVG source and none would be caught by `check_svg`, which
validates structure, not legibility. The fix was to move the legend into two rows below the grid, offset the decision
ids under their labels, and shrink the grid so the status column fits. This is the fourth time in the programme that
a headless-browser render found a defect the verifier could not — recorded because it is a recurring class, not an
accident.

**Supporting changes.** `papers/PAPER_METHODS_v1.md` gains the figure with a caption that states the counts;
`CLAIMS_METHODS.json` grows to **25** claims, three of which assert the figure's own numbers (21 filled cells, ten
events, nine rules) against `figures_data.json`; `verify_figures.py` now takes the paper into account when deciding
which figures a paper must link, so the methods paper is checked for its figure and the empirical paper for its four;
and the round-end gate runs both figure verifications, making the gate **9 steps**.

**Not claimed.** That the map is exhaustive — it records the events that motivated rules, not every failed
experiment; several negative results informed no new rule and are listed only in the results index.
