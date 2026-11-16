# PRODUCT-004 — Delivery Report

**Release:** PRODUCT-004 — Intelligence Brief Workbench
**Branch:** `feat/product-004-intelligence-workbench`
**Base:** `origin/feat/data-003-runtime-reliability` @ `c23429f` (PR #52), which contains production
commit `7415382` (DATA-003 Correction-1)
**Product version:** `2.3.0-product-004`
**Snapshot:** `2026-11-14T22:09:22Z-openfda` (91,457 collected records, 91,384 attributed, 59 tracked
organizations, 4 openFDA endpoints)
**Pull request:** https://github.com/ChazY11/medradar/pull/53 — Draft, stacked on PR #52
**Date:** 2026-11-17

---

## 1. Why this release exists

PRODUCT-001–003 built a trustworthy evidence browser: identity review, four time semantics, an
evidence drawer, a conservative comparison engine and a device model. The audit
(`product_004/PRODUCT_AUDIT.md`) found that the product still could not answer the analyst's actual
job: *"brief me on this competitor, and let me defend it."* There was no research object, no findings,
no way to interrogate a difference, and no deliverable.

PRODUCT-004 turns the evidence layer into a **research workflow**: define a question → explore
evidence → compare and explain → verify the record → take a sourced brief away.

## 2. What was delivered

| Layer | Deliverable |
|---|---|
| Backend | `medradar/product/brief.py`: company/comparison/device brief builders, `brief-findings-v1` rules, metric explanation, Markdown + Evidence Appendix CSV rendering. |
| API | `/api/brief`, `/api/brief/explain`, `/api/export/brief.md`, `/api/export/brief-evidence.csv`; additive `product_code` filter on event routes; `global_aggregations` on `/api/meta`; `technology` on the organization profile. |
| Data | Official FDA classification names retained per product code (7,098-row map) so technology views are interpretable where the FDA specialty is `Unknown`. |
| Frontend | `/brief` Intelligence Brief workspace, explain drawer, findings cards, comparison metrics, device history, changes and limitations; task-first home; Brief in primary navigation; organization/compare entry points; product-code filter in the event browser; mobile language switch; print stylesheet. |
| Tests | 14 new pytest tests; the existing product and repository suites; a Playwright acceptance script with 63 checks across four scenarios and regressions. |
| Docs | `product_004/`: audit, user problems, scope, journeys, design decisions, evidence contract, acceptance, known limitations, delivery report. Updated API contract, UI spec, data contract, architecture, README, CHANGELOG, next steps. |
| Evidence | 15 screenshots, 3 Markdown briefs, 3 evidence appendix CSVs and `acceptance-report.json` under `product_004/`. |

## 3. The three cases, with real data

### Case 1 — Medtronic, last five complete years

* **Question:** What does Medtronic's FDA device record show for 2021–2025, and what can it not
  establish?
* **How MedRadar guides it:** `/brief` → Company → `medtronic` → 5 complete years (default) → Build.
  The brief opens with scope, counting rule, executive tiles and findings.
* **Real data:** 3,426 records — 510(k) 159, PMA originals 9, PMA supplements 2,633, recalls 625.
  Verified 709 (20.7%), rule-verified 1,469 (42.9%), provisional 1,248 (36.4%).
* **Facts worth attention:** PMA supplements are 76.9% of the window; recalls fell from a
  160-record average in 2023–2024 to 46 in 2025 (−71.2%); P010031 has 179 supplement decisions in
  the window; the official specialty is `Unknown` for 73.9% of records, so the product-code view is
  the interpretable technology view; `LWS` (ICD, non-CRT) is the largest product code at 344 records.
* **What cannot be said:** that supplements are new products; that the recall decline is a safety
  improvement; that record counts measure innovation; that the applicant string is the current
  manufacturer.
* **Verification:** the pathway-concentration finding opens the event browser filtered to
  `types=pma_supplement` and 2021–2025; a record (`K251025`) opens the official FDA URL and the four
  separate time fields.
* **Output:** `medtronic-company-brief-en.md` (20.4 KB) and `medtronic-evidence-appendix.csv`
  (1.32 MB, 3,446 rows).
* **Reduced burden:** from roughly a dozen page transitions and manual counting to 3 user actions for
  the first brief (9 including verification and downloads).

### Case 2 — GE HealthCare vs Philips

* **Question:** Under the same counting rule, how do GE HealthCare and Philips differ for 2021–2025,
  and which differences are not comparable?
* **Real data:** GE HealthCare 493 records (129/0/3/361); Philips 963 (119/1/51/792).
* **Coverage:** source coverage is **symmetric** — both sides have 510(k), PMA and recall records in
  the window. The brief says so instead of inventing a coverage problem.
* **Differences that matter:** verification is asymmetric — GE HealthCare 100.0% evidence-verified,
  Philips 71.0% (271 provisional). Pathway mix diverges sharply (GE is recall-dominant; Philips is
  supplement-heavy). Eight product-code families are shared; five appear only for each side.
* **Explain:** the Recall measure opens definition, denominator 1,153 (361 + 792), per-side record
  lists with official links and a reproduce link.
* **What cannot be said:** that one company is safer, more innovative or commercially stronger; that
  shared product codes mean competing products.
* **Output:** `ge-healthcare-vs-philips-brief-en.md` (12.5 KB) and
  `compare-evidence-appendix.csv` (564 KB, 1,460 rows).

### Case 3 — PMA P980016

* **Question:** What is the official history of this PMA family, which relations are confirmed, and
  what cannot be concluded?
* **Real data:** 935 applications = 1 original approval + 934 supplements (1998-10-09 → 2026-10-29);
  934 confirmed supplement relations; 0 candidate relations; 0 recalls linked through the official
  K-number field.
* **Facts worth attention:** the family is a long supplement chain; no recall carries this
  application's K number in the snapshot.
* **What cannot be said:** that the device is safe, effective, commercially successful or still
  marketed; that no recall occurred; that a later supplement caused a later event.
* **Verification:** official FDA URL for the application and every supplement; MedRadar identifier
  shown beside the official one; family basis and candidate rule stated.
* **Output:** `device-p980016-brief-en.md` (14.5 KB) and `device-evidence-appendix.csv` (319 KB,
  935 application rows).

### Case 4 — No new changes

The deployment has no DATA-001 change ledger. The brief reports `not_configured` with an explicit
statement; `/api/changes` returns `total: 0`, `configured: false`; `/api/data-status` reports
`not_configured`. No record is described as new and no update is fabricated.

## 4. Acceptance and verification

* **Browser acceptance:** `node scripts/product_004_acceptance.mjs http://127.0.0.1:8790` — **63/63
  checks**, 0 console errors, 0 unhandled request failures. See `product_004/ACCEPTANCE.md` and
  `acceptance-report.json`.
* **Screenshots:** 15 files in `product_004/screenshots/` covering the brief, finding drill-down,
  evidence drawer, comparison, explain drawer, device history, no-changes state, Chinese, mobile,
  home, organization product-code table, compare page, product-code filter and print layout.
* **Exports:** three Markdown briefs and three evidence appendices in `product_004/exports/`.
* **New tests:** `tests/product/test_brief.py` — 14 tests. They assert, among other things, that the
  brief count equals `filter_events`, comparison sides equal `build_compare`, every finding cites
  real records, the Evidence Appendix has one row per window record, Explain reproduces metric
  values, the device brief separates confirmed/candidate facts, and the API contract/errors hold.
* **Full product suite:** 158 passed (python -m pytest tests/product -q), including the 14 new brief tests.
* **Repository suite:** 1,471 passed, 4 skipped, 297 subtests passed (python -m pytest -q -o addopts="", 237.97 s).
* **Governance:** licence inventory regenerated for the new derived artifacts
  (`docs/governance/DATA_INVENTORY.yaml`); the governance licence test passes.
* **Performance:** warm company brief 109 ms, comparison brief 99 ms, explain 42 ms, Markdown export
  60 ms, product-code events 61 ms. Cold dataset load remains ~10.8 s (existing DATA-003 behaviour);
  the first brief that needs the device index builds it once (~4 s). No new per-request heavy
  computation.

## 5. Product-value acceptance (G1–G8)

* **G1 User value — yes.** The first screen now starts from a research task; the brief produces
  findings, technology and device facts in one place, and the cases above were completed in 3–4 user
  actions each (not counting verification/downloads).
* **G2 Workflow completion — yes.** Question → evidence → analysis → brief is one route ending in
  Markdown/CSV/print. No page transition is required to obtain a deliverable.
* **G3 Evidence integrity — yes.** Brief numbers are computed by the same functions as the pages
  (tested), findings cite official records, every record has an official URL, and the appendix is
  the complete supporting set.
* **G4 Analytical honesty — yes.** The brief states the counting rule, time semantics, identity
  verification, ownership-at-event-time limits, coverage, relationship confirmation and "questions
  this cannot answer". Findings include a "what this does not mean" clause. The changes section never
  invents an update.
* **G5 Product experience — improved.** Task-first home, consistent navigation, bilingual brief,
  explainable comparison, mobile language switch and no overflow, print layout. Inherited pages keep
  their existing structure (with the organization provenance block collapsed to one line).
* **G6 Technical regression — yes.** Existing API routes and fields are additive; `tests/product` and
  the repository suite pass; the compare engine, device model, review service and data pipeline were
  not rewritten.
* **G7 Performance — acceptable.** No new database, cache or per-request index; one 7,098-row map.
  Warm brief requests are ~0.1 s; cold start is unchanged.
* **G8 Real browser acceptance — yes.** Scenarios A–D plus regressions executed in Chromium with
  screenshots, downloads and a machine-readable report. No fabricated user research or metrics.

## 6. What changed in the existing product

* Home is task-first; the stale "Product 001" label is gone; the whole-snapshot year chart now uses
  the snapshot aggregation instead of a 12-record page.
* Navigation includes **Brief**; labels were shortened so the global search remains usable at
  1440 px; the mobile panel exposes the language switch.
* Organization page: primary "Open intelligence brief" action, official product-code family table,
  provenance collapsed to a summary line.
* Compare page: "Open comparison brief" and "Explain any difference" links; the comparison engine is
  unchanged.
* Event browser: exact `product_code` filter and URL state.
* `/api/meta` and the organization profile gained additive fields.

## 7. What was not done (and why)

* No production deployment, sync change, cloud change or PR merge. The release is verified on a
  loopback server only.
* No accounts, saved briefs or collaboration: the URL and exports are the record; persistence needs a
  storage decision and is a separate project.
* No PDF library: print CSS is the PDF path.
* No AI narrative: findings are deterministic templates over computed values.
* No new finding types beyond the six validated rules.
* No ranking, innovation score, market-share estimate or causal claim.

## 8. Known limitations

See `product_004/KNOWN_LIMITATIONS.md`. The most important for a reader: the brief describes one
snapshot; the FDA specialty is often `Unknown`; 36.4% of Medtronic's window records rest on
provisional mappings; the tracked registry is 59 organizations; coverage and ownership limits remain;
the change ledger is not configured on this deployment; inherited pages are only partially Chinese.

## 9. Next phase

See `docs/product/NEXT_STEPS.md` (PRODUCT-004 follow-ups): saved briefs/workspace, change-aware
briefs when the ledger exists, more rules only after user testing, a second regulatory source with
the same contract, custom denominators in Explain, translation completion, and PDF only if needed.
