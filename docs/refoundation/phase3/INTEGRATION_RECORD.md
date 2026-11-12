# REFOUNDATION-003 — Integration Record

**Baseline:** `origin/main` = `b2a14c0` (unchanged throughout this work).
**Integration branch:** `integration/ref003` (local, then PR).
**Constraint:** every step below is a **local dry-run**. No `main` push, no merge button, no force-push, no branch deletion. Actual merging requires the owner's explicit approval.

---

## 0. Remote tips at start (verified with `git ls-remote`, not assumed)

| Branch | Tip |
|---|---|
| `main` | `b2a14c0` |
| `governance/refoundation-002` (#32) | `1331883` (after two integration fixes, see §3) |
| `feature/evidence-core-v1` (#35) | `f088e37` |
| `research/e1b-source-recovery` (#36) | `6ffe7e7` |
| `docs/readme-truth-phase2` (#34) | `6a95a5b` |
| `refoundation/phase2-acceptance` (#37) | `8c23a3a` |
| `docs/ref003-navigation-readme` (new README) | `032b960` |

A first attempt merged the **stale local** `governance/refoundation-002` (`8d7fd62`) instead of the pushed `beacd11`. That is exactly the class of error this dry-run exists to catch; the branch was reset and every merge was redone from `origin/*` refs.

---

## 1. Merge sequence (final, all clean unless stated)

| Step | Ref merged | Merge commit | Conflicts | Result |
|---|---|---|---|---|
| 1 | `origin/governance/refoundation-002` (#32) | `d746b86` | none | 6 governance gates + 46 tests green |
| 2 | `origin/feature/evidence-core-v1` (#35) | `faab1a5` | none | Evidence Core + 28 tests |
| 3 | `origin/research/e1b-source-recovery` (#36) | `413254f` | none | E1b docs + scripts |
| 4 | `origin/docs/readme-truth-phase2` (#34) | `3be8a4e` | none | truth README + `test_release` fix |
| 5 | `docs/ref003-navigation-readme` (new front page) | `96950ba` + `81aaa84` | **README.md / README.zh-CN.md** | resolved in favour of the new design; #34's README text superseded, its test fix and report kept |

`#37` (Phase 2 acceptance package) is **superseded by this integration**: 4 of its 5 files are byte-identical copies of the #32/#34/#35/#36 reports; only `PHASE2_ACCEPTANCE.md` is unique and will be folded in here.

---

## 2. Test matrix at each step

| After | Suite | Gates |
|---|---|---|
| #32 | 46 governance tests pass; full 1,117 collected / 1,114 passed / 3 skipped | state 240, views 3, frozen 36, licence 14, links 3, rule-audit 18 — all PASS |
| #32+#35 | **2 failures found** (see §3) | licence 6 failures (diff scan) |
| #32+#35+#36 | 1,145 passed / 3 skipped | licence diff failures fixed by `1331883` |
| #32+#35+#36+#34 | 1,145 passed / 3 skipped | all 6 gates PASS, `gen_views --check` PASS |
| + new README | **1,145 passed / 3 skipped / 224 subtests** | all 6 gates PASS; `gen_views --check` PASS |

Final `pytest`: `1145 passed, 3 skipped, 224 subtests passed in 45.10s` (1,148 collected).

---

## 3. Blockers found and fixed on the owning PR (not in a mega-PR)

The dry-run found two **real cross-PR interactions** that no individual PR could see:

1. **Inventory vs Evidence JSON (#32 × #35).**
   `check_licence` requires every tracked data file to have an inventory entry. Evidence Core's `evidence_core.json` (and later E1b's five JSON/JSONL files) are **our own generated evidence**, not third-party data. Fix on #32: `docs/refoundation/*/_evidence/*` is exempt from the *inventory requirement only*; content classification and restricted-format rejection are unchanged. Records: `RC-0002` / `GOV-0002`. Commit `4ea5ada`.
2. **Same exemption missing in the PR diff scan (#32 × #36).**
   The tree check was fixed but `diff.changed_data_file` still failed on the same files. Fix on #32: apply the same exemption to the diff scan. Commit `1331883`.

Both fixes were made **on PR #32**, pushed as fast-forwards, and the integration was redone from `origin/*` refs. No new mega-PR was created.

---

## 4. State source after consecutive merges

`PROJECT_STATE.yaml` describes the **base** `origin/main`, so during the dry-run it still says `b2a14c0` and `check_state` passes against the real `origin/main`. After `main` actually advances, the next PR must bump it:

```
python tools/governance/bump_state.py --ref origin/main --dry-run   # show diff
python tools/governance/bump_state.py --ref origin/main --with-views # apply + regenerate
```

Verified by dry-run against the integration HEAD (`81aaa84`): it updates `main.head`, `short`, `committed_at`, `commit_subject`, `tracked_files` (1,135 → 1,225) and regenerates views. So the answer to "does the state auto-update?" is: **no silent auto-update; a one-command bump is required after each merge**, and the gate fails loudly until it runs (by design, so the state cannot silently drift).

---

## 5. Gate-proof on the integrated tree

| Proof | Result |
|---|---|
| Freeze tamper: append 1 byte to a frozen forecast set | **FAIL check_frozen (2 failures)** |
| Restore via `git checkout --` | **PASS**, worktree clean |
| `gen_views --check` after hand-regenerating status | **PASS** |
| `check_rule_audit` with RC-0002/GOV-0002 | **PASS (18 checks)** |
| GitHub Actions on #32 | 11/11 green, including all 6 governance jobs |

---

## 6. Rollback

Each step is an ordinary merge commit on `integration/ref003`:

- Undo the last merge: `git revert -m 1 <merge-sha>` (keeps history).
- Undo to a step: `git reset --hard <previous-merge-sha>` on the integration branch only.
- No `main` was touched, no force-push was used, and the production DB was never opened read-write (sha256 `445807ca…` unchanged).

---

## 7. Known issue to fix after merge

`tests/governance/test_bump_state.py::test_generated_at_is_the_ref_commit_time` failed **once** in a full-suite run and passed in isolation and on every subsequent run (`4 passed`). It compares `%cI` of a temp-repo commit with the generated timestamp and is sensitive to the surrounding test environment (likely a second-boundary/clock issue). Treat as **flaky**, not a product defect; add a deterministic clock or tolerance before making it a required check.
