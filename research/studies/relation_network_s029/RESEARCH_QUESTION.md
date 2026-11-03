# S-029 研究问题与仓库审计 / Research Question and Repository Audit

**Study:** `relation_network_s029` · **Branch:** `research/s029-evidence-based-relations`
**Base commit:** `d05fc81` (`feat/observatory-reliability-v1`, PR #14) — chosen as the minimal
baseline that contains the ClinicalTrials.gov and Europe PMC data-access code and contains **no**
S-028 research artefacts, so this PR cannot alter or re-litigate PR #15.
**Frozen S-028 artefacts:** untouched, read-only (`D:\DEPPSKK\medradar\research\studies\graph_early_signal_s028`).
**Execution date:** 2026-11-04 (UTC timestamps in every artefact).

---

## 1. The scientific question

> Can we reliably reconstruct observable, time-resolved relationships among medical-technology
> companies, research institutions, clinical studies, scientific publications and regulatory
> activity — from real, verifiable public evidence?

S-029 answers this **before** any model is fitted. It deliberately does not train a GNN, does not
optimise a predictive metric, and does not claim to have discovered a knowledge-diffusion law.
The deliverable is a measured evidence base plus a documented set of limits.

### RQ1 — relation observability

Which company–institution–study relations can be identified *reliably* in currently available public
sources, and with which roles? Sub-questions that are answered with numbers in this study:

* which source fields state a relation directly (structured) versus state it in free text;
* how much of the target population a name-based search actually reaches;
* how many returned records are name collisions rather than the entity.

### RQ2 — temporal quality

For each relation, what can be known about (a) when the event happened, (b) when the source published
it, (c) when MedRadar first observed it, (d) the period it is valid? Three clocks are never
interchanged; where a clock does not exist, it is `null`, not imputed.

### RQ3 — cross-source consistency

Can the same company, institution or study be linked across ClinicalTrials.gov, Europe PMC, OpenAlex
and Crossref? The study separates: same entity / probably same entity / same name different entity /
participating in the same project / merely active in the same field.

### RQ4 — sufficiency

Is the relation layer good enough to support a later time-ordered prediction study (S-030)? The
answer is a verdict from a pre-registered rule (`GO_NO_GO_CRITERIA.md`), not a judgement call.

---

## 2. What S-028 established, and what S-029 inherits

Read in full before any collection: `NEGATIVE_RESULTS.md`, `LIMITATIONS.md`,
`RELATION_AND_TIME_EVIDENCE_AUDIT.md`, `CORRECTION_REPORT_ZH.md` in the S-028 directory.

| S-028 finding | Consequence designed into S-029 |
|---|---|
| Graph features gave no out-of-sample AP gain (ΔAP −0.006, CI spanning zero), and the study's own power analysis was later found to be mis-stated (16.3% power for the effect it reported) | S-029 does not fit a predictive model at all. It measures the relation layer first. |
| The graph rested on **12.1%** of the event lane (3,833/31,802) | S-029 measures coverage explicitly per source and per relation family, and reports unmapped records instead of dropping them. |
| `first_seen_at` had **one value** for all 55,090 historical rows; only **6/400** observatory records had a genuine ≤1-day lag | S-029 records a real collection timestamp and computes `observed_lag_days` per claim, then reports the share that could support `ACTUAL_OBSERVATION`. |
| Entity mapping carried hindsight: **84** events predate the acquisition of the subsidiary they were credited to; 44.11% of one company's events came from acquired aliases | S-029 checks every subsidiary string against a date-validity test and **keeps the anachronism as a measured quantity** (`NEGATIVE_FINDINGS.md` NF-4). |
| There was **no** company↔company edge, no institution entity, no author/paper data | S-029 collects institution and publication evidence from a second and third source, and states which relations remain impossible. |
| "统计共现不是知识转移的证据" | Co-affiliation is emitted as its own predicate with an explicit `interpretation_limit`; no cooperation edge is ever derived from it. |
| A literature claim was wrongly negated because a keyword search missed the paper (Correction 1) | Every citation in `LITERATURE_REVIEW.md` is verified against Crossref/Europe PMC/OpenAlex metadata; "not found in our verified corpus" replaces "does not exist". |

---

## 3. Pilot scope (deliberately small)

Five companies only, with historical legal identity treated as a research object:

Medtronic · GE HealthCare · Philips · Dräger · Mindray

Three relation families (definition and role semantics in `RELATION_ONTOLOGY.md`):

* **A** clinical-study participation — ClinicalTrials.gov v2: lead sponsor, collaborator, responsible
  party, site facility, registry references to publications;
* **B** publication affiliation — Europe PMC: author affiliation, company/institution co-affiliation,
  MeSH topic, declared grant funder;
* **C** publicly confirmed organisational cooperation — **reserved, zero collected**; no source in
  this round meets the evidential bar (see `NEGATIVE_FINDINGS.md` NF-1).

Data sources: ClinicalTrials.gov API v2, Europe PMC REST, OpenAlex (bounded), Crossref, ROR.
All keyless/free; no purchased database, no cloud compute, no GPU, no new always-on service.

---

## 4. Method in one paragraph per phase

**Phase 0 — evidence feasibility audit.** Search-recall probe across name variants
(`query_recall_probe.json`), source composition audit, ontology freeze, pre-registered decision
thresholds, verified literature review, company identity register from primary sources.

**Phase 1 — relation reconstruction pilot.** Bounded collection with every response stored gzipped
and hash-addressed; extraction that preserves raw strings; deterministic identity mapping with a
date test; claims + evidence + rejects written as JSONL. Failures (unmapped, ambiguous, collided,
anachronistic, non-publication records) are data, not noise.

**Phase 2 — quality and feasibility evaluation.** Coverage, entity resolution, temporal quality,
relation quality, cross-source agreement, network structure; a ~100-row human review worksheet with
all human fields empty; and the pre-registered verdict.

---

## 5. What would make this study wrong, and how it is guarded

| failure mode | guard |
|---|---|
| Counting a substring match as a company | word-boundary matching; measured collisions ("Colle(ge Healthcare)", "Oran(ge healthcare)") are recorded as rejects |
| Counting an author surname as a company | email-domain vs email-local-part vs personal-name classification; Dräger is the stress test (78% rejected) |
| Treating a subsidiary string as the parent in an earlier period | date-validity test against the entity register; anachronisms counted |
| Reporting "no relation" when the search simply could not reach it | variant recall probe; all zero-hit and unmapped queries reported |
| Presenting a backfilled observation as point-in-time | per-claim `observed_lag_days` + `time_basis`; ACTUAL_OBSERVATION count reported |
| Presenting machine labels as human truth | human worksheet fields forced empty; `HUMAN_VALIDATION_PENDING`; no precision/recall claim |
| Silently fixing an inconvenient number | `s029_12_verify_report.py` recomputes every reported figure from the artefacts |

---

## 6. Repository audit (Task 1 of the brief)

* Repository: `https://github.com/ChazY11/medradar`, local main checkout `D:\DEPPSKK\medradar`
  (current checkout was on `research/s028-temporal-graph-early-signal`, 4 commits ahead of
  `feat/observatory-reliability-v1`).
* Work is done in an isolated git worktree `D:\DEPPSKK\worktrees\s029-relations` so that the S-028
  branch, its frozen artefacts, and its pre-existing uncommitted modification
  (`research/studies/early_signal_5firms/HUMAN_REVIEW_WORKSHEET.csv`, a line-ending-only diff that
  was already present before this session) are not touched.
* Branches that contain the data-access adapters (`medradar/observatory/adapters/{ctgov,europepmc,sec_edgar}.py`):
  `feat/live-observatory-v1`, `feat/observatory-reliability-v1`, `research/s028-…`. Only the first two
  have no S-028 artefacts; `feat/observatory-reliability-v1` is the newest of them → chosen as base.
* The frozen study database (`medradar/data/research.sqlite`, 289 MB, sha256 `dd241bfe…`) is **not**
  written to; the Live Observatory ledger is opened read-only by the temporal auditor.
* Nothing is merged, no existing PR is modified, no scheduled collection is stopped.

---

## 7. Deliverables map

| file | content |
|---|---|
| `RESEARCH_QUESTION.md` | this document |
| `RELATION_ONTOLOGY.md` | entities, predicates, roles, statuses, four clocks, conflict rules |
| `GO_NO_GO_CRITERIA.md` | pre-registered thresholds (written before measurement) |
| `LITERATURE_REVIEW.md` | verified prior work + closest-work comparison (lit reviewer) |
| `SOURCE_AUDIT.md` | what each source can and cannot state (measured) |
| `ENTITY_HISTORY_REGISTER.md` | corporate identity over time with primary sources (entity auditor) |
| `ENTITY_RESOLUTION.md` | measured mapping error rates (entity auditor) |
| `TEMPORAL_PROVENANCE.md` | the four clocks, measured (temporal auditor) |
| `RELATION_PILOT.md` | the collected evidence set, described |
| `DATA_QUALITY_REPORT.md` | A–D quality metrics |
| `NETWORK_FEASIBILITY.md` | E: structure, and what it can/cannot support |
| `HUMAN_REVIEW_PROTOCOL.md` + `S029_HUMAN_REVIEW_WORKSHEET.csv` | ~100 stratified candidates, human fields empty |
| `NEGATIVE_FINDINGS.md` | every negative and every self-correction, with the measurement |
| `PHASE_REPORT_ZH.md` | the Chinese phase report and the formal verdict |
| `REPRODUCE.md` | exact commands, environment, expected outputs |
