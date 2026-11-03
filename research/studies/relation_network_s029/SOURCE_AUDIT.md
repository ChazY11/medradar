# S-029 数据源审计 / Source Audit

**Every number below was produced by a script and stored in an artefact** (paths given per section).
Nothing here is an estimate from memory. Measurements are dated to the collection window
2026-11-04 (UTC), recorded per HTTP call in `data/request_log.jsonl`.

Question this audit answers (RQ1): **what can each source state, about which relation, with what
reach, and what does it silently not say?**

---

## 0. Sources used, and why no others

| source | role in this study | access | licence / cost |
|---|---|---|---|
| ClinicalTrials.gov API v2 | Relation A: sponsor / collaborator / responsible party / site | keyless JSON API, paged | public domain US government data |
| Europe PMC REST | Relation B: author affiliation, co-affiliation, MeSH, declared funders | keyless JSON API | open (Europe PMC terms) |
| ROR (Research Organization Registry) | institution identity | keyless API | CC0 |
| OpenAlex | cross-source agreement only | keyless, shared free budget | CC0 metadata |
| Crossref | DOI/funder verification, literature verification | keyless polite pool | open |
| medradar observation ledger | the only genuine `observed_as-of` evidence | read-only SQLite | internal |

Deliberately **not** used: commercial databases, paid APIs, purchased datasets, cloud compute. Two
candidate sources were considered and rejected as out of scope for a five-company pilot: FDA openFDA
device events (already in S-028's frozen lane; would re-import its 12.1% coverage problem) and NMPA
(no machine-readable public API). Recorded as a scope decision, not a silent omission.

---

## 1. ClinicalTrials.gov — a registry of *registrations*, not of research collaborations

**Reach is name-string reach.** `query.spons` matches the sponsor/collaborator name *string*,
token-wise. Measured hit counts (`artifacts/query_recall_probe.json`):

| company | canonical string | Σ over all tested variants | variant / canonical ratio |
|---|---:|---:|---:|
| Medtronic | 1,675 | 1,940 | 1.16 |
| Philips | 376 | 684 | 1.82 |
| GE HealthCare | 343 | 741 | 2.16 |
| Mindray | 6 | 18 | 3.00 |
| Dräger | **2** | **18** | **9.00** |

The Dräger row is the clearest measurement in this section: the diacritic canonical spelling returns
2 studies, while the ASCII/compound spellings return 18 distinct studies. **A study that searched only
the canonical name would have concluded that Dräger has almost no clinical research activity.** Every
one of the 2,498 collected studies was reached by *some* company-named query; 184 Medtronic studies and
232 Philips studies were reached only through a non-canonical string (measured by the entity auditor in
`artifacts/entity_resolution_metrics.json`, §5).

**What the fields can and cannot state:**

| field | states | does not state |
|---|---|---|
| `leadSponsorName` | who registered the study | who invented or owns the technology |
| `collaboratorName` | whom the sponsor named as participating | that a research agreement exists (that is Relation C, none collected) |
| `responsibleParty` | who is accountable for conduct (can be an individual) | an organisational relation when it is a person |
| `locations[].facility` | where participants were enrolled | **anything about cooperation with the sponsor** |
| `references[].pmid` + citation | that the registration cites a publication | authorship, funding, or that the paper resulted from the trial |

**A measured data-quality defect:** the sponsor field occasionally contains free text, not an entity
name. Observed and registered in the entity register's `not_company_registry`:
`"MEDTRONIC labs provide the aquamantys® probes for the study."` and `"GE Medical Systems ultrasound
(only technical support)"`. A pipeline that trusts the field as an organisation identifier would
count these as companies.

**Time:** `studyFirstPostDate` is 100% day-precision in the audited sample (n=128); `startDateStruct`
is **44.53% month-only** (Dräger 100%, Medtronic 57.5%, GE 55.0%, Philips 25.0%, Mindray 0.0%);
`resultsFirstPostDate` is missing in 67.19% (temporal auditor, `artifacts/clock_audit.json`).
Half of trials are posted *before* their stated start date — legitimate pre-registration, and a trap
for anyone who treats "first posted" as "start of research".

**As-of retrieval is impossible.** Tested directly: the API rejects `asOf`/`date`/`studyVersion`
parameters (HTTP 400) and has no `/history` or `/versions` endpoint (404). A trial first posted
2008-02-15 and updated 2025-07-02 returns one current state only. **There is no way to ask this source
what it said in 2015.**

---

## 2. Europe PMC — an index whose query semantics are wider than its returned text

**Composition of what an affiliation query actually returns** (`artifacts/extract_report.json`,
770 unique records): MEDLINE 751, **PAT 38 (patent records)**, PMC 3.

The 38 patent records are not publications. A pipeline that treats every Europe PMC hit as a paper
would silently add patent records to a publication graph. They are excluded and counted
(`data/claim_rejects.jsonl`, rule `not_a_publication_record`).

**The query does not always hit the field you think.** `AFF:"Draeger"` returned papers by authors
**surnamed** Draeger, matched through the email address inside the affiliation field
(`draeger@ana.unibe.ch`) and through name forms such as `"H.T. Draeger, MD, University Health System"`.
Measured on the collected sample: of 81 Draeger affiliation mentions, **62 (76.5%) were rejected** as
surname/email collisions; the accepted 17 came from strings such as `Dräger Safety AG & Co. KGaA` or a
`@draeger.com` corporate email. This is the name-collision failure mode in its purest form, and it is
why the ASCII spelling of Dräger cannot be used as a company query without a classifier.

An analogous, smaller collision exists for Philips: `"Raymond C. Philips Unit, Division of Genetics…"`
and `"Philips R. Lee Institute for Health Policy Studies"` are named after people, not the company, and
are rejected. For GE, substring matching would have counted `"Imperial College Healthcare NHS Trust"`
(`Colle(ge Healthcare)`) and `"Orange healthcare"` (`Oran(ge healthcare)`) as the company; word-boundary
matching plus an explicit not-company registry rejects them (measured counts in
`artifacts/company_mapping.json`).

**Structural break in retrievability (the most important source finding).** For each year-stratified
sample, the returned record was checked for an affiliation string that actually contains the query
token (`artifacts/quality_metrics.json` → `affiliation_retrievability`):

| company | overall retrievability | 2010 | 2011 | 2012 | 2013 | 2014+ |
|---|---:|---:|---:|---:|---:|---:|
| Medtronic | 89.4% | 5/10 | 8/10 | 6/10 | 5/10 | 9–10/10 |
| GE HealthCare | 84.0% | 3/10 | 2/10 | 4/10 | 5/10 | 9–10/10 |
| Philips | 89.4% | 5/10 | 7/10 | 5/10 | 8/10 | 9–10/10 |
| Dräger | 61.0% | 1/10 | 3/10 | 1/1 | 2/2 | mixed (small n) |

Up to 2013 a large share of index hits carry **no retrievable affiliation text at all** (MEDLINE
indexed only first-author affiliations before ~2014). The consequence is severe and must be stated in
any downstream use: **a "relations per year" curve built on this source has a mechanical break around
2014 that has nothing to do with the companies.** S-029 therefore does not interpret the yearly
affiliation counts as growth of collaboration.

**Time:** `firstPublicationDate` (event), `firstIndexDate` (index visibility; median lag after
publication 4.0 days, p75 19, max 1245), `dateOfCreation`/`dateOfRevision` (record metadata; revision
moves forward). There is no field stating when the *relation* began, and no observed-as-of stamp.
A paper published in 2022 therefore dates the co-affiliation to 2022, not the start of any collaboration.

---

## 3. ROR — a research-organisation registry, not an organisation registry

4,395 institution candidates were extracted from three families and resolved against ROR
(`artifacts/ror_resolution.json`). Final outcomes after the alternative-span pass:

| family | EXACT | FUZZY | UNMAPPED |
|---|---:|---:|---:|
| trial organisation fields | 582 | 341 | 512 |
| trial site facilities | 272 | 270 | 270 |
| publication affiliations | 339 | 1,167 | 642 |

Two things must be said plainly:

1. **The denominator contains non-institutions.** Of 4,395 candidates, 211 are company names (corporate
   suffix and no institution keyword) and 1,041 are ambiguous strings. ROR does not index companies, so
   an "unmapped" company is not a resolution failure. The honest metric is the unmapped rate among
   *institution-classified* candidates: **572 / 3,143 = 18.2%** (the naive all-candidate rate is 32.4%).
   Both are reported in `DATA_QUALITY_REPORT.md` §B.3, and T3's failure comes from a different clause
   (10.1% fuzzy-identity claims against a 10.0% ceiling), not from this one.
2. **The parser contributed to that rate, and was improved rather than excused.** A department-first
   string ("Medical Imaging Centre, Uppsala University Hospital") fails a whole-string lookup. A second
   pass tries alternative organisation spans and recovers **564** candidates (first-pass unmapped 1,988
   → 1,424), recording every attempt in `ror.resolution_attempts`. What remains is real: ROR has no
   record for many hospitals and for most company-adjacent organisations.

ROR's search is fuzzy by design — `"Mayo Clinic"` returns 441 results — so a match is a decision. The
study only grants `EXACT` on normalised equality with a ROR display name/alias/acronym, keeps
token-overlap matches as `FUZZY`/`CANDIDATE`, and stores the matched field and the candidate list.

---

## 4. OpenAlex and Crossref — verification channels, with their own limits

* **OpenAlex** `created_date` is a bulk-ingest stamp, not a publication clock: on a 24-work sample the
  median gap between `publication_date` and `created_date` is **3,567.5 days**, and legacy records all
  carry `created_date = 2016-06-24` (temporal auditor). It may be used to check *identifiers*, never to
  date an event. Budget discipline: DOIs are batched 50 per request against a shared
  unauthenticated budget, and the request list is stored in `artifacts/crosssource.json`.
* **Crossref** `created` is a DOI-deposit timestamp (median 13.5 days after `issued`, max 12,598,
  and 6/30 *negative*), `issued` is day-precision on only 17/30 sampled works. It verifies identity and
  funders; it does not date the science.

---

## 5. Observation ledger — the only real `observed_as-of` evidence, and it is one day long

Read-only audit (`artifacts/clock_audit.json`, sha256 unchanged before/after):

* 400 observations, all created on **2026-11-03**, 400/400 marked `reconstructed_from_run_history`,
  **0** direct captures;
* genuine prospective observations (lag ≤ 1 day): **6 / 400 (1.5%)**; lag > 7 days: 365 (91.25%);
  median lag 65 days, max 7,613 days;
* re-measuring the S-028 audit's 29 metrics on this ledger produced **0 changes** —
  `STAYED_THE_SAME`. No new collection cycle has run.

Consequence, stated as a binding rule for this study: the historical relation set is
`HISTORICAL_PROXY`. The only claims that could ever be `ACTUAL_OBSERVATION` are records whose
publication date falls within a week of our own collection time — this round found **8 publications
and 3 trials** in that window out of 3,268 collected records. That is not enough to build a
point-in-time evaluation, and no number in S-029 is presented as if it were.

---

## 6. What no source in this round can provide (RQ3/RQ4 boundary)

| wanted relation | available? | why not |
|---|---|---|
| Company ↔ Company cooperation | **no** | no source in scope states it; Relation C reserved with zero rows |
| Company → ResearchInstitution confirmed partnership | **no** | trial co-participation and paper co-affiliation are not partnership statements |
| Direction of knowledge flow | **no** | nothing in any collected record states a direction |
| True `valid_from` of a collaboration | **no** | best available is the first public record date |
| Historical as-of snapshot of any source | **no** | verified impossible at CT.gov; the others are current-state indexes |
| Company→publication *funding* | **partial** | 112 grant acknowledgements name a pilot company (self-declared) |
| Trial→publication link | **yes** | registry `references` with PMID/DOI, verified in data |

The audit's conclusion is not that the sources are bad. It is that **each source states a specific
kind of fact, and the study's claims are bounded by the field that states it** — which is exactly what
S-028 did not do when it read co-classification as cooperation.
