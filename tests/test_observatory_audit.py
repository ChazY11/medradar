"""Synthetic tier — read-only Observation Ledger integrity audit (design §7).

Everything here is synthetic and offline: the ledger, the prospective registry and
the backup manifest all live under ``tmp_path`` (``MEDRADAR_OBSERVATORY_DB`` /
``MEDRADAR_PROSPECTIVE_DIR``), and the real ``data/observatory/observatory.sqlite``
is never opened or written.  Every frozen entry carries the ``合成测试`` marker so
nothing here can be mistaken for a real prospective observation.

What is proven here:

* a clean ledger with **no** prospective registry and **no** backup evidence is
  ``REQUIRES_MANUAL_REVIEW`` (never PASS on absence), with exactly the checks the
  environment supports passing and exactly two manual-review checks;
* the same ledger **with** a synthetic frozen registry entry and a synthetic
  backup manifest whose created_at is not older than the last ledger write is a
  full ``PASS`` (and ``run_audit`` exits 0);
* injected corruption is detected with concrete offending ids/counts:
  - a raw-SQL duplicate observation row -> ``duplicate_observations`` FAIL
    (the fixture weakens the ``UNIQUE(source, source_record_id)`` constraint,
    because the real schema makes that duplication impossible);
  - an orphan version row without a change row -> ``version_change_consistency``
    and ``payload_version_chain`` FAIL;
  - a FAILED run that advanced a newer watermark -> ``watermark_safety``
    ``REQUIRES_MANUAL_REVIEW`` with the run id; an unattributable newer watermark
    is ``FAIL``;
  - a tampered frozen prospective document -> ``prospective_freeze_integrity``
    FAIL;
  - a backup manifest whose counts do not match the live ledger -> FAIL;
* ``render_report`` prints every check title and verdict plus the explicit
  "needs human review" section, and never a naked ``PASS`` / ``FAIL`` line;
* the audit is genuinely read-only: the ledger file's SHA-256 is identical
  before/after, and a second audit yields identical verdicts;
* a legacy observation whose ``first_seen_at``/``captured_at`` are spelled with
  ``Z`` (raw SQL, as old rows are) is **not** reported as a replay anomaly: the
  audit derives every ``snapshot(as_of=...)`` boundary from a parsed datetime, so
  the ``Z`` / ``+00:00`` spelling never decides which records a replay contains.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from medradar.observatory import audit as audit_module
from medradar.observatory import ledger as ledger_module
from medradar.observatory import prospective as prospective_module
from medradar.observatory.ledger import ObservationLedger
from medradar.observatory.records import (
    ENTITY_MAPPED,
    RUN_OK,
    MappingResult,
    RawRecord,
    canonical_json,
    observation_id as make_observation_id,
    payload_hash,
    utc_now_iso,
    version_id as make_version_id,
)

MAPPING_VERSION = "obs-mapping-v1"
COLLECTOR_VERSION = "test-collector/1.0"
SOURCE = "synthetic_source"
RUN_ID = "synthetic-run-0001"

#: Synthetic observation timeline (second precision, ``+00:00`` like the collector).
T0 = "2026-11-01T10:00:00+00:00"
T1 = "2026-11-02T10:00:00+00:00"
T2 = "2026-11-03T10:00:00+00:00"


# --------------------------------------------------------------------- fixtures
@pytest.fixture()
def env(tmp_path, monkeypatch):
    ledger_path = tmp_path / "observatory.sqlite"
    registry_dir = tmp_path / "prospective"
    monkeypatch.setenv("MEDRADAR_OBSERVATORY_DB", str(ledger_path))
    monkeypatch.setenv("MEDRADAR_PROSPECTIVE_DIR", str(registry_dir))
    ledger = ObservationLedger(ledger_path)
    try:
        yield SimpleNamespace(
            ledger=ledger,
            ledger_path=ledger_path,
            registry_dir=registry_dir,
            tmp_path=tmp_path,
        )
    finally:
        ledger.close()


def _record(record_id: str, *, revision: int = 1, source: str = SOURCE) -> RawRecord:
    return RawRecord(
        source=source,
        source_record_id=record_id,
        record_type="synthetic_record",
        title=f"合成测试记录 {record_id} v{revision}",
        url=f"https://example.invalid/synthetic/{record_id}",
        event_at="2026-10-25",
        event_at_precision="date",
        published_at="2026-10-25T12:00:00+00:00",
        published_at_precision="datetime",
        payload={"record_id": record_id, "revision": revision, "status": "active"},
    )


def _mapping() -> MappingResult:
    return MappingResult(
        entity_id="synthetic_entity",
        entity_status=ENTITY_MAPPED,
        entity_method="synthetic_exact",
        entity_confidence=1.0,
        track_id="synthetic_track",
        track_status="MAPPED",
        track_method="synthetic_keyword",
    )


def _collect(ledger: ObservationLedger, record_id: str, seen_at: str, *,
             revision: int = 1, mapping: MappingResult | None = None,
             run_id: str = RUN_ID) -> str:
    outcome = ledger.record_observation(
        _record(record_id, revision=revision),
        mapping or _mapping(),
        run_id=run_id,
        collector_version=COLLECTOR_VERSION,
        mapping_version=MAPPING_VERSION,
        seen_at=seen_at,
    )
    return outcome.observation_id


# ------------------------------------------------------- optional phase table
def _phase_table_present(ledger: ObservationLedger) -> bool:
    return bool(
        ledger.con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='observation_phase'"
        ).fetchone()
    )


def _fill_phase_rows(ledger: ObservationLedger) -> bool:
    """Give every observation one synthetic phase row (optional Lead table)."""
    if not _phase_table_present(ledger):
        return False
    con = ledger.con
    columns = [str(row["name"]) for row in con.execute("PRAGMA table_info(observation_phase)")]
    if not {"observation_id", "phase", "assigned_at"} <= set(columns):
        return False
    existing = {
        str(row["observation_id"])
        for row in con.execute("SELECT DISTINCT observation_id FROM observation_phase")
    }
    try:
        rows = con.execute(
            "SELECT observation_id, first_seen_at, first_seen_run_id FROM observation"
        ).fetchall()
        for row in rows:
            observation_id = str(row["observation_id"])
            if observation_id in existing:
                continue
            values = {
                "observation_id": observation_id,
                "phase": "INITIAL_DISCOVERY",
                "assigned_at": row["first_seen_at"],
                "run_id": row["first_seen_run_id"],
                "method": "reconstructed_from_run_history",
                "note_zh": "合成测试：审计测试夹具的采集阶段标注",
            }
            usable = [column for column in columns if column in values]
            con.execute(
                f"INSERT INTO observation_phase ({', '.join(usable)})"
                f" VALUES ({', '.join('?' for _ in usable)})",
                [values[column] for column in usable],
            )
        con.commit()
    except sqlite3.Error:
        try:
            con.rollback()
        except sqlite3.Error:  # pragma: no cover - already rolled back
            pass
        return False
    return True


# --------------------------------------------------------------- clean ledger
@pytest.fixture()
def clean_env(env):
    """A small, fully consistent synthetic ledger (no registry, no backup)."""
    ledger = env.ledger
    ledger.ensure_source(
        SOURCE,
        label_zh="合成测试来源",
        adapter_version="synthetic/1.0",
        declared_cadence_zh="每 6 小时（合成）",
    )
    ledger.start_run(SOURCE, trigger="test", collector_version=COLLECTOR_VERSION,
                     run_id=RUN_ID)
    ledger.finish_run(RUN_ID, status=RUN_OK, counters={"requests": 3, "records_seen": 4})

    # single-version observation
    _collect(ledger, "clean-a", T0)
    # multi-version observation: the replay sample needs one
    _collect(ledger, "clean-b", T0)
    _collect(ledger, "clean-b", T1, revision=2)
    # removed + re-appeared with the identical payload: an extra UPDATED row
    # pointing at the still-latest version (no new version must be created)
    removed_id = _collect(ledger, "clean-c", T0)
    ledger.mark_removed(removed_id, run_id=RUN_ID, seen_at=T1,
                        note_zh="合成测试：来源不再提供该记录")
    _collect(ledger, "clean-c", T2)
    # mapping history: UNMAPPED -> MAPPED appends a second row
    _collect(ledger, "clean-d", T0, mapping=MappingResult())
    _collect(ledger, "clean-d", T1)

    # Source state as a successful collector run leaves it: the watermark was
    # written by the same successful run (watermark_updated_at <= last_success_at).
    watermark = canonical_json({"cursor": "synthetic-1"})
    ledger.con.execute(
        "UPDATE source_state SET status='OK', last_attempt_at=?, last_success_at=?,"
        " watermark=?, watermark_updated_at=? WHERE source=?",
        (T2, T2, watermark, T2, SOURCE),
    )
    ledger.con.commit()

    phase_present = _phase_table_present(ledger)
    phase_filled = _fill_phase_rows(ledger) if phase_present else False
    return SimpleNamespace(
        ledger=ledger,
        ledger_path=env.ledger_path,
        registry_dir=env.registry_dir,
        tmp_path=env.tmp_path,
        phase_present=phase_present,
        phase_filled=phase_filled,
        observation_ids={
            record_id: _record(record_id).observation_id
            for record_id in ("clean-a", "clean-b", "clean-c", "clean-d")
        },
    )


# ----------------------------------------------------------- backup manifest
def _bundle_manifest(ledger: ObservationLedger, manifest_path) -> dict:
    counts = ledger.counts()
    first_seen = ledger.con.execute(
        "SELECT MIN(first_seen_at) AS minimum, MAX(first_seen_at) AS maximum FROM observation"
    ).fetchone()
    per_source = {
        str(row["source"]): int(row["n"])
        for row in ledger.con.execute(
            "SELECT source, COUNT(*) AS n FROM observation GROUP BY source ORDER BY source"
        ).fetchall()
    }
    watermarks = {
        str(row["source"]): {"watermark": row["watermark"]}
        for row in ledger.con.execute(
            "SELECT source, watermark FROM source_state ORDER BY source"
        ).fetchall()
    }
    chain = ledger.con.execute(
        "SELECT COALESCE(MAX(version_count), 0) AS maximum,"
        " COALESCE(SUM(CASE WHEN version_count > 1 THEN 1 ELSE 0 END), 0) AS multi,"
        " COALESCE(SUM(CASE WHEN version_count > 0 THEN 1 ELSE 0 END), 0) AS with_versions"
        " FROM observation"
    ).fetchone()
    manifest = {
        "schema": "medradar-observatory-backup-1",
        "name": "observatory-synthetic-audit",
        "created_at": utc_now_iso(),
        "ledger": {
            "schema_version": counts["schema_version"],
            "integrity_check": "ok",
            "consistency_ok": True,
        },
        "counts": {
            "observations": counts["observations"],
            "versions": counts["versions"],
            "changes": counts["changes"],
            "runs": counts["runs"],
        },
        "first_seen": {
            "min": first_seen["minimum"],
            "max": first_seen["maximum"],
        },
        "per_source_observation_counts": per_source,
        "source_watermarks": watermarks,
        "version_chain": {
            "max_version_count": int(chain["maximum"]),
            "multi_version_observations": int(chain["multi"]),
            "observations_with_versions": int(chain["with_versions"]),
        },
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def _write_default_manifest(ledger: ObservationLedger, manifest_path, *,
                            overrides: dict | None = None) -> dict:
    manifest = _bundle_manifest(ledger, manifest_path)
    if overrides:
        for key, value in overrides.items():
            manifest[key] = value
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    return manifest


# ------------------------------------------------------- synthetic registry
SYNTHETIC_ENTRY_ID = "synthetic-audit-entry-1"


def _freeze_synthetic_entry(ledger: ObservationLedger) -> dict:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    freeze_at = now - timedelta(days=2)
    spec = {
        "entry_id": SYNTHETIC_ENTRY_ID,
        "label_zh": "合成测试：审计用前瞻冻结条目（非真实研究）",
        "hypothesis_zh": "合成测试假设：仅用于验证冻结哈希校验，不代表任何真实研究。",
        "target_event_definition_zh": "合成测试事件定义：只用于测试。",
        "baseline_zh": "合成测试基线：只用于测试。",
        "evaluation_criteria_zh": "合成测试判据：只用于测试。",
        "window_start": freeze_at.isoformat(),
        "window_end": (now + timedelta(days=1)).isoformat(),
        "freeze_at": freeze_at.isoformat(),
        "scope": {"source": SOURCE},
        "synthetic": True,
        "note_zh": "合成测试：仅为审计测试构造，不是真实前瞻观察结果。",
    }
    frozen = prospective_module.freeze(spec, ledger=ledger)
    assert frozen["result"] == "created"
    return frozen


# ----------------------------------------------------------------- helpers
def _checks_by_id(report: dict) -> dict[str, dict]:
    return {check["id"]: check for check in report["checks"]}


def _raw_insert(con: sqlite3.Connection, table: str, values: dict) -> None:
    """Schema-adaptive raw INSERT used to simulate a write that bypassed the API."""
    columns = [str(row["name"]) for row in con.execute(f"PRAGMA table_info({table})")]
    usable = [column for column in columns if column in values]
    con.execute(
        f"INSERT INTO {table} ({', '.join(usable)})"
        f" VALUES ({', '.join('?' for _ in usable)})",
        [values[column] for column in usable],
    )
    con.commit()


def _corrupt_with_duplicate_observation(ledger: ObservationLedger) -> tuple[str, str]:
    """Insert a second observation row for an existing (source, source_record_id).

    The real schema's ``UNIQUE(source, source_record_id)`` makes this impossible
    through SQL, so the fixture rebuilds the ``observation`` table without its
    UNIQUE clauses (the append-only triggers are recreated afterwards).  The
    duplicate row is inserted with raw SQL, exactly like a buggy writer would.
    """
    con = ledger.con
    create_sql = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='observation'"
    ).fetchone()[0]
    # Remove the UNIQUE clause *together with its leading comma* so the remaining
    # CREATE TABLE statement is still valid.
    stripped = re.sub(r",\s*UNIQUE\s*\([^)]*\)", "", str(create_sql))
    if re.search(r"\bUNIQUE\b", stripped, flags=re.IGNORECASE):
        pytest.skip("cannot weaken the observation UNIQUE constraint for this fixture")
    rows = [dict(row) for row in con.execute("SELECT * FROM observation")]
    columns = [str(row["name"]) for row in con.execute("PRAGMA table_info(observation)")]
    con.execute("DROP TABLE observation")
    con.execute(stripped)
    for row in rows:
        con.execute(
            f"INSERT INTO observation ({', '.join(columns)})"
            f" VALUES ({', '.join('?' for _ in columns)})",
            [row[column] for column in columns],
        )
    # DROP TABLE also dropped the observation triggers/indexes: recreate them.
    con.executescript(ledger_module.SCHEMA)
    target = rows[0]
    duplicate = dict(target)
    duplicate["observation_id"] = "dup-" + str(target["observation_id"])
    con.execute(
        f"INSERT INTO observation ({', '.join(columns)})"
        f" VALUES ({', '.join('?' for _ in columns)})",
        [duplicate[column] for column in columns],
    )
    con.commit()
    return str(target["source"]), str(target["source_record_id"])


def _insert_orphan_version(ledger: ObservationLedger, observation_id: str) -> str:
    """Raw version row with no matching change row (a broken append-only chain)."""
    payload = {"record_id": "orphan", "revision": 99, "status": "active"}
    digest = payload_hash(payload)
    payload_text = canonical_json(payload)
    orphan_version_id = make_version_id(observation_id, digest)
    try:
        _raw_insert(
            ledger.con,
            "observation_version",
            {
                "version_id": orphan_version_id,
                "observation_id": observation_id,
                "version_seq": 2,
                "captured_at": T2,
                "change_state": "UPDATED",
                "payload_hash": digest,
                "payload": payload_text,
                "payload_bytes": len(payload_text.encode("utf-8")),
                "changed_fields": None,
                "source_updated_at": None,
                "run_id": RUN_ID,
                "collector_version": COLLECTOR_VERSION,
            },
        )
    except sqlite3.OperationalError:  # pragma: no cover - schema evolution guard
        pytest.skip("observation_version schema cannot be populated by the fixture")
    return orphan_version_id


FAILED_RUN_ID = "synthetic-failed-run-0001"


def _insert_failed_run(ledger: ObservationLedger, *, started_at: str,
                       watermark_before: str | None,
                       watermark_after: str | None,
                       status: str = "FAILED", source: str = SOURCE) -> str:
    _raw_insert(
        ledger.con,
        "sync_run",
        {
            "run_id": FAILED_RUN_ID,
            "source": source,
            "trigger": "test",
            "host": "synthetic-host",
            "started_at": started_at,
            "finished_at": started_at,
            "status": status,
            "collector_version": COLLECTOR_VERSION,
            "watermark_before": watermark_before,
            "watermark_after": watermark_after,
        },
    )
    return FAILED_RUN_ID


#: A legacy, ``Z``-spelled instant — the same moment as ``T0`` written the old way.
Z_T0 = "2026-11-01T10:00:00Z"


def _insert_legacy_z_observation(ledger: ObservationLedger,
                                 record_id: str = "legacy-z") -> str:
    """Insert a complete legacy observation whose timestamps use the ``…Z`` spelling.

    Old ledger rows (written before the canonical-UTC fix) are immutable, so a
    regression fixture has to create one with raw SQL.  It is deliberately a
    *consistent* observation (version + status history + change + mapping), so any
    check that flags it would be flagging the spelling, not real corruption.
    """
    con = ledger.con
    observation_id = make_observation_id(SOURCE, record_id)
    payload = {"record_id": record_id, "revision": 1, "status": "active"}
    digest = payload_hash(payload)
    payload_text = canonical_json(payload)
    legacy_version_id = make_version_id(observation_id, digest)
    try:
        _raw_insert(
            con,
            "observation",
            {
                "observation_id": observation_id,
                "source": SOURCE,
                "source_record_id": record_id,
                "record_type": "synthetic_record",
                "first_seen_at": Z_T0,
                "ingested_at": Z_T0,
                "observation_origin": "LIVE",
                "backfill_reason": None,
                "event_at": "2026-10-25",
                "event_at_precision": "date",
                "published_at": "2026-10-25T12:00:00Z",
                "published_at_precision": "datetime",
                "source_updated_at": None,
                "source_updated_at_precision": "unknown",
                "last_checked_at": Z_T0,
                "source_payload_hash": digest,
                "latest_version_id": legacy_version_id,
                "version_count": 1,
                "observation_status": "ACTIVE",
                "current_change_state": "NEW",
                "last_change_at": Z_T0,
                "first_seen_run_id": RUN_ID,
                "last_checked_run_id": RUN_ID,
                "title": f"合成测试记录 {record_id}（legacy Z 拼写）",
                "original_url": f"https://example.invalid/synthetic/{record_id}",
            },
        )
        _raw_insert(
            con,
            "observation_version",
            {
                "version_id": legacy_version_id,
                "observation_id": observation_id,
                "version_seq": 1,
                "captured_at": Z_T0,
                "change_state": "NEW",
                "payload_hash": digest,
                "payload": payload_text,
                "payload_bytes": len(payload_text.encode("utf-8")),
                "changed_fields": None,
                "source_updated_at": None,
                "run_id": RUN_ID,
                "collector_version": COLLECTOR_VERSION,
            },
        )
        _raw_insert(
            con,
            "observation_status_history",
            {
                "observation_id": observation_id,
                "changed_at": Z_T0,
                "status": "ACTIVE",
                "run_id": RUN_ID,
                "note": "legacy Z 拼写的首行",
            },
        )
        _raw_insert(
            con,
            "observation_change",
            {
                "change_id": f"legacy-z-{observation_id[:12]}",
                "observation_id": observation_id,
                "source": SOURCE,
                "change_state": "NEW",
                "observed_at": Z_T0,
                "version_id": legacy_version_id,
                "previous_version_id": None,
                "changed_fields": "[]",
                "first_seen_at": Z_T0,
                "event_at": "2026-10-25",
                "event_at_precision": "date",
                "published_at": "2026-10-25T12:00:00Z",
                "published_at_precision": "datetime",
                "record_type": "synthetic_record",
                "title": f"合成测试记录 {record_id}（legacy Z 拼写）",
                "url": f"https://example.invalid/synthetic/{record_id}",
                "run_id": RUN_ID,
            },
        )
        _raw_insert(
            con,
            "observation_mapping",
            {
                "observation_id": observation_id,
                "mapped_at": utc_now_iso(),
                "mapping_version": MAPPING_VERSION,
                "entity_id": None,
                "entity_status": "UNMAPPED",
                "entity_method": None,
                "entity_confidence": None,
                "track_id": None,
                "track_status": "UNMAPPED",
                "track_method": None,
                "note_zh": None,
            },
        )
    except sqlite3.OperationalError:  # pragma: no cover - schema evolution guard
        con.rollback()
        pytest.skip("ledger schema cannot host the legacy Z fixture")
    return observation_id


# ---------------------------------------------------------------- clean ledger
def test_clean_ledger_without_registry_or_backup_requires_manual_review(clean_env):
    if clean_env.phase_present and not clean_env.phase_filled:
        pytest.skip("observation_phase table exists but this fixture cannot populate it")

    report = audit_module.audit_ledger(clean_env.ledger_path)
    checks = _checks_by_id(report)

    assert report["schema"] == audit_module.REPORT_SCHEMA
    assert report["audit_version"] == audit_module.AUDIT_VERSION
    assert report["generated_at"]
    assert report["ledger"]["present"] is True
    assert report["ledger"]["read_only"] is True
    assert report["ledger"]["counts"]["observations"] == 4
    assert report["ledger"]["counts"]["versions"] == 5  # clean-b has two versions

    expected_checks = len(audit_module.CHECK_IDS) + (1 if clean_env.phase_present else 0)
    assert len(report["checks"]) == expected_checks
    for check in report["checks"]:
        assert set(check) >= {"id", "title_zh", "verdict", "detail_zh", "evidence"}
        assert check["verdict"] in audit_module.VERDICTS
        assert check["detail_zh"].strip()
        assert isinstance(check["evidence"], dict) and check["evidence"]

    # Missing evidence is never PASS: no registry and no backup bundle.
    manual = {check["id"] for check in report["checks"] if check["verdict"] == "FAIL" or check["verdict"] == audit_module.VERDICT_MANUAL}
    assert manual == {"prospective_freeze_integrity", "backup_restore_reproducibility"}
    assert checks["prospective_freeze_integrity"]["verdict"] == audit_module.VERDICT_MANUAL
    assert checks["backup_restore_reproducibility"]["verdict"] == audit_module.VERDICT_MANUAL
    assert checks["backup_restore_reproducibility"]["evidence"]["manifest_path"] is None
    assert "缺少" in checks["backup_restore_reproducibility"]["detail_zh"]

    passed = [check for check in report["checks"] if check["verdict"] == audit_module.VERDICT_PASS]
    expected_pass = 8 + (1 if clean_env.phase_present else 0)
    assert len(passed) == expected_pass
    # the replay sample is possible because clean-b has two versions
    replay = checks["replay_correctness"]
    assert replay["verdict"] == audit_module.VERDICT_PASS
    assert replay["evidence"]["multi_version_observations"] == 1
    assert replay["evidence"]["sampled_observation_ids"] == [clean_env.observation_ids["clean-b"]]
    assert report["overall"] == audit_module.VERDICT_MANUAL
    assert report["summary"]["manual_review"] == 2
    assert report["summary"]["fail"] == 0
    assert [item["id"] for item in report["manual_review"]] == [
        "prospective_freeze_integrity",
        "backup_restore_reproducibility",
    ]


def test_clean_ledger_with_frozen_entry_and_backup_manifest_passes(clean_env):
    if clean_env.phase_present and not clean_env.phase_filled:
        pytest.skip("observation_phase table exists but this fixture cannot populate it")

    frozen = _freeze_synthetic_entry(clean_env.ledger)
    assert frozen["synthetic"] is True
    assert prospective_module.SYNTHETIC_MARKER in frozen["label_zh"]

    manifest_path = (
        clean_env.ledger_path.parent
        / "backups"
        / "observatory-20260101T000000Z-synthetic"
        / "MANIFEST.json"
    )
    _write_default_manifest(clean_env.ledger, manifest_path)

    report = audit_module.audit_ledger(clean_env.ledger_path)
    checks = _checks_by_id(report)
    assert report["overall"] == audit_module.VERDICT_PASS, [
        (check["id"], check["verdict"], check["detail_zh"]) for check in report["checks"]
    ]
    assert all(check["verdict"] == audit_module.VERDICT_PASS for check in report["checks"])
    assert checks["prospective_freeze_integrity"]["evidence"]["verified_total"] == 1
    assert checks["backup_restore_reproducibility"]["evidence"]["manifest_origin"] == "discovered"
    assert checks["backup_restore_reproducibility"]["evidence"]["strict_identity_expected"] is True

    # The stable CLI entry point returns exit code 0 only outside FAIL.
    exit_code, cli_report = audit_module.run_audit(json_output=False, verbose=False)
    assert exit_code == 0
    assert cli_report["overall"] == audit_module.VERDICT_PASS


# ------------------------------------------------------- legacy Z spelling
def test_legacy_z_spelled_observation_is_not_a_replay_anomaly(env):
    """Regression: a legacy ``…Z`` row must not be missed by replay at its own instant.

    ``Z`` and ``+00:00`` spell the same UTC instant.  The audit derives every
    ``snapshot(as_of=...)`` boundary from a parsed datetime, so a legacy row must
    be replayed exactly like a canonical one — no "same-second boundary" anomaly.
    """
    ledger = env.ledger
    ledger.ensure_source(
        SOURCE,
        label_zh="合成测试来源",
        adapter_version="synthetic/1.0",
        declared_cadence_zh="每 6 小时（合成）",
    )
    ledger.start_run(SOURCE, trigger="test", collector_version=COLLECTOR_VERSION,
                     run_id=RUN_ID)
    ledger.finish_run(RUN_ID, status=RUN_OK, counters={"requests": 1, "records_seen": 2})
    _collect(ledger, "modern-a", T0)
    legacy_id = _insert_legacy_z_observation(ledger, "legacy-z")
    if _phase_table_present(ledger):
        assert _fill_phase_rows(ledger) is True

    report = audit_module.audit_ledger(env.ledger_path)
    checks = _checks_by_id(report)
    assert not [check for check in report["checks"] if check["verdict"] == audit_module.VERDICT_FAIL], [
        (check["id"], check["detail_zh"]) for check in report["checks"]
    ]
    assert report["overall"] == audit_module.VERDICT_MANUAL  # no registry/backup, no multi-version sample

    replay = checks["replay_correctness"]
    # Honest outcome: with no multi-version observation there is nothing to sample.
    assert replay["verdict"] == audit_module.VERDICT_MANUAL
    probe = replay["evidence"]["boundary_probe"]
    assert probe["sampled"] == 2
    assert probe["missing_total"] == 0
    assert legacy_id not in probe["missing_first_seen_boundary"]
    assert "均能返回该记录" in replay["detail_zh"]

    for check_id in (
        "duplicate_observations",
        "first_seen_integrity",
        "payload_version_chain",
        "version_change_consistency",
        "timestamp_ordering",
        "mapping_history_preservation",
    ):
        assert checks[check_id]["verdict"] == audit_module.VERDICT_PASS, (
            check_id,
            checks[check_id]["detail_zh"],
        )
    if "observation_phase_completeness" in checks:
        assert checks["observation_phase_completeness"]["verdict"] == audit_module.VERDICT_PASS


# --------------------------------------------------------------- corruption A
def test_duplicate_observation_is_detected(clean_env):
    if clean_env.phase_present and not clean_env.phase_filled:
        pytest.skip("observation_phase table exists but this fixture cannot populate it")
    source, source_record_id = _corrupt_with_duplicate_observation(clean_env.ledger)

    report = audit_module.audit_ledger(clean_env.ledger_path)
    checks = _checks_by_id(report)
    check = checks["duplicate_observations"]
    assert check["verdict"] == audit_module.VERDICT_FAIL
    assert check["evidence"]["duplicate_groups"] == 1
    duplicate = check["evidence"]["duplicates"][0]
    assert duplicate["source"] == source
    assert duplicate["source_record_id"] == source_record_id
    assert duplicate["rows"] == 2
    assert len(duplicate["observation_ids"]) == 2
    assert report["overall"] == audit_module.VERDICT_FAIL
    assert "duplicate_observations" in report["summary"]["fail_ids"]

    exit_code, _report = audit_module.run_audit()
    assert exit_code == 1


# --------------------------------------------------------------- corruption B
def test_orphan_version_without_change_row_breaks_version_consistency(clean_env):
    if clean_env.phase_present and not clean_env.phase_filled:
        pytest.skip("observation_phase table exists but this fixture cannot populate it")
    observation_id = clean_env.observation_ids["clean-a"]
    orphan_version_id = _insert_orphan_version(clean_env.ledger, observation_id)

    report = audit_module.audit_ledger(clean_env.ledger_path)
    checks = _checks_by_id(report)
    consistency = checks["version_change_consistency"]
    assert consistency["verdict"] == audit_module.VERDICT_FAIL
    kinds = {problem["kind"] for problem in consistency["evidence"]["problems"]}
    assert "version_without_change_row" in kinds
    offending = [
        problem
        for problem in consistency["evidence"]["problems"]
        if problem["kind"] == "version_without_change_row"
    ]
    assert offending[0]["observation_id"] == observation_id
    assert offending[0]["version_id"] == orphan_version_id

    chain = checks["payload_version_chain"]
    assert chain["verdict"] == audit_module.VERDICT_FAIL
    chain_kinds = {problem["kind"] for problem in chain["evidence"]["chain_problems"]}
    assert "version_count_mismatch" in chain_kinds
    assert report["overall"] == audit_module.VERDICT_FAIL


# --------------------------------------------------------------- corruption C
def test_failed_run_with_newer_watermark_requires_manual_review(clean_env):
    if clean_env.phase_present and not clean_env.phase_filled:
        pytest.skip("observation_phase table exists but this fixture cannot populate it")
    started_at = "2026-11-03T12:00:00+00:00"  # newer than last_success_at (T2)
    run_id = _insert_failed_run(
        clean_env.ledger,
        started_at=started_at,
        watermark_before=canonical_json({"cursor": "synthetic-1"}),
        watermark_after=canonical_json({"cursor": "synthetic-2"}),
    )

    report = audit_module.audit_ledger(clean_env.ledger_path)
    check = _checks_by_id(report)["watermark_safety"]
    assert check["verdict"] == audit_module.VERDICT_MANUAL
    assert check["evidence"]["manual_review_triggers"] >= 1
    assert run_id in check["evidence"]["flagged_run_ids"]
    flagged = check["evidence"]["manual_review"]
    assert any(item.get("run_id") == run_id for item in flagged)
    assert report["overall"] == audit_module.VERDICT_MANUAL


def test_watermark_advanced_without_a_failed_run_fails(clean_env):
    if clean_env.phase_present and not clean_env.phase_filled:
        pytest.skip("observation_phase table exists but this fixture cannot populate it")
    # No FAILED/PARTIAL run explains this: the watermark moved without a success.
    clean_env.ledger.con.execute(
        "UPDATE source_state SET watermark_updated_at=? WHERE source=?",
        ("2026-11-03T13:00:00+00:00", SOURCE),
    )
    clean_env.ledger.con.commit()

    report = audit_module.audit_ledger(clean_env.ledger_path)
    check = _checks_by_id(report)["watermark_safety"]
    assert check["verdict"] == audit_module.VERDICT_FAIL
    issues = {item["issue"] for item in check["evidence"]["failures"]}
    assert "watermark_newer_than_last_success" in issues
    assert report["overall"] == audit_module.VERDICT_FAIL


# --------------------------------------------------------------- corruption D
def test_tampered_prospective_registry_file_fails_the_freeze_check(clean_env, monkeypatch):
    if clean_env.phase_present and not clean_env.phase_filled:
        pytest.skip("observation_phase table exists but this fixture cannot populate it")
    _freeze_synthetic_entry(clean_env.ledger)

    tampered_dir = clean_env.tmp_path / "prospective-tampered"
    shutil.copytree(clean_env.registry_dir, tampered_dir)
    frozen_files = sorted((tampered_dir / "entries").glob("*.json"))
    assert len(frozen_files) == 1
    frozen_path = frozen_files[0]
    document = json.loads(frozen_path.read_text(encoding="utf-8"))
    document["hypothesis_zh"] = "被人为改写的假设：应被审计发现"
    frozen_path.write_text(
        json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MEDRADAR_PROSPECTIVE_DIR", str(tampered_dir))

    report = audit_module.audit_ledger(clean_env.ledger_path)
    check = _checks_by_id(report)["prospective_freeze_integrity"]
    assert check["verdict"] == audit_module.VERDICT_FAIL
    failures = check["evidence"]["failures"]
    assert failures[0]["entry_id"] == SYNTHETIC_ENTRY_ID
    assert failures[0]["issue"] == "frozen_document_tampered"
    assert failures[0]["stored_sha256"] != failures[0]["recomputed_sha256"]
    assert report["overall"] == audit_module.VERDICT_FAIL


def test_stale_backup_manifest_requires_manual_review_not_false_pass(clean_env):
    """A manifest older than the newest ledger write cannot prove the live state.

    A consistent *prefix* (counts <= live, same first_seen window, same sources) is
    reported as REQUIRES_MANUAL_REVIEW — never PASS, never a false FAIL.  A prefix
    that is impossible (manifest counts larger than the live ledger) is FAIL.
    """
    if clean_env.phase_present and not clean_env.phase_filled:
        pytest.skip("observation_phase table exists but this fixture cannot populate it")
    _freeze_synthetic_entry(clean_env.ledger)  # only the backup check can be "not PASS"
    live_counts = clean_env.ledger.counts()

    def _write(manifest_path, *, created_at, counts):
        _write_default_manifest(
            clean_env.ledger,
            manifest_path,
            overrides={"created_at": created_at, "counts": counts},
        )

    stale_path = clean_env.tmp_path / "stale-bundle" / "MANIFEST.json"
    _write(
        stale_path,
        created_at="2020-01-01T00:00:00+00:00",
        counts={
            "observations": live_counts["observations"] - 1,
            "versions": live_counts["versions"] - 1,
            "changes": live_counts["changes"] - 1,
            "runs": 0,
        },
    )
    report = audit_module.audit_ledger(
        clean_env.ledger_path, backup_manifest_path=stale_path
    )
    check = _checks_by_id(report)["backup_restore_reproducibility"]
    assert check["verdict"] == audit_module.VERDICT_MANUAL, check["detail_zh"]
    assert check["evidence"]["strict_identity_expected"] is False
    assert check["evidence"]["mismatch_total"] >= 1
    assert report["overall"] == audit_module.VERDICT_MANUAL

    impossible_path = clean_env.tmp_path / "impossible-bundle" / "MANIFEST.json"
    _write(
        impossible_path,
        created_at="2020-01-01T00:00:00+00:00",
        counts={
            "observations": live_counts["observations"] + 1,
            "versions": live_counts["versions"],
            "changes": live_counts["changes"],
            "runs": live_counts["runs"],
        },
    )
    report = audit_module.audit_ledger(
        clean_env.ledger_path, backup_manifest_path=impossible_path
    )
    check = _checks_by_id(report)["backup_restore_reproducibility"]
    assert check["verdict"] == audit_module.VERDICT_FAIL
    assert report["overall"] == audit_module.VERDICT_FAIL


# --------------------------------------------------------------- corruption E
def test_backup_manifest_count_mismatch_fails(clean_env):
    if clean_env.phase_present and not clean_env.phase_filled:
        pytest.skip("observation_phase table exists but this fixture cannot populate it")
    _freeze_synthetic_entry(clean_env.ledger)  # so only the backup check can fail
    manifest_path = clean_env.tmp_path / "manifest-mismatch" / "MANIFEST.json"
    live_counts = clean_env.ledger.counts()
    _write_default_manifest(
        clean_env.ledger,
        manifest_path,
        overrides={
            "counts": {
                "observations": live_counts["observations"] + 1,
                "versions": live_counts["versions"],
                "changes": live_counts["changes"],
                "runs": live_counts["runs"],
            }
        },
    )

    report = audit_module.audit_ledger(
        clean_env.ledger_path, backup_manifest_path=manifest_path
    )
    check = _checks_by_id(report)["backup_restore_reproducibility"]
    assert check["verdict"] == audit_module.VERDICT_FAIL
    assert check["evidence"]["strict_identity_expected"] is True
    mismatch_fields = {item["dimension"] for item in check["evidence"]["mismatches"]}
    assert "counts.observations" in mismatch_fields
    mismatch = check["evidence"]["mismatches"][0]
    assert mismatch["manifest"] == live_counts["observations"] + 1
    assert mismatch["live"] == live_counts["observations"]
    assert report["overall"] == audit_module.VERDICT_FAIL


# ------------------------------------------------------------------- rendering
def test_render_report_contains_every_check_and_human_review_section(clean_env):
    report = audit_module.audit_ledger(clean_env.ledger_path)
    text = audit_module.render_report(report)
    markdown = audit_module.render_report(report, style="markdown")

    for document in (text, markdown):
        for check in report["checks"]:
            assert check["title_zh"] in document
            assert check["verdict"] in document
        assert "人工复核" in document
        assert "PASS" in document  # summary, but never as a naked line
        assert "\nPASS\n" not in document
        assert "\nFAIL\n" not in document
    assert "Needs human review" in markdown
    assert "需要人工复核 / Needs human review" in markdown
    assert report["overall"] in markdown
    for check in report["checks"]:
        if check["verdict"] == audit_module.VERDICT_MANUAL:
            assert f"**{check['id']}**" in markdown

    with pytest.raises(ValueError):
        audit_module.render_report(report, style="xml")


# ------------------------------------------------------------------ read-only
def test_audit_is_read_only_and_leaves_the_ledger_byte_identical(tmp_path, monkeypatch):
    ledger_path = tmp_path / "observatory.sqlite"
    monkeypatch.setenv("MEDRADAR_OBSERVATORY_DB", str(ledger_path))
    monkeypatch.setenv("MEDRADAR_PROSPECTIVE_DIR", str(tmp_path / "empty-registry"))

    ledger = ObservationLedger(ledger_path)
    try:
        ledger.ensure_source(
            SOURCE, label_zh="合成测试来源", adapter_version="synthetic/1.0",
            declared_cadence_zh="每 6 小时（合成）",
        )
        ledger.start_run(SOURCE, trigger="test", collector_version=COLLECTOR_VERSION,
                         run_id=RUN_ID)
        ledger.finish_run(RUN_ID, status=RUN_OK, counters={"requests": 1})
        _collect(ledger, "readonly-a", T0)
        _collect(ledger, "readonly-a", T1, revision=2)
        ledger.con.execute(
            "UPDATE source_state SET status='OK', last_attempt_at=?, last_success_at=?,"
            " watermark=?, watermark_updated_at=? WHERE source=?",
            (T1, T1, canonical_json({"cursor": "synthetic-1"}), T1, SOURCE),
        )
        ledger.con.commit()
        _fill_phase_rows(ledger)
    finally:
        ledger.close()

    before = hashlib.sha256(ledger_path.read_bytes()).hexdigest()
    first = audit_module.audit_ledger(ledger_path)
    after = hashlib.sha256(ledger_path.read_bytes()).hexdigest()
    assert before == after, "the audit must not write to the observation ledger"

    second = audit_module.audit_ledger(ledger_path)
    assert [check["verdict"] for check in first["checks"]] == [
        check["verdict"] for check in second["checks"]
    ]
    assert [check["id"] for check in first["checks"]] == [
        check["id"] for check in second["checks"]
    ]


# --------------------------------------------------------------- missing ledger
def test_missing_ledger_reports_fail_honestly(tmp_path, monkeypatch):
    missing = tmp_path / "missing.sqlite"
    report = audit_module.audit_ledger(missing)
    assert report["overall"] == audit_module.VERDICT_FAIL
    assert report["ledger"]["present"] is False
    assert [check["id"] for check in report["checks"]] == ["ledger_readable"]
    assert report["checks"][0]["verdict"] == audit_module.VERDICT_FAIL

    monkeypatch.setenv("MEDRADAR_OBSERVATORY_DB", str(missing))
    exit_code, cli_report = audit_module.run_audit()
    assert exit_code == 1
    assert cli_report["overall"] == audit_module.VERDICT_FAIL
