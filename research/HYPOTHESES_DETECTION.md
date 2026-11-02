# Cycle 3 hypothesis cards — change detection in the OBSERVE layer

**Written before any detection result exists.** Owner: `detect-auditor`. Created
2026-11-02 on branch `research/change-detection-v1`, before the detector suite
(`task-4`) has produced a single number and before the benchmark runs.
Any change to a card after results are seen must be recorded in `research/DECISIONS.md`
and invalidates the affected comparison.

**Purpose.** The cycle pre-registers a detector comparison (`DECISIONS.md` D-013). A
pre-registered comparison is only worth its pre-registration if its hypotheses can be
*wrong*. These cards exist to make each detection claim falsifiable in advance, and —
more importantly — to state, in numbers, the result that would kill it.

**Read `docs/research/DETECTION_DESIGN_REVIEW.md` first.** It establishes, with commands,
that the detection frame is much sparser and much more artifact-laden than the design
assumes, and it argues that the design's own truth model is the model the likelihood
detectors assume. Several cards below are stated so that they can lose for that reason.

## Conventions used by every card

- **P-DET** = the detection panel pre-registered in D-013: monthly counts of *material*
  events — one 510(k) clearance or one original PMA approval, PMA supplements excluded —
  per (legal entity, technology track), 2016-11 … 2026-10 (120 months), on the
  deterministic legal-entity cohort of `config/universe_v1.json` (200 entities). The
  panel is built once, hashed, and frozen before any detector runs.
- **Frame size, measured before these cards were written** (so that predictions are
  calibrated to reality, not to hope). The shipped universe artifact
  (`config/universe_v1.json`) contains 642 non-empty (entity × track) cells over the
  200-entity cohort and 108 cells with ≥24 events across all lanes; the material-only
  panel is smaller. On the 51-company mapping — a proxy frame of the same lane, used
  only because it is computable in one query — the material lane gives **316 streams
  with a median of 5 events per decade, 8.0% non-zero stream-months, 89 streams with
  ≥12 events and 39 with ≥24**. Commands are in the design review §3.2–3.3.
- **Strata, fixed now and not chosen after results.** **S-HI** = ≥24 material events over
  the window. **S-MID** = 12–23. **S-LO** = 1–11. Headline verdicts are taken on S-HI
  and on the pooled S-HI+S-MID; **S-LO is reported but never used for a verdict**,
  because the arithmetic in the design review §3.3 shows that a 2× step in such a stream
  is undetectable inside a 120-month window (72% of streams in the proxy frame need more
  than 120 months).
- **Arms.** **ARM-0** = real streams, no injection (the empirical false-alarm
  calibration arm, which the current design does not have). **ARM-1** = the Lead's
  model-aligned step injection over the seeded grid. **ARM-2** = model-misaligned and
  nuisance battery: single-month spike, 3–6-month ramp, transient plateau, panel-wide
  volume shock, end-of-series publication lag, entity-rename discontinuity. **ARM-3** =
  real data with multiplicity control and artifact conditioning.
- **FAR\*** = the matched operating point. Thresholds are *not* set at a nominal α:
  each detector's threshold is calibrated on **ARM-0** so that it produces the same
  number of alerts, and **FAR\* is defined as 1 alert per stream-year in S-HI**. All
  cross-detector comparisons are at FAR\*.
- **D50** = median detection delay in months. Censored units (never detected before the
  window ends) are counted, reported as a separate column, and never dropped.
- **Monte Carlo.** 200 replicates per (stream, onset, magnitude) cell, **common random
  numbers across detectors** (paired comparison), and a Monte Carlo 95% interval printed
  for every reported difference. A difference smaller than its MC interval is not a
  difference.
- **Status vocabulary:** `UNTESTED` (no data yet), `BLOCKED` (cannot be tested with the
  current data spine — a missing source, not a missing result), `PARTIAL` (degenerate or
  indirect evidence only), `REJECTED` (falsification condition met), `SUPPORTED`
  (pre-declared success condition met). No card is `SUPPORTED` on one arm or one stratum.

## Coverage map against the brief

| Brief | Card | Headline claim |
|---|---|---|
| h1 | **H-D1** | likelihood detectors beat the naive multiplier on delay vs false alarms |
| h2 | **H-D2** | detector ranking is stable (or, predicted: it is not) across companies and magnitudes |
| h3 | **H-D3** | real detections are confirmed by an *independent* source more often than matched controls |
| h4 | **H-D4** | a single-month spike is a false alarm for "sustained change" purposes |
| h5 | **H-D5** | performance degrades measurably under realistic data-quality perturbations |
| h6 | **H-D6** | FDR cuts the alert count substantially while preserving confirmed changes |
| — | **H-D7** | the real-data alert set is dominated by the boundary month and panel-wide volume |

---

## H-D1 — A likelihood detector wins the delay-vs-false-alarm frontier (h1)

- **Claim.** At matched empirical false-alarm rate FAR\*, a likelihood-based detector
  (Poisson CUSUM, or the Poisson Bayes factor at its ARM-0-calibrated threshold) reaches
  a shorter median detection delay than the naive rate-multiplier alert on ARM-1
  injections, in S-HI.
- **Why it matters.** This is the design's primary hypothesis and the whole basis for
  recommending likelihood-based detection in the OBSERVE layer. If it fails in its own
  model it cannot be rescued elsewhere.
- **Operational estimand.** Δ = D50(naive, FAR\*) − D50(likelihood, FAR\*), in months,
  S-HI, ARM-1, averaged over the magnitude grid; and the same Δ on ARM-2.
- **Prediction.** ARM-1, 2× step, S-HI (expected n ≈ 30–40 streams): Δ = 3–8 months in
  favour of the likelihood detectors, increasing in magnitude. At 1.5×, Δ collapses to
  ≤1 month and its interval includes 0. On ARM-2's spike and ramp classes, Δ ≤ 1 month
  and its interval includes 0 — that is the part I expect the design to lose.
  Note the arithmetic that constrains this: at a 2× step with a known baseline, the
  expected number of months needed to accumulate even a modest evidence threshold is
  4.605 / (0.3863·λ) months for rate λ per month, so most streams are censored and Δ can
  only be estimated on the few that are not.
- **Test procedure.** Freeze P-DET. Calibrate every detector's threshold on ARM-0 to
  FAR\*. Run ARM-1 and ARM-2 with common random numbers. Report D50, censoring share,
  detection probability at FAR\*, and Δ with MC intervals, by stratum and by magnitude,
  with S-LO shown but excluded from the verdict.
- **Falsification / kill condition.** **REJECTED** if any of: (a) Δ ≤ 0 in ARM-1 S-HI at
  FAR\* — the likelihood detectors are not better even inside their own model;
  (b) Δ > 0 only at an unmatched, higher empirical FAR (i.e. the "advantage" is that they
  fire more often); (c) Δ ≤ 1 month on ARM-2 — the claim of operational superiority for
  the OBSERVE layer is rejected even if (a) and (b) pass. Clause (c) is what makes this
  card falsifiable; without it the card restates a theorem (see entry 3 of the
  literature review).
- **Confounders / threats.** Threshold calibration path (must be identical across
  detectors); baseline estimated by the detector vs known to the generator; censoring
  reported or hidden; MC noise; a single control limit serving a whole magnitude grid
  (favours the grid point it was tuned on).
- **Status:** `UNTESTED`. **Evidence pointer:** ARM-0/1/2 run, `out/detection/`.

## H-D2 — Detector ranking is stable across companies and magnitudes (h2)

- **Claim (stated as a prediction, not a hope).** Detector ranking is **not** stable:
  leave-entity-group-out folds do not agree, and the ranking changes with change
  magnitude.
- **Why it matters.** The design's decision rule declares a likelihood detector better
  only if it "keeps that ordering under leave-company-out". If fold-level rankings are
  noise, that requirement is satisfied or violated at random, and the decision rule is
  a coin flip dressed as robustness.
- **Operational estimand.** Spearman rank correlation between fold-level detector
  rankings (Kendall's τ reported as a check); the identity of the top detector per fold;
  the rank of each detector at each grid magnitude.
- **Prediction.** (i) Spearman ρ < 0.5 in at least one third of fold pairs; (ii) the
  identity of the best detector changes in at least 2 of 5 folds; (iii) at least one
  detector moves by ≥2 rank places between the 1.5× and 3× magnitudes.
- **Test procedure.** Build folds at the **entity-group** level on the 200-entity cohort
  (5 folds, stratified by material-event count), not at the company level: measured from
  the universe artifact, the five mandated deep cases have 423 / 287 / 262 / 90 / 30
  material events spread over 30 / 24 / 36 / 2 / 5 applicant entities (Dräger's entire
  decade is 30 events in one cohort entity, Medtronic is split across 30 applicant
  strings), so "leave-company-out" over the five cases cannot be balanced and cannot be
  the primary stability test. Deep cases are reported individually and are not folds.
  Recompute the full ranking in each fold and at each magnitude; report the fold ×
  detector rank matrix.
- **Falsification / kill condition.** **REJECTED** if all five folds rank the detectors
  identically (ρ = 1.0 in every pair) and the ranking is identical at 1.5×, 2× and 3× —
  then the instability worry is falsified and the design's leave-company-out requirement
  is sufficient as written.
- **Confounders / threats.** Folds differ in stream count and thus in MC error; a fold
  with three S-HI streams will produce a rank ordering from almost no information. This
  is itself the phenomenon the card measures, so the card must report fold stream counts
  alongside the ranks or it becomes unfalsifiable.
- **Status:** `UNTESTED`. **Evidence pointer:** ARM-1 fold runs.

## H-D3 — Real detections are confirmed by an independent source more often than matched controls (h3)

- **Claim.** Detections on real streams (ARM-3) that are followed by elevated activity in
  an **independent** source are more frequent than matched non-detection control periods —
  i.e. an alert carries evidence that something other than the filing process changed.
- **Why it matters.** This is the only part of the design that speaks to the real world.
  Without it, every detection output is a statement about the FDA filing process, not
  about technology (literature review, cluster 7).
- **Operational estimand.** r = P(independent source elevated in the 12 months after an
  alert | alert); r₀ = the same probability for control periods matched on entity, track,
  calendar month **and the stream's activity level in the preceding 12 months**; effect =
  r / r₀. The activity-level match is not optional: alerts are, by construction, months
  in which the count exceeded the baseline, so an unmatched control period is a
  lower-activity period and regression to the mean alone will manufacture an uplift.
- **Prediction.** r / r₀ ≥ 1.5 with a 95% interval excluding 1; r ≥ 0.25 in S-HI; the
  uplift survives activity-level matching; it does **not** survive for the "PMA lane
  versus 510(k) lane" variant, because that variant is not independent.
- **Test procedure.** Pre-register the confirmation definition (which source, which
  threshold, which window, one- or two-sided) *before* seeing any alert. Match controls
  within stream and within ±3 months, on preceding-12-month activity. Report the
  PMA-lane variant separately and label it non-independent. If no source exists, mark the
  card `BLOCKED` and report the reason — do not substitute a same-system source.
- **Falsification / kill condition.** **REJECTED** if (a) the uplift disappears under
  activity-level matching (the effect was regression to the mean / selection on the
  outcome), or (b) the confirmation definition was not fixed before results, in which
  case whatever is reported is not this test. **BLOCKED — measured 2026-11-02 — if no
  source outside the openFDA filing lanes exists.** The current data spine offers:
  `publication_counts` in `data/research.sqlite` — **annual**, 2014–2026, **51
  companies only** (1 observation per 12-month confirmation window and 51 of the 200
  cohort entities); and `procurement_awards` — **3,453 rows, `award_date` NULL in all
  3,453, `pit_usable = 0` in all 3,453**. No trials table exists in any shipped
  database (`data/tkg.sqlite` holds only event / product_code / company / track nodes)
  and the `events` table contains only the two openFDA bulk sources. So as the design
  stands, Evaluation B has **no usable independent source**, and the honest status is
  `BLOCKED`, not a weak positive or a weak null.
- **Confounders / threats.** Circularity through the PMA lane (98.56% of the PMA lane is
  supplements, and 69.9% of the whole PMA lane — 16,680 of 23,871 rows — is
  manufacturing/site process change, so the PMA lane measures administrative throughput);
  annual resolution; coverage of 51/200
  entities; **temporal direction** — trials and publications usually *precede*
  device clearance, so a 12-month-after window is the wrong sign for a leading source;
  either justify the direction or report both windows.
- **Status:** `BLOCKED` on source availability; `UNTESTED` conditional on one being
  built. **Evidence pointer:** source census in the design review §3.6.

## H-D4 — A single-month spike is a false alarm for "sustained change" purposes (h4)

- **Claim.** Single-month spikes are a material share of the alert set, and a detector
  that cannot separate a spike from a level shift is unfit for the OBSERVE layer, because
  the layer's output is read as "this company's activity level changed".
- **Why it matters.** Every false "sustained change" alert costs credibility; the
  cheapest fix (require persistence) has a measurable delay cost that the design does not
  currently price.
- **Operational estimand.** s = share of alerts classified as single-month spikes by a
  pre-registered rule (the count returns below the alert threshold for at least two
  consecutive months within three months of the alert); Δalerts and ΔD50 from imposing a
  two-consecutive-month persistence rule.
- **Prediction.** s ≥ 0.35 on ARM-3 and on ARM-2's spike class; the persistence rule cuts
  alerts by ≥50% and costs ≤1 month of D50 on ARM-1 and ≤2 months on short ramps.
- **Test procedure.** Classify alerts with the rule above using only the three months
  after the alert; recompute the alert set with and without persistence; report both
  metrics and the MC intervals.
- **Falsification / kill condition.** **REJECTED** in either direction: (a) if s < 0.15,
  the spike problem is not operational and the "unfit" clause is rejected; (b) if the
  persistence rule costs >3 months of D50 or removes >20% of true detections, then the
  rule is worse than the problem it solves and the claim fails as an operational
  recommendation.
- **Confounders / threats.** The spike/level-shift classification uses future data, so it
  is an *evaluative* classification, not an online detector output — it must not be
  presented as a detector feature. Spikes in S-LO streams are indistinguishable from
  Poisson noise; report s by stratum.
- **Status:** `UNTESTED`. **Evidence pointer:** ARM-2/3 alert tables.

## H-D5 — Performance degrades measurably under realistic data-quality perturbations (h5)

- **Claim.** Detection performance degrades measurably, in a predictable direction, under
  realistic data-quality perturbations of this lane.
- **Why it matters.** The design's guards "check" data quality; they do not price it.
  These four perturbations are all present in real form in this lane (see design review
  §3), so the numbers decide whether the OBSERVE layer can run on the live end of the
  series at all.
- **Operational estimand.** Change in D50 (months) and in alerts per stream-year for each
  perturbation relative to the clean arm, per stratum.
- **Prediction (direction and rough magnitude, stated in advance).**
  1. A 2-month publication lag on the final two months increases D50 by ≥2 months and
     makes alerts in those months impossible — the mechanism is truncation, not detection.
  2. One month with a 50% panel-wide volume collapse (the observed shape of 2026-10:
     139 material events against a 263 mean, i.e. 52.8% of the mean) multiplies alerts in
     that month by ≥5 on S-HI, and ≥50% of those alerts are not reproducible one month
     later.
  3. Random deletion of 10% of events changes the alert count by <15% and D50 by <1 month
     — variance, not bias.
  4. A rename discontinuity (one stream split at a random month into an "old applicant
     string" stream carrying 60% of events and a "new string" stream carrying 40%) makes
     the naive detector produce a spurious down-step and up-step pair at the split month
     with probability ≥0.5.
- **Test procedure.** Apply each perturbation to ARM-1 replicates with common random
  numbers; recompute; report paired differences.
- **Falsification / kill condition.** **REJECTED** if any perturbation with a predicted
  magnitude misses by more than a factor of two, or if (3) exceeds its predicted bound.
  A detector suite that is insensitive to all four is not "robust" — it is not measuring
  the data-quality channel at all, which would contradict the measured calendar and
  boundary effects (design review §3.4) and, in the all-events frame, the dispersion
  evidence (median variance/mean 1.36, 90th percentile 3.02 among the 95 largest
  streams; the material-only frame is milder, 1.11 / 1.40), and would have to be
  explained.
- **Confounders / threats.** The perturbations are our inventions and may be unrealistic.
  That is why every prediction is directional and numeric *before* the run, and why the
  observed artifacts in §3 are used as the calibration for magnitudes rather than
  invented ones.
- **Status:** `UNTESTED`. **Evidence pointer:** perturbation arm.

## H-D6 — FDR control cuts alert volume substantially while preserving confirmed changes (h6)

- **Claim.** Benjamini–Hochberg at q = 0.10, applied across tested cells within a month,
  reduces the reported alert count by a large margin relative to unadjusted per-cell
  nominal tests, while retaining most alerts that are later confirmed — i.e. the alerts
  removed are mostly the ones an analyst would not have acted on.
- **Why it matters.** The alert-fatigue literature (review, cluster 6) says the value of
  the channel collapses when precision falls below what the recipient can triage. If FDR
  control also discards real changes, then the layer has a precision/recall problem no
  multiplicity correction can solve and must be redesigned.
- **Operational estimand.** Alert count before/after multiplicity control; confirmed
  alert count before/after (confirmation per H-D3's pre-registered rule);
  confirmed/alerts ratio.
- **Prediction.** Alert count falls by ≥60%; confirmed count falls by <25%;
  confirmed/alerts ratio rises by ≥1.5×. The Benjamini–Yekutieli variant at q = 0.10 is
  the pre-declared sensitivity analysis and is expected to retain fewer alerts but keep
  the same qualitative ordering.
- **Test procedure.** One look across all cells (not a re-run per month, which would
  address a different, time-wise family); report both BH and BY; report the dependence
  argument for BH explicitly (literature review entry 13).
- **Falsification / kill condition.** **REJECTED** if (a) the confirmed count falls by
  ≥50% (FDR is discarding real change at this sparsity — the wrong instrument), or
  (b) the alert reduction is <20% (FDR is too weak to matter at this sparsity).
- **Confounders / threats.** H-D3 being `BLOCKED` makes the "confirmed" count
  unavailable; the card is then only testable conditionally, and that must be stated in
  any report rather than silently substituting an alert-count proxy. Dependence across
  cells (shared monthly volume, shared taxonomy) means BH's guarantee is the PRDS one and
  BY is the valid fallback.
- **Status:** `UNTESTED`; conditional on H-D3. **Evidence pointer:** ARM-3 alert table.

## H-D7 — The real-data alert set is dominated by the boundary month and by panel-wide volume (h7, extra)

- **Claim.** On ARM-3 at FAR\*, a large share of alerts is produced by the two structural
  features of the lane rather than by firm-level change: the truncated final month and
  months in which the whole panel's volume dropped.
- **Why it matters.** If true, the first thing the OBSERVE layer would report is an
  artifact of when the snapshot was taken, and the benchmark's "false alarms per
  stream-year" would be measured under a clean null that the real data never satisfies.
- **Operational estimand.** b = share of alerts falling in the final two available months
  (2026-09, 2026-10) or in a month whose panel-wide material volume is ≥25% below its
  trailing-12-month median; Δalerts and Δconfirmed from excluding those months and
  requiring a two-month stabilisation delay.
- **Prediction.** b ≥ 0.40; excluding those months removes ≥60% of alerts and <15% of
  confirmed alerts.
- **Measured motivation (facts, not predictions — see design review §3.4–3.5).** The
  material lane's last month has 139 events against a 263.0 mean (52.8%); among the 89
  largest mapped material streams the aggregate last-month count is 0.36× their own
  preceding 12-month mean; January material-lane volume averages 14.4% below other
  months (21.7% below in the all-events lane); 2025-11 runs at 79.5% of the material-lane
  material-lane mean with the PMA lane at 80 events against 218–227 in the adjacent
  months.
- **Test procedure.** Census the ARM-3 alert set by month and against panel-wide volume;
  recompute with the months excluded; report the confirmed counts under both.
- **Falsification / kill condition.** **REJECTED** if b < 0.15 (the artifact worry is
  falsified and the design may run on the raw end of the series), or if excluding those
  months removes ≥40% of confirmed alerts (the "artifacts" are carrying real signal, and
  the exclusion rule is wrong).
- **Confounders / threats.** The 25%-below-trailing-median definition is a threshold
  chosen now; it is fixed and applies to the panel total, not to the stream, so it cannot
  be tuned to a detector.
- **Status:** `UNTESTED`. **Evidence pointer:** ARM-3 census.

---

## Cycle-level kill conditions (these are not per-card; any one invalidates the whole comparison)

1. **No ARM-0.** If the false-alarm axis is not calibrated on real streams, every
   "matched FAR" statement is a statement about the Poisson assumption and the comparison
   is unidentifiable.
2. **Guard thresholds chosen after seeing which streams separate the detectors.** The
   minimum-events guards must be fixed and their sensitivity reported (S-HI / S-MID /
   S-LO are fixed above).
3. **One replicate per cell.** At S-HI n ≈ 30–40, a single-replicate detection
   probability has a binomial standard error of roughly 9 percentage points; without
   common random numbers and ≥100 replicates, the entire detector ranking is inside the
   noise and no verdict may be issued.
4. **A detector given knowledge the others are not** (known baseline, known magnitude,
   known onset) or a baseline fitted across the injected segment.
5. **Confirmation counted from a same-system source** (the PMA lane split) and reported
   as independent confirmation.
6. **A verdict reported for S-LO**, or a headline number pooled across strata without the
   stratum breakdown.

## What is deliberately *not* in these cards

- No card on cross-company contagion or sector-wide trend (different question, not in the
  pre-registered design).
- No card on the strategic importance of a detected change — that is an Understand-layer
  judgement, and the detection layer must not be allowed to imply it.
- No card on forecasting. These cards test the reality of a detection, not the
  predictability of the future; the Anticipate programme is frozen at P3
  (`DECISIONS.md` D-012).

## Change log

- 2026-11-02 — cards created before any detector or benchmark number existed. No
  revisions since.
