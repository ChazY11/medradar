# DECISION REGISTER — REFOUNDATION-001

> **Purpose:** everything in this file needs an explicit decision from the project owner.
> Nothing here has been executed. Each item states the options, the evidence, a
> recommendation, the risk of waiting, and whether it blocks other work.
>
> **Status:** draft v1 · 2026-11-12 · evidence base: `docs/refoundation/_FACTS.md`,
> `_evidence/`, and the six audit documents in this directory.
>
> **How to use:** mark one option per decision (`D-01 … D-19`) and set `STATUS`.
> Decisions marked **BLOCKING** stop the migration phases that depend on them.

**Legend:** `[FACT]` verified · `[INFERENCE]` reasoned from facts · `[RECOMMENDATION]` proposed.

---

## Decision index

| ID | Decision | Blocking | Recommendation |
|---|---|---|---|
| D-01 | What is MedRadar's public identity: research platform, intelligence product, or both? | YES | Science-first platform |
| D-02 | Does `main` become the product or the research spine first? | YES | Research spine first (Phase 2) |
| D-03 | Merge order for the #12–#14 product stack | YES | Merge #12 → #13 → #14 in one reviewed train |
| D-04 | Fate of the 19 draft research PRs | YES | Freeze as tagged research archive; merge only verdict-bearing docs |
| D-05 | Fate of PR #1 (conflicting, 154 behind) | no | Close as superseded |
| D-06 | Raw third-party data in git (UN Comtrade, etc.) | YES | Do not merge; quarantine + hash-only provenance |
| D-07 | Whether to rewrite history to purge restricted data | YES | No history rewrite; prevent forward-only |
| D-08 | Preservation of the 7 locally-unique PHOENIX commits (33 ahead / 16 behind twin) | YES | Push to a **new** `rescue/` branch + tag + bundle immediately |
| D-09 | Canonical evidence/identity/graph infrastructure | YES | main `tkg/` spine; ATLAS becomes an adapter |
| D-10 | Whether CONVERGENCE (#30) is a merge or a duplicate | no | Do not merge as-is; re-derive after D-09 |
| D-11 | Repository size strategy (data out of git) | no | Content-addressed `data/` + release assets |
| D-12 | Freeze policy for research artefacts | YES | Immutable tag + manifest + checksum |
| D-13 | Version and release numbering | no | Single generated version, `0.6.0` reset |
| D-14 | Branch protection and required checks | YES | Protect `main`, require CI + review |
| D-15 | Machine-readable project state as single source | YES | `PROJECT_STATE.yaml` + generated docs |
| D-16 | Keep or retire the trading / paper-trading framing | no | Demote to a labelled legacy demo |
| D-17 | Licence metadata and per-source data notices | no | MIT + SPDX + NOTICE/DATA_LICENSES.md |
| D-18 | Publication of the negative-result paper | no | Publish; it is a credibility asset |
| D-19 | Who owns the front page: PR #17 or the redesign? | YES | Land #17's facts first, then redesign as a second pass |

---

## D-01 — What is MedRadar's public identity?

**Question.** The repository currently describes itself three different ways at once.

**Evidence.**
- `[FACT]` GitHub repo description: *"An evidence-first research platform for observing and studying early signals in medical technology development."*
- `[FACT]` `README.md:3-6`: *"An open-source radar for FDA device & drug industry direction … what US majors are actually building next, not what they said in an earnings call."*
- `[FACT]` `README.md` front page is dominated by trading metrics: 281 signals, 400-step replay, 10/25/50 bps cost tiers, "Simulated book: in-sample, long-only, not investment advice".
- `[FACT]` `research/MISSION.md` and `research/LAYERS.md` define a science programme (Observe → Understand → Anticipate) that the README does not mention.
- `[INFERENCE]` A reader cannot tell whether this is a research project with a demo, or a product with a research appendix.

**Options.**

| Option | What it means | Cost |
|---|---|---|
| A. Research platform first, product as demo | README leads with the scientific question; product is a worked example | Rewrite README; keep product code |
| B. Intelligence product first, research as credibility | README leads with capabilities; research as evidence | Cheapest; but contradicts the stated mission |
| C. Two-track repository (product + science) | Separate READMEs / directories | Highest maintenance; risks further drift |

**Recommendation.** **A — science-first platform.** It matches the repo description, the mission docs, and the strongest asset in the repository (a rigorous negative-result paper). Option B would repeat the over-claiming failure the audit found.

**Consequence if undecided.** README redesign (A6) and architecture framing (A5) cannot be finalised; the project keeps presenting an identity it does not hold.

---

## D-02 — Does `main` become the product or the research spine first?

**Evidence.**
- `[FACT]` `main` = `b2a14c0`, PRs #2–#11 only. It is a working research/product hybrid with **1,074 passing offline tests** (measured 2026-11-12).
- `[FACT]` The unmerged product stack (#12–#14) is 3 layers deep and 71,846 added lines.
- `[FACT]` Seven branches carry the product stack by ancestry (#13, #14, #15, #16, #21, #22, phase4-base), so it is already load-bearing even though unmerged.
- `[INFERENCE]` Merging the product stack first would triple the surface area before the evidence contract exists; merging the research spine first gives the product a stable data contract to build on.

**Recommendation.** **Research spine first.** Land Phase 1 (governance) and Phase 2 (evidence contract + identity), then the product stack (#12–#14) on top of it. This is also lowest-risk: `main` stays green throughout.

---

## D-03 — Merge order for the #12–#14 product stack

**Evidence.**
- `[FACT]` #13 base = `feat/medradar-2.0-mvp`; #14 base = `feat/live-observatory-v1`; #15/#16 base = `feat/observatory-reliability-v1`.
- `[FACT]` All three are 0 commits behind their bases; no conflicts.
- `[FACT]` #14 adds systemd units, Windows one-shot tasks, single-writer lease, backups, 7-day validation — operational code that changes how the app runs.
- `[FACT]` GitHub Pages only reflects `main`; none of this is publicly visible.

**Options.**
| Option | Risk |
|---|---|
| A. Merge #12 → #13 → #14 as a reviewed train | Low conflict risk; needs one coherent review |
| B. Squash each into a single commit on main | Loses review granularity; contradicts preserved history |
| C. Park indefinitely | The 7 dependent branches stay unmergeable and drift |

**Recommendation.** **A**, after D-09/D-14, with one integration review covering the whole train and a `v0.6.0` tag at the end of #14.

---

## D-04 — Fate of the 19 draft research PRs

**Evidence.**
- `[FACT]` #15–#30 are drafts; several are explicitly "do not merge" in their titles (#15, #16, #20, #22, #24, #25, #26, #27).
- `[FACT]` Their scientific value is in **documents and frozen artefacts**, not in merging code into `main`.
- `[FACT]` #15/#16 are based on #14, so they cannot merge before the product stack anyway.
- `[INFERENCE]` Merging all research branches would add ~2.8M lines, much of it experiment output, to the shipped repository.

**Recommendation.** Treat them as a **tagged research archive**, not merge targets:
1. Preserve each branch head as an immutable tag (`archive/<study>-<sha>`).
2. Merge only the **verdict documents** (`docs/research/...`, `RESEARCH_ASSET_REGISTER` rows) into `main` via a single "research record" PR.
3. Keep code on branches until a study is re-homed onto the Phase-2 contract.

This preserves every result while keeping `main` reviewable.

---

## D-05 — Fate of PR #1

**Evidence.** `[FACT]` PR #1 is `OPEN`, not draft, `mergeable=CONFLICTING`, `mergeStateStatus=DIRTY`, **154 commits behind** main, 13 ahead. It is the oldest open PR and predates the entire research programme.

**Recommendation.** Close as **superseded** (not deleted): the useful part (frontier device radar) already exists on `main` as `medradar/frontier.py` and its tests. Record the decision in the PR. Do not force-push or rewrite it.

---

## D-06 — Raw third-party data in git

**Evidence.**
- `[FACT]` `research/horizon-001` (PR #29) commits **30 UN Comtrade paths totalling 6,234,301 B** (24 raw `*.json`, two derived `un_comtrade.jsonl`, and the derived `comtrade_usd` cell), plus `comtrade_license.html` and `terms_of_use.html`. The Usage Agreement §5 forbids copying, redistribution, publication and commercial exploitation without written permission. **RED.**
- `[FACT]` `research/data-expansion-001` (PR #27) commits a **second** Comtrade redistribution: 4 preview payloads, 255,265 B. **RED.**
- `[FACT]` `research/phoenix-003-early-evidence` (PR #26) commits Europe PMC abstracts, **22,622 of 36,644 (61.7%) non-open-access**, 29.0 MB compressed. **RED.**
- `[FACT]` Personal data: 3 raw UK Find-a-Tender OCDS packages on #29 carry **248 named buyers' work e-mails**; `s029` carries ≥417 author e-mails.
- `[FACT]` `PROVENANCE.json` records exact request URLs, bytes and sha256 — provenance is *excellent*; the concern is **redistribution**, not traceability.
- `[FACT]` HORIZON as a branch carries **1,826 blobs / ~101 MB**; `main` deliberately keeps `data/` and `out/` out of git.
- `[FACT]` Audit conclusion: **no open research branch is merge-ready as-is** — 3 RED (#29, #27, #26) and 4 AMBER-conditional (#16, #22, #21, #30).

**Recommendation.** **Do not merge any RED or AMBER-conditional branch.** Sequence: (a) seek written permission from UNSD **or** remove the 30 Comtrade paths + the 5-file derived cell + the 4 #27 previews; (b) strip `abstract` from #26 or filter to `is_open_access=true`; (c) drop `data/raw/` from #16; (d) keep structured job fields + `content_sha256` instead of verbatim employer copy on #21/#22; (e) adopt `licence_policy.json` + a CI `licence_gate.py` so the rule is executable. Because the branches are already public, removal limits future exposure but cannot un-publish. This is the single highest legal-risk item in the repository.

---

## D-07 — Rewrite history to purge restricted data?

**Evidence.** `[FACT]` The data lives only on unmerged branches, never on `main`. `[FACT]` The brief forbids history rewriting this round.

**Recommendation.** **No history rewrite.** Prevent forward-only (D-06). If a source licence ultimately forbids redistribution, the correct minimal action is to delete the *unmerged branch* after archiving hashes — not to rewrite `main`, which contains none of it. Any rewrite decision should be taken only with explicit legal input.

---

## D-08 — The unpushed PHOENIX commits

**Evidence.** `[FACT]` Local `research/phoenix-001-external-methods` (`c385553`) is **33 commits ahead and 16 behind** its remote twin (`bd2f839`); **7 commits are not on any remote**. The local branch forks from the **S-028 tip**, not from `main`. Three other branches also hold unpushed commits (`research/temporal-knowledge-graph` 2, `research/forecast-registry` 2, `phase3/registry-cycle` 1, `integration/audit-dryrun` 1). A fourth PR-less remote branch, `research/early-signal-ai-review`, is the sole home of the `full-history-v1` work.

**Correction.** The naive `git push origin research/phoenix-001-external-methods` **will be rejected**: the branch has diverged (33 ahead / 16 behind), so it is not a fast-forward.

**Recommendation.** **Rescue immediately, before any branch cleanup, onto a new branch — never onto the diverged twin:**
```
git branch rescue/phoenix-001-local c385553
git push -u origin rescue/phoenix-001-local
git tag -a rescue/phoenix-001-2026-11-12 c385553 -m "7 commits unique to local workstation"
git push origin rescue/phoenix-001-2026-11-12
git bundle create phoenix-local-2026-11-12.bundle c385553 --not --remotes
```
This is the only irreversible-loss risk found in the audit. It should be done first, independent of every other decision.

---

## D-09 — Canonical evidence / identity / graph infrastructure

**Evidence.**
- `[FACT]` `main` already has a bitemporal TKG (`medradar/tkg/`: `store.py`, `_time.py`, `query.py`, `export.py`, `adapter.py`, 31+ tests) and an immutable forecast registry (`medradar/forecast_registry.py`, 43 tests).
- `[FACT]` ATLAS (#28) adds a **second, independent** stack: `medradar/atlas/{store,evidence/schema,evidence/timeq,identity/resolver,identity/models,db/migrations,graph/build,graph/query,quality/checks}` — 31 files. Its blobs differ from `tkg/`; it is a parallel design, not a copy.
- `[FACT]` `medradar/observatory/ledger.py` is a **third** observation store (on 6 branches via #14 ancestry).
- `[INFERENCE]` Three stores with three schemas is the root of the "cannot join sources" and "no independent confirmation" problems the research programme already documents.

**Recommendation.** **`main`'s `tkg/` + `forecast_registry.py` win.** ATLAS's genuinely new parts (deterministic identity resolution, quality checks, licence tagging) are absorbed as modules on the Phase-2 contract; its duplicate store/graph is retired behind an adapter. This must be decided before #28/#30 are merged.

---

## D-10 — Is CONVERGENCE (#30) a merge or a duplicate?

**Evidence.** `[FACT]` 651 of 813 added files (80.1%) in `integration/convergence-001` are byte-identical to `research/horizon-001`, but horizon is **not** an ancestor — CONVERGENCE copied the tree. ATLAS **is** an ancestor.

**Recommendation.** Do **not** merge #30 as-is. After D-09, re-derive the integration from the canonical modules; treat #29+#30 as one body of work, not two PRs.

---

## D-11 — Repository size strategy

**Evidence.** `[FACT]` main is ~29 MB of blobs (experiments 15 MB, docs 6.4 MB, config 2.2 MB). Branches add ~100+ MB. `[FACT]` `docs/dashboard.html` alone is 3.35 MB; Pages serves it.

**Recommendation.** Keep `main` lean: generated aggregates in `docs/`, raw data out of git, `data/` content-addressed and regenerable, release assets for large snapshots. Do not add Git LFS for data that `main` does not need.

---

## D-12 — Freeze policy for research artefacts

**Evidence.** `[FACT]` `research/STATE.json` and `research/AUDIT.json` already act as a de-facto state ledger; `DECISIONS.md` D-005 states frozen artefacts are immutable inputs. `[FACT]` Horizon ships `*.sha256` sidecars (24 of them). `[INFERENCE]` Freeze is a *convention* today, not an *enforced mechanism*.

**Recommendation.** Enforce it: per-study `FREEZE.json` (protocol hash, data hashes, code commit, results hash), an immutable git tag, and a CI check that fails if a frozen path changes without a new freeze record. Adopt as part of A6's protocol.

---

## D-13 — Version and release numbering

**Evidence.** `[FACT]` `pyproject.toml` = `0.5.0`; README says "stable core through v0.2.2" / "v0.3.0 consolidates"; ATTRIBUTION says "v0.4.0"; test counts quoted as 625 / 678 / 795 / 1,074 depending on the file. `[FACT]` No releases exist on GitHub.

**Recommendation.** One generated version string; cut `0.6.0` at the end of Phase 2; publish GitHub Releases for `main` only; never hand-write test counts.

---

## D-14 — Branch protection and required checks

**Evidence.** `[FACT]` `GET /repos/.../branches/main/protection` → **404 "Branch not protected"**. `[FACT]` `ci.yml` exists and runs on PRs and main (3.10–3.12, offline suite, wheel smoke, Windows install, offline demo); recent main runs are green. `[FACT]` `.github/` has a PR template and 3 issue templates but **no `CODEOWNERS`**.

**Recommendation.** Protect `main`: require PR, require `ci` green, require linear history or squash-only, disallow force-push. Add `CODEOWNERS` for `medradar/`, `research/`, `docs/refoundation/`. This is cheap and prevents recurrence.

---

## D-15 — Machine-readable project state as single source of truth

**Evidence.** `[FACT]` State is currently spread across `research/STATE.json`, `research/AUDIT.json`, `research/FINAL_AUDIT.json`, `research/BACKLOG.yaml`, `research/DECISIONS.md`, `CHANGELOG.md`, `ROADMAP.md`, README tables, and `docs/metrics.json` — several of which already disagree. `[INFERENCE]` This is the mechanism that lets multiple agents maintain contradictory truths.

**Recommendation.** Adopt `PROJECT_STATE.yaml` (+ per-study manifests) as the only hand-edited state; generate README status tables, research index, and changelog fragments from it in CI. This is the core of A6.

---

## D-16 — Trading / paper-trading framing

**Evidence.** `[FACT]` README features signals, a simulated book, cost tiers, and an event study; `research/DECISIONS.md` and `MISSION.md` do not mention trading. `[FACT]` The negative paper explicitly reframes the programme as information-limited science.

**Recommendation.** Demote to a clearly labelled **legacy demo**: keep the code, remove it from the headline, state "not investment advice, in-sample, not a validated strategy". This is a positioning decision with reputational impact.

---

## D-17 — Licence metadata and per-source notices

**Evidence.** `[FACT]` `LICENSE` = MIT; GitHub reports `other`; `docs/ATTRIBUTION.md` covers authorship but not data licences; no `NOTICE`/`DATA_LICENSES.md`.

**Recommendation.** Add SPDX header, fix GitHub licence detection, add `DATA_LICENSES.md` with one row per source, and a `NOTICE` for third-party data. Needed before any data-bearing branch is merged.

---

## D-18 — Publish the negative-result paper?

**Evidence.** `[FACT]` `papers/PAPER_NEGATIVE_v1.md` is a complete, pre-registered negative-result paper: 55,592 trials, 0 on device tracks; 20,976 8-K, 1,360 with company key; 3 eligible pairs vs floor of 10; 1 qualifying onset in 16 cells; 0 in the primary window; conclusion "the binding constraint is information, not modelling".

**Recommendation.** **Publish it** (arXiv/preprint or a repo-hosted paper page) after an independent read. It is the strongest credibility asset MedRadar has, and it directly serves the stated scientific mission.

---

## D-19 — Who owns the front page?

**Evidence.** `[FACT]` PR #17 `maintenance/repository-consolidation` already rewrites `README.md` (+689/−443) and adds `docs/PROJECT_STATUS.md`, `docs/REPOSITORY_AUDIT.md`, `docs/DATA_ASSET_REGISTER.md`; its positioning is already research-first. `[FACT]` The README redesign proposal (A6) also rewrites the front page. `[INFERENCE]` Shipping both produces a second round of duplicate documentation — the exact failure the audit is trying to end.

**Options.** (a) Land #17 first, then apply the redesign as a second pass; (b) supersede #17's docs with the redesign; (c) merge the two into one PR.

**Recommendation.** **(a).** #17 contains measured facts (audit, data register) that the redesign needs as input; the redesign contains the provenance ledger, EN/ZH parity and CI gates that #17 lacks. Sequence them, do not parallelise them. Assign one owner for `README.md` at all times.

---

## Decision dependencies

```
D-08 (rescue commits)  ── must happen first, no dependency
D-01 (identity) ──► D-16 (trading framing), README redesign
D-09 (canonical infra) ──► D-03 (product stack), D-10 (convergence)
D-06/D-07/D-17 (data rights) ──► any merge of #27/#29/#30
D-14/D-15 (governance) ──► every later phase
D-12 (freeze) ──► D-04 (research archive)
```

## Sign-off

| Decision | Chosen option | Date | Owner |
|---|---|---|---|
| D-01 | | | |
| … | | | |
