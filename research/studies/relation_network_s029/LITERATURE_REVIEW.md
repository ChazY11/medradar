# S-029 Literature Review — Can observable, time-resolved relations among firms, institutions, studies, publications and regulators be reconstructed from public evidence?

**Study:** S-029 *Evidence-based relation reconstruction in medical technology* (project MedRadar)
**Branch:** `research/s029-evidence-based-relations`
**Reviewer:** `lit-reviewer` (independent literature verification)
**Verification window:** `2026-11-03T20:07:07Z` – `2026-11-03T20:08:41Z` (all retrieval timestamps per record are in the JSON; local time 2026-11-04, Asia/Shanghai)
**Corpus:** **45 works**, all verified by live API fetch. 32 at abstract level, 13 at title/record level, **0 full texts read**.
**Companion artifacts:**
`artifacts/literature_refs.json` (one provenance record per work), `artifacts/lit_abstracts.json` (abstract text as returned, with hash), `artifacts/lit_diagnostics.json` (why each candidate resolved or did not), `code/s029_lit_verify.py` (re-runnable verifier).
**Predecessor lesson applied:** S-028-CORRECTION-1 (`research/studies/graph_early_signal_s028/LITERATURE_CORRECTION_NOTE.md` in the main checkout `D:\DEPPSKK\medradar`) — a paper that existed was reported non-existent because a keyword search missed it, and six remembered DOIs were wrong. Both failure modes are mechanically blocked here (§1).

> **Reading rule.** Every bracketed id `[Rnn]` resolves to a record in `literature_refs.json`, which stores the DOI, the **exact title returned by the source**, all authors as returned, year, venue, verifying URL, retrieval UTC timestamp and a sha256 of the response body. `†` marks a work whose statement rests on the **record only** (no abstract was retrievable). No citation in this document was written from memory; §17 lists the corpus, §1 explains the method, §15 lists what the corpus forbids us to claim.

---

## §0 Executive summary

1. **The corpus.** 45 works in twelve groups: science of science (4), knowledge diffusion (5), university–industry (4), collaboration networks (5), temporal networks (1), translational lag (3), clinical research networks (4), technology transfer (3), entity resolution (5), temporal KGs and provenance (4), measurement error in scientific infrastructure (3), medical-device/FDA pathway (4).
2. **What the literature supplies.** Proxy designs with explicit critiques (citations as spillover, co-authorship as collaboration); small-*n* human-truth designs (interviews, hand-traced trajectories, manual record audits); source taxonomies for entities, time and provenance. That is the methodological vocabulary S-029 needs.
3. **What it does not supply.** We did **not find**, in this corpus, a study that *measures the reconstructability and provenance quality of a multi-source, dated company–institution–study–publication–regulatory relation set* for a defined firm set. All eleven works in the closest-work table (§13) solve a different question — typically one S-029 cannot answer at all (causal spillover, disambiguation accuracy, single-device ancestry, publication-bias estimation).
4. **Therefore S-029's defensible contribution is a measurement contribution, not an explanatory one:** an audited evidence base plus measured error rates for entity, relation and time, and a refusal to interpret co-activity as transfer. Any stronger claim would be unsupported by this corpus and by S-028's own negative results.
5. **Five most consequential gaps** (§14): (G1) legal-entity identity across corporate events; (G2) institution attribution from affiliation strings; (G3) what a public source actually asserts when it co-locates two entities; (G4) whether any source supports point-in-time ("as-of") reconstruction; (G6, G7) direction and causality of any flow.
6. **Verification:** 45/45 records fetched live (the verifying source is recorded per record: Crossref for 43, OpenAlex for 2), 45/45 OpenAlex cross-checks, 18/45 Europe PMC hits, 124 HTTP calls, 0 unresolved candidates; every hash validated by `--offline-check`; **nothing** in this document is quoted at a level above the record that was read.
7. **Scope exclusion.** The review deliberately contains **no graph-neural-network architecture literature**. S-029 does not build or benchmark a model; GNN papers would frame a study this round explicitly refuses to be.
8. **Read §15 before drafting any claim.** It pairs each prohibited sentence type with the work that makes it indefensible.

---

## §1 Verification method (exactly how every citation was checked)

### 1.1 The rule

A reference is citable only if `code/s029_lit_verify.py` fetched a live metadata record for it and stored the response. The candidate list in the script is **search intent**, not bibliographic fact: the string that ends up in this document is always the source's own string. Where a remembered DOI was supplied as a lookup shortcut (`doi_hint`, 17 of 45 records), it was **only a hint**: the fetched record still had to pass a title-similarity gate (Jaccard ≥ 0.50 or SequenceMatcher ≥ 0.80) **and** an author gate (the author hint must appear in the retrieved author list) before it could be used. A wrong hint is therefore rejected and falls back to a bibliographic search — it cannot smuggle a different paper in.

### 1.2 Pipeline (re-runnable, stdlib only)

1. **Resolve.** Crossref `query.bibliographic` (+ `query.author` where given), top 5 hits, ranked by title score with author/year bonuses; the first hit passing the gates wins. Two works that Crossref does not index were resolved through OpenAlex instead (R31, R40).
2. **Verify.** `GET https://api.crossref.org/works/{doi}` (polite pool, `mailto=medradar.research@proton.me`); the record is stored verbatim — title, author list (family, given, ORCID, affiliations where deposited), issued/published-print/published-online date parts, venue, publisher, type, ISSN, volume, issue, pages, record created/deposited dates.
3. **Cross-check.** Europe PMC `DOI:"…”` lookup (18/45 hits) and a batched OpenAlex `filter=doi:a|b|c` request covering all 45 works in two calls (25 and 20 DOIs). Disagreements and misses are **recorded as misses**, not smoothed away.
4. **Abstract capture.** Where a source returned an abstract it is stored with its own URL + sha256; 20 came from OpenAlex, 12 from Europe PMC. A cheap relevance screen compares title content-words with the abstract (§1.7).
5. **Coverage queries.** Six fixed searches (§1.8) whose *misses* are the only thing a "we did not find" sentence may rest on.
6. **Artifacts.** `literature_refs.json`, `lit_abstracts.json`, `lit_diagnostics.json`, all written by the same run; `--offline-check` re-validates the JSON without network (required fields, 64-hex hashes, ISO-8601-Z timestamps, HTTP 200 on the verifying fetch, no duplicate ids/DOIs, no unresolved entry marked citable, corpus size in 30–45, coverage queries present).

**Re-run:** `python research/studies/relation_network_s029/code/s029_lit_verify.py` then `... --offline-check`. Re-running re-fetches everything and rewrites the artifacts; the reference set and the stored field values are determined by the upstream records, so only `*_utc` timestamps (and genuine upstream edits) can differ between runs. `--discover "query"` runs one Crossref search and prints hits, for auditing a missing work.

### 1.3 What "verified" means here — and what it does not

| Level | Count | Meaning |
|---|---|---|
| Identity resolved against a fetched record | **45 / 45** | DOI + title + author list + year + venue came from the API, not from memory |
| Abstract available and stored | **32 / 45** | substantive statements may be made about what the work found |
| Record only (`†`) | **13 / 45** | only title/venue/authorship-level statements are allowed |
| Full text read | **0 / 45** | no method-level claim ("the paper does X") is made beyond what the abstract states |
| Cross-checked at OpenAlex | **45 / 45** | same DOI, title and year returned by a second index |
| Cross-checked at Europe PMC | **18 / 45** | biomedical coverage only; a miss means "not indexed there", not "not real" |
| Unresolved candidates | **0** | nothing was asserted from a failed lookup |

This table is the honest scope statement S-028 lacked: *verified* means **the record was fetched and its metadata checked**, not that the work's methods were read. Where a statement needs method detail that only full text could support, this review does not make it.

### 1.4 Sources, rate limits, call counts (this run)

| Source | Calls | Constraint enforced |
|---|---|---|
| Crossref | 75 | polite pool `mailto=medradar.research@proton.me`; 0.30 s between calls; 429 back-off + retry |
| Europe PMC | 45 | 0.60 s between calls (≤ ~1.7 req/s) |
| OpenAlex | **4** (2 single-work + 2 batches of 25 and 20 DOIs) | hard study cap of 25 requests; ≤25 DOIs per batched filter request; the run used 4 |

### 1.5 What may be quoted, and from where

A number may appear in this review only if (a) it is a sentence in a **stored abstract** (§18 registers each one with its URL), or (b) it was **computed by the verifier** and written into `literature_refs.json` (counts, rates, overlap scores). Title-level numbers (e.g. the phrase "17 years" in R20's title) are quoted as title text, not as a finding. Numerical claims about the *world* that appear in the literature are quoted as **what that work reported**, never as settled fact.

### 1.6 Coverage limits (stated, not hidden)

No Web of Science, Scopus, Google Scholar, CNKI, arXiv full-text search, or forward/backward citation chasing. The corpus is a **targeted** corpus of works chosen for the S-029 measurement problem, so it is biased toward well-known works. Consequences: (i) "we did not find X" statements are scoped to these 45 works and the recorded queries (§1.8); (ii) 13 works are citable only at record level; (iii) for a few works the retrieved "abstract" is a compressed summary (R15), a one-sentence summary (R21), a citation string (R18) or unrelated statutory text (R26) rather than the authors' abstract; `abstract_relevance` and `claim_scope` record this.

### 1.7 Anomalies the verifier actually caught (evidence that the method bites)

- **Crossref absence is not non-existence.** The ARIST chapter "Author name disambiguation" (R31) returns **404 at Crossref** but exists at OpenAlex with the printed DOI `10.1002/aris.2009.1440430113`. It is therefore verified through OpenAlex only, and marked as such (`resolver.stage = openalex_doi`). A reviewer who checked only Crossref would have wrongly dropped it.
- **Deposited titles can be wrong or truncated.** R33's Crossref title is just *"Entity resolution"* for the PVLDB tutorial *Entity Resolution: Theory, Practice & Open Challenges*; it was accepted only because DOI, author list (Getoor, Machanavajjhala) and year agreed (`metadata_notes` records this).
- **Deposited titles can carry markup.** R07's title arrives as `Superstar Extinction<sup>*</sup>`; the verbatim string is stored and a cleaned display form (`title_display`) is used for reading.
- **Abstract fields can be contaminated.** In R26 the text in the OpenAlex abstract field is **US statutory text about FDA user fees**, not the article's abstract; title-term overlap = 0.0 (stored in `abstract_relevance`). R18's "abstract" is a **bibliographic citation string**. Neither is quoted as content. This is a concrete instance of the infrastructure error R39/R04 describe — and it happened in the very tooling this study relies on.
- **Memory was wrong in ways the record corrected.** My candidate hints said the BMJ non-publication study was 2015 (record: **BMJ 2013;347:f6104**, R25) and the ClinicalTrials.gov final-rule paper was 2019 (record: **NEJM 2016;375:1998–2004**, R26); the measurement-error paper's deposited author list is **Wang, Shi, McFarland & Leskovec** (R39), not the list I would have written from recall; one author name was misspelled in my hint (*Smallheiser* → **Smalheiser**, R31). Each would have been a citation error under memory-only writing.

### 1.8 Negative claims: search-scoped, never absolute

Six coverage queries were run and stored with their top-10 hits and payload hashes:

| Label | Query | Hits returned |
|---|---|---|
| knowledge transfer direction from co-authorship | `co-authorship direction of knowledge flow inference` | 10 |
| bench to bedside lag measurement | `translational research lag measurement publication to practice` | 10 |
| clinical trial network co-participation knowledge | `clinical trial site network co-participation industry` | 10 |
| medical device regulatory pathway evidence | `medical device premarket approval clinical evidence outcomes` | 10 |
| temporal provenance knowledge graph construction | `temporal knowledge graph construction provenance evidence` | 10 |
| affiliation-based attribution error | `author affiliation disambiguation attribution error bibliometrics` | 10 |

All 45 resolution queries are stored under `search_queries_run`. Any statement of the form "no prior work does X" in this document is written as: **"we did not find X in our verified corpus of 45 works, located with the queries recorded in `literature_refs.json`"**. Chinese shorthand for the same rule, from the S-028 correction: **检索不到 ≠ 不存在** ("not found in a search" ≠ "does not exist").

### 1.9 How this connects to S-029's relation ontology

The corpus only matters if it constrains the study's own data model. `RELATION_ONTOLOGY.md` already stores **claims, not edges**: each `RelationClaim` carries a closed-list `predicate`, a `relation_role`, a `statement_status` (`SOURCE_STATES_IT` vs `SOURCE_IMPLIES_IT`), a `mapping_status` (`EXACT`/`ALIAS`/`FUZZY`/`AMBIGUOUS`/`UNMAPPED`/`REJECTED`) and up to four clocks. That schema is the operational form of three things this corpus insists on: the proxy critique (R05, R14, R15), the provenance distinction between what a source says and what a reader infers (R36, R41), and the clock distinction between event time and observation time (R19, R26). It is also why the prohibitions in §15 are enforceable rather than exhortative — a claim that a source merely *implies* can be filtered out, not argued about.

---

## §2 The measurement problem S-029 faces (three layers, no model)

S-029 asks whether relations among five medical-technology firms, research institutions, clinical studies, publications and regulatory activity can be **reconstructed as dated, sourced observations**. That question decomposes into three measurement layers, each with its own literature:

1. **Entity layer.** A relation is a relation *between identified things*. The entity-resolution literature (R30–R34) shows that name-string matching fails in both directions — one name many people, one person many names — and that reported accuracy depends on the truth set (R32). Institution-level resolution inherits all of this plus corporate events (merger, spin-off, rename), which no bibliographic source represents.
2. **Relation layer.** Public sources rarely assert "A transferred knowledge to B". They assert co-presence: the same paper, the same trial, the same affiliation string, the same funding statement. The diffusion literature treats such co-presence as a *proxy* and has repeatedly bounded what proxies can support (R05, R06, R08); the collaboration literature shows co-authorship is not collaboration (R14, R15).
3. **Time layer.** Reconstruction needs the date the relation existed *and* the date the statement became observable. These are two different clocks, and keeping them apart is S-029's own discipline (formalised as gap G5 in §14); the temporal-network review [R19] (`†`, record-level) is the general reference, the provenance literature gives the vocabulary (R36, R37, R41), and registry studies show a field's meaning can change with a reporting rule (R26).

S-029's contribution, on this reading, is to measure the error at each layer for a concrete firm set — not to add a fourth layer of inference (e.g. a predictive graph model). The rest of the review takes the layers in turn.

---

## §3 Science of science: what is measurable at all

Fortunato et al. [R01] frame the field as using "large-scale data on the production of science" to search for patterns, and explicitly for **policy design** — the framing already assumes the data describe the phenomenon. Clauset, Larremore & Sinatra [R02] sharpen the epistemics for prediction: the observable record is a partial, selected trace of the process, so predictive success does not license causal reading. This is the exact distinction S-028 violated and S-029 must keep: *describing a reconstructed relation is not explaining it*.

Two measurement-quality results matter more than any single finding. Martín-Martín et al. [R04] compare six citation sources and report that "Google Scholar found 88% of all citations", with the remainder distributed unevenly and coverage gaps by field; the same study counts `3,073,351` citations to `2,515` documents across `252` subject categories (§18). The disagreement is not noise at the edges — it is the size of the measurement error in the infrastructure itself. Hicks et al. [R03] (`†`, record only) is the normative reference against which such numbers are usually read; this review cites it only as the title-level statement on research metrics, not for any finding.

**Implication for S-029.** Any count computed from one database is a count *in that database*. Where S-029 reports a rate (e.g. share of claims with a resolvable identifier), the denominator and the source must travel with it, and the number must not be read as a property of the world.

---

## §4 Knowledge diffusion and spillover: the proxy tradition and its critics

The founding move is Jaffe, Trajtenberg & Henderson [R05]: compare the geography of patent citations with a **"control frequency"** reflecting pre-existing research concentration, and read the excess as localized spillover. The abstract reports domestic/state/SMSA excess, that "localization fades over time, but only very slowly", and — with unusual candour — that "there is no evidence that more 'basic' inventions diffuse more rapidly than others". The design is the ancestor of every "co-location implies relation" claim: *a citation is treated as a channel and the counterfactual is a matched frequency*. S-029 can borrow the **counterfactual discipline** (compare against what chance co-occurrence would produce) while refusing the inference from citation to transfer.

Keller [R06] reviews international diffusion and concludes that "there is no indication that international diffusion is inevitable or automatic, but rather, domestic technology investments are necessary". Diffusion is conditional and slow; co-presence of an idea in two places is compatible with no flow at all.

Azoulay, Graff Zivin & Wang [R07] is the rare design that identifies a tie-mediated effect: `112` academic "superstars" who died prematurely, and a "lasting 5% to 8% decline in … quality-adjusted publication rates" among collaborators. It demonstrates the *cost* of a credible knowledge-flow estimate — an exogenous shock plus a long panel — and therefore what S-029 simply cannot claim from co-activity. Narin, Hamilton & Olivastro [R08] (`†`, record only) reports an increasing linkage between U.S. technology and public science — the title-level statement only; no abstract was retrievable, so nothing is claimed about its indicator construction. van Wijk, Jansen & Lyles [R09] meta-analyse organisational knowledge transfer and show how much of that literature rests on perceptual or proxy measures — a warning that the construct is often measured by asking, or by counting.

**Implication for S-029.** Citations and co-affiliations are *evidence that two entities are bibliographically connected*, not evidence that anything moved. The project's one-line rule: **统计共现不是知识转移** ("statistical co-occurrence is not knowledge transfer").

---

## §5 University–industry relations: channels, not edges

Perkmann et al. [R10] review university–industry relations and separate **academic engagement** (collaborative research, contract research, consulting, informal contact) from **commercialisation** (IP, entrepreneurship). The separation matters because the two are measured by different traces: engagement often leaves no bibliographic record, while commercialisation leaves licences and patents. Cohen, Nelson & Walsh [R11], using the Carnegie Mellon survey of industrial R&D, find public research "critical … in a small number of industries" and important across much of manufacturing, and — critically for S-029 — that public research "both suggests new R&D projects and contributes to the completion of existing projects": the channel is not a citation. Bekkers & Bodas Freitas [R12] (†) enumerate transfer channels and show channel choice is sector-dependent. Mansfield [R13] (`†`, record-only) is cited as the survey-based companion on academic research and industrial innovation; no estimate from it is quoted, because no abstract was retrievable and this review does not read estimates out of titles.

**Implication.** "Firm and university co-occur" admits at least four readings (joint work, shared funder, shared facility, subcontracted analysis) and the literature does not let us pick one from bibliographic data. S-029 must therefore record **which channel the source asserts** (funding statement? co-authorship? trial sponsor-collaborator field?) and treat the rest as unknown.

---

## §6 Collaboration networks: construction and the co-authorship critique

Katz & Martin [R14] (`†`, record only) pose the definitional question — *what is research collaboration?* — and the field's operational answer has been co-authorship ever since. Newman [R16] [R17] shows how the network is actually built ("two scientists are considered connected if they have coauthored one or more papers together") and what statistics follow; the construction is simple, which is precisely why the semantic gap is easy to forget. Powell, Koput & Smith-Doerr [R18] shift the unit to organisations: interorganizational collaboration as the locus of innovation in biotechnology (title/record level; the retrieved "abstract" is a citation string).

Laudel [R15] is the human-truth check the network literature needed: interviews plus coding of contributions and acknowledgements identify **six types** of collaboration, show that "about half of the collaborations are invisible in formal communication channels because they are not rewarded", and that "about one third … are rewarded only by acknowledgements" (§18). In other words, the co-authorship graph systematically misses collaborations and systematically includes non-collaborations.

**Implication.** For S-029, a co-authorship edge is a **co-authorship relation**, full stop. It becomes a collaboration relation only with an additional, separately sourced warrant — which S-029 mostly will not have.

---

## §7 Time: temporal networks, temporal knowledge graphs, provenance

Holme & Saramäki [R19] (`†`, record only) is the standard review of temporal networks; S-029's own protocol defines its clocks operationally, and this review does not attribute specific claims to R19 beyond its title. What the research question needs is stated independently of any citation: a dated relation must carry (i) when it held and (ii) when it became observable, because the two are not the same field.

EventKG [R35] is the closest *construction* precedent: an event-centric temporal knowledge graph in which events and temporal relations are represented explicitly, reporting "over 690 thousand contemporary and historical events and over 2.3 million temporal relations" (§18). The transferable part is the construction choice — events are the objects that carry temporal scopes — not a data model to copy. The provenance literature supplies the vocabulary for what S-029 must record: Cheney, Chiticariu & Tan [R36] distinguish **why / how / where** provenance; Herschel, Diestelkämper & Ben Lahmar [R37] (`†`, record only) is cited as the entry point to the workflow-provenance literature, not for a specific taxonomy; Buneman, Khanna & Tan [R41] (`†`) carries the why/where distinction in its title — "which source said it" versus "which derivation produced it" is the part S-029 needs. Wilkinson et al. [R38] set the reuse standard (FAIR), which S-029's artifacts should meet rather than merely cite.

**Implication.** S-029 should not report a "confidence" score. It should report, per relation: the source, the exact field, the retrieval time, the asserted time, the resolution steps, and what is unknown. That is a provenance record, not a probability.

---

## §8 Entities and the error structure of the scholarly infrastructure

Ferreira, Gonçalves & Laender [R30] state the problem: name ambiguity "affects the quality of services and content in digital libraries", and methods either group records by similarity or assign them to authors. Smalheiser & Torvik [R31] (†, verified at OpenAlex only — Crossref has no record) review disambiguation evidence and error sources. Tekles & Bornmann [R32] compare unsupervised approaches under controlled conditions against a **manually curated gold standard** and find the ranking depends on that truth set — a direct statement that "accuracy" is relative to human adjudication. Getoor & Machanavajjhala [R33] give the general ER frame (blocking, matching, clustering, open challenges). Peroni et al. [R34] show that citation links themselves can be published as first-class open data (`204,637` articles, `6,325,178` references, `3,373,961` unique papers, §18) — i.e. a link's provenance can be an object in its own right.

On the infrastructure side, Wang, Shi, McFarland & Leskovec [R39] (`†`, record only) is the reference on measurement error in network data; S-029's audits use a node / edge / timing decomposition as an organising checklist, which is our reading of that work's scope rather than a verified quotation. Priem, Piwowar & Orr [R40] report OpenAlex's own coverage in its own words: "209M works", "2013M disambiguated authors", "124k venues", "109k institutions", "65k Wikidata concepts" — self-reported coverage claims, which the paper itself says will improve. Martín-Martín et al. [R04] show what happens when coverage claims meet measurement.

**Implication.** Entity resolution is not a preprocessing step whose errors can be assumed away. It is a measured quantity with a source and a direction of bias (large, well-indexed organisations are resolved more often than small ones), and S-029 should report it per entity and per claim type.

---

## §9 Translational lag: the number everyone quotes and the paper that warns against quoting it

Morris, Wooding & Grant [R20] review the literature that *quantifies* time lags in health-research translation, include `23` papers, and conclude: "Few were comparable as different studies use different measures, of different things, at different time points", and "the current state of knowledge of time lags is of limited use". The title's "17 years" is a question, not an estimate — the paper's own abstract does not report a 17-year figure (§18 records only the title-level occurrence). Contopoulos-Ioannidis et al. [R21] trace intervention life cycles from discovery to highly cited article; the retrieved abstract is a single sentence, so the review treats the method as title-level ("life cycle … translational research"). Macleod et al. [R22] (`†`, record only) is titled "Biomedical research: increasing value, reducing waste"; S-029's reading — that non-arrival should be treated as a measurable outcome rather than a missing value — is a design choice of this study, not a finding of R22.

**Implication.** S-029 must not import a lag constant. If it reports a lag, the lag must be computed on its own data with its own clock definitions and its own censoring rules — and the literature says those definitions will determine the answer.

---

## §10 Clinical research networks and trial registries

Zarin et al. [R23] describe the registry-as-database: as of 27 Sep 2010, `79,413` registry and `2,178` results records, with `20%` of results records reporting more than two primary outcomes, `61%` of sampled registry outcome measures lacking specificity, and `52%` (78/150) of sampled results records having an associated publication within two years. Ross et al. [R24] measure registration completeness and selective publication on `7,515` completed trials: mandatory fields near 100%, optional fields `53%`–`87%`, and only `46%` of a 10% subsample published. Jones et al. [R25] estimate that of `585` large prospectively registered trials, `171` (**29%**) remained unpublished, with `299,763` participants in those trials. Zarin et al. [R26] is the record of the final reporting rule (NEJM, 2016); its abstract field is contaminated (§1.7), so it is used only as a dated record that the rule exists, not for any claim about what the rule says.

**Implication.** Three distinct relations hide under "trial ↔ publication": (a) the trial record asserts a publication (a citation field), (b) a publication exists and mentions the trial, (c) neither. The literature's manual search protocols (R24) are the human-truth design S-029 cannot afford at scale; S-029 can, however, measure how often each relation is *reconstructable* from public fields, and must treat "no publication found" as **unknown**, not as a negative relation.

Also relevant: the corpus contains **no** study of the *topology* of clinical-research collaboration networks (who co-participates with whom across sites and sponsors) located by our coverage query "clinical trial site network co-participation industry" — see §1.8 and §16. That is a search-scoped absence, not a claim about the field.

---

## §11 Technology transfer

Mowery, Nelson, Sampat & Ziedonis [R27] (†) assess university patenting and licensing growth after Bayh–Dole; Henderson et al.'s earlier analysis is not in this corpus. Thursby & Thursby [R28] model licensing as a three-stage process and, using survey data from `64` universities, attribute licensing growth "primarily to an increased willingness of faculty and administrators to license and increased business reliance on external R&D rather than a shift in faculty research". Salter & Martin [R29] (†) critically review the evidence for economic benefits of publicly funded basic research.

**Implication.** Technology transfer is measured by **administrative events** (licence, patent assignment, spin-out), not by bibliographic proximity. Where S-029 has no administrative record, it has no transfer relation — only a co-presence relation.

---

## §12 Medical devices and the FDA pathway: the closest domain comparator

This is the domain S-029 works in, and the literature is blunt about what public regulatory records can support.

Zuckerman, Brown & Nissen [R42] analyse the FDA's high-risk recall list 2005–2009: `113` recalls the FDA judged could cause serious harm or death; `21` (**19%**) via PMA, `80` (**71%**) via 510(k), `8` (**7%**) exempt — i.e. "78%" of high-risk recalls came through the less stringent route or none. Ardaugh, Graves & Redberg [R43] trace the predicate ancestry of one metal-on-metal hip implant and find it "includes 95 different devices" — a hand-built regulatory-ancestry graph, the closest thing in this corpus to the relation S-029 wants to reconstruct. Kramer, Xu & Kesselheim [R44] contrast the US and EU pathways. Dhruva [R45] audits the evidence behind `78` cardiovascular PMAs (`123` supporting studies): `27%` of studies randomized, `14%` blinded, `65%` of PMAs based on a single study.

**Implication.** The device literature supplies (i) a **pathway taxonomy** to type regulatory relations (510(k) / PMA / De Novo / exempt), (ii) proof that **predicate ancestry is reconstructable** — by hand, for one device — and (iii) the ceiling: an approval is not evidence of benefit, so a "study supports device" relation must not be read as "device works". S-029's question is the missing general case: whether such ancestry and support relations can be reconstructed *with provenance, at scale, for a firm set* — and how much of them is actually observable.

---

## §13 Closest-work comparison table

Strict classification: **all eleven works below solve a question S-029 does not attempt.** S-029 does not estimate spillovers, adjudicate disambiguation accuracy, trace a device's ancestry by hand, or estimate publication bias. What it can add is confined to the last column and is deliberately small.

| # | Work | What problem it actually solved | Data used | How relations are defined | Temporal validation method | Human-truth design | Scientific conclusion (as recorded) | Limitations | What S-029 could add that is genuinely new |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Jaffe, Trajtenberg & Henderson (1993) [R05] | Did knowledge spillovers leave a geographic trace in patent citations? | US patent citations + a "control frequency" of pre-existing research concentration | citing patent → cited patent (citation tie); geography of the pair | compares citation geography with control frequency; finds localization "fades … very slowly" | matched control frequency (an empirical null, not human adjudication) | domestic/state/SMSA citations exceed the control frequency; strongest at SMSA level | citation is a proxy; no direction, content or actor verification | **SOLVES SOMETHING ELSE.** S-029 borrows only the null-comparison discipline for its false-positive audit. |
| 2 | Azoulay, Graff Zivin & Wang (2010) [R07] | Magnitude of spillovers from star scientists to their collaborators | `112` premature, unexpected deaths + collaborators' publication records | co-authorship tie; death as exogenous shock to the tie | event-time panel around the death ("lasting" decline) | death records — an exogenous, verifiable event | `5%`–`8%` lasting decline in quality-adjusted publication rate | identifies an effect of tie loss, not of knowledge content; single field | **SOLVES SOMETHING ELSE (causal).** S-029 has no exogenous shock and must not simulate one. |
| 3 | Katz & Martin (1997) [R14] † | Poses the definitional question "what is research collaboration?" (title-level record) | conceptual piece (record-level) | this review's reading: it challenges using co-authorship as the operational definition | none claimed | none | not asserted here — no abstract was retrieved, so no conclusion is attributed to it | no empirical test claimed | **SOLVES SOMETHING ELSE (conceptual).** S-029 adopts the naming discipline: every edge is labelled with the relation the source asserts. |
| 4 | Laudel (2002) [R15] | What does co-authorship actually measure? | interviews with scientists + coding of contributions and acknowledgements | six collaboration types vs authorship/acknowledgement | none | interviews (human ground truth) | ~half of collaborations invisible in formal channels; ~one third recognised only by acknowledgements | small qualitative sample, single national context | **SOLVES SOMETHING ELSE.** S-029 cannot interview; it can only report which channel the source encodes. |
| 5 | Contopoulos-Ioannidis et al. (2008) [R21] | The life cycle from discovery of an intervention to a highly cited article | hand-traced publication trajectories for medical interventions | discovery → publication → citation chain | durations between stages | manual tracing of each trajectory | the road is long and citation is not the end of it (abstract is a single sentence) | few interventions; bibliographic chain only | **SOLVES SOMETHING ELSE.** Same object (time-resolved chain) at a scale and cost S-029 cannot match. |
| 6 | Zarin et al. (2011) [R23] | Is the ClinicalTrials.gov results database usable as a research object? | registry data Sep 2009–Sep 2010 | trial → results record | single snapshot; no historical as-of | sampled record audit (150 results records) | `79,413` registry + `2,178` results records; `20%` >2 primary outcomes; `61%` of outcome measures non-specific; `52%` with a publication within 2 years | fields self-reported; current-state only | **SOLVES SOMETHING ELSE (registry quality).** Only the data source overlaps; S-029 adds field-level provenance grading per claim. |
| 7 | Ross et al. (2009) [R24] | Completeness of registration and selective publication | `7,515` completed trials; 10% subsample searched in MEDLINE | trial → publication (link by systematic search) | ≥2-year publication window built into the design | manual/systematic MEDLINE search protocol | `46%` published; industry-sponsored less likely (`40%` vs `56%`) | search-based linkage; incomplete optional fields | **SOLVES SOMETHING ELSE (publication bias).** Only the relation type overlaps; S-029 grades the provenance of each trial→publication link instead of a binary published/unpublished. |
| 8 | Zuckerman, Brown & Nissen (2011) [R42] | Were recalled high-risk devices cleared through the less stringent pathway? | FDA high-risk recall list 2005–2009 + approval records | device → approval pathway (PMA / 510(k) / exempt) | recall after approval (implicit ordering) | FDA administrative records (recall class + approval route) | `71%` of `113` high-risk recalls 510(k)-cleared, `7%` exempt (`78%` less stringent or none) | no exposure denominator; recall ≠ harm rate | **CLOSEST DOMAIN COMPARATOR.** S-029 asks whether the pathway relation itself is reconstructable with provenance, not whether it predicts recalls. |
| 9 | Ardaugh, Graves & Redberg (2013) [R43] | The predicate ancestry of one problematic hip implant | FDA 510(k) records | device → predicate device (ancestry edge) | clearance dates | hand tracing of `95` devices | ancestry includes `95` different devices | single case; no systematic graph | **CLOSEST CONSTRUCTION PRECEDENT.** S-029 generalises hand-built ancestry into a measured entity-resolution + provenance problem. |
| 10 | Dhruva (2009) [R45] | Strength of evidence behind PMA of cardiovascular devices | `78` PMA summaries; `123` supporting studies | approval → supporting study | approval years 2000–2007; no follow-up | manual review of summary documents | `27%` randomized, `14%` blinded, `65%` based on a single study | summaries not full data; one device area | **SOLVES SOMETHING ELSE.** Sets the ceiling: a "supporting study" relation is not evidence of benefit, which S-029 must state in every claim. |
| 11 | Tekles & Bornmann (2020) [R32] | Compare unsupervised author-name disambiguation under controlled conditions | benchmark author mentions + manually curated gold standard | author mention → author identity | none | manual gold standard | the best approach depends on the truth set; Caron & van Eck (2014) performed best here | person names only, not institutions | **SOLVES SOMETHING ELSE (method-adjacent).** S-029 inherits the gold-standard logic for institution/company resolution, at a coarser entity type. |

**Reading of the table.** Most rows describe a *result about the world* (spillovers exist, collaboration is under-counted, publication is selective, recalls concentrate in 510(k)); S-029 produces a *result about the evidence* (what fraction of the relations can be observed, dated and attributed, and how wrong the obvious reconstruction is). Those are different products. Anyone reading S-029 as a weak version of rows 1–2 or 8–10 has misread it; anyone reading the corpus as having already done S-029's job is wrong, because no row measures provenance across heterogeneous sources for a firm set.

*Cell provenance:* cells for rows 1, 2, 4, 5, 6, 7, 8, 9, 10, 11 restate the stored abstract; row 3 (R14) restates the title only (`†`). "Limitations" is this review's judgement in every row, not a quotation.

---

## §14 Unsolved gaps, stated as testable questions

Each gap is written so that a negative result is informative. "S-029" states whether this round measures it, and why not where it cannot.

**G1. Entity identity across corporate events.** *Testable:* for each of the five firms, is there a dated chain of legal entities (parent, operating subsidiary, former owner, brand) such that every relation can be projected onto the entity that existed at the relation's date? *S-029:* **MEASURES** — via the historical entity register and the claim-to-entity mapping audit (rates of exact/alias/fuzzy/conflict/unmapped, and anachronism cases).

**G2. Institution attribution from affiliation strings.** *Testable:* given an affiliation string as printed, what is the probability it resolves to the intended institution, and does the error differ by institution size/type? *S-029:* **MEASURES** at claim level (resolution-outcome rates), but **cannot** estimate the population error without an external gold standard.

**G3. What a source actually asserts.** *Testable:* for each reconstructed relation, can the source text be quoted to the effect "A collaborated with B" rather than merely "A and B appear together"? *S-029:* **MEASURES** by classifying the asserted relation type per claim; **cannot** verify the underlying real-world collaboration.

**G4. Point-in-time ("as-of") reconstruction.** *Testable:* for each source, does a query return the record as it stood at date *t*, or only the current state? If only current, how many relation attributes are revision-sensitive? *S-029:* **MEASURES** (clock audit: which date fields exist, their precision, and whether historical retrieval is possible); **cannot** obtain a genuine as-of snapshot for sources that are current-state only.

**G5. Clock semantics.** *Testable:* are `published_at`, `event_at`, `valid_from` and `first_seen_at` distinct and populated per claim, and what is the distribution of contradictions (`published_at` before `event_at`, entity `valid_from` after relation date)? *S-029:* **MEASURES** (completeness and contradiction rates).

**G6. Direction of flow.** *Testable:* does any public field indicate who learned from whom? *S-029:* **CANNOT** — no source in this corpus asserts direction; this needs an exogenous design (cf. R07) or internal documents.

**G7. Whether co-activity implies transfer.** *Testable:* does observed co-activity predict later independent activity beyond a matched-frequency null? *S-029:* **CANNOT** this round — prediction is explicitly out of scope, and the corpus says the causal question needs a shock, not a correlation (R07, R06).

**G8. Completeness (the denominator).** *Testable:* what fraction of true relations are observed? *S-029:* **CANNOT** without a known-complete register; it can only report observed counts and their source.

**G9. Human adjudication agreement.** *Testable:* do two independent human annotators agree on whether a claim asserts a relation, and at what κ? *S-029:* **CANNOT** — no human labelling was performed this round (the study's own pre-registered condition T6, `GO_NO_GO_CRITERIA.md`, is expected to fail for exactly this reason); the study can still specify the worksheet and sampling frame for a later round.

**G10. Revision stability.** *Testable:* how much does a relation change between two observations of the same source? *S-029:* **PARTIALLY** — only where the precursor observation ledger carries a genuine first-seen timestamp; otherwise not measurable.

---

## §15 What this study must not claim (each prohibition tied to the literature)

| # | Prohibited sentence type | Why the literature forbids it | Cite |
|---|---|---|---|
| 1 | "A and B co-authored, therefore they collaborate / shared knowledge." | Co-authorship measures one narrow form; about half of collaborations are invisible in formal channels and about a third of collaborations are acknowledged only. | R14, R15, R17 |
| 2 | "The affiliation string matches firm X, therefore the work is attributable to X." | Name-string matching fails in both directions; reported accuracy depends on the truth set; institution-level matching inherits all of it. | R30, R31, R32, R33 |
| 3 | "They appear in the same trial / share a sponsor, therefore knowledge was transferred." | Co-presence is not a channel; organisational transfer is measured by administrative or survey evidence, and diffusion is not automatic. | R06, R09, R11, R23 |
| 4 | "Citations show that knowledge flowed from A to B." | Citation is a proxy whose counterfactual requires a matched frequency; the founding study itself reports anomalies (no faster diffusion of basic inventions) and the review literature calls diffusion conditional. | R05, R06, R08 |
| 5 | "The trial is registered, therefore it exists / was conducted; no publication, therefore no study." | Registration completeness and optional-field reporting vary; `29%` of large registered trials remained unpublished and `46%` of a subsample were published at all. | R24, R25, R26 |
| 6 | "The device was cleared/approved, therefore it is effective." | Most high-risk recalls came through the less stringent route; PMA evidence is often single-study, `27%` randomized, `14%` blinded. | R42, R43, R45 |
| 7 | "Translation takes 17 years." | The paper that owns the phrase reviews `23` incomparable studies and concludes the state of knowledge is "of limited use"; its abstract reports no 17-year estimate. | R20, R21, R22 |
| 8 | "No prior work has done X" / "this paper does not exist." | Source coverage differs enormously (Google Scholar found `88%` of citations; the rest split unevenly), so a miss in one index is expected. S-028 made exactly this error. | R04, R40 + S-028-CORRECTION-1 |
| 9 | "The record has a date field, therefore we know what was known in 2012." | A record's retrieval time is not its event time (the distinction S-029 formalises as G5); provenance distinguishes source from derivation; registry field meanings change with reporting rules. | R26, R36, R37 |
| 10 | "An edge in the graph is a channel / a transfer route." | Ties are proxies whose semantics differ by construction (citation, co-authorship, alliance, co-presence); deleting or adding an edge changes the meaning of the null model. | R05, R07, R14, R18 |
| 11 | "Our count of X is the true count of X." | Measurement error in network data has structure, and infrastructure coverage is itself measured, not given. | R39, R04, R40 |

---

## §16 Unverified / not asserted

- **No work in this review is asserted from memory.** Every one of the 45 has a fetched record; none is in a "believed but unverified" state.
- **R31 was not verifiable at Crossref** (404 for `10.1002/aris.2009.1440430113`). It is verified at OpenAlex and marked accordingly. If a reader requires Crossref-only verification, R31 should be treated as unverified — its claim is used only at review level.
- **Two "abstracts" are not abstracts of the work** (R18 = a bibliographic citation string; R26 = US fee legislation) and one is a one-sentence summary (R21) and one a compressed summary (R15). They are not quoted as content; `abstract_relevance` records this.
- **A further set of candidates was verified in an earlier pass and then dropped for scope**, because they duplicated a retained work's function: science-of-science items that repeated R01–R04's role, and channel/innovation items that repeated R10–R13 or R27–R29. They were dropped for redundancy, **not** because they could not be verified. Dropping them is not evidence about them; the final artifacts contain only the 45, and `lit_diagnostics.json` is overwritten on every run, so the earlier pass's log is not retained. Any of them can be re-resolved with `s029_lit_verify.py --discover "<title>"`.
- **We did not find** a study of clinical-research collaboration-network topology (see §1.8 coverage query), a study that measures provenance quality of a multi-source dated relation set for a firm set, or a device study that reconstructs regulatory ancestry systematically (R43 is a single case). These are **search-scoped absences** in a 45-work corpus, not claims about the literature as a whole.

---

## §17 Corpus manifest (45 verified works)

Format: **[id]** first author `et al.` (year). *title (display form; verbatim record in JSON)*. venue. DOI. Scope: `A` = abstract stored, `†` = record only.

**Science of science (4)**
1. **[R01]** Fortunato et al. (2018). *Science of science*. Science 359. `10.1126/science.aao0185`. A
2. **[R02]** Clauset et al. (2017). *Data-driven predictions in the science of science*. Science 355:477–480. `10.1126/science.aal4217`. A
3. **[R03]** Hicks et al. (2015). *Bibliometrics: The Leiden Manifesto for research metrics*. Nature 520:429–431. `10.1038/520429a`. †
4. **[R04]** Martín-Martín et al. (2020). *Google Scholar, Microsoft Academic, Scopus, Dimensions, Web of Science, and OpenCitations COCI: a multidisciplinary comparison of coverage via citations*. Scientometrics 126:871–906. `10.1007/s11192-020-03690-4`. A

**Knowledge diffusion / spillover (5)**
5. **[R05]** Jaffe, Trajtenberg & Henderson (1993). *Geographic Localization of Knowledge Spillovers as Evidenced by Patent Citations*. The Quarterly Journal of Economics 108:577–598. `10.2307/2118401`. A
6. **[R06]** Keller (2004). *International Technology Diffusion*. Journal of Economic Literature 42:752–782. `10.1257/0022051042177685`. A
7. **[R07]** Azoulay, Zivin & Wang (2010). *Superstar Extinction*. Quarterly Journal of Economics 125:549–589. `10.1162/qjec.2010.125.2.549`. A
8. **[R08]** Narin, Hamilton & Olivastro (1997). *The increasing linkage between U.S. technology and public science*. Research Policy 26:317–330. `10.1016/s0048-7333(97)00013-9`. †
9. **[R09]** Van Wijk, Jansen & Lyles (2008). *Inter- and Intra-Organizational Knowledge Transfer: A Meta-Analytic Review…*. Journal of Management Studies 45:830–853. `10.1111/j.1467-6486.2008.00771.x`. A

**University–industry (4)**
10. **[R10]** Perkmann et al. (2013). *Academic engagement and commercialisation…*. Research Policy 42:423–442. `10.1016/j.respol.2012.09.007`. A
11. **[R11]** Cohen, Nelson & Walsh (2002). *Links and Impacts: The Influence of Public Research on Industrial R&D*. Management Science 48:1–23. `10.1287/mnsc.48.1.1.14273`. A
12. **[R12]** Bekkers & Bodas Freitas (2008). *Analysing knowledge transfer channels between universities and industry…*. Research Policy 37:1837–1853. `10.1016/j.respol.2008.07.007`. †
13. **[R13]** Mansfield (1991). *Academic research and industrial innovation*. Research Policy 20:1–12. `10.1016/0048-7333(91)90080-a`. †

**Collaboration networks (5)**
14. **[R14]** Katz & Martin (1997). *What is research collaboration?*. Research Policy 26:1–18. `10.1016/s0048-7333(96)00917-1`. †
15. **[R15]** Laudel (2002). *What do we measure by co-authorships?*. Research Evaluation 11:3–15. `10.3152/147154402781776961`. A
16. **[R16]** Newman (2001). *Scientific collaboration networks. I. Network construction and fundamental results*. Physical Review E 64:016131. `10.1103/physreve.64.016131`. A
17. **[R17]** Newman (2004). *Coauthorship networks and patterns of scientific collaboration*. PNAS 101:5200–5205. `10.1073/pnas.0307545100`. A
18. **[R18]** Powell, Koput & Smith-Doerr (1996). *Interorganizational Collaboration and the Locus of Innovation…*. Administrative Science Quarterly 41:116. `10.2307/2393988`. A

**Temporal networks (1)**
19. **[R19]** Holme & Saramäki (2012). *Temporal networks*. Physics Reports 519:97–125. `10.1016/j.physrep.2012.03.001`. †

**Translational lag (3)**
20. **[R20]** Morris, Wooding & Grant (2011). *The answer is 17 years, what is the question…*. Journal of the Royal Society of Medicine 104:510–520. `10.1258/jrsm.2011.110180`. A
21. **[R21]** Contopoulos-Ioannidis et al. (2008). *Life Cycle of Translational Research for Medical Interventions*. Science 321:1298–1299. `10.1126/science.1160622`. A (one-sentence abstract)
22. **[R22]** Macleod et al. (2014). *Biomedical research: increasing value, reducing waste*. The Lancet 383:101–104. `10.1016/s0140-6736(13)62329-6`. †

**Clinical research networks / registries (4)**
23. **[R23]** Zarin et al. (2011). *The ClinicalTrials.gov Results Database — Update and Key Issues*. NEJM 364:852–860. `10.1056/nejmsa1012065`. A
24. **[R24]** Ross et al. (2009). *Trial Publication after Registration in ClinicalTrials.Gov…*. PLoS Medicine 6:e1000144. `10.1371/journal.pmed.1000144`. A
25. **[R25]** Jones et al. (2013). *Non-publication of large randomized clinical trials…*. BMJ 347:f6104. `10.1136/bmj.f6104`. A
26. **[R26]** Zarin et al. (2016). *Trial Reporting in ClinicalTrials.gov — The Final Rule*. NEJM 375:1998–2004. `10.1056/nejmsr1611785`. A (abstract field contaminated, §1.7)

**Technology transfer (3)**
27. **[R27]** Mowery et al. (2001). *The growth of patenting and licensing by U.S. universities…*. Research Policy 30:99–119. `10.1016/s0048-7333(99)00100-6`. †
28. **[R28]** Thursby & Thursby (2002). *Who Is Selling the Ivory Tower?…*. Management Science 48:90–104. `10.1287/mnsc.48.1.90.14271`. A
29. **[R29]** Salter & Martin (2001). *The economic benefits of publicly funded basic research…*. Research Policy 30:509–532. `10.1016/s0048-7333(00)00091-3`. †

**Entity resolution / disambiguation (5)**
30. **[R30]** Ferreira, Gonçalves & Laender (2012). *A brief survey of automatic methods for author name disambiguation*. ACM SIGMOD Record 41:15–26. `10.1145/2350036.2350040`. A
31. **[R31]** Smalheiser & Torvik (2009). *Author name disambiguation*. Annual Review of Information Science and Technology 43:1. `10.1002/aris.2009.1440430113`. † (OpenAlex only; Crossref 404)
32. **[R32]** Tekles & Bornmann (2020). *Author name disambiguation of bibliometric data…*. Quantitative Science Studies 1:1510–1528. `10.1162/qss_a_00081`. A
33. **[R33]** Getoor & Machanavajjhala (2012). *Entity resolution* (deposited title; full title truncated by the publisher deposit). PVLDB 5:2018–2019. `10.14778/2367502.2367564`. A
34. **[R34]** Peroni et al. (2015). *Setting our bibliographic references free…*. Journal of Documentation 71:253–277. `10.1108/jd-12-2013-0166`. A

**Temporal knowledge graphs and provenance (4)**
35. **[R35]** Gottschalk & Demidova (2018). *EventKG: A Multilingual Event-Centric Temporal Knowledge Graph*. LNCS (ESWC). `10.1007/978-3-319-93417-4_18`. A
36. **[R36]** Cheney, Chiticariu & Tan (2009). *Provenance in Databases: Why, How, and Where*. Foundations and Trends in Databases 1:379–474. `10.1561/1900000006`. A
37. **[R37]** Herschel, Diestelkämper & Ben Lahmar (2017). *A survey on provenance: What for? What form? What from?*. The VLDB Journal 26:881–906. `10.1007/s00778-017-0486-1`. †
38. **[R38]** Wilkinson et al. (2016). *The FAIR Guiding Principles…*. Scientific Data 3:160018. `10.1038/sdata.2016.18`. A

**Measurement error / infrastructure quality (3)**
39. **[R39]** Wang, Shi, McFarland & Leskovec (2012). *Measurement error in network data: A re-classification*. Social Networks 34:396–409. `10.1016/j.socnet.2012.01.003`. †
40. **[R40]** Priem, Piwowar & Orr (2022). *OpenAlex: A fully-open index of scholarly works, authors, venues, institutions, and concepts*. arXiv (Cornell University). `10.48550/arxiv.2205.01833`. A
41. **[R41]** Buneman, Khanna & Tan (2001). *Why and Where: A Characterization of Data Provenance*. LNCS. `10.1007/3-540-44503-x_20`. †

**Medical devices / FDA pathway (4)**
42. **[R42]** Zuckerman, Brown & Nissen (2011). *Medical Device Recalls and the FDA Approval Process*. Archives of Internal Medicine 171. `10.1001/archinternmed.2011.30`. A
43. **[R43]** Ardaugh, Graves & Redberg (2013). *The 510(k) Ancestry of a Metal-on-Metal Hip Implant*. NEJM 368:97–100. `10.1056/nejmp1211581`. A
44. **[R44]** Kramer, Xu & Kesselheim (2012). *Regulation of Medical Devices in the United States and European Union*. NEJM 366:848–855. `10.1056/nejmhle1113918`. A
45. **[R45]** Dhruva (2009). *Strength of Study Evidence Examined by the FDA in Premarket Approval of Cardiovascular Devices*. JAMA 302:2679. `10.1001/jama.2009.1899`. A (Crossref deposit lists only the first author)

All records: `https://api.crossref.org/works/<DOI>?mailto=medradar.research@proton.me` (R31 and R40: `https://api.openalex.org/works/doi:<DOI>`).

---

## §18 Quoted-numbers register

Every number appearing in the review, with the exact stored sentence fragment and the URL of the record that supplied it. Quotes are truncated to the fragment used; the full abstract is in `artifacts/lit_abstracts.json` with its sha256.

| # | Number(s) as quoted | Quoted fragment | Ref | Verifying URL |
|---|---|---|---|---|
| 1 | `3,073,351` citations; `2,515` documents; `252` subject categories | "this paper investigates 3,073,351 citations found by these six data sources to 2,515 English-language highly-cited documents published in 2006 from 252 subject categories" | R04 | https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:%2210.1007/s11192-020-03690-4%22&format=json&resultType=core |
| 2 | `88%` | "Google Scholar found 88% of all citations" | R04 | same as #1 |
| 3 | `112` superstars; `5%`–`8%` decline | "We estimate the magnitude of spillovers generated by 112 academic 'superstars'…"; "collaborators experience, on average, a lasting 5% to 8% decline in their quality-adjusted publication rates" | R07 | https://api.crossref.org/works/10.1162/qjec.2010.125.2.549 |
| 4 | `79,413` registry records; `2,178` results records; `20%`; `61%`; `52%` | "We characterized the 79,413 registry and 2178 results of trial records…"; "20% reported more than two primary outcome measures"; "61% lacked specificity"; "78 of 150 (52%) had associated publications within 2 years" | R23 | https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:%2210.1056/nejmsa1012065%22&format=json&resultType=core |
| 5 | `7,515`; `53%`; `66%`; `87%`; `46%`; `40%` vs `56%` | "Among the full sample of completed trials (n = 7,515)…"; "53% reporting trial end date, 66% reporting primary outcome, and 87% reporting trial start date"; "less than half (311 of 677, 46%) of trials were published"; industry `40%` vs nonindustry/nongovernment `56%` | R24 | https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:%2210.1371/journal.pmed.1000144%22&format=json&resultType=core |
| 6 | `585`; `171` (`29%`); `299,763` | "Of 585 registered trials, 171 (29%) remained unpublished"; "estimated total enrollment of 299,763 study participants" | R25 | https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:%2210.1136/bmj.f6104%22&format=json&resultType=core |
| 7 | `204,637`; `6,325,178`; `3,373,961` | "reference lists from 204,637 articles… containing 6,325,178 individual references to 3,373,961 unique papers" | R34 | https://api.crossref.org/works/10.1108/jd-12-2013-0166 |
| 8 | `690 thousand` events; `2.3 million` temporal relations | "over 690 thousand contemporary and historical events and over 2.3 million temporal relations" | R35 | https://api.crossref.org/works/10.1007/978-3-319-93417-4_18 |
| 9 | `209M` works; `2013M` authors; `124k` venues; `109k` institutions; `65k` concepts | "It contains metadata for 209M works…; 2013M disambiguated authors; 124k venues…; 109k institutions; and 65k Wikidata concepts" | R40 | https://api.openalex.org/works/doi:10.48550/arXiv.2205.01833 |
| 10 | `113` recalls; `21` (`19%`); `80` (`71%`); `8` (`7%`); `78%` | "There were 113 recalls… Only 21 of the 113 devices had been approved through the PMA process (19%). Eighty were cleared through the 510(k) process (71%), and an additional 8 were exempt from any FDA regulation (7%)."; conclusion: "…cleared for market using the less stringent 510(k) process or were considered so low risk that they were exempt from review (78%)…" | R42 | https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:%2210.1001/archinternmed.2011.30%22&format=json&resultType=core |
| 11 | `95` devices | "The ancestry of a problematic metal-on-metal hip implant includes 95 different devices." | R43 | https://api.crossref.org/works/10.1056/nejmp1211581 |
| 12 | `78` PMAs; `123` studies; `27%`; `14%`; `65%`; `52%`; `31%`; `88%` | "78 summaries… for 78 PMAs…"; "Thirty-three of 123 studies (27%)… were randomized and 17 of 123 (14%) were blinded"; "Fifty-one of 78 PMAs (65%) were based on a single study"; "111 of 213 primary end points (52%) were compared with controls… 34 of 111 controls (31%) were retrospective"; "187 of 213 primary end points (88%) were surrogate measures" | R45 | https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:%2210.1001/jama.2009.1899%22&format=json&resultType=core |
| 13 | `23` papers | "The study identified 23 papers." | R20 | https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:%2210.1258/jrsm.2011.110180%22&format=json&resultType=core |
| 14 | `64` universities | "survey data from 64 universities" | R28 | https://api.crossref.org/works/10.1287/mnsc.48.1.90.14271 |
| 15 | about half; one third | "about half of the collaborations are invisible in formal communication channels…; about one third of the collaborations are rewarded only by acknowledgements" | R15 | https://api.openalex.org/works/doi:10.3152/147154402781776961 |

**Numbers computed by the verifier (not sourced from literature, stored in `literature_refs.json`):** 45 references verified; 45/45 OpenAlex cross-checks; 18/45 Europe PMC hits; 32 abstracts (20 OpenAlex, 12 Europe PMC); 13 record-only; 124 API calls (Crossref 75, Europe PMC 45, OpenAlex 4); 6 coverage queries; 4 abstracts flagged low-overlap (R15, R21, R26, R33) — R26 is demonstrably unrelated text, R15 and R21 are compressed/one-sentence summaries, and R33's flag follows from its truncated deposited title; separately, R18's "abstract" is a citation string that passed the overlap screen without being an abstract; retrieval window `2026-11-03T20:07:07Z`–`2026-11-03T20:08:41Z`.

---

## §19 What S-029 can defensibly say (closing)

Subject to §15, the corpus supports exactly this shape of claim:

> We reconstructed a dated relation set among five medical-technology firms, research institutions, clinical studies, publications and regulatory activity from public evidence, and we measured — with recorded provenance — how much of it is identifiable, how much is attributable to the intended entity, how much carries a usable date, and how much is only co-presence. We did not measure knowledge transfer, direction of flow, or completeness against any true relation set, and we did not model or predict anything this round.

Anything beyond that sentence needs one of the human-truth designs in §13 (interviews R15, hand tracing R21/R43, manual audit R23/R45) or an exogenous design R07 — none of which this round runs. Stating that limit is the deliverable's value, not its apology.
