# Cycle 38 — Figure 1 of the methods paper, and the three defects only a render exposed (2026-11-03)

**Status:** completed. Closes B-071. Decision: D-069.
Artifacts: `papers/rules_map.py`, `papers/figures/fig5_retraction_rules.svg`,
`papers/PAPER_METHODS_v1.md` (figure + caption), `papers/CLAIMS_METHODS.json` (25 claims),
`papers/verify_figures.py` (per-paper figure scoping), `tools/round_end.py` (9 steps).

## What the figure shows

Ten events in the programme's record mapped to the nine rules they motivated — **21 filled cells**: six
retractions (including the hiring-coverage conclusion, which motivated Rule 5), two confirmations, one unestablished
result and one excluded forecast set. The map lives in `papers/rules_map.py`, so the drawing and the verification read
the same source; `verify_figures.py` re-derives every cell.

**The count is the finding.** Rule 7 (check the pipeline, not just the statistics) is motivated by **four** separate
events and Rule 3 (a benchmark outcome must not use the triggering window) by **three**. The two rules a reader is
most likely to dismiss as boilerplate are the two with the most independent evidence behind them. Rules 5 and 6 have
exactly one origin each, and the figure states that rather than evening it out.

## The layout defects, found only by rendering

The first version:

1. pushed its legend **over columns 8 and 9**, hiding two column headings;
2. printed each decision id **on top of** its event label;
3. ran the legend **off the right edge** of the canvas.

None is visible in the SVG source and none would be caught by `check_svg`, which validates structure rather than
legibility. Fixed by moving the legend into two rows below the grid, offsetting the decision ids, and shrinking the
grid so the status column fits; the canvas height was raised so both caption lines sit inside the frame. This is the
**fourth** time a headless-browser render found a defect the verifier could not — recorded as a recurring class.

## Verification wiring

- `papers/CLAIMS_METHODS.json` → **25 claims**; three assert the figure's own numbers (21 filled cells, ten events,
  nine rules) against `figures_data.json`.
- `verify_figures.py` → the paper-link check is now **scoped per paper**, so the methods paper is checked for its one
  figure and the empirical paper for its four, while every SVG is still validated and re-derived.
- `tools/round_end.py` → **9 steps**, both figure verifications included.

## Gate result

```
PASS test suite (OK skipped=3) | PASS claim map 82/82 | PASS methods claim map 25/25
PASS paper figures 5/5 | PASS methods figures 5/5 | PASS profile selfcheck 5/5
PASS snapshot chain (0 leakage) | PASS audit 11 PASS/0 FAIL/1 N/A | PASS repo synced
=> 9 steps, 0 failures
```

## Not claimed

That the map is exhaustive. It records the events that motivated rules, not every failed experiment; several
negative results informed no new rule and appear only in the results index.
