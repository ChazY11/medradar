# CONCURRENT DETECTION — O1 (sustained changes, equal-FAR fusion)

Calibration 2017-Q1 … 2021-Q4 · evaluation 2022-Q1 … 2025-Q4 · budget 2.0 false alerts per company-year · protocol frozen before the run.

**Verdict:** UNDERPOWERED — 1 onset(s) in the evaluation window (floor 10). No model comparison may be stated as support or refutation of H1; results are descriptive only.

Evaluation onsets: **1** across 6 cells (24.0 company-years). Leak audit: **0** violations.

## Pooled

| model | cells | alerts | hits | false | recall [95% CI] | precision | FAR/company-year |
|---|---:|---:|---:|---:|---|---:|---:|
| m0_persistence | 5 | 3 | 1 | 2 | 1.0 [0.207, 1.0] | 0.333 | 0.083 |
| m1_regulatory_z | 5 | 5 | 1 | 4 | 1.0 [0.207, 1.0] | 0.2 | 0.167 |
| m2_recall_z | 5 | 10 | 0 | 10 | 0.0 [0.0, 0.793] | 0.0 | 0.417 |
| m5_fused | 6 | 10 | 1 | 9 | 1.0 [0.207, 1.0] | 0.1 | 0.375 |

## Per cell

| cell | reg events | recall events | onsets (eval) | censored | M1 recall | M5 recall |
|---|---:|---:|---:|---:|---:|---:|
| ge_healthcare|imaging_us | 97 | 34 | 0 | 3 | None | None |
| mindray|imaging_us | 59 | 1 | 0 | 3 | None | None |
| philips|imaging_us | 41 | 113 | 0 | 3 | None | None |
| ge_healthcare|respiratory | 3 | 74 | 0 | 3 | None | None |
| medtronic|respiratory | 7 | 39 | 1 | 3 | 1.0 | 1.0 |
| philips|respiratory | 1 | 86 | 0 | 1 | NOT_EVALUABLE | None |

## Not claimed

- no lead-time statement: G1 closed that question (PHASE1_SHRINKAGE.md)
- no causal, intent or R&D claim; the unit is public filing activity
- recalls are a different recording process but the same regulator: independence is partial and is stated as such
