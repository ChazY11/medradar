# S-029 关系重建试点 / Relation Reconstruction Pilot

**What this document is:** the description of the evidence set that S-029 actually built, how to read
it, and what was deliberately left out. It is the human-readable companion to
`data/claims.jsonl` (20,563 claims), `data/evidence.jsonl` (3,418 record-level evidence rows),
`data/entities.jsonl` (7,059 entities), `data/claim_rejects.jsonl` (158 kept rejects).

**What this document is not:** a knowledge graph of medical technology. It is a measured set of
evidence-backed claims with explicit roles and limits, and roughly a third of its company relations are
co-authorship facts that must never be read as cooperation.

---

## 1. The three data layers, and why a triple would not do

| layer | file | what it carries |
|---|---|---|
| Evidence | `data/evidence.jsonl` | the retrieved payload hash, the URL, the record id, the **exact JSON path** that states the claim, and the four source date fields with their precision |
| Claim | `data/claims.jsonl` | subject/predicate/object, role, statement vs mapping status, deterministic confidence, the four clocks, temporal type, and an `interpretation_limit` wherever the sentence could be over-read |
| Entity | `data/entities.jsonl` | canonical name, aliases as observed, verified external ids (NCT/DOI/PMID/ROR), identity confidence, and for companies a period of validity |

A triple `subject → predicate → object` is not stored anywhere as the primary object. It can be
projected from claims (`data/network_edges.jsonl`, 15,796 unique edges) and that projection
immediately loses the role, the date basis and the evidence — which is exactly what S-028 did not have.

## 2. What is in the pilot, by relation family

| family | claims | source of the statement | an example |
|---|---:|---|---|
| company → trial, lead sponsor | 2,514 (with collaborators) | CT.gov `leadSponsorName` / `collaboratorName` | Medtronic (via its unit "Medtronic Cardiac Rhythm and Heart Failure") leads NCT00239226; first posted 2005-10-14 |
| company → trial, responsible party | 3 | `responsibleParty.investigatorAffiliation` | rare; the responsible party is usually an individual |
| institution → trial (sponsor, collaborator, site) | 2,393 | CT.gov org fields and `locations[].facility` | "Mayo Clinic Arizona" is a site of a GE HealthCare-sponsored study (ROR FUZZY 0.85) |
| trial → publication | 4,351 | CT.gov `references[].pmid` + citation | a Dräger trial citing a Europe PMC paper; 150/150 sampled PMIDs exist in Europe PMC |
| company → publication (author affiliation) | 623 | Europe PMC `authorAffiliation` | 623 claims from 57 corporate-email or organisational affiliations |
| institution → publication | 1,552 | Europe PMC affiliation text → ROR | institution matched to a ROR id with the matched field recorded |
| **company ↔ institution co-affiliation** | **1,567** | same publication, ≥1 company author + ≥1 institution author | e.g. a GE HealthCare author and a ROR-matched institution on DOI 10.1097/hjh.… (2018) |
| publication → MeSH topic | 7,455 | Europe PMC MeSH headings | index terms, not the authors' framing |
| company → publication (declared funder) | 105 | Europe PMC `grantsList` | "Medtronic, Santa Rosa, California" declared as a funder |
| **C confirmed cooperation** | **0** | — | no source in scope meets the bar; predicate reserved |

Every row above is `VERIFIED_BY_SOURCE` or `CANDIDATE`; none is `HUMAN_CONFIRMED`.

## 3. What a claim row looks like, and what to read first

A sponsor claim (format from `data/claims.jsonl`):

```
relation_id      rel:SPONSORS_TRIAL:<hash>
subject_id       ent:company:medtronic
predicate        SPONSORS_TRIAL
object_id        ent:trial:NCT00239226
relation_role    lead_sponsor
statement_status SOURCE_STATES_IT          # the registry literally says it
mapping_status   ALIAS                     # …under an operating-unit string, not the parent name
claim_status     CANDIDATE                 # because identity, not the statement, is the uncertain part
confidence       0.9                       # deterministic rule, see ontology §5
evidence_id      ev:<payload_sha256>:NCT00239226
valid_from       2005-10-14                # = studyFirstPostDate: when the relation is publicly evidenced
declared_at      2005-10-14
event_at         2005-11                   # month precision: the study start, not a day
first_seen_at    2026-11-04T…Z             # our own real collection clock
time_basis       HISTORICAL_PROXY          # we did not observe it in 2005
anachronism      false
```

Read `claim_status` before `confidence`, and read `mapping_status` before either: a relation can be
perfectly stated by the source (`SOURCE_STATES_IT`) and still be a `CANDIDATE` because the *string*
was mapped to the group. That distinction is the whole point of the exercise.

## 4. The rejects are part of the dataset

158 rows in `data/claim_rejects.jsonl`, each with the rule, the reason and the record:

| reject kind | rows | example |
|---|---:|---|
| Dräger surname / email collision | 62 | "Institute of Anatomy, University of Bern … draeger@ana.unibe.ch" |
| former parent, deliberately not the company | 52 | "General Electric" (parent of the pre-2023 division) |
| historical name before group ownership | 17 | "Tyco Healthcare Group LP" (became Covidien; acquired 2015) |
| award / programme title | 11 | "Philips Chair for Medical Information Technology, RWTH Aachen" |
| non-entity free text | 6 | "MEDTRONIC labs provide the aquamantys® probes for the study." |
| subsidiary not yet owned | 6 | "Covidien, GI Solutions" in a 2010 trial |
| personal-name collision | 4 | "Raymond C. Philips Unit", "Philips R. Lee Institute" |

Without these rows the pilot would look cleaner and be less true.

## 5. Deliberate exclusions (with reasons, not silently dropped)

* **38 Europe PMC patent records** (source `PAT`) that matched affiliation queries — not publications.
* **All 52 "General Electric" trial strings** — the former parent is a different legal person from
  GE HealthCare; a GE corporate trial is not a GE HealthCare trial.
* **Datascope Corp.** — the entity register (verified against the 2008 8-K) shows Mindray bought the
  Patient Monitoring *business*, not the company; four sponsor strings are therefore not Mindray claims.
* **MeSH topics are excluded from the pilot's network claims** in the feasibility section because an
  index term is not a relation between two actors.
* **Co-affiliation is not promoted** to a company↔institution cooperation edge anywhere in this study.

## 6. What the evidence can and cannot answer, in one table

| question | answerable | by what |
|---|---|---|
| does this company appear as lead sponsor of this trial? | yes | registry field + entity mapping with dates |
| is this institution a site of that trial? | yes | `locations[].facility` (sample only) |
| were a company author and an institution author on this paper? | yes | affiliation text + ROR |
| did the company fund this paper? | partially | self-declared grant acknowledgement (105 rows) |
| does the registration cite this publication? | yes | registry reference list (current-state!) |
| were these two organisations collaborating? | **no** | no collected record states it |
| did knowledge flow, and in which direction? | **no** | nothing states a direction; co-authorship is not a flow |
| when did a collaboration start? | **no** | the earliest public record is not a start date |
| what was knowable in 2015? | **no** | 0 claims are observed-as-of; sources are current-state |

## 7. Reproducibility

Rebuild with `python code/s029_07_claims.py` after the collection and mapping steps; the evidence
counts, per-family counts and per-company counts are re-derived by `code/s029_12_verify_report.py`
(13/13 checks pass). Every claim's evidence id is `ev:<sha256 of the committed payload>:<source record
id>`, so any claim can be walked back to bytes.
