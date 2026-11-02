# Cycle 21 — deployment resolution: quarterly, one detector at that resolution, none identifiable across resolutions (2026-11-03)

**Status:** completed. Closes B-039. Pre-registered in D-044, outcome in D-045.
Artifacts: `experiments/b039/deployment_resolution.py`, `deployment_resolution.json`, `deployment.log`.

## The decision

The OBSERVE layer operates at **3 months (quarterly)**, justified by the decision cadence it serves
(quarterly portfolio reviews, analyst re-forecasting) and by the measured fact that monthly resolution leaves
~0.2 events per cell-month where detectors cannot resolve a change. Detector memory was already in calendar
months (D-020), so the sweep read here is the corrected one.

## At the deployment resolution (2 % false-alarm budget, 224 trials each)

| detector | sensitivity | 95 % CI | median delay |
|---|---:|---|---:|
| **rolling z-score** | **0.147** | 0.112–0.182 | 2 months |
| Poisson Bayes factor | 0.073 | 0.051–0.096 | 0 months |
| Poisson CUSUM | 0.065 | 0.036–0.102 | 3 months |
| naive rate multiplier | 0.025 | 0.011–0.042 | 2 months |

Within the deployment resolution the z-score interval does not overlap any other: it is the best of the
four **there**.

## Identifiability: fails

| width (months) | winner |
|---:|---|
| 1 | naive rate multiplier |
| 2 | Poisson CUSUM |
| 3 | rolling z-score |
| 4 | Poisson CUSUM |
| 6 | rolling z-score |

Kendall tau against the deployment ranking: **−1.0** at monthly (complete reversal), 0.0 at 2 months, 0.33 at
4 months, 0.67 at 6 months. The pre-registered rule (same winner everywhere and every tau ≥ 0.5) fails.

## Verdict, in the form the task demanded

No detector is identifiable as best in general. The layer deploys **rolling z-score at quarterly
resolution**, and every downstream artifact must state that resolution. It is not a ranking claim: at monthly
resolution the same detector ranks **last**.

## Consequence for the product and the paper

- The profile's alert machinery is quarterly and carries `resolution: 3 months` in provenance.
- The paper's detection section now reports the deployment choice **with** the reversal rather than stopping
  at "the ranking is unstable", which is the difference between an honest limitation and an unactionable one.

## Not claimed

That the z-score is the best detector; that 0.147 sensitivity is adequate for any particular decision; that
anything measured here transfers to another corpus or resolution.

## Verification

- `python experiments/b039/deployment_resolution.py` → exit 0, deterministic, artifact written.
- `python -m medradar selftest` → 854 tests OK (skipped=3).
