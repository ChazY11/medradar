# EVENT-SEQUENCE DETECTION — Phase 1D (controlled truth)

Cells: 16 · multipliers (2.0, 3.0) · 200 replications each · change at 60% of the sequence · seed 4242.

**Verdict:** m=2.0: A 185.5 d vs B 48.5 d, power 0.762 vs 0.333, paired median difference 133.9 [71.5, 165.2] (B earlier than A (fine unit is slower)); m=3.0: A 88.7 d vs B 56.0 d, power 0.906 vs 0.466, paired median difference 32.7 [23.9, 60.9] (B earlier than A (fine unit is slower))

## Pooled

| multiplier | cells | power A (interval LR) | power B (quarterly z) | median delay A (d) | median delay B (d) | paired median diff [95% CI] |
|---|---:|---:|---:|---:|---:|---|
| 2.0 | 16 | 0.762 | 0.333 | 185.5 | 48.5 | 133.9 [71.5, 165.2] |
| 3.0 | 16 | 0.906 | 0.466 | 88.7 | 56.0 | 32.7 [23.9, 60.9] |

## Per cell (m = 2)

| cell | events | power A | power B | delay A (d) | delay B (d) | FAR A | FAR B |
|---|---:|---:|---:|---:|---:|---:|---:|
| ge_healthcare|imaging_mr_ct | 127 | 0.9 | 0.73 | 185.5 | 47.1 | 0.1 | 0.0 |
| medtronic|cardiac_rhythm | 2459 | 0.85 | 0.0 | 140.5 | None | 0.1 | 0.0 |
| medtronic|diabetes_cgm | 141 | 0.44 | 0.225 | 175.5 | 516.1 | 0.1 | 0.09 |
| medtronic|insulin_delivery | 252 | 0.48 | 0.135 | 120.0 | 48.5 | 0.095 | 0.08 |
| philips|imaging_mr_ct | 112 | 0.895 | 0.33 | 210.5 | 45.3 | 0.1 | 0.0 |
| ge_healthcare|imaging_us | 85 | 0.625 | 0.33 | 303.5 | 53.1 | 0.095 | 0.055 |
| medtronic|coronary | 146 | 0.745 | 0.435 | 207.0 | 113.2 | 0.095 | 0.025 |
| medtronic|ep_pfa | 211 | 1.0 | 0.09 | 149.5 | 92.4 | 0.1 | 0.0 |
| medtronic|heart_failure | 137 | 0.78 | 0.43 | 280.0 | 140.2 | 0.095 | 0.0 |
| medtronic|neurostimulation | 516 | 1.0 | 0.61 | 152.0 | 18.1 | 0.1 | 0.0 |
| medtronic|neurovascular | 147 | 0.77 | 0.47 | 248.0 | 30.5 | 0.095 | 0.02 |
| medtronic|peripheral_vascular | 212 | 0.59 | 0.08 | 202.5 | 19.4 | 0.1 | 0.0 |
| medtronic|spine | 68 | 0.665 | 0.335 | 68.5 | 285.6 | 0.1 | 0.07 |
| medtronic|structural_heart | 360 | 0.885 | 0.19 | 136.5 | 41.3 | 0.1 | 0.065 |
| medtronic|urology | 406 | 1.0 | 0.435 | 316.0 | 40.1 | 0.1 | 0.025 |
| philips|cardiac_rhythm | 47 | 0.57 | 0.5 | 135.0 | 57.6 | 0.045 | 0.035 |

## Not claimed

- the truth is synthetic: this measures detector geometry, not whether real technology shifts exist
- no lead-time claim relative to real milestones (G1)
- no causal, intent or R&D claim
