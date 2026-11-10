# SCHEMA_MAPPING — `horizon.evidence.v1` → `medradar.atlas.evidence.v1`

Complete field-level mapping. Every row states where the source field **actually
goes**; "preserved" means it is stored verbatim inside the ATLAS record under
`normalized.horizon`, not discarded.

Implemented in `medradar/integration/contract.py` and
`medradar/integration/adapter.py`. Verified by
`tests/convergence/test_contract_and_adapter.py::test_conversion_is_lossless`,
which asserts that every source field round-trips byte-identically.

## 1. Record-level fields (22 declared by the source)

| # | HORIZON field | ATLAS destination | transform | semantic note |
|---|---|---|---|---|
| 1 | `source_id` | `source_id` | identity | the publishing authority |
| 2 | `source_record_id` | `source_record_id` | identity | the authority's own record key |
| 3 | `source_url` | `source_url` | identity | resolvable official URL |
| 4 | `identifiers[]` | `identifiers[]` | **scheme classification, per value** | see §2 |
| 5 | `event_at` | `time.event_at` | parse date, no substitution | when the event happened |
| 6 | `source_public_at` | `time.source_public_at` | parse, quality inferred, may be **refused** | when the record became public at the source |
| 7 | `first_observed_at` | `time.first_observed_at` | **kept empty when absent** | when the pipeline first saw it |
| 8 | `fetched_at` | `time.fetched_at` | parse datetime | this copy's retrieval |
| 9 | `licence_status` | `licence_status` (+ `provenance.source_licence_status`) | mapped (§4), **gated** | redistribution rights |
| 10 | `quality_flags[]` | `quality_flags[]` (+ `normalized.convergence.source_quality_flags`) | mapped (§5), unknown preserved | source data-quality signals |
| 11 | `schema_version` | `provenance` + `normalized.convergence.source_schema` | validated **before** any parsing | must equal `horizon.evidence.v1` |
| 12 | `entity_type` | `evidence_type` (+ `normalized.convergence.source_entity_type`) | mapped (§3) | fact-type taxonomy |
| 13 | `original_name` | `normalized.horizon.original_name` | preserved | the source's own title |
| 14 | `manufacturer` | `normalized.horizon.manufacturer` | preserved; feeds company linking | free text, never an identity |
| 15 | `attributes{}` | `normalized.horizon.attributes` | preserved | source-specific payload |
| 16 | `evidence_status` | `normalized.convergence.source_record_status` | **preserved only** | never becomes an ATLAS status |
| 17 | `identity_status` | `normalized.convergence.source_record_status` | **preserved only** | never becomes identity resolution |
| 18 | `licence_note` | `provenance.attribution` | preserved | source's own licence statement |
| 19 | `notes` | `normalized.horizon.notes` | preserved | |
| 20 | `relations[]` | `normalized.convergence.relation_grades` + graded claims | graded (§6) | never promoted |
| 21 | `raw_ref` | `provenance.raw_path` + `provenance.evidence_reference` | preserved | path to the raw capture |
| 22 | `content_hash` | `source_content_hash` | **reused after validation** | upstream SHA-256, see §7 |

ATLAS-only fields created by the adapter: `evidence_id` (deterministic from
source id + evidence type + record id), `normalized_content_hash` (SHA-256 of the
ATLAS payload), `canonical_key`, `canonical_entity_id` (empty on import),
`identity_resolution_status` (**always** `not_attempted`), `relation_status`,
`collection_run_id`, `provenance.*`.

## 2. Identifier schemes (38 observed)

`value_classified = yes` means the target scheme is decided by the value, not by
the incoming scheme name.

| HORIZON scheme | ATLAS scheme | note |
|---|---|---|
| `udi_di` | `di` | FDA UDI-DI, GTIN-14; check digit validated |
| `hc_mdall_device_identifier` | `hc_device_identifier` **or** `di` | **value-classified**: promoted to `di` only on a valid GTIN-14 |
| `hc_mdall_device_id` | `hc_mdall_device_id` | regional record id, not a device identifier |
| `hc_device_licence` | `licence_no` | licence-level, not device-level |
| `uspto_510k` | `510k` | FDA clearance |
| `uspto_pma` | `pma` | FDA approval |
| `nct` | `nct` | ClinicalTrials.gov |
| `doi` | `doi` | lower-cased for canonical keys |
| `pmid`, `pubmed_mid` | `pmid` | two spellings, one namespace |
| `pmcid` | `pmcid` | |
| `openalex_id`, `s2_corpus_id`, `mag`, `handle` | same | aggregator ids |
| `cipo_patent_number`, `epo_publication_number` | `patent_no` | publication numbers |
| `epo_application_number` | `patent_application_no` | |
| `pct_publication_number`, `pct_application_number` | same | family link basis |
| `ocds_ocid`, `ocds_party_id` | same | contract event id vs party id — kept distinct |
| `ted_publication_number` | same | |
| `federal_award_id`, `sam_uei`, `usaspending_generated_internal_id` | same | award vs company vs internal id |
| `fda_product_code`, `cfr_regulation`, `hs_code`, `eurostat_comext_cell`, `hmrc_ots_series` | same | **classification, not identity** |
| `fda_fei`, `fda_registration_number` | same | establishment ids |
| `anvisa_registro`, `anvisa_processo` | same | registration vs process |
| `nih_project_num`, `nih_core_project_num` | `nih_project_num` | |
| `cordis_rcn`, `cordis_grant_agreement_id` | same | |

Unmapped schemes are passed through unchanged with `unmapped: true` rather than
invented into an existing namespace.

## 3. Entity type → evidence type

| HORIZON `entity_type` | ATLAS `evidence_type` | records in sample |
|---|---|---|
| `patent_publication` | `patent` | 2,228 |
| `trade_flow` | `trade_statistic` | 1,500 |
| `procurement_award` | `procurement_event` | 606 |
| `product_identifier` | `product_identifier` | 369 |
| `publication` | `publication` | 308 |
| `regulatory_listing` | `device_registration` | 305 |
| `regulatory_clearance` | `regulatory_clearance` | 280 |
| `clinical_trial` | `clinical_trial` | 164 |
| `grant` | `grant` | 124 |

Any `entity_type` with no faithful target is rejected rather than coerced; the
mapping table has no "other".

## 4. Licence status mapping

| HORIZON | ATLAS | ingest | redistribute |
|---|---|---|---|
| `public_domain` | `public_domain` | yes | yes |
| `open_licence` | `open_licence` | yes | yes, with attribution |
| `open_no_explicit_licence` | `open_no_explicit_licence` | yes | only with attribution + rights caveat |
| `terms_restricted` | `restricted` | **no** | no |
| `requires_licence` | `restricted` | **no** | no |
| `unknown` | `unknown` | **no** (fail closed) | no |

Measured transitions on this run: `public_domain → public_domain` 827,
`open_licence → open_licence` 3,891,
`open_no_explicit_licence → open_no_explicit_licence` 1,104. No record's licence
status was widened by the conversion.

## 5. Quality flags

Preservation is total; translation is partial and explicitly recorded.

| HORIZON flag | ATLAS flag | note |
|---|---|---|
| `MISSING_PUBLICATION_DATE`, `MISSING_FILING_DATE`, `MISSING_PRIORITY_DATE` | `missing_time` | different missing date, same consequence for time analysis |
| `MISSING_MANUFACTURER` | `missing_company` | |
| `MISSING_TITLE` | `missing_primary_identifier` | |
| `NAME_MATCH_ONLY` | `unverified_identity` | **blocks any identity claim for that record** |
| `RETROSPECTIVE_FIELD` | `derived_time` | field reconstructed after the fact |
| `PARSED_FROM_HTML`, `DOCUMENT_IS_SEARCH_REPORT` | `schema_drift` | extraction risk |
| `SITEMAP_ONLY` | `truncated_payload` | |
| `SNAPSHOT_ONLY`, `MISSING_CLASSIFICATION`, `NOT_MEDTECH_ON_FRONT_PAGE`, `DOCUMENT_IS_CORRECTION` | **no ATLAS equivalent** | preserved verbatim in `source_quality_flags`, reported as a conversion warning (2,178 records) |

Adapter-added ATLAS flags, all evidence-based: `unverified_identity` (source
status not CONFIRMED, 4,995), `missing_time` (no publication clock, 3,877),
`missing_company` (2,847), `licence_restricted` (not redistributable, 1,104),
`derived_time` (124), `schema_drift` (227),
`missing_primary_identifier` (1), `truncated_payload` (1).

## 6. Relation grading

See `EVIDENCE_CONTRACT.md` §2 for the ladder. The mapping applied is:

| HORIZON `relation_type` | grade | ATLAS relation status |
|---|---|---|
| `applicant_group_candidate` | `CANDIDATE_RELATION` | `candidate` |
| `priority_claim` | `SOURCE_ASSERTED_RELATION` | `asserted_by_source` |
| `application_to_publication` | `SOURCE_ASSERTED_RELATION` | `asserted_by_source` |
| unrecognised type | `UNVERIFIED_RELATION` | `unknown` |

Record-level `relation_status` is the **weakest** grade the record carries, not the
strongest: one candidate link makes the record a record with a candidate relation.
Taking the maximum would let a single soft link launder the whole record.

## 7. Content hashes

| hash | what it covers | source |
|---|---|---|
`source_content_hash` | upstream SHA-256 of the source record | reused from `content_hash` **after** validating it is 64 lowercase hex |
`ingested_line_sha256` | SHA-256 of the exact JSONL line consumed | computed by the reader and stored in `provenance` |
`normalized_content_hash` | SHA-256 of the ATLAS normalized payload | ATLAS `make_evidence` |
`content_hash` | equals `normalized_content_hash` (ATLAS invariant) | ATLAS validator |

Because `normalized_content_hash` covers the payload, an ATLAS record whose
`normalized` block is edited fails validation instead of looking like an unchanged
re-fetch. The upstream hash is used only when it really is a SHA-256; otherwise it
is recomputed and `source_content_hash_basis` says so.

## 8. Lossless proof

- `source_id`, `source_record_id`, `source_url`, `identifiers`, four clocks,
  `licence_status`, `quality_flags`, `content_hash` → consumed (10 fields).
- everything else → preserved under `normalized.horizon` (12 fields).
- `fields_dropped_silently = 0` on all 5,884 records.
- Round-trip test: `test_conversion_is_lossless` compares every source key/value
  against the stored copy.
- Unrecognised extra fields are counted as `extension_fields` and preserved, never
  dropped.
