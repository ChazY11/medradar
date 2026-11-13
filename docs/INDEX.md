# Documentation index

**Purpose.** One navigation page for a repository with ~1,100 files across docs, research, papers and
audit archives. It says where the canonical version of each thing lives, what state it is in, and what
has been superseded. It **links**; it does not copy. If a fact is stated in two places, this page
points at the canonical one and the other should be trimmed.

**Status vocabulary**

| Status | Meaning |
|---|---|
| **current** | Exists on `main` (after the REFOUNDATION-003 integration) and is the canonical version. |
| **archived** | Preserved for provenance. Do not extend or "fix"; corrections go in a new document that cites it. |
| **draft** | On an open branch or PR, **not** on `main`. Not a shipped claim. |
| **⧗** | Added to `main` by the REFOUNDATION-003 integration set (#32 governance, #35 Evidence Core v1, #36 E1b research, #34 README truth). The path does not exist at `b2a14c0`; it exists once those PRs merge. |

> **Snapshot note.** This index is written against the targeted post-integration tree
> (`main` = `b2a14c0` + #32 + #34 + #35 + #36). Every ⧗ row is a real file on the corresponding PR
> branch, verified by `git ls-tree`; none is aspirational.

---

## How to read this repository

| If you are… | Start here | Then |
|---|---|---|
| Evaluating the project | [`README.md`](../README.md) → *Validation status* | [`RESEARCH.md`](RESEARCH.md), [`CASES.md`](CASES.md) |
| Reproducing a result | [`README.md`](../README.md) → *Reproduce* | [`METHODS.md`](METHODS.md), [`SCHEMA.md`](SCHEMA.md) |
| Contributing code or data | [`CONTRIBUTING.md`](../CONTRIBUTING.md) | [`GOOD_FIRST_ISSUES.md`](GOOD_FIRST_ISSUES.md), [`METHODS.md`](METHODS.md) |
| Auditing what is actually merged | this page → *4. Audit archive* | ⧗[`PROJECT_STATE.yaml`](../PROJECT_STATE.yaml), ⧗[`docs/RESEARCH_INDEX.md`](RESEARCH_INDEX.md) |

---

## 1. Start here — users and developers

| Document | What it is | Status |
|---|---|---|
| [`README.md`](../README.md) · [`README.zh-CN.md`](../README.zh-CN.md) | Project front page: mission, capabilities, limitations, quickstart | current |
| [`CONTRIBUTING.md`](../CONTRIBUTING.md) | The highest-value contributions are curated knowledge files, not code | current |
| [`GOOD_FIRST_ISSUES.md`](GOOD_FIRST_ISSUES.md) | Small, verifiable tasks with files + reproduce commands | current |
| [`ROADMAP.md`](../ROADMAP.md) | Product/engineering roadmap; the research side has its own protocol docs (§2) | current |
| [`CHANGELOG.md`](../CHANGELOG.md) | Per-release record; CI asserts it contains the current version | current |
| [`docs/refoundation/phase3/README_VISUAL_PLAN.md`](refoundation/phase3/README_VISUAL_PLAN.md) ⧗ | Image/caption policy for the front page and site | draft (this work) |

**Quickstart lives in one place only:** the `README.md` *Reproduce* section. This index deliberately
does not repeat the commands, so they cannot drift.

---

## 2. Current research — protocol, results, studies

### 2.1 Protocol (read before trusting any number)

| Document | What it fixes | Status |
|---|---|---|
| [`research/MISSION.md`](../research/MISSION.md) | The single top-level research question and what is out of scope | current |
| [`research/HYPOTHESES.md`](../research/HYPOTHESES.md) · [`research/HYPOTHESES_DETECTION.md`](../research/HYPOTHESES_DETECTION.md) | Pre-registered hypotheses before modelling | current |
| [`research/PREDICTION_PROTOCOL.md`](../research/PREDICTION_PROTOCOL.md) | Freeze rules, test windows, what counts as a claim | current (see caveat below) |
| [`research/EXPERIMENTS.md`](../research/EXPERIMENTS.md) | Experiment register | current |
| [`research/DATA_PROVENANCE.md`](../research/DATA_PROVENANCE.md) | Where each field came from | current |
| [`research/DECISIONS.md`](../research/DECISIONS.md) | ADR-style decision record (D-001 …); the canonical list is generated into ⧗[`RESEARCH_INDEX.md`](RESEARCH_INDEX.md) | current |
| [`ASSUMPTIONS.md`](ASSUMPTIONS.md) | Every modelling assumption with status | current |
| ⧗[`docs/governance/FROZEN.yaml`](governance/FROZEN.yaml) | Machine-readable freeze register (what may not change) | draft (#32) |

> **Caveat — read this before quoting a "point-in-time" claim.** The shipped snapshot has
> `published_at = available_at = event_date` for 100 % of rows and `first_seen_at` from a bulk import,
> i.e. **independent public time = 0 rows**. The protocol documents describe the *intended* discipline;
> they do not retroactively confer public timestamps the data does not have. See
> ⧗[`E1B_SOURCE_RECOVERY.md`](refoundation/phase2/E1B_SOURCE_RECOVERY.md) for which sources can and
> cannot supply one.

### 2.2 Results

| Document | What it is | Status |
|---|---|---|
| [`research/RESULTS/README.md`](../research/RESULTS/README.md) | Index of per-cycle result notes | current |
| [`research/RESULTS/PROMOTIONS.md`](../research/RESULTS/PROMOTIONS.md) | Append-only promotion ledger (a promotion is not a finding) | current |
| `research/RESULTS/cycle*.md` | One file per cycle, dated; immutable once written | archived |
| [`research/studies/early_signal_5firms/PHASE0_REPORT.md`](../research/studies/early_signal_5firms/PHASE0_REPORT.md) | Five-firm deep case study — Phase 0 CONDITIONAL-GO; lead-time gate G1 **NO-GO** | current |
| [`research/studies/early_signal_5firms/REPRODUCIBILITY.md`](../research/studies/early_signal_5firms/REPRODUCIBILITY.md) | How to re-derive the study | current |
| [`research/COMPLETION_REPORT.md`](../research/COMPLETION_REPORT.md) | Programme completion position | archived |
| [`papers/README.md`](../papers/README.md) · [`papers/PAPER_v1.md`](../papers/PAPER_v1.md) | Paper drafts with machine-checked claim maps — not submitted, not peer reviewed | draft |
| [`papers/PAPER_NEGATIVE_v1.md`](../papers/PAPER_NEGATIVE_v1.md) · [`papers/CLAIMS_NEGATIVE.json`](../papers/CLAIMS_NEGATIVE.json) | The negative-results paper and its claims | draft |
| ⧗[`docs/RESEARCH_INDEX.md`](RESEARCH_INDEX.md) | **Generated** index of studies, capabilities and decisions — do not hand-edit | draft (#32) |

**Canonical-claims rule.** A number is quotable only if it appears in a frozen artefact
(`experiments/`, `research/forecasts/`, or a `papers/CLAIMS*.json` entry) and in
`docs/refoundation/phase2/E1B_SOURCE_RECOVERY.md`-grade evidence for its timestamp basis. Otherwise it
is a descriptive statistic, and must be labelled as one.

### 2.3 Market-to-R&D lane (separate contract)

| Document | Status |
|---|---|
| [`REVERSE_RD.md`](REVERSE_RD.md) — the lane's methods contract | current |
| [`MARKET_DATA.md`](MARKET_DATA.md) — SEC / USAspending semantics and limits | current |
| [`PUBLICATION_PATENT_DATA.md`](PUBLICATION_PATENT_DATA.md) — OpenAlex evaluated; patents key-gated, **not** evaluated | current |
| [`AUDIT_MARKET_TO_RD.md`](AUDIT_MARKET_TO_RD.md) — the audit that produced the negative result | archived |

---

## 3. Data and architecture contracts

| Document | What it fixes | Status |
|---|---|---|
| [`SCHEMA.md`](SCHEMA.md) | The `metrics.json` / report contract. **Change this before changing a metric.** | current |
| [`METHODS.md`](METHODS.md) | Metric definitions, estimators, multiple-testing, threats to validity | current |
| [`DATA.md`](DATA.md) | Generated data audit: counts, timestamps, freshness, database size | current (generated) |
| [`CALIBRATION.md`](CALIBRATION.md) | Reproducible LLM-judge calibration on 25 hand-labelled 8-Ks | current |
| [`CASES.md`](CASES.md) | Case-library definition and the extreme-return audit | current |
| [`TKG.md`](TKG.md) · [`TKG_INTEGRATION.md`](TKG_INTEGRATION.md) | Bitemporal store: valid time vs knowledge time | current |
| [`FORECAST_REGISTRY.md`](FORECAST_REGISTRY.md) | Append-only forecast ledger, nowcast cohort, as-of scoring | current |
| [`ATTRIBUTION.md`](ATTRIBUTION.md) | Authorship per increment | current |
| [`INTEGRATION_2026-11-02.md`](INTEGRATION_2026-11-02.md) | The merge/audit/fix record for v0.3.0 | archived |
| ⧗[`docs/refoundation/phase2/EVIDENCE_CORE_V1.md`](refoundation/phase2/EVIDENCE_CORE_V1.md) | Append-only `event_revision` ledger + versioned migrations; **and its explicit non-guarantees** | draft (#35) |
| ⧗[`docs/governance/GOVERNANCE.md`](governance/GOVERNANCE.md) | State source, gates, `PROJECT_STATE.yaml` rules | draft (#32) |
| ⧗[`docs/governance/DATA_LICENSES.yaml`](governance/DATA_LICENSES.yaml) | Per-source licence and storage permission register | draft (#32) |
| ⧗[`docs/governance/BRANCH_PROTECTION_PLAN.md`](governance/BRANCH_PROTECTION_PLAN.md) | What protection is intended — **not yet enabled** | draft (#32) |
| ⧗[`PROJECT_STATE.yaml`](../PROJECT_STATE.yaml) | Single hand-edited source of truth; README status and `RESEARCH_INDEX.md` are generated from it | draft (#32) |

**Generated-vs-hand-written rule.** Files carrying `<!-- generated: do not edit by hand -->`
(`DATA.md`, `RESEARCH_INDEX.md`, `report_*.md`, `metrics.json`, `summary.csv`, `dashboard.html`,
`report.html`) are outputs. Edit the generator or `PROJECT_STATE.yaml`, never the output. ⧗`tools/governance/gen_views.py --check` fails a hand edit.

---

## 4. Audit and experiment archive

Everything here is historical. **Archived documents are immutable**: if an audit was wrong, write a
new document that cites and corrects it; do not rewrite the record. No evidence has been deleted or
moved by REFOUNDATION-003.

### 4.1 Phase 0 — governance MVP ⧗ (draft, PR #32)

| Document | Status |
|---|---|
| ⧗[`docs/refoundation/phase0/GOVERNANCE_MVP.md`](refoundation/phase0/GOVERNANCE_MVP.md) — state source, five local gates, CI draft, acceptance evidence | draft |
| ⧗`docs/refoundation/phase0/_evidence/governance/*` — 24 captured gate runs (pass, and deliberately-failing tamper cases) | archived |

### 4.2 Phase 1 — REFOUNDATION-001 repository audit (2026-11-12)

**Not on `main`.** The full audit set lives on branch `publish/refoundation-001` (28 documents +
evidence). It is preserved deliberately as a branch, not merged, because it describes a repository
state that no longer exists. Read it there:

| Document | What it established | Status |
|---|---|---|
| `docs/refoundation/_FACTS.md` | Verified fact base (PR ledger, branch graph, contradictions) | archived (branch) |
| `docs/refoundation/REPOSITORY_INVENTORY.md`, `BRANCH_PR_AUDIT.md` | What exists, which branch owns it | archived (branch) |
| `docs/refoundation/ARCHITECTURE_AS_IS.md`, `TECHNICAL_DEBT_REGISTER.md` | As-is architecture and debt | archived (branch) |
| `docs/refoundation/DATA_GOVERNANCE_AUDIT.md` | Licences, PIT status, uncommitted data | archived (branch) |
| `docs/refoundation/RESEARCH_ASSET_REGISTER.md` | Study inventory and verdicts | archived (branch) |
| `docs/refoundation/README_REDESIGN_PROPOSAL.md`, `AGENT_COLLABORATION_PROTOCOL.md` | Front-page redesign and the governance mechanisms #32 began implementing | archived (branch) |
| `docs/refoundation/DECISION_REGISTER.md`, `MIGRATION_PLAN.md`, `ARCHITECTURE_TO_BE.md` | Proposed decisions and target design | archived (branch) |

To read it: `git show publish/refoundation-001:docs/refoundation/_FACTS.md`.

### 4.3 Phase 2 — evidence integrity (draft, PRs #34 / #35 / #36)

| Document | What it establishes | Status |
|---|---|---|
| ⧗[`E1B_SOURCE_RECOVERY.md`](refoundation/phase2/E1B_SOURCE_RECOVERY.md) | Per-source verdict on recovering a *public* time: EDGAR **yes**, ClinicalTrials.gov **partial** (date-only, `ACTUAL` only), openFDA **no** — prospective observation only | draft (#36) |
| ⧗`docs/refoundation/phase2/_evidence/e1b/*` | 28 request records with true timestamps + hashes; retrospective and prospective findings kept in separate files | archived (#36) |
| ⧗[`EVIDENCE_CORE_V1.md`](refoundation/phase2/EVIDENCE_CORE_V1.md) | Append-only revision ledger behind `events`; what it guarantees and what it explicitly does not (not tamper-proofing) | draft (#35) |
| ⧗[`README_TRUTH_UPDATE.md`](refoundation/phase2/README_TRUTH_UPDATE.md) | The 10 claim corrections applied to the front page, each with its measurement | draft (#34) |

### 4.4 Phase 3 — documentation and navigation (this change)

| Document | Status |
|---|---|
| [`docs/INDEX.md`](INDEX.md) — this page | draft |
| ⧗[`docs/refoundation/phase3/README_VISUAL_PLAN.md`](refoundation/phase3/README_VISUAL_PLAN.md) — image keep/relabel/replace plan + style rules | draft |

### 4.5 Earlier audit trail (on `main`, pre-REFOUNDATION)

| Document | What it is | Status |
|---|---|---|
| [`docs/research/KIMI_AUDIT.md`](research/KIMI_AUDIT.md) | Independent audit of the research foundation | archived |
| [`docs/research/TKG_ADR.md`](research/TKG_ADR.md), [`docs/research/FORECAST_REGISTRY_ADR.md`](research/FORECAST_REGISTRY_ADR.md) | The two approved ADRs for the research infrastructure | current |
| [`docs/research/TKG_ACCEPTANCE.md`](research/TKG_ACCEPTANCE.md), [`docs/research/FOUNDATION_ACCEPTANCE.md`](research/FOUNDATION_ACCEPTANCE.md) | Acceptance records | archived |
| [`docs/research/TKG_HARDENING_REPORT.md`](research/TKG_HARDENING_REPORT.md), [`docs/research/INTEGRATION_FIXES.md`](research/INTEGRATION_FIXES.md) | Hardening and integration defect records | archived |
| [`docs/research/CHANGEPOINT.md`](research/CHANGEPOINT.md), [`docs/research/DETECTION_DESIGN_REVIEW.md`](research/DETECTION_DESIGN_REVIEW.md), [`docs/research/EVALSTATS.md`](research/EVALSTATS.md), [`docs/research/AUDIT_CYCLE2.md`](research/AUDIT_CYCLE2.md) | Detector design/evaluation record | archived |
| [`docs/PHASE1.md`](PHASE1.md), [`PHASE2.md`](PHASE2.md), [`PHASE3.md`](PHASE3.md), [`PHASE3_AGENT.md`](PHASE3_AGENT.md), [`PHASE3_REGISTRY.md`](PHASE3_REGISTRY.md) | The v0.3–v0.5 engineering phases (superseded as *current* description by this index, kept as record) | archived |
| [`report_en.md`](report_en.md), [`report_zh.md`](report_zh.md) | Generated reports — **snapshot artefacts**, not current claims | archived (generated) |

---

## 5. Canonical-source map (stop the duplication here)

When two documents disagree, the right-hand column wins.

| Fact | Canonical source | Not canonical (trim, don't extend) |
|---|---|---|
| Package version | `pyproject.toml` | any README prose, `CHANGELOG` headers |
| Test count / status | `pytest` output recorded in ⧗`PROJECT_STATE.yaml` + its artefact | hand-typed numbers anywhere |
| Capability status (working/draft/retired) | ⧗`PROJECT_STATE.yaml` → ⧗`RESEARCH_INDEX.md` | README tables, old audit prose |
| Metric definitions | [`METHODS.md`](METHODS.md); contract in [`SCHEMA.md`](SCHEMA.md) | reports, papers |
| Data counts / freshness / DB size | ⧗`DATA.md` (generated) | README attributes, `ROADMAP.md` |
| Data licence / storage permission | ⧗`docs/governance/DATA_LICENSES.yaml` | prose in audits |
| What may not change | ⧗`docs/governance/FROZEN.yaml` | "we won't touch X" in prose |
| Study verdicts | frozen study artefacts + ⧗`RESEARCH_INDEX.md` | `research/STATE.json` (advisory, not canonical) |
| Decision record | [`research/DECISIONS.md`](../research/DECISIONS.md) | ad-hoc rationale in PR bodies |
| Historical audit findings | Phase 1 documents (§4.2), immutable | re-tellings of them |

---

## 6. Maintenance rules for this page

1. **Links only.** If you need to explain something, link to the document that owns the explanation.
2. **No numbers.** A number here would be a third copy. Point at `DATA.md` / `PROJECT_STATE.yaml`.
3. **Status must be earned.** `current` requires the file on `main`; `draft` requires an open PR;
   `archived` means it will not be updated.
4. **Broken links are a gate failure.** ⧗`python tools/governance/check_links.py` must pass; when it
   exists, add `docs/INDEX.md` to its input set.
5. **Move nothing.** Archiving means adding a status, not relocating evidence paths — audit documents
   are cited by SHA and path in other audits.
