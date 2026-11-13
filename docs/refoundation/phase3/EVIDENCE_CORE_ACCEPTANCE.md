# Evidence Core v1 — production acceptance (independent verification)

- **Task:** REFOUNDATION-003 / `task-18` — independent production-grade acceptance of Evidence Core v1 (ADR-001 option C), not a re-run of the author's drill.
- **Branch:** `acceptance/evidence-core-v1` @ `f088e37` (`feature/evidence-core-v1`), based on `origin/main` `b2a14c0`. Not pushed; `main` untouched.
- **Original database:** `<BACKUP_DB>` — read/copied only.
  - SHA-256 before **and** after acceptance: `445807cab60df66e0f0853c973aaf0dae6065e72b6c9807d5dd5265097002c92` (1,368,469,504 B; mtime identical).
  - Fresh copy was created **before** any migration and verified byte-identical; all migrations/writes/mutations/restores happened on copies that were removed afterwards.
- **Harness:** [`_evidence/core_acceptance/run_acceptance.py`](_evidence/core_acceptance/run_acceptance.py) → [`acceptance.json`](_evidence/core_acceptance/acceptance.json).
- **Environment:** Python 3.12.10, SQLite 3.49.1, Windows; run 2026-11-12T19:5xZ (UTC).

## Verdict

**PASS — 37 / 37 acceptance items pass, with 2 findings (1 LOW robustness issue, 1 informational capacity cost).** Six author claims were re-measured; none is contradicted, four are exact, two timing claims differ within environment noise/direction (details §4).

---

## 1. PASS/FAIL table (all 37 items)

### 1. Original integrity / fresh copy

| # | Item | Result | Measured |
|---|---|---|---|
| 0.1 | Original DB byte-identical after acceptance | **PASS** | SHA-256 and mtime unchanged; `445807ca…2c92`, 1,368,469,504 B |
| 1.1 | Fresh copy byte-identical to original before migration | **PASS** | copy 0.601 s, hash equal, 1,368,469,504 B |
| 1.5 | Event count unchanged by migration | **PASS** | 375,378 |
| 1.6 | One baseline revision per event | **PASS** | 375,378 |

### 2. Migration / schema_version

| # | Item | Result | Measured |
|---|---|---|---|
| 1.2 | Exactly two versions, in order | **PASS** | `schema_version` → `[1, 2]`; version after = 2 |
| 1.3 | Stored checksums equal code checksums (sha256, 64 hex) | **PASS** | `v1 bc477359c7059fc7…`, `v2` identity checksum match |
| 1.4 | `applied_at` parseable, not back-dated | **PASS** | after 2026-01-01 |
| 1.7 | `available_at` index created | **PASS** | `idx_events_available_at` present |
| 1.8 | All three guards present | **PASS** | no-update / no-delete / no-resubmit |
| 2.1 | Second open applies nothing | **PASS** | `applied_now=[]`, version 2, 0.001 s |
| 2.2 | Second open leaves data unchanged | **PASS** | events 375,378; revisions 375,378; 2 version rows |
| 2.3 | Tampered checksum refused | **PASS** | `RuntimeError: migration 1 (evidence_core_init) checksum mismatch: applied=0000… expected=bc477359c7059fc7…; editing an applied migration is an error`; restored → clean no-op |
| 2.4 | Unknown applied version refused | **PASS** | `RuntimeError: schema_version records unknown migration 99 (future); this build cannot safely continue` |

### 3. Ledger consistency (full 375,378-event database)

| # | Item | Result | Measured |
|---|---|---|---|
| 3.1 | Every event has ≥1 revision | **PASS** | 0 events without revision |
| 3.2 | Exactly one current revision per event, no version gaps | **PASS** | `version_gaps=0`, `duplicate_pk=0`, `missing_latest=0`, `MIN=MAX=1` after clean migration |
| 3.3 | No orphan revisions | **PASS** | 0 |
| 3.4 | All `legacy_baseline` / `baseline_only` | **PASS** | 375,378 / 375,378 |
| 3.5 | Only version 1 after clean migration | **PASS** | `(min,max)=(1,1)` |
| 3.6 | `reconcile()` zero mismatches | **PASS** | head mismatches 0, missing 0, orphans 0, `ok=true` (18.236 s) |
| 3.7 | No fabricated observation time | **PASS** | baseline `recorded_at` single distinct value `2026-11-12T19:52:52.034779Z`; **0** revisions recorded before 2026 |
| 3.8 | `first_seen_at` preserved from pre-ledger rows | **PASS** | 0 mismatches vs both the revision column and `snapshot.first_seen_at` |

### 4. History retention / idempotency

| # | Item | Result | Measured |
|---|---|---|---|
| 4.1 | Change appends revision; old value retrievable; hash chain; second identical write adds nothing; earlier first-seen head-only | **PASS** | 3 sampled events: v1→v2 (`update`), old title retrievable in v1 snapshot, `prev_content_hash` links, identical rewrite → still 2 versions, later first-seen ignored, earlier first-seen → head `2000-01-01`, versions stay 2 |

### 5. Detection after direct SQL (documented boundary)

| # | Item | Result | Measured |
|---|---|---|---|
| 5.1 | Raw `UPDATE events` detected | **PASS** | `reconcile().head_mismatch_count=1` |
| 5.2 | Raw `DELETE FROM events` detected | **PASS** | `orphan_revision_count=1`, `ok=false` |
| 5.3 | `INSERT OR REPLACE INTO events` detected | **PASS** | `head_mismatch_count=1` |
| 5.4 | Ledger `UPDATE`/`DELETE`/`REPLACE` rejected | **PASS** | exact aborts: `UPDATE rejected`, `DELETE rejected`, `revision already recorded` |
| 5.5 | Dropped trigger is **not** caught (as documented) | **PASS** | forge succeeds (`revision_reason='forged'`), guards missing, `reconcile()` still `ok=true`; transaction rollback restored trigger and row |
| 5.6 | Rollbacks restore revision count | **PASS** | 375,381 before/after mutation sandbox (3 history revisions only) |

### 6. Transaction / migration rollback

| # | Item | Result | Measured |
|---|---|---|---|
| 6.1 | Partial batch failure rolls back head **and** revision | **PASS** | forced failure on 2nd event: counts identical (375,378 / 375,381), first row absent after rollback |
| 6.2 | Failed migration records no version/data; unpatched re-run succeeds | **PASS** | forced migration-2 failure: `schema_versions=[1]`, `event_revision` rows 0; re-run `applied_now=[2]` and 3 baseline rows |
| 6.3 | Finding: runner requires `sqlite3.Row` on the caller's connection | **PASS (finding)** | plain connection: `TypeError: tuple indices must be integers or slices, not str`; migration 1 committed ([1]), migration 2 rolled back cleanly; production `DB` path sets `row_factory=Row`, unaffected |

### 7. Reader compatibility + full suite

| # | Item | Result | Measured |
|---|---|---|---|
| 7.1 | Aggregate fingerprints identical before/after | **PASS** | source×kind, company, quality, dated-length fingerprints equal (4 queries) |
| 7.2 | 200-row sample (all 19 old columns) identical | **PASS** | tuple-for-tuple equal |
| 7.3 | Old audit predicate still 298,810 | **PASS** | SQL 298,810; `audit.legacy_timestamp_promotions()` 298,810 |
| 9.1 | Full pytest suite green | **PASS** | **1,099 passed, 3 skipped, 224 subtests** in 28.02 s (returncode 0) |

### 8. Restore drill

| # | Item | Result | Measured |
|---|---|---|---|
| 8.1 | Restored copy byte-identical to pre-migration | **PASS** | restored = pristine = original `445807ca…2c92` |
| 8.2 | True rollback removes ledger/schema_version | **PASS** | `event_revision` absent, `schema_version` absent, 375,378 events |

---

## 2. Storage growth (honest cost of append-only full snapshots)

| Metric | Value |
|---|---|
| Pre-migration file | 1,368,469,504 B (334,099 pages × 4,096) |
| Post-migration file (after WAL checkpoint) | **2,941,247,488 B** (718,078 pages) |
| Growth | **+1,572,777,984 B = +114.93 %** (≈ +1.46 GiB) |
| Revision payload (logical column bytes) | 1,121,277,740 B over 375,378 revisions (≈ 2.99 KB/revision) |
| Write-mode | each revision stores a full 19-column JSON snapshot; no compression/dedup/pruning |

`[INFERENCE]` Capacity planning should assume **~2.15× the current database size** for a one-shot baseline migration, and linear growth of roughly one snapshot per content change afterwards. This is the designed trade-off, not a defect — but it must be accepted explicitly.

---

## 3. Timings (acceptance environment; disk-bound, machine-dependent)

| Operation | This acceptance | Author's claim | Delta |
|---|---|---|---|
| Copy 1.37 GB | 0.601 s | 0.769 s | −0.17 s (faster) |
| Fresh migration (375,378 baselines) | **73.017 s** | 68.655 s | **+4.36 s (+6.3 %)** |
| `reconcile()` full DB | **18.236 s** | 16.843 s | +1.39 s (+8.3 %) |
| Re-open (idempotent no-op) | **0.001 s** | 0.003 s | −0.002 s |
| `available_at >= '2020-01-01'` count | **1,260.5 ms → 0.49 ms** | not claimed | ≈ **2,500× faster**; plan changes `SCAN events` → `SEARCH events USING COVERING INDEX idx_events_available_at` |
| Full pytest | 28.02–29.4 s | 26.71 s | +1–3 s |

`[INFERENCE]` Timing differences are within normal environment/disk variance (the migration batch is 375k inserts under one transaction and depends on I/O and antivirus); the direction and magnitude are consistent. No performance claim in the author's document is contradicted.

---

## 4. Mismatches vs author's claims

| Author's claim (Phase 2 doc) | Acceptance measurement | Verdict |
|---|---|---|
| 375,378 baseline revisions | 375,378 | **match** |
| all `legacy_baseline` / `baseline_only` | all 375,378 / 375,378 | **match** |
| migration 68.655 s | 73.017 s | **+6.3 %**, environment-bound (same order) |
| reconcile 16.843 s | 18.236 s | **+8.3 %**, environment-bound |
| reopen 0.003 s | 0.001 s | match (faster) |
| suite 1,099 passed / 3 skipped / 224 subtests | identical | **match** |
| production DB unchanged `445807ca…` | identical SHA-256, size and mtime | **match** |
| three guards present | no-update/no-delete/no-resubmit present | **match** |
| “ledger does not catch trigger-drop/file replacement” | confirmed (§5.5); additionally a forged revision’s **content hash** is unchanged, so `reconcile()` stays `ok=true` | **match (boundary reproduced)** |
| storage growth not quantified by author | **+114.93 %** | new measurement, no contradiction |

**No claim is contradicted.** The only substantive *new* finding is §5.1/6.3 below.

---

## 5. Findings

1. **[LOW] Migration runner is only callable on a connection with `sqlite3.Row`.**
   `_seed_legacy_baseline` indexes rows by name (`row["event_id"]`); `DB.__init__` sets `row_factory=Row`, so the production path is fine, but `medradar.evidence_core.ensure_schema(plain_conn)` on a plain `sqlite3.connect()` connection raises `TypeError: tuple indices must be integers or slices, not str`.
   Observed state after the failure: migration 1 committed (`schema_version=[1]`), migration 2 **rolled back** (`event_revision` 0 rows) — fail-safe, no partial data. Recommended: document the precondition or make the seed read rows positionally/defensively. Not a blocker for production use through `DB`.
2. **[INFO] +114.93 % storage growth** (1.37 GB → 2.94 GB) for the baseline snapshot; linear thereafter. Needs an explicit retention/archival decision before the next full sync.
3. **[INFO] The `available_at` index is effective** for range scans (~2,500× on this workload), confirming design item 6.
4. **[INFO] A forged revision made after dropping a trigger is invisible to `reconcile()`** when only non-content fields are touched (content hash unchanged); the guard report (`verify_guards`) is the only signal. This matches the author's stated boundary; it should be paired with an external anchor (e.g. periodic `reconcile()` output + guards snapshot published outside the DB) if tamper evidence is required.

---

## 6. Limits of this acceptance (explicit)

- The checksum in `schema_version` protects **migration identity**, not database tampering: a DB owner can edit `schema_version`, drop triggers, replace the file; the runner refuses edited migrations only when the checksum row is changed *and the runner is run*.
- No signing, no external anchoring, no WORM storage: detection of a forged file is out of scope (as documented by the author).
- Legacy baseline is a **snapshot**, not history: `history_completeness='baseline_only'` is the only honest statement for the 375,378 pre-existing rows.
- The ledger’s `first_seen_at` is per-revision; head-only monotonic MIN updates are not themselves revisioned (by design to keep identical re-import revision-free).
- No cross-store reconciliation (TKG/ATLAS/observatory), no automatic backup, no pruning/compaction, no concurrency stress beyond SQLite’s write lock; acceptance used a single process.
- Timing numbers are environment-specific; the correctness items are deterministic.

---

## 7. Reproduction

```bash
# full acceptance (migrates a fresh 1.37 GB copy in a temp workdir; ~2.5 min; needs ~5 GB free)
python docs/refoundation/phase3/_evidence/core_acceptance/run_acceptance.py \
  --workdir <WORKDIR> \
  --json-out docs/refoundation/phase3/_evidence/core_acceptance/acceptance.json

# skip the pytest subprocess
python .../run_acceptance.py --skip-pytest --json-out /tmp/acceptance_fast.json
```

The original database is never opened read-write and is re-hashed before/after; the harness returns exit code 0 only when all checks pass and the original is byte-identical.
