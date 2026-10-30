"""Offline unit tests for the openFDA device collector (``medradar.collect_device``).

Nothing here touches the network:

* normalisation / mapping tests use synthetic openFDA records;
* pagination, retries and window splitting run against a scripted fake fetcher;
* the end-to-end collection test replays the static fixtures in
  ``tests/fixtures/device`` (regenerate with ``python tests/fixtures/device/_generate.py``).
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from medradar import collect_device as cd
from medradar.config import load_companies, load_tracks
from medradar.db import DB, make_event_id
from medradar.http import BudgetExceeded, Fetcher, HttpError, NotFound

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "device"
FIXTURE_DAY = date(2026, 10, 30)  # must match tests/fixtures/device/_generate.py


class _NoSleepMixin:
    """The retry path sleeps between attempts; tests must not."""

    def setUp(self) -> None:
        super().setUp()
        patcher = mock.patch.object(cd, "_sleep", lambda seconds: None)
        patcher.start()
        self.addCleanup(patcher.stop)


class FakeFetcher:
    """Minimal ``Fetcher`` stand-in driven by a ``handler(url, params, refresh, n)``."""

    def __init__(self, handler) -> None:
        self.handler = handler
        self.calls: list[dict] = []
        self.stats = {"requests": 0, "cache_hits": 0, "retries": 0, "errors": 0}

    def get_json(self, url, params=None, refresh=False, **kwargs):
        params = dict(params or {})
        self.calls.append({"url": url, "params": params, "refresh": refresh})
        self.stats["requests"] += 1
        return self.handler(url, params, refresh, len(self.calls))


def _page(total: int, skip: int, limit: int, id_prefix: str = "r") -> dict:
    n = max(0, min(limit, total - skip))
    return {
        "meta": {"results": {"total": total, "skip": skip, "limit": limit}},
        "results": [{"id": f"{id_prefix}-{skip + i}"} for i in range(n)],
    }


# --------------------------------------------------------------------------- normalise
class Normalize510kTests(unittest.TestCase):
    def test_event_fields(self) -> None:
        record = {
            "k_number": "K250001",
            "applicant": "MEDTRONIC MINIMED",
            "device_name": "Pulsed Field Ablation Catheter",
            "product_code": "OAD",
            "decision_date": "2025-03-14",
            "date_received": "2025-01-02",
            "decision_code": "SESE",
            "decision_description": "Substantially Equivalent",
            "clearance_type": "Traditional",
            "advisory_committee_description": "Cardiovascular",
            "country_code": "US",
        }
        event = cd.normalize_510k(
            record,
            company_key="medtronic",
            track_id="ep_pfa",
            track_zh="电生理与脉冲场消融",
            as_of="2026-10-30",
        )
        self.assertIsNotNone(event)
        event = dict(event)
        self.assertEqual(event["event_id"], make_event_id("openfda_device_510k", "510k", "K250001"))
        self.assertEqual(event["source"], "openfda_device_510k")
        self.assertEqual(event["kind"], "510k")
        self.assertEqual(event["event_date"], "2025-03-14")  # decision date, not received date
        self.assertEqual(event["as_of"], "2026-10-30")
        self.assertEqual(event["company_key"], "medtronic")
        self.assertEqual(event["applicant_raw"], "MEDTRONIC MINIMED")
        self.assertEqual(event["track_id"], "ep_pfa")
        self.assertEqual(event["product_code"], "OAD")
        self.assertIn("K250001", event["url"])
        self.assertIn("电生理与脉冲场消融", event["summary"])
        self.assertIn("OAD", event["summary"])

    def test_event_id_is_deterministic(self) -> None:
        record = {"k_number": "K999999", "applicant": "X", "decision_date": "2025-01-01"}
        first = cd.normalize_510k(record, company_key=None, track_id=None, as_of="2026-10-30")
        second = cd.normalize_510k(record, company_key="medtronic", track_id="ep_pfa", as_of="2026-10-31")
        self.assertEqual(first["event_id"], second["event_id"])

    def test_missing_k_number_is_skipped(self) -> None:
        self.assertIsNone(cd.normalize_510k({"applicant": "X"}, company_key=None, track_id=None))

    def test_missing_decision_date_falls_back_to_date_received(self) -> None:
        event = cd.normalize_510k(
            {"k_number": "K1", "date_received": "2025-02-02"},
            company_key=None,
            track_id=None,
            as_of="2026-10-30",
        )
        self.assertEqual(event["event_date"], "2025-02-02")

    def test_payload_priority_survives_truncation(self) -> None:
        record = {
            "k_number": "K250001",
            "applicant": "MEDTRONIC",
            "device_name": "Catheter",
            "openfda": {"registration_number": ["r" * 40] * 500},
        }
        event = cd.normalize_510k(record, company_key=None, track_id=None)
        self.assertLessEqual(len(event["payload"]), cd.PAYLOAD_LIMIT)
        self.assertIn('"k_number": "K250001"', event["payload"])


class NormalizePmaTests(unittest.TestCase):
    def test_original_and_supplement_are_distinct_events(self) -> None:
        original = {
            "pma_number": "P250001",
            "supplement_number": "",
            "applicant": "Edwards Lifesciences",
            "product_code": "DHT",
            "trade_name": "Test Valve",
            "decision_date": "2025-06-11",
            "decision_code": "APPR",
        }
        supplement = dict(original, supplement_number="S001", decision_date="2025-07-09")
        first = cd.normalize_pma(original, company_key="edwards_lifesciences", track_id="structural_heart")
        second = cd.normalize_pma(supplement, company_key="edwards_lifesciences", track_id="structural_heart")
        self.assertNotEqual(first["event_id"], second["event_id"])
        self.assertEqual(first["event_id"], make_event_id("openfda_device_pma", "pma", "P250001", ""))
        self.assertEqual(second["event_id"], make_event_id("openfda_device_pma", "pma", "P250001", "S001"))
        self.assertEqual(second["event_date"], "2025-07-09")
        self.assertIn("S001", second["summary"])

    def test_missing_pma_number_is_skipped(self) -> None:
        self.assertIsNone(cd.normalize_pma({"applicant": "X"}, company_key=None, track_id=None))


class NormalizeRecallTests(unittest.TestCase):
    def test_classification_date_wins_over_posted_date(self) -> None:
        record = {
            "cfres_id": "99001",
            "recalling_firm": "PHILIPS MEDICAL SYSTEMS",
            "product_description": "Ultrasound failure",
            "reason_for_recall": "Software",
            "event_date_posted": "2025-02-10",
            "center_classification_date": "2025-02-05",
        }
        event = cd.normalize_recall(record, company_key="philips", track_id=None)
        self.assertEqual(event["event_date"], "2025-02-05")
        self.assertEqual(event["kind"], "device_recall")
        self.assertEqual(event["source"], "openfda_device_recall")
        self.assertEqual(event["applicant_raw"], "PHILIPS MEDICAL SYSTEMS")
        self.assertIn("99001", event["payload"])

    def test_posted_date_is_used_when_real_schema_has_no_classification_date(self) -> None:
        record = {
            "cfres_id": "99002",
            "recalling_firm": "X",
            "event_date_posted": "2025-08-01",
            "event_date_initiated": "2025-07-15",
        }
        event = cd.normalize_recall(record, company_key=None, track_id=None)
        self.assertEqual(event["event_date"], "2025-08-01")

    def test_initiated_date_is_last_resort(self) -> None:
        event = cd.normalize_recall(
            {"cfres_id": "99003", "event_date_initiated": "2025-07-15"}, company_key=None, track_id=None
        )
        self.assertEqual(event["event_date"], "2025-07-15")

    def test_missing_date_is_kept_with_empty_event_date(self) -> None:
        event = cd.normalize_recall({"cfres_id": "99004", "recalling_firm": "X"}, company_key=None, track_id=None)
        self.assertEqual(event["event_date"], "")

    def test_missing_identity_is_skipped(self) -> None:
        self.assertIsNone(cd.normalize_recall({"recalling_firm": "X"}, company_key=None, track_id=None))

    def test_payload_keeps_requested_recall_fields(self) -> None:
        record = {
            "cfres_id": "99005",
            "recalling_firm": "PHILIPS",
            "product_description": "Device",
            "product_code": "QQQ",
            "reason_for_recall": "Reason",
            "root_cause_description": "Software",
            "recall_status": "Open, Classified",
            "product_res_number": "Z-1-2025",
            "res_event_number": "95005",
            "k_numbers": ["K1"],
            "code_info": "x" * 9000,  # would otherwise push the priority keys past 4k
        }
        event = cd.normalize_recall(record, company_key=None, track_id=None)
        payload = event["payload"]
        self.assertLessEqual(len(payload), cd.PAYLOAD_LIMIT)
        for key in (
            "root_cause_description",
            "recall_status",
            "product_res_number",
            "res_event_number",
            "k_numbers",
        ):
            self.assertIn(f'"{key}"', payload)


# ------------------------------------------------------------------------ code mapping
class ProductCodeMappingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = load_tracks("device")
        # The shipped config file is a generated artefact; never let it leak into mapping
        # expectations by building from synthetic records only.
        self.assertEqual(self.registry.get("ep_pfa")["name_zh"], "电生理与脉冲场消融")

    def _map(self, records, existing=None):
        return cd.build_product_code_map(records, self.registry, existing)

    def test_device_name_wins_over_definition(self) -> None:
        mapping, _ = self._map(
            [
                {
                    "product_code": "AAA",
                    "device_name": "Dental Implant System",
                    "definition": "Software for clinical decision support.",
                }
            ]
        )
        self.assertEqual(mapping, {"AAA": "dental"})

    def test_definition_is_used_only_when_device_name_has_no_keyword(self) -> None:
        mapping, stats = self._map(
            [
                {
                    "product_code": "BBB",
                    "device_name": "Pierced Ear Cleaning Tray",
                    "definition": "Software for clinical decision support.",
                }
            ]
        )
        self.assertEqual(mapping, {"BBB": "medical_ai"})
        self.assertEqual(stats["definition_keyword"], 1)

    def test_word_order_does_not_matter(self) -> None:
        mapping, _ = self._map(
            [{"product_code": "CCC", "device_name": "Catheter, Ablation, Cardiac", "definition": ""}]
        )
        self.assertEqual(mapping, {"CCC": "ep_pfa"})

    def test_naive_plurals_match(self) -> None:
        mapping, _ = self._map([{"product_code": "DDD", "device_name": "Stents, Coronary", "definition": ""}])
        self.assertEqual(mapping, {"DDD": "coronary"})

    def test_ambiguous_longest_keyword_is_left_unmapped(self) -> None:
        mapping, _ = self._map(
            [{"product_code": "EEE", "device_name": "Widget", "definition": "Endoscope pacemaker"}]
        )
        self.assertEqual(mapping, {})

    def test_manual_rule_beats_keyword_match(self) -> None:
        mapping, stats = self._map(
            [{"product_code": "FFF", "device_name": "System, Ultrasound, Software", "definition": ""}]
        )
        # "ULTRASOUND" is longer than "SOFTWARE", but the code describes SaMD.
        self.assertEqual(mapping, {"FFF": "medical_ai"})
        self.assertEqual(stats["manual"], 1)

    def test_existing_overlay_wins_and_invalid_tracks_are_ignored(self) -> None:
        mapping, stats = self._map(
            [{"product_code": "OAD", "device_name": "Pulsed Field Ablation System", "definition": ""}],
            existing={"OAD": "dental", "BAD": "not_a_track"},
        )
        self.assertEqual(mapping, {"OAD": "dental"})
        self.assertNotIn("BAD", mapping)
        self.assertEqual(stats["existing_override"], 1)

    def test_existing_overlay_preserves_hand_added_codes(self) -> None:
        mapping, stats = self._map(
            [{"product_code": "OAD", "device_name": "Pulsed Field Ablation System", "definition": ""}],
            existing={"ZZZ": "ep_pfa"},
        )
        self.assertEqual(mapping, {"OAD": "ep_pfa", "ZZZ": "ep_pfa"})
        self.assertEqual(stats["existing_new"], 1)

    def test_written_file_is_flat_sorted_and_compact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "product_code_tracks.json"
            cd._write_product_code_map({"OAD": "ep_pfa", "GEX": "dental", "DHT": "structural_heart"}, path)
            text = path.read_text(encoding="utf-8")
            self.assertEqual(text.count("\n"), 1)  # one compact line
            self.assertEqual(
                text.strip(), '{"DHT":"structural_heart","GEX":"dental","OAD":"ep_pfa"}'
            )
            self.assertEqual(json.loads(text), {"DHT": "structural_heart", "GEX": "dental", "OAD": "ep_pfa"})


# --------------------------------------------------------------------- company registry
class CompanyResolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = load_companies("device")

    def test_subsidiaries_resolve_to_their_parent(self) -> None:
        cases = {
            "MEDTRONIC MINIMED": "medtronic",
            "Medtronic Sofamor Danek USA, Inc.": "medtronic",
            "ETHICON INC": "johnson_johnson_medtech",
            "BOSTON SCIENTIFIC SCIMED, INC.": "boston_scientific",
            "St. Jude Medical, Cardiology Division": "abbott",
            "PHILIPS MEDICAL SYSTEMS": "philips",
        }
        for applicant, expected in cases.items():
            with self.subTest(applicant=applicant):
                key, confidence, _ = self.registry.resolve(applicant)
                self.assertEqual(key, expected)
                self.assertGreaterEqual(confidence, 0.82)

    def test_false_positives_stay_unmatched(self) -> None:
        # NOTE: "JOHNSON CONTROLS INC" is *not* covered here on purpose: CompanyRegistry's
        # contains_alias() uses set semantics, so the alias "JOHNSON & JOHNSON" collapses
        # to a bare "JOHNSON" token and matches it. That registry bug lives in
        # medradar/config.py (out of this task's write scope) and is reported to the Lead;
        # no such applicant occurs in the collected 24-month data.
        for applicant in ("ACME WIDGETS LLC", "", "MEDICORE SOLUTIONS"):
            with self.subTest(applicant=applicant):
                self.assertIsNone(self.registry.resolve(applicant)[0])

    def test_major_company_keys_are_present(self) -> None:
        majors = set(self.registry.major_keys())
        self.assertTrue({"medtronic", "abbott", "boston_scientific", "philips"} <= majors)


# ------------------------------------------------------------------------- pagination
class PaginationTests(_NoSleepMixin, unittest.TestCase):
    ENDPOINT = "/device/510k.json"

    def test_fetch_window_paginates_to_the_end(self) -> None:
        def handler(url, params, refresh, n):
            if params["limit"] == 1:
                return {"meta": {"results": {"total": 2500}}, "results": []}
            return _page(2500, params["skip"], params["limit"])

        fetcher = FakeFetcher(handler)
        windows: list[dict] = []
        records = cd._fetch_window(
            fetcher,
            self.ENDPOINT,
            "decision_date",
            date(2025, 1, 1),
            date(2026, 10, 30),
            0,
            [],
            windows=windows,
        )
        self.assertEqual(len(records), 2500)
        self.assertEqual(windows[0]["total"], 2500)
        self.assertEqual(windows[0]["fetched"], 2500)
        skips = [call["params"].get("skip") for call in fetcher.calls if call["params"]["limit"] != 1]
        self.assertEqual(skips, [0, 1000, 2000])

    def test_cap_stops_early(self) -> None:
        def handler(url, params, refresh, n):
            if params["limit"] == 1:
                return {"meta": {"results": {"total": 5000}}, "results": []}
            return _page(5000, params["skip"], params["limit"])

        records = cd._fetch_window(
            FakeFetcher(handler), self.ENDPOINT, "decision_date", date(2024, 1, 1), date(2026, 10, 30), 1200, []
        )
        self.assertEqual(len(records), 1200)

    def test_window_above_skip_cap_is_split(self) -> None:
        full_search = cd._range_search("decision_date", date(2020, 1, 1), date(2026, 10, 30))

        def handler(url, params, refresh, n):
            search = params.get("search", "")
            if search == full_search:
                return {"meta": {"results": {"total": 30000}}, "results": []}
            if params["limit"] == 1:
                return {"meta": {"results": {"total": 1200}}, "results": []}
            return _page(1200, params["skip"], params["limit"], id_prefix=search[:20])

        fetcher = FakeFetcher(handler)
        warnings: list[str] = []
        windows: list[dict] = []
        records = cd._fetch_window(
            fetcher,
            self.ENDPOINT,
            "decision_date",
            date(2020, 1, 1),
            date(2026, 10, 30),
            0,
            warnings,
            windows=windows,
        )
        self.assertEqual(len(records), 2400)
        self.assertEqual(len(windows), 2)
        self.assertTrue(any("splitting" in warning for warning in warnings))
        # The oversized window is counted but never paged directly.
        for call in fetcher.calls:
            if call["params"].get("search") == full_search:
                self.assertEqual(call["params"]["limit"], 1)

    def test_short_page_is_retried_with_cache_refresh(self) -> None:
        def handler(url, params, refresh, n):
            if params["limit"] == 1:
                return {"meta": {"results": {"total": 1500}}, "results": []}
            total, skip, limit = 1500, params["skip"], params["limit"]
            expected = min(limit, total - skip)
            if not refresh:
                return _page(total, skip, expected // 2)
            return _page(total, skip, expected)

        fetcher = FakeFetcher(handler)
        records = cd._fetch_window(
            fetcher, self.ENDPOINT, "decision_date", date(2024, 1, 1), date(2026, 10, 30), 0, []
        )
        self.assertEqual(len(records), 1500)
        self.assertTrue(any(call["refresh"] for call in fetcher.calls))

    def test_429_is_retried(self) -> None:
        state = {"count_calls": 0}

        def handler(url, params, refresh, n):
            if params["limit"] == 1:
                state["count_calls"] += 1
                if state["count_calls"] == 1:
                    raise HttpError(429, url, "rate limited")
                return {"meta": {"results": {"total": 2}}, "results": []}
            return _page(2, params["skip"], params["limit"])

        records = cd._fetch_window(
            FakeFetcher(handler), self.ENDPOINT, "decision_date", date(2025, 1, 1), date(2025, 12, 31), 0, []
        )
        self.assertEqual(len(records), 2)

    def test_not_found_means_empty(self) -> None:
        def handler(url, params, refresh, n):
            raise NotFound(404, url, "No matches found")

        self.assertEqual(
            cd._fetch_window(FakeFetcher(handler), self.ENDPOINT, "decision_date", date(2025, 1, 1), date(2025, 2, 1), 0, []),
            [],
        )


# ---------------------------------------------------------------- end-to-end (offline)
class OfflineCollectionTests(_NoSleepMixin, unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.tmp = Path(self._tmpdir.name)
        self.code_map_path = self.tmp / "product_code_tracks.json"
        self.dbs: list[DB] = []

    def _fetcher(self) -> Fetcher:
        return Fetcher(fixtures_dir=FIXTURES_DIR, offline=True, min_interval=0)

    def _db(self, name: str = "device.sqlite") -> DB:
        db = DB(self.tmp / name)
        self.addCleanup(db.close)
        self.dbs.append(db)
        return db

    def _collect(self, db: DB, **kwargs):
        kwargs.setdefault("months", 24)
        kwargs.setdefault("limit", 0)
        kwargs.setdefault("code_map_path", self.code_map_path)
        kwargs.setdefault("today", FIXTURE_DAY)
        return cd.collect(db, self._fetcher(), **kwargs)

    def test_collect_end_to_end(self) -> None:
        db = self._db()
        stats = self._collect(db)

        self.assertEqual(stats["per_kind"], {"510k": 3, "pma": 2, "device_recall": 2})
        self.assertEqual(stats["events_total"], 7)
        self.assertEqual(stats["matched"], 5)
        self.assertEqual(stats["unmatched"], 2)
        self.assertAlmostEqual(stats["match_rate"], round(5 / 7, 4))
        self.assertEqual(stats["track_matched"], 6)
        self.assertEqual(stats["unmapped_codes"], 1)
        self.assertEqual(stats["product_codes"]["codes"], 4)
        self.assertEqual(stats["product_codes"]["mapped_codes"], 3)
        self.assertEqual(stats["warnings"], [])
        self.assertEqual(db.table_count("events"), 7)
        self.assertEqual(db.table_count("product_codes"), 4)
        self.assertEqual(db.table_count("companies"), len(load_companies("device").all()))
        self.assertEqual(db.table_count("tracks"), len(load_tracks("device").ids()))

        # Unmapped product code, ranked by how many events carry it (K250003 + recall 99001).
        self.assertEqual(len(stats["top_unmapped_codes"]), 1)
        top = stats["top_unmapped_codes"][0]
        self.assertEqual(top["product_code"], "QQQ")
        self.assertEqual(top["events"], 2)
        self.assertEqual(top["device_name"], "Pierced Ear Cleaning Tray")

        # 510(k): decision date, subsidiary resolution, product-code track, accessdata URL.
        k_row = db.query(
            "SELECT * FROM events WHERE event_id = ?",
            (make_event_id("openfda_device_510k", "510k", "K250001"),),
        )[0]
        self.assertEqual(k_row["event_date"], "2025-03-14")
        self.assertEqual(k_row["company_key"], "medtronic")
        self.assertEqual(k_row["track_id"], "ep_pfa")
        self.assertIn("K250001", k_row["url"])
        self.assertLessEqual(len(k_row["payload"]), cd.PAYLOAD_LIMIT)

        # PMA original and supplement both stored.
        supplement_row = db.query(
            "SELECT * FROM events WHERE event_id = ?",
            (make_event_id("openfda_device_pma", "pma", "P250001", "S001"),),
        )[0]
        self.assertEqual(supplement_row["company_key"], "edwards_lifesciences")
        self.assertEqual(supplement_row["track_id"], "structural_heart")
        self.assertEqual(supplement_row["event_date"], "2025-07-09")

        # Recall: documented classification date preferred, real-schema posted date otherwise.
        recall_classified = db.query(
            "SELECT * FROM events WHERE event_id = ?",
            (make_event_id("openfda_device_recall", "device_recall", "99001"),),
        )[0]
        self.assertEqual(recall_classified["event_date"], "2025-02-05")
        self.assertEqual(recall_classified["company_key"], "philips")
        # Unmapped product code, but the description still names a modality.
        self.assertEqual(recall_classified["track_id"], "imaging_us")
        recall_posted = db.query(
            "SELECT * FROM events WHERE event_id = ?",
            (make_event_id("openfda_device_recall", "device_recall", "99002"),),
        )[0]
        self.assertEqual(recall_posted["event_date"], "2025-08-01")
        self.assertIsNone(recall_posted["company_key"])
        # product_code OAD is mapped, so the track comes from the dictionary.
        self.assertEqual(recall_posted["track_id"], "ep_pfa")

        # Generated dictionary: flat, sorted, compact.
        text = self.code_map_path.read_text(encoding="utf-8")
        self.assertEqual(text.count("\n"), 1)
        self.assertEqual(
            json.loads(text),
            {"DHT": "structural_heart", "GEX": "dental", "OAD": "ep_pfa"},
        )

    def test_collect_is_idempotent(self) -> None:
        db = self._db()
        self._collect(db)
        before = db.query("SELECT event_id, event_date, company_key, track_id FROM events ORDER BY event_id")
        stats = self._collect(db)
        after = db.query("SELECT event_id, event_date, company_key, track_id FROM events ORDER BY event_id")
        self.assertEqual(before, after)
        self.assertEqual(stats["events_total"], 7)
        self.assertEqual(db.table_count("events"), 7)

    def test_limit_caps_each_kind(self) -> None:
        db = self._db()
        stats = self._collect(db, limit=1)
        self.assertEqual(stats["per_kind"], {"510k": 1, "pma": 1, "device_recall": 1})
        self.assertEqual(stats["events_total"], 3)

    def test_budget_exhaustion_degrades_gracefully(self) -> None:
        def handler(url, params, refresh, n):
            raise BudgetExceeded("request budget 0 exhausted")

        db = self._db()
        stats = cd.collect(
            db,
            FakeFetcher(handler),
            months=24,
            limit=0,
            code_map_path=self.code_map_path,
            today=FIXTURE_DAY,
        )
        self.assertEqual(stats["events_total"], 0)
        self.assertEqual(stats["per_kind"], {"510k": 0, "pma": 0, "device_recall": 0})
        self.assertTrue(any("budget" in warning for warning in stats["warnings"]))
        self.assertEqual(db.table_count("events"), 0)

    def test_offline_mode_never_requests_network(self) -> None:
        # Fetcher(offline=True) raises OfflineMiss for any URL missing from fixtures, so a
        # clean run proves every call came from fixtures/device.
        db = self._db()
        stats = self._collect(db)
        self.assertEqual(stats["events_total"], 7)
        self.assertGreater(stats["cache_hits"], 0)
        self.assertEqual(stats["requests"], 0)


if __name__ == "__main__":
    unittest.main()
