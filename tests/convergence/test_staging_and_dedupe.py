"""Staging-database and de-duplication guarantees.

The staging store must be idempotent, version-appending, auditable and
rollback-safe, and it must keep the four identity layers apart.  These tests
build a small real import from the frozen export so they exercise the same code
paths the full run uses.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from medradar.integration.adapter import HorizonToAtlasAdapter  # noqa: E402
from medradar.integration.dedupe import (  # noqa: E402
    dedupe_report,
    patent_family_key,
    party_of,
)
from medradar.integration.licence import LicencePolicy  # noqa: E402
from medradar.integration.staging import ConvergenceStore  # noqa: E402

EXPORT = REPO_ROOT / "research/horizon/exports/horizon-2026-11-10"


def _sample_records(limit_per_source: int = 3) -> list[tuple[dict, bytes]]:
    manifest = json.loads((EXPORT / "MANIFEST.json").read_text(encoding="utf-8"))
    out: list[tuple[dict, bytes]] = []
    for entry in manifest["files"]:
        path = EXPORT / entry["path"]
        if not path.exists():
            continue
        with path.open("rb") as handle:
            for index, line in enumerate(handle):
                if index >= limit_per_source:
                    break
                if line.strip():
                    out.append((json.loads(line), line))
    return out


@pytest.fixture()
def store(tmp_path: Path):
    path = tmp_path / "staging.sqlite"
    with ConvergenceStore(path) as convergence:
        yield convergence


def _import(store: ConvergenceStore, records, run_id: str = "t"):
    adapter = HorizonToAtlasAdapter(LicencePolicy.load())
    store.begin_run(run_id=run_id, export_id="test", policy_id="test")
    summary = store.import_records(
        [record for record, _ in records],
        adapter=adapter,
        run_id=run_id,
        raw_lines=[line for _, line in records],
    )
    store.close_run(run_id)
    return summary


def test_import_is_idempotent(store):
    records = _sample_records()
    first = _import(store, records, "run1")
    second = _import(store, records, "run2")
    assert first["evidence_inserted"] == first["seen"]
    # A second identical import must add no new evidence versions.
    assert second["evidence_inserted"] == 0
    assert second["evidence_noop"] == second["seen"]
    versions = store.atlas.query("SELECT COUNT(*) n, COUNT(DISTINCT evidence_id) d FROM evidence")[0]
    assert versions["n"] == versions["d"]
    assert versions["d"] == first["seen"]


def test_all_records_are_retained_with_their_outcome(store):
    records = _sample_records()
    summary = _import(store, records)
    rows = store.atlas.query("SELECT COUNT(*) n FROM conv_conversions")[0]["n"]
    assert rows == summary["seen"]
    assert store.atlas.query("SELECT COUNT(*) n FROM conv_rejections")[0]["n"] == summary["rejected"]


def test_repeated_source_record_keeps_every_occurrence(store):
    # Two identical source records are two observations of one record: ATLAS
    # versions them, and the staging log must still show both occurrences.
    record, line = _sample_records(1)[0]
    adapter = HorizonToAtlasAdapter(LicencePolicy.load())
    store.begin_run(run_id="dup", export_id="test", policy_id="test")
    summary = store.import_records(
        [record, record], adapter=adapter, run_id="dup", raw_lines=[line, line]
    )
    store.close_run("dup")
    assert summary["seen"] == 2
    assert summary["repeat_observations"] == 1
    occurrences = [
        row["occurrence"]
        for row in store.atlas.query(
            "SELECT occurrence FROM conv_conversions ORDER BY occurrence"
        )
    ]
    assert occurrences == [1, 2]
    # Identical content is a no-op, not a second version.
    assert store.atlas.query("SELECT COUNT(*) n FROM evidence")[0]["n"] == 1


def test_rollback_removes_the_run_and_refuses_to_break_a_later_one(store):
    records = _sample_records()
    _import(store, records, "run1")
    before = store.atlas.query("SELECT COUNT(*) n FROM evidence")[0]["n"]
    result = store.rollback_run("run1")
    assert result["rolled_back"] is True
    assert store.atlas.query("SELECT COUNT(*) n FROM evidence")[0]["n"] == 0
    assert store.atlas.query("SELECT COUNT(*) n FROM conv_conversions")[0]["n"] == 0
    assert before > 0


def test_second_run_cannot_be_rolled_back_out_of_order(store):
    records = _sample_records()
    _import(store, records, "run1")
    _import(store, records, "run2")
    result = store.rollback_run("run1")  # not the latest completed run
    assert result["rolled_back"] is False
    assert "latest" in result["reason"]


def test_identity_status_is_never_confirmed_on_import(store):
    _import(store, _sample_records())
    statuses = {
        row["identity_status"]
        for row in store.atlas.query("SELECT DISTINCT identity_status FROM evidence")
    }
    assert statuses == {"not_attempted"}


def test_dedupe_layers_are_measured_separately():
    records = [
        {
            "evidence_id": "ev_a",
            "source_id": "crossref",
            "evidence_type": "publication",
            "canonical_key": "doi:10.1/x",
            "identifiers": [{"scheme": "doi", "value": "10.1/x"}],
            "normalized": {"horizon": {"source_record_id": "10.1/x"}},
        },
        {
            "evidence_id": "ev_b",
            "source_id": "openalex",
            "evidence_type": "publication",
            "canonical_key": "doi:10.1/x",
            "identifiers": [{"scheme": "doi", "value": "10.1/x"}],
            "normalized": {"horizon": {"source_record_id": "10.1/x"}},
        },
    ]
    report = dedupe_report(records)
    assert report["layers"]["record_identity"]["distinct"] == 2
    assert report["layers"]["entity_identity"]["records_collapsed_into_shared_entity"] == 1
    assert report["independent_pairs_same_key"] == 0


def test_patent_family_null_is_not_a_family():
    record = {
        "evidence_type": "patent",
        "normalized": {"horizon": {"attributes": {"pct_application_number": "NULL"}}},
    }
    assert patent_family_key(record) is None
    record["normalized"]["horizon"]["attributes"]["pct_application_number"] = "PCT/US2020/000001"
    assert patent_family_key(record) == "family:PCT/US2020/000001"


def test_party_extraction_for_party_bearing_source():
    record = {
        "source_id": "eu_ted",
        "normalized": {"horizon": {"attributes": {"supplier_name": "ACME A/S"}}},
    }
    assert party_of(record) == "ACME A/S"
    assert party_of({"source_id": "crossref", "normalized": {"horizon": {"attributes": {}}}}) is None
