# Phase 3 — unified forecasting, temporal graph, evidence-grounded research agent

Phase 3 (v0.5.0) turns the research pieces into a closed loop: one canonical forecast ledger,
a bitemporal graph over the real event history, and a deterministic research agent that answers
questions with cited evidence. Every number below is from a real run on the frozen research
database (55,090 FDA events, 43,420 SEC facts, market/publication tables); commands are in §5.

## 1. One canonical forecast registry (`medradar/forecast_registry.py`)

**Decision.** The v0.3.0 research foundation registry is the canonical ledger; the Market-to-R&D
Horizon forecaster now writes through `medradar/intelligence/forecasting/registry_adapter.py`
instead of keeping a second, mutable `horizon_forecasts` table as the system of record.

**The nowcast problem.** A quarterly-cutoff Horizon forecast targets `(cutoff, cutoff+12m]` but is
registered *after* `cutoff` — i.e. while its target window is already open. Labelling it `forecast`
is impossible under the strict future-window rule, and labelling it `retrospective_fixture` would be
dishonest (it is a genuine prospective prediction). The registry therefore gained a third immutable
record kind:

| `record_kind` | Meaning | Window rule |
|---|---|---|
| `forecast` | registered before the window opens | `window_start >= generated_at`, `window_end > generated_at` |
| `nowcast` | registered while the window is open (the Horizon case) | explicit `window_start <= generated_at < window_end`; a closed window is rejected |
| `retrospective_fixture` | historical backtest record, never scored prospectively | any valid window, excluded from the prospective headline |

Cohorts stay separate: `evaluate()` keeps the pure-future headline, reports the nowcast cohort and a
descriptive prospective union explicitly, and adds a `record_kind_breakdown`; the artifact lists the
three kinds separately. Nowcasts are append-only and scored only when their window has matured and
source coverage passes it.

**Adapter contract.** A Horizon record maps to a canonical spec with a stable
`idempotency_key = horizon:<forecast_id>:<model_version>`, `record_kind="nowcast"`,
`target.type="company_track"`, `p = predicted_probability`, model/feature versions, information
cutoff, window start, and evidence provenance (a locator, the SHA-256 of the canonical provenance
payload, and the observed/source kind). Exact retries are idempotent; reusing a key with a different
probability raises `IdempotencyConflict` (never a silent overwrite). `verify_registered_forecasts`
resolves matured records from the real event table using the material 510(k)/PMA rule and refuses to
resolve from incomplete coverage.

**Real run (data/research.sqlite, `--coverage-end 2026-10-15 --offline`):**

- 25 Horizon records → **25 nowcasts registered**, 0 rejected, 0 verified / 25 pending (windows end
  2027-10-01 > coverage end), calibration status `insufficient_matured_forecasts`.
- Probabilities are bit-identical to the frozen Horizon run (no new model, no retro-fitting).
- Second run: `registered=0, idempotent=25`, same `run_id`, same registry contents and artifact hash
  → the cycle is idempotent.
- Example registry ids: `sha256:e2b0750039217d4e3edd7578d36caa30fd5fa6e695305a95c48797eeb0f9050a`
  (siemens_healthineers/imaging_mr_ct), `sha256:c3b6df5283ea9e1cdab833d332134a70b18dab13f1d2e453f9fbc464a2d4e4c5`
  (intuitive_surgical/surgical_robotics).
- Cycle log committed at `experiments/reverse_rd_v2/forecast_cycle_report.json`; the registry
  database itself is gitignored (`data/`).

**Continuous schedule.** `scripts/forecast_cycle.py` is the unit of a cycle (load examples → train
the frozen model → score the current quarter → register nowcasts → verify matured → export the
deterministic artifact + cycle log). `.github/workflows/forecast-cycle.yml` commits a weekly schedule
plus `workflow_dispatch`. **Honest status:** the workflow is committed but was not executed in this
environment, so no green GitHub run is claimed; the registry has zero matured forecasts, so no
calibration claim is made yet.

## 2. Bitemporal graph over the real event history (`medradar/tkg`)

The Phase 0 TKG store is now fed from the real `events` table through the existing read-only adapter
(`scripts/tkg_import_research.py`), and `medradar/intelligence/graph_context.py` exposes read-only
pair context/timeline/counts under independent `known_at`/`valid_at` cutoffs.

**Real run (55,090 events, data/research.sqlite 289,443,840 B):**

- Import: **171,800 assertions** created in 32.59 s (112,128 intra-batch duplicates from multi-track
  events); 0 skipped rows; source file SHA-256 unchanged before/after (opened `mode=ro`).
- Store: **57,381 nodes** (55,090 event · 2,202 product_code · 51 company · 38 track) and
  **114,419 edges** (event_has_code 54,967 · event_in_track 37,782 · company_event 21,670). No
  inferred investment edges are created.
- PIT snapshot `known_at=2026-12-31` → 57,381/114,419, SHA-256
  `b60c8360656d15def5f7a81115ab069e48fb21281ac8d51167667c226c3010f3`; re-export identical.
- **Idempotent re-import:** created 0, no store growth; whole-script re-run on the reopened store
  reproduces the identical snapshot hash.
- **Knowledge-time gate:** `known_at=2026-01-01` → 0 nodes / 0 edges (all rows were backfilled on
  2026-11-02, so the import observation time is the knowledge clock). This demonstrates the gate, not
  historical publication availability; the adapter's honest caveat is recorded in
  `docs/TKG_INTEGRATION.md`.
- Read-only graph context on the real pair `medtronic` × `cardiac_rhythm`: 2,663 events, 14 products,
  7,989 edges in 0.50 s; store file hash unchanged.
- Report committed at `experiments/reverse_rd_v2/tkg_import_report.json`. Known bottleneck: the
  tkg-schema-2 store has no `idempotency_key` index, so duplicate lookups are O(n²) (10k rows
  50.7 s vs 4.2 s with operational indexes; the script adds indexes to the target store only, without
  changing exported content).

## 3. Evidence-grounded research agent (`medradar/research_agent.py`)

A deterministic multi-step workflow — **not** a chatbot and not an LLM probability generator:

`question template → plan → tool calls → evidence table → conflict detection → labelled hypothesis →
counter-evidence → statistical validation → cited synthesis → uncertainty → research log → stop/failure condition`.

Eight read-only point-in-time tools: canonical `forecast_evidence`, `event_history`,
`financial_context`, `market_context`, `publication_context`, `graph_context` (soft-optional TKG),
`counter_evidence` (track-wide activity, company activity elsewhere, SPY/XBI regime, peer financial
trend), `baseline_comparison` (purged per-pair base rate vs model/registry p). Five templates:
`entry_forecast`, `market_leading_indicator`, `early_signal`, `strategic_shift`,
`cross_source_validation`. Five deterministic conflict rules flag cases such as a high model
probability against a low historical base rate, or market-positive against financial/event-negative
evidence. Every factual claim carries a citation id that was re-queried at generation time; missing
data is reported as `null`/`unavailable`, never invented. There is no LLM path in the default
workflow.

**Real demo** (`experiments/reverse_rd_v2/agent_demo.json`, as-of 2026-11-02, with the canonical
registry and TKG present): 5 questions, **55 claims, 224 unique cited ids, 314 citation checks, 0
missing**, 3 genuine cross-source conflicts, citation kinds include `registry_forecast` and event
ids. The earlier registry/TKG-absent run is superseded; the agent explicitly reports degraded mode
when a source is missing rather than substituting a guess.

## 4. Boundaries that must not be blurred

- Nowcasts are **not** pre-registered future forecasts; they are kept in a separate cohort and are
  never merged into the pure-future headline.
- The registry has no matured forecast yet, so calibration/Brier/ECE claims are `insufficient_data`,
  not "good".
- TKG knowledge time for the current import is the backfill observation time; it cannot support
  "what the system knew in 2020" claims for these rows. Public/available timestamps are preserved as
  provenance metadata, but most are date-level and timezone-naive (55,090 dropped from `public_time`
  with an explicit counter).
- The research agent narrates stored evidence. It does not establish causality, does not predict
  stock returns, and does not replace the statistical experiments; conflict rules are heuristics.
- Patents (no API key) and hiring signals (no stable legal source) are absent from every tool and are
  reported as evidence gaps.

## 5. Reproduce

```bash
pip install -e '.[dev,bulk]'

# 0) research database (see docs/PHASE2.md §Reproduce for the 6-minute collection); then:
python experiments/reverse_rd_v2/run_v2.py --db data/research.sqlite --holdouts 3

# 1) canonical registry + continuous cycle (idempotent; run twice to check)
python scripts/forecast_cycle.py --db data/research.sqlite --registry data/registry.sqlite \
  --out out/forecast_cycle --horizon 12 --top-n 25 --coverage-end 2026-10-15 --offline

# 2) bitemporal graph over the real events + PIT snapshot report
python scripts/tkg_import_research.py --db data/research.sqlite --tkg data/tkg.sqlite \
  --known-at 2026-12-31T00:00:00Z --report-out experiments/reverse_rd_v2/tkg_import_report.json

# 3) research agent (single question, cited JSON/markdown; then the frozen demo)
python -m medradar.research_agent ask --company medtronic --track spine \
  --template market_leading_indicator --as-of 2026-11-02 \
  --db data/research.sqlite --registry data/registry.sqlite --tkg data/tkg.sqlite
python scripts/run_agent_demo.py --db data/research.sqlite --registry data/registry.sqlite \
  --tkg data/tkg.sqlite --out experiments/reverse_rd_v2/agent_demo.json --as-of 2026-11-02

# 4) behavioural acceptance
python verifier/v1/verify.py
```

The `.sqlite` stores and all raw data stay gitignored; the committed artefacts are the small
JSON/Markdown reports, the tests, and the code.
