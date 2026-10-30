# Roadmap

Guiding rule: **trust first, distribution second.** A research tool that cannot
be audited should not be promoted.

## Now (v0.1 hardening)

- [x] Execution guards: no-trade freeze, slippage-aware sizing, stale-quote
      rejection, tradeable-source allowlist, cross-source dedupe.
- [ ] Event-time discipline: add `published_at` / `first_seen_at` /
      `available_at` / `timestamp_quality` to every event and state which one
      the backtest uses.
- [ ] Packaging: ship `config/` as a package resource, separate user data
      directory, test `pip install` from a clean wheel on Windows + Linux.
- [ ] `medradar demo` (offline snapshot, one command) and `medradar doctor`
      (config/DB/network checks).
- [ ] Reproducible LLM evaluation: the calibration run must call the production
      endpoint, keep raw responses, and re-run in CI with a key.

## Next (research credibility)

- [ ] 100-filing calibration with two independent annotators and Cohen's κ.
- [ ] Point-in-time features: compute THI and mappings using only data available
      at the event date, then re-run the event study.
- [ ] Multiple-testing correction and block bootstrap for the event study.
- [ ] Out-of-sample / walk-forward split, reported alongside the in-sample case.
- [ ] Negative and failed-signal case studies in the report.

## Later (reach)

- [ ] Interactive dashboard filters + shareable event permalinks (static JS only).
- [ ] CSV/JSON export endpoints and a minimal Python API.
- [ ] NMPA CSV importer + province-level China-gap view.
- [ ] FDA statistical-review PDF mining (trial-design red flags).
- [ ] Weekly auto-published research note.

## Explicitly not planned

- Real-money execution, broker integration, or investment advice.
- Scraping sites behind a WAF (NMPA) — use a CSV export instead.
- Chasing every framework integration before the core is trustworthy.
