# Governance MVP — Phase 0

**Deliverable:** `task-7` — a solo-maintainer governance minimum viable version for
MedRadar, based on `main` at `b2a14c0` (branch `governance/refoundation-002`).
**Status:** built; every gate passes and every gate was deliberately broken and
restored as demonstrated below. Branch protection is **documented but not
applied**.

---

## 1. What was built

| Path | Role |
| --- | --- |
| [`PROJECT_STATE.yaml`](../../../PROJECT_STATE.yaml) | single hand-edited source of truth (identity, `main` head, version, test counts, data snapshot, capability list with status/evidence, research studies with verdict/freeze/public-claim, open work, governance status, decision index, `not_claimed` list) |
| [`tools/governance/yamlmini.py`](../../../tools/governance/yamlmini.py) | documented YAML subset reader/writer (no PyYAML) |
| [`tools/governance/common.py`](../../../tools/governance/common.py) | root discovery, read-only git queries, SHA-256, globbing, deterministic report |
| [`tools/governance/check_state.py`](../../../tools/governance/check_state.py) | state gate (git head/date/subject, version, tree counts, paths, ids, decisions, freezes, measured test counts) |
| [`tools/governance/gen_views.py`](../../../tools/governance/gen_views.py) | generated views: README status block, `docs/RESEARCH_INDEX.md`, CHANGELOG snapshot; digest-anchored tamper detection |
| [`tools/governance/check_frozen.py`](../../../tools/governance/check_frozen.py) | frozen-file digests and frozen-study-directory manifests |
| [`tools/governance/check_licence.py`](../../../tools/governance/check_licence.py) | per-source GREEN/AMBER/RED redistribution policy vs `git ls-files` |
| [`tools/governance/check_links.py`](../../../tools/governance/check_links.py) | relative Markdown links under `docs/` |
| [`tools/governance/record_tests.py`](../../../tools/governance/record_tests.py) | runs the offline suite, writes the test-count artifact the state gate verifies |
| [`docs/governance/FROZEN.yaml`](../../governance/FROZEN.yaml) | frozen forecast sets, study protocol/report/amendments, study-directory manifest |
| [`docs/governance/DATA_LICENSES.yaml`](../../governance/DATA_LICENSES.yaml) | data-source licence policy (10 sources) + explicit AMBER policy entries + residual-risk notes |
| [`docs/governance/BRANCH_PROTECTION_PLAN.md`](../../governance/BRANCH_PROTECTION_PLAN.md) | exact owner settings for `main`; zero mandatory approvals; audited owner bypass; no force-push/deletion |
| [`docs/governance/GOVERNANCE.md`](../../governance/GOVERNANCE.md) | operating manual: gates, determinism, YAML subset, freeze/licence procedures, limitations |
| [`.github/CODEOWNERS`](../../../.github/CODEOWNERS) | routing only; explicitly not a review mandate |
| [`.github/pull_request_template.md`](../../../.github/pull_request_template.md) | classification, capability claim, evidence-for-every-number, gates, not-claimed, freeze, base-vs-ancestry |
| [`.github/workflows/governance.yml`](../../../.github/workflows/governance.yml) | draft CI: `state`, `views`, `frozen`, `licence`, `links` jobs on pull requests (merge gate); valid YAML, references only files in this change |
| [`docs/RESEARCH_INDEX.md`](../../RESEARCH_INDEX.md) | generated study/capability/decision index |

`PROJECT_STATE.yaml` is truthful to `main` at `b2a14c0`: 1,135 tracked files and
four workflows on the `main` tree; 1,074 pytest tests collected (1,071 passed, 3
skipped, 0 failed); PRs #2–#11 merged, #1 and #12–#30 open (19 drafts); `docs/`
as the Pages source; **no branch protection** (recorded as `applied: false`, with
the plan linked, not applied). PR/branch counts are marked owner-reported /
informational because this session was offline and did not call the GitHub API.

## 2. How to run every check

```bash
python tools/governance/check_state.py          # exit 0 pass, 1 fail, 2 config
python tools/governance/gen_views.py            # regenerate + verify (idempotent)
python tools/governance/gen_views.py --check    # verify only
python tools/governance/check_frozen.py
python tools/governance/check_licence.py
python tools/governance/check_links.py
python tools/governance/record_tests.py         # refresh the test-count artifact
python -m compileall -q tools/governance        # syntax check
```

Every gate accepts `--help`, `--root`, `--json`; `gen_views` adds `--check`,
`--init`, `--write`; `check_state` adds `--main-ref`, `--tests-mode`,
`--drift-warn`, `--test-artifact`; `check_frozen` adds `--manifest`. Both
`python tools/governance/<gate>.py` and `python -m tools.governance.<gate>` work.

## 3. Demonstrated evidence

All outputs are in [`_evidence/governance/`](_evidence/governance/); start with
[`00_INDEX.md`](_evidence/governance/00_INDEX.md). Each file records the exact
command, the observed exit code and the raw output. The state was restored
after every deliberate failure, and `20_restored_all_pass.txt` proves it.

| # | Evidence file | Command | Expected | Observed |
| --- | --- | --- | --- | --- |
| 1 | `03_check_state_pass.txt` | `check_state.py` | exit 0 | exit 0, 240 checks, 0 failures |
| 2 | `04_check_state_fail_wrong_head.txt` | `check_state.py` after `main.head` set to a wrong SHA | exit 1 | exit 1 (2 failures, 1 warning), both SHAs named |
| 3 | `05_check_state_fail_missing_path.txt` | `check_state.py` after a capability `evidence:` pointed at a missing file | exit 1 | exit 1, `path.capabilities[0].evidence` fails |
| 4 | `06_check_state_fail_duplicate_id.txt` | `check_state.py` after duplicating a capability id | exit 1 | exit 1, `capabilities.unique_ids` fails |
| 5 | `07_check_state_fail_test_drift.txt` | `check_state.py` after changing the declared collected/passed counts | exit 1 | exit 1, `tests.artifact.match` names state vs artifact |
| 6 | `08_check_state_drift_warn.txt` | same edit with `--drift-warn` | exit 0 + warning | exit 0, one `[WARN]` |
| 7 | `09_gen_views_pass_twice.txt` | `gen_views.py` twice + SHA-256 before/after + `git diff --exit-code` | second run no diff | identical digests, no writes, diff exit 0 |
| 8 | `10_gen_views_stale_regen.txt` | state timestamp changed → `gen_views.py` → state restored → `gen_views.py` | stale regenerated, then clean | 3 targets rewritten (9 changed lines); restore returns to empty diff |
| 9 | `11_gen_views_fail_tampered.txt` | one generated README line hand-edited → `gen_views.py` | exit 1 | exit 1: "region records the current source digest but its content differs; hand-edited generated region" |
| 10 | `12_check_frozen_pass.txt` | `check_frozen.py` | exit 0 | exit 0, 34 checks, 7 entries, 50-file directory manifest |
| 11 | `13_check_frozen_fail_tampered.txt` | one frozen study file modified → `check_frozen.py` | exit 1 | exit 1, `sha256` mismatch showing both digests |
| 12 | `14_check_licence_pass.txt` | `check_licence.py` | exit 0 | exit 0, 96 checks, 10 sources, 18 AMBER matches covered, no RED match |
| 13 | `15_check_licence_fail_red_source.txt` | fake `prices_2019.csv` staged under `docs/governance/_tmp_red_source/` → `check_licence.py` | exit 1 | exit 1: "RED source 'yahoo_chart_bars' has a tracked file outside data/"; file removed, pass restored |
| 14 | `16_check_links_pass.txt` | `check_links.py` | exit 0 | exit 0, 41 Markdown files, 79 relative links resolve |
| 15 | `17_check_links_fail_broken.txt` | temporary page with a broken relative link → `check_links.py` | exit 1 | exit 1, names file:line and target; page removed, pass restored |
| 16 | `18_compileall.txt` | `python -m compileall -q tools/governance` | exit 0 | exit 0 |
| 17 | `19_workflow_yaml_valid.txt` | PyYAML `safe_load` + the documented YAML subset on `governance.yml` | valid, 5 jobs | valid under both parsers; jobs `state, views, frozen, licence, links` |
| 18 | `20_restored_all_pass.txt` | all five gates re-run after the failure demos | exit 0 each | exit 0 each (240/34/96/3 checks) |
| 19 | `21_json_summary.txt` | each gate's report reduced to `tool, ok, counts` | `ok: true` | `ok: true` for all five |
| 20 | `22_file_inventory.txt` | line count of every file created/modified | inventory of every created/modified path |
| 21 | `23_git_status.txt` | `git add -A; git status --short` | staged, no commit | staged; no commit made |
| 22 | `pytest_count.json` | `record_tests.py` | artifact written | 1,074 collected / 1,071 passed / 3 skipped / 0 failed; tested head `b2a14c0`, `tests/` unchanged |

## 4. Determinism

`gen_views.py` never reads the clock or the network. The generated block's
`source-sha256` is the digest of `PROJECT_STATE.yaml` bytes; `payload-sha256` is
the digest of the generated markdown. Two consecutive runs are byte-identical
(the second writes nothing), and the CI `views` job turns a committed stale view
into a `git diff` failure. A hand edit fails before that: the region carries the
current source digest with different content, or its payload digest does not
match its own bytes.

The deliberate-failure captures show both branches: tampering fails, stale
regenerates.

## 5. Freeze and licence semantics (and their limits)

* **Freeze** (`FROZEN.yaml`): six hashed files (both forecast sets, the study
  protocol, Phase-0 report, domain amendment, labelling protocol) plus the
  complete 50-file manifest of `research/studies/early_signal_5firms`. A new
  file under that directory fails until FROZEN.yaml is re-baselined in a
  reviewed commit. This is deliberate: an unreviewed artifact entering a
  registered study is exactly what governance is for.
* **Licence** (`DATA_LICENSES.yaml`): GREEN sources need attribution only; AMBER
  sources need an explicit `policy_entries` record for every attributable
  tracked file (all 18 Wayback-derived matches are recorded, in 4 entries); RED
  sources may not be committed at all (`yahoo_chart_bars` raw bars stay in
  gitignored `data/`). Unknown sources default to RED. The gate also proves
  `data/` is actually gitignored, so the RED rule is not vacuous.
* Residual risk recorded rather than hidden: `docs/replay_intraday.html` embeds
  a small intraday price window from the Yahoo lane for the offline demo. It is
  listed in `DATA_LICENSES.yaml` `review_notes`; the remediation decision belongs
  to the Lead.

## 6. What was not done (explicitly)

* **Branch protection was NOT applied** and no GitHub API or repository settings
  were touched.
* Nothing was pushed, merged or rewritten. `medradar/`, `tests/` and
  `experiments/` were not modified: the deliberate tamper demos touched only
  `research/studies/...` and generated views, and every one was restored
  byte-for-byte (verified by `20_restored_all_pass.txt` and `git status`).
* No scientific claim is made here. The gates check consistency and provenance,
  not correctness; there is still one maintainer and one pair of eyes.
* The governance workflow is a draft merge gate (pull requests only); it is not a
  required check yet.

## 7. Open decisions for the Lead

1. **Merge-gate friction.** `PROJECT_STATE.yaml` describes the PR's base
   `main`, so every PR opened after a merge must carry the one-line
   head/date/subject/count update (and regenerated views). That is what makes the
   recorded head true at each merge point, but it is real friction for the 19
   open draft PRs. Alternative: relax the state gate to accept an ancestor
   checkpoint (weaker truth claim). Phase-0 default is strict.
2. **Freeze scope vs Phase 1.** The whole `early_signal_5firms` directory is
   frozen. If Phase-1 work adds study files in another workstream, that PR must
   re-baseline `FROZEN.yaml`. Keep it (governed additions) or narrow the freeze
   to the Phase-0 records only?
3. **Apply branch protection?** The plan requires `governance` + `ci` checks, no
   mandatory approvals, owner bypass, no force-push, no deletion. It must be
   applied in the GitHub UI *after* the `governance` workflow has run once on a
   PR (check names must be discoverable). Not applied by this task.
4. **`docs/replay_intraday.html` embedded price window** — regenerate from a
   synthetic fixture in Phase 1, or keep it with the recorded AMBER note?
5. **Commit/merge.** Per the task rule this work is left **uncommitted** on
   `governance/refoundation-002` (staged for review, `23_git_status.txt`).
   Committing and merging is the Lead's call.
