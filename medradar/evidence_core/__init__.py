"""Evidence Core v1 — append-only revision ledger behind ``events``.

ADR-001 option C, Phase 2. The public entry point is
:func:`medradar.evidence_core.migrations.ensure_schema`, called from
``medradar.db.DB.__init__`` after the legacy forward-migration adds the timing
columns.

Guarantees (and only these — see ``docs/refoundation/phase2/EVIDENCE_CORE_V1.md``
for the full bypass matrix):

* every row in ``event_revision`` is a full snapshot of one write/version;
* ``UPDATE``/``DELETE``/resubmitting an existing ``(event_id, version)`` are
  rejected by SQLite triggers;
* the write path in :func:`medradar.db.DB.upsert_events` appends exactly one
  revision per content change, none for an identical re-import, and keeps
  ``first_seen_at`` monotonic (MIN, never later).

It does **not** make ``events`` immutable: the head table is still a normal
table, ``INSERT OR REPLACE``/direct SQL can change it without a revision, and a
database owner can drop triggers or replace the file. ``reconcile`` detects the
first class of bypass, not the rest.
"""

from __future__ import annotations

from .ledger import (
    EVENT_CONTENT_FIELDS,
    EVENT_SNAPSHOT_FIELDS,
    canonical_json,
    content_hash,
    latest_revision,
    reconcile,
    revisions_for,
    sha256_hex,
    snapshot_of_row,
)
from .migrations import MIGRATIONS, SCHEMA_TABLE, ensure_schema, reinstall_guards, verify_guards

__all__ = [
    "EVENT_CONTENT_FIELDS",
    "EVENT_SNAPSHOT_FIELDS",
    "MIGRATIONS",
    "SCHEMA_TABLE",
    "canonical_json",
    "content_hash",
    "ensure_schema",
    "latest_revision",
    "reconcile",
    "reinstall_guards",
    "revisions_for",
    "sha256_hex",
    "snapshot_of_row",
    "verify_guards",
]
