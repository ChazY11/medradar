# Changelog

All notable changes to MedRadar. Format loosely follows Keep a Changelog.
This is a research tool; "fixed" means a documented behaviour changed.

## [0.2.0] — 2026-10-31 (data & case library)

### Added
- **Full-history backfill**: 510(k) 176,466 (1976→2026), PMA 57,372 (1968→2026),
  recalls 59,646 (2002→2026), drug approvals 5,326 (1966→2026), trials 55,592
  (1999→2026) — **363,177 events**, 1.2 GiB SQLite.
- **EDGAR historical catalyst corpus v2, fully fetched**: 20,976 8-K filings
  (2015–2026, 16 phrase buckets, 100% of candidates, 0 fetch failures) with
  verbatim text and source URLs.
- **Case library**: **2,384 traceable cases** with verbatim evidence (3,700+ quotes),
  1/5/20/60-day SPY-abnormal reactions, hit/miss outcomes and negative examples.
  Diversity caps (`--per-company`, `--per-month`) are now configurable; the old
  defaults silently capped the library at ~1,000 cases.
- **Event study summary**: direction-aligned, winsorised at 2.5/97.5, block
  bootstrap by event month, Holm correction. Final result at 2,384 cases:
  **approval +2.8% survives Holm over the full 12-test category × horizon family
  (adjusted p=0.007); CRL −3.8% is borderline (adjusted p=0.060); trial
  readouts do not** (−0.3%, n.s.). Caveats: price-coverage survivorship
  (145 delisted tickers have no free price source) and heuristic categories.
- **Data audit** (`medradar audit`): dates, availability, quality, match rates,
  price coverage, freshness, duplicate detection.
- **`medradar stats`** + auto-generated `docs/DATA.md`; `scripts/nightly.ps1`.
- **Chinese product catalog 2,000 → 2,740** entries; product families 204.
- **19-chapter report** incl. case library, event study, replay, timing quality.

### Fixed
- **Release blocker: simulated buys now debit cash.** `_handle_entries` booked
  positions without subtracting `qty * fill_price`; the book is now checked
  against the fills ledger after every order (`cash + holdings = equity`, cash
  never negative) and the invariant fails closed.
- **Quote-time / market-state guards**: only an OPEN market with a timestamped
  quote that is not older than the news and not older than 30 minutes may fill.
  Unfillable orders go to `live_pending` and retry next cycle; every skip is
  written to `live_skips` with a machine-readable reason.
- **Demo no longer has dead buttons**: it builds `dashboard.html` and ships the
  assumptions file; report links are emitted only when the target exists.
  `scripts/check_install.py` now verifies the dashboard and every local link.
- **Research consistency**: `eventstudy.py` uses block bootstrap; case-study
  p-values come from the same block bootstrap as the CI; Holm runs over the full
  category × horizon family; the README states that all events are date-level.
- Company alias matching requires a **contiguous token run** (no more
  `JOHNSON CONTROLS` → J&J).
- Replay artefacts no longer overwrite the report dashboard; `--with-cases`
  builds before analyze; datetime `available_at` preserved end to end.
- Event-study means are outlier-robust (small-cap returns are fat-tailed).

## [0.1.0] — 2026-10-31

### Added
- Unified `events` fact table (510(k), PMA, recall, drug approval, trial,
  NMPA registration) with a single metrics contract (`docs/SCHEMA.md`).
- Company/subsidiary registry (89 names) and a Chinese track dictionary
  (38 tracks, 1,958 mapped product codes).
- **Product-level device intelligence**: 159 product families, 600 Chinese
  product names (85.5% of device events), `medradar products` CLI, new-product
  radar, company portfolio mix and a CSV export.
- Metrics engine: Gamma-Poisson shrinkage, observed-exposure baselines,
  Jensen-Shannon mix shift, first-occurrence novelty, recall clusters.
- Chinese report + self-contained HTML dashboard (18 chapters), English
  one-pager, summary CSV.
- Event study and simulated long-only book on real daily bars (`paper`).
- **Replay engine**: event → decision → fill → 1/5/20-day outcome, 1-minute
  fills for the last ~7 days, daily fills beyond, 10/25/50 bps cost tiers,
  standalone HTML timeline, `medradar replay` CLI.
- **Research-grade timing**: `published_at` / `first_seen_at` / `available_at`
  / `timestamp_quality` on every event and signal; point-in-time signal scoring.
- **Statistics**: block bootstrap, Holm/Bonferroni correction, dev/validation/
  holdout splits, survivorship flags, MDE/power hints.
- **Reproducible calibration**: `medradar.calibration` with recorded fixtures;
  no key needed in CI, drift fails the score script.
- **Onboarding**: `medradar demo` (offline snapshot), `doctor`, `watchlist`;
  `config/` ships inside the wheel; `MEDRADAR_HOME` keeps data out of site-packages.
- Live lane: SEC EDGAR 8-K feed, full-text backfill, FDA RSS, ClinicalTrials.gov
  status changes, simulated fills at real quotes with 10 bps slippage.
- LLM judge for 8-K materiality (OpenAI-compatible endpoint), content-hash cache,
  per-cycle budget, evidence-quote enforcement, heuristic fallback.
- Calibration on 25 hand-labelled real filings (`docs/CALIBRATION.md`).
- **274 offline tests**; CI matrix 3.10–3.12 + Windows install job; Pages deploy
  via artifact upload; `docs/GOOD_FIRST_ISSUES.md`.

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
