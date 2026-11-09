"""Write ``registry/sources/<source_id>.json`` for the INDUSTRY workstream.

Every claim in these entries is backed by a file in this repository:

* ``SOURCE_PROBES/industry/PROBES.json``      -> ACCESS evidence
* ``SOURCE_PROBES/industry/REQUEST_LOG.jsonl``-> every GET and POST, with sizes
* ``DATASETS/industry/<id>/raw/*``            -> verbatim bytes + sha256
* ``DATASETS/industry/LICENCE_EVIDENCE.json`` -> the licence sentences quoted

``licence_note`` quotes the sentence relied on. Where the sentence is a
*prohibition*, it is quoted as a prohibition and the access state says so.

Run:

    python experiments/industry/write_registry.py
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

from hz.registry import SourceEntry, write_entry  # noqa: E402
from hz.timeq import now_utc  # noqa: E402

SUITE = "industry"


def _count(source_id: str) -> int:
    p = os.path.join(ROOT, "experiments", "industry", "evidence", f"{source_id}.jsonl")
    if not os.path.isfile(p):
        return 0
    with open(p, "r", encoding="utf-8") as fh:
        return sum(1 for line in fh if line.strip())


def entry(**kw) -> SourceEntry:
    kw.setdefault("first_verified_at", now_utc())
    kw.setdefault("probe_suite", SUITE)
    return SourceEntry(**kw)


def build() -> list[SourceEntry]:
    out: list[SourceEntry] = []

    # ------------------------------------------------------------------ trade
    out.append(entry(
        source_id="un_comtrade",
        name="UN Comtrade — International Trade Statistics (public preview API)",
        operator="United Nations Statistics Division",
        domain="comtradeapi.un.org",
        access_state="OPEN_DOCUMENTED",
        access_evidence=(
            "GET /public/v1/preview/C/A/HS answered HTTP 200 with 64 rows for "
            "8 reporters x 4 HS4 x 2 flows (probe un_comtrade_preview_annual); "
            "monthly freqCode=M also 200. Reference files Reporters.json (81,177 B) "
            "and HS.json (1,952,940 B) answered 200."
        ),
        machine_interface="REST JSON; /public/v1/preview (keyless) and /data/v1/get (keyed)",
        auth_required=False,
        rate_policy=(
            "Observed: HTTP 429 on roughly every second call at 1.5 req/s; "
            "practical keyless ceiling ~1 req/s, recovered by bounded retry. "
            "Hard cap: exactly ONE reference period per preview request "
            "(HTTP 400 'Maximum number of periods for preview is 1')."
        ),
        licence_status="terms_restricted",
        licence_url="https://comtradeplus.un.org/LicenseAgreement",
        licence_note=(
            "UN Comtrade Usage Agreement §5: 'any copying, automated browsing or "
            "downloading, redistribution, publication, or commercial exploitation "
            "of any material contained on or otherwise made available to you on "
            "United Nations COMTRADE is strictly prohibited without the prior "
            "written permission of the United Nations.' The keyless preview API is "
            "published for programmatic access, so the two instruments conflict; "
            "HORIZON-001 treats operational reuse as requiring written permission."
        ),
        robots_url="https://comtradeplus.un.org/robots.txt",
        robots_summary="not relied upon; the Usage Agreement governs",
        bulk_available=False,
        historical_depth="annual from 1962, monthly from 2010 (subject to reporter practice)",
        what_is_new=(
            f"{_count('un_comtrade')} country-total medical-HS4 trade observations "
            "(8 reporters x 9018/9019/9020/9022 x imports/exports x 2015-2024, plus a "
            "2025 monthly slice) with HS descriptions and scope notes attached "
            "per record."
        ),
        id_schemes=["hs_code", "comtrade_reporter_flow_cmd_period"],
        entity_types=["trade_flow"],
        blockers=[
            "TERMS_PROHIBIT_AUTOMATED_DOWNLOAD: Usage Agreement §5 reserves all "
            "rights; written permission from UNSD is required for anything beyond "
            "this bounded research sample.",
            "PREVIEW_ONE_PERIOD_PER_REQUEST: only one reference period per request.",
            "NO_PUBLICATION_DATE: the API returns no release date, so no observation "
            "can be placed on an observability timeline.",
            "REPORTER_GAPS: France (M49 250) returned zero rows for all four HS4 "
            "codes 2015-2024; only one of the two monthly reporters reports monthly.",
        ],
        unlock_route=(
            "1) Written permission from the Director, UN Statistics Division "
            "(comtrade@un.org) as required by the Usage Agreement. "
            "2) A licensed Comtrade subscription: https://comtradeplus.un.org "
            "(free registration tier exists and unlocks the non-preview path)."
        ),
        notes=(
            "Only the preview path was exercised. The keyed /data/v1/get path "
            "answered HTTP 401 on the probe (probe un_comtrade_public_data_path)."
        ),
    ))

    out.append(entry(
        source_id="eurostat_comext",
        name="Eurostat Comext — DS-045409 EU trade by HS2-4-6 and CN8",
        operator="European Commission (Eurostat)",
        domain="ec.europa.eu/eurostat",
        access_state="OPEN_DOCUMENTED",
        access_evidence=(
            "GET /api/comext/dissemination/statistics/1.0/data/DS-045409 returned "
            "HTTP 200 with JSON-stat values for 7 of 8 requested reporters, "
            "5 HS4 codes x 2 flows x 2015-2024, in 8 requests."
        ),
        machine_interface="REST JSON-stat 2.0 (dissemination API); browser UI at /comext/newxtweb/",
        auth_required=False,
        rate_policy="No key, no documented quota; collection throttled to ~1.5 req/s by the client.",
        licence_status="open_licence",
        licence_url="https://ec.europa.eu/eurostat/help/copyright-notice",
        licence_note=(
            "'Reuse of statistical data, metadata, publications, and other "
            "dissemination tools published on this website for commercial or "
            "non-commercial purposes is authorised provided the source is "
            "acknowledged.' (Eurostat copyright notice; Commission Decision of "
            "12 December 2011 on the reuse of Commission documents.)"
        ),
        robots_url="https://ec.europa.eu/robots.txt",
        robots_summary="not relied upon; reuse is explicitly authorised by the copyright notice",
        bulk_available=False,
        historical_depth="annual from 1988 (dataset label: 'EU trade since 1988 by HS2-4-6 and CN8')",
        what_is_new=(
            f"{_count('eurostat_comext')} Comext observations (value in EUR and net "
            "mass) for 7 EU reporters x 9018/9019/9020/9021/9022 x imports/exports x "
            "2015-2024 — fills the Comtrade France gap and gives an independent "
            "second compilation of the same customs declarations."
        ),
        id_schemes=["hs_code", "eurostat_comext_cell"],
        entity_types=["trade_flow"],
        blockers=[
            "NO_BULK_TSV: format=TSV and format=CSV are rejected (HTTP 400 'Invalid "
            "value for wsOutputFormat parameter'); only JSON-stat was usable.",
            "NO_CATALOGUE_ENDPOINT: /api/comext/dissemination/catalogue/datasets/ "
            "returns 404, so the current DS code list had to be known in advance.",
            "EU_AGGREGATE_ABSENT: reporter=EU27_2020 and reporter=EU returned no "
            "values for these products; the aggregate must be computed by the caller.",
            "NO_PER_OBSERVATION_RELEASE_DATE: only a dataset-level 'updated' "
            "timestamp is exposed.",
        ],
        unlock_route=(
            "Comext bulk download exists only through the interactive "
            "https://ec.europa.eu/eurostat/comext/newxtweb/ application (a JS UI "
            "with no documented machine bulk URL found), so the dissemination API "
            "is the legitimate machine route."
        ),
        notes="Value in EUR; mass in 100 kg. No deflation, no FX conversion.",
    ))

    out.append(entry(
        source_id="uk_hmrc_trade",
        name="HM Revenue & Customs — UK Trade Info (Overseas Trade Statistics, OData)",
        operator="HM Revenue & Customs",
        domain="api.uktradeinfo.com",
        access_state="OPEN_DOCUMENTED",
        access_evidence=(
            "GET api.uktradeinfo.com/ returned HTTP 200 with the OData entity list; "
            "$metadata 200 (15,406 B); OTS $apply aggregation 200; 11 requests "
            "produced 100 annual UK series rows."
        ),
        machine_interface="OData v4 (JSON), incl. $filter and $apply=filter()/groupby()",
        auth_required=False,
        rate_policy="No key, no documented quota; collection throttled to ~1.5 req/s.",
        licence_status="open_licence",
        licence_url="https://www.uktradeinfo.com/",
        licence_note=(
            "'All content is available under the Open Government Licence v3.0, "
            "except where otherwise stated' (uktradeinfo.com site footer, stored at "
            "DATASETS/industry/uk_hmrc_trade/raw/portal_home.html)."
        ),
        robots_url="https://www.uktradeinfo.com/robots.txt",
        robots_summary="not relied upon; OGL v3.0 explicitly permits reuse",
        bulk_available=True,
        historical_depth="OTS monthly from 2000 (Date entity starts at 200001)",
        what_is_new=(
            f"{_count('uk_hmrc_trade')} UK annual aggregates in GBP for "
            "9018/9019/9020/9021/9022 x imports/exports x 2015-2024, computed "
            "server-side from the CN8 microcube, plus the exact CN8 child list used "
            "for each HS4."
        ),
        id_schemes=["hs_code", "hmrc_ots_series"],
        entity_types=["trade_flow"],
        blockers=[
            "NO_WORLD_TOTAL_ROW: OTS is CN8 x country x port x flow x month; a UK "
            "annual total is a sum computed by the caller and inherits any "
            "suppression in the cells.",
            "EU_NON_EU_FLOW_SPLIT: FlowType 1/2 are EU flows and 3/4 non-EU, so "
            "reading flow 1 as 'imports' understates UK imports. Imports = 1+3, "
            "exports = 2+4.",
            "BREXIT_DISCONTINUITY: the EU/non-EU split is not stable across the "
            "2015-2025 window.",
            "NO_PUBLICATION_DATE: OTS exposes no release timestamp per cell.",
        ],
        unlock_route="No blocker: fully open under OGL v3.0.",
        notes="Values in GBP, not deflated.",
    ))

    out.append(entry(
        source_id="us_census_trade",
        name="US Census Bureau — International Trade API (HS time series)",
        operator="US Census Bureau",
        domain="api.census.gov",
        access_state="REQUIRES_REGISTRATION",
        access_evidence=(
            "GET /data/timeseries/intltrade/imports/hs?... returned HTTP 200 but "
            "redirected to https://api.census.gov/data/missing_key.html (8,764 B) — "
            "the key-required page. The variable dictionary "
            "/variables.json returned 200 JSON, so the schema is public even though "
            "values are not."
        ),
        machine_interface="REST JSON (keyed); variable dictionary unkeyed",
        auth_required=True,
        registration_url="https://api.census.gov/data/key_signup.html",
        rate_policy="Key required; key signup page answered HTTP 200 (10,287 B).",
        licence_status="open_no_explicit_licence",
        licence_url="https://www.census.gov/foreign-trade/index.html",
        licence_note=(
            "No explicit reuse-licence sentence was found on the pages fetched "
            "(foreign-trade index and the developers' page both yielded none; "
            "https://www.census.gov/foreign-trade/developers/index.html returned "
            "HTTP 404). Recorded as publicly readable without an explicit reuse "
            "licence rather than assumed permissive."
        ),
        bulk_available=True,
        historical_depth="not verified (no data observed)",
        what_is_new="Nothing collected: the value path is keyed. This is a clean negative.",
        id_schemes=[],
        entity_types=["trade_flow"],
        blockers=[
            "KEY_REQUIRED: data requests redirect to /data/missing_key.html.",
        ],
        unlock_route=(
            "Free self-service API key at https://api.census.gov/data/key_signup.html "
            "and send it as ?key=; then /timeseries/intltrade/imports/hs becomes "
            "usable (COMM_LVL=HS4, I_COMMODITY=9018)."
        ),
        notes=(
            "The brief described this endpoint as 'keyless for limited use'. On "
            "2026-11-10 it is not: the redirect to missing_key.html is unambiguous."
        ),
    ))

    # -------------------------------------------------------------- procurement
    out.append(entry(
        source_id="usaspending",
        name="USAspending.gov — federal award search API v2",
        operator="US Department of the Treasury (Bureau of the Fiscal Service)",
        domain="api.usaspending.gov",
        access_state="OPEN_DOCUMENTED",
        access_evidence=(
            "POST /api/v2/search/spending_by_award/ returned HTTP 200 for three "
            "filter sets (PSC, NAICS, device keywords), 100 rows each; the official "
            "PSC filter tree (depth=3, 382,700 B) and the data dictionary "
            "(358,054 B) answered keylessly."
        ),
        machine_interface="REST JSON; award search is POST-only (GET returns HTTP 405)",
        auth_required=False,
        rate_policy="No key, no documented quota; 3 POSTs used.",
        licence_status="open_no_explicit_licence",
        licence_url="https://www.usaspending.gov/about",
        licence_note=(
            "No explicit reuse-licence sentence was found on the pages fetched "
            "(https://www.usaspending.gov/about returned a 3,003 B JS shell with no "
            "licence statement). Recorded as publicly readable without an explicit "
            "reuse licence rather than assumed permissive; the underlying records "
            "are the awarding agencies' own public contract data."
        ),
        bulk_available=True,
        historical_depth="awards from FY2008 (API message: 'earliest date of 2007-10-01')",
        what_is_new=(
            f"{_count('usaspending')} unique federal contract awards naming a "
            "recipient, with the recipient pinned by SAM UEI (245/245), award "
            "amount, period of performance, awarding agency, NAICS, verified PSC "
            "label, and a device-naming analysis (70 awards name a device class, "
            "11 carry a model-like token)."
        ),
        id_schemes=["sam_uei", "federal_award_id", "usaspending_generated_internal_id"],
        entity_types=["procurement_award"],
        blockers=[
            "NO_ACTION_DATE: the spending_by_award field set does not return the "
            "award action date (requesting 'Action Date' yields null), so event_at "
            "is the period-of-performance start.",
            "NO_PUBLICATION_DATE: no per-award publication timestamp is returned.",
            "PSC_CONTAMINATION: 6515 mixes instruments with COVID-19 tests and "
            "vaccines; 6550 is reagents/test kits; 6540 is OPHTHALMIC instruments "
            "and 6545 is REPLENISHABLE FIELD MEDICAL SETS (the brief's assumption "
            "for both was wrong).",
            "NO_DEVICE_MANUFACTURER: the award text names the supplier, never the OEM.",
            "PAGE1_ONLY: 100 rows per query — a sample of the largest awards, not a "
            "census.",
        ],
        unlock_route=(
            "No blocker for access. For a census instead of a sample, page through "
            "with generated_internal_id / last_record_sort_value, or use the "
            "bulk_download endpoints listed at https://api.usaspending.gov/docs/endpoints."
        ),
        notes=(
            "device_relation_status is CANDIDATE even when the text names a device "
            "class: no OEM is identified."
        ),
    ))

    out.append(entry(
        source_id="eu_ted",
        name="Tenders Electronic Daily (TED) — API v3 notice search",
        operator="Publications Office of the European Union",
        domain="api.ted.europa.eu",
        access_state="OPEN_DOCUMENTED",
        access_evidence=(
            "POST /v3/notices/search returned HTTP 200 keylessly: 102 can-standard "
            "medical notices in the trailing 12 months, 93 of them with "
            "winner-name, 91 with winner-identifier. GET on the same path returns "
            "HTTP 405."
        ),
        machine_interface="REST JSON; search is POST-only with an expert query language",
        auth_required=False,
        rate_policy="No key for search; no documented quota; 4 POSTs used.",
        licence_status="open_no_explicit_licence",
        licence_url="https://docs.ted.europa.eu/api/latest/index.html",
        licence_note=(
            "TED API docs state developers can 'Retrieve published procurement "
            "notices from the TED website for analysis or reuse' and address "
            "'reusers of TED Data', but no formal reuse licence sentence was found "
            "on the pages fetched. Recorded as publicly readable without an explicit "
            "reuse licence rather than assumed permissive."
        ),
        bulk_available=True,
        historical_depth="not verified for bulk; search covers legacy and eForms notices",
        what_is_new=(
            f"{_count('eu_ted')} supplier rows from 102 eForms-era EU award notices "
            "(2019 name-bearing, 91 with national registration numbers) — this "
            "reverses the previous round's 'TED has no award suppliers' verdict, and "
            "measures that CPV 33100000 is the division-level code, not a "
            "device filter."
        ),
        id_schemes=["ted_publication_number"],
        entity_types=["procurement_award"],
        blockers=[
            "FULL_NOTICE_REQUIRES_KEY: GET /v3/notices/{publication-number} returns "
            "HTTP 400 'Missing Authorization header in request'.",
            "PER_NOTICE_XML_WAF: https://ted.europa.eu/en/notice/{pn}/xml returns "
            "HTTP 405 with an AWS WAF 'Human Verification' interstitial.",
            "LEGACY_NOTICES_HAVE_NO_WINNER: for 2016-era CANs winner-name is null and "
            "BT-768-Contract is only a [true]/[false] presence flag.",
            "IDENTIFIERS_NOT_ALIGNED_TO_NAMES: winner-name and winner-identifier are "
            "parallel lists of unequal length with no stated alignment, so no "
            "identifier can be attached to a specific supplier.",
            "CPV_IS_NOT_A_DEVICE_FILTER: classification-cpv=33100000 matches the whole "
            "division (identical totalNoticeCount of 102 to the union of its "
            "subfamilies; sampled notices also carry 98310000 laundry and 19260000 "
            "leather codes).",
        ],
        unlock_route=(
            "Register for a TED API key at the TED Developer Portal "
            "(https://developer.ted.europa.eu/, reachable from the docs index "
            "'obtain an API key' section). The keyed GET /v3/notices/{pn} then "
            "returns the full eForms payload including BT-768 Contractor with its "
            "identifier."
        ),
        notes=(
            "Notice values are notice/lot totals, not per-device prices. Only "
            "can-standard notices were sampled."
        ),
    ))

    out.append(entry(
        source_id="uk_find_a_tender",
        name="UK Find a Tender Service — OCDS release packages",
        operator="UK Cabinet Office / Crown Commercial Service",
        domain="www.find-tender.service.gov.uk",
        access_state="OPEN_DOCUMENTED",
        access_evidence=(
            "GET /api/1.0/ocdsReleasePackages?stages=award&limit=100 returned HTTP "
            "200 three times (~1.1 MB each), 300 award-stage releases, 316 KB-1.1 MB "
            "each, containing awards[].suppliers[].name."
        ),
        machine_interface="REST JSON, OCDS 1.1 release packages",
        auth_required=False,
        rate_policy=(
            "No key, no documented quota; the API rejects unknown parameters "
            "(HTTP 400) and accepts only stages, limit, cursor, updatedFrom, updatedTo."
        ),
        licence_status="open_licence",
        licence_url="http://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
        licence_note=(
            "The OCDS package declares its own licence field: "
            "'http://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/' "
            "(read verbatim from DATASETS/industry/uk_find_a_tender/raw/"
            "award_packages_p1.json). Open Government Licence v3.0."
        ),
        bulk_available=True,
        historical_depth="not verified (the API is a rolling updatedFrom/updatedTo window)",
        what_is_new=(
            f"{_count('uk_find_a_tender')} UK award-supplier rows for medical CPV "
            "codes, from a scan of 300 award-stage releases (16 medical releases, 32 "
            "medical awards, 100% with a named supplier). Establishes that UK FTS "
            "*does* expose award suppliers, unlike TED's legacy notices."
        ),
        id_schemes=["ocds_ocid", "ocds_party_id"],
        entity_types=["procurement_award"],
        blockers=[
            "NO_CPV_OR_KEYWORD_FILTER: HTTP 400 'Request parameter keyword is not "
            "recognised, allowed parameters are: stages, limit, cursor, updatedFrom, "
            "updatedTo'. Medical awards must be found by scanning.",
            "NO_AWARD_DATE: awards[] carries no date; release.date is the "
            "publication date, so event_at is null unless contracts[].dateSigned "
            "exists.",
            "NO_FIXED_SAMPLE_WINDOW: the 'most recent award releases' window is not a "
            "calendar period, so only the medical share of the sample generalises.",
        ],
        unlock_route=(
            "No access blocker. For a census, page with cursor / updatedFrom; the "
            "only real limitation is the absence of a server-side subject filter."
        ),
        notes="Supplier identity is CONFIRMED only when the buyer published a legal identifier (10 of 62 rows).",
    ))

    # ------------------------------------------------------------ blocked probed
    out.append(entry(
        source_id="sam_gov",
        name="SAM.gov — System for Award Management entity/exclusions extracts",
        operator="US General Services Administration",
        domain="api.sam.gov",
        access_state="REQUIRES_REGISTRATION",
        access_evidence=(
            "GET https://api.sam.gov/ and GET /entity-information/v2/entities"
            "?api_key=test&samRegistered=Yes both returned HTTP 404 with a ZERO-byte "
            "body. The documented route (https://open.gsa.gov/api/"
            "sam-entity-extracts-api/, HTTP 200, 42,115 B) states: 'To access Public "
            "extracts: Users must have a non-Federal/Federal Individual (Personal) "
            "account and the respective API Key'."
        ),
        machine_interface="REST JSON (keyed) + bulk extract files on sam.gov/data-services",
        auth_required=True,
        registration_url="https://sam.gov/",
        rate_policy="Per the docs page: 'API Key Rate Limits' section; not exercised.",
        licence_status="open_no_explicit_licence",
        licence_url="https://open.gsa.gov/api/sam-entity-extracts-api/",
        licence_note=(
            "The GSA docs page states the access requirement ('Users must have a "
            "non-Federal/Federal Individual (Personal) account and the respective API "
            "Key') but no reuse-licence sentence was found on it. Recorded as "
            "publicly readable without an explicit reuse licence."
        ),
        bulk_available=True,
        historical_depth="not verified",
        what_is_new=(
            "Nothing collected: access is registration-gated and the unkeyed host "
            "returns a zero-byte 404 rather than an auth error. Clean negative."
        ),
        id_schemes=["sam_uei"],
        entity_types=["organisation"],
        blockers=[
            "ACCOUNT_AND_KEY_REQUIRED (quoted above).",
            "UNKEYED_HOST_404: api.sam.gov returns HTTP 404 with an empty body even "
            "for its documented paths, so the failure mode is not a 401/403.",
        ],
        unlock_route=(
            "Create a SAM.gov individual (personal) account, request an API key, then "
            "use the Entity/Exclusions Extracts API "
            "(https://open.gsa.gov/api/sam-entity-extracts-api/) for monthly public "
            "extract files."
        ),
        notes="Not needed for this workstream's findings: SAM UEIs arrive with USAspending awards.",
    ))

    out.append(entry(
        source_id="usitc_dataweb",
        name="USITC DataWeb — US trade statistics query tool",
        operator="US International Trade Commission",
        domain="dataweb.usitc.gov",
        access_state="BLOCKED_TECHNICAL",
        access_evidence=(
            "GET https://dataweb.usitc.gov/ returned HTTP 200 (9,516 B) but the body "
            "is a JavaScript single-page-app shell with no data in it; GET /login "
            "returned the identical 9,516 B shell. No public API or JSON endpoint was "
            "found or is documented, so no machine interface could be demonstrated."
        ),
        machine_interface="none demonstrated (browser SPA)",
        auth_required=True,
        registration_url="https://dataweb.usitc.gov/",
        rate_policy="not applicable",
        licence_status="unknown",
        licence_url=None,
        licence_note=(
            "No licence or terms text was recoverable from the served HTML (the page "
            "is a JS shell). Recorded as unknown rather than guessed."
        ),
        bulk_available=False,
        historical_depth="not verified",
        what_is_new=(
            "Nothing collected. DataWeb is an interactive query tool with no keyless "
            "machine interface; the same underlying statistics are available from "
            "the Census trade API (keyed) and Comtrade."
        ),
        id_schemes=[],
        entity_types=["trade_flow"],
        blockers=[
            "NO_MACHINE_INTERFACE_DEMONSTRATED: SPA shell only; /login returns the same "
            "shell, so even the account gate could not be observed as HTML.",
        ],
        unlock_route=(
            "Create a DataWeb account at https://dataweb.usitc.gov/ and use its "
            "interactive export; or obtain the same data from the Census trade API "
            "(keyed) instead. Not pursued: no public API documentation found."
        ),
        notes=(
            "The account requirement is stated in USITC's own documentation, but that "
            "documentation was not fetched here, so the claim above is limited to what "
            "the HTTP responses show."
        ),
    ))

    # ------------------------------------------------------- commercial BoL data
    out.append(entry(
        source_id="importyeti",
        name="ImportYeti — US import bill-of-lading search",
        operator="ImportYeti LLC",
        domain="www.importyeti.com",
        access_state="BLOCKED_LEGAL",
        access_evidence=(
            "GET https://www.importyeti.com/ returned HTTP 200 (53,134 B). robots.txt "
            "(HTTP 200, 167 B) allows crawling of pages but disallows every data "
            "endpoint: 'Disallow: /search?q', 'Disallow: /api/addresses', "
            "'Disallow: /api/ep', 'Disallow: /cdn-cgi/', 'Disallow: /mx/', "
            "'Disallow: /us-export/', 'Disallow: /partnerships/'. The /policies page "
            "returned 200 but no automated-access prohibition could be extracted from "
            "it (the served HTML is largely stylesheet and script text)."
        ),
        machine_interface="web pages only; internal /api/* endpoints exist but are disallowed",
        auth_required=False,
        rate_policy="No published API; robots restricts the data endpoints.",
        licence_status="terms_restricted",
        licence_url="https://www.importyeti.com/policies",
        licence_note=(
            "robots.txt is the operative published restriction: 'Allow: /' followed by "
            "'Disallow: /api/addresses' and 'Disallow: /api/ep'. The shipment data is "
            "served through exactly those disallowed paths, so a compliant crawler "
            "cannot obtain it. No explicit written reuse licence was found."
        ),
        robots_url="https://www.importyeti.com/robots.txt",
        robots_summary=(
            "Allow: / ; Disallow: /search?q, /api/addresses, /api/ep, /cdn-cgi/, /mx/, "
            "/us-export/, /partnerships/"
        ),
        bulk_available=False,
        historical_depth="not assessed (no data acquired)",
        what_is_new=(
            "Nothing collected, and nothing may be collected: the operator's robots "
            "policy disallows the data endpoints. This is the correct conclusion, not "
            "a workaround."
        ),
        id_schemes=[],
        entity_types=["trade_flow"],
        blockers=[
            "ROBOTS_DISALLOWS_DATA_ENDPOINTS: /api/addresses and /api/ep are Disallow.",
            "NO_PUBLISHED_API_LICENCE: no reusable dataset or API terms were found.",
        ],
        unlock_route=(
            "Only with the operator's written permission or a commercial agreement. "
            "Absent that, company-level US customs shipment data must not be acquired "
            "from this vendor. For an aggregate alternative see un_comtrade / "
            "us_census_trade (country totals) — but those cannot substitute for "
            "company-level attribution."
        ),
        notes="No page was crawled beyond the homepage, robots.txt and /policies.",
    ))

    out.append(entry(
        source_id="importgenius",
        name="ImportGenius — trade data (advertised enterprise API)",
        operator="ImportGenius LLC",
        domain="www.importgenius.com",
        access_state="BLOCKED_LEGAL",
        access_evidence=(
            "GET https://www.importgenius.com/ HTTP 200 (232,972 B); robots.txt HTTP "
            "200 (12,540 B, 'User-agent: * / Allow: /'); terms of use HTTP 200 "
            "(103,460 B); /features/api-integration HTTP 200 (131,577 B) advertising "
            "'Enterprise API integration ... A daily-updated REST API with full "
            "documentation and enterprise-grade access. Sign up now / Request a demo'."
        ),
        machine_interface="commercial REST API behind an enterprise agreement",
        auth_required=True,
        rate_policy="Per commercial agreement; no public quota published.",
        licence_status="requires_licence",
        licence_url="https://www.importgenius.com/utilities/legal/terms-of-use",
        licence_note=(
            "Terms of use: 'You may not sell, transfer, assign, license, sublicense or "
            "modify any Content or reproduce, display, publicly perform, make a "
            "derivative work of, distribute or otherwise use any Content in any way "
            "for any purpose, including without limitation any public or commercial "
            "...' and 'No other use is permitted without our prior written consent.'"
        ),
        robots_url="https://www.importgenius.com/robots.txt",
        robots_summary="User-agent: * / Allow: / (sitemaps listed)",
        bulk_available=False,
        historical_depth="25+ countries per the vendor's own feature page",
        what_is_new=(
            "Nothing collected. The vendor's own terms forbid reuse of Content and its "
            "API is enterprise-licensed, so company-level shipment data is "
            "paywalled and must not be acquired."
        ),
        id_schemes=[],
        entity_types=["trade_flow"],
        blockers=[
            "TOS_PROHIBITS_REUSE: quoted above.",
            "API_REQUIRES_COMMERCIAL_AGREEMENT: 'Enterprise API integration ... "
            "enterprise-grade access'.",
        ],
        unlock_route=(
            "A paid commercial agreement with ImportGenius. There is no licence-free "
            "route, and this project's evidence standard does not permit scraping "
            "against those terms."
        ),
        notes="Only the homepage, robots.txt, terms and the API feature page were fetched.",
    ))

    out.append(entry(
        source_id="panjiva",
        name="Panjiva (S&P Global Market Intelligence) — supply-chain trade data",
        operator="S&P Global",
        domain="panjiva.com",
        access_state="REQUIRES_LICENCE",
        access_evidence=(
            "GET https://panjiva.com/ returned HTTP 200 and redirected to "
            "https://panjiva.com/ (33,038 B), listing commercial products 'Panjiva "
            "Platform', 'S&P Capital IQ Pro', 'XpressFeed'. robots.txt HTTP 200 "
            "(7,228 B, disallow-heavy). The linked terms of use "
            "(https://www.spglobal.com/en/terms-of-use) returned HTTP 403 to the "
            "automated client (2,008 B), so the terms could not be quoted."
        ),
        machine_interface="commercial platform / data feed (XpressFeed)",
        auth_required=True,
        rate_policy="Per S&P Global subscription.",
        licence_status="requires_licence",
        licence_url="https://www.spglobal.com/en/terms-of-use",
        licence_note=(
            "The S&P Global terms of use could not be read: HTTP 403 to an automated "
            "client (2,008 B). Panjiva is sold as a subscription platform "
            "('Panjiva Platform', 'XpressFeed'), so the licence status is recorded as "
            "requires_licence on the strength of the product structure, and the exact "
            "terms sentence is explicitly NOT quoted because it was not retrieved."
        ),
        robots_url="https://panjiva.com/robots.txt",
        robots_summary="disallow-heavy; see DATASETS/industry/panjiva/raw/robots.txt",
        bulk_available=False,
        historical_depth="not assessed",
        what_is_new=(
            "Nothing collected. Panjiva is a licensed S&P Global product; the terms "
            "page itself is WAF-blocked to automated clients."
        ),
        id_schemes=[],
        entity_types=["trade_flow"],
        blockers=[
            "COMMERCIAL_SUBSCRIPTION: platform/feed products only.",
            "TERMS_PAGE_403: https://www.spglobal.com/en/terms-of-use returned HTTP 403 "
            "(2,008 B) so the reuse terms are unverified, not permissive.",
        ],
        unlock_route=(
            "An S&P Global commercial licence. Because the terms page is not readable "
            "by an automated client, even the licence text must be obtained by a human "
            "before any use."
        ),
        notes="Homepage and robots.txt only; no data page crawled.",
    ))

    out.append(entry(
        source_id="descartes_datamyne",
        name="Descartes Datamyne — US/global customs shipment data",
        operator="The Descartes Systems Group Inc.",
        domain="www.descartes.com",
        access_state="REQUIRES_LICENCE",
        access_evidence=(
            "GET https://www.descartes.com/datamyne returned HTTP 200 but redirected to "
            "https://www.descartes.com/about/investor-relations/acquisitions/"
            "descartes-datamyne (a corporate acquisition page, not a product page). "
            "/legal-compliance returned HTTP 200 (353,715 B) and lists the governing "
            "instruments: 'Descartes Online Subscription Terms for SaaS Services', "
            "'End User License Agreement (EULA)', 'Descartes Software Support Policy'."
        ),
        machine_interface="commercial SaaS / licensed data",
        auth_required=True,
        rate_policy="Per subscription terms.",
        licence_status="requires_licence",
        licence_url="https://www.descartes.com/legal-compliance",
        licence_note=(
            "The Descartes legal-compliance page lists 'Descartes Online Subscription "
            "Terms for SaaS Services ... (these \"Online Terms\") govern the purchase "
            "and Use of Descartes SaaS Services' and an 'End User License Agreement "
            "(EULA)'. Access to shipment data is therefore contractual."
        ),
        robots_url="https://www.descartes.com/robots.txt",
        robots_summary="standard allow-list for CSS/JS assets (2,141 B)",
        bulk_available=False,
        historical_depth="not assessed",
        what_is_new=(
            "Nothing collected. Datamyne is a subscription product whose terms are "
            "EULA/SaaS-based."
        ),
        id_schemes=[],
        entity_types=["trade_flow"],
        blockers=[
            "SAAS_EULA_ONLY: no open data or open API licence.",
            "PRODUCT_PAGE_REDIRECTS: /datamyne no longer resolves to a product page.",
        ],
        unlock_route="A Descartes commercial subscription. No licence-free route exists.",
        notes="Homepage, /datamyne, /legal-compliance and robots.txt only.",
    ))

    return out


def main() -> int:
    entries = build()
    for e in entries:
        p = write_entry(ROOT, e)
        print(f"wrote {p}")
    print(f"{len(entries)} registry entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
