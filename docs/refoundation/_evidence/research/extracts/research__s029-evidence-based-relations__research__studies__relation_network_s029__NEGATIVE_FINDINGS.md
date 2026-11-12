# S-029 负结果与自我更正登记 / Negative Findings and Self-Corrections

**Rule of this document:** every negative result and every correction of the study's own work is
recorded with the measurement that produced it and what it does *not* license. Nothing is deleted
because it weakened a claim. This file is a primary scientific output, not an appendix.

Each entry is labelled:
`OBSERVED_FACT` (measured in this study) · `SOURCE_SUPPORTED_CLAIM` (a source states it) ·
`MACHINE_INFERENCE` (our pipeline decided it) · `HYPOTHESIS` · `UNKNOWN`.

---

## NF-1 — Relation C (confirmed organisational cooperation) has **zero** admissible rows `OBSERVED_FACT`

The ontology reserved `COOPERATES_WITH` with roles (research agreement / joint development / consortium /
licence) and an evidential bar: primary document, quotable clause, declaration date, start date if
stated. No source in this round meets it. Trial co-participation is not a cooperation statement,
co-authorship is not a cooperation statement, and press-release mining was out of scope.
**Consequence:** the study has **no** company↔company edge and no confirmed company↔institution
partnership edge. Do not describe the network as a collaboration network. **Does not license:** "these
companies do not cooperate" — it licenses "this study did not establish any cooperation claim".

## NF-2 — One third of company relations are co-authorship, not cooperation `OBSERVED_FACT`

1,567 `CO_AFFILIATED_ON` claims = **32.56%** of all company relations. They are stored with
`interpretation_limit = "co-authorship is not collaboration, not knowledge transfer, and has no
direction"`. In the network feasibility inventory they form a **single 1,056-node component**, which is
an artefact of publication co-authorship, not evidence of a research community. **This is the S-028
error in its most tempting form and the study refuses it explicitly.**

## NF-3 — The Dräger ASCII query is 65.26% name collisions `OBSERVED_FACT`

`AFF:"Draeger"` returns papers by authors **surnamed** Draeger (email `[EMAIL_REDACTED]`, name forms
like "H.T. Draeger, MD"). Of 95 Draeger affiliation mentions, **62 (65.26%) were rejected**; the 33 accepted came
from organisational strings or `@draeger.com` addresses. Canonical "Dräger" spelling was worse in a
different way: ClinicalTrials.gov returned **2** studies for "Dräger" and **18** for variant spellings.
**Does not license:** "Dräger has no clinical research". It licenses: "a name-based search for this
company is unusable without a collision classifier."

## NF-4 — Corporate history: four corrections to the study's own assumptions `OBSERVED_FACT`

1. **Datascope was never acquired by Mindray.** The verified 2008 8-K shows only the Patient Monitoring
   *business* was sold (closed 2008-05-14); Datascope Corp. continued independently. My provisional rule
   had treated the company as Mindray. Now 4 sponsor strings are correctly `NOT_MAPPED`.
2. **There was no 2018 "relisting" of the Cayman issuer.** The 2018 ChiNext listing is a *different
   legal person* (Shenzhen Mindray). The study brief's premise was corrected by the register.
3. **"Covidien" before 2015-01-26 is not Medtronic.** 6 mentions are `AMBIGUOUS` for this reason
   (e.g. "Covidien, GI Solutions" in a 2010 trial); 17 further strings are historical names
   ("Tyco Healthcare") that never existed under Medtronic ownership.
4. **GE "Healthcare" before 2023-01-03 is a division, not the legal entity.** 282 claims carry an
   anachronism flag. The business is the same; the legal person is not. **Does not license:** attributing
   pre-spin GE Healthcare activity to GE HealthCare Technologies Inc. as a legal fact.

## NF-5 — Europe PMC affiliation retrievability breaks in 2014 `OBSERVED_FACT`

Share of year-stratified samples whose returned record actually contains the query token: **2010 28.0%**,
2011 44.0%, 2012 51.6%, 2013 62.5%, **2014 97.1%**, then ≥94.6% every year after. Before 2014 the index
hit frequently cannot be verified from the record at all. **Consequence:** any "relations per year"
curve crossing 2014 is measurably a metadata artefact. **Does not license:** "company–academic
collaboration grew after 2014."

## NF-6 — Patent records contaminate a publication search `OBSERVED_FACT`

38 of 770 Europe PMC records returned by affiliation queries are **patent records** (`source=PAT`), not
publications. They are excluded and counted. A pipeline that trusts the hit type would add patents to a
publication graph.

## NF-7 — Zero genuine point-in-time evidence; the pipeline's own labels were wrong and were corrected `SELF-CORRECTION`

The claims builder labelled 60 claims (0.29%) `ACTUAL_OBSERVATION` under a rule "published within 7 days
of our fetch". The independent temporal audit showed that none of the 20,563 claims has a `first_seen_at`
recorded by the Live Observatory, and all 107 distinct `first_seen_at` values fall inside a 200-second
ETL window. **Correction applied (twice — the first patch wrote the field after the file had already been
persisted, which the auditor correctly caught): every claim now carries `strict_observed_asof=false`
and an explicit `observation_system` field **in the committed file**; the verdict uses the strict count
(**0**), and the lenient window computed from the clocks (`first_seen_at − published_at ∈ [0,7] days`)
is **76 claims behind 10 source records, 34 with lag ≤1 day** — reported alongside with the
definitional difference stated (`DATA_QUALITY_REPORT.md` §C.2).
**Does not license:** any point-in-time, prospective or as-of reconstruction claim.

## NF-8 — No human adjudication exists; therefore no precision, recall or accuracy may be quoted `MACHINE_INFERENCE`

The worksheet has 102 stratified rows with `human_label`, `reviewer_id`, `review_date`,
`review_reason`, `adjudication_status` **empty by construction** (verified by `s029_12` check V6).
No claim is `HUMAN_CONFIRMED`. Status: **`HUMAN_VALIDATION_PENDING`**.
**Does not license:** "the relations are 9x% accurate", "machine–human agreement", "validated dataset".

## NF-9 — Registry reference lists are current-state, so trial→publication dates cannot be trusted `OBSERVED_FACT`

Of 4,351 reference claims, only 26 resolve inside this study's publication sample; of those, **24 (at day precision; 23 when
compared at year level, which is the auditor's figure)**
cite a paper published *after* the trial's first-post date (up to 14 years).

> "23 of the 4351 REFERENCES_PUBLICATION claims (0.53% of the family) cite a paper whose publication
> date is later than the trial's first-post date, by up to 14 years. The ClinicalTrials.gov reference
> list is current-state — the registry keeps no history of when a reference was added — so these are
> references added at a later registry update, not future citations: the relation is back-dated because
> it is dated by the trial's first-post date instead of the paper's publication date. For 16 of the 23
> the trial's last-update date is on or after the paper's publication date, which is consistent with
> that mechanism; for 7 it is not, and those 7 remain unexplained and should be checked individually."
> — wording from `TEMPORAL_PROVENANCE.md` §5.3 (independent temporal auditor)

The relation exists; its date basis must be re-based on the publication or marked unknown. A 150-PMID external probe shows **150/150 resolvable in Europe PMC** — so the low
in-sample rate is a sampling artefact, not a linkage failure.

## NF-10 — Two pre-registered conditions fail marginally or by denominator choice `OBSERVED_FACT` + `MACHINE_INFERENCE`

* **T3**: the institution-unmapped clause passes under the class-correct denominator (18.2% ≤ 20%) but
  the *fuzzy-identity* clause fails by **0.08 percentage points** (10.08% vs a 10.0% ceiling). The naive
  all-candidate unmapped rate is 32.4% and is also reported.
* **T5**: clause (a) passes (100% of sampled trial-referenced PMIDs resolvable); clause (b) passes
  on its conditional denominator (300/300 = 100% of institutions that appear in ≥2 sources carry a
  verified ROR id — true by construction once an entity is a ROR institution). The *population* share,
  15.08% of all 1,990 institution entities appearing in both sources, is reported separately as a
  descriptive statistic and is not the threshold quantity. The first version of the code divided by the
  wrong denominator and emitted FAIL; corrected as `GO_NO_GO_CRITERIA.md` Appendix A Amendment 2, with
  both numbers retained. An independent OpenAlex check finds **452 of 454** institution-bearing papers
  corroborated (99.6%).

Neither marginal condition changes the verdict: **T4 (0 point-in-time) and T6 (no human review) are
decisive on their own**, and a verdict of `REVISE` would still be required even if T3 and T5 both passed.
Both denominators and both pass/fail values are stored in `artifacts/quality_metrics.json`.

## NF-11 — ROR does not cover a large minority of the institutions we found `OBSERVED_FACT`

Among 3,143 institution-classified candidates, **18.2% (572) are unmapped**; including non-institution
strings the rate is 32.4%. A second resolution pass that tries alternative organisation spans recovered
564 candidates, so part of the gap was my parser. What remains is a genuine registry gap (small hospitals,
company-adjacent organisations). **Does not license:** treating an unmapped institution as absent.

## NF-12 — Canonical-name-only reconstruction would lose two thirds of the evidence `OBSERVED_FACT`

Of 3,134 records carrying a company mention, only 1,013 are reachable by the exact parent name:
**67.68% lost**. The loss is not random — it concentrates in companies with divisional structure
(Philips: 99.5% of accepted sponsor strings are units; Medtronic: 61.8%).

## NF-13 — Two "time" fields that look like clocks are infrastructure stamps `SOURCE_SUPPORTED_CLAIM`

OpenAlex `created_date` is a bulk-ingest stamp (median **3,567.5 days** after `publication_date`; legacy
records all 2016-06-24). Crossref `created` is a DOI deposit (median 13.5 days after `issued`, max
12,598, and 6/30 negative). Neither may be used to date an event. The temporal auditor verified that no
`asOf`/`date`/`studyVersion` parameter exists at ClinicalTrials.gov (HTTP 400) and no `/history` endpoint
(404): **historical as-of retrieval is impossible, not merely unimplemented here.**

## NF-14 — S-028's data situation has not improved `OBSERVED_FACT`

The temporal audit re-measured **29 metrics** of the frozen S-028 input and observatory ledger:
**0 changed** (`STAYED_THE_SAME`). The ledger still holds 400 observations from one day, 6 with lag ≤1
day; the frozen input still has one `first_seen_at` value for 55,090 rows. No new collection cycle has
run. Any S-030 plan that assumes "the observatory has been accumulating history since S-028" is wrong.

## NF-14b — An ownership-date statistic of this study was withdrawn after reconciliation `SELF-CORRECTION`

The entity auditor first reported **86 mentions** (2.31% of accepted mappings) whose group-ownership
start was unestablished, dominated by 79 "Medtronic MiniMed, Inc." strings. Reconciliation showed the
mapper dates those strings through the MiniMed acquisition event (2001-08-28, verified in the register),
and the auditor **withdrew** the 86/2.31% figure. The residual is **5 claims (0.13%)** — 4 Dräger
Medical GmbH/Inc strings whose LEI is inactive with a merge date the register cannot establish, and 1
Medtronic Vascular unit string — listed by `relation_id` in the metrics artefact. Both the withdrawn and
the reconciled numbers are recorded here rather than only the favourable one.

## NF-15 — A provenance defect in this study was found and fixed `SELF-CORRECTION`

Evidence rows were initially keyed by the *query payload* (which holds up to 200 studies), so a claim's
`original_text_reference` could point at a different record from the same payload. Detected while
building the pilot examples. **Correction:** evidence ids are now
`ev:<payload_sha256>:<source_record_id>` (3,418 rows), the verifier resolves them per record, and check
V1b passes for all 20,563 claims. Recorded because a traceability claim that is subtly false is worse
than no claim.

## NF-16 — ClinicalTrials.gov sponsor fields can contain free text, not entities `OBSERVED_FACT`

Observed strings: `"MEDTRONIC labs provide the aquamantys® probes for the study."` and
`"GE Medical Systems ultrasound (only technical support)"`. Registered in the entity register's
`not_company_registry` and rejected by rule. A field that usually holds an organisation does not always
hold one.

## NF-17 — The verdict is `NO-GO FOR PREDICTION` `MACHINE_INFERENCE` (from pre-registered rules)

T1, T2, T5 pass; T3, T4, T6 fail. The relation layer is reconstructable and traceable, but it is neither
point-in-time nor human-validated, and the institution identity layer is incomplete. The next round must
**either** run a live forward-collection to accumulate genuine observed-as-of history **or** complete the
human adjudication — before any temporal prediction is attempted. Thresholds were not relaxed; the
marginal failures are documented above rather than renegotiated.

---

## What is *not* in this file, deliberately

No claim that a missing relation does not exist. Every zero in this study is a statement about **what the
sources and the search could reach**, never about the world. Searches that returned nothing (e.g.
"Draegerwerk" at ClinicalTrials.gov, funder registry entries for Dräger and Mindray) are recorded in
`artifacts/query_recall_probe.json` and `artifacts/crosssource.json` with the exact query strings.


## NF-18 — An independent adversarial review found 9 unreproducible numbers and 5 ontology divergences; all were corrected `SELF-CORRECTION`

Before delivery, an independent reviewer (not the author) recomputed 24 numbers and audited the claim
store against the frozen ontology. Result: **NOT_READY**, with these defects, all now fixed:

| defect | correction |
|---|---|
| "evidence rows 113" | 113 is the number of *payload envelopes*; evidence rows are **3,418** (one per payload+record) |
| "stable identifier on both sides 100%" | **19.31%** strict (3,971/20,563), **40.34%** allowing `object_external_id` |
| Dräger "81 mentions / 76.5% / 17 accepted" | **95 mentions / 62 rejected (65.26%) / 33 accepted** |
| "MEDLINE 751" | 751 is *records seen*; **729 unique** MEDLINE records (770 unique total) |
| "184 / 232 studies reached **only** via non-canonical string" | they were reached **with** one; **only-via** is 22 (Medtronic) / 6 (Philips) |
| GE and Philips degrees swapped; "90× spread" | Philips 381, GE HealthCare 345; spread is **238×** |
| "alias/fuzzy 17.59%" | **17.57%** |
| "23 future-dated references" | **24** at day precision, 23 at year level |
| T5 clause (b) divided by all institutions | corrected to the conditional denominator (100%, PASS); population share reported separately (15.08%) |
| `mapping_status` outside the closed list (2,190 claims) | the three extra values are now formally in the ontology (Appendix A1) |
| anachronism rule not implemented as written | the actual two-case implementation is now documented (Appendix A2), not merely implied |
| `HAS_TOPIC` `declared_at != published_at` (7,007 claims) | fixed in code; `declared_at` is the record's `published_at` |
| reference roles not in the ontology | actual roles (`background/derived/result`) documented (Appendix A3) |
| "the order of events is verifiable" | **removed**: the pre-registration, the metrics and the hash first entered git in one commit, so ordering is documented by timestamps and the amendment log, not by an earlier commit |
| "0.00% anachronisms" (entity audit) vs 282 flagged claims | two different notions (register `valid_from` violations vs mapped division-era strings); reconciled in `DATA_QUALITY_REPORT.md` §B.4 |

The reviewer also confirmed the prohibitions passed (no claim treated co-authorship as collaboration or
knowledge transfer; no precision/recall; no prediction claim; 45/45 citations resolve) and that the
worksheet is genuinely stratified with human fields empty.

**What this correction does not change:** the verdict remains `NO-GO FOR PREDICTION` (T3/T4/T6 fail),
T5 now passes, and no threshold was altered — the two measurement-definition changes are recorded as
dated amendments with the old and new values side by side.
