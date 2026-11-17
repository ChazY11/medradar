# REFOUNDATION-004 - Test results

Environment: Windows host, Python 3.12.10, pytest 9.1.1. Commands are run from the repository root
with PYTHONPATH pointing at the worktree (the package is not installed into this interpreter).

## 1. Baseline, before any change (HEAD 14eaf61)

- Full suite: **green** (`python -m pytest tests -q`), no failures.
- A per-file run with timings was captured for the first 60 test files
  (D:/DEPPSKK/data004-baseline/tests-per-file.txt); the slowest files were test_radar_api.py (5 s),
  test_research_agent.py (4 s), test_foundation.py (3 s), and most files run in 1-2 s.
- The suite is the legacy lane as well as the product and radar lanes; a green baseline is what
  makes a behaviour change attributable to this round.

## 2. After the changes (this branch)

- Full suite: **green**. 1,632 tests collected across 86 files, 5 skipped, 0 failed.
- Targeted suites run repeatedly during the work, all green:
  - `tests/test_radar_core.py test_radar_relevance.py test_radar_ledger.py test_radar_pipeline.py
    test_radar_api.py test_radar_graph.py test_radar_scheduler.py test_radar_ai.py
    test_radar_backup.py test_radar_parsers.py test_radar_alpha_gate.py`
  - `tests/test_radar_integrity.py` (14 tests, new)
  - `tests/governance` (73 tests, green after the new evidence files were placed under the
    licence-policy exempt path `docs/refoundation/004/_evidence/`)

## 3. Integration and data checks performed

| Check | Command / method | Result |
| --- | --- | --- |
| FastAPI app end-to-end (product + radar on one app) | in-process TestClient against the real 8,593-row ledger copy | 12/12 PASS: `/api/radar/feed` 200 with dimension objects and HIGH tier only, no vendor-statement false accept in the top 5; `/api/radar/feed/admission-summary` 200; `/api/radar/health` 200; `/api/meta` 200; `/api/events` 200; `/` 200 (new bundle); `/api/radar/graph/summary` 503 (no graph.db in the test data dir - the documented "not broken" state) |
| v2 -> v3 ledger migration on the real data | open the 8,593-row copy with the new code | schema radar-ledger-v3; all admission rows copied; feed/summary work |
| Re-judgement on rule change | run `apply_admissions` after a rules edit | 8,593 new decisions appended; earlier rows retained; `admission_current` shows the newest |
| Relevance projected on the real ledger | reproject + feed | 7,360 FEED / 1,154 LOW / 56 IRRELEVANT / 23 REVIEW of 8,593 decisions; 30-day feed = 20 records, no HyperVue/UniGuide |
| Quality report regeneration and drift check | `evaluate_relevance.py ... --check` | passes (JSON and Markdown match a fresh computation) |
| Web bundle | `npm run build` in web/ | succeeds; dist/index-Bxn-0Rgq.js (570 KB) + index-CnNYtwtQ.css; index.html updated; the bundle contains the precision label |
| Licence/governance gate | `python tools/governance/check_licence.py` (through tests) | green; new evidence artefacts placed under the policy's exempt path; the pre-existing inventory file is unchanged |

## 4. What is not covered by these tests

- No live network collection was run; adapter tests use fixtures. "A new record was actually
  discovered today" is NOT VERIFIED by this suite.
- No browser automation was run this round. The product UI changes are type-checked, built and
  served by the API smoke test, but layout, touch targets and the iPhone-sized viewport from
  QUALITY-001 were not re-measured.
- The production deployment is untouched and unobserved from this host.
