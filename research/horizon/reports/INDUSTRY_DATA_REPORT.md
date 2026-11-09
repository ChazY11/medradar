# INDUSTRY / TRADE / PROCUREMENT — data report (HORIZON-001)

Workstream owner: INDUSTRY. Suite: `hz/suites_industry.py`.
Collection date: **2026-11-09T23:20Z – 2026-11-10T07:30Z** (all timestamps in
`PROBES.json`, `PROVENANCE.json` and `REQUEST_LOG.jsonl` are UTC).

Everything below is measured. Where a thing could not be measured, it says so.

---

## 0. The one paragraph that matters

**A trade flow is an aggregate.** Not one of the 1,408 trade series rows in this
workstream identifies a company, a brand, a product or a device. They say "the
United Kingdom imported £4.65 bn of HS 9018 goods in 2024"; they do **not** say
who made it, who sold it, or how much of it was a specific product. Every trade
record on disk carries `attributes.firm_attribution = "none"` and an
`attributes.aggregation_semantics` string, and the experiment asserts that zero
records violate this (`EXP_H4_INDUSTRY.json → cross_checks.trade_records_missing_aggregation_disclaimer = 0`).
Any analysis that treats these numbers as revenue, market share, R&D intensity or
firm-level adoption is wrong, and it is wrong by construction, not by accident.

The **only** firm-level evidence in this workstream comes from procurement
awards, and even there: a supplier is named (370 awards), a device *class* is
named (94 awards), a model-like token appears (11 awards), and a device
**manufacturer** is named in **zero** awards.

---

## 1. Per-source outcome — ACCESS / DATA / IDENTITY / RESEARCH

Four separate success levels. Nothing below promotes one into the next.

| source_id | access_state | licence_status | ACCESS | DATA | IDENTITY | RESEARCH | records |
|---|---|---|---|---|---|---|---|
| `un_comtrade` | OPEN_DOCUMENTED | terms_restricted | ✅ | ✅ | ❌ aggregate only | ⚠️ macro only | 608 |
| `eurostat_comext` | OPEN_DOCUMENTED | open_licence | ✅ | ✅ | ❌ aggregate only | ⚠️ macro only | 1,400 |
| `uk_hmrc_trade` | OPEN_DOCUMENTED | open_licence (OGL v3) | ✅ | ✅ | ❌ aggregate only | ⚠️ macro only | 100 |
| `us_census_trade` | REQUIRES_REGISTRATION | open_no_explicit_licence | ✅ | ❌ | ❌ | ❌ | 0 |
| `usaspending` | OPEN_DOCUMENTED | open_no_explicit_licence | ✅ | ✅ | ✅ **SAM UEI** | ✅ | 245 |
| `eu_ted` | OPEN_DOCUMENTED | open_no_explicit_licence | ✅ | ✅ | ⚠️ name only | ✅ | 299 |
| `uk_find_a_tender` | OPEN_DOCUMENTED | open_licence (OGL v3) | ✅ | ✅ | ⚠️ name + OCDS party id | ✅ | 62 |
| `sam_gov` | REQUIRES_REGISTRATION | open_no_explicit_licence | ✅ (404) | ❌ | ❌ | ❌ | 0 |
| `usitc_dataweb` | BLOCKED_TECHNICAL | unknown | ⚠️ SPA only | ❌ | ❌ | ❌ | 0 |
| `importyeti` | BLOCKED_LEGAL | terms_restricted | ✅ | ❌ (robots) | ❌ | ❌ | 0 |
| `importgenius` | BLOCKED_LEGAL | requires_licence | ✅ | ❌ (ToS) | ❌ | ❌ | 0 |
| `panjiva` | REQUIRES_LICENCE | requires_licence | ✅ | ❌ | ❌ | ❌ | 0 |
| `descartes_datamyne` | REQUIRES_LICENCE | requires_licence | ✅ | ❌ | ❌ | ❌ | 0 |

**Totals:** 2,714 records written; 6 of 13 sources yielded data; 4 sources are
paywalled/terms-blocked; 1 is keyed; 1 has no machine interface; 1 (Census) is now
keyed where the brief expected keyless.

---

## 2. Priority 1 — medical-device trade time series

### 2.1 What was actually collected

Bounded by design: **7 reporters × 4–5 HS4 codes × imports/exports × 2015–2024**,
plus one 12-month monthly slice. Not "all countries, all years".

| source | reporters | HS4 codes | years | series rows | unit |
|---|---|---|---|---|---|
| `un_comtrade` | 7 present of 8 requested | 9018, 9019, 9020, 9022 | 2015–2024 annual + 2025 monthly | 608 | USD |
| `eurostat_comext` | 7 present of 8 requested | 9018, 9019, 9020, 9021, 9022 | 2015–2024 | 700 values + 700 masses | EUR, 100 kg |
| `uk_hmrc_trade` | GB | 9018, 9019, 9020, 9021, 9022 | 2015–2024 | 100 | GBP |

Reporters requested: China (156), USA (842), Germany (276), France (250),
Japan (392), UK (826), Italy (380), Spain (724).
**France returned zero Comtrade rows for all four codes 2015–2024** — Comext
(FR) fills that gap. EU aggregate (`EU27_2020`, `EU`) returned no Comext values
for these products, so an EU total must be computed by the caller.

Monthly: the preview API allows **one reference period per request**
(`HTTP 400 "Maximum number of periods for preview is 1"`), so a 12-month slice
costs 12 requests. Only **one** of the two monthly reporters (USA, 842) actually
publishes monthly HS4 data; China returned nothing at monthly frequency for 2025.

Sample of the series, to show the data is real and sane (HS 9018, imports):

| year | China (USD bn, Comtrade) | UK (GBP bn, HMRC) | Germany (EUR bn, Comext) |
|---|---|---|---|
| 2015 | 6.07 | 2.50 | — |
| 2019 | 9.84 | 3.08 | — |
| 2021 | 12.62 | 3.02 | — |
| 2023 | 11.69 | 4.67 | 12.72 |
| 2024 | 11.22 | 4.65 | — |

(the full series is in `experiments/industry/evidence/*.jsonl`; `—` means the
cell was not printed here, not that it is absent — except Germany 2023 which is
printed and audited below.)

### 2.2 HS coverage table — what each code covers and what it wrongly sweeps in

Descriptions are quoted from the official nomenclatures fetched during the run
(Comtrade `HS.json`, HMRC `Commodity`, Comext dimension labels). The
"contaminates with" column is analyst commentary and is labelled as such inside
each record as `attributes.hs_scope_note`.

| HS4 | source description (verbatim, truncated) | what it wrongly sweeps in | verdict |
|---|---|---|---|
| **9018** | "Instruments and appliances used in medical, surgical, dental or veterinary sciences, incl. scintigraphic apparatus, other electro-medical apparatus and sight-testing instruments, n.e.s." | dental chairs, veterinary instruments, non-corrective ophthalmic instruments, sight-testing apparatus | usable as the broadest "medical instrument" proxy, **not** a device-class proxy |
| **9019** | "Mechano-therapy appliances; massage apparatus; psychological aptitude-testing apparatus; ozone therapy, oxygen, aerosol therapy, artificial respiration or other therapeutic respiration apparatus" | massage devices and consumer ozone/aerosol therapy equipment | **highest-value code for respiratory care** (ventilators live here, not in 9020) |
| **9020** | "Breathing appliances and gas masks, incl. parts and accessories (excl. protective masks having neither mechanical parts nor replaceable filters)" | industrial/consumer breathing apparatus | narrow; must be read **with** 9019 |
| **9022** | "Apparatus based on the use of X-rays or of alpha, beta, gamma or other ionising radiation, whether or not for medical, surgical, dental or veterinary uses…" | industrial radiography, security scanning, non-destructive testing | usable for imaging, contaminated by industrial NDT |
| **9021** | "Orthopaedic appliances, incl. crutches, surgical belts and trusses; splints and other fracture appliances; artificial parts of the body; hearing aids…" | prosthetics, orthotics, hearing aids — devices, but a different commercial category from capital equipment | collected from Comext + HMRC only (cost/benefit) |
| 3822 | diagnostic/lab reagents (not collected) | — | **not collected**: reagent trade is lab supply, not device adoption |
| 3002–3006 | pharmaceuticals (not collected) | — | **deliberately excluded**: pharma-adjacent, would swamp any device signal |
| 9402 | medical furniture (not collected) | — | not collected: furniture is a different market |
| 8504/8543 | power supplies / electrical machines (not collected) | — | **rejected**: `8543` alone covers a vast range of electrical apparatus; the signal-to-noise ratio is unusable |

**Two contamination traps worth stating explicitly:**

1. **9019 vs 9020.** Ventilators and oxygen-therapy apparatus sit in **9019**.
   Analysts commonly assume 9020 ("breathing appliances") is the ventilator code;
   it is not. Analysts assembling a "respiratory" aggregate must use 9019 + 9020.
2. **HS is a customs classification, not a market.** A single HS4 mixes
   capital equipment, consumables and consumer goods. There is no HS-level way to
   separate "a hospital MRI" from "a veterinary ultrasound".

### 2.3 Cross-source reconciliation (the check that would catch a mislabelled series)

Same cell, two independent compilations — Germany, HS 9018, imports, 2023:

* Comext: **€12,719,356,730** (value in euro)
* Comtrade: **US$13,359,445,208.52** (primary value, USD)
* implied USD/EUR = 1.0504, vs a 2023 annual average of roughly 1.08.

They are close but not equal — as expected, because they are different
compilations with different revision and rounding policies. The point of the
check is that **both cells are retrievable and comparable**, not that they agree.
A 20 %+ divergence would have been the signal that one of the series was
mislabelled. Recorded in `EXP_H4_INDUSTRY.json → cross_checks.de_9018_imports_2023`.

### 2.4 Time semantics — and a real limitation

`audit_clocks()` classification of every trade record:

| source | class | count |
|---|---|---|
| `un_comtrade` | EVENT_ONLY | 608 |
| `eurostat_comext` | EVENT_ONLY | 1,400 |
| `uk_hmrc_trade` | EVENT_ONLY | 100 |

**No trade source discloses when a given figure became public.** Comtrade returns
no release date; Comext exposes only a dataset-level `updated` timestamp; HMRC
exposes nothing per cell. Therefore every trade record has `source_public_at =
None` and carries `MISSING_PUBLICATION_DATE`. They are usable as *measurements*
and **unusable** as evidence of what was knowable at a point in time. No
observability-gap claim can be made from them.

---

## 3. Priority 2 — procurement: device-level awards

### 3.1 The stage table (closed vocabulary, never collapsed)

The brief's central warning is correct and this workstream enforces it. Every
procurement record carries `attributes["stage"]` from a closed vocabulary, and
`event_at` is the date **of that stage**:

| stage | what it means | sources where it occurs | records |
|---|---|---|---|
| `tender_published` | an opportunity was advertised | **none collected** | 0 |
| `contract_award` | a buyer decided to award; a supplier is named | USAspending, TED, UK FTS | 606 supplier relations / 370 awards |
| `contract_delivery` | goods/services actually delivered | **none of these sources exposes this** | 0 |
| `revenue` | money recognised by a company | **not observable from any source here** | 0 |

Verified assertion: `EXP_H4_INDUSTRY.json → cross_checks.procurement_stage_values_observed = ["contract_award"]`
and `collapsed_stage_values_present = []`. No record uses "procurement" as a
stage, and no record treats a published tender as an award.

### 3.2 USAspending — the only source reaching IDENTITY

* 3 keyless POSTs to `/api/v2/search/spending_by_award/` (PSC filter, NAICS
  filter, device-keyword filter), 100 rows each.
* **245 unique awards, 245/245 carry the recipient's SAM UEI** — an official
  identifier issued by GSA, not a name match. `identity_status = CONFIRMED`.
* 70 awards name a concrete device class in the award text; 11 carry a
  model-like token (e.g. `ABX`, `MX400`-style).
* PSC labels were taken from the official filter tree
  (`/api/v2/references/filter_tree/psc/?depth=3`, 382,700 B), **not from the
  brief** — and the brief was wrong:

| PSC | brief assumed | official label (verified) |
|---|---|---|
| 6510 | — | SURGICAL DRESSING MATERIALS |
| 6515 | "surgical dressing materials" | **MEDICAL AND SURGICAL INSTRUMENTS, EQUIPMENT, AND SUPPLIES** |
| 6520 | dental | DENTAL INSTRUMENTS, EQUIPMENT, AND SUPPLIES ✔ |
| 6525 | imaging | IMAGING EQUIPMENT AND SUPPLIES: MEDICAL, DENTAL, VETERINARY ✔ |
| 6530 | hospital furniture | HOSPITAL FURNITURE, EQUIPMENT, UTENSILS, AND SUPPLIES ✔ |
| 6540 | "medical/dental instruments" | **OPHTHALMIC INSTRUMENTS, EQUIPMENT, AND SUPPLIES** |
| 6545 | "reagents" | **REPLENISHABLE FIELD MEDICAL SETS, KITS, AND OUTFITS** |
| 6550 | — | IN VITRO DIAGNOSTIC SUBSTANCES, REAGENTS, TEST KITS AND SETS |

**PSC filtering does not yield devices.** Concrete counter-examples from the
saved responses:

* `W911QY20C0119` — ASTRAZENECA PHARMACEUTICALS LP, US$1,107,934,203.08,
  "SARS-COV-2 THERAPEUTIC AZD7442", NAICS 325412 (pharmaceutical preparation
  manufacturing) — filed under PSC **6550**.
* `W58P0522C0009` — IHEALTH LABS INC., US$1,774,999,987.20,
  "COVID-19 ANTIGEN TEST", NAICS 325413 (in-vitro diagnostic substance
  manufacturing) — filed under PSC **6515**.

Neither is a device purchase. A naive "PSC 6515+6550 ⇒ medical device market"
query would report a multi-billion-dollar device market that is mostly vaccines
and lateral-flow tests.

Award-date caveat: `spending_by_award` does **not** return the award action date
(requesting the field `"Action Date"` is accepted and returns `null`), so
`event_at` is the **period-of-performance start** and the record says so in
`attributes.event_at_semantics` plus `MISSING_FILING_DATE`.

### 3.3 EU TED — the previous round's BLOCKED verdict is **overturned, with scope**

The previous round skipped TED because "its search API returns notices without
award suppliers". That is true only for **legacy** notices. Measured today:

| question | measured answer | evidence |
|---|---|---|
| Is `POST /v3/notices/search` keyless? | **yes**, HTTP 200 | 4 POSTs, `REQUEST_LOG.jsonl` |
| Does it return winners? | **yes for eForms-era CANs** — `winner-name` is a multilingual map | e.g. `{"eng": ["Elis Norge AS (hovedenhet)"]}` |
| Does it return supplier identifiers? | **yes** — `winner-identifier` = national registration numbers (`"RO 29674809"`, `"827 181 88 28"`) | 91 of 102 notices |
| Legacy notices? | `winner-name = null`; `BT-768-Contract` returns only `[true]/[false]` presence | 2016 CANs |
| `GET /v3/notices/{pn}` (full notice)? | **REQUIRES_REGISTRATION** — `HTTP 400 "Missing Authorization header in request"` | probe `eu_ted_single_notice_auth` |
| Per-notice XML on ted.europa.eu? | **BLOCKED** — `HTTP 405` with an AWS WAF "Human Verification" interstitial | probe `eu_ted_notice_xml_waf` |

Result: **299 supplier rows from 102 award notices, 93 with supplier names, 19
naming a device class.**

Unlock route for the keyed/blocked part: register for a TED API key via the TED
Developer Portal (reachable from the docs index's "obtain an API key" section);
the keyed `GET /v3/notices/{pn}` then returns the full eForms payload including
BT-768 Contractor **with its identifier**.

**Two identity traps in TED, both of which this workstream refuses to paper over:**

1. `winner-name` and `winner-identifier` are **parallel lists of unequal length**
   (one entry per contract/lot, e.g. 4 names vs 6 identifiers in
   `741786-2025`). Their index alignment is not stated by the API. Zipping them
   would invent supplier identities, so identifiers are stored as an explicitly
   *unaligned* list and `identity_status = CANDIDATE`.
2. Placeholder identifiers exist (`"00000000"`). They are dropped.

### 3.4 CPV 33100000 is **not** a medical-device filter — measured

This is a trap the whole sector falls into, so it was measured rather than
asserted:

| query (12-month window, `notice-type=can-standard`) | `totalNoticeCount` |
|---|---|
| `classification-cpv=33100000` | **102** |
| `classification-cpv=33140000` | 33 |

The two are *not* disjoint additions (102 ≠ 102+33), and a sampled notice matched
by `33100000` carries `19260000` (leather), `98310000` (laundry services) and
`33199000` — none of which is "medical equipment". So the expert-search CPV
predicate matches **descendants**, and `33100000` behaves as the whole
medical / pharmaceutical / personal-care **division**, not as a device filter.
**40 of 102 sampled notices are CPV-mixed** (they contain non-medical codes), so
the award value on them is not a medical-device value.

### 3.5 UK Find a Tender — suppliers are present, but there is no filter

* keyless OCDS release packages; `stages=award&limit=100`.
* `awards[].suppliers[].name` **is** present (so the "no suppliers" worry does not
  apply to UK FTS), plus an OCDS party `id` such as `GB-FTS-8557`.
* The API accepts **only** `stages, limit, cursor, updatedFrom, updatedTo`.
  Probed with `keyword=medical` → `HTTP 400 "Request parameter 'keyword' is not
  recognised, allowed parameters are: stages, limit, cursor, updatedFrom, updatedTo"`.
  **There is no CPV or keyword filter**, so medical awards can only be found by
  scanning. This collection scanned 300 award-stage releases (3 pages):
  16 medical releases, **32 medical awards, 32/32 with a named supplier**,
  5 naming a device class, 10 suppliers with a legal identifier.
* The scan denominator is reported so the sample is interpretable: medical awards
  were 32 of 678 awards in the sampled window (~4.7 %). That share is the only
  statistic that generalises; the absolute counts are sample counts, not census
  counts.

---

## 4. Priority 3 — commercial bill-of-lading vendors: all four are unacquirable

The correct research conclusion here is *"company-level shipment data is
paywalled and must not be acquired"*, and it is documented rather than worked
around. No vendor data page was crawled; only the homepage, `robots.txt` and the
published legal/policy pages were read.

| vendor | finding | exact evidence |
|---|---|---|
| **ImportYeti** | `BLOCKED_LEGAL`. `robots.txt` allows page crawling but disallows every data endpoint: `Disallow: /api/addresses`, `Disallow: /api/ep`, plus `/search?q`, `/mx/`, `/us-export/`. The shipment records are served through exactly those paths. | `DATASETS/industry/importyeti/raw/robots.txt` (167 B, HTTP 200) |
| **ImportGenius** | `BLOCKED_LEGAL` + `REQUIRES_LICENCE`. ToS: *"You may not sell, transfer, assign, license, sublicense or modify any Content or reproduce, display, publicly perform, make a derivative work of, distribute or otherwise use any Content in any way for any purpose…"* and *"No other use is permitted without our prior written consent."* The API is enterprise-licensed: *"Enterprise API integration … enterprise-grade access."* | `terms_of_use.html` (103,460 B), `features/api-integration` (131,577 B) |
| **Panjiva** (S&P Global) | `REQUIRES_LICENCE`. Sold as a platform/feed (`Panjiva Platform`, `S&P Capital IQ Pro`, `XpressFeed`). The linked terms page itself is WAF-blocked: `HTTP 403` (2,008 B) — so **the licence text could not be read and is therefore not quoted**. | probe `spglobal_terms` = BLOCKED_AUTH 403 |
| **Descartes Datamyne** | `REQUIRES_LICENCE`. `descartes.com/datamyne` redirects to a corporate-acquisition page; `/legal-compliance` lists *"Descartes Online Subscription Terms for SaaS Services"* and an *"End User License Agreement (EULA)"*. | `legal_compliance.html` (353,715 B) |

**Does a free API exist?** No. ImportGenius sells one commercially; ImportYeti's
API paths are robots-disallowed; Panjiva and Descartes sell platform licences.

**Correct conclusion:** company-level US customs shipment data (which is the only
data that could attribute imports to a specific firm) is **not obtainable under a
licence this project can accept**. The aggregate substitutes (`un_comtrade`,
`eurostat_comext`, `uk_hmrc_trade`) **cannot** substitute for it: they are
country totals and say nothing about any company.

---

## 5. Priority 4 — the two "verify if keyed" sources

* **`sam_gov` → REQUIRES_REGISTRATION** (with a precise quote).
  `GET https://api.sam.gov/` and `GET /entity-information/v2/entities?api_key=test&samRegistered=Yes`
  both returned **HTTP 404 with a ZERO-byte body** — not a 401/403, so the
  failure signature is unusual and worth recording. The documented route
  (`https://open.gsa.gov/api/sam-entity-extracts-api/`, HTTP 200, 42,115 B)
  states: *"To access Public extracts: Users must have a non-Federal/Federal
  Individual (Personal) account and the respective API Key"*.
  Unlock: SAM.gov individual account → API key → Entity/Exclusions Extracts API.
* **`usitc_dataweb` → BLOCKED_TECHNICAL.** `https://dataweb.usitc.gov/` returns
  HTTP 200 (9,516 B) but the body is a JavaScript single-page-app shell with no
  data and no documented public API; `/login` returns the **identical** 9,516 B
  shell, so even the account gate could not be observed as HTML. No machine
  interface was demonstrated. The same statistics are reachable elsewhere
  (Census trade API with a key, or Comtrade).

---

## 6. Blockers, with exact HTTP evidence

| # | blocker | exact evidence | legitimate unlock route |
|---|---|---|---|
| B1 | **UN Comtrade terms prohibit automated download** | Usage Agreement §5: *"any copying, automated browsing or downloading, redistribution, publication, or commercial exploitation of any material … is strictly prohibited without the prior written permission of the United Nations"* (`DATASETS/industry/un_comtrade/raw/comtrade_license.html`) | written permission from the Director, UN Statistics Division; or a licensed Comtrade subscription (`https://comtradeplus.un.org`). The bounded research sample was taken under a *documented public API* whose terms conflict with that clause — the conflict is recorded, not resolved by assertion |
| B2 | Comtrade preview = **one period per request** | `HTTP 400 {"error":"Maximum number of periods for preview is 1"}` | keyed `/data/v1/get` (see B3) |
| B3 | Comtrade keyed path is keyed | `GET /data/v1/get/C/A/HS…` → **HTTP 401** (152 B) | subscription / registration |
| B4 | Comtrade **rate limit** | HTTP 429 on ~every second call at 1.5 req/s; recovered by bounded retry; practical ceiling ≈ 1 req/s | throttle to ≤1 req/s, or keyed tier |
| B5 | Comext has **no TSV/CSV output** | `format=TSV` and `format=CSV` → `HTTP 400 "Invalid value for 'wsOutputFormat' parameter"` | JSON-stat only |
| B6 | Comext has **no catalogue endpoint** | `/api/comext/dissemination/catalogue/datasets/` → **HTTP 404** (9 B) | DS codes must be known in advance |
| B7 | Comext bulk is UI-only | `/comext/newxtweb/` HTTP 200 but a 168,856 B JS app; **no bulk link in the served HTML** | use the dissemination API (as done) |
| B8 | **US Census trade API is now keyed** | `GET /data/timeseries/intltrade/imports/hs?…` → HTTP 200 but **redirected to `https://api.census.gov/data/missing_key.html`** (8,764 B) | free key: `https://api.census.gov/data/key_signup.html` (HTTP 200, 10,287 B); variable dictionary is keyless |
| B9 | USAspending **no action date** | field `"Action Date"` accepted, value `null` | `/api/v2/awards/{generated_internal_id}/` per award (1 request each) |
| B10 | TED full notice **keyed** | `GET /v3/notices/393130-2016` → `HTTP 400 "Missing Authorization header in request"` | TED Developer Portal API key |
| B11 | TED per-notice XML **WAF** | `GET ted.europa.eu/en/notice/393130-2016/xml` → `HTTP 405` + `awsWafCookieDomainList` / "Human Verification" | keyed API route |
| B12 | TED legacy notices have no winners | `winner-name = null`; `BT-768-Contract = [true]/[false]` only | none — legacy format limitation |
| B13 | TED identifiers **not aligned to names** | name list length ≠ identifier list length in the same notice | keyed full-notice fetch, which carries per-contract BT-768 |
| B14 | **CPV 33100000 is not a device filter** | 102 notices for the division code, matched notices carry `98310000`/`19260000`; 40/102 CPV-mixed | use subfamily codes (e.g. 33140000 → 33 notices) and accept that CPV ≠ device |
| B15 | UK FTS has **no filter parameters** | `HTTP 400 "Request parameter 'keyword' is not recognised, allowed parameters are: stages, limit, cursor, updatedFrom, updatedTo"` | scan + report the sampled denominator |
| B16 | UK FTS awards have **no date** | `awards[]` has no date field; `release.date` is publication | `contracts[].dateSigned` when present |
| B17 | HMRC OTS has **no world-total row** | raw OTS grain is `CommodityId × CountryId × PortId × MonthId × FlowTypeId` | server-side `$apply=filter()/groupby()` sum (as done) |
| B18 | HMRC splits EU/non-EU flows | FlowType 1/2 = EU import/export, 3/4 = non-EU | imports = 1+3, exports = 2+4 |
| B19 | `sam_gov` keyed, **404 not 401** | `GET api.sam.gov/` → HTTP 404, **0 bytes**; docs quote the account+key requirement | SAM.gov account → API key |
| B20 | `usitc_dataweb` no machine interface | `/` and `/login` both return the identical 9,516 B SPA shell | account + interactive export; or Census/Comtrade |
| B21 | ImportYeti robots-disallows the data | `Disallow: /api/addresses`, `Disallow: /api/ep` | operator permission only |
| B22 | ImportGenius ToS forbids reuse | quoted in §4 | paid commercial agreement |
| B23 | Panjiva terms page **403** | `GET spglobal.com/en/terms-of-use` → HTTP 403 (2,008 B) | human must read the terms before any use |
| B24 | Descartes = SaaS/EULA only | `/legal-compliance` lists Online Subscription Terms + EULA | subscription |

---

## 7. What is company-level vs aggregate — the summary table

| evidence type | count | identifies a company? | identifies a device? | identifies a device *manufacturer*? |
|---|---|---|---|---|
| Trade series rows | 1,408 | **no** (by construction) | no | no |
| Procurement awards with a named supplier | 370 | **yes** — name, plus SAM UEI for 245 | no | no |
| Supplier↔award relations | 606 | yes | no | no |
| Awards naming a concrete device *class* | 94 | yes | **class only, CANDIDATE** | no |
| Awards naming a model-like token | 11 | yes | **CANDIDATE** | no |
| Device↔award relations **CONFIRMED** | **0** | — | — | — |
| Device↔award relations **CANDIDATE** | 124 | yes | class-level | **no** |

`identity_status` across the 606 procurement rows: **CONFIRMED 255**
(245 USAspending via SAM UEI + 10 UK FTS with a published legal identifier),
**CANDIDATE 351** (TED names, FTS names without a legal identifier).

`evidence_status` across procurement: CONFIRMED 307 (the award facts),
CANDIDATE 299 (the TED supplier relations).

**Zero device↔award relations are CONFIRMED.** A plausible-looking pipeline that
claims "Baxter supplied device model X to hospital Y" cannot be built from any
source here: the award names the *supplier*, and the device text is a generic
class ("ventilator", "ultrasound"). Where a model-like token appears (11 cases)
it is matched by a regex, which is a lead for manual verification, not evidence.

---

## 8. Budget actually consumed

From `SOURCE_PROBES/industry/REQUEST_LOG.jsonl` (every GET and POST, including
exploratory scratch and re-runs):

* **270 logged request attempts** — 249 GET, **21 POST** (logged manually, each
  with a request-body sha256, because `hz.http.BoundedClient` is GET-only by
  contract)
* **26.86 MB** received
* outcomes: 191 OK, 79 HTTP_ERROR — of which the large majority are expected
  diagnostics (HTTP 400/405 evidence probes) and Comtrade HTTP 429 rate limits
* collection requests in the six data connectors: 22 + 8 + 11 + 4 + 4 + 3 = **52**
* bulk files preferred over pagination: Comtrade reference files (81 KB + 1.95 MB)
  and the USAspending PSC tree (383 KB) were each fetched once instead of
  paginating; HMRC was aggregated server-side (`$apply`) rather than downloading
  ~10^5 microcube rows.

---

## 9. Reproduce

```powershell
cd D:\DEPPSKK\worktrees\horizon-001\research\horizon
python -m hz.cli probe --suite industry --max-requests 70
python CONNECTORS\industry\_licence.py
python CONNECTORS\industry\un_comtrade.py
python CONNECTORS\industry\eurostat_comext.py
python CONNECTORS\industry\uk_hmrc_trade.py
python CONNECTORS\industry\usaspending.py
python CONNECTORS\industry\eu_ted.py
python CONNECTORS\industry\uk_find_a_tender.py
python experiments\industry\write_registry.py
python experiments\industry\run_experiment.py
python -m hz.cli verify
```

Offline afterwards: everything under `DATASETS/industry/` is verbatim bytes with
sha256 in `PROVENANCE.json`; the parsers re-read only those files if pointed at
them.

---

## 10. Two engineering findings the Lead must know

### 10.1 `hz.http.BoundedClient` memoises by URL and **ignores `params`**

`BoundedClient.get()` caches on `self._cache[url]` and does not include `params`
in the cache key (`hz/http.py`, line ~170). Consequence: a loop that varies only
`params=` silently replays the **first** response for every iteration. This was
caught here the hard way — the first pass of the Comtrade connector produced 560
annual rows that all carried the 2015 payload under 2015–2024 labels, and the
HMRC connector produced five identical HS4 child lists. Both connectors now bake
the query string into the URL and **read the period back out of the response**,
raising if it disagrees with the request. Any other workstream looping over
`params` is very likely producing mislabelled rows right now. `hz/` is outside
this workstream's write scope, so the fix belongs to whoever owns it.

### 10.2 `hz.schema.dedupe_key` is an *entity* key, not a row key

`dedupe_key` prefers a strong identifier, so all supplier rows of one TED notice
share `ted_publication_number:…`, and all award rows of one OCDS release share
`ocds_ocid:…`. Measured: `eu_ted` has 299 rows but 93 unique dedupe keys;
`uk_find_a_tender` has 62 rows but 16 unique keys. ATLAS must group on
`source_record_id` within these sources, or it will collapse distinct suppliers
into one row. This is defensible (the entity *is* the notice) but it must be
stated, not discovered downstream.

`python -m hz.cli verify` currently reports `ok: false` for one reason outside
this workstream: `SOURCE_PROBES/regulatory/` has a `REQUEST_LOG.jsonl` but no
`PROBES.json`. The `industry` suite reports `ok`.
