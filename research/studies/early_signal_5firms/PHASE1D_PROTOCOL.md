# PHASE 1D PROTOCOL — event-level point-process detection under controlled truth

**Status:** FROZEN before any injection or detection result existed · **Study:** `early_signal_5firms` ·
**Supersedes:** nothing; it answers the open question left by `PHASE1_SHRINKAGE.md` §5 (option O4/ (a) "change the unit")

> The quarterly unit failed not because the detectors were weak but because the positive class was empty
> (`ONSET_LADDER.json`: 1 qualifying quarter in 16 cells over nine years). This protocol therefore **abandons
> observed labels** and uses **controlled truth**: real inter-event structure, with a known rate change injected.
> That answers a different and answerable question — *does the finer unit detect a rate change earlier than coarse
> counting?* It does **not** answer whether real technology shifts exist.

---

## 1. Question

**RQ (1D):** at an equal false-alarm budget, does a point-process detector on event intervals detect a known filing-rate
change **earlier** (and/or more often) than the deployed quarterly count detector?

- **H1D:** the interval detector has a shorter median detection delay at equal false-alarm rate.
- **H1D₀:** no difference beyond simulation noise.

## 2. Unit and data

- One sequence per firm × track cell: the **regulatory stream** (510(k) + PMA), dated by
  `available_at = event_date + 30 days` (Tier B, as audited).
- Cells: exactly the 16 from `CELL_INVENTORY.json` (5 both-stream + 11 regulatory-only). No cell may be added after
  seeing results.
- Only cells with **≥ 20 events in 2017–2025** are evaluable for delay measurement; smaller cells are reported as
  `INSUFFICIENT_EVENTS` rather than silently dropped.

## 3. Controlled truth (pre-registered injection)

- **Rate multiplier** m ∈ {2, 3}: after a change point, intervals are **compressed by 1/m** (rate increased m-fold),
  preserving the empirical interval structure rather than assuming exponentiality.
- **Change position:** the event index at **60 % of the sequence** (rounded down), so at least 20 % of events remain
  after the change for delay measurement.
- **Replications:** 200 injections per cell per multiplier, with the interval set rotated by a seeded offset so the
  same intervals are not always used in the same order. Seed **4242**.
- A cell is **evaluable** for a multiplier only if it has ≥ 8 events before and ≥ 5 after the injection point.

## 4. Detectors

**A — interval likelihood ratio (point process).** For a homogeneous Poisson process on [0, T] with n events, the
profile-likelihood ratio for a rate change at time t splits the count into k before t and n−k after:

  LR(t) = 2 [ k·ln(λ₁/λ₀) + (n−k)·ln(λ₂/λ₀) ],  λ₁ = k/t, λ₂ = (n−k)/(T−t), λ₀ = n/T

The statistic is the **maximum over candidate cut points** (each event time in the middle 20 %–90 % of the sequence).
Threshold is calibrated by **parametric null simulation**: 20,000 homogeneous Poisson samples with the same (n, T),
threshold chosen so the per-sequence false-alarm probability equals the declared budget.

**B — quarterly count z-score (deployed style).** Quarterly counts over the same span, rolling z against the previous
8 quarters, the programme's validated threshold 3.5, evaluated at each quarter boundary; delay measured to the first
quarter end after the change.

## 5. Budget, metrics, and the comparison

- **Primary false-alarm budget:** 0.10 false alarms per detector-run (one per ten runs), calibrated separately for
  each detector so that both are compared **at the same budget**.
- Reported per cell and pooled: injection power (detected within the observed window), median and quartiles of
  detection delay **in days**, delay **in events**, and the number of non-detections.
- **Headline comparison:** pooled median delay A vs B, with a paired bootstrap over cells (2,000 resamples, seed 7).
- **Underpowered clause:** if fewer than 8 cells are evaluable at a given multiplier, the comparison is descriptive
  and no H1D statement is made.

## 6. Leak audit

The injected change is the only truth used. Every detector input must be derived from the sequence strictly before the
detection time; the audit recomputes, for each detection, the timestamp of the last datum used and asserts it is ≤ the
detection time. **Any violation aborts the run.**

## 7. What this design cannot say

- Nothing about real technology shifts: the truth is synthetic, so the result is about **detector geometry**, not about
  the world.
- Nothing about lead time before real milestones (G1 closed that).
- It cannot rescue the empty positive class: if real changes do not occur, a better detector still detects nothing.
- The exponential model is a working approximation; the injection preserves empirical structure but the detector
  assumes Poisson, and that mismatch is part of what is being measured.

## 8. Human sign-off

| item | status |
|---|---|
| Injection design (position 60 %, multipliers 2 and 3, 200 reps) | **PENDING_HUMAN_REVIEW** |
| Equal-budget comparison (0.10 per run for both detectors) | **PENDING_HUMAN_REVIEW** |
| Any H1D statement | **PENDING_HUMAN_REVIEW** |
