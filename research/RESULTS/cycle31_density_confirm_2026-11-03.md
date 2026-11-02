# Cycle 31 — density scaling confirmed on fresh draws, and the product stops over-labelling ramps (2026-11-03)

**Status:** completed. Closes B-064. Pre-registered in D-060, outcome in D-061.
Artifacts: `experiments/b026/density_confirm.py`, `density_confirm.json`, `density_confirm.log`;
`medradar/intelligence/promotion.py` (policy v2), `tests/test_promotion.py` (28 tests).

## What ran

The D-060 design: same 38 dense track series and five thinning factors, but **entirely fresh draws** — thinning
seed 7171, origins 8181, bootstrap 9191 — and a criterion fixed before looking (rank correlation ≥ 0.8 **and**
dense ramp recall ≥ 2× sparse; strict monotonicity dropped because D-059 showed it was the brittle part).

## Result: CONFIRMED

| τ | density (events/series-month) | ramp recall | 95 % CI | precision |
|---:|---:|---:|---|---:|
| 1 | 4.16 | **0.444** | 0.333–0.560 | 0.909 |
| 2 | 2.06 | 0.402 | 0.280–0.525 | 0.922 |
| 5 | 0.84 | 0.321 | 0.218–0.432 | 0.884 |
| 10 | 0.42 | 0.214 | 0.114–0.328 | 0.867 |
| 20 | 0.22 | **0.204** | 0.111–0.300 | 0.890 |

Rank correlation **0.908** (floor 0.8), dense/sparse ratio **2.18×** (floor 2.0). The ordering also came out
monotone, though the criterion no longer requires it.

**Stated with its history:** the first controlled test failed a stricter gate, the gate was recorded as the
defect, and the revised criterion was confirmed out of sample. Weaker than a first-pass confirmation, stronger
than an exploratory finding — and the paper says exactly that.

## The product consequence (the real output of this cycle)

The policy was still calling Medtronic's `insulin_delivery` alert a **ramp** — in a company cell carrying about
**0.08 events per month**, where measured ramp recall is 0.14. That label was unjustified.

**Policy v2** therefore adds a reporting rule: if the classifier says *ramp* but the cell's baseline rate is below
**1.0 event per month**, the shape is reported as **`sustained_unresolved`** with the reason attached. The alert
stays **promotable** — the binary spike-versus-sustained decision is unaffected and remains confirmed at these
densities. Three tests cover the relabelling, including that the floor is per month, not per quarter.

The profile now prints:

```
promotion: promote_pending_signoff — shape sustained_unresolved (post-alert rate is elevated and
still rising, but this cell carries 0.08 events per month, below the 1/month floor at which ramps are
recoverable (D-061); the shape stays unresolved)
```

## Not claimed

That the scaling generalises beyond binomial thinning of this taxonomy; that 1.0/month is an optimal floor (it is
a conservative choice consistent with the measured curve, not a fitted threshold); or that any ramp above the
floor is technological.

## Verification

- `density_confirm.py` → exit 0, 2.5 s, deterministic (seeds 7171/8181/9191).
- `pytest tests/test_promotion.py` → **28 passed**.
- `selfcheck.py` → 5/5 profiles, 5/5 snapshots (the frozen snapshots keep their v1 labels, as history should).
- `verify_claims.py` → **78/78**.
- `python -m medradar selftest` → 892 tests OK (skipped=3).

## Next

1. Freeze a snapshot under policy v2 so the label change enters the point-in-time chain.
2. Wire the audit into the round-end routine.
3. Consider a second paper focused on the measurement rules and the density confirmation.
