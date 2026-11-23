# Intelligence sources: what exists, what this repository now reads, and what is deliberately unread

This is the source inventory for the intelligence layer. It exists because "we added more
sources" is not a claim anybody can check, while "this endpoint answered this on this date with
these fields" is.

Measured evidence for every row below: [`evidence/source_probe_intel.json`](evidence/source_probe_intel.json).

## Why this document exists

The project's first six sources (openFDA 510(k)/PMA/recall, ClinicalTrials.gov, SEC 8-K,
openFDA drugsfda) are public and freely available **to everyone**, including every competitor.
That is not a weakness of the data, it is a fact about the sourcing strategy: the same public
sources underpin the commercial platforms, which add analyst interpretation on top.

What no commercial platform does is read the **regulatory document corpus** — the 510(k)
Summary, the PMA statement, the MAUDE narrative — at the granularity an engineer needs. That is
where the defensible corpus is, and it is where this layer now points.

## The eight layers

| Layer | What it answers | Status here | Entry |
|---|---|---|---|
| L1 Regulatory | what was cleared, by whom, on what evidence | **read** (structured fields) + **read** (documents) + **batch corpus** (new) | `radar/adapters/openfda*.py`, `radar/documents.py`, `radar/fda_corpus.py` |
| L2 Clinical | what was tested in humans, and what happened | partial (trials, existing) | existing `clinical.py` lane |
| L3 Academic | what the literature says, and when it became public | **read** (new: real publication instant) | `radar/adapters/europepmc.py` |
| L4 Patent | what the claims actually constrain | **ownership resolution works; fetch is credential-gated** | `radar/patents.py` |
| L5 Corporate | what the company says about its own R&D | partial (8-K only) | existing corpus lane |
| L6 Funding | what labs are being paid to build, 2–5 years ahead | **read** (new) | `radar/adapters/nih_reporter.py` |
| L7 Supply & purchase | what is actually being bought | not started | see below |
| L8 People | who is doing this work | partial (PIs via RePORTER) | grows out of L6 |

### L1 — Regulatory, including the documents

Structured rows were already present. The new part is the **document layer**:

* `derive_510k_pdf_url` — one rule, verified on six live filings (6/6):
  `K<nnnnnn>` → `/cdrh_docs/pdf<first two digits>/K<nnnnnn>.pdf`.
* `fetch_510k_summary` — fetches, extracts the text layer, and splits the summary into named
  sections (indications, device description, substantial equivalence, performance data, bench
  testing, sterilisation, biocompatibility, clinical data, conclusion).
* Why it is worth the work: a 510(k) Summary states, in the manufacturer's own words, which
  predicate it compared itself to and which bench tests it ran. That is the single most useful
  public artefact for a design engineer, there are ~176k of them, and nobody sells them
  structured.
* Honesty rules: a filing that publishes nothing is recorded as `not_published`, never as an
  empty summary; a scanned filing is `no_text_layer` with a named reason and needs OCR, which
  is deliberately out of scope for a standard-library-only core.

### L1b — MAUDE, the failure narratives

`radar/adapters/maude.py`. **26,849,547** device event reports, each with free-text narrative
blocks, a product-problem taxonomy, a model number and sometimes a baseline 510(k) number.

> Correction carried in the evidence file: an earlier revision recorded 513,481 as the total.
> That was the count for `search=device.generic_name:"catheter"` — a filtered count labelled as
> a population, understating the source by 52×. The unfiltered endpoint returns 26,849,547.

Measured on a 999-row sample of product code DQY: 959 carried a narrative, 944 carried a model
number, 10 carried a baseline 510(k) number. That ratio is why the model number — not the 510(k)
field — is the join into the device register.

This also reframes the project's own premise. The committed snapshot holds 375,378 events
across six sources; MAUDE alone is 26.8M. The gap is depth, not exclusivity.

### L1c — UDI, the identity spine

`radar/reference.py` (API) and `radar/gudid.py` (bulk). 5,182,695 device records, each carrying
`labeler_duns_number`, the official product codes and `premarket_submissions`, which is a direct
link to the clearance.

Two ways in, and the bulk one is the right one for a first load:

| route | cost |
|---|---|
| openFDA `device/udi` | ~5,183 pages; 1,000/day anonymous, 120,000/day keyed |
| **GUDID full release** | **one 549,941,186-byte download, measured** |
| GUDID daily/weekly/monthly delta | 633 KB – 7 MB |

The full release is **211 XML parts of ~25,000 devices each** (21 GB of XML). `iter_devices`
walks every part in natural order; a first implementation read only member one, imported 25,000
of 5,258,157, and the completeness check in `import_release` is what caught it — which is the
argument for writing the check before writing the loader.

Measured end to end on 2026-11-21:

```
download   549,941,186 bytes in 43 s (resumable, verified)
import     5,258,157 devices, 0 skipped, 1,675 s (~3,160 rows/s)
declared   5,258,157  ← header count matched the parse exactly
coverage   5,258,157 with DUNS (100 %) · 5,258,129 with a model number · 12,536 companies
```

Top labelers by device count, as a sanity check that the register is real:
Cardinal Health 200 (383,755), Medline Industries (252,243), ICU Medical (65,006),
Smith & Nephew (53,923), Medtronic Sofamor Danek (45,433), Globus Medical (44,993),
NuVasive (44,675).

This fixes a measured defect rather than adding a capability: entity resolution matches
**applicant name strings** and resolves 35.2 % of events. A DUNS is a legal-entity key the
labeler maintains, so `MAUDE model → UDI device → labeler DUNS → 510(k)` is a join, not a guess.
Verified on 3,948 live daily-release records: 3,943 carried a DUNS and a resolvable model number.

It is kept in a **fourth database** (`reference.db`), not the ledger: 5.18M device records are
not 5.18M events, and a re-sync must never look like a change.

### L3 — Europe PMC, the first real public instant

`radar/adapters/europepmc.py`. This is the source that closes the project's headline
limitation for the literature lane instead of arguing about it:

* `firstPublicationDate` → `published_at` (a real public instant);
* `firstIndexDate` → `source_updated_at` (when this index could serve it);
* the gap between them is the access lag a naive backtest hides. Measured over 100 records:
  median 2 days, maximum 38, minimum −391 (ahead-of-print records, recorded rather than
  clamped).

`sort=FIRST_PDATE:asc` makes the endpoint answer HTTP 503 instead of rejecting the field, so the
adapter sends no sort parameter. A retry loop against that would look like an outage.

### L6 — NIH RePORTER, the layer every commercial platform leaves empty

`radar/adapters/nih_reporter.py`. Federal research funding: what American labs are being paid to
build, typically three to seven years before a clearance.

No audited platform tracks this against device companies. They track markets, shares and
clearances. This is the earliest public statement that a technology direction is funded.

The join that makes it more than a list: RePORTER returns `organization.primary_duns`, which is
**the same key as the UDI register's `labeler_duns_number`**. So

```
NIH award (primary_duns) → UDI device (labeler_duns) → 510(k) clearance
```

is a join, not a guess. Measured on one scope (FY2025, "catheter"): 100 of 323 projects
returned, 93 carried a DUNS, 98 carried a real `award_notice_date`.

Honest note on the overlap, measured against the **full** register rather than a sample:

```
GUDID full release imported : 5,258,157 devices, 12,536 distinct labeler DUNS
NIH RePORTER DUNS sampled   : 501 (FY2024+FY2025, four device terms)
Matched as UDI labelers     : 29   (5.8 %)
```

Those 29 are the interesting population, not a rounding error: **SINTX Technologies (3,032
devices), Infinite Biomedical Technologies, Baebies, Biotex, Mercator MedSystems, IotaMotion,
Sonavex, PuraCath, Vantis Vascular, MicroStructure Imaging**. They are small firms that both
receive federal research money and hold clearances — exactly the "who is funded and shipping"
index that no audited platform sells.

Time semantics: `award_notice_date` is `event_at` **and** `published_at` — a real public instant.
`project_start_date` / `project_end_date` describe the funded period and are never used as the
event time; `fiscal_year` is an administrative bucket, never a date.

Transport: RePORTER v2 is POST-only, which is why `PoliteFetcher.post_json` exists. It shares the
same pacing, budget, refusal and capability-limit code path as `get_text`, so a POST cannot
acquire different retry semantics from a GET.

## L4 — Patent ownership: the half that works without a credential

`radar/patents.py`. A patent states its owner as a string (`MEDTRONIC SOFAMOR DANEK, INC.`).
A string is not an entity. The device register is keyed on `labeler_duns_number`, which is.

So the resolver asks a narrower question than "can we download patents": **can an assignee
string be resolved to a DUNS?** That one is answerable today, because the candidate set is the
register we already hold — 12,536 companies.

Measured on 39 real assignee strings and 4 deliberate negatives:

```
resolved 31 / 39        exact 30, flagged 1
false positives 0 / 4
```

```
MEDTRONIC SOFAMOR DANEK, INC.  -> DUNS 830350380   exact  1.00
COVIDIEN LP                    -> DUNS 058614483   exact  1.00
Biosense Webster, Inc.         -> DUNS 020163218   exact  1.00
SIEMENS HEALTHINEERS AG        -> DUNS 314699460   exact  1.00
STRYKER CORPORATION            -> DUNS 481999654   exact_entity_mismatch  0.55
BAXTER HEALTHCARE SA           -> DUNS 005083209   token_subset_entity_mismatch  0.55
BIOTRONIK SE & CO. KG          -> DUNS 480862817   token_subset_entity_mismatch  0.55
```

The flagged rows are the important ones. `STRYKER CORPORATION` first resolved to **Stryker
GmbH** — a different legal entity in a different country — at confidence 1.00, because
stripping the suffix left `STRYKER` and any company called Stryker qualified. That is exactly the
silent corruption the spine exists to prevent, so the resolver now compares the *removed* legal
forms and downgrades when they disagree. The candidate is still returned (it is usually the right
corporate family) but the method and confidence say what actually happened.

### The fetch lane: ODP route table, measured keyless

> **The key now requires ID.me identity verification.** Measured 2026-11-23 on a signed-in
> USPTO.gov account: `/apikey` answers *"Your USPTO.gov account is not currently verified with
> ID.me. In order to obtain an API key, you will need to create an ID.me account and link it to
> your USPTO.gov account."* The signed-in account also had to complete a four-field ODP profile
> (job title, organization type, organization name, intended use) before the key page opened at
> all — accounts that skipped it by 2026-10-08 had their keys deactivated. So this is not an
> "verify an email address" step: it is a third-party identity check, and it is the gate on L4.


`api.uspto.gov` is behind AWS API Gateway, which answers three different ways and each needs a
different fix:

| status | body | meaning | what you do |
|---|---|---|---|
| 401 | `{"message":"Unauthorized"}` | route exists, no credential supplied | configure a key |
| **403** | **`{"message":"Forbidden"}`** | **the credential was rejected** | **the key is wrong or expired** |
| 403 | `{"message":"Missing Authentication Token"}` | **no such route** | stop calling it |

The middle row is the one that matters for operations: measured with a deliberately wrong key,
ODP answers `403 {"message":"Forbidden"}`, and reporting that as "the operator refuses automated
access" would send a reader hunting a policy problem when the answer is a bad key. The detection
is kept narrow — a JSON object with a `message` field whose value is exactly `Forbidden` — so an
HTML error page saying 403 never matches.

Reading that distinction is what turned "the assignment API is blocked" into "the assignment API
does not exist on ODP":

| path | status | meaning |
|---|---|---|
| `/api/v1/patent/applications/search` | 401 | **live**, needs a key |
| `/api/v1/datasets/products/search` | 401 | **live**, needs a key |
| `/api/v1/patent/assignments/search` | 403 | no such route |
| `/api/v1/patent/assignments` | 403 | no such route |
| `/api/v1/patent/assignment/` | 403 | no such route |
| `/api/v1/ptab/`, `/api/v1/trademarks/`, `/api/v1/bulk/` | 403 | no such route |
| `/openapi.json`, `/api/v1/openapi.json` | 403 | **no published spec** |

Consequences, stated rather than worked around:

1. **ODP gives patent applications and a dataset catalogue.** No assignment search, so the
   ownership chain cannot be read from ODP. Ownership is resolved from the assignee name on
   each application record, which is what `AssigneeResolver` does.
2. **There is no OpenAPI document**, so response field names cannot be read in advance. The
   client therefore *tolerates* several envelopes and raises `OdpShapeError` with the top-level
   keys it actually saw — an unrecognised reply can never look like "no matches".
3. **The dataset catalogue is the highest-value unknown.** If `/datasets/products/search` lists
   a bulk patent-assignment product, ownership chains become a file download rather than an API
   problem. That is the first thing `odp_doctor.py` reports once a key exists.

The other hosts stay as measured: `search.patentsview.org`, `assignment-api.uspto.gov`,
`assignment.uspto.gov`, `ped.uspto.gov` and `bulkdata.uspto.gov` do not resolve from this
network at all; `patents.google.com/xhr/query` answers 503; BigQuery needs a GCP project. The
clients raise `CredentialMissing` naming the exact environment variable
(`USPTO_ODP_API_KEY`, `PATENTSVIEW_API_KEY`, `GOOGLE_CLOUD_PROJECT`) — a missing credential is
reported as a missing credential, never as zero patents.

```bash
# install a key: writes the user environment variable AND a key file, then calls the live API
# to prove it is accepted before anything depends on it
python tools/odp_setup.py --key YOUR_KEY
python tools/odp_setup.py --file key.txt      # keeps it out of shell history
python tools/odp_setup.py --check             # validate what is already configured
```

**Account creation is the one step that cannot be automated here, and the reason is concrete
rather than cautious:** registration sits behind an AWS WAF challenge
(`0dd6fc7fe1e2.edge.sdk.awswaf.com/challenge.js`) plus a USPTO.gov account, and confirming that
account requires an e-mail inbox. Measured 2026-11-21: key issuance lives behind `/account`, no
unauthenticated key route exists on `api.uspto.gov`, and every keyless patent source is closed
too — PatentsView's S3 bucket now answers `AccessDenied`, Google Patents serves 503,
Justia and FreePatentsOnline serve 403, `patft.uspto.gov` does not resolve.

## The 510(k) corpus: how big it actually is

`radar/fda_corpus.py`. **Three** corrections came out of measuring rather than assuming, and each
one shrank the number.

**One: filings are not documents.** 176,683 is the number of 510(k) *filings*. The number that
publish a Summary is **94,291**, and the share is not uniform:

| period | filings | summaries | share |
|---|---:|---:|---:|
| 1976–1989 | 47,440 | ~0 | 0 % |
| 1990–1999 | 44,082 | 17,778 | 40.3 % |
| 2000–2009 | 32,942 | 27,562 | 83.7 % |
| 2010–2019 | 30,476 | 28,381 | 93.1 % |
| 2020–2026 | 21,743 | 20,570 | 94.6 % |

**Two: half of those flags point at nothing.** openFDA's `statement_or_summary` field is honest —
the filing did publish a summary — but the document is **only digitised from 2010**. Measured by
taking five real filings per year and requesting the derived URL:

| year | URL 200 | |
|---|---|---|
| 1998–2009 | **0 / 5 each** | 60 samples, all 404 |
| 2010 | 2 / 5 | April onward; 4/4 from July |
| 2011+ | 5 / 5 | |

Five alternative path shapes for K002182 and K093456 (`pdf/`, `pdf2/`, `pdf2000/`, upper-case
extension) all answer 404, so this is not a URL rule that needs fixing — the scans are not public.
Querying 2010-06 onward returns **39,176** filings, and that is the real index.

A crawl starting at 1976 would have spent its first ten hours on certain 404s. It did, briefly:
the first attempt walked 500 filings and got `not_published` on every one.

**Three: about half the scanned era has no text layer.** Running the real crawl, at 1,750
attempts the split was `text=682 / no_text_layer=1,013 / not_published=55`. The scans stop
around 2012 — by 1,750 filings the no-text count had plateaued while the text count kept climbing
— because 2013 onward is digital-born. So of the 39,176 filings in range, roughly **28,000 will
yield readable text**, and the rest are image-only PDFs this stdlib extractor cannot read (a
defect to solve with OCR, not with a network retry).

Every one of those steps was a real measurement that changed the plan, and none of them was
visible from the row count alone.

Throughput, measured: **1.7 filings/s** with a 3 requests/second host policy, zero failures,
resumable through the document store. ~1,700 filings per 20 minutes.

```bash
python -m medradar.corpus_510k --limit 40000 --since 2010-06-01   # resumable
```

## The bridge: 510(k) document → device → DUNS → failure

`radar/premarket_bridge.py`. This is the join the whole exercise was for, and it is made of
equality joins only — **no company-name matching anywhere in the chain**:

```
510(k) Summary document (K number)
  -> UDI device  (premarket_submissions.submission_number == K number)
     -> labeler DUNS + version_or_model
        -> MAUDE event (device.model_number)
```

### It works, at a measured rate

Two independent methods agree, which is why the number is worth trusting:

**Method 1 — random real filings** (10 per year, K numbers taken from openFDA `device/510k`,
then each queried against UDI):

| year | hits / 10 |
|---|---|
| 2005 | 2 |
| 2010 | 1 |
| 2013 | 2 |
| 2016 | 7 |
| 2019 | 6 |
| 2021 | 5 |
| 2023 | 4 |
| 2025 | 6 |

**33 / 80 = 41 %.**

**Method 2 — the actual stored corpus**, per cohort:

| cohort | documents | aligned | rate |
|---|---:|---:|---:|
| 2021 | 17 | 7 | **41.2 %** |
| 2022 | 93 | 36 | **38.7 %** |
| 2025 | 234 | 7 | 3.0 % |
| 2026 | 969 | 11 | 1.1 % |
| **2000–2023** | 111 | 43 | **38.7 %** |
| **2024–2026** | 1,205 | 18 | **1.5 %** |

Blended, the corpus reads 61 / 1,316 = 4.6 %. **That blended number is a trap** and is reported
here only to be dismissed: the corpus was built newest-first, and a labeler publishes its UDI
record some time *after* clearance, so the last eighteen months have almost no bridge yet. The
mechanism is not failing; the cohort has not populated.

Consequence for the product, and it is a real one: **the corpus must target 2000–2023, not the
newest filings.** A newest-first crawl produces documents that cannot be attached to a device.

### A silent-truncation trap this pass hit

While testing batched queries, `("K250063" OR "K252901")` returned 794, which is the count for
`K250063` alone — the second term appeared to be ignored. The decisive test that settled it:

```
K250063 alone   794
K950913  alone   50
A OR B          844   == 794 + 50
B OR A          844
```

So openFDA's OR **is** correct and order-independent. The earlier "40 batches all 404" was not a
syntax problem: **979 of the 980 newest filings genuinely have no UDI link yet.** The near-miss
here was concluding "the API silently truncates my query" from a sample in which the second term
happened to be empty — the same class of error as mistaking a filtered count for a population.

Real example of the chain, from the corpus:

```
K210313  EasyFinder Fixed Curve Diagnostic catheter  (15,092 chars of text)
  -> di:06952450918906  Shanghai Microport Ep Medtech Co., Ltd.  DUNS 542965535
     -> model EPD6AB252  (56 devices share this submission)
```

### Two modes, and the difference matters

* `sync_bridge()` sweeps the whole bridge set — `1,584,610` records, ~1,586 pages, resumable
  through a cursor in `reference_kv`, and reports `complete=False` when it stopped early.
* `link_submissions()` asks only about the numbers already in hand — 1,280 corpus numbers in
  **52 batched queries**, 2,660 devices written.

The first answers "any future document joins locally". The second answers "the corpus I have
today is aligned now". A 15-page sweep of the first had produced 1 of 960 documents aligned; the
second turned that into 61 of 1,313 in under a minute.

### The third leg is weaker than the first two, and now says by how much

Model-number matching into MAUDE returned **0 events for all three samples** on the first
attempt. That looked like "these models never failed", which would have been a false and
comfortable conclusion. The real cause is that `model_number` in MAUDE is free text and
manufacturers usually leave it empty.

`radar/failure_index.py` therefore does what the premarket bridge does — **sweep once at a coarse
key, then join locally**:

* coarse key = **product code**: a controlled vocabulary, always present, cheap to walk;
* the sweep writes one row per (product code, normalised model, normalised brand), after which a
  device is matched with no further requests;
* **model match and brand match are reported separately**, because they are different claims. The
  same model failing is this device; the same brand failing is the manufacturer's family.

Measured on the 12 highest-volume product codes behind our aligned devices (71.8 % of them):

```
index    137 pages · 33,604 events · 17,998 rows · 5,333 distinct models · 3,838 brands
blank    15,794 device entries carried no model number  (54 %)
join     model-exact 125 (3.4 %) · brand-only 1,020 (27.5 %) · neither 2,570 (69.2 %)
events   Malfunction 44,011 · Injury 41,047 · Death 385
```

Two honest limits on that table. The index covers **2015 onward and at most 15 pages per code**,
so every count is a **lower bound**, and `stop_reason` says so rather than pretending the sweep
was complete. And the 69.2 % "neither" is not a coverage artefact — 71.8 % of those devices sit
inside the swept codes — it is the real cost of a field that is blank more than half the time,
plus brand-name normalisation that GUDID and MAUDE disagree about.

Worked example from the join: `MEDTRONIC SOFAMOR DANEK, INC.` model `X1209255` → **73 events**
(68 Malfunction, 5 Injury), attributed at brand level and labelled as such.

A transport defect surfaced here and is worth recording: a 999-row MAUDE page is about **9 MB**,
and one arrived truncated — 5,209,171 of 8,852,529 bytes. `http.client.IncompleteRead` inherits
from `HTTPException`, which inherits from `Exception` and **not** `OSError`, so it escaped the
transport handler and killed the sweep. Truncation is a transient failure and is now retried;
MAUDE pages are also 250 rows rather than 999, which is ~2.2 MB and survives a flaky link.

### Three: the scanned era, and what OCR actually buys

Running the real crawl, at 1,750 attempts the split was `text=682 / no_text_layer=1,013 /
not_published=55`. The no-text count plateaus at about 1,036 while the text count keeps climbing,
so the scans are concentrated in **2010–2012** and 2013 onward is digital-born.

Those scans are image-only PDFs: a valid file with no text operators at all. Two things followed.

**The reader defect.** `tools/ocr_scan.py` renders pages with **pypdfium2** (Apache-2.0 /
BSD-3-Clause) and reads them with **tesseract 5.4.0**, installed here with
`winget install UB-Mannheim.TesseractOCR`. PyMuPDF is also present on this machine and was
deliberately not used: it is AGPL, and pulling AGPL into the pipeline of an MIT project is a
licence decision nobody asked for. OCR lives in `tools/`, never in the package, because the
package's `dependencies == []` is a property worth keeping.

Measured on K100017 (a 2010 EUROIMMUN NMDA-receptor 510(k)): 8/8 pages read, 0 empty, 17.1 s,
**16,271 characters**, and the text is legible prose, not noise.

Every OCR'd document is marked so it can never be mistaken for a publisher text layer:

```json
{"status": "text", "text_source": "ocr", "ocr_pages": 8, "ocr_pages_empty": 0,
 "ocr_engine": "tesseract v5.4.0.20240606", "ocr_confidence_low": true,
 "pdf_reason": "pdf reason=no_content_stream; needs OCR",
 "note": "text recovered by OCR from an image-only PDF; not a publisher text layer"}
```

**A section format nobody had noticed.** That same document produced exactly **one** section
before, and **ten** after: `submission_identity`, `measurand`, `test_type`, `applicant_identity`,
`device_names`, `regulatory_info`, `intended_use`, `indications`, `substantial_equivalence`,
`clinical_data`, `conclusion`.

The reason is structural, not a regex typo. Filings up to roughly 2012 follow 21 CFR 807.92 as a
**lettered** list — `A. 510(k)Number:`, `B. Purpose for Submission:`, `C. Measurand:`,
`D. Type of Test:` — rather than the modern `Indications for Use` headings. Two changes were
needed:

1. the heading pattern accepted `1.` but not `B.`, so lettered headings never matched;
2. the value sits **on the heading line** in this format (`B. Purpose for Submission: New device`),
   so the inline tail is now kept;
3. and the 40-character minimum was dropping legitimately short field answers (`A. 510(k)Number:
   K100017` is seven characters and is exactly the fact a reader wants) — the floor now applies
   only to headings with no inline value, which is where the OMB scaffolding risk actually lives.

All three are locked by `test_the_pre_2013_lettered_format_still_sections`, and they improve the
text-layer documents too, because the older digitised filings use the same format.

## R&D direction: clinical trials, the lane that needs no credential

The patent lane dead-ends at a USPTO key that its own UI will not issue (see L4). Chasing it
further would have been polite stubbornness, because the question the platform has to answer —
*what is this company building next* — has a free, documented, keyless answer:

```bash
GET https://clinicaltrials.gov/api/v2/studies?query.spons=Medtronic&countTotal=true
```

Measured 2026-11-24 from the production host: **200**, `totalCount` **1,677**, and every record
carries the sponsor, the device names under study, the phase, the dates and the enrolment. A
patent is a claim made after the fact; a trial is work in progress. For an engineer choosing what
to benchmark against, the trial is the more useful document.

What one query actually returns, unedited:

```
2026-10-15  NCT07401901  [NOT_YET_RECRUITING]  Novel Medtronic NMX8 System · AID therapy · n=230
2026-09-11  NCT07321899  [RECRUITING]          Medtronic Intrepid™ transcatheter tricuspid valve · n=1,186
2025-08-28  NCT07120945  [ACTIVE_NOT_RECRUITING]  Hugo™ RAS in gynaecological surgery · n=70
```

### Three design rules, each earned

**The join key is the query itself.** Registry sponsors are subsidiaries — `Medtronic - MITG`,
`ARUM DENTISTRY Co., Ltd.` — and the register's legal name may not resemble them at all. A fuzzy
join across those strings produces confident nonsense, so a trial is attached to a company
because *that company was searched for*, recorded in `query_key` beside every row.

**The group fallback is labelled.** When the full legal name yields nothing, the first token
(`MEDTRONIC`) is tried and the answer is printed as **集团级 / group-level**. Same discipline as
model-exact versus brand-family in the failure lane: a weaker claim is allowed, an unlabelled one
is not.

**An empty table is not an import.** `tables_present()` requires rows, not merely a table. This
was measured the hard way: a `--summary` call created the empty tables, and the device view then
reported `no_patent_for_this_assignee` — "this company holds no patents" — when the truth was
"the bulk files were never imported". Two different facts, and only one of them is honest.

## The literature lane: two sources added, three traps found

The repository already had PubMed, Europe PMC and Crossref. Two gaps mattered, and both were
measured from the production host before anything was written (academic endpoints are *not*
geo-blocked, unlike every patent endpoint tried):

| Endpoint | Result 2026-11-24 |
|---|---|
| `api.medrxiv.org` / `api.biorxiv.org` | **200**, 30 records/page, `total` in the message block |
| `api.openalex.org/works` | **200**, 1,350,820 works for `catheter` |
| `api.semanticscholar.org` | 429 (rate-limited, not blocked) |
| `eutils.ncbi.nlm.nih.gov` | 200 |
| `api.crossref.org` | 200 |

### Preprints are the only records measured in days

Everything else in the literature lane indexes a paper after a journal accepted it. For "what is
this company working on right now" that is months late. `radar/adapters/preprints.py` reads both
servers over a date interval, filters to device-relevant categories client-side (a scope is a
**server**, not a category, or ten categories would mean ten identical downloads), and stops
paging on the `total` the API reports rather than on a fixed page count.

**Trap: a new `record_type` would have silently disabled the assessment.** The obvious design is
`record_type = "preprint"`. But `assessment.py` decides the entire publication path with an exact
`record_type == "publication"` test, and classifies authenticity with
`record_type in ("publication", "clinical_trial")`. A fourth type would have skipped both and
graded every preprint as `SECONDARY`. Preprints therefore carry `record_type="publication"` and
mark themselves in `payload["channel"]` and `extra["peer_review"]`, where nothing has to branch on
them to stay correct.

### OpenAlex is metered now, and that changes the design

Measured: an unkeyed request costs **$0.001** against a **$0.10/day budget shared by everyone on
the host's IP** — roughly 100 requests a day. A free key raises it to **$1/day**; the signup is one
`POST https://api.openalex.org/api-keys` with an email, and the key works after the user clicks the
mailed link. Response headers carry `x-ratelimit-remaining-usd` and `x-ratelimit-reset`.

So the lane is budgeted, not throttled: eight queries at two pages each is **16 requests (~$0.016)
per cycle**, leaving the shared budget for anything else on the host. `MAX_RESULTS_PER_SCOPE` is
400 for that reason, not for politeness.

**Trap: `grants` is not a valid `select` field.** Requesting it returns
`400 "grants is not a valid select field"`. The default therefore selects a small field set and
`MEDRADAR_OPENALEX_FULL_RECORDS=1` opts into unselected records (which do carry grants) at roughly
twenty times the bytes.

**Trap: "University College London" is not a company.** The first version matched legal-form
tokens as substrings, so `" CO"` matched inside `COLLEGE` and a university paper was attributed to
a vendor. Matching is now on whole tokens, and a test pins it.

OpenAlex's own value is that it answers three things the biomedical indexes cannot: **who**
(institution entities rather than free-text affiliations), **how much it mattered**
(`cited_by_count`, `counts_by_year`), and **who paid** (`grants[]`, which joins onto the NIH award
table this repository already builds).

## The openFDA page-size ceiling (a live defect this pass found)

Measured 2026-11-21 on `api.fda.gov/device/event.json`, keyless:

| limit | result |
|---:|---|
| 999 | HTTP 200, 999 rows |
| 1000 | HTTP 403 `{"error":{"code":"API_KEY_MISSING"}}` |

`openfda.py` and `openfda_recall.py` both shipped `PAGE_SIZE = 1000`, so they would have
received a 403 that the client classified as **"the operator refuses automated access"** — a
false access restriction in front of the user, and a source disabled for ever.

Two fixes, both in `medradar/radar/http.py`:

1. `OPENFDA_MAX_LIMIT_WITHOUT_KEY = 999`, used by every openFDA caller.
2. `CapabilityLimit` — a 403 whose body names a documented limit (`API_KEY_MISSING`,
   `OVER_LIMIT`) is raised as its own kind, not as `Refused`. The distinction is made from the
   error body on the **first** response; nothing about the request is retried, so the standing
   contract that a plain refusal is terminal on the first observation is unchanged.

Set `OPENFDA_API_KEY` to lift the ceiling: 120,000 requests/day and the full page size. That is
the difference between a 5,183-page UDI sweep taking six days and taking one afternoon.

## Deliberately not read, and why

These are recorded as not-started, not as unavailable. A reader should be able to tell the two
apart.

| Layer | Route | Why not now |
|---|---|---|
| L4 Patent | Google Patents BigQuery (`patents-public-data`), USPTO Open Data Portal, EPO OPS, USPTO Patent Assignment | Not probed in this pass. `search.patentsview.org` did not answer from this host, so it is recorded **UNVERIFIED**, not "blocked". The assignment database is the highest-value route here because it maps patent ownership to subsidiaries, which is the other half of the identity spine. |
| L6 Funding | SBIR/STTR (`api.www.sbir.gov`), USAspending v2, NSF Award Search | NIH RePORTER is now read. SBIR's public API answered **HTTP 403 Forbidden** to this client on 2026-11-21 (all three path variants tried), so it is recorded as key-gated-and-unverified rather than blocked; USAspending and NSF are not probed yet. |
| L7 Supply | VA ECAT, GSA/FPDS, USAspending contracts | Not probed. |
| L8 People | FDA advisory panels, RePORTER PIs, patent inventors, conference speakers, Open Payments | Needs L4 and L6 first: the same identifier resolves all of them. |

## What is explicitly not attempted

* No paywall, no login, no credential sharing.
* No rate-limit circumvention: a 429 is retried with `Retry-After` and backoff, bounded.
* No identity spoofing against a site that refuses anonymous access. The GE HealthCare adapter
  stays disabled for exactly this reason.
* Full text is fetched only where the source marks a record open access or in PMC.

## Reproducing the measurements

```bash
python - <<'PY'
from medradar.radar.http import PoliteFetcher, HostPolicy
from medradar.radar.adapters.maude import MaudeAdapter
f = PoliteFetcher(policies={"api.fda.gov": HostPolicy(requests_per_second=3.0)})
a = MaudeAdapter(None, product_codes=["DQY"])
page = a.fetch_page(type("C", (), {"fetcher": f, "watermark": None, "cursor": {},
                                   "adapter_state": {}, "emit": print})(),
                    a.plan(None)[0], None)
print(page.note)                                  # 999 of 42296 rows
print(sum(1 for r in page.records if r.extra["maude"]["narrative_chars"]))
PY
```
