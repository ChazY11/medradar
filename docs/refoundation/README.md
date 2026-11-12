# REFOUNDATION-001 — MedRadar Repository Audit

> **What this is:** a read-only architectural, scientific and data-governance audit of
> `github.com/ChazY11/medradar`, performed against live GitHub state on **2026-11-12**.
> **What this is not:** a refactor. No PR was merged, no branch deleted, no history
> rewritten, and `main` was not modified. The only write target is this directory,
> inside an isolated worktree (`audit/refoundation-001`, cut from `origin/main` @ `b2a14c0`).

**Start here →** [`EXECUTIVE_SUMMARY_ZH.md`](EXECUTIVE_SUMMARY_ZH.md) (Chinese, owner-facing).
**Facts first →** [`_FACTS.md`](_FACTS.md) (verified ground truth shared by every auditor).

---

## Deliverables

| # | Document | What it answers |
|---|---|---|
| 1 | [`EXECUTIVE_SUMMARY_ZH.md`](EXECUTIVE_SUMMARY_ZH.md) | 一页结论 + 六部分路线图（中文） |
| 2 | [`REPOSITORY_INVENTORY.md`](REPOSITORY_INVENTORY.md) | What exists, where, on which branch, with what tests |
| 3 | [`BRANCH_PR_AUDIT.md`](BRANCH_PR_AUDIT.md) | All 30 PRs / 34 branches, dispositions, merge order |
| 4 | [`ARCHITECTURE_AS_IS.md`](ARCHITECTURE_AS_IS.md) | The architecture `main` actually has |
| 5 | [`TECHNICAL_DEBT_REGISTER.md`](TECHNICAL_DEBT_REGISTER.md) | 40 ranked debt items + 9 duplicated infrastructures |
| 6 | [`RESEARCH_ASSET_REGISTER.md`](RESEARCH_ASSET_REGISTER.md) | 24 research assets, verdicts, frozen evidence, retractions |
| 7 | [`DATA_GOVERNANCE_AUDIT.md`](DATA_GOVERNANCE_AUDIT.md) | Licences, provenance, PII, do-not-merge list |
| 8 | [`ARCHITECTURE_TO_BE.md`](ARCHITECTURE_TO_BE.md) | The unified target architecture (10 design questions) |
| 9 | [`MIGRATION_PLAN.md`](MIGRATION_PLAN.md) | 6 reversible phases, 21.5 days, per-phase rollback |
| 10 | [`README_REDESIGN_PROPOSAL.md`](README_REDESIGN_PROPOSAL.md) | New front page, EN + ZH copy, visual system |
| 11 | [`AGENT_COLLABORATION_PROTOCOL.md`](AGENT_COLLABORATION_PROTOCOL.md) | How multiple agents stop re-fragmenting the repo |
| 12 | [`DECISION_REGISTER.md`](DECISION_REGISTER.md) | 19 decisions the owner must make |

## Evidence pack

Machine-readable and reproducible — everything above is derived from these:

| File | Content |
|---|---|
| `_evidence/repo_facts.json` | Repo, 30 PRs, branches, sizes, Pages, protection (regenerate: `collect_facts.py`) |
| `_evidence/ancestry.json` | Which unmerged stack each branch really contains |
| `_evidence/collisions.json` | Cross-branch touched-path collisions |
| `_evidence/blob_identity.json` | Byte-identical file groups (copy vs inheritance) |
| `_evidence/copy_volume.json` | Copy volume per branch pair |
| `_evidence/inventory/` | Inventory collectors + facts |
| `_evidence/arch/` | Architecture probes |
| `_evidence/research/` | 86 verbatim study extracts + frozen artifact hashes |
| `_evidence/data/` | 32,232 tree rows, 69-source register, 4,199-blob secret scan |
| `_evidence/comms/` | Extracted `origin/main` front-door blobs |

## Reproduce

```bash
cd <worktree>
python docs/refoundation/_evidence/collect_facts.py     # live GitHub + git facts
python docs/refoundation/_evidence/ancestry_matrix.py   # branch ancestry
python docs/refoundation/_evidence/collision_analysis.py
python docs/refoundation/_evidence/blob_identity.py
python -m pytest -q -p no:cacheprovider                 # 1,074 tests, exit 0
```

## Three findings that outrank everything else

1. **`main` is healthy but tiny relative to the project.** `main` = PRs #2–#11, 1,135 files,
   1,074 passing tests. PRs #12–#30 (+2,824,212 lines) are unmerged drafts; GitHub Pages
   shows `main` only. Any claim about "2.0 / Observatory / PHOENIX / ATLAS / HORIZON" is a
   claim about a draft branch.
2. **Three RED data-rights branches.** PR #29 commits 30 UN Comtrade paths (6,234,301 B)
   under an explicit no-redistribution clause; PR #27 commits a second Comtrade set; PR #26
   commits 22,622 non-open-access abstracts. No open research branch is merge-ready as-is.
3. **The research record is the real asset.** `research/RESULTS` R1–R124, five documented
   retractions to one confirmed decision rule, and a complete negative-result paper. It is
   currently invisible from the front page and unrepresented in the repo's identity.

## Boundary

- No network probes to data providers; no production data reads.
- No writes outside `docs/refoundation/` (verified: `git status` shows only that path).
- No merge, delete, force-push, rebase or history rewrite.
- Every non-obvious claim is labelled **FACT / INFERENCE / RECOMMENDATION / UNVERIFIED**.
