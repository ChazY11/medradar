# Governance hardening — Phase 2, Workflow A

**Branch:** `governance/phase2-hardening` (based on PR #32 @ `8d7fd62`)
**Status:** implemented, tested and committed on the branch. Not pushed, not
merged, no branch protection applied, no repository settings changed.
**Commits:** `36cf0e5` (hardening + tests), `500a321` (test counts + views),
`8a0e8f9` (licence classification fixes), plus this documentation/evidence commit.
**Scope:** the four Phase-1 review defects — licence bypasses, freeze bypasses,
missing rule-change audit, state staleness — fixed in runnable code with tests,
not described as a report.

## 1. What changed (file:line)

| File | Change |
| --- | --- |
| `tools/governance/check_licence.py:103` `detect_kind` | content sniffing: SQLite, Parquet, HDF5, gzip, zip, ELF, PDF, PNG/JPEG/GIF, JSON, CSV, text, binary; Unicode/UTF-16 log handling so legacy console logs are not mistaken for restricted binaries |
| `tools/governance/check_licence.py:193` `Policy` | executable policy: sources, worst-status-wins classification, per-source `policy_entries`, inventory path/extensions/restricted kinds, manual-review and disclaimer validation |
| `tools/governance/check_licence.py:257` `load_inventory` | validates `DATA_INVENTORY.yaml` schema, duplicate paths and GREEN/AMBER/RED statuses |
| `tools/governance/check_licence.py:379` `check_tree` | **positive inventory coverage** for every tracked data file (extension or restricted content), stale-entry detection after delete/rename, declared-vs-detected content mismatch, restricted binary formats, RED entries, extension masquerade, and the legacy RED/AMBER pattern tripwire |
| `tools/governance/check_licence.py:506` `check_untracked` | untracked data files fail, so a file cannot hide outside the final tree |
| `tools/governance/check_licence.py:523` `check_diff` | PR-diff scan against `--base` (default `origin/main`): added/modified/renamed paths are compared with the inventory and with their own content kind; deleted/renamed-away paths surface as stale inventory entries |
| `tools/governance/check_licence.py:565` `generate_inventory`, `:600` `write_inventory` | `--write-inventory` generates the reviewed positive inventory (`--summary` is the human review list) |
| `tools/governance/check_licence.py:673` `build_report` | policy schema v2, `raw_root` must be gitignored, inventory+content+untracked+diff checks in one report |
| `tools/governance/check_frozen.py:47` schema `medradar.frozen.v2` | per-file SHA-256 manifests replace name-only lists |
| `tools/governance/check_frozen.py:104` `_manifest_map` | every file in a frozen directory is hashed; new/removed/renamed files fail; `no_new_files` enforced |
| `tools/governance/check_frozen.py:254` `_valid_rebalances` | `rebalances:` records need path, previous/new digest, decision_id (checked against `research/DECISIONS.md` or `DECISION_LOG.yaml`), date, reason, approved_by |
| `tools/governance/check_frozen.py:372` `_audit_rebaselines` | compares current `FROZEN.yaml` with the base ref; every digest/manifest change requires a matching approved rebalance record |
| `tools/governance/check_frozen.py:497` `print_manifest` | `--manifest` prints current per-file manifests for a reviewed re-baseline (read-only) |
| `tools/governance/check_rule_audit.py` (new, 347 lines) | protected-surface audit: changes to `.github/workflows/governance.yml`, `tools/governance/**`, `docs/governance/DATA_LICENSES.yaml`, `docs/governance/FROZEN.yaml` require a **new** `RULE_CHANGES.yaml` record backed by a real decision id (`rules.uncovered_change` at `:312`) |
| `tools/governance/bump_state.py` (new, 281 lines) | deterministic `main`-block bump from a git ref; empty-workflow list fixed; no wall clock |
| `tools/governance/record_tests.py` | refuses to record while `tests/` has uncommitted **or untracked** changes |
| `tools/governance/check_state.py:688` `_freeze_ids` | accepts freeze schema v1 and v2 |
| `.github/workflows/governance.yml` | six jobs: `state`, `views`, `frozen`, `licence`, `links`, `rule-audit`; `contents: read`; `fetch-depth: 0` for the four base-ref jobs |
| `docs/governance/DATA_LICENSES.yaml` | schema v2, inventory section, three GREEN sources (`medradar_derived_artifacts`, `curated_configuration`, `synthetic_fixtures`) and patterns for `docs/research/**`, `docs/refoundation/**`, `tools/*.json` |
| `docs/governance/DATA_INVENTORY.yaml` (new) | generated positive inventory: **167 data files**, every entry with source and detected content kind |
| `docs/governance/FROZEN.yaml` | format 2: 7 hashed file entries + 2 directory manifests (52 file digests), coverage extended to `research/forecasts/` and `papers/CLAIMS.json`, empty `rebalances:` log |
| `docs/governance/RULE_CHANGES.yaml`, `DECISION_LOG.yaml` (new) | RC-0001 / GOV-0001 for this hardening change |
| `docs/governance/GOVERNANCE.md`, `BRANCH_PROTECTION_PLAN.md` | documented gates, procedures, re-baseline and rule-change flow, six required checks, still not applied |
| `tests/governance/` (new) | 43 tests: 19 licence, 12 freeze, 8 rule audit, 4 bump, plus synthetic fixtures and a git-repo helper |

## 2. Licence gate: before/after bypass results

Identical fixture repositories; old code is `8d7fd62:tools/governance/check_licence.py`
with the Phase-0 pattern policy (policy entries stripped because the fixture repo
does not carry those files), new code is this branch. Full log:
[`_evidence/governance/02_before_after_bypass_table.txt`](_evidence/governance/02_before_after_bypass_table.txt).

| Bypass | old exit | new exit | new failure ids |
| --- | --- | --- | --- |
| baseline (no bypass) | 0 | 0 | — |
| A new source / new location (CSV in `data_exports/`) | **0 (missed)** | **1** | `inventory.coverage`, `diff.changed_data_file` |
| B known AMBER source at undeclared path (`research/RESULTS/…json`) | **0 (missed)** | **1** | `inventory.coverage`, `diff.changed_data_file` |
| C binary SQLite under `docs/` | **0 (missed)** | **1** | `content.restricted_kind`, `inventory.coverage`, `diff.changed_data_file` |
| D CSV data under `docs/` | **0 (missed)** | **1** | `inventory.coverage`, `diff.changed_data_file` |
| E control: declared RED pattern `**/prices_*.csv` | 1 (caught) | **1** | `source.pattern` + inventory |
| F extension masquerade (a declared `.csv` whose bytes are SQLite) | **0 (missed)** | **1** | `inventory.content_match` |
| G renamed declared data file | **0 (missed)** | **1** | `inventory.coverage`, `inventory.stale_entry` |
| H untracked data file (not in final tree) | **0 (missed)** | **1** | `untracked.data_file` |

So all four Phase-1 bypasses (A–D) are caught, plus relocated/renamed,
masquerade and untracked variants; the old gate caught only the pattern it
already declared. In every row the synthetic marker inside the fixture bytes
appeared **0 times** in gate logs (leak=False), and the marker search on the real
repository's gate output is 0
([`11_log_privacy.txt`](_evidence/governance/11_log_privacy.txt)).

## 3. False-positive baseline

[`_evidence/governance/03_false_positive_baseline.txt`](_evidence/governance/03_false_positive_baseline.txt):
the hardened gate on the real repository classifies **167 tracked data-like
files, flags 0**, finds no stale inventory entries, no RED/AMBER pattern
violations and no untracked data files; the diff scan covers 63 changed paths and
5 data files. Inventory classification: 112 `medradar_derived_artifacts`, 30
`synthetic_fixtures`, 9 `internet_archive_cdx` (AMBER, covered by policy entries),
9 `curated_configuration`, 4 `sec_8k_hand_labels`, 1 `nmpa_demo_seed`, **0
unclassified**. The two files that were initially unclassified
(`docs/refoundation/phase0/.../pytest_count.json`, `tools/round_end.json`) were
classified rather than exempted; the gate now also fails any inventory entry whose
status is RED.

Manual review is retained: `--write-inventory` regenerates, `--summary` prints the
classification for a human, and the disclaimer in `DATA_LICENSES.yaml` and
`GOVERNANCE.md` states this is a repository consistency control, **not a legal
guarantee**.

## 4. Freeze bypass matrix

Base = `HEAD` (`8a0e8f9`), format 2, all attempts restored afterwards. Full log:
[`_evidence/governance/04_freeze_bypass_matrix.txt`](_evidence/governance/04_freeze_bypass_matrix.txt).

| Attempt | Result |
| --- | --- |
| baseline committed tree | exit 0 |
| 1 name-only content edit inside frozen study directory | **caught** `frozen.entries[6].files[CASE_CANDIDATES.md].sha256` |
| 2 new forecast set in `research/forecasts/` | **caught** `no_new_files` |
| 3 deleted file inside frozen directory | **caught** `no_removed_files` |
| 4 renamed file inside frozen directory | **caught** added+removed |
| 5 edited `papers/CLAIMS.json` | **caught** `sha256` (+ `rebalance.unapproved`) |
| 6 edit + digest update, no `rebalances:` record | **caught** `rebalance.unapproved` |
| 7 re-baseline with unknown decision id `D-999` | **caught** `decision_id.exists` |
| 8 re-baseline with approved `GOV-0001` | **passes** (exit 0) |
| final committed tree restored | exit 0 |

`--manifest` prints the current per-file digests used for a reviewed re-baseline;
the command never writes. `research/RESULTS/`, `experiments/` and
`docs/calibration/` remain deliberately unfrozen (research records, not study
inputs); that scope decision is recorded under `policy.scope` in `FROZEN.yaml`
and in `GOVERNANCE.md` §6.

## 5. Rule-change audit proof

[`_evidence/governance/05_rule_change_audit_proof.txt`](_evidence/governance/05_rule_change_audit_proof.txt):

| Scenario | Result |
| --- | --- |
| baseline vs `HEAD` and vs `origin/main` | pass |
| 1 edit `.github/workflows/governance.yml`, no record | **fail** `rules.uncovered_change` |
| 2 edit `docs/governance/DATA_LICENSES.yaml`, no record | **fail** `rules.uncovered_change` |
| 3 add a new untracked gate tool under `tools/governance/`, no record | **fail** `rules.uncovered_change` |
| 4 documentation-only change | pass (not protected) |
| 5 workflow edit + new record + `GOV-0001` decision | **pass** |
| 6 workflow edit + record with unknown `D-999` | **fail** decision-id check |
| final restored tree | pass |

The gate is wired into CI as the sixth job (`rule-audit`). A change to the gate
or the workflow therefore cannot land silently; an agent must add an explicit,
approved record. Limitation: approval identity is a recorded string, not a
cryptographic signature — the audit removes *silent* weakening, not a
maintainer's deliberate forgery.

## 6. State staleness / bump proof

[`_evidence/governance/06_state_staleness_and_bump.txt`](_evidence/governance/06_state_staleness_and_bump.txt):
a throwaway `sim/p2-main-advance` branch added one workflow and one document
(tracked files 1,197 vs real 1,135). `check_state --main-ref sim/p2-main-advance`
failed exactly five checks (`head`, `committed_at`, `commit_subject`,
`tracked_files`, `workflows`); `bump_state.py --ref sim/p2-main-advance
--dry-run` printed the deterministic diff; after `bump_state` + `gen_views.py`
the state gate passed. The resulting worktree diff is four files
(PROJECT_STATE.yaml, README.md, CHANGELOG.md, RESEARCH_INDEX.md), 20 insertions /
19 deletions. The branch/worktree was then removed and the state restored.

`bump_state.py` derives head/short/date/subject/version/counts from the ref and
sets `generated_at` to the ref commit time. A post-merge bot commit cannot satisfy
strict equality, so the documented flow is **pre-merge**: the PR carries the bump.

## 7. Tests and CI

| Check | Result |
| --- | --- |
| `tests/governance/` (new) | **43 passed** |
| full suite, `python -m pytest -q -o addopts=""` | **1117 collected, 1114 passed, 3 skipped, 224 subtests**, 0 failed |
| `python -m medradar selftest` (the CI packaging entry point) | **Ran 1117 tests, OK (skipped=3)** |
| `check_state` | PASS, 240 checks, 0 failures, 1 expected warning (counts measured on branch HEAD, not `main.head`) |
| `gen_views --check` | PASS, 3 targets |
| `check_frozen --base origin/main` | PASS, 36 checks (legacy base → rebalance audit skipped with a warning) |
| `check_licence --base origin/main` | PASS, 14 checks |
| `check_links` | PASS, 3 checks |
| `check_rule_audit --base origin/main` | PASS, 12 checks |
| `compileall`, module invocation, workflow YAML (PyYAML + yamlmini) | clean; 6 jobs; `contents: read`; 4 jobs with `fetch-depth: 0` |

Evidence: [`07`](_evidence/governance/07_governance_unit_tests.txt),
[`08`](_evidence/governance/08_full_suite.txt),
[`09`](_evidence/governance/09_all_gates_after.txt). `medradar/` and
`experiments/` are untouched vs `origin/main`; `tests/` changes are only the new
`tests/governance/` package (11 files, 726 insertions).

The state test counts and the measurement artifact were refreshed in `500a321`
(1,117/1,114/3/0) and `docs/governance/DATA_INVENTORY.yaml` in `8a0e8f9`; the
derived views were regenerated in the same commit.

## 8. Remaining limitations (stated, not hidden)

1. **Data embedded in Markdown** (or base64 in a `.md`/`.py`) is *not* detected by
   the content scan: the gate classifies tracked files, and a pasted table in a
   document is text. The inventory can only force an entry for data-extension
   files. This is reported as not handled; the mitigation is review plus the
   frozen-directory rule for research records.
2. **Known formats only.** Content classification recognises SQLite, Parquet,
   HDF5, gzip, zip, ELF, PDF, images, JSON, CSV and text. Any unrecognised binary
   is classified `binary`, which is a restricted kind and fails unless declared
   as a synthetic fixture — conservative, but a text file whose delimiter pattern
   is irregular is classified `text`; it is still covered by the inventory's
   extension rule.
3. **Human review remains required.** The inventory is a control, not a legal
   opinion; the gate cannot decide whether a bytes-to-licence combination is
   lawful, and `DATA_LICENSES.yaml` says so.
4. **Rule-change approval is an audited record, not a signature.** A maintainer
   with write access can forge `approved_by`; what the gate removes is the silent
   path.
5. **Base-ref audits need history.** `check_frozen`/`check_licence`/
   `check_rule_audit` compare against `origin/main`; CI checks out with
   `fetch-depth: 0`. In a shallow local clone the base comparison warns/skips,
   which is recorded in output rather than hidden.
6. **Freeze coverage is a decision.** Results/experiments/calibration are not
   frozen; the coverage added is the forecast directory and the claims map. Any
   expansion needs its own reviewed re-baseline decision.
7. **Server-side enforcement is still absent.** Branch protection is not applied;
   the workflow is a merge gate only once the branch lands on `main` (and, as the
   Phase-1 review noted, a same-repo PR runs its own workflow version — the
   rule-change audit makes weakening visible but does not prevent it).

## 9. Evidence index

All under `docs/refoundation/phase2/_evidence/governance/`:

| File | Contents |
| --- | --- |
| `01_environment.txt` | branch, HEAD, origin/main, Python/git/OS |
| `02_before_after_bypass_table.txt` | old-vs-new gate on identical fixtures; A–D, control, masquerade, rename, untracked; marker leak column |
| `03_false_positive_baseline.txt` | real-repo scan: 167 files, 0 flagged; inventory classification; manual review list |
| `04_freeze_bypass_matrix.txt` | eight freeze attempts, result per attempt, manifest printer output |
| `05_rule_change_audit_proof.txt` | protected edits with/without records and decision ids |
| `06_state_staleness_and_bump.txt` | simulated main advance, five state failures, bump diff, four-file view diff, restore |
| `07_governance_unit_tests.txt` | 43 new tests |
| `08_full_suite.txt` | full pytest + selftest + unittest discovery |
| `09_all_gates_after.txt` | six gates, workflow YAML validation, module invocation, protected-tree diff |
| `10_file_inventory.txt` | line counts of the deliverable, gates, tests, fixtures, configs |
| `11_log_privacy.txt` | marker occurrences in gate logs = 0 |

## 10. Scope statement

This work commits on `governance/phase2-hardening` only. No push, no merge, no
branch protection, no repository settings, no changes under `medradar/` or
`experiments/`. The branch is based on PR #32 (`8d7fd62`); PR #32 itself is
untouched and still unmerged.
