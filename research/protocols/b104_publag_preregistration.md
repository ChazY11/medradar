# PRE-REGISTRATION — b104: publication knowledge-lag sensitivity (backlog B-041)

**Status:** FROZEN 2026-11-03, before any b104 run. **Backlog item:** B-041 "Publication-lag sensitivity analysis".
**Design it tests:** the hist_v1 fusion comparison (feature set C vs D) on the 2016-Q1+ origins.

## Question

The hist_v1 fusion features assume a publication year `y` is usable from the start of `y+1` (the OpenAlex annual
counts are treated as known once the year is complete). The backlog asks whether the headline conclusion — *adding
trial + publication features does not improve ranking* (hist_v1: ΔAP(D−C) = −0.0053, `experiments/hist_v1/REPORT.md`
§5.4) — survives assumed publication knowledge lags of **0, 14, 30 and 90 days** after the end of the year.

## Design (frozen)

For each lag `L ∈ {0, 14, 30, 90}` days:

1. A publication year `y` is **usable** at quarter `t` iff `date(y+1, 1, 1) + L days ≤ last day of quarter t`.
2. `y*` = the most recent usable year with a count for the company; the three publication features become
   `pub_prev_year = log1p(works[y*])`, `pub_3y = log1p(works[y*]+works[y*-1]+works[y*-2])` (None unless all three
   exist), `pub_growth = works[y*]/(works[y*-1]+0.5)` (None if either is missing). At L = 0…30 this reproduces the
   hist_v1 definition for every origin; the 90-day lag can only affect first-quarter origins.
3. Trial features and all other elements of the C/D evaluations are unchanged (same panel, same risk set `R_adj`,
   h=8, origins 2016-Q1…2024-Q1, same model, same training sampler, same seed 20261103).
4. For each lag, run the C and D configurations and report: per-lag publication join rate, mean per-origin AP(C),
   mean per-origin AP(D), point ΔAP(D−C), and the per-origin sign count.

## Decision rule (frozen)

The hist_v1 conclusion is reported as **unchanged** if ΔAP(D−C) ≤ 0 at every lag; the **largest positive ΔAP** across
lags is reported as the sensitivity envelope. No new inferential test is added: this is a sensitivity analysis of a
previously reported descriptive comparison, and it may not be used to upgrade the hist_v1 fusion conclusion to a
positive result. If any lag produces ΔAP(D−C) > 0, the finding is reported as "lag-dependent, not robust" and the
hist_v1 conclusion is marked as sensitive.

## Output

`experiments/b104_publag/publag.py` → `experiments/b104_publag/publag.json`, `REPORT.md` (from the JSON only),
`tests/test_publag.py` (lag→usable-year rule, y* selection, quarter-end arithmetic).
