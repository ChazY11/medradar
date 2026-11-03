# S-029 数据质量报告 / Data Quality Report

**Machine-readable source for every number here:** `artifacts/quality_metrics.json`
(sections A–D and the verdict), plus the per-source artefacts named inline.
**No number in this document is hand-entered**; `code/s029_12_verify_report.py` re-derives the
headline counts (**13/13 checks pass**, including a check that each claim's evidence id resolves to its own source record).

---

## A. Coverage

| quantity | value |
|---|---:|
| ClinicalTrials.gov studies collected (unique NCT ids) | **2,498** |
| of which reached by a non-canonical company string | 184 Medtronic / 232 Philips (see §B) |
| Europe PMC records collected (unique) | **770** |
| — of which MEDLINE / PMC / **patent records (PAT)** | 729 / 3 / **38** |
| site-facility rows from the 209-study location sub-sample | **1,126** |
| institution candidates extracted | **4,395** |
| relation claims built | **20,563** |
| — `VERIFIED_BY_SOURCE` / `CANDIDATE` | 10,412 / 10,151 |
| records kept as explicit rejects (not discarded) | **158** |
| claims with a stable external identifier on ≥1 side | **100%** (subject side) |
| claims with a `published_at` | **100%** |
| claims with a stable identifier on **both** sides | **19.31%** strict (3,971/20,563); **40.34%** if `object_external_id` is allowed (8,296) |

**Claims per relation family** (`quality_metrics.json` → `A_coverage.claims_by_family`):

| family | claims |
|---|---:|
| A company → trial (lead sponsor / collaborator) | 2,514 |
| A company → trial (responsible party) | 3 |
| A institution → trial (sponsor / collaborator / site) | 2,393 |
| A trial → publication (registry reference) | 4,351 |
| B company → publication (author affiliation) | 623 |
| B institution → publication (author affiliation) | 1,552 |
| B company ↔ institution (co-affiliation on one paper) | 1,567 |
| B publication → MeSH topic | 7,455 |
| B company → publication (declared grant funder) | 105 |
| **C confirmed organisational cooperation** | **0** (reserved; no admissible source) |

**Per company** (claims whose subject is the company): Medtronic 2,487 · Philips 963 · GE HealthCare
886 · Mindray 362 · **Dräger 114**. All five exceed the pre-registered 40-claim floor; the ratio
between the largest and smallest is 21.8×, which is itself a selection-bias warning: this dataset is
effectively Medtronic-weighted, and any cross-company comparison would be driven by company size and
by how the registry names the sponsor, not by research conduct.

**Claims by publication year:** fairly flat at 922–1,474 for 2019–2026, **but this is not a growth
statement** — before 2014 the Europe PMC affiliation evidence is largely unretrievable (§C.4), so the
left part of any such curve is an indexing artefact.

## B. Entity resolution

**B.1 Company strings.** 6,940 company-string occurrences were classified; decisions
(`artifacts/company_mapping.json`, `data/company_mentions.jsonl`):

| decision | count | meaning |
|---|---:|---|
| `ALIAS` (operating unit / group member) | 1,516 | mapped to the group, unit-level; confidence 0.70–0.90 |
| `ORG_TEXT` (affiliation names the company as the organisation) | 1,137 | 0.80 |
| `EXACT` (string equals the group name) | 1,020 | 1.00 |
| `NOT_MAPPED` (former parent, historical name pre-ownership) | 69 | deliberately **not** a claim |
| `ORG_EMAIL` (corporate email domain) | 57 | 0.95 |
| `REJECTED` (collision / not an entity) | 73 | e.g. Dräger surname, Philips personal names |
| `WEAK_TEXT` (award title, acknowledgement text) | 11 | 0.30–0.45 |
| `AMBIGUOUS` (ownership date precedes group ownership) | 6 | e.g. "Covidien, GI Solutions" 2010 |

**B.2 The company is largely a fiction in registry data.** Measured by the entity auditor
(`artifacts/entity_resolution_metrics.json`, §2): denominator = mentions whose role is `lead_sponsor` or
`collaborator` (ClinicalTrials.gov sponsor fields) and whose mapping is accepted
(`EXACT/ALIAS/ORG_TEXT/ORG_EMAIL`). **61.8%** of Medtronic's such strings (1,083/1,753) are operating
units rather than the parent name ("Medtronic Cardiac Rhythm and Heart Failure" alone appears 280
times), and **99.5%** of Philips's (399/401) are units/divisions. The claim-level equivalent after the
claim-store join is 61.7% (1,079/1,749) and 99.5% (393/395). Consequently, **67.68%** of records carrying a
company mention would be invisible to a study that queried only the exact parent name
(`artifacts/network_feasibility.json` → `sensitivity`). This is the quantified version of the S-028
lessons about entity identity; it is not a rounding detail.

**B.3 Institutions.** ROR resolution of 4,395 candidates: **EXACT 1,193 (27.1%)**, FUZZY 1,778
(40.5%), **UNMAPPED 1,424 (32.4% of all candidates)**. That last figure is the wrong denominator for a
resolution-failure claim: ROR indexes research organisations, so the 211 company strings and 1,041
unclear strings in the candidate set cannot resolve by construction. Among the **3,143
institution-classified** candidates the unmapped rate is **18.2%** (572/3,143) — below the
pre-registered 20% ceiling. Both numbers are reported in `quality_metrics.json` and the choice is
documented as a denominator clarification, not a threshold change.

A second resolution pass that tries alternative organisation spans inside a messy affiliation string
recovered **564** candidates (first-pass unmapped 1,988 → 1,424), which is the honest attribution of
that gap: part of it was the parser, part is the registry. Remaining failures are real (small hospitals,
company-adjacent organisations, and ROR's lack of non-research entities).

**B.4 Historical identity.** Verified from primary documents (SEC 10-K/8-K, GLEIF) by the entity
auditor: Medtronic plc took over 2015-01-26 (Covidien acquisition completed), MiniMed acquisition
2001-08-28, GE HealthCare spin-off completed 2023-01-03, Respironics 2008-03-17, Mindray's Cayman
holding delisted 2016-03-03, Datascope's Patient Monitoring business sold 2008-05-14 (Datascope Corp.
itself was **not** acquired), ZONARE 2013-07-17. These dates are enforced in code: **6** mentions are
`AMBIGUOUS` because the string names an entity before the group owned it (e.g. a 2010 trial sponsored by
"Covidien"), and **282** claims carry an anachronism flag (GE "GE Healthcare" strings dated before the
legal entity existed — the same business, a different legal person). On ownership dating, the auditor's first pass reported 86 mentions whose group-ownership start was
unestablished; after reconciliation it **accepted** the study's MiniMed attribution (dated by the
2001-08-28 acquisition) and withdrew that figure. The reconciled residual is **5 claims (0.13%)** whose
entity's own start date the register could not establish (4 Dräger Medical GmbH/Inc strings and 1
Medtronic Vascular unit string); their `relation_id`s are listed in
`entity_resolution_metrics.json` → `ownership_reconciliation.undated_ownership.claims_affected_ids` and
they must be excluded from any time-sensitive test rather than accepted silently.
Two different notions of "anachronism" coexist and must not be merged: the mapper flags **282 claims**
whose string names a division of a former parent (`division-era`), while the entity auditor's own check
counts **0** violations of a register `valid_from`; the auditor verified the two sets are **disjoint**.
The 1.37% anachronism rate in the network gate is the mapper's notion, not the register's.

**B.5 Collisions that a naive pipeline would have counted as relations** (`data/claim_rejects.jsonl`):
Dräger-A author with email `draeger@ana.unibe.ch` (62 rejects of **95** Draäger affiliation mentions = **65.26%**; 33 accepted), "Raymond C. Philips Unit" / "Philips R. Lee Institute" (4), "Imperial College Healthcare" /
"Orange healthcare" substring matches (6), 52 "General Electric" strings (former parent, not GE
HealthCare), 17 historical-name strings ("Tyco Healthcare"), 11 award/programme titles.

## C. Temporal quality

**C.1 Which clocks exist** (temporal auditor, `artifacts/clock_audit.json`; details in
`TEMPORAL_PROVENANCE.md`):

| clock | populated | precision |
|---|---:|---|
| `published_at` | 100% | DAY 100% |
| `declared_at` | 100% | DAY 100% |
| `event_at` | 78.77% | DAY 13,580 / MONTH 2,618 / missing 4,365; trial families are 52.8–66.7% month-only |
| `first_seen_at` | 100% | datetime; **107 distinct values across 20,563 claims** (all within a 200-second collection window) |
| `valid_from` | 100% | DAY 100% |
| `valid_to` | **0%** | — no relation can be claimed to have ended |

**C.2 Genuine observed-as-of evidence: 0 claims.** Adopting the temporal auditor's stricter standard,
a claim is `ACTUAL_OBSERVATION` only if its `first_seen_at` came from the Live Observatory ledger — and
it never does, because the ledger contains 400 observations from one day (2026-11-03) and none of them
matches a claim in this dataset. Under the looser definition, computed from the clocks themselves (own `first_seen_at` minus
`published_at` within 0–7 days), there are **76 claims behind 10 source records**, of which 34 have a
lag of ≤1 day. Of the 76, 60 carry the explicit flag `near_realtime_this_study=true` (they were
originally labelled `ACTUAL_OBSERVATION`; that label has been removed and the claims are stored as
`HISTORICAL_PROXY`, so **0 claims retain the `ACTUAL_OBSERVATION` label**), and 16 are `HAS_TOPIC`
claims whose family label is `SOURCE_PUBLISHED` — the label and the clock did not agree, which is
exactly why the lenient window is computed from the clocks rather than from a label. None of the 76 is a ledger observation, so none is
used for any point-in-time claim. Observed lag over all 20,563 claims: median **3,327 days**, p25 1,615, p75 5,052, max 9,434.

**C.3 Ordering inside a year.** `declared_at` is day-precision in every family, so relations can be
ordered by declaration. `event_at` cannot: trial families are month/year-only for the majority, and
`REFERENCES_PUBLICATION` has no event time at all (100% missing).

**C.4 The retrievability break (a source artefact that looks like history).** In year-stratified
Europe PMC samples, the share of records whose returned text actually contains the query token:
2010 **28.0%**, 2011 44.0%, 2012 51.6%, 2013 62.5%, 2014 **97.1%**, 2015 96.9%, then ≥94.6% every year
after. Before 2014 the index hit frequently cannot be verified from the record at all (MEDLINE indexed
only first-author affiliations). **Any "relations per year" trend crossing 2014 is measurably a
metadata artefact.**

**C.5 Contradictions, separated by kind.** **2,775 claims (13.5%)** have `published_at` < `event_at`
(month-precision dates compared at first-of-month). This must not be reported as one error class:
**2,169** are trial-registration relations where the registration lawfully precedes the study start
(pre-registration), and **606** are non-trial cases where the index date precedes the issue date
(an artefact). Both are counted separately in `quality_metrics.json`. 24 `REFERENCES_PUBLICATION` claims cite a paper published after the trial's first-post date —
not a contradiction but proof that the registry's reference list is **current-state**, not as-of
(a 2012 trial citing a 2026 paper means the reference was added later).

## D. Relation quality

| quantity | value | comment |
|---|---:|---|
| evidence rows | **3,418** | one per (retrieved payload, source record), hash-addressed; 113 distinct payload envelopes |
| claims per evidence row / per envelope | ~6 / ~182 | many claims come from one query payload; the record id + JSON path pinpoint each claim |
| claims whose evidence is `PRIMARY_STRUCTURED` | **45.04%** | a structured source field states it |
| claims whose evidence is `PRIMARY_TEXT` | **54.96%** | an affiliation string states it |
| claims derived rather than directly stated | **7.62%** | co-affiliation (1,567) is the only derived predicate |
| claims resting on alias/fuzzy identity | **17.57%** | group-member or fuzzy mapping |
| claims resting on fuzzy identity only | **10.08%** | institution ROR token-overlap matches |
| conflicted claims | **0** | no source pair in this round disagreed about the same relation |
| co-affiliation share of company relations | **32.56%** | this is why the prohibition matters |

**The most important sentence in this section:** 32.56% of the company relations in this dataset are
co-affiliation on a publication. They are a fact about authorship, and the study emits them as
`CO_AFFILIATED_ON` with `interpretation_limit = "co-authorship is not collaboration, not knowledge
transfer, and has no direction"`. They must never be aggregated into a "collaboration network".

## E. What these measurements license

**Licensed:** "we can reconstruct 20,563 machine-labelled, individually traceable relation claims across
two relation families and five companies, with 100% stable-identifier coverage, 45% structured-source
support, 0.0% genuine point-in-time observation, and measured entity error rates of 18.2% (institutions)
/ 1.9% (company ambiguity)."

**Not licensed by anything in this dataset:** any precision, recall or accuracy figure (no human
adjudication exists — `HUMAN_VALIDATION_PENDING`); any knowledge-transfer, collaboration or causal
claim; any predictive claim; any claim that a relation which was not found does not exist.
