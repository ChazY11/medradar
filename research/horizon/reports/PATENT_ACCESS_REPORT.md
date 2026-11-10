# PATENT_ACCESS_REPORT

**HORIZON-001 · patent data frontier · verified 2026-11-10**

Prior rounds listed EPO OPS, USPTO Open Data Portal, PatentsView, Google Patents,
WIPO PATENTSCOPE and Lens.org as "investigated" but produced **no patent
acquisition asset**. This round re-tested every one of those channels live, and
found **two channels that actually work without an API key**, plus three more
that are open but licenced.

Result in one line: **two real patent corpora were acquired this round** — EP
publications from the EPO European Publication Server (sitemap channel), and the
Canadian patent database from CIPO under the Open Government Licence – Canada.

Every claim below corresponds to a probe in `SOURCE_PROBES/patents/` or
`SOURCE_PROBES/patents_unlock/`, or to bytes saved under `DATASETS/patents/`.

---

## 1. Channel-by-channel results

`outcome` is the machine-recorded probe verdict; `bytes` is the response body
size actually received.

| # | Channel | HTTP | Bytes | Outcome | Verdict |
|---|---|---|---|---|---|
| 1 | **EPO European Publication Server — sitemap index** | 200 | 360 906 | `OK` | **WORKS, keyless** |
| 2 | **EPO Publication Server — weekly gzip sitemap** | 200 | 238 148 | `OK` | **WORKS, keyless** |
| 3 | **EPO Publication Server — `document.html` front page** | 200 | 124 905 | `OK` | **WORKS, keyless** |
| 4 | **EPO Publication Server — `document.pdf`** | 200 | 524 450 | `OK` | **WORKS, keyless** |
| 5 | **CIPO Canada — patent bulk CSV (CKAN catalogue)** | 200 | 147 files | `OK` | **WORKS, open licence** |
| 6 | EPO OPS — biblio, anonymous | 403 | 208 | `BLOCKED_AUTH` | needs OAuth consumer key |
| 7 | EPO OPS — service root | 403 | 208 | `BLOCKED_AUTH` | needs OAuth consumer key |
| 8 | EPO Linked Open Data — API root | 500 | 114 | `SERVER_ERROR` | service broken; landing page 200 |
| 9 | EPO Global Patent Index sitemap (advertised in robots.txt) | 404 | 0 | `NOT_FOUND` | advertised but absent |
| 10 | USPTO ODP — dataset search | 401 | 26 | `BLOCKED_AUTH` | needs API key |
| 11 | USPTO ODP — bulk file path | 403 | 42 | `BLOCKED_AUTH` | needs API key |
| 12 | `bulkdata.uspto.gov` (legacy keyless bulk host) | — | 0 | `TRANSPORT_ERROR` | **DNS no longer resolves** |
| 13 | PatentsView legacy API | 200 | 20 666 | `OK_NO_MARKER` | returns the ODP SPA shell, not JSON |
| 14 | `search.patentsview.org` | — | 0 | `TRANSPORT_ERROR` | **DNS no longer resolves** |
| 15 | PatentsView bulk S3 | 403 | 243 | `BLOCKED_AUTH` | bucket no longer public |
| 16 | USPTO PEDS API | — | 0 | `TRANSPORT_ERROR` | DNS no longer resolves |
| 17 | USPTO assignment API | — | 0 | `TRANSPORT_ERROR` | DNS no longer resolves |
| 18 | Espacenet publication details | 403 | 5 878 | `BLOCKED_WAF` | AWS WAF challenge |
| 19 | WIPO PATENTSCOPE bulk endpoint | 404 | 8 020 | `NOT_FOUND` | no anonymous bulk |
| 20 | WIPO PATENTSCOPE search UI | 200 | 52 215 | `OK` | human interface only |
| 21 | Lens.org API | 401 | 114 | `BLOCKED_AUTH` | token required |
| 22 | Google Patents record page | 200 | 371 596 | `OK` | single-record read only; bulk is BigQuery+billing |
| 23 | DPMA (DE) register search | 200 | 160 771 | `OK` | human interface reachable |
| 24 | DPMA open-data landing (URL tried) | 404 | 23 823 | `NOT_FOUND` | correct data URL still to be found |
| 25 | JPO (JP) pages | 403 | 9 939 | `BLOCKED_AUTH` | edge-blocked from this host |
| 26 | IP Australia via data.gov.au CKAN | 200 | 18 778 | `OK` | catalogue open; **statistics, not patent texts** |
| 27 | `developers.epo.org` (OPS signup) | 403 | 5 696 | `BLOCKED_WAF` | registration portal behind WAF |
| 28 | Zenodo patent datasets | 200 | 49 622 | `OK` | open datasets exist; not a substitute corpus |
| 29 | HuggingFace patent datasets | 200 | 12 142 | `OK` | open datasets exist; licence varies per dataset |

**The honest summary of the "big six" that the brief named:**

* **EPO OPS** — blocked, needs a free registered key. Unlock route recorded.
* **USPTO Open Data Portal** — blocked, needs a free API key. Unlock route recorded.
* **PatentsView** — **effectively retired**: its hosts no longer resolve or now
  return the ODP shell, and its bulk bucket is closed. Do not chase it again.
* **Google Patents** — no bulk outside BigQuery, which requires a billing account.
* **WIPO PATENTSCOPE** — no anonymous machine interface.
* **Lens.org** — token required.

None of these was circumvented. Where a key is required, the official signup URL
and the project-owner action are recorded in `registry/sources/` under
`unlock_route`.

---

## 2. Channel that works #1 — EPO European Publication Server

### How it was found

It was not in the brief's list. `https://data.epo.org/robots.txt` — the operator's
own crawler policy — advertises:

```
Sitemap: https://data.epo.org/publication-server/sitemap.xml
Sitemap: https://data.epo.org/gpi/sitemap.xml
Disallow: /pise-server/
Disallow: /qual_lod/
Disallow: /linked-data/id/
Disallow: /linked-data/doc/
Disallow: /linked-data/data/
Disallow: /linked-data/def/
Disallow: /linked-data/representation/
```

That is the EPO itself publishing a machine-readable index of its own publication
server. The same file asks crawlers **intending to build indexes** to e-mail
`patentinformation@epo.org` to register for deep redirects. This connector does
**not** build an index: it samples a bounded number of advertised sitemaps and a
bounded number of front pages, and it never requests any robots-disallowed path.

### Structure

```
sitemap.xml                     sitemap index, one <sitemap> per weekly publication date
sitemap.YYYY-MM-DD.xml.gz       gzip XML, ~3 800-5 500 <url> entries per week
  <url>
    <loc> …/patents/EP4488863NWA1/document.pdf
    <loc> …/patents/EP4488863NWA1/document.html
    <pubsrv:ep-patent-document-ref>
      <publication-reference><document-id>
        country / doc-number / kind / date
      <application-reference><document-id>
        doc-number / date          <- the filing date, per record
      <classification-ipc><text>A61M0005142 A61M0005172 C07K001622
```

Note the IPC compaction: `A61M0005142` = subclass `A61M` + group `0005` + subgroup
`142` → `A61M 5/142`. This was determined empirically against the front page and
is implemented in `parse_weekly_sitemap`; getting it wrong silently zeroes the
medical-device filter, which is exactly what happened on the first run.

### Fields available

The `document.html` front page carries the full INID block, parsed by
`parse_front_page`:

| INID | field | completeness in the 228-record sample |
|---|---|---|
| 11 | publication number (e.g. `EP4488863A1`) | 228 / 228 |
| 12 | document type | 228 / 228 |
| 21 | application number | 228 / 228 |
| 22 | **filing date** → `event_at` | 228 / 228 |
| 30 | priority claims (country, number, date) | 184 / 228 |
| 43 | **application publication date** | 228 / 228 |
| 45 | **grant publication date** (B documents) | 116 / 116 B-documents |
| 51 | IPC | 228 / 228 |
| 52 | CPC | 228 / 228 |
| 54 | title (all languages, English preferred) | 227 / 228 |
| 57 | abstract | 227 / 228 |
| 71 | applicant (A documents) | 112 / 112 A-documents |
| 72 | inventors | 227 / 228 |
| 73 | proprietor (B documents) | 116 / 116 B-documents |
| 74 | representative | high |
| 84 | designated contracting states | high |
| 86/87 | PCT application / publication numbers | where present |

**Not available on the front page:** claims text and citations. Both exist further
into the HTML/PDF (`the word "Claims" is present in the document body`) but are
not required for the identity/date work and were not parsed this round. That is a
deliberate scope boundary, not an oversight.

### The temporal trap this source exposes — and what it cost

The same patent front page carries **two different publication dates**:

```
EP2490731B1
  (43) Date of publication of application: 29.08.2012   Bulletin 2012/35
  (45) Mention of the grant:               05.06.2024   Bulletin 2024/23
  (22) Date of filing:                     19.10.2010
```

Picking 43 for a granted document places it **~11.8 years** before anybody could
read it. `epo_publication_server.parse_front_page.publication_date_for(kind)` now
selects 45 for `B*` kinds and 43 for `A*` kinds, and the connector records both
raw values in `attributes.date_43_application` / `attributes.date_45_grant` so the
choice is auditable rather than hidden.

Measured on the 228-record sample: `publication − filing` gap is **min 114 days,
median 1 738 days (~4.8 y), max 6 881 days (~18.8 y)**. Any study that uses filing
dates as observation dates would be wrong by years.

### Document roles — the second trap

EP publication kinds are not interchangeable. In the acquired sample:

| kind | role | n | independent disclosure? |
|---|---|---|---|
| B1 | granted specification | 115 | yes |
| A1 | application publication | 58 | yes |
| A3 | **search report, published separately** | 28 | **no** |
| A2 | application, no search report | 22 | yes |
| B8 | **corrected title page** | 3 | **no** |
| B2 | amended granted specification | 1 | yes |
| B3 | limited granted specification | 1 | yes |

So 228 fetched documents correspond to **197 independent technical disclosures**.
Counting A3 as a publication would have inflated the corpus by 14 % and
double-counted content. `tools/finalize_patent_records.py` applies the mapping and
flags `DOCUMENT_IS_SEARCH_REPORT` / `DOCUMENT_IS_CORRECTION`.

### Acquisition actually performed

| quantity | value |
|---|---|
| weekly sitemaps sampled | 10 (2005-06-01 … 2026-06-03) |
| publications enumerated | 37 989 |
| medical-device publications among them | 3 093 (8.1 %) |
| front pages fetched | 228 |
| requests used | 241 |
| bytes received | 30 752 412 (30.7 MB) |
| records emitted | 228 |
| independent disclosures | 197 |
| distinct first applicants | 193 |
| two-clock records (`FULL_TWO_CLOCK`) | 228 |

Medical-device IPC distribution in the sample: `A61B` 103, `A61M` 51, `A61F` 40,
`A61N` 20, `A61L` 18, `G16H` 17, `A61C` 11, `A61G` 5, `A61H` 5, `A61J` 2,
`H05G` 1, `A61D` 1.

### Target-firm presence in the sample

| firm | patents found | note |
|---|---|---|
| Philips | 7 | `Koninklijke Philips N.V.` is the top applicant in the whole sample (6) |
| Medtronic | 3 | |
| Covidien | 2 | Medtronic subsidiary since 2015 — the historical-attribution case |
| GE HealthCare | 0 | present in the sample only as `Siemens Healthineers`, not GE |
| Dräger | 0 | |
| Mindray | 0 | |

Zero hits for three of the five firms is a **sampling** outcome, not an absence
claim: the sample is 228 of 3 093 medical-device publications across 10 weeks. See
§5 for why that matters and §6 for what to do about it.

---

## 3. Channel that works #2 — CIPO Canada (open licence)

### Why it matters more than its row count

The CIPO patent dataset is published on `open.canada.ca` (CKAN package
`fe1dfbb9-0fc3-42ca-b2a9-6ca4c05dbac9`) as zipped CSV, and its licence is not
"terms of use" but an actual **Open Government Licence – Canada**:

> "… grants you a worldwide, royalty-free, perpetual, non-exclusive licence to use
> the Information, including for commercial purposes …"
> Attribution required: "Contains information licensed under the Open Government
> Licence – Canada."

Coverage statement in the catalogue record: **patent documents 1869 → 2022-02-28**.
Tables join on `Patent Number`:

| table | what it adds |
|---|---|
| `PT_Main` | titles EN/FR, **Filing Date**, **Grant Date**, application status/type, PCT application/publication numbers and PCT publication date |
| `PT_Interested_Party` | applicants / owners / inventors, **with `Owner Enable Date` and `Ownership End date`** |
| `PT_IPC_Classification` | full IPC with subclass code |
| `PT_Priority_Claim` | priority country, number, date |

`PT_Interested_Party` carrying an **ownership timeline** is the single most useful
structural feature found in any patent source this round: it is what lets a 2004
applicant be attributed correctly instead of being retrospectively labelled with
today's corporate parent.

### Two real obstacles, both solved legitimately

**Obstacle 1 — broken TLS chain.** `opic-cipo.ca` serves only its leaf
certificate and omits the intermediate:

```
leaf   CN=*.opic-cipo.ca
issuer CN=RapidSSL TLS RSA CA G1, OU=www.digicert.com, O=DigiCert Inc, C=US
```

A browser silently repairs this by fetching the intermediate from the leaf's AIA
`caIssuers` URL. Python's `ssl` does not chase AIA, so `requests` fails with
`unable to get local issuer certificate`. `hz/tls.py` performs the *same* repair a
browser performs — reads the leaf, follows
`http://cacerts.rapidssl.com/RapidSSLTLSRSACAG1.crt`, appends the public
intermediate to the platform trust bundle, and **verifies normally against the
platform roots**. Verification is never disabled; if the rebuilt chain does not
validate, the fetch fails. After the repair: `206 Partial Content, bytes 0-3/…,
PK\x03\x04`.

**Obstacle 2 — no publication date.** `PT_Main` has Filing Date and Grant Date but
**no publication / open-to-inspection date**. Canadian applications are laid open
18 months after filing, but that is a *rule*, not a recorded field. The connector
therefore does **not** compute it:

* granted patent → `source_public_at` = `Grant Date` (recorded)
* pending application → `source_public_at = NULL` + `MISSING_PUBLICATION_DATE`

and records the 18-month rule only as text in
`attributes.public_availability_note`. This is the difference between capturing a
fact and manufacturing one.

Every record is additionally flagged `SNAPSHOT_ONLY`: the dataset is a single
quarterly extract whose last bibliographic date is 2022-02-28, so no record-level
history is observable.

*Acquisition figures are in §4 and in `DATASETS/patents/cipo_canada/ETL_SUMMARY.json`.*

---

## 4. Records acquired

| source | records | independent disclosures | with applicant | with public date | with filing date | with IPC | licence |
|---|---|---|---|---|---|---|---|
| `epo_publication_server` | 228 | 197 | 227 | 228 | 228 | 228 | open, no explicit licence |
| `cipo_canada` | see `ETL_SUMMARY.json` | = records | yes | grants only | yes | yes | **Open Government Licence – Canada** |

Both are exported in `horizon.evidence.v1` form (see `ATLAS_HANDOFF.md`).

What is **asserted** here: these are real server responses, hashed, with URLs and
timestamps recorded. What is **not** asserted: that this sample is representative
of EP or CA patenting in medical technology — 10 weeks out of ~2 500 for EP, and a
firm-scoped slice for CA, are samples and are labelled as such.

---

## 5. What was NOT obtained, and the precise reason

| missing | reason | lawful route |
|---|---|---|
| US patent records | every USPTO endpoint that answers is keyed | free ODP API key by the project owner |
| EP claims / citations | out of scope this round (present but unparsed) | parse further into the same HTML; citations need OPS |
| Patent family IDs (DOCDB/INPADOC) | family data is an OPS/Lens feature; the sitemap carries no family key | EPO OPS with a key |
| JP / KR / CN records | JP edge-blocks this host; KR/CN need keys via national portals | national office accounts |
| Legal status | not in the publication sitemap | EPO OPS legal service; national registers |
| Google Patents bulk | BigQuery requires billing | owner's GCP project |

---

## 6. What the next round should do (ranked by evidence)

1. **Ask the project owner for one free key each** at `https://developers.epo.org/`
   (OPS) and `https://data.uspto.gov/apis/getting-started` (ODP). That single
   action converts the two largest blocked corpora — including patent families,
   citations and US assignees — into accessible data. It is a five-minute
   registration and it is the highest-value unblock available.
2. **Raise EPO sample density, not breadth.** The channel is already proven and
   costs ~135 KB per record. Fetching all medical-device front pages for 4–6
   consecutive recent weeks (~1 500 documents, ~200 MB) would give meaningful
   per-firm coverage for all five target firms; 228 records across 10 weeks cannot.
3. **Use CIPO's ownership timeline as the company-attribution ground truth.** It is
   the only source found that records *when* ownership changed, so it can validate
   ATLAS-001's subsidiary/parent logic against dated facts instead of intuition.
4. **Do not re-probe PatentsView, `bulkdata.uspto.gov`, PEDS or the USPTO
   assignment API.** They are gone; the evidence is recorded here so nobody spends
   another round on them.
5. **Parse claims** from the already-downloadable EP HTML if claims text is needed.
   No new access is required.
