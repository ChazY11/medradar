# MedRadar browser acceptance suite (PRODUCT-002)

Real Chromium against a real backend. No mocking: the suite drives the built React workbench and
compares what the screen shows with what the API returns.

## What it runs against

* The **committed, hash-pinned openFDA snapshot** in `medradar/product/snapshot/`. It is immutable
  and its SHA-256 values are in the manifest, so the run is reproducible and offline. No synthetic
  fixture is needed and no network request is made.
* Two origins:
  * `ADMIN_BASE` (default `http://127.0.0.1:8811`) - the identity-review service, which also serves
    the public read-only API and the built UI.
  * `PUBLIC_BASE` (default `http://127.0.0.1:8812`) - the public application only, used to prove
    that no review write route exists there.

## Run locally

```bash
# 1. build the UI once
cd web && npm ci && npm run build && cd ..

# 2. review service (writes go to a throwaway ledger)
MEDRADAR_REVIEW_TOKEN=e2e-local-token \
MEDRADAR_REVIEW_DB=build/e2e/review.db \
python -m medradar.product.review serve --port 8811 &

# 3. public application
python -m medradar.product.web --port 8812 &

# 4. the suite
cd tests/e2e && npm ci && npx playwright install chromium
node medradar.e2e.mjs        # ADMIN_BASE / PUBLIC_BASE / MEDRADAR_REVIEW_TOKEN from the environment
```

Locally, if the Playwright browser download is unavailable, the suite falls back to the installed
Chrome channel; CI always installs the bundled Chromium.

## Output

* `build/e2e/report.json` - one row per check (id, description, passed, evidence).
* `build/e2e/screenshots/` - a screenshot per interactive surface.
* Exit code 0 only when every check passes, 1 when any check fails, 2 when the backend is down.
  The GitHub workflow `.github/workflows/e2e.yml` fails the job on a non-zero exit code.
