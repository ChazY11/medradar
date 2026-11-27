"""INDUSTRY / TRADE / PROCUREMENT probe suite.

Every endpoint the INDUSTRY workstream relies on appears here exactly once, so
that ``SOURCE_PROBES/industry/PROBES.json`` is the machine-checkable evidence
behind ``reports/INDUSTRY_DATA_REPORT.md``.

Deliberate design notes
-----------------------
* A probe proves ACCESS only. It never proves DATA, IDENTITY or RESEARCH.
* Endpoints that need a POST (USAspending ``spending_by_award``, TED
  ``/v3/notices/search``) cannot be expressed as a :class:`Probe`; their calls
  are issued by the connectors and appended to the same
  ``REQUEST_LOG.jsonl`` with ``"method": "POST"`` and a body digest.
* Endpoints that are *expected* to fail are still probed. A 404/403 with a
  recorded body signature is the evidence for a BLOCKED_* verdict; guessing the
  verdict would not be.
"""

from __future__ import annotations

from .probe import Probe

# Reporters used for the trade time series. Chosen for size + diversity of
# reporting practice, not because they are "the important ones".
#   156 China, 842 USA, 276 Germany, 250 France, 392 Japan, 826 UK,
#   380 Italy, 724 Spain
COMTRADE_ANNUAL_URL = (
    "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
    "?reporterCode=156,842,276,250,392,826,380,724"
    "&period=2023&cmdCode=9018,9019,9020,9022&flowCode=M,X"
    "&partnerCode=0&partner2Code=0&customsCode=C00&motCode=0"
)

COMTRADE_MONTHLY_URL = (
    "https://comtradeapi.un.org/public/v1/preview/C/M/HS"
    "?reporterCode=842&period=202503&cmdCode=9018&flowCode=M"
    "&partnerCode=0&partner2Code=0&customsCode=C00&motCode=0"
)

COMEXt_ONE = (
    "https://ec.europa.eu/eurostat/api/comext/dissemination/statistics/1.0/data/"
    "DS-045409?format=JSON&lang=EN&freq=A&reporter=DE&partner=WORLD"
    "&product=9018&flow=1&sinceTimePeriod=2023&untilTimePeriod=2023"
)

COMEXT_MULTI = (
    "https://ec.europa.eu/eurostat/api/comext/dissemination/statistics/1.0/data/"
    "DS-045409?format=JSON&lang=EN&freq=A&reporter=DE&partner=WORLD"
    "&product=9018&product=9019&product=9020&product=9022&flow=1&flow=2"
    "&sinceTimePeriod=2015&untilTimePeriod=2024"
)

HMRC_COMMODITY_9018 = (
    "https://api.uktradeinfo.com/Commodity?%24filter=Hs4Code%20eq%20%279018%27"
)

HMRC_OTS_APPLY = (
    "https://api.uktradeinfo.com/OTS?%24apply=filter("
    "(CommodityId%20eq%2090181100%20or%20CommodityId%20eq%2090181200)"
    "%20and%20MonthId%20ge%20202301%20and%20MonthId%20le%20202312)"
    "/groupby((MonthId,FlowTypeId),aggregate(Value%20with%20sum%20as%20TotalValue))"
)

CENSUS_HS_DATA = (
    "https://api.census.gov/data/timeseries/intltrade/imports/hs"
    "?get=CTY_CODE,I_COMMODITY,GEN_VAL_MO,GEN_VAL_YR"
    "&time=2023-12&COMM_LVL=HS4&I_COMMODITY=9018"
)

TED_NOTICE_XML = "https://ted.europa.eu/en/notice/393130-2016/xml"
TED_SINGLE_NOTICE = "https://api.ted.europa.eu/v3/notices/393130-2016"

FTS_PACKAGES = (
    "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages"
    "?stages=award&limit=2"
)

FTS_BAD_PARAM = (
    "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages"
    "?stages=award&keyword=medical&limit=2"
)

IMPORTYETI = "https://www.importyeti.com/"
IMPORTGENIUS = "https://www.importgenius.com/"
PANJIVA = "https://panjiva.com/"
DESCARTES_DATAMYNE = "https://www.descartes.com/datamyne"


def probes() -> list[Probe]:
    return [
        # =================================================================
        # 1. UN Comtrade — public keyless preview API
        # =================================================================
        Probe(
            probe_id="un_comtrade_preview_annual",
            source_id="un_comtrade",
            url=COMTRADE_ANNUAL_URL,
            question=(
                "Does the keyless /public/v1/preview endpoint return annual HS "
                "trade values for 8 reporters x 4 medical HS4 codes x 2 flows?"
            ),
            expect_marker="primaryValue",
            note=(
                "documented path family https://comtradeapi.un.org ; "
                "preview = no subscription key"
            ),
        ),
        Probe(
            probe_id="un_comtrade_preview_monthly",
            source_id="un_comtrade",
            url=COMTRADE_MONTHLY_URL,
            question="Is a monthly (freqCode=M) preview series available keylessly?",
            expect_marker="primaryValue",
        ),
        Probe(
            probe_id="un_comtrade_preview_multi_period",
            source_id="un_comtrade",
            url=(
                "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
                "?reporterCode=156&period=2022,2023&cmdCode=9018&flowCode=M"
                "&partnerCode=0&partner2Code=0&customsCode=C00&motCode=0"
            ),
            question=(
                "Is more than one reference period allowed per preview request? "
                "(documented cap: 1)"
            ),
            note="expected HTTP 400 with 'Maximum number of periods for preview is 1'",
        ),
        Probe(
            probe_id="un_comtrade_public_data_path",
            source_id="un_comtrade",
            url=(
                "https://comtradeapi.un.org/data/v1/get/C/A/HS"
                "?reporterCode=156&period=2023&cmdCode=9018&flowCode=M"
            ),
            question="Is the full (non-preview) data path keyed?",
            note="expected 401/403: the subscription-key path",
        ),
        Probe(
            probe_id="un_comtrade_reference_reporters",
            source_id="un_comtrade",
            url="https://comtradeapi.un.org/files/v1/app/reference/Reporters.json",
            question=(
                "Is the official reporter-code reference file public, so reporter "
                "names need never be guessed?"
            ),
            expect_marker="reporterCode",
        ),
        Probe(
            probe_id="un_comtrade_reference_hs",
            source_id="un_comtrade",
            url="https://comtradeapi.un.org/files/v1/app/reference/HS.json",
            question=(
                "Is the official HS commodity reference public, so HS descriptions "
                "are quoted from source rather than paraphrased?"
            ),
            expect_marker="id",
        ),
        Probe(
            probe_id="un_comtrade_terms",
            source_id="un_comtrade",
            url="https://comtradeplus.un.org/TermsOfUse",
            question="What are the terms of use attached to Comtrade data?",
        ),
        # =================================================================
        # 2. Eurostat Comext — dissemination API
        # =================================================================
        Probe(
            probe_id="eurostat_comext_ds045409_single",
            source_id="eurostat_comext",
            url=COMEXt_ONE,
            question=(
                "Does the Comext dissemination API return DS-045409 (EU trade since "
                "1988 by HS2-4-6 and CN8) values keylessly for one product/year?"
            ),
            expect_marker="VALUE_IN_EUROS",
        ),
        Probe(
            probe_id="eurostat_comext_ds045409_multi",
            source_id="eurostat_comext",
            url=COMEXT_MULTI,
            question=(
                "Can one request cover 4 HS4 codes x 2 flows x 10 years via repeated "
                "product/flow params plus sinceTimePeriod/untilTimePeriod?"
            ),
            expect_marker='"size"',
        ),
        Probe(
            probe_id="eurostat_comext_format_tsv",
            source_id="eurostat_comext",
            url=COMEXt_ONE.replace("format=JSON", "format=TSV"),
            question=(
                "Is a TSV/CSV output format accepted by the Comext dissemination "
                "API (the bulk-ish route)?"
            ),
            note="expected 400 'Invalid value for wsOutputFormat parameter'",
        ),
        Probe(
            probe_id="eurostat_comext_catalogue",
            source_id="eurostat_comext",
            url="https://ec.europa.eu/eurostat/api/comext/dissemination/catalogue/datasets/",
            question="Is there a machine-readable dataset catalogue listing current DS codes?",
        ),
        Probe(
            probe_id="eurostat_comext_newxtweb",
            source_id="eurostat_comext",
            url="https://ec.europa.eu/eurostat/comext/newxtweb/",
            question="Is the Comext bulk-download web UI reachable (and is it a JS app)?",
        ),
        Probe(
            probe_id="eurostat_copyright",
            source_id="eurostat_comext",
            url="https://ec.europa.eu/eurostat/help/copyright-notice",
            question="What reuse licence does Eurostat attach to its data?",
        ),
        # =================================================================
        # 3. UK HMRC Trade Info (uktradeinfo OData)
        # =================================================================
        Probe(
            probe_id="uk_hmrc_api_root",
            source_id="uk_hmrc_trade",
            url="https://api.uktradeinfo.com/",
            question="Does the HMRC Trade Info OData service answer without a key?",
            expect_marker="EntitySet",
        ),
        Probe(
            probe_id="uk_hmrc_metadata",
            source_id="uk_hmrc_trade",
            url="https://api.uktradeinfo.com/%24metadata",
            question="Is the OData $metadata (entity/field schema) public?",
            expect_marker="EntityType",
        ),
        Probe(
            probe_id="uk_hmrc_commodity_hs4",
            source_id="uk_hmrc_trade",
            url=HMRC_COMMODITY_9018,
            question=(
                "Can the CN8 children of HS4 9018 be enumerated from the official "
                "commodity table (so HS scope is quoted, not assumed)?"
            ),
            expect_marker="Hs4Code",
        ),
        Probe(
            probe_id="uk_hmrc_ots_apply_groupby",
            source_id="uk_hmrc_trade",
            url=HMRC_OTS_APPLY,
            question=(
                "Does the OTS aggregate entity support server-side "
                "$apply=filter()/groupby() so exact annual totals need no mass rows?"
            ),
            expect_marker="TotalValue",
        ),
        Probe(
            probe_id="uk_hmrc_ots_raw",
            source_id="uk_hmrc_trade",
            url=(
                "https://api.uktradeinfo.com/OTS?%24filter=CommodityId%20eq%2090181100"
                "%20and%20MonthId%20eq%20202312%20and%20FlowTypeId%20eq%201&%24top=2"
            ),
            question=(
                "What is the native grain of OTS (commodity x country x port x month)?"
            ),
            expect_marker="SuppressionIndex",
        ),
        Probe(
            probe_id="uk_hmrc_flowtype",
            source_id="uk_hmrc_trade",
            url="https://api.uktradeinfo.com/FlowType",
            question=(
                "Are imports/exports split EU vs non-EU, so totals need an explicit sum?"
            ),
            expect_marker="FlowTypeDescription",
        ),
        Probe(
            probe_id="uk_trade_info_site",
            source_id="uk_hmrc_trade",
            url="https://www.uktradeinfo.com/",
            question="Is the Trade Info data portal itself reachable?",
        ),
        # =================================================================
        # 4. US Census trade (api.census.gov)
        # =================================================================
        Probe(
            probe_id="us_census_trade_hs_month",
            source_id="us_census_trade",
            url=CENSUS_HS_DATA,
            question=(
                "Does the Census HS import time-series endpoint return values without "
                "a key?"
            ),
            expect_marker="GEN_VAL_MO",
            note="expected redirect to /data/missing_key.html",
        ),
        Probe(
            probe_id="us_census_trade_variables",
            source_id="us_census_trade",
            url="https://api.census.gov/data/timeseries/intltrade/imports/hs/variables.json",
            question="Is at least the variable dictionary public without a key?",
            expect_marker="variables",
        ),
        Probe(
            probe_id="us_census_key_signup",
            source_id="us_census_trade",
            url="https://api.census.gov/data/key_signup.html",
            question="Is there an official self-service key signup page?",
            expect_marker="key",
        ),
        Probe(
            probe_id="us_census_trade_developers",
            source_id="us_census_trade",
            url="https://www.census.gov/foreign-trade/developers/index.html",
            question="What does Census publish as its developer/API access policy?",
        ),
        # =================================================================
        # 5. USAspending (GET reference endpoints only; POST is in the connector)
        # =================================================================
        Probe(
            probe_id="usaspending_psc_filter_tree",
            source_id="usaspending",
            url="https://api.usaspending.gov/api/v2/references/filter_tree/psc/?depth=3",
            question=(
                "Is the authoritative PSC code list public, so medical-equipment PSC "
                "codes are verified rather than trusted from memory?"
            ),
            expect_marker="MEDICAL",
        ),
        Probe(
            probe_id="usaspending_awards_get",
            source_id="usaspending",
            url="https://api.usaspending.gov/api/v2/search/spending_by_award/",
            question="Is the award-search endpoint GET-able, or POST-only?",
            note="expected 405: POST-only endpoint",
        ),
        Probe(
            probe_id="usaspending_data_dictionary",
            source_id="usaspending",
            url="https://api.usaspending.gov/api/v2/references/data_dictionary/",
            question="Is the field-level data dictionary public?",
            expect_marker="",
        ),
        # =================================================================
        # 6. EU TED (search is POST; these are the GET-able facts)
        # =================================================================
        Probe(
            probe_id="eu_ted_search_get_rejected",
            source_id="eu_ted",
            url="https://api.ted.europa.eu/v3/notices/search?query=medical&limit=1",
            question="Is the v3 notice search POST-only?",
            note="expected 405 'Request method GET is not supported'",
        ),
        Probe(
            probe_id="eu_ted_single_notice_auth",
            source_id="eu_ted",
            url=TED_SINGLE_NOTICE,
            question=(
                "Is single-notice retrieval (the route that carries the full eForms "
                "payload incl. BT-768 Contractor) keyed?"
            ),
            auth_required=True,
            note="expected 400 'Missing Authorization header in request'",
        ),
        Probe(
            probe_id="eu_ted_notice_xml_waf",
            source_id="eu_ted",
            url=TED_NOTICE_XML,
            question=(
                "Is the public per-notice XML/HTML reachable by an automated client, "
                "or is it behind an anti-automation challenge?"
            ),
            note="expected AWS WAF 'Human Verification' interstitial",
        ),
        Probe(
            probe_id="eu_ted_api_docs",
            source_id="eu_ted",
            url="https://docs.ted.europa.eu/api/latest/index.html",
            question="Are the API docs public (i.e. is the keyed route documented)?",
            expect_marker="api",
        ),
        # =================================================================
        # 7. UK Find a Tender (OCDS)
        # =================================================================
        Probe(
            probe_id="uk_fts_release_packages_award",
            source_id="uk_find_a_tender",
            url=FTS_PACKAGES,
            question=(
                "Do award-stage OCDS release packages expose awards[].suppliers[].name?"
            ),
            expect_marker="suppliers",
        ),
        Probe(
            probe_id="uk_fts_param_allowlist",
            source_id="uk_find_a_tender",
            url=FTS_BAD_PARAM,
            question=(
                "Which query parameters does the API accept? (needed to know whether "
                "CPV/keyword filtering is even possible server-side)"
            ),
            note="expected 400 listing: stages, limit, cursor, updatedFrom, updatedTo",
        ),
        Probe(
            probe_id="uk_fts_root",
            source_id="uk_find_a_tender",
            url="https://www.find-tender.service.gov.uk/api/1.0/",
            question="Is there an API index/version document?",
        ),
        # =================================================================
        # 8. sam.gov
        # =================================================================
        Probe(
            probe_id="us_sam_api_root",
            source_id="sam_gov",
            url="https://api.sam.gov/",
            question="Does the SAM.gov API host answer at all without a key?",
            note="observed: HTTP 404 with a zero-byte body",
        ),
        Probe(
            probe_id="us_sam_entity_v2",
            source_id="sam_gov",
            url=(
                "https://api.sam.gov/entity-information/v2/entities"
                "?api_key=test&samRegistered=Yes"
            ),
            question="Does the documented entity endpoint give an auth error or a 404?",
        ),
        Probe(
            probe_id="open_gsa_sam_extracts_docs",
            source_id="sam_gov",
            url="https://open.gsa.gov/api/sam-entity-extracts-api/",
            question="What is the documented, legitimate route to SAM entity data?",
            expect_marker="sam",
        ),
        # =================================================================
        # 9. USITC DataWeb
        # =================================================================
        Probe(
            probe_id="usitc_dataweb_landing",
            source_id="usitc_dataweb",
            url="https://dataweb.usitc.gov/",
            question="Is DataWeb a JS application with no keyless data endpoint?",
        ),
        Probe(
            probe_id="usitc_dataweb_login",
            source_id="usitc_dataweb",
            url="https://dataweb.usitc.gov/login",
            question="Does DataWeb expose an account/login gate?",
        ),
        # =================================================================
        # 10. Commercial bill-of-lading vendors — access model only, no scraping
        # =================================================================
        Probe(
            probe_id="importyeti_home",
            source_id="importyeti",
            url=IMPORTYETI,
            question="Is ImportYeti's public site reachable, and does it publish an API?",
        ),
        Probe(
            probe_id="importyeti_robots",
            source_id="importyeti",
            url="https://www.importyeti.com/robots.txt",
            question="What does ImportYeti's robots.txt allow?",
        ),
        Probe(
            probe_id="importyeti_policies",
            source_id="importyeti",
            url="https://www.importyeti.com/policies",
            question="What do ImportYeti's own policies say about data use?",
        ),
        Probe(
            probe_id="importgenius_home",
            source_id="importgenius",
            url=IMPORTGENIUS,
            question="Is ImportGenius reachable, and does it advertise an API?",
        ),
        Probe(
            probe_id="importgenius_robots",
            source_id="importgenius",
            url="https://www.importgenius.com/robots.txt",
            question="What does ImportGenius's robots.txt allow?",
        ),
        Probe(
            probe_id="importgenius_terms",
            source_id="importgenius",
            url="https://www.importgenius.com/utilities/legal/terms-of-use",
            question="What does the ImportGenius terms of use prohibit?",
            expect_marker="",
        ),
        Probe(
            probe_id="importgenius_api_page",
            source_id="importgenius",
            url="https://www.importgenius.com/features/api-integration",
            question="Is the ImportGenius data API self-service or enterprise-only?",
        ),
        Probe(
            probe_id="panjiva_home",
            source_id="panjiva",
            url=PANJIVA,
            question="Is Panjiva (S&P Global) reachable, and what access model applies?",
        ),
        Probe(
            probe_id="panjiva_robots",
            source_id="panjiva",
            url="https://panjiva.com/robots.txt",
            question="What does Panjiva's robots.txt allow?",
        ),
        Probe(
            probe_id="spglobal_terms",
            source_id="panjiva",
            url="https://www.spglobal.com/en/terms-of-use",
            question="What do the S&P Global terms of use say about automated collection?",
            note="observed: HTTP 403 to a non-browser client",
        ),
        Probe(
            probe_id="descartes_datamyne_home",
            source_id="descartes_datamyne",
            url=DESCARTES_DATAMYNE,
            question="Where does descartes.com/datamyne resolve, and is it a product page?",
        ),
        Probe(
            probe_id="descartes_robots",
            source_id="descartes_datamyne",
            url="https://www.descartes.com/robots.txt",
            question="What does Descartes' robots.txt allow?",
        ),
        Probe(
            probe_id="descartes_legal",
            source_id="descartes_datamyne",
            url="https://www.descartes.com/legal-compliance",
            question="What licence/subscription terms govern Descartes data products?",
            expect_marker="",
        ),
    ]
