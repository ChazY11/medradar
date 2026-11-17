# QUALITY-001 — Intelligence relevance, product integrity and independent QA closure

Status: fixed and deployed. Baseline for the work: PR #54 at `e51ae4d`, which the independent QA
report measured. Every number below was produced on the production host or through the public
HTTPS URL; nothing is projected. The developer self-assessment cannot close the QA verdict — this
document is the evidence package for the independent re-test.

## 1. What the independent QA found, and what was actually wrong

| QA finding | Root cause | Fix | Regression proof |
| --- | --- | --- | --- |
| P1-01: 17 of the first 20 feed records were not ICU monitoring intelligence | Admission was keyword-driven: a topic keyword anywhere (often `"false alarm"`, `"monitoring"`, `"ECG"`) was enough. There was no layer that asked whether the record studies a monitoring *technology* | Three-layer qualification: discovery stays broad; `medradar/radar/relevance.py` (version `radar-admission-2026.11.3`) scores explicit device/engineering/evaluation features, rejects clinical prediction/risk work, veterinary/industrial/military/radiation domains, case vignettes, health economics and unmapped vendor statements; only `HIGH_RELEVANCE` reaches the default feed. Decisions are an append-only `observation_admission` projection | `tests/test_radar_relevance.py`; section 3 metrics; the QA's own named records are now all LOW/IRRELEVANT/REVIEW (section 4) |
| P1-02: public-time historical view returned 500 and printed a Python signature | `snapshot_cached()` called `normalize_moment(value)` with one argument while the signature is `(value, field)` | Correct call; the default 500 body is now generic with a log reference | `test_a_historical_public_time_view_answers_200_instead_of_500`, `test_the_public_500_never_returns_the_internal_exception`; live probe returns 200 for 2020 public and knowledge views |
| P1-03: evidence node drawer 404 | The UI split `record_node` on `:` and dropped the `obs:` prefix | The API sends `record_node_id` and `record_node_type`; the UI uses them verbatim | `test_the_map_sends_the_exact_node_id_and_the_node_endpoint_accepts_it`; real clicks on publication / regulatory_record / document / product each opened a 200 drawer |
| P1-04: TOPIC_RELATED regulatory evidence shown as "capability" | Product capability lists were built from regulatory topic edges | Capabilities are only `PRODUCT_HAS_REPORTED_CAPABILITY`; regulatory-derived products expose `regulatory_evidence` and a separate count; the branch shows 官方能力 / 监管主题证据 / 科研证据 separately | `test_no_regulatory_product_is_reported_as_a_capability`; live map reports 0 official capabilities and 307 regulatory evidence rows |
| P1-05: 8.9–16.6 s cold starts, 6.4–12.9 s old-route redirects | Every response carried `cache-control: no-store`, so each navigation re-downloaded the 557 KB bundle; the status API ran in the first request burst | Hashed assets are `private, max-age=31536000, immutable`; HTML/API stay `no-store`; the source-status card starts only after the first feed page is in | Section 5: 10 cold + 10 refresh + 8 redirect rounds, none over 10 s |
| P1-06: truncated products/evidence/changes had no way to see the rest | Only `LIMIT` was exposed, no offset or totals | `product_offset` / `evidence_offset` on the map, `offset` on graph changes; totals and `has_more`; the UI has a branch pager that loads to the end | `test_map_pagination_can_walk_a_branch_to_its_end`, `test_graph_changes_reports_offset_and_has_more`; live 29/29 evidence rows to "已到该分支末尾" |
| P2-01: duplicate company filters | Facets were grouped by (company, confirmation) and rendered per row | Merged per company with a confirmation breakdown inside the row | `test_the_facet_list_merges_one_company_into_one_filter`; live: Philips 223, GE 173, Dräger 90 — one chip each |
| P2-02: 26–40 px touch targets | Small chips and buttons | 44 px minimum on phone widths | Section 6 measurement |
| P2-03: mixed Chinese/English | Time-view explanations and graph counts came from English-only backend strings | Chinese `statement_zh` / `cannot_do_zh`; count line now describes the selected view | Screenshot 02 |
| P2-04: 500 leaked implementation detail | The handler returned `str(exc)` | Generic message + reference; full traceback only in the journal | `test_the_public_500_never_returns_the_internal_exception` |
| P2-05: whole-graph counts shown as the company view | The map note printed total nodes/edges | The note reports branches with evidence and evidence rows in the selected view | Screenshot 02 |

## 2. Relevance mechanism

- **Discovery** (adapters, unchanged): a record is stored when a monitored source mentions a
  monitored company or topic. Nothing in qualification can un-store it.
- **Qualification** (`medradar/radar/relevance.py`): feature-gated rules, not a model.
  Hard exclusions: non-human subjects, non-medical domains (grid/industrial/military/radiation),
  case vignettes, health economics, clinical prediction/risk studies. `HIGH_RELEVANCE` requires a
  title-level device/engineering subject *and* an evaluation/validation/design signal;
  `NEEDS_REVIEW` holds plausible but unconfirmed monitoring technology; `LOW_RELEVANCE` and
  `IRRELEVANT` keep the record with its reason.
- **Publication**: four user views — 最新发现 (source-published inside 30 days), 最新观察 (first seen
  by MedRadar inside 30 days, may be old), 历史资料库 (all qualified history), 待核实
  (NEEDS_REVIEW). The default is 最新发现.
- **Storage**: `observation_admission` is append-only, keyed by `(observation_id,
  admission_version)`. The observation, its versions and `first_observed_at` are never modified;
  a rejected record is retained with a reason. Re-projection is `python -m medradar radar reproject`.

## 3. Human-labelled evaluation set and measured quality

The set is in `config/radar/quality_eval.json`: 38 records from the production ledger, stratified
as 3 default-feed records, 20 fixed-seed random publications, 6 PubMed, 5 FDA and 4 vendor press
records. Label rule: *relevant* = the record is about an ICU/patient-monitoring device,
measurement, system or algorithm (filings and vendor statements about one included); *boundary* =
a reasonable reviewer could go either way and is excluded from precision/recall. Labels were
written by the development agent after reading titles and, where present, abstracts; they are
independent of the rule code and are the basis of the numbers below.

Measured with `scripts/evaluate_relevance.py` against the production ledger
(`docs/radar/quality_001/evidence/relevance-eval.json`):

| Metric | Value |
| --- | --- |
| Labelled records | 34 (4 boundary excluded) |
| Relevant in sample | 17 |
| Default-feed precision (HIGH ∩ relevant / HIGH) | **1.00** (9/9) |
| Recall (HIGH ∩ relevant / relevant) | **0.94** (16/17) |
| Irrelevant records wrongly HIGH | 0 |
| Precision 95 % Wilson lower bound (n=9) | ≈0.70 — the sample is small and the interval is reported, not hidden |
| Recall 95 % Wilson interval (16/17) | ≈0.73–0.99 |
| Per source | PubMed precision 1.00 / recall 0.50; Crossref 1.00 / 0.25; FDA 1.00 / 1.00; Dräger press 1.00 / n.a. |
| Default feed (30 days) | 13 records, all HIGH_RELEVANCE |

The one remaining false negative is an explainable-ML ECG classification paper whose title does
not carry a device noun; it is in 待核实 rather than the default feed. The per-source recall shows
the honest limitation: many relevant Crossref/PubMed papers are reviews or measurement papers that
the title-level rule sends to review, not to the default feed.

## 4. The QA's own examples, re-checked against the deployed rules

| QA example | Tier now | Category |
| --- | --- | --- |
| TIMI Risk Score for ACS | LOW_RELEVANCE | clinical_prediction_model |
| TIPS Endoprosthesis | LOW_RELEVANCE | clinical_study_without_device_focus |
| Pilates physiological indicators | LOW_RELEVANCE | no_monitoring_technology |
| Wearable sensing for sport horses | IRRELEVANT | non_human_subject |
| Smart-grid false data injection | IRRELEVANT | non_medical_domain |
| FreeStyle Libre cost-effectiveness | LOW_RELEVANCE | health_economics |
| Electrical-infrastructure condition monitoring | IRRELEVANT | non_medical_domain |
| Elevated Creatinine — False Alarm? | NEEDS_REVIEW | plausible_monitoring_technology |

None of them appears in the default feed.

## 5. Performance, measured as the QA asked (10 rounds each)

Chromium, 390×844, public URL, CDP cache cleared for cold rounds. Full data:
`docs/radar/quality_001/evidence/performance.json`.

| Scenario | Median first card | P90 | Max | >10 s |
| --- | --- | --- | --- | --- |
| Cold start ×10 | **1.23 s** | 1.75 s | 2.02 s | 0 |
| Refresh ×10 | **1.13 s** | 2.38 s | 2.59 s | 0 |
| Old workbench URL → feed ×8 | 1.30 s | — | 3.28 s | 0 |

Stable (first card + settle) maxima: 3.54 s cold, 3.41 s refresh. For comparison, the independent
report measured 8.875 s first card / 11.092 s stable on mobile, a 16.649 s refresh and 6.362–12.941 s
redirects. No slow round was dropped; the worst run in each series is in the table.

## 6. Live acceptance (public HTTPS, authenticated, 390×844)

- Default feed: 13 cards, tab counts 13 / 6934 / 6575 / 359, every card carries a 相关情报 badge;
  1.0 s class first paint; no console error, no failed request.
- Historical view: 公开时间 2020-01-01 returns 200, renders 12 branches and reconstructs what was
  publicly true then; 知识时间 2020 returns 200 with an honest empty view.
- Evidence nodes: publication, regulatory_record, document and product each opened a drawer from a
  real click; `/api/radar/graph/node` answered 200 for each.
- Capability semantics: every product shows 注册设备 (filed device) or 官方能力 N (vendor statement);
  branch summary reads 官方能力 0 · 监管主题证据 N · 科研证据 M.
- Pagination: the arrhythmia branch pager walked 29 / 29 rows to "已到该分支末尾"; graph changes
  reports offset, totals and `has_more`.
- Touch: card buttons and chips measure 44 px, tabs 53 px at 390 px width; no horizontal overflow
  (`scrollWidth` 375 ≤ 390).
- Security regression: unauthenticated page/API 401; `/api/review/*`, `/api/export/*`, `/api/docs`,
  `/openapi.json`, database paths 404 even authenticated; TLS chain valid; the 500 body no longer
  contains internal text.

Screenshots: `docs/radar/quality_001/evidence/01-mobile-feed.png` … `04-mobile-historical-view.png`.

## 7. Deployment, migration and rollback

- Pre-deploy verified backup: `/srv/medradar/backups/radar/radar-20261117T162205594.db`
  (40.1 MB, `integrity_check=ok`, 8,281 observations, sha256
  `ace59c674ad27cbb9b712f37a14f572bffcf19b17e5834532a442141225795e2`).
- Deployed commit: **`d91d647eda15e480136b8b13db188581cfbd43f2`** (release tree under
  `/srv/medradar/radar/releases/`); scheduler, web, tunnel and backup units stayed active.
- Migration: one additive table, `observation_admission`, plus its index. No observation row,
  version, change event or `first_observed_at` is edited. `radar reproject` filled 8,281 decisions
  (7,159 HIGH / 379 review / 642 low / 101 irrelevant).
- Rollback: redeploy `e51ae4d` — the old code ignores the new table, which is inert; the ledger and
  graph remain valid. If the ledger itself were suspect, restore the backup above with
  `radar restore-check` before swapping it in. Monitoring does not need to stop for either path.
- CI: see the PR check run on `d91d647`.

## 8. Evidence index for the independent re-test

| Evidence | Location |
| --- | --- |
| Relevance metrics (machine-readable) | `docs/radar/quality_001/evidence/relevance-eval.json` |
| Human labels and sampling rules | `config/radar/quality_eval.json` |
| Performance rounds | `docs/radar/quality_001/evidence/performance.json` |
| Mobile feed / map / pager / historical screenshots | `docs/radar/quality_001/evidence/*.png` |
| Reproduce relevance numbers | `python scripts/evaluate_relevance.py --data-dir /srv/medradar/data/radar` |
| Re-projection | `python -m medradar radar reproject --batch 1000` |
| Historical-view HTTP check | `GET /api/radar/technology-map?mode=public&at=2020-01-01T00:00:00Z` → 200 |
| Node check | pick `record_node_id` from the map payload, `GET /api/radar/graph/node?node_type=…&node_id=obs:…` → 200 |
| Backup manifest | `radar backup --destination /srv/medradar/backups/radar --json` |

## 9. Remaining issues (not hidden)

- The evaluation set is small (34 labelled) and labelled by the development agent; the Wilson
  intervals above are wide. It is a regression baseline, not a certification.
- Per-source recall is uneven: Crossref/PubMed relevant reviews and measurement papers often land
  in 待核实, so the default feed is small (13 records in 30 days). That is deliberate precision
  over volume, but it reduces discovery for a user who wants breadth.
- Vendor statements are admitted when the mapper places them in a monitored topic; a launch that
  only mentions imaging (e.g. Philips HyperVue) can still appear if the mapping puts it in a topic.
  This is a boundary the next evaluation round should label explicitly.
- Press records without a parseable publication date cannot enter 最新发现; they appear in
  最新观察/历史资料库. The adapter does not yet extract the article date.
- The public address is still the temporary Quick Tunnel hostname; stable domain remains open.
- WebKit/Safari was not executed; the mobile checks are Chromium at an iPhone-sized viewport.
