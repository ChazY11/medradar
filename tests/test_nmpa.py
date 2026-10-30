"""Offline unit tests for the honest NMPA adapter.

The whole point of ``medradar/nmpa.py`` is that it never invents Chinese
registration data: either a real user-exported CSV is parsed, or the answer is
``unavailable`` (zero events), or - explicitly requested - clearly fictional
demo rows are loaded and tagged. These tests pin that contract down and never
touch the network.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from medradar import nmpa
from medradar.db import DB

TODAY = date(2026, 10, 31)
SEED = Path(__file__).resolve().parents[1] / "config" / "nmpa_demo_seed.csv"

CHINESE_CSV = """注册证编号,产品名称,企业名称,批准日期,有效期,类别,省份
国械注准20243210001,PULSED FIELD ABLATION CATHETER 脉冲场消融导管,示例电生理（虚构）有限公司,2024/03/11,2029-03-10,III,上海
国械注准20243210002,UNKNOWN PRODUCT XYZ 未知产品,示例未知（虚构）有限公司,2024-05-01,2029-04-30,II,北京
国械注准20243210003,TRANSCATHETER VALVE 经导管瓣膜,示例结构心（虚构）有限公司,2024-06-02,2029-06-01,III,广东
"""

ENGLISH_CSV = """registration_no,product_name,company_name,approval_date,valid_until,class,province
REG-1,CONTINUOUS GLUCOSE MONITOR 连续血糖监测,示例糖尿病（虚构）有限公司,2025-02-03,2030-02-02,II,浙江
REG-2,SURGICAL ROBOT 手术机器人,示例机器人（虚构）有限公司,2025-03-04,2030-03-03,III,江苏
"""


def _clean_env() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if key not in ("MEDRADAR_NMPA_DEMO", "MEDRADAR_NMPA_CSV")
    }


class NmpaCsvParsingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def _write(self, name: str, text: str, encoding: str = "utf-8") -> Path:
        path = self.dir / name
        path.write_bytes(text.encode(encoding))
        return path

    def test_chinese_headers_are_mapped(self) -> None:
        rows = nmpa.read_rows(self._write("cn.csv", CHINESE_CSV))
        self.assertEqual(len(rows), 3)
        first = rows[0]
        self.assertEqual(first["registration_no"], "国械注准20243210001")
        self.assertEqual(first["product_name"], "PULSED FIELD ABLATION CATHETER 脉冲场消融导管")
        self.assertEqual(first["company_name"], "示例电生理（虚构）有限公司")
        self.assertEqual(first["approval_date"], "2024/03/11")
        self.assertEqual(first["class"], "III")
        self.assertEqual(first["province"], "上海")

    def test_english_headers_and_bom_are_accepted(self) -> None:
        rows = nmpa.read_rows(self._write("en.csv", ENGLISH_CSV, "utf-8-sig"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["registration_no"], "REG-2")

    def test_gbk_export_is_decoded(self) -> None:
        rows = nmpa.read_rows(self._write("gbk.csv", CHINESE_CSV, "gb18030"))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["province"], "上海")

    def test_rows_without_identity_are_ignored(self) -> None:
        csv_text = "注册证编号,产品名称,企业名称,批准日期\n,,,,2024-01-01\n"
        rows = nmpa.read_rows(self._write("empty.csv", csv_text))
        self.assertEqual(rows, [])


class NmpaNormalisationTests(unittest.TestCase):
    def test_payload_contract(self) -> None:
        event = nmpa.normalize_registration(
            {
                "registration_no": "国械注准20243210001",
                "product_name": "PULSED FIELD ABLATION CATHETER",
                "company_name": "示例电生理（虚构）有限公司",
                "approval_date": "2024-03-11",
                "valid_until": "2029-03-10",
                "class": "III",
                "province": "上海",
            },
            source=nmpa.SOURCE,
            demo=False,
            track_id="ep_pfa",
            as_of=TODAY.isoformat(),
        )
        assert event is not None
        self.assertEqual(event["kind"], "nmpa_registration")
        self.assertEqual(event["source"], "nmpa")
        self.assertEqual(event["country"], "CN")
        self.assertEqual(event["event_date"], "2024-03-11")
        self.assertEqual(event["track_id"], "ep_pfa")
        payload = event["payload"]
        self.assertEqual(payload["registration_no"], "国械注准20243210001")
        self.assertEqual(payload["product_name"], "PULSED FIELD ABLATION CATHETER")
        self.assertEqual(payload["company_name"], "示例电生理（虚构）有限公司")
        self.assertEqual(payload["approval_date"], "2024-03-11")
        self.assertEqual(payload["class"], "III")
        self.assertEqual(payload["province"], "上海")
        self.assertFalse(payload["demo"])
        self.assertEqual(payload["raw"]["registration_no"], "国械注准20243210001")

    def test_undated_row_is_rejected(self) -> None:
        self.assertIsNone(
            nmpa.normalize_registration(
                {"product_name": "X", "approval_date": "not-a-date"},
                source="nmpa",
                demo=False,
            )
        )


class NmpaCollectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.db = DB(self.dir / "test.sqlite")
        self.addCleanup(self.db.close)

    def test_csv_is_loaded_with_tracks_and_cn_country(self) -> None:
        csv_path = self.dir / "nmpa.csv"
        csv_path.write_text(CHINESE_CSV, encoding="utf-8")
        with patch.dict(os.environ, _clean_env(), clear=True):
            stats = nmpa.collect(
                self.db, None, months=1200, csv_path=csv_path, today=TODAY
            )
        self.assertEqual(stats["status"], "loaded")
        self.assertFalse(stats["demo"])
        self.assertEqual(stats["events"], 3)
        self.assertEqual(stats["per_kind"], {"nmpa_registration": 3})
        self.assertEqual(stats["track_matched"], 2)  # PFA + transcatheter valve
        self.assertEqual(stats["tracks"].get("ep_pfa"), 1)
        self.assertEqual(stats["tracks"].get("unmatched"), 1)

        rows = self.db.query("SELECT * FROM events WHERE kind = 'nmpa_registration'")
        self.assertEqual(len(rows), 3)
        self.assertEqual({row["source"] for row in rows}, {"nmpa"})
        self.assertEqual({row["country"] for row in rows}, {"CN"})
        pfa = [row for row in rows if row["track_id"] == "ep_pfa"]
        self.assertEqual(len(pfa), 1)
        self.assertEqual(pfa[0]["event_date"], "2024-03-11")
        payload = json.loads(pfa[0]["payload"])
        self.assertEqual(payload["registration_no"], "国械注准20243210001")
        self.assertFalse(payload["demo"])

    def test_missing_csv_is_honestly_unavailable(self) -> None:
        before = self.db.table_count("events")
        with patch.dict(os.environ, _clean_env(), clear=True):
            stats = nmpa.collect(
                self.db,
                None,
                months=1200,
                csv_path=self.dir / "nmpa_registrations.csv",
                today=TODAY,
            )
        self.assertEqual(stats["status"], "unavailable")
        self.assertEqual(stats["events"], 0)
        self.assertIn("412", stats["reason"])
        self.assertIn("nmpa_registrations.csv", stats["csv_expected"])
        # Unavailable must not write anything - the blank slate stays blank.
        self.assertEqual(self.db.table_count("events"), before)

    def test_missing_csv_and_demo_flag_off_writes_nothing(self) -> None:
        with patch.dict(os.environ, _clean_env(), clear=True):
            nmpa.collect(self.db, None, months=1200, today=TODAY)
        self.assertEqual(self.db.table_count("events"), 0)

    def test_limit_caps_loaded_rows(self) -> None:
        csv_path = self.dir / "nmpa.csv"
        csv_path.write_text(ENGLISH_CSV, encoding="utf-8")
        with patch.dict(os.environ, _clean_env(), clear=True):
            stats = nmpa.collect(
                self.db, None, months=1200, csv_path=csv_path, limit=1, today=TODAY
            )
        self.assertEqual(stats["events"], 1)
        self.assertEqual(self.db.table_count("events"), 1)

    def test_demo_flag_loads_only_demo_tagged_rows(self) -> None:
        missing = self.dir / "does-not-exist.csv"
        with patch.dict(os.environ, {**_clean_env(), "MEDRADAR_NMPA_DEMO": "1"}, clear=True):
            stats = nmpa.collect(self.db, None, months=1200, csv_path=missing, today=TODAY)
        self.assertEqual(stats["status"], "demo")
        self.assertTrue(stats["demo"])
        self.assertGreaterEqual(stats["events"], 28)
        self.assertIn("虚构", stats["note"])

        rows = self.db.query("SELECT * FROM events")
        self.assertEqual({row["source"] for row in rows}, {"nmpa_demo"})
        self.assertEqual({row["country"] for row in rows}, {"CN"})
        payload = json.loads(rows[0]["payload"])
        self.assertTrue(payload["demo"])
        self.assertIn("【演示数据·非真实】", rows[0]["title"])

    def test_real_csv_wins_over_demo_flag(self) -> None:
        csv_path = self.dir / "real.csv"
        csv_path.write_text(ENGLISH_CSV, encoding="utf-8")
        with patch.dict(os.environ, {**_clean_env(), "MEDRADAR_NMPA_DEMO": "1"}, clear=True):
            stats = nmpa.collect(self.db, None, months=1200, csv_path=csv_path, today=TODAY)
        self.assertEqual(stats["status"], "loaded")
        self.assertFalse(stats["demo"])
        self.assertEqual({row["source"] for row in self.db.query("SELECT source FROM events")}, {"nmpa"})


class DemoSeedHonestyTests(unittest.TestCase):
    def test_seed_exists_and_is_obviously_fictional(self) -> None:
        self.assertTrue(SEED.exists(), "config/nmpa_demo_seed.csv must be committed")
        rows = nmpa.read_rows(SEED)
        self.assertGreaterEqual(len(rows), 28)
        for row in rows:
            self.assertEqual(row.get("source"), "nmpa_demo")
            self.assertIn("DEMO", row["registration_no"])
            self.assertIn("虚构", row["product_name"])
            self.assertIn("虚构", row["company_name"])
            self.assertIsNotNone(nmpa.parse_date(row["approval_date"]))

    def test_load_demo_is_callable_directly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = DB(Path(tmp) / "demo.sqlite")
            try:
                stats = nmpa.load_demo(db, months=1200, today=TODAY)
                self.assertEqual(stats["status"], "demo")
                self.assertEqual(stats["source"], "nmpa_demo")
                self.assertGreaterEqual(stats["events"], 28)
                self.assertEqual(db.table_count("events"), stats["events"])
            finally:
                db.close()

    def test_demo_events_have_tracks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = DB(Path(tmp) / "demo.sqlite")
            try:
                stats = nmpa.load_demo(db, months=1200, today=TODAY)
                self.assertGreaterEqual(stats["track_matched"], 25)
                self.assertEqual(stats["tracks"].get("ep_pfa"), 2)
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
