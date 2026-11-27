# GLOBAL_SOURCE_DEEP_AUDIT

**HORIZON-001 · 51 sources audited · verified 2026-11-10**

This is the per-source audit behind every dataset in `exports/horizon-2026-11-10`.
It replaces "we looked at 59 sources" with a register where each source states what
access it grants, what licence governs reuse, what it actually added, and — where it
added nothing — the exact technical or legal blocker and the legitimate unlock route.

The register is machine-readable: one file per source under `registry/sources/` (51 entries), validated by `python -m hz.cli verify`, which currently returns `ok: true` with 0 issues. The tables below are generated from it.

**Access posture across 51 sources**

| state | n | meaning |
|---|---|---|
| `OPEN_DOCUMENTED` | 24 | keyless, machine-readable, documented |
| `OPEN` | 2 | keyless, machine-readable, possibly undocumented |
| `BLOCKED_TECHNICAL` | 8 | WAF / retired host / broken endpoint |
| `REQUIRES_REGISTRATION` | 7 | free key or account needed |
| `MANUAL_ONLY` | 6 | human interface only |
| `REQUIRES_LICENCE` | 2 | commercial product |
| `BLOCKED_LEGAL` | 2 | terms forbid automated reuse |

**Licence posture**

| licence | n |
|---|---|
| `open_licence` (explicit reuse rights) | 10 |
| `public_domain` | 10 |
| `open_no_explicit_licence` | 10 |
| `terms_restricted` | 8 |
| `requires_licence` | 3 |
| `unknown` | 10 |

Only **20 of 51** sources have a licence that unambiguously permits
reuse. That is the real constraint on building a data asset, and it is the number
that matters — not the source count.

---

## 1. The full register

| source_id | access | licence | bulk | verified | what it adds |
|---|---|---|---|---|---|
| `cipo_canada` | OPEN_DOCUMENTED | open_licence | Y | 2026-11-10 | Second patent jurisdiction **and** an explicit open licence; uniquely carries an ownership timeline (Owner Enable / Ownership End dates) with 1869–2022 depth |
| `epo_publication_server` | OPEN_DOCUMENTED | open_no_explicit_licence | Y | 2026-11-10 | The only keyless channel yielding applicant-of-record, inventor, IPC, CPC, filing date, publication date, priority and abstract for real EP patents |
| `accessgudid` | OPEN_DOCUMENTED | public_domain | Y | — | UDI-DI as the strongest US product identifier, plus brand/model/company |
| `openfda_device_510k` | OPEN_DOCUMENTED | public_domain | Y | — | Clearance numbers, device class, product codes, decision dates |
| `openfda_device_pma` | OPEN_DOCUMENTED | public_domain | Y | — | PMA approvals for the highest-risk devices |
| `openfda_device_classification` | OPEN_DOCUMENTED | public_domain | Y | — | Product-code → regulation/class map, the join spine for US devices |
| `openfda_device_registrationlisting` | OPEN_DOCUMENTED | public_domain | Y | — | Establishment registration + device listing (who makes what, where) |
| `canada_mdall` | OPEN_DOCUMENTED | open_licence | Y | — | Canadian device licences: licence number, device name, model, manufacturer, licence dates |
| `brazil_anvisa` | OPEN_DOCUMENTED | open_no_explicit_licence | Y | — | A third regulatory jurisdiction (partial coverage; see report) |
| `openalex` | OPEN_DOCUMENTED | open_licence (CC0) | Y | 2026-11-09 | The only source here with a per-work index-creation timestamp; definitional for the anchor set |
| `crossref` | OPEN_DOCUMENTED | open_no_explicit_licence | Y | 2026-11-09 | The only source where the creation timestamp is a **registry event** (DOI registration), not an index event |
| `europepmc` | OPEN_DOCUMENTED | open_licence | Y | 2026-11-09 | Best identifier convergence (doi+pmid+pmcid on one record) and richest grant surface |
| `pubmed_eutils` | OPEN_DOCUMENTED | open_no_explicit_licence | Y | 2026-11-09 | The authoritative PMID↔DOI edge and the GrantList |
| `semantic_scholar` | OPEN_DOCUMENTED | open_no_explicit_licence | Y | 2026-11-09 | Only source exposing an ArXiv identifier; carries pmid/pmcid too |
| `openaire` | OPEN_DOCUMENTED | open_licence (CC-BY) | Y | 2026-11-09 | The only source that de-duplicates works across repositories; surfaced multi-DOI records |
| `clinicaltrials_gov` | OPEN_DOCUMENTED | public_domain | Y | 2026-11-09 | The only trial registry that answered: 185 references, 179 with PMID, plus submission and posting dates |
| `nih_reporter` | OPEN_DOCUMENTED | public_domain | Y | 2026-11-09 | The only open grant registry resolving a declared grant number to a specific project |
| `eu_cordis` | OPEN | open_no_explicit_licence | – | 2026-11-09 | EU project identity (RCN + grant agreement id); **no publication index**, so EU grant→paper is not buildable |
| `eu_ted` | OPEN_DOCUMENTED | open_no_explicit_licence | Y | 2026-11-09 | 299 supplier rows from 102 eForms-era EU award notices; 91 carry national registration numbers |
| `uk_find_a_tender` | OPEN_DOCUMENTED | open_licence (OGL v3) | Y | 2026-11-09 | 62 UK award-supplier rows for medical CPV codes, from scanning 300 award releases |
| `usaspending` | OPEN_DOCUMENTED | open_no_explicit_licence | Y | 2026-11-09 | 245 federal awards with recipients pinned by SAM UEI (245/245) — the only procurement identity success |
| `un_comtrade` | OPEN_DOCUMENTED | **terms_restricted** | – | 2026-11-09 | 608 country-total medical-HS4 observations. **Licence conflict — see §4** |
| `eurostat_comext` | OPEN_DOCUMENTED | open_licence | – | 2026-11-09 | 1 400 Comext observations (value EUR + net mass) for 7 EU reporters |
| `uk_hmrc_trade` | OPEN_DOCUMENTED | open_licence (OGL v3) | Y | 2026-11-09 | 100 UK annual aggregates in GBP for medical HS4 codes |
| `ip_australia` | OPEN_DOCUMENTED | open_licence | Y | 2026-11-10 | Catalogue is open but holds statistics, not patent texts — low marginal value, recorded as such |
| `eu_ctis` | REQUIRES_REGISTRATION | unknown | – | 2026-11-09 | Zero rows. Recorded negative, not replaced with a guess |
| `uspto_open_data_portal` | REQUIRES_REGISTRATION | public_domain | Y | 2026-11-10 | The authoritative US patent corpus once keyed |
| `sam_gov` | REQUIRES_REGISTRATION | open_no_explicit_licence | Y | 2026-11-09 | Would confirm contractor identity; keyed |
| `us_census_trade` | REQUIRES_REGISTRATION | open_no_explicit_licence | Y | 2026-11-09 | No longer keyless (corrects the previous round) |
| `epo_ops` | REQUIRES_REGISTRATION | terms_restricted | Y | 2026-11-10 | Would add applicant/inventor **search**, citations and family IDs |
| `lens_org` | REQUIRES_REGISTRATION | terms_restricted | – | 2026-11-10 | Cross-office citation and family data once tokenised |
| `panjiva` | REQUIRES_LICENCE | requires_licence | – | 2026-11-09 | Commercial S&P product; terms page itself WAF-blocked |
| `descartes_datamyne` | REQUIRES_LICENCE | requires_licence | – | 2026-11-09 | SaaS/EULA only |
| `importgenius` | BLOCKED_LEGAL | requires_licence | – | 2026-11-09 | ToS forbids reuse; API is enterprise-contractual |
| `importyeti` | BLOCKED_LEGAL | terms_restricted | – | 2026-11-09 | robots.txt disallows `/api/addresses` and `/api/ep` |
| `patentsview` | BLOCKED_TECHNICAL | unknown | – | 2026-11-10 | **Retired**: hosts no longer resolve or return the ODP shell; bulk bucket closed |
| `uspto_bulkdata` | BLOCKED_TECHNICAL | public_domain | – | 2026-11-10 | Legacy keyless bulk host gone |
| `espacenet` | BLOCKED_TECHNICAL | terms_restricted | – | 2026-11-10 | AWS WAF challenge — treated as an anti-automation control, not circumvented |
| `epo_linked_open_data` | BLOCKED_TECHNICAL | unknown | – | 2026-11-10 | API root 500; disallowed paths not crawled |
| `epo_global_patent_index` | BLOCKED_TECHNICAL | unknown | – | 2026-11-10 | Sitemap advertised in robots.txt does not resolve |
| `jpo_bulk` | BLOCKED_TECHNICAL | unknown | Y | 2026-11-10 | Every JPO page 403 from this host (geo/UA filtering) |
| `usitc_dataweb` | BLOCKED_TECHNICAL | unknown | – | 2026-11-09 | SPA shell only; no machine interface demonstrated |
| `dpma_open_data` | MANUAL_ONLY | unknown | Y | 2026-11-10 | Register UI reachable; documented open-data path not found at the URL tried |
| `wipo_patentscope` | MANUAL_ONLY | terms_restricted | – | 2026-11-10 | Stateful JSF app; no anonymous machine interface |
| `google_patents` | MANUAL_ONLY | terms_restricted | Y | 2026-11-10 | Bulk needs BigQuery + billing account; site scraping not attempted |

---

## 2. Sources whose verdict **changed** this round

These matter more than the sources we merely re-confirmed, because a stale verdict
is worse than no verdict.

| source | previous verdict | this round | evidence |
|---|---|---|---|
| **EU TED** | *blocked — search API returns notices without suppliers* | **open for eForms-era award notices** | `POST api.ted.europa.eu/v3/notices/search` is keyless and returns `winner-name` **and** `winner-identifier` (national registration numbers, 91/102 notices). Legacy 2016 CANs return null. Full notice retrieval and per-notice XML **are** keyed/ WAF (`400 Missing Authorization header`; `405` + WAF). So: partially open, precisely characterised |
| **PatentsView** | *investigated, needs key* | **retired** | `api.patentsview.org` returns the ODP SPA shell (20 666 B, no `patents` key); `search.patentsview.org`, `ped.uspto.gov`, `assignment-api.uspto.gov` and `bulkdata.uspto.gov` **no longer resolve**; PatentsView bulk S3 → 403 |
| **US Census trade** | *keyless for limited use* | **keyed** | HS endpoint 200 but redirects to `/data/missing_key.html` |
| **CPV 33100000** | *medical-device filter* | **not a device filter** | measured: `33100000` → 102 notices, `33140000` → 33, and matched notices carry `98310000` (laundry) and `19260000` (leather) |
| **PSC mapping in the brief** | 6515=dressings, 6540=dental, 6545=reagents | **wrong on 3 of 6** | verified from the official filter tree: 6515 = MEDICAL AND SURGICAL INSTRUMENTS, **6540 = OPHTHALMIC**, **6545 = REPLENISHABLE FIELD MEDICAL SETS** (reagents is 6550) |
| **EPO publication server** | *not investigated* | **the patent breakthrough** | sitemap advertised in the operator's own robots.txt; 227/228 records carry applicant, 228/228 carry both dates |
| **CIPO Canada** | *not investigated* | **second patent corpus, explicit open licence** | OGL-Canada, 19 702 firm-scoped records, ownership timeline |

---

## 3. Methodological traps this audit found (each one had a real cost)

1. **EPO IPC compaction.** The sitemap writes `A61M0005142`, not `A61M 5/142`.
   Parsing it as 4+6 digits instead of 4+4+rest silently zeroes the entire
   medical-device filter — which is what happened on the first run (0 medtech out of
   37 989 publications). Verified against the front page and fixed.
2. **Comma-delimited assumption for CIPO.** The CSVs are **pipe**-delimited with a
   bilingual header (`Patent Number - Numéro du brevet`). Reading them as CSV yields
   one giant column and zero rows. Delimiter is now sniffed, header split at ` - `.
3. **`csv.field_size_limit`.** The CIPO party table contains a field above the 128 KiB
   default; the parser raises rather than truncates, and the limit is raised
   explicitly.
4. **HTTP cache key.** `BoundedClient` cached on URL only, ignoring query params, so
   any loop varying only `params` replays the first response under later labels.
   Found by the industry workstream, fixed to `(url, sorted params)`, and both
   affected workstreams re-verified their stored records against their queries.
5. **GET-only client.** NIH RePORTER answers `405` to GET and needs POST;
   Semantic Scholar's batch endpoint silently returns `{paperId,title}` only unless
   `fields` is passed as a **query** parameter. Both are documented as traps.
6. **A 200 that carries nothing.** EU CTIS `/retrieve/<n>` returns **HTTP 200 with a
   2-byte `{}`**. A connector that keys off status code alone logs "found".
7. **`pid=doi:<doi>` returns zero on OpenAIRE**; only the bare DOI resolves. PubMed
   needs DOIs double-quoted before `[doi]`, otherwise a 60-DOI OR query silently
   returns 10 of 37 hits.

---

## 4. Decision required from the project owner

**UN Comtrade.** Its public API and its licence disagree. Usage Agreement §5 states
that "any copying, automated browsing or downloading … [is] strictly prohibited
without the prior written permission of the United Nations". A bounded 22-request
sample was taken, the licence is recorded as `terms_restricted`, and **no research
claim rests on it**. Options:

1. request written permission from UNSD, or
2. drop Comtrade and rely on Eurostat Comext + UK HMRC, which are explicitly open
   (`open_licence`, OGL-compatible) and already cover the same HS codes for EU/UK
   reporters.

Recommendation: option 2 for the base layer, option 1 only if non-EU reporters
become important.

**Second decision: two free API keys.** `https://developers.epo.org/` (EPO OPS) and
`https://data.uspto.gov/apis/getting-started` (USPTO ODP) are free registrations
that the project owner can complete in minutes. They unlock the two largest
currently-blocked corpora — including patent families, citations and US assignees.
HORIZON did not register accounts on the owner's behalf.

---

## 5. What "38 sources" actually bought

| outcome | sources |
|---|---|
| produced usable records in the export | **24** |
| verified open but no records taken (low value or size budget) | 2 (`ip_australia`, `openfda_bulk_download`) |
| clean negatives with an unlock route (keyed) | 6 |
| clean negatives (technically blocked) | 7 |
| clean negatives (legal/commercial) | 4 |

The number worth quoting is not 51. It is **24 sources delivered data, 20 have licences that unambiguously permit reuse, and 2 of those required real engineering to exercise at all** (EPO sitemap semantics, CIPO TLS chain). A further 2 channels would open with a five-minute free registration, and those two are the largest.
