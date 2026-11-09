# DATA_SOURCE_INTEGRATION — what was verified, what was built, what is blocked

**Rule:** a source is "integrated" only when a real request returned real records, the payload
shape is understood, identifiers and clocks are mapped, and the connector passes tests. A source
listed in a registry is not an integrated source.

---

## 1. Verified and used in ATLAS-001

| Source | Access basis | Verified on | Records used | Identity keys | Time mapping |
|---|---|---|---|---|---|
| **openFDA Device UDI** | public API, no key, 240 req/min | 2026-11-10 | 510 sampled across 5 firms (of 88,142 / 518 / 4,241 / 316 / 1,602 total) | `identifiers[].id` (DI), `labeler_duns_number`, `public_device_record_key` | `publish_date` → `source_public_at` (day); `public_version_date` explicitly **not** a clock |
| **AccessGUDID v3 lookup** | public API, no key | 2026-11-10 | 12 re-reads of UDI records | `gudid.device.identifiers.identifier[].deviceId` | `devicePublishDate` → public (day) |
| **openFDA Device 510(k)** | public API, no key | 2026-11-10 | 250 clearances | `k_number`, `product_code` | `decision_date` → event; public **derived** (FDA publishes no per-record publication date) |
| **Health Canada MDALL** | public JSON API + open-data release, no key | 2026-11-10 | 219,970,233-byte identifier table; 5,512 GTIN-shaped rows retained; 40 licences detailed | `original_licence_no`, `device_id`, `device_identifier` | `first_licence_dt` / `first_licence_status_dt` → event; public **derived** |

### Measured access facts (these shaped the connectors)

1. **AccessGUDID has no company search.** It is DI-keyed only. Company-level discovery must go
   through openFDA UDI; AccessGUDID is a second read of the same GUDID authority.
2. **openFDA UDI accepts a company phrase query** (`company_name:"MEDTRONIC"`) with real totals:
   Medtronic 88,142; GE HealthCare 518 (+ GE Medical Systems 955); Philips 4,241;
   Draeger 316; Mindray 1,602.
3. **MDALL listing endpoints ignore `limit`.** `licence/?licence_number=` returned 21 MB;
   `deviceidentifier/?state=active` returned ~220 MB. `?id=` returns a single row in ~0.7 s.
   The connector therefore streams the identifier table once and uses id-keyed lookups.
4. **MDALL `device_identifier` is usually not a UDI-DI.** Of 1,673,926 active rows on
   2026-11-10, 5,477 were bare 14-digit values and 5,512 normalised to a 14-digit DI when
   separators were removed (0.33 %). The rest are manufacturer model/catalogue strings.
5. **The GTIN subset bridges cleanly.** 1,200 deterministically sampled GTIN-shaped MDALL rows
   resolved to 942 openFDA UDI records; 934 produced a device pair (8 resolved records were
   package-level DIs not present in the Canadian identifier table).
6. **A failed openFDA request is a 404, not an empty page.** A wrong company string
   (`"Medtronic plc"`) returns 404; the pilot records it as a coverage error instead of
   reporting zero devices.

---

## 2. Registered but not used in ATLAS-001

These are documented in `config/atlas_sources.json` with access basis, licence and clocks. They
were deliberately **not** collected: they add research value but do not improve the product
identity question this round, and some need credentials the project owner must obtain.

| Source | Status | Blocker / next step |
|---|---|---|
| OpenAlex | `NOT_TESTED_IN_ATLAS_001` | public API; planned Phase 4 (publication evidence) |
| Europe PMC | `NOT_TESTED_IN_ATLAS_001` | public API; planned Phase 4 |
| ClinicalTrials.gov v2 | `NOT_TESTED_IN_ATLAS_001` | public API; planned Phase 4 |
| USPTO Open Data Portal | `NOT_TESTED_IN_ATLAS_001` | public bulk/API; some endpoints need a free key |
| EU TED | `NOT_TESTED_IN_ATLAS_001` | public search API; bulk endpoints may need registration |
| EPO OPS | `REQUIRES_REGISTRATION` | free OAuth consumer key; **project owner must register**; ATLAS does not create accounts |
| EUDAMED | not registered | legal/access precondition; do not scrape |
| NMPA UDI | not registered | legal/access precondition; do not scrape |

No account was created, no third-party credential was used, and no paid service was called.

---

## 3. Connector inventory

| Connector | Operations | Budget shape | Tests |
|---|---|---|---|
| `openfda_device_udi@1` | company search page, batch identifier resolver | 1 request/firm + 1/25 ids | `tests/test_atlas_connectors.py` |
| `accessgudid@1` | DI lookup | 1 request/DI, ≥1 s interval | same |
| `openfda_device_510k@1` | applicant search page | 1 request/firm | same |
| `canada_mdall@1` | whole-table stream, licence by id, company by id, device-identifier rows | 1 stream + 2 requests/licence | same |

Every request goes through `HttpClient` with a per-run budget (400 in the pilot), a minimum
interval (0.5 s), bounded retries and a JSONL ledger that is copied into `request_log`.

---

## 4. Access standards applied to every source

| Requirement | Implementation |
|---|---|
| official documentation / access basis | `config/atlas_sources.json` |
| licence and redistribution | per-source `licence_status`; restricted sources never stored |
| bounded pagination | page size capped at 100; explicit `limit`/`skip` |
| timeout and limited retries | 45 s timeout; 2 retries on 429/5xx/transport |
| rate limiting | minimum interval; `Retry-After` honoured |
| raw verification | SHA-256 of record bytes + response size |
| stable identity fields | per-source mapping table above |
| time-field mapping | explicit per source; derived/coarse flagged |
| idempotency | deterministic `evidence_id`; same hash = no-op |
| content hash | `source_content_hash` + `normalized_content_hash` |
| request log | `request_log` + JSONL ledger |
| tests | offline payload tests + live pilot |
| failure handling | `collection_runs.status` + quality finding |
| update/retire policy | source status rows; versioned evidence |

---

## 5. What is still missing for "global identity"

1. **EUDAMED Basic UDI-DI** — the only EU-wide device key. Requires the EUDAMED public
   interface to be legally accessible; not attempted.
2. **NMPA UDI** — China's registry; not attempted.
3. **A GUDID premarket-submission bridge.** GUDID v3 lookup does not publish the 510(k)
   number in the payload, so device↔clearance cannot be confirmed from public APIs at scale.
   A future route is the GUDID full release (does not carry it either) or FDA's registration &
   listing data joined on owner/operator — both are candidate-grade, not identity-grade.
4. **MDALL brand/model fields.** The licence detail endpoint gives a licence name, but the
   identifier table has no brand/model, so name comparison across the U.S./Canada bridge is
   structurally impossible for the non-UDI 99.67 %.

These are reported as `BLOCKED`/`NOT_COLLECTED`, not as completed capabilities.
