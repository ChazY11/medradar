# Cycle 34 — end-to-end pipeline evaluation: alerts predict persistence, the promotion filter's added value does not (2026-11-03)

**Status:** completed. Closes B-067. Pre-registered in D-064, outcome in D-065.
Artifacts: `experiments/b067/promotion_rolling_origin.py`, `promotion_rolling_origin.json`,
`promotion_rolling_origin.log`.

## The gap this closes

Every component of the alerting pipeline had been validated in isolation: the detector (D-045), the calibration
(D-033), the promotion rule on injected shapes (D-043, D-048), and the rule across units and domains
(D-057, D-061). The pipeline **as a whole** had never been evaluated on real history.

## Design (fixed before running)

Quarterly origins 2019-Q1 … 2024-Q4; deployed detector (z ≥ 3.5 against the previous eight quarters); the
confirmed two-quarter promotion rule applied to t+1, t+2; outcome = mean activity in t+3 … t+6 at least the
alert-time baseline; companies resampled in the bootstrap (2,000 replications).

## Result

**68 alerts (35 promoted, 33 unpromoted), 4,594 control cell-quarters.**

| group | P(persisted) | 95 % CI |
|---|---:|---|
| promoted | **0.800** | 0.652–0.917 |
| unpromoted (spikes) | 0.667 | — |
| no alert (control) | **0.373** | — |
| **difference** (promoted − unpromoted) | **+0.133** | **−0.074 … 0.344** |

**Verdict as pre-registered: NO ADDED VALUE.** The interval includes zero, so the promotion filter is recorded as a
**documentation discipline, not a measured predictive improvement**.

## The pipeline result is not a null

Alerts persist far more often than comparable non-alert cell-quarters (0.80 and 0.67 against 0.37) — that is the
detector doing its job. What the experiment fails to establish is the **marginal** contribution of the two-month
filter on top of the alert: a 13-point difference measured on 33 unpromoted alerts, with an interval spanning
zero.

**Why it is underpowered.** Spikes are rare among alerts (33 of 68) *because* the promotion rule exists — the
design leaves few negative cases. Testing the filter needs a longer history (not obtainable) or a lower alert
threshold (which would change the operating point under test).

## Consequence

No product change. The filter remains justified by its **shape-classification** performance on injections, not by
this end-to-end test; the promotion policy already frames promotion as a decision with a measured error rate. What
changes is the paper: the pipeline result must appear beside the injection results so neither is read alone.

## Not claimed

That the detector "predicts technology"; that the promotion filter is useless (it is unestablished, not refuted);
or that 0.37 is a fair counterfactual — control cells are by construction not on an elevated path.

## Verification

- `python experiments/b067/promotion_rolling_origin.py` → exit 0, 2.2 s, deterministic (seed 4242).
- `python tools/round_end.py` → 7 steps, exit 0 (run as this round's gate).
