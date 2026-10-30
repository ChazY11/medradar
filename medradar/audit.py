"""Data-quality audit: the numbers that tell you whether the dataset can be trusted.

A research tool is only as good as its dirtiest table. This module reports the
things that silently break analyses: missing dates, unmatched companies, unmapped
product codes, duplicate rows, price gaps, future timestamps and stale sources.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping

from .config import load_companies, load_tracks
from .db import DB
from .util import iso, parse_date, read_json, today_utc

EXPECTED_SOURCES = {
    "openfda_device_510k": "510k",
    "openfda_device_pma": "pma",
    "openfda_device_recall": "device_recall",
    "openfda_drug_drugsfda": "drug_approval",
    "ctgov": "trial",
    "nmpa": "nmpa_registration",
    "nmpa_demo": "nmpa_registration",
}


def run_audit(db: DB, stale_days: int = 30) -> dict[str, Any]:
    """Return a structured audit; every check has a status and a count."""
    today = today_utc()
    events = db.query(
        "SELECT event_id, source, kind, event_date, available_at, timestamp_quality,"
        " company_key, track_id, product_code, as_of FROM events"
    )
    total = len(events)
    by_kind = Counter(event.get("kind") or "unknown" for event in events)
    by_source = Counter(event.get("source") or "unknown" for event in events)
    by_year = Counter((event.get("event_date") or "")[:4] or "unknown" for event in events)

    missing_date = [event for event in events if not event.get("event_date")]
    missing_available = [event for event in events if not event.get("available_at")]
    future = [
        event
        for event in events
        if (parse_date(event.get("event_date")) or today) > today + timedelta(days=1)
    ]
    bad_quality = [
        event
        for event in events
        if (event.get("timestamp_quality") or "unknown") not in ("datetime", "date", "estimated", "unknown")
    ]

    def match_rate(kind: str | None = None) -> dict[str, Any]:
        subset = [event for event in events if kind is None or event.get("kind") == kind]
        if not subset:
            return {"total": 0, "matched": 0, "rate": None}
        matched = sum(1 for event in subset if event.get("company_key"))
        tracked = sum(1 for event in subset if event.get("track_id"))
        return {
            "total": len(subset),
            "matched": matched,
            "rate": round(matched / len(subset), 4),
            "track_mapped": tracked,
            "track_rate": round(tracked / len(subset), 4),
        }

    company_rates = {kind: match_rate(kind) for kind in sorted(by_kind)}

    product_codes = db.query("SELECT product_code, track_id FROM product_codes")
    codes_total = len(product_codes)
    codes_mapped = sum(1 for row in product_codes if row.get("track_id"))

    prices = db.query("SELECT ticker, date, close FROM prices")
    price_tickers: dict[str, list[str]] = defaultdict(list)
    for row in prices:
        price_tickers[row["ticker"]].append(row["date"])
    tickers = len(price_tickers)
    tickers_with_252 = sum(1 for days in price_tickers.values() if len(days) >= 252)
    price_dates = [day for days in price_tickers.values() for day in days]
    bad_prices = db.query("SELECT COUNT(*) AS n FROM prices WHERE close IS NULL OR close <= 0")
    duplicate_prices = db.query(
        "SELECT COUNT(*) AS n FROM (SELECT ticker, date, COUNT(*) c FROM prices GROUP BY ticker, date HAVING c > 1)"
    )

    signals = db.query("SELECT COUNT(*) AS n FROM signals")
    last_event = max((event.get("event_date") or "" for event in events), default="")
    staleness_days = None
    if last_event:
        parsed = parse_date(last_event)
        if parsed:
            staleness_days = (today - parsed).days

    checks: list[dict[str, Any]] = [
        _check("events_present", total > 0, total, "events row count"),
        _check("dates_complete", not missing_date, len(missing_date), "events without event_date"),
        _check("availability_complete", not missing_available, len(missing_available), "events without available_at"),
        _check("no_future_events", not future, len(future), "event_date beyond today"),
        _check("quality_values_valid", not bad_quality, len(bad_quality), "invalid timestamp_quality"),
        _check("product_codes_mapped", codes_total == 0 or codes_mapped / max(1, codes_total) > 0.2,
               codes_mapped, f"{codes_mapped}/{codes_total} product codes mapped"),
        _check("prices_present", tickers > 0, tickers, "distinct tickers with prices"),
        _check("prices_clean", not bad_prices or int(bad_prices[0]["n"]) == 0,
               int(bad_prices[0]["n"]) if bad_prices else 0, "non-positive closes"),
        _check("prices_not_duplicated", not duplicate_prices or int(duplicate_prices[0]["n"]) == 0,
               int(duplicate_prices[0]["n"]) if duplicate_prices else 0, "duplicate (ticker,date)"),
        _check("data_fresh", staleness_days is not None and staleness_days <= stale_days,
               staleness_days, f"days since latest event (threshold {stale_days})"),
    ]
    failures = [check for check in checks if check["status"] == "FAIL"]
    warnings = [check for check in checks if check["status"] == "WARN"]

    return {
        "status": "fail" if failures else ("warn" if warnings else "ok"),
        "generated_at": iso(today),
        "events": {
            "total": total,
            "by_kind": dict(by_kind),
            "by_source": dict(by_source),
            "by_year": dict(sorted(by_year.items())),
            "latest_event_date": last_event,
            "staleness_days": staleness_days,
            "missing_date": len(missing_date),
            "missing_available_at": len(missing_available),
            "future_dated": len(future),
            "quality": dict(Counter(event.get("timestamp_quality") or "unknown" for event in events)),
        },
        "companies": {
            "registry_size": len(load_companies("device").all()) + len(load_companies("drug").all()),
            "rates_by_kind": company_rates,
        },
        "tracks": {
            "registry_size": len(load_tracks("device").all()),
            "product_codes_total": codes_total,
            "product_codes_mapped": codes_mapped,
            "mapped_rate": round(codes_mapped / codes_total, 4) if codes_total else None,
        },
        "prices": {
            "tickers": tickers,
            "tickers_with_252_days": tickers_with_252,
            "rows": len(prices),
            "start": min(price_dates) if price_dates else "",
            "end": max(price_dates) if price_dates else "",
            "bad_closes": int(bad_prices[0]["n"]) if bad_prices else 0,
            "duplicate_keys": int(duplicate_prices[0]["n"]) if duplicate_prices else 0,
        },
        "signals": int(signals[0]["n"]) if signals else 0,
        "checks": checks,
        "failures": [check["name"] for check in failures],
        "warnings": [check["name"] for check in warnings],
    }


def _check(name: str, ok: bool, value: Any, detail: str, warn_only: bool = False) -> dict[str, Any]:
    if ok:
        status = "PASS"
    elif warn_only:
        status = "WARN"
    else:
        status = "FAIL"
    return {"name": name, "status": status, "value": value, "detail": detail}


def render_audit_markdown(audit: Mapping[str, Any]) -> str:
    events = audit.get("events") or {}
    prices = audit.get("prices") or {}
    lines = [
        "# MedRadar 数据质量审计",
        "",
        f"- 状态：{audit.get('status')}",
        f"- 事件总数：{events.get('total', 0)}",
        f"- 最新事件：{events.get('latest_event_date')}（滞后 {events.get('staleness_days')} 天）",
        f"- 价格覆盖：{prices.get('tickers')} 个 ticker / {prices.get('rows')} 行（{prices.get('start')} → {prices.get('end')}）",
        "",
        "| 检查 | 状态 | 值 | 说明 |",
        "|---|---|---|---|",
    ]
    for check in audit.get("checks") or []:
        lines.append(f"| {check['name']} | {check['status']} | {check['value']} | {check['detail']} |")
    lines += [
        "",
        "## 事件构成",
        "",
        "| kind | 数量 |",
        "|---|---|",
    ]
    for kind, count in sorted((events.get("by_kind") or {}).items(), key=lambda pair: -pair[1]):
        lines.append(f"| {kind} | {count} |")
    lines.append("")
    return "\n".join(lines)
