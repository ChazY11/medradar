# Agent Collaboration & Repository Governance Protocol — MedRadar

**Deliverable:** A6 · REFOUNDATION-001 · owner `comms-lead`
**Status:** proposal. Nothing here is deployed; every mechanism below is a **recommendation** with a
concrete implementation path, an owner, and a CI gate you can actually write.
**Snapshot:** 2026-11-12 (Asia/Shanghai), read from `origin/main` = `b2a14c0` (PR #11 merge, 2026-11-02).

---

## 0. Scope / Method / Evidence base / Limits

**Scope.** Ten enforceable mechanisms that stop parallel AI agents (and humans working with them) from
(a) writing the same thing twice, (b) letting documentation drift out of agreement with code, and
(c) fragmenting the architecture into mutually incompatible lane stacks. Plus copy-pasteable
templates and an exact CI gate list bound to the workflows that exist on `main` today.

**Out of scope.** Rewriting history, deleting branches, merging PRs, choosing an architecture (that is
`ARCHITECTURE_TO_BE`), audit of research *quality* (that is `research-registrar`), and evaluation of
individual agents or sessions.

**Method.** Each mechanism is derived from a *specific observed failure* in this repository, cited to a
path/ref. Where a mechanism would cost more than the failure it prevents, that is stated and it is not
recommended. Every proposed CI gate names the file, job name, command, and blocking behaviour so the
next agent can implement it without re-deriving anything.

**Evidence base.** `docs/refoundation/_FACTS.md`; `_evidence/repo_facts.json`; the four workflows on
`main` (`.github/workflows/{ci,forecast-cycle,live,weekly}.yml` — **[FACT]** these are the only four;
`observatory.yml` does **not** exist on `main`, contrary to `_FACTS.md` §7 and the task brief, see
G-10); `.github/pull_request_template.md`; `.github/ISSUE_TEMPLATE/*`; `docs/ATTRIBUTION.md`;
`docs/ROADMAP.md`; `research/DECISIONS.md`; `research/STATE.json`; PR #17's draft docs.

**Labels.** **[FACT]** read from a cited file/ref. **[INFERENCE]** reasoned from facts, chain shown.
**[RECOMMENDATION]** a proposed action. **[UNVERIFIED]** not checkable here, reason given.

**Limits.**
1. GitHub-side settings (branch protection, required checks, label definitions, CODEOWNERS
   enforcement, Actions permissions) are **not** visible in git objects. Every gate below is written
   repo-side (a script + a workflow job) so it works even if branch protection is never configured —
   but a non-blocking gate is advisory only **[INFERENCE]** and I cannot verify current protection.
2. **[UNVERIFIED]** Whether `main`'s CI is currently green. The design deliberately treats "CI green"
   as a *claim to be verified by CI itself* rather than a statement in a doc.
3. I could not test any of the proposed scripts. Command names are proposals, not existing tools.
4. Effort estimates are **[INFERENCE]**, order-of-magnitude only.

---

## 1. The failure modes we actually have

This is not a hypothetical. Each row is a live defect in this repository at `b2a14c0`.

| # | Failure | Evidence | Consequence |
|---|---|---|---|
| **E1** | **Seven different test counts** committed on `main` | 274 (`docs/GOOD_FIRST_ISSUES.md:76`, `CHANGELOG.md:322`), 578 (`docs/INTEGRATION_2026-11-02.md:94`), 625 (`docs/ATTRIBUTION.md:55`), 636 (`docs/TKG_INTEGRATION.md:10`), 678 (`README.md:42`), 679 (`research/DECISIONS.md:14`), 795 (`research/STATE.json:35`) — vs the measured **1,074** on `b2a14c0` **[FACT]** | Every doc that names a test count is wrong, including the front page |
| **E2** | **Three competing project positionings**, all on `main` | `README.md:6-11` (FDA weekly brief), repo description (evidence-first platform), `research/STATE.json:6-7` ("Global MedTech Intelligence & Foresight") | No single answer to "what is this"; the front page cannot be written |
| **E3** | **Decision record asserts a false state of `main`** | `research/DECISIONS.md` D-001: "`main` is frozen at `7a639f7` (v0.2.2)" — `main` is **154 commits ahead** of `7a639f7` **[FACT, `git rev-list --count`]** | A reader following the ADR builds on a stale reference point |
| **E4** | **Superseded result still published** | `ROADMAP.md:44-49` disowns the 2,384-case study; `docs/report_zh.md:601-619` still ships it unlabelled, and Pages serves it | Public claim contradicts internal ruling |
| **E5** | **A `main` workflow was claimed that exists only on branches** | The task brief and the first snapshot of `_FACTS.md` §7 listed `observatory.yml`; `git ls-tree origin/main -- .github/workflows` returns only `ci, forecast-cycle, live, weekly` **[FACT]**; `observatory.yml` exists on `feat/live-observatory-v1`, `feat/observatory-reliability-v1`, `integration/phase4-base`. The fact base was corrected on 2026-11-12 (`_FACTS.md:240`), but **the audit itself** made the error | Even the audit's own ground truth drifted once; gates must verify, not remember |
| **E6** | **19 draft PRs blocking product PRs, 3-deep stacks** | `_FACTS.md` §4: `#12 → #13 → #14 → {#15,#16}`; research studies physically depend on unmerged product code; `integration/phase4-base` is a **base branch with no PR** | Merge order is invisible; reviewers cannot reason about readiness |
| **E7** | **Duplicate work already happened at the doc layer** | PR #17 (`maintenance/repository-consolidation`, draft) rewrites both READMEs (689 and 443 changed lines respectively) and adds `docs/PROJECT_STATUS.md`, `docs/REPOSITORY_AUDIT.md`, `docs/DATA_ASSET_REGISTER.md` while the A6 proposal you are reading proposes a README redesign | Two front pages in flight — exactly the parallel-agent failure this protocol exists to prevent |
| **E8** | **Hand-typed numbers drift from generated ones** | `docs/DATA.md:36` says 1.3 GiB (generated); `README.md:29,47`, `README.zh-CN.md:22`, `docs/METHODS.md:206` say 1.2 GiB | The generated file is right and nobody propagates it |
| **E9** | **PR template cannot express the work** | `.github/pull_request_template.md:7-12` offers bugfix / data correction / new metric / docs. No research-question field, no branch-stack field, no freeze field, no "does this touch `main` state" field | Stacked research PRs are indistinguishable from a typo fix |
| **E10** | **No ownership map** | 87 files in `medradar/`, 34 branches, 8 agent roles documented in `docs/ATTRIBUTION.md:32-42` — but nothing maps an area to an owner or a write scope | Two agents edit `medradar/analyze.py` in parallel and find out at merge time |

**[INFERENCE]** E1–E10 share one root cause: **state is written by hand, in prose, many times, and
never verified.** Every mechanism below is a special case of one rule — *state is generated once and
checked by CI*.

---

## 2. Mechanism index

| ID | Mechanism | Kills | Blocking gate |
|---|---|---|---|
| **M1** | Machine-readable single source of truth (`PROJECT_STATE.yaml`) + generated docs | E1, E2, E3, E8 | `g1-state-fresh` |
| **M2** | Module ownership map + CODEOWNERS | E10 | `g6-ownership` |
| **M3** | PR naming, classification, draft policy, stack declaration | E6, E9 | `g7-pr-contract` |
| **M4** | Experiment freeze + immutable versioning | E4 | `g4-freeze-verify` |
| **M5** | Data asset registry | E8 (data half) | `g5-assets` |
| **M6** | README / research-status sync, generated not maintained | E1, E2, E3, E4, E8 | `g2-readme-sync`, `g3-facts-ledger` |
| **M7** | CI quality gates (the catalogue) | all | all |
| **M8** | Architecture change proposals (ADR/RFC) | E3, E6 | `g8-adr-index` |
| **M9** | Agent parallel-development + handoff protocol | E7, E10 | `g9-lease` |
| **M10** | Periodic technical-debt audit cadence | E4, E6, E7 | scheduled report |
| **M11** | Definition of Done (research vs product) | E6, E9 | part of `g7-pr-contract` |

---

## 3. M1 — Single source of truth

**Problem.** E1, E2, E3, E8. Every document is authoritative because every document is hand-written.

**Mechanism.** One file at repo root: `PROJECT_STATE.yaml`. Everything a human or agent needs to know
about "what is this project right now" is a field in it. Every document that restates those facts is
**generated** from it and carries a delimiter so CI can prove the generation is current.

```yaml
# PROJECT_STATE.yaml — single source of truth. Edit this, run `make state`, commit both.
# Any file containing "BEGIN GENERATED" is derived; hand-editing it is a CI failure.
schema: medradar.project_state.v1
updated_at: "2026-11-12T00:00:00+08:00"   # ISO-8601, Asia/Shanghai

identity:
  name: MedRadar
  one_line: >-
    An evidence-first research instrument asking whether publicly observable evidence gives
    reliable early warning of meaningful change in medical-technology development.
  status: research_instrument          # research_instrument | product | archived
  core_question: >-
    Can publicly observable evidence provide reliable early signals of meaningful changes in
    medical technology development?
  licence: MIT
  repository: https://github.com/ChazY11/medradar
  site: https://chazy11.github.io/medradar/

release:
  version: "0.5.0"                     # MUST equal pyproject.toml; g1 asserts equality
  version_source: pyproject.toml
  main_head: "b2a14c0"                 # g1 asserts equality with `git rev-parse --short origin/main`
  main_head_date: "2026-11-02"

verification:
  test_command: "python -m pytest -q"   # the single canonical command
  test_count: 1074                      # MUST be the output of test_command; g1 re-runs or refuses
  test_count_measured_at: "2026-11-12"
  test_count_ref: "b2a14c0"
  ci_workflow: ".github/workflows/ci.yml"
  ci_status: unverified                 # verified_green | verified_red | unverified

capabilities:
  # Bucket A: on main and exercised by the offline suite.
  on_main_tested: [ingest_openfda, event_store, entity_resolution, track_heat,
                   product_families, replay, event_study, paper_sim, tkg_bitemporal,
                   forecast_registry, reverse_rd_evaluation, research_agent, offline_demo,
                   interactive_dashboard]
  # Bucket B: on main, measurably unreliable. Must be named experimental in docs.
  on_main_experimental: [adcom_collector_zero_rows, forecast_cycle_never_dispatched,
                         live_lane_best_effort]
  # Bucket C: on main but superseded. Must carry a superseded banner wherever shown.
  on_main_superseded: [corpus_study_2384_cases]
  # Bucket D: branch-only. NEVER described as a main capability.
  branch_only:
    - {name: medradar_2_0_mvp,        pr: 12, branch: feat/medradar-2.0-mvp}
    - {name: live_observatory_v1,     pr: 13, branch: feat/live-observatory-v1}
    - {name: observatory_reliability, pr: 14, branch: feat/observatory-reliability-v1}
    - {name: s028_temporal_graph,     pr: 15, branch: research/s028-temporal-graph-early-signal}
    - {name: s029_evidence_relations, pr: 16, branch: research/s029-evidence-based-relations}
    - {name: repository_consolidation,pr: 17, branch: maintenance/repository-consolidation}
    - {name: local_llm_foundation,    pr: 19, branch: research/local-llm-foundation}
    - {name: overnight_qlora_s030,    pr: 20, branch: research/overnight-qlora-s030}
    - {name: innovation_observatory,  pr: 21, branch: research/innovation-signals-observatory}
    - {name: s031_hiring,             pr: 22, branch: research/s031-hiring-capability-study}
    - {name: phoenix_001,             pr: 23, branch: research/phoenix-001-external-methods}
    - {name: phoenix_002,             pr: 25, branch: research/phoenix-002-h8-validation}
    - {name: phoenix_003,             pr: 26, branch: research/phoenix-003-early-evidence}
    - {name: data_expansion_001,      pr: 27, branch: research/data-expansion-001}
    - {name: atlas_001,               pr: 28, branch: foundation/atlas-001}
    - {name: horizon_001,             pr: 29, branch: research/horizon-001}
    - {name: convergence_001,         pr: 30, branch: integration/convergence-001}

gates:
  pages_source: legacy_main_docs        # legacy_main_docs | github_actions_artifact
  pages_last_build_commit: "b2a14c0"
  fail_on_hand_edited_generated: true
  fail_on_stale_facts: true
  draft_max_age_days: 30

experiments:
  frozen: [reverse_rd_v1, reverse_rd_v2, early_signal_5firms]
  active: []

open_questions_for_owner: []
```

**Generated artefacts (each gets a header comment naming its source):**

| Output | Generator | Delimiters |
|---|---|---|
| `README.md` status table + badge block | `scripts/gen_readme.py` | `<!-- BEGIN GENERATED: status -->` … `<!-- END GENERATED: status -->` |
| `README.zh-CN.md` same block | same generator, same data | identical delimiter names |
| `docs/PROJECT_STATUS.md` | `scripts/gen_status_doc.py` | whole file generated |
| `docs/DATA_ASSET_REGISTER.md` | `scripts/gen_assets_doc.py` | whole file generated |
| `.github/workflows/ci.yml` badge inputs | `scripts/gen_badges.py` | n/a (writes `badges.json`) |

**Enforcement — `g1-state-fresh`:**

```yaml
g1-state-fresh:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with: {python-version: "3.12"}
    - run: pip install pyyaml
    - name: version in pyproject == PROJECT_STATE.release.version
      run: python scripts/check_state.py --assert-version
    - name: main_head matches the actual HEAD of the checked-out ref
      run: python scripts/check_state.py --assert-head
    - name: test_count matches the real pytest collection
      run: |
        pip install -e .
        python -m pytest --collect-only -q | tail -1 > collected.txt
        python scripts/check_state.py --assert-test-count collected.txt
    - name: generated files are not hand-edited
      run: |
        python scripts/gen_state.py --all
        git diff --exit-code -- README.md README.zh-CN.md docs/PROJECT_STATUS.md docs/DATA_ASSET_REGISTER.md
```

**Tie to findings.** Kills E1 (one count, machine-checked), E2 (one `one_line` + `core_question`; the
a11y of every other doc hangs off it), E3 (state is generated from HEAD, so it cannot claim a stale
commit), E8 (numbers come from artefacts).

**Cost.** **[INFERENCE]** ~1 engineer-day for the generator + checker; every subsequent doc edit gets
cheaper. The one-off backfill of `PROJECT_STATE.yaml` is ~2 hours.

---

## 4. M2 — Module ownership map

**Problem.** E10. `docs/ATTRIBUTION.md:32-42` names eight agent roles, but nothing maps a directory to
a role, a reviewer, or a write scope. With 34 branches and 87 modules in `medradar/`, two agents
editing `analyze.py` is a merge conflict the protocol should have prevented.

**Mechanism.** `docs/state/OWNERS.yaml`, generated into `CODEOWNERS`. An area is a directory plus a
test directory; an owner is a GitHub handle or an agent role name; `write_scope` is the advisory lock.

```yaml
# docs/state/OWNERS.yaml — generated into .github/CODEOWNERS by scripts/gen_owners.py
schema: medradar.owners.v1
areas:
  - id: ingest
    paths: ["medradar/collect_*.py", "medradar/http.py", "medradar/adcom.py", "medradar/frontier.py"]
    tests: ["tests/test_collect*.py", "tests/test_http*.py"]
    owner: ingest-owner
    reviewers: [lead]
  - id: store
    paths: ["medradar/db.py", "medradar/schema*", "docs/SCHEMA.md"]
    tests: ["tests/test_db*.py"]
    owner: store-owner
    reviewers: [lead]
  - id: resolve
    paths: ["medradar/config.py", "config/companies_*.json", "config/tracks_*.json",
            "config/product_code_tracks.json"]
    tests: ["tests/test_config*.py"]
    owner: data-curation-owner
    reviewers: [lead]
  - id: analyse
    paths: ["medradar/analyze.py", "medradar/stats.py", "medradar/stats_cmd.py", "docs/METHODS.md"]
    tests: ["tests/test_analy*.py", "tests/test_stats*.py"]
    owner: metrics-owner
    reviewers: [lead]
  - id: products
    paths: ["medradar/products.py", "medradar/families.py", "config/product_catalog_zh.json"]
    owner: product-owner
  - id: simulation
    paths: ["medradar/paper.py", "medradar/eventstudy.py", "medradar/prices.py", "medradar/replay.py"]
    owner: quant-owner
    reviewers: [lead]
    notes: "in-sample only; any headline number from this area needs the 4 qualifiers"
  - id: research-foundation
    paths: ["medradar/tkg/", "medradar/forecast_registry.py",
            "medradar/intelligence/forecasting/", "medradar/intelligence/graph_context.py"]
    tests: ["tests/test_tkg*.py", "tests/test_forecast*.py"]
    owner: foundation-owner
    reviewers: [lead, research-registrar]
  - id: research-lane
    paths: ["medradar/intelligence/", "experiments/", "research/"]
    tests: ["tests/test_intelligence*.py"]
    owner: research-owner
    reviewers: [research-registrar]
  - id: agent
    paths: ["medradar/research_agent.py"]
    owner: research-owner
    reviewers: [lead]
  - id: output
    paths: ["medradar/report.py", "medradar/dashboard*", "docs/index.html", "docs/dashboard.html",
            "docs/preview.png"]
    owner: comms-owner
    reviewers: [lead]
  - id: docs
    paths: ["README.md", "README.zh-CN.md", "docs/**/*.md", "ROADMAP.md", "CONTRIBUTING.md"]
    owner: comms-owner
  - id: ci
    paths: [".github/**", "scripts/**", "pyproject.toml", "MANIFEST.in"]
    owner: infra-owner
    reviewers: [lead]
  - id: state
    paths: ["PROJECT_STATE.yaml", "docs/state/**"]
    owner: lead
    notes: "single-source-of-truth files; only lead edits, everyone regenerates"
```

**Enforcement — `g6-ownership`:**

```yaml
g6-ownership:
  if: github.event_name == 'pull_request'
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - run: pip install pyyaml
    - name: every changed path has an owner
      run: python scripts/check_ownership.py --diff-base "origin/${{ github.base_ref }}"
    - name: a PR may touch at most one area unless labelled area:multi
      env: {LABELS: "${{ join(github.event.pull_request.labels.*.name, ',') }}"}
      run: python scripts/check_ownership.py --max-areas 1 --labels "$LABELS"
    - name: CODEOWNERS is generated, not hand-edited
      run: |
        python scripts/gen_owners.py
        git diff --exit-code -- .github/CODEOWNERS
```

**Tie to findings.** E10; also the reason E7 happened — two agents both "owned" the README.

**Note on non-negotiable limits.** CODEOWNERS only blocks if branch protection requires code-owner
review **[UNVERIFIED whether enabled]**. So the script check is the real gate; CODEOWNERS is the
human nicety.

---

## 5. M3 — PR naming, classification, draft policy

**Problem.** E6, E9. Twenty open PRs, nineteen drafts, stacking three deep, with a template that
cannot express any of it. `integration/phase4-base` is a review target with no PR at all.

**Mechanism A — title grammar.** `type(area): subject`

* `type` ∈ `feat | fix | research | docs | data | refactor | infra | chore`
* `area` ∈ the `OWNERS.yaml` area IDs (`ingest`, `store`, `resolve`, `analyse`, `products`,
  `simulation`, `research-foundation`, `research-lane`, `agent`, `output`, `docs`, `ci`, `state`)
* subject: imperative, ≤ 72 chars, no trailing period, no emoji, no agent name

Examples that would have caught this repo's history: `research(research-lane): S-028 temporal graph
early-signal study (draft)`, `fix(store): bitemporal as-of query returns later knowledge time`.

**Mechanism B — required labels.**

| Label | Values | Required | Meaning |
|---|---|---|---|
| `area:*` | one of the 13 areas | yes | routing |
| `type:*` | mirrors title type | yes | classification |
| `status:*` | `draft` \| `ready` \| `blocked` \| `frozen` | yes | `draft` = not for merge |
| `evidence:*` | `frozen` \| `none` | yes for `type:research` | a frozen manifest exists |
| `affects:*` | `main-state` \| `docs` \| `data` \| `none` | yes | `main-state` forces `g1` |
| `stack:depth-N` | `1`..`4` | when PR base ≠ `main` | declares stack position |
| `blocked-by:#N` | PR numbers | when `status:blocked` | explicit dependency |

**Mechanism C — draft policy (the important one).**

1. **A PR targeting anything other than `main` must be `status:draft`.** Stacked PRs are drafts by
   definition until their base merges. **[FACT-based rationale]** `#13` targets `feat/medradar-2.0-mvp`,
   `#15/#16` target `feat/observatory-reliability-v1` (`_FACTS.md` §4) — these can never be "ready"
   while the base is unmerged, yet nothing in the repo says so.
2. **`status:ready` requires:** base is `main`, CI green, no `stack:depth-*`, and either no
   `type:research` or `evidence:frozen`.
3. **`research/*` PRs never get `status:ready` without a frozen manifest** (M4).
4. **Every base branch must have a PR or be deleted.** Kills `integration/phase4-base` (39 commits
   ahead of `main`, invisible to reviewers — `_FACTS.md` §4).
5. **Draft age > `draft_max_age_days` (30) → monthly report line item**, not an automatic close
   (closing an agent's 690k-line branch unilaterally would destroy work; the report is the pressure).

**Enforcement — `g7-pr-contract`:**

```yaml
g7-pr-contract:
  if: github.event_name == 'pull_request'
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
      with: {fetch-depth: 0}
    - run: pip install pyyaml
    - name: title grammar
      env: {TITLE: "${{ github.event.pull_request.title }}"}
      run: python scripts/check_pr.py --title "$TITLE"
    - name: labels + draft policy + base-branch rule
      env:
        LABELS:  "${{ join(github.event.pull_request.labels.*.name, ',') }}"
        BASE:    "${{ github.base_ref }}"
        IS_DRAFT:"${{ github.event.pull_request.draft }}"
      run: python scripts/check_pr.py --labels "$LABELS" --base "$BASE" --is-draft "$IS_DRAFT"
    - name: stacked PRs must declare depth and blocker
      run: python scripts/check_pr.py --require-stack-label-if-base-not-main
    - name: research PRs must reference a frozen manifest digest
      run: python scripts/check_pr.py --require-manifest-on-research
```

---

## 6. M4 — Experiment freeze and versioning

**Problem.** E4. A superseded result is still published because there is no machine-visible statement
of "this result is frozen, at this commit, with these hashes, and its verdict is final".

**Mechanism.** Every study is a directory `experiments/<study_id>/` containing `MANIFEST.yaml`, and
every frozen study gets an annotated, immutable tag `freeze/<study_id>/v<N>` on the commit that added
the manifest.

```yaml
# experiments/<study_id>/MANIFEST.yaml
schema: medradar.experiment_manifest.v1
study_id: reverse_rd_v2
version: 2
title: "Pure-R&D baselines: purged multi-window continuation + dormant→active entry"
status: frozen                      # proposed | running | frozen | superseded
supersedes: reverse_rd_v1
superseded_by: null

question: >-
  Can public regulatory + financial + publication evidence forecast 12-month R&D/regulatory
  milestones better than a per-pair historical base rate?
hypothesis: >-
  Added sources improve ranking (PR-AUC) over the R&D-only baseline at a purge-safe multi-window
  origin set.
preregistered_at: "2026-11-02"
protocol_doc: docs/REVERSE_RD.md
adr: research/DECISIONS.md#d-0xx

code:
  commit: "<40-hex sha of the commit adding this manifest>"
  entrypoints:
    - experiments/reverse_rd_v2/run_v2.py
    - experiments/reverse_rd_v2/run_ablation.py
    - experiments/reverse_rd_v2/merge_ablation.py

data:
  dataset_ids: [fda_events_2015_2026, sec_facts_32co, procurement_2016_2026, price_daily_local]
  row_counts: {continuation: 6701, entry: 41003}
  origins: {continuation: 25, entry: 24}
  holdouts: ["2025-04-01", "2025-07-01", "2025-10-01"]
  point_in_time: true
  purge_window_months: 12
  known_limits:
    - "procurement snapshot is not point-in-time usable → excluded from gain claims"
    - "patents not evaluated (USPTO ODP requires a key)"
    - "entry target is left-censored"

environment:
  python: "3.12"
  dependencies: ["stdlib"]          # core is stdlib-only; extras listed explicitly
  seeds: [0, 1, 2, 3, 4]
  determinism: "fixed bootstrap seed; identical rerun hash asserted"

outputs:                            # g4 recomputes every sha256; mismatch = failure
  - path: experiments/reverse_rd_v2/ablation_metrics.json
    sha256: "<64 hex>"
  - path: experiments/reverse_rd_v2/holdout_metrics.json
    sha256: "<64 hex>"

verdict:
  headline: negative                # positive | negative | mixed | inconclusive
  claim_allowed: >-
    No added source produces a statistically detectable ranking gain on the continuation target;
    the model is statistically indistinguishable from a per-pair base rate.
  claim_denied: >-
    That MedRadar can forecast medical-technology R&D direction; that added data improves ranking.
  numbers:                          # the ONLY numbers any doc may quote from this study
    - {id: N-14, value: "PR-AUC 0.7935 (all) vs 0.7922 (+financials)", holdout: "2025-10-01"}
    - {id: N-15, value: "marginal Δ PR-AUC: fin −0.0013, mkt −0.0015, pub −0.0001, all −0.0068"}
    - {id: N-16, value: "AP 0.7935 vs base rate 0.7913, Δ +0.0022, CI [−0.032,+0.037]"}

freeze:
  frozen_at: "2026-11-02T00:00:00Z"
  frozen_by: research-owner
  tag: freeze/reverse_rd_v2/v2
  immutability: "tag is annotated and protected; manifest edits require a new version"
```

**Rules.**

1. A frozen manifest is **immutable**. Any change requires `version: n+1` and a new tag; the old file
   stays on disk with `superseded_by: <id>/v{n+1}`.
2. Only numbers listed under `verdict.numbers` may appear in README, docs, or slides — this is what
   `g3-facts-ledger` checks against.
3. `verdict.claim_denied` is mandatory: it is the sentence that prevents the next agent from
   overclaiming.
4. A negative verdict is a **successful** study. `headline: negative` does not block publication.

**Enforcement — `g4-freeze-verify`:**

```yaml
g4-freeze-verify:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
      with: {fetch-depth: 0}
    - run: pip install pyyaml
    - name: every experiments/*/ has a valid manifest
      run: python scripts/check_freeze.py --require-manifest
    - name: every output sha256 matches the committed file
      run: python scripts/check_freeze.py --verify-hashes
    - name: frozen studies carry an immutable tag pointing at the manifest commit
      run: |
        for m in experiments/*/MANIFEST.yaml; do
          python scripts/check_freeze.py --assert-tag "$m"
        done
    - name: superseded studies are linked forward, never orphaned
      run: python scripts/check_freeze.py --assert-supersession-chain
```

**[RECOMMENDATION] Also enforce at push time**, not just PR time: a pre-push hook or a `freeze-guard`
job that refuses to modify a path listed under any frozen manifest's `outputs`.

---

## 7. M5 — Data asset registry

**Problem.** E8 (data half). The 1.3 GiB SQLite (`docs/DATA.md:36`: 1,368,469,504 B) is not committed;
the raw HTTP cache is not committed; procurement's snapshot is "not point-in-time usable"
(`README.md:329`); 657 files / 15.05 MiB sit under `experiments/` with no registry. Nobody can answer
"what data do we have, where did it come from, is it allowed to be used, and is it point-in-time?"

**Mechanism.** `docs/state/DATA_ASSETS.yaml` → generated `docs/DATA_ASSET_REGISTER.md`.

```yaml
schema: medradar.data_assets.v1
assets:
  - asset_id: fda_events_2015_2026
    kind: derived_table               # source | derived_table | snapshot | raw_cache | external
    committed: false
    path_in_repo: null
    regenerated_by: "medradar.intelligence.pipeline collect --source fda --months 120"
    size_bytes: 1368469504            # docs/DATA.md:36
    sha256: null                      # uncommitted → unhashed; state it
    provenance:
      publisher: openFDA
      urls: ["https://api.fda.gov/device/510k.json", "https://api.fda.gov/device/pma.json"]
      licence: "public domain (US government work)"
      fetched_at: "2026-10-30"
      fetched_by: "weekly-radar workflow"
    point_in_time: partial            # yes | no | partial
    pit_notes: "510(k)/PMA rows have no public publication timestamp → timestamp_quality=unknown;
                they enter counts but never return studies (docs/METHODS.md:30-32)"
    retention: "regenerate on demand; never commit"
    owner: ingest-owner

  - asset_id: procurement_awards
    kind: derived_table
    committed: false
    point_in_time: no
    pit_notes: "obligations, not revenue; snapshot lacks historical publication time →
                EXCLUDED from all historical gain claims (README.md:329)"
    owner: research-owner

  - asset_id: sec_facts_32co
    kind: derived_table
    committed: false
    point_in_time: yes
    pit_notes: "as-of by filing date; consolidated company facts only, never relabelled product sales"
    owner: research-owner

  - asset_id: corpus_metrics_2026_10_30
    kind: snapshot
    committed: true
    path_in_repo: docs/metrics.json
    size_bytes: 468561
    sha256: "<64 hex>"
    provenance: {publisher: "MedRadar", generated_at: "2026-10-30T19:23:33Z"}
    point_in_time: not_applicable
    superseded: true                  # ← forces the banner wherever it is displayed
    owner: output-owner

  - asset_id: nmpa_registrations
    kind: external
    committed: false
    point_in_time: "unknown"
    pit_notes: "not scraped; adapter accepts a user-supplied CSV at data/nmpa_registrations.csv;
                absent ⇒ every CN value is null, never zero"
    owner: ingest-owner
```

**Enforcement — `g5-assets`:**

```yaml
g5-assets:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - run: pip install pyyaml
    - name: every committed file > 1 MiB is registered
      run: python scripts/check_assets.py --require-for-large-files --threshold 1048576
    - name: every registry path exists and matches its sha256
      run: python scripts/check_assets.py --verify-committed
    - name: every asset declares point_in_time and licence
      run: python scripts/check_assets.py --require-fields point_in_time,provenance.licence
    - name: no doc may cite an asset absent from the registry
      run: python scripts/check_assets.py --crossref docs/
    - name: registry is generated, not hand-edited
      run: |
        python scripts/gen_assets_doc.py
        git diff --exit-code -- docs/DATA_ASSET_REGISTER.md
```

**Tie to findings.** Directly kills the 1.2-vs-1.3 GiB class of error (E8) by making `size_bytes` a
single field consumed by the generator; makes the procurement exclusion structural rather than a
sentence someone can forget.

---

## 8. M6 — README / research-status sync (generated, never maintained)

**Problem.** E1, E2, E3, E4, E8. The README is a 480-line hand-maintained aggregate of facts that
exist elsewhere. Six documents restate the same facts and all six disagree. The fix is not "be more
careful"; it is **stop restating**.

**Mechanism.** The README keeps only three kinds of content:

1. **Generated blocks** (status table, badges, capability buckets, experiment list) — delimited,
   produced by `scripts/gen_readme.py` from `PROJECT_STATE.yaml` + `docs/metrics.json` + manifests.
2. **Stable prose** (mission, question, architecture, limitations policy) — changes rarely, reviewed
   like an ADR.
3. **Numbers only from the facts ledger** (`docs/state/FACTS_LEDGER.yaml`), which is itself generated
   from frozen manifests (`verdict.numbers`) and committed artefacts.

```markdown
<!-- BEGIN GENERATED: status — source PROJECT_STATE.yaml + docs/metrics.json; do not hand-edit -->
| Field | Value |
|---|---|
| Version | 0.5.0 |
| `main` | `b2a14c0` (2026-11-02) |
| Tests | 1,074 — green at `b2a14c0`, measured 2026-11-12 |
| Data snapshot | 2026-10-30T19:23:33Z |
| Licence | MIT |
<!-- END GENERATED: status -->
```

```yaml
# docs/state/FACTS_LEDGER.yaml  (generated; the union of every frozen manifest's verdict.numbers)
schema: medradar.facts_ledger.v1
generated_at: "2026-11-12T00:00:00+08:00"
facts:
  - {id: N-03, value: "1074", unit: tests, source: "ci.yml job test", ref: b2a14c0, label: FACT}
  - {id: N-14, value: "PR-AUC 0.7935", source: experiments/reverse_rd_v2/MANIFEST.yaml,
     study: reverse_rd_v2/v2, ref: reverse_rd_v2/v2, label: FACT}
  - {id: N-22, value: "38 trades / +19.19 % / Sharpe 2.30", source: docs/metrics.json,
     qualifiers: [in-sample, long-only, 38-trades, 11-months], label: FACT}
```

**Three checks, all blocking:**

**`g2-readme-sync`** — regenerate and diff both languages:

```yaml
g2-readme-sync:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - run: pip install pyyaml
    - name: generated blocks are current in both languages
      run: |
        python scripts/gen_readme.py --all
        git diff --exit-code -- README.md README.zh-CN.md
    - name: structural parity (heading count, table row counts, image count)
      run: python scripts/check_parity.py --en README.md --zh README.zh-CN.md
    - name: mermaid node-id parity between languages
      run: python scripts/check_parity.py --mermaid-node-ids --en README.md --zh README.zh-CN.md
```

**`g3-facts-ledger`** — every numeral in prose must be in the ledger:

```yaml
g3-facts-ledger:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - run: pip install pyyaml
    - name: no unledgered numerals in the front-door docs
      run: |
        python scripts/check_facts.py \
          --ledger docs/state/FACTS_LEDGER.yaml \
          --files README.md README.zh-CN.md docs/PROJECT_STATUS.md
    - name: superseded facts never appear without the banner
      run: python scripts/check_facts.py --forbid-superseded-without-banner docs/
    - name: claim-denied sentences are present
      run: python scripts/check_facts.py --require-claim-denied README.md README.zh-CN.md
```

**`g3b-no-branch-claims`** — the capability claim check (the one that would have caught E5):

```yaml
g3b-no-branch-claims:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
      with: {fetch-depth: 0}
    - name: every capability claimed "on main" resolves to a path at HEAD
      run: python scripts/check_claims.py --state PROJECT_STATE.yaml --ref HEAD
    - name: branch-only names never appear outside the branch-only block
      run: python scripts/check_claims.py --forbid-branch-names-outside-block README.md README.zh-CN.md
    - name: workflow names cited in docs exist on main
      run: python scripts/check_claims.py --assert-workflow-names-exist
```

**Tie to findings.** E1 (one count), E2 (one positioning), E3 (refs generated), E4 (superseded banner
enforced), E5 (workflow names machine-checked — this is the exact gate that would have failed on
`_FACTS.md` §7's `observatory.yml`), E8 (numbers from one source).

---

## 9. M7 — CI quality gates (the exact catalogue)

**[FACT] There are four workflows on `main`**: `ci.yml`, `forecast-cycle.yml`, `live.yml`,
`weekly.yml`. `observatory.yml` is **not** among them (E5). To avoid multiplying workflow files — which
is itself drift — **all new gates go into `ci.yml`**, the only workflow that runs on every PR
(`ci.yml:3-6`: `on: push: branches: [main]` + `pull_request`).

| Gate | Job name | Runs in | Trigger | Blocking | Enforces |
|---|---|---|---|---|---|
| G1 | `g1-state-fresh` | `ci.yml` (new) | PR + push main | yes | M1 |
| G2 | `g2-readme-sync` | `ci.yml` (new) | PR when `README*.md`, `PROJECT_STATE.yaml`, `docs/metrics.json` change | yes | M6 |
| G3 | `g3-facts-ledger` | `ci.yml` (new) | PR + push main | yes | M6 |
| G3b | `g3b-no-branch-claims` | `ci.yml` (new) | PR + push main | yes | M6, E5 |
| G4 | `g4-freeze-verify` | `ci.yml` (new) | PR touching `experiments/**` or `research/**`; also push main | yes | M4 |
| G5 | `g5-assets` | `ci.yml` (new) | PR + push main | yes | M5 |
| G6 | `g6-ownership` | `ci.yml` (new) | PR only | yes | M2 |
| G7 | `g7-pr-contract` | `ci.yml` (new) | PR only | yes | M3, M11 |
| G8 | `g8-adr-index` | `ci.yml` (new) | PR touching `docs/adr/**` or `medradar/**` public interfaces | yes | M8 |
| G9 | `g9-lease` | `ci.yml` (new) | PR only | advisory → blocking after 30 days | M9 |
| G10 | `selftest` (existing) | `ci.yml` job `test` | PR + push | yes, already | package integrity |
| G11 | `data-stats` (existing) | `ci.yml` job `data-stats` | PR + push | yes, already | stats contract |
| G12 | `windows-install` (existing) | `ci.yml` job `windows-install` | PR + push | yes, already | packaging, Windows data-files |
| G13 | `forecast-cycle` | `forecast-cycle.yml` | Monday 02:00 UTC + manual | no (artifact) | research cadence |
| G14 | `live-lane` | `live.yml` | manual only | no | simulation |
| G15 | `weekly-radar` | `weekly.yml` | Sunday 21:00 UTC + manual | deploy | Pages |

**Additional insertions into existing workflows (small, high leverage):**

```yaml
# weekly.yml — insert BEFORE the "Collect, analyze, render" step in the `build` job.
      - name: State + README are current before we publish a site
        run: |
          pip install pyyaml
          python scripts/gen_state.py --all --check
          python scripts/gen_readme.py --all --check
          python scripts/check_facts.py --ledger docs/state/FACTS_LEDGER.yaml --files README.md
```

```yaml
# forecast-cycle.yml — insert AFTER "Run the continuous forecast cycle".
      - name: The cycle output must satisfy its own manifest
        run: python scripts/check_freeze.py --verify-run out/forecast_cycle
```

**[RECOMMENDATION] Branch protection.** Mark G1–G10 as required status checks on `main`, and require
a review from the owning area. **[UNVERIFIED]** current settings; if they cannot be changed, the gates
still fail loudly in the PR UI, which is 80 % of the value for an agent-driven repo where
"CI red" is the signal an agent actually reads.

**Gate budget discipline.** Ten new jobs × ~40 s each = ~7 min added to PR latency **[INFERENCE]**.
That is acceptable; a repo whose front page is wrong in seven ways should spend seven minutes
preventing it. If it becomes painful, merge G1+G2+G3 into one job (`g-docs`) — but never drop G3b.

---

## 10. M8 — Architecture change proposals (ADR / RFC)

**Problem.** E3, E6. `research/DECISIONS.md` is a good ADR file whose D-001 states `main` is frozen at
`7a639f7` while `main` is 154 commits ahead. The format worked; the *index and the state claims* did
not. Meanwhile `#12→#13→#14→{#15,#16}` shows architecture decisions being made implicitly by stack
order.

**Mechanism.** Two-tier document process, both under `docs/adr/`.

| Tier | When | File | Review | Immutable after |
|---|---|---|---|---|
| **ADR** | reversible, single-area, implementation-level | `docs/adr/NNNN-slug.md` | area owner | `status: accepted` |
| **RFC** | irreversible or cross-area: changes a public interface (`events` schema, `metrics.json`
  contract, `forecast_registry` schema), adds a runtime dependency, changes the merge/base strategy,
  or touches ≥2 areas | `docs/adr/rfc/NNNN-slug.md` | Lead + area owners + 7-day comment window | `status: accepted` |

**Rules.**

1. ADR numbers are sequential, never reused, never renumbered.
2. An accepted ADR is **append-only**: corrections are a new ADR with `supersedes:`.
3. **An ADR may not assert the state of a branch.** State assertions must be generated from
   `PROJECT_STATE.yaml` (this is the fix for E3 — D-001's "main is frozen at 7a639f7" is exactly the
   forbidden sentence).
4. `docs/adr/INDEX.md` is generated; a PR adding an ADR must regenerate it (`g8`).
5. Existing `research/DECISIONS.md` entries are **grandfathered**, not migrated, but its D-001 gets an
   erratum note (a one-line `superseded_by` pointing at the fact that `main` = `b2a14c0`).

**Template** — §14.2.

**Enforcement — `g8-adr-index`:** regenerate `docs/adr/INDEX.md`; assert every ADR has
`status/date/deciders/context/decision/consequences`; assert no ADR contains a hard-coded branch state
regex (`main` + a 7/40-hex sha, or the strings "frozen at", "currently at", "HEAD is"); assert every
`supersedes:`/`superseded_by:` pair is reciprocal.

---

## 11. M9 — Agent parallel development and handoff protocol

**Problem.** E7, E10, and the structural facts of `_FACTS.md` §4–§5: 19 drafts, 3-deep stacks, 34
branches, 39 registered worktrees, and five local branches with unpushed commits (33 of them on
`research/phoenix-001-external-methods`). Duplicate work is not hypothetical: PR #17 rewrote the README
while this audit proposed a README rewrite.

**The five rules.**

**R1 — Branch lease.** Before an agent writes, it claims a lease in `docs/state/LEASES.yaml` (or via a
`team_task`-equivalent record). A lease is: branch, owner, area(s), write scopes, base, expiry.

```yaml
schema: medradar.leases.v1
updated_at: "2026-11-12T10:00:00+08:00"
leases:
  - id: L-2026-11-12-01
    branch: comms/readme-redesign-001
    owner: comms-lead
    area: docs
    write_scopes:
      - docs/refoundation/README_REDESIGN_PROPOSAL.md
      - docs/refoundation/AGENT_COLLABORATION_PROTOCOL.md
      - docs/refoundation/_evidence/comms/
    base: b2a14c0
    expires: "2026-11-13T10:00:00+08:00"
    status: active                     # active | released | expired
```

**R2 — Write-scope claim.** Scopes are path prefixes. Two active leases may not overlap; the check is
mechanical (`g9`). Serialising agents is cheaper than reconciling two versions of one file.

**R3 — Evidence requirement.** Any PR that makes a research or numeric claim must link:
(a) the manifest path, (b) the manifest `sha256`, (c) the exact command that produced the number.
"No manifest, no number" (M4 rule 2). **[FACT-based rationale]** the repo already has frozen
`experiments/` artefacts; the gap is that nothing forces a PR to point at them.

**R4 — Handoff note.** A note in `docs/state/HANDOFF/<branch>.md` is mandatory when an agent stops
mid-task, when a lease transfers, or when a branch is parked > 7 days. Template in §14.4.

**R5 — No silent supersession.** If your work overlaps an open branch, you must either take it over
(recorded in the handoff note) or leave it untouched and say why. **[FACT-based rationale]** PR #17 vs
this proposal.

**Enforcement — `g9-lease`:**

```yaml
g9-lease:
  if: github.event_name == 'pull_request'
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - run: pip install pyyaml
    - name: PR touches only paths claimed by an active lease for this branch
      run: python scripts/check_lease.py --leases docs/state/LEASES.yaml \
             --branch "${{ github.head_ref }}" --diff-base "origin/${{ github.base_ref }}"
    - name: no overlapping write scopes across open PRs
      env: {GH_TOKEN: "${{ secrets.GITHUB_TOKEN }}"}
      run: python scripts/check_lease.py --cross-pr-overlap --repo "${{ github.repository }}"
    - name: handoff note present for parked or transferred branches
      run: python scripts/check_lease.py --require-handoff-after-days 7
```

**[RECOMMENDATION]** Make `g9` advisory for 30 days, then blocking. Making it blocking on day one,
with 19 open drafts that predate the rule, would freeze the repo.

---

## 12. M10 — Periodic technical-debt audit cadence

**Problem.** E4, E6, E7 recur on a schedule nobody set. REFOUNDATION-001 happened once; it needs a
cadence so that the next "seven test counts" is caught in weeks, not after 2.8 M unmerged lines.

| Cadence | Who | What | Output |
|---|---|---|---|
| **Every push (automated)** | CI | all gates; publish `badges.json`; compute doc-staleness | Actions summary |
| **Weekly (automated)** | `weekly.yml` job | stale-docs report: files whose `updated_at` in front-matter is older than the facts they cite; draft PRs older than 30 days; branches with no PR; local-only commits | `docs/state/reports/weekly-<date>.json` + issue |
| **Monthly (30 min, human)** | owner + area owners | triage the weekly reports; update `docs/TECHNICAL_DEBT_REGISTER.md`; retire or re-base dead branches; review `claim_denied` sentences | debt register diff |
| **Quarterly (1 day, agent-assisted)** | full audit team, like REFOUNDATION-001 | re-run the fact collector (`docs/refoundation/_evidence/collect_facts.py`); re-verify every front-door number; audit the ownership map against reality | new `_FACTS.md` snapshot + updated registers |

**Debt register schema** (generated index, human-written items):

```yaml
# docs/state/DEBT.yaml
schema: medradar.debt.v1
items:
  - id: TD-001
    title: "Seven competing test counts on main"
    evidence: [README.md#L42, docs/ATTRIBUTION.md#L55, research/STATE.json#L35]
    severity: critical
    owner: lead
    discovered: "2026-11-12"
    discovered_by: REFOUNDATION-001/A6
    fix: "M1 + M6: generate the count, gate with g1/g3"
    status: open                  # open | scheduled | fixed | wontfix
    target: "2026-11-30"
  - id: TD-002
    title: "Pages source contradicts weekly.yml (legacy main:/docs vs Actions artifact)"
    evidence: [".github/workflows/weekly.yml#L10-L11", "_FACTS.md §7"]
    severity: critical
    fix: "Pick one; assert it in PROJECT_STATE.gates.pages_source; g1 check"
    status: open
```

**Rule.** A debt item is closed only when a **gate** prevents recurrence. Fixing the symptom without a
gate is recorded as `wontfix` with a reason, so the next quarterly audit does not rediscover it.

---

## 13. M11 — Definition of Done

Two different definitions, because research and product work fail differently.

### 13.1 Research DoD (a study is done when it is frozen, refutable, and honest)

- [ ] Question and hypothesis written **before** results; `preregistered_at` ≤ first result commit.
- [ ] `experiments/<study_id>/MANIFEST.yaml` present, schema-valid, all `outputs[].sha256` real.
- [ ] `verdict.headline` ∈ {positive, negative, mixed, inconclusive} — `inconclusive` is a valid,
      publishable outcome.
- [ ] `verdict.claim_allowed` written in one sentence, with its numbers, and every number is in
      `verdict.numbers`.
- [ ] `verdict.claim_denied` written — what this study does **not** license anyone to say.
- [ ] At least one **named baseline** (`constant`, `company`, `track`, `per-pair base rate`) with a
      paired comparison; a bare model metric is not a result.
- [ ] Purge/leakage statement: label window vs origin; left-censoring; excluded sources with reasons.
- [ ] Multiple-testing policy stated (Holm family defined) if >1 hypothesis.
- [ ] Negative results kept, not deleted, and given the same prominence in any summary.
- [ ] Immutable tag `freeze/<study>/v<N>` pushed.
- [ ] README/docs numbers regenerate from the manifest (`g3` green).

### 13.2 Product DoD (a feature is done when it is on `main`, tested, documented, and deletable)

- [ ] On `main` (merged), exercised by the offline suite — not only by a manual run.
- [ ] `python -m pytest` green; `python -m medradar selftest` green; CI matrix green (3.10/3.11/3.12 +
      Windows install).
- [ ] No new runtime dependency in the core package (stdlib only) — or an ADR/RFC approving it.
- [ ] `docs/METHODS.md` and `docs/SCHEMA.md` updated **before** the metric changes meaning.
- [ ] Capability added to exactly one bucket in `PROJECT_STATE.yaml` (`on_main_tested` /
      `on_main_experimental` / `on_main_superseded` / `branch_only`), and if bucket B, the docs say
      "experimental" in the same sentence.
- [ ] No `git diff` after regeneration (`g1`/`g2` green).
- [ ] Offline demo still works (`medradar demo` in `ci.yml:43-44`).
- [ ] If it touches the Pages output, `weekly.yml` still produces a valid site and
      `gates.pages_source` still describes reality.

### 13.3 The one thing both share

**No claim may be stronger than its artefact.** A product claim needs a test; a research claim needs a
frozen manifest with a hash. If neither exists, the claim is prose and belongs in a design doc, not in
the README.

---

## 14. Templates (copy-paste)

### 14.1 `.github/pull_request_template.md` (replacement)

```markdown
<!-- Title must be `type(area): subject` — e.g. `fix(store): as-of query returned later knowledge time`.
     All `<!-- -->` comments are stripped from the rendered PR; leave the headings. -->

## What this changes

<!-- 1-3 sentences. If it changes behaviour, say what was true before. -->

## Why

<!-- Link the issue/RFC: Closes #123 / RFC-0007. -->

## Classification

- **type:** feat | fix | research | docs | data | refactor | infra | chore
- **area:** ingest | store | resolve | analyse | products | simulation | research-foundation |
  research-lane | agent | output | docs | ci | state
- **base branch:** `main` | `<other>`  ← if not `main`, this PR MUST be `status:draft`
- **stack depth:** 1 (base is `main`) | 2 | 3 | 4
- **blocked by:** #__ (required when `status:blocked`)

## Capability claim

<!-- Which bucket of PROJECT_STATE.yaml does this land in? Delete three of four. -->

- [ ] `on_main_tested` — merged to main AND exercised by the offline suite
- [ ] `on_main_experimental` — on main, measurably unreliable; docs say "experimental"
- [ ] `on_main_superseded` — replaces an older result; old one gets a superseded banner
- [ ] `branch_only` — NOT a main capability; this PR is a draft and must not be described as shipped

## Evidence (required for any number)

| Number | Value | Provenance | Frozen manifest | Commit |
|---|---|---|---|---|
|  |  | `path:line` or command | `experiments/<study>/MANIFEST.yaml` @ `sha256:` |  |

<!-- No manifest, no number. If you cannot fill this table, remove the number. -->

## Gates

- [ ] `python -m pytest` green
- [ ] `python -m medradar selftest` green (offline, no network)
- [ ] `python scripts/gen_state.py --all` then `git diff` is empty
- [ ] `python scripts/gen_readme.py --all` then `git diff` is empty
- [ ] every numeral in this PR's doc changes exists in `docs/state/FACTS_LEDGER.yaml`
- [ ] no new runtime dependency in the core package (stdlib only)
- [ ] if a metric changed meaning: `docs/METHODS.md` + `docs/SCHEMA.md` updated first
- [ ] if data quality changed: before/after counts in this description
- [ ] lease claimed in `docs/state/LEASES.yaml`; write scope matches the diff

## Not claimed

<!-- One sentence: what a reader must NOT infer from this PR.
     This line is mandatory for research PRs and is checked by g7. -->
```

### 14.2 ADR / RFC template — `docs/adr/NNNN-slug.md`

```markdown
# NNNN — <decision in one imperative line>

- **Status:** proposed | accepted | superseded
- **Date:** YYYY-MM-DD
- **Deciders:** <names/roles>
- **Area(s):** <OWNERS.yaml area ids>
- **Tier:** ADR (reversible, single area) | RFC (cross-area / public interface / dependency / merge policy)
- **Supersedes:** NNNN or null
- **Superseded by:** NNNN or null

## Context

<!-- The forces at play, with locators, not opinions. Cite files/PRs/measurements. -->

## Decision

<!-- What we will do. One paragraph, then a numbered list of the concrete changes. -->

## Alternatives considered

| Alternative | Why rejected |
|---|---|
|  |  |

## Consequences

- **Positive:**
- **Negative / accepted cost:**
- **Follow-ups:**

## State assertions

<!-- FORBIDDEN: "main is at <sha>", "branch X is frozen", "HEAD is ...".
     State facts are generated. Instead write: "see PROJECT_STATE.yaml (generated <date>)". -->
This ADR intentionally asserts no branch state.

## Review

- Comment window: N days (RFC only)
- Approvals: <areas>
```

### 14.3 Experiment freeze manifest — `experiments/<study_id>/MANIFEST.yaml`

See §6 for the full annotated example (`reverse_rd_v2`). Required top-level keys:
`schema, study_id, version, title, status, question, hypothesis, preregistered_at, protocol_doc,
code, data, environment, outputs, verdict, freeze`. Anything missing fails `g4`.

Minimal valid skeleton:

```yaml
schema: medradar.experiment_manifest.v1
study_id: <snake_case>
version: 1
title: "<one line>"
status: proposed            # proposed | running | frozen | superseded
question: "<the question>"
hypothesis: "<falsifiable>"
preregistered_at: "YYYY-MM-DD"
protocol_doc: docs/<X>.md
code: {commit: "<sha>", entrypoints: []}
data: {dataset_ids: [], row_counts: {}, origins: {}, holdouts: [], point_in_time: true,
       purge_window_months: 12, known_limits: []}
environment: {python: "3.12", dependencies: ["stdlib"], seeds: [0], determinism: "<statement>"}
outputs: [{path: "<path>", sha256: "<64 hex>"}]
verdict:
  headline: inconclusive    # positive | negative | mixed | inconclusive
  claim_allowed: "<one sentence>"
  claim_denied: "<one sentence>"
  numbers: [{id: N-xx, value: "<value>", scope: "<holdout/window>"}]
freeze: {frozen_at: "<ISO>", frozen_by: "<role>", tag: "freeze/<study>/v1",
         immutability: "manifest edits require a new version + tag"}
```

### 14.4 Handoff note — `docs/state/HANDOFF/<branch>.md`

```markdown
# Handoff — <branch>

- **From:** <agent/role>  **To:** <agent/role or "unclaimed">
- **Date:** YYYY-MM-DDTHH:MM+08:00
- **Lease:** L-YYYY-MM-DD-NN  **Expires:** <ISO>
- **Base:** <sha> · **Head:** <sha> · **Commits ahead:** N · **Behind base:** N

## State of the work

<!-- One paragraph a cold agent can act on. What is done, what is half-done, what is a trap. -->

- Done:
- Half-done (file:line):
- Do NOT touch (why):

## Verified facts

| Claim | How verified | Where |
|---|---|---|
|  | command / file:line |  |

## Evidence produced

| Artefact | sha256 | Path |
|---|---|---|
|  |  |  |

## Blockers

| Blocker | Needs | Owner |
|---|---|---|
|  |  |  |

## Next three actions

1.
2.
3.

## What a successor must NOT redo

<!-- Duplicated work is the failure this protocol exists to prevent. List branches/PRs already
     covering this ground, with their numbers. -->
```

### 14.5 Lease + write-scope claim — `docs/state/LEASES.yaml`

See §11 R1 for a filled example. Required fields per lease: `id, branch, owner, area, write_scopes,
base, expires, status`.

---

## 15. Rollout plan (ordered, smallest risky step first)

| Step | What | Why first | Blocks |
|---|---|---|---|
| **1** | Write `PROJECT_STATE.yaml` by hand from the audit facts; add `scripts/gen_state.py --check` as G1 | one file kills E1/E3 classes | everything |
| **2** | Add `docs/state/FACTS_LEDGER.yaml` + `g3` in warn-only mode | makes the drift visible without breaking PRs | step 3 |
| **3** | Land the README redesign (§A6 proposal) with generated status block; flip `g2`/`g3` to blocking | consumes step 1–2 | front page |
| **4** | Add experiment manifests for the three already-frozen studies (`reverse_rd_v1`, `v2`, `early_signal_5firms`); `g4` blocking | turns existing artefacts into machine-verifiable claims | M4 |
| **5** | Add `OWNERS.yaml` → CODEOWNERS; `g6` warn-only → blocking | ownership before parallel work increases | M2 |
| **6** | Replace the PR template; `g7` blocking | every new PR is classified from day one | M3/M11 |
| **7** | `g9` lease checks, warn-only for 30 days | serialises agents without freezing the 19 drafts | M9 |
| **8** | ADR index + `g8`; erratum on `research/DECISIONS.md` D-001 | fixes the stale-reference class | M8 |
| **9** | Weekly/monthly/quarterly cadence; debt register | makes it self-sustaining | M10 |

**[INFERENCE]** Steps 1–2 are ~1.5 engineer-days. Steps 3–6 are ~2 days. Steps 7–9 are ~1 day plus
recurring cost. Total ≈ 4–5 days for the enforcement layer — against 2,824,212 unmerged lines and 7
contradictory test counts, that is the cheapest leverage available in this repository.

---

## 16. What to deliberately **not** do

1. **Don't add a new workflow file per gate.** Four workflows on `main` is already the boundary between
   "reviewable" and "nobody reads these". Extend `ci.yml`.
2. **Don't delete the 19 drafts to tidy up.** They contain 2.8 M lines including five local-only
   branches with unpushed commits (`_FACTS.md` §5). Quarantine + register, never delete.
3. **Don't make `g9` blocking immediately.** It would freeze every pre-existing draft.
4. **Don't build a dashboard for the state file.** The state file *is* the dashboard; a UI is another
   hand-maintained surface that will drift.
5. **Don't let the protocol become a document nobody regenerates.** It has no numbers of its own
   (deliberately) and every mechanism it names has a gate ID; if a mechanism has no gate, cut it.

---

## 17. Open questions for the owner

1. **Who is the "lead" in `PROJECT_STATE.yaml`?** A named human, or the agent role? Gates that require
   a decision (draft policy, supersession) need a real person to escalate to.
2. **Can branch protection be configured?** If yes, G1–G10 become required checks and the protocol has
   teeth. If no (solo repo, no admin token), the gates are advisory and the protocol's value halves —
   say which world we are in before implementing.
3. **Do you accept `status:draft` as the default for every stacked PR** (i.e. 19 existing drafts get
   relabelled and none can become "ready" until its base merges)? That is the correct rule and it will
   feel like a freeze.
4. **Is PR #17's `PROJECT_STATUS.md` allowed to become the generated status doc**, or should that name
   be reserved for a new file? Two status docs is the failure mode.
5. **What is the budget for the weekly automated reports?** They need somewhere to land — an issue, a
   Actions summary, a file. Prefer a file in `docs/state/reports/` so it is diffable, but that grows
   the repo; a rolling issue avoids that but is not gated.
6. **Which command is canonical for the test count** — `python -m pytest` (1,074) or
   `python -m medradar selftest` (what `ci.yml:29` actually runs)? The published number must be the
   output of the command CI runs, else the badge is theatre.
7. **Who owns `PROJECT_STATE.yaml` write access?** The map says `lead` only; if several agents run in
   parallel, the state file becomes the hottest contention point. Confirm that serialising it is
   acceptable.
8. **Is there an existing governance document in a draft branch** (e.g. PHOENIX/ATLAS method docs) that
   this protocol should merge with rather than shadow? I did not audit branch docs for this; if one
   exists, it wins on prior art and this document should be reconciled, not shipped alongside.

---

## 18. Findings register (for the executive summary)

| ID | Mechanism | Failure it kills | Severity of the failure | Gate |
|---|---|---|---|---|
| E1 | M1, M6 | seven test counts | critical | g1, g3 |
| E2 | M1, M6 | three positionings | critical | g1, g3 |
| E3 | M8 | ADR asserts false `main` state | high | g8 |
| E4 | M4, M6 | superseded result still published | critical | g4, g3 |
| E5 | M6 | nonexistent workflow cited as `main`'s | high | g3b |
| E6 | M3, M9 | 19 drafts, 3-deep invisible stacks | critical | g7, g9 |
| E7 | M9 | duplicate README rewrite in flight | high | g9 |
| E8 | M1, M5 | 1.2 vs 1.3 GiB drift | medium | g1, g5 |
| E9 | M3, M11 | PR template can't express the work | medium | g7 |
| E10 | M2, M9 | no ownership map | high | g6, g9 |
