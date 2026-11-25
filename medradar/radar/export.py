"""Exports for people who have to send the answer to someone else.

Why this exists
---------------
An engineer does not read a dossier for their own pleasure: they paste it into a design review, a
slide, a supplier email, or a regulatory file. Before this, the only way to do that was a screenshot,
which carries no provenance and cannot be checked.

Rules the exports obey, because a downloaded file outlives the page it came from:

1. Every section names its source. A number without an origin becomes an assertion the moment it
   leaves this site.
2. Every absence is written out with its reason code, exactly as the page does. A file that silently
   omits the empty sections reads as if those questions were never asked.
3. Weaker matches keep their label. A group-level trial count stays "集团名匹配", a company-level
   paper match stays "公司级", a search-derived patent stays excluded and its count is reported.
4. No rendering of anything we did not store. The export repeats the database, it does not embellish.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

GAP_TEXT = {
    "device_not_in_udi_register": "这个标识不在设备注册表里",
    "no_clearance_linked_to_this_device": "注册表没有把任何批文关联到这台设备",
    "no_readable_summary_for_any_clearance": "批文存在，但存储的文本读不出内容",
    "document_not_published_by_fda": "FDA 没有公布这份文件的正文",
    "document_present_but_unreadable": "文件在，但正文不可读",
    "product_code_not_swept": "这个产品码还没扫过失效记录",
    "no_failure_in_swept_window": "已扫过的窗口里没有这台设备的失效记录",
    "patent_bulk_tables_absent": "专利表还没有导入过数据",
    "patent_only_searched_not_recorded": "只有按名字搜到、申请人并非本公司的专利记录",
    "patent_source_needs_credential": "专利源需要凭据（EPO 账号审核中）",
    "no_patent_for_this_assignee": "专利表里没有匹配到这个受让人",
    "trials_table_absent": "试验表还没有导入过数据",
    "no_trial_for_this_sponsor": "试验库里没有匹配到这个申办方",
    "paper_index_absent": "论文索引还没有构建",
    "no_paper_mentions_this_device": "已入库的论文里没有提到这个名称",
    "only_generic_words_in_this_name": "这个名称里只有通用词，无法定位到具体论文",
    "company_not_in_technology_map": "这家公司不在科技地图覆盖范围内",
    "company_not_in_register": "设备注册表里没有匹配到这家公司",
    "no_brand_for_this_company": "这家公司名下没有登记了品牌的设备",
    "no_topic_evidence": "图谱里还没有任何主题证据",
    "no_data": "这一项没有数据，而且没有记录原因（不该发生）",
}

SOURCE_LINE = ("来源：FDA UDI 设备注册表、FDA 510(k) 摘要正文、MAUDE 失效记录、"
               "ClinicalTrials.gov、公开文献全文。")


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _gap(code: str) -> str:
    return f"`{code}` — {GAP_TEXT.get(code, code)}"


def device_markdown(timeline: Any, *, query: str) -> str:
    refs = timeline.refs
    lines: list[str] = []
    if not refs:
        lines.append(f"# 没有找到「{query}」")
        lines.append("")
        lines.append(_gap("device_not_in_udi_register"))
        lines.append("")
        lines.append(f"> 导出于 {_stamp()}。{SOURCE_LINE}")
        return "\n".join(lines)

    head = refs[0]
    lines.append(f"# {head.brand_name or head.version_or_model or query}")
    meta = [head.company_name or "厂商未知"]
    if head.version_or_model:
        meta.append(f"型号 {head.version_or_model}")
    if head.di:
        meta.append(f"DI {head.di}")
    if head.labeler_duns:
        meta.append(f"DUNS {head.labeler_duns}")
    lines.append(" · ".join(meta))
    lines.append("")
    lines.append(f"> 导出于 {_stamp()}。{SOURCE_LINE}")
    lines.append("> 每个空缺都写明原因：「没有数据」和「查过确实没有」不是一回事。")
    lines.append("")

    lines.append("## 1 · 批文与规格")
    lines.append("")
    if not timeline.clearances:
        lines.append(_gap("no_clearance_linked_to_this_device"))
        lines.append("")
    for number, summary in timeline.clearances.items():
        if getattr(summary, "gap", None):
            lines.append(f"### {number}")
            lines.append("")
            lines.append(_gap(summary.gap))
            lines.append("")
            continue
        lines.append(f"### {number} — {summary.text_chars:,} 字符（{summary.text_source or '文本'}）")
        lines.append("")
        sections = summary.sections or {}
        if sections:
            lines.append("| 章节 | 字符 |")
            lines.append("| --- | ---: |")
            for name, text in sections.items():
                lines.append(f"| {name} | {len(text):,} |")
            lines.append("")
        block = (timeline.specs or {}).get(number)
        if block and block.get("by_quantity"):
            lines.append("**厂家在文件里自己写的规格**（不是第三方测得）："
                         f"提取 {block.get('count', 0)} 条，"
                         f"丢弃 {block.get('rejected_implausible', 0)} 条物理上不可能的数值。")
            lines.append("")
            lines.append("| 量 | 数值 |")
            lines.append("| --- | --- |")
            for quantity, items in list(block["by_quantity"].items())[:10]:
                shown = "、".join(f"{item['value']} {item['unit']}" for item in items[:6])
                lines.append(f"| {quantity} | {shown} |")
            lines.append("")

    def section(title: str, key: str, count_label: str, method_note: str = "") -> None:
        lines.append(f"## {title}")
        lines.append("")
        block = (getattr(timeline, key, None) or {}).get(head.device_key)
        total = int(getattr(block, "count", 0) or getattr(block, "total", 0) or 0) if block else 0
        if not block or not total:
            gap = getattr(block, "gap", None) if block else None
            lines.append(_gap(gap or "no_data"))
            lines.append("")
            return
        if method_note:
            lines.append(method_note)
            lines.append("")
        lines.append(f"{count_label}：{total:,}")
        lines.append("")

    section("2 · 现场失效", "failures", "失效记录")
    section("3 · 在研试验", "trials", "在研试验",
            "按申办方匹配；集团级匹配不等于这个法人实体。")
    section("4 · 专利", "patents", "专利",
            "只统计申请人字段为本公司的记录；按名字搜到的另计，不计入。")
    section("5 · 相关论文", "papers", "相关论文",
            "论文提到名称不等于研究这台设备；公司级匹配已标注。")

    gaps = list(dict.fromkeys(timeline.gaps or []))
    if gaps:
        lines.append("## 无法回答的部分")
        lines.append("")
        for code in gaps:
            lines.append(f"- {_gap(code)}")
        lines.append("")
    return "\n".join(lines)


def device_csv(timeline: Any, *, query: str) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["query", "device_key", "brand", "model", "company", "di", "duns",
                     "product_codes", "clearances", "specs", "failures", "trials",
                     "patents", "papers", "gaps"])
    specs_total = sum(int((b or {}).get("count") or 0)
                      for b in (timeline.specs or {}).values())
    for ref in timeline.refs:
        key = ref.device_key
        failures = (timeline.failures or {}).get(key)
        trials = (timeline.trials or {}).get(key)
        patents = (timeline.patents or {}).get(key)
        papers = (timeline.papers or {}).get(key)
        writer.writerow([
            query, key, ref.brand_name or "", ref.version_or_model or "",
            ref.company_name or "", ref.di or "", ref.labeler_duns or "",
            ";".join(ref.product_codes or []),
            len(timeline.clearances), specs_total,
            int(getattr(failures, "total", 0) or 0) if failures else "",
            int(getattr(trials, "trials", 0) or 0) if trials else "",
            int(getattr(patents, "patents", 0) or 0) if patents else "",
            int(getattr(papers, "papers", 0) or 0) if papers else "",
            ";".join(dict.fromkeys(timeline.gaps or [])),
        ])
    return buffer.getvalue()


def compare_markdown(companies: Sequence[Mapping[str, Any]]) -> str:
    found = [c for c in companies if c.get("found")]
    lines = ["# 公司对比", "", f"> 导出于 {_stamp()}。{SOURCE_LINE}", ""]
    if not found:
        lines.append(_gap("company_not_in_register"))
        return "\n".join(lines)
    header = "| 指标 | " + " | ".join(str(c.get("company_name")) for c in found) + " |"
    lines.append(header)
    lines.append("| --- |" + " ---: |" * len(found))
    for label, key in (("注册设备", "devices"), ("批文", "clearances"), ("失效记录", "failures"),
                       ("在研试验", "trials"), ("专利", "patents"), ("相关论文", "papers")):
        lines.append(f"| {label} | " + " | ".join(f"{c.get(key) or 0:,}" for c in found) + " |")
    codes = [set(c.get("product_codes") or []) for c in found]
    shared = set.intersection(*codes) if codes else set()
    union = set.union(*codes) if codes else set()
    lines.append("")
    lines.append(f"共同覆盖的产品码 {len(shared)} 个（合计 {len(union)} 个，"
                 f"重合度 {(100.0 * len(shared) / len(union)) if union else 0:.0f}%）："
                 f"{'、'.join(sorted(shared)) or '无'}")
    lines.append("")
    lines.append("说明：注册设备多表示铺货广，批文多才表示产品线深；两者不可互换。")
    return "\n".join(lines)


def compare_csv(companies: Sequence[Mapping[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["company", "duns", "devices", "clearances", "failures", "trials",
                     "patents", "papers", "product_codes", "topic_gap"])
    for item in companies:
        if not item.get("found"):
            continue
        writer.writerow([
            item.get("company_name") or item.get("query"), item.get("labeler_duns") or "",
            item.get("devices") or 0, item.get("clearances") or 0, item.get("failures") or 0,
            item.get("trials") or 0, item.get("patents") or 0, item.get("papers") or 0,
            ";".join(item.get("product_codes") or []), item.get("topic_gap") or "",
        ])
    return buffer.getvalue()


def device_json(timeline: Any, *, query: str) -> str:
    to_dict = getattr(timeline, "to_dict", None)
    payload = to_dict() if callable(to_dict) else {"query": query, "refs": []}
    payload["schema"] = "medradar.radar.device.export.v1"
    payload["exported_at"] = _stamp()
    payload["gaps_explained"] = {code: GAP_TEXT.get(code, code) for code in (timeline.gaps or [])}
    return json.dumps(payload, ensure_ascii=False, indent=2)


__all__ = ["compare_csv", "compare_markdown", "device_csv", "device_json", "device_markdown"]
