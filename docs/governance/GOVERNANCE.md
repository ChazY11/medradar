# MedRadar governance

**Status:** Phase-2 hardened MVP, solo-maintainer. **Owner:** `ChazY11`.
**Branch protection:** not applied — see [`BRANCH_PROTECTION_PLAN.md`](BRANCH_PROTECTION_PLAN.md).
**Scope:** consistency, provenance, claim discipline and rule-change accountability
for this repository. It is not a second pair of eyes and it does not decide
whether the science is right.

All gates are Python-standard-library only, need no network, and run identically
locally and in the `governance` workflow.

---

## 1. One source of truth: `PROJECT_STATE.yaml`

`PROJECT_STATE.yaml` at the repository root is the single hand-edited description
of the project: identity/mission, `main` head + date + version, test counts, data
snapshot, capability list with status, research studies with verdict/freeze/public
claim, open-work counts, governance status, a decision index, and an explicit
`not_claimed` list.

Everything derived is generated from it:

```text
PROJECT_STATE.yaml
        │  python tools/governance/gen_views.py
        ├── README.md                    (generated status block)
        ├── CHANGELOG.md                 (generated unreleased snapshot)
        └── docs/RESEARCH_INDEX.md       (whole file generated)
```

**The edit flow:** edit `PROJECT_STATE.yaml` → run
`python tools/governance/gen_views.py` → commit the regenerated views in the same
commit → run the gates before pushing.

The state describes **`main`**, not the branch. `main.head` must equal the
resolved `main.ref` (`origin/main`). On a pull request, `origin/main` is the PR's
base, so "the state matches main" is checked at the merge point; a PR started
after a merge carries the state update in its own diff. The `governance` workflow
therefore runs on `pull_request` (and manual dispatch), not `push` to `main`: a
post-merge run would be red by design until the next PR updates the state. `ci`
still covers `main` pushes.

### After `main` advances: `bump_state.py`

```bash
python tools/governance/bump_state.py --ref origin/main     # rewrite main block
python tools/governance/gen_views.py                        # regenerate views
```

`bump_state.py` derives the whole `main` block from the ref — head, short, commit
time, subject, version from that ref's `pyproject.toml`, tracked-file count,
workflow names — and sets `generated_at` to the ref's commit time (deterministic;
no wall clock). It preserves the hand-written comments and changes nothing else.
Use `--dry-run` to see the exact diff. A post-merge bot commit cannot maintain
strict equality (the commit that records the head changes the head), so the safe
automation is **pre-merge**: the PR carries the bump.

## 2. The six gates

| Gate | Command | Verifies | Blocks |
| --- | --- | --- | --- |
| State | `python tools/governance/check_state.py` | schema/sections; `main.head` vs `git rev-parse origin/main`; date/subject/version/tree/workflow counts; every referenced path; duplicate ids; decision and freeze ids exist; declared test counts vs the measurement artifact | a state file that is wrong about git, cites missing files/decisions/freezes, or claims an unmeasured test count |
| Views | `python tools/governance/gen_views.py` (`--check`) | README/CHANGELOG regions and `docs/RESEARCH_INDEX.md` are exactly the current state's output, with matching source/payload digests | stale generated views, hand-edited generated regions |
| Freeze | `python tools/governance/check_frozen.py --base origin/main` | per-file SHA-256 in `FROZEN.yaml` (including inside frozen directories), directory structure, and approved `rebalances:` vs the base ref | any frozen byte change, name-only edit, added/removed study file, or unapproved re-baseline |
| Licence | `python tools/governance/check_licence.py --base origin/main` | source patterns, positive `DATA_INVENTORY.yaml` coverage, content/magic-byte classification, untracked data files, PR-diff changes | an undeclared, moved, renamed or content-swapped data file; a restricted binary format outside synthetic fixtures; a RED-source file |
| Links | `python tools/governance/check_links.py` | relative Markdown links/images under `docs/**/*.md` resolve and stay inside the repo | moved/renamed/typo'd docs, broken generated links |
| Rule audit | `python tools/governance/check_rule_audit.py --base origin/main` | changes to the governance surface have a **new** rule-change record with an approved decision id | silently weakening CI or a gate |

Exit-code contract: **0** pass, **1** check failed, **2** configuration/usage
error (nothing verified). Every script supports `--help`; all gates support
`--json` and `--root`. `record_tests.py` is the maintenance companion for the
test-count artifact.

The `governance` workflow has six jobs (the gates above). Jobs that compare
against a base ref check out with `fetch-depth: 0` so `origin/main` exists.

## 3. Determinism and tamper detection

Generated output is reproducible: no wall clock, no network, no locale, no
unordered iteration. `generated_at` is a hand-maintained state field (or the ref
commit time when `bump_state.py` runs), so regenerating from the same state yields
the same bytes.

Each generated region records two digests:

```html
<!-- generated: do not edit by hand; regenerate with tools/governance/gen_views.py -->
<!-- source-sha256: <sha256 of PROJECT_STATE.yaml bytes> -->
<!-- payload-sha256: <sha256 of the generated markdown payload> -->
```

Region equal to expected → up to date. Region from the *current* source but with
different bytes → **hand-edited: FAIL**, even if a digest was recomputed. Older
source digest with self-consistent payload → stale, regenerate. Inconsistent
payload digest → **hand-edited: FAIL**. `gen_views.py` run twice writes nothing
the second time; the CI `views` job fails on `git diff`.

## 4. The YAML subset

No PyYAML dependency, including for tooling. `tools/governance/yamlmini.py`
implements exactly the subset the governance files use: one document; `#`
comments outside quotes; block mappings/sequences nested by spaces (tabs
rejected); plain/quoted scalars; `|`/`>` block scalars; booleans/null/ints/floats;
`[]`/`{}` empties; duplicate keys rejected. Flow collections, anchors/tags, merge
keys, multi-document files, tabs for indentation and multi-line quoted scalars are
rejected loudly with file and line.

## 5. Generated views: never hand-edit

* **README.md** — region between `<!-- BEGIN GENERATED: status -->` and
  `<!-- END GENERATED: status -->`.
* **CHANGELOG.md** — region between the `unreleased` markers.
* **docs/RESEARCH_INDEX.md** — whole file.

Commands: default run verifies and regenerates only stale views; `--check`
verifies without writing; `--init` bootstraps missing markers; `--write` force
regenerates (restoration only). Routine edits never need `--write`.

## 6. Frozen research artifacts (format 2)

`FROZEN.yaml` pins the scientific record with **per-file SHA-256 digests**:
pre-registered protocols/amendments, the Phase-0 report, both forecast sets, the
complete file manifest of the registered study directory
(`research/studies/early_signal_5firms`), the `research/forecasts/` directory (a
new forecast set is an unreviewed addition) and `papers/CLAIMS.json` (the
machine-verified claim map).

A frozen artifact may only change in a **dedicated re-baseline commit** that:

1. updates the digest/manifest in `FROZEN.yaml`;
2. adds a `rebalances:` record with `path`, `previous_sha256`, `new_sha256`,
   `decision_id`, `date`, `reason`, `approved_by`;
3. cites a decision id that exists as `## D-nnn` in `research/DECISIONS.md` or as
   an `id` in `docs/governance/DECISION_LOG.yaml`;
4. does not mix the re-baseline with unrelated work.

`check_frozen.py --base <ref>` compares the current file/manifest against the base
commit: every changed digest, added file or removed file must be covered by a
matching rebalance record. `--manifest` prints the current directory manifests for
that review (it never writes). Coverage decisions for programme assets
(`research/RESULTS/`, `experiments/`) are recorded in the freeze policy text
rather than silently ignored.

## 7. Data licence policy (three layers)

`DATA_LICENSES.yaml` is executable policy:

1. **Source patterns** — GREEN may be committed with attribution; AMBER needs an
   explicit `policy_entries` record; RED may not be committed at all.
2. **Positive inventory** — `docs/governance/DATA_INVENTORY.yaml` lists every
   committed data file with its `source_id`, `status` and detected `content` kind.
   Every tracked data file (by extension or by restricted content) must appear;
   moved, renamed or newly created files have no entry and fail. The inventory is
   regenerated with
   `python tools/governance/check_licence.py --write-inventory` and reviewed in
   the PR diff.
3. **Content classification** — the gate sniffs bytes (SQLite, Parquet, HDF5,
   gzip, zip, ELF, PDF, image, JSON, CSV, text, binary). A `.csv` that is really
   SQLite, or a declared file whose bytes change format, fails. Restricted binary
   formats are allowed only for synthetic fixtures under `tests/`.

Unlisted sources default to **RED**. `--summary` prints the inventory
classification for a human reviewer, and
`python tools/governance/check_licence.py --base origin/main` also scans the PR's
added/modified/renamed/deleted paths and untracked data files.

**This is a repository consistency control, not a legal guarantee.** A human still
reviews every inventory entry and owns the licence judgement; the gate detects
known restricted formats and undeclared files, not the lawfulness of a particular
bytes-to-licence combination.

## 8. Documentation links

`check_links.py` resolves every relative Markdown link/image under `docs/`
(skipping external URLs, pure `#fragment` anchors and fenced code). Links that
escape the repository root fail. Generated pages are checked too.

## 9. Test counts are measurements, not claims

`PROJECT_STATE.yaml` declares `collected`/`passed`/`skipped`/`failed`; the gate
compares them with `docs/refoundation/phase0/_evidence/governance/pytest_count.json`
(and the Phase-2 evidence artifacts). `record_tests.py` runs the suite and records
the exact command, the commit measured, whether `tests/` matched that commit, and
whether `tests/` differs from the base ref. It refuses to run while `tests/` has
uncommitted or untracked changes. After changing tests: commit the tests, run
`record_tests.py`, update the state counts and regenerate the views.

## 10. Rule-change audit

Changes to the governance surface itself require a **new** record in
`docs/governance/RULE_CHANGES.yaml` covering every changed protected path, with:

* a unique `change_id` (`RC-nnnn`);
* a `decision_id` that exists in `research/DECISIONS.md` or
  `docs/governance/DECISION_LOG.yaml`;
* `approved_by`, `date`, `reason` and the protected `paths`.

`check_rule_audit.py --base origin/main` compares the changed paths with the base
commit and fails if a protected path (`.github/workflows/governance.yml`,
`tools/governance/**`, `docs/governance/DATA_LICENSES.yaml`,
`docs/governance/FROZEN.yaml`) has no new record. The audit inputs themselves
(`RULE_CHANGES.yaml`, `DECISION_LOG.yaml`, the generated `DATA_INVENTORY.yaml`)
are excluded from the protected set to avoid recursion; they are still reviewed in
the PR diff.

**Limitation:** the gate makes weakening explicit and reviewable; it does not
cryptographically prove who approved a decision. A maintainer with write access can
forge an approval. What it removes is the *silent* weakening path for an agent.

## 11. Branch protection and the solo maintainer

Branch protection is **not applied**. The plan requires the six governance checks
plus `ci`, **zero mandatory approving reviews**, keeps an audited owner bypass, and
blocks force pushes and deletions.
`.github/CODEOWNERS` exists for routing/notification only.

## 12. What this governance does not do

* It does not verify that a scientific claim is correct.
* It does not provide independent review.
* It does not prevent a wrong edit; it makes the wrong edit visible and
  merge-blocking.
* It is not a security control: a maintainer can edit any file (the rule-change
  audit makes gate weakening visible, not impossible).
* The licence gate is not a legal opinion (see §7).
* It is not yet enforced server-side (branch protection not applied).

## 13. Operating procedures

**Before every commit / PR:**

```bash
python tools/governance/check_state.py
python tools/governance/gen_views.py --check
python tools/governance/check_frozen.py --base origin/main
python tools/governance/check_licence.py --base origin/main
python tools/governance/check_links.py
python tools/governance/check_rule_audit.py --base origin/main
python -m pytest -q
```

**Adding data files:** add the file → `check_licence.py --write-inventory` →
review the inventory diff (source + content kind) → commit both.

**Changing a frozen artifact:** add the `rebalances:` record with the decision id
and both digests in the same commit; the gate audits it against the base.

**Changing a gate, the workflow, or the licence/freeze rules:** add a
`RULE_CHANGES.yaml` record (and a `DECISION_LOG.yaml` entry if the decision is new)
with the approved decision id.

**After `main` advances:** `bump_state.py --ref origin/main` then
`gen_views.py`; the next PR carries it.

**Gate failure playbook:** the failing check id names the defect. Do not use
`--write`, `--write-inventory`, `--base ""` or an admin bypass to silence a real
inconsistency; fix the artifact or the record. `--base ""` is recorded as a
warning precisely because it weakens the audit.

## 14. Evidence and reproduction

Phase-0 acceptance evidence: `docs/refoundation/phase0/_evidence/governance/`.
Phase-1 activation review: `docs/refoundation/phase1/GOVERNANCE_ACTIVATION_REVIEW.md`.
Phase-2 hardening evidence and proof:
`docs/refoundation/phase2/_evidence/governance/` and
`docs/refoundation/phase2/GOVERNANCE_HARDENING.md`.

## 15. When a second maintainer exists

In order: required approvals → 1; require review from Code Owners; require
branches up to date; disable the admin bypass; then delete the solo-maintainer
rationale from the plan and this document.

## Appendix — governance file map

```text
PROJECT_STATE.yaml                                  single source of truth
tools/governance/yamlmini.py                        documented YAML subset
tools/governance/common.py                          git/root/digest/report helpers
tools/governance/check_state.py                     state gate
tools/governance/gen_views.py                       generated views gate
tools/governance/check_frozen.py                    freeze gate (format 2, rebalance audit)
tools/governance/check_licence.py                   licence gate (inventory + content scan)
tools/governance/check_links.py                     docs-link gate
tools/governance/check_rule_audit.py                governance-rule-change gate
tools/governance/bump_state.py                      deterministic main-block bump
tools/governance/record_tests.py                    test-count measurement
.github/CODEOWNERS                                  routing only (no review mandate)
.github/pull_request_template.md                    claim/evidence/freeze checklist
.github/workflows/governance.yml                    CI (six jobs, PR merge gate)
docs/governance/FROZEN.yaml                         frozen artifacts + per-file digests + rebalances
docs/governance/DATA_LICENSES.yaml                  per-source licence policy (v2)
docs/governance/DATA_INVENTORY.yaml                 generated positive data inventory
docs/governance/RULE_CHANGES.yaml                   approved governance rule-change records
docs/governance/DECISION_LOG.yaml                   governance approval ids
docs/governance/BRANCH_PROTECTION_PLAN.md           owner plan (not applied)
docs/governance/GOVERNANCE.md                       this document
docs/RESEARCH_INDEX.md                              generated index
tests/governance/                                   gate tests (synthetic fixtures)
```
