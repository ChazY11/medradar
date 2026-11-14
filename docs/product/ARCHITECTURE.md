# Product Architecture (as built)

This document describes the architecture that is actually implemented on branch
`feat/product-001-core-workbench`, not an aspirational design.

---

## 1. Shape of the system

```
                    committed snapshot (medradar/product/snapshot/, 91,457 records, sha256 in manifest)
                                        |
                    medradar/product/dataset.py   (load once, attribute, aggregate)
                          |            |            |
              identity.py         compare.py     export.py
           (registry, exact      (windows,      (CSV / Markdown
            attribution)          warnings)      reproducing the screen)
                          \            |            /
                         medradar/product/api.py  (FastAPI: JSON + static UI)
                                        |
                     FastAPI serves web/dist (React 19 + Vite build)
                                        |
                              analyst's browser
```

One process, no database server, no background workers, no external services at request time.
The only mutable thing is the collected snapshot on disk, and the API never writes it.

## 2. Why this stack

The repository before PRODUCT-001 was a Python CLI plus a generated static HTML dashboard. It had
no API, no interactive product and no committed data (runtime data was git-ignored and regenerated
by the research pipeline). Three options were considered:

| Option | Why not chosen |
|---|---|
| Reuse the research SQLite pipeline directly (the PR #12 approach) | It requires running the research collectors to build `data/medradar.sqlite`, ties the product to a mutable research artefact, and models only five featured firms. The product needed a versioned, hash-addressed dataset and a company search across a tracked registry. |
| Static site with pre-rendered pages | Cannot support filtering, comparison, URL state or export; would freeze the product into a set of screenshots. |
| Node/TypeScript backend (single language with the UI) | The data contract, attribution rules and export logic are the hard part; the repository already has the Python testing and CI conventions. A second runtime would double the maintenance surface for one developer. |
| **Chosen: FastAPI + React/Vite + committed snapshot** | Installed Python deps are small (fastapi, uvicorn); the UI is a static build served by the same process (no CORS, no second deployment); the snapshot is diffable and hash-addressed; the data layer is testable without HTTP. |

The frontend is React 19 + TypeScript + Vite with hand-written CSS: no UI kit, no chart library,
no CSS framework. Bundle: 368 KB JS (112 KB gzip) + 18 KB CSS (4.4 KB gzip). That is small enough
for a one-maintainer product and gives full control of the analytical layout.

## 3. Repository layout (product-owned code)

```
medradar/product/
  __init__.py           product identity constants
  dataset.py            snapshot loading, attribution application, aggregation, coverage
  identity.py           organization registry, exact-string attribution, organization search
  identity/organizations.json   59 organizations, 1,590 accepted spellings, 9 rejections
  compare.py            2-4 organization comparison, warnings, shares, matrices
  export.py             CSV and Markdown exports
  api.py                FastAPI routes, static serving, error envelope
  web.py                uvicorn entry point (python -m medradar web)
web/                    React workbench (source + committed dist/)
scripts/
  product_collect.py    openFDA collection, sharding, compaction, manifest
  product_curate_aliases.py  observed-spelling proposals (append-only, review=pending)
  gen_org_registry.py   base registry from the research roster + enriched identities
  product_acceptance.mjs     Playwright end-to-end acceptance walkthrough
medradar/product/snapshot/           committed snapshot (events/applicants/classifications + manifest)
docs/product/           this document set
tests/product/          pytest suite for the product layer
```

The research modules (`medradar/*.py`, `experiments/`, `research/`, `papers/`) are untouched.

## 4. Data pipeline

### 4.1 Collection (`scripts/product_collect.py`)

* Queries the public openFDA device endpoints (510(k), PMA, recall, classification) with a
  documented User-Agent; no key, no paid service.
* One query per organization per endpoint, using that organization's curated search tokens OR-joined
  inside `applicant:(...)` (recalls use `recalling_firm`). Pagination is 1000 records per request,
  with retry/backoff on 429/5xx and explicit 404 handling ("no matches" is an empty result).
* Every request URL is written into the manifest, so a reviewer can replay the collection.
* Six shards were collected in parallel (the full sweep is ~258 requests and ~1.3 GB of responses),
  then merged deterministically by event id. The merge, not the shard order, defines the snapshot.

### 4.2 Record normalisation and compaction

Records keep the source identifiers, dates, applicant strings, product codes and the verbatim
fields needed for evidence. The large `openfda` cross-reference blocks are dropped (they are not
needed to identify a device record and would dominate the repository size). Long free-text fields
are truncated with an ellipsis; no value is invented. Output is deterministic: sorted keys, gzip
mtime 0, SHA-256 per file in the manifest.

Implausible dates (16 records) are **quarantined**, not silently kept: `event_date` is set to null,
`time_quality` to `unknown`, and the original value is preserved as
`raw.event_date_as_published`. The count is reported in the manifest and on the sources page.

### 4.3 Attribution (`medradar/product/identity.py`)

* Registry: 59 organizations. Applicant spellings are accepted only by exact match after Unicode
  NFC, case-folding and whitespace collapse; the verbatim string is always preserved.
* 180 spellings are curated (research roster + a reviewed alias set ported from the PRODUCT/2.0
  branch). 1,410 were auto-proposed from observed openFDA spellings by
  `scripts/product_curate_aliases.py` under one narrow rule: the string was retrieved inside that
  organization's own query scope, contains one of its distinctive tokens as a whole-word sequence,
  and contains none of its documented exclusion tokens. These are `review=pending_review` and are
  labelled provisional in the UI.
* 9 spellings are explicitly rejected with a written reason (e.g. "Drager Safety", "Fresenius Kabi",
  "Siemens Energy"). Two ambiguous strings (an Abbott/Guidant joint-venture name and an
  Olympus-Terumo joint venture) are deliberately left unattributed.
* Load-time integrity: a spelling cannot be accepted by two organizations, cannot be both accepted
  and rejected, and duplicate case-variants are removed with a diagnostic. These are tested.

### 4.4 Snapshot contract

`medradar/product/snapshot/snapshot.json` carries: schema version, snapshot id, collection timestamps, collector
version and User-Agent, openFDA last-updated, request count, response bytes, errors, per-file SHA-256
and record counts, per-organization query audit, data-quality counters and notes. The API exposes it
verbatim on `/api/coverage`; the UI renders it on the sources page.

## 5. Measurement layer (`dataset.py`)

Loaded once per process (~3 s for 91k records) and immutable afterwards:

* attribute each record by exact applicant spelling -> organization / unattributed / rejected;
* attach the category from the FDA classification dictionary via product code (device class too);
* derive `first_observed_at` (= snapshot collected_at) and `available_at`
  (= published_at ?? first_observed_at);
* precompute per-organization counts, aggregations, coverage per source, recent events and
  attribution evidence, plus global aggregates.

Queries (`/api/events`, `/api/organizations/{key}/events`) filter the in-memory list, sort, paginate
and aggregate over the filtered set. At this data size this is fast (single-digit milliseconds) and
removes the need for a query cache or a database.

## 6. API surface

| Route | Purpose |
|---|---|
| `GET /api/health` | status, snapshot ref, version |
| `GET /api/meta` | product, snapshot, freshness, sources, event types, categories, coverage, time semantics, limits |
| `GET /api/search?q=` | organization search (exact legal/brand/ticker/alias, prefix, substring, applicant substring for >=4 chars) + unattributed applicant matches |
| `GET /api/organizations` | tracked organizations with counts and ranges |
| `GET /api/organizations/{key}` | organization profile (identity, attribution composition, coverage, counts, aggregations, recent events, quality notes) |
| `GET /api/organizations/{key}/events`, `GET /api/events` | filtered/paginated event records + aggregations over the filtered set |
| `GET /api/events/{event id or official id}` | record + provenance + verbatim source fields |
| `GET /api/compare?orgs=` | 2-4 organizations, one window, warnings, matrices, shares |
| `GET /api/export/events.csv` | exactly the filtered records, UTF-8 BOM, provenance header |
| `GET /api/export/compare.md`, `/api/export/organization.md` | sourced Markdown reports |
| `GET /api/coverage` | snapshot manifest, sources, collection audit, attribution summary, limits, reproduction commands |
| `GET /api/attribution` | every attribution decision, rejection and unmatched string |
| `GET /*` | static React build with SPA fallback |

Errors use one envelope: `{"error": {"code", "message", "hint"?}}` with 400/404/503/500 semantics.
A missing snapshot returns `503 dataset_unavailable` with the collection command as a hint - never an
empty dataset that looks like zero activity.

## 7. Frontend

* Six routes: `/` overview, `/organizations`, `/organizations/:key` (tabs: overview, events,
  attribution), `/events` and `/events/:eventId` (evidence drawer deep link), `/compare`, `/sources`.
* A typed API client generated by hand from `docs/product/API_CONTRACT.md` (`web/src/api/types.ts`);
  no `any` in product code paths.
* Components: page header, metric tiles, data tables, filter bar with URL state, SVG year-series and
  distribution charts, evidence drawer, warnings/banners, loading/error/empty states.
* Filters and comparison selection live in the URL, so every view is shareable and back/forward
  works. `/` focuses search; Escape closes overlays; table rows are keyboard reachable.
* Responsive: navigation collapses under 900px, tables become labelled stacked rows under 768px.
  Verified at 1440x900 and 390x844 (see screenshots in `docs/product/screenshots/`).
* Bilingual chrome (English/Chinese) via a small dictionary; long methodology prose is English-only
  (documented limitation).

## 8. Deployment and maintenance

* `pip install -e '.[product]'` then `python -m medradar web --port 8787`. The committed
  `web/dist` is served directly, so Node is only needed to change the UI (`cd web && npm run build`).
* No hosting is claimed or required. If hosted later, it is a single stateless process plus the
  snapshot; no managed database, no queue, no paid API.
* Refresh path: `python scripts/product_collect.py` (optionally sharded) -> `--merge` -> re-run
  `product_curate_aliases.py --apply` for new spellings -> commit the new snapshot. The manifest
  changes and is diffable.
* Cost: one developer, one machine. The only external dependency at build time is openFDA's free
  public API (rate-limited without a key, hence the aggressive one-shot collection and committed
  snapshot).

## 9. Failure modes (designed behaviour)

| Failure | Behaviour |
|---|---|
| Snapshot missing/corrupt | `503 dataset_unavailable` with the collection command; UI shows an error state, not zeros |
| Snapshot stale (>30 days) | Freshness banner on the overview and sources page; API returns `freshness.state = stale` |
| openFDA down / rate-limited during collection | Retry/backoff; failing queries are recorded in the manifest and the run continues (0 errors in the shipped snapshot) |
| Unattributed applicant string | Never counted as company activity; listed in the audit with record count and endpoints |
| Ambiguous official identifier in a deep link | 404 with an explicit message instead of guessing a record |
| UI build missing | `503 ui_not_built` with the build command |

## 10. Testing strategy

* `tests/product/test_identity.py` - registry integrity, exact-match rules, no fuzzy matching,
  search precedence, short-query behaviour, provisional labelling.
* `tests/product/test_dataset.py` - attribution accounting, event-type separation, undated handling,
  publication-time rule, category mapping, coverage ranges, identifier resolution, metadata limits.
* `tests/product/test_api.py` - HTTP contract, error codes, pagination bounds, CSV row count equals
  the filtered API total, Markdown exports, static serving.
* `scripts/product_acceptance.mjs` - real-browser walkthrough with 15 checks and screenshots;
  results recorded in `docs/product/ACCEPTANCE.md` and `acceptance-report.json`.

The research test suite is unaffected and still runs (`python -m medradar selftest` / pytest).
