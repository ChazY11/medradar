"""Backup and restore drill: the ledger is recoverable, the graph is rebuildable.

A backup that only copies bytes is not a recovery test. These tests copy a live ledger through
SQLite's online backup API, verify the copy's own integrity and counts, then restore it into an
isolated directory and rebuild the technology graph from it.
"""

from __future__ import annotations

import sqlite3

from pathlib import Path

import unittest

try:  # the repository's `medradar selftest` runs under unittest without pytest installed
    import pytest
except ModuleNotFoundError:  # pragma: no cover
    raise unittest.SkipTest("pytest is not installed; run these tests with pytest")

from medradar.radar.backup import backup, restore_check
from medradar.radar.classify import RuleMapper
from medradar.radar.ledger import ObservationLedger
from medradar.radar.paths import radar_paths
from medradar.radar.records import MAPPING_VERSION, RawRecord
from medradar.radar.taxonomy import load_taxonomy

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "radar"


def _seed(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    ledger = ObservationLedger(root / "radar.db")
    ledger.ensure_source("pubmed", label="PubMed", adapter_version="a1", cadence_hours=6)
    taxonomy = load_taxonomy(str(CONFIG_DIR))
    for index in range(3):
        title = "SpO2 oximetry and alarm fatigue in intensive care monitoring"
        record = RawRecord(
            source="pubmed", source_record_id=f"pmid:{index}", official_identifier=f"PMID:{index}",
            record_type="publication", title=title,
            url=f"https://pubmed.ncbi.nlm.nih.gov/{index}/",
            published_at="2026-02-01", published_at_precision="date",
            payload={"pmid": str(index), "title": title,
                     "abstract": title, "doi": f"10.1000/test.{index}"},
            text=title, extra={"affiliations": [], "doi": f"10.1000/test.{index}"},
        )
        ledger.record_observation(record, RuleMapper(taxonomy).map(record), run_id="r",
                                  adapter_version="a1", mapping_version=MAPPING_VERSION)
    ledger.close()
    return root


def test_a_backup_is_consistent_and_verified(tmp_path: Path):
    root = _seed(tmp_path)
    paths = radar_paths(root)
    result = backup(paths, destination=tmp_path / "backups", keep=2, log=lambda _m: None)
    manifest = result.manifest
    assert result.destination.is_file()
    assert manifest["verified"] is True
    assert manifest["integrity_check"] == "ok"
    assert manifest["counts"]["observation"] == 3
    assert manifest["counts"]["observation_version"] == 3
    assert manifest["graph_included"] is False
    assert len(manifest["backup_sha256"]) == 64


def test_rotation_keeps_the_newest_copies(tmp_path: Path):
    root = _seed(tmp_path)
    paths = radar_paths(root)
    for _ in range(3):
        backup(paths, destination=tmp_path / "backups", keep=2, log=lambda _m: None)
    remaining = sorted((tmp_path / "backups").glob("radar-*.db"))
    assert len(remaining) == 2


def test_rebuild_graph_rebuilds_everything_not_only_what_the_old_graph_lacked(tmp_path: Path):
    """The graph is a projection: a rebuild must reproduce it from the ledger alone.

    The first attempt returned 0 nodes because the ledger still recorded every observation as
    materialised in the *old* graph. A rebuild has to ignore that work state.
    """
    from medradar.radar import cli
    from medradar.radar.graph import open_graph
    from medradar.radar.taxonomy import load_taxonomy

    root = _seed(tmp_path)
    taxonomy = load_taxonomy(str(CONFIG_DIR))
    graph = open_graph(root / "graph.db", taxonomy)
    ledger = ObservationLedger(root / "radar.db", create=False)
    try:
        graph.materialize(ledger, limit=50, log=lambda _m: None)
        before = graph.summary()["nodes"]
    finally:
        graph.store.close()
        ledger.close()
    assert before > 0

    exit_code = cli.main(["--data-dir", str(root), "rebuild-graph", "--limit", "50"])
    assert exit_code == 0

    rebuilt = open_graph(root / "graph.db", taxonomy)
    try:
        after = rebuilt.summary()
    finally:
        rebuilt.store.close()
    assert after["nodes"] == before
    assert after["edges"] > 0


def test_a_restore_drill_rebuilds_a_graph_even_when_the_backup_thinks_it_is_current(tmp_path: Path):
    """Production drill: the backup carries graph_materialization rows from the live graph.

    The first version materialised nothing (0 nodes) yet reported ok, because those rows said
    every observation was already materialised. The drill must clear that work state in the
    isolated copy and require a non-empty graph before calling itself successful.
    """
    from medradar.radar.graph import open_graph
    from medradar.radar.taxonomy import load_taxonomy

    root = _seed(tmp_path)
    taxonomy = load_taxonomy(str(CONFIG_DIR))
    graph = open_graph(root / "graph.db", taxonomy)
    ledger = ObservationLedger(root / "radar.db", create=False)
    try:
        graph.materialize(ledger, limit=50, log=lambda _m: None)
    finally:
        graph.store.close()
        ledger.close()

    result = backup(radar_paths(root), destination=tmp_path / "backups", keep=2,
                    log=lambda _m: None)
    report = restore_check(backup_path=result.destination, work_dir=tmp_path / "restored",
                           log=lambda _m: None)
    assert report["ok"] is True
    assert report["graph"]["nodes"] > 0
    assert report["graph"]["edges"] > 0


def test_a_restore_drill_proves_the_graph_can_be_rebuilt_from_the_backup(tmp_path: Path):
    root = _seed(tmp_path)
    result = backup(radar_paths(root), destination=tmp_path / "backups", keep=2,
                    log=lambda _m: None)
    report = restore_check(backup_path=result.destination, work_dir=tmp_path / "restored",
                           log=lambda _m: None)
    assert report["ok"] is True
    assert report["integrity_check"] == "ok"
    assert report["counts"]["observations"] == 3
    assert report["graph"]["rebuilt"] is True
    assert report["graph"]["errors"] == []
    assert report["graph"]["nodes"] > 0
    # The untouched original still exists; the drill wrote only into the isolated directory.
    assert (root / "radar.db").is_file()

def test_a_backup_carries_the_human_store_because_it_is_not_derivable(tmp_path: Path):
    """A watchlist and a review note exist nowhere else; a backup that omits them loses them.

    The ledger can be rebuilt from sources, the graph from the ledger, but a person's decision
    cannot be recomputed. So the same backup window must capture human.db too.
    """
    from medradar.radar.backup import backup
    from medradar.radar.human import HumanStore
    from medradar.radar.paths import radar_paths

    radar_dir = tmp_path / "radar"
    radar_dir.mkdir()
    ledger = ObservationLedger(radar_dir / "radar.db")
    ledger.ensure_source("crossref", label="Crossref", adapter_version="a1", cadence_hours=6)
    ledger.close()

    store = HumanStore(str(radar_dir / "human.db"))
    store.save_watchlist("Recalls", {"source": "openfda_recall"})
    store.set_review("obs-1", status="CONFIRMED", note="verified")
    store.close()

    paths = radar_paths(radar_dir)
    result = backup(paths, destination=tmp_path / "backups", keep=5, log=lambda _m: None)
    manifest = result.manifest
    assert manifest["human_included"] is True
    human_path = Path(manifest["human_backup"])
    assert human_path.is_file()
    assert manifest["human_counts"]["watchlist"] == 1
    assert manifest["human_counts"]["review"] == 1
    assert manifest["human_counts"]["audit"] >= 1, "the audit trail travels with the decisions"

    restored = sqlite3.connect(f"file:{human_path.as_posix()}?mode=ro", uri=True)
    try:
        assert restored.execute("SELECT name FROM watchlist").fetchone()[0] == "Recalls"
        assert restored.execute("SELECT status FROM review").fetchone()[0] == "CONFIRMED"
    finally:
        restored.close()
