# REGULATORY_FRONTIER_REPORT

**HORIZON-001 · global medical-device regulatory data · verified 2026-11-10**

This report answers one question per jurisdiction: **can machine-readable official
device records be obtained lawfully, and do they carry an identifier strong enough
to resolve product identity?**

It is not a list of countries. Seven sources produced records; six produced a
precise, actionable negative. The scientific result — in §5 — is that **cross-national
device identity is not solvable from official registries alone**, because the
registries do not share an identifier namespace.

All numbers come from `exports/horizon-2026-11-10/MANIFEST.json` and the probe logs
in `SOURCE_PROBES/regulatory/`.

---

## 1. What was acquired

| source | jurisdiction | records | official identifier | with identifier | with public date | with event date | licence |
|---|---|---|---|---|---|---|---|
| `accessgudid` | US (NLM/FDA) | **320** | **UDI-DI / GTIN** | 320 (100 %) | **320 (100 %)** | 0 | public domain |
| `openfda_device_510k` | US (FDA) | **160** | **K number** + product code | 160 (100 %) | 0 | 160 (100 %) | public domain |
| `openfda_device_pma` | US (FDA) | **60** | **PMA number** + product code | 60 (100 %) | 0 | 60 (100 %) | public domain |
| `openfda_device_classification` | US (FDA) | **60** | product code + CFR regulation | 60 (100 %) | 0 | 0 | public domain |
| `openfda_device_registrationlisting` | US (FDA) | **60** | FEI + registration number | 60 (100 %) | 0 | 0 | public domain |
| `canada_mdall` | Canada (Health Canada) | **174** | **device licence number** + MDALL device id | 174 (100 %) | 0 | 174 (100 %) | **open_licence (OGL-Canada)** |
| `brazil_anvisa` | Brazil (ANVISA) | **120** | registro + processo | 120 (100 %) | **120 (100 %)** | 120 (100 %) | open, no explicit licence |
| **total** | | **954** | | **954 (100 %)** | 440 | 514 | |

**Every acquired record carries a source-issued official identifier.** That is the
one thing this corpus does well, and it is why it is worth keeping even though the
coverage is small.

A second point worth stating plainly: **440 records have a recorded public date and
514 have a recorded event date, but only the Brazilian set has both.** So the
regulatory corpus is usable for *identity* work and for *event timelines*, but only
partially usable for *observability* work.

---

## 2. Per-jurisdiction depth

### 2.1 United States — deepest, and the only place with a real publication clock

**AccessGUDID** (`https://accessgudid.nlm.nih.gov/api/v3/...`, keyless)

| property | value |
|---|---|
| machine interface | REST JSON: `/devices/lookup.json` by `di`, `udi`, `record_key`; `/devices/history.json`; `/devices/snomed.json`; `/devices/parse_udi.json`; `/devices/implantable/{list,download}` |
| bulk | yes — full / monthly / weekly / daily ZIP releases of GUDID XML |
| historical depth | dated daily/weekly/monthly **delta archives**; each record exposes `publicVersionNumber`, `publicVersionDate` and `devicePublishDate`; superseded versions are not served as separate files |
| licence | public domain (US federal dataset, redistributed by NLM) |

This is the strongest **identifier** source in the whole round: 320/320 records carry
a UDI-DI, and the UDI-DI is issued by the manufacturer under an accredited issuing
agency (GS1 etc.), not assigned by us. It is also the only regulatory source with a
genuine **publication clock** (`devicePublishDate`), which is why all 320 records are
`PUBLICATION_ONLY` rather than `EVENT_ONLY`.

**openFDA device family** (`https://api.open.fda.gov/device/...`, keyless at low volume)

* `510(k)` — 160 records, `k_number` + `product_code`, `decision_date` as `event_at`.
  Live totals observed for the five target firms: MEDTRONIC 1,588 · GE 1,036 ·
  PHILIPS 994 · DRAGER 34 · MINDRAY 180.
* `PMA` — 60 records; `supplement_number` distinguishes original approvals from
  supplements, which matters because counting supplements as approvals inflates the
  approval count.
* `classification` — 60 records; product code → regulation number → device class.
  This is the **join spine**: product codes are how a 510(k), a PMA, a registration
  and a GUDID record can be related without name matching.
* `registrationlisting` — 60 records; establishment (FEI) + registration number +
  product codes. Answers "who makes what, where" at establishment level.
* `bulk_download` — catalogue reachable (`/download.json`), but **the device exports
  exceed this round's byte budget**, so only the catalogue was taken. Honest state:
  ACCESS yes, DATA no.

Licence: openFDA states its content is public domain / CC0 1.0 unless otherwise noted.

**Limit:** none of the openFDA device endpoints expose a record-publication date, so
all of them are `EVENT_ONLY`. A 510(k) decision date is when FDA decided; it is not
when a competitor could have read the decision.

### 2.2 Canada — a real open licence and a retention model the US lacks

**MDALL** (`https://health-products.canada.ca/api/medical-devices/...`, keyless)

| property | value |
|---|---|
| machine interface | REST JSON/XML: `licence/`, `company/`, `device/`, `deviceidentifier/`, `licencetype/`, `sbdlocation/`; params `id`, `state` (`active`\|`archived`), `licence_name`, `company_id`, `device_name`, `licence_number`, `device_identifier`, `lang`, `type` |
| licence | **Open Government Licence – Canada** (dataset `c801a084-210b-4cd2-8513-26a00b66eb6f`), i.e. explicit reuse with attribution |
| historical depth | **two states**: `active` (no cancellation date) and `archived` (carries `end_date`). Cancelled licences are retained, and per-device / per-identifier first and end dates are published |
| identifiers | `hc_device_licence`, `hc_mdall_device_id`, `hc_mdall_device_identifier` |

The archive state is genuinely useful and is *better* than the US position: a
researcher can see that a licence existed and when it ended, rather than only the
current snapshot.

**But MDALL has no publication clock and no status-change date.** We know a licence
exists and when it ended; we do not know when it first became publicly visible. All
174 records are `EVENT_ONLY`.

Two access constraints found by measurement:
* `licence?company_id=N` is **unbounded** for large firms — a read timeout was
  observed on Medtronic `company_id 114663`.
* `device?licence_number=N` is documented but unscoped — every call returned >2.5 MB.

So MDALL is open but not cheaply pageable; the 174-record slice is a deliberate
bounded sample, not the full corpus.

### 2.3 Brazil — partial, and why

ANVISA publishes bulk CSV from an h5ai directory index with no key and no login.
Row-level dates exist (`DT_INICIO_VIGENCIA`, `DT_VENCIMENTO_REGISTRO`, `DT_CARGA_ETL`),
so Brazilian records are the only regulatory records in this round with **both** clocks.

**Blocker:** the server caps HTTP Range responses at **256 KiB**, so only a 256 KiB
prefix (902 rows scanned → 120 records in scope) was sampled. The full file is outside
this round's budget. Licence is `open_no_explicit_licence` — the portal states no
licence, and inventing one would be wrong.

Note `DT_CARGA_ETL` is an **ETL load stamp**, not a public-availability date. It is
recorded as an attribute, never as `source_public_at`.

### 2.4 Jurisdictions that produced a precise negative

| jurisdiction | source | outcome | exact evidence | lawful unlock route |
|---|---|---|---|---|
| **EU** | EUDAMED | `REQUIRES_REGISTRATION` | public API paths return **HTTP 429** with an explicit anti-scraping instruction directing machine users to the official data API | register at the EU Health Data Lake developer portal (`developer.datalake.sante.service.ec.europa.eu`), subscribe to the EUDAMED API, call with the subscription key |
| **Australia** | TGA ARTG | `BLOCKED_TECHNICAL` | `www.tga.gov.au` resets/closes the TCP connection from this host (`RemoteDisconnected`, then `ConnectionResetError 10054`); **no ARTG dataset on data.gov.au** (verified via CKAN `package_search`) | human search at `tga.gov.au/resources/artg`; machine access via TGA data request |
| **Japan** | PMDA | `MANUAL_ONLY` | HTML indexes and PDFs only; no machine endpoint | no keyless API exists; commercial agreement or index scraping |
| **UK** | MHRA | `MANUAL_ONLY` | **no public per-device UK registration register exists as open data**; GOV.UK content API serves guidance/alerts pages only | FOI request to MHRA for company-level registration data |
| **China** | NMPA UDI | `MANUAL_ONLY` | `www.nmpa.gov.cn` answers **HTTP 412** with a JS challenge; `udi.nmpa.gov.cn` is a Chinese-language web query app | no official keyless API; human query or commercial vendor |

The EUDAMED result is the most consequential of these. The EU device database is the
single most valuable missing jurisdiction for a European-facing medtech project, and
the block is **not** a technical accident: the API tells automated clients to go and
register. That is a policy gate with a documented, free route.

---

## 3. What the official identifiers actually are

This is the part that determines whether the data can resolve identity.

| identifier | issued by | scope | shared with any other registry here? |
|---|---|---|---|
| UDI-DI / GTIN | manufacturer, under an accredited issuing agency (GS1…) | global in principle | **no** — MDALL, ANVISA do not key on it |
| 510(k) K number | FDA | US only | no |
| PMA number | FDA | US only | no |
| product code | FDA | US only | no |
| FEI / registration number | FDA | US establishment | no |
| Health Canada device licence number | Health Canada | Canada only | no |
| MDALL device id / device identifier | Health Canada | Canada only | no |
| ANVISA registro / processo | ANVISA | Brazil only | no |

**The UDI-DI is the only identifier in this table that is global by design**, because
it is minted under an international issuing-agency system. Every other identifier is
jurisdiction-local. That asymmetry is the whole story of §5.

---

## 4. Time semantics of the regulatory corpus

| source | recorded public date? | recorded event date? | clock class | consequence |
|---|---|---|---|---|
| `accessgudid` | **yes** (`devicePublishDate`) | no | `PUBLICATION_ONLY` | can date when a UDI record became visible |
| `canada_mdall` | no | yes (licence dates) | `EVENT_ONLY` | cannot date when the licence became knowable |
| `openfda_device_510k` | no | yes (`decision_date`) | `EVENT_ONLY` | decision ≠ observable |
| `openfda_device_pma` | no | yes | `EVENT_ONLY` | same |
| `openfda_device_classification` | no | no | `EVENT_ONLY` | reference table, no clock at all |
| `openfda_device_registrationlisting` | no | no | `EVENT_ONLY` | current snapshot, `reg_expiry_date_year` only |
| `brazil_anvisa` | yes (`DT_INICIO_VIGENCIA`) | yes | `FULL_TWO_CLOCK` | only full-two-clock regulatory source |

Two specific hazards:

1. **`decision_date` is not an observability date.** Using it as one would let a study
   "see" an approval on the day FDA signed it, which is not when the market or a
   competitor could read it.
2. **`DT_CARGA_ETL` is a pipeline stamp**, not a public date. It is stored as an
   attribute so it cannot be mistaken for a clock.

---

## 5. EXP-H2 — can a US and a Canadian record be shown to be the same product?

712 candidate pairs were generated from 320 GUDID × 174 MDALL records against a
pre-registered selection rule, then scored on five signals of increasing strength.

| verdict | n |
|---|---|
| **CONFIRMED** | **0** |
| REJECTED | 387 |
| UNKNOWN | 325 |

**`S4_official_identifier_fired = 0`.**

| signal combination | pairs | CONFIRMED | REJECTED | UNKNOWN |
|---|---|---|---|---|
| S2 + S3 + S5 | 5 | 0 | 5 | 0 |
| S2 + S3 | 93 | 0 | 35 | 58 |
| S2 + S5 | 156 | 0 | 156 | 0 |
| S2 alone (shared model token, 445 fired) | — | 0 | 387 | 58 |
| S3 alone (same firm, 365 fired) | — | 0 | 40 | 325 |
| S1+S2+S3 (strongest non-identifier combination) | — | **0** | — | — |

Hard negatives: 12 pairs built by the stated rule `HN4_subsidiary_vs_parent`; all 12
land in `UNKNOWN`, which is the correct outcome — the purpose of a hard negative is
that it must not be silently matched.

### The finding

**GUDID and MDALL share no identifier namespace.** UDI-DI is not present in MDALL;
Health Canada licence and device numbers are not present in GUDID. There is therefore
**no keyless official-identifier bridge between the two registries**, and no
combination of name, model token and firm — the strongest evidence obtainable without
a shared identifier — ever produces a confirmation.

This matters beyond these two countries: if the two best-documented device registries
in the world cannot be joined on an official identifier, then no pair of national
registries can. The identity layer cannot be built by matching harder. It has to be
built by importing **non-registry** bridging evidence, for example:

* the UDI-DI appearing in procurement text, recall notices, or manufacturers' own
  labelling;
* PCT priority links for patent-side attribution;
* manufacturer cross-reference filings that name both jurisdictions' numbers.

Naming that as the design constraint is the useful output of this experiment, and it
is the question `ATLAS_HANDOFF.md` puts back to ATLAS-001.

---

## 6. What this corpus enables, and what it does not

**Enables**

* A registry of real, officially identified devices for four of the five target firms
  in three jurisdictions (US, CA, BR).
* Product-code–driven joins *within* the US system across 510(k), PMA, classification
  and registration — this is a genuine, working join spine and needs no fuzzy matching.
* Establishment-level "who manufactures what" via FEI + registration listing.
* A five-firm 510(k) volume baseline (Medtronic 1,588 · GE 1,036 · Philips 994 ·
  Dräger 34 · Mindray 180) as measured totals, not estimates.

**Does not enable**

* Cross-national product identity. Measured above: 0 confirmations, no shared key.
* Observability-timeline claims for any jurisdiction except GUDID and Brazil.
* Historical version diffs except via GUDID's dated delta archives and MDALL's
  archived state.
* Any statement about EU, AU, JP, UK or CN device populations — those are negatives,
  not zero counts.

---

## 7. Ranked next steps

1. **Get the EUDAMED developer subscription.** It is the largest missing jurisdiction
   and the block is a documented, free registration gate rather than a technical wall.
   This is the single highest-value regulatory unlock available.
2. **Use UDI-DI as the intended bridge and hunt for it outside the registries.** The
   experiment says the registries will not provide the join; procurement text, recalls
   and manufacturer labelling might. That is a concrete, testable hypothesis rather
   than "improve matching".
3. **Take the openFDA device bulk exports** when the byte budget allows — the catalogue
   is already reachable, so this is a budget decision, not an access one.
4. **Page MDALL properly.** Company-scoped queries time out, so page by
   `licence_number` with explicit bounds rather than by company.
5. **Do not re-probe** TGA, PMDA, MHRA or NMPA expecting a different answer; each has a
   recorded route that requires a human request or a commercial agreement.
