"""Event-driven replay: 事件 → 判定 → 成交 → 后续 1/5/20 日.

Why this module exists
----------------------
The paper trader answers "if I had followed every signal, what would the book
have done?". This module answers the *audit* question: show every step of the
chain, with the exact clock that was allowed to be used at each step, so a
reader can challenge a single decision instead of trusting an aggregate.

Hard rules (also stated in ``docs/ASSUMPTIONS.md`` and in the HTML banner):

* **No look-ahead.** A decision may only consume information whose
  ``available_at`` is at or before the decision instant. The fill must happen
  strictly *after* the public moment. Every accepted fill is re-checked before
  it enters the book (``lookahead_rejected`` would count violations, and it must
  stay ``0``).
* **Date-quality timestamps are end-of-day.** The database currently stores
  ``available_at`` with day precision (``timestamp_quality='date'``). Treating a
  date as "known at 00:00" would allow a same-session fill that no trader could
  have made, so a date is expanded to 23:59:59 UTC of that day. The first usable
  bar is therefore the *next* session. A minute-quality timestamp
  (``timestamp_quality='datetime'``) can fill inside the same session.
* **Intraday branch.** When the public moment is inside the last
  ``intraday_days`` days and Yahoo 1-minute bars are reachable, the fill is the
  open of the first 1-minute bar strictly after the public moment. Otherwise the
  fill is the open of the first trading session strictly after the public date
  (the daily branch).
* **Costs** are applied as ``costs_bps`` *per side* (matching
  ``paper.COST_BPS``), charged once on entry and once on exit; the HTML and the
  report therefore speak of "单边 bps". Each tier is re-marked independently
  from the same fills, which makes the cost sensitivity exactly monotone.
* **Long only by default**, matching the paper trader. ``direction = -1``
  (recall cluster) is recorded as ``SKIP / short_not_supported``; borrow fees,
  locate availability and merger squeeze-outs are not modelled. Passing
  ``allow_short=True`` is available for research but is flagged as unmodelled.

Data limits that the free feed cannot remove (banner on the page):

* Yahoo's ``range=7d&interval=1m`` only covers roughly the last seven calendar
  days, so older events can only be replayed on daily bars;
* there is no bid/ask quote, so the fill is an *assumed* price at the bar open
  plus the bps cost, not a real execution;
* there is no securities-lending/borrow data, which is why the book is long only.

Public API
----------
``build_replay(db, start, end, capital=100000, costs_bps=(10,25,50),
intraday_days=7)`` returns the complete payload (also written to
``out/replay/replay.json`` + ``out/replay/index.html``). The payload keys are
documented in ``docs/SCHEMA.md`` §11; extra keys are research detail, never a
replacement for the contracted ones.
"""

from __future__ import annotations

import bisect
import html as _html
import json
import math
import os
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote

from .config import CACHE_DIR, OUT_DIR, ROOT
from .db import DB
from .http import BudgetExceeded, Fetcher
from .prices import CHART_URL, PriceSeries, fetch_ticker_rows, load_series
from .util import (
    ensure_dir,
    iso,
    parse_date,
    sha1,
    summarize,
    t_stat,
    utc_now_iso,
    write_json,
    write_text,
)

ENGINE = "replay_v1"
SCHEMA_VERSION = "replay.v1"
ASSUMPTIONS_URL = "docs/ASSUMPTIONS.md"
DISCLAIMER_ZH = (
    "回放为研究口径，非投资建议；仅做多、固定持有 20 个交易日、"
    "成本按 bps 近似，未建模冲击成本、借券费、停牌/涨跌停与并购逼平。"
)

DEFAULT_COSTS_BPS: tuple[float, ...] = (10.0, 25.0, 50.0)
HORIZONS: tuple[int, ...] = (1, 5, 20)
INTRADAY_RANGE = "7d"
INTRADAY_INTERVAL = "1m"

#: Only observed public timestamps may enter the replay. Estimated, unknown and
#: missing timestamps remain available for descriptive industry analysis.
QUALITY_ALLOWED = ("datetime", "date")
QUALITY_ZH = {
    "datetime": "精确时间戳",
    "date": "仅日期（按当日收盘后可用）",
    "estimated": "估算时间（不进回放）",
    "unknown": "未知（不进回放）",
}

KIND_ZH = {
    "device_novel_code": "首次出现产品码",
    "device_new_track": "首次进入赛道",
    "drug_approval": "药品获批",
    "trial_start": "III 期试验启动",
    "recall_cluster": "召回聚集",
    "510k": "510(k) 清关",
    "pma": "PMA 批准",
    "device_recall": "器械召回",
    "trial": "临床试验",
    "drug_approval_raw": "药品批准",
    "nmpa_registration": "NMPA 注册",
    "8k_catalyst": "8-K 催化剂",
}

INTRADAY_STATUS_ZH = {
    "ok": "可用（最近约 7 天）",
    "partial": "部分标的可用",
    "unavailable": "不可用（已降级日线）",
    "not_requested": "未触发（窗口内无需 1 分钟价格）",
}

SKIP_REASON_ZH = {
    "no_ticker": "无股票代码",
    "short_not_supported": "做空不建模（本回放仅做多）",
    "not_yet_public": "回放时点尚未公开（防前视）",
    "no_price": "没有该标的的日线价格（优雅降级）",
    "no_future_price": "公开日之后没有可用价格",
    "no_future_bar": "公开日之后的交易日尚未开盘",
    "no_exit_price": "成交后没有收盘价可用于平仓",
    "no_calendar": "没有可用的交易日历",
    "no_calendar_bar": "交易日历缺少成交日之后的日期",
    "already_open": "同标的仍有未平仓仓位（不叠加）",
    "no_capacity": "并发仓位已满（上限 5 笔）",
    "low_score": "信号分数低于阈值",
    "lookahead_rejected": "成交时点早于公开时点（已拒绝）",
    "low_timestamp_quality": "时间戳质量不足（已过滤）",
}

_COST_KEY_RE = re.compile(r"^(\d+(?:\.\d+)?)$")


# --------------------------------------------------------------------------- helpers
def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def _round(value: Any, digits: int = 6) -> float | None:
    number = _as_float(value)
    return None if number is None else round(number, digits)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _mean(values: Sequence[float]) -> float | None:
    return (sum(values) / len(values)) if values else None


def _table_columns(db: Any, table: str) -> set[str]:
    try:
        rows = db.query(f"PRAGMA table_info({table})")
    except Exception:  # pragma: no cover - defensive against exotic DB shims
        return set()
    return {str(row.get("name") or "") for row in rows}


def _payload_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _direction(value: Any) -> int:
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        number = 0
    return -1 if number < 0 else 1


def _quality(value: Any) -> str:
    raw = str(value or "").strip().lower()
    return raw if raw in ("datetime", "date", "estimated", "unknown") else "unknown"


# --------------------------------------------------------------------------- time
def _now_utc(value: Any = None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return moment.astimezone(timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    text = str(value).strip().replace("Z", "+00:00")
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"cannot parse replay 'now': {value!r}") from exc
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _end_of_day(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 23, 59, 59, tzinfo=timezone.utc)


_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_moment(value: Any) -> tuple[datetime | None, bool]:
    """Return ``(moment_utc, has_time_precision)`` for date/datetime inputs.

    Date-only values are expanded to the end of that UTC day: a day-precision
    public record is only safely knowable after the day is over.
    """
    if value is None:
        return None, False
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return moment.astimezone(timezone.utc), True
    if isinstance(value, date):
        return _end_of_day(value), False
    text = str(value).strip()
    if not text:
        return None, False
    if _ISO_DATE_RE.match(text):
        day = parse_date(text)
        return (_end_of_day(day), False) if day else (None, False)
    candidate = text.replace("Z", "+00:00").replace("z", "+00:00")
    try:
        moment = datetime.fromisoformat(candidate)
    except ValueError:
        day = parse_date(text)
        return (_end_of_day(day), False) if day else (None, False)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc), True


def _resolve_available_at(row: Mapping[str, Any]) -> tuple[datetime | None, str]:
    """Resolve the instant this signal may first be acted on.

    Priority: ``events.available_at`` → ``events.published_at`` → payload JSON
    keys. There is deliberately no ``event_date`` fallback: a decision date is
    not proof of when the record became public. A day-precision value is expanded
    to the end of its day; estimated/unknown quality is returned as ``unknown``
    so every caller excludes it from trading (SCHEMA §9).
    """
    raw: Any = None
    for key in ("available_at", "published_at"):
        value = row.get(key)
        if value:
            raw = value
            break
    if raw is None:
        payload = _payload_dict(row.get("payload"))
        raw = payload.get("available_at") or payload.get("published_at")
    quality_raw = str(row.get("timestamp_quality") or "").strip().lower()
    moment, precise = _parse_moment(raw)
    if moment is None:
        return None, "unknown"
    else:
        if quality_raw in ("datetime", "date", "estimated", "unknown"):
            quality = quality_raw
        else:
            # Older DBs without the column: a real timestamp is datetime,
            # otherwise be honest and call it estimated.
            quality = "datetime" if precise else "estimated"
    if quality not in ("datetime", "date"):
        return moment, "unknown"
    if quality != "datetime" or not precise:
        moment = _end_of_day(moment.date())
        if quality == "datetime":
            quality = "date"
    return moment, quality


# --------------------------------------------------------------------------- US Eastern
try:  # pragma: no cover - exercised through the fallback in offline CI
    from zoneinfo import ZoneInfo

    _EASTERN = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover - Windows without tzdata
    _EASTERN = None


def _nth_sunday(year: int, month: int, n: int) -> int:
    first = date(year, month, 1)
    first_sunday = 1 + (6 - first.weekday()) % 7
    return first_sunday + 7 * (n - 1)


def _et_offset_hours(moment: datetime) -> int:
    """UTC offset (hours) of US Eastern at ``moment`` with a stdlib DST rule."""
    utc = moment.astimezone(timezone.utc)
    year = utc.year
    start = datetime(year, 3, _nth_sunday(year, 3, 2), 7, 0, tzinfo=timezone.utc)
    end = datetime(year, 11, _nth_sunday(year, 11, 1), 6, 0, tzinfo=timezone.utc)
    return -4 if start <= utc < end else -5


def _to_iso_et(moment: datetime) -> str:
    """ISO-8601 with the US/Eastern offset (``2026-10-29T09:30:00-04:00``)."""
    utc = moment.astimezone(timezone.utc)
    if _EASTERN is not None:  # pragma: no cover - depends on the host tzdata
        local = utc.astimezone(_EASTERN)
        return local.replace(microsecond=0).isoformat()
    offset = _et_offset_hours(utc)
    local = utc + timedelta(hours=offset)
    sign = "+" if offset >= 0 else "-"
    return f"{local:%Y-%m-%dT%H:%M:%S}{sign}{abs(offset):02d}:00"


def _market_open_utc(day: date) -> datetime:
    """09:30 US/Eastern on ``day`` expressed in UTC (handles DST)."""
    guess = datetime(day.year, day.month, day.day, 13, 30, tzinfo=timezone.utc)
    offset = _et_offset_hours(guess)
    local = datetime(day.year, day.month, day.day, 9, 30, tzinfo=timezone(timedelta(hours=offset)))
    return local.astimezone(timezone.utc)


def _iso_utc(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# --------------------------------------------------------------------------- intraday
def parse_intraday_chart(payload: Any, ticker: str) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Parse a Yahoo ``range=7d&interval=1m`` payload into bar dicts.

    Returns ``(bars, error)``. Bars are ``{time, datetime, open}`` with
    ``datetime`` an aware UTC instant, sorted ascending.
    """
    result = None
    if isinstance(payload, Mapping):
        chart = payload.get("chart")
        if isinstance(chart, Mapping):
            results = chart.get("result")
            if isinstance(results, list) and results:
                result = results[0]
    if not isinstance(result, Mapping):
        return None, "no_chart_result"
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    quote_rows = (indicators.get("quote") or [{}])[0] or {}
    opens = quote_rows.get("open") or []
    bars: list[dict[str, Any]] = []
    for stamp, open_price in zip(timestamps, opens):
        price = _as_float(open_price)
        if price is None or price <= 0:
            continue
        try:
            moment = datetime.fromtimestamp(int(stamp), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            continue
        bars.append({"time": int(stamp), "datetime": moment, "open": float(price)})
    if not bars:
        return None, "no_bars"
    bars.sort(key=lambda item: item["time"])
    return bars, None


def fetch_intraday(fetcher: Any, ticker: str, range_: str = INTRADAY_RANGE) -> list[dict[str, Any]]:
    """One polite Yahoo request for the last ~7 days of 1-minute bars."""
    symbol = str(ticker).strip().upper()
    payload = fetcher.get_json(
        CHART_URL.format(ticker=quote(symbol, safe="")),
        params={"range": range_, "interval": INTRADAY_INTERVAL, "includePrePost": "false"},
    )
    return parse_intraday_chart(payload, symbol)


# --------------------------------------------------------------------------- fetcher
class _BudgetedFetcher:
    """Hard request budget shared by intraday and daily fallback requests."""

    def __init__(self, inner: Any, max_requests: int) -> None:
        self.inner = inner
        self.max_requests = max(0, int(max_requests))
        self.used = 0

    def get_json(self, url: str, params: Any = None, **kwargs: Any) -> Any:
        if self.used >= self.max_requests:
            raise BudgetExceeded(f"replay request budget {self.max_requests} exhausted")
        self.used += 1
        return self.inner.get_json(url, params=params, **kwargs)

    def __getattr__(self, name: str) -> Any:  # pragma: no cover - passthrough
        return getattr(self.inner, name)


# --------------------------------------------------------------------------- price book
class _PriceBook:
    """Lazy daily + intraday price access with DB-first semantics."""

    def __init__(
        self,
        db: Any,
        fetcher: Any,
        *,
        offline: bool,
        now: datetime,
        daily_years: int,
        budget_max: int,
    ) -> None:
        self.db = db
        self.fetcher = fetcher
        self.offline = bool(offline)
        self.now = now
        self.daily_years = max(1, int(daily_years))
        self.budget_max = int(budget_max)
        self._series: dict[str, PriceSeries | None] = {}
        self._intraday: dict[str, list[dict[str, Any]] | None] = {}
        self._intraday_error: dict[str, str] = {}
        self._daily_source: dict[str, str] = {}
        self._daily_error: dict[str, str] = {}

    # ------------------------------------------------------------------ stats
    @property
    def budget_used(self) -> int:
        if isinstance(self.fetcher, _BudgetedFetcher):
            return int(self.fetcher.used)
        return 0

    def request_stats(self) -> dict[str, Any]:
        inner = getattr(self.fetcher, "stats", None) or {}
        if isinstance(self.fetcher, _BudgetedFetcher):
            used = int(self.fetcher.used)
        else:
            used = int(inner.get("requests", 0) or 0)
        return {
            "requests": int(inner.get("requests", 0) or 0),
            "cache_hits": int(inner.get("cache_hits", 0) or 0),
            "budget_used": used,
            "budget_max": self.budget_max,
            "mode": "offline" if self.fetcher is None else "online",
        }

    # ----------------------------------------------------------------- series
    def series(self, ticker: str) -> PriceSeries | None:
        symbol = str(ticker).strip().upper()
        if symbol in self._series:
            return self._series[symbol]
        series = None
        error = None
        try:
            cached = load_series(self.db, symbol)
        except Exception as exc:
            cached, error = None, f"db_error: {exc}"
        if cached is not None:
            series = cached
            self._daily_source[symbol] = "db_cache"
        elif self.fetcher is not None:
            try:
                rows = fetch_ticker_rows(self.fetcher, symbol, years=self.daily_years)
                if rows:
                    series = PriceSeries(symbol, rows)
                    self._daily_source[symbol] = "fetch"
                else:
                    error = "no_rows"
            except BudgetExceeded as exc:
                error = f"budget_exceeded: {exc}"
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
        self._series[symbol] = series
        if error:
            self._daily_error[symbol] = error
        return series

    def daily_status(self, tickers: Iterable[str]) -> dict[str, Any]:
        return {
            "requested": sorted({str(t).strip().upper() for t in tickers if t}),
            "sources": dict(self._daily_source),
            "errors": dict(self._daily_error),
            "mode": "offline" if self.fetcher is None else "online",
        }

    # --------------------------------------------------------------- intraday
    def intraday(self, ticker: str) -> tuple[list[dict[str, Any]] | None, str | None]:
        symbol = str(ticker).strip().upper()
        if symbol in self._intraday:
            return self._intraday[symbol], self._intraday_error.get(symbol)
        if self.fetcher is None:
            self._intraday[symbol] = None
            self._intraday_error[symbol] = "offline_no_fetcher"
            return None, self._intraday_error[symbol]
        try:
            bars = fetch_intraday(self.fetcher, symbol)
            self._intraday[symbol] = bars
            return bars, None
        except BudgetExceeded as exc:
            self._intraday[symbol] = None
            self._intraday_error[symbol] = f"budget_exceeded: {exc}"
        except Exception as exc:
            self._intraday[symbol] = None
            self._intraday_error[symbol] = f"{type(exc).__name__}: {exc}"
        return None, self._intraday_error[symbol]

    def intraday_errors(self) -> dict[str, str]:
        return dict(self._intraday_error)

    # --------------------------------------------------------------- calendar
    def calendar(self, tickers: Sequence[str]) -> list[str]:
        spy = self.series("SPY")
        if spy is not None and spy.dates:
            return list(spy.dates)
        union: set[str] = set()
        for ticker in tickers:
            series = self.series(ticker)
            if series is not None:
                union.update(series.dates)
        return sorted(union)


# --------------------------------------------------------------------------- loading
def _load_signal_rows(db: Any) -> list[dict[str, Any]]:
    """Join ``signals`` to ``events`` so the replay can see ``available_at``."""
    event_columns = _table_columns(db, "events")
    select = [
        "s.signal_id",
        "s.event_id",
        "s.ticker",
        "s.signal_date",
        "s.kind",
        "s.direction",
        "s.score",
        "s.track_id",
        "s.reason_zh",
        "s.created_at",
        "e.kind AS event_kind",
        "e.source AS event_source",
        "e.company_key AS event_company",
        "e.event_date",
        "e.title",
        "e.summary",
        "e.url",
        "e.payload",
        "e.as_of",
    ]
    for column in ("available_at", "published_at", "first_seen_at", "timestamp_quality"):
        select.append(f"e.{column}" if column in event_columns else f"NULL AS {column}")
    sql = "SELECT " + ", ".join(select) + " FROM signals s LEFT JOIN events e ON e.event_id = s.event_id"
    rows = db.query(sql)
    for row in rows:
        row["_ticker"] = str(row.get("ticker") or "").strip().upper()
        row["_signal_day"] = parse_date(row.get("signal_date"))
    return rows


DEVICE_ACTIVITY_KINDS = ("510k", "pma")
EVENT_MODE_KINDS: tuple[str, ...] = (
    "device_novel_code",
    "device_new_track",
    "drug_approval",
    "trial_start",
    "recall_cluster",
    "8k_catalyst",
)
DEFAULT_EVENT_MAX_STEPS = 400
DEFAULT_PER_KIND_LIMIT = 150
DEFAULT_COMPANY_CAP = 2
DEFAULT_GLOBAL_COMPANY_CAP = 3

#: Words that look like tickers in an 8-K headline but are not symbols.
_TICKER_STOPWORDS = frozenset(
    """
    INC LLC LTD PLC CORP CO COMPANY THE AND FOR NEW CEO CFO FDA SEC USA US
    GROUP HOLDINGS MEDICAL PHARMA PHARMACEUTICAL PHARMACEUTICALS THERAPEUTICS
    BIOSCIENCES BIOTECH TECHNOLOGIES TECHNOLOGY SYSTEMS SOLUTIONS HEALTH CARE
    LABS LABORATORIES TRUST FUND ETF AG SA NV AB SE KG LP CLASS COMMON STOCK
    SHARE SHARES WARRANT WARRANTS MEMBERSHIP INTERESTS PARTNERS PARTNERSHIP
    LTD HOLDING INTERNATIONAL INDUSTRIES PRODUCTS SERVICES RESEARCH CLINICAL
    TRIAL TRIALS DATA UPDATE ANNOUNCES ANNOUNCED RECEIVES RECEIVED REPORTS
    FDA APPROVAL APPROVED MEETING RESULTS RESULT STUDY PHASE PRIMARY ENDPOINT
    COMPLETE RESPONSE LETTER REVIEW PRIORITY ORPHAN BREAKTHROUGH TRACK FAST
    """.split()
)
_CATALYST_POSITIVE = (
    "fda approval",
    "approval",
    "approved",
    "clearance",
    "cleared",
    "met the primary",
    "met primary",
    "positive topline",
    "positive results",
    "positive data",
    "breakthrough",
    "fast track",
    "priority review",
    "orphan drug",
    "orphan designation",
    "granted",
    "license agreement",
    "licensing",
    "partnership",
    "collaboration",
    "acquisition",
    "agreement",
)
_CATALYST_NEGATIVE = (
    "did not meet",
    "did not achieve",
    "failed to meet",
    "failed",
    "missed",
    "complete response letter",
    "crl",
    "refus",
    "reject",
    "terminated",
    "discontinued",
    "clinical hold",
    "halt",
    "safety",
    "adverse",
    "warning letter",
    "recall",
    "withdraw",
)
_TICKER_TOKEN_RE = re.compile(r"\b([A-Z]{1,5}(?:\.[A-Z]{1,2})?)\b")


def _event_select_columns(db: Any) -> str:
    """Column list for an event row (gracefully handles pre-migration DBs)."""
    event_columns = _table_columns(db, "events")
    columns = [
        "event_id",
        "source",
        "kind",
        "event_date",
        "as_of",
        "company_key",
        "track_id",
        "product_code",
        "title",
        "summary",
        "url",
        "payload",
    ]
    for column in ("available_at", "published_at", "first_seen_at", "timestamp_quality"):
        columns.append(column if column in event_columns else f"NULL AS {column}")
    return ", ".join(columns)


def _available_sql(db: Any) -> str:
    """SQL expression for an observed public instant, never the decision date."""
    event_columns = _table_columns(db, "events")
    parts = [
        f"NULLIF({column}, '')"
        for column in ("available_at", "published_at")
        if column in event_columns
    ]
    return "COALESCE(" + ", ".join(parts) + ")" if parts else "NULL"


def _event_price_universe(db: Any) -> tuple[dict[str, str], set[str]]:
    """``company_key → ticker`` mapping plus the tickers that have price bars.

    Only tickers that already exist in ``prices`` are eligible: a long-history
    replay must not queue 400 steps that will all be skipped for missing data.
    """
    company_tickers: dict[str, str] = {}
    try:
        for row in db.query("SELECT key, ticker FROM companies"):
            ticker = str(row.get("ticker") or "").strip().upper()
            if row.get("key") and ticker:
                company_tickers[str(row["key"])] = ticker
    except Exception:  # pragma: no cover - a DB without companies still works
        company_tickers = {}
    try:
        price_tickers = {
            str(row.get("ticker") or "").strip().upper()
            for row in db.query("SELECT DISTINCT ticker FROM prices WHERE ticker IS NOT NULL")
        }
    except Exception:  # pragma: no cover
        price_tickers = set()
    price_tickers.discard("")
    return company_tickers, price_tickers


def _event_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return _payload_dict(row.get("payload"))


def _event_candidate(
    event: Mapping[str, Any],
    *,
    ticker: str,
    signal_kind: str,
    direction: int,
    score: float,
    reason: str,
    avail_day: date,
) -> dict[str, Any]:
    """Build a signal-shaped row exactly like ``_load_signal_rows`` output."""
    event_id = str(event.get("event_id") or "")
    signal_day = avail_day + timedelta(days=1)
    return {
        "signal_id": f"evt-{sha1(f'{event_id}|{signal_kind}')[:12]}",
        "event_id": event_id,
        "ticker": ticker,
        "signal_date": signal_day.isoformat(),
        "kind": signal_kind,
        "direction": direction,
        "score": score,
        "track_id": event.get("track_id"),
        "reason_zh": reason,
        "created_at": utc_now_iso(),
        "event_kind": event.get("kind"),
        "event_source": event.get("source"),
        "event_company": event.get("company_key"),
        "event_date": event.get("event_date"),
        "title": event.get("title"),
        "summary": event.get("summary"),
        "url": event.get("url"),
        "payload": event.get("payload"),
        "as_of": event.get("as_of"),
        "available_at": event.get("available_at"),
        "published_at": event.get("published_at"),
        "first_seen_at": event.get("first_seen_at"),
        "timestamp_quality": event.get("timestamp_quality"),
        "_ticker": ticker,
        "_signal_day": signal_day,
        "_avail_day": avail_day,
        "_company": str(event.get("company_key") or ""),
    }


def _event_candidate_from_row(
    event: Mapping[str, Any],
    *,
    company_tickers: Mapping[str, str],
    price_tickers: set[str],
    start_day: date,
    end_day: date,
    signal_kind: str,
    direction: int,
    score: float,
    reason: str,
    ticker: str | None = None,
) -> dict[str, Any] | None:
    """Apply the shared point-in-time / tradeability gate to one event row."""
    resolved = (ticker or company_tickers.get(str(event.get("company_key") or "")) or "").strip().upper()
    if not resolved or resolved not in price_tickers:
        return None
    moment, quality = _resolve_available_at(event)
    if moment is None or quality == "unknown":
        return None
    day = moment.date()
    if day < start_day or day > end_day:
        return None
    return _event_candidate(
        event,
        ticker=resolved,
        signal_kind=signal_kind,
        direction=direction,
        score=score,
        reason=reason,
        avail_day=day,
    )


def _title_ticker(title: Any, price_tickers: set[str]) -> str:
    """Heuristic: first parenthesised / uppercase token that is a real ticker.

    The 8-K corpus does not carry a resolved CIK→ticker map, so this is the only
    free way to trade those catalysts. It is intentionally conservative: an
    unknown headline simply produces no candidate (surfaced in ASSUMPTIONS).
    """
    for token in _TICKER_TOKEN_RE.findall(str(title or "").upper()):
        if len(token) < 2 or token in _TICKER_STOPWORDS:
            continue
        if token in price_tickers:
            return token
    return ""


def _catalyst_direction(event: Mapping[str, Any]) -> tuple[int, str] | None:
    """Keyword-based direction for an 8-K catalyst headline (no LLM, no network)."""
    payload = _event_payload(event)
    buckets = payload.get("buckets") or []
    if isinstance(buckets, str):
        buckets = [buckets]
    haystack = " ".join(
        [
            str(payload.get("category") or ""),
            " ".join(str(item) for item in buckets),
            str(event.get("title") or ""),
        ]
    ).lower()
    negative = [word for word in _CATALYST_NEGATIVE if word in haystack]
    positive = [word for word in _CATALYST_POSITIVE if word in haystack]
    if negative and positive:
        return None  # ambiguous headline -> never trade a coin flip
    if negative:
        return -1, "负面"
    if positive:
        return 1, "正面"
    return None


def _first_occurrence_candidates(
    db: Any,
    *,
    group_column: str,
    signal_kind: str,
    direction: int,
    score: float,
    company_tickers: Mapping[str, str],
    price_tickers: set[str],
    start_day: date,
    end_day: date,
    skip_event_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """First-ever ``(company, group_column)`` pair inside the replay window.

    ``MIN(avail)`` is computed over the company's whole history up to ``end``, so
    an event only qualifies as "first" when nothing earlier existed. Only the
    rows whose first occurrence falls inside the window become candidates.
    """
    select = _event_select_columns(db)
    avail = _available_sql(db)
    sql = f"""
    WITH base AS (
      SELECT {select}, {avail} AS avail
      FROM events
      WHERE kind IN ('510k', 'pma')
        AND company_key IS NOT NULL AND company_key != ''
        AND {group_column} IS NOT NULL AND {group_column} != ''
        AND event_date <= ?
    ), firsts AS (
      SELECT company_key, {group_column} AS grp, MIN(avail) AS first_avail
      FROM base GROUP BY company_key, grp
    )
    SELECT b.* FROM base b
    JOIN firsts f ON b.company_key = f.company_key
      AND b.{group_column} = f.grp AND b.avail = f.first_avail
    """
    rows = db.query(sql, (end_day.isoformat(),))
    rows.sort(key=lambda row: (str(row.get("avail") or ""), str(row.get("event_id") or "")))
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        event_id = str(row.get("event_id") or "")
        if skip_event_ids and event_id in skip_event_ids:
            continue
        group_value = str(row.get(group_column) or "")
        key = (str(row.get("company_key") or ""), group_value, str(row.get("avail") or "")[:10])
        if key in seen:
            continue  # tie on the first available date: keep one representative
        seen.add(key)
        if signal_kind == "device_novel_code":
            reason = f"首次出现产品码 {group_value}（events 自动生成）"
        else:
            reason = f"首次进入赛道 {group_value}（events 自动生成）"
        candidate = _event_candidate_from_row(
            row,
            company_tickers=company_tickers,
            price_tickers=price_tickers,
            start_day=start_day,
            end_day=end_day,
            signal_kind=signal_kind,
            direction=direction,
            score=score,
            reason=reason,
        )
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def _event_rule_drug_approvals(
    db: Any,
    *,
    company_tickers: Mapping[str, str],
    price_tickers: set[str],
    start_day: date,
    end_day: date,
) -> list[dict[str, Any]]:
    select = _event_select_columns(db)
    avail = _available_sql(db)
    rows = db.query(
        f"SELECT {select}, {avail} AS avail FROM events"
        " WHERE kind = 'drug_approval' AND company_key IS NOT NULL AND company_key != ''"
        " AND event_date <= ? ORDER BY avail, event_id",
        (end_day.isoformat(),),
    )
    candidates: list[dict[str, Any]] = []
    for row in rows:
        candidate = _event_candidate_from_row(
            row,
            company_tickers=company_tickers,
            price_tickers=price_tickers,
            start_day=start_day,
            end_day=end_day,
            signal_kind="drug_approval",
            direction=1,
            score=0.7,
            reason="药品获批（events 自动生成）",
        )
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def _event_rule_trial_start(
    db: Any,
    *,
    company_tickers: Mapping[str, str],
    price_tickers: set[str],
    start_day: date,
    end_day: date,
) -> list[dict[str, Any]]:
    select = _event_select_columns(db)
    avail = _available_sql(db)
    rows = db.query(
        f"SELECT {select}, {avail} AS avail FROM events"
        " WHERE kind = 'trial' AND company_key IS NOT NULL AND company_key != ''"
        " AND payload LIKE '%PHASE3%' AND event_date <= ? ORDER BY avail, event_id",
        (end_day.isoformat(),),
    )
    candidates: list[dict[str, Any]] = []
    for row in rows:
        phases = _event_payload(row).get("phase") or []
        if isinstance(phases, str):
            phases = [phases]
        if not any(str(phase).upper() == "PHASE3" for phase in phases):
            continue
        candidate = _event_candidate_from_row(
            row,
            company_tickers=company_tickers,
            price_tickers=price_tickers,
            start_day=start_day,
            end_day=end_day,
            signal_kind="trial_start",
            direction=1,
            score=0.5,
            reason="III 期试验启动（events 自动生成）",
        )
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def _event_rule_recall_cluster(
    db: Any,
    *,
    company_tickers: Mapping[str, str],
    price_tickers: set[str],
    start_day: date,
    end_day: date,
) -> list[dict[str, Any]]:
    """Second (and later, once per 90-day window) recall per company.

    The 90-day count only includes recalls that came *before* the current one, so
    the cluster is knowable at the decision moment.
    """
    select = _event_select_columns(db)
    avail = _available_sql(db)
    rows = db.query(
        f"SELECT {select}, {avail} AS avail FROM events"
        " WHERE kind = 'device_recall' AND company_key IS NOT NULL AND company_key != ''"
        " AND event_date <= ? ORDER BY company_key, avail, event_id",
        (end_day.isoformat(),),
    )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("company_key") or "")].append(row)
    candidates: list[dict[str, Any]] = []
    for company, events in grouped.items():
        ordered: list[tuple[date, dict[str, Any]]] = []
        for event in events:
            moment, quality = _resolve_available_at(event)
            if moment is None or quality == "unknown":
                continue
            ordered.append((moment.date(), event))
        ordered.sort(key=lambda pair: (pair[0], str(pair[1].get("event_id") or "")))
        seen_days: list[date] = []
        emitted: date | None = None
        for day, event in ordered:
            seen_days.append(day)
            recent = sum(1 for value in seen_days if (day - value).days <= 90)
            if recent < 2:
                continue
            if emitted is not None and (day - emitted).days < 90:
                continue
            emitted = day
            candidate = _event_candidate_from_row(
                event,
                company_tickers=company_tickers,
                price_tickers=price_tickers,
                start_day=start_day,
                end_day=end_day,
                signal_kind="recall_cluster",
                direction=-1,
                score=0.7,
                reason=f"90 天内 {recent} 起召回（events 自动生成）",
            )
            if candidate is not None:
                candidates.append(candidate)
    return candidates


def _event_rule_8k_catalyst(
    db: Any,
    *,
    company_tickers: Mapping[str, str],
    price_tickers: set[str],
    start_day: date,
    end_day: date,
) -> list[dict[str, Any]]:
    select = _event_select_columns(db)
    avail = _available_sql(db)
    rows = db.query(
        f"SELECT {select}, {avail} AS avail FROM events"
        " WHERE kind = '8k_catalyst' AND event_date <= ? ORDER BY avail, event_id",
        (end_day.isoformat(),),
    )
    candidates: list[dict[str, Any]] = []
    for row in rows:
        payload = _event_payload(row)
        if payload.get("backfill"):
            # A backfilled alert was only discovered later; trading it at the
            # original event date is look-ahead, so it never enters the replay.
            continue
        direction_info = _catalyst_direction(row)
        if direction_info is None:
            continue
        direction, label = direction_info
        ticker = company_tickers.get(str(row.get("company_key") or ""), "")
        if not ticker:
            ticker = _title_ticker(row.get("title"), price_tickers)
        candidate = _event_candidate_from_row(
            row,
            ticker=ticker,
            company_tickers=company_tickers,
            price_tickers=price_tickers,
            start_day=start_day,
            end_day=end_day,
            signal_kind="8k_catalyst",
            direction=direction,
            score=0.6,
            reason=f"8-K 催化剂：{label}（events 自动生成）",
        )
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def _diverse_sample(
    candidates: Sequence[dict[str, Any]],
    limit: int | None,
    *,
    company_cap: int = DEFAULT_COMPANY_CAP,
) -> list[dict[str, Any]]:
    """Deterministic stratified pick that keeps kind × year × company diversity.

    Buckets are ``(kind, year)``; the sampler takes one item per bucket per round
    and limits each ``(kind, company, year)`` cell to ``company_cap`` picks in a
    first pass. A second chronological pass relaxes that cap only if the limit is
    still not reached (e.g. one company dominates a tiny year).
    """
    ordered = sorted(
        candidates,
        key=lambda item: (
            item.get("_avail_day") or date.min,
            str(item.get("kind") or ""),
            str(item.get("_company") or ""),
            str(item.get("event_id") or ""),
        ),
    )
    if not ordered:
        return []
    if limit is None or len(ordered) <= limit:
        return ordered
    if limit <= 0:
        return []
    buckets: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for item in ordered:
        day = item.get("_avail_day")
        year = day.year if isinstance(day, date) else 0
        buckets[(str(item.get("kind") or ""), year)].append(item)
    keys = sorted(buckets, key=lambda key: (key[1], key[0]))
    pointers = {key: 0 for key in keys}
    selected: list[dict[str, Any]] = []
    cell_counts: Counter[tuple[str, str, int]] = Counter()

    def take_round(cap: int | None) -> bool:
        progressed = False
        for key in keys:
            if len(selected) >= limit:
                return progressed
            bucket = buckets[key]
            index = pointers[key]
            while index < len(bucket):
                item = bucket[index]
                day = item.get("_avail_day")
                year = day.year if isinstance(day, date) else 0
                cell = (str(item.get("kind") or ""), str(item.get("_company") or ""), year)
                if cap is None or cell_counts[cell] < cap:
                    selected.append(item)
                    cell_counts[cell] += 1
                    pointers[key] = index + 1
                    progressed = True
                    break
                index += 1
            else:
                pointers[key] = len(bucket)
        return progressed

    while len(selected) < limit and take_round(company_cap):
        pass
    if len(selected) < limit:  # relax the company cap rather than underfilling
        taken = {id(item) for item in selected}
        for item in ordered:
            if len(selected) >= limit:
                break
            if id(item) not in taken:
                selected.append(item)
    return sorted(
        selected,
        key=lambda item: (
            item.get("_avail_day") or date.min,
            str(item.get("kind") or ""),
            str(item.get("_company") or ""),
            str(item.get("event_id") or ""),
        ),
    )


def _normalise_kind_limits(value: Any) -> dict[str, int]:
    """Accept ``150`` or ``{kind: limit}`` and return a complete per-kind map."""
    if isinstance(value, Mapping):
        limits = {}
        for kind in EVENT_MODE_KINDS:
            limits[kind] = max(0, int(value.get(kind, DEFAULT_PER_KIND_LIMIT)))
        return limits
    default = max(0, int(value if value is not None else DEFAULT_PER_KIND_LIMIT))
    return {kind: default for kind in EVENT_MODE_KINDS}


def _event_mode_rows(
    db: Any,
    start_day: date,
    end_day: date,
    *,
    per_kind_limit: Any = DEFAULT_PER_KIND_LIMIT,
    max_steps: int | None = DEFAULT_EVENT_MAX_STEPS,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build the multi-year replay candidate set directly from ``events``.

    This is a *replay-local* re-implementation of the signal rules (no import of
    ``analyze``): each rule is point-in-time by construction, and every candidate
    is filtered by ``available_at``-based window, timestamp quality and tradeable
    ticker before it can become a step. Per-kind limits plus a kind×year×company
    stratified sample keep the output at a few hundred steps even on a 312k-event
    corpus.
    """
    company_tickers, price_tickers = _event_price_universe(db)
    limits = _normalise_kind_limits(per_kind_limit)
    candidates_by_kind: dict[str, list[dict[str, Any]]] = {}
    novel = _first_occurrence_candidates(
        db,
        group_column="product_code",
        signal_kind="device_novel_code",
        direction=1,
        score=0.6,
        company_tickers=company_tickers,
        price_tickers=price_tickers,
        start_day=start_day,
        end_day=end_day,
    )
    candidates_by_kind["device_novel_code"] = novel
    candidates_by_kind["device_new_track"] = _first_occurrence_candidates(
        db,
        group_column="track_id",
        signal_kind="device_new_track",
        direction=1,
        score=0.55,
        company_tickers=company_tickers,
        price_tickers=price_tickers,
        start_day=start_day,
        end_day=end_day,
        skip_event_ids={str(item["event_id"]) for item in novel},
    )
    candidates_by_kind["drug_approval"] = _event_rule_drug_approvals(
        db,
        company_tickers=company_tickers,
        price_tickers=price_tickers,
        start_day=start_day,
        end_day=end_day,
    )
    candidates_by_kind["trial_start"] = _event_rule_trial_start(
        db,
        company_tickers=company_tickers,
        price_tickers=price_tickers,
        start_day=start_day,
        end_day=end_day,
    )
    candidates_by_kind["recall_cluster"] = _event_rule_recall_cluster(
        db,
        company_tickers=company_tickers,
        price_tickers=price_tickers,
        start_day=start_day,
        end_day=end_day,
    )
    candidates_by_kind["8k_catalyst"] = _event_rule_8k_catalyst(
        db,
        company_tickers=company_tickers,
        price_tickers=price_tickers,
        start_day=start_day,
        end_day=end_day,
    )

    stats: dict[str, Any] = {
        "candidate_counts": {},
        "sampled_counts": {},
        "per_kind_limit": limits,
        "max_steps": max_steps,
        "diversity": "kind×year 分层、每 (kind, company, year) 首轮至多 2 条；公司/类别/年份兼顾",
    }
    selected: list[dict[str, Any]] = []
    for kind in EVENT_MODE_KINDS:
        candidates = candidates_by_kind.get(kind, [])
        stats["candidate_counts"][kind] = len(candidates)
        sampled = _diverse_sample(candidates, limits.get(kind, DEFAULT_PER_KIND_LIMIT))
        stats["sampled_counts"][kind] = len(sampled)
        selected.extend(sampled)
    before_global = len(selected)
    selected = _diverse_sample(
        selected,
        max_steps,
        company_cap=DEFAULT_GLOBAL_COMPANY_CAP,
    )
    stats["total_candidates"] = sum(stats["candidate_counts"].values())
    stats["total_before_global_cap"] = before_global
    stats["total_steps"] = len(selected)
    stats["tradeable_tickers"] = len(price_tickers)
    stats["company_tickers"] = len(company_tickers)
    return selected, stats


def _auto_signal_rows(db: Any, start_day: date, end_day: date) -> list[dict[str, Any]]:
    """Backwards-compatible alias for the events-mode generator."""
    rows, _stats = _event_mode_rows(db, start_day, end_day)
    return rows


def _dedupe_rows(rows: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Keep the latest analysis run per (event, ticker, direction, kind, date).

    ``analyze`` is re-run often, so the same signal can be ingested more than
    once with a new ``signal_id``. Without this the replay would double every
    recall.
    """
    best: dict[tuple, dict[str, Any]] = {}
    duplicates = 0
    for row in rows:
        key = (
            row.get("event_id") or row.get("signal_id") or "",
            row.get("_ticker") or "",
            _direction(row.get("direction")),
            str(row.get("kind") or ""),
            iso(row.get("signal_date")),
        )
        current = best.get(key)
        if current is None:
            best[key] = dict(row)
            continue
        duplicates += 1
        left = (str(row.get("created_at") or ""), float(row.get("score") or 0.0), str(row.get("signal_id") or ""))
        right = (
            str(current.get("created_at") or ""),
            float(current.get("score") or 0.0),
            str(current.get("signal_id") or ""),
        )
        if left > right:
            best[key] = dict(row)
    ordered = sorted(
        best.values(),
        key=lambda item: (
            iso(item.get("signal_date")),
            item.get("_ticker") or "",
            str(item.get("signal_id") or ""),
        ),
    )
    return ordered, duplicates


def _company_names() -> dict[str, str]:
    """key → 中文名 for display (best effort, never fatal)."""
    names: dict[str, str] = {}
    try:
        from .config import load_companies

        for kind in ("device", "drug"):
            try:
                registry = load_companies(kind)
            except Exception:  # pragma: no cover - config problems must not break a replay
                continue
            for entry in registry.all():
                key = str(entry.get("key") or "")
                if key and entry.get("name_zh"):
                    names.setdefault(key, str(entry["name_zh"]))
    except Exception:  # pragma: no cover
        pass
    return names


# --------------------------------------------------------------------------- fill logic
def _intraday_eligible(moment: datetime, now: datetime, days: float) -> bool:
    if moment > now:
        return False
    return (now - moment) <= timedelta(days=max(0.0, float(days)))


def _first_intraday_fill(
    bars: Sequence[Mapping[str, Any]], available_at: datetime, now: datetime
) -> dict[str, Any] | None:
    """Open of the first 1-minute bar strictly after the public moment."""
    for bar in bars:
        moment = bar.get("datetime")
        price = _as_float(bar.get("open"))
        if not isinstance(moment, datetime) or price is None or price <= 0:
            continue
        if moment <= available_at or moment > now:
            continue
        return {
            "price": float(price),
            "date": moment.date().isoformat(),
            "time": moment,
            "source": "1m",
        }
    return None


def _daily_fill(
    series: PriceSeries, available_at: datetime, now: datetime
) -> tuple[dict[str, Any] | None, str | None]:
    """Open of the first session strictly after the public *date*."""
    start = bisect.bisect_right(series.dates, available_at.date().isoformat())
    for index in range(start, len(series.dates)):
        day = series.dates[index]
        price = _as_float(series.open(day))
        if price is None or price <= 0:
            continue
        day_obj = parse_date(day)
        if day_obj is None:
            continue
        open_moment = _market_open_utc(day_obj)
        if open_moment > now:
            return None, "no_future_bar"
        return {"price": float(price), "date": day, "time": open_moment, "source": "daily"}, None
    return None, "no_future_price"


def _gross_return(entry: float, exit_price: float, direction: int) -> float | None:
    if not entry or entry <= 0 or exit_price is None or exit_price <= 0:
        return None
    if direction >= 0:
        return exit_price / entry - 1.0
    return 1.0 - exit_price / entry


def _close_at_or_after(
    series: PriceSeries, calendar: Sequence[str], anchor: int, target: int
) -> tuple[int | None, float | None, str | None]:
    """Close at ``target``, else the nearest later close, else the data end."""
    last = len(calendar) - 1
    if target <= last:
        for index in range(target, last + 1):
            close = _as_float(series.close(calendar[index]))
            if close is not None and close > 0:
                reason = "time_exit" if index >= target else "end_of_data"
                return index, float(close), reason
    for index in range(last, anchor - 1, -1):
        close = _as_float(series.close(calendar[index]))
        if close is not None and close > 0:
            return index, float(close), "end_of_data"
    return None, None, None


# --------------------------------------------------------------------------- steps
def _event_label(kind: str, title: str, fallback: str) -> str:
    kind_zh = KIND_ZH.get(kind, kind or "事件")
    text = str(title or "").strip()
    if not text:
        text = str(fallback or "").strip()
    if len(text) > 90:
        text = text[:89] + "…"
    return f"{kind_zh}：{text}" if text else kind_zh


def _skip(step: dict[str, Any], reason: str) -> dict[str, Any]:
    step["decision"] = "SKIP"
    step["skip_reason"] = reason
    step["skip_reason_zh"] = SKIP_REASON_ZH.get(reason, reason)
    if not step.get("t"):
        step["t"] = step.get("available_at") or step.get("available_at_utc") or ""
    return step


def _base_step(row: Mapping[str, Any], names: Mapping[str, str]) -> dict[str, Any]:
    ticker = str(row.get("_ticker") or "")
    kind = str(row.get("kind") or row.get("event_kind") or "")
    company_key = str(row.get("event_company") or row.get("company_key") or "")
    return {
        "step_id": None,
        "ticker": ticker,
        "company_key": company_key,
        "company_zh": names.get(company_key, ""),
        "event_id": row.get("event_id") or "",
        "signal_id": row.get("signal_id") or "",
        "kind": kind,
        "kind_zh": KIND_ZH.get(kind, kind or "事件"),
        "track_id": row.get("track_id") or "",
        "source": row.get("event_source") or "",
        "signal_date": iso(row.get("signal_date")),
        "available_at": "",
        "available_at_utc": "",
        "timestamp_quality": "unknown",
        "score": _round(row.get("score"), 3),
        "direction": _direction(row.get("direction")),
        "decision": "SKIP",
        "skip_reason": None,
        "skip_reason_zh": None,
        "t": "",
        "fill_time": None,
        "fill_date": None,
        "fill_price": None,
        "price_source": None,
        "price_source_zh": None,
        "shares": None,
        "notional": None,
        "gross_return": None,
        "exit_date": None,
        "exit_price": None,
        "exit_reason": None,
        "holding_days": None,
        "outcome_1d": None,
        "outcome_5d": None,
        "outcome_20d": None,
        "net_by_cost": {},
        "pnl_by_cost": {},
        "intraday_fallback": None,
        "reference_only": False,
        "event_zh": _event_label(kind, str(row.get("title") or ""), str(row.get("reason_zh") or "")),
        "reason_zh": str(row.get("reason_zh") or ""),
        "title": str(row.get("title") or ""),
        "url": str(row.get("url") or ""),
        "_sort": None,
        "_anchor_idx": None,
        "_exit_idx": None,
    }


def _resolve_step(
    row: Mapping[str, Any],
    *,
    book: _PriceBook,
    calendar: Sequence[str],
    now: datetime,
    names: Mapping[str, str],
    intraday_days: float,
    allow_short: bool,
    capital: float,
    position_pct: float,
    hold_days: int,
    min_score: float,
) -> dict[str, Any] | None:
    """Resolve one candidate into a fully described timeline step.

    Returns ``None`` only for rows that must be filtered out entirely (unknown
    timestamp quality); everything else becomes a step, possibly a ``SKIP``.
    """
    step = _base_step(row, names)
    direction = int(step["direction"])
    step["side"] = "long" if direction > 0 else "short"

    available_at, quality = _resolve_available_at(row)
    if available_at is None or quality == "unknown":
        return None
    step["available_at"] = _to_iso_et(available_at)
    step["available_at_utc"] = _iso_utc(available_at)
    step["timestamp_quality"] = quality
    step["_sort"] = available_at

    if not step["ticker"]:
        return _skip(step, "no_ticker")
    # Shorts are excluded from the book, but we still resolve a *reference* fill
    # so the timeline can show the price the decision would have used (tagged
    # ``reference_only`` and never counted in any summary).
    forced_skip = "short_not_supported" if (direction < 0 and not allow_short) else None
    if available_at > now:
        return _skip(step, "not_yet_public")
    score = _as_float(row.get("score")) or 0.0
    if score < float(min_score):
        return _skip(step, "low_score")

    series = book.series(step["ticker"])
    if series is None:
        return _skip(step, "no_price")
    if not calendar:
        return _skip(step, "no_calendar")

    # ------------------------------------------------------------ price branch
    fill: dict[str, Any] | None = None
    intraday_error: str | None = None
    # Offline runs never *attempt* a 1-minute request, so they must not be
    # reported as fallbacks; the HTML explains the offline mode separately.
    if book.fetcher is not None and _intraday_eligible(available_at, now, intraday_days):
        bars, error = book.intraday(step["ticker"])
        if bars:
            fill = _first_intraday_fill(bars, available_at, now)
            if fill is None:
                intraday_error = "no_bar_after_public_time"
        else:
            intraday_error = error or "intraday_unavailable"
    if fill is None:
        fill, daily_reason = _daily_fill(series, available_at, now)
        if fill is None:
            return _skip(step, daily_reason or "no_future_price")
    if intraday_error:
        step["intraday_fallback"] = intraday_error
    step["price_source"] = fill["source"]
    step["price_source_zh"] = "1 分钟 bar 开盘" if fill["source"] == "1m" else "次日交易日开盘"
    step["fill_price"] = round(float(fill["price"]), 6)
    step["fill_date"] = fill["date"]
    step["fill_time"] = _to_iso_et(fill["time"])
    step["t"] = step["fill_time"]

    # Hard look-ahead guard: the fill must be strictly after the public moment.
    if fill["time"] <= available_at:
        return _skip(step, "lookahead_rejected")

    # --------------------------------------------------------------- outcomes
    anchor = bisect.bisect_left(calendar, fill["date"])
    if anchor >= len(calendar):
        return _skip(step, "no_calendar_bar")
    entry_price = float(fill["price"])
    direction_sign = 1 if direction > 0 else -1
    outcomes: dict[str, float | None] = {}
    for horizon in HORIZONS:
        target = anchor + horizon
        value = None
        if target < len(calendar):
            close = _as_float(series.close(calendar[target]))
            if close is not None and close > 0:
                value = _gross_return(entry_price, close, direction_sign)
        outcomes[horizon] = _round(value)
    step["outcome_1d"] = outcomes[1]
    step["outcome_5d"] = outcomes[5]
    step["outcome_20d"] = outcomes[20]
    step["_anchor_idx"] = anchor

    if forced_skip is not None:
        # Reference-only row: keep the decision explanation and the hypothetical
        # outcome, but never book a position, PnL or cost.
        step["reference_only"] = True
        return _skip(step, forced_skip)

    exit_index, exit_price, exit_reason = _close_at_or_after(
        series, calendar, anchor, anchor + int(hold_days)
    )
    if exit_index is None or exit_price is None:
        return _skip(step, "no_exit_price")

    gross_return = _gross_return(entry_price, exit_price, direction_sign)
    if gross_return is None:
        return _skip(step, "no_exit_price")

    score_for_size = _clamp(score if score > 0 else 0.5, 0.2, 1.0)
    notional = float(capital) * float(position_pct) * score_for_size
    shares = notional / entry_price if entry_price > 0 else 0.0

    step["decision"] = "BUY" if direction > 0 else "SHORT"
    step["notional"] = round(notional, 2)
    step["shares"] = round(shares, 6)
    step["gross_return"] = _round(gross_return)
    step["exit_date"] = calendar[exit_index]
    step["exit_price"] = round(exit_price, 6)
    step["exit_reason"] = exit_reason
    step["holding_days"] = int(exit_index - anchor)
    step["_exit_idx"] = exit_index
    return step


def _assign_capacity(steps: Sequence[dict[str, Any]], max_concurrent: int) -> None:
    """Reject entries that would break the one-per-ticker / N-concurrent limit.

    The check only uses the deterministic holding rule (``hold_days``) and the
    already booked entries, never a future price.
    """
    active: list[dict[str, Any]] = []
    for step in steps:
        if step.get("decision") not in ("BUY", "SHORT"):
            continue
        entry_index = step.get("_anchor_idx")
        exit_index = step.get("_exit_idx")
        if entry_index is None or exit_index is None:
            continue
        active = [item for item in active if item["exit_idx"] > entry_index]
        if any(item["ticker"] == step["ticker"] for item in active):
            _skip(step, "already_open")
        elif len(active) >= int(max_concurrent):
            _skip(step, "no_capacity")
        else:
            active.append(
                {"ticker": step["ticker"], "entry_idx": entry_index, "exit_idx": exit_index}
            )
        if step.get("decision") == "SKIP":
            _clear_planned_fill(step)


def _clear_planned_fill(step: dict[str, Any]) -> None:
    """A rejected entry keeps its reference price but leaves the book."""
    step["decision"] = "SKIP"
    step["shares"] = None
    step["notional"] = None
    step["gross_return"] = None
    step["exit_date"] = None
    step["exit_price"] = None
    step["exit_reason"] = None
    step["holding_days"] = None
    step["outcome_1d"] = None
    step["outcome_5d"] = None
    step["outcome_20d"] = None
    step["net_by_cost"] = {}
    step["pnl_by_cost"] = {}
    step["_anchor_idx"] = None
    step["_exit_idx"] = None


# --------------------------------------------------------------------------- aggregation
def cost_key(bps: Any) -> str:
    number = float(bps)
    return str(int(number)) if abs(number - int(number)) < 1e-9 else f"{number:g}"


def _summarize(trades: Sequence[Mapping[str, Any]], capital: float, bps: float) -> dict[str, Any]:
    if not trades:
        return {
            "cost_bps": float(bps),
            "trades": 0,
            "n_trades": 0,
            "total_return": None,
            "final_equity": None,
            "max_drawdown": None,
            "win_rate": None,
            "avg_trade_return": None,
            "total_pnl": None,
            "avg_holding_days": None,
            "mean_gross_return": None,
            "mean_outcome_1d": None,
            "mean_outcome_5d": None,
            "mean_outcome_20d": None,
            "start": None,
            "end": None,
            "equity_curve": [],
        }
    ordered = sorted(trades, key=lambda item: (str(item["exit_date"]), str(item["trade_id"])))
    returns = [float(item["ret"]) for item in ordered]
    pnl_total = sum(float(item["pnl"]) for item in ordered)
    by_day: dict[str, float] = defaultdict(float)
    for trade in ordered:
        by_day[str(trade["exit_date"])] += float(trade["pnl"])
    start_day = min(str(item["entry_date"]) for item in ordered)
    curve = [{"date": start_day, "equity": round(float(capital), 2)}]
    equity = float(capital)
    peak = float(capital)
    max_drawdown = 0.0
    for day in sorted(by_day):
        equity += by_day[day]
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity / peak - 1.0 if peak > 0 else 0.0)
        curve.append({"date": day, "equity": round(equity, 2)})
    outcomes = {h: [] for h in HORIZONS}
    for trade in ordered:
        for horizon in HORIZONS:
            value = trade.get(f"fwd_{horizon}d")
            if value is not None:
                outcomes[horizon].append(float(value))
    return {
        "cost_bps": float(bps),
        "trades": len(ordered),
        "n_trades": len(ordered),
        "total_return": _round(pnl_total / capital if capital else None),
        "final_equity": round(float(capital) + pnl_total, 2),
        "max_drawdown": _round(max_drawdown),
        "win_rate": _round(sum(1 for value in returns if value > 0) / len(returns)),
        "avg_trade_return": _round(_mean(returns)),
        "total_pnl": round(pnl_total, 2),
        "avg_holding_days": _round(_mean([float(item["holding_days"]) for item in ordered]), 2),
        "mean_gross_return": _round(_mean([float(item["gross_return"]) for item in ordered])),
        "mean_outcome_1d": _round(_mean(outcomes[1])),
        "mean_outcome_5d": _round(_mean(outcomes[5])),
        "mean_outcome_20d": _round(_mean(outcomes[20])),
        "start": start_day,
        "end": max(str(item["exit_date"]) for item in ordered),
        "equity_curve": curve,
    }


def _event_study(steps: Sequence[Mapping[str, Any]], cost_items: Sequence[tuple[str, float]]) -> dict[str, Any]:
    accepted = [step for step in steps if step.get("decision") in ("BUY", "SHORT")]
    result: dict[str, Any] = {"n_entries": len(accepted), "horizons": {}, "by_side": {}}
    for horizon in HORIZONS:
        key = str(horizon)
        values = [float(step[f"outcome_{horizon}d"]) for step in accepted if step.get(f"outcome_{horizon}d") is not None]
        stats = summarize(values)
        result["horizons"][key] = {
            "n": stats["n"],
            "mean": _round(stats["mean"]),
            "median": _round(stats["median"]),
            "std": _round(stats["std"]),
            "hit_rate": _round(sum(1 for value in values if value > 0) / len(values)) if values else None,
            "t": _round(t_stat(values)),
            "mean_net_by_cost": {
                cost: _round(_mean([value - 2.0 * bps / 10000.0 for value in values]))
                for cost, bps in cost_items
            },
        }
    for side in ("BUY", "SHORT"):
        subset = [step for step in accepted if step.get("decision") == side]
        if not subset:
            continue
        result["by_side"][side] = {
            str(horizon): {
                "n": sum(1 for step in subset if step.get(f"outcome_{horizon}d") is not None),
                "mean": _round(
                    _mean(
                        [
                            float(step[f"outcome_{horizon}d"])
                            for step in subset
                            if step.get(f"outcome_{horizon}d") is not None
                        ]
                    )
                ),
            }
            for horizon in HORIZONS
        }
    return result


# --------------------------------------------------------------------------- simulate
def _simulate(
    db: Any,
    start_day: date,
    end_day: date,
    *,
    capital: float,
    costs_bps: Sequence[float],
    intraday_days: float,
    now: datetime,
    fetcher: Any,
    offline: bool,
    max_requests: int,
    hold_days: int,
    allow_short: bool,
    position_pct: float,
    max_concurrent: int,
    min_score: float,
    source_mode: str = "auto",
    max_steps: int | None = None,
    per_kind_limit: Any = DEFAULT_PER_KIND_LIMIT,
) -> dict[str, Any]:
    names = _company_names()
    event_stats: dict[str, Any] = {}
    signals_rows = _load_signal_rows(db) if source_mode != "events" else []
    use_events = source_mode == "events" or (source_mode == "auto" and not signals_rows)
    if use_events:
        effective_max_steps = max_steps if max_steps is not None else DEFAULT_EVENT_MAX_STEPS
        rows, event_stats = _event_mode_rows(
            db,
            start_day,
            end_day,
            per_kind_limit=per_kind_limit,
            max_steps=effective_max_steps,
        )
        signal_source = "events" if source_mode == "events" else "events_fallback"
    else:
        rows = signals_rows
        signal_source = "signals_table"
        effective_max_steps = None
    event_mode = use_events
    # Both modes share one price rule: 1-minute bars exist only for the most
    # recent ~7 days, so older public moments automatically fall back to the
    # next-session daily open. ``intraday_days=0`` forces daily-only.
    resolution_intraday_days = float(intraday_days)
    unique_rows, duplicates = _dedupe_rows(rows)
    in_window = [
        row
        for row in unique_rows
        if row.get("_signal_day") is not None and start_day <= row["_signal_day"] <= end_day
    ]

    filtered: list[dict[str, Any]] = []
    usable: list[dict[str, Any]] = []
    quality_counts: Counter[str] = Counter()
    for row in in_window:
        available_at, quality = _resolve_available_at(row)
        quality_counts[quality] += 1
        if available_at is None or quality == "unknown":
            filtered.append(
                {
                    "signal_id": row.get("signal_id"),
                    "ticker": row.get("_ticker"),
                    "reason": "low_timestamp_quality",
                    "timestamp_quality": quality,
                }
            )
            continue
        usable.append(row)

    tickers = sorted({str(row.get("_ticker") or "") for row in usable if row.get("_ticker")})
    daily_years = max(1, min(10, int(math.ceil((now.date() - start_day).days / 365.25)) + 1))
    book = _PriceBook(
        db,
        fetcher if usable else None,  # no candidates -> never touch the network
        offline=offline,
        now=now,
        daily_years=daily_years,
        budget_max=max_requests,
    )
    calendar = book.calendar(tickers) if usable else []

    steps: list[dict[str, Any]] = []
    for row in usable:
        step = _resolve_step(
            row,
            book=book,
            calendar=calendar,
            now=now,
            names=names,
            intraday_days=resolution_intraday_days,
            allow_short=allow_short,
            capital=capital,
            position_pct=position_pct,
            hold_days=hold_days,
            min_score=min_score,
        )
        if step is not None:
            steps.append(step)
    steps.sort(
        key=lambda step: (
            step.get("_sort") or now,
            step.get("ticker") or "",
            str(step.get("signal_id") or ""),
        )
    )
    _assign_capacity(steps, max_concurrent)

    cost_items = [(cost_key(bps), float(bps)) for bps in costs_bps]
    for step in steps:
        if step.get("decision") in ("BUY", "SHORT"):
            for key, bps in cost_items:
                net = float(step["gross_return"]) - 2.0 * bps / 10000.0
                step["net_by_cost"][key] = round(net, 6)
                step["pnl_by_cost"][key] = round(float(step["notional"]) * net, 2)

    trades_by_cost: dict[str, list[dict[str, Any]]] = {}
    summary_by_cost: dict[str, dict[str, Any]] = {}
    for key, bps in cost_items:
        trades: list[dict[str, Any]] = []
        for step in steps:
            if step.get("decision") not in ("BUY", "SHORT"):
                continue
            net = float(step["gross_return"]) - 2.0 * bps / 10000.0
            trades.append(
                {
                    "trade_id": f"replay-{str(step.get('step_id') or '').split('-')[-1]}",
                    "step_id": step.get("step_id"),
                    "signal_id": step.get("signal_id"),
                    "event_id": step.get("event_id"),
                    "ticker": step.get("ticker"),
                    "company_zh": step.get("company_zh"),
                    "kind": step.get("kind"),
                    "side": step.get("side"),
                    "decision": step.get("decision"),
                    "entry_date": step.get("fill_date"),
                    "entry_time": step.get("fill_time"),
                    "entry_price": step.get("fill_price"),
                    "price_source": step.get("price_source"),
                    "notional": step.get("notional"),
                    "shares": step.get("shares"),
                    "exit_date": step.get("exit_date"),
                    "exit_price": step.get("exit_price"),
                    "exit_reason": step.get("exit_reason"),
                    "holding_days": step.get("holding_days"),
                    "cost_bps": bps,
                    "gross_return": step.get("gross_return"),
                    "ret": round(net, 6),
                    "pnl": round(float(step["notional"]) * net, 2),
                    "fwd_1d": step.get("outcome_1d"),
                    "fwd_5d": step.get("outcome_5d"),
                    "fwd_20d": step.get("outcome_20d"),
                    "url": step.get("url"),
                    "available_at": step.get("available_at"),
                    "timestamp_quality": step.get("timestamp_quality"),
                }
            )
        trades_by_cost[key] = trades
        summary = _summarize(trades, capital, bps)
        summary["n_signals"] = len(in_window)
        summary["n_steps"] = len(steps)
        summary["n_skipped"] = sum(1 for step in steps if step.get("decision") == "SKIP")
        summary_by_cost[key] = summary

    accepted = [step for step in steps if step.get("decision") in ("BUY", "SHORT")]
    skip_reasons: Counter[str] = Counter(
        str(step.get("skip_reason")) for step in steps if step.get("decision") == "SKIP"
    )
    price_sources: Counter[str] = Counter(
        str(step.get("price_source")) for step in steps if step.get("price_source")
    )
    # Verifiable 1-minute boundary statistics (also exposed top-level):
    #   1m       = fill came from the first 1-minute bar after available_at
    #   daily    = daily open, no 1-minute attempt was needed (outside window /
    #              forced daily / offline)
    #   fallback = 1-minute request attempted but unusable -> daily open
    #   missing  = step never reached a price (no price / no future session)
    price_source_counts: dict[str, int] = {
        "1m": 0,
        "daily": 0,
        "fallback": 0,
        "missing": 0,
        "total": len(steps),
    }
    for step in steps:
        source = step.get("price_source")
        if source == "1m":
            price_source_counts["1m"] += 1
        elif source == "daily":
            if step.get("intraday_fallback"):
                price_source_counts["fallback"] += 1
            else:
                price_source_counts["daily"] += 1
        else:
            price_source_counts["missing"] += 1
    intraday_eligible = any(
        _intraday_eligible(moment, now, resolution_intraday_days) for moment in _all_moments(usable)
    )
    intraday_status = _intraday_status(book, intraday_eligible)

    first_seen_lags = _first_seen_lags(usable)
    steps_payload = [_public_step(step) for step in steps]
    entered = len(accepted)
    status = "ok"
    reason: str | None = None
    if not rows:
        status = "insufficient_data"
        reason = "no_event_candidates" if (event_mode and source_mode == "events") else "no_signals"
    elif not in_window:
        status, reason = "insufficient_data", "no_signals_in_window"
    elif not usable:
        status, reason = "insufficient_data", "low_timestamp_quality"
    elif not calendar:
        status, reason = "insufficient_data", "no_calendar"
    elif entered == 0:
        status = "insufficient_data"
        for candidate in ("no_price", "no_future_bar", "no_future_price", "not_yet_public"):
            if skip_reasons.get(candidate):
                reason = {
                    "no_price": "no_prices",
                    "no_future_bar": "no_future_bars",
                    "no_future_price": "no_future_bars",
                    "not_yet_public": "no_public_events_yet",
                }[candidate]
                break
        reason = reason or "no_trades"

    first_key = cost_items[0][0] if cost_items else None
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "reason": reason,
        "as_of": calendar[-1] if calendar else now.date().isoformat(),
        "window": {
            "start": start_day.isoformat(),
            "end": end_day.isoformat(),
            "signals": len(in_window),
        },
        # Contract for the 1-minute boundary (verifiable, machine-readable):
        "intraday_window_days": float(resolution_intraday_days),
        "price_source_counts": price_source_counts,
        "assumptions": [
            "decision_time=events.available_at（公开时点，缺失或估算质量的事件不进回放）",
            "date 级时间戳按当日 23:59:59 UTC 处理；datetime 级按实际时刻处理",
            "fill=公开时点之后第一根 bar 的开盘价（1 分钟数据不可用时降级为次日交易日开盘价）",
            "exit=入场后第 20 个交易日收盘价（数据末端回退为最后可得收盘价，exit_reason=end_of_data）",
            "costs_bps 为单边成本，入场与出场各计一次；未建模冲击成本与借券费",
            "仅做多（做空信号以 reference_only 记录参考价与假设结果，不入账）",
            "Yahoo 1 分钟数据仅覆盖最近约 7 天；更早事件只能使用日线",
        ],
        "meta": {
            "generated_at": utc_now_iso(),
            "engine": ENGINE,
            "schema_version": SCHEMA_VERSION,
            "capital": float(capital),
            "costs_bps": [float(bps) for bps in costs_bps],
            "intraday_days": float(resolution_intraday_days),
            "intraday_window_days": float(resolution_intraday_days),
            "hold_days": int(hold_days),
            "allow_short": bool(allow_short),
            "position_pct": float(position_pct),
            "max_concurrent": int(max_concurrent),
            "min_score": float(min_score),
            "max_requests": int(max_requests),
            "offline": bool(offline),
            "price_window": {"days": float(resolution_intraday_days), "interval": INTRADAY_INTERVAL},
            "signals_total": len(rows),
            "signals_deduped": duplicates,
            "signals_in_window": len(in_window),
            "signals_filtered": len(filtered),
            "signals_usable": len(usable),
            "skipped_low_timestamp_quality": len(filtered),
            "timestamp_quality_counts": dict(sorted(quality_counts.items())),
            "daily_price_window_years": daily_years,
            "lookahead_rejected": int(skip_reasons.get("lookahead_rejected", 0)),
            "daily_prices": book.daily_status(tickers),
            "intraday_errors": book.intraday_errors(),
            "signal_source": signal_source,
        },
        "window_stats": {
            "signals": len(in_window),
            "candidates": len(usable),
            "entered": entered,
            "skipped": len(steps) - entered,
        },
        "coverage": {
            "signals_total": len(rows),
            "in_window": len(in_window),
            "usable": len(usable),
            "filtered_low_timestamp_quality": len(filtered),
            "entered": entered,
            "skipped": len(steps) - entered,
        },
        "timestamp_quality": {
            "counts": dict(sorted(quality_counts.items())),
            "counts_zh": {QUALITY_ZH.get(key, key): value for key, value in sorted(quality_counts.items())},
            "filtered": len(filtered),
            "filtered_signals": filtered[:50],
        },
        "data_sources": {
            "daily": book.daily_status(tickers),
            "intraday": {
                "status": intraday_status,
                "status_zh": INTRADAY_STATUS_ZH.get(intraday_status, intraday_status),
                "requested": bool(book.intraday_errors()) or intraday_status in ("ok", "partial"),
                "errors": book.intraday_errors(),
            },
            "requests": book.request_stats(),
        },
        "price_source_counts": price_source_counts,
        "first_seen_lag_days": first_seen_lags,
        "steps": steps_payload,
        "timeline": steps_payload,
        "trades_by_cost": trades_by_cost,
        "trades": trades_by_cost.get(first_key or "", []),
        "summary_by_cost": summary_by_cost,
        "summary": summary_by_cost.get(first_key or "", {}),
        "event_study": _event_study(steps, cost_items),
        "skip_reasons": dict(sorted(skip_reasons.items())),
        "price_sources": dict(sorted(price_sources.items())),
        "decision_counts": {
            "BUY": sum(1 for step in steps if step.get("decision") == "BUY"),
            "SHORT": sum(1 for step in steps if step.get("decision") == "SHORT"),
            "SKIP": sum(1 for step in steps if step.get("decision") == "SKIP"),
        },
        "lookahead_rejected": int(skip_reasons.get("lookahead_rejected", 0)),
        "assumptions_url": ASSUMPTIONS_URL,
        "disclaimer": DISCLAIMER_ZH,
        "limits": [
            "仅覆盖最近约 7 天的 1 分钟数据，其余交易日退化为次日开盘价",
            "无 bid/ask，成交价为 bar 开盘价加 bps 成本的假设值",
            "无借券数据，默认仅做多",
        ],
    }
    if signal_source != "signals_table":
        payload["meta"]["event_mode"] = event_stats
        payload["meta"]["candidate_kind_counts"] = event_stats.get("candidate_counts")
        payload["meta"]["sampled_kind_counts"] = event_stats.get("sampled_counts")
        payload["meta"]["selection"] = {
            "per_kind_limit": event_stats.get("per_kind_limit"),
            "max_steps": event_stats.get("max_steps"),
            "total_candidates": event_stats.get("total_candidates"),
            "total_steps": event_stats.get("total_steps"),
            "diversity": event_stats.get("diversity"),
        }
    return payload


def _all_moments(rows: Iterable[Mapping[str, Any]]) -> list[datetime]:
    moments = []
    for row in rows:
        moment, quality = _resolve_available_at(row)
        if moment is not None and quality in QUALITY_ALLOWED:
            moments.append(moment)
    return moments


def _intraday_status(book: _PriceBook, eligible: bool) -> str:
    errors = book.intraday_errors()
    if not eligible:
        return "not_requested"
    if book.fetcher is None:
        return "unavailable"
    if not errors:
        return "ok"
    return "partial"


def _first_seen_lags(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    lags: list[float] = []
    for row in rows:
        first_seen = _parse_moment(row.get("first_seen_at"))[0]
        available_at = _resolve_available_at(row)[0]
        if first_seen is None or available_at is None:
            continue
        lag = (available_at - first_seen).total_seconds() / 86400.0
        if lag >= 0:
            lags.append(lag)
    if not lags:
        return {"n": 0, "mean": None, "median": None, "p90": None}
    ordered = sorted(lags)
    p90_index = min(len(ordered) - 1, int(math.ceil(len(ordered) * 0.9)) - 1)
    return {
        "n": len(ordered),
        "mean": _round(_mean(ordered), 3),
        "median": _round(ordered[len(ordered) // 2], 3),
        "p90": _round(ordered[p90_index], 3),
    }


def _public_step(step: Mapping[str, Any]) -> dict[str, Any]:
    """Strip internal bookkeeping fields from a step for the JSON/HTML output."""
    keep = {
        key: value
        for key, value in step.items()
        if not str(key).startswith("_")
    }
    return keep


# --------------------------------------------------------------------------- HTML
_CSS = """
:root{--bg:#f6f7f9;--panel:#ffffff;--ink:#1b2733;--muted:#5d6b7a;--line:#d9e0e7;
--accent:#2c6fbb;--good:#2e7d32;--bad:#c62828;--skip:#8a6d1d;--chip:#eef3f8}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font-family:"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;font-size:14px;line-height:1.5}
header{padding:22px 24px 14px;border-bottom:1px solid var(--line);background:var(--panel)}
header h1{margin:0 0 6px;font-size:20px}
header .sub{color:var(--muted);font-size:13px}
.banner{margin:14px 24px 0;padding:10px 14px;border:1px solid #f0d48a;background:#fff8e1;border-radius:6px;font-size:13px}
.banner b{color:#7a5c00}
main{padding:16px 24px 40px;display:block}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:16px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px 12px}
.card .k{font-size:12px;color:var(--muted)}
.card .v{font-size:17px;font-weight:600;margin-top:2px;word-break:break-all}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px 16px;margin-bottom:16px}
.panel h2{margin:0 0 10px;font-size:15px}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;white-space:nowrap}
td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.chip{display:inline-block;padding:1px 8px;border-radius:999px;font-size:11.5px;font-weight:600;white-space:nowrap}
.chip.buy{background:#e6f2e6;color:var(--good)}
.chip.short{background:#fdecea;color:var(--bad)}
.chip.skip{background:var(--chip);color:var(--skip)}
.muted{color:var(--muted)}
.step{border-top:1px solid var(--line);padding:10px 2px}
.step:first-of-type{border-top:none}
.step .row1{display:flex;flex-wrap:wrap;gap:8px;align-items:baseline}
.step .row1 .t{font-weight:600;font-variant-numeric:tabular-nums}
.step .row1 .ticker{font-weight:700;color:var(--accent)}
.step .row2{margin-top:4px}
.step .row3{margin-top:4px;font-size:12.5px;color:var(--muted)}
.step .arrow{color:var(--muted);padding:0 4px}
.pos{color:var(--good);font-weight:600}
.neg{color:var(--bad);font-weight:600}
.spark{width:100%;height:auto;display:block;margin-top:6px}
footer{padding:14px 24px 28px;color:var(--muted);font-size:12px}
footer p{margin:4px 0}
a{color:var(--accent)}
.src{display:block;font-size:11.5px;color:var(--muted);margin-top:2px;word-break:break-all}
@media (max-width:720px){main,header,footer{padding-left:12px;padding-right:12px}}
"""


def _esc(value: Any) -> str:
    return _html.escape("" if value is None else str(value))


def _fmt_pct(value: Any, digits: int = 1) -> str:
    number = _as_float(value)
    if number is None:
        return "—"
    return f"{number * 100:.{digits}f}%"


def _fmt_pct_signed(value: Any, digits: int = 2) -> str:
    number = _as_float(value)
    if number is None:
        return "—"
    cls = "pos" if number >= 0 else "neg"
    return f'<span class="{cls}">{number * 100:+.{digits}f}%</span>'


def _fmt_money(value: Any) -> str:
    number = _as_float(value)
    if number is None:
        return "—"
    return f"${number:,.0f}"


def _fmt_number(value: Any, digits: int = 2) -> str:
    number = _as_float(value)
    if number is None:
        return "—"
    return f"{number:,.{digits}f}"


def _sparkline(points: Sequence[Mapping[str, Any]]) -> str:
    """Inline SVG equity sparkline (zero dependencies, zero JS)."""
    values = [_as_float(point.get("equity")) for point in points]
    values = [value for value in values if value is not None]
    if len(values) < 2:
        return '<span class="muted">权益曲线点不足</span>'
    width, height = 320, 48
    low, high = min(values), max(values)
    span = (high - low) or 1.0
    step_x = width / (len(values) - 1)
    coords = []
    for index, value in enumerate(values):
        x = index * step_x
        y = height - 4 - (value - low) / span * (height - 8)
        coords.append(f"{x:.1f},{y:.1f}")
    return (
        f'<svg class="spark" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="权益曲线">'
        f'<polyline fill="none" stroke="#2c6fbb" stroke-width="1.6" points="{" ".join(coords)}"/>'
        f"</svg>"
    )


def _decision_chip(decision: str) -> str:
    mapping = {"BUY": ("chip buy", "做多"), "SHORT": ("chip short", "做空"), "SKIP": ("chip skip", "跳过")}
    cls, label = mapping.get(decision, ("chip skip", decision or "?"))
    return f'<span class="{cls}">{_esc(label)}</span>'


def _step_html(step: Mapping[str, Any]) -> str:
    decision = str(step.get("decision") or "SKIP")
    when = _esc(step.get("fill_time") or step.get("t") or step.get("available_at") or "—")
    ticker = _esc(step.get("ticker") or "—")
    event = _esc(step.get("event_zh") or step.get("kind_zh") or "事件")
    fill = _esc(_fmt_number(step.get("fill_price")))
    parts = [f'<div class="row1"><span class="t">{when}</span>'
             f'<span class="ticker">{ticker}</span>{_decision_chip(decision)}</div>']
    parts.append(f'<div class="row2">{_esc(step.get("company_zh") or "")} {event}</div>')
    if decision == "SKIP":
        reason = _esc(step.get("skip_reason_zh") or step.get("skip_reason") or "")
        row3 = f"跳过原因：{reason}"
        if step.get("fill_price") is not None:
            tag = "（参考价，不入账）" if step.get("reference_only") else ""
            row3 += f" ｜ 参考价 {fill}{tag}"
    else:
        row3 = (
            f'成交价 {fill}'
            f'<span class="arrow">→</span>1日 {_fmt_pct_signed(step.get("outcome_1d"))}'
            f'<span class="arrow">·</span>5日 {_fmt_pct_signed(step.get("outcome_5d"))}'
            f'<span class="arrow">·</span>20日 {_fmt_pct_signed(step.get("outcome_20d"))}'
        )
        price_source = _esc(step.get("price_source_zh") or "")
        if price_source:
            row3 += f' ｜ {price_source}'
        if step.get("intraday_fallback"):
            row3 += f'（1 分钟降级：{_esc(step.get("intraday_fallback"))}）'
    url = str(step.get("url") or "").strip()
    if url:
        parts.append(f'<div class="row3">{row3}<a class="src" href="{_esc(url)}" rel="noopener">{_esc(url)}</a></div>')
    else:
        parts.append(f'<div class="row3">{row3}</div>')
    return f'<div class="step">{"".join(parts)}</div>'


def render_html(payload: Mapping[str, Any], docs_rel: str = "../../docs/ASSUMPTIONS.md") -> str:
    meta = payload.get("meta") or {}
    coverage = payload.get("coverage") or {}
    quality = payload.get("timestamp_quality") or {}
    sources = payload.get("data_sources") or {}
    intraday = sources.get("intraday") or {}
    window = payload.get("window") or {}
    steps = list(payload.get("steps") or payload.get("timeline") or [])
    status = str(payload.get("status") or "ok")
    decision_counts = payload.get("decision_counts") or {}

    cards = [
        ("回放窗口", f"{_esc(window.get('start') or '—')} ~ {_esc(window.get('end') or '—')}"),
        ("事件总数", _esc(coverage.get("signals_total", meta.get("signals_total", "—")))),
        ("窗口内信号", _esc(coverage.get("in_window", "—"))),
        ("可用信号", _esc(coverage.get("usable", "—"))),
        ("做多成交", _esc(decision_counts.get("BUY", 0))),
        ("跳过", _esc(decision_counts.get("SKIP", 0))),
        ("1 分钟数据", _esc(intraday.get("status_zh") or intraday.get("status") or "—")),
        ("前视拒绝", _esc(payload.get("lookahead_rejected", 0))),
    ]
    card_html = "".join(
        f'<div class="card"><div class="k">{_esc(label)}</div><div class="v">{value}</div></div>'
        for label, value in cards
    )

    summary_rows = []
    for key, summary in (payload.get("summary_by_cost") or {}).items():
        summary_rows.append(
            "<tr>"
            f"<td>{_esc(key)} bps（单边）</td>"
            f'<td class="num">{_esc(summary.get("trades", 0))}</td>'
            f'<td class="num">{_fmt_pct_signed(summary.get("total_return"))}</td>'
            f'<td class="num">{_esc(_fmt_money(summary.get("total_pnl")))}</td>'
            f'<td class="num">{_fmt_pct(summary.get("win_rate"))}</td>'
            f'<td class="num">{_fmt_pct(summary.get("max_drawdown"))}</td>'
            f'<td class="num">{_esc(_fmt_number(summary.get("avg_holding_days"), 1))}</td>'
            "</tr>"
        )
    summary_table = (
        "<table><thead><tr><th>成本（单边）</th><th>笔数</th><th>总收益</th><th>盈亏</th>"
        "<th>胜率</th><th>最大回撤</th><th>平均持有（交易日）</th></tr></thead>"
        f"<tbody>{''.join(summary_rows) or '<tr><td colspan=\"7\" class=\"muted\">无成交</td></tr>'}</tbody></table>"
    )

    quality_rows = "".join(
        f'<tr><td>{_esc(QUALITY_ZH.get(name, name))}</td><td class="num">{_esc(count)}</td></tr>'
        for name, count in (quality.get("counts") or {}).items()
    )
    quality_table = (
        '<table><thead><tr><th>时间戳质量</th><th>信号数</th></tr></thead>'
        f"<tbody>{quality_rows or '<tr><td colspan=\"2\" class=\"muted\">无数据</td></tr>'}</tbody></table>"
        f'<p class="muted">因时间戳质量不足被过滤：{_esc(quality.get("filtered", 0))} 条'
        "（这些事件仍用于行业统计，但不进入回放）。</p>"
    )

    event_study = payload.get("event_study") or {}
    horizon_rows = []
    for horizon, stats in (event_study.get("horizons") or {}).items():
        net = (stats.get("mean_net_by_cost") or {})
        net_text = " / ".join(f"{k}:{_fmt_pct(v)}" for k, v in net.items()) or "—"
        horizon_rows.append(
            f'<tr><td>{_esc(horizon)} 日</td><td class="num">{_esc(stats.get("n", 0))}</td>'
            f'<td class="num">{_fmt_pct_signed(stats.get("mean"))}</td>'
            f'<td class="num">{_fmt_pct(stats.get("hit_rate"))}</td>'
            f'<td class="num">{_esc(_fmt_number(stats.get("t"), 2))}</td>'
            f'<td class="num muted">{_esc(net_text)}</td></tr>'
        )
    study_table = (
        "<table><thead><tr><th>窗口</th><th>样本</th><th>平均毛收益</th><th>胜率</th><th>t 值</th>"
        "<th>净收益均值（10/25/50bps）</th></tr></thead>"
        f"<tbody>{''.join(horizon_rows) or '<tr><td colspan=\"6\" class=\"muted\">无成交样本</td></tr>'}</tbody></table>"
    )

    first_summary = payload.get("summary") or {}
    spark = _sparkline(first_summary.get("equity_curve") or [])
    steps_html = "".join(_step_html(step) for step in steps) or '<p class="muted">本窗口没有可展示的回放步骤。</p>'

    assumptions_items = "".join(f"<li>{_esc(item)}</li>" for item in (payload.get("assumptions") or []))
    limits_items = "".join(f"<li>{_esc(item)}</li>" for item in (payload.get("limits") or []))

    intraday_days = meta.get("intraday_days", 7)
    if meta.get("offline"):
        intraday_note = "本次为离线回放：不请求 1 分钟数据，所有成交按日线口径（公开日后首个交易日开盘价）。"
    else:
        intraday_days_note = _esc(intraday_days)
        intraday_note = (
            f"最近约 {intraday_days_note} 天内公开的事件使用 Yahoo 1 分钟 bar 开盘价；"
            "更早事件使用次日交易日开盘价。"
        )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MedRadar 回放 · 事件到成交</title>
<style>{_CSS}</style>
</head>
<body>
<header>
<h1>MedRadar 回放 · 事件 → 判定 → 成交 → 1/5/20 日</h1>
<div class="sub">生成于 {_esc(meta.get("generated_at", "—"))} ｜ 引擎 {_esc(meta.get("engine", ENGINE))} ｜ 模式 {"离线" if meta.get("offline") else "在线"} ｜ 状态 {_esc(status)}</div>
</header>
<div class="banner">
<b>口径与限制（务必阅读）：</b>{_esc(payload.get("disclaimer") or DISCLAIMER_ZH)}<br>
1) 判定时间只使用 events.available_at（公开时点），缺失或估算时间的事件不进回放；
2) 成交价 = 公开时点之后第一根 bar 的开盘价（{_esc(intraday_note)}）；
3) 数据限制：Yahoo 1 分钟数据仅覆盖最近约 7 天，无 bid/ask（成交价为假设值）、无借券数据（默认仅做多）。
</div>
<main>
<div class="grid">{card_html}</div>
<div class="panel"><h2>权益曲线（{(payload.get("meta") or {}).get("costs_bps", [10])[0]}bps 单边）</h2>{spark}
<p class="muted">{_esc(payload.get("as_of", ""))} 截止；end_of_data 退出表示数据末端无更多收盘价。</p></div>
<div class="panel"><h2>成本敏感性</h2>{summary_table}</div>
<div class="panel"><h2>事件研究（成交样本的 1/5/20 日）</h2>{study_table}</div>
<div class="panel"><h2>时间戳质量（为什么有些事件不进回放）</h2>{quality_table}</div>
<div class="panel"><h2>回放步骤（{len(steps)}）</h2>{steps_html}</div>
<div class="panel"><h2>假设</h2><ul>{assumptions_items}</ul>
<h2>数据限制</h2><ul>{limits_items}</ul>
<p class="muted">假设登记表：<a href="{_esc(docs_rel)}">{_esc(docs_rel)}</a>（README 与 SCHEMA 同步维护）。</p></div>
</main>
<footer>
<p>{_esc(payload.get("disclaimer") or DISCLAIMER_ZH)}</p>
<p>MedRadar · 开源研究工具 · 非投资建议</p>
</footer>
</body>
</html>"""


# --------------------------------------------------------------------------- entry point
def build_replay(
    db: Any = None,
    start: Any = None,
    end: Any = None,
    *,
    capital: float = 100000.0,
    costs_bps: Sequence[float] = DEFAULT_COSTS_BPS,
    intraday_days: float = 7,
    hold_days: int = 20,
    allow_short: bool = False,
    position_pct: float = 0.20,
    max_concurrent: int = 5,
    min_score: float = 0.3,
    source: str = "auto",
    out_dir: Any = None,
    now: Any = None,
    fetcher: Any = None,
    offline: bool = False,
    max_requests: int = 24,
    max_steps: int | None = None,
    per_kind_limit: Any = DEFAULT_PER_KIND_LIMIT,
) -> dict[str, Any]:
    """Replay ``db`` events between ``start`` and ``end`` (inclusive dates).

    ``source='signals'`` replays the analyst-written ``signals`` table;
    ``source='events'`` derives point-in-time candidates from ``events``
    (first-seen product codes / new tracks, drug approvals, Phase-III trial
    starts, recall clusters, 8-K catalysts) and is the only mode that scales to
    a multi-year window; ``'auto'`` prefers ``signals`` and falls back to
    ``events`` when the table is empty. ``max_steps`` (default 400 in events
    mode; pass ``None`` for no global cap in research runs — the CLI already
    does this) and ``per_kind_limit`` (default 150 per kind) keep a 300k+
    event corpus bounded and diverse.

    ``now`` is injectable so the "最近 7 天" branch is deterministic in tests.
    The parameter list above is the public contract; the keyword-only parameters
    are research controls with documented defaults.
    """
    start_day = parse_date(start)
    end_day = parse_date(end)
    if start_day is None or end_day is None:
        raise ValueError(f"invalid replay window: start={start!r} end={end!r}")
    if end_day < start_day:
        start_day, end_day = end_day, start_day
    source_mode = str(source or "auto").strip().lower()
    if source_mode not in ("auto", "signals", "events"):
        raise ValueError(f"invalid replay source: {source!r} (expected auto|signals|events)")
    if max_steps is not None and int(max_steps) < 0:
        raise ValueError("max_steps must be non-negative or None")
    kind_limits = _normalise_kind_limits(per_kind_limit)
    capital = float(capital)
    if capital <= 0:
        raise ValueError("capital must be positive")
    tiers = tuple(float(bps) for bps in (costs_bps or DEFAULT_COSTS_BPS))
    if not tiers:
        raise ValueError("costs_bps must contain at least one tier")
    moment_now = _now_utc(now)
    budget = max(0, int(max_requests))
    active_fetcher = _prepare_fetcher(fetcher, offline, budget)

    own_db: DB | None = None
    if isinstance(db, (str, Path)):
        own_db = DB(db)
        db = own_db
    try:
        payload = _simulate(
            db,
            start_day,
            end_day,
            capital=capital,
            costs_bps=tiers,
            intraday_days=float(intraday_days),
            now=moment_now,
            fetcher=active_fetcher,
            offline=bool(offline),
            max_requests=budget,
            hold_days=max(1, int(hold_days)),
            allow_short=bool(allow_short),
            position_pct=_clamp(float(position_pct), 0.0, 1.0) or DEFAULT_POSITION_PCT,
            max_concurrent=max(1, int(max_concurrent)),
            min_score=float(min_score),
            source_mode=source_mode,
            max_steps=None if max_steps is None else int(max_steps),
            per_kind_limit=kind_limits,
        )
    finally:
        if own_db is not None:
            own_db.close()

    target = Path(out_dir) if out_dir is not None else (OUT_DIR / "replay")
    ensure_dir(target)
    json_path = target / "replay.json"
    html_path = target / "index.html"
    payload["files"] = {"json": str(json_path), "html": str(html_path)}
    try:
        docs_rel = os.path.relpath(ROOT / "docs" / "ASSUMPTIONS.md", target)
    except ValueError:  # pragma: no cover - exotic drive layouts
        docs_rel = ASSUMPTIONS_URL
    docs_rel = Path(docs_rel).as_posix()
    html_text = render_html(payload, docs_rel=docs_rel)
    write_text(html_path, html_text)
    write_json(json_path, payload)
    return payload


def _prepare_fetcher(fetcher: Any, offline: bool, max_requests: int) -> Any:
    """Build the budgeted fetcher used for intraday bars and daily fallbacks."""
    if fetcher is not None:
        return fetcher if isinstance(fetcher, _BudgetedFetcher) else _BudgetedFetcher(fetcher, max_requests)
    if offline:
        return None
    return _BudgetedFetcher(Fetcher(cache_dir=CACHE_DIR / "http"), max_requests)


__all__ = [
    "ASSUMPTIONS_URL",
    "DEFAULT_COSTS_BPS",
    "DEFAULT_EVENT_MAX_STEPS",
    "DEFAULT_PER_KIND_LIMIT",
    "ENGINE",
    "EVENT_MODE_KINDS",
    "SCHEMA_VERSION",
    "build_replay",
    "cost_key",
    "fetch_intraday",
    "parse_intraday_chart",
    "render_html",
]
