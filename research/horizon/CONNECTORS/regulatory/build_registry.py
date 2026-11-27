"""Write the REGULATORY workstream's registry entries.

Run:  python CONNECTORS/regulatory/build_registry.py

Every value here is traceable to a file this workstream produced: the probe
results in ``SOURCE_PROBES/regulatory/PROBES.json``, the per-source
``DATASETS/regulatory/<source_id>/COUNTS.json``, or the saved raw responses.
``licence_note`` quotes the sentence actually relied on.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from hz.registry import SourceEntry, write_entry  # noqa: E402

from CONNECTORS.regulatory._util import ROOT, utc_now  # noqa: E402

VERIFIED = "2026-11-10T07:30:00Z"

OPENFDA_LICENCE_NOTE = (
    "openFDA licence page: '...unless otherwise noted, the content, data, documentation, code, "
    "and related materials on openFDA is public domain and made available with a Creative "
    "Commons CC0 1.0 Universal dedication.' Caveat recorded on the same page: 'GMDN(R) is a "
    "registered trademark of The GMDN Agency... which is used under license from The GMDN "
    "Agency', with conditions on extracting GMDN Content. openFDA device endpoints do not "
    "carry GMDN fields, so this does not affect the openFDA records."
)

OPENFDA_RATE = (
    "openFDA authentication page: 'With no API key: 240 requests per minute, per IP address. "
    "1,000 requests per day, per IP address.' No X-RateLimit-* response headers are sent; "
    "observed: all keyless pulls returned 200 at ~1.2 req/s, no 429."
)


def entries() -> list[SourceEntry]:
    e: list[SourceEntry] = []

    e.append(SourceEntry(
        source_id="accessgudid",
        name="AccessGUDID (FDA Global Unique Device Identification Database)",
        operator="U.S. National Library of Medicine / U.S. FDA",
        domain="accessgudid.nlm.nih.gov",
        access_state="OPEN_DOCUMENTED",
        access_evidence=(
            "PROBES.json reg_accessgudid_001: HTTP 200 application/json 2,806 bytes for "
            "/api/v3/devices/lookup.json?di=00885074528007; reg_accessgudid_002: HTTP 200 "
            "text/html 44,748 bytes on /download listing gudid_full_release_*.zip. "
            "DATASETS/regulatory/accessgudid/raw/ holds the 7,002,352-byte monthly release ZIP "
            "(sha256 e9d6c8dbecbebce3...) and 10 lookup responses."
        ),
        machine_interface=(
            "REST JSON v3: /devices/lookup.json (by di | udi | record_key), /devices/history.json, "
            "/devices/snomed.json, /devices/parse_udi.json, /devices/implantable/list|download. "
            "Plus ZIP release files (full / monthly / weekly / daily) of GUDID XML."
        ),
        auth_required=False,
        rate_policy="No documented quota. Observed 10 lookups at ~1 req/s, all HTTP 200.",
        licence_status="public_domain",
        licence_url=None,
        licence_note=(
            "US federal government dataset (FDA GUDID, redistributed by NLM). No reuse "
            "restriction and no login is stated on the download or API pages, and robots.txt "
            "disallows nothing. No explicit licence sentence is published on the release pages, "
            "so this is recorded as public_domain on the basis of US federal authorship rather "
            "than of an explicit licence statement. GMDN term names carried in GUDID are "
            "third-party content (see the openFDA licence caveat)."
        ),
        robots_url="https://accessgudid.nlm.nih.gov/robots.txt",
        robots_summary=(
            "HTTP 200, 267 bytes. The 'User-agent: * / Disallow: /' block is commented out, so "
            "no path is disallowed. Declares Sitemap: "
            "https://accessgudid.nlm.nih.gov/sitemaps/sitemap.xml.gz"
        ),
        bulk_available=True,
        historical_depth=(
            "Current full release plus dated daily/weekly/monthly delta archives (October 2026 "
            "monthly archive bundles 21 daily XML deltas, ~59,774 device records scanned). "
            "Superseded versions are not served as separate files; each record exposes "
            "publicVersionNumber/publicVersionDate and devicePublishDate instead."
        ),
        first_verified_at=VERIFIED,
        what_is_new=(
            "First GUDID-derived inventory in MedRadar that separates the public clock "
            "(devicePublishDate) from the event clock, and that keeps the full official UDI-DI "
            "plus model/catalogue numbers, so a device can be matched to other sources on an "
            "identifier rather than on a name."
        ),
        id_schemes=["udi_di", "gtin", "fda_product_code"],
        entity_types=["product_identifier"],
        blockers=[],
        unlock_route="",
        probe_suite="regulatory",
        notes=(
            "There is NO description/keyword search in the public API: the guessed path "
            "/api/v3/devices/search.json returns HTTP 404 with body "
            "{'timestamp':...,'status':404,...}. Bulk sampling therefore uses the release ZIPs. "
            "COUNTS.json in DATASETS/regulatory/accessgudid/ records the selection rule."
        ),
    ))

    ofda_common = dict(
        operator="U.S. Food and Drug Administration",
        domain="api.fda.gov",
        access_state="OPEN_DOCUMENTED",
        auth_required=False,
        rate_policy=OPENFDA_RATE,
        licence_status="public_domain",
        licence_url="https://open.fda.gov/license/",
        licence_note=OPENFDA_LICENCE_NOTE,
        robots_url="https://api.fda.gov/robots.txt",
        robots_summary="HTTP 404 with body 'Cannot GET /robots.txt' — no robots policy is served "
                       "for the API host; access is governed by the published openFDA terms.",
        bulk_available=True,
        first_verified_at=VERIFIED,
        probe_suite="regulatory",
    )

    e.append(SourceEntry(
        source_id="openfda_device_510k",
        name="openFDA — device 510(k) clearances",
        machine_interface="REST JSON: /device/510k.json with Lucene-style search, limit<=1000, skip",
        access_evidence=(
            "PROBES.json reg_openfda_510k_001: HTTP 200 application/json 3,205 bytes for "
            "search=applicant:\"MEDTRONIC\"&limit=1. DATASETS/regulatory/openfda_device_510k/raw/ "
            "holds 8 pulls; 50/50 records in each firm pull match its applicant term "
            "(see CONNECTORS/regulatory/_verify_cache_integrity.py output)."
        ),
        historical_depth=(
            "FDA 510(k) decisions reported from 1976 onward; 1,588 MEDTRONIC matches, 1,036 GE "
            "matches, 994 PHILIPS matches, 34 DRAGER matches, 180 MINDRAY matches as of this run "
            "(meta.results.total). No historical supersession: one row per clearance."
        ),
        what_is_new=(
            "Adds the clearable event clock (decision_date) that GUDID lacks, and the official "
            "510(k) number as a join key — the first precedent-shaped regulatory signal in "
            "MedRadar with a jurisdiction, a date and an identifier."
        ),
        id_schemes=["uspto_510k", "fda_product_code"],
        entity_types=["regulatory_clearance"],
        blockers=[],
        unlock_route="",
        notes="Records carry k_number, decision_date, product_code, applicant, device_name, "
              "advisory_committee. source_public_at is unknown (MISSING_PUBLICATION_DATE).",
        **ofda_common,
    ))

    e.append(SourceEntry(
        source_id="openfda_device_pma",
        name="openFDA — device Premarket Approvals (PMA)",
        machine_interface="REST JSON: /device/pma.json",
        access_evidence=(
            "PROBES.json reg_openfda_pma_001: HTTP 200, 1,977 bytes, marker 'pma_number'. "
            "DATASETS/regulatory/openfda_device_pma/raw/ holds 3 pulls (12,900 MEDTRONIC "
            "supplement matches, 169 PHILIPS)."
        ),
        historical_depth="PMA approvals and supplements; supplement_number distinguishes "
                        "original approvals from supplements.",
        what_is_new="Highest-risk device approvals with an official pma_number, complementing "
                   "the 510(k) clearance series.",
        id_schemes=["uspto_pma", "fda_product_code"],
        entity_types=["regulatory_clearance"],
        blockers=[],
        unlock_route="",
        notes="The endpoint mixes original PMAs and supplements; pma_number repeats across "
              "supplement rows, so unique_official_ids < records (33 of 60).",
        **ofda_common,
    ))

    e.append(SourceEntry(
        source_id="openfda_device_registrationlisting",
        name="openFDA — device establishment registration & device listing",
        machine_interface="REST JSON: /device/registrationlisting.json",
        access_evidence=(
            "PROBES.json reg_openfda_reglist_001: HTTP 200, 2,158 bytes, dotted path "
            "search=registration.owner_operator.firm_name:\"MEDTRONIC\"&limit=1. "
            "5,205 MEDTRONIC / 2,392 PHILIPS matches."
        ),
        historical_depth="Current registration snapshot with reg_expiry_date_year per "
                         "establishment; no superseded registration rows.",
        what_is_new="Establishment-level FEI numbers and registration expiry years — the "
                   "regulatory footprint behind a licence, not just the product approval.",
        id_schemes=["fda_fei", "fda_registration_number", "fda_product_code"],
        entity_types=["regulatory_listing"],
        blockers=[],
        unlock_route="",
        notes="Query field matters: bare owner_operator.firm_name returns NOT_FOUND; the working "
              "path is registration.owner_operator.firm_name. 'DRAGER' returns NOT_FOUND because "
              "the firm is indexed as Dräger — an honest tokenisation gap, not a bug.",
        **ofda_common,
    ))

    e.append(SourceEntry(
        source_id="openfda_device_classification",
        name="openFDA — device classification (product code → class / regulation)",
        machine_interface="REST JSON: /device/classification.json",
        access_evidence=(
            "PROBES.json reg_openfda_classification_001: HTTP 200, 5,478 bytes, marker "
            "'product_code'. Pulls: 79 deviceName~monitor, 22 ~ventilator, 29 ~infusion matches."
        ),
        historical_depth="Current classification table; regulation_number points at the CFR "
                         "section that governs the device type.",
        what_is_new="The join table that turns a bare product_code into device_class + "
                   "regulation_number, so 510(k) rows can be grouped by risk instead of by "
                   "substring.",
        id_schemes=["fda_product_code", "cfr_regulation"],
        entity_types=["regulatory_listing"],
        blockers=[],
        unlock_route="",
        notes="No dates of any kind: both clocks are missing and flagged.",
        **ofda_common,
    ))

    e.append(SourceEntry(
        source_id="openfda_bulk_download",
        name="openFDA — bulk download catalogue",
        machine_interface="REST JSON catalogue: /download.json (per-endpoint exported JSON files)",
        access_evidence=(
            "PROBES.json reg_openfda_bulk_001: HTTP 200, 601,654 bytes, marker 'device'. "
            "DATASETS/regulatory/openfda_bulk_download/raw/download_catalogue.json saved verbatim; "
            "COUNTS.json summarises the device exports and their partition sizes."
        ),
        historical_depth="Files are dated exports (export_date per endpoint).",
        what_is_new=(
            "Documents that openFDA bulk export exists and is keyless, and quantifies why it is "
            "the wrong tool for a bounded study: the device.udi export alone runs to hundreds of "
            "MB per partition."
        ),
        id_schemes=["fda_product_code", "udi_di"],
        entity_types=["product_identifier", "regulatory_clearance"],
        blockers=["Bulk device exports exceed this workstream's byte budget; catalogue only."],
        unlock_route="",
        notes="Deliberately used as catalogue-only evidence; no bulk file was downloaded.",
        **ofda_common,
    ))

    e.append(SourceEntry(
        source_id="canada_mdall",
        name="Medical Devices Active Licence Listing (MDALL)",
        operator="Health Canada",
        domain="health-products.canada.ca",
        access_state="OPEN_DOCUMENTED",
        access_evidence=(
            "PROBES.json reg_mdall_001/002/003: HTTP 200 JSON for company search (6,909 bytes), "
            "licence search (55,291 bytes) and device search (45,068 bytes). The historical path "
            "/api/medical-device/device/ returns HTTP 404 (recorded in "
            "DATASETS/regulatory/_discovery/round1.json); the working base is "
            "/api/medical-devices/."
        ),
        machine_interface=(
            "REST JSON/XML under https://health-products.canada.ca/api/medical-devices/: "
            "licence/, company/, device/, deviceidentifier/, licencetype/, sbdlocation/. "
            "Params: id, state (active|archived), licence_name, company_id, device_name, "
            "licence_number, device_identifier, lang, type."
        ),
        auth_required=False,
        rate_policy="No documented quota. Observed ~20 calls at ~1.2 req/s; the unbounded "
                    "licence?company_id= and device?licence_number= calls time out or return "
                    ">2.5 MB for large firms.",
        licence_status="open_licence",
        licence_url="https://open.canada.ca/en/open-government-licence-canada",
        licence_note=(
            "Open Government Portal dataset c801a084-210b-4cd2-8513-26a00b66eb6f 'Medical Devices "
            "Active Licence Listing (MDALL)' states licence_title 'Open Government Licence - "
            "Canada' with license_url https://open.canada.ca/en/open-government-licence-canada."
        ),
        robots_url="https://health-products.canada.ca/robots.txt",
        robots_summary="HTTP 404 (ASP.NET error page) — no robots policy is served.",
        bulk_available=True,
        historical_depth=(
            "Two states: active (no cancellation date) and archived (carries end_date), so "
            "cancelled licences are retained. Per-device and per-identifier first/end dates are "
            "published. There is NO publication clock and NO status-change date."
        ),
        first_verified_at=VERIFIED,
        what_is_new=(
            "First Canadian counterpart data in MedRadar with official licence numbers "
            "(original_licence_no) and per-identifier model tokens, which is what makes an "
            "FDA<->Canada identity experiment possible at all — and what exposes that the two "
            "jurisdictions share no identifier namespace."
        ),
        id_schemes=["hc_device_licence", "hc_mdall_device_id", "hc_mdall_device_identifier"],
        entity_types=["regulatory_clearance", "regulatory_listing", "product_identifier"],
        blockers=[
            "licence?company_id=N is unbounded for large firms (read timeout observed on "
            "Medtronic company_id 114663).",
            "device?licence_number=N is documented but unscoped: every call returned >2.5 MB.",
        ],
        unlock_route="",
        probe_suite="regulatory",
        notes=(
            "Work-around used instead of the two broken filters: discover licences via "
            "licence_name=<keyword> and attribute them to a firm by the official company_id from "
            "company?company_name=<firm>; collect devices via device_name=<keyword>&state=active "
            "and attribute via original_licence_no. Documented in "
            "DATASETS/regulatory/canada_mdall/COUNTS.json."
        ),
    ))

    e.append(SourceEntry(
        source_id="brazil_anvisa",
        name="ANVISA open data — health product consultation (Produtos para Saúde)",
        operator="Agência Nacional de Vigilância Sanitária (ANVISA), Brazil",
        domain="dados.anvisa.gov.br",
        access_state="OPEN",
        access_evidence=(
            "PROBES.json reg_anvisa_001 records the unbounded GET exceeding our 6 MB cap "
            "(TOO_LARGE) — the file is large. The bounded path succeeded: "
            "DATASETS/regulatory/brazil_anvisa/raw/TA_CONSULTA_PRODUTOS_SAUDE.csv.head256k is an "
            "HTTP 206 Range response, 262,144 bytes, parsed into 902 rows; the directory index "
            "/dados/CONSULTAS/PRODUTOS/ (HTTP 200, 5,539 bytes) lists 12 TA_CONSULTA_*.CSV files."
        ),
        machine_interface="Bulk CSV over HTTP (h5ai directory index). No REST API.",
        auth_required=False,
        rate_policy="No stated quota. One prefix request; no throttling observed.",
        licence_status="open_no_explicit_licence",
        licence_url="https://www.gov.br/anvisa/pt-br/acessoainformacao/dadosabertos",
        licence_note=(
            "ANVISA presents the files on its 'dados abertos' portal with no login and no key, "
            "and the directory index carries no licence statement. Recorded as "
            "open_no_explicit_licence rather than inventing a CC-BY grant."
        ),
        robots_url="https://dados.anvisa.gov.br/robots.txt",
        robots_summary="HTTP 404 — no robots policy is served.",
        bulk_available=True,
        historical_depth=(
            "One current-state consultation table per product category (medical devices, IVD, "
            "medicines, cosmetics...). Row-level dates present: DT_INICIO_VIGENCIA, "
            "DT_VENCIMENTO_REGISTRO, DT_CARGA_ETL (ETL load stamp). No version history."
        ),
        first_verified_at=VERIFIED,
        what_is_new=(
            "The one non-US/non-Canadian jurisdiction that yielded genuine keyless records: "
            "Brazilian device registrations with an official ANVISA registro number, risk class "
            "(SG_RISCO_PRODUTO) and registration validity dates."
        ),
        id_schemes=["anvisa_registro"],
        entity_types=["regulatory_listing"],
        blockers=["Server caps HTTP Range responses at 256 KiB, so only a 256 KiB prefix "
                  "(902 rows) was sampled; the full file is outside budget."],
        unlock_route="",
        probe_suite="regulatory",
        notes="DT_CARGA_ETL is an ETL load timestamp, NOT a publication date; it is not used as "
              "source_public_at.",
    ))

    e.append(SourceEntry(
        source_id="australia_tga_artg",
        name="Therapeutic Goods Administration — Australian Register of Therapeutic Goods (ARTG)",
        operator="Therapeutic Goods Administration, Australia",
        domain="www.tga.gov.au",
        access_state="BLOCKED_TECHNICAL",
        access_evidence=(
            "PROBES.json reg_tga_001: TRANSPORT_ERROR — "
            "ConnectionError('Connection aborted.', RemoteDisconnected('Remote end closed "
            "connection without response')) on https://www.tga.gov.au/robots.txt. Repeated for "
            "https://www.tga.gov.au/ (read timeout) and http://www.tga.gov.au/robots.txt "
            "(ConnectionResetError 10054). https://apps.tga.gov.au/ answers HTTP 200 but its only "
            "content is a 221-byte meta-refresh to the blocked corporate site. "
            "data.gov.au CKAN package_search for 'artg' / 'therapeutic goods' returned no ARTG "
            "dataset (rows are NSW gazettes and unrelated PDFs)."
        ),
        machine_interface="None reachable. ARTG public search is a human HTML application.",
        auth_required=False,
        rate_policy="n/a — the host closes the connection before any HTTP response.",
        licence_status="unknown",
        licence_url=None,
        licence_note=(
            "Not determinable: the licence statement lives on the unreachable www.tga.gov.au. "
            "TGA material is normally published under a Creative Commons Attribution 3.0 "
            "Australia licence, but that could not be read from the source, so it is recorded as "
            "unknown rather than assumed."
        ),
        robots_url="https://www.tga.gov.au/robots.txt",
        robots_summary="Not retrievable — TCP connection reset before a response.",
        bulk_available=False,
        historical_depth="Unknown (no access).",
        first_verified_at=VERIFIED,
        what_is_new="Nothing obtained. Recorded as a clean negative with the exact transport "
                   "evidence so the next workstream does not repeat the attempt blind.",
        id_schemes=["artg_id"],
        entity_types=["regulatory_listing"],
        blockers=[
            "www.tga.gov.au resets/closes the TCP connection from this host (RemoteDisconnected, "
            "then ConnectionResetError 10054).",
            "No ARTG dataset is published on data.gov.au (CKAN package_search verified).",
        ],
        unlock_route=(
            "ARTG is queried through the human search at https://www.tga.gov.au/resources/artg. "
            "For machine access, request data from TGA (https://www.tga.gov.au/about-us/"
            "contact-us) or via the Australian Government data-sharing process; there is no "
            "published keyless ARTG bulk export."
        ),
        probe_suite="regulatory",
    ))

    e.append(SourceEntry(
        source_id="eudamed",
        name="EUDAMED — European Database on Medical Devices",
        operator="European Commission, DG SANTE",
        domain="ec.europa.eu/tools/eudamed",
        access_state="REQUIRES_REGISTRATION",
        access_evidence=(
            "PROBES.json reg_eudamed_001: HTTP 429 with JSON body {'error':'Too many requests. "
            "Please try again later.','message':'For automated/machine-to-machine access, please "
            "use the official EUDAMED data API instead of scraping the public endpoints.',"
            "'machineToMachineApi':'https://developer.datalake.sante.service.ec.europa.eu/"
            "api-details#api=94b9e658-d721-4b58-8d96-022c490f7a17'}. The public application root "
            "returns HTTP 200 HTML (48,323 bytes) but carries no data without the JS app."
        ),
        machine_interface="Official EUDAMED data API on the EU Health Data Lake developer portal; "
                          "requires an EU Login identity and a subscription key.",
        auth_required=True,
        registration_url="https://developer.datalake.sante.service.ec.europa.eu/api-details",
        rate_policy="Public web endpoints are rate-limited (429 observed on first automated call).",
        licence_status="terms_restricted",
        licence_url="https://developer.datalake.sante.service.ec.europa.eu/api-details",
        licence_note=(
            "EUDAMED's own 429 body directs machine users to the official data API instead of "
            "the public endpoints, which places reuse under the developer-portal terms rather "
            "than an open licence."
        ),
        robots_url="https://ec.europa.eu/robots.txt",
        robots_summary="HTTP 200, 10,827 bytes returned; the content was not parsed for this "
                       "workstream, so no rule is asserted here.",
        bulk_available=True,
        historical_depth="Unknown (no authorised access).",
        first_verified_at=VERIFIED,
        what_is_new="Nothing obtained. Establishes that EUDAMED is registration-gated for "
                   "machine access and names the exact official route to unblock it.",
        id_schemes=["eudamed_sru", "basic_udi_di"],
        entity_types=["regulatory_listing", "product_identifier"],
        blockers=[
            "Public API paths return HTTP 429 with an explicit anti-scraping instruction.",
            "The official data API requires EU Login + subscription key.",
        ],
        unlock_route=(
            "Register at the EU Health Data Lake developer portal "
            "(https://developer.datalake.sante.service.ec.europa.eu/api-details), subscribe to "
            "the EUDAMED data API, then call it with the subscription key."
        ),
        probe_suite="regulatory",
    ))

    e.append(SourceEntry(
        source_id="japan_pmda",
        name="PMDA — Pharmaceuticals and Medical Devices Agency (Japan) device approvals",
        operator="Pharmaceuticals and Medical Devices Agency, Japan",
        domain="www.pmda.go.jp",
        access_state="MANUAL_ONLY",
        access_evidence=(
            "PROBES.json reg_pmda_001: HTTP 200 text/html 58,415 bytes on the English "
            "review-services index. The page is an HTML/PDF index of review information; no "
            "JSON, CSV or bulk endpoint was found. robots.txt returns HTTP 404 (HTML error page)."
        ),
        machine_interface="HTML indexes and PDFs only.",
        auth_required=False,
        rate_policy="No stated quota; nothing automated was attempted beyond the index pages.",
        licence_status="unknown",
        licence_url=None,
        licence_note="No licence statement was read for PMDA content in this workstream, so it is "
                     "recorded as unknown rather than assumed open.",
        robots_url="https://www.pmda.go.jp/robots.txt",
        robots_summary="HTTP 404 returning an HTML page (70,060 bytes) — no robots policy is "
                       "served.",
        bulk_available=False,
        historical_depth="HTML/PDF approval listings; no machine-readable history.",
        first_verified_at=VERIFIED,
        what_is_new="Nothing obtained. Documents that Japan's device approvals are not a keyless "
                   "machine source.",
        id_schemes=["pmda_approval_number"],
        entity_types=["regulatory_clearance"],
        blockers=["No machine-readable endpoint; HTML/PDF only.", "Japanese-language content."],
        unlock_route=(
            "PMDA publishes approval information as HTML/PDF; there is no keyless API to request. "
            "Machine use would require scraping those indexes or a commercial data agreement."
        ),
        probe_suite="regulatory",
    ))

    e.append(SourceEntry(
        source_id="uk_mhra_device",
        name="MHRA — UK medical device register / market surveillance",
        operator="Medicines and Healthcare products Regulatory Agency, UK",
        domain="www.gov.uk",
        access_state="MANUAL_ONLY",
        access_evidence=(
            "PROBES.json reg_mhra_001: HTTP 200 application/json 13,426 bytes from the GOV.UK "
            "search API for 'medical device register'. The results are GOV.UK guidance and "
            "publication pages; no per-device registration dataset is published."
        ),
        machine_interface="GOV.UK content API (guidance/alerts pages), not a device register.",
        auth_required=False,
        rate_policy="GOV.UK search API is public; no quota exercised.",
        licence_status="open_licence",
        licence_url="https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
        licence_note=(
            "GOV.UK content is published under the Open Government Licence v3.0. No licence "
            "sentence was quoted for a device register because no device register was found."
        ),
        robots_url="https://www.gov.uk/robots.txt",
        robots_summary="Not fetched in this workstream; no assertion made.",
        bulk_available=False,
        historical_depth="Guidance/alerts pages only.",
        first_verified_at=VERIFIED,
        what_is_new="Nothing obtained. Records that the UK has no open per-device register, which "
                   "is itself a coverage boundary for the frontier map.",
        id_schemes=[],
        entity_types=["regulatory_listing"],
        blockers=["No public per-device UK registration register exists as open data."],
        unlock_route=(
            "MHRA device alerts/guidance are on GOV.UK. Company-level registration data is not "
            "open; access would require an FOI request to MHRA."
        ),
        probe_suite="regulatory",
    ))

    e.append(SourceEntry(
        source_id="china_nmpa_udi",
        name="NMPA UDI database (China)",
        operator="National Medical Products Administration, China",
        domain="udi.nmpa.gov.cn",
        access_state="MANUAL_ONLY",
        access_evidence=(
            "PROBES.json reg_nmpa_001: HTTP 200 text/html 49,373 bytes from "
            "https://udi.nmpa.gov.cn/ — an application shell with no data payload and no "
            "documented API. https://www.nmpa.gov.cn/ returns HTTP 412 (2,506 bytes) to this "
            "client with a JS anti-bot challenge page."
        ),
        machine_interface="None documented. Chinese-language web query application.",
        auth_required=False,
        rate_policy="n/a",
        licence_status="unknown",
        licence_url=None,
        licence_note="No licence statement was readable from the accessible pages; recorded as "
                     "unknown.",
        robots_url="https://udi.nmpa.gov.cn/robots.txt",
        robots_summary="Not fetched; no assertion made.",
        bulk_available=False,
        historical_depth="Unknown.",
        first_verified_at=VERIFIED,
        what_is_new="Nothing obtained. Records that NMPA UDI is a human-query interface with an "
                   "anti-bot layer, so China is not a keyless source.",
        id_schemes=["nmpa_udi_di"],
        entity_types=["product_identifier"],
        blockers=["No machine interface.", "www.nmpa.gov.cn answers HTTP 412 with a JS challenge."],
        unlock_route=(
            "Query https://udi.nmpa.gov.cn/ as a human, or obtain data through a Chinese "
            "regulatory-intelligence vendor. No official keyless API exists."
        ),
        probe_suite="regulatory",
    ))

    return e


def main() -> int:
    written = []
    for entry in entries():
        path = write_entry(ROOT, entry)
        written.append(os.path.relpath(path, ROOT).replace(os.sep, "/"))
        print("wrote", written[-1])
    print(f"\n{len(written)} registry entries written at {utc_now()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
