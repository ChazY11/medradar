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
        key = (fn.__name__, sig["mtime_ns"], sig["bytes"], args, tuple(sorted(kwargs.items())))
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
#: research store's mtime changes.
ENTITY_MAP = DB_FILE.parent / "product_entity_map.sqlite"
_ENTITY_LOCK = threading.Lock()


def _entity_map_stale() -> bool:
    if not ENTITY_MAP.exists():
        return True
    sig = dataset_signature()
    return ENTITY_MAP.stat().st_mtime_ns < int(sig.get("mtime_ns") or 0)


def ensure_entity_map() -> None:
    if not DB_FILE.exists():
        return
    with _ENTITY_LOCK:
        if not _entity_map_stale():
            return
        ENTITY_MAP.parent.mkdir(parents=True, exist_ok=True)
        tmp = ENTITY_MAP.with_name(ENTITY_MAP.name + ".tmp")
        if tmp.exists():
            tmp.unlink()
        source = sqlite3.connect(f"file:{DB_FILE.as_posix()}?mode=ro", uri=True)
        try:
            target = sqlite3.connect(tmp)
            try:
                target.executescript(
                    "CREATE TABLE event_company ("
                    "event_id TEXT PRIMARY KEY, company_key TEXT NOT NULL, matched_alias TEXT);"
                    "CREATE INDEX idx_event_company_key ON event_company(company_key);"
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
        if ENTITY_MAP.exists():
            ENTITY_MAP.unlink()
        tmp.replace(ENTITY_MAP)


@contextmanager
def read() -> Iterable[sqlite3.Connection]:
    if not DB_FILE.exists():
        raise FileNotFoundError(
            f"research store not found: {DB_FILE}. "
            "Run `python -m medradar run` once to build it, then start the product server."
        )
    ensure_entity_map()
    con = sqlite3.connect(f"file:{DB_FILE.as_posix()}?mode=ro", uri=True, timeout=15.0)
    con.row_factory = sqlite3.Row
    try:
        if ENTITY_MAP.exists():
            con.execute("ATTACH DATABASE ? AS pm", (ENTITY_MAP.as_posix(),))
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


def is_period_partial(period: str, edge: str) -> bool:
    """True when ``period`` contains the dataset edge (still accruing)."""
    finish = _parse(edge)
    if not finish:
        return False
    if "-Q" in period:
        year, quarter = period.split("-Q")
        position = (finish.month - 1) // 3 + 1
        return finish.year == int(year) and position == int(quarter)
    if len(period) == 8 and "-" in period:
        return finish.strftime("%Y-%m") == period
    if len(period) == 4:
        return finish.year == int(period)
    return False


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


def _company_track_firsts(con: sqlite3.Connection, key: str) -> dict[str, dict[str, Any]]:
    prefix, frm, cte_params = company_from([key])
    rows = _rows(
        con,
        f"{prefix}SELECT e.track_id AS track, MIN(e.event_date) first_date, COUNT(*) n "
        f"FROM {frm} WHERE e.track_id IS NOT NULL AND e.kind IN ('510k','pma') "
        f"GROUP BY e.track_id",
        cte_params,
    )
    return {row["track"]: row for row in rows if row["track"]}


@_memo
def company_track_table(key: str, metric: str, start: str, end: str) -> dict[str, Any]:
    prior_start, prior_end = previous_window(start, end)
    with read() as con:
        recent, recent_unmapped = _track_counts_window(con, [key], metric, start, end)
        prior, prior_unmapped = _track_counts_window(con, [key], metric, prior_start, prior_end)
        industry_recent = _industry_track_counts(con, metric, start, end)
        industry_prior = _industry_track_counts(con, metric, prior_start, prior_end)
        firsts = _company_track_firsts(con, key)
    total_recent = sum(recent.values())
    total_prior = sum(prior.values())
    industry_total_recent = sum(industry_recent.values())
    industry_total_prior = sum(industry_prior.values())
    rows = []
    for track in set(recent) | set(prior):
        r = recent.get(track, 0)
        p = prior.get(track, 0)
        ir = industry_recent.get(track, 0)
        ip = industry_prior.get(track, 0)
        delta = r - p
        share_r = (r / total_recent) if total_recent else None
        share_p = (p / total_prior) if total_prior else None
        ind_share_r = (ir / industry_total_recent) if industry_total_recent else None
        first = firsts.get(track)
        first_date = first["first_date"] if first else None
        rows.append(
            {
                **track_meta(track),
                "track": track,
                "recent": r,
                "prior": p,
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
                "all_time": (first or {}).get("n"),
                "new_in_window": bool(first_date and start <= first_date <= end),
                "z": _poisson_z(r, p),
            }
        )
    rows.sort(key=lambda row: (-row["recent"], -row["prior"]))
    return {
        "rows": rows,
        "total_recent": total_recent,
        "total_prior": total_prior,
        "unmapped_recent": recent_unmapped,
        "unmapped_prior": prior_unmapped,
        "industry_total_recent": industry_total_recent,
        "industry_total_prior": industry_total_prior,
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
    edge: str,
) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for series, values in mapping.items():
        out[series] = [
            {
                "period": p,
                "count": int(values.get(p, 0)),
                "partial": is_period_partial(p, edge),
            }
            for p in periods
        ]
    return out


@_memo
def company_series(key: str, metric: str, start: str, end: str, granularity: str = "quarter") -> dict[str, Any]:
    with read() as con:
        data = _series(con, keys=[key], track=None, metric=metric, start=start, end=end, granularity=granularity)
        industry = _industry_track_counts(con, metric, start, end)
    periods = _periods(start, end, granularity)
    series = _fill_series(data, periods, end).get("total", [])
    return {
        "granularity": granularity,
        "start": start,
        "end": end,
        "metric": metric,
        "points": series,
        "total": sum(point["count"] for point in series),
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
    return {
        "event_id": row.get("event_id"),
        "event_date": row.get("event_date"),
        "kind": row.get("kind"),
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
    }


@_memo
def company_milestones(key: str) -> list[dict[str, Any]]:
    kinds = [
        ("pma", "首个 PMA 批准"),
        ("510k", "首个 510(k) 记录"),
        ("trial", "首个临床试验注册"),
        ("device_recall", "首个召回记录"),
        ("8k_catalyst", "首个 8-K 事件"),
    ]
    out: list[dict[str, Any]] = []
    with read() as con:
        for kind, label in kinds:
            row = _milestone_event(con, key, kind)
            if not row:
                continue
            brief = _event_brief(row)
            brief["label_zh"] = label
            out.append(brief)
        firsts = _company_track_firsts(con, key)
        top = sorted(firsts.items(), key=lambda item: item[1]["first_date"])
        for track, info in top[:6]:
            meta = track_meta(track)
            out.append(
                {
                    "event_id": None,
                    "event_date": info["first_date"],
                    "kind": "track_first",
                    "source": "derived",
                    "title": f"{meta['name_zh']}赛道的首条公开审批记录",
                    "url": None,
                    "company_key": key,
                    "company_name_zh": entities.display_name(key),
                    "company_match": "derived",
                    "track_id": track,
                    "track_name_zh": meta["name_zh"],
                    "product_code": None,
                    "applicant_raw": None,
                    "available_at": info["first_date"],
                    "label_zh": f"首次进入 {meta['name_zh']}",
                    "derived": True,
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
    kind_counts = company_kind_counts(key)
    coverage = company_coverage(key)
    tracks = company_track_table(key, "approvals", start, end)
    series_approvals = company_series(key, "approvals", start, end, "quarter")
    with read() as con:
        recent = _recent_events(con, key)
        # per-kind annual series for the same window
        kind_series = _series(con, keys=[key], track=None, metric=None, start=start, end=end, granularity="year")
        periods = _periods(start, end, "year")
        filled = _fill_series(kind_series, periods, end)
    total_window = tracks["total_recent"]
    total_prior = tracks["total_prior"]
    pathway = {
        "pma": kind_counts.get("pma", 0),
        "510k": kind_counts.get("510k", 0),
        "recalls": kind_counts.get("device_recall", 0),
        "trials": kind_counts.get("trial", 0),
        "corporate": kind_counts.get("8k_catalyst", 0),
    }
    pathway_all = sum(pathway.values()) or 1
    approvals_pathway = (pathway["pma"] + pathway["510k"]) or 1
    claims = _company_claims(key, meta, tracks, start, end, pathway, kind_counts)
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
        },
        "headline": {
            "events_all_time": sum(kind_counts.values()),
            "approvals_all_time": kind_counts.get("510k", 0) + kind_counts.get("pma", 0),
            "approvals_window": total_window,
            "approvals_window_mapped": total_window,
            "approvals_window_all": total_window + tracks["unmapped_recent"],
            "approvals_prior": total_prior,
            "approvals_prior_all": total_prior + tracks["unmapped_prior"],
            "unmapped_window": tracks["unmapped_recent"],
            "unmapped_prior": tracks["unmapped_prior"],
            "window_basis_zh": (
                "近窗/前窗审批记录只统计已映射到技术赛道的记录（与结论、赛道表同一口径）；"
                "未映射条数单独列出，未映射不等于零活动。"
            ),
            "delta": total_window - total_prior,
            "pct_change": ((total_window - total_prior) / total_prior) if total_prior else None,
            "tracks_active": len([row for row in tracks["rows"] if row["recent"] > 0]),
            "first_event": _coverage_span(coverage)["first"],
            "last_event": _coverage_span(coverage)["last"],
            "recalls_all_time": kind_counts.get("device_recall", 0),
            "trials_all_time": kind_counts.get("trial", 0),
            "pathway_mix": {
                "pma": pathway["pma"] / approvals_pathway,
                "510k": pathway["510k"] / approvals_pathway,
                "basis": "approvals_only",
                "note_zh": "仅以 510(k)+PMA 审批记录为分母；召回、试验、8-K 不计入，避免路径结构被安全性事件稀释。",
            },
            "pathway_mix_counts": pathway,
            "evidence_mix_of_all": {k: (v / pathway_all) for k, v in pathway.items()},
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
                f"该企业在窗口内的审批记录中有 {tracks['unmapped_recent']} 条未映射到技术赛道"
                if tracks["unmapped_recent"]
                else None
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
    pathway: Mapping[str, int],
    kind_counts: Mapping[str, int],
) -> list[dict[str, Any]]:
    """Deterministic, evidence-linked statements (Observed Change tier).

    The rules are deliberately conservative: a claim is only made when both
    windows have enough records, and the text always states the industry
    comparison so a company-specific "increase" cannot be mistaken for a
    strategic signal when the whole track grew.
    """
    claims: list[dict[str, Any]] = []
    years = max(1, round((_parse(end) - _parse(start)).days / 365)) if _parse(end) and _parse(start) else 5
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
                f"近{years}年，{meta.get('name_zh')}在{row['name_zh']}赛道的公开审批记录由 {prior} 条变为 {recent} 条；"
                f"两期合计仅 {recent + prior} 条，绝对数量过少，不足以判断趋势或相对地位，"
                f"这里只把它作为可逐条核查的观察记录列出。"
            )
        elif direction == "up":
            if prior == 0:
                statement = (
                    f"近{years}年，{meta.get('name_zh')}在{row['name_zh']}赛道出现 {recent} 条公开审批记录，"
                    f"而前一个同长度时间窗内为 0 条；这是数据覆盖期内该企业在该赛道首次观察到审批活动"
                    f"（首条记录 {row['first_approval'] or '无'}）。"
                )
            elif ind_pct is not None and ind_pct > 0.15 and (pct or 0) <= ind_pct * 1.2:
                statement = (
                    f"近{years}年，{meta.get('name_zh')}在{row['name_zh']}赛道的公开审批记录由 {prior} 条增至 {recent} 条"
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
                    f"近{years}年，{meta.get('name_zh')}在{row['name_zh']}赛道的公开审批记录由 {prior} 条增至 {recent} 条"
                    f"（{pct:+.0%}）；{industry_part}。该企业在本赛道的记录份额由 {share_p:.1%} 变为 {share_r:.1%}。"
                )
        else:
            industry_part = (
                f"同期该赛道全行业变化 {ind_pct:+.0%}" if ind_pct is not None else "同期该赛道行业对照不足"
            )
            statement = (
                f"近{years}年，{meta.get('name_zh')}在{row['name_zh']}赛道的公开审批记录由 {prior} 条降至 {recent} 条"
                f"（{pct:+.0%}）；{industry_part}，其在本赛道的记录份额由 {share_p:.1%} 变为 {share_r:.1%}。"
            )
        caveats = [
            "计数为美国 FDA 公开记录条数，不等于产品数或创新能力。",
            "对照窗口为紧邻的等长历史窗口，属于描述性比较，不做因果推断。",
        ]
        if row.get("industry_pct_change") is None:
            caveats.append("该赛道历史记录过少，行业对照不稳定。")
        if str(meta.get("key")) in ("mindray", "draeger"):
            caveats.append("美国记录不代表该企业全球活动；赛道映射只覆盖部分记录。")
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
                    "low_volume": low_volume,
                },
                "window": {
                    "recent_start": start,
                    "recent_end": end,
                    "prior_start": tracks["window"]["prior_start"],
                    "prior_end": tracks["window"]["prior_end"],
                    "years": years,
                },
                "evidence_params": {
                    "company": key,
                    "track": row["track"],
                    "metric": "approvals",
                    "recent_start": start,
                    "recent_end": end,
                    "prior_start": tracks["window"]["prior_start"],
                    "prior_end": tracks["window"]["prior_end"],
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
    return {"start": start, "end": end, "prior_start": prior_start, "prior_end": prior_end, "years": years}


@_memo
def radar_overview(years: int = 3) -> dict[str, Any]:
    window = _year_windows(years)
    start, end = window["start"], window["end"]
    prior_start, prior_end = window["prior_start"], window["prior_end"]
    with read() as con:
        recent = _industry_track_counts(con, "approvals", start, end)
        prior = _industry_track_counts(con, "approvals", prior_start, prior_end)
        mapped_total = _one(
            con,
            "SELECT COUNT(*) FROM events WHERE track_id IS NOT NULL AND kind IN ('510k','pma') "
            "AND event_date >= ? AND event_date <= ?",
            [start, end],
        )
        unmapped_total = _one(
            con,
            "SELECT COUNT(*) FROM events WHERE track_id IS NULL AND kind IN ('510k','pma') "
            "AND event_date >= ? AND event_date <= ?",
            [start, end],
        )
        # quarterly series per track (last 10 years, complete quarters only for signals)
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
            [start, end],
        )
        comp_extra = {}
        for key in entities.EXTRA_ALIAS_COMPANIES:
            prefix, frm, cte_params = company_from([key])
            for row in _rows(
                con,
                f"{prefix}SELECT e.track_id track, COUNT(*) n FROM {frm} "
                f"WHERE e.kind IN ('510k','pma') AND e.track_id IS NOT NULL "
                f"AND e.event_date >= ? AND e.event_date <= ? GROUP BY 1",
                [*cte_params, start, end],
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
            points = [{"period": p, "count": series.get(p, 0), "partial": is_period_partial(p, end)} for p in periods]
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
        "track_mapping_coverage": (mapped_total / (mapped_total + unmapped_total)) if (mapped_total + unmapped_total) else None,
        "method": {
            "signal": "以完整季度计数相对前 8 个季度均值的 z 分数；|z|≥2.5 且当前季度≥5 条时标记为统计探测信号。",
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
    domain = DOMAIN_BY_ID.get(meta.get("domain") or "", None)
    with read() as con:
        series_map = _series(con, keys=None, track=track, metric=None, start=start, end=end, granularity="quarter")
        periods = _quarter_list(start, end)
        filled = _fill_series(series_map, periods, end)
        kind_total = {kind: sum(p["count"] for p in points if not p["partial"]) for kind, points in filled.items()}
        approvals_points = []
        for index, period in enumerate(periods):
            value = sum(filled[kind][index]["count"] for kind in ("510k", "pma") if kind in filled)
            approvals_points.append({"period": period, "count": value, "partial": is_period_partial(period, end)})
        recent = _one(
            con,
            "SELECT COUNT(*) FROM events WHERE track_id = ? AND kind IN ('510k','pma') "
            "AND event_date >= ? AND event_date <= ?",
            [track, start, end],
        )
        prior = _one(
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
            [track, start, end],
        )
        for key in entities.EXTRA_ALIAS_COMPANIES:
            prefix, frm, cte_params = company_from([key])
            row = con.execute(
                f"{prefix}SELECT COUNT(*) n, MIN(e.event_date) first, MAX(e.event_date) last FROM {frm} "
                f"WHERE e.track_id = ? AND e.kind IN ('510k','pma') "
                f"AND e.event_date >= ? AND e.event_date <= ?",
                [*cte_params, track, start, end],
            ).fetchone()
            if row and row["n"]:
                comp_rows.append({"company": key, "n": row["n"], "first": row["first"], "last": row["last"]})
        comp_rows.sort(key=lambda row: -row["n"])
        # first-time entrants within the window (one query for the whole track)
        first_rows = _rows(
            con,
            "SELECT e.company_key company, MIN(e.event_date) first FROM events e "
            "WHERE e.track_id = ? AND e.kind IN ('510k','pma') AND e.company_key IS NOT NULL "
            "GROUP BY 1",
            [track],
        )
        first_by_company = {row["company"]: row["first"] for row in first_rows}
        for key in entities.EXTRA_ALIAS_COMPANIES:
            prefix, frm, cte_params = company_from([key])
            value = _one(
                con,
                f"{prefix}SELECT MIN(e.event_date) FROM {frm} WHERE e.track_id = ? "
                f"AND e.kind IN ('510k','pma')",
                [*cte_params, track],
            )
            if value:
                first_by_company[key] = value
        entrants = []
        for row in comp_rows:
            first = first_by_company.get(row["company"])
            if first and start <= first <= end:
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
            history = [p["count"] for p in approvals_points[: index + 1]]
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
    total_kind = kind_total.get("510k", 0) + kind_total.get("pma", 0)
    attributed_recent = sum(int(row["n"]) for row in comp_rows)
    unattributed_recent = max(0, int(recent or 0) - attributed_recent)
    return {
        "track": meta,
        "domain": domain,
        "window": {"start": start, "end": end, "prior_start": prior_start, "prior_end": prior_end, "years": years},
        "totals": {
            "recent": int(recent or 0),
            "prior": int(prior or 0),
            "delta": int((recent or 0) - (prior or 0)),
            "pct_change": (((recent or 0) - (prior or 0)) / prior) if prior else None,
            "series_total_complete": total_kind,
            "all_time": int(industry_mapped or 0),
        },
        "attribution": {
            "attributed_recent": attributed_recent,
            "unattributed_recent": unattributed_recent,
            "attributed_share": (attributed_recent / int(recent)) if recent else None,
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
                "share": (row["n"] / (int(recent or 0) or 1)),
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
            "signal": "季度审批记录数相对前 8 季度均值的 z 分数；|z|≥2.5 且计数≥5 时标记。",
            "entrant": "企业在窗口内出现该赛道的首条 510(k)/PMA 记录（数据覆盖期内）。",
        },
    }


# --------------------------------------------------------------------------- events
_EVENT_FIELDS = (
    "e.event_id, e.source, e.kind, e.event_date, e.published_at, e.available_at, "
    "e.company_key, e.applicant_raw, e.track_id, e.product_code, e.title, e.summary, e.url"
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
@_memo
def company_compare(keys: tuple[str, ...], metric: str = "approvals", years: int = 5, granularity: str = "quarter") -> dict[str, Any]:
    keys = tuple(dict.fromkeys(keys))[:5]
    if len(keys) < 2:
        raise ValueError("comparison requires at least two companies")
    if metric not in METRICS:
        raise ValueError("unknown metric")
    if granularity not in ("year", "quarter", "month"):
        raise ValueError("unknown granularity")
    start, end = resolve_window(years)
    prior_start, prior_end = previous_window(start, end)
    companies = []
    warnings: list[dict[str, Any]] = []
    with read() as con:
        industry = _industry_track_counts(con, metric, start, end)
        industry_total = sum(industry.values()) or 1
        company_track_maps: dict[str, dict[str, int]] = {}
        for key in keys:
            meta = entities.company_meta(key) or {"name_en": key}
            coverage = company_coverage(key)
            series = _series(con, keys=[key], track=None, metric=metric, start=start, end=end, granularity=granularity)
            periods = _periods(start, end, granularity)
            filled = _fill_series(series, periods, end).get("total", [])
            window_total = sum(point["count"] for point in filled)
            complete_total = sum(point["count"] for point in filled if not point["partial"])
            partial_total = window_total - complete_total
            tracks, unmapped = _track_counts_window(con, [key], metric, start, end)
            priors, prior_unmapped = _track_counts_window(con, [key], metric, prior_start, prior_end)
            company_track_maps[key] = tracks
            kind_counts = _company_counts(con, key)
            pma = kind_counts.get("pma", 0)
            _510k = kind_counts.get("510k", 0)
            pathway_total = (pma + _510k) or 1
            companies.append(
                {
                    "key": key,
                    "name_zh": meta.get("name_zh") or meta.get("name_en") or key,
                    "name_en": meta.get("name_en") or key,
                    "ticker": meta.get("ticker"),
                    "featured": key in FEATURED_KEYS,
                    "roster_present": meta.get("roster_present", True),
                    "series": filled,
                    "total": window_total,
                    "total_complete": complete_total,
                    "partial_total": partial_total,
                    "prior_total": sum(priors.values()) + prior_unmapped,
                    "tracks": tracks,
                    "unmapped": unmapped,
                    "coverage": coverage,
                    "pathway": {
                        "pma": pma,
                        "510k": _510k,
                        "pma_share": pma / pathway_total,
                        "510k_share": _510k / pathway_total,
                    },
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
            "industry_share": industry.get(track, 0) / industry_total,
            "companies": [],
        }
        for company in companies:
            n = company_track_maps[company["key"]].get(track, 0)
            share = (n / company["total"]) if company["total"] else None
            lq = None
            if share is not None and row["industry_share"]:
                lq = share / row["industry_share"]
            row["companies"].append(
                {"key": company["key"], "n": n, "share": share, "location_quotient": lq}
            )
        track_table.append(row)
    track_table.sort(key=lambda row: -max((c["n"] for c in row["companies"]), default=0))

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
    pma_shares = [c["pathway"]["pma_share"] for c in companies if c["pathway"]["pma"] + c["pathway"]["510k"] >= 20]
    if pma_shares and (max(pma_shares) - min(pma_shares)) >= 0.3:
        warnings.append(
            {
                "code": "pathway_mix",
                "severity": "medium",
                "text_zh": "所选企业的监管路径结构差异明显（PMA 占比相差 30 个百分点以上），审批记录数不宜直接横比，请优先看赛道内占比与专业化指数。",
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
    totals = [c["total"] for c in companies]
    if totals and min(totals) < 10:
        warnings.append(
            {
                "code": "low_count",
                "severity": "high",
                "text_zh": "至少一家企业在窗口内的记录数少于 10 条，不足以支撑趋势性比较。",
            }
        )
    return {
        "companies": companies,
        "metric": METRICS[metric],
        "window": {"start": start, "end": end, "prior_start": prior_start, "prior_end": prior_end, "years": years},
        "granularity": granularity,
        "track_table": track_table,
        "warnings": warnings,
        "notes": [
            "比较页同时展示绝对记录数、企业内赛道占比（share）与相对全行业的专业化指数（location quotient = 企业赛道占比 / 全行业赛道占比）。",
            "location quotient > 1 表示该企业在该赛道的记录占比高于全行业；它不是创新能力或市场地位。",
            "total 为窗口内全部记录（含数据截止所在的不完整周期）；total_complete 为仅完整周期合计，partial_total 为不完整周期内记录数。",
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
    kind_counts = company_kind_counts(key)
    claims = _company_claims(key, meta, tracks, start, end, {}, kind_counts)
    return {
        "company": key,
        "company_name_zh": entities.display_name(key),
        "window": {"start": start, "end": end, "years": years},
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
    kind_sql, kind_params = _kind_marks(metric)
    with read() as con:
        rows = _rows(
            con,
            f"SELECT e.company_key company, COUNT(*) n, MIN(e.event_date) first, MAX(e.event_date) last "
            f"FROM events e WHERE e.track_id = ? AND {kind_sql} AND e.company_key IS NOT NULL "
            f"AND e.event_date >= ? AND e.event_date <= ? GROUP BY 1",
            [track, *kind_params, start, end],
        )
        prior_rows = _rows(
            con,
            f"SELECT e.company_key company, COUNT(*) n FROM events e WHERE e.track_id = ? AND {kind_sql} "
            f"AND e.company_key IS NOT NULL AND e.event_date >= ? AND e.event_date <= ? GROUP BY 1",
            [track, *kind_params, prior_start, prior_end],
        )
        extra_counts: dict[str, tuple[int, str | None, str | None]] = {}
        extra_prior: dict[str, int] = {}
        for key in entities.EXTRA_ALIAS_COMPANIES:
            prefix, frm, cte_params = company_from([key])
            row = con.execute(
                f"{prefix}SELECT COUNT(*) n, MIN(e.event_date) first, MAX(e.event_date) last FROM {frm} "
                f"WHERE e.track_id = ? AND {kind_sql} AND e.event_date >= ? AND e.event_date <= ?",
                [*cte_params, track, *kind_params, start, end],
            ).fetchone()
            if row and row["n"]:
                extra_counts[key] = (row["n"], row["first"], row["last"])
            prow = con.execute(
                f"{prefix}SELECT COUNT(*) FROM {frm} WHERE e.track_id = ? AND {kind_sql} "
                f"AND e.event_date >= ? AND e.event_date <= ?",
                [*cte_params, track, *kind_params, prior_start, prior_end],
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
        "window": {"start": start, "end": end, "prior_start": prior_start, "prior_end": prior_end, "years": years},
        "companies": base,
        "total_recent": total_recent,
        "total_prior": sum(row["prior"] for row in base),
    }


@_memo
def tracks_acceleration(years: int = 3) -> dict[str, Any]:
    """Rank the curated radar tracks by observed change versus the prior window."""
    start, end = resolve_window(years)
    prior_start, prior_end = previous_window(start, end)
    with read() as con:
        recent = _industry_track_counts(con, "approvals", start, end)
        prior = _industry_track_counts(con, "approvals", prior_start, prior_end)
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
        points = [{"period": period, "count": values.get(period, 0), "partial": is_period_partial(period, end)} for period in periods]
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
        "window": {"start": start, "end": end, "prior_start": prior_start, "prior_end": prior_end, "years": years},
        "tracks": result,
        "method_zh": "比较最近一个时间窗与紧邻的等长历史窗口的公开审批记录数；同时给出季度 z 分数作为统计探测参考。",
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
        "evidence_tiers": EVIDENCE_TIERS,
        "entity_review": entities.company_alias_review(FEATURED_KEYS),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

