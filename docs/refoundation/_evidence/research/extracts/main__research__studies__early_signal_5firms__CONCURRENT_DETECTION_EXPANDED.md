# CONCURRENT DETECTION (EXPANDED) — pre-registered multiplicity control

Primary set: **5** both-stream cells · secondary: 11 regulatory-only cells · budget 2.0 false alerts/company-year · leak audit **0** violations.

**Verdict:** UNDERPOWERED — 0 onset(s) in the primary evaluation set (floor 10). H1 is neither supported nor refuted; results are descriptive.

Primary evaluation onsets: **0**

## Pooled, primary set

| model | cells | alerts | hits | false | recall [95% CI] | precision | FAR/cy |
|---|---:|---:|---:|---:|---|---:|---:|
| m0_persistence | 5 | 7 | 0 | 7 | None None | 0.0 | 0.35 |
| m1_regulatory_z | 5 | 9 | 0 | 9 | None None | 0.0 | 0.45 |
| m2_recall_z | 5 | 8 | 0 | 8 | None None | 0.0 | 0.4 |
| m5_fused | 5 | 8 | 0 | 8 | None None | 0.0 | 0.4 |

## Fusion vs single (pre-registered sign test + Holm)

| comparison | cells | + | − | ties | sign-test p | Holm p | reject |
|---|---:|---:|---:|---:|---:|---:|---|
| M5 vs m0_persistence | 0 | 0 | 0 | 0 | 1.0 | 1.0 | no |
| M5 vs m1_regulatory_z | 0 | 0 | 0 | 0 | 1.0 | 1.0 | no |
| M5 vs m2_recall_z | 0 | 0 | 0 | 0 | 1.0 | 1.0 | no |

## Per cell (primary)

| cell | onsets (eval) | censored | M1 recall | M2 recall | M5 recall |
|---|---:|---:|---:|---:|---:|
| ge_healthcare\|imaging_mr_ct | 0 | 3 | None | None | None |
| medtronic\|cardiac_rhythm | 0 | 3 | None | None | None |
| medtronic\|diabetes_cgm | 0 | 3 | None | None | None |
| medtronic\|insulin_delivery | 0 | 3 | None | None | None |
| philips\|imaging_mr_ct | 0 | 3 | None | None | None |

## Decision steps

- underpowered_clause_satisfied: False
- pooled_difference_at_least_0.10: False
- any_comparison_passes_holm: False

## Not claimed

- no lead-time statement (G1 closed it)
- recalls share the regulator with clearances: independence is partial
- no causal, intent or R&D claim
- H2-H4 untested
