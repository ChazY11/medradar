"""Measurement layer for MedRadar 2.0.

All numbers in the product are computed here from the existing research store
``data/medradar.sqlite`` (read-only). Nothing is hard-coded, nothing is
synthesised, and every aggregate keeps enough parameters to be re-expanded into
the underlying event rows.

Design rules enforced by this module
------------------------------------
* the store is opened ``mode=ro`` — the product never writes to research data;
* events are counted by *record*, and metrics state which ``kind`` values they
  sum, so 510(k), PMA, recalls and trials are never silently mixed;
* the technology track is the store's own ``events.track_id`` (derived at
  collection time from the FDA product code -> track map); records without a
  track are reported as *unmapped*, not as zero activity;
* company attribution reuses the store's ``company_key`` and, for the two
  roster-absent firms, the reviewed exact-alias set in
  :mod:`medradar.product.entities`;
* every aggregate accepts an explicit date window and reports the observed
  coverage of the sources it used, because source start dates differ (recalls
  from ~2002, 8-K from 2015).
"""
from __future__ import annotations

import json
import math
import sqlite3
import threading
from collections import OrderedDict
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from ..config import DEFAULT_DB
from . import entities
from .catalog import (
    DOMAIN_BY_ID,
    EVIDENCE_TIERS,
    FEATURED_COMPANIES,
    FEATURED_KEYS,
    LIMITATIONS,
    METRICS,
    PRODUCT_VERSION,
    RADAR_DOMAINS,
    SOURCES,
    TRACK_TO_DOMAIN,
)

DB_FILE = Path(DEFAULT_DB)
_QUARTER_END = {"03": "03-31", "06": "06-30", "09": "09-30", "12": "12-31"}


# --------------------------------------------------------------------------- cache
_CACHE: "OrderedDict[tuple, Any]" = OrderedDict()
_CACHE_MAX = 256


def dataset_signature() -> dict[str, Any]:
    path = DB_FILE
    if not path.exists():
        return {"path": str(path), "exists": False, "mtime_ns": 0, "bytes": 0}
    stat = path.stat()
    return {
        "path": str(path),
        "exists": True,
        "mtime_ns": stat.st_mtime_ns,
        "bytes": stat.st_size,
        "modified_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }


def _memo(fn: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        sig = dataset_signature()
        key = (fn.__name__, sig["path"], sig["mtime_ns"], sig["bytes"], args, tuple(sorted(kwargs.items())))
        if key in _CACHE:
            _CACHE.move_to_end(key)
            return _CACHE[key]
        value = fn(*args, **kwargs)
        _CACHE[key] = value
        if len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)
        return value

    return wrapper


def clear_cache() -> None:
    _CACHE.clear()


# ----------------------------------------------------------------------- connection
#: Product-side derived index. ``events`` has no index on ``applicant_raw`` and
#: the research store must not be modified, so the ~550 events of the two
#: roster-absent firms are materialised once into a tiny auxiliary SQLite file
#: which every product connection attaches read-only. It is rebuilt whenever the
#: research store's mtime changes. The path is derived from the active store so
#: a fixture database never reuses the real dataset's alias index.
_ENTITY_LOCK = threading.Lock()


def entity_map_path() -> Path:
    return DB_FILE.parent / f"{DB_FILE.stem}.product_entity_map.sqlite"


@contextmanager
def use_database(path: str | Path) -> Iterable[Path]:
    """Temporarily point the product layer at another SQLite store.

    Used by the synthetic fixture tests (Tier B) so the measurement code under
    test is exactly the production code path, not a mocked one. The research
    database is never modified; only the module-level path is switched and all
    memoised aggregates are cleared on entry and exit.
    """
    global DB_FILE
    target = Path(path)
    previous = DB_FILE
    DB_FILE = target
    clear_cache()
    try:
        yield target
    finally:
        DB_FILE = previous
        clear_cache()


def _entity_map_stale() -> bool:
    entity_map = entity_map_path()
    if not entity_map.exists():
        return True
    sig = dataset_signature()
    return entity_map.stat().st_mtime_ns < int(sig.get("mtime_ns") or 0)


def ensure_entity_map() -> None:
    entity_map = entity_map_path()
    if not DB_FILE.exists():
        return
    with _ENTITY_LOCK:
        if not _entity_map_stale():
            return
        entity_map.parent.mkdir(parents=True, exist_ok=True)
        tmp = entity_map.with_name(entity_map.name + ".tmp")
        if tmp.exists():
            tmp.unlink()
        source = sqlite3.connect(f"file:{DB_FILE.as_posix()}?mode=ro", uri=True)
        try:
            target = sqlite3.connect(tmp)
            try:
                target.executescript(
                    "CREATE TABLE IF NOT EXISTS event_company ("
                    "event_id TEXT PRIMARY KEY, company_key TEXT NOT NULL, matched_alias TEXT);"
                    "CREATE INDEX IF NOT EXISTS idx_event_company_key ON event_company(company_key);"
                )
                rows: list[tuple[str, str, str]] = []
                for key, meta in entities.roster().items():
                    if meta.get("roster_present", True) is not False:
                        continue
                    aliases = [str(a) for a in (meta.get("aliases") or [])]
                    if not aliases:
                        continue
                    marks = ",".join("?" for _ in aliases)
                    for event_id, applicant in source.execute(
                        f"SELECT event_id, applicant_raw FROM events WHERE applicant_raw IN ({marks})",
                        aliases,
                    ):
                        rows.append((event_id, key, applicant))
                target.executemany(
                    "INSERT OR REPLACE INTO event_company VALUES (?,?,?)", rows
                )
                target.commit()
            finally:
                target.close()
        finally:
            source.close()
        if entity_map.exists():
            entity_map.unlink()
        tmp.replace(entity_map)


@contextmanager
def read() -> Iterable[sqlite3.Connection]:
    if not DB_FILE.exists():
        raise FileNotFoundError(
            f"research store not found: {DB_FILE}. "
            "Run `python -m medradar run` once to build it, then start the product server."
        )
    ensure_entity_map()
    entity_map = entity_map_path()
    con = sqlite3.connect(f"file:{DB_FILE.as_posix()}?mode=ro", uri=True, timeout=15.0)
    con.row_factory = sqlite3.Row
    try:
        if entity_map.exists():
            con.execute("ATTACH DATABASE ? AS pm", (entity_map.as_posix(),))
        yield con
    finally:
        con.close()


def _rows(con: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in con.execute(sql, params).fetchall()]


def _one(con: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> Any:
    row = con.execute(sql, params).fetchone()
    return None if row is None else row[0]


def company_predicate(keys: Iterable[str], alias: str = "e") -> tuple[str, list[Any]]:
    """SQL predicate for product queries.

    Roster firms use the store's own ``company_key``; roster-absent firms use the
    attached product index (exact applicant aliases, built above). The predicate
    stays tiny (one parameter per company), so aggregate queries stay fast.
    """
    clauses: list[str] = []
    params: list[Any] = []
    for key in dict.fromkeys(keys):
        if not key:
            continue
        meta = entities.company_meta(key)
        if meta and meta.get("roster_present", True) is False:
            clauses.append(
                f"{alias}.event_id IN (SELECT event_id FROM pm.event_company WHERE company_key = ?)"
            )
            params.append(key)
        else:
            clauses.append(f"{alias}.company_key = ?")
            params.append(key)
    if not clauses:
        return "0", []
    return "(" + " OR ".join(clauses) + ")", params


def company_from(keys: Iterable[str]) -> tuple[str, str, list[Any]]:
    """Return ``(prefix, from_sql, params)`` that select events for ``keys``.

    Roster firms filter on the store's ``company_key``. Roster-absent firms join
    the attached exact-alias index; crucially the joins start from the tiny
    ``pm.event_company`` table (551 rows) instead of from ``events``, otherwise
    SQLite's planner scans a whole ``kind`` index and each product page takes
    seconds. ``prefix`` is a ``WITH sel AS (...)`` clause, ``from_sql`` exposes
    the alias ``e``, and ``params`` must be bound *before* any further filter
    parameters.
    """
    keys = [key for key in dict.fromkeys(keys) if key]
    if not keys:
        return "", "events e", []
    parts: list[str] = []
    params: list[Any] = []
    for key in keys:
        meta = entities.company_meta(key)
        if meta and meta.get("roster_present", True) is False:
            parts.append(
                "SELECT e.* FROM pm.event_company x JOIN events e ON e.event_id = x.event_id "
                "WHERE x.company_key = ?"
            )
            params.append(key)
        else:
            parts.append("SELECT e.* FROM events e WHERE e.company_key = ?")
            params.append(key)
    prefix = "WITH sel AS (" + " UNION ALL ".join(parts) + ") "
    return prefix, "sel e", params


# ------------------------------------------------------------------------- taxonomy
@_memo
def track_rows() -> dict[str, dict[str, Any]]:
    with read() as con:
        rows = _rows(con, "SELECT id, name_zh, name_en, category FROM tracks ORDER BY id")
    return {
        row["id"]: {
            "id": row["id"],
            "name_zh": row["name_zh"],
            "name_en": row["name_en"],
            "category": row["category"],
            "domain": TRACK_TO_DOMAIN.get(row["id"]),
            "domain_label_zh": DOMAIN_BY_ID.get(TRACK_TO_DOMAIN.get(row["id"], ""), {}).get("label_zh"),
        }
        for row in rows
    }


def track_meta(track_id: str | None) -> dict[str, Any]:
    if not track_id:
        return {
            "id": None,
            "name_zh": "未映射赛道",
            "name_en": "Unmapped track",
            "category": None,
            "domain": None,
            "domain_label_zh": None,
        }
    return track_rows().get(track_id) or {
        "id": track_id,
        "name_zh": track_id,
        "name_en": track_id,
        "category": None,
        "domain": TRACK_TO_DOMAIN.get(track_id),
        "domain_label_zh": None,
    }


def sortable_tracks(ids: Iterable[str]) -> list[dict[str, Any]]:
    out = [track_meta(i) for i in ids if i]
    out.sort(key=lambda row: (row.get("domain") or "zz", row.get("name_zh") or ""))
    return out


def radar_domains() -> list[dict[str, Any]]:
    tracks = track_rows()
    payload = []
    for domain in RADAR_DOMAINS:
        payload.append(
            {
                **domain,
                "track_detail": [tracks.get(t) for t in domain["tracks"] if tracks.get(t)],
            }
        )
    return payload


# ---------------------------------------------------------------------------- time
def _parse(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


@_memo
def data_edge() -> str:
    with read() as con:
        latest = _one(con, "SELECT MAX(event_date) FROM events WHERE event_date IS NOT NULL")
    return str(latest or date.today().isoformat())


def resolve_window(
    years: int | None = None,
    start: str | None = None,
    end: str | None = None,
) -> tuple[str, str]:
    """Return an inclusive ISO date window.

    Unspecified ``end`` is the latest event date in the store (not wall clock),
    so generated views are stable for a frozen dataset. ``years`` sets the
    start from the end when ``start`` is missing.
    """
    edge = _parse(end) or _parse(data_edge()) or date.today()
    if start:
        begin = _parse(start) or (edge - timedelta(days=365 * (years or 5)))
    else:
        begin = edge - timedelta(days=365 * (years or 5))
    if begin > edge:
        begin, edge = edge, begin
    return begin.isoformat(), edge.isoformat()


def previous_window(start: str, end: str) -> tuple[str, str]:
    begin = _parse(start) or date.today()
    finish = _parse(end) or date.today()
    span = max(timedelta(days=1), finish - begin)
    return (begin - span).isoformat(), (begin - timedelta(days=1)).isoformat()


def _period_expr(granularity: str) -> str:
    if granularity == "year":
        return "substr(e.event_date, 1, 4)"
    if granularity == "month":
        return "substr(e.event_date, 1, 7)"
    return (
        "substr(e.event_date, 1, 4) || '-Q' || "
        "CAST((CAST(substr(e.event_date, 6, 2) AS INTEGER) + 2) / 3 AS TEXT)"
    )


GRANULARITIES = ("year", "quarter", "month")
#: A company must have at least this many *track-mapped* records in the window
#: before a location quotient is reported; below it the ratio is too unstable to
#: distinguish from noise.
MIN_LQ_COMPANY_RECORDS = 10
#: An industry track must have at least this many records before it can serve as
#: a denominator for a company location quotient.
MIN_LQ_INDUSTRY_TRACK_RECORDS = 5
#: A calendar period ending within this many days of the data edge is complete on
#: the calendar but may still be revised because source publication lags.
SOURCE_LAG_DAYS = 90


def _require_granularity(granularity: str) -> str:
    if granularity not in GRANULARITIES:
        raise ValueError(f"unknown granularity: {granularity}")
    return granularity


def _period_start(day: date, granularity: str) -> date:
    if granularity == "year":
        return date(day.year, 1, 1)
    if granularity == "month":
        return date(day.year, day.month, 1)
    month = (day.month - 1) // 3 * 3 + 1
    return date(day.year, month, 1)


def _period_end(day: date, granularity: str) -> date:
    start = _period_start(day, granularity)
    if granularity == "year":
        return date(start.year, 12, 31)
    if granularity == "month":
        if start.month == 12:
            return date(start.year, 12, 31)
        return date(start.year, start.month + 1, 1) - timedelta(days=1)
    quarter_end_month = start.month + 2
    if quarter_end_month == 12:
        return date(start.year, 12, 31)
    return date(start.year, quarter_end_month + 1, 1) - timedelta(days=1)


def _next_period_start(day: date, granularity: str) -> date:
    return _period_end(day, granularity) + timedelta(days=1)


def _prev_period_end(day: date, granularity: str) -> date:
    return _period_start(day, granularity) - timedelta(days=1)


def period_bounds(period: str, granularity: str) -> tuple[date, date] | None:
    """Return the inclusive calendar bounds of a ``YYYY`` / ``YYYY-Qn`` / ``YYYY-MM`` label."""
    _require_granularity(granularity)
    try:
        if granularity == "year":
            day = date(int(period), 1, 1)
        elif granularity == "month":
            day = date.fromisoformat(period + "-01")
        else:
            year_text, quarter_text = period.split("-Q")
            day = date(int(year_text), (int(quarter_text) - 1) * 3 + 1, 1)
    except (TypeError, ValueError):
        return None
    return _period_start(day, granularity), _period_end(day, granularity)


def is_period_partial(period: str, granularity: str, window_start: str, window_end: str) -> bool:
    """True when the period is clipped by the research window at either end.

    Calendar completeness is *not* the same as source completeness: a period that
    ends within :data:`SOURCE_LAG_DAYS` of the data edge is calendar-complete but
    still exposed to publication lag. That second condition is reported
    separately by :func:`period_flags` and never silently folded into ``partial``.
    """
    bounds = period_bounds(period, granularity)
    begin = _parse(window_start)
    finish = _parse(window_end)
    if bounds is None or begin is None or finish is None:
        return False
    start, end = bounds
    return start < begin or end > finish


def period_flags(
    period: str,
    granularity: str,
    window_start: str,
    window_end: str,
    data_edge: str,
) -> dict[str, Any]:
    """Detailed completeness flags for one period inside a research window."""
    bounds = period_bounds(period, granularity)
    begin = _parse(window_start)
    finish = _parse(window_end)
    edge = _parse(data_edge)
    if bounds is None or begin is None or finish is None:
        return {
            "period": period,
            "partial": True,
            "complete": False,
            "source_lag_risk": False,
            "period_start": None,
            "period_end": None,
            "reason_zh": "无法解析周期",
        }
    start, end = bounds
    clipped = start < begin or end > finish
    source_lag = (not clipped) and edge is not None and (edge - end).days < SOURCE_LAG_DAYS
    reason = None
    if start < begin and end > finish:
        reason = "起止两端均不完整"
    elif start < begin:
        reason = "窗口起点落在周期中途"
    elif end > finish:
        reason = "窗口终点落在周期中途"
    elif source_lag:
        reason = "日历周期完整，但距数据截止不足 90 天，源数据可能仍会修订/补录"
    return {
        "period": period,
        "partial": clipped,
        "complete": not clipped,
        "source_lag_risk": source_lag,
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "reason_zh": reason,
    }


def complete_window(
    start: str,
    end: str,
    granularity: str = "quarter",
) -> tuple[str, str] | None:
    """Largest period-aligned window fully inside ``[start, end]``.

    Returns ``None`` when the window does not contain one whole period; callers
    must then report that a complete-period comparison is not available instead
    of computing a misleading percentage.
    """
    _require_granularity(granularity)
    begin = _parse(start)
    finish = _parse(end)
    if begin is None or finish is None:
        return None
    aligned_start = begin if begin == _period_start(begin, granularity) else _next_period_start(begin, granularity)
    aligned_end = finish if finish == _period_end(finish, granularity) else _prev_period_end(finish, granularity)
    if aligned_start > aligned_end:
        return None
    return aligned_start.isoformat(), aligned_end.isoformat()


def _shift_period_start(day: date, granularity: str, delta: int) -> date:
    """First day of the period ``delta`` periods away from ``day``'s period."""
    _require_granularity(granularity)
    start = _period_start(day, granularity)
    if granularity == "year":
        return date(start.year + delta, 1, 1)
    if granularity == "month":
        month_index = start.year * 12 + (start.month - 1) + delta
        return date(month_index // 12, month_index % 12 + 1, 1)
    quarter_index = start.year * 4 + (start.month - 1) // 3 + delta
    return date(quarter_index // 4, (quarter_index % 4) * 3 + 1, 1)


def _count_periods(start: str, end: str, granularity: str) -> int:
    begin, finish = _parse(start), _parse(end)
    if begin is None or finish is None:
        return 0
    first = _period_start(begin, granularity)
    last = _period_start(finish, granularity)
    if granularity == "year":
        return last.year - first.year + 1
    if granularity == "month":
        return (last.year - first.year) * 12 + (last.month - first.month) + 1
    return (last.year - first.year) * 4 + ((last.month - 1) // 3 - (first.month - 1) // 3) + 1


def comparison_windows(start: str, end: str, granularity: str = "quarter") -> dict[str, Any]:
    """Return equal-length, contiguous, complete-period recent/prior windows.

    The requested window is first trimmed to whole periods; the prior window is
    then the same number of whole periods immediately preceding it. This avoids
    the common defect where a partial start/end quarter silently changes the
    comparison length or leaves a gap between "recent" and "prior".
    """
    aligned = complete_window(start, end, granularity)
    if aligned is None:
        return {
            "start": start,
            "end": end,
            "granularity": granularity,
            "comparable": False,
            "analysis_start": None,
            "analysis_end": None,
            "prior_analysis_start": None,
            "prior_analysis_end": None,
            "periods": 0,
            "reason_zh": "窗口内没有完整的自然周期，无法进行完整周期比较。",
        }
    analysis_start, analysis_end = aligned
    periods = _count_periods(analysis_start, analysis_end, granularity)
    prior_end_start = _parse(analysis_start) - timedelta(days=1)  # type: ignore[operator]
    prior_analysis_end = _period_start(prior_end_start, granularity)  # type: ignore[arg-type]
    prior_analysis_start = _shift_period_start(prior_analysis_end, granularity, -(periods - 1))
    prior_analysis_end = _period_end(prior_analysis_end, granularity)
    partial_start = analysis_start > start
    partial_end = analysis_end < end
    return {
        "start": start,
        "end": end,
        "granularity": granularity,
        "comparable": True,
        "analysis_start": analysis_start,
        "analysis_end": analysis_end,
        "prior_analysis_start": prior_analysis_start.isoformat(),
        "prior_analysis_end": prior_analysis_end.isoformat(),
        "periods": periods,
        "partial_start": partial_start,
        "partial_end": partial_end,
        "reason_zh": (
            f"比较使用 {periods} 个完整自然{'年' if granularity == 'year' else '月' if granularity == 'month' else '季度'}："
            f"{analysis_start} 至 {analysis_end}，对照窗口为紧邻的等长 {periods} 个周期；"
            "请求窗口起止的不完整周期只展示、不参与同比、份额与 LQ。"
            if partial_start or partial_end
            else f"比较使用 {periods} 个完整自然周期：{analysis_start} 至 {analysis_end}，"
            f"对照为紧邻的等长窗口 {prior_analysis_start.isoformat()} 至 {prior_analysis_end.isoformat()}。"
        ),
    }


def window_completeness(start: str, end: str, granularity: str = "quarter") -> dict[str, Any]:
    """Describe how much of a research window is usable for period comparisons."""
    aligned = complete_window(start, end, granularity)
    begin = _parse(start)
    finish = _parse(end)
    if aligned is None or begin is None or finish is None:
        return {
            "start": start,
            "end": end,
            "granularity": granularity,
            "analysis_start": None,
            "analysis_end": None,
            "comparable": False,
            "partial_start": True,
            "partial_end": True,
            "reason_zh": "窗口内没有完整的自然周期，无法进行完整周期比较（只展示窗口合计）。",
        }
    analysis_start, analysis_end = aligned
    partial_start = analysis_start > start
    partial_end = analysis_end < end
    return {
        "start": start,
        "end": end,
        "granularity": granularity,
        "analysis_start": analysis_start,
        "analysis_end": analysis_end,
        "comparable": True,
        "partial_start": partial_start,
        "partial_end": partial_end,
        "reason_zh": (
            "比较采用完整自然季度口径；窗口起点/终点所在的不完整季度不参与同比与份额计算。"
            if partial_start or partial_end
            else "窗口起点与终点均对齐自然季度，全部记录参与比较。"
        ),
    }


def location_quotient(
    company_track_records: int,
    company_mapped_records: int,
    industry_track_records: int,
    industry_mapped_records: int,
    *,
    min_company_records: int = MIN_LQ_COMPANY_RECORDS,
    min_industry_track_records: int = MIN_LQ_INDUSTRY_TRACK_RECORDS,
) -> tuple[float | None, str]:
    """Consistent-denominator location quotient.

    Both sides use **track-mapped records only**:

    ``LQ = (company_track / company_mapped) / (industry_track / industry_mapped)``

    Returns ``(value, status)``; ``value`` is ``None`` when the ratio would be
    numerically meaningless (zero denominator or too small a sample), with a
    machine-readable status the UI must display as "不适用" rather than fabricate
    a number.
    """
    if company_mapped_records <= 0 or industry_mapped_records <= 0:
        return None, "zero_denominator"
    if company_track_records <= 0:
        return None, "zero_company_track"
    if company_mapped_records < min_company_records:
        return None, "low_company_mapped_sample"
    if industry_track_records < min_industry_track_records:
        return None, "low_industry_track_sample"
    company_share = company_track_records / company_mapped_records
    industry_share = industry_track_records / industry_mapped_records
    if industry_share <= 0:
        return None, "zero_denominator"
    return round(company_share / industry_share, 3), "ok"


def _periods(start: str, end: str, granularity: str) -> list[str]:
    begin, finish = _parse(start), _parse(end)
    if not begin or not finish:
        return []
    out: list[str] = []
    if granularity == "year":
        for year in range(begin.year, finish.year + 1):
            out.append(str(year))
    elif granularity == "month":
        year, month = begin.year, begin.month
        while (year, month) <= (finish.year, finish.month):
            out.append(f"{year:04d}-{month:02d}")
            month += 1
            if month > 12:
                year, month = year + 1, 1
    else:
        year, quarter = begin.year, (begin.month - 1) // 3 + 1
        while (year, quarter) <= (finish.year, (finish.month - 1) // 3 + 1):
            out.append(f"{year:04d}-Q{quarter}")
            quarter += 1
            if quarter > 4:
                year, quarter = year + 1, 1
    return out


def _period_label(period: str) -> str:
    return period


# ------------------------------------------------------------------------- sources
def _metric(kind: str) -> dict[str, Any]:
    metric = METRICS.get(kind)
    if not metric:
        raise KeyError(f"unknown metric: {kind}")
    return metric


def _kinds_for(metric: str) -> list[str]:
    return list(_metric(metric)["kinds"])


def _kind_marks(metric: str, alias: str = "e") -> tuple[str, list[str]]:
    kinds = _kinds_for(metric)
    return f"{alias}.kind IN ({','.join('?' for _ in kinds)})", kinds


# --------------------------------------------------------- approval classification
#: FDA openFDA PMA rows carry ``supplement_number`` and ``supplement_type`` for
#: every record (verified on 57,372/57,372 rows in the current store): an empty
#: ``supplement_number`` is an original PMA approval, a non-empty one is a PMA
#: supplement. 510(k) rows carry ``clearance_type`` (Traditional / Special /
#: Abbreviated / ...). Both fields are read from the stored raw payload; no type
#: is inferred from an application-number pattern.
def _payload_text(alias: str, field: str) -> str:
    return (
        f"(CASE WHEN json_valid({alias}.payload) "
        f"THEN json_extract({alias}.payload, '$.{field}') ELSE NULL END)"
    )


def _pma_original_sql(alias: str = "e") -> str:
    # A missing ``supplement_number`` key is *not* an original approval; it is
    # unknown (and must agree with approval_classification() in Python).
    return (
        f"({alias}.kind = 'pma' AND json_valid({alias}.payload) "
        f"AND json_type({alias}.payload, '$.supplement_number') IS NOT NULL "
        f"AND coalesce({_payload_text(alias, 'supplement_number')}, '') = '')"
    )


def _pma_supplement_sql(alias: str = "e") -> str:
    return (
        f"({alias}.kind = 'pma' AND json_valid({alias}.payload) "
        f"AND coalesce({_payload_text(alias, 'supplement_number')}, '') <> '')"
    )


def _traditional_510k_sql(alias: str = "e") -> str:
    return (
        f"({alias}.kind = '510k' AND json_valid({alias}.payload) "
        f"AND coalesce({_payload_text(alias, 'clearance_type')}, '') = 'Traditional')"
    )


def first_entry_sql(alias: str = "e") -> str:
    """Predicate for a plausible *first device approval* record.

    A PMA supplement is a change to an already-approved device and a Special or
    Abbreviated 510(k) is a change to the submitter's own cleared device, so
    neither is treated as evidence that the company first entered a track. Records
    whose payload cannot be parsed are excluded (and counted as unknown), never
    silently promoted to originals.
    """
    return f"({_pma_original_sql(alias)} OR {_traditional_510k_sql(alias)})"


PMA_TYPE_LABELS = {
    "pma_original": "原始 PMA 批准",
    "pma_supplement": "PMA 补充申请",
    "pma_unknown": "PMA 类型不可判定",
    "510k_traditional": "Traditional 510(k)",
    "510k_special": "Special 510(k)",
    "510k_abbreviated": "Abbreviated 510(k)",
    "510k_other": "其他 510(k) 类型",
    "510k_unknown": "510(k) 类型不可判定",
}


def approval_classification(kind: str | None, raw_payload: Any) -> dict[str, Any]:
    """Classify one approval record from its stored payload.

    Returns a dict with ``approval_type``, ``approval_type_label_zh``,
    ``is_first_entry_candidate`` and the raw type fields used. Unknown is a
    first-class outcome: ``classification_unavailable`` is never guessed.
    """
    payload: dict[str, Any] = {}
    if isinstance(raw_payload, str) and raw_payload:
        try:
            parsed = json.loads(raw_payload)
            if isinstance(parsed, dict):
                payload = parsed
        except (TypeError, ValueError):
            payload = {}
    elif isinstance(raw_payload, dict):
        payload = raw_payload
    if kind == "pma":
        if "supplement_number" not in payload:
            approval_type = "pma_unknown"
            detail = None
        elif str(payload.get("supplement_number") or "").strip():
            approval_type = "pma_supplement"
            detail = payload.get("supplement_type") or None
        else:
            approval_type = "pma_original"
            detail = None
        return {
            "approval_type": approval_type,
            "approval_type_label_zh": PMA_TYPE_LABELS[approval_type],
            "is_first_entry_candidate": approval_type == "pma_original",
            "classification_detail": detail,
            "classification_available": approval_type != "pma_unknown",
        }
    if kind == "510k":
        clearance_type = payload.get("clearance_type")
        if not clearance_type:
            approval_type = "510k_unknown"
        elif clearance_type == "Traditional":
            approval_type = "510k_traditional"
        elif clearance_type == "Special":
            approval_type = "510k_special"
        elif clearance_type == "Abbreviated":
            approval_type = "510k_abbreviated"
        else:
            approval_type = "510k_other"
        return {
            "approval_type": approval_type,
            "approval_type_label_zh": PMA_TYPE_LABELS[approval_type],
            "is_first_entry_candidate": approval_type == "510k_traditional",
            "classification_detail": clearance_type,
            "classification_available": approval_type != "510k_unknown",
        }
    return {
        "approval_type": kind or "unknown",
        "approval_type_label_zh": KIND_LABELS.get(kind or "", kind or "unknown"),
        "is_first_entry_candidate": False,
        "classification_detail": None,
        "classification_available": True,
    }


KIND_LABELS = {
    "510k": "510(k)",
    "pma": "PMA",
    "device_recall": "器械召回",
    "trial": "临床试验",
    "8k_catalyst": "8-K",
    "drug_approval": "药品批准",
}


@_memo
def company_pathway_window(key: str, start: str, end: str) -> dict[str, Any]:
    """Cached approval-type / pathway structure for one company and window."""
    with read() as con:
        return _pathway_window(con, key, start, end)


@_memo
def company_breakdown_all_time(key: str, end: str) -> dict[str, int]:
    """Cached all-time approval type counts for one company."""
    with read() as con:
        return _approval_breakdown(con, [key], "1900-01-01", end)


def _approval_breakdown(
    con: sqlite3.Connection,
    keys: list[str],
    start: str,
    end: str,
) -> dict[str, int]:
    """Counts of original/supplement PMA and 510(k) clearance types in a window."""
    prefix, frm, cte_params = company_from(keys)
    row = con.execute(
        f"""{prefix}
        SELECT
          SUM(CASE WHEN {_pma_original_sql('e')} THEN 1 ELSE 0 END) AS pma_original,
          SUM(CASE WHEN {_pma_supplement_sql('e')} THEN 1 ELSE 0 END) AS pma_supplement,
          SUM(CASE WHEN e.kind = 'pma' AND NOT ({_pma_original_sql('e')} OR {_pma_supplement_sql('e')}) THEN 1 ELSE 0 END) AS pma_unknown,
          SUM(CASE WHEN {_traditional_510k_sql('e')} THEN 1 ELSE 0 END) AS k510_traditional,
          SUM(CASE WHEN e.kind = '510k' AND json_valid(e.payload)
               AND coalesce({_payload_text('e', 'clearance_type')}, '') = 'Special' THEN 1 ELSE 0 END) AS k510_special,
          SUM(CASE WHEN e.kind = '510k' AND json_valid(e.payload)
               AND coalesce({_payload_text('e', 'clearance_type')}, '') IN ('Abbreviated') THEN 1 ELSE 0 END) AS k510_abbreviated,
          SUM(CASE WHEN e.kind = '510k' AND (NOT json_valid(e.payload)
               OR coalesce({_payload_text('e', 'clearance_type')}, '') = '') THEN 1 ELSE 0 END) AS k510_unknown,
          SUM(CASE WHEN e.kind = '510k' AND json_valid(e.payload)
               AND coalesce({_payload_text('e', 'clearance_type')}, '') NOT IN ('Traditional','Special','Abbreviated','') THEN 1 ELSE 0 END) AS k510_other
        FROM {frm}
        WHERE e.kind IN ('510k','pma') AND e.event_date >= ? AND e.event_date <= ?""",
        [*cte_params, start, end],
    ).fetchone()
    out = {key: int(row[key] or 0) for key in row.keys()} if row is not None else {}
    return out


def classification_audit(con: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Dataset-level availability of approval subtype classification."""
    if con is None:
        with read() as local:
            return classification_audit(local)
    pma_total = int(_one(con, "SELECT COUNT(*) FROM events WHERE kind='pma'") or 0)
    pma_bad = int(
        _one(
            con,
            "SELECT COUNT(*) FROM events WHERE kind='pma' AND (NOT json_valid(payload) "
            "OR json_type(payload, '$.supplement_number') IS NULL)",
        )
        or 0
    )
    k_total = int(_one(con, "SELECT COUNT(*) FROM events WHERE kind='510k'") or 0)
    k_bad = int(
        _one(
            con,
            "SELECT COUNT(*) FROM events WHERE kind='510k' AND (NOT json_valid(payload) "
            "OR coalesce(json_extract(payload, '$.clearance_type'), '') = '')",
        )
        or 0
    )
    return {
        "pma_total": pma_total,
        "pma_unknown": pma_bad,
        "pma_classification_available": pma_total > 0 and pma_bad == 0,
        "pma_unknown_share": (pma_bad / pma_total) if pma_total else None,
        "k510_total": k_total,
        "k510_unknown": k_bad,
        "k510_classification_available": k_total > 0 and k_bad == 0,
        "k510_unknown_share": (k_bad / k_total) if k_total else None,
        "rule_zh": (
            "PMA 类型取自原始 payload 的 supplement_number（空=原始批准，非空=补充申请）；"
            "510(k) 类型取自 clearance_type。无法解析的记录标记为 unknown，不猜测类型。"
        ),
        "source_fields": ["pma_number", "supplement_number", "supplement_type", "clearance_type"],
    }


def source_catalog(con: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    observed: dict[str, dict[str, Any]] = {}
    if con is not None:
        for row in _rows(
            con,
            "SELECT source, COUNT(*) n, MIN(event_date) first, MAX(event_date) last "
            "FROM events GROUP BY source",
        ):
            observed[row["source"]] = row
    out = []
    for source, meta in SOURCES.items():
        seen = observed.get(source) or {}
        out.append(
            {
                "id": source,
                **meta,
                "observed_count": seen.get("n"),
                "observed_first": seen.get("first"),
                "observed_last": seen.get("last"),
            }
        )
    return out


# ------------------------------------------------------------------------ company
def _company_counts(con: sqlite3.Connection, key: str, kind_filter: str | None = None) -> dict[str, int]:
    prefix, frm, cte_params = company_from([key])
    sql = f"{prefix}SELECT e.kind, COUNT(*) n FROM {frm} WHERE 1=1"
    args: list[Any] = list(cte_params)
    if kind_filter:
        sql += " AND e.kind = ?"
        args.append(kind_filter)
    sql += " GROUP BY e.kind"
    return {row["kind"]: row["n"] for row in _rows(con, sql, args)}


@_memo
def company_kind_counts(key: str) -> dict[str, int]:
    with read() as con:
        return _company_counts(con, key)


@_memo
def company_list(include_all: bool = True) -> list[dict[str, Any]]:
    """Lightweight company directory with real event counts."""
    roster = entities.roster()
    counts: dict[str, dict[str, int]] = {}
    spans: dict[str, tuple[str, str]] = {}
    track_counts: dict[str, int] = {}
    with read() as con:
        for row in _rows(
            con,
            "SELECT company_key, kind, COUNT(*) n, MIN(event_date) first, MAX(event_date) last "
            "FROM events WHERE company_key IS NOT NULL GROUP BY company_key, kind",
        ):
            key = row["company_key"]
            counts.setdefault(key, {})[row["kind"]] = row["n"]
            first, last = row["first"], row["last"]
            old = spans.get(key)
            spans[key] = (
                min(old[0], first) if old and old[0] else (first or (old[0] if old else None)),
                max(old[1], last) if old and old[1] else (last or (old[1] if old else None)),
            )
        for row in _rows(
            con,
            "SELECT company_key, COUNT(DISTINCT track_id) n FROM events "
            "WHERE company_key IS NOT NULL AND track_id IS NOT NULL GROUP BY company_key",
        ):
            track_counts[row["company_key"]] = row["n"]
        for key in entities.EXTRA_ALIAS_COMPANIES:
            prefix, frm, cte_params = company_from([key])
            rows = _rows(
                con,
                f"{prefix}SELECT kind, COUNT(*) n, MIN(event_date) first, MAX(event_date) last "
                f"FROM {frm} GROUP BY kind",
                cte_params,
            )
            merged: dict[str, int] = {}
            first = last = None
            for row in rows:
                merged[row["kind"]] = row["n"]
                first = row["first"] if first is None or (row["first"] and row["first"] < first) else first
                last = row["last"] if last is None or (row["last"] and row["last"] > last) else last
            counts[key] = merged
            spans[key] = (first, last)
            trow = _one(
                con,
                f"{prefix}SELECT COUNT(DISTINCT track_id) FROM {frm} WHERE track_id IS NOT NULL",
                cte_params,
            )
            track_counts[key] = int(trow or 0)

    out = []
    for key, meta in roster.items():
        kinds = counts.get(key, {})
        total = sum(kinds.values())
        if not include_all and not meta.get("featured") and total < 1:
            continue
        if not include_all and not meta.get("featured") and total < 50:
            continue
        first, last = spans.get(key, (None, None))
        out.append(
            {
                "key": key,
                "name_en": meta.get("name_en") or key,
                "name_zh": meta.get("name_zh") or meta.get("name_en") or key,
                "ticker": meta.get("ticker"),
                "exchange": meta.get("exchange"),
                "hq_zh": meta.get("hq_zh"),
                "featured": bool(meta.get("featured")),
                "roster_present": meta.get("roster_present", True),
                "events": total,
                "approvals": kinds.get("510k", 0) + kinds.get("pma", 0),
                "recalls": kinds.get("device_recall", 0),
                "trials": kinds.get("trial", 0),
                "corporate": kinds.get("8k_catalyst", 0),
                "tracks": track_counts.get(key, 0),
                "first_event": first,
                "last_event": last,
            }
        )
    out.sort(key=lambda row: (not row["featured"], -row["events"], row["name_en"]))
    return out


@_memo
def company_coverage(key: str) -> list[dict[str, Any]]:
    prefix, frm, cte_params = company_from([key])
    with read() as con:
        rows = _rows(
            con,
            f"{prefix}SELECT e.source, e.kind, COUNT(*) n, MIN(e.event_date) first, MAX(e.event_date) last, "
            f"MIN(e.available_at) first_available "
            f"FROM {frm} GROUP BY e.source, e.kind ORDER BY n DESC",
            cte_params,
        )
    out = []
    for row in rows:
        meta = SOURCES.get(row["source"], {})
        out.append(
            {
                **row,
                "label_zh": meta.get("label_zh") or row["source"],
                "short_zh": meta.get("short_zh") or row["kind"],
                "market": meta.get("market"),
                "coverage_zh": meta.get("coverage_zh"),
                "caveat_zh": meta.get("caveat_zh"),
            }
        )
    return out


def _track_counts_window(
    con: sqlite3.Connection,
    keys: list[str],
    metric: str,
    start: str,
    end: str,
) -> tuple[dict[str, int], int]:
    prefix, frm, cte_params = company_from(keys)
    kind_sql, kind_params = _kind_marks(metric)
    sql = (
        f"{prefix}SELECT e.track_id AS track, COUNT(*) n FROM {frm} "
        f"WHERE {kind_sql} AND e.event_date >= ? AND e.event_date <= ? "
        f"GROUP BY e.track_id"
    )
    rows = _rows(con, sql, [*cte_params, *kind_params, start, end])
    mapped = {row["track"]: row["n"] for row in rows if row["track"]}
    unmapped = sum(row["n"] for row in rows if not row["track"])
    return mapped, unmapped


def _industry_track_counts(con: sqlite3.Connection, metric: str, start: str, end: str) -> dict[str, int]:
    kind_sql, kind_params = _kind_marks(metric)
    rows = _rows(
        con,
        f"SELECT e.track_id AS track, COUNT(*) n FROM events e "
        f"WHERE {kind_sql} AND e.track_id IS NOT NULL AND e.event_date >= ? AND e.event_date <= ? "
        f"GROUP BY e.track_id",
        [*kind_params, start, end],
    )
    return {row["track"]: row["n"] for row in rows}


def _industry_metric_total(con: sqlite3.Connection, metric: str, start: str, end: str) -> int:
    """All industry records for a metric in a window (mapped + unmapped tracks)."""
    kind_sql, kind_params = _kind_marks(metric)
    value = _one(
        con,
        f"SELECT COUNT(*) FROM events e WHERE {kind_sql} AND e.event_date >= ? AND e.event_date <= ?",
        [*kind_params, start, end],
    )
    return int(value or 0)


def _industry_coverage(con: sqlite3.Connection, metric: str, start: str, end: str) -> dict[str, Any]:
    mapped_total = sum(_industry_track_counts(con, metric, start, end).values())
    all_total = _industry_metric_total(con, metric, start, end)
    return {
        "mapped_records": mapped_total,
        "all_records": all_total,
        "unmapped_records": max(0, all_total - mapped_total),
        "mapping_coverage": (mapped_total / all_total) if all_total else None,
        "start": start,
        "end": end,
    }


def _track_approval_breakdown(
    con: sqlite3.Connection,
    keys: list[str],
    start: str,
    end: str,
) -> dict[str, dict[str, int]]:
    """Per-track original/supplement PMA and Traditional 510(k) counts."""
    prefix, frm, cte_params = company_from(keys)
    rows = _rows(
        con,
        f"""{prefix}SELECT e.track_id AS track,
          SUM(CASE WHEN {_pma_original_sql('e')} THEN 1 ELSE 0 END) AS pma_original,
          SUM(CASE WHEN {_pma_supplement_sql('e')} THEN 1 ELSE 0 END) AS pma_supplement,
          SUM(CASE WHEN {_traditional_510k_sql('e')} THEN 1 ELSE 0 END) AS k510_traditional,
          COUNT(*) AS approvals_total
        FROM {frm}
        WHERE e.kind IN ('510k','pma') AND e.track_id IS NOT NULL
          AND e.event_date >= ? AND e.event_date <= ?
        GROUP BY e.track_id""",
        [*cte_params, start, end],
    )
    return {
        row["track"]: {
            "pma_original": int(row["pma_original"] or 0),
            "pma_supplement": int(row["pma_supplement"] or 0),
            "k510_traditional": int(row["k510_traditional"] or 0),
            "approvals_total": int(row["approvals_total"] or 0),
        }
        for row in rows
        if row["track"]
    }


def _company_first_entries(con: sqlite3.Connection, key: str) -> dict[str, dict[str, Any]]:
    """First *original* approval per track (Traditional 510(k) or original PMA)."""
    prefix, frm, cte_params = company_from([key])
    rows = _rows(
        con,
        f"{prefix}SELECT e.track_id AS track, MIN(e.event_date) first_date, COUNT(*) n "
        f"FROM {frm} WHERE e.track_id IS NOT NULL AND {first_entry_sql('e')} "
        f"GROUP BY e.track_id",
        cte_params,
    )
    return {row["track"]: row for row in rows if row["track"]}


def _company_all_time_firsts(con: sqlite3.Connection, key: str) -> dict[str, dict[str, Any]]:
    """First date of *any* approval record per track (context, not first entry)."""
    prefix, frm, cte_params = company_from([key])
    rows = _rows(
        con,
        f"{prefix}SELECT e.track_id AS track, MIN(e.event_date) first_any_approval "
        f"FROM {frm} WHERE e.track_id IS NOT NULL AND e.kind IN ('510k','pma') "
        f"GROUP BY e.track_id",
        cte_params,
    )
    return {row["track"]: row for row in rows if row["track"]}


@_memo
def company_track_table(key: str, metric: str, start: str, end: str) -> dict[str, Any]:
    """Track-level company/industry comparison on a complete-period window.

    ``recent``/``prior`` are **complete-quarter** counts (the comparison basis);
    ``recent_all``/``prior_all`` are the same slices over the exact requested
    window, including its clipped start/end quarters, and are exposed for
    transparency. Shares always use mapped records as denominators on both the
    company and industry side.
    """
    prior_start, prior_end = previous_window(start, end)
    comparison = comparison_windows(start, end, "quarter")
    analysis_start = comparison["analysis_start"] or start
    analysis_end = comparison["analysis_end"] or end
    prior_analysis_start = comparison["prior_analysis_start"] or prior_start
    prior_analysis_end = comparison["prior_analysis_end"] or prior_end
    with read() as con:
        recent, recent_unmapped = _track_counts_window(con, [key], metric, analysis_start, analysis_end)
        prior, prior_unmapped = _track_counts_window(con, [key], metric, prior_analysis_start, prior_analysis_end)
        recent_all, recent_all_unmapped = _track_counts_window(con, [key], metric, start, end)
        prior_all, prior_all_unmapped = _track_counts_window(con, [key], metric, prior_start, prior_end)
        industry_recent = _industry_track_counts(con, metric, analysis_start, analysis_end)
        industry_prior = _industry_track_counts(con, metric, prior_analysis_start, prior_analysis_end)
        industry_coverage = _industry_coverage(con, metric, analysis_start, analysis_end)
        industry_coverage_prior = _industry_coverage(con, metric, prior_analysis_start, prior_analysis_end)
        firsts = _company_first_entries(con, key)
        first_any = _company_all_time_firsts(con, key)
        breakdown_recent = _track_approval_breakdown(con, [key], analysis_start, analysis_end)
        breakdown_prior = _track_approval_breakdown(con, [key], prior_analysis_start, prior_analysis_end)
    total_recent = sum(recent.values())
    total_prior = sum(prior.values())
    total_recent_all = sum(recent_all.values())
    total_prior_all = sum(prior_all.values())
    industry_total_recent = sum(industry_recent.values())
    industry_total_prior = sum(industry_prior.values())
    rows = []
    for track in set(recent) | set(prior) | set(recent_all) | set(prior_all):
        r = recent.get(track, 0)
        p = prior.get(track, 0)
        r_all = recent_all.get(track, 0)
        p_all = prior_all.get(track, 0)
        ir = industry_recent.get(track, 0)
        ip = industry_prior.get(track, 0)
        delta = r - p
        share_r = (r / total_recent) if total_recent else None
        share_p = (p / total_prior) if total_prior else None
        ind_share_r = (ir / industry_total_recent) if industry_total_recent else None
        first = firsts.get(track)
        first_any_row = first_any.get(track)
        first_date = first["first_date"] if first else None
        breakdown_r = breakdown_recent.get(track, {})
        breakdown_p = breakdown_prior.get(track, {})
        rows.append(
            {
                **track_meta(track),
                "track": track,
                "recent": r,
                "prior": p,
                "recent_all": r_all,
                "prior_all": p_all,
                "delta": delta,
                "pct_change": (delta / p) if p else None,
                "share_recent": share_r,
                "share_prior": share_p,
                "industry_recent": ir,
                "industry_prior": ip,
                "industry_delta": ir - ip,
                "industry_pct_change": ((ir - ip) / ip) if ip else None,
                "industry_share_recent": ind_share_r,
                "first_approval": first_date,
                "first_any_approval": first_any_row["first_any_approval"] if first_any_row else None,
                "first_entry_candidate_count": (first or {}).get("n"),
                "new_in_window": bool(first_date and analysis_start <= first_date <= analysis_end),
                "pma_original_recent": breakdown_r.get("pma_original", 0),
                "pma_supplement_recent": breakdown_r.get("pma_supplement", 0),
                "k510_traditional_recent": breakdown_r.get("k510_traditional", 0),
                "pma_original_prior": breakdown_p.get("pma_original", 0),
                "pma_supplement_prior": breakdown_p.get("pma_supplement", 0),
                "k510_traditional_prior": breakdown_p.get("k510_traditional", 0),
                "z": _poisson_z(r, p),
            }
        )
    rows.sort(key=lambda row: (-row["recent"], -row["prior"]))
    company_all_recent = total_recent_all + recent_all_unmapped
    company_all_prior = total_prior_all + prior_all_unmapped
    return {
        "rows": rows,
        "total_recent": total_recent,
        "total_prior": total_prior,
        "total_recent_all": total_recent_all,
        "total_prior_all": total_prior_all,
        "unmapped_recent": recent_unmapped,
        "unmapped_prior": prior_unmapped,
        "unmapped_recent_all": recent_all_unmapped,
        "unmapped_prior_all": prior_all_unmapped,
        "industry_total_recent": industry_total_recent,
        "industry_total_prior": industry_total_prior,
        "coverage": {
            "company": {
                "recent": {
                    "mapped_records": total_recent,
                    "all_records": company_all_recent,
                    "unmapped_records": recent_all_unmapped,
                    "mapping_coverage": (total_recent / company_all_recent) if company_all_recent else None,
                },
                "prior": {
                    "mapped_records": total_prior,
                    "all_records": company_all_prior,
                    "unmapped_records": prior_all_unmapped,
                    "mapping_coverage": (total_prior / company_all_prior) if company_all_prior else None,
                },
            },
            "industry": {"recent": industry_coverage, "prior": industry_coverage_prior},
        },
        "analysis_window": {
            "start": analysis_start,
            "end": analysis_end,
            "prior_start": prior_analysis_start,
            "prior_end": prior_analysis_end,
            "comparable": comparison["comparable"],
            "granularity": "quarter",
            "periods": comparison["periods"],
            "reason_zh": comparison["reason_zh"],
            "partial_start": comparison["partial_start"],
            "partial_end": comparison["partial_end"],
        },
        "window": {"start": start, "end": end, "prior_start": prior_start, "prior_end": prior_end},
        "metric": metric,
    }


def _poisson_z(recent: int, prior: int) -> float | None:
    denom = math.sqrt(recent + prior)
    if denom <= 0:
        return None
    return round((recent - prior) / denom, 3)


def _series(
    con: sqlite3.Connection,
    *,
    keys: list[str] | None,
    track: str | None,
    metric: str | None,
    start: str,
    end: str,
    granularity: str,
) -> dict[str, dict[str, int]]:
    """Return ``{series_name: {period: count}}`` for the requested slice."""
    period = _period_expr(granularity)
    prefix, frm, cte_params = company_from(keys or [])
    clauses: list[str] = ["e.event_date >= ?", "e.event_date <= ?"]
    params: list[Any] = [*cte_params, start, end]
    if track is not None:
        clauses.append("e.track_id = ?")
        params.append(track)
    groups = ["period"]
    select = [f"{period} AS period"]
    if metric:
        kind_sql, kind_params = _kind_marks(metric)
        clauses.append(kind_sql)
        params.extend(kind_params)
        select.append("'total' AS series")
        groups.append("series")
    else:
        select.append("e.kind AS series")
        groups.append("series")
    sql = (
        f"{prefix}SELECT {', '.join(select)}, COUNT(*) n FROM {frm} "
        f"WHERE {' AND '.join(clauses)} GROUP BY {', '.join(groups)}"
    )
    out: dict[str, dict[str, int]] = {}
    for row in _rows(con, sql, params):
        out.setdefault(row["series"], {})[row["period"]] = row["n"]
    return out


def _fill_series(
    mapping: Mapping[str, Mapping[str, int]],
    periods: Sequence[str],
    start: str,
    end: str,
    granularity: str,
    edge: str,
) -> dict[str, list[dict[str, Any]]]:
    """Fill zero periods and attach explicit completeness flags.

    ``partial`` means the period is clipped by the window at either end;
    ``source_lag_risk`` means the calendar period is complete but ends close to
    the data edge, so the source may still revision/backfill it. They are
    separate fields on purpose.
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for series, values in mapping.items():
        points = []
        for period in periods:
            flags = period_flags(period, granularity, start, end, edge)
            points.append(
                {
                    "period": period,
                    "count": int(values.get(period, 0)),
                    **flags,
                }
            )
        out[series] = points
    return out


def _summarise_points(points: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    complete = [point for point in points if point.get("complete")]
    return {
        "total": sum(int(point["count"]) for point in points),
        "total_complete": sum(int(point["count"]) for point in complete),
        "complete_periods": len(complete),
        "partial_periods": len(points) - len(complete),
        "partial_total": sum(int(point["count"]) for point in points if not point.get("complete")),
        "source_lag_risk_periods": sum(1 for point in points if point.get("source_lag_risk")),
    }


@_memo
def company_series(key: str, metric: str, start: str, end: str, granularity: str = "quarter") -> dict[str, Any]:
    with read() as con:
        data = _series(con, keys=[key], track=None, metric=metric, start=start, end=end, granularity=granularity)
        industry = _industry_track_counts(con, metric, *((complete_window(start, end, granularity) or (start, end))))
    periods = _periods(start, end, granularity)
    points = _fill_series(data, periods, start, end, granularity, data_edge()).get("total", [])
    summary = _summarise_points(points)
    completeness = window_completeness(start, end, granularity)
    return {
        "granularity": granularity,
        "start": start,
        "end": end,
        "metric": metric,
        "points": points,
        **summary,
        "completeness": completeness,
        "covered_tracks": len(industry),
    }


def _milestone_event(con: sqlite3.Connection, key: str, kind: str) -> dict[str, Any] | None:
    prefix, frm, cte_params = company_from([key])
    row = con.execute(
        f"{prefix}SELECT e.* FROM {frm} WHERE e.kind = ? AND e.event_date IS NOT NULL "
        f"ORDER BY e.event_date ASC, e.event_id ASC LIMIT 1",
        [*cte_params, kind],
    ).fetchone()
    return dict(row) if row else None


def _event_brief(row: Mapping[str, Any]) -> dict[str, Any]:
    company = entities.event_company_fields(row)
    track = track_meta(row.get("track_id"))
    classification = approval_classification(row.get("kind"), row.get("payload"))
    return {
        "event_id": row.get("event_id"),
        "event_date": row.get("event_date"),
        "kind": row.get("kind"),
        "kind_label_zh": KIND_LABELS.get(str(row.get("kind") or ""), row.get("kind")),
        "source": row.get("source"),
        "title": row.get("title"),
        "url": row.get("url"),
        "company_key": company["company_key"],
        "company_name_zh": company["company_name_zh"],
        "company_match": company["company_match"],
        "track_id": track["id"],
        "track_name_zh": track["name_zh"],
        "product_code": row.get("product_code"),
        "applicant_raw": row.get("applicant_raw"),
        "available_at": row.get("available_at"),
        **classification,
    }


def _first_matching_event(
    con: sqlite3.Connection,
    key: str,
    condition: str,
    params: Sequence[Any] = (),
) -> dict[str, Any] | None:
    prefix, frm, cte_params = company_from([key])
    row = con.execute(
        f"{prefix}SELECT e.* FROM {frm} WHERE ({condition}) AND e.event_date IS NOT NULL "
        f"ORDER BY e.event_date ASC, e.event_id ASC LIMIT 1",
        [*cte_params, *params],
    ).fetchone()
    return dict(row) if row else None


@_memo
def company_milestones(key: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with read() as con:
        milestones = [
            (_pma_original_sql("e"), (), "首个原始 PMA 批准"),
            (_traditional_510k_sql("e"), (), "首个 Traditional 510(k)"),
            (_pma_supplement_sql("e"), (), "首个 PMA 补充申请"),
            ("e.kind = ?", ("trial",), "首个临床试验注册"),
            ("e.kind = ?", ("device_recall",), "首个召回记录"),
            ("e.kind = ?", ("8k_catalyst",), "首个 8-K 事件"),
        ]
        for condition, params, label in milestones:
            row = _first_matching_event(con, key, condition, params)
            if not row:
                continue
            brief = _event_brief(row)
            brief["label_zh"] = label
            out.append(brief)
        firsts = _company_first_entries(con, key)
        first_any = _company_all_time_firsts(con, key)
        top = sorted(firsts.items(), key=lambda item: item[1]["first_date"])
        for track, info in top[:6]:
            meta = track_meta(track)
            any_row = first_any.get(track)
            out.append(
                {
                    "event_id": None,
                    "event_date": info["first_date"],
                    "kind": "track_first",
                    "source": "derived",
                    "title": (
                        f"{meta['name_zh']}赛道数据覆盖期内首条原始批准"
                        f"（Traditional 510(k) 或原始 PMA）"
                    ),
                    "url": None,
                    "company_key": key,
                    "company_name_zh": entities.display_name(key),
                    "company_match": "derived",
                    "track_id": track,
                    "track_name_zh": meta["name_zh"],
                    "product_code": None,
                    "applicant_raw": None,
                    "available_at": info["first_date"],
                    "first_any_approval": any_row["first_any_approval"] if any_row else None,
                    "label_zh": f"数据覆盖期内首次观察到原始批准：{meta['name_zh']}",
                    "derived": True,
                    "approval_type": "first_entry_candidate",
                    "approval_type_label_zh": "首次进入候选（原始批准）",
                }
            )
    seen: set[tuple] = set()
    unique = []
    for item in out:
        marker = (item.get("event_id"), item.get("kind"), item.get("track_id"))
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(item)
    unique.sort(key=lambda item: item.get("event_date") or "")
    return unique


def _recent_events(con: sqlite3.Connection, key: str, limit: int = 12) -> list[dict[str, Any]]:
    prefix, frm, cte_params = company_from([key])
    rows = _rows(
        con,
        f"{prefix}SELECT e.* FROM {frm} WHERE e.event_date IS NOT NULL "
        f"ORDER BY e.event_date DESC, e.event_id ASC LIMIT ?",
        [*cte_params, limit],
    )
    return [_event_brief(row) for row in rows]


def _coverage_span(coverage: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    firsts = [row["first"] for row in coverage if row.get("first")]
    lasts = [row["last"] for row in coverage if row.get("last")]
    return {
        "first": min(firsts) if firsts else None,
        "last": max(lasts) if lasts else None,
        "sources": len(coverage),
        "events": sum(int(row.get("n") or 0) for row in coverage),
    }


@_memo
def company_profile(key: str, years: int = 5) -> dict[str, Any]:
    meta = entities.company_meta(key)
    if not meta:
        raise KeyError(f"unknown company: {key}")
    start, end = resolve_window(years)
    prior_start, prior_end = previous_window(start, end)
    completeness = window_completeness(start, end, "quarter")
    analysis_start = completeness["analysis_start"] or start
    analysis_end = completeness["analysis_end"] or end
    kind_counts = company_kind_counts(key)
    coverage = company_coverage(key)
    tracks = company_track_table(key, "approvals", start, end)
    series_approvals = company_series(key, "approvals", start, end, "quarter")
    with read() as con:
        recent = _recent_events(con, key)
        # per-kind annual series for the same window
        kind_series = _series(con, keys=[key], track=None, metric=None, start=start, end=end, granularity="year")
        periods = _periods(start, end, "year")
        filled = _fill_series(kind_series, periods, start, end, "year", data_edge())
        window_pathway = company_pathway_window(key, analysis_start, analysis_end)
        all_time_pathway = company_pathway_window(key, "1900-01-01", end)
        industry_window = _industry_coverage(con, "approvals", analysis_start, analysis_end)
    total_window = tracks["total_recent"]  # mapped, complete-period basis
    total_prior = tracks["total_prior"]
    total_window_all = tracks["total_recent_all"]
    total_prior_all = tracks["total_prior_all"]
    window_breakdown = window_pathway
    all_time_breakdown = all_time_pathway
    pma_window_total = (
        window_breakdown.get("pma_original", 0)
        + window_breakdown.get("pma_supplement", 0)
        + window_breakdown.get("pma_unknown", 0)
    )
    k510_window_total = sum(
        window_breakdown.get(k, 0)
        for k in ("k510_traditional", "k510_special", "k510_abbreviated", "k510_other", "k510_unknown")
    )
    approvals_window_total = pma_window_total + k510_window_total
    pma_all_total = (
        all_time_breakdown.get("pma_original", 0)
        + all_time_breakdown.get("pma_supplement", 0)
        + all_time_breakdown.get("pma_unknown", 0)
    )
    k510_all_total = sum(
        all_time_breakdown.get(k, 0)
        for k in ("k510_traditional", "k510_special", "k510_abbreviated", "k510_other", "k510_unknown")
    )
    approvals_all_total = pma_all_total + k510_all_total
    total_events_all = sum(kind_counts.values()) or 1
    claims = (
        _company_claims(key, meta, tracks, analysis_start, analysis_end)
        if tracks["analysis_window"]["comparable"]
        else []
    )
    return {
        "key": key,
        "info": {
            **meta,
            "display_name_zh": meta.get("name_zh") or meta.get("name_en"),
            "display_name_en": meta.get("name_en") or key,
            "featured": bool(meta.get("featured")),
            "roster_present": meta.get("roster_present", True),
        },
        "window": {
            "start": start,
            "end": end,
            "prior_start": prior_start,
            "prior_end": prior_end,
            "years": years,
            "data_edge": data_edge(),
            "completeness": completeness,
        },
        "headline": {
            "events_all_time": sum(kind_counts.values()),
            "approvals_all_time": kind_counts.get("510k", 0) + kind_counts.get("pma", 0),
            "approvals_window": total_window,
            "approvals_window_mapped": total_window,
            "approvals_window_all": total_window_all + tracks["unmapped_recent_all"],
            "approvals_window_complete": total_window + tracks["unmapped_recent"],
            "approvals_prior": total_prior,
            "approvals_prior_all": total_prior_all + tracks["unmapped_prior_all"],
            "approvals_prior_complete": total_prior + tracks["unmapped_prior"],
            "unmapped_window": tracks["unmapped_recent_all"],
            "unmapped_prior": tracks["unmapped_prior_all"],
            "unmapped_window_complete": tracks["unmapped_recent"],
            "window_basis_zh": (
                "近窗/前窗的比较口径为完整自然季度；表格另列窗口全部记录（含起止不完整季度）。"
                "未映射到赛道的记录单独列出，未映射不等于零活动。"
            ),
            "delta": total_window - total_prior,
            "pct_change": ((total_window - total_prior) / total_prior) if total_prior else None,
            "tracks_active": len([row for row in tracks["rows"] if row["recent"] > 0]),
            "first_event": _coverage_span(coverage)["first"],
            "last_event": _coverage_span(coverage)["last"],
            "recalls_all_time": kind_counts.get("device_recall", 0),
            "trials_all_time": kind_counts.get("trial", 0),
            "pma_original_all_time": all_time_breakdown.get("pma_original", 0),
            "pma_supplement_all_time": all_time_breakdown.get("pma_supplement", 0),
            "pma_unknown_all_time": all_time_breakdown.get("pma_unknown", 0),
            "pma_original_window": window_breakdown.get("pma_original", 0),
            "pma_supplement_window": window_breakdown.get("pma_supplement", 0),
            "pma_unknown_window": window_breakdown.get("pma_unknown", 0),
            "pathway_mix": {
                "pma": (pma_window_total / approvals_window_total) if approvals_window_total else None,
                "510k": (
                    (approvals_window_total - pma_window_total) / approvals_window_total
                    if approvals_window_total
                    else None
                ),
                "basis": "window_approvals_only",
                "window": {"start": analysis_start, "end": analysis_end},
                "note_zh": (
                    "监管路径结构按所选窗口的完整周期计算，分母为 510(k)+PMA 记录；"
                    "召回、试验、8-K 不计入。"
                ),
            },
            "pathway_mix_counts": {
                **window_breakdown,
                "window": {"start": analysis_start, "end": analysis_end},
            },
            "pathway_mix_all_time": {
                "pma": (pma_all_total / approvals_all_total) if approvals_all_total else None,
                "510k": (k510_all_total / approvals_all_total) if approvals_all_total else None,
                "basis": "all_time_approvals_only",
                "note_zh": "全历史审批路径结构，不能解释为当前研究窗口内的结构。",
            },
            "pma_original_share_of_pma_all_time": (
                all_time_breakdown.get("pma_original", 0) / pma_all_total if pma_all_total else None
            ),
            "pma_breakdown": {
                "window": {
                    **window_breakdown,
                    "window": {"start": analysis_start, "end": analysis_end},
                },
                "all_time": {**all_time_breakdown, "end": end},
                "note_zh": (
                    "原始 PMA 批准是新技术/新器械进入市场的候选事件；PMA 补充申请是已批准器械的"
                    "变更（如工艺、标签、适应证扩展），两者都计入监管活动，但不能都当作“新器械”。"
                ),
            },
            "evidence_mix_of_all": {
                "pma": pma_all_total / total_events_all,
                "510k": kind_counts.get("510k", 0) / total_events_all,
                "recalls": kind_counts.get("device_recall", 0) / total_events_all,
            },
            "industry_coverage": industry_window,
        },
        "coverage": coverage,
        "coverage_span": _coverage_span(coverage),
        "tracks": tracks,
        "series": {
            "approvals": series_approvals,
            "by_kind_year": {
                "periods": periods,
                "series": {
                    kind: filled.get(kind, [])
                    for kind in ("510k", "pma", "device_recall", "trial", "8k_catalyst")
                    if kind in filled
                },
            },
        },
        "milestones": company_milestones(key),
        "recent_events": recent,
        "claims": claims,
        "entity_review": entities.company_alias_review([key]),
        "limitations": _company_limitations(meta, coverage, tracks),
        "evidence_tiers": EVIDENCE_TIERS,
        "flags": {
            "roster_absent": meta.get("roster_present", True) is False,
            "track_mapping_note": (
                f"该企业在窗口内的审批记录中有 {tracks['unmapped_recent_all']} 条未映射到技术赛道"
                if tracks["unmapped_recent_all"]
                else None
            ),
            "pma_mix_note_zh": (
                f"PMA 记录中原始批准 {all_time_breakdown.get('pma_original', 0)} 条、"
                f"补充申请 {all_time_breakdown.get('pma_supplement', 0)} 条；"
                "审批总量不等于新器械数量。"
            ),
        },
    }


def _company_limitations(meta: Mapping[str, Any], coverage: Sequence[Mapping[str, Any]], tracks: Mapping[str, Any]) -> list[dict[str, str]]:
    keys = ["us_only", "record_not_product", "not_prediction", "coverage_change"]
    if meta.get("roster_present", True) is False or meta.get("key") in entities.EXTRA_ALIAS_COMPANIES:
        keys.append("entity_mapping")
    if meta.get("key") in ("mindray", "draeger"):
        keys.append("no_global_rank")
    if int(tracks.get("unmapped_recent") or 0) > 0:
        keys.append("track_mapping")
    if any(row.get("kind") == "device_recall" for row in coverage):
        keys.append("recall_not_tech")
    return [{"id": key, "text_zh": LIMITATIONS[key]} for key in keys]


def _company_claims(
    key: str,
    meta: Mapping[str, Any],
    tracks: Mapping[str, Any],
    start: str,
    end: str,
) -> list[dict[str, Any]]:
    """Deterministic, evidence-linked statements (Observed Change tier).

    ``start``/``end`` are the complete-period comparison window. The rules are
    deliberately conservative: a claim is only made when both windows have enough
    records, and the text always states the industry comparison so a company
    specific increase cannot be mistaken for a strategic signal when the whole
    track grew. PMA supplements are disclosed next to the count because they are
    regulatory activity, not a new device entering the market.
    """
    claims: list[dict[str, Any]] = []
    begin = _parse(start)
    finish = _parse(end)
    years = max(1, round((finish - begin).days / 365)) if begin and finish else 5
    window_text = f"{start} 至 {end}（完整自然季度，约 {years} 年）"
    rows = tracks.get("rows") or []
    for row in rows:
        recent, prior = row["recent"], row["prior"]
        if recent + prior < 6:
            continue
        if recent < 3 and prior < 3:
            continue
        if recent > prior:
            direction = "up"
        elif recent < prior:
            direction = "down"
        else:
            direction = "flat"
        if direction == "flat":
            continue
        pct = row.get("pct_change")
        ind_pct = row.get("industry_pct_change")
        share_r, share_p = row.get("share_recent"), row.get("share_prior")
        share_change = None
        if share_r is not None and share_p is not None:
            share_change = share_r - share_p
        confidence = "high" if (recent + prior) >= 30 and min(recent, prior) >= 5 else ("medium" if (recent + prior) >= 10 else "low")
        low_volume = min(recent, prior) < 5
        if low_volume:
            confidence = "low"
            statement = (
                f"在 {window_text} 内，{meta.get('name_zh')}在{row['name_zh']}赛道的公开审批记录由 {prior} 条变为 {recent} 条；"
                f"两期合计仅 {recent + prior} 条，绝对数量过少，不足以判断趋势或相对地位，"
                f"这里只把它作为可逐条核查的观察记录列出。"
            )
        elif direction == "up":
            if prior == 0:
                first_note = (
                    f"；该赛道数据覆盖期内首条原始批准为 {row['first_approval']}"
                    if row.get("first_approval") and row.get("new_in_window")
                    else f"；该赛道数据覆盖期内首条原始批准为 {row['first_approval']}（早于本窗口）"
                    if row.get("first_approval")
                    else ""
                )
                statement = (
                    f"在 {window_text} 内，{meta.get('name_zh')}在{row['name_zh']}赛道出现 {recent} 条公开审批记录，"
                    f"而前一个同长度时间窗内为 0 条{first_note}；"
                    "首次被数据库观察到不等于该企业首次进入该技术领域。"
                )
            elif ind_pct is not None and ind_pct > 0.15 and (pct or 0) <= ind_pct * 1.2:
                statement = (
                    f"在 {window_text} 内，{meta.get('name_zh')}在{row['name_zh']}赛道的公开审批记录由 {prior} 条增至 {recent} 条"
                    f"（{pct:+.0%}）；同期该赛道全行业增长 {ind_pct:+.0%}，企业与行业同步上升，"
                    f"其在本赛道的记录份额由 {share_p:.1%} 变为 {share_r:.1%}，相对地位基本持平。"
                )
            else:
                industry_part = (
                    f"同期该赛道全行业由 {row['industry_prior']} 条变为 {row['industry_recent']} 条（{ind_pct:+.0%}）"
                    if row.get("industry_prior")
                    else "同期该赛道全行业记录极少，无法给出稳定的行业对照"
                )
                statement = (
                    f"在 {window_text} 内，{meta.get('name_zh')}在{row['name_zh']}赛道的公开审批记录由 {prior} 条增至 {recent} 条"
                    f"（{pct:+.0%}）；{industry_part}。该企业在本赛道的记录份额由 {share_p:.1%} 变为 {share_r:.1%}。"
                )
        else:
            industry_part = (
                f"同期该赛道全行业变化 {ind_pct:+.0%}" if ind_pct is not None else "同期该赛道行业对照不足"
            )
            statement = (
                f"在 {window_text} 内，{meta.get('name_zh')}在{row['name_zh']}赛道的公开审批记录由 {prior} 条降至 {recent} 条"
                f"（{pct:+.0%}）；{industry_part}，其在本赛道的记录份额由 {share_p:.1%} 变为 {share_r:.1%}。"
            )
        caveats = [
            "计数为美国 FDA 公开记录条数，不等于产品数或创新能力。",
            "对照窗口为紧邻的等长历史窗口，且只使用完整自然季度，属于描述性比较，不做因果推断。",
        ]
        if row.get("industry_pct_change") is None:
            caveats.append("该赛道历史记录过少，行业对照不稳定。")
        if str(meta.get("key")) in ("mindray", "draeger"):
            caveats.append("美国记录不代表该企业全球活动；赛道映射只覆盖部分记录。")
        supplement_recent = int(row.get("pma_supplement_recent") or 0)
        if supplement_recent:
            caveats.append(
                f"该赛道完整周期内审批记录含 PMA 补充申请 {supplement_recent} 条、"
                f"原始 PMA 批准 {int(row.get('pma_original_recent') or 0)} 条；"
                "补充申请是已上市器械的变更，不代表新器械进入。"
            )
        claims.append(
            {
                "claim_id": f"{key}:{row['track']}:approvals:{years}y",
                "tier": "observed",
                "tier_label_zh": EVIDENCE_TIERS["observed"]["label_zh"],
                "company": key,
                "track": row["track"],
                "track_name_zh": row["name_zh"],
                "direction": direction,
                "statement_zh": statement,
                "metrics": {
                    "metric": "approvals",
                    "recent": recent,
                    "prior": prior,
                    "delta": row["delta"],
                    "pct_change": pct,
                    "industry_recent": row.get("industry_recent"),
                    "industry_prior": row.get("industry_prior"),
                    "industry_pct_change": ind_pct,
                    "share_recent": share_r,
                    "share_prior": share_p,
                    "share_change": share_change,
                    "z": row.get("z"),
                    "first_approval": row.get("first_approval"),
                    "first_any_approval": row.get("first_any_approval"),
                    "pma_original_recent": row.get("pma_original_recent"),
                    "pma_supplement_recent": row.get("pma_supplement_recent"),
                    "k510_traditional_recent": row.get("k510_traditional_recent"),
                    "low_volume": low_volume,
                    "basis": "complete_quarters",
                },
                "window": {
                    "recent_start": start,
                    "recent_end": end,
                    "prior_start": tracks["analysis_window"]["prior_start"],
                    "prior_end": tracks["analysis_window"]["prior_end"],
                    "years": years,
                    "basis": "complete_quarters",
                },
                "evidence_params": {
                    "company": key,
                    "track": row["track"],
                    "metric": "approvals",
                    "recent_start": start,
                    "recent_end": end,
                    "prior_start": tracks["analysis_window"]["prior_start"],
                    "prior_end": tracks["analysis_window"]["prior_end"],
                },
                "confidence": confidence,
                "caveats": caveats,
            }
        )
    claims.sort(key=lambda c: (c["confidence"] != "high", -abs(c["metrics"]["delta"] or 0)))
    return claims[:8]


# ---------------------------------------------------------------------------- radar
def _quarter_list(start: str, end: str) -> list[str]:
    return _periods(start, end, "quarter")


def _signal_for_counts(points: Sequence[Mapping[str, Any]], baseline_quarters: int = 8) -> dict[str, Any] | None:
    counts = [int(p["count"]) for p in points if not p.get("partial")]
    if len(counts) < baseline_quarters + 1:
        return None
    trailing = counts[-(baseline_quarters + 1):-1]
    current = counts[-1]
    mean = sum(trailing) / len(trailing)
    var = sum((x - mean) ** 2 for x in trailing) / max(1, len(trailing) - 1)
    sd = math.sqrt(var)
    if sd <= 0:
        return None
    z = round((current - mean) / sd, 2)
    return {
        "z": z,
        "current": current,
        "baseline_mean": round(mean, 2),
        "baseline_sd": round(sd, 2),
        "baseline_quarters": baseline_quarters,
        "direction": "up" if z > 0 else "down",
        "flagged": abs(z) >= 2.5 and current >= 5,
    }


def _year_windows(years: int = 3) -> dict[str, Any]:
    start, end = resolve_window(years)
    prior_start, prior_end = previous_window(start, end)
    comparison = comparison_windows(start, end, "quarter")
    return {
        "start": start,
        "end": end,
        "prior_start": prior_start,
        "prior_end": prior_end,
        "analysis_start": comparison["analysis_start"] or start,
        "analysis_end": comparison["analysis_end"] or end,
        "prior_analysis_start": comparison["prior_analysis_start"] or prior_start,
        "prior_analysis_end": comparison["prior_analysis_end"] or prior_end,
        "completeness": comparison,
        "periods": comparison["periods"],
        "years": years,
    }


@_memo
def radar_overview(years: int = 3) -> dict[str, Any]:
    window = _year_windows(years)
    start, end = window["start"], window["end"]
    analysis_start, analysis_end = window["analysis_start"], window["analysis_end"]
    prior_analysis_start, prior_analysis_end = window["prior_analysis_start"], window["prior_analysis_end"]
    with read() as con:
        recent = _industry_track_counts(con, "approvals", analysis_start, analysis_end)
        prior = _industry_track_counts(con, "approvals", prior_analysis_start, prior_analysis_end)
        coverage_now = _industry_coverage(con, "approvals", analysis_start, analysis_end)
        coverage_prior = _industry_coverage(con, "approvals", prior_analysis_start, prior_analysis_end)
        mapped_total = coverage_now["mapped_records"]
        unmapped_total = coverage_now["unmapped_records"]
        # quarterly series per track (last 10 years, flags mark clipped/source-lag periods)
        series_start = (date.fromisoformat(end) - timedelta(days=3650)).isoformat()
        rows = _rows(
            con,
            "SELECT e.track_id track, "
            + _period_expr("quarter")
            + " period, COUNT(*) n FROM events e WHERE e.kind IN ('510k','pma') "
            "AND e.track_id IS NOT NULL AND e.event_date >= ? AND e.event_date <= ? "
            "GROUP BY 1, 2",
            [series_start, end],
        )
        comp_rows = _rows(
            con,
            "SELECT e.track_id track, e.company_key company, COUNT(*) n FROM events e "
            "WHERE e.kind IN ('510k','pma') AND e.track_id IS NOT NULL "
            "AND e.event_date >= ? AND e.event_date <= ? AND e.company_key IS NOT NULL "
            "GROUP BY 1, 2 ORDER BY n DESC",
            [analysis_start, analysis_end],
        )
        comp_extra = {}
        for key in entities.EXTRA_ALIAS_COMPANIES:
            prefix, frm, cte_params = company_from([key])
            for row in _rows(
                con,
                f"{prefix}SELECT e.track_id track, COUNT(*) n FROM {frm} "
                f"WHERE e.kind IN ('510k','pma') AND e.track_id IS NOT NULL "
                f"AND e.event_date >= ? AND e.event_date <= ? GROUP BY 1",
                [*cte_params, analysis_start, analysis_end],
            ):
                comp_extra[(row["track"], key)] = row["n"]
    periods = _quarter_list(series_start, end)
    by_track_series: dict[str, dict[str, int]] = {}
    for row in rows:
        by_track_series.setdefault(row["track"], {})[row["period"]] = row["n"]
    company_by_track: dict[str, list[dict[str, Any]]] = {}
    for row in comp_rows:
        company_by_track.setdefault(row["track"], []).append({"company": row["company"], "n": row["n"]})
    for (track, key), n in comp_extra.items():
        company_by_track.setdefault(track, []).append({"company": key, "n": n})

    domains = []
    for domain in RADAR_DOMAINS:
        track_stats = []
        for track in domain["tracks"]:
            series = by_track_series.get(track, {})
            points = _fill_series({track: series}, periods, series_start, end, "quarter", data_edge())[track]
            signal = _signal_for_counts(points)
            companies = company_by_track.get(track, [])
            companies.sort(key=lambda item: -item["n"])
            r, p = recent.get(track, 0), prior.get(track, 0)
            track_stats.append(
                {
                    **track_meta(track),
                    "track": track,
                    "recent": r,
                    "prior": p,
                    "delta": r - p,
                    "pct_change": ((r - p) / p) if p else None,
                    "spark": points[-12:],
                    "signal": signal,
                    "companies_active": len(companies),
                    "top_companies": [
                        {"company": item["company"], "name_zh": entities.display_name(item["company"]), "n": item["n"]}
                        for item in companies[:5]
                    ],
                }
            )
        track_stats.sort(key=lambda row: -row["recent"])
        recent_total = sum(t["recent"] for t in track_stats)
        prior_total = sum(t["prior"] for t in track_stats)
        companies_active = set()
        for track_stat in track_stats:
            companies_active.update(c["company"] for c in company_by_track.get(track_stat["track"], []))
        domains.append(
            {
                **domain,
                "recent": recent_total,
                "prior": prior_total,
                "delta": recent_total - prior_total,
                "pct_change": ((recent_total - prior_total) / prior_total) if prior_total else None,
                "tracks": track_stats,
                "companies_active": len(companies_active),
                "signal_tracks": [t["track"] for t in track_stats if t.get("signal", {} ) and t["signal"].get("flagged")],
            }
        )
    domains.sort(key=lambda d: -d["recent"])
    return {
        "window": window,
        "domains": domains,
        "mapped_records": mapped_total,
        "unmapped_records": unmapped_total,
        "track_mapping_coverage": coverage_now["mapping_coverage"],
        "mapping_coverage": {"recent": coverage_now, "prior": coverage_prior},
        "method": {
            "signal": (
                "以完整季度计数相对前 8 个季度均值的 z 分数；|z|≥2.5 且当前季度≥5 条时标记为统计探测信号。"
                "起止不完整季度不参与信号基线。"
            ),
            "comparison": "recent/prior 使用完整自然季度口径；窗口起止所在的不完整季度只展示、不参与同比。",
            "caveat": "统计探测只说明记录数偏离历史基线，不证明存在真实技术变化，也不是预测。",
        },
    }


@_memo
def radar_track(track: str, years: int = 10) -> dict[str, Any]:
    meta = track_meta(track)
    if not track_rows().get(track):
        raise KeyError(f"unknown track: {track}")
    start, end = resolve_window(years)
    prior_start, prior_end = previous_window(start, end)
    comparison = comparison_windows(start, end, "quarter")
    analysis_start = comparison["analysis_start"] or start
    analysis_end = comparison["analysis_end"] or end
    prior_analysis_start = comparison["prior_analysis_start"] or prior_start
    prior_analysis_end = comparison["prior_analysis_end"] or prior_end
    domain = DOMAIN_BY_ID.get(meta.get("domain") or "", None)
    with read() as con:
        series_map = _series(con, keys=None, track=track, metric=None, start=start, end=end, granularity="quarter")
        periods = _quarter_list(start, end)
        filled = _fill_series(series_map, periods, start, end, "quarter", data_edge())
        approvals_points = []
        for index, period in enumerate(periods):
            value = sum(filled[kind][index]["count"] for kind in ("510k", "pma") if kind in filled)
            flags = (
                filled["510k"][index]
                if "510k" in filled
                else filled["pma"][index]
                if "pma" in filled
                else period_flags(period, "quarter", start, end, data_edge())
            )
            approvals_points.append(
                {
                    "period": period,
                    "count": value,
                    "partial": flags.get("partial", True),
                    "complete": flags.get("complete", False),
                    "source_lag_risk": flags.get("source_lag_risk", False),
                }
            )
        summarised = _summarise_points(approvals_points)
        recent = _one(
            con,
            "SELECT COUNT(*) FROM events WHERE track_id = ? AND kind IN ('510k','pma') "
            "AND event_date >= ? AND event_date <= ?",
            [track, analysis_start, analysis_end],
        )
        prior = _one(
            con,
            "SELECT COUNT(*) FROM events WHERE track_id = ? AND kind IN ('510k','pma') "
            "AND event_date >= ? AND event_date <= ?",
            [track, prior_analysis_start, prior_analysis_end],
        )
        recent_all = _one(
            con,
            "SELECT COUNT(*) FROM events WHERE track_id = ? AND kind IN ('510k','pma') "
            "AND event_date >= ? AND event_date <= ?",
            [track, start, end],
        )
        prior_all = _one(
            con,
            "SELECT COUNT(*) FROM events WHERE track_id = ? AND kind IN ('510k','pma') "
            "AND event_date >= ? AND event_date <= ?",
            [track, prior_start, prior_end],
        )
        comp_rows = _rows(
            con,
            "SELECT e.company_key company, COUNT(*) n, MIN(e.event_date) first, MAX(e.event_date) last "
            "FROM events e WHERE e.track_id = ? AND e.kind IN ('510k','pma') "
            "AND e.event_date >= ? AND e.event_date <= ? AND e.company_key IS NOT NULL "
            "GROUP BY 1 ORDER BY n DESC",
            [track, analysis_start, analysis_end],
        )
        for key in entities.EXTRA_ALIAS_COMPANIES:
            prefix, frm, cte_params = company_from([key])
            row = con.execute(
                f"{prefix}SELECT COUNT(*) n, MIN(e.event_date) first, MAX(e.event_date) last FROM {frm} "
                f"WHERE e.track_id = ? AND e.kind IN ('510k','pma') "
                f"AND e.event_date >= ? AND e.event_date <= ?",
                [*cte_params, track, analysis_start, analysis_end],
            ).fetchone()
            if row and row["n"]:
                comp_rows.append({"company": key, "n": row["n"], "first": row["first"], "last": row["last"]})
        comp_rows.sort(key=lambda row: -row["n"])
        # first *original* approval per company in this track (Traditional 510k / original PMA)
        first_rows = _rows(
            con,
            "SELECT e.company_key company, MIN(e.event_date) first FROM events e "
            "WHERE e.track_id = ? AND e.company_key IS NOT NULL AND " + first_entry_sql("e") +
            " GROUP BY 1",
            [track],
        )
        first_by_company = {row["company"]: row["first"] for row in first_rows}
        for key in entities.EXTRA_ALIAS_COMPANIES:
            prefix, frm, cte_params = company_from([key])
            value = _one(
                con,
                f"{prefix}SELECT MIN(e.event_date) FROM {frm} WHERE e.track_id = ? AND {first_entry_sql('e')}",
                [*cte_params, track],
            )
            if value:
                first_by_company[key] = value
        entrants = []
        for row in comp_rows:
            first = first_by_company.get(row["company"])
            if first and analysis_start <= first <= analysis_end:
                entrants.append(
                    {
                        "company": row["company"],
                        "name_zh": entities.display_name(row["company"]),
                        "first_date": first,
                        "n": row["n"],
                    }
                )
        entrants.sort(key=lambda item: item["first_date"])
        signals = []
        baseline_quarters = 8
        for index, point in enumerate(approvals_points):
            if point["partial"]:
                continue
            history = [p["count"] for p in approvals_points[: index + 1] if p["complete"]]
            signal = _signal_for_counts([{"count": c, "partial": False} for c in history], baseline_quarters)
            if signal and signal["flagged"]:
                signals.append({"period": point["period"], **signal})
        signals = signals[-6:]
        events = _rows(
            con,
            "SELECT e.* FROM events e WHERE e.track_id = ? AND e.kind IN ('510k','pma') "
            "AND e.event_date >= ? AND e.event_date <= ? ORDER BY e.event_date DESC LIMIT 30",
            [track, start, end],
        )
        industry_mapped = _one(
            con,
            "SELECT COUNT(*) FROM events WHERE track_id = ? AND kind IN ('510k','pma')",
            [track],
        )
        track_all_total = _one(
            con,
            "SELECT COUNT(*) FROM events WHERE track_id = ? AND kind IN ('510k','pma') "
            "AND event_date >= ? AND event_date <= ?",
            [track, analysis_start, analysis_end],
        )
        track_bad = _one(
            con,
            "SELECT COUNT(*) FROM events WHERE track_id = ? AND kind='pma' "
            "AND NOT json_valid(payload) AND event_date >= ? AND event_date <= ?",
            [track, analysis_start, analysis_end],
        )
    attributed_recent = sum(int(row["n"]) for row in comp_rows)
    unattributed_recent = max(0, int(recent or 0) - attributed_recent)
    totals_recent = int(recent or 0)
    totals_prior = int(prior or 0)
    return {
        "track": meta,
        "domain": domain,
        "window": {
            "start": start,
            "end": end,
            "prior_start": prior_start,
            "prior_end": prior_end,
            "analysis_start": analysis_start,
            "analysis_end": analysis_end,
            "prior_analysis_start": prior_analysis_start,
            "prior_analysis_end": prior_analysis_end,
            "years": years,
            "completeness": comparison,
            "periods": comparison["periods"],
        },
        "totals": {
            "recent": totals_recent,
            "prior": totals_prior,
            "delta": totals_recent - totals_prior,
            "pct_change": ((totals_recent - totals_prior) / totals_prior) if totals_prior else None,
            "recent_all": int(recent_all or 0),
            "prior_all": int(prior_all or 0),
            "series_total": summarised["total"],
            "series_total_complete": summarised["total_complete"],
            "partial_total": summarised["partial_total"],
            "all_time": int(industry_mapped or 0),
            "pma_unknown": int(track_bad or 0),
        },
        "attribution": {
            "attributed_recent": attributed_recent,
            "unattributed_recent": unattributed_recent,
            "attributed_share": (attributed_recent / totals_recent) if totals_recent else None,
            "track_total_records_recent": int(track_all_total or 0),
            "note_zh": (
                "企业构成只统计能归到具体企业的记录；未归属记录仍计入赛道总量与份额分母，"
                "因此企业份额之和不等于 100%。"
            ),
        },
        "series": {
            "periods": periods,
            "approvals": approvals_points,
            "by_kind": {kind: filled.get(kind, []) for kind in ("510k", "pma")},
        },
        "companies": [
            {
                "company": row["company"],
                "name_zh": entities.display_name(row["company"]),
                "n": row["n"],
                "share": (row["n"] / totals_recent) if totals_recent else None,
                "first": row["first"],
                "last": row["last"],
                "featured": row["company"] in FEATURED_KEYS,
            }
            for row in comp_rows
        ],
        "entrants": entrants,
        "signals": signals,
        "events": [_event_brief(row) for row in events],
        "method": {
            "signal": "季度审批记录数相对前 8 季度均值的 z 分数；|z|≥2.5 且计数≥5 时标记；不完整季度不进入基线。",
            "entrant": (
                "企业在本窗口内出现该赛道数据覆盖期内的首条原始批准（Traditional 510(k) 或原始 PMA）；"
                "PMA 补充申请与 Special/Abbreviated 510(k) 不计入首次进入。"
            ),
            "comparison": "recent/prior 使用完整自然季度口径；窗口起止不完整季度仅展示，不参与同比。",
        },
    }


# --------------------------------------------------------------------------- events
_EVENT_FIELDS = (
    "e.event_id, e.source, e.kind, e.event_date, e.published_at, e.available_at, "
    "e.company_key, e.applicant_raw, e.track_id, e.product_code, e.title, e.summary, e.url, "
    "e.payload"
)


def _event_where(
    *,
    track: str | None = None,
    metric: str | None = None,
    source: str | None = None,
    start: str | None = None,
    end: str | None = None,
    query: str | None = None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if track:
        clauses.append("e.track_id = ?")
        params.append(track)
    if metric:
        kind_sql, kind_params = _kind_marks(metric)
        clauses.append(kind_sql)
        params.extend(kind_params)
    if source:
        clauses.append("e.source = ?")
        params.append(source)
    if start:
        clauses.append("e.event_date >= ?")
        params.append(start)
    if end:
        clauses.append("e.event_date <= ?")
        params.append(end)
    if query:
        clauses.append("(e.title LIKE ? OR e.applicant_raw LIKE ? OR e.summary LIKE ?)")
        like = f"%{query}%"
        params.extend([like, like, like])
    if not clauses:
        clauses.append("1=1")
    return " AND ".join(clauses), params


@_memo
def evidence_search(
    companies: tuple[str, ...] = (),
    track: str | None = None,
    metric: str | None = None,
    source: str | None = None,
    start: str | None = None,
    end: str | None = None,
    query: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    where, params = _event_where(track=track, metric=metric, source=source, start=start, end=end, query=query)
    prefix, frm, cte_params = company_from(list(companies))
    with read() as con:
        total = _one(con, f"{prefix}SELECT COUNT(*) FROM {frm} WHERE {where}", [*cte_params, *params])
        rows = _rows(
            con,
            f"{prefix}SELECT {_EVENT_FIELDS} FROM {frm} WHERE {where} "
            f"ORDER BY e.event_date DESC, e.event_id ASC LIMIT ? OFFSET ?",
            [*cte_params, *params, limit, offset],
        )
    items = [_event_brief(row) for row in rows]
    for item, row in zip(items, rows):
        item["published_at"] = row.get("published_at")
    return {
        "total": int(total or 0),
        "limit": limit,
        "offset": offset,
        "items": items,
        "params": {
            "companies": list(companies),
            "track": track,
            "metric": metric,
            "source": source,
            "start": start,
            "end": end,
            "query": query,
        },
    }


@_memo
def event_detail(event_id: str) -> dict[str, Any]:
    with read() as con:
        row = con.execute("SELECT * FROM events e WHERE e.event_id = ?", (event_id,)).fetchone()
        if not row:
            raise KeyError(f"unknown event: {event_id}")
        event = dict(row)
        product = None
        if event.get("product_code"):
            prow = con.execute(
                "SELECT * FROM product_codes WHERE product_code = ?", (event["product_code"],)
            ).fetchone()
            product = dict(prow) if prow else None
        source = SOURCES.get(event.get("source"), {})
        track = track_meta(event.get("track_id"))
        company_fields = entities.event_company_fields(event)
    payload = None
    if event.get("payload"):
        try:
            payload = json.loads(event["payload"])
        except (TypeError, ValueError):
            payload = {"_raw": str(event["payload"])[:2000]}
    classification = approval_classification(event.get("kind"), event.get("payload"))
    mapping_note = None
    if company_fields["company_match"] == "exact_alias":
        mapping_note = (
            "企业归属来自本轮补充的逐条精确名称匹配（该企业不在仓库原有名册中），标记为待人工复核。"
        )
    elif company_fields["company_match"] == "unmapped":
        mapping_note = "该记录的申请人/申办方字符串未映射到任何企业，产品没有强行归属。"
    return {
        "event": {
            **event,
            **company_fields,
            "track_name_zh": track["name_zh"],
            "track_name_en": track["name_en"],
            "track_domain": track.get("domain"),
            "track_mapped": bool(event.get("track_id")),
        },
        "product_code": product,
        "source": source,
        "track": track,
        "payload": payload,
        "approval": {
            **classification,
            "source_fields": (
                ["pma_number", "supplement_number", "supplement_type"]
                if event.get("kind") == "pma"
                else ["k_number", "clearance_type"]
                if event.get("kind") == "510k"
                else []
            ),
            "note_zh": (
                "PMA 的 supplement_number 为空表示原始批准，非空表示补充申请；"
                "510(k) 的 clearance_type 区分 Traditional / Special / Abbreviated。"
                "无法解析 payload 时标记为 unknown，不猜测。"
            ),
        },
        "mapping": {
            "company_method": company_fields["company_match"],
            "company_note_zh": mapping_note,
            "track_method": "product_code_to_track" if event.get("track_id") else "unmapped",
            "track_note_zh": (
                "赛道由 FDA 产品代码映射到仓库既有分类体系。"
                if event.get("track_id")
                else "该记录没有可用的产品代码/赛道映射，产品不把它计为任何赛道的活动。"
            ),
        },
        "dates": {
            "event_date": event.get("event_date"),
            "published_at": event.get("published_at"),
            "available_at": event.get("available_at"),
            "timestamp_quality": event.get("timestamp_quality"),
            "note_zh": "event_date 为事件发生日期；available_at 为数据可用日期（若与事件日不同则提示）。",
        },
        "links": {"source_url": event.get("url") or None},
        "limitations": [
            LIMITATIONS["us_only"],
            LIMITATIONS["record_not_product"],
            LIMITATIONS["entity_mapping"],
        ],
    }


def claim_evidence(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute the event set behind a claim, so a claim can always be audited."""
    company = str(payload.get("company") or "")
    track = str(payload.get("track") or "")
    metric = str(payload.get("metric") or "approvals")
    recent_start = str(payload.get("recent_start") or "")
    recent_end = str(payload.get("recent_end") or "")
    prior_start = str(payload.get("prior_start") or "")
    prior_end = str(payload.get("prior_end") or "")
    if not company or not track or not recent_start or not recent_end:
        raise ValueError("claim evidence requires company, track and recent window")
    if metric not in METRICS:
        raise ValueError("unknown metric")
    with read() as con:
        prefix, frm, cte_params = company_from([company])
        kind_sql, kp = _kind_marks(metric)
        recent_total = _one(
            con,
            f"{prefix}SELECT COUNT(*) FROM {frm} WHERE e.track_id = ? "
            f"AND {kind_sql} AND e.event_date >= ? AND e.event_date <= ?",
            [*cte_params, track, *kp, recent_start, recent_end],
        )
        prior_total = _one(
            con,
            f"{prefix}SELECT COUNT(*) FROM {frm} WHERE e.track_id = ? "
            f"AND {kind_sql} AND e.event_date >= ? AND e.event_date <= ?",
            [*cte_params, track, *kp, prior_start, prior_end],
        )
        recent_rows = _rows(
            con,
            f"{prefix}SELECT {_EVENT_FIELDS} FROM {frm} WHERE e.track_id = ? "
            f"AND {kind_sql} AND e.event_date >= ? AND e.event_date <= ? "
            f"ORDER BY e.event_date DESC LIMIT 400",
            [*cte_params, track, *kp, recent_start, recent_end],
        )
        prior_rows = _rows(
            con,
            f"{prefix}SELECT {_EVENT_FIELDS} FROM {frm} WHERE e.track_id = ? "
            f"AND {kind_sql} AND e.event_date >= ? AND e.event_date <= ? "
            f"ORDER BY e.event_date DESC LIMIT 400",
            [*cte_params, track, *kp, prior_start, prior_end],
        )
    return {
        "company": company,
        "company_name_zh": entities.display_name(company),
        "track": track_meta(track),
        "metric": METRICS[metric],
        "window": {
            "recent_start": recent_start,
            "recent_end": recent_end,
            "prior_start": prior_start,
            "prior_end": prior_end,
        },
        "recomputed": {
            "recent": int(recent_total or 0),
            "prior": int(prior_total or 0),
            "listed_recent": len(recent_rows),
            "listed_prior": len(prior_rows),
        },
        "recent_events": [_event_brief(row) for row in recent_rows],
        "prior_events": [_event_brief(row) for row in prior_rows],
        "note_zh": (
            "recomputed 为按同一口径重新计算的记录条数（全部记录）；事件列表按日期倒序列出"
            "最多各 400 条，用于逐条核查。计数为记录条数，不是产品数，也不包含未映射到该赛道的记录。"
        ),
        "limitations": [LIMITATIONS["us_only"], LIMITATIONS["record_not_product"], LIMITATIONS["track_mapping"]],
    }


# ------------------------------------------------------------------------ compare
def _pathway_window(con: sqlite3.Connection, key: str, start: str, end: str) -> dict[str, Any]:
    breakdown = _approval_breakdown(con, [key], start, end)
    pma_total = breakdown.get("pma_original", 0) + breakdown.get("pma_supplement", 0) + breakdown.get("pma_unknown", 0)
    k510_total = sum(
        breakdown.get(name, 0)
        for name in ("k510_traditional", "k510_special", "k510_abbreviated", "k510_other", "k510_unknown")
    )
    approvals_total = pma_total + k510_total
    return {
        **breakdown,
        "pma": pma_total,
        "510k": k510_total,
        "approvals_total": approvals_total,
        "pma_total": pma_total,
        "k510_total": k510_total,
        "pma_share": (pma_total / approvals_total) if approvals_total else None,
        "510k_share": (k510_total / approvals_total) if approvals_total else None,
        "pma_original_share": (breakdown.get("pma_original", 0) / approvals_total) if approvals_total else None,
        # kept for compatibility: share among *all window approvals*
        "pma_supplement_share": (breakdown.get("pma_supplement", 0) / approvals_total) if approvals_total else None,
        "pma_supplement_share_of_approvals": (
            (breakdown.get("pma_supplement", 0) / approvals_total) if approvals_total else None
        ),
        "pma_supplement_share_of_pma": (
            (breakdown.get("pma_supplement", 0) / pma_total) if pma_total else None
        ),
        "pma_original_share_of_pma": (breakdown.get("pma_original", 0) / pma_total) if pma_total else None,
        "basis": "complete_window_approvals_only",
        "window": {"start": start, "end": end},
        "note_zh": "按本窗口完整周期统计的监管路径结构；补充申请计入 PMA 但不等同于新器械。",
    }


@_memo
def company_compare(keys: tuple[str, ...], metric: str = "approvals", years: int = 5, granularity: str = "quarter", include_all_time: bool = False) -> dict[str, Any]:
    keys = tuple(dict.fromkeys(keys))[:5]
    if len(keys) < 2:
        raise ValueError("comparison requires at least two companies")
    if metric not in METRICS:
        raise ValueError("unknown metric")
    if granularity not in ("year", "quarter", "month"):
        raise ValueError("unknown granularity")
    start, end = resolve_window(years)
    prior_start, prior_end = previous_window(start, end)
    comparison = comparison_windows(start, end, "quarter")
    comparable = bool(comparison["comparable"])
    analysis_start = comparison["analysis_start"] or start
    analysis_end = comparison["analysis_end"] or end
    prior_analysis_start = comparison["prior_analysis_start"] or prior_start
    prior_analysis_end = comparison["prior_analysis_end"] or prior_end
    companies = []
    warnings: list[dict[str, Any]] = []
    with read() as con:
        if comparable:
            industry = _industry_track_counts(con, metric, analysis_start, analysis_end)
            industry_coverage = _industry_coverage(con, metric, analysis_start, analysis_end)
            industry_coverage_prior = _industry_coverage(con, metric, prior_analysis_start, prior_analysis_end)
        else:
            industry = {}
            industry_coverage = _industry_coverage(con, metric, start, end)
            industry_coverage_prior = _industry_coverage(con, metric, prior_start, prior_end)
        industry_total = sum(industry.values())
        company_track_maps: dict[str, dict[str, int]] = {}
        for key in keys:
            meta = entities.company_meta(key) or {"name_en": key}
            coverage = company_coverage(key)
            series = _series(con, keys=[key], track=None, metric=metric, start=start, end=end, granularity=granularity)
            periods = _periods(start, end, granularity)
            filled = _fill_series(series, periods, start, end, granularity, data_edge()).get("total", [])
            window_total_all = sum(point["count"] for point in filled)
            tracks_all, unmapped_all = _track_counts_window(con, [key], metric, start, end)
            if comparable:
                tracks, unmapped = _track_counts_window(con, [key], metric, analysis_start, analysis_end)
                priors, prior_unmapped = _track_counts_window(
                    con, [key], metric, prior_analysis_start, prior_analysis_end
                )
                pathway = company_pathway_window(key, analysis_start, analysis_end)
            else:
                tracks, unmapped = tracks_all, unmapped_all
                priors, prior_unmapped = _track_counts_window(con, [key], metric, prior_start, prior_end)
                pathway = dict(company_pathway_window(key, start, end))
                pathway["basis"] = "requested_window_only"
                pathway["note_zh"] = (
                    "窗口内没有完整自然周期，这里的路径结构按请求窗口计算，仅作展示，"
                    "不能与完整周期口径的数字直接比较。"
                )
            company_track_maps[key] = tracks
            mapped_total = sum(tracks.values())
            all_total = mapped_total + unmapped
            prior_mapped_total = sum(priors.values())
            prior_all_total = prior_mapped_total + prior_unmapped
            if include_all_time:
                pathway_all_time = dict(company_pathway_window(key, "1900-01-01", end))
                pathway_all_time["basis"] = "all_time_approvals_only"
                pathway_all_time["note_zh"] = (
                    "全历史审批路径结构（1900-01-01 至数据截止），只作为背景，"
                    "不能解释为当前研究窗口内的结构。"
                )
            else:
                pathway_all_time = None
            companies.append(
                {
                    "key": key,
                    "name_zh": meta.get("name_zh") or meta.get("name_en") or key,
                    "name_en": meta.get("name_en") or key,
                    "ticker": meta.get("ticker"),
                    "featured": key in FEATURED_KEYS,
                    "roster_present": meta.get("roster_present", True),
                    "series": filled,
                    "total": all_total,
                    "total_complete": all_total,
                    "total_all_window": window_total_all,
                    "total_all": all_total,
                    "total_mapped": mapped_total,
                    "total_unmapped": unmapped,
                    "mapping_coverage": (mapped_total / all_total) if all_total else None,
                    "prior_total": prior_all_total,
                    "prior_total_all": prior_all_total,
                    "prior_total_mapped": prior_mapped_total,
                    "prior_total_unmapped": prior_unmapped,
                    "prior_mapping_coverage": (prior_mapped_total / prior_all_total) if prior_all_total else None,
                    "delta": (all_total - prior_all_total) if comparable else None,
                    "pct_change": ((all_total - prior_all_total) / prior_all_total) if comparable and prior_all_total else None,
                    "tracks": tracks,
                    "unmapped": unmapped,
                    "coverage": coverage,
                    "pathway": pathway,
                    "pathway_all_time": pathway_all_time,
                }
            )
    union_tracks = sorted({track for tracks in company_track_maps.values() for track in tracks})
    track_table = []
    for track in union_tracks:
        meta = track_meta(track)
        row = {
            "track": track,
            "name_zh": meta["name_zh"],
            "domain": meta.get("domain"),
            "industry_total": industry.get(track, 0),
            "industry_all_total": industry_coverage["all_records"],
            "industry_unmapped": industry_coverage["unmapped_records"],
            "industry_mapping_coverage": industry_coverage["mapping_coverage"],
            "industry_share": (industry.get(track, 0) / industry_total) if industry_total else None,
            "companies": [],
        }
        for company in companies:
            n = company_track_maps[company["key"]].get(track, 0)
            if comparable:
                lq, lq_status = location_quotient(
                    n,
                    company["total_mapped"],
                    industry.get(track, 0),
                    industry_total,
                )
            else:
                lq, lq_status = None, "not_comparable"

            row["companies"].append(
                {
                    "key": company["key"],
                    "n": n,
                    "share": (n / company["total_mapped"]) if company["total_mapped"] else None,
                    "location_quotient": lq,
                    "lq_status": lq_status,
                    "lq_reason_zh": {
                        "ok": "分母一致：企业与行业均使用完整窗口内已映射赛道记录。",
                        "zero_denominator": "企业或行业已映射记录为 0，LQ 不适用。",
                        "zero_company_track": "该企业在本完整窗口内该赛道没有已映射记录，LQ 不适用。",
                        "not_comparable": "窗口内没有完整自然周期，无法进行完整周期比较，LQ 不适用。",
                        "low_company_mapped_sample": (
                            f"企业已映射记录少于 {MIN_LQ_COMPANY_RECORDS} 条，LQ 不适用。"
                        ),
                        "low_industry_track_sample": (
                            f"该赛道全行业记录少于 {MIN_LQ_INDUSTRY_TRACK_RECORDS} 条，LQ 不适用。"
                        ),
                    }.get(lq_status, "LQ 不适用。"),
                }
            )
        track_table.append(row)
    track_table.sort(key=lambda row: -max((c["n"] for c in row["companies"]), default=0))

    if not comparable:
        warnings.append(
            {
                "code": "incomplete_window",
                "severity": "high",
                "text_zh": comparison["reason_zh"] + " 同比、份额与 LQ 均不计算。",
            }
        )
    elif comparison["partial_start"] or comparison["partial_end"]:
        warnings.append(
            {
                "code": "complete_quarter_basis",
                "severity": "info",
                "text_zh": (
                    f"比较使用完整自然季度窗口 {analysis_start} 至 {analysis_end}；"
                    f"请求窗口 {start} 至 {end} 的起止不完整季度只展示、不参与同比、份额与 LQ。"
                ),
            }
        )
    # comparability warnings (computed, not boilerplate)
    spans = {c["key"]: _coverage_span(c["coverage"]) for c in companies}
    firsts = [span["first"] for span in spans.values() if span["first"]]
    if firsts and (max(firsts) > min(firsts)):
        gap_years = (date.fromisoformat(max(firsts)) - date.fromisoformat(min(firsts))).days / 365
        if gap_years >= 5:
            warnings.append(
                {
                    "code": "coverage_gap",
                    "severity": "high",
                    "text_zh": f"所选企业的数据起始时间相差约 {gap_years:.0f} 年，跨企业总量比较会被覆盖差异污染。",
                }
            )
    coverages = [c["mapping_coverage"] for c in companies if c["mapping_coverage"] is not None]
    if coverages and (max(coverages) - min(coverages)) >= 0.05:
        warnings.append(
            {
                "code": "mapping_coverage_gap",
                "severity": "medium",
                "text_zh": (
                    "所选企业的赛道映射覆盖率相差超过 5 个百分点；份额与 LQ 只能在同一已映射口径下比较，"
                    "未映射记录已单独列出，不能视为零活动。"
                ),
            }
        )
    pma_shares = [
        c["pathway"]["pma_share"]
        for c in companies
        if c["pathway"]["pma_share"] is not None and c["pathway"]["approvals_total"] >= 20
    ]
    if pma_shares and (max(pma_shares) - min(pma_shares)) >= 0.3:
        warnings.append(
            {
                "code": "pathway_mix",
                "severity": "medium",
                "text_zh": (
                    "所选企业的监管路径结构差异明显（PMA 占比相差 30 个百分点以上，按同一完整窗口计算），"
                    "审批记录数不宜直接横比，请优先看赛道内占比与 LQ。"
                ),
            }
        )
    pma_rows = [c for c in companies if c["pathway"]["pma_total"] > 0]
    if pma_rows and any((c["pathway"]["pma_original_share_of_pma"] or 0) < 0.5 for c in pma_rows):
        warnings.append(
            {
                "code": "pma_supplement_share",
                "severity": "medium",
                "text_zh": (
                    "PMA 记录中补充申请占比很高；补充申请是已批准器械的变更（如工艺、标签），"
                    "不能当作新器械批准或技术首次进入。"
                ),
            }
        )
    if any(not c["roster_present"] for c in companies):
        warnings.append(
            {
                "code": "entity_mapping",
                "severity": "medium",
                "text_zh": "部分企业的归属来自补充的精确名称匹配（待人工复核），其计数可能与仓库主名册口径略有差异。",
            }
        )
    if metric == "recalls":
        warnings.append(
            {
                "code": "recall_metric",
                "severity": "medium",
                "text_zh": "召回记录反映安全性事件，不是研发或技术活动；召回数据约自 2002 年起收录。",
            }
        )
    if metric in ("trials", "corporate"):
        warnings.append(
            {
                "code": "source_window",
                "severity": "medium",
                "text_zh": "该指标的数据源历史窗口较短（试验注册约 2000 年起、8-K 语料 2015 年起），改变时间窗会显著改变可比性。",
            }
        )
    mapped_totals = [c["total_mapped"] for c in companies]
    if mapped_totals and min(mapped_totals) < 10:
        warnings.append(
            {
                "code": "low_count",
                "severity": "high",
                "text_zh": "至少一家企业在完整窗口内已映射赛道的记录数少于 10 条，不足以支撑趋势性比较。",
            }
        )
    return {
        "companies": companies,
        "metric": METRICS[metric],
        "window": {"start": start, "end": end, "prior_start": prior_start, "prior_end": prior_end, "years": years},
        "analysis_window": {
            **comparison,
            "prior_start": prior_analysis_start,
            "prior_end": prior_analysis_end,
            "comparable": comparable,
            "periods": comparison["periods"],
        },
        "comparability": {
            "comparable": comparable,
            "reason_zh": comparison["reason_zh"] if comparable else comparison["reason_zh"],
            "company_mapping_coverage": {c["key"]: c["mapping_coverage"] for c in companies},
            "industry_mapping_coverage": industry_coverage["mapping_coverage"],
            "industry_records": industry_coverage,
        },
        "granularity": granularity,
        "track_table": track_table,
        "warnings": warnings,
        "notes": [
            "LQ =（企业该赛道记录 / 企业已映射赛道记录）/（全行业该赛道记录 / 全行业已映射赛道记录）；企业与行业使用同一已映射分母。",
            "LQ > 1 表示该企业在该赛道的记录占比高于全行业；它描述记录分布，不是创新能力、技术实力或市场份额。",
            "记录数少于阈值（企业已映射 < 10 或行业赛道 < 5）时 LQ 返回“不适用”，不制造数值。",
            "total_all 为完整比较窗口内全部记录；total_mapped 为其中已映射到赛道的记录；未映射记录单独列出。",
            "监管路径结构按同一完整窗口计算；全历史结构单独标注，不能解释为当前窗口结构。",
        ],
    }


# ------------------------------------------------------------- analyst helpers
@_memo
def company_claims(key: str, years: int = 5, metric: str = "approvals") -> dict[str, Any]:
    """Public claim list used by the analyst (same rules as the company page)."""
    meta = entities.company_meta(key)
    if not meta:
        raise KeyError(f"unknown company: {key}")
    start, end = resolve_window(years)
    tracks = company_track_table(key, metric, start, end)
    analysis_start = tracks["analysis_window"]["start"]
    analysis_end = tracks["analysis_window"]["end"]
    claims = (
        _company_claims(key, meta, tracks, analysis_start, analysis_end)
        if tracks["analysis_window"]["comparable"]
        else []
    )
    return {
        "company": key,
        "company_name_zh": entities.display_name(key),
        "window": {
            "start": analysis_start,
            "end": analysis_end,
            "requested_start": start,
            "requested_end": end,
            "years": years,
            "basis": "complete_quarters",
        },
        "metric": metric,
        "claims": claims,
        "track_table": tracks,
    }


@_memo
def track_companies(track: str, metric: str = "approvals", years: int = 5) -> dict[str, Any]:
    """Per-company activity inside one technology track for a window and its prior window."""
    if not track_rows().get(track):
        raise KeyError(f"unknown track: {track}")
    start, end = resolve_window(years)
    prior_start, prior_end = previous_window(start, end)
    comparison = comparison_windows(start, end, "quarter")
    analysis_start = comparison["analysis_start"] or start
    analysis_end = comparison["analysis_end"] or end
    prior_analysis_start = comparison["prior_analysis_start"] or prior_start
    prior_analysis_end = comparison["prior_analysis_end"] or prior_end
    kind_sql, kind_params = _kind_marks(metric)
    with read() as con:
        rows = _rows(
            con,
            f"SELECT e.company_key company, COUNT(*) n, MIN(e.event_date) first, MAX(e.event_date) last "
            f"FROM events e WHERE e.track_id = ? AND {kind_sql} AND e.company_key IS NOT NULL "
            f"AND e.event_date >= ? AND e.event_date <= ? GROUP BY 1",
            [track, *kind_params, analysis_start, analysis_end],
        )
        prior_rows = _rows(
            con,
            f"SELECT e.company_key company, COUNT(*) n FROM events e WHERE e.track_id = ? AND {kind_sql} "
            f"AND e.company_key IS NOT NULL AND e.event_date >= ? AND e.event_date <= ? GROUP BY 1",
            [track, *kind_params, prior_analysis_start, prior_analysis_end],
        )
        extra_counts: dict[str, tuple[int, str | None, str | None]] = {}
        extra_prior: dict[str, int] = {}
        for key in entities.EXTRA_ALIAS_COMPANIES:
            prefix, frm, cte_params = company_from([key])
            row = con.execute(
                f"{prefix}SELECT COUNT(*) n, MIN(e.event_date) first, MAX(e.event_date) last FROM {frm} "
                f"WHERE e.track_id = ? AND {kind_sql} AND e.event_date >= ? AND e.event_date <= ?",
                [*cte_params, track, *kind_params, analysis_start, analysis_end],
            ).fetchone()
            if row and row["n"]:
                extra_counts[key] = (row["n"], row["first"], row["last"])
            prow = con.execute(
                f"{prefix}SELECT COUNT(*) FROM {frm} WHERE e.track_id = ? AND {kind_sql} "
                f"AND e.event_date >= ? AND e.event_date <= ?",
                [*cte_params, track, *kind_params, prior_analysis_start, prior_analysis_end],
            ).fetchone()
            extra_prior[key] = int(prow[0] if prow else 0)
    prior = {row["company"]: row["n"] for row in prior_rows}
    total_recent = sum(row["n"] for row in rows) + sum(v[0] for v in extra_counts.values())
    base = [
        {
            "company": row["company"],
            "name_zh": entities.display_name(row["company"]),
            "featured": row["company"] in FEATURED_KEYS,
            "recent": row["n"],
            "prior": prior.get(row["company"], 0),
            "first": row["first"],
            "last": row["last"],
        }
        for row in rows
    ]
    for key, (n, first, last) in extra_counts.items():
        base.append(
            {
                "company": key,
                "name_zh": entities.display_name(key),
                "featured": True,
                "recent": n,
                "prior": extra_prior.get(key, 0),
                "first": first,
                "last": last,
            }
        )
    for row in base:
        row["delta"] = row["recent"] - row["prior"]
        row["pct_change"] = (row["delta"] / row["prior"]) if row["prior"] else None
        row["share"] = (row["recent"] / total_recent) if total_recent else None
        row["z"] = _poisson_z(row["recent"], row["prior"])
    base.sort(key=lambda row: (-row["recent"], row["name_zh"]))
    return {
        "track": track_meta(track),
        "metric": metric,
        "window": {
            "start": start,
            "end": end,
            "prior_start": prior_start,
            "prior_end": prior_end,
            "analysis_start": analysis_start,
            "analysis_end": analysis_end,
            "prior_analysis_start": prior_analysis_start,
            "prior_analysis_end": prior_analysis_end,
            "years": years,
            "completeness": comparison,
            "periods": comparison["periods"],
            "basis": "complete_quarters",
        },
        "companies": base,
        "total_recent": total_recent,
        "total_prior": sum(row["prior"] for row in base),
        "note_zh": "仅统计能归属到具体企业的记录；未归属记录不在此表中，但会计入赛道总量。",
    }


@_memo
def tracks_acceleration(years: int = 3) -> dict[str, Any]:
    """Rank the curated radar tracks by observed change versus the prior window."""
    start, end = resolve_window(years)
    prior_start, prior_end = previous_window(start, end)
    comparison = comparison_windows(start, end, "quarter")
    analysis_start = comparison["analysis_start"] or start
    analysis_end = comparison["analysis_end"] or end
    prior_analysis_start = comparison["prior_analysis_start"] or prior_start
    prior_analysis_end = comparison["prior_analysis_end"] or prior_end
    with read() as con:
        recent = _industry_track_counts(con, "approvals", analysis_start, analysis_end)
        prior = _industry_track_counts(con, "approvals", prior_analysis_start, prior_analysis_end)
        series_start = (date.fromisoformat(end) - timedelta(days=365 * max(3, years * 2))).isoformat()
        rows = _rows(
            con,
            "SELECT e.track_id track, " + _period_expr("quarter") + " period, COUNT(*) n FROM events e "
            "WHERE e.kind IN ('510k','pma') AND e.track_id IS NOT NULL "
            "AND e.event_date >= ? AND e.event_date <= ? GROUP BY 1, 2",
            [series_start, end],
        )
    periods = _quarter_list(series_start, end)
    by_track: dict[str, dict[str, int]] = {}
    for row in rows:
        by_track.setdefault(row["track"], {})[row["period"]] = row["n"]
    track_ids = sorted({track for domain in RADAR_DOMAINS for track in domain["tracks"]})
    result = []
    for track in track_ids:
        r = recent.get(track, 0)
        p = prior.get(track, 0)
        values = by_track.get(track, {})
        points = _fill_series({track: values}, periods, series_start, end, "quarter", data_edge())[track]
        signal = _signal_for_counts(points)
        meta = track_meta(track)
        result.append(
            {
                "track": track,
                "name_zh": meta["name_zh"],
                "domain": meta.get("domain"),
                "domain_label_zh": meta.get("domain_label_zh"),
                "recent": r,
                "prior": p,
                "delta": r - p,
                "pct_change": ((r - p) / p) if p else None,
                "z": _poisson_z(r, p),
                "signal": signal,
                "spark": points[-8:],
            }
        )
    result.sort(key=lambda row: (-(row["pct_change"] or -9), -row["delta"]))
    return {
        "window": {
            "start": start,
            "end": end,
            "prior_start": prior_start,
            "prior_end": prior_end,
            "analysis_start": analysis_start,
            "analysis_end": analysis_end,
            "prior_analysis_start": prior_analysis_start,
            "prior_analysis_end": prior_analysis_end,
            "years": years,
            "completeness": comparison,
            "basis": "complete_quarters",
        },
        "tracks": result,
        "method_zh": (
            "比较最近一个完整季度窗口与紧邻的等长历史窗口的公开审批记录数；"
            "同时给出季度 z 分数作为统计探测参考。"
        ),
        "caveat_zh": "记录数变化可能来自数据覆盖、申报节奏或分类口径；这不是未来预测。",
    }


# ----------------------------------------------------------------------------- meta
@_memo
def dataset_meta() -> dict[str, Any]:
    with read() as con:
        counts = {
            table: _one(con, f"SELECT COUNT(*) FROM {table}")
            for table in ("events", "companies", "tracks", "product_codes")
        }
        by_kind = {
            row["kind"]: row["n"]
            for row in _rows(con, "SELECT kind, COUNT(*) n FROM events GROUP BY kind ORDER BY n DESC")
        }
        date_range = dict(
            con.execute("SELECT MIN(event_date) first, MAX(event_date) last FROM events").fetchone()
        )
        tracks = _rows(con, "SELECT id, name_zh, name_en, category FROM tracks ORDER BY id")
        sources = source_catalog(con)
        mapped = _one(con, "SELECT COUNT(*) FROM events WHERE track_id IS NOT NULL")
        company_keys = _one(con, "SELECT COUNT(DISTINCT company_key) FROM events WHERE company_key IS NOT NULL")
        unmapped_companies = _one(con, "SELECT COUNT(*) FROM events WHERE company_key IS NULL")
        signal_rows = _one(con, "SELECT COUNT(*) FROM signals")
        runs = _rows(con, "SELECT * FROM runs ORDER BY started_at DESC LIMIT 3")
        approval_audit = classification_audit(con)
    return {
        "product": {"version": PRODUCT_VERSION, "schema": "medradar.product.v1"},
        "dataset": {
            **dataset_signature(),
            "counts": counts,
            "events_by_kind": by_kind,
            "date_range": date_range,
            "track_mapped_events": int(mapped or 0),
            "track_unmapped_events": counts["events"] - int(mapped or 0),
            "track_mapping_coverage": (mapped / counts["events"]) if counts["events"] else None,
            "attributed_events": counts["events"] - int(unmapped_companies or 0),
            "unattributed_events": int(unmapped_companies or 0),
            "attribution_note_zh": (
                "track_unmapped_events 是未映射到技术赛道的事件数；attributed_events/unattributed_events "
                "则是未映射到企业的口径，两者不是同一个概念。"
            ),
            "companies_with_events": int(company_keys or 0),
            "signals": int(signal_rows or 0),
            "approval_classification": approval_audit,
            "recent_runs": runs,
        },
        "sources": sources,
        "tracks": tracks,
        "domains": radar_domains(),
        "metrics": {name: METRICS[name] for name in METRICS},
        "featured_companies": [
            {**company, "key": company["key"]} for company in FEATURED_COMPANIES
        ],
        "limitations": [{"id": key, "text_zh": text} for key, text in LIMITATIONS.items()],
        "roster_size": len(entities.roster()),
        "evidence_tiers": EVIDENCE_TIERS,
        "entity_review": entities.company_alias_review(FEATURED_KEYS),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

