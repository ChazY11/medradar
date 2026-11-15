# E2E_TEST_REPORT

Browser end-to-end acceptance is now part of GitHub CI and runs against a real backend.

## What runs where

| Layer | What | Command |
|---|---|---|
| Unit + integration | 96 product tests in `tests/product/` (status derivation, metrics, review ledger, ownership, invariants, API contract) | `python -m pytest tests/product -q` |
| Browser acceptance | `tests/e2e/medradar.e2e.mjs`, 16 checks, Chromium, real uvicorn backend, committed hash-pinned snapshot | `node tests/e2e/medradar.e2e.mjs` |
| CI | `.github/workflows/e2e.yml` job "product browser acceptance": installs the browser fresh, builds the UI from source, starts the review service on :8811 and the public application on :8812, waits for health, runs the suite, uploads `build/e2e` (screenshots + report + server logs) | pull_request |
| Existing CI | `ci.yml` and `governance.yml` unchanged and still required | pull_request |

The E2E job fails the pull request when any check fails: there is no `continue-on-error` and no
`|| true` on the test step. Artefacts are uploaded with `if: always()` so a red run is diagnosable.

## Why the data is reproducible without a synthetic fixture

The product serves an immutable snapshot committed at `medradar/product/snapshot/`; the manifest
pins each file's SHA-256 and record count, and the loader reads only that directory. Running the
suite against the committed snapshot gives byte-identical data on every machine and needs no
network. The suite additionally derives its expectations from the API at run time (e.g. the CSV row
count is compared with `/api/events?…` for the same filters), so it does not hard-code a count that
could silently drift.

## Check matrix (local run, 16/16, executed twice)

| ID | What it proves | Result |
|---|---|---|
| E2E-01 | searching "Medtronic" reaches the organization page | PASS |
| E2E-02 | organization page states attribution confidence and matches the API record count (17,473) | PASS |
| E2E-03 | event-type filter narrows the table and agrees with the API total (2,622 recalls) | PASS |
| E2E-04 | evidence drawer shows the official identifier, official FDA link and verification status | PASS |
| E2E-05 | comparison renders both organizations, one shared window (2021-01-01..2025-12-31), the comparability verdict and the "not innovation" disclaimer | PASS |
| E2E-06 | CSV export row count equals the API total for the same filters (95 = 95) and the header carries `attribution_verification` | PASS |
| E2E-07 | Markdown comparison export contains the disclaimer, both names and the verification table | PASS |
| E2E-08 | Chinese interface renders Chinese headings and translated metric definitions | PASS |
| E2E-09 | mobile viewport (390x844) renders the organization page with 0px horizontal overflow | PASS |
| E2E-10 | an unknown filter value produces an explicit error/empty state, never a blank page | PASS |
| E2E-11 | an unknown organization shows an error state with retry and a way back | PASS |
| E2E-12 | no unexpected console errors and no failed requests (the two deliberate error-path 400/404 probes are excluded and counted in the evidence) | PASS |
| E2E-13 | the identity-review workspace unlocks with the token and lists the queue (25 rows) | PASS |
| E2E-14 | a review decision is appended and every unrelated organization keeps its exact count | PASS |
| E2E-15 | a withdrawn decision leaves both entries in the append-only history | PASS |
| E2E-16 | review writes require the token (401 without/with a wrong token) and the public application has no review route (404/405) | PASS |

Report and screenshots: `build/e2e/report.json`, `build/e2e/screenshots/` (CI artefact
`medradar-e2e`). A copy of the screenshots used in this delivery is in `screenshots/`.

## How to run locally

```bash
cd web && npm ci && npm run build && cd ..
MEDRADAR_REVIEW_TOKEN=e2e-local-token MEDRADAR_REVIEW_DB=build/e2e/review.db \
  python -m medradar.product.review serve --port 8811 &
python -m medradar.product.web --port 8812 &
cd tests/e2e && npm ci && npx playwright install chromium
ADMIN_BASE=http://127.0.0.1:8811 PUBLIC_BASE=http://127.0.0.1:8812 node medradar.e2e.mjs
```

If the Playwright browser download is unavailable locally, the suite falls back to an installed
Chrome channel; CI always installs the bundled Chromium, so the pipeline does not depend on any
developer machine's browser cache.

## Honest limitations

* Chromium only; no Firefox/WebKit matrix in this release.
* No visual-regression baseline: screenshots are artefacts for a human, not compared pixel-by-pixel.
* The snapshot is a frozen collection; the suite proves the product reads it correctly, not that a
  fresh collection would contain the same records (that is the retrieval-coverage problem, which is
  reported UNKNOWN rather than tested).
* Accessibility is covered only indirectly (roles/labels are asserted through Playwright's role
  selectors); no dedicated axe audit yet.
