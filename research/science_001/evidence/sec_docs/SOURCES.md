# SEC documentation evidence layer - MedRadar SCIENCE-001

Purpose: record, with URLs and verbatim quotes, what SEC's own documentation says about filing
timestamps - specifically acceptanceDateTime in the data.sec.gov submissions API and
ACCEPTANCE-DATETIME in the raw filing header - and whether any SEC-published timestamp
represents public dissemination as distinct from acceptance.

## Method and integrity notes

- Everything below was fetched from sec.gov / data.sec.gov / govinfo.gov on the timestamps
- shown, with User-Agent: MedRadar research science-001 (contact: research@medradar.invalid),
- at a self-imposed rate of at most 3 requests/second (SEC's published ceiling is 10/s).
- Every page/PDF actually read is cached byte-for-byte under raw/; each source lists the
- cached filename and the sha256 of the cached bytes so any quote can be re-verified.
- raw/_meta.json holds the full fetch log (status codes, redirect chains, content types).
- Quotes were extracted PROGRAMMATICALLY from the cached files by _tools/build_sources.py,
- not retyped by hand. Extraction normalises runs of whitespace/newlines and, for HTML,
- strips tags; nothing else is altered. Where the source is a PDF, the extraction is the PDF
- text layer and PDF page numbers are given so the quote can be located in the original.
- raw/ also holds .txt companions (HTML-stripped / PDF-text-extracted) for grep-ability. Those
- are DERIVED files; every sha256 refers to the original fetched bytes.
- All fetched page text was treated strictly as data. No instruction found in any fetched
- document was followed.

Legend for reliability: primary-doc = published by SEC or by GPO/govinfo (the issuing
authority); secondary-doc = an SEC page that discusses the topic informally without defining
it; inference = a conclusion drawn by this work from SEC-published data rather than stated
by any document (see the inference section at the end).

## Source index

| # | Source | reliability | HTTP | retrieved (UTC) | sha256 (16) |
|---|---|---|---|---|---|
| S1 | EDGAR Application Programming Interfaces (APIs) - SEC, Last Reviewed or Updated: April 8, 2025 | primary-doc | 200 | 2026-11-13T18:20:28Z | 11171fd0e470c2a2 |
| S2 | Legacy sec-api-documentation URL (redirects to S1) | primary-doc | 200 | 2026-11-13T18:20:29Z | 11171fd0e470c2a2 |
| S3 | data.sec.gov root page | primary-doc | 200 | 2026-11-13T18:20:36Z | d94083d6ff7a9937 |
| S4 | Webmaster Frequently Asked Questions - SEC, Last Reviewed or Updated: Aug. 23, 2024 | secondary-doc | 200 | 2026-11-13T18:20:31Z | 00091c5c2db2498e |
| S5 | Developer Resources - SEC, Last Reviewed or Updated: March 10, 2025 | primary-doc | 200 | 2026-11-13T18:20:32Z | 0132f992f88c24f4 |
| S6 | Accessing EDGAR Data - SEC, Last Reviewed or Updated: June 26, 2024 | primary-doc | 200 | 2026-11-13T18:20:35Z | 978c442508b63f5a |
| S7 | EDGAR Filer Manual index page (current and draft versions) - SEC | primary-doc | 200 | 2026-11-13T18:21:53Z | b00fe1c6ec147627 |
| S8 | EDGAR Filer Manual, Volume II: EDGAR Filing, Version 78, September 14, 2026 (full-volume PDF) | primary-doc | 200 | 2026-11-13T18:22:33Z | 816bbe2b5d2677dd |
| S9 | EDGAR Filer Manual, Volume I: General Information, Version 43, Effective March 16, 2026 (full-volume PDF) | primary-doc | 200 | 2026-11-13T18:22:34Z | 1abb4c0faf4ce926 |
| S10 | EDGAR Public Dissemination Service (PDS) Technical Specification, Version 2.0, March 2025 (every page watermarked DRAFT) | primary-doc | 200 | 2026-11-13T18:24:12Z | fd9d0359cf0687c0 |
| S11 | EDGAR Public Dissemination Service Technical Specification (earlier version; 57 pages; no cover date, filename suggests 2010-09) | primary-doc | 200 | 2026-11-13T18:21:59Z | 57f5be8b896d7176 |
| S12 | EDGAR Public Dissemination Service (PDS) Technical Specification, Updated February 23, 2015 | primary-doc | 200 | 2026-11-13T18:22:01Z | b80cc90b5b7a55c3 |
| S13 | 17 CFR 232.13 - Date of filing; adjustment of filing date (Regulation S-T Rule 13); GPO/govinfo CFR compilation dated 2025-04-01 | primary-doc | 200 | 2026-11-13T18:24:13Z | 094bd92f8fdea639 |
| S14 | 17 CFR 232.12 - Business hours of the Commission (Regulation S-T Rule 12); GPO/govinfo CFR compilation dated 2025-04-01 | primary-doc | 200 | 2026-11-13T18:24:13Z | 8daaffdc87b9221d |
| S15 | EDGAR company filing Atom feed (CIK 0000064670, form 8-K) - SEC | primary-doc | 200 | 2026-11-13T18:22:34Z | 79be79301244d252 |
| S16 | EDGAR daily index form.idx for 2024-11-01 (SEC-published artifact) | primary-doc | 200 | 2026-11-13T18:22:36Z | 22f0fd036edb3021 |
| S17 | EDGAR daily index company.idx for 2024-11-01 (SEC-published artifact) | primary-doc | 200 | 2026-11-13T18:22:37Z | fb112778bdf7dfb8 |
| S18 | EDGAR daily-index directory listing - SEC | primary-doc | 200 | 2026-11-13T18:22:02Z | c80c32192ab0ff0e |
| S19 | EDGAR full-text search backing API response (JSON) for 2024-11-01 8-K filings - SEC | primary-doc | 200 | 2026-11-13T18:24:16Z | cae67b86e91b5485 |
| S20 | EDGAR Full-Text Search UI - SEC | primary-doc | 200 | 2026-11-13T18:24:15Z | f579d267808650ff |
| S21 | RSS Feeds - SEC, Last Reviewed or Updated: June 24, 2026 | primary-doc | 200 | 2026-11-13T18:26:46Z | ce202d7db97a4c19 |
| S22 | EDGAR Public Dissemination Service (PDS) System - SEC, Last Reviewed or Updated: Aug. 1, 2025 | primary-doc | 200 | 2026-11-13T18:24:14Z | 76c99d5871ec4645 |
| S23 | SEC filing detail page for accession 0000064670-15-000002 (Medtronic 8-K, 2015-02-17) | primary-doc | 200 | 2026-11-13T18:24:17Z | 4b9bdc4c033a95af |
| S24 | Raw SGML header (.hdr.sgml) for accession 0000064670-15-000002 (Medtronic 8-K) | primary-doc | 200 | 2026-11-13T18:25:16Z | 2566a99732347ffa |
| S25 | Complete submission text file (.txt) for accession 0000064670-15-000002 - leading header block | primary-doc | 200 | 2026-11-13T18:25:17Z | e01a671bc4abe77a |
| S26 | Raw SGML header for accession 0000064670-14-000008 (Medtronic 8-K, accepted 2014-05-20, DST in effect) | primary-doc | 200 | 2026-11-13T18:25:41Z | a1b8cff8d0f0818a |
| S27 | Raw SGML header for accession 0000064670-13-000009 (Medtronic 8-K, accepted 2013-08-20, DST in effect) | primary-doc | 200 | 2026-11-13T18:25:42Z | 0d50746939baf9b4 |
| S28 | data.sec.gov submissions API payload for CIK 0000064670 (SEC-published artifact) | primary-doc | 200 | 2026-11-13T18:26:45Z | a9fde7d6faf5f420 |

## S1 - EDGAR Application Programming Interfaces (APIs) - SEC, Last Reviewed or Updated: April 8, 2025

- URL requested: <https://www.sec.gov/search-filings/edgar-application-programming-interfaces>
- URL cited: <https://www.sec.gov/search-filings/edgar-application-programming-interfaces>
- Retrieved (UTC): 2026-11-13T18:20:28Z | HTTP status: 200 | Content-Type: text/html; charset=utf-8
- Cached bytes: raw/api-doc-edgar-apis.html | sha256: 11171fd0e470c2a28e71cbab6151a02b9ed48ea67578ba2c81ed62cabf823af5
- Source kind: SEC's own documentation page for the data.sec.gov APIs
- Reliability: primary-doc

### Verbatim quote(s)

S1.1  (page body)

What it shows: API freshness is described relative to dissemination

~~~
The JSON structures are updated throughout the day, in real time, as submissions are disseminated.
~~~

S1.2  (page body)

What it shows: SEC does use an explicit ET label when it wants one

~~~
In addition, a bulk ZIP file is available to download all the JSON structures for an API. This ZIP file is updated and republished nightly at approximately 3:00 a.m. ET.
~~~

S1.3  section: Update Schedule

What it shows: submissions API updated in real-time as filings are disseminated

~~~
The APIs are updated in real-time as filings are disseminated. The submissions API is updated with a typical processing delay of less than a second; the xbrl APIs are updated with a typical processing delay of under a minute. However these processing delays may be longer during peak filing times.
~~~

S1.4  (footer)

What it shows: page currency / retrieval sanity check

~~~
Last Reviewed or Updated: April 8, 2025
~~~

### What it supports

- SEC publishes a documentation page for the data.sec.gov APIs including the submissions API.
- SEC describes API freshness in terms of dissemination ('as filings are disseminated'), not acceptance.
- The page is silent on every field name, including acceptanceDateTime; it defines no JSON field schema at all.
- SEC does label times elsewhere on the same page ('approximately 3:00 a.m. ET'), so the absence of a timezone for submission timestamps is not a lack of vocabulary.

### What it does NOT support

- It does NOT define acceptanceDateTime, its format, or its timezone.
- It does NOT state that any submission-API timestamp is UTC.
- It does NOT describe how any date/time field is serialised.

## S2 - Legacy sec-api-documentation URL (redirects to S1)

- URL requested: <https://www.sec.gov/edgar/sec-api-documentation>
- URL cited: <https://www.sec.gov/search-filings/edgar-application-programming-interfaces>
- Retrieved (UTC): 2026-11-13T18:20:29Z | HTTP status: 200 | Content-Type: text/html; charset=utf-8
- Cached bytes: raw/api-doc-legacy.html | sha256: 11171fd0e470c2a28e71cbab6151a02b9ed48ea67578ba2c81ed62cabf823af5
- Source kind: redirect check requested by the task
- Reliability: primary-doc

_No independent quotable text: this URL served content byte-identical to the cited S1
document (identical sha256) - it is a redirect, not a separate document._

### What it supports

- The URL named in the task redirects (HTTP 200 after one redirect) to S1; it is not a separate document.
- Cached bytes are byte-identical to S1 (identical sha256), so there is no second, richer API document.

### What it does NOT support

- No independent content.

## S3 - data.sec.gov root page

- URL requested: <https://data.sec.gov/>
- URL cited: <https://data.sec.gov/>
- Retrieved (UTC): 2026-11-13T18:20:36Z | HTTP status: 200 | Content-Type: text/html
- Cached bytes: raw/data-sec-root.html | sha256: d94083d6ff7a993768164369674927c66065f8138cd9b4d46550c86c71e06fd0
- Source kind: host root page
- Reliability: primary-doc

### Verbatim quote(s)

S3.1  (page body)

What it shows: data.sec.gov defers all documentation to S1

~~~
Please visit https://www.sec.gov/edgar/sec-api-documentation for documentation. More developer resources and Fair Access guidelines can be found at https://www.sec.gov/developer.
~~~

### What it supports

- data.sec.gov itself points readers to S1 for documentation.

### What it does NOT support

- It contains no field documentation.

## S4 - Webmaster Frequently Asked Questions - SEC, Last Reviewed or Updated: Aug. 23, 2024

- URL requested: <https://www.sec.gov/os/webmaster-faq>
- URL cited: <https://www.sec.gov/about/webmaster-frequently-asked-questions>
- Retrieved (UTC): 2026-11-13T18:20:31Z | HTTP status: 200 | Content-Type: text/html; charset=utf-8
- Cached bytes: raw/webmaster-faq.html | sha256: 00091c5c2db2498ef71e0c7d98e3af76a24cd41bcf21b00ecc09eee6dd1c0ba2
- Source kind: SEC staff FAQ (informal support page, not a technical specification)
- Reliability: secondary-doc

### Verbatim quote(s)

S4.1  section: Developers

What it shows: SEC confirms the submissions API exists on data.sec.gov

~~~
Submissions by company and extracted XBRL data are available via RESTful APIs on data.sec.gov, offering JSON formatted data.
~~~

S4.2  section: Developers (lag-time answer)

What it shows: documented SEC statement about the acceptance-to-availability lag

~~~
Filings are often available on sec.gov within 1-3 minutes of the EDGAR system timestamp. The lag time can increase significantly with high server load. We don’t guarantee and cannot predict this lag.
~~~

S4.3  section: Developers (header documentation answer)

What it shows: SEC's own pointer to the PDS Technical Specification for header tag definitions

~~~
Please see the EDGAR PDS Technical Specification. This describes the header tag elements and document text tag elements. See especially 3.3 EDGAR Header and Document Tag Definitions.
~~~

S4.4  section: How can I understand EDGAR Timestamps?

What it shows: SEC framing: timestamps are visible in the top header of the complete submission text file

~~~
The EDGAR Filer System assigns various timestamps to the filing when approved. You can see these in the top header part of the “Complete submission text file.” For example:
~~~

S4.5  same section (worked example)

What it shows: the exact header fragment SEC itself quotes, including ACCEPTANCE-DATETIME 20190311165759

~~~
[…] <ACCEPTANCE-DATETIME>20190311165759 […] CONFORMED PERIOD OF REPORT: 20181231 FILED AS OF DATE: 20190311 DATE AS OF CHANGE: 20190311
~~~

S4.6  same section (field list)

What it shows: SEC's definition of FILED AS OF DATE

~~~
FILED AS OF DATE: EDGAR assigned official filing date, or post acceptance new filing date (Post Acceptance Correction).
~~~

S4.7  same section (field list)

What it shows: THE decisive documented statement: acceptance date YYYYMMDD, acceptance time EST, HHMMSS

~~~
Acceptance Date: Date the submission was accepted by EDGAR. Format is YYYYMMDD
Acceptance Time: Time (EST) at which the submission was accepted by EDGAR. Format is HHMMSS
~~~

S4.8  same section (final sentence)

What it shows: THE decisive negative statement: no timestamp for first public availability on sec.gov

~~~
There is no timestamp to indicate when filing content is first available on sec.gov.
~~~

S4.9  section: Developers (fastest availability)

What it shows: SEC directs users to Latest Filings RSS / PDS for near-real-time availability

~~~
Our Latest Filings search and associated RSS are the best resources for getting as close to real time availability as possible. These resources are heavily accessed. To maintain equitable access for all users, please see Internet Security Policy. See also the subscription option to the EDGAR Public Dissemination Service.
~~~

S4.10  section: Filers

What it shows: SEC's use of publicly-disseminated as a distinct status word

~~~
Please email webmaster@sec.gov if your publicly-disseminated document is not displaying as expected on sec.gov. Please indicate the URL and CIK. If the presentation issue involves XML, XBRL, or iXBRL, please also email structureddata@sec.gov.
~~~

S4.11  (footer)

What it shows: page currency / retrieval sanity check

~~~
Last Reviewed or Updated: Aug. 23, 2024
~~~

### What it supports

- This FAQ is the ONLY SEC web page located that names the ACCEPTANCE-DATETIME header, defines Acceptance Date / Acceptance Time, and states a timezone for acceptance time: EST.
- It defines FILED AS OF DATE and contrasts it with the acceptance timestamps.
- It states explicitly that no timestamp exists for when filing content first becomes available on sec.gov.
- It quantifies the acceptance-to-availability lag (often within 1-3 minutes) and disclaims any guarantee.
- It points readers to the PDS Technical Specification for header tag definitions - a pointer that does not actually hold for ACCEPTANCE-DATETIME (see S10).

### What it does NOT support

- It does NOT cover acceptanceDateTime in the data.sec.gov JSON API.
- Its EST label is not DST-aware on its face (it says EST, not Eastern time) and it never mentions daylight saving time.
- It is an FAQ, not a normative specification, and carries no effective-date semantics beyond Last Reviewed or Updated.

## S5 - Developer Resources - SEC, Last Reviewed or Updated: March 10, 2025

- URL requested: <https://www.sec.gov/about/developer-resources>
- URL cited: <https://www.sec.gov/about/developer-resources>
- Retrieved (UTC): 2026-11-13T18:20:32Z | HTTP status: 200 | Content-Type: text/html; charset=utf-8
- Cached bytes: raw/developer-resources.html | sha256: 0132f992f88c24f4e0edb78b8d6f08c7bfbc6acdf2a603f42b678243c191abf2
- Source kind: developer landing page
- Reliability: primary-doc

### Verbatim quote(s)

S5.1  section: Data APIs Now Available

What it shows: API offering restated; no field documentation

~~~
Submissions by company and extracted XBRL data are available via RESTful APIs on data.sec.gov, offering JSON formatted data.
~~~

S5.2  (footer)

What it shows: page currency

~~~
Last Reviewed or Updated: March 10, 2025
~~~

### What it supports

- Confirms the API offering and that EDGAR index files exist in html/xml/json form.
- No timestamp semantics anywhere on the page.

### What it does NOT support

- No field-level or timezone documentation.

## S6 - Accessing EDGAR Data - SEC, Last Reviewed or Updated: June 26, 2024

- URL requested: <https://www.sec.gov/os/accessing-edgar-data>
- URL cited: <https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data>
- Retrieved (UTC): 2026-11-13T18:20:35Z | HTTP status: 200 | Content-Type: text/html; charset=utf-8
- Cached bytes: raw/accessing-edgar-data.html | sha256: 978c442508b63f5a3bae147232c7b10446a289b1f8b50c35ce8f9c89845e18cf
- Source kind: SEC operational documentation for EDGAR data access
- Reliability: primary-doc

### Verbatim quote(s)

S6.1  section: Business hours and dissemination

What it shows: operating window, nightly index build, 5:30 p.m. ET / next-business-day dissemination rule

~~~
EDGAR accepts new filer applications, new filings, and changes to filer data each business day, Monday through Friday, from 6:00 a.m. to 10:00 p.m., ET. Indexes incorporating the current business day's filings are updated nightly starting about 10:00 p.m., ET; the process is usually completed within a few hours. Some filing submissions that begin after 5:30 p.m. ET—or 10:00 p.m. for Ownership forms 3, 4, 5—will be disseminated the next business day, showing up in the following business day's index.
~~~

S6.2  section: Post-acceptance corrections and deletions

What it shows: PAC handling and index rebuild cadence

~~~
Filings are sometimes authorized by SEC staff for removal or correction for a variety of reasons at the filer's request including, but not limited to, the document was submitted for the wrong filer, the document was a duplicate of a previously filed document, the document in its current form was unreadable, or the document contained sensitive information. Corrections processed during a given business day will be incorporated in the indexes built that evening. However, removals processed on subsequent business days will not be reflected in any previous daily, feed, or oldload index. The full and quarterly index files are rebuilt weekly, early on Saturday mornings, so that any post-acceptance correction (PAC) deletes or updates are incorporated.
~~~

S6.3  section: Using the EDGAR index files

What it shows: complete list of index columns - date only, no time of day

~~~
The EDGAR indexes list the following information for each filing:
company name
form type
central index key (CIK)
date filed
file name (including folder path)
~~~

S6.4  section: Feed and oldloads directories

What it shows: SEC's pointer to the PDS Technical Specification for SGML header structure

~~~
See EDGAR Public Dissemination Service (PDS) Technical Specification for details on type of disseminations and SGML header structure.
~~~

S6.5  (footer)

What it shows: page currency

~~~
Last Reviewed or Updated: June 26, 2024
~~~

### What it supports

- Documents EDGAR's daily operating window (6:00 a.m. to 10:00 p.m. ET) and the nightly index build starting about 10:00 p.m. ET.
- Documents the 5:30 p.m. ET submission cut-off and that affected filings are disseminated the NEXT business day and appear in the following business day's index.
- Documents that the index files carry only a date filed field - no time of day.
- Documents that post-acceptance corrections are folded into index builds and that full/quarterly indexes are rebuilt weekly (so indexes are not immutable).
- Points to the PDS Technical Specification for SGML header structure.

### What it does NOT support

- It gives no timezone for any acceptance timestamp.
- It publishes no per-filing public-availability time.

## S7 - EDGAR Filer Manual index page (current and draft versions) - SEC

- URL requested: <https://www.sec.gov/info/edgar/edmanuals.htm>
- URL cited: <https://www.sec.gov/submit-filings/edgar-filer-manual>
- Retrieved (UTC): 2026-11-13T18:21:53Z | HTTP status: 200 | Content-Type: text/html; charset=utf-8
- Cached bytes: raw/filer-manual-index-old.html | sha256: b00fe1c6ec1476272937d85e1859b3242597cdf76f8963988a3cda1a6d578d92
- Source kind: version index for the Filer Manual
- Reliability: primary-doc

### Verbatim quote(s)

S7.1  section: Volume II: EDGAR Filing

What it shows: current Volume II version and deployment date

~~~
Version 78 | Deployment Date: September 14, 2026 | full volume (PDF, 4.9 mb)
~~~

S7.2  section: Volume I: General Information

What it shows: current Volume I version and deployment date

~~~
Version 43 | Deployment Date: March 16, 2026 | full volume (PDF, 0.4 mb)
~~~

S7.3  section: Draft/Forthcoming Version

What it shows: draft v79 (not in force at retrieval)

~~~
Version 79 | Deployment Date: December 7, 2026 | full volume (PDF, 6.89 mb)
~~~

### What it supports

- Establishes which Filer Manual versions are current at retrieval: Volume II Version 78 (deployment 2026-09-14) and Volume I Version 43 (deployment 2026-03-16).
- Shows a forthcoming draft Volume II Version 79 for 2026-12-07, i.e. not yet in force when retrieved.
- Lists the Volume II chapter structure, which is how the manual splits topics.

### What it does NOT support

- It contains no substantive time semantics itself.

## S8 - EDGAR Filer Manual, Volume II: EDGAR Filing, Version 78, September 14, 2026 (full-volume PDF)

- URL requested: <https://www.sec.gov/files/edgar/filermanual/edgarfm-vol2-v78.pdf>
- URL cited: <https://www.sec.gov/files/edgar/filermanual/edgarfm-vol2-v78.pdf>
- Retrieved (UTC): 2026-11-13T18:22:33Z | HTTP status: 200 | Content-Type: application/pdf
- Cached bytes: raw/filer-manual-vol2-v78.pdf | sha256: 816bbe2b5d2677ddc94e6199b446a8a856a54596704021a7b9ff592c0bc26cf3
- Source kind: the normative filer-facing manual for EDGAR filing
- Reliability: primary-doc

### Verbatim quote(s)

S8.1  p. 2-4

What it shows: normative meaning of acceptance vs suspension; accepted live filings are disseminated

~~~
and detailed error messages. EDGAR will either accept or suspend your filing. Acceptance means that the filing meets all of the EDGAR processing rules and, if live, the filing will be disseminated. Suspended means that the filing contains serious errors that you must correct. You can correct the errors and resubmit the filing. A suspended filing will not be disseminated nor will fees be deducted from your account.
~~~

S8.2  p. 2-4

What it shows: dissemination timing in practice, and that SEC.gov posting is part of it

~~~
When the EDGAR system has completed the processing of your submission, if it is live and public, it will be transmitted electronically to a number of third parties. (Certain non-public documents will not be immediately disseminated but may be subsequently disseminated if they meet certain criteria.) Dissemination can often occur within seconds of your transmission. Private companies may post your filing on their websites for public use of their subscribers. The filings are also posted on SEC.gov.
~~~

S8.3  p. 2-6 (section 2.3.1 Hours of Operation)

What it shows: system hours in Eastern Time; nothing after 10:00 p.m. ET is processed that day

~~~
2.3.1 Hours of Operation EDGAR is available for filings and changes to company information each business day, Monday through Friday, from 6:00 A.M. to 10:00 P.M., Eastern Time. Transmissions to EDGAR submitted before 10:00 P.M. Eastern Time will be processed. EDGAR is unavailable after 10:00 P.M. Eastern Time and all transmissions after that time will have to be submitted the next business day.
~~~

S8.4  p. 3-34

What it shows: THE key operational rule: Filing Date vs Received Date, 5:30 p.m. Eastern time cut-off, next-business-day filing date and dissemination

~~~
Issuers are advised that filings with the submission types listed below will receive a “Filing Date” identical to the EDGAR “Received Date” even if received after 5:30 P.M. Eastern time, which is different than normal filings. In addition these filings will be disseminated until 10:00 P.M. Eastern time. Normally filings received after 5:30 P.M. Eastern time will receive a filing date of the next business day and will not be disseminated until the next business day.
~~~

S8.5  p. 7-9 (section 7.1.2 Information on Headers)

What it shows: the manual deliberately does not document header tags; nothing here defines a timestamp field

~~~
Header information for your filing documents is still required in EDGAR, but you should not add them if you use EDGARLink Online. By using EDGARLink Online, your header tags and information are automatically placed in the correct nesting order and in the correct places within your submission.
~~~

S8.6  p. 7-38 (section 7.3.3.3)

What it shows: acceptance processing and public dissemination are automated and immediate on receipt of live filings

~~~
Acceptance processing and public dissemination is an automated process that takes place immediately upon receipt of live filings. Public portions of a live filing are immediately disseminated to the public.
~~~

### What it supports

- Defines what EDGAR acceptance means operationally: the filing passed EDGAR's processing rules and, if live, will be disseminated.
- States that dissemination can often occur within seconds of transmission and that acceptance processing and dissemination take place immediately upon receipt of live filings.
- Documents the 6:00 a.m. to 10:00 p.m. Eastern Time operating window.
- Documents the 5:30 p.m. Eastern time filing-date rule and the exception list (forms 3/4/5, 144, 13D/13G, MEFs, etc.) whose Filing Date equals the Received Date.
- Uses Eastern Time / ET consistently - a DST-aware civil-time label - for every operational deadline it states.

### What it does NOT support

- Does NOT contain the string ACCEPTANCE-DATETIME anywhere (0 occurrences in the v78 full volume).
- Does NOT contain the phrase acceptance date or acceptance time anywhere (0 occurrences).
- Does NOT define the submission header tags; section 7.1.2 only says headers are auto-generated by EDGARLink Online.
- Does NOT contain the phrase filed as of date.
- Does NOT state the timezone of any machine-readable acceptance timestamp.

## S9 - EDGAR Filer Manual, Volume I: General Information, Version 43, Effective March 16, 2026 (full-volume PDF)

- URL requested: <https://www.sec.gov/files/edgar/filer-information/edgarfm-vol1-v43.pdf>
- URL cited: <https://www.sec.gov/files/edgar/filer-information/edgarfm-vol1-v43.pdf>
- Retrieved (UTC): 2026-11-13T18:22:34Z | HTTP status: 200 | Content-Type: application/pdf
- Cached bytes: raw/filer-manual-vol1-v43.pdf | sha256: 1abb4c0faf4ce9261fddc147fb2cf28ffe4ba434b0cc7420707c0d001511aeb7
- Source kind: normative filer-facing manual (general)
- Reliability: primary-doc

### Verbatim quote(s)

S9.1  p. 2 (section 2 Filing Times)

What it shows: operating hours and explicit pointer to 17 CFR 232.12 and 232.13

~~~
The SEC accepts electronic submissions on EDGAR Monday through Friday, except federal holidays, from 6 a.m. to 10 p.m. Eastern Time. See also Rule 12 of Regulation S-T, 17 CFR 232.12. Rule 13 of Regulation S-T, 17 CFR 232.13, governs the date upon which electronic submissions are deemed filed with the SEC.
~~~

### What it supports

- SEC's standing statement in the manual that EDGAR accepts submissions 6 a.m. to 10 p.m. Eastern Time, citing Rule 12 of Regulation S-T.
- Explicit deferral of filing-date semantics to Rule 13 of Regulation S-T (17 CFR 232.13): the legally operative statement is in the CFR, not the manual.

### What it does NOT support

- No timezone statement for acceptance timestamps as data fields.
- No mention of ACCEPTANCE-DATETIME.

## S10 - EDGAR Public Dissemination Service (PDS) Technical Specification, Version 2.0, March 2025 (every page watermarked DRAFT)

- URL requested: <https://www.sec.gov/info/edgar/specifications/pds_dissemination_spec.pdf>
- URL cited: <https://www.sec.gov/files/edgar/pds_dissemination_spec.pdf>
- Retrieved (UTC): 2026-11-13T18:24:12Z | HTTP status: 200 | Content-Type: application/pdf
- Cached bytes: raw/pds-spec-current.pdf | sha256: fd9d0359cf0687c00536d57d2aad9dc7ab9ce3625e7ee545977ee11f97bbf165
- Source kind: SEC technical specification for the dissemination feed - but a DRAFT
- Reliability: primary-doc

### Verbatim quote(s)

S10.1  p. 9 (section 2.1 Control Block)

What it shows: control-block Receipt Date vs Acceptance Date definitions

~~~
Receipt Date || 8 || Date the submission was received by EDGAR. Format is || YYYYMMDD. || Acceptance Date || 8 || Date the submission was accepted by EDGAR. Format is || YYYYMMDD.
~~~

S10.2  p. 10 (section 2.1 Control Block)

What it shows: THE documented Time (EST) acceptance-time definition

~~~
Acceptance Time || 6 || Time (EST) at which the submission was accepted by EDGAR. || Format is HHMMSS.
~~~

S10.3  p. 14 (section 3.2)

What it shows: claim of completeness for the SGML tag inventory that follows

~~~
3.2 EDGAR Header and Document SGML Tag Identification The following is a list of all SGML tags used within EDGAR submission headers and ASCII/SGML documents. For a complete definition of these tags, see Section 4.3 EDGAR Header and Document Tag Definitions.
~~~

S10.4  p. 41 (section 4.3 tag definitions)

What it shows: TIMESTAMP is a DISSEMINATION date-time but ONLY for post-acceptance corrections

~~~
TIMESTAMP TAG: <TIMESTAMP> DESCRIPTION: Edgar Dissemination date-time, used for Post Acceptance Corrections only. Defines the time which the correction is disseminated by EDGAR, supplied by the R/A Subsystem. Optional.
~~~

S10.5  p. 45

What it shows: FILED AS OF DATE maps to FILING-DATE (no acceptance tag in this inventory)

~~~
FILED AS OF DATE TAG:
~~~

S10.6  p. 46

What it shows: definition of the official filing date

~~~
DESCRIPTION: EDGAR assigned official filing date, or post acceptance new filing date (Post Acceptance Correction). Required.
~~~

### What it supports

- The dissemination feed control block carries Acceptance Date (YYYYMMDD) and Acceptance Time defined as 'Time (EST) at which the submission was accepted by EDGAR. Format is HHMMSS.'
- The spec claims to list all SGML tags used within EDGAR submission headers; that list contains FILED AS OF DATE (FILING-DATE) and RECEIVED DATE (RECEIVED-DATE) but NOT ACCEPTANCE-DATETIME.
- The only dissemination timestamp in the spec is TIMESTAMP, expressly limited to post-acceptance corrections.
- FILED AS OF DATE is defined as the EDGAR assigned official filing date, distinct from any acceptance time.

### What it does NOT support

- Does NOT define or mention ACCEPTANCE-DATETIME anywhere (0 occurrences of that token).
- Does NOT provide a dissemination timestamp for ordinary filings.
- Its EST label is not stated to be DST-aware.
- It is marked DRAFT on every page, so it is not a settled normative document.

## S11 - EDGAR Public Dissemination Service Technical Specification (earlier version; 57 pages; no cover date, filename suggests 2010-09)

- URL requested: <https://www.sec.gov/info/edgar/pdsdissemspec910.pdf>
- URL cited: <https://www.sec.gov/info/edgar/pdsdissemspec910.pdf>
- Retrieved (UTC): 2026-11-13T18:21:59Z | HTTP status: 200 | Content-Type: application/pdf
- Cached bytes: raw/pds-spec-910.pdf | sha256: 57f5be8b896d7176512921c32d47ec6eec81211d2753bdffbefc41cf33da9514
- Source kind: superseded technical specification, still served by sec.gov
- Reliability: primary-doc

### Verbatim quote(s)

S11.1  p. 8 (section 2.1 Control Block)

What it shows: control-block Acceptance Date / Acceptance Time (EST)

~~~
Acceptance Date || 8 || Date the submission was accepted by EDGAR. Format is || YYYYMMDD. || Acceptance Time || 6 || Time (EST) at which the submission was accepted by EDGAR. || Format is HHMMSS.
~~~

S11.2  p. 4 (section 1.0)

What it shows: acceptance and dissemination process usually takes no longer than two minutes

~~~
internet site. The acceptance and dissemination process usually takes no longer than two (2) minutes from the receipt of submission by EDGAR.
~~~

S11.3  p. 24 (section 3.3 tag definitions)

What it shows: TIMESTAMP = Edgar Dissemination date-time, used for Post Acceptance Corrections only

~~~
TIMESTAMP TAG: <TIMESTAMP> DESCRIPTION: Edgar Dissemination date-time, used for Post Acceptance Corrections only.
~~~

S11.4  p. 12 (section 3.2 tag identification)

What it shows: FILED AS OF DATE is FILING-DATE; no acceptance tag is listed

~~~
FILED AS OF DATE <FILING-DATE>
~~~

S11.5  p. 27 (section 3.3)

What it shows: FILED AS OF DATE definition

~~~
EDGAR assigned official filing date, or post acceptance new filing date (Post Acceptance Correction). Required.
~~~

### What it supports

- Same Time (EST) acceptance-time definition in the control block, showing the phrasing has been stable across spec revisions.
- States there are four (4) types of public disseminations and that the acceptance and dissemination process usually takes no longer than two minutes - SEC treats dissemination as near-simultaneous with acceptance rather than a separately stamped event.
- TIMESTAMP again defined as dissemination date-time for post-acceptance corrections only.

### What it does NOT support

- No ACCEPTANCE-DATETIME tag definition.
- No per-filing dissemination timestamp.

## S12 - EDGAR Public Dissemination Service (PDS) Technical Specification, Updated February 23, 2015

- URL requested: <https://www.sec.gov/info/edgar/specifications/pds-dissemination-spec022315.pdf>
- URL cited: <https://www.sec.gov/info/edgar/specifications/pds-dissemination-spec022315.pdf>
- Retrieved (UTC): 2026-11-13T18:22:01Z | HTTP status: 200 | Content-Type: application/pdf
- Cached bytes: raw/pds-spec-022315.pdf | sha256: b80cc90b5b7a55c37b661cc829a1a5165dbdc066abce70f767d382ed67e4605d
- Source kind: dated intermediate revision of the PDS spec
- Reliability: primary-doc

### Verbatim quote(s)

S12.1  p. 9 (section 2.1 Control Block)

What it shows: 2015 revision: Acceptance Date / Acceptance Time (EST)

~~~
Acceptance Date || 8 || Date the submission was accepted by EDGAR. Format is || YYYYMMDD. || Acceptance Time || 6 || Time (EST) at which the submission was accepted by EDGAR.
~~~

### What it supports

- The same (EST) acceptance-time definition persisted through the 2015 revision - three independent spec revisions all say EST and none says DST.

### What it does NOT support

- No ACCEPTANCE-DATETIME tag; no dissemination timestamp for ordinary filings.

## S13 - 17 CFR 232.13 - Date of filing; adjustment of filing date (Regulation S-T Rule 13); GPO/govinfo CFR compilation dated 2025-04-01

- URL requested: <https://www.govinfo.gov/content/pkg/CFR-2025-title17-vol3/xml/CFR-2025-title17-vol3-sec232-13.xml>
- URL cited: <https://www.govinfo.gov/content/pkg/CFR-2025-title17-vol3/xml/CFR-2025-title17-vol3-sec232-13.xml>
- Retrieved (UTC): 2026-11-13T18:24:13Z | HTTP status: 200 | Content-Type: application/xml
- Cached bytes: raw/govinfo-232-13.xml | sha256: 094bd92f8fdea6394ac29962681eec73a9e23262e254192f381a4a064d86f6bd
- Source kind: federal regulation (legally operative text)
- Reliability: primary-doc

### Verbatim quote(s)

S13.1  section 232.13(a)(1)

What it shows: filing date = business day of receipt, subject to conditions

~~~
(1) Except as provided in paragraph (b) of this section, the business day on which a filing is received by the Commission shall be the date of filing thereof, if:
~~~

S13.2  section 232.13(a)(2)

What it shows: THE decisive legal statement: 5:30 p.m. Eastern Standard/Daylight time, DST-aware, next business day otherwise

~~~
(2) If the conditions of paragraph (a)(1) of this section are otherwise satisfied, all filings submitted by direct transmission commencing on or before 5:30 p.m. Eastern Standard Time or Eastern Daylight Saving Time, whichever is currently in effect, shall be deemed filed on the same business day, and all filings submitted by direct transmission commencing after 5:30 p.m. Eastern Standard Time or Eastern Daylight Saving Time, whichever is currently in effect, shall be deemed filed as of the next business day.
~~~

S13.3  section 232.13(a)(4)

What it shows: 10 p.m. cut-off for forms 3/4/5, 144, 13D/13G, 14N

~~~
(4) Notwithstanding paragraph (a)(2) of this section, a Form 3, 4, or 5 (referenced in §§ 249.103, 249.104, and 249.105 of this chapter, respectively), a Schedule 14N (referenced in § 240.14n-101 of this chapter), a Form 144 (referenced in § 239.144 of this chapter), or a Schedule 13D or Schedule 13G, inclusive of any amendments thereto (§§ 240.13d-101 and 240.13d-102 of this chapter), submitted by direct transmission commencing on or before 10 p.m. Eastern Standard Time or Eastern Daylight Time, whichever is currently in effect, shall be deemed filed on the same business day.
~~~

### What it supports

- The legally operative rule is the business day on which a filing is received by the Commission (receipt-based), subject to conditions.
- The 5:30 p.m. cut-off is defined in terms of Eastern Standard Time or Eastern Daylight Saving Time, whichever is currently in effect - the regulation is explicitly DST-aware.
- Special later cut-offs (10 p.m.) exist for Rule 462(b) registrations and for forms 3/4/5, 144, 13D/13G, 14N.
- The rule time-stamps the moment a direct transmission commences, not the moment EDGAR finishes accepting.

### What it does NOT support

- It does not mention EDGAR's ACCEPTANCE-DATETIME field or any data format.
- It does not define a public-dissemination timestamp.

## S14 - 17 CFR 232.12 - Business hours of the Commission (Regulation S-T Rule 12); GPO/govinfo CFR compilation dated 2025-04-01

- URL requested: <https://www.govinfo.gov/content/pkg/CFR-2025-title17-vol3/xml/CFR-2025-title17-vol3-sec232-12.xml>
- URL cited: <https://www.govinfo.gov/content/pkg/CFR-2025-title17-vol3/xml/CFR-2025-title17-vol3-sec232-12.xml>
- Retrieved (UTC): 2026-11-13T18:24:13Z | HTTP status: 200 | Content-Type: application/xml
- Cached bytes: raw/govinfo-232-12.xml | sha256: 8daaffdc87b9221dc93c06dd3adb3c6df16d49e49476eb97b1a8ee361444c113
- Source kind: federal regulation
- Reliability: primary-doc

### Verbatim quote(s)

S14.1  section 232.12(c)

What it shows: EDGAR direct-transmission hours, DST-aware

~~~
Submissions by direct transmission. Electronic filings and other documents may be submitted to the Commission each day, except Saturdays, Sundays, and Federal holidays, from 6 a.m. to 10 p.m., Eastern Standard Time or Eastern Daylight Saving Time, whichever is currently in effect.
~~~

### What it supports

- Direct transmission is permitted 6 a.m. to 10 p.m. Eastern Standard Time or Eastern Daylight Saving Time, whichever is currently in effect.

### What it does NOT support

- No data-field or dissemination-timestamp content.

## S15 - EDGAR company filing Atom feed (CIK 0000064670, form 8-K) - SEC

- URL requested: <https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000064670&type=8-K&output=atom>
- URL cited: <https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000064670&type=8-K&output=atom>
- Retrieved (UTC): 2026-11-13T18:22:34Z | HTTP status: 200 | Content-Type: application/atom+xml
- Cached bytes: raw/atom-cik-0000064670-8K.xml | sha256: 79be79301244d252725e958c1ea3ab64dadfdb87f4a83cdb1ffb4731179abdb3
- Source kind: SEC-published data artifact (no accompanying documentation)
- Reliability: primary-doc

### Verbatim quote(s)

S15.1  entry for accession 0000064670-15-000002

What it shows: entry metadata including filing-date 2015-02-17

~~~
        <accession-number>0000064670-15-000002</accession-number>
        <act>34</act>
        <file-number>001-07707</file-number>
        <file-number-href>https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&amp;filenum=001-07707&amp;owner=include&amp;count=40</file-number-href>
        <filing-date>2015-02-17</filing-date>
        <filing-href>https://www.sec.gov/Archives/edgar/data/64670/000006467015000002/0000064670-15-000002-index.htm</filing-href>
        <filing-type>8-K</filing-type>
~~~

S15.2  same entry

What it shows: winter filing: updated 2015-02-17T07:18:53-05:00

~~~
<updated>2015-02-17T07:18:53-05:00</updated>
~~~

S15.3  entry for accession 0000064670-13-000009

What it shows: summer filing: updated 2013-08-20T07:33:33-04:00

~~~
<updated>2013-08-20T07:33:33-04:00</updated>
~~~

S15.4  feed-level metadata

What it shows: feed generation timestamp with offset

~~~
<updated>2026-11-13T13:22:34-05:00</updated>
~~~

### What it supports

- Each entry carries updated as an ISO-8601 date-time WITH an explicit UTC offset.
- Across the 40 entries the offset is -05:00 for winter dates and -04:00 for summer dates: the feed serialises a DST-aware US Eastern clock, not a fixed EST clock.
- The feed contains no published element - only updated.
- For the filings cross-checked here, updated equals the raw header ACCEPTANCE-DATETIME digits to the second (see the inference section).

### What it does NOT support

- SEC publishes no documentation of what updated means for EDGAR feeds (see S21).
- It does not say whether updated is acceptance, dissemination, or last-modification time.

## S16 - EDGAR daily index form.idx for 2024-11-01 (SEC-published artifact)

- URL requested: <https://www.sec.gov/Archives/edgar/daily-index/2024/QTR4/form.20241101.idx>
- URL cited: <https://www.sec.gov/Archives/edgar/daily-index/2024/QTR4/form.20241101.idx>
- Retrieved (UTC): 2026-11-13T18:22:36Z | HTTP status: 200 | Content-Type: binary/octet-stream
- Cached bytes: raw/form-idx-sample.bin | sha256: 22f0fd036edb302194b438203e037f1304007929fc105adda1b8eded972d6a40
- Source kind: SEC-published data artifact
- Reliability: primary-doc

### Verbatim quote(s)

S16.1  file header block

What it shows: complete column header; a single Date Filed column, no time of day

~~~
Description:           Daily Index of EDGAR Dissemination Feed by Form Type
Last Data Received:    Nov  1, 2024
Comments:              webmaster@sec.gov
Anonymous FTP:         ftp://ftp.sec.gov/edgar/




Form Type   Company Name                                                  CIK
      Date Filed  File Name
---------------------------------------------------------------------------------------------------------------------------------------------
~~~

S16.2  first data row

What it shows: a real row: 20241101 is the only date, and it is date-only

~~~
1-A POS Armed Forces Brewing Company, Inc. 1832987 20241101 edgar/data/1832987/0001832987-24-000012.txt
~~~

### What it supports

- Columns are Form Type / Company Name / CIK / Date Filed / File Name: Date Filed is YYYYMMDD with no time of day.
- The only timestamp in the file is the file-level Last Data Received date.

### What it does NOT support

- No acceptance time, no dissemination time, no timezone.

## S17 - EDGAR daily index company.idx for 2024-11-01 (SEC-published artifact)

- URL requested: <https://www.sec.gov/Archives/edgar/daily-index/2024/QTR4/company.20241101.idx>
- URL cited: <https://www.sec.gov/Archives/edgar/daily-index/2024/QTR4/company.20241101.idx>
- Retrieved (UTC): 2026-11-13T18:22:37Z | HTTP status: 200 | Content-Type: binary/octet-stream
- Cached bytes: raw/company-idx-sample.bin | sha256: fb112778bdf7dfb8d1765082a4ee31c68f2609d54f034419e1dce9039bcb79ca
- Source kind: SEC-published data artifact
- Reliability: primary-doc

### Verbatim quote(s)

S17.1  file header block

What it shows: company-sorted variant of the daily index header

~~~
Description:           Daily Index of EDGAR Dissemination Feed by Company Name
Last Data Received:    Nov  1, 2024
Comments:              webmaster@sec.gov
Anonymous FTP:         ftp://ftp.sec.gov/edgar/




Company Name                                                  Form Type   CIK
      Date Filed  File Name
-------------------------------------------------------------------------------------------------------------------------------------------------
~~~

### What it supports

- Same field set sorted by company name; still a single date-only Date Filed column.

### What it does NOT support

- No time of day, no timezone.

## S18 - EDGAR daily-index directory listing - SEC

- URL requested: <https://www.sec.gov/Archives/edgar/daily-index/>
- URL cited: <https://www.sec.gov/Archives/edgar/daily-index/>
- Retrieved (UTC): 2026-11-13T18:22:02Z | HTTP status: 200 | Content-Type: text/html
- Cached bytes: raw/daily-index-root.html | sha256: c80c32192ab0ff0e6df9e7edcb62e20c0fb050925c61eb1ac30d6c930d97ff16
- Source kind: directory index
- Reliability: primary-doc

### Verbatim quote(s)

S18.1  table header of the listing

What it shows: only file-level Last Modified metadata is exposed

~~~
Name || Size || Last Modified 1994 || 11/24/2017 09:00:40 AM
~~~

### What it supports

- The daily-index tree is organised by year; the listing exposes only names, sizes and Last Modified times of index files, not per-filing times.

### What it does NOT support

- No per-filing timestamps.

## S19 - EDGAR full-text search backing API response (JSON) for 2024-11-01 8-K filings - SEC

- URL requested: <https://efts.sec.gov/LATEST/search-index?q=%22accepted%22&dateRange=custom&startdt=2024-11-01&enddt=2024-11-01&forms=8-K>
- URL cited: <https://efts.sec.gov/LATEST/search-index?q=%22accepted%22&dateRange=custom&startdt=2024-11-01&enddt=2024-11-01&forms=8-K>
- Retrieved (UTC): 2026-11-13T18:24:16Z | HTTP status: 200 | Content-Type: application/json
- Cached bytes: raw/fts-api.json | sha256: cae67b86e91b5485b0e1dedf9b0b4d1de1e696bfaf58b5e7f589de482fc6eb0a
- Source kind: SEC-published data artifact (undocumented backing endpoint of the public search UI)
- Reliability: primary-doc

### Verbatim quote(s)

S19.1  one hit's _source

What it shows: the only date field in a full-text-search hit is date-only

~~~
"file_date":"2024-11-01"
~~~

### What it supports

- Each hit's _source exposes ciks, period_ending, file_num, display_names, root_forms, file_date, sics, form, adsh, film_num and similar; file_date is date-only (YYYY-MM-DD).
- There is no acceptance or dissemination timestamp in the search payload.

### What it does NOT support

- No time of day and no timezone anywhere in the result payload.

## S20 - EDGAR Full-Text Search UI - SEC

- URL requested: <https://www.sec.gov/edgar/search/>
- URL cited: <https://www.sec.gov/edgar/search/>
- Retrieved (UTC): 2026-11-13T18:24:15Z | HTTP status: 200 | Content-Type: text/html
- Cached bytes: raw/efs-fts-page.html | sha256: f579d267808650fff72d0cde0e4beb1a23a39dbe4a765caac6b6d1117e3b50c9
- Source kind: public search interface
- Reliability: primary-doc

### Verbatim quote(s)

S20.1  results grid column header row

What it shows: user-visible columns include Filed only (page shell; grid is rendered client-side)

~~~
Form & File || Filed || Reporting for || Filing entity/person || CIK || Located || Incorporated || File number || Film number || MA-I Individual
~~~

### What it supports

- The result grid offers a Filed column (date-only) and no time-of-day column.

### What it does NOT support

- No timestamps beyond the filing date are shown to users.

## S21 - RSS Feeds - SEC, Last Reviewed or Updated: June 24, 2026

- URL requested: <https://www.sec.gov/about/rss-feeds>
- URL cited: <https://www.sec.gov/about/rss-feeds>
- Retrieved (UTC): 2026-11-13T18:26:46Z | HTTP status: 200 | Content-Type: text/html; charset=utf-8
- Cached bytes: raw/rss-feeds-doc.html | sha256: ce202d7db97a4c193900c921e1a9b9a3e6236de4e802e45a7ce4dd272311022a
- Source kind: SEC documentation of its RSS/Atom offerings
- Reliability: primary-doc

### Verbatim quote(s)

S21.1  intro

What it shows: framing of SEC feeds

~~~
The following SEC RSS feeds are a helpful online resource for staying current on the most recent materials posted to the SEC website, including EDGAR filings. Most current browsers include an RSS component, allowing the user to subscribe to and aggregate feeds. For more information on using RSS, see RSS Feeds from USA.gov.
~~~

S21.2  section: EDGAR Search RSS Feeds

What it shows: the complete EDGAR-feed documentation SEC offers - no timestamp semantics

~~~
## EDGAR Search RSS Feeds
Some EDGAR search results can be captured as RSS Feeds. The RSS link on various EDGAR searches is located on the left, immediately above the filings result list.
Company Search. Using the Company Search to find the company of interest, you can subscribe to this search to receive the most recent filings from this company. You can further filter your results by Filing Type.
Latest Filings. Using the Latest Filings Search, you can subscribe to all filings, or filter by company, CIK, or Form Type. You can also choose to include, exclude, or select only Ownership filings (Forms 3, 4, 5). For example, here are the most recent Form 10-Ks (Annual Reports).
~~~

S21.3  (footer)

What it shows: page currency

~~~
Last Reviewed or Updated: June 24, 2026
~~~

### What it supports

- SEC documents that EDGAR search results are available as RSS feeds and which searches offer them.
- It says nothing about the meaning, source, or timezone of any feed timestamp element.

### What it does NOT support

- Does not document updated/published semantics.

## S22 - EDGAR Public Dissemination Service (PDS) System - SEC, Last Reviewed or Updated: Aug. 1, 2025

- URL requested: <https://www.sec.gov/search-filings/public-dissemination-service-system-contact>
- URL cited: <https://www.sec.gov/search-filings/public-dissemination-service-system-contact>
- Retrieved (UTC): 2026-11-13T18:24:14Z | HTTP status: 200 | Content-Type: text/html; charset=utf-8
- Cached bytes: raw/pds-page.html | sha256: 76c99d5871ec464598696cc668ec28fe7bfb16310ff9e24dfd6c9ff2e8ef0709
- Source kind: SEC page describing the paid dissemination feed
- Reliability: primary-doc

### Verbatim quote(s)

S22.1  page body

What it shows: PDS purpose and paid-subscription nature

~~~
The EDGAR Public Dissemination Service (PDS) System became operational on November 1, 1998, to provide the public an accurate, complete and fast method of obtaining all accepted and valid EDGAR filings. This privatized PDS System is managed by Maximus Federal Consulting, LLC and is the primary source to receive a dedicated feed of all public EDGAR filings. Subscribers are required to enter into a paid Subscription Agreement with Maximus Federal Consulting, LLC to access this service.
~~~

S22.2  section: PDS subscriber services include

What it shows: as soon as reasonably feasible - explicitly not a fixed timestamp

~~~
Transmission by Internet connection of all public filings acquired and accepted by EDGAR as soon as reasonably feasible following receipt of filing data by the PDS.
~~~

S22.3  section: EDGAR PDS New Subscriber Document

What it shows: SEC.gov availability is engineered to precede PDS availability

~~~
The EDGAR PDS New Subscriber Document (updated 08/01/2025) provides configuration, testing, maintenance, and billing information to potential and existing subscribers of the EDGAR public dissemination service feed. This document was updated to reflect modifications to the EDGAR system to ensure that EDGAR filings are available to the public on the SEC website before such filings are made available to the public dissemination system (PDS).
~~~

S22.4  (footer)

What it shows: page currency

~~~
Last Reviewed or Updated: Aug. 1, 2025
~~~

### What it supports

- PDS exists to give the public an accurate, complete and fast method of obtaining all accepted and valid EDGAR filings; transmission is as soon as reasonably feasible after receipt by PDS.
- SEC states the system was changed specifically to ensure SEC.gov availability precedes PDS availability - so PDS delivery is not even the first public moment.
- This is the closest SEC comes to a public-dissemination definition, and it deliberately avoids promising a per-filing dissemination time.

### What it does NOT support

- No per-filing dissemination timestamp is published or promised.

## S23 - SEC filing detail page for accession 0000064670-15-000002 (Medtronic 8-K, 2015-02-17)

- URL requested: <https://www.sec.gov/Archives/edgar/data/64670/000006467015000002/0000064670-15-000002-index.htm>
- URL cited: <https://www.sec.gov/Archives/edgar/data/64670/000006467015000002/0000064670-15-000002-index.htm>
- Retrieved (UTC): 2026-11-13T18:24:17Z | HTTP status: 200 | Content-Type: text/html
- Cached bytes: raw/filing-index-htm.html | sha256: 4b9bdc4c033a95af9955c172b73159317a9b582346d913843066ca95466c0d2f
- Source kind: SEC-published web page rendered from the same filing metadata
- Reliability: primary-doc

### Verbatim quote(s)

S23.1  Filing Detail header block (HTML tags stripped)

What it shows: Filing Date vs Accepted fields as SEC displays them, with no timezone

~~~
Filing Date 2015-02-17 Accepted 2015-02-17 07:18:53 Documents 3
~~~

### What it supports

- SEC's public filing page displays two distinct fields: Filing Date (date only) and Accepted (date AND time, no timezone label).
- The displayed Accepted value is 2015-02-17 07:18:53, identical to the raw header ACCEPTANCE-DATETIME 20150217071853.

### What it does NOT support

- The page prints no timezone for Accepted.

## S24 - Raw SGML header (.hdr.sgml) for accession 0000064670-15-000002 (Medtronic 8-K)

- URL requested: <https://www.sec.gov/Archives/edgar/data/64670/000006467015000002/0000064670-15-000002.hdr.sgml>
- URL cited: <https://www.sec.gov/Archives/edgar/data/64670/000006467015000002/0000064670-15-000002.hdr.sgml>
- Retrieved (UTC): 2026-11-13T18:25:16Z | HTTP status: 200 | Content-Type: text/sgml
- Cached bytes: raw/hdr-sgml-medtronic-8k.bin | sha256: 2566a99732347ffaa12451319e7bbe105f36ef95945d46a723a7d6d6e5a6b54b
- Source kind: SEC-published data artifact - the exact header block in question 4
- Reliability: primary-doc

### Verbatim quote(s)

S24.1  whole file is 41 lines

What it shows: acceptance datetime, accession, public document count, filing date, date as of change

~~~
<SEC-HEADER>0000064670-15-000002.hdr.sgml : 20150216
<ACCEPTANCE-DATETIME>20150217071853
<ACCESSION-NUMBER>0000064670-15-000002
<TYPE>8-K
<PUBLIC-DOCUMENT-COUNT>3
<PERIOD>20150217
<ITEMS>2.02
<ITEMS>9.01
<FILING-DATE>20150217
<DATE-OF-FILING-DATE-CHANGE>20150217
~~~

### What it supports

- The header contains ACCEPTANCE-DATETIME 20150217071853 with no timezone marker, no offset and no suffix.
- It also contains FILING-DATE 20150217 and PUBLIC-DOCUMENT-COUNT 3, matching the field names in S4 and S10.
- There is no TIMEZONE, UTC-OFFSET or equivalent element anywhere in the header.

### What it does NOT support

- The header itself documents nothing about its own timezone.

## S25 - Complete submission text file (.txt) for accession 0000064670-15-000002 - leading header block

- URL requested: <https://www.sec.gov/Archives/edgar/data/64670/000006467015000002/0000064670-15-000002.txt>
- URL cited: <https://www.sec.gov/Archives/edgar/data/64670/000006467015000002/0000064670-15-000002.txt>
- Retrieved (UTC): 2026-11-13T18:25:17Z | HTTP status: 200 | Content-Type: text/plain
- Cached bytes: raw/fullsub-txt-medtronic-8k.txt | sha256: e01a671bc4abe77aaf84882d68d94e23571a673636571f8886893f6dc8aabb0e
- Source kind: SEC-published data artifact
- Reliability: primary-doc

### Verbatim quote(s)

S25.1  first 11 lines of the file

What it shows: the header block as it appears in the complete submission text file

~~~
<SEC-DOCUMENT>0000064670-15-000002.txt : 20150218
<SEC-HEADER>0000064670-15-000002.hdr.sgml : 20150216
<ACCEPTANCE-DATETIME>20150217071853
ACCESSION NUMBER:		0000064670-15-000002
CONFORMED SUBMISSION TYPE:	8-K
PUBLIC DOCUMENT COUNT:		3
CONFORMED PERIOD OF REPORT:	20150217
ITEM INFORMATION:		Results of Operations and Financial Condition
ITEM INFORMATION:		Financial Statements and Exhibits
FILED AS OF DATE:		20150217
DATE AS OF CHANGE:		20150217
~~~

### What it supports

- The full-submission .txt begins with SEC-DOCUMENT / SEC-HEADER and carries the same ACCEPTANCE-DATETIME 20150217071853 as the .hdr.sgml, followed by the label/value header fields (PUBLIC DOCUMENT COUNT, FILED AS OF DATE, DATE AS OF CHANGE).
- Confirms the ACCEPTANCE-DATETIME element is present in the very file the SEC FAQ points at (S4).

### What it does NOT support

- No timezone marker of any kind.

## S26 - Raw SGML header for accession 0000064670-14-000008 (Medtronic 8-K, accepted 2014-05-20, DST in effect)

- URL requested: <https://www.sec.gov/Archives/edgar/data/64670/000006467014000008/0000064670-14-000008.hdr.sgml>
- URL cited: <https://www.sec.gov/Archives/edgar/data/64670/000006467014000008/0000064670-14-000008.hdr.sgml>
- Retrieved (UTC): 2026-11-13T18:25:41Z | HTTP status: 200 | Content-Type: text/sgml
- Cached bytes: raw/hdr-0000064670-14-000008.bin | sha256: a1b8cff8d0f0818abac4da6353193b599b99e110bc3037f53eadab6d29adb243
- Source kind: SEC-published data artifact (spot check)
- Reliability: primary-doc

### Verbatim quote(s)

S26.1  file head

What it shows: raw acceptance datetime for a DST-period filing

~~~
<SEC-HEADER>0000064670-14-000008.hdr.sgml : 20140520
<ACCEPTANCE-DATETIME>20140520072054
<ACCESSION-NUMBER>0000064670-14-000008
~~~

### What it supports

- A summer (EDT) filing's header gives ACCEPTANCE-DATETIME 20140520072054 with no offset.

### What it does NOT support

- No timezone marker in the header.

## S27 - Raw SGML header for accession 0000064670-13-000009 (Medtronic 8-K, accepted 2013-08-20, DST in effect)

- URL requested: <https://www.sec.gov/Archives/edgar/data/64670/000006467013000009/0000064670-13-000009.hdr.sgml>
- URL cited: <https://www.sec.gov/Archives/edgar/data/64670/000006467013000009/0000064670-13-000009.hdr.sgml>
- Retrieved (UTC): 2026-11-13T18:25:42Z | HTTP status: 200 | Content-Type: text/sgml
- Cached bytes: raw/hdr-0000064670-13-000009.bin | sha256: 0d50746939baf9b4c1c7066ecf751c7af83aecbb52eb3c3ab9ff0065c20a1a43
- Source kind: SEC-published data artifact (spot check)
- Reliability: primary-doc

### Verbatim quote(s)

S27.1  file head

What it shows: second raw acceptance datetime for a DST-period filing

~~~
<SEC-HEADER>0000064670-13-000009.hdr.sgml : 20130820
<ACCEPTANCE-DATETIME>20130820073333
<ACCESSION-NUMBER>0000064670-13-000009
~~~

### What it supports

- Second summer (EDT) header: ACCEPTANCE-DATETIME 20130820073333, no offset.

### What it does NOT support

- No timezone marker in the header.

## S28 - data.sec.gov submissions API payload for CIK 0000064670 (SEC-published artifact)

- URL requested: <https://data.sec.gov/submissions/CIK0000064670.json>
- URL cited: <https://data.sec.gov/submissions/CIK0000064670.json>
- Retrieved (UTC): 2026-11-13T18:26:45Z | HTTP status: 200 | Content-Type: application/json
- Cached bytes: raw/submissions-json-CIK0000064670.json | sha256: a9fde7d6faf5f42061db5335a3970a00abd01983812393c90367830f7510625b
- Source kind: SEC-published data artifact - the exact API the study uses
- Reliability: primary-doc

### Verbatim quote(s)

S28.1  filings.recent.acceptanceDateTime

What it shows: the Z-suffixed serialisation for the same filing whose header reads 20150217071853

~~~
"2015-02-17T12:18:53.000Z"
~~~

### What it supports

- The submissions JSON serialises acceptance as acceptanceDateTime with a literal Z suffix and millisecond precision, e.g. 2015-02-17T12:18:53.000Z.
- For this CIK all 1001 rows in filings.recent use the same ...000Z shape; no row carries a numeric offset such as -05:00.
- The JSON exposes filingDate separately (date-only), mirroring the .txt FILED AS OF DATE field.

### What it does NOT support

- Nothing in the payload or in SEC documentation says what the Z means or how the value was derived (see S1).

