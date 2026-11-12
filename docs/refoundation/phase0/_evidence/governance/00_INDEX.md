# Governance evidence — index

This directory is the machine-captured evidence for the Phase-0 governance MVP
(`task-7`). Every `*.txt` file records, at the top:

```text
# command: <the exact command that produced this file>
# exit code: <the observed exit code>
```

and then the raw output. Nothing here was hand-written; the files were produced
by running the commands on this branch. After every deliberate failure the
tampered file was restored byte-for-byte (from a backup copy taken before the
demo), and `20_restored_all_pass.txt` re-runs all five gates to prove it.

Exit-code contract of every gate: `0` pass, `1` check failed, `2` configuration
or usage error (nothing verified).

| File | Shows |
| --- | --- |
| `01_env.txt` | python/git/platform identity of the capturing run; `HEAD` and `origin/main`; file counts |
| `03_check_state_pass.txt` | `check_state.py` passes (239 checks) |
| `04_check_state_fail_wrong_head.txt` | wrong `main.head` → exit 1, gate names both SHAs |
| `05_check_state_fail_missing_path.txt` | capability `evidence` path missing → exit 1 |
| `06_check_state_fail_duplicate_id.txt` | duplicated capability id → exit 1 |
| `07_check_state_fail_test_drift.txt` | declared test count disagrees with the measured artifact → exit 1 |
| `08_check_state_drift_warn.txt` | same disagreement with `--drift-warn` → exit 0 + warning |
| `09_gen_views_pass_twice.txt` | `gen_views.py` twice: identical SHA-256s, second run writes nothing, `git diff --exit-code` is 0 |
| `10_gen_views_stale_regen.txt` | changed state → stale views regenerated (diff non-empty); restore → clean again |
| `11_gen_views_fail_tampered.txt` | one hand-edited generated README line → exit 1 (hand-edited region) |
| `12_check_frozen_pass.txt` | `check_frozen.py` passes (7 entries, 50-file study manifest) |
| `13_check_frozen_fail_tampered.txt` | one frozen study byte changed → exit 1 with both digests |
| `14_check_licence_pass.txt` | `check_licence.py` passes (10 sources; tracked-file count is in the log) |
| `15_check_licence_fail_red_source.txt` | fake tracked `prices_2019.csv` for the RED source → exit 1; file then removed |
| `16_check_links_pass.txt` | `check_links.py` passes |
| `17_check_links_fail_broken.txt` | temporary page with a broken relative link → exit 1; file then removed |
| `18_compileall.txt` | `python -m compileall -q tools/governance` exits 0 |
| `19_workflow_yaml_valid.txt` | `.github/workflows/governance.yml` parses with PyYAML **and** the governance YAML subset |
| `20_restored_all_pass.txt` | all five gates re-run after the failure demos: exit 0 each |
| `21_json_summary.txt` | in-process summary of all five gates (`tool, ok, checks, failures, warnings`) |
| `22_file_inventory.txt` | line counts of every file created or modified by this task |
| `23_git_status.txt` | final `git add -A; git status --short`: the work is staged, not committed |
| `pytest_count.json` | the test-count measurement artifact verified by `check_state.py` |

Reproduce from the repository root:

```bash
python tools/governance/check_state.py
python tools/governance/gen_views.py --check
python tools/governance/check_frozen.py
python tools/governance/check_licence.py
python tools/governance/check_links.py
```

Note on counts: `01_env.txt` reports the git **index** file count (the captured
run had this change staged on top of `main`), while `main` itself has 1,135
tracked files at `b2a14c0` — that is the number `PROJECT_STATE.yaml` records and
`check_state.py` verifies against the `main` tree.
