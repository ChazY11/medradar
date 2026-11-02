# Cycle 3 — OBSERVE layer: change detection (2026-11-02)

**Status:** completed, pre-registered analysis run. **Branch:** `research/change-detection-v1`.
**Full report:** [`experiments/detect_v1/REPORT.md`](../../experiments/detect_v1/REPORT.md) —
generated from artifacts by `write_report.py`, no hand-typed numbers.
**Pre-registered design:** [`../DECISIONS.md`](../DECISIONS.md) D-013, amended D-014, corrected
D-015/D-016.

## The question

The mission is now Observe → Understand → Anticipate. The OBSERVE layer needs one thing first:
**can a real change in a company's rate of technology activity be detected, early, without
drowning the analyst in false alarms — and can it be distinguished from product refresh, data
noise and taxonomy churn?**

## What was built

1. `medradar/intelligence/changepoint.py` — four detectors on sparse monthly count streams:
   naive rate multiplier (baseline comparator), rolling z-score, Poisson CUSUM, Poisson Bayes
   factor. Pure stdlib, deterministic, 44 tests.
2. `experiments/detect_v1/` — a controlled-truth benchmark with real monthly stream shapes,
   Poisson-redrawn injections, a by-entity split, an **FPR–detection frontier** instead of a
   single hidden threshold, and **paired entity-clustered inference** (every detector scores the
   identical injected series).
3. Noise controls: a track-assignment provenance audit, a product-code reassignment audit, a
   deterministic-track-only sensitivity panel, exclusion of the partial final month, and a
   zero-baseline guard.

## Outcome

**The simple baseline is not beaten.** At a matched 2 % false-alarm budget on the primary panel,
the naive rate-multiplier detects 0.223 of injected shifts against 0.181 (CUSUM), 0.122 (Bayes
factor) and 0.112 (z-score). Paired entity-clustered differences are **negative and exclude zero**
(Bayes factor −0.101 [−0.134, −0.067]; CUSUM −0.042; z-score −0.111).

The one exception: on the **deterministic-track-only** panel the Bayes factor is ahead
(+0.039 [+0.003, +0.071]). It is the only case in three granularities where a likelihood detector
wins, so the evidence does not support preferring a likelihood detector.

**Absolute detection is low.** Even the best detector catches ~22 % of injected shifts overall and
about half of 5× shifts, with a median delay of one to five months. A 2× change is effectively
undetectable at any honest budget. The binding constraint is **data density** (~0.2 material
events per cell-month; 25 events per cell-decade), not the algorithm.

## Negative and blocked results

- **Poisson CUSUM, the textbook choice, is not usable** at an honest budget (needs threshold 40;
  at looser thresholds it reaches ~51 % detection but alarms on ~45 % of clean streams).
- **The spike-versus-level-shift test is inconclusive**: at this density an injected one-month
  spike usually adds zero or one event, so the injection cannot discriminate. Backlog B-026.
- **The independence/confirmation test is blocked, not answered**: the two regulatory pathways
  share one filing system, procurement rows are undated with `pit_usable=0`, publication counts are
  annual and cover 51 entities, and there is no trials table. Marked BLOCKED by the design review
  and recorded as such rather than reported as a null.
- **The novelty confirmation signature failed**: post-alert new-product-code share is zero in both
  alerted and control cells because most cells use one or two codes.
- **Real-data alert volume is tiny** (0–2 alarms over 104 cells) — a needle-finder, not a
  monitoring feed.
- **Harness defects found and fixed mid-cycle**: an unreachable false-alarm target (D-015), an
  unstable single-point calibration, and a partial final month (D-016). Superseded numbers are
  recorded in those decisions and never cited.

## What cycle 3 changes for the programme

1. The OBSERVE layer now has a **working, honest instrument** and a measured operating
   characteristic: at a 2 % alarm budget it can confirm large sustained increases in the densest
   cells and cannot see small ones.
2. **Detector sophistication is not the lever; data density is.** The next OBSERVE investments
   should be coverage (hiring, patents, 8-K CIK linking) and coarser/denser aggregation
   (quarterly), not another algorithm.
3. The claim "detected a technology change" now requires evidence beyond a rate shift — a
   taxonomy-churn check, a Special-510(k) filter, and an independent source that does not yet
   exist. That is the Understand layer's entry condition.
