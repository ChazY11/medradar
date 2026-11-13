# README scientific-consistency audit — final merge gate (Task 4)

**Task:** `task-23` · REFOUNDATION-003 final merge gate · auditor `comms-lead`
**Candidate:** `<WORKTREE>`, branch `integration/ref003`,
HEAD **`cfa685c`** (PR #38 candidate)
**Mode:** read-only audit. **No README, no tree file was edited.** This report is the only output.
**Report location:** `<EVIDENCE_OUT>\README_CONSISTENCY.md`
(outside every git worktree — per Lead instruction, because untracked evidence files in a worktree
break `test_check_licence::test_current_repository_is_clean` during concurrent runs).
**Audit time:** 2026-11-13T04:39–04:52 +08:00.

---

## 0. Scope / Method / Evidence base / Limits

**Scope.** `README.md` (277 lines) and `README.zh-CN.md` (240 lines) on the candidate: every numeric
claim, every capability-status claim, every version claim, the negative-results block, the image
caption, and the "what is / is not released" boundary. Plus the three files the README must agree
with: `pyproject.toml`, `medradar/__init__.py`, `PROJECT_STATE.yaml`, and the release plan in
`docs/refoundation/phase3/PHASE3_ACCEPTANCE.md`.

**Method.** (a) run the merged suite; (b) query live PR state; (c) recompute every metric from the
committed artefact that the README cites; (d) diff the README's version/status facts against their
single sources; (e) check the two "must be adjacent" fields (time limitation next to the 60-day
return; snapshot/version/not-live next to the screenshot).

**Commands used (reproducible).**

```bash
python -m pytest -q -o addopts=""                     # merged suite
python -m pytest tests/test_release.py -q -o addopts=""   # the README guard alone
gh api "repos/ChazY11/medradar/pulls?state=open&per_page=100" --jq 'length'
gh api "repos/ChazY11/medradar/pulls?state=closed&per_page=100" --jq '[.[]|select(.merged_at!=null)]|length'
python -c "import json;m=json.load(open('docs/metrics.json'));print(m['trading']['event_study'])"
```

**Evidence base.** `docs/metrics.json` (generated 2026-10-30T19:23:33Z), `docs/DATA.md` (generated),
`experiments/reverse_rd_v2/ablation_metrics.json`, `CHANGELOG.md`, `PROJECT_STATE.yaml`,
`docs/refoundation/phase3/PHASE3_ACCEPTANCE.md`, `docs/refoundation/phase3/PR_TRIAGE.md`,
`docs/refoundation/phase2/E1{B,VIDENCE_CORE_V1}.md`.

**Limits.**
1. **The suite result below is contaminated by the working tree, not by the commit.** Two untracked
   files exist in the worktree (see §1); on a clean checkout of `cfa685c` the expected result is
   1,145 passed / 3 skipped. I report both numbers and label which is which.
2. `gh` counts are a point-in-time read; they change the moment #38 merges (§F1).
3. I did not verify the Chinese text semantically against the English sentence-by-sentence; I checked
   structural parity and every numeric/status fact.
4. `docs/preview.png` renders were not inspected; only its presence, size and caption were verified.

---

## 1. Environment blocker (not a tree defect — Lead is handling it)

```
docs/refoundation/phase3/_evidence/data_safety/data_safety_final.json   (untracked, 18,197 B)
docs/refoundation/phase3/_evidence/data_safety/scan_history.py         (untracked)
```

`check_licence` scans **untracked data files by design**, so their presence makes
`tests/governance/test_check_licence.py::RealRepositoryBaselineTests::test_current_repository_is_clean`
fail:

```
1 failed, 1144 passed, 3 skipped, 224 subtests passed in 67.20s
FAILED tests/governance/test_check_licence.py::...test_current_repository_is_clean
  [FAIL] untracked.data_file: ... data_safety_final.json ... add it (with inventory) or remove it
```

**Interpretation.** 1,144 + 1 + 3 = **1,148 collected**, which matches the expected total exactly; the
single failure is the untracked-file check, not a README claim. **The README's 1,145/3/0 is correct for
the committed tree.** This audit therefore does **not** raise a FIX against the README for it — but the
merge gate must ensure clean-tree CI (either remove those files, or commit them **with** a
`DATA_LICENSES` inventory entry). Lead has been notified and is relocating the artifacts.

---

## 2. Verdict summary

| Verdict | Count |
|---|---|
| Claims checked | **24** |
| **PASS** | 17 |
| **FIX — blocking on merge** | **5** (F1, F2, F4, F5, F6) |
| **FIX — should fix in the same PR** | 4 (F3, F7, F8, F9) |
| **Post-merge step** (not a diff) | 1 (F10) |
| Claims that are **unverifiable** on this tree | 0 (one had an unsourced number → F6) |

Blocking rationale: F1 states a fact that is wrong **right now**; F2 makes the release metadata
contradict the release plan; F4/F5 are explicit gate items (adjacency of the time limitation; negative
results intact); F6 violates "no invented numbers" (an unsourced figure).

---

## 3. Claim-by-claim table

Locators are 1-based lines in the candidate. `en` = `README.md`, `zh` = `README.zh-CN.md`.

| # | Claim | Locator | Source checked | Verdict |
|---|---|---|---|---|
| C1 | Package version `0.5.0`, "pyproject.toml, the only source" | en:21, en:38, zh:16 | `pyproject.toml:3` = 0.5.0; `medradar/__init__.py` = 0.5.0; `PROJECT_STATE:35` = 0.5.0 | **PASS** (internally consistent) — see **F2** for RC mismatch |
| C2 | `1,148 offline tests (1,145 passed, 3 skipped)` | en:22, zh:17 | merged suite = 1,148 collected; clean-tree 1,145 passed / 3 skipped; measured here 1,144 passed + 1 env failure + 3 skipped | **PASS** (see §1) |
| C3 | `1,145 passed, 3 skipped, 0 failed (1,148 collected)` | en:39 (generated block) | same as C2; `PROJECT_STATE` tests block | **PASS** (see §1) |
| C4 | `python -m pytest -q -o addopts=""` guard passes | en:217 | `tests/test_release.py` → 8 passed | **PASS** |
| C5 | Data snapshot `2026-10-31`, 375,378 events, 1.3 GiB | en:23, en:42, zh:18 | `docs/DATA.md:23` (375,378), `DATA.md:36` (1.3 GiB = 1,368,469,504 B), `PROJECT_STATE:57-60` | **PASS** |
| C6 | `Open PRs: 23 open (22 draft), 10 merged` | en:43 | `gh api …state=open` → **28 open / 27 draft**; closed+merged → 10 | **FIX F1** |
| C7 | `Capabilities: 7 working · 6 draft · 1 retired` | en:40 | `PROJECT_STATE.yaml` capability `status:` counts = 7/6/1 | **PASS** |
| C8 | Ingest capability "working — counts reproduce from live sources" | en:57, zh:31 | `medradar/collect_*.py`, `medradar/intelligence/` present; tests cover collectors | **PASS** |
| C9 | Event store `working` | en:58 | `medradar/db.py` present, tested | **PASS** |
| C10 | Revision ledger "working … explicitly not tamper-proofing" | en:59 | `medradar/evidence_core/` present; `tests/test_event_revision.py`, `tests/test_evidence_core.py`; `EVIDENCE_CORE_V1.md` §1 states the same limitation | **PASS** |
| C11 | Entity resolution "partial — ~35 % company key, **~11 % auditable basis**" | en:60, en:196, zh:34, zh:166 | `docs/DATA.md:70` = 35.2 % company_key; `DATA.md:71` = 52.4 % track_id. **No source for 11 %** anywhere on the tree | **FIX F6** |
| C12 | Track heat "descriptive only" | en:61, zh:35 | `medradar/analyze.py`; no out-of-sample claim anywhere | **PASS** |
| C13 | Event study/replay/book "working, simulation — in-sample, long-only, not investment advice" | en:62, zh:36 | `medradar/{eventstudy,replay,paper}.py`; `metrics.json trading.method.long_only = true` | **PASS** |
| C14 | Bitemporal store "mechanism only" | en:63 | `medradar/tkg/`; limitation consistent with C22 | **PASS** |
| C15 | Forecast registry "25 registered, 0 matured, `insufficient_matured_forecasts`" | en:64, zh:38 | `CHANGELOG.md:38` (25 nowcasts), `docs/PHASE3.md:42`, `PHASE3_REGISTRY.md:229` | **PASS** |
| C16 | Research agent "working … no causality" | en:65 | `medradar/research_agent.py` present, tested | **PASS** |
| C17 | `#12–#30 not released` boundary block | en:68-70, zh:42-44 | `PROJECT_STATE` branch-only list; `PR_TRIAGE.md`; no #12–#30 path exists in `medradar/` | **PASS** |
| C18 | 60-day event study: n=61, +5.65 %, t=2.45, CI [+1.35, +10.32] | en:148, zh:122 | `docs/metrics.json trading.event_study["60"]`: n=61, mean=5.6485 %, t=2.4545, ci95=[1.3547, 10.3198] | **PASS** (numbers) — **FIX F4** (adjacency) |
| C19 | 1/5/20-day rows | en:145-147, zh:119-121 | metrics.json: +0.1456/−0.3677/+1.1375 %, t .5733/−.9155/1.1706, CIs match to 2 dp | **PASS** |
| C20 | "38 trades over ~11 months" | en:204 | `metrics.json trading.summary`: n_trades=38, 2025-11-21 → 2026-10-30 | **PASS** |
| C21 | M2RD: ΔPR-AUC −0.0013/−0.0015/−0.0001/−0.0068; AP 0.7935 vs 0.7913, Δ +0.0022, CI [−0.032,+0.037]; ECE 0.0811→0.0628; FPR 0.2753→0.2472 | en:162-165, zh:135-137 | `experiments/reverse_rd_v2/ablation_metrics.json` contains 0.7934764, 0.7912589, 0.0811203, 0.0627768, 0.2752809, 0.2471910, 0.0022176 (all match at 4 dp). The two ablation deltas `−0.0015` and `−0.0068` are **not** numeric fields of that JSON (checked: 0 exact matches) — they are stated verbatim in `docs/PHASE2.md:46` (and `CHANGELOG.md`). Traceable, but to a prose record rather than the machine artefact | **PASS** (with the note above) |
| C22 | Event-time-only limitation, `375,378 / 375,378`, independent public time = 0 | en:189-192, zh:159-162 | `DATA.md:73` (`timestamps: date 375,378`), `README_TRUTH_UPDATE.md` D7, `E1B_SOURCE_RECOVERY.md` §5 | **PASS** |
| C23 | E1b verdicts (EDGAR STRONG / CT.gov MEDIUM / openFDA no public time; 28 requests, 5 per source) | en:176-183, zh:150-154 | `E1B_SOURCE_RECOVERY.md` §0, §5, §8; `_evidence/e1b/summary.json` (`requests: 28`, `samples_per_source: 5`) | **PASS** |
| C24 | Image caption: dataset date + package version + "not a live service and not a forecast" | en:241,244-247, zh:207,210-212 | `docs/preview.png` exists (488,736 B); caption has all three elements in both languages | **PASS** |
| C25 | S-028 / S-029 negative results | en:68 only (listed as *not in main*), zh:42 | `PR_TRIAGE.md` rows #15/#16 both "NO-GO"; not present in the negative-results section | **FIX F5** |
| C26 | "Shipped already: v0.3.0 … v0.4.0 … v0.5.0" | en:253-255 | `CHANGELOG.md` has those releases; `ROADMAP.md` ships-lists | **PASS** |
| C27 | Zero-dependency dashboard / no external requests | en:66 | `docs/dashboard.html` single file; consistent with `report.py` | **PASS** |

---

## 4. FIX register

### F1 — Open-PR count is stale (blocking)

Live read at 2026-11-13T04:41 +08:00: **28 open (27 draft), 10 merged**; the README says
**23 open (22 draft), 10 merged** — it predates #32–#38 being opened. The row is inside the
**generated** block, so it must be fixed at the source and regenerated, never hand-edited.

```diff
--- a/PROJECT_STATE.yaml
+++ b/PROJECT_STATE.yaml
@@ open_work:
   prs:
     merged_count: 10
     merged_range: '#2-#11'
-    open_count: 23
-    open_range: '#1, #12-#33'
-    draft_count: 22
-    measured_from: "Read-only `gh pr list` on 2026-11-13: 23 open, 22 drafts, numbers 1 and 12-33."
+    open_count: 28
+    open_range: '#1, #12-#38 (re-measure immediately before merge)'
+    draft_count: 27
+    measured_from: "Read-only `gh api repos/ChazY11/medradar/pulls?state=open` on 2026-11-13T04:41+08:00: 28 open, 27 drafts."
```

Then `python tools/governance/gen_views.py` and commit the regenerated `README.md` block (+ the zh
block once F8 exists).

**Note for the merger:** the number decays instantly — after #38 merges it becomes 27 open / 26
draft. **[RECOMMENDATION]** Change the row to `Open PRs | 28 open (27 draft) as of 2026-11-13` so the
date is part of the claim, or drop the row. A bare count in a merge candidate will be wrong within
minutes.

### F2 — Package version 0.5.0 vs release candidate 0.6.0 (blocking decision)

`docs/refoundation/phase3/PHASE3_ACCEPTANCE.md` recommends a release candidate **v0.6.0-rc1**
(L21, L144) and states the version should be **0.6.0** (L148) because Evidence Core + governance gates
are a semantic-minor addition. Every other source says 0.5.0. The README, `pyproject.toml`,
`medradar/__init__.py` and `PROJECT_STATE.yaml` are mutually consistent — they are simply one release
behind the plan. Pick one:

* **Option A (recommended — matches the acceptance record): bump to 0.6.0.**

```diff
--- a/pyproject.toml
+++ b/pyproject.toml
@@
-version = "0.5.0"
+version = "0.6.0"
--- a/medradar/__init__.py
+++ b/medradar/__init__.py
@@
-__version__ = "0.5.0"
+__version__ = "0.6.0"
--- a/PROJECT_STATE.yaml
+++ b/PROJECT_STATE.yaml
@@ main:
-  version: "0.5.0"
+  version: "0.6.0"
--- a/README.md
+++ b/README.md
@@ -21 +21 @@
-| Package version | `0.5.0` (`pyproject.toml`, the only source) |
+| Package version | `0.6.0` (`pyproject.toml`, the only source) |
--- a/README.zh-CN.md
+++ b/README.zh-CN.md
@@ -16 +16 @@
-| 包版本 | `0.5.0`（以 `pyproject.toml` 为唯一来源） |
+| 包版本 | `0.6.0`（以 `pyproject.toml` 为唯一来源） |
```

  …then `CHANGELOG.md` needs a `## [0.6.0]` section (the guard
  `test_changelog_has_current_release` asserts `[<version>]` is present), and the generated README/zh
  status blocks must be regenerated (they render `Version` from the state file).

  ⚠ **Do not bump the image caption (§F-C24).** The screenshot was produced by the 0.5.0 dashboard;
  `README.md:241,244` and `zh:207,210` say `package v0.5.0` because that is the generator version. If
  the release is 0.6.0 either keep the caption as the *generating* version and say so, or regenerate
  the image with `medradar dashboard` at 0.6.0 and update both. Bumping the caption without
  regenerating would falsify provenance — the one thing this repository cannot afford.

* **Option B:** keep 0.5.0 and amend `PHASE3_ACCEPTANCE.md` L21/L144/L148/L167 to say the RC is
  `v0.5.0` (or "version unchanged; no release tag in this PR"). Cheaper, but it drops the semantic
  minor that the acceptance record argues for.

### F3 — `pyproject.toml` description is still the old marketing line (should fix, 1 line)

Shown on PyPI/GitHub; contradicts the new mission paragraph (README:3-9).

```diff
--- a/pyproject.toml
+++ b/pyproject.toml
@@
-description = "FDA device & drug industry radar: big-pharma pipeline direction, China-gap comparison, and paper-trading event study."
+description = "An evidence-first research project on whether public regulatory, trial and filing evidence gives reliable early warning of change in medical-technology development."
```

### F4 — The 60-day result is not adjacent to the time-data limitation (blocking)

Gate item: *"the 60-day event-study figure must carry the adjacent event-time/no-independent-public-time
limitation"*. Currently the only adjacent qualifier is "in-sample … no out-of-sample claim"
(en:150-152, zh:124-125); the event-time/public-time limitation sits 37 lines later in `## Limitations`.
A reader who stops at the table reads a return number with no time caveat.

```diff
--- a/README.md
+++ b/README.md
@@ -150,3 +150,5 @@
-Source: `docs/metrics.json` → `trading.event_study`, generated 2026-10-30, snapshot window
-2025-11-21 → 2026-10-30. This is the simulation lane; it is in-sample and makes no out-of-sample
-claim.
+Source: `docs/metrics.json` → `trading.event_study`, generated 2026-10-30, snapshot window
+2025-11-21 → 2026-10-30. **Two limits apply to every figure above:** it is **in-sample** (a
+simulation, no out-of-sample claim), and it is **event-time only** — the snapshot carries
+independent public time for **0 of 375,378 rows**, so these returns assume the event date is the
+public date. See [Limitations](#limitations) items 1–2 before quoting any of them.
--- a/README.zh-CN.md
+++ b/README.zh-CN.md
@@ -124,2 +124,4 @@
-2026-10-30。这是模拟层的结果：样本内，不作样本外声明。
+2026-10-30。**上表每个数字都受两项限制**：其一为**样本内**（模拟，不作样本外声明）；其二为
+**仅事件时间**——该快照 375,378 行中**独立公开时间为 0 行**，因此这些收益假设「事件日 = 公开日」。
+引用任何数字前请先读「局限」第 1–2 条。
```

### F5 — S-028 / S-029 NO-GO results are missing from the negative-results block (blocking)

Gate item: negative results must be intact (M2RD, S-028/S-029, no matured prospective). M2RD (en:154-168)
and "no matured prospective" (en:64) are present; S-028/S-029 appear only in the *not-in-main* list
(en:68), never as a result. Both are **draft-branch** studies, so the fix must say that explicitly.

```diff
--- a/README.md
+++ b/README.md
@@ after the Early-signal study paragraph (line 172)
+**S-028 / S-029 relation-reconstruction studies (draft branches, not on `main`).** Both were completed
+with a **NO-GO** verdict and are archived as research drafts (#15, #16) rather than merged; they are
+*not* released findings. See [`PR_TRIAGE.md`](docs/refoundation/phase3/PR_TRIAGE.md) rows #15–#16.
+
--- a/README.zh-CN.md
+++ b/README.zh-CN.md
@@ after the Early-signal paragraph (line 143)
+**S-028 / S-029 关系重建研究（草稿分支，不在 `main`）。** 两项研究均以 **NO-GO** 结论完成，作为研究草稿
+归档（#15、#16）而不合并；它们**不是**已发布的结论。见
+[`PR_TRIAGE.md`](docs/refoundation/phase3/PR_TRIAGE.md) 第 #15–#16 行。
+
```

### F6 — "~11 % auditable basis" has no source on this tree (blocking: no invented numbers)

`docs/DATA.md` (generated) supports **35.2 %** company key and **52.4 %** track; there is no 11 %
figure anywhere in the tree, and the Phase-1 document that originally carried it is not merged. Replace
the unsourced number with the two generated, citable ones.

```diff
--- a/README.md
+++ b/README.md
@@ -60 +60 @@
-| Company / subsidiary and technology-track resolution | `medradar/config.py`, `config/*.json` | **partial** — ~35 % of events carry a company key, ~11 % an auditable basis; unmatched events are reported, never guessed |
+| Company / subsidiary and technology-track resolution | `medradar/config.py`, `config/*.json` | **partial** — 35.2 % of events carry a company key and 52.4 % a track ([`DATA.md`](docs/DATA.md) L70-71); unmatched events are reported, never guessed |
@@ -196,2 +196,2 @@
-3. **Entity resolution is partial.** ~35 % of events carry a company key, ~11 % have an auditable
-   basis. Unmapped events stay unmapped and are counted; they are never guessed.
+3. **Entity resolution is partial.** 35.2 % of events carry a company key and 52.4 % a track
+   (`docs/DATA.md` L70-71). Unmapped events stay unmapped and are counted; they are never guessed.
--- a/README.zh-CN.md
+++ b/README.zh-CN.md
@@ -34 +34 @@
-| 公司/子公司与技术赛道消歧 | `medradar/config.py`、`config/*.json` | **部分** —— 约 35 % 事件带公司键，约 11 % 有可审计依据；未匹配事件如实计数，绝不猜测 |
+| 公司/子公司与技术赛道消歧 | `medradar/config.py`、`config/*.json` | **部分** —— 35.2 % 事件带公司键、52.4 % 带赛道（[`DATA.md`](docs/DATA.md) L70-71）；未匹配事件如实计数，绝不猜测 |
@@ -166,2 +166,2 @@
-3. **实体消歧只完成一部分。** 约 35 % 事件带公司键，约 11 % 有可审计依据。未映射的保持未映射并计数，
-   绝不猜测。
+3. **实体消歧只完成一部分。** 35.2 % 事件带公司键、52.4 % 带赛道（`docs/DATA.md` L70-71）。
+   未映射的保持未映射并计数，绝不猜测。
```

### F7 — Stray BOM (U+FEFF) before the generated block (should fix, 1 character)

`README.md:29` begins with `﻿<!-- BEGIN GENERATED: status -->` where the first character is U+FEFF.
It is invisible in the rendered page but it is residue from a generator write, it breaks any tool that
anchors on `^<!-- BEGIN GENERATED`, and it will be re-created unless the generator strips it.

```diff
--- a/README.md
+++ b/README.md
@@ -29 +29 @@
-﻿<!-- BEGIN GENERATED: status -->
+<!-- BEGIN GENERATED: status -->
```
(also: make `tools/governance/gen_views.py` open its outputs with `encoding="utf-8"` and no BOM.)

### F8 — The Chinese README has no generated status block (should fix: parity)

`README.md:29-47` renders a generated 12-row status block; `README.zh-CN.md` has none (a 5-row
hand-written table at zh:14-19 instead). Result: the zh reader cannot see main head, capability counts,
research-study count, open PRs or branch-protection state — and any fix to F1 lands only in English.

Minimal durable fix: teach `tools/governance/gen_views.py` to emit the same block into **both**
READMEs (translated labels, identical payload), then regenerate. Inserting the block by hand into
`README.zh-CN.md` will be overwritten at the next regeneration and is therefore a temporary patch only.

```diff
--- a/tools/governance/gen_views.py   (proposal, not applied)
@@
-TARGETS = ["README.md"]
+TARGETS = ["README.md", "README.zh-CN.md"]
+# plus a label map so the zh block renders Chinese headers with identical values
```

### F9 — Duplicated status facts (hygiene, keep README concise)

`README.md:19-25` (hand table) repeats three facts that the generated block also renders (`version`
en:21 vs en:38; `tests` en:22 vs en:39; `snapshot` en:23 vs en:42). Two sources for one number is the
drift mechanism this repository is trying to remove. Keep the hand table for facts that are **not**
generated (`Released claims`, `Licence`) and let the block own the rest. `zh:14-19` likewise.

```diff
--- a/README.md
+++ b/README.md
@@ -19,7 +19,5 @@
 | | |
 |---|---|
-| Package version | `0.5.0` (`pyproject.toml`, the only source) |
-| Test suite | **1,148 offline tests (1,145 passed, 3 skipped)** — no network, no API key (`python -m pytest -q -o addopts=""`) |
-| Data snapshot | **2026-10-31** · 375,378 events · 1.3 GiB SQLite (not committed) |
 | Released claims | descriptive event-time statistics and the negative results below — nothing else |
 | Licence | MIT |
```

⚠ If you apply F9, the literal string `N offline tests` must remain somewhere in `README.md`, because
`tests/test_release.py::test_readme_test_count_is_not_stale` requires it. It does: `en:217` in the
Reproduce block already contains `1,148 offline tests`. Re-run the guard after editing.

### F10 — Post-merge state bump (process step, not a diff)

After #38 merges, `PROJECT_STATE.yaml`'s `main.head`/`short`/`committed_at`/`commit_subject`
(L30-34) still describe `b2a14c0`; `main.head` is declared as `origin/main`, so `check_state` and
`gen_views --check` will fail on the merge commit until the bump. Also L55's note names integration
tree `96950ba` while the candidate is `cfa685c`.

Merge checklist addition:

1. merge PR #38 (merge commit),
2. update `PROJECT_STATE.yaml` main block to the new head + subject + date,
3. `python tools/governance/gen_views.py` and commit regenerated views (README ×2, `RESEARCH_INDEX.md`,
   `CHANGELOG` unreleased block),
4. `python tools/governance/check_state.py` + `gen_views.py --check` green,
5. tag `v0.6.0-rc1` (or the chosen version, F2).

---

## 5. Version decision matrix

| Source | Value | Role |
|---|---|---|
| `pyproject.toml:3` | 0.5.0 | build metadata (authoritative for the package) |
| `medradar/__init__.py` | 0.5.0 | runtime `__version__`; asserted equal to pyproject by `test_package_version_matches_pyproject` |
| `PROJECT_STATE.yaml:35` | 0.5.0 | governance source of truth; rendered into README status block |
| `README.md:21,38` · `README.zh-CN.md:16` | 0.5.0 | reader-facing |
| `CHANGELOG.md` | latest `[0.5.0]` (+ generated `[Unreleased]`) | release record; guard asserts current version present |
| `docs/refoundation/phase3/PHASE3_ACCEPTANCE.md:21,144,148,167` | **0.6.0-rc1 / 0.6.0** | release plan |
| `docs/preview.png` caption (en:241,244 · zh:207,210) | v0.5.0 | **provenance of the image**, not the release |

**Conclusion.** All five code/doc sources agree on 0.5.0; the acceptance record plans 0.6.0. That is a
**decision**, not a bug — but shipping as 0.6.0-rc1 while every file says 0.5.0 is a release-metadata
contradiction. F2 resolves it; the caption must not be bumped unless the image is regenerated.

---

## 6. Items explicitly **not** changed by this audit

* No README/`zh` line was edited; all diffs are proposals for the merger.
* The `## Limitations` block, negative-results numbers and E1b table are accurate as written — no
  softening found. M2RD "no added source produces a detectable ranking gain" is intact (en:162).
* `#12–#30` are nowhere presented as released: the only mentions are the not-in-main list (en:68-70),
  the roadmap subgraph (en:101-107) and roadmap item 5 (en:263). Verified against
  `PROJECT_STATE` branch-only list and `PR_TRIAGE.md`.
* The 2,384-case corpus study (superseded) is **not** quoted in this README at all — correct.

---

## 7. Open questions for the Lead

1. **F2: 0.6.0 or stay 0.5.0?** If 0.6.0, does the screenshot get regenerated at 0.6.0, or does the
   caption stay at the generating version (my recommendation)?
2. **F1: keep a PR count at all?** It decays within minutes of merge; a dated snapshot is the only
   honest form.
3. **F8: who owns `gen_views.py`?** Emitting the block into `README.zh-CN.md` is a tool change, not a
   docs edit — I did not touch `tools/`.
4. **§1 untracked artifacts:** if `_evidence/data_safety/*` are intended deliverables, they need a
   `DATA_LICENSES` inventory entry before the merge commit, or CI on `main` will be red for a reason
   unrelated to this README.
