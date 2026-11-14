# SOURCES - captured primary sources and data identities

Every external statement in this study is either a measurement of our own captured
data or a quote from a captured page. This file records URL, retrieval date,
byte size, SHA-256 and the verbatim text used. Raw bodies are not committed (size);
`artifacts/source_manifest.json` lists all **204** cached responses with their
hashes so a reader can re-fetch and verify.

Retrieval date for everything below: **2026-11-14 (UTC)**.

---

## 1. openFDA bulk exports (the outcome data)

| source | bytes | SHA-256 |
|---|---|---|
| `https://download.open.fda.gov/device/510k/device-510k-0001-of-0001.json.zip` | 249,963,096 | `eb479de53bcb8b48c73c9a5ecaf6eea75eb84a00431ac0c04000090005c663c9` |
| `https://download.open.fda.gov/device/registrationlisting/device-registrationlisting-0001-of-0002.json.zip` | 63,633,455 | `eb9da6bfd97ad78f866637bfe7e27ff0f130c56b125cb31ef78dfead93a500ba` |
| `https://download.open.fda.gov/device/registrationlisting/device-registrationlisting-0002-of-0002.json.zip` | 22,037,347 | `6efc769ab62587c4e2b87fba6cab3bcead20021b0bb4d4623aabab3cc976cc75` |
| `https://api.fda.gov/download.json` (manifest that names the three files above) | - | recorded in `source_manifest.json` |

Manifest-level facts observed at retrieval:

* `device/510k` - **176,625** records, `last_updated = 2026-11-02`,
  manifest `export_date = 2026-11-09`;
* `device/registrationlisting` - **336,932** records, same dates;
* the newest `decision_date` in the 510(k) export is **2026-10-30**, and the
  export contains **no** 2026-11 decisions. See TIME_SEMANTICS.md section 3.

## 2. openFDA documentation and licence

| page | bytes | SHA-256 | used for |
|---|---|---|---|
| `https://open.fda.gov/apis/device/510k/` | 127,819 | `edb7f1a0ae154166b124e734d75f902e88a325be17991dbe858204dcd376b544` | field inventory of the 510(k) endpoint |
| `https://open.fda.gov/apis/device/registrationlisting/` | 119,104 | `9c4787c751dbccffd18dcc303dbdf3453a7de3871f3aea36045e1967e5e8fea3` | field inventory of the registration/listing endpoint |
| `https://open.fda.gov/license/` | 123,019 | `7fda0041a24f8d7139a1781d4462ae39643a2ee6f3b0f079946c989a8e1982d2` | licence basis |
| `https://www.fda.gov/medical-devices/device-approvals-denials-and-clearances/510k-clearances` | 39,525 | `c4895c0eaa06afda80974a32ccbef20ff4795fd41c3239c8809fc8b46a0177ec` | FDA's own 510(k) database page |

**Licence quote** (openFDA licence page, verbatim):

> "unless otherwise noted, the content, data, documentation, code, and related
> materials on openFDA is public domain and made available with a Creative Commons
> CC0 1.0 Universal dedication."

**What the documentation does *not* provide.** Neither the endpoint pages nor the
download manifest documents a per-record publication or dissemination timestamp, nor
a refresh cadence. The only machine-readable freshness signal is the endpoint-level
`last_updated` and the manifest `export_date`. This is the factual basis for
TIME_SEMANTICS.md section 3, which refuses to treat `decision_date` as a
publication date.

**openFDA disclaimer** (returned in the `meta` block of every API response, verbatim):

> "Do not rely on openFDA to make decisions regarding medical care. While we make
> every effort to ensure that data is accurate, you should assume all results are
> unvalidated."

## 3. SEC EDGAR

| document | used for | hashes |
|---|---|---|
| `https://www.sec.gov/files/company_tickers.json` | 10,404 ticker/CIK/name triples, the registrant naming source | in `source_manifest.json` |
| `https://data.sec.gov/submissions/CIK##########.json` (62 registrants) | `acceptanceDateTime`, `items`, `sic`, `formerNames` | per-CIK hashes in `source_manifest.json` |
| `https://data.sec.gov/submissions/CIK##########-submissions-###.json` | older filing index blocks, merged so trailing-365-day windows are complete | per-file hashes |
| `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` (62 registrants) | `ResearchAndDevelopmentExpense` and revenue facts with `filed` days | per-CIK hashes |

The EDGAR *time-semantics* findings used here were established and documented in
SCIENCE-001 (`research/science_001/TIME_SEMANTICS.md`, 720 filings, 28 captured SEC
sources with verbatim quotes and hashes). They are **reused, not re-verified**, and
that is stated wherever they are used:

* `ACCEPTANCE-DATETIME` is a US/Eastern wall clock; converting with the US DST
  rule reproduces `data.sec.gov`'s `acceptanceDateTime` exactly for 720/720
  filings;
* after 17:30 ET the archival write trails acceptance by a median 11.6 h (weekend
  for Friday evenings) versus 35 s before the cut-off;
* 17 CFR 232.13(a)(2) keys the filing date on when direct transmission commences,
  so `filingDate` is a business-day label, not an instant.

A reader who wants the primary quotes should read
`research/science_001/evidence/sec_docs/SOURCES.md`; this study does not duplicate
that layer, it cites it.

## 4. Requests made, and their limits

* SEC: one User-Agent string naming the study and a contact address; 0.34 s between
  requests; every response cached with status, `Last-Modified`, collection time
  and SHA-256; a hard per-run request budget of 4,000.
* openFDA: three bulk downloads plus five documentation pages; no paged API
  scraping beyond the manifest.
* Total committed size impact: the raw sources are **not** committed; the derived
  artifacts are under 1.2 MB.
* No paid API, no credentialled account, no private data source.
