# Cycle 13 — calibrated momentum: three of five profile readings were noise (2026-11-02)

**Status:** completed. **Corrects** the momentum field of D-032. Decision: D-033.
Artifacts: `medradar/intelligence/profile.py` (momentum test), `tests/test_profile.py` (36 tests),
`experiments/b027/profiles.json`, `experiments/b027/profiles/*.md`, `experiments/b027/selfcheck.py`,
`experiments/b027/print_momentum.py`.

## The defect in cycle 12

Momentum was a rate ratio between the last 24 months and the 24 before; a ratio ≥ 1.25 was called
"rising". That is the mistake the programme has paid for repeatedly: **a ratio is not evidence.**
With counts in the tens, 90 versus 66 is entirely compatible with a constant rate.

## The fix

Momentum is now a **two-sided exact binomial test** of the recent count conditional on the total
(equivalently the Poisson rate-ratio test under a constant-rate null), at α = 0.05:

- `increasing` / `decreasing` only when p < 0.05;
- otherwise `no_detectable_change`, and the field must report the **minimum detectable ratio at 80 %
  power** implied by the observed counts, so a null can never be read as "no change".

The rendered profile prints p, α, the MDE and the `detected` flag; `selfcheck.py` re-derives them
from the JSON.

## What happened to the cycle-12 readings

| company | last 24 m | prior 24 m | ratio | exact p | MDE (80 %) | verdict |
|---|---:|---:|---:|---:|---:|---|
| Medtronic | 90 | 66 | 1.36 | 0.065 | 1.57× | **no detectable change** (was "rising") |
| GE HealthCare | 57 | 48 | 1.19 | 0.435 | 1.73× | no detectable change (was "stable") |
| Philips | 73 | 36 | 2.03 | **0.001** | 1.77× | **increasing** (survives) |
| Mindray | 18 | 12 | 1.50 | 0.362 | 2.84× | **no detectable change** (was "rising") |
| Dräger | 10 | 10 | 1.00 | 1.000 | 3.50× | no detectable change (was "stable") |

**Three of five cycle-12 momentum readings were noise.** Only Philips' doubling clears the test.

This is the fourth time a tempting positive has dissolved under a better null — and the first time it
dissolved **inside the product, automatically**, because D-032's rule forced the contradiction check to
exist. That is the design working as intended.

## Not claimed

A non-detection is **not** evidence of stability. The MDE column states how large a change this data
could have seen: Medtronic would have needed a 57 % increase to be detectable, so a real 20 % increase
is fully compatible with the data and simply invisible. The honest sentence is "no detectable change,
with MDE 1.57×", never "stable".

## Verification

- `python -m pytest tests/test_profile.py` → 36 tests pass (momentum: detection, non-detection, exact
  p-values, MDE monotonicity)
- `python experiments/b027/selfcheck.py` → 5/5 profiles pass, now also checking the p-value, MDE and
  `detected` flag appear in the Markdown and agree with the JSON
- `python -m medradar selftest` → 831 tests OK (skipped=3)

## Why this matters

The Understand layer now cannot report a direction without a test that supports it, and cannot report
a null without stating its power. That is the difference between a dashboard and an instrument: the
profile's "no detectable change" is a falsifiable statement about this data's resolution, not a soft
claim of stability.
