# Cycle 20 — the programme's first confirmed pre-registered prediction (2026-11-03)

**Status:** completed. Closes B-054. Decision: D-043.
Artifacts: `experiments/b026/confirm_window.py`, `confirm_window.json`, `confirm_window.log`;
paper updated (new §4.9, revised title and abstract).

## What was tested

D-041 found that excluding the alert month from a shape classifier's confirmation window lifts balanced
accuracy from 0.394 to 0.608 and sustained-change precision from 0.764 to 0.940. That fix was found **after**
seeing the pre-registered rule fail, so D-042 fixed a confirmatory test in advance: three fresh injection
origins per cell, each at least six months from the discovery origin, zero origins inside the guard band;
same shapes, magnitudes and detector.

## Result: 494 alerts, verdict CONFIRMED

| truth \ predicted | spike | level | ramp | recall |
|---|---:|---:|---:|---:|
| spike (120) | 118 | 15 | 17 | **0.787** |
| level (175) | 0 | 144 | 31 | 0.823 |
| ramp (169) | 3 | 142 | 24 | 0.142 |

- balanced accuracy **0.584** (95 % CI 0.556–0.607), floor 0.50 → pass
- sustained-change precision **0.914** (95 % CI 0.892–0.934), floor 0.85 → pass
- sustained base rate **0.696**; CI lower bound 0.892 exceeds it → pass

## What is confirmed, and how narrowly

The **binary** decision — *promote an alert to "technology change" or treat it as a transient spike* — is
now evidence-based rather than a default: precision 0.914 against a 0.696 base rate, because 78.7 % of spikes
are caught.

The **three-way** distinction is **not** confirmed: ramp recall is 0.142, so a ramp remains indistinguishable
from a level shift at this counting rate. The aggregate balanced accuracy clears its floor because two of the
three classes separate — a narrower success than the aggregate suggests, and stated that way in the paper.

## The caveat that must travel with it

The window fix came from the discovery sample. The confirmation used fresh **injection months** but the same
65 cells. This is a post-discovery confirmation: legitimate, and weaker than confirming an a-priori
hypothesis, because the hypothesis space was narrowed using the same cells.

It does **not** rescue any earlier finding. The five retractions stand; the rolling-origin null stands; and
nothing here says a promoted change is technological.

## Paper changes

- Title now reads *"five retractions, a controlled-truth frontier, and one confirmed decision rule"* (the
  previous "no surviving positive result" was no longer accurate).
- The abstract carries a paragraph explicitly labelled **after drafting**, attributing the result as an
  addition rather than folding it into the negative-results claim.
- New §4.9 reports the failure, the diagnosis, the confirmation, the scope limit and the caveat; figures
  section renumbered to §4.10.
- Claims file extended: **51 of 51** quantitative claims verified in both directions.

## Verification

- `python experiments/b026/confirm_window.py` → exit 0, 2 s, deterministic (seed 2026).
- `python papers/verify_claims.py` → 51/51, exit 0.
- `python papers/verify_figures.py` → 4 figures, 0 failures.
- `python -m medradar selftest` → 854 tests OK (skipped=3).

## Next

1. **B-039** deployment-resolution fix (the last P0 technical debt in the Observe layer).
2. Extend the confirmed promotion rule into the profile's momentum/alert fields with its measured error rate.
3. Consider a second confirmation with **fresh cells** (requires more eligible cells than 65) before treating
   the rule as portable.
