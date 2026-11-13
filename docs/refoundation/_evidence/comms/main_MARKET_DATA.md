# Market data: point-in-time bars and the Phase-2A market feature ablation

This document covers the **market-data source**, the **market feature group**, their
point-in-time rules, coverage, and the real-data incremental-value ablation
(`experiments/reverse_rd_v2/market_metrics.json`). It is part of the
Market-to-R&D (Reverse R&D) layer; it does not modify the FDA, clinical-trial,
SEC or trading lanes.

## Source and provenance

- **Lane:** the base MedRadar repository already stores a daily US-equity lane in
  its `prices(ticker, date, open, high, low, close, adj_close, volume)` table,
  fetched once from Yahoo Finance's public chart endpoint
  (`medradar/prices.py` in the base repository). `adj_close` is the
  split/dividend-adjusted close.
- **Import:** `medradar/intelligence/sources/market_data.py` opens that SQLite
  file **read-only** (SQLite `mode=ro` + `PRAGMA query_only`) and copies the rows
  for the curated device companies plus the `SPY` (market) and `XBI` (biotech)
  benchmarks into the intelligence table
  `market_bars(ticker, date, open, high, low, close, adj_close, volume, source, retrieved_at)`.
  There are **no network calls** in the import or in any feature/ablation code.
- **Idempotency:** a re-run replaces (does not merge) the rows of the requested
  tickers, so repeats are deterministic apart from the `retrieved_at` import
  timestamp. The source database is never written (a write attempt on the
  read-only connection raises `sqlite3.OperationalError`; a test covers this).
- **Knowledge time:** the `prices` table has no vendor publication timestamp, so
  `retrieved_at` records the local import moment and is **not** used as
  availability. Feature knowledge time is the trading date: a bar dated `d` is
  treated as known at the end of `d`. A bar dated exactly at the cutoff is
  included; anything later is invisible.
- **Licence/redistribution caveat:** this is a **research import, not a licensed
  market-data feed**. Raw bars live in gitignored `data/`; only small aggregates
  (coverage counts, metrics) are committed. Yahoo Finance terms govern the
  original retrieval; do not redistribute the raw bars as part of a product.
- **Survivorship:** the table is a current snapshot of whatever tickers an
  earlier collection run fetched. Delisted/acquired tickers are absent; a
  company that changed ticker only has the tickers that were requested. The
  matched set is therefore **not a random sample**, and the ablation's
  market-feature rows are a biased subset of the full example set.
- **Non-US listings:** `SHL.DE`, `AMBU-B.CO` and the ADRs (`PHG`, `TRUMY`,
  `OCPNY`, `FUJIY`, `CAJ`) are a different instrument from the local
  shares (FX, ADR ratio, local market). Returns are used as coarse company-level
  market context only.

## Coverage on this machine

Imported from `<REDACTED_LOCAL_PATH> into the research
database:

| Item | Value |
|---|---|
| Curated device companies | 51 |
| Companies with a ticker in `config/companies_device.json` | 44 |
| Tickers found in the local `prices` table | **38** |
| Benchmarks imported | `SPY`, `XBI` (2/2) |
| Bars imported | **95,725** |
| Bar date range | **2016-10-31 … 2026-10-30** |
| v1 examples (2019-10-01 … 2025-10-01) with complete market features | **5,206 / 6,701 (77.7%)** |
| Holdout (2025-10-01) examples with complete market features | **245 / 307** |

Companies without bars (13): `masimo` (MASI), `hologic` (HOLX), `nevro`
(NVRO), `invacare` (IVC), `olympus` (OCPNY), `canon_medical` (CAJ) have a
ticker that is **absent from the local price table**; `cook_medical`,
`wl_gore`, `biotronik`, `bbraun`, `medline`, `karl_storz`, `pentax_medical`
have **no ticker** at all. MASI/HOLX/NVRO/IVC/OCPNY/CAJ being absent is a
property of the local snapshot (collection set or failed fetch), not proof that
the company was never listed. Invacare/IVC was delisted, which is exactly the
survivorship gap described above.

## Point-in-time rules

All features are computed from `market_bars` rows with `date <= cutoff` using
`adj_close` only — raw `close` is never used for a return, so a split or large
dividend cannot become a fake return (covered by a test with a 2:1 split proxy).
A trailing 12-month window requires:

- a bar at or before `cutoff - 365 days` (the window base), and
- at least **200 window bars** between the base and the cutoff.

If either condition fails, every market feature is `None` and `mkt_missing = 1`
— a recently listed company (for example GE HealthCare at 2022–2023 cutoffs) is
reported as missing instead of being given a shorter-horizon proxy. Nothing is
imputed inside the feature module; the backtest's `LogisticBaseline` applies
training-only median imputation with missing indicators.

## Feature definitions (`features/market_features.py`)

| Feature | Definition |
|---|---|
| `mkt_ret_12m` | `adj_close(cutoff) / adj_close(base) - 1`, base = last bar at or before `cutoff - 365d`. |
| `mkt_vol_12m` | Sample stdev of daily log returns inside the 12m window × `sqrt(252)`. |
| `mkt_max_drawdown_12m` | Worst peak-to-trough `close/peak - 1` inside the 12m window (≤ 0). |
| `mkt_rel_spy_12m` | `mkt_ret_12m` minus SPY's 12m return. |
| `mkt_rel_xbi_12m` | `mkt_ret_12m` minus XBI's 12m return. |
| `mkt_volume_z_3m` | z-score of mean daily volume in the last 3 months vs the earlier ~9 months of the 12m window (needs ≥10 recent and ≥30 baseline bars, non-zero dispersion). |
| `mkt_regime_spy_above_200d` | 1 when SPY's adjusted close at the cutoff is strictly above its 200-trading-day simple moving average, else 0. |
| `mkt_days_since_12m_high` | Trading bars since the highest adjusted close inside the 12m window (0 = high is the latest bar). |
| `mkt_missing` | 1 when **any** of the eight values above is unavailable (unknown ticker, insufficient 12m history, missing benchmark, or degenerate volume coverage); else 0. |

`attach_market_features(store, examples, companies, tickers=None)` only adds
these keys to each example's `features` mapping. Base R&D and financial features
are never removed or overwritten, and examples without market data get `None`
values plus `mkt_missing = 1` rather than a fabricated default.

## Missing-data policy

- A company with no ticker, a ticker absent from `market_bars`, or insufficient
  12m history gets `mkt_missing = 1` and `None` values.
- If the SPY/XBI benchmarks are missing, the company-level features are still
  reported and only the benchmark-dependent ones (`mkt_rel_*`,
  `mkt_regime_spy_above_200d`) are `None`; the row is flagged.
- `mkt_missing` is a feature for the model, not a filter: missing rows stay in
  the dataset. The ablation therefore compares the feature sets on **identical
  rows**, including the rows where the market block is imputed to the training
  median.

## Real-data ablation (frozen v1 continuation task)

Protocol: frozen v1 `reverse_rd_v1` examples reused unchanged; target = any
material public 510(k)/PMA activity for an already-active company–track pair in
the next 12 months; purged expanding-window rolling-origin evaluation; the final
chronological origin **2025-10-01** is the single untouched holdout (307 rows,
129 positives, prevalence 0.420). Identical rows, algorithm and hyperparameters
across all four feature sets. Reproduce with:

```bash
python scripts/run_market_ablation.py
```

Results (holdout 2025-10-01; higher PR-AUC/Precision@10%, lower Brier/ECE/FPR is
better; Precision@10% is identical because it saturates at the top of the
ranking):

| Model | Features | PR-AUC | Brier | ECE-10 | FPR@0.5 | Precision@10% |
|---|---|---|---|---|---|---|
| A `rd_only` | 10 R&D | 0.793476 | 0.172134 | 0.081120 | 0.275281 | 0.935484 |
| B `rd_financial` | 21 R&D+SEC | 0.792199 | 0.172104 | 0.073737 | 0.264045 | 0.935484 |
| C `rd_market` | 18 R&D+market | 0.792020 | 0.171955 | 0.080433 | 0.269663 | 0.935484 |
| D `rd_financial_market` | 29 all | 0.787156 | 0.172326 | 0.061475 | 0.247191 | 0.935484 |

Marginal value (delta = second − first on the same rows):

| Comparison | PR-AUC | Brier | ECE-10 | FPR@0.5 | Precision@10% |
|---|---|---|---|---|---|
| market on R&D (C − A) | **−0.001456** | −0.000179 | −0.000688 | −0.005618 | 0.000000 |
| financial on R&D (B − A) | −0.001278 | −0.000030 | −0.007383 | −0.011236 | 0.000000 |
| market on R&D+financial (D − B) | **−0.005043** | +0.000222 | −0.012262 | −0.016854 | 0.000000 |
| all vs R&D (D − A) | −0.006320 | +0.000192 | −0.019645 | −0.028090 | 0.000000 |

Reference points from the same run (v1 protocol): per-pair persistence baseline
PR-AUC 0.791259; `rd_only` PR-AUC delta vs that baseline +0.002218 with a paired
bootstrap 95% interval **[−0.031599, +0.036773]** (p(delta ≤ 0) = 0.431) — i.e.
even the R&D features are not statistically distinguishable from per-pair
persistence on this single holdout. The v1 reference block is reproduced
**exactly** (`delta = 0.0` for every metric of `rd_only` and `rd_financial`
against `experiments/reverse_rd_v1/metrics.json`), which confirms the market
ablations share the same rows and evaluation protocol.

### Honest reading

- **Market data does not add incremental ranking value on this holdout.** PR-AUC
  falls by 0.0015 when market features are added to R&D and by 0.0050 when they
  are added on top of R&D+financial. Negative results are kept, not hidden; this
  is an expected possible outcome and is reported as such.
- Calibration moves in the opposite, small direction: Brier is marginally lower
  for `rd_market` (−0.000179) and ECE/FPR are lower, especially for
  `rd_financial_market` (ECE 0.0615 vs 0.0737). With 307 holdout rows these are
  point estimates; no significance test is claimed for any delta.
- The market group is incomplete: 62/307 holdout rows (20.2%) are
  median-imputed, concentrated in the 13 uncovered companies. The imputation
  indicator lets the model down-weight them, but this ablation cannot measure
  what a complete market panel would have contributed.
- One chronological holdout is a directional check, not proof. The multi-holdout
  protocol was **not available** in this worktree (the installed
  `run_backtest` has no `holdouts` parameter; that change is owned by a separate
  worktree), so only the frozen single holdout was run; this is recorded in
  `evaluation_protocol.multi_holdout` of the JSON artifact.
- **Stock returns are not technological capability.** A price move is not
  evidence about internal R&D, and no causal market→R&D mechanism is claimed.

## Explicit non-goals and boundaries

- **Market capitalisation and valuation multiples are NOT implemented.** There
  is no shares-outstanding, enterprise-value or book-value data in this
  database, and deriving a market cap from price alone would fabricate a
  fundamental factor. Any future version needs a documented point-in-time
  shares-outstanding source (with split history) before this can be added.
- No intraday, options, short-interest, analyst, patent, publication or
  alternative-data market features are implemented.
- The market lane is a small, survivorship-biased, partly non-US sample; it is
  not a market-factor model and is not used for trading signals in this layer.
- Raw bars are not committed (gitignored `data/`); the committed artifact is
  `experiments/reverse_rd_v2/market_metrics.json`, which reproduces from the
  command above on a machine that has the base repository's `prices` table.
