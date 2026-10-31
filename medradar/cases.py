"""Case library: one traceable record per notable event.

A case answers three questions, and every answer must be checkable:

1. **What happened?** Verbatim evidence quotes plus the SEC/FDA source URL.
2. **What did the system decide at the time?** Direction and materiality using
   only information available at ``available_at`` (no hindsight).
3. **What did the market do next?** Raw and SPY-abnormal returns at 1/5/20/60
   trading days, so a hit and a miss are both visible.

The library deliberately keeps *negative examples*: a tool that only shows
winning cases is marketing, not research.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .config import load_companies
from .db import DB
from .util import iso, parse_date, read_json, sha1, truncate, write_json

HORIZONS = (1, 5, 20, 60)
CATEGORY_DIRECTION = {
    "approval": 1,
    "trial_result": 1,   # refined below by text: "did not meet" flips it
    "label_expansion": 1,
    "deal": 0,
    "earnings": 0,
    "crl": -1,
    "safety": -1,
    "other": 0,
}

EVIDENCE_PATTERNS = {
    "approval": (r"fda (?:has )?approved", r"receives? fda approval", r"approval of"),
    "crl": (r"complete response letter", r"cannot approve", r"not approvable"),
    "trial_result": (r"met the primary endpoint", r"did not meet", r"topline results", r"primary endpoint"),
    "earnings": (r"financial results", r"revenue", r"net (?:loss|income)"),
    "safety": (r"recall", r"safety signal", r"adverse event"),
    "deal": (r"acquisition", r"merger", r"license agreement"),
    "label_expansion": (r"label expansion", r"expanded indication", r"new indication"),
}


def build_cases(
    db: DB,
    corpus_path: str | Path | None = None,
    max_cases: int = 120,
    benchmark: str = "SPY",
    missing_price_tickers: Iterable[str] | None = None,
    per_company: int = 3,
    per_month: int = 8,
) -> dict[str, Any]:
    """Build the case library from the EDGAR corpus, enriched with real prices.

    ``missing_price_tickers`` lets the caller fetch prices first (the pipeline
    does this through the normal price layer) so this function stays offline and
    deterministic.
    """
    items = load_corpus(corpus_path)
    if not items:
        return {"status": "insufficient_data", "reason": "no corpus", "selected": [], "negative_examples": []}

    price_cache = _load_price_cache(db, benchmark)
    registry = load_companies("device")

    cases: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    for item in items:
        ticker = (item.get("ticker") or "").upper()
        signal_day = parse_date(item.get("filed"))
        if not ticker or not signal_day:
            skipped["no_ticker_or_date"] += 1
            continue
        series = price_cache.get(ticker)
        if not series or len(series) < 10:
            skipped["no_prices"] += 1
            continue
        category = item.get("category") or "other"
        direction = _direction_for(item)
        if direction == 0:
            skipped["neutral"] += 1
            continue
        reactions = price_reaction(series, signal_day, benchmark_series=price_cache.get(benchmark), horizons=HORIZONS)
        if reactions.get("abnormal_20d") is None:
            skipped["no_forward_window"] += 1
            continue
        evidence = extract_evidence(item.get("text") or "", EVIDENCE_PATTERNS.get(category, ()))
        company_key = item.get("company_key") or ""
        entry = registry.get(company_key) or {}
        outcome = _outcome(direction, reactions["abnormal_20d"])
        cases.append(
            {
                "case_id": "case-" + sha1((item.get("accession") or "") + ticker)[:10],
                "date": iso(signal_day),
                "ticker": ticker,
                "company_zh": item.get("company_zh") or entry.get("name_zh") or item.get("company") or ticker,
                "event_zh": item.get("headline_zh") or _headline_zh(category, item.get("headline") or ""),
                "category": category,
                "direction": direction,
                "source_url": item.get("url") or "",
                "evidence_quotes": evidence or [truncate(item.get("headline") or "", 160)],
                "price_1d": reactions["abnormal_1d"],
                "price_5d": reactions["abnormal_5d"],
                "price_20d": reactions["abnormal_20d"],
                "price_60d": reactions["abnormal_60d"],
                "raw_20d": reactions["raw_20d"],
                "verdict_zh": (
                    f"系统判定：{'利好' if direction > 0 else '利空'}（{category}）；"
                    f"20 日{'跑赢' if (reactions['abnormal_20d'] or 0) > 0 else '跑输'}基准"
                ),
                "outcome": outcome,
            }
        )

    # Public cases must be diverse: cap per company and per month so one busy
    # filer cannot dominate the library. Both caps are parameters because the
    # defaults silently limit the library to ~per_month × months cases.
    per_company_count: Counter[str] = Counter()
    per_month_count: Counter[str] = Counter()
    selected: list[dict[str, Any]] = []
    for case in sorted(cases, key=lambda row: row["date"], reverse=True):
        month = case["date"][:7]
        if per_company_count[case["ticker"]] >= per_company or per_month_count[month] >= per_month:
            continue
        per_company_count[case["ticker"]] += 1
        per_month_count[month] += 1
        selected.append(case)
        if len(selected) >= max_cases:
            break

    hits = [c for c in selected if c["outcome"] == "hit"]
    misses = [c for c in selected if c["outcome"] == "miss"]
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in selected:
        by_category[case["category"]].append(case)
    stats = {
        "total": len(selected),
        "hit_rate_20d": round(len(hits) / len(selected), 4) if selected else None,
        "hit_rate_60d": _hit_rate(selected, "price_60d"),
        "by_category": [
            [
                category,
                len(rows),
                round(sum(1 for row in rows if row["outcome"] == "hit") / len(rows), 3),
            ]
            for category, rows in sorted(by_category.items())
        ],
        "skipped": dict(skipped),
        "corpus_total": len(items),
        "evidence_quotes_total": sum(len(case["evidence_quotes"]) for case in selected),
    }
    return {
        "status": "ok",
        "selected": selected,
        "negative_examples": misses[:8],
        "stats": stats,
        "benchmark": benchmark,
        "window": {
            "start": min((c["date"] for c in selected), default=""),
            "end": max((c["date"] for c in selected), default=""),
        },
    }


# --------------------------------------------------------------------- corpus IO
CORPUS_FIELDS = ("company", "company_zh", "company_key", "cik", "ticker", "accession",
                 "filed", "category", "headline", "headline_zh", "url", "text", "bucket")


def corpus_tickers(path: str | Path | None = None) -> list[str]:
    """Unique tickers mentioned by the corpus (for targeted price fetching)."""
    tickers = {str(item.get("ticker") or "").upper() for item in load_corpus(path)}
    return sorted(ticker for ticker in tickers if ticker)


BUCKET_CATEGORY_PRIORITY = (
    ("complete response letter", "crl"),
    ("did not meet", "trial_result"),
    ("announces positive topline", "trial_result"),
    ("met the primary endpoint", "trial_result"),
    ("receives fda approval", "approval"),
    ("fda approval", "approval"),
    ("financial results", "earnings"),
)


def _bucket_list(item: Mapping[str, Any]) -> list[str]:
    raw = item.get("buckets")
    if isinstance(raw, (list, tuple)):
        return [str(value).lower() for value in raw]
    text = str(raw or "")
    try:
        import ast

        parsed = ast.literal_eval(text)
        if isinstance(parsed, (list, tuple)):
            return [str(value).lower() for value in parsed]
    except (ValueError, SyntaxError):
        pass
    return [token for token in text.lower().replace("[", "").replace("]", "").replace("'", "").split(",") if token.strip()]


def enrich_items(items: Sequence[Mapping[str, Any]], cik_to_ticker: Mapping[str, str]) -> list[dict[str, Any]]:
    """Fill ticker/category/headline/company_key that the raw EDGAR pipeline lacks."""
    device = load_companies("device")
    drug = load_companies("drug")
    enriched: list[dict[str, Any]] = []
    for item in items:
        row = dict(item)
        cik = str(row.get("cik") or "").strip()
        if not row.get("ticker") and cik:
            row["ticker"] = cik_to_ticker.get(cik, "")
        buckets = _bucket_list(row)
        category = "other"
        for phrase, value in BUCKET_CATEGORY_PRIORITY:
            if any(phrase in bucket for bucket in buckets):
                category = value
                break
        row["category"] = row.get("category") or category
        company = str(row.get("company") or "").strip()
        key = ""
        for registry in (device, drug):
            matched, confidence, _alias = registry.resolve(company)
            if matched and confidence >= 0.82:
                key = matched
                break
        row["company_key"] = row.get("company_key") or key
        if not row.get("company_zh"):
            entry = device.get(key) or drug.get(key) or {}
            row["company_zh"] = entry.get("name_zh") or company
        if not row.get("headline"):
            row["headline"] = f"{company} · {' / '.join(buckets[:2])}"
        enriched.append(row)
    return enriched


def write_corpus(items: Sequence[Mapping[str, Any]], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    return target


def cik_ticker_map(fetcher: Any = None) -> dict[str, str]:
    """CIK → ticker from SEC's public company_tickers.json (cached)."""
    from .config import CACHE_DIR
    from .http import Fetcher

    if fetcher is None:
        from .live import SEC_UA

        fetcher = Fetcher(cache_dir=CACHE_DIR, min_interval=0.3, max_requests=5, ua=SEC_UA)
    payload = fetcher.get_json("https://www.sec.gov/files/company_tickers.json")
    mapping: dict[str, str] = {}
    for item in payload.values() if isinstance(payload, dict) else []:
        try:
            mapping[str(item["cik_str"])] = str(item["ticker"]).upper()
        except (KeyError, TypeError, ValueError):
            continue
    return mapping


def load_corpus(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Read ``corpus.jsonl`` (produced by ``scripts/build_corpus.py``)."""
    if path:
        target = Path(path)
    else:
        target = Path("data/edgar_corpus/corpus.jsonl")
    if not target.exists():
        return []
    items: list[dict[str, Any]] = []
    for line in target.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("text"):
            items.append(payload)
    return items


# ------------------------------------------------------------------- price maths
def _load_price_cache(db: DB, benchmark: str) -> dict[str, list[dict[str, Any]]]:
    rows = db.query("SELECT ticker, date, open, close, adj_close FROM prices ORDER BY ticker, date")
    cache: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        cache[row["ticker"]].append(
            {
                "date": row["date"],
                "open": row.get("open"),
                "close": row.get("adj_close") or row.get("close"),
            }
        )
    return dict(cache)


def price_reaction(
    series: Sequence[Mapping[str, Any]],
    signal_day: date,
    benchmark_series: Sequence[Mapping[str, Any]] | None = None,
    horizons: Sequence[int] = HORIZONS,
) -> dict[str, Any]:
    """Raw and abnormal returns from the first open after ``signal_day``.

    Prices are daily adjusted closes; the entry is the next session open, which
    is one full session later than the event date (conservative, never same-day).
    """
    dates = [row["date"] for row in series]
    entry_index = _first_index_after(dates, iso(signal_day))
    if entry_index is None:
        return {}
    entry = _float(series[entry_index].get("open")) or _float(series[entry_index].get("close"))
    if not entry:
        return {}
    result: dict[str, Any] = {"entry_date": dates[entry_index], "entry_price": round(entry, 4)}
    benchmark_dates = [row["date"] for row in (benchmark_series or [])]
    benchmark_entry_index = _first_index_after(benchmark_dates, iso(signal_day))
    for horizon in horizons:
        exit_index = entry_index + horizon
        if exit_index >= len(series):
            result[f"raw_{horizon}d"] = None
            result[f"abnormal_{horizon}d"] = None
            continue
        exit_price = _float(series[exit_index].get("close"))
        if not exit_price:
            result[f"raw_{horizon}d"] = None
            result[f"abnormal_{horizon}d"] = None
            continue
        raw = exit_price / entry - 1
        abnormal = raw
        if benchmark_series and benchmark_entry_index is not None:
            bench_exit = benchmark_entry_index + horizon
            if bench_exit < len(benchmark_series):
                bench_entry = _float(benchmark_series[benchmark_entry_index].get("open")) or 0.0
                bench_exit_price = _float(benchmark_series[bench_exit].get("close")) or 0.0
                if bench_entry and bench_exit_price:
                    abnormal = raw - (bench_exit_price / bench_entry - 1)
        result[f"raw_{horizon}d"] = round(raw, 6)
        result[f"abnormal_{horizon}d"] = round(abnormal, 6)
    return result


def _first_index_after(dates: Sequence[str], signal_date: str) -> int | None:
    for index, day in enumerate(dates):
        if day > signal_date:
            return index
    return None


def _float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _hit_rate(cases: Sequence[Mapping[str, Any]], key: str) -> float | None:
    values = [case.get(key) for case in cases if case.get(key) is not None]
    if not values:
        return None
    return round(sum(1 for value in values if value > 0) / len(values), 4)


# ---------------------------------------------------------------------- evidence
def extract_evidence(text: str, patterns: Iterable[str], limit: int = 3) -> list[str]:
    """Pull verbatim sentences that contain one of ``patterns``.

    Evidence must be copied, not generated: the case library is only credible if
    a reader can search the quoted sentence in the source document.
    """
    haystack = re.sub(r"\s+", " ", (text or ""))
    if not haystack:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", haystack)
    found: list[str] = []
    compiled = [re.compile(pattern, re.I) for pattern in patterns]
    for sentence in sentences:
        if not any(regex.search(sentence) for regex in compiled):
            continue
        cleaned = sentence.strip()
        if not cleaned or cleaned in found:
            continue
        found.append(truncate(cleaned, 280))
        if len(found) >= limit:
            break
    return found


# ------------------------------------------------------------------- small helper
def _direction_for(item: Mapping[str, Any]) -> int:
    category = item.get("category") or "other"
    direction = CATEGORY_DIRECTION.get(category, 0)
    if category == "trial_result":
        text = (item.get("text") or "").lower()
        if any(token in text for token in ("did not meet", "failed to meet", "did not achieve")):
            direction = -1
        elif "met the primary endpoint" in text or "topline" in text:
            direction = 1
    if category == "earnings":
        direction = 0
    return direction


def _outcome(direction: int, abnormal_20d: float | None) -> str:
    if abnormal_20d is None:
        return "unknown"
    aligned = direction * abnormal_20d
    if aligned > 0.02:
        return "hit"
    if aligned < -0.02:
        return "miss"
    return "mixed"


def _headline_zh(category: str, fallback: str) -> str:
    labels = {
        "approval": "FDA 批准",
        "crl": "收到 CRL",
        "trial_result": "临床数据读出",
        "earnings": "财报",
        "safety": "安全/召回",
        "deal": "交易",
        "label_expansion": "标签扩展",
        "other": "其他事件",
    }
    return f"{labels.get(category, '事件')}：{truncate(fallback, 80)}"


# ------------------------------------------------------------------------ output
def write_cases(cases: Mapping[str, Any], out_dir: str | Path = "out/cases") -> dict[str, Any]:
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    write_json(target / "cases.json", cases)
    (target / "cases.md").write_text(render_markdown(cases), encoding="utf-8")
    return {"json": str(target / "cases.json"), "markdown": str(target / "cases.md")}


def render_markdown(cases: Mapping[str, Any], limit: int = 20) -> str:
    stats = cases.get("stats") or {}
    lines = [
        "# MedRadar 案例库",
        "",
        f"- 语料总量：{stats.get('corpus_total', 0)}",
        f"- 入选案例：{stats.get('total', 0)}",
        f"- 20 日命中率：{stats.get('hit_rate_20d')}",
        f"- 逐字证据条数：{stats.get('evidence_quotes_total', 0)}",
        "",
        "> 样本内研究演示，非策略业绩；价格反应为相对 SPY 的超额收益。",
        "",
    ]
    for case in (cases.get("selected") or [])[:limit]:
        lines += [
            f"## {case['date']} · {case['company_zh']}（{case['ticker']}）· {case['event_zh']}",
            "",
            f"- 类别：{case['category']}｜方向：{case['direction']:+d}｜结果：{case['outcome']}",
            f"- 超额收益：1日 {_pct(case.get('price_1d'))}｜5日 {_pct(case.get('price_5d'))}"
            f"｜20日 {_pct(case.get('price_20d'))}｜60日 {_pct(case.get('price_60d'))}",
            f"- 来源：{case.get('source_url') or '（无）'}",
        ]
        for quote in case.get("evidence_quotes") or []:
            lines.append(f"> {quote}")
        lines.append("")
    negatives = cases.get("negative_examples") or []
    if negatives:
        lines += ["## 反例（系统判定与事后走势不一致）", ""]
        for case in negatives[:5]:
            lines.append(
                f"- {case['date']} {case['company_zh']}（{case['ticker']}）"
                f" {case['event_zh']}：20日超额 {_pct(case.get('price_20d'))}"
            )
        lines.append("")
    return "\n".join(lines)


def event_study_summary(cases: Mapping[str, Any], horizons: Sequence[int] = HORIZONS) -> dict[str, Any]:
    """Aggregate the case library into an event study with proper statistics.

    Uses block bootstrap (blocks = event month) because overlapping holding
    windows are correlated, and Holm correction across the category × horizon
    tests so the result can be reported honestly.
    """
    try:
        from .stats import (
            block_bootstrap_ci,
            block_bootstrap_p_value,
            mean,
            median,
            multiple_testing,
            stdev,
            t_stat,
        )
    except Exception:  # pragma: no cover - stats ships with the package
        return {}
    selected = list(cases.get("selected") or [])
    if not selected:
        return {}
    result: dict[str, Any] = {"n_cases": len(selected), "by_horizon": {}}
    categories = sorted({str(case.get("category") or "other") for case in selected})
    global_tests: list[dict[str, Any]] = []
    for horizon in horizons:
        key = f"price_{horizon}d"
        per_category: dict[str, Any] = {}
        for category in categories:
            rows = [case for case in selected if str(case.get("category") or "other") == category and case.get(key) is not None]
            if len(rows) < 3:
                continue
            # Direction-aligned: a CRL is a "win" when the stock falls. Report both
            # the aligned series (what the signal claims) and the raw one.
            raw_values = [float(case[key]) for case in rows]
            values = [float(case[key]) * (int(case.get("direction") or 0) or 1) for case in rows]
            blocks = [str(case.get("date") or "")[:7] for case in rows]
            # Small-cap biotech returns are wildly fat-tailed (a single approval can
            # be +200%). The raw mean is then meaningless, so inference runs on a
            # 2.5/97.5-percentile winsorised series while raw stats stay visible.
            ordered = sorted(values)
            low = ordered[max(0, int(0.025 * (len(ordered) - 1)))]
            high = ordered[min(len(ordered) - 1, int(0.975 * (len(ordered) - 1)))]
            winsorised = [min(high, max(low, value)) for value in values]
            ci = block_bootstrap_ci(winsorised, blocks=blocks, seed=7)
            # Same sampling model for CI and p-value: block bootstrap, not a t-test.
            p_value = block_bootstrap_p_value(winsorised, blocks=blocks, seed=7)["p"]
            stat = t_stat(winsorised)
            per_category[category] = {
                "n": len(values),
                "mean": round(mean(winsorised), 6),
                "raw_mean": round(mean(raw_values), 6),
                "median": round(median(values), 6),
                "p10": round(ordered[max(0, int(0.10 * (len(ordered) - 1)))], 6),
                "p90": round(ordered[min(len(ordered) - 1, int(0.90 * (len(ordered) - 1)))], 6),
                "std": round(stdev(winsorised), 6),
                "t": round(stat, 4) if stat is not None else None,
                "p": p_value,
                "ci95": [round(ci["lo"], 6), round(ci["hi"], 6)] if ci else None,
                "hit_rate": round(sum(1 for value in values if value > 0) / len(values), 4),
                "winsor_bounds": [round(low, 6), round(high, 6)],
            }
            if p_value is not None:
                global_tests.append({"label": f"{category}:{horizon}d", "raw_p": p_value, "horizon": horizon})
        result["by_horizon"][str(horizon)] = {"categories": per_category}

    # Holm correction over the **whole family** (category × horizon), not once per
    # horizon; otherwise the reported family size is understated 4x.
    adjusted_rows: list[dict[str, Any]] = []
    if global_tests:
        corrected = multiple_testing(
            [test["raw_p"] for test in global_tests],
            method="holm",
            labels=[test["label"] for test in global_tests],
        )
        adjusted_rows = list(corrected.get("adjusted") or [])
        by_label = {str(row.get("key")): row for row in adjusted_rows}
        for test in global_tests:
            row = by_label.get(str(test["label"]))
            if not row:
                continue
            category, horizon_label = str(test["label"]).rsplit(":", 1)
            horizon = horizon_label.rstrip("d")
            block = result["by_horizon"].get(horizon) or {}
            if category in (block.get("categories") or {}):
                block["categories"][category]["p_holm"] = row.get("adjusted_p")
                block["categories"][category]["significant_holm"] = bool(row.get("significant"))
    result["multiple_testing"] = {
        "method": "holm",
        "family": "category × horizon",
        "m": len(global_tests),
        "rejected": sum(1 for row in adjusted_rows if row.get("significant")),
        "tests": adjusted_rows,
    }
    for horizon in horizons:
        block = result["by_horizon"].get(str(horizon)) or {}
        horizon_tests = [
            row for row in adjusted_rows if str(row.get("key", "")).endswith(f":{horizon}d")
        ]
        block["multiple_testing"] = {
            "method": "holm",
            "family": "category × horizon",
            "m": len(global_tests),
            "rejected": sum(1 for row in horizon_tests if row.get("significant")),
            "tests": horizon_tests,
        }
        result["by_horizon"][str(horizon)] = block
    return result


def _pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:+.2f}%"
    except (TypeError, ValueError):
        return "—"
