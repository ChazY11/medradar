"""Synthetic tier — Observatory verified backups, restore drills and retention.

Everything here runs offline against throwaway SQLite files under ``tmp_path`` and
a throwaway prospective-registry directory.  Nothing reads or writes the real
``data/`` directory and nothing touches the network.  These tests prove the
*mechanical* guarantees of design §2: an unverified bundle is never OK, hashes
catch corruption, retention never deletes the newest or an unverifiable bundle,
restore preserves ``first_seen_at`` identity and the restore drill can prove
continuity after a real ledger-level write.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

import pytest

from medradar.observatory.backup import (
    BUNDLE_PREFIX,
    LEDGER_NAME,
    MANIFEST_NAME,
    RAW_CACHE_DIR,
    README_NAME,
    cache_key_for_url,
    create_backup,
    list_backups,
    prune_backups,
    prune_raw_cache,
    sha256_file,
    verify_backup,
)
from medradar.observatory.ledger import ObservationLedger
from medradar.observatory.records import (
    ENTITY_MAPPED,
    ENTITY_PENDING_REVIEW,
    PRECISION_DATE,
    PRECISION_DATETIME,
    MappingResult,
    RawRecord,
)
from medradar.observatory.restore import (
    RESTORE_REPORT_NAME,
    restore_backup,
    run_restore_drill,
    verify_restored,
)


# ----------------------------------------------------------------------- fixtures
@pytest.fixture(autouse=True)
def isolated_environment(tmp_path, monkeypatch):
    """Keep the real data/ tree out of every test."""
    registry = tmp_path / "prospective_env"
    monkeypatch.setenv("MEDRADAR_PROSPECTIVE_DIR", str(registry))
    monkeypatch.setenv("MEDRADAR_OBSERVATORY_DB", str(tmp_path / "default_ledger.sqlite"))
    return registry


def _mapping(entity_id: str = "medtronic") -> MappingResult:
    return MappingResult(
        entity_id=entity_id,
        entity_status=ENTITY_MAPPED,
        entity_method="test_exact",
        entity_confidence=1.0,
        track_id="cardiac_rhythm",
        track_status="MAPPED",
        track_method="test_keyword",
    )


def _record(
    record_id: str,
    *,
    source: str = "sec_edgar",
    title: str | None = None,
    payload: dict | None = None,
    url: str | None = None,
    event_at: str = "2026-10-01",
) -> RawRecord:
    title = title or f"合成记录 {record_id}"
    return RawRecord(
        source=source,
        source_record_id=record_id,
        record_type="synthetic_record",
        title=title,
        url=url if url is not None else f"https://example.invalid/records/{record_id}",
        event_at=event_at,
        event_at_precision=PRECISION_DATE,
        published_at="2026-10-02T21:18:02+00:00",
        published_at_precision=PRECISION_DATETIME,
        payload=payload if payload is not None else {"status": "active", "title": title},
        company_hint="Medtronic",
    )


def write_prospective(registry: Path) -> list[Path]:
    """A prospective-like frozen registry directory (copied read-only by backup)."""
    entries = registry / "entries"
    entries.mkdir(parents=True, exist_ok=True)
    frozen = entries / "synthetic-entry.json"
    frozen.write_text(
        json.dumps(
            {
                "schema": "medradar-prospective-entry-1",
                "entry_id": "synthetic-entry",
                "synthetic": True,
                "label_zh": "合成测试条目",
                "freeze_at": "2026-11-01T00:00:00Z",
                "content_sha256": "0" * 64,
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    appendix = entries / "synthetic-entry.evaluation.1.json"
    appendix.write_text(
        json.dumps(
            {"schema": "medradar-prospective-evaluation-1", "entry_id": "synthetic-entry"},
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return [frozen, appendix]


def build_ledger(tmp_path: Path) -> dict:
    """A throwaway ledger with multi-version records and append-only mapping history."""
    obs_dir = tmp_path / "observatory"
    obs_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = obs_dir / "observatory.sqlite"
    ledger = ObservationLedger(ledger_path)
    for source in ("sec_edgar", "ctgov", "europepmc"):
        ledger.ensure_source(
            source,
            label_zh=f"{source} 合成来源",
            adapter_version="synthetic/1.0",
            declared_cadence_zh="每 6 小时轮询（合成）",
        )
    run_sec = ledger.start_run("sec_edgar", trigger="synthetic", collector_version="synthetic/1.0")
    run_ctgov = ledger.start_run("ctgov", trigger="synthetic", collector_version="synthetic/1.0")
    run_epmc = ledger.start_run("europepmc", trigger="synthetic", collector_version="synthetic/1.0")

    urls = {
        "rec-1": "https://example.invalid/api/sec/rec-1",
        "rec-2": "https://example.invalid/api/ctgov/rec-2",
        "rec-3": "https://example.invalid/api/epmc/rec-3",
    }
    common = dict(collector_version="synthetic/1.0", mapping_version="obs-mapping-v1")

    # rec-1: two payload versions, first_seen_at must stay the first value.
    ledger.record_observation(
        _record(
            "rec-1",
            title="原始标题",
            payload={"status": "recruiting", "enrollment": 100},
            url=urls["rec-1"],
        ),
        _mapping(),
        run_id=run_sec,
        seen_at="2026-01-10T10:00:00+00:00",
        **common,
    )
    ledger.record_observation(
        _record(
            "rec-1",
            title="修订标题",
            payload={"status": "completed", "enrollment": 100},
            url=urls["rec-1"],
        ),
        _mapping(),
        run_id=run_sec,
        seen_at="2026-01-11T10:00:00+00:00",
        **common,
    )

    # rec-2: mapping history (PENDING_REVIEW → MAPPED), payload unchanged.
    ledger.record_observation(
        _record("rec-2", source="ctgov", url=urls["rec-2"]),
        MappingResult(
            entity_id="medtronic",
            entity_status=ENTITY_PENDING_REVIEW,
            entity_method="name_fuzzy",
            entity_confidence=0.7,
        ),
        run_id=run_ctgov,
        seen_at="2026-01-10T11:00:00+00:00",
        **common,
    )
    ledger.record_observation(
        _record("rec-2", source="ctgov", url=urls["rec-2"]),
        _mapping(),
        run_id=run_ctgov,
        seen_at="2026-01-11T11:00:00+00:00",
        **common,
    )

    # rec-3: another source, then rec-4 is explicitly removed (status history).
    ledger.record_observation(
        _record("rec-3", source="europepmc", url=urls["rec-3"]),
        _mapping("philips"),
        run_id=run_epmc,
        seen_at="2026-01-10T12:00:00+00:00",
        **common,
    )
    rec4 = _record("rec-4", source="ctgov", url=None)
    ledger.record_observation(
        rec4,
        _mapping(),
        run_id=run_ctgov,
        seen_at="2026-01-10T12:30:00+00:00",
        **common,
    )
    ledger.mark_removed(
        rec4.observation_id,
        run_id=run_ctgov,
        note_zh="合成测试：来源不再提供",
        seen_at="2026-01-11T12:30:00+00:00",
    )

    ledger.set_watermark("sec_edgar", {"cursor": 42, "known_ids": ["rec-1"]})
    ledger.set_watermark("ctgov", {"cursor": 7, "known_ids": ["rec-2", "rec-4"]})
    ledger.set_watermark("europepmc", {"cursor": "2026-11-03", "known_ids": ["rec-3"]})
    for run_id, source in ((run_sec, "sec_edgar"), (run_ctgov, "ctgov"), (run_epmc, "europepmc")):
        ledger.note_source_success(source, run_id=run_id, message="synthetic ok")
        ledger.finish_run(
            run_id,
            status="OK",
            counters={"requests": 1, "pages": 1, "records_seen": 2, "records_new": 2},
        )

    cache_dir = obs_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{cache_key_for_url(urls['rec-1'])}.json").write_text(
        '{"synthetic": true}', encoding="utf-8"
    )
    return {
        "obs_dir": obs_dir,
        "ledger_path": ledger_path,
        "ledger": ledger,
        "urls": urls,
    }


# -------------------------------------------------------------------- backup bundle
def test_create_backup_writes_verified_bundle_and_records_runtime_state(
    tmp_path, isolated_environment
):
    built = build_ledger(tmp_path)
    ledger = built["ledger"]
    write_prospective(isolated_environment)
    destination = tmp_path / "backups"

    result = create_backup(
        ledger_path=built["ledger_path"],
        dest_dir=destination,
        include_raw_cache=True,
        include_prospective=True,
        label="unit",
    )

    assert result["status"] == "OK", result["error"]
    assert result["ok"] is True and result["verified"] is True
    bundle = Path(result["path"])
    assert bundle.parent == destination
    assert bundle.name.startswith(f"{BUNDLE_PREFIX}2026") or bundle.name.startswith(
        BUNDLE_PREFIX
    )
    assert bundle.name.endswith("-unit")
    for name in (LEDGER_NAME, MANIFEST_NAME, README_NAME):
        assert (bundle / name).is_file(), name
    assert (bundle / RAW_CACHE_DIR).is_dir()
    assert (bundle / "prospective" / "entries" / "synthetic-entry.json").is_file()
    # the snapshot is a single-file, WAL-sidecar-free database
    assert not Path(str(bundle / LEDGER_NAME) + "-wal").exists()
    assert not Path(str(bundle / LEDGER_NAME) + "-shm").exists()

    manifest = json.loads((bundle / MANIFEST_NAME).read_text(encoding="utf-8"))
    counts = ledger.counts()
    first_seen = ledger.con.execute(
        "SELECT MIN(first_seen_at), MAX(first_seen_at) FROM observation"
    ).fetchone()
    assert manifest["schema"].startswith("medradar-observatory-backup")
    assert manifest["counts"]["observations"] == counts["observations"]
    assert manifest["counts"]["versions"] == counts["versions"]
    assert manifest["counts"]["changes"] == counts["changes"]
    assert manifest["first_seen"]["min"] == first_seen[0]
    assert manifest["first_seen"]["max"] == first_seen[1]
    assert manifest["per_source_observation_counts"] == {"ctgov": 2, "europepmc": 1, "sec_edgar": 1}
    assert set(manifest["source_watermarks"]) == {"sec_edgar", "ctgov", "europepmc"}
    assert manifest["ledger"]["integrity_check"] == "ok"
    assert manifest["ledger"]["consistency_ok"] is True
    assert manifest["ledger"]["schema_version"] == "obs-ledger-v1"
    assert manifest["raw_cache"]["included"] is True
    assert manifest["prospective"]["included"] is True
    assert manifest["prospective"]["entries"] == 1
    assert manifest["tool"]["name"] == "medradar-observatory-backup"
    assert manifest["tool"]["version"]
    # every manifest artifact hash is re-derivable
    assert manifest["artifacts"]
    for artifact in manifest["artifacts"]:
        artifact_path = bundle / artifact["path"]
        assert artifact_path.stat().st_size == artifact["bytes"]
        assert sha256_file(artifact_path) == artifact["sha256"]

    verification = verify_backup(bundle)
    assert verification["ok"] is True and verification["status"] == "OK"
    assert verification["problems"] == []
    assert verification["counts"]["observations"] == counts["observations"]

    # the operational record is in the real ledger and matches §2
    assert result["runtime_state_recorded"] is True
    record = ledger.get_runtime("last_backup", {})
    assert record["status"] == "OK"
    assert record["verified"] is True
    assert record["bundle"] == bundle.name
    assert record["sha256_manifest"] == sha256_file(bundle / MANIFEST_NAME)
    assert record["counts"]["observations"] == counts["observations"]
    assert record["counts"]["versions"] == counts["versions"]
    assert record["counts"]["changes"] == counts["changes"]
    assert record["integrity_check"] == "ok"
    assert record["consistency_ok"] is True
    assert record["cache_included"] is True
    assert record["retention"]["kept"] >= 1

    # bytes reported by the bundle match its artifacts
    total = sum(item["bytes"] for item in manifest["artifacts"])
    assert result["bytes"] == total
    assert result["ledger_bytes"] == manifest["ledger"]["bytes"]
    ledger.close()


def test_manifest_hashes_detect_corrupted_or_missing_artifacts(tmp_path):
    built = build_ledger(tmp_path)
    result = create_backup(
        ledger_path=built["ledger_path"],
        dest_dir=tmp_path / "backups",
        include_raw_cache=False,
        include_prospective=False,
    )
    assert result["status"] == "OK"
    bundle = Path(result["path"])

    # flip one byte of the copied ledger: the hash must catch it
    ledger_copy = bundle / LEDGER_NAME
    data = bytearray(ledger_copy.read_bytes())
    data[len(data) // 2] ^= 0xFF
    ledger_copy.write_bytes(bytes(data))
    verification = verify_backup(bundle)
    assert verification["ok"] is False
    assert verification["status"] == "FAILED"
    assert any("sha256 mismatch" in problem for problem in verification["problems"])

    # a tampered README is also a failure (not a "cosmetic" artifact)
    data = bytearray((bundle / README_NAME).read_bytes())
    data[0] ^= 0x01
    (bundle / README_NAME).write_bytes(bytes(data))
    assert verify_backup(bundle)["ok"] is False

    # a missing artifact is a failure
    (bundle / README_NAME).unlink()
    missing = verify_backup(bundle)
    assert missing["ok"] is False
    assert any("missing" in problem for problem in missing["problems"])

    # no manifest at all can never be reported OK (it is UNVERIFIED)
    (bundle / MANIFEST_NAME).unlink()
    unverified = verify_backup(bundle)
    assert unverified["ok"] is False
    assert unverified["status"] == "UNVERIFIED"
    built["ledger"].close()


def test_create_backup_reports_failure_instead_of_raising(tmp_path):
    missing = tmp_path / "does-not-exist.sqlite"
    result = create_backup(ledger_path=missing, dest_dir=tmp_path / "backups")
    assert result["status"] == "FAILED"
    assert result["ok"] is False
    assert result["verified"] is False
    assert "not found" in (result["error"] or "")
    assert not (tmp_path / "backups").exists() or not any(
        (tmp_path / "backups").iterdir()
    )


# ---------------------------------------------------------------- retention / prune
def _copy_ledger(source: Path, destination: Path) -> None:
    source_connection = sqlite3.connect(
        f"file:{source.as_posix()}?mode=ro", uri=True, timeout=30.0
    )
    destination_connection = sqlite3.connect(str(destination))
    try:
        source_connection.backup(destination_connection)
        destination_connection.execute("PRAGMA journal_mode=DELETE")
    finally:
        destination_connection.close()
        source_connection.close()


def _make_bundle(destination: Path, stamp: str, created_at: str, ledger_path: Path) -> Path:
    """A structurally valid bundle with a controlled created_at (retention tests)."""
    bundle = destination / f"{BUNDLE_PREFIX}{stamp}"
    bundle.mkdir(parents=True, exist_ok=True)
    _copy_ledger(ledger_path, bundle / LEDGER_NAME)
    (bundle / README_NAME).write_text("synthetic retention bundle\n", encoding="utf-8")
    artifacts = [
        {
            "path": relative,
            "role": "test",
            "bytes": (bundle / relative).stat().st_size,
            "sha256": sha256_file(bundle / relative),
        }
        for relative in (LEDGER_NAME, README_NAME)
    ]
    manifest = {
        "schema": "medradar-observatory-backup-1",
        "name": bundle.name,
        "created_at": created_at,
        "counts": {"observations": 0},
        "first_seen": {"min": None, "max": None},
        "per_source_observation_counts": {},
        "source_watermarks": {},
        "version_chain": {},
        "ledger": {"schema_version": "obs-ledger-v1"},
        "artifacts": artifacts,
    }
    (bundle / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return bundle


def test_prune_backups_applies_daily_weekly_monthly_labels(tmp_path):
    built = build_ledger(tmp_path)
    destination = tmp_path / "retention"
    destination.mkdir()
    names = {}
    for stamp, created_at in (
        ("20260105T100000Z", "2026-01-05T10:00:00Z"),
        ("20260106T100000Z", "2026-01-06T10:00:00Z"),
        ("20260210T100000Z", "2026-02-10T10:00:00Z"),
        ("20260315T100000Z", "2026-03-15T10:00:00Z"),
    ):
        names[stamp] = _make_bundle(destination, stamp, created_at, built["ledger_path"]).name

    newest = names["20260315T100000Z"]
    dry_run = prune_backups(destination, daily=1, weekly=1, monthly=1, dry_run=True)
    assert dry_run["ok"] is True
    assert sorted(dry_run["pruned"]) == sorted(
        names[stamp] for stamp in ("20260105T100000Z", "20260106T100000Z", "20260210T100000Z")
    )
    assert len(dry_run["kept"]) == 1 and dry_run["kept"][0] == newest
    for stamp in names:
        assert (destination / names[stamp]).is_dir()  # dry run deletes nothing

    real = prune_backups(destination, daily=1, weekly=1, monthly=1, dry_run=False)
    assert real["ok"] is True
    assert real["kept"] == [newest]
    assert (destination / newest).is_dir()
    for stamp in ("20260105T100000Z", "20260106T100000Z", "20260210T100000Z"):
        assert not (destination / names[stamp]).exists()
    assert real["quarantined"] == []
    # listing is newest-first
    listed = list_backups(destination)
    assert listed[0]["name"] == newest
    built["ledger"].close()


def test_prune_backups_weekly_and_monthly_keep_newest_per_label(tmp_path):
    built = build_ledger(tmp_path)
    destination = tmp_path / "retention_weeks"
    destination.mkdir()
    names = {}
    for stamp, created_at in (
        ("20260105T100000Z", "2026-01-05T10:00:00Z"),  # ISO week 2
        ("20260108T100000Z", "2026-01-08T10:00:00Z"),  # ISO week 2 (newest of that week)
        ("20260112T100000Z", "2026-01-12T10:00:00Z"),  # ISO week 3
        ("20260202T100000Z", "2026-02-02T10:00:00Z"),  # ISO week 6, newest overall
    ):
        names[stamp] = _make_bundle(destination, stamp, created_at, built["ledger_path"]).name

    result = prune_backups(destination, daily=0, weekly=2, monthly=1)
    assert result["ok"] is True
    # newest per week for the two most recent weeks (6, 3) + newest per month (Feb)
    assert sorted(result["kept"]) == sorted(
        [names["20260202T100000Z"], names["20260112T100000Z"]]
    )
    assert sorted(result["pruned"]) == sorted(
        [names["20260105T100000Z"], names["20260108T100000Z"]]
    )
    assert (destination / names["20260202T100000Z"]).is_dir()
    built["ledger"].close()


def test_prune_backups_never_deletes_newest_and_quarantines_unverifiable(tmp_path):
    built = build_ledger(tmp_path)
    destination = tmp_path / "retention_protect"
    destination.mkdir()
    names = []
    for stamp, created_at in (
        ("20260101T100000Z", "2026-01-01T10:00:00Z"),
        ("20260102T100000Z", "2026-01-02T10:00:00Z"),
        ("20260103T100000Z", "2026-01-03T10:00:00Z"),
    ):
        names.append(_make_bundle(destination, stamp, created_at, built["ledger_path"]).name)
    newest = names[-1]

    # missing manifest -> quarantine, never delete (older than the newest valid bundle)
    missing = _make_bundle(
        destination, "20251230T100000Z", "2025-12-30T10:00:00Z", built["ledger_path"]
    )
    (missing / MANIFEST_NAME).unlink()
    # corrupt manifest -> quarantine, never delete
    corrupt = _make_bundle(
        destination, "20251231T100000Z", "2025-12-31T10:00:00Z", built["ledger_path"]
    )
    (corrupt / MANIFEST_NAME).write_text("{ this is not json", encoding="utf-8")

    dry_run = prune_backups(destination, daily=7, weekly=4, monthly=6, dry_run=True)
    assert {item["name"] for item in dry_run["quarantined"]} == {missing.name, corrupt.name}
    assert missing.is_dir() and corrupt.is_dir()

    result = prune_backups(destination, daily=7, weekly=4, monthly=6)
    assert result["ok"] is True
    assert {item["name"] for item in result["quarantined"]} == {missing.name, corrupt.name}
    quarantine = destination / "quarantine"
    assert (quarantine / missing.name).is_dir()
    assert (quarantine / corrupt.name).is_dir()
    assert not missing.exists() and not corrupt.exists()
    # the newest bundle is never removed
    assert (destination / newest).is_dir()
    assert newest in result["kept"]
    built["ledger"].close()


def test_prune_backups_with_zero_policy_keeps_only_newest(tmp_path):
    built = build_ledger(tmp_path)
    destination = tmp_path / "retention_zero"
    destination.mkdir()
    names = []
    for stamp, created_at in (
        ("20260101T100000Z", "2026-01-01T10:00:00Z"),
        ("20260102T100000Z", "2026-01-02T10:00:00Z"),
        ("20260103T100000Z", "2026-01-03T10:00:00Z"),
    ):
        names.append(_make_bundle(destination, stamp, created_at, built["ledger_path"]).name)
    result = prune_backups(destination, daily=0, weekly=0, monthly=0)
    assert result["ok"] is True
    assert result["kept"] == [names[-1]]
    assert len(result["pruned"]) == 2
    assert (destination / names[-1]).is_dir()
    built["ledger"].close()


# ------------------------------------------------------------------- raw cache prune
def test_prune_raw_cache_only_removes_old_ledger_confirmed_files(tmp_path):
    built = build_ledger(tmp_path)
    ledger = built["ledger"]
    cache = built["obs_dir"] / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    old = time.time() - 200 * 86400
    recent = time.time()

    confirmed_old = cache / f"{cache_key_for_url(built['urls']['rec-1'])}.json"
    confirmed_old.write_text('{"cached": "old"}', encoding="utf-8")
    os.utime(confirmed_old, (old, old))
    confirmed_old_text = cache / f"{cache_key_for_url(built['urls']['rec-2'])}.txt"
    confirmed_old_text.write_text("cached text", encoding="utf-8")
    os.utime(confirmed_old_text, (old, old))
    confirmed_recent = cache / f"{cache_key_for_url(built['urls']['rec-3'])}.json"
    confirmed_recent.write_text('{"cached": "recent"}', encoding="utf-8")
    os.utime(confirmed_recent, (recent, recent))
    unconfirmed_old = cache / f"{'a' * 24}.json"
    unconfirmed_old.write_text('{"unknown": true}', encoding="utf-8")
    os.utime(unconfirmed_old, (old, old))

    protected = {
        "observatory.sqlite": "not a cache entry",
        "MANIFEST.json": "{}",
        "backup.zip": "zip",
    }
    for name, text in protected.items():
        path = cache / name
        path.write_text(text, encoding="utf-8")
        os.utime(path, (old, old))
    protected_dir = cache / "raw-cache-backup"
    protected_dir.mkdir()
    (protected_dir / "nested.json").write_text("{}", encoding="utf-8")

    dry_run = prune_raw_cache(cache, ledger, retention_days=180, dry_run=True)
    assert dry_run["ok"] is True
    assert dry_run["deleted_count"] == 2
    assert confirmed_old.is_file() and confirmed_old_text.is_file()

    result = prune_raw_cache(cache, ledger, retention_days=180)
    assert result["ok"] is True, result["problems"]
    assert sorted(result["deleted"]) == sorted([confirmed_old.name, confirmed_old_text.name])
    assert not confirmed_old.exists()
    assert not confirmed_old_text.exists()
    # recent / unconfirmed / protected files survive
    assert confirmed_recent.is_file()
    assert unconfirmed_old.is_file()
    for name in protected:
        assert (cache / name).is_file(), name
    assert (protected_dir / "nested.json").is_file()
    assert result["deleted_bytes"] > 0
    # the ledger itself is untouched
    assert ledger.counts()["observations"] > 0
    ledger.close()


# --------------------------------------------------------------------- restore tests
def test_restore_refuses_a_tampered_bundle(tmp_path):
    built = build_ledger(tmp_path)
    result = create_backup(
        ledger_path=built["ledger_path"],
        dest_dir=tmp_path / "backups",
        include_raw_cache=False,
        include_prospective=False,
    )
    assert result["status"] == "OK"
    bundle = Path(result["path"])
    target = tmp_path / "restored"

    data = bytearray((bundle / LEDGER_NAME).read_bytes())
    data[len(data) // 2] ^= 0xFF
    (bundle / LEDGER_NAME).write_bytes(bytes(data))

    refused = restore_backup(bundle, target)
    assert refused["ok"] is False
    assert refused["status"] == "REFUSED"
    assert refused["problems"]
    assert not (target / "observatory.sqlite").exists()
    assert not (target / RESTORE_REPORT_NAME).exists()
    built["ledger"].close()


def test_restore_refuses_non_empty_target_without_overwrite(tmp_path):
    built = build_ledger(tmp_path)
    result = create_backup(
        ledger_path=built["ledger_path"],
        dest_dir=tmp_path / "backups",
        include_raw_cache=False,
        include_prospective=False,
    )
    bundle = Path(result["path"])
    target = tmp_path / "occupied"
    target.mkdir()
    (target / "keep-me.txt").write_text("do not clobber", encoding="utf-8")

    refused = restore_backup(bundle, target)
    assert refused["ok"] is False and refused["status"] == "REFUSED"
    assert (target / "keep-me.txt").read_text(encoding="utf-8") == "do not clobber"
    assert not (target / "observatory.sqlite").exists()
    built["ledger"].close()


def test_restore_preserves_counts_first_seen_version_chain_and_watermarks(
    tmp_path, isolated_environment
):
    built = build_ledger(tmp_path)
    ledger = built["ledger"]
    write_prospective(isolated_environment)
    original_counts = ledger.counts()
    original_rows = {
        row["observation_id"]: row["first_seen_at"]
        for row in ledger.con.execute("SELECT observation_id, first_seen_at FROM observation")
    }
    original_versions = {
        observation_id: [
            (version["version_seq"], version["payload_hash"], version["captured_at"])
            for version in ledger.versions(observation_id)
        ]
        for observation_id in original_rows
    }
    original_watermarks = {
        row["source"]: (row["watermark"], row["watermark_updated_at"])
        for row in ledger.con.execute(
            "SELECT source, watermark, watermark_updated_at FROM source_state"
        )
    }
    original_mapping_history = {
        observation_id: len(ledger.mapping_history(observation_id))
        for observation_id in original_rows
    }

    result = create_backup(
        ledger_path=built["ledger_path"],
        dest_dir=tmp_path / "backups",
        include_raw_cache=True,
        include_prospective=True,
    )
    assert result["status"] == "OK"
    bundle = Path(result["path"])
    manifest = json.loads((bundle / MANIFEST_NAME).read_text(encoding="utf-8"))

    target = tmp_path / "restored"
    restore = restore_backup(bundle, target)
    assert restore["status"] == "OK", restore["problems"]
    assert restore["ok"] is True
    restored_path = Path(restore["ledger"])
    assert restored_path == target / "observatory.sqlite"
    assert (target / RESTORE_REPORT_NAME).is_file()
    assert (target / "cache").is_dir()
    assert (target / "prospective" / "entries" / "synthetic-entry.json").is_file()

    report = json.loads((target / RESTORE_REPORT_NAME).read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["manifest_verified_before_restore"] is True
    assert report["policy"]["first_seen_at"].startswith("copied from the backup")

    restored_verification = verify_restored(restored_path, manifest)
    assert restored_verification["ok"] is True, restored_verification["problems"]
    assert all(check["ok"] for check in restored_verification["checks"])
    assert restore["restored_verification"]["ok"] is True

    restored = ObservationLedger(restored_path, read_only=True)
    try:
        counts = restored.counts()
        for key in ("observations", "versions", "changes", "runs", "failures", "sources"):
            assert counts[key] == original_counts[key], key
        assert counts["schema_version"] == original_counts["schema_version"]
        rows = {
            row["observation_id"]: row["first_seen_at"]
            for row in restored.con.execute(
                "SELECT observation_id, first_seen_at FROM observation"
            )
        }
        assert rows == original_rows
        for observation_id, expected in original_versions.items():
            actual = [
                (version["version_seq"], version["payload_hash"], version["captured_at"])
                for version in restored.versions(observation_id)
            ]
            assert actual == expected
        watermarks = {
            row["source"]: (row["watermark"], row["watermark_updated_at"])
            for row in restored.con.execute(
                "SELECT source, watermark, watermark_updated_at FROM source_state"
            )
        }
        assert watermarks == original_watermarks
        for observation_id, expected_count in original_mapping_history.items():
            assert len(restored.mapping_history(observation_id)) == expected_count
        assert restored.consistency_check()["ok"] is True
    finally:
        restored.close()
    ledger.close()


def test_restore_overwrite_preserves_the_previous_ledger(tmp_path):
    built = build_ledger(tmp_path)
    result = create_backup(
        ledger_path=built["ledger_path"],
        dest_dir=tmp_path / "backups",
        include_raw_cache=False,
        include_prospective=False,
    )
    bundle = Path(result["path"])
    target = tmp_path / "restored_over"
    target.mkdir()
    previous = target / "observatory.sqlite"
    previous.write_text("previous ledger placeholder", encoding="utf-8")

    restore = restore_backup(bundle, target, overwrite=True)
    assert restore["status"] == "OK", restore["problems"]
    assert restore["preserved_previous_ledger"]
    assert Path(restore["preserved_previous_ledger"]).read_text(
        encoding="utf-8"
    ) == "previous ledger placeholder"
    assert (target / "observatory.sqlite").is_file()
    built["ledger"].close()


# ----------------------------------------------------------------------- drill test
def test_restore_drill_proves_first_seen_continuity(tmp_path, isolated_environment):
    built = build_ledger(tmp_path)
    ledger = built["ledger"]
    write_prospective(isolated_environment)
    before_counts = ledger.counts()
    before_rows = {
        row["observation_id"]: row["first_seen_at"]
        for row in ledger.con.execute("SELECT observation_id, first_seen_at FROM observation")
    }
    ledger.close()

    report = run_restore_drill(
        ledger_path=built["ledger_path"],
        work_dir=tmp_path / "drill_work",
        include_raw_cache=True,
    )
    assert report["status"] == "OK", report["error"]
    assert report["ok"] is True
    assert report["bundle"]
    assert report["bundle_path"]
    assert report["restored_ledger"]
    assert report["synthetic_observation_id"]
    assert report["synthetic_first_seen_at"]
    assert report["first_seen_max"] == max(before_rows.values())
    assert report["counts"]["observations"] == before_counts["observations"]
    assert report["counts"]["versions"] == before_counts["versions"]
    assert report["counts"]["changes"] == before_counts["changes"]
    assert report["runtime_state_recorded"] is True
    assert report["runtime_state_error"] is None

    checks = {item["id"]: item for item in report["checks"]}
    for check_id in (
        "original_ledger_read",
        "backup_created",
        "backup_verified",
        "restore_completed",
        "restored_verified",
        "first_seen_identity",
        "restored_consistency",
        "continuity_new_row_fresh",
        "continuity_old_rows_unchanged",
        "continuity_version_chain",
        "post_write_consistency",
    ):
        assert checks[check_id]["ok"] is True, checks[check_id]
    assert Path(report["restored_ledger"]).is_file()
    assert Path(report["restore_report"]).is_file()

    # the synthetic write got a genuinely fresh first_seen_at; old rows kept theirs
    restored = ObservationLedger(report["restored_ledger"], read_only=True)
    try:
        after_rows = {
            row["observation_id"]: row["first_seen_at"]
            for row in restored.con.execute(
                "SELECT observation_id, first_seen_at FROM observation"
            )
        }
        for observation_id, first_seen in before_rows.items():
            assert after_rows[observation_id] == first_seen
        new_row = restored.observation_row(report["synthetic_observation_id"])
        assert new_row is not None
        assert new_row["source"] == "drill_continuity"
        assert new_row["first_seen_at"] == report["synthetic_first_seen_at"]
        assert new_row["first_seen_at"] > max(before_rows.values())
        assert new_row["first_seen_at"] >= report["at"]
        assert len(restored.versions(report["synthetic_observation_id"])) == 1
    finally:
        restored.close()

    # the drill recorded its outcome in the REAL ledger's runtime_state
    ledger_ro = ObservationLedger(built["ledger_path"], read_only=True)
    try:
        state = ledger_ro.get_runtime("last_restore_drill")
        assert isinstance(state, dict)
        assert state["status"] == "OK"
        assert state["ok"] is True
        assert state["bundle"]
        assert state["checks"]
        assert state["first_seen_max"] == max(before_rows.values())
        assert state["counts"]["observations"] == before_counts["observations"]
        assert state["error"] is None
        # the drill did not change production data
        after = ledger_ro.counts()
        for key in ("observations", "versions", "changes", "runs", "failures", "sources"):
            assert after[key] == before_counts[key], key
    finally:
        ledger_ro.close()


def test_restore_drill_reports_missing_ledger_without_raising(tmp_path):
    report = run_restore_drill(
        ledger_path=tmp_path / "missing.sqlite",
        work_dir=tmp_path / "drill_missing",
    )
    assert report["status"] == "FAILED"
    assert report["ok"] is False
    assert "not found" in (report["error"] or "")
    assert report["runtime_state_recorded"] is False
