# PRODUCT-004 — Design Decisions

Each decision records the alternative that was rejected and the user task it improves. Decisions are
binding for this release unless a later document supersedes them.

## D1. Branch from PR #52, not from `main`

**Observed state (2026-11-17):** the open stack is
`main → #46 → #47 → #48 → #49 → #50 → #51 → #52`, each PR based on the previous head. PR #52 is
`feat/data-003-runtime-reliability` @ `c23429f` and contains production commit `7415382`
(DATA-003 Correction-1). `main` has none of PRODUCT-001/002/003 or DATA-001/002/003.
**Decision:** create `feat/product-004-intelligence-workbench` from
`origin/feat/data-003-runtime-reliability` and open a stacked Draft PR with #52 as base.
**Rejected:** branching from `main` (would remove the product and data layers this release builds on).

## D2. A brief is a derived artefact that reuses the existing measurement code

`medradar/product/brief.py` calls `dataset.filter_events`, `dataset.counts`, `aggregate`,
`compare.build_compare` and the PRODUCT-003 device payload. It never re-implements a count.
**Why:** the analyst must be able to move from a brief number to the same number on the event
browser or Compare page. Reusing the code makes disagreement a bug that tests can catch.
**Rejected:** a separate reporting query path (two definitions of the same metric) and storing
precomputed briefs (a second source of truth).

## D3. Six finding rules, each with evidence and a "does not mean" clause

Implemented: pathway concentration, recall-dominant window, year-on-year record shift, PMA family
scale, specialty-not-stated, provisional-attribution caution. Every rule has an explicit threshold,
returns its inputs, cites records and is disabled when the data does not support it.
**Why:** the audit found that the analyst must eyeball tables to reach three facts. A small set of
transparent rules gives a first draft without inventing causal or predictive claims.
**Rejected:** anomaly detection or a model (unverifiable), and dozens of rules (noise, false claims).
**Bound:** if no rule fires the brief says so; it does not manufacture an observation.

## D4. Technology areas use the official product code *and* the official classification name

The audit found the "medical specialty" chart dominated by the FDA's own `Unknown` value (11,522 of
17,473 Medtronic records; 2,520 of 3,426 in the 2021–2025 window). The dataset is extended with a
bounded 7,098-row classification map (device name, specialty, class, regulation number).
**Why:** the question "where is this company active?" remains answerable without inventing a
MedRadar taxonomy. `LWS` → "Implantable Cardioverter Defibrillator (Non-Crt)" is an official fact.
**Rejected:** hiding the Unknown bucket, dropping those records, or inventing technology segments.
**Cost:** ~2 MB resident; no per-request build.

## D5. The comparison brief explains, it does not rank

The comparison reuses `build_compare` and adds 21 measures whose values, definitions, denominators
and records can be opened. The brief states source coverage explicitly (symmetric or not) and keeps
the existing warnings.
**Why:** "why is this different?" was unanswerable; "which company is better?" is not answerable from
FDA records. The product answers the first and refuses the second.
**Rejected:** composite scores or a ranking.

## D6. Compare page keeps its role; the brief is the output layer

The existing Compare page remains the interactive matrix tool and gains two links: "Open comparison
brief" and "Explain any difference". No second comparison engine or duplicate page was built.
**Why:** the audit found Compare analytically strong; replacing it would discard working behaviour.
**Rejected:** rebuilding Compare or moving its controls into the brief.

## D7. Structured question form, not a chat box

The brief form is a mode selector, target input (organization key or device identifier), window chips
and event-type chips. The resulting URL is the research record.
**Why:** the task explicitly asks for clear structured interaction; a URL can be pasted into a
meeting note and re-run later.
**Rejected:** natural-language prompt + LLM (non-deterministic, unauditable).

## D8. Evidence appendix is a first-class export

The CSV has one row per supporting record with section, metric, official id, event type, all time
fields, official URL, product code, specialty, applicant, attribution state, verification state and
snapshot id. The brief's Markdown links the counting rule and the appendix row count.
**Why:** a manager's "where does this come from?" must be answerable without the UI.
**Rejected:** only summarised aggregates (not auditable) and only raw CSV (no question, no scope).

## D9. Print CSS instead of a PDF dependency

`window.print()` plus a print stylesheet hides navigation/forms and avoids breaking findings across
pages.
**Rejected:** adding a PDF library and a second rendering path for one deliverable format.

## D10. Bilingual at the brief level

Findings and brief prose are generated in both languages by the server; the UI selects by locale. The
main brief workflow has Chinese labels, findings, tiles and exports. Existing English-only server
warning messages are labelled "（英文原文）" in Chinese rather than silently presented as translated.
**Why:** partial translation that pretends to be complete is worse than an explicit label; the new
workflow is fully covered.
**Known gap:** the inherited Compare/Sources pages still contain English explanatory copy (recorded in
`KNOWN_LIMITATIONS.md`).

## D11. Product-code filter added to the existing event browser

Findings and product-family rows need to open the records behind a product code. `product_code` is
added to `dataset.filter_events`, `/api/events`, `/api/organizations/{key}/events`,
`/api/export/events.csv` and the event-browser URL state.
**Why:** a text search for `NIK` could match other fields; an exact filter makes the drill-down
reproducible.
**Rejected:** linking with a fuzzy query and claiming it is the exact set.

## D12. Fix the homepage chart and language/nav defects found during implementation

* The homepage chart labelled "records per year across the whole snapshot" was fed by the 12-row
  "latest records" request, so it drew one bar. `/api/meta` now exposes the already-computed
  global aggregation and the chart uses it.
* Adding a ninth navigation item squeezed global search to ~40 px at 1440 px. Primary nav labels
  were shortened (Brief, Events, Sources, Review), spacing reduced and search given a protected
  width.
* At 390 px the header search and page actions overflowed (scrollWidth 491 vs 390). Both now shrink
  or wrap; the mobile language switch is inside the navigation panel (it was hidden at ≤768 px).

Each fix is tied to a concrete user task: read the whole-snapshot trend, use search, and read/switch
language on a phone.

## D13. Version and API are additive

Product version is `2.3.0-product-004`. New endpoints: `/api/brief`, `/api/brief/explain`,
`/api/export/brief.md`, `/api/export/brief-evidence.csv`. Existing responses gain fields
(`global_aggregations`, `technology`) and optional query parameters (`product_code`); nothing is
removed or renamed.
