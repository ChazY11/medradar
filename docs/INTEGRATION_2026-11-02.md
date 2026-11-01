# Integration & defect-fix record — 2026-11-02

This branch (`integration/market-to-rd-v2`, PR against `main` at `7a639f7` / v0.2.2) consolidates
three independently authored research branches into one reviewable target, after an independent
forensic audit of each branch and a defect-fix pass. `main` was not modified and nothing was force
pushed.

## 1. What was integrated

| PR | Head | Contribution | Size | Integrated as |
|---|---|---|---|---|
| #2 `research/research-foundation-integration` | `dedfd68` | Bitemporal TKG (`medradar/tkg`) + immutable Forecast Registry (`medradar/forecast_registry.py`) + ADR/acceptance docs | 14 commits · 28 files · +6014/−3 | merge commit `3c6dd4d` |
| #3 `feature/market-to-rd` | `ad38d27` | Market-to-R&D lane (`medradar/intelligence`): SEC XBRL, USAspending, openFDA bulk, point-in-time examples, logistic Reverse R&D, rolling-origin evaluation, Horizon forecasts, real-data experiment | 34 commits · 60 files · +2453/−25 | merge commit `a1131d6` |
| #1 `feat/frontier-device-radar` | `94c6a10` | Frontier radar (`adcom.py`, `frontier.py`), ClinicalTrials.gov device filter, 8-K pre-submission/designation taxonomy, 50 tracks / 23 domains, look-ahead removal, extreme-return audit | 13 commits · 44 files · +2709/−234 | **squash** `1074e6d` (see §3) |

Fix branches on top of `1074e6d`: `fix/pr2-defects` (`456c638`, merge `023030b`),
`fix/pr1-frontier` (`0e49f19` … `fa3514c`, merge `fff3a82`), `fix/pr3-science`
(`30ea51b`, `1d8ee97`, merge `66fe850`).

The three branches are almost entirely code-disjoint, so only four files needed manual conflict
resolution: `README.md`, `README.zh-CN.md` (union of sections + test count), `pyproject.toml`
(`[tool.setuptools.packages.find] include = ["medradar*"]` so `medradar.tkg` and
`medradar.intelligence` ship in the wheel, plus the optional `bulk = ["ijson>=3.3"]` extra), and
`CHANGELOG.md` (union). `verifier/` kept the Market-to-R&D acceptance flow; PR #1's
self-attestation files and duplicate `docs/docs/ASSUMPTIONS.md` were dropped.

## 2. Independent audit basis

Three isolated worktrees were audited by independent agents (no write access to any branch), then
every claimed number was re-derived from live sources:

- `pr1_and_base_audit.md` — PR #1 + base capability inventory.
- `pr2_audit.md` — 60 TKG probes / 38 registry probes, py3.10 CI reproduced, doc-claim checks.
- `pr3_audit.md` — full live re-download (openFDA bulk 176,466 + 57,373 records; SEC 43,420 facts
  over 32 companies; USAspending 3,453/3,372 awards) and a bit-identical re-run of the frozen
  experiment, plus purge/persistence re-evaluation.

**Verdicts:** PR #3 data are real and the experiment reproduced bit-identically (6,701 examples,
25 origins, holdout 307/129, PR-AUC 0.792370/0.790946), but the v1 evaluation had no purge/embargo,
no persistence baseline and a tautological leakage audit; PR #2's design held up under adversarial
probing but had a py3.10 CI blocker, a date-only timestamp defect and a registry key-rebind hole;
PR #1 contained real engineering but a non-functional live AdCom collector, an empty commit and a
commit whose tree fails 29/53 replay tests.

## 3. Defects fixed in this branch

| Area | Defect | Fix |
|---|---|---|
| py3.10 CI | `fromisoformat` rejects 1/2/4/5-digit fractions on 3.10 (`.5Z`) | shared `medradar/tkg/_time.py` normalises 1–9 digits to 6 before parsing; used by store and registry |
| TKG PIT | date-only inputs rendered `…T00:00:00Z`, breaking same-second cuts and adapter rows | both fast paths render `.000000Z`; tests cover midnight/sub-second cuts |
| Registry | `INSERT OR REPLACE` with reused `idempotency_key` + new `prediction_id` deleted an unresolved forecast | key-rebind `BEFORE INSERT` guard + `forecast_idempotency` ledger guards (owner-level SQL still out of threat model) |
| Registry | `retrospective_fixture` could not hold a historical backtest window | historical windows allowed for fixtures; still excluded from prospective headline |
| Evaluation | no purge/embargo: training labels overlapped the test window | purged/embargoed training is the default; old leaky numbers kept as a labelled diagnostic (holdout PR-AUC 0.7924→0.7935, Brier 0.1687→0.1721, ECE 0.0605→0.0811, FPR 0.2416→0.2753) |
| Baselines | no naive benchmark; 0.79 PR-AUC overstated skill | constant / company / track / per-pair base-rate baselines + deterministic paired bootstrap (per-pair AP 0.7913 vs model 0.7935; Δ CI [−0.032, +0.037]) |
| Leakage audit | checked only a builder-declared field | independent as-of replay of all 21 features from source tables (6,701 examples / 140,721 values / 0 mismatches) with positive and negative controls |
| Forecast evidence | raw `value` shown next to standardized contribution | `raw_value`, `standardized_value`, `median_imputed` fields added |
| AdCom source | silent `status="ok"` with 0 parsed meetings (JS-rendered table) | returns `empty`/`source_changed` + warning, parses `<time datetime>`, documented experimental |
| Case library | raw `open` entry vs adjusted `close` exit (split/dividend fake alpha) | entry uses `prices.adjusted_open`; 2:1-split invariance test |
| Timestamp gate | looked retroactive but only applies to newly collected rows | documented prospective-only; `medradar audit` reports a read-only `legacy_timestamp_promotions` count; manual demotion recipe in `docs/DATA.md` |
| Hygiene | duplicate `docs/docs/ASSUMPTIONS.md`, stale hardcoded test counts, historical pinned hashes | duplicate removed, published links rewritten, counts point to `python -m medradar selftest`, superseded hashes documented in `docs/research/INTEGRATION_FIXES.md` |

## 4. Verification actually run

Offline suite `python -m medradar selftest` (no network, no API key):

| Interpreter | Result |
|---|---|
| CPython 3.12.10 | Ran **578** tests — OK (skipped=3), exit 0 |
| CPython 3.11.15 | Ran **578** tests — OK (skipped=3), exit 0 |
| CPython 3.10.20 | Ran **578** tests — OK (skipped=3), exit 0 |

Wheel: `uv build --wheel` → `medradar-0.3.0`; installed into a fresh 3.12 venv and executed from a
non-repo cwd: `medradar --help`, `medradar.forecast_registry demo`, `medradar.tkg demo` and
`config_origin="installed"` all pass. The wheel ships `medradar.tkg`, `medradar.intelligence` and
the config data-files.

Acceptance script: `python verifier/v1/verify.py` runs the full offline suite in a subprocess and
20 behavioural checks (artifact presence, recomputed origin stability, recomputed financial marginal
value, leakage-audit workload/method, evidence fields, REPORT-vs-metrics numbers) — exit 0.

Frozen experiment regeneration (from the collected DB; `data/` is gitignored):

```
55,090 FDA events · 43,420 SEC facts / 32 companies · 3,453 procurement awards (0 PIT-usable)
6,701 examples / 25 quarterly origins · holdout 2025-10-01 = 307 rows / 129 positives
purged holdout (rd_only): PR-AUC 0.7935 · Brier 0.1721 · ECE 0.0811 · FPR 0.2753
purged holdout (rd_financial): PR-AUC 0.7922 · Brier 0.1721 · ECE 0.0737 · FPR 0.2640
```

## 5. Reproduce

```bash
pip install -e '.[dev]'
python -m medradar selftest                 # 578 offline tests
python -m pytest tests/ -q                  # same suite through pytest
python verifier/v1/verify.py                # behavioural acceptance, exit 0

# Research lane (network; bulk ZIPs are ~270 MB, cached under $MEDRADAR_HOME/data/cache)
pip install -e '.[bulk]'
export MEDRADAR_HOME=/tmp/medradar-research
python -m medradar.intelligence.pipeline collect --source fda --months 120
python -m medradar.intelligence.pipeline collect --source sec
python -m medradar.intelligence.pipeline collect --source procurement --start-date 2016-01-01
python -m medradar.intelligence.pipeline research --horizon 12
```

## 6. What this branch does *not* claim

- The prediction target is **continuation of public activity in an already-active company–track
  pair**, not first entry and not the unobservable internal R&D start date.
- The 0.79 PR-AUC is dominated by persistence (per-pair base rate); no incremental skill is
  established against that baseline. The financial features add no stable out-of-sample gain.
- One 307-row holdout is not proof of stability, in either direction.
- SEC revenue is consolidated company facts, never product-line sales. USAspending award amounts are
  obligations; the current snapshot (`pit_usable=0`) is excluded from historical gain claims.
- A regulatory milestone is a lagging proxy for R&D activity; nothing here supports a causal
  "markets drive R&D" conclusion.
- The AdCom collector is experimental: FDA renders its calendar rows client-side, so a static fetch
  currently yields zero meetings (reported loudly, not silently).
- Market prices, patents, publications and hiring signals are **not** yet features (Phase 2), and no
  temporal graph neural model is claimed to beat the logistic baseline (Phase 3).
- Historical pinned hashes in `docs/research/FOUNDATION_*` / `FORECAST_REGISTRY_LOG.txt` were recorded
  under `code_version=medradar-0.2.2`; the 0.3.0 integration changed the canonical rendering, so the
  current values are listed in `docs/research/INTEGRATION_FIXES.md`.
