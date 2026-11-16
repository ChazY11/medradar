# PRODUCT-004 — User Journeys (implemented, with real data)

All figures below were produced by the running workbench from snapshot
`2026-11-14T22:09:22Z-openfda` (collected 2026-11-14T22:09:22Z, openFDA last updated 2026-11-02).
Operation counts are from `scripts/product_004_acceptance.mjs`; they count user actions, not HTTP
requests.

---

## Journey 0 — Define the question

**Where:** `/brief` (primary navigation: **Brief**).

1. Choose a mode: **Company**, **Compare** or **Device**.
2. Enter an organization key (`medtronic`) or a device/PMA identifier (`P980016`).
3. Choose a window: 3, 5 or 10 complete calendar years, or explicit dates.
4. Optionally narrow event types.
5. Press **Build intelligence brief**.

The URL becomes `/brief?mode=company&org=medtronic&years=5`; it can be pasted into a meeting note and
re-opened later with the same scope. No chat box, no hidden state.

**If the user does nothing**, the page offers three one-click examples (Medtronic 2021–2025,
GE HealthCare vs Philips, PMA P980016). This is the fastest path to a real brief.

---

## Journey 1 — Case A: Medtronic, last five complete years

**Question:** *What does Medtronic's FDA device record show for 2021–2025, and what can it not
establish?*

**Path (3 user actions):** open `/brief`, type `medtronic`, press Build. The window defaults to five
complete years and all event types. Total measured operations in the acceptance run: 9 (including
verification and both downloads).

**What the brief shows (real):**

* Window 2021-01-01 → 2025-12-31; 3,426 attributed records.
* 510(k) 159 · PMA originals 9 · PMA supplements 2,633 · recalls 625.
* Verification: 709 evidence-verified/human-reviewed (20.7%), 1,469 rule-verified (42.9%), 1,248
  provisional (36.4%).
* Technology areas by official product code: `LWS` Implantable Cardioverter Defibrillator (Non-Crt)
  344 records; `NIK` CRT-D 257; `NVZ` implantable pulse generator 208; `LGW` spinal-cord stimulator
  155. The FDA medical-specialty table states `Unknown` for 2,520 of 3,426 records (73.6%) — the
  reason the official product-code view exists.
* PMA families: P010031 179 supplements in window, P980016 174, P980035 158.
* Recent records: 2026-10-30 → 2025-12; every row opens an evidence drawer.

**Findings (real):**

1. `pathway_concentration` — 2,633 of 3,426 records (76.9%) are PMA supplements.
2. `activity_shift_recall` — recalls fell from a 160-record average in 2023–2024 to 46 in 2025
   (−71.2% against that average).
3. `pma_family_scale` — P010031 has 179 supplement decisions in the window.
4. `specialty_not_stated` (caution) — 73.9% of window records have no usable medical specialty.
5. `provisional_attribution` (caution) — 36.4% of records rest on provisional applicant mappings.

**Verify:** each finding links to the event browser with the same filters (PMA supplement,
2021–2025). Opening a record shows official ID `K251025`, the official FDA URL, event date,
publication status, first-observed time and available-at. The acceptance run checks all four.

**Cannot conclude:** that supplements are new products; that the recall decline is a safety
improvement; that record counts measure innovation; that the applicant string is the current
manufacturer; that unnamed subsidiaries are covered.

**Take away:** Company brief Markdown (20,366 bytes, 8 sections plus limitations) and Evidence
Appendix CSV (1,324,304 bytes, 3,446 rows: window records plus finding citations), both stamped with
the snapshot id.

**Before PRODUCT-004:** the same facts required the organization page (all-time), the event browser
with manually recreated filters, the specialty chart (dominated by Unknown), the device explorer
(separately), and a Markdown export that had no window, findings or "cannot conclude" section —
roughly a dozen page transitions and manual counting.

---

## Journey 2 — Case B: GE HealthCare vs Philips

**Question:** *Under one counting rule, how do GE HealthCare and Philips differ for 2021–2025, and
which differences are not comparable?*

**Path (2 user actions):** open the one-click example, or select Compare and two organizations; press
Build. Acceptance: 4 operations including the explain drawer and exports.

**What the brief shows (real):**

* GE HealthCare 493 records: 129 510(k), 0 PMA originals, 3 supplements, 361 recalls.
* Philips 963 records: 119 510(k), 1 PMA original, 51 supplements, 792 recalls.
* Source coverage is **symmetric**: both sides have 510(k), PMA and recall records in the window. The
  brief states this explicitly, including that a symmetric coverage does not make totals a
  performance comparison.
* Verification is **asymmetric**: GE HealthCare 100.0% evidence-verified (493/493); Philips 71.0%
  (684/963, 271 provisional). This is a data-confidence difference, not an activity difference.
* Product-code overlap: 8 codes are shared in the shown set; 5 appear only for GE HealthCare and 5
  only for Philips. Shared codes are an FDA classification overlap, not proof of competing products.
* 21 explainable measures: all records, each pathway, top specialties and top product-code families.

**Explain this difference:** opening `type.recall` shows the definition (recall = safety action),
window, denominator 1,153 (361 + 792), one row per side with up to 20 records and official links, and
a link that applies the identical filter in the event browser.

**Cannot conclude:** that GE is "safer" because its window is recall-dominant, that Philips is more
innovative because it has more PMA activity, or any ranking. A recall share is not a defect rate, and
a PMA supplement is not a new device.

**Take away:** comparison brief Markdown (11,983 bytes) and Evidence Appendix CSV (564,490 bytes,
1,460 rows, marked `side:ge_healthcare` / `side:philips`).

**Before PRODUCT-004:** Compare could show the matrices but could not explain a cell, could not show
shared/exclusive technology overlap, and exported a table report without findings or limitations.

---

## Journey 3 — Case C: PMA P980016, a real device family

**Question:** *What is the official history of this PMA family, which relations are confirmed, and
what cannot be concluded?*

**Path (2 user actions):** open the one-click device example or type `P980016`; press Build.
Acceptance: 4 operations including the official link and both downloads.

**What the brief shows (real):**

* 935 applications in the family: 1 original approval + 934 supplements (1998-10-09 → 2026-10-29).
* 934 confirmed supplement relations (same official PMA number); 0 candidate relations.
* 0 recalls linked through the official K-number field.
* Findings: `pma_supplement_history` (a long supplement chain; each supplement changed an approved
  device) and `no_confirmed_recall_link` (caution: no link is not evidence that no recall occurred;
  unlinked recalls remain in the unlinked browser).

**Verify:** the original approval and supplements carry official URLs; the device identity shows the
official PMA identifier beside the internal MedRadar identifier; the report states that the family is
the FDA application hierarchy, not a commercial product line.

**Cannot conclude:** that the device is safe, effective, commercially successful or still marketed;
that a late supplement caused a later recall; that a missing recall link means no recall.

**Take away:** device brief Markdown (14,487 bytes) and Evidence Appendix CSV (319,046 bytes; 935
application rows).

---

## Journey 4 — Case D: no new changes

The deployment used for this release has no DATA-001 change ledger. The brief's changes section
reports `not_configured` and states: *"This deployment has no continuous-pipeline change ledger. No
claim is made about records added, updated or removed since the snapshot; the brief describes the
snapshot only."*

The API confirms `/api/changes` → `total: 0`, `configured: false`, and `/api/data-status` →
`state: "not_configured"`. No record is presented as new, and no "latest update" is fabricated.

If a ledger is configured but reports zero changes, the state is `no_changes` with the same
no-fabrication rule. If it reports items, they come from the ledger with their own observed time —
never confused with FDA decision dates.

---

## Cross-cutting verify and deliver

From any brief:

1. **Verify a finding** → "View supporting records" opens the event browser filtered to the same
   organization/pathway/window; each row opens the evidence drawer.
2. **Verify a metric** → "Explain" opens definition, numerator, denominator, filters and records.
3. **Verify provenance** → the scope strip shows snapshot id, collection date and counting rule; the
   Sources page holds the full contract.
4. **Deliver** → Markdown brief, Evidence Appendix CSV, or browser Print/PDF (print CSS removes
   navigation and forms).

## What this changes for the analyst

| Task | Before | After |
|---|---|---|
| State the question and scope | Not possible; implicit page state | One form; scope encoded in the URL |
| Reach a first defensible fact | Read tables across 2–4 pages | Brief opens with 2–5 evidence-backed findings |
| Explain a comparison difference | Manually rebuild filters | Definition + denominator + records + reproduce link |
| Interpret technology mix | Specialty chart dominated by `Unknown` | Official product-code families with FDA names |
| Include device evidence | Separate device explorer | PMA families and device brief linked from the same object |
| Produce something to send | All-time Markdown with no findings | Windowed brief with scope, findings, evidence and limitations |
| Check the latest changes | Data-status page | Changes section states ledger state honestly |
