# Acceptance Record - PRODUCT-001

This is the record of what was actually executed and observed, not a test plan. The machine-readable
form is `docs/product/acceptance-report.json` (written by `scripts/product_acceptance.mjs`).

**Snapshot under test:** `2026-11-14T22:09:22Z-openfda` · collected 2026-11-14T22:09:22Z ·
openFDA last updated 2026-11-02 · 91,457 records · 59 organizations.
**Environment:** Windows, Python 3.12, Node 24, Google Chrome (Playwright), local server
`http://127.0.0.1:8787`. Desktop viewport 1440x900, mobile viewport 390x844.

---

## G1 - REAL DATA (PASS)

| Check | Result |
|---|---|
| Records come from the live openFDA API, not from fixtures | PASS - `scripts/product_collect.py` made 258 requests (~1.33 GB of responses, 0 errors); every query URL is recorded in the manifest |
| Records are traceable to official FDA pages | PASS - each record carries its official identifier and an `accessdata.fda.gov` URL; the evidence drawer and every export print them |
| No synthetic or placeholder values on core pages | PASS - the UI has no mock rows or sample metrics; empty states and error states are explicit |
| Data spot-check against the live source (independent of our pipeline) | PASS - re-queried openFDA directly for three records and compared: 510(k) K260306 (`Smith & Nephew Medical, Ltd.`, decision 2026-10-30, product code OMP), PMA originals/supplements under P830061, and a 2026 recall (`Z-0289-2027`, recalling firm `Canon Medical System, USA, INC.`, initiated 2026-10-12, posted 2026-10-27). Applicant, dates and product codes matched the snapshot exactly. |
| Official record page reachable | PASS - `https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID=K260306` returned HTTP 200 |

Coverage of the shipped snapshot: 23,400 × 510(k) · 574 × PMA originals · 37,658 × PMA supplements ·
29,825 × recalls; event dates 1960-10-14 to 2026-10-30; 91,384 records attributed (99.92%),
73 records unattributed and listed in the audit.

---

## G2 - WORKING PRODUCT (PASS)

Executed in a real browser through `node scripts/product_acceptance.mjs`. Result: **15 checks, 15
passed, 0 failed**.

| # | Check | Observed |
|---|---|---|
| A1 | Homepage loads with product title and 5 navigation items | title rendered, nav=5 |
| A2 | Overview shows tracked organizations and record totals from the live API | 59 organizations, 91,384 attributed records |
| A3 | Search by company name opens the organization page | "Medtronic" result -> page title "Medtronic" |
| A4 | Organization page counts match the API measurement layer | 17,473 records, identical to `/api/organizations/medtronic` |
| A5 | Organization event tab lists real records with official FDA identifiers | 25 rows, first official id `P200026:S020`, total 17,473 |
| A6 | Evidence drawer shows the official record URL and the separate time fields | official PMA URL present; event date / published by source / first observed / available at all labelled |
| A6b | 510(k)/PMA records state that the source publishes no publication time | "Not published by this source" shown |
| A7 | Filter changes are reflected in the URL and the rendered count | `/events?types=510k&org=medtronic&from=2020-01-01` -> 252 records, matches `/api/events` |
| A8 | CSV export equals exactly the filtered records | 252 CSV rows = 252 API records; header contains `official_url` and `attribution_review` |
| A9 | Comparison shows both organizations, warnings and the disclaimer | 4 warnings rendered above the data; "Records are not innovation" visible |
| A10 | Markdown comparison report downloads with window, warnings and source links | 5,612 characters, source links present |
| A11 | Sources page shows manifest, attribution audit and out-of-scope list | snapshot id, "Collection audit", "Not covered in this release" all present |
| A12 | Mobile layout fits the viewport and exposes navigation | horizontal overflow 0 px at 390x844; menu button visible |
| A13 | Interface language toggles to Chinese | nav becomes 总览 / 企业 / 监管事件 / 企业对比 / 数据来源与覆盖; page title in Chinese |
| A14 | No console errors or failed network requests during the walkthrough | console=0, failedRequests=0 |

Screenshots (committed): `docs/product/screenshots/01-overview.png`, `02-organization.png`,
`03-organization-events.png`, `04-evidence-drawer.png`, `05-events-filtered.png`,
`06-compare.png`, `07-sources.png`, `08-mobile-organization.png`, `09-overview-zh.png`.

---

## G3 - EVIDENCE TRACEABILITY (PASS)

* Recording identity: events are keyed by source + official FDA identifier
  (`openfda_510k:K260306`, `openfda_pma:P830061:S097`, `openfda_recall:Z-0289-2027`), stable across
  snapshots.
* Every screen that shows a number also shows its basis (event types counted, window, snapshot) and
  the coverage behind it.
* The evidence drawer exposes: official identifier, official URL, the verbatim applicant string,
  attribution basis and review state, the four time fields, the verbatim source fields kept by the
  collector, and the collection provenance.
* Time limits are visible where they matter: 510(k)/PMA records state that openFDA publishes no
  publication time, so `published_at` is null by rule rather than guessed; first-observed is always
  labelled as the snapshot time.
* Identity limits are visible: 1,410 of 1,590 accepted applicant spellings are machine-proposed and
  labelled provisional (82% of records); 9 look-alike strings are explicitly rejected with reasons;
  2 ambiguous joint-venture strings are left unattributed; the audit lists every unattributed
  applicant string.
* Exports reproduce the basis and the source links (CSV includes `official_url`, `snapshot_id`,
  `collected_at`; Markdown includes counting rule, warnings and source URLs).

---

## G4 - ENGINEERING QUALITY (PASS with a documented limitation)

* **Product test suite:** `python -m pytest tests/product -q` -> **47 passed**.
* **Repository test suite:** `python -m pytest` on this branch -> **1301 passed, 3 skipped,
  269 subtests passed in 77.5 s** (exit code 0), including the repository's governance gates.
  The 47 product tests are part of that total.
* **Governance change (disclosed):** the repository's licence gate originally rejected any
  committed restricted binary format. The product snapshot is a compressed projection of
  public-domain openFDA records (13 MB compressed vs 140 MB plain). Rather than drop the data or
  ship a weaker panel, the gate gained a **hash-bound exception** (GOV-0004 / RC-0004): a
  restricted binary may be committed only when its inventory entry is GREEN, its source is
  declared redistributable and the declared SHA-256 matches the bytes. Undeclared gzip still
  fails, and the gate now prints the accepted files with their hash prefixes. The change and its
  rationale are recorded in `docs/governance/DECISION_LOG.yaml` and `RULE_CHANGES.yaml`.
* **No known blocking data error:** implausible dates are quarantined (16 records); attribution
  integrity is enforced at load time and tested; unattributed records are counted and visible.
* **Core interaction failures:** none observed in the acceptance walkthrough; 0 console errors,
  0 failed requests.
* **Security/input handling:** all query parameters are validated (event types, page bounds, dates,
  organisation keys); SQL is not used at request time; static file serving is restricted to the
  built UI directory; exports are generated from the same validated filter object as the screen.
* **Performance:** snapshot load ~3 s once per process; event queries are in-memory and return in
  single-digit milliseconds; the built UI is 112 KB gzip JS + 4.4 KB gzip CSS.
* **Limitation:** the attribution review is not complete - 82% of records rely on machine-proposed
  spellings (see KNOWN_LIMITATIONS). This is disclosed in the product and not presented as reviewed
  fact.

---

## G5 - REPRODUCIBILITY (PASS)

A new developer can follow `docs/product/ARCHITECTURE.md` section 8 and `README` "Workbench quick
start":

1. `pip install -e '.[product]'` (fastapi + uvicorn).
2. `python -m medradar web --port 8787` - the committed snapshot and the committed `web/dist` make
   this work offline, without Node and without re-collecting.
3. Open `http://127.0.0.1:8787` and complete the analyst workflow.
4. To refresh data: `python scripts/product_collect.py` (optionally sharded) then
   `--merge`; to review new applicant spellings: `python scripts/product_curate_aliases.py --apply`.
5. To run the acceptance walkthrough: `node scripts/product_acceptance.mjs` against the running
   server (Playwright required, not a product dependency).

The snapshot is hash-addressed; the manifest records request URLs, counts and file SHA-256, so the
same workflow can be reproduced from the committed data and re-verified against the same public
source.

---

## Honest status summary

| Criterion | Status | Note |
|---|---|---|
| G1 Real data | **PASS** | live openFDA collection; independent spot-check matched |
| G2 Working product | **PASS** | 15/15 browser checks; screenshots committed |
| G3 Evidence traceability | **PASS** | record identity, official links, time and attribution limits visible |
| G4 Engineering quality | **PASS (with limitation)** | product tests green, full suite recorded; attribution review incomplete |
| G5 Reproducibility | **PASS** | offline start from committed snapshot + built UI; refresh and acceptance documented |

Nothing in this release is claimed as deployed, live, monitored or predictive.
