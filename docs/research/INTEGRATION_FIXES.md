# INTEGRATION_FIXES — PR #2 defect-fix pass (bitemporal TKG + forecast registry)

- **Branch**: `fix/pr2-defects` on top of `1074e6d` (integration base)
- **Trigger**: independent audit `medradar-orchestration/audit2/pr2_audit.md` (F1–F5)
- **Scope**: `medradar/tkg/`, `medradar/forecast_registry.py`, the two focused test
  modules, `docs/TKG.md`, `docs/FORECAST_REGISTRY.md`, this note. No model, no
  network, no new dependencies, public API unchanged.
- **Posture**: every defect below was reproduced (red) before the fix and is
  covered by a test that fails on the pre-fix code (green after).

## F1 (CI blocker) — py3.10 rejected 1/2/4/5-digit fractional seconds

**Root cause.** `medradar/tkg/store.py::normalize_moment` and
`medradar/forecast_registry.py::normalize_moment` passed raw text to
`datetime.fromisoformat`. Python 3.10 accepts only **3 or 6** fractional digits
(3.11+ relaxed this to 1–9), so `2024-01-01T00:00:00.5Z` / `...:00.50+00:00`
raised `ValueError` on 3.10 only. `requires-python = ">=3.10"` and the CI matrix
test 3.10, so the job was red while 3.11/3.12 were green.

**Fix.** New shared helper `medradar/tkg/_time.py` (used by both modules, which
had already diverged): `normalize_fraction()` right-pads a 1–9 digit fraction to
6 digits and truncates sub-microsecond digits **before** `fromisoformat`;
`render_moment()` renders the canonical fixed-width form. Both modules keep
their own exception types/messages.

**Evidence.** New tests `test_fractional_second_digits_parse_on_python_310` in
both test modules (1/2/4/5/6 digits, `...5000009` truncation, offset
combination). Full offline suite via `uv venv -p 3.10` (CPython 3.10.20):
`Ran 563 tests ... OK (skipped=3)`, exit 0; same on 3.12.10.

## F2 — date-only inputs bypassed the fixed-width-microsecond invariant

**Root cause.** Two date-only fast paths in `tkg/store.py` returned
`YYYY-MM-DDT00:00:00Z` (second precision) instead of going through the canonical
renderer, contradicting the schema-2 promise and the function's own comment.
`'Z' > '.'`, so same-second lexical comparisons were wrong:
`valid_start=2024-02-03` was invisible at `valid_at=2024-02-03T00:00:00.5Z`, a
date-only `valid_to` was not honoured at a sub-second cutoff, the natural
`snapshot(known_at=2024-02-03T00:00Z)` call (valid_at defaults to known_at, see
`query.py:155`) hid the node, and a date-only `valid_from` plus a sub-second
`valid_to` was wrongly rejected as an empty interval. The events adapter writes
date-only `event_date` into `valid_from`, so this affected every imported row.

**Fix.** Both fast paths now render `YYYY-MM-DDT00:00:00.000000Z` (precision
still recorded as `"date"`). No other rendering path changed.

**Evidence.** New tests: `test_date_only_inputs_render_fixed_width_microseconds`,
`test_date_only_valid_from_visible_at_same_day_subsecond_cutoff`,
`test_date_only_valid_to_is_honoured_half_open`; the manifest assertion in
`test_manifest_carries_cutoffs_versions_and_provenance` was corrected to
`2021-01-01T00:00:00.000000Z`.

**Hash consequence (expected).** The fixed-vector export hash changed. The vector
now pins an explicit `code_version` (`medradar.__version__` patched inside the
test) so a package version bump cannot invalidate it again, and the expected
value is `e9822d6e…` (previous literal `f39e2581…` was recorded on the 0.2.2-era
feature branch and was already stale after the integration merge bumped
`medradar.__version__` 0.2.2 → 0.3.0). Current reproducible values (identical on
CPython 3.12.10 and 3.10.20):

| artifact | sha256 |
|---|---|
| `python -m medradar.tkg demo` early export | `9028cb26c18e673e14d9cb8c2ed76dcc0c9520e6ca470ccffe395ce0601747c5` |
| `python -m medradar.tkg demo` final export | `ddaac3f31d15625a0ab1685e5ea51c23ff5aec1621e67fb2b83157e9f6fb53b8` |
| `python -m medradar.tkg bench --n 2000` snapshot | `90602fc28226f92f32cf238c9ac12fc496978545f983973875d7c16f7d94d0f9` |
| `python -m medradar.forecast_registry demo` artifact | `b445d85a717579f3d30d96af54ffdb58e294dca78c1c1c3507218c15d52f704c` |

The TKG demo/bench values moved for two honest reasons: the manifest carries
`code_version` (0.2.2 → 0.3.0 on integration) and date-only `valid_from` rows now
render `.000000Z`. So the byte values quoted in the historical foundation
reports (`FOUNDATION_ACCEPTANCE.md`, `FOUNDATION_WHEEL_SMOKE.txt`,
`tkg_bench_synthetic.json`, `TKG_HARDENING_REPORT.md`) no longer reproduce as-is;
that is the documented "hash changes with schema/adapter/code version" design,
not a regression. Use the values above for current verification.

## F3 — `INSERT OR REPLACE` could still delete a forecast via a reused idempotency key

**Root cause.** The only REPLACE guard was `forecasts_no_replace`, keyed on
`NEW.prediction_id`. A raw `INSERT OR REPLACE` with a **new** `prediction_id` and
an existing `idempotency_key` did not fire it; SQLite resolved the UNIQUE
conflict by deleting the old unresolved row below the DELETE-trigger layer. The
`forecast_idempotency` ledger had no guards at all, so a raw REPLACE could
rebind the key → prediction_id mapping (a later legitimate retry then raised
`IdempotencyConflict`).

**Fix (schema, applied on every open via `CREATE TRIGGER IF NOT EXISTS`).**
`forecasts_no_key_rebind` (`BEFORE INSERT`, existing `idempotency_key` mapped to
a different `prediction_id` → ABORT); `forecast_idempotency_no_update`,
`forecast_idempotency_no_delete`, `forecast_idempotency_no_resubmit`. Existing
database files gain the triggers when reopened. Boundary now documented: this
stops rewrites/deletes, **not** owner-level forged appends.

**Evidence.** `test_insert_or_replace_with_reused_idempotency_key_is_rejected`,
`test_idempotency_ledger_cannot_be_rebound_deleted_or_replaced`,
`test_existing_database_gets_new_guards_when_reopened`.

## F4 — `retrospective_fixture` could not hold a prior backtest

**Root cause.** Docs say `record_kind="retrospective_fixture"` is for prior
backtests, but `_finalize_window` required a genuinely future window and the
`forecasts` table carried `CHECK (window_start >= generated_at)`; a prior
backtest (e.g. a 2020 window registered in 2026) was rejected. Test fixtures
used an injected clock, hiding the gap.

**Fix.** The future-only rules in `_finalize_window` are skipped for
`record_kind="retrospective_fixture"` (window_end is still derived from the
declared horizon, non-empty window still enforced), and the table CHECK became
`window_start >= generated_at OR record_kind = 'retrospective_fixture'`.
Fixtures remain excluded from the prospective headline/denominators (unchanged
evaluation logic). No schema migration is performed: the relaxed CHECK is part of
the fresh schema; a pre-release file created by an older dev build must be
recreated (no released DBs exist). Documented in `docs/FORECAST_REGISTRY.md`.

**Evidence.** `test_retrospective_fixture_may_hold_historical_prior_backtest_window`
(historical fixture accepted, prospective historical still rejected, headline
count 0, `retrospective` cohort/artifact list has 1).

## F5 — documentation honesty corrections

- `docs/TKG.md`: removed the stale hardcoded test counts (`482`, `46`);
  confirmed resubmit guards protect **rewrites/deletes, not forged appends**;
  the fixed-width promise now states that date-only input has no second-precision
  shortcut and that 1–9 digit fractions normalize identically on Python 3.10+.
- `docs/FORECAST_REGISTRY.md`: REPLACE claim now states exactly which guards
  exist (PK, idempotency-key rebind, ledger) and what is **not** protected
  (owner-level tamper, forged appends); retrospective-fixture historical-window
  behaviour documented.
- `medradar/tkg/export.py` docstring: `valid_at=None` defaults to `known_at`
  (`query.py:155`), it does not disable the valid-time filter.

## Verification (commands actually run)

```bash
# py3.12
python -m medradar selftest                    # Ran 563 tests, OK (skipped=3), exit 0

# py3.10 (CI shape)
uv venv -p 3.10 .audit/py310
uv pip install --python .audit/py310/Scripts/python.exe .
.audit/py310/Scripts/python.exe -m medradar selftest   # Ran 563 tests, OK (skipped=3), exit 0

# demos (offline, synthetic)
python -m medradar.tkg demo --out-dir .audit/demo312
python -m medradar.tkg bench --n 2000 --out-dir .audit/bench312
python -m medradar.forecast_registry demo      # exit 0
```

## Residual risk

- Raw SQL with DB-owner rights can still drop triggers, rebuild the file, or
  **append** plausible forged rows; only rewrites/deletes are physically blocked
  (documented, not a regression).
- Registry stores created by earlier pre-release dev builds are not migrated in
  place (relaxed window CHECK); recreate them. F3 triggers are added on open.
- Multi-process concurrent writes still rely on external serialisation
  (single-writer assumption, unchanged).
