# PHASE 1C PROTOCOL — expanded concurrent detection with pre-registered multiplicity control

**Status:** FROZEN before `CONCURRENT_DETECTION_EXPANDED.json` existed · **Supersedes:** the cell set of
`PHASE1B_PROTOCOL.md` (which covered only two tracks and was underpowered — `STUDY_DECISIONS.md` S-010)

> The cell set below was chosen from **coverage only** (`CELL_INVENTORY.json`: event counts and quarters with
> activity per stream). No onset count, alert or detection result was computed before this protocol was written.
> That ordering is the anti-cherry-picking guarantee, and it is auditable: `CELL_INVENTORY.json` contains no outcome
> quantities by construction.

---

## 1. Question

Same as O1: **at an equal false-alarm budget, does adding a second recording stream (recalls) improve detection of
sustained technology-activity changes over the regulatory stream alone?** Lead time is not claimed (G1 closed it).

H1 (fusion advantage) vs H1₀ (no difference). H2–H4 remain untested.

## 2. Cell set (frozen from coverage)

**Primary set — both streams above the frozen floors** (≥40 observations and ≥12 quarters with observation each,
2017–2025): **5 cells**

| company | track | regulatory | recall |
|---|---|---:|---:|
| GE HealthCare | `imaging_mr_ct` | 127 obs / 36 q | 389 obs / 33 q |
| Medtronic | `cardiac_rhythm` | 2,459 / 36 | 224 / 24 |
| Medtronic | `diabetes_cgm` | 141 / 24 | 49 / 13 |
| Medtronic | `insulin_delivery` | 252 / 33 | 40 / 14 |
| Philips | `imaging_mr_ct` | 112 / 33 | 759 / 35 |

**Secondary set — regulatory stream only** (single-source power check, 11 cells): GE `imaging_us`; Medtronic
`coronary`, `ep_pfa`, `heart_failure`, `neurostimulation`, `neurovascular`, `peripheral_vascular`, `spine`,
`structural_heart`, `urology`; Philips `cardiac_rhythm`.

Cells outside these lists are excluded. Adding a cell after seeing results is a protocol violation.

## 3. Positive, detection window, models

Unchanged from `PHASE1B_PROTOCOL.md`: sustained onset = ≥2 regulatory events within 4 quarters after ≥12 months of
silence; an alert at q or q+1 counts as concurrent detection; M0 persistence, M1 regulatory z, M2 recall z, M5
equal-FAR max fusion; thresholds calibrated on 2017–2021 to the budget and applied unchanged to 2022–2025.

**Budget:** 2 false alerts per company-year, per cell.

## 4. Multiplicity control (pre-registered)

Three fusion-vs-single comparisons (M5 vs M0, M1, M2). For each comparison:

1. compute per-cell recall difference (fusion − single) over cells where both models are calibrated;
2. **sign test** on the per-cell differences (cells with equal recalls are dropped and the drop is reported);
3. **Holm–Bonferroni** adjustment across the three comparisons at family-wise α = 0.05;
4. require the pooled recall difference to be **≥ +0.10** in the same direction.

**H1 is supported** only if at least one comparison passes all four steps *and* the underpowered clause is satisfied.
Anything else is reported as "not supported by this data", never as "falsified".

## 5. Underpowered clause (frozen)

If the evaluation window contains **<10 onsets across the primary set**, no comparison may be interpreted as support
or refutation of H1; results are descriptive and the verdict must say so.

## 6. Reporting

Per-cell and pooled tables for both sets; onsets, censored episodes, alerts, hits, false alerts, recall with Wilson
interval, precision, FAR per company-year, calibration thresholds, sign-test p-values, Holm-adjusted p-values, and the
number of cells dropped from each comparison. `NOT_EVALUABLE` where a model cannot reach the budget.

## 7. Leak audit

Every feature at decision time q−1 uses only events visible (`event_date` + declared lag) by the real last day of
q−1. The audit recomputes this over all included cells and **must report 0 violations**; a non-zero count aborts the
run before any result is written.

## 8. What the expanded design still cannot say

- Nothing about lead time (G1).
- Nothing about Dräger (no cell passes any floor).
- Nothing causal; recalls share the regulator with clearances, so independence is **partial** and must be stated
  wherever fusion is discussed.
- Nothing about firms not in the five-firm set.

## 9. Human sign-off

| item | status |
|---|---|
| Expanded cell set and the coverage-only selection rule | **PENDING_HUMAN_REVIEW** |
| Sign test + Holm procedure as the multiplicity control | **PENDING_HUMAN_REVIEW** |
| Any H1 statement | **PENDING_HUMAN_REVIEW** |
