# Changelog

All notable changes to MedRadar. Format loosely follows Keep a Changelog.
This is a research tool; "fixed" means a documented behaviour changed.

<!-- BEGIN GENERATED: unreleased -->
<!-- generated: do not edit by hand; regenerate with tools/governance/gen_views.py -->
<!-- source-sha256: d71d68a3d775f0f033b0fc86558317e149c3e954c7ea01903fffb34f99e58c92 -->
<!-- payload-sha256: b11bf5a204c226d9c1de20bef200e3ad20094852198b97c2d5e3dee637a51a87 -->
## [Unreleased] — generated governance snapshot

_Snapshot of [`PROJECT_STATE.yaml`](PROJECT_STATE.yaml) at `2026-11-12T23:35:20+08:00`. Regenerate with `python tools/governance/gen_views.py`; do not edit this block by hand._

- **Main head:** `b2a14c0` (2026-11-03), version **0.5.0**
- **Tests:** 1,071 passed, 3 skipped, 0 failed (1,074 collected)
- **Capabilities:** 7 working, 6 draft, 1 retired
- **Open PRs:** 20 open (19 draft), 10 merged; branch protection not applied
- **Data snapshot:** 2026-10-31, 375,378 events (local build; `data/` is gitignored)
<!-- END GENERATED: unreleased -->

## [0.5.0] — 2026-11-02 (Phase 3: unified forecast cycle, temporal graph, evidence-grounded research agent)

### Added
- **Canonical `nowcast` record kind** (`medradar/forecast_registry.py`, schema `forecast-registry-2`):
  a genuine prospective forecast registered while its target window is already open (the quarterly
  Horizon case). Strict validation (`window_start <= generated_at < window_end`, closed windows
  rejected), append-only history, and explicit cohort separation in `evaluate()`: pure-future
  headline, nowcast cohort, descriptive prospective union and a `record_kind_breakdown`.
- **Horizon→canonical adapter** (`medradar/intelligence/forecasting/registry_adapter.py`): stable
  `horizon:<forecast_id>:<model_version>` idempotency keys, `company_track` targets, canonical
  evidence provenance (locator + SHA-256), idempotent re-registration (`IdempotencyConflict` on a
  changed probability), and coverage-guarded resolution of matured forecasts from the real events
  table.
- **Continuous forecasting cycle** (`scripts/forecast_cycle.py`, `medradar/intelligence/forecasting/cycle.py`):
  train frozen model → score current quarter → register nowcasts → verify matured → export
  deterministic registry artifact + cycle log; idempotent and offline-safe. Weekly
  `.github/workflows/forecast-cycle.yml` committed (not executed in this environment).
  Real run: 25 Horizon records → 25 nowcasts registered, 0 rejected, 25 pending; second run
  `registered=0, idempotent=25`, identical artifact hash.
- **TKG real-data integration** (`scripts/tkg_import_research.py`,
  `medradar/intelligence/graph_context.py`): the 55,090-event `events` table imported read-only into
  the bitemporal store → 171,800 assertions, **57,381 nodes / 114,419 edges**, deterministic PIT
  snapshot (sha256 `b60c8360…`), idempotent re-import (0 created, same hash), source unchanged;
  read-only pair context/timeline/counts helpers under independent known-time/valid-time cutoffs.
- **Evidence-grounded research agent** (`medradar/research_agent.py`, CLI `python -m medradar.research_agent`):
  deterministic workflow (plan → 8 point-in-time tools → evidence table → 5 conflict rules →
  labelled hypothesis → counter-evidence → statistical validation → cited synthesis → uncertainty →
  research log → stop condition). Five question templates (`entry_forecast`,
  `market_leading_indicator`, `early_signal`, `strategic_shift`, `cross_source_validation`). Every
  claim cites a stored id; probabilities come only from the model/registry; no LLM path by default.
  Real demo: 5 questions · 55 claims · 224 unique cited ids · 314 citation checks · 0 missing ·
  3 cross-source conflicts, with the canonical registry and TKG in use.
- Docs: `docs/PHASE3.md`, `docs/PHASE3_REGISTRY.md`, `docs/PHASE3_AGENT.md`,
  `docs/TKG_INTEGRATION.md`; behavioural Phase-3 checks added to `verifier/v1/verify.py`.

### Fixed
- Windows console encoding: the research-agent CLI reconfigures stdout/stderr to UTF-8 with
  `errors="replace"` before printing, so evidence text containing `→`/CJK cannot raise
  `UnicodeEncodeError` on legacy Windows codepages (this was caught by the Windows CI job, not by
  the local UTF-8 shells).
- The two disconnected forecast ledgers are unified: the immutable canonical registry is the system
  of record and the Horizon forecaster writes through the adapter; the legacy research-table
  forecasts remain as an untouched historical artifact, not a parallel ledger.
- `tkg-schema-2` idempotency lookup is O(n²) without an index; the import script installs
  operational indexes on the target store only (documented; exported content/hash unaffected).

### Scope boundary
- Nowcast records are **not** pre-registered future forecasts; they are kept in a separate cohort and
  never merged into the pure-future headline.
- The canonical registry has no matured forecast yet → calibration status is
  `insufficient_matured_forecasts`, not a quality claim.
- TKG knowledge time for the current import equals the backfill observation time; it cannot support
  "what was known in 2020" claims for these rows. Most source public timestamps are date-level and
  timezone-naive (explicitly dropped from `public_time` and counted).
- The research agent narrates stored evidence; it does not establish causality, predict returns, or
  replace the statistical experiments. Conflict rules are heuristics. Patents (no API key) and
  hiring signals (no stable legal source) are explicit evidence gaps.
- The weekly forecast workflow is committed but was not executed here; no green CI run is claimed.

## [0.4.0] — 2026-11-02 (Phase 1–2: harder target, multi-window, market/publication signals)

### Added
- **Dormant→active track-entry target** (`first_entry_v1`): candidate at quarterly cutoff
  `t` = a `(company, track)` pair whose company is already active but whose pair has no
  material event in `(t−36m, t]`; label = first material 510(k)/original-or-panel-track PMA
  activity in `(t, t+12m]`. 41,003 mature examples over 24 origins, 503 positives (1.23%
  base rate), six new point-in-time entry features (inactive months, active-track/company
  counts and deltas, novelty share) and an explicit left-censoring statement. The
  independent as-of leakage replay was extended to the entry dataset (1,107,081 values,
  0 mismatches).
- **Multi-window purged evaluation**: `run_backtest(holdouts=K)` evaluates the last K
  evaluable origins with purged expanding training sets and reports per-window metrics,
  mean/std, and per-window paired bootstrap CIs; `holdouts=1` reproduces the v1 contract.
- **Market-data lane**: the base repo's Yahoo daily `prices` table is imported read-only
  into `market_bars` (95,725 bars, 38/44 mapped tickers, SPY/XBI benchmarks) with eight
  point-in-time features (`mkt_ret_12m`, `mkt_vol_12m`, `mkt_max_drawdown_12m`,
  `mkt_rel_spy_12m`, `mkt_rel_xbi_12m`, `mkt_volume_z_3m`, `mkt_regime_spy_above_200d`,
  `mkt_days_since_12m_high`) and an explicit missing flag. `pipeline collect --source
  market --prices-db <base.sqlite>`. Consolidation note: market capitalisation and
  valuation multiples are not implemented (no shares-outstanding data).
- **Publication lane (OpenAlex, keyless)**: annual work counts for all 51 curated
  companies (150,087 works, 2014–2026), five point-in-time features using complete years
  only with a 15-Feb knowledge lag, disk cache + offline replay, and per-company alias
  provenance. `pipeline collect --source publications`.
- **Patent adapter (key-gated)**: USPTO Open Data Portal collector that returns an explicit
  `unavailable_missing_api_key` status (no rows, no fabricated numbers) without
  `USPTO_ODP_API_KEY`, plus a documented JSONL importer and publication-date PIT rule.
  Patents are **not evaluated** in this release.
- **Feature-group ablation harness**: `experiments/reverse_rd_v2/run_ablation.py` +
  `merge_ablation.py`, frozen `ablation_metrics.json`, covering A–G specifications for both
  targets on identical rows (`holdouts=3`, purged). Procurement is excluded from historical
  gain claims (current snapshot is not point-in-time usable).
- Docs: `docs/PHASE1.md`, `docs/PHASE2.md`, `docs/MARKET_DATA.md`,
  `docs/PUBLICATION_PATENT_DATA.md`, updated `docs/REVERSE_RD.md`, `README`/`README.zh-CN`
  and a behavioural v2 check in `verifier/v1/verify.py`.

### Fixed
- Phase 1's frozen `entry_metrics.json` A/B cells were trained on shared R&D features only;
  the v2 ablation adds the six entry-specific features (spec C/D) and keeps A/B as
  explicitly labelled Phase-1 parity cells. The corrected entry baseline is spec D in
  `ablation_metrics.json`.
- `tests/test_intelligence.py` gained a regression test for custom ablation specifications
  and for the unchanged default two-spec contract.

### Scope boundary
- Market returns are not treated as technological capability; publication counts are a weak
  alias-matched signal, not evidence of approved R&D projects; patents are not evaluated.
- Neither target establishes causality; multi-window holdouts share overlapping 12-month
  label windows and are not independent replications.

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
