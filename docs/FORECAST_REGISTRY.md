# Forecast Registry — usage & contract

Minimal **immutable Forecast Registry + deterministic evaluation** foundation
(`medradar/forecast_registry.py`, stdlib+SQLite only). It exists so that future
3/6/12/24-month forecasting research can register *real* forecasts before
outcomes are known and score them later without after-the-fact leakage. Since
Phase 3 it is also the canonical registry for the Horizon forecasting lane
(`medradar/intelligence/forecasting/registry_adapter.py`); see
[PHASE3_REGISTRY.md](PHASE3_REGISTRY.md).

Scope discipline: this module contains **no model**, generates **no
predictions**, and makes **no accuracy claims**. All demo/test records are
synthetic and in-memory; they never masquerade as historical forecasts. See
`docs/research/FORECAST_REGISTRY_ADR.md` for the decisions and acceptance
report.

Three **record kinds** are explicit because registration time relative to the
target window is evidence quality:

| `record_kind` | Registration-time window | Meaning |
|---|---|---|
| `forecast` | `window_start >= generated_at` (pure future) | genuinely ex-ante forecast |
| `nowcast` | `window_start <= generated_at < window_end` | prospective forecast registered while the window is already open (e.g. a quarterly-cutoff Horizon forecast before its 12-month horizon ends) |
| `retrospective_fixture` | any window, may be historical | prior backtests only; never scored prospectively |

## CLI (fully offline)

```bash
python -m medradar.forecast_registry demo                      # synthetic in-memory demo
python -m medradar.forecast_registry register --db reg.sqlite --spec forecast.json
python -m medradar.forecast_registry resolve  --db reg.sqlite --spec resolution.json
python -m medradar.forecast_registry evaluate --db reg.sqlite --as-of 2024-06-01T00:00:00Z
python -m medradar.forecast_registry export   --db reg.sqlite --as-of 2024-06-01T00:00:00Z --out-dir out/eval
```

`demo` builds three synthetic forecasts on an injected in-memory clock,
resolves one positively inside its window, censors one as unknown, leaves one
unresolved, then evaluates and exports a deterministic artifact. It prints
`"synthetic": true` and touches no files unless `--out-dir` is given.

### Forecast spec (`register`)

```json
{
  "idempotency_key": "required, stable, caller-chosen",
  "record_kind": "forecast | nowcast | retrospective_fixture (default forecast; nowcast = prospective with an already-open window; retrospective_fixture = prior backtests)",
  "target": {"type": "nmpa_acceptance", "id": "DEV-123", "attrs": {"synthetic": true}},
  "horizon_months": 6,
  "p": 0.7,
  "information_cutoff": "2024-01-10T00:00:00Z",
  "window_start": "forecast: optional >= generated_at (default generated_at);"
                  " nowcast: REQUIRED and <= generated_at (the already-open window);"
                  " retrospective_fixture: may be historical",
  "window_end": "always derived: window_start + horizon_months calendar months (month-end clamped);"
                " an explicit value is accepted only when exactly equal to the derived end",
  "model_version": "required", "feature_version": "required",
  "snapshot_sha256": "optional 64-hex declared snapshot identity (omit for 'none'), or",
  "snapshot": {"sha256": "64-hex", "path": "optional local medradar-tkg snapshot.json to verify"},
  "evidence": {
    "source_locator": "required", "evidence_kind": "source_observed|inferred|reconstructed",
    "evidence_sha256": "64-hex",
    "provenance": [{"source_locator": "...", "evidence_sha256": "..."}]
  }
}
```

### Resolution spec (`resolve`)

```json
{
  "prediction_id": "sha256:... of a registered forecast",
  "outcome": 1,                          // 0/1 only; omit + "kind": "censor" for unknown/censored
  "event_time": "2024-03-20T00:00:00Z",  // required for outcome=1: must lie in the target window AND
                                      // must not be after the store-assigned resolved_at (no advance
                                      // knowledge of future events); must be absent for 0/censor
  "reason": "required for every version past the first (corrections)",
  "evidence": {"source_locator": "...", "evidence_kind": "...", "evidence_sha256": "..."}
}
```

## Contract (enforced, tested)

**Registration**
- `generated_at` is assigned **inside the store** from a monotonic UTC clock;
  there is no caller channel (no backdating), and an injected test clock is
  accepted only on `:memory:` stores. Timestamps are strict: naive input is
  rejected, offsets/fractions normalize to fixed-microsecond UTC (`...Z`),
  date-only input is widened to `T00:00:00.000000Z` with its precision stored.
  1–9 digit fractional seconds are accepted and normalised identically on every
  supported Python (3.10+), where stdlib `fromisoformat` is stricter; parsing
  and rendering share `medradar/tkg/_time.py` with the TKG store.
- `p` must be a finite number in `[0,1]` (bools rejected); evidence requires a
  non-empty `source_locator`, a valid `evidence_kind`, 64-hex
  `evidence_sha256`, and a non-empty `provenance` locator list; horizon must
  be 3/6/12/24; `information_cutoff <= generated_at`.
- For prospective `record_kind="forecast"` rows the target window is
  **genuinely future**: `window_start` equals `generated_at` or is explicitly
  `>= generated_at`, and `window_end > generated_at`.
- `record_kind="nowcast"` is a prospective forecast registered **while the
  target window is already open**: an explicit `window_start` is required and
  must satisfy `window_start <= generated_at < window_end`, with
  `information_cutoff <= window_start`. A nowcast whose window has already
  closed is rejected (that is a retrospective claim, not a nowcast). Nowcast
  rows are append-only exactly like pure forecasts and are scored in their own
  prospective cohort (see Evaluation).
- `record_kind="retrospective_fixture"` is explicitly exempt from the
  future-only rule so prior backtests can be registered with a historical
  window (e.g. a 2020 window registered in 2026); such rows are still kept out
  of the prospective cohorts.
- `window_end` is **always derived** as
  `window_start + horizon_months` calendar months with documented month-end
  clamping (`2024-01-31` + 3 → `2024-04-30`; `2024-02-29` + 12 →
  `2025-02-28`), so the `horizon_months` label always denotes the **actual**
  window duration and scoring strata never mix incomparable horizons. An
  explicit `window_end` is accepted only when it exactly equals the derived
  end; anything else (e.g. a shortened or lengthened override) is rejected.
  The window is half-open `[start, end)`.
- `prediction_id` is content-addressed (`sha256:` + canonical content hash).
  Idempotency: an exact retry returns the original record **without consuming
  the write clock even if the clock moved**; a conflicting key reuse raises
  `IdempotencyConflict`; identical content under a new key is the same
  immutable forecast.
- Immutability is **physical for rewrites/deletes**: SQL triggers reject
  `UPDATE` and `DELETE` on `forecasts`, `resolutions` and the
  `forecast_idempotency` ledger. `INSERT OR REPLACE` is rejected too: SQLite
  resolves REPLACE conflicts below the DELETE-trigger layer, so dedicated
  `BEFORE INSERT` guards cover (a) an existing `prediction_id`, (b) an
  existing `idempotency_key` bound to a **different** `prediction_id`, and
  (c) any duplicate insert into the idempotency ledger. Guard (b) is what
  stops `INSERT OR REPLACE` with a new `prediction_id` from silently deleting
  an unresolved forecast. **Boundary**: this is not tamper-proofness against
  the DB owner - an owner can drop triggers or rebuild the file, and a stray
  SQL session can still **append** forged rows (a trigger cannot tell a forged
  append from a genuine one, and no such guarantee is claimed). What the guards
  do guarantee is that existing history cannot be **rewritten or deleted**
  through the trigger path. Single writer per store file.

**Resolution**
- Separate append-only ledger referencing `prediction_id` (FK enforced).
  Outcomes are 0/1 only, with evidence and `resolved_at` assigned by the store
  (never backdated; evidence metadata may predate the resolution).
- A positive outcome may resolve when the event arrives; its `event_time`
  must lie inside the target window — pre-forecast and post-window events are
  rejected — and must **not be after the store-assigned `resolved_at`** (no
  advance knowledge of future events; the failed attempt rolls back whole,
  clock included). A negative resolves only **after the full window matured**
  (store clock ≥ `window_end`). Unknown/censored targets get
  `kind="censor"` and stay **explicitly unscored**.
- Corrections are new `resolution_version` rows with a mandatory `reason`;
  the original is preserved. `p` is never updated to improve a score.

**Evaluation (`evaluate --as-of`)**
- `as_of` must not be after the store clock. Only forecasts with
  `generated_at <= as_of` and, per forecast, the **latest resolution with
  `resolved_at <= as_of`** are visible — a later correction cannot leak into
  an earlier as-of view.
- Eligible = latest resolution is a 0/1 outcome and, for negatives, the window
  has matured by `as_of`. Unresolved, censored and immature negatives are
  **counted, never silently scored as zero**.
- Metrics per cohort: Brier score; log loss with documented epsilon clipping
  (`p` clipped to `[1e-15, 1-1e-15]`); calibration with **exact** equal-width
  bins on boundaries `i/10` (last bin closed at 1.0) and ECE. All values are
  finite; an empty cohort yields explicit `null` metrics.
- Stratification is by `(horizon_months, model_version)`; the headline
  aggregates all eligible forecasts and carries explicit `mixed_targets`
  scope metadata so strata are never mixed silently. No AUC/AP in the MVP.
  Toy-n results must not be read as calibration evidence.
- **Cohort separation.** `counts`/`headline`/`strata` contain only
  `record_kind="forecast"` (the pure-future estimate). `nowcast` is a sibling
  block with its own `counts`/`headline`/`strata` and an explicit label;
  `prospective` is the descriptive union `forecast+nowcast` (explicitly *not*
  the pure-future estimate); `record_kind_breakdown` gives the denominators per
  kind. A nowcast can therefore never contaminate the pure-future aggregate.
- `record_kind="retrospective_fixture"` rows (prior backtests) are stored but
  **never** silently enter any prospective metrics or denominators: they are
  reported only under the explicitly labeled `retrospective` block (own
  counts, headline and strata). Fixtures may carry a historical window (see
  Registration), which is why the future-only window rule would make the
  documented prior-backtest use case impossible.

**Deterministic artifact (`export`)**
- `evaluation.json` contains the forecast/resolution versions visible at
  `as_of`, the evaluation, `scoring_version`, schema/code versions and
  provenance metadata; canonical UTF-8 JSON (sorted keys) hashed with SHA256.
  The three record kinds live in separate, explicitly labeled lists
  (`forecasts` / `nowcasts` / `retrospective_fixtures`); the manifest carries
  both the pure-future `counts` and `counts_by_record_kind`.
  No wall-clock report timestamp: writes after `as_of` cannot change the hash,
  and no live whole-DB fingerprint is included.

**Snapshot provenance**
- The registry may store the TKG snapshot manifest identity
  (`snapshot_sha256`) plus a verification flag. Omitting a snapshot is
  explicit: the row records `verification="none"` and never a fabricated hash.
  A bare hash is **declared provenance** — hash length proves nothing
  cryptographically. If a local `snapshot.json` path is supplied at
  registration, the hash is recomputed with the existing `medradar.tkg` APIs
  and a mismatch is a hard error (`verified_local`).

## Library use

```python
from medradar.forecast_registry import ForecastRegistry

with ForecastRegistry("reg.sqlite") as registry:          # or ForecastRegistry() for in-memory
    registered = registry.register({...forecast spec...})
    registry.resolve({"prediction_id": registered["prediction_id"], "outcome": 1,
                      "event_time": "2024-03-20T00:00:00Z", "evidence": {...}})
    evaluation = registry.evaluate("2024-06-01T00:00:00Z")
    artifact = registry.build_artifact("2024-06-01T00:00:00Z")
```

The Horizon lane registers through the adapter instead of hand-building specs
(see [PHASE3_REGISTRY.md](PHASE3_REGISTRY.md)):

```python
from medradar.intelligence.forecasting.registry_adapter import (
    FEATURE_VERSION, register_horizon_forecasts, verify_registered_forecasts)

counts = register_horizon_forecasts(registry, horizon_records,
                                    data_provenance=provenance,
                                    feature_version=FEATURE_VERSION)
verification = verify_registered_forecasts(registry, intelligence_store, "2026-10-15")
```

## Limitations

- Single writer per store file; no multi-writer coordination.
- No tamper-proof guarantees against whoever controls the SQLite file: the SQL
  guards stop `UPDATE`/`DELETE`/`REPLACE` rewrites, not owner-level forged
  **appends** (a stray session can still insert a plausible new row, and the
  owner can drop triggers or rebuild the database).
- `declared` snapshot hashes are caller assertions, not validation; omitting a
  snapshot is recorded as `none` (never invented).
- Outcomes are binary only; multi-class / continuous targets are future work.
- A `nowcast` is honest but weaker evidence than a pure `forecast`: part of its
  target window elapsed before registration, so the two cohorts must be
  compared separately (`nowcast` block vs `headline`), never merged into one
  claim.
- No in-place schema migration: the immutability triggers are (re)applied with
  `CREATE TRIGGER IF NOT EXISTS` every time a store is opened, so existing
  files gain them automatically. Schema changes that SQLite cannot `ALTER`
  (nullable `snapshot_sha256`, the `nowcast` record-kind/window `CHECK`s) are
  part of the fresh **`forecast-registry-2`** schema: a registry file created
  by an earlier pre-release build (schema-1) must be recreated. No released
  database exists; this registry has never been published.
