# REFOUNDATION-004 - Performance measurements

All measurements below were produced on this host in this session. They are in-process Python
benchmarks against a copy of the production-shaped ledger, not browser timings. Browser timings
from QUALITY-001 remain the reference for cold-start behaviour; they were not re-measured after
the web bundle rebuild and are therefore marked NOT RE-MEASURED.

## Environment

| Item | Value |
| --- | --- |
| Host | Windows 11, the development machine used for this round |
| Python | 3.12.10 |
| Database | SQLite, WAL, single writer (PipelineLock) |
| Dataset | copy of radar.db: 8,593 observations, 1,137 Crossref, 6,936 openFDA, 484 PubMed, 31 Dräger, 5 Philips |
| Iterations | 40 per query, warm connection, p50/p95/max reported |
| Script | D:/DEPPSKK/data004-baseline/bench_feed.py, run_bench.ps1 |
| Comparison | old code = feat/radar-001-live-intelligence-graph (HEAD 14eaf61); new code = refoundation/004 |

## Result: intelligence feed query

| Query | Before p50 | Before p95 | After p50 | After p95 | Change p50 |
| --- | --- | --- | --- | --- | --- |
| Default feed (HIGH, 30-day window, order=published, limit 20) | 23.3 ms | 41.8 ms | **31.9 ms** | **56.1 ms** | +37% |
| Feed, unfiltered (no admission, limit 20) | 143.5 ms | 159.1 ms | 150-192 ms (run variance) | 186-235 ms | parity to +30% |
| Admission summary (30-day counts) | 49.2 ms | 60.1 ms | 66.8 ms | 98.3 ms | +36% |

Interpretation and honesty notes:

- The feed got slower because it now returns a richer admission object (decision, dimensions,
  reasons) and joins the current-decision projection instead of a single narrow table. The first
  version of the new code was 48.9 ms p50 / 85.7 ms p95; replacing a correlated MAX view with an
  explicit derived projection and materialising the work key brought it to 31.9/56.1. The remaining
  cost is acceptable for a page of 20 rows against a ~1 s page budget, but it is a real regression,
  not a win.
- The unfiltered query is dominated by the window-function dedupe over 8.6k rows and varies between
  runs on this host; the reported range is the honest one. Pagination is offset-based and still
  scans; keyset pagination is the next step.
- No query in the benchmark exceeded 250 ms. The page budget is not at risk; the p95 regression is
  the number to watch.

## What was explicitly protected

- Snapshot activation still never blocks a request (DATA-003 design: background loader, single
  reference swap). This round did not touch `DatasetHolder`.
- The graph is still materialised into a derived store with invalidation; a classification change
  invalidates only the affected observation's projection (now also queued for re-judgement).
- The new admission projection is a single indexed table read; no full-history scan is on the read
  path.
- No new caches were introduced, so the "new intelligence is not visible because of a cache"
  failure mode was not added.

## Not measured this round (do not claim otherwise)

- Cold start / first card / settle on desktop and mobile after the bundle rebuild.
- API latency under the production service (uvicorn, TLS terminator, tunnel).
- Memory peak of the full product service with the snapshot.
- Data-processing throughput of a full source sync.

Those require the production host or a local browser matrix and are listed in the final report as
NOT VERIFIED.
