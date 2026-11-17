# REFOUNDATION-004 - Complexity report

Two numbers tell different stories and both are reported.

## Measured before/after (AST, whole repository)

| Metric | Before (14eaf61) | After (refoundation/004) | Direction |
| --- | --- | --- | --- |
| Modules | 510 | 512 | +2 |
| Python lines | 152,602 | 154,096 | +1.0% |
| Functions | 5,613 | 5,665 | +1% |
| CC > 10 | 698 | 703 | +5 |
| CC > 15 | 80 | 80 | 0 |
| Longest function | product/api.py create_app 949 lines / CC 240 | unchanged | 0 |
| Unreachable-from-entry-point modules | 75 / 20,558 lines | 75 / 20,558 lines | 0 |

Raw size and cyclomatic complexity did **not** fall. Claiming otherwise would be false. The
increase is one new responsibility (assessment, 889 lines) plus tests and the evaluator; the old
scoring module it replaces was 421 lines, and a second rule path in the adapters was deleted
entirely.

## What actually got simpler

| Change | Before | After |
| --- | --- | --- |
| Places that decide relevance | 3 (relevance.py scoring, adapters' pre-storage gate, CLI corroborate gate) | 1 (assessment.py); relevance.py is a 100-line facade with no logic |
| Admission storage semantics | one row per (obs, version), overwritten | append-only history + one explicit derived projection; readers have one path |
| Admission read path | correlated view (first attempt: 48.9 ms p50) | indexed projection (31.9 ms p50) |
| Work identity | ad-hoc title string inside a window function | one materialised work_key (DOI -> PMID -> title) used by every query |
| Time display | one formatter that widened month precision to a midnight instant | one precision-aware formatter + precision label |
| Quality reporting | hand-written numbers beside a JSON | Markdown generated from the JSON; --check fails on drift |
| Regression protection | 1 relevance test file (189 lines, 9 tests) | +16 named integrity tests including all QA-002 classes |

## What got more complex, and why it is justified

- One more dimension set on every decision (7 fields, JSON) and 4 more columns on the admission
  table. In exchange, a decision explains itself without reading the code, and re-judgement is
  provable. The cost is bounded: the extra fields are ~200 bytes per decision.
- One derived table (`admission_current`) that must be kept consistent. It is rebuildable from the
  history, is refreshed automatically, and is covered by the migration test.
- A larger vocabulary module. This is the domain complexity that previously existed as scattered
  keyword lists in two modules; it is now in one versioned place with a digest.

## Top remaining hotspots (unchanged, with the reason they were not touched)

| Function | Size / CC | Why it is still there |
| --- | --- | --- |
| product/api.py create_app | 949 lines / 240 | 48 routes; splitting it is safe only with route-level tests and a browser matrix |
| product/brief.py brief_markdown | 267 / 182 | generates a document; extraction is mostly presentation |
| product/device/build.py build_index | 349 / 116 | builds a derived index; needs a profiler-driven split |
| data_pipeline/validator.validate_snapshot | 262 / 113 | validation rules are deliberately dense; each branch is a gate |
| data_pipeline/pipeline._sync_locked | 412 / 105 | production sync state machine; needs its own acceptance run |
| product/dataset.py load_dataset | 294 / 94 | snapshot loader; candidate for an index-builder extraction |
| radar/graph.py technology_map | 263 / 87 | bitemporal query assembly; candidate for query-builder extraction |

## How to measure the next round

Re-run `python D:/DEPPSKK/data004-baseline/complexity.py <repo> <out.json>` and compare. The metric
that matters for future development is not LOC: it is the number of modules a typical change must
touch. This round reduced that for relevance (1 file + 1 config), work identity (1 file), time
display (2 files) and quality reporting (1 script).
