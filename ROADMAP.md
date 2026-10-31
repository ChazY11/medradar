# Roadmap

Guiding rule: **trust first, distribution second.** A research tool that cannot be
audited should not be promoted.

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
- [x] Full-history devices/drugs/trials: **375,378 events** (510(k) 176,466 ·
      PMA 57,372 · recalls 59,646 · trials 55,592 · drug approvals 5,326),
      1.3 GiB SQLite, 1966–2026 where the source allows.
- [x] EDGAR 8-K catalyst corpus: **20,976 filings** (2015–2026, 16 phrase
      buckets, 100% of candidates fetched, 0 failures).
- [x] Product intelligence: **204 families**, **2,740 Chinese product names**.
- [x] `medradar stats` + auto-generated `docs/DATA.md`; `medradar audit`.

### Research
- [x] Event-time model (`published_at` / `first_seen_at` / `available_at` /
      `timestamp_quality`); point-in-time signal scoring.
- [x] Case library: **2,384 traceable cases** with verbatim evidence and
      1/5/20/60-day abnormal returns; negative examples kept.
- [x] Event study: direction-aligned, winsorised, **block bootstrap CI + p**
      (same sampling model), Holmes over the full category × horizon family.
      Honest result: approval/CRL survive Holm, trial readouts do not.
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
- [ ] NMPA CSV importer + province-level China-gap view.
- [ ] Out-of-sample (holdout) event study with a pre-registered split.
- [ ] Expand the corpus to 3,000+ filings and 500+ selected cases.
- [ ] Interactive dashboard: shareable per-case permalinks and CSV export.

## Later (reach)

- [ ] FDA statistical-review PDF mining (trial-design red flags).
- [ ] Weekly auto-published research note.
- [ ] Data-source adapters: AdCom calendar, recalls RSS, PatentsView.
- [ ] Minimal Python API for programmatic queries.

## Explicitly not planned

- Real-money execution, broker integration, or investment advice.
- Scraping sites behind a WAF (NMPA, Stooq) — use a CSV export instead.
- Minute-level event studies on date-only data: the database is openly
  date-level, and the only minute-level lane is the last-7-day live replay.
