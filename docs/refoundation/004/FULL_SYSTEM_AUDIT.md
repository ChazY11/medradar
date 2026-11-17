# REFOUNDATION-004 - Full system audit

Status: audit of the real repository, performed before and during the repairs. Every number in
this document was produced in this session; commands and raw artefacts are cited so a reader can
re-run them. Nothing here is projected from documentation.

- Audit date: 2026-11-18
- Repository: https://github.com/ChazY11/medradar (single repository, many worktrees)
- Working copy for this round: branch refoundation/004, based on feat/radar-001-live-intelligence-graph (PR #54, HEAD 14eaf61)
- Reference data: a read-only copy of the production-shaped ledger (data/radar/radar.db from that worktree, 8,593 observations, copied to D:/DEPPSKK/data004-baseline/)
- Environment: Windows host, Python 3.12.10, Node 24.18, SQLite (WAL), no access to the production server

## 0. What this round found in one paragraph

The code is not one system. It is three partially overlapping systems in one repository: a legacy
market/trading research lane, an FDA-snapshot product workbench, and the RADAR-001 live
intelligence lane. The newest lane has good bones - an append-only observation ledger, an explicit
taxonomy, a bitemporal graph, a documented source policy - but its one relevance label carried
eight different judgements at once, so 83.4% of the ledger was "HIGH_RELEVANCE" and the default
feed contained official Philips imaging launches next to genuine oximetry research. The quality
numbers the previous round published were measured on a self-labelled 38-item set with a 14-day
window while the product used 30 days, and the report contradicted its own JSON. The fixes below
are therefore structural: a dimension-separated assessment engine, an actually append-only
admission history, an evaluation harness whose prose is generated from its own JSON, identifier-
based work identity, precision-aware time display, and a test file that fails by name if any of
the reported defects returns.

## 1. How the audit was done

| Step | Method | Artefact |
| --- | --- | --- |
| Repository state | git refs, worktrees, gh pr list, commit log | section 2 |
| Architecture map | AST import graph, reachability from declared entry points, line/function counts | section 3 |
| Complexity | AST cyclomatic complexity and function length for 512 modules | D:/DEPPSKK/data004-baseline/complexity-before.json |
| Data reality | read-only SQL on the ledger copy: counts, date coverage, per-source tiers, feed contents | section 5 |
| Defect reproduction | ran the production classifier on the QA-002 case classes and on the sample | sections 6, 7 |
| Quality baseline | frozen fixed-seed sample, labelled before rule work; old rules measured | docs/refoundation/004/quality/QUALITY_BEFORE.md |
| Tests | full pytest suite plus a per-file baseline with timings | D:/DEPPSKK/data004-baseline/tests-per-file.txt |

## 2. Git and PR archaeology

The repository is a single git repository used by many worktrees (67 at the time of the audit).

- origin/main is at 86311b1 ("Merge pull request #41"), which is the published research front page
  and the SCIENCE-001 experiment. main does **not** contain the product or the radar lane.
- The current product line is a nine-deep draft stack, all open, none merged:
  #46 PRODUCT-001 -> #47 PRODUCT-002 -> #48 PRODUCT-003 P0 -> #49 PRODUCT-003 ->
  #50 DATA-001 -> #51 DATA-002 -> #52 DATA-003 -> #53 PRODUCT-004 ->
  #54 RADAR-001 (base: feat/product-004-intelligence-workbench, head 14eaf61, adds QUALITY-001 and
  HOTFIX-001 on top).
- The stack is strictly linear; each PR's base is the previous PR's head. PRs #38/#39/#40/#41 were
  merged to main earlier and are not part of the product line.
- 30+ further open drafts exist for research lanes (PHOENIX, S-028/S-029/S-031, ATLAS, HORIZON,
  CONVERGENCE, local-LLM, AI evidence review). Several are marked "research, do not merge" in
  their titles. They are historical research evidence and were left untouched.
- Deployment, as recorded by the documents (not verified from this host):
  RADAR deployed commit d91d647 (QUALITY-001 migration) under /srv/medradar/radar/releases,
  data at /srv/medradar/data/radar; the FDA workbench is a separate worktree /srv/medradar/app at
  1bdb1c3 (PRODUCT-003), serving 127.0.0.1:8787. The host is a Tencent Cloud Lighthouse instance.
  **Deployment state is NOT VERIFIED in this round**: no credentials, no SSH, and this audit did
  not touch any production artefact.

Why this matters for the audit: main cannot be used as "the product", README describes the research
project, and the only product state is the tip of a never-merged draft stack. Any repair must keep
the stack's base intact and add one more reviewable layer rather than rebasing nine drafts.

## 3. Architecture map (measured)

Reachability from the declared entry points (medradar.__main__, product.api, radar.api,
data_pipeline.cli, radar.cli, product.review.cli, tkg.__main__), AST based, then checked by hand for
dynamic imports: **87 of 162 packages/modules in medradar/** are reachable from an entry point
(52,664 lines); **75 modules (20,558 lines) are not** reachable from any entry point. The largest
unreachable ones are the research/forecast lanes (`medradar.research_agent` 1,900 lines,
`intelligence.evalstats` 1,455, `forecast_registry` 1,271, `corpus` 1,242,
`calibration` 1,090, `collect_device` 1,064, plus the intelligence/* feature and model modules,
`nmpa`, `adcom`, `studies/*`). They are reachable from scripts and from `python -m medradar
collect/analyze/report/trade`, which is the legacy lane, so "unreachable" here means "not reachable
from the product/intelligence entry points", not "dead".

The three lanes:

| Lane | Entry points | Authoritative store | What it is for |
| --- | --- | --- | --- |
| Legacy market/research (2019-2022 lineage, PRs #1-#25) | `python -m medradar collect/analyze/report/trade/live/replay/cases/products/audit/stats` | `data/medradar.sqlite` (`medradar/db.py`: events, prices, signals, runs) | FDA approvals + market signals + paper-trading + research studies. Its front page is docs/dashboard.html (3.3 MB) |
| FDA snapshot product (PRODUCT-001..004) | `python -m medradar web` -> `medradar.product.api` | a hash-addressed snapshot under `medradar/product/snapshot/` or `data/product`, built by `medradar/data_pipeline/*` from openFDA 510(k)/PMA/recall bulk files | company/device evidence workbench: identity resolution, review ledger, briefs, compare, export |
| Live intelligence radar (RADAR-001, DATA-001..003) | `python -m medradar radar ...` -> `medradar.radar.cli`, `radar.scheduler`, `radar.api` | `data/radar/radar.db` (observation ledger) + `data/radar/graph.db` (derived technology graph) | continuous multi-source monitoring intelligence: adapters, ledger, taxonomy mapping, admission, graph, feed |

The three lanes share vocabulary (device, topic, organization, publication) but not a data contract.
That is the single largest structural debt in the repository: the same question ("what do we know
about Philips?") has three different answers depending on which store is asked, and the UI has two
different front doors (`/api/events` from the snapshot, `/api/radar/feed` from the ledger).

### 3.1 Subsystem inventory

| Subsystem | Current responsibility | Entry | Facts it owns | Depends on | History | Issues found | Strategy |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Radar adapters (`radar/adapters/*`) | fetch openFDA 510(k)/PMA, PubMed, Crossref, Philips, Dräger, GE news | `radar.cli`, `radar.scheduler` | raw source responses -> RawRecord | http, taxonomy, records | added RADAR-001 | PubMed/Crossref applied a second relevance gate before storage (fixed this round); Dräger parses no article date (31 dateless records); Crossref watermark can jump to a future issue date | REFACTOR (fixed gate; date parsing open) |
| Observation ledger (`radar/ledger.py`, 1,721 lines) | append-only observation/version/change history + mutable head projection + admission decisions | adapters, engine, api | observation identity, first_observed_at, versions, changes, fails, identifiers, admission decisions | records, data_pipeline.lock | swapped from the Observatory ledger in RADAR-001 | `observation_admission` was INSERT OR REPLACE keyed by (obs, version) so history was overwritten (fixed this round: append-only v3 + derived current projection); feed deduplicated by title string (fixed: DOI/PMID work_key) | KEEP (core asset), REFACTOR done |
| Normalisation (`radar/records.py`, `data_pipeline/normalize.py`) | canonical record shape, time precision, identifiers, hashing | adapters, ledger | record contract | util | reused from Observatory/DATA-001 | two normalisation paths (radar RawRecord vs data_pipeline rows) | MERGE later; documented |
| Identity resolution (`radar/taxonomy.py`, `product/identity.py`) | org alias resolution (exact/prefix, no fuzzy) and applicant registry | classify, product dataset | organization ids, alias confidences | config | taxonomy from RADAR-001, registry from PRODUCT-002 | two org registries (`config/radar/organizations.json`, `medradar/product/identity/organizations.json`, 454 KB) with different ids | MERGE later (single registry) |
| Relevance admission (`radar/relevance.py` -> `radar/assessment.py`) | decide what is monitoring intelligence | engine.apply_admissions, api | admission decisions | taxonomy | QUALITY-001 added one tier; REFOUNDATION-004 replaced with 8 dimensions + decision | one tier carried 8 meanings; 83.4% of the ledger was HIGH; official press granted relevance; journal text used as subject evidence; non-medical domains admitted | REFACTOR done |
| Evidence + graph (`radar/graph.py` 1,100 lines, `evidence_core/*`, `tkg/*`) | bitemporal assertions with evidence ids; entity/technology graph | engine, api | assertions, node detail | ledger, taxonomy | RADAR-001 + REFOUNDATION-002 evidence core | graph materialisation is a derived projection with invalidation; TKG store is a separate older implementation | KEEP radar graph; ARCHIVE tkg for the product path |
| Product dataset (`product/dataset.py` 1,365 lines) | load + index the FDA snapshot; attribution, coverage, metrics | product.api | product dataset (immutable per snapshot) | identity, attribution | PRODUCT-001..004 | one 294-line/cc 94 loader; N+1-ish derived indexes; a second store next to the radar ledger | KEEP, REFACTOR hotspot |
| Product API (`product/api.py`, create_app 949 lines, cc 240) | 48 routes: dataset + review + export + radar? | uvicorn | HTTP contract | dataset, review, radar? | PRODUCT-001..004 | one giant function holds all routes and policy; hotspot #1 in the repo | REFACTOR hotspot (not done this round) |
| Radar API (`radar/api.py` build_router 428 lines, cc 74) | feed, detail, facets, graph, pipeline, health | web UI | HTTP contract | ledger, graph | RADAR-001/QUALITY-001 | feed query cost grew; candidate for extraction | REFACTOR hotspot |
| Data pipeline (`data_pipeline/*`) | openFDA bulk sync -> validated snapshot -> atomic publish | data_pipeline.cli, systemd timer | snapshots, change ledger, source state | openfda, validator, lock, publisher | DATA-001..003 | `_sync_locked` 412 lines/cc 105; snapshot activation machinery is sophisticated and load-bearing | KEEP |
| Frontend (`web/src`) | 20-ish pages: feed, graph, topics, organizations, devices, review, compare, briefs, data status, auth | served by product.api | none (projection) | API | PRODUCT-001..004, QUALITY-001 | month-precision dates rendered as midnight UTC (fixed); dimension chips added; one 568 KB bundle | KEEP |
| Scheduling/ops (`radar/scheduler.py`, `data_pipeline/status_service.py`, deploy/) | watch loop, source due/retry, health, backups | systemd | run state | ledger, lock | RADAR-001/DATA-002 | single-writer lock reuse is good; no unified health across the two services | KEEP |
| Quality evaluation (`scripts/evaluate_relevance.py`, `config/radar/quality_eval.json`) | measure relevance rules | manual | labels, metrics | relevance | QUALITY-001 | 14-day window vs 30-day product; docs/JSON disagree; no per-class metrics; no N/A handling; labels by the same agent that wrote rules | REWRITTEN this round |
| Research/legacy (`report.py` 4,145 lines, `replay.py` 2,842, `families.py`, `intelligence/*`, `studies/*`, `experiments/`, `research/`) | historical studies, paper trading, forecasts, dashboards | legacy CLI/scripts | research data | db | PRs #1-#45 | 75 modules not reachable from product entry points; mixed evidence standards; cannot be deleted (it is the project's research record) | ARCHIVE (freeze, document, stop extending) |

## 4. Measured complexity

Before this round (HEAD 14eaf61) and after (this branch), same AST script
(`D:/DEPPSKK/data004-baseline/complexity.py`):

| Metric | Before | After |
| --- | --- | --- |
| Python modules (repo) | 510 | 512 |
| Python lines | 152,602 | 154,090 |
| Functions | 5,613 | 5,665 |
| Functions with CC > 10 | 698 | 703 |
| Functions with CC > 15 | 80 | 80 |
| Longest function | product/api.py create_app, 949 lines, CC 240 | unchanged |
| Second | radar/api.py build_router, 428 lines, CC 74 | unchanged |
| Third | replay.py _simulate, 414 lines, CC 74 | unchanged |

Interpretation, stated plainly: **raw size and cyclomatic complexity did not fall.** This round
replaced one overloaded rule module with a larger, better-structured one and added tests, so lines
went up by 1.5%. What did fall is *conceptual* duplication and state ambiguity:

- the judgement now has one implementation (876-line assessment module) instead of a scoring engine
  in relevance.py plus a second pre-storage gate in the adapters (`classify.publication_relevance`);
- relevance.py shrank from 421 to 96 lines and is a facade with no logic;
- the admission table went from "one row per (obs, version), overwritten" to "append-only history +
  one explicit derived projection", so there is now exactly one reader path for the current
  decision;
- an evaluation harness whose report is generated from its own JSON replaces hand-written numbers;
- 14 named regression tests encode the defects, so the cheap way to reintroduce one is blocked.

The remaining hotspots are unchanged and are the honest next targets: `product/api.py create_app`
(949 lines, 48 routes), `product/dataset.py load_dataset`, `data_pipeline/pipeline._sync_locked`,
`radar/graph.technology_map`, `replay.py`. Splitting them mechanically would not reduce complexity;
the audit recommends extracting route groups and the dataset index builder behind existing tests.

## 5. What the data actually looks like

Read-only analysis of the ledger copy (8,593 observations, schema radar-ledger-v2 at copy time):

| Source | Observations | Date facts | Admission (old rules) |
| --- | --- | --- | --- |
| openfda_device | 6,936 | decision_date in event_at; published_at is null by design | 6,936 HIGH (100%) |
| crossref | 1,137 | published/event dates, 4 records with a future issue date (2026-12) | 411 HIGH after v2 rules |
| pubmed | 484 | published date; MeSH terms | mostly clinical, not monitoring technology |
| draeger_official | 31 | **no date at all** (title-only newsroom scrape) | LOW after v2 |
| philips_official | 5 | dates present | LOW after v2 |

The old rules put 7,166 of 8,593 observations (83.4%) in HIGH_RELEVANCE, 873 LOW, 438 REVIEW,
116 IRRELEVANT. A label that is true for five sixths of the corpus cannot inform a feed: the
default 30-day feed was 17 records, of which two were official Philips imaging launches
(HyperVue, UniGuide) and several were clinical prediction papers. The archive view was 6,584
records, almost all of them openFDA clearances.

Two time facts deserve their own line because they corrupt freshness if mishandled:

- openFDA publishes no per-record publication timestamp; the adapter records that fact
  (`published_at_status = not_published_by_source`) and stores the decision date as `event_at`.
  The product must never render the decision date as a publication date.
- Crossref can state a future issue month (a 2026-12 article seen in November). The old feed
  ordered on the raw date, so an ahead-of-print record could top a "last 30 days" view; this round
  excludes source-stated future dates from the "latest" scope and documents the watermark risk.

## 6. Defects found, with evidence

Each item: what was wrong, the evidence, the root cause, and the risk if left alone. Severity is
about product trust, not code aesthetics.

### D1 (critical) One tier carried eight judgements
Evidence: 7,166/8,593 = 83.4% HIGH_RELEVANCE; tier counts above. Root cause: `HIGH_RELEVANCE`
answered source authenticity, medical domain, monitoring relevance, transfer value, entity link,
freshness, importance and confidence simultaneously. Risk: the feed cannot be trusted, and every
downstream count (topics, companies, capabilities) is inflated. Fixed: dimensions + decision
(docs/refoundation/004/ARCHITECTURE_DECISIONS.md ADR-001).

### D2 (critical) Source authenticity substituted for subject judgement
Evidence: `classify_observation` returned HIGH score 10.0 for every mapped press release or
regulatory record; the default feed contained "Philips launches HyperVue" and "Philips launches
UniGuide 3D Live Guidance" (QA-002: 2 of 13). Reproduction: probe script, both are
`HIGH_RELEVANCE vendor_statement`. Root cause: the authoritative-record branch never asked what
the record was about. Fixed: a primary record is DIRECT only if its own subject names a monitoring
device/measurement; an authentic statement about an imaging product is MEDICAL_UNRELATED.

### D3 (critical) Venue text used as subject evidence
Evidence: "Explainable Feature-based Machine Learning for Patient-independent ECG Arrhythmia
Classification" was IRRELEVANT ("the monitored system is not a patient") because its journal is
"International Journal of ... Telecommunications". Root cause: `_text_of` concatenated
journal/container title into the text matched by the non-medical exclusion vocabulary. Fixed:
subject text, venue text, index text and entity text are separate inputs with separate roles; a
venue can only add a positive engineering signal, never a non-medical exclusion.

### D4 (high) Non-medical domains admitted
Evidence (old rules, reproduced): "Wearable sensor-based hand hygiene monitoring in nursing homes"
HIGH; radar target detection, gear-health monitoring, gravitational-wave detection, radar odometry
and CFAR detectors all NEEDS_REVIEW. Root cause: generic device nouns ("sensor", "probe",
"detector") and engineering words ("false alarm", "detector") were sufficient; the non-medical
vocabulary had no aerospace/mechanical/geophysics/IT terms. Fixed: domain vocabulary + a
medical-anchor requirement + a behaviour/workflow branch; 16 regression cases.

### D5 (high) Genuine monitoring evidence rejected
Evidence (old rules, reproduced): "Performance of a novel single-lead ECG algorithm ..." NEEDS_REVIEW;
"Cardiac monitor recall analysis" LOW; oximetry-in-engineering-journal IRRELEVANT. Root cause: a
title-level device-noun whitelist that missed "ECG algorithm", "cerebral oximetry", "continuous
EEG", "recall", and a scoring threshold that a correct paper could miss. Fixed: measurement
vocabulary (oximetry/saturation/NIRS/EEG/ECG/IBP/capnography...), device families from the
taxonomy, strict-evaluation precedence, recall importance.

### D6 (critical) Admission history was overwritten
Evidence: `record_admissions` used `INSERT OR REPLACE INTO observation_admission` with
PRIMARY KEY (observation_id, admission_version); a re-run with different evidence replaced the
earlier judgement, so no one could answer "was this record reconsidered, and what did the earlier
rules say?". Root cause: conflating a decision with a mutable projection. Fixed: append-only v3
(surrogate key, evidence_key, rules_digest, judged_version_id, triggers rejecting UPDATE/DELETE,
history API) plus a derived current projection; a rule change now appends a re-judgement instead of
editing one.

### D7 (high) Report and JSON disagreed
Evidence: docs/radar/QUALITY_001_ACCEPTANCE.md claims "Default feed (30 days) | 13 records" and
"PubMed precision 1.00 / recall 0.50; Crossref 1.00 / 0.25", while
docs/radar/quality_001/evidence/relevance-eval.json has `window_days: 14`, `count: 4`,
`by_stratum: unstratified`, and pubmed 4/4, crossref 7/8. Root cause: prose written by hand beside
generated data. Fixed: the report is generated from the JSON by the same command, a --check mode
fails on drift, and a test asserts window alignment.

### D8 (high) Evaluation window differed from the product window
Evidence: the old evaluator hard-coded 14 days for its feed composition; the product default
`admission_days` is 30. Root cause: two independent constants. Fixed: FEED_WINDOW_DAYS=30 in the
evaluator, asserted against the API default in a test.

### D9 (high) Coarse date precision rendered as an exact instant
Evidence: web/src/components/ui.tsx formatDateTime used `new Date("2026-11")`, which is
2026-11-01T00:00:00Z, and the feed called it for `source_published_at` without the precision the
API already sends. QA-002's "2026-11-01 00:00 UTC" is this line. Fixed: precision-aware
formatDate/formatDateTime plus a precision label; the API fields were already correct.

### D10 (high) Work identity was a title string
Evidence: `PARTITION BY lower(trim(o.title,' .;'))` in the feed. Root cause: convenience. Risk:
two different works with the same generic title are merged; one work whose title changes is shown
twice; the archive count is a count of titles, not works. Fixed: work_key from DOI, then PMID, then
title fallback, materialised on the observation row and covered by a test with one shared DOI and
two same-title different-DOI works.

### D11 (high) Discovery was filtered before storage
Evidence: `PubmedAdapter.accept_record` and `CrossrefAdapter.accept_record` called
`publication_relevance`, so an out-of-scope search hit was never stored. Root cause: a second rule
set, in a different module, applied at a different lifecycle stage, contradicting the ledger's
documented "discovery is broad; nothing can un-store it". Risk: a rule change cannot re-judge what
was never stored, and an evaluation sample drawn from the ledger cannot contain those false
negatives (see the limits section of the quality report). Fixed: the adapters store what the source
returned; the assessment layer decides. Consequence, stated honestly: ingestion volume grows for
publication sources, and the existing ledger was not re-collected in this round.

### D12 (medium) No safety-action lane in the radar
Evidence: radar adapters collect 510(k) and PMA; the product snapshot collects recalls; there is no
recall adapter in radar, so a monitoring-device recall can never enter the intelligence feed.
Root cause: lane split. Risk: the highest-value safety signal is missing from the intelligence
product. Status: not fixed in this round (needs a recall adapter + product-code mapping + tests);
the assessment engine already marks a recall record DIRECT/HIGH importance when one arrives.

### D13 (medium) Crossref watermark can jump into the future
Evidence: source_state crossref watermark = "2027-02" while the corpus was collected in 2026-11;
the incremental query starts from watermark - 45 days, so records published between the present and
the future watermark are never requested. Root cause: watermark = max(source-stated date), and an
ahead-of-print record states a future date. Fixed partially: the feed excludes future-dated records
from "latest"; the watermark policy still needs a fix (record it, do not rewrite the source state
in this round).

### D14 (medium) Dräger newsroom has no dates
Evidence: all 31 draeger_official observations have `published_at = event_at = null` and
precision unknown; the adapter scrapes titles without the article date. Risk: these records can
never appear in a time-scoped view and their freshness is unknowable. Status: open (adapter
improvement); the assessment correctly keeps them out of the feed.

### D15 (medium) API hotspots and route/blocks coupling
Evidence: product/api.py create_app 949 lines/CC 240 with 48 routes; radar/api.py build_router 428
lines/CC 74; `GET /api/events` and the radar feed share nothing. Status: documented, not
refactored this round (risk without browser E2E coverage of every route).

### D16 (medium) Feed query cost
Evidence: benchmark of the same corpus (40 iterations, in-process): v1 feed 30d p50 23.3 ms /
p95 41.8 ms; v2 after optimisation p50 31.9 / p95 56.1. The first v2 attempt was 48.9/85.7 because
the current-decision view was a correlated MAX over history; replacing it with an explicit derived
projection and a materialised work_key brought it back. Unfiltered feed 143.5 -> ~150-192 ms
(variance between runs), summary 49.2 -> 66.8 ms. Status: acceptable (page budget is ~1 s) but the
offset-based pagination still scans; keyset pagination is the next step.

### D17 (medium) No re-judgement on content change
Evidence: the old `admission_pending` only asked "is there a row for this version?", so a new
version of a record or a re-mapping did not trigger a new decision. Fixed: a work queue is filled
when a mapping/version changes, and `rules_digest` differences also queue a re-judgement (verified
on the real ledger: 8,593 decisions appended, old rows preserved).

### D18 (high, structural) Three stores, one vocabulary
Evidence: section 3. Root cause: each product round added a lane instead of unifying a contract.
Risk: duplicated identity registries, duplicated relevance semantics, inconsistent counts between
two UI surfaces. Status: documented; this round deliberately did not attempt a migration (it would
require a snapshot rebuild and a browser E2E matrix). Recommendation in REPAIR_PLAN.md.

## 7. What was deliberately not changed

- No production deployment, no data migration on the server, no re-collection of sources.
- No deletion of research branches, studies or historic evidence.
- No mechanical split of the 949-line API function or the 4,145-line report module: without a
  browser-level regression suite for every route, that is a higher risk than the debt it removes.
- No merge of the nine PRs; this round adds one reviewable layer on top of #54.
- The legacy market/trading lane stays; it is the project's research record, not a product path.

## 8. Evidence index

| Claim | Artefact |
| --- | --- |
| Complexity before/after | D:/DEPPSKK/data004-baseline/complexity-before.json, complexity-after.json |
| Reachability | D:/DEPPSKK/data004-baseline/reachability.json, reachability-after.json |
| Test baseline (per file, timings) | D:/DEPPSKK/data004-baseline/tests-per-file.txt |
| Baseline feed (old rules) | D:/DEPPSKK/data004-baseline/baseline_feed.json |
| Rule probes on the QA-002 classes | D:/DEPPSKK/data004-baseline/probe_rules.py output (in the session log) |
| Quality before/after/held-out | docs/refoundation/004/quality/*.json and QUALITY_*.md |
| Feed benchmark | D:/DEPPSKK/data004-baseline/bench_feed.py + run_bench.ps1 output |
| Frozen samples and labels | docs/refoundation/004/_evidence/quality/independent-sample.json, heldout-sample.json (sha256 recorded inside) |
