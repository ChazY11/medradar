# Project Status — MedRadar

**Single source of truth for "what is this project, what does it actually have, and what is next".**
Update this file in place when status changes; do not create parallel status documents.
Last consolidated: **2026-11-04** (maintenance pass `maintenance/repository-consolidation`, base
`main` = `b2a14c0`). See also [REPOSITORY_AUDIT.md](REPOSITORY_AUDIT.md) for the structure map and
[DATA_ASSET_REGISTER.md](DATA_ASSET_REGISTER.md) for data governance.

---

## 1. What the project is

MedRadar is an **evidence-first research project on early signals in medical technology development**.
It is not a general medical-AI platform, not a commercial forecasting system, and not a validated
prediction product.

**Core question (the only top-level research question):**

> Can publicly observable evidence provide reliable early signals of meaningful changes in medical
> technology development?

**Core research work:** observing technology-development change; multi-source evidence collection;
time and first-observation records; early-signal hypothesis testing; scientific reproducibility.

**Supporting engineering (serves the question, is not the question):** data storage, collection
scheduling, entity mapping, data quality, visualisation, experiment execution.

**Completed exploratory research (evidence assets, not current directions):** the five-firm
early-signal study (S-026/S-027 records), S-028 + Correction 1, S-029, the Market-to-R&D /
horizon-forecasting lane. These do not automatically become the next research direction.

Repository charter: [research/MISSION.md](../research/MISSION.md) · provenance rules:
[research/DATA_PROVENANCE.md](../research/DATA_PROVENANCE.md) · papers: [papers/](../papers/README.md).

---

## 2. Capability status

Four buckets. A capability is only in the first bucket if it exists on `main` and is exercised by the
offline suite.

### Implemented (on `main`, tested)

| Capability | Evidence |
|---|---|
| Public-source collection (openFDA 510(k)/PMA/recall/classification/drugsfda, ClinicalTrials.gov v2, optional SEC EDGAR 8-K) with response cache and resumable stages | `medradar/collect_*.py`, `medradar/http.py`, `medradar/corpus.py`; 375,378 events in the operator store |
| Point-in-time event model (`event_date` / `published_at` / `first_seen_at` / `available_at` / `timestamp_quality`) | `medradar/db.py`, [DATA_PROVENANCE.md](../research/DATA_PROVENANCE.md) |
| Company + track metrics (Gamma–Poisson shrinkage, THI, JS mix shift, first-occurrence novelty) | `medradar/analyze.py`, [METHODS.md](METHODS.md) |
| Report + self-contained dashboard + replay timeline (zero external requests) | `medradar/report.py`, `medradar/dashboard.py`, `medradar/replay.py`, `docs/index.html` |
| Case library + event study + simulated (paper) portfolio with frictions | `medradar/cases.py`, `medradar/eventstudy.py`, `medradar/paper.py` |
| Statistics utilities (block bootstrap, Holm, time splits, power) | `medradar/stats.py` |
| Bitemporal knowledge store with deterministic PIT export | `medradar/tkg/`, [TKG.md](TKG.md), [TKG_INTEGRATION.md](TKG_INTEGRATION.md) |
| Append-only forecast registry with as-of scoring | `medradar/forecast_registry.py`, [FORECAST_REGISTRY.md](FORECAST_REGISTRY.md) |
| Deterministic evidence-citing research agent (demo) | `medradar/research_agent.py`, [PHASE3_AGENT.md](PHASE3_AGENT.md) |
| Offline test suite: 1,074 checks, 3 skipped, ~25 s, no network/keys | `python -m medradar selftest` (verified 2026-11-04) |
| CI on `main` (py3.10/3.11/3.12 + Windows) — green | `.github/workflows/ci.yml` |

### Experimental (on `main`, explicitly unreliable)

- **FDA Advisory Committee calendar** (`medradar/adcom.py`): client-side-rendered rows → parses **zero**
  meetings; returns `status="empty"`/`"source_changed"`; the frontier feed therefore has **no AdCom
  signal** ([DATA.md](DATA.md) marks it experimental).
- **NMPA/China adapter** (`medradar/nmpa.py`): not scraped (HTTP 412 / JS WAF). Requires a manual CSV;
  otherwise every CN value is `null` and says so.
- **LLM filing judge** (`medradar/llm.py`): optional key, heuristic fallback labelled in output. The
  published calibration is a 25-item single-annotator **pilot**, not an accuracy guarantee
  ([CALIBRATION.md](CALIBRATION.md)).
- **Frontier feed** (`medradar/frontier.py`): descriptive monitoring only; `pending_510k_pma_monitoring`
  is explicitly `false`.

### Under validation (draft branches, **not** on `main`)

| Work | Branch / PR | Actual state |
|---|---|---|
| Live Observatory v1 (append-only observation ledger, official-source adapters) | `feat/live-observatory-v1` / [#13](https://github.com/ChazY11/medradar/pull/13) | Ledger operating locally; 400 observations from one discovery sweep; 37 sync runs OK. Draft. |
| Observatory Reliability (durable persistence, verified backups, supervision, 7-day validation) | `feat/observatory-reliability-v1` / [#14](https://github.com/ChazY11/medradar/pull/14) | **`VALIDATION_IN_PROGRESS`**; window 2026-11-03T15:35Z → 2026-11-10T15:35Z, 1 of 28 planned slots executed at audit time. Deployment **`DEPLOYED_LOCAL`**, production **`NOT_DEPLOYED`**. Not signed/notarised. Draft. |
| MedRadar 2.0 product surface (company/radar/analyst/evidence web layer) | `feat/medradar-2.0-mvp` / [#12](https://github.com/ChazY11/medradar/pull/12) | Draft; **CI red** (new pytest-style modules are imported by the `selftest` job, which does not install pytest). |

### Not demonstrated (do not claim)

- Any predictive skill for medical-technology change.
- Any measured lead time / earlier warning from public evidence.
- Better detection from cross-source fusion.
- Relational/graph structure carrying usable signal (S-028 H1 null).
- Point-in-time, human-validated relation networks (S-029 T4/T6 failed).
- Calibrated forecasts (0 matured).
- Production deployment of any continuous service.

---

## 3. Research index

One row per line of work, one canonical entry each. **Status vocabulary is fixed:**

`ACTIVE` · `UNDER_VALIDATION` · `COMPLETED_EXPLORATORY` · `NEGATIVE_RESULT` · `ARCHIVED` ·
`SUPERSEDED` · `FUTURE_CANDIDATE`

Frozen evidence is **not moved**. Corrections are appended and linked from the entry. A study may carry
two statuses (e.g. `COMPLETED_EXPLORATORY / NEGATIVE_RESULT`).

| ID | Line of work | Status | Result (own wording) | Canonical entry (branch) | Correction / superseding doc | Human validation |
|---|---|---|---|---|---|---|
| ES-5F | Five-firm early-signal study | `COMPLETED_EXPLORATORY` / `NEGATIVE_RESULT` | "the phenomenon this study set out to detect does not occur often enough to be measured. The binding constraint is information, not modelling." | [research/studies/early_signal_5firms/](../research/studies/early_signal_5firms/PROTOCOL.md) (`main`, merged as `4627672`) | [PAPER_NEGATIVE_v1.md](../papers/PAPER_NEGATIVE_v1.md); decision log S-005/S-010/S-011/S-031 | **69 packets unlabelled** → `PENDING_HUMAN_REVIEW`; agent pre-adjudication ≠ human truth |
| S-026 | Independent review record of the published head | `ARCHIVED` | "Publication approved on that basis"; procedural, "not peer review of the science" | [STUDY_DECISIONS.md](../research/studies/early_signal_5firms/STUDY_DECISIONS.md) §S-026 (`main`) | — | n/a |
| S-027 | Publication record (PR #6 → `4627672`) | `ARCHIVED` | PR #6 merged with 5/5 CI green on the merged head | [STUDY_DECISIONS.md](../research/studies/early_signal_5firms/STUDY_DECISIONS.md) §S-027 (`main`) | — | "Target B still does not exist" |
| S-028 | Temporal company–technology graph early signals | `COMPLETED_EXPLORATORY` / `NEGATIVE_RESULT` (conditionally sealed; **not** confirmatory) | ΔAP −0.00609, both clustered CIs include 0, 0/3 windows exclude 0 → no improvement detected | **Branch only** — `research/studies/graph_early_signal_s028/RESEARCH_QUESTION.md` on `research/s028-temporal-graph-early-signal`; [PR #15](https://github.com/ChazY11/medradar/pull/15) | **S-028-CORRECTION-1**: `CORRECTION_REPORT_ZH.md`, `STATISTICAL_REVIEW_CORRECTION.md`, `RANDOMISATION_DEFECT_ANALYSIS.md`, `G2_CORRECTION_RESULTS.md`, `TEMPORAL_LEAKAGE_AUDIT_CORRECTION.md`, `FALSE_POSITIVE_CASE_REVIEW.md`, `LIMITATIONS.md`, `artifacts/correction_round_1/` | Sealed as exploratory only; 5 conditions for confirmatory listed and unmet |
| S-029 | Evidence-based temporal relation reconstruction | `COMPLETED_EXPLORATORY` / `NEGATIVE_RESULT` — **`NO-GO FOR PREDICTION`** | "the relations are reconstructable and individually traceable, but they are not point-in-time evidence and they are not human-validated" | **Branch only** — `research/studies/relation_network_s029/RESEARCH_QUESTION.md` on `research/s029-evidence-based-relations`; [PR #16](https://github.com/ChazY11/medradar/pull/16) | `NEGATIVE_FINDINGS.md` NF-1…NF-18; `artifacts/independent_review.json` (`READY_WITH_CONCERNS`) | **`HUMAN_VALIDATION_PENDING`** — 102-row worksheet, 0 labelled; no precision/recall may be quoted |
| M2RD | Market-to-R&D / Reverse R&D v1+v2 + Horizon nowcasts | `COMPLETED_EXPLORATORY` / `NEGATIVE_RESULT` | "No added source produces a statistically detectable ranking gain"; continuation is "mostly persistence" (Δ +0.0022, 95% CI [−0.032, +0.037]) | [REVERSE_RD.md](REVERSE_RD.md), [PHASE1.md](PHASE1.md), [PHASE2.md](PHASE2.md) (`main`) | `experiments/reverse_rd_v2/REPORT.md`; [RESULTS/README.md](../research/RESULTS/README.md) R1–R7 | Patents not collected (key); procurement not PIT-usable |
| TKG | Bitemporal knowledge store + PIT export | `ACTIVE` (infrastructure; no scientific claim) | as-of queries never return a fact known after the cutoff | [TKG.md](TKG.md) (`main`) | [TKG_HARDENING_REPORT.md](research/TKG_HARDENING_REPORT.md) | Knowledge clock = backfill time, not historical publication time |
| FR | Immutable forecast registry + continuous cycle | `UNDER_VALIDATION` | "25 genuine prospective forecasts registered, none matured" | [FORECAST_REGISTRY.md](FORECAST_REGISTRY.md) (`main`) | [research/FORECAST_REGISTRY_ADR.md](research/FORECAST_REGISTRY_ADR.md) | Earliest windows close 2027-10; calibration `insufficient_matured_forecasts` |
| DETECT | Change detection + entry clustering | `COMPLETED_EXPLORATORY` / `NEGATIVE_RESULT` | simple baseline not beaten at a matched false-alarm budget; entry clustering closed as null | [RESULTS/README.md](../research/RESULTS/README.md) (`main`) | `research/DECISIONS.md` retractions | One promotion `PENDING_SIGNOFF` |
| CYC2 | Coverage → power on 200-entity cohort | `COMPLETED_EXPLORATORY` | "detection rather than earlier warning" | [CYCLE2_DESIGN.md](../research/CYCLE2_DESIGN.md) (`main`) | `experiments/cycle2_coverage/REPORT.md` | 51-parent panel underpowered |
| PAPERS | Three draft papers + machine-checked claim maps | `ARCHIVED` | "draft v1: not submitted, no venue claimed" | [papers/README.md](../papers/README.md) (`main`) | `CLAIMS*.json` verified by `verify_claims.py` | Peer review not sought |
| OBS/REL | Live Observatory + Reliability programme | `UNDER_VALIDATION` | `VALIDATION_IN_PROGRESS`, `DEPLOYED_LOCAL`, `NOT_DEPLOYED` | branch only, [PR #13](https://github.com/ChazY11/medradar/pull/13) / [#14](https://github.com/ChazY11/medradar/pull/14) | `docs/RELIABILITY_ACCEPTANCE.md`, `CONTINUOUS_VALIDATION_PROTOCOL.md` | Validation ends 2026-11-10T15:35Z; must be reported as it actually ends |
| FRONTIER | Frontier radar lane | `ACTIVE` (descriptive) | "public-source monitoring, not a pending-application oracle" | [METHODS.md](METHODS.md), `medradar/frontier.py` (`main`) | PR #1 is `SUPERSEDED_CANDIDATE` (conflicting, mostly already on `main`) | AdCom sub-source returns 0 meetings |
| — | S-030 or any new study number | `FUTURE_CANDIDATE` — **not started** | — | — | Not permitted until the core question is re-scoped with data availability and human-review capacity | — |

**Naming collision to be aware of:** `research/studies/early_signal_5firms/STUDY_DECISIONS.md` uses
`S-001…S-033` as *decision-log* IDs, which collides with the *programme* study IDs `S-028`/`S-029`. The
same string means different objects. Do not renumber frozen records; cite the file plus the ID.

**Visibility caveat:** everything after ES-5F lives on unmerged draft branches. A reader of `main`
cannot see S-028, S-029, the Observatory or the product surface. That is why this index carries branch
annotations.

---

## 4. Open pull requests and branches

Rule: **no PR is closed, merged or force-pushed as part of repository maintenance.** The table is
advice for a human.

| PR | Head → Base | Draft | CI | Disposition |
|---|---|---|---|---|
| [#12](https://github.com/ChazY11/medradar/pull/12) MedRadar 2.0 MVP | `feat/medradar-2.0-mvp` → `main` | yes | **red** (4/6: `selftest` imports pytest-only modules; `ci.yml` does not install the `dev` extra) | `DRAFT_ACTIVE` — fix `ci.yml` install (`.[dev]`) or make `selftest` skip pytest modules, then re-run |
| [#13](https://github.com/ChazY11/medradar/pull/13) Live Observatory v1 | `feat/live-observatory-v1` → `feat/medradar-2.0-mvp` | yes | green (6/6, against a non-`main` base) | `DRAFT_ACTIVE` — retarget to `main` only after #12 merges |
| [#14](https://github.com/ChazY11/medradar/pull/14) Observatory Reliability | `feat/observatory-reliability-v1` → `feat/live-observatory-v1` | yes | green (6/6) | `DRAFT_ACTIVE` — blocked by its own 7-day validation, which ends 2026-11-10 |
| [#15](https://github.com/ChazY11/medradar/pull/15) S-028 | `research/s028-…` → `feat/observatory-reliability-v1` | yes | green (6/6) | `RESEARCH_ARCHIVE` — preserve as evidence; "do not merge without human scientific review" |
| [#16](https://github.com/ChazY11/medradar/pull/16) S-029 | `research/s029-…` → `feat/observatory-reliability-v1` | yes | green (6/6) | `RESEARCH_ARCHIVE` — `NO-GO`; `HUMAN_VALIDATION_PENDING`; remove committed `__pycache__` before any merge |
| [#1](https://github.com/ChazY11/medradar/pull/1) Frontier device radar | `feat/frontier-device-radar` → `main` | no | 154 commits behind, `CONFLICTING`; most content already on `main` | `SUPERSEDED_CANDIDATE` — **needs human decision** to close |

**Merge order if these are ever merged:** `#12 → #13 → #14 → {#15, #16}`. #15 and #16 are siblings on
the same base with disjoint file sets. Each PR's green CI was run against its own stack base, not
against `main`, so after any merge every remaining PR needs a retarget and a fresh run.

Branches carrying unique work (do **not** prune): `research/temporal-knowledge-graph`,
`research/early-signal-ai-review`, `research/full-history-v1`. All other stale branches are ancestors of
`main` or content-identical to it; deleting them is a human decision and is out of scope here.

There is **no branch protection and no required check** on `main`: CI runs on a docs-only PR, but nothing
blocks a merge. Do not mistake a green run for a gate.

---

## 5. Data

One operational database, one frozen research dataset, one append-only observation ledger. The
distinction matters and is documented in [DATA_ASSET_REGISTER.md](DATA_ASSET_REGISTER.md). Short
version:

- **Operational**: `data/medradar.sqlite` — 1.37 GB, 375,378 events (1966–2026), sha256 `445807ca…`
  (local only, not in git).
- **Historical research / frozen experimental**: `research.sqlite` — 289 MB, sha256 `dd241bfe…`
  (local only; **absent from the repository**).
- **Observation ledger**: `data/observatory/observatory.sqlite` — 1.96 MB, append-only.
- **Backup archive**: one verified bundle under `data/observatory/backups/`.

No database file is tracked on any branch.

---

## 6. Roadmap (the only current roadmap)

Three priorities, no new study numbers.

### Priority 1 — Project clarity (this consolidation)

Make the repository state, research status and data assets explicit and maintainable. Concretely:
accurate GitHub front page, one status document, one data-asset register, one repository audit, and no
capability branch growing while its status is unclear.
**Exit condition:** a first-time reader understands within five minutes what is researched, what works,
what was found, what is unproven, how to reproduce, and what comes next.

### Priority 2 — Observatory reliability

Keep the real observation record and its backup chain sustainable and auditable **without new
infrastructure**. The seven-day continuous validation must run to its end and be published as it
actually ended — including a failure, or an incomplete run. No retrofitting.
**Exit condition:** a documented validation outcome (whatever it is) plus a verified backup/restore path
that has been exercised on the current bundle, and an explicit decision about offsite storage.

### Priority 3 — Core research validation

Return to the core question: *can public information provide genuine early signals of medical
technology change?* With the current evidence the honest answer is "not demonstrable with the coverage
we have". The next step is a small, traceable case design — not a new large research engineering build.

### The five questions a roadmap must answer

| Question | Answer |
|---|---|
| What is the single research question? | Can publicly observable evidence provide reliable early signals of meaningful changes in medical technology development? |
| Which existing capability genuinely supports it? | The point-in-time event store plus the frozen-protocol study framework and the offline verification suite. Nothing else is load-bearing yet. |
| What is the most critical blocker? | **Information, not modelling**: the event rate at firm × track × quarter is too low to measure the phenomenon, and human adjudication of the candidate packets is incomplete. |
| What work can stop? | New graph/GNN work, new data-source expansion, new study numbers, further product-surface build-out on draft branches, and any claim of prediction before validation. |
| What is the next minimal executable research action? | **Finish the 69-packet human adjudication** of the five-firm study (worksheet + validator already exist on `main`), then re-run the frozen gates on human labels and publish the result as-is. |

Nothing else should be started before that action completes. In particular: do not open S-030, do not
train new models, do not extend collection scope.

---

## 7. Open human decisions

1. **69-packet adjudication** (ES-5F) — who reviews, and when. Blocks any detector scoring or lead-time
   claim. Worksheet: `research/studies/early_signal_5firms/HUMAN_REVIEW_WORKSHEET.csv`.
2. **S-029 human validation** (102 rows) — required before the relation layer can be used for anything.
3. **PR #12 CI fix** — install `.[dev]` in the two legacy `ci.yml` jobs (or teach `selftest` to skip
   pytest-style modules); the product layer cannot be reviewed while its CI is red.
4. **PR #1** — close as superseded, or rebase the residue. No science depends on it.
5. **Branch cleanup** — delete merged/superseded refs only; keep the three branches carrying unique
   work. Requires a human because it is irreversible on GitHub.
6. **Seven-day validation outcome** (PR #14) — publish the actual result after 2026-11-10, including any
   gaps, and state whether production/offsite hosting is authorised (currently not, and not purchased).
7. **S-028 sealing** — confirm the corrected wording is the version of record; the original report must
   remain marked `INVALIDATED` where Correction 1 says so.
8. **Licence detector mismatch** — decide whether to move the data notice out of `LICENSE` so GitHub
   reports "MIT" (currently "Other"). Not changed in this pass: it edits legal text.
9. **S-029 raw payloads** — decide retention/redistribution posture for the committed per-query raw
   responses (`data/raw/*.json.gz`) and the tracked `__pycache__`, before that branch is ever merged.
10. **Uncommitted local work** — `research/studies/early_signal_5firms/HUMAN_REVIEW_WORKSHEET.csv`
    carries uncommitted owner edits, and the `study-early-signal` worktree has uncommitted changes.
    Left untouched; owner decides whether to keep them.
