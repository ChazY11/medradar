"""Offline tests for the interactive single-file dashboard.

The dashboard is a static artefact built from three JSON inputs; these tests
build it from a tiny fixture and verify the *contract* (seven views, inline JSON,
interactive controls, zero external resources, graceful degradation) without a
browser. Browser behaviour is validated separately with Chromium.
"""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from medradar.dashboard import VIEWS, build_dashboard, render_dashboard_html

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "dashboard"
FIXTURE_METRICS = FIXTURE_DIR / "metrics.json"
FIXTURE_CASES = FIXTURE_DIR / "cases.json"
FIXTURE_REPLAY = FIXTURE_DIR / "replay.json"
FIXTURE_AUDIT = FIXTURE_DIR / "audit.json"

USER_URL_RE = re.compile(r"https?://[^\s\"'<>\\]+", re.IGNORECASE)
DATA_RE = re.compile(
    r'<script type="application/json" id="dashboard-data">(.*?)</script>',
    re.DOTALL,
)


class DashboardBuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        cls.out = cls.tmp / "dashboard.html"
        cls.result = build_dashboard(
            metrics_path=FIXTURE_METRICS,
            cases_path=FIXTURE_CASES,
            replay_path=FIXTURE_REPLAY,
            out_path=cls.out,
            audit_path=FIXTURE_AUDIT,
        )
        cls.html = cls.out.read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    # ------------------------------------------------------------------ structure
    def test_seven_views_and_navigation(self) -> None:
        self.assertEqual(list(VIEWS), ["overview", "tracks", "companies", "products", "cases", "replay", "data"])
        for view in VIEWS:
            self.assertIn(f'id="view-{view}"', self.html)
            self.assertIn(f'data-view="{view}"', self.html)
            self.assertIn(f'data-nav="{view}"', self.html)
        for title in ("概览", "赛道", "公司", "产品", "案例库", "回放", "数据"):
            self.assertIn(title, self.html)
        self.assertEqual(self.html.count('class="view"'), 7)

    def test_interactive_controls_present(self) -> None:
        for control in (
            'id="global-search"',
            'id="case-category"',
            'id="case-year"',
            'id="case-outcome"',
            'id="case-sort"',
            'id="cases-grid"',
            'id="case-dialog"',
            'id="replay-costs"',
            'id="replay-year"',
            'id="replay-kind"',
            'id="replay-chart"',
            'id="replay-table"',
            'id="theme-toggle"',
            'data-sort-table=',
            'showModal',
            "Escape",
            'location.hash',
            'history.replaceState',
            'localStorage',
            'price_source',
            '暂无数据',
        ):
            self.assertIn(control, self.html)
        for cost in ("10", "25", "50"):
            self.assertIn(f'data-cost="{cost}"', self.html)
        # a real detail drawer with evidence + price bars + source link
        for marker in ("逐字证据", "价格反应", "原文链接", "blockquote", "pricebar", "反例"):
            self.assertIn(marker, self.html)

    def test_noscript_fallback(self) -> None:
        self.assertIn("<noscript>", self.html)
        self.assertIn("需要启用 JavaScript", self.html)

    def test_data_view_sections(self) -> None:
        for marker in ("数据源状态", "覆盖率", "时间质量", "审计检查", "样本划分", "缺口说明", "回放方法与假设"):
            self.assertIn(marker, self.html)

    # ------------------------------------------------------------------ inline JSON
    def test_inline_json_is_valid_and_complete(self) -> None:
        match = DATA_RE.search(self.html)
        self.assertIsNotNone(match, "inline <script type=application/json> missing")
        data_text = match.group(1)
        payload = json.loads(data_text)
        self.assertIn("metrics", payload)
        self.assertIn("cases", payload)
        self.assertIn("replay", payload)
        self.assertEqual(payload["metrics"]["device"]["tracks"][0]["track_id"], "ep_pfa")
        self.assertEqual(len(payload["cases"]["selected"]), 3)
        self.assertEqual(len(payload["replay"]["steps"]), 3)
        self.assertIsNotNone(payload["audit"], "audit fixture should be embedded")
        self.assertEqual(payload["views"], list(VIEWS))
        self.assertEqual(payload["sources"]["metrics"]["exists"], True)
        # data cannot break out of the script element
        self.assertNotIn("</script>", data_text)

    def test_json_with_script_close_is_escaped(self) -> None:
        payload = {
            "generated_at": "2026-01-01",
            "views": list(VIEWS),
            "metrics": {"meta": {"title": "</script><script>alert(1)</script>"}},
            "cases": {},
            "replay": {},
            "data_stats": None,
            "audit": None,
            "sources": {},
        }
        html_doc = render_dashboard_html(payload)
        match = DATA_RE.search(html_doc)
        self.assertIsNotNone(match)
        self.assertNotIn("</script>", match.group(1))
        parsed = json.loads(match.group(1))
        self.assertIn("alert(1)", parsed["metrics"]["meta"]["title"])
        # only the two real closing tags remain: JSON payload + application script
        self.assertEqual(html_doc.count("</script>"), 2)

    # ---------------------------------------------------------------- zero deps
    def test_no_external_resources(self) -> None:
        lowered = self.html.lower()
        self.assertNotIn("<link", lowered)
        self.assertNotIn("@import", lowered)
        self.assertNotIn("src=", lowered)
        self.assertNotIn("cdn.", lowered)
        self.assertNotIn("unpkg", lowered)
        self.assertNotIn("googleapis", lowered)
        self.assertNotIn("<iframe", lowered)
        # user data contains source URLs; after stripping those, no remote refs remain
        stripped = USER_URL_RE.sub("", self.html)
        self.assertNotIn("http://", stripped.lower())
        self.assertNotIn("https://", stripped.lower())
        # the only two scripts are inline (JSON payload + application code)
        self.assertEqual(self.html.count("<script"), 2)
        self.assertIn("<style>", self.html)

    def test_output_size_and_single_file(self) -> None:
        self.assertTrue(self.out.is_file())
        self.assertLessEqual(self.result["bytes"], 8 * 1024 * 1024)
        self.assertEqual(self.result["views"], list(VIEWS))
        self.assertEqual(self.result["cases"], 3)
        self.assertEqual(self.result["negative_cases"], 1)
        self.assertEqual(self.result["replay_steps"], 3)
        self.assertGreater(self.result["inline_data_bytes"], 1000)
        self.assertTrue(self.html.lstrip().startswith("<!DOCTYPE html>"))
        self.assertIn("MedRadar 交互式看板", self.html)

    # --------------------------------------------------------------- degradation
    def test_missing_blocks_degrade_gracefully(self) -> None:
        empty_dir = self.tmp / "empty"
        empty_dir.mkdir()
        empty_metrics = empty_dir / "metrics.json"
        empty_cases = empty_dir / "cases.json"
        empty_replay = empty_dir / "replay.json"
        for path in (empty_metrics, empty_cases, empty_replay):
            path.write_text("{}", encoding="utf-8")
        target = self.tmp / "empty.html"
        result = build_dashboard(
            metrics_path=empty_metrics,
            cases_path=empty_cases,
            replay_path=empty_replay,
            out_path=target,
        )
        page = target.read_text(encoding="utf-8")
        self.assertTrue(target.is_file())
        self.assertEqual(result["cases"], 0)
        self.assertEqual(result["replay_steps"], 0)
        self.assertEqual(len(result["views"]), 7)
        self.assertIn("暂无数据", page)

    def test_nonexistent_input_paths_do_not_crash(self) -> None:
        target = self.tmp / "missing.html"
        result = build_dashboard(
            metrics_path=self.tmp / "nope-metrics.json",
            cases_path=self.tmp / "nope-cases.json",
            replay_path=self.tmp / "nope-replay.json",
            out_path=target,
        )
        self.assertTrue(target.is_file())
        self.assertEqual(result["cases"], 0)
        page = target.read_text(encoding="utf-8")
        match = DATA_RE.search(page)
        self.assertIsNotNone(match)
        payload = json.loads(match.group(1))
        self.assertEqual(payload["metrics"], {})
        self.assertIn('id="view-overview"', page)

    def test_default_out_path_and_local_cli_example(self) -> None:
        module_path = Path(__file__).resolve().parents[1] / "medradar" / "dashboard.py"
        source = module_path.read_text(encoding="utf-8")
        self.assertIn('if __name__ == "__main__"', source)
        self.assertIn("def build_dashboard(", source)
        self.assertIn("def render_dashboard_html(", source)


if __name__ == "__main__":
    unittest.main()
