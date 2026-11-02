# PHASE 1B PROTOCOL — concurrent multi-source change detection (study O1)

**Status:** FROZEN before `CONCURRENT_DETECTION.json` existed · **Study:** `early_signal_5firms` ·
**Supersedes for O1:** nothing (it amends only the positive definition and drops lead time, which G1 found
unmeasurable — `PHASE1_SHRINKAGE.md`)

> Lead time is **not** claimed in O1. The question is narrower and answerable on this corpus: *at a fixed false-alarm
> budget, does adding a second recording stream detect a sustained change in a firm's technology activity more
> reliably than the regulatory stream alone?*

---

## 1. Question and hypotheses

**RQ (O1):** at an equal false-alarm budget, does a multi-source detector recall sustained technology changes better
than the single regulatory stream?

- **H1 (fusion advantage):** fusion recall − best single-stream recall > 0, with the difference's interval excluding 0.
- **H1₀ (null):** no difference beyond sampling noise.

H2–H4 from `PROTOCOL.md` are not tested here; H2 (lead time) is unmeasurable on this corpus and stays closed.

## 2. Positive definition (amended, frozen now)

A **sustained change onset** is a firm × track quarter **q** such that:

1. the firm has **no regulatory event** (510(k) or PMA) in that track during the 12 months before q;
2. q is the **first** quarter of an episode containing **≥ 2 regulatory events within q … q+3**;
3. q lies inside the evaluation window and its 4-quarter maturation window is complete (otherwise **censored**, and
   censored quarters are excluded from positives *and* reported).

A single clearance is **not** a positive. This is the direct consequence of `PILOT_RESULTS.md` §5: a rate-anomaly
detector cannot detect a one-event entry, so the earlier target was a specification mismatch.

**Negative quarters:** firm-track quarters inside the window that are not onsets, with a usable baseline
(≥ 8 prior quarters) and not inside the 4-quarter maturation window of an onset.

## 3. Detection rule and window

- Decision is taken at the **end of quarter q−1**; an alert **at q** or **q+1** counts as concurrent detection of an
  onset at q (concurrent, not early — no lead-time claim).
- An alert with no onset within [q, q+1] is a **false alert**.

## 4. Models (fixed order, none tuned per company)

| id | signal | definition |
|---|---|---|
| **M0** | persistence | alert if the current quarter's count exceeds the maximum of the previous 8 quarters |
| **M1** | regulatory rate anomaly | quarterly rolling z-score on 510(k)+PMA counts, 8-quarter baseline, threshold calibrated to the budget |
| **M2** | recall-stream anomaly | the same detector on device **recall** counts in the same firm-track (a different recording process, same regulator) |
| **M5** | fusion | alert if `max(z_regulatory, z_recall)` exceeds one calibrated threshold (equal-FAR fusion, not a union of separately-tuned alerts) |

Thresholds are **calibrated once on the calibration window (2018–2021)** to the declared budget and then applied
unchanged to the evaluation window (2022–2025). Per-company tuning is forbidden.

## 5. Metrics and budget

- **Primary false-alarm budget:** **2 false alerts per company-year**, achieved by threshold calibration on the
  calibration window.
- Reported: recall at the budget (with Wilson interval), false alerts per company-year, precision, per-cell results,
  number of positives, censored onsets, and each model's alert count.
- **Underpowered clause:** if the evaluation window contains **fewer than 10 onsets**, no model comparison may be
  stated as support or refutation of H1; results are reported as descriptive with the count and the interval.
- **Multiplicity:** 4 models are compared; the H1 decision requires the paired difference's interval to exclude 0 and
  a Holm adjustment across the three fusion-vs-single comparisons (M5 vs M0, M1, M2).

## 6. Rolling-origin design and leak audit

- Origins: every evaluation quarter q with a complete 8-quarter baseline and complete maturation.
- **Leak rule:** every feature at decision time q−1 uses only events whose availability (`event_date` + declared lag;
  the store's Tier B) is ≤ end of q−1. Recomputed independently by the leak audit; any violation aborts the run.
- No sampling randomness in this study; results must be reproducible by re-running the script.

## 7. Stop conditions

1. **Underpowered** (<10 onsets): report descriptively, do not claim H1 support or refutation, stop model expansion.
2. **Leak violations > 0:** abort and fix before reporting anything.
3. If the calibration window cannot reach the budget for a model (e.g. it never alerts), that model is reported as
   `NOT_EVALUABLE`, never given a synthetic threshold.

## 8. What O1 cannot say

- Nothing about lead time, earlier warning, or how early anything is visible (G1 closed that).
- Nothing about firm-level or global technology strategy; the unit is a firm-track activity change.
- Nothing about Dräger (no evaluable cell).
- Nothing about causality, intent or R&D.

## 9. Human sign-off

| item | status |
|---|---|
| Amended positive definition and evaluation window split (2018–2021 / 2022–2025) | **PENDING_HUMAN_REVIEW** |
| Treating recalls as a second stream (same regulator, different recording process) | **PENDING_HUMAN_REVIEW** |
| Any eventual H1 statement | **PENDING_HUMAN_REVIEW** |
