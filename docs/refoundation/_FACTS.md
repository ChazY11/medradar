# REFOUNDATION-001 — Verified Fact Base & Audit Charter

> **Status:** internal working document for the REFOUNDATION-001 audit team.
> **Collected:** 2026-11-12 (Asia/Shanghai) from live GitHub API + local git object store.
> **Machine-readable:** [`repo_facts.json`](_evidence/repo_facts.json) (regenerate with `collect_facts.py`).
> **This file is evidence, not a deliverable.** It is the shared ground truth every auditor builds on.

---

## 0. Audit doctrine (mandatory)

Every auditor MUST label statements as one of:

| Label | Meaning |
|---|---|
| **[FACT]** | Verified directly from git objects, GitHub API, file bytes, or a command whose output is cited. |
| **[INFERENCE]** | A reasoned conclusion from facts; state the reasoning chain. |
| **[RECOMMENDATION]** | A proposed action; not a finding. |
| **[UNVERIFIED]** | Could not be checked (network/data/tool gap). State exactly why. |

Rules:

1. **Never** infer state from a README, PR description, commit message, or another agent's report. Open the file / run the command.
2. **`main` is the only shipped state.** Anything on another branch is *not* a main capability. Say "on branch X" explicitly.
3. Do **not** delete, merge, force-push, rewrite, or modify any branch, PR, or frozen artifact. This worktree is the only write target.
4. Do **not** run `git fetch`, `git checkout`, `git switch`, `git reset`, `git merge`, `git rebase`, `git commit`, or `git push`. All refs are already fetched. Use `git show origin/<branch>:<path>`, `git ls-tree`, `git log origin/<branch>`, `git diff origin/main...origin/<branch>`.
5. Do **not** run network probes against production data sources (FDA, SEC, Comtrade, etc.). Cite committed evidence files instead.
6. Reading is unlimited. Writing is limited to **your assigned files** (see §10).
7. Prefer citing `path:line` or `git show <ref>:<path>`. A claim without a locator is worth little.
8. When two sources disagree, report both and say which is authoritative and why.

---

## 1. Repository identity

| Field | Value | Label |
|---|---|---|
| URL | `https://github.com/ChazY11/medradar` | FACT |
| Default branch | `main` | FACT |
| Visibility | public | FACT |
| Created | 2026-10-31T05:54:07Z | FACT |
| Last push | 2026-11-11T16:34:32Z (on `integration/convergence-001`, **not** main) | FACT |
| Stars / forks | 151 / 8 | FACT |
| Disk usage | 88,383 KB (~86 MiB) | FACT |
| Primary language | Python 4,262,504 bytes; PowerShell 9,618 bytes | FACT |
| Licence (GitHub) | `other` / "Other" | FACT |
| Licence (file) | MIT, "Copyright (c) 2026 MedRadar contributors" | FACT |
| Homepage | `https://chazy11.github.io/medradar/` | FACT |
| Issues | 0 (open **and** closed) — issue tracking is unused | FACT |
| Discussions / Wiki | both enabled, both unused as far as this audit observed | FACT |
| Releases | none | FACT |

**[INFERENCE]** GitHub classifies the licence as "Other" although `LICENSE` contains standard MIT text — likely because the file has no SPDX-recognisable header / the copyright line differs from the canonical template. A one-line licence metadata fix would restore the correct badge. *Verify in DATA_GOVERNANCE_AUDIT.*

---

## 2. `main` state (the only shipped code)

| Field | Value | Label |
|---|---|---|
| HEAD | `b2a14c0a92332c004445de686daee97754cf94cb` | FACT |
| HEAD subject | `Merge pull request #11 from ChazY11/research/early-signal-review-workbench` | FACT |
| HEAD date | 2026-11-02 | FACT |
| Files | 1,135 | FACT |
| Version in `pyproject.toml` | `0.5.0` | FACT |
| Version claimed in README body | "stable core through `v0.2.2`", "`v0.3.0` consolidates…" | FACT |

**[FACT] The single most important structural fact of this audit:**
`main` contains only the work merged through PR #11 on 2026-11-02.
Twenty PRs (#1, #12–#30) are still open, nineteen of them drafts, representing
**2,824,212 added lines** versus the 541,569 lines merged into main.
Everything described as "MedRadar 2.0", "Live Observatory", "PHOENIX", "ATLAS",
"HORIZON", "CONVERGENCE", "S-028…S-031", "QLoRA" etc. lives **only on branches**.

---

## 3. Full pull-request ledger (30 PRs, live API)

| PR | State | Draft | Base | Head | Merged | Files | +/- | Title |
|---|---|---|---|---|---|---|---|---|
| #1 | OPEN | no | main | feat/frontier-device-radar | - | 44 | +2709/-234 | Add frontier device intelligence and research safeguards |
| #2 | MERGED | no | main | research/research-foundation-integration | 2026-11-02 | 28 | +6014/-3 | feat(research): add bitemporal knowledge store and immutable forecast re |
| #3 | MERGED | no | main | feature/market-to-rd | 2026-11-02 | 60 | +2453/-25 | Add Market-to-R&D intelligence and horizon forecasting |
| #4 | MERGED | no | main | integration/market-to-rd-v2 | 2026-11-02 | 173 | +59831/-543 | v0.3.0: integrate research foundation (TKG + forecast registry) and Mark |
| #5 | MERGED | no | main | research/change-detection-v1 | 2026-11-02 | 901 | +444600/-543 | MedRadar Foresight Lab: change detection, company profiles, frozen forec |
| #6 | MERGED | no | main | research/early-signal-5firms | 2026-11-02 | 97 | +24205/-39 | Early-signal study (Phase 0-1D): five-firm cross-source audit, four pre- |
| #7 | MERGED | no | main | research/early-signal-postmerge | 2026-11-02 | 1 | +28/-0 | docs(study): publication record for PR #6 merged as 4627672 |
| #8 | MERGED | no | main | research/early-signal-third-source | 2026-11-02 | 9 | +1375/-0 | feat(study): Europe PMC third-source cross-check — one near-term hit, th |
| #9 | MERGED | no | main | research/early-signal-adjudication | 2026-11-02 | 7 | +2012/-0 | feat(study): agent pre-adjudication of the 69 packets — a non-human tier |
| #10 | MERGED | no | main | research/early-signal-review-workbench | 2026-11-02 | 8 | +742/-0 | feat(study): human review workbench — 69-row worksheet, guide, and a val |
| #11 | MERGED | no | main | research/early-signal-review-workbench | 2026-11-02 | 5 | +309/-2 | feat(study): drop-down-validated Excel workbook for the human review, wi |
| #12 | OPEN | yes | main | feat/medradar-2.0-mvp | - | 57 | +17646/-1 | MedRadar 2.0 MVP: evidence-driven company, radar, analyst and evidence p |
| #13 | OPEN | yes | feat/medradar-2.0-mvp | feat/live-observatory-v1 | - | 57 | +31301/-7 | MedRadar Live Observatory v1: append-only observation ledger, official-s |
| #14 | OPEN | yes | feat/live-observatory-v1 | feat/observatory-reliability-v1 | - | 54 | +22899/-71 | MedRadar Observatory Reliability: durable persistence, verified backups, |
| #15 | OPEN | yes | feat/observatory-reliability-v1 | research/s028-temporal-graph-early-signal | - | 86 | +114442/-0 | S-028: temporal company-technology graph early-signal study (DRAFT, nega |
| #16 | OPEN | yes | feat/observatory-reliability-v1 | research/s029-evidence-based-relations | - | 205 | +133237/-0 | S-029: evidence-based temporal relation reconstruction — measured eviden |
| #17 | OPEN | yes | main | maintenance/repository-consolidation | - | 6 | +947/-805 | Repository consolidation: documentation, research index, and data asset |
| #18 | OPEN | yes | main | research/ai-evidence-review | - | 4 | +575/-0 | AI evidence review of the 69 early-signal packets (machine review, not h |
| #19 | OPEN | yes | main | research/local-llm-foundation | - | 110 | +32464/-0 | research(local-llm): Phase 2 — first real local GPU run (Qwen3-4B-Instru |
| #20 | OPEN | yes | research/local-llm-foundation | research/overnight-qlora-s030 | - | 147 | +16826/-55 | research(overnight): 隔夜探索性 QLoRA 训练与四臂独立评价（Draft，不合并） |
| #21 | OPEN | yes | integration/phase4-base | research/innovation-signals-observatory | - | 96 | +64441/-0 | Phase 4: Innovation Signals Observatory — recruitment lane, real collect |
| #22 | OPEN | yes | main | research/s031-hiring-capability-study | - | 600 | +303926/-2 | S-031: hiring capability & R&D evidence study - 100 AI preliminary label |
| #23 | OPEN | yes | main | research/phoenix-001-external-methods | - | 40 | +6075/-0 | PHOENIX-001: External methods audit and reproducible experiments |
| #24 | OPEN | yes | main | research/phoenix-001-round2 | - | 166 | +158731/-0 | PHOENIX-001 round 2: frozen protocol, ten pre-registered experiments, 13 |
| #25 | OPEN | yes | research/phoenix-001-round2 | research/phoenix-002-h8-validation | - | 59 | +58438/-0 | PHOENIX-002: independent H8 re-validation - methodology audit and a NO-G |
| #26 | OPEN | yes | main | research/phoenix-003-early-evidence | - | 104 | +197464/-0 | PHOENIX-003: regulatory-anchored early-evidence discovery - rigorous NO-G |
| #27 | OPEN | yes | main | research/data-expansion-001 | - | 916 | +260389/-0 | DATA-EXPANSION-001: global data-source discovery, live access verificati |
| #28 | OPEN | yes | main | foundation/atlas-001 | - | 70 | +18648/-0 | ATLAS-001: identity, evidence and graph foundation (identity pilot + ind |
| #29 | OPEN | yes | main | research/horizon-001 | - | 691 | +692975/-0 | HORIZON-001: 全球数据前沿 — 两条免密专利通道、真实证据导出与三项实测实验（Draft） |
| #30 | OPEN | yes | main | integration/convergence-001 | - | 815 | +690079/-0 | CONVERGENCE-001: ATLAS x HORIZON end-to-end integration, P0 reconciliation |

**Summary:** 10 merged · 20 open (19 drafts) · 0 closed-unmerged.
**PR #1 is `CONFLICTING` (`mergeStateStatus=DIRTY`), 154 commits behind main.**
**The user brief did not mention #1, #18, #21, #22 — they are real and must be audited.**

---

## 4. Branch stack graph (base ← head)

```
main (b2a14c0, PR #11)
├── #1  feat/frontier-device-radar            (CONFLICTING, +2709)
├── #12 feat/medradar-2.0-mvp                 (+17,646)
│   └── #13 feat/live-observatory-v1          (+31,301)
│       └── #14 feat/observatory-reliability-v1 (+22,899)
│           ├── #15 research/s028-temporal-graph-early-signal (+114,442)
│           └── #16 research/s029-evidence-based-relations    (+133,237)
├── #17 maintenance/repository-consolidation  (+947/-805)
├── #18 research/ai-evidence-review           (+575)
├── #19 research/local-llm-foundation         (+32,464)
│   └── #20 research/overnight-qlora-s030     (+16,826)
├── #22 research/s031-hiring-capability-study (+303,926)
├── #23 research/phoenix-001-external-methods (+6,075)
├── #24 research/phoenix-001-round2           (+158,731)
│   └── #25 research/phoenix-002-h8-validation (+58,438)
├── #26 research/phoenix-003-early-evidence   (+197,464)
├── #27 research/data-expansion-001           (+260,389)
├── #28 foundation/atlas-001                  (+18,648)
├── #29 research/horizon-001                  (+692,975)
└── #30 integration/convergence-001           (+690,079)
integration/phase4-base (no PR; 39 ahead of main; contains #12→#14 **and the S-028 tip**)
└── #21 research/innovation-signals-observatory (+64,441)
```

**Key structural consequences:**

- `#13/#14` form a **3-deep product stack** on `#12`; `#15/#16` are stacked on top of `#14` — i.e. the research studies physically depend on unmerged product code.
- **`#15` (S-028) is itself an ancestor of `integration/phase4-base`, `#21` and `#22`** (verified: `git rev-list --count origin/research/s028-... ^origin/integration/phase4-base` = 0). The stack is therefore **5 deep**, and #21/#22 silently import the product stack *and* S-028.
- `#20` depends on `#19`; `#25` depends on `#24`.
- `integration/phase4-base` is a **base branch with no PR of its own**; `#21` targets it. It is 39 commits ahead of main and invisible to reviewers.
- Every stacked branch is 0 behind its own base (clean stacks), so the blocker is policy/merge order, not conflicts — except #1, the only conflicting PR.

---

## 5. Branch divergence and unpushed work

All remote branches: 34 non-HEAD refs. Divergence vs `origin/main`:

| Branch | Ahead | Behind |
|---|---|---|
| feat/frontier-device-radar | 13 | **154** |
| feat/medradar-2.0-mvp | 8 | 0 |
| feat/live-observatory-v1 | 16 | 0 |
| feat/observatory-reliability-v1 | 22 | 0 |
| maintenance/repository-consolidation | 2 | 0 |
| research/ai-evidence-review | 1 | 0 |
| research/local-llm-foundation | 9 | 0 |
| research/overnight-qlora-s030 | 11 | 0 |
| research/innovation-signals-observatory | 46 | 0 |
| integration/phase4-base | 39 | 0 |
| research/s031-hiring-capability-study | 83 | 0 |
| research/s028-temporal-graph-early-signal | 26 | 0 |
| research/s029-evidence-based-relations | 34 | 0 |
| research/phoenix-001-external-methods | 16 | 0 |
| research/phoenix-001-round2 | 7 | 0 |
| research/phoenix-002-h8-validation | 10 | 0 |
| research/phoenix-003-early-evidence | 4 | 0 |
| research/data-expansion-001 | 7 | 0 |
| foundation/atlas-001 | 4 | 0 |
| research/horizon-001 | 4 | 0 |
| integration/convergence-001 | 9 | 0 |
| research/full-history-v1 | 1 | 0 |
| research/early-signal-ai-review | 11 | 0 |
| (merged branches) | 0 | 5–140 |

**Unpushed local work (exists on this machine only):**

| Local branch | Remote twin | Ahead / behind twin | Unique (not on any remote) |
|---|---|---|---|
| `research/phoenix-001-external-methods` | `bd2f839` | **33 / 16** | **7** |
| `research/temporal-knowledge-graph` | none | 2 | 2 |
| `research/forecast-registry` | none | 2 | 2 |
| `phase3/registry-cycle` | none | 1 | 1 |
| `integration/audit-dryrun` | none | 1 | 1 |

**[FACT]** A local `research/phoenix-001-external-methods` is 33 commits ahead of the remote twin but **16 behind** it, has **7 commits not on any remote**, and forks from the S-028 tip. The PR therefore shows stale content, and "33 unpushed" conflates ahead (33), behind (16) and unique (7). `research/early-signal-ai-review` is a 4th PR-less remote branch (11 ahead) and is the sole home of the `full-history-v1` work.
**[RECOMMENDATION]** Preserve the 7 unique commits before any branch cleanup (see MIGRATION_PLAN).

**39 worktrees** are registered in `<REDACTED_LOCAL_PATH> including detached audit trees and the `fix/pr1..pr3` local fix branches. Do not disturb them.

---

## 6. `main` asset footprint

| Top-level | Files | MiB |
|---|---|---|
| experiments | 657 | 15.05 |
| docs | 60 | 6.39 |
| config | 10 | 2.18 |
| medradar | 87 | 1.77 |
| research | 116 | 1.33 |
| tests | 105 | 1.25 |
| papers | 32 | 0.51 |
| scripts | 13 | 0.38 |
| tools | 15 | 0.06 |
| verifier | 22 | 0.03 |
| .github | 8 | 0.01 |
| **total** | **1,135** | **~29** |

Notable single artefacts on main:

| Path | Bytes | Note |
|---|---|---|
| `docs/dashboard.html` | 3,350,819 | single-file dashboard; Pages asset |
| `docs/preview.png` | 488,736 | README hero image |
| `docs/metrics.json` | 468,561 | committed metrics snapshot |
| `docs/report_zh.md` | 55,768 | generated report |
| `docs/summary.csv` | 68,460 | generated summary |
| `README.md` | 31,738 | long; mixes product, research, results |
| `README.zh-CN.md` | 26,132 | Chinese mirror |

`medradar/` on main has 87 files: core pipeline, `intelligence/` (sources, features, models, evaluation, forecasting), `tkg/`, `studies/`, plus collectors and CLI.
`tests/` has 48 test modules and fixtures; README claims **678 offline tests** (unverified by this collector — owners must run them).
`experiments/` is dominated by `experiments/b027` (391 files) plus `b0xx`, `detect_v1`, `cycle2_coverage`, `reverse_rd_v1/v2`.

---

## 7. GitHub Pages and CI

- **Pages:** `build_type=legacy`, `source = main:/docs`, status `built`, last build commit `b2a14c0` (2026-11-02). The site therefore reflects **main only**; none of PR #12–#30 is published.
- **Workflows on main:** exactly four — `.github/workflows/{ci,forecast-cycle,live,weekly}.yml`. `observatory.yml`, `atlas.yml` and `convergence.yml` exist only on branches. `.github/` also contains 3 issue templates and a PR template, but **no `CODEOWNERS`**.
- **Branch protection:** `GET /repos/ChazY11/medradar/branches/main/protection` returns **404 "Branch not protected"** — `main` accepts direct pushes with no required checks.
- **Recent Actions:** runs named `ci`, `atlas`, `convergence` on `integration/convergence-001` — success and failure alternating on 2026-11-10/11. **[UNVERIFIED]** whether main's own CI is green; owners must run/inspect it.

---

## 8. Known contradictions to resolve (do not paper over)

| # | Contradiction | Where |
|---|---|---|
| C1 | `pyproject.toml` version `0.5.0` vs README "stable core through v0.2.2" / "v0.3.0 consolidates" | main |
| C2 | GitHub licence "Other" vs `LICENSE` = MIT | main |
| C3 | Homepage says "evidence-first research platform" (repo description) but README is an FDA weekly-intelligence brief with trading KPIs | main |
| C4 | README claims 678 tests, 375,378 events, 1.2 GiB SQLite, 2,384 cases — all snapshot-dependent and unverifiable from a clean clone | main |
| C5 | PR #23 shows remote branch content, but local branch is 33 commits ahead | local/git |
| C6 | `integration/phase4-base` is a review target with no PR | git |
| C7 | 19 draft PRs labelled "do not merge" coexist with product PRs that are blocked behind them | PRs |
| C8 | `research/` on main has `STATE.json`, `AUDIT.json`, `FINAL_AUDIT.json`, `BACKLOG.yaml` — possible competing state sources | main |

---

## 9. Navigation cheat-sheet

```bash
# from <REDACTED_LOCAL_PATH>
git show origin/main:README.md
git ls-tree -r --name-only origin/<branch>
git show origin/<branch>:<path>
git log origin/<branch> --oneline -30
git diff --stat origin/main...origin/<branch>
git diff origin/main...origin/<branch> -- <path>

# what changed in a study branch, docs only
git diff --stat origin/main...origin/research/phoenix-001-round2 -- '*.md'
```

Machine-readable facts: `docs/refoundation/_evidence/repo_facts.json`
(keys: `repo`, `main_head`, `pull_requests`, `pull_request_summary`, `issues`,
`pages`, `remote_branches`, `local_branches`, `main_tree_by_top_level`, `worktrees`).

---

## 10. Write-scope discipline (advisory lock)

| Owner | Sole write targets |
|---|---|
| lead | `docs/refoundation/EXECUTIVE_SUMMARY_ZH.md`, `DECISION_REGISTER.md`, `_evidence/repo_facts.json`, `_evidence/collect_facts.py`, `_FACTS.md` |
| inventory-auditor | `REPOSITORY_INVENTORY.md`, `BRANCH_PR_AUDIT.md`, `_evidence/inventory/` |
| architecture-auditor | `ARCHITECTURE_AS_IS.md`, `TECHNICAL_DEBT_REGISTER.md`, `_evidence/arch/` |
| research-registrar | `RESEARCH_ASSET_REGISTER.md`, `_evidence/research/` |
| data-governance | `DATA_GOVERNANCE_AUDIT.md`, `_evidence/data/` |
| target-architect | `ARCHITECTURE_TO_BE.md`, `MIGRATION_PLAN.md`, `_evidence/tobe/` |
| comms-lead | `README_REDESIGN_PROPOSAL.md`, `AGENT_COLLABORATION_PROTOCOL.md`, `_evidence/comms/` |

Never write outside your scope. Never write into `<REDACTED_LOCAL_PATH> Never touch files outside `docs/refoundation/`.

---

## 11. Deliverable quality bar

- Chinese for `EXECUTIVE_SUMMARY_ZH.md`; English for the other audit documents (bilingual headings allowed).
- Every table row must be traceable: path, branch, PR number, commit, or command.
- Start each document with a 10-line "Scope / Method / Evidence base / Limits" block.
- End each document with "Open questions for the owner".
- Distinguish **what exists** from **what is verified** from **what is recommended**.
- No fabricated metrics, screenshots, or "results". If a number cannot be reproduced, label it **[UNVERIFIED]**.
