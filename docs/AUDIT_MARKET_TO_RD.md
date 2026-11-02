# Repository audit — Market-to-R&D starting point

Audit target: `main` commit `7a639f795969e14a7b077dc609311f0b27ce4439` (`v0.2.2`). Baseline: 440 passed, 3 skipped (`python -m medradar selftest` on `main` v0.2.2); the integrated v0.3.0 suite is 578 tests (3 skipped).

## Reused rather than rebuilt

- Unified `events` table with company, track, product code, event date and `available_at` knowledge time.
- Curated parent/subsidiary `CompanyRegistry`, product-code track mapping and existing openFDA collection/cache.
- SQLite migrations, atomic writes, deterministic JSON output and standard-library-only analysis style.
- Existing SEC 8-K live lane remains independent of the new XBRL Company Facts lane.

## Gaps addressed in this branch

1. No structured filing-time financial facts → SEC Company Facts collector and amendment-aware features.
2. No procurement fact model → USAspending awards, provenance, quality labels and observed temporal edges.
3. No future-R&D example set → quarterly company–track examples with explicit maturity and dual-time tests.
4. No fair cross-source incremental evaluation → frozen logistic ablations and rolling-origin holdout.
5. No forecast lifecycle → persistent Horizon registry, future verification conditions and calibration report.

## Deliberately not claimed

The current repository did not contain its 1.2 GiB runtime SQLite snapshot, so this branch recollects real data rather than inventing a backtest from documentation totals. Product-level segment revenue, historical procurement publication time, patents, research collaborations, jobs and causal market→R&D inference are not represented as completed capabilities.
