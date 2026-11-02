# Phase 3A — unified Forecast Registry + continuous forecasting cycle

This documents the Phase 3A work (post-v0.4.0): the canonical immutable
`medradar/forecast_registry.py` becomes the **single registry** for the Horizon
forecasting lane, and a continuous cycle trains, scores, registers, verifies and
exports forecasts on the research database.

Status: implemented and run on the staged `data/research.sqlite` (276 MB,
gitignored); the GitHub workflow is committed but **not executed** in this
environment (see Schedule).

## Decision record (nrec)

1. **A quarterly-cutoff forecast is a `nowcast`, not a `forecast` and not a
   fixture.** The Horizon lane predicts any material public 510(k)/PMA activity
   in `(cutoff, cutoff + horizon]`. It is necessarily registered *after* the
   cutoff, so part of the target window has already elapsed. The existing
   registry only allowed a `forecast` when `window_start >= generated_at`, and
   the alternatives were dishonest: labelling it `forecast` violates the
   pure-future rule, labelling it `retrospective_fixture` falsely says the data
   are history. `record_kind="nowcast"` is the honest third kind: prospective
   (the outcome is still unknown at registration) but with an already-open
   window (`window_start <= generated_at < window_end`).
2. **Nowcasts never contaminate the pure-future estimate.** They are scored in
   their own explicitly labelled cohort inside the same evaluation block; the
   `headline`/`counts` fields remain `record_kind="forecast"` only.
   `prospective` is a clearly-labelled descriptive union, and
   `record_kind_breakdown` exposes the denominators per kind.
3. **A missing snapshot identity is `none`, not a fabricated hash.** Horizon
   records have no TKG snapshot; the registry now stores
   `snapshot_sha256 = NULL` / `verification = "none"` when none is declared.
   Schema version becomes `forecast-registry-2` (fresh files only; no released
   registry exists).
4. **One training path.** `horizon.build_forecasts()` is the pure extraction of
   `horizon.create_forecasts()` (same features, same deterministic
   `LogisticBaseline`, same hyperparameters as the frozen reverse_rd_v2 run).
   The cycle uses it so it can register records without touching the research
   DB's legacy `horizon_forecasts` table, and it filters
   `dataset_version="reverse_rd_v1"` so the new entry-target examples can never
   leak into the continuation model.
5. **No LLM (or any other) probability is invented.** The registered `p` is the
   frozen logistic model's output on the frozen feature contract; the adapter
   has no fallback constant.

## Record kinds and nowcast validation (enforced in `forecast_registry.py`)

| kind | window rule at registration | scored in |
|---|---|---|
| `forecast` | explicit/`generated_at` start `>= generated_at`, end `> generated_at` | pure-future `counts`/`headline`/`strata` |
| `nowcast` | explicit `window_start <= generated_at < window_end`, `information_cutoff <= window_start`; a closed window is rejected | separate `nowcast` cohort; descriptive `prospective` union |
| `retrospective_fixture` | any window (may be historical) | `retrospective` block only |

`window_end` is always derived (`window_start + horizon_months`, month-end
clamped) and an explicit `window_end` must match exactly. Nowcast rows are
append-only exactly like pure forecasts (same SQL guards). Missing
`window_start`, a future start, a closed window, a horizon mismatch, or a cutoff
after the start are all rejected.

## Adapter (`medradar/intelligence/forecasting/registry_adapter.py`)

`to_registry_spec(record, *, data_provenance, feature_version, snapshot_path=None)`
maps a Horizon record:

| Horizon record | registry spec |
|---|---|
| `forecast_id` + `model_version` | `idempotency_key = "horizon:<forecast_id>:<model_version>"` |
| (always) | `record_kind = "nowcast"` |
| `target_company`, `technology_track` | `target.type="company_track"`, `target.id="<company>/<track>"`, `attrs={company, track, event_kinds:["510k","pma"], material_pma_only:true}` |
| `predicted_probability` | `p` |
| `forecast_horizon_months` | `horizon_months` |
| `historical_information_cutoff` | `information_cutoff` **and** `window_start` |
| `horizon_end` | explicit `window_end` (re-derived and cross-checked; a mismatch is rejected) |
| `model_version` | `model_version` |
| — | `feature_version` (caller constant, currently `reverse-rd-v2-features`) |
| provenance block | `evidence`: `source_locator`, `evidence_sha256 = sha256(canonical provenance JSON)`, `evidence_kind="source_observed"`, `provenance=[{source_locator, evidence_sha256}]` |
| optional snapshot file | `snapshot={"sha256": <manifest snapshot_sha256>, "path": ...}` → `verified_local` in the registry |

`register_horizon_forecasts(registry, records, ...)` returns
`{"registered", "idempotent", "rejected":[{forecast_id, error}], "prediction_ids"}`.
An exact retry is `idempotent`; the same key with a **different probability
raises `IdempotencyConflict`** (it is never silently overwritten, and it is not
downgraded to a per-record rejection).

### Verification with coverage guards

`verify_registered_forecasts(registry, store, coverage_end, as_of=None)`:

- resolves only **still-unresolved registered nowcasts** whose whole window
  matured *inside the observed coverage*: `window_end <= min(as_of, coverage_end)`;
- queries `events` for the target company/track in `(window_start, window_end]`,
  keeping 510(k) rows and material PMA rows only
  (`supplement_number in {"", 0, S0}` or `PANEL TRACK`), and drops events whose
  `available_at` is after the coverage end (no resolving from knowledge the
  coverage does not contain);
- outcome 1 with `event_time` = first matching event date, otherwise outcome 0
  (negative) once the window has matured;
- everything else stays `pending`; per-row resolution errors are counted in
  `errors`/`error_details` instead of aborting the batch.

## Continuous cycle (`scripts/forecast_cycle.py`)

```bash
python scripts/forecast_cycle.py \
  --db data/research.sqlite --registry data/registry.sqlite \
  --out out/forecast_cycle --horizon 12 --top-n 25 \
  --coverage-end 2026-10-15 --offline
```

Steps (implemented in `medradar/intelligence/forecasting/cycle.py`):

1. **train** - load the mature `reverse_rd_v1` continuation examples from
   `forecast_examples` (explicit dataset filter) and fit `LogisticBaseline` on
   the frozen 21-feature contract (10 R&D-history + 11 SEC Company Facts,
   defaults 180 epochs / lr 0.15 / l2 1.0);
2. **score** - build the current-quarter pending candidates with the existing
   point-in-time `build_examples` (features require
   `event_date/available_at <= cutoff`), rank by predicted probability, keep the
   top N;
3. **create** - `horizon.build_forecasts` returns Horizon records (deterministic
   ids, model probabilities, uncertainty from three expanding temporal fits);
4. **register** - map through the adapter into the canonical registry as
   `nowcast` rows;
5. **verify** - coverage-guarded resolution from the real events table (see
   above);
6. **export** - `registry.build_artifact(as_of)` → `evaluation.json` plus a
   `cycle.json` log (`run_id`, `generated_at`, counts, registry summary,
   timings, calibration status, artifact hash).

Outputs: `out/forecast_cycle/evaluation.json` (deterministic artifact with
`forecasts`/`nowcasts`/`retrospective_fixtures` lists) and
`out/forecast_cycle/cycle.json`.

### Idempotency and determinism

- The `idempotency_key` is content-independent of wall-clock time, so re-running
  the same cycle registers **zero** new rows: the second run reports
  `registered = 0`, `idempotent = N` and the registry row count is unchanged.
- Forecast ids, probabilities and the exported artifact are deterministic for
  the same registry state: the artifact cutoff is the latest *assigned*
  registry timestamp (`clock_guard.last_at`) rather than the wall clock, so a
  duplicate re-run exports the byte-identical artifact hash. Only genuinely new
  writes (new timestamps) change it.
- `run_id` is a hash of coverage/dataset/feature/version/top-n/forecast-ids
  (no wall clock), so identical cycles share the run id.
- The cycle performs no network I/O (`--offline` states it explicitly).

## Schedule (`.github/workflows/forecast-cycle.yml`)

Weekly (`cron: "0 2 * * 1"`, Monday 02:00 UTC) plus `workflow_dispatch`. The
workflow installs `.[bulk]`, collects openFDA bulk + SEC Company Facts (public
APIs), builds the continuation examples, runs the cycle, runs the offline test
suite and uploads `evaluation.json`/`cycle.json` as build artifacts. SEC requires
the `SEC_USER_AGENT` repository secret; no paid APIs and no LLM calls.

**This workflow is committed but was not executed in the development
environment** (no GitHub Actions run was triggered): do not claim a green run.
Reproduction here uses a locally collected research DB.

## Real run on `data/research.sqlite`

Data: 55,090 FDA events (2016-11-01..2026-10-18), 43,420 SEC facts, 6,701 mature
continuation examples (`reverse_rd_v1`, 2019-10-01..2025-10-01), 41,003 entry
examples (not used by this cycle), 25 pre-existing rows in the legacy
`horizon_forecasts` table (untouched by the cycle).

Command (first run, `--coverage-end 2026-10-15`, offline):

```bash
python scripts/forecast_cycle.py --db data/research.sqlite \
  --registry data/registry.sqlite --out out/forecast_cycle \
  --horizon 12 --top-n 25 --coverage-end 2026-10-15 --offline
```

First run (fresh `data/registry.sqlite`, 2026-11-02):

- `horizon_records = 25`, `registered = 25`, `idempotent = 0`, `rejected = 0`;
  registry: **25 rows, all `record_kind="nowcast"`**, 0 resolutions,
  0 declared snapshots (`verification="none"`);
- target window `[2026-10-01, 2027-10-01)`, information cutoff 2026-10-01,
  `model_version="reverse-rd-logistic-v1"`,
  `feature_version="reverse-rd-v2-features"`;
- `p` ranges over `[0.91925, 0.99998]` with 25 distinct values; **all 25
  probabilities are bit-identical to the frozen 2026-11-01 Horizon run already
  stored in `horizon_forecasts`** (same model/features/hyperparameters; the
  legacy table itself was not touched: still 25 rows, latest creation
  2026-11-01T23:16:37Z);
- verification: `verified = 0`, `pending = 25` — `window_end 2027-10-01` is after
  the coverage end 2026-10-15, so nothing is resolved from incomplete coverage;
- calibration status: `insufficient_matured_forecasts` (0 eligible, 25 unresolved);
- artifact `out/forecast_cycle/evaluation.json`, SHA256
  `45e630481d617df5ea9fc24396416f98a220c241e7376bc6ea031d2c425618fd`,
  `counts_by_record_kind = {forecast: 0, nowcast: 25, retrospective_fixture: 0}`;
- timings: train+score 21.9 s, register 0.15 s, verify <0.01 s, total 22.1 s.

Example registered nowcasts:

| prediction_id | target | p |
|---|---|---|
| `sha256:e2b0750039217d4e3edd7578d36caa30fd5fa6e695305a95c48797eeb0f9050a` | `siemens_healthineers/imaging_mr_ct` | 0.9999816721261416 |
| `sha256:c3b6df5283ea9e1cdab833d332134a70b18dab13f1d2e453f9fbc464a2d4e4c5` | `intuitive_surgical/surgical_robotics` | 0.9997900805152966 |
| `sha256:e9a2afe70c4620a3b2b7f8a7648a13360f40d24b4ee2068fca0f1b7e792c10dc` | `philips/imaging_mr_ct` | 0.9997290077662635 |

Second identical run against the same registry: `registered = 0`,
`idempotent = 25`, registry still 25 rows / 0 resolutions, `run_id`
`5a8bf2b0ad66626c` unchanged and the artifact hash unchanged
(`45e630481d617d…`). No duplicate forecast, no clock consumption for retries.

## Tests

- `tests/test_forecast_registry.py` - `NowcastTests` (accept/reject rules,
  append-only, cohort separation in `evaluate()`/artifact, `schema-2`,
  `snapshot="none"`).
- `tests/test_registry_adapter.py` - field mapping, deterministic specs,
  verified-local snapshot, create/retry/idempotency, conflicting p raises
  `IdempotencyConflict`, rejections, positive/negative/pending/incomplete-coverage
  verification and the material-PMA rule.
- `tests/test_forecast_cycle.py` - synthetic research DB: real model
  probabilities registered as nowcasts, cohort separation, second-run
  idempotency, deterministic artifact/run id across fresh registries, explicit
  `reverse_rd_v1` training filter (entry examples cannot leak), empty-candidate
  cycle.

Run: `python -m medradar selftest` (offline).

## Limitations

- **No calibration claim.** Registered 2026-Q4 nowcasts mature 2027-10-01,
  after the frozen coverage end 2026-10-15, so they are correctly `pending`;
  calibration status is `insufficient_matured_forecasts` until ≥20 matured and
  verified rows exist (expected from 2027-Q4 onward).
- A nowcast is weaker evidence than a pure forecast: part of its window may
  already have elapsed at registration. Never merge the `nowcast` cohort with
  the pure-future `headline` in a skill/calibration claim.
- Verification uses the events table available in the research DB; missing
  coverage keeps rows pending instead of guessing. `available_at` dates inside
  the coverage window are assumed to be the public-availability times recorded
  by collection.
- The model is a deterministic logistic baseline, not an LLM; no
  model-generated textual probability is registered.
- Single writer per registry file (documented in `docs/FORECAST_REGISTRY.md`).

## Reproduce

```bash
python -m medradar selftest                                  # offline tests
python scripts/forecast_cycle.py --db data/research.sqlite \
  --registry data/registry.sqlite --out out/forecast_cycle \
  --horizon 12 --top-n 25 --coverage-end 2026-10-15 --offline
# run it a second time: registered=0, idempotent=N, identical artifact hash
python -c "import json; d=json.load(open('out/forecast_cycle/evaluation.json')); print([f['prediction_id'] for f in d['nowcasts']])"
```
