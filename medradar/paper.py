"""Long-only paper trading over MedRadar signals (``medradar trade``).

Position rules (v1, mirrored into ``out/trading.json["method"]``)
-----------------------------------------------------------------
* **Long only.** ``direction = -1`` signals are counted as skipped, never
  shorted. Short-side borrow fees and merger squeeze-outs are NOT modelled.
* Signals are processed in signal-date order (ties broken by score, then
  ticker) and enter at the **open of the first trading day strictly after the
  signal date** - never at the signal-day close, which would be look-ahead.
* At most one open position per ticker (no pyramiding).
* Position size <= **5% of prior-close equity**; total track exposure <= **25%
  of prior-close equity**; no leverage. Sizing uses only prices known before
  the entry session.
* Exit at the close of the **60th trading day after entry**, or at the close on
  which ``close <= entry * (1 - 20%)`` (stop checked on daily closes; intraday
  gaps and overnight fills are not modelled), or at data end if neither fired.
* Costs: **20 bps + USD 1 per fill**, charged on both entry and exit. The
  simulation allows fractional shares and has no lot-size or market-impact
  model.
* Daily mark-to-market uses adjusted prices; the equity curve is
  ``cash + sum(shares * last available adjusted close)``.

Honest limitations (also returned in the payload)
-------------------------------------------------
This is an **academic signal-validation and simulated-book exercise, not
investment advice**. It does not model short borrow fees, merger squeeze-outs,
taxes, financing, dilution, liquidity, or intraday stop fills. A delisted or
acquired ticker is closed at its last available close (``reason = "end"``)
because the merger/squeeze-out path is out of scope for v1.
"""

from __future__ import annotations

import bisect
import csv
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .db import DB
from .eventstudy import (
    ingest_signals,
    load_signals,
    normalize_signal_kinds,
    run_event_study,
)
from .prices import load_series
from .util import ensure_dir, sha1, today_utc, utc_now_iso, write_json

ENGINE = "long_only_v1"
COST_BPS = 20.0
COST_FIXED = 1.0
HOLD_DAYS = 60
STOP_LOSS = -0.20
MAX_POSITION_PCT = 0.05
MAX_TRACK_PCT = 0.25
MIN_NOTIONAL = 1.0
TRADING_DAYS_PER_YEAR = 252
EQUITY_SAMPLE_STEP = 5  # trading days between equity_curve points (weekly-ish)

DISCLAIMER_ZH = (
    "模拟研究，非投资建议；未建模做空借券费与并购逼平。"
    "v1 仅做多：direction=-1 的信号不参与模拟。"
)

TRADE_CSV_FIELDS = (
    "trade_id",
    "signal_id",
    "kind",
    "ticker",
    "track_id",
    "side",
    "entry_date",
    "entry_price",
    "exit_date",
    "exit_price",
    "shares",
    "entry_notional",
    "exit_notional",
    "costs",
    "pnl",
    "ret",
    "holding_days",
    "reason",
)
EQUITY_CSV_FIELDS = ("date", "equity", "cash", "exposure", "drawdown")


# --------------------------------------------------------------------------- method
def _method() -> dict[str, Any]:
    return {
        "version": ENGINE,
        "long_only": True,
        "direction_filter": "direction=-1 skipped; v1 never shorts",
        "entry": "open of the first trading day strictly after signal_date",
        "sizing_basis": "prior close equity",
        "max_position_pct": MAX_POSITION_PCT,
        "max_track_pct": MAX_TRACK_PCT,
        "one_position_per_ticker": True,
        "hold_days": HOLD_DAYS,
        "stop_loss": STOP_LOSS,
        "exit_basis": "daily adjusted close (no intraday stop modelling)",
        "cost_bps": COST_BPS,
        "cost_fixed_usd": COST_FIXED,
        "cost_charged_per_fill": True,
        "fractional_shares": True,
        "benchmark": "SPY",
        "event_study_sample": "all directional signals of the selected kinds; direction=-1 sign-flipped",
        "not_modelled": [
            "short borrow fees",
            "merger squeeze-outs / delisting cash-out mechanics",
            "taxes, financing, dilution, liquidity/market impact",
            "intraday gap fills for the -20% stop",
        ],
    }


# --------------------------------------------------------------------------- helpers
def _first_entry_index(series, calendar: Sequence[str], signal_date: str) -> int | None:
    """First calendar session strictly after ``signal_date`` where the stock opens."""
    start = bisect.bisect_right(calendar, signal_date)
    for index in range(start, len(calendar)):
        price = series.open(calendar[index])
        if price is not None and price > 0:
            return index
    return None


def _mark_price(position: Mapping[str, Any], series, day: str | None) -> float:
    price: float | None = None
    if day is not None:
        price, _ = series.last_close_on_or_before(day)
    if price is None:
        price = position["entry_price"]
    return float(price)


def _close_trade(
    position: Mapping[str, Any],
    exit_date: str,
    exit_index: int,
    exit_price: float,
    exit_notional: float,
    exit_cost: float,
    reason: str,
) -> dict[str, Any]:
    pnl = exit_notional - position["entry_notional"] - position["entry_cost"] - exit_cost
    return {
        "trade_id": position["trade_id"],
        "signal_id": position["signal_id"],
        "kind": position["kind"],
        "ticker": position["ticker"],
        "track_id": position["track_id"],
        "side": "long",
        "entry_date": position["entry_date"],
        "entry_price": position["entry_price"],
        "entry_notional": position["entry_notional"],
        "entry_cost": position["entry_cost"],
        "exit_date": exit_date,
        "exit_price": float(exit_price),
        "exit_notional": float(exit_notional),
        "exit_cost": float(exit_cost),
        "shares": position["shares"],
        "pnl": pnl,
        "ret": pnl / position["entry_notional"] if position["entry_notional"] else 0.0,
        "holding_days": int(exit_index - position["entry_idx"]),
        "reason": reason,
    }


def _sharpe(equity_rows: Sequence[Mapping[str, Any]]) -> float | None:
    returns = [
        current["equity"] / previous["equity"] - 1.0
        for previous, current in zip(equity_rows, equity_rows[1:])
        if previous["equity"]
    ]
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
    if variance <= 0:
        return None
    return mean / math.sqrt(variance) * math.sqrt(TRADING_DAYS_PER_YEAR)


def _by_kind(trades: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for trade in trades:
        grouped[trade["kind"] or "unknown"].append(trade)
    result: dict[str, dict[str, Any]] = {}
    for kind in sorted(grouped):
        items = grouped[kind]
        returns = [float(item["ret"]) for item in items]
        result[kind] = {
            "trades": len(items),
            "win_rate": sum(1 for value in returns if value > 0) / len(returns),
            "avg_return": sum(returns) / len(returns),
            "total_pnl": sum(float(item["pnl"]) for item in items),
            "mean_holding_days": sum(int(item["holding_days"]) for item in items) / len(items),
        }
    return result


def _attribution(by_kind: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "kind": kind,
            "trades": int(stats["trades"]),
            "avg_return": stats["avg_return"],
            "total_pnl": stats["total_pnl"],
        }
        for kind, stats in by_kind.items()
    ]


def _equity_curve(equity_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Down-sample to ~weekly points while keeping the first and last bars."""
    if not equity_rows:
        return []
    indices = list(range(0, len(equity_rows), EQUITY_SAMPLE_STEP))
    if indices[-1] != len(equity_rows) - 1:
        indices.append(len(equity_rows) - 1)
    return [{"date": equity_rows[i]["date"], "equity": equity_rows[i]["equity"]} for i in indices]


def _embed_event_study(study: Mapping[str, Any], benchmark: str = "SPY") -> dict[str, Any]:
    """Flatten :func:`run_event_study` into the SCHEMA §7.1 shape."""
    if study.get("status") != "ok":
        return {"benchmark": study.get("benchmark") or benchmark, "horizons": {}, "curve": []}
    horizons: dict[str, dict[str, Any]] = {}
    for key, stats in (study.get("all") or {}).items():
        ci = stats.get("ci95")
        horizons[str(key)] = {
            "n": stats.get("n") or 0,
            "mean_ar": stats.get("mean"),
            "median_ar": stats.get("median"),
            "t": stats.get("t"),
            "ci95": [ci.get("lo"), ci.get("hi")] if ci else None,
            "hit_rate": stats.get("hit_rate"),
        }
    source = study.get("curve_signal_relative") or study.get("curve") or {}
    days = source.get("days") or []
    values = source.get("all") or []
    curve = [
        {"t": int(day), "ar": value}
        for day, value in zip(days, values)
        if value is not None
    ]
    return {
        "benchmark": study.get("benchmark") or benchmark,
        "horizons": horizons,
        "curve": curve,
    }


def _benchmark_total_return(spy, start: str | None, end: str | None) -> float | None:
    if spy is None or not start or not end:
        return None
    start_close, _ = spy.last_close_on_or_before(start)
    end_close, _ = spy.last_close_on_or_before(end)
    if not start_close or not end_close:
        return None
    return end_close / start_close - 1.0


# --------------------------------------------------------------------------- payload
def _insufficient_payload(
    reason: str,
    capital: float,
    kinds: tuple[str, ...] | None,
    skipped: Mapping[str, Any] | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    skipped_dict = dict(skipped or {})
    return {
        "status": "insufficient_data",
        "as_of": as_of or today_utc().isoformat(),
        "reason": reason,
        "meta": {
            "generated_at": utc_now_iso(),
            "capital": float(capital),
            "signal_kind": list(kinds) if kinds else None,
            "engine": ENGINE,
            "disclaimer_zh": DISCLAIMER_ZH,
            "status": "insufficient_data",
            "reason": reason,
            "skipped": skipped_dict,
        },
        "method": _method(),
        "summary": {
            "total_return": None,
            "final_equity": None,
            "max_drawdown": None,
            "win_rate": None,
            "avg_trade_return": None,
            "sharpe": None,
            "n_trades": None,
            "trades": None,
            "n_signals": skipped_dict.get("signals"),
            "benchmark": "SPY",
            "start": None,
            "end": None,
        },
        "equity_curve": [],
        "by_kind": {},
        "attribution": [],
        "event_study": {"benchmark": "SPY", "horizons": {}, "curve": []},
        "trades": [],
        "benchmark": {"ticker": "SPY", "total_return": None},
        "disclaimer_zh": DISCLAIMER_ZH,
    }


# --------------------------------------------------------------------------- simulate
def _simulate(db, capital: float, kinds: tuple[str, ...] | None) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    signals, skipped = load_signals(db, kinds)
    skipped = Counter(skipped)
    skipped["signals"] = len(signals)
    if not signals:
        return _insufficient_payload("no_signals", capital, kinds, skipped), [], []

    tickers = sorted({signal["ticker"] for signal in signals})
    series: dict[str, Any] = {}
    for ticker in tickers:
        loaded = load_series(db, ticker)
        if loaded is not None:
            series[ticker] = loaded
    if not series:
        return _insufficient_payload("no_prices", capital, kinds, skipped), [], []

    spy = load_series(db, "SPY")
    if spy is not None:
        series.setdefault("SPY", spy)
        calendar = list(spy.dates)
    else:
        calendar = sorted({day for ticker in tickers if ticker in series for day in series[ticker].dates})
    if not calendar:
        return _insufficient_payload("no_prices", capital, kinds, skipped), [], []
    as_of = calendar[-1]

    scheduled: list[dict[str, Any]] = []
    for signal in sorted(
        signals,
        key=lambda item: (item["signal_date"], -item["score"], item["ticker"], item["signal_id"]),
    ):
        if signal["direction"] < 0:
            skipped["short_not_supported"] += 1
            continue
        ticker_series = series.get(signal["ticker"])
        if ticker_series is None:
            skipped["no_prices"] += 1
            continue
        entry_idx = _first_entry_index(ticker_series, calendar, signal["signal_date"])
        if entry_idx is None:
            skipped["no_entry_bar"] += 1
            continue
        scheduled.append({**signal, "entry_idx": entry_idx})
    if not scheduled:
        reason = "no_entry_bars"
        if skipped["short_not_supported"] and not (
            skipped["no_prices"] or skipped["no_entry_bar"]
        ):
            reason = "short_not_supported"
        return _insufficient_payload(reason, capital, kinds, skipped, as_of), [], []

    entry_by_index: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for item in scheduled:
        entry_by_index[item["entry_idx"]].append(item)
    first_index = min(entry_by_index)
    last_entry_index = max(entry_by_index)
    last_index = min(len(calendar) - 1, last_entry_index + HOLD_DAYS + 5)

    cash = float(capital)
    positions: list[dict[str, Any]] = []
    closed: list[dict[str, Any]] = []
    equity_rows: list[dict[str, Any]] = []
    peak = float(capital)

    for index in range(first_index, last_index + 1):
        day = calendar[index]
        previous_day = calendar[index - 1] if index > 0 else None
        equity_prev = equity_rows[-1]["equity"] if equity_rows else float(capital)

        # --- entries at the open (sized from the prior close, no look-ahead) ---
        for item in entry_by_index.get(index, []):
            ticker = item["ticker"]
            if any(position["ticker"] == ticker for position in positions):
                skipped["already_open"] += 1
                continue
            ticker_series = series[ticker]
            entry_price = ticker_series.open(day)
            if entry_price is None or entry_price <= 0:
                skipped["no_entry_bar"] += 1
                continue
            track = item["track_id"] or ""
            track_exposure = sum(
                position["shares"] * _mark_price(position, series[position["ticker"]], previous_day)
                for position in positions
                if (position["track_id"] or "") == track
            )
            room = min(
                MAX_POSITION_PCT * equity_prev,
                MAX_TRACK_PCT * equity_prev - track_exposure,
                (cash - COST_FIXED) / (1.0 + COST_BPS / 10000.0),
            )
            if room <= 0 or room < MIN_NOTIONAL:
                skipped["no_capacity"] += 1
                continue
            shares = room / entry_price
            entry_cost = COST_FIXED + COST_BPS / 10000.0 * room
            cash -= room + entry_cost
            positions.append(
                {
                    "trade_id": sha1(f"{item['signal_id']}|{day}|{ticker}")[:16],
                    "signal_id": item["signal_id"],
                    "kind": item["kind"],
                    "ticker": ticker,
                    "track_id": item["track_id"],
                    "entry_idx": index,
                    "entry_date": day,
                    "entry_price": float(entry_price),
                    "entry_notional": float(room),
                    "entry_cost": float(entry_cost),
                    "shares": float(shares),
                }
            )

        # --- exits at the close ---
        for position in list(positions):
            ticker_series = series[position["ticker"]]
            close_price = ticker_series.close(day)
            if close_price is None:
                continue
            reason = None
            if close_price <= position["entry_price"] * (1.0 + STOP_LOSS):
                reason = "stop"
            elif index - position["entry_idx"] >= HOLD_DAYS:
                reason = "time_exit"
            if reason is None:
                continue
            exit_notional = position["shares"] * close_price
            exit_cost = COST_FIXED + COST_BPS / 10000.0 * exit_notional
            cash += exit_notional - exit_cost
            closed.append(
                _close_trade(position, day, index, close_price, exit_notional, exit_cost, reason)
            )
            positions.remove(position)

        # --- daily mark to market ---
        exposure = sum(
            position["shares"] * _mark_price(position, series[position["ticker"]], day)
            for position in positions
        )
        equity = cash + exposure
        peak = max(peak, equity)
        drawdown = equity / peak - 1.0 if peak > 0 else 0.0
        equity_rows.append(
            {
                "date": day,
                "equity": equity,
                "cash": cash,
                "exposure": exposure,
                "drawdown": drawdown,
            }
        )

    # --- force-close whatever is still open at the data end ---
    if positions:
        end_index = last_index
        end_day = calendar[end_index]
        for position in list(positions):
            ticker_series = series[position["ticker"]]
            exit_price, _ = ticker_series.last_close_on_or_before(end_day)
            if exit_price is None:
                exit_price = position["entry_price"]
            exit_notional = position["shares"] * exit_price
            exit_cost = COST_FIXED + COST_BPS / 10000.0 * exit_notional
            cash += exit_notional - exit_cost
            closed.append(
                _close_trade(
                    position, end_day, end_index, exit_price, exit_notional, exit_cost, "end"
                )
            )
            positions.remove(position)
        last_row = equity_rows[-1]
        last_row["cash"] = cash
        last_row["exposure"] = 0.0
        last_row["equity"] = cash
        last_row["drawdown"] = cash / peak - 1.0 if peak > 0 else 0.0

    # Trim the flat tail that only exists because the last signal needed a 60-day window.
    last_activity = max((trade["exit_date"] for trade in closed), default=None)
    if last_activity:
        equity_rows = [row for row in equity_rows if row["date"] <= last_activity]

    # -------------------------------------------------------------------- report
    study: dict[str, Any]
    try:
        study = run_event_study(db, benchmark="SPY", signal_kind=kinds)
    except Exception as exc:  # pragma: no cover - a study bug must not sink the book
        study = {"status": "error", "reason": f"{type(exc).__name__}: {exc}"}
    event_study = _embed_event_study(study)
    event_study_status = study.get("status") or "unknown"

    final_equity = float(equity_rows[-1]["equity"])
    total_return = final_equity / capital - 1.0 if capital else None
    max_drawdown = min((float(row["drawdown"]) for row in equity_rows), default=0.0)
    returns = [float(trade["ret"]) for trade in closed]
    win_rate = (sum(1 for value in returns if value > 0) / len(returns)) if returns else None
    avg_trade_return = (sum(returns) / len(returns)) if returns else None
    by_kind = _by_kind(closed)
    attribution = _attribution(by_kind)
    percentiles = _equity_curve(equity_rows)
    benchmark_return = _benchmark_total_return(spy, equity_rows[0]["date"], equity_rows[-1]["date"])

    payload = {
        "status": "ok",
        "as_of": as_of,
        "meta": {
            "generated_at": utc_now_iso(),
            "capital": float(capital),
            "signal_kind": list(kinds) if kinds else None,
            "engine": ENGINE,
            "disclaimer_zh": DISCLAIMER_ZH,
            "status": "ok",
            "n_signals": len(signals),
            "n_tradable_signals": len(scheduled),
            "skipped": dict(skipped),
            "event_study_status": event_study_status,
        },
        "method": _method(),
        "summary": {
            "total_return": total_return,
            "final_equity": final_equity,
            "max_drawdown": max_drawdown,
            "win_rate": win_rate,
            "avg_trade_return": avg_trade_return,
            "sharpe": _sharpe(equity_rows),
            "n_trades": len(closed),
            "trades": len(closed),
            "n_signals": len(signals),
            "benchmark": "SPY",
            "start": equity_rows[0]["date"],
            "end": equity_rows[-1]["date"],
        },
        "equity_curve": percentiles,
        "by_kind": by_kind,
        "attribution": attribution,
        "event_study": event_study,
        "trades": [
            {
                "ticker": trade["ticker"],
                "entry_date": trade["entry_date"],
                "entry_price": trade["entry_price"],
                "exit_date": trade["exit_date"],
                "exit_price": trade["exit_price"],
                "ret": trade["ret"],
                "pnl": trade["pnl"],
                "reason": trade["reason"],
            }
            for trade in closed
        ],
        "benchmark": {"ticker": "SPY", "total_return": benchmark_return},
        "disclaimer_zh": DISCLAIMER_ZH,
    }
    return payload, closed, equity_rows


# --------------------------------------------------------------------------- persistence
def _write_csv(path: Path, fields: Sequence[str], rows: Iterable[Sequence[Any]]) -> None:
    ensure_dir(path.parent)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(fields)
        for row in rows:
            writer.writerow(row)


def _write_outputs(out_dir: Path, payload: Mapping[str, Any], trades: Sequence[Mapping[str, Any]], equity_rows: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    ensure_dir(out_dir)
    trading_path = write_json(out_dir / "trading.json", payload)
    trades_path = out_dir / "paper_trades.csv"
    equity_path = out_dir / "paper_equity.csv"
    _write_csv(
        trades_path,
        TRADE_CSV_FIELDS,
        [
            (
                trade["trade_id"],
                trade["signal_id"],
                trade["kind"],
                trade["ticker"],
                trade["track_id"],
                trade["side"],
                trade["entry_date"],
                trade["entry_price"],
                trade["exit_date"],
                trade["exit_price"],
                trade["shares"],
                trade["entry_notional"],
                trade["exit_notional"],
                trade["entry_cost"] + trade["exit_cost"],
                trade["pnl"],
                trade["ret"],
                trade["holding_days"],
                trade["reason"],
            )
            for trade in trades
        ],
    )
    _write_csv(
        equity_path,
        EQUITY_CSV_FIELDS,
        [
            (
                row["date"],
                row["equity"],
                row["cash"],
                row["exposure"],
                row["drawdown"],
            )
            for row in equity_rows
        ],
    )
    return {
        "trading": str(trading_path),
        "trades_csv": str(trades_path),
        "equity_csv": str(equity_path),
    }


def _persist(db, trades: Sequence[Mapping[str, Any]], equity_rows: Sequence[Mapping[str, Any]]) -> None:
    """Replace the previous simulated book in ``paper_trades`` / ``paper_equity``."""
    db.execute("DELETE FROM paper_trades")
    db.execute("DELETE FROM paper_equity")
    stamp = utc_now_iso()
    if trades:
        db.executemany(
            "INSERT OR REPLACE INTO paper_trades(trade_id, signal_id, ticker, side,"
            " entry_date, entry_price, exit_date, exit_price, shares, pnl, ret,"
            " reason, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    trade["trade_id"],
                    trade["signal_id"],
                    trade["ticker"],
                    trade["side"],
                    trade["entry_date"],
                    trade["entry_price"],
                    trade["exit_date"],
                    trade["exit_price"],
                    trade["shares"],
                    trade["pnl"],
                    trade["ret"],
                    trade["reason"],
                    stamp,
                )
                for trade in trades
            ],
        )
    if equity_rows:
        db.executemany(
            "INSERT OR REPLACE INTO paper_equity(date, equity, cash, exposure, drawdown)"
            " VALUES (?,?,?,?,?)",
            [
                (row["date"], row["equity"], row["cash"], row["exposure"], row["drawdown"])
                for row in equity_rows
            ],
        )
    db.commit()


# --------------------------------------------------------------------------- public
def run_paper(
    db_path: str | Path,
    capital: float = 100000.0,
    out_dir: str | Path = "out",
    signal_kind: Any = None,
) -> dict[str, Any]:
    """Simulate the long-only paper book and write the trading artefacts.

    Writes ``out/trading.json`` (SCHEMA §7.1), ``out/paper_trades.csv``,
    ``out/paper_equity.csv`` and refreshes the ``paper_trades`` /
    ``paper_equity`` SQLite tables. Missing database, signals or prices produce
    an ``insufficient_data`` payload instead of an exception. Returns a compact
    summary dict (the full payload lives in ``trading.json``).
    """
    capital = float(capital)
    out_path = Path(out_dir)
    kinds = normalize_signal_kinds(signal_kind)
    if not Path(db_path).exists():
        payload = _insufficient_payload("db_missing", capital, kinds)
        files = _write_outputs(out_path, payload, [], [])
        return {
            "status": payload["status"],
            "reason": payload.get("reason"),
            "files": files,
            "summary": payload["summary"],
        }

    with DB(db_path) as db:
        payload, trades, equity_rows = _simulate(db, capital, kinds)
        _persist(db, trades, equity_rows)

    files = _write_outputs(out_path, payload, trades, equity_rows)
    return {
        "status": payload["status"],
        "reason": payload.get("reason"),
        "as_of": payload.get("as_of"),
        "signal_kind": list(kinds) if kinds else None,
        "files": files,
        "summary": payload["summary"],
        "attribution": payload.get("attribution") or [],
        "event_study_status": (payload.get("meta") or {}).get("event_study_status"),
        "disclaimer_zh": DISCLAIMER_ZH,
    }
