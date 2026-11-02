# Cycle 25 — no confirmation window recovers the ramp class; the two-month policy stands (2026-11-03)

**Status:** completed. Closes B-058. Pre-registered in D-050, outcome in D-051.
Artifacts: `experiments/b026/window_tradeoff.py`, `window_tradeoff.json`, `window_tradeoff.log`.

## Why this run

The confirmed promotion rule (D-043, replicated D-048) uses a **two-month** confirmation window. It separates
spike from sustained well (precision 0.914–0.917) but cannot separate a **ramp** from a level shift (ramp
recall 0.117–0.142). A ramp keeps growing, so a longer window should help — at the cost of slower decisions.

## Design (fixed before running)

Windows of **1, 2, 3, 4 and 6 months** after the alert (alert month always excluded), on **both** units — 65
eligible company cells and 191 eligible entity cells — with three fresh origins per cell and fixed seeds. Same
shapes, magnitudes and detector; only the window varies. Recommendation rule: worth re-pre-registering only if
ramp recall > 0.40 **and** sustained precision ≥ 0.85 on **both** units.

## Result: no window qualifies

| window | company ramp recall | company precision | entity ramp recall | entity precision |
|---:|---:|---:|---:|---:|
| 1 month | 0.000 | 0.911 | 0.000 | 0.937 |
| 2 months | 0.154 | 0.897 | 0.128 | 0.897 |
| 3 months | 0.183 | 0.895 | 0.107 | 0.889 |
| 4 months | 0.143 | 0.886 | 0.107 | 0.889 |
| 6 months | 0.229 | 0.862 | 0.114 | 0.885 |

Best ramp recall anywhere is **0.229**, and precision falls monotonically as the window lengthens. With 495
company alerts and 1,222 entity alerts per window, this is not a sample-size artefact.

## The trap worth naming

**Balanced accuracy is highest at the one-month window** (0.588 company, 0.616 entity) — because a one-month
window cannot see a ramp forming, so it calls every ramp "level" and scores those cases right for the wrong
reason. A report built on balanced accuracy alone would recommend the window that is *worst* at the job the
window exists for. The class-specific recall is the metric that matters, which is why the pre-registration
fixed it in advance.

## Decision

The promotion policy stays at **two months**. Three-way shape classification is recorded as **not available**
at this counting rate — not as a tuning problem. At ~0.2 events per cell-month, a ramp adds roughly one event
per month at peak; distinguishing it from a flat step would need a confirmation window longer than the ramps
themselves.

## What changes in the product

Nothing operational: the policy already promotes on the binary sustained/spike decision. What changes is the
claim — the profile no longer implies `ramp` is a recoverable class, and this analysis is the evidence that it
is not.

## Verification

- `python experiments/b026/window_tradeoff.py` → exit 0, 4.5 s, deterministic (seeds 7071/7072).
- `python -m medradar selftest` → 880 tests OK (skipped=3).
- `verify_claims.py` → claims unchanged; no paper number depends on this analysis.

## Next

1. Second-domain validation before any portability claim.
2. Decide how promoted changes enter the paper's results ledger (a promoted alert is not a finding).
3. Record the ramp limitation in the profile's limits field so it travels with every profile.
