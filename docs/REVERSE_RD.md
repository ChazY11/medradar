# Market-to-R&D Intelligence / Reverse R&D v1

## What is implemented

This branch adds a separate Market Intelligence layer on the existing SQLite database. It does not replace the FDA, clinical-trial, SEC-event, report or trading paths.

- `sec_financials.py`: SEC ticker→CIK resolution and XBRL Company Facts. Revenue, R&D, cash flow, cash, inventory, capex and acquisition observations retain period end and `filed` knowledge time, including amendments.
- `procurement_us.py`: real USAspending contract awards with buyer, supplier, NAICS category, obligation, performance dates, source URL and company-resolution evidence.
- `company_identifiers` and `temporal_edges`: deterministic CIK/ticker links and observed company–contract/filing relations. Model-inferred investment relations are not inserted as facts.
- `forecast_examples`: quarterly company–track examples with dual-time filtering and a defined 12-month public FDA milestone target. Two targets share the table: v1 continuation (`dataset_version='reverse_rd_v1'`) and the v2 entry target (`dataset_version='first_entry_v1'`).
- `LogisticBaseline`: fixed, dependency-free logistic regression with training-only median imputation and standardization.
- `backtesting.py`: expanding-window rolling-origin evaluation and a final chronological holdout. `run_backtest(holdouts=K)` reports the last K evaluable origins as sequential holdout windows plus per-window mean/std; the default `holdouts=1` reproduces v1 exactly.
- `horizon.py`: probability forecasts registered with model version, cutoff, uncertainty, supporting/contradictory feature contributions and a machine-checkable future event condition.
- `calibration.py`: Brier/ECE/PR-AUC once enough registered forecasts have matured.

## Data meanings that must not be blurred

**SEC Company Facts is not product revenue.** Facts are marked `consolidated` and `companyfacts_no_segment_dimension`. Company Facts does not reliably expose the segment dimensions needed for product-line sales. No code in v1 turns total company revenue into medical-device or product revenue. Segment-footnote parsing remains separate future work.

**USAspending Award Amount is an obligation.** It is not a tender budget, delivery, cash receipt or recognized revenue. The search response exposes performance dates and a last-modified timestamp, not first-publication history. Rows therefore use retrieval time as knowledge time and `pit_usable=0`. They support source validation, current demand descriptions and future prospective collection, not retrospective predictive-gain claims.

**The shared `events` table is overwritten by the bulk lane.** `pipeline collect --source fda` writes the same `event_id`s as the legacy paged collector (`python -m medradar collect --sources device`) with `INSERT OR REPLACE`, but with different knowledge time: the bulk lane stores `decision_date + 14 days` with `timestamp_quality='estimated'`, while the paged lane stores `published_at or event_date`. Re-running the bulk lane can therefore silently change `available_at` for existing rows and thus the point-in-time features derived from them. This is intended when reproducing the frozen experiment, but it is a semantic change, not a no-op, and the two lanes must not be mixed within one backtest.

**Two SEC companies file IFRS, not US-GAAP.** `philips` and `smith_nephew` resolve to a CIK but have zero `us-gaap` facts in Company Facts, so all consolidated financial features are null for them. Siemens, Terumo and Fujifilm are absent because they have no US ticker in `company_tickers.json`. Missing financial features are imputed to the training median with a missing indicator; they are never fabricated.

**A regulatory milestone is a lagging R&D proxy.** A future 510(k)/PMA does not reveal when internal research began. v1 predicts continued public activity in an already-active company–track pair. v2 adds first-entry prediction as an explicitly separate, left-censored target (see below); it is never silently substituted for continuation, and neither target measures internal R&D start.

## Reproduce

Exact commands for the frozen v1 aggregates. `MEDRADAR_HOME` relocates `data/`, `out/` and the HTTP cache; the defaults are below the repository root. Python 3.12 was used; the `[bulk]` extra is required by the streaming openFDA importer and was omitted by earlier drafts of this recipe.

```bash
# 0. Install the collector extra (ijson) used by the openFDA bulk streaming lane.
python -m pip install -e '.[bulk]'

# 1. openFDA 510(k)/PMA bulk exports, ten-year window. Streams the official
#    archives; availability = decision_date + 14 days, timestamp_quality=estimated.
python -m medradar.intelligence.pipeline collect --source fda --months 120 \
  --out data/out/reverse_rd/data_provenance.json

# 2. SEC Company Facts for the curated device registry (filed is knowledge time).
python -m medradar.intelligence.pipeline collect --source sec \
  --out data/out/reverse_rd/data_provenance.json

# 3. USAspending incumbent-contract obligations (descriptive, pit_usable=0).
python -m medradar.intelligence.pipeline collect --source procurement \
  --start-date 2016-01-01 --max-pages 2 \
  --out data/out/reverse_rd/data_provenance.json

# 4. Frozen v1: examples, purged rolling evaluation, persistence baselines,
#    as-of leakage replay and horizon forecasts. Writes/publishes the artifacts.
python -m medradar.intelligence.pipeline research --horizon 12 --top-n 25 \
  --db data/medradar.sqlite \
  --provenance experiments/reverse_rd_v1/data_provenance.json \
  --out data/out/reverse_rd --publish-experiment experiments/reverse_rd_v1

# 5. Offline checks.
python -m pytest
python3 verifier/v1/verify.py
```

**v2 (Phase 1).** The v2 aggregates are regenerated from the same collected database and do not touch `experiments/reverse_rd_v1/`:

```bash
# Builds the entry dataset (dataset_version='first_entry_v1'), runs both leakage
# audits, evaluates continuation and entry with holdouts=3, writes config.json,
# data_provenance.json, continuation_metrics.json and entry_metrics.json.
python experiments/reverse_rd_v2/run_v2.py --db data/medradar.sqlite --holdouts 3
```

`experiments/reverse_rd_v2/run_timings.json` records wall-clock timings of the run; it is informational only. The numbers in `experiments/reverse_rd_v2/REPORT.md` and `docs/PHASE1.md` are read from `continuation_metrics.json` / `entry_metrics.json`.

The exact `--db` path is the default (`data/medradar.sqlite`); with `MEDRADAR_HOME` set, pass that home's database explicitly. The paged-API lane (`python -m medradar collect --sources device`) is a different ingest with different availability semantics and does **not** reproduce the frozen metrics.

Raw bulk archives, the SQLite database, the HTTP cache and `out/` are not committed (`data/` and `out/` are ignored); the cache/tmp artifacts are reproducible by re-running the commands and are not required to trust the committed aggregates. Committed under `experiments/reverse_rd_v1/` are only small aggregates: `config.json`, `metrics.json`, `forecasts.json`, `procurement_summary.json`, `data_provenance.json` and `REPORT.md`.

## Evaluation contract

Features at quarterly cutoff `t` require both `event_date <= t` and `available_at <= t`. Financial observations additionally require `filed <= t`; later amendments cannot change an earlier feature row. Labels use material public FDA events with `t < event_date <= t+12 months`. Only origins whose complete horizon lies inside observed FDA coverage receive labels.

**Purge/embargo.** The default rolling-origin training rule is `cutoff + horizon_months <= origin`: an example only trains an origin once its label window has closed before the test window opens. Without this rule the previous 1–3 quarters of training labels overlap the test window by up to nine months and the calibration metrics are optimistic. `metrics.json` reports the purged specification under `models` (the headline numbers) and the old overlapping-label variant under `leaky_labels_diagnostic` purely to quantify that bias; the diagnostic is not a result to cite.

The last origin is the holdout. Earlier origins use expanding training windows. Both ablations see identical rows and use the same fixed optimizer. Metrics are PR-AUC, Brier score, 10-bin ECE, false-positive rate at 0.5, Precision@ceil(10%N), mean target lead time and per-origin PR-AUC stability. Negative results remain in `metrics.json`; a single holdout is not evidence of a causal market→R&D mechanism.

**Persistence baselines.** A headline PR-AUC must be compared with no-feature predictors on the same holdout, fitted only on purged training origins: constant training prevalence, company base rate, track base rate and per-pair historical base rate. The per-pair persistence benchmark and a deterministic paired bootstrap (2,000 resamples, fixed seed) of `PR-AUC(model) - PR-AUC(pair base rate)` are reported in `metrics.json` (`baselines`, `model_vs_pair_baseline`). If the interval includes zero, the ten R&D features add no statistically detectable ranking value beyond stable per-pair activity persistence.

**Leakage audit scope.** `leakage_audit` replays each stored example's features directly from `events`/`financial_facts` with SQL restricted to information available at the cutoff (events: `event_date <= cutoff AND available_at <= cutoff`; financials: `available_at <= cutoff AND period_end <= cutoff`, latest filed row per period) and compares them with the stored feature JSON. For `dataset_version='first_entry_v1'` it additionally replays the six entry-specific features and the base features of never-observed pairs (zero counts, recency top-code, zero observable active years). This detects stored features that could not have been produced from as-of information and is a genuine improvement over re-reading the builder's own declaration. It is still an *as-of replay / consistency* audit: it cannot prove the absence of semantic leakage from unversioned current product-code mappings, aliases or target-definition choices applied to history, and it does not re-verify the provenance of the dates themselves.

## Entry (dormant → active) target

`build_entry_examples` (in `features/research_features.py`) adds a harder, decision-relevant question to the same `forecast_examples` table under `dataset_version='first_entry_v1'`. No schema change: the existing `label`, `maturity`, `first_target_event_date` and `target_event_count` columns carry the entry label, and the feature JSON carries the feature set.

**Material event definition (identical to v1).** Any 510(k) resolved to a curated company and track, plus PMA rows whose `supplement_number` is empty/`0`/`S0` or whose `supplement_type` contains "PANEL TRACK". The bulk lane ends 2026-10-15; that end is asserted, not assumed.

**Exact label.** At a quarterly quarter-start cutoff `t`:

- *Candidate*: a `(company_key, track_id)` pair where the company already has at least one material event with `event_date <= t` (an active company), `track_id` is non-null, and the pair has **zero** material events in `(t - 36 months, t]`. The candidate universe is the cross product of active companies and tracks observed by `t`, so pairs that were never observed at all are candidates.
- *Origins*: quarter-start cutoffs with `t - 36 months >= coverage_start` and `t + 12 months <= coverage_end`. On the frozen data `coverage_start = 2016-11-01`, `coverage_end = 2026-10-15`, giving 24 origins from 2020-01-01 to 2025-10-01. Dormancy uses exact calendar months (`add_months`), not a 1095-day approximation, so an event at exactly `t - 36 months` counts as dormant while one day later does not.
- *Label*: 1 iff a material event exists for the same pair in `(t, t + 12 months]` (both ends inclusive at `t + 12 months`). The row is `mature` iff `t + 12 months <= coverage_end`; otherwise the label is `null` and the row is `pending`. The default is to omit pending origins, not to guess their labels.
- All features use rows with `event_date <= t` **and** `available_at <= t`; financial features require `filed/available_at <= t`. This is the same point-in-time rule as v1.

**Features.** The ten v1 R&D-history features are computed by a shared helper used by both targets (a pair with no observed history gets zero counts, the recency top-code and zero observable active years, which the leakage replay independently reproduces). The eleven consolidated SEC features are unchanged. Six entry-specific features are added:

| Feature | Definition at cutoff `t` |
|---|---|
| `rd_pair_inactive_months` | Months (`days / 30.4375`) since the last observed material event of the pair, capped at **120 months** (the length of the observable bulk window). A never-observed pair receives the cap, meaning "at least this dormant", not "exactly this old". |
| `rd_company_active_tracks_12m` | Distinct tracks in which the company had a material event in `(t - 12m, t]`. |
| `rd_company_active_tracks_delta` | Same count for `(t - 12m, t]` minus the count for `(t - 24m, t - 12m]`. |
| `rd_track_active_companies_12m` | Distinct companies with a material event in that track in `(t - 12m, t]`. |
| `rd_track_active_companies_delta` | Same count for `(t - 12m, t]` minus `(t - 24m, t - 12m]`. |
| `rd_company_track_novelty_share` | Share of the company's material events in `(t - 24m, t]` that fall in tracks whose first observed company event is inside that same 24-month window (0.0 when the company had no event in the window). |

**Left-censoring statement.** The openFDA bulk window starts 2016-11-01. "Dormant" therefore means **no event observed inside the bulk window**, never "provably inactive": a pair first observed in 2018 may have had unobserved pre-2016 activity, and a never-observed pair may have been active before 2016 or be a genuinely new track entry. The target is first *observed* public entry inside the window, not internal R&D start, not product launch, and not a claim that the company was not already working in that track. Because the observable dormancy clock cannot start before `coverage_start`, early origins have less dormancy evidence than later ones, and the 120-month cap is a top-code, not a measurement.

**Multi-window protocol.** `run_backtest(..., holdouts=K)` evaluates the last K origins that have a purged training set as sequential holdout windows. Each window retrains with an expanding training set containing only examples whose 12-month label window closed at or before that origin (`cutoff + horizon_months <= origin`), and uses identical features, algorithm and hyperparameters. Test rows are disjoint because each window is a single origin; the 12-month label windows of adjacent origins overlap almost entirely, so the windows are *not* independent replications of a causal effect. Reported per window and as mean/std across windows (population standard deviation — a descriptive spread, not a confidence interval): PR-AUC, Brier, ECE-10, FPR@0.5, Precision@ceil(10%N), prevalence, plus the same no-feature baselines and the paired bootstrap of `AP(model) - AP(pair base rate)`. `holdouts=1` reproduces the v1 single-holdout output exactly (the multi-window fields are additive).

## Forecast verification

Each forecast stores `event_date_after`, `event_date_on_or_before`, company, track, event kinds and minimum coverage end. `verify_forecasts` leaves it pending until both wall-clock time and source coverage pass the horizon. It then writes outcome, verification time and matching event ID. No LLM generates probabilities.

Feature contributions are labelled on both scales: `contribution = coefficient * standardized_value`, where `standardized_value` is the z-scored design input. Each evidence record carries `raw_value` (the stored feature, null when absent), `standardized_value`, `median_imputed` (true when the training median replaced a missing raw value) and `coefficient`; `value` is retained as a backward-compatible alias of `raw_value`. A null raw value can therefore still have a nonzero contribution — that is the training median imputed at the model's z-scale, not a data value.

## Current boundaries

- No market-price, patent, publication, UK procurement or jobs features are in v1. Adapters should only be added after point-in-time availability and licensing are demonstrated.
- `CrossDomainCompanyResolver` was dead code and has been removed; company resolution uses the curated registry directly in the SEC and USAspending collectors.
- Static product-code/track mappings are current curated knowledge, not historical mapping versions. This is a documented metadata limitation and is not covered by the leakage replay.
- OpenFDA publication lag is date-level. Forecast horizons are monthly/quarterly, not intraday.
- Procurement coverage is recipient-search and NAICS dependent; zero search results do not prove zero demand.
- Company aliases are incomplete and acquisitions change ownership over time. Unmatched suppliers remain null.
- v1 evaluates association and incremental prediction. It does not establish that sales, procurement or prices cause research decisions.
- The entry target's candidate universe uses the *current* curated product-code/track taxonomy applied to historical events, so "tracks observed by `t`" is current knowledge, not a versioned historical ontology.
- Entry candidates are dominated by pairs that were never observed inside the bulk window (322 ever-observed pairs versus a 51 × 38 cross product); that is the honest left-censored population, and it makes the entry base rate near 1%. The per-pair persistence baseline is nevertheless computable for 99.3–99.5% of entry holdout rows because candidate pairs recur across origins; only pairs appearing for the first time in a holdout window fall back to training prevalence.
- Entry positives per origin are few (order 10–30), so per-window AP/Brier intervals are wide and three windows are not an independent replication.
- Multi-window holdouts share overlapping 12-month label windows; mean/std across windows describes window-to-window dispersion, not sampling uncertainty.
