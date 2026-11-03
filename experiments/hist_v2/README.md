# hist_v2 — domain-level entry benchmark (frozen design, implemented)

Successor to `hist_v1`. Frozen pre-registration: `research/protocols/hist_v2_preregistration.md`
(2026-11-03, before any hist_v2 model was fitted). This directory contains the **regenerable
domain panel** and the **walk-forward evaluation harness** for that frozen design; it contains
no paper claim of its own.

Unit: `(company, technology-domain, quarter)` — 53 companies, 22 domains, 1976-Q1…2026-Q2.
A domain event is the sum of its tracks' material events, mapped through
`config/tracks_device.json` `tracks[].domain`; availability rules are inherited from hist_v1
unchanged.

## Commands

```bash
python experiments/hist_v2/build_domain_panel.py     # out/hist_v2/domain_panel.json + manifest.json
python experiments/hist_v2/eval.py --quick           # smoke only (200 bootstrap / 5 permutation reps)
python experiments/hist_v2/eval.py --panel out/hist_v2/domain_panel.json --workers 12   # full run
python -m unittest tests.test_hist_v2_eval -v        # 40 unit/integration tests
```

Standard library only, deterministic, no network. The hist_v1 panel is opened read-only and
never modified. The canonical run of the builder writes `out/hist_v2/domain_panel.json`
(git-ignored; SHA-256 in `experiments/hist_v2/manifest.json`).

## What is frozen (implemented literally)

* 21 annual origins **1995-Q1…2015-Q1** for h=8 (24 months, primary) and h=4 (12 months,
  secondary); post-2015 origins (2016…2024) are a **descriptive holdout only**.
* Primary risk set **R_dom**: firm has ≥1 material event by *t*, pair has no domain event by
  *t* (no adjacency restriction; new-category entries included by design).
* 15 point-in-time features (protocol §6), all computed from events with `available_at ≤ end
  of t`; training-only weighted median imputation and standardisation.
* Baselines B0 prevalence, B1 company rate, B2 domain rate, B3 B1×B2; models M1A (firm),
  M1B (+domain/tempo), M1C (all 15); L2 logistic λ=1.0, lr=0.1, 120 full-batch epochs; A2
  weighted case-control cap 12,000 training rows; purge `t' + h ≤ t` asserted per origin.
* Primary metric = mean per-origin average precision. Company-clustered paired bootstrap
  (2,000 reps, seed 20261103) with the hist_v1 reliability gate (UNRELIABLE, and no CI
  quoted, if >5 % of resamples have fewer than `ceil(25/30 × n_origins)` computable origins).
* Success criterion (protocol §8): CI of ΔAP(M1C−B1) excludes 0 and is positive **and**
  ΔAP(M1C−B3) point estimate positive **and** ≥60 % of origins positive; the pre-declared
  power target MDE ≤ 0.05 AP points is applied in advance (otherwise UNDERPOWERED).
* 200-permutation null (seed 20261103; labels shuffled among cells sharing (origin, domain));
  era split 1995–2004 / 2005–2015; feature ablation A/B/C; lead-time frontier at
  1/5/10/20 % budgets with missed entries; `pairs_no_acquired` attribution sensitivity.

## Implementation interpretations (no protocol amendment)

1. **Domain-level adjacency = sibling domains sharing a config `category` band.** The literal
   reading of "the firm already has an activity in a different domain" is implied by firm
   establishment for every unentered candidate domain, so it would make `R_dom_adj`
   identical to `R_dom` and the adjacency features duplicates of firm activity. The
   category-band translation preserves hist_v1's adjacency estimand and the protocol's
   stated "comparison with hist_v1's restriction".
2. **`domain_share`** (the 15th feature, hist_v1 `cat_share` analog) = share of the company's
   ever events in the candidate domain's sibling domains; the own-domain share is identically
   0 on candidate cells (an own-domain event removes the cell from the risk set).
3. No fusion lanes: hist_v2 §9–10 contain no trial/publication test and make no Target B
   claims. H3/H4-style heterogeneity is not part of this protocol.
4. `--quick` reduces repetition counts only (bootstrap 200, permutation 5); the full run uses
   2,000 / 200.

## `out/hist_v2/domain_panel.json` contract — `hist_v2.domain_panel.v1`

Compact, key-sorted UTF-8 JSON with a trailing newline; `qidx = (year − 1976) × 4 + quarter − 1`.
Fields: `schema`, `generated_at` (hist_v1 data snapshot time), `quarter_start/end`, `quarters`
(202), `companies` (53), `domains` (22, with `categories`, `track_ids`, industry counts),
`pairs` / `pairs_no_acquired` (`company_key`, `domain_id`, `event_qidx`, `event_iso`,
`event_counts`, `n_510k`, `n_pma`), and `audits` with source/aggregation reconciliation,
per-domain pair/event counts, domain category bands, and any events whose track has no domain.
This build: **377 domain pairs / 14,704 events** (14,090 510(k) + 614 PMA) in 7,538 pair-quarters;
`pairs_no_acquired`: 377 pairs / 14,487 events; 0 events without a domain; two consecutive runs
are byte-identical (panel SHA-256 `44c115c2022326f6676c753f2d56bb31d2fac60032755f7d82d4768a01d8c7df`,
393,793 bytes, recorded in the manifest).

## Smoke run (`--quick`, 21 origins, reduced repetitions)

`out/hist_v2/results_smoke.json` (git-ignored, 425 s serial):

* **Dataset (R_dom|h8):** mean **725.4 candidates** / **12.00 positives** per origin, mean
  per-origin base rate **1.70 %** (16,543 pooled), **252 total positives** in 15,233 candidate
  cells — exactly the `experiments/hist_v2/feasibility.json` measurement.
* Mean per-origin AP: B0 0.0170 · B1 0.0435 · B2 0.0277 · B3 0.0619 · M1A 0.0515 · M1B 0.0812
  · M1C 0.0775. ΔAP(M1C−B1) = **+0.0340** (bootstrap OK; 85.7 % of origins positive);
  decisive ΔAP(M1C−B3) = **+0.0156** (CI includes 0). Permutation p (5 reps) = 0.167.
* **Smoke MDE estimate: 0.032 AP points** for M1C−B1 (and 0.039 for M1C−B3) — a 200-resample
  smoke estimate, **not** the pre-registered result (full run: 2,000 resamples).
* Leakage replay: 0/300 mismatches; label purge violations 0. Holdout (descriptive) ΔAP
  +0.0095; `pairs_no_acquired` sensitivity ΔAP +0.0361.

## Files

| path | role |
|---|---|
| `experiments/hist_v2/build_domain_panel.py` | deterministic domain panel builder (stdlib) |
| `experiments/hist_v2/eval.py` | walk-forward evaluation harness (stdlib) |
| `experiments/hist_v2/manifest.json` | SHA-256 of input panel/config/script/output + row counts |
| `experiments/hist_v2/feasibility.py`, `feasibility.json` | pre-freeze feasibility measurement |
| `out/hist_v2/domain_panel.json` | generated panel (git-ignored) |
| `out/hist_v2/results_smoke.json` | `--quick` smoke output (git-ignored) |
| `tests/test_hist_v2_eval.py` | 40 tests: metrics, purge, risk sets, aggregation, bootstrap, lead time, golden end-to-end |
