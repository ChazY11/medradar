# Changelog

All notable changes to MedRadar. Format loosely follows Keep a Changelog.
This is a research tool; "fixed" means a documented behaviour changed.

## [0.1.0] — 2026-10-31

### Added
- Unified `events` fact table (510(k), PMA, recall, drug approval, trial,
  NMPA registration) with a single metrics contract (`docs/SCHEMA.md`).
- Company/subsidiary registry (89 names) and a Chinese track dictionary
  (38 tracks, 1,958 mapped product codes).
- Metrics engine: Gamma-Poisson shrinkage, observed-exposure baselines,
  Jensen-Shannon mix shift, first-occurrence novelty, recall clusters.
- Chinese report + self-contained HTML dashboard, English one-pager, summary CSV.
- Event study and simulated long-only book on real daily bars (`paper`).
- Live lane: SEC EDGAR 8-K feed, full-text backfill, FDA RSS, ClinicalTrials.gov
  status changes, simulated fills at real quotes with 10 bps slippage.
- LLM judge for 8-K materiality (OpenAI-compatible endpoint), content-hash cache,
  per-cycle budget, evidence-quote enforcement, heuristic fallback.
- Calibration on 25 hand-labelled real filings (`docs/CALIBRATION.md`).
- 139 offline tests; CI workflow; Pages deploy via artifact upload.

### Fixed
- Baseline exposure now uses observed quarters (removed a 40x THI artefact).
- PMA activity counts material submissions only (78% are admin supplements).
- Recall dedupe by `res_event_number`; payload truncation now yields valid JSON.
- openFDA deep-page 404 now splits the window instead of silently truncating.
- `--no-trade` freezes exits as well as entries.
- Position sizing uses the slipped fill price, so cash cannot go negative.
- Stale/closed-market quotes can mark the book but never fill an order.
- Only the fresh EDGAR feed may open a position; derived/backfilled sources are
  alert-only. Cross-source duplicate alerts are collapsed per (ticker, day, kind).

### Known limitations
- `config/` is read from the source tree; wheel packaging of config is pending.
- Free quotes are delayed; the lane is minute-level, not intraday.
- Shorts are alerted but not traded (borrow/squeeze not modelled).
- NMPA data must be supplied as a CSV (the official site is behind a WAF).
