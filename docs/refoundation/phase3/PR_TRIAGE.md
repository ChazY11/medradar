# PR_TRIAGE — REFOUNDATION-003 consolidation plan

> **Program:** REFOUNDATION-003 · **Owner:** `inventory-auditor` · **Date:** 2026-11-13 (Asia/Shanghai)
> **Worktree:** `D:\DEPPSKK\worktrees\rf003-triage`, branch `docs/ref003-pr-triage`, cut from `origin/main` `b2a14c0`
> **Mode:** **read-only triage.** No PR was merged, closed, deleted, retargeted or commented; no branch was pushed; no repository setting was changed.
> **Machine-readable:** [`_evidence/pr_triage.json`](_evidence/pr_triage.json) · raw metadata copy: [`_evidence/pr_metadata_raw.json`](_evidence/pr_metadata_raw.json)
> **Evidence scripts:** `_evidence/collect_pr_triage.py`, `build_triage.py`, `check_boundary.py`, `check_dup.py`

---

## 0. Scope / Method / Evidence base / Limits

**Scope.** Every one of the **27 open pull requests** in `ChazY11/medradar` at collection time: the 19 legacy PRs (#12–#30), the Phase 0–2 program PRs (#31–#37), and the still-open pre-refoundation **#1**. For each: metadata (draft/base/head/last commit), size, **server-side mergeable state**, local merge-probe, ancestry relative to other open PRs, overlap/duplication, exactly one status from the five required, a one-line reason and evidence. Then: overlap analysis, a consolidated active queue, and a merge/closure order for the next two cycles.

**Method.**

1. **PR metadata** — GitHub `GET /pulls?state=open` plus `GET /pulls/{n}` for all 27 (server fields: `draft`, `base.ref`, `head.ref`, `mergeable`, `mergeable_state`, `additions`, `deletions`, `changed_files`, `updated_at`). Collected 2026-11-13. [FACT]
2. **Local corroboration** — every head branch is present in the local object store; `git diff --numstat origin/main...origin/<head>` and a **read-only** `git merge-tree --write-tree` were run for each. The API `mergeable` flag and the local probe agree except where noted (#1 conflicts locally too). [FACT]
3. **Ancestry** — `git merge-base --is-ancestor` for all 27×27 open-head pairs. Declared `base` is treated as a *display choice*, never as a fact about the graph. [FACT]
4. **Overlap/duplication** — blob-SHA comparison of files added vs `main` against the other open heads; plus the REFOUNDATION-001 audit's measured copy volumes where still applicable (the branches have not moved). [FACT]
5. **Licence/restricted-data** — path-level scan against restricted source families plus the **branch-committed licence registers** (`research/data_expansion/registry/sources/*.json`) and the CONVERGENCE licence review. Not a legal opinion. [FACT for the declarations; judgement for the classification]
6. **Doctrine** — every non-obvious claim is labelled **[FACT]**, **[INFERENCE]**, **[RECOMMENDATION]** or **[UNVERIFIED]**. PR prose is never trusted: bodies are quoted as *claims*, and statuses rest on git objects/API fields.

**Evidence base.**

| Evidence | Proves |
|---|---|
| `_evidence/pr_triage.json` | 27 records: API metadata + local diff/merge/ancestry + status/reason/evidence/action |
| `_evidence/pr_metadata_raw.json` | unmodified collector output, including path samples and body excerpts |
| `git merge-base --is-ancestor` (all pairs) | topology; e.g. #19/#20 are ancestors of #21/#22; #29 is **not** an ancestor of #30 |
| `git merge-tree --write-tree` | only #1 conflicts; all #12–#37 merge textually clean into `main` |
| blob identity (`check_dup.py`) | #37's four copied reports are **byte-identical** to #32/#34/#35/#36 |
| branch licence registers + `docs/convergence/LICENCE_AND_SECURITY_REVIEW.md` | #27/#29 restricted-data exposure; #30 sanitised |
| REFOUNDATION-001 audit (`BRANCH_PR_AUDIT.md` §7) | #21/#22 duplication (560/600), #29/#30 duplication (654/813), #1 supersession, PHOENIX local divergence |

**Limits.**

1. **Snapshot.** GitHub state is as of 2026-11-13; PRs could have changed after collection. Re-collect before acting.
2. **No branch execution.** Test counts in PR bodies (e.g. #32 "1,071 passed / 3 skipped", #35 "1,099 passed") are **claims**, not re-run. The only measured baseline available is REFOUNDATION-001's `main` suite: 1,074 collected, exit 0.
3. **Mergeable ≠ safe.** `mergeable=true` is textual/graph mergeability; it does not detect hidden ancestry imports, duplicated trees, or licence contamination. Those are handled explicitly in §4–§5.
4. **Licence classification is path-based.** No content scan of binaries/archives or history was performed; #29's already-public exposure is reported, not remediated.
5. **No deep re-audit.** Per the task, Phase-0 facts and PR metadata are used rather than re-deriving the whole repository; where a deeper fact is needed (#37 blob identity, #27 licence register, #29 restricted boundary) it was measured directly and cited.
6. **Dates** are local (+08:00); GitHub `created_at`/`updated_at` are UTC.

---

## 1. Executive summary

| Metric | Value |
|---|---|
| Open PRs | **27** (all collected; `open_issues_count` = 27) |
| Drafts | **26** — every open PR except **#1** is a draft [FACT] |
| Mergeable (API) | **26 true**; **#1 false / `dirty`** [FACT] |
| Non-clean mergeable states | #1 `dirty`; **#12, #19, #20 `unstable`** (not merge-blocking but CI/checks not green) |
| Largest open PR | **#29** 691 files / +692,975; **#30** 815 files / +690,079; **#22** 600 files / +303,926 |
| Smallest open PR | **#18** 4 files / +575; **#33** 4 files / +12,049 (one 503-line doc + large evidence JSON) |
| PRs with hidden ancestry | #13, #14, #15, #16, #20, #21, #22, #25 (declared base or ancestry carries unmerged stacks) |
| PRs with duplicated content | **#22** (560/600 from #21), **#30** (721/813 from #29/#28), **#37** (4/5 identical copies) |
| BLOCKED_LEGAL | **#27, #29** |
| Status counts | **READY_TO_INTEGRATE 6 · NEEDS_REWORK 6 · RESEARCH_ARCHIVE 9 · BLOCKED_LEGAL 2 · SUPERSEDED 4** |

**Three headline judgements.**

1. **[FACT]** The repository is not "27 competing PRs". It is **one active engineering spine (#31–#36), one duplicate acceptance bundle (#37), two legally blocked research PRs (#27/#29), four superseded PRs (#1/#17/#23/#37), nine research records (#15/#16/#18–#20/#22/#24–#26), and six rework items left from the pre-refoundation product program (#12–#14/#21/#28/#30).**
2. **[INFERENCE]** Nothing in the Phase 0–2 set is blocked by another PR's content; the six READY PRs are all `main`-based, clean, and independent. The only ordering constraints are semantic: #33 is the decision record that #35 implements, and #32 defines the state-bump gate every later merge must satisfy.
3. **[FACT + RECOMMENDATION]** Both legal flags are about **data**, not code: #29 ships the bulk UN Comtrade raw payload; #27 ships Comtrade preview samples. #30 is the **sanitised** version of #29 and is *not* legally blocked — it needs de-duplication, not a licence hold.

---

## 2. Status legend

| Status | Meaning in this triage | Required owner action |
|---|---|---|
| **READY_TO_INTEGRATE** | Can merge after normal review; no known blocker. | Review → merge in the proposed order. |
| **NEEDS_REWORK** | Keep open; must be rebased/split/redesigned before it can merge. | Do not merge this cycle. |
| **RESEARCH_ARCHIVE** | Research record; keep the branch, close/mark the PR; never merge to `main`. | Close or label; preserve evidence. |
| **BLOCKED_LEGAL** | Contains restricted/licence-encumbered data. | Must not merge until stripped or cleared. |
| **SUPERSEDED** | Its content is already on `main`, or replaced by newer work. | Close (after any rescue). |

**No PR was closed by this task.** Every status is a **[RECOMMENDATION]**.

---

## 3. Full triage table (27 rows)

`Last` = last commit date (local +08). `Files/+/−` are the **server-side PR counts** (`changed_files`/`additions`/`deletions`), i.e. what a reviewer sees. `Mergeable` is the API flag/state. Reason is one line; full evidence is in `_evidence/pr_triage.json`.

| PR | Title (abbreviated) | Draft | Base → Head | Files | +/− | Mergeable | Status | One-line reason |
|---:|---|:--:|---|---:|---:|---|---|---|
| #1 | Add frontier device intelligence and research safeguards | – | `main` → `feat/frontier-device-radar` | 44 | +2,709/−234 | **false / dirty** | **SUPERSEDED** | Feature already on `main`; 154 behind; 11-path conflict; only 5 verifier artefacts are net-new. |
| #12 | MedRadar 2.0 MVP (company/radar/analyst/evidence) | D | `main` → `feat/medradar-2.0-mvp` | 57 | +17,646/−1 | true / **unstable** | **NEEDS_REWORK** | Product-stack base of 10 open PRs; never accepted under refoundation governance. |
| #13 | Live Observatory v1 (observation ledger) | D | `feat/medradar-2.0-mvp` → `feat/live-observatory-v1` | 57 | +31,301/−7 | true / clean | **NEEDS_REWORK** | Stacked on #12; must follow it or die with it. |
| #14 | Observatory Reliability (persistence/backups) | D | `feat/live-observatory-v1` → `feat/observatory-reliability-v1` | 54 | +22,899/−71 | true / clean | **NEEDS_REWORK** | Last reviewable product PR; base of the research stack (#15/#16). |
| #15 | S-028 temporal-graph early signal (NO-GO) | D | `feat/observatory-reliability-v1` → `research/s028-temporal-graph-early-signal` | 86 | +114,442/−0 | true / clean | **RESEARCH_ARCHIVE** | Negative-result study, title says do-not-merge; its tip is an ancestor of `phase4-base`/#21/#22. |
| #16 | S-029 evidence-based relations (NO-GO) | D | `feat/observatory-reliability-v1` → `research/s029-evidence-based-relations` | 205 | +133,237/−0 | true / clean | **RESEARCH_ARCHIVE** | NO-GO study; includes 130 raw CT.gov `.json.gz` dumps that must not enter `main`. |
| #17 | Repository consolidation (docs/data assets) | D | `main` → `maintenance/repository-consolidation` | 6 | +947/−805 | true / clean | **SUPERSEDED** | Pre-refoundation status/audit docs and README edits replaced by #31/#32/#34. |
| #18 | AI evidence review of 69 packets (machine) | D | `main` → `research/ai-evidence-review` | 4 | +575/−0 | true / clean | **RESEARCH_ARCHIVE** | Machine review, explicitly not human truth; research record only. |
| #19 | local-LLM Phase 2 (Qwen3-4B GPU run) | D | `main` → `research/local-llm-foundation` | 110 | +32,464/−0 | true / **unstable** | **RESEARCH_ARCHIVE** | GPU claims unverifiable from git; ancestor of #20/#21/#22. |
| #20 | overnight QLoRA S-030 (do-not-merge) | D | `research/local-llm-foundation` → `research/overnight-qlora-s030` | 147 | +16,826/−55 | true / **unstable** | **RESEARCH_ARCHIVE** | Title says 不合并 (do not merge); ancestor of #21/#22. |
| #21 | Phase 4 Innovation Signals Observatory | D | `integration/phase4-base` → `research/innovation-signals-observatory` | 96 | +64,441/−0 | true / clean | **NEEDS_REWORK** | Base branch has no PR; ancestry = product + S-028 + LLM lane; cannot be reviewed standalone. |
| #22 | S-031 hiring capability study (do-not-merge) | D | `main` → `research/s031-hiring-capability-study` | 600 | +303,926/−2 | true / clean | **RESEARCH_ARCHIVE** | 560/600 changed files are #21's; only 33 files/+4,032 genuine; title says do-not-merge. |
| #23 | PHOENIX-001 external methods audit | D | `main` → `research/phoenix-001-external-methods` | 40 | +6,075/−0 | true / clean | **SUPERSEDED** | Round 2 (#24) contains the same register/licence/reproduction docs; local branch diverged (33 ahead/16 behind, 7 unique commits). |
| #24 | PHOENIX-001 round 2 (frozen protocol) | D | `main` → `research/phoenix-001-round2` | 166 | +158,731/−0 | true / clean | **RESEARCH_ARCHIVE** | Pre-registered research bundle; title says do-not-merge. |
| #25 | PHOENIX-002 H8 re-validation (NO-GO) | D | `research/phoenix-001-round2` → `research/phoenix-002-h8-validation` | 59 | +58,438/−0 | true / clean | **RESEARCH_ARCHIVE** | NO-GO re-validation stacked on #24. |
| #26 | PHOENIX-003 early-evidence (NO-GO) | D | `main` → `research/phoenix-003-early-evidence` | 104 | +197,464/−0 | true / clean | **RESEARCH_ARCHIVE** | NO-GO study with compressed study datasets; research record only. |
| #27 | DATA-EXPANSION-001 global data sources | D | `main` → `research/data-expansion-001` | 916 | +260,389/−0 | true / clean | **BLOCKED_LEGAL** | Ships UN Comtrade preview payloads (3 JSON + portal HTML) whose own register says redistribution **PARTIAL**; UK-tender samples are OGL-permitted. |
| #28 | ATLAS-001 identity/evidence/graph foundation | D | `main` → `foundation/atlas-001` | 70 | +18,648/−0 | true / clean | **NEEDS_REWORK** | Clean foundation but ADR-001 canon decision is open (zero `main` consumers; E2 portability unproven). |
| #29 | HORIZON-001 global data frontier | D | `main` → `research/horizon-001` | 691 | +692,975/−0 | true / clean | **BLOCKED_LEGAL** | Bulk restricted UN Comtrade payload: 27 raw JSON + 3 JSONL + 3 UK raw award packages + 4 derived reports. |
| #30 | CONVERGENCE-001 ATLAS × HORIZON integration | D | `main` → `integration/convergence-001` | 815 | +690,079/−0 | true / clean | **NEEDS_REWORK** | Legally sanitised, but 721/813 added files duplicate #29/#28 (654 horizon copies + 67 atlas); 92 net-new. |
| #31 | REFOUNDATION-001 repository audit (sanitised) | D | `main` → `publish/refoundation-001` | 179 | +54,732/−0 | true / clean | **READY_TO_INTEGRATE** | Docs-only sanitised publication of the audit; no code, no risk-path hits. |
| #32 | Phase-0 governance MVP (state + 5 gates + CI) | D | `main` → `governance/refoundation-002` | 74 | +10,676/−17 | true / clean | **READY_TO_INTEGRATE** | Verified locally (240 state checks, 5 gates); defines the state-bump merge flow. |
| #33 | Phase-0 evidence-store comparison + 3 options | D | `main` → `research/evidence-architecture-002` | 4 | +12,049/−0 | true / clean | **READY_TO_INTEGRATE** | Decision document; adopts no canon, changes no code/data. |
| #34 | README truth revision | D | `main` → `docs/readme-truth-phase2` | 4 | +263/−22 | true / clean | **READY_TO_INTEGRATE** | Mission/main-vs-draft/event-time truth fixes; no redesign. |
| #35 | Evidence Core v1 (option C ledger) | D | `main` → `feature/evidence-core-v1` | 9 | +2,383/−49 | true / clean | **READY_TO_INTEGRATE** | Only code PR in the ready set; append-only ledger + migrations + 28 new tests, migration on a copy only. |
| #36 | E1b source recovery (PIT availability) | D | `main` → `research/e1b-source-recovery` | 8 | +1,543/−0 | true / clean | **READY_TO_INTEGRATE** | Small measured experiment; hashes only, no raw documents; independent. |
| #37 | Phase-2 acceptance package | D | `main` → `refoundation/phase2-acceptance` | 5 | +890/−0 | true / clean | **SUPERSEDED** | 4 of 5 files are byte-identical copies of #32/#34/#35/#36 reports; only `PHASE2_ACCEPTANCE.md` is unique. |

**FACT:** `#1` is the only non-draft and the only conflicted PR. Every #12–#37 PR is a draft and textually mergeable, so "mergeable" is not a useful discriminator here — status must come from ancestry, duplication and licence.

---

## 4. Topology and overlap

### 4.1 Verified ancestry chains

`git merge-base --is-ancestor`, all 27 open heads against each other (full matrix in `_evidence/pr_triage.json` → `ancestry`). Only non-empty relations are shown.

```
main b2a14c0
├── #12 ── #13 ── #14 ── #15 ── phase4-base(no PR) ── #21 ── #22
│                      └── #16                      ▲
├── #19 ── #20 ────────────────────────────────────┘        (LLM lane is an ancestor of #21/#22)
├── #24 ── #25
├── #28 ── #30
├── #17   #18   #23   #26   #27   #29   #31   #32   #33   #34   #35   #36   #37   (independent)
└── #1  (conflicted, superseded)
```

**FACT (measured pairs):** `#12→#13→#14`; `#14→#15`; `#14→#16`; `#15→#21`; `#12,#13,#14,#15,#19,#20 → #21`; `#21→#22`; `#19→#20`; `#24→#25`; `#28→#30`. **No relation:** `#29→#30` (the HORIZON tree is **copied**, not merged); `#15↔#16` (siblings); `#23→#24` (independent forks, superseded only in content).

[INFERENCE] The "product stack" is really a **5-deep chain** `#12→#13→#14→#15→phase4-base(no PR)`, and the two hiring PRs inherit product + S-028 + local-LLM. That is why #22's diff is 600 files even though its genuine work is 33 files.

### 4.2 Overlap matrix

| Pair | Kind | Evidence | Consequence |
|---|---|---|---|
| **#21 / #22** | ancestry + duplication | `#21` is an ancestor of `#22`; **560 of 600** changed files byte-identical; diff #22 vs #21 = **33 files / +4,032** | #22 cannot be reviewed or merged separately; salvage 33 files. |
| **#29 / #30** | **copy, not ancestry** | 654 of 813 added files byte-identical to #29; `#29` is **not** an ancestor of `#30`; #30 removes exactly the 37 restricted/derived files | Merging both duplicates 654 files; #30 is the sanitised copy. |
| **#28 / #30** | ancestry | `#28` **is** an ancestor of `#30`; 67 identical files are legitimate inheritance | #28 must land before #30 (or #30 carries it). |
| **#37 vs #32/#34/#35/#36** | byte-identical copies | 4 of 5 files are identical blobs (verified); only `PHASE2_ACCEPTANCE.md` is unique | Do not merge #37 as a duplicate bundle; fold the acceptance doc into the integration PR. |
| **#17 vs #34** | same files, stale | both modify `README.md`, `README.zh-CN.md`, `tests/test_release.py`; different README blobs (`a814a5a91b12` vs `5acc30bc83d2`) | #34 is the newer truth revision; #17 superseded. |
| **#27 vs #29/#30** | same restricted source family | UN Comtrade + UK Find a Tender; #27 carries *previews*, #29 *bulk raw*, #30 *sanitised* | Legal handling differs by payload size (§5). |
| **#15 / #16** | sibling studies | both branched from #14; neither contains the other | Independent research records. |
| **#31 / #37** | adjacent docs | #31 publishes RF001 audit docs; #37 copies Phase-2 workstream reports | Different content; #31 ready, #37 superseded. |

### 4.3 The four known stacks, judged

1. **S-028 stack.** `#15` (S-028) is not just a sibling study: its tip `4c6686f` is an ancestor of `integration/phase4-base` and therefore of `#21` and `#22`. Merging #21/#22 lands S-028 regardless. [FACT]
2. **#21/#22.** `#21` declares `integration/phase4-base` as base — a branch **with no PR of its own** — and its ancestry includes `#12–#14`, `#15`, `#19`, `#20`. `#22` declares `main` but contains `#21`. Both are structurally un-reviewable as written. [FACT]
3. **#29/#30 vs CONVERGENCE.** `#29` (HORIZON) is the source; `#30` (CONVERGENCE) **copies** the horizon tree (654 identical files) but strips the restricted payload. `#28` (ATLAS) is a true ancestor of `#30`. The correct consolidation is **#28 → #30 (dedupe), not #29 + #30**. [FACT + INFERENCE]
4. **Phase 0–2 program.** `#32`, `#33`, `#34`, `#35`, `#36` are independent `main`-based PRs; `#37` only re-packages their reports; the local `integration/ref003` branch (9 commits) already merges `#32` + `#35` and is the natural integration vehicle. [FACT: branch log/merge commits; RECOMMENDATION: use it]

---

## 5. BLOCKED_LEGAL — restricted-data detail

**Do not merge these two PRs as published.** Both are *data*, not code, problems.

### 5.1 #29 HORIZON-001 — bulk restricted payload [FACT]

The branch's own CONVERGENCE licence review (`docs/convergence/LICENCE_AND_SECURITY_REVIEW.md`) states UN Comtrade is redistribution-blocked and that the payload is reachable from `origin/research/horizon-001` (a **public** remote). Path-level confirmation in the PR diff:

| Group | Files | Examples |
|---|---:|---|
| UN Comtrade raw series | **27** | `research/horizon/DATASETS/industry/un_comtrade/raw/annual_2015–2024.json` (10), `monthly_202501–202512.json` (12), `summary.json`, `hs.json`, `reporters.json`, `api_root.html`, `comtradeplus_home.html` |
| UN Comtrade derived exports | **3** | `experiments/industry/evidence/un_comtrade.jsonl`, `exports/horizon-2026-11-10/un_comtrade.jsonl(.sha256)` |
| UK Find a Tender raw award packages | **3** | `research/horizon/DATASETS/industry/uk_find_a_tender/raw/award_packages_p1–p3.json` |
| Derived reports quoting Comtrade figures | **4** | `EXPERIMENT_RESULTS.md`, `experiments/industry/EXP_H4_INDUSTRY.json`, `reports/INDUSTRY_DATA_REPORT.md`, `reports/REGULATORY_FRONTIER_REPORT.md` |
| **Total implicated** | **37** | of 691 changed files |

**Severity:** the restricted bytes are **already on a public remote**; this is an owner/data-governance escalation regardless of what happens to the PR. [RECOMMENDATION] Do not merge #29; either strip these 37 files and rework, or close as superseded by #30's sanitised copy. A history rewrite (if desired) requires explicit owner authorisation and is outside this task.

### 5.2 #27 DATA-EXPANSION-001 — Comtrade preview payloads [FACT + judgement]

Its own source register `research/data_expansion/registry/sources/un_comtrade.json` says:
`"redistribution_allowed": "PARTIAL"` and `"licence": "... free for non-commercial use with attribution, bulk redistribution restricted"`.
The PR ships 4 implicated artefacts:

- `research/data_expansion/samples/un_comtrade/preview_9018.json`
- `research/data_expansion/samples/un_comtrade/preview_9022.json`
- `research/data_expansion/samples/un_comtrade/preview_9402.json`
- `research/data_expansion/samples/un_comtrade/developer_portal.html`

Its **UK Find a Tender** artefacts are **not** restricted (`"redistribution_allowed": "YES"`, Open Government Licence v3 with attribution), and its FDA/GUDID/openFDA samples are US public domain.

**Severity:** small payload (previews, ~278 records total), but from a PARTIAL-restricted source → flag rather than merge. [RECOMMENDATION] Strip the 4 Comtrade artefacts; the PR then moves to NEEDS_REWORK (code/evidence is otherwise mergeable in principle).

### 5.3 Not legally blocked, but flagged for rework

- **#30 CONVERGENCE** — path check shows only Comtrade **licence/terms HTML + provenance/registry** (no raw data); its own gate reports 0 of 30 quarantined paths. It is the sanitised copy. → NEEDS_REWORK (dedupe), not BLOCKED_LEGAL.
- **#16 S-029** — 130 raw ClinicalTrials.gov `.json.gz` files. CT.gov is a US public-domain source, so this is **not** a licence block, but bulk raw dumps should not land in `main`. → RESEARCH_ARCHIVE.
- **#26 PHOENIX-003** — compressed study datasets; research archive, not legal.
- **#24/#25/#32** sqlite/gz hits are **test fixtures** (e.g. `experiments/phoenix/rea/fixtures/sample.sqlite`, `tests/governance/fixtures/fake_*.gz`) — not risk.

---

## 6. Consolidated active queue

### 6.1 Keep open and mergeable (6) — `READY_TO_INTEGRATE`

| PR | Why it stays | Dependency/order |
|---|---|---|
| #32 | Governance state source + 5 gates; every later merge must bump its state | **First** |
| #33 | ADR-001 decision record (option C recommended); no code | before #35 |
| #35 | Implements option C; only code PR in the ready set | after #33 |
| #31 | Docs-only RF001 audit publication | independent |
| #34 | README truth revision | independent |
| #36 | E1b source-recovery evidence | independent |

### 6.2 Research archive (9) — keep branch, close/mark PR, never merge

`#15` S-028 (NO-GO) · `#16` S-029 (NO-GO) · `#18` AI evidence review (machine) · `#19` local-LLM Phase 2 · `#20` overnight QLoRA (do-not-merge) · `#22` S-031 (33 genuine files, do-not-merge) · `#24` PHOENIX round 2 · `#25` PHOENIX-002 (NO-GO) · `#26` PHOENIX-003 (NO-GO).

**Retention rule [RECOMMENDATION]:** keep the branches and their evidence; close the PRs with a link to this triage, or convert them to a `research-archive` label if the owner prefers to leave them open. **#22 salvage:** the 33 genuine files (`research/s031`, `medradar/recruitment`, `config/recruitment_function_classes.json`, `S031_DELIVERY_MANIFEST.json`, verifier v2) can become a small future PR *only if the hiring lane is funded*.

### 6.3 Supersede / close (4)

| PR | Superseded by | Pre-close action |
|---|---|---|
| #1 | Its own content already on `main` | Copy the 5 unique verifier artefacts to a preservation branch. |
| #17 | #31 (audit docs) + #32 (state source) + #34 (README truth) | Preserve `DATA_ASSET_REGISTER.md` if DATA_GOVERNANCE_AUDIT does not cover it. |
| #23 | #24 round 2 (same register/licence/reproduction docs) | **Rescue the 7 unique local PHOENIX commits** to a preservation branch/remote first. |
| #37 | #32/#34/#35/#36 + the integration vehicle | Fold `PHASE2_ACCEPTANCE.md` into the integration PR. |

### 6.4 Rework queue (6) — not merged in the next two cycles

`#12` → `#13` → `#14` product stack (only if the product line is funded); `#21` (base with no PR; split/retarget); `#28` (ADR-001 canon decision); `#30` (dedupe 721 duplicated files after #28). **#1/#17/#23/#37** are in §6.3, not here.

---

## 7. Recommended order for the next two cycles

### 7.1 Cycle 1 — merge the ready spine (one week)

| Step | PR | Action | Gate |
|---:|---|---|---|
| 1 | **#32** | Mark ready → merge | Governance CI draft green; state file records `main` head; 240 checks / 0 fail |
| 2 | **#33** | Merge | Decision doc only; must precede #35 |
| 3 | **#35** | Merge | Full suite green (baseline 1,074 collected; PR claims 1,099 passed); migration exercised on a copy |
| 4 | **#31** | Merge | Docs-only; owner read-through of the sanitised audit |
| 5 | **#34** | Merge | README truth; `tests/test_release.py` updated |
| 6 | **#36** | Merge | Research evidence only; no raw documents |

**[FACT]** After each merge, `PROJECT_STATE.yaml` head/tracked-file count must be bumped — that is #32's designed merge-gate flow (5th workflow). **[RECOMMENDATION]** Run the full offline suite after every merge; any regression blocks the next step.

**Why this order:** #32 first because it is the gate every later merge must satisfy; #33 before #35 because #35 implements the option #33 recommends; #35 merged while the governance state is fresh; #31/#34/#36 are independent and can be reordered if review capacity demands it. All six are `main`-based with no cross-ancestry, so the order is risk-based, not graph-forced.

### 7.2 Cycle 2 — consolidate and close (one week)

1. **Land the integration vehicle.** Refresh `integration/ref003` (already merges #32 + #35; 9 commits) into a single integration PR that absorbs #37's `PHASE2_ACCEPTANCE.md` and its four workstream reports, then **close #37 as superseded**.
2. **ADR-001 canon decision.** Run the E2 portability test on #28. If option **B** (ATLAS canon) is chosen: rework #28, then dedupe #30 (drop 654 horizon copies) in Cycle 3. If option **C** (the #33 recommendation) is confirmed: archive #28/#30 as research.
3. **Legal remediation.** Strip the payloads from #27 (4 artefacts) and #29 (37 files); reclassify only after licence sign-off. Escalate the #29 public exposure to the owner in parallel.
4. **Close the superseded set** (#1, #17, #23, #37) — #23 only after the 7-commit rescue.
5. **Archive the nine research PRs** (branches kept, PRs closed/labelled). No research merges this cycle.

**Deliberately *not* in the next two cycles:** the entire product stack (#12–#14), #21/#22, and any research PR. They are not blockers for the refoundation spine and would consume review capacity without advancing the evidence platform.

---

## 8. Top 5 recommended actions

1. **Merge Cycle 1 in order #32 → #33 → #35 → #31 → #34 → #36**, bumping the governance state and running the full suite after each. This is the only work that advances the evidence platform this cycle.
2. **Do not merge #29 or #27.** #29 carries the bulk restricted UN Comtrade payload (37 files); #27 carries Comtrade previews (4 files). Strip and reclassify; escalate #29's public exposure to the owner.
3. **Fold #37 into the integration PR and close it.** Four of its five files are byte-identical copies of #32/#34/#35/#36 reports; only `PHASE2_ACCEPTANCE.md` is unique.
4. **Rescue the 7 unique local PHOENIX commits, then close #23** (superseded by #24) **and #17** (superseded by #31/#32/#34). #1 closes without rescue beyond its 5 verifier artefacts.
5. **Mark the nine research PRs RESEARCH_ARCHIVE** (branches kept, PRs closed or labelled). No research PR is merged in the next two cycles; revisit only if a programme is explicitly funded.

---

## 9. Reproducible commands

All read-only. Run from `D:\DEPPSKK\worktrees\rf003-triage`.

```bash
# Re-collect PR metadata + local metrics + ancestry (writes _evidence/pr_triage.json)
python docs/refoundation/phase3/_evidence/collect_pr_triage.py

# Re-render the compact view and per-PR rows
python docs/refoundation/phase3/_evidence/show_pr_triage.py
python docs/refoundation/phase3/_evidence/dump_rows.py

# Rebuild statuses/topology/plan on top of the collected metadata
python docs/refoundation/phase3/_evidence/build_triage.py

# Overlap / legal boundary evidence
python docs/refoundation/phase3/_evidence/check_boundary.py   # #27/#29 restricted paths
python docs/refoundation/phase3/_evidence/check_dup.py        # #37 byte-identical copies
python docs/refoundation/phase3/_evidence/list_paths.py       # #17/#31/#33/#34/#35/#36/#37 paths

# Manual spot checks
git merge-base --is-ancestor origin/research/innovation-signals-observatory \
                           origin/research/s031-hiring-capability-study; echo $?   # 0 = #21 ancestor of #22
git merge-base --is-ancestor origin/research/horizon-001 \
                           origin/integration/convergence-001; echo $?            # 1 = copy, not ancestry
git merge-tree --write-tree origin/main origin/feat/frontier-device-radar | head  # conflicts for #1
git rev-parse origin/refoundation/phase2-acceptance:docs/refoundation/phase2/EVIDENCE_CORE_V1.md
git rev-parse origin/feature/evidence-core-v1:docs/refoundation/phase2/EVIDENCE_CORE_V1.md  # same blob
```

**Safety statement:** the collector performs HTTP GETs against the public GitHub API and local `git` reads only. It does not write to any PR, branch, or GitHub setting. The only writes are the evidence files under `docs/refoundation/phase3/`.

---

## 10. Open questions for the owner

1. **Product line (#12–#14):** is it funded? If not, should these be closed/archived rather than held in NEEDS_REWORK? They are the base of eight other open PRs, so closing them changes the ancestry story for #15/#16/#21/#22.
2. **ADR-001 canon:** confirm option C (#35) as the interim canon, and schedule the E2 portability test that decides whether #28 (ATLAS, option B) is ever merged. #33 recommends "C now → B only if E1+E2 pass".
3. **Legal remediation authority:** who authorises stripping #27/#29, and does the already-public Comtrade payload in `origin/research/horizon-001` require a history rewrite or a redaction commit? This is an owner/data-governance decision; this triage only flags it.
4. **PHOENIX rescue:** who pushes the 7 unique local commits from `research/phoenix-001-external-methods` to a preservation branch before #23 is closed?
5. **#37:** fold into `integration/ref003` and close, or keep it as the Phase-2 acceptance record? Evidence says the four reports are duplicates and only `PHASE2_ACCEPTANCE.md` is unique.
6. **#31 size:** the RF001 audit publication is 179 files / +54,732 (docs + evidence JSON). Is publishing the full evidence corpus acceptable, or should only the 15 documents ship?
7. **Research PR policy:** close the nine research PRs, or keep them open under an `research-archive` label? Closing is cleaner for the open-PR count; labelling preserves discoverability.
8. **Queue ownership:** who executes Cycle 1 (the task explicitly forbids this triage from merging)? The plan assumes the owner or a designated merger with write access.
