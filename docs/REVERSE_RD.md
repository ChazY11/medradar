# Market-to-R&D Intelligence / Reverse R&D v1

## What is implemented

This branch adds a separate Market Intelligence layer on the existing SQLite database. It does not replace the FDA, clinical-trial, SEC-event, report or trading paths.

- `sec_financials.py`: SEC ticker→CIK resolution and XBRL Company Facts. Revenue, R&D, cash flow, cash, inventory, capex and acquisition observations retain period end and `filed` knowledge time, including amendments.
- `procurement_us.py`: real USAspending contract awards with buyer, supplier, NAICS category, obligation, performance dates, source URL and company-resolution evidence.
- `company_identifiers` and `temporal_edges`: deterministic CIK/ticker links and observed company–contract/filing relations. Model-inferred investment relations are not inserted as facts.
- `forecast_examples`: quarterly company–track examples with dual-time filtering and a defined 12-month public FDA milestone target.
- `LogisticBaseline`: fixed, dependency-free logistic regression with training-only median imputation and standardization.
- `backtesting.py`: expanding-window rolling-origin evaluation and a final chronological holdout.
- `horizon.py`: probability forecasts registered with model version, cutoff, uncertainty, supporting/contradictory feature contributions and a machine-checkable future event condition.
- `calibration.py`: Brier/ECE/PR-AUC once enough registered forecasts have matured.

## Data meanings that must not be blurred

**SEC Company Facts is not product revenue.** Facts are marked `consolidated` and `companyfacts_no_segment_dimension`. Company Facts does not reliably expose the segment dimensions needed for product-line sales. No code in v1 turns total company revenue into medical-device or product revenue. Segment-footnote parsing remains separate future work.

**USAspending Award Amount is an obligation.** It is not a tender budget, delivery, cash receipt or recognized revenue. The search response exposes performance dates and a last-modified timestamp, not first-publication history. Rows therefore use retrieval time as knowledge time and `pit_usable=0`. They support source validation, current demand descriptions and future prospective collection, not retrospective predictive-gain claims.

**The shared `events` table is overwritten by the bulk lane.** `pipeline collect --source fda` writes the same `event_id`s as the legacy paged collector (`python -m medradar collect --sources device`) with `INSERT OR REPLACE`, but with different knowledge time: the bulk lane stores `decision_date + 14 days` with `timestamp_quality='estimated'`, while the paged lane stores `published_at or event_date`. Re-running the bulk lane can therefore silently change `available_at` for existing rows and thus the point-in-time features derived from them. This is intended when reproducing the frozen experiment, but it is a semantic change, not a no-op, and the two lanes must not be mixed within one backtest.

**Two SEC companies file IFRS, not US-GAAP.** `philips` and `smith_nephew` resolve to a CIK but have zero `us-gaap` facts in Company Facts, so all consolidated financial features are null for them. Siemens, Terumo and Fujifilm are absent because they have no US ticker in `company_tickers.json`. Missing financial features are imputed to the training median with a missing indicator; they are never fabricated.

**A regulatory milestone is a lagging R&D proxy.** A future 510(k)/PMA does not reveal when internal research began. v1 predicts continued public activity in an already-active company–track pair. First-entry prediction needs a longer left-censoring audit and is not silently substituted.

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

The exact `--db` path is the default (`data/medradar.sqlite`); with `MEDRADAR_HOME` set, pass that home's database explicitly. The paged-API lane (`python -m medradar collect --sources device`) is a different ingest with different availability semantics and does **not** reproduce the frozen metrics.

Raw bulk archives, the SQLite database, the HTTP cache and `out/` are not committed (`data/` and `out/` are ignored); the cache/tmp artifacts are reproducible by re-running the commands and are not required to trust the committed aggregates. Committed under `experiments/reverse_rd_v1/` are only small aggregates: `config.json`, `metrics.json`, `forecasts.json`, `procurement_summary.json`, `data_provenance.json` and `REPORT.md`.

## Evaluation contract

Features at quarterly cutoff `t` require both `event_date <= t` and `available_at <= t`. Financial observations additionally require `filed <= t`; later amendments cannot change an earlier feature row. Labels use material public FDA events with `t < event_date <= t+12 months`. Only origins whose complete horizon lies inside observed FDA coverage receive labels.

**Purge/embargo.** The default rolling-origin training rule is `cutoff + horizon_months <= origin`: an example only trains an origin once its label window has closed before the test window opens. Without this rule the previous 1–3 quarters of training labels overlap the test window by up to nine months and the calibration metrics are optimistic. `metrics.json` reports the purged specification under `models` (the headline numbers) and the old overlapping-label variant under `leaky_labels_diagnostic` purely to quantify that bias; the diagnostic is not a result to cite.

The last origin is the holdout. Earlier origins use expanding training windows. Both ablations see identical rows and use the same fixed optimizer. Metrics are PR-AUC, Brier score, 10-bin ECE, false-positive rate at 0.5, Precision@ceil(10%N), mean target lead time and per-origin PR-AUC stability. Negative results remain in `metrics.json`; a single holdout is not evidence of a causal market→R&D mechanism.

**Persistence baselines.** A headline PR-AUC must be compared with no-feature predictors on the same holdout, fitted only on purged training origins: constant training prevalence, company base rate, track base rate and per-pair historical base rate. The per-pair persistence benchmark and a deterministic paired bootstrap (2,000 resamples, fixed seed) of `PR-AUC(model) - PR-AUC(pair base rate)` are reported in `metrics.json` (`baselines`, `model_vs_pair_baseline`). If the interval includes zero, the ten R&D features add no statistically detectable ranking value beyond stable per-pair activity persistence.

**Leakage audit scope.** `leakage_audit` replays each stored example's 21 features directly from `events`/`financial_facts` with SQL restricted to information available at the cutoff (events: `event_date <= cutoff AND available_at <= cutoff`; financials: `available_at <= cutoff AND period_end <= cutoff`, latest filed row per period) and compares them with the stored feature JSON. This detects stored features that could not have been produced from as-of information and is a genuine improvement over re-reading the builder's own declaration. It is still an *as-of replay / consistency* audit: it cannot prove the absence of semantic leakage from unversioned current product-code mappings, aliases or target-definition choices applied to history, and it does not re-verify the provenance of the dates themselves.

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
