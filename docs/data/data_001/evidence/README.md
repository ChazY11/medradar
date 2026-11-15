# DATA-001 Evidence

This directory contains reproduction evidence, not marketing screenshots.

| File | What it proves |
|---|---|
| `source-check-live.json` | Live openFDA probe on 2026-11-15/16: endpoint versions, totals, request count. |
| `real-sync.json` | Sanitized result of an isolated real scoped reconciliation: elapsed time, peak process working set, requests, response bytes, counts, snapshot ids, validation metrics. |
| `server-baseline-2026-11-16.txt` | Read-only live server inspection before any deployment. |
| `server-final-baseline.txt` | Final read-only check: production still serves the old snapshot and SHA after all isolated tests. |
| `server-isolated-sync.txt` | Real sync in `/tmp/data001` on the 2 vCPU / 4 GB server, with `/usr/bin/time -v`, plus live service health before/after. |
| `acceptance-tests.txt` | Offline test command and count summary. |
| `ui-data-status-real.png` | Data Status page served from the isolated real pipeline state (captured locally). |

Raw openFDA responses, the full 91k-event snapshot and the pipeline SQLite database are not
committed: they are large runtime data. The commands below reproduce them.

```bash
python -m pytest tests/data_pipeline tests/product -q
python -m medradar.data_pipeline --root <state> bootstrap --from medradar/product/snapshot
python -m medradar.data_pipeline --root <state> sync --force --json
python -m medradar.data_pipeline --root <state> status --json
```

The real run used no API key. The request count is far below the unauthenticated 900/day
budget.
