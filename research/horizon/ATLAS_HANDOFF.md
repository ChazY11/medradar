# ATLAS_HANDOFF

**HORIZON-001 → ATLAS-001 data handoff. Nothing here requires changing ATLAS-001's
code, schema, migrations or working tree.**

---

## 1. What you can consume today

```
research/horizon/exports/horizon-2026-11-10/
    MANIFEST.json        counts, per-file sha256, licence posture, coverage limits
    README.md            how to load, and what the export does NOT claim
    <source_id>.jsonl    horizon.evidence.v1, one record per line, 24 sources
    <source_id>.jsonl.sha256
```

Load with nothing but the standard library:

```python
import json, glob
rows = [json.loads(l) for p in glob.glob('exports/horizon-2026-11-10/*.jsonl')
                        for l in open(p, encoding='utf-8')]
```

Verify before trusting:

```powershell
cd research\horizon
python -m hz.cli verify          # re-hashes every export file against the manifest
```

Current state of that command: `exports` all `ok:true`; the only failure is
`SOURCE_PROBES/regulatory/` missing a `PROBES.json`, which is a probe-log
completeness issue and does **not** affect record validity.

---

## 2. The schema (`horizon.evidence.v1`)

Defined and enforced in `research/horizon/hz/schema.py`. This is a **temporary
contract** until you publish a stable Evidence Contract; when you do, I convert via
a separate adapter rather than silently redefining fields.

| field | type | meaning |
|---|---|---|
| `schema_version` | str | always `horizon.evidence.v1` |
| `source_id` | str | stable identifier of the data source, matches `registry/sources/<id>.json` |
| `source_record_id` | str | identifier **within** the source (publication no., UDI-DI, NCT, award id…) |
| `entity_type` | enum | `patent_publication`, `regulatory_listing`, `regulatory_clearance`, `product_identifier`, `publication`, `clinical_trial`, `grant`, `procurement_award`, `trade_flow`, `organisation`, `postmarket_event`, `recall` |
| `original_name` | str | the name exactly as the source wrote it, never normalised |
| `identifiers[]` | list | `{scheme, value, issuing_authority, scope, is_primary}` — only values that appear in the source |
| `manufacturer` | str \| null | the source's own applicant/company field, verbatim |
| `attributes` | object | source-specific payload (see §4) |
| `event_at` | ISO date \| null | **when the described event happened** |
| `source_public_at` | ISO date \| null | **when a human could first have seen this record** |
| `first_observed_at` | ISO datetime | first time HORIZON saw it |
| `fetched_at` | ISO datetime | this retrieval |
| `source_url` | str | the URL that produced the record |
| `content_hash` | str | sha256 over a canonical subset (stable across fetch runs) |
| `licence_status` | enum | `open_licence`, `public_domain`, `open_no_explicit_licence`, `terms_restricted`, `requires_registration`, `requires_licence`, `unknown` |
| `licence_note` | str | what we relied on, with URL |
| `identity_status` | enum | `UNKNOWN`, `CANDIDATE`, `CONFIRMED` |
| `evidence_status` | enum | `CANDIDATE`, `CONFIRMED`, `REJECTED` |
| `quality_flags[]` | list | closed vocabulary, see §5 |
| `relations[]` | list | `{type, to_scheme, to_value, basis, status}` |
| `raw_ref` | str \| null | path into `DATASETS/` for the verbatim response |
| `notes` | str \| null | free text |

### Two fields that require your attention

**`identity_status` and `evidence_status` are separate axes.** A record can be
`evidence_status=CONFIRMED` (the source said it) while `identity_status=UNKNOWN`
(we cannot tell which company or product it is). Do not collapse them.

**There is no single `publication_date`.** `event_at` and `source_public_at` are
different clocks and must stay separate. The measured evidence for this is in
`EXPERIMENT_RESULTS.md` EXP-H3: 60 % of scholarly works get different publication
dates from different databases, 36.7 % by more than 30 days.

---

## 3. Dedupe keys — read this before grouping

`hz.schema.dedupe_key(record)` returns an **entity** key (UDI-DI, DOI, patent
number, NCT…), falling back to the content hash.

* `dedupe_key` is for **grouping** records that describe the same entity.
* `dedupe_key` must **never** be used to filter a table.

There are sources where many records legitimately share one entity key:

| source | records | distinct entity keys | what the records are |
|---|---|---|---|
| `eu_ted` | 299 | 93 | one row per supplier on a contract-award notice |
| `uk_find_a_tender` | 62 | 16 | one row per supplier on an OCDS release |

Filtering on `dedupe_key` there deletes distinct suppliers. This actually happened
in the first export build and was caught; the exporter now de-duplicates on
`(source_record_id, content_hash)` and writes a manifest note wherever entity-key
multiplicity exists.

For "is this the same *work*" across scholarly databases, the correct key is the
**DOI** — see `EXP_H1_DEDUP.json`: 308 source rows collapse to 60 works.

---

## 4. `attributes` payload by entity type

### `patent_publication` — `epo_publication_server`
`publication_id, publication_date, bulletin, filing_date, application_number,
kind, document_role, is_independent_disclosure, ipc[], ipc_subclasses[],
medtech_ipc_subclasses[], cpc[], applicants[], proprietors[], inventors[],
patentees[], representative, priority_claims[{date,country,number}], priority_date,
title_all_langs{lang:title}, abstract, designated_states[], pct_application,
pct_publication, pct_publication_date, date_43_application, date_45_grant, clock{}`

Key points:
* `date_43_application` = application publication; `date_45_grant` = grant. `kind`
  decides which becomes `source_public_at`.
* `document_role` ∈ {`application_publication`, `application_publication_no_search_report`,
  `search_report`, `granted_specification`, `granted_specification_amended`,
  `granted_specification_limited`, `corrected_title_page`, `corrected_specification`}.
  `is_independent_disclosure=false` marks A3/B8 — **exclude these from any count of
  technical disclosures** or you inflate the corpus by ~13.6 %.

### `patent_publication` — `cipo_canada`
`patent_number, grant_date, filing_date, public_availability_basis, status_code,
application_type_code, document_kind, publication_kind, country_of_publication,
filing_country, filing_language, examination_request_date,
bibliographic_extract_date, pct_application_number, pct_publication_number,
pct_publication_date, parent_application_number, title_en, title_fr, applicants[],
owners[], inventors[], party_ownership_timeline[{party,type,enable_date,end_date,country}],
ipc[], ipc_subclasses[], medtech_ipc_subclasses[], priority_claims[], priority_date,
firm_group_candidates[], alias_matches[[firm, alias]], clock{}`

Key points:
* `party_ownership_timeline` is the **ownership history with effective dates** — the
  most useful structure found this round for historical company attribution.
* All CIPO records are `identity_status=CANDIDATE` with `NAME_MATCH_ONLY`. There is
  **no IPC** for CIPO (see §7 gap 1), so these are firm-scoped, not
  technology-scoped.
* `source_public_at` is present for granted patents only (15 490 / 19 702).

### `product_identifier` / `regulatory_*`
See the registry entries and `REGULATORY_FRONTIER_REPORT.md`; the important field is
that the official identifier (UDI-DI, licence number, K/PMA number) is in
`identifiers[]` with the issuing authority, never in `attributes`.

### `publication`
`doi_values_all[]` (OpenAIRE can carry several DOIs), affiliation strings verbatim,
per-source date fields, `created/index` timestamps where the source has them.

### `trade_flow`
`firm_attribution="none"`, `aggregation_semantics`, HS code, reporter, partner,
period, flow. **A trade record never identifies a firm.**

### `procurement_award`
`stage` ∈ {`tender`, `award`, `delivery`} kept distinct; supplier identifiers
(SAM UEI where present); device-class token if named.

---

## 5. `quality_flags` vocabulary

```
MISSING_PUBLICATION_DATE  MISSING_FILING_DATE     MISSING_PRIORITY_DATE
MISSING_IDENTIFIER        MISSING_MANUFACTURER    MISSING_TITLE
MISSING_CLASSIFICATION    NOT_MEDTECH_ON_FRONT_PAGE
SITEMAP_ONLY              DOCUMENT_IS_SEARCH_REPORT  DOCUMENT_IS_CORRECTION
NAME_MATCH_ONLY           IDENTIFIER_SELF_ASSIGNED
SNAPSHOT_ONLY             RETROSPECTIVE_FIELD      TRUNCATED_RESPONSE
PARSED_FROM_PDF           PARSED_FROM_HTML         DUPLICATE_OF_OTHER_SOURCE
LICENCE_UNCLEAR           RATE_LIMITED             PARTIAL_PAGE
```

An unknown flag is a **build error** in `tools/build_export.py`, not a warning.

---

## 6. Reusable code (independent of ATLAS-001)

| module | use it for |
|---|---|
| `hz/schema.py` | record construction, validation, dedupe keys |
| `hz/timeq.py` | `audit_clocks()`, `classify_record()` — **the four-clock admission test** |
| `hz/http.py` | bounded HTTP: request budget, byte cap, retry policy, request log |
| `hz/probe.py` | declarative probes → `PROBES.json` evidence |
| `hz/registry.py` | source register with access/licence/blocker semantics |
| `hz/export.py` | versioned export + manifest |
| `hz/tls.py` | AIA chain completion for servers with a broken chain (verification stays on) |
| `hz/verify.py` | offline integrity self-check |

None of these import `medradar.*`. You can vendor them or read the JSONL directly.

---

## 7. Known gaps and known limits (do not paper over these)

1. **CIPO has no IPC in this export.** `PT_IPC_classification` is published and open
   but >230 MB per range split, so it was deliberately not downloaded. Consequence:
   CIPO is a firm-scoped slice, **not** a medical-device slice. Closing this is the
   single highest-value next acquisition.
2. **EP sample is 228 documents over 10 weeks**; 179 sit in two dense weeks. Three of
   five target firms have zero hits. That is sampling, not absence.
3. **No patent family IDs.** Requires EPO OPS or Lens with a key.
4. **No US patents.** Every answering USPTO endpoint needs a free API key.
5. **2,928 records are `EVENT_ONLY`** (trade, USAspending, 510(k), PMA, MDALL) with
   no recorded public date. They are ineligible for observability claims —
   `audit_clocks` will reject them, by design.
6. **Identity is not solved.** Zero `CONFIRMED` cross-source device identities were
   produced. Everything is `CANDIDATE` or `UNKNOWN`. That is the state of the
   evidence, not a coding shortcut.
7. **UN Comtrade is licence-ambiguous** — its public API contradicts its usage
   agreement. Its 608 records are marked `terms_restricted` and no research claim
   rests on them. Project-owner decision needed.

---

## 8. If we need to align with your published contract

Nothing in this handoff changes if you publish a new Evidence Contract. The intended
path is:

1. You publish the contract.
2. I add `tools/convert_to_atlas.py` mapping `horizon.evidence.v1` → your schema,
   field by field, with an explicit mapping table in this file.
3. The export directory is regenerated under a new `export_id`; the old one stays
   readable.

No field meaning will be changed silently. If a field cannot be represented in your
contract, it is dropped **and listed** rather than coerced.

---

## 9. Open questions for ATLAS-001

1. Do you want `source_public_at` as a single value plus per-source disagreement, or
   one row per (record × source) with its own date? The measurement in EXP-H3 says
   the latter is more truthful but heavier.
2. How should `identity_status=CANDIDATE` records enter your identity resolver —
   pre-filtered, or as weak evidence with a confidence?
3. Do you want the CIPO `party_ownership_timeline` flattened into
   `(entity, valid_from, valid_to)` ownership edges, or handed over as-is?
4. `dedupe_key` is an entity key, not a record key. Please confirm your grouping
   semantics before using it to de-duplicate.
