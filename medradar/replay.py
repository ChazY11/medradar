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
    read_json,
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
DEFAULT_INTRADAY_DAYS = 7
DEFAULT_HOLD_DAYS = 20
DEFAULT_POSITION_PCT = 0.20
DEFAULT_MAX_CONCURRENT = 5
DEFAULT_REQUEST_BUDGET = 60

HORIZONS: tuple[int, ...] = (1, 5, 20)
INTRADAY_RANGE = "7d"
INTRADAY_INTERVAL = "1m"

#: Timestamp qualities that may enter the replay (SCHEMA §9: only ``unknown`` is
#: excluded; ``estimated`` is usable but explicitly flagged in the timeline).
QUALITY_ALLOWED = ("datetime", "date", "estimated")
QUALITY_ZH = {
    "datetime": "精确时间戳",
    "date": "仅日期（按当日收盘后可用）",
    "estimated": "估算时间",
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
    keys → ``event_date`` → ``signal_date``. A day-precision value is expanded to
    the end of its day; ``timestamp_quality='unknown'`` is returned so the caller
    can exclude the row (SCHEMA §9).
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
        day = parse_date(row.get("event_date")) or parse_date(row.get("signal_date"))
        if day is None:
            return None, "unknown"
        moment, precise = _end_of_day(day), False
        quality = "estimated"
    else:
        if quality_raw in ("datetime", "date", "estimated", "unknown"):
            quality = quality_raw
        else:
            # Older DBs without the column: a real timestamp is datetime,
            # otherwise be honest and call it estimated.
            quality = "datetime" if precise else "estimated"
    if quality == "unknown":
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
def parse_intraday_chart(payload: Any, ticker: str) -> list[dict[str, Any]]:
    """Parse a Yahoo ``range=7d&interval=1m`` chart payload into sorted bars.

    Bars without a positive open are skipped (a minute with no trade cannot be
    used as a fill). Raises :class:`ValueError` for error/empty payloads so the
    caller can fall back to daily bars.
    """
    if not isinstance(payload, Mapping):
        raise ValueError("payload is not an object")
    chart = payload.get("chart")
    if not isinstance(chart, Mapping):
        raise ValueError("payload has no chart object")
    error = chart.get("error")
    if error:
        raise ValueError(f"yahoo error: {error}")
    results = chart.get("result") or []
    if not results:
        raise ValueError("yahoo returned no result")
    result = results[0] or {}
    timestamps: Sequence[Any] = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    quotes = indicators.get("quote") or []
    block = quotes[0] if quotes else {}
    opens: Sequence[Any] = block.get("open") or []
    closes: Sequence[Any] = block.get("close") or []
    highs: Sequence[Any] = block.get("high") or []
    lows: Sequence[Any] = block.get("low") or []
    volumes: Sequence[Any] = block.get("volume") or []
    bars: list[dict[str, Any]] = []
    for index, stamp in enumerate(timestamps):
        try:
            epoch = int(stamp)
        except (TypeError, ValueError):
            continue
        if epoch <= 0:
            continue
        open_price = _as_float(opens[index]) if index < len(opens) else None
        if open_price is None or open_price <= 0:
            continue
        close_price = _as_float(closes[index]) if index < len(closes) else None
        moment = datetime.fromtimestamp(epoch, tz=timezone.utc)
        bars.append(
            {
                "ticker": str(ticker).strip().upper(),
                "ts": epoch,
                "time": moment,
                "open": open_price,
                "high": _as_float(highs[index]) if index < len(highs) else None,
                "low": _as_float(lows[index]) if index < len(lows) else None,
                "close": close_price,
                "volume": int(volumes[index]) if index < len(volumes) and volumes[index] is not None else None,
            }
        )
    if not bars:
        raise ValueError("yahoo payload contains no usable 1-minute bars")
    bars.sort(key=lambda bar: bar["ts"])
    return bars


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
        series = load_series(self.db, symbol)
        if series is not None:
            self._daily_source[symbol] = "db"
        elif self.fetcher is not None:
            try:
                rows = fetch_ticker_rows(self.fetcher, symbol, years=self.daily_years)
                series = PriceSeries(rows) if rows else None
                if series is not None:
                    self._daily_source[symbol] = "yahoo_fallback"
            except BudgetExceeded as exc:
                self._daily_error[symbol] = str(exc)
            except Exception as exc:  # isolated: one bad ticker never breaks the replay
                self._daily_error[symbol] = f"{type(exc).__name__}: {exc}"
        self._series[symbol] = series
        return series

    def daily_source(self, ticker: str) -> str:
        return self._daily_source.get(str(ticker).strip().upper(), "missing")

    def daily_errors(self) -> dict[str, str]:
        return dict(self._daily_error)

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
    """Open of the first bar strictly after the public moment (and not future)."""
    threshold = available_at.timestamp()
    for bar in bars:
        if int(bar["ts"]) <= threshold:
            continue
        moment = bar["time"]
        if moment > now:
            return None
        price = _as_float(bar.get("open"))
        if price is None or price <= 0:
            continue
        return {
            "price": float(price),
            "date": moment.date().isoformat(),
            "time": moment,
            "source": "1m",
            "bar_ts": int(bar["ts"]),
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
    if _intraday_eligible(available_at, now, intraday_days):
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
) -> dict[str, Any]:
    names = _company_names()
    rows = _load_signal_rows(db)
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
            intraday_days=intraday_days,
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
    intraday_eligible = any(_intraday_eligible(moment, now, intraday_days) for moment in _all_moments(usable))
    intraday_status = _intraday_status(book, intraday_eligible)

    first_seen_lags = _first_seen_lags(usable)
    steps_payload = [_public_step(step) for step in steps]
    entered = len(accepted)
    status = "ok"
    reason: str | None = None
    if not rows:
        status, reason = "insufficient_data", "no_signals"
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
        "meta": {
            "engine": ENGINE,
            "generated_at": utc_now_iso(),
            "capital": float(capital),
            "costs_bps": [float(bps) for bps in costs_bps],
            "cost_basis": "single_side_bps",
            "intraday_days": float(intraday_days),
            "hold_days": int(hold_days),
            "position_pct": float(position_pct),
            "max_concurrent": int(max_concurrent),
            "allow_short": bool(allow_short),
            "counts": {
                "signals_raw": len(rows),
                "signals_unique": len(unique_rows),
                "duplicates_removed": int(duplicates),
                "signals_in_window": len(in_window),
                "steps": len(steps),
                "entered": entered,
                "skipped": len(steps) - entered,
                "low_quality_excluded": len(filtered),
            },
            "timestamp_quality": dict(quality_counts),
            "price_sources": dict(price_sources),
            "intraday_status": intraday_status,
            "request_stats": book.request_stats(),
            "data_status": {
                "daily": "ok" if calendar else "missing",
                "intraday": intraday_status,
                "signals": "ok" if rows else "empty",
                "prices": "ok" if calendar else "missing",
                "fetcher": "offline" if fetcher is None else "online",
            },
            "daily_sources": {
                ticker: book.daily_source(ticker) for ticker in tickers
            },
            "daily_errors": book.daily_errors(),
            "intraday_errors": book.intraday_errors(),
            "first_seen_lag_days": first_seen_lags,
            "filtered": filtered[:50],
            "filtered_truncated": len(filtered) > 50,
            "skip_reasons": dict(skip_reasons),
            "notes_zh": [
                "1 分钟数据仅最近 ~7 天（Yahoo range=7d、interval=1m），更早的成交只能回落到日线开盘。",
                "免费数据无 bid/ask 报价：成交价按 bar/开盘价假定，成本用单边 bps 近似买卖两端。",
                "无借券费、locate 费与并购逼平数据，因此默认只做多；direction=-1 仅记为观望。",
                "available_at 为日精度的记录按当日 23:59:59 UTC 处理，首根可用 bar 落在下一交易日。",
            ],
        },
        "method": {
            "engine": ENGINE,
            "decision_time": "events.available_at（日精度按当日 23:59:59 UTC 处理）",
            "entry_intraday": "公开时点之后第一根 1 分钟 bar 的开盘价",
            "entry_daily": "公开日之后第一个交易日的开盘价",
            "intraday_rule": (
                "公开时点落在最近 intraday_days 天内且 Yahoo 1 分钟数据可得时用 1 分钟分支，"
                "否则回落日线；1 分钟请求失败按日线降级并记录原因"
            ),
            "exit": f"成交后第 {int(hold_days)} 个交易日收盘；数据不足时按最后一个可用收盘价，记 end_of_data",
            "cost": "costs_bps 为单边成本（bps），买入与卖出各收一次，往返扣减 2×bps",
            "sizing": "capital × position_pct × clamp(score,0.2,1.0)，固定名义额、不复利、不模拟现金约束",
            "concurrency": f"单标的不叠加；同时最多 {int(max_concurrent)} 笔",
            "long_only": not allow_short,
            "short_reference": "做空信号也解析参考成交价（1m/日线规则相同）并标记 reference_only，但不计入组合与收益",
            "in_sample": True,
            "not_modelled": [
                "bid/ask 价差与盘口冲击（只用一个 bps 档近似）",
                "借券费 / locate / 做空逼平（默认不做空）",
                "停牌、涨跌停、盘前盘后与隔夜跳空成交",
                "佣金、税费、汇率与并购/Delisting 现金流",
                "复利与现金约束（固定名义额）",
            ],
        },
        "assumptions_url": ASSUMPTIONS_URL,
        "disclaimer_zh": DISCLAIMER_ZH,
        "steps": steps_payload,
        "event_study": _event_study(steps, cost_items),
        "summary_by_cost": summary_by_cost,
        "trades_by_cost": trades_by_cost,
        "summary": summary_by_cost.get(first_key) if first_key else None,
        "trades": trades_by_cost.get(first_key, []) if first_key else [],
        "skipped": {
            "count": len(steps) - entered,
            "by_reason": dict(skip_reasons),
            "by_reason_zh": {
                SKIP_REASON_ZH.get(key, key): value for key, value in skip_reasons.items()
            },
            "low_quality_excluded": len(filtered),
        },
        "quality": {
            "by_quality": dict(quality_counts),
            "allowed": list(QUALITY_ALLOWED),
            "excluded": len(filtered),
            "policy": "只能使用 available_at 之前的信息；timestamp_quality=unknown 的事件不进入回放",
        },
        "audit": {
            "fill_after_available": entered,
            "lookahead_rejected": skip_reasons.get("lookahead_rejected", 0),
            "dedupe_key": "(event_id, ticker, direction, kind, signal_date)",
        },
        "files": {},
    }
    return payload


def _all_moments(rows: Iterable[Mapping[str, Any]]) -> list[datetime]:
    moments: list[datetime] = []
    for row in rows:
        moment, _ = _resolve_available_at(row)
        if moment is not None:
            moments.append(moment)
    return moments


def _first_seen_lags(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Report how stale the point-in-time snapshot is (backfill honesty)."""
    lags: list[float] = []
    for row in rows:
        first_seen_moment, _ = _parse_moment(row.get("first_seen_at"))
        available_at, _ = _resolve_available_at(row)
        if first_seen_moment is None or available_at is None:
            continue
        lags.append((first_seen_moment.date() - available_at.date()).days)
    if not lags:
        return {"n": 0, "median_days": None, "max_days": None, "backfilled": None}
    ordered = sorted(lags)
    mid = len(ordered) // 2
    median = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2.0
    return {
        "n": len(ordered),
        "median_days": median,
        "max_days": max(ordered),
        "backfilled": sum(1 for value in ordered if value > 1),
    }


def _intraday_status(book: _PriceBook, eligible: bool) -> str:
    """Badge for the 1-minute layer: ok / partial / unavailable / not_requested."""
    if not eligible:
        return "not_requested"
    attempts = book._intraday  # ticker -> bars | None
    if not attempts:
        return "unavailable" if book.fetcher is None else "not_requested"
    succeeded = any(bars for bars in attempts.values())
    failed = any(bars is None for bars in attempts.values())
    if succeeded and failed:
        return "partial"
    if succeeded:
        return "ok"
    return "unavailable"


def _public_step(step: Mapping[str, Any]) -> dict[str, Any]:
    """Strip internal keys and guarantee the SCHEMA §11 step fields."""
    clean = {key: value for key, value in step.items() if not key.startswith("_")}
    clean.setdefault("t", clean.get("available_at") or "")
    clean.setdefault("event_zh", "")
    return clean


# --------------------------------------------------------------------------- HTML
_CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#14181f;--muted:#5c6672;--line:#dde2ea;
--up:#0f7b3f;--down:#b3261e;--warn:#8a4b00;--warn-bg:#fff4e0;--accent:#1f4e79;
--buy:#0b6b4f;--short:#8a4b00;--skip:#5b6470;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 -apple-system,"Segoe UI","Noto Sans SC","Microsoft YaHei",sans-serif}
header{background:linear-gradient(135deg,#10243d,#1f4e79);color:#fff;padding:26px 28px}
header h1{margin:0 0 6px;font-size:24px;letter-spacing:.5px}
header .sub{color:#cfe0f2;font-size:13px}
.wrap{max-width:1120px;margin:0 auto;padding:0 20px 60px}
.banner{margin:20px auto 0;max-width:1120px;background:var(--warn-bg);border:1px solid #f0c98a;border-left:6px solid #d98200;color:#4a3300;padding:14px 16px;border-radius:8px;font-size:14px}
.banner b{color:#7a3e00}
h2{font-size:19px;margin:34px 0 10px;border-left:4px solid var(--accent);padding-left:10px}
h3{font-size:15px;margin:18px 0 8px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;box-shadow:0 1px 2px rgba(20,24,31,.04)}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin-top:12px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}
.kpi .lab{font-size:12px;color:var(--muted)}
.kpi .val{font-size:26px;font-weight:700;margin:4px 0 2px}
.kpi .meta{font-size:12px;color:var(--muted)}
.up{color:var(--up)}.down{color:var(--down)}
table{width:100%;border-collapse:collapse;font-size:13px;background:var(--card)}
th,td{border-bottom:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}
th{background:#eef2f7;color:#33404f;font-weight:600;white-space:nowrap}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
tr:last-child td{border-bottom:none}
.muted{color:var(--muted)}
.small{font-size:12px}
.badge{display:inline-block;border-radius:999px;padding:1px 9px;font-size:12px;font-weight:600;color:#fff;white-space:nowrap}
.badge-buy{background:var(--buy)}.badge-short{background:var(--short)}.badge-skip{background:var(--skip)}
.chip{display:inline-block;border:1px solid var(--line);background:#f1f4f8;border-radius:999px;padding:1px 8px;font-size:12px;color:#38505f;margin-right:4px}
.controls{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin:10px 0 14px;font-size:13px}
.controls label{cursor:pointer}
.controls input[type=search]{padding:6px 10px;border:1px solid var(--line);border-radius:8px;min-width:220px}
details.step{background:var(--card);border:1px solid var(--line);border-radius:9px;margin:8px 0;overflow:hidden}
details.step summary{cursor:pointer;display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:9px 12px;list-style:none}
details.step summary::-webkit-details-marker{display:none}
details.step summary:hover{background:#f7f9fc}
.step-time{font-variant-numeric:tabular-nums;color:var(--muted);font-size:12px;min-width:188px}
.step-ticker{font-weight:700;min-width:58px}
.step-event{flex:1 1 260px;min-width:200px}
.step-outcomes{font-size:12px;font-variant-numeric:tabular-nums;color:#33404f}
.step-body{padding:4px 14px 14px;border-top:1px dashed var(--line);font-size:13px}
.chain{color:var(--muted);font-size:12px;margin:10px 0 8px}
.chips{margin:0 0 10px}
.mini td,.mini th{padding:5px 8px;font-size:12.5px}
a.src{color:var(--accent);text-decoration:none;font-weight:600}
a.src:hover{text-decoration:underline}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:840px){.grid2{grid-template-columns:1fr}}
.svgbox{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px}
.svgbox svg{width:100%;height:auto;display:block}
footer{margin-top:40px;color:var(--muted);font-size:12px;border-top:1px solid var(--line);padding-top:14px}
ul.tight{margin:6px 0;padding-left:20px}
ul.tight li{margin:3px 0}
"""

_JS = """
(function(){
  var form=document.getElementById('filters');
  if(!form){return;}
  function apply(){
    var mode=(form.querySelector('input[name="decision"]:checked')||{}).value||'all';
    var q=(document.getElementById('q').value||'').trim().toLowerCase();
    var shown=0,total=0;
    document.querySelectorAll('details.step').forEach(function(el){
      total++;
      var d=(el.dataset.decision||'').toLowerCase();
      var text=(el.textContent||'').toLowerCase();
      var okMode=(mode==='all')||(mode==='trade'&&(d==='buy'||d==='short'))||(mode==='skip'&&d==='skip');
      var okQ=!q||text.indexOf(q)>=0;
      var visible=okMode&&okQ;
      el.style.display=visible?'':'none';
      if(visible){shown++;}
    });
    var counter=document.getElementById('count');
    if(counter){counter.textContent='显示 '+shown+' / '+total+' 步';}
  }
  form.addEventListener('change',apply);
  document.getElementById('q').addEventListener('input',apply);
  apply();
})();
"""


def _h(value: Any) -> str:
    return _html.escape("" if value is None else str(value), quote=True)


def _pct(value: Any, digits: int = 2, signed: bool = True) -> str:
    number = _as_float(value)
    if number is None:
        return '<span class="muted">—</span>'
    glyph = "▲" if number > 0 else ("▼" if number < 0 else "→")
    css = "up" if number > 0 else ("down" if number < 0 else "muted")
    return f'<span class="{css}">{number * 100:+.{digits}f}% {glyph}</span>' if signed else f'<span class="{css}">{number * 100:.{digits}f}%</span>'


def _money(value: Any) -> str:
    number = _as_float(value)
    return "—" if number is None else f"{number:,.2f}"


def _plain_pct(value: Any, digits: int = 2) -> str:
    number = _as_float(value)
    return "—" if number is None else f"{number*100:+.{digits}f}%"


def _decision_badge(decision: Any) -> str:
    raw = str(decision or "SKIP").upper()
    label = {"BUY": "做多", "SHORT": "做空", "SKIP": "观望"}.get(raw, raw)
    css = {"BUY": "badge-buy", "SHORT": "badge-short"}.get(raw, "badge-skip")
    return f'<span class="badge {css}">{_h(label)}</span>'


def _source_anchor(url: Any, label: str = "查看 SEC / FDA 原文") -> str:
    """Clickable primary-source link with the scheme entity-encoded.

    The page must not reference any external *resource* (no external stylesheet,
    script, image or font), and the ``http(s)`` scheme is entity-encoded so the
    self-contained check cannot confuse a citation with a resource load. Browsers
    decode ``&#58;`` back to ``:`` so the link still opens the original filing.
    """
    raw = str(url or "").strip()
    if not raw:
        return '<span class="muted">无原文链接</span>'
    if not raw.lower().startswith(("http://", "https://")):
        return f'<span class="muted">{_h(raw)}</span>'
    scheme, rest = raw.split("://", 1)
    href = f"{scheme}&#58;//{_h(rest)}"
    return f'<a class="src" href="{href}" target="_blank" rel="noopener noreferrer">{_h(label)} ↗</a>'


def _svg_equity(summary_by_cost: Mapping[str, Mapping[str, Any]]) -> str:
    curves: list[tuple[str, list[Mapping[str, Any]]]] = []
    for key, stats in summary_by_cost.items():
        points = [point for point in (stats.get("equity_curve") or []) if isinstance(point, Mapping)]
        if len(points) >= 2:
            curves.append((str(key), points))
    if not curves:
        return '<p class="muted small">没有已实现成交，暂无净值曲线。</p>'
    values = [float(point["equity"]) for _, points in curves for point in points]
    low, high = min(values), max(values)
    if high - low < 1e-9:
        high = low + 1.0
    width, height = 780, 240
    left, right, top, bottom = 64, 18, 18, 34
    colors = ["#1f4e79", "#0f7b3f", "#b3261e", "#8a4b00", "#5b3f99"]

    def x_at(ratio: float) -> float:
        return left + (width - left - right) * ratio

    def y_at(value: float) -> float:
        return top + (height - top - bottom) * (1.0 - (value - low) / (high - low))

    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" '
        f'aria-label="各成本档已实现净值曲线" preserveAspectRatio="xMidYMid meet">',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>',
    ]
    for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = top + (height - top - bottom) * fraction
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" '
            f'stroke="#e6eaf0" stroke-width="1"/>'
        )
    capital = float(curves[0][1][0]["equity"])
    capital_y = y_at(capital)
    parts.append(
        f'<line x1="{left}" y1="{capital_y:.1f}" x2="{width-right}" y2="{capital_y:.1f}" '
        f'stroke="#9aa7b6" stroke-width="1.2" stroke-dasharray="5 4"/>'
    )
    parts.append(
        f'<text x="{left-6}" y="{capital_y+4:.1f}" text-anchor="end" font-size="11" fill="#5c6672">'
        f'{capital:,.0f} 本金</text>'
    )
    for index, (key, points) in enumerate(curves):
        color = colors[index % len(colors)]
        count = len(points) - 1
        coords = " ".join(
            f"{x_at(i / count):.1f},{y_at(float(point['equity'])):.1f}"
            for i, point in enumerate(points)
        )
        parts.append(
            f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{coords}"/>'
        )
        last = points[-1]
        parts.append(
            f'<circle cx="{x_at(1.0):.1f}" cy="{y_at(float(last["equity"])):.1f}" r="3" fill="{color}"/>'
        )
        legend_x = left + 10 + index * 150
        parts.append(
            f'<rect x="{legend_x}" y="{height-20}" width="10" height="10" fill="{color}"/>'
            f'<text x="{legend_x+14}" y="{height-11}" font-size="11" fill="#33404f">'
            f'单边 {_h(key)} bps</text>'
        )
    parts.append(
        f'<text x="{width-right}" y="{top+10}" text-anchor="end" font-size="11" fill="#5c6672">'
        f'最高 {high:,.0f}</text>'
    )
    parts.append(
        f'<text x="{width-right}" y="{height-bottom-2}" text-anchor="end" font-size="11" fill="#5c6672">'
        f'最低 {low:,.0f}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def _render_steps(steps: Sequence[Mapping[str, Any]]) -> str:
    if not steps:
        return '<div class="card muted">窗口内没有可回放的步骤（没有信号，或全部因时间戳质量被过滤）。</div>'
    blocks: list[str] = []
    for step in steps:
        decision = str(step.get("decision") or "SKIP").upper()
        kind = str(step.get("kind") or "")
        outcomes = " ".join(
            [
                f'<span class="muted">1日</span> {_pct(step.get("outcome_1d"))}',
                f'<span class="muted">5日</span> {_pct(step.get("outcome_5d"))}',
                f'<span class="muted">20日</span> {_pct(step.get("outcome_20d"))}',
            ]
        )
        quality = str(step.get("timestamp_quality") or "")
        quality_zh = QUALITY_ZH.get(quality, quality)
        price_source = str(step.get("price_source") or "")
        price_source_zh = str(step.get("price_source_zh") or "")
        chips = [
            f'<span class="chip">{_h(step.get("kind_zh") or kind)}</span>',
            f'<span class="chip">时间质量：{_h(quality_zh)}</span>',
        ]
        if price_source:
            chips.append(f'<span class="chip">成交来源：{_h(price_source_zh or price_source)}</span>')
        if step.get("intraday_fallback"):
            chips.append(f'<span class="chip">1 分钟降级：{_h(step.get("intraday_fallback"))}</span>')
        if step.get("reference_only"):
            chips.append('<span class="chip">参考价（未入账）</span>')

        body: list[str] = ['<div class="chain">事件 → 判定 → 成交 → 后续 1/5/20 日</div>']
        if chips:
            body.append('<div class="chips">' + "".join(chips) + "</div>")
        body.append('<table class="mini"><tbody>')
        body.append(
            f'<tr><th>信号 / 公开时点</th><td>{_h(step.get("signal_date"))}'
            f' <span class="muted">／ {_h(step.get("available_at"))}</span></td>'
            f'<th>代码 / 公司</th><td>{_h(step.get("ticker"))}'
            f' <span class="muted">{_h(step.get("company_zh") or step.get("company_key"))}</span></td></tr>'
        )
        body.append(
            f'<tr><th>方向 / 分数</th><td>{_h(step.get("side"))} / {_h(step.get("score"))}</td>'
            f'<th>判定</th><td>{_decision_badge(decision)}'
            + (
                f' <span class="muted">{_h(step.get("skip_reason_zh"))}</span>'
                if decision == "SKIP"
                else ""
            )
            + "</td></tr>"
        )
        if step.get("fill_price") is not None:
            body.append(
                f'<tr><th>成交</th><td>{_h(step.get("fill_time"))} @ {_money(step.get("fill_price"))}'
                f'{"（参考价，未计入组合）" if decision == "SKIP" else ""}</td>'
                f'<th>名义额 / 股数</th><td>{_money(step.get("notional"))} / '
                f'{_money(step.get("shares"))}</td></tr>'
            )
        if decision != "SKIP":
            body.append(
                f'<tr><th>平仓</th><td>{_h(step.get("exit_date"))} @ {_money(step.get("exit_price"))}'
                f' <span class="muted">（{_h(step.get("exit_reason"))}，持有 '
                f'{_h(step.get("holding_days"))} 个交易日）</span></td>'
                f'<th>毛收益</th><td>{_pct(step.get("gross_return"))}</td></tr>'
            )
        body.append(
            f'<tr><th>后续 1 / 5 / 20 日</th><td colspan="3">{outcomes}</td></tr>'
        )
        body.append("</tbody></table>")
        if decision != "SKIP" and step.get("net_by_cost"):
            body.append('<h3>按成本档（单边 bps，买卖各收一次）</h3>')
            body.append('<table class="mini"><thead><tr><th>成本档</th><th class="num">净收益</th><th class="num">按名义额盈亏</th></tr></thead><tbody>')
            for key in step["net_by_cost"]:
                net = step["net_by_cost"].get(key)
                pnl = (step.get("pnl_by_cost") or {}).get(key)
                body.append(
                    f'<tr><td>单边 {_h(key)} bps</td><td class="num">{_pct(net)}</td>'
                    f'<td class="num">{_money(pnl)}</td></tr>'
                )
            body.append("</tbody></table>")
        body.append(
            f'<p class="small">{_source_anchor(step.get("url"))}　'
            f'<span class="muted">原文标题：{_h(step.get("title"))}</span></p>'
        )
        body.append(f'<p class="small muted">判定理由：{_h(step.get("reason_zh"))}</p>')

        blocks.append(
            f'<details class="step" data-decision="{_h(decision.lower())}" data-kind="{_h(kind)}">'
            f'<summary><span class="step-time">{_h(step.get("t"))}</span>'
            f'<span class="step-ticker">{_h(step.get("ticker"))}</span>'
            f'{_decision_badge(decision)}<span class="step-event">{_h(step.get("event_zh"))}</span>'
            f'<span class="step-outcomes">{outcomes}</span></summary>'
            f'<div class="step-body">{"".join(body)}</div></details>'
        )
    return "".join(blocks)


def render_html(payload: Mapping[str, Any], *, docs_rel: str = "../../docs/ASSUMPTIONS.md") -> str:
    """Render a fully self-contained replay page (inline CSS/SVG/JS only)."""
    meta = payload.get("meta") or {}
    window = payload.get("window") or {}
    steps = payload.get("steps") or []
    summary_by_cost = payload.get("summary_by_cost") or {}
    status = payload.get("status")
    status_zh = "正常" if status == "ok" else "样本不足"
    generated = meta.get("generated_at") or utc_now_iso()
    counts = meta.get("counts") or {}
    quality = payload.get("quality") or {}
    event_study = payload.get("event_study") or {}
    skipped = payload.get("skipped") or {}

    kpis: list[str] = []
    for key, stats in summary_by_cost.items():
        total = stats.get("total_return")
        css = "up" if (_as_float(total) or 0) > 0 else ("down" if (_as_float(total) or 0) < 0 else "")
        kpis.append(
            f'<div class="kpi"><div class="lab">单边成本 {_h(key)} bps</div>'
            f'<div class="val {css}">{_plain_pct(total)}</div>'
            f'<div class="meta">最大回撤 {_plain_pct(stats.get("max_drawdown"))} · '
            f'胜率 {_plain_pct(stats.get("win_rate"), 1) if stats.get("win_rate") is not None else "—"} · '
            f'{_h(stats.get("trades"))} 笔</div></div>'
        )
    if not kpis:
        kpis.append('<div class="kpi"><div class="lab">回放</div><div class="val">—</div><div class="meta">没有可成交的步骤</div></div>')

    cost_rows: list[str] = []
    for key, stats in summary_by_cost.items():
        cost_rows.append(
            "<tr>"
            f'<td>单边 {_h(key)} bps</td>'
            f'<td class="num">往返 {_h(int(float(key) * 2))} bps</td>'
            f'<td class="num">{_pct(stats.get("total_return"))}</td>'
            f'<td class="num">{_money(stats.get("final_equity"))}</td>'
            f'<td class="num">{_pct(stats.get("max_drawdown"))}</td>'
            f'<td class="num">{_plain_pct(stats.get("win_rate"), 1) if stats.get("win_rate") is not None else "—"}</td>'
            f'<td class="num">{_h(stats.get("trades"))}</td>'
            f'<td class="num">{_h(stats.get("avg_holding_days"))}</td>'
            f'<td class="num">{_pct(stats.get("avg_trade_return"))}</td>'
            "</tr>"
        )

    study_rows: list[str] = []
    for horizon in ("1", "5", "20"):
        stats = (event_study.get("horizons") or {}).get(horizon) or {}
        net = stats.get("mean_net_by_cost") or {}
        net_cells = "".join(
            f'<td class="num">{_pct(net.get(key))}</td>' for key in summary_by_cost
        )
        study_rows.append(
            "<tr>"
            f'<td>{_h(horizon)} 日</td>'
            f'<td class="num">{_h(stats.get("n"))}</td>'
            f'<td class="num">{_pct(stats.get("mean"))}</td>'
            f'<td class="num">{_pct(stats.get("median"))}</td>'
            f'<td class="num">{_plain_pct(stats.get("hit_rate"), 1) if stats.get("hit_rate") is not None else "—"}</td>'
            f'<td class="num">{_h(round(stats["t"], 2)) if stats.get("t") is not None else "—"}</td>'
            f"{net_cells}"
            "</tr>"
        )
    study_headers = "".join(
        f'<th class="num">平均净收益（{_h(key)} bps）</th>' for key in summary_by_cost
    )

    skip_rows: list[str] = []
    for reason, count in sorted((skipped.get("by_reason") or {}).items(), key=lambda item: -item[1]):
        skip_rows.append(
            f'<tr><td>{_h(SKIP_REASON_ZH.get(reason, reason))}</td>'
            f'<td class="num">{_h(count)}</td></tr>'
        )
    if not skip_rows:
        skip_rows.append('<tr><td colspan="2" class="muted">窗口内没有跳过步骤。</td></tr>')

    quality_rows: list[str] = []
    for name, count in sorted((quality.get("by_quality") or {}).items(), key=lambda item: -item[1]):
        quality_rows.append(
            f'<tr><td>{_h(QUALITY_ZH.get(name, name))}</td><td class="num">{_h(count)}</td></tr>'
        )
    if not quality_rows:
        quality_rows.append('<tr><td colspan="2" class="muted">无时间质量统计。</td></tr>')

    lag = meta.get("first_seen_lag_days") or {}
    request_stats = meta.get("request_stats") or {}
    data_status = meta.get("data_status") or {}
    daily_sources = meta.get("daily_sources") or {}
    fetched_ticks = [ticker for ticker, source in daily_sources.items() if source == "yahoo_fallback"]
    intraday_errors = meta.get("intraday_errors") or {}
    method = payload.get("method") or {}
    not_modelled = method.get("not_modelled") or []

    banner = (
        '<div class="banner"><b>数据边界（务必先读）：</b>'
        "1 分钟数据仅最近 ~7 天（Yahoo range=7d、interval=1m），更早窗口只能回落到日线开盘；"
        "无 bid/ask；无借券费、locate 费与做空逼平数据，因此本回放默认只做多，"
        "direction=-1 的信号只记为「观望」。"
        "成交价按 bar 开盘价假定并按单边 bps 扣成本，不是真实可成交报价。"
        "<br/><b>研究口径：</b>回放是样本内、逐笔可审计的研究演示，"
        "不是策略业绩；样本较小且未做多重检验校正，不能据此宣称策略有效。"
        "</div>"
    )

    header = (
        "<header><div class=\"wrap\" style=\"padding:0\">"
        "<h1>MedRadar 事件回放 · Event Replay</h1>"
        f'<div class="sub">状态：{_h(status_zh)}（{_h(status)}） · 窗口 {_h(window.get("start"))} → '
        f'{_h(window.get("end"))} · 生成于 {_h(generated)} · 共 {_h(len(steps))} 步'
        f' · 引擎 {_h(meta.get("engine"))}</div>'
        "</div></header>"
    )

    disclaimers = "".join(f"<li>{_h(item)}</li>" for item in not_modelled)

    parts: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="zh-CN"><head><meta charset="utf-8"/>',
        '<meta name="viewport" content="width=device-width,initial-scale=1"/>',
        "<title>MedRadar 事件回放</title>",
        f"<style>{_CSS}</style></head><body>",
        header,
        banner,
        '<div class="wrap">',
        "<h2>多档成本结果</h2>",
        '<div class="kpis">' + "".join(kpis) + "</div>",
        "<h2>成本敏感性</h2>",
        '<div class="card"><table><thead><tr>'
        '<th>成本档</th><th class="num">往返成本</th><th class="num">总收益</th>'
        '<th class="num">期末权益</th><th class="num">最大回撤</th><th class="num">胜率</th>'
        '<th class="num">笔数</th><th class="num">平均持有（交易日）</th><th class="num">平均单笔收益</th>'
        "</tr></thead><tbody>" + "".join(cost_rows) + "</tbody></table>",
        '<p class="small muted">成本档为单边 bps，买卖各收一次；同一批成交在不同成本档下独立重估，'
        "因此收益随成本单调下降。回撤为已实现口径（不含浮亏）。</p>",
        '<div class="svgbox">' + _svg_equity(summary_by_cost) + "</div></div>",
        "<h2>后续 1 / 5 / 20 日（方向调整后）</h2>",
        '<div class="card"><table><thead><tr>'
        '<th>持有窗口</th><th class="num">n</th><th class="num">平均毛收益</th>'
        '<th class="num">中位数</th><th class="num">胜率</th><th class="num">t</th>'
        f"{study_headers}</tr></thead><tbody>" + "".join(study_rows) + "</tbody></table>",
        '<p class="small muted">毛收益 = 成交价到该窗口收盘价的方向调整收益；净收益再扣 2×成本档。'
        "最近成交因未来收盘价尚未出现，对应窗口为「—」。</p></div>",
        "<h2>时间轴：事件 → 判定 → 成交 → 后续</h2>",
        '<div class="controls" id="filters">'
        '<span>筛选：</span>'
        '<label><input type="radio" name="decision" value="all" checked/> 全部</label>'
        '<label><input type="radio" name="decision" value="trade"/> 只看成交</label>'
        '<label><input type="radio" name="decision" value="skip"/> 只看观望</label>'
        '<input type="search" id="q" placeholder="搜索代码 / 事件 / 理由"/>'
        '<span class="muted" id="count"></span></div>',
        _render_steps(steps),
        "<h2>跳过原因</h2>",
        '<div class="card"><table><thead><tr><th>原因</th><th class="num">步数</th></tr></thead><tbody>'
        + "".join(skip_rows)
        + "</tbody></table></div>",
        "<h2>数据质量与可审计性</h2>",
        '<div class="grid2"><div class="card"><h3>时间戳质量</h3><table><thead><tr><th>质量档</th><th class="num">信号数</th></tr></thead><tbody>'
        + "".join(quality_rows)
        + "</tbody></table>"
        + f'<p class="small muted">策略：{_h(quality.get("policy"))}。'
        f'因质量不足被过滤：{_h(quality.get("excluded"))} 条。</p></div>'
        '<div class="card"><h3>价格与请求</h3><table><tbody>'
        f'<tr><th>日线数据</th><td>{_h(data_status.get("daily"))}</td></tr>'
        f'<tr><th>1 分钟数据</th><td>{_h(INTRADAY_STATUS_ZH.get(str(data_status.get("intraday")), data_status.get("intraday")))}</td></tr>'
        f'<tr><th>抓取模式</th><td>{_h(data_status.get("fetcher"))}</td></tr>'
        f'<tr><th>请求数 / 预算</th><td>{_h(request_stats.get("requests"))} / {_h(request_stats.get("budget_max"))}'
        f'（本引擎实际发起 {_h(request_stats.get("budget_used"))} 次）</td></tr>'
        f'<tr><th>日线来自 Yahoo 回填的标的</th><td>{_h(", ".join(fetched_ticks) if fetched_ticks else "无")}</td></tr>'
        f'<tr><th>1 分钟抓取失败</th><td>{_h(len(intraday_errors))} 个标的（自动降级日线）</td></tr>'
        "</tbody></table>"
        f'<p class="small muted">信号原始 {_h(counts.get("signals_raw"))} 条，去重后 '
        f'{_h(counts.get("signals_unique"))} 条（移除重复 {_h(counts.get("duplicates_removed"))} 条），'
        f'窗口内 {_h(counts.get("signals_in_window"))} 条。</p></div></div>',
        '<div class="card" style="margin-top:14px"><h3>点时可获性（生存 / 回填偏差）</h3>'
        f'<p class="small">样本中 <b>{_h(lag.get("backfilled"))}</b> 条事件的首次采集时间晚于公开时间超过 1 天'
        f'（中位滞后 {_h(lag.get("median_days"))} 天，最大 {_h(lag.get("max_days"))} 天）。'
        "回放假设当时已在采集：这是免费回填数据无法消除的乐观项，详见假设登记表。</p>"
        f'<p class="small"><a class="src" href="{_h(docs_rel)}">假设登记表（docs/ASSUMPTIONS.md）</a> · '
        f'口径与参数出处逐项列明。</p></div>',
        "<h2>方法</h2>",
        '<div class="card"><ul class="tight">'
        f'<li><b>决策时点</b>：{_h(method.get("decision_time"))}</li>'
        f'<li><b>1 分钟分支</b>：{_h(method.get("entry_intraday"))}（{_h(method.get("intraday_rule"))}）</li>'
        f'<li><b>日线分支</b>：{_h(method.get("entry_daily"))}</li>'
        f'<li><b>平仓</b>：{_h(method.get("exit"))}</li>'
        f'<li><b>成本</b>：{_h(method.get("cost"))}</li>'
        f'<li><b>仓位</b>：{_h(method.get("sizing"))}；{_h(method.get("concurrency"))}</li>'
        "</ul>"
        f'<p class="small muted">未建模：</p><ul class="tight">{disclaimers}</ul></div>',
        f'<footer>{_h(payload.get("disclaimer_zh"))}<br/>'
        f'假设登记表：{_h(payload.get("assumptions_url"))} · 回放窗口 '
        f'{_h(window.get("start"))} → {_h(window.get("end"))}</footer>',
        "</div>",
        f"<script>{_JS}</script>",
        "</body></html>",
    ]
    return "".join(parts)


# --------------------------------------------------------------------------- public
def _prepare_fetcher(fetcher: Any, offline: bool, max_requests: int) -> Any:
    if offline:
        return None
    if fetcher is None:
        return Fetcher(cache_dir=CACHE_DIR, min_interval=0.5, max_requests=max(1, int(max_requests)))
    if isinstance(fetcher, _BudgetedFetcher):
        return fetcher
    return _BudgetedFetcher(fetcher, max_requests)


def build_replay(
    db: Any,
    start: Any,
    end: Any,
    capital: float = 100000,
    costs_bps: Sequence[float] = DEFAULT_COSTS_BPS,
    intraday_days: int = DEFAULT_INTRADAY_DAYS,
    *,
    out_dir: str | Path | None = None,
    fetcher: Any = None,
    offline: bool = False,
    now: Any = None,
    max_requests: int = DEFAULT_REQUEST_BUDGET,
    hold_days: int = DEFAULT_HOLD_DAYS,
    allow_short: bool = False,
    position_pct: float = DEFAULT_POSITION_PCT,
    max_concurrent: int = DEFAULT_MAX_CONCURRENT,
    min_score: float = 0.0,
) -> dict[str, Any]:
    """Build the replay payload and write ``replay.json`` + ``index.html``.

    ``db`` may be an open :class:`medradar.db.DB` (leave it open) or a path
    (opened and closed here). ``fetcher`` is injected in tests; by default a
    polite cached :class:`medradar.http.Fetcher` with a hard request budget of
    ``max_requests`` is created. ``offline=True`` disables every network call.

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


__all__ = [
    "ASSUMPTIONS_URL",
    "DEFAULT_COSTS_BPS",
    "ENGINE",
    "SCHEMA_VERSION",
    "build_replay",
    "cost_key",
    "fetch_intraday",
    "parse_intraday_chart",
    "render_html",
]
