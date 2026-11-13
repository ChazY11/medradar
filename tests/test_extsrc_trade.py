"""Offline tests for the trade/patent external-source connectors.

No network.  Every fixture below is a *small handwritten* payload shaped exactly
like the live responses recorded under ``research/data_expansion/probes/`` (see
the sampled field names in the comments); nothing is read from disk except the
shipped company registry.

The point of these tests is not coverage theatre — it is to pin three
things that would silently corrupt research:

1. an aggregate record can never acquire a company link;
2. an aggregate record has no publication clock (``source_public_at`` unknown);
3. a company-level presence record is not a shipment value.
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

from medradar.external_sources import base, identity, schema
from medradar.external_sources.trade import eurostat_comext, uk_hmrc_trade, un_comtrade

FIXED = datetime(2026, 11, 9, 12, 0, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# A minimal stand-in for base.HttpClient: same ``get`` shape, canned payloads.
# --------------------------------------------------------------------------- #
class FakeClient:
    def __init__(self, routes: dict[str, object]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, dict]] = []

    def get(self, url, *, params=None, headers=None, accept="application/json"):
        self.calls.append((url, dict(params or {})))
        for fragment, payload in self.routes.items():
            if fragment in url:
                body = json.dumps(payload).encode("utf-8")
                return base.HttpResult(url, "GET", 200, body, {"content-type": "application/json"}, 1, 1)
        return base.HttpResult(url, "GET", 404, b"{}", {}, 1, 1, error="HTTP 404 Not Found")

    def requests_made(self) -> int:
        return len(self.calls)


# --------------------------------------------------------------------------- #
# UN Comtrade — field names copied from samples/un_comtrade/preview_9018.json
# --------------------------------------------------------------------------- #
COMTRADE_ROW = {
    "typeCode": "C",
    "freqCode": "A",
    "refYear": 2023,
    "refMonth": 52,
    "period": "2023",
    "reporterCode": 842,
    "flowCode": "M",
    "partnerCode": 0,
    "partner2Code": 0,
    "classificationCode": "H6",
    "cmdCode": "9018",
    "qtyUnitCode": -1,
    "qty": 0.0,
    "isQtyEstimated": True,
    "netWgt": None,
    "primaryValue": 37909230134.0,
    "cifvalue": 37909230134.0,
    "fobvalue": 37476154253.0,
    "partnerDesc": None,
    "reporterDesc": None,
}


class UnComtradeTests(unittest.TestCase):
    def test_normalize_flags_world_total_and_direction(self):
        row = un_comtrade.normalize_item(COMTRADE_ROW)
        self.assertEqual(row["reporter_code"], 842)
        self.assertEqual(row["partner_code"], 0)
        self.assertTrue(row["partner_is_world_total"])
        self.assertEqual(row["flow_direction"], "imports")
        self.assertEqual(row["hs_code"], "9018")
        self.assertEqual(row["data_class"], "country_level_aggregate")
        self.assertEqual(row["trade_value_usd"], 37909230134.0)

    def test_missing_values_stay_none_and_are_not_zeroed(self):
        row = un_comtrade.normalize_item(COMTRADE_ROW)
        self.assertIsNone(row["net_weight_kg"])  # the source sent null
        self.assertEqual(row["quantity"], 0.0)  # the source sent 0.0: keep it

    def test_to_evidence_is_valid_and_has_no_company_link(self):
        record = un_comtrade.to_evidence(COMTRADE_ROW, fetched_at=FIXED)
        self.assertEqual(schema.validate_evidence(record), [])
        self.assertEqual(record["kind"], "trade_aggregate")
        self.assertEqual(record["entity_refs"], [])
        self.assertIsNone(record["canonical_key"])  # aggregates are not de-duplicable

    def test_aggregate_has_no_publication_clock(self):
        record = un_comtrade.to_evidence(COMTRADE_ROW, fetched_at=FIXED)
        time_block = record["time"]
        self.assertEqual(time_block["event_at"], "2023-12-31")  # derived period anchor
        self.assertEqual(time_block["source_public_at"], "")  # never fabricated
        self.assertEqual(time_block["source_public_at_quality"], "unknown")
        self.assertEqual(time_block["first_observed_at"], time_block["fetched_at"])

    def test_evidence_id_is_deterministic(self):
        first = un_comtrade.to_evidence(COMTRADE_ROW, fetched_at=FIXED)
        second = un_comtrade.to_evidence(COMTRADE_ROW, fetched_at=FIXED)
        self.assertEqual(first["evidence_id"], second["evidence_id"])
        self.assertIn("reporter=842", first["source_record_id"])
        self.assertIn("hs=9018", first["source_record_id"])

    def test_collect_is_bounded_and_never_links_entities(self):
        client = FakeClient({"preview/C/A/HS": {"count": 1, "data": [COMTRADE_ROW]}})
        records = un_comtrade.collect(client, cmd_codes=("9018", "9022"), limit=1)
        self.assertEqual(len(records), 1)
        self.assertEqual(client.requests_made(), 1)  # stops as soon as the limit is hit
        self.assertEqual(records[0]["entity_refs"], [])

        client = FakeClient({"preview/C/A/HS": {"count": 1, "data": [COMTRADE_ROW]}})
        records = un_comtrade.collect(client, cmd_codes=("9018", "9022", "9402"), limit=50)
        self.assertEqual(len(records), 3)
        self.assertEqual(client.requests_made(), 3)
        for record in records:
            self.assertEqual(record["entity_refs"], [])
            self.assertEqual(schema.validate_evidence(record), [])

    def test_collect_survives_a_failed_request(self):
        client = FakeClient({})  # every call 404s
        self.assertEqual(un_comtrade.collect(client, cmd_codes=("9018",), limit=5), [])


# --------------------------------------------------------------------------- #
# Eurostat Comext — JSON-stat shape copied from
# samples/eurostat_comext/hs9018_de_imports_2023.json
# --------------------------------------------------------------------------- #
JSONSTAT = {
    "version": "2.0",
    "class": "dataset",
    "label": "EU trade since 1988 by HS2-4-6 and CN8",
    "updated": "2026-10-16T11:00:00+0200",
    "value": {"0": 2682137903},
    "id": ["freq", "reporter", "partner", "product", "flow", "indicators", "time"],
    "size": [2, 1, 1, 1, 1, 1, 1],
    "dimension": {
        "freq": {"label": "Frequency", "category": {"index": {"A": 0, "M": 1},
                                                    "label": {"A": "Annual", "M": "Monthly"}}},
        "reporter": {"label": "REPORTER", "category": {"index": {"DE": 0},
                                                       "label": {"DE": "Germany"}}},
        "partner": {"label": "PARTNER", "category": {"index": {"US": 0}, "label": {"US": "United States"}}},
        "product": {"label": "PRODUCT", "category": {"index": {"9018": 0},
                                                     "label": {"9018": "Instruments and appliances used in medical sciences"}}},
        "flow": {"label": "FLOW", "category": {"index": {"1": 0}, "label": {"1": "IMPORT"}}},
        "indicators": {"label": "INDICATORS",
                       "category": {"index": {"VALUE_IN_EUROS": 0}, "label": {"VALUE_IN_EUROS": "VALUE_IN_EUROS"}}},
        "time": {"label": "TIME_PERIOD", "category": {"index": {"2023": 0}, "label": {"2023": "2023"}}},
    },
    "positions-with-no-data": {"freq": [1]},
}


class EurostatComextTests(unittest.TestCase):
    def test_flatten_keeps_codes_and_labels(self):
        cells = eurostat_comext.flatten_jsonstat(JSONSTAT)
        self.assertEqual(len(cells), 1)
        cell = cells[0]
        self.assertEqual(cell["freq_code"], "A")  # position 0 is Annual, not Monthly
        self.assertEqual(cell["freq"], "Annual")
        self.assertEqual(cell["reporter_code"], "DE")
        self.assertEqual(cell["product_code"], "9018")
        self.assertEqual(cell["flow_code"], "1")
        self.assertEqual(cell["value"], 2682137903)

    def test_flatten_is_sparse_and_invents_nothing(self):
        payload = json.loads(json.dumps(JSONSTAT))
        payload["value"] = {}  # nothing published
        self.assertEqual(eurostat_comext.flatten_jsonstat(payload), [])

        payload = json.loads(json.dumps(JSONSTAT))
        payload["value"] = {"1": 42.0}  # the monthly cell, which has data
        cells = eurostat_comext.flatten_jsonstat(payload)
        self.assertEqual(len(cells), 1)
        self.assertEqual(cells[0]["freq_code"], "M")
        self.assertEqual(cells[0]["value"], 42.0)

    def test_normalize_observation_labels_units(self):
        observation = eurostat_comext.normalize_observation(eurostat_comext.flatten_jsonstat(JSONSTAT)[0])
        self.assertEqual(observation["product_code"], "9018")
        self.assertIn("medical", observation["product_description"])
        self.assertEqual(observation["flow_direction"], "imports")
        self.assertEqual(observation["currency"], "EUR")
        self.assertEqual(observation["period"], "2023")

    def test_to_evidence_is_valid_aggregate_without_company(self):
        record = eurostat_comext.to_evidence(
            eurostat_comext.flatten_jsonstat(JSONSTAT)[0], fetched_at=FIXED
        )
        self.assertEqual(schema.validate_evidence(record), [])
        self.assertEqual(record["kind"], "trade_aggregate")
        self.assertEqual(record["entity_refs"], [])
        self.assertTrue(record["source_record_id"].startswith("DS-045409:"))
        self.assertEqual(record["time"]["source_public_at"], "")
        self.assertEqual(record["time"]["source_public_at_quality"], "unknown")
        self.assertEqual(record["time"]["event_at"], "2023-12-31")

    def test_collect_makes_one_request_per_product(self):
        client = FakeClient({"comext/dissemination": JSONSTAT})
        records = eurostat_comext.collect(client, products=("9018", "9402"), limit=50)
        self.assertEqual(client.requests_made(), 2)
        self.assertEqual(len(records), 2)
        for record in records:
            self.assertEqual(record["kind"], "trade_aggregate")
            self.assertEqual(record["entity_refs"], [])

    def test_collect_respects_limit(self):
        client = FakeClient({"comext/dissemination": JSONSTAT})
        records = eurostat_comext.collect(client, products=("9018", "9402", "9022"), limit=1)
        self.assertEqual(len(records), 1)
        self.assertEqual(client.requests_made(), 1)


# --------------------------------------------------------------------------- #
# HMRC UK Trade Info — rows copied from samples/uk_hmrc_trade/*.json
# --------------------------------------------------------------------------- #
MEDTRONIC_TRADER = {"TraderId": 213902, "CompanyName": "MEDTRONIC VASCULAR GALWAY UNLIMITEDCOMPANY",
                    "PostCode": "AB10 1ZP"}
MEDTRONIC_LTD = {"TraderId": 243358, "CompanyName": "MEDTRONIC LIMITED", "PostCode": "WD18 8WW"}
YEARLY_ROW = {
    "TraderId": 213902,
    "CommodityId": 90183900,
    "Year": 2023,
    "TradeTypeId": 0,
    "ImportMonths": "July 2023,September 2023,April 2023",
    "ExportMonths": "June 2023,September 2023",
}
OTS_ROW = {"MonthId": 201301, "FlowTypeId": 3, "GovRegionId": 1, "CountryId": 1,
           "CommoditySitc2Id": 0, "Value": 245071.0, "NetMass": 557.0}


class HmrcTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.index = identity.CompanyIndex.from_config()

    def test_parse_month_list(self):
        self.assertEqual(
            uk_hmrc_trade.parse_month_list("December 2023,October 2023,November 2023"),
            [12, 11, 10],
        )
        self.assertEqual(uk_hmrc_trade.parse_month_list(""), [])
        self.assertEqual(uk_hmrc_trade.parse_month_list("garbage,May 2023"), [5])

    def test_normalize_presence_records_absence_of_value(self):
        presence = uk_hmrc_trade.normalize_presence(MEDTRONIC_TRADER, YEARLY_ROW)
        self.assertEqual(presence["trader_id"], "213902")
        self.assertEqual(presence["cn8_code"], "90183900")
        self.assertEqual(presence["year"], 2023)
        self.assertEqual(presence["import_months"], [9, 7, 4])
        self.assertEqual(presence["export_months"], [9, 6])
        self.assertTrue(presence["has_import"])
        self.assertTrue(presence["has_export"])
        self.assertFalse(presence["value_available"])
        self.assertFalse(presence["consignment_available"])
        self.assertTrue(presence["is_hmrc_placeholder_address"])  # AB10 1ZP is HMRC's own address

    def test_hq_name_is_recognised_as_placeholder(self):
        presence = uk_hmrc_trade.normalize_presence(MEDTRONIC_LTD, YEARLY_ROW)
        self.assertFalse(presence["is_hmrc_placeholder_address"])

    def test_link_company_confirmed_alias(self):
        link = uk_hmrc_trade.link_company(self.index, "MEDTRONIC LIMITED")
        self.assertEqual(link["resolved_key"], "medtronic")
        self.assertIn(link["method"], schema.CONFIRMED_METHODS)
        self.assertGreaterEqual(link["confidence"], 0.9)

    def test_link_company_mindray(self):
        link = uk_hmrc_trade.link_company(self.index, "MINDRAY UK LTD")
        self.assertEqual(link["resolved_key"], "mindray")
        self.assertIn(link["method"], schema.CONFIRMED_METHODS)

    def test_non_medical_division_is_demoted_to_candidate(self):
        link = uk_hmrc_trade.link_company(self.index, "PHILIPS IN LIGHTING LTD")
        self.assertEqual(link["resolved_key"], "philips")
        self.assertEqual(link["method"], "candidate")
        self.assertLess(link["confidence"], 0.9)
        self.assertEqual(link["evidence"]["trade_demotion_guard"], "LIGHTING")

    def test_draeger_safety_is_not_a_confirmed_medical_link(self):
        link = uk_hmrc_trade.link_company(self.index, "DRAEGER SAFETY UK LTD")
        self.assertEqual(link["resolved_key"], "draeger")
        self.assertEqual(link["method"], "candidate")

    def test_presence_evidence_is_valid_company_record(self):
        record = uk_hmrc_trade.to_evidence(
            {"record_type": "trader_commodity_year_presence",
             "trader": MEDTRONIC_TRADER, "presence": YEARLY_ROW},
            fetched_at=FIXED,
            company_index=self.index,
        )
        self.assertEqual(schema.validate_evidence(record), [])
        self.assertEqual(record["kind"], "trade_by_trader")
        self.assertEqual(len(record["entity_refs"]), 1)
        self.assertEqual(record["entity_refs"][0]["resolved_key"], "medtronic")
        self.assertEqual(record["normalized"]["data_class"], "company_level_presence")
        self.assertFalse(record["normalized"]["value_available"])
        self.assertIn("trader=213902", record["source_record_id"])
        schemes = {ident["scheme"] for ident in record["identifiers"]}
        self.assertEqual(schemes, {"hmrc_trader_id", "cn8"})

    def test_presence_has_no_value_and_no_publication_clock(self):
        record = uk_hmrc_trade.to_evidence(
            {"record_type": "trader_commodity_year_presence",
             "trader": MEDTRONIC_TRADER, "presence": YEARLY_ROW},
            fetched_at=FIXED,
            company_index=self.index,
        )
        self.assertEqual(record["time"]["event_at"], "2023-12-31")
        self.assertEqual(record["time"]["source_public_at"], "")
        self.assertEqual(record["time"]["source_public_at_quality"], "unknown")
        self.assertNotIn("value", record["normalized"])
        self.assertNotIn("value_gbp", record["normalized"])

    def test_ots_row_is_an_aggregate_without_company_links(self):
        record = uk_hmrc_trade.to_evidence(
            {"record_type": "ots_month_aggregate", "aggregate": OTS_ROW},
            fetched_at=FIXED,
            company_index=self.index,
        )
        self.assertEqual(schema.validate_evidence(record), [])
        self.assertEqual(record["kind"], "trade_aggregate")
        self.assertEqual(record["entity_refs"], [])
        self.assertEqual(record["normalized"]["value_gbp"], 245071.0)
        self.assertEqual(record["time"]["source_public_at"], "")

    def test_unknown_record_type_is_rejected(self):
        with self.assertRaises(schema.EvidenceError):
            uk_hmrc_trade.to_evidence({"record_type": "something_else"}, fetched_at=FIXED)

    def test_collect_is_bounded(self):
        client = FakeClient({
            "/Trader": {"value": [MEDTRONIC_TRADER]},
            "/YearlyTrade": {"value": [YEARLY_ROW]},
        })
        records = uk_hmrc_trade.collect(
            client, fragments=("MEDTRONIC",), year=2023, limit=10, company_index=self.index
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(client.requests_made(), 2)  # one trader search + one year query
        self.assertEqual(records[0]["kind"], "trade_by_trader")


class ClassSeparationTests(unittest.TestCase):
    """The rule the whole trade section rests on."""

    def test_aggregate_records_never_carry_entity_links(self):
        aggregates = [
            un_comtrade.to_evidence(COMTRADE_ROW, fetched_at=FIXED),
            eurostat_comext.to_evidence(eurostat_comext.flatten_jsonstat(JSONSTAT)[0], fetched_at=FIXED),
            uk_hmrc_trade.to_evidence(
                {"record_type": "ots_month_aggregate", "aggregate": OTS_ROW},
                fetched_at=FIXED,
                company_index=identity.CompanyIndex.from_config(),
            ),
        ]
        for record in aggregates:
            self.assertEqual(record["kind"], "trade_aggregate")
            self.assertEqual(record["entity_refs"], [])
            self.assertIsNone(record["canonical_key"])
            self.assertEqual(schema.validate_evidence(record), [])

    def test_company_presence_and_aggregate_are_different_kinds(self):
        index = identity.CompanyIndex.from_config()
        presence = uk_hmrc_trade.to_evidence(
            {"record_type": "trader_commodity_year_presence",
             "trader": MEDTRONIC_TRADER, "presence": YEARLY_ROW},
            fetched_at=FIXED,
            company_index=index,
        )
        aggregate = uk_hmrc_trade.to_evidence(
            {"record_type": "ots_month_aggregate", "aggregate": OTS_ROW},
            fetched_at=FIXED,
            company_index=index,
        )
        self.assertNotEqual(presence["kind"], aggregate["kind"])
        self.assertTrue(presence["entity_refs"])
        self.assertFalse(aggregate["entity_refs"])

    def test_presence_records_are_not_independent_of_each_other_by_accident(self):
        index = identity.CompanyIndex.from_config()
        first = uk_hmrc_trade.to_evidence(
            {"record_type": "trader_commodity_year_presence",
             "trader": MEDTRONIC_TRADER, "presence": YEARLY_ROW},
            fetched_at=FIXED, company_index=index,
        )
        other = dict(YEARLY_ROW)
        other["CommodityId"] = 30061010
        second = uk_hmrc_trade.to_evidence(
            {"record_type": "trader_commodity_year_presence",
             "trader": MEDTRONIC_TRADER, "presence": other},
            fetched_at=FIXED, company_index=index,
        )
        self.assertNotEqual(first["evidence_id"], second["evidence_id"])
        self.assertTrue(schema.is_independent(first, second))


if __name__ == "__main__":
    unittest.main()
