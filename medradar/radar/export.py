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

from .paper_passes import TREND_MIN_PAPERS

SOURCE_LINE = ("来源：FDA UDI 设备注册表、FDA 510(k) 摘要正文、MAUDE 失效记录、"
               "ClinicalTrials.gov、公开文献全文。")


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _gap(code: str) -> str:
    return f"`{code}` — {GAP_TEXT.get(code, code)}"


def device_markdown(timeline: Any, *, query: str,
                    shelf: Mapping[str, int] | None = None,
                    emerging: Mapping[str, Any] | None = None,
                    code_peers: Mapping[str, Sequence[Mapping[str, Any]]] | None = None) -> str:
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

    # The shelf the device sits on. The page has shown this since round 68 and the file never did, so a
    # reader who received the file saw one registration with no sense of the category.
    shelf = dict(shelf or {})
    owned = [(str(code), int(shelf.get(str(code)) or 0))
             for code in (getattr(head, "product_codes", None) or []) if int(shelf.get(str(code)) or 0)]
    if owned:
        listed = " · ".join(f"{code} {count:,} 台" for code, count in owned[:3])
        lines.append("> 同类规模：这些产品码下已关联 510(k) 批文的设备台数 —— "
                     f"{listed}。**只统计带批文的设备**，不等于整个注册表的全部同类产品。")
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

    # Who else registers under these codes. The page has carried it since round 135; the file is what gets
    # forwarded, and a peer list without its bound invites "biggest = best".
    peers = dict(code_peers or {})
    peer_lines: list[str] = []
    for code, rows in peers.items():
        if not rows:
            continue
        peer_lines.append("")
        peer_lines.append(f"### 产品码 {code} 下注册最多的公司")
        peer_lines.append("")
        stamp = str((rows[0] or {}).get("computed_at") or "")
        peer_lines.append(f"> 按注册设备数排前 {len(rows)} 位"
                          + (f"，算于 {stamp}" if stamp else "")
                          + "。这是「注册了什么」，不是销量、不是市场份额。")
        peer_lines.append("")
        peer_lines.append("| # | 公司 | 设备数 |")
        peer_lines.append("| ---: | --- | ---: |")
        for item in rows:
            peer_lines.append(f"| {int(item.get('rank') or 0)} | {item.get('company_name')} | "
                              f"{int(item.get('devices') or 0):,} |")
    if peer_lines:
        lines.append("")
        lines.append("## 同一产品码下还有谁")
        lines.extend(peer_lines)

    # What is rising in this device's field, from the same materialised table the page reads. A forwarded
    # dossier is where a number is most likely to be quoted without the sentence that bounds it, so the
    # bound travels in the same paragraph.
    trend = dict(emerging or {})
    if trend.get("term"):
        lines.append("## 这个领域最近上升的词")
        lines.append("")
        # The share, not just the count: the row now keeps both window sizes, so the file says 17/83 the way the
        # field page does. An unqualified count invites "17 papers mention it" to be read as a rate.
        recent_total = int(trend.get("recent_total") or 0)
        baseline_total = int(trend.get("baseline_total") or 0)
        recent_text = (f"{int(trend.get('recent') or 0)}/{recent_total} 篇"
                       if recent_total else f"{int(trend.get('recent') or 0)} 篇")
        baseline_text = (f"{int(trend.get('baseline') or 0)}/{baseline_total} 篇"
                         if baseline_total else f"{int(trend.get('baseline') or 0)} 篇")
        lines.append(f"> {trend.get('term')} · 近 90 天 {recent_text}用到"
                     f"（之前一年 {baseline_text}）· {trend.get('lift')}×"
                     f" · 算于 {trend.get('computed_at') or '未知'}")
        lines.append("> 这是词频，不是我们的技术判断，也不是对这台设备的评价；只统计我们抓到的这批论文。")
        lines.append("")

    gaps = list(dict.fromkeys(timeline.gaps or []))
    if gaps:
        lines.append("## 无法回答的部分")
        lines.append("")
        for code in gaps:
            lines.append(f"- {_gap(code)}")
        lines.append("")
    return "\n".join(lines)


def device_csv(timeline: Any, *, query: str, shelf: Mapping[str, int] | None = None) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    # The shelf travels as a column, not a sentence: a CSV is read by a machine as often as by a person.
    writer.writerow(["query", "device_key", "brand", "model", "company", "di", "duns",
                     "product_codes", "code_devices", "clearances", "specs", "failures", "trials",
                     "patents", "papers", "gaps"])
    shelf = dict(shelf or {})
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
            ";".join(f"{code}:{shelf.get(str(code))}"
                     for code in (ref.product_codes or []) if shelf.get(str(code))),
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

    # Failure reports matched by brand name, with the same bound the page carries. A file that dropped
    # this would show a company's scale and leave the reader thinking nothing has ever been reported.
    brand_shape = data.get("brand_failures") or {}
    if int(brand_shape.get("total") or 0):
        events = brand_shape.get("by_event") or {}
        ordered = [("Malfunction", "故障"), ("Injury", "伤害"), ("Death", "死亡")]
        split = " · ".join(f"{label} {int(events.get(k) or 0):,}"
                           for k, label in ordered if events.get(k))
        other = int(brand_shape.get("total") or 0) - sum(int(events.get(k) or 0) for k, _ in ordered)
        if other > 0:
            split += f" · 其他/未标注 {other:,}"
        lines.append("## 它的品牌报过哪些失效")
        lines.append("")
        lines.append(f"> 用这家公司法人在注册表里的全部 {int(brand_shape.get('brands') or 0):,} 个品牌"
                     f"名称匹配 FDA MAUDE，共 {int(brand_shape.get('total') or 0):,} 条——{split}。")
        lines.append("> **这是名称匹配，不是法定主体归属**：MAUDE 的品牌字段是上报人手写的自由文本，"
                     "同一集团的不同法人、同一品牌的不同型号都会混在一起；而且上报是自愿的，"
                     "数字大小取决于有多少人在报，不是故障率。")
        lines.append("")
        lines.append("| 品牌 | 报告数 |")
        lines.append("| --- | ---: |")
        for item in (brand_shape.get("by_brand") or []):
            lines.append(f"| {str(item.get('brand') or '')} | {int(item.get('reports') or 0):,} |")
        lines.append("")
    elif int(brand_shape.get("brands") or 0):
        lines.append("## 它的品牌报过哪些失效")
        lines.append("")
        lines.append(f"> 用这家公司法人的 {int(brand_shape.get('brands') or 0):,} 个品牌名称匹配 FDA MAUDE，"
                     "一条也没有匹配到。这不等于没有失效：MAUDE 的品牌字段记的是被匹配上的那台设备的"
                     "品牌，同一集团的其他法人、其他产品线会记在别的品牌名下。")
        lines.append("")

    # Registered devices by year: the company's own record, so no name-matching caveat - only the one
    # about what a UDI publish date means.
    years = data.get("device_years") or []
    if years:
        lines.append("## 注册登记按年")
        lines.append("")
        lines.append("> 按 UDI 发布日期统计。**这是 GUDID 的收录时间，不是研发时间**：登记可以晚于上市，"
                     "早年设备也可能被集中补录，当前年份未满。")
        lines.append("")
        lines.append("| 年份 | 注册台数 |")
        lines.append("| --- | ---: |")
        for item in years:
            lines.append(f"| {item.get('year')} | {int(item.get('n') or 0):,} |")
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


def areas_markdown(items: Sequence[Mapping[str, Any]], *, updated_at: str | None = None,
                   recency: Mapping[str, Mapping[str, int]] | None = None,
                   trends: Mapping[str, Mapping[str, Any]] | None = None,
                   order: str = "devices") -> str:
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
    if recency:
        lines.append("> 近 90 天占比：每个领域只保留最新的 120 篇，占比高说明这个领域近期产出密集到把"
                     "这个名额填满——是密度信号，不是产量。")
        lines.append("")
    order_note = {
        "devices": "按注册设备数排序。",
        "companies": "按公司数排序。",
        "papers": "按已归档论文数排序。",
        "recent": "按近 90 天发表占比排序。",
        "pending": "还没被文献线抓到过的领域排在最前，再按设备数——待办队列，不是阅读顺序。",
        "trend": (f"按「上升最快的词」的涨幅排序；只排近 90 天样本达到 {TREND_MIN_PAPERS} 篇的领域，"
                  "样本更小的排在最后。涨幅是词频变化，不是重要性判断。"),
    }.get(order, "")
    if order_note:
        lines.append(f"> 排序：{order_note}")
        lines.append("")
    has_trend = bool(trends)
    header = (["技术领域", "产品码", "设备数", "公司数", "设备最多的公司", "近 90 天占比"]
              + (["上升最快的词"] if has_trend else []))
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| --- | ---: | ---: | ---: | --- | ---: |" + (" --- |" if has_trend else ""))
    for item in items:
        leaders = item.get("top_companies") or []
        names = "；".join(f"{lead.get('company')} {int(lead.get('devices') or 0):,}"
                          for lead in leaders[:4])
        entry = (recency or {}).get(str(item.get("specialty"))) or {}
        share = (f"{int(entry['pct'])}%" if entry else "—")
        cells = [str(item.get("specialty")), f"{int(item.get('codes') or 0):,}",
                 f"{int(item.get('devices') or 0):,}", f"{int(item.get('companies') or 0):,}",
                 names or "—", share]
        if has_trend:
            trend = (trends or {}).get(str(item.get("specialty"))) or {}
            term = str(trend.get("term") or "")
            if term:
                total = int(trend.get("recent_total") or 0)
                cells.append(f"{term} {int(trend.get('recent') or 0)}"
                             + (f"/{total} 篇" if total else " 篇")
                             + f" · {trend.get('lift')}×")
            else:
                cells.append("—")
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def areas_csv(items: Sequence[Mapping[str, Any]],
              recency: Mapping[str, Mapping[str, int]] | None = None,
              trends: Mapping[str, Mapping[str, Any]] | None = None) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    header = ["specialty", "product_codes", "devices", "companies", "top_company",
              "top_company_devices", "papers_held", "papers_last_90d", "recent_pct"]
    if trends:
        header += ["trend_term", "trend_recent", "trend_recent_total", "trend_lift"]
    writer.writerow(header)
    for item in items:
        leaders = item.get("top_companies") or []
        lead = leaders[0] if leaders else {}
        entry = (recency or {}).get(str(item.get("specialty"))) or {}
        cells = [item.get("specialty"), int(item.get("codes") or 0),
                 int(item.get("devices") or 0), int(item.get("companies") or 0),
                 lead.get("company") or "", int(lead.get("devices") or 0),
                 int(entry.get("held") or 0), int(entry.get("recent") or 0),
                 int(entry.get("pct") or 0)]
        if trends:
            trend = (trends or {}).get(str(item.get("specialty"))) or {}
            cells += [trend.get("term") or "", int(trend.get("recent") or 0),
                      int(trend.get("recent_total") or 0), trend.get("lift") or 0]
        writer.writerow(cells)
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
                  companies: Sequence[Mapping[str, Any]],
                  *, failures: Mapping[str, Any] | None = None,
                  topics: Sequence[Mapping[str, Any]] | None = None,
                  emerging: Mapping[str, Any] | None = None,
                  codes: Mapping[str, Any] | None = None) -> str:
    """One specialty's leaders and failure record, with the sampling and reporting caveats kept."""
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
    if companies:
        lines.append("| # | 公司 | 该领域设备数 |")
        lines.append("| ---: | --- | ---: |")
        for item in companies:
            lines.append(f"| {item.get('rank')} | {item.get('company_name')} | "
                         f"{int(item.get('devices') or 0):,} |")
    else:
        # No companies is not a reason to stop: a small field can still have a failure record, and the
        # first version returned here, which dropped the whole failure section for exactly those fields.
        lines.append(_gap("no_company_in_this_specialty"))

    # The failure record travels with the file. A document gets forwarded without the page around it, so
    # the two bounds - voluntary reporting and our sweep window - are written into the document itself.
    shape = dict(failures or {})
    if int(shape.get("total") or 0):
        events = shape.get("by_event") or {}
        lines.append("")
        lines.append("## 这个领域报过哪些失效")
        lines.append("")
        ordered = [("Malfunction", "故障"), ("Injury", "伤害"), ("Death", "死亡")]
        split = " · ".join(f"{label} {int(events.get(key) or 0):,}"
                           for key, label in ordered if events.get(key))
        other = int(shape.get("total") or 0) - sum(int(events.get(k) or 0) for k, _ in ordered)
        if other > 0:
            split += f" · 其他/未标注 {other:,}"
        lines.append(f"> 本领域 {int(shape.get('codes') or 0):,} 个产品码下共 "
                     f"{int(shape.get('total') or 0):,} 条 FDA MAUDE 报告——{split}。")
        lines.append("> **这是报告数，不是故障率**：MAUDE 靠自愿上报，产品用得越多、上报的人越多，"
                     "数字就越大；不能用来比较两个产品谁更安全。")
        years = shape.get("by_year") or {}
        if years:
            keys = sorted(years)
            total_year = sum(int(v or 0) for v in years.values()) or 1
            top_key = max(years, key=lambda k: int(years[k] or 0))
            share = 100.0 * int(years[top_key] or 0) / total_year
            lines.append(f"> 报告日期 {keys[0]}–{keys[-1]}，其中 {top_key} 年占 {share:.0f}%——"
                         "因为我们的失效索引扫的是最近的报告文件，所以近年偏多；"
                         "这不是该领域变得更危险了。")
        lines.append("")
        lines.append("| 产品码 | 器械类别 | 报告数 |")
        lines.append("| --- | --- | ---: |")
        names = shape.get("names") or {}
        for item in (shape.get("by_code") or []):
            code = str(item.get("code") or "")
            lines.append(f"| {code} | {str(names.get(code) or '').strip()} | "
                         f"{int(item.get('reports') or 0):,} |")
    # The chips on the page, with their coverage, so a forwarded file says what the field talks about
    # and not only how big it is.
    topic_rows = list(topics or [])
    if topic_rows:
        lines.append("")
        lines.append("## 这个领域的文献在谈什么")
        lines.append("")
        lines.append("> 从本领域已归档全文中统计。这是「论文里出现的词」，不是我们的技术判断。"
                     "两条过滤：结构性虚词按词表去掉；在 10 个以上领域都出现的词也去掉。")
        lines.append("")
        lines.append("| 词 | 出现在多少篇 | 命中次数 |")
        lines.append("| --- | ---: | ---: |")
        for item in topic_rows:
            lines.append(f"| {item.get('term')} | {int(item.get('papers') or 0):,}/"
                         f"{int(item.get('held') or 0):,} | {int(item.get('count') or 0):,} |")
    # The two lists stay two lists in the file, with their different meanings printed beside them: a
    # forwarded document is where a reader is most likely to take "rising" for "important".
    trend = dict(emerging or {})
    rising = list(trend.get("terms") or [])
    fresh = list(trend.get("new") or [])
    if rising or fresh:
        recent = int(trend.get("recent") or 0)
        baseline = int(trend.get("baseline") or 0)
        lines.append("")
        lines.append("## 近 90 天相对上升的说法")
        lines.append("")
        until = str(trend.get("until") or "")
        lines.append(f"> 本领域近 {int(trend.get('recent_days') or 90)} 天"
                     + (f"（截至 {until}）" if until else "") + f"的 {recent:,} 篇，"
                     f"对比之前一年的 {baseline:,} 篇，比每个词在两边各占多少篇。"
                     "**这是词频，不是我们的技术判断**，而且只统计我们抓到的这批论文。")
        lines.append("")
        if rising:
            lines.append("| 说法 | 类型 | 近 90 天 | 之前一年 | 涨幅 |")
            lines.append("| --- | --- | ---: | ---: | ---: |")
            for item in rising:
                lines.append(f"| {item.get('term')} | 已存在 | {int(item.get('recent') or 0)}/{recent} | "
                             f"{int(item.get('baseline') or 0)}/{baseline} | {item.get('lift')}× |")
        if fresh:
            lines.append("")
            lines.append("### 近 90 天新出现的说法")
            lines.append("")
            lines.append("> 这些词在之前一年里一次都没出现。**可能是新方向，也可能只是一个仪器品牌或"
                         "作者名**——按出现的篇数排，判断它是不是真方向要读原文。")
            lines.append("")
            lines.append("| 说法 | 类型 | 近 90 天 | 之前一年 |")
            lines.append("| --- | --- | ---: | ---: |")
            for item in fresh:
                lines.append(f"| {item.get('term')} | 新出现 | {int(item.get('recent') or 0)}/{recent} | 0/{baseline} |")
    elif int(shape.get("codes") or 0):
        # Checked and empty is an answer; an absent section would read as "not looked at".
        lines.append("")
        lines.append("## 这个领域报过哪些失效")
        lines.append("")
        lines.append(f"> 这个领域的 {int(shape.get('codes') or 0):,} 个产品码下，"
                     "我们扫过的 MAUDE 报告里一条也没有匹配到。"
                     "这不等于没有上报：可能是这些码的报告文件还没扫到。")
    # Which codes the field is made of: the register's structure, and the vocabulary a regulatory reader
    # files and searches in. Absent when the caller did not pass them, not shown empty.
    code_rows = list((codes or {}).get("codes") or [])
    if code_rows:
        total_codes = int((codes or {}).get("total") or len(code_rows))
        lines.append("")
        lines.append("## 这个领域由哪些产品码组成")
        lines.append("")
        lines.append(f"> 按注册设备数排序列出前 {len(code_rows)} 个，共 {total_codes:,} 个。"
                     "设备数为「—」表示这次没能统计，不是没有设备。")
        lines.append("")
        lines.append("| 产品码 | 分类名 | 法规号 | 设备数 |")
        lines.append("| --- | --- | --- | ---: |")
        for item in code_rows:
            devices = item.get("devices")
            lines.append(f"| {item.get('product_code')} | {item.get('device_name') or ''} | "
                         f"{item.get('regulation_number') or ''} | "
                         f"{f'{int(devices):,}' if devices is not None else '—'} |")
    return "\n".join(lines)


def area_csv(companies: Sequence[Mapping[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["rank", "company", "devices_in_specialty"])
    for item in companies:
        writer.writerow([item.get("rank"), item.get("company_name"),
                         int(item.get("devices") or 0)])
    return buffer.getvalue()


def _uncovered(company: Mapping[str, Any], key: str) -> bool:
    """True when a zero in this column means "not in the lane", not "none of them".

    The patent lane covers 92 applicants out of the register; the per-company lookup records that in
    `patent_gap`. The page started saying so in round 133, and the file - which is the artefact that travels -
    kept printing 0.
    """
    if key != "patents":
        return False
    return (int(company.get("patents") or 0) == 0
            and company.get("patent_gap") == "patent_only_searched_not_recorded")


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
        lines.append(f"| {label} | " + " | ".join(
            ("未收录" if _uncovered(c, key) else f"{c.get(key) or 0:,}") for c in found) + " |")
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
    # Brand reports, kept out of the metrics table above for the same reason they are a separate
    # section on the page: devices are the company's own records, these are name matches.
    reports = [c.get("brand_failures") or {} for c in found]
    if any(int(shape.get("total") or 0) for shape in reports):
        lines.append("")
        lines.append("## 品牌报告（名称匹配）")
        lines.append("")
        lines.append("> 按各公司在注册表里的全部品牌名称匹配 FDA MAUDE。**这是名称匹配，不是法定主体"
                     "归属**，也不跨法人合并：同一集团的不同公司各算各的。上报是自愿的，数字大小取决于"
                     "有多少人在报，**不是故障率，不能用来比较谁更安全**。")
        lines.append("")
        lines.append("| 公司 | 报告数 | 故障 | 伤害 | 死亡 |")
        lines.append("| --- | ---: | ---: | ---: | ---: |")
        for company, shape in zip(found, reports):
            total = int(shape.get("total") or 0)
            if total:
                events = shape.get("by_event") or {}
                cells = " | ".join(f"{int(events.get(k) or 0):,}"
                                   for k in ("Malfunction", "Injury", "Death"))
                lines.append(f"| {company.get('company_name')} | {total:,} | {cells} |")
            else:
                # Zero matches is not zero reports, and a bare 0 would say the opposite.
                lines.append(f"| {company.get('company_name')} | "
                             f"— 按 {int(shape.get('brands') or 0):,} 个品牌名未匹配到 | | | |")

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
                     "patents", "patents_covered", "papers", "product_codes", "specialties",
                     "topic_gap"])
    for item in companies:
        if not item.get("found"):
            continue
        writer.writerow([
            item.get("company_name") or item.get("query"), item.get("labeler_duns") or "",
            item.get("devices") or 0, item.get("clearances") or 0, item.get("failures") or 0,
            item.get("trials") or 0,
            # An explicit coverage column, because a CSV has no room for the sentence: the number stays a
            # number and the truth travels beside it.
            "" if _uncovered(item, "patents") else (item.get("patents") or 0),
            "no" if _uncovered(item, "patents") else "yes",
            item.get("papers") or 0,
            ";".join(item.get("product_codes") or []),
            # "Dental:8;Orthopedic:2" - the count matters, not only the name.
            ";".join(f"{row['specialty']}:{row['codes']}"
                     for row in (item.get("specialties") or [])),
            item.get("topic_gap") or "",
        ])
    return buffer.getvalue()


def device_json(timeline: Any, *, query: str,
                code_peers: Mapping[str, Sequence[Mapping[str, Any]]] | None = None) -> str:
    to_dict = getattr(timeline, "to_dict", None)
    payload = to_dict() if callable(to_dict) else {"query": query, "refs": []}
    payload["schema"] = "medradar.radar.device.export.v1"
    payload["exported_at"] = _stamp()
    payload["gaps_explained"] = {code: GAP_TEXT.get(code, code) for code in (timeline.gaps or [])}
    # Who else registers under the same codes; null when the caller had none, so a consumer can tell
    # "not provided" from "nobody".
    peers = dict(code_peers or {})
    payload["code_peers"] = ({code: [{"rank": int(item.get("rank") or 0),
                                      "company_name": item.get("company_name"),
                                      "devices": int(item.get("devices") or 0)}
                                     for item in rows]
                              for code, rows in peers.items()} if peers else None)
    payload["code_peers_bounds"] = ("按注册设备数排序，不是销量或市场份额；"
                                    "同一台设备带多个产品码时会在各码下分别计入。")
    return json.dumps(payload, ensure_ascii=False, indent=2)


def area_failures_json(specialty: str, failures: Mapping[str, Any]) -> str:
    """The failure table as JSON, carrying the two bounds as fields.

    A separate schema rather than reusing area_json: this export answers "which codes report", not "what is
    in this field", and pretending otherwise is how the first version ended up passing a list where a
    summary mapping was expected - a 500 on a URL the parameter validator accepted.
    """
    shape = dict(failures or {})
    names = shape.get("names") or {}
    return _json_payload(
        "area_failures",
        specialty=specialty,
        codes=int(shape.get("codes") or 0),
        reports=int(shape.get("total") or 0),
        by_event=shape.get("by_event") or {},
        by_year=shape.get("by_year") or {},
        by_code=[{"product_code": item.get("code"),
                  "device_name": str(names.get(str(item.get("code"))) or ""),
                  "reports": int(item.get("reports") or 0)}
                 for item in (shape.get("by_code") or [])],
        bounds=[
            "报告数不是故障率：MAUDE 靠自愿上报，产品用得越多、上报的人越多，数字就越大。",
            "失效索引扫的是最近的报告文件，年份分布反映我们的扫描窗口，不是领域趋势。",
        ])


def area_failures_csv(specialty: str, failures: Mapping[str, Any]) -> str:
    """The failure table as its own file.

    One CSV holds one table. Squeezing companies and failure codes into the same sheet, or into two blocks
    under one header, produces a file that no spreadsheet and no parser reads correctly - and the field's
    company list is what the CSV is for. The caveats that must travel with these numbers are in the
    markdown and in the JSON's bounds; a CSV column cannot carry a sentence.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["specialty", "product_code", "device_name", "reports"])
    names = failures.get("names") or {}
    for item in (failures.get("by_code") or []):
        code = str(item.get("code") or "")
        writer.writerow([specialty, code, str(names.get(code) or ""), int(item.get("reports") or 0)])
    return buffer.getvalue()


def _json_payload(schema: str, **fields: Any) -> str:
    """The envelope every JSON export shares, so a consumer can tell which one it received."""
    payload: dict[str, Any] = {"schema": f"medradar.radar.{schema}.export.v1",
                               "exported_at": _stamp(),
                               "source": SOURCE_LINE}
    payload.update(fields)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def recent_markdown(payload: Mapping[str, Any]) -> str:
    """The last fortnight, per field, as a file.

    Same bounds as the page: papers we hold, grouped by the query that fetched them, forward-dated records
    excluded. A forwarded list without those three sentences would read as "this is what was published".
    """
    fields = list(payload.get("fields") or [])
    total = int(payload.get("total") or 0)
    days = int(payload.get("days") or 14)
    until = str(payload.get("until") or "")
    lines = [f"# 近 {days} 天发表", "", f"> 导出于 {_stamp()}。{SOURCE_LINE}", ""]
    lines.append(f"> 截至 {until}，抓到的论文里有 {total:,} 篇的发表日期落在过去 {days} 天。"
                 "**这是我们抓到的，不是该领域全部发表**——没被任何一个领域查询命中的论文不在这里；"
                 "未来日期的记录已排除（期刊会预填下期）。")
    lines.append("")
    if not fields:
        lines.append(_gap("no_papers_in_window"))
        return "\n".join(lines)
    for item in fields:
        lines.append(f"## {item.get('specialty')} · {int(item.get('count') or 0)} 篇")
        lines.append("")
        lines.append("| 发表日期 | 标题 | 编号 |")
        lines.append("| --- | --- | --- |")
        for paper_id, title, published in (item.get("papers") or []):
            lines.append(f"| {published} | {title} | {paper_id} |")
        lines.append("")
    return "\n".join(lines)


def recent_csv(payload: Mapping[str, Any]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["specialty", "published_at", "paper_id", "title"])
    for item in (payload.get("fields") or []):
        for paper_id, title, published in (item.get("papers") or []):
            writer.writerow([item.get("specialty"), published, paper_id, title])
    return buffer.getvalue()


def recent_json(payload: Mapping[str, Any]) -> str:
    return _json_payload(
        "recent",
        days=int(payload.get("days") or 14),
        until=str(payload.get("until") or ""),
        total=int(payload.get("total") or 0),
        fields=[{"specialty": item.get("specialty"),
                 "count": int(item.get("count") or 0),
                 "papers": [{"paper_id": paper_id, "title": title, "published_at": published}
                            for paper_id, title, published in (item.get("papers") or [])]}
                for item in (payload.get("fields") or [])],
        bounds="我们抓到的论文，按领域查询分组；未来日期的记录已排除",
    )


def area_json(specialty: str, summary: Mapping[str, Any],
              companies: Sequence[Mapping[str, Any]],
              *, failures: Mapping[str, Any] | None = None,
              monthly: Sequence[Mapping[str, Any]] | None = None,
              topics: Sequence[Mapping[str, Any]] | None = None,
              emerging: Mapping[str, Any] | None = None,
              codes: Mapping[str, Any] | None = None) -> str:
    """One specialty, machine-readable, with the bounds as fields rather than as prose.

    A JSON consumer will not read a Chinese sentence in a document header, so each caveat is a named
    field: `bounds` says what the numbers are not, and `gaps` carries the same reason codes the page uses.
    """
    shape = dict(failures or {})
    return _json_payload(
        "area",
        specialty=specialty,
        summary={"devices": int(summary.get("devices") or 0),
                 "codes": int(summary.get("codes") or 0),
                 "companies": int(summary.get("companies") or 0)},
        companies=[{"rank": item.get("rank"), "company_name": item.get("company_name"),
                    "devices": int(item.get("devices") or 0)} for item in companies],
        companies_kept=len(companies),
        companies_total=int(summary.get("companies") or 0),
        # Which codes make up the field; null when the caller had none to pass, so a consumer can tell
        # "not provided" from "empty".
        product_codes=None if not (codes or {}).get("codes") else [
            {"product_code": item.get("product_code"),
             "device_name": item.get("device_name") or "",
             "regulation_number": item.get("regulation_number") or "",
             "device_class": item.get("device_class") or "",
             # None, not 0: an uncounted code is not an empty one.
             "devices": (None if item.get("devices") is None else int(item.get("devices") or 0))}
            for item in ((codes or {}).get("codes") or [])],
        product_codes_total=int((codes or {}).get("total") or 0),
        # Two named fields, not one list: a consumer that merges them would rank a brand-new instrument name
        # above a real trend, which is the defect round 106 fixed on the page.
        terms_rising=[{"term": item.get("term"), "recent": int(item.get("recent") or 0),
                       "baseline": int(item.get("baseline") or 0), "lift": item.get("lift")}
                      for item in ((emerging or {}).get("terms") or [])],
        terms_new=[{"term": item.get("term"), "recent": int(item.get("recent") or 0),
                    "baseline": 0} for item in ((emerging or {}).get("new") or [])],
        terms_window={"recent_days": int((emerging or {}).get("recent_days") or 90),
                      "recent_papers": int((emerging or {}).get("recent") or 0),
                      "baseline_papers": int((emerging or {}).get("baseline") or 0),
                      "until": (emerging or {}).get("until") or ""},
        terms_bounds="词频，不是技术判断；只统计我们抓到的这批论文；新出现的词可能是仪器品牌或作者名",
        failures={"codes": int(shape.get("codes") or 0),
                  "reports": int(shape.get("total") or 0),
                  "by_event": shape.get("by_event") or {},
                  "by_code": shape.get("by_code") or [],
                  "by_year": shape.get("by_year") or {}},
        monthly=list(monthly or []),
        topics=[{"term": item.get("term"),
                 "papers": int(item.get("papers") or 0),
                 "held": int(item.get("held") or 0),
                 "hits": int(item.get("count") or 0)} for item in (topics or [])],
        bounds=[
            "失败记录是 MAUDE 报告数，不是故障率：自愿上报，产品用得越多、上报的人越多，数字越大。",
            "失效索引扫的是最近的报告文件，年份分布反映我们的扫描窗口，不是领域趋势。",
            "月度论文分布来自一轮抓取，年份集中，不代表该领域全部发表。",
            "topics 是论文里出现的词，不是技术判断；已去掉结构性虚词与在 10 个以上领域出现的通用词。",
        ],
        gaps={code: GAP_TEXT.get(code, code) for code in
              (["no_company_in_this_specialty"] if not companies else [])})


def company_json(data: Mapping[str, Any]) -> str:
    """One company, machine-readable. The name-matched block is a separate key, never merged with totals."""
    brand_shape = dict(data.get("brand_failures") or {})
    return _json_payload(
        "company",
        company_name=data.get("company_name"), query=data.get("query"),
        found=bool(data.get("found")), labeler_duns=data.get("labeler_duns"),
        matched_by=data.get("matched_by"),
        counts={"devices": int(data.get("devices") or 0),
                "clearances": int(data.get("clearances") or 0),
                "failures_by_product_code": int(data.get("failures") or 0),
                "trials": int(data.get("trials") or 0),
                "patents": int(data.get("patents") or 0),
                "papers": int(data.get("papers") or 0)},
        brands=data.get("brands") or [],
        product_codes=data.get("product_codes") or [],
        product_code_total=data.get("product_code_total"),
        specialties=data.get("specialties") or [],
        device_years=data.get("device_years") or [],
        brand_reports={"brands_matched": int(brand_shape.get("brands") or 0),
                       "reports": int(brand_shape.get("total") or 0),
                       "by_brand": brand_shape.get("by_brand") or [],
                       "by_event": brand_shape.get("by_event") or {},
                       "attribution": "name_match_not_legal_entity"},
        bounds=[
            "brand_reports 是名称匹配，不是法定主体归属，也不跨法人合并。",
            "brand_reports 是 MAUDE 报告数，不是故障率。",
            "device_years 按 UDI 发布日期统计，是 GUDID 的收录时间，不是研发时间。",
            "trials 可能按集团名匹配，不等于这个法人实体。",
        ])


def compare_json(companies: Sequence[Mapping[str, Any]]) -> str:
    found = [c for c in companies if c.get("found")]
    return _json_payload(
        "compare",
        companies=[{"company_name": c.get("company_name"),
                    "counts": {"devices": int(c.get("devices") or 0),
                               "clearances": int(c.get("clearances") or 0),
                               "failures_by_product_code": int(c.get("failures") or 0),
                               "trials": int(c.get("trials") or 0),
                               # null, not 0: the patent lane covers 92 applicants, so an absent
                               # count here means "not covered", and a consumer reading 0 would rank it.
                               "patents": (None if _uncovered(c, "patents")
                                           else int(c.get("patents") or 0)),
                               "papers": int(c.get("papers") or 0)},
                    "product_codes": c.get("product_codes") or [],
                    "specialties": c.get("specialties") or [],
                    "device_years": c.get("device_years") or [],
                    "brand_reports": {"brands_matched": int((c.get("brand_failures") or {}).get("brands") or 0),
                                      "reports": int((c.get("brand_failures") or {}).get("total") or 0),
                                      "by_event": (c.get("brand_failures") or {}).get("by_event") or {},
                                      "attribution": "name_match_not_legal_entity"}}
                   for c in found],
        missing=[{"query": c.get("query")} for c in companies if not c.get("found")],
        bounds=["注册设备多表示铺货广，批文多才表示产品线深；两者不可互换。",
                "brand_reports 是名称匹配，不是法定主体归属，也不跨法人聚合。",
                "counts.patents 为 null 表示这家公司不在专利库覆盖范围内（专利库只覆盖已抓取的受让人），"
                "不是它没有专利；0 才是搜过而确实没有入库记录。",
                "counts.papers 按注册品牌名称在已归档全文中匹配；提到名称不等于研究这家公司，"
                "索引也只含已归档全文。"])


def areas_json(items: Sequence[Mapping[str, Any]], *, updated_at: str | None = None,
               recency: Mapping[str, Mapping[str, int]] | None = None,
               trends: Mapping[str, Mapping[str, Any]] | None = None,
               order: str = "devices") -> str:
    rows = []
    for item in items:
        entry = (recency or {}).get(str(item.get("specialty"))) or {}
        held = int(entry.get("held") or 0)
        rows.append({
            "specialty": item.get("specialty"),
            "devices": int(item.get("devices") or 0),
            "codes": int(item.get("codes") or 0),
            "companies": int(item.get("companies") or 0),
            # The specialty row does not always carry a paper count; the recency map does. Without the
            # fallback the file said papers 0 next to papers_last_90d 64 - two fields in one object
            # contradicting each other.
            "papers": int(item.get("papers") or held or 0),
            "papers_held": held,
            "matched": int(item.get("matched") or 0),
            "papers_last_90d": int(entry.get("recent") or 0),
            "recent_pct": int(entry.get("pct") or 0),
            # Null when the field has no rising term, so a consumer can tell "no signal" from "not computed".
            "trend": (None if not (trends or {}).get(str(item.get("specialty"))) else {
                "term": ((trends or {}).get(str(item.get("specialty"))) or {}).get("term") or "",
                "recent": int(((trends or {}).get(str(item.get("specialty"))) or {}).get("recent") or 0),
                "recent_total": int(((trends or {}).get(str(item.get("specialty"))) or {})
                                    .get("recent_total") or 0),
                "lift": ((trends or {}).get(str(item.get("specialty"))) or {}).get("lift") or 0,
                "computed_at": ((trends or {}).get(str(item.get("specialty"))) or {})
                               .get("computed_at") or "",
            }),
        })
    return _json_payload(
        "areas",
        updated_at=updated_at,
        order=order,
        specialties=rows,
        bounds=["数字按注册条目计，一台设备带多个产品码时会在各领域分别计入。",
                "recent_pct 建立在每领域 120 篇的上限上：它是产出密度的信号，不是产量。"])


def field_papers_json(specialty: str, papers: Sequence[Mapping[str, Any]],
                      *, held: int = 0) -> str:
    return _json_payload(
        "papers",
        specialty=specialty, held=int(held),
        papers=[{"paper_id": item.get("paper_id"), "title": item.get("title"),
                 "journal": item.get("journal"), "published_at": item.get("published_at")}
                for item in papers],
        bounds=["这是「我们手上的这些论文里最新的」，不是该领域全部新论文；"
                "出版日期在未来的期刊预填记录已排除。"])


__all__ = ["area_csv", "area_failures_csv", "area_failures_json", "area_json", "area_markdown", "areas_csv", "areas_json", "areas_markdown",
           "company_csv", "company_json", "company_markdown", "compare_csv", "compare_json",
           "compare_markdown", "device_csv", "device_json", "device_markdown",
           "field_papers_json", "field_papers_markdown"]
