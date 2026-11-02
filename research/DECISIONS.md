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
