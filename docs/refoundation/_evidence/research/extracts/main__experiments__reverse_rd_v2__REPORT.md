# Reverse R&D v2 — Phase 1–2 real-data report (entry target, multi-window, source ablation)

Generated 2026-11-02 from the frozen research database (openFDA bulk lane 2016-11-01..2026-10-15, SEC Company Facts, USAspending snapshot); no network was used. Configuration: [`config.json`](config.json). Machine-readable values: [`continuation_metrics.json`](continuation_metrics.json) and [`entry_metrics.json`](entry_metrics.json). Every number below is read from those two files (or from [`data_provenance.json`](data_provenance.json)); none is estimated. Regenerate with:

```bash
python experiments/reverse_rd_v2/run_v2.py --db data/medradar.sqlite --holdouts 3
```

`experiments/reverse_rd_v1/` is untouched: the v1 single-holdout metrics are reproduced bit-for-bit by the continuation run below.

## What v2 adds

1. **A harder entry target.** `build_entry_examples` builds `dataset_version='first_entry_v1'`: at each quarter-start cutoff `t`, the candidate is a `(company, track)` pair where the company is already active (≥1 material event by `t`), `track_id` is non-null, and the pair has **zero** material events in `(t − 36 months, t]`. The label is 1 iff a material event occurs for that pair in `(t, t + 12 months]`. Material-event rules are identical to v1 (any 510(k); PMA only original/panel-track supplements). Full definition and the left-censoring statement are in [`docs/REVERSE_RD.md`](../../docs/REVERSE_RD.md).
2. **Multi-window expanding-origin evaluation.** `run_backtest(..., holdouts=K)` evaluates the last K origins with a purged training set as sequential holdouts, with per-window metrics and mean/std across windows for every model and baseline. `holdouts=1` reproduces the v1 output exactly (the new fields are additive).
3. **A reusable, reproducible driver** (`run_v2.py`) that builds both datasets, runs both independent as-of leakage replays and writes the frozen artifacts.

## Data actually used

- **Material events:** 3,833 resolved-company material events over 51 companies and 38 tracks (322 observed company–track pairs), coverage `2016-11-01 .. 2026-10-15` (asserted against the documented end, delta 0 days).
- **Continuation dataset** (`reverse_rd_v1`): 6,701 mature examples over 25 quarterly origins (2019-10-01..2025-10-01), 3,154 positives, base rate 0.470676; 21 origins have a purged training set.
- **Entry dataset** (`first_entry_v1`): 41,003 mature examples over 24 quarterly origins (2020-01-01..2025-10-01), 503 positives, base rate 0.012267; 20 origins have a purged training set. Candidates per origin range 1,634..1,730; positives per origin range 10..28 (last three windows: 25, 27, 26). No pending origins: `t + 12m <= coverage_end` holds for every origin by construction (`skipped_pending_examples = 0`); pending behaviour is covered by synthetic tests.
- **Leakage audit (independent as-of replay, 0 mismatches):**
  - continuation: 6,701 examples, 25 cutoffs, 140,721 feature values, 0 mismatches, 0 unreplayable;
  - entry: 41,003 examples, 24 cutoffs, 1,107,081 feature values, 0 mismatches, 0 unreplayable. The replay independently recomputes all 27 entry features, including never-observed pairs, from `events`/`financial_facts` restricted to `available_at <= cutoff`.
- SEC facts: 43,420 rows over 32 companies. USAspending: 3,453 awards, 0 point-in-time usable (unchanged). The two IFRS filers (`philips`, `smith_nephew`) have zero `us-gaap` facts, so their financial features are null.

## Protocol (identical for both targets)

Expanding-window rolling origin, no random split. At origin `t` the model may train only on examples whose 12-month label window closed at or before `t` (`cutoff + 12m <= t`); identical features, algorithm (batch-GD logistic regression, 180 epochs, lr 0.15, L2 1.0, training-only median imputation and standardization) and hyperparameters in every window and ablation. The last K evaluable origins are reported as sequential holdout windows (`2025-04-01`, `2025-07-01`, `2025-10-01`). Their **test rows are disjoint** (each window is one origin), but their 12-month label windows overlap; the windows are therefore not independent replications. Mean/std across windows is a descriptive dispersion (population std), not a confidence interval. The paired bootstrap of `AP(model) − AP(pair base rate)` is repeated per window (2,000 resamples, seed 7).

## A. Continuation target — multi-window results

Per-window metrics (`rd_only` = 10 R&D features; `rd_financial` = + 11 consolidated SEC features):

| Window | Rows | Positives | Prevalence | Train rows | AP rd_only | AP rd_fin | Brier rd_only | Brier rd_fin | ECE rd_only | ECE rd_fin |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2025-04-01 | 302 | 124 | 0.410596 | 4,905 | 0.786455 | 0.786716 | 0.175084 | 0.175112 | 0.104711 | 0.089765 |
| 2025-07-01 | 304 | 123 | 0.404605 | 5,197 | 0.741223 | 0.739151 | 0.184957 | 0.184336 | 0.092174 | 0.076814 |
| 2025-10-01 | 307 | 129 | 0.420195 | 5,491 | 0.793476 | 0.792199 | 0.172134 | 0.172104 | 0.081120 | 0.073737 |
| **mean (std)** | | | | | **0.773718** (0.023156) | **0.772689** (0.023820) | **0.177392** (0.005484) | **0.177184** (0.005204) | **0.092668** (0.009637) | **0.080105** (0.006945) |

Mean across windows: FPR@0.5 0.299791 (rd_only) / 0.284903 (rd_fin); Precision@10% 0.924731 / 0.946237; mean positive-target lead 125.841642 days. The **2025-10-01 row reproduces v1 exactly** (AP 0.793476 / 0.792199; Brier 0.172134 / 0.172104; ECE 0.081120 / 0.073737; FPR 0.275281 / 0.264045; Precision@10% 0.935484 both) and the v1 leaky-label diagnostic deltas also reproduce (purged − leaky AP +0.001106 / +0.001253).

No-feature baselines on the same windows (fitted only on purged training origins; unseen keys fall back to training prevalence):

| Window | constant prevalence | company base rate | track base rate | pair base rate |
|---|---:|---:|---:|---:|
| 2025-04-01 | 0.410596 | 0.549078 | 0.507595 | 0.738690 |
| 2025-07-01 | 0.404605 | 0.540609 | 0.499553 | 0.736461 |
| 2025-10-01 | 0.420195 | 0.570689 | 0.506832 | 0.791259 |
| **mean (std)** | **0.411799** (0.006421) | **0.553459** (0.012665) | **0.504660** (0.003624) | **0.755470** (0.025323) |

Paired bootstrap `AP(model) − AP(pair base rate)`:

| Window | Δ rd_only | 95% CI rd_only | Δ rd_fin | 95% CI rd_fin |
|---|---:|---|---:|---|
| 2025-04-01 | 0.047765 | [0.006836, 0.092100] | 0.048026 | [0.005900, 0.093040] |
| 2025-07-01 | 0.004762 | [-0.034485, 0.043917] | 0.002690 | [-0.036518, 0.042217] |
| 2025-10-01 | 0.002218 | [-0.031599, 0.036774] | 0.000940 | [-0.032642, 0.035645] |
| **mean Δ** | **0.018248** | | **0.017219** | |

Only the 2025-04-01 window excludes zero; the other two include zero. The v1 conclusion still holds on the newest window: the model's ranking advantage over a one-parameter per-pair persistence baseline is not statistically detectable.

**Financial marginal value (continuation).** Per-window `rd_financial − rd_only` AP: +0.000261, −0.002071, −0.001278; mean **−0.001030**. ECE improves in every window (mean **−0.012563**), FPR@0.5 improves in every window (mean **−0.014888**), Brier mean −0.000208, Precision@10% mean +0.021505. **Ranking did not improve; only a small calibration/threshold shift replicates.**

## B. Entry target — multi-window results

Base rate 0.012267 (503 / 41,003); the three holdout windows contain 1,722 / 1,721 / 1,716 rows. Candidates per origin range 1,634..1,730 and positives 10..28 over the 24 origins.

| Window | Rows | Positives | Prevalence | Train rows | AP rd_only | AP rd_fin | Brier rd_only | Brier rd_fin | ECE rd_only | ECE rd_fin |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2025-04-01 | 1,722 | 25 | 0.014518 | 30,679 | 0.118793 | 0.132107 | 0.013800 | 0.013663 | 0.004825 | 0.004886 |
| 2025-07-01 | 1,721 | 27 | 0.015689 | 32,402 | 0.087657 | 0.096154 | 0.015082 | 0.015053 | 0.003727 | 0.003715 |
| 2025-10-01 | 1,716 | 26 | 0.015152 | 34,122 | 0.113927 | 0.116347 | 0.014298 | 0.014330 | 0.004060 | 0.004585 |
| **mean (std)** | | | | | **0.106792** (0.013675) | **0.114869** (0.014715) | **0.014393** (0.000528) | **0.014349** (0.000567) | **0.004204** (0.000460) | **0.004395** (0.000497) |

Mean across windows: Precision@10% 0.069487 (rd_only) / 0.073375 (rd_fin); mean positive-target lead 190.646819 days. **FPR@0.5 is exactly 0.000000 in every window for both models**: with a 1.5% base rate every predicted probability stays below 0.5, so that threshold metric is uninformative here and should not be read as a good result.

No-feature baselines on the same windows:

| Window | constant prevalence | company base rate | track base rate | pair base rate |
|---|---:|---:|---:|---:|
| 2025-04-01 | 0.014518 | 0.065534 | 0.047926 | 0.079463 |
| 2025-07-01 | 0.015689 | 0.049114 | 0.031172 | 0.047244 |
| 2025-10-01 | 0.015152 | 0.041736 | 0.032312 | 0.027826 |
| **mean (std)** | **0.015119** (0.000478) | **0.052128** (0.009947) | **0.037136** (0.007643) | **0.051511** (0.021296) |

Paired bootstrap `AP(model) − AP(pair base rate)`:

| Window | Δ rd_only | 95% CI rd_only | Δ rd_fin | 95% CI rd_fin |
|---|---:|---|---:|---|
| 2025-04-01 | 0.039329 | [-0.118469, 0.213820] | 0.052644 | [-0.102720, 0.222919] |
| 2025-07-01 | 0.040413 | [-0.054323, 0.165076] | 0.048910 | [-0.041020, 0.169352] |
| 2025-10-01 | 0.086101 | [0.008276, 0.219389] | 0.088520 | [0.016255, 0.219491] |
| **mean Δ** | **0.055281** | | **0.063358** | |

The point estimate beats per-pair persistence in every window, but the 2025-04-01 and 2025-07-01 intervals are very wide and include zero; only 2025-10-01 excludes zero. With 25–27 positives per window that is expected, and it is not evidence of a stable effect.

**Financial marginal value (entry).** Per-window `rd_financial − rd_only` AP: **+0.013315, +0.008496, +0.002420**; mean **+0.008077**. Brier mean −0.000044, ECE mean +0.000191, Precision@10% mean +0.003887. This is the one ablation in v1/v2 where consolidated financial features add a positive and consistently signed ranking delta — but three overlapping windows with ~25 positives each are far too few to call it stable.

**Per-origin variance (entry).** Across the 19 non-holdout evaluated origins the AP ranges from **0.018130** (2021-01-01, the first origin with a single training origin) to **0.237008** (2023-07-01), mean 0.115007, std 0.057940 (rd_only); mean 0.117769, std 0.055416 (rd_financial). Most of the skill appears from 2022 onwards, when several matured training origins exist; the earliest origins are essentially at chance. A single headline AP for this target would be misleading, which is why the multi-window protocol is required.

**Pair-base-rate caveat.** For entry candidates the per-pair persistence baseline is *not* degenerate in the way one might expect: 99.3%–99.5% of holdout rows have a pair that appeared in matured training rows (`pair_base_rate_coverage` 0.993031 / 0.993608 / 0.994755), so the baseline is a genuine per-pair candidate rate. It is degenerate only for pairs appearing for the first time in a holdout window (0.5%–0.7% of rows), which fall back to training prevalence.

**Purge diagnostic (entry).** Purged minus leaky (`delta_purged_minus_leaky`): AP +0.002962 (rd_only) / +0.003416 (rd_fin), Brier +0.000097 / +0.000121, ECE −0.001063 / +0.001277, development AP −0.000267 / −0.002725. Unlike the v1 continuation target, the purge changes little for entry: a candidate dormant for ≥36 months cannot have a 12-month training label window overlapping the test events (the construction already separates them in event time). The v1 continuation diagnostic reproduces the previously reported bias exactly.

## Negative results and what did not improve

- **Entry target is hard and modestly predictable.** Mean AP across windows is 0.106792 (rd_only) / 0.114869 (rd_financial) against a 0.015119 constant-prevalence baseline; the model beats per-pair persistence on average but only one of three windows excludes zero. This is a weak-signal target, not a validated predictor.
- **Continuation target did not improve.** Multi-window AP is 0.773718 (rd_only) / 0.772689 (rd_financial); the model-vs-pair interval includes zero in two of three windows. Adding consolidated financial features still does **not** improve continuation ranking (mean Δ AP −0.001030), confirming the v1 negative result.
- **Financial features help entry ranking but weakly and unstably** (mean Δ AP +0.008077; individual windows +0.013315 / +0.008496 / +0.002420). This is a hypothesis, not a finding.
- **FPR@0.5 is uninformative for entry** (0.000000 everywhere because predicted probabilities never cross 0.5); report Precision@10% instead.
- **Early entry origins are at chance** (AP 0.018130 at 2021-01-01) because almost no matured training data exists yet; pooling origins hides this.
- **The candidate universe is dominated by never-observed pairs.** 322 pairs have ever been observed versus a 51 × 38 = 1,938 cross product; most candidates are pairs that may never have been active, which is exactly the left-censoring the target documents and cannot be resolved with this data.
- **No causal claim.** Neither target measures internal R&D start, product revenue, or a causal market→R&D mechanism. The entry label is a *first observed public milestone*, not a discovered project.

## Residual limitations

- openFDA bulk availability is `decision_date + 14 days` (estimated); decision dates are date-level, not first-publication timestamps.
- "Dormant" is only observable inside the 2016-11-01..2026-10-15 bulk window; pre-2016 activity is unobserved (`rd_pair_inactive_months` is capped at 120 months, and a never-observed pair receives the cap).
- The track taxonomy is the current curated product-code mapping applied to history; it is not versioned, so "tracks observed by t" uses current knowledge.
- 51 curated companies are not an industry-wide random sample; the two IFRS filers have no US-GAAP financial features.
- Three overlapping holdout windows are not three independent replications. The paired-bootstrap intervals are wide by construction; a null or positive window delta should not be generalized.
- The leakage replay is an as-of consistency audit, not a proof of absence of semantic leakage (unversioned mappings, aliases, target-definition choices are not detectable this way).

## C. Phase 2 feature-group ablation (v0.4.0)

New sources evaluated on the identical rows, purge and multi-window protocol (`holdouts=3`), one specification per run, same logistic model and hyperparameters:

- **Market features (8 + missing flag):** daily Yahoo-adjusted closes imported read-only from the base MedRadar `prices` table into `market_bars` (95,725 bars, 38/44 mapped tickers + SPY/XBI, 2016-10-31..2026-10-30). Features at cutoff `t` use bars with `date <= t` only: 12-month return, 12-month volatility, 12-month max drawdown, return vs SPY, return vs XBI, 3-month volume z-score, SPY-above-200d regime flag, days since 12-month high. Complete on 5,206/6,701 continuation examples (77.7%) and 245/307 final-holdout rows; missing tickers receive `None` + `mkt_missing=1`. Market capitalisation and valuation multiples are **not** implemented (no shares-outstanding data), and stock returns are not treated as technological capability.
- **Publication features (5, OpenAlex):** annual work counts from raw-affiliation alias searches for 51/51 curated companies (150,087 works, 2014–2026); at cutoff `t` only complete years `<= year(t)-1` are used with a 15-Feb knowledge lag (`pub_count_prev_year`, `pub_count_3y`, `pub_growth_prev_year`, `pub_intensity_vs_company`, `pub_missing`). Alias matching is noisy and is a weak signal, not evidence of approved R&D projects.
- **Excluded:** procurement (the current USAspending snapshot is not point-in-time usable, `pit_usable=0`) and patents (USPTO Open Data Portal requires an API key; adapter implemented, **no rows collected or evaluated**).

Specifications — continuation: A `rd_only` (reference), B `+financial`, C `+market`, D `+publication`, E `+financial+market+publication`. Entry: A shared R&D only (Phase 1 parity), B shared+financial (Phase 1 parity), C shared+entry-specific, D shared+entry+financial (reference), E D+market, F D+publication, G D+market+publication.

**Continuation target** (holdout 2025-10-01, n=307 / 129 positives; AP window mean over 2025-04/07/10):

| Spec | Features | AP | Brier | ECE-10 | FPR@0.5 | P@10% | AP window mean (std) |
|---|---:|---:|---:|---:|---:|---:|---:|
| A rd_only | 10 | **0.793476** | 0.172134 | 0.081120 | 0.275281 | 0.935484 | **0.773718** (0.023156) |
| B +financial | 21 | 0.792199 | 0.172104 | 0.073737 | 0.264045 | 0.935484 | 0.772689 (0.023820) |
| C +market | 18 | 0.792020 | 0.171955 | 0.080433 | 0.269663 | 0.935484 | 0.771247 (0.023441) |
| D +publication | 15 | 0.793349 | 0.172047 | 0.086677 | 0.286517 | 0.935484 | 0.771593 (0.024131) |
| E all available | 34 | 0.786696 | 0.172341 | **0.062777** | **0.247191** | 0.935484 | 0.768162 (0.024795) |

Marginal deltas vs A: financial AP **−0.001278** (window mean −0.001030), market **−0.001456** (−0.002471), publication **−0.000128** (−0.002125), all **−0.006780** (−0.005556). The only replicating improvement is calibration/threshold: E lowers ECE by 0.018343 and FPR by 0.028090 while losing ranking. **No added source improves continuation ranking, and the v1 negative conclusion stands.**

**Entry target** (holdout 2025-10-01, n=1,716 / 26 positives; AP window mean over the same three windows):

| Spec | Features | AP | Brier | ECE-10 | P@10% | AP window mean (std) |
|---|---:|---:|---:|---:|---:|---:|
| A shared only (parity) | 10 | **0.113927** | 0.014298 | 0.004060 | 0.063953 | 0.106792 (0.013675) |
| B shared+financial (parity) | 21 | **0.116347** | 0.014330 | 0.004585 | **0.081395** | 0.114869 (0.014715) |
| C shared+entry | 16 | 0.100476 | 0.014315 | 0.003184 | 0.069767 | 0.110862 (0.018675) |
| D shared+entry+financial | 27 | 0.102205 | 0.014361 | 0.003232 | 0.069767 | 0.118180 (0.022483) |
| E D+market | 35 | 0.096865 | 0.014459 | 0.003347 | 0.075581 | **0.119426** (0.026396) |
| F D+publication | 32 | 0.105083 | 0.014351 | 0.002568 | 0.075581 | 0.119135 (0.021890) |
| G D+market+publication | 40 | 0.097863 | 0.014450 | 0.003254 | 0.075581 | **0.119658** (0.025998) |

Marginal deltas vs D: entry-specific C **−0.001729**, market E **−0.005340**, publication F **+0.002879**, all G **−0.004341**; window-mean deltas are +0.001245 (E), +0.000955 (F), +0.001478 (G). The final holdout favours the Phase-1 shared-only cells A/B, while the window mean favours D/E/G; the differences (≤0.015 AP) are small relative to the window std (0.014–0.026). **Entry-specific features did not add a stable ranking gain, and no new source produced one either.** FPR@0.5 remains uninformative for entry; use Precision@10% (B 0.0814 highest on the final holdout).

Frozen machine-readable values: [`ablation_metrics.json`](ablation_metrics.json). Regenerate a cell with `python experiments/reverse_rd_v2/run_ablation.py --db data/medradar.sqlite --target continuation --spec C --out <cell>.json` and merge with `python experiments/reverse_rd_v2/merge_ablation.py --cells <dir> --out experiments/reverse_rd_v2/ablation_metrics.json`. The Phase 1 A/B cells are read from [`continuation_metrics.json`](continuation_metrics.json)/[`entry_metrics.json`](entry_metrics.json) so the parity numbers cannot drift.

**Honest bottom line for v0.4.0:** across both targets and all available added sources (consolidated SEC financials, PIT market features, OpenAlex publications), the only replicating effect is a small calibration/FPR shift from financial features and from the all-source continuation model; no source adds a statistically detectable ranking improvement, and the entry target's apparent skill is weak and window-dependent. Procurement and patents are excluded for documented reasons, not because they were tested and failed.

