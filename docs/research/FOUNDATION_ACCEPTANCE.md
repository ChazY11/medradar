# FOUNDATION-INTEGRATE-007 — Integration & Adversarial Review Acceptance

Date: 2026-11-01 · Branch: `research/research-foundation-integration` · Base: `75acc2d`

## Reviewer context (explicit)

This review was performed by **Kimi Code in a fresh, independent context** — the same
model family as the original TKG (`research/tkg-mvp`) and Forecast Registry
(`research/forecast-registry`) author sessions, but a **distinct session that read
neither session's logs nor conclusions**. It is **not** a cross-model audit and makes
**no claim of independent DeepSeek verification**; the DeepSeek-side reconciliation of
the TKG increment remains open (see `docs/ATTRIBUTION.md`). Director contracts:
`kimi-forecast.txt` (FORECAST-REGISTRY-006), `kimi-hardening.txt` (TKG-HARDEN-005).

## What was integrated

| Source commit | Content | Cherry-pick |
|---|---|---|
| `b90c649` | Forecast Registry implementation + tests (FORECAST-REGISTRY-006) | `b4d0d5b` |
| `d5aa16c` | Forecast Registry docs/ADR/log (FORECAST-REGISTRY-006) | `489d496` |

Combined baseline before any new work: **521 tests collected (518 passed, 3 skipped,
12 subtests)** — matches the director's expected 521.

## Director issues — verification & resolution

### 1. Future-dated positive resolution — CONFIRMED, FIXED
`resolve()` checked the window but not the store clock: a positive outcome could record
an `event_time` after `resolved_at` (advance knowledge of future events). Fix: inside
the same transaction, a positive outcome now requires `event_time <= resolved_at`
(fixed-microsecond UTC on both sides, lexical = chronological); the failed attempt
rolls back atomically, clock-guard advance included.
Tests: `ResolutionTests::test_future_dated_positive_rejected_and_valid_resolution_still_works`
(future-dated positive fails, leaves zero resolution rows, does not consume the clock;
a later valid resolution succeeds; an event may predate its observation).

### 2. Horizon labels vs actual durations — CONFIRMED, FIXED
`_finalize_window` accepted arbitrary explicit `window_end` (even future-anchored
short windows mislabeled `horizon=24`). Fix: `window_end` is now **always**
`add_months_clamped(window_start, horizon_months)`; an explicit `window_end` is
accepted only when exactly equal to the derived end. Explicit future `window_start
>= generated_at` remains supported. Strata can no longer mix incomparable horizons.
Tests: `WindowTests::test_window_end_must_match_horizon_duration` (override
shortening/lengthening rejected, exact match accepted),
`WindowTests::test_derived_window_calendar_boundaries` (leap/monthend clamping,
far-future start keeps full 24-month duration).

### 3. Retrospective fixture contamination — CONFIRMED, FIXED
`evaluate()` mixed `record_kind='retrospective_fixture'` into headline metrics and
denominators. Fix: the default evaluation counts/scores only `record_kind='forecast'`;
fixtures are reported in a separate, explicitly labeled `retrospective` block (own
counts/headline/strata), and the export artifact stores them in a separate
`retrospective_fixtures` list. No retroactively generated "real" predictions; baseline
backtests remain a separate future task.
Tests: `EvaluationTests::test_retrospective_fixtures_never_contaminate_headline_metrics`.

### 4. Source-version provenance — CONFIRMED (documentation overclaim), FIXED
The hardening report's D4 said manifest-level `schema_version`/`adapter_version`/
`code_version` "carry" the per-assertion `source_version`. They do not — they are
code/manifest identity. Fixed honestly in `docs/research/TKG_HARDENING_REPORT.md`,
`docs/research/TKG_ADR.md`, `docs/research/TKG_ACCEPTANCE.md` (C2) and `docs/TKG.md`:
per-assertion `source_version` is **not stored** (explicit unknown, never claimed
complete); `evidence_sha256` is a **content hash**, not a source revision; a critical
source revision may be recorded by the caller in `source_locator`/`attrs` (preserved
in export) without new infrastructure. No new field was added; snapshot determinism
and cutoff stability are unchanged. No code/test change required beyond docs.

### 5. Registry guards / idempotency / tamper probes — PROBED, no new material defect
Author-suite claims were not trusted; an independent probe suite was written
(`docs/research/foundation_probe.py`, output `docs/research/FOUNDATION_INTEGRATION_LOG.txt`):
raw **separate-connection** UPDATE/DELETE/INSERT-OR-REPLACE attempts on a file-backed
registry are all rejected and `p` survives at 0.7; the historical artifact hash is
identical before/after a later correction (as-of view pins the original outcome);
known-value metrics recomputed with **Decimal arithmetic** (Brier 0.075, log loss
≈0.299001, ECE 0.25) match the implementation; snapshot-content tampering is detected
at registration; two CLI demo runs produce the identical artifact hash
`2ff5ca42…00f288`. Existing tests additionally cover idempotency under moved clocks
and correction as-of semantics. No further material issue confirmed in scope; the
legacy prices bug was explicitly left alone (out of scope).

### 6. Schema-2 behavior on preexisting schema-1 TKG — CONFIRMED, FIXED
`TKGStore.__init__` previously ran `CREATE TABLE IF NOT EXISTS` unconditionally and
never stamped or checked `meta.schema_version`, so opening a schema-1 store would
silently mix second-precision rows with microsecond schema-2 writes. Fix: fresh stores
are stamped `tkg-schema-2` at creation; opening a store whose stamp is **missing**
(schema-1 era never stamped) or **mismatched** raises `TKGError` with an actionable
message (detected version, required version, why mixing is unsafe, "no automatic
migration", "no data modified", rebuild guidance) **before any write**; the failing
connection is closed without deleting or stamping anything. Marked explicitly: no
automatic migration; a future migration task is separate.
Tests: `SchemaVersioningTests::{test_legacy_schema1_store_rejected_without_data_loss,
test_mismatched_schema_stamp_rejected, test_non_tkg_sqlite_file_rejected,
test_fresh_persistent_store_is_stamped_and_reopenable}`.

## Test evidence

- Full selftest after all fixes: `python -m pytest tests/` →
  **526 passed, 3 skipped, 12 subtests passed** (529 collected = 521 baseline + 8 new).
- Focused: `tests/test_forecast_registry.py` (43 tests) + `tests/test_tkg.py` (46 tests)
  → 89 passed.
- Probe suite: 6/6 PASS (`docs/research/FOUNDATION_INTEGRATION_LOG.txt`).

## Offline demos & install smoke (all synthetic, no network)

- `python -m medradar.forecast_registry demo` (repo and installed wheel): synthetic
  label printed, counts reproducible, artifact hash `2ff5ca42…00f288` identical across
  runs and across repo/wheel installs; `evaluation.json` byte-identical.
- `python -m medradar.tkg {demo,bench}` from an installed wheel in a non-repo cwd:
  deterministic repeat export `true`, snapshot hash `1091db6e…` matches the hardened
  fixed vector in `docs/research/TKG_HARDENING_REPORT.md`.
- Evidence: `docs/research/FOUNDATION_WHEEL_SMOKE.txt` (wheel built with
  `--no-deps --no-build-isolation`, installed to an isolated target dir, run from a
  non-repository working directory).
- These are **synthetic known-value / reproducibility results only** — no predictive
  accuracy or calibration claims are made.

## Deferred roadmap (next tasks, NOT implemented here)

1. Cross-source entity-resolution benchmark with **human** labels (AI-generated
   labels must not be presented as human ground truth).
2. Point-in-time rolling forecasting baselines (the registry foundation now supports
   registering real prospective forecasts first).
3. Legacy case raw/adjusted-price correction requires actual data recomputation
   (deliberately not touched by this task).

## Status

**PASS** — all six director issues verified; four required code fixes (+docs) with
targeted adversarial tests; full selftest green; offline CLI demos and installed-wheel
smoke reproducible. Main branch untouched; no merge/push; no production data; no
network; worktree left clean.
