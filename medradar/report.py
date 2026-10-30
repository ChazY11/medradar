"""Chinese research report, English one-pager and a self-contained HTML dashboard.

The report stage is deliberately *read-only*: it consumes ``out/metrics.json``
(the data contract in ``docs/SCHEMA.md``) and nothing else. No network, no
database, no third-party libraries - just the standard library, because the
GitHub Action must be able to render the dashboard on a bare Python.

Design constraints that the offline test suite enforces:

* ``report_zh.md`` has exactly twelve chapters, in the fixed order.
* ``index.html`` is **fully self-contained**: inline CSS, inline vanilla JS and
  server-side generated SVG. It must not reference a CDN, an external font or
  any remote resource - it is served from GitHub Pages and has to work offline.
* ``cn_data_status == "unavailable"`` is reported as
  "不可用（NMPA 数据未加载）"; a ``null`` China count is never rendered as ``0``.
* Missing fields / empty lists degrade to "暂无数据" instead of raising.

``build_report`` returns a small machine-readable summary (paths, counts,
status) which the CLI prints as JSON.
"""

from __future__ import annotations

import csv
import html
import io
import math
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .config import DEFAULT_METRICS, DOCS_DIR, OUT_DIR
from .util import ensure_dir, read_json, write_text

DASH = "暂无数据"
MAX_TRACK_ROWS = 24
MAX_COMPANY_ROWS = 20
MAX_FIRSTSEEN_ROWS = 20
MAX_SIGNAL_ROWS = 20
MAX_FAMILY_ROWS = 20
MAX_PRODUCT_ROWS = 20
MAX_REPLAY_STEPS = 24
MAX_CASE_CARDS = 5
MAX_NEGATIVE_CASES = 3

#: Fixed chapter names of the Chinese report (asserted by tests). The original
#: twelve chapters keep their relative order; research-grade blocks are inserted.
CHAPTERS_ZH: tuple[str, ...] = (
    "一、本期结论",
    "二、数据状态",
    "三、赛道热度榜",
    "四、大厂动量",
    "五、产品族热度与新势力",
    "六、结构迁移",
    "七、公司产品组合迁移",
    "八、本周新品雷达",
    "九、本周/本期首次出现",
    "十、召回与风险",
    "十一、药品侧",
    "十二、中国空白度",
    "十三、信号与模拟盘",
    "十四、回放研究",
    "十五、案例库与证据",
    "十六、时间质量与样本划分",
    "十七、多重检验与生存偏差",
    "十八、方法与局限",
    "十九、免责声明",
)

SOURCE_LABELS = {
    "device": "器械（openFDA 510(k)/PMA/召回）",
    "drug": "药品（openFDA Drugs@FDA）",
    "trials": "临床试验（ClinicalTrials.gov）",
    "nmpa": "中国 NMPA 注册证",
    "prices": "美股价格（Yahoo）",
}

KIND_LABELS = {
    "510k": "510(k) 清关",
    "pma": "PMA 批准",
    "device_recall": "器械召回",
    "drug_approval": "药品批准",
    "trial": "临床试验启动",
    "nmpa_registration": "NMPA 注册",
    "device_new_track": "新赛道进入",
    "device_novel_code": "新产品码",
    "trial_start": "试验启动",
    "recall_cluster": "召回聚集",
}

PHASE_LABELS = {"PHASE1": "1 期", "PHASE2": "2 期", "PHASE3": "3 期", "PHASE4": "4 期", "EARLY_PHASE1": "早期 1 期"}

TREND_UP = "升温"
TREND_DOWN = "降温"
TREND_FLAT = "平稳"

_LEVEL_TAGS = {
    "high": "〔重点〕",
    "critical": "〔重点〕",
    "urgent": "〔重点〕",
    "medium": "〔关注〕",
    "warning": "〔关注〕",
    "warn": "〔关注〕",
    "low": "〔提示〕",
}

_ALERT_TEXT_KEYS = (
    "text_zh",
    "text",
    "message_zh",
    "message",
    "title_zh",
    "title",
    "summary_zh",
    "summary",
    "name_zh",
    "name",
    "label_zh",
    "label",
    "desc",
    "description",
)
_ALERT_CONTAINER_KEYS = ("items", "alerts", "list", "entries", "highlights", "top", "data")
_ALERT_LEVEL_KEYS = ("level", "severity", "priority", "kind", "type", "category")


# --------------------------------------------------------------------------- small helpers
def _h(value: Any) -> str:
    """HTML-escape any value (attributes included)."""
    return html.escape("" if value is None else str(value), quote=True)


def _attr(name: str, value: str) -> str:
    return f' {name}="{_h(value)}"' if value else ""


def _s(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _d(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _num(value: Any) -> float | None:
    """Best-effort finite float; ``bool``, NaN and junk become ``None``."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            return None
        try:
            number = float(text.rstrip("%"))
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def _fmt(value: Any, digits: int = 1) -> str:
    number = _num(value)
    if number is None:
        return DASH
    if digits <= 0:
        return f"{number:,.0f}"
    return f"{number:,.{digits}f}"


def _fmt_int(value: Any) -> str:
    return _fmt(value, 0)


def _fmt_thi(value: Any) -> str:
    number = _num(value)
    if number is None:
        return DASH
    text = f"{number:.2f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _fmt_prob(value: Any) -> str:
    number = _num(value)
    if number is None:
        return DASH
    return f"{number * 100:.1f}%"


def _fmt_share(value: Any, digits: int = 0) -> str:
    number = _num(value)
    if number is None:
        return DASH
    return f"{number * 100:.{digits}f}%"


def _fmt_signed_pp(value: Any, digits: int = 1) -> str:
    number = _num(value)
    if number is None:
        return DASH
    return f"{number * 100:+.{digits}f} 个百分点"


def _fmt_auto_pct(value: Any, digits: int = 1) -> str:
    """Trading numbers arrive as either fractions (0.12) or percent (12.0)."""
    number = _num(value)
    if number is None:
        return DASH
    if abs(number) <= 3.0:
        number *= 100.0
    return f"{number:+.{digits}f}%"


def _fmt_ratio(value: Any, digits: int = 2) -> str:
    number = _num(value)
    if number is None:
        return DASH
    return f"{number:,.{digits}f}"


def _ci_text(value: Any) -> str:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        low, high = _num(value[0]), _num(value[1])
        if low is not None and high is not None:
            return f"[{_fmt_thi(low)}, {_fmt_thi(high)}]"
    return DASH


def _trim(text: Any, limit: int = 48) -> str:
    value = _s(text)
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _describe(value: Any) -> str:
    """Compact human readable rendering of an unknown metrics value."""
    if isinstance(value, dict):
        parts = [f"{key}={_describe(item)}" for key, item in list(value.items())[:8]]
        return "；".join(parts) if parts else DASH
    if isinstance(value, (list, tuple)):
        return "、".join(_describe(item) for item in value) if value else DASH
    if isinstance(value, bool):
        return "是" if value else "否"
    if value is None or (isinstance(value, str) and not value.strip()):
        return DASH
    number = _num(value)
    if number is not None:
        if abs(number - round(number)) < 1e-9:
            return f"{number:,.0f}"
        return _fmt(number, 2)
    return _s(value)


_KIND_STAT_LABELS = (
    ("n_trades", "笔数"),
    ("trades", "笔数"),
    ("win_rate", "胜率"),
    ("hit_rate", "命中率"),
    ("mean_return", "平均收益"),
    ("avg_return", "平均收益"),
    ("mean_ar", "平均 AR"),
    ("total_pnl", "累计盈亏"),
    ("total_return", "累计收益"),
    ("mean_holding_days", "平均持有"),
)


def _format_kind_stats(value: Any) -> str:
    """Render one ``by_kind`` bucket (e.g. 7 trades, 57% win rate, +$4.4k)."""
    if not isinstance(value, dict):
        return _describe(value)
    parts: list[str] = []
    used: set[str] = set()
    for key, label in _KIND_STAT_LABELS:
        if key not in value or key in used:
            continue
        used.add(key)
        raw = value.get(key)
        number = _num(raw)
        if number is None:
            text = DASH
        elif key in ("n_trades", "trades"):
            text = _fmt_int(number)
        elif key in ("win_rate", "hit_rate"):
            text = _fmt_prob(number)
        elif key in ("mean_return", "avg_return", "mean_ar", "total_return"):
            text = _fmt_auto_pct(number)
        elif key == "total_pnl":
            text = f"${_fmt(number, 0)}"
        elif key == "mean_holding_days":
            text = f"{_fmt(number, 0)} 天"
        else:
            text = _describe(number)
        parts.append(f"{label} {text}")
    for key, raw in value.items():
        if key not in used:
            parts.append(f"{key} {_describe(raw)}")
    return "；".join(parts) if parts else DASH


def _ci_pct_text(value: Any) -> str:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        low, high = _num(value[0]), _num(value[1])
        if low is not None and high is not None:
            return f"[{low * 100:+.1f}%, {high * 100:+.1f}%]"
    return DASH


def _en_conclusions(ctx: Mapping[str, Any]) -> list[str]:
    """English takeaways generated from the same normalised context."""
    out: list[str] = []
    tracks = ctx["tracks"]
    if tracks:
        top = tracks[0]
        out.append(
            f"Top device track: {_en_track(top)} (THI {_fmt_thi(top.get('thi'))}, "
            f"P(up) {_fmt_prob(top.get('prob_up'))}), {_fmt_int(top.get('recent'))} events in window "
            f"vs {_fmt(top.get('baseline_per_q'))}/quarter baseline."
        )
        rising = sum(1 for track in tracks if _trend(track) == TREND_UP)
        out.append(f"{rising} of {len(tracks)} tracked device segments are in a heating-up regime (THI 95% CI above 1.0).")
    companies = ctx["companies"]
    if companies:
        top = companies[:3]
        out.append(
            "Strongest big-pharma momentum: "
            + ", ".join(f"{_en_company(item)} (THI {_fmt_thi(item.get('thi'))})" for item in top)
            + ". Regulatory cadence is a proxy, not revenue."
        )
    firstseen = ctx["firstseen"]
    if firstseen:
        first = firstseen[0]
        out.append(
            f"{len(firstseen)} first-seen records in the last 90 days; latest: "
            f"{_en_company(first)} into {_s(first.get('track_id')) or _s(first.get('track_zh')) or 'a new segment'}."
        )
    recalls = ctx["recalls"]
    if recalls:
        out.append(
            "Recall clusters: "
            + ", ".join(f"{_en_company(item)} ({_fmt_int(item.get('recent'))})" for item in recalls[:3])
            + "; watch product-line ageing and software-related causes."
        )
    if ctx["cn_gap"]:
        if ctx["cn_unavailable"]:
            out.append("China gap: unavailable (NMPA data not loaded); no China-vs-US inference is made.")
        else:
            top_gap = max(
                ctx["cn_gap"],
                key=lambda item: _num(item.get("gap_index")) if _num(item.get("gap_index")) is not None else -9,
            )
            out.append(f"China gap: {_s(top_gap.get('track_id')) or _s(top_gap.get('name_zh'))} shows the widest US lead.")
    trading = ctx["trading"]
    if trading and trading["curve"]:
        out.append(
            f"Paper portfolio: {_fmt_auto_pct(trading.get('total_return'))} total return, "
            f"{_fmt_auto_pct(trading.get('max_drawdown'))} max drawdown, "
            f"{_fmt_int(trading.get('trades'))} trades; long-only research engine, not tradable advice."
        )
    return out


def _cell_value(value: Any, limit: int = 24) -> str:
    """Compact scalar-or-structured cell used by the research-grade tables."""
    if isinstance(value, (dict, list, tuple)):
        return _trim(_describe(value), limit)
    text = _trim(value, limit)
    return text or DASH


def _md_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _md_table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    rows = list(rows)
    if not rows:
        return DASH
    lines = ["| " + " | ".join(_md_cell(header) for header in headers) + " |"]
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        lines.append("| " + " | ".join(_md_cell(cell) for cell in row) + " |")
    return "\n".join(lines)


def _range_text(block: Mapping[str, Any]) -> str:
    start, end = _s(block.get("start")), _s(block.get("end"))
    quarters = _num(block.get("quarters"))
    if not start and not end:
        return DASH
    text = f"{start or DASH} 至 {end or DASH}"
    if quarters is not None:
        text += f"（{quarters:.0f} 个季度）"
    return text


def _range_text_en(block: Mapping[str, Any]) -> str:
    start, end = _s(block.get("start")), _s(block.get("end"))
    quarters = _num(block.get("quarters"))
    if not start and not end:
        return "n/a"
    text = f"{start or 'n/a'} to {end or 'n/a'}"
    if quarters is not None:
        text += f" ({quarters:.0f} quarters)"
    return text


def _en_name(entry: Mapping[str, Any] | None) -> str:
    entry = entry or {}
    return (
        _s(entry.get("name_en"))
        or _s(entry.get("ticker"))
        or _s(entry.get("key"))
        or _s(entry.get("track_id"))
        or _s(entry.get("name_zh"))
        or _s(entry.get("company_zh"))
        or DASH
    )


def _en_company(entry: Mapping[str, Any] | None) -> str:
    entry = entry or {}
    if _s(entry.get("name_en")):
        return _s(entry.get("name_en"))
    key = _s(entry.get("key"))
    if key:
        return " ".join(part.capitalize() for part in key.replace("-", "_").split("_") if part)
    return _en_name(entry)


def _en_track(entry: Mapping[str, Any] | None) -> str:
    entry = entry or {}
    return _s(entry.get("name_en")) or _s(entry.get("track_id")) or _s(entry.get("name_zh")) or DASH


_TREND_EN = {TREND_UP: "heating", TREND_DOWN: "cooling", TREND_FLAT: "steady"}


def _trend_en(trend: str) -> str:
    return _TREND_EN.get(trend, "n/a")


def _fmt_delta_en(value: Any) -> str:
    number = _num(value)
    if number is None:
        return "n/a"
    return f"{number * 100:+.1f}pp"


def _signed_pct_text(value: Any, digits: int = 1) -> str:
    """Signed percentage with a direction glyph - never colour-only."""
    number = _num(value)
    if number is None:
        return DASH
    if abs(number) <= 3.0:
        number *= 100.0
    glyph = "▲" if number > 0 else "▼" if number < 0 else "→"
    return f"{number:+.{digits}f}% {glyph}"


def _decision_label(value: Any) -> tuple[str, str]:
    """Map a replay decision to ``(text, css)`` so colour is never the only cue."""
    raw = _s(value).lower()
    if raw in ("long", "buy", "1", "+1", "做多", "买入"):
        return "做多", "badge badge-long"
    if raw in ("short", "sell", "-1", "做空", "卖出", "回避"):
        return "做空 / 回避", "badge badge-short"
    if raw in ("hold", "skip", "flat", "0", "观望", "跳过"):
        return "观望", "badge badge-flat"
    return (_s(value) or DASH), "badge badge-flat"


def _source_text(value: Any, limit: int = 72) -> str:
    """Scheme-stripped source citation: keeps the dashboard free of remote URLs."""
    text = _s(value)
    if not text:
        return DASH
    lowered = text.lower()
    for prefix in ("https://", "http://", "//"):
        if lowered.startswith(prefix):
            text = text[len(prefix):]
            break
    return _trim(text, limit)


def _source_span(value: Any, label: str = "来源", limit: int = 72) -> str:
    text = _source_text(value, limit)
    if text == DASH:
        return ""
    return f'<span class="src">{_h(label)}：{_h(text)}</span>'


def _assumptions_link(url: Any) -> str:
    """Relative link to the assumptions register; external URLs degrade to text."""
    raw = _s(url)
    if not raw:
        return ""
    label = _source_text(raw, 80)
    if raw.lower().startswith(("http://", "https://")):
        return f'<span class="src">假设登记表：{_h(label)}</span>'
    return f'<a class="src-link" href="{_h(raw)}">假设登记表：{_h(label)}</a>'


def _family_name(entry: Mapping[str, Any] | None) -> str:
    entry = entry or {}
    return _s(entry.get("name_zh")) or _s(entry.get("name_en")) or _s(entry.get("family_id")) or DASH


def _family_key(entry: Mapping[str, Any] | None) -> str:
    entry = entry or {}
    return _s(entry.get("family_id")) or _s(entry.get("name_en")) or DASH


def _company_count(entry: Mapping[str, Any]) -> str:
    value = entry.get("companies")
    if isinstance(value, (list, tuple)):
        return _fmt_int(len(value))
    if isinstance(value, dict):
        return _fmt_int(len(value))
    return _fmt_int(value)


def _top_families_text(value: Any, limit: int = 3) -> str:
    parts: list[str] = []
    for pair in _l(value)[:limit]:
        if isinstance(pair, (list, tuple)) and len(pair) >= 2:
            parts.append(f"{_s(pair[0]) or DASH} {_fmt_share(pair[1])}")
    return "、".join(parts) if parts else DASH


QUALITY_LABELS = {
    "datetime": "精确时间戳（datetime）",
    "date": "仅日期（date）",
    "estimated": "估算时间（estimated）",
    "unknown": "未知（unknown，不进回测）",
}


def _quality_label(value: Any) -> str:
    key = _s(value).lower()
    return QUALITY_LABELS.get(key, _s(value) or DASH)


CASE_CATEGORY_LABELS = {
    "approval": "批准",
    "drug_approval": "药品批准",
    "device_clearance": "器械清关",
    "510k": "510(k) 清关",
    "pma": "PMA 批准",
    "recall": "召回",
    "recall_cluster": "召回聚集",
    "trial": "临床试验",
    "trial_start": "试验启动",
    "device_novel_code": "新产品码",
    "device_new_track": "新赛道",
    "earnings": "财报",
    "ma": "并购",
    "labeling": "标签/说明书",
}

CASE_OUTCOME_LABELS = {"hit": "命中", "miss": "未命中", "mixed": "部分命中"}


def _case_category(value: Any) -> str:
    raw = _s(value)
    return CASE_CATEGORY_LABELS.get(raw.lower(), raw or DASH)


def _case_outcome(value: Any) -> str:
    raw = _s(value).lower()
    return CASE_OUTCOME_LABELS.get(raw, _s(value) or DASH)


def _case_outcome_css(value: Any) -> str:
    raw = _s(value).lower()
    if raw == "hit":
        return "badge badge-hit"
    if raw == "miss":
        return "badge badge-miss"
    return "badge badge-mixed"


def _case_company(case: Mapping[str, Any]) -> str:
    return (
        _s(case.get("company_zh"))
        or _s(case.get("company_name"))
        or _s(case.get("ticker"))
        or _s(case.get("case_id"))
        or DASH
    )


def _case_date(case: Mapping[str, Any]) -> str:
    return _s(case.get("date")) or _s(case.get("event_date")) or _when_text(case.get("t")) or DASH


def _when_text(value: Any) -> str:
    """Shorten ISO datetimes for display: ``2026-05-12T09:30:00-04:00`` -> ``2026-05-12 09:30``."""
    text = _s(value)
    if "T" in text and len(text) >= 16:
        date_part, _, time_part = text.partition("T")
        return f"{date_part} {time_part[:5]}"
    return text


def _case_direction(case: Mapping[str, Any]) -> str:
    number = _num(case.get("direction"))
    if number is None:
        return DASH
    if number > 0:
        return "做多 ▲"
    if number < 0:
        return "做空 ▼"
    return "中性 →"


def _case_evidence(case: Mapping[str, Any]) -> list[str]:
    quotes = []
    for quote in _l(case.get("evidence_quotes")):
        text = _trim(quote, 500)
        if text:
            quotes.append(text)
    return quotes


def _case_price_rows(case: Mapping[str, Any]) -> list[tuple[str, float]]:
    rows: list[tuple[str, float]] = []
    for label, key in (("1 日", "price_1d"), ("5 日", "price_5d"), ("20 日", "price_20d"), ("60 日", "price_60d")):
        number = _num(case.get(key))
        if number is not None:
            rows.append((label, number))
    return rows


def _case_price_text(case: Mapping[str, Any]) -> str:
    rows = _case_price_rows(case)
    if not rows:
        return DASH
    return "、".join(f"{label} {_signed_pct_text(value)}" for label, value in rows)


def _case_source_text(case: Mapping[str, Any]) -> str:
    return _source_text(case.get("source_url"), 100)


def _case_link_html(case: Mapping[str, Any]) -> str:
    """Case cards may carry a clickable anchor (allowed by the case contract)."""
    url = _s(case.get("source_url"))
    if not url:
        return f'<span class="src">来源：{_h(DASH)}</span>'
    label = _source_text(url, 100)
    if url.lower().startswith(("http://", "https://")):
        return f'<a class="case-link" href="{_h(url)}" rel="noopener">来源：{_h(label)}</a>'
    return f'<span class="src">来源：{_h(label)}</span>'


def _case_stats_rows(stats: Mapping[str, Any]) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    known = {
        "total",
        "hit_rate_20d",
        "hit_rate_5d",
        "hit_rate_1d",
        "hit_rate_60d",
        "by_category",
    }
    total = _num(stats.get("total"))
    if total is not None or "total" in stats:
        rows.append(("样本总数", _fmt_int(total)))
    for key, label in (
        ("hit_rate_1d", "1 日命中率"),
        ("hit_rate_5d", "5 日命中率"),
        ("hit_rate_20d", "20 日命中率"),
        ("hit_rate_60d", "60 日命中率"),
    ):
        if key in stats:
            rows.append((label, _fmt_prob(stats.get(key))))
    for key, value in stats.items():
        if key in known or isinstance(value, (dict, list, tuple)):
            continue
        rows.append((str(key), _describe(value)))
    return rows


def _case_category_rows(stats: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for item in _l(stats.get("by_category")):
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            name = _case_category(item[0])
            count = _fmt_int(item[1])
            rate = _fmt_prob(item[2]) if len(item) >= 3 else DASH
            rows.append((name, count, rate))
        elif isinstance(item, dict):
            name = _case_category(
                item.get("category") or item.get("name") or item.get("kind")
            )
            count = _fmt_int(item.get("n") or item.get("count") or item.get("total"))
            rate = _fmt_prob(
                item.get("hit_rate") or item.get("win_rate") or item.get("rate")
            )
            rows.append((name, count, rate))
    return rows


def _sort_cases_desc(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def rank(item: Mapping[str, Any]) -> tuple[int, str]:
        value = _s(item.get("date")) or _s(item.get("event_date")) or _s(item.get("t"))
        return (0, "~" + value) if value else (1, "")

    return sorted(items, key=rank, reverse=True)


def _sort_desc(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    def rank(item: Mapping[str, Any]) -> tuple[int, float]:
        value = _num(item.get(key))
        return (1, 0.0) if value is None else (0, -value)

    return sorted(items, key=rank)


def _sort_abs_desc(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    def rank(item: Mapping[str, Any]) -> tuple[int, float]:
        value = _num(item.get(key))
        return (1, 0.0) if value is None else (0, -abs(value))

    return sorted(items, key=rank)


def _sort_date_desc(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def rank(item: Mapping[str, Any]) -> tuple[int, str]:
        value = _s(item.get("event_date")) or _s(item.get("signal_date")) or _s(item.get("date"))
        return (0, "~" + value) if value else (1, "")

    # ISO dates sort lexicographically; ascending on "~"+date then reverse.
    return sorted(items, key=rank, reverse=True)


def _track_name(entry: Mapping[str, Any] | None, fallback: str = DASH) -> str:
    entry = entry or {}
    return (
        _s(entry.get("name_zh"))
        or _s(entry.get("track_zh"))
        or _s(entry.get("name_en"))
        or _s(entry.get("track_id"))
        or fallback
    )


def _company_name(entry: Mapping[str, Any] | None) -> str:
    entry = entry or {}
    return (
        _s(entry.get("name_zh"))
        or _s(entry.get("company_zh"))
        or _s(entry.get("company_name"))
        or _s(entry.get("key"))
        or _s(entry.get("name_en"))
        or DASH
    )


def _trend(entry: Mapping[str, Any]) -> str:
    ci = entry.get("ci")
    low = high = None
    if isinstance(ci, (list, tuple)) and len(ci) >= 2:
        low, high = _num(ci[0]), _num(ci[1])
    if low is not None and low > 1.0:
        return TREND_UP
    if high is not None and high < 1.0:
        return TREND_DOWN
    thi = _num(entry.get("thi"))
    if thi is None:
        return DASH
    if thi > 1.05:
        return TREND_UP
    if thi < 0.95:
        return TREND_DOWN
    return TREND_FLAT


def _trend_css(trend: str) -> str:
    return {TREND_UP: "trend up", TREND_DOWN: "trend down", TREND_FLAT: "trend flat"}.get(trend, "trend flat")


# --------------------------------------------------------------------------- context
def _flatten_counts(counts: Any, prefix: str = "") -> list[tuple[str, float | None]]:
    rows: list[tuple[str, float | None]] = []
    if isinstance(counts, dict):
        for key, value in counts.items():
            label = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, dict):
                rows.extend(_flatten_counts(value, label))
            else:
                rows.append((label, _num(value)))
    elif isinstance(counts, (list, tuple)):
        for item in counts:
            if isinstance(item, dict):
                name = _s(item.get("kind")) or _s(item.get("name")) or _s(item.get("key"))
                rows.append((f"{prefix}.{name}" if prefix and name else name or DASH, _num(item.get("count"))))
    return rows


def _event_total(meta: Mapping[str, Any]) -> float | None:
    counts = _d(meta.get("counts"))
    for key in ("total", "events_total", "all"):
        value = _num(counts.get(key)) if counts else None
        if value is not None:
            return value
    total = None
    for _, value in _flatten_counts(counts):
        if value is not None:
            total = (total or 0.0) + value
    if total is not None:
        return total
    return _num(meta.get("events_total"))


def _source_status_zh(source: str, value: Any) -> str:
    status = _s(value).lower()
    if source == "nmpa":
        if status in ("unavailable", "") or value is None:
            return "不可用（NMPA 数据未加载）"
        if status == "demo":
            return "示例数据（demo，非真实注册证）"
        if status == "loaded":
            return "已加载"
        return _s(value) or DASH
    if source == "prices":
        if status in ("missing", "unavailable", "") or value is None:
            return "不可用（价格数据未加载）"
        if status == "partial":
            return "部分可用（部分股票缺失）"
        if status == "ok":
            return "可用"
        return _s(value) or DASH
    if status == "ok":
        return "可用"
    if status == "missing":
        return "不可用（数据未加载）"
    if status == "partial":
        return "部分可用"
    return _s(value) or DASH


def _cn_status_label(value: Any) -> str:
    status = _s(value).lower()
    if status == "loaded":
        return "已加载"
    if status == "demo":
        return "示例数据（demo）"
    return "不可用（NMPA 数据未加载）" if status in ("unavailable", "") else _s(value)


def _alert_entries(alerts: Any) -> list[tuple[str, str]]:
    """Flatten the loosely specified ``metrics.alerts`` into ``(text, level)``."""
    output: list[tuple[str, str]] = []

    def walk(node: Any, depth: int) -> None:
        if depth > 5 or node is None:
            return
        if isinstance(node, str):
            text = node.strip()
            if text:
                output.append((text, ""))
            return
        if isinstance(node, bool) or isinstance(node, (int, float)):
            return
        if isinstance(node, (list, tuple)):
            for item in node:
                walk(item, depth + 1)
            return
        if not isinstance(node, dict):
            return
        text = ""
        for key in _ALERT_TEXT_KEYS:
            candidate = node.get(key)
            if isinstance(candidate, str) and candidate.strip():
                text = candidate.strip()
                break
            if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
                text = _describe(candidate)
                break
        if text:
            level = ""
            for key in _ALERT_LEVEL_KEYS:
                candidate = node.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    level = candidate.strip()
                    break
            output.append((text, level))
            return
        for key in _ALERT_CONTAINER_KEYS:
            if key in node:
                walk(node[key], depth + 1)
        for key, value in node.items():
            if key in _ALERT_CONTAINER_KEYS:
                continue
            if isinstance(value, (list, dict)):
                walk(value, depth + 1)

    walk(alerts, 0)
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for text, level in output:
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append((text, level))
    return unique


_STRUCTURED_ALERT_KEYS = (
    "accelerating_tracks",
    "company_movers",
    "new_entries",
    "recall_clusters",
    "cn_gap_top",
)


def _structured_alert_lines(alerts: Any) -> list[str]:
    """Render ``metrics.alerts`` (fixed list-of-dict contract) into conclusions."""
    if not isinstance(alerts, dict):
        return []
    lines: list[str] = []
    for item in _l(alerts.get("accelerating_tracks"))[:3]:
        if isinstance(item, dict):
            lines.append(
                f"热度加速：**{_track_name(item)}** THI {_fmt_thi(item.get('thi'))}"
                f"（P(高于基线) {_fmt_prob(item.get('prob_up'))}），窗口内 {_fmt_int(item.get('recent'))} 件。"
            )
    for item in _l(alerts.get("company_movers"))[:2]:
        if isinstance(item, dict):
            lines.append(
                f"大厂异动：**{_company_name(item)}** THI {_fmt_thi(item.get('thi'))}，"
                f"窗口内 {_fmt_int(item.get('recent'))} 件，近 12 个月新增 {_fmt_int(item.get('novelty_12m'))} 个产品码。"
            )
    for item in _l(alerts.get("new_entries"))[:2]:
        if isinstance(item, dict):
            lines.append(
                f"首次进入：{_s(item.get('event_date')) or DASH} **{_company_name(item)}** 进入 "
                f"{_s(item.get('track_zh')) or _track_name(item)}"
                f"（{_trim(item.get('device_name') or item.get('title'), 34)}）。"
            )
    for item in _l(alerts.get("recall_clusters"))[:2]:
        if isinstance(item, dict):
            lines.append(
                f"召回聚集：**{_company_name(item)}** 窗口内 {_fmt_int(item.get('recent'))} 次召回，高于基线。"
            )
    for item in _l(alerts.get("cn_gap_top"))[:2]:
        if not isinstance(item, dict):
            continue
        status = _s(item.get("cn_data_status")).lower()
        if status in ("unavailable", "") or _num(item.get("cn_count")) is None:
            lines.append(
                f"中国空白度：不可用（NMPA 数据未加载）；{_track_name(item)} 美国近 24 个月 "
                f"{_fmt_int(item.get('us_recent'))} 件事件，本期不做中美对比推断。"
            )
        else:
            lines.append(
                f"中国空白度：{_track_name(item)} 美国事件占比领先 "
                f"{_fmt_signed_pp(item.get('gap_index'))}，为当前最明显的空白赛道。"
            )
    return lines


def _track_name_map(device: Mapping[str, Any], drug: Mapping[str, Any], cn_gap: list[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for entry in _l(device.get("tracks")) + _l(device.get("migration")) + cn_gap + _l(drug.get("areas")):
        if not isinstance(entry, dict):
            continue
        track_id = _s(entry.get("track_id"))
        name = _track_name(entry, fallback="")
        if track_id and name:
            mapping.setdefault(track_id, name)
    return mapping


def _resolve_trading(metrics: Mapping[str, Any], metrics_path: Path, out_dir: Path) -> dict[str, Any] | None:
    for candidate in (
        metrics.get("trading"),
        metrics.get("paper_trading"),
        metrics.get("paper"),
    ):
        if isinstance(candidate, dict) and candidate:
            return candidate
    for path in (metrics_path.parent / "trading.json", out_dir / "trading.json"):
        payload = read_json(path)
        if isinstance(payload, dict) and payload:
            return payload
    return None


def _equity_points(trading: Mapping[str, Any]) -> list[tuple[str, float]]:
    curve_keys = (
        "equity_curve",
        "equity_series",
        "equity",
        "nav_curve",
        "nav",
        "curve",
        "series",
        "points",
    )
    raw: Any = None
    for key in curve_keys:
        candidate = trading.get(key)
        if isinstance(candidate, (list, tuple)) and candidate:
            raw = candidate
            break
    if raw is None:
        nested = _d(trading.get("result"))
        for key in curve_keys:
            candidate = nested.get(key)
            if isinstance(candidate, (list, tuple)) and candidate:
                raw = candidate
                break
    points: list[tuple[str, float]] = []
    for item in _l(raw):
        date_text, value = "", None
        if isinstance(item, dict):
            for key in ("date", "day", "as_of", "signal_date", "ts", "x"):
                if item.get(key) is not None:
                    date_text = _s(item.get(key))[:10]
                    break
            for key in ("equity", "nav", "net_value", "value", "equity_value", "capital", "close", "y"):
                value = _num(item.get(key))
                if value is not None:
                    break
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            date_text = _s(item[0])[:10]
            value = _num(item[1])
        if value is not None:
            points.append((date_text, value))
    return points


def _trading_view(trading: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(trading, dict) or not trading:
        return None
    summary: dict[str, Any] = {}
    nested_keys = ("summary", "stats", "performance", "result", "metrics")
    for source in [trading] + [_d(trading.get(key)) for key in nested_keys]:
        for key, value in source.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                summary.setdefault(key, value)
    status = _s(trading.get("status")) or _s(summary.get("status"))
    curve = _equity_points(trading)
    by_kind = _d(trading.get("by_kind")) or _d(trading.get("attribution")) or _d(summary.get("by_kind"))
    total_return = _first_num(summary, ("total_return", "total_return_pct", "return_pct", "cum_return", "net_return"))
    capital = _first_num(summary, ("capital", "initial_capital", "start_capital")) or _num(
        _d(trading.get("meta")).get("capital")
    )
    final_equity = _first_num(summary, ("final_equity", "equity_end", "ending_equity", "final_value", "equity_final"))
    if final_equity is None and curve:
        final_equity = curve[-1][1]
    if total_return is None and final_equity is not None and capital:
        total_return = final_equity / capital - 1.0
    return {
        "status": status,
        "curve": curve,
        "by_kind": by_kind,
        "total_return": total_return,
        "max_drawdown": _first_num(summary, ("max_drawdown", "max_dd", "mdd")),
        "win_rate": _first_num(summary, ("win_rate", "hit_rate", "winrate", "winning_rate")),
        "trades": _first_num(summary, ("n_trades", "trades", "num_trades", "trade_count")),
        "avg_hold_return": _first_num(summary, ("avg_trade_return", "avg_hold_return", "average_return", "avg_return")),
        "capital": capital,
        "final_equity": final_equity,
        "event_study": _d(trading.get("event_study")),
        "raw": trading,
    }


def _event_study_rows(trading: Mapping[str, Any] | None) -> tuple[str, list[tuple[str, Mapping[str, Any]]]]:
    """Return ``(benchmark, [(horizon, stats), ...])`` from the event study block."""
    if not trading:
        return "", []
    study = _d(trading.get("event_study"))
    if not study:
        return "", []
    horizons = _d(study.get("horizons"))
    rows: list[tuple[str, Mapping[str, Any]]] = [
        (_s(key), value)
        for key, value in horizons.items()
        if isinstance(value, dict)
    ]
    rows.sort(key=lambda pair: _num(pair[0]) or 0.0)
    return _s(study.get("benchmark")), rows


def _first_num(mapping: Mapping[str, Any], keys: Sequence[str]) -> float | None:
    for key in keys:
        value = _num(mapping.get(key))
        if value is not None:
            return value
    return None


def build_context(metrics: Any, metrics_path: Path | str = DEFAULT_METRICS, out_dir: Path | str = OUT_DIR) -> dict[str, Any]:
    """Normalise the metrics JSON into the flat structures the renderers use."""
    metrics = metrics if isinstance(metrics, dict) else {}
    metrics_path = Path(metrics_path)
    out_dir = Path(out_dir)
    meta = _d(metrics.get("meta"))
    device = _d(metrics.get("device"))
    drug = _d(metrics.get("drug"))
    data_status = _d(meta.get("data_status"))

    tracks = [entry for entry in _l(device.get("tracks")) if isinstance(entry, dict)]
    tracks = _sort_desc(tracks, "thi")
    name_map = _track_name_map(device, drug, [entry for entry in _l(metrics.get("cn_gap")) if isinstance(entry, dict)])
    companies = _sort_desc([entry for entry in _l(device.get("companies")) if isinstance(entry, dict)], "thi")
    migration = _sort_abs_desc([entry for entry in _l(device.get("migration")) if isinstance(entry, dict)], "delta")
    firstseen = _sort_date_desc([entry for entry in _l(device.get("firstseen")) if isinstance(entry, dict)])
    recalls = _sort_desc([entry for entry in _l(device.get("recalls")) if isinstance(entry, dict)], "recent")

    approvals = _sort_desc([entry for entry in _l(drug.get("approvals")) if isinstance(entry, dict)], "thi")
    areas = _sort_desc([entry for entry in _l(drug.get("areas")) if isinstance(entry, dict)], "thi")
    trials = _sort_desc([entry for entry in _l(drug.get("trials")) if isinstance(entry, dict)], "thi")

    cn_gap = [entry for entry in _l(metrics.get("cn_gap")) if isinstance(entry, dict)]
    cn_gap = _sort_desc(cn_gap, "us_recent")
    # A gap is "available" only when it can actually be computed: rows exist AND
    # a Chinese source is loaded AND the rows carry a numeric CN count. An empty
    # cn_gap (e.g. no US device events yet) must not be reported as available.
    nmpa_status = _s(data_status.get("nmpa")).lower()
    cn_unavailable = (
        not cn_gap
        or nmpa_status in ("unavailable", "")
        or any(
            _s(entry.get("cn_data_status")).lower() in ("unavailable", "")
            or _num(entry.get("cn_count")) is None
            for entry in cn_gap
        )
    )
    signals = [entry for entry in _l(metrics.get("signals")) if isinstance(entry, dict)]
    trading_view = _trading_view(_resolve_trading(metrics, metrics_path, out_dir))

    alerts_raw = metrics.get("alerts")
    alert_lines = _structured_alert_lines(alerts_raw)
    leftover_alerts: Any = alerts_raw
    if isinstance(alerts_raw, dict):
        leftover_alerts = {
            key: value for key, value in alerts_raw.items() if key not in _STRUCTURED_ALERT_KEYS
        }
    for text, level in _alert_entries(leftover_alerts):
        alert_lines.append(_LEVEL_TAGS.get(level.lower(), "") + text)

    products = _d(metrics.get("products"))
    families = _sort_desc([entry for entry in _l(products.get("families")) if isinstance(entry, dict)], "thi")
    new_products = _sort_date_desc([entry for entry in _l(products.get("new_products")) if isinstance(entry, dict)])
    company_portfolio = _sort_abs_desc(
        [entry for entry in _l(products.get("company_portfolio")) if isinstance(entry, dict)], "js_shift"
    )
    family_map = {_family_key(entry): _family_name(entry) for entry in families if _family_key(entry) != DASH}

    replay = _d(metrics.get("replay"))
    replay_steps = [entry for entry in _l(replay.get("steps")) if isinstance(entry, dict)]
    replay_summary = replay.get("summary_by_cost")
    if not isinstance(replay_summary, dict):
        replay_summary = {}
    replay_view = {
        "status": _s(replay.get("status")) or ("ok" if replay_steps else ""),
        "window": _d(replay.get("window")),
        "steps": replay_steps,
        "summary_by_cost": replay_summary,
        "assumptions_url": _s(replay.get("assumptions_url")),
        "present": bool(replay),
    }

    timestamps = _d(metrics.get("timestamps"))
    by_quality = _d(timestamps.get("by_quality"))
    quality_rows: list[tuple[str, float | None]] = [
        (_s(key), _num(value)) for key, value in by_quality.items()
    ]
    quality_rows.sort(key=lambda pair: (pair[1] is None, -(pair[1] or 0)))
    quality_total = sum(value for _, value in quality_rows if value is not None)

    research = _d(metrics.get("research"))
    sample_split = _d(research.get("sample_split"))
    multiple_testing = _d(research.get("multiple_testing"))
    survivorship = _d(research.get("survivorship"))

    cases_raw = metrics.get("cases")
    if isinstance(cases_raw, list):
        cases_raw = {"selected": cases_raw}
    cases_raw = _d(cases_raw)
    selected_cases = _sort_cases_desc(
        [entry for entry in _l(cases_raw.get("selected")) if isinstance(entry, dict)]
    )
    negative_cases = _sort_cases_desc(
        [entry for entry in _l(cases_raw.get("negative_examples")) if isinstance(entry, dict)]
    )
    cases_view = {
        "present": bool(cases_raw),
        "selected": selected_cases,
        "negative": negative_cases,
        "stats": _d(cases_raw.get("stats")),
    }

    counts = _flatten_counts(meta.get("counts"))
    available = [status for status in data_status.values() if _s(status).lower() in ("ok", "loaded", "partial")]
    return {
        "meta": meta,
        "window": _d(meta.get("window")),
        "baseline": _d(meta.get("baseline")),
        "data_status": data_status,
        "counts": counts,
        "event_total": _event_total(meta),
        "tracks": tracks,
        "companies": companies,
        "migration": migration,
        "firstseen": firstseen,
        "recalls": recalls,
        "approvals": approvals,
        "areas": areas,
        "trials": trials,
        "cn_gap": cn_gap,
        "cn_unavailable": cn_unavailable,
        "signals": signals,
        "families": families,
        "new_products": new_products,
        "company_portfolio": company_portfolio,
        "family_map": family_map,
        "replay": replay_view,
        "timestamps": timestamps,
        "quality_rows": quality_rows,
        "quality_total": quality_total,
        "excluded_from_trading": _num(timestamps.get("excluded_from_trading")),
        "timestamps_policy": _s(timestamps.get("policy")),
        "research": research,
        "sample_split": sample_split,
        "multiple_testing": multiple_testing,
        "survivorship": survivorship,
        "cases": cases_view,
        "alerts": alerts_raw,
        "alert_lines": alert_lines,
        "trading": trading_view,
        "name_map": name_map,
        "has_core": bool(tracks or companies or approvals or areas or trials or signals or cn_gap),
        "source_available": len(available),
        "generated_at": _s(meta.get("generated_at")),
        "db": _s(meta.get("db")),
        "counts_text": "、".join(
            f"{KIND_LABELS.get(key, key)} {_fmt_int(value)}" for key, value in counts
        )
        or DASH,
    }


# --------------------------------------------------------------------------- conclusions
def _auto_conclusions(ctx: Mapping[str, Any]) -> list[str]:
    out: list[str] = []
    tracks = ctx["tracks"]
    if tracks:
        top = tracks[0]
        out.append(
            f"赛道热度：**{_track_name(top)}** 的 THI 为 {_fmt_thi(top.get('thi'))}"
            f"（95% 区间 {_ci_text(top.get('ci'))}，P(高于基线) = {_fmt_prob(top.get('prob_up'))}），"
            f"窗口内 {_fmt_int(top.get('recent'))} 件，约 {_fmt(top.get('recent_per_q'))} 件/季"
            f"（基线 {_fmt(top.get('baseline_per_q'))} 件/季），趋势判断为「{_trend(top)}」。"
        )
        up_count = sum(1 for track in tracks if _trend(track) == TREND_UP)
        down_count = sum(1 for track in tracks if _trend(track) == TREND_DOWN)
        out.append(
            f"赛道结构：{len(tracks)} 个赛道中 {up_count} 个处于升温区间、{down_count} 个处于降温区间；"
            f"大厂进入占比最高的三个赛道为 "
            + "、".join(
                f"{_track_name(track)}（{_fmt_share(track.get('major_share_recent'))}）"
                for track in sorted(tracks, key=lambda item: -(_num(item.get("major_share_recent")) or 0))[:3]
            )
            + "。"
        )
    companies = ctx["companies"]
    if companies:
        top = companies[:3]
        out.append(
            "大厂动量："
            + "、".join(f"**{_company_name(item)}**（THI {_fmt_thi(item.get('thi'))}）" for item in top)
            + f" 为本期动量最强的 {len(top)} 家；公司动量只反映监管事件节奏，不代表营收或股价。"
        )
    firstseen = ctx["firstseen"]
    if firstseen:
        tracks_seen = {_s(item.get("track_id")) for item in firstseen if _s(item.get("track_id"))}
        out.append(
            f"本期首次出现：近 90 天有 {len(firstseen)} 条首次出现记录，涉及 {len(tracks_seen) or len(firstseen)} 个赛道，"
            f"最新一条为 {_s(firstseen[0].get('event_date')) or DASH} 的 {_trim(firstseen[0].get('device_name') or firstseen[0].get('title'), 30)}。"
        )
    recalls = ctx["recalls"]
    if recalls:
        out.append(
            "召回聚集："
            + "、".join(f"{_company_name(item)}（近 {_fmt_int(item.get('recent'))} 次）" for item in recalls[:3])
            + f" 的召回次数高于基线，需要结合产品线老化与软件类风险解读。"
        )
    signals = ctx["signals"]
    if signals:
        longs = sum(1 for signal in signals if (_num(signal.get("direction")) or 0) > 0)
        out.append(f"信号：本期共 {len(signals)} 条信号，其中做多候选 {longs} 条、做空候选 {len(signals) - longs} 条；信号只用于模拟盘，不构成交易建议。")
    if ctx["cn_gap"]:
        if ctx["cn_unavailable"]:
            out.append("中国空白度：不可用（NMPA 数据未加载），本期不对中美赛道空白做任何数值推断。")
        else:
            top_gap = max(
                ctx["cn_gap"],
                key=lambda item: _num(item.get("gap_index")) if _num(item.get("gap_index")) is not None else -9,
            )
            out.append(
                f"中国空白度：{_track_name(top_gap)} 的美国事件占比领先 "
                f"{_fmt_signed_pp(top_gap.get('gap_index'))}，为已加载口径下最明显的空白信号。"
            )
    trading = ctx["trading"]
    if trading and trading["curve"]:
        out.append(
            f"模拟盘：净值曲线共 {len(trading['curve'])} 个交易日，区间收益 {_fmt_auto_pct(trading['total_return'])}，"
            f"最大回撤 {_fmt_auto_pct(trading['max_drawdown'])}；仅做多、未建模借券费与并购逼平，结果不具可交易性。"
        )
    return out


def _conclusion_lines(ctx: Mapping[str, Any]) -> list[str]:
    lines: list[str] = list(ctx["alert_lines"])[:5]
    if len(lines) < 3:
        for text in _auto_conclusions(ctx):
            if len(lines) >= 5:
                break
            if text not in lines:
                lines.append(text)
    if not lines:
        return [f"{DASH}：本期 metrics 为空或字段缺失，无法生成结论。"]
    return lines[:5]


# --------------------------------------------------------------------------- Chinese markdown
def _zh_conclusions(ctx: Mapping[str, Any]) -> str:
    lines = _conclusion_lines(ctx)
    return "\n".join(f"{index}. {line}" for index, line in enumerate(lines, start=1))


def _zh_data_status(ctx: Mapping[str, Any]) -> str:
    meta = ctx["meta"]
    data_status = ctx["data_status"]
    rows = []
    for source, label in SOURCE_LABELS.items():
        value = data_status.get(source)
        if value is None and source not in data_status:
            continue
        rows.append((label, _source_status_zh(source, value)))
    for source, value in data_status.items():
        if source not in SOURCE_LABELS:
            rows.append((source, _source_status_zh(source, value)))
    lines = [
        f"- **生成时间**：{ctx['generated_at'] or DASH}（UTC）",
        f"- **统计窗口**：{_range_text(ctx['window'])}",
        f"- **基线窗口**：{_range_text(ctx['baseline'])}",
        f"- **事件总数**：{_fmt_int(ctx['event_total'])} 件",
        f"- **数据源**：{ctx['source_available']} 路可用（共 {len(data_status)} 路登记）",
        "",
        _md_table(["数据源", "状态"], rows) if rows else DASH,
        "",
    ]
    if ctx["counts"]:
        lines.append(f"**事件构成**：{ctx['counts_text']}")
    else:
        lines.append(f"**事件构成**：{DASH}")
    if ctx["db"]:
        lines.append("")
        lines.append(f"**事实库**：`{ctx['db']}`")
    lines.append("")
    if ctx["cn_unavailable"]:
        lines.append(
            "> **中国侧数据警告**：NMPA 注册证数据不可用（NMPA 数据未加载）。"
            "因此中国空白度仅为美国侧参考，报告不以 0 代替缺失值，也不做中美对比推断。"
        )
    price_status = _s(data_status.get("prices")).lower()
    if price_status in ("", "missing", "unavailable"):
        lines.append("")
        lines.append("> **价格侧数据警告**：价格数据未加载，事件研究与模拟盘不可用。")
    return "\n".join(line for line in lines if line is not None).rstrip()


def _zh_tracks(ctx: Mapping[str, Any]) -> str:
    tracks = ctx["tracks"]
    if not tracks:
        return f"{DASH}（device.tracks 为空，或 analyze 尚未运行）。"
    top = tracks[0]
    intro = (
        f"按 THI（Gamma-Poisson 收缩后的近期速率 / 基线速率）排序，本期热度最高的是 "
        f"**{_track_name(top)}**：THI = {_fmt_thi(top.get('thi'))}，"
        f"95% 后验区间 {_ci_text(top.get('ci'))}，P(真实速率高于基线) = {_fmt_prob(top.get('prob_up'))}；"
        f"窗口内 {_fmt_int(top.get('recent'))} 件（约 {_fmt(top.get('recent_per_q'))} 件/季，基线 {_fmt(top.get('baseline_per_q'))} 件/季）。"
    )
    rows = []
    for index, track in enumerate(tracks[:MAX_TRACK_ROWS], start=1):
        rows.append(
            (
                index,
                _track_name(track),
                _fmt_thi(track.get("thi")),
                _ci_text(track.get("ci")),
                _fmt_prob(track.get("prob_up")),
                _fmt_int(track.get("recent")),
                _fmt(track.get("recent_per_q"), 2),
                _fmt(track.get("baseline_per_q"), 2),
                _fmt_share(track.get("major_share_recent")),
                _fmt_int(track.get("new_entrants_12m")),
                _trend(track),
            )
        )
    table = _md_table(
        ["#", "赛道", "THI", "95% 区间", "P(高于基线)", "窗口事件", "近期/季", "基线/季", "大厂占比", "新进入(12月)", "趋势"],
        rows,
    )
    more = ""
    if len(tracks) > MAX_TRACK_ROWS:
        more = f"\n\n> 仅展示 THI 前 {MAX_TRACK_ROWS} 个赛道，共 {len(tracks)} 个；完整数据见 `summary.csv`。"
    return f"{intro}\n\n{table}{more}\n\n> 解读：THI 与区间必须一起看。区间整体高于 1.0 才算真正的升温；区间跨过 1.0 时只能视为「方向不明确」。"


def _zh_companies(ctx: Mapping[str, Any]) -> str:
    companies = ctx["companies"]
    if not companies:
        return f"{DASH}（device.companies 为空，或公司名称匹配尚未产生结果）。"
    name_map = ctx["name_map"]
    top = companies[0]
    intro = (
        f"大厂动量榜按 THI 排序，共 {len(companies)} 家。当前动量最强的是 **{_company_name(top)}**"
        f"（THI = {_fmt_thi(top.get('thi'))}，P(高于基线) = {_fmt_prob(top.get('prob_up'))}，"
        f"窗口内 {_fmt_int(top.get('recent'))} 件）。"
    )
    rows = []
    for company in companies[:MAX_COMPANY_ROWS]:
        tracks = []
        for pair in _l(company.get("top_tracks"))[:2]:
            if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                track_id = _s(pair[0])
                label = name_map.get(track_id) or track_id
                tracks.append(f"{label} {_fmt_share(pair[1], 0)}")
        rows.append(
            (
                _company_name(company),
                _s(company.get("ticker")) or "—",
                _fmt_thi(company.get("thi")),
                _fmt_prob(company.get("prob_up")),
                _fmt_int(company.get("recent")),
                _fmt(company.get("recent_per_q"), 2),
                _fmt(company.get("baseline_per_q"), 2),
                _fmt_int(company.get("novelty_12m")),
                _fmt_int(company.get("recalls_recent")),
                "、".join(tracks) if tracks else DASH,
            )
        )
    table = _md_table(
        ["公司", "代码", "THI", "P(高于基线)", "窗口事件", "近期/季", "基线/季", "12月新产品码", "近12月召回", "主赛道"],
        rows,
    )
    more = f"\n\n> 仅展示前 {MAX_COMPANY_ROWS} 家，共 {len(companies)} 家。" if len(companies) > MAX_COMPANY_ROWS else ""
    return f"{intro}\n\n{table}{more}"


def _zh_products_families(ctx: Mapping[str, Any]) -> str:
    families = ctx["families"]
    if not families:
        return f"{DASH}（products.families 为空，或产品级分析尚未运行）。"
    top = families[0]
    intro = (
        f"产品族是在赛道之下按 openFDA 产品码族细分的一层。本期共 {len(families)} 个产品族，"
        f"热度最高的是 **{_family_name(top)}**（ID `{_family_key(top)}`）：THI = {_fmt_thi(top.get('thi'))}，"
        f"P(高于基线) = {_fmt_prob(top.get('prob_up'))}，窗口内 {_fmt_int(top.get('recent'))} 件，"
        f"覆盖 {_company_count(top)} 家公司，近 12 个月新进入 {_fmt_int(top.get('new_entrants_12m'))} 家。"
    )
    movers = sorted(families, key=lambda entry: -(_num(entry.get("new_entrants_12m")) or 0))[:3]
    movers = [entry for entry in movers if (_num(entry.get("new_entrants_12m")) or 0) > 0]
    lines = [intro]
    if movers:
        lines.append(
            "**新势力**：近 12 个月新进入公司最多的产品族为 "
            + "、".join(f"{_family_name(entry)}（{_fmt_int(entry.get('new_entrants_12m'))} 家）" for entry in movers)
            + "。"
        )
    lines.append("")
    rows = []
    for index, entry in enumerate(families[:MAX_FAMILY_ROWS], start=1):
        rows.append(
            (
                index,
                _family_name(entry),
                _fmt_thi(entry.get("thi")),
                _fmt_prob(entry.get("prob_up")),
                _fmt_int(entry.get("recent")),
                _company_count(entry),
                _fmt_int(entry.get("new_entrants_12m")),
                _cell_value(entry.get("first_seen"), 12),
                _family_key(entry),
            )
        )
    table = _md_table(
        ["#", "产品族", "THI", "P(高于基线)", "窗口事件", "公司数", "12月新进入", "首次出现", "产品族 ID"],
        rows,
    )
    lines.append(table)
    lines.append("")
    lines.append("> 每个产品族都可用 `产品族 ID` + 产品码回查到 `config/product_code_tracks.json` 与 openFDA 原始记录。")
    return "\n".join(lines)


def _zh_company_portfolio(ctx: Mapping[str, Any]) -> str:
    portfolio = ctx["company_portfolio"]
    if not portfolio:
        return f"{DASH}（products.company_portfolio 为空，或公司产品组合分析尚未运行）。"
    top = portfolio[0]
    lines = [
        "公司产品组合迁移衡量公司「产品族结构」的变化：`js_shift` 是窗口内组合分布相对基线的 "
        "Jensen-Shannon 距离，越接近 0 说明产品结构越稳定，越大说明公司正在换产品方向。",
        "",
    ]
    for item in portfolio[:5]:
        lines.append(
            f"- **{_company_name(item)}**：主产品族 {_top_families_text(item.get('top_families'))}；"
            f"组合迁移指数 JS = {_fmt(item.get('js_shift'), 3)}。"
        )
    lines.append("")
    rows = []
    for item in portfolio[:MAX_COMPANY_ROWS]:
        shift = _num(item.get("js_shift"))
        direction = "结构明显变化" if (shift or 0) >= 0.1 else "结构相对稳定"
        rows.append(
            (
                _company_name(item),
                _top_families_text(item.get("top_families")),
                _fmt(item.get("js_shift"), 3),
                direction,
            )
        )
    lines.append(_md_table(["公司", "主产品族（窗口占比）", "JS 组合迁移", "解读"], rows))
    lines.append("")
    lines.append(f"> 组合迁移最大的是 **{_company_name(top)}**（JS = {_fmt(top.get('js_shift'), 3)}）；"
                 "占比与指数均可由产品族归属逐条回查。")
    return "\n".join(lines)


def _zh_new_products(ctx: Mapping[str, Any]) -> str:
    items = ctx["new_products"]
    if not items:
        return f"{DASH}（products.new_products 为空，或本周没有抓取到新品记录）。"
    intro = (
        f"本周新品雷达共 {len(items)} 条（按日期倒序），每条都保留中文产品名、用途、"
        "510(k)/PMA 编号与来源，可直接回查原始记录。"
    )
    rows = []
    for item in items[:MAX_PRODUCT_ROWS]:
        product_name = _s(item.get("device_name_zh")) or _s(item.get("device_name")) or DASH
        rows.append(
            (
                _s(item.get("date")) or DASH,
                _s(item.get("company_zh")) or DASH,
                _s(item.get("family_zh")) or DASH,
                _s(item.get("code")) or "—",
                product_name,
                _trim(_s(item.get("definition_zh")) or _s(item.get("definition")), 56) or DASH,
                _s(item.get("k_number")) or DASH,
                _source_text(item.get("url"), 110),
            )
        )
    table = _md_table(
        ["日期", "公司", "产品族", "产品码", "中文产品名", "用途 / 定义", "510(k)/PMA 编号", "来源"],
        rows,
    )
    return f"{intro}\n\n{table}\n\n> 来源列为去掉协议头的原文路径，可在 docs/ 与 openFDA 原始记录中逐条核对；未取得来源时显示暂无数据。"


def _cost_row_values(stats: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    known = {
        "total_return",
        "max_drawdown",
        "win_rate",
        "n_trades",
        "trades",
        "sharpe",
        "avg_trade_return",
    }
    ignored = {
        "cost_bps",
        "final_equity",
        "total_pnl",
        "start",
        "end",
        "n_signals",
        "n_steps",
        "n_skipped",
        "equity_curve",
        "mean_gross_return",
        "mean_outcome_1d",
        "mean_outcome_5d",
        "mean_outcome_20d",
    }
    extras: list[str] = []
    if _num(stats.get("sharpe")) is not None:
        extras.append(f"夏普 {_fmt(stats.get('sharpe'), 2)}")
    if _num(stats.get("avg_holding_days")) is not None:
        extras.append(f"平均持有 {_fmt(stats.get('avg_holding_days'), 1)} 天")
    extras.extend(
        f"{key}={_describe(value)}"
        for key, value in stats.items()
        if key not in known and key not in ignored and not isinstance(value, (dict, list))
    )
    return (
        _fmt_auto_pct(stats.get("total_return")),
        _fmt_auto_pct(stats.get("max_drawdown")),
        _fmt_prob(stats.get("win_rate")),
        _fmt_int(_first_num(stats, ("n_trades", "trades"))),
        "；".join(extras[:3]) if extras else DASH,
    )


def _replay_cost_rows(summary_by_cost: Mapping[str, Any]) -> list[tuple[str, str, str, str, str, str]]:
    rows: list[tuple[str, str, str, str, str, str]] = []
    for label, stats in summary_by_cost.items():
        stats = _d(stats)
        if not stats:
            continue
        total, drawdown, win, trades, extra = _cost_row_values(stats)
        rows.append((f"{_s(label)} bps", total, drawdown, win, trades, extra))
    return rows


def _zh_replay(ctx: Mapping[str, Any]) -> str:
    replay = ctx["replay"]
    if not replay.get("present"):
        return f"{DASH}（replay 块缺失，回放研究尚未运行）。"
    status = _s(replay.get("status"))
    steps = replay.get("steps") or []
    if status == "insufficient_data" or not steps:
        return f"{DASH}（回放样本不足：status = {status or 'insufficient_data'}）。"
    window = _range_text(replay.get("window"))
    lines = [
        f"回放研究把每条信号按「决策时点 → 成交价 → 1/5/20 日结果」逐笔展开，共 {len(steps)} 步，"
        f"窗口 {window}。回放只使用决策时点可见的信息，避免前视偏差。",
        "",
    ]
    rows = []
    for step in steps[:MAX_REPLAY_STEPS]:
        decision, _ = _decision_label(step.get("decision"))
        skip_reason = _s(step.get("skip_reason_zh"))
        if skip_reason:
            decision = f"{decision}（{_trim(skip_reason, 16)}）"
        rows.append(
            (
                _when_text(step.get("t") or step.get("fill_date")) or DASH,
                _s(step.get("ticker")) or DASH,
                _trim(_s(step.get("event_zh")) or _s(step.get("event")) or DASH, 42),
                decision,
                _fmt(step.get("fill_price"), 2),
                _fmt_int(step.get("shares")),
                _signed_pct_text(step.get("outcome_1d")),
                _signed_pct_text(step.get("outcome_5d")),
                _signed_pct_text(step.get("outcome_20d")),
                _source_text(step.get("url"), 44),
            )
        )
    lines.append(
        _md_table(
            ["时间", "代码", "事件", "决策", "成交价", "股数", "1 日", "5 日", "20 日", "来源"],
            rows,
        )
    )
    cost_rows = _replay_cost_rows(_d(replay.get("summary_by_cost")))
    if cost_rows:
        lines.append("")
        lines.append("**多档交易成本下的回放结果**（成本以单边 bps 计）：")
        lines.append("")
        lines.append(_md_table(["成本档", "区间总收益", "最大回撤", "胜率", "笔数", "备注"], cost_rows))
    assumptions_url = replay.get("assumptions_url")
    if assumptions_url:
        lines.append("")
        lines.append(f"> 完整假设与数据口径见 [假设登记表]({assumptions_url})。")
    lines.append("")
    lines.append("> 回放为研究口径：只做多、未建模借券费/并购逼平/滑点冲击，结果不可直接交易。")
    return "\n".join(lines)


def _assumptions_md_link(ctx: Mapping[str, Any]) -> str:
    replay = ctx["replay"]
    url = _s(replay.get("assumptions_url"))
    if not url:
        return ""
    return f"[假设登记表]({url})"


def _zh_timestamps(ctx: Mapping[str, Any]) -> str:
    rows_data = ctx["quality_rows"]
    total = ctx["quality_total"]
    parts: list[str] = []
    if rows_data:
        lines = [
            "时间质量统计每条事件的时间戳精度：`datetime` 最可靠，`date` 只能按日对齐，"
            "`estimated` 是估算值，`unknown` 不进入交易研究。",
            "",
        ]
        rows = []
        for quality, count in rows_data[:12]:
            rows.append(
                (
                    _quality_label(quality),
                    _fmt_int(count),
                    _fmt_share((count or 0) / total) if total else DASH,
                )
            )
        lines.append(_md_table(["时间质量档", "事件数", "占比"], rows))
        excluded = ctx["excluded_from_trading"]
        lines.append("")
        lines.append(
            f"**不进入交易研究的事件**：{_fmt_int(excluded)} 条"
            + ("（时间质量未知，回测直接剔除）。" if excluded is not None else "（未统计）。")
        )
        if ctx["timestamps_policy"]:
            lines.append("")
            lines.append(f"**口径说明**：{ctx['timestamps_policy']}")
        lines.append("")
        lines.append("> 统计口径：逐条读取事件表的 `timestamp_quality` 字段并计数，可按事件 ID 回查；`unknown` 不进入交易研究。")
        parts.append("\n".join(lines))
    else:
        parts.append(f"{DASH}（timestamps.by_quality 为空，或时间质量统计尚未运行）。")

    sample_split = ctx["sample_split"]
    if sample_split:
        rows = _sample_split_rows(sample_split)
        parts.append("**样本划分**（时间切分，避免用未来数据训练）：\n\n" + _md_table(["划分", "说明"], rows))
    else:
        parts.append(f"**样本划分**：{DASH}（research.sample_split 为空）。")
    assumptions = _assumptions_md_link(ctx)
    if assumptions:
        parts.append(f"> 回放与时间质量的完整假设见 {assumptions}。")
    return "\n\n".join(parts)


_ADJUSTED_LABELS = {
    "track_id": "赛道 / 产品族",
    "family_id": "产品族",
    "key": "项目",
    "raw_p": "原始 p 值",
    "p_value": "原始 p 值",
    "p": "原始 p 值",
    "adjusted_p": "校正后 p 值",
    "q_value": "校正后 p 值",
    "significant": "是否显著",
}


def _fmt_pvalue(value: Any) -> str:
    number = _num(value)
    if number is None:
        return DASH
    if number < 0.001:
        return f"{number:.5f}"
    if number < 0.1:
        return f"{number:.4f}"
    return f"{number:.3f}"


def _adjusted_table(multiple_testing: Mapping[str, Any]) -> tuple[list[str] | None, list[list[str]]]:
    adjusted = [item for item in _l(multiple_testing.get("adjusted")) if isinstance(item, dict)]
    if not adjusted:
        return None, []
    keys: list[str] = []
    for item in adjusted:
        for key in item:
            if key not in keys and len(keys) < 6:
                keys.append(str(key))
    headers = [_ADJUSTED_LABELS.get(key, key) for key in keys]
    rows: list[list[str]] = []
    for item in adjusted[:12]:
        row: list[str] = []
        for key in keys:
            if key in ("raw_p", "p_value", "p", "adjusted_p", "q_value"):
                row.append(_fmt_pvalue(item.get(key)))
            else:
                row.append(_describe(item.get(key)))
        rows.append(row)
    return headers, rows


def _zh_research_quality(ctx: Mapping[str, Any]) -> str:
    multiple_testing = ctx["multiple_testing"]
    survivorship = ctx["survivorship"]
    lines: list[str] = []
    if multiple_testing:
        method = _s(multiple_testing.get("method")) or "未标注"
        adjusted = _l(multiple_testing.get("adjusted"))
        lines.append(
            f"多重检验校正方法：**{method}**；参与校正的检验 {_fmt_int(len(adjusted)) if adjusted else DASH} 个。"
            "校正后仍有显著结果的赛道/产品族才值得单独解读。"
        )
        keys, rows = _adjusted_table(multiple_testing)
        if keys and rows:
            lines.append("")
            lines.append(_md_table([key for key in keys], rows))
        elif adjusted:
            preview = "、".join(_describe(value) for value in adjusted[:10])
            lines.append("")
            lines.append(f"**调整后 p 值（前 10）**：{preview}")
        n_significant = _first_num(multiple_testing, ("n_significant", "significant", "n_rejected"))
        if n_significant is not None:
            lines.append("")
            lines.append(f"**校正后显著项**：{_fmt_int(n_significant)} 个。")
    else:
        lines.append(f"{DASH}（research.multiple_testing 为空）。")

    lines.append("")
    if survivorship:
        flagged = _num(survivorship.get("flagged"))
        extra = [
            f"{key}={_describe(value)}"
            for key, value in survivorship.items()
            if key != "flagged" and not isinstance(value, (dict, list))
        ][:3]
        lines.append(
            f"**生存偏差标记**：{_fmt_int(flagged)} 个标的/事件被标记为可能受生存偏差影响"
            + (f"（{'；'.join(extra)}）。" if extra else "。")
        )
        if flagged and flagged > 0:
            lines.append("")
            lines.append(
                "> 存在生存偏差风险：只用当前仍在市/仍在目录中的样本会高估历史收益，"
                "相关结论应视为上界而非点估计。"
            )
    else:
        lines.append(f"**生存偏差标记**：{DASH}（research.survivorship 为空）。")
    lines.append("")
    lines.append("> 校正对象为各赛道 / 产品族的 THI 显著性检验，逐项 `adjusted` 与标记数均来自 `metrics.research`，可回查。")
    return "\n".join(lines)


def _md_case_block(case: Mapping[str, Any]) -> str:
    case_id = _s(case.get("case_id")) or "未编号"
    ticker = _s(case.get("ticker")) or "—"
    lines = [
        f"#### 案例 {case_id} · {_case_date(case)} · {_case_company(case)}（{ticker}）",
        "",
        f"- **事件**：{_s(case.get('event_zh')) or _s(case.get('title')) or DASH}",
        f"- **分类 / 方向 / 事后结果**：{_case_category(case.get('category'))} ｜ "
        f"{_case_direction(case)} ｜ **{_case_outcome(case.get('outcome'))}**",
        "- **逐字证据**：",
    ]
    quotes = _case_evidence(case)
    if quotes:
        lines.extend(f"  > {quote}" for quote in quotes)
    else:
        lines.append(f"  > {DASH}")
    lines.append(f"- **价格反应（1/5/20/60 日）**：{_case_price_text(case)}")
    verdict = _s(case.get("verdict_zh"))
    if verdict:
        lines.append(f"- **系统判定与事后**：{verdict}")
    source_url = _s(case.get("source_url"))
    if source_url.lower().startswith(("http://", "https://")):
        source_md = f"[{_case_source_text(case)}]({source_url})"
    else:
        source_md = _case_source_text(case)
    lines.append(f"- **原文链接**：{source_md} ｜ **案例 ID**：`{case_id}`")
    return "\n".join(lines)


def _zh_cases(ctx: Mapping[str, Any]) -> str:
    cases = ctx["cases"]
    if not cases.get("present"):
        return f"{DASH}（cases 块缺失，案例库尚未生成）。"
    selected = cases["selected"]
    negative = cases["negative"]
    stats = cases["stats"]
    if not selected and not negative and not stats:
        return f"{DASH}（cases 块为空，或本期没有可展示的案例）。"
    parts: list[str] = [
        f"本期案例库精选 **{len(selected)}** 个案例、**{len(negative)}** 个反例。"
        "所有案例都是**样本内**回看：用系统当时的判定对照事后价格反应，只用于说明证据链，"
        "**不是策略业绩，也不是样本外收益**。",
    ]
    stats_rows = _case_stats_rows(stats)
    if stats_rows:
        parts.append("**分类统计（样本内）**：\n\n" + _md_table(["指标", "数值"], stats_rows))
        category_rows = _case_category_rows(stats)
        if category_rows:
            parts.append(_md_table(["案例分类", "样本数", "20 日命中率"], category_rows))
    else:
        parts.append(f"**分类统计**：{DASH}（cases.stats 为空）。")

    if selected:
        parts.append(f"### 精选案例（{len(selected)} 个）")
        parts.extend(_md_case_block(case) for case in selected[:MAX_CASE_CARDS])
    else:
        parts.append(f"### 精选案例\n\n{DASH}（cases.selected 为空）。")

    if negative:
        parts.append(f"### 反例（{len(negative)} 个，未命中 / 反向）")
        parts.extend(_md_case_block(case) for case in negative[:MAX_NEGATIVE_CASES])
    else:
        parts.append(f"### 反例\n\n{DASH}（cases.negative_examples 为空）。")

    parts.append(
        "> 口径说明：案例来自历史事件与行情的样本内回看，价格反应为事后统计；"
        "命中率与分类统计仅描述这批案例，不代表策略业绩，也不构成投资建议。"
    )
    return "\n\n".join(parts)


def _zh_migration(ctx: Mapping[str, Any]) -> str:
    migration = ctx["migration"]
    if not migration:
        return f"{DASH}（device.migration 为空，或本期没有达到阈值的结构迁移）。"
    lines = ["结构迁移衡量的是「谁在换方向」：公司窗口内赛道占比相对基线占比的变化（Δ，单位为个百分点），"
             "并用 Jensen-Shannon 距离（JS）过滤掉只是总量波动、组合结构没变的噪声。", ""]
    for item in migration[:10]:
        delta = _num(item.get("delta"))
        direction = "明显向该赛道倾斜" if (delta or 0) > 0 else "明显撤出该赛道"
        clauses = [
            f"窗口占比 {_fmt_share(item.get('share_recent'))}",
            f"基线 {_fmt_share(item.get('share_base'))}",
            f"Δ {_fmt_signed_pp(item.get('delta'))}",
        ]
        if _num(item.get("js")) is not None:
            clauses.append(f"JS = {_fmt(item.get('js'), 3)}")
        lines.append(
            f"- **{_company_name(item)}** → {_s(item.get('track_zh')) or _track_name(item)}："
            + "，".join(clauses)
            + f"，{direction}。"
        )
    rows = []
    for item in migration[:MAX_COMPANY_ROWS]:
        rows.append(
            (
                _company_name(item),
                _s(item.get("track_zh")) or _track_name(item),
                _fmt_share(item.get("share_recent")),
                _fmt_share(item.get("share_base")),
                _fmt_signed_pp(item.get("delta")),
                _fmt(item.get("js"), 3),
            )
        )
    table = _md_table(["公司", "赛道", "窗口占比", "基线占比", "Δ", "JS 距离"], rows)
    more = f"\n\n> 仅展示 |Δ| 前 {MAX_COMPANY_ROWS} 条，共 {len(migration)} 条。" if len(migration) > MAX_COMPANY_ROWS else ""
    return "\n".join(lines) + "\n\n" + table + more


def _zh_firstseen(ctx: Mapping[str, Any]) -> str:
    firstseen = ctx["firstseen"]
    if not firstseen:
        return f"{DASH}（device.firstseen 为空，或近 90 天没有首次出现记录）。"
    intro = f"近 90 天共 {len(firstseen)} 条首次出现记录（按日期倒序，展示前 {min(len(firstseen), MAX_FIRSTSEEN_ROWS)} 条）。"
    rows = []
    for item in firstseen[:MAX_FIRSTSEEN_ROWS]:
        rows.append(
            (
                _s(item.get("event_date")) or DASH,
                _company_name(item),
                _s(item.get("track_zh")) or _track_name(item),
                _s(item.get("product_code")) or "—",
                _trim(item.get("device_name") or item.get("title"), 32),
                _trim(item.get("title"), 40),
            )
        )
    table = _md_table(["日期", "公司", "中文赛道", "产品码", "器械/产品名", "标题"], rows)
    return f"{intro}\n\n{table}"


def _zh_recalls(ctx: Mapping[str, Any]) -> str:
    recalls = ctx["recalls"]
    track_hits = [
        track
        for track in ctx["tracks"]
        if (_num(track.get("recalls_recent")) or 0) > 0
    ]
    parts: list[str] = []
    if recalls:
        intro = f"本期召回聚集榜共 {len(recalls)} 家公司（按窗口内召回次数排序）。"
        rows = []
        for item in recalls[:MAX_COMPANY_ROWS]:
            rows.append(
                (
                    _company_name(item),
                    _fmt_int(item.get("recent")),
                    _fmt(item.get("baseline_per_q"), 2),
                    _s(item.get("reason_top")) or DASH,
                )
            )
        table = _md_table(["公司", "窗口内召回", "基线/季", "主要原因"], rows)
        parts.append(f"{intro}\n\n{table}")
    else:
        parts.append(f"{DASH}（device.recalls 为空，或本期没有可用召回数据）。")
    if track_hits:
        parts.append(
            "**赛道维度召回**："
            + "、".join(
                f"{_track_name(track)}（{_fmt_int(track.get('recalls_recent'))} 次）"
                for track in track_hits[:8]
            )
            + "。召回密集的赛道通常对应更成熟、装机量更大的产品线，不等同于安全性恶化。"
        )
    return "\n\n".join(parts)


def _zh_drug(ctx: Mapping[str, Any]) -> str:
    approvals = ctx["approvals"]
    areas = ctx["areas"]
    trials = ctx["trials"]
    if not (approvals or areas or trials):
        return f"{DASH}（drug.approvals / drug.areas / drug.trials 均为空，或药品数据未加载）。"
    name_map = ctx["name_map"]
    parts: list[str] = []
    if approvals:
        rows = []
        for item in approvals[:MAX_COMPANY_ROWS]:
            rows.append(
                (
                    _company_name(item),
                    _s(item.get("ticker")) or "—",
                    _fmt_int(item.get("recent")),
                    _fmt(item.get("recent_per_q"), 2),
                    _fmt(item.get("baseline_per_q"), 2),
                    _fmt_thi(item.get("thi")),
                    _fmt_prob(item.get("prob_up")),
                    _fmt_int(item.get("nme_recent")),
                )
            )
        parts.append(
            f"**NDA/BLA 批准**（{len(approvals)} 家公司，按 THI 排序）：\n\n"
            + _md_table(["公司", "代码", "批准数", "近期/季", "基线/季", "THI", "P(高于基线)", "新分子实体"], rows)
        )
    else:
        parts.append(f"**NDA/BLA 批准**：{DASH}")
    if areas:
        rows = []
        for item in areas[:MAX_COMPANY_ROWS]:
            rows.append(
                (
                    name_map.get(_s(item.get("track_id"))) or _track_name(item),
                    _fmt_int(item.get("recent")),
                    _fmt_thi(item.get("thi")),
                    _fmt_prob(item.get("prob_up")),
                    _trend(item),
                )
            )
        parts.append(
            "**治疗领域**：\n\n" + _md_table(["领域", "窗口事件", "THI", "P(高于基线)", "趋势"], rows)
        )
    if trials:
        rows = []
        for item in trials[:MAX_COMPANY_ROWS]:
            phases = []
            for phase, share in list(_d(item.get("phase_mix")).items())[:4]:
                phases.append(f"{PHASE_LABELS.get(phase, phase)} {_fmt_share(share, 0)}")
            rows.append(
                (
                    _company_name(item),
                    _fmt_int(item.get("starts_recent")),
                    _fmt(item.get("recent_per_q"), 2),
                    _fmt(item.get("baseline_per_q"), 2),
                    _fmt_thi(item.get("thi")),
                    "、".join(phases) if phases else DASH,
                )
            )
        parts.append(
            "**临床试验启动**：\n\n"
            + _md_table(["公司", "启动数", "近期/季", "基线/季", "THI", "阶段结构"], rows)
        )
    return "\n\n".join(parts)


def _zh_cn_gap(ctx: Mapping[str, Any]) -> str:
    cn_gap = ctx["cn_gap"]
    if not cn_gap:
        return f"{DASH}（cn_gap 为空，或分析阶段未计算中国空白度）。"
    parts: list[str] = []
    if ctx["cn_unavailable"]:
        parts.append(
            "> **中国空白度：不可用（NMPA 数据未加载）。** "
            "NMPA 注册证数据缺失时 `cn_count` / `cn_share` 为 null，本报告**不以 0 代替**，"
            "因此不计算、也不解读 `gap_index`；下表仅保留美国侧事件作为方向参考。"
        )
    else:
        parts.append(
            "中国空白度 = 美国赛道事件占比 − 已加载的中国注册证占比（`gap_index`）。"
            "数值越大表示美国侧越领先、国内对应供给越少；该指标只在 NMPA 数据已加载时有效。"
        )
    rows = []
    for item in cn_gap[:MAX_TRACK_ROWS]:
        status = _s(item.get("cn_data_status")).lower()
        cn_count = _num(item.get("cn_count"))
        unavailable = status in ("unavailable", "") or cn_count is None
        rows.append(
            (
                _track_name(item),
                _fmt_int(item.get("us_recent")),
                _fmt_share(item.get("us_share"), 1),
                "不可用" if unavailable else _fmt_int(cn_count),
                "不可用" if unavailable else _fmt_share(item.get("cn_share"), 1),
                "不可用" if unavailable else _fmt_signed_pp(item.get("gap_index"), 1),
                _cn_status_label(status),
            )
        )
    parts.append(
        _md_table(
            ["赛道", "美国近24月事件", "美国占比", "中国注册证", "中国占比", "空白指数", "数据状态"],
            rows,
        )
    )
    if any(
        _s(item.get("cn_data_status")).lower() == "demo" for item in cn_gap
    ):
        parts.append("> 注：标记为 demo 的行是示例数据，仅用于验证管线，不代表真实 NMPA 注册证。")
    more = f"\n\n> 仅展示美国事件数前 {MAX_TRACK_ROWS} 个赛道，共 {len(cn_gap)} 个。" if len(cn_gap) > MAX_TRACK_ROWS else ""
    return "\n\n".join(parts) + more


def _zh_signals(ctx: Mapping[str, Any]) -> str:
    signals = ctx["signals"]
    parts: list[str] = []
    if signals:
        kinds: dict[str, int] = {}
        for signal in signals:
            kind = _s(signal.get("kind")) or "unknown"
            kinds[kind] = kinds.get(kind, 0) + 1
        longs = sum(1 for signal in signals if (_num(signal.get("direction")) or 0) > 0)
        parts.append(
            f"本期共 {len(signals)} 条信号（做多候选 {longs} 条 / 做空候选 {len(signals) - longs} 条）；"
            f"类型分布：" + "、".join(f"{KIND_LABELS.get(kind, kind)} {count}" for kind, count in sorted(kinds.items(), key=lambda pair: -pair[1])) + "。"
        )
        rows = []
        for signal in signals[:MAX_SIGNAL_ROWS]:
            direction = _num(signal.get("direction")) or 0
            rows.append(
                (
                    _s(signal.get("signal_date")) or DASH,
                    _company_name(signal),
                    _s(signal.get("ticker")) or "—",
                    KIND_LABELS.get(_s(signal.get("kind")), _s(signal.get("kind")) or DASH),
                    "做多" if direction > 0 else "做空" if direction < 0 else "中性",
                    _fmt(_num(signal.get("score")), 2) if _num(signal.get("score")) is not None else DASH,
                    ctx["name_map"].get(_s(signal.get("track_id"))) or _s(signal.get("track_id")) or DASH,
                    _trim(signal.get("reason_zh"), 42),
                )
            )
        parts.append(
            f"信号明细（前 {min(len(signals), MAX_SIGNAL_ROWS)} 条，按输入顺序；`signal_date` 为最早可公开获知日期，用于避免前视偏差）：\n\n"
            + _md_table(["日期", "公司", "代码", "类型", "方向", "置信度", "赛道", "理由"], rows)
        )
    else:
        parts.append(f"信号：{DASH}（本期 metrics.signals 为空或不含信号）。")

    trading = ctx["trading"]
    if trading:
        status = _s(trading.get("status"))
        curve = trading.get("curve") or []
        if status == "insufficient_data" or (not curve and trading.get("total_return") is None):
            parts.append(f"模拟盘：样本不足，未运行模拟盘（status = {status or 'insufficient_data'}）。")
        else:
            summary_rows = [
                ("区间总收益", _fmt_auto_pct(trading.get("total_return"))),
                ("最大回撤", _fmt_auto_pct(trading.get("max_drawdown"))),
                ("胜率", _fmt_prob(trading.get("win_rate"))),
                ("交易笔数", _fmt_int(trading.get("trades"))),
                ("平均持有收益", _fmt_auto_pct(trading.get("avg_hold_return"))),
                ("期末净值", _fmt(trading.get("final_equity"), 0)),
            ]
            parts.append("**模拟盘摘要**：\n\n" + _md_table(["指标", "数值"], summary_rows))
            if curve:
                parts.append(
                    f"净值曲线共 {len(curve)} 个交易日，区间 {curve[0][0] or DASH} 至 {curve[-1][0] or DASH}；"
                    "曲线与回撤明细见同目录 `index.html` 看板。"
                )
            if trading.get("by_kind"):
                rows = [
                    (KIND_LABELS.get(kind, kind), _format_kind_stats(value))
                    for kind, value in trading["by_kind"].items()
                ]
                parts.append("**按信号类型归因**：\n\n" + _md_table(["类型", "指标"], rows))
            benchmark, horizons = _event_study_rows(trading)
            if horizons:
                parts.append(
                    f"**事件研究（超额收益 AR，基准 {benchmark or 'SPY'}）**："
                    + "、".join(
                        f"{horizon} 日 {_fmt_auto_pct(stats.get('mean_ar'))}"
                        f"（n={_fmt_int(stats.get('n'))}，命中率 {_fmt_prob(stats.get('hit_rate'))}）"
                        for horizon, stats in horizons
                    )
                    + "；AR 已按信号方向调整，仅统计有价格覆盖的标的。"
                )
            parts.append(
                "> 模拟盘规则：只做多、信号次一交易日开盘入场、单票上限 5%、单赛道上限 25%、"
                "持有 60 个交易日或 -20% 止损、成本 20bps + 每笔 1 美元；"
                "未建模做空借券费与并购逼平，结果为研究口径，不构成真实交易建议。"
            )
    else:
        parts.append(f"模拟盘：{DASH}（未运行 trade 阶段，或 trading.json 缺失）。")
    return "\n\n".join(parts)


def _zh_methods(ctx: Mapping[str, Any]) -> str:
    window = _range_text(ctx["window"])
    baseline = _range_text(ctx["baseline"])
    return "\n".join(
        [
            f"1. **数据延迟 2-12 天。** openFDA 与 ClinicalTrials.gov 都有上报与索引延迟，"
            f"本期窗口为 {window}，基线为 {baseline}；所有速率按 `event_date`（最早可公开获知日期）计算。",
            "2. **名称口径漏检。** 公司归属依赖别名模糊匹配，宁可漏检也不误配；未匹配事件保留在事实库中，"
            "但不计入公司动量，`top_unmatched` 需人工复核。",
            "3. **批准 ≠ 研发投入。** 510(k)/PMA/NDA 只是监管结果，不等于销售额、装机量或研发投入；"
            "本报告把它当作公开、可复核的活动代理变量。",
            "4. **样本量与 Poisson 收缩。** 小样本直接算速率会被单次事件放大，因此 THI 使用 Gamma-Poisson "
            "经验贝叶斯收缩（先验强度取同侪水平），并给出 95% 后验区间与 P(真实速率高于基线)；"
            "请把 THI 与区间一起读，区间跨 1.0 时方向不明确。",
            "5. **赛道映射是人工词典。** 产品码 / 适应症关键词到中文赛道的映射由 `config/tracks_*.json` 维护，"
            "存在跨赛道误分的可能，新增产品码需要人工补充。",
            "6. **中国侧不做推断。** NMPA 不可用时，中国空白度标记为不可用（NMPA 数据未加载），"
            "缺失值保持 null，不以 0 冒充真实空白。",
            "7. **模拟盘是研究工具。** 只做多、未建模借券费、并购逼平与大额冲击成本，"
            "样本量小，不能外推为可交易策略。",
        ]
    )


def _zh_disclaimer() -> str:
    return "\n".join(
        [
            "本报告由 MedRadar 自动生成，仅用于开源研究、技术演示与数据方法讨论，"
            "**不构成任何投资建议、荐股或交易邀约**。",
            "",
            "数据来自美国 FDA openFDA、ClinicalTrials.gov 等公开数据源，可能存在延迟、遗漏、去重错误与口径差异；"
            "中国 NMPA 注册证数据可用性以报告内标注为准。",
            "",
            "读者应自行核验原始数据，并在做出任何医疗、商业或投资决策前咨询持牌专业人士。"
            "作者与贡献者不对因使用本报告或本看板造成的任何直接或间接损失承担责任。",
        ]
    )


def _zh_sections(ctx: Mapping[str, Any]) -> list[tuple[str, str]]:
    return [
        (CHAPTERS_ZH[0], _zh_conclusions(ctx)),
        (CHAPTERS_ZH[1], _zh_data_status(ctx)),
        (CHAPTERS_ZH[2], _zh_tracks(ctx)),
        (CHAPTERS_ZH[3], _zh_companies(ctx)),
        (CHAPTERS_ZH[4], _zh_products_families(ctx)),
        (CHAPTERS_ZH[5], _zh_migration(ctx)),
        (CHAPTERS_ZH[6], _zh_company_portfolio(ctx)),
        (CHAPTERS_ZH[7], _zh_new_products(ctx)),
        (CHAPTERS_ZH[8], _zh_firstseen(ctx)),
        (CHAPTERS_ZH[9], _zh_recalls(ctx)),
        (CHAPTERS_ZH[10], _zh_drug(ctx)),
        (CHAPTERS_ZH[11], _zh_cn_gap(ctx)),
        (CHAPTERS_ZH[12], _zh_signals(ctx)),
        (CHAPTERS_ZH[13], _zh_replay(ctx)),
        (CHAPTERS_ZH[14], _zh_cases(ctx)),
        (CHAPTERS_ZH[15], _zh_timestamps(ctx)),
        (CHAPTERS_ZH[16], _zh_research_quality(ctx)),
        (CHAPTERS_ZH[17], _zh_methods(ctx)),
        (CHAPTERS_ZH[18], _zh_disclaimer()),
    ]


def render_report_zh(ctx: Mapping[str, Any]) -> str:
    header = [
        "# MedRadar 器械与药品产业方向雷达 · 中文研究报告",
        "",
        f"> 生成时间：{ctx['generated_at'] or DASH}（UTC） ｜ 统计窗口：{_range_text(ctx['window'])} ｜ "
        f"数据状态：{ctx['source_available']} 路可用 ｜ "
        f"中国空白度：{'不可用（NMPA 数据未加载）' if ctx['cn_unavailable'] else '可用'}",
        "",
        "本报告由 `python -m medradar report` 自动生成，全部数字来自当次运行的 `out/metrics.json`；"
        "字段缺失时显示「暂无数据」，不以 0 代替。",
        "",
    ]
    parts = list(header)
    for title, body in _zh_sections(ctx):
        parts.extend([f"## {title}", "", body.strip(), ""])
    return "\n".join(parts).rstrip() + "\n"


# --------------------------------------------------------------------------- English one-pager
def render_report_en(ctx: Mapping[str, Any]) -> str:
    status = ctx["data_status"]
    lines: list[str] = [
        "# MedRadar: FDA Device & Drug Industry Radar",
        "",
        f"_Generated {ctx['generated_at'] or 'not available'} (UTC) · Window {_range_text_en(ctx['window'])} · "
        f"Baseline {_range_text_en(ctx['baseline'])}_",
        "",
        "## Key takeaways",
        "",
    ]
    for index, text in enumerate(_en_conclusions(ctx)[:5], start=1):
        lines.append(f"{index}. {text}")
    lines.extend(
        [
            "",
            "## Data status",
            "",
            f"- Device / drug / trials: `{_s(status.get('device')) or 'unknown'}`, "
            f"`{_s(status.get('drug')) or 'unknown'}`, `{_s(status.get('trials')) or 'unknown'}`",
            f"- NMPA (China registrations): `{_s(status.get('nmpa')) or 'unavailable'}`"
            + (" - **unavailable (NMPA data not loaded)**; China-gap numbers are not inferred." if ctx["cn_unavailable"] else ""),
            f"- Prices: `{_s(status.get('prices')) or 'unknown'}`",
            f"- Events in window: {_fmt_int(ctx['event_total'])}",
            "",
        ]
    )
    tracks = ctx["tracks"]
    if tracks:
        lines.extend(["## Hottest device tracks", "", "| # | Track | THI | 95% CI | P(up) | Recent | Trend |", "|---|---|---|---|---|---|---|"])
        for index, track in enumerate(tracks[:8], start=1):
            lines.append(
                f"| {index} | {_md_cell(_en_track(track))} | {_fmt_thi(track.get('thi'))} | {_ci_text(track.get('ci'))} | "
                f"{_fmt_prob(track.get('prob_up'))} | {_fmt_int(track.get('recent'))} | {_trend_en(_trend(track))} |"
            )
        lines.append("")
    companies = ctx["companies"]
    if companies:
        lines.extend(["## Big-pharma momentum (top 5)", "", "| Company | Ticker | THI | P(up) | Recent |", "|---|---|---|---|---|"])
        for company in companies[:5]:
            lines.append(
                f"| {_md_cell(_en_company(company))} | {_md_cell(_s(company.get('ticker')) or '-')} | "
                f"{_fmt_thi(company.get('thi'))} | {_fmt_prob(company.get('prob_up'))} | {_fmt_int(company.get('recent'))} |"
            )
        lines.append("")
    if ctx["families"]:
        lines.extend(["## Product families", ""])
        for entry in ctx["families"][:5]:
            lines.append(
                f"- {_md_cell(_family_name(entry))} (`{_family_key(entry)}`): THI {_fmt_thi(entry.get('thi'))}, "
                f"P(up) {_fmt_prob(entry.get('prob_up'))}, {_fmt_int(entry.get('recent'))} events, "
                f"{_fmt_int(entry.get('new_entrants_12m'))} new entrants in 12 months."
            )
        if ctx["new_products"]:
            lines.append(f"- New products in the weekly radar: {len(ctx['new_products'])} (Chinese names + 510(k)/PMA numbers).")
        lines.append("")
    if ctx["migration"]:
        lines.append("## Portfolio migration")
        lines.append("")
        for item in ctx["migration"][:4]:
            lines.append(
                f"- {_md_cell(_en_company(item))} moved towards {_md_cell(_s(item.get('track_id')) or _s(item.get('track_zh')) or '-')}: "
                f"share {_fmt_share(item.get('share_recent'))} vs baseline {_fmt_share(item.get('share_base'))} "
                f"({_fmt_delta_en(item.get('delta'))})."
            )
        lines.append("")
    if ctx["firstseen"]:
        lines.extend(["## First seen in the last 90 days", ""])
        for item in ctx["firstseen"][:5]:
            lines.append(
                f"- {_s(item.get('event_date')) or 'n/a'} · {_md_cell(_en_company(item))} · "
                f"{_md_cell(_s(item.get('track_id')) or _s(item.get('track_zh')) or '-')} · "
                f"{_md_cell(_trim(item.get('device_name') or item.get('title'), 60))}"
            )
        lines.append("")
    if ctx["recalls"]:
        lines.extend(["## Recall clusters", "", "| Company | Recalls in window | Baseline / quarter | Top reason |", "|---|---|---|---|"])
        for item in ctx["recalls"][:5]:
            lines.append(
                f"| {_md_cell(_en_company(item))} | {_fmt_int(item.get('recent'))} | "
                f"{_fmt(item.get('baseline_per_q'), 2)} | {_md_cell(_s(item.get('reason_top')) or '-')} |"
            )
        lines.append("")
    if ctx["approvals"] or ctx["areas"] or ctx["trials"]:
        lines.extend(["## Drug side", ""])
        if ctx["approvals"]:
            lines.append(
                "Top NDA/BLA momentum: "
                + ", ".join(f"{_md_cell(_en_company(item))} (THI {_fmt_thi(item.get('thi'))})" for item in ctx["approvals"][:5])
                + "."
            )
        if ctx["areas"]:
            lines.append(
                "Hottest therapeutic areas: "
                + ", ".join(
                    f"{_md_cell(_s(item.get('track_id')) or _en_name(item))} (P {_fmt_prob(item.get('prob_up'))})"
                    for item in ctx["areas"][:4]
                )
                + "."
            )
        if ctx["trials"]:
            lines.append(
                "Trial starts: "
                + ", ".join(f"{_md_cell(_en_company(item))} ({_fmt_int(item.get('starts_recent'))})" for item in ctx["trials"][:5])
                + "."
            )
        lines.append("")
    lines.extend(["## China gap", ""])
    if ctx["cn_unavailable"]:
        lines.append(
            "**Unavailable (NMPA data not loaded).** China registration counts are `null`, not zero; "
            "no China-vs-US gap is inferred for this run."
        )
    elif ctx["cn_gap"]:
        lines.extend(["| Track | US events (24m) | US share | CN registrations | Gap |", "|---|---|---|---|---|"])
        for item in ctx["cn_gap"][:8]:
            lines.append(
                f"| {_md_cell(_s(item.get('track_id')) or _en_name(item))} | {_fmt_int(item.get('us_recent'))} | "
                f"{_fmt_share(item.get('us_share'), 1)} | {_fmt_int(item.get('cn_count'))} | "
                f"{_fmt_signed_pp(item.get('gap_index'))} |"
            )
    else:
        lines.append("No China-gap rows in this run.")
    lines.append("")
    trading = ctx["trading"]
    lines.extend(["## Signals and paper trading", ""])
    if ctx["signals"]:
        lines.append(f"- Signals generated: {len(ctx['signals'])}")
    else:
        lines.append("- Signals: not available")
    if trading and trading["curve"]:
        lines.append(
            f"- Paper portfolio: total return {_fmt_auto_pct(trading.get('total_return'))}, "
            f"max drawdown {_fmt_auto_pct(trading.get('max_drawdown'))}, "
            f"win rate {_fmt_prob(trading.get('win_rate'))}, trades {_fmt_int(trading.get('trades'))}."
        )
        lines.append(
            f"- Equity curve: {len(trading['curve'])} trading days, {trading['curve'][0][0] or 'n/a'} to {trading['curve'][-1][0] or 'n/a'}."
        )
    else:
        lines.append("- Paper trading: not available (trade stage not run, or insufficient data)")
    replay = ctx["replay"]
    lines.extend(["", "## Replay and research hygiene", ""])
    if replay.get("present") and replay.get("steps"):
        lines.append(
            f"- Replay: {len(replay['steps'])} steps from {_range_text_en(replay.get('window'))}; "
            f"multi-cost summary for {len(_d(replay.get('summary_by_cost')))} cost buckets."
        )
    else:
        lines.append("- Replay: not available (insufficient data or replay block missing).")
    if ctx["quality_rows"]:
        quality = ", ".join(f"{_s(key)} {_fmt_int(value)}" for key, value in ctx["quality_rows"][:4])
        lines.append(
            f"- Timestamp quality: {quality}; excluded from trading: {_fmt_int(ctx['excluded_from_trading'])}."
        )
    else:
        lines.append("- Timestamp quality: not available.")
    method = _s(ctx["multiple_testing"].get("method"))
    if method:
        lines.append(f"- Multiple testing: {method} correction over {_fmt_int(len(_l(ctx['multiple_testing'].get('adjusted'))))} tests.")
    else:
        lines.append("- Multiple testing: not available.")
    flagged = ctx["survivorship"].get("flagged")
    lines.append(f"- Survivorship flags: {_fmt_int(flagged) if flagged is not None else 'not available'}.")
    assumptions_url = _s(replay.get("assumptions_url"))
    if assumptions_url:
        lines.append(f"- Assumption register: `{assumptions_url}`.")
    lines.append("")
    cases = ctx["cases"]
    if cases.get("selected") or cases.get("stats"):
        lines.extend(["", "## Case library (in-sample evidence)", ""])
        case_stats = _case_stats_rows(cases["stats"])
        if case_stats:
            lines.append("- " + "; ".join(f"{label}: {value}" for label, value in case_stats[:4]))
        for case in cases["selected"][:3]:
            lines.append(
                f"- {_case_date(case)} · {_en_company(case)}: "
                f"{_trim(_s(case.get('event_zh')) or _s(case.get('title')), 90)} — "
                f"outcome {_case_outcome(case.get('outcome'))}; price 1/5/20/60d: {_case_price_text(case)}."
            )
        if cases["negative"]:
            lines.append(f"- Negative examples: {len(cases['negative'])} (missed / reversed cases).")
        lines.append("- Retrospective in-sample evidence only; not strategy performance.")
        lines.append("")
    lines.extend(
        [
            "",
            "## Method and limitations",
            "",
            "- Data lag of 2-12 days; rates are computed on the earliest public date (`event_date`) to limit look-ahead bias.",
            "- Company attribution is alias-based fuzzy matching: false negatives are kept visible, false positives are bounded.",
            "- Approvals are a regulatory activity proxy, not R&D spend or revenue.",
            "- Small samples are shrunk with a Gamma-Poisson empirical-Bayes prior; read THI together with its 95% interval.",
            "- Track mapping is a curated product-code / keyword dictionary and can misclassify edge cases.",
            "- NMPA data are never imputed: unavailable stays `null` and is reported as unavailable.",
            "",
            "## Disclaimer",
            "",
            "This report is generated automatically for open-source research and engineering demonstration only. "
            "It is **not investment advice**, not a recommendation and not an offer to trade. "
            "Public data may be delayed, incomplete or inconsistent; verify the original sources before any decision.",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _plain(text: str) -> str:
    """Strip the tiny bit of markdown used in Chinese conclusions for the EN page."""
    return _s(text).replace("**", "").replace("`", "")


# --------------------------------------------------------------------------- summary.csv
CSV_COLUMNS = (
    "section",
    "key",
    "name_zh",
    "name_en",
    "recent",
    "recent_per_q",
    "baseline_per_q",
    "thi",
    "prob_up",
    "ci_low",
    "ci_high",
    "major_share_recent",
    "major_share_base",
    "new_entrants_12m",
    "recalls_recent",
    "note",
)


def _csv_num(value: Any, digits: int = 3) -> str:
    number = _num(value)
    if number is None:
        return ""
    text = f"{number:.{digits}f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def _csv_ci(entry: Mapping[str, Any]) -> tuple[str, str]:
    ci = entry.get("ci")
    if isinstance(ci, (list, tuple)) and len(ci) >= 2:
        return _csv_num(ci[0]), _csv_num(ci[1])
    return "", ""


def render_summary_csv(ctx: Mapping[str, Any]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    name_map = ctx["name_map"]

    def row(section: str, key: Any, name_zh: Any, name_en: Any, entry: Mapping[str, Any], note: str = "") -> None:
        low, high = _csv_ci(entry)
        writer.writerow(
            [
                section,
                _s(key),
                _s(name_zh),
                _s(name_en),
                _csv_num(entry.get("recent")),
                _csv_num(entry.get("recent_per_q"), 2),
                _csv_num(entry.get("baseline_per_q"), 2),
                _csv_num(entry.get("thi"), 3),
                _csv_num(entry.get("prob_up"), 4),
                low,
                high,
                _csv_num(entry.get("major_share_recent"), 3),
                _csv_num(entry.get("major_share_base"), 3),
                _csv_num(entry.get("new_entrants_12m"), 0),
                _csv_num(entry.get("recalls_recent"), 0),
                note,
            ]
        )

    for track in ctx["tracks"]:
        row("device_track", track.get("track_id"), _track_name(track), track.get("name_en"), track, _trend(track))
    for company in ctx["companies"]:
        row(
            "device_company",
            company.get("key"),
            _company_name(company),
            company.get("name_en") or company.get("key"),
            company,
            _s(company.get("ticker")),
        )
    for item in ctx["migration"]:
        row(
            "device_migration",
            item.get("key"),
            _company_name(item),
            item.get("key"),
            item,
            f"track={name_map.get(_s(item.get('track_id'))) or _s(item.get('track_id'))}; "
            f"delta={_csv_num(item.get('delta'))}; js={_csv_num(item.get('js'))}",
        )
    for item in ctx["approvals"]:
        row("drug_approval", item.get("key"), _company_name(item), item.get("key"), item, f"nme_recent={_csv_num(item.get('nme_recent'), 0)}")
    for item in ctx["areas"]:
        row(
            "drug_area",
            item.get("track_id"),
            _track_name(item),
            item.get("name_en"),
            item,
            _trend(item),
        )
    for item in ctx["trials"]:
        row(
            "drug_trial",
            item.get("key"),
            _company_name(item),
            item.get("key"),
            item,
            "starts_recent=" + _csv_num(item.get("starts_recent"), 0),
        )
    for item in ctx["cn_gap"]:
        status = _s(item.get("cn_data_status")).lower()
        unavailable = status in ("unavailable", "") or _num(item.get("cn_count")) is None
        row(
            "cn_gap",
            item.get("track_id"),
            _track_name(item),
            item.get("name_en"),
            {"recent": item.get("us_recent")},
            f"cn_data_status={status or 'unavailable'}; "
            f"us_share={_csv_num(item.get('us_share'))}; "
            f"cn_count={'null' if unavailable else _csv_num(item.get('cn_count'), 0)}; "
            f"gap_index={'null' if unavailable else _csv_num(item.get('gap_index'))}",
        )

    # ---------------------------------------------------------------- W5 research blocks
    def flat_row(
        section: str,
        key: Any = "",
        name_zh: Any = "",
        name_en: Any = "",
        recent: Any = "",
        recent_per_q: Any = "",
        baseline_per_q: Any = "",
        thi: Any = "",
        prob_up: Any = "",
        note: str = "",
    ) -> None:
        writer.writerow(
            [
                section,
                _s(key),
                _s(name_zh),
                _s(name_en),
                _s(recent),
                _s(recent_per_q),
                _s(baseline_per_q),
                _s(thi),
                _s(prob_up),
                "",
                "",
                "",
                "",
                "",
                "",
                note,
            ]
        )

    for entry in ctx["families"]:
        flat_row(
            "product_family",
            _family_key(entry),
            _family_name(entry),
            entry.get("name_en"),
            _csv_num(entry.get("recent"), 0),
            "",
            "",
            _csv_num(entry.get("thi"), 3),
            _csv_num(entry.get("prob_up"), 4),
            f"companies={_company_count(entry)}; "
            f"new_entrants_12m={_csv_num(entry.get('new_entrants_12m'), 0)}; "
            f"first_seen={_s(entry.get('first_seen')) or 'null'}",
        )
    for item in ctx["new_products"]:
        flat_row(
            "product_new",
            _s(item.get("code")) or _s(item.get("k_number")),
            _s(item.get("device_name_zh")) or _s(item.get("device_name")),
            _s(item.get("family_zh")),
            _s(item.get("date")),
            "",
            "",
            "",
            "",
            f"company={_s(item.get('company_zh'))}; k_number={_s(item.get('k_number')) or 'null'}; "
            f"url={_s(item.get('url')) or 'null'}; definition={_trim(_s(item.get('definition_zh')), 120)}",
        )
    for item in ctx["company_portfolio"]:
        flat_row(
            "product_portfolio",
            "",
            _company_name(item),
            "",
            "",
            "",
            "",
            "",
            "",
            f"top_families={_top_families_text(item.get('top_families'), 5)}; "
            f"js_shift={_csv_num(item.get('js_shift'))}",
        )
    for step in (ctx["replay"].get("steps") or []):
        flat_row(
            "replay_step",
            _s(step.get("ticker")),
            _trim(_s(step.get("event_zh")) or _s(step.get("event")), 120),
            "",
            _s(step.get("t")),
            "",
            "",
            "",
            "",
            f"decision={_s(step.get('decision'))}; fill_price={_csv_num(step.get('fill_price'), 2)}; "
            f"shares={_csv_num(step.get('shares'), 0)}; outcome_1d={_csv_num(step.get('outcome_1d'), 4)}; "
            f"outcome_5d={_csv_num(step.get('outcome_5d'), 4)}; outcome_20d={_csv_num(step.get('outcome_20d'), 4)}; "
            f"url={_s(step.get('url')) or 'null'}",
        )
    for quality, count in ctx["quality_rows"]:
        flat_row(
            "timestamp_quality",
            quality,
            _quality_label(quality),
            "",
            _csv_num(count, 0),
            "",
            "",
            "",
            "",
            f"excluded_from_trading={_csv_num(ctx['excluded_from_trading'], 0) if ctx['excluded_from_trading'] is not None else 'null'}",
        )
    if ctx["multiple_testing"]:
        flat_row(
            "multiple_testing",
            _s(ctx["multiple_testing"].get("method")),
            "多重检验校正",
            "",
            _csv_num(len(_l(ctx["multiple_testing"].get("adjusted"))), 0),
            "",
            "",
            "",
            "",
            "adjusted=" + _trim(_describe(ctx["multiple_testing"].get("adjusted")), 200),
        )
    if ctx["survivorship"]:
        flat_row(
            "survivorship",
            "flagged",
            "生存偏差标记",
            "",
            _csv_num(ctx["survivorship"].get("flagged"), 0) if _num(ctx["survivorship"].get("flagged")) is not None else "",
            "",
            "",
            "",
            "",
            _trim(_describe(ctx["survivorship"]), 200),
        )
    for section, bucket in (
        ("case_selected", ctx["cases"]["selected"]),
        ("case_negative", ctx["cases"]["negative"]),
    ):
        for case in bucket:
            flat_row(
                section,
                _s(case.get("case_id")),
                _case_company(case),
                _s(case.get("ticker")),
                _case_date(case),
                "",
                "",
                "",
                "",
                f"category={_case_category(case.get('category'))}; "
                f"outcome={_case_outcome(case.get('outcome'))}; "
                f"direction={_s(case.get('direction'))}; "
                f"prices={_case_price_text(case)}; "
                f"source_url={_s(case.get('source_url')) or 'null'}; "
                f"evidence_quotes={len(_case_evidence(case))}",
            )
    return "\ufeff" + buffer.getvalue()


# --------------------------------------------------------------------------- SVG
def _svg_track_bars(tracks: Sequence[Mapping[str, Any]], limit: int = 12) -> str:
    rows = list(tracks)[:limit]
    if not rows:
        return f'<p class="empty">{_h(DASH)}</p>'
    width, label_width, bar_x = 920, 250, 258
    bar_width = 470
    usable = bar_width - 190
    row_height, top = 34, 28
    height = top + row_height * len(rows) + 16
    values = [_num(item.get("thi")) or 0.0 for item in rows]
    maximum = max([1.0] + values)
    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="赛道热度条">',
        f'<text class="axis-title" x="0" y="14">THI 相对热度（1.0 = 基线水平）</text>',
        f'<text class="axis-note" x="{width}" y="14" text-anchor="end">条长 = THI；文字 = THI 与 P(高于基线)</text>',
    ]
    for index, track in enumerate(rows):
        y = top + index * row_height
        thi = _num(track.get("thi"))
        ratio = (thi or 0.0) / maximum
        length = max(2.0, ratio * usable)
        trend = _trend(track)
        colour = {TREND_UP: "#0f766e", TREND_DOWN: "#b45309", TREND_FLAT: "#64748b"}.get(trend, "#94a3b8")
        name = _trim(_track_name(track), 16)
        parts.append(f'<text class="tick" x="0" y="{y + 14}">{_h(name)}</text>')
        parts.append(f'<rect class="bar" x="{bar_x}" y="{y + 3}" width="{length:.1f}" height="15" rx="2" fill="{colour}"/>')
        baseline_x = bar_x + usable / maximum
        if baseline_x <= bar_x + usable:
            parts.append(
                f'<line class="baseline" x1="{baseline_x:.1f}" y1="{y}" x2="{baseline_x:.1f}" y2="{y + 21}" />'
            )
        value_text = f"THI {_fmt_thi(thi)}" if thi is not None else "THI 暂无数据"
        probability = f"P {_fmt_prob(track.get('prob_up'))}"
        parts.append(f'<text class="val" x="{bar_x + length + 8:.1f}" y="{y + 14}">{_h(value_text)}　{_h(probability)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _svg_family_bars(families: Sequence[Mapping[str, Any]], limit: int = 12) -> str:
    rows = list(families)[:limit]
    if not rows:
        return f'<p class="empty">{_h(DASH)}</p>'
    width, bar_x = 920, 258
    bar_width = 470
    usable = bar_width - 190
    row_height, top = 34, 28
    height = top + row_height * len(rows) + 16
    values = [_num(item.get("thi")) or 0.0 for item in rows]
    maximum = max([1.0] + values)
    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="产品族热度条">',
        '<text class="axis-title" x="0" y="14">产品族 THI 相对热度（1.0 = 基线水平）</text>',
        f'<text class="axis-note" x="{width}" y="14" text-anchor="end">条长 = THI；文字 = THI 与 P(高于基线)</text>',
    ]
    for index, entry in enumerate(rows):
        y = top + index * row_height
        thi = _num(entry.get("thi"))
        length = max(2.0, (thi or 0.0) / maximum * usable)
        trend = _trend(entry)
        colour = {TREND_UP: "#0f766e", TREND_DOWN: "#b45309", TREND_FLAT: "#64748b"}.get(trend, "#94a3b8")
        name = _trim(_family_name(entry), 16)
        parts.append(f'<text class="tick" x="0" y="{y + 14}">{_h(name)}</text>')
        parts.append(f'<rect class="bar" x="{bar_x}" y="{y + 3}" width="{length:.1f}" height="15" rx="2" fill="{colour}"/>')
        baseline_x = bar_x + usable / maximum
        parts.append(f'<line class="baseline" x1="{baseline_x:.1f}" y1="{y}" x2="{baseline_x:.1f}" y2="{y + 21}" />')
        value_text = f"THI {_fmt_thi(thi)}" if thi is not None else "THI 暂无数据"
        parts.append(
            f'<text class="val" x="{bar_x + length + 8:.1f}" y="{y + 14}">{_h(value_text)}　'
            f'{_h("P " + _fmt_prob(entry.get("prob_up")))}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _svg_equity(points: Sequence[tuple[str, float]]) -> str:
    if len(points) < 2:
        return f'<p class="empty">{_h(DASH)}（模拟盘净值数据不足）</p>'
    width, height = 920, 280
    left, right, top, bottom = 76, width - 24, 22, height - 44
    values = [value for _, value in points]
    low, high = min(values), max(values)
    if math.isclose(low, high):
        padding = max(1.0, abs(high) * 0.02)
        low -= padding
        high += padding
    span = high - low

    def x_at(index: int) -> float:
        return left + (right - left) * index / (len(points) - 1)

    def y_at(value: float) -> float:
        return top + (bottom - top) * (1.0 - (value - low) / span)

    coords = " ".join(f"{x_at(index):.1f},{y_at(value):.1f}" for index, (_, value) in enumerate(points))
    area = f"M {x_at(0):.1f},{bottom:.1f} L " + " L ".join(
        f"{x_at(index):.1f},{y_at(value):.1f}" for index, (_, value) in enumerate(points)
    ) + f" L {x_at(len(points) - 1):.1f},{bottom:.1f} Z"
    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="模拟盘净值曲线">',
        f'<defs><linearGradient id="equity-fill" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="#1f4e79" stop-opacity="0.22"/>'
        f'<stop offset="100%" stop-color="#1f4e79" stop-opacity="0.02"/></linearGradient></defs>',
    ]
    for step in range(5):
        value = high - span * step / 4.0
        y = y_at(value)
        parts.append(f'<line class="grid" x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}"/>')
        parts.append(f'<text class="axis-note" x="{left - 10}" y="{y + 4:.1f}" text-anchor="end">{_h(_fmt(value, 0))}</text>')
    parts.append(f'<path d="{area}" fill="url(#equity-fill)" stroke="none"/>')
    parts.append(f'<polyline class="equity-line" points="{coords}" fill="none"/>')
    last_x, last_y = x_at(len(points) - 1), y_at(values[-1])
    parts.append(f'<circle class="dot" cx="{last_x:.1f}" cy="{last_y:.1f}" r="3.6"/>')
    parts.append(
        f'<text class="val" x="{last_x - 6:.1f}" y="{last_y - 12:.1f}" text-anchor="end">{_h(_fmt(values[-1], 0))}</text>'
    )
    first_label = _s(points[0][0]) or DASH
    last_label = _s(points[-1][0]) or DASH
    parts.append(f'<text class="axis-note" x="{left}" y="{height - 12}" text-anchor="start">{_h(first_label)}</text>')
    parts.append(f'<text class="axis-note" x="{right}" y="{height - 12}" text-anchor="end">{_h(last_label)}</text>')
    parts.append("</svg>")
    return "".join(parts)


# --------------------------------------------------------------------------- HTML
_CSS = """
:root{--bg:#f5f6f8;--panel:#fff;--ink:#17202a;--muted:#65707d;--line:#e2e6eb;--line-strong:#cbd3dc;
--accent:#1f4e79;--accent-soft:#eaf1f8;--teal:#0f766e;--amber:#b45309;--red:#b91c1c;--green:#15803d}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
font-size:15px;line-height:1.65;-webkit-font-smoothing:antialiased}
a{color:var(--accent)}
.wrap{max-width:1180px;margin:0 auto;padding:0 20px}
header.top{background:#fff;color:var(--ink);padding:22px 0 16px;border-bottom:3px solid var(--accent)}
.brandline{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap}
.mark{font-size:24px;font-weight:700;letter-spacing:.5px;color:var(--accent)}
.mark .dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:#0f766e;margin-left:6px;vertical-align:middle}
.sub{font-size:14px;color:var(--muted)}
.tagline{margin:6px 0 0;font-size:13px;color:var(--muted)}
.statusbar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:14px;padding:9px 14px;border-radius:8px;
font-size:13.5px;border:1px solid var(--line);background:#f8fafc}
.statusbar .dot{width:9px;height:9px;border-radius:50%;background:#94a3b8}
.statusbar.green .dot{background:#15803d}
.statusbar.amber .dot{background:#b45309}
.statusbar.red .dot{background:#b91c1c}
.statusbar .detail{color:var(--muted)}
.statusbar .warnchip{display:inline-block;padding:1px 8px;border-radius:999px;background:#fdf1f1;color:#9f1239;
border:1px solid #f3c6c6;font-size:12px}
.num,.kpi .value,.stat .v{font-family:ui-monospace,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
font-variant-numeric:tabular-nums}
td.num,th.num,.kpi .value,.stat .v{letter-spacing:-.2px}
main{padding:22px 0 8px}
.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:0 0 18px}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.kpi .label{font-size:12px;color:var(--muted);letter-spacing:.4px}
.kpi .value{font-size:22px;font-weight:650;margin-top:4px;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
.kpi .value.small{font-size:16px;line-height:1.4}
.kpi .hint{font-size:12px;color:var(--muted);margin-top:4px}
.toolbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;background:var(--panel);border:1px solid var(--line);
border-radius:10px;padding:10px 14px;margin:0 0 18px;position:sticky;top:0;z-index:5}
.toolbar label{font-size:12.5px;color:var(--muted)}
.toolbar input[type=search]{flex:1 1 240px;min-width:180px;border:1px solid var(--line-strong);border-radius:6px;padding:7px 10px;
font-size:13.5px;font-family:inherit;background:#fff;color:var(--ink)}
.toolbar input[type=search]:focus{outline:2px solid #b9cfe4;outline-offset:1px}
.toolbar .check{display:flex;align-items:center;gap:6px;font-size:13px;color:var(--ink);white-space:nowrap}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:18px 20px;margin:0 0 18px}
.panel>h2{margin:0 0 12px;font-size:17px;letter-spacing:.3px;padding-bottom:9px;border-bottom:1px solid var(--line)}
.panel>h3{margin:16px 0 8px;font-size:14.5px}
.note{color:var(--muted);font-size:13px;margin:0 0 10px}
.lead{font-size:14px;margin:0 0 12px;color:#2b3947}
code{background:#eef2f6;color:#1f3a52;padding:1px 4px;border-radius:3px;font-size:12.5px;
font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace}
ol.conclusions{margin:0;padding-left:22px}
ol.conclusions li{margin:0 0 7px}
.callout{border-left:4px solid var(--amber);background:#fdf8ee;padding:10px 14px;border-radius:0 6px 6px 0;font-size:13.5px;margin:0 0 12px}
.callout.danger{border-left-color:var(--red);background:#fdf1f1}
.callout.ok{border-left-color:var(--green);background:#f0f8f2}
.tablewrap{overflow-x:auto;border:1px solid var(--line);border-radius:8px;background:#fff}
table{border-collapse:collapse;width:100%;min-width:760px;font-size:13px}
th,td{padding:6px 9px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap;vertical-align:top}
th{background:#eef2f6;color:#33424f;font-weight:600;position:sticky;top:0;z-index:1}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover td{background:#fafbfc}
th.num,td.num{text-align:right;font-variant-numeric:tabular-nums}
td.name{font-weight:560}
.trend.up{color:var(--teal);font-weight:600}
.trend.down{color:var(--amber);font-weight:600}
.trend.flat{color:var(--muted)}
.empty{color:var(--muted);font-size:13.5px;margin:6px 0}
.chart{display:block;width:100%;height:auto;overflow:visible}
.chart text{font-family:inherit;fill:#3f4c59;font-size:12px}
.chart .axis-title{fill:var(--muted);font-size:12px}
.chart .axis-note{fill:var(--muted);font-size:11px}
.chart .tick{fill:#33424f;font-size:12.5px}
.chart .val{fill:#17202a;font-size:12px;font-weight:600}
.chart .baseline{stroke:#94a3b8;stroke-width:1;stroke-dasharray:3 3}
.chart .grid{stroke:#e7ebef;stroke-width:1}
.chart .equity-line{stroke:#1f4e79;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.chart .dot{fill:#fff;stroke:#1f4e79;stroke-width:2}
.chartlegend{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin-top:8px}
.chartlegend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px}
.statgrid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:0 0 14px}
.stat{border:1px solid var(--line);border-radius:8px;padding:10px 12px;background:#fbfcfd}
.stat .k{font-size:12px;color:var(--muted)}
.stat .v{font-size:18px;font-weight:650;font-variant-numeric:tabular-nums}
.radar{list-style:none;margin:0;padding:0}
.radar li{border:1px solid var(--line);border-radius:8px;padding:10px 13px;margin:0 0 8px;background:#fbfcfd}
.radar .name{font-weight:650;font-size:14.5px}
.radar .line{font-size:13px;color:#3f4c59;margin-top:2px}
.radar .line b{font-weight:560;color:var(--ink)}
.src{color:var(--muted);font-size:12px;overflow-wrap:anywhere}
.src-link{color:var(--accent);font-size:12.5px;text-decoration:none;border-bottom:1px dotted currentColor}
.timeline{list-style:none;margin:0;padding:2px 0 0 18px;border-left:2px solid var(--line-strong)}
.timeline li{position:relative;padding:0 0 15px 14px}
.timeline li:before{content:"";position:absolute;left:-25px;top:5px;width:9px;height:9px;border-radius:50%;
background:var(--accent);border:2px solid #fff;box-shadow:0 0 0 1px var(--line-strong)}
.timeline .when{font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums}
.timeline .what{font-weight:560;margin:1px 0 2px}
.timeline .meta{font-size:13px;color:#3f4c59}
.timeline .meta .sep{color:var(--muted);margin:0 5px}
.badge{display:inline-block;padding:0 7px;border-radius:999px;font-size:12px;border:1px solid;white-space:nowrap}
.badge-long{background:#eaf6f3;border-color:#b7dcd4;color:#0b5f57}
.badge-short{background:#fdf1ea;border-color:#f0cbb6;color:#8f3f12}
.badge-flat{background:#f1f3f6;border-color:#d7dde4;color:#4b5563}
.badge-hit{background:#eaf6f3;border-color:#b7dcd4;color:#0b5f57}
.badge-miss{background:#fdf1ea;border-color:#f0cbb6;color:#8f3f12}
.badge-mixed{background:#f5f1e6;border-color:#e2d6ae;color:#6b5320}
.casegrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:0 0 6px}
.casecard{border:1px solid var(--line);border-radius:10px;padding:14px 16px;background:#fbfcfd;min-width:0}
.casecard.negative{border-left:4px solid var(--amber);background:#fdfbf6}
.casehead{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;justify-content:space-between}
.casecase{font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums}
.casetitle{font-weight:650;font-size:14.5px;margin:2px 0 6px}
.casetitle .ticker{color:var(--muted);font-weight:560;font-size:12.5px;margin-left:4px}
.casemeta{font-size:12.5px;color:#3f4c59;margin:0 0 6px}
.casecard blockquote{margin:6px 0;padding:6px 12px;border-left:3px solid #c4d3e2;background:#f4f7fa;color:#33424f;
font-size:12.8px;line-height:1.55;border-radius:0 5px 5px 0;overflow-wrap:anywhere}
.caseprices{font-size:13px;margin:6px 0;font-variant-numeric:tabular-nums}
.caseverdict{font-size:13px;color:#3f4c59;margin:6px 0}
.case-link{color:var(--accent);font-size:12px;text-decoration:none;border-bottom:1px dotted currentColor;overflow-wrap:anywhere}
.case-link:hover{border-bottom-style:solid}
.src{color:var(--muted);font-size:12px;overflow-wrap:anywhere}
.up-text{color:#0b5f57;font-weight:600;font-variant-numeric:tabular-nums}
.down-text{color:#8f3f12;font-weight:600;font-variant-numeric:tabular-nums}
.flat-text{color:var(--muted);font-variant-numeric:tabular-nums}
footer{border-top:1px solid var(--line);background:#fff;margin-top:10px;padding:22px 0 28px;color:var(--muted);font-size:12.5px}
footer p{margin:0 0 6px}
footer .disclaimer{color:#4b5563}
@media (max-width:1020px){.kpis{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media (max-width:760px){
.wrap{padding:0 12px}
.kpis{grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}
.kpi{padding:11px 12px}
.kpi .value{font-size:19px}
.panel{padding:14px 13px}
.statgrid{grid-template-columns:repeat(2,minmax(0,1fr))}
.mark{font-size:20px}
.toolbar{position:static}
table{min-width:680px}
.casegrid{grid-template-columns:1fr}
}
@media print{header.top{background:#fff;color:#111}.toolbar{display:none}.panel{break-inside:avoid}}
"""

_JS = """
(function () {
  var search = document.getElementById('q');
  var onlyUp = document.getElementById('uponly');
  function allRows() {
    return document.querySelectorAll('table[data-filterable] tbody tr');
  }
  function apply() {
    var needle = search ? search.value.toLowerCase().trim() : '';
    var up = onlyUp ? onlyUp.checked : false;
    var rows = allRows();
    for (var i = 0; i < rows.length; i += 1) {
      var row = rows[i];
      var text = (row.textContent || '').toLowerCase();
      var visible = needle === '' || text.indexOf(needle) !== -1;
      if (up && row.getAttribute('data-trend') !== 'up') { visible = false; }
      row.style.display = visible ? '' : 'none';
    }
  }
  if (search) { search.addEventListener('input', apply); }
  if (onlyUp) { onlyUp.addEventListener('change', apply); }
})();
"""


def _table(
    columns: Sequence[tuple[str, str]],
    rows: Sequence[Sequence[Any]],
    *,
    filterable: bool = True,
    row_attrs: Sequence[str] | None = None,
    empty: str = DASH,
) -> str:
    if not rows:
        return f'<p class="empty">{_h(empty)}</p>'
    head = "".join(f'<th{_attr("class", css)}>{_h(label)}</th>' for label, css in columns)
    body: list[str] = []
    for index, row in enumerate(rows):
        extra = row_attrs[index] if row_attrs and index < len(row_attrs) else ""
        cells: list[str] = []
        for cell in row:
            if isinstance(cell, tuple):
                text, css = cell
            else:
                text, css = cell, ""
            cells.append(f'<td{_attr("class", css)}>{_h("" if text is None else str(text))}</td>')
        body.append(f"<tr{extra}>{''.join(cells)}</tr>")
    return (
        '<div class="tablewrap"><table'
        + (' data-filterable="1"' if filterable else "")
        + f"><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"
    )


def _panel(panel_id: str, title: str, body: str, note: str = "") -> str:
    note_html = f'<p class="note">{note}</p>' if note else ""
    return f'<section class="panel" id="{_h(panel_id)}"><h2>{_h(title)}</h2>{note_html}{body}</section>'


def _kpi(label: str, value: str, hint: str = "", small: bool = False) -> str:
    css = "value small" if small else "value"
    return (
        f'<div class="kpi"><div class="label">{_h(label)}</div>'
        f'<div class="{css}">{_h(value)}</div>'
        f'<div class="hint">{_h(hint)}</div></div>'
    )


def _status_for_html(ctx: Mapping[str, Any]) -> tuple[str, str, str]:
    data_status = ctx["data_status"]
    nmpa = _s(data_status.get("nmpa")).lower()
    prices = _s(data_status.get("prices")).lower()
    core_ok = any(
        _s(data_status.get(source)).lower() in ("ok", "loaded", "partial") for source in ("device", "drug", "trials")
    ) or (ctx["has_core"] and not data_status)
    if not ctx["has_core"] or not core_ok:
        return "red", "数据受限", "核心数据源未就绪，看板仅显示可用的美国侧公开数据"
    if nmpa != "loaded" or prices in ("", "missing", "unavailable"):
        return "amber", "部分可用", "NMPA 注册证或价格数据未加载，相关章节标注为不可用"
    return "green", "数据可用", "器械 / 药品 / 试验 / NMPA / 价格数据均已加载"


def _html_track_rows(ctx: Mapping[str, Any]) -> tuple[list[list[Any]], list[str]]:
    name_map = ctx["name_map"]
    rows: list[list[Any]] = []
    attrs: list[str] = []
    for index, track in enumerate(ctx["tracks"][:MAX_TRACK_ROWS], start=1):
        trend = _trend(track)
        rows.append(
            [
                str(index),
                (_track_name(track), "name"),
                _fmt_thi(track.get("thi")),
                _ci_text(track.get("ci")),
                _fmt_prob(track.get("prob_up")),
                _fmt_int(track.get("recent")),
                _fmt(track.get("recent_per_q"), 2),
                _fmt(track.get("baseline_per_q"), 2),
                _fmt_share(track.get("major_share_recent")),
                _fmt_int(track.get("new_entrants_12m")),
                _fmt_int(track.get("recalls_recent")),
                (trend, _trend_css(trend)),
            ]
        )
        attrs.append(f' data-trend="{_h(trend)}"')
    return rows, attrs


def _html_company_rows(ctx: Mapping[str, Any]) -> list[list[Any]]:
    name_map = ctx["name_map"]
    rows: list[list[Any]] = []
    for company in ctx["companies"][:MAX_COMPANY_ROWS]:
        top_tracks = []
        for pair in _l(company.get("top_tracks"))[:2]:
            if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                track_id = _s(pair[0])
                top_tracks.append(f"{name_map.get(track_id) or track_id} {_fmt_share(pair[1])}")
        rows.append(
            [
                (_company_name(company), "name"),
                _s(company.get("ticker")) or "—",
                _fmt_thi(company.get("thi")),
                _fmt_prob(company.get("prob_up")),
                _fmt_int(company.get("recent")),
                _fmt(company.get("recent_per_q"), 2),
                _fmt(company.get("baseline_per_q"), 2),
                _fmt_int(company.get("novelty_12m")),
                _fmt_int(company.get("recalls_recent")),
                "、".join(top_tracks) if top_tracks else DASH,
            ]
        )
    return rows


def _html_migration_rows(ctx: Mapping[str, Any]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for item in ctx["migration"][:MAX_COMPANY_ROWS]:
        delta = _num(item.get("delta"))
        rows.append(
            [
                (_company_name(item), "name"),
                _s(item.get("track_zh")) or _track_name(item),
                _fmt_share(item.get("share_recent")),
                _fmt_share(item.get("share_base")),
                _fmt_signed_pp(item.get("delta")),
                _fmt(item.get("js"), 3),
                "向该赛道倾斜" if (delta or 0) > 0 else "撤出该赛道",
            ]
        )
    return rows


def _html_firstseen_rows(ctx: Mapping[str, Any]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for item in ctx["firstseen"][:MAX_FIRSTSEEN_ROWS]:
        rows.append(
            [
                _s(item.get("event_date")) or DASH,
                (_company_name(item), "name"),
                _s(item.get("track_zh")) or _track_name(item),
                _s(item.get("product_code")) or "—",
                _trim(item.get("device_name") or item.get("title"), 34),
                _trim(item.get("title"), 52),
            ]
        )
    return rows


def _html_recall_rows(ctx: Mapping[str, Any]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for item in ctx["recalls"][:MAX_COMPANY_ROWS]:
        rows.append(
            [
                (_company_name(item), "name"),
                _fmt_int(item.get("recent")),
                _fmt(item.get("baseline_per_q"), 2),
                _s(item.get("reason_top")) or DASH,
            ]
        )
    return rows


def _html_drug_panels(ctx: Mapping[str, Any]) -> str:
    name_map = ctx["name_map"]
    parts: list[str] = []
    approval_rows = [
        [
            (_company_name(item), "name"),
            _s(item.get("ticker")) or "—",
            _fmt_int(item.get("recent")),
            _fmt(item.get("recent_per_q"), 2),
            _fmt(item.get("baseline_per_q"), 2),
            _fmt_thi(item.get("thi")),
            _fmt_prob(item.get("prob_up")),
            _fmt_int(item.get("nme_recent")),
        ]
        for item in ctx["approvals"][:MAX_COMPANY_ROWS]
    ]
    parts.append(
        "<h3>NDA/BLA 批准动量</h3>"
        + _table(
            [
                ("公司", ""),
                ("代码", ""),
                ("批准数", "num"),
                ("近期/季", "num"),
                ("基线/季", "num"),
                ("THI", "num"),
                ("P(高于基线)", "num"),
                ("新分子实体", "num"),
            ],
            approval_rows,
        )
    )
    area_rows = [
        [
            (name_map.get(_s(item.get("track_id"))) or _track_name(item), "name"),
            _fmt_int(item.get("recent")),
            _fmt_thi(item.get("thi")),
            _fmt_prob(item.get("prob_up")),
            (_trend(item), _trend_css(_trend(item))),
        ]
        for item in ctx["areas"][:MAX_COMPANY_ROWS]
    ]
    parts.append(
        "<h3>治疗领域</h3>"
        + _table(
            [("领域", ""), ("窗口事件", "num"), ("THI", "num"), ("P(高于基线)", "num"), ("趋势", "")],
            area_rows,
        )
    )
    trial_rows = []
    for item in ctx["trials"][:MAX_COMPANY_ROWS]:
        phases = [
            f"{PHASE_LABELS.get(phase, phase)} {_fmt_share(share, 0)}"
            for phase, share in list(_d(item.get("phase_mix")).items())[:4]
        ]
        trial_rows.append(
            [
                (_company_name(item), "name"),
                _fmt_int(item.get("starts_recent")),
                _fmt(item.get("recent_per_q"), 2),
                _fmt(item.get("baseline_per_q"), 2),
                _fmt_thi(item.get("thi")),
                "、".join(phases) if phases else DASH,
            ]
        )
    parts.append(
        "<h3>临床试验启动</h3>"
        + _table(
            [("公司", ""), ("启动数", "num"), ("近期/季", "num"), ("基线/季", "num"), ("THI", "num"), ("阶段结构", "")],
            trial_rows,
        )
    )
    return "".join(parts)


def _html_cn_gap_panel(ctx: Mapping[str, Any]) -> str:
    cn_gap = ctx["cn_gap"]
    if not cn_gap:
        return f'<p class="empty">{_h(DASH)}（cn_gap 为空，或分析阶段未计算中国空白度）</p>'
    banner = ""
    if ctx["cn_unavailable"]:
        banner = (
            '<div class="callout danger"><strong>中国空白度：不可用（NMPA 数据未加载）。</strong> '
            "NMPA 注册证数据缺失时 cn_count / cn_share 为 null，本页<b>不以 0 代替</b>，"
            "不计算也不解读 gap_index；下表仅保留美国侧事件作为方向参考。</div>"
        )
    rows: list[list[Any]] = []
    for item in cn_gap[:MAX_TRACK_ROWS]:
        status = _s(item.get("cn_data_status")).lower()
        cn_count = _num(item.get("cn_count"))
        unavailable = status in ("unavailable", "") or cn_count is None
        rows.append(
            [
                (_track_name(item), "name"),
                _fmt_int(item.get("us_recent")),
                _fmt_share(item.get("us_share"), 1),
                "不可用" if unavailable else _fmt_int(cn_count),
                "不可用" if unavailable else _fmt_share(item.get("cn_share"), 1),
                "不可用" if unavailable else _fmt_signed_pp(item.get("gap_index")),
                _cn_status_label(status),
            ]
        )
    table = _table(
        [
            ("赛道", ""),
            ("美国近 24 月事件", "num"),
            ("美国占比", "num"),
            ("中国注册证", "num"),
            ("中国占比", "num"),
            ("空白指数", "num"),
            ("数据状态", ""),
        ],
        rows,
    )
    demo = any(_s(item.get("cn_data_status")).lower() == "demo" for item in cn_gap)
    note = "demo 行为示例数据，仅用于验证管线，不代表真实 NMPA 注册证。" if demo else ""
    return banner + table + (f'<p class="note">{_h(note)}</p>' if note else "")


def _html_signals_panel(ctx: Mapping[str, Any]) -> str:
    signals = ctx["signals"]
    parts: list[str] = []
    if signals:
        rows: list[list[Any]] = []
        for signal in signals[:MAX_SIGNAL_ROWS]:
            direction = _num(signal.get("direction")) or 0
            rows.append(
                [
                    _s(signal.get("signal_date")) or DASH,
                    (_company_name(signal), "name"),
                    _s(signal.get("ticker")) or "—",
                    KIND_LABELS.get(_s(signal.get("kind")), _s(signal.get("kind")) or DASH),
                    "做多" if direction > 0 else "做空" if direction < 0 else "中性",
                    _fmt(_num(signal.get("score")), 2) if _num(signal.get("score")) is not None else DASH,
                    ctx["name_map"].get(_s(signal.get("track_id"))) or _s(signal.get("track_id")) or DASH,
                    _trim(signal.get("reason_zh"), 46),
                ]
            )
        parts.append(
            _table(
                [
                    ("信号日期", ""),
                    ("公司", ""),
                    ("代码", ""),
                    ("类型", ""),
                    ("方向", ""),
                    ("置信度", "num"),
                    ("赛道", ""),
                    ("理由", ""),
                ],
                rows,
            )
        )
    else:
        parts.append(f'<p class="empty">{_h(DASH)}（本期无信号）</p>')
    return "".join(parts)


def _html_trading_panel(ctx: Mapping[str, Any]) -> str:
    trading = ctx["trading"]
    if not trading:
        return f'<p class="empty">{_h(DASH)}（未运行 trade 阶段，或 trading.json 缺失）</p>'
    status = _s(trading.get("status"))
    curve = trading.get("curve") or []
    if status == "insufficient_data" or (not curve and trading.get("total_return") is None):
        return f'<p class="empty">{_h(DASH)}：样本不足，未运行模拟盘（status = {_h(status or "insufficient_data")}）</p>'
    stats = "".join(
        [
            _stat("区间总收益", _fmt_auto_pct(trading.get("total_return"))),
            _stat("最大回撤", _fmt_auto_pct(trading.get("max_drawdown"))),
            _stat("胜率", _fmt_prob(trading.get("win_rate"))),
            _stat("交易笔数", _fmt_int(trading.get("trades"))),
            _stat("平均持有收益", _fmt_auto_pct(trading.get("avg_hold_return"))),
            _stat("期末净值", _fmt(trading.get("final_equity"), 0)),
        ]
    )
    chart = _svg_equity(curve) if curve else f'<p class="empty">{_h(DASH)}（无净值曲线）</p>'
    attribution = ""
    if trading.get("by_kind"):
        rows = [
            [KIND_LABELS.get(_s(kind), _s(kind) or DASH), _format_kind_stats(value)]
            for kind, value in trading["by_kind"].items()
        ]
        attribution = '<h3>按信号类型归因</h3>' + _table([("类型", ""), ("指标", "")], rows)
    benchmark, horizons = _event_study_rows(trading)
    study = ""
    if horizons:
        rows = [
            [
                f"{horizon} 日",
                _fmt_auto_pct(stats.get("mean_ar")),
                _fmt_auto_pct(stats.get("median_ar")),
                _fmt_int(stats.get("n")),
                _fmt_prob(stats.get("hit_rate")),
                _ci_pct_text(stats.get("ci95")),
            ]
            for horizon, stats in horizons
        ]
        study = (
            f'<h3>事件研究：平均超额收益（基准 {_h(benchmark or "SPY")}）</h3>'
            + _table(
                [
                    ("窗口", ""),
                    ("平均 AR", "num"),
                    ("中位数 AR", "num"),
                    ("样本", "num"),
                    ("命中率", "num"),
                    ("95% CI", "num"),
                ],
                rows,
            )
        )
    return (
        f'<div class="statgrid">{stats}</div>{chart}'
        '<div class="chartlegend"><span><i style="background:#1f4e79"></i>模拟盘净值（美元）</span>'
        "<span>横轴为交易日，纵轴为组合净值；曲线为研究口径，未建模借券费与并购逼平。</span></div>"
        + study
        + attribution
    )


def _outcome_html(value: Any) -> str:
    """Signed outcome with glyph + colour, so direction never relies on colour alone."""
    text = _signed_pct_text(value)
    number = _num(value)
    if text == DASH or number is None:
        return f'<span class="flat-text">{_h(DASH)}</span>'
    if abs(number) <= 3.0:
        number *= 100.0
    css = "up-text" if number > 0 else "down-text" if number < 0 else "flat-text"
    return f'<span class="{css}">{_h(text)}</span>'


def _html_family_panel(ctx: Mapping[str, Any]) -> str:
    families = ctx["families"]
    if not families:
        return f'<p class="empty">{_h(DASH)}（products.families 为空，或产品级分析尚未运行）</p>'
    intro = (
        f'<p class="lead">产品族在赛道之下按 openFDA 产品码族细分，共 {len(families)} 个。'
        f'热度最高：<b>{_h(_family_name(families[0]))}</b>（ID '
        f'<code>{_h(_family_key(families[0]))}</code>）。</p>'
    )
    rows = []
    for index, entry in enumerate(families[:MAX_FAMILY_ROWS], start=1):
        rows.append(
            [
                str(index),
                (_family_name(entry), "name"),
                _fmt_thi(entry.get("thi")),
                _fmt_prob(entry.get("prob_up")),
                _fmt_int(entry.get("recent")),
                _company_count(entry),
                _fmt_int(entry.get("new_entrants_12m")),
                _cell_value(entry.get("first_seen"), 12),
                _family_key(entry),
            ]
        )
    table = _table(
        [
            ("#", "num"),
            ("产品族", ""),
            ("THI", "num"),
            ("P(高于基线)", "num"),
            ("窗口事件", "num"),
            ("公司数", "num"),
            ("12月新进入", "num"),
            ("首次出现", ""),
            ("产品族 ID", ""),
        ],
        rows,
    )
    legend = (
        '<div class="chartlegend"><span><i style="background:#0f766e"></i>升温</span>'
        '<span><i style="background:#64748b"></i>平稳</span>'
        '<span><i style="background:#b45309"></i>降温</span>'
        "<span>虚线 = THI 1.0 基线</span></div>"
    )
    return intro + _svg_family_bars(families) + legend + table


def _html_portfolio_panel(ctx: Mapping[str, Any]) -> str:
    portfolio = ctx["company_portfolio"]
    if not portfolio:
        return f'<p class="empty">{_h(DASH)}（products.company_portfolio 为空，或组合分析尚未运行）</p>'
    rows = []
    for item in portfolio[:MAX_COMPANY_ROWS]:
        shift = _num(item.get("js_shift"))
        direction = "结构明显变化 ▲" if (shift or 0) >= 0.1 else "结构相对稳定 →"
        rows.append(
            [
                (_company_name(item), "name"),
                _top_families_text(item.get("top_families")),
                _fmt(item.get("js_shift"), 3),
                direction,
            ]
        )
    return (
        '<p class="lead">组合迁移指数 <code>js_shift</code> 衡量公司产品族结构相对基线的 Jensen-Shannon 距离：'
        "越接近 0 越稳定，越大说明正在换产品方向。</p>"
        + _table(
            [("公司", ""), ("主产品族（窗口占比）", ""), ("JS 组合迁移", "num"), ("解读", "")],
            rows,
        )
    )


def _html_new_products_panel(ctx: Mapping[str, Any]) -> str:
    items = ctx["new_products"]
    if not items:
        return f'<p class="empty">{_h(DASH)}（products.new_products 为空，或本周没有新品记录）</p>'
    blocks: list[str] = []
    for item in items[:MAX_PRODUCT_ROWS]:
        name = _s(item.get("device_name_zh")) or _s(item.get("device_name")) or DASH
        company = _s(item.get("company_zh")) or DASH
        family = _s(item.get("family_zh")) or DASH
        code = _s(item.get("code")) or "—"
        definition = _trim(_s(item.get("definition_zh")) or _s(item.get("definition")), 120) or DASH
        number = _s(item.get("k_number")) or DASH
        source = _source_span(item.get("url"), limit=110) or f'<span class="src">来源：{_h(DASH)}</span>'
        blocks.append(
            f'<li><div class="name">{_h(_s(item.get("date")) or DASH)} · {_h(name)}</div>'
            f'<div class="line"><b>公司</b> {_h(company)} · <b>产品族</b> {_h(family)} · '
            f'<b>产品码</b> {_h(code)}</div>'
            f'<div class="line"><b>用途 / 定义</b> {_h(definition)}</div>'
            f'<div class="line"><b>510(k)/PMA</b> {_h(number)} · {source}</div></li>'
        )
    return (
        f'<p class="lead">本周新品 {len(items)} 条，每条保留中文产品名、用途、公司、编号与来源，可逐条回查。</p>'
        + '<ul class="radar">' + "".join(blocks) + "</ul>"
    )


def _html_replay_panel(ctx: Mapping[str, Any]) -> str:
    replay = ctx["replay"]
    if not replay.get("present"):
        return f'<p class="empty">{_h(DASH)}（replay 块缺失，回放研究尚未运行）</p>'
    status = _s(replay.get("status"))
    steps = replay.get("steps") or []
    if status == "insufficient_data" or not steps:
        return (
            f'<p class="empty">{_h(DASH)}：样本不足，回放研究未运行'
            f'（status = {_h(status or "insufficient_data")}）</p>'
        )
    items: list[str] = []
    for step in steps[:MAX_REPLAY_STEPS]:
        decision_text, decision_css = _decision_label(step.get("decision"))
        skip_reason = _s(step.get("skip_reason_zh"))
        if skip_reason:
            decision_text = f"{decision_text}（{_trim(skip_reason, 16)}）"
        url_source = _source_span(step.get("url"))
        meta = (
            f'成交价 {_h(_fmt(step.get("fill_price"), 2))} · 股数 {_h(_fmt_int(step.get("shares")))} · '
            f'1 日 {_outcome_html(step.get("outcome_1d"))} · '
            f'5 日 {_outcome_html(step.get("outcome_5d"))} · '
            f'20 日 {_outcome_html(step.get("outcome_20d"))}'
        )
        items.append(
            f'<li><div class="when">{_h(_when_text(step.get("t") or step.get("fill_date")) or DASH)} · '
            f'{_h(_s(step.get("ticker")) or DASH)} '
            f'<span class="{decision_css}">{_h(decision_text)}</span></div>'
            f'<div class="what">{_h(_trim(_s(step.get("event_zh")) or _s(step.get("event")) or DASH, 90))}</div>'
            f'<div class="meta">{meta}</div>'
            f'<div class="meta">{url_source}</div></li>'
        )
    timeline = '<ol class="timeline">' + "".join(items) + "</ol>"
    cost_rows = _replay_cost_rows(_d(replay.get("summary_by_cost")))
    cost_table = ""
    if cost_rows:
        cost_table = "<h3>多档交易成本下的回放结果</h3>" + _table(
            [
                ("成本档", ""),
                ("区间总收益", "num"),
                ("最大回撤", "num"),
                ("胜率", "num"),
                ("笔数", "num"),
                ("备注", ""),
            ],
            [list(row) for row in cost_rows],
        )
    assumptions = _assumptions_link(replay.get("assumptions_url"))
    footer_note = '<p class="note">回放只使用决策时点可见的信息；只做多，未建模借券费、并购逼平与滑点冲击，结果不可直接交易。</p>'
    if assumptions:
        footer_note = f'<p class="note">{assumptions}</p>' + footer_note
    return (
        f'<p class="lead">回放窗口 {_h(_range_text(replay.get("window")))}，共 {len(steps)} 步；'
        "每步记录决策时点、成交价与 1/5/20 日结果。</p>" + timeline + cost_table + footer_note
    )


def _sample_split_rows(sample_split: Mapping[str, Any]) -> list[tuple[str, str]]:
    """Flatten the research sample split (supports ``bounds`` or flat mappings)."""
    data = _d(sample_split)
    if not data:
        return []
    bounds = _d(data.get("bounds"))
    fractions = _d(data.get("sample_fractions"))
    if bounds:
        rows: list[tuple[str, str]] = []
        for label, info in bounds.items():
            info = _d(info)
            parts: list[str] = []
            start, end = _s(info.get("start")), _s(info.get("end"))
            if start or end:
                parts.append(f"{start or DASH} 至 {end or DASH}")
            if _num(info.get("n")) is not None:
                parts.append(f"{_fmt_int(info.get('n'))} 件")
            if _num(info.get("n_days")) is not None:
                parts.append(f"{_fmt(info.get('n_days'), 0)} 天")
            if _num(fractions.get(label)) is not None:
                parts.append(f"占比 {_fmt_share(fractions.get(label), 1)}")
            rows.append((str(label), " · ".join(parts) if parts else DASH))
        flags = [f"{key}={_describe(data.get(key))}" for key in ("key", "no_overlap", "status") if key in data]
        if flags:
            rows.append(("划分口径", "；".join(flags)))
        return rows
    return [(str(key), _describe(value)) for key, value in data.items()]


def _html_timestamps_panel(ctx: Mapping[str, Any]) -> str:
    parts: list[str] = []
    quality_rows = ctx["quality_rows"]
    total = ctx["quality_total"]
    if quality_rows:
        rows = [
            [
                (_quality_label(quality), "name"),
                _fmt_int(count),
                _fmt_share((count or 0) / total) if total else DASH,
            ]
            for quality, count in quality_rows[:12]
        ]
        parts.append(
            "<h3>时间质量分布</h3>"
            + _table([("时间质量档", ""), ("事件数", "num"), ("占比", "num")], rows)
        )
        excluded = ctx["excluded_from_trading"]
        parts.append(
            f'<p class="note">不进入交易研究的事件：<b>{_h(_fmt_int(excluded))}</b> 条'
            "（未知时间质量直接剔除）。</p>"
        )
        if ctx["timestamps_policy"]:
            parts.append(f'<p class="note">口径：{_h(ctx["timestamps_policy"])}</p>')
        parts.append(
            '<p class="note">统计口径：逐条读取事件表的 <code>timestamp_quality</code> 字段并计数，'
            "可按事件 ID 回查；unknown 不进入交易研究。</p>"
        )
    else:
        parts.append(f'<p class="empty">{_h(DASH)}（timestamps.by_quality 为空）</p>')
    if ctx["sample_split"]:
        parts.append(
            "<h3>样本划分</h3>"
            + _table([("划分", ""), ("说明", "")], _sample_split_rows(ctx["sample_split"]))
        )
    else:
        parts.append(f'<p class="empty">{_h(DASH)}（research.sample_split 为空）</p>')
    assumptions = _assumptions_link(ctx["replay"].get("assumptions_url"))
    if assumptions:
        parts.append(f'<p class="note">{assumptions}</p>')
    return "".join(parts)


def _html_research_panel(ctx: Mapping[str, Any]) -> str:
    parts: list[str] = []
    multiple_testing = ctx["multiple_testing"]
    if multiple_testing:
        method = _s(multiple_testing.get("method")) or "未标注"
        adjusted = _l(multiple_testing.get("adjusted"))
        parts.append(
            f'<p class="lead">多重检验校正：<b>{_h(method)}</b>；参与校正的检验 '
            f'{_h(_fmt_int(len(adjusted)))} 个。校正后仍显著的赛道/产品族才值得单独解读。</p>'
        )
        keys, rows = _adjusted_table(multiple_testing)
        if keys and rows:
            parts.append(_table([(key, "") for key in keys], rows))
        elif adjusted:
            preview = "、".join(_describe(value) for value in adjusted[:10])
            parts.append(f'<p class="note">调整后 p 值（前 10）：{_h(preview)}</p>')
        n_significant = _first_num(multiple_testing, ("n_significant", "significant", "n_rejected"))
        if n_significant is not None:
            parts.append(f'<p class="note">校正后显著项：<b>{_h(_fmt_int(n_significant))}</b> 个。</p>')
    else:
        parts.append(f'<p class="empty">{_h(DASH)}（research.multiple_testing 为空）</p>')
    survivorship = ctx["survivorship"]
    if survivorship:
        flagged = _num(survivorship.get("flagged"))
        extra = [
            f"{key}={_describe(value)}"
            for key, value in survivorship.items()
            if key != "flagged" and not isinstance(value, (dict, list))
        ][:3]
        text = (
            f'生存偏差标记：<b>{_h(_fmt_int(flagged))}</b> 个标的/事件'
            + (f"（{_h('；'.join(extra))}）" if extra else "")
        )
        if flagged and flagged > 0:
            parts.append(f'<div class="callout danger">{text}。相关结论应视为上界而非点估计。</div>')
        else:
            parts.append(f'<p class="note">{text}。</p>')
    else:
        parts.append(f'<p class="empty">{_h(DASH)}（research.survivorship 为空）</p>')
    parts.append(
        '<p class="note">校正对象为各赛道 / 产品族的 THI 检验，逐项 adjusted 与标记数均来自 '
        "<code>metrics.research</code>，可按赛道 ID 回查。</p>"
    )
    return "".join(parts)


def _case_card_html(case: Mapping[str, Any], negative: bool = False) -> str:
    quotes = _case_evidence(case)
    quote_html = "".join(f"<blockquote>{_h(quote)}</blockquote>" for quote in quotes)
    if not quote_html:
        quote_html = f'<p class="empty">{_h(DASH)}（无逐字证据）</p>'
    price_rows = _case_price_rows(case)
    price_html = (
        " · ".join(f"{label} {_outcome_html(value)}" for label, value in price_rows)
        if price_rows
        else f'<span class="flat-text">{_h(DASH)}</span>'
    )
    verdict = _s(case.get("verdict_zh"))
    case_id = _s(case.get("case_id")) or "未编号"
    ticker = _s(case.get("ticker")) or "—"
    css = "casecard negative" if negative else "casecard"
    return "".join(
        [
            f'<article class="{css}" id="case-{_h(case_id)}">',
            '<div class="casehead">',
            f'<span class="casecase">案例 {_h(case_id)} · {_h(_case_date(case))}</span>',
            f'<span class="{_case_outcome_css(case.get("outcome"))}">'
            f'{_h(_case_outcome(case.get("outcome")))}</span>',
            "</div>",
            f'<div class="casetitle">{_h(_case_company(case))}'
            f'<span class="ticker">{_h(ticker)}</span></div>',
            f'<div class="casemeta">事件：{_h(_s(case.get("event_zh")) or _s(case.get("title")) or DASH)}</div>',
            f'<div class="casemeta">分类：{_h(_case_category(case.get("category")))} · '
            f"方向：{_h(_case_direction(case))}</div>",
            quote_html,
            f'<div class="caseprices">价格反应（1/5/20/60 日）：{price_html}</div>',
            f'<div class="caseverdict">系统判定与事后：{_h(verdict or DASH)}</div>',
            f"<div>{_case_link_html(case)}</div>",
            "</article>",
        ]
    )


def _html_cases_panel(ctx: Mapping[str, Any]) -> str:
    cases = ctx["cases"]
    if not cases.get("present"):
        return f'<p class="empty">{_h(DASH)}（cases 块缺失，案例库尚未生成）</p>'
    selected = cases["selected"]
    negative = cases["negative"]
    stats = cases["stats"]
    if not selected and not negative and not stats:
        return f'<p class="empty">{_h(DASH)}（cases 块为空，或本期没有可展示的案例）</p>'
    parts: list[str] = [
        '<div class="callout"><strong>样本内回看，非策略业绩。</strong> '
        "案例用系统当时的判定对照事后 1/5/20/60 日价格反应，只用于展示证据链与判定依据，"
        "不代表样本外收益或可交易策略。</div>"
    ]
    stats_rows = _case_stats_rows(stats)
    if stats_rows:
        parts.append(
            "<h3>分类统计（样本内）</h3>"
            + _table([("指标", ""), ("数值", "num")], [[label, value] for label, value in stats_rows])
        )
        category_rows = _case_category_rows(stats)
        if category_rows:
            parts.append(
                _table(
                    [("案例分类", ""), ("样本数", "num"), ("20 日命中率", "num")],
                    [[row[0], row[1], row[2]] for row in category_rows],
                )
            )
    else:
        parts.append(f'<p class="empty">{_h(DASH)}（cases.stats 为空）</p>')
    if selected:
        parts.append(f"<h3>精选案例（{len(selected)} 个）</h3>")
        parts.append(
            '<div class="casegrid">'
            + "".join(_case_card_html(case) for case in selected[:MAX_CASE_CARDS])
            + "</div>"
        )
    else:
        parts.append(f'<p class="empty">{_h(DASH)}（cases.selected 为空）</p>')
    if negative:
        parts.append(f"<h3>反例（{len(negative)} 个，未命中 / 反向）</h3>")
        parts.append(
            '<div class="casegrid">'
            + "".join(_case_card_html(case, negative=True) for case in negative[:MAX_NEGATIVE_CASES])
            + "</div>"
        )
    else:
        parts.append(f'<p class="empty">{_h(DASH)}（cases.negative_examples 为空）</p>')
    parts.append(
        '<p class="note">证据为逐字引用；价格反应为事后统计（▲/▼ + 正负号）；'
        "原文链接可直接打开，页面本身不加载任何外部资源。</p>"
    )
    return "".join(parts)


def _stat(label: str, value: str) -> str:
    return f'<div class="stat"><div class="k">{_h(label)}</div><div class="v">{_h(value)}</div></div>'


def _html_kpis(ctx: Mapping[str, Any]) -> str:
    cards: list[str] = [
        _kpi("事件总数", f"{_fmt_int(ctx['event_total'])} 件", "统计窗口内全部事件"),
    ]
    tracks = ctx["tracks"]
    families = ctx["families"]
    family_hint = f"；另 {len(families)} 个产品族" if families else ""
    if tracks:
        top = tracks[0]
        cards.append(_kpi("热度最高赛道", _track_name(top), f"THI {_fmt_thi(top.get('thi'))} · {_trend(top)}", small=True))
        cards.append(
            _kpi(
                "赛道数量",
                f"{len(tracks)} 个",
                f"其中 {sum(1 for t in tracks if _trend(t) == TREND_UP)} 个升温{family_hint}",
            )
        )
    else:
        cards.append(_kpi("热度最高赛道", DASH, "device.tracks 为空", small=True))
        cards.append(_kpi("赛道数量", DASH, "暂无数据"))
    companies = ctx["companies"]
    if companies:
        median = sorted([_num(c.get("thi")) or 0.0 for c in companies])
        middle = median[len(median) // 2] if median else None
        cards.append(_kpi("大厂动量中位数", _fmt_thi(middle), f"{len(companies)} 家已匹配公司"))
    else:
        cards.append(_kpi("大厂动量中位数", DASH, "暂无数据"))
    cards.append(_kpi("近 90 天首次出现", f"{len(ctx['firstseen'])} 条", "首次见到的产品 / 公司"))
    cards.append(_kpi("信号数", f"{len(ctx['signals'])} 条", "喂给模拟盘的事件信号"))
    if ctx["new_products"]:
        cards.append(_kpi("本周新品雷达", f"{len(ctx['new_products'])} 条", "中文产品名 + 510(k)/PMA"))
    else:
        cards.append(_kpi("本周新品雷达", DASH, "暂无数据", small=True))
    trading = ctx["trading"]
    if trading and trading.get("total_return") is not None:
        cards.append(_kpi("模拟盘区间收益", _fmt_auto_pct(trading.get("total_return")), "研究口径，仅做多", small=True))
    else:
        cards.append(_kpi("模拟盘区间收益", DASH, "未运行 trade 或数据不足", small=True))
    replay = ctx["replay"]
    if replay.get("present") and replay.get("steps"):
        cards.append(_kpi("回放研究", f"{len(replay['steps'])} 步", "含 1/5/20 日结果", small=True))
    else:
        cards.append(_kpi("回放研究", DASH, "样本不足或未运行", small=True))
    cards.append(
        _kpi(
            "中国空白度",
            "不可用" if ctx["cn_unavailable"] else "可用",
            "NMPA 数据未加载，不作推断" if ctx["cn_unavailable"] else f"{len(ctx['cn_gap'])} 个赛道",
            small=True,
        )
    )
    return '<div class="kpis">' + "".join(cards) + "</div>"


def _html_status_panel(ctx: Mapping[str, Any]) -> str:
    data_status = ctx["data_status"]
    rows: list[list[Any]] = []
    for source, label in SOURCE_LABELS.items():
        if source not in data_status:
            continue
        rows.append([(label, "name"), _source_status_zh(source, data_status.get(source))])
    for source, value in data_status.items():
        if source not in SOURCE_LABELS:
            rows.append([source, _source_status_zh(source, value)])
    status_table = _table([("数据源", ""), ("状态", "")], rows, filterable=False)
    meta_rows = [
        ["生成时间（UTC）", ctx["generated_at"] or DASH],
        ["统计窗口", _range_text(ctx["window"])],
        ["基线窗口", _range_text(ctx["baseline"])],
        ["事件总数", f"{_fmt_int(ctx['event_total'])} 件"],
        ["事件构成", ctx["counts_text"]],
        ["事实库", ctx["db"] or DASH],
    ]
    meta_table = _table([("项目", ""), ("值", "")], meta_rows, filterable=False)
    warning = ""
    if ctx["cn_unavailable"]:
        warning = (
            '<div class="callout danger"><strong>中国侧数据警告：</strong>'
            "NMPA 数据不可用（NMPA 数据未加载），中国空白度不计算、不推断。</div>"
        )
    return f"{warning}<h3>数据源状态</h3>{status_table}<h3>运行元信息</h3>{meta_table}"


def _html_conclusions(ctx: Mapping[str, Any]) -> str:
    items = "".join(f"<li>{_h(_plain(line))}</li>" for line in _conclusion_lines(ctx))
    return f'<ol class="conclusions">{items}</ol>'


def _html_methods(ctx: Mapping[str, Any]) -> str:
    paragraphs = [line.strip() for line in _zh_methods(ctx).splitlines() if line.strip()]
    items: list[str] = []
    for line in paragraphs:
        text = line.lstrip("0123456789. ")
        safe = _h(text)
        safe = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", safe)
        safe = re.sub(r"`(.+?)`", r"<code>\1</code>", safe)
        items.append(f"<li>{safe}</li>")
    return f'<ol class="conclusions">{"".join(items)}</ol>'


def render_html(ctx: Mapping[str, Any]) -> str:
    status_class, status_label, status_detail = _status_for_html(ctx)
    nmpa_chip = (
        '<span class="warnchip">中国空白度不可用（NMPA 数据未加载）</span>'
        if ctx["cn_unavailable"]
        else ""
    )
    window = _range_text(ctx["window"])
    tracks = ctx["tracks"]
    track_rows, track_attrs = _html_track_rows(ctx)
    heat_chart = _svg_track_bars(tracks)
    company_rows = _html_company_rows(ctx)
    migration_rows = _html_migration_rows(ctx)
    firstseen_rows = _html_firstseen_rows(ctx)
    recall_rows = _html_recall_rows(ctx)
    drug_panels = _html_drug_panels(ctx)
    family_panel = _html_family_panel(ctx)
    portfolio_panel = _html_portfolio_panel(ctx)
    new_products_panel = _html_new_products_panel(ctx)
    replay_panel = _html_replay_panel(ctx)
    cases_panel = _html_cases_panel(ctx)
    timestamps_panel = _html_timestamps_panel(ctx)
    research_panel = _html_research_panel(ctx)

    company_columns = [
        ("公司", ""),
        ("代码", ""),
        ("THI", "num"),
        ("P(高于基线)", "num"),
        ("窗口事件", "num"),
        ("近期/季", "num"),
        ("基线/季", "num"),
        ("12月新产品码", "num"),
        ("近12月召回", "num"),
        ("主赛道", ""),
    ]
    track_columns = [
        ("#", "num"),
        ("赛道", ""),
        ("THI", "num"),
        ("95% 区间", "num"),
        ("P(高于基线)", "num"),
        ("窗口事件", "num"),
        ("近期/季", "num"),
        ("基线/季", "num"),
        ("大厂占比", "num"),
        ("新进入(12月)", "num"),
        ("近12月召回", "num"),
        ("趋势", ""),
    ]

    sections = [
        _panel("conclusions", "本期结论", _html_conclusions(ctx)),
        _panel("status", "数据状态", _html_status_panel(ctx)),
        _panel(
            "tracks",
            "赛道热度榜",
            f'<p class="lead">按 THI（Gamma-Poisson 收缩后的近期速率 / 基线速率）排序，共 {len(tracks)} 个赛道。'
            "区间整体高于 1.0 才算真正的升温；区间跨过 1.0 时只视为「方向不明确」。</p>"
            + heat_chart
            + '<div class="chartlegend"><span><i style="background:#0f766e"></i>升温</span>'
            '<span><i style="background:#64748b"></i>平稳</span>'
            '<span><i style="background:#b45309"></i>降温</span>'
            '<span>虚线 = THI 1.0 基线</span></div>'
            + _table(track_columns, track_rows, row_attrs=track_attrs),
            note="SVG 热力条由 Python 在构建时生成；表格可横向滚动。",
        ),
        _panel("companies", "大厂动量", _table(company_columns, company_rows)),
        _panel(
            "families",
            "产品族热度与新势力",
            family_panel,
            note="产品族 ID + 产品码可回查 config/product_code_tracks.json 与 openFDA 原始记录。",
        ),
        _panel(
            "migration",
            "结构迁移",
            _table(
                [
                    ("公司", ""),
                    ("赛道", ""),
                    ("窗口占比", "num"),
                    ("基线占比", "num"),
                    ("Δ", "num"),
                    ("JS 距离", "num"),
                    ("方向", ""),
                ],
                migration_rows,
            ),
            note="Δ 为赛道占比变化（百分点）；JS 为组合结构的 Jensen-Shannon 距离，用于区分「真正换方向」与「总量波动」。",
        ),
        _panel("portfolio", "公司产品组合迁移", portfolio_panel),
        _panel("new-products", "本周新品雷达", new_products_panel),
        _panel(
            "firstseen",
            "首次出现（近 90 天）",
            _table(
                [("日期", ""), ("公司", ""), ("中文赛道", ""), ("产品码", ""), ("器械 / 产品名", ""), ("标题", "")],
                firstseen_rows,
            ),
        ),
        _panel(
            "recalls",
            "召回与风险",
            _table(
                [("公司", ""), ("窗口内召回", "num"), ("基线/季", "num"), ("主要原因", "")],
                recall_rows,
            )
            + (
                "".join(
                    f'<p class="note">赛道维度召回：'
                    + "、".join(
                        f"{_h(_track_name(track))}（{_fmt_int(track.get('recalls_recent'))} 次）"
                        for track in tracks
                        if (_num(track.get("recalls_recent")) or 0) > 0
                    )
                    + "</p>"
                    if any((_num(track.get("recalls_recent")) or 0) > 0 for track in tracks)
                    else ""
                )
            ),
        ),
        _panel("drug", "药品侧", drug_panels if (ctx["approvals"] or ctx["areas"] or ctx["trials"]) else f'<p class="empty">{_h(DASH)}（药品数据未加载或字段为空）</p>'),
        _panel("cn-gap", "中国空白度", _html_cn_gap_panel(ctx)),
        _panel(
            "signals",
            "信号与模拟盘",
            _html_signals_panel(ctx) + '<h3>模拟盘净值</h3>' + _html_trading_panel(ctx),
        ),
        _panel(
            "replay",
            "回放研究",
            replay_panel,
            note="回放为静态时间轴：决策时点 → 成交价 → 1/5/20 日结果，逐笔可回查来源。",
        ),
        _panel(
            "cases",
            "案例库与证据",
            cases_panel,
            note="精选案例 + 反例 + 分类统计；均为样本内回看，非策略业绩。",
        ),
        _panel(
            "timestamps",
            "时间质量与样本划分",
            timestamps_panel,
            note="时间质量决定事件能否进入交易研究；样本划分按时间切分，避免用未来数据训练。",
        ),
        _panel("research", "多重检验与生存偏差", research_panel),
        _panel("method", "方法与局限", _html_methods(ctx)),
    ]

    footer = (
        '<footer><div class="wrap">'
        "<p><strong>MedRadar</strong> · 开源 FDA 器械与药品产业方向雷达 · 为中国医疗器械从业者与量化学生而做</p>"
        "<p>本页面完全自包含：内联 CSS、原生 JavaScript 与构建期生成的 SVG，不加载任何外部资源，可离线打开。</p>"
        "<p>数据来源：美国 FDA openFDA（510(k) / PMA / 召回 / Drugs@FDA）、ClinicalTrials.gov 等公开数据；"
        "中国 NMPA 注册证数据可用性以页内标注为准。</p>"
        '<p class="disclaimer">免责声明：本页面及随附报告仅用于开源研究与技术演示，不构成投资建议、荐股或交易邀约。'
        "数据可能存在延迟、遗漏与口径差异，读者应自行核验原始来源。作者不对使用本页内容造成的任何损失负责。</p>"
        "</div></footer>"
    )
    document = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="MedRadar report.py">
<meta name="description" content="MedRadar：FDA 器械与药品产业方向雷达，中文看板与研究报告。">
<title>MedRadar · 器械与药品产业方向雷达</title>
<style>{_CSS}</style>
</head>
<body>
<header class="top">
<div class="wrap">
<div class="brandline"><span class="mark">MedRadar<span class="dot"></span></span><span class="sub">FDA 器械与药品产业方向雷达 · 中文看板</span></div>
<div class="statusbar {status_class}"><span class="dot"></span><strong>数据状态：{_h(status_label)}</strong><span class="detail">{_h(status_detail)}</span>{nmpa_chip}</div>
<p class="tagline">统计窗口 {_h(window)} ｜ 生成时间 {_h(ctx["generated_at"] or DASH)}（UTC） ｜ 全部数字来自 metrics.json</p>
</div>
</header>
<main class="wrap">
{_html_kpis(ctx)}
<div class="toolbar">
<label for="q">表格筛选</label>
<input id="q" type="search" placeholder="输入公司 / 赛道 / 产品码 / 关键词…" autocomplete="off">
<label class="check"><input id="uponly" type="checkbox"> 仅看升温赛道</label>
</div>
{"".join(sections)}
</main>
{footer}
<script>{_JS}</script>
</body>
</html>
"""
    return document


# --------------------------------------------------------------------------- build
def build_report(
    metrics_path: str | Path = DEFAULT_METRICS,
    out_dir: str | Path = OUT_DIR,
    docs_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Render every report artefact from ``metrics_path`` into ``out_dir``.

    The same ``index.html`` is copied to ``docs/`` so GitHub Pages always serves
    the latest dashboard. ``docs_dir`` is exposed mainly so the offline tests can
    write to a temporary directory instead of the checked-in Pages entry.
    """
    metrics_path = Path(metrics_path)
    out_dir = Path(out_dir)
    docs_target = Path(docs_dir) if docs_dir is not None else Path(DOCS_DIR)
    ensure_dir(out_dir)
    ensure_dir(docs_target)

    metrics = read_json(metrics_path, default={})
    ctx = build_context(metrics, metrics_path=metrics_path, out_dir=out_dir)

    report_zh = render_report_zh(ctx)
    report_en = render_report_en(ctx)
    summary_csv = render_summary_csv(ctx)
    index_html = render_html(ctx)

    zh_path = write_text(out_dir / "report_zh.md", report_zh)
    en_path = write_text(out_dir / "report_en.md", report_en)
    csv_path = write_text(out_dir / "summary.csv", summary_csv)
    html_path = write_text(out_dir / "index.html", index_html)

    docs_index = write_text(docs_target / "index.html", index_html)
    nojekyll = write_text(docs_target / ".nojekyll", "")

    return {
        "out_dir": str(out_dir),
        "docs_dir": str(docs_target),
        "files": {
            "report_zh": str(zh_path),
            "report_en": str(en_path),
            "summary_csv": str(csv_path),
            "index_html": str(html_path),
            "docs_index": str(docs_index),
            "nojekyll": str(nojekyll),
        },
        "chapters_zh": len(CHAPTERS_ZH),
        "html_lines": index_html.count("\n") + 1,
        "html_bytes": len(index_html.encode("utf-8")),
        "report_zh_lines": report_zh.count("\n") + 1,
        "device_tracks": len(ctx["tracks"]),
        "device_companies": len(ctx["companies"]),
        "drug_approvals": len(ctx["approvals"]),
        "signals": len(ctx["signals"]),
        "cn_gap_status": _s(ctx["data_status"].get("nmpa")) or "unavailable",
        "trading": "ok" if ctx["trading"] else "missing",
        "product_families": len(ctx["families"]),
        "new_products": len(ctx["new_products"]),
        "company_portfolio": len(ctx["company_portfolio"]),
        "replay_steps": len(ctx["replay"].get("steps") or []),
        "replay_status": ctx["replay"].get("status") or "missing",
        "timestamp_quality": len(ctx["quality_rows"]),
        "research_blocks": sum(
            1
            for block in (ctx["sample_split"], ctx["multiple_testing"], ctx["survivorship"])
            if block
        ),
        "case_selected": len(ctx["cases"]["selected"]),
        "case_negative": len(ctx["cases"]["negative"]),
        "cases_present": bool(ctx["cases"]["present"]),
    }
