# Repository Audit — MedRadar

Structure map, redundancy findings, what was actually cleaned, and what needs a human decision.
Audit performed **2026-11-04** on a read-only copy of `main` (`b2a14c0`); the maintenance branch
`maintenance/repository-consolidation` was created afterwards from that same commit.

Companion documents: [PROJECT_STATUS.md](PROJECT_STATUS.md) (what the project is / what is proven),
[DATA_ASSET_REGISTER.md](DATA_ASSET_REGISTER.md) (data governance).

---

## 1. Audit method and boundary

- Read-only phase (Step A) before any edit: full tree at `origin/main`, all branches and worktrees,
  all open/closed PRs, CI runs, `docs/`, `research/`, `experiments/`, `data/`, `scripts/`, `tools/`,
  `verifier/`, `papers/`, configuration, ignore rules, Python environment and dependency declaration.
- The primary checkout was **not** modified: it sits on `research/s028-temporal-graph-early-signal`
  with an uncommitted owner edit (`research/studies/early_signal_5firms/HUMAN_REVIEW_WORKSHEET.csv`).
  All documentation work happened in a separate linked worktree on a new branch off `main`.
- SQLite databases were opened read-only (`mode=ro&immutable=1`). No restore, prune, migration,
  deletion, rebase, force-push, PR edit or branch deletion was performed.
- Not verified in this pass: live collection runs against the network (`medradar run`), the
  observatory's scheduled task internals, and backup/restore execution (deliberately out of scope).

**Status vocabulary used below:** `CURRENT`, `DRAFT`, `EXPERIMENTAL`, `HISTORICAL`, `GENERATED`,
`DUPLICATED`, `OBSOLETE_CANDIDATE`, `UNKNOWN`.

---

## 2. Repository map (`main`, 1,135 files, 30.5 MB tracked)

| Path | Files | What it is | Status |
|---|---:|---|---|
| `medradar/` | 87 | The package: collectors, event store, metrics, report/dashboard, replay, paper trading, statistics, bitemporal store, forecast registry, research agent, intelligence lane | `CURRENT` |
| `config/` | 10 | Curated knowledge: company aliases, track dictionaries, product families, entity universe | `CURRENT` |
| `tests/` | 105 | Offline suite: 47 `test_*.py` modules, 1,074 unittest checks, synthetic fixtures | `CURRENT` |
| `docs/` | 60 | Methodology, schema contract, data notes, assumptions, calibration, plus the **published GitHub Pages site** (`index.html`, `dashboard.html`, `replay*.html`, PNGs) | `CURRENT` + `GENERATED` |
| `docs/research/` | 18 | Foundation ADRs, TKG acceptance/hardening, forecast registry ADR, audit reports | `HISTORICAL` / `CURRENT` reference |
| `research/` | 116 | Programme charter and rules (`MISSION.md`, `DATA_PROVENANCE.md`, `DECISIONS.md`, `HYPOTHESES*.md`, `PREDICTION_PROTOCOL.md`, `LAYERS.md`), the `RESULTS/` cycle log (46 files), `forecasts/`, `STATE.json`, `ROADMAP.md`, and `research/studies/` | `CURRENT` (rules) + `HISTORICAL` (logs) + `FROZEN` (studies) |
| `research/studies/early_signal_5firms/` | 50 | The only study on `main`: protocols, pre-registration, results, human-review worksheet, decision log | `FROZEN` |
| `papers/` | 32 | Three draft papers + machine-checked claim maps + verification scripts | `HISTORICAL` (drafts, unsubmitted) |
| `experiments/` | 657 | Frozen experiment scripts and outputs (`b026…b098`, `detect_v1`, `cycle2_coverage`, `reverse_rd_v1/v2`); 91 committed `.log` files are run records | `HISTORICAL` / `FROZEN` |
| `scripts/` | 13 | Operational entry points (backfill, corpus, nightly, forecast cycle, TKG import, agents) | `CURRENT` |
| `tools/` | 15 | Governance/audit scripts, round-end gate, plus one-off `update_state_cycle*.py` mutators and their logs | `CURRENT` + `OBSOLETE_CANDIDATE` |
| `verifier/` | 22 | Acceptance-run records (`runs/001…013`) and the v1 criteria/verify script | `HISTORICAL` |
| `.github/` | 8 | `ci.yml` (PR-triggered, no path filter), `forecast-cycle.yml`, `live.yml`, `weekly.yml` (cron/dispatch), issue/PR templates | `CURRENT` |
| root | 9 | `README.md`, `README.zh-CN.md`, `ROADMAP.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `LICENSE`, `MANIFEST.in`, `pyproject.toml`, `.gitignore`/`.gitattributes` | `CURRENT` |

Runtime directories, **not in git**: `data/` (8.9 GiB), `out/` (448 MiB), `logs/`, `build/`,
`__pycache__/`, `*.egg-info/`, `.pytest_cache/`.

### Branches and pull requests

19 remote branches; 6 open PRs (5 draft + 1 conflicting). The five feature/research PRs form a chain
`main → #12 → #13 → #14 → {#15, #16}`. Most other branches are ancestors of `main` (already merged) or
content-identical to it. Three branches carry unique unmerged work and must not be pruned:
`research/temporal-knowledge-graph`, `research/early-signal-ai-review`, `research/full-history-v1`.
Full table and recommended dispositions: [PROJECT_STATUS.md](PROJECT_STATUS.md) §4.

---

## 3. Where the actual mainline is — and what is only history

**The mainline is:** *public-source collection with a point-in-time event model → track/company
metrics → evidence-carrying reports → frozen-protocol studies that test whether any of it predicts
technology change early.*

The load-bearing artifacts are therefore: `medradar/` (the instrument), `research/` (questions,
provenance rules, decisions), `research/studies/early_signal_5firms/` (the one completed study),
`papers/` (the written record), and the offline test suite that keeps the instrument honest.

**Historical exploration, not current direction** — these are evidence assets to preserve and cite, not
programmes to resume:

- `experiments/` (657 files) and `research/RESULTS/cycle*.md` (44 cycle reports): an autonomous research
  log. Many entries are retractions or null results. Valuable as a record; not a roadmap.
- `papers/` — three drafts, not submitted.
- `verifier/runs/`, `tools/*.log`, `tools/update_state_cycle*.py` — acceptance and state-maintenance
  records from earlier rounds.
- The Market-to-R&D / Reverse R&D lane (`docs/PHASE1-3`, `experiments/reverse_rd_v1/v2`) — completed;
  its own result is "no added source produces a detectable ranking gain".
- `docs/research/` ADRs — historical design records; still the reference for the TKG/registry contracts.

**Draft/unmerged, visible only on branches:** S-028 (PR #15), S-029 (PR #16), Live Observatory
(PR #13), Reliability programme (PR #14), MedRadar 2.0 product surface (PR #12). A reader of `main`
cannot see them — this is the single most confusing property of the repository, and it is why
`PROJECT_STATUS.md` annotates every entry with its branch.

**Genuinely obsolete-looking but retained:** the `experiments/b026…b098` numbering, the `b0xx` scripts,
and the cycle log look like clutter but are the audit trail for claims in `papers/`. Deleting them would
silently break claim provenance. Retained.

---

## 4. Redundancy and structural findings

| # | Finding | Evidence | Action |
|---|---|---|---|
| 1 | **Three overlapping roadmaps** | root `ROADMAP.md` (shipped-version checklist), `research/ROADMAP.md` ("plan of record", 36 cycles), README "Roadmap" section, plus `research/BACKLOG.yaml` | Documented; the single current roadmap now lives in `PROJECT_STATUS.md` §6. Files not deleted — each is a historical/component record that still has value. **Human decision needed** whether to convert the others into links. |
| 2 | **Two parallel results namespaces** | `research/RESULTS/` (cycle log, main) vs `docs/research/` (ADRs and acceptance reports) vs `research/` top level | Documented in the map above. No files moved: study/claim paths must stay stable. |
| 3 | **`main` cannot see its own newest science** | S-028/S-029 live only in draft PRs #15/#16; `main`'s `docs/report_en.md` is a generated product snapshot with no study summary | Mitigated by the README "Research Findings" section and `PROJECT_STATUS.md` §3 linking to the PRs. Merging the research PRs is a human decision. |
| 4 | **README numbers that no record supported** | "678 offline tests" (actual: 1,074), "1.2 GiB SQLite" (actual 1,368,469,504 B = 1.27 GiB), AdCom "in one feed" while it parses zero meetings, "verifies matured windows" while none matured, a 25-item calibration pilot presented as an accuracy result, "predicts future R&D milestones" contradicted by the lane's own ablation | **Fixed** in the rewritten `README.md` / `README.zh-CN.md`: verified numbers only, experimental items labelled experimental, negative results stated as negative. |
| 5 | **Documented test count out of sync across documents** | 678 (README), 913 (COMPLETION_REPORT), 795 (STATE.json), 1,065 `def test_` in the tree, 1,074 at runtime, 1,232/1,316 in two PR descriptions | README now states the **runtime** number (1,074 checks, 3 skipped) measured in this pass; other documents left as historical. Future counts should cite `medradar selftest` output. |
| 6 | **Triplicate description of the same product** | `README.md` / `README.zh-CN.md` each carried a full 400-line product manual (duplicated, drifting; the Chinese one still said "weekly automatic update" which never ran) | English README is now the maintained document; the Chinese README is a deliberate ~70-line summary pointing to it. **This is the most important reduction of maintenance surface in this pass.** |
| 7 | **Committed compiled bytecode in a research branch** | `research/studies/relation_network_s029/code/__pycache__/*.pyc` (3 files) and two scratch scripts `_patch_len.py`, `_patch_strict2.py` on the S-029 branch | Not on `main`, so not touched. **Recommendation:** remove in PR #16 — it contradicts `.gitignore` (`__pycache__/`) and it is not evidence. |
| 8 | **Nested duplicate doc path** | `docs/docs/ASSUMPTIONS.md` (identical to `docs/ASSUMPTIONS.md`) exists only on PR #1's branch | Recorded. `main` is clean. Resolve when PR #1 is closed. |
| 9 | **Two names for one derived DB** | `data/product_entity_map.sqlite` ≡ `data/medradar.product_entity_map.sqlite` (identical bytes) | Runtime artifact; kept. Recorded as a cleanup candidate in `DATA_ASSET_REGISTER.md`. |
| 10 | **No CI gate** | `main` is unprotected: no required checks, no rulesets. `ci.yml` has no `paths` filter, so a docs-only PR still runs 3 Linux + 1 Windows jobs — a run, but not a gate. | Recorded in `PROJECT_STATUS.md` §4. Enabling branch protection is a **human decision**; not changed here. |
| 11 | **Pages configuration contradicts a workflow's assumption** | GitHub Pages is `build_type: legacy`, source `main:/docs`; `weekly.yml` deploys with `configure-pages`/`deploy-pages`, which presumes "Source: GitHub Actions" | Recorded. Do **not** move/delete `docs/` content — it is the live site. |
| 12 | **Licence detector mismatch** | `LICENSE` is MIT + an appended data-notice paragraph → GitHub reports "Other" while `pyproject.toml` says `MIT` | Documented in README's licence section. Editing licence text is a **human decision**, not a maintenance edit. |
| 13 | **`doctor` can turn 3 skips into 3 errors** | `python -m medradar doctor --offline` creates an empty `data/medradar.sqlite`; three local-store artifact tests guard with `if not Path(DEFAULT_DB).exists(): skipTest(...)`, so once the 0-byte file exists they stop skipping and error on an empty DB. Reproduced in this pass. | Not fixed: it is a test-guard/code change, not documentation. Workaround is in the README getting-started block. **Suggested fix:** guard on `is_file() and st_size > 0`, or have `doctor` probe without creating the file. |

---

## 5. Cleanup record — what was actually changed or deleted

**Deleted: nothing.** No file was removed, moved or renamed, in this pass.

Reason: the tracked tree on `main` is already clean. Verified checks:

- `git ls-tree origin/main` contains **0** `__pycache__`, **0** `.pyc`, **0** `*.sqlite`/`*.db`,
  **0** `build/`, `out/`, `logs/` or `data/` entries.
- Hash-based duplicate detection on `main` found 6 groups totalling **4,572 B** — two generated snapshot
  `summary.json`, four identical selfcheck logs, one tiny device fixture JSON duplicated, and 9 empty
  files. None is worth deleting: the logs are run evidence and the fixtures are test inputs.
- The 91 committed `.log` files under `experiments/`, `papers/`, `tools/` are run records referenced by
  the experiment directories that produced them. Removing them would break reproducibility traces.
- `docs/` is the published GitHub Pages site; removing "unused" images or HTML can break it.

**Changed files in this pass**

| File | Change |
|---|---|
| `README.md` | Rewritten as the research-first front page: mission/question, honest capability status, data sources, research findings (negative results), architecture, verified getting-started, structure, reproducibility, limitations, one roadmap, licence/provenance. Removed unverifiable numbers and unmerged-capability claims. |
| `README.zh-CN.md` | Reduced from a 408-line duplicated product manual to a maintained ~70-line summary that points at `README.md` and the three governance documents. |
| `docs/PROJECT_STATUS.md` | **New** — the single status overview: capability buckets, research index with fixed status vocabulary, PR/branch state, roadmap, open human decisions. |
| `docs/DATA_ASSET_REGISTER.md` | **New** — data asset table with measured sizes and provenance; explicit answers for operational DB vs historical research dataset vs frozen experimental dataset vs observation ledger vs backup archive; duplicates, large-file governance, licensing, backup/restore status, regeneration honesty. |
| `docs/REPOSITORY_AUDIT.md` | **New** — this file. |
| `tests/test_release.py` | **One test guard updated** (not a behaviour change): `test_readme_test_count_is_not_stale` required a 3-digit count between 400 and 900, so it silently sanctioned the stale "678 offline tests" and would have *failed* a truthful count (the suite runs 1,074). The guard now compares the advertised number with a tolerance band derived from the number of `def test_` functions in `tests/`. Without this, a corrected README cannot pass CI. |

`.gitignore` was reviewed and **left unchanged**. It already covers every runtime directory and every
generated artifact class this project produces (`data/`, `out/`, `__pycache__/`, `*.py[cod]`,
`*.egg-info/`, `.venv/`, `build/`, `dist/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`,
`.audit/`, `*.xlsx`, `experiments/**/pred_*.json`). Two traps worth knowing rather than "fixing":

- `*.xlsx` silently ignores the human-review workbook that a merged PR (#11) described as delivered. It
  is generated from `HUMAN_REVIEW_WORKSHEET.csv` by `experiments/b097/build_review_xlsx.py`; the **CSV
  is the record**, so the workbook is correctly untracked. Do not force-add it.
- `logs/` is not ignored on `main` because nothing on `main` writes there (only the observatory branch
  does, and that branch ignores it). If a main-branch command ever writes `logs/`, add it then.

---

## 6. What needs a human decision

Carried from [PROJECT_STATUS.md](PROJECT_STATUS.md) §7 — the same ten items, most urgent first:

1. Complete the **69-packet human adjudication** (five-firm study). Nothing downstream can be scored
   without it.
2. Complete the **S-029 102-row human validation** before that layer is used for anything.
3. Fix **PR #12's CI** (install `.[dev]` in the legacy `ci.yml` jobs, or make `selftest` skip
   pytest-style modules).
4. Decide the fate of **PR #1** (`SUPERSEDED_CANDIDATE`, conflicting).
5. **Branch cleanup** on GitHub (only merged/superseded refs; keep the three unique-work branches).
6. Publish the **seven-day validation outcome** after 2026-11-10 as it actually ended.
7. Confirm the **S-028 corrected wording** is the version of record.
8. Decide whether to move the **data notice out of `LICENSE`** so GitHub detects MIT.
9. Decide **retention/redistribution** for S-029's raw payloads and remove its tracked `__pycache__`
   before any merge.
10. Decide whether to keep the **uncommitted owner edits** in `HUMAN_REVIEW_WORKSHEET.csv` (left
    untouched) and the uncommitted changes in the `study-early-signal` worktree.

---

## 7. Multiplicity of management documents — deliberately limited

This pass adds exactly **three** documents and rewrites **two** READMEs. It does not create per-topic
policy files, generated documentation sites, or parallel status pages. When status changes, edit these
files in place.

If the project later outgrows this, the correct move is to delete a document, not add another.
