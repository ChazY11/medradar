# Cycle 1 — frozen results (v0.5.0, 2026-11-02)

**Provenance.** Every number below is copied from committed artifacts, not recomputed
by memory: `experiments/reverse_rd_v2/continuation_metrics.json`,
`entry_metrics.json`, `ablation_metrics.json`, `market_metrics.json`,
`publication_metrics.json`, `forecast_cycle_report.json`, `tkg_import_report.json`,
and the narrative `experiments/reverse_rd_v2/REPORT.md`. The pipeline is reproducible
with `python experiments/reverse_rd_v2/run_v2.py --db data/research.sqlite --holdouts 3`
(plus one invocation per ablation cell).

**Data.** openFDA bulk lane 2016-11-01 .. 2026-10-15: 31,219 510(k) + 23,871 PMA rows,
51 curated companies, 38 tracks, **3,833 resolved-company material events**, 322
observed company-track pairs. SEC Company Facts 43,420 rows / 32 companies. Market
bars 95,725. OpenAlex 616 company-year rows (150,087 works, 51/51 companies).
USAspending 3,453 awards with `pit_usable=0`.

**Protocol.** Purged expanding-window rolling origin; a training example may only
train an origin if `cutoff + 12m <= origin`. Three sequential holdout windows
2025-04-01 / 2025-07-01 / 2025-10-01, overlapping label windows (not independent
replications). Logistic regression, fixed hyperparameters. Paired bootstrap
(2,000 resamples, seed 7). Independent as-of leakage replay.

## R1 — Continuation (T-cont)

| Quantity | Value |
|---|---|
| Examples / origins | 6,701 over 25 quarterly origins |
| Positives | 3,154 (base rate 0.470676) |
| AP, window mean (rd_only / rd_financial) | **0.773718** (std 0.023156) / 0.772689 (0.023820) |
| Per-pair persistence baseline AP | **0.755470** (std 0.025323) |
| ΔAP(model − persistence), window mean | **+0.018248** (rd_only) |
| ΔAP CI per window | 2025-04 +0.047765 [0.006836, 0.092100]; 2025-07 +0.004762 [−0.034485, 0.043917]; 2025-10 +0.002218 [−0.031599, 0.036774] |
| ECE-10 mean | 0.092668 / 0.080105 |

**Reading.** Two of three windows include zero. The model's ranking advantage over a
one-parameter per-pair persistence baseline is **not statistically detectable**. The
high AP is mostly persistence, not a learned signal.

## R2 — First entry (T-entry)

| Quantity | Value |
|---|---|
| Examples / origins | 41,003 over 24 origins (2020-01-01 .. 2025-10-01) |
| Positives | **503** (base rate **0.012267**) |
| Candidates per origin | 1,634 .. 1,730; positives per origin 10 .. 28 |
| AP, window mean (rd_only / rd_financial) | **0.106792** (0.013675) / 0.114869 (0.014715) |
| Constant-prevalence baseline | 0.015119 |
| Per-pair persistence baseline AP | 0.051511 (0.021296) |
| ΔAP(model − persistence), window mean | **+0.055281** |
| ΔAP CI per window | +0.039329 [−0.118469, +0.213820]; +0.040413 [−0.054323, +0.165076]; +0.086101 [+0.008276, +0.219389] |
| Per-origin AP range (non-holdout) | 0.018130 (2021-01-01) .. 0.237008 (2023-07-01) |
| Mean positive-target lead | 190.6 days |
| FPR@0.5 | 0.000000 in every window — **uninformative**, do not cite as a result |

**Reading.** Point estimate beats persistence in every window, but with 25–27
positives per window the intervals are wide and only one window excludes zero. This
is a **hypothesis**, not a validated predictor. Early origins are at chance because
almost no matured training data exists.

## R3–R6 — Source ablation (frozen, identical rows)

Continuation, marginal ΔAP vs shared-only: financial **−0.001278**, market
**−0.001456**, publication **−0.000128**, all sources **−0.006780** (window means:
−0.001030 / −0.002471 / −0.002125 / −0.005556).

Entry, marginal ΔAP vs shared+entry+financial: entry-specific **−0.001729**, market
**−0.005340**, publication **+0.002879**, all **−0.004341**; window means +0.001245 /
+0.000955 / +0.001478.

**Reading.** No added source produces a statistically detectable ranking gain on
either target. The financial→entry delta (+0.008077 window mean, all three windows
positive) is the only consistently signed effect and is far too weakly supported to
call a finding. The all-source continuation model improves calibration (ECE
0.0811→0.0628) and FPR (0.2753→0.2472) **while losing ranking** — a real but different
effect.

## R7 — Leakage audit

Continuation: 6,701 examples, 25 cutoffs, 140,721 feature values, **0 mismatches**.
Entry: 41,003 examples, 24 cutoffs, **1,107,081 feature values, 0 mismatches**.
The replay independently recomputes all 27 entry features, including never-observed
pairs, from `events`/`financial_facts` restricted to `available_at <= cutoff`.

**Scope limit.** This is an as-of *consistency* audit. It cannot detect semantic
leakage from unversioned product-code mappings, alias tables or target-definition
choices applied to history.

## R8 — Bitemporal graph over real history

55,090 real events → **171,800 assertions → 57,381 nodes / 114,419 edges**;
deterministic PIT snapshot (`b60c8360…`); idempotent re-import (0 created, identical
hash); early-cutoff knowledge gate returns 0/0. The TKG knowledge clock is **backfill
time**, not historical publication time, and is documented as such.

## R9 — Prospective forecasts

**25 nowcasts registered, 0 rejected, 25 pending** (windows end 2027-10); second run
`registered=0, idempotent=25` with identical state and artifact hash. Calibration:
`insufficient_matured_forecasts`.

**Reading.** We have **zero** calibration evidence about our own forecasts. Nothing in
this file should be read as calibration.

## Explicit non-claims

- Not a causal market→R&D mechanism.
- Not a demonstration that the system predicts corporate R&D direction.
- Not evidence that any deep/complex model beats baselines (none was tested).
- Not industry-representative: 51 curated companies, 322 observed pairs.
- Not independent replications: three overlapping label windows.
