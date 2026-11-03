# PRE-REGISTRATION — b103: cross-source lead/lag at company level (backlog B-021)

**Status:** FROZEN 2026-11-03, before any b103 statistic was computed. **Author:** Principal Research Agent.
**Backlog item:** B-021 "Lead/lag program between source classes and milestones (mission question 3)".
**Worktree:** `D:/DEPPSKK/worktrees/es-ai-review` · **Branch:** `research/early-signal-ai-review`.

---

## 1. Question

At the company level, does activity in financial, market or publication sources systematically lead or lag material
regulatory events — and if a lead is claimed, does it survive a company-clustered bootstrap, a pre-declared
circular-shift permutation null, Holm correction across sources, and an era split?

This is a **descriptive association** study. No causal language is permitted: a leading correlation does not
establish that the source causes or predicts the event.

## 2. Data (all existing, PIT fields used)

| source | series | resolution | knowledge time | window |
|---|---|---|---|---|
| regulatory events | material 510(k)/PMA counts per company-quarter (frozen hist_v1 panel) | quarter | `available_at` | 2016-11…2026-Q2 |
| financial | trailing 4-quarter `ResearchAndDevelopmentExpense` (USD, log), from `financial_facts` | quarter (fact `available_at`) | the filing's `available_at` quarter | 2009…2026 |
| market | quarterly return and quarterly volatility of `adj_close` (auxiliary only) | quarter | quarter end | 2016-10…2026-10 |
| publication | OpenAlex works per company-year, divided equally across the year's quarters | annual (declared) | 15 February of year+1 for year y | 2014…2026 |
| procurement | — | — | all `announcement_date` NULL, `pit_usable=0` | **NOT_EVALUABLE (measured)** |

**Analysis window:** 2017-Q1 … 2025-Q4 (36 quarters), the overlap where the market and event lanes exist; lags use up
to 8 quarters of earlier data, so the first usable milestone quarter is 2019-Q1 for k=8. Companies with fewer than 8
quarters of either series are excluded from that source and counted.

## 3. Statistic (frozen)

For each source S and lag k ∈ {−8,…,+8} (positive k = source precedes events):

`r(k) = corr( z(S_{c,t−k}), z(M_{c,t}) )` pooled over companies c and quarters t where both z-scores exist; z-scores are
computed per company over its own observed window of that series (so company level and scale cannot drive the
correlation). `M` is the per-company quarterly material-event count from the frozen panel.

Primary per source: `k* = argmax_{k ∈ 1..8} |r(k)|` (the strongest *lead*). Secondary: the full profile −8…+8.

## 4. Inference (frozen)

1. **Company-clustered bootstrap**, 2,000 resamples (seed 20261103): resample companies with replacement, recompute
   `r(k)`; report the 95 % percentile interval for each `k` (descriptive; labelled uncorrected).
2. **Circular-shift permutation null**, 1,000 permutations (seed 20261103): for each company independently, rotate its
   source series by a random offset in 1..T−1 and recompute `k*`; `p_S = P(max_k |r(k)| under the null ≥ observed
   max_k |r(k)|)` over the pre-declared lead window k ∈ 1..8. The rotation preserves each series' autocorrelation and
   marginal distribution; it breaks the alignment with events.
3. **Holm correction** across the three primary sources (financial, market-return, publication) at α = 0.05.
4. **Era split** (descriptive): 2017–2021 vs 2022–2025; a lead is reported as *stable* only if the point estimate has
   the same sign and the absolute value ≥ 50 % of the full-window value in both eras.
5. **Power:** report the minimum detectable |r| at 80 % power (α = 0.05) implied by the bootstrap SD, so a null is
   labelled `underpowered` or `well-powered negative`.

`market-volatility` is secondary/descriptive only and is not part of the Holm family.

## 5. Decision rule (frozen)

A source is said to **lead** only if all hold: (i) `k* > 0`; (ii) Holm-adjusted `p < 0.05`; (iii) the era-split
stability rule holds. Otherwise the result is reported as **no lead detected** with its MDE; a source whose data are
insufficient is reported as `NOT_EVALUABLE` with the measured coverage. No source is dropped after seeing its result.

## 6. Deliverables and run

```
experiments/b103_leadlag/leadlag.py   -> experiments/b103_leadlag/leadlag.json
experiments/b103_leadlag/REPORT.md    (written from the JSON only)
tests/test_leadlag.py                 (z-score/correlation/lag alignment/rotation-null determinism)
```

## 7. Amendment log

Empty at freeze. Any change after this point must be appended here with the reason and the fact that no b103 statistic
had been computed.

| id | date | change | result inspected before change? |
|---|---|---|---|
| — | — | none | — |
