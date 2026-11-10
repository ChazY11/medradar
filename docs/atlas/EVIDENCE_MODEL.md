# EVIDENCE_MODEL — records, clocks, versions and quality

**Schema id:** `medradar.atlas.evidence.v1` (`medradar/atlas/evidence/schema.py`)
**Storage:** `evidence` + `evidence_head` + child tables in `research/atlas/staging/atlas.sqlite`

---

## 1. The record

Every fact ATLAS stores is one row per source record, with this contract:

| Field | Required | Meaning |
|---|---|---|
| `archive_id` | — | not used; `evidence_id` is the identity |
| `evidence_id` | ✓ | deterministic id from source + record id + type |
| `schema`, `schema_version` | ✓ | `medradar.atlas.evidence.v1`, `1.0.0` |
| `source_id` | ✓ | source register key |
| `source_record_id` | ✓ | the source's own record identity |
| `evidence_type` | ✓ | closed vocabulary (registration, clearance, publication, …) |
| `source_url` | ✓ | the exact retrievable URL |
| `canonical_entity_id` | — | entity this record is about, when resolved |
| `source_content_hash` | ✓ | SHA-256 of the source record bytes |
| `normalized_content_hash` | ✓ | SHA-256 of the deterministic normalized JSON |
| `collection_run_id` | — | run that produced this version |
| `time` | ✓ | four clocks + publication quality |
| `identifiers[]` | — | scheme-scoped official ids |
| `entity_refs[]` | — | company links with method + confidence |
| `identity_resolution_status` | ✓ | confirmed / candidate / none / not_attempted / ambiguous |
| `relation_status` | ✓ | asserted_by_source / candidate / none / contradicted / unknown |
| `licence_status` | ✓ | public_domain / open_licence / open_no_explicit_licence / restricted / unknown |
| `quality_flags[]` | — | closed vocabulary |
| `provenance` | ✓ | source name, attribution, evidence reference, raw byte count |
| `canonical_key` | derived | cross-source dedupe key from authoritative ids only |

`validate_evidence` recomputes `normalized_content_hash` from the payload. A record whose hash
does not cover its own content fails validation — editing `normalized` cannot masquerade as an
unchanged re-fetch.

---

## 2. Four clocks

```
event_at          ── when it happened             (decision date, licence issue date, …)
source_public_at  ── when it became public        (per-record publication date if published)
first_observed_at ── when MedRadar first saw it   (fetch clock of the first capture)
fetched_at        ── when this copy was retrieved
```

Rules:

1. A missing clock is `""`, never a convenient substitute.
2. `first_observed_at` defaults to `fetched_at` (a first backfill observes when it fetches).
   It is never defaulted to `source_public_at`.
3. `source_public_at_quality ∈ {exact, day, coarse, derived, unknown}`. `derived` means ATLAS
   inferred it (e.g. MDALL publishes no publication date, so the licence date is used and
   flagged). Derived/coarse dates cannot support a lead-time claim.
4. `observation_basis` records that the observation clock is a fetch clock.

Per-source decisions:

| Source | `source_public_at` | Quality | Why |
|---|---|---|---|
| openFDA UDI / AccessGUDID | `publish_date` / `devicePublishDate` | `day` | genuine per-record first publication; `public_version_date` is a version stamp and is not used |
| openFDA 510(k) | `decision_date` | `derived` | FDA publishes no per-record publication timestamp |
| Health Canada MDALL | `first_licence_dt` / `first_licence_status_dt` | `derived` | no publication date; `last_refresh_dt` is a database stamp and `end_date` is cancellation |

---

## 3. Immutability

`evidence` is keyed by `(evidence_id, version)` and is append-only:

- same `evidence_id` + same `content_hash` → no-op (idempotent re-fetch);
- same `evidence_id` + different hash → new version, head pointer moves;
- previous versions keep their payload and their `fetched_at`;
- `evidence_head.first_observed_at` keeps the **earliest** observation across versions.

`relation` history is analogous: `entity_relations` rows are never deleted; revocation sets
`revoked_at`/`revoked_reason` and appends a `relation_events` row.

---

## 4. Cross-source deduplication

`canonical_key` is built only from authoritative identifiers, in priority order:
`di > basic_udi_di > licence_no > 510k > pma > denovo > nct > doi > pmid > patent_no > ocid`.

Consequences:

- Two interfaces over the **same upstream authority** (openFDA UDI and AccessGUDID both read
  GUDID) produce the same canonical key: they are duplicates, not corroboration.
- The same DI in GUDID and MDALL produces the same canonical key: they are the *same device*
  observed in two registries — useful for identity, not independent evidence.
- A record with no authoritative identifier gets `canonical_key = NULL` and can never be
  deduplicated across sources. The quality report counts those rows.

`is_independent(a, b)` returns false when the canonical keys match, so a research count cannot
silently double-count one device.

---

## 5. Version semantics by scenario

| Scenario | Representation |
|---|---|
| first observation | version 1, `first_observed_at` set |
| content update | version n+1, new hashes, new `fetched_at` |
| source correction | same as update; old version retained |
| identity correction | a new/revoked relation + `relation_events`, evidence unchanged |
| source unavailable | `collection_runs.status != ok` + quality finding |
| source retired | `source_status` row + quality finding |
| identifier changed | new identifier rows with validity dates; old ids retained |

---

## 6. Quality checks (implemented)

| Check | Severity | Catches |
|---|---|---|
| `duplicate_same_source` | warning | one source emitting the same canonical key twice |
| `duplicate_cross_source_expected` | info | legitimate dedupe across registries (counted once) |
| `missing_primary_identifier` | warning | record with no authoritative id, aggregated per source |
| `missing_company_link` | info | no target-firm link (expected outside the five-firm sample) |
| `time_public_after_fetch` | error | publication date after fetch date |
| `time_observed_after_fetch` | error | observation after fetch |
| `possible_clock_copy` | warning | event clock copied into the observation clock |
| `identity_contradiction` | error | same identifier, conflicting descriptive fields |
| `company_name_conflict` | error | one name mapping to two companies |
| `collection_run_not_ok` | error | failed/aborted run |
| `request_failures` | warning | HTTP failures recorded in a run |
| `zero_records_with_requests` | warning | requests made, zero records — never reported as "no events" |
| `source_not_available` | warning | source status below verified |
| `run_growth_anomaly` | warning | one run producing an implausible share of evidence |
| `restricted_source_record` | error | restricted-licence content entering the public store |

Findings are aggregated (one row per source/class), stored in `quality_findings`, and written to
`research/atlas/reports/quality_report.json`.

---

## 7. Licence and redistribution

`licence_status` is part of every record:

- `public_domain` — openFDA (CC0);
- `open_licence` — GUDID/AccessGUDID, Health Canada MDALL (Open Government Licence – Canada);
- `restricted` — e.g. EPO OPS; **no raw content is stored or committed**, and the verifier
  asserts zero restricted rows in the public database.

The committed sample (`research/atlas/samples/identity_pilot_pairs.json`) contains only
openFDA/GUDID and Canadian open-licence identifiers, with attribution.
