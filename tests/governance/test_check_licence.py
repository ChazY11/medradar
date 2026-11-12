"""Unit tests for the hardened licence gate: positive inventory + content scan."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from . import gitfix
from tools.governance import check_licence

MARKER = gitfix.MARKER


def _seed(root: Path) -> Path:
    gitfix.init_repo(root)
    gitfix.copy_policy(root)
    gitfix.write(root / "docs/metrics.json", '{"synthetic": true}')
    gitfix.write(root / "config/seed.csv", "key,value\n1,2\n")
    gitfix.commit(root, "baseline")
    result = gitfix.run_gate("check_licence.py", root, "--write-inventory")
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    gitfix.commit(root, "inventory")
    return root


class BypassTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = _seed(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self):
        return gitfix.run_gate("check_licence.py", self.root, "--base", "HEAD")

    def _stage(self, rel: str, data: bytes) -> None:
        target = self.root / rel
        gitfix.write_bytes(target, data)
        gitfix.stage(self.root, rel)

    def _assert_caught(self, result, *needles: str) -> None:
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        for needle in needles:
            self.assertIn(needle, result.stdout + result.stderr)
        self.assertNotIn(
            MARKER,
            result.stdout + result.stderr,
            "gate logs must not echo file content",
        )

    def test_bypass_a_new_source_new_location_csv(self):
        self._stage(
            "data_exports/vendor_flight_feed_2026.csv",
            b"ticker,date,signal\nSYNTH,2026-01-02,buy\n",
        )
        self._assert_caught(self._run(), "inventory.coverage", "diff.changed_data_file")

    def test_bypass_b_amber_content_at_undeclared_path(self):
        self._stage(
            "research/RESULTS/wayback_monthly_counts.json",
            b'{"source": "internet_archive_cdx", "months": 12}',
        )
        self._assert_caught(self._run(), "inventory.coverage")

    def test_bypass_c_binary_sqlite_under_docs(self):
        self._stage("docs/market_data.sqlite", gitfix.fixture_bytes("fake_market.sqlite"))
        self._assert_caught(
            self._run(), "inventory.coverage", "restricted binary format"
        )

    def test_bypass_d_csv_under_docs(self):
        self._stage(
            "docs/market_bars_2026.csv",
            b"ticker,date,close\nSYNTH,2026-01-02,1.0\n",
        )
        self._assert_caught(self._run(), "inventory.coverage")

    def test_control_declared_red_pattern_is_caught(self):
        self._stage(
            "docs/prices_2019.csv",
            b"ticker,date,close\nSYNTH,2019-01-02,1.0\n",
        )
        self._assert_caught(self._run(), "source.pattern", "yahoo_chart_bars")

    def test_extension_masquerade_is_caught(self):
        gitfix.write(self.root / "docs/market.csv", "ticker,date\nSYNTH,2026-01-02\n")
        gitfix.commit(self.root, "add declared csv")
        result = gitfix.run_gate("check_licence.py", self.root, "--write-inventory")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        gitfix.commit(self.root, "inventory covers csv")
        # Same declared path, but the bytes are now a SQLite database.
        gitfix.write_bytes(
            self.root / "docs/market.csv", gitfix.fixture_bytes("fake_market.sqlite")
        )
        gitfix.stage(self.root, "docs/market.csv")
        self._assert_caught(self._run(), "content kind changed since inventory")

    def test_untracked_data_file_is_caught(self):
        gitfix.write_bytes(
            self.root / "data_exports/hidden.csv", b"ticker,date\nSYNTH,2026-01-02\n"
        )
        self._assert_caught(self._run(), "untracked.data_file")

    def test_renamed_data_file_is_caught(self):
        gitfix.run_git(self.root, "mv", "docs/metrics.json", "docs/metrics_renamed.json")
        self._assert_caught(
            self._run(), "inventory.coverage", "inventory.stale_entry"
        )

    def test_baseline_repo_passes(self):
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class DetectKindTests(unittest.TestCase):
    def test_sqlite(self):
        self.assertEqual(check_licence.detect_kind(b"SQLite format 3\x00rest"), "sqlite")

    def test_parquet(self):
        self.assertEqual(check_licence.detect_kind(b"PAR1rest"), "parquet")

    def test_gzip(self):
        self.assertEqual(check_licence.detect_kind(b"\x1f\x8b\x08rest"), "gzip")

    def test_zip(self):
        self.assertEqual(check_licence.detect_kind(b"PK\x03\x04rest"), "zip")

    def test_json(self):
        self.assertEqual(check_licence.detect_kind(b'{"a": 1}'), "json")

    def test_csv(self):
        self.assertEqual(check_licence.detect_kind(b"a,b\n1,2\n"), "csv")

    def test_text(self):
        self.assertEqual(check_licence.detect_kind(b"plain words\n"), "text")

    def test_utf16_log_is_text_not_binary(self):
        data = "eligible cells: 65\n".encode("utf-16")
        self.assertEqual(check_licence.detect_kind(data), "text")

    def test_media(self):
        self.assertEqual(check_licence.detect_kind(b"\x89PNG\r\n\x1a\nrest"), "png")


class RealRepositoryBaselineTests(unittest.TestCase):
    def test_current_repository_is_clean(self):
        policy = gitfix.REPO_ROOT / "docs/governance/DATA_LICENSES.yaml"
        report = check_licence.build_report(
            gitfix.REPO_ROOT, policy, base=None
        )
        self.assertTrue(report.ok, report.render())
        restricted = [
            check
            for check in report.checks
            if check["id"].startswith(("content.restricted_kind", "inventory.coverage"))
            and not check["ok"]
        ]
        self.assertEqual(restricted, [])


if __name__ == "__main__":
    unittest.main()
