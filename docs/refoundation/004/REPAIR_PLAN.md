# REFOUNDATION-004 - Repair plan and status

The order is dependency-driven: a correctness change that later work depends on goes first.
Every "done" item has a test or a measured artefact; every "open" item states what blocks it.

## Phase 3 - Critical integrity repairs (this round)

| ID | Task | Depends on | Risk | Validation | Complexity impact | Status |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | Replace the single relevance tier with dimension-separated assessment + decision policy | taxonomy families (exists) | medium: every admission changes | 16 integrity tests; 120-item development sample; 80-item held-out sample | +~890 lines in one module; -321 lines of old scoring; removes a second rule path in adapters | DONE |
| R2 | Make admission decisions append-only (v3) with evidence_key, rules_digest, judged_version_id, triggers | R1 (new columns) | medium: schema migration | immutability test, history test, idempotency test, v2-migration test, real 8,593-row migration | +1 table, +1 view; one derived projection keeps reads fast | DONE |
| R3 | Re-judge on content change and on rule change; queue work instead of overwriting | R2 | low | unit test + real ledger re-judgement (8,593 rows appended, history preserved) | +1 work-queue table | DONE |
| R4 | Remove the pre-storage relevance gate from PubMed/Crossref adapters | R1 (assessment must be good enough) | medium: ingestion volume grows | radar pipeline tests; documented in ADR-004 | -2 overrides, -1 rule path | DONE (code) / re-collection NOT DONE |
| R5 | Identifier-first work identity (DOI, PMID, title fallback) | ledger identifier table (exists) | low | test: shared DOI = 1 row; same title + different DOI = 2 rows | +1 derived column + index | DONE |
| R6 | Precision-aware time display; no fabricated midnight; openFDA decision date never a publication date | API precision fields (exist) | low | UI code + integration test on precision handling; bundle rebuilt | none | DONE |
| R7 | Exclude source-stated future dates from the "latest" scope | none | low | feed on the real ledger no longer contains the 2026-12 record | none | DONE |
| R8 | Evaluation harness rewritten: generated JSON+Markdown, --check, per-class/per-source, N/A, 30-day window | R1 | low | --check passes; test asserts window alignment; committed artefacts | replaces a 189-line script | DONE |
| R9 | Frozen development + held-out samples with digests | R8 | none | sha256 in the sample files | none | DONE |
| R10 | Regression tests for every QA-002 defect class | R1-R7 | none | tests/test_radar_integrity.py | +~300 test lines | DONE |

## Phase 4 - Architecture simplification (this round, deliberately bounded)

| ID | Task | Status | Reason |
| --- | --- | --- | --- |
| S1 | One implementation of relevance (relevance.py -> facade) | DONE | removes the duplicate scoring path (audit D1/D11) |
| S2 | Derived current-decision projection instead of a correlated view on the read path | DONE | keeps feed p95 below the page budget after v3 |
| S3 | Materialised work_key instead of a per-query identifier aggregate | DONE | measured in PERFORMANCE.md |
| S4 | Split product/api.py create_app (949 lines, 48 routes) into routers | OPEN | needs browser E2E coverage per route; not safe in this round |
| S5 | Split data_pipeline/pipeline._sync_locked (412 lines, cc 105) | OPEN | load-bearing production path; needs its own acceptance run |
| S6 | Merge the two organization registries | OPEN | requires a reviewed alias merge; a wrong merge poisons the graph permanently |
| S7 | One Observation/Evidence contract across the three lanes | OPEN | requires a snapshot rebuild + browser matrix; see ADR-007 |
| S8 | Freeze/archive the legacy lane explicitly (no new features) | PARTIAL | audit documents it; no code change |

## Phase 5 - Product completeness (this round)

| ID | Task | Status | Evidence / gap |
| --- | --- | --- | --- |
| P1 | Relevance badges that state the dimension instead of one tier | DONE | feed cards show source/domain/relevance/confidence |
| P2 | Month/year precision shown as such | DONE | formatDate/formatDateTime take precision; precisionLabel |
| P3 | Recall adapter in the radar lane (safety intelligence) | OPEN | audit D12; the assessment already ranks recalls DIRECT/HIGH importance |
| P4 | Dräger article-date extraction | OPEN | audit D14 |
| P5 | English translations for the new category labels | OPEN | Chinese labels added; English falls back to the code string |
| P6 | Browser E2E re-run after the bundle rebuild | OPEN | bundle rebuilt and type-checked; no browser matrix in this round (see FINAL report) |

## Phase 6 - Verification performed this round

- Full pytest suite (baseline green, re-run after the changes).
- Radar integration tests through the FastAPI TestClient (feed, detail, graph, pipeline, auth).
- Ledger migration and re-projection on a copy of the real 8,593-observation ledger.
- Relevance measured on a development sample and on a held-out sample frozen before the rules were final.
- Feed-query benchmark before/after on the same corpus.
- Web bundle type-checked and rebuilt with the existing toolchain.

## Phase 7 - What the next round must do, in order

1. Add the recall adapter and a safety-case recall test (P3). Highest product value.
2. Fix the Crossref watermark policy (D13) and Dräger date extraction (D14), then re-collect and
   re-measure the held-out numbers on refreshed data.
3. Merge the organization registries behind a reviewed alias diff (S6).
4. Extract product/api.py routers with route-level tests and a browser pass (S4).
5. Replace offset pagination with keyset pagination on the feed (D16).
6. Deploy behind the existing runbook, with a verified backup and a rollback SHA, then run the
   live acceptance checklist (deployment NOT VERIFIED in this round).
7. Re-run the independent evaluation with a different reviewer and a re-drawn fresh sample; the
   current labels are one reviewer's adjudication and must not be presented as a human panel.
