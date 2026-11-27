"""Counts that change slowly, written once and read cheaply.

Why this exists
---------------
The landing page counts five stores. Measured warm: `COUNT(DISTINCT paper_id) FROM paper_term` takes
360 ms over 785k rows, `COUNT(*) FROM udi_device` 59 ms over 5.2M, and the corpus is a directory
listing of 40,731 files. Cold, with the pages not yet in the OS cache, the same page took 1.8 s
locally and 6.5 s through the tunnel.

None of those numbers changes between two visits, and the scheduler cycle that would change them
runs every five minutes. So they are computed by a job and stored with the time they were taken.

The honest part
---------------
A cached number is a claim about the past, so the page prints `updated_at` beside the counters and
says when they were last refreshed. A materialised table that shows a number without its timestamp
is the same failure as a summary card without its qualifier, one layer down.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS store_stats (
  key        TEXT PRIMARY KEY,
  value      INTEGER NOT NULL,
  updated_at TEXT NOT NULL
);
"""

#: key -> SQL. Every entry is a count of rows the landing page shows.
#:
#: Two of these are slow enough to matter and are the reason the whole set is materialised:
#: `register_codes` expands the JSON product codes of 5.2M rows (6.7 s warm, far worse cold) and
#: `labelers` is a distinct over the same table (0.7 s). Measured on the coverage page: reading them
#: live made /sources take 21.5 s.
COUNTS: dict[str, str] = {
    "devices": "SELECT COUNT(*) FROM udi_device",
    "labelers": "SELECT COUNT(DISTINCT labeler_duns) FROM udi_device",
    "register_codes": "SELECT COUNT(DISTINCT j.value) FROM udi_device d, "
                      "json_each(d.product_codes) j",
    "failures": "SELECT COUNT(*) FROM maude_failure_index",
    "failure_codes": "SELECT COUNT(DISTINCT product_code) FROM maude_failure_index",
    "failure_models": "SELECT COUNT(DISTINCT model_norm) FROM maude_failure_index",
    "failure_brands": "SELECT COUNT(DISTINCT brand_norm) FROM maude_failure_index",
    "trials": "SELECT COUNT(*) FROM trial",
    "trial_sponsors": "SELECT COUNT(DISTINCT lead_sponsor) FROM trial",
    "patents": "SELECT COUNT(*) FROM bulk_patent",
    "patent_assignees": "SELECT COUNT(DISTINCT organization_norm) FROM bulk_patent_assignee "
                        "WHERE COALESCE(assignee_type,'applicant') <> 'query_matched'",
    "papers": "SELECT COUNT(DISTINCT paper_id) FROM paper_term",
    "codes": "SELECT COUNT(*) FROM product_code_class",
    "specialties": "SELECT COUNT(DISTINCT medical_specialty) FROM product_code_class",
}


def ensure_table(reference) -> None:
    reference.conn.executescript(SCHEMA)


def refresh(reference, *, corpus_dir: str | Path | None = None,
            papers_dir: str | Path | None = None) -> dict[str, Any]:
    """Recompute every count and store it with one timestamp shared by the set."""
    ensure_table(reference)
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    written: dict[str, int] = {}
    for key, sql in COUNTS.items():
        try:
            value = int(reference.conn.execute(sql).fetchone()[0] or 0)
        except Exception:  # noqa: BLE001 - an absent table is a zero, and the key is still recorded
            value = 0
        reference.conn.execute(
            "INSERT OR REPLACE INTO store_stats (key, value, updated_at) VALUES (?,?,?)",
            (key, value, at))
        written[key] = value
    if corpus_dir is not None:
        try:
            count = sum(1 for _ in Path(corpus_dir).glob("*.json"))
        except OSError:
            count = 0
        reference.conn.execute(
            "INSERT OR REPLACE INTO store_stats (key, value, updated_at) VALUES (?,?,?)",
            ("corpus", count, at))
        written["corpus"] = count
    if papers_dir is not None:
        # A corpus file that yields no vocabulary term is not searchable, and the count alone hid that:
        # measured 2026-11-28, 5,755 files produced 5,485 indexed papers and nothing on the page said
        # where the other 270 went.
        try:
            files = sum(1 for _ in Path(papers_dir).glob("*.json"))
        except OSError:
            files = 0
        try:
            indexed = int(reference.conn.execute(
                "SELECT COUNT(*) FROM paper_meta").fetchone()[0] or 0)
        except Exception:  # noqa: BLE001 - no index yet
            indexed = 0
        for key, value in (("paper_files", files), ("paper_indexed", indexed)):
            reference.conn.execute(
                "INSERT OR REPLACE INTO store_stats (key, value, updated_at) VALUES (?,?,?)",
                (key, value, at))
            written[key] = value
    reference.conn.commit()
    return {"updated_at": at, "counts": written}


def peek(reference) -> dict[str, Any]:
    """The stored counts, without creating the table.

    `read` calls `ensure_table`, which is a write. On a read-only connection that raises, so a read
    path fell through to the expensive scan every time - and on a writable connection the write
    changed the file's mtime, which invalidated the paper counter cache that is keyed on it.
    """
    try:
        rows = reference.conn.execute(
            "SELECT key, value, updated_at FROM store_stats").fetchall()
    except Exception:  # noqa: BLE001 - no table yet is an answer, not an error
        return {"available": False, "counts": {}, "updated_at": None}
    counts: dict[str, int] = {}
    stamps: set[str] = set()
    for key, value, at in rows:
        counts[str(key)] = int(value)
        if at:
            stamps.add(str(at))
    if not counts:
        return {"available": False, "counts": {}, "updated_at": None}
    return {"available": True, "counts": counts,
            "updated_at": max(stamps) if stamps else None,
            "mixed_stamps": len(stamps) > 1}


def read(reference) -> dict[str, Any]:
    """The stored counts and the moment they were taken, or an empty answer if never refreshed."""
    try:
        ensure_table(reference)
        rows = reference.conn.execute(
            "SELECT key, value, updated_at FROM store_stats").fetchall()
    except Exception:  # noqa: BLE001
        return {"available": False, "counts": {}, "updated_at": None}
    counts: dict[str, int] = {}
    stamps: set[str] = set()
    for key, value, at in rows:
        counts[str(key)] = int(value)
        if at:
            stamps.add(str(at))
    if not counts:
        return {"available": False, "counts": {}, "updated_at": None}
    # One timestamp for the set; if a key was refreshed separately the newest is the honest one to
    # print, because it is the least stale.
    return {"available": True, "counts": counts, "updated_at": max(stamps) if stamps else None}


def age_seconds(reference_read: dict[str, Any]) -> float | None:
    at = reference_read.get("updated_at")
    if not at:
        return None
    try:
        stamp = datetime.fromisoformat(str(at).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - stamp).total_seconds()


__all__ = ["COUNTS", "age_seconds", "ensure_table", "read", "refresh"]
