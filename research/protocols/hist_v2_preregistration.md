# PRE-REGISTRATION — hist_v2: domain-level entry benchmark, 1995–2015 (frozen before any model fit)

**Status:** FROZEN 2026-11-03, before any hist_v2 model was fitted and before any hist_v2 outcome metric was produced.
**Author:** Principal Research Agent · **Branch:** `research/early-signal-ai-review` · **Worktree:** `D:/DEPPSKK/worktrees/es-ai-review`
**Successor to:** `hist_v1` (see `research/protocols/hist_v1_preregistration.md` and `experiments/hist_v1/REPORT.md`).
**Feasibility artifact:** `experiments/hist_v2/feasibility.json` (measured before this freeze).

---

## 1. Why a successor design is needed

hist_v1's pre-registered primary test was supported but marginal: on the adjacency-restricted company × track risk set
it had **6.0 positives per origin**, an MDE of 0.090 (larger than the observed 0.058), and it did **not** beat the
two-way exposure baseline B3. Two structural causes were measured, not guessed:

1. **The adjacency restriction excluded most milestones**: 161 of 255 entry events were new-category entries, removed
   by construction.
2. **The 38-track unit is too fine for the modern era**: the mandated firms' track portfolios are saturated (last new
   track: Medtronic 2012, GE HealthCare 2000, Dräger 2014, Mindray 2011; Philips added 4 in 2016–2025), so entries
   concentrate in 1995–2015.

The measured feasibility of the coarser unit (`experiments/hist_v2/feasibility.json`):

| unit, 1995–2015, h=8 | origins | mean candidates | mean positives | base rate | total positives |
|---|---:|---:|---:|---:|---:|
| 22 technology **domains** | 21 | 725.4 | **12.00** | 0.017 | 252 |
| 38 tracks (same window, full risk set) | 21 | 130.1 | 17.57 | 0.142 | 369 |

The domain unit **doubles positives per origin relative to hist_v1's primary risk set (12.0 vs 6.0)** and, because the
unit is the domain, it includes the new-category entries the adjacency restriction had to exclude. This is the basis
for a *new* pre-registration; it is not a re-reading of hist_v1.

## 2. Research question

At the end of quarter *t*, using only information publicly available then, can (company, technology-domain) pairs be
ranked by the probability of the company's **first observed clearance in that domain** within 12 / 24 months — better
than (a) firm persistence, (b) domain tempo, and (c) the two-way exposure product of the two?

## 3. Data and unit (frozen)

- Same frozen panel as hist_v1: 1976-Q1…2026-Q2, 53 firms, 38 tracks, 14,704 material events
  (SHA-256 `10f8c00a…` in `experiments/hist_v1/manifest.json`).
- **Unit:** `(company, technology-domain, quarter)`, where domain is the `domain` field of
  `config/tracks_device.json` applied through the event's `track_id` (22 observed domains).
- A domain-level event is the aggregate of its tracks' material events; availability rules are inherited unchanged.
- **Evaluation window:** origins at Q1 of every year **1995…2015** (21 origins) — the entry-rich era measured above.
  The post-2015 era is used only as a descriptive holdout, never for the primary test.
- **Horizons:** h=8 (24 months, primary) and h=4 (12 months, secondary).

## 4. Outcome (frozen)

`Y_h(c,d,t) = 1` iff the company's first observed material event in domain `d` falls in `(t, t+h]`. Cells whose
horizon crosses 2026-Q2 are excluded and counted. First entries are single-use: a pair leaves the risk set after entry.

## 5. Risk sets (frozen)

- **Primary `R_dom`:** firms with ≥1 material event by *t*, pairs with no domain event by *t* (the unrestricted full
  risk set at domain level; the new-category entries are included by design).
- **Secondary `R_dom_adj`:** as `R_dom`, plus the firm already has an activity in a *different* domain (adjacency at
  domain level), for comparison with hist_v1's restriction.

## 6. Features (frozen; same 15 as hist_v1, re-defined at domain level)

Firm activity/growth/tempo/tenure/size; domain-level industry activity, growth, entrants, recent competitor entries,
domain age; the firm's activity in *other domains* (adjacency at domain level) and its share; the firm's share of
events in this domain's tracks. All computed from events with `available_at ≤ end of t`; training-only imputation.

## 7. Model and baselines (frozen)

L2 logistic regression (λ = 1.0, lr 0.1, 120 epochs, training-only standardisation/median imputation, no tuning).
Baselines: B0 prevalence, B1 company base rate, B2 domain base rate, B3 B1×B2. Same weighted case-control training cap
as hist_v1 (A2: 12,000 rows). The primary comparison is **M1 − B1**, with **M1 − B3 reported as the decisive secondary
comparison** (hist_v1's unresolved question).

## 8. Inference (frozen)

Company-clustered paired bootstrap (2,000 reps, seed 20261103) on mean per-origin AP; 95 % CI; report
`share_resamples_below_min_contributing_origins` and the reliability gate exactly as in hist_v1.
**Success criterion:** the 95 % CI of ΔAP(M1−B1) excludes 0 and is positive **and** the ΔAP(M1−B3) point estimate is
positive **and** at least 60 % of origins have a positive ΔAP(M1−B1). A result that beats B1 but not B3 is reported as
"persistence beaten, incremental value not established" (the hist_v1 outcome).
**Pre-declared power target:** MDE ≤ 0.05 AP points on the primary comparison; if the measured MDE exceeds 0.05 the
result is declared underpowered in advance, whatever its p-value.

## 9. Robustness (frozen)

Label-permutation null (200 permutations, same scheme as hist_v1); era split 1995–2004 / 2005–2015; feature groups
A/B/C; descriptive holdout on 2016–2024 origins; the `pairs_no_acquired` attribution sensitivity inherited from A5.
The lead-time frontier (1/5/10/20 % budgets) is reported descriptively with missed entries, as in hist_v1.

## 10. Not claimed

No causal claim; no internal-R&D claim; no pooled comparison with hist_v1's AP values (different unit and window);
no Target B claims (that study is closed negative by owner authorisation, D-079).

## 11. Run command (next round; nothing in this freeze depends on the result)

```bash
python experiments/hist_v2/build_domain_panel.py          # to be written next round, reuses hist_v1 panel
python experiments/hist_v2/eval.py --panel out/hist_v2/domain_panel.json --workers 12
```

## 12. Amendment log

Empty at freeze. Any change after this point must be appended here with the reason and the fact that no hist_v2 model
had been fitted.

| id | date | change | result inspected before change? |
|---|---|---|---|
| — | — | none | — |
