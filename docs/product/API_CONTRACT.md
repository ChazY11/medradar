# MedRadar API Contract v1 (PRODUCT-001)

Binding contract between the FastAPI backend (`medradar/product/api/`) and the React
workbench (`web/`). Types below are normative; the frontend copies them into
`web/src/api/types.ts` and the backend must satisfy them exactly.

Base URL: same origin as the UI. All responses JSON unless stated.
Errors: HTTP 400/404/503 with body `{"error": {"code": string, "message": string, "hint"?: string}}`.
Every data response includes `snapshot` and `basis` where declared.

---

## Common objects

```ts
type EventType = "510k" | "pma" | "pma_supplement" | "recall";
type SourceId = "openfda_510k" | "openfda_pma" | "openfda_recall";

interface SnapshotRef {
  id: string;                 // e.g. "2026-11-15T06:10:00Z-openfda"
  collected_at: string;       // ISO datetime, when the collector ran
  openfda_last_updated: string | null;
  file_sha256: Record<string, string>;
  note: string;               // one line, human readable
}

interface Freshness {
  state: "fresh" | "stale" | "unknown";
  age_days: number | null;
  threshold_days: number;
  collected_at: string | null;
}

interface Basis {
  event_types: EventType[];
  window: { from: string | null; to: string | null };
  org_keys: string[];
  snapshot_id: string;
  rule: string;               // human readable sentence naming the counting rule
}

interface Counts {
  records: number;
  dated: number;
  undated: number;
  unmapped_category: number;
  pending_review: number;
  by_source: { source_id: SourceId; count: number }[];
  by_type: { event_type: EventType; count: number }[];
}

interface Category {
  id: string;        // slug of FDA advisory committee description, or "unclassified"
  label: string;     // FDA advisory committee description
}

interface EventRecord {
  event_id: string;
  official_id: string;
  source_id: SourceId;
  source_name: string;
  event_type: EventType;
  event_date: string | null;             // YYYY-MM-DD
  published_at: string | null;
  published_at_status: "from_source" | "not_published_by_source";
  first_observed_at: string;             // ISO datetime
  available_at: string;                  // ISO datetime
  record_updated_at: string | null;
  time_quality: "date_from_source" | "date_derived_from_source" | "unknown";
  organization_key: string | null;
  organization_name: string | null;
  applicant_name: string;
  attribution: {
    status: "attributed" | "unattributed" | "rejected";
    basis: "legal_name" | "brand" | "subsidiary" | "historical_name" | "division" | null;
    review: "curated" | "pending_review" | "rejected" | null;
  };
  product_code: string | null;
  category: Category | null;
  device_class: "1" | "2" | "3" | null;
  device_name: string | null;
  title: string;
  summary: string | null;
  official_url: string;
  fields: Record<string, string | null>;  // verbatim source fields for the evidence view
}

interface Aggregations {
  by_year: { year: string; counts: Record<EventType, number>; total: number }[];
  by_type: { event_type: EventType; count: number }[];
  by_category: { id: string; label: string; counts: Record<EventType, number>; total: number }[];
  by_class: { device_class: "1" | "2" | "3" | "unknown"; count: number }[];
  undated_records: number;
}
```

---

## 1. `GET /api/health`

```ts
{ status: "ok" | "degraded"; snapshot: SnapshotRef | null; version: string; store: string }
```

## 2. `GET /api/meta`

```ts
{
  product: {
    name: "MedRadar"; version: string;
    positioning_en: string; positioning_zh: string;
  };
  snapshot: SnapshotRef;
  freshness: Freshness;
  sources: { source_id: SourceId; name: string; official_base_url: string; licence: string;
             collected: boolean; note: string }[];
  out_of_scope: { item: string; reason: string }[];
  event_types: { event_type: EventType; label: string; note: string }[];
  categories: Category[];
  coverage: { tracked_organizations: number; total_records: number; attributed_records: number;
              unattributed_records: number; earliest_event_date: string | null;
              latest_event_date: string | null };
  time_semantics: { field: string; meaning: string }[];
  limitations: string[];
  methodology_url: string;   // "/sources"
}
```

## 3. `GET /api/search?q=<string>&limit=<int=8>`

Returns organizations plus, separately, raw applicant strings that are not attributed.

```ts
{
  query: string;
  results: {
    key: string; display_name: string; legal_name: string | null; ticker: string | null;
    country: string | null; organization_type: string;
    event_count: number;
    event_range: { from: string | null; to: string | null };
    match: { field: "legal_name" | "brand" | "ticker" | "alias" | "applicant" | "substring";
             value: string; };
    ambiguous_name: boolean;     // true when another org shares a distinctive token
  }[];
  applicant_matches: { applicant_name: string; record_count: number;
                       note: "not attributed to a tracked organization" }[];
  coverage: { tracked_organizations: number; note: string };
  took_ms: number;
}
```

Empty query returns 400. No results is a valid 200 with empty arrays.

## 4. `GET /api/organizations`

```ts
{
  organizations: {
    key: string; display_name: string; legal_name: string | null; ticker: string | null;
    country: string | null; organization_type: string; featured: boolean;
    event_count: number; event_range: { from: string | null; to: string | null };
    attribution_review: "curated" | "pending_review";
  }[];
  total: number;
  note: string;
}
```

## 5. `GET /api/organizations/{key}` -> OrganizationProfile

```ts
interface OrganizationProfile {
  key: string;
  display_name: string;
  display_name_zh: string | null;
  legal_name: string | null;
  ticker: string | null;
  exchange: string | null;
  country: string | null;            // ISO2 of registered seat, registry metadata
  country_name: string | null;
  organization_type: "public_company" | "private_company" | "subsidiary" | "unknown";
  description: string;               // factual 1-3 sentences, registry metadata
  registry: {
    review_status: "curated" | "pending_review";
    metadata_source: string;
    updated_at: string;
    attribution_note: string;
  };
  ownership: {
    parent: { key: string; display_name: string; relation: string;
              status: "declared" | "pending_review" | "unknown" } | null;
    children: { key: string; display_name: string; relation: string;
                status: "declared" | "pending_review" | "unknown" }[];
    note: string;
  };
  attribution: {
    accepted_spellings: number;
    pending_review_spellings: number;
    rejected_spellings: { applicant_name: string; reason: string }[];
    unattributed_in_scope: number;   // records retrieved by this org's tokens but not attributed
    examples: { applicant_name: string; basis: string;
                review: "curated" | "pending_review"; record_count: number }[];
  };
  coverage: {
    window: { from: string | null; to: string | null };   // min/max event_date
    sources: {
      source_id: SourceId; name: string; records: number;
      min_event_date: string | null; max_event_date: string | null;
      first_observed_at: string | null; published_field_available: boolean;
    }[];
  };
  counts: Counts;
  aggregations: Aggregations;
  recent_events: EventRecord[];      // up to 10, sorted event_date desc
  data_quality_notes: string[];
  basis: Basis;
  snapshot: SnapshotRef;
  freshness: Freshness;
}
```

## 6. `GET /api/organizations/{key}/events` and `GET /api/events`

Same query parameters and response shape. `/api/organizations/{key}/events` fixes `org`.

Query parameters:

| param | type | default | notes |
|---|---|---|---|
| `org` | csv of org keys | all | only for `/api/events` |
| `types` | csv of EventType | all | invalid value -> 400 |
| `from`, `to` | YYYY-MM-DD | none | filters on `event_date`; undated always excluded when a bound is set |
| `category` | csv of category ids | all | `unclassified` selects `category = null` |
| `q` | string | none | substring over device_name, applicant_name, official_id, title |
| `review` | `curated|pending_review|any` | any | attribution review filter |
| `sort` | `event_date_desc|event_date_asc|official_id_asc` | event_date_desc | |
| `page` | int >=1 | 1 | |
| `page_size` | int 10..100 | 25 | |

```ts
{
  items: EventRecord[];
  page: number; page_size: number; total: number; total_pages: number;
  applied_filters: Record<string, string>;
  aggregations: Aggregations;   // computed over the FILTERED set (ignoring pagination)
  counts: Counts;
  basis: Basis;
  snapshot: SnapshotRef;
}
```

## 7. `GET /api/events/{event_id}` (URL-encoded)

```ts
{
  event: EventRecord;
  provenance: {
    source_id: SourceId; source_name: string; official_url: string;
    queried_endpoint: string;        // the openFDA URL the collector used
    collected_at: string;            // snapshot collected_at
    official_identifier_label: string;  // "510(k) number" etc.
    raw: Record<string, string | null>; // verbatim record fields kept by the collector
  };
  freshness: Freshness;
}
```
404 when unknown.

## 8. `GET /api/compare?orgs=a,b&from=&to=&types=`

2 to 4 orgs. Default window: last 5 complete calendar years ending 31 Dec of the
latest complete year in the snapshot.

```ts
{
  organizations: {
    key: string; display_name: string; legal_name: string | null; ticker: string | null;
    country: string | null;
    counts: Counts;
    coverage: {
      window: { from: string | null; to: string | null };
      sources: { source_id: SourceId; name: string; records: number;
                 min_event_date: string | null; max_event_date: string | null }[];
      unmapped_category: number;
      pending_review: number;
    };
    aggregations: Aggregations;
    per_year_totals: { year: string; total: number; by_type: Record<EventType, number> }[];
    share_of_all_tracked: Record<EventType, number>;   // 0..1, denominator = all tracked orgs in window
  }[];
  window: {
    requested: { from: string | null; to: string | null };
    effective: { from: string | null; to: string | null };
    complete_years: string[];
    note: string;
  };
  totals_by_type: { event_type: EventType; label: string;
                    values: { org_key: string; count: number }[];
                    note: string }[];
  category_matrix: { id: string; label: string;
                     values: { org_key: string; count: number }[];
                     note: string }[];
  class_matrix: { device_class: string; values: { org_key: string; count: number }[] }[];
  warnings: { code: string; severity: "info" | "warning"; message: string;
              org_keys: string[] }[];
  disclaimer: string;
  basis: Basis;
  snapshot: SnapshotRef;
  freshness: Freshness;
}
```

Warnings must include (when true): `partial_year_excluded`, `coverage_mismatch` (source
start dates or record counts differ materially), `unmapped_category_present`,
`pending_review_present`, `pathway_mix` (PMA vs 510(k) composition differs), `recall_share`
(recalls dominate a side), `low_volume` (< 10 records in window).

## 9. Exports

`GET /api/export/events.csv` — accepts every filter from `6. Response
`text/csv; charset=utf-8`, `Content-Disposition: attachment; filename="medradar-events-<snapshot-date>.csv"`.
BOM prefixed. Two header rows: a comment block is NOT valid CSV, so instead the first row is
the column header and the snapshot provenance is written into a sidecar response header
`X-MedRadar-Provenance` (URL-safe JSON, base64) plus the file name. Columns exactly as in
DATA_CONTRACT `8.

`GET /api/export/compare.md?orgs=&from=&to=&types=` — `text/markdown; charset=utf-8`.
Markdown comparison report with: title, snapshot + collection time, window and counting rule,
warnings as blockquotes, per-org coverage table, totals by type, category matrix, class matrix,
per-year table, per-org attribution review state, and a source list with the official URLs of
every cited aggregate (and up to 5 example record URLs per org). Filename
`medradar-comparison-<orgs>-<snapshot-date>.md`.

`GET /api/export/organization.md?key=` — single-org intelligence brief, same conventions.

## 10. `GET /api/coverage` (data transparency page)

```ts
{
  snapshot: SnapshotRef;
  freshness: Freshness;
  sources: { source_id: SourceId; name: string; endpoints: string[];
             records: number; min_event_date: string | null; max_event_date: string | null;
             official_base_url: string; licence: string; collected_at: string }[];
  organizations: {
    key: string; display_name: string; records: number;
    sources: { source_id: SourceId; records: number; min_event_date: string | null;
               max_event_date: string | null }[];
    pending_review_spellings: number;
  }[];
  collection_audit: {
    tokens: { token: string; org_key: string; endpoint: SourceId;
              records_retrieved: number; pages: number; urls: string[] }[];
    unattributed: { applicant_name: string; records: number; endpoints: SourceId[] }[];
    rejected: { applicant_name: string; org_key: string; reason: string }[];
  };
  out_of_scope: { item: string; reason: string }[];
  time_semantics: { field: string; meaning: string }[];
}
```

## 11. `GET /api/attribution`

```ts
{
  decisions: { organization_key: string; organization_display: string;
               applicant_name: string; basis: string;
               review: "curated" | "pending_review";
               confidence: "high" | "medium" | "low";
               record_count: number;
               evidence: string }[];
  rejected: { applicant_name: string; organization_key: string; reason: string }[];
  unmatched: { applicant_name: string; records: number; endpoints: SourceId[];
               seen_with_tokens: string[] }[];
  policy: string[];
  snapshot: SnapshotRef;
}
```

## 12. Static UI

`GET /` and any non-`/api` path serve `web/dist/index.html` (SPA fallback). Assets under
`/assets/*`. `GET /favicon.svg`. If the build is missing, return a 503 JSON error with the
build command in `hint`.

## PRODUCT-002 additions (v2)

The following are additive. No PRODUCT-001 field was removed; two changed meaning and are marked.

### `GET /api/metrics`

Returns the five measurements with their definitions, per level (record / applicant / organization):
`attributed_share`, `rule_verified_share`, `curated_share`, `estimated_attribution_precision`,
`retrieval_coverage`. `definitions` is the same text the documentation uses, so the API cannot drift
from the docs. Precision and retrieval return `state: "unknown"` with a reason when unsupported.

### `GET /api/ownership`

Ownership relations with `relation_id`, `entity`, `relation_type`, `effective_from`,
`historical_owner_before`, `status` (`evidence_verified` | `unresolved`), `reviewer_kind` and the
recorded `evidence` (type, URL, title, access date, quote). Unresolved relations carry no evidence.

### Event attribution object (additive fields)

```json
{
  "status": "attributed",
  "basis": "legal_name | brand | subsidiary | historical_name | division | review_decision",
  "review": "curated | pending_review | rejected",
  "verification": "proposed | rule_verified | evidence_verified | human_reviewed | rejected | unresolved | unattributed",
  "verified": false,
  "rule": "name_identity_v1 | lexical_equivalence_v1 | ownership_evidence_v1 | token_scope_proposal_v1 | registry_authoring_v1 | review_ledger_v1",
  "evidence_count": 0,
  "reviewer": null,
  "reviewer_kind": "human | agent | null",
  "provenance": "registry_authoring | machine_proposal | name_identity_rule | lexical_equivalence_rule | ownership_evidence | review_ledger",
  "predecessor_entity": false
}
```

`review` remains for compatibility but is no longer the product's claim; `verification` is.
`counts.pending_review` now means "not evidence-verified and not human-reviewed" and is broken down by
`counts.provisional`, `counts.rule_verified_records`, `counts.verified_records` and
`counts.by_verification`.

### Query parameters

* `review` on `/api/events`, `/api/organizations/{key}/events`, `/api/compare`, CSV and Markdown
  exports: `curated` (alias `verified`), `rule_verified`, `provisional` (alias `pending_review`),
  `unverified`, `any`. Unknown values return 400.
* `basis` on the same routes: `current_group` (default) or `historical_owner_verified` (owner at event
  time, from a verified relation with an effective date). Unknown values return 400; the retired
  `original_registrant` returns `400 retired_basis` with a hint. The effective basis is echoed in the
  payload and in every export header, and the historical basis reports excluded records in
  `basis_excluded_totals`.

### Comparison additions

`comparability` (window/event-type sharing, counting unit, ownership basis, review filter, coverage
symmetry, verdict), `not_evidence_of` (explicit list), per-side `verification` and
`historical_ownership` blocks, and warnings `provisional_attribution_present`,
`verification_asymmetry`, `historical_ownership_included` (replacing `pending_review_present`).

### Device Intelligence API (PRODUCT-003, additive)

| Route | Purpose |
|---|---|
| `GET /api/devices` | device explorer: `q` (name/trade name/applicant/official number), `org`, `pathway` (510k/pma), `product_code`, `category`, `relation` (confirmed/candidate/none/any), `sort` (relevance/date_desc/name_asc), `page`, `page_size` |
| `GET /api/devices/quality` | relationship quality report: relation counts by type/status, evidence completeness, coverage, conflicts, and four separate verification levels (rule consistency, documentary evidence, human review = 0, accuracy = UNKNOWN) |
| `GET /api/devices/unlinked` | recall records with no application link in the snapshot, each with a reason |
| `GET /api/devices/{device_id}` | device detail: identity basis and disclosures, applicant attribution block, application/versions, family, timeline (event date vs first-observed), confirmed and candidate relations with evidence, related recalls (official K-number reference only) |
| `GET /api/device-families/{family_id}` | PMA family: basis, versions ordered by decision date, missing-original disclosure, related recalls, timeline |
| `GET /api/export/devices.csv` | CSV of every device matching the explorer filters, with provenance header and `X-MedRadar-Records` |
| `GET /api/export/device.md` | Markdown device brief (identity, timeline, relations with evidence) |

Identifiers: MedRadar ids are prefixed (`app:`, `device:`, `family:`) and never impersonate an FDA
identifier; the official identifier is always a separate field. A device id can be looked up by its
MedRadar id or by its official K/PMA number. Unknown ids return `404 device_not_found` /
`family_not_found` with a hint. Relation status is one of `confirmed`, `evidence_supported`,
`candidate`, `unlinked`; a candidate is never presented as established.

### Data lifecycle API (DATA-001, additive)

| Route | Purpose |
|---|---|
| `GET /api/data-status` | active snapshot, per-source check/sync state, last successful sync, change counts, latency semantics and recent incidents. If the pipeline database is absent, returns `configured=false` and `state=not_configured`. |
| `GET /api/changes?source=&type=&org=&limit=&offset=` | published change ledger only. `type` is one of `ADDED`, `UPDATED`, `REMOVED_CONFIRMED`, `UNCHANGED`, `MISSING_ON_RECHECK`, `UNRESOLVED`; `limit` 1–200. |

```ts
interface DataStatusResponse {
  configured: boolean;
  state: "not_configured" | "ok" | "unverified" | "update_available" | "degraded" | "configured_no_publication";
  snapshot: SnapshotRef | null;
  synchronization: {
    state: string;
    last_successful_sync: string | null;
    last_check_attempt: string | null;
    active_snapshot_id: string | null;
    change_feed_available: boolean;
  };
  sources: {
    source_id: SourceId | "openfda_classification";
    status: "NO_CHANGE" | "UPDATE_AVAILABLE" | "CHECK_FAILED" | "SOURCE_DEGRADED" | "UNKNOWN";
    official_last_updated: string | null;
    last_checked_at: string | null;
    last_success_sync_at: string | null;
    added_since_previous: number | null;
    updated_since_previous: number | null;
    consecutive_failures: number;
    declared_frequency: string;
  }[];
  change_counts: Record<string, number>;
  latency: { official_source_version: string | null; last_checked_by_medradar: string | null;
             last_successful_sync: string | null; sync_lag_hours: number | null; statement: string };
  terminology: { continuously_monitored: boolean; automatically_synchronized: boolean;
                 real_time_claim: false; labels: string[] };
  dataset_error?: string | null; // present when the active snapshot cannot load
}
```

`SnapshotRef` gained optional `previous_snapshot_id`, `content_hash` and
`source_versions`. `EventRecord` gained optional `record_state` and `missing_count`.
No existing response shape was removed. The change feed is not a claim that a new regulatory
event occurred; it reports source-record changes detected by MedRadar.

### Internal review API (not part of the public contract)

`/api/review/*` exists only on the loopback admin application
(`python -m medradar.product.review serve`):

| Route | Purpose |
|---|---|
| `GET /api/review/ping` | auth check and ledger identity |
| `GET /api/review/queue` | queue: status, org, risk, q, sort, page, page_size, include_verified |
| `GET /api/review/summary` | queue + ledger statistics + metrics |
| `GET /api/review/case/{applicant}` | verbatim string, current mapping, risk flags, candidates, FDA records, ownership relations, history |
| `GET /api/review/history/{applicant}` | append-only decision history |
| `GET /api/review/impact` | which organizations changed, and how many did not |
| `GET /api/review/capabilities` | what the service can attest: `human_review_authority_available: false`, writable statuses, actor-kind policy |
| `POST /api/review/decisions` | append a decision (approve/reassign/reject/unresolved); `reviewer_kind` in the body is rejected 400, `human_reviewed` is refused 403 |
| `POST /api/review/decisions/{uid}/revoke` | withdraw a decision (append-only) |
| `GET /api/review/export`, `POST /api/review/import` | offline review file |

Every route requires `X-MedRadar-Review-Token` and a loopback client; the public application has no
`/api/review` route at all (404).
