"""Data-scale statistics for ``medradar stats`` (CLI wiring lives in ``__main__``).

One read-only pass over SQLite that answers "how much data do we actually have,
from where, over which years, and where are the holes?". It is deliberately
tolerant: an empty database, a database missing newer tables, or a path that has
not been collected yet all return a report instead of raising.

The returned payload is JSON-serializable and stable enough to feed
``docs/DATA.md``'s growth table (see :func:`append_growth_row`).

    from medradar.db import DB
    from medradar.stats_cmd import data_stats

    with DB("data/medradar.sqlite") as db:
        stats = data_stats(db)

``data_stats`` accepts either an open :class:`medradar.db.DB` (left open) or a
path (opened and closed here; a missing path is reported, never created).
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from .util import utc_now_iso

#: Tables whose row counts are reported under ``payload["tables"]``.
#: ``runs``/``llm_verdicts`` are not in ``DB.table_count``'s whitelist, so counts
#: are read with plain SQL on purpose.
COUNTED_TABLES = (
    "events",
    "companies",
    "tracks",
    "product_codes",
    "prices",
    "signals",
    "paper_trades",
    "paper_equity",
    "live_alerts",
    "paper_orders",
    "positions",
    "live_equity",
    "runs",
    "llm_verdicts",
)

#: Marker that closes the growth table in ``docs/DATA.md``.
GROWTH_MARKER = "<!-- growth:end -->"

_ISO_DATE_GLOB = "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*'"
_YEAR_GLOB = "'[0-9][0-9][0-9][0-9]-*'"


# ------------------------------------------------------------------------ helpers
def human_size(num_bytes: Any) -> str:
    """Render a byte count as ``512 B`` / ``1.5 KiB`` / ``328.5 MiB``."""
    try:
        size = float(num_bytes or 0)
    except (TypeError, ValueError):
        return "0 B"
    if size <= 0:
        return "0 B"
    if size < 1024:
        return f"{int(round(size))} B"
    for unit in ("KiB", "MiB", "GiB", "TiB"):
        size /= 1024.0
        if size < 1024 or unit == "TiB":
            return f"{size:.1f} {unit}"
    return f"{size:.1f} TiB"


def _scalar(db: Any, sql: str, params: tuple[Any, ...] = (), default: Any = None,
            errors: list[str] | None = None, tag: str = "") -> Any:
    try:
        return db.scalar(sql, params, default)
    except Exception as exc:  # tolerant: old/partial DBs must not crash stats
        if errors is not None:
            errors.append(f"{tag or sql[:40]}: {type(exc).__name__}: {exc}")
        return default


def _query(db: Any, sql: str, params: tuple[Any, ...] = (),
           errors: list[str] | None = None, tag: str = "") -> list[dict[str, Any]]:
    try:
        return list(db.query(sql, params))
    except Exception as exc:
        if errors is not None:
            errors.append(f"{tag or sql[:40]}: {type(exc).__name__}: {exc}")
        return []


def _counter(rows: list[Mapping[str, Any]], key: str, value: str = "n") -> dict[str, int]:
    """Turn ``[{key: k, value: v}]`` into an ordered ``{k: v}`` dict."""
    return {str(row[key]): int(row[value] or 0) for row in rows}


def format_rate(part: Any, total: Any) -> float:
    try:
        num, den = float(part or 0), float(total or 0)
    except (TypeError, ValueError):
        return 0.0
    if den <= 0:
        return 0.0
    return round(num / den, 3)


def _db_file_info(path: Path | None) -> dict[str, Any]:
    info: dict[str, Any] = {
        "path": str(path) if path else "",
        "exists": bool(path and path.exists()),
        "bytes": 0,
        "size_human": "0 B",
        "wal_bytes": 0,
        "shm_bytes": 0,
    }
    if path is None or not path.exists():
        return info
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    info["bytes"] = size
    info["size_human"] = human_size(size)
    for suffix, key in (("-wal", "wal_bytes"), ("-shm", "shm_bytes")):
        sibling = path.with_name(path.name + suffix)
        try:
            info[key] = sibling.stat().st_size if sibling.exists() else 0
        except OSError:
            info[key] = 0
    return info


def _empty_report(path: Path | None, status: str, errors: list[str]) -> dict[str, Any]:
    return {
        "generated_at": utc_now_iso(),
        "status": status,
        "db": {**_db_file_info(path), "sqlite_version": sqlite3.sqlite_version},
        "tables": {name: 0 for name in COUNTED_TABLES},
        "events": {
            "total": 0,
            "earliest": "",
            "latest": "",
            "earliest_available": "",
            "latest_available": "",
            "undated": 0,
            "by_year": {},
            "by_source": {},
            "by_kind": {},
            "by_source_kind": [],
            "by_country": {},
            "by_timestamp_quality": {},
            "with_company": 0,
            "with_track": 0,
            "with_product_code": 0,
            "match_rate": {"company": 0.0, "track": 0.0, "product_code": 0.0},
        },
        "registries": {
            "companies": 0,
            "companies_with_ticker": 0,
            "companies_major": 0,
            "tracks": 0,
            "product_codes": 0,
            "product_codes_mapped": 0,
            "product_code_coverage": 0.0,
        },
        "prices": {
            "rows": 0,
            "tickers": 0,
            "earliest": "",
            "latest": "",
            "tickers_detail": [],
            "benchmarks": {"SPY": False, "XBI": False},
        },
        "trading": {
            "signals": 0,
            "signals_by_kind": {},
            "signals_earliest": "",
            "signals_latest": "",
            "paper_trades": 0,
            "paper_equity": 0,
            "positions": 0,
            "paper_orders": 0,
            "live_alerts": 0,
            "live_equity": 0,
            "llm_verdicts": 0,
            "runs": 0,
            "last_run": None,
        },
        "errors": list(errors),
    }


# ------------------------------------------------------------------------- events
def _events_section(db: Any, counts: Mapping[str, int], errors: list[str]) -> dict[str, Any]:
    total = int(counts.get("events", 0))

    row = _query(
        db,
        "SELECT MIN(event_date) AS earliest, MAX(event_date) AS latest,"
        " MIN(available_at) AS earliest_available, MAX(available_at) AS latest_available"
        f" FROM events WHERE event_date GLOB {_ISO_DATE_GLOB}",
        errors=errors,
        tag="events.dates",
    )
    dates = row[0] if row else {}

    by_year = _counter(
        _query(
            db,
            "SELECT substr(event_date, 1, 4) AS year, COUNT(*) AS n FROM events"
            f" WHERE event_date GLOB {_YEAR_GLOB} GROUP BY year ORDER BY year",
            errors=errors,
            tag="events.by_year",
        ),
        "year",
    )
    by_source = _counter(
        _query(
            db,
            "SELECT source, COUNT(*) AS n FROM events GROUP BY source ORDER BY n DESC, source",
            errors=errors,
            tag="events.by_source",
        ),
        "source",
    )
    by_kind = _counter(
        _query(
            db,
            "SELECT kind, COUNT(*) AS n FROM events GROUP BY kind ORDER BY n DESC, kind",
            errors=errors,
            tag="events.by_kind",
        ),
        "kind",
    )
    source_kind_rows = _query(
        db,
        "SELECT source, kind, COUNT(*) AS n, MIN(NULLIF(event_date, '')) AS earliest,"
        " MAX(NULLIF(event_date, '')) AS latest FROM events"
        " GROUP BY source, kind ORDER BY n DESC, source, kind",
        errors=errors,
        tag="events.by_source_kind",
    )
    by_source_kind = [
        {
            "source": str(item.get("source") or ""),
            "kind": str(item.get("kind") or ""),
            "n": int(item.get("n") or 0),
            "earliest": str(item.get("earliest") or ""),
            "latest": str(item.get("latest") or ""),
        }
        for item in source_kind_rows
    ]
    by_country = _counter(
        _query(
            db,
            "SELECT COALESCE(NULLIF(country, ''), 'unknown') AS country, COUNT(*) AS n"
            " FROM events GROUP BY country ORDER BY n DESC, country",
            errors=errors,
            tag="events.by_country",
        ),
        "country",
    )
    by_quality = _counter(
        _query(
            db,
            "SELECT COALESCE(NULLIF(timestamp_quality, ''), 'unknown') AS quality,"
            " COUNT(*) AS n FROM events GROUP BY quality ORDER BY n DESC, quality",
            errors=errors,
            tag="events.by_quality",
        ),
        "quality",
    )
    coverage_rows = _query(
        db,
        "SELECT COUNT(*) AS total,"
        " SUM(CASE WHEN company_key IS NOT NULL AND company_key <> '' THEN 1 ELSE 0 END) AS with_company,"
        " SUM(CASE WHEN track_id IS NOT NULL AND track_id <> '' THEN 1 ELSE 0 END) AS with_track,"
        " SUM(CASE WHEN product_code IS NOT NULL AND product_code <> '' THEN 1 ELSE 0 END) AS with_code"
        " FROM events",
        errors=errors,
        tag="events.coverage",
    )
    coverage = coverage_rows[0] if coverage_rows else {}
    with_company = int(coverage.get("with_company") or 0)
    with_track = int(coverage.get("with_track") or 0)
    with_code = int(coverage.get("with_code") or 0)

    return {
        "total": total,
        "earliest": str(dates.get("earliest") or ""),
        "latest": str(dates.get("latest") or ""),
        "earliest_available": str(dates.get("earliest_available") or ""),
        "latest_available": str(dates.get("latest_available") or ""),
        "undated": max(0, total - sum(by_year.values())),
        "by_year": by_year,
        "by_source": by_source,
        "by_kind": by_kind,
        "by_source_kind": by_source_kind,
        "by_country": by_country,
        "by_timestamp_quality": by_quality,
        "with_company": with_company,
        "with_track": with_track,
        "with_product_code": with_code,
        "match_rate": {
            "company": format_rate(with_company, total),
            "track": format_rate(with_track, total),
            "product_code": format_rate(with_code, total),
        },
    }


# ---------------------------------------------------------------------- registries
def _registries_section(db: Any, counts: Mapping[str, int], errors: list[str]) -> dict[str, Any]:
    company_rows = _query(
        db,
        "SELECT COUNT(*) AS total,"
        " SUM(CASE WHEN ticker IS NOT NULL AND ticker <> '' THEN 1 ELSE 0 END) AS with_ticker,"
        " SUM(CASE WHEN is_major = 1 THEN 1 ELSE 0 END) AS major"
        " FROM companies",
        errors=errors,
        tag="registries.companies",
    )
    companies = company_rows[0] if company_rows else {}
    code_rows = _query(
        db,
        "SELECT COUNT(*) AS total,"
        " SUM(CASE WHEN track_id IS NOT NULL AND track_id <> '' THEN 1 ELSE 0 END) AS mapped"
        " FROM product_codes",
        errors=errors,
        tag="registries.product_codes",
    )
    codes = code_rows[0] if code_rows else {}
    code_total = int(codes.get("total") or counts.get("product_codes", 0) or 0)
    code_mapped = int(codes.get("mapped") or 0)
    company_total = int(companies.get("total") or counts.get("companies", 0) or 0)
    return {
        "companies": company_total,
        "companies_with_ticker": int(companies.get("with_ticker") or 0),
        "companies_major": int(companies.get("major") or 0),
        "tracks": int(counts.get("tracks", 0)),
        "product_codes": code_total,
        "product_codes_mapped": code_mapped,
        "product_code_coverage": format_rate(code_mapped, code_total),
    }


# -------------------------------------------------------------------------- prices
def _prices_section(db: Any, counts: Mapping[str, int], errors: list[str]) -> dict[str, Any]:
    summary = _query(
        db,
        "SELECT COUNT(*) AS rows, COUNT(DISTINCT ticker) AS tickers,"
        " MIN(date) AS earliest, MAX(date) AS latest FROM prices",
        errors=errors,
        tag="prices.summary",
    )
    row = summary[0] if summary else {}
    detail = _query(
        db,
        "SELECT ticker, COUNT(*) AS rows, MIN(date) AS earliest, MAX(date) AS latest"
        " FROM prices GROUP BY ticker ORDER BY ticker",
        errors=errors,
        tag="prices.by_ticker",
    )
    tickers = [str(item["ticker"]) for item in detail]
    return {
        "rows": int(row.get("rows") or counts.get("prices", 0) or 0),
        "tickers": int(row.get("tickers") or len(detail)),
        "earliest": str(row.get("earliest") or ""),
        "latest": str(row.get("latest") or ""),
        "tickers_detail": [
            {
                "ticker": str(item["ticker"]),
                "rows": int(item["rows"] or 0),
                "earliest": str(item.get("earliest") or ""),
                "latest": str(item.get("latest") or ""),
            }
            for item in detail
        ],
        "benchmarks": {"SPY": "SPY" in tickers, "XBI": "XBI" in tickers},
    }


# ------------------------------------------------------------------------- trading
def _trading_section(db: Any, counts: Mapping[str, int], errors: list[str]) -> dict[str, Any]:
    signal_dates = _query(
        db,
        "SELECT MIN(signal_date) AS earliest, MAX(signal_date) AS latest,"
        " COUNT(*) AS n FROM signals"
        f" WHERE signal_date GLOB {_ISO_DATE_GLOB}",
        errors=errors,
        tag="trading.signals.dates",
    )
    dates = signal_dates[0] if signal_dates else {}
    by_kind = _counter(
        _query(
            db,
            "SELECT kind, COUNT(*) AS n FROM signals GROUP BY kind ORDER BY n DESC, kind",
            errors=errors,
            tag="trading.signals.by_kind",
        ),
        "kind",
    )
    last_run_rows = _query(
        db,
        "SELECT run_id, started_at, finished_at, stage, stats FROM runs"
        " ORDER BY finished_at DESC LIMIT 1",
        errors=errors,
        tag="trading.runs",
    )
    last_run = last_run_rows[0] if last_run_rows else None
    if last_run is not None:
        raw = last_run.get("stats")
        if isinstance(raw, str) and raw:
            try:
                import json

                last_run["stats"] = json.loads(raw)
            except (TypeError, ValueError):
                pass
    return {
        "signals": int(counts.get("signals", 0)),
        "signals_by_kind": by_kind,
        "signals_earliest": str(dates.get("earliest") or ""),
        "signals_latest": str(dates.get("latest") or ""),
        "paper_trades": int(counts.get("paper_trades", 0)),
        "paper_equity": int(counts.get("paper_equity", 0)),
        "positions": int(counts.get("positions", 0)),
        "paper_orders": int(counts.get("paper_orders", 0)),
        "live_alerts": int(counts.get("live_alerts", 0)),
        "live_equity": int(counts.get("live_equity", 0)),
        "llm_verdicts": int(counts.get("llm_verdicts", 0)),
        "runs": int(counts.get("runs", 0)),
        "last_run": last_run,
    }


# ------------------------------------------------------------------------- public
def data_stats(db: Any) -> dict[str, Any]:
    """Return a JSON-serializable data-scale report for ``db``.

    Args:
        db: an open :class:`medradar.db.DB` (left open) or a path to the SQLite
            file (opened and closed here). A missing path returns
            ``status="missing_db"`` with zeroed sections instead of creating it.

    Returns:
        ``{"generated_at", "status", "db", "tables", "events", "registries",
        "prices", "trading", "errors"}``. ``status`` is ``"ok"`` for any
        readable database (including an empty one) and ``"missing_db"`` when the
        path does not exist. ``errors`` lists individual queries that a
        partial/older database could not answer; they never abort the report.
    """
    from .db import DB  # lazy: stats_cmd must stay importable without a DB

    errors: list[str] = []
    path: Path | None = None
    owned = False
    if isinstance(db, (str, Path)):
        path = Path(db)
        if not path.exists():
            return _empty_report(path, "missing_db", errors)
        if not path.is_file():
            errors.append(f"not a database file: {path}")
            return _empty_report(path, "missing_db", errors)
        try:
            db = DB(path)
        except (sqlite3.Error, OSError) as exc:
            errors.append(f"cannot open {path}: {type(exc).__name__}: {exc}")
            return _empty_report(path, "unreadable_db", errors)
        owned = True
    else:
        raw_path = getattr(db, "path", None)
        if raw_path is not None:
            path = Path(raw_path)
    if not hasattr(db, "query") or not hasattr(db, "scalar"):
        raise TypeError("data_stats(db) expects a DB instance or a database path")

    try:
        counts: dict[str, int] = {}
        for table in COUNTED_TABLES:
            counts[table] = int(
                _scalar(
                    db,
                    f"SELECT COUNT(*) FROM {table}",
                    default=0,
                    errors=errors,
                    tag=f"tables.{table}",
                )
                or 0
            )
        info = _db_file_info(path)
        info["sqlite_version"] = str(
            _scalar(db, "SELECT sqlite_version()", default=sqlite3.sqlite_version,
                    errors=errors, tag="db.sqlite_version")
            or sqlite3.sqlite_version
        )
        payload = {
            "generated_at": utc_now_iso(),
            "status": "ok",
            "db": info,
            "tables": counts,
            "events": _events_section(db, counts, errors),
            "registries": _registries_section(db, counts, errors),
            "prices": _prices_section(db, counts, errors),
            "trading": _trading_section(db, counts, errors),
            "errors": errors,
        }
        return payload
    finally:
        if owned:
            db.close()


# ------------------------------------------------------------------------ growth
def growth_row(
    stats: Mapping[str, Any],
    note: str = "",
    day: str | None = None,
) -> dict[str, Any]:
    """Compact one-row summary used by ``docs/DATA.md``'s growth table."""
    events = stats.get("events") or {}
    registries = stats.get("registries") or {}
    prices = stats.get("prices") or {}
    row_date = day or date.today().isoformat()
    return {
        "date": row_date,
        "events": int(events.get("total") or 0),
        "companies": int(registries.get("companies") or 0),
        "tracks": int(registries.get("tracks") or 0),
        "product_codes": int(registries.get("product_codes") or 0),
        "price_rows": int(prices.get("rows") or 0),
        "db_human": str((stats.get("db") or {}).get("size_human") or "0 B"),
        "note": note,
    }


def render_growth_markdown_row(row: Mapping[str, Any]) -> str:
    """Render :func:`growth_row` as one ``| ... |`` markdown table row."""
    return "| {date} | {events} | {companies} | {tracks} | {product_codes} | {price_rows} | {db_human} | {note} |".format(
        date=row.get("date", ""),
        events=row.get("events", 0),
        companies=row.get("companies", 0),
        tracks=row.get("tracks", 0),
        product_codes=row.get("product_codes", 0),
        price_rows=row.get("price_rows", 0),
        db_human=row.get("db_human", "0 B"),
        note=row.get("note", ""),
    )


def append_growth_row(
    stats: Mapping[str, Any],
    path: str | Path = "docs/DATA.md",
    note: str = "",
    day: str | None = None,
) -> dict[str, Any]:
    """Append/replace today's row in the growth table of ``docs/DATA.md``.

    The table is delimited by ``<!-- growth:start -->`` ... ``<!-- growth:end -->``
    so the nightly script can keep it current without a markdown parser. A row
    for the same date is replaced (reruns are idempotent); when the file or the
    marker is missing the call is a no-op reported as ``status="skipped"``.
    """
    target = Path(path)
    row = growth_row(stats, note=note, day=day)
    rendered = render_growth_markdown_row(row)
    if not target.is_file():
        return {"status": "skipped", "reason": f"missing file: {target}", "row": row}
    text = target.read_text(encoding="utf-8")
    if GROWTH_MARKER not in text:
        return {
            "status": "skipped",
            "reason": f"missing marker {GROWTH_MARKER!r}",
            "row": row,
        }
    head, _, tail = text.partition(GROWTH_MARKER)
    lines = head.rstrip("\n").splitlines()
    # replace today's row if a previous nightly already appended it
    day_prefix = f"| {row['date']} |"
    while lines and lines[-1].strip().startswith(day_prefix):
        lines.pop()
    lines.append(rendered)
    start = "\n".join(lines)
    new_text = f"{start}\n{GROWTH_MARKER}{tail}"
    target.write_text(new_text, encoding="utf-8")
    return {"status": "appended", "date": row["date"], "path": str(target), "row": row}


# ------------------------------------------------------------- DATA.md snapshot
STATS_MARKER_START = "<!-- stats:start -->"
STATS_MARKER_END = "<!-- stats:end -->"


def _fmt_int(value: Any) -> str:
    try:
        return f"{int(value or 0):,}"
    except (TypeError, ValueError):
        return "0"


def _fmt_pct(rate: Any) -> str:
    try:
        return f"{float(rate or 0) * 100:.1f}%"
    except (TypeError, ValueError):
        return "0.0%"


def _range_cell(earliest: Any, latest: Any) -> str:
    first = str(earliest or "")
    last = str(latest or "")
    if not first and not last:
        return "—"
    return f"{first or '?'} → {last or '?'}"


def render_stats_markdown(stats: Mapping[str, Any]) -> str:
    """Render the machine-maintained snapshot block for ``docs/DATA.md``.

    The block is bounded by ``<!-- stats:start -->`` / ``<!-- stats:end -->`` and
    rewritten by :func:`update_stats_markdown`, so the numbers in DATA.md never
    depend on a human copying them out of a terminal.
    """
    events = stats.get("events") or {}
    registries = stats.get("registries") or {}
    prices = stats.get("prices") or {}
    trading = stats.get("trading") or {}
    db_info = stats.get("db") or {}
    errors = stats.get("errors") or []

    generated = str(stats.get("generated_at") or "")
    lines: list[str] = [
        STATS_MARKER_START,
        "",
        f"> **自动生成区**（`medradar.stats_cmd.data_stats` 快照，生成于 {generated or 'unknown'}）。",
        "> 请勿手工编辑本区块：运行 `python -m medradar stats --db data/medradar.sqlite`",
        "> 或 `scripts/nightly.ps1` 即会原地刷新。",
        "",
        "### 总览",
        "",
        "| 指标 | 当前值 |",
        "| --- | ---: |",
        f"| 事件 `events` | **{_fmt_int(events.get('total'))}** |",
        f"| 事件日期范围 | {_range_cell(events.get('earliest'), events.get('latest'))} |",
        f"| 无日期事件 | {_fmt_int(events.get('undated'))} |",
        f"| 公司 `companies` | **{_fmt_int(registries.get('companies'))}**"
        f"（有 ticker {_fmt_int(registries.get('companies_with_ticker'))}，"
        f"重点 {_fmt_int(registries.get('companies_major'))}） |",
        f"| 赛道 `tracks` | **{_fmt_int(registries.get('tracks'))}** |",
        f"| 产品码 `product_codes` | **{_fmt_int(registries.get('product_codes'))}**"
        f"（已映射赛道 {_fmt_int(registries.get('product_codes_mapped'))}，"
        f"{_fmt_pct(registries.get('product_code_coverage'))}） |",
        f"| 价格 `prices` | **{_fmt_int(prices.get('rows'))} 行 / {_fmt_int(prices.get('tickers'))} 个 ticker**"
        f"（{_range_cell(prices.get('earliest'), prices.get('latest'))}） |",
        f"| 信号 `signals` | **{_fmt_int(trading.get('signals'))}** |",
        f"| 模拟盘 `paper_trades` / `paper_equity` | "
        f"{_fmt_int(trading.get('paper_trades'))} / {_fmt_int(trading.get('paper_equity'))} |",
        f"| 实时通道 `live_alerts` / `live_equity` | "
        f"{_fmt_int(trading.get('live_alerts'))} / {_fmt_int(trading.get('live_equity'))} |",
        f"| 当前持仓 `positions` / 挂单 `paper_orders` | "
        f"{_fmt_int(trading.get('positions'))} / {_fmt_int(trading.get('paper_orders'))} |",
        f"| 运行记录 `runs` | {_fmt_int(trading.get('runs'))} |",
        f"| LLM 缓存 `llm_verdicts` | {_fmt_int(trading.get('llm_verdicts'))} |",
        f"| 数据库体积 | **{db_info.get('size_human') or '0 B'}**"
        f"（{_fmt_int(db_info.get('bytes'))} B；WAL {_fmt_int(db_info.get('wal_bytes'))} B；"
        f"SQLite {db_info.get('sqlite_version') or '?'}） |",
        "",
        "### 来源与类型",
        "",
        "| `source` | `kind` | 条数 | 覆盖区间 |",
        "| --- | --- | ---: | --- |",
    ]
    for item in events.get("by_source_kind") or []:
        lines.append(
            f"| `{item.get('source')}` | `{item.get('kind')}` | {_fmt_int(item.get('n'))} | "
            f"{_range_cell(item.get('earliest'), item.get('latest'))} |"
        )
    if not events.get("by_source_kind"):
        lines.append("| — | — | 0 | — |")

    lines += [
        "",
        "### 覆盖年份（按 `event_date`）",
        "",
        "| 年份 | 事件数 |",
        "| --- | ---: |",
    ]
    by_year = events.get("by_year") or {}
    pre_rows: list[tuple[str, int]] = []
    post_rows: list[tuple[str, int]] = []
    for year in sorted(by_year):
        try:
            numeric = int(year)
        except (TypeError, ValueError):
            continue
        (pre_rows if numeric < 2016 else post_rows).append((year, int(by_year[year] or 0)))
    if pre_rows:
        lines.append(
            f"| {pre_rows[0][0]}–2015（合计） | {_fmt_int(sum(n for _, n in pre_rows))} |"
        )
    for year, count in post_rows:
        lines.append(f"| {year} | {_fmt_int(count)} |")
    if not pre_rows and not post_rows:
        lines.append("| — | 0 |")

    lines += [
        "",
        "### 覆盖质量",
        "",
        "| 指标 | 数值 |",
        "| --- | ---: |",
        f"| 公司已归属 `company_key` | {_fmt_int(events.get('with_company'))} "
        f"({_fmt_pct((events.get('match_rate') or {}).get('company'))}) |",
        f"| 赛道已归属 `track_id` | {_fmt_int(events.get('with_track'))} "
        f"({_fmt_pct((events.get('match_rate') or {}).get('track'))}) |",
        f"| 产品码已归属 | {_fmt_int(events.get('with_product_code'))} "
        f"({_fmt_pct((events.get('match_rate') or {}).get('product_code'))}) |",
        "| 时间戳精度 | "
        + " ｜ ".join(
            f"{quality} {_fmt_int(count)}"
            for quality, count in (events.get("by_timestamp_quality") or {}).items()
        )
        + " |",
        "| 国家字段 Top 10（原始值，未归一化） | "
        + " ｜ ".join(
            f"{country} {_fmt_int(count)}"
            for country, count in list((events.get("by_country") or {}).items())[:10]
        )
        + " |",
        "",
        "### 价格覆盖",
        "",
        "| 项 | 值 |",
        "| --- | --- |",
        f"| 基准 SPY / XBI | {'有' if (prices.get('benchmarks') or {}).get('SPY') else '缺'}"
        f" / {'有' if (prices.get('benchmarks') or {}).get('XBI') else '缺'} |",
        "| 覆盖 ticker 数 | "
        + _fmt_int(prices.get("tickers"))
        + " |",
        "| 日期范围 | "
        + _range_cell(prices.get("earliest"), prices.get("latest"))
        + " |",
        "",
        "### 交易与回放",
        "",
        "| 项 | 值 |",
        "| --- | --- |",
        "| 信号 `kind` 分布 | "
        + (
            " ｜ ".join(
                f"`{kind}` {_fmt_int(count)}"
                for kind, count in (trading.get("signals_by_kind") or {}).items()
            )
            or "—"
        )
        + " |",
        "| 信号日期范围 | "
        + _range_cell(trading.get("signals_earliest"), trading.get("signals_latest"))
        + " |",
        "| 最近一次运行 | "
        + (
            f"`{((trading.get('last_run') or {}).get('stage'))}` @ "
            f"{((trading.get('last_run') or {}).get('finished_at') or '?')}"
            if trading.get("last_run")
            else "—"
        )
        + " |",
        "",
        "### 数据健康",
        "",
        "- 查询失败："
        + ("无" if not errors else f"{len(errors)} 项（`{errors[0]}`）")
        + "",
        STATS_MARKER_END,
    ]
    return "\n".join(lines) + "\n\n"


def update_stats_markdown(
    stats: Mapping[str, Any],
    path: str | Path = "docs/DATA.md",
) -> dict[str, Any]:
    """Replace the generated snapshot block inside ``docs/DATA.md`` in place.

    Markers: ``<!-- stats:start -->`` ... ``<!-- stats:end -->``. Missing file or
    markers is a no-op reported as ``status="skipped"``; identical content is
    ``status="unchanged"`` so nightly reruns do not dirty the file.
    """
    target = Path(path)
    if not target.is_file():
        return {"status": "skipped", "reason": f"missing file: {target}"}
    text = target.read_text(encoding="utf-8")
    if STATS_MARKER_START not in text or STATS_MARKER_END not in text:
        return {"status": "skipped", "reason": "missing stats markers"}
    head = text.split(STATS_MARKER_START, 1)[0]
    # The rendered block owns exactly one newline after the end marker; trimming
    # leading newlines here keeps repeated refresh byte-identical instead of
    # growing a blank line on every nightly run.
    tail = text.split(STATS_MARKER_END, 1)[1].lstrip("\n")
    block = render_stats_markdown(stats)
    new_text = f"{head}{block}{tail}"
    if new_text == text:
        return {"status": "unchanged", "path": str(target)}
    target.write_text(new_text, encoding="utf-8")
    return {
        "status": "updated",
        "path": str(target),
        "generated_at": stats.get("generated_at"),
        "bytes": target.stat().st_size,
    }


__all__ = [
    "COUNTED_TABLES",
    "GROWTH_MARKER",
    "STATS_MARKER_END",
    "STATS_MARKER_START",
    "append_growth_row",
    "data_stats",
    "growth_row",
    "human_size",
    "render_growth_markdown_row",
    "render_stats_markdown",
    "update_stats_markdown",
]
