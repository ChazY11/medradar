# PHOENIX-003 — External source acquisition spec (FROZEN before any anchor is built)

This file is part of the pre-registration. It was written and committed **before** the
regulatory anchor set was constructed, so that no external-source retrieval choice can be
influenced by which milestones turn out to be interesting.

Everything below is machine-readable in `fetch_spec.json`; this markdown is the human view.

## Why two external sources, chosen at firm level

The study asks whether independent public sources show a device firm's technical activity
*before* a regulatory milestone. Retrieval must therefore be **firm-anchored and independent
of any regulatory record**, otherwise the search itself would leak the milestone.

Consequence: we harvest, for each of the five core firms, the **whole** firm-anchored corpus
available in the window — not a query built from a device name. Device-name matching happens
later, in the linker, against this frozen corpus.

## Core firms and query terms

| firm key | display | CT.gov `query.spons` | Europe PMC `AFF:` clause |
|---|---|---|---|
| `medtronic` | Medtronic | `Medtronic` | `AFF:"Medtronic"` |
| `ge_healthcare` | GE HealthCare | `GE HealthCare`, `GE Medical Systems`, `General Electric Medical Systems` | `(AFF:"GE HealthCare" OR AFF:"GE Healthcare" OR AFF:"GE Medical Systems" OR AFF:"General Electric Medical Systems")` |
| `philips` | Philips | `Philips` | `(AFF:"Philips" OR AFF:"Philips Healthcare" OR AFF:"Philips Medical Systems")` |
| `draeger` | Dräger | `Draeger`, `Dräger` | `(AFF:"Draeger" OR AFF:"Dräger" OR AFF:"Draegerwerk")` |
| `mindray` | Mindray | `Mindray` | `(AFF:"Mindray" OR AFF:"Shenzhen Mindray")` |

Notes recorded as known limitations, not corrected after the fact:

* `GE Medical Systems` / `General Electric Medical Systems` are pre-2023 division names of the
  same corporate lineage that became GE HealthCare on 2023-01-04. They are harvested because the
  lineage, not the current legal entity, is what a milestone in 2015 belongs to. This is a
  documented corporate-lineage rule, not a back-projection of today's entity.
* `AFF:"Philips"` also retrieves non-medical Philips (lighting, semiconductors in early years).
  The linker does not use affiliation alone; the contamination is measured in
  `DATA_INTEGRITY_AUDIT.md`.
* Europe PMC `AFF:` retrieves papers **by** firm-affiliated authors. Papers about the firm's
  device written only by outsiders are out of scope by construction. This is a coverage
  boundary, stated in advance, and it is the boundary that matters for "the firm's own R&D".

## Windows (frozen)

* Europe PMC: `FIRST_PDATE:[2012-01-01 TO 2025-12-31]`
* ClinicalTrials.gov: no server-side date filter; all studies returned by the sponsor query.
  `first_posted` is filtered client-side to `[2010-01-01, 2025-12-31]` when the compact file is
  written; the manifest records both raw and retained counts.
* Rationale: anchors are drawn from 2015–2024 and the analysis window for evidence is
  `[anchor_date − 5y, anchor_date − 1d]`, i.e. at most 2010-01-01. Two to three years of margin
  beyond the furthest evidence date we can need.

Do **not** add a date filter that depends on a regulatory record.

## Endpoints and politeness

* ClinicalTrials.gov API v2: `https://clinicaltrials.gov/api/v2/studies`
  `pageSize=1000`, paginate with `nextPageToken`, `countTotal=true` on the first request.
* Europe PMC REST: `https://www.ebi.ac.uk/europepmc/webservices/rest/search`
  `format=json&resultType=core&pageSize=1000`, paginate with `cursorMark`.
* User-Agent: `MedRadar-PHOENIX003/1.0 (research; contact chazy11@users.noreply.github.com)`
* Minimum inter-request delay: 0.35 s. Max 3 retries with exponential backoff (1 s, 2 s, 4 s).
  Abort the whole harvest on repeated failure rather than emitting a partial file silently.

## Output contracts (exact; the linker depends on them)

### `experiments/phoenix003/dataset/ctgov_compact.jsonl.gz`

One JSON object per line, UTF-8, gzip. Keys:

```
nct_id, source_firm, api_query, brief_title, official_title, acronym,
overall_status, study_type, phases[], conditions[], interventions[{type,name,description}],
lead_sponsor, collaborators[], enrollment, start_date, primary_completion_date,
completion_date, first_posted, last_update_posted, study_first_submitted,
results_first_posted, has_results, countries[], org_study_id, secondary_ids[],
fetched_at
```

* `first_posted` = `protocolSection.statusModule.studyFirstPostDateStruct.date` (YYYY-MM-DD or
  YYYY-MM). This is the **public availability date** used by the study.
* `study_first_submitted` recorded separately; it is *not* treated as public.
* Deduplicate by `nct_id`; if two queries return the same trial, keep the first and append the
  extra query string to `api_query` separated by ` | `.
* A study with no `first_posted` is still written, with `first_posted: null`.

### `experiments/phoenix003/dataset/epmc_compact.jsonl.gz`

One JSON object per line, UTF-8, gzip. Keys:

```
source_firm, api_query, id, source, pmid, pmcid, doi, title, author_string,
journal_title, pub_year, first_publication_date, electronic_publication_date,
first_index_date, pub_types[], is_open_access, cited_by_count,
firm_affiliations[], abstract, keywords[], mesh_terms[], fetched_at
```

* `first_publication_date` = `firstPublicationDate`. When absent, fall back in this frozen order:
  `electronicPublicationDate` → `firstIndexDate` → `(pubYear + "-01-01")`, recording which fallback
  was used in a new key `date_basis` (`"firstPublicationDate" | "electronicPublicationDate" |
  "firstIndexDate" | "pubYear"`). A record with none of these is written with
  `first_publication_date: null, date_basis: "none"`.
* `firm_affiliations`: only affiliation strings that match the firm's own patterns (the harvest
  query's AFF terms). Others are dropped, not summarised.
* `abstract`: `abstractText` truncated to 2000 characters (mark `abstract_truncated: true`).
* Deduplicate by `(source, id)`.

### Manifests

`CTgov_FETCH_MANIFEST.json` / `EPMC_FETCH_MANIFEST.json`, each containing:

```
generated_at, endpoint, queries:[{firm, api_query, http_status, requests, pages,
reported_hit_count, records_returned, records_retained, started_at, finished_at}],
counts:{records_total, records_retained, per_field_nulls:{first_posted: n, ...}},
files:[{path, bytes, sha256, lines}],
limitations:[...]
```

## Reproducibility

The harvester scripts must be deterministic given the same upstream bytes and must support
`--limit-pages N` for a smoke run. They must never write outside
`experiments/phoenix003/dataset/`, and must never touch `data/medradar.sqlite`
(read-only, and not needed at all here).

Published artefacts are cached so the pipeline runs offline: `code/*` reads only the two
`.jsonl.gz` files plus `data/medradar.sqlite`, never the network, unless `--allow-network` is
passed.
