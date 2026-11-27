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

from .gaps import GAP_TEXT

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


def company_markdown(data: Mapping[str, Any]) -> str:
    """One company as a file: what it holds, where it works, and which claims are weaker.

    A company page is the thing people forward — "what does this company look like" — and until now it
    could only be screenshotted, which carries no source and cannot be checked.
    """
    name = str(data.get("company_name") or data.get("query") or "")
    lines = [f"# {name}", "", f"> 导出于 {_stamp()}。{SOURCE_LINE}", ""]
    if not data.get("found"):
        lines.append(_gap("company_not_in_register"))
        return "\n".join(lines)

    lines.append(f"- 查询词：{data.get('query')}")
    lines.append(f"- 匹配方式：{data.get('matched_by')}")
    if data.get("labeler_duns"):
        lines.append(f"- DUNS：{data.get('labeler_duns')}")
    lines.append("")

    lines.append("## 规模与产出")
    lines.append("")
    lines.append("| 指标 | 数量 | 说明 |")
    lines.append("| --- | ---: | --- |")
    lines.append(f"| 注册设备 | {int(data.get('devices') or 0):,} | FDA UDI 注册表 |")
    lines.append(f"| 批文 | {int(data.get('clearances') or 0):,} | 已关联的 510(k) |")
    failures = int(data.get("failures") or 0)
    lines.append(f"| 失效记录 | {failures:,} | MAUDE，按产品码与品牌匹配 |")
    trials = int(data.get("trials") or 0)
    trial_note = ("按集团名匹配，不等于这个法人实体" if data.get("trial_method") == "group"
                  else "按申办方精确匹配")
    lines.append(f"| 在研试验 | {trials:,} | {trial_note} |")
    patents = int(data.get("patents") or 0)
    patent_note = ("含同一申请人的其他写法" if data.get("patent_variants")
                   else "申请人字段精确匹配")
    lines.append(f"| 专利 | {patents:,} | {patent_note} |")
    papers = int(data.get("papers") or 0)
    lines.append(f"| 相关论文 | {papers:,} | "
                 f"{'公司级匹配：论文提到公司，不等于研究某台设备' if papers else '无匹配'} |")
    lines.append("")

    specialties = data.get("specialties") or []
    if specialties:
        lines.append("## 技术领域（按 FDA 产品码分类）")
        lines.append("")
        lines.append("> 这是「注册了什么」，不是「发表了什么」，也不代表技术领先。")
        lines.append("")
        lines.append("| 技术领域 | 产品码数 | 代表性分类 |")
        lines.append("| --- | ---: | --- |")
        examples = data.get("specialty_examples") or {}
        for item in specialties:
            names = "；".join(examples.get(item["specialty"], [])[:3])
            lines.append(f"| {item['specialty']} | {int(item.get('codes') or 0):,} | {names} |")
        used, total = data.get("area_codes_used"), data.get("area_codes_total")
        if used is not None and total and used < total:
            lines.append("")
            lines.append(f"> 按该公司最常见的 {used:,} 个产品码统计（共 {total:,} 个），"
                         f"这是分布，不是完整清单。")
        lines.append("")
    elif data.get("area_gap"):
        lines.append(f"> {_gap(data.get('area_gap'))}")
        lines.append("")

    brands = data.get("brands") or []
    if brands:
        lines.append("## 品牌")
        lines.append("")
        lines.append("| 品牌 | 型号数 |")
        lines.append("| --- | ---: |")
        for item in brands[:40]:
            lines.append(f"| {item.get('brand')} | {int(item.get('models') or 0):,} |")
        if len(brands) > 40:
            lines.append(f"| … | 共 {len(brands):,} 个品牌 |")
        lines.append("")

    topics = data.get("topics") or []
    if topics:
        lines.append("## 科技地图里的方向")
        lines.append("")
        for item in topics:
            evidence = item.get("evidence_count")
            lines.append(f"- {item.get('topic')}"
                         + (f"（{evidence} 条证据）" if evidence else "")
                         + f" · {item.get('confirmation') or 'TOPIC_RELATED'}")
        lines.append("")
    elif data.get("topic_gap"):
        lines.append(f"> {_gap(data.get('topic_gap'))}")
        lines.append("")

    return "\n".join(lines)


def company_csv(data: Mapping[str, Any]) -> str:
    """One row per company, with the areas flattened so a spreadsheet can pivot on them."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["company", "duns", "matched_by", "devices", "clearances", "failures",
                     "trials", "trial_method", "patents", "papers", "brands", "specialties",
                     "topic_gap"])
    if not data.get("found"):
        return buffer.getvalue()
    writer.writerow([
        data.get("company_name") or data.get("query"), data.get("labeler_duns") or "",
        data.get("matched_by") or "", int(data.get("devices") or 0),
        int(data.get("clearances") or 0), int(data.get("failures") or 0),
        int(data.get("trials") or 0), data.get("trial_method") or "",
        int(data.get("patents") or 0), int(data.get("papers") or 0),
        ";".join(str(item.get("brand")) for item in (data.get("brands") or [])[:50]),
        ";".join(f"{item['specialty']}:{item['codes']}" for item in (data.get("specialties") or [])),
        data.get("topic_gap") or "",
    ])
    return buffer.getvalue()


def areas_markdown(items: Sequence[Mapping[str, Any]], *, updated_at: str | None = None) -> str:
    """The whole-register split by specialty, with the caveats the page prints.

    An export that loses the caveat is worse than no export: the file travels alone, so the reader
    has nothing to correct it against.
    """
    lines = ["# 技术领域分布", "", f"> 导出于 {_stamp()}。{SOURCE_LINE}", ""]
    if updated_at:
        lines.append(f"> 数据更新于 {str(updated_at)[:16]}，全库聚合由夜间任务重算。")
        lines.append("")
    lines.append("> 数的是「注册了什么」——产品码来自厂商登记，不是论文、不是专利。设备多说明铺得广，"
                 "不说明技术领先。一台设备带多个产品码时会在各领域分别计入，所以各行相加大于总设备数。")
    lines.append("")
    if not items:
        lines.append(_gap("specialty_stats_absent"))
        return "\n".join(lines)
    lines.append("| 技术领域 | 产品码 | 设备数 | 公司数 | 设备最多的公司 |")
    lines.append("| --- | ---: | ---: | ---: | --- |")
    for item in items:
        leaders = item.get("top_companies") or []
        names = "；".join(f"{lead.get('company')} {int(lead.get('devices') or 0):,}"
                          for lead in leaders[:4])
        lines.append(f"| {item.get('specialty')} | {int(item.get('codes') or 0):,} | "
                     f"{int(item.get('devices') or 0):,} | {int(item.get('companies') or 0):,} | "
                     f"{names or '—'} |")
    return "\n".join(lines)


def areas_csv(items: Sequence[Mapping[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["specialty", "product_codes", "devices", "companies", "top_company",
                     "top_company_devices"])
    for item in items:
        leaders = item.get("top_companies") or []
        lead = leaders[0] if leaders else {}
        writer.writerow([item.get("specialty"), int(item.get("codes") or 0),
                         int(item.get("devices") or 0), int(item.get("companies") or 0),
                         lead.get("company") or "", int(lead.get("devices") or 0)])
    return buffer.getvalue()


def field_papers_csv(papers: Sequence[Mapping[str, Any]]) -> str:
    """One field's newest archived papers, so the list can be pasted into a report."""
    import csv
    import io

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["发表日期", "标题", "期刊", "论文编号", "链接"])
    for item in papers:
        # paper_id already carries the PMC prefix, so the URL path needs the bare number: measured on a
        # real export, every link read .../article/PMC/PMC13788955 and went nowhere.
        paper_id = str(item.get("paper_id") or "")
        number = paper_id[3:] if paper_id.upper().startswith("PMC") else paper_id
        writer.writerow([item.get("published_at") or "", item.get("title") or "",
                         item.get("journal") or "", paper_id,
                         f"https://europepmc.org/article/PMC/{number}"])
    return buffer.getvalue()


def field_papers_markdown(specialty: str, papers: Sequence[Mapping[str, Any]],
                          *, held: int = 0) -> str:
    """Same bound as the page: the newest of what we hold, not everything published in the field.

    A file travels further than a page and loses its context on the way, so the caveat is in the
    document rather than only in the HTML around it.
    """
    lines = [f"# {specialty} · 最近发表", "",
             f"> 导出于 {_stamp()}。{SOURCE_LINE}", ""]
    lines.append(f"> 本领域已归档论文 {held:,} 篇，下面按发表日期列出最新的 {len(papers)} 篇。"
                 f"这是「我们手上的这些论文里最新的」，不是该领域全部新论文；"
                 f"出版日期在未来的期刊预填记录已排除。")
    lines.append("")
    if not papers:
        lines.append(_gap("no_papers_for_this_specialty"))
        return "\n".join(lines)
    lines.append("| 发表日期 | 标题 | 期刊 | 编号 |")
    lines.append("| --- | --- | --- | --- |")
    for item in papers:
        title = str(item.get("title") or "").replace("|", "\\|")
        journal = str(item.get("journal") or "").replace("|", "\\|")
        lines.append(f"| {item.get('published_at') or ''} | {title} | {journal} | "
                     f"{item.get('paper_id') or ''} |")
    return "\n".join(lines)


def area_markdown(specialty: str, summary: Mapping[str, Any],
                  companies: Sequence[Mapping[str, Any]]) -> str:
    """One specialty's leaders, with the sampling caveat kept."""
    lines = [f"# {specialty}", "", f"> 导出于 {_stamp()}。{SOURCE_LINE}", ""]
    lines.append(f"> {int(summary.get('devices') or 0):,} 台设备 · "
                 f"{int(summary.get('codes') or 0):,} 个产品码 · "
                 f"{int(summary.get('companies') or 0):,} 家公司。"
                 f"数字按注册条目计，一台设备带多个产品码时会在各领域分别计入。")
    lines.append("")
    kept = len(companies)
    total = int(summary.get("companies") or 0)
    if total and kept < total:
        lines.append(f"> 下面是设备数最多的 {kept} 家（全领域共 {total:,} 家）。"
                     f"没上榜不等于规模为零。")
        lines.append("")
    if not companies:
        lines.append(_gap("no_company_in_this_specialty"))
        return "\n".join(lines)
    lines.append("| # | 公司 | 该领域设备数 |")
    lines.append("| ---: | --- | ---: |")
    for item in companies:
        lines.append(f"| {item.get('rank')} | {item.get('company_name')} | "
                     f"{int(item.get('devices') or 0):,} |")
    return "\n".join(lines)


def area_csv(companies: Sequence[Mapping[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["rank", "company", "devices_in_specialty"])
    for item in companies:
        writer.writerow([item.get("rank"), item.get("company_name"),
                         int(item.get("devices") or 0)])
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
    # Technology areas, so the exported file says what the page says.
    areas = [{item["specialty"]: int(item["codes"])
              for item in (c.get("specialties") or [])} for c in found]
    names: dict[str, int] = {}
    for mapping in areas:
        for name, count in mapping.items():
            names[name] = names.get(name, 0) + count
    if names:
        lines.append("")
        lines.append("## 技术领域（按 FDA 产品码分类）")
        lines.append("")
        lines.append("> 数字是落在该领域的产品码数量，空表示没有。这是「注册了什么」，"
                     "不是「发表了什么」，也不代表技术领先。")
        lines.append("")
        lines.append("| 技术领域 | " + " | ".join(str(c.get("company_name")) for c in found) + " |")
        lines.append("| --- |" + " ---: |" * len(found))
        for name in sorted(names, key=lambda key: -names[key])[:12]:
            cells = " | ".join(f"{mapping.get(name):,}" if mapping.get(name) else ""
                               for mapping in areas)
            lines.append(f"| {name} | {cells} |")
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
                     "patents", "papers", "product_codes", "specialties", "topic_gap"])
    for item in companies:
        if not item.get("found"):
            continue
        writer.writerow([
            item.get("company_name") or item.get("query"), item.get("labeler_duns") or "",
            item.get("devices") or 0, item.get("clearances") or 0, item.get("failures") or 0,
            item.get("trials") or 0, item.get("patents") or 0, item.get("papers") or 0,
            ";".join(item.get("product_codes") or []),
            # "Dental:8;Orthopedic:2" - the count matters, not only the name.
            ";".join(f"{row['specialty']}:{row['codes']}"
                     for row in (item.get("specialties") or [])),
            item.get("topic_gap") or "",
        ])
    return buffer.getvalue()


def device_json(timeline: Any, *, query: str) -> str:
    to_dict = getattr(timeline, "to_dict", None)
    payload = to_dict() if callable(to_dict) else {"query": query, "refs": []}
    payload["schema"] = "medradar.radar.device.export.v1"
    payload["exported_at"] = _stamp()
    payload["gaps_explained"] = {code: GAP_TEXT.get(code, code) for code in (timeline.gaps or [])}
    return json.dumps(payload, ensure_ascii=False, indent=2)


__all__ = ["area_csv", "area_markdown", "areas_csv", "areas_markdown", "company_csv",
           "company_markdown", "compare_csv", "compare_markdown", "device_csv", "device_json",
           "device_markdown"]
