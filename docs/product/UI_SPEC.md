# MedRadar Workbench - UI Specification v1

Target: a professional medical-technology intelligence workbench. The user is a competitive
intelligence analyst. The UI must feel like commercial analyst software (dense, calm, precise),
not a university project, dashboard demo, or marketing page.

Stack (fixed): React 19 + TypeScript + Vite + react-router-dom. No UI kit, no chart library -
custom components and hand-written CSS (CSS variables + plain classes, one stylesheet per area).
Served as a static build from `web/dist` by the FastAPI server. Dev mode uses Vite proxy to
`http://127.0.0.1:8787`.

**Hard rule: the UI renders only what the API returns. No mock rows, no placeholder metrics,
no invented numbers, no Lorem ipsum. Every absence is an explicit empty/unknown state.**
The API contract is `docs/product/API_CONTRACT.md`; the data semantics are
`docs/product/DATA_CONTRACT.md`. Read both before coding.

---

## 1. Information architecture

```
/                         Overview - what the product is, live coverage, featured orgs, recent records
/organizations            Browse tracked organizations (searchable, sortable)
/organizations/:key       Organization profile
   ?tab=overview          identity + coverage + distributions + recent
   ?tab=events            paged event table (filters) + CSV export
   ?tab=attribution       which applicant spellings were attributed, how, review state
/events                   Global regulatory event browser + filters + CSV export
/compare?orgs=a,b         Side-by-side comparison + warnings + markdown report export
/sources                  Sources, snapshot provenance, collection audit, time semantics, limits
```

Global search lives in the top bar on every page: fuzzy prefix input, debounced 180ms,
keyboard navigable (↑/↓/Enter/Esc), "/" focuses it. Results group into Organizations (primary)
and "Applicant names not attributed to a tracked organization" (secondary, shown as a caveat,
never clickable as a company).

## 2. Design tokens

```css
--bg:#f6f7f9; --surface:#ffffff; --surface-2:#fbfcfd; --border:#e4e7ec; --border-strong:#cfd5de;
--text:#0d1526; --text-2:#465063; --text-3:#6b7689; --text-inv:#ffffff;
--accent:#1f4bd8; --accent-hover:#1740be; --accent-soft:#edf2ff;
--ok:#0f7b52; --ok-soft:#e8f6ef; --warn:#a8610a; --warn-soft:#fdf3e3; --danger:#b42318; --danger-soft:#fdeceb;
--510k:#1f4bd8; --pma:#7a2fd1; --pma_supplement:#b28ae0; --recall:#c0362c;
--radius:6px; --radius-lg:10px; --shadow-1:0 1px 2px rgba(13,21,38,.05);
--font: -apple-system, "Segoe UI", "Helvetica Neue", Arial, "PingFang SC", "Microsoft YaHei", sans-serif;
--mono: "SFMono-Regular", "Cascadia Mono", Consolas, monospace;
```

- Base font size 14px, table 13px, metadata 12px, labels 11px uppercase with letter-spacing .04em.
- Numbers: `font-variant-numeric: tabular-nums`.
- Light theme only. No gradients, no glassmorphism, no animation longer than 120ms, no shadows
  beyond `--shadow-1`, no emoji in product chrome.
- Accent colour only for interactive/selected state, never for decoration.
- Never use colour alone to encode a distinction: pair with a text label or a shape.

## 3. Layout

- App bar height 56px, sticky, surface with bottom border: left = wordmark "MedRadar" +
  subtitle "Medical Technology Intelligence"; centre = nav links (overview, organizations,
  events, compare, sources); right = global search (280px, grows to 420px on focus) +
  snapshot chip ("snapshot: 2026-11-15" with freshness dot and tooltip).
- Content max-width 1500px, padding 24px (16px on mobile).
- Page header pattern: 11px uppercase eyebrow (e.g. "ORGANIZATION"), 24px title, one-line
  description in --text-2, right side actions (export buttons).
- Section pattern: title 13px semibold + optional right-side note; card with 1px border,
  0 radius on table edges.
- Density: card padding 16px, row height 34px, first column left-aligned, numeric columns
  right-aligned.

## 4. Components (build these, reuse them everywhere)

1. `AppBar`, `GlobalSearch`, `SnapshotChip`
2. `PageHeader` (eyebrow, title, description, actions, breadcrumb)
3. `MetricTile` (label, value, sub-note, optional delta; value may be "-" with an explicit
   "not available" tooltip - never 0 for missing data)
4. `DataTable` (column defs, sortable, sticky header, row click, pagination, dense mode,
   accessible caption, empty state slot). Numeric right align. Row hover.
5. `FilterBar` (multi-select chips, select, date range from/to, text input, "reset", active
   filter summary line: "42 records - filtered by 510(k), 2019-2025").
6. `EventTypeBadge` (coloured dot + label), `SourceBadge`, `TimeQualityBadge`,
   `ReviewBadge` ("attribution pending review" = warn style), `FreshnessBadge`.
7. `BarBreakdown` (horizontal stacked bars with labels + counts, used for category/class),
   `YearSeries` (inline SVG line/area per year, 4 series max, legend, tooltip on hover,
   y-axis labelled "records"), `Sparkline` (tiny, no axes).
8. `EvidenceDrawer` (right-side drawer, 520px, opens from a record row or link): shows
   event identity, official id + official URL (external, rel="noopener"), the four times with
   plain-language labels, attribution (applicant string verbatim, basis, review state),
   category/class, "verbatim source fields" table, collector provenance (endpoint, snapshot,
   collected_at). Must be deep-linkable: `/events/:eventId` opens the drawer over the list.
9. `Banner` (info/warn/danger with optional dismiss), `Callout` (methodology note)
10. `EmptyState` (title, explanation, action), `ErrorState` (message, retry, request id),
    `LoadingSkeleton` (shimmer-free, neutral blocks).
11. `Tooltip`, `DefinitionLabel` (dotted underline term + explanation, for "records",
    "event date", "first observed", "attribution").
12. `ExportButton` (calls export endpoints, shows file name, handles error).
13. `Pagination`, `Tabs`, `Breadcrumb`, `Card`, `Stat`, `KeyValueList`.

## 5. Page requirements

### Overview
- One-sentence product statement, not marketing: what data is covered, what it can answer.
- Snapshot/freshness banner when stale.
- Coverage strip: tracked organizations, total records, date range, sources (4 tiles).
- "Start here" 3 actions: search an organization, browse events, compare two organizations.
- Featured organizations (from `/api/organizations`, featured first) as a compact table with
  record counts and date ranges.
- Latest observed records table (10 rows) with event type, org, date, official id, evidence link.
- Methodology callout linking to /sources with the four time concepts in one line each.

### Organization profile
- Header: display name + legal name (if different, shown as "legal name: ..."), ticker,
  country, registry review badge, actions: "Add to comparison", "Export CSV", "Export brief".
- Identity/caveat block: how attribution works for this org (accepted spellings count,
  pending-review count, rejected strings, unattributed in scope) + ownership note when unknown.
- Coverage card: per source rows (records, min..max event date, first observed, whether the
  source publishes a publication date).
- Metrics row: total records, 510(k), PMA (+supplements separately), recalls; each with a note.
- Charts: records per year by type (YearSeries), specialty distribution (BarBreakdown),
  device class distribution.
- Recent records table -> EvidenceDrawer.
- If zero records: full-width EmptyState explaining what would produce data and the coverage
  boundary; no fake zeros everywhere.
- Tabs for events and attribution.

### Events browser
- FilterBar: organization (select, searchable), event type multi-select, date range, category,
  review state, text search. URL state (shareable) - filters serialise into query string.
- Result summary line + total, export CSV button.
- Table columns: event date, type, organization, official id (mono), device/applicant,
  category, class, source, review, evidence (link icon). Sortable.
- Aggregation strip above table: records per year mini chart + by-type counts for the
  filtered set.
- Row click -> `/events/:eventId` drawer with URL sync.

### Compare
- Org picker (2-4) with add/remove chips; window selector (3y/5y/10y/custom), type selector.
- Warnings block **above** all data, one banner per warning, each with severity.
- Side-by-side header cards (identity + coverage + review state).
- Matrix tables: totals by type, specialty, device class, per-year totals; each cell formatted
  number + share, with a footnote naming the denominator.
- Per-org coverage table showing differing source coverage; highlight material differences.
- Disclaimer block (records != innovation) always visible above the matrices.
- Export markdown report button.

### Sources & coverage
- Snapshot manifest summary (id, collected_at, files + sha256 truncated, openFDA last_updated).
- Source table: endpoint, records, coverage range, licence, official base URL.
- Collection audit table: tokens queried, records retrieved, unattributed applicant strings,
  rejected strings with reasons.
- Time semantics explanation (4 cards) and the list of limitations / out-of-scope sources.
- This page is the trust anchor: it must be accurate and complete.

## 6. Interaction and states

- Every fetch: loading skeleton sized like the final content, error state with retry, empty state.
- Never flash "0" while loading; never render a chart without data - show empty state instead.
- All filters are shareable via URL; back/forward must work.
- Keyboard: "/" focus search, Esc closes overlays, table rows focusable + Enter opens evidence.
- Mobile (<768px): nav becomes a menu, tables become stacked definition lists, charts full width,
  compare becomes sequential blocks. No horizontal page scroll.
- Performance: paginate server-side, memoise selectors, avoid layout shift, keep bundle < 300KB gz.

## 7. Copy rules

- English primary UI labels for data concepts, with the product also usable in Chinese:
  implement a minimal i18n dictionary (en/zh) with a toggle persisted in localStorage,
  default en. All fixed UI strings go through `t()`; do not hardcode English in components.
- Never say "real-time", "live", "AI-powered", "breakthrough", "innovative",
  "market leader", "predicts". Say "snapshot", "records", "observed", "attributed".
- Every number carries its unit and its basis on hover or adjacent note: "42 records",
  "3 sources", "5 complete years".
- Warnings are informative, not alarming: state the fact, the consequence, and what to do.

## 8. Definition of done

- `npm run build` succeeds with no TypeScript errors and no `any` leaks in new code paths.
- All 6 routes render against the real API with empty, loading and error states implemented.
- Lighthouse-ish sanity: no console errors, no failed requests, keyboard navigable.
- Screenshots at 1440x900 and 390x844 of every route are captured for the acceptance record.
