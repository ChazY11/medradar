from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from tests.data_pipeline.conftest import make_legacy_snapshot


def _run(args: list[str], root: Path, *, cwd: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["MEDRADAR_PIPELINE_ROOT"] = str(root)
    env["MEDRADAR_REVIEW_DB"] = str(root / "no-review.db")
    env["PYTHONPATH"] = str(cwd)
    return subprocess.run(
        [sys.executable, "-m", "medradar.data_pipeline", *args],
        cwd=str(cwd), env=env, text=True, capture_output=True, timeout=120,
    )


def test_cli_accepts_json_on_both_sides_and_bootstrap_status_changes_prune(tmp_path: Path) -> None:
    cwd = Path(__file__).resolve().parents[2]
    legacy = make_legacy_snapshot(tmp_path / "legacy", [{
        "k_number": "K000001", "applicant": "ACME", "decision_date": "2026-01-01",
        "device_name": "CLI Widget", "product_code": "ABC",
    }])
    root = tmp_path / "state"
    boot = _run(["--root", str(root), "bootstrap", "--from", str(legacy), "--json"], root, cwd=cwd)
    assert boot.returncode == 0, boot.stderr
    boot_payload = json.loads(boot.stdout)
    assert boot_payload["snapshot_id"]

    status = _run(["--root", str(root), "--json", "status"], root, cwd=cwd)
    assert status.returncode == 0, status.stderr
    status_payload = json.loads(status.stdout)
    assert status_payload["active"]["snapshot_id"] == boot_payload["snapshot_id"]
    assert "health" in status_payload["public"]

    changes = _run(["--root", str(root), "changes", "--json"], root, cwd=cwd)
    assert changes.returncode == 0, changes.stderr
    assert "items" in json.loads(changes.stdout)

    prune = _run(["--root", str(root), "prune", "--keep", "4", "--json"], root, cwd=cwd)
    assert prune.returncode == 0, prune.stderr
    assert "kept" in json.loads(prune.stdout)

    backup = _run(["--root", str(root), "backup", "--destination", str(tmp_path / "backups"), "--json"], root, cwd=cwd)
    assert backup.returncode == 0, backup.stderr
    backup_path = json.loads(backup.stdout)["backup"]
    restore = _run([
        "--root", str(root), "restore", "--archive", backup_path,
        "--destination", str(tmp_path / "restored-cli"), "--json",
    ], root, cwd=cwd)
    assert restore.returncode == 0, restore.stderr
    restored = json.loads(restore.stdout)
    assert restored["active_snapshot_id"] == boot_payload["snapshot_id"]


def test_cli_rejects_unknown_command_with_nonzero_exit(tmp_path: Path) -> None:
    cwd = Path(__file__).resolve().parents[2]
    result = _run(["--root", str(tmp_path / "state"), "not-a-command"], tmp_path, cwd=cwd)
    assert result.returncode != 0
