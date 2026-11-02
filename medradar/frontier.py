"""Front-edge medical-device intelligence across public pre-decision signals."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from .clinical import device_intervention_text
from .config import load_tracks
from .db import DB
from .util import ensure_dir, today_utc, utc_now_iso, write_json

FRONTIER_KINDS = ("advisory_committee", "trial", "8k_catalyst")
FRONTIER_CATEGORIES = {"pre_submission", "designation"}
DEVICE_FILING_RE = re.compile(
    r"\b(?:medical\s+)?device\b|510\s*\(k\)|\bde\s+novo\b|\bpma\b|"
    r"\bivd\b|\bdiagnostic\b|\bassay\b|\becmo\b|brain[- ]computer",
    re.I,
)
STAGE_LABELS = {
    "advisory_committee": "咨询委员会/审评前公开讨论",
    "clinical_trial": "临床试验注册",
    "pre_submission": "预申请沟通",
    "designation": "突破性/优先审评等资格认定",
}


def _payload(event: Mapping[str, Any]) -> dict[str, Any]:
    raw = event.get("payload")
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def _stage(event: Mapping[str, Any], payload: Mapping[str, Any]) -> str | None:
    kind = str(event.get("kind") or "")
    if kind == "advisory_committee":
        return "advisory_committee"
    if kind == "trial":
        return "clinical_trial"
    if kind == "8k_catalyst":
        category = str(payload.get("category") or "")
        return category if category in FRONTIER_CATEGORIES else None
    return None


def build_frontier(db: DB, limit: int = 500) -> dict[str, Any]:
    """Return a domain-aware, machine-readable frontier event feed.

    No pending-application status is inferred. Every row is tied to a public
    source URL and keeps its original public-time quality.
    """
    placeholders = ",".join("?" for _ in FRONTIER_KINDS)
    rows = db.query(
        "SELECT event_id, source, kind, event_date, published_at, available_at,"
        " timestamp_quality, company_key, applicant_raw, track_id, title, summary,"
        " url, payload FROM events"
        f" WHERE kind IN ({placeholders}) ORDER BY event_date DESC, event_id",
        FRONTIER_KINDS,
    )
    registry = load_tracks("device")
    events: list[dict[str, Any]] = []
    skipped = Counter()
    for row in rows:
        payload = _payload(row)
        stage = _stage(row, payload)
        if stage is None:
            skipped["not_frontier"] += 1
            continue
        kind = str(row.get("kind") or "")
        device_text = device_intervention_text(payload) if kind == "trial" else ""
        match_text = " ".join(
            str(value or "") for value in (
                row.get("title"), row.get("summary"), row.get("applicant_raw"),
                payload.get("meeting"), payload.get("center"), device_text,
            )
        )
        existing_track = row.get("track_id") if registry.get(row.get("track_id")) else None
        track_id = existing_track or registry.match_frontier_text(match_text)
        if kind == "trial" and not existing_track and not device_text:
            skipped["non_device_trial"] += 1
            continue
        if (
            kind == "8k_catalyst" and not existing_track and not track_id
            and not DEVICE_FILING_RE.search(match_text)
        ):
            skipped["non_device_filing"] += 1
            continue
        track = registry.get(track_id) or {}
        domain = registry.domain(track_id)
        events.append({
            "event_id": row.get("event_id"),
            "date": row.get("event_date"),
            "stage": stage,
            "stage_zh": STAGE_LABELS[stage],
            "source": row.get("source"),
            "kind": row.get("kind"),
            "company_key": row.get("company_key"),
            "applicant": row.get("applicant_raw") or "",
            "track_id": track_id,
            "track_zh": track.get("name_zh") or "未分类",
            "domain": domain["id"],
            "domain_zh": domain["name_zh"],
            "title": row.get("title") or "",
            "summary": row.get("summary") or "",
            "url": row.get("url") or "",
            "published_at": row.get("published_at"),
            "available_at": row.get("available_at"),
            "timestamp_quality": row.get("timestamp_quality") or "unknown",
            "documents": payload.get("documents") or [],
            "evidence_scope": "public source only",
        })
    events = events[: max(0, int(limit))]

    domain_groups: dict[str, list[dict[str, Any]]] = {}
    track_counts: Counter[str] = Counter()
    for event in events:
        domain_groups.setdefault(event["domain"], []).append(event)
        if event.get("track_id"):
            track_counts[str(event["track_id"])] += 1
    by_domain = []
    for domain, items in sorted(domain_groups.items(), key=lambda pair: (-len(pair[1]), pair[0])):
        by_domain.append({
            "domain": domain,
            "domain_zh": items[0]["domain_zh"],
            "events": len(items),
            "by_stage": dict(Counter(item["stage"] for item in items)),
            "top_tracks": [
                {"track_id": track_id, "name_zh": registry.name_zh(track_id), "events": count}
                for track_id, count in Counter(
                    str(item["track_id"]) for item in items if item.get("track_id")
                ).most_common(8)
            ],
        })
    configured_domains = sorted({str(track.get("domain") or "other") for track in registry.all()})
    return {
        "schema": "medradar.frontier.v1",
        "generated_at": utc_now_iso(),
        "as_of": today_utc().isoformat(),
        "status": "ok" if events else "insufficient_data",
        "events": events,
        "summary": {
            "events": len(events),
            "by_stage": dict(Counter(event["stage"] for event in events)),
            "by_domain": by_domain,
            "unclassified": sum(1 for event in events if not event.get("track_id")),
            "documents": sum(len(event.get("documents") or []) for event in events),
        },
        "coverage": {
            "configured_tracks": len(registry.all()),
            "configured_domains": len(configured_domains),
            "domains": configured_domains,
            "top_tracks": [
                {"track_id": track_id, "name_zh": registry.name_zh(track_id), "events": count}
                for track_id, count in track_counts.most_common(20)
            ],
        },
        "sources": {
            "advisory_committee": "https://www.fda.gov/advisory-committees/advisory-committee-calendar",
            "clinical_trials": "https://clinicaltrials.gov/data-api/api",
            "company_filings": "https://www.sec.gov/edgar/search/",
        },
        "capabilities": {
            "public_pre_decision_signals": True,
            "pending_510k_pma_monitoring": False,
            "pending_510k_pma_reason": "Non-public pending applications are confidential; MedRadar does not fabricate a pending-review feed.",
        },
        "skipped": dict(skipped),
    }


def render_markdown(payload: Mapping[str, Any], limit: int = 80) -> str:
    summary = payload.get("summary") or {}
    lines = [
        "# MedRadar 医疗器械前沿雷达",
        "",
        f"- 数据日期：{payload.get('as_of')}",
        f"- 前沿事件：{summary.get('events', 0)}",
        f"- 公开日程/简报材料：{summary.get('documents', 0)}",
        "- 口径：只使用公开来源；不把决定日当成公开日，不宣称监测保密的 pending 510(k)/PMA。",
        "",
        "## 领域分布",
        "",
        "| 领域 | 事件 | 阶段分布 |",
        "|---|---:|---|",
    ]
    for row in summary.get("by_domain") or []:
        stages = "、".join(f"{STAGE_LABELS.get(key, key)} {value}" for key, value in (row.get("by_stage") or {}).items())
        lines.append(f"| {row.get('domain_zh')} (`{row.get('domain')}`) | {row.get('events')} | {stages} |")
    lines += ["", "## 最新前沿事件", ""]
    for event in (payload.get("events") or [])[:limit]:
        lines += [
            f"### {event.get('date')} · {event.get('domain_zh')} · {event.get('stage_zh')}",
            "",
            f"- {event.get('title')}",
            f"- 赛道：{event.get('track_zh')}｜来源：{event.get('source')}｜时间质量：{event.get('timestamp_quality')}",
            f"- 原文：{event.get('url') or '（无）'}",
            "",
        ]
        for document in (event.get("documents") or [])[:6]:
            lines.append(f"  - 材料：[{document.get('text') or 'FDA document'}]({document.get('url')})")
        if event.get("documents"):
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def write_frontier(payload: Mapping[str, Any], out_dir: str | Path = "out") -> dict[str, str]:
    target = ensure_dir(Path(out_dir))
    json_path = target / "frontier.json"
    md_path = target / "frontier.md"
    write_json(json_path, payload)
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


__all__ = ["FRONTIER_KINDS", "build_frontier", "render_markdown", "write_frontier"]
