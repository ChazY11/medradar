# State lifecycle — the five-concept scheme

**Problem.** The old state recorded a single `main.head` and required it to equal
`origin/main`. A merge therefore made the state instantly and permanently stale:
the next PR failed `check_state` until someone ran `bump_state`, and a post-merge
bot commit could never fix it (recording the head changes the head).

**Solution.** `PROJECT_STATE.yaml` (schema `medradar.project_state.v2`) distinguishes
five concepts and validates each against the commit it describes. A stale-but-real
observation is a **warning**; a wrong lineage is a **failure**.

Schema: `PROJECT_STATE.yaml` → `git`, `verified`, `release`, `data_snapshot`,
`tests`. `tools/governance/check_state.py` implements the matrix below;
`tools/governance/bump_state.py` refreshes the observed/verified/version facts in
one deterministic command.

## 1. The five concepts

| # | Field | Meaning | May lag main? | Validated against |
| --- | --- | --- | --- | --- |
| 1 | `git.head` (+ `ref`, `short`, `committed_at`, `commit_subject`, `observed_at`, `tracked_files`, `workflows`) | the main commit last **observed**; facts in this block describe that commit | **yes, by design** | ancestry vs current main (`origin/main`); date/subject/counts/workflows vs `git.head` itself |
| 2 | `verified.commit` (+ `verified_at`, `note`) | last commit whose full offline suite + all six gates passed | yes (must be on main's history) | ancestor of current main |
| 3 | `release.version` + `release.commit` | what is actually released; `commit: null` = unreleased | `commit` must be a landed main commit | `version` = `pyproject.toml` at `git.head`; non-null `commit` ancestor of main |
| 4 | `data_snapshot` | local data build (date, events, sources, DB size) | n/a (not a git fact) | existing structural checks; `data/` is gitignored |
| 5 | `tests.tested_head` (+ counts, artifact) | commit the measured suite describes | yes | ancestry-related to `verified.commit` or `git.head`; lag/ahead is a warning; unrelated is a failure |

The recorded file/workflow/version counts are validated against **`git.head`**
(the commit the state describes), not against current `origin/main`. That is what
makes a merge safe: main can advance while the state still truthfully describes
the previously observed commit.

## 2. Validation matrix (`check_state.py`)

| Check id | Rule | Outcome |
| --- | --- | --- |
| `git.head.format` / `git.short.consistent` | 40-hex, short = first 7 | FAIL |
| `git.ref.resolve` | `--main-ref` (default: `git.ref`, i.e. `origin/main`) resolves | FAIL |
| `git.head.exists` | recorded commit exists | FAIL |
| `git.head.ancestor` | observed head **is an ancestor of** current main | PASS; if it is main: current, otherwise **WARN** (`stale by design`) |
| `git.head.ancestor` (wrong lineage) | observed head is **not** an ancestor of main | **FAIL** |
| `git.committed_at.git`, `git.commit_subject.git` | date/subject at the observed commit | FAIL on mismatch |
| `git.tracked_files.git`, `git.workflows.git` | tree counts at the observed commit | FAIL on mismatch |
| `verified.commit.format` / `.exists` | 40-hex, exists | FAIL |
| `verified.commit.ancestor` | verified baseline is an ancestor of main | FAIL if not |
| `release.version.format` / `.pyproject` | semver-like; equals `pyproject.toml` at `git.head` | FAIL on mismatch |
| `release.commit` | `null`, or an existing ancestor of main | FAIL if not |
| `tests.tested_head.format` / `.exists` | 40-hex, exists | FAIL |
| `tests.tested_head.ancestry` | ancestry-related to `verified.commit` **or** `git.head` | FAIL if unrelated; **WARN** if lagging or ahead |
| `tests.artifact.tested_head` | same rules for the measurement artifact; must equal the state's `tests.tested_head` | FAIL on mismatch/unrelated |
| tests counts/arith./artifact | existing strict artifact comparison | FAIL on mismatch |
| paths, ids, decisions, freeze refs, data snapshot, capabilities, studies, PR counts | unchanged existing checks | as before |

Ancestry is directed: a commit is related when one is an ancestor of the other.
Two commits on unrelated lines (a diverged branch) therefore FAIL. A measurement
taken on an integration tree that is *ahead* of the observed head is reported as a
warning, not a failure — it is the same lineage and becomes an ordinary ancestor
after the merge bump. This is the migration path for the current state, whose
`tests.tested_head` is the REFOUNDATION-003 integration measurement.

## 3. Lifecycle after a merge

```
merge lands on main
        │
        ▼
check_state:  git.head is stale but an ancestor  → PASS + WARN    ← no red gate
views/frozen/licence/links/rule-audit:            PASS
        │
        ▼
python tools/governance/bump_state.py            ← ONE command
   refreshes git.* and verified.* from origin/main,
   keeps release.commit, regenerates the views
        │
        ▼
check_state:  git.head == origin/main            → PASS (no staleness warning)
```

The one command is `python tools/governance/bump_state.py` (default
`--ref origin/main`). Options: `--dry-run` (diff only), `--no-views` (state only),
`--ref <branch>` (simulation or a non-default main). It is deterministic: the
state `generated_at`, the observed date and `verified_at` come from the ref's
commit time — no wall clock. It never invents a release: an existing non-null
`release.commit` is preserved.

## 4. Three consecutive simulated merges (mandatory proof)

Throwaway branch `sim/main-3merge` from the current branch head; three feature
branches merged with `--no-ff`. After each merge the **six gates ran without
bump**, then `bump_state.py --ref sim/main-3merge` ran (regenerating views), then
the gates ran again. Full log:
[`_evidence/state_scheme/02_three_merge_simulation.txt`](_evidence/state_scheme/02_three_merge_simulation.txt).

| Round | Merge commit | Gates WITHOUT bump | Stale warning | Bump | State tracks head | Gates AFTER bump |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `1ed43b2e14a9` | all six PASS (state PASS + WARN) | yes | UPDATED, 1238 files, 5 workflows, views regenerated | `git.head` = `verified.commit` = `1ed43b2` | all six PASS, no staleness |
| 2 | `91cd144e050a` | all six PASS (state PASS + WARN) | yes | UPDATED, 1239 files | `git.head` = `verified.commit` = `91cd144` | all six PASS |
| 3 | `12a1c9a52289` | all six PASS (state PASS + WARN) | yes | UPDATED, 1240 files | `git.head` = `verified.commit` = `12a1c9a` | all six PASS |

**Result: PASS.** A merge no longer creates a permanently failing gate; the bump
is a refresh, not a rescue.

## 5. Other proofs and tests

* `tests/governance/test_state_scheme.py`: stale-but-ancestor → pass+warning;
  current head → no warning; non-ancestor `git.head` → fail; non-ancestor
  `verified.commit` → fail; unrelated `tests.tested_head` → fail; lagging tested
  head → warning; the three-merge simulation at unit level.
* `tests/governance/test_bump_state.py`: static fixture state + pyproject (no live
  repo copy), every bump call asserts exit 0, `generated_at` compared as a
  normalized instant (epoch seconds), all-digit hash quoting regression test.
* Flake fix: the old test copied the **live** repo-root `PROJECT_STATE.yaml` and
  ignored bump's exit code, so a mutable/partial repo state or a failed bump
  produced a misleading `generated_at` mismatch. The seed is now
  `tests/governance/fixtures/state_schema_v2.yaml` +
  `pyproject_fixture.toml`; `test_generated_at_is_the_ref_commit_time` ran
  **30/30** in a loop
  ([`03_30_run_flake_log.txt`](_evidence/state_scheme/03_30_run_flake_log.txt)).
* Full suite and six gates: see
  [`05_full_suite_and_gates.txt`](_evidence/state_scheme/05_full_suite_and_gates.txt).

## 6. Migration notes

* Schema changed `medradar.project_state.v1` → `.v2`; `main:` became `git:` +
  `verified:` + `release:`. `data_snapshot` and `tests` are unchanged in meaning.
* On this branch the state describes `origin/main` at `b2a14c0` (pre-merge), while
  the measured suite is the REFOUNDATION-003 integration tree. That measurement is
  *ahead* of the observed head and flagged as a warning; the merge bump makes it an
  ordinary ancestor and the warning disappears.
* `release.commit` is `null` until a release commit is recorded; bump preserves it.
* A release version must match `pyproject.toml` at the observed head; when a
  release is made from an earlier commit, bump first then record the release
  commit and version in the same hand edit.

## 7. Remaining limitations

* `verified.commit` asserts "the suite and gates passed there" as a recorded fact;
  the gate checks ancestry, not that the run happened. The artifact chain
  (`tests.tested_head`, `record_tests`, CI) is the evidence for the suite.
* `git.head` may lag arbitrarily; the gate bounds it only by ancestry and warns.
  A maximum-lag policy (e.g. "bump within N merges") would be a policy choice, not
  implemented here.
* Base-ref checks (`frozen`, `licence`, `rule-audit`) need `origin/main` history
  (`fetch-depth: 0` in CI); in a shallow clone the comparison warns/skips.
* Branch protection is still not applied; this is a merge-gate workflow, not
  server-side enforcement.

## 8. Evidence index

Under `docs/refoundation/phase3/_evidence/state_scheme/`:

| File | Contents |
| --- | --- |
| `00_state_schema_v2_fixture.yaml` | static PROJECT_STATE fixture used by the tests |
| `00_pyproject_fixture.toml` | static pyproject fixture (version 9.9.9) |
| `01_environment.txt` | branch/HEAD/origin/main, Python/git/OS |
| `02_three_merge_simulation.txt` | the three-merge table above, with every gate exit |
| `03_30_run_flake_log.txt` | 30/30 passes of the previously flaky timestamp test |
| `04_state_scheme_tests.txt` | the new state-scheme test module |
| `05_full_suite_and_gates.txt` | full pytest, selftest and the six gates |
| `06_state_after_migration.txt` | the migrated `git`/`verified`/`release`/`tests` blocks |
| `07_final_validation.txt` | final HEAD: full pytest, six gates, clean worktree, local-only commits |
