# BRANCH_PR_AUDIT — 30 PRs, 33 remote branches, 49 local branches

> **Audit:** REFOUNDATION-001 · **Owner:** `inventory-auditor` · **Date:** 2026-11-12 (Asia/Shanghai)
> **Worktree:** `<REDACTED_LOCAL_PATH> (`audit/refoundation-001` @ `b2a14c0`)
> **Companion:** [`REPOSITORY_INVENTORY.md`](REPOSITORY_INVENTORY.md) · **Ground truth:** [`_FACTS.md`](_FACTS.md), [`_evidence/repo_facts.json`](_evidence/repo_facts.json)
> **Machine-readable:** [`_evidence/inventory/inventory_facts.json`](_evidence/inventory/inventory_facts.json), [`ancestry_verify.json`](_evidence/inventory/ancestry_verify.json), [`pr_deltas.json`](_evidence/inventory/pr_deltas.json)
> **Nothing in this document was executed.** No branch was merged, closed, deleted, retargeted or pushed. Every "disposition" is a **[RECOMMENDATION]** for the repository owner.

---

## 0. Scope / Method / Evidence base / Limits

**Scope.** All **30 pull requests** (#1–#30), all **33 non-main remote branches**, and all **49 local branches** (including 5 branches carrying commits that exist on no remote). For each: state, declared base/head, true ancestry, divergence vs `main` and vs its declared base, draft status, reviewability, duplication, and a recommended disposition. Also: the stack graph, the required merge order, the four items the user brief omitted or under-specified, and the local-work preservation problem.

**Method.**

1. PR metadata (state, draft, base, head, +/- , dates) from `_evidence/repo_facts.json`, collected from the live API on 2026-11-12 — **not** re-queried.
2. **Divergence re-measured locally** with `git rev-list --left-right --count origin/main...origin/<branch>` (note: left-only = *behind*, right-only = *ahead*; an early probe of mine had this inverted and was corrected — see §9).
3. **True ancestry** with `git merge-base --is-ancestor`, never inferred from a declared base. A PR's `baseRefName` is a *display choice*, not a fact about the graph.
4. **Merge feasibility** with `git merge-tree --write-tree <base> <head>` — read-only, index untouched. `exit 0` = textually clean; it does **not** mean safe (see §4.4).
5. **Duplication** by comparing blob SHAs of files added vs `main` against every other open-PR head (§7.5), and "true delta" by diffing a stacked PR against its declared base rather than `main`.
6. **Reviewability** is my own rubric: `draft?` + `commits` + `files in the diff a reviewer must read` + `hidden imports` + `duplication`. It is [INFERENCE], stated so the owner can disagree.

**Evidence base.**

| Evidence | Proves |
|---|---|
| `repo_facts.json` (`pull_requests`, `remote_branches`, `local_branches`, `worktrees`) | PR state/draft/base/head; 33 non-main remote refs; 49 local heads; 40 worktree entries |
| `git rev-list --left-right --count` | ahead/behind for every branch |
| `git merge-base --is-ancestor` | hidden stack membership (#§3, §7.2) |
| `git merge-tree --write-tree` | only #1 conflicts; all other open PRs merge textually clean into `main` |
| `git diff --numstat A...B` | delta vs declared base vs `main` (`pr_deltas.json`) |
| blob-SHA comparison (`verify_ancestry.py`, `convergence_dup.py`) | #30 = 654 horizon + 67 atlas + **92 net-new**; #22 = 560 #21 + **33 net-new** |
| `ancestry_extra.py`, `horizon_vs_convergence.py` | horizon is **not** an ancestor of convergence; the 37 differing files are the restricted Comtrade/UK-tender payload |
| `python -m pytest` on `b2a14c0` | 1,074 tests, exit 0 — the baseline any merge must preserve |

**Limits.**

1. **No network.** `mergeStateStatus`, review approvals, CI status and labels are **not** re-verified. `CONFLICTING` for #1 is reported from `_FACTS.md:113` **and** independently proven locally (11 conflicted paths, §7.1).
2. **Branch code was not executed.** A "clean merge" or "tests exist" claim does not mean branch tests pass. Every branch-quality statement beyond file existence is [INFERENCE] or [UNVERIFIED].
3. **Commit counts vs declared base** for stacked PRs are derived as `ahead(main)−ahead(base)` and cross-checked with `git rev-list --count base..head`; where they disagree I use the direct count.
4. **Reviewability is judgement**, not measurement. I show the inputs so it can be challenged.
5. **No disposition was applied.** GitHub state could have changed after 2026-11-12T02:37+08:00; re-collect before acting.

**Baseline for every merge recommendation [FACT, measured].** `main` @ `b2a14c0`: `python -B -m pytest -p no:cacheprovider -q` → **exit 0**, **1,074 collected**. Any merge that breaks this is a regression, regardless of how many lines it adds.

---

## 1. Executive summary

| Question | Answer | Label |
|---|---|---|
| Merged PRs | **10** (#2–#11), all on 2026-11-02 | FACT `repo_facts.json` |
| Open PRs | **20** (#1, #12–#30), of which **19 drafts** | FACT |
| Closed-unmerged | **0** | FACT |
| Added lines still unmerged | **2,824,212** vs 541,569 merged | FACT `_FACTS.md:68-73` |
| Non-main remote branches | **33** (34 non-HEAD refs incl. `main`) | FACT |
| Remote branches with **no PR** | **4**: `integration/phase4-base`, `research/early-signal-ai-review`, `research/full-history-v1`, `research/cycle2-coverage-power` (merged content) | FACT §6 |
| Local heads | **49**, of which **5 carry commits on no remote (13 unique commits total)** | FACT §5 |
| PRs that conflict with `main` | **exactly one: #1** (11 conflicted paths) | FACT §7.1 |
| PRs whose declared base hides ancestry | **7** (#13,#14,#15,#16,#20,#21,#25) + **2** that hide it despite declaring `main` (#22 via #21/phase4; #30 via #28) | FACT §3 |
| Largest genuine PR, by net-new files | **#24 PHOENIX round-2**: 166 files / +158,731, no duplication found | FACT §3 |
| Most deceptive diff | **#22**: 600 files/+303,926 shown, **33 files/+4,032 genuine** (94.6 % is #21) | FACT §7.6 |
| Highest severity side-finding | **#29 (HORIZON) publicly contains the UN Comtrade restricted payload**; #30 is its sanitised copy | FACT §7.8 |
| Recommended dispositions | **merge 10 · merge-after-split 4 · park 4 · hold/supersede 2 · no-action (merged) 10** = 30 PRs; plus 1 unreviewed remote branch to raise as a PR | RECOMMENDATION §8 |

**One-paragraph verdict.** The repository is not "20 PRs behind `main`". It is **three independent programme lineages (PHOENIX, HORIZON/ATLAS/CONVERGENCE, data-expansion) plus one product stack (#12→#14) onto which almost everything else was accidentally piled**. The 2.8 M added-line figure is dominated by re-counted duplicates (654 files copied between #29/#30; 560 between #21/#22; 133–134 product files in each study). Only #1 has a genuine conflict, and #1's content is already on `main`. The real work is merge **ordering, splitting** and one **data-licence decision**, not conflict resolution.

---

## 2. Full PR ledger (30 rows)

Columns: `Δbase` = files/+/- vs **declared base** (what the GitHub PR page shows); `Δmain` = files/+/- vs `origin/main` (what a merge actually imports); `commits` = commits ahead of `main`; `probe` = local `merge-tree` result into `main`.

### 2.1 Merged PRs (#2–#11) — historical, no action

| PR | Title (truncated) | Head branch | Merged | Files | +/− | Note |
|---:|---|---|---|---:|---:|---|
| #2 | bitemporal knowledge store + immutable forecast registry | `research/research-foundation-integration` | 2026-11-02 | 28 | +6,014/−3 | foundation; branch now 140 behind |
| #3 | Market-to-R&D intelligence and horizon forecasting | `feature/market-to-rd` | 2026-11-02 | 60 | +2,453/−25 | branch now 120 behind |
| #4 | v0.3.0 integrate research foundation + Market-to-R&D | `integration/market-to-rd-v2` | 2026-11-02 | 173 | +59,831/−543 | branch now 71 behind |
| #5 | change detection, company profiles, frozen forecasts | `research/change-detection-v1` | 2026-11-02 | 901 | +444,600/−543 | **largest merge**; branch 26 behind |
| #6 | early-signal five-firm cross-source audit | `research/early-signal-5firms` | 2026-11-02 | 97 | +24,205/−39 | S-026 |
| #7 | publication record for #6 | `research/early-signal-postmerge` | 2026-11-02 | 1 | +28/−0 | docs only |
| #8 | Europe PMC third-source cross-check | `research/early-signal-third-source` | 2026-11-02 | 9 | +1,375/−0 | S-026 |
| #9 | agent pre-adjudication of 69 packets | `research/early-signal-adjudication` | 2026-11-02 | 7 | +2,012/−0 | non-human tier |
| #10 | human review workbench | `research/early-signal-review-workbench` | 2026-11-02 | 8 | +742/−0 | S-026 |
| #11 | drop-down-validated Excel workbook | `research/early-signal-review-workbench` | 2026-11-02 | 5 | +309/−2 | same head as #10 — **is `main` HEAD** |

[FACT] #10 and #11 share head `research/early-signal-review-workbench`; #11 is `main`'s HEAD commit (`b2a14c0`). [RECOMMENDATION] after refoundation, delete the **9 distinct** merged head branches (they are 2–140 commits behind and their content is in `main`); no history is lost.

### 2.2 Open PRs (#1, #12–#30) — fact table

| PR | Draft | Declared base | Head | commits vs main | Δbase (files/+/−) | Δmain (files/+/−) | Probe into main | Reviewability (my rubric) |
|---:|:--:|---|---|---:|---|---|---|---|
| #1 | no | `main` | `feat/frontier-device-radar` | 13 | 44 / +2,709/−234 | 44 / +2,709/−234 | **CONFLICT (11)** | **Low** — 154 behind, stale fork, net-new = 5 verifier artefacts (§7.1) |
| #12 | yes | `main` | `feat/medradar-2.0-mvp` | 8 | 57 / +17,646/−1 | 57 / +17,646/−1 | clean | **High** — 57 files, self-contained product MVP |
| #13 | yes | `feat/medradar-2.0-mvp` | `feat/live-observatory-v1` | 16 | 57 / +31,301/−7 | 101 / +48,941/−2 | clean | **High vs base** / low vs main |
| #14 | yes | `feat/live-observatory-v1` | `feat/observatory-reliability-v1` | 22 | 54 / +22,899/−71 | 139 / +71,769/−2 | clean | **High vs base** / low vs main |
| #15 | yes | `feat/observatory-reliability-v1` | `research/s028-temporal-graph-early-signal` | 26 | 86 / +114,442/−0 | 225 / +186,211/−2 | clean | **Medium** — 4 true commits, 86 files |
| #16 | yes | `feat/observatory-reliability-v1` | `research/s029-evidence-based-relations` | 34 | 205 / +133,237/−0 | 344 / +205,006/−2 | clean | **Medium** — 12 true commits, 205 files |
| #17 | yes | `main` | `maintenance/repository-consolidation` | 2 | 6 / +947/−805 | 6 / +947/−805 | clean | **High** — docs only |
| #18 | yes | `main` | `research/ai-evidence-review` | 1 | 4 / +575/−0 | 4 / +575/−0 | clean | **High** — 1 commit |
| #19 | yes | `main` | `research/local-llm-foundation` | 9 | 110 / +32,464/−0 | 110 / +32,464/−0 | clean | **Medium** — GPU/LLM claims need re-run |
| #20 | yes | `research/local-llm-foundation` | `research/overnight-qlora-s030` | 11 | 147 / +16,826/−55 | 248 / +49,235/−0 | clean | **Low** — PR body says 不合并 (do not merge) |
| #21 | yes | `integration/phase4-base` | `research/innovation-signals-observatory` | 46 | 96 / +64,441/−0 | 567 / +299,894/−2 | clean | **Low** — base has no PR; 7 true commits |
| #22 | yes | `main` | `research/s031-hiring-capability-study` | 83 | 600 / +303,926/−2 | 600 / +303,926/−2 | clean | **Very low** — **33 genuine files**; contains phase4-base + #21 |
| #23 | yes | `main` | `research/phoenix-001-external-methods` | 16 | 40 / +6,075/−0 | 40 / +6,075/−0 | clean | **Low** — remote content stale vs local (33/16 divergence, §7.4) |
| #24 | yes | `main` | `research/phoenix-001-round2` | 7 | 166 / +158,731/−0 | 166 / +158,731/−0 | clean | **Medium-high** — 7 commits, no duplication found |
| #25 | yes | `research/phoenix-001-round2` | `research/phoenix-002-h8-validation` | 10 | 59 / +58,438/−0 | 225 / +217,169/−0 | clean | **High vs base** — 3 true commits |
| #26 | yes | `main` | `research/phoenix-003-early-evidence` | 4 | 104 / +197,464/−0 | 104 / +197,464/−0 | clean | **Medium** — 4 commits, 104 files |
| #27 | yes | `main` | `research/data-expansion-001` | 7 | 916 / +260,389/−0 | 916 / +260,389/−0 | clean | **Low** — 863 evidence files dominate |
| #28 | yes | `main` | `foundation/atlas-001` | 4 | 70 / +18,648/−0 | 70 / +18,648/−0 | clean | **High** — foundation, 4 commits |
| #29 | yes | `main` | `research/horizon-001` | 4 | 691 / +692,975/−0 | 691 / +692,975/−0 | clean | **Medium** — 4 commits, but **restricted payload present** (§7.8) |
| #30 | yes | `main` | `integration/convergence-001` | 9 | 815 / +690,079/−0 | 815 / +690,079/−0 | clean | **Low** — 721 of 813 added files are duplicates; **92 net-new** |

**FACT:** only PR #1 fails `merge-tree`; every other open PR is textually mergeable into `main` *today*. [INFERENCE] this is why the stack feels "blocked": the obstacle is policy, ordering and duplication, not conflicts.

---

## 3. Per-PR disposition — with base-vs-ancestry mismatch and "what a merge silently imports"

**How to read.** *True ancestry* is the list of unmerged branches that are ancestors of the head (verified with `merge-base --is-ancestor`), regardless of the declared base. *Silent import* = the unmerged code a merge would bring into `main` **in addition to** the head's own new files. Disposition is a **[RECOMMENDATION] only**.

| PR | Draft | Declared base | True ancestry (verified) | Base vs ancestry | Silent import if merged as-is | Δ genuine (net-new) | Recommended disposition |
|---:|:--:|---|---|---|---|---|---|
| #1 | no | `main` | — | consistent | none (content already on `main`) | 5 verifier artefacts | **SUPERSEDE / close** — preserve 5 files (§7.1) |
| #12 | yes | `main` | — | consistent | none | 57 files / +17,646 | **MERGE** (Stage B1) after marking ready |
| #13 | yes | #12 | #12 | consistent (stacked) | 8 commits of #12 (+17,646) | 57 files / +31,301 | **MERGE** (B2) after #12 |
| #14 | yes | #13 | #12, #13 | consistent (stacked) | 16 commits of #12–#13 | 54 files / +22,899 | **MERGE** (B3) after #13 |
| #15 | yes | #14 | #12, #13, #14 | consistent (stacked) | 22 commits of #12–#14 (133 product files) | 86 files / +114,442 | **PARK until #14**, then MERGE (D1) |
| #16 | yes | #14 | #12, #13, #14 | consistent (stacked) | 22 commits of #12–#14 (134 files) | 205 files / +133,237 | **PARK until #14**, then MERGE (D2) |
| #17 | yes | `main` | — | consistent | none | 6 files / +947/−805 | **MERGE early** (A1) |
| #18 | yes | `main` | — | consistent | none | 4 files / +575 | **MERGE early** (A2) |
| #19 | yes | `main` | — | consistent | none | 110 files / +32,464 | **MERGE** (E1) if LLM lane in scope |
| #20 | yes | #19 | #19 | consistent (stacked) | 9 commits of #19 | 147 files / +16,826 | **PARK / archive** — PR body: "do not merge" |
| #21 | yes | `integration/phase4-base` | #12, #13, #14, **#15**, **phase4-base** | **MISMATCH — base has no PR** | 39 commits of phase4-base (incl. #12–#15 + phase-4 groundwork) | 96 files / +64,441 (+7 commits) | **SPLIT**: open a phase4-base PR or retarget #21 to #14; then MERGE (D3) |
| #22 | yes | `main` | #12, #13, #14, **#15**, **phase4-base**, **#21** | **MISMATCH — declared `main` hides the whole stack** | 39 phase4-base + 46 #21 commits; **560 of 600 files are #21's** | **33 files / +4,032** | **SPLIT**: rebase onto #21, keep 33 files; never merge as one PR |
| #23 | yes | `main` | — | consistent | none | 40 files / +6,075 | **PARK** pending local/remote reconciliation (§7.4), then re-review |
| #24 | yes | `main` | — | consistent | none | 166 files / +158,731 | **MERGE** (F1) after PHOENIX scope decision |
| #25 | yes | #24 | #24 | consistent (stacked) | 7 commits of #24 | 59 files / +58,438 | **MERGE** (F2) after #24 |
| #26 | yes | `main` | — | consistent | none | 104 files / +197,464 | **MERGE or PARK** (F3) — independent NO-GO study |
| #27 | yes | `main` | — | consistent | none | 916 files / +260,389 (863 evidence) | **SPLIT** code (`medradar/external_sources`, 46) vs evidence (863); merge code |
| #28 | yes | `main` | — | consistent | none | 70 files / +18,648 | **MERGE** (C1) |
| #29 | yes | `main` | — | consistent | none, **but 33 restricted raw files** | 691 files / +692,975 | **HOLD/SUPERSEDE** — do not merge until restricted payload removed; use #30 as sanitised copy (§7.8) |
| #30 | yes | `main` | **#28** (atlas ancestry) | consistent base, **inherits atlas** | 4 commits of #28 (67 files); horizon content is **copied, not ancestor** | **92 files** net-new (721 duplicated) | **SPLIT**: rebase onto #28, drop 654 horizon duplicates, merge 92-file delta (C2) |

**Merge-probe caveat [FACT]:** all rows except #1 are `CLEAN` under `git merge-tree`. [INFERENCE] "clean" is exactly why the mismatch matters — a clean merge of #22 silently fast-forwards 39+46 foreign commits into `main` with no conflict to force a reviewer's attention.

### 2.3 PR title (intent) vs measured content (reality)

PR titles are **[FACT]** (API records). "Reality" is my measurement. No title was trusted as a description of the diff.

| PR | Stated intent (title, abbreviated) | Measured reality | Gap |
|---:|---|---|---|
| #1 | "Add frontier device intelligence and research safeguards" | feature already on `main`; net-new = 5 verifier artefacts | **Fully superseded** |
| #12 | "MedRadar 2.0 MVP: company, radar, analyst and evidence product" | 57 files; self-contained on `main` base | consistent |
| #13 | "Live Observatory v1: append-only observation ledger, official-source adapters" | 57 files / 8 commits over #12 | consistent |
| #14 | "Observatory Reliability: durable persistence, verified backups, seven-day continuous validation" | 54 files / 6 commits; `deploy/systemd`, `deploy/windows` | consistent |
| #15 | "S-028 … (DRAFT, negative result, **do not merge**)" | 86 files; **is ancestor of phase4-base/#21/#22** | title says do-not-merge; branch is a base of two other PRs |
| #16 | "S-029 … NO-GO verdict (research, draft)" | 205 files vs base; sibling of #15 | consistent |
| #17 | "Repository consolidation: documentation, research index, data asset governance" | 6 files, +947/−805 | consistent |
| #18 | "AI evidence review of the 69 packets (machine review, not human truth)" | 4 files, 1 commit | consistent |
| #19 | "Phase 2 — first real local GPU run (Qwen3-4B vs rules on 19 documents)" | 110 files; **no weights/results verifiable offline** | partially [UNVERIFIED] |
| #20 | "隔夜探索性 QLoRA …（Draft，**不合并**）" | 147 files vs #19 | **title forbids merge** |
| #21 | "Phase 4: Innovation Signals Observatory — recruitment lane" | 96 files vs a **base with no PR**; inherits product + S-028 | base hidden |
| #22 | "S-031 … 100 AI labels, 8 deliverables (**do not merge**)" | **33 genuine files**; inherits #15+phase4+#21 | **94.6 % not its own work** |
| #23 | "PHOENIX-001: External methods audit and reproducible experiments" | remote 40 files / main-based; **local is 33-ahead/16-behind on an S-028 base** | content mismatch |
| #24 | "PHOENIX-001 round 2: frozen protocol, ten pre-registered experiments" | 166 files, 7 commits, no duplication detected | consistent |
| #25 | "PHOENIX-002: independent H8 re-validation — NO-GO" | 59 files via declared base; 3 commits | consistent |
| #26 | "PHOENIX-003: regulatory-anchored early-evidence discovery — NO-GO" | 104 files, 4 commits | consistent |
| #27 | "DATA-EXPANSION-001: global data-source discovery, live access verification" | 916 files, **863 of them evidence** | code/evidence mixed |
| #28 | "ATLAS-001: identity, evidence and graph foundation" | 70 files, 4 commits | consistent |
| #29 | "HORIZON-001: 全球数据前沿 — two keyless patent channels, real evidence export" | 691 files; **30 restricted Comtrade + 3 UK-tender raw files present** | **licence problem** |
| #30 | "CONVERGENCE-001: ATLAS × HORIZON end-to-end integration" | 813 added, **721 duplicated**, 92 net-new | **integration is mostly a copy** |

---

## 4. Stack graph and required merge order

### 4.1 Graph (verified ancestry; `←` = "contains as ancestor")

```
main b2a14c0 (PR #11)
├── #1  feat/frontier-device-radar           13 ahead, 154 behind, CONFLICTING  [superseded]
├── #12 feat/medradar-2.0-mvp                 8 commits / +17,646
│   └── #13 feat/live-observatory-v1         16 / +31,301
│       └── #14 feat/observatory-reliability-v1  22 / +22,899
│           ├── #15 S-028                    26 / +114,442
│           │   └── integration/phase4-base  39 / +235,453   ← NO PR; built ON #15, +13 commits
│           │       └── #21 innovation-signals-observatory  46 / +64,441
│           │           └── #22 s031-hiring-capability 83 / +303,926  ← declared base = main (!)
│           └── #16 S-029                    34 / +133,237   (sibling of #15, NOT in phase4-base)
├── #17 maintenance/repository-consolidation   2 / +947/−805
├── #18 research/ai-evidence-review            1 / +575
├── #19 research/local-llm-foundation          9 / +32,464
│   └── #20 overnight-qlora-s030              11 / +16,826   [PR says do-not-merge]
├── #23 phoenix-001-external-methods          16 / +6,075    ← local diverged 33 ahead/16 behind
├── #24 phoenix-001-round2                     7 / +158,731
│   └── #25 phoenix-002-h8-validation         10 / +58,438
├── #26 phoenix-003-early-evidence             4 / +197,464
├── #27 data-expansion-001                     7 / +260,389
├── #28 foundation/atlas-001                   4 / +18,648
│   └── (inherited by #30)
├── #29 research/horizon-001                   4 / +692,975  ← restricted payload
└── #30 integration/convergence-001            9 / +690,079  ← 654 files COPIED from #29
```

**FACT (verified edges, not inferred):** #12→#13→#14; #14→#15; #14→#16; **#15→`phase4-base`**; `phase4-base`→#21; #21→#22; #19→#20; #24→#25; #28→#30. The `#15→phase4-base` edge is the one `_FACTS.md` §4 does not show: `git rev-list --count origin/research/s028… ^origin/integration/phase4-base` = **0**, and `research/studies/graph_early_signal_s028/` is in the phase4-base tree. **Not** ancestor edges (despite appearances): #29→#30 (copy, not ancestry), #23→#24 (independent forks of `main`), #15↔#16 (siblings), #16↛phase4-base.

[INFERENCE] consequence: the "product stack" is actually a **5-deep chain** `#12→#13→#14→#15→phase4-base`, and the two hiring PRs (#21/#22) inherit **two** research studies' worth of code plus the product. This is why their diffs are enormous and their reviewability is near zero — not because the authors wrote 300 k lines.

### 4.2 Required merge order (one defensible plan)

| Stage | PRs | Why this order |
|---|---|---|
| **A — hygiene, independent** | #17, #18 | 2 and 1 commits, docs/review only; no ancestry; cheapest wins; merge before research branches so the docs they touch are settled |
| **B — product foundation** | #12 → #13 → #14 | strict stack; each is only 6–8 commits over its base; unblocks C/D |
| **C — foundations & convergence** | #28 → (#30 split) | #28 is a verified ancestor of #30; merge #28 first, then merge #30's 92-file delta; **do not merge #29 as-is** (§7.8) |
| **D — studies on product** | #15, #16 (after B); phase4-base decision; #21 after that; #22 after #21 | all physically require #14; #15 is also an ancestor of phase4-base; #22 must be split to its 33 genuine files |
| **E — local-LLM lane** | #19 → (decide #20) | #20 is explicitly exploratory and stacked on #19; archive unless the owner funds it |
| **F — PHOENIX** | #24 → #25; #26 independent | #23 must be reconciled first; #24/#25 are a verified stack; #26 is independent |
| **G — data expansion** | #27 (split: code vs evidence) | 863 of 916 files are evidence, not code; merging code unlocks the lane without a 260 k-line dump |
| **H — supersede/close** | #1, and after merging: #29 (superseded by sanitised #30 content) | #1's content is on `main`; #29 is unsafe as published |

### 4.3 Rationale and alternatives

**[INFERENCE]** The order above minimises rework because the only true stacks are the product (#12–#14), the phase-4 extension (`phase4-base`→#21→#22), PHOENIX 24→25, and LLM 19→20. Everything else rebases onto `main` independently. **Alternative A (product-last):** merge all independent research first, product later — rejected because #15/#16/#21/#22 then have to be rebased twice and their CI cannot be trusted without the product code they import. **Alternative B (single mega-merge of #12–#14):** rejected; each PR has its own acceptance docs and the stack is already clean, so three small merges are cheaper to review than one 100-file merge.

**[RECOMMENDATION]** Before Stage B, open a **phase4-base PR** (or retarget #21 to `feat/observatory-reliability-v1`). `integration/phase4-base` is a real 39-commit branch with no review surface (§7.3); merging it via #21 or #22 is the single largest hidden-import risk in the repository.

### 4.4 Why "clean merge" is not a green light

[FACT] `git merge-tree` only detects textual conflicts. The three real hazards here are invisible to it:

1. **Ancestry import** — #22's merge tree is clean, yet it fast-forwards `phase4-base` + #21 into `main` (§3).
2. **Semantic duplication** — #30's merge tree is clean, yet it re-adds 654 horizon files, so the same code can drift in two copies (§7.5).
3. **Licence contamination** — #29's merge tree is clean, yet 33 raw restricted files ride along (§7.8).

[RECOMMENDATION] adopt a merge gate that fails on: ancestry containing a branch with no PR; >50 % blob-identity with another open-PR head; and any path matching the quarantined-dataset list.

---

## 5. Remote branches (33 non-main) — full ledger

`ahead`/`behind` are vs `origin/main`; recomputed 2026-11-12.

| Branch | Ahead | Behind | PR | Draft | Disposition (recommendation) |
|---|---:|---:|---:|:--:|---|
| `feat/frontier-device-radar` | 13 | **154** | #1 | no | **SUPERSEDE** — content on main; 5 verifier artefacts to preserve |
| `feat/medradar-2.0-mvp` | 8 | 0 | #12 | yes | MERGE (B1) |
| `feat/live-observatory-v1` | 16 | 0 | #13 | yes | MERGE (B2) |
| `feat/observatory-reliability-v1` | 22 | 0 | #14 | yes | MERGE (B3) |
| `feature/market-to-rd` | 0 | **120** | #3 | no | merged; delete branch later |
| `foundation/atlas-001` | 4 | 0 | #28 | yes | MERGE (C1) |
| `integration/convergence-001` | 9 | 0 | #30 | yes | SPLIT → merge 92-file delta (C2) |
| `integration/market-to-rd-v2` | 0 | **71** | #4 | no | merged; delete later |
| `integration/phase4-base` | **39** | 0 | **none** | — | **OPEN A PR or RETARGET #21** (§7.3); do not merge via another PR |
| `maintenance/repository-consolidation` | 2 | 0 | #17 | yes | MERGE (A1) |
| `research/ai-evidence-review` | 1 | 0 | #18 | yes | MERGE (A2) |
| `research/change-detection-v1` | 0 | **26** | #5 | no | merged; delete later |
| `research/cycle2-coverage-power` | 0 | **70** | **none** | — | content is in main; archive branch (§6) |
| `research/data-expansion-001` | 7 | 0 | #27 | yes | SPLIT (G) |
| `research/early-signal-5firms` | 0 | 11 | #6 | no | merged; delete later |
| `research/early-signal-adjudication` | 0 | 5 | #9 | no | merged; delete later |
| `research/early-signal-ai-review` | **11** | 0 | **none** | — | **REVIEW → open PR or archive** (§6) |
| `research/early-signal-postmerge` | 0 | 9 | #7 | no | merged; delete later |
| `research/early-signal-review-workbench` | 0 | 2 | #10/#11 | no | merged; delete later |
| `research/early-signal-third-source` | 0 | 7 | #8 | no | merged; delete later |
| `research/full-history-v1` | 1 | 0 | **none** | — | **CONTAINED in `early-signal-ai-review`** (verified ancestor); archive |
| `research/horizon-001` | 4 | 0 | #29 | yes | **HOLD** — restricted payload; supersede with sanitised content |
| `research/innovation-signals-observatory` | **46** | 0 | #21 | yes | retarget/split, then MERGE (D3) |
| `research/local-llm-foundation` | 9 | 0 | #19 | yes | MERGE (E1) |
| `research/overnight-qlora-s030` | 11 | 0 | #20 | yes | PARK/archive (do-not-merge) |
| `research/phoenix-001-external-methods` | 16 | 0 | #23 | yes | **PARK** — reconcile with local 33/16 divergence (§7.4) |
| `research/phoenix-001-round2` | 7 | 0 | #24 | yes | MERGE (F1) |
| `research/phoenix-002-h8-validation` | 10 | 0 | #25 | yes | MERGE (F2) after #24 |
| `research/phoenix-003-early-evidence` | 4 | 0 | #26 | yes | MERGE or PARK (F3) |
| `research/research-foundation-integration` | 0 | **140** | #2 | no | merged; delete later |
| `research/s028-temporal-graph-early-signal` | 26 | 0 | #15 | yes | PARK → MERGE (D1) |
| `research/s029-evidence-based-relations` | 34 | 0 | #16 | yes | PARK → MERGE (D2) |
| `research/s031-hiring-capability-study` | **83** | 0 | #22 | yes | **SPLIT** (33 genuine files) |

**Counts [FACT]:** 33 non-main remote branches = **23 unmerged** + **10 merged** (0 ahead). Of the 23 unmerged, **20 are PR heads**, **3 have no PR** (`phase4-base`, `early-signal-ai-review`, `full-history-v1`), and one merged-content branch (`cycle2-coverage-power`) has no PR record.

### 5.1 Merged branches — retire candidates

[FACT] `feature/market-to-rd` (120 behind), `integration/market-to-rd-v2` (71), `research/change-detection-v1` (26), `research/early-signal-5firms` (11), `research/early-signal-postmerge` (9), `research/early-signal-review-workbench` (2), `research/early-signal-third-source` (7), `research/early-signal-adjudication` (5), `research/research-foundation-integration` (140) are all **0 ahead** of `main`; their content is fully merged. [RECOMMENDATION] archive or delete after refoundation; nothing unique is lost. **Exception:** keep `research/early-signal-review-workbench` until #11's workbook is verified present in `main` (it is `main`'s HEAD, so it is).

### 5.2 Branch timeline (tip commit dates, Asia/Shanghai unless marked `Z`)

[FACT] Read from `git log -1 --format=%cI`. Divergence is cumulative — a branch's date is its last commit, not its activity period.

| Branch | Tip date | Tip sha | Ahead/behind | Signal |
|---|---|---:|---|---|
| `main` | 2026-11-03 04:26 | `b2a14c0a92` | 0/0 | PR #11 merge |
| `feat/frontier-device-radar` | 2026-11-01 09:41 | `94c6a10004` | 13/**154** | 2 days stale |
| `feature/market-to-rd` | 2026-11-01 17:48 | `ad38d27033` | 0/120 | merged |
| `research/research-foundation-integration` | 2026-11-01 11:05 | `dedfd68d7b` | 0/140 | merged |
| `research/change-detection-v1` | 2026-11-02 13:51 | `5bb6545f6c` | 0/26 | merged |
| `research/cycle2-coverage-power` | 2026-11-02 10:25 | `ce99ea12f6` | 0/70 | merged content, no PR |
| `integration/market-to-rd-v2` | 2026-11-02 09:29 | `1749bd5f3a` | 0/71 | merged |
| `research/early-signal-5firms` | 2026-11-03 03:49 | `bb8f9f84ca` | 0/11 | merged |
| `research/early-signal-postmerge` | 2026-11-03 03:53 | `a23ee604cb` | 0/9 | merged |
| `research/early-signal-third-source` | 2026-11-03 04:00 | `1e3864b188` | 0/7 | merged |
| `research/early-signal-adjudication` | 2026-11-03 04:09 | `d530abfa87` | 0/5 | merged |
| `research/early-signal-review-workbench` | 2026-11-03 04:23 | `fa1d57b874` | 0/2 | merged (`main` HEAD) |
| `research/full-history-v1` | 2026-11-03 07:20 | `969fd0cc4f` | 1/0 | **no PR** |
| `research/early-signal-ai-review` | 2026-11-03 10:49 | `38565cbcf4` | 11/0 | **no PR** |
| `feat/medradar-2.0-mvp` | 2026-11-03 22:00 | `ee7d011846` | 8/0 | product B1 |
| `feat/live-observatory-v1` | 2026-11-03 23:09 | `5335dfde39` | 16/0 | product B2 |
| `feat/observatory-reliability-v1` | 2026-11-04 00:05 | `d05fc81ff7` | 22/0 | product B3 |
| `research/s028-temporal-graph-early-signal` | 2026-11-04 03:05 | `4c6686f45f` | 26/0 | **becomes phase4 base** |
| `research/s029-evidence-based-relations` | 2026-11-04 05:09 | `10f25d190a` | 34/0 | sibling |
| `maintenance/repository-consolidation` | 2026-11-04 06:19 | `b4a6af3fc6` | 2/0 | docs |
| `research/ai-evidence-review` | 2026-11-04 07:20 | `b68af122a7` | 1/0 | tiny |
| `research/local-llm-foundation` | 2026-11-04 09:25 | `d4c4e43c9a` | 9/0 | LLM E1 |
| `research/overnight-qlora-s030` | 2026-11-04 11:33 | `5954d7d81b` | 11/0 | do-not-merge |
| `integration/phase4-base` | 2026-11-04 20:48 | `aa0f6fca85` | **39/0** | **no PR** |
| `research/innovation-signals-observatory` | 2026-11-04 22:37 | `c4327ce44c` | 46/0 | #21 |
| `research/s031-hiring-capability-study` | 2026-11-06 04:57 | `e3e39d59e8` | **83/0** | #22 |
| `research/phoenix-001-external-methods` | **2026-11-06 01:15Z** | `bd2f839033` | 16/0 | #23 remote |
| `research/phoenix-001-round2` | 2026-11-09 01:13 | `cd63c7245b` | 7/0 | #24 |
| `research/phoenix-002-h8-validation` | 2026-11-09 03:44 | `c826703126` | 10/0 | #25 |
| `research/phoenix-003-early-evidence` | 2026-11-09 05:38 | `91495bce95` | 4/0 | #26 |
| `research/data-expansion-001` | 2026-11-09 06:19 | `192085e781` | 7/0 | #27 |
| `foundation/atlas-001` | 2026-11-11 01:49 | `c63683631a` | 4/0 | #28 |
| `research/horizon-001` | 2026-11-11 01:37 | `2dcdc99510` | 4/0 | #29 |
| `integration/convergence-001` | **2026-11-12 00:34** | `c6606c301b` | 9/0 | #30, newest commit in repo |

[FACT] The repository's last push was 2026-11-11T16:34Z on `integration/convergence-001` (`_FACTS.md:42`); the newest tip I measure is 2026-11-12 00:34+08:00 = 2026-11-11 16:34Z — same commit, different clock representation. [INFERENCE] no work has landed anywhere since #30's last push; the repo is idle as of the audit window.

---

## 6. Remote branches with **no PR** (review gap)

| Branch | Ahead | What it contains | Finding | Recommendation |
|---|---:|---|---|---|
| `integration/phase4-base` | 39 | 472-file tree, +235,453/−2; inherits #12–#14; the declared base of #21 | **review target with no review surface** (`_FACTS.md` C6:254) | open a PR; or retarget #21 to #14 and retire this branch |
| `research/early-signal-ai-review` | 11 | 85 added files: `experiments/hist_v1` (11), `hist_v2` (9), `b099`–`b105`, `research/protocols` (5), `papers/PAPER_UPDATE_v1.md`, `research/RESEARCH_STATE.md` | **substantive unreviewed work**, and it **contains `research/full-history-v1`** (verified ancestor) | open a PR or explicitly archive; do not merge silently |
| `research/full-history-v1` | 1 | 19 added files: `experiments/hist_v1` (11), `research/protocols` (2), `tests/test_hist_eval.py` | superseded by `early-signal-ai-review` | archive |
| `research/cycle2-coverage-power` | 0 | fully merged content (70 behind) | historical branch, no PR record | archive |

[INFERENCE] `research/early-signal-ai-review` is the most likely "lost work" in the repository: 11 commits of a full-history benchmark with no PR, and it is the superset of another PR-less branch. It is also **the only branch that adds `experiments/hist_v1` + a paper update**, i.e. a distinct scientific line.

---

## 7. Flagged findings (including the four brief gaps)

### 7.1 PR #1 — `CONFLICTING`, 154 commits behind, **and already superseded** [FACT]

- **State:** OPEN, not draft, base `main`, head `feat/frontier-device-radar`, **13 ahead / 154 behind**, `mergeStateStatus=DIRTY` (`_FACTS.md:113`).
- **Locally proven:** `git merge-tree --write-tree origin/main origin/feat/frontier-device-radar` → exit 1, **11 conflicted paths**: `CHANGELOG.md`, `README.md`, `README.zh-CN.md`, `docs/DATA.md`, `docs/docs/ASSUMPTIONS.md` (modify/delete — a doubled `docs/docs/` path in the branch), `medradar/__init__.py`, `medradar/adcom.py` (add/add), `pyproject.toml`, `tests/test_frontier.py`, `verifier/README.md`, `verifier/v1/verify.py` (`final_checks.py`, deduplicated CONFLICT lines).
- **The decisive finding:** the branch's 13 "added" files are **already on `main`** except 5 verifier artefacts. Verified one-by-one:

| Path added by #1 | On `main`? |
|---|---|
| `medradar/adcom.py`, `medradar/frontier.py` | **YES** (byte-identical: `frontier.py` blob `3a0b2d72…` on both) |
| `tests/fixtures/adcom_calendar.html`, `adcom_detail.html` | YES |
| `tests/test_frontier.py`, `tests/test_research_integrity.py` | YES |
| `verifier/README.md`, `verifier/v1/verify.py` | YES |
| `verifier/v1/acceptance.md` | **NO** |
| `verifier/runs/2026-10-31T{06-30-00Z-v1-baseline,18-53-30Z-v1-final,22-40-02Z-v1-merged-final}.json`, `verifier/runs/index.ndjson` | **NO** |

[INFERENCE] PR #1 was opened 2026-11-01 01:44Z; its content reached `main` via the 2026-11-02 merge train (#2–#11) by another path. The PR is a stale fork whose remaining diff is 31 outdated file versions plus 5 historical verifier logs. **Its "frontier intelligence" feature is already shipped** — `medradar/frontier.py`, `medradar/adcom.py` and `test_frontier.py` are on `main` today (`medradar/__main__.py` even has a `frontier` subcommand).
**Recommended disposition [RECOMMENDATION]:** **supersede / close** (do *not* delete the branch until the 5 verifier artefacts are copied to a preservation branch). Do not spend review effort on the conflict.

### 7.2 PRs #18, #21, #22 — omitted from the user brief [FACT]

The brief named #2–#17, #19–#20, #23–#30 but not these three. All are real, open and drafted:

| PR | Head | Files | +/− | Why it matters |
|---:|---|---:|---|---|
| **#18** | `research/ai-evidence-review` | 4 | +575 | 1 commit; independent AI review of the 69 early-signal packets. **Machine review, explicitly not human** (PR title). Cheap to review, cheap to merge. |
| **#21** | `research/innovation-signals-observatory` | 96 vs base / 567 vs main | +64,441 | Phase 4 recruitment lane. Its declared base is the PR-less `integration/phase4-base`; 133 files are product-stack copies; 247 are `overnight-qlora` copies (verified). |
| **#22** | `research/s031-hiring-capability-study` | 600 | +303,926 | **Largest open diff after #29/#30, and mostly not its own work**: 560/600 added files are byte-identical to #21 (verified); **phase4-base, #21 and #15 (S-028) are ancestors**. Genuine delta: **33 files / +4,032**. |

### 7.3 `integration/phase4-base` — a base branch with no PR [FACT]

- 39 commits ahead of `main`, 472-file tree, +235,453/−2; **no PR, no review, no CI of its own** (`_FACTS.md` C6:254).
- Verified ancestor of #21 (and therefore of #22). **Its ancestry is `#12 → #13 → #14 → #15 (S-028) → phase4-base`**: `git rev-list --count origin/research/s028… ^origin/integration/phase4-base` = **0**, and `research/studies/graph_early_signal_s028/` is present in its tree. So it contains the product stack **and the S-028 study**, plus 13 phase-4 commits.
- [RECOMMENDATION] This is the highest **process** risk in the repository: two research PRs cite it as "base", so merging either silently lands 39 unreviewed commits — including a study branch that was never merged on its own. Either open a PR for it or retarget #21 to `feat/observatory-reliability-v1` and rebase the phase-4 commits.

### 7.4 Local `research/phoenix-001-external-methods` — 33 ahead of its remote twin, **and 16 behind it** [FACT]

`_FACTS.md:189-195` reports "33 commits not on any remote". Measured precisely:

| Measure | Value | Command |
|---|---:|---|
| local ahead of `main` | **33** | `git rev-list --count origin/main..research/phoenix-001-external-methods` |
| local ahead of its **remote twin** (`bd2f839`) | **33** | `git rev-list --count origin/research/phoenix-001-external-methods..research/phoenix-001-external-methods` |
| local **behind** its remote twin | **16** | `git rev-list --left-right --count` → `33 16` |
| commits reachable from **no remote** | **7** | `git log --oneline research/phoenix-001-external-methods --not --remotes` |
| merge-base with remote twin | `b2a14c0` (**main HEAD**) | `git merge-base` |

**Interpretation [FACT + INFERENCE]:** this is not "33 unpushed commits on top of the PR branch", and the 26 vs 7 split is **not** about a second remote.

| Measured fact | Value | Command |
|---|---|---|
| commits ahead of `main` | 33 | `git rev-list --count origin/main..<local>` |
| of those, contained in `integration/phase4-base` | **26** | `git rev-list --count <local> ^origin/integration/phase4-base` → 7 remain |
| **fork point** of the local branch | **`4c6686f` = the tip of `research/s028-temporal-graph-early-signal`** | `git merge-base <local> origin/integration/phase4-base` |
| local branch contains S-028 tip | **YES** | `merge-base --is-ancestor <s028 tip> <local>` |
| commits unique to this machine | **7** | `git log --oneline <local> --not --remotes` |
| local behind its remote twin | **16** | `--left-right --count` → `33 16` |

[INFERENCE] The local PHOENIX branch was accidentally created **on top of S-028's tip**, i.e. on the unmerged product+S-028 stack; its 26 inherited commits are `#12→#14→#15`, not PHOENIX work. The remote twin (`bd2f839`, 16 ahead) is `main`-based. So the two lineages have **different bases as well as different commits**, and PR #23's visible 40-file/+6,075 diff is the main-based variant only. A reviewer cannot see the local 7-commit variant, and a merge of the remote branch would bring nothing from the local work.
**Disposition [RECOMMENDATION]:** **park #23**; create a preservation branch/archive for the 7 unique commits; reconcile the two lineages (rebuild the 16 remote commits on the local line, or split PHOENIX-001 into "round 1 remote" and "local extended") before any review.

### 7.5 Copy-paste duplication — quantified [FACT]

Measured by blob SHA, files added vs `main` that are byte-identical to another open-PR head (`verify_ancestry.py`, `convergence_dup.py`):

| PR | Added vs main | Duplicated from | Identical | **Genuine remainder** | Share duplicated |
|---:|---:|---|---:|---:|---:|
| #30 | 813 | #29 (654) + #28 (67) | 721 | **92** | **88.7 %** |
| #22 | 592 added (600 changed) | #21 (560) | 560 | **33** (diff vs #21 = +4,032/−0) | **94.6 %** |
| #21 | 560 | #20/#19 (247), #14 (133), #15/#16 (219 cross) | 247+ | 96 vs base | 44 % of added |
| #16 | 339 | #14 (134) | 134 | 205 vs base | 39.5 % |
| #15 | 220 | #14 (134) | 134 | 86 vs base | 61 % |
| #25 | 225 | #24 (166) — **#24 is its ancestor** | 166 | 59 vs base | expected |
| #12 | 53 | #13–#16/#21/#22 (43) — **#12 is their ancestor** | 43 | 57 vs main | expected |

**FACT for #30:** `research/horizon-001` is **not** an ancestor of `integration/convergence-001` (`merge-base --is-ancestor` → false), while `foundation/atlas-001` **is** (true). Therefore #30's atlas content is legitimate inheritance but its horizon content is **copy-paste**. The Lead's independent count was 651/813 (80.1 %); mine is 654/813 (80.4 %) — the 3-file delta is a counting convention; both confirm the duplication.

### 7.6 Version and README drift [FACT]

Across `main` + 20 open-PR heads (`blob_variants_check.py`):

| File | Distinct blobs | Distribution |
|---|---:|---|
| `README.md` | **7** | main 10 refs · observatory group 5 · frontier/2.0/live/maintenance/atlas+convergence singletons |
| `pyproject.toml` | **5** | main 11 refs · product stack 5 · local-llm 2 · innovation/s031 2 · frontier 1 |
| `CHANGELOG.md` | **3** | main 18 refs · innovation/s031 2 · frontier 1 |

[INFERENCE] The Lead's earlier figures (README 2, pyproject 3) are **not reproducible** over this ref set; I report the recomputed values with the exact ref list. Regardless of count, there is no single source of project identity. [RECOMMENDATION] freeze root docs on `main` and require every branch to rebase them away before merge.

### 7.7 `main` health baseline [FACT, measured]

`python -B -m pytest -p no:cacheprovider -q` on `b2a14c0` → **exit 0**; `--collect-only` → **1,074 tests**. This is the acceptance bar for every merge in §4.2. [UNVERIFIED] branch test suites were not run; a PR's own "tests pass" claim cannot be checked from git objects alone.

### 7.8 Data-rights contamination in #29, sanitised in #30 [FACT — highest severity]

`origin/integration/convergence-001:docs/convergence/LICENCE_AND_SECURITY_REVIEW.md` states:
- UN Comtrade is **redistribution-blocked** (608 of 6,492 records);
- the restricted payload **is on PR #29's public branch**: 30 paths / 29 distinct blobs / 6,234,301 B, commit `18a7580`;
- the convergence branch has **0 of 30** quarantined paths (export gate PASS).

I verified this independently by diffing the two trees (`horizon_vs_convergence.py`): of the 691 files added by `research/horizon-001`, exactly **37 are absent or different in `integration/convergence-001`**, and they are precisely:

| Group | Files | Examples |
|---|---:|---|
| UN Comtrade `DATASETS/…/raw/` exports | **27** | `annual_2015–2024.json` (10), `monthly_202501–202512.json` (12), `hs.json`, `reporters.json`, `summary.json`, `api_root.html`, `comtradeplus_home.html` |
| UN Comtrade derived exports | **3** | `experiments/industry/evidence/un_comtrade.jsonl`, `exports/horizon-2026-11-10/un_comtrade.jsonl`, `.jsonl.sha256` |
| UK Find a Tender raw award packages | **3** | `…/uk_find_a_tender/raw/award_packages_p1–p3.json` |
| Derived files that quote Comtrade figures | **4** | `EXPERIMENT_RESULTS.md`, `experiments/industry/EXP_H4_INDUSTRY.json`, `reports/INDUSTRY_DATA_REPORT.md`, `reports/REGULATORY_FRONTIER_REPORT.md` |
| **Total differing files** | **37** | 30 Comtrade + 3 UK-tender + 4 derived |

**Implication [INFERENCE]:** #30 is the **sanitised** horizon copy; #29 is the **unsanitised** one. Merging #29 would publish restricted data into `main` and its Pages site. Merging #30 instead would preserve the research while omitting the payload.
**Recommendation [RECOMMENDATION]:** do **not** merge #29 as-is; either rewrite/strip #29's history (owner authorisation required) or treat #30 as the sole horizon integration and close #29 as superseded. Escalate the already-public exposure to the owner and to `DATA_GOVERNANCE_AUDIT` regardless — the blob is on a public remote now.

### 7.9 The brief's framing vs measurement

| Brief claim | Measurement | Verdict |
|---|---|---|
| "only PRs #2–#11 are merged" | 10 merged, 0 closed-unmerged | FACT confirmed |
| "PRs #1 and #12–#30 are open (19 drafts)" | #1 is **not** a draft; #12–#30 are 19 drafts; 20 open total | **correct** |
| "34 remote branches" | 34 non-HEAD remote refs (incl. `main`); 33 non-main | FACT (definition) |
| "39 local worktrees" | 39 entries under `worktrees/` **+ 1 primary checkout = 40** in `repo_facts.worktrees` | consistent |
| "33 unpushed commits on local phoenix" | 33 ahead of its remote twin, **16 behind it**; only **7** on no remote | **imprecise — see §7.4** |
| "PR #18/#21/#22 omitted from brief" | all exist, all drafts | Lead flagged correctly |

---

### 7.10 Local state: 40 worktree entries (one per branch, mostly)

[FACT] `git worktree list --porcelain` returns **40** entries = the primary clone `<REDACTED_LOCAL_PATH> + **39** registered worktrees, matching `_FACTS.md:198` and `repo_facts.json`. This is why "the local machine" holds state that no remote shows.

| Worktree | Checkout | Note |
|---|---|---|
| `<REDACTED_LOCAL_PATH> (**primary clone**) | `4c6686f` = **S-028 tip** | [INFERENCE] explains why the local PHOENIX branch forks at S-028 (§7.4): the main checkout sat on the S-028 branch |
| `worktrees/refoundation-001` | `b2a14c0` @ `audit/refoundation-001` | this audit's tree |
| `worktrees/audit-base` | `7a639f7` detached | the `v0.2.2` commit cited in `docs/ATTRIBUTION.md:5` |
| `worktrees/audit-pr1` / `audit-pr2` / `audit-pr3` | `94c6a10` / `dedfd68` / `ad38d27` detached | historical PR-review trees |
| `worktrees/fix-pr1` / `fix-pr2` / `fix-pr3` | `fa3514c` / `456c638` / `1d8ee97` | local `fix/*` branches (0 ahead, 98–102 behind) |
| `worktrees/integration-dry` | `4f4a999` @ `integration/audit-dryrun` | **1 commit on no remote** |
| `worktrees/phase1-targets`, `phase2-aux`, `phase2-market`, `phase3-agent`, `phase3-registry`, `phase3-tkg` | `cc1799…`–`ad53ef6` | phase lineage; 0 ahead except `phase3/registry-cycle` (**1 unique commit**) |
| `worktrees/kimi-forecast` | `d5aa16c` @ `research/forecast-registry` | **2 unique commits** |
| `worktrees/kimi-tkg` / `kimi-tkg-hardening` / `deepseek-research` / `deepseek-tkg-review` | `f1b8132` / `75acc2d` / `1d9e0d1` / `f194520` | TKG history; `research/temporal-knowledge-graph` has **2 unique commits** |
| `worktrees/kimi-research` / `kimi-integration` | `a362bac` / `dedfd68` | independent-validation / foundation |
| `worktrees/ai-review`, `atlas-001`, `convergence-001`, `data-expansion-001`, `es-ai-review`, `hist-v1`, `horizon-001`, `local-llm-research`, `maint-consolidation`, `overnight-s030`, `phase4`, `phoenix002`, `phoenix003`, `s029-relations`, `s031-delivery`, `study-early-signal`, `integration-v2` | matching branch tips | one worktree per open PR/branch; `s031-delivery` is a local alias of `research/s031…` |

[RECOMMENDATION] Worktrees are cheap to recreate but expensive to audit: 39 parallel checkouts is why local branch state (unpushed commits, dirty trees, detached review checkouts) diverged from remote. Before refoundation, record `git worktree list` and the 5 unpushed branches, then prune the 30+ worktrees whose branches are merged or archived. **Do not delete them during this audit** — `_FACTS.md:198` explicitly says "Do not disturb them".

## 8. Disposition summary (recommendation only)

| Disposition | PRs | Count |
|---|---|---:|
| **No action — already merged** | #2–#11 | 10 |
| **Merge (ordered)** | #12, #13, #14, #17, #18, #19, #24, #25, #26, #28 | 10 |
| **Merge after split** | #21 (phase4 retarget), #22 (33 files), #27 (code vs evidence), #30 (92 files) | 4 |
| **Park** | #15, #16 (until #14), #20 (do-not-merge), #23 (until local/remote reconciliation) | 4 |
| **Hold / supersede** | #29 (restricted payload), #1 (superseded) | 2 |
| **Total** | | **30** |

**Remote-branch dispositions:** archive/delete the **9 distinct** merged heads; open a PR for `phase4-base` and `early-signal-ai-review` (or archive the latter); archive `full-history-v1` and `cycle2-coverage-power`; keep all 20 PR heads until their PRs close.

**If the owner wants the smallest possible reduction:** #1 (close) + #29 (supersede) + #20 (archive) + #30 (split) removes or shrinks **~1.4 M** of the 2.8 M added lines with **zero functional loss** — because #1 duplicates `main`, #29 duplicates #30's sanitised tree, #20 is explicitly exploratory, and #30 duplicates #29/#28.

### 8.1 Per-PR rationale (why each disposition, one block each)

[RECOMMENDATION] blocks. Facts are cited; the decision is the owner's.

**#1 — supersede.** All 13 feature files are already on `main` (8 on-main, 5 historical verifier artefacts); 31 files are stale versions; 11 conflicts. Merging would regress `main` to an older tree. Action: copy `verifier/{v1/acceptance.md,runs/2026-10-31*}` to a preservation branch, then close. **Do not merge.**
**#12 — merge.** 8 commits, 57 files, clean, no ambiguity; it is the base of everything product. Mark ready-for-review and merge first in the product stack.
**#13 — merge after #12.** 8 commits, 57 files vs base; clean. Its diff-vs-`main` looks 2× larger only because it inherits #12.
**#14 — merge after #13.** 6 commits, 54 files; adds `deploy/` and reliability docs. It is the last product PR that is still reviewable in one sitting.
**#15 — park, then merge only as part of the chain.** 4 commits, 86 files; PR title says **do not merge**. It is an ancestor of `phase4-base`, so its content would land anyway if #21 merges. Decide the chain first; merging #15 alone drags nothing, but is scientifically a NO-GO study.
**#16 — park until #14, then merge.** 12 commits, 205 files; sibling of #15; NO-GO study. Cheapest to review after the product stack is in.
**#17 — merge early.** 2 commits, 6 files, docs only (+947/−805). It fixes the docs that every other branch conflicts with; merging early reduces later churn.
**#18 — merge early.** 1 commit, 4 files. Explicitly a machine review, not human truth; provenance is in the PR title. Least risky PR in the repository.
**#19 — merge only if the LLM lane is funded.** 9 commits, 110 files. GPU results are [UNVERIFIED] from git objects; no weights committed (good). The code is separable from the claim.
**#20 — park/archive.** 11 commits, 147 files; PR body says 不合并. It is an overnight exploratory run; keep as evidence, do not merge.
**#21 — split, retarget, then merge.** 7 genuine commits / 96 files over a **PR-less base** (`phase4-base`) that itself contains product + S-028. Action: either open the phase4-base PR first, or retarget #21 to #14 and rebase the 7 phase-4 commits. Never merge it as a review bypass.
**#22 — split; never merge as-is.** Declared base `main` but contains #15 + phase4-base + #21; **560 of 600 changed files are #21's**. Genuine contribution: 33 files / +4,032 (`research/s031`, `medradar/recruitment`, `config/recruitment_function_classes.json`, verifier v2, `S031_DELIVERY_MANIFEST.json`). Rebase onto #21 after it merges, then review 33 files.
**#23 — park.** Remote is main-based (16 commits, 40 files); local is S-028-based (33 ahead, 16 behind, 7 unique). The PR shows neither the local work nor the real base. Reconcile before review.
**#24 — merge after PHOENIX scope decision.** 7 commits, 166 files, no duplication detected; largest clean research PR. It is the best candidate for "merge one research programme to prove the gate works".
**#25 — merge after #24.** 3 commits, 59 files; verified ancestor stack; NO-GO verdict. Low review cost once #24 is in.
**#26 — merge or park.** 4 commits, 104 files, independent; NO-GO study with a reusable control battery. Merge if PHOENIX is in scope; otherwise archive with #24/#25.
**#27 — split code vs evidence.** 916 files, 863 under `research/data_expansion/` (JSON/MD evidence), 46 under `medradar/external_sources/`, 6 tests. Merge the 46+6 code path and treat evidence as a data-release artifact.
**#28 — merge.** 4 commits, 70 files: `medradar/atlas/` (31), `research/atlas/` (16), `docs/atlas/` (10), config, tests, tools. It is an ancestor of #30, so it must land first in any convergence plan.
**#29 — hold/supersede.** 4 commits but **33 restricted raw files** (Comtrade/UK-tender) and derived reports quoting them. Do not merge as published; either strip/rewrite the branch or take #30's sanitised copy. This is a licence decision, not a code decision.
**#30 — split, then merge 92 files.** 9 commits; 721 of 813 added files duplicate #29/#28; 92 net-new (`medradar/integration/`, `docs/convergence/`, `research/convergence/`, `tools/convergence/`, `tests/convergence/`, 2 workflows). Rebase onto #28 after it merges, drop the 654 horizon copies (depend on the sanitised horizon source instead), then review 92 files.

---

## 9. Reproducible command appendix

```bash
# 1. PR ledger (do NOT re-query the API without the collector)
python docs/refoundation/_evidence/inventory/probe_facts.py

# 2. Divergence for every branch (note: left-only = behind, right-only = ahead)
git rev-list --left-right --count origin/main...origin/research/horizon-001

# 3. Full branch/PR matrices used in §2 and §5
python docs/refoundation/_evidence/inventory/collect_inventory.py
python docs/refoundation/_evidence/inventory/summarize_inventory.py prs branches local
python docs/refoundation/_evidence/inventory/summarize_more.py merge counts

# 4. Declared-base vs main deltas (§2.2) and true deltas (§7.5/7.6)
python docs/refoundation/_evidence/inventory/pr_deltas.py
python docs/refoundation/_evidence/inventory/true_deltas.py
python docs/refoundation/_evidence/inventory/convergence_dup.py

# 5. Ancestry (the only valid hidden-stack test)
git merge-base --is-ancestor origin/research/innovation-signals-observatory \
                           origin/research/s031-hiring-capability-study; echo $?   # 0 = YES
git merge-base --is-ancestor origin/research/horizon-001 \
                           origin/integration/convergence-001; echo $?            # 1 = NO (copy)
python docs/refoundation/_evidence/inventory/ancestry_extra.py
python docs/refoundation/_evidence/inventory/verify_ancestry.py

# 6. Merge feasibility (read-only; exit 1 == conflicts)
git merge-tree --write-tree origin/main origin/feat/frontier-device-radar          # 11 conflicts
for b in origin/feat/medradar-2.0-mvp origin/research/horizon-001; do \
  git merge-tree --write-tree origin/main "$b" >/dev/null || echo "CONFLICT $b"; done

# 7. Duplication / restricted-payload evidence (§7.5, §7.8)
python docs/refoundation/_evidence/inventory/horizon_vs_convergence.py
python docs/refoundation/_evidence/inventory/blob_variants_check.py

# 8. Local-only commit accounting (§7.4) — report BOTH definitions
git rev-list --count origin/research/phoenix-001-external-methods..research/phoenix-001-external-methods   # 33
git log --oneline research/phoenix-001-external-methods --not --remotes | wc -l                             # 7
git rev-list --left-right --count research/phoenix-001-external-methods...origin/research/phoenix-001-external-methods  # 33  16

# 9. Baseline acceptance bar (§7.7)
python -B -m pytest -p no:cacheprovider -q                                   # exit 0
python -B -m pytest -p no:cacheprovider --collect-only -q | tail -1          # 1074
```

**Method note on the ahead/behind inversion** (§0.2): an early version of my collector labelled the left count as "ahead", producing 154 ahead / 13 behind for #1. The correct reading of `--left-right --count A...B` is `<left-only = behind A…>`, `<right-only = ahead>`. All numbers in this document come from the corrected collector (`inventory_facts.json`, regenerated after the fix); `_FACTS.md:156-183` agrees with the corrected values.

---

## 10. Open questions for the owner

1. **Is PR #1 to be closed as superseded, or does the owner believe something in its 31 modified files is still wanted?** Evidence says the feature is on `main`; only 5 historical verifier artefacts are unique.
2. **Will the owner authorise opening a PR for `integration/phase4-base`** (or retargeting #21 to `#14`)? Without that, #21 and #22 cannot be reviewed honestly.
3. **What is PR #22's intent?** It shows 600 files / 303,926 lines but contains only 33 genuine files; was the author aware it inherits #21 + phase4-base?
4. **What should happen to #29 vs #30?** #29 is the unsanitised horizon branch (restricted Comtrade payload); #30 is the sanitised copy with 654 duplicated files. Merge the sanitised copy and close #29, or rewrite #29's history? Either needs explicit owner authorisation.
5. **Is the local `research/phoenix-001-external-methods` lineage (33 ahead / 16 behind its remote twin, 7 unique commits) to be preserved?** If yes, who pushes it, and to which branch?
6. **Are #15/#16 to be merged as studies after #14, or parked pending a scientific review?** Both are drafts and both physically depend on unmerged product code.
7. **Is the local-LLM lane (#19/#20) in scope for the refoundation?** #20's own PR body says "do not merge"; #19 claims a first real GPU run that cannot be verified from git objects.
8. **Which of PHOENIX-001 (#24), PHOENIX-003 (#26), data-expansion (#27) is funded?** They are independent; the audit can order merges but cannot rank scientific value.
9. **Should `research/early-signal-ai-review` (11 commits, no PR) get a PR, or be archived?** It is the only place `experiments/hist_v1` + `hist_v2` + `PAPER_UPDATE_v1` exist, and it contains `research/full-history-v1`.
10. **What is the acceptance gate for merging after `main`?** I recommend: `main` suite green (1,074), no ancestry containing a PR-less branch, <50 % blob duplication with another head, and no quarantined-dataset path. Owner sign-off needed on the duplication and licence thresholds.
