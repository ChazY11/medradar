"""Read-only product query layer over the Live Observation Ledger.

The ledger (``medradar/observatory/ledger.py``) stores *observations*: what a
source said, when the source said it, and when MedRadar's collector first saw it.
This module never writes. It resolves the ledger path at **request time** through
:func:`medradar.observatory.ledger.default_ledger_path` (so ``MEDRADAR_OBSERVATORY_DB``
is honoured), opens the file with ``open_ledger_readonly`` and closes it after the
response payload has been built.

Honesty rules implemented here (see ``docs/LIVE_OBSERVATORY_DESIGN.md`` §1/§8):

* ``event_at``, ``published_at``, ``first_seen_at`` and ``last_checked_at`` stay
  four different statements; the payload never substitutes one for another.
* A measured lag is only reported as measured when the source published a
  *timestamp* (``published_at_precision == "datetime"``); otherwise
  ``time_basis.measurable`` is ``False`` and ``evidence_zh`` says ``无法测量``
  together with the reason.
* ``NEW`` / ``UPDATED`` / ``REMOVED_OR_UNAVAILABLE`` / ``FETCH_FAILED`` are four
  different claims with four different Chinese labels.
* A missing / unreadable ledger is an honest empty state (``exists: false``,
  empty windows, empty item lists, HTTP 200). It is never fabricated evidence and
  never a 500 — the CI wheel/demo has no ledger.
* Only the ledger's own query methods are used for record data; the few
  per-source aggregates that the ledger does not expose (run history, failure
  history, per-source observation totals) are read with read-only SELECTs over
  the same connection. Nothing is written, ever.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from ..config import DATA_DIR
from ..observatory import mapping as mapping_layer
from ..observatory.lag import measure_lag, observation_lag
from ..observatory.ledger import ObservationLedger, default_ledger_path, open_ledger_readonly
from ..observatory.records import (
    CHANGE_FETCH_FAILED,
    CHANGE_NEW,
    CHANGE_REMOVED,
    CHANGE_UPDATED,
    ENTITY_AMBIGUOUS,
    ENTITY_MAPPED,
    ENTITY_PENDING_REVIEW,
    ENTITY_UNMAPPED,
    FIELD_LABELS_ZH,
    ORIGIN_BACKFILLED,
    SOURCE_STATUS_LABELS_ZH,
    STATUS_REMOVED,
    TRACK_UNMAPPED,
    short_preview,
    utc_now_iso,
)

# --------------------------------------------------------------------- vocabulary
WINDOWS: dict[str, int] = {"24h": 24, "7d": 24 * 7, "30d": 24 * 30}
CHANGE_STATES_FOR_FILTER: dict[str, tuple[str, ...] | None] = {
    "all": None,
    "new": (CHANGE_NEW,),
    "updated": (CHANGE_UPDATED,),
    "removed": (CHANGE_REMOVED,),
    "failed": (CHANGE_FETCH_FAILED,),
}
CHANGE_ORDER = (CHANGE_NEW, CHANGE_UPDATED, CHANGE_REMOVED, CHANGE_FETCH_FAILED)

#: Contract shape of §6 ``measured_lag`` (projected from observatory.lag).
MEASURED_LAG_KEYS = ("measurable", "note_zh", "p50_hours", "p90_hours", "max_hours", "n")

#: Row-level labels. ``records.CHANGE_LABELS_ZH`` is the collector vocabulary
#: ("新增观察"); the observatory list intentionally uses the shorter claim words
#: so a chip reads as a claim type, not as a sentence.
CHANGE_LABELS_ZH = {
    CHANGE_NEW: "新增",
    CHANGE_UPDATED: "修订",
    CHANGE_REMOVED: "不再提供",
    CHANGE_FETCH_FAILED: "采集失败",
}

SOURCE_LABELS_ZH = {
    "sec_edgar": "SEC EDGAR 公开披露",
    "ctgov": "ClinicalTrials.gov 注册库",
    "europepmc": "Europe PMC 文献库",
}

RECORD_TYPE_LABELS_ZH = {
    "sec_8k": "8-K 重大事件披露",
    "sec_8ka": "8-K 修订披露",
    "sec_6k": "6-K 外国发行人报告",
    "sec_10q": "10-Q 季度报告",
    "sec_10k": "10-K 年度报告",
    "sec_20f": "20-F 外国发行人年报",
    "sec_other": "其他 SEC 披露",
    "trial": "临床试验注册",
    "publication": "公开文献",
}

SOURCE_LIMITATIONS_ZH = {
    "sec_edgar": (
        "SEC 披露只覆盖美国上市发行人。不是 SEC 注册人的企业本来就不会有 8-K，"
        "「没有该企业记录」不等于「该企业没有活动」。"
    ),
    "ctgov": "注册记录不等于上市产品；部分注册记录无法映射到已审技术赛道，未映射不等于零活动。",
    "europepmc": "文献按单位署名检索命中，PENDING_REVIEW 只表示待人工复核，不等同于经核实的法人归属。",
    "unknown": "该数据源尚未登记展示说明；未声明覆盖范围不等于零活动。",
}

LEDGER_MISSING_NOTE_ZH = (
    "观察账本尚不存在或无法读取：MedRadar 还没有在这个数据目录里完成过任何观察采集。"
    "因此这里没有任何观察记录。空状态不等于「来源没有新事件」，也不代表数据源不可用。"
)

LEDGER_HONESTY_ZH = (
    "账本只记录 MedRadar 采集器真实抓取到的记录；first_seen_at 由采集器在首次成功抓取时"
    "写入且不可修改。所有来源都是按声明周期轮询采集，不是实时推送。"
)

LIMITATIONS: list[dict[str, str]] = [
    {
        "id": "not_realtime",
        "text_zh": "观察站是轮询采集，不是实时推送；每个来源的声明周期与实际观察间隔见「数据源同步状态」。",
    },
    {
        "id": "first_seen_semantics",
        "text_zh": (
            "「首次观察」是 MedRadar 采集器真实首次成功抓取该记录的时间；它不等于来源发布时间，"
            "也不等于事件发生时间。三个时间在本页始终分开陈述。"
        ),
    },
    {
        "id": "failed_not_absence",
        "text_zh": "采集失败（FETCH_FAILED）只表示这一次抓取失败，不表示来源没有新记录，更不表示「无新事件」。",
    },
    {
        "id": "removed_not_gone",
        "text_zh": "「来源不再提供」只表示来源当前不再返回该记录，不代表现实世界中的事物消失或停止。",
    },
    {
        "id": "backfilled",
        "text_zh": "BACKFILLED 记录是事后导入的历史材料，会单独标注来源与回填原因；本轮不向账本回填任何历史记录。",
    },
    {
        "id": "not_interpretation",
        "text_zh": "本页只陈述观察到的事实与时间口径，不对新出现的公开活动做排名、评分或战略解读。",
    },
]

_ENTITY_STATUS_PRIORITY = {
    ENTITY_MAPPED: 4,
    ENTITY_PENDING_REVIEW: 3,
    ENTITY_AMBIGUOUS: 2,
    ENTITY_UNMAPPED: 1,
}

_MAPPING_STATUS_LABELS_ZH = {
    ENTITY_MAPPED: "已映射",
    ENTITY_PENDING_REVIEW: "待人工复核",
    ENTITY_AMBIGUOUS: "存在歧义",
    ENTITY_UNMAPPED: "未映射",
}


# ----------------------------------------------------------------------- helpers
@lru_cache(maxsize=None)
def _company_name(entity_id: str | None) -> str | None:
    """Chinese display name from the curated roster; never invented for a null id."""
    if not entity_id or entity_id == "__unmapped__":
        return None
    try:
        return mapping_layer.company_display_name(entity_id)
    except Exception:  # noqa: BLE001 - a missing config must not break the page
        return entity_id


@lru_cache(maxsize=None)
def _track_display(track_id: str | None) -> dict[str, Any]:
    if not track_id or track_id == "__unmapped__":
        return {"track_id": None, "name_zh": None, "name_en": None, "domain": None}
    try:
        return mapping_layer.track_display(track_id)
    except Exception:  # noqa: BLE001
        return {"track_id": track_id, "name_zh": None, "name_en": None, "domain": None}


def _relative_display_path(path: Path) -> str:
    """A ledger path suitable for JSON: relative, never an absolute host path."""
    resolved = path.expanduser()
    for base in (Path.cwd(), DATA_DIR.parent):
        try:
            return resolved.resolve().relative_to(base.resolve()).as_posix()
        except (ValueError, OSError):
            continue
    return resolved.name


def _run(builder: Callable[[ObservationLedger | None], dict[str, Any]]) -> dict[str, Any]:
    """Open the ledger read-only at request time, build the payload, close it.

    A missing file, an unreadable file or a corrupt schema all yield the honest
    empty state instead of an exception.
    """
    try:
        ledger = open_ledger_readonly(default_ledger_path())
    except (FileNotFoundError, OSError, sqlite3.Error):
        return builder(None)
    try:
        try:
            return builder(ledger)
        except sqlite3.Error:
            return builder(None)
    finally:
        ledger.close()


def _rows(ledger: ObservationLedger, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in ledger.con.execute(sql, params).fetchall()]


def _json_value(value: Any, default: Any = None) -> Any:
    if value is None:
        return default
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _json_list(value: Any) -> list[Any]:
    decoded = _json_value(value, [])
    return decoded if isinstance(decoded, list) else []


def _payload_dict(value: Any) -> dict[str, Any]:
    decoded = _json_value(value, None)
    if isinstance(decoded, dict):
        return decoded
    return {}


def _zero_window() -> dict[str, int]:
    return {"new": 0, "updated": 0, "removed": 0, "failed": 0, "total": 0}


def _source_label(source: str | None, state: Mapping[str, Any] | None = None) -> str:
    if not source:
        return "未知来源"
    label = (state or {}).get("label_zh")
    return label or SOURCE_LABELS_ZH.get(source) or source


def _record_type_label(record_type: str | None) -> str:
    if not record_type:
        return "未标注记录类型"
    return RECORD_TYPE_LABELS_ZH.get(record_type, record_type)


def _source_limit_zh(source: str | None) -> str:
    return SOURCE_LIMITATIONS_ZH.get(source or "unknown", SOURCE_LIMITATIONS_ZH["unknown"])


def _mapping_status_label(status: str | None) -> str:
    return _MAPPING_STATUS_LABELS_ZH.get(status or ENTITY_UNMAPPED, status or "未映射")


# ----------------------------------------------------------------- ledger object
def _empty_ledger_object() -> dict[str, Any]:
    return {
        "path": _relative_display_path(default_ledger_path()),
        "exists": False,
        "bytes": 0,
        "observations": 0,
        "versions": 0,
        "changes": 0,
        "live_observations": 0,
        "backfilled_observations": 0,
        "sources": 0,
        "first_live_observation_at": None,
        "first_run_at": None,
        "last_run_at": None,
        "schema_version": None,
        "honesty_zh": LEDGER_MISSING_NOTE_ZH,
    }


def _ledger_object(ledger: ObservationLedger) -> dict[str, Any]:
    counts = ledger.counts()
    live_first = _rows(
        ledger,
        "SELECT MIN(first_seen_at) AS first_seen FROM observation WHERE observation_origin='LIVE'",
    )
    return {
        "path": _relative_display_path(ledger.path),
        "exists": True,
        "bytes": int(counts.get("db_bytes") or ledger.size_bytes()),
        "observations": int(counts.get("observations") or 0),
        "versions": int(counts.get("versions") or 0),
        "changes": int(counts.get("changes") or 0),
        "live_observations": int(counts.get("live_observations") or 0),
        "backfilled_observations": int(counts.get("backfilled_observations") or 0),
        "sources": int(counts.get("sources") or 0),
        "first_live_observation_at": (live_first[0]["first_seen"] if live_first else None),
        "first_run_at": counts.get("first_run_at"),
        "last_run_at": counts.get("last_run_at"),
        "schema_version": counts.get("schema_version"),
        "honesty_zh": LEDGER_HONESTY_ZH,
    }


# --------------------------------------------------------------- aggregate maps
def _aggregate_window(rows: Iterable[Mapping[str, Any]], key_fields: Sequence[str]) -> dict[Any, dict[str, Any]]:
    aggregated: dict[Any, dict[str, Any]] = {}
    for row in rows:
        key = tuple(row.get(field) for field in key_fields)
        if len(key) == 1:
            key = key[0]
        entry = aggregated.setdefault(key, {"key": key, "status": None, "states": {}})
        status = row.get("entity_status") or row.get("track_status")
        if status and _ENTITY_STATUS_PRIORITY.get(status, 0) > _ENTITY_STATUS_PRIORITY.get(entry["status"], 0):
            entry["status"] = status
        state = row.get("change_state")
        if state:
            entry["states"][state] = entry["states"].get(state, 0) + int(row.get("n") or 0)
    return aggregated


def _state_count(entry: Mapping[str, Any] | None, state: str) -> int:
    if not entry:
        return 0
    return int((entry.get("states") or {}).get(state) or 0)


def _measured_lag(ledger: ObservationLedger, source: str | None = None) -> dict[str, Any]:
    """Project ``observatory.lag.measure_lag`` onto the §6 shape.

    The lag math itself lives in :mod:`medradar.observatory.lag` (single source of
    truth). This function only adds the honesty guard the aggregate cannot know:
    a *backfilled* record's ``first_seen_at`` is the ingestion moment, not a real
    observation, so a source whose only publish timestamps come from BACKFILLED
    records must report 无法测量 instead of a fabricated sync latency.
    """
    measured = measure_lag(ledger, source)
    block = {key: measured.get(key) for key in MEASURED_LAG_KEYS}
    if not source:
        return block
    published = _rows(
        ledger,
        "SELECT observation_origin, COUNT(*) AS n FROM observation"
        " WHERE source=? AND published_at IS NOT NULL GROUP BY observation_origin",
        (source,),
    )
    counts = {str(row["observation_origin"]): int(row["n"] or 0) for row in published}
    live_n = counts.get("LIVE", 0)
    backfilled_n = counts.get("BACKFILLED", 0)
    if block.get("measurable") and live_n == 0 and backfilled_n:
        block.update(
            {
                "measurable": False,
                "p50_hours": None,
                "p90_hours": None,
                "max_hours": None,
                "n": 0,
                "note_zh": (
                    "该来源带有发布时间的记录全部是事后回填（BACKFILLED）；"
                    "回填的 first_seen_at 是入库时刻，无法测量同步延迟"
                ),
            }
        )
    elif block.get("measurable") and backfilled_n:
        block["note_zh"] = (
            f"{block.get('note_zh') or ''}；统计中包含 {backfilled_n} 条 BACKFILLED 记录，"
            "其 first_seen_at 为回填入库时刻，不是当时的观察"
        ).strip("；")
    return block


def _coverage_entries(state: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    coverage = _json_value((state or {}).get("entity_coverage"), None)
    if not isinstance(coverage, list):
        return []
    entries: list[dict[str, Any]] = []
    for item in coverage:
        if not isinstance(item, Mapping):
            continue
        entity_id = item.get("entity_id")
        status = str(item.get("status") or "UNVERIFIED")
        entries.append(
            {
                "entity_id": entity_id,
                "name_zh": item.get("name_zh") or item.get("name") or _company_name(entity_id or "") or entity_id,
                "covered": status == "COVERED",
                "evidence_zh": item.get("evidence_zh") or "未记录核验证据",
                "identifier": item.get("identifier"),
                "status": status,
            }
        )
    return entries


def _coverage_note(entries: Sequence[Mapping[str, Any]]) -> str:
    if not entries:
        return "该来源尚未记录已验证的实体覆盖范围；「没有记录」不等于「该企业没有活动」。"
    counts: dict[str, int] = {}
    for entry in entries:
        status = str(entry.get("status") or "UNVERIFIED")
        counts[status] = counts.get(status, 0) + 1
    labels = {
        "COVERED": "已覆盖",
        "NOT_REGISTRANT": "非注册人",
        "NOT_CURRENT_REGISTRANT": "非当前注册人",
        "UNVERIFIED": "未核验",
    }
    parts = [f"{labels.get(status, status)} {count}" for status, count in counts.items()]
    return f"已逐家核验 {len(entries)} 家企业的来源覆盖：" + " · ".join(parts) + "。未覆盖 ≠ 零活动。"


def _source_ids(ledger: ObservationLedger) -> list[str]:
    registered = [row["source"] for row in _rows(ledger, "SELECT source FROM source_state ORDER BY source")]
    observed = [row["source"] for row in _rows(ledger, "SELECT DISTINCT source FROM observation ORDER BY source")]
    ordered: list[str] = []
    for source in [*registered, *observed]:
        if source and source not in ordered:
            ordered.append(source)
    return ordered


def _source_state_or_never(ledger: ObservationLedger, source: str) -> dict[str, Any]:
    state = ledger.get_source_state(source) or {}
    state.setdefault("source", source)
    state.setdefault("status", "NEVER_RUN")
    state["status_label_zh"] = SOURCE_STATUS_LABELS_ZH.get(
        state.get("status") or "NEVER_RUN", state.get("status") or "NEVER_RUN"
    )
    state.setdefault("declared_cadence_zh", None)
    state.setdefault("consecutive_failures", 0)
    return state


# --------------------------------------------------------------- time semantics
def _honest_lag(lag: Mapping[str, Any]) -> dict[str, Any]:
    """Refuse to present a self-contradictory latency as a measurement.

    ``observation_lag`` reports whatever the two stored timestamps say; if the
    source "published" a record *after* MedRadar first observed it, the fields
    contradict each other and the only honest answer is 无法测量 plus the reason.
    """
    block = dict(lag)
    value = block.get("publish_to_first_seen_hours")
    if block.get("measurable") and value is not None and float(value) < 0:
        block["measurable"] = False
        block["note_zh"] = "来源发布时间晚于 MedRadar 首次观察时间，两个时间字段相互矛盾，无法测量"
    return block


def _time_basis(lag: Mapping[str, Any], event_at: str | None,
                first_seen_at: str | None) -> dict[str, Any]:
    """The §6 row time block, built from ``observatory.lag.observation_lag``."""
    if event_at:
        event_sentence = f"该事件发生于 {event_at}"
    else:
        event_sentence = "来源未提供事件发生时间"
    seen_sentence = f"MedRadar 于 {first_seen_at} 首次观察到它" if first_seen_at else "MedRadar 首次观察时间未知"
    return {
        "event_to_publish_hours": lag.get("event_to_publish_hours"),
        "publish_to_first_seen_hours": lag.get("publish_to_first_seen_hours"),
        "event_to_first_seen_hours": lag.get("event_to_first_seen_hours"),
        "measurable": bool(lag.get("measurable")),
        "observed_later_than_event": lag.get("observed_later_than_event"),
        "statement_zh": f"{event_sentence}；{seen_sentence}。",
    }


def _evidence_zh(lag: Mapping[str, Any], published_at: str | None,
                 first_seen_at: str | None) -> str:
    value = lag.get("publish_to_first_seen_hours")
    if lag.get("measurable") and value is not None:
        return (
            f"来源发布于 {published_at}；MedRadar 于 {first_seen_at} 首次观察，"
            f"间隔 {float(value):.1f} 小时（轮询采集，非实时推送）。"
        )
    reason = lag.get("note_zh") or "来源未提供可测量的发布时间"
    return f"无法测量发布到首次观察的间隔：{reason}"


# -------------------------------------------------------------- mapping display
def _company_block(entity_id: str | None, entity_status: str | None, entity_method: str | None,
                   note_zh: str | None) -> dict[str, Any]:
    status = entity_status or ENTITY_UNMAPPED
    return {
        "entity_id": entity_id,
        "name_zh": _company_name(entity_id),
        "status": status,
        "method": entity_method,
        "note_zh": note_zh or (None if status == ENTITY_MAPPED else _mapping_status_label(status)),
    }


def _track_block(track_id: str | None, track_status: str | None) -> dict[str, Any]:
    display = _track_display(track_id)
    return {
        "track_id": track_id,
        "name_zh": display.get("name_zh"),
        "domain": display.get("domain"),
        "status": track_status or TRACK_UNMAPPED,
    }


# ------------------------------------------------------------------- change rows
def _version_sequence(ledger: ObservationLedger, observation_id: str, version_id: str | None) -> int | None:
    if not version_id:
        return None
    rows = _rows(
        ledger,
        "SELECT version_seq FROM observation_version WHERE version_id=?",
        (version_id,),
    )
    return int(rows[0]["version_seq"]) if rows else None


def _changed_field_details(ledger: ObservationLedger, observation_id: str,
                           version_id: str | None, field_names: Sequence[str]) -> list[dict[str, Any]]:
    """Field deltas with old/new previews, taken from the append-only versions."""
    if not field_names:
        return []
    details = [{"field": name, "label_zh": FIELD_LABELS_ZH.get(name, name), "old": None, "new": None}
               for name in field_names]
    if not version_id:
        return details
    sequence = _version_sequence(ledger, observation_id, version_id)
    if sequence is None:
        return details
    rows = _rows(
        ledger,
        "SELECT version_seq, payload FROM observation_version"
        " WHERE observation_id=? AND version_seq IN (?, ?) ORDER BY version_seq DESC",
        (observation_id, sequence, sequence - 1),
    )
    payloads = {int(row["version_seq"]): _payload_dict(row["payload"]) for row in rows}
    previous = payloads.get(sequence - 1, {})
    current = payloads.get(sequence, {})
    by_name = {detail["field"]: detail for detail in details}
    for name in field_names:
        detail = by_name.get(name)
        if detail is None:
            continue
        detail["old"] = short_preview(previous.get(name))
        detail["new"] = short_preview(current.get(name))
    return details


def _change_item(ledger: ObservationLedger, row: Mapping[str, Any],
                 source_labels: Mapping[str, str]) -> dict[str, Any]:
    change_state = row.get("change_state")
    field_names = _json_list(row.get("changed_fields"))
    changed_fields: list[dict[str, Any]] = []
    if change_state == CHANGE_UPDATED and field_names:
        changed_fields = _changed_field_details(
            ledger, row.get("observation_id", ""), row.get("version_id"), field_names
        )
    if change_state == CHANGE_NEW:
        version_seq: int | None = 1
    else:
        version_seq = _version_sequence(ledger, row.get("observation_id", ""), row.get("version_id"))
    lag = _honest_lag(observation_lag(row))
    time_basis = _time_basis(lag, row.get("event_at"), row.get("first_seen_at"))
    url = row.get("url")
    return {
        "change_id": row.get("change_id"),
        "observation_id": row.get("observation_id"),
        "source": row.get("source"),
        "source_label_zh": source_labels.get(row.get("source") or "", _source_label(row.get("source"))),
        "record_type": row.get("record_type"),
        "record_type_label_zh": _record_type_label(row.get("record_type")),
        "change_state": change_state,
        "change_label_zh": CHANGE_LABELS_ZH.get(change_state, change_state),
        "observed_at": row.get("observed_at"),
        "first_seen_at": row.get("first_seen_at"),
        "event_at": row.get("event_at"),
        "event_at_precision": row.get("event_at_precision"),
        "event_at_label_zh": "事件发生",
        "published_at": row.get("published_at"),
        "published_at_precision": row.get("published_at_precision"),
        "source_updated_at": row.get("o_source_updated_at"),
        "time_basis": time_basis,
        "title": row.get("title"),
        "url": url,
        "original_url": url,
        "company": _company_block(
            row.get("entity_id"),
            row.get("entity_status"),
            row.get("entity_method"),
            row.get("mapping_note_zh"),
        ),
        "track": _track_block(row.get("track_id"), row.get("track_status")),
        "changed_fields": changed_fields,
        "version": {
            "version_seq": version_seq,
            "version_count": int(row.get("version_count") or 1),
            "version_id": row.get("version_id"),
        },
        "is_revision": change_state == CHANGE_UPDATED,
        "evidence_zh": _evidence_zh(
            lag, row.get("published_at"), row.get("first_seen_at"),
        ),
    }


def _observation_item(ledger: ObservationLedger, observation: Mapping[str, Any],
                      change: Mapping[str, Any] | None, source_labels: Mapping[str, str]) -> dict[str, Any]:
    change = change or {}
    change_state = change.get("change_state") or observation.get("current_change_state")
    version_id = change.get("version_id") or observation.get("latest_version_id")
    field_names = _json_list(change.get("changed_fields"))
    changed_fields: list[dict[str, Any]] = []
    if change_state == CHANGE_UPDATED and field_names:
        changed_fields = _changed_field_details(
            ledger, observation.get("observation_id", ""), version_id, field_names
        )
    version_seq = 1 if change_state == CHANGE_NEW else _version_sequence(
        ledger, observation.get("observation_id", ""), version_id
    )
    lag = _honest_lag(observation_lag(observation))
    time_basis = _time_basis(lag, observation.get("event_at"), observation.get("first_seen_at"))
    url = change.get("url") or observation.get("original_url")
    item = {
        "change_id": change.get("change_id"),
        "observation_id": observation.get("observation_id"),
        "source": observation.get("source"),
        "source_label_zh": source_labels.get(
            observation.get("source") or "", _source_label(observation.get("source"))
        ),
        "record_type": observation.get("record_type"),
        "record_type_label_zh": _record_type_label(observation.get("record_type")),
        "change_state": change_state,
        "change_label_zh": CHANGE_LABELS_ZH.get(change_state, change_state),
        "observed_at": change.get("observed_at") or observation.get("last_change_at"),
        "first_seen_at": observation.get("first_seen_at"),
        "event_at": observation.get("event_at"),
        "event_at_precision": observation.get("event_at_precision"),
        "event_at_label_zh": "事件发生",
        "published_at": observation.get("published_at"),
        "published_at_precision": observation.get("published_at_precision"),
        "source_updated_at": observation.get("source_updated_at"),
        "time_basis": time_basis,
        "title": observation.get("title"),
        "url": url,
        "original_url": observation.get("original_url"),
        "company": _company_block(
            observation.get("entity_id"),
            observation.get("entity_status"),
            observation.get("entity_method"),
            observation.get("mapping_note_zh"),
        ),
        "track": _track_block(observation.get("track_id"), observation.get("track_status")),
        "changed_fields": changed_fields,
        "version": {
            "version_seq": version_seq,
            "version_count": int(observation.get("version_count") or 1),
            "version_id": version_id,
        },
        "is_revision": change_state == CHANGE_UPDATED,
        "evidence_zh": _evidence_zh(
            lag, observation.get("published_at"), observation.get("first_seen_at"),
        ),
    }
    # detail-only fields required by §6
    item.update(
        {
            "source_record_id": observation.get("source_record_id"),
            "ingested_at": observation.get("ingested_at"),
            "observation_status": observation.get("observation_status"),
            "observation_origin": observation.get("observation_origin"),
            "backfill_reason": observation.get("backfill_reason"),
            "last_checked_at": observation.get("last_checked_at"),
        }
    )
    return item


def _source_labels(ledger: ObservationLedger) -> dict[str, str]:
    labels: dict[str, str] = {}
    for row in _rows(ledger, "SELECT source, label_zh FROM source_state"):
        labels[row["source"]] = row["label_zh"] or SOURCE_LABELS_ZH.get(row["source"]) or row["source"]
    return labels


# --------------------------------------------------------------------- summary
def _first_change(ledger: ObservationLedger) -> dict[str, Any] | None:
    rows = _rows(
        ledger,
        "SELECT change_id, observed_at, source, title FROM observation_change"
        " ORDER BY observed_at ASC, change_id ASC LIMIT 1",
    )
    return rows[0] if rows else None


def _summary_by_source(ledger: ObservationLedger, source_labels: Mapping[str, str]) -> list[dict[str, Any]]:
    windows_24 = _aggregate_window(ledger.summary_by_source(24), ["source"])
    windows_7d = _aggregate_window(ledger.summary_by_source(WINDOWS["7d"]), ["source"])
    by_source: list[dict[str, Any]] = []
    for source in _source_ids(ledger):
        state = ledger.get_source_state(source) or {}
        entry_24 = windows_24.get(source)
        entry_7d = windows_7d.get(source)
        by_source.append(
            {
                "source": source,
                "label_zh": source_labels.get(source, _source_label(source, state)),
                "status": state.get("status") or "NEVER_RUN",
                "status_label_zh": SOURCE_STATUS_LABELS_ZH.get(
                    state.get("status") or "NEVER_RUN", state.get("status") or "NEVER_RUN"
                ),
                "last_success_at": state.get("last_success_at"),
                "last_attempt_at": state.get("last_attempt_at"),
                "declared_cadence_zh": state.get("declared_cadence_zh") or "未声明轮询周期",
                "consecutive_failures": int(state.get("consecutive_failures") or 0),
                "new_24h": _state_count(entry_24, CHANGE_NEW),
                "updated_24h": _state_count(entry_24, CHANGE_UPDATED),
                "new_7d": _state_count(entry_7d, CHANGE_NEW),
                "updated_7d": _state_count(entry_7d, CHANGE_UPDATED),
                "measured_lag": _measured_lag(ledger, source),
                "coverage_zh": _coverage_note(_coverage_entries(state)),
                "limitation_zh": _source_limit_zh(source),
            }
        )
    by_source.sort(key=lambda item: (-(item["new_24h"] + item["updated_24h"]),
                                    -(item["new_7d"] + item["updated_7d"]), item["source"]))
    return by_source


def _summary_by_company(ledger: ObservationLedger) -> list[dict[str, Any]]:
    windows_24 = _aggregate_window(ledger.summary_by_entity(24), ["entity_id"])
    windows_7d = _aggregate_window(ledger.summary_by_entity(WINDOWS["7d"]), ["entity_id"])
    totals = ledger.entity_totals()
    rows: list[dict[str, Any]] = []
    for entity_id, entry in windows_7d.items():
        total = int((totals.get(entity_id or "__unmapped__", {}) or {}).get("n") or 0)
        status = entry.get("status") or (
            (totals.get(entity_id or "__unmapped__", {}) or {}).get("entity_status")
        ) or (ENTITY_UNMAPPED if entity_id == "__unmapped__" else ENTITY_UNMAPPED)
        rows.append(
            {
                "entity_id": entity_id,
                "name_zh": _company_name(entity_id) or ("未映射" if entity_id == "__unmapped__" else entity_id),
                "new_24h": _state_count(windows_24.get(entity_id), CHANGE_NEW),
                "updated_24h": _state_count(windows_24.get(entity_id), CHANGE_UPDATED),
                "new_7d": _state_count(entry, CHANGE_NEW),
                "updated_7d": _state_count(entry, CHANGE_UPDATED),
                "total": total,
                "status": status,
            }
        )
    rows.sort(key=lambda item: (-(item["new_7d"] + item["updated_7d"]), -item["total"], str(item["entity_id"])))
    return rows


def _summary_by_track(ledger: ObservationLedger) -> list[dict[str, Any]]:
    windows_24 = _aggregate_window(ledger.summary_by_track(24), ["track_id"])
    windows_7d = _aggregate_window(ledger.summary_by_track(WINDOWS["7d"]), ["track_id"])
    rows: list[dict[str, Any]] = []
    for track_id, entry in windows_7d.items():
        display = _track_display(track_id if track_id != "__unmapped__" else None)
        rows.append(
            {
                "track_id": track_id,
                "name_zh": display.get("name_zh") or ("未映射" if track_id == "__unmapped__" else track_id),
                "domain": display.get("domain"),
                "new_24h": _state_count(windows_24.get(track_id), CHANGE_NEW),
                "updated_24h": _state_count(windows_24.get(track_id), CHANGE_UPDATED),
                "new_7d": _state_count(entry, CHANGE_NEW),
                "updated_7d": _state_count(entry, CHANGE_UPDATED),
            }
        )
    rows.sort(key=lambda item: (-(item["new_7d"] + item["updated_7d"]), str(item["track_id"])))
    return rows


def _summary(ledger: ObservationLedger | None) -> dict[str, Any]:
    generated_at = utc_now_iso()
    if ledger is None:
        return {
            "generated_at": generated_at,
            "ledger": _empty_ledger_object(),
            "windows": {window: _zero_window() for window in WINDOWS},
            "first_observation": None,
            "by_source": [],
            "by_company": [],
            "by_track": [],
            "unmapped": {
                "company": 0,
                "track": 0,
                "note_zh": "账本尚不存在，因此没有未映射记录。",
            },
            "empty": True,
            "limitations": [{"id": "ledger_missing", "text_zh": LEDGER_MISSING_NOTE_ZH}, *LIMITATIONS],
        }
    source_labels = _source_labels(ledger)
    windows = {window: ledger.window_counts(hours) for window, hours in WINDOWS.items()}
    unmapped_counts = ledger.unmapped_counts()
    first = _first_change(ledger)
    first_observation = None
    if first:
        first_observation = {
            "change_id": first.get("change_id"),
            "observed_at": first.get("observed_at"),
            "source": first.get("source"),
            "title": first.get("title"),
        }
    observations = int(ledger.counts().get("observations") or 0)
    limitations = list(LIMITATIONS)
    if unmapped_counts.get("company") or unmapped_counts.get("track"):
        limitations.append(
            {
                "id": "unmapped_records",
                "text_zh": (
                    f"当前账本中有 {int(unmapped_counts.get('company') or 0)} 条记录未映射到企业、"
                    f"{int(unmapped_counts.get('track') or 0)} 条未映射到技术赛道；未映射单独计数，不当作零活动。"
                ),
            }
        )
    return {
        "generated_at": generated_at,
        "ledger": _ledger_object(ledger),
        "windows": windows,
        "first_observation": first_observation,
        "by_source": _summary_by_source(ledger, source_labels),
        "by_company": _summary_by_company(ledger),
        "by_track": _summary_by_track(ledger),
        "unmapped": {
            "company": int(unmapped_counts.get("company") or 0),
            "track": int(unmapped_counts.get("track") or 0),
            "note_zh": "未映射记录单独计数并保留展示；未映射不等于零活动，也不等于来源没有该企业记录。",
        },
        "empty": observations == 0,
        "limitations": limitations,
    }


# ---------------------------------------------------------------------- events
def _empty_events(window: str, change: str, source: str | None, company: str | None,
                  track: str | None, q: str | None, limit: int, offset: int) -> dict[str, Any]:
    hours = WINDOWS[window]
    now = datetime.now(timezone.utc).replace(microsecond=0)
    start = now - timedelta(hours=hours)
    return {
        "total": 0,
        "limit": limit,
        "offset": offset,
        "window": {
            "id": window,
            "hours": hours,
            "start": start.isoformat(),
            "end": now.isoformat(),
        },
        "filters": {
            "change": change,
            "source": source or None,
            "company": company or None,
            "track": track or None,
            "q": q or None,
        },
        "facets": {
            "sources": [],
            "companies": [],
            "tracks": [],
            "changes": [
                {"change_state": state, "label_zh": CHANGE_LABELS_ZH[state], "count": 0}
                for state in CHANGE_ORDER
            ],
        },
        "items": [],
    }


def _normalise_facets(ledger: ObservationLedger, raw: Mapping[str, Any],
                      source_labels: Mapping[str, str]) -> dict[str, Any]:
    sources = [
        {
            "source": row.get("source"),
            "label_zh": source_labels.get(row.get("source") or "", _source_label(row.get("source"))),
            "count": int(row.get("n") or 0),
        }
        for row in raw.get("sources") or []
    ]
    companies_merged: dict[Any, int] = {}
    for row in raw.get("companies") or []:
        key = row.get("entity_id")
        companies_merged[key] = companies_merged.get(key, 0) + int(row.get("n") or 0)
    companies = [
        {
            "entity_id": entity_id,
            "name_zh": _company_name(entity_id) or ("未映射" if entity_id == "__unmapped__" else entity_id),
            "count": count,
        }
        for entity_id, count in sorted(companies_merged.items(), key=lambda item: (-item[1], str(item[0])))
    ]
    tracks_merged: dict[Any, int] = {}
    for row in raw.get("tracks") or []:
        key = row.get("track_id")
        tracks_merged[key] = tracks_merged.get(key, 0) + int(row.get("n") or 0)
    tracks = []
    for track_id, count in sorted(tracks_merged.items(), key=lambda item: (-item[1], str(item[0]))):
        display = _track_display(track_id if track_id != "__unmapped__" else None)
        tracks.append(
            {
                "track_id": track_id,
                "name_zh": display.get("name_zh") or ("未映射" if track_id == "__unmapped__" else track_id),
                "count": count,
            }
        )
    counts = {row.get("change_state"): int(row.get("n") or 0) for row in raw.get("changes") or []}
    changes = [
        {"change_state": state, "label_zh": CHANGE_LABELS_ZH[state], "count": counts.get(state, 0)}
        for state in CHANGE_ORDER
    ]
    return {"sources": sources, "companies": companies, "tracks": tracks, "changes": changes}


def _events(ledger: ObservationLedger | None, *, window: str, change: str,
            source: str | None, company: str | None, track: str | None,
            q: str | None, limit: int, offset: int) -> dict[str, Any]:
    if ledger is None:
        return _empty_events(window, change, source, company, track, q, limit, offset)
    hours = WINDOWS[window]
    states = CHANGE_STATES_FOR_FILTER[change]
    rows, total = ledger.change_rows(
        hours=hours,
        states=states,
        source=source or None,
        entity_id=company or None,
        track_id=track or None,
        query=q or None,
        limit=limit,
        offset=offset,
    )
    source_labels = _source_labels(ledger)
    facets = _normalise_facets(ledger, ledger.change_facets(hours=hours), source_labels)
    span = ledger.window_span(hours)
    return {
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "window": {"id": window, "hours": span["hours"], "start": span["start"], "end": span["end"]},
        "filters": {
            "change": change,
            "source": source or None,
            "company": company or None,
            "track": track or None,
            "q": q or None,
        },
        "facets": facets,
        "items": [_change_item(ledger, row, source_labels) for row in rows],
    }


# ------------------------------------------------------------------- detail
def _event_detail(ledger: ObservationLedger | None, observation_id: str) -> dict[str, Any]:
    if ledger is None:
        raise KeyError(f"unknown observation: {observation_id}")
    observation = ledger.observation_row(observation_id)
    if observation is None:
        raise KeyError(f"unknown observation: {observation_id}")
    changes = ledger.changes_for(observation_id)
    versions = ledger.versions(observation_id)
    source_labels = _source_labels(ledger)
    # Detail is looked up by observation id, not change id: use the newest change
    # event as the row-shaped "observation" (the change log below still lists all).
    chosen: Mapping[str, Any] | None = changes[-1] if changes else None
    item = _observation_item(ledger, observation, chosen, source_labels)
    limitations = [
        {"id": "event_vs_observed", "text_zh": LIMITED_EVENT_VS_OBSERVED},
        {"id": "failed_not_absence", "text_zh": LIMITED_FAILED},
        {"id": "source_limit", "text_zh": _source_limit_zh(observation.get("source"))},
    ]
    if observation.get("observation_origin") == ORIGIN_BACKFILLED:
        limitations.insert(
            0,
            {
                "id": "backfilled_observation",
                "text_zh": (
                    "该记录是 BACKFILLED（事后回填的历史材料），其回填原因见 observation.backfill_reason；"
                    "回填记录的「首次观察」不表示 MedRadar 在当时就观察到了它。"
                ),
            },
        )
    if observation.get("observation_status") == STATUS_REMOVED:
        limitations.append(
            {
                "id": "removed_not_gone",
                "text_zh": "该记录状态为 REMOVED_OR_UNAVAILABLE：来源当前不再提供它，不等于事物本身消失。",
            }
        )
    return {
        "observation": item,
        "versions": [
            {
                "version_seq": row.get("version_seq"),
                "version_id": row.get("version_id"),
                "captured_at": row.get("captured_at"),
                "change_state": row.get("change_state"),
                "payload_hash": row.get("payload_hash"),
                "changed_fields": _json_list(row.get("changed_fields")),
                "payload": _payload_dict(row.get("payload")),
            }
            for row in versions
        ],
        "changes": [
            {
                "change_id": row.get("change_id"),
                "change_state": row.get("change_state"),
                "observed_at": row.get("observed_at"),
                "version_id": row.get("version_id"),
                "changed_fields": _json_list(row.get("changed_fields")),
            }
            for row in changes
        ],
        "mapping_history": [
            {
                "mapping_version": row.get("mapping_version"),
                "mapped_at": row.get("mapped_at"),
                "entity_id": row.get("entity_id"),
                "entity_status": row.get("entity_status"),
                "track_id": row.get("track_id"),
                "track_status": row.get("track_status"),
                "note_zh": row.get("note_zh"),
            }
            for row in ledger.mapping_history(observation_id)
        ],
        "status_history": [
            {
                "changed_at": row.get("changed_at"),
                "status": row.get("status"),
                "note": row.get("note"),
            }
            for row in ledger.status_history(observation_id)
        ],
        "sync_context": {
            "first_seen_run_id": observation.get("first_seen_run_id"),
            "run": ledger.run_row(observation.get("first_seen_run_id") or ""),
            "source_state": ledger.get_source_state(observation.get("source") or ""),
        },
        "limitations": limitations,
    }


LIMITED_EVENT_VS_OBSERVED = (
    "版本历史来自观察账本：每次版本都在真实的抓取时刻写入，且不可修改；"
    "「首次观察」时间是采集器首次成功抓取该记录的时刻。"
)
LIMITED_FAILED = "采集失败只说明本次抓取失败，不说明来源没有新记录。"


# ------------------------------------------------------------------- sources
def _recent_runs(ledger: ObservationLedger, source: str, limit: int = 6) -> list[dict[str, Any]]:
    rows = _rows(
        ledger,
        "SELECT run_id, started_at, finished_at, status, trigger, requests, records_seen,"
        " records_new, records_updated, records_unchanged, records_removed, error_detail"
        " FROM sync_run WHERE source=? ORDER BY started_at DESC LIMIT ?",
        (source, int(limit)),
    )
    return rows


def _recent_failures(ledger: ObservationLedger, source: str, limit: int = 6) -> list[dict[str, Any]]:
    rows = _rows(
        ledger,
        "SELECT occurred_at, kind, message, http_status, retryable FROM source_failure"
        " WHERE source=? ORDER BY occurred_at DESC LIMIT ?",
        (source, int(limit)),
    )
    for row in rows:
        if row.get("retryable") is not None:
            row["retryable"] = bool(row["retryable"])
    return rows


def _source_counts(ledger: ObservationLedger, source: str) -> dict[str, int]:
    rows = _rows(
        ledger,
        "SELECT COUNT(*) AS runs_total,"
        " COALESCE(SUM(CASE WHEN status='OK' THEN 1 ELSE 0 END), 0) AS runs_ok,"
        " COALESCE(SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END), 0) AS runs_failed,"
        " COALESCE(SUM(records_failed), 0) AS records_failed"
        " FROM sync_run WHERE source=?",
        (source,),
    )
    run_stats = rows[0] if rows else {}
    observations = _rows(ledger, "SELECT COUNT(*) AS n FROM observation WHERE source=?", (source,))
    windows_7d = _aggregate_window(ledger.summary_by_source(WINDOWS["7d"]), ["source"])
    entry = windows_7d.get(source)
    return {
        "runs_total": int(run_stats.get("runs_total") or 0),
        "runs_ok": int(run_stats.get("runs_ok") or 0),
        "runs_failed": int(run_stats.get("runs_failed") or 0),
        "observations": int(observations[0]["n"] or 0) if observations else 0,
        "new_7d": _state_count(entry, CHANGE_NEW),
        "updated_7d": _state_count(entry, CHANGE_UPDATED),
        "records_failed": int(run_stats.get("records_failed") or 0),
    }


def _source_panel(ledger: ObservationLedger, source: str) -> dict[str, Any]:
    state = _source_state_or_never(ledger, source)
    coverage = _coverage_entries(state)
    status = state.get("status") or "NEVER_RUN"
    return {
        "source": source,
        "label_zh": _source_label(source, state),
        "status": status,
        "status_label_zh": SOURCE_STATUS_LABELS_ZH.get(status, status),
        "declared_cadence_zh": state.get("declared_cadence_zh") or "未声明轮询周期",
        "last_attempt_at": state.get("last_attempt_at"),
        "last_success_at": state.get("last_success_at"),
        "last_failure_at": state.get("last_failure_at"),
        "consecutive_failures": int(state.get("consecutive_failures") or 0),
        "watermark": _json_value(state.get("watermark"), None),
        "watermark_updated_at": state.get("watermark_updated_at"),
        "structure": {
            "signature": state.get("structure_signature"),
            "changed_at": state.get("structure_changed_at"),
            "note_zh": state.get("structure_note_zh"),
        },
        "counts": _source_counts(ledger, source),
        "recent_runs": _recent_runs(ledger, source),
        "recent_failures": _recent_failures(ledger, source),
        "entity_coverage": coverage,
        "measured_lag": _measured_lag(ledger, source),
        "coverage_note_zh": _coverage_note(coverage),
        "limitation_zh": _source_limit_zh(source),
    }


def _sources(ledger: ObservationLedger | None) -> dict[str, Any]:
    generated_at = utc_now_iso()
    if ledger is None:
        return {"sources": [], "generated_at": generated_at}
    return {
        "sources": [_source_panel(ledger, source) for source in _source_ids(ledger)],
        "generated_at": generated_at,
    }


# -------------------------------------------------------------------- replay
def _normalise_as_of(value: Any) -> str:
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    text = str(value or "").strip()
    if not text:
        raise ValueError("as_of is required (ISO 8601)")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"as_of must be ISO 8601, got {text!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _replay(ledger: ObservationLedger | None, as_of: str, source: str | None,
            limit: int) -> dict[str, Any]:
    moment = _normalise_as_of(as_of)
    if ledger is None:
        return {
            "as_of": moment,
            "policy_zh": _REPLAY_POLICY_ZH,
            "total": 0,
            "excluded_discovered_later": 0,
            "items": [],
        }
    snapshot = ledger.snapshot(moment, source=source or None, limit=limit)
    items = [
        {
            "observation_id": row.get("observation_id"),
            "source": row.get("source"),
            "title": row.get("title"),
            "first_seen_at": row.get("first_seen_at"),
            "event_at": row.get("event_at"),
            "version_seq": row.get("version_seq"),
            "captured_at": row.get("captured_at"),
            "status": row.get("status_at"),
            "payload_hash": row.get("payload_hash"),
        }
        for row in snapshot.get("items") or []
    ]
    return {
        "as_of": snapshot.get("as_of") or moment,
        "policy_zh": snapshot.get("policy_zh") or _REPLAY_POLICY_ZH,
        "total": len(items),
        "excluded_discovered_later": int(snapshot.get("excluded_discovered_later") or 0),
        "items": items,
    }


_REPLAY_POLICY_ZH = (
    "只包含在 as_of 之前已被 MedRadar 实际观察到的记录（first_seen_at <= as_of）；"
    "之后才发现的历史记录一律排除，即使其事件日期更早。"
)


# ----------------------------------------------------------------- public API
def _validated_window(window: str) -> str:
    value = str(window or "").strip()
    if value not in WINDOWS:
        raise ValueError(f"window must be one of {', '.join(WINDOWS)}; got {value!r}")
    return value


def _validated_change(change: str) -> str:
    value = str(change or "all").strip()
    if value not in CHANGE_STATES_FOR_FILTER:
        raise ValueError(f"change must be one of {', '.join(CHANGE_STATES_FOR_FILTER)}; got {value!r}")
    return value


def summary() -> dict[str, Any]:
    """Ledger health, per-window change counts, per-source/company/track rollups."""
    return _run(_summary)


def events(*, window: str = "7d", change: str = "all", source: str | None = None,
           company: str | None = None, track: str | None = None, q: str | None = None,
           limit: int = 50, offset: int = 0) -> dict[str, Any]:
    """Observed changes in a time window, with window-scoped facets."""
    window = _validated_window(window)
    change = _validated_change(change)
    rows_limit = max(1, min(int(limit or 50), 200))
    rows_offset = max(0, int(offset or 0))
    return _run(
        lambda ledger: _events(
            ledger,
            window=window,
            change=change,
            source=source or None,
            company=company or None,
            track=track or None,
            q=q or None,
            limit=rows_limit,
            offset=rows_offset,
        )
    )


def event_detail(observation_id: str) -> dict[str, Any]:
    """One observation with its version chain, mapping history and sync context."""
    if not observation_id:
        raise KeyError("unknown observation: (empty)")
    return _run(lambda ledger: _event_detail(ledger, observation_id))


def sources() -> dict[str, Any]:
    """Per-source sync status, measured lag, recent runs/failures and coverage."""
    return _run(_sources)


def replay(*, as_of: str, source: str | None = None, limit: int = 100) -> dict[str, Any]:
    """What the ledger actually knew at ``as_of`` (later discoveries excluded)."""
    rows_limit = max(1, min(int(limit or 100), 500))
    return _run(lambda ledger: _replay(ledger, as_of, source or None, rows_limit))


__all__ = ["summary", "events", "event_detail", "sources", "replay"]
