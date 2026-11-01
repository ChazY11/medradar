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

**A regulatory milestone is a lagging R&D proxy.** A future 510(k)/PMA does not reveal when internal research began. v1 predicts continued public activity in an already-active company–track pair. First-entry prediction needs a longer left-censoring audit and is not silently substituted.

## Reproduce

```bash
# Existing real FDA events; HTTP responses are cached and runs are resumable.
python -m medradar collect --sources device --months 120 --limit 0

# Real SEC and USAspending collection into the same SQLite file.
python -m medradar.intelligence.pipeline collect --source sec
python -m medradar.intelligence.pipeline collect --source procurement \
  --start-date 2016-01-01 --max-pages 2

# Frozen v1: build examples, leakage audit, rolling evaluation and forecasts.
python -m medradar.intelligence.pipeline research --horizon 12

# Offline checks.
python -m pytest
python3 verifier/v1/verify.py
```

Bulk responses, SQLite, dataset rows and runtime output remain ignored under `data/` and `out/`. Small aggregated results and the frozen configuration live in `experiments/reverse_rd_v1/`.

## Evaluation contract

Features at quarterly cutoff `t` require both `event_date <= t` and `available_at <= t`. Financial observations additionally require `filed <= t`; later amendments cannot change an earlier feature row. Labels use material public FDA events with `t < event_date <= t+12 months`. Only origins whose complete horizon lies inside observed FDA coverage receive labels.

The last origin is the holdout. Earlier origins use expanding training windows. Both ablations see identical rows and use the same fixed optimizer. Metrics are PR-AUC, Brier score, 10-bin ECE, false-positive rate at 0.5, Precision@ceil(10%N), mean target lead time and per-origin PR-AUC stability. Negative results remain in `metrics.json`; a single holdout is not evidence of a causal market→R&D mechanism.

## Forecast verification

Each forecast stores `event_date_after`, `event_date_on_or_before`, company, track, event kinds and minimum coverage end. `verify_forecasts` leaves it pending until both wall-clock time and source coverage pass the horizon. It then writes outcome, verification time and matching event ID. No LLM generates probabilities.

## Current boundaries

- No market-price, patent, publication, UK procurement or jobs features are in v1. Adapters should only be added after point-in-time availability and licensing are demonstrated.
- Static product-code/track mappings are current curated knowledge, not historical mapping versions. This is a documented metadata limitation.
- OpenFDA publication lag is date-level. Forecast horizons are monthly/quarterly, not intraday.
- Procurement coverage is recipient-search and NAICS dependent; zero search results do not prove zero demand.
- Company aliases are incomplete and acquisitions change ownership over time. Unmatched suppliers remain null.
- v1 evaluates association and incremental prediction. It does not establish that sales, procurement or prices cause research decisions.
