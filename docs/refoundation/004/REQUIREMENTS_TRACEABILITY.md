# REFOUNDATION-004 - Requirements traceability

Status vocabulary is exact and is not softened: IMPLEMENTED+VERIFIED means a test or a measured
artefact in this repository demonstrates it; IMPLEMENTED+PARTIAL means the mechanism exists but a
stated condition is not met; NOT IMPLEMENTED means it does not exist; NOT VERIFIED means it may
exist but this round could not observe it (deployment, live collection); BLOCKED-EXTERNAL means it
needs access this environment does not have.

## A. Medical-technology intelligence collection

| Requirement | Status | Evidence / gap |
| --- | --- | --- |
| PubMed collection | IMPLEMENTED+PARTIAL | adapter + fixtures + pipeline tests; live collection NOT re-run this round |
| Crossref collection | IMPLEMENTED+PARTIAL | adapter; watermark risk D13 open (a future issue date can push the watermark ahead) |
| openFDA regulatory records (510k/PMA) | IMPLEMENTED+VERIFIED | 6,936 observations in the ledger; adapter parses decision_date with precision |
| openFDA device recalls | NOT IMPLEMENTED in radar | the product snapshot has recalls; the radar has no recall adapter (audit D12). The assessment already ranks a recall DIRECT/HIGH importance |
| Company official news (Philips/Dräger/GE) | IMPLEMENTED+PARTIAL | Philips/Dräger adapters present; GE blocked by access policy (recorded as BLOCKED); Dräger article dates not parsed (D14) |
| Historical backfill | IMPLEMENTED+VERIFIED | backfill path with mandatory reason; ledger refuses an unexplained backfill |
| Continuous incremental update | IMPLEMENTED+PARTIAL | scheduler, watermarks, due/retry, resume, single-writer lock, tests; production cadence NOT VERIFIED from this host |
| Pagination/cursors | IMPLEMENTED+VERIFIED | page cursor + checkpoints; openFDA skip/total; tests |
| Retry/backoff/ratelimit/failure recording | IMPLEMENTED+VERIFIED | PoliteFetcher + source_failure table + run outcomes; tests |
| Resume after interruption | IMPLEMENTED+VERIFIED | recover_interrupted_runs, RUN_INTERRUPTED; tests |
| Raw response / provenance stored | IMPLEMENTED+VERIFIED | observation_version payload + content hash + source url per version |
| Change detection (NEW/UPDATED/REMOVED) | IMPLEMENTED+VERIFIED | change rows + tests; UNCHANGED never stored |
| Licence/attribution limits | IMPLEMENTED+PARTIAL | documented per source; no enforcement in code |

## B. Monitoring-rd relevance (the core domain problem)

| Requirement | Status | Evidence |
| --- | --- | --- |
| Separate source authenticity from subject relevance | IMPLEMENTED+VERIFIED | dimensions source_authenticity vs monitoring_relevance; HyperVue/UniGuide regression test |
| Separate medical domain from monitoring relevance | IMPLEMENTED+VERIFIED | medical_domain dimension; drone/radar/gear/gravity/oil-leak/CFAR regression tests |
| Explicit DIRECT/TRANSFER/CLINICAL/MEDICAL_UNRELATED/NON_MEDICAL classes | IMPLEMENTED+VERIFIED | assessment.py vocabulary + evaluator 5-class confusion matrix |
| Default feed = DIRECT (+ explicit TRANSFER) | IMPLEMENTED+VERIFIED | decision policy FEED; feed query filters decision; 20 records in the 30-day feed of the real ledger |
| Non-medical content in default feed | IMPLEMENTED+VERIFIED (zero tolerance test) | 8 named cases never FEED; held-out sample 0 non-medical false accepts |
| Important monitoring evidence not rejected | IMPLEMENTED+PARTIAL | intravascular/cerebral oximetry, ECG algorithm, EEG, ICP, recall-analysis cases are DIRECT; held-out recall 87.5% (28/32) |
| Official company identity cannot grant relevance | IMPLEMENTED+VERIFIED | vendor statement policy + test |
| Clinical/care studies not promoted by keywords | IMPLEMENTED+VERIFIED | clinical_application/clinical_target branches; sepsis/BNP/nursing tests |
| Two independent rule paths removed | IMPLEMENTED+VERIFIED | adapters no longer gate; relevance.py is a facade; single assessment module |
| Recall precision/recall targets (>=90% / >=85%) | MET ON HELD-OUT SAMPLE | precision 0.9333, recall 0.875 (Wilson 0.787-0.982 / 0.719-0.950); see QUALITY_HELDOUT.md |
| Crossref materially improved (not disabled) | IMPLEMENTED+VERIFIED | before 0.667/0.429 on the sample, held-out 1.0/0.727 for crossref; adapter still enabled |
| Safety-critical recall recall-check | NOT IMPLEMENTED | needs the recall adapter (D12); the assessment side is ready |

## C. Trustworthy evidence and entity relations

| Requirement | Status | Evidence |
| --- | --- | --- |
| Source links preserved | IMPLEMENTED+VERIFIED | source_url per observation/version; API exposes it |
| Original record identity | IMPLEMENTED+VERIFIED | (source, source_record_id) identity; official_identifier |
| DOI/PMID normalisation | IMPLEMENTED+VERIFIED | normalize_doi/normalize_pmid + tests; identifier table append-only |
| Company/product/topic entities | IMPLEMENTED+VERIFIED | taxonomy aliases (exact/prefix, no fuzzy) + graph assertions with method+confidence |
| TOPIC_RELATED never shown as product capability | IMPLEMENTED+VERIFIED | capability only from PRODUCT_HAS_REPORTED_CAPABILITY; QUALITY-001 test + branch UI separates 官方能力/监管主题证据/科研证据 |
| Relation provenance | IMPLEMENTED+VERIFIED | evidence id + rule version on assertions |
| Same DOI across sources = one work, provenance kept | IMPLEMENTED+VERIFIED | work_key DOI-first; two observations retained |
| Duplicate display suppression | IMPLEMENTED+VERIFIED | feed partitions by work_key; test |
| One organization registry | NOT IMPLEMENTED | two registries exist (config/radar/organizations.json and product/identity/organizations.json); documented in REPAIR_PLAN |

## D. Time, versions, immutable history

| Requirement | Status | Evidence |
| --- | --- | --- |
| event / published / first-observed / knowledge time distinct | IMPLEMENTED+VERIFIED | records.py contract, graph known_at/valid_at, API fields |
| Coarse precision never widened to an instant | IMPLEMENTED+VERIFIED | precision-aware UI formatting + precision label + test on features |
| openFDA decision date not presented as publication date | IMPLEMENTED+VERIFIED | published_at null + not_published_by_source; UI text |
| Admission decisions immutable | IMPLEMENTED+VERIFIED | v3 triggers reject UPDATE/DELETE; test |
| Re-judgement keeps history | IMPLEMENTED+VERIFIED | evidence_key + history API; test; real ledger: 8,593 re-judgements appended, earlier rows retained |
| Rule version triggers re-judgement | IMPLEMENTED+VERIFIED | rules_digest queueing; real ledger re-judged after a rules change |
| Migration safety (v2 -> v3) | IMPLEMENTED+VERIFIED | row-by-row copy forward, old copy dropped only after copy; test constructs a v2 table |
| Idempotent repeated run | IMPLEMENTED+VERIFIED | same evidence_key => no new row; test |
| Migration of the real ledger | IMPLEMENTED+VERIFIED | the 8,593-row copy was migrated and re-projected in this round |

## E. Technology tree and research views

| Requirement | Status | Evidence |
| --- | --- | --- |
| Technology branches (topics) | IMPLEMENTED+VERIFIED | taxonomy config + topic detail API + tests |
| Company/product relations | IMPLEMENTED+VERIFIED | graph assertions + node detail + tests |
| Research evidence vs regulatory evidence vs capability | IMPLEMENTED+VERIFIED | separate edge types and UI sections; tests |
| Historical (public-time / knowledge-time) queries | IMPLEMENTED+VERIFIED | mode=public/knowledge with at=; 500 fixed in QUALITY-001; tests |
| Graph node detail + evidence pagination | IMPLEMENTED+VERIFIED | product_offset/evidence_offset + has_more; tests |
| Change log pagination | IMPLEMENTED+VERIFIED | /graph/changes offset+totals+has_more; tests |
| Workbench filters | IMPLEMENTED+VERIFIED | source/org/topic/confirmation/state/phase/date/tier filters; tests |
| No regression of accepted features | IMPLEMENTED+VERIFIED | full pytest suite green before and after (see TEST_RESULTS in FINAL report) |

## F. Product experience and language

| Requirement | Status | Evidence |
| --- | --- | --- |
| Desktop layout | IMPLEMENTED+NOT VERIFIED this round | existing pages and screenshots from PRODUCT-004; no new browser run |
| Mobile layout / 44 px touch targets | IMPLEMENTED+PARTIAL | QUALITY-001 measured 44 px and no overflow at 390 px; not re-measured after the bundle rebuild |
| Chinese and English | IMPLEMENTED+PARTIAL | i18n dictionary; new dimension chips are bilingual; new category labels only have Chinese translations (English falls back to the code) |
| Loading/error/empty states | IMPLEMENTED+VERIFIED | AsyncSection/EmptyState/Banner; tests on error bodies |
| Pagination | IMPLEMENTED+VERIFIED | API page/total/has_more + UI pagers; tests |
| Legacy URL redirect | IMPLEMENTED+VERIFIED | QUALITY-001 hotfix; tests |
| Auth/session | IMPLEMENTED+VERIFIED | alpha gate + auth tests; unauthenticated API returns 401 |
| Honest labels (no unsupported claims) | IMPLEMENTED+PARTIAL | capability semantics fixed in QUALITY-001; new dimension chips show source/domain/relevance with confidence; there is no UI for "importance" yet |

## G. Quality system

| Requirement | Status | Evidence |
| --- | --- | --- |
| QA-002 findings tracked as known issues | IMPLEMENTED | every finding has a regression test or a documented open item |
| QA-002 original 120-item sample preserved as baseline | NOT POSSIBLE | the QA-002 sample file is not in the repository or on this host; the report's findings (metrics, named cases) are preserved and each named case is a regression test |
| New independent validation set | IMPLEMENTED (with stated limits) | two frozen fixed-seed samples (120 development, 80 held-out), labelled before/after rule freeze; single-reviewer machine-assisted, not a human panel |
| Per-source and per-class metrics | IMPLEMENTED+VERIFIED | evaluator JSON + generated Markdown |
| False positives and false negatives analysed | IMPLEMENTED+VERIFIED | both lists with rationales in the generated report |
| Sampling and inference limits stated | IMPLEMENTED+VERIFIED | in the sample metadata and the report footer |
| Machine-generated JSON and report | IMPLEMENTED+VERIFIED | one producer; --check mode; Markdown generated from the JSON |
| N/A instead of 100% for empty denominators | IMPLEMENTED+VERIFIED | ratio() returns null; report prints n/a |
| Product window == evaluation window | IMPLEMENTED+VERIFIED | both 30 days; test |
| Registry of high-risk recall cases | NOT IMPLEMENTED | blocked by the missing recall adapter |

## H. Engineering governance

| Requirement | Status | Evidence |
| --- | --- | --- |
| Complexity baseline measured | IMPLEMENTED+VERIFIED | complexity-before.json / complexity-after.json |
| Module responsibility documented | IMPLEMENTED | docs/engineering/ENGINEERING_START_HERE.md |
| Anti-regression tests for this round's defects | IMPLEMENTED+VERIFIED | tests/test_radar_integrity.py (14 tests) |
| Reviewable, separable commits | IMPLEMENTED | commit series described in FINAL_ENGINEERING_REPORT.md |
| Performance measured, not asserted | IMPLEMENTED+PARTIAL | feed/summary benchmark before/after; the browser-level cold-start measurement was not repeated |
| Deployment / rollback path | NOT VERIFIED | runbook exists (docs/radar/LAUNCH_001_RUNBOOK.md); this round did not deploy |
| Live collection proof (new records appear) | NOT VERIFIED | no source was re-collected in this round; the incremental machinery is covered by synthetic-record tests only |
