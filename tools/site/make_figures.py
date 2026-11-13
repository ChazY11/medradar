"""Generate the HOMEPAGE-001 figures as deterministic SVG from the committed data.

The site is stdlib-only and makes zero external requests, so the figures are plain
SVG emitted by this script rather than by a plotting library. Every number is
parsed from the committed sources --- ``docs/DATA.md`` (generated stats block) and
``docs/metrics.json`` (``trading.event_study``) --- so a data edit cannot leave
stale art behind: ``--check`` re-renders in memory and fails when the checked-in
files differ.

Figures (written to ``docs/assets/figures/``):
    coverage-en.svg      events by event year, 1966-2015 aggregate (English)
    coverage-zh.svg      same chart, Chinese labels
    sources-en.svg        rows per free public source (English)
    sources-zh.svg        same chart, Chinese labels
    event-study-en.svg    direction-aligned abnormal return by horizon

Usage:
    python tools/site/make_figures.py            # (re)write the SVGs
    python tools/site/make_figures.py --check    # exit 1 if a committed SVG is stale

Output is byte-deterministic: no timestamps, no locale-dependent formatting, no
font measurement. The same source data always produces the same bytes.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[2]
FIG_DIR = ROOT / "docs" / "assets" / "figures"

# ---------------------------------------------------------------- design tokens
W = 860
INK = "#0B1220"
INK_2 = "#334155"
INK_3 = "#64748B"
LINE = "#E5EAF1"
LINE_STRONG = "#CBD5E1"
ACCENT = "#2B7FC4"
ACCENT_STRONG = "#1B5E96"
SURFACE = "#FFFFFF"
WARN = "#A9762A"
WARN_SOFT = "#FBF3E5"
GRAPHITE = "#94A3B8"

SANS = "Inter, -apple-system, Segoe UI, Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, Liberation Mono, monospace"

EN_DASH = "\u2013"
MIDDLE_DOT = " \u00b7 "
MINUS = "\u2212"
ARROW = " \u2192 "

# Only the +60 d horizon survives the Holm correction over the full
# category x horizon family (FACTS.md, README "The positive result, at its real
# size"). `trading.event_study` carries the estimates but no adjusted p-value,
# so the survival flag is declared here instead of being invented from |t| >= 1.96.
HOLM_SURVIVORS = frozenset({60})


class DataError(RuntimeError):
    """The committed data cannot support the figures (missing or inconsistent)."""


# ---------------------------------------------------------------- data model
@dataclass(frozen=True)
class YearBar:
    label: str
    value: int
    aggregate: bool = False


@dataclass(frozen=True)
class Source:
    key: str
    label_en: str
    label_zh: str
    rows: int
    first_year: int
    last_year: int


@dataclass(frozen=True)
class Horizon:
    days: int
    n: int
    mean: float          # fraction, e.g. 0.05648
    ci_low: float
    ci_high: float
    t: float


@dataclass(frozen=True)
class Snapshot:
    snapshot_date: str
    total: int
    aggregate_label: str
    aggregate_value: int
    yearly: tuple[YearBar, ...]
    sources: tuple[Source, ...]
    horizons: tuple[Horizon, ...]


SOURCE_LABELS = {
    "openfda_device_510k": ("openFDA device 510(k)", "openFDA 器械 510(k)"),
    "openfda_device_recall": ("openFDA device recall", "openFDA 器械召回"),
    "openfda_device_pma": ("openFDA device PMA", "openFDA 器械 PMA"),
    "ctgov": ("ClinicalTrials.gov v2", "ClinicalTrials.gov v2"),
    "sec_edgar_corpus": ("SEC EDGAR 8-K corpus", "SEC EDGAR 8-K 语料"),
    "openfda_drug_drugsfda": ("openFDA drugsfda", "openFDA 药品批准"),
}


# ---------------------------------------------------------------- parsing
def _stats_block(text: str) -> str:
    start = text.index("<!-- stats:start -->")
    end = text.index("<!-- stats:end -->")
    return text[start:end]


def parse_data_md(path: Path) -> dict:
    """Read the generated stats block of docs/DATA.md (single source of truth)."""
    text = path.read_text(encoding="utf-8")
    stats = _stats_block(text)

    date_match = re.search(r"生成于 (\d{4}-\d{2}-\d{2})T", stats)
    total_match = re.search(r"\| 事件 `events` \| \*\*([\d,]+)\*\* \|", stats)
    if not date_match or not total_match:
        raise DataError(f"{path}: snapshot date or event total not found in the stats block")
    snapshot_date = date_match.group(1)
    total = int(total_match.group(1).replace(",", ""))

    source_zone = _zone(stats, "### 来源与类型", "### 覆盖年份", path)
    sources = []
    for key, rows, first, last in re.findall(
        r"\| `([a-z0-9_]+)` \| `[a-z0-9_]+` \| ([\d,]+) \| (\d{4})-\d{2}-\d{2} \u2192 "
        r"(\d{4})-\d{2}-\d{2} \|",
        source_zone,
    ):
        if key not in SOURCE_LABELS:
            raise DataError(f"{path}: unknown source id {key!r}")
        label_en, label_zh = SOURCE_LABELS[key]
        sources.append(Source(key, label_en, label_zh, int(rows.replace(",", "")),
                              int(first), int(last)))

    coverage_zone = _zone(stats, "### 覆盖年份", "### 覆盖质量", path)
    aggregate_match = re.search(
        rf"\| (\d{{4}}){EN_DASH}(\d{{4}})（合计） \| ([\d,]+) \|", coverage_zone)
    if not aggregate_match:
        raise DataError(f"{path}: 1966-2015 aggregate row not found")
    aggregate_label = f"{aggregate_match.group(1)}{EN_DASH}{aggregate_match.group(2)}"
    aggregate_value = int(aggregate_match.group(3).replace(",", ""))
    yearly = tuple(
        YearBar(label=year, value=int(value.replace(",", "")))
        for year, value in re.findall(r"\| (\d{4}) \| ([\d,]+) \|", coverage_zone)
    )

    if len(sources) != 6:
        raise DataError(f"{path}: expected 6 sources, found {len(sources)}")
    if not yearly:
        raise DataError(f"{path}: no per-year coverage rows found")
    if sum(bar.value for bar in yearly) + aggregate_value != total:
        raise DataError(
            f"{path}: coverage rows sum to "
            f"{sum(bar.value for bar in yearly) + aggregate_value:,}, total is {total:,}")
    if sum(source.rows for source in sources) != total:
        raise DataError(
            f"{path}: source rows sum to {sum(source.rows for source in sources):,}, "
            f"total is {total:,}")

    return {
        "snapshot_date": snapshot_date,
        "total": total,
        "aggregate_label": aggregate_label,
        "aggregate_value": aggregate_value,
        "yearly": yearly,
        "sources": tuple(sources),
    }


def _zone(text: str, start: str, end: str, path: Path) -> str:
    try:
        return text[text.index(start):text.index(end)]
    except ValueError as exc:
        raise DataError(f"{path}: section {start!r} missing") from exc


def parse_metrics(path: Path) -> tuple[Horizon, ...]:
    """Read docs/metrics.json -> trading.event_study.horizons."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        raw = data["trading"]["event_study"]["horizons"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise DataError(f"{path}: trading.event_study.horizons unavailable ({exc})") from exc

    horizons = []
    for days in (1, 5, 20, 60):
        block = raw.get(str(days))
        if not isinstance(block, dict):
            raise DataError(f"{path}: horizon {days} d missing from the event study")
        try:
            horizon = Horizon(
                days=days,
                n=int(block["n"]),
                mean=float(block["mean_ar"]),
                ci_low=float(block["ci95"][0]),
                ci_high=float(block["ci95"][1]),
                t=float(block["t"]),
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise DataError(f"{path}: horizon {days} d is malformed ({exc})") from exc
        if not all(math.isfinite(value)
                   for value in (horizon.mean, horizon.ci_low, horizon.ci_high, horizon.t)):
            raise DataError(f"{path}: horizon {days} d contains a non-finite value")
        if horizon.ci_low > horizon.mean or horizon.ci_high < horizon.mean:
            raise DataError(f"{path}: horizon {days} d confidence interval misses the mean")
        horizons.append(horizon)
    return tuple(horizons)


def load_snapshot(root: Path = ROOT) -> Snapshot:
    docs = root / "docs"
    data = parse_data_md(docs / "DATA.md")
    horizons = parse_metrics(docs / "metrics.json")
    return Snapshot(
        snapshot_date=data["snapshot_date"],
        total=data["total"],
        aggregate_label=data["aggregate_label"],
        aggregate_value=data["aggregate_value"],
        yearly=data["yearly"],
        sources=data["sources"],
        horizons=horizons,
    )


# ---------------------------------------------------------------- SVG helpers
def _esc(text: object) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _g(value: float) -> str:
    """Compact deterministic coordinate: 40.0 -> '40', 12.25 -> '12.2'."""
    text = f"{value:.1f}"
    return text[:-2] if text.endswith(".0") else text


def _count(value: int) -> str:
    return f"{value:,}"


def _pct(value: float) -> str:
    return f"{value:+.2f}".replace("-", MINUS) + " %"


def _tstat(value: float) -> str:
    return f"{value:.2f}".replace("-", MINUS)


def _tspan(text: str, mono: bool) -> str:
    family = f' font-family="{MONO}"' if mono else ""
    return f"<tspan{family}>{_esc(text)}</tspan>"


def _runs(content: str | Sequence[tuple[str, bool]]) -> str:
    if isinstance(content, str):
        return _esc(content)
    return "".join(_tspan(text, mono) for text, mono in content)


def text(x: float, y: float, content: str | Sequence[tuple[str, bool]], *,
         size: float = 11, fill: str = INK_3, weight: int | None = None,
         anchor: str | None = None, mono: bool = False) -> str:
    attrs = [f'x="{_g(x)}"', f'y="{_g(y)}"', f'font-size="{_g(size)}"']
    if weight is not None:
        attrs.append(f'font-weight="{weight}"')
    if mono:
        attrs.append(f'font-family="{MONO}"')
    attrs.append(f'fill="{fill}"')
    if anchor is not None:
        attrs.append(f'text-anchor="{anchor}"')
    return f"<text {' '.join(attrs)}>{_runs(content)}</text>"


def rect(x: float, y: float, width: float, height: float, fill: str, *,
         rx: float | None = None) -> str:
    attrs = [f'x="{_g(x)}"', f'y="{_g(y)}"', f'width="{_g(width)}"',
             f'height="{_g(height)}"', f'fill="{fill}"']
    if rx is not None:
        attrs.append(f'rx="{_g(rx)}"')
    return f"<rect {' '.join(attrs)}/>"


def line(x1: float, y1: float, x2: float, y2: float, stroke: str, *,
         width: float = 1, dash: str | None = None) -> str:
    attrs = [f'x1="{_g(x1)}"', f'y1="{_g(y1)}"', f'x2="{_g(x2)}"', f'y2="{_g(y2)}"',
             f'stroke="{stroke}"', f'stroke-width="{_g(width)}"']
    if dash is not None:
        attrs.append(f'stroke-dasharray="{dash}"')
    return f"<line {' '.join(attrs)}/>"


def svg_open(title: str, desc: str, height: int) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height}" '
        f'viewBox="0 0 {W} {height}" role="img" font-family="{SANS}">',
        f"  <title>{_esc(title)}</title>",
        f"  <desc>{_esc(desc)}</desc>",
        f'  <rect width="{W}" height="{height}" fill="{SURFACE}"/>',
    ]


def svg_close(parts: list[str]) -> str:
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _with_date(snapshot: Snapshot, template: str) -> list[tuple[str, bool]]:
    """Split a caption template into runs, rendering each ``{date}`` in mono."""
    runs: list[tuple[str, bool]] = []
    for index, chunk in enumerate(template.split("{date}")):
        if index:
            runs.append((snapshot.snapshot_date, True))
        if chunk:
            runs.append((chunk, False))
    return runs


# ---------------------------------------------------------------- coverage
COVERAGE_HEIGHT = 420
COVERAGE_BASELINE = 348
COVERAGE_TOP = 96
YEAR_SLOT = 62
AGGREGATE_SLOT = 98
YEAR_BAR = 40
AGGREGATE_BAR = 62


def render_coverage(snapshot: Snapshot, lang: str) -> str:
    en = lang == "en"
    last_year = snapshot.yearly[-1].label
    bars = list(snapshot.yearly) + [
        YearBar(snapshot.aggregate_label, snapshot.aggregate_value, aggregate=True)
    ]
    plot_height = COVERAGE_BASELINE - COVERAGE_TOP
    scale = plot_height / max(bar.value for bar in bars)

    if en:
        title = "Evidence coverage by event year"
        subtitle = _with_date(
            snapshot, "source: docs/DATA.md \u00b7 snapshot {date} \u00b7 "
        ) + [(_count(snapshot.total), True), (" events", False)]
        total_note = [(_count(snapshot.total), True), (" total", False)]
        aggregate_note = "pre-2016 aggregate"
        partial = _with_date(snapshot, f"{last_year} is a partial year (snapshot {{date}}).")
        desc = (
            f"Bar chart of all {_count(snapshot.total)} events in the MedRadar snapshot by event "
            f"year. The {snapshot.aggregate_label} aggregate is {_count(snapshot.aggregate_value)} "
            f"events; {snapshot.yearly[0].label} to {last_year} range from "
            f"{_count(min(bar.value for bar in snapshot.yearly))} to "
            f"{_count(max(bar.value for bar in snapshot.yearly))} events per year. "
            f"{last_year} is a partial year (snapshot {snapshot.snapshot_date})."
        )
    else:
        title = "按事件年份的证据覆盖"
        subtitle = _with_date(
            snapshot, "来源：docs/DATA.md \u00b7 快照 {date} \u00b7 "
        ) + [(_count(snapshot.total), True), (" 个事件", False)]
        total_note = [(_count(snapshot.total), True), (" 个事件（共）", False)]
        aggregate_note = "2016 年前合计"
        partial = _with_date(snapshot, f"{last_year} 年为部分年度（快照 {{date}}）。")
        desc = (
            f"按事件年份统计 MedRadar 快照全部 {_count(snapshot.total)} 个事件的柱状图。"
            f"{snapshot.aggregate_label} 合计 {_count(snapshot.aggregate_value)} 个事件；"
            f"{snapshot.yearly[0].label} 至 {last_year} 年每年介于 "
            f"{_count(min(bar.value for bar in snapshot.yearly))} 至 "
            f"{_count(max(bar.value for bar in snapshot.yearly))} 个事件之间。"
            f"{last_year} 年为部分年度（快照 {snapshot.snapshot_date}）。"
        )

    parts = svg_open(title, desc, COVERAGE_HEIGHT)
    parts.append(text(40, 38, title, size=19, fill=INK, weight=600))
    parts.append(text(40, 58, subtitle, size=11.5, fill=INK_3))
    parts.append(text(820, 58, total_note, size=10.5, fill=INK_2, anchor="end"))

    # 1 px grid every 50k events: structure for the tall aggregate column, no y-axis.
    for step in range(50_000, snapshot.aggregate_value, 50_000):
        grid_y = COVERAGE_BASELINE - step * scale
        parts.append(line(40, grid_y, 820, grid_y, LINE))

    # A dashed rule separates the 11 recent years from the 50-year aggregate.
    parts.append(line(40 + YEAR_SLOT * len(snapshot.yearly), COVERAGE_TOP,
                      40 + YEAR_SLOT * len(snapshot.yearly), COVERAGE_BASELINE,
                      LINE, dash="3 4"))

    x_cursor = 40.0
    for bar in bars:
        slot = AGGREGATE_SLOT if bar.aggregate else YEAR_SLOT
        centre = x_cursor + slot / 2
        width = AGGREGATE_BAR if bar.aggregate else YEAR_BAR
        height = bar.value * scale
        top = COVERAGE_BASELINE - height
        fill = GRAPHITE if bar.aggregate else ACCENT
        parts.append(rect(centre - width / 2, top, width, height, fill, rx=1.5))
        parts.append(text(centre, top - 6, _count(bar.value), size=10, fill=INK_2,
                          anchor="middle", mono=True))
        parts.append(text(centre, 366, bar.label, size=10, fill=INK_3,
                          anchor="middle", mono=True))
        if bar.aggregate:
            parts.append(text(centre, 380, aggregate_note, size=10, fill=INK_3,
                              anchor="middle"))
        x_cursor += slot

    parts.append(line(40, COVERAGE_BASELINE, 820, COVERAGE_BASELINE, LINE_STRONG))
    parts.append(text(40, 404, partial, size=10.5, fill=INK_3))
    scale_note = ("zero-based scale \u00b7 the final bar aggregates 1966\u20132015, "
                  "the other bars are single years" if en else
                  "零基线 · 末柱为 1966\u20132015 合计，其余柱为单年")
    parts.append(text(820, 404, scale_note, size=10.5, fill=INK_3, anchor="end"))
    return svg_close(parts)


# ---------------------------------------------------------------- sources
SOURCES_HEIGHT = 420
SOURCE_ROW_TOP = 112
SOURCE_ROW_STEP = 46
SOURCE_LABEL_X = 40
SOURCE_BAR_X = 268
SOURCE_BAR_MAX = 352
SOURCE_BAR_HEIGHT = 18


def render_sources(snapshot: Snapshot, lang: str) -> str:
    en = lang == "en"
    if en:
        title = "Six free public sources"
        subtitle = _with_date(snapshot, "rows per source \u00b7 docs/DATA.md \u00b7 {date}")
        total_note = [(_count(snapshot.total), True), (" rows", False)]
        footer = "date range = first \u2192 last event date in the source"
    else:
        title = "六个免费公开数据源"
        subtitle = _with_date(snapshot, "各来源行数 \u00b7 docs/DATA.md \u00b7 {date}")
        total_note = [(_count(snapshot.total), True), (" 行（共）", False)]
        footer = "日期区间 = 该来源最早 \u2192 最晚事件日期"

    desc_parts = []

    for source in snapshot.sources:
        name = source.label_en if en else source.label_zh
        desc_parts.append(
            f"{name}: {_count(source.rows)} rows, {source.first_year}\u2192{source.last_year}")
    prefix = ("Horizontal bar chart of rows per free public source in the "
              f"{snapshot.snapshot_date} snapshot. " if en else
              f"{snapshot.snapshot_date} 快照中各免费公开数据源的行数横向柱状图。")
    desc = prefix + "; ".join(desc_parts) + f". Total {_count(snapshot.total)} rows."

    max_rows = max(source.rows for source in snapshot.sources)
    scale = SOURCE_BAR_MAX / max_rows
    parts = svg_open(title, desc, SOURCES_HEIGHT)
    parts.append(text(40, 38, title, size=19, fill=INK, weight=600))
    parts.append(text(40, 58, subtitle, size=11.5, fill=INK_3))
    parts.append(text(820, 58, total_note, size=10.5, fill=INK_2, anchor="end"))

    for index, source in enumerate(snapshot.sources):
        centre = SOURCE_ROW_TOP + SOURCE_ROW_STEP * index
        if index:
            parts.append(line(40, centre - SOURCE_ROW_STEP / 2, 820,
                              centre - SOURCE_ROW_STEP / 2, LINE))
        name = source.label_en if en else source.label_zh
        parts.append(text(SOURCE_LABEL_X, centre + 4, name, size=12.5, fill=INK_2))
        width = source.rows * scale
        parts.append(rect(SOURCE_BAR_X, centre - SOURCE_BAR_HEIGHT / 2, width,
                          SOURCE_BAR_HEIGHT, ACCENT, rx=1.5))
        parts.append(text(SOURCE_BAR_X + width + 8, centre + 4, _count(source.rows),
                          size=11, fill=INK_2, mono=True))
        parts.append(text(820, centre + 4, f"{source.first_year}{ARROW}{source.last_year}",
                          size=10.5, fill=INK_3, anchor="end", mono=True))

    parts.append(text(40, 396, footer, size=10.5, fill=INK_3))
    return svg_close(parts)


# ---------------------------------------------------------------- event study
EVENT_HEIGHT = 460
EVENT_ROW_TOP = 126
EVENT_ROW_STEP = 66
EVENT_LEFT = 170
EVENT_RIGHT = 660
EVENT_MIN = -2.0
EVENT_MAX = 11.0
EVENT_AXIS_Y = 366
EVENT_COLUMN_X = 688


def _event_x(value: float) -> float:
    return EVENT_LEFT + (value - EVENT_MIN) / (EVENT_MAX - EVENT_MIN) * (EVENT_RIGHT - EVENT_LEFT)


def render_event_study(snapshot: Snapshot) -> str:
    title = "Direction-aligned abnormal return, by horizon"
    subtitle = ("vs SPY \u00b7 95 % CI \u00b7 block bootstrap \u00b7 "
                "Holm over the category \u00d7 horizon family")
    rows = snapshot.horizons
    desc_lines = []
    for horizon in rows:
        holm = "survives Holm" if horizon.days in HOLM_SURVIVORS else "not significant after Holm"
        desc_lines.append(
            f"+{horizon.days} d: {_pct(horizon.mean * 100)} "
            f"[{_pct(horizon.ci_low * 100)}, {_pct(horizon.ci_high * 100)}], "
            f"n={horizon.n}, t={_tstat(horizon.t)} ({holm})")
    desc = ("Forest plot of direction-aligned mean abnormal returns with 95 % confidence "
            "intervals. " + "; ".join(desc_lines) + ". Only the +60 d horizon survives the "
            "Holm correction. In-sample simulation; not a point-in-time or predictive result.")

    parts = svg_open(title, desc, EVENT_HEIGHT)
    parts.append(text(40, 38, title, size=19, fill=INK, weight=600))
    parts.append(text(40, 58, subtitle, size=11.5, fill=INK_3))
    parts.append(text(40, 88, "mean \u00b7 95 % CI whisker \u00b7 n = events",
                      size=10.5, fill=INK_3))

    # vertical grid + axis ticks
    ticks = (-2, 0, 2, 4, 6, 8, 10)
    for tick in ticks:
        x = _event_x(tick)
        parts.append(line(x, 96, x, EVENT_AXIS_Y, LINE))
    parts.append(line(EVENT_LEFT, EVENT_AXIS_Y, EVENT_RIGHT, EVENT_AXIS_Y, LINE_STRONG))
    for tick in ticks:
        label = "0 %" if tick == 0 else f"{tick:+d} %".replace("-", MINUS)
        parts.append(text(_event_x(tick), 381, label, size=10, fill=INK_3,
                          anchor="middle", mono=True))

    # dashed zero line on top of the grid
    parts.append(line(_event_x(0), 96, _event_x(0), EVENT_AXIS_Y, GRAPHITE,
                      dash="4 4"))

    for index, horizon in enumerate(rows):
        centre = EVENT_ROW_TOP + EVENT_ROW_STEP * index
        survives = horizon.days in HOLM_SURVIVORS
        mark = ACCENT if survives else INK_3
        ink = ACCENT_STRONG if survives else INK_2
        if index:
            parts.append(line(40, centre - EVENT_ROW_STEP / 2, 820,
                              centre - EVENT_ROW_STEP / 2, LINE))

        parts.append(text(40, centre + 5, f"+{horizon.days} d", size=14,
                          fill=ink, weight=600))
        parts.append(text(40, centre + 24, f"n = {horizon.n}", size=10, fill=INK_3,
                          mono=True))

        x_low, x_high = _event_x(horizon.ci_low * 100), _event_x(horizon.ci_high * 100)
        x_mean = _event_x(horizon.mean * 100)
        parts.append(line(x_low, centre, x_high, centre, mark, width=1.6))
        for edge in (x_low, x_high):
            parts.append(line(edge, centre - 5, edge, centre + 5, mark, width=1.6))
        parts.append(f'<circle cx="{_g(x_mean)}" cy="{_g(centre)}" r="4.5" '
                     f'fill="{mark}" stroke="{SURFACE}" stroke-width="1.2"/>')
        parts.append(text(x_mean, centre - 13, _pct(horizon.mean * 100), size=11,
                          fill=ink, anchor="middle", mono=True))
        parts.append(text((x_low + x_high) / 2, centre + 21,
                          f"CI {_pct(horizon.ci_low * 100)} \u2026 {_pct(horizon.ci_high * 100)}",
                          size=10, fill=INK_3, anchor="middle", mono=True))

        parts.append(text(EVENT_COLUMN_X, centre - 5, f"t = {_tstat(horizon.t)}",
                          size=11, fill=INK_2, mono=True))
        holm_text = "Holm: survives" if survives else "Holm: not significant"
        parts.append(text(EVENT_COLUMN_X, centre + 13, holm_text, size=10.5,
                          fill=ACCENT_STRONG if survives else INK_3,
                          weight=600 if survives else None))

    # The caveat is part of the figure, not a caption: it must travel with the art.
    caveat = ("in-sample simulation \u00b7 n=61 at +60 d \u00b7 no independent public time "
              "in the snapshot \u00b7 not a point-in-time or predictive result")
    parts.append(rect(32, 404, 796, 42, WARN_SOFT, rx=6))
    parts.append(rect(32, 404, 3, 42, WARN, rx=1.5))
    parts.append(text(48, 430, caveat, size=11, fill=INK_2, weight=500))
    return svg_close(parts)


# ---------------------------------------------------------------- driver
def build_figures(root: Path = ROOT) -> dict[str, str]:
    snapshot = load_snapshot(root)
    return {
        "coverage-en": render_coverage(snapshot, "en"),
        "coverage-zh": render_coverage(snapshot, "zh"),
        "sources-en": render_sources(snapshot, "en"),
        "sources-zh": render_sources(snapshot, "zh"),
        "event-study-en": render_event_study(snapshot),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="re-render in memory and exit non-zero if a committed SVG differs")
    args = parser.parse_args(argv)

    try:
        figures = build_figures(ROOT)
    except DataError as exc:
        print(f"data error: {exc}", file=sys.stderr)
        return 2

    fig_dir = ROOT / "docs" / "assets" / "figures"
    if args.check:
        stale = []
        for name, markup in figures.items():
            path = fig_dir / f"{name}.svg"
            if not path.exists():
                stale.append(f"{name}.svg: missing")
            elif path.read_bytes() != markup.encode("utf-8"):
                stale.append(f"{name}.svg: differs from a fresh render")
        extra = sorted(path.name for path in fig_dir.glob("*.svg")
                       if path.stem not in figures)
        if stale or extra:
            for item in stale:
                print(f"stale: {item}", file=sys.stderr)
            for item in extra:
                print(f"unexpected: {item}", file=sys.stderr)
            print("run: python tools/site/make_figures.py", file=sys.stderr)
            return 1
        print(f"figures up to date ({len(figures)} files)")
        return 0

    fig_dir.mkdir(parents=True, exist_ok=True)
    for name, markup in figures.items():
        path = fig_dir / f"{name}.svg"
        path.write_bytes(markup.encode("utf-8"))
        print(f"wrote {path.relative_to(ROOT).as_posix()} "
              f"({len(markup.encode('utf-8'))} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
