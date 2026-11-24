"""The reader-facing pages.

Why server-rendered HTML
------------------------
The workbench SPA is a built React bundle with two routes - a monitoring feed and a technology map -
and no notion of a device. The most valuable thing this system knows is a device's whole public
life, and it had no page: it lived behind `/api/radar/device/view`, an API path that happened to
return HTML. Nobody finds that, and a page nobody can reach is not a feature.

Rebuilding the SPA would mean a Node toolchain and a build step in the deployment path. These pages
are rendered from the same service the API uses, need no build, and answer in one request - which is
also what the reader's question deserves: no spinner, no client-side state, works on a phone, works
with JavaScript disabled.

Design rules, learned from what went wrong
-----------------------------------------
1. The first screen asks one question and shows what the tool is for. The old entry point was a
   filter wall with eight facets and counts in the thousands, which told a reader nothing.
2. Every number carries its source, and every absence carries its reason. "No data" and "never
   collected" are different statements and must never look the same.
3. Order the sections by what an engineer asks, not by which table the data came from:
   approval and specifications, then field failures, then what is being tried, then what has been
   claimed, then what has been written.
4. Long primary text is collapsed but present: a reader decides what to open, and search engines and
   `curl` still see it.
"""

from __future__ import annotations

import html
from typing import Any, Mapping, Sequence

CSS = """
:root{color-scheme:light dark;--bg:#fff;--fg:#111827;--muted:#6b7280;--line:#e5e7eb;
--card:#f9fafb;--accent:#0f766e;--warn:#92400e;--bad:#991b1b}
@media (prefers-color-scheme:dark){:root{--bg:#0b0f14;--fg:#e5e7eb;--muted:#9ca3af;--line:#1f2937;
--card:#111827;--accent:#2dd4bf;--warn:#fbbf24;--bad:#f87171}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB",
"Microsoft YaHei",sans-serif}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
header{border-bottom:1px solid var(--line);padding:14px 0;margin-bottom:28px}
.wrap{max-width:960px;margin:0 auto;padding:0 20px}
.brand{font-weight:700;letter-spacing:.02em}
.brand span{color:var(--muted);font-weight:400;margin-left:8px;font-size:13px}
nav{margin-top:10px;font-size:13.5px}
nav a{margin-right:16px;color:var(--muted)}
nav a.on{color:var(--fg);font-weight:600}
h1{font-size:26px;line-height:1.35;margin:0 0 8px;letter-spacing:-.01em}
h2{font-size:17px;margin:34px 0 12px;padding-bottom:6px;border-bottom:1px solid var(--line)}
h3{font-size:14px;margin:18px 0 8px;color:var(--muted);font-weight:600;letter-spacing:.04em;
text-transform:uppercase}
p.lede{color:var(--muted);margin:0 0 22px;font-size:15px}
form.search{display:flex;gap:10px;margin:0 0 14px;flex-wrap:wrap}
input[type=search],input[type=text]{flex:1 1 260px;min-width:0;padding:13px 15px;font:inherit;
border:1px solid #9ca3af;border-radius:9px;background:var(--bg);color:inherit}
button{padding:13px 22px;font:inherit;font-weight:600;border:0;border-radius:9px;
background:var(--accent);color:#fff;cursor:pointer}
button:hover{filter:brightness(1.08)}
.examples{font-size:13.5px;color:var(--muted);margin-bottom:34px}
.examples a{display:inline-block;margin:4px 8px 4px 0;padding:3px 10px;border:1px solid var(--line);
border-radius:999px;color:var(--fg)}
.grid{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin:0 0 8px}
@media(max-width:900px){.grid{grid-template-columns:repeat(3,1fr)}}
@media(max-width:560px){.grid{grid-template-columns:repeat(2,1fr)}}
.stat{border:1px solid var(--line);border-radius:11px;padding:12px 13px;background:var(--card);
min-width:0}
.stat b{display:block;font-size:20px;font-variant-numeric:tabular-nums;letter-spacing:-.01em;
overflow-wrap:anywhere}
.stat span{color:var(--muted);font-size:12px}
.card{border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:0 0 14px;
background:var(--card)}
.card h4{margin:0 0 6px;font-size:15px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 0}
.chip{font-size:12px;padding:2px 9px;border:1px solid var(--line);border-radius:999px;
color:var(--muted);white-space:nowrap}
.chip.k{color:var(--fg);font-weight:600}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:12.5px}
td.num{text-align:right;font-variant-numeric:tabular-nums}
details{margin:8px 0;border:1px solid var(--line);border-radius:9px;padding:8px 12px}
summary{cursor:pointer;font-size:13.5px;color:var(--muted);font-weight:600}
details pre{white-space:pre-wrap;word-break:break-word;font:12.5px/1.55 ui-monospace,SFMono-Regular,
Menlo,monospace;background:transparent;margin:10px 0 0;max-height:420px;overflow:auto}
.gap{border-left:3px solid var(--warn);background:var(--card);padding:10px 14px;border-radius:0 9px 9px 0;
font-size:13.5px;margin:0 0 8px}
.gap b{color:var(--warn)}
.gap code{font-size:12px;color:var(--muted)}
.muted{color:var(--muted)}
.small{font-size:12.5px}
footer{border-top:1px solid var(--line);margin-top:48px;padding:20px 0 40px;color:var(--muted);
font-size:12.5px}
.kv{margin:0;font-size:13.5px}
.kv div{display:flex;gap:10px;padding:3px 0}
.kv dt{color:var(--muted);min-width:96px}
.kv dd{margin:0}
@media(max-width:600px){h1{font-size:21px}.wrap{padding:0 14px}th,td{padding:6px 6px}}
"""

_CSS = f"<style>{CSS}</style>"

GAP_TEXT = {
    "device_not_in_udi_register": "这个标识不在设备注册表里（K 号、DI、DUNS、型号、品牌、公司都试过了）",
    "no_clearance_linked_to_this_device": "注册表没有把任何批文关联到这台设备",
    "no_readable_summary_for_any_clearance": "批文存在，但存储的文本读不出内容",
    "document_not_published_by_fda": "FDA 没有公布这份文件的正文",
    "document_present_but_unreadable": "文件在，但正文不可读",
    "product_code_not_swept": "这个产品码还没扫过失效记录",
    "no_failure_in_swept_window": "已扫过的窗口里没有这台设备的失效记录",
    "patent_bulk_tables_absent": "专利表还没有导入过数据",
    "patent_source_needs_credential": "专利源需要凭据（EPO 账号审核中）",
    "no_patent_for_this_assignee": "专利表里没有匹配到这个受让人",
    "trials_table_absent": "试验表还没有导入过数据",
    "no_trial_for_this_sponsor": "试验库里没有匹配到这个申办方",
    "paper_index_absent": "论文索引还没有构建",
    "no_paper_mentions_this_device": "已入库的论文里没有提到这个名称",
    "only_generic_words_in_this_name": "这个名称里只有通用词（如 spinal、system），无法定位到具体论文",
}


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def n(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "—"


def gap_note(code: str, *, extra: str = "") -> str:
    text = GAP_TEXT.get(code, code)
    return (f'<div class="gap"><b>没有数据，原因：</b>{esc(text)} '
            f'<code>{esc(code)}</code>{extra}</div>')


def layout(*, title: str, body: str, active: str = "") -> str:
    def link(path: str, label: str, key: str) -> str:
        cls = ' class="on"' if key == active else ""
        return f'<a href="{esc(path)}"{cls}>{esc(label)}</a>'

    return (
        "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{esc(title)}</title>{_CSS}</head><body>"
        '<header><div class="wrap"><div class="brand">MedRadar'
        '<span>医疗器械情报</span></div><nav>'
        + link("/", "设备查询", "device")
        + link("/radar", "实时雷达", "feed")
        + link("/radar/technology-map", "科技地图", "map")
        + link("/sources", "数据覆盖", "sources")
        + "</nav></div></header>"
        f'<main class="wrap">{body}</main>'
        '<footer><div class="wrap">'
        "数据来自 FDA 公开文件（UDI、510(k)、MAUDE、临床试验）与公开文献。"
        "每条结论都标了出处；没有数据的部分会说明为什么没有，而不是留空。"
        "</div></footer></body></html>"
    )


def landing(*, stats: Mapping[str, Any], examples: Sequence[tuple[str, str]]) -> str:
    cards = "".join(
        f'<div class="stat"><b>{n(value)}</b><span>{esc(label)}</span></div>'
        for label, value in stats.items())
    chips = "".join(
        f'<a href="/device?query={esc(q)}">{esc(q)}<span class="muted"> · {esc(what)}</span></a>'
        for q, what in examples)
    body = f"""
<h1>查一台器械，看完它整个公开生命</h1>
<p class="lede">输入 K 号、DI、DUNS、型号、品牌或公司名。批文正文、厂家自己写的规格、现场失效、
在研试验、专利、相关论文——一次查完，全部来自本地数据，不联网、不等待。</p>
<form class="search" method="get" action="/device">
  <input type="search" name="query" placeholder="例如 X1209255、K213506、830350380、Medtronic"
         autofocus aria-label="查询">
  <button type="submit">查询</button>
</form>
<div class="examples">试试：{chips}</div>
<div class="grid">{cards}</div>
<h2>这个工具能回答什么</h2>
<div class="card"><h4>1 · 这台器械凭什么上市</h4>
<p class="muted small">批文号、510(k) 摘要正文、产品码，以及厂家在文件里自己写下的尺寸、压力、温度等规格——
并标出哪些数值因为物理上不可能被丢弃。</p></div>
<div class="card"><h4>2 · 它在真实世界里出过什么事</h4>
<p class="muted small">MAUDE 失效记录，按失效类型计数，并标明匹配强度：型号精确匹配，还是较弱的品牌族匹配。</p></div>
<div class="card"><h4>3 · 同行正在往哪里走</h4>
<p class="muted small">在研临床试验（申办方、状态、入组人数）与相关论文；集团级匹配会明确标注，不冒充这台设备的证据。</p></div>
<div class="card"><h4>4 · 谁在占这块地</h4>
<p class="muted small">受让人的专利、专利族规模与最近公开，用于判断这条技术路线是否已经被围住。</p></div>
<div class="card"><h4>5 · 哪里还没有答案</h4>
<p class="muted small">每个空缺都会写出原因代码，例如 <code>patent_bulk_tables_absent</code>——
"没有数据"和"查过确实没有"是两件事，绝不混为一谈。</p></div>
"""
    return layout(title="MedRadar · 医疗器械情报", body=body, active="device")


def _chip(text: str, *, strong: bool = False) -> str:
    cls = "chip k" if strong else "chip"
    return f'<span class="{cls}">{esc(text)}</span>'


def _identifier_chips(ref: Any) -> str:
    parts = []
    if ref.di:
        parts.append(_chip(f"DI {ref.di}"))
    if ref.labeler_duns:
        parts.append(_chip(f"DUNS {ref.labeler_duns}"))
    for code in (ref.product_codes or [])[:4]:
        parts.append(_chip(f"产品码 {code}"))
    if ref.gmdn_name:
        parts.append(_chip(str(ref.gmdn_name)[:48]))
    return "".join(parts)


def _clearance_block(number: str, summary: Any, specs: Mapping[str, Any] | None) -> str:
    if summary is None:
        return ""
    if summary.gap:
        return (f'<div class="card"><h4>{esc(number)}</h4>'
                + gap_note(summary.gap) + "</div>")
    sections = summary.sections or {}
    rows = "".join(
        f'<tr><td class="num">{n(len(text))}</td><td>{esc(name)}</td></tr>'
        for name, text in sections.items())
    details = "".join(
        f"<details><summary>{esc(name)} · {n(len(text))} 字符</summary>"
        f"<pre>{esc(text)}</pre></details>"
        for name, text in list(sections.items())[:8])
    spec_html = ""
    if specs:
        by_qty = specs.get("by_quantity") or {}
        if by_qty:
            spec_rows = "".join(
                "<tr><td>{}</td><td>{}</td></tr>".format(
                    esc(quantity),
                    "、".join(esc(f"{item['value']} {item['unit']}") for item in items[:6]))
                for quantity, items in list(by_qty.items())[:8])
            spec_html = (
                '<h3>厂家自己写的规格</h3>'
                '<p class="muted small">从 510(k) 正文提取，不是第三方测得。'
                f'本次提取 {n(specs.get("count"))} 条，'
                f'丢弃 {n(specs.get("rejected_implausible"))} 条物理上不可能的数值。</p>'
                '<table><thead><tr><th>量</th><th>数值</th></tr></thead>'
                f"<tbody>{spec_rows}</tbody></table>")
    return f"""
<div class="card">
  <h4>{esc(number)} <span class="muted small">· {esc(summary.text_source or '文本')}
  · {n(summary.text_chars)} 字符</span></h4>
  <div class="small muted">章节构成</div>
  <table><thead><tr><th>字符</th><th>章节</th></tr></thead><tbody>{rows}</tbody></table>
  {spec_html}
  <h3>原文</h3>
  {details or '<p class="muted small">没有可读章节。</p>'}
</div>"""


def device_dossier(timeline: Any, *, query: str) -> str:
    refs = timeline.refs
    if not refs:
        body = (f'<h1>没有找到「{esc(query)}」</h1>'
                '<p class="lede">可以输入 K 号、DI、DUNS、型号、品牌或公司名。</p>'
                + gap_note("device_not_in_udi_register")
                + '<form class="search" method="get" action="/device">'
                  '<input type="search" name="query" value="" aria-label="查询">'
                  '<button type="submit">再查一次</button></form>'
                + '<p class="small muted">例如：'
                  '<a href="/device?query=X1209255">X1209255</a> · '
                  '<a href="/device?query=K213506">K213506</a> · '
                  '<a href="/device?query=Medtronic">Medtronic</a></p>')
        return layout(title="没有找到 · MedRadar", body=body, active="device")

    head = refs[0]
    first_key = head.device_key
    papers = (timeline.papers or {}).get(first_key)
    trials = (timeline.trials or {}).get(first_key)
    patents = (timeline.patents or {}).get(first_key)
    failures = (timeline.failures or {}).get(first_key)
    spec_count = sum(int((b or {}).get("count") or 0) for b in (timeline.specs or {}).values())

    summary_cards = "".join([
        f'<div class="stat"><b>{n(len(timeline.clearances))}</b><span>批文</span></div>',
        f'<div class="stat"><b>{n(spec_count)}</b><span>规格条目</span></div>',
        f'<div class="stat"><b>{n(getattr(failures, "total", 0))}</b><span>失效记录</span></div>',
        f'<div class="stat"><b>{n(getattr(trials, "trials", 0))}</b><span>在研试验</span></div>',
        f'<div class="stat"><b>{n(getattr(patents, "patents", 0))}</b><span>专利</span></div>',
        f'<div class="stat"><b>{n(getattr(papers, "papers", 0))}</b><span>相关论文</span></div>',
    ])

    others = ""
    if len(refs) > 1:
        rows = "".join(
            f'<tr><td>{esc(ref.brand_name or "—")}</td>'
            f'<td>{esc(ref.version_or_model or "—")}</td>'
            f'<td class="muted small">{esc(ref.di or "—")}</td>'
            f'<td class="muted small">{esc(ref.matched_by)}</td></tr>'
            for ref in refs[:20])
        others = (f'<h2>同批匹配到的其他 {n(len(refs) - 1)} 台</h2>'
                  '<div class="card"><table><thead><tr><th>品牌</th><th>型号</th>'
                  f'<th>DI</th><th>匹配方式</th></tr></thead><tbody>{rows}</tbody></table></div>')

    clearance_html = "".join(
        _clearance_block(number, summary, (timeline.specs or {}).get(number))
        for number, summary in timeline.clearances.items()) or gap_note(
        "no_clearance_linked_to_this_device")

    if failures and getattr(failures, "total", 0):
        label = {"model_exact": "型号精确匹配", "brand_exact": "品牌族匹配（较弱）"}.get(
            getattr(failures, "method", ""), getattr(failures, "method", ""))
        by_type = "".join(
            f'<tr><td>{esc(name)}</td><td class="num">{n(count)}</td></tr>'
            for name, count in sorted((failures.by_type or {}).items(), key=lambda kv: -kv[1]))
        failure_html = (f'<div class="card"><h4>{n(failures.total)} 条 · {esc(label)}</h4>'
                        f'<table><tbody>{by_type}</tbody></table></div>')
    else:
        failure_html = gap_note(getattr(failures, "gap", "") or "no_failure_in_swept_window")

    if trials and getattr(trials, "trials", 0):
        level = "集团级（不等于这台设备）" if getattr(trials, "method", "") == "sponsor_group" else "精确"
        rows = "".join(
            f'<tr><td>{esc((item.get("start_date") or "—")[:10])}</td>'
            f'<td>{esc(item.get("nct_id") or "")}</td>'
            f'<td>{esc((item.get("title") or "")[:88])}</td>'
            f'<td class="muted small">{esc(item.get("status") or "")}</td>'
            f'<td class="num">{n(item.get("enrollment") or 0)}</td></tr>'
            for item in (trials.recent or [])[:8])
        trial_html = (f'<div class="card"><h4>{n(trials.trials)} 项 · 申办方'
                      f'「{esc(trials.sponsor)}」· {esc(level)}</h4>'
                      '<table><thead><tr><th>起始</th><th>NCT</th><th>标题</th>'
                      f'<th>状态</th><th>入组</th></tr></thead><tbody>{rows}</tbody></table></div>')
    else:
        trial_html = gap_note(getattr(trials, "gap", "") or "no_trial_for_this_sponsor")

    if patents and getattr(patents, "patents", 0):
        rows = "".join(
            f'<tr><td>{esc(item.get("patent_date") or "—")}</td>'
            f'<td>{esc(item.get("patent_id") or "")}</td>'
            f'<td>{esc((item.get("title") or "")[:90])}</td></tr>'
            for item in (patents.recent or [])[:8])
        patent_html = (f'<div class="card"><h4>{n(patents.patents)} 件 · 受让人'
                       f'「{esc(patents.organization)}」</h4>'
                       '<table><thead><tr><th>公开日</th><th>公开号</th><th>标题</th></tr></thead>'
                       f'<tbody>{rows}</tbody></table></div>')
    else:
        patent_html = gap_note(getattr(patents, "gap", "") or "patent_bulk_tables_absent")

    if papers and getattr(papers, "papers", 0):
        level = "设备名匹配" if getattr(papers, "level", "") == "device" else "公司级匹配（不等于这台设备）"
        rows = "".join(
            f'<tr><td>{esc((item.get("year") or "—")[:10])}</td>'
            f'<td>{esc(item.get("paper_id") or "")}</td>'
            f'<td>{esc((item.get("title") or "")[:90])}</td></tr>'
            for item in (papers.recent or [])[:8])
        terms = "、".join(esc(t) for t in (papers.terms or [])[:5])
        paper_html = (f'<div class="card"><h4>{n(papers.papers)} 篇 · {esc(level)}</h4>'
                      f'<p class="muted small">命中词：{terms}</p>'
                      '<table><thead><tr><th>年份</th><th>编号</th><th>标题</th></tr></thead>'
                      f'<tbody>{rows}</tbody></table></div>')
    else:
        paper_html = gap_note(getattr(papers, "gap", "") or "no_paper_mentions_this_device")

    gaps = "".join(gap_note(code) for code in dict.fromkeys(timeline.gaps or []))

    body = f"""
<p class="small muted"><a href="/">← 重新查询</a></p>
<h1>{esc(head.brand_name or head.version_or_model or query)}</h1>
<p class="lede">{esc(head.company_name or "厂商未知")}
{('· 型号 ' + esc(head.version_or_model)) if head.version_or_model else ''}</p>
<div class="chips">{_identifier_chips(head)}</div>
<div class="grid" style="margin-top:22px">{summary_cards}</div>

<h2>1 · 批文与规格</h2>
<p class="muted small">来源：FDA 510(k) 数据库与已归档的摘要正文。<b>规格是厂家在文件里自己写的</b>，
不是第三方测得，引用前请对照原件。</p>
{clearance_html}

<h2>2 · 现场失效</h2>
<p class="muted small">来源：MAUDE 失效记录。匹配强度决定这条数字有多可信。</p>
{failure_html}

<h2>3 · 在研试验</h2>
<p class="muted small">来源：ClinicalTrials.gov。这是"正在做什么"，不是"做成了什么"。</p>
{trial_html}

<h2>4 · 专利</h2>
<p class="muted small">来源：专利数据库按受让人匹配。</p>
{patent_html}

<h2>5 · 相关论文</h2>
<p class="muted small">来源：已归档全文。提到名称不等于研究这台设备。</p>
{paper_html}

{f'<h2>无法回答的部分</h2>{gaps}' if gaps else ''}

{others}
"""
    return layout(title=f"{head.brand_name or query} · MedRadar", body=body, active="device")


def sources_page(*, meta: Mapping[str, Any]) -> str:
    capabilities = (meta.get("capabilities") or {}).get("device_view") or {}
    sources = meta.get("sources") or []
    rows = "".join(
        f'<tr><td>{esc(item.get("display_name") or item.get("source_id"))}</td>'
        f'<td>{esc(item.get("kind") or "")}</td>'
        f'<td>{esc(item.get("cadence_hours") or "—")}</td>'
        f'<td>{"启用" if item.get("enabled") else "停用"}</td>'
        f'<td class="muted small">{esc(item.get("licence") or "—")}</td></tr>'
        for item in sources)

    def block(name: str, payload: Any, note: str) -> str:
        if payload is None:
            return (f'<div class="card"><h4>{esc(name)}</h4>'
                    f'<p class="muted small">尚未导入。{esc(note)}</p></div>')
        return (f'<div class="card"><h4>{esc(name)}</h4><pre class="small" '
                f'style="margin:0;white-space:pre-wrap">'
                f'{esc(__import__("json").dumps(payload, ensure_ascii=False, indent=2))}</pre></div>')

    body = f"""
<h1>数据覆盖</h1>
<p class="lede">这个工具知道什么、不知道什么，以及每个"不知道"的原因。
下面这些数字是直接读库得到的，不是写死的。</p>
<div class="grid">
  <div class="stat"><b>{n((capabilities.get('failures') or {}).get('rows'))}</b><span>失效记录</span></div>
  <div class="stat"><b>{n((capabilities.get('trials') or {}).get('trials'))}</b><span>临床试验</span></div>
  <div class="stat"><b>{n((capabilities.get('papers') or {}).get('papers'))}</b><span>论文索引</span></div>
  <div class="stat"><b>{n((capabilities.get('patents') or {}).get('patents'))}</b><span>专利</span></div>
</div>
<h2>雷达源</h2>
<div class="card"><table><thead><tr><th>来源</th><th>类型</th><th>周期(h)</th>
<th>状态</th><th>许可</th></tr></thead><tbody>{rows}</tbody></table></div>
<h2>各段的实际库存</h2>
{block("失效索引", capabilities.get("failures"), "运行 failure index 导入。")}
{block("临床试验", capabilities.get("trials"), "运行 trials 导入。")}
{block("专利", capabilities.get("patents"), "EPO 账号审核中（受理号 51279），或等 Google 解封。")}
{block("论文索引", capabilities.get("papers"), "运行 papers_index 构建。")}
<h2>明确不做的事</h2>
<div class="card"><p class="muted small">
· 不把"没有数据"写成"没有"——两者在结果页用不同的字样。<br>
· 不猜测匹配：型号精确匹配与品牌族匹配分开标注。<br>
· 不冒充集团证据：子公司/集团的匹配会注明"集团级"。<br>
· 不编造规格：物理上不可能的数值直接丢弃并计数。
</p></div>
"""
    return layout(title="数据覆盖 · MedRadar", body=body, active="sources")


def pages_router(service: Any) -> Any:
    """Reader-facing routes, mounted at the site root rather than under /api/radar.

    The workbench SPA keeps `/radar` and `/radar/technology-map`; these paths are the ones a person
    types or shares. Registered before the SPA catch-all, so a specific path wins.
    """
    from fastapi import APIRouter, Query
    from fastapi.responses import HTMLResponse

    from .device_view import build as build_view
    from .reference import UdiReference

    router = APIRouter()

    def _store():
        path = service.paths.reference
        if not path.is_file():
            return None
        return UdiReference(str(path))

    def _counts(store) -> dict[str, int]:
        out = {"devices": 0, "failures": 0, "trials": 0, "papers": 0, "patents": 0}
        if store is None:
            return out
        queries = {
            "devices": "SELECT COUNT(*) FROM udi_device",
            "failures": "SELECT COUNT(*) FROM maude_failure_index",
            "trials": "SELECT COUNT(*) FROM trial",
            "papers": "SELECT COUNT(DISTINCT paper_id) FROM paper_term",
            "patents": "SELECT COUNT(*) FROM bulk_patent",
        }
        for key, sql in queries.items():
            try:
                row = store.conn.execute(sql).fetchone()
                out[key] = int(row[0]) if row and row[0] is not None else 0
            except Exception:  # noqa: BLE001 - an absent table is a zero, reported by /sources
                out[key] = 0
        return out

    @router.get("/", response_class=HTMLResponse)
    def home() -> Any:
        store = _store()
        try:
            counts = _counts(store)
        finally:
            if store is not None:
                store.close()
        corpus_docs = 0
        try:
            corpus = service.paths.corpus
            if corpus.is_dir():
                corpus_docs = len(list(corpus.glob("*.json")))
        except Exception:  # noqa: BLE001
            corpus_docs = 0
        stats = {
            "设备注册": counts["devices"],
            "批文语料": corpus_docs,
            "失效记录": counts["failures"],
            "在研试验": counts["trials"],
            "专利": counts["patents"],
            "论文索引": counts["papers"],
        }
        examples = [("X1209255", "按 DI"), ("K213506", "按 K 号"),
                    ("Medtronic", "按公司"), ("Clydesdale", "按品牌")]
        return HTMLResponse(landing(stats=stats, examples=examples))

    @router.get("/device", response_class=HTMLResponse)
    def device_page_view(query: str | None = Query(None, max_length=120),
                         limit: int = Query(25, ge=1, le=100)) -> Any:
        if not query:
            return HTMLResponse(landing(stats={"设备注册": 0}, examples=[]))
        store = _store()
        if store is None:
            return HTMLResponse(layout(
                title="设备库不存在 · MedRadar",
                body=(f'<h1>这台部署没有设备库</h1>'
                      + gap_note("device_not_in_udi_register")),
                active="device"), status_code=503)
        try:
            corpus = service.paths.corpus
            timeline = build_view(store, query, limit=limit,
                                  corpus_root=corpus if corpus.is_dir() else None)
        finally:
            store.close()
        return HTMLResponse(device_dossier(timeline, query=query))

    @router.get("/sources", response_class=HTMLResponse)
    def sources_view() -> Any:
        store = _store()
        capabilities: dict[str, Any] = {"device_view": {}}
        try:
            if store is not None:
                from .failure_index import index_summary
                from .papers_index import summary as papers_summary
                from .patents_bulk import bulk_summary, tables_present as patents_present
                from .trials import tables_present as trials_present
                from .trials import trials_summary

                capabilities["device_view"]["failures"] = index_summary(store)
                capabilities["device_view"]["trials"] = (
                    trials_summary(store) if trials_present(store) else None)
                capabilities["device_view"]["patents"] = (
                    bulk_summary(store) if patents_present(store) else None)
                capabilities["device_view"]["papers"] = papers_summary(store)
        finally:
            if store is not None:
                store.close()
        meta: dict[str, Any] = {"capabilities": capabilities, "sources": []}
        try:
            payload = service.meta() if hasattr(service, "meta") else None
            if isinstance(payload, Mapping):
                meta["sources"] = payload.get("sources") or []
        except Exception:  # noqa: BLE001 - the coverage page must render even if meta fails
            meta["sources"] = []
        return HTMLResponse(sources_page(meta=meta))

    return router


__all__ = ["CSS", "device_dossier", "esc", "gap_note", "landing", "layout", "pages_router",
           "sources_page"]
