# Changelog

All notable changes to MedRadar. Format loosely follows Keep a Changelog.
This is a research tool; "fixed" means a documented behaviour changed.

## [0.3.0] — 2026-11-02 (research foundation + Market-to-R&D + frontier, integrated)

This release consolidates three independently authored branches after an independent
forensic audit and a defect-fix pass. Merge/audit/fix decisions and evidence:
`docs/INTEGRATION_2026-11-02.md` and `docs/research/INTEGRATION_FIXES.md`.

### Added
- **Market-to-R&D research lane** (`medradar/intelligence/`): SEC EDGAR XBRL Company
  Facts with filing-time availability and amendment handling; USAspending award
  collection with explicit obligation semantics; official openFDA bulk ZIP ingestion
  (streaming, resumable, offline-cache friendly); point-in-time company–track examples;
  a dependency-free logistic Reverse R&D baseline with purged rolling-origin evaluation
  and a chronological holdout; naive/persistence baselines; a Horizon forecaster with
  machine-checkable verification conditions. Frozen real-data experiment under
  `experiments/reverse_rd_v1/`: 55,090 in-window FDA events, 43,420 SEC facts over 32
  companies, 3,453 procurement awards (obligations; 0 point-in-time usable), 6,701
  examples over 25 quarterly origins, holdout 2025-10-01 (307 rows / 129 positives).
  **Honest result:** consolidated financial features add no stable out-of-sample gain
  (holdout PR-AUC 0.7935 → 0.7922), and a no-feature per-pair base rate already scores
  AP 0.7913 vs the model's 0.7935 (paired-bootstrap Δ CI [−0.032, +0.037]) — v1 measures
  persistence of public activity, not first-entry foresight.
- **Bitemporal knowledge store** (`medradar/tkg/`): append-only nodes/edges with
  independent valid-time and knowledge-time (`known_at`) queries, stable
  `assertion_id` versioning, SQL guards against history rewrites, schema-version gate,
  deterministic point-in-time export (canonical JSON/JSONL + manifest + content hash, no
  wall clock), and a strictly read-only `events` adapter that imports observation time
  as knowledge time. CLI: `python -m medradar.tkg {demo,import,export,bench}`.
- **Immutable Forecast Registry** (`medradar/forecast_registry.py`): content-addressed
  forecasts with a server-assigned monotonic `generated_at`, physically append-only
  ledgers (triggers reject UPDATE/DELETE and key-rebind INSERT-OR-REPLACE), append-only
  resolutions with corrections as new versions, 3/6/12/24 calendar-month windows,
  as-of scoring (Brier, epsilon-clipped log loss, fixed-boundary ECE), deterministic
  artifact hashing. CLI: `python -m medradar.forecast_registry
  {demo,register,resolve,evaluate,export}`. 43 dedicated offline tests, synthetic only.
- **Frontier radar & taxonomy**: FDA Advisory Committee schedules/materials,
  first-posted trials, SEC pre-submissions/designations in one `medradar frontier` feed;
  50 device tracks across 23 domains with machine-readable `domain`/`frontier_keywords`;
  clinical-trial device-intervention filter and the `clinical_hold` / `refuse_to_file` /
  `crl` / `pre_submission` / `designation` taxonomy.
- **Extreme-return audit**: absolute SPY-abnormal returns above 100% are listed with
  ticker/date/horizon and excluded from inference; unfiltered raw means stay visible.

### Fixed
- **Integration defect-fix pass (independent forensic audit, 2026-11-02):**
  - **Python 3.10 CI blocker**: 1–5-digit fractional seconds (`.5Z`) raised on 3.10;
    shared `medradar/tkg/_time.py` normalises 1–9 digits to 6 before parsing, used by
    both the TKG store and the forecast registry.
  - **Point-in-time corruption**: date-only timestamps bypassed the fixed-width
    microsecond renderer (`…T00:00:00Z`), breaking same-second cuts and every
    adapter-imported date-only row; both fast paths now render `.000000Z`.
  - **Registry immutability hole**: `INSERT OR REPLACE` with a reused
    `idempotency_key` and a new `prediction_id` could delete an unresolved forecast;
    added a key-rebind `BEFORE INSERT` guard and `forecast_idempotency` ledger guards.
    Owner-level raw SQL is still explicitly out of the threat model.
  - **Leaky rolling-origin**: training at origin *t* used examples whose 12-month label
    windows extended past *t*. Purged/embargoed training is now the default (holdout
    PR-AUC 0.7924 → 0.7935; Brier 0.1687 → 0.1721; ECE 0.0605 → 0.0811; FPR 0.2416 →
    0.2753); the old leaky variant is retained only as a labelled diagnostic block.
  - **Rubber-stamp leakage audit**: replaced the self-declared `feature_available_at`
    check with an independent as-of replay of all 21 features from source tables via a
    separate SQL path (6,701 examples / 140,721 values / 0 mismatches) plus positive and
    negative controls; docs state it is a consistency audit, not proof of no leakage.
  - **Missing baselines**: constant / company / track / per-pair base-rate baselines and
    a deterministic paired bootstrap CI are now reported with every comparison.
  - **Forecast evidence labelling**: records now carry `raw_value`, `standardized_value`
    and `median_imputed` alongside the standardized contribution.
  - **AdCom collector no longer fakes success**: FDA renders the calendar `<tbody>`
    client-side, so a static fetch parses 0 rows; collect now returns
    `status="empty"`/`"source_changed"` with a warning, parses "Content current as of"
    from `<time datetime>`, and documents the source as experimental.
  - **Case-library price basis**: entry now uses `prices.adjusted_open` (exit already
    used `adjusted_close`), removing split/dividend fake alpha; 2:1-split regression test.
  - **Timestamp gate documented as prospective-only**: the shipped snapshot keeps
    legacy `quality='date'` + `published_at=event_date` rows; `medradar audit` reports a
    read-only `legacy_timestamp_promotions` count and `docs/DATA.md` gives the manual
    (never auto-run) demotion recipe.
  - **Repository hygiene**: duplicate `docs/docs/ASSUMPTIONS.md` removed and published
    links rewritten; stale hardcoded test counts replaced by pointers to
    `python -m medradar selftest`.
- `clinical_hold`, `refuse_to_file`, `crl`, `pre_submission` and `designation` are
  independent categories: a "Pre-Submission for FDA Approval" headline no longer counts
  as an approval, and designations no longer inflate approvals.
- Historical decision dates are no longer silently promoted to `published_at` or
  `available_at`; missing/`estimated`/`unknown` public times stay descriptive only and
  are excluded and counted in return studies. openFDA 510(k)/PMA decision dates stay
  non-tradable unless a genuine public timestamp exists.
- Device and diagnostic-test interventions use the device taxonomy before the drug
  therapeutic-area fallback; drug-only trials and non-device SEC designations no longer
  leak into the device frontier feed.
- Foundation review (FOUNDATION-INTEGRATE-007) and TKG hardening (TKG-HARDEN-005):
  positive resolutions cannot record a future `event_time`; `window_end` is always
  derived from the horizon in calendar months; retrospective fixtures are excluded from
  the prospective headline; TKG snapshots omit edges unless both endpoints are visible
  under the same cutoffs; resubmit guards reject rewrites (not forged appends); duplicate
  idempotent retries return the exact original row.

### Scope boundary
- MedRadar monitors public pre-decision evidence only; it does not claim access to
  confidential pending 510(k)/PMA reviews.
- SEC revenue stays consolidated company facts (never product-line sales); USAspending
  amounts are obligations, not revenue, and the current snapshot is not usable for
  historical point-in-time claims; a regulatory milestone is a lagging proxy for R&D.
- The Market-to-R&D experiment measures association and incremental prediction of
  continued public activity; it does not establish a causal market→R&D mechanism, and a
  single 307-row holdout is not proof of stability either way.

## [0.2.2] — 2026-10-31

### Docs
- Attribution: the project is now explicitly marked as **built end-to-end by the
  DeepSeek Harness agent team on Chinese domestic models (`deepseek-flash`)** —
  in both READMEs, the report footer, the dashboard footer and
  [`docs/ATTRIBUTION.md`](docs/ATTRIBUTION.md). No other model was used.

## [0.2.1] — 2026-10-31

### Fixed
- **Pending-order expiry now anchors on the first queued time** (`created_at`),
  not `last_attempt_at`: a news item that keeps failing to quote can no longer
  stay tradeable forever by refreshing the retry clock.
- **Fills are atomic**: cash debit, position write, order record and pending
  state commit in one SQLite transaction; a failure rolls all of them back and
  queues the alert for a durable retry instead of leaving a half-applied book.
- **No implicit "seeded" exemption**: the cash-vs-ledger invariant no longer
  silently marks a mismatched book as seeded. Seeded books must be declared
  explicitly (tests/importers), so a crashed fill cannot hide behind it.
- Python 3.10 CI compatibility for the release-consistency test (`tomllib` is
  3.11+; falls back to a version-line regex).

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
