"""REGULATORY probe suite — the authoritative ACCESS evidence for this workstream.

Run:

    python -m hz.cli probe --suite regulatory

Each probe asks one falsifiable question and produces one row in
``SOURCE_PROBES/regulatory/PROBES.json`` with status, bytes and sha256. A probe
result states ACCESS only — never DATA, IDENTITY or RESEARCH success.

Where a probe is *expected* to fail (a blocked jurisdiction) the note says so and
the observed failure is the evidence we report.
"""

from __future__ import annotations

from .probe import Probe

AG = "https://accessgudid.nlm.nih.gov"
MDALL = "https://health-products.canada.ca/api/medical-devices"


def probes() -> list[Probe]:
    return [
        # ---------------- United States: GUDID ----------------------------
        Probe(
            probe_id="reg_accessgudid_001",
            source_id="accessgudid",
            url=f"{AG}/api/v3/devices/lookup.json?di=00885074528007",
            question="Does the v3 device-lookup API return JSON for a bare DI without a key?",
            expect_marker='"gudid"',
            note="Documented at /resources/developers/v3/device_lookup_api. "
                 "The old guessed search path /api/v3/devices/search.json returns 404 — "
                 "lookup requires di, udi or record_key; there is no description search.",
        ),
        Probe(
            probe_id="reg_accessgudid_002",
            source_id="accessgudid",
            url=f"{AG}/download",
            question="Is the GUDID release-file download page public and does it list ZIP releases?",
            expect_marker="gudid_full_release",
            note="Release archives gudid_full_release_YYYYMMDD.zip / monthly / weekly are "
                 "keyless; the monthly update is 7,002,352 bytes (measured with an HTTP Range "
                 "request before downloading).",
        ),
        # ---------------- United States: openFDA --------------------------
        Probe(
            probe_id="reg_openfda_510k_001",
            source_id="openfda_device_510k",
            url="https://api.fda.gov/device/510k.json?search=applicant:%22MEDTRONIC%22&limit=1",
            question="Does the device 510(k) endpoint answer keyless on api.fda.gov?",
            expect_marker='"results"',
            note="api.fda.gov (not a separate host) serves the device endpoints. "
                 "No X-RateLimit-* headers are returned; published keyless limits are recorded "
                 "in registry/sources/openfda_device_510k.json.",
        ),
        Probe(
            probe_id="reg_openfda_pma_001",
            source_id="openfda_device_pma",
            url="https://api.fda.gov/device/pma.json?search=applicant:%22PHILIPS%22&limit=1",
            question="Does the PMA endpoint answer keyless and expose pma_number + decision_date?",
            expect_marker='"pma_number"',
            note="PMA records carry decision_date, applicant, product_code, supplement_number.",
        ),
        Probe(
            probe_id="reg_openfda_reglist_001",
            source_id="openfda_device_registrationlisting",
            url=("https://api.fda.gov/device/registrationlisting.json?"
                 "search=registration.owner_operator.firm_name:%22MEDTRONIC%22&limit=1"),
            question="Does registrationlisting answer keyless with the dotted firm_name path?",
            expect_marker='"registration"',
            note="The field path matters: bare owner_operator.firm_name returns NOT_FOUND. "
                 "Record also carries reg_expiry_date_year (the listing expiry year).",
        ),
        Probe(
            probe_id="reg_openfda_classification_001",
            source_id="openfda_device_classification",
            url=("https://api.fda.gov/device/classification.json?"
                 "search=device_name:%22ventilator%22&limit=1"),
            question="Does the classification endpoint answer keyless with product_code/class?",
            expect_marker='"product_code"',
            note="Provides product_code -> device_class + regulation_number, the join key "
                 "between 510(k) records and the CFR regulation.",
        ),
        Probe(
            probe_id="reg_openfda_bulk_001",
            source_id="openfda_bulk_download",
            url="https://api.fda.gov/download.json",
            question="Is the openFDA bulk-download catalogue public, and does it list device exports?",
            expect_marker='"device"',
            note="Catalogue only. The device.udi export is hundreds of MB per partition, outside "
                 "this workstream's byte budget, so no bulk file was downloaded.",
        ),
        # ---------------- Canada: MDALL -----------------------------------
        Probe(
            probe_id="reg_mdall_001",
            source_id="canada_mdall",
            url=f"{MDALL}/company/?company_name=medtronic&lang=en&type=json",
            question="Does the documented /api/medical-devices/company/ base answer keyless JSON?",
            expect_marker="company_name",
            note="The OLD path /api/medical-device/device/ returns HTTP 404 (verified separately). "
                 "Current base per https://health-products.canada.ca/api/documentation/"
                 "mdall-documentation-en.html is /api/medical-devices/.",
        ),
        Probe(
            probe_id="reg_mdall_002",
            source_id="canada_mdall",
            url=f"{MDALL}/licence/?licence_name=ventilator&lang=en&type=json",
            question="Does the licence search answer with official licence numbers and dates?",
            expect_marker="original_licence_no",
            note="Licence objects expose first_licence_status_dt (first issued licence) and "
                 "last_refresh_dt (database refresh stamp) — see the temporal finding in "
                 "DATASETS/regulatory/canada_mdall/COUNTS.json.",
        ),
        Probe(
            probe_id="reg_mdall_003",
            source_id="canada_mdall",
            url=f"{MDALL}/device/?device_name=ventilator&state=active&lang=en&type=json",
            question="Does the device search answer keyless with trade_name + licence number?",
            expect_marker="trade_name",
            note="device/?licence_number=N is documented but returns an unscoped payload "
                 ">2.5 MB (measured), so devices are collected by name and attributed to a "
                 "firm through original_licence_no.",
        ),
        # ---------------- Brazil: ANVISA (the third-country success) -------
        Probe(
            probe_id="reg_anvisa_001",
            source_id="brazil_anvisa",
            url=("https://dados.anvisa.gov.br/dados/CONSULTAS/PRODUTOS/"
                 "TA_CONSULTA_PRODUTOS_SAUDE.CSV"),
            question="Is the ANVISA health-product consultation CSV downloadable without a key?",
            expect_status=(200, 206),
            expect_marker=";",
            note="Keyless bulk CSV. The server caps a Range response at 256 KiB, so a bounded "
                 "prefix is taken rather than the whole file.",
        ),
        # ---------------- Australia: TGA ARTG (blocked) -------------------
        Probe(
            probe_id="reg_tga_001",
            source_id="australia_tga_artg",
            url="https://www.tga.gov.au/robots.txt",
            question="Can the TGA corporate site be reached at all from this host?",
            note="EXPECTED FAILURE (documented, not repaired): www.tga.gov.au resets the TCP "
                 "connection ('RemoteDisconnected'). apps.tga.gov.au answers 200 but only "
                 "redirects to the blocked corporate site, and data.gov.au holds no ARTG dataset.",
        ),
        # ---------------- EU: EUDAMED (registration required) -------------
        Probe(
            probe_id="reg_eudamed_001",
            source_id="eudamed",
            url="https://ec.europa.eu/tools/eudamed/api/devices",
            question="Is there a keyless machine interface into EUDAMED?",
            note="EXPECTED FAILURE: HTTP 429 whose JSON body instructs automated users to use "
                 "the official EUDAMED data API on the EU Health Data Lake developer portal "
                 "(subscription key + EU login).",
        ),
        # ---------------- Japan: PMDA (manual only) -----------------------
        Probe(
            probe_id="reg_pmda_001",
            source_id="japan_pmda",
            url="https://www.pmda.go.jp/english/review-services/reviews/0001.html",
            question="Does PMDA publish device approvals in a machine-readable form?",
            expect_marker="PMDA",
            note="HTML index only; approvals are published as HTML/PDF listings with no "
                 "JSON/CSV/API and no bulk export. MANUAL_ONLY.",
        ),
        # ---------------- UK: MHRA (manual only) --------------------------
        Probe(
            probe_id="reg_mhra_001",
            source_id="uk_mhra_device",
            url=("https://www.gov.uk/api/search.json?q=medical%20device%20register&count=5"),
            question="Does the GOV.UK search API expose an MHRA per-device register?",
            expect_marker="results",
            note="The API answers, but it indexes GOV.UK guidance/alerts content. No per-device "
                 "UK registration register is published as open data. MANUAL_ONLY.",
        ),
        # ---------------- China: NMPA UDI (no machine interface) ----------
        Probe(
            probe_id="reg_nmpa_001",
            source_id="china_nmpa_udi",
            url="https://udi.nmpa.gov.cn/",
            question="Does the NMPA UDI database expose any machine interface?",
            note="HTML application shell only; no JSON/CSV export and no documented API. "
                 "www.nmpa.gov.cn answers HTTP 412 to this client.",
        ),
    ]
