"""Guards for the HOMEPAGE-001 site figures.

The figures under ``docs/assets/figures/`` are generated artifacts: every label
is parsed from ``docs/DATA.md`` (generated stats block) and ``docs/metrics.json``
(``trading.event_study``) by ``tools/site/make_figures.py``. These tests fail
when the art is stale, malformed, not self-contained, or no longer agrees with
the committed data --- editing the data without re-running the generator is a
test failure, not a silently wrong chart.
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIG_DIR = ROOT / "docs" / "assets" / "figures"
GENERATOR = ROOT / "tools" / "site" / "make_figures.py"
SVG_NS = "{http://www.w3.org/2000/svg}"

# expected canvas heights (viewBox width is 860 for every figure)
EXPECTED = {
    "coverage-en.svg": 420,
    "coverage-zh.svg": 420,
    "sources-en.svg": 420,
    "sources-zh.svg": 420,
    "event-study-en.svg": 460,
}

FOOTNOTE = ("in-sample simulation \u00b7 n=61 at +60 d \u00b7 no independent public "
            "time in the snapshot \u00b7 not a point-in-time or predictive result")

SOURCE_LABELS = {
    "openfda_device_510k": (
        "openFDA device 510(k)", "openFDA 器械 510(k)"),
    "openfda_device_recall": ("openFDA device recall", "openFDA 器械召回"),
    "openfda_device_pma": ("openFDA device PMA", "openFDA 器械 PMA"),
    "ctgov": ("ClinicalTrials.gov v2", "ClinicalTrials.gov v2"),
    "sec_edgar_corpus": ("SEC EDGAR 8-K corpus", "SEC EDGAR 8-K 语料"),
    "openfda_drug_drugsfda": ("openFDA drugsfda", "openFDA 药品批准"),
}


# ---------------------------------------------------------------- helpers
def load_generator():
    spec = importlib.util.spec_from_file_location("site_make_figures", GENERATOR)
    if spec is None or spec.loader is None:      # pragma: no cover - import guard
        raise AssertionError(f"cannot import {GENERATOR}")
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves postponed annotations through sys.modules, so the
    # module must be registered before it is executed.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_svg(name: str) -> ET.Element:
    return ET.parse(FIG_DIR / name).getroot()


def svg_texts(root: ET.Element) -> list[str]:
    return ["".join(element.itertext()) for element in root.iter(SVG_NS + "text")]


def joined_text(name: str) -> str:
    return "\n".join(svg_texts(read_svg(name)))


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u2212", "-").replace("\u2013", "-")).strip()


def count(value: int) -> str:
    return f"{value:,}"


def pct(value: float) -> str:
    """Mirror the figure's percent formatting: one decimal pair, signed, % suffix."""
    return f"{value * 100:+.2f}".replace("-", "\u2212") + " %"


def tstat(value: float) -> str:
    return f"{value:.2f}".replace("-", "\u2212")


def data_md_tables() -> dict:
    """Independently parse docs/DATA.md (the generator has its own parser)."""
    text = (ROOT / "docs" / "DATA.md").read_text(encoding="utf-8")
    stats = text[text.index("<!-- stats:start -->"):text.index("<!-- stats:end -->")]

    total_match = re.search(r"\| 事件 `events` \| \*\*([\d,]+)\*\*", stats)
    date_match = re.search(r"生成于 (\d{4}-\d{2}-\d{2})T", stats)
    assert total_match and date_match, "docs/DATA.md stats block lost its total or date"
    total = int(total_match.group(1).replace(",", ""))
    snapshot_date = date_match.group(1)

    source_zone = stats[stats.index("### 来源与类型"):stats.index("### 覆盖年份")]
    sources = [
        {"key": key, "rows": int(rows.replace(",", "")),
         "first": int(first), "last": int(last)}
        for key, rows, first, last in re.findall(
            r"\| `([a-z0-9_]+)` \| `[a-z0-9_]+` \| ([\d,]+) \| "
            r"(\d{4})-\d{2}-\d{2} \u2192 (\d{4})-\d{2}-\d{2} \|",
            source_zone,
        )
    ]

    coverage_zone = stats[stats.index("### 覆盖年份"):stats.index("### 覆盖质量")]
    aggregate = re.search(r"\| (\d{4})\u2013(\d{4})（合计） \| ([\d,]+) \|", coverage_zone)
    assert aggregate, "docs/DATA.md coverage table lost its 1966-2015 aggregate row"
    yearly = [(year, int(value.replace(",", ""))) for year, value in re.findall(
        r"\| (\d{4}) \| ([\d,]+) \|", coverage_zone)]

    return {
        "total": total,
        "snapshot_date": snapshot_date,
        "aggregate_label": f"{aggregate.group(1)}\u2013{aggregate.group(2)}",
        "aggregate_value": int(aggregate.group(3).replace(",", "")),
        "yearly": yearly,
        "sources": sources,
    }


def event_study_horizons() -> dict[int, dict]:
    data = json.loads((ROOT / "docs" / "metrics.json").read_text(encoding="utf-8"))
    return {int(key): block for key, block in data["trading"]["event_study"]["horizons"].items()}


# ---------------------------------------------------------------- tests
class FigureArtifactTests(unittest.TestCase):
    def test_all_figures_exist_and_are_small(self):
        for name in EXPECTED:
            path = FIG_DIR / name
            self.assertTrue(path.is_file(), f"missing figure: {path}")
            self.assertLess(path.stat().st_size, 60 * 1024,
                            f"{name} exceeds the 60 KB budget")

    def test_generator_reproduces_committed_files_byte_for_byte(self):
        figures = load_generator().build_figures(ROOT)
        self.assertEqual(set(figures), {name[:-4] for name in EXPECTED})
        for name in EXPECTED:
            committed = (FIG_DIR / name).read_bytes()
            rendered = figures[name[:-4]].encode("utf-8")
            self.assertEqual(committed, rendered,
                             f"{name} is stale; run python tools/site/make_figures.py")
        self.assertEqual(figures, load_generator().build_figures(ROOT),
                         "figure rendering is not deterministic")

    def test_check_mode_exits_zero_on_clean_tree(self):
        result = subprocess.run(
            [sys.executable, str(GENERATOR), "--check"],
            cwd=ROOT, capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0,
                         f"--check failed:\n{result.stdout}\n{result.stderr}")
        self.assertIn("up to date", result.stdout)

    def test_svgs_are_well_formed_with_the_contract_viewbox(self):
        for name, height in EXPECTED.items():
            root = read_svg(name)
            self.assertEqual(root.tag, SVG_NS + "svg", f"{name} root is not <svg>")
            self.assertEqual(root.get("width"), "860", f"{name} width")
            self.assertEqual(root.get("height"), str(height), f"{name} height")
            self.assertEqual(root.get("viewBox"), f"0 0 860 {height}", f"{name} viewBox")
            self.assertEqual(root.get("role"), "img", f"{name} is missing role=img")
            title = root.find(SVG_NS + "title")
            desc = root.find(SVG_NS + "desc")
            self.assertIsNotNone(title, f"{name} has no <title>")
            self.assertIsNotNone(desc, f"{name} has no <desc>")
            self.assertTrue("".join(title.itertext()).strip(), f"{name} <title> is empty")
            self.assertGreater(len("".join(desc.itertext()).strip()), 40,
                               f"{name} <desc> is too thin for screen readers")

    def test_labels_are_at_least_ten_pixels(self):
        for name in EXPECTED:
            root = read_svg(name)
            for element in root.iter():
                size = element.get("font-size")
                if size is None:
                    continue
                self.assertGreaterEqual(float(size), 10,
                                        f"{name} has a label below the 10 px floor: {size}")

    def test_no_external_or_active_content(self):
        namespace = 'xmlns="http://www.w3.org/2000/svg"'
        for name in EXPECTED:
            markup = (FIG_DIR / name).read_text(encoding="utf-8").replace(namespace, "")
            lowered = markup.lower()
            for token in ("http://", "https://", "href=", "<image", "<script",
                          "<foreignobject", "@import", "url("):
                self.assertNotIn(token, lowered,
                                 f"{name} contains external or active content: {token}")

    def test_only_the_snapshot_date_appears_as_a_date(self):
        snapshot_date = data_md_tables()["snapshot_date"]
        for name in EXPECTED:
            found = set(re.findall(r"\d{4}-\d{2}-\d{2}",
                                   (FIG_DIR / name).read_text(encoding="utf-8")))
            self.assertLessEqual(found, {snapshot_date},
                                 f"{name} leaks a date that is not the snapshot date")


class CoverageFigureTests(unittest.TestCase):
    def setUp(self):
        self.data = data_md_tables()
        self.en = joined_text("coverage-en.svg")
        self.zh = joined_text("coverage-zh.svg")

    def test_coverage_table_is_internally_consistent(self):
        yearly_total = sum(value for _, value in self.data["yearly"])
        self.assertEqual(yearly_total + self.data["aggregate_value"], self.data["total"],
                         "docs/DATA.md coverage rows do not add up to the event total")
        self.assertEqual(len(self.data["yearly"]), 11, "expected 2016-2026 coverage rows")

    def test_every_number_is_drawn(self):
        drawn = [self.data["aggregate_value"]] + [value for _, value in self.data["yearly"]]
        drawn.append(self.data["total"])
        for value in drawn:
            self.assertIn(count(value), self.en, f"coverage-en.svg is missing {count(value)}")
            self.assertIn(count(value), self.zh, f"coverage-zh.svg is missing {count(value)}")

    def test_axes_and_captions(self):
        for chart in (self.en, self.zh):
            self.assertIn(self.data["snapshot_date"], chart)
            self.assertIn(self.data["aggregate_label"], chart)
            for year, _ in self.data["yearly"]:
                self.assertIn(year, chart)
        self.assertIn("Evidence coverage by event year", self.en)
        self.assertIn("按事件年份的证据覆盖", self.zh)
        self.assertIn("pre-2016 aggregate", self.en)
        self.assertIn("2016 年前合计", self.zh)


class SourcesFigureTests(unittest.TestCase):
    def setUp(self):
        self.data = data_md_tables()
        self.en = joined_text("sources-en.svg")
        self.zh = joined_text("sources-zh.svg")

    def test_six_sources_and_their_sum(self):
        self.assertEqual(len(self.data["sources"]), 6)
        self.assertEqual(sum(source["rows"] for source in self.data["sources"]),
                         self.data["total"], "docs/DATA.md source rows do not add up")

    def test_every_count_range_and_label_is_drawn(self):
        for source in self.data["sources"]:
            range_en = f"{source['first']} \u2192 {source['last']}"
            for chart in (self.en, self.zh):
                self.assertIn(count(source["rows"]), chart,
                              f"missing row count for {source['key']}")
                self.assertIn(range_en, chart,
                              f"missing date range for {source['key']}")
            label_en, label_zh = SOURCE_LABELS[source["key"]]
            self.assertIn(label_en, self.en, f"missing source label {source['key']}")
            self.assertIn(label_zh, self.zh, f"missing source label {source['key']}")
        for chart in (self.en, self.zh):
            self.assertIn(count(self.data["total"]), chart)
            self.assertIn(self.data["snapshot_date"], chart)
        self.assertIn("Six free public sources", self.en)
        self.assertIn("六个免费公开数据源", self.zh)


class EventStudyFigureTests(unittest.TestCase):
    def setUp(self):
        self.horizons = event_study_horizons()
        self.chart = joined_text("event-study-en.svg")

    def test_title_and_snapshot_numbers(self):
        self.assertIn("Direction-aligned abnormal return, by horizon", self.chart)
        self.assertEqual(sorted(self.horizons), [1, 5, 20, 60])

    def test_every_horizon_row_is_drawn_from_metrics(self):
        for days, block in sorted(self.horizons.items()):
            self.assertIn(f"+{days} d", self.chart, f"missing horizon +{days} d")
            self.assertIn(f"n = {block['n']}", self.chart, f"missing n for +{days} d")
            self.assertIn(pct(block["mean_ar"]), self.chart, f"missing mean for +{days} d")
            self.assertIn(f"t = {tstat(block['t'])}", self.chart, f"missing t for +{days} d")
            for bound in block["ci95"]:
                self.assertIn(pct(bound), self.chart,
                              f"missing CI bound for +{days} d")

    def test_only_sixty_days_survives_holm(self):
        self.assertEqual(self.chart.count("Holm: survives"), 1,
                         "exactly one horizon may survive Holm")
        self.assertEqual(self.chart.count("Holm: not significant"), 3)
        self.assertLess(self.chart.rindex("Holm: not significant"),
                        self.chart.index("Holm: survives"),
                        "the surviving row must be the +60 d row, drawn last")

    def test_caveat_is_inside_the_image(self):
        self.assertIn(normalise(FOOTNOTE), normalise(self.chart),
                      "the in-sample caveat must be part of the figure")
        self.assertIn("n=61 at +60 d", normalise(self.chart))


if __name__ == "__main__":
    unittest.main()
