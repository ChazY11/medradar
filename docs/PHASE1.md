# Phase 1 — scientific hardening of the Market-to-R&D layer

Status: implemented and committed on branch `phase1/entry-multiwindow`. Real-data run frozen under [`experiments/reverse_rd_v2/`](../experiments/reverse_rd_v2/). This phase deliberately does **not** add model complexity: it adds a harder target, an honest multi-window protocol, and the real-data numbers, including negative ones.

## What changed

1. **Dormant → active track-entry target** (`medradar/intelligence/features/research_features.py`).

   `build_entry_examples` builds `dataset_version='first_entry_v1'` in the existing `forecast_examples` table (no schema change). At each quarterly quarter-start cutoff `t`:
   - candidate: a `(company_key, track_id)` pair where the company already had a material event by `t`, the track is non-null, and the pair had **zero** material events in `(t − 36 months, t]`;
   - candidate universe: active companies × tracks observed by `t` (so never-observed pairs are candidates);
   - label: 1 iff a material event occurs in `(t, t + 12 months]`; mature iff `t + 12m <= coverage_end` (asserted against the documented 2026-10-15 bulk-window end);
   - features: the ten v1 R&D-history features (shared helper; an empty history gets zero counts / recency top-code / zero observable active years), the eleven consolidated SEC features, and six entry-specific features — `rd_pair_inactive_months` (capped at 120 months), `rd_company_active_tracks_12m`, `rd_company_active_tracks_delta`, `rd_track_active_companies_12m`, `rd_track_active_companies_delta`, `rd_company_track_novelty_share`;
   - everything strictly point-in-time (`event_date <= t` AND `available_at <= t`; financials `filed/available_at <= t`), with exact calendar-month dormancy.

   The left-censoring statement is explicit in [`docs/REVERSE_RD.md`](REVERSE_RD.md): the bulk window starts 2016-11-01, so "dormant" means "no observed event inside the window", never "provably inactive"; the 120-month cap is a top-code; the label is a first *observed* public milestone, not internal R&D start.

2. **Multi-window expanding-origin evaluation** (`medradar/intelligence/evaluation/backtesting.py`).

   `run_backtest(..., holdouts: int = 1)`: with `holdouts=K` the last K evaluable origins (those with a purged training set) are evaluated as sequential holdout windows, each retrained on its own expanding purged training set (`cutoff + horizon_months <= origin`), identical features/algorithm/hyperparameters. Every model and every persistence baseline gets per-window metrics plus mean/std across windows; the paired bootstrap `AP(model) − AP(pair base rate)` is repeated per window. `holdouts=1` reproduces the v1 output exactly — the v1 single-holdout fields are unchanged and the multi-window fields are additive.

3. **Leakage audit extended to the entry target** (`medradar/intelligence/evaluation/leakage_audit.py`). The independent as-of replay now recomputes the six entry-specific features and the base features of never-observed pairs. This was the minimum change needed to keep the "every stored feature must be reproducible from as-of source rows" property for the new dataset; it is additive and v1 audits are unchanged.

4. **Reproducible real-data driver** (`experiments/reverse_rd_v2/run_v2.py`) and frozen artifacts: `config.json`, `data_provenance.json`, `continuation_metrics.json`, `entry_metrics.json`, `REPORT.md`, `run_timings.json`.

## Results on the real database

Exact values are in [`experiments/reverse_rd_v2/REPORT.md`](../experiments/reverse_rd_v2/REPORT.md) and the two metrics JSON files. Summary:

**Datasets.** Material events 3,833 over 51 companies / 38 tracks / 322 observed pairs; coverage 2016-11-01..2026-10-15.

- Continuation (v1 target): 6,701 mature examples, 25 origins (2019-10-01..2025-10-01), 3,154 positives, base rate 0.470676.
- Entry (new target): 41,003 mature examples, 24 origins (2020-01-01..2025-10-01), 503 positives, base rate 0.012267; 1,634..1,730 candidates and 10..28 positives per origin.
- Independent as-of leakage replay: continuation 6,701 examples / 140,721 values; entry 41,003 examples / 1,107,081 values; **0 mismatches, 0 unreplayable** in both.

**Holdout windows** (both targets): 2025-04-01, 2025-07-01, 2025-10-01.

**Continuation, AP mean across the 3 windows:** 0.773718 (rd_only, std 0.023156) / 0.772689 (rd_financial, std 0.023820). The 2025-10-01 window reproduces v1 exactly (0.793476 / 0.792199). Pair-persistence baseline mean AP 0.755470; model−pair mean Δ 0.018248 / 0.017219, but only the 2025-04-01 window's 95% CI excludes zero.

**Entry, AP mean across the 3 windows:** 0.106792 (rd_only, std 0.013675) / 0.114869 (rd_financial, std 0.014715) against a 0.015119 constant-prevalence baseline and 0.051511 pair-persistence baseline; model−pair mean Δ 0.055281 / 0.063358, with only 2025-10-01 excluding zero. Positive-target lead ≈ 190.6 days. Per-origin AP ranges 0.018130..0.237008, so the target is weak and highly origin-dependent.

## What did NOT improve

- **Continuation ranking is unchanged and still mostly pair persistence.** The multi-window AP (0.773718 / 0.772689) and the per-window model−pair intervals (two of three include zero) confirm the v1 null result. Consolidated financial features still do not improve continuation ranking: mean Δ AP −0.001030 (ECE −0.012563 and FPR −0.014888 improve, i.e. calibration only).
- **The entry target is a weak signal, not a validated predictor.** Mean AP ≈ 0.107/0.115 at a 1.5% base rate is above the baselines but driven by few positives per window; two of three windows have CIs including zero, and the earliest origins are at chance (AP 0.018130).
- **Financial features do add a positive entry-ranking delta** (mean +0.008077 AP, positive in all three windows) — the only consistently signed ablation gain in v1/v2 — but with 25–27 positives per window this is a hypothesis to test with more data, not a stable effect.
- **FPR@0.5 is degenerate for entry** (0.000000 in every window; probabilities never cross 0.5 at a 1.5% base rate). Precision@10% is reported instead.
- **Sparsity check.** The task's downgrade rule (<5 positives per origin) is not triggered: every entry origin has 10–28 positives. The limitation is instead window-to-window variance and overlapping label windows, not absence of positives.

## How to reproduce

```bash
# From the repository root, with the collected research database at data/medradar.sqlite
python experiments/reverse_rd_v2/run_v2.py --db data/medradar.sqlite --holdouts 3

# Offline checks (py3.12)
python -m pytest
python -m medradar selftest

# Verify that every decimal quoted in REPORT.md / PHASE1.md exists in the JSON artifacts
python experiments/reverse_rd_v2/check_numbers.py
```

The driver rebuilds both datasets, persists the entry examples under `first_entry_v1`, runs both leakage audits, runs both multi-window backtests and rewrites the four JSON artifacts plus `run_timings.json`. `experiments/reverse_rd_v1/` is not modified.

Environment caveat for this worktree: `python -m medradar selftest` runs 588 tests and the only failures are three pre-existing `tests/test_products.py::ArtifactTests` cases (`test_catalog_covers_real_top2000`, `test_catalog_is_idempotent_and_preserves_reviewed_entries`, `test_families_artifact_matches_rebuild`). They compare `config/*.json` catalog artifacts against `data/medradar.sqlite` and fail when that file is the reduced research database (55,090 device events only); with `data/medradar.sqlite` absent they skip and the suite is green (12 passed, 3 skipped in that file). They are environment-induced, not caused by this phase; the 26 intelligence-layer tests and every other test pass.

## Files touched

- `medradar/intelligence/features/research_features.py` — shared pair-feature helper, `material_event_coverage`, `entry_origins`, `build_entry_examples`, entry constants.
- `medradar/intelligence/evaluation/backtesting.py` — `holdouts`, per-window metrics/summaries/baselines, per-window paired bootstrap.
- `medradar/intelligence/evaluation/leakage_audit.py` — entry-feature as-of replay and never-observed-pair base replay.
- `tests/test_intelligence.py` — 10 new tests (entry target semantics/PIT/audit, multi-window protocol).
- `docs/REVERSE_RD.md` — entry target, left-censoring statement, multi-window protocol, limitations.
- `docs/PHASE1.md`, `experiments/reverse_rd_v2/` — this document and the frozen v2 artifacts.
