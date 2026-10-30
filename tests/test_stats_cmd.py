"""Offline tests for ``medradar.stats_cmd.data_stats`` and the DATA.md growth row.

Everything is built from ``tests/fixtures/stats/mini_events.json`` (a synthetic
5-event database) into a temporary SQLite file: no network, no real data, no
writes inside the checkout.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from medradar.db import DB
from medradar.stats_cmd import (
    COUNTED_TABLES,
    GROWTH_MARKER,
    STATS_MARKER_END,
    STATS_MARKER_START,
    append_growth_row,
    data_stats,
    growth_row,
    human_size,
    render_growth_markdown_row,
    render_stats_markdown,
    update_stats_markdown,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "stats" / "mini_events.json"

#: Extra fixture tables inserted verbatim (schema already created by ``DB``).
EXTRA_TABLES = {
    "paper_trades",
    "paper_equity",
    "live_alerts",
    "positions",
    "live_equity",
    "runs",
}


def build_mini_db(path: str | Path) -> Path:
    """Materialise the synthetic mini database used by the stats tests."""
    target = Path(path)
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    with DB(target) as db:
        db.upsert_companies(data.get("companies", []))
        db.upsert_tracks(data.get("tracks", []))
        db.upsert_product_codes(data.get("product_codes", []))
        db.upsert_events(data.get("events", []))
        db.upsert_prices(data.get("prices", []))
        db.upsert_signals(data.get("signals", []))
        for table, rows in (data.get("tables") or {}).items():
            if table not in EXTRA_TABLES:
                raise AssertionError(f"unexpected fixture table: {table}")
            for row in rows:
                columns = list(row)
                placeholders = ",".join("?" for _ in columns)
                db.execute(
                    f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})",
                    [row[column] for column in columns],
                )
        db.commit()
    return target


class _MiniDbCase(unittest.TestCase):
    """Shared read-only mini database, one copy for the whole test class."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.db_path = build_mini_db(Path(cls._tmp.name) / "mini.sqlite")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def stats(self) -> dict:
        with DB(self.db_path) as db:
            return data_stats(db)


# ---------------------------------------------------------------------- overview
class OverviewTests(_MiniDbCase):
    def test_tables_counts(self) -> None:
        stats = self.stats()
        tables = stats["tables"]
        self.assertEqual(tables["events"], 5)
        self.assertEqual(tables["companies"], 3)
        self.assertEqual(tables["tracks"], 2)
        self.assertEqual(tables["product_codes"], 3)
        self.assertEqual(tables["prices"], 5)
        self.assertEqual(tables["signals"], 2)
        self.assertEqual(tables["paper_trades"], 1)
        self.assertEqual(tables["paper_equity"], 2)
        self.assertEqual(tables["live_alerts"], 3)
        self.assertEqual(tables["paper_orders"], 0)
        self.assertEqual(tables["positions"], 1)
        self.assertEqual(tables["live_equity"], 2)
        self.assertEqual(tables["runs"], 1)
        self.assertEqual(tables["llm_verdicts"], 0)
        self.assertEqual(set(tables), set(COUNTED_TABLES))

    def test_status_and_db_info(self) -> None:
        stats = self.stats()
        self.assertEqual(stats["status"], "ok")
        self.assertEqual(stats["errors"], [])
        self.assertTrue(stats["db"]["exists"])
        self.assertGreater(stats["db"]["bytes"], 0)
        self.assertTrue(stats["db"]["size_human"].endswith(("B", "KiB", "MiB")))
        self.assertEqual(stats["db"]["path"], str(self.db_path))
        self.assertRegex(stats["generated_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_payload_is_json_serializable(self) -> None:
        text = json.dumps(self.stats(), ensure_ascii=False)
        self.assertIn("events", text)
        self.assertGreater(len(text), 500)


# -------------------------------------------------------------------- events dist
class EventsDistributionTests(_MiniDbCase):
    def test_totals_and_date_range(self) -> None:
        events = self.stats()["events"]
        self.assertEqual(events["total"], 5)
        self.assertEqual(events["undated"], 1)
        self.assertEqual(events["earliest"], "2019-12-31")
        self.assertEqual(events["latest"], "2021-06-15")
        self.assertEqual(events["earliest_available"], "2019-12-31")
        self.assertEqual(events["latest_available"], "2021-06-15")

    def test_by_year_and_the_year_boundary(self) -> None:
        by_year = self.stats()["events"]["by_year"]
        self.assertEqual(by_year, {"2019": 1, "2020": 2, "2021": 1})
        # 2019-12-31 and 2020-01-01 must never collapse into one bucket
        self.assertIn("2019", by_year)
        self.assertIn("2020", by_year)

    def test_by_source(self) -> None:
        self.assertEqual(
            self.stats()["events"]["by_source"],
            {
                "openfda_device_510k": 2,
                "ctgov": 1,
                "openfda_device_recall": 1,
                "openfda_drug_drugsfda": 1,
            },
        )

    def test_by_kind(self) -> None:
        self.assertEqual(
            self.stats()["events"]["by_kind"],
            {"510k": 2, "trial": 1, "device_recall": 1, "drug_approval": 1},
        )

    def test_by_source_kind_has_ranges(self) -> None:
        rows = self.stats()["events"]["by_source_kind"]
        self.assertEqual(len(rows), 4)
        first = rows[0]
        self.assertEqual(first["source"], "openfda_device_510k")
        self.assertEqual(first["kind"], "510k")
        self.assertEqual(first["n"], 2)
        self.assertEqual(first["earliest"], "2019-12-31")
        self.assertEqual(first["latest"], "2020-01-01")

    def test_by_country(self) -> None:
        self.assertEqual(self.stats()["events"]["by_country"], {"US": 4, "CN": 1})

    def test_by_timestamp_quality(self) -> None:
        self.assertEqual(
            self.stats()["events"]["by_timestamp_quality"],
            {"date": 4, "estimated": 1},
        )

    def test_coverage_rates(self) -> None:
        events = self.stats()["events"]
        self.assertEqual(events["with_company"], 4)
        self.assertEqual(events["with_track"], 2)
        self.assertEqual(events["with_product_code"], 2)
        self.assertEqual(events["match_rate"], {"company": 0.8, "track": 0.4, "product_code": 0.4})


# ---------------------------------------------------------------------- registries
class RegistryTests(_MiniDbCase):
    def test_registry_counts(self) -> None:
        registries = self.stats()["registries"]
        self.assertEqual(registries["companies"], 3)
        self.assertEqual(registries["companies_with_ticker"], 2)
        self.assertEqual(registries["companies_major"], 1)
        self.assertEqual(registries["tracks"], 2)
        self.assertEqual(registries["product_codes"], 3)
        self.assertEqual(registries["product_codes_mapped"], 2)
        self.assertEqual(registries["product_code_coverage"], 0.667)


# ------------------------------------------------------------------------- prices
class PriceTests(_MiniDbCase):
    def test_price_coverage(self) -> None:
        prices = self.stats()["prices"]
        self.assertEqual(prices["rows"], 5)
        self.assertEqual(prices["tickers"], 3)
        self.assertEqual(prices["earliest"], "2020-01-02")
        self.assertEqual(prices["latest"], "2020-01-03")
        self.assertEqual(prices["benchmarks"], {"SPY": True, "XBI": False})

    def test_ticker_detail_is_sorted(self) -> None:
        detail = self.stats()["prices"]["tickers_detail"]
        self.assertEqual([row["ticker"] for row in detail], ["ACME", "GMMA", "SPY"])
        acme = detail[0]
        self.assertEqual(acme["rows"], 2)
        self.assertEqual(acme["earliest"], "2020-01-02")
        self.assertEqual(acme["latest"], "2020-01-03")


# ------------------------------------------------------------------ trading / live
class TradingTests(_MiniDbCase):
    def test_signal_and_paper_counts(self) -> None:
        trading = self.stats()["trading"]
        self.assertEqual(trading["signals"], 2)
        self.assertEqual(
            trading["signals_by_kind"],
            {"device_novel_code": 1, "drug_approval": 1},
        )
        self.assertEqual(trading["signals_earliest"], "2020-01-05")
        self.assertEqual(trading["signals_latest"], "2020-01-06")
        self.assertEqual(trading["paper_trades"], 1)
        self.assertEqual(trading["paper_equity"], 2)
        self.assertEqual(trading["positions"], 1)
        self.assertEqual(trading["paper_orders"], 0)
        self.assertEqual(trading["live_alerts"], 3)
        self.assertEqual(trading["live_equity"], 2)
        self.assertEqual(trading["llm_verdicts"], 0)

    def test_last_run_stats_are_decoded(self) -> None:
        trading = self.stats()["trading"]
        self.assertEqual(trading["runs"], 1)
        last_run = trading["last_run"]
        self.assertIsNotNone(last_run)
        assert last_run is not None
        self.assertEqual(last_run["stage"], "nightly")
        self.assertEqual(last_run["stats"], {"events": 5, "ok": True})


# ------------------------------------------------------------------------ tolerance
class ToleranceTests(unittest.TestCase):
    def test_missing_path_reports_instead_of_creating(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "not-collected-yet.sqlite"
            stats = data_stats(missing)
            self.assertEqual(stats["status"], "missing_db")
            self.assertFalse(stats["db"]["exists"])
            self.assertFalse(missing.exists())
            self.assertEqual(stats["events"]["total"], 0)
            self.assertEqual(stats["tables"]["events"], 0)

    def test_directory_path_is_not_mistaken_for_a_database(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stats = data_stats(Path(tmp))
            self.assertEqual(stats["status"], "missing_db")
            self.assertTrue(stats["errors"])

    def test_empty_database_does_not_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty.sqlite"
            with DB(empty):
                pass
            stats = data_stats(empty)
            self.assertEqual(stats["status"], "ok")
            self.assertEqual(stats["events"]["total"], 0)
            self.assertEqual(stats["events"]["by_year"], {})
            self.assertEqual(stats["events"]["undated"], 0)
            self.assertEqual(stats["events"]["earliest"], "")
            self.assertEqual(stats["events"]["latest"], "")
            self.assertEqual(stats["events"]["match_rate"], {"company": 0.0, "track": 0.0, "product_code": 0.0})
            self.assertEqual(stats["prices"]["rows"], 0)
            self.assertIsNone(stats["trading"]["last_run"])
            self.assertEqual(stats["errors"], [])

    def test_dropped_tables_are_reported_not_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = build_mini_db(Path(tmp) / "partial.sqlite")
            with DB(db_path) as db:
                db.execute("DROP TABLE prices")
                db.commit()
                stats = data_stats(db)
            self.assertEqual(stats["status"], "ok")
            self.assertEqual(stats["prices"]["rows"], 0)
            self.assertEqual(stats["prices"]["tickers"], 0)
            self.assertTrue(any("prices" in error for error in stats["errors"]))
            self.assertEqual(stats["events"]["total"], 5)

    def test_accepts_a_db_instance_and_leaves_it_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = build_mini_db(Path(tmp) / "mini.sqlite")
            with DB(db_path) as db:
                stats = data_stats(db)
                self.assertEqual(stats["events"]["total"], 5)
                self.assertEqual(db.query("SELECT 1"), [{"1": 1}])

    def test_accepts_a_path_and_closes_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = build_mini_db(Path(tmp) / "mini.sqlite")
            stats = data_stats(str(db_path))
            self.assertEqual(stats["events"]["total"], 5)
            self.assertEqual(stats["db"]["bytes"], db_path.stat().st_size)

    def test_rejects_garbage_input(self) -> None:
        with self.assertRaises(TypeError):
            data_stats(42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------- growth
class GrowthRowTests(unittest.TestCase):
    def _stats(self) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = build_mini_db(Path(tmp) / "mini.sqlite")
            return data_stats(db_path)

    def test_growth_row_fields(self) -> None:
        row = growth_row(self._stats(), note="nightly", day="2026-10-31")
        self.assertEqual(row["date"], "2026-10-31")
        self.assertEqual(row["events"], 5)
        self.assertEqual(row["companies"], 3)
        self.assertEqual(row["tracks"], 2)
        self.assertEqual(row["product_codes"], 3)
        self.assertEqual(row["price_rows"], 5)
        self.assertEqual(row["note"], "nightly")
        self.assertIn("B", row["db_human"])

    def test_render_markdown_row(self) -> None:
        rendered = render_growth_markdown_row(
            {
                "date": "2026-10-31",
                "events": 83578,
                "companies": 89,
                "tracks": 60,
                "product_codes": 7097,
                "price_rows": 180535,
                "db_human": "328.5 MiB",
                "note": "nightly",
            }
        )
        self.assertEqual(
            rendered,
            "| 2026-10-31 | 83578 | 89 | 60 | 7097 | 180535 | 328.5 MiB | nightly |",
        )

    def test_append_is_idempotent_per_day(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "DATA.md"
            target.write_text(
                "# DATA\n\n"
                + GROWTH_MARKER.replace("end", "start")
                + "\n| 日期 | events |\n| --- | ---: |\n"
                + GROWTH_MARKER
                + "\n",
                encoding="utf-8",
            )
            stats = self._stats()
            first = append_growth_row(stats, target, note="nightly", day="2026-10-31")
            self.assertEqual(first["status"], "appended")
            second = append_growth_row(stats, target, note="nightly", day="2026-10-31")
            self.assertEqual(second["status"], "appended")
            text = target.read_text(encoding="utf-8")
            self.assertEqual(text.count("| 2026-10-31 |"), 1)
            self.assertLess(text.index("| 2026-10-31 |"), text.index(GROWTH_MARKER))
            # the row must stay glued to the table header, otherwise markdown
            # renders the header as plain text (markers live outside the table)
            self.assertIn("| --- | ---: |\n| 2026-10-31 |", text)

            third = append_growth_row(stats, target, note="nightly", day="2026-11-01")
            self.assertEqual(third["status"], "appended")
            text = target.read_text(encoding="utf-8")
            self.assertEqual(text.count("| 2026-11-01 |"), 1)
            self.assertEqual(text.count("| 2026-10-31 |"), 1)
            self.assertLess(text.index("| 2026-10-31 |"), text.index("| 2026-11-01 |"))
            self.assertIn("| 2026-10-31 |", text.split(GROWTH_MARKER)[0])

    def test_append_skips_missing_file_or_marker(self) -> None:
        stats = self._stats()
        with tempfile.TemporaryDirectory() as tmp:
            missing = append_growth_row(stats, Path(tmp) / "nope.md", day="2026-10-31")
            self.assertEqual(missing["status"], "skipped")

            no_marker = Path(tmp) / "DATA.md"
            no_marker.write_text("# DATA\nno table here\n", encoding="utf-8")
            skipped = append_growth_row(stats, no_marker, day="2026-10-31")
            self.assertEqual(skipped["status"], "skipped")
            self.assertEqual(no_marker.read_text(encoding="utf-8"), "# DATA\nno table here\n")


# ---------------------------------------------------------------------------- DATA.md
class DataMdBlockTests(_MiniDbCase):
    def test_render_has_every_section(self) -> None:
        block = render_stats_markdown(self.stats())
        self.assertTrue(block.startswith(STATS_MARKER_START))
        self.assertTrue(block.rstrip().endswith(STATS_MARKER_END))
        for heading in (
            "### 总览",
            "### 来源与类型",
            "### 覆盖年份",
            "### 覆盖质量",
            "### 价格覆盖",
            "### 交易与回放",
            "### 数据健康",
        ):
            self.assertIn(heading, block)
        self.assertIn("openfda_device_510k", block)
        self.assertIn("| 2019 | 1 |", block)
        self.assertIn("| 2020 | 2 |", block)
        self.assertIn("查询失败：无", block)

    def test_render_tolerates_an_empty_payload(self) -> None:
        block = render_stats_markdown({})
        self.assertIn("### 总览", block)
        self.assertIn("| — | 0 |", block)
        self.assertIn("查询失败：无", block)

    def test_update_replaces_block_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "DATA.md"
            target.write_text(
                "# DATA\n\nprose before\n\n"
                + STATS_MARKER_START
                + "\nOLD CONTENT\n"
                + STATS_MARKER_END
                + "\n\nprose after\n",
                encoding="utf-8",
            )
            snapshot = self.stats()
            first = update_stats_markdown(snapshot, target)
            self.assertEqual(first["status"], "updated")
            text = target.read_text(encoding="utf-8")
            self.assertNotIn("OLD CONTENT", text)
            self.assertIn("### 总览", text)
            self.assertIn("prose before", text)
            self.assertIn("prose after", text)
            self.assertEqual(text.count(STATS_MARKER_START), 1)

            # same payload -> byte-identical file, so nightly reruns stay clean
            unchanged = update_stats_markdown(snapshot, target)
            self.assertEqual(unchanged["status"], "unchanged")
            self.assertEqual(target.read_text(encoding="utf-8"), text)

    def test_update_skips_missing_file_or_markers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = update_stats_markdown(self.stats(), Path(tmp) / "nope.md")
            self.assertEqual(missing["status"], "skipped")

            no_markers = Path(tmp) / "DATA.md"
            no_markers.write_text("# DATA\n", encoding="utf-8")
            skipped = update_stats_markdown(self.stats(), no_markers)
            self.assertEqual(skipped["status"], "skipped")
            self.assertEqual(no_markers.read_text(encoding="utf-8"), "# DATA\n")


# ---------------------------------------------------------------------------- helpers
class HelperTests(unittest.TestCase):
    def test_human_size(self) -> None:
        self.assertEqual(human_size(0), "0 B")
        self.assertEqual(human_size(None), "0 B")
        self.assertEqual(human_size(512), "512 B")
        self.assertEqual(human_size(1536), "1.5 KiB")
        self.assertEqual(human_size(344436736), "328.5 MiB")
        self.assertTrue(human_size(2 * 1024 ** 3).endswith("GiB"))

    def test_fixture_shape(self) -> None:
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(len(data["events"]), 5)
        self.assertEqual(len(data["companies"]), 3)
        self.assertEqual(len(data["tracks"]), 2)
        self.assertEqual(len(data["product_codes"]), 3)
        self.assertTrue(any(not event.get("event_date") for event in data["events"]))
        self.assertTrue(any(not event.get("company_key") for event in data["events"]))


if __name__ == "__main__":
    unittest.main()
