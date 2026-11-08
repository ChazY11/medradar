"""Offline tests for the postmarket (recall / MAUDE / shortage / import-alert) connectors.

Everything here runs without network access: parsers are pure functions, the
connector ``to_evidence`` functions take small inline dicts, and the collector
tests use a fake client.  ``python -m medradar selftest`` must stay green.
"""

from __future__ import annotations

import json
import unittest

from medradar.external_sources import base as ev_base
from medradar.external_sources import identity as ev_identity
from medradar.external_sources import schema as ev_schema
from medradar.external_sources.regulatory import postmarket_common as common
from medradar.external_sources.regulatory import postmarket_fda_device_shortages as shortages
from medradar.external_sources.regulatory import postmarket_fda_import_alerts as alerts
from medradar.external_sources.regulatory import postmarket_openfda_device_maude as maude
from medradar.external_sources.regulatory import postmarket_openfda_device_recall as recall

FETCHED_AT = "2026-11-09T00:00:00Z"

RECALL_ITEM = {
    "cfres_id": "30043",
    "product_res_number": "Z-0001-04",
    "event_date_initiated": "2003-10-27",
    "event_date_posted": "2003-10-29",
    "event_date_terminated": "2004-03-24",
    "recall_status": "Terminated",
    "res_event_number": "27549",
    "product_code": "IZL--",
    "k_numbers": ["K020436"],
    "product_description": "Sedecal SP-HF 4.0 Portable X-Ray System",
    "recalling_firm": "Medtronic Puerto Rico Operations Co.",
    "reason_for_recall": "minimum source-skin-distance not met",
    "root_cause_description": "Other",
    "action": "Important Safety Notice sent",
    "city": "Humacao",
    "state": "PR",
    "country": "US",
}

MAUDE_ITEM = {
    "mdr_report_key": "999001",
    "report_number": "2243621-2024-00001",
    "event_type": "Injury",
    "date_of_event": "20240115",
    "date_received": "20240201",
    "date_report": "20240120",
    "date_report_to_fda": "20240122",
    "date_added": "20240210",
    "manufacturer_name": "",
    "manufacturer_country": "US",
    "report_source_code": "Manufacturer report",
    "device": [
        {
            "manufacturer_d_name": "MEDTRONIC MINIMED",
            "brand_name": "MINIMED 780G",
            "generic_name": "INSULIN PUMP",
            "device_report_product_code": "OZP",
            "model_number": "MMT-1886",
        }
    ],
}

SHORTAGE_HTML = """
<html><body>
<table class="table"><thead><tr>
<th>Category</th><th>Product Code (Description)</th>
<th>Availability and Estimated Shortage Duration</th><th>Additional Information</th>
<th>Reason for Interruption (per 506J)</th><th>Date (YYYY/MM/DD)</th>
</tr></thead><tbody>
<tr>
<td>Neurology &ndash; Neurosurgical Devices</td>
<td><strong>HBA</strong> (Neurosurgical pattie)</td>
<td>Estimated through Q4 2026</td>
<td>Patties are in shortage.</td>
<td>Shortage of a component.</td>
<td>2026/05/06 initial</td>
</tr>
</tbody></table>
<table class="table"><thead><tr>
<th>Date Posted</th><th>Category</th><th>Product Code</th><th>Manufacturer Name</th>
<th>Device Trade Name</th><th>Reason for Discontinuance</th>
</tr></thead><tbody>
<tr>
<td>10/26/2026</td><td>HEMATOLOGY - Immunology</td>
<td>GKZ&nbsp; (COUNTER, DIFFERENTIAL CELL)</td>
<td>Medtronic Puerto Rico Operations Co.</td>
<td>CELL-DYN Sapphire Systems</td>
<td>Discontinuance of the manufacture of the device</td>
</tr>
<tr>
<td>10/20/2026</td><td>RADIOLOGY</td><td>JAK (X-RAY SYSTEM)</td>
<td>Unrelated Instruments LLC</td><td>Model 9</td>
<td>Discontinuance of the manufacture of the device</td>
</tr>
</tbody></table>
</body></html>
"""

ALERT_HTML = """
<html><body><table><thead><tr>
<th>Import Alert Number</th><th>Import Alert Type</th><th>Publish Date</th><th>Import Alert Name</th>
</tr></thead><tbody>
<tr><td>76-01</td><td>DWPE</td><td>11/06/2026</td>
<td><a href="importalert_224.html">Detention Without Physical Examination Of Medical Instruments from Pakistan</a></td></tr>
<tr><td>99-49</td><td>DWPE</td><td>06/22/2026</td>
<td><a href="importalert_1182.html">Detention Without Physical Examination of Devices Without a Unique Device Identifier</a></td></tr>
</tbody></table></body></html>
"""


class FakeClient:
    """Mimics the tiny surface the connectors use: one GET returning canned bytes."""

    def __init__(self, payloads: dict[str, bytes]) -> None:
        self.payloads = payloads
        self.calls: list[tuple[str, dict]] = []
        self._requests = 0

    def get(self, url: str, *, params=None, headers=None, accept="application/json"):  # noqa: ANN001
        self.calls.append((url, dict(params or {})))
        self._requests += 1
        body = self.payloads.get(url)
        if body is None:
            return ev_base.HttpResult(url, "GET", 404, b"", {}, 1, 1, error="HTTP 404 Not Found")
        return ev_base.HttpResult(url, "GET", 200, body, {}, 1, 1)

    def requests_made(self) -> int:
        return self._requests


class RecallConnectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.index = ev_identity.CompanyIndex.from_config()
        self.evidence = recall.to_evidence(RECALL_ITEM, fetched_at=FETCHED_AT, company_index=self.index)

    def test_evidence_validates(self) -> None:
        self.assertEqual(ev_schema.validate_evidence(self.evidence), [])

    def test_time_semantics_separate_event_from_public(self) -> None:
        block = self.evidence["time"]
        self.assertEqual(block["event_at"], "2003-10-27")
        self.assertEqual(block["source_public_at"], "2003-10-29")
        self.assertNotEqual(block["event_at"], block["source_public_at"])
        self.assertEqual(block["source_public_at_quality"], "day")
        # first_observed_at is the fetch clock, never a back-filled history
        self.assertEqual(block["first_observed_at"], block["fetched_at"])

    def test_identifiers_and_canonical_key(self) -> None:
        schemes = {ident["scheme"] for ident in self.evidence["identifiers"]}
        self.assertIn("recall_number", schemes)
        self.assertIn("accession", schemes)
        # k_numbers are kept in normalized but deliberately not promoted: a 510(k)
        # outranks recall_number in canonical_key and would merge distinct recalls.
        self.assertNotIn("510k", schemes)
        self.assertEqual(self.evidence["normalized"]["k_numbers"], ["K020436"])
        self.assertEqual(self.evidence["canonical_key"], "recall_number:Z-0001-04")

    def test_firm_resolution_is_confirmed_not_candidate(self) -> None:
        ref = self.evidence["entity_refs"][0]
        self.assertEqual(ref["resolved_key"], "medtronic")
        self.assertEqual(ref["method"], "exact_alias")
        self.assertGreaterEqual(ref["confidence"], 0.9)

    def test_interpretation_warning_present(self) -> None:
        warning = self.evidence["normalized"]["interpretation_warning"].lower()
        self.assertIn("not the underlying failure rate", warning)
        self.assertIn("recall", warning)
        self.assertIn("enforcement action", warning)

    def test_evidence_id_is_idempotent_but_content_hash_tracks_content(self) -> None:
        again = recall.to_evidence(RECALL_ITEM, fetched_at=FETCHED_AT, company_index=self.index)
        self.assertEqual(again["evidence_id"], self.evidence["evidence_id"])
        self.assertEqual(again["content_hash"], self.evidence["content_hash"])
        changed = dict(RECALL_ITEM, reason_for_recall="different reason")
        changed_evidence = recall.to_evidence(changed, fetched_at=FETCHED_AT, company_index=self.index)
        self.assertEqual(changed_evidence["evidence_id"], self.evidence["evidence_id"])
        self.assertNotEqual(changed_evidence["content_hash"], self.evidence["content_hash"])

    def test_missing_identity_returns_none(self) -> None:
        self.assertIsNone(recall.to_evidence({"recalling_firm": "X"}, fetched_at=FETCHED_AT))

    def test_collect_uses_client_and_normalises(self) -> None:
        payload = {"meta": {"results": {"total": 1}, "last_updated": "2026-11-05"}, "results": [RECALL_ITEM]}
        client = FakeClient({recall.API_URL: json.dumps(payload).encode()})
        records = recall.collect(client, limit=1, search="recalling_firm:medtronic", fetched_at=FETCHED_AT)
        self.assertEqual(len(records), 1)
        self.assertEqual(client.calls[0][1]["limit"], 1)
        self.assertIn("search", client.calls[0][1])


class MaudeConnectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.index = ev_identity.CompanyIndex.from_config()
        self.evidence = maude.to_evidence(MAUDE_ITEM, fetched_at=FETCHED_AT, company_index=self.index)

    def test_evidence_validates(self) -> None:
        self.assertEqual(ev_schema.validate_evidence(self.evidence), [])

    def test_three_maude_dates_are_distinct_facts(self) -> None:
        block = self.evidence["time"]
        self.assertEqual(block["event_at"], "2024-01-15")  # date_of_event
        self.assertEqual(block["source_public_at"], "2024-02-01")  # date_received
        self.assertNotEqual(block["event_at"], block["source_public_at"])
        self.assertIn("date_received", block["notes"])
        normalized = self.evidence["normalized"]
        self.assertEqual(normalized["date_report"], "20240120")
        self.assertEqual(normalized["date_added"], "20240210")

    def test_nested_manufacturer_is_used_and_resolved(self) -> None:
        ref = self.evidence["entity_refs"][0]
        self.assertEqual(ref["resolved_key"], "medtronic")
        self.assertEqual(self.evidence["normalized"]["device_manufacturer_names"], ["MEDTRONIC MINIMED"])

    def test_passive_reporting_warning_is_blunt(self) -> None:
        warning = self.evidence["normalized"]["interpretation_warning"].lower()
        self.assertIn("not an incidence rate", warning)
        self.assertIn("reporting incentives", warning)
        self.assertIn("no denominator", warning)
        self.assertIn("never interpret a count", warning)

    def test_missing_report_key_returns_none(self) -> None:
        self.assertIsNone(maude.to_evidence({"event_type": "Injury"}, fetched_at=FETCHED_AT))

    def test_annual_histogram_aggregates_day_buckets(self) -> None:
        buckets = [
            {"value": "20240101", "count": 2},
            {"value": "20240102", "count": 3},
            {"value": "20231231", "count": 1},
        ]
        self.assertEqual(maude.annual_histogram(buckets), {"2023": 1, "2024": 5})

    def test_count_by_reads_exact_term_and_time_buckets(self) -> None:
        payload = {"results": [{"term": "MEDTRONIC MINIMED", "count": 7}, {"time": "20240102", "count": 4}]}
        client = FakeClient({maude.API_URL: json.dumps(payload).encode()})
        buckets, meta = maude.count_by(client, "device.manufacturer_d_name.exact", search="x")
        self.assertEqual([b["value"] for b in buckets], ["MEDTRONIC MINIMED", "20240102"])
        self.assertEqual(meta["bucket_sum"], 11)
        self.assertEqual(client.calls[0][1]["count"], "device.manufacturer_d_name.exact")


class ShortageConnectorTests(unittest.TestCase):
    def test_both_real_tables_parse(self) -> None:
        parsed = shortages.parse_shortages_page(SHORTAGE_HTML)
        self.assertEqual(parsed["table_count"], 2)
        self.assertEqual(len(parsed["shortages"]), 1)
        self.assertEqual(len(parsed["discontinuances"]), 2)
        first = parsed["shortages"][0]
        self.assertEqual(first["product_code"], "HBA")
        self.assertEqual(first["product_code_description"], "Neurosurgical pattie")
        self.assertEqual(first["date_posted"], "2026/05/06")
        disc = parsed["discontinuances"][0]
        self.assertEqual(disc["product_code"], "GKZ")
        self.assertEqual(disc["manufacturer_name"], "Medtronic Puerto Rico Operations Co.")
        self.assertEqual(disc["date_posted"], "10/26/2026")

    def test_evidence_is_valid_and_has_no_invented_event_date(self) -> None:
        records = shortages.parse_to_evidence(
            SHORTAGE_HTML.encode("utf-8"),
            fetched_at=FETCHED_AT,
            company_index=ev_identity.CompanyIndex.from_config(),
        )
        self.assertEqual(len(records), 3)
        for record in records:
            self.assertEqual(ev_schema.validate_evidence(record), [])
            self.assertEqual(record["kind"], "shortage")
            self.assertEqual(record["time"]["event_at"], "")
            self.assertEqual(record["time"]["source_public_at_quality"], "day")
        shortage_record = next(r for r in records if r["normalized"]["record_type"] == "shortage")
        self.assertEqual(shortage_record["time"]["source_public_at"], "2026-05-06")

    def test_discontinuance_firm_link_confirmed_and_other_firm_not(self) -> None:
        records = shortages.parse_to_evidence(
            SHORTAGE_HTML.encode("utf-8"),
            fetched_at=FETCHED_AT,
            company_index=ev_identity.CompanyIndex.from_config(),
        )
        discons = [r for r in records if r["normalized"]["record_type"] == "discontinuance"]
        medtronic = next(r for r in discons if "Medtronic" in r["normalized"]["manufacturer_name"])
        other = next(r for r in discons if "Unrelated" in r["normalized"]["manufacturer_name"])
        self.assertEqual(medtronic["entity_refs"][0]["resolved_key"], "medtronic")
        self.assertEqual(medtronic["entity_refs"][0]["method"], "exact_alias")
        self.assertEqual(other["entity_refs"][0]["method"], "none")

    def test_shortage_rows_cannot_be_firm_linked(self) -> None:
        parsed = shortages.parse_shortages_page(SHORTAGE_HTML)
        self.assertNotIn("manufacturer_name", parsed["shortages"][0])

    def test_product_code_parser(self) -> None:
        self.assertEqual(shortages.parse_product_code("GKZ  (COUNTER, DIFFERENTIAL CELL)"), ("GKZ", "COUNTER, DIFFERENTIAL CELL"))
        self.assertEqual(shortages.parse_product_code("IZL--"), ("", "IZL--"))


class ImportAlertConnectorTests(unittest.TestCase):
    def test_index_parses_number_type_date_name_and_link(self) -> None:
        rows = alerts.parse_alert_index(ALERT_HTML)
        self.assertEqual(len(rows), 2)
        first = rows[0]
        self.assertEqual(first["alert_number"], "76-01")
        self.assertEqual(first["alert_type"], "DWPE")
        self.assertEqual(first["publish_date"], "11/06/2026")
        self.assertIn("Pakistan", first["alert_name"])
        self.assertEqual(first["detail_href"], "importalert_224.html")
        self.assertEqual(first["detail_id"], "224")

    def test_evidence_is_valid_with_unknown_event_date(self) -> None:
        records = alerts.parse_to_evidence(ALERT_HTML.encode("utf-8"), fetched_at=FETCHED_AT)
        self.assertEqual(len(records), 2)
        for record in records:
            self.assertEqual(ev_schema.validate_evidence(record), [])
            self.assertEqual(record["kind"], "import_alert")
            self.assertEqual(record["time"]["event_at"], "")
        self.assertEqual(records[0]["time"]["source_public_at"], "2026-11-06")
        self.assertEqual(records[0]["identifiers"][0]["scheme"], "import_alert_no")
        # The index has no company column; the record says so instead of implying a link.
        self.assertEqual(records[0]["entity_refs"], [])
        self.assertIn("not available", records[0]["normalized"]["firm_linkage"].lower())

    def test_firm_tokens_counted_as_text_only(self) -> None:
        html = "<html><body>MEDTRONIC MINIMED and Dräger and Shenzhen Mindray</body></html>"
        counts = alerts.count_firm_tokens(html)
        self.assertGreater(counts["medtronic"], 0)
        self.assertGreater(counts["mindray"], 0)
        self.assertGreater(counts["draeger"], 0)
        self.assertEqual(counts["philips"], 0)

    def test_device_keyword_subset_is_labelled(self) -> None:
        records = alerts.parse_to_evidence(ALERT_HTML.encode("utf-8"), fetched_at=FETCHED_AT)
        subset = alerts.device_alert_subset(records)
        self.assertEqual(len(subset), 2)  # both names contain 'device(s)'


class IdentityAndCommonTests(unittest.TestCase):
    def test_guard_demotes_alias_to_candidate(self) -> None:
        index = ev_identity.CompanyIndex.from_config()
        lighting = index.resolve("Philips Lighting")
        self.assertEqual(lighting["resolved_key"], "philips")
        self.assertEqual(lighting["method"], "candidate")
        self.assertLess(lighting["confidence"], 0.9)
        safety = index.resolve("Draeger Safety AG")
        self.assertEqual(safety["method"], "candidate")

    def test_confirmed_alias_for_all_five_firms(self) -> None:
        index = ev_identity.CompanyIndex.from_config()
        for name, expected in (
            ("Medtronic Puerto Rico Operations Co.", "medtronic"),
            ("GE HealthCare Technologies", "ge_healthcare"),
            ("Philips Medical Systems Nederland B.V.", "philips"),
            ("Dräger Medical Systems", "draeger"),
            ("Shenzhen Mindray Bio-Medical Electronics Co., Ltd.", "mindray"),
        ):
            ref = common.resolve_company(index, name)
            self.assertEqual(ref["resolved_key"], expected, name)
            self.assertEqual(ref["method"], "exact_alias", name)
            self.assertEqual(common.confirmed_firm_key(ref), expected)
            self.assertTrue(common.is_five_firm(ref))

    def test_candidate_is_never_confirmed_firm_key(self) -> None:
        index = ev_identity.CompanyIndex.from_config()
        ref = common.resolve_company(index, "Philips Lighting")
        self.assertEqual(ref["method"], "candidate")
        self.assertIsNone(common.confirmed_firm_key(ref))

    def test_year_and_clip_helpers(self) -> None:
        self.assertEqual(common.year_of("2003-10-29"), "2003")
        self.assertEqual(common.year_of("10/26/2026"), "2026")
        self.assertEqual(common.year_of("not a date"), "")
        self.assertEqual(common.clip(" abc "), "abc")
        self.assertTrue(common.clip("x" * 50, 10).endswith("…"))

    def test_html_table_parser_handles_entities_and_links(self) -> None:
        html = (
            "<table><tr><th>A</th><th>B</th></tr>"
            "<tr><td>1&nbsp;2</td><td><a href='x.html'>link</a></td></tr></table>"
        )
        tables = common.html_tables(html)
        self.assertEqual(tables[0]["headers"], ["A", "B"])
        self.assertEqual(tables[0]["rows"][0]["cells"][0], "1 2")
        self.assertIn("x.html", tables[0]["rows"][0]["hrefs"][1])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
