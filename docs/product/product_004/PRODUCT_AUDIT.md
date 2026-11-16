# PRODUCT-004 Phase 0 — Independent Product Audit

**Baseline:** `origin/feat/data-003-runtime-reliability` (PR #52, head `c23429f`), which contains
production commit `7415382` (DATA-003 Correction-1). The worktree was created from that branch, not
from `main`: the stacked PR chain #46 → #47 → #48 → #49 → #50 → #51 → #52 is still open, so `main`
does not contain PRODUCT-001/002/003 or DATA-001/002/003.

**Method:** the workbench was started from this checkout (`python -m medradar.product.web --port 8790`,
committed snapshot `2026-11-14T22:09:22Z-openfda`), exercised in Chromium at 1440×900 and 390×844,
in both English and Chinese, and inspected at the API and source level. All numbers below were
produced by that running instance; nothing in this document is estimated.

---

## 1. What exists and works

| Area | State | Evidence |
|---|---|---|
| Snapshot | 59 tracked organizations, 91,457 collected records, 91,384 attributed, 4 openFDA endpoints, event dates 1960-10-14 → 2026-10-30, collected 2026-11-14 | `/api/meta` |
| Organization search | Organization-level results with match field and record count; explicit "not a full FDA applicant registry" note | `/api/search?q=medtronic` |
| Regulatory event browser | URL-state filters (org, type, dates, category, review, text), filtered totals, per-year chart, evidence drawer | `/events?org=medtronic&types=510k&from=2024-01-01&to=2024-12-31` = 30 records |
| Evidence drawer | Official id + URL, four time fields, verbatim applicant string, attribution basis/review, snapshot provenance | `POST`-free `/api/events/{id}`, UI drawer |
| Compare | 2–4 organizations, one window, one counting rule, ownership basis, review filter, comparability verdict, six warnings, pathway/specialty/class/per-year matrices, Markdown export | `/compare?orgs=medtronic,ge_healthcare` |
| Device intelligence | 23,974 device identities, 630 PMA families, 55,870 confirmed relations, 21,881 candidates; application, versions, timeline, confirmed/candidate recalls | `/devices`, `/devices/P980016` |
| Data lifecycle | Explicit "pipeline not configured" state, UNKNOWN sync, no fabricated changes | `/data-status`, `/api/changes` → `total: 0`, "no change feed exists" |
| Exports | CSV of the filtered set; organization Markdown; comparison Markdown; device Markdown | `/api/export/*` |

The evidence and honesty machinery is real and is the strongest part of the product. PRODUCT-004 must
not weaken it.

## 2. Where the product fails the analyst

### A. The first screen answers a pipeline question, not a research question
The homepage opens with five verification metrics (`Attributed share 99.9%`, `Rule-verified 44.1%`,
`Curated 9.8%`, `Estimated precision 100%`, `Retrieval coverage UNKNOWN`) and a provisional-attribution
alert, then "Start here". The eyebrow still says **"MedRadar - Product 001"**, three releases stale.
An analyst asked to "brief me on Medtronic before Thursday" has no task entry, no window, and no output
object on this screen.

### B. There is no analysis artifact
Every answer is a page state. Nothing captures *what was asked, over which window, under which rule,
with which findings*. The window control exists only on Compare. The organization page is all-time
only (17,473 records), so "recent activity" cannot be expressed without manually using the event
browser.

### C. The organization page is provenance-first
Rendered height at 390 px: 7,310 px. Order: identity → four counts → **attribution confidence (the
record count is repeated, plus four more verification numbers)** → ownership/historical limits →
attribution audit → coverage → data-quality notes → two charts → recent records.
The questions an analyst actually has — what changed, in which technology areas, which devices — sit
below two screens of provenance. The provenance is necessary; its *position* is not.

### D. The technology-area view does not work
The organization page charts "Records by FDA medical specialty". For Medtronic, **11,522 of 17,473
records are `Unknown`**, because the FDA classification dictionary itself carries
`specialty: "Unknown"` for 900 product codes (e.g. `LWS` Implantable Cardioverter Defibrillator,
`NVZ` implantable pulse generator, `LGW` spinal-cord stimulator). The chart therefore says "mostly
unknown" and stops. The product already holds the official classification **device name** for each
product code, which *is* interpretable ("Implantable Cardioverter Defibrillator (Non-CRT)",
"Stimulator, Spinal-Cord, Totally Implanted For Pain Relief") but does not expose it.

### E. Compare is a dead end
Compare is analytically the best screen: shared window, comparability verdict, coverage/provisional/
ownership/pathway warnings, matrices and per-year rows. But:
* a difference cannot be expanded: there is no definition, numerator/denominator, or route to the
  records that produced a cell;
* there is no "what do the two companies have in common / only one side" technology view;
* the output is a Markdown table dump, not a brief with findings and limitations.

### F. No findings layer
91,457 records produce distributions, never statements. The analyst must eyeball tables to notice
that, for example, Medtronic's 2021–2025 window is 77% PMA supplements, or that GE HealthCare's window
is recall-dominant. These are exactly the facts that belong in a first draft — as records, not as
commentary.

### G. Exports are wide but not deliverables
`organization.md` is all-time, and has no study question, window, generation date, metric definitions,
findings, "what cannot be concluded" section, or change/sync context. `compare.md` has the same gap.
Neither can be handed to a manager without editing.

### H. Bilingual coverage is incomplete, and mobile cannot switch language
Chinese covers navigation and tiles, but long explanatory callouts on the organization page remain
English (e.g. the current-group counting callout and the provisional-attribution alert). At 390 px the
language toggle and snapshot chip are hidden, so a Chinese user cannot switch at all.

### I. Navigation mixes research and operations
"Identity review" (internal governance) and "Data status" (operations) sit beside Compare and
Organizations. There is no "Brief" entry because no brief exists. The snapshot chip is genuinely
useful and should stay.

### J. Cold-start cost
First API call after process start: ~10.8 s (snapshot load, 91,457 events). Device index build:
4.1 s on first device request. Steady-state requests are fast (search 3 ms). PRODUCT-004 must not add
per-request heavy computation on the 4 GB host.

## 3. What must be preserved

* The evidence drawer and the four separate time fields.
* Identity/attribution review states and the ownership-at-event-time distinction.
* Compare warnings (coverage, pathway mix, provisional attribution, recall share, unclassified records).
* The device model: confirmed vs candidate, supplements as versions, recalls linked only by official
  K number.
* Data-status honesty ("pipeline not configured" must stay a legitimate state).
* URL-state filters and CSV exports that reproduce the screen.

## 4. Audit verdict

The product is a **good evidence browser** and a **weak analyst workbench**. The gap is not data,
not visual polish and not AI: it is the absence of a research object that carries a question, a scope,
a rule, findings, evidence and limitations from first click to export. PRODUCT-004 addresses that gap
and leaves the evidence layer intact.

---

## 5. Defects found while implementing (fixed in PRODUCT-004)

These were not visible from a page-by-page read; they surfaced while exercising the real browser and
the real aggregation paths. They are recorded here because they changed the product, not only the new
feature.

| Defect | Evidence | Fix |
|---|---|---|
| The homepage chart labelled "records per year across the whole snapshot" plotted the 12-row "latest records" request, so it drew a single bar for 2026 | `/` chart had one column; `latest` is fetched with `page_size: 12` | `/api/meta` now exposes the already-computed `global_aggregations`; the chart uses it (regression check: >20 bars) |
| Adding a ninth primary-navigation item squeezed global search to ~40 px at 1440 px | Screenshot of `/brief` showed only the `/` hint | Shorter nav labels, reduced spacing, protected search width |
| At 390 px the header search and page actions overflowed the viewport (scrollWidth 491 vs 390) | Mobile probe | Search shrinks; page actions wrap; mobile language switch moved into the navigation panel (it was hidden ≤768 px) |
| The device API exposes each supplement twice (application relation and derived version relation), so a naive "confirmed relations" count showed 1,868 instead of 934 | `/api/devices/P980016` relation counts | The brief counts official supplement relations once and shows the supplement, recall and candidate tiles separately |
| The organization page's specialty chart is unusable on its own (Medtronic all-time: 11,522 of 17,473 `Unknown`) | Organization page chart and FDA dictionary | Official product-code family table added to the organization page and the brief |

## 6. Audit limitations

* One operator, one host, one snapshot; the audit is an expert product review, not user research.
* The Chinese review covered the organization and brief workflows; not every inherited page string.
* Firefox/Safari were not exercised; the DOM/CSS review used Chromium.
* Stacked-branch state was verified from the GitHub API (`gh pr list`) and `git merge-base` on
  2026-11-17; it can change while PRs remain open.

---

## 7. The ten audit questions, answered

1. **Who is the core user?** A medical-device competitive-intelligence / strategy analyst who must
   brief others before a decision meeting; secondarily the manager who fact-checks the brief.
2. **Three most important jobs?** (a) know what one competitor has filed and what is notable;
   (b) compare two competitors on one defensible rule; (c) trace a product/device history and hand
   over a sourced brief.
3. **What only displays data?** The current charts, matrices and tables show distributions but never
   state which facts are worth attention, why a difference exists, or what a number cannot support.
   The comparison matrix and the specialty chart are the clearest examples.
4. **How many operations from question to conclusion?** Before this release: open home → search →
   organization page → event tab → rebuild filters → open record → evidence drawer → compare page →
   re-select orgs/window → read warnings → export → edit the export. Around a dozen transitions, with
   the counting rule and caveats reconstructed from memory.
5. **What is buried?** Technology and device facts sit below two screens of provenance; PMA families
   are only in the device explorer; no window control exists on the organization page.
6. **What cannot be explained?** A comparison cell (no definition, numerator, denominator or records),
   a specialty of `Unknown`, and the relationship between "attributed", "rule-verified" and
   "verified" unless the reader finds the transparency page.
7. **What is duplicated?** The record count appears twice on the first organization screen; the
   verification story appears on home, organization, sources and metrics; exports restate the whole
   page.
8. **What feels like a developer tool?** The stale "Product 001" label, pipeline QA as the first home
   block, raw enums in the export (`pma_supplement`), and no research object — only page states.
9. **Smallest changes with the largest value?** A windowed brief with findings; official product-code
   technology names; an explainable comparison; a brief + evidence appendix export; task-first home.
   These are the PRODUCT-004 scope.
10. **What can the data actually support?** Pathway mix and its change over complete years; activity by
    official product code and FDA specialty (with the `Unknown` caveat); PMA family/supplement
    histories; recall counts and official K-number links; attribution/coverage/ownership limits.
    It cannot support innovation, quality, market share, revenue, causality, global activity, or a
    claim that a missing record means no activity.
