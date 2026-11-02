# Cycle 41 — seasonality is real, quantified, and unreachable at this resolution (2026-11-03)

**Status:** completed. Closes B-037. Pre-registered in D-072, outcome in D-073.
Artifacts: `experiments/b074/seasonality.py`, `seasonality.json`, `seasonality.log`;
`papers/PAPER_v1.md` §6 (seasonality paragraph); `CLAIMS.json` (88 claims).

## The open obligation this discharges

The detector's operating point — quarterly, rolling z ≥ 3.5, measured false-alarm rate **0.0179** — was computed on raw
counts. The programme's noise controls require month-of-year and lane-wide volume effects to be estimated and either
removed or explicitly stated. This cycle measures them on the frozen lane (329 company × track cells, 3,928 events,
119 months) and states the consequence.

## The month-of-year effect is real and sizeable

- January and February factors **0.891** against a lane mean of 1.0; March **1.118**; annual spread **1.255×**.
- Permutation test with 2,000 label shuffles: **0 of 2,000** reach the observed dispersion, **p = 0.0005**.
- The spread sits **inside Q1** (0.891, 0.891, 1.118), so quarterly aggregation does not average it away.

**Quarter-boundary artifact** (events in the first/last month of a calendar quarter): **1.058×** and **1.054×** the
interior-month mean — about 5–6 %.

## Per-cell scaling cannot remove it, and the reason is count resolution

Dividing each cell-month by its factor changes **9 of 39,151** cell-months — two cells. The lane is **91.8 % zeros**
and almost all remaining months are 1, so a factor of 0.891 rounds back to the same integer. Consequently:

| quantity | raw | adjusted |
|---|---:|---:|
| detector alert rate (quarterly) | **0.0090** | **0.0090** |
| alerts / opportunities | 89 / 9,870 | 89 / 9,870 |
| injected alert rate (monthly) | 0.9720 | 0.9720 |

**Verdict as pre-registered: the alert rate is an upper bound**; the 0.0179 figure stands uncorrected. But the reading
is sharper than the rule required: **seasonality cannot manufacture false alarms at this density**, because a
lane-wide 11 % January dip is well below one event for a cell whose monthly baseline is a fraction of an event. The
bound is loose in theory and unreachable in practice, and the paper now says both.

## Consequence

No change to the deployed detector, threshold, window or resolution. The noise-control obligation is discharged with a
measurement rather than an assumption, and the paper carries the numbers (claims CC1–CC6).

## Not claimed

That the effect is irrelevant at coarser units. Track-aggregate series carry ~2.3 events per month (D-057), so an
11 % dip **is** resolvable there and a market-level seasonal correction would be applicable — this run tested the cell
level the detector actually operates on.

## Verification

- `python experiments/b074/seasonality.py` → exit 0, 1.8 s, deterministic (seed 7373).
- `python papers/verify_claims.py` → **88/88** after the paper paragraph was added.
- `python tools/round_end.py` → gate run for this round.
