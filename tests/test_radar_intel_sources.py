"""Tests for the intelligence-layer sources added in INTEL-v2.

Coverage note, because this repository is strict about it: the paths exercised here are the
ones that decide whether a number is allowed into the product - URL derivation, document
sectioning, the two adapters' time semantics, the reference store's joins, and the binary
fetch path. The network is never touched; every source response is a fixture shaped like the
real one, captured on 2026-11-21.
"""

from __future__ import annotations

import json
import zlib
from pathlib import Path

import pytest

from medradar.radar.adapters import available_sources, build_adapters
from medradar.radar.adapters.europepmc import EuropePmcAdapter
from medradar.radar.adapters.europepmc import _record as epmc_record
from medradar.radar.adapters.maude import MaudeAdapter
from medradar.radar.documents import (
    derive_510k_pdf_url,
    derive_pma_urls,
    split_sections,
)
from medradar.radar.pdf import extract_text
from medradar.radar.records import Scope
from medradar.radar.reference import DEVICE_COLUMNS, UdiReference

#: The repository's config directory, used by the adapter fixtures below.
CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "radar"


# --------------------------------------------------------------------------- fixtures
def _pdf(content: bytes) -> bytes:
    packed = zlib.compress(content)
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Length " + str(len(packed)).encode()
        + b" /Filter /FlateDecode >>\nstream\n"
        + packed
        + b"\nendstream\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"
    )


CONTENT = (
    b"BT\n/F1 12 Tf\n72 720 Td\n(Indications for Use) Tj\n"
    b"72 700 Td\n(The device is a self-expanding catheter.) Tj\n"
    b"72 680 Td\n(Substantial Equivalence) Tj\nET\n"
)


class _Response:
    def __init__(self, payload: bytes, status: int = 200, headers=None) -> None:
        self._payload = payload
        self.status = status
        self.headers = headers or {"Content-Type": "application/pdf"}

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False


class _Topic:
    product_codes = ("MHX",)


class _Taxonomy:
    topics = (_Topic(),)


MAUDE_ROW = {
    "mdr_report_key": "100001",
    "report_number": "6000002-1997-00486",
    "event_type": "Malfunction",
    "date_of_event": "19970320",
    "date_received": "19970618",
    "date_added": "19970625",
    "product_problems": ["Device, or device fragments remain in patient", "Tip breakage"],
    "device": [{
        "brand_name": "FOGARTY ARTERIAL EMBOLECTOMY CATHETER",
        "generic_name": "EMBOLECTOMY CATHETER",
        "manufacturer_d_name": "BAXTER HEALTHCARE CORP.",
        "model_number": "12-080-3F",
        "catalog_number": "NA",
        "device_report_product_code": "DXE",
        "baseline_510_k__number": "K950913",
    }],
    "mdr_text": [
        {"text_type_code": "Description of Event or Problem",
         "text": "WHEN CATHETER WAS REMOVED FROM THE ARTERY, THE BALLOON AND SPRING TIP WERE MISSING."},
        {"text_type_code": "Manufacturer Narrative", "text": "Device was returned to manufacturer."},
    ],
}

EPMC_ROW = {
    "id": "43035860",
    "source": "MED",
    "pmid": "43035860",
    "doi": "10.1536/ihj.26-233",
    "title": "Integrated ablation and left atrial appendage occlusion.",
    "abstractText": "A one-stop strategy combining AF ablation and LAAO.",
    "firstPublicationDate": "2026-11-13",
    "firstIndexDate": "2026-11-16",
    "electronicPublicationDate": "2026-11-13",
    "isOpenAccess": "N",
    "inPMC": "N",
    "hasPDF": "N",
    "citedByCount": 0,
    "journalInfo": {"journal": {"title": "International heart journal"}},
    "authorList": {"author": [{
        "fullName": "Lee WC",
        "authorAffiliationDetailsList": {"authorAffiliation": [
            {"affiliation": "Division of Cardiology, Chi Mei Medical Center."},
            {"affiliation": "Acme Medical Devices Inc, San Jose, CA."},
        ]},
    }]},
}

UDI_ROWS = [
    {
        "device_description": "Diagnostix Desk Set",
        "brand_name": "Diagnostix",
        "company_name": "AMERICAN DIAGNOSTIC CORP",
        "labeler_duns_number": "108999095",
        "catalog_number": "55102A",
        "version_or_model_number": "55102A",
        "identifiers": [{"id": "00634782076825", "type": "Primary", "issuing_agency": "GS1"}],
        "product_codes": [{"code": "ERA", "name": "Otoscope", "openfda": {
            "regulation_number": "874.4770", "device_class": "1"}}],
        "premarket_submissions": [{"submission_number": "K950913", "supplement_number": "000"}],
        "gmdn_terms": [{"code": "45084", "name": "Ophthalmic/otologic diagnostic set",
                        "implantable": "false"}],
        "is_single_use": "false", "is_kit": "true", "is_rx": "false", "is_pm_exempt": "false",
        "mri_safety": "Labeling does not contain MRI Safety Information",
        "publish_date": "2016-09-21", "public_version_date": "2018-07-06",
        "record_status": "Published",
    },
    {
        "device_description": "Tyber Trauma Screw",
        "brand_name": "Tyber",
        "company_name": "TYBER MEDICAL LLC",
        "labeler_duns_number": "117222222",
        "catalog_number": "TS-44",
        "version_or_model_number": "12-080-3F",
        "identifiers": [{"id": "00812345678901", "type": "Primary", "issuing_agency": "GS1"}],
        "product_codes": [{"code": "HWC", "openfda": {
            "regulation_number": "888.3040", "device_class": "2"}}],
        "premarket_submissions": [{"submission_number": "K252901", "supplement_number": "000"}],
        "record_status": "Published",
    },
]


class _PageFetcher:
    """Returns scripted pages so the reference store's paging contract can be asserted."""

    def __init__(self, rows, total=None) -> None:
        self.rows = rows
        self.total = total if total is not None else len(rows)
        self.calls = 0

    def get_json(self, url, *, params=None, allow_not_found=False):
        limit = int((params or {}).get("limit") or 1000)
        skip = int((params or {}).get("skip") or 0)
        self.calls += 1
        chunk = self.rows[skip:skip + limit]
        return {
            "meta": {"last_updated": "2026-11-02",
                     "results": {"skip": skip, "limit": limit, "total": self.total}},
            "results": chunk,
        }


# ------------------------------------------------------------------------- 510(k) URLs
@pytest.mark.parametrize("k_number,expected", [
    ("K252901", "https://www.accessdata.fda.gov/cdrh_docs/pdf25/K252901.pdf"),
    ("k243627", "https://www.accessdata.fda.gov/cdrh_docs/pdf24/K243627.pdf"),
    ("K013456", "https://www.accessdata.fda.gov/cdrh_docs/pdf01/K013456.pdf"),
])
def test_510k_url_derivation_matches_the_observed_rule(k_number, expected):
    assert derive_510k_pdf_url(k_number) == expected


@pytest.mark.parametrize("value", ["", "K12", "not-a-number", None, "K1"])
def test_510k_url_is_none_when_the_identifier_cannot_be_used(value):
    assert derive_510k_pdf_url(value) is None


def test_pma_urls_are_candidates_not_answers():
    candidates = derive_pma_urls("P980016")
    assert candidates and all(name.startswith("https://") for name in candidates)
    assert derive_pma_urls("not-a-pma") == []


# ------------------------------------------------------------------------ pdf extractor
def test_text_layer_is_extracted_with_line_breaks():
    result = extract_text(_pdf(CONTENT), min_chars=10)
    assert result.has_text_layer
    assert "Indications for Use" in result.text
    assert "self-expanding catheter" in result.text
    assert result.summary()["extractor"] == "medradar.radar.pdf/1"


def test_a_non_pdf_payload_is_reported_not_raised():
    result = extract_text(b"<html>403 Forbidden</html>")
    assert not result.has_text_layer
    assert result.reason == "not_a_pdf"


def test_encrypted_pdf_is_named_as_such():
    result = extract_text(b"%PDF-1.7\n2 0 obj\n<< /Encrypt 3 0 R >>\nendobj\n")
    assert result.reason == "encrypted"


def test_a_pdf_without_streams_is_not_called_empty_text():
    result = extract_text(b"%PDF-1.4\ntrailer\n<<>>\n%%EOF\n")
    assert result.reason == "no_content_stream"
    assert result.has_text_layer is False


def test_short_text_is_flagged_as_a_scan_stub_rather_than_accepted():
    result = extract_text(_pdf(b"BT\n72 720 Td\n(Page 1 of 12) Tj\nET\n"))
    assert not result.has_text_layer
    assert result.reason == "text_too_short"


# --------------------------------------------------------------------------- sections
SUMMARY_TEXT = """510(k) Summary
27. Indications for Use
The device is indicated for percutaneous aspiration of thrombus.

Device Description
A dual-lumen catheter with a radiopaque marker band.

Substantial Equivalence
The subject device is substantially equivalent to the predicate K123456.

Performance Data
Burst pressure testing per ISO 10555-1 passed at 3.0 MPa.

Sterilization
Sterilized by ethylene oxide per ISO 11135.
"""


def test_sections_are_split_on_the_headings_that_actually_appear():
    sections = split_sections(SUMMARY_TEXT)
    assert "indications" in sections
    assert "catheter" in sections["device_description"].lower()
    assert "K123456" in sections["substantial_equivalence"]
    assert "3.0 MPa" in sections["performance_data"]
    assert "ethylene oxide" in sections["sterilization"]


def test_an_absent_section_is_absent_not_empty():
    sections = split_sections("Indications for Use\nThe device aspirates thrombus.\n")
    assert "clinical_data" not in sections
    assert split_sections("") == {}


# ----------------------------------------------------------------------------- MAUDE
def test_maude_event_time_is_when_it_happened_and_publish_is_the_db_add_date():
    adapter = MaudeAdapter(_Taxonomy(), product_codes=["DXE"])
    record = adapter._record(MAUDE_ROW)
    assert record is not None
    assert record.event_at == "1997-03-20"
    assert record.published_at == "1997-06-25"
    assert record.extra["published_at_status"] == "database_add_date"
    assert record.extra["official_identifier"] == "6000002-1997-00486"
    assert record.url.endswith("mdrfoi__id=100001")


def test_maude_keeps_the_narrative_and_reports_what_was_missing():
    adapter = MaudeAdapter(_Taxonomy(), product_codes=["DXE"])
    record = adapter._record(MAUDE_ROW)
    assert "BALLOON AND SPRING TIP WERE MISSING" in record.text
    maude = record.extra["maude"]
    assert maude["has_model_number"] is True
    assert maude["has_baseline_510k"] is True
    assert "Additional Manufacturer Narrative" in maude["narrative_blocks_skipped"]


def test_maude_without_a_report_key_is_dropped_not_invented():
    adapter = MaudeAdapter(_Taxonomy(), product_codes=["DXE"])
    assert adapter._record({"report_number": "x"}) is None


# ------------------------------------------------------------------------ Europe PMC
def test_europepmc_publishes_a_real_public_instant_and_a_separate_index_lag():
    record = epmc_record(EPMC_ROW)
    assert record is not None
    assert record.published_at == "2026-11-13"
    assert record.source_updated_at == "2026-11-16"
    assert record.extra["published_at_status"] == "source_published_instant"
    assert record.source_updated_at != record.published_at


def test_europepmc_carries_affiliations_forward_for_entity_resolution():
    record = epmc_record(EPMC_ROW)
    assert "Acme Medical Devices Inc, San Jose, CA." in record.extra["affiliations"]
    assert record.extra["organization_hint"] == "Acme Medical Devices Inc, San Jose, CA."
    assert record.extra["open_access"]["full_text_permitted"] is False


# ------------------------------------------------------------------------- registry
def test_the_new_sources_are_registered_and_ordered_before_the_literature_lane():
    sources = available_sources()
    assert "openfda_maude" in sources
    assert "europepmc" in sources
    adapters = build_adapters(_Taxonomy())
    assert [a.source_id for a in adapters][:3] == [
        "openfda_device", "openfda_recall", "openfda_maude"
    ]


def test_an_unknown_source_id_is_an_error_never_a_silent_skip():
    with pytest.raises(KeyError):
        build_adapters(_Taxonomy(), ["not_a_source"])


# ------------------------------------------------------------------ binary http path
def test_get_bytes_returns_the_payload_and_leaves_body_empty():
    from medradar.radar.http import PoliteFetcher

    payload = _pdf(CONTENT)
    fetcher = PoliteFetcher(opener=lambda *a, **k: _Response(payload))
    result = fetcher.get_bytes("https://example.test/doc.pdf")
    assert result.payload == payload
    assert result.body == ""
    assert result.raw_bytes == len(payload)


def test_get_text_still_decodes_and_does_not_populate_payload():
    from medradar.radar.http import PoliteFetcher

    fetcher = PoliteFetcher(opener=lambda *a, **k: _Response(b'{"ok": true}'))
    result = fetcher.get_text("https://example.test/x.json")
    assert result.body == '{"ok": true}'
    assert result.payload == b""


# ------------------------------------------------------------------ reference store
def test_udi_sync_builds_the_duns_spine_and_the_clearance_links(tmp_path):
    store = UdiReference(tmp_path / "reference.db")
    fetcher = _PageFetcher(UDI_ROWS)
    result = store.sync(fetcher, page_size=1000)

    assert result.complete is True
    assert result.devices_written == 2
    assert result.submissions_written == 2
    assert result.companies_written == 2
    assert result.endpoint_version == "2026-11-02"

    coverage = store.coverage()
    assert coverage["devices"] == 2
    assert coverage["devices_with_duns"] == 2
    assert coverage["companies"] == 2
    assert coverage["distinct_submissions"] == 2
    store.close()


def test_a_maude_model_number_resolves_to_a_company_and_a_clearance(tmp_path):
    store = UdiReference(tmp_path / "reference.db")
    store.sync(_PageFetcher(UDI_ROWS), page_size=1000)

    devices = store.devices_for_model("12-080-3F")
    assert devices and devices[0]["labeler_duns"] == "117222222"
    assert store.submissions_for_model("12-080-3F") == ["K252901"]
    company = store.company_by_duns("117222222")
    assert company is not None and company["company_name"] == "TYBER MEDICAL LLC"
    store.close()


def test_a_partial_sweep_says_so_instead_of_reporting_coverage(tmp_path):
    store = UdiReference(tmp_path / "reference.db")
    fetcher = _PageFetcher(UDI_ROWS, total=5_000_000)
    result = store.sync(fetcher, page_size=1, max_pages=2)

    assert result.complete is False
    assert result.stop_reason == "page budget 2 reached"
    assert any("complete sweep needs" in note for note in result.notes)
    store.close()


# ------------------------------------------------- openFDA key-gated page-size ceiling
def test_every_openfda_caller_uses_the_measured_ceiling():
    """limit=1000 -> 403 API_KEY_MISSING (measured 2026-11-21); 999 -> 200.

    The ceiling lives in one constant so the next upstream change is one edit, not four.
    """
    from medradar.radar import reference
    from medradar.radar.adapters import maude, openfda, openfda_recall
    from medradar.radar.http import OPENFDA_MAX_LIMIT_WITHOUT_KEY

    assert OPENFDA_MAX_LIMIT_WITHOUT_KEY == 999
    assert openfda.PAGE_SIZE == 999
    assert openfda_recall.PAGE_SIZE == 999
    assert maude.PAGE_SIZE == 999
    assert reference.PAGE_SIZE == 999


def test_a_403_naming_a_capability_limit_is_not_recorded_as_a_refusal():
    """The distinction matters: one disables a public source for ever, the other does not."""
    import io
    import urllib.error

    from medradar.radar.http import CapabilityLimit, PoliteFetcher

    body = io.BytesIO(b'{"error": {"code": "API_KEY_MISSING"}}')
    error = urllib.error.HTTPError("https://api.fda.gov/x", 403, "Forbidden",
                                   {"Content-Type": "application/json"}, body)

    def opener(*args, **kwargs):
        raise error

    fetcher = PoliteFetcher(opener=opener)
    with pytest.raises(CapabilityLimit) as caught:
        fetcher.get_text("https://api.fda.gov/x")
    assert caught.value.kind == "CAPABILITY_LIMIT"
    assert fetcher.stats["capability_limits"] == 1


def test_a_persistent_403_without_a_limit_body_still_becomes_terminal():
    """A plain 403 stays terminal on the first response - the project's standing contract.

    ``tests/test_radar_core.py::test_a_refusal_is_terminal_and_never_retried`` already holds
    this for ``PoliteFetcher``; this test guards the same property from the intelligence side,
    because reading the error body must not have become a reason to retry.
    """
    import io
    import urllib.error

    from medradar.radar.http import PoliteFetcher, Refused

    def opener(*args, **kwargs):
        raise urllib.error.HTTPError("https://blocked.test/x", 403, "Forbidden",
                                     {"Content-Type": "text/html"},
                                     io.BytesIO(b"<html>Access Denied</html>"))

    fetcher = PoliteFetcher(opener=opener)
    with pytest.raises(Refused):
        fetcher.get_text("https://blocked.test/x")
    assert fetcher.stats["refusals"] == 1
    assert fetcher.stats["retries"] == 0


def test_a_403_naming_a_capability_limit_is_classified_without_any_retry():
    """Reading the body must not turn into a retry loop: the first answer is the answer."""
    import io
    import urllib.error

    from medradar.radar.http import CapabilityLimit, PoliteFetcher

    calls = {"n": 0}

    def opener(*args, **kwargs):
        calls["n"] += 1
        raise urllib.error.HTTPError(
            "https://api.fda.gov/x", 403, "Forbidden",
            {"Content-Type": "application/json"},
            io.BytesIO(b'{"error": {"code": "API_KEY_MISSING"}}'),
        )

    fetcher = PoliteFetcher(opener=opener)
    with pytest.raises(CapabilityLimit):
        fetcher.get_text("https://api.fda.gov/x")
    assert calls["n"] == 1
    assert fetcher.stats["capability_limits"] == 1
    assert fetcher.stats["retries"] == 0


# ------------------------------------------------------------ sectioning honesty
def test_form_scaffolding_is_never_reported_as_a_section():
    """K252901 repeats "Indications for Use" above the OMB paperwork notice."""
    text = (
        "Indications for Use\n"
        "Form Approved: OMB No. 0910-0120 Please type in the marketing application number. "
        "The textbox will be left blank for original applications.\n"
        "Substantial Equivalence\n"
        "The subject device is substantially equivalent to predicate K53575 for mechanical "
        "testing already conducted.\n"
    )
    sections = split_sections(text)
    assert "indications" not in sections
    assert "K53575" in sections["substantial_equivalence"]


def test_the_longest_real_body_wins_when_a_heading_repeats():
    text = (
        "Device Description\nShort.\n"
        "Device Description\n"
        "A dual-lumen aspiration catheter with a radiopaque marker band and a hydrophilic "
        "coating, supplied sterile.\n"
    )
    sections = split_sections(text)
    assert "hydrophilic" in sections["device_description"]


# -------------------------------------------------------------------------- POST path
def test_post_json_sends_the_body_and_parses_the_reply():
    from medradar.radar.http import PoliteFetcher

    seen = {}

    def opener(request, timeout=None):
        seen["method"] = request.get_method()
        seen["data"] = request.data
        seen["content_type"] = request.get_header("Content-type")
        return _Response(b'{"meta": {"total": 3}, "results": []}')

    fetcher = PoliteFetcher(opener=opener)
    payload = fetcher.post_json("https://api.reporter.nih.gov/v2/projects/search",
                                {"criteria": {"fiscal_years": [2025]}})
    assert seen["method"] == "POST"
    assert b"fiscal_years" in seen["data"]
    assert seen["content_type"] == "application/json"
    assert payload["meta"]["total"] == 3


def test_post_json_shares_the_refusal_contract_with_get():
    import io
    import urllib.error

    from medradar.radar.http import PoliteFetcher, Refused

    calls = {"n": 0}

    def opener(*args, **kwargs):
        calls["n"] += 1
        raise urllib.error.HTTPError("https://api.reporter.nih.gov/x", 403, "Forbidden",
                                     {"Content-Type": "text/html"},
                                     io.BytesIO(b"<html>no</html>"))

    fetcher = PoliteFetcher(opener=opener)
    with pytest.raises(Refused):
        fetcher.post_json("https://api.reporter.nih.gov/x", {"a": 1})
    # A POST is not a licence to retry a refusal: exactly one observation, as for GET.
    assert calls["n"] == 1


# ------------------------------------------------------------------- NIH RePORTER
NIH_ROW = {
    "fiscal_year": 2025,
    "project_num": "5R01HL170574-03",
    "project_title": "Prevention of catheter related infections",
    "organization": {"org_name": "UNIVERSITY OF GEORGIA", "primary_duns": "004315578",
                     "primary_uei": "NMJHD63STRC5"},
    "award_amount": 475865,
    "agency_ic_admin": {"name": "National Heart Lung and Blood Institute"},
    "principal_investigators": [{"full_name": "Elizabeth Joy Brisbois", "is_contact_pi": True}],
    "project_start_date": "2023-08-01T00:00:00",
    "project_end_date": "2027-04-30T00:00:00",
    "award_notice_date": "2025-05-21T00:00:00",
    "abstract_text": "Currently, clinical applications of intravascular catheters suffer...",
}


def test_nih_award_notice_date_is_the_published_instant_and_start_date_is_not():
    from medradar.radar.adapters.nih_reporter import _record

    record = _record(NIH_ROW)
    assert record is not None
    assert record.published_at == "2025-05-21"
    assert record.event_at == "2025-05-21"
    assert record.extra["published_at_status"] == "source_published_instant"
    # The funded period must never be mistaken for the publication date.
    assert record.payload["project_start_date"] != record.published_at
    assert record.record_type == "grant_award"


def test_nih_carries_the_organisation_duns_that_joins_to_the_device_register():
    from medradar.radar.adapters.nih_reporter import _record

    record = _record(NIH_ROW)
    assert record.extra["duns"] == "004315578"
    assert record.extra["organization_role"] == "grantee_organization"
    assert record.extra["organization_hint"] == "UNIVERSITY OF GEORGIA"
    assert record.extra["grant"]["principal_investigators"] == ["Elizabeth Joy Brisbois"]
    assert record.extra["grant"]["has_duns"] is True


def test_nih_falls_back_to_the_duns_list_when_primary_is_absent():
    from medradar.radar.adapters.nih_reporter import _record

    row = dict(NIH_ROW)
    row["organization"] = {"org_name": "ACME DEVICES INC", "org_duns": ["123456789"]}
    record = _record(row)
    assert record.extra["duns"] == "123456789"


def test_nih_adapter_pages_by_offset_and_stops_at_the_scope_end():
    from medradar.radar.adapters.nih_reporter import NihReporterAdapter

    calls = []

    class FakeFetcher:
        def post_json(self, url, payload, *, allow_not_found=False):
            calls.append(payload)
            offset = payload["offset"]
            rows = [dict(NIH_ROW, project_num=f"5R01HL{offset + i:06d}-01")
                    for i in range(2)]
            return {"meta": {"total": 4}, "results": rows}

    adapter = NihReporterAdapter(None, terms=[{"id": "catheter", "text": "catheter"}],
                                 fiscal_years=[2025], page_size=2)
    ctx = type("C", (), {"fetcher": FakeFetcher(), "watermark": None, "cursor": {},
                         "adapter_state": {}, "emit": print})()
    scope = adapter.plan(ctx)[0]
    assert scope.scope_id == "fy:2025:catheter"

    first = adapter.fetch_page(ctx, scope, None)
    assert first.next_cursor == "2"
    assert len(first.records) == 2
    second = adapter.fetch_page(ctx, scope, first.next_cursor)
    assert second.next_cursor is None
    assert calls[0]["criteria"]["fiscal_years"] == [2025]


# --------------------------------------------------------------------- GUDID bulk
GUDID_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<gudid xmlns="http://www.fda.gov/cdrh/gudid" version="1.0">
  <header>
    <database frequency="daily" id="1" type="DELTA_INCREMENTAL"/>
    <numberRecordXML>2</numberRecordXML>
    <numberRecordsDatabase>2</numberRecordsDatabase>
    <creationDate>2026-11-20T09:44:31</creationDate>
    <period end="2026-11-20T09:44:30" start="2026-11-17T09:08:39"/>
  </header>
  <device>
    <publicDeviceRecordKey>k1</publicDeviceRecordKey>
    <deviceRecordStatus>Published</deviceRecordStatus>
    <publicVersionDate>2026-11-20</publicVersionDate>
    <devicePublishDate>2017-01-09</devicePublishDate>
    <identifiers><identifier>
      <deviceId>00634782076825</deviceId><deviceIdType>Primary</deviceIdType>
      <deviceIdIssuingAgency>GS1</deviceIdIssuingAgency>
    </identifier></identifiers>
    <brandName>Diagnostix</brandName>
    <versionModelNumber>55102A</versionModelNumber>
    <catalogNumber>55102A</catalogNumber>
    <dunsNumber>108999095</dunsNumber>
    <companyName>AMERICAN DIAGNOSTIC CORP</companyName>
    <deviceDescription>Diagnostix Desk Set</deviceDescription>
    <singleUse>false</singleUse><deviceKit>true</deviceKit><rx>false</rx>
    <premarketExempt>false</premarketExempt>
    <MRISafetyStatus>Labeling does not contain MRI Safety Information</MRISafetyStatus>
    <gmdnTerms><gmdn>
      <gmdnCode>45084</gmdnCode><gmdnPTName>Ophthalmic/otologic diagnostic set</gmdnPTName>
      <implantable>false</implantable>
    </gmdn></gmdnTerms>
    <productCodes><productCode>ERA</productCode></productCodes>
  </device>
  <device>
    <identifiers><identifier>
      <deviceId>00812345678901</deviceId><deviceIdType>Primary</deviceIdType>
    </identifier></identifiers>
    <brandName>Tyber</brandName>
    <versionModelNumber>12-080-3F</versionModelNumber>
    <dunsNumber>117222222</dunsNumber>
    <companyName>TYBER MEDICAL LLC</companyName>
  </device>
</gudid>
"""


def _gudid_zip(tmp_path):
    import zipfile

    path = tmp_path / "gudid_daily_update_20261120.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("DELTA_INCREMENTALDownload_Part1_Of_1_2026-11-20.xml", GUDID_XML)
    return path


def test_gudid_catalogue_classifies_every_naming_scheme(tmp_path):
    from medradar.radar.gudid import discover_releases, newest

    html = """
      <a href="https://accessgudid.nlm.nih.gov/release_files/download/gudid_full_release_20261102.zip">f</a>
      <a href="https://accessgudid.nlm.nih.gov/release_files/download/gudid_full_release_20261001.zip">f</a>
      <a href="https://accessgudid.nlm.nih.gov/release_files/download/gudid_monthly_update_october_2026.zip">m</a>
      <a href="https://accessgudid.nlm.nih.gov/release_files/download/gudid_monthly_update_september_2025.zip">m</a>
      <a href="https://accessgudid.nlm.nih.gov/release_files/download/gudid_weekly_update_20261109_20261113.zip">w</a>
      <a href="https://accessgudid.nlm.nih.gov/release_files/download/gudid_daily_update_20261120.zip">d</a>
    """
    releases = discover_releases(html)
    assert len(releases) == 6
    assert newest(releases, "full").filename == "gudid_full_release_20261102.zip"
    assert newest(releases, "daily").filename == "gudid_daily_update_20261120.zip"
    # The month-name scheme is the one that used to sort wrong: a string comparison put
    # october_2026 below september_2025.
    assert newest(releases, "monthly").filename == "gudid_monthly_update_october_2026.zip"


def test_gudid_release_header_is_read_without_parsing_the_devices(tmp_path):
    from medradar.radar.gudid import release_metadata

    metadata = release_metadata(_gudid_zip(tmp_path))
    assert metadata["numberRecordsDatabase"] == "2"
    assert metadata["type"] == "DELTA_INCREMENTAL"
    assert metadata["period_end"] == "2026-11-20T09:44:30"


def test_gudid_device_maps_duns_identifier_and_model(tmp_path):
    from medradar.radar.gudid import device_to_parsed, iter_devices

    element = next(iter_devices(_gudid_zip(tmp_path), limit=1))
    parsed = device_to_parsed(element)
    assert parsed is not None
    assert parsed["device_key"] == "di:00634782076825"
    assert parsed["duns"] == "108999095"
    row = dict(zip(DEVICE_COLUMNS, parsed["row"]))
    assert row["version_or_model"] == "55102A"
    assert row["gmdn_code"] == "45084"
    assert row["is_kit"] == 1
    assert row["is_single_use"] == 0


def test_gudid_import_lands_in_the_same_tables_the_api_sync_uses(tmp_path):
    from medradar.radar.gudid import import_release

    store = UdiReference(tmp_path / "reference.db")
    result = import_release(store, _gudid_zip(tmp_path))
    assert result.devices == 2
    assert result.elements_seen == result.declared_records == 2
    assert result.companies == 2
    assert store.devices_for_model("12-080-3F")[0]["labeler_duns"] == "117222222"
    coverage = store.coverage()
    assert coverage["devices"] == 2
    assert coverage["devices_with_duns"] == 2
    # GUDID carries no premarket submissions; the 510(k) link is the openFDA sync's job and
    # the import says so rather than reporting a silent zero.
    assert any("no premarket submissions" in note for note in result.notes)
    store.close()


def test_device_rows_refuse_an_unknown_column():
    from medradar.radar.reference import build_device_row

    with pytest.raises(KeyError):
        build_device_row({"device_key": "x", "not_a_column": 1})


# ---------------------------------------------------------------- 510(k) corpus batch
def test_index_filters_to_filings_that_publish_a_summary_by_default():
    from medradar.radar.fda_corpus import collect_510k_index

    seen = {}

    class FakeFetcher:
        def get_json(self, url, *, params=None, headers=None, allow_not_found=False):
            seen["search"] = (params or {}).get("search")
            return {"meta": {"results": {"total": 1}},
                    "results": [{"k_number": "K252901", "applicant": "TYBER MEDICAL LLC",
                                 "device_name": "Trauma Screw", "product_code": "HWC",
                                 "decision_date": "2025-12-31",
                                 "statement_or_summary": "Summary"}]}

    rows = collect_510k_index(FakeFetcher())
    assert 'statement_or_summary:"Summary"' in seen["search"]
    assert rows[0]["k_number"] == "K252901"

    collect_510k_index(FakeFetcher(), only_published_summary=False)
    assert "statement_or_summary" not in (seen["search"] or "")


def _big_pdf() -> bytes:
    """A PDF that clears both guards: MIN_PDF_BYTES (2 KB) and MIN_PLAUSIBLE_CHARS (200).

    Both thresholds are real product behaviour - a 2 KB payload is usually an error page and a
    200-character body is usually a scan stub - so the fixture has to look like a document
    rather than the test relaxing the code.
    """
    lines = [
        b"Indications for Use",
        b"The device is a self-expanding catheter with a radiopaque marker band, supplied "
        b"sterile for single use in percutaneous aspiration.",
        b"Device Description",
        b"A dual-lumen aspiration catheter with a hydrophilic coating and a distal "
        b"radiopaque marker band.",
        b"Substantial Equivalence",
        b"The subject device is substantially equivalent to the predicate K123456 for the "
        b"intended use described above.",
        b"Performance Data",
        b"Burst pressure testing per ISO 10555-1 passed at 3.0 MPa; biocompatibility was "
        b"also assessed.",
    ]
    ops = [b"BT", b"/F1 12 Tf", b"72 720 Td"]
    for line in lines:
        ops.append(b"(%s) Tj" % line)
        ops.append(b"0 -14 Td")
    ops.append(b"ET")
    content = b"\n".join(ops) + b"\n"
    # Repetitive prose compresses below the 2 KB plausibility floor, so the fixture carries an
    # incompressible tail. bytes(range(256)) cannot contain the literal "stream", so it cannot
    # be mistaken for another content stream by the extractor.
    return _pdf(content) + b"\n%" + bytes(range(256)) * 12 + b"\n"


def test_batch_separates_not_published_from_failed(tmp_path):
    """The three outcomes must not collapse: one is FDA's choice, one is our fault."""
    from medradar.radar.documents import DocumentStore
    from medradar.radar.fda_corpus import build_corpus

    class Result:
        def __init__(self, status, payload=b"", raw_bytes=0, content_type=None):
            self.status = status
            self.payload = payload
            self.raw_bytes = raw_bytes or len(payload)
            self.content_type = content_type

    class FakeFetcher:
        def get_bytes(self, url, *, headers=None, allow_not_found=False):
            if "K252901" in url:
                return Result(200, _big_pdf(), content_type="application/pdf")
            if "K243627" in url:
                return Result(200, b"<html>maintenance</html>", content_type="text/html")
            return Result(404)

    store = DocumentStore(tmp_path)
    index = [{"k_number": "K252901"}, {"k_number": "K243627"}, {"k_number": "K999999"}]
    stats = build_corpus(FakeFetcher(), store, index)

    assert stats.attempted == 3
    assert stats.with_text == 1
    assert stats.failed == 1
    assert stats.not_published == 1
    assert stats.chars_total > 0
    assert stats.by_section.get("indications", 0) >= 1


def test_batch_is_resumable_and_reports_cache_hits(tmp_path):
    from medradar.radar.documents import DocumentStore
    from medradar.radar.fda_corpus import build_corpus

    class Result:
        def __init__(self, status, payload=b"", content_type=None):
            self.status = status
            self.payload = payload
            self.raw_bytes = len(payload)
            self.content_type = content_type

    calls = {"n": 0}

    class FakeFetcher:
        def get_bytes(self, url, *, headers=None, allow_not_found=False):
            calls["n"] += 1
            return Result(200, _big_pdf(), "application/pdf")

    store = DocumentStore(tmp_path)
    index = [{"k_number": "K252901"}]
    build_corpus(FakeFetcher(), store, index)
    second = build_corpus(FakeFetcher(), store, index)
    assert calls["n"] == 1          # the store answered the second time
    assert second.skipped_cached == 1


# ------------------------------------------------------------------ patent ownership
def _company_store(tmp_path):
    from medradar.radar.reference import UdiReference

    store = UdiReference(tmp_path / "reference.db")
    rows = [
        ("MEDTRONIC, INC.", "006261481", 100),
        ("MEDTRONIC VASCULAR, INC.", "080009661", 50),
        ("MEDTRONIC SOFAMOR DANEK, INC.", "830350380", 40),
        ("Covidien LP", "058614483", 30),
        ("Stryker GmbH", "481999654", 20),
        ("STRYKER CORPORATION", "021717889", 10),
        ("ACME INDUSTRIAL SUPPLY CO", "111111111", 1),
    ]
    for name, duns, count in rows:
        store.conn.execute(
            "INSERT INTO udi_company (labeler_duns, company_name, device_count, "
            "first_observed_at) VALUES (?,?,?,?)",
            (duns, name, count, "2026-11-21"),
        )
    store.conn.commit()
    return store


def test_assignee_normalisation_strips_legal_forms_but_keeps_identity():
    from medradar.radar.patents import normalise_assignee

    assert normalise_assignee("MEDTRONIC SOFAMOR DANEK, INC.") == "MEDTRONIC SOFAMOR DANEK"
    assert normalise_assignee("Smith & Nephew, Inc.") == "SMITH AND NEPHEW"
    assert normalise_assignee("THE BOEING COMPANY") == "BOEING"
    # "MEDICAL" must survive: dropping it would merge unrelated firms.
    assert "MEDICAL" in normalise_assignee("ACME MEDICAL LLC")


def test_assignee_resolves_by_exact_name(tmp_path):
    from medradar.radar.patents import AssigneeResolver

    resolver = AssigneeResolver(_company_store(tmp_path))
    hit = resolver.resolve("MEDTRONIC SOFAMOR DANEK, INC.")
    assert hit is not None
    assert hit.labeler_duns == "830350380"
    assert hit.method == "exact"
    assert hit.confidence == 1.0


def test_an_entity_mismatch_is_downgraded_not_reported_as_certain(tmp_path):
    """Measured failure: STRYKER CORPORATION matched Stryker GmbH at confidence 1.0."""
    from medradar.radar.patents import AssigneeResolver

    resolver = AssigneeResolver(_company_store(tmp_path))
    hit = resolver.resolve("STRYKER LIMITED")
    assert hit is not None
    assert hit.method.endswith("_entity_mismatch")
    assert hit.confidence <= 0.55


def test_a_name_that_is_a_different_company_is_not_guessed(tmp_path):
    from medradar.radar.patents import AssigneeResolver

    resolver = AssigneeResolver(_company_store(tmp_path))
    assert resolver.resolve("SHENZHEN RANDOM NOVELTY CO LTD") is None
    assert resolver.resolve("ACME ORTHOPEDIC RESEARCH GMBH") is None


def test_resolutions_are_written_once_with_their_method(tmp_path):
    from medradar.radar.patents import resolve_assignees

    store = _company_store(tmp_path)
    stats = resolve_assignees(store, ["MEDTRONIC INC", "COVIDIEN LP", "NOT A REAL FIRM"])
    assert stats.tried == 3
    assert stats.exact == 2
    assert stats.unresolved == 1
    assert stats.written == 2
    coverage = store.assignee_coverage()
    assert coverage["resolved_assignees"] == 2
    assert coverage["by_method"].get("exact") == 2
    store.close()


def test_patent_clients_refuse_to_invent_a_credential():
    from medradar.radar.patents import (CredentialMissing, PatentsViewClient,
                                        UsptoOdpClient, credential_status)

    class NoFetch:
        def get_json(self, *a, **k):
            raise AssertionError("must not issue a request without a credential")

    status = credential_status()
    if not status["uspto_odp"]:
        with pytest.raises(CredentialMissing) as caught:
            UsptoOdpClient(NoFetch()).search_applications("catheter")
        assert caught.value.env_var == "USPTO_ODP_API_KEY"
    if not status["patentsview"]:
        with pytest.raises(CredentialMissing):
            PatentsViewClient(NoFetch()).search({"q": 1}, fields=["patent_id"])


def test_odp_envelope_is_unwrapped_or_refused_never_silently_empty():
    from medradar.radar.patents import OdpShapeError, unwrap_count, unwrap_records

    assert unwrap_records({"results": [{"a": 1}]}) == [{"a": 1}]
    assert unwrap_records({"patentDataBag": [{"b": 2}]}) == [{"b": 2}]
    assert unwrap_records({"data": {"items": [{"c": 3}]}}) == [{"c": 3}]
    assert unwrap_records([{"d": 4}]) == [{"d": 4}]
    assert unwrap_count({"count": 12}) == 12
    assert unwrap_count({"totalNumFound": "7"}) == 7

    # An unknown envelope must fail loudly with the keys it actually saw - "no matches" and
    # "we did not understand the reply" must never look the same.
    with pytest.raises(OdpShapeError) as caught:
        unwrap_records({"somethingNew": []})
    assert "somethingNew" in str(caught.value)


def test_the_assignment_endpoint_is_reported_as_absent_not_as_an_empty_result():
    """Measured: ODP answers 403 'Missing Authentication Token' on every assignment path."""
    from medradar.radar.patents import OdpShapeError, UsptoAssignmentClient

    assert UsptoAssignmentClient.LIVE_ON_ODP is False
    with pytest.raises(OdpShapeError) as caught:
        UsptoAssignmentClient(None).lookup("medtronic")
    assert "no assignment endpoint" in str(caught.value)


def test_a_401_becomes_a_credential_error_and_a_gateway_403_becomes_route_absent():
    import io
    import urllib.error

    from medradar.radar.http import (CredentialRejected, CredentialRequired, PoliteFetcher,
                                     RouteAbsent)

    def raise_http(status, body, url="https://api.uspto.gov/api/v1/x"):
        raise urllib.error.HTTPError(url, status, "Forbidden",
                                     {"Content-Type": "application/json"}, io.BytesIO(body))

    # no credential -> the route exists and wants one
    with pytest.raises(CredentialRequired):
        PoliteFetcher(opener=lambda *a, **k: raise_http(
            401, b'{"message":"Unauthorized"}')).get_text("https://api.uspto.gov/api/v1/x")

    # credential present but wrong -> rejected, which is a configuration fix
    with pytest.raises(CredentialRejected):
        PoliteFetcher(opener=lambda *a, **k: raise_http(
            403, b'{"message":"Forbidden"}')).get_text("https://api.uspto.gov/api/v1/x")

    # no such route -> API Gateway's misleading wording, not a refusal
    with pytest.raises(RouteAbsent):
        PoliteFetcher(opener=lambda *a, **k: raise_http(
            403, b'{"message":"Missing Authentication Token"}'
        )).get_text("https://api.uspto.gov/api/v1/y")


def test_an_html_403_is_still_a_plain_refusal():
    """The rejected-credential test must stay narrow: a web page saying Forbidden is not a key."""
    import io
    import urllib.error

    from medradar.radar.http import PoliteFetcher, Refused

    def opener(*args, **kwargs):
        raise urllib.error.HTTPError("https://example.test/x", 403, "Forbidden",
                                     {"Content-Type": "text/html"},
                                     io.BytesIO(b"<html><h1>403 Forbidden</h1></html>"))

    with pytest.raises(Refused):
        PoliteFetcher(opener=opener).get_text("https://example.test/x")


def test_a_credential_can_come_from_a_file_when_the_shell_cannot_see_the_variable(
        tmp_path, monkeypatch):
    """Measured Windows trap: a user env var written now is invisible to running shells."""
    from medradar.radar.patents import ENV_USPTO_ODP, _credential, credential_status

    monkeypatch.delenv(ENV_USPTO_ODP, raising=False)
    monkeypatch.setenv("MEDRADAR_SECRETS_DIR", str(tmp_path))
    (tmp_path / f"{ENV_USPTO_ODP}.key").write_text("FILEKEY123\n", encoding="utf-8")

    assert _credential(ENV_USPTO_ODP) == "FILEKEY123"
    status = credential_status()
    assert status["uspto_odp"] is True
    assert status["found_in"][ENV_USPTO_ODP].startswith("file:")


# ------------------------------------------------------- 510(k) -> device bridge
def _udi_row(k_number, model, duns="557821945", company="ARUM DENTISTRY Co., Ltd."):
    # The device identifier must differ per device: two rows sharing a DI collapse into one
    # device record, which is correct behaviour and would silently halve a test fixture.
    return {
        "identifiers": [{"id": f"08800{k_number[-4:]}{abs(hash(model)) % 100:02d}",
                         "type": "Primary", "issuing_agency": "GS1"}],
        "brand_name": "Galaxy Star",
        "company_name": company,
        "labeler_duns_number": duns,
        "version_or_model_number": model,
        "device_description": "Dental restorative printer",
        "product_codes": [{"code": "EIA"}],
        "premarket_submissions": [{"submission_number": k_number, "supplement_number": "000"}],
    }


def test_the_index_is_partitioned_because_deep_paging_is_capped_at_25000():
    """Measured: skip 25,000 -> 200, skip 25,001 -> 400 'Skip value must 25000 or less.'

    So a 60,000-record range cannot be walked with one skip loop. It has to be split by a
    search field; this locks the splitting rather than the failure.
    """
    import re

    from medradar.radar.fda_corpus import WINDOW_CAPACITY, _windows

    assert WINDOW_CAPACITY == 25_999

    class FakeFetcher:
        def __init__(self, totals):
            self.totals = totals
            self.seen = []

        def get_json(self, url, *, params=None, headers=None, allow_not_found=False):
            search = (params or {}).get("search") or ""
            window = re.search(r"decision_date:\[(\S+) TO (\S+)\]", search)
            key = window.group(0) if window else "?"
            self.seen.append(key)
            return {"meta": {"results": {"total": self.totals.get(key, 0)}}}

    # whole range too big, every year fits -> one window per year
    totals = {"decision_date:[2000-01-01 TO 2001-12-31]": 60_000,
              "decision_date:[2000-01-01 TO 2000-12-31]": 3_000,
              "decision_date:[2001-01-01 TO 2001-12-31]": 2_500}
    fetcher = FakeFetcher(totals)
    windows = list(_windows(fetcher, [], "2000-01-01", "2001-12-31"))
    assert windows == [("2000-01-01", "2000-12-31"), ("2001-01-01", "2001-12-31")]

    # a year that still overflows -> its twelve months
    totals = {"decision_date:[2000-01-01 TO 2000-12-31]": 40_000,
              "decision_date:[2000-01-01 TO 2000-01-31]": 4_000}
    windows = list(_windows(FakeFetcher(totals), [], "2000-01-01", "2000-12-31"))
    assert windows[0] == ("2000-01-01", "2000-01-31")
    assert len(windows) == 12

    # a month that still overflows is refused, never silently truncated
    totals = {"decision_date:[2000-01-01 TO 2000-12-31]": 40_000,
              "decision_date:[2000-01-01 TO 2000-01-31]": 30_000}
    with pytest.raises(ValueError) as caught:
        list(_windows(FakeFetcher(totals), [], "2000-01-01", "2000-12-31"))
    assert "narrow the query" in str(caught.value)


def test_the_pre_2013_lettered_format_still_sections():
    """Measured on K100017 (a 2010 scan): before these patterns the whole document collapsed
    into one unnamed block and every section was lost.

    Filings up to roughly 2012 follow 21 CFR 807.92 as a lettered list - "A. 510(k) Number",
    "B. Purpose for Submission", "C. Measurand", "D. Type of Test" - rather than the modern
    "Indications for Use" headings. Both formats have to work, because the corpus spans both.
    """
    from medradar.radar.documents import split_sections

    text = (
        "PREMARKET NOTIFICATION\n510(K)\nSAFETY AND EFFECTIVENESS SUMMARY\n\n"
        "A. 510(k)Number: K100017\n"
        "B. Purpose for Submission: New device\n"
        "C. Measurand: Autoantibodies against glutamate receptor (type NMDA)\n"
        "D. Type of Test: Semiquantitative indirect immunofluorescence assay\n"
        "E. Applicant: EUROIMMUN US INC\n"
        "F. Proprietary and Established Names: NMDA Receptor IgG\n"
        "G. Regulatory Information: Class II, 21 CFR 866.5660\n"
        "H. Device Description: A slide with recombinant NMDA receptor antigen spots.\n"
        "I. Intended Use: For the semiquantitative detection of IgG antibodies to "
        "NMDA receptors in human serum.\n"
        "J. Comparison to Predicate: The subject device uses the same antigen source and "
        "the same interpretation criteria as the predicate, with an added calibrator.\n"
        "K. Performance Data: Precision was assessed across three sites; concordance with "
        "the predicate was 96.4 percent on 210 clinical samples.\n"
        "L. Conclusion: Substantially equivalent to the predicate device.\n"
    )
    sections = split_sections(text)
    for key in ("submission_identity", "measurand", "test_type", "applicant_identity",
                "device_names", "regulatory_info", "intended_use", "conclusion"):
        assert key in sections, f"{key} missing; got {sorted(sections)}"
    # The value sits on the heading line in this format, so the inline tail must be kept.
    assert "New device" in sections["submission_identity"] or \
        "K100017" in sections["submission_identity"]
    assert "96.4" in sections["performance_data"]


def test_a_binary_stream_is_not_treated_as_a_content_stream():
    """Measured: a scanned 510(k)'s JPEG streams were fed to the operator regex and pinned a core
    for fifteen minutes on one document (py-spy: extract_text -> _text_from_content_stream).

    A text stream always opens a text object and always shows something; an image never does.
    """
    from medradar.radar.pdf import (_looks_like_content_stream, extract_text,
                                    MAX_STREAM_BYTES)

    assert _looks_like_content_stream(b"BT /F1 12 Tf (hello) Tj ET") is True
    assert _looks_like_content_stream(b"BT [(ke) -2 (rn)] TJ ET") is True
    # A JPEG body: binary, no text object, no show operator.
    assert _looks_like_content_stream(bytes(range(256)) * 4000) is False
    assert _looks_like_content_stream(b"BT only a text object, nothing shown") is False
    assert _looks_like_content_stream(b"") is False

    # A PDF whose only stream is 5 MB of binary must be rejected quickly, not scanned.
    binary = (bytes(range(256)) * 20_000)[:5_000_000]
    document = (b"%PDF-1.4\n4 0 obj\n<< /Length " + str(len(binary)).encode()
                + b" /Filter /DCTDecode >>\nstream\n" + binary
                + b"\nendstream\nendobj\n%%EOF\n")
    result = extract_text(document)
    assert result.has_text_layer is False
    assert result.reason in ("no_content_stream", "no_text_operators")
    assert MAX_STREAM_BYTES == 2_000_000


def test_the_operator_regex_is_linear_on_adversarial_input():
    """The old alternation ``(?:\\\\.|[^\\\\]\\\\])*`` backtracked catastrophically.

    Measured cost of the old form on a scanned 510(k): a single document pinned one core for
    fifteen minutes. The linear idiom ``[^X]*(?:\\\\.[^X]*)*`` is the standard fix and this test
    keeps it linear by feeding a stream made entirely of escape characters.
    """
    import time

    from medradar.radar.pdf import extract_text

    evil = b"BT [" + (b"\\\\" * 20_000) + b" (x) Tj ET"
    document = (b"%PDF-1.4\n4 0 obj\n<< /Length " + str(len(evil)).encode()
                + b" >>\nstream\n" + evil + b"\nendstream\nendobj\n%%EOF\n")
    started = time.perf_counter()
    result = extract_text(document)
    elapsed = time.perf_counter() - started
    assert elapsed < 2.0, f"regex took {elapsed:.2f}s on adversarial input"
    assert result.has_text_layer in (True, False)   # must not raise


def test_a_flate_stream_that_inflates_to_binary_is_skipped():
    import zlib

    from medradar.radar.pdf import extract_text

    blob = zlib.compress(bytes(range(256)) * 3000)
    document = (b"%PDF-1.4\n4 0 obj\n<< /Length " + str(len(blob)).encode()
                + b" /Filter /FlateDecode >>\nstream\n" + blob
                + b"\nendstream\nendobj\n%%EOF\n")
    result = extract_text(document)
    assert result.reason == "no_content_stream"


def test_an_uncompressed_text_stream_is_still_read():
    """The marker check must not throw away generators that skip Flate."""
    from medradar.radar.pdf import extract_text

    body = (b"BT\n/F1 12 Tf\n72 720 Td\n"
            b"(Indications for Use) Tj\n0 -14 Td\n"
            b"(A dual-lumen aspiration catheter with a hydrophilic coating and a distal "
            b"radiopaque marker band, supplied sterile for single use.) Tj\nET")
    document = (b"%PDF-1.4\n4 0 obj\n<< /Length " + str(len(body)).encode()
                + b" >>\nstream\n" + body + b"\nendstream\nendobj\n%%EOF\n")
    result = extract_text(document, min_chars=20)
    assert result.has_text_layer is True
    assert "hydrophilic" in result.text


def test_reopening_a_current_store_does_not_write():
    """Measured: the pipeline re-opened this store on every restart and each open ran the schema
    script plus PRAGMA user_version as a write transaction; against a 1.6 GB store with a
    concurrent reader that failed 'database is locked' 62 times in a row.
    """
    import sqlite3
    import time as _time

    from medradar.radar.reference import SCHEMA_VERSION, UdiReference

    path = _time.time_ns()
    import tempfile
    with tempfile.TemporaryDirectory() as folder:
        db = f"{folder}/reference.db"
        first = UdiReference(db)
        _ = first.conn                      # creates schema, writes version
        first.close()

        # Hold a write lock on the file from a second connection; a reopening must still work
        # because it no longer needs to write anything.
        blocker = sqlite3.connect(db, timeout=5)
        blocker.execute("BEGIN IMMEDIATE")
        try:
            second = UdiReference(db)
            assert second.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
            second.close()
        finally:
            blocker.rollback()
            blocker.close()
    assert path  # keep the import used


def test_product_code_census_is_one_query(tmp_path):
    """40,731 round-trips was the failure surface; the census is a single JOIN."""
    from medradar.radar.code_census import pending_codes, product_code_census

    store = UdiReference(tmp_path / "reference.db")
    rows = [_udi_row("K250063", f"M{i}") for i in range(3)]
    store.write_udi_rows(rows)

    census = product_code_census(store)
    assert census.get("EIA") == 3

    census_all, pending = pending_codes(store)
    assert "EIA" in pending             # nothing swept yet

    from medradar.radar.failure_index import ensure_schema
    ensure_schema(store)                # the index table is owned by failure_index
    store.conn.execute(
        "INSERT INTO maude_failure_index VALUES ('EIA','M','B','Injury','2024-01-01')")
    store.conn.commit()
    _census, pending_after = pending_codes(store)
    assert "EIA" not in pending_after   # present in the index, so never re-swept
    store.close()


# ------------------------------------------------- one device, its whole public life
def _view_store(tmp_path):
    from medradar.radar.failure_index import ensure_schema
    from medradar.radar.reference import UdiReference

    store = UdiReference(tmp_path / "reference.db")
    store.write_udi_rows([
        _udi_row("K250063", "GalaxyStar-1", company="ARUM DENTISTRY Co., Ltd."),
        _udi_row("K250063", "GalaxyStar-2", company="ARUM DENTISTRY Co., Ltd."),
    ])
    ensure_schema(store)
    store.conn.execute("INSERT INTO maude_failure_index VALUES "
                       "('EIA','GALAXYSTAR1','ARUM DENTISTRY CO LTD','Malfunction','2024-05-01')")
    store.conn.execute("INSERT INTO maude_failure_index VALUES "
                       "('EIA','OTHER','ARUM DENTISTRY CO LTD','Injury','2024-05-02')")
    store.conn.commit()
    return store


def _corpus(tmp_path, k_number="K250063", **overrides):
    root = tmp_path / "corpus"
    root.mkdir(exist_ok=True)
    payload = {"identifier": k_number, "status": "text", "text_source": "text",
               "text_chars": 900,
               "sections": {"indications": "For percutaneous aspiration of the coronary tree.",
                            "conclusion": "Substantially equivalent."}}
    payload.update(overrides)
    (root / f"510k_summary_{k_number}.json").write_text(
        json.dumps(payload), encoding="utf-8")
    return root


def test_a_device_resolves_by_model_and_shows_clearance_document_and_failures(tmp_path):
    from medradar.radar.device_view import build

    store = _view_store(tmp_path)
    corpus = _corpus(tmp_path)
    timeline = build(store, "GalaxyStar-1", corpus_root=corpus)

    assert len(timeline.refs) == 1
    assert timeline.refs[0].matched_by == "version_or_model"
    assert timeline.refs[0].labeler_duns == "557821945"
    assert "K250063" in timeline.clearances
    sections = timeline.clearances["K250063"].sections
    assert "percutaneous aspiration" in sections["indications"]

    history = timeline.failures[timeline.refs[0].device_key]
    assert history.method == "model_exact"      # the model matched, so brand is not used
    assert history.events == 1
    assert history.by_type == {"Malfunction": 1}
    store.close()


def test_a_k_number_resolves_to_every_device_on_that_clearance(tmp_path):
    from medradar.radar.device_view import build

    store = _view_store(tmp_path)
    timeline = build(store, "K250063", corpus_root=_corpus(tmp_path))
    assert len(timeline.refs) == 2
    assert all(ref.matched_by == "submission_number" for ref in timeline.refs)
    store.close()


def test_a_missing_document_is_reported_with_its_reason_not_as_empty(tmp_path):
    from medradar.radar.device_view import (GAP_DOCUMENT_NOT_PUBLISHED, build,
                                            summarise_document)

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    # FDA published nothing for this filing.
    (corpus / "510k_summary_K111111.json").write_text(
        json.dumps({"identifier": "K111111", "status": "not_published"}), encoding="utf-8")
    (corpus / "510k_summary_K222222.json").write_text(
        json.dumps({"identifier": "K222222", "status": "no_text_layer"}), encoding="utf-8")

    assert summarise_document(corpus, "K111111").gap == GAP_DOCUMENT_NOT_PUBLISHED
    assert summarise_document(corpus, "K222222").gap == "document_present_but_unreadable"
    # Not in the corpus at all.
    assert summarise_document(corpus, "K999999").gap == GAP_DOCUMENT_NOT_PUBLISHED
    # No corpus configured at all: still a named reason, never a silent empty.
    assert summarise_document(None, "K111111").gap == GAP_DOCUMENT_NOT_PUBLISHED
    store = _view_store(tmp_path)
    timeline = build(store, "K250063", corpus_root=tmp_path / "empty")
    assert "no_readable_summary_for_any_clearance" in timeline.gaps
    store.close()


def test_a_document_with_text_but_no_sections_says_so(tmp_path):
    from medradar.radar.device_view import GAP_SECTION_ABSENT, summarise_document

    corpus = _corpus(tmp_path, sections={})
    summary = summarise_document(corpus, "K250063")
    assert summary.sections == {}
    assert summary.gap == GAP_SECTION_ABSENT
    assert summary.text_chars == 900        # the text exists, the splitter found no headings


def test_an_unmatched_device_is_named_not_silently_absent(tmp_path):
    from medradar.radar.device_view import GAP_NOT_IN_INDEX, build

    store = _view_store(tmp_path)
    timeline = build(store, "NOT-A-REAL-MODEL-XYZ", corpus_root=None)
    assert timeline.refs == []
    assert timeline.gaps == [GAP_NOT_IN_INDEX]
    store.close()


def test_ocr_text_is_labelled_as_ocr_in_the_rendered_view(tmp_path):
    from medradar.radar.device_view import build, render

    store = _view_store(tmp_path)
    corpus = _corpus(tmp_path, text_source="ocr")
    text = render(build(store, "K250063", corpus_root=corpus))
    assert "OCR 文本" in text
    # Measured on K100175: OCR turns "Grade I" into "Grade |" and "S1" into "$1", so a reader
    # must be told the text is not the publisher's own bytes.
    assert "字符级错误" in text
    store.close()


def test_the_patent_gap_names_the_absent_source(tmp_path):
    """It used to be a blanket "needs a credential"; the honest statement is which source is
    missing, because a deployment may have imported the bulk tables and need nothing."""
    from medradar.radar.device_view import GAP_NO_PATENT_SOURCE, build

    store = _view_store(tmp_path)
    timeline = build(store, "K250063", corpus_root=_corpus(tmp_path))
    assert GAP_NO_PATENT_SOURCE in timeline.gaps
    payload = timeline.to_dict()
    assert payload["devices"] and payload["query"] == "K250063"
    assert payload["patents"]                      # the section exists, with its gap named
    store.close()


def _device_client(tmp_path, monkeypatch, *, with_reference: bool = True):
    """A TestClient over the real router, pointed at a temporary store."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from medradar.radar.api import build_router

    store = _view_store(tmp_path)
    reference = tmp_path / "reference.db"
    store.close()                       # the route opens its own connection
    monkeypatch.setenv("MEDRADAR_REFERENCE_DB",
                       str(reference) if with_reference else str(tmp_path / "absent.db"))
    monkeypatch.setenv("MEDRADAR_CORPUS_DIR", str(_corpus(tmp_path)))
    app = FastAPI()
    app.include_router(build_router())
    return TestClient(app)


def test_the_device_endpoint_returns_the_whole_timeline(tmp_path, monkeypatch):
    client = _device_client(tmp_path, monkeypatch)
    response = client.get("/api/radar/device", params={"query": "GalaxyStar-1"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema"] == "medradar.radar.device.v1"
    assert len(payload["devices"]) == 1
    assert payload["devices"][0]["labeler_duns"] == "557821945"
    assert "K250063" in payload["clearances"]
    assert payload["clearances"]["K250063"]["sections"]["indications"]
    (key, history), = payload["failures"].items()
    assert history["method"] == "model_exact" and history["events"] == 1
    # No bulk patent import on this fixture, and the response says which source is missing
    # rather than claiming the device has no patents.
    assert "patent_bulk_tables_absent" in payload["gaps"]
    assert payload["patents"] and payload["patents"][key]["available"] is False
    assert "批文与文件" in payload["render"]


def test_the_device_endpoint_reports_a_missing_register_as_503_not_as_empty(
        tmp_path, monkeypatch):
    """An absent store and an empty result are different facts."""
    client = _device_client(tmp_path, monkeypatch, with_reference=False)
    response = client.get("/api/radar/device", params={"query": "GalaxyStar-1"})
    assert response.status_code == 503
    assert "absent store" in response.json()["detail"]


def test_an_unknown_query_is_a_named_gap_not_an_error(tmp_path, monkeypatch):
    client = _device_client(tmp_path, monkeypatch)
    response = client.get("/api/radar/device", params={"query": "NO-SUCH-DEVICE-123"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["devices"] == []
    assert payload["gaps"] == ["device_not_in_udi_register"]


def test_the_device_page_is_reachable_without_the_react_bundle(tmp_path, monkeypatch):
    client = _device_client(tmp_path, monkeypatch)
    blank = client.get("/api/radar/device/view")
    assert blank.status_code == 200
    assert "<form" in blank.text and "name=\"query\"" in blank.text

    filled = client.get("/api/radar/device/view", params={"query": "GalaxyStar-1"})
    assert filled.status_code == 200
    # The rendered answer is HTML-escaped, never injected raw.
    assert "percutaneous aspiration" in filled.text
    assert "<script" not in filled.text.lower()


# ------------------------------------------------------- bulk patent tables (no key)
def _bulk_file(tmp_path, name, header, rows):
    path = tmp_path / name
    lines = ["\t".join(header)] + ["\t".join(str(cell) for cell in row) for row in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_bulk_patents_import_and_query(tmp_path):
    """The bulk lane needs no credential; api.uspto.gov rejects even a signed-in OAuth token."""
    from medradar.radar.patents_bulk import (bulk_summary, import_tables,
                                             organisation_patents)

    store = UdiReference(tmp_path / "reference.db")
    patents = _bulk_file(tmp_path, "g_patent.tsv",
                         ["id", "type", "number", "date", "title"],
                         [["patent/1", "utility", "10000001", "2020-03-01", "Spinal implant A"],
                          ["patent/2", "utility", "10000002", "2021-07-15", "Spinal implant B"]])
    assignees = _bulk_file(tmp_path, "g_assignee_disambiguated.tsv",
                           ["patent_id", "assignee_sequence", "assignee_id",
                            "disambig_assignee_organization"],
                           [["patent/1", 0, "org1", "Medtronic Sofamor Danek, Inc."],
                            ["patent/2", 0, "org1", "Medtronic Sofamor Danek, Inc."],
                            ["patent/2", 1, "org2", "Zimmer Biomet"]])
    result = import_tables(store, patents, assignees)
    assert result["patents"]["rows_written"] == 2
    assert result["assignees"]["rows_written"] == 3

    summary = bulk_summary(store)
    assert summary["patents"] == 2
    assert summary["organisations"] == 2

    found = organisation_patents(store, "Medtronic Sofamor Danek")
    assert found["patents"] == 2
    assert found["recent"][0]["patent_date"] == "2021-07-15"   # newest first
    store.close()


def test_a_missing_column_names_itself_instead_of_guessing(tmp_path):
    """Attaching the wrong assignee to the wrong patent is worse than failing."""
    from medradar.radar.patents_bulk import BulkSchemaError, import_tables

    store = UdiReference(tmp_path / "reference.db")
    broken = _bulk_file(tmp_path, "g_assignee_disambiguated.tsv",
                        ["patent_id", "assignee_sequence"],  # no assignee_id
                        [["patent/1", 0]])
    with pytest.raises(BulkSchemaError) as caught:
        import_tables(store, None, broken)
    assert "assignee_id" in caught.value.missing
    assert "patent_id" in caught.value.headers
    store.close()


def test_a_zipped_tsv_is_read_without_unpacking_by_hand(tmp_path):
    import zipfile

    from medradar.radar.patents_bulk import import_tables

    store = UdiReference(tmp_path / "reference.db")
    inner = _bulk_file(tmp_path, "g_patent.tsv", ["patent_id", "patent_title", "patent_date"],
                       [["patent/9", "Textured grip", "2019-01-02"]])
    archive = tmp_path / "g_patent.tsv.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.write(inner, arcname="g_patent.tsv")
    import_tables(store, archive, None)
    row = store.conn.execute(
        "SELECT title FROM bulk_patent WHERE patent_id='patent/9'").fetchone()
    assert row[0] == "Textured grip"
    store.close()


def test_patents_appear_when_the_bulk_tables_are_imported(tmp_path):
    """The patent gap is reported from the data: imported tables mean real answers."""
    from medradar.radar.device_view import build, render
    from medradar.radar.patents_bulk import import_tables

    store = _view_store(tmp_path)
    patents = _bulk_file(tmp_path, "g_patent.tsv",
                         ["patent_id", "patent_title", "patent_date"],
                         [["patent/7", "Catheter with textured grip", "2022-04-01"]])
    assignees = _bulk_file(tmp_path, "g_assignee_disambiguated.tsv",
                           ["patent_id", "assignee_id", "disambig_assignee_organization"],
                           [["patent/7", "org9", "ARUM DENTISTRY Co., Ltd."]])
    import_tables(store, patents, assignees)

    timeline = build(store, "K250063", corpus_root=_corpus(tmp_path))
    history = timeline.patents[timeline.refs[0].device_key]
    assert history.available is True
    assert history.patents == 1
    assert "textured grip" in history.recent[0]["title"]
    # Normalisation must agree with the assignee resolver: "Co., Ltd." is a legal form.
    assert history.method == "disambiguated_assignee"

    text = render(timeline)
    assert "专利" in text and "ARUM DENTISTRY" in text
    assert "patent_bulk_tables_absent" not in timeline.gaps
    store.close()


def test_without_bulk_tables_the_patent_gap_names_the_absent_source(tmp_path):
    from medradar.radar.device_view import GAP_NO_PATENT_SOURCE, build

    store = _view_store(tmp_path)
    timeline = build(store, "K250063", corpus_root=_corpus(tmp_path))
    history = timeline.patents[timeline.refs[0].device_key]
    assert history.available is False
    assert history.gap == GAP_NO_PATENT_SOURCE
    assert GAP_NO_PATENT_SOURCE in timeline.gaps
    # An absent table is not the same claim as a missing credential.
    assert "patent_source_needs_credential" not in timeline.gaps
    store.close()


def test_patents_present_but_unmatched_says_so_rather_than_zero(tmp_path):
    from medradar.radar.device_view import GAP_NO_PATENT_MATCH, build
    from medradar.radar.patents_bulk import import_tables

    store = _view_store(tmp_path)
    patents = _bulk_file(tmp_path, "g_patent.tsv", ["patent_id", "patent_title", "patent_date"],
                         [["patent/1", "Unrelated", "2020-01-01"]])
    assignees = _bulk_file(tmp_path, "g_assignee_disambiguated.tsv",
                           ["patent_id", "assignee_id", "disambig_assignee_organization"],
                           [["patent/1", "org1", "Somebody Else Inc"]])
    import_tables(store, patents, assignees)

    timeline = build(store, "K250063", corpus_root=_corpus(tmp_path))
    history = timeline.patents[timeline.refs[0].device_key]
    assert history.available is True and history.patents == 0
    assert history.gap == GAP_NO_PATENT_MATCH
    assert GAP_NO_PATENT_MATCH in timeline.gaps
    store.close()


# --------------------------------------------------- clinical trials (keyless R&D signal)
def _trial_record(nct="NCT00000001", sponsor="Medtronic - MITG", start="2023-05-01",
                  phases=("NA",), interventions=("SILS port",)):
    return {"protocolSection": {
        "identificationModule": {"nctId": nct, "briefTitle": "A device study"},
        "statusModule": {"overallStatus": "RECRUITING",
                         "startDateStruct": {"date": start},
                         "completionDateStruct": {"date": "2030-01-31"}},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": sponsor}},
        "designModule": {"phases": list(phases), "studyType": "INTERVENTIONAL",
                         "enrollmentInfo": {"count": 144}},
        "armsInterventionsModule": {
            "interventions": [{"name": name} for name in interventions]},
        "contactsLocationsModule": {"locations": [{"country": "United States"},
                                                  {"country": "United States"}]},
    }}


class _TrialFetcher:
    def __init__(self, pages, *, fail_on=None):
        self.pages = pages
        self.fail_on = fail_on
        self.calls = []

    def get_json(self, url, *, params=None, headers=None, allow_not_found=False):
        self.calls.append(dict(params or {}))
        if self.fail_on and self.fail_on in str(params.get("query.spons", "")):
            raise RuntimeError("upstream exploded")
        index = 1 if params.get("pageToken") else 0
        return self.pages[min(index, len(self.pages) - 1)]


def test_trials_are_stored_against_the_query_that_found_them(tmp_path):
    """The join key is the sponsor query, because registry sponsors are subsidiaries."""
    from medradar.radar.trials import import_trials, trials_for_sponsor, trials_summary

    store = UdiReference(tmp_path / "reference.db")
    fetcher = _TrialFetcher([
        {"totalCount": 2, "nextPageToken": "tok",
         "studies": [_trial_record("NCT1"), _trial_record("NCT2", start="2024-02-02")]},
        {"studies": [_trial_record("NCT3", start="2021-01-01")]},
    ])
    stats = import_trials(store, ["Medtronic - MITG"], fetcher=fetcher, max_pages=3)
    assert stats.rows_written == 3
    assert stats.requests == 2              # paged once, then the token ran out
    assert stats.total_reported == 2

    found = trials_for_sponsor(store, "Medtronic - MITG")
    assert found["trials"] == 3
    assert found["recent"][0]["nct_id"] == "NCT2"        # newest start first
    assert found["recent"][0]["enrollment"] == 144
    assert "SILS port" in found["recent"][0]["interventions"]

    summary = trials_summary(store)
    assert summary["trials"] == 3 and summary["sponsors"] == 1
    store.close()


def test_a_different_sponsor_string_does_not_pick_up_the_trials(tmp_path):
    """Fuzzy matching across subsidiary names is what produces confident nonsense."""
    from medradar.radar.trials import import_trials, trials_for_sponsor

    store = UdiReference(tmp_path / "reference.db")
    import_trials(store, ["Medtronic - MITG"],
                  fetcher=_TrialFetcher([{"studies": [_trial_record()]}]), max_pages=1)
    assert trials_for_sponsor(store, "Medtronic - MITG")["trials"] == 1
    assert trials_for_sponsor(store, "Stryker")["trials"] == 0
    store.close()


def test_one_failing_sponsor_does_not_stop_the_batch(tmp_path):
    from medradar.radar.trials import import_trials

    store = UdiReference(tmp_path / "reference.db")
    fetcher = _TrialFetcher([{"studies": [_trial_record()]}], fail_on="Broken")
    stats = import_trials(store, ["Broken Inc", "Medtronic - MITG"], fetcher=fetcher,
                          max_pages=1)
    assert "Broken Inc" in stats.errors
    assert stats.rows_written == 1          # the good sponsor still landed
    store.close()


def test_device_view_gains_a_trials_section(tmp_path):
    from medradar.radar.device_view import build, render
    from medradar.radar.trials import import_trials

    store = _view_store(tmp_path)
    import_trials(store, ["ARUM DENTISTRY Co., Ltd."],
                  fetcher=_TrialFetcher([{"studies": [
                      _trial_record("NCT9", sponsor="ARUM DENTISTRY Co., Ltd.",
                                    interventions=("GalaxyStar implant",))]}]), max_pages=1)

    timeline = build(store, "K250063", corpus_root=_corpus(tmp_path))
    history = timeline.trials[timeline.refs[0].device_key]
    assert history.available is True and history.trials == 1
    assert history.recent[0]["nct_id"] == "NCT9"

    text = render(timeline)
    assert "临床试验" in text and "NCT9" in text and "GalaxyStar implant" in text
    assert "trials_table_absent" not in timeline.gaps
    store.close()


def test_without_the_trials_table_the_gap_names_the_missing_source(tmp_path):
    from medradar.radar.device_view import GAP_NO_TRIAL_SOURCE, build

    store = _view_store(tmp_path)
    timeline = build(store, "K250063", corpus_root=_corpus(tmp_path))
    assert timeline.trials[timeline.refs[0].device_key].gap == GAP_NO_TRIAL_SOURCE
    assert GAP_NO_TRIAL_SOURCE in timeline.gaps
    store.close()


def test_an_empty_table_is_not_mistaken_for_a_real_import(tmp_path):
    """Measured: a `--summary` call created empty tables and the device view then claimed the
    company holds no patents. "Never imported" and "imported, no match" must not look alike."""
    from medradar.radar.device_view import GAP_NO_PATENT_SOURCE, GAP_NO_TRIAL_SOURCE, build
    from medradar.radar.patents_bulk import bulk_summary
    from medradar.radar.trials import trials_summary

    store = _view_store(tmp_path)
    bulk_summary(store)          # creates the tables, writes nothing
    trials_summary(store)

    timeline = build(store, "K250063", corpus_root=_corpus(tmp_path))
    ref_key = timeline.refs[0].device_key
    assert timeline.patents[ref_key].gap == GAP_NO_PATENT_SOURCE
    assert timeline.trials[ref_key].gap == GAP_NO_TRIAL_SOURCE
    assert GAP_NO_PATENT_SOURCE in timeline.gaps
    assert GAP_NO_TRIAL_SOURCE in timeline.gaps
    store.close()


# --------------------------------------------------- preprint + OpenAlex adapters
class _ParamFetcher:
    """Records the params of each call and replays canned payloads in order."""

    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def get_json(self, url, *, params=None, headers=None, allow_not_found=False):
        self.calls.append({"url": url, "params": dict(params or {})})
        if not self.payloads:
            return {}
        return self.payloads.pop(0)


def _ctx(fetcher, *, watermark=None):
    from medradar.radar.adapter import CollectContext

    return CollectContext(fetcher=fetcher, ledger=None, adapter_version="test",
                          log=lambda _m: None, watermark=watermark)


def _taxonomy():
    from medradar.radar.taxonomy import load_taxonomy

    return load_taxonomy(str(CONFIG_DIR))


def test_preprints_plan_is_one_scope_per_server_not_per_category():
    """Ten categories over one window would be ten identical downloads."""
    from medradar.radar.adapters.preprints import PreprintAdapter

    adapter = PreprintAdapter(_taxonomy())
    scopes = adapter.plan(_ctx(_ParamFetcher([])))
    assert [scope.scope_id for scope in scopes] == ["server:medrxiv", "server:biorxiv"]


def test_a_preprint_keeps_the_posted_date_and_never_invents_a_journal_date():
    from medradar.radar.adapters.preprints import _record

    record = _record({
        "doi": "10.1101/2026.11.01.26351441",
        "title": "A device study",
        "authors": "Rani, A.; Mishra, S.",
        "author_corresponding_institution": "Medtronic PLC",
        "date": "2026-11-01",
        "version": "1",
        "category": "cardiovascular medicine",
        "abstract": "We tested a catheter.",
        "published": "NA",
        "license": "CC-BY 4.0",
        "server": "medRxiv",
    }, "medrxiv")
    assert record.published_at == "2026-11-01"
    assert record.event_at == record.published_at
    # A preprint that has not become a paper must not carry a fabricated publication date.
    assert record.extra["journal_outcome"] == "not_yet_published"
    assert record.payload["journal_published"] == "NA"
    # The corresponding institution is what lets this lane attach to a company.
    assert record.extra["organization_hint"] == "Medtronic PLC"


def test_preprint_paging_stops_on_the_reported_total():
    from medradar.radar.adapters.preprints import PreprintAdapter

    adapter = PreprintAdapter(_taxonomy(), categories=("surgery",))
    payload = {
        "messages": [{"total": 150, "count": 2}],
        "collection": [
            {"doi": "10.1/a", "title": "Surgical robot", "date": "2026-11-02",
             "category": "surgery"},
            {"doi": "10.1/b", "title": "Oncology piece", "date": "2026-11-02",
             "category": "oncology"},
        ],
    }
    page = adapter.fetch_page(_ctx(_ParamFetcher([payload])), Scope("server:medrxiv"), "0")
    assert len(page.records) == 1                   # oncology filtered out client-side
    assert page.records[0].payload["category"] == "surgery"
    assert page.next_cursor == "2"                  # offset advances by what the API returned
    assert page.watermark


def test_openalex_select_is_a_cost_and_correctness_decision(monkeypatch):
    """Measured 2026-11-24: ``grants`` is not a valid select field (the request 400s), and a
    request costs $0.001 out of a $0.10/day budget shared across the host's IP. So the default
    selects a small field set and funding metadata is opt-in at ~20x the bytes.
    """
    from medradar.radar.adapters.openalex import (FULL_RECORD_ENV, SELECT_FIELDS,
                                                  OpenAlexAdapter)

    assert "grants" not in SELECT_FIELDS

    monkeypatch.delenv(FULL_RECORD_ENV, raising=False)
    fetcher = _ParamFetcher([{"meta": {"count": 0, "next_cursor": None}, "results": []}])
    OpenAlexAdapter(_taxonomy()).fetch_page(_ctx(fetcher), Scope("query:device_safety"), None)
    params = fetcher.calls[0]["params"]
    assert params["select"] == SELECT_FIELDS
    assert params["cursor"] == "*"
    assert "from_publication_date" in params["filter"]

    monkeypatch.setenv(FULL_RECORD_ENV, "1")
    full = _ParamFetcher([{"meta": {"count": 0, "next_cursor": None}, "results": []}])
    OpenAlexAdapter(_taxonomy()).fetch_page(_ctx(full), Scope("query:device_safety"), None)
    assert "select" not in full.calls[0]["params"]      # full records carry grants


def test_openalex_separates_a_company_from_the_hospitals_around_it():
    from medradar.radar.adapters.openalex import _record

    record = _record({
        "id": "https://openalex.org/W123",
        "doi": "https://doi.org/10.1/x",
        "title": "Robot assisted surgery outcomes",
        "publication_date": "2026-10-01",
        "type": "article",
        "cited_by_count": 42,
        "counts_by_year": [{"year": 2026, "cited_by_count": 42}],
        "authorships": [
            {"author": {"display_name": "A. Surgeon"},
             "institutions": [{"display_name": "Massachusetts General Hospital"},
                              {"display_name": "Medtronic Inc"}]},
        ],
        "grants": [{"funder_display_name": "National Institutes of Health",
                    "award_id": "R01HL000001"}],
        "topics": [{"display_name": "Surgical Robotics"}],
        "primary_location": {"source": {"display_name": "Annals of Surgery"}},
        "open_access": {"is_oa": True, "oa_status": "gold"},
    })
    assert record.payload["cited_by_count"] == 42
    assert "Medtronic Inc" in record.payload["institutions"]
    assert record.payload["grants"][0]["award_id"] == "R01HL000001"
    # The hospital must not win the organisation hint: the company is what this project tracks.
    assert record.extra["organization_hint"] == "Medtronic Inc"
    assert record.published_at == "2026-10-01"


def test_the_new_sources_are_registered_and_configured():
    from medradar.radar.adapters import DEFAULT_ORDER, FACTORIES

    assert "preprints" in FACTORIES and "openalex" in FACTORIES
    assert DEFAULT_ORDER.index("preprints") < DEFAULT_ORDER.index("openalex")
    data = json.loads((CONFIG_DIR / "sources.json").read_text(encoding="utf-8"))
    sources = data["sources"] if isinstance(data, dict) and "sources" in data else data
    by_id = {entry["id"]: entry for entry in sources}
    for source_id in ("preprints", "openalex"):
        assert by_id[source_id]["enabled"] is True
        assert by_id[source_id]["adapter"] == source_id
        # The registry refuses a source without a recorded licence; keep that bar.
        assert by_id[source_id]["licence"]["name"]


def test_a_university_is_not_mistaken_for_a_company():
    """Measured false positive: "University College London" matched the substring " CO" inside
    COLLEGE and would have attached a university paper to a vendor."""
    from medradar.radar.adapters.openalex import _first_company_like

    assert _first_company_like(["University College London"]) is None
    assert _first_company_like(["San Diego State University"]) is None
    assert _first_company_like(["Massachusetts General Hospital"]) is None
    assert _first_company_like(["Medtronic Inc"]) == "Medtronic Inc"
    assert _first_company_like(["Siemens Healthineers AG"]) == "Siemens Healthineers AG"
    # The company still wins when it sits behind a hospital in the list.
    assert _first_company_like(
        ["Massachusetts General Hospital", "Medtronic Inc"]) == "Medtronic Inc"


def test_openalex_select_never_asks_for_grants():
    """Measured: ``grants`` is not a valid select field and the request 400s."""
    from medradar.radar.adapters.openalex import OpenAlexAdapter, SELECT_FIELDS

    assert "grants" not in SELECT_FIELDS
    fetcher = _ParamFetcher([{"meta": {"count": 0, "next_cursor": None}, "results": []}])
    OpenAlexAdapter(_taxonomy()).fetch_page(_ctx(fetcher), Scope("query:surgical_robotics"), None)
    assert "grants" not in fetcher.calls[0]["params"]["select"]
    assert "authorships" in fetcher.calls[0]["params"]["select"]


# --------------------------------------------------- JATS full-text parsing
JATS_SAMPLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE article PUBLIC "-//NLM//DTD JATS//EN" "x.dtd">
<article>
  <front><article-meta>
    <title-group><article-title>A catheter study</article-title></title-group>
    <abstract><p>We tested it.</p></abstract>
  </article-meta>
  <journal-meta><journal-title>Journal of Tests</journal-title></journal-meta></front>
  <body>
    <sec><title>1. Introduction</title><p>Background text.</p></sec>
    <sec><title>2. Methods</title><p>We used a catheter.</p>
      <sec><title>2.1 Study Limitations</title><p>Small sample.</p></sec>
    </sec>
    <sec><title>Results</title><p>It worked.</p></sec>
  </body>
  <back><ref-list>
    <ref><mixed-citation>A</mixed-citation></ref>
    <ref><mixed-citation>B</mixed-citation></ref>
  </ref-list></back>
</article>
"""


def test_jats_sections_keep_the_publishers_structure():
    from medradar.radar.jats import parse_jats

    document = parse_jats(JATS_SAMPLE)
    assert document.title == "A catheter study"
    assert document.journal == "Journal of Tests"
    assert document.abstract == "We tested it."
    assert document.reference_count == 2
    # Numbering is stripped from the heading, and a nested section keeps its parent path.
    assert "2. Methods" not in document.sections
    assert document.sections["Methods"] == "We used a catheter."
    assert document.sections["Methods > Study Limitations"] == "Small sample."
    assert document.sections["Results"] == "It worked."


def test_a_parent_section_never_swallows_its_children():
    """If the parent repeated the child's text, every result would be counted twice."""
    from medradar.radar.jats import parse_jats

    document = parse_jats(JATS_SAMPLE)
    assert "Small sample" not in document.sections["Methods"]


def test_canonical_headings_are_offered_for_a_stable_question():
    from medradar.radar.jats import parse_jats

    document = parse_jats(JATS_SAMPLE)
    assert document.canonical["results"] == "It worked."
    assert document.canonical["limitations"] == "Small sample."
    assert document.canonical["methods"] == "We used a catheter."


def test_jats_without_body_text_is_an_error_not_an_empty_paper():
    """An unparseable payload must not be stored as 'this paper has no sections'."""
    from medradar.radar.jats import JatsError, parse_jats

    with pytest.raises(JatsError):
        parse_jats(b"<article><front/></article>")
    with pytest.raises(JatsError):
        parse_jats(b"not xml at all")


def test_heading_numbering_is_stripped_without_eating_the_first_letter():
    """Measured on the first real record (PMC13744766): "Introduction" arrived as "ntroduction"
    because the Roman-numeral rule consumed the leading I."""
    from medradar.radar.jats import _clean_heading

    assert _clean_heading("Introduction") == "Introduction"
    assert _clean_heading("1. Introduction") == "Introduction"
    assert _clean_heading("2.3 Study Limitations") == "Study Limitations"
    assert _clean_heading("IV. Discussion") == "Discussion"
    assert _clean_heading("Results.") == "Results"


def test_a_pre_digitisation_filing_is_never_requested(tmp_path):
    """Measured: 0 of 60 sampled filings from 1998-2009 have a PDF at any path shape.

    Requesting them anyway costs ~27,000 guaranteed 404s, so the year is checked first and the
    outcome gets its own counter - a known absence must not be recorded as a discovered one.
    """
    from medradar.radar.documents import DocumentStore
    from medradar.radar.fda_corpus import SUMMARY_PDF_FLOOR, build_corpus, summary_pdf_available

    assert SUMMARY_PDF_FLOOR == "2010-06-01"
    assert summary_pdf_available("K093456") is False
    assert summary_pdf_available("K002182") is False
    assert summary_pdf_available("K102109") is True
    assert summary_pdf_available("K233456") is True

    calls = {"n": 0}

    class FakeFetcher:
        def get_bytes(self, url, *, headers=None, allow_not_found=False):
            calls["n"] += 1
            raise AssertionError("must not request a pre-digitisation filing")

    index = [{"k_number": "K093456"}, {"k_number": "K002182"}]
    stats = build_corpus(FakeFetcher(), DocumentStore(tmp_path), index)
    assert calls["n"] == 0
    assert stats.attempted == 0
    assert stats.skipped_pre_digitisation == 2
    assert stats.not_published == 0


def test_a_scanned_pdf_is_reported_as_no_text_layer_not_as_a_failure(tmp_path):
    """Measured on the real crawl: 221 of the first 500 filings were scans without a text layer.

    That is a property of the source, not a bug in the reader, so it must not hide inside
    "failed" where nobody would think to look for it.
    """
    import zlib

    from medradar.radar.documents import DocumentStore
    from medradar.radar.fda_corpus import build_corpus

    # A PDF with an image-only content stream: valid file, no text operators.
    image_stream = zlib.compress(b"q 612 0 0 792 0 0 cm /Im0 Do Q\n")
    scanned = (b"%PDF-1.4\n4 0 obj\n<< /Length " + str(len(image_stream)).encode()
               + b" /Filter /FlateDecode >>\nstream\n" + image_stream
               + b"\nendstream\nendobj\n%%EOF\n" + b"%" + bytes(range(256)) * 12)

    class Result:
        def __init__(self, payload):
            self.status = 200
            self.payload = payload
            self.raw_bytes = len(payload)
            self.content_type = "application/pdf"

    class FakeFetcher:
        def get_bytes(self, url, *, headers=None, allow_not_found=False):
            return Result(scanned)

    stats = build_corpus(FakeFetcher(), DocumentStore(tmp_path), [{"k_number": "K102109"}])
    assert stats.no_text_layer == 1
    assert stats.failed == 0
    assert stats.with_text == 0


def test_a_single_bad_document_does_not_kill_the_batch(tmp_path):
    """Measured: an unsupervised run died silently at 600 documents on one transport error."""
    from medradar.radar.documents import DocumentStore
    from medradar.radar.fda_corpus import build_corpus

    class Result:
        def __init__(self, status, payload=b"", content_type=None):
            self.status = status
            self.payload = payload
            self.raw_bytes = len(payload)
            self.content_type = content_type

    class FakeFetcher:
        def get_bytes(self, url, *, headers=None, allow_not_found=False):
            if "K200001" in url:
                raise RuntimeError("connection reset by peer")
            return Result(200, _big_pdf(), "application/pdf")

    index = [{"k_number": "K200001"}, {"k_number": "K200002"}]
    stats = build_corpus(FakeFetcher(), DocumentStore(tmp_path), index)

    assert stats.attempted == 2
    assert stats.errored == 1
    assert stats.with_text == 1          # the second document still went through
    assert stats.last_error and "K200001" in stats.last_error
    assert "connection reset" in stats.last_error


# ------------------------------------------------------- the third leg: failures
def _maude_event(model, brand, event_type="Malfunction", code="HWC", received="2024-05-01"):
    return {
        "event_type": event_type,
        "date_received": received + "T00:00:00",
        "device": [{"device_report_product_code": code, "model_number": model,
                    "brand_name": brand, "manufacturer_d_name": "ACME"}],
    }


def test_model_normalisation_keeps_separators_from_mattering():
    """Measured: a label prints EPD6AB252 or GalaxyStar-WR-14-B4 with no consistent convention."""
    from medradar.radar.failure_index import normalise_brand, normalise_model

    assert normalise_model("EPD6AB252") == "EPD6AB252"
    assert normalise_model("GalaxyStar-WR-14-B4") == "GALAXYSTARWR14B4"
    assert normalise_model("11-4105") == "114105"
    assert normalise_model("  Rev C  ") == "REVC"
    assert normalise_brand("St. Jude Medical") == "ST JUDE MEDICAL"


def test_failure_index_records_models_and_counts_blank_ones(tmp_path):
    """The blank-model count is the measurement that explains why exact matching failed."""
    from medradar.radar.failure_index import build_failure_index, index_summary

    class FakeFetcher:
        def get_json(self, url, *, params=None, headers=None, allow_not_found=False):
            return {"meta": {"results": {"total": 3}},
                    "results": [_maude_event("11-4105", "Spine Wave"),
                                _maude_event("", "Spine Wave"),
                                _maude_event("2986650", "Medtronic Sofamor Danek",
                                             event_type="Injury")]}

    store = UdiReference(tmp_path / "reference.db")
    stats = build_failure_index(FakeFetcher(), store, ["HWC"], page_size=250)
    assert stats.events_seen == 3
    assert stats.rows_written == 2          # only the two with a model can be joined later
    assert stats.rows_skipped == 1          # the blank model is counted, not stored
    assert stats.per_code == {"HWC": 2}
    summary = index_summary(store)
    assert summary["distinct_models"] == 2
    store.close()


def test_model_and_brand_answers_are_kept_apart(tmp_path):
    """A brand hit is the manufacturer's family, not this device; the two must not merge."""
    from medradar.radar.failure_index import (build_failure_index, failures_for_brand,
                                              failures_for_model)

    class FakeFetcher:
        def get_json(self, url, *, params=None, headers=None, allow_not_found=False):
            return {"meta": {"results": {"total": 2}},
                    "results": [_maude_event("11-4105", "Spine Wave", "Injury"),
                                _maude_event("11-9999", "Spine Wave", "Malfunction")]}

    store = UdiReference(tmp_path / "reference.db")
    build_failure_index(FakeFetcher(), store, ["HWC"], page_size=250)

    exact = failures_for_model(store, "11-4105")
    assert exact["events"] == 1
    assert exact["by_type"] == {"Injury": 1}
    assert exact["method"] == "model_exact"

    family = failures_for_brand(store, "Spine Wave")
    assert family["events"] == 2
    assert family["method"] == "brand_exact"
    assert family["weaker_than_model"] is True

    assert failures_for_model(store, "")["events"] == 0
    assert failures_for_model(store, "")["method"] == "none"
    store.close()


def test_the_index_stops_at_its_page_cap_and_says_so(tmp_path):
    from medradar.radar.failure_index import build_failure_index

    class FakeFetcher:
        def __init__(self):
            self.pages = 0

        def get_json(self, url, *, params=None, headers=None, allow_not_found=False):
            self.pages += 1
            return {"meta": {"results": {"total": 100_000}},
                    "results": [_maude_event(f"M{self.pages}", "X")] * 250}

    store = UdiReference(tmp_path / "reference.db")
    stats = build_failure_index(FakeFetcher(), store, ["HWC"], page_size=250,
                                max_pages_per_code=3)
    assert stats.pages == 3
    assert stats.stop_reason and "page cap" in stats.stop_reason
    store.close()


def test_a_truncated_body_is_retried_rather_than_fatal():
    """Measured: a 999-row MAUDE page is ~9 MB and one arrived with 3.6 MB missing."""
    import http.client

    from medradar.radar.http import PoliteFetcher

    state = {"attempts": 0}

    class Response:
        status = 200
        headers = {}

        def __init__(self, payload):
            self._payload = payload

        def read(self, *args):
            return self._payload

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def opener(request, timeout=None):
        state["attempts"] += 1
        if state["attempts"] == 1:
            # http.client.HTTPException inherits from Exception, not OSError: this used to
            # escape the transport handler entirely and kill a long sweep.
            raise http.client.IncompleteRead(b"partial", 3_643_358)
        return Response(b'{"ok": true}')

    fetcher = PoliteFetcher(opener=opener)
    assert fetcher.get_json("https://api.fda.gov/device/event.json") == {"ok": True}
    assert state["attempts"] == 2
    assert fetcher.stats["retries"] == 1


def test_the_bridge_query_targets_only_records_that_declare_a_submission():
    from medradar.radar.premarket_bridge import BRIDGE_SEARCH, BRIDGE_TOTAL_MEASURED

    # The restricted sweep is why this is ~1,586 pages instead of ~5,187.
    assert "premarket_submissions.submission_number" in BRIDGE_SEARCH
    assert BRIDGE_TOTAL_MEASURED < 5_182_695


def test_bridge_sweep_resumes_from_its_cursor(tmp_path):
    from medradar.radar.premarket_bridge import sync_bridge

    rows = [_udi_row("K250063", f"GalaxyStar-{i}") for i in range(6)]

    class FakeFetcher:
        def __init__(self):
            self.skips = []

        def get_json(self, url, *, params=None, headers=None, allow_not_found=False):
            skip = (params or {}).get("skip") or 0
            self.skips.append(skip)
            page = rows[skip:skip + 3]
            return {"meta": {"results": {"total": len(rows)}}, "results": page}

    store = UdiReference(tmp_path / "reference.db")
    fetcher = FakeFetcher()
    first = sync_bridge(fetcher, store, max_pages=1, page_size=3)
    assert first.pages == 1
    assert first.devices_written == 3
    # 6 records exist and one page of 3 was read: the sweep must say so.
    assert first.complete is False
    assert first.stop_reason == "page cap 1 reached"
    assert store.kv_get("premarket_bridge")["cursor"] == 3

    second = sync_bridge(fetcher, store, page_size=3)
    assert fetcher.skips[-1] == 3             # resumed, did not restart
    assert second.cursor == 6
    assert second.complete is True
    store.close()


def test_targeted_link_writes_the_bridge_for_named_submissions(tmp_path):
    from medradar.radar.premarket_bridge import link_submissions

    seen = {}

    class FakeFetcher:
        def get_json(self, url, *, params=None, headers=None, allow_not_found=False):
            search = (params or {}).get("search") or ""
            seen["search"] = search
            if "K250063" in search:
                return {"meta": {"results": {"total": 1}},
                        "results": [_udi_row("K250063", "GalaxyStar-1")]}
            return None

    store = UdiReference(tmp_path / "reference.db")
    result = link_submissions(FakeFetcher(), store, ["K250063", "K999999"], batch=2)
    assert '"K250063" OR "K999999"' in seen["search"]
    assert result["resolved"] == 1
    assert result["submissions_written"] == 1
    store.close()


def test_a_510k_document_joins_to_its_devices_by_submission_number(tmp_path):
    """The whole point: no company-name matching anywhere in this join."""
    from medradar.radar.premarket_bridge import align_corpus, link_submissions

    class FakeFetcher:
        def get_json(self, url, *, params=None, headers=None, allow_not_found=False):
            return {"meta": {"results": {"total": 2}},
                    "results": [_udi_row("K250063", "A"), _udi_row("K250063", "B")]}

    store = UdiReference(tmp_path / "reference.db")
    link_submissions(FakeFetcher(), store, ["K250063"])

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "510k_summary_K250063.json").write_text(
        '{"kind":"510k_summary","identifier":"K250063","status":"text","text_chars":36788}',
        encoding="utf-8")
    (corpus / "510k_summary_K241973.json").write_text(
        '{"kind":"510k_summary","identifier":"K241973","status":"not_published"}',
        encoding="utf-8")

    report = align_corpus(corpus, store)
    assert report.documents == 2
    assert report.documents_with_text == 1
    assert report.aligned == 1
    assert report.aligned_with_text == 1
    assert report.devices == 2
    assert report.samples[0]["labeler_duns"] == "557821945"
    assert report.samples[0]["k_number"] == "K250063"
    store.close()


def test_document_entries_reads_the_stores_own_identifier_field(tmp_path):
    """Regression: the sidecar says ``identifier``, so reading ``k_number`` yielded nothing."""
    from medradar.radar.premarket_bridge import document_entries, document_k_numbers

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "510k_summary_K250063.json").write_text(
        '{"identifier":"K250063","status":"text","text_chars":123,"sections":{"indications":1}}',
        encoding="utf-8")
    entries = document_entries(corpus)
    assert entries == [{"k_number": "K250063", "status": "text", "text_chars": 123,
                        "sections": 1}]
    assert document_k_numbers(corpus) == ["K250063"]
