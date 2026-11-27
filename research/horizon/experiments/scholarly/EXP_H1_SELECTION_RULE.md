# EXP-H1 — pre-registered anchor selection rule

**Status: FROZEN on 2026-11-10, before any anchor-set record was collected.**
Workstream: SCHOLARLY. Owner: scholarly. Code root: `research/horizon`.

This file exists so that the sample used for the cross-database de-duplication
experiment (EXP-H1) cannot be tuned after seeing the results. If a later edit is
required, it must be recorded in §9 "Amendments" with a timestamp and a reason,
and the experiment output must be re-run from scratch.

Everything below was verified against the live endpoints by *method-development*
queries (`experiments/scholarly/_scratch/`) using terms deliberately outside the
declared sample window or outside the declared firm set, so that syntax
discovery could not consume sample records.

---

## 1. What is being measured

Four quantities, all conditional on one fixed anchor set:

| quantity | definition |
|---|---|
| **source rows fetched** | number of `(source, anchor)` pairs where the source returned a record for that work |
| **distinct works after de-duplication** | number of unique works in the union, keyed on normalised DOI |
| **increment ratio** | `distinct works / source rows fetched` — the honest measure of how much unique information the multi-database fetch actually bought |
| **per-identifier coverage** | for each anchor, which of `doi`, `pmid`, `pmcid`, `openalex_id`, `arxiv`, grant numbers the source exposes |

## 2. Domain, firms, and window

**Domain.** Medical-device technology. Operationalised as a title/abstract text
filter, not as a judgement call.

**Target firms** (affiliation string filter, never an identity claim):

| firm | OpenAlex affiliation term (verbatim) | note |
|---|---|---|
| Medtronic | `medtronic` | single token, unambiguous |
| GE HealthCare | `ge healthcare` | pre-2023 spelling is `GE Healthcare` |
| Philips | `philips` | false-positive risk from `Phillips`; see §7 |
| Dräger | `dräger` | umlaut form; ASCII fallback `draeger` used only if the primary term yields 0 in a tier |
| Mindray | `mindray` | single token |

**Window.** `from_publication_date=2020-01-01`, `to_publication_date=2022-12-31`.
Rationale: three complete calendar years ending ~4 years before the observation
date, so that indexing lag is not mistaken for unavailability.

**Observation date.** 2026-11-10 (all fetch timestamps are recorded per request).

**Hard requirement.** `has_doi:true`. A work without a DOI cannot be matched
across databases by DOI and would silently inflate the "distinct works" count, so
it is excluded by construction rather than patched afterwards.

## 3. Deterministic selection algorithm

Fixed allocation: **12 anchors per firm, 60 anchors total.**

For each firm `f` in the order Medtronic, GE HealthCare, Philips, Dräger, Mindray:

```
selected[f] = []
for tier in (A, B, C):
    if len(selected[f]) >= 12: break
    params = {
        "filter":     base_filter(f) + tier_filter(tier),
        "per-page":   25,
        "sort":       "publication_date:desc",
        "select":     SELECT_FIELDS,
        "mailto":     CONTACT,
    }
    results = GET https://api.openalex.org/works  (single page only, no paging)
    order results by (publication_date DESC, OpenAlex work id ASC)
    for w in results:
        if len(selected[f]) >= 12: break
        if w.id in already_selected: continue
        selected[f].append(w)
```

with

```
base_filter(f) = "raw_affiliation_strings.search:{f},from_publication_date:2020-01-01,"
                 "to_publication_date:2022-12-31,has_doi:true"
tier_filter(A) = ',title_and_abstract.search:"medical device"'
tier_filter(B) = ',title_and_abstract.search:device'
tier_filter(C) = ''                                  # affiliation only
```

`SELECT_FIELDS = id,doi,ids,display_name,publication_date,created_date,updated_date,type,type_crossref,authorships,primary_location,awards,funders`

The tier ladder is part of the pre-registration: it makes the sample *device-
technology-targeted where the source supports it* while keeping a deterministic,
non-cherry-picked fallback for firms (Dräger) whose device-tagged output inside
the window is smaller than the allocation. The tier that supplied each anchor is
recorded per anchor.

## 4. Per-anchor cross-database fetch

For every selected anchor, identified by normalised DOI (lowercase, `https://doi.org/`
and `doi:` prefixes stripped), fetch from each source with exactly these
templates. No source is retried to obtain a more favourable answer.

| source_id | request | batch |
|---|---|---|
| `openalex` | the selection call itself | n/a |
| `crossref` | `GET https://api.crossref.org/works/{doi}` | 1 DOI |
| `europepmc` | `GET https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:"d1" OR DOI:"d2"…&resultType=core&format=json&pageSize=100` | 30 DOIs |
| `pubmed_eutils` | `GET https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=d1[doi] OR d2[doi]…&retmode=json&retmax=100` then `efetch.fcgi?db=pubmed&id=<idlist>&retmode=xml` | all DOIs, one query |
| `semantic_scholar` | `POST https://api.semanticscholar.org/graph/v1/paper/batch` body `{"ids":["DOI:d1",…]}`, `fields=title,externalIds,publicationDate,venue,authors,publicationTypes,journal` | all DOIs |
| `openaire` | `GET https://api.openaire.eu/graph/v1/researchProducts?pid={bare DOI}` | 1 DOI |

`CONTACT = medradar-research@proton.me` is sent both as the `mailto` query
parameter and inside the `User-Agent`, as OpenAlex and Crossref ask.

A source that returns zero records for an anchor is recorded as **ABSENT**, never
as agreement. A source that returns an HTTP error is recorded with its status
code; it is not silently treated as ABSENT.

## 5. Identifier normalisation

Only identifiers that literally appear in the saved response are recorded
(project rule 6). Normalisation is limited to case-folding DOIs and stripping the
`https://doi.org/` / `doi:` prefix; **no identifier is derived, inferred, or
resolved from one scheme into another.** A `pmid` counts as exposed by a source
only if that source's own payload contains it.

Per-source identifier fields that count as *exposed*:

| source | fields inspected |
|---|---|
| `openalex` | `ids.doi`, `ids.pmid`, `ids.pmcid`, `ids.mag`, `ids.openalex` |
| `crossref` | `message.DOI`, `message.alternative-id` (ISSN/IDs), `message.relation.*` |
| `europepmc` | `result.doi`, `result.pmid`, `result.pmcid`, `result.fullTextIdList`, `result.grantsList` |
| `pubmed_eutils` | `ArticleIdList/ArticleId` `IdType` ∈ {`doi`,`pubmed`,`pmc`,`mid`,`arxiv`} |
| `semantic_scholar` | `externalIds.{DOI,PubMed,PubMedCentral,ArXiv,MAG,CorpusId}` |
| `openaire` | `results[].pids`, `results[].originalIds`, `results[].instances[].pids` |

## 6. De-duplication rule

A "distinct work" is a unique key from this precedence list, applied to the
union of all *(source, anchor)* rows:

1. `doi:<casefolded DOI>` if any source exposes a DOI;
2. else `pmid:<value>` if any source exposes a PMID;
3. else the anchor's own `openalex:<work id>`.

Because the anchor selection *required* `has_doi`, rule 1 is expected to dominate;
rules 2 and 3 exist so the rule is total and so any anchor whose DOI turns out to
be absent from every other source is still counted once.

The increment ratio is `distinct_works / source_rows_fetched`. It is reported
overall and per source (marginal contribution: how many works exist that are
*not* obtainable from the same source pair).

## 7. Known contamination risks, declared up front

1. **`philips` also matches `Phillips`** (e.g. "Phillips Collection", personal
   names, "Phillips Exeter"). The affiliation string is therefore saved verbatim
   for every anchor, and every Philips anchor whose saved affiliation string does
   not contain `philips`/`philips`-rooted token is flagged
   `AFFILIATION_MAY_NOT_BE_FIRM`. No anchor is deleted: the flag travels with the
   record so the reader decides.
2. **Affiliation ≠ company.** Being listed in an affiliation string does not
   establish employment, funding, or device provenance. Records are emitted with
   `identity_status=UNKNOWN` unless the source itself asserts an organisation
   identifier, and never with `identity_status=CONFIRMED` on the strength of a
   name match.
3. **A DOI match is not a work-identity guarantee.** Two databases can point the
   same DOI at different title strings; that is measured (§8) and reported, not
   repaired.
4. **OpenAlex is a derived index.** Its `publication_date` is not authoritative
   and can change between snapshots. It is one of the disagreeing sources, not
   the referee.

## 8. Metadata disagreement measurement

For every anchor where at least two sources returned a record, compare without
repairing:

* **Title.** Exact string after collapsing internal whitespace and casefolding,
  and separately whether one is a prefix of the other (a truncation signal).
* **Authors.** Author count per source, and the family name of the first and last
  author. A differing count is reported as `author_count_delta`, never resolved.
* **Publication date.** Each source's primary publication date, and the absolute
  day difference against OpenAlex. Reported as a distribution:
  `same_day`, `1–7 days`, `8–30 days`, `31–180 days`, `>180 days`.

The dates each source exposes are listed as a *field inventory*, because whether
a *historical* date exists at all is the EXP-H3 question.

## 9. Amendments

*None.* The rule stands as written above for the run recorded in
`EXP_H1_DEDUP.json` and `EXP_H3_PUB_TIME.json`.
