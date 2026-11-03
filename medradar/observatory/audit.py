"""Read-only integrity audit of the Observation Ledger (design contract §7).

What this module is
-------------------
A **read-only** audit that answers one question honestly: *can the ledger still
prove what MedRadar had observed at a given past instant?*  It never repairs,
never migrates, never writes: the ledger is opened with
``open_ledger_readonly`` (SQLite URI ``mode=ro`` + ``PRAGMA query_only=ON``),
the collector lock is not taken, and no file is created next to the ledger
apart from SQLite's own shared-memory sidecars.

Verdict vocabulary (never collapsed into a boolean)::

    PASS                     every rule of the check was proved on real rows;
    FAIL                     a rule was proved violated (evidence names the
                             offending ids / counts / hashes);
    REQUIRES_MANUAL_REVIEW   the evidence needed to prove the rule is missing or
                             ambiguous.  Absence of evidence is **never** PASS.

Overall: ``FAIL`` if any check fails, else ``REQUIRES_MANUAL_REVIEW`` if any check
needs a human, else ``PASS``.  ``run_audit`` maps that to an exit code: 1 only
for ``FAIL``.

The ten checks (design §7, implemented in this order)
-----------------------------------------------------
1.  duplicate observations per ``(source, source_record_id)``;
2.  ``first_seen_at`` integrity (+ immutability trigger existence);
3.  payload version chain (contiguous seq, hash chain, latest pointers);
4.  version ↔ change consistency (+ real payload diff of ``changed_fields``);
5.  timestamp ordering (versions / changes / status history vs first_seen);
6.  watermark safety (parseable, only advanced by successful runs, failures are
    reported instead of being silently claimed complete);
7.  replay correctness (``snapshot`` for sampled multi-version observations);
8.  prospective registry freeze integrity (``verify_frozen`` per entry);
9.  mapping history preservation (+ latest row matches the observation view);
10. backup / restore reproducibility (manifest vs live ledger).

An eleventh, **optional** check (``observation_phase_completeness``) is added only
when the ledger has the append-only ``observation_phase`` table contributed by
the Lead.  On an older ledger its verdict is ``REQUIRES_MANUAL_REVIEW`` — never
``FAIL`` — because the table may not exist yet by design.

Rules this audit implements where the schema has a subtlety
-----------------------------------------------------------
**Version ↔ change rows.**  ``record_observation`` writes one change row per new
version: ``NEW`` for ``version_seq = 1`` and ``UPDATED`` for later versions.  A
record that disappears and re-appears with a *byte-identical* payload does **not**
create a version (the ``observation_version`` hash is unique), only an extra
``UPDATED`` change row that points at the still-latest ``version_id`` with
``changed_fields == ["status"]``.  The implemented rule is therefore:

* every version must be referenced by at least one change row;
* the earliest such change row must be ``NEW`` for ``version_seq = 1`` and
  ``UPDATED`` for ``version_seq > 1``;
* any *additional* change row for the same version must be a status restoration:
  state ``UPDATED`` and ``changed_fields == ["status"]``;
* change rows of state ``REMOVED_OR_UNAVAILABLE`` / ``FETCH_FAILED`` must carry
  ``version_id IS NULL`` (they are not evidence of a payload version); a history
  of only ``NEW`` + ``REMOVED_OR_UNAVAILABLE`` is therefore valid, which is why
  a removed observation does not fail this check;
* ``changed_fields`` of a version with ``version_seq > 1`` must equal
  ``records.changed_fields(previous_payload, payload)`` — the real diff of the two
  stored canonical payloads — and the matching change row must record the same
  list.

**Watermarks.**  A source's watermark may only be advanced by a run that actually
completed the scopes it claims.  The audit fails when the watermark's timestamp
is newer than ``last_success_at`` and no failed/partial run explains it, and it
raises ``REQUIRES_MANUAL_REVIEW`` (with the run ids) whenever a ``FAILED`` /
``PARTIAL`` run advanced the stored watermark: the audit cannot prove which pages
that run actually completed, so it refuses to call it a success.

**Replay.**  The deterministic sample is the multi-version observation ids sorted
by id and evenly spaced.  For each sample ``snapshot(captured_at_of_v1)`` must
return the v1 payload, ``snapshot(first_seen_at - 1s)`` must exclude the record,
and every distinct ``captured_at`` in the chain must replay the newest version
captured at that instant (two versions may share the same second; the later seq
wins, which is the ledger's own ``MAX(version_seq)`` rule).  Every ``snapshot``
boundary is derived from a *parsed* datetime and handed to SQLite as canonical
UTC (``…+00:00``); the audit never lets the stored spelling (``…Z`` on legacy
rows) decide which records a replay contains.  When no multi-version observation
exists the check is ``REQUIRES_MANUAL_REVIEW`` (nothing to sample); a
supplementary single-version boundary probe is then reported as evidence, never
as a silent PASS.

**Backup / restore.**  A manifest that was created at/after the live ledger's
last write must reproduce it exactly (counts, min/max ``first_seen_at``,
per-source counts; watermarks too when the manifest records them) — any mismatch
is ``FAIL``.  A manifest that predates the newest ledger write cannot prove the
*current* ledger, so a consistent prefix yields
``REQUIRES_MANUAL_REVIEW`` (a restore drill is required) while an inconsistent
prefix is still ``FAIL``.  No manifest/bundle at all is
``REQUIRES_MANUAL_REVIEW``: the audit never returns PASS on absence.

Public API
----------
``audit_ledger(...) -> dict``   build the structured report (read-only);
``render_report(report, style) -> str``  human-reviewable text / markdown;
``run_audit(json_output=False, verbose=False, backup_manifest_path=None)``
stable entry point for ``python -m medradar observatory audit``; returns
``(exit_code, report)`` with ``exit_code == 1`` only on ``FAIL``.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import prospective
from .ledger import default_ledger_path, open_ledger_readonly
from .records import (
    CHANGE_FETCH_FAILED,
    CHANGE_NEW,
    CHANGE_REMOVED,
    CHANGE_UPDATED,
    ENTITY_MAPPED,
    ENTITY_STATUSES,
    RUN_FAILED,
    RUN_PARTIAL,
    TRACK_MAPPED,
    TRACK_STATUSES,
    canonical_json,
    changed_fields,
    parse_moment,
    payload_hash,
    utc_now_iso,
    version_id as make_version_id,
)

AUDIT_VERSION = "obs-audit-v1"
REPORT_SCHEMA = "medradar-ledger-audit-1"

VERDICT_PASS = "PASS"
VERDICT_FAIL = "FAIL"
VERDICT_MANUAL = "REQUIRES_MANUAL_REVIEW"
VERDICTS = (VERDICT_PASS, VERDICT_FAIL, VERDICT_MANUAL)

#: Maximum number of offending ids/rows embedded in one check's evidence.
EVIDENCE_LIMIT = 20

CHECK_IDS: tuple[str, ...] = (
    "duplicate_observations",
    "first_seen_integrity",
    "payload_version_chain",
    "version_change_consistency",
    "timestamp_ordering",
    "watermark_safety",
    "replay_correctness",
    "prospective_freeze_integrity",
    "mapping_history_preservation",
    "backup_restore_reproducibility",
)

OPTIONAL_CHECK_ID = "observation_phase_completeness"

CHECK_TITLES_ZH: dict[str, str] = {
    "duplicate_observations": "重复观察：同一 (source, source_record_id) 只能有一条观察记录",
    "first_seen_integrity": "first_seen_at 完整性：首次观察时间写入后不可被追溯修改",
    "payload_version_chain": "载荷版本链：版本序号连续、哈希可复算、最新版本指针一致",
    "version_change_consistency": "版本与变更记录一致性：每个版本对应正确的变更状态与真实字段差异",
    "timestamp_ordering": "时间戳顺序：版本采集时间单调、不早于首次观察时间",
    "watermark_safety": "水位安全性：水位可解析、只能由成功运行推进、失败运行不得被静默当作完成",
    "replay_correctness": "时点回放正确性：snapshot 在历史时点返回当时已知的版本",
    "prospective_freeze_integrity": "前瞻登记器冻结完整性：每条冻结文档的哈希可复验且未被改写",
    "mapping_history_preservation": "映射历史留存：每条观察都有映射历史，且最新映射与观察接口一致",
    "backup_restore_reproducibility": "备份/恢复可复现性：备份清单与实时账本的计数、首次观察范围、来源分布一致",
    OPTIONAL_CHECK_ID: "采集阶段标注完整性：每条观察都有 phase 行（可选，依赖 observation_phase 表）",
    # Only used by the failure report when the ledger cannot be opened at all.
    "ledger_readable": "账本可读性：审计可以只读打开该 SQLite 文件",
}

CHECK_TITLES_EN: dict[str, str] = {
    "duplicate_observations": "Duplicate observations per (source, source_record_id)",
    "first_seen_integrity": "first_seen_at integrity & immutability triggers",
    "payload_version_chain": "Payload version chain (seq, hash, latest pointers)",
    "version_change_consistency": "Version ↔ change consistency and payload diff",
    "timestamp_ordering": "Timestamp ordering",
    "watermark_safety": "Watermark safety",
    "replay_correctness": "Point-in-time replay correctness",
    "prospective_freeze_integrity": "Prospective registry freeze integrity",
    "mapping_history_preservation": "Mapping history preservation",
    "backup_restore_reproducibility": "Backup / restore reproducibility",
    OPTIONAL_CHECK_ID: "Acquisition-phase annotation completeness (optional)",
    "ledger_readable": "Ledger readable over a read-only SQLite connection",
}

#: Immutability triggers the ledger claims in ``ledger.SCHEMA``.  The audit
#: verifies they still exist: without them ``first_seen_at`` and the payload
#: history are only append-only by convention.
REQUIRED_TRIGGERS: dict[str, tuple[str, ...]] = {
    "observation": (
        "trg_observation_first_seen_immutable",
        "trg_observation_identity_immutable",
        "trg_observation_no_delete",
    ),
    "observation_version": ("trg_version_no_update", "trg_version_no_delete"),
    "observation_change": ("trg_change_no_update", "trg_change_no_delete"),
    "observation_status_history": ("trg_status_no_update", "trg_status_no_delete"),
    "observation_mapping": ("trg_mapping_no_update", "trg_mapping_no_delete"),
    "sync_run": ("trg_run_no_delete", "trg_run_identity_immutable"),
}

#: Honesty statements shipped in every report.
LIMITATIONS_ZH: tuple[str, ...] = (
    "本审计只读：账本以 SQLite mode=ro 打开并设置 query_only，不写入、不改结构、不获取采集锁。",
    "PASS 仅表示本报告的规则在本次运行时刻被真实数据证明；它不等于研究结论已被验证，也不代表观测覆盖完整。",
    "无法被证明的检查项一律标记 REQUIRES_MANUAL_REVIEW，绝不因证据缺失而默认通过。",
    "备份清单只能证明“该时刻存在一份可复现的快照”，不能证明磁盘/对象存储的真实冗余或异地可用性；恢复演练需单独留证。",
    "审计样本量有限（回放样本由 sample_size 控制）；未抽中的记录未被逐条回放验证。",
)


# --------------------------------------------------------------------------- helpers
def _now_iso() -> str:
    return utc_now_iso()


def _cap(items: Iterable[Any], limit: int = EVIDENCE_LIMIT) -> list[Any]:
    """Bound an evidence list so one broken ledger cannot produce a huge report."""
    out: list[Any] = []
    for item in items:
        out.append(item)
        if len(out) >= limit:
            break
    return out


def _display_path(path: str | Path) -> str:
    """Relative path when inside the checkout, else the absolute path string."""
    resolved = Path(path).expanduser()
    try:
        return resolved.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except (ValueError, OSError):
        return str(resolved)


def _parse(text: Any) -> datetime | None:
    """Parse a stored moment without inventing information (``None`` if unknown)."""
    if text is None:
        return None
    value = str(text).strip()
    if not value:
        return None
    return parse_moment(value)


def _same_moment(left: Any, right: Any) -> bool:
    left_moment, right_moment = _parse(left), _parse(right)
    return left_moment is not None and right_moment is not None and left_moment == right_moment


def _le(left: Any, right: Any) -> bool:
    left_moment, right_moment = _parse(left), _parse(right)
    return left_moment is not None and right_moment is not None and left_moment <= right_moment


def _lt(left: Any, right: Any) -> bool:
    left_moment, right_moment = _parse(left), _parse(right)
    return left_moment is not None and right_moment is not None and left_moment < right_moment


def _before(text: Any, seconds: int = 1) -> str:
    moment = _parse(text)
    if moment is None:
        raise ValueError(f"cannot parse moment: {text!r}")
    return (moment - timedelta(seconds=seconds)).replace(microsecond=0).isoformat()


def _canonical_boundary(value: Any) -> str:
    """One spelling for a ``snapshot(as_of=...)`` boundary: parsed, UTC, +00:00.

    Legacy rows may store ``…Z`` while newer writes store ``…+00:00``.  Passing a
    stored string straight through would let a spelling difference decide which
    records a replay contains, so the audit always derives the boundary from a
    parsed datetime and hands SQLite a canonical UTC instant.
    """
    moment = _parse(value)
    if moment is None:
        raise ValueError(f"cannot parse snapshot boundary: {value!r}")
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _bounded_text(value: Any, limit: int = 240) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _parse_changed_fields(value: Any) -> list[str] | None:
    """Decode a stored ``changed_fields`` JSON list (``None`` means corrupt)."""
    if value is None or value == "":
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return None
    if parsed is None:
        return []
    if not isinstance(parsed, list):
        return None
    return [str(item) for item in parsed]


def _check_result(check_id: str, verdict: str, detail_zh: str,
                  evidence: Mapping[str, Any]) -> dict[str, Any]:
    if verdict not in VERDICTS:  # pragma: no cover - programming error
        raise ValueError(f"bad verdict: {verdict}")
    return {
        "id": check_id,
        "title_zh": CHECK_TITLES_ZH[check_id],
        "verdict": verdict,
        "detail_zh": detail_zh,
        "evidence": dict(evidence),
    }


# ----------------------------------------------------------------------------- facts
def _load_facts(con: sqlite3.Connection) -> dict[str, Any]:
    """Read every row the checks need, once, in a bounded number of queries."""

    def rows(sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        return [dict(row) for row in con.execute(sql, params).fetchall()]

    observations = rows("SELECT * FROM observation")
    versions = rows(
        "SELECT version_id, observation_id, version_seq, captured_at, change_state,"
        " payload_hash, payload_bytes, changed_fields, source_updated_at, run_id"
        " FROM observation_version ORDER BY observation_id, version_seq"
    )
    changes = rows(
        "SELECT change_id, observation_id, source, change_state, observed_at,"
        " version_id, previous_version_id, changed_fields, first_seen_at, run_id"
        " FROM observation_change ORDER BY observation_id, observed_at, change_id"
    )
    status_history = rows(
        "SELECT observation_id, changed_at, status, run_id FROM observation_status_history"
        " ORDER BY observation_id, changed_at"
    )
    mappings = rows("SELECT * FROM observation_mapping ORDER BY observation_id, mapped_at")
    sources = rows("SELECT * FROM source_state")
    runs = rows("SELECT * FROM sync_run")
    triggers = {
        str(row["name"])
        for row in con.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall()
    }
    tables = {
        str(row["name"])
        for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }

    observations_by_id = {str(row["observation_id"]): row for row in observations}
    versions_by_obs: dict[str, list[dict[str, Any]]] = {}
    for row in versions:
        versions_by_obs.setdefault(str(row["observation_id"]), []).append(row)
    changes_by_obs: dict[str, list[dict[str, Any]]] = {}
    changes_by_version: dict[str, list[dict[str, Any]]] = {}
    for row in changes:
        changes_by_obs.setdefault(str(row["observation_id"]), []).append(row)
        if row.get("version_id"):
            changes_by_version.setdefault(str(row["version_id"]), []).append(row)
    status_by_obs: dict[str, list[dict[str, Any]]] = {}
    for row in status_history:
        status_by_obs.setdefault(str(row["observation_id"]), []).append(row)
    mappings_by_obs: dict[str, list[dict[str, Any]]] = {}
    for row in mappings:
        mappings_by_obs.setdefault(str(row["observation_id"]), []).append(row)

    source_counts: dict[str, int] = {}
    for row in observations:
        key = str(row["source"])
        source_counts[key] = source_counts.get(key, 0) + 1

    # Newest recorded moment anywhere in the ledger: used to decide whether a
    # backup manifest is current enough for strict identity.
    last_write: str | None = None
    candidates: list[str] = []
    for row in observations:
        candidates.extend(filter(None, [row.get("first_seen_at"), row.get("last_checked_at")]))
    for row in versions:
        candidates.append(str(row.get("captured_at") or ""))
    for row in changes:
        candidates.append(str(row.get("observed_at") or ""))
    for row in runs:
        candidates.extend(filter(None, [row.get("started_at"), row.get("finished_at")]))
    for row in sources:
        candidates.extend(
            filter(None, [row.get("last_attempt_at"), row.get("last_success_at"),
                          row.get("last_failure_at")])
        )
    for candidate in candidates:
        moment = _parse(candidate)
        if moment is None:
            continue
        if last_write is None or moment > (_parse(last_write) or moment):
            last_write = str(candidate)

    return {
        "observations": observations,
        "observations_by_id": observations_by_id,
        "versions": versions,
        "versions_by_obs": versions_by_obs,
        "changes": changes,
        "changes_by_obs": changes_by_obs,
        "changes_by_version": changes_by_version,
        "status_by_obs": status_by_obs,
        "mappings": mappings,
        "mappings_by_obs": mappings_by_obs,
        "sources": sources,
        "runs": runs,
        "triggers": triggers,
        "tables": tables,
        "source_counts": source_counts,
        "last_write": last_write,
    }


# ------------------------------------------------------------------------ check 1
def _check_duplicate_observations(facts: Mapping[str, Any],
                                  con: sqlite3.Connection) -> dict[str, Any]:
    rows = [
        dict(row)
        for row in con.execute(
            "SELECT source, source_record_id, COUNT(*) AS n,"
            " GROUP_CONCAT(observation_id) AS observation_ids"
            " FROM observation GROUP BY source, source_record_id"
            " HAVING COUNT(*) > 1 ORDER BY n DESC, source, source_record_id LIMIT ?",
            (EVIDENCE_LIMIT,),
        ).fetchall()
    ]
    total_rows = con.execute(
        "SELECT COUNT(*) FROM (SELECT 1 FROM observation"
        " GROUP BY source, source_record_id HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    duplicates = []
    for row in rows:
        ids = [item for item in str(row.get("observation_ids") or "").split(",") if item]
        duplicates.append(
            {
                "source": row["source"],
                "source_record_id": row["source_record_id"],
                "rows": int(row["n"]),
                "observation_ids": _cap(ids, 5),
                "observation_ids_total": len(ids),
            }
        )
    evidence = {
        "rule": "GROUP BY source, source_record_id HAVING COUNT(*) > 1 必须为 0",
        "observations": len(facts["observations"]),
        "duplicate_groups": int(total_rows),
        "duplicates": duplicates,
        "duplicates_truncated": int(total_rows) > len(duplicates),
    }
    if total_rows:
        detail = (
            f"发现 {int(total_rows)} 组重复的 (source, source_record_id)：同一来源记录被写成多条观察，"
            "历史的“首次观察”与版本链将出现歧义。"
        )
        return _check_result("duplicate_observations", VERDICT_FAIL, detail, evidence)
    detail = (
        f"共 {len(facts['observations'])} 条观察，按 (source, source_record_id) 分组没有重复组；"
        "每条来源记录恰好对应一条观察。"
    )
    return _check_result("duplicate_observations", VERDICT_PASS, detail, evidence)


# ------------------------------------------------------------------------ check 2
def _check_first_seen_integrity(facts: Mapping[str, Any]) -> dict[str, Any]:
    missing_triggers = [
        {"table": table, "trigger": trigger}
        for table, wanted in REQUIRED_TRIGGERS.items()
        for trigger in wanted
        if trigger not in facts["triggers"]
    ]
    bad_first_version: list[dict[str, Any]] = []
    missing_first_version: list[str] = []
    bad_status_history: list[dict[str, Any]] = []
    bad_last_checked: list[dict[str, Any]] = []
    for observation in facts["observations"]:
        oid = str(observation["observation_id"])
        first_seen = observation.get("first_seen_at")
        versions = facts["versions_by_obs"].get(oid) or []
        if not versions:
            missing_first_version.append(oid)
        else:
            first_version = versions[0]
            if not _same_moment(first_version.get("captured_at"), first_seen):
                bad_first_version.append(
                    {
                        "observation_id": oid,
                        "first_seen_at": first_seen,
                        "first_version_captured_at": first_version.get("captured_at"),
                    }
                )
        history = facts["status_by_obs"].get(oid) or []
        if not history:
            bad_status_history.append({"observation_id": oid, "issue": "missing_status_history"})
        elif not _same_moment(history[0].get("changed_at"), first_seen):
            bad_status_history.append(
                {
                    "observation_id": oid,
                    "issue": "first_status_changed_at_mismatch",
                    "first_seen_at": first_seen,
                    "first_status_changed_at": history[0].get("changed_at"),
                }
            )
        last_checked = observation.get("last_checked_at")
        if last_checked and not _le(first_seen, last_checked):
            bad_last_checked.append(
                {
                    "observation_id": oid,
                    "first_seen_at": first_seen,
                    "last_checked_at": last_checked,
                }
            )
    evidence = {
        "rule": (
            "首个版本 captured_at == first_seen_at；状态历史首行 changed_at == first_seen_at；"
            "last_checked_at >= first_seen_at；不可变触发器必须存在"
        ),
        "observations_checked": len(facts["observations"]),
        "required_triggers": {table: list(names) for table, names in REQUIRED_TRIGGERS.items()},
        "triggers_present": sorted(
            trigger
            for names in REQUIRED_TRIGGERS.values()
            for trigger in names
            if trigger in facts["triggers"]
        ),
        "missing_triggers": missing_triggers,
        "missing_first_version": _cap(missing_first_version),
        "missing_first_version_total": len(missing_first_version),
        "bad_first_version": _cap(bad_first_version),
        "bad_first_version_total": len(bad_first_version),
        "bad_status_history": _cap(bad_status_history),
        "bad_status_history_total": len(bad_status_history),
        "bad_last_checked": _cap(bad_last_checked),
        "bad_last_checked_total": len(bad_last_checked),
    }
    problems = (
        missing_triggers
        or missing_first_version
        or bad_first_version
        or bad_status_history
        or bad_last_checked
    )
    if problems:
        parts = []
        if missing_triggers:
            parts.append(f"缺少 {len(missing_triggers)} 个不可变触发器")
        if missing_first_version:
            parts.append(f"{len(missing_first_version)} 条观察没有版本行")
        if bad_first_version:
            parts.append(f"{len(bad_first_version)} 条观察的首个版本采集时间≠first_seen_at")
        if bad_status_history:
            parts.append(f"{len(bad_status_history)} 条观察的状态历史缺失或首行时间≠first_seen_at")
        if bad_last_checked:
            parts.append(f"{len(bad_last_checked)} 条观察的 last_checked_at 早于 first_seen_at")
        return _check_result(
            "first_seen_integrity",
            VERDICT_FAIL,
            "first_seen_at 完整性被破坏：" + "；".join(parts) + "。具体 id 见证据。",
            evidence,
        )
    detail = (
        f"{len(facts['observations'])} 条观察的首个版本采集时间与状态历史首行均等于 first_seen_at，"
        f"last_checked_at 均不早于 first_seen_at；{sum(len(v) for v in REQUIRED_TRIGGERS.values())} "
        "个 append-only 触发器全部存在（写入层拒绝改写/删除）。"
    )
    return _check_result("first_seen_integrity", VERDICT_PASS, detail, evidence)


# ------------------------------------------------------------------------ check 3
def _check_version_chain(facts: Mapping[str, Any],
                         con: sqlite3.Connection) -> dict[str, Any]:
    problems: list[dict[str, Any]] = []
    for oid, versions in facts["versions_by_obs"].items():
        observation = facts["observations_by_id"].get(oid)
        if observation is None:
            problems.append({"kind": "orphan_version", "observation_id": oid,
                             "detail": "版本行没有对应的 observation 行"})
            continue
        seqs = [int(version["version_seq"]) for version in versions]
        if seqs != list(range(1, len(seqs) + 1)):
            problems.append(
                {
                    "kind": "version_seq_not_contiguous",
                    "observation_id": oid,
                    "version_seqs": _cap(seqs),
                    "version_seqs_total": len(seqs),
                }
            )
        hashes = [str(version["payload_hash"]) for version in versions]
        if len(set(hashes)) != len(hashes):
            problems.append({"kind": "duplicate_payload_hash", "observation_id": oid})
        if int(observation.get("version_count") or 0) != len(versions):
            problems.append(
                {
                    "kind": "version_count_mismatch",
                    "observation_id": oid,
                    "version_count": observation.get("version_count"),
                    "actual_versions": len(versions),
                }
            )
        latest = versions[-1]
        if observation.get("latest_version_id") != latest["version_id"]:
            problems.append(
                {
                    "kind": "latest_version_pointer_mismatch",
                    "observation_id": oid,
                    "latest_version_id": observation.get("latest_version_id"),
                    "max_seq_version_id": latest["version_id"],
                }
            )
        if observation.get("source_payload_hash") != latest["payload_hash"]:
            problems.append(
                {
                    "kind": "source_payload_hash_mismatch",
                    "observation_id": oid,
                    "source_payload_hash": observation.get("source_payload_hash"),
                    "latest_payload_hash": latest["payload_hash"],
                }
            )

    # Recompute every stored payload hash / version id, streaming (big ledgers safe).
    rehash_mismatches: list[dict[str, Any]] = []
    version_id_mismatches: list[dict[str, Any]] = []
    byte_mismatches: list[dict[str, Any]] = []
    unparseable_payloads: list[dict[str, Any]] = []
    versions_rehashed = 0
    for row in con.execute(
        "SELECT version_id, observation_id, payload_hash, payload, payload_bytes"
        " FROM observation_version"
    ):
        versions_rehashed += 1
        try:
            parsed = json.loads(row["payload"])
        except (TypeError, ValueError):
            unparseable_payloads.append(
                {"version_id": row["version_id"], "observation_id": row["observation_id"]}
            )
            continue
        recomputed = payload_hash(parsed)
        if recomputed != row["payload_hash"]:
            rehash_mismatches.append(
                {
                    "version_id": row["version_id"],
                    "observation_id": row["observation_id"],
                    "stored_payload_hash": row["payload_hash"],
                    "recomputed_payload_hash": recomputed,
                }
            )
        if make_version_id(str(row["observation_id"]), str(row["payload_hash"])) != row["version_id"]:
            version_id_mismatches.append(
                {
                    "version_id": row["version_id"],
                    "observation_id": row["observation_id"],
                    "payload_hash": row["payload_hash"],
                    "recomputed_version_id": make_version_id(
                        str(row["observation_id"]), str(row["payload_hash"])
                    ),
                }
            )
        canonical = canonical_json(parsed)
        canonical_bytes = len(canonical.encode("utf-8"))
        if row["payload_bytes"] is not None and int(row["payload_bytes"]) != canonical_bytes:
            byte_mismatches.append(
                {
                    "version_id": row["version_id"],
                    "observation_id": row["observation_id"],
                    "payload_bytes": row["payload_bytes"],
                    "canonical_bytes": canonical_bytes,
                }
            )

    all_problem_count = (
        len(problems)
        + len(rehash_mismatches)
        + len(version_id_mismatches)
        + len(byte_mismatches)
        + len(unparseable_payloads)
    )
    evidence = {
        "rule": (
            "version_seq 从 1 连续；payload_hash 可由 payload 复算；version_id = sha1(observation_id|payload_hash)；"
            "observation.latest_version_id/ source_payload_hash / version_count 指向最新版本"
        ),
        "observations_checked": len(facts["observations_by_id"]),
        "versions_checked": len(facts["versions"]),
        "payloads_rehashed": versions_rehashed,
        "problem_count": all_problem_count,
        "chain_problems": _cap(problems),
        "chain_problems_total": len(problems),
        "rehash_mismatches": _cap(rehash_mismatches),
        "rehash_mismatches_total": len(rehash_mismatches),
        "version_id_mismatches": _cap(version_id_mismatches),
        "version_id_mismatches_total": len(version_id_mismatches),
        "payload_bytes_mismatches": _cap(byte_mismatches),
        "payload_bytes_mismatches_total": len(byte_mismatches),
        "unparseable_payloads": _cap(unparseable_payloads),
        "unparseable_payloads_total": len(unparseable_payloads),
    }
    if all_problem_count:
        detail = (
            f"版本链存在 {all_problem_count} 处问题：序号/指针/计数不一致 {len(problems)} 处，"
            f"载荷哈希不可复算 {len(rehash_mismatches)} 处，version_id 不可复算 "
            f"{len(version_id_mismatches)} 处，payload_bytes 不等于 canonical 字节数 "
            f"{len(byte_mismatches)} 处，载荷无法解析 {len(unparseable_payloads)} 处。"
        )
        return _check_result("payload_version_chain", VERDICT_FAIL, detail, evidence)
    detail = (
        f"{len(facts['versions'])} 个版本的序号连续、哈希全部可由存储载荷复算、version_id 可由 "
        f"(observation_id, payload_hash) 复算，{len(facts['observations'])} 条观察的 latest_version_id / "
        "source_payload_hash / version_count 与版本表一致。"
    )
    return _check_result("payload_version_chain", VERDICT_PASS, detail, evidence)


# ------------------------------------------------------------------------ check 4
def _load_multi_version_payloads(
    con: sqlite3.Connection, observation_ids: Sequence[str]
) -> dict[str, dict[str, Any]]:
    """Fetch payloads only for observations with more than one version."""
    found: dict[str, dict[str, Any]] = {}
    ids = list(observation_ids)
    for start in range(0, len(ids), 300):
        chunk = ids[start : start + 300]
        placeholders = ",".join("?" for _ in chunk)
        sql = (
            "SELECT version_id, observation_id, version_seq, payload, changed_fields"
            f" FROM observation_version WHERE observation_id IN ({placeholders})"
        )
        for row in con.execute(sql, chunk):
            found[str(row["version_id"])] = dict(row)
    return found


def _check_version_change_consistency(facts: Mapping[str, Any],
                                      con: sqlite3.Connection) -> dict[str, Any]:
    problems: list[dict[str, Any]] = []
    payloads: dict[str, dict[str, Any]] = {}
    multi_version_ids = [
        oid for oid, versions in facts["versions_by_obs"].items() if len(versions) > 1
    ]
    if multi_version_ids:
        payloads = _load_multi_version_payloads(con, multi_version_ids)

    # (a) change rows must reference existing observations / versions, and the
    # REMOVED_OR_UNAVAILABLE / FETCH_FAILED states must not pretend to be versions.
    for change in facts["changes"]:
        oid = str(change["observation_id"])
        if oid not in facts["observations_by_id"]:
            problems.append(
                {"kind": "orphan_change", "change_id": change["change_id"],
                 "observation_id": oid, "change_state": change["change_state"]}
            )
            continue
        state = str(change["change_state"])
        version_ref = change.get("version_id")
        if state in (CHANGE_REMOVED, CHANGE_FETCH_FAILED):
            if version_ref:
                problems.append(
                    {
                        "kind": "non_version_state_has_version_id",
                        "change_id": change["change_id"],
                        "observation_id": oid,
                        "change_state": state,
                        "version_id": version_ref,
                    }
                )
            fields = _parse_changed_fields(change.get("changed_fields"))
            if fields is None:
                problems.append(
                    {"kind": "unparseable_changed_fields", "change_id": change["change_id"],
                     "observation_id": oid, "change_state": state}
                )
            elif state == CHANGE_REMOVED and fields != ["status"]:
                problems.append(
                    {
                        "kind": "removed_without_status_field",
                        "change_id": change["change_id"],
                        "observation_id": oid,
                        "changed_fields": fields,
                    }
                )
    known_version_ids = {
        str(version["version_id"])
        for versions in facts["versions_by_obs"].values()
        for version in versions
    }
    for change in facts["changes"]:
        if change.get("version_id") and str(change["version_id"]) not in known_version_ids:
            problems.append(
                {
                    "kind": "change_references_unknown_version",
                    "change_id": change["change_id"],
                    "observation_id": change["observation_id"],
                    "version_id": change["version_id"],
                }
            )

    # (b) every version must have the right change rows and a real payload diff.
    for oid, versions in facts["versions_by_obs"].items():
        previous_payload: Any = None
        for version in versions:
            version_id = str(version["version_id"])
            seq = int(version["version_seq"])
            references = facts["changes_by_version"].get(version_id) or []
            if not references:
                problems.append(
                    {"kind": "version_without_change_row", "observation_id": oid,
                     "version_id": version_id, "version_seq": seq}
                )
            else:
                expected_state = CHANGE_NEW if seq == 1 else CHANGE_UPDATED
                first = references[0]
                if first["change_state"] != expected_state:
                    problems.append(
                        {
                            "kind": "wrong_change_state_for_version",
                            "observation_id": oid,
                            "version_id": version_id,
                            "version_seq": seq,
                            "expected_change_state": expected_state,
                            "change_state": first["change_state"],
                            "change_id": first["change_id"],
                        }
                    )
                for extra in references[1:]:
                    extra_fields = _parse_changed_fields(extra.get("changed_fields"))
                    if extra["change_state"] != CHANGE_UPDATED or extra_fields != ["status"]:
                        problems.append(
                            {
                                "kind": "unexpected_extra_change_row",
                                "observation_id": oid,
                                "version_id": version_id,
                                "change_id": extra["change_id"],
                                "change_state": extra["change_state"],
                                "changed_fields": extra.get("changed_fields"),
                            }
                        )
            if seq == 1:
                if version.get("change_state") != CHANGE_NEW:
                    problems.append(
                        {
                            "kind": "first_version_not_new",
                            "observation_id": oid,
                            "version_id": version_id,
                            "change_state": version.get("change_state"),
                        }
                    )
                fields = _parse_changed_fields(version.get("changed_fields"))
                if fields is None or fields:
                    problems.append(
                        {
                            "kind": "first_version_has_changed_fields",
                            "observation_id": oid,
                            "version_id": version_id,
                            "changed_fields": version.get("changed_fields"),
                        }
                    )
            else:
                if version.get("change_state") != CHANGE_UPDATED:
                    problems.append(
                        {
                            "kind": "later_version_not_updated",
                            "observation_id": oid,
                            "version_id": version_id,
                            "change_state": version.get("change_state"),
                        }
                    )
                stored = _parse_changed_fields(version.get("changed_fields"))
                payload_row = payloads.get(version_id)
                if payload_row is None:
                    problems.append(
                        {"kind": "missing_payload_for_version", "observation_id": oid,
                         "version_id": version_id}
                    )
                elif stored is None:
                    problems.append(
                        {
                            "kind": "unparseable_changed_fields",
                            "observation_id": oid,
                            "version_id": version_id,
                            "changed_fields": version.get("changed_fields"),
                        }
                    )
                elif not isinstance(previous_payload, Mapping):
                    problems.append(
                        {"kind": "previous_payload_unavailable", "observation_id": oid,
                         "version_id": version_id, "version_seq": seq}
                    )
                else:
                    try:
                        current_payload = json.loads(payload_row["payload"])
                    except (TypeError, ValueError):
                        problems.append(
                            {"kind": "unparseable_payload", "observation_id": oid,
                             "version_id": version_id}
                        )
                        current_payload = None
                    if isinstance(current_payload, Mapping):
                        expected = changed_fields(previous_payload, current_payload)
                        if stored != expected:
                            problems.append(
                                {
                                    "kind": "changed_fields_mismatch",
                                    "observation_id": oid,
                                    "version_id": version_id,
                                    "version_seq": seq,
                                    "stored_changed_fields": stored,
                                    "actual_payload_diff": expected,
                                }
                            )
                        references_first = references[0] if references else None
                        if references_first is not None:
                            change_fields = _parse_changed_fields(
                                references_first.get("changed_fields")
                            )
                            if change_fields is not None and change_fields != expected:
                                problems.append(
                                    {
                                        "kind": "change_changed_fields_mismatch",
                                        "observation_id": oid,
                                        "version_id": version_id,
                                        "change_id": references_first["change_id"],
                                        "change_changed_fields": change_fields,
                                        "actual_payload_diff": expected,
                                    }
                                )
                    else:
                        previous_payload = None
                        continue
            if payloads.get(version_id) is not None:
                try:
                    previous_payload = json.loads(payloads[version_id]["payload"])
                except (TypeError, ValueError):
                    previous_payload = None

    evidence = {
        "rule": (
            "版本 seq=1 的变更行必须 NEW；seq>1 必须 UPDATED；同一版本的额外变更行只允许是"
            ' changed_fields == ["status"] 的恢复行；REMOVED_OR_UNAVAILABLE/FETCH_FAILED 允许'
            " version_id IS NULL 的历史；seq>1 的 changed_fields 必须等于前后两个存档载荷的真实差异"
        ),
        "versions_checked": len(facts["versions"]),
        "changes_checked": len(facts["changes"]),
        "multi_version_observations": len(multi_version_ids),
        "problem_count": len(problems),
        "problems": _cap(problems),
        "problems_truncated": len(problems) > EVIDENCE_LIMIT,
    }
    if problems:
        kinds: dict[str, int] = {}
        for problem in problems:
            kinds[str(problem["kind"])] = kinds.get(str(problem["kind"]), 0) + 1
        detail = (
            f"版本与变更记录存在 {len(problems)} 处不一致："
            + "，".join(f"{kind}×{count}" for kind, count in sorted(kinds.items()))
            + "。具体版本/变更 id 见证据。"
        )
        return _check_result("version_change_consistency", VERDICT_FAIL, detail, evidence)
    detail = (
        f"{len(facts['versions'])} 个版本各自有唯一正确状态的变更行，"
        f"{len(multi_version_ids)} 条多版本观察的 changed_fields 与两版载荷的真实差异完全一致；"
        f"{len(facts['changes'])} 条变更记录没有引用不存在的版本，"
        "REMOVED_OR_UNAVAILABLE / FETCH_FAILED 均为无版本的状态历史。"
    )
    return _check_result("version_change_consistency", VERDICT_PASS, detail, evidence)


# ------------------------------------------------------------------------ check 5
def _check_timestamp_ordering(facts: Mapping[str, Any]) -> dict[str, Any]:
    problems: list[dict[str, Any]] = []
    versions_checked = 0
    changes_checked = 0
    status_rows_checked = 0
    for oid, versions in facts["versions_by_obs"].items():
        observation = facts["observations_by_id"].get(oid)
        if observation is None:
            continue
        first_seen = observation.get("first_seen_at")
        previous_captured: Any = None
        for version in versions:
            versions_checked += 1
            captured = version.get("captured_at")
            if _parse(captured) is None:
                problems.append(
                    {"kind": "unparseable_captured_at", "observation_id": oid,
                     "version_id": version["version_id"], "captured_at": captured}
                )
            if not _le(first_seen, captured):
                problems.append(
                    {
                        "kind": "version_before_first_seen",
                        "observation_id": oid,
                        "version_id": version["version_id"],
                        "first_seen_at": first_seen,
                        "captured_at": captured,
                    }
                )
            if previous_captured is not None and not _le(previous_captured, captured):
                problems.append(
                    {
                        "kind": "captured_at_not_monotonic",
                        "observation_id": oid,
                        "version_id": version["version_id"],
                        "previous_captured_at": previous_captured,
                        "captured_at": captured,
                    }
                )
            previous_captured = captured
    for oid, changes in facts["changes_by_obs"].items():
        observation = facts["observations_by_id"].get(oid)
        first_seen = observation.get("first_seen_at") if observation else None
        for change in changes:
            changes_checked += 1
            observed = change.get("observed_at")
            if _parse(observed) is None:
                problems.append(
                    {"kind": "unparseable_observed_at", "change_id": change["change_id"],
                     "observation_id": oid, "observed_at": observed}
                )
            if not _same_moment(change.get("first_seen_at"), first_seen):
                problems.append(
                    {
                        "kind": "change_first_seen_at_mismatch",
                        "change_id": change["change_id"],
                        "observation_id": oid,
                        "change_first_seen_at": change.get("first_seen_at"),
                        "observation_first_seen_at": first_seen,
                    }
                )
            if not _le(first_seen, observed):
                problems.append(
                    {
                        "kind": "change_before_first_seen",
                        "change_id": change["change_id"],
                        "observation_id": oid,
                        "first_seen_at": first_seen,
                        "observed_at": observed,
                    }
                )
    for oid, history in facts["status_by_obs"].items():
        observation = facts["observations_by_id"].get(oid)
        first_seen = observation.get("first_seen_at") if observation else None
        for row in history:
            status_rows_checked += 1
            if not _le(first_seen, row.get("changed_at")):
                problems.append(
                    {
                        "kind": "status_change_before_first_seen",
                        "observation_id": oid,
                        "first_seen_at": first_seen,
                        "status_changed_at": row.get("changed_at"),
                    }
                )
    evidence = {
        "rule": (
            "同一观察的 captured_at 随 version_seq 单调不减且 >= first_seen_at；"
            "change.observed_at >= first_seen_at 且 change.first_seen_at == observation.first_seen_at；"
            "状态历史 changed_at >= first_seen_at"
        ),
        "versions_checked": versions_checked,
        "changes_checked": changes_checked,
        "status_rows_checked": status_rows_checked,
        "problem_count": len(problems),
        "problems": _cap(problems),
        "problems_truncated": len(problems) > EVIDENCE_LIMIT,
    }
    if problems:
        return _check_result(
            "timestamp_ordering",
            VERDICT_FAIL,
            f"时间戳顺序存在 {len(problems)} 处违反（版本 {versions_checked} 条、变更 "
            f"{changes_checked} 条、状态历史 {status_rows_checked} 条）；具体 id 见证据。",
            evidence,
        )
    detail = (
        f"已检查 {versions_checked} 个版本的 captured_at 单调性、{changes_checked} 条变更的 "
        f"observed_at 与 first_seen_at、{status_rows_checked} 条状态历史；没有任何时间倒挂。"
    )
    return _check_result("timestamp_ordering", VERDICT_PASS, detail, evidence)


# ------------------------------------------------------------------------ check 6
def _check_watermark_safety(facts: Mapping[str, Any]) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    manual_review: list[dict[str, Any]] = []
    sources_checked = 0
    runs_checked = 0
    failed_runs_by_source: dict[str, list[dict[str, Any]]] = {}
    for run in facts["runs"]:
        runs_checked += 1
        if run.get("status") in (RUN_FAILED, RUN_PARTIAL):
            failed_runs_by_source.setdefault(str(run["source"]), []).append(run)
    flagged_runs: set[str] = set()

    for source in facts["sources"]:
        sources_checked += 1
        name = str(source["source"])
        watermark_text = source.get("watermark")
        if watermark_text not in (None, ""):
            try:
                json.loads(str(watermark_text))
            except (TypeError, ValueError):
                failures.append(
                    {
                        "source": name,
                        "issue": "watermark_unparseable",
                        "watermark": _bounded_text(watermark_text),
                    }
                )
        last_success = source.get("last_success_at")
        watermark_updated = source.get("watermark_updated_at")
        if last_success and watermark_updated:
            if _parse(last_success) is None or _parse(watermark_updated) is None:
                failures.append(
                    {
                        "source": name,
                        "issue": "watermark_timestamps_unparseable",
                        "last_success_at": last_success,
                        "watermark_updated_at": watermark_updated,
                    }
                )
            elif not _le(watermark_updated, last_success):
                explaining = [
                    run for run in failed_runs_by_source.get(name, [])
                    if _lt(last_success, run.get("started_at"))
                ]
                if explaining:
                    # A failed run explains the advance; which pages it completed is
                    # not provable from the ledger -> human review, not PASS.
                    manual_review.append(
                        {
                            "source": name,
                            "issue": "watermark_advanced_by_newer_failed_run",
                            "watermark_updated_at": watermark_updated,
                            "last_success_at": last_success,
                            "run_ids": _cap(
                                [str(run["run_id"]) for run in explaining], 10
                            ),
                        }
                    )
                    flagged_runs.update(str(run["run_id"]) for run in explaining)
                else:
                    failures.append(
                        {
                            "source": name,
                            "issue": "watermark_newer_than_last_success",
                            "watermark_updated_at": watermark_updated,
                            "last_success_at": last_success,
                        }
                    )
        # A FAILED/PARTIAL run that moved the watermark forward is the risky case
        # the design calls out: the audit cannot prove the skipped pages were read.
        for run in failed_runs_by_source.get(name, []):
            run_id = str(run["run_id"])
            if run_id in flagged_runs:
                continue
            after = run.get("watermark_after")
            before = run.get("watermark_before")
            if after is None or after == before:
                continue
            flagged_runs.add(run_id)
            manual_review.append(
                {
                    "source": name,
                    "issue": "failed_run_advanced_watermark",
                    "run_id": run_id,
                    "status": run.get("status"),
                    "watermark_before": _bounded_text(before, 120),
                    "watermark_after": _bounded_text(after, 120),
                }
            )

    evidence = {
        "rule": (
            "source_state.watermark 必须是可解析 JSON；watermark_updated_at <= last_success_at；"
            "FAILED/PARTIAL 运行推进过水位时，本次运行实际完成的范围不可证明 -> 人工复核"
        ),
        "sources_checked": sources_checked,
        "runs_checked": runs_checked,
        "watermark_parse_failures": len(failures),
        "manual_review_triggers": len(manual_review),
        "failures": _cap(failures),
        "manual_review": _cap(manual_review),
        "flagged_run_ids": _cap(sorted(flagged_runs), 40),
    }
    if failures:
        return _check_result(
            "watermark_safety",
            VERDICT_FAIL,
            f"水位安全性有 {len(failures)} 处被证伪（水位不可解析或由无法归因的运行推进），"
            f"另有 {len(manual_review)} 处需要人工复核；具体来源/运行 id 见证据。",
            evidence,
        )
    if manual_review:
        return _check_result(
            "watermark_safety",
            VERDICT_MANUAL,
            f"{len(manual_review)} 处水位由 FAILED/PARTIAL 运行推进过（运行 id 见证据）："
            "账本无法证明这些失败运行实际完成的分页范围，因此不能声称水位对应的数据已完整采集，需人工复核。",
            evidence,
        )
    detail = (
        f"{sources_checked} 个来源的水位 JSON 均可解析；watermark_updated_at 均不晚于 last_success_at；"
        f"{runs_checked} 次运行中没有 FAILED/PARTIAL 运行推进过水位。"
    )
    return _check_result("watermark_safety", VERDICT_PASS, detail, evidence)


# ------------------------------------------------------------------------ check 7
def _check_replay_correctness(ledger: Any, facts: Mapping[str, Any],
                              sample_size: int) -> dict[str, Any]:
    candidates = sorted(
        oid for oid, versions in facts["versions_by_obs"].items() if len(versions) > 1
    )
    sampled: list[str] = []
    if candidates and sample_size > 0:
        if len(candidates) <= sample_size:
            sampled = candidates
        else:
            sampled = [
                candidates[(index * len(candidates)) // sample_size]
                for index in range(sample_size)
            ]
    problems: list[dict[str, Any]] = []
    snapshot_cache: dict[tuple[str, str], dict[str, Any]] = {}

    def snapshot(as_of: str, source: str) -> dict[str, Any]:
        key = (as_of, source)
        cached = snapshot_cache.get(key)
        if cached is None:
            cached = ledger.snapshot(as_of, source=source)
            snapshot_cache[key] = cached
        return cached

    for oid in sampled:
        observation = facts["observations_by_id"][oid]
        source = str(observation["source"])
        versions = facts["versions_by_obs"][oid]
        first_version = versions[0]
        first_boundary = _canonical_boundary(first_version["captured_at"])
        try:
            early = snapshot(first_boundary, source)
        except (ValueError, sqlite3.Error) as exc:
            problems.append(
                {"kind": "snapshot_error", "observation_id": oid,
                 "as_of": first_boundary, "error": _bounded_text(exc, 160)}
            )
            continue
        item = next(
            (row for row in early["items"] if str(row["observation_id"]) == oid), None
        )
        if item is None:
            problems.append(
                {
                    "kind": "snapshot_missing_first_version",
                    "observation_id": oid,
                    "as_of": first_boundary,
                    "first_version_id": first_version["version_id"],
                }
            )
        else:
            if item.get("version_id") != first_version["version_id"]:
                problems.append(
                    {
                        "kind": "snapshot_returned_wrong_version",
                        "observation_id": oid,
                        "as_of": first_boundary,
                        "expected_version_id": first_version["version_id"],
                        "actual_version_id": item.get("version_id"),
                    }
                )
            payload = item.get("payload")
            if isinstance(payload, Mapping):
                historical_hash = payload_hash(payload)
                if historical_hash != first_version["payload_hash"]:
                    problems.append(
                        {
                            "kind": "historical_payload_hash_mismatch",
                            "observation_id": oid,
                            "version_id": first_version["version_id"],
                            "expected_payload_hash": first_version["payload_hash"],
                            "recomputed_payload_hash": historical_hash,
                        }
                    )
        # Nothing may leak into a replay taken before the record was first seen.
        try:
            before_as_of = _before(observation["first_seen_at"], seconds=1)
            before = snapshot(before_as_of, source)
            leaked = next(
                (row for row in before["items"] if str(row["observation_id"]) == oid), None
            )
            if leaked is not None:
                problems.append(
                    {
                        "kind": "leaked_before_first_seen",
                        "observation_id": oid,
                        "as_of": before_as_of,
                        "first_seen_at": observation["first_seen_at"],
                    }
                )
        except (ValueError, sqlite3.Error) as exc:
            problems.append(
                {"kind": "snapshot_error", "observation_id": oid,
                 "error": _bounded_text(exc, 160)}
            )
        # Every distinct captured_at instant replays the newest version captured
        # at it (instants are compared as parsed datetimes, never as spellings).
        expected_by_captured: dict[str, dict[str, Any]] = {}
        for version in versions:
            expected_by_captured[_canonical_boundary(version["captured_at"])] = version
        for captured_boundary, expected in expected_by_captured.items():
            try:
                replay = snapshot(captured_boundary, source)
            except (ValueError, sqlite3.Error) as exc:
                problems.append(
                    {"kind": "snapshot_error", "observation_id": oid,
                     "as_of": captured_boundary, "error": _bounded_text(exc, 160)}
                )
                continue
            replayed = next(
                (row for row in replay["items"] if str(row["observation_id"]) == oid), None
            )
            if replayed is None or replayed.get("version_id") != expected["version_id"]:
                problems.append(
                    {
                        "kind": "snapshot_version_at_captured_at_mismatch",
                        "observation_id": oid,
                        "as_of": captured_boundary,
                        "expected_version_id": expected["version_id"],
                        "actual_version_id": None if replayed is None else replayed.get("version_id"),
                    }
                )

    # Supplementary boundary probe: only meaningful when nothing could be sampled.
    probe = {"sampled": 0, "missing_first_seen_boundary": [], "missing_total": 0}
    if not sampled:
        singles = sorted(
            oid for oid, versions in facts["versions_by_obs"].items() if len(versions) == 1
        )
        probe_ids = singles[: max(0, sample_size)] if sample_size > 0 else []
        missing: list[str] = []
        for oid in probe_ids:
            observation = facts["observations_by_id"][oid]
            try:
                snapshot_rows = ledger.snapshot(
                    _canonical_boundary(observation["first_seen_at"]),
                    source=str(observation["source"]),
                )
            except (ValueError, sqlite3.Error):
                continue
            found = any(
                str(row["observation_id"]) == oid for row in snapshot_rows["items"]
            )
            if not found:
                missing.append(oid)
        probe = {
            "sampled": len(probe_ids),
            "missing_first_seen_boundary": _cap(missing),
            "missing_total": len(missing),
            "rule": (
                "补充诊断（不属于本检查的判定规则）：对单版本观察执行 "
                "snapshot(first_seen_at) 时，该记录是否仍然出现在结果中"
            ),
        }

    evidence = {
        "rule": (
            "sample_size 内确定性抽样 version_count>1 的观察：snapshot(v1.captured_at) 必须返回 v1；"
            "snapshot(first_seen_at - 1s) 必须排除该记录；每个不同 captured_at 必须回放当时最新的版本；"
            "回放出的 payload 必须能用 records.payload_hash 复算出该版本的 payload_hash"
        ),
        "boundary_policy": (
            "所有 snapshot(as_of) 边界都由解析后的 UTC 时间生成（…+00:00），"
            "从不直接使用存储字符串的 'Z' / '+00:00' 拼写做比较"
        ),
        "sample_size": int(sample_size),
        "multi_version_observations": len(candidates),
        "sampled_observation_ids": sampled,
        "problems": _cap(problems),
        "problem_count": len(problems),
        "boundary_probe": probe,
    }
    if problems:
        return _check_result(
            "replay_correctness",
            VERDICT_FAIL,
            f"抽样回放 {len(sampled)} 条多版本观察发现 {len(problems)} 处不一致："
            "snapshot 在历史时点返回了错误的版本、缺失首版、或在首次观察之前就泄漏了该记录。具体 id 见证据。",
            evidence,
        )
    if not candidates:
        detail = (
            "账本中没有任何 version_count>1 的观察，因此无法抽样验证多版本回放；"
            "按诚实规则本项标记为人工复核，而不是默认通过。"
        )
        if probe["missing_total"]:
            detail += (
                f" 补充诊断：抽样 {probe['sampled']} 条单版本观察，其中 "
                f"{probe['missing_total']} 条在 snapshot(first_seen_at) 时点未被返回"
                "（同一秒的回放边界异常），该边界语义需人工判定。"
            )
        elif probe["sampled"]:
            detail += (
                f" 补充诊断：抽样 {probe['sampled']} 条单版本观察，"
                "snapshot(first_seen_at) 均能返回该记录（Z / +00:00 拼写不影响回放边界）。"
            )
        return _check_result("replay_correctness", VERDICT_MANUAL, detail, evidence)
    if not sampled:
        return _check_result(
            "replay_correctness",
            VERDICT_MANUAL,
            "sample_size <= 0，本次没有抽取任何多版本观察进行回放验证。",
            evidence,
        )
    detail = (
        f"抽样回放 {len(sampled)} 条多版本观察：snapshot(v1.captured_at) 均返回 v1 且历史载荷哈希可复算；"
        "first_seen_at 之前的时点均正确排除该记录；每个 captured_at 均回放当时最新的版本。"
    )
    return _check_result("replay_correctness", VERDICT_PASS, detail, evidence)


# ------------------------------------------------------------------------ check 8
def _check_prospective_freeze(include_prospective: bool) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "rule": "对登记器里的每个条目调用 verify_frozen()；空登记器 -> 人工复核；哈希不一致 -> FAIL",
    }
    if not include_prospective:
        evidence["included"] = False
        return _check_result(
            "prospective_freeze_integrity",
            VERDICT_MANUAL,
            "本次审计显式跳过前瞻登记器校验（include_prospective=False），冻结完整性没有被验证，不能视为通过。",
            evidence,
        )
    try:
        registry_dir = prospective.default_registry_dir()
        registry = prospective.open_registry(registry_dir)
    except Exception as exc:  # noqa: BLE001 - a broken registry must not crash the audit
        evidence["error"] = _bounded_text(exc, 200)
        return _check_result(
            "prospective_freeze_integrity",
            VERDICT_MANUAL,
            f"无法打开前瞻登记器：{_bounded_text(exc, 160)}；冻结完整性无法验证。",
            evidence,
        )
    evidence["included"] = True
    evidence["registry_path"] = _display_path(registry_dir)
    evidence["registry_exists"] = bool(registry.exists)
    if not registry.exists:
        return _check_result(
            "prospective_freeze_integrity",
            VERDICT_MANUAL,
            "前瞻登记器目录不存在：没有任何冻结的研究输入可供验证。缺少证据不是 PASS。",
            evidence,
        )
    try:
        entries = registry.list_entries()
    except Exception as exc:  # noqa: BLE001
        evidence["error"] = _bounded_text(exc, 200)
        return _check_result(
            "prospective_freeze_integrity",
            VERDICT_MANUAL,
            f"无法列出前瞻登记器条目：{_bounded_text(exc, 160)}；冻结完整性无法验证。",
            evidence,
        )
    evidence["entry_count"] = len(entries)
    evidence["synthetic_entry_count"] = sum(1 for entry in entries if entry.get("synthetic"))
    if not entries:
        return _check_result(
            "prospective_freeze_integrity",
            VERDICT_MANUAL,
            "前瞻登记器中没有冻结条目（no frozen research input to verify）：机制未被真实研究输入使用，"
            "冻结完整性无法证明。缺少证据不是 PASS。",
            evidence,
        )
    verified: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for entry in entries:
        entry_id = str(entry.get("entry_id") or entry.get("id") or "")
        try:
            verification = registry.verify_frozen(entry_id)
        except Exception as exc:  # noqa: BLE001 - corrupt/unreadable frozen file
            failures.append(
                {
                    "entry_id": entry_id,
                    "issue": "verify_frozen_failed",
                    "error": _bounded_text(exc, 200),
                    "synthetic": bool(entry.get("synthetic")),
                }
            )
            continue
        if verification.get("ok"):
            verified.append(
                {
                    "entry_id": entry_id,
                    "content_sha256": verification.get("content_sha256"),
                    "synthetic": bool(entry.get("synthetic")),
                }
            )
        else:
            failures.append(
                {
                    "entry_id": entry_id,
                    "issue": "frozen_document_tampered",
                    "stored_sha256": verification.get("content_sha256"),
                    "recomputed_sha256": verification.get("recomputed_sha256"),
                    "evidence_sha256_ok": verification.get("evidence_sha256_ok"),
                    "reason_zh": verification.get("reason_zh"),
                    "synthetic": bool(entry.get("synthetic")),
                }
            )
    evidence["verified_entries"] = _cap(verified)
    evidence["verified_total"] = len(verified)
    evidence["failures"] = _cap(failures)
    evidence["failures_total"] = len(failures)
    if failures:
        return _check_result(
            "prospective_freeze_integrity",
            VERDICT_FAIL,
            f"{len(failures)} 条冻结文档无法通过哈希复验（疑似被改写或损坏）："
            + "，".join(str(item["entry_id"]) for item in failures[:5])
            + "。冻结正文一旦被改写，基于它的前瞻结论就不成立。",
            evidence,
        )
    synthetic_note = (
        f"（其中 {evidence['synthetic_entry_count']} 条为合成测试条目，不属于真实研究输入）"
        if evidence["synthetic_entry_count"]
        else ""
    )
    detail = (
        f"{len(verified)} 条冻结文档全部通过 verify_frozen：正文哈希与登记内容一致、冻结证据块哈希一致"
        f"{synthetic_note}。"
    )
    return _check_result("prospective_freeze_integrity", VERDICT_PASS, detail, evidence)


# ------------------------------------------------------------------------ check 9
def _check_mapping_history(ledger: Any, facts: Mapping[str, Any],
                           con: sqlite3.Connection) -> dict[str, Any]:
    missing = [
        oid for oid in facts["observations_by_id"] if oid not in facts["mappings_by_obs"]
    ]
    history_rows = 0
    vocabulary_problems: list[dict[str, Any]] = []
    for oid, mapping_rows in facts["mappings_by_obs"].items():
        history_rows += len(mapping_rows)
        for row in mapping_rows:
            if row.get("entity_status") not in ENTITY_STATUSES:
                vocabulary_problems.append(
                    {"observation_id": oid, "mapped_at": row.get("mapped_at"),
                     "issue": "invalid_entity_status", "value": row.get("entity_status")}
                )
            if row.get("track_status") not in TRACK_STATUSES:
                vocabulary_problems.append(
                    {"observation_id": oid, "mapped_at": row.get("mapped_at"),
                     "issue": "invalid_track_status", "value": row.get("track_status")}
                )
            if row.get("entity_status") == ENTITY_MAPPED and not row.get("entity_id"):
                vocabulary_problems.append(
                    {"observation_id": oid, "mapped_at": row.get("mapped_at"),
                     "issue": "mapped_entity_without_entity_id"}
                )
            if row.get("track_status") == TRACK_MAPPED and not row.get("track_id"):
                vocabulary_problems.append(
                    {"observation_id": oid, "mapped_at": row.get("mapped_at"),
                     "issue": "mapped_track_without_track_id"}
                )

    # Compare the latest append-only mapping row with the view the observation
    # endpoints return (same JOIN fragment the product layer uses).
    join, params = ledger.current_mapping_sql("o")
    endpoint_rows = [
        dict(row)
        for row in con.execute(
            "SELECT o.observation_id AS observation_id, m.entity_id, m.entity_status,"
            " m.entity_method, m.entity_confidence, m.track_id, m.track_status,"
            " m.track_method, m.note_zh, m.mapped_at"
            f" FROM observation o{join}",
            params,
        ).fetchall()
    ]
    endpoint_by_obs = {str(row["observation_id"]): row for row in endpoint_rows}
    compared_fields = (
        "entity_id",
        "entity_status",
        "entity_method",
        "entity_confidence",
        "track_id",
        "track_status",
        "track_method",
        "note_zh",
    )
    endpoint_mismatches: list[dict[str, Any]] = []
    for oid, mapping_rows in facts["mappings_by_obs"].items():
        latest = mapping_rows[-1]
        endpoint = endpoint_by_obs.get(oid)
        if endpoint is None:
            endpoint_mismatches.append({"observation_id": oid, "issue": "endpoint_has_no_mapping"})
            continue
        for field in compared_fields:
            if endpoint.get(field) != latest.get(field):
                endpoint_mismatches.append(
                    {
                        "observation_id": oid,
                        "issue": "latest_mapping_row_differs_from_endpoint",
                        "field": field,
                        "endpoint_value": _bounded_text(endpoint.get(field), 120),
                        "latest_mapping_value": _bounded_text(latest.get(field), 120),
                    }
                )
    evidence = {
        "rule": (
            "每条观察至少有 1 条 observation_mapping；映射状态必须属于封闭词表；"
            "MAPPED 必须有 id；最新映射行（MAX(mapped_at)）必须与观察接口返回的映射字段完全一致"
        ),
        "observations_checked": len(facts["observations_by_id"]),
        "mapping_rows": history_rows,
        "observations_without_mapping": _cap(missing),
        "observations_without_mapping_total": len(missing),
        "vocabulary_problems": _cap(vocabulary_problems),
        "vocabulary_problems_total": len(vocabulary_problems),
        "endpoint_mismatches": _cap(endpoint_mismatches),
        "endpoint_mismatches_total": len(endpoint_mismatches),
    }
    problem_count = len(missing) + len(vocabulary_problems) + len(endpoint_mismatches)
    if problem_count:
        return _check_result(
            "mapping_history_preservation",
            VERDICT_FAIL,
            f"映射历史留存存在 {problem_count} 处问题：{len(missing)} 条观察完全没有映射历史，"
            f"{len(vocabulary_problems)} 条映射记录违反状态词表，"
            f"{len(endpoint_mismatches)} 处最新映射行与接口返回不一致。具体 id 见证据。",
            evidence,
        )
    detail = (
        f"{len(facts['observations_by_id'])} 条观察都有映射历史（共 {history_rows} 行，append-only），"
        "最新映射行与观察接口返回的映射字段完全一致，状态词表合法。"
    )
    return _check_result("mapping_history_preservation", VERDICT_PASS, detail, evidence)


# ----------------------------------------------------------------------- check 10
def _manifest_first_of(manifest: Mapping[str, Any], keys: Sequence[str]) -> Any:
    """Find a recorded fact at the top level or in a known nested block."""
    for node in _manifest_nested_dicts(manifest):
        for key in keys:
            value = node.get(key)
            if value is not None:
                return value
    return None


def _manifest_nested_dicts(manifest: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    nodes: list[Mapping[str, Any]] = [manifest]
    for key in (
        "counts",
        "ledger_counts",
        "ledger",
        "first_seen_at",
        "first_seen",
        "meta",
        "restore_verification",
        "version_chain",
        "source_watermarks",
        "per_source_observation_counts",
    ):
        value = manifest.get(key)
        if isinstance(value, Mapping):
            nodes.append(value)
    return nodes


def _manifest_count(manifest: Mapping[str, Any], aliases: Sequence[str]) -> int | None:
    for node in _manifest_nested_dicts(manifest):
        for alias in aliases:
            value = node.get(alias)
            if isinstance(value, bool):
                continue
            if isinstance(value, int):
                return int(value)
            if isinstance(value, str) and value.strip().lstrip("-").isdigit():
                return int(value)
    return None


def _manifest_window(manifest: Mapping[str, Any]) -> tuple[Any, Any] | None:
    for node in _manifest_nested_dicts(manifest):
        for minimum, maximum in (
            ("min", "max"),
            ("first", "last"),
            ("earliest", "latest"),
            ("first_seen_at_min", "first_seen_at_max"),
            ("first_seen_min", "first_seen_max"),
            ("min_first_seen_at", "max_first_seen_at"),
            ("first_observation_at", "last_observation_at"),
        ):
            if node.get(minimum) is not None and node.get(maximum) is not None:
                return node.get(minimum), node.get(maximum)
    return None


def _manifest_source_counts(manifest: Mapping[str, Any]) -> dict[str, int] | None:
    for node in _manifest_nested_dicts(manifest):
        for key in (
            "sources",
            "source_counts",
            "per_source",
            "source_observation_counts",
            "per_source_observation_counts",
        ):
            value = node.get(key)
            if value is None:
                continue
            found: dict[str, int] = {}
            if isinstance(value, Mapping):
                for source, entry in value.items():
                    if isinstance(entry, Mapping):
                        for alias in ("observations", "count", "n", "observation_count", "records"):
                            if isinstance(entry.get(alias), int):
                                found[str(source)] = int(entry[alias])
                                break
                    elif isinstance(entry, int) and not isinstance(entry, bool):
                        found[str(source)] = int(entry)
            elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                for entry in value:
                    if not isinstance(entry, Mapping):
                        continue
                    source = entry.get("source") or entry.get("source_id")
                    if not source:
                        continue
                    for alias in ("observations", "count", "n", "observation_count", "records"):
                        if isinstance(entry.get(alias), int):
                            found[str(source)] = int(entry[alias])
                            break
            if found:
                return found
    return None


def _manifest_watermarks(manifest: Mapping[str, Any]) -> dict[str, Any] | None:
    for node in _manifest_nested_dicts(manifest):
        for key in ("watermarks", "source_watermarks"):
            value = node.get(key)
            if isinstance(value, Mapping):
                found: dict[str, Any] = {}
                for source, entry in value.items():
                    if isinstance(entry, Mapping):
                        # A backup manifest stores per-source metadata; only the
                        # watermark value itself is comparable with source_state.
                        found[str(source)] = entry.get("watermark", entry)
                    else:
                        found[str(source)] = entry
                return found
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                found = {}
                for entry in value:
                    if isinstance(entry, Mapping) and entry.get("source"):
                        found[str(entry["source"])] = entry.get("watermark")
                if found:
                    return found
    return None


def _bundle_ledger_problems(manifest_path: Path,
                            manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Verify the copied ``ledger.sqlite`` artifact hash/size, if the bundle has it.

    Full artifact verification stays in ``observatory backup verify``; the audit
    re-hashes the one artifact that matters for reproducibility.
    """
    problems: list[dict[str, Any]] = []
    artifacts = manifest.get("artifacts")
    ledger_block = manifest.get("ledger") if isinstance(manifest.get("ledger"), Mapping) else {}
    ledger_name = str(ledger_block.get("file") or "ledger.sqlite")
    if isinstance(artifacts, Sequence) and not isinstance(artifacts, (str, bytes)):
        entry = next(
            (
                item
                for item in artifacts
                if isinstance(item, Mapping)
                and (item.get("path") in (ledger_name, "ledger.sqlite")
                     or str(item.get("path", "")).endswith("ledger.sqlite"))
            ),
            None,
        )
    else:
        entry = None
    if entry is None:
        if ledger_block:
            # Some manifests record the ledger hash under ledger{} only.
            if ledger_block.get("sha256") and ledger_block.get("bytes"):
                entry = {
                    "path": ledger_name,
                    "sha256": ledger_block.get("sha256"),
                    "bytes": ledger_block.get("bytes"),
                }
            else:
                return problems
        else:
            return problems
    bundle_dir = manifest_path.parent
    artifact_path = bundle_dir / str(entry.get("path") or ledger_name)
    if not artifact_path.is_file():
        problems.append(
            {
                "kind": "bundle_ledger_missing",
                "artifact": str(entry.get("path") or ledger_name),
                "bundle": _display_path(bundle_dir),
            }
        )
        return problems
    expected_sha = str(entry.get("sha256") or "")
    expected_bytes = entry.get("bytes")
    digest = hashlib.sha256()
    actual_bytes = 0
    try:
        with open(artifact_path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
                actual_bytes += len(chunk)
    except OSError as exc:
        problems.append(
            {"kind": "bundle_ledger_unreadable",
             "artifact": str(entry.get("path") or ledger_name),
             "error": _bounded_text(exc, 160)}
        )
        return problems
    actual_sha = digest.hexdigest()
    if expected_bytes is not None and int(expected_bytes) != actual_bytes:
        problems.append(
            {
                "kind": "bundle_ledger_size_mismatch",
                "artifact": str(entry.get("path") or ledger_name),
                "manifest_bytes": int(expected_bytes),
                "actual_bytes": actual_bytes,
            }
        )
    if expected_sha and expected_sha != actual_sha:
        problems.append(
            {
                "kind": "bundle_ledger_sha256_mismatch",
                "artifact": str(entry.get("path") or ledger_name),
                "manifest_sha256": expected_sha,
                "actual_sha256": actual_sha,
            }
        )
    return problems


def _canonical_jsonish(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return canonical_json(json.loads(value))
        except (TypeError, ValueError):
            return canonical_json(value)
    return canonical_json(value)


def _backup_bundle_manifest(
    ledger_path: Path, backup_manifest_path: str | Path | None
) -> tuple[Path | None, dict[str, Any] | None, str, list[str]]:
    """Return ``(manifest_path, manifest, origin, notes)`` without ever writing."""
    notes: list[str] = []
    if backup_manifest_path is not None:
        candidate = Path(backup_manifest_path).expanduser()
        if candidate.is_dir():
            candidate = candidate / "MANIFEST.json"
        if not candidate.is_file():
            notes.append(f"指定的备份清单不存在：{_display_path(candidate)}")
            return None, None, "supplied", notes
        try:
            manifest = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            notes.append(f"指定的备份清单无法解析：{_bounded_text(exc, 200)}")
            return candidate, None, "supplied", notes
        if not isinstance(manifest, dict):
            notes.append("指定的备份清单不是 JSON 对象")
            return candidate, None, "supplied", notes
        return candidate, manifest, "supplied", notes

    candidates: list[Path] = []
    bundle_roots = [Path(ledger_path).parent / "backups"]
    for root in bundle_roots:
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir(), key=lambda item: item.name):
            if child.is_dir() and (child / "MANIFEST.json").is_file():
                candidates.append(child / "MANIFEST.json")
        if (root / "MANIFEST.json").is_file():
            candidates.append(root / "MANIFEST.json")
    if not candidates:
        notes.append(
            "未找到备份清单：检查目录 " + "，".join(_display_path(root) for root in bundle_roots)
        )
        return None, None, "discovered", notes
    newest = max(candidates, key=lambda path: (path.stat().st_mtime, str(path)))
    try:
        manifest = json.loads(newest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        notes.append(f"备份清单无法解析：{_display_path(newest)}（{_bounded_text(exc, 160)}）")
        return newest, None, "discovered", notes
    if not isinstance(manifest, dict):
        notes.append(f"备份清单不是 JSON 对象：{_display_path(newest)}")
        return newest, None, "discovered", notes
    return newest, manifest, "discovered", notes


def _check_backup_restore(ledger: Any, facts: Mapping[str, Any], ledger_path: Path,
                          backup_manifest_path: str | Path | None) -> dict[str, Any]:
    manifest_path, manifest, origin, notes = _backup_bundle_manifest(
        ledger_path, backup_manifest_path
    )
    live_counts = {
        "observations": len(facts["observations"]),
        "versions": len(facts["versions"]),
        "changes": len(facts["changes"]),
        "runs": len(facts["runs"]),
    }
    live_first_seen = sorted(
        (str(observation["first_seen_at"]) for observation in facts["observations"]),
        key=lambda value: (_parse(value) or datetime.min.replace(tzinfo=timezone.utc), value),
    )
    live_min = live_first_seen[0] if live_first_seen else None
    live_max = live_first_seen[-1] if live_first_seen else None
    evidence: dict[str, Any] = {
        "rule": (
            "备份清单必须来自本账本的备份：当清单创建时间不早于账本最后一次写入时，"
            "计数、first_seen_at 最小/最大值、来源分布必须逐项一致（不一致 = FAIL）；"
            "清单早于最新写入时只能验证一致前缀（人工复核）；没有清单/演练证据 -> 人工复核"
        ),
        "manifest_origin": origin,
        "manifest_path": _display_path(manifest_path) if manifest_path else None,
        "notes": notes,
        "live": {
            "counts": live_counts,
            "first_seen_min": live_min,
            "first_seen_max": live_max,
            "source_counts": dict(sorted(facts["source_counts"].items())),
        },
    }
    if manifest is None:
        recorded_backup = ledger.get_runtime("last_backup", None)
        recorded_drill = ledger.get_runtime("last_restore_drill", None)
        evidence["recorded_last_backup"] = recorded_backup
        evidence["recorded_last_restore_drill"] = recorded_drill
        return _check_result(
            "backup_restore_reproducibility",
            VERDICT_MANUAL,
            "没有可核对的备份清单（也没有可读取的 MANIFEST.json）：无法证明当前账本可从备份恢复。"
            "缺少备份/演练证据按诚实规则标记人工复核，绝不默认通过。",
            evidence,
        )

    evidence["manifest_created_at"] = _manifest_first_of(
        manifest, ("created_at", "generated_at", "at", "timestamp", "frozen_recorded_at")
    )
    integrity_check = _manifest_first_of(manifest, ("integrity_check", "integrity", "pragma_integrity_check"))
    consistency_ok = _manifest_first_of(manifest, ("consistency_ok", "consistent"))
    if integrity_check is not None:
        evidence["manifest_integrity_check"] = _bounded_text(integrity_check, 120)
    if consistency_ok is not None:
        evidence["manifest_consistency_ok"] = bool(consistency_ok)

    mismatches: list[dict[str, Any]] = []
    compared: list[str] = []
    manifest_counts = {
        "observations": _manifest_count(manifest, ("observations", "observation", "observation_count")),
        "versions": _manifest_count(manifest, ("versions", "version", "version_count", "observation_versions")),
        "changes": _manifest_count(manifest, ("changes", "change", "change_count", "observation_changes")),
        "runs": _manifest_count(manifest, ("runs", "run", "sync_runs", "run_count")),
    }
    for dimension, expected in manifest_counts.items():
        if expected is None:
            continue
        compared.append(f"counts.{dimension}")
        if expected != live_counts[dimension]:
            mismatches.append(
                {
                    "dimension": f"counts.{dimension}",
                    "manifest": expected,
                    "live": live_counts[dimension],
                    "difference": live_counts[dimension] - expected,
                }
            )
    window = _manifest_window(manifest)
    if window is not None:
        compared.append("first_seen_at.min")
        compared.append("first_seen_at.max")
        manifest_min, manifest_max = window
        if not _same_moment(manifest_min, live_min):
            mismatches.append(
                {
                    "dimension": "first_seen_at.min",
                    "manifest": manifest_min,
                    "live": live_min,
                }
            )
        if not _same_moment(manifest_max, live_max):
            mismatches.append(
                {
                    "dimension": "first_seen_at.max",
                    "manifest": manifest_max,
                    "live": live_max,
                }
            )
    manifest_sources = _manifest_source_counts(manifest)
    if manifest_sources is not None:
        compared.append("sources.observations")
        for source in sorted(set(manifest_sources) | set(facts["source_counts"])):
            expected = manifest_sources.get(source)
            actual = facts["source_counts"].get(source)
            if expected != actual:
                mismatches.append(
                    {
                        "dimension": f"sources.{source}",
                        "manifest": expected,
                        "live": actual,
                    }
                )
    manifest_watermarks = _manifest_watermarks(manifest)
    watermark_mismatches: list[dict[str, Any]] = []
    if manifest_watermarks is not None:
        compared.append("watermarks")
        live_watermarks = {str(row["source"]): row.get("watermark") for row in facts["sources"]}
        for source in sorted(set(manifest_watermarks) | set(live_watermarks)):
            manifest_value = _canonical_jsonish(manifest_watermarks.get(source))
            live_value = _canonical_jsonish(live_watermarks.get(source))
            if manifest_value != live_value:
                watermark_mismatches.append(
                    {
                        "dimension": f"watermarks.{source}",
                        "manifest": _bounded_text(manifest_value, 160),
                        "live": _bounded_text(live_value, 160),
                    }
                )

    version_chain_mismatches: list[dict[str, Any]] = []
    version_chain = manifest.get("version_chain")
    if isinstance(version_chain, Mapping):
        compared.append("version_chain")
        live_chain = {
            "max_version_count": max(
                (len(versions) for versions in facts["versions_by_obs"].values()), default=0
            ),
            "multi_version_observations": sum(
                1 for versions in facts["versions_by_obs"].values() if len(versions) > 1
            ),
            "observations_with_versions": sum(
                1 for versions in facts["versions_by_obs"].values() if len(versions) > 0
            ),
        }
        for key, actual in live_chain.items():
            expected = version_chain.get(key)
            if not isinstance(expected, (int, str)) or isinstance(expected, bool):
                continue
            try:
                expected_value = int(expected)
            except (TypeError, ValueError):
                continue
            if expected_value != actual:
                version_chain_mismatches.append(
                    {
                        "dimension": f"version_chain.{key}",
                        "manifest": expected_value,
                        "live": actual,
                    }
                )
        mismatches.extend(version_chain_mismatches)

    required_compared = all(
        f"counts.{dimension}" in compared for dimension in ("observations", "versions", "changes")
    )
    window_compared = "first_seen_at.min" in compared and "first_seen_at.max" in compared
    sources_compared = "sources.observations" in compared
    evidence["compared_dimensions"] = compared
    evidence["mismatches"] = _cap(mismatches)
    evidence["mismatch_total"] = len(mismatches)
    evidence["version_chain_mismatches"] = _cap(version_chain_mismatches)
    evidence["version_chain_mismatch_total"] = len(version_chain_mismatches)
    evidence["watermark_mismatches"] = _cap(watermark_mismatches)
    evidence["watermark_mismatch_total"] = len(watermark_mismatches)
    bundle_problems = (
        _bundle_ledger_problems(manifest_path, manifest)
        if manifest_path is not None and manifest_path.name == "MANIFEST.json"
        else []
    )
    evidence["bundle_ledger_problems"] = _cap(bundle_problems)
    evidence["bundle_ledger_problem_total"] = len(bundle_problems)

    created_at = evidence["manifest_created_at"]
    last_write = facts["last_write"]
    strict = (
        created_at is not None
        and _parse(created_at) is not None
        and last_write is not None
        and _parse(last_write) is not None
        and _parse(created_at) >= _parse(last_write)  # type: ignore[operator]
    )
    evidence["strict_identity_expected"] = bool(strict)

    if integrity_check is not None and str(integrity_check).strip().lower() not in (
        "ok",
        "pass",
        "passed",
        "ok (no errors)",
    ):
        return _check_result(
            "backup_restore_reproducibility",
            VERDICT_FAIL,
            f"备份清单记录该备份的 PRAGMA integrity_check 结果为 {integrity_check!r}："
            "备份本身不是完整可恢复的账本。",
            evidence,
        )
    if consistency_ok is False:
        return _check_result(
            "backup_restore_reproducibility",
            VERDICT_FAIL,
            "备份清单记录备份时账本 consistency_check 未通过：该备份不能作为恢复依据。",
            evidence,
        )
    if bundle_problems:
        return _check_result(
            "backup_restore_reproducibility",
            VERDICT_FAIL,
            f"备份包内的 ledger.sqlite 与清单记录不一致（{len(bundle_problems)} 处）："
            + "，".join(str(item["kind"]) for item in bundle_problems[:5])
            + "。该备份不可用于恢复。",
            evidence,
        )

    if mismatches:
        if strict:
            return _check_result(
                "backup_restore_reproducibility",
                VERDICT_FAIL,
                f"备份清单与实时账本在 {len(compared)} 个维度上不一致（清单创建时间不早于账本最后写入，"
                "属于严格身份校验）：" + "，".join(str(item["dimension"]) for item in mismatches[:6]) + "。"
                "具体数值见证据。",
                evidence,
            )
        # An older manifest must at least be a consistent prefix.
        prefix_problems: list[dict[str, Any]] = []
        for item in mismatches:
            dimension = str(item["dimension"])
            manifest_value, live_value = item["manifest"], item["live"]
            if dimension.startswith("counts."):
                if isinstance(manifest_value, int) and isinstance(live_value, int):
                    if manifest_value > live_value:
                        prefix_problems.append(item)
            elif dimension == "first_seen_at.min":
                prefix_problems.append(item)
            elif dimension == "first_seen_at.max":
                if _parse(manifest_value) is not None and _parse(live_value) is not None:
                    if _parse(manifest_value) > _parse(live_value):  # type: ignore[operator]
                        prefix_problems.append(item)
            elif dimension.startswith("sources."):
                if isinstance(manifest_value, int) and isinstance(live_value, int):
                    if manifest_value > live_value:
                        prefix_problems.append(item)
        if prefix_problems:
            return _check_result(
                "backup_restore_reproducibility",
                VERDICT_FAIL,
                f"备份清单与实时账本在 {len(prefix_problems)} 个维度上不可能构成一致前缀"
                "（清单计数大于实时账本或首次观察范围不一致）：具体数值见证据。",
                evidence,
            )
        return _check_result(
            "backup_restore_reproducibility",
            VERDICT_MANUAL,
            "备份清单早于账本最后一次写入（清单是旧快照）：它无法证明*当前*账本可恢复，"
            "但也没有被证伪（一致前缀成立）。需要一次针对该清单的恢复演练或一次新的备份后再审计。",
            evidence,
        )

    incomplete: list[str] = []
    if not required_compared:
        incomplete.append("counts(observations/versions/changes)")
    if not window_compared:
        incomplete.append("first_seen_at 最小/最大值")
    if not sources_compared:
        incomplete.append("按来源的观察计数")
    if incomplete:
        return _check_result(
            "backup_restore_reproducibility",
            VERDICT_MANUAL,
            "备份清单可解析且已知维度一致，但缺少以下恢复身份维度，无法证明恢复可复现："
            + "、".join(incomplete)
            + "。",
            evidence,
        )
    if watermark_mismatches:
        if not strict:
            # The manifest predates the newest ledger write: a moved watermark is
            # expected, but it means the manifest cannot prove the *current* state.
            return _check_result(
                "backup_restore_reproducibility",
                VERDICT_MANUAL,
                f"备份清单早于账本最后一次写入，且有 {len(watermark_mismatches)} 个来源的水位在备份后推进："
                "该清单只能证明当时的一致快照，不能证明当前账本可恢复；需要恢复演练或新的备份。"
                "具体来源见证据。",
                evidence,
            )
        return _check_result(
            "backup_restore_reproducibility",
            VERDICT_FAIL,
            f"备份清单与实时账本的来源水位不一致（{len(watermark_mismatches)} 个来源）："
            "清单记录的内容与当前账本不是同一份数据。具体来源见证据。",
            evidence,
        )
    detail = (
        f"备份清单与实时账本一致：observations={live_counts['observations']}、"
        f"versions={live_counts['versions']}、changes={live_counts['changes']}、runs={live_counts['runs']}；"
        f"first_seen_at 范围 [{live_min}, {live_max}]，来源分布 "
        + "，".join(f"{source}={count}" for source, count in sorted(facts["source_counts"].items()))
        + " 全部吻合。清单只证明该时刻存在一致快照，恢复演练仍需单独留证。"
    )
    return _check_result("backup_restore_reproducibility", VERDICT_PASS, detail, evidence)


# ------------------------------------------------------------- optional check 11
def _check_observation_phase(facts: Mapping[str, Any],
                             con: sqlite3.Connection) -> dict[str, Any]:
    if "observation_phase" not in facts["tables"]:
        return _check_result(
            OPTIONAL_CHECK_ID,
            VERDICT_MANUAL,
            "账本中没有 observation_phase 表（旧版账本）：采集阶段标注的完整性无法验证；"
            "按设计这不算失败，但也不能视为通过。",
            {
                "table_present": False,
                "observations": len(facts["observations"]),
                "rule": "表存在时：每条 observation 必须至少有一条 phase 行（append-only 标注）",
            },
        )
    try:
        phase_ids = {
            str(row[0])
            for row in con.execute("SELECT DISTINCT observation_id FROM observation_phase").fetchall()
        }
    except sqlite3.Error as exc:
        return _check_result(
            OPTIONAL_CHECK_ID,
            VERDICT_MANUAL,
            f"observation_phase 表存在但无法读取其 observation_id 列：{_bounded_text(exc, 160)}；"
            "采集阶段标注完整性无法验证。",
            {"table_present": True, "error": _bounded_text(exc, 200)},
        )
    missing = [oid for oid in facts["observations_by_id"] if oid not in phase_ids]
    orphans = sorted(oid for oid in phase_ids if oid not in facts["observations_by_id"])
    evidence = {
        "table_present": True,
        "observations": len(facts["observations_by_id"]),
        "phase_observations": len(phase_ids),
        "missing_phase_rows": _cap(missing),
        "missing_phase_rows_total": len(missing),
        "orphan_phase_rows": _cap(orphans),
        "orphan_phase_rows_total": len(orphans),
        "rule": "每条 observation 必须至少有一条 observation_phase 行；phase 行不得指向不存在的观察",
    }
    if missing or orphans:
        return _check_result(
            OPTIONAL_CHECK_ID,
            VERDICT_FAIL,
            f"observation_phase 表存在但覆盖不完整：{len(missing)} 条观察没有任何 phase 行，"
            f"{len(orphans)} 条 phase 行指向不存在的观察。具体 id 见证据。",
            evidence,
        )
    detail = (
        f"observation_phase 表存在，{len(facts['observations_by_id'])} 条观察全部有至少一条 append-only "
        "phase 行，且没有孤儿 phase 行。"
    )
    return _check_result(OPTIONAL_CHECK_ID, VERDICT_PASS, detail, evidence)


# ------------------------------------------------------------------ report assembly
def _failure_report(generated_at: str, ledger_path: Path, detail_zh: str,
                    evidence: Mapping[str, Any]) -> dict[str, Any]:
    check = _check_result("ledger_readable", VERDICT_FAIL, detail_zh, evidence)
    check["title_zh"] = "账本可读性：审计可以只读打开该 SQLite 文件"
    return {
        "schema": REPORT_SCHEMA,
        "audit_version": AUDIT_VERSION,
        "generated_at": generated_at,
        "ledger": {
            "present": ledger_path.exists(),
            "path": _display_path(ledger_path),
            "read_only": True,
        },
        "overall": VERDICT_FAIL,
        "checks": [check],
        "summary": {
            "total": 1,
            "pass": 0,
            "fail": 1,
            "manual_review": 0,
            "fail_ids": ["ledger_readable"],
            "manual_review_ids": [],
        },
        "manual_review": [],
        "limitations_zh": list(LIMITATIONS_ZH),
    }


def _summarise(checks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    fail_ids = [str(check["id"]) for check in checks if check["verdict"] == VERDICT_FAIL]
    manual_ids = [str(check["id"]) for check in checks if check["verdict"] == VERDICT_MANUAL]
    return {
        "total": len(checks),
        "pass": sum(1 for check in checks if check["verdict"] == VERDICT_PASS),
        "fail": len(fail_ids),
        "manual_review": len(manual_ids),
        "fail_ids": fail_ids,
        "manual_review_ids": manual_ids,
    }


def _overall(checks: Sequence[Mapping[str, Any]]) -> str:
    verdicts = {str(check["verdict"]) for check in checks}
    if VERDICT_FAIL in verdicts:
        return VERDICT_FAIL
    if VERDICT_MANUAL in verdicts:
        return VERDICT_MANUAL
    return VERDICT_PASS


def audit_ledger(
    ledger_path: str | Path | None = None,
    *,
    sample_size: int = 20,
    include_prospective: bool = True,
    backup_manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build the structured audit report for ``ledger_path`` (read-only).

    ``ledger_path`` defaults to :func:`medradar.observatory.ledger.default_ledger_path`.
    The ledger is opened with ``open_ledger_readonly``; nothing is written and the
    collector lock is never taken.  A missing/unreadable ledger yields an
    ``overall == "FAIL"`` report with a single ``ledger_readable`` check (the ten
    §7 checks cannot be evaluated without rows, and claiming anything else would
    be dishonest).

    ``sample_size`` bounds the replay sample; ``include_prospective=False`` marks
    the freeze check ``REQUIRES_MANUAL_REVIEW`` (it was deliberately not checked);
    ``backup_manifest_path`` overrides manifest discovery under
    ``<ledger parent>/backups``.
    """
    generated_at = _now_iso()
    path = Path(ledger_path).expanduser() if ledger_path is not None else default_ledger_path()
    if not path.exists():
        return _failure_report(
            generated_at,
            path,
            f"观察账本不存在：{_display_path(path)}。无法审计一个不存在的账本。",
            {"path": _display_path(path), "exists": False, "read_only": True},
        )
    try:
        ledger = open_ledger_readonly(path)
    except (FileNotFoundError, sqlite3.Error, OSError) as exc:
        return _failure_report(
            generated_at,
            path,
            f"无法以只读方式打开观察账本：{_bounded_text(exc, 300)}",
            {"path": _display_path(path), "exists": True, "read_only": True,
             "error": _bounded_text(exc, 400)},
        )
    try:
        con = ledger.con
        # A corrupt / non-SQLite file fails here; the audit must report it, not crash.
        facts = _load_facts(con)
        counts = ledger.counts()
        ledger_summary = {
            "present": True,
            "path": counts.get("path"),
            "bytes": counts.get("db_bytes"),
            "read_only": True,
            "schema_version": counts.get("schema_version"),
            "created_at": counts.get("created_at"),
            "counts": {
                "observations": counts.get("observations"),
                "versions": counts.get("versions"),
                "changes": counts.get("changes"),
                "live_observations": counts.get("live_observations"),
                "backfilled_observations": counts.get("backfilled_observations"),
                "removed_observations": counts.get("removed_observations"),
                "sources": counts.get("sources"),
                "runs": counts.get("runs"),
                "failures": counts.get("failures"),
            },
            "first_observation_at": counts.get("first_observation_at"),
            "last_observation_at": counts.get("last_observation_at"),
            "first_run_at": counts.get("first_run_at"),
            "last_run_at": counts.get("last_run_at"),
        }
        checks: list[dict[str, Any]] = [
            _check_duplicate_observations(facts, con),
            _check_first_seen_integrity(facts),
            _check_version_chain(facts, con),
            _check_version_change_consistency(facts, con),
            _check_timestamp_ordering(facts),
            _check_watermark_safety(facts),
            _check_replay_correctness(ledger, facts, int(sample_size)),
            _check_prospective_freeze(bool(include_prospective)),
            _check_mapping_history(ledger, facts, con),
            _check_backup_restore(ledger, facts, path, backup_manifest_path),
        ]
        checks.append(_check_observation_phase(facts, con))
    except sqlite3.Error as exc:
        return _failure_report(
            generated_at,
            path,
            f"读取观察账本时发生 SQLite 错误：{_bounded_text(exc, 300)}；账本可能损坏或结构不兼容。",
            {"path": _display_path(path), "exists": True, "read_only": True,
             "error": _bounded_text(exc, 400)},
        )
    finally:
        ledger.close()

    summary = _summarise(checks)
    overall = _overall(checks)
    manual_review = [
        {
            "id": check["id"],
            "title_zh": check["title_zh"],
            "reason_zh": check["detail_zh"],
        }
        for check in checks
        if check["verdict"] == VERDICT_MANUAL
    ]
    return {
        "schema": REPORT_SCHEMA,
        "audit_version": AUDIT_VERSION,
        "generated_at": generated_at,
        "ledger": ledger_summary,
        "overall": overall,
        "checks": checks,
        "summary": summary,
        "manual_review": manual_review,
        "limitations_zh": list(LIMITATIONS_ZH),
    }


# ------------------------------------------------------------------------ render
def _verdict_badge(verdict: str) -> str:
    return {
        VERDICT_PASS: "PASS（已证明）",
        VERDICT_FAIL: "FAIL（已证伪）",
        VERDICT_MANUAL: "REQUIRES_MANUAL_REVIEW（需人工复核）",
    }.get(verdict, verdict)


def _evidence_lines(evidence: Mapping[str, Any], indent: str = "  ") -> list[str]:
    lines: list[str] = []
    for key, value in evidence.items():
        if isinstance(value, (dict, list)):
            rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
            if len(rendered) > 1200:
                rendered = rendered[:1200] + "…"
        else:
            rendered = str(value)
        lines.append(f"{indent}- {key}: {rendered}")
    return lines


def _summary_table_markdown(report: Mapping[str, Any]) -> list[str]:
    lines = [
        "| # | 检查 | 结论 | 说明 |",
        "|---|---|---|---|",
    ]
    for index, check in enumerate(report.get("checks", []), start=1):
        title = str(check.get("title_zh", ""))
        verdict = str(check.get("verdict", ""))
        detail = str(check.get("detail_zh", ""))
        if len(detail) > 90:
            detail = detail[:89] + "…"
        lines.append(f"| {index} | {title} | {verdict} | {detail} |")
    return lines


def render_report(report: Mapping[str, Any], style: str = "text") -> str:
    """Render an audit report for human review (``style="text"`` or ``"markdown"``).

    Every check is printed with its title, verdict, detail and bounded evidence;
    a dedicated "needs human review" section lists the checks that returned
    ``REQUIRES_MANUAL_REVIEW``.  No line is a bare verdict.
    """
    if style not in ("text", "markdown"):
        raise ValueError(f"unknown report style: {style!r} (expected 'text' or 'markdown')")
    checks = list(report.get("checks", []))
    summary = report.get("summary", {})
    ledger = report.get("ledger", {})
    overall = str(report.get("overall", VERDICT_MANUAL))
    failed = [check for check in checks if check.get("verdict") == VERDICT_FAIL]
    manual = [check for check in checks if check.get("verdict") == VERDICT_MANUAL]
    lines: list[str] = []

    if style == "markdown":
        lines.append("# MedRadar 观测账本完整性审计报告 / Observatory Ledger Integrity Audit")
        lines.append("")
        lines.append(f"- 生成时间 / generated_at: `{report.get('generated_at')}`")
        lines.append(
            f"- 审计契约 / contract: `{report.get('audit_version')}`"
            "（docs/RELIABILITY_DESIGN.md §7）"
        )
        lines.append(
            f"- 账本 / ledger: `{ledger.get('path')}`"
            f"（只读打开 / read-only；{ledger.get('bytes')} bytes；"
            f"schema `{ledger.get('schema_version')}`）"
        )
        counts = ledger.get("counts") or {}
        lines.append(
            "- 账本计数 / counts: "
            + "，".join(f"{key}={value}" for key, value in counts.items())
        )
        lines.append(f"- 首次/最近观察 / first_seen span: {ledger.get('first_observation_at')} → {ledger.get('last_observation_at')}")
        lines.append(
            f"- 总体结论 / overall: **{_verdict_badge(overall)}** "
            f"（PASS {summary.get('pass', 0)} / FAIL {summary.get('fail', 0)} / "
            f"需人工复核 {summary.get('manual_review', 0)}）"
        )
        lines.append("")
        lines.append(
            "> 说明：本报告只陈述审计规则在本次运行时刻的真实结果；"
            "PASS 不等于科研结论已验证，也不代表观测覆盖完整。"
        )
        lines.append("")
        lines.append("## 汇总表 / Summary")
        lines.extend(_summary_table_markdown(report))
        lines.append("")
        lines.append("## 逐项检查与证据 / Checks and evidence")
        for index, check in enumerate(checks, start=1):
            lines.append("")
            lines.append(
                f"### {index}. {check.get('title_zh')} — {check.get('verdict')}"
                f"（{CHECK_TITLES_EN.get(str(check.get('id')), '')}）"
            )
            lines.append("")
            lines.append(str(check.get("detail_zh", "")))
            lines.append("")
            lines.append("证据 / evidence:")
            lines.append("")
            lines.append("```json")
            lines.append(
                json.dumps(check.get("evidence", {}), ensure_ascii=False,
                           sort_keys=True, indent=2, default=str)
            )
            lines.append("```")
        lines.append("")
        lines.append("## 需要人工复核 / Needs human review")
        lines.append("")
        if manual:
            for check in manual:
                lines.append(
                    f"- **{check.get('id')}** — {check.get('title_zh')}：{check.get('detail_zh')}"
                )
        else:
            lines.append("- 本次审计没有需要人工复核的检查项（没有 REQUIRES_MANUAL_REVIEW）。")
        if failed:
            lines.append("")
            lines.append("### 失败项（必须调查）/ Failures (must investigate)")
            lines.append("")
            for check in failed:
                lines.append(
                    f"- **{check.get('id')}** — {check.get('title_zh')}：{check.get('detail_zh')}"
                )
        lines.append("")
        lines.append("## 限制与诚实声明 / Limitations")
        lines.append("")
        for item in report.get("limitations_zh", []):
            lines.append(f"- {item}")
        lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------- text
    rule = "=" * 78
    lines.append(rule)
    lines.append("MedRadar 观测账本完整性审计报告 (Observatory Ledger Integrity Audit)")
    lines.append(rule)
    lines.append(f"生成时间 / generated_at : {report.get('generated_at')}")
    lines.append(f"审计契约 / contract     : {report.get('audit_version')} (docs/RELIABILITY_DESIGN.md §7)")
    lines.append(
        f"账本 / ledger          : {ledger.get('path')} (只读; {ledger.get('bytes')} bytes; "
        f"schema {ledger.get('schema_version')})"
    )
    counts = ledger.get("counts") or {}
    lines.append("账本计数 / counts      : " + "，".join(f"{key}={value}" for key, value in counts.items()))
    lines.append(
        f"首次/最近观察          : {ledger.get('first_observation_at')} → {ledger.get('last_observation_at')}"
    )
    lines.append(
        f"总体结论 / overall     : {_verdict_badge(overall)} "
        f"(PASS {summary.get('pass', 0)} / FAIL {summary.get('fail', 0)} / "
        f"需人工复核 {summary.get('manual_review', 0)})"
    )
    lines.append("说明：本报告只陈述审计规则在本次运行时刻的真实结果；PASS 不等于科研结论已验证。")
    lines.append("")
    lines.append("-" * 78)
    lines.append("逐项检查 / checks")
    lines.append("-" * 78)
    for index, check in enumerate(checks, start=1):
        lines.append("")
        lines.append(
            f"[{index:02d}] {check.get('title_zh')}"
        )
        lines.append(
            f"     英文 / en : {CHECK_TITLES_EN.get(str(check.get('id')), '')}"
        )
        lines.append(f"     结论 / verdict: {check.get('verdict')}  ({_verdict_badge(str(check.get('verdict')))})")
        lines.append(f"     说明 / detail : {check.get('detail_zh')}")
        lines.append("     证据 / evidence:")
        lines.extend(_evidence_lines(check.get("evidence", {}), indent="       "))
    lines.append("")
    lines.append("-" * 78)
    lines.append("需要人工复核 / Needs human review")
    lines.append("-" * 78)
    if manual:
        for check in manual:
            lines.append(f"  * {check.get('id')} — {check.get('title_zh')}")
            lines.append(f"    原因：{check.get('detail_zh')}")
    else:
        lines.append("  (本次审计没有 REQUIRES_MANUAL_REVIEW 的检查项)")
    if failed:
        lines.append("")
        lines.append("失败项（必须调查）/ Failures (must investigate)")
        lines.append("-" * 78)
        for check in failed:
            lines.append(f"  ! {check.get('id')} — {check.get('title_zh')}")
            lines.append(f"    原因：{check.get('detail_zh')}")
    lines.append("")
    lines.append("-" * 78)
    lines.append("限制与诚实声明 / Limitations")
    lines.append("-" * 78)
    for item in report.get("limitations_zh", []):
        lines.append(f"  - {item}")
    lines.append("")
    lines.append(rule)
    return "\n".join(lines)


# --------------------------------------------------------------------------- CLI hook
def run_audit(
    json_output: bool = False,
    verbose: bool = False,
    backup_manifest_path: str | Path | None = None,
) -> tuple[int, dict[str, Any]]:
    """Stable entry point for ``python -m medradar observatory audit``.

    Returns ``(exit_code, report)`` where ``exit_code`` is 1 only when the overall
    verdict is ``FAIL`` (a ``REQUIRES_MANUAL_REVIEW`` result is reported, never
    hidden behind a non-zero exit).  ``json_output`` / ``verbose`` are accepted so
    the CLI can keep one wiring; rendering stays in :func:`render_report` and the
    structured report is identical for JSON and human output.
    """
    report = audit_ledger(backup_manifest_path=backup_manifest_path)
    exit_code = 1 if report.get("overall") == VERDICT_FAIL else 0
    return exit_code, report


__all__ = [
    "AUDIT_VERSION",
    "CHECK_IDS",
    "CHECK_TITLES_EN",
    "CHECK_TITLES_ZH",
    "LIMITATIONS_ZH",
    "OPTIONAL_CHECK_ID",
    "REPORT_SCHEMA",
    "VERDICTS",
    "VERDICT_FAIL",
    "VERDICT_MANUAL",
    "VERDICT_PASS",
    "audit_ledger",
    "render_report",
    "run_audit",
]
