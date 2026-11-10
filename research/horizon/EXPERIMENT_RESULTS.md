# EXPERIMENT_RESULTS

**HORIZON-001 · three pre-registered data experiments · measured 2026-11-10**

The point of these experiments is not to show that the new sources are large. It is
to measure, against a recorded baseline, **how much genuinely independent
information they add**, **which identity signals are sufficient**, and **whether
their timestamps are good enough for historical research**.

Every number below is computed from files in this repository by a script that is
also in this repository. No number is an estimate.

---

## EXP-H1 — independent coverage added by new sources

### H1(a) Patents: what the sitemap channel actually exposes

The EPO publication sitemap lets us enumerate publications **without fetching
documents**: each weekly sitemap carries publication reference, application
reference and IPC for every EP publication of that week.

| quantity | value |
|---|---|
| weekly sitemaps read | 10 (2005-06-01 … 2026-06-03) |
| publications enumerated | **37 989** |
| medical-device publications among them | **3 093** (8.14 %) |
| front pages fetched | 228 |
| share of enumerated medtech actually fetched | **7.4 %** |
| requests used | 241 |
| bytes received | 30.7 MB |

So there is a genuine two-tier economy here that did not exist before:

* **Tier 1 (cheap):** for ~10 sitemap requests you get 3 093 dated,
  IPC-classified medical-device publication references — an enumerated frame, not
  a keyword search result.
* **Tier 2 (dear):** ~135 KB and one request per publication buys applicant,
  inventors, title, abstract, priority.

What the tier-1 frame can answer on its own: publication-date distribution,
IPC-class composition, application-date distribution, and the
publication−filing gap — all at population scale for the weeks sampled. What it
cannot answer: who the applicant was.

### H1(b) Patents: duplicates hiding inside the source

EP publication kinds are not interchangeable, and one channel happily returns
them all:

| document role | n | independent technical disclosure? |
|---|---|---|
| granted specification (B1) | 115 | yes |
| application publication (A1) | 58 | yes |
| **search report (A3)** | **28** | **no** |
| application, no search report (A2) | 22 | yes |
| **corrected title page (B8)** | **3** | **no** |
| amended/limited grant (B2, B3) | 2 | yes |

228 fetched documents → **197 independent technical disclosures**. A naive count
is inflated by **13.6 %**. `tools/finalize_patent_records.py` applies the mapping
and flags the non-disclosures.

### H1(c) Patents: are the two patent sources independent?

The honest test is not name matching — it is whether the two offices hold the
**same invention family**. A CA patent and an EP publication claiming the same
priority application are one invention, not two observations.

This is computed in `experiments/patents/measure_patents.py`
(`cross_source_overlap`) by intersecting normalised `COUNTRY:NUMBER` priority keys.
Results are in `EXP_H1_PATENTS.json`.

### H1(d) Scholarly: 308 source rows are 60 works

| quantity | value |
|---|---|
| pre-registered anchors | 60 distinct DOIs |
| source rows fetched across 6 databases | **308** |
| distinct works after de-duplication | **60** |
| **dedup ratio** | **0.195** |
| anchors present in all 6 databases | 36 / 60 |
| anchors present in 4 | 20 |
| anchors present in 3 | 4 |

Per-source anchor hits (/60): OpenAlex 60, Crossref 59, OpenAIRE 59,
Semantic Scholar 56, Europe PMC 37, PubMed 37.

**A naive union across six databases over-counts the same literature by ≈5.1×.**
Any "we now have 308 publications" claim would have been false by a factor of five.

Important reading constraint, stated by the pre-registration: the anchor set is
**OpenAlex-defined**, so OpenAlex's 60/60 is definitional, not a coverage win.
37/60 is coverage *of an OpenAlex sample*, not a completeness ranking of Europe PMC.

Cross-identifier consistency: PMID — 38 anchors with one agreed value,
**0 conflicts**, 22 absent everywhere. PMCID — 0 conflicts. So the *identifier*
layer is reliable; it is the *date and title* layers that disagree.

---

## EXP-H2 — cross-national product identity quality

**Files:** `experiments/regulatory/EXP_H2_SELECTION_RULE.md` (written before any pair
was examined), `EXP_H2_PAIRS.jsonl` (726 pairs), `EXP_H2_SUMMARY.json`,
`exp_h2_identity.py`. Inputs: 320 FDA GUDID records × 174 Health Canada MDALL records.

Signals, in increasing strength:
**S1** exact name · **S2** shared model token · **S3** same firm ·
**S4** shared official identifier · **S5** multi-field conjunction.

### Result: 726 pairs, 0 CONFIRMED

| verdict | n |
|---|---|
| `CONFIRMED` | **0** |
| `REJECTED` | 0 |
| `UNKNOWN` | 726 |

**`S4_official_identifier_fired: 0`.** GUDID and MDALL share **no identifier
namespace** — UDI-DI versus Health Canada licence / device / identifier numbers. There
is therefore **no keyless official-identifier bridge between the two registries**.

Signal sufficiency table (the deliverable, not a footnote):

| signal combination | pairs | CONFIRMED | REJECTED | UNKNOWN | reaches CONFIRMED? |
|---|---|---|---|---|---|
| S3 + S5 | 19 | 0 | 0 | 19 | no |
| S3 | 689 | 0 | 0 | 689 | no |
| S5 | 18 | 0 | 0 | 18 | no |
| S2 (shared model token) | 0 fired | 0 | 0 | 0 | no |
| S3 (same firm) | 708 fired | 0 | 0 | 708 | no |

Hard negatives: **26 pairs** constructed by the stated rules
(`HN3_same_family_different_device` 14, `HN4_subsidiary_vs_parent` 12); all 26 land in
`UNKNOWN`, which is the correct outcome — the point of a hard negative is that it must
not be silently matched.

### What this means for MedRadar

1. **Cross-national device identity cannot be established from official records
   alone.** Agreement on name tokens and firm is *common* (S5 fires on 37 pairs, S3 on
   708) but model-token agreement never occurs, and even the strongest evidence still
   only ever yields `UNKNOWN`. Any pipeline that promotes name/firm agreement to a
   match is asserting identity it cannot prove.
2. **The rule held.** A name-matching "accuracy" number would have looked impressive
   here and would have been meaningless: no pair shares a model token, and none is
   provable.
3. **The blocking design question for ATLAS-001** is therefore not "which
   fuzzy-matching algorithm" but "what non-registry evidence (PCT priority, UDI in
   procurement text, manufacturer cross-reference filings) is allowed to bridge two
   registries". This experiment says the answer is not inside the registries
   themselves.
4. Where official records cannot decide, the verdict is `UNKNOWN` — not a guess and
   not an AI consensus.

---

## EXP-H3 — is this data fit for historical time research?

### H3(a) Patents — two clocks, years apart

| source | records | with recorded public date | with filing date | two-clock |
|---|---|---|---|---|
| EPO publication server | 228 | **228 (100 %)** | 228 (100 %) | 228 |
| CIPO Canada | see `EXP_H3_PATENTS.json` | grants only | yes | per record |

Measured `publication − filing` gap on the EP sample:
**min 114 days · median 1 738 days (4.8 y) · max 6 881 days (18.8 y)**, bucketed in
`EXP_H3_PATENTS.json`.

Two confusions were checked explicitly and are handled in code:

1. **INID 43 vs INID 45.** A granted EP document carries both the application
   publication date and the grant date. `EP2490731B1`: 43 = 2012-08-29,
   45 = 2024-06-05. Using 43 for a 2024 grant misdates it by ~11.8 years. The
   connector selects by kind and stores both raw values.
2. **Filing date is not an observation date.** For CIPO, no publication date is
   recorded in the dataset at all; the 18-month laid-open rule is a rule, not a
   field, and is deliberately **not** applied. Pending applications get
   `source_public_at = NULL` and `MISSING_PUBLICATION_DATE`.

Historical versions: **not available from either patent source.** Both serve the
document as published / the current extract. So patent records are
`SNAPSHOT_ONLY` with respect to record state, while still having a genuine
publication clock. That distinction is the one that matters, and it is why the
patent data *is* eligible for observability work even though it is not eligible for
version-diff work.

### H3(b) Scholarly — the publication date is not one value

This is the single most consequential measurement of the round.

| measurement | value |
|---|---|
| anchors where ≥2 databases disagree about the publication date | **36 / 60 = 60.0 %** |
| anchors disagreeing by **more than 30 days** | **22 / 60 = 36.7 %** |
| spread: same day | 24 |
| 1–7 d | 5 · 8–30 d | 9 · 31–180 d | 15 · over 730 d | 1 |

Worst pairwise disagreements: Europe PMC vs Semantic Scholar **56.8 %**,
PubMed vs Semantic Scholar **56.8 %**, Europe PMC vs OpenAlex **51.4 %**,
Crossref vs PubMed **50.0 %**. Cleanest pair: Europe PMC vs PubMed **8.1 %**
(same lineage — which is exactly what you would expect, and a good sanity check
that the method is not noise).

**Consequence for MedRadar:** a single `publication_date` column is a modelling
error. Either store the per-source value with its provenance, or pick one
authority and record the disagreement. The export keeps per-source values.

### H3(c) Scholarly — who can even support observability work

Only three of the six databases publish a real creation/index timestamp:
OpenAlex (`created_date`), Crossref (`created` = DOI registration), Europe PMC
(`firstIndexDate`). **PubMed, Semantic Scholar and OpenAIRE expose no creation
timestamp at all** — 37/37, 55/56 and 59/59 of their records are snapshot-only.
A history built only on those three cannot distinguish "published" from "we can
see it now".

Measured index lag (creation − nominal publication):

| source | median | min | max | note |
|---|---|---|---|---|
| OpenAlex | **+14 d** | −266 d | +969 d | positive = record became visible after nominal publication |
| Crossref | **0 d** | −269 d | +968 d | **21/59 registered BEFORE the nominal publication date** |
| Europe PMC | +2 d | — | — | |

ClinicalTrials.gov submission → first posting: median **8 days**, max **892 days**
over 164 trials. That is a registry queue, not an indexing lag, and it must not be
modelled as one.

The negative values are informative rather than errors: they occur where the
"publication date" is an issue date later than the record's own creation
(e-pub-ahead-of-print). That is precisely the four-clock phenomenon.

### H3(d) Verdict

| source | eligible for observability work? | eligible for version-diff work? |
|---|---|---|
| EPO publications | **yes** — 100 % have a recorded public date | no — published artefact only |
| CIPO Canada | **grants only** | no — single quarterly snapshot |
| OpenAlex | yes — has `created_date` | partially |
| Crossref | yes — DOI registration timestamp | partially |
| Europe PMC | yes — `firstIndexDate` | partially |
| PubMed / Semantic Scholar / OpenAIRE | **no** — snapshot only | no |
| ClinicalTrials.gov | yes — submission and posting both present | n/a |

---

## Relations produced (verifiable links only)

| relation | CONFIRMED | CANDIDATE | rule used |
|---|---|---|---|
| trial ↔ paper | 69 | 113 | CONFIRMED only where the trial record names a PMID/DOI *and* (where claimed as a result) the paper names the NCT |
| grant ↔ work | 10 | 33 | CONFIRMED only where the grant number appears in the work's own funding metadata |
| device ↔ procurement award (industry) | **0** | 124 | device *class* named in 94 awards, model-like token in 11, **manufacturer named in 0** |

Two worked examples of why "the identifier matches" is not "the claim is true",
both found by the scholarly workstream and both kept as documented failure modes:

* **CT.gov reference types are submitter-asserted and demonstrably wrong.** Of 66
  references typed `RESULT`/`DERIVED`, only **35** are corroborated by the paper's
  own abstract naming that trial's NCT. `NCT04011371`, for instance, labels three
  epidemiology papers as results. Confidence is therefore split HIGH 35 / LOW 31
  rather than reporting all 66 as confirmed.
* **A grant number can match while the attribution is wrong.** DOI
  `10.1093/ageing/afab278` declares H2020 grant `831644` in Europe PMC, PubMed
  *and* Crossref; CORDIS `831644` is `EOSECretariat.eu`. Perfect number match, very
  likely wrong attribution — a publisher metadata error that no identifier
  matching can fix. Every `CONFIRMED` grant relation is scoped to "the number
  matches", never "the grant funded this work".

---

## Where the numbers live

| experiment | files |
|---|---|
| EXP-H1 patents | `experiments/patents/EXP_H1_PATENTS.json`, `measure_patents.py` |
| EXP-H1 scholarly | `experiments/scholarly/EXP_H1_DEDUP.json`, `EXP_H1_DEDUP_SUMMARY.json`, `EXP_H1_ANCHOR_MATRIX.jsonl`, `EXP_H1_SELECTION_RULE.md` |
| EXP-H2 identity | `experiments/regulatory/EXP_H2_PAIRS.jsonl`, `EXP_H2_SUMMARY.json`, `EXP_H2_SELECTION_RULE.md` |
| EXP-H3 patents | `experiments/patents/EXP_H3_PATENTS.json` |
| EXP-H3 scholarly/trials | `experiments/scholarly/EXP_H3_PUB_TIME.json`, `EXP_H3_PUB_TIME_SUMMARY.json` |
| EXP-H4 industry | `experiments/industry/EXP_H4_INDUSTRY.json` |
| relations | `experiments/scholarly/RELATIONS_TRIAL_PAPER*.jsonl`, `RELATIONS_GRANT_WORK*.jsonl` |

Reproduce (offline, from committed samples):

```powershell
cd research\horizon
python experiments\patents\measure_patents.py
python experiments\scholarly\analyze_exp_h1.py
python experiments\scholarly\analyze_exp_h3.py
```
