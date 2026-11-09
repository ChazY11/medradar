# DATA_QUALITY_AUDIT

**HORIZON-001 · audit of the 24,194-record export `horizon-2026-11-10`**

This audit is generated from the export itself, not from intentions. Counts are
recomputable with `python -m hz.cli verify` and from `exports/horizon-2026-11-10/MANIFEST.json`.

---

## 1. Duplication

There are **three different kinds of duplicate** in this data and they must not be
handled by one mechanism.

| kind | example | correct handling | measured |
|---|---|---|---|
| **Same record fetched twice** | the same URL hit twice in one run | drop, keep one | handled by content hash + `(source_record_id, content_hash)` |
| **Same work in several databases** | one DOI in OpenAlex, Crossref, Europe PMC, PubMed, S2, OpenAIRE | **de-duplicate to one work** | 308 rows → **60 works** (ratio 0.195; naive union over-counts ≈5.1×) |
| **Same entity, several records** | 299 TED supplier rows describe 93 notices; 62 FTS rows describe 16 releases | **group on the entity key, never filter** | 299→93 and 62→16 entity keys |

That third row caused a real bug during this round. `hz.schema.dedupe_key` returns
an **entity** key (UDI-DI, DOI, publication number…). The first export build
de-duplicated on it and silently deleted **206 of 299 TED rows and 46 of 62 FTS
rows** — i.e. it deleted distinct suppliers. The exporter now de-duplicates on
record identity and emits a manifest note wherever entity-key multiplicity
exists, so ATLAS-001 groups rather than loses data.

A second duplicate class is **inside a single source**:

| source | duplicates inside the source | cause |
|---|---|---|
| EPO publications | **31 / 228 (13.6 %)** | A3 search reports (28) and B8 corrected title pages (3) are not new technical disclosures |
| CIPO Canada | 0 / 19 702 | one row per Canadian patent number |
| scholarly | 5.1× across databases | see above |

---

## 2. Entity mis-attribution

### 2.1 Name matching is not identity — measured, not asserted

`cipo_canada` is a **firm-scoped** slice: 19 702 Canadian patents whose applicant
or owner name matched a documented alias of one of five target firms. Every such
record is `identity_status = CANDIDATE` with the quality flag `NAME_MATCH_ONLY`,
and the verbatim party name is preserved. No `CONFIRMED` firm identity is claimed
for CIPO.

The same discipline applied to the scholarly workstream: a firm name inside an
affiliation string is not an identity, so **all 60 publication records are
`identity_status = UNKNOWN`** with the affiliation string stored verbatim. One
anchor matches "Medtronic" inside a 300-character disclosure block rather than an
institutional address. The strings were kept, not cleaned, so a reader can judge.

### 2.2 The historical-subsidiary problem, quantified

This is the single most important identity finding of the round, and it comes from
the CIPO ownership table. Alias hit counts across 13.2 million party rows:

| alias | patents | why it matters |
|---|---|---|
| `PHILIPS` | 13 508 | canonical name |
| `MEDTRONIC` | 1 837 | canonical name |
| `TYCO HEALTHCARE` | 1 613 | Covidien predecessor |
| `COVIDIEN` | 1 553 | Medtronic subsidiary since 2015 |
| `GE HEALTHCARE` | 572 | canonical name |
| `ST. JUDE` | 245 | Medtronic subsidiary since 2017 |
| `DRAGER` | 180 | ASCII rendering of Dräger |
| `DRAEGER` | 113 | alternative ASCII rendering |
| `RESPIRONICS` | 78 | Philips subsidiary since 2008 |
| `VOLCANO` | 77 | Philips subsidiary since 2015 |
| `OHMEDA` | 50 | GE Medical Systems subsidiary |
| `DATEX-OHMEDA` | 35 | GE Medical Systems subsidiary |
| `GE MEDICAL SYSTEMS` | 26 | GE HealthCare predecessor name |
| `ARTERIAL VASCULAR` | 20 | acquired by Medtronic 1999 |
| `INSTRUMENTARIUM` | 13 | GE Medical Systems subsidiary 2003 |
| `SPECTRANETICS` | 13 | Philips subsidiary 2017 |
| `ST JUDE` | 1 | spacing variant of the same entity |

**A naïve name filter on "Medtronic" would find 1 837 patents. The group's true
footprint in this dataset is 5 078 — because 3 166 of them were filed under Tyco
Healthcare, Covidien, St. Jude Medical or Arterial Vascular Engineering.**

That is a 2.8× undercount produced by doing the obvious thing. It is exactly the
failure mode the brief described as a top bottleneck, now measured on real data.

Two cautions on the table above, both material:

* `PHILIPS` 13 508 is **not** a medical-technology count. Philips' Canadian
  portfolio spans lighting and consumer electronics, and the CIPO IPC table was
  **not acquired** this round (see §5), so the medical subset cannot be isolated.
* Alias lists are `CANDIDATE` mappings with a stated basis. "Tyco Healthcare is a
  Covidien predecessor" is corporate history, not a verified record-level link.

### 2.3 Descriptive-title error, found and kept

Europe PMC record for DOI `10.1093/ageing/afab278` declares H2020 grant `831644`
in Europe PMC, PubMed **and** Crossref. CORDIS `831644` is `EOSCsecretariat.eu`.
The number matches perfectly and the attribution is almost certainly wrong. No
identifier-matching strategy fixes this; it is a publisher metadata error. Every
`CONFIRMED` grant relation in this round is therefore scoped to *"the number
matches"* and never to *"the grant funded this work"*.

### 2.4 Submitter-asserted fields are not ground truth

ClinicalTrials.gov reference `type` is supplied by the trial sponsor. Of 66
references typed `RESULT`/`DERIVED`, only **35** are corroborated by the paper's own
abstract naming that trial's NCT number. `NCT04011371`, for example, labels three
epidemiology papers as results. The relations file carries a HIGH/LOW confidence
split (35 HIGH / 31 LOW) rather than reporting 66 confirmations.

---

## 3. Time semantics

### 3.1 The four clocks, per source

`hz.timeq` classifies every record. From the export manifest:

| class | meaning | sources where it dominates |
|---|---|---|
| `FULL_TWO_CLOCK` | both a recorded public date and a recorded event date, correctly ordered | EPO 228/228, Crossref 59/59, Europe PMC 37/37, OpenAlex 60/60, TED 297/299, FTS 62/62 |
| `PUBLICATION_ONLY` | public date known, event date unknown | AccessGUDID 320/320 |
| `EVENT_ONLY` | event date known, **no recorded public date** | Comtrade 608/608, Comext 1400/1400, HMRC 100/100, USAspending 245/245, 510(k) 160/160, PMA 60/60, MDALL 174/174 |

`EVENT_ONLY` is the dangerous class. It means "we know when the thing happened but
not when anyone could have seen it". **Any record in this class is ineligible for
historical-observability claims** and `hz.timeq.audit_clocks` refuses it. 2 687
records in the export are in that state — most of the trade and regulatory corpus.
That is a property of the sources, not a defect in the collection, and it is the
honest reason trade data cannot support early-signal research.

### 3.2 Date confusion cases actually encountered

| case | consequence | handling |
|---|---|---|
| EP INID 43 (application publication) vs INID 45 (grant) | using 43 for a grant misdates it by **up to 11.8 years** (EP2490731B1: 2012-08-29 vs 2024-06-05) | select by kind; both raw values stored |
| Filing date used as observation date | EP median publication−filing gap **1 738 days** (4.8 y), max 6 881 d; CIPO median **1 588 d**, max 6 861 d | `event_at` and `source_public_at` kept separate; gap recorded per record |
| CIPO has no publication date at all | pending applications would get a fabricated date under the 18-month rule | `source_public_at = NULL`, `MISSING_PUBLICATION_DATE`, rule stored as text only |
| CIPO PCT publication date | it is the *international* document's date, not the CA document's | stored as an attribute, never as `source_public_at` |
| cross-database publication date | **60 % of anchors disagree**, 36.7 % by >30 days | per-source dates preserved; no single date column asserted |
| registry posting vs submission | CT.gov median 8 d, max 892 d | both fields kept; lag measured, not collapsed |

### 3.3 Snapshot-only exposure

| source | snapshot-only share | meaning |
|---|---|---|
| CIPO Canada | 100 % | single quarterly extract ending 2022-02-28 |
| OpenAIR / Semantic Scholar / PubMed | 100 % | no creation or index timestamp at all |
| EPO publications | n/a | document as published; no version history |
| OpenAlex / Crossref / Europe PMC | partial | `created_date` / `created` / `firstIndexDate` present |

`SNAPSHOT_ONLY` records can support "what is true now" but not "what was knowable
then". 2 383 records in the export carry that flag.

---

## 4. Licences — one genuine problem the project owner must decide

| licence status | sources | notes |
|---|---|---|
| `open_licence` | CIPO Canada (OGL-Canada), Eurostat Comext, HMRC (OGL v3), OpenAlex (CC0), Europe PMC, OpenAIRE (CC-BY), FTS (OGL v3) | explicit reuse rights |
| `public_domain` | AccessGUDID, openFDA, ClinicalTrials.gov, NIH RePORTER, USPTO | US government works |
| `open_no_explicit_licence` | EPO publication server, Crossref, PubMed, Semantic Scholar, USAspending, TED | publicly readable, no stated reuse licence — we store derived records plus bounded hashed samples, not mirrors |
| **`terms_restricted`** | **UN Comtrade** | see below |
| `requires_registration` / `requires_licence` | OPS, USPTO ODP, PatentsView, Lens, Panjiva, ImportGenius, Descartes, EU CTIS | not acquired |

### The UN Comtrade conflict — needs a decision

UN Comtrade publishes a **public API** and its **Usage Agreement §5** states that
"any copying, automated browsing or downloading … [is] strictly prohibited
without the prior written permission of the United Nations".

That is a direct contradiction between the technical affordance and the licence.
This round's handling:

* a **bounded 22-request sample** was taken (608 records), not a bulk harvest
* the licence is recorded as `terms_restricted`
* **no RESEARCH claim is made from Comtrade data**
* the conflict is recorded in the registry entry and in `INDUSTRY_DATA_REPORT.md`

**Recommendation:** either obtain written permission from UNSD before operational
use, or drop Comtrade and rely on Eurostat Comext + HMRC, both of which are
explicitly open. This is a project-owner decision, not an engineering one.

Two further licence facts worth carrying forward:

* **USPTO terms explicitly discourage site-level bulk access** and direct bulk users
  to separately obtained bulk products — which is exactly why the keyed ODP route is
  the correct one and scraping the website is not.
* `opic-cipo.ca` (CIPO bulk host) serves an **incomplete TLS chain**. The fix used
  (`hz/tls.py`) fetches the missing intermediate from the leaf's own AIA pointer and
  still verifies against platform roots. Verification was never disabled.

---

## 5. Missing fields — what is absent, and whether it is fixable

| field | affected sources | fixable? |
|---|---|---|
| publication/open-to-inspection date | CIPO pending applications (4 212 records) | yes — acquire the CIPO IPC/status table or a later extract with more status detail; **do not** compute from the 18-month rule |
| technology classification (IPC) | **CIPO, all 19 702 records** | yes — the `PT_IPC_classification` table is open and published; it was **deliberately not downloaded** because it exceeded 230 MB per range split. This is the top acquisition gap to close |
| filing date | CIPO 9 033 records (pre-1900 filings store `-1`) | no — the source does not have it |
| recorded public date | 2 687 trade/regulatory records | no — the sources do not disclose it |
| applicant/proprietor | EPO 1 record (sitemap-only, no front page) | yes — one more fetch |
| abstract | EPO where the front page had none | yes |
| claims text | EPO (present in HTML, unparsed) | yes — no new access needed |
| patent family ID | EPO, CIPO | no — requires OPS/INPADOC or Lens |
| legal status | EPO, CIPO | CIPO has `Application Status Code`; EPO needs OPS |

---

## 6. Integrity guarantees that were actually enforced

* Every raw sample is stored **verbatim** with a SHA-256 in `PROVENANCE.json`.
* The export validates each row against `horizon.evidence.v1`; the build **fails**
  rather than writes on a schema violation. 6 492 exported records, 0 violations (19 930 patent records acquired; the CIPO slice is exported as a bounded stratified sample).
* File-level SHA-256 is verified at export time (`verify` re-hashes every file and
  compares with the manifest).
* Closed vocabularies are enforced in code for `entity_type`, `identity_status`,
  `evidence_status`, `licence_status`, `access_state` and `quality_flags`. An
  unknown flag is a build error, not a note.
* The registry refuses `auth_required=True` together with `access_state="OPEN"`,
  and refuses a blocked/registered source with no recorded `unlock_route`.
* One self-inflicted bug was found and fixed mid-round: `BoundedClient` cached on
  URL only, ignoring query params, which would have produced pages of one response
  relabelled as another. The industry workstream detected it; the cache key is now
  `(url, sorted params)`. The scholarly workstream's first probe run had been
  corrupted by it and was re-run; both workstreams re-verified their stored records
  against their queries.

---

## 7. Residual risks that no code check can remove

1. **The patent sample is small and unevenly spread.** 228 EP documents across 10
   weeks, with 179 of them in the two dense weeks. Three of five target firms have
   zero EP hits. That is a sampling outcome and must never be reported as "no
   patents".
2. **CIPO is firm-scoped, not technology-scoped.** Without the IPC table, "Philips
   13 508" includes lighting. Do not call these medical-device patents.
3. **Alias lists are curated judgements.** They are documented and marked
   `CANDIDATE`, but they are not records-verified entity links.
4. **Affiliation strings are not company identities.** 60 scholarly records are
   `UNKNOWN` for exactly this reason.
5. **CT.gov and CORDIS text fields are self-reported.** Where they contradict the
   paper, the paper wins and the conflict is recorded.
