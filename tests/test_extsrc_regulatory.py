"""Offline tests for the regulatory connectors (no network, no filesystem samples).

Every fixture below is a small hand-written dict/XML string **modelled on** a real
response shape; the bytes that were actually captured live live under
``research/data_expansion/samples/<source_id>/`` and are referenced from
``PROBE_RESULT.json`` instead.  Nothing here touches the network.
"""

from __future__ import annotations

import unittest

from medradar.external_sources import identity, schema, timeq
from medradar.external_sources.regulatory import (
    accessgudid,
    canada_mdall,
    fda_gudid_download,
    openfda_bulk_download,
    openfda_device_510k,
    openfda_device_classification,
    openfda_device_pma,
    openfda_device_registrationlisting,
)

FETCHED_AT = "2026-11-09T00:00:00Z"


# --------------------------------------------------------------------------- fixtures
K510_RECORD = {
    "k_number": "K973011",
    "device_name": "CATHETER, INTRAVASCULAR OCCLUSION, PERMANENT",
    "applicant": "MEDTRONIC VASCULAR, INC.",
    "product_code": "DQY",
    "decision_date": "1997-12-19",
    "date_received": "1997-11-14",
    "decision_code": "SESE",
    "decision_description": "Substantially Equivalent",
    "clearance_type": "Traditional",
    "advisory_committee_description": "Cardiovascular",
    "statement_or_summary": "Summary",
    "country_code": "US",
}

PMA_ORIGINAL = {
    "pma_number": "P970003",
    "supplement_number": "",
    "applicant": "MEDTRONIC INC.",
    "trade_name": "GYRUS ACMI",
    "generic_name": "ELECTROSURGICAL",
    "product_code": "GEI",
    "decision_date": "1997-05-02",
    "date_received": "1996-01-02",
    "decision_code": "APPR",
    "supplement_type": "",
    "supplement_reason": "",
    "expedited_review_flag": "",
}

PMA_SUPPLEMENT = dict(
    PMA_ORIGINAL,
    supplement_number="007",
    decision_date="2004-08-26",
    supplement_type="Real-Time Process",
    supplement_reason="Manufacturing Change",
)

CLASSIFICATION_RECORD = {
    "product_code": "DQY",
    "device_name": "Catheter, Intravascular Occlusion, Permanent",
    "device_class": "2",
    "regulation_number": "870.1250",
    "medical_specialty_description": "Cardiovascular",
    "definition": "A permanent occlusion catheter is placed in a blood vessel.",
    "implant_flag": "N",
    "life_sustain_support_flag": "N",
    "gmp_exempt_flag": "N",
    "submission_type_id": "2",
}

REGISTRATION_RECORD = {
    "establishment_type": ["Manufacture Medical Device"],
    "k_number": ["K973011"],
    "pma_number": ["P970003"],
    "proprietary_name": ["REEF HP"],
    "products": [
        {"product_code": "DQY", "openfda": {"device_name": "Catheter"}},
        {"product_code": "GEI", "openfda": {"device_name": "Electrosurgical"}},
    ],
    "registration": {
        "name": "MEDTRONIC VASCULAR, INC.",
        "registration_number": "3016704395",
        "fei_number": "3016704395",
    },
}

ACCESSGUDID_PAYLOAD = {
    "gudid": {
        "device": {
            "publicDeviceRecordKey": "424a88d6-a714-4a49-a747-54abc7ba1259",
            "publicVersionStatus": "Update",
            "deviceRecordStatus": "Published",
            "publicVersionNumber": 3,
            "publicVersionDate": "2024-07-05T00:00:00.000Z",
            "devicePublishDate": "2016-01-07T00:00:00.000Z",
            "deviceCommDistributionStatus": "In Commercial Distribution",
            "identifiers": {
                "identifier": [
                    {
                        "deviceId": "00643169718425",
                        "deviceIdType": "Primary",
                        "deviceIdIssuingAgency": "GS1",
                    }
                ]
            },
            "brandName": "REEF HP",
            "companyName": "MEDTRONIC, INC.",
            "versionOrModelNumber": "RFHP",
        }
    }
}

GUDID_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<gudid xmlns="http://www.fda.gov/cdrh/gudid" version="1.0">
  <header>
    <database frequency="daily" id="6909" type="DELTA_INCREMENTAL">
      <downloadFile part="1" totalParts="1"/>
      <numberRecordXML>5548</numberRecordXML>
    </database>
    <creationDate>2026-11-02T10:05:09</creationDate>
    <period end="2026-11-02T10:05:09" start="2026-10-26T10:29:02"/>
  </header>
  <device>
    <publicDeviceRecordKey>025c0070-94f6-435f-973d-70c2da0eeab0</publicDeviceRecordKey>
    <publicVersionStatus>New</publicVersionStatus>
    <deviceRecordStatus>Published</deviceRecordStatus>
    <publicVersionNumber>1</publicVersionNumber>
    <publicVersionDate>2026-11-02</publicVersionDate>
    <devicePublishDate>2026-10-23</devicePublishDate>
    <deviceCommDistributionStatus>In Commercial Distribution</deviceCommDistributionStatus>
    <identifiers>
      <identifier>
        <deviceId>M739985203530</deviceId>
        <deviceIdType>Primary</deviceIdType>
        <deviceIdIssuingAgency>HIBCC</deviceIdIssuingAgency>
      </identifier>
    </identifiers>
    <brandName>REEF HP</brandName>
    <companyName>MEDTRONIC, INC.</companyName>
    <versionOrModelNumber>RFHP-2</versionOrModelNumber>
    <premarketSubmissions>
      <premarketSubmission><submissionNumber>K973011</submissionNumber></premarketSubmission>
    </premarketSubmissions>
  </device>
  <device>
    <publicDeviceRecordKey>11111111-2222-3333-4444-555555555555</publicDeviceRecordKey>
    <publicVersionDate>2026-11-02</publicVersionDate>
    <devicePublishDate>2026-10-24</devicePublishDate>
    <identifiers>
      <identifier>
        <deviceId>00840682146586</deviceId>
        <deviceIdType>Primary</deviceIdType>
        <deviceIdIssuingAgency>GS1</deviceIdIssuingAgency>
      </identifier>
    </identifiers>
    <brandName>DLIR</brandName>
    <companyName>GE Healthcare Japan Corporation</companyName>
  </device>
</gudid>
"""

MDALL_LICENCE = {
    "original_licence_no": 65113,
    "licence_status": "I",
    "appl_risk_class": 2,
    "licence_name": "REEF HP",
    "first_licence_status_dt": "2004-07-08",
    "last_refresh_dt": "2026-11-06",
    "end_date": None,
    "licence_type_cd": "F",
    "company_id": 114663,
    "licence_type_desc": "Device Family",
}


# ------------------------------------------------------------------------------ tests
class SchemaContractTests(unittest.TestCase):
    def test_openfda_510k_evidence_is_valid(self) -> None:
        record = openfda_device_510k.to_evidence(K510_RECORD, fetched_at=FETCHED_AT)
        self.assertEqual(schema.validate_evidence(record), [])
        self.assertEqual(record["kind"], "regulatory_clearance")
        self.assertEqual(record["source_id"], "openfda_device_510k")
        self.assertEqual(record["source_record_id"], "K973011")
        self.assertEqual(record["canonical_key"], "510k:K973011")

    def test_openfda_510k_normalize_flattens_real_fields(self) -> None:
        normalized = openfda_device_510k.normalize(K510_RECORD)
        self.assertEqual(normalized["k_number"], "K973011")
        self.assertEqual(normalized["decision_date"], "1997-12-19")
        self.assertEqual(normalized["advisory_committee_description"], "Cardiovascular")
        self.assertEqual(normalized["product_code"], "DQY")

    def test_evidence_id_is_deterministic_and_fetch_independent(self) -> None:
        first = openfda_device_510k.to_evidence(K510_RECORD, fetched_at=FETCHED_AT)
        second = openfda_device_510k.to_evidence(K510_RECORD, fetched_at="2027-01-01T00:00:00Z")
        self.assertEqual(first["evidence_id"], second["evidence_id"])
        self.assertEqual(first["canonical_key"], second["canonical_key"])

    def test_pma_original_and_supplement_are_distinct_records(self) -> None:
        original = openfda_device_pma.to_evidence(PMA_ORIGINAL, fetched_at=FETCHED_AT)
        supplement = openfda_device_pma.to_evidence(PMA_SUPPLEMENT, fetched_at=FETCHED_AT)
        self.assertEqual(schema.validate_evidence(original), [])
        self.assertEqual(schema.validate_evidence(supplement), [])
        self.assertEqual(original["source_record_id"], "P970003")
        self.assertEqual(supplement["source_record_id"], "P970003/007")
        self.assertNotEqual(original["evidence_id"], supplement["evidence_id"])
        # a supplement must not collapse onto the parent approval's canonical key
        self.assertEqual(original["canonical_key"], "pma:P970003")
        self.assertNotEqual(supplement["canonical_key"], original["canonical_key"])
        self.assertIs(schema.is_independent(original, supplement), True)
        schemes = {ident["scheme"] for ident in supplement["identifiers"]}
        self.assertNotIn("pma", schemes)
        self.assertIn("pma_supplement", schemes)

    def test_classification_claims_no_clock(self) -> None:
        record = openfda_device_classification.to_evidence(
            CLASSIFICATION_RECORD, fetched_at=FETCHED_AT
        )
        self.assertEqual(schema.validate_evidence(record), [])
        block = record["time"]
        self.assertEqual(block["event_at"], "")
        self.assertEqual(block["source_public_at"], "")
        self.assertEqual(block["source_public_at_quality"], "unknown")
        # the fetch clock is still recorded, so the record is not undated
        self.assertEqual(block["fetched_at"], FETCHED_AT)

    def test_registration_listing_claims_no_clock(self) -> None:
        record = openfda_device_registrationlisting.to_evidence(
            REGISTRATION_RECORD, fetched_at=FETCHED_AT
        )
        self.assertEqual(schema.validate_evidence(record), [])
        self.assertEqual(record["source_record_id"], "3016704395")
        self.assertEqual(record["time"]["source_public_at_quality"], "unknown")
        normalized = record["normalized"]
        self.assertEqual(normalized["product_codes"], ["DQY", "GEI"])
        self.assertEqual(normalized["k_numbers"], ["K973011"])


class TimeSemanticsTests(unittest.TestCase):
    def test_510k_publication_clock_is_flagged_derived(self) -> None:
        record = openfda_device_510k.to_evidence(K510_RECORD, fetched_at=FETCHED_AT)
        block = record["time"]
        self.assertEqual(block["event_at"], "1997-12-19")
        self.assertEqual(block["source_public_at"], "1997-12-19")
        self.assertEqual(block["source_public_at_quality"], "derived")
        self.assertFalse(timeq.quality_allows_lead_time(block["source_public_at_quality"]))
        self.assertEqual(timeq.check_ordering(block), [])

    def test_gudid_publish_date_is_a_real_clock_but_version_date_is_not(self) -> None:
        record = accessgudid.to_evidence(ACCESSGUDID_PAYLOAD, fetched_at=FETCHED_AT)
        block = record["time"]
        # devicePublishDate wins
        self.assertEqual(block["source_public_at"], "2016-01-07")
        self.assertEqual(block["source_public_at_quality"], "day")
        self.assertTrue(timeq.quality_allows_lead_time(block["source_public_at_quality"]))
        # publicVersionDate is retained but never promoted to a clock
        self.assertEqual(record["normalized"]["public_version_date"], "2024-07-05T00:00:00.000Z")
        for clock in ("event_at", "source_public_at", "first_observed_at", "fetched_at"):
            self.assertNotIn("2024-07-05", str(block[clock]))
        self.assertIsNone(block["event_at"] or None)

    def test_mdall_never_uses_refresh_or_cancellation_date_as_publication(self) -> None:
        record = canada_mdall.to_evidence(
            MDALL_LICENCE, company_name="MEDTRONIC INC.", fetched_at=FETCHED_AT
        )
        block = record["time"]
        self.assertEqual(block["source_public_at"], "2004-07-08")
        self.assertEqual(block["event_at"], "2004-07-08")
        self.assertEqual(block["source_public_at_quality"], "derived")
        # last_refresh_dt (2026-11-06) must survive only as data, never as a clock
        self.assertEqual(record["normalized"]["last_refresh_dt"], "2026-11-06")
        self.assertNotIn("2026-11-06", str(block))

    def test_first_observed_at_defaults_to_fetch_clock(self) -> None:
        record = canada_mdall.to_evidence(MDALL_LICENCE, fetched_at=FETCHED_AT)
        self.assertEqual(record["time"]["first_observed_at"], FETCHED_AT)
        self.assertEqual(record["time"]["observation_basis"], "fetch_clock")

    def test_lead_time_refuses_derived_quality(self) -> None:
        record = openfda_device_510k.to_evidence(K510_RECORD, fetched_at=FETCHED_AT)
        days = timeq.lead_time_days(record["time"]["source_public_at"], "1998-06-01")
        self.assertEqual(days, 164)
        # the number exists, but the quality gate must block its use for lead-time claims
        self.assertFalse(
            timeq.quality_allows_lead_time(record["time"]["source_public_at_quality"])
        )


class GUDIDParserTests(unittest.TestCase):
    def test_release_header_is_read_from_the_file(self) -> None:
        header = fda_gudid_download.release_header(GUDID_XML)
        self.assertEqual(header["frequency"], "daily")
        self.assertEqual(header["database_type"], "DELTA_INCREMENTAL")
        self.assertEqual(header["declared_records"], "5548")
        self.assertEqual(header["period_start"], "2026-10-26T10:29:02")
        self.assertEqual(header["period_end"], "2026-11-02T10:05:09")

    def test_namespaced_devices_are_parsed(self) -> None:
        devices = list(fda_gudid_download.iter_devices(GUDID_XML))
        self.assertEqual(len(devices), 2)
        # the real release files put xmlns attributes on <device>, so a naive byte
        # match on b"<device>" under-counts (observed live: 0 vs 5,548).  The parser
        # must therefore compare local tag names, not raw bytes.
        for element in devices:
            self.assertEqual(
                fda_gudid_download._local(element.tag), "device"
            )
            self.assertIn("}", element.tag)  # namespaced, as in the real files

    def test_device_normalize_and_evidence(self) -> None:
        header = fda_gudid_download.release_header(GUDID_XML)
        element = next(iter(fda_gudid_download.iter_devices(GUDID_XML)))
        normalized = fda_gudid_download.normalize(element, header=header)
        self.assertEqual(normalized["public_device_record_key"], "025c0070-94f6-435f-973d-70c2da0eeab0")
        self.assertEqual(normalized["device_publish_date"], "2026-10-23")
        self.assertEqual(normalized["premarket_submissions"], ["K973011"])
        record = fda_gudid_download.to_evidence(
            fda_gudid_download.normalize(element, header={**header, "file": "x.zip"}),
            fetched_at=FETCHED_AT,
        )
        self.assertEqual(schema.validate_evidence(record), [])
        self.assertEqual(record["time"]["source_public_at"], "2026-10-23")
        schemes = {ident["scheme"] for ident in record["identifiers"]}
        self.assertIn("di", schemes)
        self.assertIn("510k", schemes)

    def test_release_member_name_round_trip(self) -> None:
        import io
        import zipfile

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("DELTA_INCREMENTALDownload_Part1_Of_1_2026-11-02.xml", GUDID_XML)
        header, xml_bytes, member = fda_gudid_download.read_release(buffer.getvalue())
        self.assertEqual(member, "DELTA_INCREMENTALDownload_Part1_Of_1_2026-11-02.xml")
        self.assertEqual(header["declared_records"], "5548")
        self.assertEqual(len(xml_bytes), len(GUDID_XML))


class IdentityTests(unittest.TestCase):
    def test_medtronic_legal_entity_resolves_to_a_confirmed_link(self) -> None:
        record = openfda_device_510k.to_evidence(K510_RECORD, fetched_at=FETCHED_AT)
        refs = [ref for ref in record["entity_refs"] if ref.get("entity_type") == "company"]
        self.assertTrue(refs)
        self.assertEqual(refs[0]["resolved_key"], "medtronic")
        self.assertEqual(refs[0]["method"], "exact_alias")
        self.assertIn(refs[0]["method"], schema.CONFIRMED_METHODS)
        self.assertTrue(refs[0]["evidence"])

    def test_ge_healthcare_substring_resolves(self) -> None:
        record = openfda_device_registrationlisting.to_evidence(
            {
                "registration": {"name": "GE Healthcare Japan Corporation", "registration_number": "1"},
                "establishment_type": [],
                "k_number": [],
                "pma_number": [],
                "proprietary_name": [],
                "products": [],
            },
            fetched_at=FETCHED_AT,
        )
        refs = record["entity_refs"]
        self.assertTrue(refs)
        self.assertEqual(refs[0]["resolved_key"], "ge_healthcare")

    def test_unrelated_company_is_not_linked(self) -> None:
        record = openfda_device_510k.to_evidence(
            dict(K510_RECORD, applicant="ACME STENT MANUFACTURING GMBH"), fetched_at=FETCHED_AT
        )
        for ref in record["entity_refs"]:
            if ref.get("method") == "candidate":
                self.assertLess(ref["confidence"], 0.9)
            self.assertNotEqual(ref.get("method"), "official_id")

    def test_none_resolution_is_dropped_rather_than_guessed(self) -> None:
        refs = __import__(
            "medradar.external_sources.regulatory._common", fromlist=["company_refs"]
        ).company_refs("")
        self.assertEqual(refs, [])

    def test_accessgudid_di_collapses_with_openfda_udi(self) -> None:
        """GUDID (AccessGUDID) and openFDA UDI describe the same device: one canonical key."""
        gudid = accessgudid.to_evidence(ACCESSGUDID_PAYLOAD, fetched_at=FETCHED_AT)
        self.assertEqual(gudid["canonical_key"], "di:00643169718425")
        self.assertNotEqual(gudid["source_id"], "openfda_device_udi")
        # same canonical key as another publisher of the same DI => not independent
        other = dict(gudid, evidence_id="ev_other", source_id="openfda_device_udi")
        self.assertFalse(schema.is_independent(gudid, other))


class BulkDownloadTests(unittest.TestCase):
    def test_manifest_projection_keeps_export_date(self) -> None:
        manifest = {
            "results": {
                "device": {
                    "classification": {
                        "export_date": "2026-11-02",
                        "total_records": 7097,
                        "partitions": [
                            {
                                "file": "https://download.open.fda.gov/device/classification/x.json.zip",
                                "size_mb": "3.13",
                                "records": 7097,
                            }
                        ],
                    }
                }
            }
        }
        exports = openfda_bulk_download.device_exports(manifest)
        self.assertEqual(exports["classification"]["export_date"], "2026-11-02")
        self.assertEqual(exports["classification"]["partitions"][0]["records"], 7097)

    def test_bulk_record_shares_evidence_id_with_the_api_connector(self) -> None:
        api = openfda_device_510k.to_evidence(K510_RECORD, fetched_at=FETCHED_AT)
        bulk = openfda_bulk_download.to_evidence(
            K510_RECORD, endpoint="510k", export_date="2026-11-02", fetched_at=FETCHED_AT
        )
        self.assertEqual(api["evidence_id"], bulk["evidence_id"])
        self.assertNotEqual(api["content_hash"], bulk["content_hash"])
        self.assertEqual(bulk["normalized"]["export_date"], "2026-11-02")
        # the export date is a snapshot clock, never a record clock
        self.assertNotIn("2026-11-02", bulk["time"]["source_public_at"])
        self.assertEqual(schema.validate_evidence(bulk), [])

    def test_unknown_endpoint_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            openfda_bulk_download.to_evidence({}, endpoint="udi", fetched_at=FETCHED_AT)


class GuardTests(unittest.TestCase):
    def test_record_without_identifier_is_rejected(self) -> None:
        for module, payload in (
            (openfda_device_510k, {"device_name": "no number"}),
            (openfda_device_pma, {"applicant": "x"}),
            (openfda_device_classification, {"device_name": "no code"}),
            (openfda_device_registrationlisting, {"products": []}),
        ):
            with self.assertRaises(ValueError):
                module.to_evidence(payload, fetched_at=FETCHED_AT)

    def test_accessgudid_rejects_a_record_without_identifiers(self) -> None:
        with self.assertRaises(ValueError):
            accessgudid.to_evidence({"gudid": {"device": {"brandName": "x"}}}, fetched_at=FETCHED_AT)

    def test_mdall_rejects_a_licence_without_number(self) -> None:
        with self.assertRaises(ValueError):
            canada_mdall.to_evidence({"licence_name": "x"}, fetched_at=FETCHED_AT)

    def test_normalizers_are_pure(self) -> None:
        """Normalising twice must not mutate the input or drift."""
        before = dict(K510_RECORD)
        first = openfda_device_510k.normalize(K510_RECORD)
        second = openfda_device_510k.normalize(K510_RECORD)
        self.assertEqual(first, second)
        self.assertEqual(K510_RECORD, before)

    def test_licence_posture_is_a_known_value(self) -> None:
        for module in (openfda_device_510k, openfda_device_pma, accessgudid, canada_mdall):
            self.assertIn(module.LICENCE_STATUS, schema.LICENCE_STATUSES)

    def test_identifier_normalisation(self) -> None:
        self.assertEqual(identity.normalize_di("00643169718425"), "00643169718425")
        self.assertEqual(identity.normalize_di("0064-3169-718425"), "00643169718425")
        self.assertEqual(identity.normalize_regulatory_number("k973011"), "K973011")


if __name__ == "__main__":
    unittest.main()
