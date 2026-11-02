# Cycle 6 — entry-cohort unit of analysis: density solved, and one surviving signal (2026-11-02)

**Status:** completed. Closes B-042. Evidence: `experiments/detect_v1/entries*.json`, `entries*.log`.
Decisions: D-024 (design fixed before the run, outcome recorded after).

## Why this cycle existed

Every previous cycle hit the same wall. At (entity, track, month) granularity the lane holds about
0.2 events per cell-month, so all four earlier statistical tests were starved or null:

| cycle | test | outcome |
|---|---|---|
| 3 | change detection at 2 % FAR | works monthly, ranking unstable across resolutions |
| 3b/3c | sensitivity to resolution | naive detector collapses above 1-month bins |
| 4 | cross-firm co-movement | null once track growth is conditioned out |
| 5 | cross-lane association | null (16 eligible cells) |

The response is not another model but a **different unit of analysis**: the technology-entry event.

## Design

Entry = a cell's first observed event, at least 24 months into the window. Risk set at month m =
firms already observable that have not yet touched the track. Null: entries distributed over months
with probability proportional to the unit's at-risk count — which conditions out both lane growth and
risk-set shrinkage, the two confounds that invalidated the naive co-movement test. Statistic:
dispersion index (variance/mean) of monthly entry counts. Permutation-tested, BH at q = 0.10, run
per track (industry waves) and per firm (strategic-redirection bursts).

## Result

**4,814 entry events** — the density ceiling is gone.

| run | entries | tracks rejected | firms rejected |
|---|---:|---|---|
| all events | 4,814 | 0 of 38 | 0 of 60 |
| **taxonomy-churn controlled** | 4,590 | **1 of 36 — `ivd_immuno`** (p = 0.0010, z = 4.73) | 0 of 60 |

Three things follow.

1. **One positive finding survives its controls.** Immunoassay IVD shows FDR-controlled clustering of
   first entries across firms, and it *strengthens* when 467 events on 506 late-created product codes
   are removed (p 0.0055 → 0.0010) — the opposite of what a taxonomy artifact would do.
2. **A plausible-looking wave dissolved.** `medical_ai` clustered strongly before the churn control
   (p = 0.0040) and stopped doing so after it (p = 0.0365, not FDR-significant): part of the apparent
   AI entry wave was new product codes appearing in the taxonomy.
3. **No firm shows entry bursts.** 0 of 60 firms reject, so "strategic redirection" as simultaneous
   multi-track entry is not a detectable pattern here — at least at this granularity.

## What this licenses, and what it does not

**Licensed:** *at least one device technology area (immunoassay IVD) shows a detectable industry-wide
wave of first entries after controlling for risk-set size and product-code churn.* This is a narrow,
falsifiable, re-runnable claim — and the first positive empirical finding of the programme that
survived its own controls.

**Not licensed:** that the wave is technology-driven rather than a procurement or regulatory
classification effect; that entry timing is predictable; or that any firm coordinated. A single
rejection among 36 tests under 10 % FDR is *suggestive*; what makes it credible is the robustness
direction, not the p-value.

## Next

A focused case study of the `ivd_immuno` entry waves (2019 and 2023-24): which firms entered, with
what evidence, and whether the wave is visible in the independent device-trial lane from B-040. That
is the first test in this programme with a *positive* target rather than a null — a materially
different kind of work.

---

## RETRACTED 2026-11-02 — read `cycle7_retraction_2026-11-02.md`

The positive finding below (`ivd_immuno` entry wave) did **not** survive the entry-definition control
introduced the next cycle. 79 % of the "entry" events in this file were first-ever appearances of a
legal entity, not established firms entering a track; restricting to entities that were already
observable filers collapses `ivd_immuno` to 8 entries (p = 1.0) and the surviving track identity
becomes specification-dependent. The measurement rule that replaces it: state explicitly whether an
entry study measures *firm-level technology entry* or *entity appearance*.

This file is kept unedited as the record of what was concluded at the time, per the programme's rule
that superseded results get a pointer, never a rewrite.
