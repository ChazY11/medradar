"""PRODUCT-004 Intelligence Brief: from a research question to a sourced brief.

The brief is a **derived artefact**, never a new source of truth. It reads the same dataset and the
same comparison code as every other page, so a number in the brief is the number on the screen:

* company brief  -> ``dataset.filter_events`` + ``dataset.counts`` + ``aggregate``;
* comparison     -> ``compare.build_compare`` (identical to /api/compare);
* device brief   -> the PRODUCT-003 device index payload (identical to /api/devices/{id}).

Findings are produced by a small, explicit rule set. Each finding states the records that produced
it, the rule and its inputs, what it does **not** mean, and a filter that reproduces it. There is no
prediction, no generated prose and no claim of causality: a count is a count of FDA records.

The module is deliberately separate from ``export.py``: the old exports remain valid, and the brief
adds a windowed, question-first deliverable instead of changing what already ships.
"""
from __future__ import annotations

import csv
import io
import time
from collections import Counter
from datetime import date
from typing import Any, Iterable, Sequence

from .attribution import status as status_module
from .compare import (
    MAX_ORGS,
    MIN_ORGS,
    build_compare,
    complete_years,
    default_window,
)
from .dataset import (
    EVENT_TYPE_LABELS,
    EVENT_TYPE_ORDER,
    SOURCE_NAMES,
    Dataset,
    Event,
    aggregate,
)

BRIEF_SCHEMA = "medradar.brief.v1"
RULES_VERSION = "brief-findings-v1"

#: The small set of windows the UI offers. ``None`` years means an explicit from/to window.
WINDOW_YEARS = (3, 5, 10)

#: A finding is only emitted when its rule fires; this bounds how many one brief can show.
MAX_FINDINGS = 7

_TYPE_LABELS_ZH = {
    "510k": "510(k) 上市前通知",
    "pma": "PMA 原始批准",
    "pma_supplement": "PMA 补充批准",
    "recall": "召回",
}

_TYPE_DEFINITIONS_EN = {
    "510k": "A 510(k) premarket notification clearance: FDA found the device substantially equivalent to a legally marketed predicate device. It is not an approval and not a new product launch.",
    "pma": "An original premarket approval: the first FDA approval of a Class III device under a PMA number. Supplements to it are counted separately.",
    "pma_supplement": "A supplement to an existing PMA: a change to an already approved device. It is not a new device and is never counted as one.",
    "recall": "A device recall record: a safety action. It is not a product failure rate and not evidence about a company's quality system.",
}
_TYPE_DEFINITIONS_ZH = {
    "510k": "510(k) 上市前通知：FDA 认定该器械与已合法上市的对比器械实质等同。它不是批准，也不等于新产品发布。",
    "pma": "PMA 原始批准：FDA 依据某个 PMA 编号首次批准第三类器械。其补充申请单独计数。",
    "pma_supplement": "PMA 补充申请：对已获批器械的变更，不是新器械，也绝不按新器械计数。",
    "recall": "召回记录：一种安全行动，不是产品故障率，也不构成对企业质量体系的证明。",
}

COUNTING_RULE_EN = (
    "One record is one row in the FDA source dataset. Counts are attributed records: an applicant "
    "string must match the reviewed identity registry exactly. Different event types are never added "
    "together or compared with each other as if they measured one thing."
)
COUNTING_RULE_ZH = (
    "一条记录对应 FDA 源数据集中的一行。计数仅包含已归属记录：申请人名称必须与已审核的身份登记精确匹配。"
    "不同类型的事件不会被合并相加，也不会被当作同一指标互相比较。"
)

_CANNOT_CONCLUDE_COMMON_EN = (
    "FDA records do not measure innovation, R&D spending, market share, revenue, clinical quality or "
    "global regulatory activity. A missing record is not evidence that no activity happened."
)
_CANNOT_CONCLUDE_COMMON_ZH = (
    "FDA 记录不衡量创新能力、研发投入、市场份额、收入、临床质量或全球监管活动。缺少记录不等于没有发生活动。"
)


# --------------------------------------------------------------------------- helpers
def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _n(value: int | None) -> str:
    return "unknown" if value is None else f"{value:,}"


def _pct(value: float | None, digits: int = 1, signed: bool = False) -> str:
    if value is None:
        return "unknown"
    text = f"{value * 100:+.{digits}f}%" if signed else f"{value * 100:.{digits}f}%"
    return text


def _txt(en: str, zh: str) -> dict[str, str]:
    return {"en": en, "zh": zh}


def pick(value: Any, lang: str = "en") -> Any:
    """Pick one language from a {en, zh} payload, falling back to English."""
    if isinstance(value, dict) and "en" in value and "zh" in value:
        return value.get(lang) or value.get("en") or ""
    return value


def _parse(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def events_url(
    *,
    org: str | None = None,
    types: Sequence[str] | None = None,
    scope: dict[str, Any] | None = None,
    category: str | None = None,
    product_code: str | None = None,
    q: str | None = None,
) -> str:
    """A reproducible event-browser URL for the same records a metric counts."""
    params: list[tuple[str, str]] = []
    if org:
        params.append(("org", org))
    if types:
        params.append(("types", ",".join(types)))
    if scope:
        if scope.get("from"):
            params.append(("from", str(scope["from"])))
        if scope.get("to"):
            params.append(("to", str(scope["to"])))
    if category:
        params.append(("category", category))
    if product_code:
        params.append(("product_code", str(product_code).upper()))
    if q:
        params.append(("q", q))
    return "/events" + ("?" + "&".join(f"{key}={value}" for key, value in params) if params else "")


def _record_ref(event: Event) -> dict[str, Any]:
    """The minimum of a record needed to recognise and verify it in a finding."""
    return {
        "event_id": event.event_id,
        "official_id": event.official_id,
        "event_type": event.event_type,
        "event_date": event.event_date,
        "published_at": event.published_at,
        "first_observed_at": event.first_observed_at,
        "official_url": event.official_url,
        "device_name": event.device_name,
        "applicant_name": event.applicant_name,
        "organization_key": event.organization_key,
        "product_code": event.product_code,
        "attribution_verification": event.attribution_verification,
        "attribution_verified": event.attribution_verified,
        "record_state": event.record_state,
        "verification_label_en": status_module.STATUS_LABELS_EN.get(event.attribution_verification, event.attribution_verification),
        "verification_label_zh": status_module.STATUS_LABELS_ZH.get(event.attribution_verification, event.attribution_verification),
    }


def _sample(events: Iterable[Event], limit: int = 5, order: str = "date_desc") -> list[dict[str, Any]]:
    items = list(events)
    if order == "date_desc":
        items.sort(key=lambda event: (event.event_date is None, _neg(event.event_date), event.event_id))
    elif order == "date_asc":
        items.sort(key=lambda event: (event.event_date is None, event.event_date or "", event.event_id))
    return [_record_ref(event) for event in items[:limit]]


def _neg(value: str | None) -> int:
    if not value:
        return 0
    try:
        return -int(value.replace("-", ""))
    except ValueError:
        return 0


def _by_type(events: Sequence[Event]) -> dict[str, int]:
    counts = {event_type: 0 for event_type in EVENT_TYPE_ORDER}
    for event in events:
        counts[event.event_type] = counts.get(event.event_type, 0) + 1
    return counts


def _type_rows(events: Sequence[Event], total: int) -> list[dict[str, Any]]:
    counts = _by_type(events)
    return [
        {
            "event_type": event_type,
            "label": EVENT_TYPE_LABELS[event_type],
            "label_zh": _TYPE_LABELS_ZH[event_type],
            "count": counts.get(event_type, 0),
            "share": round(counts.get(event_type, 0) / total, 6) if total else None,
            "definition": _txt(_TYPE_DEFINITIONS_EN[event_type], _TYPE_DEFINITIONS_ZH[event_type]),
        }
        for event_type in EVENT_TYPE_ORDER
    ]


def _year_rows(events: Sequence[Event], complete: Sequence[str], scope: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-year counts inside the window. Partial calendar years are marked, never dropped."""
    aggregation = aggregate(events)
    rows = []
    complete_set = set(complete)
    for row in aggregation["by_year"]:
        moment_from = scope.get("from")
        moment_to = scope.get("to")
        if moment_from and row["year"] < str(moment_from)[:4]:
            continue
        if moment_to and row["year"] > str(moment_to)[:4]:
            continue
        rows.append({
            **row,
            "partial": row["year"] not in complete_set,
        })
    return rows


def _source_rows(events: Sequence[Event]) -> list[dict[str, Any]]:
    rows = []
    for source_id in SOURCE_NAMES:
        subset = [event for event in events if event.source_id == source_id]
        dates = [event.event_date for event in subset if event.event_date]
        rows.append({
            "source_id": source_id,
            "name": SOURCE_NAMES[source_id],
            "records": len(subset),
            "min_event_date": min(dates) if dates else None,
            "max_event_date": max(dates) if dates else None,
            "publication_date_published_by_source": source_id == "openfda_recall",
        })
    return rows


def _specialty_rows(events: Sequence[Event]) -> dict[str, Any]:
    aggregation = aggregate(events)
    total = len(events)
    rows = []
    for row in aggregation["by_category"]:
        rows.append({
            "id": row["id"],
            "label": row["label"],
            "count": row["total"],
            "share": round(row["total"] / total, 6) if total else None,
            "by_type": row["counts"],
        })
    unknown = next((row["count"] for row in rows if row["id"] == "unknown"), 0)
    unclassified = next((row["count"] for row in rows if row["id"] == "unclassified"), 0)
    return {
        "rows": rows,
        "unknown_count": unknown,
        "unknown_share": round(unknown / total, 6) if total else None,
        "unclassified_count": unclassified,
        "note": _txt(
            "The category is the FDA medical specialty of the record's product code. The FDA "
            "classification dictionary itself states 'Unknown' for many class III product codes, so "
            "this table is incomplete by source; read the product-code table next to it.",
            "类别来自该记录产品代码对应的 FDA 医学专科。FDA 分类字典本身对许多第三类产品代码标注为“Unknown”，"
            "因此该表受来源限制并不完整；请同时阅读产品代码表。",
        ),
    }


# --------------------------------------------------------------------------- findings
def _finding(
    *,
    finding_id: str,
    category: str,
    title_en: str,
    title_zh: str,
    statement_en: str,
    statement_zh: str,
    cannot_en: str,
    cannot_zh: str,
    basis: dict[str, Any],
    evidence: dict[str, Any],
    drilldown: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": finding_id,
        "category": category,  # "finding" | "caution"
        "title": _txt(title_en, title_zh),
        "statement": _txt(statement_en, statement_zh),
        "cannot_conclude": _txt(cannot_en, cannot_zh),
        "basis": basis,
        "evidence": evidence,
        "drilldown": drilldown or {},
    }


def _finding_evidence(records: Sequence[Event], limit: int = 5, note_en: str = "", note_zh: str = "") -> dict[str, Any]:
    return {
        "record_count": len(records),
        "records": _sample(records, limit=limit),
        "note": _txt(note_en, note_zh) if note_en or note_zh else None,
    }


def company_findings(
    dataset: Dataset,
    key: str,
    events: Sequence[Event],
    scope: dict[str, Any],
    counts: dict[str, Any],
    families: Sequence[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Rules over the window's records. Every rule is deterministic and re-computable."""
    findings: list[dict[str, Any]] = []
    total = len(events)
    if total == 0:
        return findings
    by_type = _by_type(events)
    labels = EVENT_TYPE_LABELS
    window = scope["label_short"]
    org_key = key

    # 1. Pathway concentration.
    top_type, top_count = max(by_type.items(), key=lambda item: item[1])
    top_share = top_count / total if total else 0.0
    if total >= 40 and top_share >= 0.75:
        subset = [event for event in events if event.event_type == top_type]
        findings.append(_finding(
            finding_id="pathway_concentration",
            category="finding",
            title_en="One regulatory pathway dominates the window",
            title_zh="窗口内由单一监管路径主导",
            statement_en=(
                f"{_n(top_count)} of {_n(total)} records ({_pct(top_share)}) in {window} are "
                f"{labels[top_type]} records. The remaining {_n(total - top_count)} records are spread "
                "across the other pathways."
            ),
            statement_zh=(
                f"{window} 的 {_n(total)} 条记录中有 {_n(top_count)} 条（{_pct(top_share)}）为"
                f"{_TYPE_LABELS_ZH[top_type]}。其余 {_n(total - top_count)} 条分布在其他监管路径。"
            ),
            cannot_en=(
                "A dominant pathway is a composition fact. A PMA supplement is a change to an approved "
                "device, so a supplement-heavy window does not mean a new-product-heavy window, and the "
                "share cannot be converted into a product or revenue claim."
            ),
            cannot_zh=(
                "单一监管路径占主导只是构成事实。PMA 补充申请是对已获批器械的变更，因此补充申请为主并不等于新产品为主，"
                "该占比也不能被换算为产品或收入结论。"
            ),
            basis={
                "rule": "top event type share >= 75% and total records >= 40",
                "inputs": {"total_records": total, "by_type": by_type, "top_type": top_type, "top_share": round(top_share, 6)},
                "rules_version": RULES_VERSION,
            },
            evidence=_finding_evidence(
                subset, limit=5,
                note_en="Five most recent records of the dominant pathway; the filter reproduces all of them.",
                note_zh="该主导路径最近的五条记录；使用筛选链接可复现全部记录。",
            ),
            drilldown={
                "url": events_url(org=org_key, types=[top_type], scope=scope),
                "label": _txt("Open every record of this pathway in the window", "在事件浏览器中打开该路径的全部记录"),
            },
        ))

    # 2. Recall dominance: a caution, because a recall share is routinely misread as a quality rate.
    recall_count = by_type.get("recall", 0)
    recall_share = recall_count / total if total else 0.0
    if recall_count >= 10 and recall_share >= 0.5:
        subset = [event for event in events if event.event_type == "recall"]
        findings.append(_finding(
            finding_id="recall_dominant_window",
            category="caution",
            title_en="Recalls dominate the window",
            title_zh="窗口内以召回记录为主",
            statement_en=(
                f"{_n(recall_count)} of {_n(total)} records ({_pct(recall_share)}) are recall records. "
                "A recall is a safety action with its own initiation date; it is not a product launch."
            ),
            statement_zh=(
                f"{_n(total)} 条记录中有 {_n(recall_count)} 条（{_pct(recall_share)}）为召回记录。"
                "召回是一种带有自身启动日期的安全行动，不是产品发布。"
            ),
            cannot_en=(
                "This share is not a defect rate, a quality ranking or a measure of patient risk. Recall "
                "records also depend on the source's own coverage and reporting."
            ),
            cannot_zh="该占比不是故障率、质量排名或患者风险指标。召回记录还受来源自身覆盖与报告方式影响。",
            basis={
                "rule": "recall share >= 50% and recall records >= 10",
                "inputs": {"total_records": total, "recall_records": recall_count, "recall_share": round(recall_share, 6)},
                "rules_version": RULES_VERSION,
            },
            evidence=_finding_evidence(subset, limit=5),
            drilldown={"url": events_url(org=org_key, types=["recall"], scope=scope), "label": _txt("Open recall records", "打开召回记录")},
        ))

    # 3. Year-over-year record-count shifts on complete calendar years only.
    years = [str(year) for year in scope.get("complete_years") or []]
    if len(years) >= 3:
        per_year: dict[str, dict[str, int]] = {}
        for event in events:
            if event.year:
                per_year.setdefault(event.year, {}).setdefault(event.event_type, 0)
                per_year[event.year][event.event_type] += 1
        candidates: list[tuple[str, int, float, int]] = []
        for event_type in EVENT_TYPE_ORDER:
            if by_type.get(event_type, 0) < 20:
                continue
            latest = years[-1]
            baseline_years = years[-3:-1]
            baseline = [per_year.get(year, {}).get(event_type, 0) for year in baseline_years]
            if not baseline:
                continue
            mean = sum(baseline) / len(baseline)
            value = per_year.get(latest, {}).get(event_type, 0)
            if mean >= 10 and value >= 10 and mean > 0:
                change = (value - mean) / mean
                if abs(change) >= 0.4:
                    candidates.append((event_type, value, mean, change))
        # Largest absolute change first; at most two so the brief stays readable.
        candidates.sort(key=lambda item: -abs(item[3]))
        for event_type, value, mean, change in candidates[:2]:
            subset = [event for event in events if event.event_type == event_type and event.year == years[-1]]
            direction_en = "rose" if change > 0 else "fell"
            direction_zh = "上升" if change > 0 else "下降"
            findings.append(_finding(
                finding_id="activity_shift_" + event_type,
                category="finding",
                title_en=f"{labels[event_type]} records per year changed sharply",
                title_zh=f"{_TYPE_LABELS_ZH[event_type]}年度记录数明显变化",
                statement_en=(
                    f"{labels[event_type]} records {direction_en} from a {mean:.0f}-record average in "
                    f"{years[-3]}–{years[-2]} to {_n(value)} in {years[-1]} ({_pct(change, signed=True)} "
                    "against that average)."
                ),
                statement_zh=(
                    f"{_TYPE_LABELS_ZH[event_type]}记录从 {years[-3]}–{years[-2]} 的均值 {mean:.0f} 条"
                    f"{direction_zh}至 {years[-1]} 的 {_n(value)} 条（相对均值为 {_pct(change, signed=True)}）。"
                ),
                cannot_en=(
                    "This is a change in the number of FDA records in this window, not a cause. A "
                    "reorganisation, a name change, a backlog or a change in what FDA published can "
                    "produce the same pattern."
                ),
                cannot_zh=(
                    "这是该窗口内 FDA 记录数量的变化，不是原因。组织调整、名称变更、积压或 FDA 发布方式变化都可能产生同样形状。"
                ),
                basis={
                    "rule": "|latest complete year - mean(previous two complete years)| / mean >= 40%, both >= 10 records",
                    "inputs": {
                        "event_type": event_type, "latest_year": years[-1], "latest_count": value,
                        "baseline_years": years[-3:-1], "baseline_counts": [per_year.get(year, {}).get(event_type, 0) for year in years[-3:-1]],
                        "baseline_mean": round(mean, 3), "relative_change": round(change, 6),
                    },
                    "rules_version": RULES_VERSION,
                },
                evidence=_finding_evidence(subset, limit=5),
                drilldown={
                    "url": events_url(org=org_key, types=[event_type], scope={**scope, "from": f"{years[-1]}-01-01", "to": f"{years[-1]}-12-31"}),
                    "label": _txt(f"Open {labels[event_type]} records for {years[-1]}", f"打开 {years[-1]} 年的{_TYPE_LABELS_ZH[event_type]}记录"),
                },
            ))

    # 4. A PMA family with a long supplement history is a device-level fact worth following up.
    for family in (families or [])[:1]:
        supplements = int(family.get("supplements_in_window") or 0)
        if supplements >= 20:
            findings.append(_finding(
                finding_id="pma_family_scale",
                category="finding",
                title_en="A long-lived PMA family carries many supplement decisions",
                title_zh="某一 PMA 家族存在大量补充申请",
                statement_en=(
                    f"PMA {family.get('pma_number')} ({family.get('name')}) has {_n(supplements)} supplement "
                    f"decisions inside this window, between {family.get('first_event_date')} and "
                    f"{family.get('last_event_date')}. The family has "
                    f"{_n(family.get('supplement_count_total'))} supplements in the snapshot in total."
                ),
                statement_zh=(
                    f"PMA {family.get('pma_number')}（{family.get('name')}）在本窗口内有 {_n(supplements)} 条补充申请决定，"
                    f"时间范围为 {family.get('first_event_date')} 至 {family.get('last_event_date')}。该家族在快照中共有 "
                    f"{_n(family.get('supplement_count_total'))} 条补充申请。"
                ),
                cannot_en=(
                    "A supplement changes an already approved device; it is not a new device, a new "
                    "indication or a commercial launch. The count also does not show whether the changes "
                    "were incremental or substantial."
                ),
                cannot_zh=(
                    "补充申请变更的是已获批器械，不是新器械、新适应症或商业发布。该计数也不能说明变更是渐进式还是重大变更。"
                ),
                basis={
                    "rule": "top PMA family in the window with >= 20 supplement decisions",
                    "inputs": {k: family.get(k) for k in ("pma_number", "name", "supplements_in_window", "supplement_count_total", "first_event_date", "last_event_date", "family_id")},
                    "rules_version": RULES_VERSION,
                },
                evidence={"record_count": supplements, "records": family.get("evidence_records") or [], "note": _txt("Supplement decisions from this family in the window.", "该家族在本窗口内的补充申请决定。")},
                drilldown={"url": family.get("device_url") or "/devices", "label": _txt("Open the device family and its official history", "打开该器械家族及其官方历史")},
            ))

    # 5. Coverage caution: the FDA itself states no specialty for many records.
    unknown_stated = 0
    unclassified = 0
    for event in events:
        if event.category is None:
            unclassified += 1
        elif event.category.id == "unknown":
            unknown_stated += 1
    unknown = unknown_stated + unclassified
    unknown_share = unknown / total if total else 0.0
    if total >= 50 and unknown_share >= 0.25:
        findings.append(_finding(
            finding_id="specialty_not_stated",
            category="caution",
            title_en="The FDA classification states no medical specialty for many records",
            title_zh="许多记录的 FDA 分类未给出医学专科",
            statement_en=(
                f"{_n(unknown_stated)} of {_n(total)} records ({_pct(unknown_stated / total)}) carry the "
                f"official specialty value 'Unknown', and a further {_n(unclassified)} use a product code "
                f"absent from the dictionary ({_pct(unknown / total)} together). Any technology-area statement "
                "based on specialty alone is therefore incomplete."
            ),
            statement_zh=(
                f"{_n(total)} 条记录中有 {_n(unknown_stated)} 条（{_pct(unknown_stated / total)}）的官方专科取值为“Unknown”，"
                f"另有 {_n(unclassified)} 条的产品代码不在字典中（合计 {_pct(unknown / total)}）。"
                "因此，仅依据医学专科做出的技术领域判断并不完整。"
            ),
            cannot_en=(
                "'Unknown' is a value in the official dictionary, not a MedRadar gap and not a sign that the "
                "records are unclassified. The brief shows official product-code families next to this table "
                "so those records remain readable."
            ),
            cannot_zh=(
                "“Unknown”是官方字典中的取值，不是 MedRadar 的缺失，也不代表这些记录没有分类。简报在专科表旁提供"
                "官方产品代码家族表，使这些记录仍可解读。"
            ),
            basis={
                "rule": "share of window records whose product code has no specialty or specialty 'Unknown' >= 25%, total >= 50",
                "inputs": {"total_records": total, "unknown_specialty_records": unknown_stated, "unclassified_records": unclassified, "unknown_records": unknown, "unknown_share": round(unknown_share, 6)},
                "rules_version": RULES_VERSION,
            },
            evidence={"record_count": unknown, "records": _sample([event for event in events if event.category is None or event.category.id == "unknown"], limit=3), "note": _txt("Examples only; the finding is a property of the whole window.", "仅为示例；该发现是对整个窗口的性质描述。")},
        ))

    # 6. Attribution caution: provisional mappings behind the numbers.
    provisional_share = counts.get("provisional_share")
    provisional = int(counts.get("provisional") or 0)
    if total >= 50 and provisional_share is not None and provisional_share >= 0.25:
        findings.append(_finding(
            finding_id="provisional_attribution",
            category="caution",
            title_en="A large share of these records rests on provisional applicant mappings",
            title_zh="相当比例的记录依赖暂定的申请人映射",
            statement_en=(
                f"{_n(provisional)} of {_n(total)} attributed records ({_pct(provisional_share)}) come from "
                "applicant spellings whose mapping has no independent verification."
            ),
            statement_zh=(
                f"{_n(total)} 条已归属记录中有 {_n(provisional)} 条（{_pct(provisional_share)}）来自尚无独立核验的申请人名称映射。"
            ),
            cannot_en=(
                "A provisional mapping is a working assumption, not a verified identity. Any comparison that "
                "depends on it inherits that assumption; see the attribution audit on the Sources page."
            ),
            cannot_zh=(
                "暂定映射是工作假设，而非已核验身份。依赖它的任何比较都会继承该假设；请查看“数据来源与覆盖”页面的归属审计。"
            ),
            basis={
                "rule": "provisional share >= 25% and window records >= 50",
                "inputs": {"total_records": total, "provisional_records": provisional, "provisional_share": provisional_share},
                "rules_version": RULES_VERSION,
            },
            evidence={"record_count": provisional, "records": _sample([event for event in events if not event.attribution_verified and event.attribution_verification != status_module.RULE_VERIFIED], limit=3), "note": _txt("Verification state is shown per record in the evidence drawer.", "每条记录的核验状态可在证据面板中查看。")},
            drilldown={"url": "/sources", "label": _txt("Open the attribution audit", "打开归属审计")},
        ))

    findings.sort(key=_finding_order)
    return findings[:MAX_FINDINGS]


#: Display order by rule, not alphabetically: the analyst should read composition and change before
#: the cautions, and the device fact after the record-level facts.
_FINDING_ORDER = {
    "pathway_concentration": 10,
    "activity_shift_510k": 20,
    "activity_shift_pma": 21,
    "activity_shift_pma_supplement": 22,
    "activity_shift_recall": 23,
    "pma_family_scale": 30,
    "product_family_overlap": 40,
    "coverage_asymmetry": 50,
    "recall_dominant_window": 60,
    "specialty_not_stated": 70,
    "verification_asymmetry": 80,
    "provisional_attribution": 90,
}


def _finding_order(finding: dict[str, Any]) -> tuple[int, str]:
    return (0 if finding.get("category") == "finding" else 1, _FINDING_ORDER.get(str(finding.get("id")), 100), str(finding.get("id")))


def _coverage_assessment(sides: Sequence[dict[str, Any]], comparability: dict[str, Any]) -> dict[str, Any]:
    """Whether the two sides' source coverage is symmetric, stated explicitly either way."""
    symmetric = bool(comparability.get("coverage_symmetric"))
    per_side = []
    for side in sides:
        present = [row for row in side["coverage"]["sources"] if row["records"]]
        per_side.append({
            "key": side["key"],
            "name": side["display_name"],
            "sources": [
                {"source_id": row["source_id"], "name": row["name"], "records": row["records"],
                 "min_event_date": row["min_event_date"], "max_event_date": row["max_event_date"]}
                for row in present
            ],
            "source_count": len(present),
        })
    return {
        "symmetric": symmetric,
        "per_side": per_side,
        "status": "symmetric" if symmetric else "asymmetric",
        "note": _txt(
            "Source coverage is the question of whether both sides have the same FDA sources with comparable "
            "date ranges. When it is symmetric, a difference between the totals is still not a performance "
            "difference: pathway mix, attribution verification and record counts have to be read separately.",
            "来源覆盖问题指的是双方是否拥有相同的 FDA 来源且日期范围可比。即使覆盖对称，总数差异也不是业绩差异："
            "仍需分别阅读路径构成、归属核验程度与记录数量。",
        ) if symmetric else _txt(
            "The two sides do not have the same source coverage. At least part of any difference between the "
            "totals is a difference in what the snapshot contains, not in what the companies did.",
            "双方的数据来源覆盖并不相同。总数差异中至少有一部分来自快照包含内容的不同，而不是企业行为的差异。",
        ),
    }


def comparison_findings(
    dataset: Dataset,
    keys: Sequence[str],
    sides: Sequence[dict[str, Any]],
    scope: dict[str, Any],
    events_by_key: dict[str, list[Event]],
    metrics: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    names = {side["key"]: side["display_name"] for side in sides}
    total_by_key = {side["key"]: int(side["counts"]["records"]) for side in sides}
    window = scope["label_short"]

    # 1. Coverage asymmetry: a difference can be a coverage difference.
    coverage_rows = []
    for side in sides:
        for row in side["coverage"]["sources"]:
            if row["records"]:
                coverage_rows.append({
                    "key": side["key"], "source_id": row["source_id"], "records": row["records"],
                    "min": row["min_event_date"], "max": row["max_event_date"],
                })
    source_ids = {row["source_id"] for row in coverage_rows}
    asymmetry: list[dict[str, Any]] = []
    for source_id in sorted(source_ids):
        rows = {row["key"]: row for row in coverage_rows if row["source_id"] == source_id}
        for left in sides:
            for right in sides:
                if left["key"] >= right["key"]:
                    continue
                a, b = rows.get(left["key"]), rows.get(right["key"])
                if a and not b:
                    asymmetry.append({"source_id": source_id, "kind": "one_side_only", "side": left["key"], "other": right["key"], "records": a["records"]})
                elif b and not a:
                    asymmetry.append({"source_id": source_id, "kind": "one_side_only", "side": right["key"], "other": left["key"], "records": b["records"]})
                elif a and b:
                    start_a, start_b = _parse(a["min"]), _parse(b["min"])
                    if start_a and start_b and abs(start_a.year - start_b.year) >= 3:
                        asymmetry.append({"source_id": source_id, "kind": "start_year_gap", "side": left["key"], "other": right["key"], "years": [start_a.year, start_b.year]})
    if asymmetry:
        examples = []
        for item in asymmetry[:4]:
            examples.append({
                "side": names.get(item["side"]),
                "other": names.get(item["other"]),
                "source_id": item["source_id"],
                "source_name": SOURCE_NAMES.get(item["source_id"], item["source_id"]),
                "kind": item["kind"],
                "detail": item.get("records") or item.get("years"),
            })
        findings.append(_finding(
            finding_id="coverage_asymmetry",
            category="caution",
            title_en="The two sides do not have the same source coverage",
            title_zh="双方的数据来源覆盖并不相同",
            statement_en=(
                f"{len(asymmetry)} coverage difference(s) exist in {window}: "
                + "; ".join(
                    (f"{item['source_id']} has records only for {names.get(item['side'])}" if item["kind"] == "one_side_only"
                     else f"{item['source_id']} starts {abs(item['years'][1] - item['years'][0])} years apart")
                    for item in asymmetry[:3]
                )
                + ". Part of any difference between the totals is a difference in what the snapshot contains."
            ),
            statement_zh=(
                f"{window} 内存在 {len(asymmetry)} 处覆盖差异："
                + "；".join(
                    (f"{item['source_id']} 仅 {names.get(item['side'])} 有记录" if item["kind"] == "one_side_only"
                     else f"{item['source_id']} 的起始年份相差 {abs(item['years'][1] - item['years'][0])} 年")
                    for item in asymmetry[:3]
                )
                + "。双方总数差异的一部分来自快照包含内容的不同。"
            ),
            cannot_en="A source-coverage difference is not an activity difference, and a missing source does not mean the company was inactive in it.",
            cannot_zh="来源覆盖差异不是活动差异；某一来源缺失也不代表企业在该方向没有活动。",
            basis={"rule": "a source has records for one side only, or its first event year differs by >= 3 years", "inputs": examples, "rules_version": RULES_VERSION},
            evidence={"record_count": len(asymmetry), "records": [], "note": _txt("The coverage table on each side lists the exact date range per source.", "每一侧的覆盖表列出了各来源的准确日期范围。")},
            drilldown={"url": "/sources", "label": _txt("Open sources and coverage", "打开数据来源与覆盖")},
        ))

    # 2. Pathway mix divergence.
    mix = []
    for event_type in EVENT_TYPE_ORDER:
        shares = {}
        for side in sides:
            total = total_by_key[side["key"]]
            shares[side["key"]] = (side["counts_by_type"].get(event_type, 0) / total) if total else None
        values = [value for value in shares.values() if value is not None]
        if len(values) == 2 and min(total_by_key.values()) >= 20:
            difference = abs(values[0] - values[1])
            if difference >= 0.25:
                mix.append({"event_type": event_type, "shares": shares, "difference": difference})
    if mix:
        item = max(mix, key=lambda row: row["difference"])
        left, right = sides[0], sides[1]
        share_left = item["shares"][left["key"]] or 0
        share_right = item["shares"][right["key"]] or 0
        findings.append(_finding(
            finding_id="pathway_mix_divergence",
            category="finding",
            title_en="The regulatory pathway mix differs between the two sides",
            title_zh="双方的监管路径构成存在差异",
            statement_en=(
                f"{EVENT_TYPE_LABELS[item['event_type']]} records are {_pct(share_left)} of {names[left['key']]}'s window "
                f"records and {_pct(share_right)} of {names[right['key']]}'s — a difference of "
                f"{_pct(item['difference'])} percentage points."
            ),
            statement_zh=(
                f"{_TYPE_LABELS_ZH[item['event_type']]}记录占 {names[left['key']]} 窗口记录的 {_pct(share_left)}，"
                f"占 {names[right['key']]} 的 {_pct(share_right)}，相差 {_pct(item['difference'])} 个百分点。"
            ),
            cannot_en=(
                "A pathway-mix difference describes what each company filed, not how innovative or effective "
                "it is. Different pathways have different meanings and are not interchangeable units."
            ),
            cannot_zh="路径构成差异描述的是双方申报内容的构成，不代表创新能力或效果。不同监管路径含义不同，不能互相换算。",
            basis={"rule": "absolute pathway share difference >= 25 percentage points, both sides >= 20 records", "inputs": [{"event_type": row["event_type"], **{key: round(value, 6) if value is not None else None for key, value in row["shares"].items()}, "difference": round(row["difference"], 6)} for row in mix], "rules_version": RULES_VERSION},
            evidence={"record_count": sum(int(side["counts_by_type"].get(item["event_type"], 0)) for side in sides), "records": _sample([event for side in sides for event in events_by_key[side["key"]] if event.event_type == item["event_type"]], limit=4), "note": _txt("Examples from both sides; the event browser reproduces each side separately.", "来自双方的示例；事件浏览器可分别复现每一侧。")},
            drilldown={"url": events_url(org=left["key"], types=[item["event_type"]], scope=scope), "label": _txt("Open " + names[left["key"]] + "'s records for this pathway", "打开 " + names[left["key"]] + " 在该路径下的记录")},
        ))

    # 3. Shared vs exclusive product-code families.
    rows_by_side: dict[str, dict[str, dict[str, Any]]] = {}
    for side in sides:
        payload = dataset.product_family_rows(events_by_key[side["key"]], limit=1000)
        rows_by_side[side["key"]] = {row["product_code"]: row for row in payload["rows"]}
    if len(sides) >= 2:
        left_key, right_key = sides[0]["key"], sides[1]["key"]
        left_codes, right_codes = rows_by_side[left_key], rows_by_side[right_key]
        shared = sorted(set(left_codes) & set(right_codes), key=lambda code: -(left_codes[code]["records"] + right_codes[code]["records"]))[:8]
        only_left = sorted(set(left_codes) - set(right_codes), key=lambda code: -left_codes[code]["records"])[:5]
        only_right = sorted(set(right_codes) - set(left_codes), key=lambda code: -right_codes[code]["records"])[:5]
        if shared or only_left or only_right:
            findings.append(_finding(
                finding_id="product_family_overlap",
                category="finding",
                title_en="The two sides share some official product-code families and not others",
                title_zh="双方共享部分官方产品代码家族，也存在各自独有的家族",
                statement_en=(
                    f"{len(shared)} product-code families appear on both sides in the window; "
                    f"{len(only_left)} appear only for {names[left_key]} in the shown set and "
                    f"{len(only_right)} only for {names[right_key]}. A product code is an FDA "
                    "classification unit, not a market segment."
                ),
                statement_zh=(
                    f"窗口内有 {len(shared)} 个产品代码家族同时出现在双方；在展示范围内，"
                    f"{len(only_left)} 个仅属于 {names[left_key]}，{len(only_right)} 个仅属于 {names[right_key]}。"
                    "产品代码是 FDA 分类单位，不是市场细分。"
                ),
                cannot_en=(
                    "Shared codes mean both companies have records under the same FDA classification; they do "
                    "not establish competing products, and exclusive codes do not establish a white space."
                ),
                cannot_zh="共享代码只表示双方在同一 FDA 分类下有记录，不能证明产品直接竞争；独有代码也不等于市场空白。",
                basis={
                    "rule": "set overlap of product codes with at least one window record per side",
                    "inputs": {
                        "shared": [{"product_code": code, "official_name": left_codes[code]["official_name"], "left": left_codes[code]["records"], "right": right_codes[code]["records"]} for code in shared],
                        "only_left": [{"product_code": code, "official_name": left_codes[code]["official_name"], "records": left_codes[code]["records"]} for code in only_left],
                        "only_right": [{"product_code": code, "official_name": right_codes[code]["official_name"], "records": right_codes[code]["records"]} for code in only_right],
                    },
                    "rules_version": RULES_VERSION,
                },
                evidence={"record_count": sum(left_codes[code]["records"] + right_codes[code]["records"] for code in shared), "records": _sample([event for side in sides for event in events_by_key[side["key"]] if (event.product_code or "").upper() in set(shared)], limit=4), "note": _txt("Examples from shared product codes only.", "仅来自共享产品代码的示例。")},
                drilldown={"url": f"/devices?org={left_key}", "label": _txt("Open the device explorer for the first side", "打开第一侧的器械浏览器")},
            ))

    # 4. Verification asymmetry (repeat of the Compare warning, but as a brief caution with numbers).
    left, right = sides[0], sides[1]
    left_share = left["counts"].get("curated_share")
    right_share = right["counts"].get("curated_share")
    if left_share is not None and right_share is not None and abs(left_share - right_share) >= 0.10:
        findings.append(_finding(
            finding_id="verification_asymmetry",
            category="caution",
            title_en="The two sides' records are not equally verified",
            title_zh="双方记录的核验程度并不相同",
            statement_en=(
                f"{_pct(left_share)} of {names[left['key']]}'s records are evidence-verified or human-reviewed, "
                f"compared with {_pct(right_share)} of {names[right['key']]}'s."
            ),
            statement_zh=(
                f"{names[left['key']]} 的记录中有 {_pct(left_share)} 经证据核验或人工复核，"
                f"而 {names[right['key']]} 为 {_pct(right_share)}。"
            ),
            cannot_en="A verification difference is a data-confidence difference, not an activity difference.",
            cannot_zh="核验程度差异是数据可信度差异，不是活动差异。",
            basis={"rule": "curated-share difference >= 10 percentage points", "inputs": {left["key"]: left_share, right["key"]: right_share}, "rules_version": RULES_VERSION},
            evidence={"record_count": int(left["counts"]["records"]) + int(right["counts"]["records"]), "records": [], "note": _txt("Per-record verification is shown in the evidence drawer and in each side's table.", "每条记录的核验状态见证据面板及各方表格。")},
            drilldown={"url": "/sources", "label": _txt("Open the attribution audit", "打开归属审计")},
        ))

    findings.sort(key=_finding_order)
    return findings[:MAX_FINDINGS]


# --------------------------------------------------------------------------- scope
def resolve_scope(
    dataset: Dataset,
    *,
    years: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """Resolve the requested window into an explicit, reproducible scope."""
    if date_from or date_to:
        if not date_from or not date_to:
            raise ValueError("an explicit window needs both from and to")
        start, end = _parse(date_from), _parse(date_to)
        if start is None or end is None:
            raise ValueError("from/to must be ISO dates (YYYY-MM-DD)")
        if start > end:
            raise ValueError("from must not be after to")
        if (end - start).days > 366 * 30:
            raise ValueError("the window is too large; choose at most 30 years")
        complete = complete_years(start.isoformat(), end.isoformat())
        requested = None
    else:
        requested = int(years) if years else 5
        if requested not in WINDOW_YEARS:
            raise ValueError("years must be one of " + ", ".join(str(item) for item in WINDOW_YEARS))
        start_text, end_text, _ = default_window(dataset, requested)
        start, end = _parse(start_text), _parse(end_text)
        assert start is not None and end is not None
        complete = [str(year) for year in range(start.year, end.year + 1)]
        date_from, date_to = start_text, end_text
    partial = []
    for year in range(start.year, end.year + 1):  # type: ignore[union-attr]
        if str(year) not in complete:
            partial.append(str(year))
    if complete:
        label_short = complete[0] + "–" + complete[-1] if len(complete) > 1 else complete[0]
    else:
        label_short = f"{date_from} to {date_to}"
    return {
        "from": date_from,
        "to": date_to,
        "requested_years": requested,
        "complete_years": complete,
        "partial_years": partial,
        "label": f"{date_from} to {date_to}",
        "label_short": label_short,
        "note": (
            "Per-year rates and the year-change rule use complete calendar years only. Partial years at "
            "the edges of an explicit window are shown but marked and excluded from those calculations."
            if partial else
            "The window is made of complete calendar years."
        ),
    }


# --------------------------------------------------------------------------- company
def _pma_families(
    dataset: Dataset,
    events: Sequence[Event],
    scope: dict[str, Any],
    limit: int = 6,
) -> dict[str, Any]:
    """PMA families among the window's records, using the PRODUCT-003 official hierarchy."""
    grouped: dict[str, list[Event]] = {}
    for event in events:
        if event.event_type not in ("pma", "pma_supplement"):
            continue
        pma_number = (event.official_id or "").split(":")[0].strip().upper()
        if not pma_number:
            continue
        grouped.setdefault(pma_number, []).append(event)
    if not grouped:
        return {"rows": [], "note": _txt("No PMA records in this window.", "本窗口内没有 PMA 记录。")}
    index = dataset.device_index()
    rows = []
    for pma_number, subset in grouped.items():
        family_id = "family:pma:" + pma_number
        family = index.family(family_id)
        device = index.devices.get(family.device_id) if family and family.device_id else None
        supplements = [event for event in subset if event.event_type == "pma_supplement"]
        dates = [event.event_date for event in subset if event.event_date]
        rows.append({
            "pma_number": pma_number,
            "family_id": family_id,
            "name": (family.name if family else None) or next((event.device_name for event in subset if event.device_name), pma_number),
            "device_id": family.device_id if family else None,
            "device_url": "/devices/" + (device.official_id if device else pma_number),
            "original_in_snapshot": family.original_in_snapshot if family else False,
            "supplement_count_total": family.supplement_count if family else None,
            "supplements_in_window": len(supplements),
            "records_in_window": len(subset),
            "first_event_date": min(dates) if dates else None,
            "last_event_date": max(dates) if dates else None,
            "evidence_records": _sample(subset, limit=4),
        })
    rows.sort(key=lambda row: (-row["supplements_in_window"], -row["records_in_window"], row["pma_number"]))
    return {
        "rows": rows[:limit],
        "total_families": len(rows),
        "note": _txt(
            "A family is the official PMA application hierarchy: one PMA number plus every supplement "
            "that carries it. A supplement is a version of the approved device, not a new device.",
            "家族指官方 PMA 申请层级：一个 PMA 编号及其所有补充申请。补充申请是已获批器械的版本，不是新器械。",
        ),
    }


def _changes_section(
    dataset: Dataset,
    *,
    organization_key: str | None,
    pipeline_db: Any = None,
) -> dict[str, Any]:
    """What the change ledger observed. Absence of a ledger is stated, never rendered as 'no news'."""
    from medradar.data_pipeline.status_service import changes_feed

    try:
        feed = changes_feed(organization_key=organization_key, limit=10, pipeline_db=pipeline_db, data_dir=dataset.data_dir)
    except Exception as error:  # a broken ledger must not break the brief
        return {
            "state": "unavailable",
            "observed_at": _now(),
            "counts": {},
            "items": [],
            "note": _txt(
                "The change ledger could not be read: " + str(error),
                "无法读取变化台账：" + str(error),
            ),
        }
    if not feed.get("configured"):
        return {
            "state": "not_configured",
            "observed_at": _now(),
            "counts": {},
            "items": [],
            "note": _txt(
                "This deployment has no continuous-pipeline change ledger. No claim is made about records "
                "added, updated or removed since the snapshot; the brief describes the snapshot only.",
                "该部署未配置持续同步的变化台账。简报不声称快照之后有任何新增、更新或删除记录，只描述该快照。",
            ),
        }
    items = feed.get("items") or []
    total = int(feed.get("total") or 0)
    if total == 0:
        return {
            "state": "no_changes",
            "observed_at": _now(),
            "counts": {},
            "items": [],
            "note": _txt(
                "The change ledger is configured and records no published change for this scope. This is "
                "the correct statement of 'no new changes observed'; no record is presented as new.",
                "变化台账已配置，但在该范围内没有记录到已发布的变更。这就是“未观察到新变化”的正确表述；没有记录被当作新增。",
            ),
        }
    return {
        "state": "available",
        "observed_at": _now(),
        "counts": (feed.get("counts") or feed.get("summary") or {}),
        "items": items,
        "note": _txt(
            "Changes come from the DATA-001 change ledger and refer to the official source records, not to "
            "FDA decision dates.",
            "变化来自 DATA-001 变化台账，针对官方源记录，而非 FDA 决定日期。",
        ),
    }


def company_brief(
    dataset: Dataset,
    key: str,
    *,
    years: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    event_types: Sequence[str] | None = None,
    basis: str = "current_group",
    review: str | None = None,
    pipeline_db: Any = None,
) -> dict[str, Any]:
    org = dataset.organization(key)
    if org is None:
        raise KeyError(key)
    scope = resolve_scope(dataset, years=years, date_from=date_from, date_to=date_to)
    types = [item for item in (event_types or EVENT_TYPE_ORDER) if item in EVENT_TYPE_ORDER] or list(EVENT_TYPE_ORDER)
    events = dataset.filter_events(
        org_keys=[key], event_types=types, date_from=scope["from"], date_to=scope["to"],
        review=review, basis=None if basis in (None, "", "current_group") else basis,
    )
    counts = dataset.counts(events)
    total = len(events)
    by_type = _by_type(events)
    top_type, top_count = max(by_type.items(), key=lambda item: item[1]) if by_type else (None, 0)
    families = _pma_families(dataset, events, scope)
    findings = company_findings(dataset, key, events, scope, counts, families["rows"])
    years_rows = _year_rows(events, scope["complete_years"], scope)
    recent = dataset.sort_events(events, "event_date_desc")[:12]
    sources = _source_rows(events)
    specialty = _specialty_rows(events)
    product_families = dataset.product_family_rows(events, limit=15)
    dates = [event.event_date for event in events if event.event_date]
    profile_snapshot = dataset.snapshot_ref()

    tiles = [
        {
            "id": "records",
            "label": _txt("Records in the window", "窗口内记录"),
            "value": total,
            "note": _txt("attributed records, " + scope["label_short"], "已归属记录，" + scope["label_short"]),
        },
        {
            "id": "top_pathway",
            "label": _txt("Largest pathway", "占比最高的路径"),
            "value": EVENT_TYPE_LABELS.get(top_type or "", "—"),
            "note": _txt(_pct(top_count / total) + " of the window" if total else "no records", "占窗口的 " + _pct(top_count / total) if total else "无记录"),
        },
        {
            "id": "curated",
            "label": _txt("Evidence-verified or reviewed", "经证据核验或人工复核"),
            "value": _pct(counts.get("curated_share")),
            "note": _txt(_n(counts.get("verified_records")) + " of " + _n(total), _n(counts.get("verified_records")) + " / " + _n(total)),
        },
        {
            "id": "dated_range",
            "label": _txt("Dated record range", "有日期记录范围"),
            "value": (min(dates) if dates else "—"),
            "note": _txt("to " + (max(dates) if dates else "—"), "至 " + (max(dates) if dates else "—")),
        },
    ]

    brief = {
        "schema": BRIEF_SCHEMA,
        "kind": "company",
        "generated_at": _now(),
        "rules_version": RULES_VERSION,
        "lang": "en",
        "title": _txt(
            f"{org.display_name} — FDA regulatory intelligence brief, {scope['label_short']}",
            f"{org.display_name} — FDA 监管情报简报，{scope['label_short']}",
        ),
        "question": _txt(
            f"What does {org.display_name}'s FDA device regulatory record show for {scope['label_short']}, "
            "and what can it not establish?",
            f"{org.display_name} 在 {scope['label_short']} 的 FDA 器械监管记录显示了什么，又不能证明什么？",
        ),
        "scope": {
            **scope,
            "event_types": types,
            "event_type_labels": [EVENT_TYPE_LABELS[item] for item in types],
            "ownership_basis": basis or "current_group",
            "review_filter": review or "any",
            "counting_rule": _txt(COUNTING_RULE_EN, COUNTING_RULE_ZH),
            "snapshot": profile_snapshot,
            "freshness": dataset.freshness(),
            "generated_at": _now(),
        },
        "organization": {
            "key": org.key,
            "display_name": org.display_name,
            "display_name_zh": org.display_name_zh,
            "legal_name": org.legal_name,
            "ticker": org.ticker,
            "exchange": org.exchange,
            "country": org.country,
            "country_name": org.country_name,
            "description": org.description,
            "registry_review": org.registry_review,
            "registry_updated_at": dataset.registry.updated_at,
        },
        "summary": {
            "records": total,
            "dated": counts.get("dated", 0),
            "undated": counts.get("undated", 0),
            "by_type": _type_rows(events, total),
            "tiles": tiles,
            "sources": sources,
            "verification": {
                "attributed_records": total,
                "verified_records": counts.get("verified_records", 0),
                "rule_verified_records": counts.get("rule_verified_records", 0),
                "provisional_records": counts.get("provisional", 0),
                "curated_share": counts.get("curated_share"),
                "rule_verified_share": counts.get("rule_verified_share"),
                "provisional_share": counts.get("provisional_share"),
                "by_status": counts.get("by_verification", {}),
                "note": _txt(
                    "Verified means evidence-verified or human-reviewed. A deterministic rule is reported "
                    "separately and is not review. Provisional mappings are working assumptions.",
                    "“已核验”指有证据支持或经人工复核。确定性规则单独报告，不等同于复核。暂定映射属于工作假设。",
                ),
            },
            "ownership": {
                "state_at_event_time": {
                    "verified_current_group": counts.get("historical_verified_current_group", 0),
                    "verified_predecessor": counts.get("historical_verified_predecessor", 0),
                    "unknown": counts.get("historical_unknown", 0),
                },
                "note": _txt(
                    "Counts use the current group, so a record filed by an acquired predecessor is counted "
                    "under this organization. The owner at the event date is reported separately; UNKNOWN is "
                    "reported, never counted as zero.",
                    "计数采用当前集团口径，因此被收购前身提交的记录计入本企业。事件发生时的实际所有者单独报告；未知情况如实报告，不按零处理。",
                ),
            },
        },
        "activity": {
            "by_type": _type_rows(events, total),
            "by_year": years_rows,
            "complete_years": scope["complete_years"],
            "partial_years": scope["partial_years"],
            "note": _txt(
                "Event types are never merged. A PMA supplement is a change to an approved device; a recall "
                "is a safety action. Per-year rows mark partial calendar years.",
                "不同事件类型绝不合并。PMA 补充申请是对已获批器械的变更；召回是安全行动。逐年行会标注不完整自然年。",
            ),
        },
        "technology": {
            "specialty": specialty,
            "product_families": product_families,
        },
        "devices": {
            "families": families["rows"],
            "total_families_in_window": families.get("total_families", 0),
            "note": families["note"],
        },
        "recent": {
            "records": [_record_ref(event) for event in recent],
            "note": _txt(
                "Ordered by FDA event date, not by when MedRadar collected the record. Open any record to see "
                "event date, source publication date, first-observed time and available-at as separate fields.",
                "按 FDA 事件日期排序，而非 MedRadar 采集时间。打开任意记录可分别查看事件日期、来源公开时间、首次采集时间与可用时间。",
            ),
        },
        "findings": findings,
        "changes": _changes_section(dataset, organization_key=key, pipeline_db=pipeline_db),
        "evidence": {
            "sources": sources,
            "snapshot": profile_snapshot,
            "official_links": _official_links(events, findings),
            "appendix": {
                "rows": total,
                "note": _txt(
                    "The evidence appendix (CSV) contains one row per window record with its official URL and "
                    "verification state, plus the records cited by the findings.",
                    "证据附录（CSV）每个窗口记录一行，含官方链接与核验状态，并包含发现所引用的记录。",
                ),
            },
        },
        "limitations": _limitations(
            scope=scope, counts=counts, total=total, specialty=specialty, org_name=org.display_name,
        ),
    }
    return brief


# --------------------------------------------------------------------------- comparison
def _metric_rows_for_compare(
    dataset: Dataset,
    keys: Sequence[str],
    scope: dict[str, Any],
    types: Sequence[str],
    sides: Sequence[dict[str, Any]],
    events_by_key: dict[str, list[Event]],
) -> list[dict[str, Any]]:
    """The metrics the brief shows, each explainable down to the records that produced it."""
    metrics: list[dict[str, Any]] = []
    names = {side["key"]: side["display_name"] for side in sides}

    def values_for(raw: dict[str, int]) -> list[dict[str, Any]]:
        total = sum(raw.values())
        return [
            {"key": side["key"], "name": names[side["key"]], "value": raw.get(side["key"], 0),
             "share": round(raw.get(side["key"], 0) / total, 6) if total else None}
            for side in sides
        ]

    total_raw = {side["key"]: int(side["counts"]["records"]) for side in sides}
    metrics.append({
        "id": "records_total",
        "label": _txt("All records in the window", "窗口内全部记录"),
        "definition": _txt(
            "Number of attributed regulatory records in the window, all selected event types together. "
            "Records of different event types are not interchangeable; this total is a volume measure only.",
            "窗口内已归属监管记录的数量，包含所选全部事件类型。不同事件类型的记录不可互换；该合计仅表示记录数量。",
        ),
        "values": values_for(total_raw),
        "unit": "records",
    })
    for event_type in EVENT_TYPE_ORDER:
        raw = {side["key"]: int(side["counts_by_type"].get(event_type, 0)) for side in sides}
        if not any(raw.values()):
            continue
        metrics.append({
            "id": "type." + event_type,
            "label": _txt(EVENT_TYPE_LABELS[event_type], _TYPE_LABELS_ZH[event_type]),
            "definition": _txt(_TYPE_DEFINITIONS_EN[event_type], _TYPE_DEFINITIONS_ZH[event_type]),
            "values": values_for(raw),
            "unit": "records",
        })
    # Specialty rows: top by combined count.
    specialty_totals: dict[str, int] = {}
    specialty_labels: dict[str, str] = {}
    for side in sides:
        aggregation = aggregate(events_by_key[side["key"]])
        for row in aggregation["by_category"]:
            specialty_totals[row["id"]] = specialty_totals.get(row["id"], 0) + row["total"]
            specialty_labels[row["id"]] = row["label"]
    for category_id in sorted(specialty_totals, key=lambda item: -specialty_totals[item])[:8]:
        raw = {}
        for side in sides:
            raw[side["key"]] = sum(1 for event in events_by_key[side["key"]] if (event.category.id if event.category else "unclassified") == category_id)
        metrics.append({
            "id": "specialty." + category_id,
            "label": _txt(specialty_labels[category_id], specialty_labels[category_id]),
            "definition": _txt(
                "Records whose product code's FDA medical specialty is '" + specialty_labels[category_id] + "'. "
                "The FDA dictionary states 'Unknown' for many class III codes; a low count is not absence of activity.",
                "产品代码对应的 FDA 医学专科为“" + specialty_labels[category_id] + "”的记录。FDA 字典对许多第三类代码标注“Unknown”；计数低不代表没有活动。",
            ),
            "values": values_for(raw),
            "unit": "records",
        })
    # Product-code families: top by combined count.
    combined: Counter[str] = Counter()
    for side in sides:
        for row in dataset.product_family_rows(events_by_key[side["key"]], limit=1000)["rows"]:
            combined[row["product_code"]] += row["records"]
    names_by_code = {row["product_code"]: row["official_name"] for side in sides for row in dataset.product_family_rows(events_by_key[side["key"]], limit=1000)["rows"]}
    for code in [code for code, _ in combined.most_common(8)]:
        raw = {}
        for side in sides:
            raw[side["key"]] = sum(1 for event in events_by_key[side["key"]] if (event.product_code or "").upper() == code)
        metrics.append({
            "id": "product_code." + code,
            "label": _txt(code + (": " + names_by_code[code] if names_by_code.get(code) else ""), code + (": " + names_by_code[code] if names_by_code.get(code) else "")),
            "definition": _txt(
                "Records whose official FDA product code is " + code + ". Product codes are FDA classification "
                "units, not market segments or product lines.",
                "官方 FDA 产品代码为 " + code + " 的记录。产品代码是 FDA 分类单位，不是市场细分或产品线。",
            ),
            "values": values_for(raw),
            "unit": "records",
        })
    # Attach reproducible drill-down URLs (both sides) and the event types the metric used.
    for metric in metrics:
        metric["drilldown"] = {}
        for side in sides:
            if metric["id"] == "records_total":
                url = events_url(org=side["key"], types=types, scope=scope)
            elif metric["id"].startswith("type."):
                url = events_url(org=side["key"], types=[metric["id"].split(".", 1)[1]], scope=scope)
            elif metric["id"].startswith("specialty."):
                url = events_url(org=side["key"], types=types, scope=scope, category=metric["id"].split(".", 1)[1])
            else:
                url = events_url(org=side["key"], types=types, scope=scope, product_code=metric["id"].split(".", 1)[1])
            metric["drilldown"][side["key"]] = url
    return metrics


def comparison_brief(
    dataset: Dataset,
    keys: Sequence[str],
    *,
    years: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    event_types: Sequence[str] | None = None,
    basis: str = "current_group",
    review: str | None = None,
    pipeline_db: Any = None,
) -> dict[str, Any]:
    clean_keys = [key for key in dict.fromkeys(keys) if key]
    if len(clean_keys) < MIN_ORGS:
        raise ValueError("a comparison brief needs at least " + str(MIN_ORGS) + " organizations")
    if len(clean_keys) > MAX_ORGS:
        raise ValueError("a comparison brief accepts at most " + str(MAX_ORGS) + " organizations")
    for key in clean_keys:
        if dataset.organization(key) is None:
            raise KeyError(key)
    scope = resolve_scope(dataset, years=years, date_from=date_from, date_to=date_to)
    types = [item for item in (event_types or EVENT_TYPE_ORDER) if item in EVENT_TYPE_ORDER] or list(EVENT_TYPE_ORDER)
    comparison = build_compare(
        dataset, clean_keys, scope["from"], scope["to"], types,
        basis=None if basis in (None, "", "current_group") else basis,
        review=review,
    )
    sides = comparison["organizations"]
    events_by_key = {
        key: dataset.filter_events(
            org_keys=[key], event_types=types, date_from=scope["from"], date_to=scope["to"],
            review=review, basis=None if basis in (None, "", "current_group") else basis,
        )
        for key in clean_keys
    }
    metrics = _metric_rows_for_compare(dataset, clean_keys, scope, types, sides, events_by_key)
    findings = comparison_findings(dataset, clean_keys, sides, scope, events_by_key, metrics)
    names = [side["display_name"] for side in sides]
    years_rows = []
    for side in sides:
        years_rows.append({
            "key": side["key"],
            "name": side["display_name"],
            "rows": _year_rows(events_by_key[side["key"]], scope["complete_years"], scope),
        })
    changes = []
    for key in clean_keys:
        section = _changes_section(dataset, organization_key=key, pipeline_db=pipeline_db)
        changes.append({"organization_key": key, "display_name": dataset.organization(key).display_name, **section})
    return {
        "schema": BRIEF_SCHEMA,
        "kind": "compare",
        "generated_at": _now(),
        "rules_version": RULES_VERSION,
        "title": _txt(
            " vs ".join(names) + " — competitor regulatory brief, " + scope["label_short"],
            " 对比 ".join(names) + " — 竞争对手监管简报，" + scope["label_short"],
        ),
        "question": _txt(
            "What does the same counting rule show for " + " and ".join(names) + " in " + scope["label_short"]
            + ", and which differences are not comparable?",
            "在相同统计口径下，" + " 与 ".join(names) + " 在 " + scope["label_short"] + " 的监管记录有何差异，哪些差异不可直接比较？",
        ),
        "scope": {
            **scope,
            "event_types": types,
            "event_type_labels": [EVENT_TYPE_LABELS[item] for item in types],
            "ownership_basis": basis or "current_group",
            "review_filter": review or "any",
            "counting_rule": _txt(COUNTING_RULE_EN, COUNTING_RULE_ZH),
            "snapshot": dataset.snapshot_ref(),
            "freshness": dataset.freshness(),
            "generated_at": _now(),
        },
        "sides": [
            {
                "key": side["key"],
                "display_name": side["display_name"],
                "legal_name": side["legal_name"],
                "ticker": side["ticker"],
                "country": side["country"],
                "counts": side["counts"],
                "counts_by_type": side["counts_by_type"],
                "coverage": side["coverage"],
                "verification": side["verification"],
                "historical_ownership": side["historical_ownership"],
                "per_year_totals": side["per_year_totals"],
            }
            for side in sides
        ],
        "comparability": comparison["comparability"],
        "coverage_assessment": _coverage_assessment(sides, comparison["comparability"]),
        "warnings": comparison["warnings"],
        "metrics": metrics,
        "by_year": years_rows,
        "specialty": {
            "note": _txt(
                "Specialty comes from the FDA product-code dictionary. 'Unknown' is a source value, not a "
                "MedRadar gap; see the product-code overlap finding for an interpretable alternative.",
                "专科来自 FDA 产品代码字典。“Unknown”是来源取值，不是 MedRadar 的缺失；可参考产品代码重叠发现作为可解读的替代视角。",
            ),
        },
        "findings": findings,
        "changes": changes,
        "disclaimer": comparison["disclaimer"],
        "not_evidence_of": comparison["not_evidence_of"],
        "evidence": {
            "sources": [
                {
                    "key": side["key"],
                    "name": side["display_name"],
                    "sources": side["coverage"]["sources"],
                }
                for side in sides
            ],
            "snapshot": dataset.snapshot_ref(),
            "official_links": _official_links_compare(events_by_key, findings),
            "appendix": {
                "rows": sum(len(events) for events in events_by_key.values()),
                "note": _txt(
                    "The evidence appendix (CSV) contains one row per record for every side, with official "
                    "URLs, plus the records cited by the findings.",
                    "证据附录（CSV）包含每一侧每条记录一行，附官方链接，并包含发现所引用的记录。",
                ),
            },
        },
        "limitations": _limitations_compare(scope, sides, findings),
    }


def _limitations(
    *,
    scope: dict[str, Any],
    counts: dict[str, Any],
    total: int,
    specialty: dict[str, Any],
    org_name: str,
) -> dict[str, Any]:
    return {
        "scope": [
            _txt(
                f"This brief covers {total:,} attributed records for {org_name} between {scope['from']} and {scope['to']}. "
                "It is not a statement about the company outside that window.",
                f"本简报覆盖 {org_name} 在 {scope['from']} 至 {scope['to']} 之间的 {total:,} 条已归属记录，不代表该窗口之外的情况。",
            ),
            _txt(COUNTING_RULE_EN, COUNTING_RULE_ZH),
        ],
        "coverage": [
            _txt(
                "Only the sources listed in the evidence section are included (FDA 510(k), PMA/PMI supplements and device recalls). "
                "De Novo, UDI, EU MDR, NMPA, clinical trials, patents and financial filings are out of scope.",
                "仅包含证据部分列出的来源（FDA 510(k)、PMA/补充申请与器械召回）。De Novo、UDI、EU MDR、NMPA、临床试验、专利与财务申报不在范围内。",
            ),
            _txt(
                "The FDA classification dictionary states 'Unknown' as the specialty for " + _n(specialty.get("unknown_count"))
                + " of " + _n(total) + " records in this window. A specialty table alone cannot describe the technology mix.",
                f"在本窗口 {_n(total)} 条记录中，FDA 分类字典将 {_n(specialty.get('unknown_count'))} 条的专科标注为“Unknown”。仅凭专科表无法描述技术构成。",
            ),
        ],
        "identity": [
            _txt(
                "Attribution is exact applicant-string matching against a reviewed registry. "
                + _n(counts.get("verified_records")) + " records are evidence-verified or human-reviewed, "
                + _n(counts.get("rule_verified_records")) + " rest on a deterministic rule, and "
                + _n(counts.get("provisional")) + " are provisional.",
                "归属采用已审核登记表的申请人字符串精确匹配。" + _n(counts.get("verified_records")) + " 条经证据核验或人工复核，"
                + _n(counts.get("rule_verified_records")) + " 条依赖确定性规则，" + _n(counts.get("provisional")) + " 条为暂定。",
            ),
            _txt(
                "Records filed by an acquired predecessor are counted under the current group; the owner at "
                "the event date is reported separately and is UNKNOWN for " + _n(counts.get("historical_unknown")) + " records.",
                "被收购前身提交的记录按当前集团计入；事件发生时的所有者单独报告，其中 " + _n(counts.get("historical_unknown")) + " 条为未知。",
            ),
        ],
        "time": [
            _txt(
                "Event date is the FDA decision date or the firm's recall-initiation date. openFDA states no "
                "publication timestamp for 510(k)/PMA; first-observed time is MedRadar's collection time.",
                "事件日期为 FDA 决定日期或企业召回启动日期。openFDA 未提供 510(k)/PMA 的发布时间；首次采集时间为 MedRadar 的采集时间。",
            ),
        ],
        "relationship": [
            _txt(
                "PMA families follow the official PMA number. Candidate device/recall relations are hypotheses "
                "and are never presented as established. A recall is attached only through its official "
                "K-number field.",
                "PMA 家族依据官方 PMA 编号。候选器械/召回关系只是假设，绝不作为已确认关系呈现。召回仅通过官方 K 号码字段关联。",
            ),
        ],
        "cannot_answer": [
            _txt(_CANNOT_CONCLUDE_COMMON_EN, _CANNOT_CONCLUDE_COMMON_ZH),
            _txt(
                "This brief cannot say why a count changed: organisation changes, name changes, FDA publication "
                "behaviour and backlog effects are observationally similar in a record count.",
                "本简报无法说明记录数量变化的原因：组织变更、名称变更、FDA 发布行为与积压效应在记录计数上可能表现相同。",
            ),
            _txt(
                "It cannot rank these companies, score innovation or infer commercial performance. No prediction "
                "or model output is included.",
                "它不能对企业排名、评估创新能力或推断商业表现。简报不包含预测或模型输出。",
            ),
        ],
    }


def _limitations_compare(scope: dict[str, Any], sides: Sequence[dict[str, Any]], findings: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "scope": [
            _txt(
                f"One window ({scope['from']} to {scope['to']}), one counting rule and the same event types are "
                "applied to every side. A one-sided window is not comparable and is not shown.",
                f"所有对比方使用同一窗口（{scope['from']} 至 {scope['to']}）、同一统计口径与相同事件类型。单边窗口不可比较，不予展示。",
            ),
            _txt(COUNTING_RULE_EN, COUNTING_RULE_ZH),
        ],
        "coverage": [
            _txt(
                "Coverage differs by source and by organization. The coverage table per side and the "
                "coverage-asymmetry finding state where a difference may be a data difference.",
                "不同来源与不同企业的覆盖不同。每一侧的覆盖表和覆盖差异发现会指出何处的差异可能来自数据差异。",
            ),
        ],
        "identity": [
            _txt(
                "Verification differs between sides. A provisional mapping is a working assumption; comparing "
                "curated and provisional counts as if they were equally verified would overstate the comparison.",
                "双方的核验程度不同。暂定映射只是工作假设；把已核验与暂定记录当作同等可信来比较，会高估比较结论。",
            ),
            _txt(
                "Historical ownership: counts use the current group. A verified relation with an effective date "
                "is required to state who controlled the applicant at the event date; unknown is reported.",
                "历史所有权：计数采用当前集团口径。只有在存在带生效日期的已确认关系时，才能说明事件日期时谁控制申请人；未知情况会如实报告。",
            ),
        ],
        "relationship": [
            _txt(
                "Product-code overlap is a classification overlap, not evidence of competing products. A shared "
                "code does not establish a competitive relationship.",
                "产品代码重叠是分类层面的重叠，不是产品竞争的证明。共享代码不能建立竞争关系。",
            ),
        ],
        "cannot_answer": [
            _txt(_CANNOT_CONCLUDE_COMMON_EN, _CANNOT_CONCLUDE_COMMON_ZH),
            _txt(
                "It cannot rank the companies or state that one is more innovative, safer or commercially stronger. "
                "A record-count difference is not a performance difference.",
                "不能对企业排名，也不能断言某一方更具创新性、更安全或商业更强。记录数量差异不是业绩差异。",
            ),
        ],
    }


def _official_links(events: Sequence[Event], findings: Sequence[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for finding in findings:
        for record in (finding.get("evidence") or {}).get("records") or []:
            if record.get("official_url"):
                seen.setdefault(record["event_id"], record)
    for event in events:
        if len(seen) >= limit:
            break
        if event.official_url:
            seen.setdefault(event.event_id, _record_ref(event))
    return [
        {
            "label": record.get("official_id"),
            "official_id": record.get("official_id"),
            "event_type": record.get("event_type"),
            "event_date": record.get("event_date"),
            "url": record.get("official_url"),
        }
        for record in list(seen.values())[:limit]
    ]


def _official_links_compare(events_by_key: dict[str, list[Event]], findings: Sequence[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for finding in findings:
        for record in (finding.get("evidence") or {}).get("records") or []:
            if record.get("official_url"):
                seen.setdefault(record["event_id"], record)
    for key, events in events_by_key.items():
        for event in events:
            if len(seen) >= limit:
                break
            if event.official_url:
                seen.setdefault(event.event_id, {**_record_ref(event), "organization_key": key})
    return [
        {
            "label": record.get("official_id"),
            "official_id": record.get("official_id"),
            "event_type": record.get("event_type"),
            "event_date": record.get("event_date"),
            "organization_key": record.get("organization_key"),
            "url": record.get("official_url"),
        }
        for record in list(seen.values())[:limit]
    ]


# --------------------------------------------------------------------------- device
def device_brief(dataset: Dataset, identifier: str) -> dict[str, Any]:
    """A PMA-family / device investigation. All-time by nature: the official history is the object."""
    from .device import payloads

    index = dataset.device_index()
    device = index.device(identifier)
    if device is not None:
        payload = payloads.detail(dataset, device.device_id)
        if payload is not None:
            return _device_brief_from_detail(dataset, payload)
    family = index.family(identifier) if identifier.startswith("family:") else index.family("family:pma:" + identifier.strip().upper())
    if family is not None:
        payload = payloads.family_payload(dataset, family.family_id)
        if payload is not None:
            return _device_brief_from_family(dataset, payload)
    raise KeyError(identifier)


def _device_application_rows(application: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not application:
        return []
    return [{
        "official_id": application.get("official_id"),
        "kind": application.get("kind"),
        "kind_label": application.get("kind_label"),
        "decision_date": application.get("decision_date"),
        "device_name": application.get("device_name"),
        "trade_name": application.get("trade_name"),
        "applicant_name": application.get("applicant_name"),
        "official_url": application.get("official_url"),
        "supplement_number": application.get("supplement_number"),
        "supplement_type": application.get("supplement_type"),
        "supplement_reason": application.get("supplement_reason"),
    }]


def _device_brief_common(
    dataset: Dataset,
    *,
    identity: dict[str, Any],
    application: dict[str, Any] | None,
    family: dict[str, Any] | None,
    versions: Sequence[dict[str, Any]],
    recalls_confirmed: Sequence[dict[str, Any]],
    recalls_candidate: Sequence[dict[str, Any]],
    relations_confirmed: int,
    relations_candidate: int,
    timeline: Sequence[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    official_id = (application or {}).get("official_id") or (family or {}).get("family_id") or identity.get("official_id")
    dates = [row.get("decision_date") or row.get("initiated_date") or row.get("date") for row in timeline if row.get("decision_date") or row.get("initiated_date") or row.get("date")]
    scope = {
        "from": min(dates) if dates else None,
        "to": max(dates) if dates else None,
        "requested_years": None,
        "complete_years": [],
        "partial_years": [],
        "label": "the official history present in the snapshot",
        "label_short": "all-time",
        "note": "A device investigation is not windowed: it summarises the official history that the snapshot contains, and says when that history is incomplete.",
    }
    snapshot = dataset.snapshot_ref()
    supplements = [row for row in versions if row.get("kind") == "pma_supplement"]
    tiles = [
        {"id": "applications", "label": _txt("Applications in the family", "家族内申请"), "value": 1 + len(supplements), "note": _txt("1 original + " + _n(len(supplements)) + " supplements", "1 个原始 + " + _n(len(supplements)) + " 个补充")},
        {"id": "confirmed", "label": _txt("Confirmed supplement relations", "已确认补充申请关系"), "value": len(supplements), "note": _txt("same official PMA number", "同一官方 PMA 编号")},
        {"id": "recalls", "label": _txt("Recalls linked by K number", "通过 K 号码关联的召回"), "value": len(recalls_confirmed), "note": _txt("official reference only", "仅官方引用")},
        {"id": "candidates", "label": _txt("Candidate relations", "候选关系"), "value": relations_candidate, "note": _txt("hypotheses, never established", "假设，绝不作为已确认")},
    ]
    return {
        "schema": BRIEF_SCHEMA,
        "kind": "device",
        "generated_at": _now(),
        "rules_version": RULES_VERSION,
        "title": _txt(
            f"{identity.get('name') or official_id} — device regulatory history",
            f"{identity.get('name') or official_id} — 器械监管历史",
        ),
        "question": _txt(
            "What is the official FDA application history of this device, which relations are confirmed, and what cannot be concluded?",
            "该器械的官方 FDA 申请历史是什么，哪些关系已确认，哪些结论不能得出？",
        ),
        "scope": {
            **scope,
            "event_types": ["pma", "pma_supplement", "recall"],
            "event_type_labels": ["PMA original approval", "PMA supplement", "Recall"],
            "ownership_basis": "current_group",
            "review_filter": "any",
            "counting_rule": _txt(
                "One application is one official FDA decision. A supplement is a version of the approved device, not a new device. A recall is linked only through its official K-number field.",
                "一个申请对应一条 FDA 官方决定。补充申请是已获批器械的版本，不是新器械。召回仅通过官方 K 号码字段关联。",
            ),
            "snapshot": snapshot,
            "freshness": dataset.freshness(),
            "generated_at": _now(),
        },
        "device": identity,
        "family": family,
        "application": application,
        "versions": list(versions),
        "supplements_count": len(supplements),
        "tiles": tiles,
        "timeline": list(timeline),
        "relations": {
            "confirmed_count": relations_confirmed,
            "candidate_count": relations_candidate,
            "confirmed_rule": _txt("Confirmed only by an official identifier or an official record field.", "仅由官方标识或官方记录字段确认。"),
            "candidate_rule": _txt("Candidate relations are deterministic similarity suggestions and are not established.", "候选关系是确定性相似度建议，尚未确认。"),
        },
        "related_recalls": {
            "confirmed": list(recalls_confirmed),
            "candidate": list(recalls_candidate),
            "note": _txt(
                "Recalls are attached only when their official K-number field references this application. A recall "
                "without that field stays in the unlinked recall browser; it is not evidence that no recall occurred.",
                "仅当召回的官方 K 号码字段引用本申请时才建立关联。缺少该字段的召回保留在未关联召回浏览器中；这不等于没有发生召回。",
            ),
            "unlinked_url": "/devices?view=unlinked",
        },
        "findings": findings,
        "changes": {
            "state": "not_applicable",
            "observed_at": _now(),
            "counts": {},
            "items": [],
            "note": _txt(
                "Device histories are assembled from the snapshot's official application records; the change "
                "ledger is organisation-scoped and is not reported here.",
                "器械历史由快照中的官方申请记录构成；变化台账按企业范围统计，此处不报告。",
            ),
        },
        "evidence": {
            "snapshot": snapshot,
            "official_links": [
                {"label": row.get("official_id"), "official_id": row.get("official_id"), "url": row.get("official_url"), "event_type": row.get("kind"), "event_date": row.get("decision_date")}
                for row in ([application] if application else []) + list(versions[:15])
                if row.get("official_url")
            ],
            "appendix": {
                "rows": (1 if application else 0) + len(versions) + len(recalls_confirmed),
                "note": _txt("The evidence appendix lists the application, every supplement and every linked recall with official URLs.", "证据附录列出该申请、全部补充申请与已关联召回，并附官方链接。"),
            },
        },
        "limitations": {
            "scope": [
                _txt(
                    "The family is the official PMA application hierarchy. It is not proof that these are one commercial product line, and the snapshot may not contain the original approval.",
                    "该家族是官方 PMA 申请层级，不能证明这些版本属于同一商业产品线；快照也可能不包含原始批准。",
                ),
            ],
            "coverage": [
                _txt(
                    "Only records in this snapshot are summarised. A missing supplement or recall is not evidence that it does not exist.",
                    "仅汇总本快照中的记录。缺少某条补充申请或召回，不代表它不存在。",
                ),
            ],
            "identity": [
                _txt(
                    "Applicant attribution uses exact string matching; the applicant of record is not necessarily the current manufacturer.",
                    "申请人归属采用精确字符串匹配；记录中的申请人不一定是当前制造商。",
                ),
            ],
            "time": [
                _txt(
                    "Supplement decisions are ordered by FDA decision date. A later supplement does not cause a later recall.",
                    "补充申请按 FDA 决定日期排序。较晚的补充申请不会导致较晚的召回。",
                ),
            ],
            "relationship": [
                _txt(
                    "Predicate relationships for 510(k) are not modelled because openFDA exposes no predicate identifier; candidate relations are not established.",
                    "由于 openFDA 未提供对比器械标识，510(k) 的对比关系未建模；候选关系不代表已确认。",
                ),
            ],
            "cannot_answer": [
                _txt(_CANNOT_CONCLUDE_COMMON_EN, _CANNOT_CONCLUDE_COMMON_ZH),
                _txt(
                    "This brief cannot say that the device is safe, effective, commercially successful or still marketed.",
                    "本简报不能说明该器械安全、有效、商业成功或仍在销售。",
                ),
            ],
        },
    }


def _device_brief_from_detail(dataset: Dataset, payload: dict[str, Any]) -> dict[str, Any]:
    device = payload["device"]
    application = payload.get("application")
    family = payload.get("family")
    versions = payload.get("versions") or []
    recalls_confirmed = (payload.get("related_recalls") or {}).get("confirmed") or []
    recalls_candidate = (payload.get("related_recalls") or {}).get("candidate") or []
    relations = payload.get("relations") or {}
    findings: list[dict[str, Any]] = []
    supplements = [row for row in versions if row.get("kind") == "pma_supplement"]
    if supplements:
        dates = [row.get("decision_date") for row in supplements if row.get("decision_date")]
        findings.append(_finding(
            finding_id="pma_supplement_history",
            category="finding",
            title_en="This device's approved history is a long supplement chain",
            title_zh="该器械的获批历史是一长串补充申请",
            statement_en=(
                f"{_n(len(supplements))} supplement decisions follow the original approval"
                + (f", from {min(dates)} to {max(dates)}" if dates else "")
                + ". Each supplement changed an already approved device."
            ),
            statement_zh=(
                f"原始批准之后有 {_n(len(supplements))} 条补充申请决定"
                + (f"，时间从 {min(dates)} 到 {max(dates)}" if dates else "")
                + "。每条补充申请变更的都是已获批器械。"
            ),
            cannot_en="A supplement is not a new device, a new indication or a market launch; the chain does not measure R&D intensity.",
            cannot_zh="补充申请不是新器械、新适应症或市场发布；该链条不衡量研发强度。",
            basis={"rule": "device has at least one supplement in the snapshot", "inputs": {"supplements": len(supplements), "first": min(dates) if dates else None, "last": max(dates) if dates else None}, "rules_version": RULES_VERSION},
            evidence={"record_count": len(supplements), "records": [], "note": _txt("Every supplement is listed in the timeline with its official URL.", "每条补充申请都在时间线中列出并附官方链接。")},
            drilldown={"url": "/devices/" + str(device.get("official_id") or ""), "label": _txt("Open the device page", "打开器械页面")},
        ))
    if not recalls_confirmed:
        findings.append(_finding(
            finding_id="no_confirmed_recall_link",
            category="caution",
            title_en="No recall is linked to this device by an official K number",
            title_zh="没有召回通过官方 K 号码关联到该器械",
            statement_en="No recall record in this snapshot carries this application's K number in its official reference field.",
            statement_zh="本快照中没有召回记录的官方引用字段包含该申请的 K 号码。",
            cannot_en=("This is not evidence that no recall occurred. Recalls without the official reference field remain in the unlinked recall browser."),
            cannot_zh="这不能证明没有发生召回。缺少官方引用字段的召回仍保留在未关联召回浏览器中。",
            basis={"rule": "no confirmed recall_references_application relation", "inputs": {"confirmed_recalls": 0, "candidate_recalls": len(recalls_candidate)}, "rules_version": RULES_VERSION},
            evidence={"record_count": 0, "records": [], "note": _txt("The absence is a snapshot fact, not a safety statement.", "该缺失是快照事实，不是安全性结论。")},
            drilldown={"url": "/devices?view=unlinked", "label": _txt("Open unlinked recalls", "打开未关联召回")},
        ))
    else:
        findings.append(_finding(
            finding_id="confirmed_recall_links",
            category="finding",
            title_en="Recalls are linked to this device by official K number",
            title_zh="有召回通过官方 K 号码关联到该器械",
            statement_en=f"{_n(len(recalls_confirmed))} recall record(s) reference this application through the official K-number field.",
            statement_zh=f"有 {_n(len(recalls_confirmed))} 条召回记录通过官方 K 号码字段引用本申请。",
            cannot_en="A linked recall is a safety action, not a defect rate; the link does not establish cause or severity.",
            cannot_zh="关联的召回是安全行动，不是故障率；该关联不证明因果关系或严重程度。",
            basis={"rule": "confirmed recall_references_application relation", "inputs": {"confirmed_recalls": len(recalls_confirmed)}, "rules_version": RULES_VERSION},
            evidence={"record_count": len(recalls_confirmed), "records": [], "note": _txt("Each linked recall is listed with its official record.", "每条关联召回都附官方记录。")},
            drilldown={"url": "/devices/" + str(device.get("official_id") or ""), "label": _txt("Open the device page", "打开器械页面")},
        ))
    if recalls_candidate:
        findings.append(_finding(
            finding_id="candidate_recall_relations",
            category="caution",
            title_en="Candidate recall relations exist and are not established",
            title_zh="存在候选召回关系，尚未确认",
            statement_en=f"{_n(len(recalls_candidate))} candidate relation(s) suggest a recall link without an official identifier.",
            statement_zh=f"有 {_n(len(recalls_candidate))} 条候选关系暗示召回关联，但缺少官方标识。",
            cannot_en="A candidate is a deterministic similarity rule suggestion; it is never presented as an established relationship.",
            cannot_zh="候选关系是确定性相似度规则的建议，绝不作为已确认关系呈现。",
            basis={"rule": "candidate relations present", "inputs": {"candidate_recalls": len(recalls_candidate)}, "rules_version": RULES_VERSION},
            evidence={"record_count": len(recalls_candidate), "records": [], "note": None},
            drilldown={"url": "/devices/" + str(device.get("official_id") or ""), "label": _txt("Open the device page", "打开器械页面")},
        ))
    return _device_brief_common(
        dataset,
        identity=device,
        application=application,
        family=family,
        versions=versions,
        recalls_confirmed=recalls_confirmed,
        recalls_candidate=recalls_candidate,
        relations_confirmed=len(versions) + len(recalls_confirmed),
        relations_candidate=len(relations.get("candidate") or []),
        timeline=payload.get("timeline") or [],
        findings=findings[:MAX_FINDINGS],
    )


def _device_brief_from_family(dataset: Dataset, payload: dict[str, Any]) -> dict[str, Any]:
    family = payload["family"]
    application = payload.get("application")
    versions = payload.get("versions") or []
    recalls = payload.get("related_recalls") or []
    identity = payload.get("device") or {
        "device_id": family.get("device_id"),
        "official_id": family.get("family_id"),
        "name": family.get("name"),
        "applicant_name": family.get("applicant_name"),
        "product_code": None,
        "identity_basis": "pma_application",
    }
    findings: list[dict[str, Any]] = []
    if family.get("supplement_count"):
        findings.append(_finding(
            finding_id="pma_supplement_history",
            category="finding",
            title_en="This PMA family is a long supplement chain",
            title_zh="该 PMA 家族是一条很长的补充申请链",
            statement_en=f"{_n(family.get('supplement_count'))} supplements carry this PMA number, from {family.get('first_event_date')} to {family.get('last_event_date')}.",
            statement_zh=f"有 {_n(family.get('supplement_count'))} 条补充申请使用该 PMA 编号，时间从 {family.get('first_event_date')} 到 {family.get('last_event_date')}。",
            cannot_en="A supplement changes an approved device; the family is not proof of one commercial product line.",
            cannot_zh="补充申请变更的是已获批器械；该家族不能证明属于同一商业产品线。",
            basis={"rule": "family has supplements", "inputs": {"supplement_count": family.get("supplement_count")}, "rules_version": RULES_VERSION},
            evidence={"record_count": family.get("supplement_count"), "records": [], "note": None},
            drilldown={"url": "/devices/" + str((application or {}).get("official_id") or ""), "label": _txt("Open the device page", "打开器械页面")},
        ))
    if not family.get("original_in_snapshot"):
        findings.append(_finding(
            finding_id="original_missing",
            category="caution",
            title_en="The original approval is not in this snapshot",
            title_zh="原始批准不在本快照中",
            statement_en="This family is shown from its supplements only; the original PMA approval record is absent from the snapshot.",
            statement_zh="该家族仅由补充申请呈现；快照中没有原始 PMA 批准记录。",
            cannot_en="The original decision date and its device description cannot be stated from this snapshot.",
            cannot_zh="无法依据本快照给出原始决定日期及其器械描述。",
            basis={"rule": "family.original_in_snapshot is false", "inputs": {}, "rules_version": RULES_VERSION},
            evidence={"record_count": 0, "records": [], "note": None},
        ))
    return _device_brief_common(
        dataset,
        identity=identity,
        application=application,
        family=family,
        versions=versions,
        recalls_confirmed=recalls,
        recalls_candidate=[],
        relations_confirmed=len(versions) + len(recalls),
        relations_candidate=0,
        timeline=payload.get("timeline") or [],
        findings=findings[:MAX_FINDINGS],
    )


# --------------------------------------------------------------------------- entry point
def build_brief(
    dataset: Dataset,
    *,
    mode: str = "company",
    org: str | None = None,
    orgs: Sequence[str] | None = None,
    device: str | None = None,
    years: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    event_types: Sequence[str] | None = None,
    basis: str = "current_group",
    review: str | None = None,
    pipeline_db: Any = None,
) -> dict[str, Any]:
    if mode == "company":
        if not org:
            raise ValueError("mode=company needs an organization (org)")
        if dataset.organization(org) is None:
            raise KeyError(org)
        return company_brief(
            dataset, org, years=years, date_from=date_from, date_to=date_to,
            event_types=event_types, basis=basis, review=review, pipeline_db=pipeline_db,
        )
    if mode == "compare":
        keys = [key for key in (orgs or []) if key]
        return comparison_brief(
            dataset, keys, years=years, date_from=date_from, date_to=date_to,
            event_types=event_types, basis=basis, review=review, pipeline_db=pipeline_db,
        )
    if mode == "device":
        if not device:
            raise ValueError("mode=device needs a device identifier (device)")
        return device_brief(dataset, device)
    raise ValueError("mode must be company, compare or device")


# --------------------------------------------------------------------------- explain
def explain_metric(
    dataset: Dataset,
    *,
    metric: str,
    org_keys: Sequence[str],
    years: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    event_types: Sequence[str] | None = None,
    basis: str = "current_group",
    review: str | None = None,
) -> dict[str, Any]:
    """Definition, numerator, denominator and the actual records behind one comparison metric."""
    keys = [key for key in dict.fromkeys(org_keys) if key]
    if not keys:
        raise ValueError("explain needs at least one organization")
    for key in keys:
        if dataset.organization(key) is None:
            raise KeyError(key)
    scope = resolve_scope(dataset, years=years, date_from=date_from, date_to=date_to)
    types = [item for item in (event_types or EVENT_TYPE_ORDER) if item in EVENT_TYPE_ORDER] or list(EVENT_TYPE_ORDER)
    if metric == "records_total":
        definition_en = "All attributed records in the window, all selected event types together."
        definition_zh = "窗口内全部已归属记录，包含所选全部事件类型。"
        label_en, label_zh = "All records in the window", "窗口内全部记录"
        base_types, category, product_code = types, None, None
    elif metric.startswith("type.") and metric.split(".", 1)[1] in EVENT_TYPE_ORDER:
        event_type = metric.split(".", 1)[1]
        definition_en = _TYPE_DEFINITIONS_EN[event_type]
        definition_zh = _TYPE_DEFINITIONS_ZH[event_type]
        label_en, label_zh = EVENT_TYPE_LABELS[event_type], _TYPE_LABELS_ZH[event_type]
        base_types, category, product_code = [event_type], None, None
    elif metric.startswith("specialty."):
        category = metric.split(".", 1)[1]
        label_row = next((item for item in dataset.categories if item.id == category), None)
        label_en = label_zh = label_row.label if label_row else category
        definition_en = "Records whose product code's FDA medical specialty is '" + label_en + "'. 'Unknown' is an official dictionary value."
        definition_zh = "产品代码对应的 FDA 医学专科为“" + label_zh + "”的记录。“Unknown”是官方字典取值。"
        base_types, product_code = types, None
    elif metric.startswith("product_code."):
        product_code = metric.split(".", 1)[1].upper()
        meta = dataset.classification_by_code.get(product_code) or {}
        label_en = label_zh = product_code + (" — " + meta["device_name"] if meta.get("device_name") else "")
        definition_en = "Records whose official FDA product code is " + product_code + ". Product codes are FDA classification units, not market segments."
        definition_zh = "官方 FDA 产品代码为 " + product_code + " 的记录。产品代码是 FDA 分类单位，不是市场细分。"
        base_types, category = types, None
    else:
        raise ValueError("unknown metric: " + metric)
    sides = []
    for key in keys:
        events = dataset.filter_events(
            org_keys=[key], event_types=base_types, date_from=scope["from"], date_to=scope["to"],
            categories=[category] if category else None,
            product_code=product_code,
            review=review, basis=None if basis in (None, "", "current_group") else basis,
        )
        org = dataset.organization(key)
        sides.append({
            "key": key,
            "name": org.display_name,
            "count": len(events),
            "records": [_record_ref(event) for event in dataset.sort_events(list(events), "event_date_desc")[:20]],
            "drilldown": events_url(
                org=key, types=base_types, scope=scope, category=category, product_code=product_code,
            ),
        })
    denominator_value = sum(side["count"] for side in sides)
    return {
        "schema": "medradar.brief.explain.v1",
        "metric": metric,
        "label": _txt(label_en, label_zh),
        "definition": _txt(definition_en, definition_zh),
        "unit": "records",
        "scope": scope,
        "event_types": base_types,
        "filters": {
            "category": category,
            "product_code": product_code,
            "ownership_basis": basis or "current_group",
            "review_filter": review or "any",
        },
        "denominator": {
            "label": _txt("records on the sides of this explanation", "本解释各方记录合计"),
            "value": denominator_value,
        },
        "sides": sides,
        "note": _txt(
            "The counts here are computed by the same filter as the brief. Opening the event browser link applies "
            "the identical organization, event-type, date, category or product-code filters.",
            "这里的计数与简报使用同一筛选逻辑。打开事件浏览器链接会应用相同的企业、事件类型、日期、类别或产品代码筛选。",
        ),
    }


# --------------------------------------------------------------------------- exports
def _csv_row(values: Sequence[Any]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(list(values))
    return buffer.getvalue()


def brief_evidence_csv(dataset: Dataset, brief: dict[str, Any]) -> str:
    """One row per supporting record, with the official URL and the verification state.

    The appendix is the audit trail of the brief: every window record for a company or comparison,
    plus the records a finding cites (section column marks which).
    """
    header = [
        "section", "metric", "organization", "official_id", "event_type", "event_date", "published_at",
        "first_observed_at", "available_at", "official_url", "product_code", "fda_specialty",
        "device_name", "applicant_name", "attribution_review", "attribution_verification",
        "record_state", "snapshot_id",
    ]
    lines = [_csv_row(header)]
    snapshot_id = (brief.get("scope") or {}).get("snapshot", {}).get("id") or dataset.snapshot_id
    kind = brief.get("kind")
    if kind == "company":
        org = brief["organization"]["key"]
        types = (brief["scope"].get("event_types") or list(EVENT_TYPE_ORDER))
        events = dataset.filter_events(
            org_keys=[org], event_types=types,
            date_from=brief["scope"]["from"], date_to=brief["scope"]["to"],
            review=None if brief["scope"].get("review_filter") in (None, "", "any") else brief["scope"]["review_filter"],
            basis=None if brief["scope"].get("ownership_basis") in (None, "", "current_group") else brief["scope"]["ownership_basis"],
        )
        for event in dataset.sort_events(list(events), "event_date_desc"):
            lines.append(_record_csv_row("window_records", "", event, snapshot_id))
    elif kind == "compare":
        for side in brief["sides"]:
            events = dataset.filter_events(
                org_keys=[side["key"]], event_types=brief["scope"]["event_types"],
                date_from=brief["scope"]["from"], date_to=brief["scope"]["to"],
                review=None if brief["scope"].get("review_filter") in (None, "", "any") else brief["scope"]["review_filter"],
                basis=None if brief["scope"].get("ownership_basis") in (None, "", "current_group") else brief["scope"]["ownership_basis"],
            )
            for event in dataset.sort_events(list(events), "event_date_desc"):
                lines.append(_record_csv_row("side:" + side["key"], "", event, snapshot_id))
    elif kind == "device":
        # Every official application in the family and every linked recall belongs in the appendix;
        # the on-screen official-link list is a convenience sample, not the audit trail.
        device = brief.get("device") or {}
        application = brief.get("application") or {}
        versions = brief.get("versions") or []
        recalls = (brief.get("related_recalls") or {}).get("confirmed") or []
        if application:
            lines.append(_csv_row([
                "device_history", "original_application", device.get("applicant_name"), application.get("official_id"),
                application.get("kind"), application.get("decision_date"), "", "", "", application.get("official_url"),
                application.get("product_code"), "", application.get("device_name"), application.get("applicant_name"),
                "", "", "", snapshot_id,
            ]))
        for row in versions:
            lines.append(_csv_row([
                "device_history", "supplement", device.get("applicant_name"), row.get("official_id"),
                row.get("kind"), row.get("decision_date"), "", "", "", row.get("official_url"),
                row.get("product_code"), "", row.get("device_name"), row.get("applicant_name"),
                "", "", "", snapshot_id,
            ]))
        for row in recalls:
            lines.append(_csv_row([
                "device_history", "linked_recall", device.get("applicant_name"), row.get("official_id"),
                "recall", row.get("initiated_date") or row.get("event_date"), "", "", "", row.get("official_url"),
                row.get("product_code") or "", "", row.get("device_name") or "", row.get("applicant_name") or "",
                "", "", "", snapshot_id,
            ]))
    for finding in brief.get("findings") or []:
        for record in (finding.get("evidence") or {}).get("records") or []:
            lines.append(_csv_row([
                "finding:" + str(finding.get("id")), str(finding.get("id")), "", record.get("official_id"),
                record.get("event_type"), record.get("event_date"), record.get("published_at"),
                record.get("first_observed_at"), "", record.get("official_url"), record.get("product_code"),
                "", record.get("device_name"), record.get("applicant_name"), "",
                record.get("attribution_verification"), record.get("record_state"), snapshot_id,
            ]))
    return "".join(lines)


def _record_csv_row(section: str, metric: str, event: Event, snapshot_id: str) -> str:
    return _csv_row([
        section, metric, event.organization_key, event.official_id, event.event_type, event.event_date,
        event.published_at, event.first_observed_at, event.available_at, event.official_url,
        event.product_code, (event.category.label if event.category else ""), event.device_name,
        event.applicant_name, event.attribution_review or "", event.attribution_verification,
        event.record_state, snapshot_id,
    ])


def _md_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _md_table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    lines = ["| " + " | ".join(_md_cell(item) for item in headers) + " |",
             "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(_md_cell(item) for item in row) + " |")
    return "\n".join(lines)


def brief_markdown(brief: dict[str, Any], lang: str = "en") -> str:
    """Render the brief as the deliverable a user takes to a meeting."""
    def t(value: Any) -> str:
        return str(pick(value, lang) or "")

    lines: list[str] = []
    title = t(brief.get("title"))
    lines.append("# " + title)
    lines.append("")
    scope = brief.get("scope") or {}
    lines.append(("**Generated by MedRadar** " if lang != "zh" else "**由 MedRadar 生成** ") + str(brief.get("generated_at")))
    lines.append("")
    lines.append("**" + ("Question" if lang != "zh" else "研究问题") + ":** " + t(brief.get("question")))
    lines.append("")
    snapshot = scope.get("snapshot") or {}
    window_label = str(scope.get("label") or scope.get("label_short"))
    if lang == "zh":
        window_label = window_label.replace(" to ", " 至 ")
    lines.append("- " + ("Window" if lang != "zh" else "时间窗口") + ": " + window_label)
    if lang == "zh":
        event_labels = [_TYPE_LABELS_ZH.get(item, item) for item in (scope.get("event_types") or [])]
    else:
        event_labels = list(scope.get("event_type_labels") or [])
    lines.append("- " + ("Event types" if lang != "zh" else "事件类型") + ": " + ", ".join(event_labels))
    collected_note = (" (collected " + str(snapshot.get("collected_at")) + ")") if lang != "zh" else ("（采集于 " + str(snapshot.get("collected_at")) + "）")
    lines.append("- " + ("Snapshot" if lang != "zh" else "数据快照") + ": `" + str(snapshot.get("id")) + "`" + collected_note)
    lines.append("- " + ("Counting rule" if lang != "zh" else "统计口径") + ": " + t(scope.get("counting_rule")))
    lines.append("")

    kind = brief.get("kind")
    if kind == "company":
        org = brief.get("organization") or {}
        lines.append("## " + ("Executive snapshot" if lang != "zh" else "执行摘要"))
        lines.append("")
        lines.append("**" + str(org.get("display_name")) + "** — " + str(org.get("legal_name") or "") + ((" (" + str(org.get("ticker")) + ")") if org.get("ticker") else ""))
        lines.append("")
        summary = brief.get("summary") or {}
        lines.append(_md_table(
            [("Measure" if lang != "zh" else "指标"), ("Value" if lang != "zh" else "数值"), ("Basis" if lang != "zh" else "口径")],
            [
                [t(tile.get("label")), _n(tile.get("value")) if isinstance(tile.get("value"), int) else tile.get("value"), t(tile.get("note"))]
                for tile in summary.get("tiles") or []
            ],
        ))
        lines.append("")
        lines.append("## " + ("Regulatory activity" if lang != "zh" else "监管活动"))
        lines.append("")
        lines.append(_md_table(
            ["Type", "Records", "Share", "Definition"] if lang != "zh" else ["类型", "记录数", "占比", "定义"],
            [[row.get("label") if lang != "zh" else row.get("label_zh"), _n(row.get("count")), _pct(row.get("share")), t(row.get("definition"))] for row in summary.get("by_type") or []],
        ))
        lines.append("")
        lines.append(_md_table(
            ["Year", "510(k)", "PMA", "PMA supplement", "Recall", "Total", "Partial"] if lang != "zh"
            else ["年份", "510(k)", "PMA", "PMA 补充", "召回", "合计", "不完整"],
            [[row.get("year"), (row.get("counts") or {}).get("510k"), (row.get("counts") or {}).get("pma"), (row.get("counts") or {}).get("pma_supplement"), (row.get("counts") or {}).get("recall"), row.get("total"), ("yes" if row.get("partial") else "no") if lang != "zh" else ("是" if row.get("partial") else "否")] for row in (brief.get("activity") or {}).get("by_year") or []],
        ))
        lines.append("")
        technology = brief.get("technology") or {}
        lines.append("## " + ("Technology areas" if lang != "zh" else "技术领域"))
        lines.append("")
        lines.append("### " + ("FDA medical specialty (source value)" if lang != "zh" else "FDA 医学专科（来源取值）"))
        lines.append("")
        lines.append("> " + t((technology.get("specialty") or {}).get("note")))
        lines.append("")
        lines.append(_md_table(
            ["Specialty", "Records", "Share"] if lang != "zh" else ["专科", "记录数", "占比"],
            [[row.get("label"), _n(row.get("count")), _pct(row.get("share"))] for row in ((technology.get("specialty") or {}).get("rows") or [])[:12]],
        ))
        lines.append("")
        lines.append("### " + ("FDA product-code families (official classification name)" if lang != "zh" else "FDA 产品代码家族（官方分类名称）"))
        lines.append("")
        lines.append("> " + t((technology.get("product_families") or {}).get("note")))
        lines.append("")
        lines.append(_md_table(
            ["Code", "Official FDA classification name", "Specialty", "Class", "Records", "First", "Last"] if lang != "zh"
            else ["代码", "FDA 官方分类名称", "专科", "等级", "记录数", "首次", "最近"],
            [[row.get("product_code"), row.get("official_name") or ("not in dictionary" if lang != "zh" else "不在字典中"), row.get("specialty"), row.get("device_class"), _n(row.get("records")), row.get("first_event_date"), row.get("last_event_date")] for row in (technology.get("product_families") or {}).get("rows") or []],
        ))
        lines.append("")
        lines.append("## " + ("Device intelligence" if lang != "zh" else "器械情报"))
        lines.append("")
        lines.append("> " + t((brief.get("devices") or {}).get("note")))
        lines.append("")
        lines.append(_md_table(
            ["PMA", "Family", "Supplements in window", "First", "Last", "Official record"] if lang != "zh"
            else ["PMA", "家族", "窗口内补充申请", "首次", "最近", "官方记录"],
            [[row.get("pma_number"), row.get("name"), _n(row.get("supplements_in_window")), row.get("first_event_date"), row.get("last_event_date"), row.get("device_url")] for row in (brief.get("devices") or {}).get("families") or []],
        ))
        lines.append("")
        lines.append("## " + ("Recent activity" if lang != "zh" else "近期活动"))
        lines.append("")
        lines.append("> " + t((brief.get("recent") or {}).get("note")))
        lines.append("")
        lines.append(_md_table(
            ["Event date", "Official ID", "Type", "Device", "Official URL"] if lang != "zh" else ["事件日期", "官方标识", "类型", "器械", "官方链接"],
            [[row.get("event_date"), row.get("official_id"), row.get("event_type"), row.get("device_name"), row.get("official_url")] for row in (brief.get("recent") or {}).get("records") or []],
        ))
    elif kind == "compare":
        lines.append("## " + ("Comparability" if lang != "zh" else "可比性"))
        lines.append("")
        comparability = brief.get("comparability") or {}
        lines.append("**" + str(comparability.get("verdict") or "") + "**")
        lines.append("")
        lines.append(_md_table(
            ["Side", "Records", "510(k)", "PMA", "PMA supplement", "Recall", "Curated share"] if lang != "zh"
            else ["对比方", "记录", "510(k)", "PMA", "PMA 补充", "召回", "已核验占比"],
            [[side.get("display_name"), side.get("counts", {}).get("records"), side.get("counts_by_type", {}).get("510k"), side.get("counts_by_type", {}).get("pma"), side.get("counts_by_type", {}).get("pma_supplement"), side.get("counts_by_type", {}).get("recall"), _pct(side.get("counts", {}).get("curated_share"))] for side in brief.get("sides") or []],
        ))
        lines.append("")
        lines.append("## " + ("Comparable measures" if lang != "zh" else "可比指标"))
        lines.append("")
        for metric in brief.get("metrics") or []:
            values = ", ".join(f"{value.get('name')}: {value.get('value')}" for value in metric.get("values") or [])
            lines.append("- **" + t(metric.get("label")) + "** — " + values + ". " + t(metric.get("definition")))
        lines.append("")
        lines.append("## " + ("Coverage by source" if lang != "zh" else "各来源覆盖"))
        lines.append("")
        for side in brief.get("sides") or []:
            lines.append("### " + str(side.get("display_name")))
            lines.append("")
            lines.append(_md_table(
                ["Source", "Records", "First event", "Last event"] if lang != "zh" else ["来源", "记录数", "最早事件", "最近事件"],
                [[row.get("name"), row.get("records"), row.get("min_event_date"), row.get("max_event_date")] for row in (side.get("coverage") or {}).get("sources") or []],
            ))
            lines.append("")
    elif kind == "device":
        device = brief.get("device") or {}
        lines.append("## " + ("Device identity" if lang != "zh" else "器械身份"))
        lines.append("")
        lines.append(_md_table(
            ["Field", "Value"] if lang != "zh" else ["字段", "取值"],
            [
                [("Official FDA identifier" if lang != "zh" else "官方 FDA 标识"), device.get("official_id")],
                [("Applicant as recorded" if lang != "zh" else "记录中的申请人"), device.get("applicant_name")],
                [("Product code" if lang != "zh" else "产品代码"), device.get("product_code")],
                [("Device class" if lang != "zh" else "器械等级"), device.get("device_class")],
                [("Identity basis" if lang != "zh" else "身份依据"), t(device.get("identity_basis_text")) or device.get("identity_basis")],
            ],
        ))
        lines.append("")
        lines.append("## " + ("Official application history" if lang != "zh" else "官方申请历史"))
        lines.append("")
        application = brief.get("application") or {}
        if application:
            lines.append("- " + ("Original" if lang != "zh" else "原始批准") + ": " + str(application.get("official_id")) + " — " + str(application.get("decision_date")) + " — " + str(application.get("official_url")))
        lines.append("- " + ("Supplements in the snapshot" if lang != "zh" else "快照中的补充申请") + ": " + _n(brief.get("supplements_count")))
        lines.append("")
        lines.append(_md_table(
            ["Official ID", "Decision date", "Type", "Supplement reason", "Official URL"] if lang != "zh" else ["官方标识", "决定日期", "类型", "补充原因", "官方链接"],
            [[row.get("official_id"), row.get("decision_date"), row.get("supplement_type") or row.get("kind"), row.get("supplement_reason"), row.get("official_url")] for row in (brief.get("versions") or [])[:40]],
        ))
        recalls = (brief.get("related_recalls") or {}).get("confirmed") or []
        lines.append("")
        lines.append("## " + ("Recalls linked by official K number" if lang != "zh" else "通过官方 K 号码关联的召回"))
        lines.append("")
        lines.append("> " + t((brief.get("related_recalls") or {}).get("note")))
        lines.append("")
        if recalls:
            lines.append(_md_table(
                ["Recall", "Initiated date", "Class", "Reason", "Official URL"] if lang != "zh" else ["召回", "启动日期", "分级", "原因", "官方链接"],
                [[row.get("official_id"), row.get("initiated_date") or row.get("event_date"), row.get("classification") or row.get("device_class"), row.get("reason") or row.get("summary"), row.get("official_url")] for row in recalls],
            ))
        else:
            lines.append(("No recall record in this snapshot links to this application through its official K-number field." if lang != "zh" else "本快照中没有召回记录通过官方 K 号码字段关联到该申请。"))
            lines.append("")

    lines.append("## " + ("Evidence-backed findings" if lang != "zh" else "有证据支持的发现"))
    lines.append("")
    findings = brief.get("findings") or []
    if not findings:
        lines.append(("No finding rule fired for this scope. That is a result: the brief does not invent observations." if lang != "zh" else "该范围没有触发任何发现规则。这也是结论：简报不编造观察。"))
        lines.append("")
    for index, finding in enumerate(findings, start=1):
        lines.append(f"### {index}. " + t(finding.get("title")) + (" *(caution)*" if finding.get("category") == "caution" and lang != "zh" else " *（注意事项）*" if finding.get("category") == "caution" else ""))
        lines.append("")
        lines.append(t(finding.get("statement")))
        lines.append("")
        lines.append("**" + ("What this does not mean" if lang != "zh" else "这不能说明什么") + ":** " + t(finding.get("cannot_conclude")))
        lines.append("")
        evidence = finding.get("evidence") or {}
        records = evidence.get("records") or []
        lines.append("- " + ("Rule" if lang != "zh" else "规则") + ": `" + str((finding.get("basis") or {}).get("rule")) + "`")
        lines.append("- " + ("Records cited" if lang != "zh" else "引用记录") + ": " + _n(evidence.get("record_count")))
        if records:
            for record in records[:5]:
                lines.append("  - " + str(record.get("event_date")) + " · " + str(record.get("official_id")) + " · " + str(record.get("event_type")) + " · " + str(record.get("official_url")))
        if (finding.get("drilldown") or {}).get("url"):
            lines.append("- " + ("Reproduce" if lang != "zh" else "复现") + ": " + str(finding["drilldown"]["url"]))
        lines.append("")

    changes = brief.get("changes")
    change_blocks = changes if isinstance(changes, list) else ([changes] if isinstance(changes, dict) else [])
    if change_blocks:
        lines.append("## " + ("Changes since the previous snapshot" if lang != "zh" else "自上一快照以来的变化"))
        lines.append("")
        for block in change_blocks:
            if not isinstance(block, dict):
                continue
            prefix = (str(block.get("display_name")) + ": ") if block.get("display_name") else ""
            lines.append("> " + prefix + t(block.get("note")))
            lines.append(">")
            lines.append("> " + ("State" if lang != "zh" else "状态") + ": `" + str(block.get("state")) + "`")
            lines.append("")
            items = block.get("items") or []
            if items:
                lines.append(_md_table(
                    ["Change", "Source", "Official ID", "Observed at"] if lang != "zh" else ["变化", "来源", "官方标识", "观察时间"],
                    [[row.get("change_type"), row.get("source_id"), row.get("official_id"), row.get("observed_at") or row.get("created_at")] for row in items[:20]],
                ))
                lines.append("")

    lines.append("## " + ("Evidence and limitations" if lang != "zh" else "证据与限制"))
    lines.append("")
    evidence = brief.get("evidence") or {}
    lines.append("### " + ("Sources of record" if lang != "zh" else "记录来源"))
    lines.append("")
    if kind == "compare":
        for group in evidence.get("sources") or []:
            lines.append("- **" + str(group.get("name")) + "**")
            for row in group.get("sources") or []:
                lines.append("  - " + str(row.get("name")) + ": " + _n(row.get("records")) + " records, " + str(row.get("min_event_date")) + " → " + str(row.get("max_event_date")))
    else:
        lines.append(_md_table(
            ["Source", "Records", "First event", "Last event"] if lang != "zh" else ["来源", "记录数", "最早事件", "最近事件"],
            [[row.get("name"), row.get("records"), row.get("min_event_date"), row.get("max_event_date")] for row in evidence.get("sources") or []],
        ))
    lines.append("")
    links = evidence.get("official_links") or []
    if links:
        lines.append("### " + ("Official record links" if lang != "zh" else "官方记录链接"))
        lines.append("")
        for row in links[:20]:
            lines.append("- " + str(row.get("label")) + " — " + str(row.get("url")))
        lines.append("")
    limitations = brief.get("limitations") or {}
    for key in ("scope", "coverage", "identity", "time", "relationship", "cannot_answer"):
        rows = limitations.get(key) or []
        if not rows:
            continue
        labels = {
            "scope": ("Scope", "范围"), "coverage": ("Coverage", "覆盖"), "identity": ("Identity", "身份"),
            "time": ("Time", "时间"), "relationship": ("Relationships", "关系"), "cannot_answer": ("Questions this cannot answer", "无法回答的问题"),
        }
        lines.append("### " + (labels[key][0] if lang != "zh" else labels[key][1]))
        lines.append("")
        for row in rows:
            lines.append("- " + t(row))
        lines.append("")
    appendix = evidence.get("appendix") or {}
    lines.append("### " + ("Evidence appendix" if lang != "zh" else "证据附录"))
    lines.append("")
    lines.append(t(appendix.get("note")))
    lines.append("")
    lines.append("- " + ("Rows in the appendix" if lang != "zh" else "附录行数") + ": " + _n(appendix.get("rows")))
    lines.append("- " + ("Snapshot" if lang != "zh" else "数据快照") + ": `" + str(snapshot.get("id")) + "`")
    lines.append("- " + ("Content hash" if lang != "zh" else "内容哈希") + ": `" + str(snapshot.get("content_hash") or "not recorded") + "`")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(("Generated by MedRadar PRODUCT-004 from the immutable snapshot above. Every count in this "
                  "document is reproducible from the API filters stated next to it. MedRadar does not rank "
                  "companies, score innovation or generate narrative conclusions." if lang != "zh" else
                  "本文件由 MedRadar PRODUCT-004 基于上述不可变快照生成。文中每个计数都可用紧邻的 API 筛选条件复现。"
                  "MedRadar 不进行企业排名、创新评分，也不生成叙事性商业结论。"))
    lines.append("")
    return "\n".join(lines)


def _filename_part(value: Any) -> str:
    text = "".join(ch if (ch.isalnum() or ch in "-_") else "-" for ch in str(value or ""))
    while "--" in text:
        text = text.replace("--", "-")
    return text.strip("-") or "scope"


def brief_filename(brief: dict[str, Any]) -> str:
    kind = brief.get("kind")
    scope = brief.get("scope") or {}
    stamp = _filename_part(str((scope.get("snapshot") or {}).get("id") or "")[:10])
    window = _filename_part(scope.get("label_short") or scope.get("label") or "")
    if kind == "company":
        name = _filename_part((brief.get("organization") or {}).get("key") or "company")
        return "medradar-company-brief-" + name + "-" + window + "-" + stamp + ".md"
    if kind == "compare":
        keys = "-vs-".join(_filename_part(side.get("key")) for side in brief.get("sides") or [])
        return "medradar-competitor-brief-" + keys + "-" + window + "-" + stamp + ".md"
    return "medradar-device-brief-" + _filename_part((brief.get("device") or {}).get("official_id") or "device") + "-" + stamp + ".md"
