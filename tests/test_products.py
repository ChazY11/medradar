"""Offline tests for the product-family taxonomy, Chinese catalog and products API.

Nothing here touches the network: the behavioural tests build a small synthetic
SQLite database, while the artefact tests read the generated ``config/*.json``
files (and compare them with ``data/medradar.sqlite`` read-only when it exists,
so a stale artefact is caught instead of silently drifting).
"""

from __future__ import annotations

import json
import re
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from medradar import families as fam
from medradar import products
from medradar.config import DEFAULT_DB
from medradar.db import DB, make_event_id

TODAY = date(2026, 10, 31)
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
CATALOG_KEYS = {"name_zh", "definition_zh"}


def _has_cjk(text: str) -> bool:
    return bool(CJK_RE.search(str(text or "")))


def _code_of(device_name: str, specialty: str = "Unknown") -> dict:
    return {"device_name": device_name, "definition": "", "specialty": specialty}


def _readonly_db(path: str | Path):
    """Tiny read-only DB adapter (query/scalar) so tests never touch the WAL."""

    path_str = str(Path(path))
    uri = f"file:{Path(path).as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row

    class _Reader:
        path = path_str

        def __init__(self, connection):
            self.conn = connection

        def query(self, sql, params=()):
            rows = self.conn.execute(sql, tuple(params)).fetchall()
            return [dict(row) for row in rows]

        def scalar(self, sql, params=(), default=None):
            row = self.conn.execute(sql, tuple(params)).fetchone()
            return row[0] if row is not None else default

        def close(self):
            self.conn.close()

    return _Reader(conn)


def _load_catalog_script():
    """Import ``scripts/build_product_catalog.py`` without executing its CLI."""
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "scripts" / "build_product_catalog.py"
    spec = importlib.util.spec_from_file_location("medradar_build_product_catalog", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SyntheticDatabaseMixin:
    """A tiny, deterministic database covering families, companies and new launches."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        path = Path(self._tmp.name) / "products.sqlite"
        db = DB(path)
        self.addCleanup(db.close)
        self.db = db
        db.upsert_companies(
            [
                {"key": "acme", "name_en": "Acme Medical", "name_zh": "艾克米医疗", "ticker": "ACME"},
                {"key": "globex", "name_en": "Globex", "name_zh": "环球医疗", "ticker": "GLBX"},
                {"key": "initech", "name_en": "Initech", "name_zh": "伊尼泰克", "ticker": "INIT"},
                {"key": "umbrella", "name_en": "Umbrella", "name_zh": "安布雷拉", "ticker": "UMB"},
            ]
        )
        db.upsert_product_codes(
            [
                {"product_code": "AAA", **_code_of("Implantable Cardioverter Defibrillator", "Cardiovascular")},
                {"product_code": "BBB", **_code_of("Catheter, Percutaneous", "Cardiovascular")},
                {"product_code": "CCC", **_code_of("System, X-Ray, Tomography, Computed", "Radiology")},
                {"product_code": "DDD", **_code_of("Mystery Widget", "Unknown")},
                {"product_code": "EEE", **_code_of("Mask, Surgical", "General, Plastic Surgery")},
                {"product_code": "FFF", **_code_of("Stent, Coronary", "Cardiovascular")},
            ]
        )
        events = []

        def add(kind: str, day: str, company: str | None, code: str, payload: dict | None = None, **extra) -> None:
            payload = payload or {}
            events.append(
                {
                    "event_id": make_event_id("unit", kind, company, code, day, len(events)),
                    "source": "unit_test",
                    "kind": kind,
                    "event_date": day,
                    "company_key": company,
                    "applicant_raw": company or "",
                    "product_code": code,
                    "title": f"{kind} {code}",
                    "url": f"https://example.test/{code}/{day}",
                    "payload": payload,
                    **extra,
                }
            )

        # cvd_rhythm_ep: 2 baseline, 5 recent -> THI > 1
        add("510k", "2020-03-01", "acme", "AAA", {"k_number": "K200001"})
        add("510k", "2021-05-01", "globex", "AAA", {"k_number": "K210001"})
        add("510k", "2025-04-01", "acme", "AAA", {"k_number": "K250001"})
        add("510k", "2025-08-01", "initech", "AAA", {"k_number": "K250002"})
        add("510k", "2026-01-15", "acme", "AAA", {"k_number": "K260001"})
        add("510k", "2026-06-01", "umbrella", "AAA", {"k_number": "K261001"})  # new entrant
        add("510k", "2026-09-20", "initech", "AAA", {"k_number": "K262001"})
        # other families
        add("510k", "2026-09-01", "acme", "FFF", {"k_number": "K260002"})
        add("510k", "2026-08-01", "acme", "CCC", {"k_number": "K260003"})
        add("510k", "2026-10-25", "globex", "EEE", {"k_number": "K260004"})
        add("510k", "2026-10-10", "initech", "DDD", {"k_number": "K260005"})
        add("510k", "2026-10-15", "acme", "AAA", {"k_number": "K260006"})
        # pma original + routine supplement (the supplement must NOT count as activity)
        add("pma", "2026-10-05", "acme", "BBB", {"pma_number": "P123456", "supplement_number": "S0"})
        add(
            "pma",
            "2025-06-01",
            "acme",
            "AAA",
            {"pma_number": "P123456", "supplement_number": "S010", "supplement_type": "30-Day Notice"},
        )
        # recalls are not activity, but a recent recall is reported per family
        add("device_recall", "2026-10-01", "acme", "AAA", {"res_event_number": "1"})
        add("device_recall", "2026-10-02", "acme", "N/A", {"res_event_number": "2"})
        db.upsert_events(events)


class BuildFamiliesTests(SyntheticDatabaseMixin, unittest.TestCase):
    def test_build_is_deterministic_and_partitioned(self) -> None:
        first = fam.build_families(self.db, write=False)
        second = fam.build_families(self.db, write=False)
        self.assertEqual(
            json.dumps(first, ensure_ascii=False, sort_keys=True),
            json.dumps(second, ensure_ascii=False, sort_keys=True),
        )
        required = {"id", "name_zh", "name_en", "category", "keywords", "codes", "note"}
        seen: set[str] = set()
        for family in first["families"]:
            self.assertTrue(required <= set(family))
            self.assertTrue(family["codes"])
            for code in family["codes"]:
                self.assertNotIn(code, seen, f"code {code} assigned twice")
                seen.add(code)
        self.assertFalse(seen & set(first["unclassified"]))
        self.assertTrue(first["meta"]["family_count"] >= 2)
        # an unknown code must not be force-fitted: it stays unclassified
        self.assertIn("DDD", first["unclassified"])
        self.assertNotIn("N/A", first["unclassified"])
        self.assertNotIn("N/A", seen)

    def test_coverage_meta_is_honest(self) -> None:
        payload = fam.build_families(self.db, write=False)
        cov = payload["meta"]["coverage"]
        # 16 rows carry a product code; the "N/A" recall row is not a code
        self.assertEqual(cov["coded_events"], 15)
        self.assertGreaterEqual(cov["classified_share"], 0.8)
        self.assertLessEqual(cov["classified_events"], cov["coded_events"])
        self.assertGreaterEqual(cov["top20_share"], 0.0)
        self.assertIn("classified_share_of_all_events", cov)

    def test_lookup_round_trip(self) -> None:
        payload = fam.build_families(self.db, write=False)
        by_id, code_map = fam.family_lookup(payload)
        for code, family_id in code_map.items():
            self.assertIn(family_id, by_id)
            self.assertIn(code, by_id[family_id]["codes"])
        report = fam.coverage_report(payload)
        self.assertIn("产品族数量", report)
        self.assertIn("Top20", report)


class ProductApiTests(SyntheticDatabaseMixin, unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.families = fam.build_families(self.db, write=False)
        _, self.code_map = fam.family_lookup(self.families)
        self.cvd = self.code_map["AAA"]
        self.vasc = self.code_map["BBB"]

    def test_family_stats(self) -> None:
        rows = products.family_stats(self.db, families=self.families, today=TODAY)
        self.assertIsInstance(rows, list)
        self.assertTrue(all("thi" in row for row in rows))
        cvd = next(row for row in rows if row["family_id"] == self.cvd)
        self.assertEqual(cvd["recent"], 6)
        self.assertEqual(cvd["base"], 2)
        self.assertGreater(cvd["recent_per_q"], cvd["baseline_per_q"])
        self.assertIsNotNone(cvd["thi"])
        self.assertGreater(cvd["thi"], 1.0)
        self.assertEqual(cvd["companies"], 3)  # acme, initech, umbrella in window
        self.assertEqual(cvd["new_entrants_12m"], 1)  # umbrella
        self.assertEqual(cvd["first_seen"], "2020-03-01")
        self.assertEqual(cvd["recalls_recent"], 1)
        self.assertTrue(cvd["top_product"])
        # rows are ordered by recent activity, ranks are 1..n
        recents = [row["recent"] for row in rows]
        self.assertEqual(recents, sorted(recents, reverse=True))
        self.assertEqual([row["rank"] for row in rows], list(range(1, len(rows) + 1)))

    def test_company_portfolio(self) -> None:
        portfolio = products.company_portfolio(self.db, families=self.families, today=TODAY)
        self.assertIn("acme", portfolio)
        acme = portfolio["acme"]
        self.assertEqual(acme["name_zh"], "艾克米医疗")
        self.assertGreater(acme["recent"], 0)
        families_in_mix = {row[0] for row in acme["top_families"]}
        self.assertIn(self.vasc, families_in_mix)
        self.assertIsInstance(acme["migration"], list)
        self.assertGreaterEqual(acme["js"], 0.0)
        self.assertIn("new_families_12m", acme)

    def test_new_products(self) -> None:
        items = products.new_products(self.db, days=90, families=self.families, today=TODAY)
        pairs = {(row["company_key"], row["product_code"]) for row in items}
        self.assertIn(("acme", "BBB"), pairs)  # original PMA, 2026-10-05
        self.assertIn(("globex", "EEE"), pairs)
        self.assertIn(("initech", "DDD"), pairs)
        self.assertNotIn(("acme", "AAA"), pairs)  # first seen in 2020
        self.assertNotIn(("initech", "AAA"), pairs)  # first seen in 2025-08
        for row in items:
            self.assertGreaterEqual(row["event_date"], "2026-07-27")
            self.assertTrue(row["product_code"])
            self.assertTrue(row["product_name_zh"])
            self.assertTrue(row["family_id"])
            self.assertTrue(row["url"].startswith("https://"))

    def test_new_products_number_and_family(self) -> None:
        items = products.new_products(self.db, days=90, families=self.families, today=TODAY)
        acme_bbb = next(
            row for row in items if row["company_key"] == "acme" and row["product_code"] == "BBB"
        )
        self.assertEqual(acme_bbb["kind"], "pma")
        self.assertIn("P123456", acme_bbb["number"])
        ddd = next(row for row in items if row["product_code"] == "DDD")
        self.assertEqual(ddd["number"], "K260005")
        self.assertEqual(ddd["family_id"], products.NO_FAMILY)
        self.assertEqual(ddd["family_zh"], "未分类")

    def test_family_detail(self) -> None:
        detail = products.family_detail(
            self.db, self.cvd, families=self.families, recent_limit=5, today=TODAY
        )
        self.assertEqual(detail["family_id"], self.cvd)
        self.assertGreaterEqual(detail["code_count"], 1)
        self.assertTrue(detail["codes"])
        self.assertTrue(all("product_code" in row for row in detail["codes"]))
        self.assertLessEqual(len(detail["recent_events"]), 5)
        self.assertTrue(detail["recent_events"])
        self.assertIsNotNone(detail["stats"])
        self.assertGreaterEqual(detail["recent_total"], 1)
        unknown = products.family_detail(self.db, "does_not_exist", families=self.families)
        self.assertIn("error", unknown)

    def test_catalog_name_fallback(self) -> None:
        self.assertEqual(products.catalog_name("ZZZ", {}, "Unknown Device"), "Unknown Device")
        self.assertEqual(products.catalog_definition("ZZZ", {}, "some use"), "some use")
        self.assertEqual(products.catalog_name("AAA", {}, "IDC"), "IDC")


class ArtifactTests(unittest.TestCase):
    """Validate the generated knowledge files committed under ``config/``."""

    def test_families_artifact(self) -> None:
        payload = fam.load_families()
        meta, family_list = payload["meta"], payload["families"]
        self.assertGreaterEqual(len(family_list), 180)
        self.assertLessEqual(len(family_list), 250)
        self.assertEqual(meta["family_count"], len(family_list))
        coverage = meta["coverage"]
        self.assertGreaterEqual(coverage["classified_share"], 0.985)
        self.assertGreaterEqual(coverage["top20_share"], 0.5)
        # the all-events denominator moves whenever a collector backfills
        # drug/trial events (which carry no product code), so only sanity-check it
        self.assertGreaterEqual(coverage["classified_share_of_all_events"], 0.75)
        ids = [item["id"] for item in family_list]
        self.assertEqual(len(ids), len(set(ids)))
        codes: set[str] = set()
        for item in family_list:
            self.assertTrue({"id", "name_zh", "name_en", "category", "keywords", "codes", "note"} <= set(item))
            self.assertTrue(item["name_zh"] and item["name_en"] and item["category"])
            self.assertIn(item["category"], fam.CATEGORY_ORDER)
            self.assertTrue(item["codes"])
            self.assertFalse(codes & set(item["codes"]), "codes must be partitioned")
            codes |= set(item["codes"])
        self.assertFalse(codes & set(payload["unclassified"]))
        self.assertNotIn("N/A", codes)
        top = sorted(
            (
                sum(1 for _code in item["codes"]),
                item["id"],
            )
            for item in family_list
        )
        self.assertGreater(len(top), 20)

    def test_catalog_artifact(self) -> None:
        catalog = products.load_catalog()
        self.assertGreaterEqual(len(catalog), 2000)
        self.assertLessEqual(len(catalog), 3000)
        for code, entry in catalog.items():
            self.assertEqual(set(entry), CATALOG_KEYS, code)
            self.assertTrue(entry["name_zh"].strip(), code)
            self.assertTrue(entry["definition_zh"].strip(), code)
            self.assertTrue(_has_cjk(entry["name_zh"]), code)
            self.assertTrue(_has_cjk(entry["definition_zh"]), code)
        self.assertNotIn("N/A", catalog)

    def test_catalog_covers_real_top2000(self) -> None:
        if not Path(DEFAULT_DB).exists():
            self.skipTest("real database not available")
        catalog = products.load_catalog()
        uri = f"file:{Path(DEFAULT_DB).as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        try:
            rows = conn.execute(
                "SELECT product_code, COUNT(*) n FROM events"
                " WHERE product_code IS NOT NULL AND product_code != ''"
                " GROUP BY product_code ORDER BY n DESC, product_code ASC"
            ).fetchall()
        finally:
            conn.close()
        valid = [
            (code, n)
            for code, n in rows
            if str(code).strip().upper() not in fam.INVALID_PRODUCT_CODES
            and str(code).replace("-", "").isalnum()
        ][:2000]
        self.assertEqual(len(valid), 2000)
        for code, _n in valid:
            self.assertIn(code, catalog)
            self.assertTrue(catalog[code]["name_zh"].strip())
            self.assertTrue(_has_cjk(catalog[code]["name_zh"]), code)
            self.assertTrue(catalog[code]["definition_zh"].strip(), code)

    def test_catalog_is_idempotent_and_preserves_reviewed_entries(self) -> None:
        """Re-running the generator reproduces the committed file byte-for-byte."""
        if not Path(DEFAULT_DB).exists():
            self.skipTest("real database not available")
        module = _load_catalog_script()
        reader = _readonly_db(DEFAULT_DB)
        self.addCleanup(reader.close)
        first, first_report = module.build_catalog(reader)
        second, second_report = module.build_catalog(reader)
        self.assertEqual(first, second)
        self.assertEqual(first_report, second_report)
        committed = products.load_catalog()
        self.assertGreaterEqual(len(committed), 2000)
        self.assertEqual(len(first), 2000)
        # the committed artefact must agree with a fresh build on every code it
        # covers (new top-2000 codes from a parallel collector are caught by
        # test_catalog_covers_real_top2000)
        for code in set(committed) & set(first):
            self.assertEqual(committed[code], first[code], code)
        # the reviewed 600 are the authoritative base: they are never overwritten
        self.assertEqual(len(module.REVIEWED_CATALOG), 600)
        for code, entry in module.REVIEWED_CATALOG.items():
            if code in first:
                self.assertEqual(first[code]["name_zh"], entry[0], code)
                self.assertEqual(first[code]["definition_zh"], entry[1], code)
        self.assertFalse(module.REVIEWED_CATALOG.keys() & module.EXTENDED_CATALOG.keys())
        self.assertGreaterEqual(len(module.EXTENDED_CATALOG), 1400)

    def test_families_artifact_matches_rebuild(self) -> None:
        if not Path(DEFAULT_DB).exists():
            self.skipTest("real database not available")
        reader = _readonly_db(DEFAULT_DB)
        self.addCleanup(reader.close)
        rebuilt = fam.build_families(reader, write=False)
        current = fam.load_families()
        # Compare the deterministic part (family assignment + conflicts). The
        # event counters in ``meta`` legitimately drift while a parallel
        # collector backfills drug/trial events, so they are not compared here.
        self.assertEqual(
            json.dumps(current["families"], ensure_ascii=False, sort_keys=True),
            json.dumps(rebuilt["families"], ensure_ascii=False, sort_keys=True),
            "config/product_families.json is stale - run scripts/build_product_catalog.py",
        )
        self.assertEqual(current["unclassified"], rebuilt["unclassified"])
        self.assertEqual(current["meta"]["family_count"], rebuilt["meta"]["family_count"])


if __name__ == "__main__":
    unittest.main()
