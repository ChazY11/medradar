"""Backup and restore drill: the ledger is recoverable, the graph is rebuildable.

A backup that only copies bytes is not a recovery test. These tests copy a live ledger through
SQLite's online backup API, verify the copy's own integrity and counts, then restore it into an
isolated directory and rebuild the technology graph from it.
"""

from __future__ import annotations

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
