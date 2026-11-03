"""Observatory health — computed from evidence, never from a 200 response.

The panel this feeds must be able to say, simultaneously:

* is there a supervised deployment at all (`NOT_DEPLOYED` is a real answer),
* is the collector running right now (single-writer lease + heartbeat),
* is every source actually fresh, or is one silently failing,
* is the persistence chain healthy (last backup verified, last restore drill),
* is the seven-day validation in progress (and how much of it is real),
* are there unresolved structure alerts.

A single green dot is not allowed to hide a partially failing source, so every
component is returned next to the overall verdict. The precedence order is
documented in docs/RELIABILITY_DESIGN.md §0.
"""

from __future__ import annotations

import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from .ledger import ObservationLedger, default_ledger_path, open_ledger_readonly
from .lock import CollectorLock
from .records import (
    HEALTH_DEGRADED,
    HEALTH_NOT_DEPLOYED,
    HEALTH_OPERATIONAL,
    HEALTH_PAUSED,
    HEALTH_VALIDATION,
    VALIDATION_IN_PROGRESS,
    VALIDATION_PASSED,
)
from .validation import expected_interval_hours, validation_status


def _now(now: datetime | None = None) -> datetime:
    return now or datetime.now(timezone.utc)


def _parse(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _hours_between(earlier: Any, later: datetime) -> float | None:
    moment = _parse(earlier)
    if moment is None:
        return None
    return round((later - moment).total_seconds() / 3600.0, 2)


def _dir_bytes(path: Path) -> int:
    if not path.is_dir():
        return 0
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def _disk_free_bytes(path: Path) -> int | None:
    try:
        anchor = path if path.exists() else path.parent
        while not anchor.exists() and anchor.parent != anchor:
            anchor = anchor.parent
        return shutil.disk_usage(str(anchor)).free
    except OSError:
        return None


def _newest_backup(ledger_path: Path) -> dict[str, Any] | None:
    directory = ledger_path.parent / "backups"
    if not directory.is_dir():
        return None
    candidates = sorted(
        [item for item in directory.glob("observatory-*") if item.is_dir()],
        key=lambda item: item.name,
        reverse=True,
    )
    for candidate in candidates:
        manifest = candidate / "MANIFEST.json"
        if manifest.is_file():
            return {"bundle": candidate.name, "path": str(candidate),
                    "manifest_bytes": manifest.stat().st_size}
    return None


def _deployment_state(ledger: ObservationLedger) -> dict[str, Any]:
    stored = ledger.get_deployment() or {}
    status = str(stored.get("status") or "NOT_DEPLOYED")
    if status not in ("NOT_DEPLOYED", "DEPLOYED_LOCAL", "DEPLOYED_SERVICE"):
        status = "NOT_DEPLOYED"
    return {
        "status": status,
        "installed_at": stored.get("installed_at"),
        "host": stored.get("host"),
        "supervisor": stored.get("supervisor") or "none",
        "note_zh": stored.get("note_zh"),
        "evidence": stored.get("evidence"),
    }


def _collector_state(ledger: ObservationLedger, moment: datetime) -> dict[str, Any]:
    lock_status = CollectorLock(ledger.path).status()
    heartbeat = ledger.get_runtime("heartbeat", {}) or {}
    if not isinstance(heartbeat, dict):
        heartbeat = {}
    last_run = ledger.con.execute(
        "SELECT run_id, source, status, started_at, finished_at FROM sync_run"
        " ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    last_run_row = dict(last_run) if last_run else None
    first_run = ledger.con.execute(
        "SELECT MIN(started_at) FROM sync_run"
    ).fetchone()[0]
    uptime_days = 0.0
    if first_run:
        first = _parse(first_run)
        if first is not None:
            uptime_days = round(max(0.0, (moment - first).total_seconds() / 86400.0), 3)
    return {
        "running": bool(lock_status.get("held")),
        "lock": {
            "held": bool(lock_status.get("held")),
            "stale": lock_status.get("stale"),
            "path": lock_status.get("path"),
            "heartbeat_age_seconds": lock_status.get("heartbeat_age_seconds"),
            "holder": lock_status.get("holder"),
        },
        "heartbeat": heartbeat,
        "last_run": last_run_row,
        "uptime_days": uptime_days,
        "observing_since": first_run,
    }


def health(ledger_path: str | Path | None = None, *, now: datetime | None = None) -> dict[str, Any]:
    """Return the observatory health report (read-only over the ledger)."""
    moment = _now(now)
    path = Path(ledger_path) if ledger_path is not None else default_ledger_path()
    if not path.exists():
        return {
            "generated_at": moment.replace(microsecond=0).isoformat(),
            "overall": HEALTH_NOT_DEPLOYED,
            "deployment": {"status": "NOT_DEPLOYED", "installed_at": None,
                           "host": None, "supervisor": "none",
                           "note_zh": "观察账本不存在：系统从未真实运行过"},
            "validation": {"status": "VALIDATION_NOT_STARTED", "planned_slots": 0,
                           "note_zh": "没有账本，无法证明任何持续运行"},
            "collector": {"running": False, "lock": {"held": False}, "uptime_days": 0.0},
            "persistence": {"ledger_bytes": 0, "raw_cache_bytes": 0,
                            "backup": {"status": "NEVER"}, "restore_drill": {"status": "NEVER"}},
            "sources": [],
            "checks": [{"id": "ledger_exists", "ok": False,
                        "detail_zh": "观察账本不存在"}],
            "unresolved_structure_alerts": [],
            "limitations_zh": ["没有观察账本：NOT_DEPLOYED 是唯一诚实的结论"],
        }
    ledger = open_ledger_readonly(path)
    try:
        counts = ledger.counts()
        deployment = _deployment_state(ledger)
        collector = _collector_state(ledger, moment)
        validation = validation_status(ledger, now=moment)
        paused_state = ledger.get_runtime("paused", {}) or {}
        paused = bool(isinstance(paused_state, dict) and paused_state.get("paused"))
        last_backup = ledger.get_runtime("last_backup", {}) or {}
        last_drill = ledger.get_runtime("last_restore_drill", {}) or {}
        if not isinstance(last_backup, dict):
            last_backup = {}
        if not isinstance(last_drill, dict):
            last_drill = {}
        sources: list[dict[str, Any]] = []
        for row in ledger.con.execute("SELECT * FROM source_state ORDER BY source").fetchall():
            state = dict(row)
            freshness = _hours_between(state.get("last_success_at"), moment)
            expected = expected_interval_hours(state.get("declared_cadence_zh"))
            stale_after = max(expected * 3.0, 12.0)
            stale = freshness is None or freshness > stale_after
            structure_alert = bool(state.get("structure_changed_at"))
            sources.append(
                {
                    "source": state.get("source"),
                    "label_zh": state.get("label_zh"),
                    "status": state.get("status"),
                    "last_success_at": state.get("last_success_at"),
                    "last_attempt_at": state.get("last_attempt_at"),
                    "last_failure_at": state.get("last_failure_at"),
                    "consecutive_failures": int(state.get("consecutive_failures") or 0),
                    "last_outcome": state.get("last_outcome"),
                    "last_new_records": state.get("last_new_records"),
                    "last_updated_records": state.get("last_updated_records"),
                    "declared_cadence_zh": state.get("declared_cadence_zh"),
                    "expected_interval_hours": expected,
                    "freshness_hours": freshness,
                    "stale": stale,
                    "stale_after_hours": round(stale_after, 2),
                    "structure_alert": structure_alert,
                    "structure_note_zh": state.get("structure_note_zh"),
                }
            )
        raw_cache_dir = path.parent / "cache"
        raw_cache_bytes = _dir_bytes(raw_cache_dir)
        backup_dir = path.parent / "backups"
        newest_backup = _newest_backup(path)
        backup_age = _hours_between(last_backup.get("at"), moment)
        drill_age = _hours_between(last_drill.get("at"), moment)
        free_bytes = _disk_free_bytes(path.parent)
        structure_alerts = [
            {"source": source["source"], "changed_at": source["structure_alert"] and
             (ledger.con.execute(
                 "SELECT structure_changed_at FROM source_state WHERE source=?",
                 (source["source"],),
             ).fetchone()[0]),
             "note_zh": source["structure_note_zh"]}
            for source in sources if source["structure_alert"]
        ]
        checks: list[dict[str, Any]] = []

        def add(check_id: str, ok: bool, detail_zh: str) -> None:
            checks.append({"id": check_id, "ok": bool(ok), "detail_zh": detail_zh})

        add("ledger_exists", True, f"账本存在，{counts['observations']} 条观察")
        add("sources_present", len(sources) == 3,
            f"已登记来源 {len(sources)}/3：{', '.join(s['source'] for s in sources) or '无'}")
        failing = [source for source in sources if source["status"] not in ("OK",)]
        add("sources_healthy", not failing,
            "全部来源状态 OK" if not failing else
            "异常来源：" + "，".join(f"{s['source']}={s['status']}" for s in failing))
        stale_sources = [source for source in sources if source["stale"]]
        add("freshness", not stale_sources,
            "全部来源新鲜度在阈值内" if not stale_sources else
            "超过阈值的来源：" + "，".join(
                f"{s['source']}（{s['freshness_hours']}h > {s['stale_after_hours']}h）"
                for s in stale_sources))
        add("collector_recent", collector["last_run"] is not None,
            f"最近运行：{collector['last_run']['run_id'] if collector['last_run'] else '无'}")
        backup_ok = bool(last_backup.get("status") == "OK" and last_backup.get("verified"))
        add("backup", backup_ok,
            "最近备份已验证" if backup_ok else
            f"最近备份状态：{last_backup.get('status') or 'NEVER'}（未通过验证的备份不算 OK）")
        backup_fresh = backup_age is not None and backup_age <= 48.0
        add("backup_freshness", backup_fresh,
            f"最近备份 {backup_age} 小时前" if backup_age is not None else "没有备份记录")
        drill_ok = bool(last_drill.get("status") == "OK")
        add("restore_drill", drill_ok,
            "最近恢复演练成功" if drill_ok else
            f"最近恢复演练：{last_drill.get('status') or 'NEVER'}（未演练不等于可恢复）")
        if drill_age is not None and drill_age > 24 * 30:
            add("restore_drill_freshness", False, f"恢复演练已 {drill_age:.0f} 小时未执行")
        add("structure_alerts", not structure_alerts,
            "没有未解决的结构变化告警" if not structure_alerts else
            "未解决告警：" + "，".join(item["source"] for item in structure_alerts))
        add("disk_space", free_bytes is None or free_bytes > 512 * 1024 * 1024,
            f"可用磁盘 {round((free_bytes or 0) / (1024 ** 3), 2)} GB" if free_bytes else "无法读取磁盘空间")
        consistency = ledger.consistency_check()
        add("integrity", bool(consistency.get("ok")),
            "一致性检查通过" if consistency.get("ok") else
            f"一致性异常 {consistency.get('issue_count')} 项：{sorted((consistency.get('issues') or {}).keys())}")

        degraded = (
            bool(failing) or bool(stale_sources) or bool(structure_alerts)
            or not backup_ok or not backup_fresh or not drill_ok
            or not consistency.get("ok")
        )
        if deployment["status"] == "NOT_DEPLOYED":
            overall = HEALTH_NOT_DEPLOYED
        elif paused:
            overall = HEALTH_PAUSED
        elif degraded:
            overall = HEALTH_DEGRADED
        elif validation.get("status") == VALIDATION_IN_PROGRESS:
            overall = HEALTH_VALIDATION
        else:
            overall = HEALTH_OPERATIONAL
        # A validation that is explicitly passed does not change the health word;
        # it is reported in the validation block.
        limitations = [
            "健康状态由账本、文件系统与运行记录计算，不代表 HTTP 服务是否 200。",
            "NOT_DEPLOYED 表示没有经过验证的常驻部署；手动运行与本地验证不等于生产部署。",
            "VALIDATION_IN_PROGRESS 表示七天连续验证尚未结束：不能宣称已通过。",
        ]
        if validation.get("status") == VALIDATION_PASSED:
            limitations.append("七天验证已完成并在验证窗口结束后由 validate stop 显式写入。")
        return {
            "generated_at": moment.replace(microsecond=0).isoformat(),
            "ledger": {
                "path": counts.get("path"),
                "exists": True,
                "bytes": counts["db_bytes"],
                "observations": counts["observations"],
                "versions": counts["versions"],
                "changes": counts["changes"],
                "runs": counts["runs"],
                "first_observation_at": counts["first_observation_at"],
                "last_run_at": counts["last_run_at"],
            },
            "overall": overall,
            "deployment": deployment,
            "validation": validation,
            "collector": collector,
            "persistence": {
                "ledger_bytes": counts["db_bytes"],
                "raw_cache_bytes": raw_cache_bytes,
                "raw_cache_path": str(raw_cache_dir),
                "backup": {
                    "at": last_backup.get("at"),
                    "status": last_backup.get("status") or "NEVER",
                    "verified": bool(last_backup.get("verified")),
                    "bundle": last_backup.get("bundle"),
                    "age_hours": backup_age,
                    "counts": last_backup.get("counts"),
                    "error": last_backup.get("error"),
                },
                "restore_drill": {
                    "at": last_drill.get("at"),
                    "status": last_drill.get("status") or "NEVER",
                    "ok": last_drill.get("ok"),
                    "age_hours": drill_age,
                    "bundle": last_drill.get("bundle"),
                    "error": last_drill.get("error"),
                },
                "newest_backup_bundle": newest_backup,
                "backup_dir": str(backup_dir),
                "disk_free_bytes": free_bytes,
            },
            "sources": sources,
            "unresolved_structure_alerts": [
                {"source": item["source"], "changed_at": item.get("changed_at"),
                 "note_zh": item.get("note_zh")}
                for item in structure_alerts
            ],
            "checks": checks,
            "limitations_zh": limitations,
        }
    finally:
        ledger.close()


__all__ = ["health"]
