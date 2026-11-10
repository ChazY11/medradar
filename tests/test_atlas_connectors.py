"""Offline connector tests: real payload shapes, bounded parsing, clock semantics.

No network is used.  The fake client returns recorded real-world payloads (or
their trimmed equivalents) and records every call so a test can assert the
connector stayed within its request budget.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from medradar.atlas.connectors.accessgudid import AccessGudidConnector
from medradar.atlas.connectors.canada_mdall import CanadaMdallConnector, iter_json_array
from medradar.atlas.connectors.openfda_udi import OpenFdaUdiConnector
from medradar.atlas.evidence.http import HttpLedger, HttpResult

GUDID_PAYLOAD = {
    "gudid": {
        "device": {
            "publicDeviceRecordKey": "a987ddbc-beba-4ae6-a807-4727f0ecaf5d",
            "publicVersionStatus": "Update",
            "deviceRecordStatus": "Published",
            "publicVersionNumber": 5,
            "publicVersionDate": "2026-03-03T00:00:00.000Z",
            "devicePublishDate": "2015-05-08T00:00:00.000Z",
            "identifiers": {
                "identifier": [
                    {"deviceId": "08717648200274", "deviceIdType": "Primary", "deviceIdIssuingAgency": "GS1"}
                ]
            },
            "brandName": "XIENCE ALPINE",
            "versionModelNumber": "1145350-28",
            "catalogNumber": "1145350-28",
            "companyName": "ABBOTT VASCULAR INC.",
            "deviceDescription": "XIENCE Alpine stent",
            "productCodes": {"fdaProductCode": [{"productCode": "NIQ"}]},
        }
    },
    "productCodes": [{"productCode": "NIQ", "deviceClass": "3"}],
}

OPENFDA_UDI_RECORD = {
    "public_device_record_key": "a987ddbc-beba-4ae6-a807-4727f0ecaf5d",
    "identifiers": [{"id": "08717648200274", "type": "Primary", "issuing_agency": "GS1"}],
    "brand_name": "XIENCE ALPINE",
    "version_or_model_number": "1145350-28",
    "company_name": "MEDTRONIC, INC.",
    "publish_date": "2015-05-08",
    "public_version_date": "2026-03-03",
    "product_codes": [{"code": "NIQ", "openfda": {"device_class": "3"}}],
}

MDALL_LICENCE = {
    "original_licence_no": 108437,
    "licence_status": "I",
    "licence_name": "CAPTION AI",
    "first_licence_status_dt": "2022-10-21",
    "last_refresh_dt": "2026-11-06",
    "end_date": None,
    "licence_type_cd": "F",
    "licence_type_desc": "Device Family",
    "company_id": 116173,
    "appl_risk_class": 2,
}


class FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []
        self.ledger = HttpLedger()
        self._made = 0

    def get(self, url, *, params=None, headers=None, accept="application/json"):
        self.calls.append((url, dict(params or {})))
        self._made += 1
        body = json.dumps(self.payload).encode("utf-8")
        return HttpResult(url, "GET", 200, body, {}, 1, 1)

    def requests_made(self):
        return self._made


class AccessGudidTests(unittest.TestCase):
    def test_evidence_uses_publish_date_as_public_clock(self) -> None:
        connector = AccessGudidConnector(FakeClient(GUDID_PAYLOAD))
        record = connector.to_evidence(
            GUDID_PAYLOAD, fetched_at="2026-11-10T00:00:00Z", run_id="run-1"
        )
        assert record is not None
        self.assertEqual(record["time"]["source_public_at"], "2015-05-08")
        self.assertEqual(record["time"]["source_public_at_quality"], "day")
        self.assertEqual(record["time"]["first_observed_at"], "2026-11-10T00:00:00Z")
        self.assertEqual(record["canonical_key"], "di:08717648200274")
        self.assertEqual(record["identity_resolution_status"], "none")  # Abbott is not a target firm

    def test_lookup_returns_none_on_empty_gudid(self) -> None:
        client = FakeClient({"gudid": None})
        self.assertIsNone(AccessGudidConnector(client).fetch("08717648200274"))


class OpenFdaUdiTests(unittest.TestCase):
    def test_company_link_is_confirmed_for_curated_alias(self) -> None:
        connector = OpenFdaUdiConnector(FakeClient({}))
        record = connector.to_evidence(
            OPENFDA_UDI_RECORD, fetched_at="2026-11-10T00:00:00Z", run_id="run-1"
        )
        self.assertEqual(record["identity_resolution_status"], "confirmed")
        self.assertEqual(record["entity_refs"][0]["firm_key"], "medtronic")

    def test_model_number_is_not_an_identifier(self) -> None:
        connector = OpenFdaUdiConnector(FakeClient({}))
        record = connector.to_evidence(
            OPENFDA_UDI_RECORD, fetched_at="2026-11-10T00:00:00Z", run_id="run-1"
        )
        schemes = {i["scheme"] for i in record["identifiers"]}
        self.assertIn("di", schemes)
        self.assertNotIn("model", schemes)


class CanadaMdallTests(unittest.TestCase):
    def test_licence_public_date_is_derived_and_flagged(self) -> None:
        connector = CanadaMdallConnector(FakeClient({}))
        record = connector.licence_evidence(
            MDALL_LICENCE, company={"company_name": "Medtronic"}, fetched_at="2026-11-10T00:00:00Z",
            run_id="run-1",
        )
        self.assertEqual(record["time"]["source_public_at"], "2022-10-21")
        self.assertEqual(record["time"]["source_public_at_quality"], "derived")
        self.assertIn("derived_time", record["quality_flags"])
        self.assertEqual(record["canonical_key"], "licence_no:108437")

    def test_gtin_identifier_becomes_di_and_model_does_not(self) -> None:
        connector = CanadaMdallConnector(FakeClient({}))
        gtin = connector.identifier_evidence(
            {"original_licence_no": 1, "device_id": 2, "device_identifier": "00198953030233",
             "first_licence_dt": "2025-05-21"},
            fetched_at="2026-11-10T00:00:00Z", run_id="run-1",
        )
        self.assertIn("di", {i["scheme"] for i in gtin["identifiers"]})
        model = connector.identifier_evidence(
            {"original_licence_no": 1, "device_id": 3, "device_identifier": "NHK 21 15-40",
             "first_licence_dt": "2025-05-21"},
            fetched_at="2026-11-10T00:00:00Z", run_id="run-1",
        )
        self.assertNotIn("di", {i["scheme"] for i in model["identifiers"]})
        self.assertIn("missing_primary_identifier", model["quality_flags"])

    def test_streaming_parser_handles_chunk_boundaries(self) -> None:
        rows = [{"device_identifier": f"0000000000000{i}", "original_licence_no": i} for i in range(50)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "table.json"
            path.write_text(json.dumps(rows), encoding="utf-8")
            parsed = list(iter_json_array(path, chunk_size=17))
        self.assertEqual(parsed, rows)


if __name__ == "__main__":
    unittest.main()
