"""RELEASE-GATE-001: the v2->v3 admission migration must be resumable.

Measured on an isolated copy of the production ledger: the schema version is bumped to v3 before
the old admission rows are copied forward. A crash in that window used to leave a ledger that
claimed to be v3 while every judgement still lived in the renamed observation_admission_v2
table - and the next open saw v3, skipped the legacy branch, and the product read zero
admissions. 8,360 rows, permanently invisible, with the data still on disk.

The test builds exactly that interrupted state and asserts that reopening repairs it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

try:
    import pytest  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover
    raise unittest.SkipTest("pytest is not installed; run these tests with pytest")

from medradar.radar.ledger import SCHEMA, ObservationLedger
from medradar.radar.relevance import ADMISSION_VERSION


def _row(observation_id: str) -> dict:
    import json

    return {
        "observation_id": observation_id,
        "admission_version": ADMISSION_VERSION,
        "tier": "HIGH_RELEVANCE",
        "category": "MONITORING_DEVICE",
        "score": 0.9,
        "reasons": json.dumps(["migrated"]),
        "features": "{}",
        "decision": "FEED",
        "dimensions": json.dumps({"monitoring_relevance": "DIRECT"}),
        "rules_digest": "legacy",
        "evidence_key": "legacy-evidence",
        "judged_version_id": None,
        "decided_at": "2026-11-18T00:00:00Z",
    }


def _interrupt_migration(path: Path) -> None:
    """Reproduce the exact on-disk state of a crash between the version bump and the copy."""
    handle = ObservationLedger(path)
    handle.record_admissions([_row("obs-1"), _row("obs-2")])
    assert handle.con.execute("SELECT COUNT(*) FROM observation_admission").fetchone()[0] == 2
    handle.con.execute("ALTER TABLE observation_admission RENAME TO observation_admission_v2")
    handle.con.executescript(SCHEMA)          # the v3 table exists again, empty
    handle.con.execute("UPDATE meta SET value='radar-ledger-v3' WHERE key='schema_version'")
    handle.close()


def test_a_crash_between_the_version_bump_and_the_copy_is_repaired_on_reopen(tmp_path: Path):
    path = tmp_path / "radar.db"
    _interrupt_migration(path)

    # The damaged state: v3 declared, no live judgements, the history stranded in the old table.
    con = sqlite3.connect(str(path))
    assert dict(con.execute("SELECT key, value FROM meta")).get("schema_version") == "radar-ledger-v3"
    assert con.execute("SELECT COUNT(*) FROM observation_admission").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM observation_admission_v2").fetchone()[0] == 2
    con.close()

    # Reopening with write access must finish the migration instead of freezing the loss.
    repaired = ObservationLedger(path)
    try:
        assert repaired.con.execute("SELECT COUNT(*) FROM observation_admission").fetchone()[0] == 2
        assert repaired.con.execute(
            "SELECT COUNT(*) FROM admission_current").fetchone()[0] >= 2
        tables = {row[0] for row in repaired.con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "observation_admission_v2" not in tables, "the leftover table is cleaned up"
        current = repaired._admissions_for(["obs-1"], ADMISSION_VERSION)["obs-1"]
        assert current["tier"] == "HIGH_RELEVANCE"
    finally:
        repaired.close()


def test_finishing_a_migration_twice_adds_nothing(tmp_path: Path):
    path = tmp_path / "radar.db"
    _interrupt_migration(path)
    first = ObservationLedger(path)
    rows_after_first = first.con.execute("SELECT COUNT(*) FROM observation_admission").fetchone()[0]
    first.close()
    second = ObservationLedger(path)
    try:
        assert second.con.execute(
            "SELECT COUNT(*) FROM observation_admission").fetchone()[0] == rows_after_first
    finally:
        second.close()