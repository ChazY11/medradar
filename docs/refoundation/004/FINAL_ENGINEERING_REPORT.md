# REFOUNDATION-004 - Final engineering report

Date: 2026-11-18. Branch: refoundation/004, based on feat/radar-001-live-intelligence-graph (PR #54,
HEAD 14eaf61). This report answers the twelve questions the brief asks, and marks what could not be
verified as NOT VERIFIED instead of implying success.

## 1. Which real problems were fixed?

| # | Problem (before) | Fix | Proof |
| --- | --- | --- | --- |
| 1 | 83.4% of the ledger was HIGH_RELEVANCE; one label carried eight judgements | dimension-separated assessment + feed decision policy | tier counts (7,366 FEED of 8,593, dominated by the openFDA backfill); integrity tests |
| 2 | Official Philips imaging launches in the default feed (QA-002: 2 of 13) | source authenticity is no longer relevance; a primary record must name a monitoring subject | HyperVue/UniGuide regression test; the 30-day feed no longer contains them |
| 3 | An ECG algorithm paper was IRRELEVANT because its journal said "Telecommunications" | venue text can never be a non-medical exclusion; subject/venue/index/entity roles separated | regression test; the paper is DIRECT now |
| 4 | Drone/radar/gear-health/gravitational-wave/oil-leak/CFAR content admitted | domain vocabulary + medical anchor + behaviour/workflow branch | 8 named regression cases all non-feed |
| 5 | Genuine monitoring evidence rejected (single-lead ECG algorithm, cerebral/intravascular oximetry, ICP, monitoring recall analysis) | measurement vocabulary, device families, strict-evaluation precedence | 6 named regression cases are DIRECT; held-out recall 87.5% |
| 6 | Admission history overwritten (QA-002) | append-only v3 + evidence_key + rules_digest + triggers + derived current projection | immutability/history/idempotency/migration tests; real 8,593-row migration |
| 7 | Re-running rules did not re-judge changed content | work queue + rules-digest re-judgement | 8,593 re-judgements appended on the real ledger, earlier rows kept |
| 8 | Evaluation report contradicted its own JSON; 14-day evaluator vs 30-day product | one generator for JSON+Markdown, --check drift gate, shared window constant | --check passes; window equality test |
| 9 | Month-precision dates rendered as "2026-11-01 00:00 UTC" | precision-aware formatting + precision label | web bundle rebuilt and contains the precision label; UI code |
| 10 | Work deduplicated by title string | DOI -> PMID -> title work_key | shared-DOI and same-title tests |
| 11 | Discovery filtered before storage by a second rule set | adapters store what the source returned | ADR-004; adapter change; pipeline tests |
| 12 | Source-stated future dates could enter the 30-day feed | latest scope requires date <= now | feed on the real ledger no longer lists the 2026-12 record |

## 2. Which problems were only mitigated?

- **Crossref watermark can still jump into the future** (audit D13). The feed no longer shows
  future-dated records, but the incremental watermark policy is unchanged; records between now and
  the future watermark may be skipped until the watermark is repaired. Recorded in the repair plan.
- **Feed query latency** rose from 23.3 ms p50 / 41.8 ms p95 to 31.9 / 56.1 (same corpus, in-process).
  The first attempt was 48.9/85.7; the derived projection fixed most of it. Acceptable for now, not a
  win.
- **Ingestion volume** grows now that PubMed/Crossref store everything they return. No production
  run measured the new volume; the existing ledger was not re-collected.
- **Pagination** is still offset-based and scans.
- **Two organization registries** remain (audit D18/S6).
- **New category labels are Chinese-only**; English falls back to the code string.

## 3. Which technical debt was permanently removed?

- The second relevance rule path (adapters' `accept_record` -> `publication_relevance`) is gone
  from the publication adapters; relevance has one implementation, one version, one digest.
- Admission has one read path and one write path; an overwritten decision is now impossible in the
  schema (triggers), not just discouraged in code.
- Work identity has one definition (work_key) instead of an inline title expression inside one query.
- The quality report cannot drift from the metrics: the prose is generated and a --check mode fails.
- Fourteen named regression tests encode the QA-002 defect classes; they fail by name if a later
  change reintroduces one.

## 4. Which capabilities were completed?

- Relevance explanation on the feed card (source / domain / relevance / confidence badges).
- Date precision is visible wherever a source date is shown (label + value at the stated precision).
- Admission history is queryable per observation (`ObservationLedger.admission_history`), including
  what the earlier rules said.
- Re-judgement is automatic on rule change and on record change.
- A held-out evaluation protocol with frozen samples and generated reports.

## 5. Did any capability regress?

Nothing accepted by the previous round's tests was removed; the full test suite was green before the
round and is green after (see section 11). Two intentional behaviour changes can look like
regressions and are documented: (a) vendor/regulatory records without a monitoring subject no longer
appear in the feed (that is the fix), and (b) PubMed/Crossref admissions now include a much larger
set of stored-but-excluded records, so "archive" counts of the ledger are no longer a count of
monitoring-only material. The user-facing feed views are unchanged in shape, and the historical
view still works.

## 6. Did system complexity really fall?

No, not by raw measures: +2 modules, +1% lines, +5 functions with CC > 10, CC > 15 unchanged
(80). That is reported in COMPLEXITY_REPORT.md without spin. What fell is the complexity that made
this area risky: one relevance implementation instead of three places that decided scope; a
provable admission history instead of an overwritten row; one definition of a work; a generated
quality report instead of hand-written numbers; and 14 tests that make the old failure modes
visible. The remaining hotspots (product/api.py 949 lines / CC 240, `_sync_locked`,
`load_dataset`, `technology_map`) were intentionally not split without browser-level coverage.

## 7. Did performance really improve?

No. The feed is slower by roughly a third on p50 (23.3 -> 31.9 ms) and p95 (41.8 -> 56.1 ms) on the
same corpus, because each row now carries an explained decision. It remains far under the page
budget, and the first implementation was worse (48.9/85.7) until the current-decision projection
and materialised work key were added. Browser cold-start timings were not re-measured
(NOT VERIFIED). See PERFORMANCE.md for the table and the environment.

## 8. Is new intelligence actually being produced continuously?

NOT VERIFIED in this round. No source was re-collected; no live cycle was run against the network.
What is verified: the incremental machinery (watermarks, cursors, checkpoints, resume, failure
recording, change states, re-judgement) is covered by tests, and the scheduler and systemd runbook
exist. Whether the production timer is currently producing new observations could not be observed
from this host. The audit did find one concrete incremental risk (Crossref watermark, D13) that
would degrade discovery in production.

## 9. Did independent intelligence quality reach the target?

Yes, on the held-out sample, with stated limits.

| Measurement | Precision | Recall | Sample |
| --- | --- | --- | --- |
| Old rules, independent sample (this round's reproducible before) | 0.7736 (41/53) | 0.7736 (41/53) | 120 records, 53 feed-relevant |
| New rules, same development sample | 1.000 (52/52) | 0.9811 (52/53) | same 120 (used while designing v2 - optimistic) |
| New rules, held-out sample frozen before the final rules | **0.9333 (28/30)** | **0.8750 (28/32)** | 80 records, 32 feed-relevant; Wilson 95% 0.787-0.982 / 0.719-0.950 |

Targets were >= 90% precision and >= 85% recall on unseen data: met on this held-out sample. The
QA-002 report's 71.2% / 75.5% measured the old rules; this round's reproducible "before" number on
its own sample is 77.4% / 77.4%, in the same range, which is a useful cross-check that the before
state is not understated.

Limits that must be read with the numbers:
- The labels are one reviewer's adjudication against a frozen rule, not an independent human panel.
- The held-out per-source picture is uneven: PubMed precision 0.0 (2 predicted positives, both
  wrong) / recall 0.0 (0/1); Crossref 1.0 / 0.727; openFDA 1.0 / 1.0. The two PubMed false accepts
  are a clinical review using monitoring-derived metrics (SpO2 histograms) and a physiology study
  (HRV trajectories); the false reject is an AI-monitoring review without a device noun. These are
  named in QUALITY_HELDOUT.md and are the first thing the next round must fix.
- The sample comes from one corpus snapshot; records the old adapters discarded before storage could
  not be sampled (disclosed in ADR-004 and the sample metadata).
- The QA-002 120-item sample file is not available in this repository or on this host; its findings
  are preserved as named regression cases, not as item-level data.

## 10. Does the system meet the bar for a real R&D team today?

Partially, and the honest answer depends on the use.
- As a monitoring-technology reading queue: close. The default feed is 20 records over 30 days from
  the current corpus, each with source, dimensions, confidence and evidence links; the known errors
  are documented and bounded.
- As an early-warning system: no. The project's own studies are negative, and the intelligence lane
  has no validated predictive signal. Do not present it as one.
- As a safety monitor: not yet. There is no recall adapter in the radar (audit D12).
- As a production service: the deployment is documented but was NOT VERIFIED in this round; no
  live recollection or browser matrix was run.

## 11. Do the tests pass?

Baseline before the round: full pytest suite **green**. After the changes: full suite **green**
(1,632 tests collected across 86 files, 5 skipped, 0 failed). The radar suites were run repeatedly
during the work (all green), the new integrity suite is 14 tests green, the governance suite is 73
tests green, and the FastAPI app answers the product and radar endpoints end-to-end against the
real ledger copy (12/12 checks). Details in TEST_RESULTS.md; per-file baseline timings are in
D:/DEPPSKK/data004-baseline/tests-per-file.txt.

Counts observed in this round: 162 modules; radar suite (relevance, integrity, core, ledger, api,
pipeline, graph, scheduler, ai, backup, parsers, alpha gate) 143+ tests green; governance 73 tests
green; new integrity tests 14.

## 12. Should this be merged and deployed?

Merge: yes, as a reviewable layer on top of #54, after a reviewer reads ADR-001/002 and the diff of
ledger.py. The changes are additive at the schema level (v3 migration is one-way but safe) and the
tier vocabulary is unchanged.
Deploy: not yet. Conditions before deployment: (1) run the QUALITY-001 runbook with a verified
backup and record the deployed SHA, (2) re-run the live acceptance checklist on the public URL,
(3) decide the Crossref watermark fix and the recall adapter, (4) re-measure cold start after the
bundle rebuild. None of this was done here, and none of it should be skipped.

## What is in the branch

| Area | Change |
| --- | --- |
| medradar/radar/assessment.py (new, 889 lines) | eight-dimension assessment and the feed decision policy |
| medradar/radar/relevance.py | 421 -> ~100 lines, a facade with no logic |
| medradar/radar/ledger.py | schema v3: append-only admission + derived projection + work_key + work queue, v2->v3 migration, feed dedupe by work, future-date exclusion |
| medradar/radar/engine.py | re-judgement on rule change, evidence keys, dimensions persisted |
| medradar/radar/adapters/{pubmed,crossref}.py | removed the pre-storage relevance gate |
| scripts/evaluate_relevance.py | rewritten evaluator + generated report + --check |
| web/src (ui, feed page, api types) | precision-aware dates, precision label, dimension chips; bundle rebuilt |
| tests/test_radar_integrity.py (new) | 14 named regression tests for every defect class |
| docs/refoundation/004/* | audit, decisions, traceability, repair plan, complexity, performance, quality artefacts, this report |
| docs/engineering/ENGINEERING_START_HERE.md | the single entry point for a new engineer or agent |

## Commit series (each independently reviewable)

1. docs: full system audit and engineering entry point.
2. feat(radar): dimension-separated relevance assessment, replacing the single tier.
3. feat(radar): append-only admission history v3 with a derived current decision.
4. feat(radar): identifier-based work identity, future-date guard, re-judgement queue.
5. fix(web): precision-aware dates and dimension badges; rebuilt bundle.
6. test(radar): regression suite for the QA-002 defect classes.
7. docs(refoundation): decisions, traceability, repair plan, complexity, performance, quality and final report.

## NOT VERIFIED (explicit)

- Production deployment state and the currently deployed SHA.
- Any live source collection or new intelligence observed in production.
- Browser cold-start / mobile timing after the bundle rebuild; WebKit/Safari.
- Memory peak and CPU of the full product service.
- Data-processing throughput of a full sync.
- Whether the production systemd timers are currently running.