"""Offline tests for the Chinese report, English one-pager and HTML dashboard.

Everything here is hermetic: the fixture is a hand-written ``metrics.json`` that
covers every field of ``docs/SCHEMA.md`` (including the "NMPA unavailable"
scenario), and ``build_report`` is pointed at a temporary directory so running
the suite can never clobber the real ``docs/index.html``.
"""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

from medradar.report import CHAPTERS_ZH, build_report

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "metrics_sample.json"

#: The original twelve chapters (semantic names, numbering stripped) must keep
#: their relative order after the W5 chapters are inserted between them.
ORIGINAL_CHAPTERS = (
    "本期结论",
    "数据状态",
    "赛道热度榜",
    "大厂动量",
    "结构迁移",
    "本周/本期首次出现",
    "召回与风险",
    "药品侧",
    "中国空白度",
    "信号与模拟盘",
    "方法与局限",
    "免责声明",
)


def _chapter_body(title: str) -> str:
    """``六、结构迁移`` -> ``结构迁移`` (numbering-independent comparison)."""
    return re.sub(r"^[一二三四五六七八九十百]+、", "", title)


def _headings(markdown_text: str) -> list[str]:
    return re.findall(r"^## (.+)$", markdown_text, flags=re.MULTILINE)

#: HTML void elements, plus SVG children our generator self-closes.
VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


class _BalanceParser(HTMLParser):
    """Tiny structural checker: reports unbalanced or unexpected closing tags."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.errors: list[str] = []
        self.tags: set[str] = set()
        self.stack: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: D401 - HTMLParser API
        self.tags.add(tag)
        if tag not in VOID_TAGS:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs) -> None:  # noqa: D401
        self.tags.add(tag)

    def handle_endtag(self, tag: str) -> None:  # noqa: D401
        if tag in VOID_TAGS:
            return
        if not self.stack:
            self.errors.append(f"unexpected closing tag </{tag}>")
            return
        if self.stack[-1] == tag:
            self.stack.pop()
            return
        if tag in self.stack:
            while self.stack and self.stack[-1] != tag:
                self.errors.append(f"unclosed <{self.stack.pop()}> before </{tag}>")
            if self.stack:
                self.stack.pop()
        else:
            self.errors.append(f"unmatched closing tag </{tag}>")


def _parse(html_text: str) -> _BalanceParser:
    parser = _BalanceParser()
    parser.feed(html_text)
    parser.close()
    parser.errors.extend(f"unclosed <{tag}>" for tag in parser.stack)
    return parser


class ReportBuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        cls.out = cls.tmp / "out"
        cls.docs = cls.tmp / "docs"
        cls.result = build_report(FIXTURE, cls.out, docs_dir=cls.docs)
        cls.zh = (cls.out / "report_zh.md").read_text(encoding="utf-8")
        cls.en = (cls.out / "report_en.md").read_text(encoding="utf-8")
        cls.html = (cls.out / "index.html").read_text(encoding="utf-8")
        cls.csv_bytes = (cls.out / "summary.csv").read_bytes()
        cls.metrics = json.loads(FIXTURE.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    # ------------------------------------------------------------------ artefacts
    def test_outputs_exist(self) -> None:
        for name in ("report_zh.md", "report_en.md", "index.html", "summary.csv"):
            self.assertTrue((self.out / name).is_file(), f"missing {name}")
        self.assertTrue((self.out / "index.html").stat().st_size > 5000)
        self.assertGreater(self.result["html_lines"], 100)
        self.assertEqual(self.result["chapters_zh"], len(CHAPTERS_ZH))
        self.assertEqual(len(CHAPTERS_ZH), 18, "twelve original chapters + six W5 chapters")

    def test_docs_entry_point_is_copied_verbatim(self) -> None:
        docs_html = (self.docs / "index.html").read_text(encoding="utf-8")
        self.assertEqual(docs_html, self.html)
        self.assertTrue((self.docs / ".nojekyll").exists())
        self.assertEqual((self.docs / ".nojekyll").read_text(encoding="utf-8"), "")

    def test_report_zh_has_eighteen_chapters_and_keeps_original_order(self) -> None:
        headings = _headings(self.zh)
        self.assertEqual(len(headings), 18, f"got {headings}")
        for index, title in enumerate(CHAPTERS_ZH):
            self.assertEqual(headings[index], title)
            self.assertIn(f"## {title}", self.zh)
        bodies = [_chapter_body(title) for title in headings]
        positions = [bodies.index(name) for name in ORIGINAL_CHAPTERS]
        self.assertEqual(positions, sorted(positions), "original 12 chapters must keep their order")
        self.assertTrue(self.zh.startswith("# "), "Chinese report needs a level-1 title")
        self.assertGreater(len(self.zh.splitlines()), 100)

    def test_english_report_is_one_page(self) -> None:
        self.assertIn("MedRadar", self.en)
        self.assertIn("China gap", self.en)
        self.assertIn("unavailable", self.en.lower())
        self.assertLessEqual(len(self.en.splitlines()), 120, "English report should stay one page")
        self.assertTrue(self.en.startswith("# "))

    # ----------------------------------------------------------------------- HTML
    def test_html_is_self_contained(self) -> None:
        lowered = self.html.lower()
        self.assertNotIn("http://", lowered)
        self.assertNotIn("https://", lowered)
        self.assertNotIn("<link", lowered)
        self.assertNotIn("@import", lowered)
        self.assertNotIn("src=", lowered)
        self.assertNotIn("cdn.", lowered)
        # exactly one inline script block, no module imports
        self.assertEqual(lowered.count("<script"), 1)
        self.assertIn("<style>", lowered)

    def test_html_parses_and_is_balanced(self) -> None:
        parser = _parse(self.html)
        self.assertEqual(parser.errors, [])
        for tag in ("html", "head", "body", "table", "svg", "footer", "section"):
            self.assertIn(tag, parser.tags)
        self.assertTrue(self.html.lstrip().startswith("<!DOCTYPE html>"))

    def test_html_contains_required_visual_blocks(self) -> None:
        for marker in (
            "数据状态",
            "本期结论",
            "赛道热度榜",
            "大厂动量",
            "产品族热度与新势力",
            "结构迁移",
            "公司产品组合迁移",
            "本周新品雷达",
            "首次出现",
            "召回与风险",
            "药品侧",
            "中国空白度",
            "信号与模拟盘",
            "回放研究",
            "时间质量与样本划分",
            "多重检验与生存偏差",
            "方法与局限",
            "免责声明",
        ):
            self.assertIn(marker, self.html)
        # status bar, KPI cards, generated SVG charts, timeline and equity polyline
        self.assertRegex(self.html, r'class="statusbar (green|amber|red)"')
        self.assertIn('class="kpi"', self.html)
        self.assertIn('<svg class="chart"', self.html)
        self.assertIn('aria-label="产品族热度条"', self.html)
        self.assertIn('<ol class="timeline">', self.html)
        self.assertIn("<polyline", self.html)
        self.assertIn("@media (max-width:760px)", self.html)

    # ------------------------------------------------------------- honesty rules
    def test_cn_gap_unavailable_is_explicit(self) -> None:
        phrase = "不可用（NMPA 数据未加载）"
        self.assertIn(phrase, self.zh)
        self.assertIn(phrase, self.html)
        self.assertIn("中国空白度不可用（NMPA 数据未加载）", self.html)
        # null must not be rendered as a zero registration count
        self.assertIn("不以 0 代替", self.zh)
        self.assertIn("不以 0 代替", self.html)
        self.assertNotIn("cn_count=0", self.csv_text())
        self.assertIn("cn_count=null", self.csv_text())

    def test_loaded_cn_row_still_shows_real_numbers(self) -> None:
        # The fixture has one genuinely loaded row with 12 registrations.
        self.assertIn(">12</td>", self.html)
        self.assertIn("cn_data_status=loaded", self.csv_text())

    def test_no_data_fallbacks(self) -> None:
        self.assertIn("暂无数据", self.zh)
        self.assertIn("暂无数据", self.html)

    # --------------------------------------------------- W5 research blocks
    def test_w5_blocks_degrade_gracefully(self) -> None:
        payload = {
            key: value
            for key, value in self.metrics.items()
            if key not in ("products", "replay", "timestamps", "research")
        }
        metrics_path = self.tmp / "metrics_no_w5.json"
        metrics_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        target = self.tmp / "out_no_w5"
        result = build_report(metrics_path, target, docs_dir=self.tmp / "docs_no_w5")
        zh = (target / "report_zh.md").read_text(encoding="utf-8")
        page = (target / "index.html").read_text(encoding="utf-8")
        self.assertEqual(len(_headings(zh)), 18)
        for marker in (
            "产品族热度与新势力",
            "本周新品雷达",
            "回放研究",
            "时间质量与样本划分",
            "多重检验与生存偏差",
        ):
            self.assertIn(marker, zh)
        self.assertIn("暂无数据", zh)
        self.assertIn("暂无数据", page)
        self.assertGreaterEqual(page.count("暂无数据"), 5)
        self.assertEqual(_parse(page).errors, [])
        self.assertEqual(result["product_families"], 0)
        self.assertEqual(result["replay_steps"], 0)

    def test_product_families_and_new_products_rendered(self) -> None:
        self.assertIn("脉冲场消融发生器", self.zh)
        self.assertIn("手术机器人机械臂", self.zh)
        self.assertIn('aria-label="产品族热度条"', self.html)
        self.assertIn('class="radar"', self.html)
        self.assertIn("脉冲场消融发生器（带接触力感应）", self.html)
        self.assertIn("K242001", self.html)
        self.assertEqual(self.result["product_families"], 4)
        self.assertEqual(self.result["new_products"], 3)
        self.assertEqual(self.result["company_portfolio"], 3)

    def test_new_products_show_chinese_name_use_and_source(self) -> None:
        for text in ("中文产品名", "用途 / 定义", "510(k)/PMA", "来源："):
            self.assertIn(text, self.html)
        # source URLs are displayed scheme-stripped so the page stays self-contained
        self.assertIn("www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID=K242001", self.html)
        self.assertNotIn("https://", self.html.lower())
        self.assertNotIn("http://", self.html.lower())
        self.assertIn("皮下植入式葡萄糖传感器", self.html)

    def test_replay_timeline_and_cost_buckets(self) -> None:
        self.assertIn('<ol class="timeline">', self.html)
        self.assertIn("成交价", self.html)
        self.assertIn("多档交易成本", self.html)
        for bucket in ("10 bps", "25 bps", "50 bps"):
            self.assertIn(bucket, self.html)
        # direction must not rely on colour alone: glyphs + signed text
        self.assertIn("▲", self.html)
        self.assertIn("▼", self.html)
        self.assertIn("+4.1%", self.html)
        self.assertIn("-1.1%", self.html)
        self.assertIn("回放研究", self.zh)
        self.assertEqual(self.result["replay_steps"], 4)
        self.assertIn("docs/ASSUMPTIONS.md", self.zh)

    def test_timestamps_quality_and_sample_split(self) -> None:
        for text in ("时间质量", "精确时间戳", "样本划分", "回测只使用 available_at"):
            self.assertIn(text, self.zh)
        self.assertIn("时间质量分布", self.html)
        self.assertIn("不进入交易研究的事件", self.html)
        self.assertIn("train", self.html)
        self.assertIn("test", self.html)
        self.assertEqual(self.result["timestamp_quality"], 4)

    def test_assumptions_link_and_research_quality(self) -> None:
        self.assertIn('href="docs/ASSUMPTIONS.md"', self.html)
        self.assertIn("假设登记表", self.html)
        self.assertIn("holm", self.html)
        self.assertIn("生存偏差", self.html)
        self.assertIn("多重检验", self.zh)
        self.assertIn("生存偏差", self.zh)
        self.assertNotIn("http://", self.html.lower())
        self.assertNotIn("https://", self.html.lower())

    # ------------------------------------------------------------------------ CSV
    def test_summary_csv_is_excel_friendly(self) -> None:
        self.assertTrue(self.csv_bytes.startswith(b"\xef\xbb\xbf"), "summary.csv needs a UTF-8 BOM")
        text = self.csv_bytes.decode("utf-8-sig")
        lines = text.splitlines()
        self.assertGreater(len(lines), 10)
        header = lines[0].split(",")
        self.assertEqual(header[0], "section")
        self.assertIn("device_track", text)
        self.assertIn("device_company", text)
        self.assertIn("drug_approval", text)
        self.assertIn("cn_gap", text)
        # every row has the same column count (no embedded unquoted commas)
        expected = len(header)
        for line in lines:
            if not line:
                continue
            self.assertEqual(len(next(_csv_rows(line))), expected, f"bad row: {line[:80]}")

    def csv_text(self) -> str:
        return self.csv_bytes.decode("utf-8-sig")

    # ------------------------------------------------------------- degradation
    def test_missing_and_empty_metrics_do_not_crash(self) -> None:
        cases = {
            "empty": {},
            "partial": {
                "meta": {"data_status": {"nmpa": "unavailable"}},
                "device": {"tracks": [{"track_id": "unknown_track"}]},
                "cn_gap": [{"track_id": "x", "cn_count": None, "cn_data_status": "unavailable"}],
            },
            "no_trading": {
                key: value for key, value in self.metrics.items() if key != "trading"
            },
        }
        for label, payload in cases.items():
            with self.subTest(label=label):
                metrics_path = self.tmp / f"metrics_{label}.json"
                metrics_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                target = self.tmp / f"out_{label}"
                result = build_report(metrics_path, target, docs_dir=self.tmp / f"docs_{label}")
                zh = (target / "report_zh.md").read_text(encoding="utf-8")
                page = (target / "index.html").read_text(encoding="utf-8")
                self.assertEqual(len(re.findall(r"^## ", zh, flags=re.MULTILINE)), 18)
                self.assertIn("暂无数据", zh)
                self.assertIn("暂无数据", page)
                self.assertEqual(_parse(page).errors, [])
                self.assertEqual(result["chapters_zh"], 18)

    def test_trading_insufficient_data_gets_explicit_message(self) -> None:
        payload = {
            "meta": {"data_status": {"nmpa": "unavailable", "prices": "missing"}},
            "trading": {"status": "insufficient_data"},
        }
        metrics_path = self.tmp / "metrics_insufficient.json"
        metrics_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        target = self.tmp / "out_insufficient"
        build_report(metrics_path, target, docs_dir=self.tmp / "docs_insufficient")
        page = (target / "index.html").read_text(encoding="utf-8")
        zh = (target / "report_zh.md").read_text(encoding="utf-8")
        self.assertIn("样本不足", page)
        self.assertIn("样本不足", zh)

    def test_unparsable_metrics_file_is_tolerated(self) -> None:
        bad = self.tmp / "metrics_broken.json"
        bad.write_text("{not valid json", encoding="utf-8")
        result = build_report(bad, self.tmp / "out_broken", docs_dir=self.tmp / "docs_broken")
        self.assertEqual(result["chapters_zh"], 18)
        self.assertTrue((self.tmp / "out_broken" / "index.html").is_file())
        self.assertTrue((self.tmp / "docs_broken" / "index.html").is_file())


def _csv_rows(line: str):
    """Minimal CSV line splitter honouring double quotes (test helper)."""
    import csv
    import io

    return csv.reader(io.StringIO(line))


if __name__ == "__main__":
    unittest.main()
