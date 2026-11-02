# PRE-REGISTRATION — hist_v1: Full-history early-warning benchmark (1976–2026)

**Status:** FROZEN before any outcome model was fitted, before any label was computed, and before any
evaluation metric was produced.
**Author:** Principal Research Agent · **Date:** 2026-11-03 (Asia/Shanghai)
**Branch:** `research/full-history-v1` · **Worktree:** `D:/DEPPSKK/worktrees/hist-v1`
**Applies to:** `experiments/hist_v1/` only. It does not modify, and may not be used to reinterpret, any
frozen prior experiment.

> **Why this study exists.** The programme's own diagnostic (`research/STATE.json`,
> `experiments/detect_v1/REPORT.md`) is that the binding constraint is *information*, not modelling: the
> detection and forecasting panels were built from a 2016–2026 openFDA **bulk** lane (55,090 events), while
> the store already holds the **full** openFDA device history (510(k) 176,466 records from 1976-07-15; PMA
> 57,372 records from 1968-10-09). The 10-year window is a collection artifact. This study rebuilds the
> panel over the whole history and re-asks the directive's core question with the additional 40 years, more
> training data, and ~30 walk-forward origins instead of 24 consecutive quarters.

---

## 1. Research question

**RQ.** At the end of quarter *t*, using only information publicly available at that moment, can we rank
(company, technology-track) pairs by the probability that the company achieves its **first regulatory
clearance in that track** within the next 12 months (Y4) or 24 months (Y8) — better than prevalence and
per-company persistence baselines — and with what lead time and false-alarm cost?

This is a *prediction* question. It is **not** causal, and it is **not** about unobservable internal R&D.
The outcome is a public regulatory event; the predictors are public prior activity.

Corresponding directive hypotheses:

| ID | Hypothesis | Where tested |
|---|---|---|
| H1 | Early signals precede a verifiable milestone | primary: ΔAP vs baselines, Y4/Y8 |
| H2 | Multi-source fusion adds information over regulatory-only | §9 fusion ablation (2016-Q1+) |
| H3 | Firm heterogeneity in signal effectiveness | §10 per-company analysis |
| H4 | Technology-domain heterogeneity | §10 per-domain analysis |
| H5 | Earlier warning trades against reliability | §8.4 lead-time / alert-budget frontier |

---

## 2. Data and unit

- **Store:** `data/medradar.sqlite` (read-only), table `events`.
- **Sources in scope:** `openfda_device_510k` (all records) and `openfda_device_pma`.
- **Material event:** every 510(k) record; a PMA record **only** if
  `payload.supplement_number` is empty/null/`0`/`S0`, **or** `payload.supplement_type` contains
  `PANEL TRACK` (the materiality rule already used by `experiments/reverse_rd_v2`). Non-material PMA
  supplements are retained in the raw store but excluded from the panel.
- **Event time:** `event_date` (the FDA decision date). **Availability time:** `available_at` if present,
  else `event_date`. An event is usable at quarter *t* only if availability ≤ the last calendar day of *t*.
  The approximation (decision date as public availability) is declared as a limitation; the historical
  publication lag is not observable from openFDA and is not imputed beyond `available_at` as stored.
- **Company universe:** 53 companies = the 51-company curated roster (`data/research.sqlite`, table
  `companies`, via the store's own `company_key`) + **Dräger** and **Mindray**, which are absent from the
  store's roster mapping and are resolved by the exact-string registry
  `config/hist_entity_aliases.json` (no fuzzy matching).
- **Track:** `events.track_id` when present; otherwise the product code mapped through
  `config/product_code_tracks.json`; otherwise the event is **excluded** and the exclusion is counted.
- **Panel grid:** quarters 1976-Q1 … 2026-Q2 inclusive (2026-Q3 is partial and excluded). The last
  complete quarter is **2026-Q2**.
- **Unit:** `(company_key, track_id, quarter)`.

**Entity-resolution audit (required before results):** for every deep-case company, list every
`applicant_raw` string the store assigns to it; flag strings that are not a legal name / known brand /
subsidiary; any flagged string is placed on a deny list applied at panel build time and reported. For
Dräger and Mindray the accepted strings are fixed in `config/hist_entity_aliases.json` and are audited
string by string.

---

## 3. Candidate (risk) sets — frozen

Let `E(c)` = material events of company `c` with availability ≤ end of *t*, and `E(c,k)` = those in track `k`.

**Primary risk set `R_adj` (adjacency-conditioned, PIT):** pair `(c,k)` is a candidate at the end of *t* iff

1. `|E(c)| ≥ 1` (the company is an established filer by *t*);
2. `|E(c,k)| = 0` (the company has never had a material event in this track by *t*);
3. the company has ≥ 1 material event before *t* in **another track of the same `category`** as `k`
   (`config/tracks_device.json` `category` field; e.g. `cardiovascular`, `imaging`, `surgery`).

Condition 3 is the substantive restriction: a firm is only asked about entering a technology area in which
it already operates. It is computed only from events available by *t*.

**Secondary risk set `R_full` (unrestricted, PIT):** conditions 1 and 2 only.

Both are reported for every primary metric. `R_adj` is the pre-registered primary risk set; `R_full` is a
declared robustness estimand and may not be substituted for `R_adj` after seeing results.

**Left-censoring declaration:** the store begins in 1976. A pair whose first-ever clearance predates 1976
is indistinguishable from a pair that never entered. This affects `R_full` more than `R_adj`; it is a
declared limitation, not corrected.

---

## 4. Outcome (label) definition — frozen

For a candidate cell at the end of quarter *t* with track `k` and company `c`:

```
Y_h(c,k,t) = 1   iff there exists a material event e with e.company_key = c,
                     e.track_id = k, and end(t) < available_at(e) ≤ end(t + h quarters)
Y_h(c,k,t) = 0   otherwise
```

* `h = 8` (24 months) is the **primary horizon**; `h = 4` (12 months) is secondary.
* A cell is **label-mature** iff `t + h` ≤ 2026-Q2. Cells that are not mature are excluded from
  evaluation and counted (right-censoring).
* Entry events are single-use: the pair leaves the risk set forever after its entry quarter. One event can
  therefore contribute to at most `h` positive cells (the horizon window), never to two independent targets.
* No label is derived from post-*t* information other than the outcome events themselves.

---

## 5. Features (PIT, computed only from events available ≤ end of *t*)

All counts are log1p-transformed where they are counts. Features are computed per candidate cell from the
panel's event index; a feature whose components are undefined (e.g. growth with zero denominator) is
imputed with the **training-set median** (never with a future value).

| # | name | definition |
|---|---|---|
| 1 | `firm_act_4` | log1p company material events, all tracks, last 4 quarters |
| 2 | `firm_act_8` | log1p company material events, all tracks, last 8 quarters |
| 3 | `firm_growth` | `firm_act_4 / (firm_act_8 − firm_act_4 + 0.5)` |
| 4 | `firm_tracks` | number of distinct tracks the company has ever had a material event in by *t* |
| 5 | `firm_tenure` | years since the company's first observed material event |
| 6 | `firm_entry_rate` | company's first-entry events per year over the last 8 years |
| 7 | `adj_act_8` | log1p company material events in **other tracks of the same category**, last 8 quarters |
| 8 | `adj_share` | share of the company's last-8-quarter events that are in the same category |
| 9 | `track_act_8` | log1p material events by **other companies** in this track, last 8 quarters |
| 10 | `track_growth` | `track_act_4 / (track_act_8 − track_act_4 + 0.5)` |
| 11 | `track_entrants` | number of distinct companies that have ever entered this track by *t* |
| 12 | `track_recent_entries` | log1p first entries by **other companies** into this track, last 8 quarters |
| 13 | `track_age` | years since the industry's first observed event in this track |
| 14 | `cat_share` | share of the company's ever-events that are in this track's category |
| 15 | `firm_size` | log1p company material events ever, all tracks |
| 16 | `era_*` | (robustness only; not in the primary model) era dummy for the origin quarter's decade |

**Feature-group sets (frozen):**

* **A — firm only:** 1–6, 15
* **B — + industry/track:** 9–13
* **C — + adjacency (primary regulatory model):** 7, 8, 14 → all of 1–15
* **D — C + fusion sources (2016-Q1-origin subset only):** + trial features `tr_track_8`,
  `tr_adj_8` (log1p device-trial events in the track / in adjacent tracks, last 8 quarters, from
  `data/b040_device_trials.sqlite`) and publication features `pub_prev_year`, `pub_3y`,
  `pub_growth` (company-level annual OpenAlex works from `data/research.sqlite.publication_counts`,
  only complete calendar years ≤ year(t) − 1)
* **E — diffusion only:** 12 alone, to isolate the competitor-entry signal

`D` exists only for origins where the trial and publication lanes are available (2016-Q1 onwards); the
fusion test compares `D` vs `C` **on exactly the same rows and origins**.

---

## 6. Model

* **Primary model M1:** L2-regularised logistic regression (intercept + features standardised on
  training-only mean/sd; median imputation from training-only values; λ = 1.0; batch gradient descent with
  a fixed learning rate 0.1 and a fixed number of 120 epochs; no per-origin tuning). Deterministic.
* **Baselines (pre-declared, each fitted only on matured training cells):**
  * `B0` constant training prevalence;
  * `B1` company base rate: the company's historical first-entry rate, as a probability of entry within `h`
    quarters (firm-level persistence baseline; the strongest no-feature baseline used by prior experiments);
  * `B2` track base rate: the track's historical entry rate across companies;
  * `B3` combined exposure baseline: `B1 × B2` normalised to training prevalence.
* No hyperparameter selection, no model family search. If M1 fails to converge, that is a result
  (reported), not a reason to switch models.

---

## 7. Evaluation protocol

* **Walk-forward, expanding window.** For origin quarter `t`, train on every candidate cell `(c,k,t')`
  with `t' + h ≤ t` (labels mature strictly before the origin) — this purge prevents any training label
  from overlapping the test horizon. Test on candidates at `t`.
* **Origins:** the first quarter of every calendar year from **1995-Q1** to **2024-Q1** for `h=8`
  (30 origins), and to **2025-Q1** for `h=4` (31 origins). One prediction per candidate per origin.
* **No random split anywhere.** No cell from a future origin enters training.
* **Primary metric:** **mean per-origin average precision (AP / PR-AUC)** over the 30 evaluation origins,
  on the pre-registered primary risk set `R_adj`, horizon `h=8`. Each origin contributes equally, so a
  change in prevalence across eras cannot dominate the metric, and no ranking is formed across models
  fitted at different origins (their score scales are not comparable). Pooled AP over all test cells is
  reported as a secondary metric, never as the primary one.
  * **Primary comparison:** `ΔAP = mean_origin AP(M1,C) − mean_origin AP(B1)`.
  * **Inference:** company-clustered paired bootstrap, 2,000 resamples (seed 20261103): resample companies
    with replacement; for each resample, recompute each origin's AP on that resample's cells and then the
    mean across origins, for every model; the same resamples are used for every model so comparisons are
    paired. 95% percentile CI.
  * **Success criterion (H1):** the 95% CI of `ΔAP` excludes 0 **and** the point estimate is positive.
* **Secondary metrics (all reported):** per-origin AP (mean/sd/min/max), ROC-AUC, Brier score,
  expected calibration error (ECE-10), precision@10 / @25 per origin, recall at a 10 % alert budget,
  false-alarm rate at that budget, and the pooled AP on `R_full`.
* **Robustness (pre-declared):** (a) horizon `h=4`; (b) `R_full`; (c) era strata 1995–2004, 2005–2014,
  2015–2024 (AP per era and sign of ΔAP); (d) feature-group ablations A/B/C; (e) label-permutation null:
  scramble which company enters which track within each track (preserving each track's entry count and each
  company's total entries where feasible), refit, recompute ΔAP, 200 permutations (seed 20261103).
* **Multiple testing:** the two horizons are the only confirmatory tests; Holm correction across the two
  primary p-values (bootstrap-based). All other analyses are labelled secondary/descriptive.

## 8. Lead time, false alarms, and the H5 frontier

At each origin, the alert threshold is the **90th percentile of that origin's training scores** (so the
alert budget is fixed by construction, not tuned on test). Then:

* **Lead time** for an entry event at quarter `τ`: `τ − a`, where `a` is the first quarter in
  `[τ−8, τ−1]` in which the pair was a candidate and was alerted. Entries never alerted in that window are
  counted as **missed** and reported; lead time is **not** computed only over successful cases.
* Report: number of entry events in the evaluation window, number alerted, median/IQR lead (with missed
  events listed separately), and the false-alarm rate per candidate-quarter at the same threshold.
* **H5 frontier:** repeat at alert budgets 1 %, 5 %, 10 %, 20 % (threshold = corresponding training
  quantile). Report (budget, precision, recall, false alarms per 1,000 candidate-quarters, median lead).
  This is descriptive; no success threshold is pre-declared for H5.

## 9. Ablations and fusion (H2)

Primary ablation on the same origins/cells: feature sets A, B, C (all with M1). Fusion: on the 2016-Q1+
origins, compare C vs D, paired by cell, with the same bootstrap. **H2 is supported** iff the 95 % CI of
`AP(D) − AP(C)` excludes 0 and is positive on that subset. If the trial/publication lanes cannot be joined
to the panel at cell level (coverage < 50 % of candidates), the fusion test is reported as
`NOT_EVALUABLE` with the measured coverage, and no substitute proxy is used.

## 10. Heterogeneity (H3, H4)

* **H3 (firms):** per-company AP and per-company ΔAP for companies with ≥ 10 positive test cells;
  Kendall τ between company AP and company size (material-event count); the deep-case companies reported
  individually. A difference between the deep cases and the auxiliary roster is reported with its CI but
  is **descriptive** (53 companies, not a random sample).
* **H4 (domains):** per-category AP and ΔAP; the difference between the highest and lowest category is
  tested by a company-clustered bootstrap (resampling companies within categories).

## 11. What would falsify the study's premise

The premise ("public signals contain usable early warning") is **not supported** if, on the primary
estimand, `ΔAP`'s 95 % CI includes 0 and the minimum detectable ΔAP is small enough to rule out a
practically useful effect. The MDE is computed from the bootstrap dispersion and reported alongside every
null. A null with a large MDE is reported as **underpowered**, not as evidence of absence.

## 12. Leakage controls (audited, not asserted)

1. Feature availability: every feature uses only events with availability ≤ end of *t*; the panel builder
   stores per-pair event dates and the evaluator recomputes features from them.
2. Label purge: training cells satisfy `t' + h ≤ t`; asserted for every origin.
3. Independent replay: a seeded 300-cell sample is recomputed by a separate function with `available_at`
   filters, and must match the feature matrix exactly (0 mismatches).
4. Taxonomy: the product-code→track mapping is current and unversioned; applying it to history is a
   declared limitation (it can make a track look newer than it was). Mitigation: the `track_age` feature
   is computed from observed events, and a robustness run excludes product codes whose first observed use
   is after 2010.
5. Entity resolution: deep-case alias audit; the store's mapping for the auxiliary roster is unaudited and
   is declared as the main external-validity limitation.
6. No feature uses the label; no hyperparameter is chosen on test.

## 13. Analysis plan / artifacts

```
experiments/hist_v1/build_panel.py   -> out/hist_v1/panel.json (+ experiments/hist_v1/{audits,manifest}.json)
experiments/hist_v1/eval.py          -> experiments/hist_v1/results.json
experiments/hist_v1/REPORT.md        -> written from results.json only
tests/test_hist_eval.py              -> unit tests for AP, purge, bootstrap, lead time, feature defs
```

All committed code is standard-library only and deterministic. The panel is a regenerable intermediate and
is written to `out/` (git-ignored); its SHA-256 is recorded in `manifest.json` and in `results.json`.

## 14. Amendment log

Any change to this document after the freeze must be appended here **before** the changed analysis is run,
with the reason and the fact that no result had been inspected.

| id | date | change | result inspected before change? |
|---|---|---|---|
| A1 | 2026-11-03 | Primary metric changed from *pooled* AP to *mean per-origin* AP (pooled kept as secondary). Reason: models are refitted at every origin, so their score scales are not comparable; pooling ranks across origins would let the largest-prevalence era dominate and would rank cells from different models against each other. No model had been fitted and no metric produced. | no |
| A2 | 2026-11-03 | Training-set size control: at each origin the training set is a weighted case-control sample — **all** positive cells and a seeded (seed 20261103) random sample of negative cells such that total training rows ≤ 12,000; each sampled negative carries weight `1/p_neg` (`p_neg` = sampling fraction), positives carry weight 1. Reason: the full-history training set reaches tens of thousands of cells per origin and the pure-Python fit would not finish the pre-registered grid (61 origins × feature groups × 200 permutations) on the target laptop. Weighted fitting keeps the population estimand; the test set is never subsampled; calibration is computed on the unsampled test cells. No model had been fitted and no metric produced. | no |
| A3 | 2026-11-03 | Feature-group ablations A/B/C and the H3/H4 analyses run on `h=8` only; `h=4` runs the primary model C plus baselines (resource control, not inferential). The label-permutation null (200 permutations) runs on feature set C, `h=8`. Reason: same compute bound as A2. No model had been fitted and no metric produced. | no |
| A4 | 2026-11-03 | If the panel's candidate counts make the full grid exceed a 90-minute single-run budget, the permutation null is reduced to the largest number of permutations that fits, the achieved number is recorded in `results.json`, and the empirical p-value is reported with its resolution floor (`1/(n_perm+1)`) explicitly. Any such reduction is reported as a limitation, not hidden. This is a pre-declared resource fallback; it changes no estimand. | no |
| A5 | 2026-11-03 | Entity-attribution sensitivity: the store's `company_key` is a **current corporate-group** mapping, so historical events of acquired brands (Medtronic: Covidien, Tyco Healthcare, Kendall Healthcare; ~210 material events in the store) are attributed retroactively to the acquirer, which is a point-in-time look-ahead in the entity definition. The primary panel keeps the store mapping (declared limitation). A sensitivity panel `pairs_no_acquired` removes every event whose `applicant_raw` does not contain the parent brand token (MEDTRONIC / GE / PHILIPS / DRAGER / MINDRAY; Dräger's token is DRAGER because its parent records omit the umlaut). The primary result is re-run on `pairs_no_acquired` and reported as a robustness row; if the exclusion changes fewer than 5 % of evaluation cells the row is reported as `UNCHANGED` without a second inference. No model had been fitted and no metric produced. | no |

**Freeze attestation.** At the time of these amendments no outcome label had been computed, no model had
been fitted, and no evaluation metric had been produced for this study. The universe characterisation
(event counts by decade, 525 observed company-track pairs, 337 re-entries at a 5-year gap) was inspected
while deciding whether the full-history study was feasible; it is not an outcome of the model and did not
inform any threshold, metric, or decision rule above.
