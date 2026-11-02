"""OpenAlex publication counts: keyless, one grouped request per company.

Why this source
---------------
OpenAlex exposes scholarly works with raw affiliation strings. It is keyless and
its metadata is CC0, so it is usable without a commercial contract. This module
deliberately uses **one grouped request per company**::

    /works?filter=raw_affiliation_strings.search:<alias>,
                 from_publication_date:<start>-01-01
          &group_by=publication_year

The grouped response yields a count per publication year in a single request,
which keeps the live request budget tiny (51 companies -> 51 requests) and
matches the annual granularity we can defend point-in-time.

Scope and honesty notes
-----------------------
* ``raw_affiliation_strings`` matching is an alias search, not an entity
  resolver. A company alias can match unrelated papers (e.g. the parent J&J
  includes pharma works) and can miss papers that use a different spelling.
  Counts are therefore weak, noisy signals, not measures of R&D output or
  approved projects.
* The current calendar year (and any year whose aggregated records are still
  changing) is a partial year. It is stored as reported but the feature builder
  never uses it (see ``features/publication_features.py``).
* No API key is required, but OpenAlex applies a small shared daily budget per
  IP and asks for polite use. Every response is cached on disk under
  ``data/cache/openalex/`` keyed by the request URL, so re-collection and the
  ablation replay offline from the same frozen responses.

Counts are persisted in a small local table created here::

    publication_counts(company_key, year, works, source, retrieved_at)

The query string, alias and API cost of each request are kept in the provenance
payload returned by :func:`collect` (and in the gitignored cache index), not in
the counts table.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable, Mapping

from ...config import CACHE_DIR
from ...http import BudgetExceeded, Fetcher, HttpError, OfflineMiss
from ...util import ensure_dir, read_json, utc_now_iso, write_json

OPENALEX_WORKS = "https://api.openalex.org/works"
OPENALEX_CACHE_DIR = CACHE_DIR / "openalex"
DEFAULT_START_YEAR = 2014
SOURCE = "openalex_group_by_publication_year"
POLITE_UA = (
    "medradar/0.3 (open-source medical-device radar; OpenAlex CC0 metadata; "
    "one grouped request per company)"
)
PUBLICATION_COUNTS_DDL = """
CREATE TABLE IF NOT EXISTS publication_counts (
    company_key TEXT NOT NULL,
    year INTEGER NOT NULL,
    works INTEGER NOT NULL,
    source TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    PRIMARY KEY (company_key, year, source)
);
"""


def ensure_publication_table(store: Any) -> None:
    store.conn.executescript(PUBLICATION_COUNTS_DDL)
    store.conn.commit()


def preferred_alias(company: Mapping[str, Any]) -> str:
    """Deterministic search alias: first curated alias, else the English name."""
    aliases = [str(alias).strip() for alias in (company.get("aliases") or []) if str(alias or "").strip()]
    if aliases:
        return aliases[0]
    return str(company.get("name_en") or company.get("key") or "").strip()


def build_query(alias: str, start_year: int = DEFAULT_START_YEAR) -> dict[str, str]:
    return {
        "filter": f"raw_affiliation_strings.search:{alias},from_publication_date:{start_year}-01-01",
        "group_by": "publication_year",
    }


def query_string(alias: str, start_year: int = DEFAULT_START_YEAR) -> str:
    query = build_query(alias, start_year)
    return f"filter={query['filter']}&group_by={query['group_by']}"


def parse_grouped_counts(payload: Any) -> dict[str, Any]:
    """Parse a ``group_by=publication_year`` response into annual counts.

    Partial years are returned as reported; the feature builder is responsible
    for excluding them by knowledge time. Missing/blank groups are ignored.
    """
    counts: dict[int, int] = {}
    for group in (payload or {}).get("group_by") or []:
        try:
            year = int(str(group.get("key")))
            works = int(group.get("count") or 0)
        except (TypeError, ValueError):
            continue
        counts[year] = works
    meta = (payload or {}).get("meta") or {}
    total = meta.get("count")
    return {
        "counts": dict(sorted(counts.items())),
        "total_works": int(total) if total is not None else sum(counts.values()),
        "groups_count": meta.get("groups_count"),
        "cost_usd": meta.get("cost_usd"),
    }


def _index_path(cache_dir: Path) -> Path:
    return cache_dir / "index.json"


def _load_index(cache_dir: Path) -> dict[str, Any]:
    payload = read_json(_index_path(cache_dir), {})
    return payload if isinstance(payload, dict) else {}


def display_path(path: Path) -> str:
    """Stable, non-absolute cache path for committed provenance artifacts."""
    resolved = Path(path).resolve()
    if resolved == Path(OPENALEX_CACHE_DIR).resolve():
        return "data/cache/openalex"
    return resolved.name


def collect(store: Any, companies: Iterable[Mapping[str, Any]], *,
            fetcher: Fetcher | None = None, cache_dir: str | Path | None = None,
            offline: bool = False, refresh: bool = False,
            start_year: int = DEFAULT_START_YEAR,
            max_requests: int | None = None) -> dict[str, Any]:
    """Collect annual publication counts for ``companies`` into the store.

    ``companies`` is an iterable of mappings with ``key`` and ``aliases``/``name_en``
    (the rows of ``config/companies_device.json``). With ``offline=True`` no
    network call is made: the cached grouped response for each company must
    exist, otherwise the company is recorded as a failure. A live run caches
    every response under ``cache_dir`` (default ``data/cache/openalex``).
    """
    company_list = [dict(company) for company in companies]
    base_cache = Path(cache_dir) if cache_dir else OPENALEX_CACHE_DIR
    ensure_dir(base_cache)
    if fetcher is None:
        fetcher = Fetcher(
            cache_dir=base_cache, offline=offline, min_interval=0.2,
            max_requests=max_requests if max_requests is not None else len(company_list) + 4,
            ua=POLITE_UA,
        )
    ensure_publication_table(store)
    index = _load_index(base_cache)
    meta = index.get("_meta") if isinstance(index.get("_meta"), dict) else {}
    per_company: dict[str, Any] = {}
    failures: list[dict[str, Any]] = []
    for company in company_list:
        key = str(company.get("key") or "")
        if not key:
            continue
        alias = preferred_alias(company)
        query = build_query(alias, start_year)
        previous = index.get(key) if isinstance(index.get(key), dict) else {}
        try:
            requests_before = int(fetcher.stats["requests"])
            payload = fetcher.get_json(OPENALEX_WORKS, query, refresh=refresh)
            live = int(fetcher.stats["requests"]) > requests_before
            parsed = parse_grouped_counts(payload)
            retrieved_at = utc_now_iso() if live or not previous.get("retrieved_at") else str(previous["retrieved_at"])
            store.conn.execute(
                "DELETE FROM publication_counts WHERE company_key = ? AND source = ?", (key, SOURCE))
            store.conn.executemany(
                "INSERT OR REPLACE INTO publication_counts (company_key, year, works, source, retrieved_at) "
                "VALUES (?, ?, ?, ?, ?)",
                [(key, year, works, SOURCE, retrieved_at) for year, works in parsed["counts"].items()],
            )
            store.conn.commit()
            entry = {
                "name_en": company.get("name_en"),
                "alias": alias,
                "query": query_string(alias, start_year),
                "status": "ok" if parsed["counts"] else "zero_works",
                "years": parsed["counts"],
                "total_works": parsed["total_works"],
                "groups_count": parsed["groups_count"],
                "cost_usd": parsed["cost_usd"],
                "source": SOURCE,
                "retrieved_at": retrieved_at,
                "requests": 1 if live else int(previous.get("requests") or 0),
            }
            per_company[key] = entry
            index[key] = entry
        except (OfflineMiss, HttpError, BudgetExceeded, OSError) as exc:
            failure = {"company_key": key, "alias": alias, "query": query_string(alias, start_year),
                       "error": f"{type(exc).__name__}: {exc}"}
            failures.append(failure)
            per_company[key] = {"name_en": company.get("name_en"), "alias": alias, "status": "failed", **failure}
    if meta and (offline or int(fetcher.stats["requests"]) == 0):
        # A cache replay (or a run that only hit the cache) must not erase the
        # request provenance of the collection that populated the cache.
        request_stats = meta.get("request_stats") or {}
        collected_at = meta.get("retrieved_at")
    else:
        request_stats = dict(fetcher.stats)
        collected_at = utc_now_iso()
        index["_meta"] = {
            "source": "openalex",
            "endpoint": OPENALEX_WORKS,
            "start_year": start_year,
            "query_shape": (
                "filter=raw_affiliation_strings.search:<alias>,"
                "from_publication_date:<start_year>-01-01&group_by=publication_year"),
            "request_stats": request_stats,
            "retrieved_at": collected_at,
        }
    write_json(_index_path(base_cache), index, indent=1)
    with_data = sum(1 for entry in per_company.values() if entry.get("status") in ("ok", "zero_works"))
    return {
        "source": "openalex",
        "endpoint": OPENALEX_WORKS,
        "licence": (
            "OpenAlex metadata is CC0; attribution is appreciated. No API key is required for this "
            "endpoint but a small shared daily budget applies, so requests are throttled and cached."),
        "query_shape": (
            "one grouped request per company: "
            "filter=raw_affiliation_strings.search:<alias>,"
            "from_publication_date:<start_year>-01-01&group_by=publication_year"),
        "start_year": start_year,
        "offline_replay": bool(offline),
        "collected_at": collected_at,
        "request_stats": request_stats,
        "live_requests_this_run": int(fetcher.stats["requests"]),
        "cache_dir": display_path(base_cache),
        "companies_requested": len(per_company),
        "companies_with_data": with_data,
        "companies_zero_works": sum(1 for entry in per_company.values() if entry.get("status") == "zero_works"),
        "companies_failed": len(failures),
        "total_works": sum(int(entry.get("total_works") or 0) for entry in per_company.values()),
        "year_range": {
            "min": min((min(entry["years"]) for entry in per_company.values() if entry.get("years")), default=None),
            "max": max((max(entry["years"]) for entry in per_company.values() if entry.get("years")), default=None),
        },
        "failures": failures,
        "per_company": dict(sorted(per_company.items())),
    }


def load_counts(store: Any) -> dict[str, dict[int, int]]:
    """Read persisted annual counts as ``{company_key: {year: works}}``."""
    try:
        rows = store.conn.execute(
            "SELECT company_key, year, works FROM publication_counts ORDER BY company_key, year").fetchall()
    except sqlite3.OperationalError:
        return {}
    counts: dict[str, dict[int, int]] = {}
    for row in rows:
        try:
            company_key, year, works = str(row[0]), int(row[1]), int(row[2])
        except (TypeError, ValueError):
            continue
        counts.setdefault(company_key, {})[year] = works
    return {key: dict(sorted(years.items())) for key, years in sorted(counts.items())}
