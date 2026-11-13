# MIGRATION_PLAN — phased, executable, reversible (REFOUNDATION-001 / A5)

**Scope.** This is the execution plan that turns `main` (HEAD `b2a14c0`, 2026-11-02, PRs #1–#11 only) into
the architecture described in `ARCHITECTURE_TO_BE.md`, without losing a single frozen research result and
without a big-bang merge. Seven phases, each independently shippable, each with a concrete rollback. It
covers the merge order for the #12–#16 product stack **and** for the #27/#28/#29/#30 foundation stack.

**Method.** Read-only inspection of the git object store (`git show origin/<ref>:<path>`, `git ls-tree`,
`git diff --stat origin/A...origin/B`, `git rev-parse <ref>:<path>`), plus direct reads of `main` and of the
nine branch-only infrastructures. Blob identities were verified for the duplication claims (see
`ARCHITECTURE_TO_BE.md` §13.3). No branch was fetched, checked out, merged, rebased, committed or pushed
while writing this plan; every `git` command below is a *proposal* for the owner to run.

**Evidence base.** `docs/refoundation/_FACTS.md`; `docs/refoundation/_evidence/repo_facts.json`;
`ARCHITECTURE_TO_BE.md` (this plan's target state); direct blob inspection of
`origin/{feat/medradar-2.0-mvp, feat/live-observatory-v1, feat/observatory-reliability-v1,
research/s028-temporal-graph-early-signal, research/s029-evidence-based-relations, foundation/atlas-001,
research/horizon-001, integration/convergence-001}`;
`docs/refoundation/_evidence/tobe/verified_invariants.json` (blob hashes and incremental-scope counts this
plan's merge order depends on).

**Limits.** (1) The 39 registered worktrees in `<REDACTED_LOCAL_PATH> were not inspected individually; this
plan assumes they are harmless and says where they matter (Phase 0.4, Phase 3). (2) Unpushed local commits
were counted from `_FACTS.md`, not re-counted; the Phase-0 commands must re-verify counts before pushing.
(3) CI status of `main` is `[UNVERIFIED]`; the plan therefore *starts* by measuring it rather than assuming
green. (4) Wall-clock estimates assume one owner working with AI assistance, 5–6 productive hours a day, no
review queue. (5) Nothing here has been executed; a phase is "done" only when its exit-criteria commands
have been run and their output attached.

**Labels.** `[FACT]` verified from git/files. `[INFERENCE]` reasoned, chain stated. `[RECOMMENDATION]`
proposal. `[UNVERIFIED]` could not be checked, reason stated.

---

## 0. How to read this plan

### 0.1 Six rules that govern every phase

1. **`main` is the only shipped state.** Every phase ends with `main` green and Pages still building.
   A phase that leaves `main` red is worse than a phase that does not happen.
2. **Nothing is ever force-pushed.** Not a branch, not a tag, not `main`. History is append-only; a
   mistake is corrected by a revert commit, never by rewriting.
3. **Each phase is a revertible unit.** One merge commit (or one small chain of merge commits) per phase,
   tagged before and after, so rollback is `git revert -m 1 <sha>` rather than archaeology.
4. **Frozen evidence has a higher priority than tidiness.** If a work item would change the bytes of a
   frozen artifact, the work item is wrong.
5. **Exit criteria are commands, not adjectives.** "Evidence layer complete" is not an exit criterion;
   `python -m medradar selftest` returning 0 plus a named test file passing is.
6. **No phase depends on a phase that has not shipped.** Prerequisites name a *tag*, not an intention.

### 0.2 The four invariants that must never be violated

| # | Invariant | Measured by | Current value |
|---|---|---|---|
| I1 | the offline suite passes | `python -m medradar selftest` | `[FACT]` 1,074 tests per the Lead's evidence bundle; must never decrease |
| I2 | frozen results are byte-identical to their recorded hash | `git rev-parse <ref>:<path>` + the study's own freeze manifest | `[FACT]` S-028 `prereg_freeze.json` records protocol hashes + input DB sha256 |
| I3 | no branch, tag or PR is rewritten or deleted | `git tag -l 'refoundation/*'`, PR history | n/a |
| I4 | Pages still builds from `main:/docs` | Pages build status after every merge to `main` | `[FACT]` last build `b2a14c0` |

`[INFERENCE]` I1 is the single most valuable asset in this repository. It means the "stable spine"
(`medradar/tkg`, `medradar/db.py`, `medradar/intelligence`, `medradar/config.py`) can be treated as a
*platform* rather than as code under change — which is why every phase below adds around the spine instead
of through it.

---

## 1. Preconditions measured before Phase 0

Run these first and attach the output. If any of them contradicts this plan, stop and re-plan.

```bash
# P-1  what main actually is
git rev-parse origin/main                      # expect b2a14c0a92332c004445de686daee97754cf94cb
git log -1 --format='%H %ci %s' origin/main

# P-2  does main's own suite pass? (this is I1; do not trust the README)
python -m medradar selftest                    # expect exit 0; record the test count

# P-3  does the package install and resolve config from a wheel?
python scripts/check_install.py

# P-4  the unpushed-work inventory (must match _FACTS.md §5 before touching anything)
git for-each-ref --format='%(refname:short) %(objectname:short)' refs/heads | sort
for b in research/phoenix-001-external-methods research/temporal-knowledge-graph \
         research/forecast-registry phase3/registry-cycle integration/audit-dryrun; do
  echo "== $b"; git rev-list --count origin/main..$b 2>/dev/null || echo "no local branch"
done

# P-5  the duplicate-infrastructure confirmation (drives Phase 3 and Phase 6)
for b in feat/medradar-2.0-mvp feat/live-observatory-v1 feat/observatory-reliability-v1 \
         research/s028-temporal-graph-early-signal research/s029-evidence-based-relations; do
  git rev-parse "origin/$b:medradar/product/store.py"
done                                            # expect one identical blob 5×
git rev-parse origin/foundation/atlas-001:medradar/atlas/evidence/schema.py \
              origin/integration/convergence-001:medradar/atlas/evidence/schema.py   # expect identical

# P-6  branch-only targets we must not disturb
git worktree list | measure-object -line        # expect 39 registered worktrees
```

`[RECOMMENDATION]` Paste the output of P-1…P-6 into `docs/refoundation/_evidence/tobe/preflight.md` before
starting Phase 0. That file becomes the baseline the whole migration is judged against.

---

## 2. The merge-order decision

### 2.1 The dependency reality

`[FACT]` Three separate dependency structures exist, and they must not be treated as one queue:

```
A. product stack (all on branch-only bases)
   main ── #12 feat/medradar-2.0-mvp
             └── #13 feat/live-observatory-v1
                   └── #14 feat/observatory-reliability-v1
                         ├── #15 research/s028-temporal-graph-early-signal   (+ research/studies/graph_early_signal_s028/** only)
                         └── #16 research/s029-evidence-based-relations      (+ research/studies/relation_network_s029/** only)

B. foundation stack (all based on main, independent of A)
   main ── #28 foundation/atlas-001
   main ── #29 research/horizon-001
   main ── #27 research/data-expansion-001
   main ── #30 integration/convergence-001  = ATLAS + HORIZON + glue

C. independent strays
   #1  (CONFLICTING, 154 behind) · #17 · #18 · #19→#20 · #21(PR-less base) · #22 · #23→#24→#25 · #26
```

`[FACT]` I verified the incremental content of #15 and #16 against their base (#14): **#15 adds only
`research/studies/graph_early_signal_s028/**`, #16 adds only `research/studies/relation_network_s029/**`.**
Neither touches `medradar/`, `config/`, `tests/` or `.github/`. `[INFERENCE]` Therefore, once #14 is on
`main`, #15 and #16 merge in **either order with zero conflicts** — the "stack" is only a stack because
they were branched from #14 instead of from `main`.

`[FACT]` I also verified that `medradar/product/store.py` is the **same blob** on all five of
#12/#13/#14/#15/#16, and that `medradar/atlas/**` is **byte-identical** between #28 and #30.
`[FACT]` The reason is **inheritance, not copying**, and this materially simplifies the plan:
- `git merge-base --is-ancestor origin/foundation/atlas-001 origin/integration/convergence-001` → **0 (yes)**
- `git merge-base --is-ancestor origin/feat/medradar-2.0-mvp origin/feat/observatory-reliability-v1` → **0 (yes)**

`[INFERENCE]` So the "byte-identical across N branches" observation is ordinary linear stacking: each head
contains its base's files unchanged. Merging base-first means every later merge re-adds **nothing** for those
paths. Nothing has to be "de-duplicated" by hand; the only thing that must not happen is merging a *child*
before its parent, which would import the parent's work unreviewed. The one genuine copy-paste in the
repository is `#29 HORIZON` → `#30` (not an ancestor; `ARCHITECTURE_AS_IS.md` §9.4 assigns it TD-001), and I
quantified it in §2.2 below.
(the blobs are equal) but the ownership would be ambiguous and a future edit would diverge them silently.

### 2.2 The decided order

| Step | What merges | Onto | Why this position |
|---|---|---|---|
| **1** | #28 `foundation/atlas-001` | `main` | Independent of everything; it is the evidence+identity core that Phases 2–6 all need |
| **2** | #12 `feat/medradar-2.0-mvp` | `main` (rebase first) | Product read model + SPA; needed before the app can be gated |
| **3** | #13 `feat/live-observatory-v1` | `main` after #12 | Adds `medradar/observatory/**`; the acquisition layer |
| **4** | #14 `feat/observatory-reliability-v1` | `main` after #13 | Backup/restore/lease/7-day validation — the local-first guarantees |
| **5** | #15 **and** #16 | `main` after #14, either order | Pure additive study trees; frozen; no code risk |
| **6** | #27, #29 | `main` | Data corpora + connectors; #29 before #30 because #30 assumes it |
| **7** | #30 `integration/convergence-001` | `main` after #28 **and** #29, rebased | Glue only: `medradar/integration/**`, `config/convergence/**`, plus 155 paths that exist only on #30 |
| **8** | #1, #17, #18, #19/#20, #21, #22, #23–#26 | *not in this programme* | See §2.3 |

`[RECOMMENDATION]` Rationale for putting #28 before the product stack even though the product stack is the
"visible" work: #28 changes no existing file (it is 70 files, all additions per
`git diff --stat origin/main...origin/foundation/atlas-001`), so it is the lowest-risk merge available, and
every later phase needs its identity and evidence code. Merging it first also means #30's duplicate can be
detected mechanically (`git diff` shows nothing new under `medradar/atlas/`) rather than by review.

### 2.3 "Do not merge until …" list

| PR | Do not merge until | Reason |
|---|---|---|
| **#1** | **never in this programme** | `[FACT]` `CONFLICTING`, 154 commits behind `main`, and its capability already exists on `main` as `medradar/frontier.py`. Closing it with a note is the correct action. |
| **#12** | Phase 2 exit (tag `refoundation/p2`) | Rebase onto a `main` that already has #28, so the product read model can consume the evidence store rather than re-deriving from S1 |
| **#13** | #12 merged **and** Phase 3a tag | Its incremental diff includes a full copy of #12; merging it first would import #12 implicitly without review |
| **#14** | #13 merged | Same reason, one level deeper |
| **#15** | #14 merged | Its only unique content is a frozen study tree; it must land on a `main` where `research/studies/` already exists |
| **#16** | #14 merged | Same |
| **#27** | Phase 5 start | It is a data corpus whose licence posture must be judged by the Gate that Phase 2 introduces |
| **#29** | Phase 5 start | 692,975 added lines, 691 files; merging it before the licence gate exists means importing data we cannot yet classify |
| **#30** | #28 **and** #29 merged, **and** the six divergent paths reconciled (`.gitignore`, `README.md`, `research/horizon/{EXPERIMENT_RESULTS.md, experiments/industry/EXP_H4_INDUSTRY.json, reports/INDUSTRY_DATA_REPORT.md, reports/REGULATORY_FRONTIER_REPORT.md}`) | #28 is an *ancestor* so its ATLAS files are a no-op, but #29 is **not** an ancestor: 1,787 paths are equal, **6 differ**, 155 are #30-only. Those six are the real conflicts and must be resolved by a human, not by `-X theirs` |
| **#17** | after Phase 1 | Documentation consolidation should follow the governance spine, not precede it |
| **#18** | never as a merge; read as evidence | Machine review of 69 packets; `[FACT]` the study's own protocol says AI labels cannot count as human truth |
| **#19/#20** | never as a merge | `[FACT]` #20's title declares "Draft，不合并" (draft, do not merge) |
| **#21** | never as-is | Its base `integration/phase4-base` has no PR and is 39 commits ahead of `main`; merge the *studies* individually if ever |
| **#22** | Phase 4 (freeze first) | 600 files / +303,926; must be frozen before relocation |
| **#23–#26** | Phase 4 (freeze only) | PHOENIX results are negative results with protocols; they are cited, not merged into the runtime path |

`[RECOMMENDATION]` Convert this table into the PR template's checklist
(`.github/pull_request_template.md`) so the rule is enforced at review time, not remembered.

---

## 3. Phase overview

| Phase | Name | Effort | Window (est.) | Ends with | Tag |
|---|---|---|---|---|---|
| **0** | Preserve & protect | 0.5 d | 2026-11-12 | nothing changed; everything recoverable | `refoundation/p0` |
| **1** | Governance spine | 2 d | 2026-11-13 → 11-14 | machine-readable state + 4 CI gates on `main` | `refoundation/p1` |
| **2** | Evidence contract + identity (absorb ATLAS) | 5 d | 2026-11-15 → 11-19 | one vertical slice: source → evidence → identity → export | `refoundation/p2` |
| **3** | Product stack rebase/merge (#12→#13→#14) | 4 d | 2026-11-20 → 11-23 | product + web + observatory on `main`, green | `refoundation/p3a/p3b/p3c` |
| **4** | Study re-homing (S-028/029, PHOENIX, S-031) | 3 d | 2026-11-24 → 11-26 | frozen studies relocated, hashes proven unchanged | `refoundation/p4` |
| **5** | Global data + rights gating (#27/#29) | 3 d | 2026-11-27 → 11-29 | licence gate enforced at store **and** export | `refoundation/p5` |
| **6** | CONVERGENCE (#30) + app integration | 4 d | 2026-11-30 → 12-03 | de-duplicated convergence glue + gated app + generated Pages | `refoundation/p6` |
| | **Total** | **21.5 d** | 2026-11-12 → 12-03 | `main` is the single shipped state | |

`[RECOMMENDATION]` The order is not negotiable in one respect only: **Phase 2 before Phase 3**. Everything
else can slip a week without breaking a dependency, because each phase's prerequisite is a tag.

---

## 4. Phase 0 — Preserve and protect (0.5 day, 2026-11-12)

### 4.1 Goal

Make every existing artifact recoverable before a single byte changes. This phase produces **no code
change and no merge**; it produces tags, a bundle, and a written inventory.

### 4.2 Prerequisites

P-1…P-6 from §1 executed. Read access to the clone `<REDACTED_LOCAL_PATH> (write access is *not* needed
beyond creating tags/branches, which the owner performs).

### 4.3 Work items

**0.1 Preserve the 33 unpushed commits.** `[FACT]` the local `research/phoenix-001-external-methods` is 33
commits ahead of the remote branch PR #23 points at, so the PR shows stale content. Push the local state to
a **new** protection branch (never over the PR branch):

```bash
git -C <REDACTED_LOCAL_PATH> push origin \
  refs/heads/research/phoenix-001-external-methods:refs/heads/rescue/phoenix-001-local-33
git -C <REDACTED_LOCAL_PATH> rev-list --count origin/rescue/phoenix-001-local-33   # expect 33+delta
```

`[RECOMMENDATION]` The `rescue/` prefix matches `DECISION_REGISTER.md` D-08 ("push to a `rescue/` branch +
tag immediately"); do not use an ad-hoc name.

**0.2 Preserve the four orphan local branches.** `[FACT]` `research/temporal-knowledge-graph` (2 commits),
`research/forecast-registry` (2), `phase3/registry-cycle` (1), `integration/audit-dryrun` (1) exist on this
machine only:

```bash
for b in research/temporal-knowledge-graph research/forecast-registry \
         phase3/registry-cycle integration/audit-dryrun; do
  git -C <REDACTED_LOCAL_PATH> push origin "refs/heads/$b:refs/heads/rescue/$b"
done
```

**0.3 Take a full local bundle** (offline, immune to remote accidents):

```bash
mkdir <REDACTED_LOCAL_PATH>
git -C <REDACTED_LOCAL_PATH> bundle create <REDACTED_LOCAL_PATH> --all
git -C <REDACTED_LOCAL_PATH> bundle verify <REDACTED_LOCAL_PATH>
Get-FileHash <REDACTED_LOCAL_PATH> -Algorithm SHA256
```

**0.4 Do not disturb the 39 worktrees.** `[FACT]` `_FACTS.md` §5 records 39 registered worktrees including
detached audit trees. Record them; then **close** (not delete) any that the migration does not need, because
a stale worktree holds a lock on a branch name and will make Phase 3's rebase confusing:

```bash
git -C <REDACTED_LOCAL_PATH> worktree list --porcelain > <REDACTED_LOCAL_PATH>
```

**0.5 Tag the frozen evidence and the current `main`.**

```bash
# main as-shipped
git -C <REDACTED_LOCAL_PATH> tag -a refoundation/p0-main-2026-11-12 b2a14c0 \
  -m "REFOUNDATION-001 Phase 0: main as shipped (PRs #1-#11), pre-migration baseline"
# each frozen study branch head, so the exact commit that produced the results is permanent
for b in research/s028-temporal-graph-early-signal research/s029-evidence-based-relations \
         research/phoenix-001-external-methods research/phoenix-001-round2 \
         research/phoenix-002-h8-validation research/phoenix-003-early-evidence \
         research/s031-hiring-capability-study; do
  git -C <REDACTED_LOCAL_PATH> tag -a "refoundation/p0-frozen-$(echo $b | tr '/' '-')" "origin/$b" \
    -m "REFOUNDATION-001 Phase 0: frozen study head for $b"
done
git -C <REDACTED_LOCAL_PATH> push origin --tags        # tags are additive; nothing is rewritten
```

**0.6 Record the freeze inputs in one machine-readable file.** Write
`docs/refoundation/_evidence/tobe/frozen_inputs.json` listing, per study: protocol file hashes, the input
database sha256 and size, the artifact hashes, and the branch head commit. `[FACT]` S-028's own
`artifacts/prereg_freeze.json` already contains most of this — copy it, do not recompute it, so the record
is the *study's* claim rather than ours.

**0.7 Declare the no-touch list** for the whole programme: `docs/dashboard.html`, `docs/preview.png`,
`docs/metrics.json`, `docs/report_zh.md`, `docs/report_en.md`, `docs/summary.csv`, `research/RESULTS/**`,
`research/forecasts/FORECAST_SET_*.json`, `verifier/runs/**`, `research/studies/**/artifacts/**`,
`research/atlas/reports/**`, `research/atlas/samples/**`. These may be *moved* (Phase 4) but never edited.

### 4.4 Owner

Owner (the person with push rights). Estimated 3–4 hours.

### 4.5 Verification commands

```bash
git -C <REDACTED_LOCAL_PATH> tag -l 'refoundation/*' | measure-object -line        # expect >= 8
git -C <REDACTED_LOCAL_PATH> rev-parse origin/rescue/phoenix-001-local-33
git -C <REDACTED_LOCAL_PATH> rev-parse research/phoenix-001-external-methods       # must be equal
git -C <REDACTED_LOCAL_PATH> bundle verify <REDACTED_LOCAL_PATH>
python -m medradar selftest                                                     # I1 unchanged: exit 0
```

### 4.6 Rollback

Additive only, so rollback is deletion of the protection refs and tags — and it should not be needed:

```bash
git -C <REDACTED_LOCAL_PATH> push origin --delete \
  rescue/phoenix-001-local-33 rescue/research/temporal-knowledge-graph \
  rescue/research/forecast-registry rescue/phase3/registry-cycle rescue/integration/audit-dryrun
git -C <REDACTED_LOCAL_PATH> tag -d $(git tag -l 'refoundation/p0-*')
```

No commit was created, so `main` cannot be broken by this phase.

### 4.7 Exit criteria

- ≥ 8 `refoundation/p0-*` tags exist on the remote and are visible via `git ls-remote --tags origin`.
- `origin/rescue/phoenix-001-local-33` equals the local branch head (33 commits rescued).
- The bundle verifies and its sha256 is recorded in `frozen_inputs.json`.
- `frozen_inputs.json` exists and lists at least S-028 and S-029 with protocol + input-DB hashes.
- `python -m medradar selftest` still exits 0.

### 4.8 Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Pushing 33 local commits accidentally updates PR #23 | reviewer confusion, not data loss | push to `rescue/*`, never to the PR branch (0.1) |
| A tag push is rejected by branch protection | Phase 0 blocked | tags are not branches; if rejected, use annotated tags on `rescue/*` branches instead |
| Local branch names differ from `_FACTS.md` | 0.2 loop silently does nothing | re-run P-4 and reconcile before 0.2 |
| A worktree holds `main` | Phase 3 rebase confusion | record (0.4) and close unneeded worktrees before Phase 3 |

---

## 5. Phase 1 — Governance spine (2 days, 2026-11-13 → 11-14)

### 5.1 Goal

Make the project's state **machine-readable** and make the four rules that this programme depends on
**fail in CI** instead of living in a document. After this phase, a change that violates a rule is rejected
by a workflow, not by a reviewer's memory.

### 5.2 Prerequisites

Tag `refoundation/p0`. Nothing else.

### 5.3 Work items

**1.1 Declare one authoritative state file.** `[FACT]` `research/STATE.json` (schema
`medradar.foresight.state.v2`) is the only state file that tooling writes (`tools/update_state_cycle33.py`,
`…cycle37/38/39`, `tools/update_state_final.py`) and it already carries `phase`, `cycle`, `last_completed_cycle`,
`working_tree`, `last_verified`, `layer_status`. Declare it the single source of project state in
`research/STATE.json`'s own header field and in `.github/pull_request_template.md`.
`[FACT]` Competing sources exist: `research/AUDIT.json`, `research/FINAL_AUDIT.json`,
`research/BACKLOG.yaml`, `tools/round_end.json` (`_FACTS.md` C8). Do **not** delete them; demote them:
add `"state_authority": "research/STATE.json"` to each JSON and a header comment to the YAML.

**1.2 Add the study registry (empty, then populated in Phase 4).** Create
`research/studies/INDEX.json`:

```json
{"schema": "medradar.studies.index.v1",
 "updated_at": "2026-11-13T00:00:00Z",
 "studies": []}
```

**1.3 Write `tools/check_governance.py`** (~200 lines, stdlib only). It implements the four gates and exits
non-zero with a per-gate report. Gates:

| Gate | Rule | Prevents |
|---|---|---|
| **G1 contract-version** | any file under `medradar/atlas/evidence/` or `medradar/evidence/` that defines/consumes a `SCHEMA_ID` must reference the version declared in `medradar/atlas/evidence/schema.py::SCHEMA_ID` | the v1/v2/v3 sprawl that produced three record shapes |
| **G2 taxonomy-version** | if any of `config/tracks_device.json`, `config/tracks_drug.json`, `config/product_code_tracks.json`, `config/product_families.json`, `config/product_catalog_zh.json` changed, `docs/TAXONOMY.md` (new, 20 lines: id, date, sha256 list) must change in the same commit | the "unversioned taxonomy = semantic leakage channel" named in `research/LAYERS.md` |
| **G3 generated-blob** | files matching `docs/dashboard.html`, `docs/*.png` (except `docs/preview.png`), `docs/metrics.json`, `docs/summary.csv`, `docs/report_*.md` may not be *modified* by a PR until Phase 6 moves them to build output | another 3.35 MB binary diff in review |
| **G4 frozen-artifact** | every artifact listed in `research/studies/INDEX.json` must exist with the recorded sha256; every protocol file must match its freeze hash | silent edits to published results |

**1.4 Wire the gates into `.github/workflows/ci.yml`.** `[FACT]` the current workflow has three jobs
(`test` on py3.10/3.11/3.12, `data-stats`, `windows-install`) and runs `python -m medradar selftest`,
`scripts/check_install.py`, the offline demo. Add one job, do not restructure:

```yaml
  governance:
    name: governance gates (contract / taxonomy / generated / frozen)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }          # G3/G4 need history
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: python -m pip install .
      - run: python tools/check_governance.py --all --strict
```

**1.5 Make the verifier a gate, not a narrative.** `[FACT]` `verifier/v1/verify.py` already runs the full
pytest suite in a subprocess and recomputes numbers from stored artifacts, and `verifier/runs/001…013` are
committed run records. Add `python verifier/v1/verify.py` to the same job, writing to `verifier/runs/014-*.{meta,txt}`.

**1.6 Reconcile the four state files' *claims* with reality, once.** Specifically `_FACTS.md` C1
(`pyproject.toml` = `0.5.0` vs README "stable core through v0.2.2") and C2 (GitHub licence "Other" vs MIT).
Work item: bump `pyproject.toml` `version` to a value consistent with `CHANGELOG.md` (or fix the CHANGELOG),
and add an SPDX header to `LICENSE` so GitHub classifies it as MIT. Two one-line changes, both reversible.

**1.7 Add `docs/refoundation/` to the repo** (this audit's deliverables) with a `README.md` index, so the
programme has a landing page and the `_evidence/` files are not orphaned.

### 5.4 Owner

Architect (this role). 2 days.

### 5.5 Verification commands

```bash
python -m medradar selftest                      # I1, unchanged
python tools/check_governance.py --all --strict  # expect exit 0, 4 gates reported
python verifier/v1/verify.py                     # expect exit 0
```

**Proof that the gates actually bite** (do this, do not assume): on a scratch branch,
`echo '{}' > config/tracks_device.json` and confirm G2 fails; add a byte to `docs/dashboard.html` and
confirm G3 fails; change one protocol file and confirm G4 fails. Revert the scratch branch afterwards.

### 5.6 Rollback

Phase 1 is one PR with one merge commit (no squashing, so the individual work items stay visible):

```bash
git -C <REDACTED_LOCAL_PATH> tag -a refoundation/p1-pre  <merge-base-sha>  -m "before Phase 1"
git -C <REDACTED_LOCAL_PATH> revert -m 1 <phase1_merge_sha>
git -C <REDACTED_LOCAL_PATH> push origin main
```

`[RECOMMENDATION]` Keep `tools/check_governance.py` in the revert (it is additive and harmless); if it must
go too, revert its own commit separately. The CI job is the only thing that can make `main` red, so it is
the first thing to revert.

### 5.7 Exit criteria

- `python tools/check_governance.py --all --strict` exists, passes on `main`, and **fails** on the three
  deliberate-breach branches (G2, G3, G4).
- `.github/workflows/ci.yml` has a `governance` job; it is green on `main`.
- `research/STATE.json`, `research/AUDIT.json`, `research/FINAL_AUDIT.json`, `research/BACKLOG.yaml`,
  `tools/round_end.json` all name `research/STATE.json` as the state authority.
- `research/studies/INDEX.json` exists and is valid JSON.
- `pyproject.toml` version and `LICENSE` SPDX header reconciled (C1, C2 closed).
- Tag `refoundation/p1` on the merge commit.

### 5.8 Risks

| Risk | Impact | Mitigation |
|---|---|---|
| A gate is too strict and blocks legitimate work | team bypasses governance entirely | start with `--strict` on 4 rules only; every new rule needs a test proving a real past defect it would have caught |
| `fetch-depth: 0` slows CI | minor | one job only; `fetch-depth: 1` for the rest |
| Bumping the version breaks the demo snapshot path | I1 red | `python -m medradar demo` is already in CI; it will catch it |
| Someone edits a frozen artifact during the phase | I2 broken | G4 exists from the moment the phase merges; run it once locally before merging |

---

## 6. Phase 2 — Evidence contract + identity, absorbing ATLAS (5 days, 2026-11-15 → 11-19)

### 6.1 Goal

Land **one** evidence contract and **one** identity resolver on `main`, and prove them end-to-end with a
single vertical slice. This is the phase that converts the architecture from a diagram into a running path.

### 6.2 Prerequisites

Tag `refoundation/p1`. `[FACT]` #28 `foundation/atlas-001` is 4 commits ahead of `main`, 0 behind, and adds
70 files with 18,648 insertions and **no deletions** (`git diff --stat origin/main...origin/foundation/atlas-001`)
— the lowest-risk merge in the repository.

### 6.3 Work items

**2.1 Rebase and merge #28.**
```bash
git -C <REDACTED_LOCAL_PATH> fetch origin && git -C <REDACTED_LOCAL_PATH> rebase origin/main foundation/atlas-001
python -m medradar selftest
python -m unittest tests.test_atlas_evidence tests.test_atlas_identity tests.test_atlas_db \
                  tests.test_atlas_connectors tests.test_atlas_research -v
python tools/verify_atlas.py
git -C <REDACTED_LOCAL_PATH> merge --no-ff foundation/atlas-001 -m "feat(atlas): evidence, identity and graph foundation"
```
`[RECOMMENDATION]` Merge with `--no-ff` so the 4 commits stay reviewable and the merge is a single revert
target.

**2.2 Promote the contract, keep the path.** Create `medradar/evidence/__init__.py` (~40 lines) that
re-exports `make_evidence`, `validate_evidence`, `require_valid`, `canonical_key`, `is_independent`,
`canonical_json`, `sha256_json`, `EVIDENCE_TYPES`, `LICENCE_STATUSES`, `IDENTITY_STATUSES`,
`RELATION_STATUSES`, `QUALITY_FLAGS`, and the time helpers. No logic. `[FACT]` the implementations live in
`medradar/atlas/evidence/{schema,timeq}.py`; the shim gives the contract an owner-neutral import path.

**2.3 Add the v2 delta (the four `# NEW` functions of `ARCHITECTURE_TO_BE.md` §15).** In the existing
modules, not new ones:

| Function | File | Size | What it does |
|---|---|---|---|
| `validate_v2(record) -> ValidationResult` | `medradar/atlas/evidence/schema.py` | ~120 LOC | merges `validate_evidence` + `LicencePolicy`; returns `errors`/`warnings`/`LicenceTag` |
| `read_v1_as_v2(record) -> dict` | same | ~60 LOC | lifts a stored `medradar.atlas.evidence.v1` row to the v2 shape; lossless |
| `taxonomy_version(paths=None) -> str` | `medradar/atlas/identity/normalize.py` | ~40 LOC | sha256 over the sorted taxonomy files → `tracks-YYYY-MM-DD` |
| `assert_no_leakage(*, records, as_of, basis, label_evidence_ids)` | `medradar/intelligence/leakage.py` (new file, existing package) | ~80 LOC | Gate 2; raises `LeakageError` listing offenders |

`[FACT]` `medradar/intelligence/evaluation/leakage_audit.py` already exists and reports leakage classes;
`assert_no_leakage` must **call** it rather than re-implement it. If the call does not fit, the fit is the
work item.

**2.4 Promote CONVERGENCE's three governance pieces early** (they are needed by Phases 4–6 and are already
written and tested on #30):
- `medradar/integration/licence.py` → `medradar/integration/licence.py` (unchanged; brings `LicencePolicy`,
  `LicenceError`, `check_ingestible`, fail-closed `DEFAULT_POLICY`)
- `medradar/integration/clock.py` → `medradar/integration/clock.py` (unchanged; brings `build_time_block`
  with `BASIS_*` constants)
- `config/convergence/licence_policy.json` → `config/convergence/licence_policy.json`

`[RECOMMENDATION]` Do this with `git checkout integration/convergence-001 -- <paths>` **plus** its tests
(`tests/convergence/**`), in their own commit, so a later revert of the CONVERGENCE merge does not remove
them.

**2.5 Wire Gate 1 into the writer.** In `medradar/atlas/store.py::append_evidence`, replace the bare
`ev.validate_evidence(record)` call with `validate_v2(record, policy=...)` and refuse on errors. This is the
first place the licence policy becomes load-bearing. `[FACT]` the current method already validates and
raises `EvidenceError`, so the change is a substitution, not a restructure.

**2.6 Add `medradar/intelligence/dataset.py`** (~200 LOC): `export_snapshot(*, dataset_id, as_of,
contract_version, out_dir, filters)` → writes `manifest.json` + `part-*.jsonl.gz` + `excluded.jsonl.gz`, and
`load_snapshot(manifest_path)`. `[FACT]` `medradar/tkg/export.py` is the existing prototype of the same
idea; copy its manifest discipline.

**2.7 Create `data/evidence/` and prove idempotency.** One connector (#28 ships
`medradar/atlas/connectors/openfda_510k.py`) run twice over the same fixture must produce: 1
`collection_runs` row per run, identical `raw_objects` content hash, **no** new `evidence` version. This is
the property that makes re-collection safe.

**2.8 The vertical slice (the phase's real deliverable).** One command produces, from a fixture, the whole
chain:

```
fixture JSON → RawPayload → CAS file → EvidenceRecord(v2) → validate_v2 → append_evidence
            → IdentityClaim (candidate, gated) → export_snapshot → manifest.json
            → a count with {tier, coverage, limitations, licence_summary}
```

Add `tests/test_vertical_slice.py` asserting exactly those seven steps and that the exported JSONL
round-trips to an equal canonical hash.

### 6.4 Owner

Evidence owner (architect +1 if available). 5 days.

### 6.5 Verification commands

```bash
python -m medradar selftest                                   # I1: must be >= 1,074 and green
python -m unittest tests.test_atlas_evidence tests.test_atlas_identity -v
python -m unittest tests.test_vertical_slice -v
python -m unittest tests.test_leakage_gate -v
python tools/check_governance.py --all --strict               # G1 now covers the contract version
python tools/verify_atlas.py                                  # #28's own acceptance harness
python -c "from medradar.evidence import validate_evidence, require_valid; print('ok')"
python -m medradar atlas --help                               # CLI still resolves
```

### 6.6 Rollback

```bash
git -C <REDACTED_LOCAL_PATH> tag -a refoundation/p2-pre <sha-of-p1> -m "before Phase 2"
git -C <REDACTED_LOCAL_PATH> revert -m 1 <atlas_merge_sha>        # removes #28 wholesale
```

The v2 delta (2.3), the licence/clock promotion (2.4) and the slice (2.8) are separate commits and can be
reverted individually or kept. `[RECOMMENDATION]` Prefer reverting *forward* (fix the offending commit)
over reverting the merge; the merge revert exists for the case where ATLAS itself is judged unfit.

### 6.7 Exit criteria

- `main` contains `medradar/atlas/**`, `medradar/evidence/**`, `medradar/integration/{licence,clock}.py`,
  `config/convergence/licence_policy.json`.
- `tests/test_vertical_slice.py` passes and asserts the seven-step chain.
- Running the same fixture collection twice creates exactly one evidence version (idempotency proven).
- `validate_v2` rejects a record whose `licence.status = "unknown"` (fail-closed proof) and accepts a
  `public_domain` one.
- `assert_no_leakage` fails a synthetic record whose `source_public_at > as_of` (Gate-2 proof).
- `python -m medradar selftest` ≥ 1,074 tests, exit 0.
- Tag `refoundation/p2`.

### 6.8 Risks

| Risk | Impact | Mitigation |
|---|---|---|
| ATLAS's `timeq.build_time` defaults `first_observed_at` from `fetched_at` | fabricated observation history for imported data | §8.3 of the architecture: adopt CONVERGENCE's strict behaviour for foreign evidence; add a test asserting the default is *not* applied when a basis says unknown |
| Identity pilot labels are not genuinely human-adjudicated | `confirmed` status over-claims | ship `candidate`-gated; do not change the ladder until the owner answers §21 Q1 |
| The v2 delta grows scope | phase slips | hard cap: the four functions, nothing else; anything else becomes Phase 3+ |
| Two writers to `data/evidence/` | corruption | single-writer lease (observatory's pattern) applied to the evidence store in 2.7 |

---

## 7. Phase 3 — Product stack: rebase and merge #12 → #13 → #14 (4 days, 2026-11-20 → 11-23)

### 7.1 Goal

Put the product read model, the web app and the acquisition ledger on `main` **once**, in dependency order,
with the duplicated blobs merged only once and with `main` green after each of the three merges.

### 7.2 Prerequisites

Tag `refoundation/p2` (the product stack's read model will consume the evidence store instead of
re-deriving from S1 where cheap). Preflight P-5 must show the five identical `product/store.py` blobs.

### 7.3 Work items

**3.1 Confirm the inheritance, so nobody "de-duplicates" by hand.** `[FACT]` `medradar/product/store.py` is
blob `3c603e4ab9d7…` on #12/#13/#14/#15/#16 because
`git merge-base --is-ancestor origin/feat/medradar-2.0-mvp origin/feat/observatory-reliability-v1` exits 0 —
the product files are *inherited* down a linear stack, not copied. `[RECOMMENDATION]` The operative rule is
therefore **merge parent-before-child and never the reverse**; no file has to be dropped, and a rebase that
"removes" an inherited file would be a defect. Record that rule in `.github/pull_request_template.md`
("child branches must be merged after their base; inherited files must not be re-added by hand").

**3.2 Rebase #12 onto `main` and resolve the three conflicts that must exist.**
`[FACT]` #12 touches `README.md` (+31), `pyproject.toml` (+15/-…), `medradar/__main__.py` (+18),
`.github/workflows/ci.yml` (+20), and adds `medradar/product/**`, `medradar/web/**`, `web/**`,
`tests/test_product_*`, `docs/PRODUCT_*`, `scripts/product_e2e.cjs`.
`[FACT]` `_FACTS.md`/Lead evidence: README has two competing blobs and `pyproject.toml` three.
Conflict policy:
- `pyproject.toml`: keep main's identity fields, take #12's `web` extra and `share/medradar/web` data-files,
  keep `version` from Phase 1. Never take a *different* version string from a branch.
- `README.md`: main wins for the shipped-features section; #12's product section is inserted, not replacing.
  The README redesign is `README_REDESIGN_PROPOSAL.md`'s job (comms lead), so **do not rewrite the README
  here** — only merge mechanically.
- `medradar/__main__.py`: main's subparsers must all survive; #12 adds `web`. Verify with
  `python -m medradar --help | Select-String web`.

```bash
git -C <REDACTED_LOCAL_PATH> fetch origin
git -C <REDACTED_LOCAL_PATH> switch -c merge/p3a-medradar-2.0 origin/main
git -C <REDACTED_LOCAL_PATH> merge --no-ff origin/feat/medradar-2.0-mvp
# resolve the three files by hand, then:
python -m medradar selftest
python -m unittest tests.test_product_store tests.test_product_analyst tests.test_product_statistics \
                  tests.test_product_api -v
python -m medradar --help
```

**3.3 Merge #12** (`--no-ff`), tag `refoundation/p3a`, then repeat for #13.

**3.4 Merge #13 (`feat/live-observatory-v1`).** `[FACT]` its incremental content vs #12 is
`medradar/observatory/**` (25 modules incl. `ledger.py` 1,487 lines, `adapter.py`, 3 adapters,
`prospective.py`, `scheduler.py`, `runner.py`), `medradar/product/{observatory,prospective}.py`,
`medradar/web/routes_observatory.py`, `.github/workflows/observatory.yml`, `docs/LIVE_OBSERVATORY*`,
`docs/observatory/evidence/**`, `scripts/observatory_*`.
The product and web files it re-adds are **identical blobs** to #12's — after the rebase they must show as
already-present, i.e. `git diff --stat origin/merge/p3a-medradar.....origin/feat/live-observatory-v1` should
list only the observatory additions. If it lists `medradar/product/store.py`, the rebase went wrong.

```bash
git switch -c merge/p3b-live-observatory origin/merge/p3a-medradar-2.0
git merge --no-ff origin/feat/live-observatory-v1
python -m medradar selftest
python -m unittest tests.test_observatory_core tests.test_observatory_api -v   # names as shipped by #13
python -m medradar observatory status
python -m medradar.web --help                                                   # product server (from #12)
```

**3.5 Merge #14 (`feat/observatory-reliability-v1`).** `[FACT]` increments: `deploy/systemd/**`,
`deploy/windows/**`, `docs/{DEPLOYMENT,BACKUP_AND_RECOVERY,HEALTH_AND_VALIDATION,RELIABILITY_*,
CONTINUOUS_VALIDATION_PROTOCOL}.md`, `docs/reliability/evidence/**`, backup/restore/lease code, and a much
larger `medradar/__main__.py` CLI surface (`observatory status|sources|sync|backfill|watch|pause|resume|
replay|reconcile|backup|restore|audit|health|validate|deploy-status|lock|phase`).
This is also the phase where the **single-writer lease** becomes real — verify it:

```bash
git switch -c merge/p3c-reliability origin/merge/p3b-live-observatory
git merge --no-ff origin/feat/observatory-reliability-v1
python -m medradar selftest
python -m medradar observatory lock status
python -m medradar observatory health
python -m medradar observatory backup --help && python -m medradar observatory restore --help
```

**3.6 Prove the CLI surface is additive.** Snapshot `python -m medradar --help` before and after; the diff
must contain only additions. Any removed subcommand is a regression for legacy users.

**3.7 Do not publish yet.** Pages must still build from the *Phase 0* `docs/`; #12–#14 add `docs/product/*.png`
and `docs/observatory/evidence/*.json` (large), which is acceptable as evidence but must not be regenerated.

### 7.4 Owner

Product owner (with the architect reviewing the merge commits). 4 days.

### 7.5 Verification commands

```bash
python -m medradar selftest                       # I1: no test may be removed; count only grows
python -m medradar --help                         # all legacy subcommands present
python -m medradar demo                           # offline demo still works (CI job)
python scripts/check_install.py                   # wheel resolves config + web data-files
python -m medradar observatory status             # real ledger path, no exception
python -m medradar.web --help                  # optional extra path reports the missing uvicorn, exit 2 not a crash
python tools/check_governance.py --all --strict
```

`[RECOMMENDATION]` `scripts/product_e2e.cjs` needs Node; keep it **out** of the required CI gate (it is not
in `pyproject.toml` and Node is not a declared dependency) and run it manually once, recording the output in
the merge commit message.

### 7.6 Rollback

Three independent merge commits, each its own revert target and each preceded by a tag:

```bash
git -C <REDACTED_LOCAL_PATH> tag -a refoundation/p3c-pre <sha-before-3.5>
git -C <REDACTED_LOCAL_PATH> revert -m 1 <p3c_merge_sha>      # back to #13 only
git -C <REDACTED_LOCAL_PATH> revert -m 1 <p3b_merge_sha>      # back to #12 only
git -C <REDACTED_LOCAL_PATH> revert -m 1 <p3a_merge_sha>      # back to main-without-product
```

Order matters: revert #14 first, then #13, then #12 — reverting an inner merge before an outer one will
conflict. `[RECOMMENDATION]` If only one is faulty, revert that one; do not cascade.

### 7.7 Exit criteria

- `main` has `medradar/product/**`, `medradar/observatory/**`, `medradar/web/**`, `web/**`, `deploy/**`.
- `python -m medradar selftest` green, test count ≥ pre-Phase-3 count (record both numbers).
- `python -m medradar observatory status` and `… health` exit 0 against a scratch data dir.
- `python -m medradar --help` is a strict superset of the pre-Phase-3 output.
- Tags `refoundation/p3a`, `p3b`, `p3c` exist.
- `git diff origin/main...origin/feat/observatory-reliability-v1 --stat` is now empty for `medradar/product/**`
  (proving the inheritance chain held and nothing was re-added by hand).

### 7.8 Risks

| Risk | Impact | Mitigation |
|---|---|---|
| 72k lines land with unknown runtime behaviour | `main` broken | merge one branch at a time; each has its own tests; `--no-ff` keeps revert granular |
| README/pyproject conflict resolved differently each time | three versions again | conflict policy fixed in 3.2 and *written into the PR template* |
| Observability CLI introduces a network path | breaks offline CI | CI already asserts offline; run `selftest` first, it is the canary |
| `docs/` grows by megabytes of evidence JSON | slow clones, Pages bloat | those files are evidence (keep); only *generated* HTML moves out (Phase 6) |
| The lease is not actually enforced | two writers on one DB | 3.5 exercises `lock status`; add a test that a second lease acquisition is refused |

---

## 8. Phase 4 — Study re-homing: S-028 / S-029 / PHOENIX / S-031 (3 days, 2026-11-24 → 11-26)

### 8.1 Goal

Land the frozen studies on `main`, relocate them into the target layout **without changing a single byte**,
and register them in `research/studies/INDEX.json` so the app (Phase 6) and CI (Phase 1 G4) can find them.

### 8.2 Prerequisites

Tag `refoundation/p3c` (so `research/studies/` has a home and `main` already carries #14, which #15/#16 are
based on).

### 8.3 Work items

**4.1 Merge #15 and #16 in either order.** `[FACT]` verified: #15 adds only
`research/studies/graph_early_signal_s028/**` (86 files, +114,442) and #16 only
`research/studies/relation_network_s029/**` (205 files, +133,237) relative to #14. Zero overlap, zero
`medradar/` changes.

```bash
git switch -c merge/p4a-s028 origin/main
git merge --no-ff origin/research/s028-temporal-graph-early-signal
python -m medradar selftest                 # must be byte-identical in result to pre-merge

git switch -c merge/p4b-s029 origin/merge/p4a-s028
git merge --no-ff origin/research/s029-evidence-based-relations
python -m medradar selftest
```

**4.2 Relocate by `git mv` only.** `[FACT]` Before scripting this: **5 of #16's 205 incremental paths and
several of #29's carry non-ASCII (German umlaut) filenames** under `data/raw/` (e.g.
`ctgov_draeger_dräger.json.gz`). `git diff --name-only` quotes and octal-escapes such paths unless
`core.quotepath=false`; a naive `git mv $(git diff --name-only …)` loop will fail or corrupt them. Use
`git -c core.quotepath=false …` in every scripted move, and verify with a byte-for-byte `git ls-tree`
comparison afterwards. Recorded in `_evidence/tobe/verified_invariants.json`.

Target layout:

| From (`origin/research/...`) | To (`main`) | Rule |
|---|---|---|
| `research/studies/graph_early_signal_s028/**` | `research/studies/S-028/graph_early_signal/**` | `git mv`; bytes unchanged |
| `research/studies/relation_network_s029/**` | `research/studies/S-029/relation_network/**` | `git mv`; bytes unchanged |
| `research/atlas/reports/**`, `research/atlas/samples/**` (from #28) | `research/atlas/**` (already there) | no move |
| PHOENIX trees (#23–#26) | `research/studies/PHOENIX-00x/**` | only if they are merged; otherwise register as `external` |
| S-031 tree (#22) | `research/studies/S-031/**` | **freeze first**: create the missing `PROTOCOL.json` from its committed protocol text before any move |

`[RECOMMENDATION]` Keep the study-internal structure exactly as it is (`code/`, `artifacts/`, `data/`,
`*.md`). Do not "tidy" filenames: every report in the study cites its own artifacts by relative path, and
`REPRODUCE.md` contains absolute commands.

**4.3 Prove the move is non-destructive.** For every artifact file, the blob hash before and after must be
equal. Make this a script (`tools/check_frozen.py`, ~120 lines) so it is repeatable:

```bash
# before the move, for each relocated file
git rev-parse "origin/research/s028-temporal-graph-early-signal:research/studies/graph_early_signal_s028/artifacts/prereg_freeze.json"
# after the move
git rev-parse "main:research/studies/S-028/graph_early_signal/artifacts/prereg_freeze.json"
# must be the same 40-hex sha
```

**4.4 Write `PROTOCOL.json` per study** (the `StudyProtocol` of `ARCHITECTURE_TO_BE.md` §10.2). It is
**derived** from the study's own committed text — for S-028, from `PRE_REGISTRATION.md`,
`HYPOTHESIS_REGISTRY.md`, `artifacts/prereg_freeze.json`, `artifacts/prereg_freeze_amendment1.json`, and
`REPRODUCE.md`'s seeds. Do not invent a hypothesis or a decision rule that the study does not state; if a
field is unknown, write `null` and list it in `open_questions`.

**4.5 Write `RUNS.json` per study** — append-only list of `StudyRun` records reconstructed from the committed
artifacts (`artifacts/frozen_validation.json`, `statistical_validation.json`, `run_main.log`,
`comparison_table.json`). `[FACT]` S-028 has `artifacts/run_main.log` (14,400 bytes) and
`artifacts/frozen_validation.json`, so the run record is reconstructible.

**4.6 Populate `research/studies/INDEX.json`** (created in Phase 1.2) with one entry per study:
`{study_id, title, status: frozen, protocol: "…/PROTOCOL.json", protocol_sha256, runs: "…/RUNS.json",
headline: "null result"|"…", branch, tags: ["refoundation/p0-frozen-…"]}`.

**4.7 Freeze, do not improve.** Write a one-paragraph `FROZEN.md` in each study directory: what the study
claims, which commit produced it, and the sentence "This directory is frozen; corrections are new studies,
not edits." This is the social enforcement of I2.

**4.8 Do not run the studies.** `[FACT]` S-028 reads
`<REDACTED_LOCAL_PATH> (289,443,840 bytes, sha256 `dd241bfe…`) by
absolute path, and `verify_frozen_db` refuses if it differs. Re-running is out of scope and would require
that exact file. Record its hash in `frozen_inputs.json` (Phase 0.6) as `[UNVERIFIED]` availability.

### 8.4 Owner

Research registrar (with the architect). 3 days.

### 8.5 Verification commands

```bash
python tools/check_frozen.py --all            # every artifact hash equals its recorded value
python tools/check_governance.py --all --strict   # G4 now covers the new INDEX.json
python -m json.tool research/studies/INDEX.json > $null; echo $?    # valid JSON
python -m medradar selftest
git log --oneline -5 -- research/studies/S-028    # expect only merge + git mv + metadata commits
```

### 8.6 Rollback

The merges and the move are separate commits, so:

```bash
git revert <relocation_commit>                 # restores the pre-move paths, keeps the studies on main
git revert -m 1 <p4b_merge_sha>                # removes S-029
git revert -m 1 <p4a_merge_sha>                # removes S-028
```

`[RECOMMENDATION]` Never `git reset --hard` a study branch. If a relocation is wrong, revert it and redo the
`git mv`; the artifacts' blobs are untouched either way, which is the whole point.

### 8.7 Exit criteria

- `research/studies/INDEX.json` lists every frozen study that is on `main`, and nothing that is not.
- `tools/check_frozen.py --all` passes; specifically S-028's `prereg_freeze.json` blob is unchanged from
  `origin/research/s028-temporal-graph-early-signal`.
- Every relocated study has `PROTOCOL.json`, `RUNS.json`, `FROZEN.md`.
- No study file content changed: `git diff --stat` between the merge and the move shows **only** renames
  (`R100`) and the three new metadata files per study.
- Tag `refoundation/p4`.

### 8.8 Risks

| Risk | Impact | Mitigation |
|---|---|---|
| A `git mv` is done with `write`+`delete` instead of `mv` | blob rewritten, freeze hash broken | 4.3's script is the gate; also `git diff --find-renames --stat` must show `R100` |
| Someone "fixes a typo" in a frozen report | I2 broken, results unreproducible | `FROZEN.md` + G4; the typo goes in an erratum, not the file |
| `PROTOCOL.json` invents a hypothesis | scientific misrepresentation | 4.4: `null` + `open_questions`, never a guess |
| #22 (600 files) is merged without a protocol | an unfreezable study on `main` | #22 stays out until `PROTOCOL.json` exists; register it as `external` in the index meanwhile |
| The input database is gone | study not re-runnable, only citable | already the case; record the hash and cite it |
| **Non-ASCII filenames break a scripted `git mv`** (`[FACT]` 5 in #16, several in #29) | corrupted or lost raw-data files inside a frozen study | 4.2: `core.quotepath=false` everywhere; verify with `git ls-tree -r` before/after and compare blob hashes |

---

## 9. Phase 5 — Global data and rights gating (#27 / #29) (3 days, 2026-11-27 → 11-29)

### 9.1 Goal

Bring the global source corpora onto `main` **behind the licence gate**, and make redistribution a property
that the build enforces rather than a promise in a document.

### 9.2 Prerequisites

Tag `refoundation/p4`. Phase 2.4 promoted `medradar/integration/licence.py` +
`config/convergence/licence_policy.json` and Phase 2.5 wired Gate 1 into `append_evidence`.

### 9.3 Work items

**5.1 Establish the policy before the data.** Audit the source list and write the authoritative
`config/convergence/licence_policy.json` (`schema: medradar.licence_policy.v1`) with, per source:
`{may_query, may_ingest, may_redistribute, attribution_required, licence_status}` plus
`quarantine.source_ids`. Seed it from what already exists:
- `[FACT]` `medradar/integration/licence.py::DEFAULT_POLICY` (fail-closed fallback, `un_comtrade` quarantined)
- `[FACT]` `research/horizon/DATASETS/industry/LICENCE_EVIDENCE.json` and the per-dataset
  `research/horizon/DATASETS/*/PROVENANCE.json` (HORIZON already recorded licence evidence per dataset)
- `[FACT]` `config/sources.json` on `main` (the existing source registry)
`[RECOMMENDATION]` The policy must be a *table*, not a rule: a reviewer must be able to answer "may we
publish a Eurostat Comext cell?" by reading one line.

**5.2 Merge #27 (`research/data-expansion-001`).** `[FACT]` 916 files, +260,389, all under `research/`.
No package code, so it cannot break `selftest`. Merge with `--no-ff`, then immediately run the licence gate
over its manifests.

**5.3 Merge #29 (`research/horizon-001`) — as data, not as code.** `[FACT]` 691 files, +692,975: connectors
under `research/horizon/CONNECTORS/{regulatory,patents,scholarly,industry}/`, datasets under
`research/horizon/DATASETS/**` with `PROVENANCE.json` per dataset, plus `research/horizon/ATLAS_HANDOFF.md`.
`[RECOMMENDATION]` Merge #29 but **do not promote `research/horizon/CONNECTORS/**` into `medradar/`** in
this phase. Promotion is a per-connector decision, made when that connector gains a licence-policy entry
and a `Normaliser` (§7.2 of the architecture). Until then it stays research code.

**5.4 Enforce redistribution at the two boundaries.** Two new filters, both small:
- **export boundary**: `medradar/intelligence/dataset.py::export_snapshot` must write records with
  `may_redistribute == false` to `excluded.jsonl.gz`, never to `part-*.jsonl.gz`, and must put a
  `licence_summary` block in `manifest.json`.
- **read-model boundary**: the product read model (`medradar/product/store.py`) must never surface a
  non-redistributable record. `[FACT]` today it reads `data/medradar.sqlite`, which has no licence column;
  therefore add a `source_id → may_redistribute` lookup and filter at query time rather than adding a column
  to the legacy schema.

**5.5 Add the licence tests.** `tests/test_licence_gate.py`, five assertions:
(a) deleting the policy file makes every source non-ingestible (fail-closed);
(b) `unknown` status is refused at Gate 1;
(c) `open_no_explicit_licence` is storable but absent from `part-*.jsonl.gz`;
(d) `quarantined_sources` are refused with a typed error;
(e) the export manifest's `licence_summary` sums to the record count.

**5.6 Record the global-source coverage honestly.** `[FACT]` `docs/DATA.md` already says
"US records are not global product/registration/R&D activity". Add a `docs/COVERAGE.md` generated from the
export manifests: per source, `{first_record, last_record, records, licence_status, may_redistribute}`.
This is the document that stops "global data" from being an overclaim.

### 9.4 Owner

Data-governance owner (with the architect). 3 days.

### 9.5 Verification commands

```bash
python -m medradar selftest
python -m unittest tests.test_licence_gate tests.test_leakage_gate -v
python tools/check_governance.py --all --strict
python -c "from medradar.integration.licence import LicencePolicy; p=LicencePolicy.load(); print(p.summary())"
# proof that a quarantined source cannot be ingested
python -c "from medradar.integration.licence import LicencePolicy; p=LicencePolicy.load(); \
           print(p.may_ingest('un_comtrade','open_licence'))"   # expect False
```

### 9.6 Rollback

```bash
git revert -m 1 <p5b_horizon_merge_sha>
git revert -m 1 <p5a_data_expansion_merge_sha>
git revert <licence_policy_commit>          # policy file is additive; reverting restores fail-closed default
```

`[RECOMMENDATION]` If a single source is mis-classified, **fix the policy file** (one line) rather than
reverting the merge; reverting #29 to correct one licence entry would lose a corpus.

### 9.7 Exit criteria

- `config/convergence/licence_policy.json` covers every `source_id` present in `config/sources.json` and in
  `research/horizon/DATASETS/*/PROVENANCE.json`; a test asserts no source is unlisted.
- The five licence tests pass.
- An export of a mixed source set produces `part-*.jsonl.gz` and `excluded.jsonl.gz` whose union equals the
  input count (no silent loss).
- `docs/COVERAGE.md` is generated and committed.
- Tag `refoundation/p5`.

### 9.8 Risks

| Risk | Impact | Mitigation |
|---|---|---|
| #29's 692,975 lines include third-party data whose licence is genuinely unknown | legal exposure | fail-closed default already treats `unknown` as non-ingestible; unknown sources stay out of `part-*` until proven |
| The policy table is written once and never maintained | drifts from reality | G-gate: a new `source_id` in `config/sources.json` without a policy row fails CI (add to `check_governance.py`) |
| Filtering at query time is slow on the legacy DB | app latency | the lookup is a small in-memory dict loaded once; measure before optimising |
| "Global data" claim outruns the evidence | reputational | `docs/COVERAGE.md` is generated from manifests, never hand-written |

---

## 10. Phase 6 — CONVERGENCE (#30) + app integration (4 days, 2026-11-30 → 12-03)

### 10.1 Goal

Land CONVERGENCE's glue **without its duplicate of ATLAS**, complete the app data boundary (tier envelope +
licence filter + run-id requirement), and turn `docs/` into build output so `main` is the single shipped
state end to end.

### 10.2 Prerequisites

Tags `refoundation/p2` (ATLAS on main) and `refoundation/p5` (#29 on main). Both are hard prerequisites
because #30 = ATLAS + HORIZON + glue.

### 10.3 Work items

**6.1 Merge #30 with a measured conflict surface, not a guessed one.** `[FACT]` Verified with
`git merge-base --is-ancestor` and a blob-by-blob `ls-tree` comparison of the two tips:

| Relation of #30 to #29 | Count | Merge consequence |
|---|---|---|
| `#28` **is** an ancestor of `#30` | — | every `medradar/atlas/**`, `tests/test_atlas_*`, `tools/*atlas*`, `config/atlas_*` path is already on `main` after Phase 2 → **no-op, do not "drop" anything** |
| `#29` is **not** an ancestor of `#30` | — | histories diverged; a real 3-way merge is required |
| paths present in both tips, **equal** blobs | **1,787** | merge cleanly, no conflict |
| paths present in both tips, **different** blobs | **6** | **the only real conflicts** |
| paths only in #30 | **155** | additions (`medradar/integration/**`, `config/convergence/**`, `research/convergence/**`, `docs/convergence/**`, `.github/workflows/convergence.yml`) |

The six divergent paths are exactly: `.gitignore`, `README.md`,
`research/horizon/EXPERIMENT_RESULTS.md`, `research/horizon/experiments/industry/EXP_H4_INDUSTRY.json`,
`research/horizon/reports/INDUSTRY_DATA_REPORT.md`, `research/horizon/reports/REGULATORY_FRONTIER_REPORT.md`.

```bash
git switch -c merge/p6-convergence origin/main
git merge --no-ff origin/integration/convergence-001
# expected conflicts: the six paths above — resolve by hand, then:
#   .gitignore  -> take the union (Phase 3/5 may have added entries)
#   README.md   -> main wins (comms lead's redesign is authoritative)
#   research/horizon/{EXPERIMENT_RESULTS.md, experiments/industry/EXP_H4_INDUSTRY.json,
#                     reports/INDUSTRY_DATA_REPORT.md, reports/REGULATORY_FRONTIER_REPORT.md}
#               -> take #30's version (it is the later revision of the same study) and record the
#                  blob change in the merge commit message; these are research prose, not frozen artifacts
git diff --stat origin/foundation/atlas-001..HEAD -- medradar/atlas | Measure-Object -Line   # must be 0
```

`[RECOMMENDATION]` Assert the inheritance claim mechanically after merging, in both directions:
```bash
git diff --stat origin/foundation/atlas-001..HEAD -- medradar/atlas   # expect empty (main's ATLAS unchanged)
git merge-base --is-ancestor origin/foundation/atlas-001 HEAD && echo "ATLAS inherited, not duplicated"
```
If the first command is non-empty, main's ATLAS was modified during the merge — investigate before proceeding.

**6.2 Keep only the glue.** The files that must survive from #30:
`medradar/integration/{__init__,__main__,adapter,cli,clock,contract,dedupe,demo,graph,licence,staging}.py`,
`config/convergence/**`, `tests/convergence/**`,
`.github/workflows/convergence.yml`, `docs/convergence/**`, `research/convergence/**`,
`tools/convergence/**`. `[FACT]` `licence.py` and `clock.py` were already promoted in Phase 2.4 — verify they
are the same blobs and keep main's.

**6.3 Complete the app data boundary.** Three changes in `medradar/product/store.py` +
`medradar/web/**` (the smallest place that can enforce the architecture):

| Change | Where | Rule |
|---|---|---|
| tier envelope | every numeric response object | `{value, tier, coverage, limitations, source_records, artifact_id, run_id}` per `ARCHITECTURE_TO_BE.md` §11.2 |
| licence filter | the store's query layer | a record with `may_redistribute == false` never reaches a response; the response carries `licence_summary` |
| run-id requirement | `detected`/`hypothesis` tiers | must carry `run_id` present in `research/studies/INDEX.json`, else the field is `null` and the tile renders "not available" |

Add `tests/test_app_contract.py`: (a) no bare number in any response (walk the JSON), (b) a
non-redistributable fixture record is absent, (c) a `detected` value without a registered run id is `null`.

**6.4 Turn `docs/` into build output.** `[FACT]` `docs/dashboard.html` is 3,350,819 bytes, `docs/metrics.json`
468,561, `docs/report_zh.md` 55,768, `docs/summary.csv` 68,460 — all generated, all committed, and Pages
builds from `main:/docs` (`build_type=legacy`). Work items:
- add `.github/workflows/pages.yml` that regenerates those files from an export snapshot and a
  `medradar report`/`dashboard` run, then deploys `docs/` (Pages artifact flow);
- remove the generated files from git in one commit, keep `docs/index.html`, `docs/preview.png`,
  `docs/.nojekyll` and the hand-written `docs/*.md` documentation;
- add a `docs/.gitignore` for the generated names so they cannot come back;
- **keep** the evidence directories (`docs/observatory/evidence/**`, `docs/reliability/evidence/**`,
  `docs/product/*.png`, `docs/atlas/**`) — they are evidence, not output.

`[RECOMMENDATION]` Do the removal in its own commit: `Phase 6.4: move generated docs to build output`. It is
the single riskiest-looking commit of the programme (a 3.35 MB deletion) and should be independently
revertible.

**6.5 Re-point the verifier.** Make `verifier/v1/verify.py` verify the *new* artifacts (export manifest
counts, frozen study hashes) in addition to the old experiment artifacts, without deleting old checks.

**6.6 Update the landing documentation.** `README.md` and `README.zh-CN.md` must stop claiming capabilities
that are not on `main`. This is the comms lead's `README_REDESIGN_PROPOSAL.md` applied — not rewritten here.
The only architectural requirement in this plan: the README must link the architecture document and state
the licence posture (`docs/COVERAGE.md`).

### 10.4 Owner

Architect (integration) + product owner (app boundary). 4 days.

### 10.5 Verification commands

```bash
python -m medradar selftest
python tools/check_governance.py --all --strict
python -m unittest tests.test_app_contract tests.test_licence_gate -v
python -m unittest discover -s tests/convergence -v
git diff --stat origin/foundation/atlas-001..HEAD -- medradar/atlas      # expect empty
python -m medradar observatory health
python -m medradar.web --host 127.0.0.1 --port 8765   # smoke: GET / returns 200, then stop
python tools/check_frozen.py --all
```

### 10.6 Rollback

```bash
git revert -m 1 <convergence_merge_sha>            # removes the glue, keeps ATLAS and #29
git revert <docs_build_output_commit>              # restores the committed generated files
git revert <app_contract_commit>                   # restores the unenveloped responses
```
`[RECOMMENDATION]` The `docs/` build-output commit is the one most likely to need rollback (Pages
configuration is outside the repo). Keep it isolated and revert it alone if Pages breaks; the architecture
does not depend on it.

### 10.7 Exit criteria

- `medradar/integration/**` and `config/convergence/**` are on `main`; `medradar/atlas/**` on `main` is
  byte-identical to `origin/foundation/atlas-001`.
- `tests/test_app_contract.py` passes: no bare numbers, licence filter effective, run-id gating works.
- `docs/` contains no generated HTML/CSV/JSON blob; Pages builds from the workflow and the preview URL
  returns the generated dashboard.
- `python -m medradar selftest` green; all five stores wired; `tools/check_frozen.py --all` passes.
- Tag `refoundation/p6` and a release tag `v1.0.0-refoundation` (the first tag since `v0.2.2`, which also
  resolves `_FACTS.md` C1).

### 10.8 Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Merging #30 re-introduces a divergent ATLAS | two identity authorities again | 6.1's `git diff` assertion is a hard gate; the merge is blocked until it is empty |
| Removing generated `docs/` breaks Pages the same day | public site down | do it in its own commit after the Pages workflow has run successfully on a branch |
| The tier envelope requires touching every route | schedule | start with the store's response builder (one function), not per-route |
| Run-id gating hides numbers the owner wants visible | product pushback | `null` + "not available" is the honest state; §21 Q3 of the architecture is the owner's decision point |

---

## 11. Cross-phase CI gate map

| Gate | Introduced | Phase 1 | Phase 3 | Phase 5 | Phase 6 |
|---|---|---|---|---|---|
| I1 `python -m medradar selftest` | existing | enforced | enforced | enforced | enforced |
| wheel/config resolution (`scripts/check_install.py`) | existing | enforced | enforced | enforced | enforced |
| G1 contract-version | Phase 1.3 | on (evidence only) | on | on | on |
| G2 taxonomy-version | Phase 1.3 | on | on | on | on |
| G3 generated-blob | Phase 1.3 | on (block) | on (allow evidence) | on | **relaxed** (files gone) |
| G4 frozen-artifact | Phase 1.3 | on (empty list) | on | on | on |
| G5 licence coverage | Phase 5.1 | – | – | on | on |
| G6 app contract (no bare numbers) | Phase 6.3 | – | – | – | on |
| `verifier/v1/verify.py` | Phase 1.5 | on | on | on | on |

`[RECOMMENDATION]` Every gate must be **proven to fail** on a deliberate breach before the phase that
introduces it can be tagged. A gate that has never failed is decoration.

---

## 12. Rollback master table

| Phase | Tag before | Rollback command | Data loss risk |
|---|---|---|---|
| 0 | — (nothing changed) | delete `rescue/*` refs and `p0-*` tags | none (additive) |
| 1 | `refoundation/p0-main-2026-11-12` | `git revert -m 1 <p1_merge>` | none (docs + one tool + CI job) |
| 2 | `refoundation/p1` | `git revert -m 1 <atlas_merge>` (+ individual commits) | none (all additions) |
| 3 | `refoundation/p2`, `p3a`, `p3b` | `git revert -m 1` **in reverse order** (`p3c → p3b → p3a`) | none; branch data intact on `origin/feat/*` |
| 4 | `refoundation/p3c` | `git revert <relocation>` then `-m 1 <merges>` | **frozen bytes preserved by `git mv` + revert**; the artifacts are never edited |
| 5 | `refoundation/p4` | `git revert -m 1 <p5b>` then `<p5a>`; fix policy in place instead | none; corpora stay in git history |
| 6 | `refoundation/p5` | `git revert -m 1 <convergence_merge>`; `<docs_commit>` separately | none; generated docs return if that commit is reverted |

**Universal rule.** There is no `git reset --hard`, no force-push, no branch deletion anywhere in this plan.
Every rollback is a forward revert commit, so the migration itself remains auditable.

---

## 13. Effort and calendar summary

| Phase | Days | Owner | Cumulative date | Independently shippable? |
|---|---|---|---|---|
| 0 Preserve & protect | 0.5 | owner | 2026-11-12 | yes (no change) |
| 1 Governance spine | 2 | architect | 2026-11-14 | yes |
| 2 Evidence contract + identity | 5 | evidence owner | 2026-11-19 | yes (vertical slice) |
| 3 Product stack #12→#13→#14 | 4 | product owner | 2026-11-23 | yes (3 separate merges) |
| 4 Study re-homing | 3 | research registrar | 2026-11-26 | yes |
| 5 Global data + rights | 3 | data governance | 2026-11-29 | yes |
| 6 CONVERGENCE + app | 4 | architect + product | 2026-12-03 | yes |
| **Total** | **21.5** | | | |

`[INFERENCE]` The critical path is Phase 2 → Phase 3 (the product stack cannot merge before the contract
exists if the read model is to consume it) and Phase 5 → Phase 6 (#30 needs #29). Phases 1 and 4 are
parallelisable with 2 and 5 respectively if a second person is available; Phase 0 is not optional and not
parallelisable.

`[RECOMMENDATION]` If only one phase can be funded, fund **Phase 2**. A single contract + resolver + gates
delivers most of the architectural value and leaves every other branch mergeable later; the product stack
without the contract is the status quo with more code.

---

## 14. Open questions for the owner

**Q1 — Phase 3 ordering.** Do you accept merging #28 *before* the visible product stack (#12–#14)? It
delays the product demo by ~5 days but makes the product read model consume real evidence instead of
re-deriving from the legacy table, and it makes #30's duplicate mechanically detectable.
*Default:* yes, #28 first.

**Q2 — #1, #21, and the PR-less base branch.** This plan proposes closing #1 (superseded by `main`'s
`frontier.py`) and retiring `integration/phase4-base` without merging #21. Both are destructive *decisions*
(not destructive git operations). Do you agree?
*Default:* close #1 with a note; leave #21 open but unmerged and unmaintained.

**Q3 — #22 (S-031, 600 files / +303,926).** It cannot be frozen until a `PROTOCOL.json` exists, and creating
one is research work, not migration work. Merge-with-`external`-status, or leave it out entirely?
*Default:* register as `external` in `research/studies/INDEX.json`; do not merge.

**Q4 — `docs/` as build output.** Confirm you are willing to lose "the dashboard is in the repo" in exchange
for a generated, licence-filtered site. This changes how Pages is published and is the one item where the
plan's benefit is mostly hygiene.
*Default:* yes, in Phase 6.4, as an isolated commit.

**Q5 — Who reviews the three Phase-3 merges?** 72k lines across three branches cannot be reviewed line by
line by one person. Do you accept "tests + governance gates + one architectural review per merge" as the
review standard?
*Default:* yes, with the merge commit messages recording the test counts and the `--stat` of what landed.

**Q6 — Is the 21.5-day estimate acceptable, or should the phases be cut to 3 (0, 1, 2) and the rest
deferred?** The programme's riskiest property is that it is long enough to lose momentum.
*Default:* run 0–2 as one sprint (7.5 days), then decide.

**Q7 — Does any production consumer depend on `data/medradar.sqlite` being written by collectors?** Phase 2
proposes that S1 becomes a projection fed from S3. If an external process reads S1 directly, the
transition needs a dual-write window.
*Default:* assume no external consumer; verify by grep before Phase 6.



