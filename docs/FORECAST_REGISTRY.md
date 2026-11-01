# Forecast Registry — usage & contract

Minimal **immutable Forecast Registry + deterministic evaluation** foundation
(`medradar/forecast_registry.py`, stdlib+SQLite only). It exists so that future
3/6/12/24-month forecasting research can register *real* forecasts before
outcomes are known and score them later without after-the-fact leakage.

Scope discipline: this module contains **no model**, generates **no
predictions**, and makes **no accuracy claims**. All demo/test records are
synthetic and in-memory; they never masquerade as historical forecasts. See
`docs/research/FORECAST_REGISTRY_ADR.md` for the decisions and acceptance
report.

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
  "record_kind": "forecast | retrospective_fixture (default forecast; use the latter for prior backtests and label them)",
  "target": {"type": "nmpa_acceptance", "id": "DEV-123", "attrs": {"synthetic": true}},
  "horizon_months": 6,
  "p": 0.7,
  "information_cutoff": "2024-01-10T00:00:00Z",
  "window_start": "optional, must be >= generated_at (default: generated_at, never an event-date fallback)",
  "window_end": "always derived: window_start + horizon_months calendar months (month-end clamped);"
                " an explicit value is accepted only when exactly equal to the derived end",
  "model_version": "required", "feature_version": "required",
  "snapshot_sha256": "64-hex, or",
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
- `p` must be a finite number in `[0,1]` (bools rejected); evidence requires a
  non-empty `source_locator`, a valid `evidence_kind`, 64-hex
  `evidence_sha256`, and a non-empty `provenance` locator list; horizon must
  be 3/6/12/24; `information_cutoff <= generated_at`.
- The target window is **genuinely future**: `window_start` equals
  `generated_at` or is explicitly `>= generated_at`. `window_end` is **always
  derived** as `window_start + horizon_months` calendar months with documented
  month-end clamping (`2024-01-31` + 3 → `2024-04-30`; `2024-02-29` + 12 →
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
- Immutability is **physical**: SQL triggers reject `UPDATE`, `DELETE`, and
  `INSERT OR REPLACE` on both ledgers (REPLACE is guarded with a dedicated
  `BEFORE INSERT` existence trigger because SQLite resolves it below the
  trigger layer). This is **not** tamper-proofness against the DB owner, and
  no such claim is made. Single writer per store file.

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
- `record_kind="retrospective_fixture"` rows (prior backtests) are stored but
  **never** silently enter prospective headline metrics or denominators: the
  default evaluation counts and scores only `record_kind="forecast"`, and the
  fixture cohort is reported separately under the explicitly labeled
  `retrospective` block (own counts, headline and strata).

**Deterministic artifact (`export`)**
- `evaluation.json` contains the forecast/resolution versions visible at
  `as_of`, the evaluation, `scoring_version`, schema/code versions and
  provenance metadata; canonical UTF-8 JSON (sorted keys) hashed with SHA256.
  Prospective forecasts and `retrospective_fixture` rows live in separate,
  explicitly labeled lists (`forecasts` / `retrospective_fixtures`).
  No wall-clock report timestamp: writes after `as_of` cannot change the hash,
  and no live whole-DB fingerprint is included.

**Snapshot provenance**
- The registry stores the TKG snapshot manifest identity (`snapshot_sha256`)
  plus a verification flag. A bare hash is **declared provenance** — hash
  length proves nothing cryptographically. If a local `snapshot.json` path is
  supplied at registration, the hash is recomputed with the existing
  `medradar.tkg` APIs and a mismatch is a hard error (`verified_local`).

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

## Limitations

- Single writer per store file; no multi-writer coordination.
- No tamper-proof guarantees against whoever controls the SQLite file.
- `declared` snapshot hashes are caller assertions, not validation.
- Outcomes are binary only; multi-class / continuous targets are future work.
