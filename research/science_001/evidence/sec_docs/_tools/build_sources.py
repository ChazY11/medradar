#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Build SOURCES.md and sources.json for the SEC documentation evidence layer.

Every quote is extracted programmatically from a cached file (never retyped),
so the markdown cannot drift from what SEC actually published.  Extraction is
whitespace-normalised; the raw originals are cached with sha256 in raw/.
"""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RAW = os.path.join(ROOT, "raw")
META = os.path.join(RAW, "_meta.json")

UA = "MedRadar research science-001 (contact: research@medradar.invalid)"
FENCE = "~~~"


def read_lines(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()


def strip_tags(s):
    s = re.sub(r"<[^>]+>", " ", s)
    s = (s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
          .replace("&quot;", '"').replace("&#39;", "'"))
    return s


def norm(s):
    return re.sub(r"[ \t\u00a0]+", " ", s).strip()


def extract(spec):
    path = os.path.join(RAW, spec["file"])
    if "literal" in spec:
        txt = open(path, encoding="utf-8", errors="replace").read()
        lit = spec["literal"]
        assert lit in txt, "LITERAL NOT FOUND in %s: %r" % (spec["file"], lit[:80])
        return lit
    lines = read_lines(path)
    seg = lines[spec["l0"] - 1: spec["l1"]]
    if spec.get("strip"):
        seg = [strip_tags(x) for x in seg]
    join = spec.get("join", "space")
    if join == "newline":
        out = [x.rstrip() for x in seg]
        while out and not out[-1].strip():
            out.pop()
        while out and not out[0].strip():
            out.pop(0)
        res = "\n".join(out)
    elif join == "pipe":
        cells = [norm(x) for x in seg if norm(x)]
        res = " || ".join(cells)
    else:
        res = norm(" ".join(norm(x) for x in seg))
    # optional machine-checked trimming, so a quote can start/end mid-line
    if spec.get("start"):
        i = res.find(spec["start"])
        assert i >= 0, "START NOT FOUND in %r: %r" % (spec["file"], spec["start"][:60])
        res = res[i:]
    if spec.get("end"):
        j = res.find(spec["end"])
        assert j >= 0, "END NOT FOUND in %r: %r" % (spec["file"], spec["end"][:60])
        res = res[:j + len(spec["end"])]
    return res


S = []


def src(**kw):
    kw.setdefault("quotes", [])
    S.append(kw)


src(id="S1",
    url="https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
    title="EDGAR Application Programming Interfaces (APIs) - SEC, Last Reviewed or Updated: April 8, 2025",
    reliability="primary-doc",
    kind="SEC's own documentation page for the data.sec.gov APIs",
    supports=[
        "SEC publishes a documentation page for the data.sec.gov APIs including the submissions API.",
        "SEC describes API freshness in terms of dissemination ('as filings are disseminated'), not acceptance.",
        "The page is silent on every field name, including acceptanceDateTime; it defines no JSON field schema at all.",
        "SEC does label times elsewhere on the same page ('approximately 3:00 a.m. ET'), so the absence of a timezone for submission timestamps is not a lack of vocabulary.",
    ],
    not_supports=[
        "It does NOT define acceptanceDateTime, its format, or its timezone.",
        "It does NOT state that any submission-API timestamp is UTC.",
        "It does NOT describe how any date/time field is serialised.",
    ],
    quotes=[
        dict(file="api-doc-edgar-apis.txt", l0=8, l1=8, page="(page body)",
             shows="API freshness is described relative to dissemination"),
        dict(file="api-doc-edgar-apis.txt", l0=9, l1=9, page="(page body)",
             shows="SEC does use an explicit ET label when it wants one"),
        dict(file="api-doc-edgar-apis.txt", l0=41, l1=41, page="section: Update Schedule",
             shows="submissions API updated in real-time as filings are disseminated"),
        dict(file="api-doc-edgar-apis.txt", l0=47, l1=47, page="(footer)",
             shows="page currency / retrieval sanity check"),
    ])

src(id="S2",
    url="https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
    url_requested="https://www.sec.gov/edgar/sec-api-documentation",
    title="Legacy sec-api-documentation URL (redirects to S1)",
    reliability="primary-doc",
    kind="redirect check requested by the task",
    supports=[
        "The URL named in the task redirects (HTTP 200 after one redirect) to S1; it is not a separate document.",
        "Cached bytes are byte-identical to S1 (identical sha256), so there is no second, richer API document.",
    ],
    not_supports=["No independent content."],
    quotes=[])

src(id="S3",
    url="https://data.sec.gov/",
    title="data.sec.gov root page",
    reliability="primary-doc",
    kind="host root page",
    supports=["data.sec.gov itself points readers to S1 for documentation."],
    not_supports=["It contains no field documentation."],
    quotes=[dict(file="data-sec-root.txt", l0=3, l1=3, page="(page body)",
                 shows="data.sec.gov defers all documentation to S1")])

src(id="S4",
    url="https://www.sec.gov/about/webmaster-frequently-asked-questions",
    url_requested="https://www.sec.gov/os/webmaster-faq",
    title="Webmaster Frequently Asked Questions - SEC, Last Reviewed or Updated: Aug. 23, 2024",
    reliability="secondary-doc",
    kind="SEC staff FAQ (informal support page, not a technical specification)",
    supports=[
        "This FAQ is the ONLY SEC web page located that names the ACCEPTANCE-DATETIME header, defines Acceptance Date / Acceptance Time, and states a timezone for acceptance time: EST.",
        "It defines FILED AS OF DATE and contrasts it with the acceptance timestamps.",
        "It states explicitly that no timestamp exists for when filing content first becomes available on sec.gov.",
        "It quantifies the acceptance-to-availability lag (often within 1-3 minutes) and disclaims any guarantee.",
        "It points readers to the PDS Technical Specification for header tag definitions - a pointer that does not actually hold for ACCEPTANCE-DATETIME (see S10).",
    ],
    not_supports=[
        "It does NOT cover acceptanceDateTime in the data.sec.gov JSON API.",
        "Its EST label is not DST-aware on its face (it says EST, not Eastern time) and it never mentions daylight saving time.",
        "It is an FAQ, not a normative specification, and carries no effective-date semantics beyond Last Reviewed or Updated.",
    ],
    quotes=[
        dict(file="webmaster-faq.txt", l0=163, l1=163, page="section: Developers",
             shows="SEC confirms the submissions API exists on data.sec.gov"),
        dict(file="webmaster-faq.txt", l0=180, l1=180, page="section: Developers (lag-time answer)",
             shows="documented SEC statement about the acceptance-to-availability lag"),
        dict(file="webmaster-faq.txt", l0=194, l1=194, page="section: Developers (header documentation answer)",
             shows="SEC's own pointer to the PDS Technical Specification for header tag definitions"),
        dict(file="webmaster-faq.txt", l0=196, l1=196, page="section: How can I understand EDGAR Timestamps?",
             shows="SEC framing: timestamps are visible in the top header of the complete submission text file"),
        dict(file="webmaster-faq.txt", l0=197, l1=197, page="same section (worked example)",
             shows="the exact header fragment SEC itself quotes, including ACCEPTANCE-DATETIME 20190311165759"),
        dict(file="webmaster-faq.txt", l0=200, l1=200, page="same section (field list)",
             shows="SEC's definition of FILED AS OF DATE"),
        dict(file="webmaster-faq.txt", l0=202, l1=203, join="newline", page="same section (field list)",
             shows="THE decisive documented statement: acceptance date YYYYMMDD, acceptance time EST, HHMMSS"),
        dict(file="webmaster-faq.txt", l0=204, l1=204, page="same section (final sentence)",
             shows="THE decisive negative statement: no timestamp for first public availability on sec.gov"),
        dict(file="webmaster-faq.txt", l0=182, l1=182, page="section: Developers (fastest availability)",
             shows="SEC directs users to Latest Filings RSS / PDS for near-real-time availability"),
        dict(file="webmaster-faq.txt", l0=221, l1=221, page="section: Filers",
             shows="SEC's use of publicly-disseminated as a distinct status word"),
        dict(file="webmaster-faq.txt", l0=224, l1=224, page="(footer)",
             shows="page currency / retrieval sanity check"),
    ])

src(id="S5",
    url="https://www.sec.gov/about/developer-resources",
    title="Developer Resources - SEC, Last Reviewed or Updated: March 10, 2025",
    reliability="primary-doc",
    kind="developer landing page",
    supports=["Confirms the API offering and that EDGAR index files exist in html/xml/json form.",
              "No timestamp semantics anywhere on the page."],
    not_supports=["No field-level or timezone documentation."],
    quotes=[
        dict(file="developer-resources.txt", l0=7, l1=7, page="section: Data APIs Now Available",
             shows="API offering restated; no field documentation"),
        dict(file="developer-resources.txt", l0=32, l1=32, page="(footer)",
             shows="page currency"),
    ])

src(id="S6",
    url="https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data",
    url_requested="https://www.sec.gov/os/accessing-edgar-data",
    title="Accessing EDGAR Data - SEC, Last Reviewed or Updated: June 26, 2024",
    reliability="primary-doc",
    kind="SEC operational documentation for EDGAR data access",
    supports=[
        "Documents EDGAR's daily operating window (6:00 a.m. to 10:00 p.m. ET) and the nightly index build starting about 10:00 p.m. ET.",
        "Documents the 5:30 p.m. ET submission cut-off and that affected filings are disseminated the NEXT business day and appear in the following business day's index.",
        "Documents that the index files carry only a date filed field - no time of day.",
        "Documents that post-acceptance corrections are folded into index builds and that full/quarterly indexes are rebuilt weekly (so indexes are not immutable).",
        "Points to the PDS Technical Specification for SGML header structure.",
    ],
    not_supports=[
        "It gives no timezone for any acceptance timestamp.",
        "It publishes no per-filing public-availability time.",
    ],
    quotes=[
        dict(file="accessing-edgar-data.txt", l0=24, l1=24, page="section: Business hours and dissemination",
             shows="operating window, nightly index build, 5:30 p.m. ET / next-business-day dissemination rule"),
        dict(file="accessing-edgar-data.txt", l0=27, l1=27, page="section: Post-acceptance corrections and deletions",
             shows="PAC handling and index rebuild cadence"),
        dict(file="accessing-edgar-data.txt", l0=38, l1=43, join="newline", page="section: Using the EDGAR index files",
             shows="complete list of index columns - date only, no time of day"),
        dict(file="accessing-edgar-data.txt", l0=60, l1=60, page="section: Feed and oldloads directories",
             shows="SEC's pointer to the PDS Technical Specification for SGML header structure"),
        dict(file="accessing-edgar-data.txt", l0=114, l1=114, page="(footer)",
             shows="page currency"),
    ])

src(id="S7",
    url="https://www.sec.gov/submit-filings/edgar-filer-manual",
    url_requested="https://www.sec.gov/info/edgar/edmanuals.htm",
    title="EDGAR Filer Manual index page (current and draft versions) - SEC",
    reliability="primary-doc",
    kind="version index for the Filer Manual",
    supports=[
        "Establishes which Filer Manual versions are current at retrieval: Volume II Version 78 (deployment 2026-09-14) and Volume I Version 43 (deployment 2026-03-16).",
        "Shows a forthcoming draft Volume II Version 79 for 2026-12-07, i.e. not yet in force when retrieved.",
        "Lists the Volume II chapter structure, which is how the manual splits topics.",
    ],
    not_supports=["It contains no substantive time semantics itself."],
    quotes=[
        dict(file="filer-manual-index-old.txt", l0=17, l1=17, page="section: Volume II: EDGAR Filing",
             shows="current Volume II version and deployment date"),
        dict(file="filer-manual-index-old.txt", l0=7, l1=7, page="section: Volume I: General Information",
             shows="current Volume I version and deployment date"),
        dict(file="filer-manual-index-old.txt", l0=51, l1=51, page="section: Draft/Forthcoming Version",
             shows="draft v79 (not in force at retrieval)"),
    ])

src(id="S8",
    url="https://www.sec.gov/files/edgar/filermanual/edgarfm-vol2-v78.pdf",
    title="EDGAR Filer Manual, Volume II: EDGAR Filing, Version 78, September 14, 2026 (full-volume PDF)",
    reliability="primary-doc",
    kind="the normative filer-facing manual for EDGAR filing",
    supports=[
        "Defines what EDGAR acceptance means operationally: the filing passed EDGAR's processing rules and, if live, will be disseminated.",
        "States that dissemination can often occur within seconds of transmission and that acceptance processing and dissemination take place immediately upon receipt of live filings.",
        "Documents the 6:00 a.m. to 10:00 p.m. Eastern Time operating window.",
        "Documents the 5:30 p.m. Eastern time filing-date rule and the exception list (forms 3/4/5, 144, 13D/13G, MEFs, etc.) whose Filing Date equals the Received Date.",
        "Uses Eastern Time / ET consistently - a DST-aware civil-time label - for every operational deadline it states.",
    ],
    not_supports=[
        "Does NOT contain the string ACCEPTANCE-DATETIME anywhere (0 occurrences in the v78 full volume).",
        "Does NOT contain the phrase acceptance date or acceptance time anywhere (0 occurrences).",
        "Does NOT define the submission header tags; section 7.1.2 only says headers are auto-generated by EDGARLink Online.",
        "Does NOT contain the phrase filed as of date.",
        "Does NOT state the timezone of any machine-readable acceptance timestamp.",
    ],
    quotes=[
        dict(file="filer-manual-vol2-v78.txt", l0=716, l1=720, page="p. 2-4",
             start="EDGAR will either accept or suspend your filing.",
             shows="normative meaning of acceptance vs suspension; accepted live filings are disseminated"),
        dict(file="filer-manual-vol2-v78.txt", l0=721, l1=726, page="p. 2-4",
             shows="dissemination timing in practice, and that SEC.gov posting is part of it"),
        dict(file="filer-manual-vol2-v78.txt", l0=842, l1=847, page="p. 2-6 (section 2.3.1 Hours of Operation)",
             shows="system hours in Eastern Time; nothing after 10:00 p.m. ET is processed that day"),
        dict(file="filer-manual-vol2-v78.txt", l0=4830, l1=4834, page="p. 3-34",
             shows="THE key operational rule: Filing Date vs Received Date, 5:30 p.m. Eastern time cut-off, next-business-day filing date and dissemination"),
        dict(file="filer-manual-vol2-v78.txt", l0=15846, l1=15849, page="p. 7-9 (section 7.1.2 Information on Headers)",
             shows="the manual deliberately does not document header tags; nothing here defines a timestamp field"),
        dict(file="filer-manual-vol2-v78.txt", l0=17769, l1=17771, page="p. 7-38 (section 7.3.3.3)",
             shows="acceptance processing and public dissemination are automated and immediate on receipt of live filings"),
    ])

src(id="S9",
    url="https://www.sec.gov/files/edgar/filer-information/edgarfm-vol1-v43.pdf",
    title="EDGAR Filer Manual, Volume I: General Information, Version 43, Effective March 16, 2026 (full-volume PDF)",
    reliability="primary-doc",
    kind="normative filer-facing manual (general)",
    supports=[
        "SEC's standing statement in the manual that EDGAR accepts submissions 6 a.m. to 10 p.m. Eastern Time, citing Rule 12 of Regulation S-T.",
        "Explicit deferral of filing-date semantics to Rule 13 of Regulation S-T (17 CFR 232.13): the legally operative statement is in the CFR, not the manual.",
    ],
    not_supports=["No timezone statement for acceptance timestamps as data fields.",
                  "No mention of ACCEPTANCE-DATETIME."],
    quotes=[
        dict(file="filer-manual-vol1-v43.txt", l0=181, l1=185, page="p. 2 (section 2 Filing Times)",
             shows="operating hours and explicit pointer to 17 CFR 232.12 and 232.13"),
    ])

src(id="S10",
    url="https://www.sec.gov/files/edgar/pds_dissemination_spec.pdf",
    url_requested="https://www.sec.gov/info/edgar/specifications/pds_dissemination_spec.pdf",
    title="EDGAR Public Dissemination Service (PDS) Technical Specification, Version 2.0, March 2025 (every page watermarked DRAFT)",
    reliability="primary-doc",
    kind="SEC technical specification for the dissemination feed - but a DRAFT",
    supports=[
        "The dissemination feed control block carries Acceptance Date (YYYYMMDD) and Acceptance Time defined as 'Time (EST) at which the submission was accepted by EDGAR. Format is HHMMSS.'",
        "The spec claims to list all SGML tags used within EDGAR submission headers; that list contains FILED AS OF DATE (FILING-DATE) and RECEIVED DATE (RECEIVED-DATE) but NOT ACCEPTANCE-DATETIME.",
        "The only dissemination timestamp in the spec is TIMESTAMP, expressly limited to post-acceptance corrections.",
        "FILED AS OF DATE is defined as the EDGAR assigned official filing date, distinct from any acceptance time.",
    ],
    not_supports=[
        "Does NOT define or mention ACCEPTANCE-DATETIME anywhere (0 occurrences of that token).",
        "Does NOT provide a dissemination timestamp for ordinary filings.",
        "Its EST label is not stated to be DST-aware.",
        "It is marked DRAFT on every page, so it is not a settled normative document.",
    ],
    quotes=[
        dict(file="pds-spec-current.txt", l0=456, l1=463, join="pipe", page="p. 9 (section 2.1 Control Block)",
             shows="control-block Receipt Date vs Acceptance Date definitions"),
        dict(file="pds-spec-current.txt", l0=470, l1=473, join="pipe", page="p. 10 (section 2.1 Control Block)",
             shows="THE documented Time (EST) acceptance-time definition"),
        dict(file="pds-spec-current.txt", l0=699, l1=703, page="p. 14 (section 3.2)",
             shows="claim of completeness for the SGML tag inventory that follows"),
        dict(file="pds-spec-current.txt", l0=2806, l1=2811, page="p. 41 (section 4.3 tag definitions)",
             shows="TIMESTAMP is a DISSEMINATION date-time but ONLY for post-acceptance corrections"),
        dict(file="pds-spec-current.txt", l0=3145, l1=3148, join="space", page="p. 45",
             shows="FILED AS OF DATE maps to FILING-DATE (no acceptance tag in this inventory)"),
        dict(file="pds-spec-current.txt", l0=3156, l1=3158, page="p. 46",
             shows="definition of the official filing date"),
    ])

src(id="S11",
    url="https://www.sec.gov/info/edgar/pdsdissemspec910.pdf",
    title="EDGAR Public Dissemination Service Technical Specification (earlier version; 57 pages; no cover date, filename suggests 2010-09)",
    reliability="primary-doc",
    kind="superseded technical specification, still served by sec.gov",
    supports=[
        "Same Time (EST) acceptance-time definition in the control block, showing the phrasing has been stable across spec revisions.",
        "States there are four (4) types of public disseminations and that the acceptance and dissemination process usually takes no longer than two minutes - SEC treats dissemination as near-simultaneous with acceptance rather than a separately stamped event.",
        "TIMESTAMP again defined as dissemination date-time for post-acceptance corrections only.",
    ],
    not_supports=["No ACCEPTANCE-DATETIME tag definition.", "No per-filing dissemination timestamp."],
    quotes=[
        dict(file="pds-spec-910.txt", l0=266, l1=273, join="pipe", page="p. 8 (section 2.1 Control Block)",
             shows="control-block Acceptance Date / Acceptance Time (EST)"),
        dict(file="pds-spec-910.txt", l0=82, l1=83, page="p. 4 (section 1.0)",
             start="The acceptance and dissemination process",
             shows="acceptance and dissemination process usually takes no longer than two minutes"),
        dict(file="pds-spec-910.txt", l0=1474, l1=1480, page="p. 24 (section 3.3 tag definitions)",
             shows="TIMESTAMP = Edgar Dissemination date-time, used for Post Acceptance Corrections only"),
        dict(file="pds-spec-910.txt", l0=460, l1=461, join="space", page="p. 12 (section 3.2 tag identification)",
             shows="FILED AS OF DATE is FILING-DATE; no acceptance tag is listed"),
        dict(file="pds-spec-910.txt", l0=1713, l1=1717, page="p. 27 (section 3.3)",
             shows="FILED AS OF DATE definition"),
    ])

src(id="S12",
    url="https://www.sec.gov/info/edgar/specifications/pds-dissemination-spec022315.pdf",
    title="EDGAR Public Dissemination Service (PDS) Technical Specification, Updated February 23, 2015",
    reliability="primary-doc",
    kind="dated intermediate revision of the PDS spec",
    supports=["The same (EST) acceptance-time definition persisted through the 2015 revision - three independent spec revisions all say EST and none says DST."],
    not_supports=["No ACCEPTANCE-DATETIME tag; no dissemination timestamp for ordinary filings."],
    quotes=[
        dict(file="pds-spec-022315.txt", l0=415, l1=421, join="pipe", page="p. 9 (section 2.1 Control Block)",
             shows="2015 revision: Acceptance Date / Acceptance Time (EST)"),
    ])

src(id="S13",
    url="https://www.govinfo.gov/content/pkg/CFR-2025-title17-vol3/xml/CFR-2025-title17-vol3-sec232-13.xml",
    title="17 CFR 232.13 - Date of filing; adjustment of filing date (Regulation S-T Rule 13); GPO/govinfo CFR compilation dated 2025-04-01",
    reliability="primary-doc",
    kind="federal regulation (legally operative text)",
    supports=[
        "The legally operative rule is the business day on which a filing is received by the Commission (receipt-based), subject to conditions.",
        "The 5:30 p.m. cut-off is defined in terms of Eastern Standard Time or Eastern Daylight Saving Time, whichever is currently in effect - the regulation is explicitly DST-aware.",
        "Special later cut-offs (10 p.m.) exist for Rule 462(b) registrations and for forms 3/4/5, 144, 13D/13G, 14N.",
        "The rule time-stamps the moment a direct transmission commences, not the moment EDGAR finishes accepting.",
    ],
    not_supports=[
        "It does not mention EDGAR's ACCEPTANCE-DATETIME field or any data format.",
        "It does not define a public-dissemination timestamp.",
    ],
    quotes=[
        dict(file="govinfo-232-13.txt", l0=25, l1=25, strip=True, page="section 232.13(a)(1)",
             shows="filing date = business day of receipt, subject to conditions"),
        dict(file="govinfo-232-13.txt", l0=36, l1=36, strip=True, page="section 232.13(a)(2)",
             shows="THE decisive legal statement: 5:30 p.m. Eastern Standard/Daylight time, DST-aware, next business day otherwise"),
        dict(file="govinfo-232-13.txt", l0=38, l1=38, strip=True, page="section 232.13(a)(4)",
             shows="10 p.m. cut-off for forms 3/4/5, 144, 13D/13G, 14N"),
    ])

src(id="S14",
    url="https://www.govinfo.gov/content/pkg/CFR-2025-title17-vol3/xml/CFR-2025-title17-vol3-sec232-12.xml",
    title="17 CFR 232.12 - Business hours of the Commission (Regulation S-T Rule 12); GPO/govinfo CFR compilation dated 2025-04-01",
    reliability="primary-doc",
    kind="federal regulation",
    supports=["Direct transmission is permitted 6 a.m. to 10 p.m. Eastern Standard Time or Eastern Daylight Saving Time, whichever is currently in effect."],
    not_supports=["No data-field or dissemination-timestamp content."],
    quotes=[
        dict(file="govinfo-232-12.txt", l0=37, l1=38, strip=True, page="section 232.12(c)",
             shows="EDGAR direct-transmission hours, DST-aware"),
    ])

src(id="S15",
    url="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000064670&type=8-K&output=atom",
    title="EDGAR company filing Atom feed (CIK 0000064670, form 8-K) - SEC",
    reliability="primary-doc",
    kind="SEC-published data artifact (no accompanying documentation)",
    supports=[
        "Each entry carries updated as an ISO-8601 date-time WITH an explicit UTC offset.",
        "Across the 40 entries the offset is -05:00 for winter dates and -04:00 for summer dates: the feed serialises a DST-aware US Eastern clock, not a fixed EST clock.",
        "The feed contains no published element - only updated.",
        "For the filings cross-checked here, updated equals the raw header ACCEPTANCE-DATETIME digits to the second (see the inference section).",
    ],
    not_supports=[
        "SEC publishes no documentation of what updated means for EDGAR feeds (see S21).",
        "It does not say whether updated is acceptance, dissemination, or last-modification time.",
    ],
    quotes=[
        dict(file="atom-cik-0000064670-8K.txt", l0=38, l1=44, join="newline", page="entry for accession 0000064670-15-000002",
             shows="entry metadata including filing-date 2015-02-17"),
        dict(file="atom-cik-0000064670-8K.txt", l0=54, l1=54, page="same entry",
             shows="winter filing: updated 2015-02-17T07:18:53-05:00"),
        dict(file="atom-cik-0000064670-8K.txt", l0=747, l1=747, page="entry for accession 0000064670-13-000009",
             shows="summer filing: updated 2013-08-20T07:33:33-04:00"),
        dict(file="atom-cik-0000064670-8K.txt", l0=880, l1=880, page="feed-level metadata",
             shows="feed generation timestamp with offset"),
    ])

src(id="S16",
    url="https://www.sec.gov/Archives/edgar/daily-index/2024/QTR4/form.20241101.idx",
    title="EDGAR daily index form.idx for 2024-11-01 (SEC-published artifact)",
    reliability="primary-doc",
    kind="SEC-published data artifact",
    supports=["Columns are Form Type / Company Name / CIK / Date Filed / File Name: Date Filed is YYYYMMDD with no time of day.",
              "The only timestamp in the file is the file-level Last Data Received date."],
    not_supports=["No acceptance time, no dissemination time, no timezone."],
    quotes=[
        dict(file="form-idx-sample.txt", l0=1, l1=11, join="newline", page="file header block",
             shows="complete column header; a single Date Filed column, no time of day"),
        dict(file="form-idx-sample.txt", l0=12, l1=12, page="first data row",
             shows="a real row: 20241101 is the only date, and it is date-only"),
    ])

src(id="S17",
    url="https://www.sec.gov/Archives/edgar/daily-index/2024/QTR4/company.20241101.idx",
    title="EDGAR daily index company.idx for 2024-11-01 (SEC-published artifact)",
    reliability="primary-doc",
    kind="SEC-published data artifact",
    supports=["Same field set sorted by company name; still a single date-only Date Filed column."],
    not_supports=["No time of day, no timezone."],
    quotes=[
        dict(file="company-idx-sample.txt", l0=1, l1=11, join="newline", page="file header block",
             shows="company-sorted variant of the daily index header"),
    ])

src(id="S18",
    url="https://www.sec.gov/Archives/edgar/daily-index/",
    title="EDGAR daily-index directory listing - SEC",
    reliability="primary-doc",
    kind="directory index",
    supports=["The daily-index tree is organised by year; the listing exposes only names, sizes and Last Modified times of index files, not per-filing times."],
    not_supports=["No per-filing timestamps."],
    quotes=[
        dict(file="daily-index-root.txt", l0=45, l1=46, page="table header of the listing",
             shows="only file-level Last Modified metadata is exposed"),
    ])

src(id="S19",
    url="https://efts.sec.gov/LATEST/search-index?q=%22accepted%22&dateRange=custom&startdt=2024-11-01&enddt=2024-11-01&forms=8-K",
    title="EDGAR full-text search backing API response (JSON) for 2024-11-01 8-K filings - SEC",
    reliability="primary-doc",
    kind="SEC-published data artifact (undocumented backing endpoint of the public search UI)",
    supports=["Each hit's _source exposes ciks, period_ending, file_num, display_names, root_forms, file_date, sics, form, adsh, film_num and similar; file_date is date-only (YYYY-MM-DD).",
              "There is no acceptance or dissemination timestamp in the search payload."],
    not_supports=["No time of day and no timezone anywhere in the result payload."],
    quotes=[
        dict(file="fts-api.json", literal='"file_date":"2024-11-01"', page="one hit's _source",
             shows="the only date field in a full-text-search hit is date-only"),
    ])

src(id="S20",
    url="https://www.sec.gov/edgar/search/",
    title="EDGAR Full-Text Search UI - SEC",
    reliability="primary-doc",
    kind="public search interface",
    supports=["The result grid offers a Filed column (date-only) and no time-of-day column."],
    not_supports=["No timestamps beyond the filing date are shown to users."],
    quotes=[
        dict(file="efs-fts-page.txt", l0=8, l1=8, page="results grid column header row",
             shows="user-visible columns include Filed only (page shell; grid is rendered client-side)"),
    ])

src(id="S21",
    url="https://www.sec.gov/about/rss-feeds",
    title="RSS Feeds - SEC, Last Reviewed or Updated: June 24, 2026",
    reliability="primary-doc",
    kind="SEC documentation of its RSS/Atom offerings",
    supports=["SEC documents that EDGAR search results are available as RSS feeds and which searches offer them.",
              "It says nothing about the meaning, source, or timezone of any feed timestamp element."],
    not_supports=["Does not document updated/published semantics."],
    quotes=[
        dict(file="rss-feeds-doc.txt", l0=5, l1=5, page="intro",
             shows="framing of SEC feeds"),
        dict(file="rss-feeds-doc.txt", l0=14, l1=17, join="newline", page="section: EDGAR Search RSS Feeds",
             shows="the complete EDGAR-feed documentation SEC offers - no timestamp semantics"),
        dict(file="rss-feeds-doc.txt", l0=22, l1=22, page="(footer)",
             shows="page currency"),
    ])

src(id="S22",
    url="https://www.sec.gov/search-filings/public-dissemination-service-system-contact",
    title="EDGAR Public Dissemination Service (PDS) System - SEC, Last Reviewed or Updated: Aug. 1, 2025",
    reliability="primary-doc",
    kind="SEC page describing the paid dissemination feed",
    supports=[
        "PDS exists to give the public an accurate, complete and fast method of obtaining all accepted and valid EDGAR filings; transmission is as soon as reasonably feasible after receipt by PDS.",
        "SEC states the system was changed specifically to ensure SEC.gov availability precedes PDS availability - so PDS delivery is not even the first public moment.",
        "This is the closest SEC comes to a public-dissemination definition, and it deliberately avoids promising a per-filing dissemination time.",
    ],
    not_supports=["No per-filing dissemination timestamp is published or promised."],
    quotes=[
        dict(file="pds-page.txt", l0=5, l1=5, page="page body",
             shows="PDS purpose and paid-subscription nature"),
        dict(file="pds-page.txt", l0=8, l1=8, page="section: PDS subscriber services include",
             shows="as soon as reasonably feasible - explicitly not a fixed timestamp"),
        dict(file="pds-page.txt", l0=23, l1=23, page="section: EDGAR PDS New Subscriber Document",
             shows="SEC.gov availability is engineered to precede PDS availability"),
        dict(file="pds-page.txt", l0=28, l1=28, page="(footer)",
             shows="page currency"),
    ])

src(id="S23",
    url="https://www.sec.gov/Archives/edgar/data/64670/000006467015000002/0000064670-15-000002-index.htm",
    title="SEC filing detail page for accession 0000064670-15-000002 (Medtronic 8-K, 2015-02-17)",
    reliability="primary-doc",
    kind="SEC-published web page rendered from the same filing metadata",
    supports=["SEC's public filing page displays two distinct fields: Filing Date (date only) and Accepted (date AND time, no timezone label).",
              "The displayed Accepted value is 2015-02-17 07:18:53, identical to the raw header ACCEPTANCE-DATETIME 20150217071853."],
    not_supports=["The page prints no timezone for Accepted."],
    quotes=[
        dict(file="filing-index-htm.html", l0=77, l1=84, strip=True, page="Filing Detail header block (HTML tags stripped)",
             shows="Filing Date vs Accepted fields as SEC displays them, with no timezone"),
    ])

src(id="S24",
    url="https://www.sec.gov/Archives/edgar/data/64670/000006467015000002/0000064670-15-000002.hdr.sgml",
    title="Raw SGML header (.hdr.sgml) for accession 0000064670-15-000002 (Medtronic 8-K)",
    reliability="primary-doc",
    kind="SEC-published data artifact - the exact header block in question 4",
    supports=["The header contains ACCEPTANCE-DATETIME 20150217071853 with no timezone marker, no offset and no suffix.",
              "It also contains FILING-DATE 20150217 and PUBLIC-DOCUMENT-COUNT 3, matching the field names in S4 and S10.",
              "There is no TIMEZONE, UTC-OFFSET or equivalent element anywhere in the header."],
    not_supports=["The header itself documents nothing about its own timezone."],
    quotes=[
        dict(file="hdr-sgml-medtronic-8k.txt", l0=1, l1=10, join="newline", page="whole file is 41 lines",
             shows="acceptance datetime, accession, public document count, filing date, date as of change"),
    ])

src(id="S25",
    url="https://www.sec.gov/Archives/edgar/data/64670/000006467015000002/0000064670-15-000002.txt",
    title="Complete submission text file (.txt) for accession 0000064670-15-000002 - leading header block",
    reliability="primary-doc",
    kind="SEC-published data artifact",
    supports=["The full-submission .txt begins with SEC-DOCUMENT / SEC-HEADER and carries the same ACCEPTANCE-DATETIME 20150217071853 as the .hdr.sgml, followed by the label/value header fields (PUBLIC DOCUMENT COUNT, FILED AS OF DATE, DATE AS OF CHANGE).",
              "Confirms the ACCEPTANCE-DATETIME element is present in the very file the SEC FAQ points at (S4)."],
    not_supports=["No timezone marker of any kind."],
    quotes=[
        dict(file="fullsub-txt-medtronic-8k.txt", l0=1, l1=11, join="newline", page="first 11 lines of the file",
             shows="the header block as it appears in the complete submission text file"),
    ])

src(id="S26",
    url="https://www.sec.gov/Archives/edgar/data/64670/000006467014000008/0000064670-14-000008.hdr.sgml",
    title="Raw SGML header for accession 0000064670-14-000008 (Medtronic 8-K, accepted 2014-05-20, DST in effect)",
    reliability="primary-doc",
    kind="SEC-published data artifact (spot check)",
    supports=["A summer (EDT) filing's header gives ACCEPTANCE-DATETIME 20140520072054 with no offset."],
    not_supports=["No timezone marker in the header."],
    quotes=[
        dict(file="hdr-0000064670-14-000008.txt", l0=1, l1=3, join="newline", page="file head",
             shows="raw acceptance datetime for a DST-period filing"),
    ])

src(id="S27",
    url="https://www.sec.gov/Archives/edgar/data/64670/000006467013000009/0000064670-13-000009.hdr.sgml",
    title="Raw SGML header for accession 0000064670-13-000009 (Medtronic 8-K, accepted 2013-08-20, DST in effect)",
    reliability="primary-doc",
    kind="SEC-published data artifact (spot check)",
    supports=["Second summer (EDT) header: ACCEPTANCE-DATETIME 20130820073333, no offset."],
    not_supports=["No timezone marker in the header."],
    quotes=[
        dict(file="hdr-0000064670-13-000009.txt", l0=1, l1=3, join="newline", page="file head",
             shows="second raw acceptance datetime for a DST-period filing"),
    ])

src(id="S28",
    url="https://data.sec.gov/submissions/CIK0000064670.json",
    title="data.sec.gov submissions API payload for CIK 0000064670 (SEC-published artifact)",
    reliability="primary-doc",
    kind="SEC-published data artifact - the exact API the study uses",
    supports=["The submissions JSON serialises acceptance as acceptanceDateTime with a literal Z suffix and millisecond precision, e.g. 2015-02-17T12:18:53.000Z.",
              "For this CIK all 1001 rows in filings.recent use the same ...000Z shape; no row carries a numeric offset such as -05:00.",
              "The JSON exposes filingDate separately (date-only), mirroring the .txt FILED AS OF DATE field."],
    not_supports=["Nothing in the payload or in SEC documentation says what the Z means or how the value was derived (see S1)."],
    quotes=[
        dict(file="submissions-json-CIK0000064670.json", literal='"2015-02-17T12:18:53.000Z"',
             page="filings.recent.acceptanceDateTime",
             shows="the Z-suffixed serialisation for the same filing whose header reads 20150217071853"),
    ])

src(id="S29",
    url="https://www.sec.gov/Archives/edgar/data/64670/000006467014000008/0000064670-14-000008-index.htm",
    title="SEC filing detail page for accession 0000064670-14-000008 (Medtronic 8-K, 2014-05-20)",
    reliability="primary-doc",
    kind="SEC-published web page (spot check)",
    supports=["SEC's own page displays Accepted 2014-05-20 07:20:54 - identical to the raw header digits, and again with no timezone label - for a filing made while US daylight saving time was in effect."],
    not_supports=["No timezone label."],
    quotes=[
        dict(file="filing-index-14-000008.html", l0=78, l1=83, strip=True, page="Filing Detail header block (HTML tags stripped)",
             shows="Filing Date / Accepted for a DST-period filing"),
    ])

src(id="S30",
    url="https://www.sec.gov/Archives/edgar/data/64670/000006467013000009/0000064670-13-000009-index.htm",
    title="SEC filing detail page for accession 0000064670-13-000009 (Medtronic 8-K, 2013-08-20)",
    reliability="primary-doc",
    kind="SEC-published web page (spot check)",
    supports=["Second DST-period confirmation: Accepted 2013-08-20 07:33:33 with no timezone label."],
    not_supports=["No timezone label."],
    quotes=[
        dict(file="filing-index-13-000009.html", l0=78, l1=83, strip=True, page="Filing Detail header block (HTML tags stripped)",
             shows="Filing Date / Accepted for a second DST-period filing"),
    ])

# ---------------------------------------------------------------- build output
meta = json.load(open(META, encoding="utf-8"))
problems = []
for s in S:
    req = s.get("url_requested") or s["url"]
    rec = None
    for r in meta["records"]:
        if r["requested_url"] == req:
            rec = r
            break
    if rec is None:
        problems.append("no fetch record for %s" % req)
        rec = {"status": None, "final_url": s["url"], "retrieved_at": None,
               "sha256": None, "file": None, "content_type": None}
    s["fetch"] = rec
    for q in s["quotes"]:
        try:
            q["text"] = extract(q)
        except Exception as e:
            problems.append("%s %s: %s" % (s["id"], q.get("file"), e))
            q["text"] = "EXTRACTION FAILED"

if problems:
    print("PROBLEMS:")
    for p in problems:
        print(" -", p)

out = []
for s in S:
    out.append(dict(
        id=s["id"], url=s["url"], url_requested=s.get("url_requested"),
        final_url=s["fetch"].get("final_url"), http_status=s["fetch"].get("status"),
        retrieved_at_utc=s["fetch"].get("retrieved_at"),
        title=s["title"], reliability=s["reliability"], source_kind=s["kind"],
        cached_file=s["fetch"].get("file"), content_type=s["fetch"].get("content_type"),
        sha256_of_cached_bytes=s["fetch"].get("sha256"),
        supports=s["supports"], does_not_support=s["not_supports"],
        quotes=[dict(text=q["text"], locator=q.get("page"), supports=q.get("shows")) for q in s["quotes"]],
    ))
with open(os.path.join(ROOT, "sources.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)

L = []
A = L.append
A("# SEC documentation evidence layer - MedRadar SCIENCE-001")
A("")
A("Purpose: record, with URLs and verbatim quotes, what SEC's own documentation says about filing")
A("timestamps - specifically acceptanceDateTime in the data.sec.gov submissions API and")
A("ACCEPTANCE-DATETIME in the raw filing header - and whether any SEC-published timestamp")
A("represents public dissemination as distinct from acceptance.")
A("")
A("## Method and integrity notes")
A("")
A("- Everything below was fetched from sec.gov / data.sec.gov / govinfo.gov on the timestamps")
A("- shown, with User-Agent: " + UA + ",")
A("- at a self-imposed rate of at most 3 requests/second (SEC's published ceiling is 10/s).")
A("- Every page/PDF actually read is cached byte-for-byte under raw/; each source lists the")
A("- cached filename and the sha256 of the cached bytes so any quote can be re-verified.")
A("- raw/_meta.json holds the full fetch log (status codes, redirect chains, content types).")
A("- Quotes were extracted PROGRAMMATICALLY from the cached files by _tools/build_sources.py,")
A("- not retyped by hand. Extraction normalises runs of whitespace/newlines and, for HTML,")
A("- strips tags; nothing else is altered. Where the source is a PDF, the extraction is the PDF")
A("- text layer and PDF page numbers are given so the quote can be located in the original.")
A("- raw/ also holds .txt companions (HTML-stripped / PDF-text-extracted) for grep-ability. Those")
A("- are DERIVED files; every sha256 refers to the original fetched bytes.")
A("- All fetched page text was treated strictly as data. No instruction found in any fetched")
A("- document was followed.")
A("")
A("Legend for reliability: primary-doc = published by SEC or by GPO/govinfo (the issuing")
A("authority); secondary-doc = an SEC page that discusses the topic informally without defining")
A("it; inference = a conclusion drawn by this work from SEC-published data rather than stated")
A("by any document (see the inference section at the end).")
A("")
A("## Source index")
A("")
A("| # | Source | reliability | HTTP | retrieved (UTC) | sha256 (16) |")
A("|---|---|---|---|---|---|")
for s in S:
    fa = s["fetch"]
    sha = (fa.get("sha256") or "")[:16]
    A("| %s | %s | %s | %s | %s | %s |" % (
        s["id"], s["title"].replace("|", "/"), s["reliability"], fa.get("status"),
        fa.get("retrieved_at"), sha))
A("")
for s in S:
    fa = s["fetch"]
    A("## %s - %s" % (s["id"], s["title"]))
    A("")
    A("- URL requested: <" + (s.get("url_requested") or s["url"]) + ">")
    A("- URL cited: <" + s["url"] + ">")
    if fa.get("final_url") and fa.get("final_url") != s["url"]:
        A("- Final URL served after redirects: <" + fa["final_url"] + ">")
    A("- Retrieved (UTC): %s | HTTP status: %s | Content-Type: %s" % (
        fa.get("retrieved_at"), fa.get("status"), fa.get("content_type")))
    A("- Cached bytes: raw/%s | sha256: %s" % (fa.get("file"), fa.get("sha256")))
    A("- Source kind: %s" % s["kind"])
    A("- Reliability: " + s["reliability"])
    A("")
    if s["quotes"]:
        A("### Verbatim quote(s)")
        A("")
        for i, q in enumerate(s["quotes"], 1):
            A("%s.%d  %s" % (s["id"], i, q.get("page") or ""))
            A("")
            A("What it shows: " + (q.get("shows") or ""))
            A("")
            A(FENCE)
            A(q["text"].replace(FENCE, ""))
            A(FENCE)
            A("")
    else:
        A("_No independent quotable text: this URL served content byte-identical to the cited S1")
        A("document (identical sha256) - it is a redirect, not a separate document._")
        A("")
    A("### What it supports")
    A("")
    for x in s["supports"]:
        A("- " + x)
    A("")
    A("### What it does NOT support")
    A("")
    for x in s["not_supports"]:
        A("- " + x)
    A("")

with open(os.path.join(ROOT, "SOURCES.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(L) + "\n")

print("wrote SOURCES.md and sources.json")
print("sources:", len(S), "quotes:", sum(len(s["quotes"]) for s in S))
for s in S:
    for q in s["quotes"]:
        print("%-4s %-32s %-38s %4d ch | %s" % (
            s["id"], q.get("file", "")[:32], (q.get("page") or "")[:38], len(q["text"]),
            q["text"][:64].replace("\n", " / ")))
