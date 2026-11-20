"""Human judgement lives beside the ledger, never inside it.

The ledger is evidence: append-only, bitemporal, and opened read-only by the serving process so a
buggy or compromised request cannot corrupt the record. Everything a *person* decides - which
filters they care about, what they concluded about a record, what they asked a colleague to do -
is a different kind of fact: it is revisable, personal and worthless as evidence.

This module keeps those facts in their own SQLite database:

* ~watchlist~  - a saved filter, so "relevance" can be answered without asking a form again.
* ~review~     - one row per record: status, assignee, note.
* ~review_event~ - an append-only trail of every review transition, including the actor and time.
* ~audit~      - every write the human side performs, in order, so the deployment can be audited.
* ~delivery~   - what was pushed out, to which channel, and whether it worked.

The ledger database is never modified here, and every function that writes takes the store as an
argument so a test can drive it without a server.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any, Iterable, Mapping

#: Review states a record can hold. Deliberately small: a queue with twelve statuses is a queue
#: nobody keeps up to date.
REVIEW_STATES = ("NEW", "REVIEWING", "CONFIRMED", "DISMISSED")

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS watchlist (
        id          TEXT PRIMARY KEY,
        name        TEXT NOT NULL,
        filter_json TEXT NOT NULL,
        created_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS review (
        observation_id TEXT PRIMARY KEY,
        status         TEXT NOT NULL,
        assignee       TEXT,
        note           TEXT,
        updated_at     TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS review_event (
        seq            INTEGER PRIMARY KEY AUTOINCREMENT,
        observation_id TEXT NOT NULL,
        action         TEXT NOT NULL,
        from_status    TEXT,
        to_status      TEXT,
        assignee       TEXT,
        note           TEXT,
        actor          TEXT NOT NULL,
        at             TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit (
        seq        INTEGER PRIMARY KEY AUTOINCREMENT,
        at         TEXT NOT NULL,
        actor      TEXT NOT NULL,
        action     TEXT NOT NULL,
        target     TEXT,
        detail     TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS delivery (
        seq       INTEGER PRIMARY KEY AUTOINCREMENT,
        at        TEXT NOT NULL,
        channel   TEXT NOT NULL,
        status    TEXT NOT NULL,
        detail    TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_review_status ON review(status)",
    "CREATE INDEX IF NOT EXISTS idx_review_event_obs ON review_event(observation_id)",
]


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _clean_filter(value: Any) -> dict[str, Any]:
    """Only the fields the feed understands, so a saved filter cannot smuggle anything else."""
    allowed = {"scope", "source", "topic", "company", "record_type", "confirmation",
               "change_state", "published_from", "published_to", "observed_from",
               "observed_to", "min_confidence", "q", "order"}
    if not isinstance(value, Mapping):
        return {}
    out: dict[str, Any] = {}
    for key, item in value.items():
        if key not in allowed or item in (None, "", []):
            continue
        out[key] = item
    return out


class HumanStore:
    """The side store: watchlists, review decisions, audit trail and delivery log."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.con = sqlite3.connect(path, timeout=30, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.execute("PRAGMA synchronous=NORMAL")
        for statement in SCHEMA:
            self.con.execute(statement)
        self.con.commit()

    # ------------------------------------------------------------------ audit
    def audit(self, actor: str, action: str, target: str | None = None,
              detail: Mapping[str, Any] | None = None) -> None:
        self.con.execute(
            "INSERT INTO audit (at, actor, action, target, detail) VALUES (?, ?, ?, ?, ?)",
            (_now(), actor or "unknown", action, target,
             json.dumps(detail, ensure_ascii=False) if detail else None),
        )

    # -------------------------------------------------------------- watchlists
    def list_watchlists(self) -> list[dict[str, Any]]:
        rows = self.con.execute(
            "SELECT id, name, filter_json, created_at, updated_at FROM watchlist ORDER BY created_at"
        ).fetchall()
        return [{**dict(row), "filter": json.loads(row["filter_json"])} for row in rows]

    def get_watchlist(self, watchlist_id: str) -> dict[str, Any] | None:
        row = self.con.execute("SELECT * FROM watchlist WHERE id = ?", (watchlist_id,)).fetchone()
        if row is None:
            return None
        return {**dict(row), "filter": json.loads(row["filter_json"])}

    def save_watchlist(self, name: str, filt: Mapping[str, Any], *,
                       watchlist_id: str | None = None, actor: str = "operator") -> dict[str, Any]:
        name = (name or "").strip()
        if not name:
            raise ValueError("a watchlist needs a name")
        if len(name) > 80:
            raise ValueError("the name is longer than 80 characters")
        payload = json.dumps(_clean_filter(filt), ensure_ascii=False, sort_keys=True)
        now = _now()
        if watchlist_id:
            row = self.con.execute("SELECT id FROM watchlist WHERE id = ?", (watchlist_id,)).fetchone()
            if row is None:
                raise KeyError(watchlist_id)
            self.con.execute(
                "UPDATE watchlist SET name = ?, filter_json = ?, updated_at = ? WHERE id = ?",
                (name, payload, now, watchlist_id),
            )
            action = "watchlist.update"
        else:
            watchlist_id = uuid.uuid4().hex[:12]
            self.con.execute(
                "INSERT INTO watchlist (id, name, filter_json, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (watchlist_id, name, payload, now, now),
            )
            action = "watchlist.create"
        self.audit(actor, action, watchlist_id, {"name": name, "filter": json.loads(payload)})
        self.con.commit()
        return self.get_watchlist(watchlist_id) or {}

    def delete_watchlist(self, watchlist_id: str, *, actor: str = "operator") -> bool:
        row = self.con.execute("SELECT name FROM watchlist WHERE id = ?", (watchlist_id,)).fetchone()
        if row is None:
            return False
        self.con.execute("DELETE FROM watchlist WHERE id = ?", (watchlist_id,))
        self.audit(actor, "watchlist.delete", watchlist_id, {"name": row["name"]})
        self.con.commit()
        return True

    # ------------------------------------------------------------------ review
    def get_review(self, observation_id: str) -> dict[str, Any] | None:
        row = self.con.execute(
            "SELECT observation_id, status, assignee, note, updated_at FROM review WHERE observation_id = ?",
            (observation_id,),
        ).fetchone()
        return dict(row) if row else None

    def reviews(self, observation_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
        ids = [item for item in observation_ids if item]
        if not ids:
            return {}
        out: dict[str, dict[str, Any]] = {}
        for start in range(0, len(ids), 400):
            chunk = ids[start:start + 400]
            marks = ",".join("?" * len(chunk))
            for row in self.con.execute(
                f"SELECT observation_id, status, assignee, note, updated_at FROM review"
                f" WHERE observation_id IN ({marks})", chunk):
                out[row["observation_id"]] = dict(row)
        return out

    def set_review(self, observation_id: str, *, status: str | None = None,
                   assignee: str | None = None, note: str | None = None,
                   actor: str = "operator") -> dict[str, Any]:
        """Record a human decision. Every call appends a review_event row."""
        if status is not None and status not in REVIEW_STATES:
            raise ValueError(f"unknown review status {status!r}; expected one of {REVIEW_STATES}")
        current = self.get_review(observation_id)
        from_status = current["status"] if current else None
        next_status = status or from_status or "NEW"
        next_assignee = assignee if assignee is not None else (current["assignee"] if current else None)
        next_note = note if note is not None else (current["note"] if current else None)
        now = _now()
        self.con.execute(
            "INSERT INTO review (observation_id, status, assignee, note, updated_at)"
            " VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(observation_id) DO UPDATE SET status = excluded.status,"
            " assignee = excluded.assignee, note = excluded.note, updated_at = excluded.updated_at",
            (observation_id, next_status, next_assignee, next_note, now),
        )
        action = "status" if status is not None and status != from_status else "update"
        self.con.execute(
            "INSERT INTO review_event (observation_id, action, from_status, to_status,"
            " assignee, note, actor, at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (observation_id, action, from_status, next_status, next_assignee, next_note,
             actor or "unknown", now),
        )
        self.audit(actor, "review." + action, observation_id,
                   {"from": from_status, "to": next_status, "assignee": next_assignee})
        self.con.commit()
        return self.get_review(observation_id) or {}

    def review_queue(self, *, status: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        sql = ("SELECT observation_id, status, assignee, note, updated_at FROM review")
        params: list[Any] = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(int(limit))
        return [dict(row) for row in self.con.execute(sql, params)]

    def review_history(self, observation_id: str, limit: int = 50) -> list[dict[str, Any]]:
        return [dict(row) for row in self.con.execute(
            "SELECT seq, action, from_status, to_status, assignee, note, actor, at"
            " FROM review_event WHERE observation_id = ? ORDER BY seq DESC LIMIT ?",
            (observation_id, int(limit)),
        )]

    def stats(self) -> dict[str, Any]:
        by_status = {row["status"]: row["n"] for row in self.con.execute(
            "SELECT status, COUNT(*) AS n FROM review GROUP BY status")}
        return {
            "reviews": sum(by_status.values()),
            "by_status": by_status,
            "watchlists": self.con.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0],
            "audit_rows": self.con.execute("SELECT COUNT(*) FROM audit").fetchone()[0],
        }

    # ------------------------------------------------------------------- audit
    def audit_log(self, limit: int = 200) -> list[dict[str, Any]]:
        return [dict(row) for row in self.con.execute(
            "SELECT seq, at, actor, action, target, detail FROM audit ORDER BY seq DESC LIMIT ?",
            (int(limit),),
        )]

    def record_delivery(self, channel: str, status: str, detail: Mapping[str, Any] | None = None) -> None:
        self.con.execute(
            "INSERT INTO delivery (at, channel, status, detail) VALUES (?, ?, ?, ?)",
            (_now(), channel, status, json.dumps(detail, ensure_ascii=False) if detail else None),
        )
        self.con.commit()

    def deliveries(self, limit: int = 50) -> list[dict[str, Any]]:
        return [dict(row) for row in self.con.execute(
            "SELECT seq, at, channel, status, detail FROM delivery ORDER BY seq DESC LIMIT ?",
            (int(limit),),
        )]

    def close(self) -> None:
        try:
            self.con.close()
        except Exception:
            pass


def open_human_store(path: str) -> HumanStore:
    return HumanStore(path)