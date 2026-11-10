# KNOWLEDGE_GRAPH_DEMO — real queries against real evidence

Every result below was produced by the integrated pipeline against the isolated
staging database, and every item carries its evidence id, source id, the source's
own record id, a resolvable URL, the four clocks, the licence status and the grade
of any inferred link.

```bash
python -m medradar.integration import --fresh --run-id demo
python -m medradar.integration query all --out research/convergence/reports/demo.json
```

Machine output: `research/convergence/reports/demo_queries_<run>.json`.
Reference implementation: `medradar/integration/demo.py`.

<!-- convergence:numbers
c5_cited_items=134
c5_uncited_items=0
-->

## What the graph contains

| layer | count | grade |
|---|---|---|
evidence records (distinct) | 5,822 | observed fact |
evidence versions | 5,884 | append-only |
cross-source identity relations | 672 | `AUTHORITATIVE_ID_MATCH` (shared DOI) |
company attribution links | 2,101 | `SOURCE_ASSERTED_RELATION` |
identity-carrying records | 5,822 all `not_attempted` | unresolved by design |

Identity relations are only ever created from a **shared official identifier in
the same namespace across two different sources** (672 × `SAME_WORK` via DOI).
Company attribution is a *source assertion* from the manufacturer/applicant field,
never an identity match.

---

## Research chain A — regulatory identity: Medtronic → product → official record

Query `q1`. Result: **25 product identifiers** with their official GUDID record.

```
Medtronic Reusable Instruments
  evidence_id      ev_f43c3958511079690e31ec0b9c453d10
  source_id        accessgudid            (FDA GUDID, public_domain)
  source_record_id ed8c7fa7-25f2-4baa-9ce3-a7c528822132
  source_url       https://accessgudid.nlm.nih.gov/download
  manufacturer     MEDTRONIC SOFAMOR DANEK, INC.
  identifier       di = 00885074528007  (issuer GS1, scope US, primary)
  source_public_at 2022-10-07
  first_observed_at (unknown — HORIZON recorded no observation log for this record)
  fetched_at       2026-11-09T23:07:07Z
  licence_status   public_domain
```

This is the complete, verifiable `company → product → official registration` chain:
the manufacturer string comes from the GUDID record, the device is named by its
UDI-DI, and the source record id resolves to the official entry.

**Known limitation, stated plainly.** The Canada side of chain A returns **0**
records. HORIZON's MDALL licence/device records carry `manufacturer = null`; the
only firm hint is `attributes.target_firm_slice`, which is the collector's sampling
label, not a source assertion. Attributing those licences to Medtronic on that
basis would be inventing a company link, so the query returns nothing rather than
something false. Fixing this needs MDALL's company endpoint, which is future work.

## Research chain B — historical applicants: Medtronic → historical entity → patent publication

Query `q4`. **517** patent records mention a Medtronic name; they resolve to **20**
distinct applicant strings, i.e. the names the patent offices printed at
publication time:

| applicant (as printed) | patents | earliest publication seen |
|---|---|---|
| TYCO HEALTHCARE GROUP LP | 98 | 2010-01-12 |
| MEDTRONIC, INC. | 62 | 2000-03-14 |
| MEDTRONIC MINIMED, INC. | 35 | 2010-01-19 |
| COVIDIEN LP | 24 | 2020-03-10 |
| TYCO HEALTHCARE GROUP, LP | 21 | 2010-08-03 |
| ST. JUDE CHILDREN'S RESEARCH HOSPITAL | 10 | 2000-08-08 |
| ST. JUDE MEDICAL, INC. | 6 | — |
| MEDTRONIC XOMED, INC. | 5 | — |
| ARTERIAL VASCULAR ENGINEERING, INC. | 3 | — |

This is the query the identity model exists for, and it deliberately answers less
than a naive version would:

- it answers **"which legal name applied for this patent at publication"**;
- it does **not** answer "which corporate group owns it today";
- it does **not** answer "when was the acquisition", because no corporate-history
  source is in the corpus;
- it does **not** claim every patent above is a medical-device patent merely
  because the applicant name matches.

Tyco Healthcare, Covidien, St. Jude and Arterial Vascular Engineering are all
historically associated with Medtronic in the real world — but the corpus contains
no document that establishes those corporate events, so the report does not assert
them. What it establishes is narrower and true: these are the applicant names on
patents that also mention Medtronic.

## Research chain C — scholarly linkage: technology theme → independent evidence

Query `q5`, theme = FDA product code `MHX`.

| measurement | value |
|---|---|
| records carrying `MHX` | 11 |
| distinct official sources | 3 — `openfda_device_510k`, `openfda_device_classification`, `openfda_device_registrationlisting` |
| distinct canonical works | 9 |

Three *different official registers* about one theme are genuinely independent
evidence: different record types, different identifiers (`510k`, `cfr_regulation`,
`fda_registration_number`), no duplicate collapse.

Contrast with the failure mode this layer prevents: for scholarly themes the same
DOI is carried by up to **6** aggregators (Crossref, OpenAlex, Openaire, EuropePMC,
PubMed, Semantic Scholar). 307 publication records collapse to 60 works. Counting
records rather than works would overstate independent literature evidence ~5×.

Query `q3` shows the deliberately weak counterpart: keyword "infusion" returns
**9** trials/papers, all labelled `CANDIDATE_RELATION`. No paper is bound to a
specific FDA device on the strength of a word.

## Research chain D — historical time: what was knowable, and when

Query `q6`, `as_of = 2020-01-01`:

| bucket | records | meaning |
|---|---|---|
| observed by the cutoff | **0** | MedRadar's first observation of this corpus is 2026-11-09 |
| public before the cutoff, not observed then | 2,342 | genuinely *retrospective* discovery |
| not knowable by the cutoff | 3,480 | neither clock reaches the cutoff |

The zero is the honest and important result. Every record in this corpus was
first observed in November 2026; none of it could have informed a decision in 2020.
The 2,342 records that were *public* before 2020 are precisely the records for
which a retrospective study must say "discovered later" — they are **not** evidence
that MedRadar had predictive capability in 2020. Any claim of prospective
prediction built on these records would be a fabrication, and the `as_of` query
makes that visible instead of tempting.

## Query contract

Each query returns `evidence_id`, `source_id`, `source_record_id`, `source_url`,
the four clocks, `licence_status`, `identity_resolution_status`, and the grade of
any inferred link. In the full run: **134** cited items, **0** uncited. A result
that cannot cite its evidence is not returned by these functions.

## Known limits of the demonstration

1. Canada licence linkage (chain A) is blocked by missing manufacturer fields in
   the HORIZON MDALL sample.
2. Corporate-history claims (chain B) are out of scope: no acquisition evidence.
3. Multi-party procurement events are absent from this sample, so chain "one notice
   → several suppliers" cannot be shown on real data, only unit-tested.
4. The patent corpus is a bounded slice (2,228 publications), not a firm census.
5. `MHX` is one theme; independence is demonstrated for that theme, not proven
   corpus-wide.
