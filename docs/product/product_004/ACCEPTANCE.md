# PRODUCT-004 — Acceptance Record

This is an internal engineering acceptance record, executed in a real browser against the real
snapshot. It is **not** external user research and contains no invented interviews, retention or
conversion numbers.

## Environment

| Item | Value |
|---|---|
| Commit base | `origin/feat/data-003-runtime-reliability` @ `c23429f` (PR #52) |
| Snapshot | `2026-11-14T22:09:22Z-openfda`, collected `2026-11-14T22:09:22Z`, openFDA last updated `2026-11-02` |
| Server | `python -m medradar.product.web --port 8790`, loopback only |
| Browser | Google Chrome (Playwright-driven, headless), viewport 1440×900 and 390×844 |
| Languages | English and Chinese (`medradar.lang`) |
| Date | 2026-11-17 (Asia/Shanghai) |
| Command | `node scripts/product_004_acceptance.mjs http://127.0.0.1:8790` |
| Machine report | `docs/product/product_004/acceptance-report.json` |

## Result summary

| Scenario | Checks | User operations | Result |
|---|---|---|---|
| A. Company research — Medtronic, 2021–2025 | 24 / 24 | 9 | PASS |
| B. Competitor comparison — GE HealthCare vs Philips | 14 / 14 | 4 | PASS |
| C. Device investigation — PMA P980016 | 9 / 9 | 4 | PASS |
| D. No new changes | 4 / 4 | 1 | PASS |
| R. Regression, mobile, Chinese, product-code filter | 10 / 10 | 7 | PASS |
| **Total** | **62 / 62** | | **PASS** |

The script fails the run on any check failure, console error or unhandled request failure. The final
report is written to `acceptance-report.json`.

## Scenario A — Company research

* **User goal:** brief a competitor's last five complete calendar years.
* **Steps:** `/brief` → type `medtronic` → Build. Then reproduce a finding in the event browser, open
  a record's evidence drawer, download the brief and appendix, and read the changes section.
* **Operations:** 9, including 4 verification/download steps. The first brief is produced by 2 user
  actions after opening the page (type the company, press Build); the window default is five complete
  years.
* **Completion:** yes.
* **What was checked:** URL scope, question, window, 3,426 records, ≥3 findings, product-code official
  names, PMA family section, attribution caution, finding drill-down filter (`types=pma_supplement`),
  evidence drawer official ID/URL/four time fields, Markdown sections and numbers, CSV header, row
  count and official URLs, change-ledger honesty.
* **Main difficulties:** the evidence/explain drawers load asynchronously; the acceptance script must
  wait for loaded content instead of the skeleton (fixed in the script). Server warning text is
  English in the Chinese UI and is explicitly labelled as the source text.
* **Screenshots:** `screenshots/01-company-brief.png`, `02-company-finding-records.png`,
  `03-company-evidence-drawer.png`.
* **Exports:** `exports/medtronic-company-brief-en.md` (20,366 bytes),
  `exports/medtronic-evidence-appendix.csv` (1,324,304 bytes, 3,446 rows).
* **Key numbers:** 3,426 records: 159 / 9 / 2,633 / 625; verified 709 (20.7%), rule 1,469 (42.9%),
  provisional 1,248 (36.4%); findings: pathway concentration, recall shift, PMA family scale,
  specialty-not-stated, provisional attribution.

## Scenario B — Competitor comparison

* **User goal:** compare GE HealthCare and Philips under one rule and explain the difference.
* **Steps:** open the comparison example → read comparability/coverage → open "Explain" on the Recall
  measure → inspect records and reproduce link → download both files.
* **Operations:** 4.
* **Completion:** yes.
* **What was checked:** shared window, 493 vs 963, explicit coverage assessment, verification
  asymmetry 100.0% vs 71.0%, product-code overlap finding, explain definition/denominator/records,
  identical-filter link, Markdown comparability and limitations, CSV side markers.
* **Main difficulties:** the difference that matters most for this pair is **not** source coverage
  (it is symmetric) but verification quality and pathway mix. The brief states both explicitly rather
  than manufacturing a coverage problem.
* **Screenshots:** `screenshots/04-compare-brief.png`,
  `05-compare-explain-difference.png`.
* **Exports:** `exports/ge-healthcare-vs-philips-brief-en.md` (11,983 bytes),
  `exports/compare-evidence-appendix.csv` (564,490 bytes, 1,460 rows).
* **Key numbers:** GE 493 = 129/0/3/361; Philips 963 = 119/1/51/792; recall explain denominator
  1,153 (361 + 792); 21 explainable measures.

## Scenario C — Device investigation

* **User goal:** understand a real PMA family and distinguish confirmed from candidate facts.
* **Steps:** open the device example or enter `P980016` → Build → inspect identity, application
  history, recalls, findings → open the official FDA link → download both files.
* **Operations:** 4.
* **Completion:** yes.
* **What was checked:** official PMA number, 934 supplements, separation of original and supplements,
  the no-confirmed-recall caution, candidate-relation language, official accessdata link, Markdown
  limitations, CSV application rows.
* **Main difficulties:** "confirmed relations" in the raw device API counts two representations of the
  same supplement (application relation + derived version relation). The brief counts the official
  supplement relations once (934), matching the device page, and the acceptance checks the tile value.
* **Screenshots:** `screenshots/06-device-brief.png`.
* **Exports:** `exports/device-p980016-brief-en.md` (14,487 bytes),
  `exports/device-evidence-appendix.csv` (319,046 bytes, 935 application rows).

## Scenario D — No new changes

* **Goal:** ensure absence of a ledger is not converted into "no news" or fake updates.
* **Steps:** open the company brief; read the changes section; call `/api/changes` and
  `/api/data-status`.
* **Result:** the brief reports `not_configured` with an explicit statement; `/api/changes` returns
  `total: 0`, `configured: false`; data status reports `state: "not_configured"`. No record is
  presented as new. PASS.
* **Screenshot:** `screenshots/07-no-new-changes.png`.

## Regression and experience checks

* Home is task-first; the stale "Product 001" eyebrow is gone; the whole-snapshot year chart uses the
  snapshot aggregation (>20 bars) rather than a 12-record page.
* Organization page links to the brief and shows official product-code families.
* Compare page links to the comparison brief.
* `/events?org=medtronic&product_code=NIK&from=2021-01-01&to=2025-12-31` returns 257 records through
  the new exact product-code filter, matching the brief/explain computation.
* Chinese brief renders analysis, findings, tiles and window in Chinese; the language switch remains
  reachable on mobile (390 px) via the navigation panel; no horizontal overflow
  (`scrollWidth == clientWidth == 390`).
* `screenshots/08-company-brief-zh.png`, `09-mobile-nav-zh.png`.

## Automated tests

| Suite | Result |
|---|---|
| `tests/product/test_brief.py` (new) | 14 passed |
| `tests/product` (all) | see final test run in `DELIVERY_REPORT.md` |
| Repository suite (`python -m pytest -q`) | see final test run in `DELIVERY_REPORT.md` |

## Performance observed

| Operation | Observed |
|---|---|
| Server cold dataset load (first request) | ~10.8 s (91,457 events) |
| Warm `/api/brief` company (Medtronic 5y) | ~0.15 s |
| First company brief with PMA families (device index build) | ~3.9–5.0 s once per process |
| Later briefs in the same process | 0.01–0.1 s |
| Warm `/api/compare`-based brief | ~0.08 s |
| Device brief after index build | ~0.02 s |

No per-request index rebuild was added; the only new resident structure is the 7,098-row
classification map.

## Issues found and fixed during acceptance

1. Evidence/explain checks read the drawer before its async content loaded (test fixed to wait).
2. Adding a ninth navigation item squeezed global search to ~40 px at 1440 px (labels and spacing
   fixed, search width protected).
3. At 390 px the header search and page actions overflowed (`scrollWidth 491`); both now shrink/wrap.
4. Device "confirmed relations" double-counted supplements; the brief counts official supplement
   relations once.
5. The homepage whole-snapshot chart was fed by a 12-row page; it now uses `/api/meta`
   `global_aggregations`.
6. Screenshot tooling intermittently timed out at long scroll positions; the acceptance script uses
   Playwright directly with a 120 s screenshot timeout and `animations: "disabled"`.

## Honest limitations of this acceptance

* One operator, one machine, one snapshot; no external users, no interviews, no retention or
  conversion metrics are claimed.
* Chromium/Chrome only; Firefox and Safari were not exercised.
* The change-ledger paths (`available`, `no_changes`) are covered by unit tests with synthetic state
  and by the honest `not_configured` path here; this deployment has no live ledger to exercise.
* The acceptance verifies that the PDF **print layout** exists; it does not claim a generated PDF
  artefact.
