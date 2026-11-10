"""End-to-end integration test on a small real slice of the frozen export."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from medradar.integration import demo  # noqa: E402
from medradar.integration.staging import ConvergenceStore  # noqa: E402

EXPORT = REPO_ROOT / "research/horizon/exports/horizon-2026-11-10"


def _run_pipeline(db: Path, run_id: str, limit: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools/convergence/run_integration.py"),
            "--fresh",
            "--db",
            str(db),
            "--run-id",
            run_id,
            "--limit",
            str(limit),
            "--no-graph",
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


@pytest.fixture(scope="module")
def imported(tmp_path_factory) -> tuple[Path, dict]:
    db = tmp_path_factory.mktemp("e2e") / "staging.sqlite"
    proc = _run_pipeline(db, "e2e_test", 250)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads(
        (REPO_ROOT / "research/convergence/reports/integration_e2e_test.json").read_text(
            encoding="utf-8"
        )
    )
    return db, report


def test_pipeline_reports_verified_integrity(imported):
    _, report = imported
    counts = report["integrity"]["state_counts"]
    assert counts.get("mismatch", 0) == 0
    assert counts.get("verbose", 0) == 0
    assert report["integrity"]["problems"] == []
    # The quarantined source is declared but absent, which is the expected state.
    assert counts.get("quarantined", 0) == 1


def test_every_imported_record_is_accounted_for(imported):
    _, report = imported
    assert report["import"]["seen"] == report["import"]["converted"] + report["import"]["degraded"] + report["import"]["rejected"]
    assert report["import"]["rejected"] == 0


def test_no_imported_record_claims_identity(imported):
    db, _ = imported
    with ConvergenceStore(db) as store:
        rows = store.atlas.query("SELECT DISTINCT identity_status FROM evidence")
    assert [row["identity_status"] for row in rows] == ["not_attempted"]


def test_restricted_source_is_absent_from_staging(imported):
    db, _ = imported
    with ConvergenceStore(db) as store:
        rows = store.atlas.query("SELECT DISTINCT source_id FROM evidence")
        sources = {row["source_id"] for row in rows}
    assert "un_comtrade" not in sources


def test_demo_queries_return_cited_evidence(imported):
    db, _ = imported
    with ConvergenceStore(db) as store:
        result = demo.q1_company_product_regulatory(store, "medtronic", limit=5)
        as_of = demo.q6_as_of(store, "2020-01-01", limit=5)
    assert "products" in result
    if result["products"]:
        first = result["products"][0]
        assert first["evidence_id"].startswith("ev_")
        assert first["source_id"]
        assert first["source_record_id"]
        assert set(first["time"]) >= {
            "event_at",
            "source_public_at",
            "first_observed_at",
            "fetched_at",
        }
    assert set(as_of["counts"]) == {
        "observed_by_cutoff",
        "public_by_cutoff_not_yet_observed",
        "not_knowable_by_cutoff",
    }


def test_as_of_never_counts_unknown_observation_as_observed(imported):
    db, _ = imported
    with ConvergenceStore(db) as store:
        early = demo.q6_as_of(store, "2000-01-01", limit=1)
    # Nothing could have been observed by MedRadar in 2000: the corpus was
    # collected in 2026 and unknown observation clocks stay unknown.
    assert early["counts"]["observed_by_cutoff"] == 0


def test_pipeline_is_deterministic(tmp_path):
    db1 = tmp_path / "a.sqlite"
    db2 = tmp_path / "b.sqlite"
    assert _run_pipeline(db1, "det_a", 200).returncode == 0
    report_a = json.loads(
        (REPO_ROOT / "research/convergence/reports/integration_det_a.json").read_text(
            encoding="utf-8"
        )
    )
    assert _run_pipeline(db2, "det_b", 200).returncode == 0
    report_b = json.loads(
        (REPO_ROOT / "research/convergence/reports/integration_det_b.json").read_text(
            encoding="utf-8"
        )
    )
    # The run id is intentionally different; everything else must be identical.
    import_a = {k: v for k, v in report_a["import"].items() if k != "run_id"}
    import_b = {k: v for k, v in report_b["import"].items() if k != "run_id"}
    assert import_a == import_b
    assert report_a["integrity"] == report_b["integrity"]
    assert (
        report_a["dedupe"]["layers"]["record_identity"]
        == report_b["dedupe"]["layers"]["record_identity"]
    )
