# Roadmap

Guiding rule: **trust first, distribution second.** A research tool that cannot be
audited should not be promoted.

## Shipped in v0.3.0 (2026-10-31)

- [x] Independent `clinical_hold`, `refuse_to_file`, `crl`, `pre_submission` and
      `designation` taxonomy, including a pre-submission/approval false-positive guard.
- [x] No `event_date` fallback for missing public timestamps. `estimated` and
      `unknown` records are descriptive-only and visibly excluded from trading.
- [x] Extreme abnormal-return audit with case-level flags, exclusion counts and
      unfiltered raw means; >100% observations leave the inferential sample.
- [x] Public frontier feed: FDA AdCom schedules/materials, first-posted trials,
      pre-submissions and designations via `medradar frontier`.
- [x] Hierarchical device coverage: 50 tracks / 23 domains, including life support,
      IVD, BCI, neuromodulation, cardiovascular, imaging, robotics and SaMD/AI.

## Shipped in v0.2.0 (2026-10-31)

### Trust / execution
- [x] Cash-conservation invariant: every simulated buy debits cash, and the book
      is checked against the fills ledger after each order (`cash + holdings =
      equity`, cash never negative).
- [x] Quote guards: market must be OPEN, quote must carry a timestamp, timestamp
      must not predate the news, quote older than 30 min is rejected.
- [x] Unfillable orders are queued in `live_pending` and retried next cycle;
      every skip is recorded in `live_skips` with a machine-readable reason.
- [x] No-trade freeze, slippage-aware sizing, tradeable-source allowlist,
      cross-source dedupe, idempotent re-runs.

### Data
- [x] Full-history snapshot: **375,378 events** (510(k) 176,466 · PMA 57,372 ·
      recalls 59,646 · trials 55,592 · drug approvals 5,326 · EDGAR 20,976),
      1.3 GiB SQLite, 1966–2026 where the source allows.
- [x] EDGAR 8-K catalyst corpus: **20,976 filings** (2015–2026; the snapshot used
      16 phrase buckets, v0.3.0 defines 19, 100% of candidates fetched, 0 failures).
- [x] Product intelligence: **204 families**, **2,740 Chinese product names**.
- [x] `medradar stats` + auto-generated `docs/DATA.md`; `medradar audit`.

### Research
- [x] Event-time model (`published_at` / `first_seen_at` / `available_at` /
      `timestamp_quality`); point-in-time signal scoring.
- [x] Case library: **2,384 traceable cases** with verbatim evidence and
      1/5/20/60-day abnormal returns; negative examples kept.
- [x] Event study: direction-aligned, winsorised, **block bootstrap CI + p**
      (same sampling model), Holm over the full category × horizon family.
      The v0.2 snapshot found approval significant and CRL not significant after
      Holm. That mixed-category result is superseded and must be rebuilt in v0.3.0.
- [x] Replay: 400-step 7-year events timeline; 1-minute fills for the last 7
      days, daily before that; 10/25/50 bps cost tiers.
- [x] `eventstudy.py` switched from iid to block bootstrap.

### Product / UX
- [x] Interactive zero-dependency dashboard (`docs/dashboard.html`, 7 views:
      overview, tracks, companies, products, cases, replay, data) with search,
      sorting, evidence drawer, replay cost switching, hash routing, theme.
- [x] `medradar demo` is a complete first-run flow: report **and** dashboard,
      every local link resolves; unavailable pages are hidden.
- [x] `medradar dashboard` CLI, `run --with-dashboard`, weekly CI wiring.
- [x] 1-minute replay page (`docs/replay_intraday.html`) with a per-step price
      source explanation and the 7-day boundary documented.

### Engineering
- [x] Release consistency: `pyproject.toml` / `__init__` / CHANGELOG / README all
      0.2.0; version-consistency tests; no placeholder clone URLs.
- [x] Offline test suite covers business invariants (cash conservation, quote
      guards, retry queue, no dead demo links), not just smoke tests.

## Next (needs an API key or external data)

- [ ] 100-filing calibration with two independent annotators and Cohen's κ.
- [ ] Re-run calibration against a live endpoint and record raw responses.
- [ ] Province-level China-gap view using a maintained, legally obtained NMPA CSV snapshot.
- [ ] Out-of-sample (holdout) event study with a pre-registered split.
- [ ] Reclassify all 20,976 filings under v0.3.0, audit extreme prices, and publish
      a fresh frozen metrics/case snapshot (the source SQLite/HTTP cache is not committed).
- [ ] Interactive dashboard: shareable per-case permalinks and CSV export.

## Later (reach)

- [ ] FDA statistical-review PDF mining (trial-design red flags).
- [ ] Weekly auto-published research note.
- [ ] Data-source adapters: recalls RSS, PatentsView, FDA statistical-review PDFs.
- [ ] Minimal Python API for programmatic queries.

## Explicitly not planned

- Real-money execution, broker integration, or investment advice.
- Claiming to monitor confidential pending 510(k)/PMA reviews; only public
  pre-decision evidence (AdCom, trials, filings) is in scope.
- Scraping sites behind a WAF (NMPA, Stooq) — use a CSV export instead.
- Minute-level event studies on date-only data: the database is openly
  date-level, and the only minute-level lane is the last-7-day live replay.
