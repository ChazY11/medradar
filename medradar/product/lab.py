"""Research Lab data for MedRadar 2.0.

The lab surfaces the *existing* research programme without re-running or
re-interpreting it. Two kinds of content are served:

* curated study records from :mod:`medradar.product.catalog` (question, method,
  findings, negative results, reproduction commands, limitations);
* frozen artifacts read from the repository: the 69-packet human-review
  worksheet and the AI pre-adjudication summary (main branch), and the
  five-firm entry timeline of the Cycle 43 full-history benchmark (read-only
  copy from ``research/full-history-v1``; that branch is **not** merged).

Nothing here creates new labels, probabilities or claims. Where a study is
blocked or negative, the lab says so.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .catalog import STUDIES, STUDY_BY_ID

REPO_ROOT = Path(__file__).resolve().parents[2]
STUDY_DIR = REPO_ROOT / "research" / "studies" / "early_signal_5firms"
CYCLE43_REPORT = REPO_ROOT / "research" / "RESULTS" / "cycle43_full_history_2026-11-03.md"
ARTIFACT_DIR = Path(__file__).with_name("artifacts")

PROVENANCE = {
    "hist_v1": {
        "artifact": "medradar/product/artifacts/five_firm_timeline.json",
        "source_branch": "research/full-history-v1",
        "source_commit": "969fd0c",
        "source_path": "experiments/hist_v1/five_firm_timeline.json",
        "merged": False,
        "note_zh": (
            "该分支的全历史实验结果尚未合入 main，本轮只以只读方式引用其冻结产物"
            "（五家企业进入时间线），不合并其代码与结论。"
        ),
    },
    "early_signal_5firms": {
        "source_branch": "main",
        "source_path": "research/studies/early_signal_5firms/",
        "note_zh": "主分支研究材料，包含协议、AI 预标注、复核工作表与统计结果。",
    },
}


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def _human_review_stats() -> dict[str, Any] | None:
    path = STUDY_DIR / "HUMAN_REVIEW_WORKSHEET.csv"
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
    except OSError:
        return None
    labels: dict[str, int] = {}
    for row in rows:
        label = (row.get("agent_preliminary_label") or "").strip() or "（空）"
        labels[label] = labels.get(label, 0) + 1
    human_labels = sum(1 for row in rows if (row.get("final_label") or "").strip())
    return {
        "packets": len(rows),
        "agent_preliminary_labels": labels,
        "human_labels_recorded": human_labels,
        "status": "PENDING_HUMAN_REVIEW" if human_labels == 0 else "PARTIAL",
        "worksheet": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
        "note_zh": "工作表来自主分支；每份证据包的 AI 预标注不是人工真值，final_label 仍为空。",
    }


def _adjudication_summary() -> dict[str, Any] | None:
    payload = _read_json(STUDY_DIR / "ADJUDICATION_AGENT_V1.json")
    if not payload:
        return None
    return {
        "tier": payload.get("tier"),
        "generated_at_utc": payload.get("generated_at_utc"),
        "packets_assessed": payload.get("packets_assessed"),
        "summary": payload.get("summary"),
        "meaning": payload.get("meaning"),
        "not_human_truth": bool((payload.get("meaning") or {}).get("not_human_truth")),
    }


def _pilot_summary() -> dict[str, Any] | None:
    payload = _read_json(STUDY_DIR / "PILOT_RESULTS.json")
    if not payload:
        return None
    cells = payload.get("by_cell") or {}
    alerts = 0
    hits = 0
    for cell in cells.values():
        for model in ("m0_persistence", "m1_zscore"):
            model_data = cell.get(model) or {}
            alerts += int(model_data.get("alerts") or 0)
            hits += int(model_data.get("hits") or 0)
    return {
        "status": payload.get("status"),
        "window": payload.get("window"),
        "unit": payload.get("unit"),
        "availability_rule": payload.get("availability_rule"),
        "cells": len(cells),
        "leak_audit": payload.get("leak_audit"),
        "alerts_total": alerts,
        "hits_total": hits,
        "note_zh": "Pilot 只是规则化代理标签下的描述性结果，不是 H1–H4 的检验。",
    }


def _conditional_detection() -> dict[str, Any] | None:
    payload = _read_json(STUDY_DIR / "CONCURRENT_DETECTION.json")
    if not payload:
        return None
    return {
        "verdict": payload.get("verdict"),
        "totals": payload.get("totals"),
        "window": payload.get("window"),
        "not_claimed": payload.get("not_claimed"),
    }


def _lead_time() -> dict[str, Any] | None:
    payload = _read_json(STUDY_DIR / "LEAD_TIME_SMALL_SAMPLE.json")
    if not payload:
        return None
    return {
        "summary": payload.get("summary"),
        "underpowered_statement": payload.get("underpowered_statement"),
        "events": len(payload.get("events") or []),
        "not_claimed": payload.get("not_claimed"),
    }


def _third_source() -> dict[str, Any] | None:
    payload = _read_json(STUDY_DIR / "THIRD_SOURCE_CROSSWALK.json")
    if not payload:
        return None
    return {
        "status_counts": payload.get("status_counts"),
        "distance_counts": payload.get("distance_counts"),
        "interpretation": payload.get("interpretation"),
        "not_claimed": payload.get("not_claimed"),
    }


def _hist_timeline() -> dict[str, Any] | None:
    payload = _read_json(ARTIFACT_DIR / "five_firm_timeline.json")
    if not payload:
        return None
    cases = []
    for key, entry in (payload.get("deep_cases") or {}).items():
        cases.append(
            {
                "company": key,
                "display_name": entry.get("display_name"),
                "cohort": entry.get("cohort"),
                "material_events": entry.get("material_events"),
                "tracks_entered": entry.get("tracks_entered"),
                "first_entry": entry.get("first_entry"),
                "last_entry": entry.get("last_entry"),
                "entries_by_era": entry.get("entries_by_era"),
                "entries_with_same_category_prior_activity": entry.get("entries_with_same_category_prior_activity"),
                "entries": entry.get("entries") or [],
            }
        )
    return {
        "schema": payload.get("schema"),
        "n_companies": payload.get("n_companies"),
        "n_tracks": payload.get("n_tracks"),
        "cases": cases,
        "note_zh": (
            "该时间线来自 Cycle 43 冻结产物：material event 的赛道首次进入按季度记录，"
            "只描述数据覆盖期内的首次进入，不是产品发布或战略意图。"
        ),
    }


def _cycle43_report_excerpt() -> dict[str, Any] | None:
    # The report lives on research/full-history-v1 (not merged into main); a
    # frozen copy is vendored next to this module so the lab can serve it
    # read-only with provenance instead of hiding the study behind a dead link.
    candidates = [CYCLE43_REPORT, ARTIFACT_DIR / "cycle43_full_history_2026-11-03.md"]
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            text = candidate.read_text(encoding="utf-8")
        except OSError:
            continue
        return {
            "path": str(candidate.relative_to(REPO_ROOT)).replace("\\", "/")
            if candidate.is_relative_to(REPO_ROOT)
            else str(candidate),
            "source_branch": "research/full-history-v1",
            "source_commit": "969fd0c",
            "chars": len(text),
            "title": text.splitlines()[0].lstrip("# ").strip() if text.splitlines() else "",
            "excerpt_zh": "\n".join(text.splitlines()[:6]),
        }
    return None


def _study_artifacts(study_id: str) -> dict[str, Any]:
    if study_id == "S-027-early-signal-5firms":
        return {
            "human_review": _human_review_stats(),
            "agent_pre_adjudication": _adjudication_summary(),
            "pilot": _pilot_summary(),
            "concurrent_detection": _conditional_detection(),
            "lead_time_small_sample": _lead_time(),
            "third_source": _third_source(),
        }
    if study_id == "C43-hist-v1":
        return {
            "five_firm_timeline": _hist_timeline(),
            "report": _cycle43_report_excerpt(),
            "provenance": PROVENANCE["hist_v1"],
        }
    if study_id == "R-forecast-registry":
        payload = _read_json(REPO_ROOT / "research" / "forecasts" / "FORECAST_SET_2026-11-03.json")
        entries = (payload or {}).get("forecasts") or (payload or {}).get("predictions") or []
        return {
            "registered_forecasts": len(entries) if isinstance(entries, list) else None,
            "prospective_set": _read_json(REPO_ROOT / "research" / "forecasts" / "FORECAST_SET_2026-11-03_prospective.json")
            is not None,
            "calibration_claim_zh": "当前没有已成熟、可计算校准误差的前瞻预测集合。",
        }
    return {}


def lab_overview() -> dict[str, Any]:
    studies = []
    for study in STUDIES:
        artifacts = _study_artifacts(study["id"])
        studies.append(
            {
                **study,
                "artifacts": artifacts,
                "has_artifacts": bool(artifacts),
            }
        )
    data_edge = None
    try:
        from . import store

        data_edge = store.data_edge()
    except Exception:  # pragma: no cover - store may be absent in docs-only mode
        data_edge = None
    return {
        "studies": studies,
        "provenance": PROVENANCE,
        "data_foundation": {
            "store": "data/medradar.sqlite",
            "data_edge": data_edge,
            "note_zh": "所有产品数字来自同一研究数据层；研究实验的结论与产品观察结论严格分开标注。",
        },
        "policy_zh": [
            "Research Lab 只展示已验证、不确定与负面的研究状态，不把研究假设包装成产品预测。",
            "AI 预标注不是人工真值；未完成人工复核的研究保持 blocked 状态。",
            "未合入 main 的研究分支只做只读引用，并标注来源 commit。",
        ],
    }


def study_detail(study_id: str) -> dict[str, Any]:
    study = STUDY_BY_ID.get(study_id)
    if not study:
        raise KeyError(f"unknown study: {study_id}")
    artifacts = _study_artifacts(study_id)
    return {
        **study,
        "artifacts": artifacts,
        "cross_links": {
            "note_zh": "研究结论与产品观察结论的边界：研究回答“是否可能提前”，产品只陈述“记录中观察到什么”。",
            "related_views": ["/radar", "/companies", "/evidence"],
        },
    }
