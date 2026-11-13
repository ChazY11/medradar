# Evidence Core v1 — append-only revision ledger behind `events` (ADR-001 option C)

- **Task:** REFOUNDATION-002 Phase 2 / `task-16` — implement option C as working, tested code.
- **Branch:** `feature/evidence-core-v1`, based on `origin/main` `b2a14c0` (not pushed; main untouched).
- **Deliverables:** `medradar/evidence_core/{__init__,migrations,ledger}.py`, modified `medradar/db.py` (`DB.upsert_events`, `DB.__init__`), `tests/test_evidence_core.py`, `tests/test_event_revision.py`, this document, and `_evidence/evidence_core/{run_evidence.py,evidence_core.json}`.
- **Labels:** `[FACT]` measured/implemented; `[INFERENCE]` conclusion; `[LIMITATION]` explicit non-guarantee.

**One-line result.** Every write through `DB.upsert_events` now produces exactly one immutable revision per **content change** and none for an identical re-import, with `first_seen_at` monotonic; the three ledger triggers reject `UPDATE`/`DELETE`/re-submit; the 1,074-test baseline stays green (**1,099 passed / 3 skipped / 224 subtests** with 28 new tests); the production database was only read (SHA-256 unchanged).

---

## 1. What is guaranteed, and what is not

| Guarantee | Mechanism | Evidence |
|---|---|---|
| One immutable revision per content change of an event | `DB.upsert_events` append inside the same transaction as the head write | `tests/test_event_revision.py::RevisionWritePathTests` |
| Identical re-import is idempotent (no revision) and `first_seen_at` is preserved | content hash excludes volatile fields; MIN update on head only | same file, `test_identical_reimport_adds_no_revision_and_preserves_first_seen` |
| `first_seen_at` never moves later | `_min_first_seen` (lexicographic MIN over ISO date/datetime) | `test_earlier_first_seen_moves_head_only_never_creates_revision` |
| Old values are recoverable after an overwrite | full snapshot JSON + `content_hash` per revision | `test_changed_import_appends_revision_keeping_old_values` |
| `event_revision` rows cannot be updated, deleted or replaced via SQL | `BEFORE UPDATE` / `BEFORE DELETE` / resubmit-guard triggers, `RAISE(ABORT)` | `ImmutabilityTriggerTests` (incl. `recursive_triggers=ON/OFF`) |
| Batch atomicity | one `BEGIN IMMEDIATE` transaction covers head rows + revisions | `test_batch_is_one_transaction_and_rolls_back_on_failure` |
| Migrations are idempotent, transactional, checksummed | `schema_version` + `migrations.ensure_schema` | `tests/test_evidence_core.py::MigrationRunnerTests` |
| Existing readers are unaffected | no query path changed; `events` schema is only **extended** (one index) | `test_old_queries_return_the_same_rows_after_migration`; full suite green |
| Legacy rows get an honest baseline, not fake history | one `origin='legacy_baseline'`, `history_completeness='baseline_only'` revision per event | `LegacyBaselineTests`; full-copy drill below |

`[LIMITATION]` **This is not tamper-proofing.** The `events` head table remains a normal mutable table; a database owner can `INSERT OR REPLACE`, update it directly, drop triggers/tables, or replace the file. The ledger records the **application write path**, and `reconcile()` detects head-row mutation — it cannot detect a forged file. The full matrix is §5.

---

## 2. Schema

`schema_version` (application schema ledger, **not** SQLite's internal `PRAGMA schema_version` cookie):

| column | meaning |
|---|---|
| `version` INTEGER PK | migration number, 1..N |
| `name` TEXT | stable migration name |
| `checksum` TEXT | sha256 of the migration text (or stable identity for the Python data migration) |
| `applied_at` TEXT | UTC moment the migration committed |

`event_revision` (append-only; `PRIMARY KEY (event_id, version)`):

| column | meaning |
|---|---|
| `event_id`, `version` | revision identity; PK + resubmit guard make duplicates abort |
| `snapshot` TEXT | canonical JSON of the **full** `events` row at that revision (all 19 columns) |
| `content_hash` TEXT | sha256 over the **content fields only** — `snapshot` minus `first_seen_at`, `fetched_at`, `as_of` (volatile; otherwise a retry would look like a change) |
| `prev_content_hash` TEXT | previous revision's content hash (NULL for v1); forms an audit chain |
| `revision_reason` TEXT | `insert` / `update` / `adopted_existing_row` / `legacy baseline: …` |
| `source` TEXT | `events.source` at that revision |
| `origin` TEXT | `live` or `legacy_baseline` (CHECK) |
| `history_completeness` TEXT | `complete` (created after ledger) / `partial_before_ledger` (live revision of a pre-ledger event) / `baseline_only` (the single legacy snapshot) — CHECK |
| `recorded_at` TEXT | UTC moment **this revision was recorded** (never back-dated) |
| `first_seen_at` TEXT | MIN first-seen known at this revision |
| `available_at`, `timestamp_quality` | public clock / quality as stored at this revision |

Indexes: `idx_event_revision_recorded_at(recorded_at)`, `idx_event_revision_source(source)`, plus the required `idx_events_available_at(available_at)`.
Triggers: `event_revision_no_update`, `event_revision_no_delete`, `event_revision_no_resubmit` (`RAISE(ABORT, …)`).

`[FACT]` `MIGRATIONS` = v1 (`evidence_core_init`: table + indexes + triggers + events index) and v2 (`legacy_baseline_seed`: Python data migration because SQLite has no `sha256`).

---

## 3. Migration runner (`medradar/evidence_core/migrations.py`)

- `ensure_schema(conn)` — bootstrap `schema_version`, verify applied checksums, apply pending migrations.
- Each migration runs in its own transaction (`BEGIN IMMEDIATE`, or `SAVEPOINT` if the caller already opened one); failure rolls back the whole migration and records nothing.
- **Checksum discipline:** an applied migration whose text/identity changed is a hard `RuntimeError` — editing history is an error, not a silent divergence. Unknown applied versions are also refused.
- **Idempotent / re-runnable:** second call = `applied_now: []`. Called from `DB.__init__` after the legacy forward-migration, so every open is safe; measured re-open cost on the migrated 1.37 GB DB = **0.003 s** (only the `MAX(version)` probe).
- **Guards repair:** `verify_guards()` reports present/missing triggers; `reinstall_guards()` recreates dropped triggers (documented as *not* repairing forged rows).
- `[LIMITATION]` The runner does **not** create a backup automatically. The prescribed drill is: copy the file (or SQLite backup API) → migrate → verify; backup/restore is tested in `BackupRestoreDrillTests` and the full-copy drill (§6).

### Legacy baseline seeding (migration 2)

For every existing event with **no** revision: one row with `version=1`, `origin='legacy_baseline'`, `history_completeness='baseline_only'`, `revision_reason='legacy baseline: one snapshot at migration time; pre-ledger history unavailable'`, `recorded_at` = migration moment. Rows that already have a revision are skipped, so a re-run cannot duplicate. The snapshot is the post-forward-migration row (columns added by `_migrate` are included as they actually are; nothing is invented).

`[FACT]` Full production copy: **375,378 events → exactly 375,378 baseline revisions**, all `legacy_baseline`/`baseline_only`, version 1, in **68.655 s**; the legacy forward-migration fills the new timing columns from existing values, and because `ALTER TABLE … ADD COLUMN … DEFAULT 'date'` fills pre-existing rows, `timestamp_quality` lands as `'date'` (not the `'estimated'` COALESCE branch). This is recorded rather than “corrected”.

---

## 4. Write path (`DB.upsert_events`)

Normalisation is byte-for-byte the pre-ledger logic (same `iso`/`iso_moment`/quality inference) extracted into `DB._normalise_event`, then per row:

| Head state | Condition | Head write | Revision |
|---|---|---|---|
| absent | — | `INSERT OR REPLACE` (insert) | v1, `origin='live'`, `complete`, reason `insert` |
| present | latest hash **==** new hash | none, except `first_seen_at = MIN(old, new)` (maintenance-only) | **none** (idempotent) |
| present | latest hash **!=** new hash | `INSERT OR REPLACE` with new values, `first_seen_at=MIN` | vN, reason `update`, `prev_content_hash` set, `complete` or `partial_before_ledger` |
| present, no revision (defensive) | migrations bypassed | replace | v1 `adopted_existing_row`, `partial_before_ledger` |

- One `BEGIN IMMEDIATE` transaction per batch; `first_seen_at` on the head is the only non-revision field that may move, and only **earlier**.
- `DB.event_history(event_id)`, `DB.event_revision_count(...)`, `DB.reconcile_ledger()` are new read-only helpers.
- `[FACT]` Compatibility: full suite **1,099 passed, 3 skipped, 224 subtests**; old 1,071 tests unchanged and green; no existing test modified.

`[INFERENCE]` Cost: the write path adds one indexed point query + one INSERT per changed row; identical re-imports add a hash computation only. The migration cost is linear and was measured at 68.7 s for 375k rows (including trigger/index maintenance).

---

## 5. Bypass matrix — what the ledger catches, detects, and cannot catch

Measured by `_evidence/evidence_core/run_evidence.py` (`bypass_matrix`, 10 cases) on a scratch DB; exact rejected messages come from the triggers.

| # | Bypass | Ledger catches? | Detectable? | Mechanism / observation |
|---|---|---|---|---|
| 1 | `INSERT OR REPLACE` on `events` (the pre-ledger write path) | **No** | **Yes** | REPLACE rewrites the head row with no trigger on `events`; `reconcile()` reports `head_mismatch_count=1` (head hash ≠ latest revision hash) |
| 2 | Direct `UPDATE events …` | **No** | **Yes** | same; `reconcile()` `head_mismatch_count` |
| 3 | Direct `DELETE FROM events` | **No** | **Yes** | ledger row survives as an orphan; `reconcile()` `orphan_revision_count=1` |
| 4 | `UPDATE event_revision` | **Yes** | Yes | `sqlite3.IntegrityError: event_revision is append-only: UPDATE rejected` |
| 5 | `DELETE FROM event_revision` | **Yes** | Yes | `…: DELETE rejected` |
| 6 | `INSERT OR REPLACE INTO event_revision …` | **Yes** | Yes | BEFORE INSERT resubmit guard: `…: revision already recorded` |
| 7 | Same update with `PRAGMA recursive_triggers=ON` | **Yes** | Yes | triggers fire exactly the same with recursive_triggers ON or OFF |
| 8 | `DROP TRIGGER` then `UPDATE event_revision` | **No** | **No** | forge succeeds; `verify_guards()` flags the missing guard; `reinstall_guards()` restores future protection but the forged row remains and `reconcile()` cannot see it (hash fields untouched) |
| 9 | `DROP TABLE event_revision` | **No** | **No** at DB level | `reconcile()` errors because the ledger is gone |
| 10 | Whole-file replacement / `VACUUM INTO` swap | **No** | **No** | the next process opens a self-consistent, different history; only an external hash/anchor (e.g. published `evidence_core` file digest) can detect it |

`[LIMITATION]` Not covered by design and not claimed: a privileged actor editing the SQLite file bytes, re-enabling `PRAGMA writable_schema` to drop trigger rows, or restoring an older backup. The ledger is **tamper-evident only for head-row mutations through SQL**, and only if `reconcile()` is run and its result is anchored somewhere the attacker does not control.

`[INFERENCE]` The practical threat model is: a *bug or legacy code path* using `INSERT OR REPLACE` bypasses the ledger silently (cases 1–3, detectable later); an *operator/admin* can forge anything (cases 8–10, not detectable inside the same file). This matches ADR-001 option C's stated boundary and makes no stronger claim.

---

## 6. Verification evidence (`_evidence/evidence_core/evidence_core.json`)

**Full suite** (repo, Python 3.12.10, offline):
`python -m pytest -q -o addopts=""` → **1,099 passed, 3 skipped, 224 subtests passed in 26.71 s**. New tests: 28 (`test_event_revision.py` 18, `test_evidence_core.py` 10). Baseline was 1,071 passed / 3 skipped before this change; no baseline test was edited.

**Production database integrity** `[FACT]`:

| Check | Value |
|---|---|
| path | a read-only copy of the production DB, outside the repository (`<BACKUP_DB>`) |
| SHA-256 before / after | `445807cab60df66e0f0853c973aaf0dae6065e72b6c9807d5dd5265097002c92` / identical |
| bytes / mtime | `1,368,469,504 B` / unchanged (never opened read-write; only copied) |

**Full-copy migration drill** on a copy of that backup `[FACT]`:

| Metric | Result |
|---|---|
| copy | 1,368,469,504 B in 0.769 s; copy SHA-256 == source |
| `DB(copy)` migration | **68.655 s**; `schema_version 0 → 2`; **375,378 baseline revisions** (all `legacy_baseline`/`baseline_only`, v1) |
| ledger counts | events 375,378; revisions 375,378; every event has exactly one v1 |
| `reconcile()` full | 16.843 s; head mismatches **0**, missing **0**, orphans **0**, `ok=true` |
| sample checks (5 events) | head `content_hash` == latest revision hash for all |
| old-query compatibility | aggregate signature (source×kind rows: count, title chars, payload chars) identical before/after migration (`equal=true`, 6 groups) |
| re-open (idempotency) | 0.003 s, `applied_now=[]`, counts unchanged, `reconcile_ok=true` |
| restore drill | pristine copy restored: SHA-256 matches, 375,378 events, ledger table absent (pre-migration state) |
| guards after migration | all 3 triggers present |

`[INFERENCE]` The 68.7 s is one-time and disk-bound (one transaction, 375k inserts, three indexes, triggers); re-opening the migrated DB is effectively free because the version probe short-circuits.

---

## 7. Test map (new tests only)

| Area | Tests |
|---|---|
| Migration runner | fresh DB `schema_version`/checksums/applied_at/guards/index; reopen no-op; checksum tamper refused; unknown future version refused |
| Legacy baseline | exactly one marked baseline per event; reopen no reseed; change-after-baseline gets `partial_before_ledger`; old query rows identical pre/post migration |
| Backup/restore | migrate → backup → corrupt → restore → counts/hashes/guards verified; file hash stable after reopen |
| Write path | v1 insert; identical re-import (no revision, first_seen preserved); earlier first_seen head-only; changed import keeps old snapshot + hash chain; deterministic hash ignoring volatile fields; batch rollback; empty batch; mixed batch |
| Immutability | UPDATE / DELETE / `INSERT OR REPLACE` on ledger rejected; `recursive_triggers` ON/OFF no effect; guards present |
| Bypass matrix | REPLACE/UPDATE/DELETE on `events` not caught but reconcile-detected; trigger drop forge + reinstall; whole-file replacement outside the model |

---

## 8. Known limitations

1. `[LIMITATION]` `events` is still mutable. `reconcile()` is a **detector**, not an enforcer; it must be run (and its output anchored) for the head bypasses to be visible.
2. `[LIMITATION]` Ledger `first_seen_at` is the value at that revision. If an earlier first-seen arrives later, only the head row moves (the immutable revision cannot be edited); the next real change carries the MIN forward. This is the price of “identical re-import creates no revision”.
3. `[LIMITATION]` Legacy baseline rows are honest snapshots, not history. `history_completeness='baseline_only'` says exactly that; no provenance before the migration exists.
4. `[LIMITATION]` Payload/content is still the collector projection (not raw source bytes — see Phase 1/E1). `content_hash` identifies *our stored content*, not the upstream record.
5. `[LIMITATION]` No automatic backup, no retention/pruning, no cross-store reconciliation (TKG/ATLAS/ledger), no external anchoring, no cryptographic signing. Append-only growth is unbounded (`event_revision` ≈ one full snapshot per content change).
6. `[LIMITATION]` Not retroactive: rows written before this change keep `baseline_only`; the PIT/public-time gaps measured in Phase 1 (E1) are unchanged by this work.
7. `[LIMITATION]` Single-writer assumption: SQLite's write lock serialises writers; concurrent processes are safe but the migration runner should not be raced by two first-time migrators (BEGIN IMMEDIATE serialises; the second sees the committed version).

---

## 9. Reproduction

```bash
# tests
python -m pytest -q -o addopts=""

# evidence (bypass matrix + production integrity + full-copy drill; ~2 min, needs ~2.8 GB temp)
python docs/refoundation/phase2/_evidence/evidence_core/run_evidence.py \
  --json-out docs/refoundation/phase2/_evidence/evidence_core/evidence_core.json

# fast: bypass matrix + production hash only, no 1.4 GB drill
python docs/refoundation/phase2/_evidence/evidence_core/run_evidence.py \
  --skip-full --json-out /tmp/evidence_core_fast.json
```

The production database is only ever read/copied; the drill operates on a temp copy and restores it as part of the test.
