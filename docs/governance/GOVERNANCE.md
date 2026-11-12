# MedRadar governance

**Status:** Phase-0 MVP, solo-maintainer. **Owner:** `ChazY11`.
**Branch protection:** not applied — see [`BRANCH_PROTECTION_PLAN.md`](BRANCH_PROTECTION_PLAN.md).
**Scope:** consistency, provenance and claim discipline for this repository. It is
not a second pair of eyes and it does not decide whether the science is right.

This document is the operating manual for the gates in `tools/governance/`. All
of them are Python-standard-library only, need no network, and run identically
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

**The edit flow is always the same:**

1. edit `PROJECT_STATE.yaml`;
2. run `python tools/governance/gen_views.py` and commit the regenerated views
   in the same commit;
3. run `python tools/governance/check_state.py` before pushing.

The state describes **`main`**, not the branch you are on. `main.head` must equal
the resolved `main.ref` (`origin/main`); a branch-only capability must not be
recorded here. When `main` advances, the next PR updates `main.head`,
`main.committed_at`, `main.commit_subject`, the tracked-file/workflow counts, the
test artifact and the views in that PR — until then the gate fails, which is the
point.

**Merge-gate semantics.** On a pull request, `origin/main` is the PR's base, so
"the state matches main" is checked at the merge point, and a PR that starts
after a merge carries the one-line state update in its own diff. Because of that,
the `governance` workflow runs on `pull_request` (and manual dispatch), not on
`push` to `main`: a post-merge push run would go red by design until the next PR
updates the state, which trains people to ignore a red check. `ci` still runs on
`main` pushes, and branch protection makes the PR run the merge gate.

## 2. The five gates

| Gate | Command | Verifies | Blocks |
| --- | --- | --- | --- |
| State | `python tools/governance/check_state.py` | schema/required sections; `main.head` vs `git rev-parse origin/main`; commit date/subject; version vs `pyproject.toml`; tracked-file count vs the `main` tree; workflows vs the `main` tree; every referenced path exists; duplicate ids; capability status vocabulary; decision ids exist in `research/DECISIONS.md`; study `freeze_ref` ids exist in `FROZEN.yaml`; declared test counts vs the measurement artifact | a state file that is wrong about git, cites missing files/decisions/freezes, or claims an unmeasured test count |
| Views | `python tools/governance/gen_views.py` (or `--check`) | README/CHANGELOG regions and `docs/RESEARCH_INDEX.md` are exactly the output of the current state, with matching source/payload digests | stale generated views, hand-edited generated regions, a RESEARCH_INDEX that no longer matches the state |
| Freeze | `python tools/governance/check_frozen.py` | every `FROZEN.yaml` file's SHA-256; no added/removed file under a frozen study directory | in-place edits of frozen protocols/reports/forecast sets; unreviewed artifacts entering a registered study |
| Licence | `python tools/governance/check_licence.py` | `DATA_LICENSES.yaml` is internally consistent; `data/` is gitignored; no tracked file matches a **RED** source; every **AMBER** match has an explicit `policy_entries` record | committing raw data whose licence forbids it; silently adding derived content without recording the redistribution basis |
| Links | `python tools/governance/check_links.py` | every repository-relative Markdown link/image under `docs/**/*.md` resolves; links that escape the repository are rejected | moved/renamed/typo'd docs, broken generated links |

Exit-code contract for every gate: **0** pass, **1** check failed, **2**
configuration/usage error (nothing was verified). Every script supports
`--help`; the five gates support `--json` for machine-readable output, and
`--root` to point at another checkout.

The `governance` workflow (`.github/workflows/governance.yml`) runs these five
jobs on pull requests and manual dispatch — it is the merge gate, not a monitor
of `main`. Job names are the status-check names in the branch-protection plan.

`record_tests.py` is the maintenance companion: it runs the offline pytest suite
and writes the test-count artifact that the state gate checks.

## 3. Determinism and tamper detection

Generated output must be reproducible: no wall clock, no network, no locale, no
unordered iteration. `generated_at` is a hand-maintained field of the state, so
regenerating from the same state yields the same bytes.

Each generated region records two digests:

```html
<!-- generated: do not edit by hand; regenerate with tools/governance/gen_views.py -->
<!-- source-sha256: <sha256 of PROJECT_STATE.yaml bytes> -->
<!-- payload-sha256: <sha256 of the generated markdown payload> -->
```

That makes the outcome unambiguous:

* bytes equal to the expected output → up to date (no write);
* region generated from the **current** state but content differs →
  **hand-edited: FAIL**, even if the editor recomputed a digest;
* older source digest, self-consistent payload digest → stale, regenerate;
* payload digest inconsistent with the payload → **hand-edited: FAIL**.

Consequence: `gen_views.py` run twice in a row writes nothing the second time.
The workflow runs it and then fails on `git diff`, so a committed stale view is a
merge blocker, and a hand edit is caught before `git diff` is even reached.

## 4. The YAML subset

No PyYAML dependency, including for tooling. `tools/governance/yamlmini.py`
implements exactly the subset the governance files use:

* one document, optional leading `---` / trailing `...`;
* `#` comments outside quotes;
* block mappings and sequences, nested by spaces (tabs rejected);
* plain, single-quoted and double-quoted scalars; `|` and `>` block scalars;
* `true`/`false`, `null`/`~`, decimal int, decimal float; `[]` / `{}` empties;
* duplicate mapping keys rejected.

Rejected loudly (with file and line): flow collections, anchors/aliases/tags,
merge keys, multiple documents, tabs in indentation, multi-line quoted scalars.
If a governance file needs more YAML than this, extend `yamlmini.py` and its
documented subset in the same PR — do not silently switch to PyYAML.

## 5. Generated views: never hand-edit

* **README.md** — the block between `<!-- BEGIN GENERATED: status -->` and
  `<!-- END GENERATED: status -->` is generated. The surrounding README is
  hand-written.
* **CHANGELOG.md** — the block between the `unreleased` markers is generated.
  Write your actual changelog entry outside the generated block.
* **docs/RESEARCH_INDEX.md** — the whole file is generated.

Commands: default run verifies and regenerates only stale views;
`--check` verifies without writing (for CI convenience); `--init` bootstraps a
missing marker block at its documented anchor; `--write` force-regenerates and
exists **only** to restore a file after a deliberate edit. Routine edits never
need `--write`.

## 6. Frozen research artifacts

`FROZEN.yaml` pins the scientific record: pre-registered protocols/amendments,
the Phase-0 report, the original and prospective forecast sets, and the complete
file manifest of the registered study directory
(`research/studies/early_signal_5firms`).

A frozen file may only change in a **dedicated re-baseline commit** that:

1. updates the digest/manifest in `FROZEN.yaml`;
2. states the reason in the commit and PR body;
3. links the decision id that authorised the change;
4. does not mix the re-baseline with unrelated work.

Use `python tools/governance/check_frozen.py --manifest` to print the current
directory manifests for review; it never writes. Adding a new artifact to the
study directory is therefore a governed act, not a silent one.

**Scope note:** freezing the whole study directory is deliberate. If a Phase-1
workstream needs to add study files, that PR must re-baseline FROZEN.yaml; the
Lead decides whether the study stays frozen during Phase 1.

## 7. Data licence policy

`DATA_LICENSES.yaml` is executable policy, enforced against `git ls-files`:

| Status | Meaning | Enforced rule |
| --- | --- | --- |
| `GREEN` | redistributable with attribution | may be committed; `may_redistribute: true` required |
| `AMBER` | raw content not redistributable | a committed file attributable to the source needs an explicit `policy_entries` record with kind and reason |
| `RED` | not redistributable at all | **any** tracked match fails; `policy_entries` cannot override; raw bytes may only live under the gitignored `data/` |

Unlisted sources default to **RED**. Every source needs an attribution string;
`raw_patterns` must stay under `data/`, and the gate verifies `data/` is actually
gitignored (otherwise the RED rule would be meaningless).

To add a source: classify it in `DATA_LICENSES.yaml` first, then commit derived
content. If it is AMBER, add a `policy_entries` record naming the exact file or
pattern and why the committed content is safe. `review_notes` records residual
risks that are currently tolerated (e.g. the demo page's embedded intraday price
window) — a note is a recorded decision, not a licence.

## 8. Documentation links

`check_links.py` resolves every relative Markdown link/image under `docs/`
(skipping external URLs, pure `#fragment` anchors and fenced code). Links that
escape the repository root fail. Generated pages are checked too, so a generator
that emits a stale path fails this gate.

## 9. Test counts are measurements, not claims

`PROJECT_STATE.yaml` declares `collected`/`passed`/`skipped`/`failed`; the gate
compares them with `docs/refoundation/phase0/_evidence/governance/pytest_count.json`,
which records the exact command, the commit measured (`tested_head`), whether
`tests/` matched that commit, and whether `tests/` differs from the base ref.

* after changing `tests/`, run `python tools/governance/record_tests.py`, commit
  the new artifact and update the state;
* `record_tests.py` refuses to write if `tests/` has uncommitted changes, so the
  recorded count always describes a commit; `tested_head` must be an ancestor of
  the current `HEAD`;
* the gate warns (does not fail) when `tested_head` is not `main.head`, so a
  branch that legitimately changes the suite can record its own measurement;
* `--tests-mode off` skips the check (use only when pytest genuinely cannot run)
  and emits a warning; `--drift-warn` downgrades a count mismatch to a warning for
  environments where the suite is measured elsewhere. The state file's
  `tests.policy` is `strict` by default.

## 10. Branch protection and the solo maintainer

Branch protection is **not applied**. The plan in
[`BRANCH_PROTECTION_PLAN.md`](BRANCH_PROTECTION_PLAN.md) requires the machine
checks and **zero mandatory approving reviews**, keeps an audited owner bypass,
and blocks force pushes and deletions.

`.github/CODEOWNERS` exists for routing/notification only. It must not be
converted into a review requirement until a second maintainer exists: a
requirement nobody can satisfy is worse than no requirement.

## 11. What this governance does not do

- It does not verify that a scientific claim is correct; it verifies that the
  record, provenance and declared state are consistent and that claims are not
  silently inflated.
- It does not provide independent review. One owner still makes every decision;
  research integrity still depends on pre-registration, artifacts and the
  documented decision log (`research/DECISIONS.md`).
- It does not prevent a wrong edit; it makes the wrong edit **visible** and
  merge-blocking.
- It is not a security control: a maintainer can edit any file. Digests make
  frozen-artifact changes explicit, not impossible.
- It is not yet enforced server-side (branch protection not applied).

## 12. Operating procedures

**Before every commit / PR:**

```text
python tools/governance/check_state.py
python tools/governance/gen_views.py --check
python tools/governance/check_frozen.py
python tools/governance/check_licence.py
python tools/governance/check_links.py
python -m pytest -q
```

**Adding a capability:** add an entry to `capabilities` with `working` only when
an evidence path and (where applicable) an offline test exist; otherwise `draft`.
Run `gen_views.py`; the generated index updates.

**Adding a research study:** add `id`, `verdict`, `evidence`, `freeze_ref` and
`public_claim: false` unless the claim has survived its pre-registered test. Add
a freeze entry (file digests or directory manifest) in the same PR.

**Adding a decision:** append to `research/DECISIONS.md`, add it to the state's
`decisions.index` if it is load-bearing, and update `decisions.count`.

**After `main` advances:** update `main.*`, regenerate views, and re-run
`record_tests.py` if `tests/` moved; the state check fails until you do.

**Gate failure playbook:** the failing check id in the output names the defect.
Do not use `--write`, `--tests-mode off` or admin bypass to silence a failure
that describes a real inconsistency; fix the artifact or the record.

## 13. Evidence and reproduction

The Phase-0 acceptance evidence (pass and deliberate-failure outputs for every
gate) is in
`docs/refoundation/phase0/_evidence/governance/`, with the narrative in
`docs/refoundation/phase0/GOVERNANCE_MVP.md`. Every capture was produced by the
commands above on this branch; no output was hand-written.

## 14. When a second maintainer exists

In order: required approvals → 1; require review from Code Owners; require
branches up to date; disable the admin bypass; then delete the solo-maintainer
rationale from the plan and this document. Until then, keep the gates machine-only
and leave the bypass auditable.

## Appendix — governance file map

```text
PROJECT_STATE.yaml                                  single source of truth
tools/governance/yamlmini.py                        documented YAML subset
tools/governance/common.py                          git/root/digest/report helpers
tools/governance/check_state.py                     state gate
tools/governance/gen_views.py                       generated views gate
tools/governance/check_frozen.py                    freeze gate
tools/governance/check_licence.py                   licence gate
tools/governance/check_links.py                     docs-link gate
tools/governance/record_tests.py                    test-count measurement
.github/CODEOWNERS                                  routing only (no review mandate)
.github/pull_request_template.md                    claim/evidence/freeze checklist
.github/workflows/governance.yml                    CI draft (five jobs)
docs/governance/FROZEN.yaml                         frozen artifacts + manifests
docs/governance/DATA_LICENSES.yaml                  per-source licence policy
docs/governance/BRANCH_PROTECTION_PLAN.md           owner plan (not applied)
docs/governance/GOVERNANCE.md                       this document
docs/RESEARCH_INDEX.md                              generated index
docs/refoundation/phase0/GOVERNANCE_MVP.md          Phase-0 narrative + evidence
docs/refoundation/phase0/_evidence/governance/      captured gate outputs
```
