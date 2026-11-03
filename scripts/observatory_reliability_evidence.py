"""Generate the reliability acceptance evidence bundle (UTF-8 JSON, committed).

Everything here is *read* from the real ledger, the real filesystem and the real
supervisor state. Nothing is fabricated: a capability that cannot be demonstrated
yet (for example a completed seven-day window) is recorded with its honest status.

Usage::

    python scripts/observatory_reliability_evidence.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from medradar.observatory import backup as backup_mod  # noqa: E402
from medradar.observatory import health as health_mod  # noqa: E402
from medradar.observatory import validation as validation_mod  # noqa: E402
from medradar.observatory.audit import audit_ledger, render_report  # noqa: E402
from medradar.observatory.ledger import ObservationLedger, default_ledger_path  # noqa: E402
from medradar.observatory.lock import CollectorLock  # noqa: E402
from medradar.observatory.runner import status_report, sync  # noqa: E402

EVIDENCE = ROOT / "docs" / "reliability" / "evidence"


def write(name: str, payload) -> str:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return str(path.relative_to(ROOT))


def _task_status() -> dict:
    if os.name != "nt":
        return {"available": False, "reason": "not Windows"}
    exe = shutil.which("schtasks")
    if not exe:
        return {"available": False, "reason": "schtasks not found"}
    proc = subprocess.run(
        [exe, "/Query", "/TN", "MedRadarObservatory", "/V", "/FO", "LIST"],
        capture_output=True, text=True, errors="replace",
    )
    text = (proc.stdout or "") + (proc.stderr or "")
    interesting = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if key.lower() in {"taskname", "status", "state", "last run time", "last result",
                           "next run time", "number of missed runs", "task to run",
                           "scheduled task state", "lastruntime", "lasttaskresult",
                           "nextruntime", "numberofmissedruns", "tasktorun"}:
            interesting[key] = value.strip()
    return {"available": True, "returncode": proc.returncode, "summary": interesting,
            "raw_excerpt": "\n".join(text.splitlines()[:40])}


def main() -> int:
    ledger_path = default_ledger_path()
    ledger = ObservationLedger(ledger_path, read_only=True)
    try:
        generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        health = health_mod.health(ledger_path)
        status = status_report(ledger_path=ledger_path, include_consistency=True)
        validation = validation_mod.validation_status(ledger)
        audit = audit_ledger(ledger_path)
        audit_markdown = render_report(audit, style="markdown")
        lock_status = CollectorLock(ledger_path).status()
        backups = backup_mod.list_backups(ledger_path.parent / "backups")
        last_backup = ledger.get_runtime("last_backup", {})
        last_drill = ledger.get_runtime("last_restore_drill", {})
        deployment = ledger.get_deployment()
        lock_recovery = ledger.get_runtime("lock_recovery")
        outcomes = [
            dict(row) for row in ledger.con.execute(
                "SELECT source, last_outcome, last_new_records, last_updated_records,"
                " last_success_at, last_attempt_at, consecutive_failures, status"
                " FROM source_state ORDER BY source"
            ).fetchall()
        ]
        ops = ledger.ops_metric_series("daily_snapshot", days=30)
        runs = [
            dict(row) for row in ledger.con.execute(
                "SELECT run_id, source, status, trigger, started_at, finished_at, requests,"
                " records_seen, records_new, records_updated, records_unchanged, error_detail"
                " FROM sync_run ORDER BY started_at"
            ).fetchall()
        ]
        phases = ledger.phase_summary()
        observation_stats = ledger.observation_stats()
        counts = ledger.counts()
    finally:
        ledger.close()

    concurrency: dict = {"attempted": False}
    # Prove the single-writer guard against the really running scheduled collector.
    # If the supervisor is not currently holding the lease, run the probe against a
    # temporary lease instead of disturbing the live ledger.
    temp_ledger = ROOT / "out" / "reliability_evidence" / "lock_probe.sqlite"
    temp_ledger.parent.mkdir(parents=True, exist_ok=True)
    probe = CollectorLock(ledger_path)
    if probe.status()["held"]:
        try:
            report = sync(sources=["sec_edgar"], ledger_path=ledger_path, log=lambda m: None)
            concurrency = {
                "attempted": True,
                "expected": "LOCKED_SKIPPED",
                "locked": report.get("locked"),
                "ok": report.get("ok"),
                "sources": report.get("sources"),
                "note_zh": "在常驻采集进程持有租约时，第二个采集进程被拒绝，未写入任何观察",
            }
        except Exception as exc:  # noqa: BLE001
            concurrency = {"attempted": True, "error": f"{type(exc).__name__}: {exc}"}
    else:
        temp_ledger_path = temp_ledger
        if temp_ledger_path.exists():
            temp_ledger_path.unlink()
        holder = CollectorLock(temp_ledger_path)
        holder.acquire(mode="watch")
        try:
            report = sync(sources=["sec_edgar"], ledger_path=str(temp_ledger_path),
                          log=lambda m: None)
            concurrency = {
                "attempted": True,
                "probe": "temporary ledger with a held lease (live supervisor not running)",
                "expected": "LOCKED_SKIPPED",
                "locked": report.get("locked"),
                "ok": report.get("ok"),
                "sources": report.get("sources"),
            }
        finally:
            holder.release()

    bundle = {
        "generated_at": generated_at,
        "ledger_path": str(ledger_path.relative_to(ROOT)) if ledger_path.is_relative_to(ROOT) else str(ledger_path),
        "counts": counts,
        "observation_stats": observation_stats,
        "phases": phases,
        "source_outcomes": outcomes,
        "health": health,
        "status": status,
        "validation": validation,
        "deployment": deployment,
        "lock": lock_status,
        "lock_recovery": lock_recovery,
        "backups": backups,
        "last_backup": last_backup,
        "last_restore_drill": last_drill,
        "runs": runs,
        "ops_metrics": ops,
        "concurrency_probe": concurrency,
        "audit": audit,
        "supervisor_task": _task_status(),
    }
    bundle_path = write("dependency_health_and_validation.json", {
        "generated_at": generated_at,
        "ledger": counts,
        "phases": phases,
        "source_outcomes": outcomes,
        "health": health,
        "validation": validation,
        "deployment": deployment,
        "lock": lock_status,
        "lock_recovery": lock_recovery,
        "concurrency_probe": concurrency,
        "supervisor_task": bundle["supervisor_task"],
    })
    write("backup_and_restore.json", {
        "generated_at": generated_at,
        "last_backup": last_backup,
        "backups": backups,
        "last_restore_drill": last_drill,
    })
    write("audit_report.json", audit)
    (EVIDENCE / "audit_report.md").write_text(audit_markdown, encoding="utf-8")
    write("runs_and_outcomes.json", {"runs": runs, "source_outcomes": outcomes,
                                     "ops_metrics": ops})
    write("full_bundle.json", bundle)

    print(json.dumps({
        "evidence": [p.name for p in sorted(EVIDENCE.iterdir())],
        "bundle": bundle_path,
        "overall_health": health["overall"],
        "validation_status": validation.get("status"),
        "deployment": deployment.get("status"),
        "observations": counts["observations"],
        "runs": len(runs),
        "audit_overall": audit.get("overall"),
        "concurrency_locked": concurrency.get("locked"),
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
