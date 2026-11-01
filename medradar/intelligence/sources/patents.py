"""USPTO Open Data Portal patent adapter — API key required.

The USPTO Open Data Portal application-search endpoint requires an API key;
without one it answers HTTP 401. This module therefore has an honest blocked
path: if ``USPTO_ODP_API_KEY`` is absent it returns
``{"status": "unavailable_missing_api_key", "rows": 0, ...}`` and creates no
rows. It never fabricates patent counts.

Two collection paths are supported:

1. :func:`collect` — live USPTO ODP search by assignee (needs the key).
   Endpoint (documented by USPTO, shape unverified in this environment):
   ``POST https://api.uspto.gov/api/v1/patent/applications/search`` with
   ``X-API-KEY: <key>`` and a JSON body such as
   ``{"q": "<assignee alias>", "fields": [...], "pagination": {...}}``.
   The response parser accepts the documented ``patentFileWrapperDataBag``
   collection (and a few equivalent keys) and stores only fields actually
   present in the response.
2. :func:`collect_from_jsonl` — import a user-provided JSONL export with
   documented columns, so the point-in-time feature path is testable and usable
   once any patent export exists.

Point-in-time rule: knowledge time is the **publication date**, never the filing
date. A patent application filed before a cutoff but published after it is not
known at the cutoff and is ignored by the feature builder.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Mapping

from ...http import Fetcher
from ...util import iso, parse_date, utc_now_iso

USPTO_ODP_APPLICATIONS = "https://api.uspto.gov/api/v1/patent/applications/search"
USPTO_API_KEY_ENV = "USPTO_ODP_API_KEY"
MISSING_KEY_WARNING = (
    "USPTO Open Data Portal requires an API key (HTTP 401 without one). "
    f"Set {USPTO_API_KEY_ENV} or import a JSONL export with "
    "patents.collect_from_jsonl(); no patent rows were collected and none were fabricated.")
JSONL_COLUMNS = (
    "application_id", "company_key", "assignee", "filing_date", "publication_date",
    "title", "source", "retrieved_at",
)
PATENT_DDL = """
CREATE TABLE IF NOT EXISTS patent_applications (
    application_id TEXT PRIMARY KEY,
    company_key TEXT,
    assignee TEXT,
    filing_date TEXT,
    publication_date TEXT,
    title TEXT,
    source TEXT NOT NULL,
    retrieved_at TEXT NOT NULL
);
"""


def api_key(provided: str | None = None) -> str | None:
    return provided or os.environ.get(USPTO_API_KEY_ENV) or None


def ensure_patent_table(store: Any) -> None:
    store.conn.executescript(PATENT_DDL)
    store.conn.commit()


def _normalize_date(value: Any) -> str | None:
    return iso(value) or None


def normalize_application(row: Mapping[str, Any], *, source: str,
                          retrieved_at: str) -> dict[str, Any] | None:
    """Map one raw application row to the stored shape; never invent fields."""
    application_id = row.get("application_id") or row.get("applicationNumberText") or row.get("applicationNumber")
    application_id = str(application_id or "").strip()
    if not application_id:
        return None
    return {
        "application_id": application_id,
        "company_key": row.get("company_key"),
        "assignee": row.get("assignee"),
        "filing_date": _normalize_date(row.get("filing_date") or row.get("filingDate")),
        "publication_date": _normalize_date(row.get("publication_date") or row.get("publicationDate")),
        "title": row.get("title") or row.get("inventionTitle"),
        "source": source,
        "retrieved_at": retrieved_at,
    }


def collect(store: Any, companies: Iterable[Mapping[str, Any]], *,
            fetcher: Fetcher | None = None, limit: int = 0,
            key: str | None = None) -> dict[str, Any]:
    """Collect patent applications from USPTO ODP, or return the blocked status.

    Without an API key this returns ``unavailable_missing_api_key`` and writes
    nothing. With a key it queries by assignee alias and stores only returned
    applications; failures are recorded per company rather than replaced with
    numbers.
    """
    company_list = [dict(company) for company in companies]
    resolved_key = api_key(key)
    if not resolved_key:
        return {
            "status": "unavailable_missing_api_key",
            "warning": MISSING_KEY_WARNING,
            "rows": 0,
            "companies_requested": len(company_list),
            "endpoint": USPTO_ODP_APPLICATIONS,
            "env_var": USPTO_API_KEY_ENV,
            "evaluated": False,
            "note": "No patent ablation numbers are reported; patents are not evaluated in this environment.",
        }
    fetcher = fetcher or Fetcher(min_interval=1.0, max_requests=max(len(company_list) + 2, 10))
    ensure_patent_table(store)
    retrieved_at = utc_now_iso()
    rows_written = 0
    per_company: dict[str, Any] = {}
    failures: list[dict[str, Any]] = []
    attempted = 0
    for company in company_list:
        aliases = [str(alias).strip() for alias in (company.get("aliases") or []) if str(alias or "").strip()]
        assignee = aliases[0] if aliases else str(company.get("name_en") or company.get("key") or "")
        key_name = str(company.get("key") or "")
        if limit and attempted >= limit:
            break
        attempted += 1
        body = {
            "q": assignee,
            "fields": ["applicationNumberText", "filingDate", "publicationDate", "inventionTitle"],
            "pagination": {"offset": 0, "limit": 100},
        }
        try:
            payload = fetcher.post_json(
                USPTO_ODP_APPLICATIONS, body,
                retries=1, backoff=2.0,
            )
            raw_rows = (
                payload.get("patentFileWrapperDataBag")
                or payload.get("results")
                or payload.get("data")
                or []
            )
            stored = []
            for raw in raw_rows:
                normalized = normalize_application(raw, source="uspto_odp_search", retrieved_at=retrieved_at)
                if normalized is not None:
                    if not normalized.get("company_key"):
                        normalized["company_key"] = key_name
                    stored.append(normalized)
            if stored:
                store.conn.executemany(
                    "INSERT OR REPLACE INTO patent_applications VALUES (?,?,?,?,?,?,?,?)",
                    [(row["application_id"], row["company_key"], row["assignee"], row["filing_date"],
                      row["publication_date"], row["title"], row["source"], row["retrieved_at"])
                     for row in stored])
                store.conn.commit()
            rows_written += len(stored)
            per_company[key_name] = {"assignee": assignee, "rows": len(stored), "status": "ok"}
        except Exception as exc:  # noqa: BLE001 - record API failures honestly
            failures.append({"company_key": key_name, "assignee": assignee,
                             "error": f"{type(exc).__name__}: {exc}"})
            per_company[key_name] = {"assignee": assignee, "status": "failed",
                                     "error": f"{type(exc).__name__}: {exc}"}
    return {
        "status": "ok" if not failures else "partial_failures",
        "rows": rows_written,
        "companies_requested": len(company_list),
        "per_company": per_company,
        "failures": failures,
        "endpoint": USPTO_ODP_APPLICATIONS,
        "retrieved_at": retrieved_at,
        "evaluated": False,
        "note": "Patent ablation is not evaluated; this adapter only collects applications when a key exists.",
    }


def collect_from_jsonl(path: str | Path, store: Any = None, *,
                       retrieved_at: str | None = None) -> dict[str, Any]:
    """Import a local JSONL export (one JSON object per line).

    Documented columns: ``application_id`` (required), ``company_key``,
    ``assignee``, ``filing_date``, ``publication_date``, ``title``. Extra keys
    are ignored. Invalid lines are skipped and counted, never guessed.
    """
    retrieved = retrieved_at or utc_now_iso()
    rows: list[dict[str, Any]] = []
    skipped = 0
    target = Path(path)
    if not target.exists():
        return {"status": "file_not_found", "rows": 0, "skipped": 0, "path": str(target),
                "applications": [], "warning": "No JSONL export was found; nothing was imported."}
    for line in target.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            skipped += 1
            continue
        if not isinstance(raw, dict):
            skipped += 1
            continue
        normalized = normalize_application(raw, source="jsonl_import", retrieved_at=retrieved)
        if normalized is None:
            skipped += 1
            continue
        rows.append(normalized)
    if store is not None and rows:
        ensure_patent_table(store)
        store.conn.executemany(
            "INSERT OR REPLACE INTO patent_applications VALUES (?,?,?,?,?,?,?,?)",
            [(row["application_id"], row["company_key"], row["assignee"], row["filing_date"],
              row["publication_date"], row["title"], row["source"], row["retrieved_at"]) for row in rows])
        store.conn.commit()
    return {"status": "ok", "rows": len(rows), "skipped": skipped, "path": str(target),
            "applications": rows}


def load_publications(store: Any) -> dict[str, list]:
    """Publication dates per company, used by the point-in-time patent features."""
    try:
        rows = store.conn.execute(
            "SELECT company_key, publication_date FROM patent_applications "
            "WHERE company_key IS NOT NULL AND publication_date IS NOT NULL").fetchall()
    except sqlite3.OperationalError:
        return {}
    result: dict[str, list] = {}
    for row in rows:
        day = parse_date(row[1])
        if day is not None:
            result.setdefault(str(row[0]), []).append(day)
    return {key: sorted(days) for key, days in sorted(result.items())}
