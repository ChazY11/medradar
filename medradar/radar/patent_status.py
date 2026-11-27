"""Whether patent collection is working, in the same vocabulary as everything else here.

The problem this exists for
---------------------------
Measured on the live deployment: every nightly patent batch returned
`TransientHttpError: 503 Service Unavailable` for all eight companies, for at least a week. Nothing
recorded that. `/sources` went on printing "专利只覆盖了 92 个受让人" as though the number were simply
behind, and the only trace of the block was a journal line.

A coverage number that cannot move because its source refuses us is a different fact from a coverage
number that is behind because nobody has run the job. This module records the attempt, so the page can
say which one it is.
"""

from __future__ import annotations

from typing import Any

STATUS_SCHEMA = """
CREATE TABLE IF NOT EXISTS patent_fetch_state (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    attempted_at  TEXT NOT NULL,
    attempted     INTEGER NOT NULL DEFAULT 0,
    failed        INTEGER NOT NULL DEFAULT 0,
    detail        TEXT
);
"""


def ensure_table(reference) -> None:
    reference.conn.executescript(STATUS_SCHEMA)


def record_attempt(reference, *, attempted: int, failed: int, detail: str = "",
                   at: str | None = None) -> None:
    """Remember that a batch was tried, and how much of it the source refused."""
    from .records import utc_now_iso

    ensure_table(reference)
    reference.conn.execute(
        "INSERT OR REPLACE INTO patent_fetch_state (id, attempted_at, attempted, failed, detail)"
        " VALUES (1, ?, ?, ?, ?)",
        (at or utc_now_iso(), int(attempted), int(failed), (detail or "")[:300]))
    reference.conn.commit()


def read(reference) -> dict[str, Any]:
    """The last attempt, or an empty answer for a store that has never tried."""
    try:
        ensure_table(reference)
        row = reference.conn.execute(
            "SELECT attempted_at, attempted, failed, detail FROM patent_fetch_state").fetchone()
    except Exception:  # noqa: BLE001 - no table yet is an answer
        return {"available": False}
    if not row:
        return {"available": False}
    attempted, failed = int(row[1] or 0), int(row[2] or 0)
    return {
        "available": True,
        "attempted_at": row[0],
        "attempted": attempted,
        "failed": failed,
        # "Refused" means the source answered and said no - a 503 block - as opposed to a partial
        # batch where some companies came back and some did not.
        "refused": bool(attempted) and failed >= attempted,
        "detail": row[3] or "",
    }


__all__ = ["ensure_table", "read", "record_attempt"]
