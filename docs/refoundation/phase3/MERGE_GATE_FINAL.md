# MERGE GATE FINAL — REFOUNDATION-003

**Candidate:** `integration/ref003` → **PR #38** (Draft)
**Validated tree commit:** `34b3548` (`chore(state): record final merged test measurement and README counts`)
**This report's commit:** the tip that adds this file (docs-only; see §2)
**Base:** `origin/main` = `b2a14c0` (unchanged)
**Decision:** **GO** — with the conditions in §7. No merge, release, protection change, or branch deletion has been performed by the agent.

---

## 1. Fixes and evidence

### 1.1 Task 1 — flaky `test_generated_at_is_the_ref_commit_time` (root cause, no retry/skip)

**Root cause (reproduced):** the test copied the **live** repo-root `PROJECT_STATE.yaml` / `pyproject.toml`
into its temp repo and **ignored the subprocess return code**. Under concurrent work, the copied
fixture could change, and a failed bump surfaced as a misleading `generated_at` string mismatch.
A second, independent reproduction showed the same class of defect elsewhere: during the flake
loop, `test_check_licence::test_current_repository_is_clean` failed because a worker wrote
untracked evidence files into the worktree while the suite ran — the tests depended on mutable
working-tree state, not on committed state.

**Fix (on `governance/state-scheme`, merged):**
- committed static fixtures `tests/governance/fixtures/state_schema_v2.yaml` and `pyproject_fixture.toml`;
  `_seed()` no longer reads the live repo.
- every `_bump()` call now asserts `returncode == 0` (with stdout/stderr on failure).
- timestamp comparison is on the **instant** (epoch seconds), not on formatted strings.
- evidence files now live outside git worktrees during audits.

**Proof:** `_evidence/state_scheme/03_30_run_flake_log.txt` and the Lead's independent loop:
**30/30 passes** (0 failures) on the final tree.

### 1.2 Task 2 — main-branch state self-reference (five concepts, merge-safe)

`PROJECT_STATE.yaml` is now schema **v2** with five distinct concepts:

| Concept | Field | Validation |
|---|---|---|
| Git observed HEAD | `git.head` (+date/subject/counts) | stale-but-**ancestor** of `origin/main` = **WARN**; non-ancestor = **FAIL** |
| Last verified baseline | `verified.commit` | must be ancestor of `origin/main` |
| Release | `release.version` / `release.commit` (nullable) | version matches `pyproject.toml` at `git.head`; commit must be ancestor |
| Data snapshot | `data_snapshot` (unchanged) | existing checks |
| Tested commit | `tests.tested_head` (+artifact) | must be same-lineage; lag/ahead = **WARN**, unrelated = **FAIL**; state/artifact must agree |

`bump_state.py` refreshes `git.*` + `verified.*` deterministically (ref commit time, no wall clock)
and regenerates views. **A merge no longer creates a permanently failing gate.** Recorded as
`RC-0003` / `GOV-0003`.

**Three consecutive simulated merges** (`_evidence/state_scheme/02_three_merge_simulation.txt`):

| Round | Simulated merge commit | Gates WITHOUT bump | Bump | State tracks head | Gates AFTER bump |
|---|---|---|---|---|---|
| 1 | `1ed43b2e14a9` | six gates **PASS** + staleness WARN | updated (1238 files) | `git.head = verified.commit = 1ed43b2` | PASS, no staleness |
| 2 | `91cd144e050a` | six gates **PASS** + WARN | updated (1239 files) | `91cd144` | PASS |
| 3 | `12a1c9a52289` | six gates **PASS** + WARN | updated (1240 files) | `12a1c9a` | PASS |

### 1.3 Task 4 — README scientific consistency (5 blocking findings fixed)

| ID | Fix |
|---|---|
| F1 | Open-PR counts updated to live **28 open / 27 draft / 10 merged** in the state and regenerated block |
| F2 | Version ambiguity removed: package stays **0.5.0**; release candidate is a post-merge bump to **0.6.0-rc1**, stated consistently in `PHASE3_ACCEPTANCE` |
| F3 | `pyproject.toml` description now states the research mission (removed marketing line) |
| F4 | **Adjacent** time-data caveat next to the +60-day result: all 375,378 rows have no independent public time → same-day assumption, not point-in-time (EN+zh) |
| F5 | **S-028 / S-029 NO-GO** added to the negative-results section, marked branch-only drafts (EN+zh) |
| F6 | Unsourced "~11 % auditable basis" replaced with sourced **35.2 % company key / 52.4 % track** (`docs/DATA.md`) (EN+zh) |
| F7 | Stray BOM removed; all touched text normalized to **LF** (fixes the CI-only `views` failure: `gen_views` hashes raw state bytes) |

**Verified:** 24 README claims checked; the 60-day figure (n=61, +5.6485 %, t=2.4545, CI [1.3547, 10.3198]), M2RD negative results, 375,378 events / 1.3 GiB, image caption (snapshot 2026-10-31 + package v0.5.0 + "not live/not a forecast"), and the #12–#30 "not released" boundary all match their artefacts. Test count guard `tests/test_release.py` passes at 1,160.

**Minor, non-blocking (documented):** Chinese README has no generated status block (EN-only) and a few version/test facts are duplicated between the summary table and the generated block. No numbers conflict.

### 1.4 Task 3 — historical data safety

**PASS** (independent scan; `_evidence/data_safety/DATA_SAFETY_FINAL.md`):
24 commits (19 normal + 5 merges), 315 reachable objects, **157 blobs content-scanned**, 589 file-change
events, replaced blobs included (README 7 versions, PROJECT_STATE 3, DATA_LICENSES 4, …), binaries
header/size only, 0 blobs > 200 KB.

| Category | Result |
|---|---|
| Restricted Comtrade-derived value | **0 blobs / 0 occurrences** (also 0 in `git log -p`, 30,944 lines) |
| Restricted bulk payload records | **0 blobs** |
| Credentials (PEM, `ghp_`, `AKIA`, `sk-`, JWT, password, `.env`) | **0 blobs / 0 occurrences** |
| Personal e-mails | **0** |
| Phones / contact names / buyer lists | **0 / 0 / 0** |
| Diagnostic fixture e-mail (`@example.invalid`) | 1, not PII |
| Restricted-source **path references** (triage docs only) | 4 blobs / 74 matches, no data |
| Absolute paths / machine identifiers | 8 occurrences in 5 blobs; **1 user-profile path** in a historical evidence log |
| Binary blobs | 2 synthetic fixtures (62 B SQLite header, 51 B gzip) |

**Advisory (disclosed, non-blocking):** the only personal-ish token is a local Windows user-profile
path inside a historical blob of `docs/refoundation/phase2/_evidence/governance/01_environment.txt`
(intermediate commit). The **final tree is sanitized** (`<PYTHON>` / `<WORKTREE>`), it is already
present in the public `governance/refoundation-002` branch history, and removing it would require
rewriting history, which this task forbids. **No restricted value, credential, or personal-data list
exists in any reachable commit.** Owner may accept (recommended) or schedule a future rewrite.

---

### 1.5 Python 3.10 CI compatibility (found on the first final CI run)

First final CI run: py3.11/3.12 green, **py3.10 failed** with
`ValueError: Invalid isoformat string: '2026-11-12T21:05:55Z'`. Root cause:
`datetime.fromisoformat()` only accepts the `Z` suffix from Python 3.11; the state fixtures and
git/CI timestamps emit it. This made three merge-simulation tests and the bump instant test fail on
3.10 only.

Fix: `check_state._parse_iso()` normalizes a trailing `Z` to `+00:00` before parsing, and the test
instant helper does the same. **Assertions are unchanged.** Verified under the real interpreter:
`python3.10 -m unittest tests.governance.test_bump_state tests.governance.test_state_scheme` →
**16/16 OK**, and `python3.10 tools/governance/check_state.py` → PASS (253 checks).

---

## 2. Final commit SHA

| Ref | SHA |
|---|---|
| Validated integration tree | **`6784043`** (includes the Python 3.10 fix; supersedes the earlier `34b3548` measurement commit) |
| This report (docs-only tip) | the branch tip after this file is committed (§7 records it) |
| PR #38 head before this gate | `cfa685c` |
| Base `origin/main` | `b2a14c0` (unchanged) |

---

## 3. CI and repeated test results

| Check | Result |
|---|---|
| Flake test, **30 independent runs** | **30/30 pass**, 0 failures |
| Full suite on final tree | **1,157 passed, 3 skipped, 224 subtests** (1,160 collected), 69.4 s |
| `python -m medradar selftest` | `Ran 1,160, OK (skipped=3)` |
| Six governance gates | state **253 checks**, views 3, frozen 36, licence 14, links 3, rule-audit 24 — **all PASS** (2 expected state warnings: stale-but-ancestor + tested-head ahead) |
| CI | re-run after this push (previous #38 run at `cfa685c`: **11/11 green**) |
| Clean-tree requirement | satisfied: audits were moved outside worktrees; no untracked data files |

---

## 4. Historical data safety

See §1.4. **PASS**, with one disclosed advisory. No history rewrite performed or recommended in
this round.

---

## 5. Consecutive merge simulation

See §1.2: **3/3 merges** with gates PASS before bump (staleness WARN only), then bump tracks the new
head and gates pass without staleness. This demonstrates the state no longer self-references the
merge SHA.

---

## 6. Post-merge verification and rollback

**Merge mechanics (owner action):** merge PR #38 with a **merge commit** (do not squash).

**Immediately after merge:**
```bash
python tools/governance/bump_state.py --ref origin/main --with-views
python tools/governance/check_state.py
python tools/governance/gen_views.py --check
python -m pytest -q -o addopts=""          # expect 1,157 passed / 3 skipped
```
The bump sets `git.head` and `verified.commit` to the new `main`, refreshes counts/subject, and
regenerates README/CHANGELOG/RESEARCH_INDEX. Expect the two current warnings to disappear.

**Verification checklist:** 6 CI jobs green on the first post-merge PR; `main` CI green; no UNKNOWN
state; `docs/INDEX.md` links resolve.

**Rollback:** `git revert -m 1 <merge-sha>` on `main` restores the previous tree; the production
SQLite was never migrated by this PR (migration is lazy and not run), so no data rollback is needed.
If Evidence Core has been opened against the production DB before rollback, restore from the
Phase 0 backup (`sha256 445807ca…`).

---

## 7. GO / NO-GO

**Decision: GO.**

Conditions attached to the GO:
1. Merge **PR #38** with a merge commit, then run the bump command above as a small follow-up commit
   (owner action).
2. Do **not** set branch protection or required checks until a deliberate-failure PR proves the
   gates go red and a post-merge PR proves they run on `main`.
3. **#27 / #29 remain BLOCKED_LEGAL** and are not part of this PR; do not merge them.
4. Accept the §1.4 advisory (user-profile path in historical blob) or schedule a separate,
   owner-approved history rewrite; it is **not** a merge blocker for this PR.
5. Preserve #37 as SUPERSEDED; do not merge it separately.

**NO-GO would apply if:** a restricted value/credential appears in the final tree (none), the 30-run
proof fails (it passes 30/30), the full suite fails (1,157 pass), or a gate fails (all pass).
