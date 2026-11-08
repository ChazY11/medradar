# A04 — The Lens: paper↔patent linkage, citation structure, time-lag, and access terms (M4)

Audit of: **The Lens** — platform (lens.org), its API (api.lens.org / docs.api.lens.org), and the published
method behind its patent–scholarship linkage: **Jefferson OA, Jaffe A, Ashton D, Warren B, Koellhofer D, Dulleck
U, Ballagh A, Moe J, DiCuccio M, Ward K, Bilder G, Dolby K, Jefferson RA. "Mapping the global influence of
published research on industry and innovation." Nature Biotechnology 2018;36:31–39.**
doi:[10.1038/nbt.4049](https://doi.org/10.1038/nbt.4049) · [PMC12094095](https://pmc.ncbi.nlm.nih.gov/articles/PMC12094095/)

| Field | Value |
|---|---|
| Name | The Lens (PatCite + scholarly/patent corpus); method paper = Jefferson et al., Nat Biotechnol 2018 |
| Official URL | https://www.lens.org/ · API docs https://docs.api.lens.org/ · terms https://about.lens.org/policies/ and https://about.lens.org/lens-api-terms-of-use/ |
| Type | **Public platform** (non-profit social enterprise, "The Lens PTY LTD" → The Lens Limited per 2026 relaunch notice) + one public paper describing its linkage method |
| Licence / terms | **Not an open licence.** Terms of Use v2026.06.01: data use conditions "intended to resonate with the principles of Creative Commons attribution license **CC BY-NC-SA**", with mandatory retention of Lens IDs and attribution. API governed by separate API Terms (institutional subscription only). Commercial use requires a commercial licence. |
| Code public? | **No.** No public source for the NPL-resolver, In4M metric or PatCite backend. |
| Data public? | **Partly, for human browsing — not for bulk or programmatic reuse.** Anonymous users may "export up to 1,000 records and metadata"; registered individuals may export records for personal non-commercial use; bulk download requires a plan. |
| Access barrier | (a) API: institutional subscription, manual approval, token; trial is non-commercial evaluation only. (b) No automated crawling/scraping permitted — explicitly prohibited. (c) Bulk data behind subscription. **No free public API tier.** |
| GPU / paid needed | No GPU. **Paid**: API/bulk access is subscription or custom-priced. |
| Reproducibility status | **Not reproduced and deliberately not attempted.** The method (NPL resolution → identifier matching → family-weighted citation intensity) is documented in enough detail to re-implement the *pipeline shape* (threshold 0.9 vs PubMed/Crossref), but the corpus is proprietary and the terms forbid the automated extraction a reproduction would require. No Lens data was queried during this audit (see §5). |

---

## 1) What the source actually says

**1a. Access rights — verified verbatim from the current Terms of Use** (`about.lens.org/policies/`,
v2026.06.01, retrieved via the site's own WP REST API because the rendered page's navigation consumed the fetch
budget):

> "**Anonymous users**: Anyone and anywhere in the world, without registering on Lens.org or signing any
> contract, can freely and securely, discover, explore all the Lens innovation data, analyse their results, and
> export up to 1,000 records and metadata."

> "**Individual users**: Individuals who register for a free account can access the platform with additional
> benefits for their own personal, non-commercial use … Individual users who currently use the Lens.org platform
> for commercial purposes are requested to take up a subscription"

> "The conditions by which The Lens data may be used are intended to resonate with the principles of Creative
> Commons attribution license **CC BY-NC-SA** including retention of Lens IDs in any redistribution of the data to
> facilitate data interoperability and reuse."

> "you may not engage in deceptive behaviour or use any automated crawlers, robots, spiders, or other automated
> downloading programs to: (i) continuously and automatically search, scrape, extract or index any content; …
> (iii) cause disruption to the working of the Services"

Attribution is mandatory: "Enabled by The Lens" or "Data Sourced from The Lens", plus the Lens logo, plus the
lens.org URL, "prominently displayed at the point of delivery".

**1b. API availability and terms** (`docs.api.lens.org`, and `about.lens.org/lens-api-terms-of-use/`):

> "**Lens API service is only available through an institutional subscription.** Individuals are encouraged to
> approach their institutional librarian to take up a lens institutional subscription."
> (API Terms of Use, v2026.06.01)

> "Trial access is provided to evaluate the API and is **for non-commercial use only**." … "Note, that trial
> access does not include commercial permissions."

> "For all requests for API access, The Lens asks that you provide an official email address and inform the Lens
> team of your use case, affiliation, and project timeline." … "Your request will be reviewed and processed
> **manually**"

Documented endpoints (`docs.api.lens.org/getting-started.html`, API 2.20.0, patent schema 1.6.5):
`POST/GET /patent/search`, `GET /patent/{lens_id}`, `POST/GET /scholarly/search`, `GET /scholarly/{lens_id}`,
`GET /schema/patent`, `GET /schema/scholarly`, `POST/GET /collections/{collection_id}`, plus usage endpoints.
Rate limiting is real and documented via response headers (`x-rate-limit-remaining-request-per-minute`,
`x-rate-limit-remaining-record-per-month`, …), with `429 Too Many Requests` on breach. Bulk data is a separate
product: "Bulk data downloads enable users to download scholarly and patent bulk data files via the API or UI"
(subject to a plan).

**Answer to "is there a public API with documented terms, and what is permitted without a paid subscription?"**
Documentation and schema are public and readable without an account. **Use** of the API is not: it requires an
approved token, and approval is tied to an institutional subscription. Without a paid subscription the only
permitted access is interactive browsing/analysis in the UI plus export of **≤1,000 records** for non-commercial
use with attribution — no automated querying, no bulk download.

**1c. Corpus scale** (from the Lens PatCite page, `about.lens.org/patcite-linking-patents-and-scholarship/`):
patents 153.2M; patent citations 417M; applicants 17.5M; owners 1.6M; families 86.2M; scholarly works 266M;
scholarly citations 2.1B; authors 39.2M; scholarly coverage "1800–".

**1d. Paper↔patent linkage method** (Jefferson et al. 2018, PMC12094095 — CC BY):

> "there are almost 54.87 million simple patent families (distinct inventions). Out of these, 4.7 million
> families (7.6 million patent documents) contain the 31.6 million NPL citations as strings of free text"

> "we challenged canonical, well-curated databases, namely PubMed and Crossref metadata, and resolved the poorly
> structured NPL strings into more uniform and standard formats through the use of open persistent identifiers"

> "Resolving the 31.6 million NPL strings to either PubMed IDs or DOIs, or both, resulted in 14.1 million total
> resolved citations; 8.3 million resolved to a DOI citation, 5.8 million to a PMID, and 4.3 million to both IDs.
> **Resolving and matching was done based on a matching score threshold of 0.9.**"

Source of the citation records: "Over 30 patent authorities voluntarily contribute citations to the EPO citation
database … The top four contributors are the USPTO, WIPO, EPO and SIPO" (paraphrase; the four are named in the
figure legend). Technology classification uses "the WIPO concordance table, which links IPC symbols with 35
fields of technology".

Citation structure and weighting (the metric, In4M):

> "We weight each unique citation by the size of the patent family, as this count is a proxy of a perceived
> economic value of the invention by patent applicants, and also normalizes for variation in citation reporting
> between jurisdictions."

> "By analyzing resolved scholarly outputs from about 200 leading global research institutions over the past 35
> years … an international innovation and industry influence mapping (In4M) metric … citations of the patents
> citing third parties, weighted by the size of patent family over total resolved articles."

Reported scale for that exercise: 11.8M resolved scholarly outputs 1980–2015; "10%, on average, were matched in
the Lens citation database"; those were cited in 690,000 simple patent families (1.1M patent records).

**1e. Time-lag between research output and technology application.** The Lens paper does **not** publish a lag
distribution. The nearest published quantity it cites is secondary:

> "Ahmadpoor and Jones have recently shown that 80% of cited research is connected to future patents and 61% of
> patents link to prior scholarship, if linkage is defined on a network including indirect linkages."

So: the *mechanism* for measuring a lag is present (each resolved citation carries the cited article's
publication year and the citing patent's filing/priority/publication year, both first-class fields), but **no
Lens publication I could access reports an estimated lag distribution**. Any lag number must be computed by the
user, on the user's own access rights. I did not compute one (see §5).

## 2) What is NOT disclosed

- **The resolver itself.** "matching score threshold of 0.9" is the only algorithmic constant. The score's
  definition (string similarity? token overlap? which normalisation?), the blocking/indexing strategy, and the
  handling of ambiguous matches are in "Supplementary Methods", which I did not retrieve (PMC supplementary list
  is present; contents not fetched).
- **The In4M normalisation constants** and the discipline mapping (nine research disciplines via ISSN/Crossref
  categories) — described in outline only.
- **PatCite's "multi-stage citation-processing protocol"** — named, not specified.
- **API quotas and prices.** No public rate/volume table per plan; trial limits are conveyed on approval, and
  pricing is "determined by use case, attribution plan and API volume and speed requirements" (custom quote).
- **Whether the 0.9 threshold was tuned on a labelled sample**, and what its precision/recall are on a
  held-out set. Not reported in the parts I retrieved.
- **Time-lag statistics.** See §1e: not published in the accessible sources.
- **The exact licence of the *paper's* supplementary data** vs the *platform's* data — the article is CC BY, the
  platform data is not.

## 3) Method extraction (precise enough to re-implement, subject to data access)

```
Stage 1 — obtain NPL citations
  patent documents -> non-patent-literature reference strings
  source: EPO citation database (30+ authorities), ingested by The Lens
  unit   : simple patent family (dedupe citations within a family; count across families)

Stage 2 — resolve strings to persistent identifiers
  candidate authorities: PubMed (PMID) and Crossref metadata (DOI)
  match if similarity score >= 0.9        [only published constant]
  outputs: NPL -> {DOI, PMID, both, unresolved}

Stage 3 — link and classify
  resolved article  <-> citing patent family
  patent -> technology field via WIPO IPC -> 35-field concordance
  article -> research discipline via journal ISSN -> Crossref category -> 9 disciplines

Stage 4 — weight and aggregate (In4M)
  w(family)      = size of the simple patent family (proxy for perceived value;
                   also normalises cross-jurisdiction citation-reporting differences)
  In4M(entity)   = sum over resolved citations of w(family) citing third parties
                   / total resolved articles of that entity
  variants       : normalised by research discipline; by field of use (35 WIPO fields)

Stage 5 — time-lag (mechanism present, parameters unpublished)
  lag = citing patent filing/priority year - cited article publication year
  distribution/median NOT published by The Lens in the sources audited
```

## 4) Data requirements, and whether that data exists in a medical-device regulatory setting

| Requirement | Lens | MedRadar |
|---|---|---|
| patent corpus with citations | 153.2M patents / 417M citations (proprietary) | **absent** — MedRadar has no patent data at all |
| scholarly corpus with citations | 266M works / 2.1B citations | **absent** — no bibliographic layer |
| NPL reference strings | present (31.6M) | n/a |
| regulated-product authorisation records | incidental | **present and strong**: 375,378 events incl. 510(k)/PMA |
| firm identity | owners/applicants | `companies` (89 keys — narrow) |
| classification dimension | IPC → 35 fields; ISSN → 9 disciplines | `tracks` (60), `product_codes.specialty` (FDA panels) |

So: the Lens linkage construct requires two corpora, and MedRadar has **neither**. Building a
patent→device or paper→device linkage is possible in principle (e.g. openFDA 510(k) summaries cite literature;
ClinicalTrials.gov records have publications) but that is a data-acquisition project, not a method transfer,
and the Lens corpus could not lawfully be bulk-acquired under the terms audited here.

## 5) My independent implementation and its self-test result

**No implementation of the Lens pipeline was written, and no Lens data was queried.** That is a deliberate
compliance decision, not an oversight:

- The terms prohibit automated extraction and bulk download, and the API requires an approved institutional
  token. Producing an implementation would only be exercisable by violating those terms, so building one would
  be theatre.
- The audit's purpose for M4 is the *legality and availability* question, which is answered directly from the
  primary terms documents (§1a–1b) rather than inferred from behaviour.

What was verified mechanically instead: the terms text and the API documentation were retrieved from the
publishers' own endpoints (two WP REST API calls for the policy pages, whose rendered HTML exceeded the fetch
budget; `docs.api.lens.org` pages directly; the 2018 method paper from PMC full text). Every quoted sentence
above is from those retrievals on 2026-11-08.

The **shared** self-test in this audit folder (56/56 checks, `selftest_synthetic.py`) does exercise one construct
that a Lens-style analysis would need if MedRadar ever obtained a citation-like graph: contemporaneous,
snapshot-based accumulation with an explicit leakage guard
(`trajectory_features.contemporaneous_influence`, verified to ignore citations dated after the snapshot year).
That is method scaffolding, not a reproduction.

## 6) Applicability to MedRadar

Mostly **not applicable**, for hard reasons:

1. **No legal path to the data.** Bulk/programmatic access requires an institutional subscription under a
   CC BY-NC-SA-resonant, non-commercial, attribution-heavy regime; MedRadar has no such subscription and the task
   forbids paid keys. Even under a subscription, the terms' non-commercial framing would need legal review before
   anything entered a product pipeline.
2. **No corpus to link.** MedRadar has no patents and no scholarly works. A paper↔patent or patent↔device linkage
   needs both sides.
3. **What *is* transferable is conceptual and cheap:** (a) the idea of **normalising a citation/attention signal by
   a group-size or family-size weight** so that jurisdiction/documenting artefacts don't masquerade as signal;
   (b) the discipline of **resolving free-text references to persistent identifiers with an explicit match
   threshold and a measured resolution rate** (14.1M/31.6M ≈ 45% resolved) rather than pretending the join is
   clean. For MedRadar, the analogous join is free-text company/applicant names → `company_key`, where an explicit
   match threshold plus a reported resolution rate would materially improve the 89-key firm universe.
4. **Attribution obligation, if ever used.** Any MedRadar artefact derived from Lens data must carry the Lens logo,
   the lens.org URL, "Enabled by The Lens", and retain Lens IDs — a product-level constraint, not a footnote.

## 7) Limitations, bias and leakage risks

- **Licence risk dominates everything else.** "CC BY-NC-SA-resonant" is not CC BY-NC-SA; it is a bespoke term set
  that additionally forbids automated access. Do not treat Lens data as open data.
- **Non-commercial constraint.** Trial API access is explicitly non-commercial; commercial use needs a separate
  agreement. Any MedRadar use is presumptively commercial.
- **Resolution bias.** Only ~45% of NPL strings resolve (14.1M/31.6M). Resolution quality varies by era and
  jurisdiction (older and non-Roman-script references resolve worse), so any lag or intensity statistic inherits a
  time- and country-dependent *missingness* that is correlated with the very quantities being measured.
- **Citation-reporting bias.** The paper itself notes "The role of scholarly citation in patents varies over
  jurisdictions, locations within the patent document and prosecution history" — the family-size weighting
  mitigates but does not remove it.
- **Field skew.** The authors state the observed skew is "mainly in pharmaceuticals and biotech sectors"; a
  medical-device application would sit in a *different* skew regime, so any Lens-derived benchmark is not
  transferable to devices.
- **Time-lag construct is weak even in principle.** Patent citations are added by examiners as well as applicants
  and can be added years after filing; "lag" therefore conflates invention timing, drafting, examination and
  database ingestion.
- **Leakage risk if ever used for forecasting.** Citing-patent publication date is *after* the citation event;
  using publication year as the time stamp leaks future information relative to the patent's filing. Any lag must
  be measured from priority/filing date, not grant/publication date.
- **Attribution/derivative risk.** CC BY-NC-SA-resonant terms plus "no derivatives" is not stated for data, but the
  paper is CC BY-NC-ND — do not assume figure reuse is permitted.

## 8) Decision

**STUDY_ONLY.**

Reasoning: the method is well enough described to be *understood* and partly re-implementable in shape, but the
data is proprietary, bulk and automated access are contractually prohibited without an institutional
subscription, trial access is explicitly non-commercial, and there is no free public API tier. MedRadar has no
patent or scholarly corpus to link, so even a licensed implementation would have nothing to run on. The
transferable value is limited to two design patterns (group-size normalisation; explicit match threshold with a
reported resolution rate) and one compliance obligation (attribution). This would become **BLOCKED-for-data /
ADAPT-for-method** only if MedRadar obtained an institutional Lens subscription *and* a patent corpus — neither of
which is in scope.

## 9) Open questions

1. What does the 0.9 matching score actually compute, and what are its precision/recall on a labelled sample?
   (Supplementary Methods — not retrieved.)
2. Are there published Lens time-lag statistics anywhere (e.g. in the In4M/PatCite grey literature or the
   *Transgenic Research* 2021 companion paper)? Not found in the sources audited.
3. What are the concrete trial-API limits (calls/month, records/month)? Documented as headers at runtime only;
   values appear after approval.
4. Does an institutional Lens subscription permit *derived* statistics to be published or used commercially, or
   only non-commercial research? (Needs the signed agreement, not the public terms.)
5. Is "The Lens Limited" (2026 entity) changing the licence regime? The relaunch notice (1 June 2026, SPIE
   partnership) is recent; terms were last updated 2026-06-01.
6. Could openFDA 510(k) summaries' cited literature give MedRadar a lawful, small-scale paper→device linkage
   without Lens? (Not tested; would be a separate feasibility task.)

## Evidence paths

- `docs/phoenix/audits/A04_the_lens.md` (this file)
- `experiments/phoenix/external/methods_audit_summary.json` — machine-readable decision record
- `experiments/phoenix/external/methods/evidence.json` — retrieval record incl. the two terms documents and the
  2018 method paper
- `experiments/phoenix/external/methods/trajectory_features.py` — the leakage-guarded contemporaneous accumulation
  helper referenced in §5

## Citations

- The Lens — Terms of Use (v2026.06.01): https://about.lens.org/policies/
- The Lens — API Terms of Use (v2026.06.01): https://about.lens.org/lens-api-terms-of-use/
- The Lens — API documentation (v2.20.0): https://docs.api.lens.org/ · https://docs.api.lens.org/getting-started.html
  · https://docs.api.lens.org/bulk-data.html
- The Lens — PatCite: https://about.lens.org/patcite-linking-patents-and-scholarship/
- Jefferson OA et al. Nat Biotechnol 2018;36:31–39. https://doi.org/10.1038/nbt.4049 ·
  https://pmc.ncbi.nlm.nih.gov/articles/PMC12094095/
