# Roadmap

Guiding rule: **trust first, distribution second.** A research tool that cannot
be audited should not be promoted.

## Now (v0.1 hardening) — done

- [x] Execution guards: no-trade freeze, slippage-aware sizing, stale-quote
      rejection, tradeable-source allowlist, cross-source dedupe.
- [x] Event-time discipline: `published_at` / `first_seen_at` / `available_at` /
      `timestamp_quality` on events and signals; point-in-time signal scoring.
- [x] Packaging: `config/` ships as wheel data, user data in `MEDRADAR_HOME`,
      clean-install tested on Windows (CI covers 3.10–3.12 + Windows).
- [x] `medradar demo` (offline snapshot) and `medradar doctor`.
- [x] Product-level device intelligence: 159 families, 600 Chinese product
      names, `medradar products`, new-product radar, portfolio mix.
- [x] Replay engine with 1m/daily fills, 10/25/50 bps tiers, assumption registry.
- [x] Statistics: block bootstrap, Holm correction, sample splits, survivorship.
- [x] Reproducible calibration harness with recorded fixtures (no key in CI).

## Next (with an API key / external data)

- [ ] 100-filing calibration with two independent annotators and Cohen's κ.
- [ ] Re-run calibration against a live endpoint and record raw responses.
- [ ] Replace the event study's iid bootstrap with `stats.block_bootstrap_ci`.
- [ ] NMPA CSV importer + province-level China-gap view (needs data, not code).
- [ ] Interactive dashboard filters + shareable event permalinks.

## Later (reach)

- [ ] CSV/JSON export endpoints and a minimal Python API.
- [ ] FDA statistical-review PDF mining (trial-design red flags).
- [ ] Weekly auto-published research note.
- [ ] Data-source adapters: AdCom calendar, recalls RSS, PatentsView.

## Explicitly not planned

- Real-money execution, broker integration, or investment advice.
- Scraping sites behind a WAF (NMPA) — use a CSV export instead.
- Chasing every framework integration before the core is trustworthy.
