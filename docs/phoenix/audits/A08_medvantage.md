# A08 — MedVantage

## Metadata

| Field | Value |
|---|---|
| Name | MedVantage (MedVantage MedTech Intel) |
| Official URL | https://medvantage.ai/ |
| Vendor | MedVantage (independent early-stage venture; contact emad.piracha@gmail.com; "Not affiliated with the U.S. FDA") |
| Product type | Pre-launch SaaS — searchable, source-linked profiles over public US FDA records + "Market Maps" + monitoring |
| Target customer | Emerging and mid-market device companies and RA consultants; secondary: BD/corp-dev/investors, quality & post-market teams |
| Licence / terms | No public ToS or price list found on the site. Early access is stated as free ("Pre-launch. No cost, no commitment"). Terms text **UNKNOWN**. |
| Access barrier | **Low-to-moderate.** Full marketing site is public and unusually specific. Product itself is **pre-launch** — "Request a sample platform view" form only; no login, no self-serve, no schema browser. |
| Evidence date | 2026-11-08 (Asia/Shanghai) |
| Overall confidence | **Medium-high for design intent**, **low for delivered behaviour** — the product does not yet exist in inspectable form. |

## 1) What it is and who buys it

MedVantage is a **pre-launch** platform that turns the US FDA record into searchable, source-linked profiles. Its own framing: "MedVantage makes the FDA record searchable." The unit of value is a *profile* — device, company, product code, or FDA submission — and the roll-up is a "Market Map" (Portfolio / Competitor / Market Entry) with monitoring on top.

Notably, it is **not** a medtech market-sizing product: there is no sales, share, pricing, or forecast claim anywhere. It is a regulatory-evidence product. That is a deliberate and honest positioning for a new entrant.

Purchasing: early access, free, no self-serve checkout. No pricing model is public.

## 2) Public evidence inventory

| # | URL | Quote (verbatim) | Confidence |
|---|---|---|---|
| E1 | https://medvantage.ai/ | "MedVantage makes the FDA record searchable. Open source-linked profiles for devices, companies, product codes, and FDA submissions" | VERIFIED |
| E2 | homepage | "Nine public FDA sources Devices · Companies · Product codes · Submissions Every point linked to its FDA filing" | VERIFIED |
| E3 | homepage | "Applicant, owner-operator, and brand names are reconciled into a single company — so subsidiaries and legal-entity variants of the same firm count as one." | CLAIMED_UNVERIFIED |
| E4 | homepage | "Predicate chains locked inside 510(k) summary PDFs are extracted and structured into a queryable lineage." | CLAIMED_UNVERIFIED |
| E5 | homepage | "Every point traces to a public FDA / openFDA record and links back to it — never third-party estimates standing in for the source." | VERIFIED (design statement) |
| E6 | homepage | "Where the exact FDA wording matters, you get the source text and a link to the original document — not a summary quietly standing in for the record." | VERIFIED (design statement) |
| E7 | homepage | "No black-box summaries" | VERIFIED (design statement) |
| E8 | homepage | "Nine systems · no joins: 510(k), PMA, De Novo, Classification, GUDID / UDI, Registration, Recalls, Adverse Events, Warning Letters" | VERIFIED |
| E9 | homepage | "Pre-launch · early access for design partners" ; "Pre-launch. No cost, no commitment" | VERIFIED |
| E10 | homepage | "Figures from **openFDA**"; "Company figures below are real, from openFDA. Interfaces are illustrative." | VERIFIED — note the honesty of labelling mock UI |
| E11 | homepage | Product-code profile: "the classification itself — class, regulation, review panel — plus who is cleared in it, how they got cleared, predicate families, clearance timelines, and post-market risk across the code" | VERIFIED |
| E12 | homepage | Example figures: Boston Scientific "863 × 510(k)"; WATCHMAN "P130013 · 82 records"; recalls "1,358 recall records on the FDA register"; code QEW "141 clearances", "Class II · 21 CFR 870.5150" | INFERRED (illustrative UI; the page itself says interfaces are illustrative) |

## 3) Data structure & standardisation principles

This is the most explicitly documented entity model of the seven. Four profile types are named (E1, E11):

- **Device** — device description, intended use and indications, IFU where publicly available, predicate devices, comparison and testing summaries, clearance/approval history, post-market signals.
- **Company** — every device and submission on the FDA record, product codes touched, registered establishments, recalls, warning letters, full regulatory history.
- **Product code** — class, regulation (21 CFR cite), review panel, who is cleared in it, how they got cleared, predicate families, clearance timelines, post-market risk.
- **FDA submission** — decision and dates, pathway, predicates cited, the summary document, link to the primary FDA record.

The **standardisation spine is the regulatory artefact** (submission / product code / registration), not a vendor market segmentation. Nine source systems are enumerated (E8), and the explicit joining problem — "Nine systems · no joins" — is stated as the product thesis.

Also noteworthy: the site openly distinguishes real figures from illustrative UI (E10). That is a rare and credible practice.

## 4) Company identity resolution

**The strongest public ER statement of the seven** (E3): "Applicant, owner-operator, and brand names are reconciled into a single company — so subsidiaries and legal-entity variants of the same firm count as one."

Three name spaces are named — *applicant*, *owner-operator*, *brand* — which maps closely to the real FDA problem. However:

- No accuracy figure, no merge/split audit trail, no confidence score, no manual-review workflow is described.
- No statement about **Chinese/English name pairs**, because the product is US-FDA-only.
- Pre-launch, so the claim is unimplementable to verify.

**Verdict: concept is VERIFIED as design intent; performance is CLAIMED_UNVERIFIED.**

## 5) Technology / product taxonomy

Taxonomy is **inherited from the regulator**, not invented: FDA product code + classification (class, 21 CFR regulation, review panel) per E11. Depth is therefore exactly as deep as the FDA classification database — typically product-code (3-letter) → regulation → class. It is **inspectable in principle** because the FDA classification DB is public, which is a real advantage over proprietary taxonomies.

No commercial market taxonomy (segment/赛道) is offered. No technology-generation axis.

## 6) Data provenance & evidence presentation

Best-in-class among the seven, on stated design:

- "Every point traces to a public FDA / openFDA record and links back to it" (E5).
- Source text shown verbatim rather than paraphrased (E6, E7).
- "No black-box summaries" (E7).
- The UI distinguishes real numbers from illustrative mock (E10).
- Predicate chains "extracted and structured into a queryable lineage" (E4) — an explicit provenance graph.

What is missing: **no point-in-time / as-of versioning is described.** FDA records change (supplements, reclassifications, ownership transfers); the site says it is "designed to update as new FDA records appear" but does not claim historical snapshotting. For a regulatory-evidence product this is the main provenance gap. Also no citation of *when* a record was last verified.

## 7) Competitor comparison features

Comparison is done through **Market Maps** with three named types:

- **Portfolio Map** — own footprint: devices & product codes, clearances/approvals, predicates, registration & listing, recalls, MAUDE, warning letters.
- **Competitor Map** — rival's devices, recent clearances, new entrants, predicate usage, product-code movement, recalls, MAUDE trends, warning letters, adjacent-category expansion.
- **Market Entry Map** — active companies, pathway mix, predicate options, clearance timelines, post-market signals, regulatory risk.

Dimensions compared are therefore **regulatory and safety**: pathway mix, predicate usage, clearance timeline, post-market signal. Not price, not share, not revenue. This is a coherent, defensible scope.

## 8) Technology-generation expression

**Absent.** There is no concept of product generation, iteration, or model lineage. The nearest constructs are "predicate devices" (a regulatory-lineage relation) and "clearance or approval history" (a chronological list).

This is a genuine gap MedRadar can exploit: predicate lineage is a *precursor* to technology generation but is not the same thing.

## 9) Historical technology activity display

"Clearance or approval history" and "full regulatory history" are claimed per entity (E11). "Clearance timelines" are an explicit comparison dimension. Monitoring surfaces "new activity" as it appears.

Coverage start date is **UNKNOWN**; no explicit backfill boundary is published. No timeline visualisation is described beyond history lists and "trends" (MAUDE trends).

## 10) Prediction capability: marketed vs validated

**Marketed: essentially none.** This is the notable finding. MedVantage makes **no forecasting, predictive, or "AI-powered prediction" claim** anywhere on its public site. The word "predict" does not appear as a capability. It promises search, traceability, roll-up, and *monitoring* ("surface new moves for you"), which is detection, not prediction.

**Validated: not applicable** — nothing to validate.

**Verdict:** MedVantage is the only one of the seven that **does not overclaim prediction**, and it is also the only one that openly labels its own UI mock as illustrative. That restraint is itself the most useful signal in this audit: a pre-launch entrant competing on *auditability* rather than on *forecasting*. Recorded as a positive control against which the other six's forecast claims can be judged.

## 11) What MedRadar can learn conceptually

1. **"Nine systems, no joins"** is the single best articulation of the integration thesis — the value is in the join, and the join is the moat.
2. **Four-profile entity model** (device / company / product code / submission) is a clean, minimal, regulator-anchored schema MedRadar can adopt conceptually and extend with NMPA.
3. **Verbatim source text + deep link instead of paraphrase** — the correct provenance contract.
4. **Openly labelling illustrative UI vs real figures** — a trust practice worth institutionalising.
5. **Predicate lineage as a queryable graph** — a genuinely novel structure that maps well onto "technology ancestry."
6. **Restraint from forecasting** — a positioning option, and proof that a medtech CI product can be sold on auditability alone.

## 12) What must NOT be copied

1. **"Nine sources" as a completeness claim** — nine US FDA systems is not global coverage; MedRadar must not imply global reach from a US-only base.
2. **Entity resolution asserted without auditability.** "Reconciled into a single company" with no merge log, no confidence, and no split path is exactly the unverifiable claim class this program exists to avoid. If MedRadar does ER, it must expose the evidence and allow correction.
3. **No as-of/point-in-time model.** Copying this would reproduce a known weakness.
4. **Pre-launch marketing as capability.** All product behaviour here is a promise; nothing is delivered.

## 13) Decision + reasoning

**Decision: STUDY_ONLY.**

Reasoning: ADOPT/ADAPT are impossible — there is no shipped product, no API, no data to obtain; access is a form. But the *design documentation* is the highest-value artefact in this set: the four-profile model, the explicit ER claim, the predicate-lineage graph, and the deliberate refusal to claim prediction. MedRadar should study the model and treat the ER claim as a design target it must then *validate*, not inherit.

## 14) Access log

All timestamps 2026-11-08, Asia/Shanghai (+08:00).

| Attempt | URL | Result |
|---|---|---|
| 1 | https://medvantage.ai/ (`web_fetch`) | **HTTP 200 — full page text obtained.** Single fetch sufficient; the entire site is a one-page marketing site. |

No further URLs were required or attempted. No forms were submitted (no account created, no sample requested). No login exists to bypass. Price list: none published. ToS: not linked from the page (only Contact/Request access), so licence terms remain UNKNOWN.
