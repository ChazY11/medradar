"""Read-only shaping for the Research Lab Prospective Observation Registry API.

This module never writes and never creates a directory: a missing or empty
registry renders an honest empty state, and an entry is only reported from frozen
files that actually exist.  It makes no validated/calibrated/predictive claim —
the registry is an audit instrument, not a prediction engine.  Optional fields
that are unknown stay ``None`` instead of becoming 0 or "today".
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from ..observatory import prospective as registry_module
from ..observatory.records import utc_now_iso

REPO_ROOT = Path(__file__).resolve().parents[2]

#: What the block is (and is not) — shown verbatim by the UI.
POLICY_ZH = [
    "前瞻观察登记器记录「假设何时冻结、冻结时账本已知什么、声明窗口内后来又观察到什么」；它不是预测引擎。",
    "冻结文档只写入一次，评估与撤回都是新的不可变附录文件；冻结输入的哈希可随时复核。",
    "任何条目在研究者按声明判据判定之前都只是未验证的实验性观察，不构成已验证或已校准的结论。",
    "合成测试条目（label 含「合成测试」）只用于测试登记器机制，不代表任何真实世界事件或真实前瞻结果。",
]

HONESTY_ZH = [
    "窗口结束前拒绝计算结局（status=NOT_DUE），不写入任何评估附录。",
    "结局只统计冻结之后、声明窗口内首次观察到的候选证据；登记器不自动判定目标事件是否发生。",
    "该接口不返回概率、评分、校准误差或准确率。",
    "缺失的时间保持为空，不做插补。",
]

REGISTRY_NOTICE_ZH = (
    "登记器目录来自 MEDRADAR_PROSPECTIVE_DIR 或数据主目录下的 prospective/；"
    "没有冻结条目时保持空状态，不生成任何示例条目。"
)


def _display_path(path: Path) -> str:
    """Portable path for the API: relative when possible, never an absolute host path."""
    for base in (REPO_ROOT, Path.cwd()):
        try:
            return path.resolve().relative_to(base.resolve()).as_posix()
        except (OSError, ValueError):
            continue
    return f"…/{path.name}"


def _empty_status_counts() -> dict[str, int]:
    return {status: 0 for status in registry_module.STATUSES}


def _status_counts(entries: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts = _empty_status_counts()
    for entry in entries:
        status = str(entry.get("status") or "")
        if status in counts:
            counts[status] += 1
    return counts


def _integrity_issues(entries: Iterable[Mapping[str, Any]]) -> int:
    return sum(1 for entry in entries if entry.get("integrity") != "OK")


def _synthetic_count(entries: Iterable[Mapping[str, Any]]) -> int:
    return sum(1 for entry in entries if entry.get("synthetic"))


def _latest_freeze_at(entries: Iterable[Mapping[str, Any]]) -> str | None:
    moments = [str(entry.get("freeze_at")) for entry in entries if entry.get("freeze_at")]
    return max(moments) if moments else None


def _registry_view(entries: list[dict[str, Any]], registry: Any) -> dict[str, Any]:
    counts = _status_counts(entries)
    synthetic = _synthetic_count(entries)
    return {
        "path": _display_path(Path(registry.directory)),
        "exists": bool(registry.exists),
        "entry_count": len(entries),
        "status_counts": counts,
        "synthetic_count": synthetic,
        "real_entry_count": len(entries) - synthetic,
        "matured_count": counts[registry_module.STATUS_MATURED],
        "due_count": counts[registry_module.STATUS_DUE],
        "integrity_issues": _integrity_issues(entries),
        "latest_freeze_at": _latest_freeze_at(entries),
        "empty": not entries,
        "notice_zh": REGISTRY_NOTICE_ZH,
    }


def _evaluation_brief(evaluation: Mapping[str, Any]) -> dict[str, Any]:
    inputs = evaluation.get("inputs") or {}
    outcomes = evaluation.get("outcomes") or {}
    ledger = evaluation.get("ledger") or {}
    ledger_counts = ledger.get("counts") or {}
    return {
        "evaluation_seq": evaluation.get("evaluation_seq"),
        "computed_at": evaluation.get("computed_at"),
        "recorded_at": evaluation.get("recorded_at"),
        "status": evaluation.get("status"),
        "inputs_count": inputs.get("count"),
        "outcomes_count": outcomes.get("count"),
        "new_version_count": outcomes.get("new_version_count"),
        "classification": outcomes.get("classification"),
        "human_classification_required": outcomes.get("human_classification_required"),
        "snapshot_as_of": ledger.get("snapshot_as_of"),
        "ledger_counts": {
            key: ledger_counts.get(key)
            for key in ("observations", "versions", "changes")
        },
    }


def _entry_view(summary: Mapping[str, Any]) -> dict[str, Any]:
    """List-row view of one frozen entry (no full evidence payload)."""
    synthetic = bool(summary.get("synthetic"))
    latest = summary.get("latest_evaluation")
    return {
        "entry_id": summary.get("entry_id"),
        "label_zh": summary.get("label_zh"),
        "hypothesis_zh": summary.get("hypothesis_zh"),
        "truth_statement_zh": "该条目为冻结后待验证的前瞻观察，不是预测，也未经验证。",
        "freeze_at": summary.get("freeze_at"),
        "window_start": summary.get("window_start"),
        "window_end": summary.get("window_end"),
        "target_event_definition_zh": summary.get("target_event_definition_zh"),
        "baseline_zh": summary.get("baseline_zh"),
        "evaluation_criteria_zh": summary.get("evaluation_criteria_zh"),
        "scope": dict(summary.get("scope") or {}),
        "status": summary.get("status"),
        "status_label_zh": summary.get("status_label_zh"),
        "status_note_zh": registry_module.STATUS_NOTES_ZH.get(
            str(summary.get("status") or ""), None
        ),
        "frozen_status": summary.get("frozen_status"),
        "synthetic": synthetic,
        "synthetic_badge_zh": "合成测试（非真实前瞻结果）" if synthetic else None,
        "evidence_status": "SYNTHETIC" if synthetic else "UNVALIDATED",
        "frozen_evidence_count": summary.get("frozen_evidence_count"),
        "frozen_evidence_as_of": summary.get("frozen_evidence_as_of"),
        "evaluation_count": summary.get("evaluation_count"),
        "latest_evaluation": _evaluation_brief(latest) if isinstance(latest, Mapping) else None,
        "evaluation_history": [
            _evaluation_brief(item)
            for item in (summary.get("evaluations") or [])
            if isinstance(item, Mapping)
        ],
        "retracted": bool(summary.get("retracted")),
        "retraction_reason_zh": summary.get("retraction_reason_zh"),
        "frozen_verified": bool(summary.get("frozen_verified")),
        "integrity": summary.get("integrity"),
        "content_sha256": summary.get("content_sha256"),
        "note_zh": summary.get("note_zh"),
    }


def _entry_detail(view: Mapping[str, Any]) -> dict[str, Any]:
    """Detail view: frozen protocol + frozen evidence items, shaped for display."""
    entry = _entry_view(view)
    evidence = view.get("evidence") or {}
    entry["frozen_recorded_at"] = view.get("frozen_recorded_at")
    entry["target_event_type"] = view.get("target_event_type")
    entry["verification"] = view.get("verification")
    entry["evidence"] = {
        "as_of": evidence.get("as_of"),
        "count": evidence.get("count"),
        "evidence_sha256": evidence.get("evidence_sha256"),
        "excluded_discovered_later": evidence.get("excluded_discovered_later"),
        "items": list(evidence.get("items") or []),
        "observation_policy_zh": evidence.get("observation_policy_zh"),
        "policy_zh": evidence.get("policy_zh"),
    }
    entry["policy_zh"] = list(view.get("policy_zh") or [])
    entry["status_history"] = list(view.get("status_history") or [])
    return entry


def _open_registry() -> Any:
    return registry_module.open_registry()


def _read_entries(registry: Any) -> list[dict[str, Any]]:
    return list(registry.list_entries())


def prospective_summary() -> dict[str, Any]:
    """Compact block embedded in ``lab_overview``; never raises, never invents entries."""
    try:
        registry = _open_registry()
        entries = _read_entries(registry)
    except Exception as exc:  # pragma: no cover - defensive: lab must keep rendering
        return {
            "available": False,
            "registry_path": "prospective",
            "error_zh": f"登记器目录不可读：{exc}",
            "notice_zh": REGISTRY_NOTICE_ZH,
            "entry_count": 0,
            "status_counts": _empty_status_counts(),
            "synthetic_count": 0,
            "real_entry_count": 0,
            "matured_count": 0,
            "due_count": 0,
            "integrity_issues": 0,
            "latest_freeze_at": None,
            "note_zh": "暂无可审计的前瞻登记；本产品不生成示例条目。",
        }
    block = _registry_view(entries, registry)
    return {
        "available": True,
        "registry_path": block["path"],
        "error_zh": None,
        "notice_zh": REGISTRY_NOTICE_ZH,
        "entry_count": block["entry_count"],
        "status_counts": block["status_counts"],
        "synthetic_count": block["synthetic_count"],
        "real_entry_count": block["real_entry_count"],
        "matured_count": block["matured_count"],
        "due_count": block["due_count"],
        "integrity_issues": block["integrity_issues"],
        "latest_freeze_at": block["latest_freeze_at"],
        "note_zh": (
            "前瞻观察登记器不是预测引擎：条目冻结后才报告窗口内观察到的候选证据，"
            "默认状态 EXPERIMENTAL，本产品不做校准或预测性声明。"
        ),
    }


def overview() -> dict[str, Any]:
    """``GET /api/lab/prospective`` — honest empty state when nothing is frozen."""
    registry = _open_registry()
    entries = _read_entries(registry)
    views = [_entry_view(entry) for entry in entries]
    return {
        "generated_at": utc_now_iso(),
        "registry": _registry_view(entries, registry),
        "entries": views,
        "empty": not views,
        "empty_zh": (
            "登记器尚未冻结任何条目：这里不会显示示例或伪造的前瞻结果。"
            " 冻结后的条目会列出冻结时点、声明窗口与冻结证据数。"
        ),
        "status_vocabulary": [
            {
                "status": status,
                "label_zh": registry_module.STATUS_LABELS_ZH[status],
                "note_zh": registry_module.STATUS_NOTES_ZH[status],
            }
            for status in registry_module.STATUSES
        ],
        "policy_zh": list(POLICY_ZH),
        "honesty_zh": list(HONESTY_ZH),
        "validation": {
            "validated": False,
            "calibrated": False,
            "predictive": False,
            "note_zh": "登记器不提供已验证结论、校准误差或预测值；任何此类说法都不来自本接口。",
        },
    }


def entry(entry_id: str) -> dict[str, Any]:
    """``GET /api/lab/prospective/{entry_id}`` — raises ``KeyError`` when unknown."""
    registry = _open_registry()
    view = registry.get_entry(entry_id)
    verification = registry.verify_frozen(view.get("entry_id") or entry_id)
    evaluations = [dict(item) for item in (view.get("evaluations") or [])]
    return {
        "generated_at": utc_now_iso(),
        "entry": _entry_detail(view),
        "evaluations": evaluations,
        "evaluation_count": len(evaluations),
        "verification": verification,
        "policy_zh": list(POLICY_ZH),
        "honesty_zh": list(HONESTY_ZH),
        "validation": {
            "validated": False,
            "calibrated": False,
            "predictive": False,
            "note_zh": "该条目是冻结后待验证的前瞻观察；本接口不给出预测或校准结论。",
        },
    }
