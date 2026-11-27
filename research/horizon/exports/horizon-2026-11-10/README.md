# Export `horizon-2026-11-10`

Schema: `horizon.evidence.v1`  
Generated: 2026-11-09T23:35:44Z  
Generator: `tools/build_export.py`

## How to load

```python
import json
rows = [json.loads(l) for l in open('cipo_canada.jsonl', encoding='utf-8')]
```

Every row validates against `research/horizon/hz/schema.py`. Rows are already deduplicated *within* a source; cross-source dedupe uses `hz.schema.dedupe_key`.

## What this export does NOT claim

- `accessgudid`: 320 records; 320 (100%) carry a recorded public observation date and 0 (0%) a recorded event date. Top quality flags: MISSING_FILING_DATE=320.
- `brazil_anvisa`: 120 records; 120 (100%) carry a recorded public observation date and 120 (100%) a recorded event date. Top quality flags: RETROSPECTIVE_FIELD=120.
- `canada_mdall`: 174 records; 0 (0%) carry a recorded public observation date and 174 (100%) a recorded event date. Top quality flags: MISSING_PUBLICATION_DATE=174.
- `cipo_canada`: 2000 records; 2000 (100%) carry a recorded public observation date and 916 (46%) a recorded event date. Top quality flags: MISSING_CLASSIFICATION=2000, NAME_MATCH_ONLY=2000, NOT_MEDTECH_ON_FRONT_PAGE=2000, SNAPSHOT_ONLY=2000.
- `clinicaltrials_gov`: 164 records; 164 (100%) carry a recorded public observation date and 94 (57%) a recorded event date. Top quality flags: MISSING_FILING_DATE=70.
- `crossref`: 59 records; 59 (100%) carry a recorded public observation date and 59 (100%) a recorded event date. Top quality flags: none.
- `epo_publication_server`: 228 records; 228 (100%) carry a recorded public observation date and 228 (100%) a recorded event date. Top quality flags: PARSED_FROM_HTML=227, MISSING_PRIORITY_DATE=43, DOCUMENT_IS_SEARCH_REPORT=28, DOCUMENT_IS_CORRECTION=3.
- `eu_cordis`: 60 records; 0 (0%) carry a recorded public observation date and 0 (0%) a recorded event date. Top quality flags: SNAPSHOT_ONLY=60.
- `eu_ted`: 299 records; 299 (100%) carry a recorded public observation date and 297 (99%) a recorded event date. Top quality flags: MISSING_FILING_DATE=2.
- `europepmc`: 37 records; 37 (100%) carry a recorded public observation date and 37 (100%) a recorded event date. Top quality flags: none.
- `eurostat_comext`: 1400 records; 0 (0%) carry a recorded public observation date and 1400 (100%) a recorded event date. Top quality flags: MISSING_PUBLICATION_DATE=1400.
- `nih_reporter`: 64 records; 64 (100%) carry a recorded public observation date and 56 (88%) a recorded event date. Top quality flags: MISSING_FILING_DATE=8, RETROSPECTIVE_FIELD=4.
- `openaire`: 59 records; 59 (100%) carry a recorded public observation date and 59 (100%) a recorded event date. Top quality flags: SNAPSHOT_ONLY=59.
- `openalex`: 60 records; 60 (100%) carry a recorded public observation date and 60 (100%) a recorded event date. Top quality flags: none.
- `openfda_device_510k`: 160 records; 0 (0%) carry a recorded public observation date and 160 (100%) a recorded event date. Top quality flags: MISSING_PUBLICATION_DATE=160.
- `openfda_device_classification`: 60 records; 0 (0%) carry a recorded public observation date and 0 (0%) a recorded event date. Top quality flags: MISSING_FILING_DATE=60, MISSING_PUBLICATION_DATE=60.
- `openfda_device_pma`: 60 records; 0 (0%) carry a recorded public observation date and 60 (100%) a recorded event date. Top quality flags: MISSING_PUBLICATION_DATE=60.
- `openfda_device_registrationlisting`: 60 records; 0 (0%) carry a recorded public observation date and 0 (0%) a recorded event date. Top quality flags: MISSING_FILING_DATE=60, MISSING_PUBLICATION_DATE=60.
- `pubmed_eutils`: 37 records; 37 (100%) carry a recorded public observation date and 37 (100%) a recorded event date. Top quality flags: none.
- `semantic_scholar`: 56 records; 55 (98%) carry a recorded public observation date and 55 (98%) a recorded event date. Top quality flags: SNAPSHOT_ONLY=56, MISSING_PUBLICATION_DATE=1.
- `uk_find_a_tender`: 62 records; 62 (100%) carry a recorded public observation date and 62 (100%) a recorded event date. Top quality flags: none.
- `uk_hmrc_trade`: 100 records; 0 (0%) carry a recorded public observation date and 100 (100%) a recorded event date. Top quality flags: MISSING_PUBLICATION_DATE=100.
- `un_comtrade`: 608 records; 0 (0%) carry a recorded public observation date and 608 (100%) a recorded event date. Top quality flags: MISSING_PUBLICATION_DATE=608.
- `usaspending`: 245 records; 0 (0%) carry a recorded public observation date and 245 (100%) a recorded event date. Top quality flags: MISSING_PUBLICATION_DATE=245, MISSING_FILING_DATE=245.
- These are SAMPLES, not censuses. EP: 10 weekly publication dates enumerated out of ~2 500. CA: firm-scoped slice of an open bulk extract ending 2022-02-28. Row counts must not be read as coverage.
- `identity_status = CANDIDATE` records carry a name-fragment firm attribution only. No record in this export claims a confirmed cross-source identity.
- `canada_mdall`: 174 records share only 60 `dedupe_key` entity keys — group on `dedupe_key`, do NOT filter on it.
- `openfda_device_classification`: 60 records share only 50 `dedupe_key` entity keys — group on `dedupe_key`, do NOT filter on it.
- `openfda_device_pma`: 60 records share only 33 `dedupe_key` entity keys — group on `dedupe_key`, do NOT filter on it.
- `openfda_device_registrationlisting`: 60 records share only 26 `dedupe_key` entity keys — group on `dedupe_key`, do NOT filter on it.
- `nih_reporter`: 64 records share only 9 `dedupe_key` entity keys — group on `dedupe_key`, do NOT filter on it.
- `openaire`: 59 records share only 58 `dedupe_key` entity keys — group on `dedupe_key`, do NOT filter on it.
- `eu_ted`: 299 records share only 93 `dedupe_key` entity keys — group on `dedupe_key`, do NOT filter on it.
- `uk_find_a_tender`: 62 records share only 16 `dedupe_key` entity keys — group on `dedupe_key`, do NOT filter on it.
- `cipo_canada`: export carries a DETERMINISTIC STRATIFIED SAMPLE of 2000 from 19702 acquired records (cap 2000). The full extract is regenerable with the committed connector; the stratum is (firm candidate, publication decade), so every firm and decade survives.

## Per-source counts

| source | records | unique keys | with id | with public date | licence |
|---|---|---|---|---|---|
| `accessgudid` | 320 | 320 | 320 | 320 | public_domain |
| `brazil_anvisa` | 120 | 120 | 120 | 120 | open_no_explicit_licence |
| `canada_mdall` | 174 | 60 | 174 | 0 | open_licence |
| `cipo_canada` | 2000 | 2000 | 2000 | 2000 | open_licence |
| `clinicaltrials_gov` | 164 | 164 | 164 | 164 | public_domain |
| `crossref` | 59 | 59 | 59 | 59 | open_no_explicit_licence |
| `epo_publication_server` | 228 | 228 | 228 | 228 | open_no_explicit_licence |
| `eu_cordis` | 60 | 60 | 60 | 0 | open_no_explicit_licence |
| `eu_ted` | 299 | 93 | 299 | 299 | open_no_explicit_licence |
| `europepmc` | 37 | 37 | 37 | 37 | open_licence |
| `eurostat_comext` | 1400 | 1400 | 1400 | 0 | open_licence |
| `nih_reporter` | 64 | 9 | 64 | 64 | public_domain |
| `openaire` | 59 | 58 | 59 | 59 | open_licence |
| `openalex` | 60 | 60 | 60 | 60 | open_licence |
| `openfda_device_510k` | 160 | 160 | 160 | 0 | public_domain |
| `openfda_device_classification` | 60 | 50 | 60 | 0 | public_domain |
| `openfda_device_pma` | 60 | 33 | 60 | 0 | public_domain |
| `openfda_device_registrationlisting` | 60 | 26 | 60 | 0 | public_domain |
| `pubmed_eutils` | 37 | 37 | 37 | 37 | open_no_explicit_licence |
| `semantic_scholar` | 56 | 56 | 56 | 55 | open_no_explicit_licence |
| `uk_find_a_tender` | 62 | 16 | 62 | 62 | open_licence |
| `uk_hmrc_trade` | 100 | 100 | 100 | 0 | open_licence |
| `un_comtrade` | 608 | 608 | 608 | 0 | terms_restricted |
| `usaspending` | 245 | 245 | 245 | 0 | open_no_explicit_licence |
