# S-029 关系本体 / Relation Ontology

**Study:** `relation_network_s029` · **Version:** `s029-1.0.0`
**Status:** frozen before any relation was counted. If it changes later, the change is recorded as an
amendment with the reason and the timestamp, and earlier results are re-run rather than edited.

This ontology exists to make one failure impossible: **a triple is not evidence.** S-028 built a
`company → technology` bipartite graph out of a shared regulatory classification and then found that
the resulting "relations" were statistical co-activity rather than cooperation. S-029 therefore
stores claims, not edges, and every claim carries the record that states it, the role it plays, the
identity decision behind it, and up to four separate clocks.

---

## 1. Three logical entities

### 1.1 `Entity`

| field | meaning | rule |
|---|---|---|
| `entity_id` | stable local id, `ent:<type>:<slug>` | never reused, never renamed |
| `entity_type` | `company_legal` \| `company_brand` \| `company_operating_unit` \| `research_institution` \| `clinical_trial` \| `publication` \| `topic` | brand ≠ legal entity; operating unit ≠ legal entity |
| `canonical_name` | one chosen display name | chosen for disambiguation, not for history |
| `known_aliases` | list of `{string, source, observed_at}` | the **exact string** seen, never a normalised form |
| `stable_external_ids` | e.g. `{nct: NCT01234567}`, `{doi: ...}`, `{pmid: ...}`, `{ror: ...}`, `{cik: ...}`, `{lei: ...}` | only ids actually verified from the source |
| `identity_confidence` | 0–1, by the rule in §5 | deterministic, not a model score |
| `identity_evidence` | list of `evidence_id` | at least one per alias that is used in a claim |
| `valid_from` / `valid_to` | period during which this identity existed | from the entity register, with the corporate event that justifies it |
| `parent_entity_id` | ownership at a **time**, see §6 | never "current parent applied to all history" |

### 1.2 `RelationClaim`

| field | meaning |
|---|---|
| `relation_id` | `rel:<predicate-short>:<hash>` |
| `subject_id`, `object_id` | `entity_id`; for unresolved strings the claim is **still stored** with the raw label and `object_id = null` |
| `predicate` | from the closed list in §2 only |
| `relation_role` | role within the predicate (§2); roles are never collapsed |
| `statement_status` | `SOURCE_STATES_IT` \| `SOURCE_IMPLIES_IT` — the literal statement vs. what a reader infers |
| `mapping_status` | `EXACT` \| `ALIAS` \| `FUZZY` \| `AMBIGUOUS` \| `UNMAPPED` \| `REJECTED` (§5) |
| `claim_status` | `VERIFIED_BY_SOURCE` \| `CANDIDATE` \| `AMBIGUOUS` \| `CONFLICTED` \| `REJECTED` \| `HUMAN_CONFIRMED` |
| `confidence` | 0–1 from the deterministic mapping rule; **not** a probability of scientific importance |
| `mapping_method` | which rule produced the identity decision |
| `source_record_id` | e.g. `NCT03437382`, `MED:38329507`, `DOI:10.1000/x` |
| `evidence_id` | → §1.3 |
| `valid_from`, `valid_to` | evidence-supported validity of the relation (§3) |
| `declared_at` | the source's own declaration date = that record's `published_at` |
| `first_seen_at` | when **we** first observed the record (real wall clock; never synthesised) |
| `time_basis` | `HISTORICAL_PROXY` \| `SOURCE_PUBLISHED` \| `ACTUAL_OBSERVATION` \| `DATE_ONLY` \| `TIME_UNKNOWN` |
| `extraction_version` | `s029-1.0.0`; a re-extraction bumps it and old claims are kept |

`HUMAN_CONFIRMED` is reserved for a real person's adjudication recorded in
`S029_HUMAN_REVIEW_WORKSHEET.csv`. This study contains no `HUMAN_CONFIRMED` rows.

### 1.3 `Evidence`

| field | meaning |
|---|---|
| `evidence_id` | content hash of the source record |
| `source` | `clinicaltrials_gov_api_v2` \| `europepmc` \| `openalex` \| `crossref` \| `ror` \| `sec_edgar` \| `gleif` |
| `original_url` | the exact URL retrieved |
| `source_record_id` | the source's own identifier |
| `payload_hash` | sha256 of the retrieved payload; the raw payload is committed gzipped |
| `original_text_reference` | the JSON path (or quoted excerpt ≤ 300 chars) that states the claim |
| `published_at`, `source_updated_at`, `first_seen_at`, `ingested_at` | §4 |
| `timestamp_precision` | `DAY` \| `MONTH` \| `YEAR` \| `UNKNOWN` |
| `provenance_quality` | `PRIMARY_STRUCTURED` \| `PRIMARY_TEXT` \| `INDEX_METADATA` |

Multiple evidence rows may support one claim; a claim that is contradicted elsewhere becomes
`CONFLICTED` and **both** evidence rows stay. Nothing is silently overwritten (§7).

---

## 2. Closed predicate list (with role semantics)

### Relation A — clinical study participation (source: ClinicalTrials.gov v2)

| predicate | role | source field | temporal type | what it means | what it does **not** mean |
|---|---|---|---|---|---|
| `SPONSORS_TRIAL` | `lead_sponsor` | `leadSponsorName` (+ `leadSponsorClass`) | INTERVAL | the entity is the registered lead sponsor of record | not "invented the technology"; not "collaborated with sites" |
| `SPONSORS_TRIAL` | `collaborator` | `collaboratorName` (+ class) | INTERVAL | the sponsor named this entity as a collaborator | not an R&D partnership unless separately confirmed (Relation C) |
| `RESPONSIBLE_FOR_TRIAL` | `responsible_party` | `responsibleParty.type` + `investigatorAffiliation` | INTERVAL | the named party is responsible for the study conduct | role can rest with an individual, not an organisation |
| `HOSTS_TRIAL_SITE` | `site_facility` | `locations[].facility` | INTERVAL | participants are enrolled at this facility | **never** evidence of cooperation with the sponsor |
| `REFERENCES_PUBLICATION` | `derived_reference` | `references[].pmid` + `citation` | POINT | the registration cites this publication | citation is not authorship, and "DERIVED" references are registry-derived |

### Relation B — publication affiliation (source: Europe PMC core records)

| predicate | role | source field | temporal type | what it means | what it does **not** mean |
|---|---|---|---|---|---|
| `AFFILIATED_WITH` | `author_affiliation` | `authorList.author[].authorAffiliationDetailsList...` | POINT | at least one author gave this affiliation on this paper | does not prove employment duration, nor that the paper is about the company's product |
| `CO_AFFILIATED_ON` | `co_affiliation` | same record, ≥1 author from A and ≥1 from B | POINT | two organisations appear as author affiliations on one paper | **co-authorship ≠ collaboration and ≠ knowledge transfer**; no direction is implied |
| `HAS_TOPIC` | `mesh_index_term` | `meshHeadingList` | POINT | the index assigned this MeSH term | index assignment, not the authors' framing |
| `FUNDED_BY` | `grant_funder` | `grantsList[].funder` | POINT | the record lists this funder | funder attribution is self-declared and often absent |

### Relation C — publicly confirmed organisational cooperation

**Not collected in this round.** The ontology reserves the predicate
`COOPERATES_WITH` (roles: `research_agreement`, `joint_development`, `consortium`, `licence`) and its
required evidence (primary document URL + quotable clause + declaration date + start date if stated),
but S-029 collected **zero** such relations, because no source in this round meets the bar. The
reserved predicate is documented here so that a later round cannot quietly relabel Relation A or B
edges as cooperation. See `NEGATIVE_FINDINGS.md` **NF-1**.

### Explicitly rejected "relations"

| rejected construct | why it is not a relation |
|---|---|
| company A and company B both active in the same technology track | shared classification, not interaction (the S-028 error) |
| company sponsors trial T, hospital H is a site of T ⇒ `COOPERATES_WITH` | no source states it; site participation is not R&D partnership |
| two institutions in the same city / same disease area | shared context only |
| same publication cites a company-funded paper | influence is unmeasured; citation ≠ transfer |
| name similarity between two entities | a mapping candidate, never a relation |

---

## 3. Temporal typing of a relation

| temporal type | definition | example | what `valid_from` may be |
|---|---|---|---|
| `INTERVAL` | the relation plausibly holds over a period, and the source dates its existence | lead sponsorship of a registered trial | `StudyFirstPostDate` — the date the relation becomes publicly evidenced; **not** the trial start date |
| `POINT` | the relation is an event, not a state | co-authorship on one paper | the publication's public date; `valid_to = null`; **the paper date is not the start of a collaboration** |
| `UNKNOWN` | the source gives no usable date | a record with no dates | `null`; precision `UNKNOWN`; never imputed |

Hard rules:

1. **Publication date ≠ collaboration start date.** A co-affiliation dated 2022 says the paper was
   public in 2022; it says nothing about when the organisations started working together, and S-029
   never writes such a start date.
2. **A declaration date is not a start date.** A cooperation announcement dated 2024-05-01 does not
   date the beginning of the cooperation.
3. Missing time stays missing (`null` + `TIME_UNKNOWN`). No `01-01` fill, no "today", no midpoint.

---

## 4. The four clocks

| clock | definition | field(s) used | never to be used as |
|---|---|---|---|
| `event_at` | when the event happened | CT.gov `startDateStruct`, `primaryCompletionDateStruct` (+ struct `type`: ACTUAL/ESTIMATED); paper publication date | publication timestamp |
| `published_at` | when the source made the record public | CT.gov `studyFirstPostDateStruct`; Europe PMC `firstIndexDate`; Crossref `created` (deposit) | event date |
| `first_seen_at` | when MedRadar observed the record | collection wall clock (real, this run) | point-in-time availability in the past |
| `valid_from`/`valid_to` | period the relation is evidenced | see §3 | either of the above clocks |

`time_basis` labels every claim:

* `ACTUAL_OBSERVATION` — we saw the record within its own publication window (only possible for
  records published after our collection started; expected to be ~0 in a historical sweep);
* `SOURCE_PUBLISHED` — the relation is dated by the source's public date, and we observed it after
  the fact;
* `HISTORICAL_PROXY` — the time is reconstructed by assuming "the record existed at its publication
  date" and we could not observe it then;
* `DATE_ONLY` / `TIME_UNKNOWN` — precision qualifiers applied together with the basis above.

The `first_seen_at` recorded in `data/` is a **real** wall clock. Its scientific meaning is honest:
it is the moment of a backfill observation of an older record. It is never presented as point-in-time
knowledge of the historical period (see `TEMPORAL_PROVENANCE.md`).

---

## 5. Deterministic identity-mapping rule (confidence, not a model score)

| `mapping_status` | rule | `claim_status` | confidence |
|---|---|---|---|
| `EXACT` | normalised source string == normalised register canonical name **and** entity valid at claim date | `VERIFIED_BY_SOURCE` | 1.00 |
| `ALIAS` | source string matches a register alias that has its own primary-source evidence | `VERIFIED_BY_SOURCE` | 0.90 |
| `ALIAS_HISTORICAL` | matches a former/subsidiary alias **and** the claim date falls inside that entity's valid period | `CANDIDATE` | 0.75 |
| `FUZZY` | token-containment match, unique candidate, no stable id | `CANDIDATE` | 0.55 |
| `AMBIGUOUS` | ≥2 register entities match, or the string is a known name collision | `AMBIGUOUS` | 0.30 |
| `UNMAPPED` | no register entity matches | (no claim) — recorded in the rejects table | 0 |
| `REJECTED` | a human/rule rejects a candidate match | `REJECTED` | 0 |

Anachronism rule: if `claim.declared_at < entity.valid_from`, the claim is downgraded to
`AMBIGUOUS` and flagged `anachronism=true`. This is the mechanical implementation of "do not project
today's group structure onto history".

---

## 6. Ownership over time

`parent_entity_id` is only ever asserted **with a date interval**, produced by the entity register
from primary sources (acquisition completion, spin-off first trade, name change). Consequences:

* a record dated 2012 under the string `Covidien` is **not** a Medtronic claim for 2012;
* a 2022 record under `GE Healthcare` precedes the GE HealthCare legal entity (2023 spin-off) — the
  register records this and the claim is flagged;
* a record under a former subsidiary name after the acquisition date may be attached to the parent
  **as a subsidiary claim**, marked `ALIAS_HISTORICAL`, never as `EXACT`.

---

## 7. Conflict and supersession

1. Two sources supporting the same claim → two evidence rows, one claim, `evidence_count = 2`.
2. Two sources disagreeing (e.g. a relation asserted in one record and denied in another) →
   `claim_status = CONFLICTED`; **both** evidence rows are kept; the conflict is counted in
   `DATA_QUALITY_REPORT.md`.
3. A later source revision does not delete the earlier observation; the earlier record keeps its own
   `first_seen_at` and hash. Supersession is recorded, never applied destructively.
4. Nothing in the claim store is edited by hand. All tables are produced by re-runnable code with a
   fixed `extraction_version`.

---

## 8. What this ontology forces us to report

Because unobservable ≠ non-existent, and because roles differ, every downstream document must report
alongside any positive count:

* the number of records **found but unmapped**, and why;
* the number of records the query could **not reach** (variant recall, §2 of the probe);
* the number of claims whose only support is a text affiliation string (`PRIMARY_TEXT`) rather than a
  structured field (`PRIMARY_STRUCTURED`);
* the share of claims whose time is `HISTORICAL_PROXY` and therefore unusable for point-in-time work.
