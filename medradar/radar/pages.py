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

import os

import html
import json
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

#: Rendered technology map, keyed by nothing but the clock: the answer cannot change faster than
#: the scheduler cycle (300 s), so five minutes of staleness costs nothing and saves a minute's wait.
_MAP_CACHE: dict[str, Any] = {}
_MAP_TTL = 300.0

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
.second{margin:0 0 30px;padding:14px 16px;border:1px solid var(--line);border-radius:11px;
background:var(--card)}
.second form{margin:8px 0 0}
.second input{padding:10px 13px}
.second button{padding:10px 16px}
.second .hint{font-size:13px;color:var(--muted);margin:0}
.grid{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin:0 0 8px}
@media(max-width:900px){.grid{grid-template-columns:repeat(3,1fr)}}
@media(max-width:560px){.grid{grid-template-columns:repeat(2,1fr)}}
.stat{border:1px solid var(--line);border-radius:11px;padding:12px 13px;background:var(--card);
min-width:0}
.stat b{display:block;font-size:20px;font-variant-numeric:tabular-nums;letter-spacing:-.01em;
overflow-wrap:anywhere}
.stat span{color:var(--muted);font-size:12px;display:block}
.bar{display:block;height:6px;border-radius:3px;background:var(--accent);min-width:2px}
.stat i{display:block;margin-top:3px;font-size:11px;font-style:normal;color:var(--warn);
letter-spacing:.02em}
.card{border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:0 0 14px;
background:var(--card)}
.card h4{margin:0 0 6px;font-size:15px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 0}
.months{display:flex;gap:6px;align-items:flex-end;padding:10px 0 4px;overflow-x:auto}
.month{display:flex;flex-direction:column;align-items:center;gap:4px;min-width:34px}
.month .bar{width:22px;background:var(--accent,#4f7cff);border-radius:3px 3px 0 0;opacity:.85;align-self:flex-end}
.chip{font-size:12px;padding:2px 9px;border:1px solid var(--line);border-radius:999px;
color:var(--muted);white-space:nowrap}
.chip.k{color:var(--fg);font-weight:600}
.tab{display:inline-block;font-size:12.5px;padding:3px 10px;margin:0 6px 0 0;border:1px solid var(--line);
border-radius:6px;color:var(--muted);text-decoration:none}
.tab.on{color:var(--fg);border-color:var(--fg);font-weight:600}
.tab:hover{text-decoration:none;border-color:var(--fg)}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:12.5px;white-space:nowrap}
td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
td.num.lead{font-weight:700;color:var(--accent)}
td.nw{white-space:nowrap}
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
@media(max-width:600px){h1{font-size:21px}.wrap{padding:0 14px}th,td{padding:6px 6px}
/* A four-column evidence table cannot fit 375 px without either wrapping into mush or running off
   the screen. Let it scroll inside its own box instead of pushing the page sideways. */
table{display:block;overflow-x:auto;-webkit-overflow-scrolling:touch}
.stat b{font-size:18px}}
"""

_CSS = f"<style>{CSS}</style>"

from .gaps import GAP_TEXT


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _slug(text: str) -> str:
    """A filename fragment: readable, no shell or header metacharacters."""
    cleaned = "".join(ch if (ch.isalnum() or ch in "-_") else "-" for ch in str(text or ""))
    return (cleaned.strip("-")[:60] or "query").lower()


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
        + link("/paper", "论文反查", "paper")
        + link("/map", "科技地图", "map")
        + link("/areas", "技术领域", "areas")
        + link("/compare", "公司对比", "compare")
        + link("/sources", "数据覆盖", "sources")
        + link("/radar", "实时雷达", "feed")
        + "</nav></div></header>"
        f'<main class="wrap">{body}</main>'
        '<footer><div class="wrap">'
        "数据来自 FDA 公开文件（UDI、510(k)、MAUDE、临床试验）与公开文献。"
        "每条结论都标了出处；没有数据的部分会说明为什么没有，而不是留空。"
        "</div></footer></body></html>"
    )


def _landing_literature(store: Any) -> dict[str, Any]:
    """Newest papers across tracked fields, plus how many fields the lane has reached.

    Wrapped: the landing page must render even when the literature tables do not exist yet.
    """
    if store is None:
        return {}
    try:
        from .paper_passes import QUERIES, by_specialty, recent_any

        held = by_specialty(store)
        return {
            "recent_papers": recent_any(store, limit=8),
            "fields_with_papers": len(held),
            "fields_total": len(QUERIES),
        }
    except Exception:  # noqa: BLE001 - no literature yet is a stated gap, not a failure
        return {}


def _stored_counts(store: Any) -> dict[str, Any] | None:
    try:
        from .store_stats import read

        return read(store)
    except Exception:  # noqa: BLE001 - fall back to counting live
        return None


def _relative_age(stored: Mapping[str, Any]) -> str | None:
    """A human age for the materialised counts, or None when the stamp is unreadable."""
    from datetime import datetime, timezone

    at = stored.get("updated_at")
    if not at:
        return None
    try:
        stamp = datetime.fromisoformat(str(at).replace("Z", "+00:00"))
    except ValueError:
        return None
    seconds = max(0.0, (datetime.now(timezone.utc) - stamp).total_seconds())
    if seconds < 3600:
        return f"{int(seconds // 60)} 分钟前"
    if seconds < 86400:
        return f"{int(seconds // 3600)} 小时前"
    return f"{int(seconds // 86400)} 天前"


def landing(*, stats: Mapping[str, Any], examples: Sequence[tuple[str, str]],
            counts_at: str | None = None, data: Mapping[str, Any] | None = None) -> str:
    """The front door. It used to describe the product; the newest publications are now on it.

    A reader arriving here had no way to see that anything is being tracked - the numbers said what the
    deployment holds, not that it moves. The strip below is the newest papers across every field we
    track, and the line under it says how many fields that is out of how many exist.
    """
    data = data or {}
    recent = data.get("recent_papers") or []
    fields_held = int(data.get("fields_with_papers") or 0)
    fields_total = int(data.get("fields_total") or 0)
    cards = "".join(
        f'<div class="stat"><b>{n(value)}</b><span>{esc(label)}</span></div>'
        for label, value in stats.items())
    # A cached number is a claim about the past; say when it was taken.
    stamp = (f'<p class="small muted" style="margin:6px 0 0">库存计数更新于 {esc(counts_at)}，'
             f'不是每一次请求都重算。</p>' if counts_at else "")
    chips = "".join(
        f'<a href="/device?query={esc(q)}">{esc(q)}<span class="muted"> · {esc(what)}</span></a>'
        for q, what in examples)
    if recent:
        rows = "".join(
            f'<tr><td class="muted small">{esc(str(item.get("published_at") or ""))}</td>'
            f'<td><a href="/paper?id={esc(str(item.get("paper_id")))}">'
            f'{esc(str(item.get("title") or "")[:96])}</a></td>'
            f'<td class="muted small"><a href="/area?name='
            f'{esc(str(item.get("specialty") or ""))}">{esc(str(item.get("specialty") or ""))}</a>'
            f'</td></tr>'
            for item in recent)
        if fields_total and fields_held >= fields_total:
            # The tail of this sentence used to promise a queue that no longer exists: "还没抓的排在
            # 这里" next to "20 / 20" reads as a contradiction, and the reader is told to click a link
            # that has nothing to show.
            scope = (f'{fields_total} 个技术领域全部抓过；此后按"最久未跑优先"轮转刷新，'
                     f'<a href="/areas?sort=papers">按已抓论文数看各领域</a>。')
        elif fields_total:
            scope = (f'文献线已覆盖 {fields_held} / {fields_total} 个技术领域，'
                     f'<a href="/areas?sort=pending">还没抓的排在这里</a>。')
        else:
            scope = ""
        recent_block = (
            '<h2>最近发表</h2>'
            f'<p class="muted small">所跟踪领域里发表日期最新的 {n(len(recent))} 篇。'
            f'这是"我们手上的论文里最新的"，不是全部新论文；出版日期在未来的期刊预填记录已排除。'
            f'{scope}</p>'
            f'<div class="card"><table><thead><tr><th>发表日期</th><th>标题</th>'
            f'<th>领域</th></tr></thead><tbody>{rows}</tbody></table></div>')
    else:
        recent_block = ""
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
<div class="second">
  <p class="hint">手上是一篇论文，想知道做这东西的是谁？</p>
  <form class="search" method="get" action="/paper">
    <input type="search" name="id" placeholder="论文编号，例如 PMC12568234" aria-label="论文编号">
    <button type="submit">反查产品</button>
  </form>
  <p class="hint">也有 <a href="/compare?q=Medtronic,Bauerfeind">公司对比</a> 与
  <a href="/map">科技地图</a>。</p>
</div>
<div class="grid">{cards}</div>
{stamp}
{recent_block}
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


def _looks_chinese(text: str) -> bool:
    from .aliases import has_cjk

    return has_cjk(text)


def _cjk_hint(query: str, *, action: str) -> str:
    """What to say when a Chinese name found nothing.

    Measured in the browser: 「美敦力」 answered "这个标识不在设备注册表里", which reads as "we have never
    heard of Medtronic". The register stores English legal names as filed with the FDA, so a Chinese
    name cannot match - that is the reason, and the page should give the reader a way forward instead
    of blaming the identifier.
    """
    from .aliases import lookup

    hits = lookup(query)
    if hits:
        first = hits[0]
        links = "、".join(
            f'<a href="{action}?q={esc(item["search_as"])}">{esc(item["search_as"])}</a>'
            for item in hits[:3])
        return (f'<div class="gap"><b>「{esc(first["chinese"])}」在注册表里是英文法定名称。</b>'
                f'FDA 登记的是厂商申报的英文名，中文名不会命中。试试：{links}'
                f'<span class="muted small">（中文名对照只是方便输入，不是注册表内容）</span></div>')
    return ('<div class="gap"><b>注册表用的是英文法定名称。</b>'
            '设备与公司都按 FDA 登记的名称存，所以中文名（如「美敦力」）不会命中。'
            '请试用厂商的英文名，或从 <a href="/areas">技术领域</a> 进入。</div>')


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


def _area_line(timeline: Any) -> str:
    """One sentence saying what kind of device this is, in FDA's own classification.

    Every other section describes what happened to the device. This one says what it is, which a
    reader needs first and which the page did not have.
    """
    areas = getattr(timeline, "areas", None) or {}
    if not areas:
        return ""
    parts = []
    seen: set[str] = set()
    for code, meta in areas.items():
        specialty = str(meta.get("medical_specialty") or "").strip() or "未分类"
        name = str(meta.get("device_name") or "").strip()
        regulation = str(meta.get("regulation_number") or "").strip()
        detail = " · ".join(piece for piece in (name, ("21 CFR " + regulation) if regulation else "")
                            if piece)
        label = f'<a href="/area?name={esc(specialty)}">{esc(specialty)}</a>'
        if name:
            label += f'<span class="muted small"> · {esc(detail)}</span>'
        if specialty in seen:
            label += f'<span class="muted small">（{esc(code)}）</span>'
        seen.add(specialty)
        parts.append(f'<li>{label}</li>')
    return ('<p class="small"><b>器械类别（FDA 产品码分类）：</b></p>'
            f'<ul class="small" style="margin:4px 0 0 18px">{"".join(parts)}</ul>')


def _field_topics_line(timeline: Any) -> str:
    """What the device's field is talking about, so one product leads to the research around it.

    The terms are the field's own papers' words, filtered for structural vocabulary; the sentence says
    so, because a term list read as a technology verdict is exactly the overstatement to avoid.
    """
    topics = getattr(timeline, "field_topics", None) or []
    specialty = str(getattr(timeline, "field_specialty", "") or "")
    if not topics or not specialty:
        return ""
    # Same unit and same rule as the field page: coverage over repetition, and the cross-field filter
    # stated. This line kept showing hit counts after round 87 changed the field page, so the same word
    # carried two different numbers on two pages.
    chips = "".join(
        f'<span class="chip" title="{n(item.get("count"))} 次命中">{esc(str(item.get("term")))}'
        f'<span class="muted small"> {n(item.get("papers"))}/{n(item.get("held"))} 篇</span></span>'
        for item in topics)
    return (f'<p class="small" style="margin:10px 0 0">'
            f'<b>{esc(specialty)}</b> 这个领域的文献在谈什么'
            f'（<a href="/area?name={esc(specialty)}">看该领域</a>）'
            f'<span class="muted small"> · 论文里出现的词，不是技术判断；'
            '虚词与在 10 个以上领域都出现的通用词已去掉。数字是「出现在多少篇里」</span></p>'
            f'<div class="chips">{chips}</div>')


def device_dossier(timeline: Any, *, query: str, store: Any = None,
                   substituted_from: str = "") -> str:
    refs = timeline.refs
    if not refs:
        body = (f'<h1>没有找到「{esc(query)}」</h1>'
                '<p class="lede">可以输入 K 号、DI、DUNS、型号、品牌或公司名。</p>'
                # A Chinese name cannot match an English legal name, and saying only "not in the
                # register" leaves the reader thinking the product has never heard of the company.
                + (_cjk_hint(query, action="/device") if _looks_chinese(query) else "")
                # Every gap this search recorded, not just "not in the register". A name scan that hit
                # its time budget means the answer is "we stopped looking", which is a different claim
                # from "it is not there" - and the hardcoded code below used to hide exactly that.
                + "".join(gap_note(code) for code in dict.fromkeys(
                    code for code in (timeline.gaps or []) if code != "device_not_in_udi_register"))
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

    # The summary must not say more than the sections below it. Measured on X1209255: the cards read
    # "200 在研试验" and "2 相关论文" while the sections said 按集团名匹配 and 公司级匹配（不等于这台设备）.
    # A reader skimming the top takes those numbers as facts about this device, which is exactly the
    # overstatement the rest of the page refuses to make.
    def card(value: Any, label: str, note: str = "") -> str:
        # A qualifier on a zero is noise: "0 失效记录 · 品牌族匹配" describes a match that returned
        # nothing, and the reader learns nothing from which method found nothing.
        qualifier = f'<i>{esc(note)}</i>' if note and n(value) != "0" else ""
        return (f'<div class="stat"><b>{n(value)}</b><span>{esc(label)}</span>'
                f'{qualifier}</div>')

    failure_note = ("品牌族匹配" if getattr(failures, "method", "") == "brand_exact" else "")
    trial_note = ("集团级" if getattr(trials, "method", "") == "sponsor_group" else "")
    paper_note = ("公司级" if getattr(papers, "level", "") == "company" else "")
    patent_note = "含其他写法" if (patents and getattr(patents, "variants", None)) else ""

    summary_cards = "".join([
        card(len(timeline.clearances), "批文"),
        card(spec_count, "规格条目"),
        card(getattr(failures, "total", 0), "失效记录", failure_note),
        card(getattr(trials, "trials", 0), "在研试验", trial_note),
        card(getattr(patents, "patents", 0), "专利", patent_note),
        card(getattr(papers, "papers", 0), "相关论文", paper_note),
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

    # How big is the same-product-code shelf? DZE holds 321 devices in the cleared-device census, which
    # is the context a reader wants before treating one registration as the category.
    shelf = ""
    try:
        from .code_census import product_code_census

        # The codes come off the matched device reference and the census off the store the route
        # already holds; the timeline carries neither, so both are passed in rather than guessed at.
        codes = [str(c) for c in (getattr(refs[0], "product_codes", None) or [])][:3]
        census = product_code_census(store) if (codes and store is not None) else {}
        rows = "".join(
            f'<span class="chip">{esc(code)}<span class="muted small"> '
            f'{n(census.get(code) or 0)} 台</span></span>'
            for code in codes if census.get(code))
        if rows:
            shelf = (
                '<p class="small muted" style="margin-top:8px">同类规模：这些产品码下已关联 510(k) 批文的'
                f'设备台数 —— {rows}。'
                '<b>只统计带批文的设备</b>，不等于整个注册表的全部同类产品。</p>')
    except Exception:  # noqa: BLE001 - a census that fails is a line fewer, not a broken page
        shelf = ""

    # The substitution is printed, not hidden: a reader who typed 美敦力 must see that the page is about
    # Medtronic, and that the Chinese name is a convenience, not register content.
    substitution_note = (
        f'<p class="small muted">「{esc(query)}」按英文法定名称「{esc(substituted_from)}」查询'
        '<span class="muted">（中文名对照只是方便输入，不是注册表内容）</span></p>'
        if substituted_from else "")

    gaps = "".join(gap_note(code) for code in dict.fromkeys(timeline.gaps or []))

    body = f"""
<p class="small muted"><a href="/">← 重新查询</a></p>
<h1>{esc(head.brand_name or head.version_or_model or query)}</h1>
{substitution_note}
<p class="lede"><a href="/company?q={esc(head.company_name or '')}">{esc(head.company_name or "厂商未知")}</a>
{('· 型号 ' + esc(head.version_or_model)) if head.version_or_model else ''}</p>
<div class="chips">{_identifier_chips(head)}</div>
{_area_line(timeline)}
{_field_topics_line(timeline)}
{shelf}
<div class="grid" style="margin-top:22px">{summary_cards}</div>

<h2>1 · 批文与规格</h2>
<p class="small muted">导出：<a href="/download?kind=device&format=md&q={esc(query)}">Markdown</a>
 · <a href="/download?kind=device&format=csv&q={esc(query)}">CSV</a>
 · <a href="/download?kind=device&format=json&q={esc(query)}">JSON</a>
 —— 每个空缺都带原因码，可直接发给同事核对。</p>
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


def sources_page(*, meta: Mapping[str, Any], coverage: Mapping[str, Any] | None = None,
                 tunnel: Mapping[str, Any] | None = None) -> str:
    """What this deployment holds, how wide each set reaches, and what is still missing.

    Rewritten after the first audit found the page printing raw JSON, an empty source table, and a
    paper count that disagreed with the landing page by five - on the one page whose job is to state
    the truth about coverage.
    """
    data = coverage or {}
    datasets = data.get("datasets") or []
    shape = data.get("shape") or {}
    gaps = data.get("gaps") or []
    # The nightly steps all swallow their own failures, on purpose. This is where a reader can see that
    # "no new papers" meant "the step returned 503" rather than "nothing was published".
    night = data.get("nightly") or {}
    if night.get("available"):
        night_rows = "".join(
            f'<tr><td>{esc(str(step.get("step")))}</td>'
            f'<td>{"✓" if step.get("ok") else "✗"}</td>'
            f'<td class="muted small">{esc(str(step.get("note") or ""))}</td>'
            f'<td class="muted small">{esc(str(step.get("at") or ""))}</td></tr>'
            for step in (night.get("steps") or []))
        # A run that never reached `done` was interrupted, and printing only "共 N 步" would present a
        # half-finished attempt as the night's work.
        # A rehearsal is real evidence but it is not the night's work, and the two looked identical.
        dry_note = (
            '<p class="gap"><b>这次是手动试跑</b>：不是定时任务执行的结果，'
            '用途是验证链路本身。它跑出的数字是真的，但不代表这一夜做了什么。</p>'
            if night.get("dry") else "")
        interrupted_note = (
            '<p class="gap"><b>这次运行没有跑完</b>：账本里没有 done 这一步，'
            '说明它被中断了（手动结束、超时或机器重启）。下面是它中断前做完的部分。</p>'
            if night.get("interrupted") else "")
        night_block = ('<h2>最近一次夜间任务</h2>'
                       f'<p class="muted small">开始于 {esc(str(night.get("run")))}，'
                       f'共 {n(night.get("count"))} 步。每一步都故意吞掉自己的失败——'
                       '抓不到源是正常的一夜，不是故障——所以这里列出每一步到底做了什么。</p>'
                       + dry_note + interrupted_note +
                       '<div class="card"><table><thead><tr><th>步骤</th><th>结果</th>'
                       f'<th>产出</th><th>时间</th></tr></thead><tbody>{night_rows}</tbody></table></div>')
    elif night:
        night_block = ('<h2>最近一次夜间任务</h2>'
                       '<p class="muted small">还没有记录过夜间任务。'
                       '第一次记录会在下一个 04:20 之后出现。</p>')
    else:
        night_block = ""

    # The public address rotates, and during a reconnect the relay answers 502. Saying so here turns an
    # unexplained error into a known event with a timestamp.
    tunnel_state = dict(tunnel or {})
    if tunnel_state.get("available"):
        rotations = int(tunnel_state.get("rotations") or 0)
        history_rows = "".join(
            f'<tr><td class="small">{esc(str(item.get("at") or ""))}</td>'
            f'<td class="small"><code>{esc(str(item.get("url") or ""))}</code></td></tr>'
            for item in (tunnel_state.get("history") or []))
        tunnel_block = (
            '<h2>公网入口</h2>'
            f'<p class="small">当前地址：<code>{esc(str(tunnel_state.get("url")))}</code></p>'
            '<p class="muted small">隧道是<b>出站</b> ssh 连接（localhost.run 免费档），'
            '中继在自己的域名上终结 TLS 再转发到本机 8791。免费档会周期性换子域，'
            '换的瞬间中继对旧地址回 502——看起来像站点挂了，其实是在重连。'
            f'最近记录到 {n(rotations)} 次地址变更，下面是最新的几次；'
            '重连后自动恢复，不需要人工干预。</p>'
            + (f'<div class="card"><table><thead><tr><th>时间</th><th>新地址</th></tr></thead>'
               f'<tbody>{history_rows}</tbody></table></div>' if history_rows else
               '<p class="muted small">还没有记录到地址变更。</p>'))
    elif tunnel:
        tunnel_block = ('<h2>公网入口</h2>'
                        + gap_note("public_url_absent"))
    else:
        tunnel_block = ""

    def row(label: str, value: Any, note: str = "") -> str:
        return (f'<tr><td>{esc(label)}</td><td class="num">{n(value)}</td>'
                f'<td class="muted small">{esc(note)}</td></tr>')

    def data_row(item: Mapping[str, Any]) -> str:
        # Sentences, joined with a space. Joining with ； produced "无法检索。；按发表日期：" - two
        # complete sentences with a semicolon between them, which reads as a typo.
        pieces = [str(item.get(k) or "").strip() for k in ("note", "beside", "years")]
        note = " ".join(piece for piece in pieces if piece)
        return row(str(item["label"]), item["count"], note)

    dataset_rows = "".join(data_row(item) for item in datasets)
    # The shape of each set matters more than its size: 348k records over how many codes, how many
    # models? A big table with narrow coverage is a small answer.
    shape_rows = "".join([
        # Two numbers, because they answer two questions: how many codes were checked, and how many
        # of those produced a record. Showing one under the other's label is how this page claimed
        # 838 of 5,229 forever.
        row("已检查的产品码", shape.get("failure_codes_checked"),
            f"其中 {n(shape.get('failure_codes_empty'))} 个查了没有可连接的失效记录" if
            shape.get("failure_codes_empty") else "扫过的都算，含空结果"),
        row("有失效记录的产品码", shape.get("failure_codes"), "注册表里的产品码见下方缺口"),
        row("失效记录涉及的型号", shape.get("failure_models"), "型号归一后去重"),
        row("失效记录涉及的品牌", shape.get("failure_brands"), ""),
        row("试验涉及的申办方", shape.get("trial_sponsors"), "按申办方名称去重"),
        row("专利涉及的受让人", shape.get("patent_assignees"), "只算申请人字段真实的记录"),
        row("产品码分类的专科数", shape.get("specialties"), ""),
        row("注册表里的产品码", shape.get("register_codes"), ""),
    ])
    gap_items = "".join(
        f'<li><b>{esc(item.get("title"))}</b>——{esc(item.get("detail"))}</li>' for item in gaps)

    sources = meta.get("sources") or []
    health = data.get("health") or {}
    health_rows = health.get("sources") or []

    def _status_chip(status: str) -> str:
        colour = {"OK": "var(--accent)", "WARN": "var(--warn)", "STALE": "var(--warn)"}.get(
            status, "var(--bad)") if status in {"OK", "WARN", "STALE"} else "var(--bad)"
        return f'<span style="color:{colour};font-weight:600">{esc(status)}</span>'

    def _watermark_cell(item: Mapping[str, Any]) -> str:
        """How current the data is, in the source's own clock.

        A failure counter only grows - it never resets until a run succeeds - so "1,143 次" reads as
        "broken right now" long after the endpoint has recovered (measured 2026-11-28: europepmc showed
        1,143 while the identical query answered 200 from this host). The watermark is the number that
        answers the reader's real question: how far has this source reached?
        """
        stamp = str(item.get("watermark") or "")[:10]
        if stamp:
            return f'<td class="num small">{esc(stamp)}</td>'
        return '<td class="num muted small">—</td>'

    health_table = "".join(
        f'<tr><td>{esc(item.get("source_id"))}</td><td>{_status_chip(str(item.get("status")))}</td>'
        f'<td class="num">{n(item.get("consecutive_failures"))}'
        + (f'<span class="muted small"> 自 {esc(str(item.get("last_failure_at"))[:16])}</span>'
           if item.get("last_failure_at") and int(item.get("consecutive_failures") or 0) else "")
        + f'</td>'
        f'<td class="num">{esc(str(item.get("hours_since_success") or "—")[:6])}</td>'
        f'<td>{esc(str(item.get("last_success") or "从未成功")[:19])}</td>'
        + _watermark_cell(item)
        + f'<td class="muted small">{esc(str(item.get("reason") or "")[:70])}</td></tr>'
        for item in health_rows)
    # The banner is the whole point: a frozen graph that looks alive is the failure mode here.
    if health.get("stale"):
        banner = (f'<div class="gap" style="border-color:var(--bad)">'
                  f'<b>图谱数据已停止更新：最新观测在 {esc(str(health.get("stale_hours")))} 小时前。</b>'
                  f'科技地图与实时雷达展示的是历史快照，不是当前状态。'
                  f'下面「雷达源」一栏列出了每个源最后成功的时间与失败原因。</div>')
    elif health.get("available"):
        banner = ""
    else:
        banner = ('<div class="gap"><b>读不到雷达源状态。</b>'
                  f'台账打不开（{esc(str(health.get("reason") or "原因未记录"))}），'
                  f'所以无法判断图谱数据是否新鲜。</div>')
    health_block = (f'<div class="card"><table><thead><tr><th>源</th><th>状态</th>'
                    f'<th>连续失败</th><th>距上次成功(h)</th><th>最后成功</th><th>数据到</th><th>原因</th>'
                    f'</tr></thead><tbody>{health_table}</tbody></table></div>'
                    if health_table else gap_note("radar_health_unavailable"))

    source_rows = "".join(
        f'<tr><td>{esc(item.get("display_name") or item.get("source_id"))}</td>'
        f'<td>{esc(item.get("kind") or "")}</td>'
        f'<td class="num">{esc(item.get("cadence_hours") or "—")}</td>'
        f'<td>{"启用" if item.get("enabled") else "停用"}</td>'
        f'<td class="muted small">{esc(item.get("licence") or "—")}</td></tr>'
        for item in sources)
    # An empty table with headers and no rows looks like a rendering bug; say why instead - but only
    # when the health table above has not already listed the real sources.
    sources_block = (f'<div class="card"><table><thead><tr><th>来源</th><th>类型</th><th>周期(h)</th>'
                     f'<th>状态</th><th>许可</th></tr></thead><tbody>{source_rows}</tbody>'
                     f'</table></div>' if source_rows else
                     ("" if health_rows else gap_note("radar_sources_absent")))

    stamp = (f'<p class="small muted">库存计数更新于 {esc(str(data.get("updated_at"))[:16])}，'
             f'与首页同一份，所以两边不会互相矛盾。</p>'
             if data.get("updated_at") else
             '<p class="small muted">库存计数还没有物化，本次为实时统计。</p>')

    body = f"""
<h1>数据覆盖</h1>
<p class="lede">这个工具知道什么、不知道什么，以及每个"不知道"的原因。下面的数字读自库，
与首页用的是同一份物化计数。</p>
{banner}
{stamp}
{night_block}
<h2>各数据集规模</h2>
<div class="card"><table><thead><tr><th>数据集</th><th>规模</th><th>说明</th></tr></thead>
<tbody>{dataset_rows}</tbody></table></div>
<h2>各数据集覆盖到的范围</h2>
<p class="muted small">规模大不等于覆盖全——34 万条失效记录只覆盖了部分产品码，
这个区别在结果页会以不同的缺口字样体现。</p>
<div class="card"><table><thead><tr><th>维度</th><th>数量</th><th>说明</th></tr></thead>
<tbody>{shape_rows}</tbody></table></div>
<h2>还没做到的</h2>
<div class="card"><ul class="small">{gap_items}</ul></div>
{tunnel_block}
<h2>雷达源</h2>
<p class="muted small">每个源的最近一次成功、连续失败次数、<b>数据抓到哪一天</b>与失败原因。状态读自台账，不推断。
连续失败次数只增不减，直到有一次成功才归零——它说明"这个源最近不好用"，不等于"现在坏了"；
判断新鲜度看「数据到」那一列。</p>
{health_block}
{sources_block}
<h2>明确不做的事</h2>
<div class="card"><p class="muted small">
· 不把"没有数据"写成"没有"——两者在结果页用不同的字样，且都带原因。<br>
· 不猜测匹配：型号精确匹配与品牌族匹配分开标注。<br>
· 不冒充集团证据：子公司/集团的匹配会注明"集团级"。<br>
· 不编造规格：物理上不可能的数值直接丢弃并计数。<br>
· 不把"我们没抓"写成"它没有"：专利与失效都区分这两种情况。<br>
· 对不可能靠重试成功的源不再反复打：openalex 需要凭据（401）、draeger 拒绝自动访问（403），
两者都已注明不可重试，调度器改为最多每 24 小时试一次，而不是每 5 分钟写一条失败。
</p></div>
"""
    return layout(title="数据覆盖 · MedRadar", body=body, active="sources")


def map_page(*, payload: Mapping[str, Any]) -> str:
    """The technology map, browsable: which company is working on which topic, and what says so.

    The API answers this as JSON with per-evidence nodes; a reader needs the opposite order - the
    topic first, then who is in it, then the citation they can open. Confirmation level is printed
    next to every claim because TOPIC_RELATED is a weaker statement than CONFIRMED and the two must
    not look alike.
    """
    topics = payload.get("topics") or []
    counts = payload.get("counts") or {}
    cards = []
    for topic in topics:
        companies = topic.get("companies") or []
        rows = []
        for company in companies:
            evidence = company.get("evidence") or []
            cites = "".join(
                f'<li><a href="{esc(item.get("source_url") or "#")}" rel="noopener" target="_blank">'
                f'{esc((item.get("title") or "（无标题）")[:96])}</a>'
                f'<span class="muted small"> · {esc(item.get("source") or "")}'
                f' · {esc(item.get("confirmation") or "")}</span></li>'
                for item in evidence[:2])
            rows.append(
                f'<tr><td class="nw"><a href="/device?query={esc(company.get("display_name") or "")}">'
                f'{esc(company.get("label_zh") or company.get("display_name"))}</a></td>'
                f'<td class="num">{n(company.get("evidence_total"))}</td>'
                f'<td><ul style="margin:0;padding-left:18px">{cites or "<li class=muted>暂无公开证据</li>"}</ul></td></tr>')
        codes = "".join(_chip(f"产品码 {c}") for c in (topic.get("product_codes") or [])[:6])
        cards.append(f"""
<div class="card">
  <h4><a href="/topic?id={esc(topic.get("topic_id") or "")}">{esc(topic.get("label_zh") or topic.get("label_en"))}</a>
      <span class="muted small">· {esc(topic.get("label_en") or "")}</span></h4>
  <p class="muted small">{esc(topic.get("description") or "")}</p>
  <div class="chips">{codes}</div>
  <table style="margin-top:10px"><thead><tr><th>公司</th><th>证据</th><th>最近的公开出处</th></tr></thead>
  <tbody>{''.join(rows) or '<tr><td colspan=3 class=muted>这个主题下还没有证据</td></tr>'}</tbody></table>
</div>""")

    body = f"""
<h1>科技地图：谁在做哪一块</h1>
<p class="lede">{n(len(topics))} 个技术主题 · {n(counts.get("nodes"))} 个图谱节点 ·
{n(counts.get("edges"))} 条关联。每一条"某公司在做某主题"都挂着它的出处，
可以点开核对。标着 <code>TOPIC_RELATED</code> 的是按文本规则关联的，比
<code>CONFIRMED</code> 弱——不要把两者当成一件事。</p>
<p class="small muted">时间语义：{esc((payload.get("time_semantics") or {}).get("statement_zh") or "")}</p>
{''.join(cards) or gap_note("no_topic_evidence")}
"""
    return layout(title="科技地图 · MedRadar", body=body, active="map")


def topic_page(*, payload: Mapping[str, Any], topic_id: str,
               data: Mapping[str, Any] | None = None) -> str:
    """One technology topic, with every company in it and the citations behind each claim.

    The topic page answered "who is in this space" and stopped there. A reader looking at a technology
    direction also wants to know what is being published about it, so the page now carries the papers
    whose indexed terms match the topic's own words - a lead, labelled as one.
    """
    data = data or {}
    topics = payload.get("topics") or []
    topic = next((t for t in topics if str(t.get("topic_id")) == topic_id), None)
    if topic is None:
        return layout(
            title="科技地图 · MedRadar",
            body=(f'<h1>没有这个技术主题：{esc(topic_id)}</h1>'
                  + gap_note("no_topic_evidence")
                  + '<p class="small muted"><a href="/map">← 回到科技地图</a></p>'),
            active="map")

    blocks = []
    for company in (topic.get("companies") or []):
        evidence = company.get("evidence") or []
        items = "".join(
            f'<li><a href="{esc(item.get("source_url") or "#")}" rel="noopener" target="_blank">'
            f'{esc((item.get("title") or "（无标题）")[:110])}</a>'
            f'<div class="muted small">{esc(item.get("source") or "")}'
            f' · {esc(item.get("confirmation") or "")}'
            f' · {esc(item.get("record_type") or "")}'
            f'{(" · " + esc(str(item.get("valid_from"))[:10])) if item.get("valid_from") else ""}'
            f"</div></li>"
            for item in evidence)
        total = company.get("evidence_total")
        shown = len(evidence)
        note = ("" if total is None or shown >= int(total)
                else f'<p class="muted small">显示 {shown} / 共 {n(total)} 条，'
                     f'其余在实时雷达里按需展开。</p>')
        name = company.get("display_name") or ""
        blocks.append(f"""
<div class="card">
  <h4><a href="/company?q={esc(name)}">{esc(company.get("label_zh") or name)}</a>
      <span class="muted small">· 共 {n(total)} 条证据</span></h4>
  <ul style="margin:8px 0 0;padding-left:18px">{items or "<li class=muted>暂无公开证据</li>"}</ul>
  {note}
</div>""")

    papers = data.get("papers") or []
    terms = data.get("terms") or []
    if papers:
        rows = "".join(
            f'<tr><td class="muted small">{esc(str(item.get("published_at") or ""))}</td>'
            f'<td><a href="/paper?id={esc(str(item.get("paper_id")))}">'
            f'{esc(str(item.get("title") or "")[:100])}</a>'
            f'<div class="muted small">{esc(str(item.get("journal") or "")[:70])}</div></td></tr>'
            for item in papers)
        literature_block = (
            '<h2>这个方向最近发表的</h2>'
            f'<p class="muted small">用这个主题自己的词（{esc("、".join(terms[:6]))}）'
            f'在已归档论文里检索，命中的最新 {n(len(papers))} 篇。'
            '命中只说明论文里出现了这些词，<b>不等于</b>这篇论文研究的是这个主题。</p>'
            f'<div class="card"><table><thead><tr><th>发表日期</th><th>标题</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>')
    elif terms:
        # Terms existed but nothing matched. Measured on the live map: 3 of 16 topics have hits, so this
        # is the common case and it has to explain itself - a missing block is indistinguishable from a
        # feature that was never built.
        literature_block = (
            '<h2>这个方向最近发表的</h2>'
            f'<p class="muted small">用这个主题自己的词（{esc("、".join(terms[:6]))}）检索已归档论文，'
            '没有命中。语料是器械注册相关的开放全文，监护与软件类主题覆盖得少；'
            '<b>没有命中不等于没有研究</b>。</p>')
    elif "terms" in data:
        literature_block = (
            '<h2>这个方向最近发表的</h2>'
            '<p class="muted small">这个主题的词在论文语料里都太常见（属于通用词），'
            '无法用它们定位具体论文。</p>')
    else:
        # Nothing was computed. Saying "the words are too common" here would be an invented reason -
        # the reader would be told why, and the why would be false.
        literature_block = ""

    body = f"""
<p class="small muted"><a href="/map">← 科技地图</a></p>
<h1>{esc(topic.get("label_zh") or topic.get("label_en"))}</h1>
<p class="lede">{esc(topic.get("label_en") or "")}</p>
<p class="muted">{esc(topic.get("description") or "")}</p>
<div class="chips">{''.join(_chip(f"产品码 {c}") for c in (topic.get("product_codes") or [])[:8])}</div>
<h2>谁在这块</h2>
<p class="muted small">每条都挂着公开出处，可直接点开核对。
<code>TOPIC_RELATED</code> 是按文本规则关联的，比 <code>CONFIRMED</code> 弱。</p>
{''.join(blocks) or gap_note("no_topic_evidence")}
{literature_block}
"""
    return layout(title=f"{topic.get('label_zh') or topic_id} · MedRadar", body=body, active="map")


def company_page(*, data: Mapping[str, Any]) -> str:
    """One company: how much it has registered, filed, failed, is trialling, owns, and publishes."""
    name = data.get("company_name") or data.get("query") or ""
    if not data.get("found"):
        # `name` is the Chinese query when nothing matched, so the hint speaks about that string.
        missing = str(data.get("query") or name)
        return layout(
            title="没有这家公司 · MedRadar",
            body=(f'<h1>没有找到「{esc(missing)}」</h1>'
                  '<p class="lede">在设备注册表里按公司名匹配（先精确、后包含）。</p>'
                  + (_cjk_hint(missing, action="/company") if _looks_chinese(missing) else "")
                  + gap_note("company_not_in_register")
                  + '<p class="small muted"><a href="/">← 回到查询</a></p>'),
            active="company")

    codes = data.get("product_codes") or []

    def _card(value: Any, label: str, note: str = "") -> str:
        qualifier = f'<i>{esc(note)}</i>' if note and n(value) != "0" else ""
        return (f'<div class="stat"><b>{n(value)}</b><span>{esc(label)}</span>'
                f'{qualifier}</div>')

    # Same rule as the dossier: a company page whose top row says 200 trials must say 集团级 there,
    # not only in the section three screens down.
    stats = "".join([
        _card(data.get("devices"), "注册设备"),
        _card(data.get("clearances"), "批文"),
        _card(data.get("failures"), "失效记录"),
        _card(data.get("trials"), "在研试验",
              "集团级" if data.get("trial_method") == "group" else ""),
        _card(data.get("patents"), "专利",
              "含其他写法" if data.get("patent_variants") else ""),
        _card(data.get("papers"), "相关论文", "公司级" if data.get("papers") else ""),
    ])

    brands = data.get("brands") or []
    brand_rows = "".join(
        f'<tr><td><a href="/device?query={esc(item["brand"])}">{esc(item["brand"])}</a></td>'
        f'<td class="num">{n(item["devices"])}</td></tr>'
        for item in brands)
    brand_html = (f'<div class="card"><table><thead><tr><th>品牌</th><th>设备数</th></tr></thead>'
                  f'<tbody>{brand_rows}</tbody></table></div>'
                  if brands else gap_note("no_brand_for_this_company"))

    topics = data.get("topics") or []
    topic_html = "".join(
        f'<div class="card"><h4><a href="/topic?id={esc(t["topic_id"])}">'
        f'{esc(t.get("label_zh") or t.get("topic_id"))}</a>'
        f' <span class="muted small">· 本公司在其中有 {n(t.get("evidence_total"))} 条证据</span></h4>'
        f'<p class="muted small">{esc(t.get("description") or "")}</p></div>'
        for t in topics) or gap_note(data.get("topic_gap") or "no_topic_evidence")

    specialties = data.get("specialties") or []
    examples = data.get("specialty_examples") or {}
    area_rows = "".join(
        f'<tr><td>{esc(item["specialty"])}</td>'
        f'<td class="num">{n(item["codes"])}</td>'
        f'<td class="muted small">{esc("；".join(examples.get(item["specialty"], []))[:110])}</td></tr>'
        for item in specialties)
    used, total = data.get("area_codes_used"), data.get("area_codes_total")
    area_note = ""
    if used is not None and total and used < total:
        # Say which slice the percentages are over, rather than implying the full set.
        area_note = (f'<p class="muted small">按该公司最常见的 {n(used)} 个产品码统计'
                     f'（共 {n(total)} 个），所以这是分布，不是完整清单。</p>')
    area_html = ((f'<div class="card">{area_note}<table><thead><tr><th>技术领域</th>'
                  f'<th>产品码数</th><th>代表性分类</th></tr></thead><tbody>{area_rows}</tbody>'
                  f'</table></div>') if area_rows
                 else gap_note(data.get("area_gap") or "no_classified_product_code"))

    trial_rows = "".join(
        f'<tr><td>{esc((item.get("start_date") or "—")[:10])}</td>'
        f'<td>{esc(item.get("nct_id") or "")}</td>'
        f'<td>{esc((item.get("title") or "")[:80])}</td>'
        f'<td class="num">{n(item.get("enrollment") or 0)}</td></tr>'
        for item in (data.get("trial_recent") or [])[:8])
    trial_note = ""
    if trial_rows and data.get("trial_method") == "group":
        trial_note = (f'<p class="muted small">按集团名「{esc(data.get("trial_sponsor") or "")}」'
                      f'匹配，不是这个法人实体的精确统计。</p>')
    trial_html = (f'<div class="card">{trial_note}<table><thead><tr><th>起始</th><th>NCT</th>'
                  f'<th>标题</th><th>入组</th></tr></thead><tbody>{trial_rows}</tbody></table></div>'
                  if trial_rows else gap_note(data.get("trial_gap") or "no_trial_for_this_sponsor"))

    paper_rows = "".join(
        f'<tr><td>{esc(str(item.get("year") or "—")[:10])}</td>'
        f'<td>{esc(item.get("paper_id") or "")}</td>'
        f'<td>{esc((item.get("title") or "")[:90])}</td></tr>'
        for item in (data.get("paper_recent") or [])[:8])
    paper_note = ""
    if paper_rows:
        terms = "、".join(esc(t) for t in (data.get("paper_terms") or [])[:4])
        paper_note = (f'<p class="muted small">公司级匹配：论文里出现「{terms}」，'
                      f'不等于研究这台设备。</p>')
    paper_html = (f'<div class="card">{paper_note}<table><thead><tr><th>年份</th><th>编号</th>'
                  f'<th>标题</th></tr></thead><tbody>{paper_rows}</tbody></table></div>'
                  if paper_rows else gap_note(data.get("paper_gap") or "no_paper_mentions_this_device"))

    patent_rows = "".join(
        f'<tr><td>{esc((item.get("patent_date") or "—")[:10])}</td>'
        f'<td>{esc(item.get("patent_id") or "")}</td>'
        f'<td>{esc((item.get("title") or "")[:90])}</td></tr>'
        for item in (data.get("patent_recent") or [])[:8])
    patent_note = ""
    if patent_rows and data.get("patent_variants"):
        # The same applicant is written several ways in the documents; say which spellings were merged.
        merged = "、".join(esc(v) for v in (data["patent_variants"] or [])[:4])
        patent_note = (f'<p class="muted small">已合并同一申请人的其他写法：{merged}</p>')
    if patent_rows and data.get("patent_searched_for"):
        patent_note += (f'<p class="muted small">另有 {n(data["patent_searched_for"])} 件是按这个名字'
                        f'搜到、但申请人字段并非本公司的记录，不计入。</p>')
    patent_html = (f'<div class="card">{patent_note}<table><thead><tr><th>公开日</th><th>公开号</th>'
                   f'<th>标题</th></tr></thead><tbody>{patent_rows}</tbody></table></div>'
                   if patent_rows else gap_note(data.get("patent_gap") or "patent_bulk_tables_absent"))

    from .watermark import utc_today

    # What the company's brands have reported. Placed after the scale block and before the fields,
    # because an engineer deciding whether to trust a supplier wants this next to their volume.
    brand_shape = data.get("brand_failures") or {}
    if int(brand_shape.get("total") or 0):
        events = brand_shape.get("by_event") or {}
        order = [("Malfunction", "故障"), ("Injury", "伤害"), ("Death", "死亡")]
        bits = " · ".join(f'{label} {n(int(events.get(k) or 0))}'
                          for k, label in order if events.get(k))
        other = int(brand_shape.get("total") or 0) - sum(int(events.get(k) or 0) for k, _ in order)
        if other > 0:
            bits += f' · 其他/未标注 {n(other)}'
        rows = "".join(
            f'<tr><td>{esc(str(item["brand"]))}</td>'
            f'<td class="num">{n(item["reports"])}</td></tr>'
            for item in (brand_shape.get("by_brand") or []))
        brand_failures_block = (
            '<h2>它的品牌报过哪些失效</h2>'
            f'<p class="muted small">用注册表里这家公司的全部 {n(brand_shape.get("brands"))} 个'
            f'品牌名称去匹配 FDA MAUDE，共 {n(brand_shape.get("total"))} 条 —— {bits}。'
            '<b>这是名称匹配，不是法定主体归属</b>：MAUDE 的品牌字段是上报人手写的自由文本，'
            '同一集团的不同法人、同一品牌的不同型号都会混在一起；'
            '而且上报是自愿的，数字大小取决于有多少人在报，不是故障率。要确认某台设备，'
            '看设备档案里按产品码统计的那一份。</p>'
            f'<div class="card"><table><thead><tr><th>品牌</th><th>报告数</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>')
    elif int(brand_shape.get("brands") or 0):
        # Nothing matched, and that is not the same as "nothing failed". Measured on Stryker GmbH: 59
        # brand names, 18,269 devices, zero matches - the reports for Stryker products sit under the
        # brand strings of its other legal entities, which this page does not claim.
        brand_failures_block = (
            '<h2>它的品牌报过哪些失效</h2>'
            f'<p class="muted small">用注册表里这家公司法人的 {n(brand_shape.get("brands"))} 个品牌'
            '名称去匹配 FDA MAUDE，<b>一条也没有匹配到</b>。这不等于没有失效：MAUDE 的品牌字段记的是'
            '被匹配上的那台设备的品牌，同一集团的其他法人、其他产品线会记在别的品牌名下。'
            '要按产品码看这类报告，去对应的技术领域页。</p>')
    else:
        brand_failures_block = ""

    # Registered devices by year, above the field block: it is the company's own record, not a lead.
    #
    # Drawn as a table, not bars. Measured on Medtronic: one backfill year holds 20,440 devices and the
    # recent years hold 803 / 1,904 / 881, so a bar chart scaled to the peak renders every interesting
    # year as a two-pixel stub. Reading the numbers beats reading a shape that cannot show them.
    years = data.get("device_years") or []
    this_year = str(utc_today())[:4]
    total_years = sum(int(item.get("n") or 0) for item in years)
    if years and total_years:
        peak = max(int(item.get("n") or 0) for item in years) or 1
        peak_year = next(str(item.get("year")) for item in years
                         if int(item.get("n") or 0) == peak)
        rows = "".join(
            f'<tr><td>{esc(str(item.get("year")))}'
            f'{"<span class=\"muted small\"> · 当年未满</span>" if str(item.get("year")) == this_year else ""}'
            f'</td><td class="num">{n(item.get("n"))}</td>'
            f'<td class="num muted small">{100.0 * int(item.get("n") or 0) / total_years:.1f}%</td></tr>'
            for item in years)
        years_block = (
            '<h2>注册登记按年</h2>'
            f'<p class="muted small">这家公司的设备注册记录按 UDI 发布日期统计，{n(len(years))} 年，'
            f'合计 {n(total_years)} 台，最多一年是 {esc(peak_year)} 的 {n(peak)} 台。'
            '<b>这是 GUDID 的收录时间，不是研发时间</b>——登记可以晚于上市，早年设备也可能被集中补录；'
            '当前年份未满。因此这张表看的是记录节奏，不能当作研发投入的曲线。</p>'
            '<div class="card"><table><thead><tr><th>年份</th><th>注册台数</th><th>占比</th></tr>'
            f'</thead><tbody>{rows}</tbody></table></div>')
    else:
        years_block = ""

    primary = str(data.get("primary_specialty") or "")
    topics = data.get("field_topics") or []
    field_recent = data.get("field_recent") or []
    if primary and (topics or field_recent):
        chips = "".join(
            f'<span class="chip">{esc(str(item.get("term")))}'
            f'<span class="muted small"> {n(item.get("count"))}</span></span>'
            for item in topics)
        rows = "".join(
            f'<tr><td class="muted small">{esc(str(item.get("published_at") or ""))}</td>'
            f'<td><a href="/paper?id={esc(str(item.get("paper_id")))}">'
            f'{esc(str(item.get("title") or "")[:96])}</a></td></tr>'
            for item in field_recent)
        field_block = (
            '<h2>2c · 这些产品所在的领域在谈什么</h2>'
            f'<p class="muted small">它的产品码里 <b>{esc(primary)}</b> 最多'
            f'（{n(data.get("primary_specialty_count"))} 个）。下面是该领域已归档论文的词频与'
            f'最新几篇（<a href="/area?name={esc(primary)}">进该领域</a>）。'
            '这是"论文里出现的词"，不是我们的技术判断。</p>'
            + (f'<div class="chips">{chips}</div>' if chips else '')
            + (f'<div class="card" style="margin-top:10px"><table><thead><tr><th>发表日期</th>'
               f'<th>标题</th></tr></thead><tbody>{rows}</tbody></table></div>'
               if rows else gap_note("no_papers_for_this_specialty")))
    else:
        field_block = ""

    body = f"""
<p class="small muted"><a href="/">← 重新查询</a></p>
<h1>{esc(name)}</h1><p class="lede">{esc(data.get("matched_by") or "")} · DUNS {esc(data.get("labeler_duns") or "—")}
 · <a href="/compare?q={esc(name)}">与其他公司对比</a></p>
<p class="small muted">导出：<a href="/download?kind=company&format=md&q={esc(name)}">Markdown</a>
 · <a href="/download?kind=company&format=csv&q={esc(name)}">CSV</a>
 · <a href="/download?kind=company&format=json&q={esc(name)}">JSON</a></p>
<div class="grid">{stats}</div>

<h2>1 · 它注册了哪些器械</h2><p class="muted small">来源：FDA UDI 设备注册表。点击品牌进入设备档案。</p>
{brand_html}
<p class="muted small">产品码（{n(len(codes))} 个，前 20）：
{esc("、".join(codes[:20]) or "—")}</p>

<h2>2 · 它在哪些技术方向上有公开证据</h2>
<p class="muted small">来自科技地图：每个方向一条，点进去看具体出处。</p>
{topic_html}

{brand_failures_block}
{years_block}
<h2>2b · 它在哪些技术领域注册了产品</h2>
<p class="muted small">按 FDA 产品码分类统计——<b>这是"注册了什么"，不是"发表了什么"</b>，
和上面那段（科技地图）回答的是不同的问题，不能混用。</p>
{area_html}

{field_block}
<h2>3 · 在研试验</h2>
{trial_html}

<h2>4 · 相关论文</h2>
{paper_html}

<h2>5 · 专利</h2>
{patent_html}
"""
    return layout(title=f"{name} · MedRadar", body=body, active="company")


def _company_data(store: Any, query: str, *, snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Everything the company page shows, in one place, with each absence named."""
    from .papers_index import papers_for_tokens, tokens as tokenise
    from .patents_bulk import patents_for_assignee
    from .trials import trials_for_sponsor

    from .watermark import utc_today

    out: dict[str, Any] = {"query": query, "found": False}
    row = None
    try:
        row = store.conn.execute(
            "SELECT labeler_duns, company_name, device_count FROM udi_company "
            "WHERE company_name = ? COLLATE NOCASE ORDER BY device_count DESC LIMIT 1",
            (query,)).fetchone()
        matched_by = "公司名精确匹配"
        if row is None:
            row = store.conn.execute(
                "SELECT labeler_duns, company_name, device_count FROM udi_company "
                "WHERE company_name LIKE ? ORDER BY device_count DESC LIMIT 1",
                (f"%{query}%",)).fetchone()
            matched_by = "公司名包含匹配"
    except Exception:  # noqa: BLE001
        row = None
    if row is None:
        return out

    duns, name, devices = str(row[0] or ""), str(row[1] or ""), int(row[2] or 0)
    out.update({"found": True, "labeler_duns": duns, "company_name": name,
                "devices": devices, "matched_by": matched_by})

    def scalar(sql: str, args: Sequence[Any]) -> int:
        try:
            value = store.conn.execute(sql, args).fetchone()[0]
            return int(value) if value is not None else 0
        except Exception:  # noqa: BLE001
            return 0

    out["clearances"] = scalar(
        "SELECT COUNT(DISTINCT submission_number) FROM udi_premarket WHERE labeler_duns = ?",
        (duns,))
    # Registered devices by year. Solid attribution (labeler DUNS) and large numbers, unlike papers,
    # which we can only tie to a company by brand-name mention. Measured on Medtronic: 45,433 devices
    # across 2019-2026 with a 7,554 peak in 2022 - a shape worth showing and worth bounding.
    try:
        # Twelve range counts instead of one GROUP BY substr(...). Measured on MEDLINE INDUSTRIES with
        # 252,243 devices: 218 ms for the GROUP BY (a temp B-tree over every row), 169 ms even with the
        # composite index, and about 60 ms for twelve index range reads, because each one is a seek and a
        # sequential count on idx_udi_duns_pub.
        #
        # The range bounds are half-open and cover the whole year, so nothing is counted twice or lost at
        # a boundary; an empty year is recorded as zero rather than omitted.
        end_year = int(str(utc_today())[:4])
        years_series: list[dict[str, Any]] = []
        for year in range(end_year - 11, end_year + 1):
            try:
                count = int(store.conn.execute(
                    "SELECT COUNT(*) FROM udi_device WHERE labeler_duns = ?"
                    " AND publish_date >= ? AND publish_date < ?",
                    (duns, f"{year}-01-01", f"{year + 1}-01-01")).fetchone()[0] or 0)
            except Exception:  # noqa: BLE001 - a broken count is a zero, not a failed page
                count = 0
            years_series.append({"year": str(year), "n": count})
        # Keep only years that actually have records, oldest first, so the table matches what the
        # company holds instead of padding a decade of zeros for a young labeler.
        out["device_years"] = [item for item in years_series if item["n"]]
    except Exception:  # noqa: BLE001 - no register is a stated gap
        out["device_years"] = []
    try:
        # The list is capped for display, and the cap is recorded rather than hidden: reporting
        # "共 200 个产品码" for a labeler that has 500 is a completeness claim the data does not
        # support. `product_code_total` is the true count; the cap only shortens the list.
        code_rows = [str(r[0]) for r in store.conn.execute(
            "SELECT DISTINCT j.value FROM udi_device d, json_each(d.product_codes) j "
            "WHERE d.labeler_duns = ? LIMIT 201", (duns,))]
        capped = len(code_rows) > 200
        codes = code_rows[:200]
        if capped:
            try:
                out["product_code_total"] = int(store.conn.execute(
                    "SELECT COUNT(DISTINCT j.value) FROM udi_device d, json_each(d.product_codes) j "
                    "WHERE d.labeler_duns = ?", (duns,)).fetchone()[0] or 0)
            except Exception:  # noqa: BLE001 - the cap note falls back to "more than 200"
                out["product_code_total"] = None
        else:
            out["product_code_total"] = len(codes)
    except Exception:  # noqa: BLE001 - a store without JSON1 still renders the rest
        codes = []
        out["product_code_total"] = None
    out["product_codes"] = codes
    out["product_codes_capped"] = bool(codes) and out.get("product_code_total") not in (None, len(codes))
    if codes:
        placeholders = ",".join("?" for _ in codes)
        out["failures"] = scalar(
            f"SELECT COUNT(*) FROM maude_failure_index WHERE product_code IN ({placeholders})",
            codes)
    else:
        out["failures"] = 0
    try:
        out["brands"] = [
            {"brand": str(r[0]), "devices": int(r[1])}
            for r in store.conn.execute(
                "SELECT brand_name, COUNT(*) FROM udi_device WHERE labeler_duns = ? "
                "AND brand_name IS NOT NULL AND brand_name <> '' "
                "GROUP BY brand_name ORDER BY 2 DESC LIMIT 12", (duns,))
        ]
    except Exception:  # noqa: BLE001
        out["brands"] = []

    # What the brands we just listed have reported to MAUDE. Name matching, not attribution: MAUDE brand
    # strings are free text typed by reporters, so a match is a lead to check against the device's own
    # record. Measured on MEDLINE INDUSTRIES: 326 reports across its 12 listed brands in 1 ms, and one of
    # the matches was NAMIC - a brand it owns, next to the ones a reader would expect, which is exactly
    # why the label has to say what the match is.
    # Both sides have to be normalised the same way. Measured on MEDTRONIC SOFAMOR DANEK: its brands are
    # stored as "CD HORIZON® Spinal System" and "CD Horizon™ ModuLeX™ Spinal System", while MAUDE holds a
    # normalised key - so a plain IN(...) match returned 0 for a company with 45,433 devices. The registry
    # side is normalised with the same function the failure index uses on its side.
    try:
        # normalise_brand, not normalise_model: the index keeps word boundaries (MAUDE holds
        # "CD HORIZON") while a model key drops every separator. Using the model function matched nothing
        # for a company with 45,433 devices.
        #
        # Every brand name the labeler uses, not the twelve on display. Measured on MEDTRONIC SOFAMOR
        # DANEK: 416 distinct names, and matching all of them is 2 ms - while the twelve most common
        # missed whole families, because a brand can appear on one device and still carry reports.
        from .failure_index import normalise_brand

        raw_brands = [str(row[0]) for row in store.conn.execute(
            "SELECT DISTINCT brand_name FROM udi_device WHERE labeler_duns = ?"
            " AND brand_name IS NOT NULL AND brand_name <> ''", (duns,))]
        brand_names = sorted({normalise_brand(name) for name in raw_brands})
        # A one-word placeholder is not a name anyone can match on; "N/A" is literally stored as a brand
        # by some labelers and would sweep in unrelated reports.
        brand_names = [name for name in brand_names
                       if len(name) >= 6 and name not in ("NA", "NONE", "UNKNOWN", "NOTAPPLICABLE")]
        out["brand_names_total"] = len(brand_names)
        brand_names = brand_names[:2000]
    except Exception:  # noqa: BLE001 - without the normaliser, match on the raw names
        brand_names = [str(item["brand"]) for item in (out.get("brands") or [])]
        out["brand_names_total"] = len(brand_names)
    brand_shape: dict[str, Any] = {"brands": int(out.get("brand_names_total") or len(brand_names)),
                                   "total": 0, "by_brand": [], "by_event": {}}
    if brand_names:
        marks = ",".join("?" for _ in brand_names)
        try:
            brand_shape["total"] = scalar(
                f"SELECT COUNT(*) FROM maude_failure_index WHERE brand_norm IN ({marks})",
                brand_names)
            brand_shape["by_brand"] = [
                {"brand": str(r[0]), "reports": int(r[1] or 0)}
                for r in store.conn.execute(
                    f"SELECT brand_norm, COUNT(*) AS n FROM maude_failure_index"
                    f" WHERE brand_norm IN ({marks}) GROUP BY 1 ORDER BY n DESC LIMIT 6",
                    brand_names)]
            brand_shape["by_event"] = {
                str(r[0] or "未标注"): int(r[1] or 0) for r in store.conn.execute(
                    f"SELECT event_type, COUNT(*) FROM maude_failure_index"
                    f" WHERE brand_norm IN ({marks}) GROUP BY 1", brand_names)}
        except Exception:  # noqa: BLE001 - no failure index is a stated gap
            brand_shape = {"brands": len(brand_names), "total": 0, "by_brand": [], "by_event": {}}
    out["brand_failures"] = brand_shape

    # The registry holds the legal entity ("MEDTRONIC SOFAMOR DANEK, INC."); registry sponsors are
    # filed under the group ("Medtronic"). Try the full name, then the first distinctive token, and
    # label the weaker match rather than reporting zero trials for a company that runs thousands.
    trials = trials_for_sponsor(store, name, limit=8)
    trial_method = "exact"
    if not int(trials.get("trials") or 0):
        first = name.replace(",", " ").split()
        candidate = first[0] if first and len(first[0]) >= 5 else ""
        if candidate:
            trials = trials_for_sponsor(store, candidate, limit=8)
            trial_method = "group"
    out["trials"] = int(trials.get("trials") or 0)
    out["trial_recent"] = trials.get("recent") or []
    out["trial_method"] = trial_method
    out["trial_sponsor"] = trials.get("organization") or trials.get("sponsor") or name
    out["trial_gap"] = None if out["trials"] else "no_trial_for_this_sponsor"

    patents = patents_for_assignee(store, name, limit=8, include_variants=True)
    out["patents"] = int(patents.get("patents") or 0)
    out["patent_recent"] = patents.get("recent") or []
    out["patent_variants"] = patents.get("variants") or []
    out["patent_searched_for"] = int(patents.get("searched_for") or 0)
    out["patent_gap"] = None if out["patents"] else (
        "patent_only_searched_not_recorded" if out["patent_searched_for"]
        else "patent_bulk_tables_absent")

    # A company name is *supposed* to be common: "medtronic" occurs in 117 of 2,552 papers, which
    # the device-level 2% cut-off would call generic. At company level that frequency is the signal,
    # so the allowance is raised and the weaker claim is labelled in the page.
    papers = papers_for_tokens(store, tokenise(name), max_df_ratio=0.10)
    out["papers"] = int(papers.get("papers") or 0)
    out["paper_recent"] = papers.get("recent") or []
    out["paper_terms"] = papers.get("terms") or []
    out["paper_gap"] = (None if out["papers"]
                        else ("paper_index_absent" if not papers.get("available")
                              else "no_paper_mentions_this_device"))

    topics = []
    for topic in snapshot.get("topics") or []:
        for company in topic.get("companies") or []:
            if str(company.get("organization_id") or "") and (
                    str(company.get("display_name") or "").lower() == name.lower()
                    or str(company.get("organization_id") or "").lower() in name.lower()
                    or name.lower().startswith(str(company.get("display_name") or "###").lower())):
                topics.append({"topic_id": topic.get("topic_id"),
                               "label_zh": topic.get("label_zh"),
                               "description": topic.get("description"),
                               "evidence_total": company.get("evidence_total")})
                break
    out["topics"] = topics
    # "This company is not in the graph" and "the graph has no evidence" are different statements.
    out["topic_gap"] = None if topics else (
        "company_not_in_technology_map" if (snapshot.get("topics")) else "no_topic_evidence")

    # Technology areas from the FDA product-code classification: this answers for every labeler in
    # the register, not only the three the radar graph tracks. It is a different claim from the map -
    # the map is what a company published about, this is what it registered.
    from .product_codes import classes_for_codes, specialty_counts

    code_cap = 400
    codes_for_areas = codes[:code_cap]
    out["area_codes_used"] = len(codes_for_areas)
    # The true number of codes, not the length of the display list: a company with 500 codes
    # must not be described as having 200.
    out["area_codes_total"] = out.get("product_code_total") or len(codes)
    out["specialties"] = specialty_counts(store, codes_for_areas)
    classes = classes_for_codes(store, codes_for_areas)
    examples: dict[str, list[str]] = {}
    for code in codes_for_areas:
        meta = classes.get(code)
        if not meta:
            continue
        name = str(meta.get("medical_specialty") or "").strip() or "Unclassified"
        label = str(meta.get("device_name") or "").strip()
        if label and label not in examples.setdefault(name, []):
            examples[name].append(label)
    out["specialty_examples"] = {k: v[:3] for k, v in examples.items()}
    # The field this company mostly registers in, and what that field's literature says. A reader
    # looking up a manufacturer is one hop away from "what is being published around their products",
    # which is the question this product exists for.
    try:
        # specialty_counts returns a list of {"specialty", "codes"} dicts, not a mapping - reading it as
        # a mapping raised inside the try and silently produced an empty block for every company.
        ranked = sorted((row for row in (out["specialties"] or []) if isinstance(row, dict)),
                        key=lambda row: -int(row.get("codes") or 0))
        primary, primary_codes = "", 0
        for row in ranked:
            name = str(row.get("specialty") or "")
            if name and name != "Unknown" and int(row.get("codes") or 0):
                primary, primary_codes = name, int(row.get("codes") or 0)
                break
        if primary:
            from .paper_passes import field_topics, recent_for

            out["primary_specialty"] = primary
            out["primary_specialty_count"] = primary_codes
            out["field_topics"] = field_topics(store, primary, limit=8)
            out["field_recent"] = recent_for(store, primary, limit=5)
    except Exception:  # noqa: BLE001 - no literature yet is a stated gap
        out["primary_specialty"] = ""
        out["field_topics"] = []
        out["field_recent"] = []
    from .product_codes import table_present as classification_present

    out["area_gap"] = None if out["specialties"] else (
        "product_classification_absent" if not classification_present(store)
        else "no_classified_product_code")
    return out


def compare_page(*, companies: Sequence[Mapping[str, Any]],
                 substitutions: Mapping[str, str] | None = None,
                 data_recency: Mapping[str, Mapping[str, Any]] | None = None) -> str:
    """Two to four companies side by side.

    Built on the same per-company lookups the dossier uses, not on /api/radar/compare: that endpoint
    walks the whole graph and took longer than forty seconds to answer for two companies, which is
    useless behind a page. These numbers come from the register and the indexes and answer in about
    a second for four companies.

    ``substitutions`` maps a name the reader typed to the one that was looked up; it is printed so a
    reader who typed 美敦力 knows they are looking at Medtronic and not at something else.
    """
    from .watermark import utc_today

    swapped = dict(substitutions or {})
    found = [item for item in companies if item.get("found")]
    if not found:
        return layout(
            title="公司对比 · MedRadar",
            body=('<h1>没有可比的公司</h1>'
                  + gap_note("company_not_in_register")
                  + '<p class="small muted"><a href="/">← 重新查询</a></p>'),
            active="company")

    def cell(value: Any) -> str:
        return f'<td class="num">{n(value)}</td>'

    metrics = [
        ("注册设备", "devices"), ("批文", "clearances"), ("失效记录", "failures"),
        ("在研试验", "trials"), ("专利", "patents"), ("相关论文", "papers"),
    ]
    header = "".join(
        f'<th><a href="/company?q={esc(item.get("company_name"))}">'
        f'{esc(item.get("company_name"))}</a></th>'
        for item in found)

    rows = []
    for label, key in metrics:
        values = [item.get(key) or 0 for item in found]
        top = max(values) if values and max(values) > 0 else None
        cells = "".join(
            f'<td class="num{" lead" if top is not None and value == top else ""}">{n(value)}</td>'
            for value in values)
        rows.append(f"<tr><td>{esc(label)}</td>{cells}</tr>")
    table = (f'<div class="card"><table><thead><tr><th>指标</th>{header}</tr></thead>'
             f'<tbody>{"".join(rows)}</tbody></table></div>')

    # Registrations by year, side by side: the only column here that says whether a company is moving.
    # Table, not bars - one company's backfill year (Medtronic 2015: 20,440) flattens every other bar to
    # a stub, which is exactly what the single-company block was changed away from last round.
    year_maps = [{str(item.get("year")): int(item.get("n") or 0)
                  for item in (company.get("device_years") or [])} for company in found]
    year_names = sorted({year for mapping in year_maps for year in mapping}, reverse=True)[:12]
    if year_names:
        this_year = str(utc_today())[:4]
        year_rows = []
        for year in year_names:
            values = [mapping.get(year) or 0 for mapping in year_maps]
            top = max(values) if values and max(values) > 0 else None
            cells = "".join(
                f'<td class="num{" lead" if top is not None and value == top else ""}">'
                f'{n(value) if value else "—"}</td>' for value in values)
            label = year + ("<span class=\"muted small\">·未满</span>" if year == this_year else "")
            year_rows.append(f"<tr><td>{label}</td>{cells}</tr>")
        year_table = (f'<div class="card"><table><thead><tr><th>年份</th>{header}</tr></thead>'
                      f'<tbody>{"".join(year_rows)}</tbody></table></div>'
                      '<p class="muted small">按 UDI 发布日期统计的注册台数，只列最近 12 个有记录的年份。'
                      '<b>这是 GUDID 的收录时间，不是研发时间</b>：登记可以晚于上市，早年设备也可能被'
                      '集中补录，当前年份未满。所以它说明记录节奏，不是研发投入的曲线。</p>')
    else:
        year_table = ""
    year_block = (f'<h2>注册登记按年</h2>{year_table}' if year_table else "")

    # How active the literature is in the fields each company sits in. A weighted mean over the company's
    # own product codes, so it answers "is this company's area moving", not "does this company publish".
    field_recency = data_recency if isinstance(data_recency, Mapping) else {}
    if field_recency:
        recency_rows = []
        for company in found:
            pairs = [(str(item["specialty"]), int(item["codes"]))
                     for item in (company.get("specialties") or []) if item.get("codes")]
            weighted, weight = 0.0, 0
            for name, codes in pairs:
                entry = field_recency.get(name) or {}
                if entry:
                    weighted += float(entry.get("pct") or 0) * codes
                    weight += codes
            if not weight:
                recency_rows.append(f'<tr><td>{esc(str(company.get("company_name") or ""))}</td>'
                                    f'<td class="num muted">—</td>'
                                    f'<td class="muted small">它的产品码没有落在已抓文献的领域里</td></tr>')
                continue
            mean = int(round(weighted / weight))
            top = sorted(((name, field_recency[name]) for name, _ in pairs if name in field_recency),
                         key=lambda pair: -int(pair[1].get("pct") or 0))[:3]
            detail = "；".join(f'{esc(name)} {int(entry.get("pct") or 0)}%'
                              for name, entry in top)
            recency_rows.append(f'<tr><td>{esc(str(company.get("company_name") or ""))}</td>'
                                f'<td class="num">{mean}%</td>'
                                f'<td class="muted small">{detail}</td></tr>')
        recency_block = (
            '<h2>所在领域的文献活跃度</h2>'
            '<div class="card"><table><thead><tr><th>公司</th><th>近 90 天文献占比</th>'
            '<th>它的主要领域</th></tr></thead>'
            f'<tbody>{"".join(recency_rows)}</tbody></table></div>'
            '<p class="muted small">按公司各产品码所在领域的「近 90 天发表占比」加权平均。'
            '<b>这衡量的是它所在赛道的文献活跃度，不是这家公司的产出</b>：'
            '一家公司自己发不发论文，这个数字都说明不了；它只说这个领域的近期工作在变多还是变少。</p>')
    else:
        recency_block = ""

    # What each company's brands have reported. Kept out of the metrics table above, because those are
    # counts of the company's own records while these are name matches into someone else's free text -
    # putting them in the same table would imply they are the same kind of number.
    reports = []
    for company in found:
        shape = company.get("brand_failures") or {}
        reports.append({
            "name": str(company.get("company_name") or company.get("query") or ""),
            "brands": int(shape.get("brands") or 0),
            "total": int(shape.get("total") or 0),
            "events": shape.get("by_event") or {},
        })
    if any(item["total"] for item in reports):
        rows = []
        for item in reports:
            events = item["events"]
            if item["total"]:
                cells = "".join(
                    f'<td class="num">{n(int(events.get(k) or 0))}</td>'
                    for k in ("Malfunction", "Injury", "Death"))
                rows.append(f'<tr><td>{esc(item["name"])}</td><td class="num">{n(item["total"])}</td>'
                            f'{cells}</tr>')
            else:
                # Zero matches is not zero reports: say which one it is.
                rows.append(f'<tr><td>{esc(item["name"])}</td>'
                            f'<td class="num" colspan="4">— 按 {n(item["brands"])} 个品牌名未匹配到</td></tr>')
        brand_table = (
            '<div class="card"><table><thead><tr><th>公司</th><th>报告数</th><th>故障</th>'
            '<th>伤害</th><th>死亡</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>'
            '<p class="muted small">按各公司在注册表里的全部品牌名称匹配 FDA MAUDE。'
            '<b>这是名称匹配，不是法定主体归属</b>，也不跨法人合并：同一集团的不同公司各算各的。'
            '上报是自愿的，数字大小取决于有多少人在报，<b>不是故障率，不能用来比较谁更安全</b>。</p>')
    else:
        brand_table = ""
    brand_block = (f'<h2>品牌报告（名称匹配）</h2>{brand_table}' if brand_table else "")

    # Technology areas side by side: where two companies both register devices is where they compete.
    # A row is a specialty, a cell is how many of that company's product codes fall in it. This uses
    # the FDA classification, so it is "registered in", not "leads in" - the note says so.
    specialty_sets = [{item["specialty"]: int(item["codes"])
                       for item in (company.get("specialties") or [])} for company in found]
    area_names: dict[str, int] = {}
    for mapping in specialty_sets:
        for name, count in mapping.items():
            area_names[name] = area_names.get(name, 0) + count
    area_rows = []
    for name in sorted(area_names, key=lambda key: -area_names[key])[:12]:
        cells = "".join(
            f'<td class="num{" lead" if mapping.get(name) else ""}">'
            f'{n(mapping.get(name)) if mapping.get(name) else "—"}</td>'
            for mapping in specialty_sets)
        area_rows.append(f"<tr><td>{esc(name)}</td>{cells}</tr>")
    area_table = (f'<div class="card"><h4>技术领域（按 FDA 产品码分类）</h4>'
                  f'<p class="muted small">数字是该公司落在该领域的产品码数量；— 表示没有产品码落在那里。'
                  f'这是"注册了什么"，不是"发表了什么"，也不代表技术领先。</p>'
                  f'<table><thead><tr><th>技术领域</th>{header}</tr></thead>'
                  f'<tbody>{"".join(area_rows)}</tbody></table></div>'
                  if area_rows else gap_note("no_classified_product_code"))

    # Product-code overlap: the codes two companies both hold are where they actually compete.
    codes = [set(item.get("product_codes") or []) for item in found]
    shared = set.intersection(*codes) if codes else set()
    union = set.union(*codes) if codes else set()
    # A company with no classified product codes is a real state (its devices carry codes the
    # classification table does not cover), and it made this line divide by zero. Say it instead.
    if union:
        overlap_head = (f'<h4>共同覆盖的产品码 {n(len(shared))} 个'
                        f'（合计 {n(len(union))} 个，重合度 '
                        f'{(100.0 * len(shared) / len(union)):.0f}%）</h4>')
    else:
        overlap_head = ('<h4>没有可比较的产品码</h4>'
                        '<p class="muted small">这些公司在注册表里的产品码为空，'
                        '或都还没被产品码分类表覆盖，所以算不出重合度。</p>')
    overlap = (f'<div class="card">{overlap_head}'
               + (f'<p class="muted small">{esc("、".join(sorted(shared)[:40]))}</p>'
                  if shared else ('<p class="muted small">没有共同的产品码。</p>' if union else ''))
               + "</div>")

    brands = []
    for item in found:
        items = item.get("brands") or []
        listing = "".join(
            f'<tr><td><a href="/device?query={esc(b["brand"])}">{esc(b["brand"])}</a></td>'
            f'<td class="num">{n(b["devices"])}</td></tr>'
            for b in items[:5])
        brands.append(
            f'<div class="card"><h4><a href="/company?q={esc(item.get("company_name"))}">'
            f'{esc(item.get("company_name"))}</a></h4>'
            f'<table><tbody>{listing or "<tr><td class=muted>无品牌记录</td></tr>"}</tbody>'
            f'</table></div>')

    missing = [item for item in companies if not item.get("found")]
    missing_html = "".join(
        f'<p class="small muted">「{esc(item.get("query"))}」没有匹配到公司，未参与对比。</p>'
        for item in missing)
    # A swapped name is printed, not hidden: a reader who typed 美敦力 must be able to see that the
    # column is Medtronic and not a different company with a similar name.
    swapped_html = "".join(
        f'<p class="small muted">「{esc(typed)}」按英文法定名称「{esc(english)}」对比'
        f'<span class="muted">（中文名对照只是方便输入，不是注册表内容）</span></p>'
        for typed, english in swapped.items()) if swapped else ""

    body = f"""
<p class="small muted"><a href="/">← 重新查询</a></p>
<h1>公司对比</h1>
<p class="lede">{n(len(found))} 家公司并列。数字大的标出来，但"大"不等于"强"——
注册设备多是铺货广，批文多才是产品线深。</p>
<p class="small muted">导出：<a href="/download?kind=compare&format=md&q={esc(','.join(str(c.get('company_name') or c.get('query')) for c in found))}">Markdown</a>
 · <a href="/download?kind=compare&format=csv&q={esc(','.join(str(c.get('company_name') or c.get('query')) for c in found))}">CSV</a>
 · <a href="/download?kind=compare&format=json&q={esc(','.join(str(c.get('company_name') or c.get('query')) for c in found))}">JSON</a></p>
{swapped_html}
{missing_html}
<h2>规模与产出</h2>
{table}
{year_block}
{recency_block}
{brand_block}
<h2>技术领域对比</h2>
{area_table}
<h2>竞争面</h2>
{overlap}
<h2>各自的品牌</h2>
{''.join(brands)}
"""
    return layout(title="公司对比 · MedRadar", body=body, active="company")


def warmup(service: Any) -> dict[str, Any]:
    """Touch the stores before a reader does.

    Measured on a freshly restarted process: the first `/device?query=X1209255` took 15 s, of which
    `resolve` was 6.8 s and the paper history 4.1 s - for queries that answer in milliseconds once
    the pages are in memory. Nothing was slow; everything was cold. Index pages for a 5.2M-row table
    and the 785k-row paper index have to come off disk the first time.

    So the process reads them at startup, in a daemon thread, while nobody is waiting. Every step is
    allowed to fail: a deployment without a device register must still serve its pages.
    """
    report: dict[str, Any] = {"queries": 0, "papers": False, "errors": []}
    store = None
    try:
        from .reference import UdiReference

        path = service.paths.reference
        if not path.is_file():
            report["errors"].append("no device register")
            return report
        store = UdiReference(str(path))
        # One of each identifier shape, because each takes a different index - and the company and
        # brand shapes are the expensive ones (ten device timelines each). These are exactly the
        # examples the landing page offers, so the first reader who clicks one does not pay for it.
        for query in ("08800055700571", "K213506", "X1209255", "Medtronic", "Clydesdale"):
            try:
                from .device_view import resolve

                resolve(store, query)
                report["queries"] += 1
            except Exception as error:  # noqa: BLE001
                report["errors"].append(f"{query}: {type(error).__name__}")
        try:
            from .device_view import build as build_view

            corpus = service.paths.corpus
            build_view(store, "Medtronic", limit=10,
                       corpus_root=corpus if corpus.is_dir() else None)
            report["dossier"] = True
        except Exception as error:  # noqa: BLE001
            report["errors"].append(f"dossier: {type(error).__name__}")
        # The field pages need the 318k-term vocabulary loaded before their topic chips can be built.
        # Measured: the first /area in a fresh process took 1.1-1.35 s and every one after it 0.26-0.30 s,
        # with field_topics itself at 851-959 ms on the first call and 33 ms afterwards.
        try:
            from .paper_passes import field_topics

            field_topics(store, "Dental")
            report["vocabulary"] = True
        except Exception as error:  # noqa: BLE001 - no literature yet is normal
            report["errors"].append(f"vocabulary: {type(error).__name__}")

        try:
            from .papers_index import _total_papers

            _total_papers(store)
            report["papers"] = True
        except Exception as error:  # noqa: BLE001
            report["errors"].append(f"papers: {type(error).__name__}")
        # The landing page counts four stores; on a cold process those counts read millions of
        # index pages off disk and the first visitor paid for it (measured 8 s for "/").
        for key, sql in (("devices", "SELECT COUNT(*) FROM udi_device"),
                         ("failures", "SELECT COUNT(*) FROM maude_failure_index"),
                         ("trials", "SELECT COUNT(*) FROM trial"),
                         ("patents", "SELECT COUNT(*) FROM bulk_patent")):
            try:
                store.conn.execute(sql).fetchone()
                report[key] = True
            except Exception as error:  # noqa: BLE001 - an absent table is normal on a fresh deploy
                report["errors"].append(f"{key}: {type(error).__name__}")

        # Every page in the navigation, not just the landing page. Measured: /paper took 4.71 s for
        # the first reader after a restart and 0.29 s for the second - the whole cost was a cold
        # index, paid by whoever happened to open the second-most-prominent link in the nav. This
        # runs the same queries the pages run, so the pages' own caches are primed too.
        warmed: dict[str, Any] = {}
        try:
            from .papers_index import brands_for_terms, distinctive_terms, paper_record, paper_terms

            row = store.conn.execute(
                "SELECT paper_id FROM paper_term GROUP BY paper_id "
                "ORDER BY COUNT(*) DESC LIMIT 1").fetchone()
            sample = str(row[0]) if row and row[0] else None
            if sample:
                paper_record(store, sample)
                terms = [str(item["term"]) for item in paper_terms(store, sample, limit=60)]
                kept, _dropped = distinctive_terms(store, terms)
                brands_for_terms(store, kept, limit=30)
                warmed["paper"] = sample
        except Exception as error:  # noqa: BLE001
            report["errors"].append(f"paper: {type(error).__name__}")

        # /radar was not warmed at all and cost the first reader 3.8 s (measured cold, twice):
        # the feed reads the whole observation table. /compare likewise - 1.8 s cold, 0.29 s warm.
        try:
            from .health import change_stream

            with service.ledger() as ledger:
                change_stream(ledger, limit=40)
                ledger.raw("SELECT COUNT(*) AS n FROM observation")
            warmed["radar"] = True
        except Exception as error:  # noqa: BLE001 - no ledger is a normal first deployment
            report["errors"].append(f"radar: {type(error).__name__}")
        try:
            names, _substitutions = _resolve_compare_names(store, ["Medtronic", "Stryker"], {})
            for name in names[:2]:
                _company_data(store, name, snapshot={})
            warmed["compare"] = len(names)
        except Exception as error:  # noqa: BLE001
            report["errors"].append(f"compare: {type(error).__name__}")

        for name, builder in (("company", lambda: _company_data(store, "Medtronic", snapshot={})),
                              ("areas", lambda: __import__(
                                  "medradar.radar.specialty", fromlist=["read"]).read(store)),
                              ("sources", lambda: __import__(
                                  "medradar.radar.coverage", fromlist=["coverage"]).coverage(store))):
            try:
                builder()
                warmed[name] = True
            except Exception as error:  # noqa: BLE001 - a page that cannot warm still serves
                report["errors"].append(f"{name}: {type(error).__name__}")
        # Prime the rendered pages themselves. This is the step audit 06 said was missing: the data
        # below these routes was warm and the cache entry was not, so /compare still cost 1.76 s cold.
        primed: dict[str, bool] = {}
        for name, call in list(_PAGE_ROUTES.items()):
            try:
                call()
                primed[name] = True
            except Exception as error:  # noqa: BLE001 - a page that cannot warm still serves
                report["errors"].append(f"prime:{name}: {type(error).__name__}")
        report["primed"] = primed

        # Every field page, staggered.
        #
        # Measured: the first /area for a field that has not been read in this process costs 0.3-1.35 s
        # and every later one 0.26-0.34 s, because that field's rows come off disk then. Touring all
        # twenty fields paid it twenty times. Priming them all at once was measured to be worse than
        # useless - the burst competed with real requests and /compare went from 1.76 s to 4.6 s - so
        # they are spread out, one every two seconds, and the loop stops if the process is shutting down.
        #
        # This runs last: a reader who arrives during it has every page except the field they asked for.
        try:
            from .specialty import read as read_specialties

            names = [str(item.get("specialty") or "") for item in
                     (read_specialties(store).get("items") or [])]
            staggered: list[str] = []
            for name in names:
                if not name or _AREA_PRIMER is None:
                    continue
                try:
                    _AREA_PRIMER(name=name)
                    staggered.append(name)
                except Exception as error:  # noqa: BLE001 - one field must not stop the rest
                    report["errors"].append(f"prime:area:{name}: {type(error).__name__}")
                time.sleep(2.0)
            report["primed_areas"] = len(staggered)
        except Exception as error:  # noqa: BLE001
            report["errors"].append(f"prime:areas: {type(error).__name__}")
        report["warmed"] = warmed
    except Exception as error:  # noqa: BLE001
        report["errors"].append(f"{type(error).__name__}: {error}")
    finally:
        if store is not None:
            try:
                store.close()
            except Exception:  # noqa: BLE001
                pass
    return report


def paper_page(*, record: Mapping[str, Any] | None, terms: Sequence[Mapping[str, Any]],
               brands: Sequence[Mapping[str, Any]], paper_id: str,
               suggestions: Sequence[str] = (),
               title_matches: Sequence[Mapping[str, Any]] = ()) -> str:
    """The reverse of the device dossier: a reader arrives with a paper and asks who makes the thing.

    Every other page here starts from a device. An engineer reading a paper has the opposite problem,
    and the honest answer is narrow: the index can say which registered brand names share the words
    this paper was indexed under. That is a lead to check, not a claim that the paper studies that
    product, and the page says so before the list rather than after it.
    """
    from .watermark import utc_today

    if record is None:
        # A reader who arrives with a title used to be told the paper was not in the index, which was
        # false whenever the title did match - the page only looked at identifiers. Titles are now
        # searched, and the matches are offered as candidates rather than as an identity: a title can
        # repeat across papers, and a paraphrased one will not match at all.
        if title_matches:
            rows = "".join(
                f'<tr><td><a href="/paper?id={esc(str(item.get("paper_id")))}">'
                f'{esc(str(item.get("title")))}</a></td>'
                f'<td class="muted small">{esc(str(item.get("journal") or ""))}</td>'
                f'<td class="muted small">{esc(str(item.get("published_at") or ""))}</td></tr>'
                for item in title_matches)
            found = (f'<h2>标题里有这几个字的有 {len(title_matches)} 篇</h2>'
                     '<p class="small muted">按标题文字匹配，不是唯一识别——同名论文会有多个，'
                     '改写或截断的标题匹配不到。点开确认是哪一篇。</p>'
                     f'<div class="card"><table><thead><tr><th>标题</th><th>期刊</th>'
                     f'<th>发表日期</th></tr></thead><tbody>{rows}</tbody></table></div>')
        else:
            found = (gap_note("paper_not_in_index")
                     + '<p class="small muted">标题里也没有这几个字。索引只收录已归档全文，'
                       '摘要和付费墙后的正文不在内。</p>')

        return layout(
            title="论文 · MedRadar",
            body=(f'<h1>没有这篇论文：{esc(paper_id)}</h1>'
                  '<p class="lede">可以输入论文编号（如 PMC13788955），也可以输入标题里的几个词。</p>'
                  '<form class="search" method="get" action="/paper">'
                  f'<input type="search" name="id" value="{esc(paper_id)}" '
                  'aria-label="论文编号或标题关键词">'
                  '<button type="submit">反查</button></form>'
                  + found
                  + (f'<p class="small muted">例如：'
                     + " · ".join(f'<a href="/paper?id={esc(s)}">{esc(s)}</a>' for s in suggestions[:4])
                     + "</p>" if suggestions else "")),
            active="device")

    term_rows = "".join(
        f'<span class="chip">{esc(item["term"])} · {n(item["hits"])}</span>'
        for item in terms[:24])
    brand_rows = "".join(
        f'<tr><td><a href="/device?query={esc(item["brand_name"])}">'
        f'{esc(item["brand_name"])}</a></td>'
        f'<td class="num">{n(item.get("shared"))}</td>'
        f'<td class="muted small">{esc("、".join(item.get("shared_terms") or []))}</td></tr>'
        for item in brands)
    brand_html = (f'<div class="card"><table><thead><tr><th>已注册品牌</th><th>共同词</th>'
                  f'<th>是哪些词</th></tr></thead><tbody>{brand_rows}</tbody></table></div>'
                  if brand_rows else gap_note("no_registered_brand_shares_these_terms"))

    # A date after today is a journal pre-filling an upcoming issue, not a paper published in the
    # future. Measured in the live corpus: 14 of 3,366 records carry one (three at 2027-01-01).
    raw_date = str(record.get("year") or "")[:10]
    if raw_date and raw_date > str(utc_today()):
        date_note = f' · {esc(raw_date)}<span class="muted small">（期刊预填，尚未出版）</span>'
    else:
        date_note = f' · {esc(raw_date)}' if raw_date else ""

    body = f"""
<p class="small muted"><a href="/">← 重新查询</a></p>
<h1>{esc(record.get("title") or paper_id)}</h1>
<p class="lede">{esc(paper_id)}{date_note}</p>

<h2>这篇论文被索引到的词</h2>
<p class="muted small">只索引了注册表里出现过的名称，所以这张词表本身就是"这篇论文提到了哪些已知产品名"。</p>
<div class="chips">{term_rows or '<span class="muted">没有索引词</span>'}</div>

<h2>这些词指向哪些已注册产品</h2>
<div class="gap"><b>先看清楚这是什么：</b>下面是<b>共用这些词</b>的已注册品牌名，
<b>不代表</b>这篇论文研究的就是这些产品。它是一条线索，判断还得打开原文核对。</div>
{brand_html}
"""
    return layout(title=f"{record.get('title') or paper_id} · MedRadar", body=body, active="device")


def areas_page(*, data: Mapping[str, Any]) -> str:
    """Every medical specialty in the register: how big, and who is crowded into it.

    This is the whole-market view the company pages could not give. It answers a different question
    from the technology map and from a company dossier: not what one company registered, but how the
    register splits across device categories, and which manufacturers dominate each.
    """
    items = data.get("items") or []
    if not items:
        return layout(
            title="技术领域 · MedRadar",
            body=('<h1>技术领域分布</h1>'
                  + gap_note(data.get("gap") or "specialty_stats_absent")),
            active="areas")

    largest = max((int(item.get("devices") or 0) for item in items), default=0) or 1
    literature = data.get("literature") or {}

    def _paper_count(specialty: str) -> int:
        # The linked total, not the last run's yield: a re-run that finds everything cached reports
        # stored 0 and used to make a well-covered field look empty.
        entry = literature.get(specialty) or {}
        return int(entry.get("papers") or entry.get("stored") or 0)

    recency = data.get("recency") or {}

    def _recency_pct(specialty: str) -> int:
        return int((recency.get(specialty) or {}).get("pct") or 0)

    order = str(data.get("sort") or "devices")
    if order == "recent":
        # Where the literature is moving, not where it is largest. The ratio is bounded by the crawler's
        # 120-per-field cap, which the note under the table states.
        items = sorted(items, key=lambda item: (-_recency_pct(str(item.get("specialty"))),
                                               -int(item.get("devices") or 0)))
    elif order == "papers":
        items = sorted(items, key=lambda item: (-_paper_count(str(item.get("specialty"))),
                                               -int(item.get("devices") or 0)))
    elif order == "pending":
        # Fields the literature lane has not reached at all come first, largest register first:
        # that is the work queue, not the reading list.
        items = sorted(items, key=lambda item: (str(item.get("specialty")) in literature,
                                               -int(item.get("devices") or 0)))
    elif order == "companies":
        items = sorted(items, key=lambda item: -int(item.get("companies") or 0))
    else:
        items = sorted(items, key=lambda item: -int(item.get("devices") or 0))

    tabs = "".join(
        f'<a class="tab{" on" if key == order else ""}" href="/areas?sort={key}">{esc(label)}</a>'
        for key, label in (("devices", "按设备数"), ("companies", "按公司数"),
                           ("papers", "按已抓论文"), ("recent", "按近 90 天占比"),
                           ("pending", "按未抓取优先")))
    order_note = {
        "devices": "按注册设备数排序：市场铺得最广的领域在前。",
        "companies": "按公司数排序：挤进来的厂商最多的领域在前。",
        "papers": "按已归档论文数排序：文献线目前投得最多的领域在前。",
        "recent": ("按「近 90 天发表占比」排序：每个领域我们只保留最新的 120 篇，"
                   "占比高说明这个领域近期产出密集到把这个名额填满。"),
        "pending": "还没被文献线抓到过的领域排在最前，再按设备数——这是待办队列，不是阅读顺序。",
    }.get(order, "")

    def _recent_cell(specialty: str) -> str:
        entry = recency.get(specialty) or {}
        if not entry:
            return '<span class="muted">—</span>'
        pct = int(entry.get("pct") or 0)
        return (f'{pct}%<span class="muted small"> {int(entry.get("recent") or 0)}/'
                f'{int(entry.get("held") or 0)}</span>')

    def lit_cell(specialty: str) -> str:
        """What the literature lane has done for this field - and nothing it has not.

        A field that has never been crawled and a field whose query found nothing are different
        states; printing a dash for both would make the second look like an absence of research.
        """
        entry = literature.get(specialty)
        if not entry and specialty == "Unknown":
            # FDA's own catch-all: 420 product codes the classification table files under no specialty.
            # It has no query because there is nothing to query - saying "未纳入轮转" would imply a
            # backlog that does not exist.
            return '<span class="muted small">FDA 未分类，不做文献轮转</span>'
        if not entry:
            # Not the same as "no research exists": the first papers were fetched for weeks by one
            # fixed query that was not recorded per field, so a well-covered field can legitimately be
            # absent from the rotation table. "未抓取" would understate orthopaedics.
            return '<span class="muted small">未纳入轮转</span>'
        stored = int(entry.get("papers") or entry.get("stored") or 0)
        matched = int(entry.get("matched") or 0)
        gap = max(0, matched - stored)
        if stored:
            extra = f'（查询命中 {n(matched)}，其中 {n(gap)} 篇没有全文）' if gap else ''
            return (f'<span class="num">{n(stored)}</span>'
                    f'<span class="muted small"> 篇已归档{extra}</span>')
        return (f'<span class="muted small">候选 {n(entry.get("candidates") or 0)}，'
                f'其中 {n(entry.get("skipped") or 0)} 篇已缓存</span>')

    rows = []
    for item in items:
        leaders = item.get("top_companies") or []
        share = int(round(100.0 * int(item.get("devices") or 0) / largest))
        company_list = "；".join(
            f'<a href="/company?q={esc(str(lead.get("company") or ""))}">'
            f'{esc(str(lead.get("company") or ""))[:34]}</a>'
            f'<span class="muted small"> {n(lead.get("devices"))}</span>'
            for lead in leaders[:4])
        rows.append(
            f'<tr><td>{esc(item.get("specialty"))}</td>'
            f'<td class="num">{n(item.get("codes"))}</td>'
            f'<td class="num">{n(item.get("devices"))}</td>'
            f'<td class="num">{n(item.get("companies"))}</td>'
            f'<td>{company_list or "<span class=\'muted\'>—</span>"}</td>'
            f'<td>{lit_cell(str(item.get("specialty")))}</td>'
            f'<td class="num">{_recent_cell(str(item.get("specialty")))}</td>'
            f'<td><span class="bar" style="width:{share}%"></span></td></tr>')
    body = f"""
<h1>技术领域分布</h1>
<p class="lede">按 FDA 产品码分类，全库 {n(len(items))} 个技术领域里，各自有多少设备、多少家公司，
以及设备数最多的那几家。点公司名直接进档案。</p>
<p class="small">{tabs}</p>
<p class="muted small">{esc(order_note)}</p>
<p class="small muted">导出：<a href="/download?kind=areas&format=md">Markdown</a>
 · <a href="/download?kind=areas&format=csv">CSV</a>
 · <a href="/download?kind=areas&format=json">JSON</a></p>
<div class="gap"><b>这张表说明什么：</b>它数的是<b>注册了什么</b>——产品码来自厂商登记，
不是论文、不是专利。一家公司在某领域设备多，说明它在那里铺得广，不说明它技术领先。
「设备数」按注册条目计，同一台设备有多个产品码时会分别计入各领域，所以各行相加会大于总设备数。</div>
<div class="card"><table>
<thead><tr><th>技术领域</th><th>产品码</th><th>设备数</th><th>公司数</th><th>设备最多的公司</th>
<th>文献抓取</th><th>近 90 天占比</th><th>规模</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
<p class="small muted">数据更新于 {esc(str(data.get("updated_at") or "未知")[:16])}，
由夜间任务重算（全库聚合约 29 秒，不实时计算）。</p>
"""
    return layout(title="技术领域分布 · MedRadar", body=body, active="areas")


def area_page(*, specialty: str, summary: Mapping[str, Any] | None,
              companies: Sequence[Mapping[str, Any]],
              data: Mapping[str, Any] | None = None) -> str:
    """One specialty: its leaders, what its literature talks about, and a way to compare them.

    The link from /areas used to lead nowhere; the chain is 领域 -> 公司 -> 对比, and this is the
    middle. The checkboxes submit several `q` values to /compare, which joins them, so the comparison
    page is reachable without typing a comma-separated URL.

    The literature block answers the question this product exists for - what is being researched in
    this field now - and is careful about what it claims: term frequency in the papers this field's own
    query fetched, with structural words removed, not a judgement about technology direction.
    """
    data = data or {}
    if summary is None:
        # The field exists under its English name. Saying only "统计表缺失" would report our vocabulary
        # as missing data - the same mistake as answering 美敦力 with "不在注册表里".
        from .aliases import lookup_specialty

        hits = lookup_specialty(specialty)
        if hits:
            links = "、".join(
                f'<a href="/area?name={esc(item["specialty"])}">{esc(item["specialty"])}</a>'
                for item in hits[:3])
            hint = (f'<div class="gap"><b>技术领域用的是 FDA 的英文分类名。</b>'
                    f'「{esc(hits[0]["chinese"])}」在库里叫 {links}'
                    f'<span class="muted small">（中文名对照只是方便输入，不是库里的字段）</span></div>')
        else:
            hint = ('<div class="gap"><b>技术领域用的是 FDA 的英文分类名。</b>'
                    '可以用 Orthopedic、Dental、Cardiovascular 这样的英文名，'
                    '或从 <a href="/areas">技术领域总表</a> 里点进去。</div>')
        return layout(
            title=f"{specialty} · MedRadar",
            body=(f'<h1>{esc(specialty)}</h1>' + hint
                  + '<p class="small muted"><a href="/areas">← 全部技术领域</a></p>'),
            active="areas")

    kept = len(companies)
    total = int(summary.get("companies") or 0)
    rows = "".join(
        f'<tr><td class="num">{n(item.get("rank"))}</td>'
        f'<td><label><input type="checkbox" name="q" value="{esc(item.get("company_name"))}"> '
        f'<a href="/company?q={esc(item.get("company_name"))}">'
        f'{esc(item.get("company_name"))}</a></label></td>'
        f'<td class="num">{n(item.get("devices"))}</td></tr>'
        for item in companies)
    table = (f'<form method="get" action="/compare">'
             f'<div class="card"><table><thead><tr><th>#</th><th>公司（勾选后一起对比）</th>'
             f'<th>该领域设备数</th></tr></thead><tbody>{rows}</tbody></table>'
             f'<p><button type="submit">对比勾选的公司（最多 4 家）</button></p></div></form>'
             if rows else gap_note("no_company_in_this_specialty"))
    # A list of fifty is a sample of the field, and saying which sample matters.
    coverage = (f'<p class="small muted">下面是该领域设备数最多的 {n(kept)} 家'
                f'（全领域共 {n(total)} 家）。没上榜不等于规模为零，只表示排在这 {n(kept)} 家之后。'
                f'</p>' if kept < total else
                f'<p class="small muted">该领域全部 {n(total)} 家公司都在下面。</p>')
    # What the field's own papers talk about. Restricted to the papers this field's query brought in,
    # so the answer is about the field rather than about the corpus as a whole.
    resolved_from = str(data.get("resolved_from") or "")
    # Never swap a field silently: say which name was used for the lookup.
    resolved_note = (f'<p class="small muted">「{esc(resolved_from)}」按英文分类名 '
                     f'「{esc(specialty)}」查询。</p>' if resolved_from else "")
    topics = data.get("field_topics") or []
    field_papers = data.get("field_papers") or []
    if topics:
        # "in 42 of 120 papers" is checkable; a hit count is not, because it depends on how often a paper
        # repeats a word. The hits stay in the tooltip for anyone who wants them.
        # How much of the corpus the field pages speak for. Audit 09 asked for this: 120 papers is a
        # sample of the field's literature, and 43% of the corpus is split into fields at all.
        coverage = data.get("literature_coverage") or {}
        coverage_note = ""
        if coverage.get("indexed") and coverage.get("field_linked"):
            share = int(round(100.0 * int(coverage["field_linked"]) / int(coverage["indexed"])))
            coverage_note = (f'全部 {n(coverage["indexed"])} 篇已索引论文里，'
                             f'{n(coverage["field_linked"])} 篇（{share}%）被分进了某个领域；'
                             '其余没有命中任何领域的查询，所以领域页说的是它自己那批，不是全库。')
        chips = "".join(
            f'<span class="chip" title="{n(item.get("count"))} 次命中">{esc(str(item["term"]))}'
            f'<span class="muted small"> {n(item.get("papers"))}/{n(item.get("held"))} 篇</span></span>'
            for item in topics)
        topics_block = (
            '<h2>这个领域的文献在谈什么</h2>'
            f'<p class="muted small">从本领域查询抓进来的 {n(len(field_papers))} 篇全文中统计词频。'
            '这是「论文里出现的词」，不是我们的技术判断。两条过滤：结构性虚词按词表去掉，'
            '同时在 10 个以上领域都出现的词也去掉——到处都有的词说明不了这个领域。'
            f'数字是「出现在这 {n(len(field_papers))} 篇里的多少篇」，不是出现次数。{coverage_note}</p>'
            f'<div class="chips">{chips}</div>')
    else:
        topics_block = ('<h2>这个领域的文献在谈什么</h2>'
                        + gap_note("no_papers_for_this_specialty"))
    # What goes wrong in this field, from MAUDE. Counts of reports, not rates: MAUDE is voluntary, so a
    # popular code has more reports partly because it has more devices in use and more reporters.
    shape = data.get("field_failures") or {}
    if int(shape.get("total") or 0):
        events = shape.get("by_event") or {}
        order = [("Malfunction", "故障"), ("Injury", "伤害"), ("Death", "死亡")]
        event_bits = " · ".join(
            f'{label} {n(int(events.get(key) or 0))}' for key, label in order if events.get(key))
        other = int(shape.get("total") or 0) - sum(
            int(events.get(key) or 0) for key, _ in order)
        if other > 0:
            event_bits += f' · 其他/未标注 {n(other)}'
        rows = "".join(
            f'<tr><td>{esc(item["code"])}'
            f'<span class="muted small"> {esc(str((shape.get("names") or {}).get(item["code"]) or "")[:52])}</span>'
            f'</td><td class="num">{n(item["reports"])}</td></tr>'
            for item in (shape.get("by_code") or []))
        failures_block = (
            '<h2>这个领域报过哪些失效</h2>'
            f'<p class="muted small">按 FDA MAUDE 报告统计：本领域 {n(shape.get("codes"))} 个产品码下'
            f'共 {n(shape.get("total"))} 条报告 —— {event_bits}。'
            '<b>这是报告数，不是故障率</b>：MAUDE 靠自愿上报，产品用得越多、上报的人越多，'
            '数字就越大；不能用来比较两个产品谁更安全。</p>'
            f'<div class="card"><table><thead><tr><th>产品码</th><th>报告数</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>')
        # When those reports arrived, and why the shape is ours rather than the field's. Measured on
        # Dental: 2015-2026, with 5,457 of 12,428 in 2026 because the sweep walks the newest files;
        # DZE's 1,653 are all 2026. Printed as numbers with that sentence, not as bars, because a bar
        # chart of a crawl window reads as a safety trend.
        years = shape.get("by_year") or {}
        if years:
            keys = sorted(years)
            total_year = sum(years.values()) or 1
            top_key = max(years, key=lambda k: years[k])
            share = 100.0 * years[top_key] / total_year
            listed = " · ".join(f"{k} {n(years[k])}" for k in keys[-6:])
            failures_block += (
                f'<p class="muted small">报告日期 {esc(keys[0])}–{esc(keys[-1])}，'
                f'最近几年：{listed}。'
                f'其中 {esc(top_key)} 年占 {share:.0f}%——'
                '<b>因为我们的失效索引扫的是最近的报告文件</b>，所以近年偏多；'
                '这不是该领域变得更危险了。</p>')
    elif int(shape.get("codes") or 0):
        # Checked and empty: say so, because an absent section reads as "not looked at".
        failures_block = (
            '<h2>这个领域报过哪些失效</h2>'
            f'<p class="muted small">这个领域的 {n(shape.get("codes"))} 个产品码下，'
            '我们扫过的 MAUDE 报告里一条也没有匹配到。这不等于没有上报：'
            '可能是这些码的报告文件还没扫到。</p>')
    else:
        failures_block = ""

    # Monthly shape. The corpus is one crawl, made now, so the series says when our papers were
    # published - not how much the field publishes. The sentence under the bars states that.
    monthly = data.get("field_monthly") or []
    if monthly and sum(int(item.get("n") or 0) for item in monthly):
        peak = max(int(item.get("n") or 0) for item in monthly) or 1
        bars = "".join(
            f'<div class="month"><div class="bar" style="height:{max(2, int(round(60 * int(item.get("n") or 0) / peak)))}px"'
            f' title="{esc(str(item.get("ym")))}：{n(item.get("n"))} 篇"></div>'
            f'<span class="muted small">{esc(str(item.get("ym"))[2:])}</span></div>'
            for item in monthly)
        # The same measure /areas sorts by, stated here so the field page answers "is this field busy"
        # without the reader going back to the list.
        recent_note = ""
        recency = data.get("field_recency") or {}
        if recency:
            recent_note = (f'其中近 90 天发表 {n(int(recency.get("recent") or 0))} 篇'
                           f'（{int(recency.get("pct") or 0)}%）——'
                           '每个领域我们只保留最新的 120 篇，这个比例衡量的是产出密度，不是产量。')
        monthly_block = (
            '<h2>按月分布</h2>'
            f'<p class="muted small">本领域已归档论文按发表日期统计，近 {n(len(monthly))} 个月，'
            f'最高一个月 {n(peak)} 篇。{recent_note}'
            '<b>这反映的是我们这批论文的发表时间</b>，不是该领域的总发表量——'
            '语料是一轮抓取的结果，年份集中在抓取时可见的近几年。</p>'
            f'<div class="months">{bars}</div>')
    else:
        monthly_block = ""

    # What has been published lately among what we hold. Bounded in the sentence itself: this is the
    # newest of the papers this field's lane fetched, not everything published in the field.
    recent = data.get("field_recent") or []
    if recent:
        recent_rows = "".join(
            f'<tr><td class="muted small">{esc(str(item.get("published_at") or ""))}</td>'
            f'<td><a href="/paper?id={esc(str(item.get("paper_id")))}">'
            f'{esc(str(item.get("title") or "")[:110])}</a>'
            f'<div class="muted small">{esc(str(item.get("journal") or ""))[:70]}</div></td></tr>'
            for item in recent)
        recent_block = (
            '<h2>这个领域最近发表的</h2>'
            f'<p class="muted small">本领域已归档论文中发表日期最新的 {n(len(recent))} 篇。'
            '这是"我们手上的这些论文里最新的"，不是"这个领域全部新论文"；'
            '出版日期在未来的期刊预填记录已排除。</p>'
            f'<p class="small muted">导出：'
            f'<a href="/download?kind=papers&format=md&name={esc(specialty)}">Markdown</a>'
            f' · <a href="/download?kind=papers&format=csv&name={esc(specialty)}">CSV</a>'
            f' · <a href="/download?kind=papers&format=json&name={esc(specialty)}">JSON</a>'
            f'<span class="muted"> —— CSV 是纯数据表，上面那句边界说明不在文件里；'
            f'要连说明一起转发，用 Markdown。</span></p>'
            f'<div class="card"><table><thead><tr><th>发表日期</th><th>标题</th></tr></thead>'
            f'<tbody>{recent_rows}</tbody></table></div>')
    else:
        recent_block = ""
    body = f"""
<p class="small muted"><a href="/areas">← 全部技术领域</a></p>
<h1>{esc(specialty)}</h1>
<p class="lede">{n(summary.get("devices"))} 台设备 · {n(summary.get("codes"))} 个产品码 ·
{n(summary.get("companies"))} 家公司</p>
{resolved_note}
<p class="small muted">导出：
<a href="/download?kind=area&format=md&name={esc(specialty)}">Markdown</a>
 · <a href="/download?kind=area&format=csv&name={esc(specialty)}">CSV</a>
 · <a href="/download?kind=area&format=json&name={esc(specialty)}">JSON</a>
 · 失效表 <a href="/download?kind=area_failures&format=csv&name={esc(specialty)}">CSV</a></p>
<div class="gap"><b>这张表数的是注册，不是技术。</b>设备数按注册条目计，一台设备带多个产品码时
会在各领域分别计入；一家公司在这里设备多，说明它铺得广，不说明它领先。</div>
{topics_block}
{monthly_block}
{failures_block}
{recent_block}
{coverage}
{table}
<p class="small muted">数据更新于 {esc(str(summary.get("updated_at") or "未知")[:16])}。</p>
"""
    return layout(title=f"{specialty} · MedRadar", body=body, active="areas")


def _compare_names(store: Any, raw: Sequence[str], snapshot: Mapping[str, Any]) -> list[str]:
    """Which companies the URL asked for.

    Repeated `q` values (what /area's checkboxes send) are literal names - splitting them on commas
    broke every company whose registered name contains one, and "GLOBUS MEDICAL, INC." became two
    companies plus a fragment. A single comma string (what a person types) is still split, but only
    after the whole string fails to resolve as one company.
    """
    values = [str(value).strip() for value in raw if str(value).strip()]
    if len(values) == 1 and "," in values[0]:
        whole = values[0]
        if _company_data(store, whole, snapshot=snapshot).get("found"):
            return [whole]
        parts = [part.strip() for part in whole.split(",") if part.strip()]
        return list(dict.fromkeys(parts))[:4]
    return list(dict.fromkeys(values))[:4]


def _resolve_compare_names(store: Any, names: Sequence[str],
                           snapshot: Mapping[str, Any]) -> tuple[list[str], dict[str, str]]:
    """Swap Chinese company names for the English name the register holds.

    Measured: /compare?q=美敦力,捷迈 resolved neither, so a reader who typed two company names in
    Chinese got two "not found" columns and no comparison. The mapping is explicit data, and every
    substitution is reported back so the page can say which name it looked up - a silent swap would be
    worse than the failure it fixes.
    """
    from .aliases import lookup

    def exists(name: str) -> bool:
        """Is this a company the register knows? Two columns, not a dossier.

        This used to call _company_data, which builds the whole company view - brands, failures,
        trials, patents, papers, specialties, years. Measured on /compare?q=Bauerfeind,Medline: the
        resolve step called it 3 times and the render called it twice more, so two companies cost five
        dossiers and the cold page took 1.9 s instead of 0.8 s.
        """
        try:
            return store.conn.execute(
                "SELECT 1 FROM udi_company WHERE company_name = ? COLLATE NOCASE"
                " OR company_name LIKE ? LIMIT 1", (name, f"%{name}%")).fetchone() is not None
        except Exception:  # noqa: BLE001 - an absent register means "not found", same as before
            return False

    resolved: list[str] = []
    substitutions: dict[str, str] = {}
    for name in names:
        candidate = name
        if not exists(name):
            for hit in lookup(name):
                target = str(hit["search_as"])
                if exists(target):
                    candidate = target
                    substitutions[name] = target
                    break
        if candidate not in resolved:
            resolved.append(candidate)
    return resolved[:4], substitutions


def radar_page(*, feed: Mapping[str, Any], stats: Mapping[str, Any]) -> str:
    """A server-rendered front door for the live radar.

    /radar used to be the SPA alone: the server answered with an empty shell, so the page could not
    be linked into a summary, could not be read with JavaScript off, and had nothing to show if the
    bundle failed to load. This is the same data the app fetches, ordered for reading.

    The distinction the feed's own note makes is kept visible in the table: a NEW row from the
    INITIAL_DISCOVERY phase is a historical record that was already public when the source was
    switched on, not a new event. Printing both as "new" is the overstatement this product exists to
    avoid.
    """
    items = feed.get("items") or []

    def stamp(value: Any) -> str:
        return str(value or "")[:19].replace("T", " ")

    rows = []
    for item in items:
        phase = str(item.get("discovery_phase") or "")
        state = str(item.get("change_state") or "")
        first_seen = stamp(item.get("first_observed_at"))
        observed = stamp(item.get("observed_at"))
        # INITIAL_DISCOVERY is history, not news. Say so in the row itself.
        if phase == "INITIAL_DISCOVERY":
            when = (f'<span class="muted small">历史记录 · 首次开启时已公开</span><br>'
                    f'<span class="small muted">{esc(observed)}</span>')
        else:
            when = esc(observed)
        title = esc(str(item.get("title") or "")[:120])
        url = str(item.get("url") or "")
        link = (f'<a href="{esc(url)}" rel="noopener noreferrer nofollow">{title}</a>'
                if url.startswith(("http://", "https://")) else title)
        rows.append(
            f'<tr><td class="small">{when}</td>'
            f'<td class="small">{esc(str(item.get("source") or ""))}</td>'
            f'<td class="small">{esc(str(item.get("record_type") or ""))}</td>'
            f'<td>{link}</td>'
            f'<td class="small">{esc(state)}</td></tr>')

    body = f"""
<h1>实时雷达</h1>
<p class="lede">各追踪源最近观测到的变化。下面的表由服务端直出，不需要 JavaScript；
交互式视图在 <a href="/radar/live">/radar/live</a>。</p>
<div class="grid">
  <div class="stat"><b>{n(stats.get("observations"))}</b><span>观测总数</span></div>
  <div class="stat"><b>{n(stats.get("changes"))}</b><span>变化记录</span></div>
  <div class="stat"><b>{n(stats.get("sources"))}</b><span>在产出的源</span></div>
  <div class="stat"><b>{n(len(items))}</b><span>本页条数</span></div>
</div>
<div class="gap"><b>怎么读这张表：</b>「NEW」不都是新闻。首次开启某个源时回填的历史记录也会以 NEW 出现，
这类行标着<span class="muted">历史记录 · 首次开启时已公开</span>。只有不带这个标记的行才是我们观察到的变化。</div>
<div class="card"><table><thead><tr><th>观测时间</th><th>源</th><th>类型</th><th>标题</th>
<th>变化</th></tr></thead><tbody>{''.join(rows) or '<tr><td colspan="5" class="muted">还没有任何变化记录</td></tr>'}</tbody></table></div>
<p class="small muted">{esc(str(feed.get("note") or ""))}</p>
"""
    return layout(title="实时雷达 · MedRadar", body=body, active="feed")


#: The canonical request for each page, filled by pages_router() and used by warmup().
#
# Warming the data underneath a page is not the same as warming the page: every route returns
# `cached(key, ttl, render)` (rendered HTML), while warmup() called the builders. Measured cold after a
# restart: /compare 1.76 s, and the audit recorded the cause but not the fix. Calling the route functions
# themselves primes the entry the reader will ask for.
_PAGE_ROUTES: dict[str, Any] = {}

#: The field-page handler, registered by pages_router() so warmup() can prime every field.
#:
#: area_view is a local function inside pages_router, so warmup() could not see it: the first attempt
#: referenced it by name, raised NameError inside a try/except, and silently primed nothing - the fields
#: still cost about a second each on first visit.
_AREA_PRIMER: Any = None


def pages_router(service: Any, *, endpoints: Mapping[str, Any] | None = None) -> Any:
    """Reader-facing routes, mounted at the site root rather than under /api/radar.

    The workbench SPA keeps `/radar` and `/radar/technology-map`; these paths are the ones a person
    types or shares. Registered before the SPA catch-all, so a specific path wins.
    """
    from fastapi import APIRouter, Query
    from fastapi.responses import HTMLResponse

    from .device_view import build as build_view
    from .reference import UdiReference

    router = APIRouter()
    # Measured on the production store: the landing page counts 5.2M device rows and globs 40,731
    # corpus files (5.8 s), and one device dossier builds a todo list of clearances, failures,
    # trials, patents and papers (12.6 s). Neither number may change inside a few minutes, and a
    # reader who waits twelve seconds decides the tool is broken. Small in-process TTL cache, one
    # entry per key.
    cache: dict[str, tuple[float, str]] = {}

    def cached(key: str, ttl: float, render) -> str:
        hit = cache.get(key)
        now = time.time()
        if hit and now - hit[0] < ttl:
            return hit[1]
        page = render()
        cache[key] = (now, page)
        return page

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
        def render() -> str:
            examples = [("X1209255", "按 DI"), ("K213506", "按 K 号"),
                        ("Medtronic", "按公司"), ("Clydesdale", "按品牌")]
            store = _store()
            try:
                # Prefer the materialised counts: the paper count alone is a 360 ms scan over 785k
                # rows, and none of these numbers changes between two visits. The timestamp goes on
                # the page, because a cached number is a claim about the past.
                stored = _stored_counts(store) if store is not None else None
                if stored and stored.get("available"):
                    counts = stored["counts"]
                    stats = {
                        "设备注册": counts.get("devices", 0),
                        "批文语料": counts.get("corpus", 0),
                        "失效记录": counts.get("failures", 0),
                        "在研试验": counts.get("trials", 0),
                        "专利": counts.get("patents", 0),
                        "论文索引": counts.get("papers", 0),
                    }
                    return landing(stats=stats, examples=examples,
                                   counts_at=_relative_age(stored),
                                   data=_landing_literature(store))
                counts = _counts(store)
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
            finally:
                if store is not None:
                    store.close()
            # No timestamp: these were counted just now.
            return landing(stats=stats, examples=examples,
                           data=_landing_literature(store))

        return HTMLResponse(cached("home", 300.0, render))

    @router.get("/device", response_class=HTMLResponse)
    def device_page_view(query: str | None = Query(None, max_length=120),
                         limit: int = Query(25, ge=1, le=100)) -> Any:
        if not query:
            return HTMLResponse(landing(stats={"设备注册": 0}, examples=[]))

        def render() -> str:
            # A name query resolves up to `limit` devices and the dossier summarises them; 25 of
            # them costs 11 s cold (resolve 6.7 s + a paper history each, 4.4 s) to produce a page
            # that shows one head device, a summary row and a brand table. Ten is enough for that,
            # and an identifier query still gets the full allowance. Measured: 11 s -> 4 s cold.
            width = limit if any(ch.isdigit() for ch in query) else min(limit, 10)
            store = _store()
            if store is None:
                return layout(
                    title="设备库不存在 · MedRadar",
                    body=(f'<h1>这台部署没有设备库</h1>'
                          + gap_note("device_not_in_udi_register")),
                    active="device")
            corpus = service.paths.corpus
            timeline = build_view(store, query, limit=width, detail_for=1,
                                  corpus_root=corpus if corpus.is_dir() else None)
            # A Chinese company name used to dead-end: the page knew the mapping (it printed 试试：Medtronic
            # as a hint) and still said 没有找到. The register holds English legal names, so resolve through
            # the alias table and report the substitution, the same way /compare does.
            substituted_from = ""
            if not timeline.refs and _looks_chinese(query):
                try:
                    from .aliases import lookup

                    for hit in lookup(query):
                        target = str(hit.get("search_as") or "")
                        if not target:
                            continue
                        candidate = build_view(store, target, limit=width, detail_for=1,
                                               corpus_root=corpus if corpus.is_dir() else None)
                        if candidate.refs:
                            timeline = candidate
                            substituted_from = target
                            break
                except Exception:  # noqa: BLE001 - a failed alias lookup is the old behaviour
                    substituted_from = ""
            try:
                return device_dossier(timeline, query=query, store=store,
                                      substituted_from=substituted_from)
            finally:
                store.close()

        return HTMLResponse(cached(f"device:{query}:{limit}", 120.0, render))

    @router.get("/sources", response_class=HTMLResponse)
    def sources_view() -> Any:
        def render() -> str:
            store = _store()
            data: dict[str, Any] = {}
            try:
                if store is not None:
                    from .coverage import coverage as build_coverage

                    data = build_coverage(store, corpus_dir=service.paths.corpus, service=service)
            finally:
                if store is not None:
                    store.close()
            meta: dict[str, Any] = {"sources": []}
            try:
                payload = service.meta() if hasattr(service, "meta") else None
                if isinstance(payload, Mapping):
                    meta["sources"] = payload.get("sources") or []
            except Exception:  # noqa: BLE001 - the coverage page must render even if meta fails
                meta["sources"] = []
            # What the last nightly run did, so a step that silently did nothing is visible here.
            try:
                from .nightly import summary_for_page

                data = dict(data or {})
                data["nightly"] = summary_for_page(getattr(service.paths, "radar", None))
            except Exception:  # noqa: BLE001 - a missing ledger is not a page failure
                pass
            # The tunnel's own state, from the files its shell script writes. Absent files are reported
            # as a gap, not as an empty address.
            try:
                from .tunnel import state as tunnel_state

                # The service does not carry the radar directory on `paths`; it resolves it once at
                # startup and exposes it to the app. Asking `paths` returned nothing and the page
                # printed the "tunnel not started" gap while the tunnel was running.
                radar_dir = getattr(service, "radar_dir", None) or os.environ.get("MEDRADAR_RADAR_DIR")
                tunnel = (tunnel_state(Path(str(radar_dir)) / "public_url.txt",
                                       Path(str(radar_dir)) / "public_url_history.tsv")
                          if radar_dir else {"available": False})
            except Exception:  # noqa: BLE001 - the coverage page renders without it
                tunnel = {"available": False}
            return sources_page(meta=meta, coverage=data, tunnel=tunnel)

        return HTMLResponse(cached("sources", 300.0, render))

    def _snapshot() -> Mapping[str, Any]:
        path = Path(str(getattr(service.paths, "root", ""))) / "map_page.json"
        if not path.is_file():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return payload if isinstance(payload, Mapping) else {}

    @router.get("/topic", response_class=HTMLResponse)
    def topic_view(id: str | None = Query(None, max_length=80)) -> Any:
        if not id:
            return HTMLResponse(layout(
                title="科技地图 · MedRadar",
                body='<h1>缺少主题 id</h1><p><a href="/map">← 科技地图</a></p>', active="map"))

        def render() -> str:
            payload = _snapshot()
            topic = next((t for t in (payload.get("topics") or [])
                          if str(t.get("topic_id")) == id), None)
            literature: dict[str, Any] = {}
            store = _store()
            if topic is not None and store is not None:
                try:
                    from .papers_index import distinctive_terms, papers_for_tokens, tokens

                    # The topic's own words, filtered for distinctiveness exactly like the device page
                    # does: a word shared by thousands of papers points at nothing.
                    words = tokens(" ".join([str(topic.get("label_en") or ""),
                                             str(topic.get("description") or "")]))
                    kept, _dropped = distinctive_terms(store, words)
                    found = papers_for_tokens(store, kept[:8], limit=5) or {}
                    recent = [dict(item) for item in (found.get("recent") or [])]
                    from .paper_passes import dates_for

                    dates = dates_for(store, [str(item.get("paper_id") or "") for item in recent])
                    for item in recent:
                        item.setdefault("published_at", dates.get(str(item.get("paper_id") or ""), ""))
                    # The heading promises "最近发表的" and the index returns matches by mention count.
                    # Measured: the table read 2026-11-18, 2026-05-10, 2026-08-01 under a heading that
                    # said newest first. Sort the claim to match the word.
                    recent.sort(key=lambda item: str(item.get("published_at") or ""), reverse=True)
                    literature = {"terms": kept[:8], "papers": recent}
                except Exception:  # noqa: BLE001 - no literature is a stated gap, not a failure
                    literature = {}
                finally:
                    store.close()
            elif store is not None:
                store.close()
            return topic_page(payload=payload, topic_id=id, data=literature)

        return HTMLResponse(cached(f"topic:{id}", 300.0, render))

    @router.get("/company", response_class=HTMLResponse)
    def company_view(q: str | None = Query(None, max_length=120)) -> Any:
        if not q:
            return HTMLResponse(layout(
                title="公司 · MedRadar",
                body='<h1>缺少公司名</h1><p><a href="/">← 查询</a></p>', active="company"))

        def render() -> str:
            store = _store()
            if store is None:
                return layout(title="设备库不存在 · MedRadar",
                              body=gap_note("device_not_in_udi_register"), active="company")
            try:
                data = _company_data(store, q, snapshot=_snapshot())
            finally:
                store.close()
            return company_page(data=data)

        return HTMLResponse(cached(f"company:{q}", 300.0, render))

    @router.get("/compare", response_class=HTMLResponse)
    def compare_view(q: list[str] | None = Query(None)) -> Any:
        raw = [str(value) for value in (q or []) if str(value).strip()]
        if not raw:
            return HTMLResponse(layout(
                title="公司对比 · MedRadar",
                body=('<h1>公司对比</h1>'
                      '<p class="lede">用逗号分隔两到四家公司，例如 '
                      '<a href="/compare?q=Medtronic,Bauerfeind">Medtronic,Bauerfeind</a>。</p>'
                      '<form class="search" method="get" action="/compare">'
                      '<input type="search" name="q" placeholder="公司A, 公司B" aria-label="对比">'
                      '<button type="submit">对比</button></form>'),
                active="company"))
        key = "|".join(raw)

        def render() -> str:
            store = _store()
            if store is None:
                return layout(title="设备库不存在 · MedRadar",
                              body=gap_note("device_not_in_udi_register"), active="company")
            snapshot = _snapshot()
            field_recency: dict[str, Any] = {}
            try:
                names = _compare_names(store, raw, snapshot)
                names, substitutions = _resolve_compare_names(store, names, snapshot)
                data = [_company_data(store, name, snapshot=snapshot) for name in names]
                # The literature-activity column needs the per-field recency map; 5 ms, computed here
                # rather than inside the page so the page stays a pure function of its data.
                from .paper_passes import recency_by_specialty

                field_recency = recency_by_specialty(store)
            finally:
                store.close()
            return compare_page(companies=data, substitutions=substitutions,
                                data_recency=field_recency)

        return HTMLResponse(cached(f"compare:{key}", 300.0, render))

    @router.get("/download")
    def download(q: str = Query("", max_length=240),
                 name: str = Query("", max_length=120),
                 kind: str = Query("device",
                          pattern="^(device|compare|areas|area|area_failures|company|papers)$"),
                 format: str = Query("md", pattern="^(md|csv|json)$")) -> Any:
        """One dossier, one comparison, the whole field map, or one specialty - as a file.

        A reader who has to send the answer onward was previously limited to a screenshot, which
        carries no source and cannot be checked. The exporters live in export.py and follow the same
        rules as the pages: every section names its source, every absence carries its reason code,
        and a weaker match keeps its label. /areas and /area were view-only until audit 02 listed
        them; the caveats travel with them for the same reason.
        """
        from fastapi.responses import Response

        from . import export as export_mod

        if kind in {"device", "compare", "company"} and not q:
            return HTMLResponse(layout(title="缺少查询词 · MedRadar",
                                       body=gap_note("no_data"), active="device"),
                                status_code=400)
        if kind in {"area", "papers"} and not name:
            return HTMLResponse(layout(title="缺少技术领域 · MedRadar",
                                       body=gap_note("no_data"), active="areas"),
                                status_code=400)

        store = _store()
        if store is None:
            return HTMLResponse(layout(title="设备库不存在 · MedRadar",
                                       body=gap_note("device_not_in_udi_register"),
                                       active="device"), status_code=503)
        try:
            if kind == "areas":
                from .specialty import read as read_specialties

                data = read_specialties(store)
                items = data.get("items") or []
                try:
                    from .paper_passes import recency_by_specialty

                    data["recency"] = recency_by_specialty(store)
                except Exception:  # noqa: BLE001 - no literature is an empty column, not a broken page
                    data["recency"] = {}
                # The recency column travels with the file: the page can show it, so the export must.
                try:
                    from .paper_passes import recency_by_specialty

                    recency = recency_by_specialty(store)
                except Exception:  # noqa: BLE001 - an empty column, not a failed export
                    recency = {}
                if format == "csv":
                    body = export_mod.areas_csv(items, recency=recency)
                    media, suffix = "text/csv; charset=utf-8", "csv"
                elif format == "json":
                    body = export_mod.areas_json(items, updated_at=data.get("updated_at"),
                                                 recency=recency)
                    media, suffix = "application/json; charset=utf-8", "json"
                else:
                    body = export_mod.areas_markdown(items, updated_at=data.get("updated_at"),
                                                     recency=recency)
                    media, suffix = "text/markdown; charset=utf-8", "md"
                stem = "medradar-areas"
            elif kind == "area":
                from .specialty import companies_in_specialty, one

                summary = one(store, name) or {}
                companies = companies_in_specialty(store, name)
                # The failure record goes into the export too: the page has carried it since round 71,
                # and a document that omits it would report a field without its reports.
                try:
                    from .specialty import failure_shape as read_failures

                    failures = read_failures(store, name)
                except Exception:  # noqa: BLE001 - no failure index is a stated gap
                    failures = {}
                # The monthly shape comes along so a JSON consumer sees the same series the page draws.
                try:
                    from .paper_passes import field_topics as read_topics, monthly_counts

                    monthly = monthly_counts(store, name)
                    field_topics = read_topics(store, name)
                except Exception:  # noqa: BLE001 - no literature yet is a stated gap
                    monthly = []
                    field_topics = []
                if format == "csv":
                    body = export_mod.area_csv(companies)
                    media, suffix = "text/csv; charset=utf-8", "csv"
                elif format == "json":
                    body = export_mod.area_json(name, summary, companies,
                                                failures=failures, monthly=monthly,
                                                topics=field_topics)
                    media, suffix = "application/json; charset=utf-8", "json"
                else:
                    body = export_mod.area_markdown(name, summary, companies, failures=failures,
                                                    topics=field_topics)
                    media, suffix = "text/markdown; charset=utf-8", "md"
                stem = f"medradar-area-{_slug(name)}"
            elif kind == "area_failures":
                # Its own file: a CSV holds one table, and the caveats live in the JSON's bounds.
                from .specialty import failure_shape as read_failures

                failures = read_failures(store, name)
                if format == "json":
                    body = export_mod.area_failures_json(name, failures)
                    media, suffix = "application/json; charset=utf-8", "json"
                else:
                    body = export_mod.area_failures_csv(name, failures)
                    media, suffix = "text/csv; charset=utf-8", "csv"
                stem = f"medradar-area-failures-{_slug(name)}"
            elif kind == "papers":
                from .paper_passes import papers_for, recent_for

                held = len(papers_for(store, name))
                items = recent_for(store, name, limit=60)
                if format == "csv":
                    body = export_mod.field_papers_csv(items)
                    media, suffix = "text/csv; charset=utf-8", "csv"
                elif format == "json":
                    body = export_mod.field_papers_json(name, items, held=held)
                    media, suffix = "application/json; charset=utf-8", "json"
                else:
                    body = export_mod.field_papers_markdown(name, items, held=held)
                    media, suffix = "text/markdown; charset=utf-8", "md"
                stem = f"medradar-papers-{_slug(name)}"
            elif kind == "company":
                snapshot = _snapshot()
                data = _company_data(store, q, snapshot=snapshot)
                if format == "csv":
                    body = export_mod.company_csv(data)
                    media, suffix = "text/csv; charset=utf-8", "csv"
                elif format == "json":
                    body = export_mod.company_json(data)
                    media, suffix = "application/json; charset=utf-8", "json"
                else:
                    body = export_mod.company_markdown(data)
                    media, suffix = "text/markdown; charset=utf-8", "md"
                stem = f"medradar-company-{_slug(str(data.get('company_name') or q))}"
            elif kind == "device":
                corpus = service.paths.corpus
                timeline = build_view(store, q, limit=25,
                                      corpus_root=corpus if corpus.is_dir() else None)
                shelf: dict[str, int] = {}
                try:
                    from .code_census import product_code_census

                    shelf = product_code_census(store)
                except Exception:  # noqa: BLE001 - no census is a line fewer, not a failed export
                    shelf = {}
                if format == "md":
                    body = export_mod.device_markdown(timeline, query=q, shelf=shelf)
                    media, suffix = "text/markdown; charset=utf-8", "md"
                elif format == "csv":
                    body = export_mod.device_csv(timeline, query=q, shelf=shelf)
                    media, suffix = "text/csv; charset=utf-8", "csv"
                else:
                    body = export_mod.device_json(timeline, query=q)
                    media, suffix = "application/json; charset=utf-8", "json"
                stem = f"medradar-device-{_slug(q)}"
            else:
                names = [part.strip() for part in q.split(",") if part.strip()][:4]
                snapshot = _snapshot()
                data = [_company_data(store, company_name, snapshot=snapshot)
                        for company_name in names]
                if format == "md":
                    body = export_mod.compare_markdown(data)
                    media, suffix = "text/markdown; charset=utf-8", "md"
                elif format == "csv":
                    body = export_mod.compare_csv(data)
                    media, suffix = "text/csv; charset=utf-8", "csv"
                else:
                    # A plain dump of the internal dicts shipped every field including the ones the page
                    # deliberately keeps apart. The envelope names the schema and separates the
                    # name-matched block, so a consumer cannot merge it into the hard numbers by accident.
                    body = export_mod.compare_json(data)
                    media, suffix = "application/json; charset=utf-8", "json"
                stem = f"medradar-compare-{_slug('-'.join(names))}"
        finally:
            store.close()
        return Response(
            content=body,
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="{stem}.{suffix}"',
                     "X-Robots-Tag": "noindex, nofollow"},
        )

    @router.get("/paper", response_class=HTMLResponse)
    def paper_view(id: str | None = Query(None, max_length=80)) -> Any:
        if not id:
            return HTMLResponse(layout(
                title="论文 · MedRadar",
                body=('<h1>论文反查</h1><p class="lede">输入论文编号，例如 '
                      '<a href="/paper?id=PMC13713206">PMC13713206</a>。</p>'
                      '<form class="search" method="get" action="/paper">'
                      '<input type="search" name="id" placeholder="PMC13713206" aria-label="论文编号">'
                      '<button type="submit">反查</button></form>'),
                active="device"))

        def render() -> str:
            from .papers_index import (brands_for_terms, distinctive_terms, paper_record,
                                       paper_terms)

            store = _store()
            if store is None:
                return layout(title="设备库不存在 · MedRadar",
                              body=gap_note("device_index_absent"), active="device")
            try:
                record = paper_record(store, id)
                # Not an identifier: try the title. Measured 6 ms over 5,485 titles.
                title_matches = []
                if record is None:
                    from .papers_index import search_paper_titles

                    title_matches = search_paper_titles(store, id)
                # The same cross-field rule the field pages use: a word that appears in ten or more of
                # the twenty fields says nothing about this paper either. Measured on PMC13788955: the
                # list led with implants, prosthetic, children, bone, growth, treatment, years, clinical.
                try:
                    from .papers_index import is_generic, term_field_spread

                    spread = term_field_spread(store)
                    terms = [item for item in paper_terms(store, id, limit=120)
                             if not is_generic(str(item["term"]), spread)][:24]
                except Exception:  # noqa: BLE001 - the unfiltered list is the old behaviour
                    terms = paper_terms(store, id, limit=60)
                # Only words that can name a product: a paper is indexed under "with" and "the" too,
                # and every brand would share those.
                kept, _generic = distinctive_terms(store, [t["term"] for t in terms])
                brands = brands_for_terms(store, kept, limit=30)
                suggestions = [str(r[0]) for r in store.conn.execute(
                    "SELECT DISTINCT paper_id FROM paper_term ORDER BY paper_id LIMIT 4")]
            finally:
                store.close()
            return paper_page(record=record, terms=terms, brands=brands, paper_id=id,
                              suggestions=suggestions, title_matches=title_matches)

        return HTMLResponse(cached(f"paper:{id}", 300.0, render))

    @router.get("/areas", response_class=HTMLResponse)
    def areas_view(sort: str = Query("devices", max_length=16)) -> Any:
        # Sorting is the answer to "which field do I look at first", and the three orders answer three
        # different questions: biggest, most researched, and not researched at all.
        order = sort if sort in ("devices", "papers", "pending", "companies", "recent") else "devices"

        def render() -> str:
            store = _store()
            if store is None:
                return layout(title="技术领域 · MedRadar",
                              body=gap_note("device_index_absent"), active="areas")
            try:
                from .specialty import read as read_specialties

                data = dict(read_specialties(store))
                # The order has to travel inside the data: areas_page reads data["sort"], and without this
                # the tab highlighted 按近 90 天占比 while the table stayed in register order.
                data["sort"] = order
                # Same for the recency column. This is computed here, in the page's own render, not in the
                # download branch - the first attempt put it there and every cell rendered as a dash.
                try:
                    from .paper_passes import recency_by_specialty

                    data["recency"] = recency_by_specialty(store)
                except Exception:  # noqa: BLE001 - an empty column, not a broken page
                    data["recency"] = {}
                if not data.get("available"):
                    data["gap"] = "specialty_stats_absent"
                # What the literature lane has actually done per field. Empty is a legitimate answer
                # and the page distinguishes "never crawled" from "crawled, nothing new".
                try:
                    from .paper_passes import by_specialty

                    data["literature"] = by_specialty(store)
                except Exception:  # noqa: BLE001 - no paper_pass table yet
                    data["literature"] = {}
            except Exception:  # noqa: BLE001 - an absent table is a gap, not a crash
                data = {"available": False, "items": [], "updated_at": None,
                        "gap": "specialty_stats_absent"}
            finally:
                store.close()
            data["sort"] = order
            return areas_page(data=data)

        return HTMLResponse(cached(f"areas:{order}", 300.0, render))

    @router.get("/area", response_class=HTMLResponse)
    def area_view(name: str | None = Query(None, max_length=120)) -> Any:
        if not name:
            return HTMLResponse(layout(
                title="技术领域 · MedRadar",
                body=('<h1>技术领域</h1><p class="lede">从 '
                      '<a href="/areas">全部技术领域</a> 选一个。</p>'),
                active="areas"))

        def render() -> str:
            store = _store()
            if store is None:
                return layout(title="设备库不存在 · MedRadar",
                              body=gap_note("device_index_absent"), active="areas")
            try:
                from .specialty import companies_in_specialty, one

                summary = one(store, name)
                # `name` comes from the query string and must stay read-only here: assigning to it
                # inside this closure made it a local and raised UnboundLocalError on the first read.
                resolved_name = name
                resolved_from = ""
                if summary is None:
                    # A Chinese field name is a different spelling of a field we hold, not a missing
                    # field. Resolve it explicitly rather than only telling the reader to retype - and
                    # say on the page which name was used, so nothing changes silently.
                    from .aliases import lookup_specialty

                    hits = lookup_specialty(name)
                    if hits:
                        mapped = hits[0]["specialty"]
                        candidate = one(store, mapped)
                        if candidate is not None:
                            summary, resolved_from, resolved_name = candidate, str(name), mapped
                companies = companies_in_specialty(store, resolved_name) if summary else []
                field_topics: list[dict[str, Any]] = []
                field_papers: list[str] = []
                field_recent: list[dict[str, Any]] = []
                field_monthly: list[dict[str, Any]] = []
                field_failures: dict[str, Any] = {}
                if summary:
                    try:
                        from .paper_passes import field_topics as read_topics, papers_for

                        field_papers = papers_for(store, resolved_name)
                        field_topics = read_topics(store, resolved_name, limit=12)
                        from .paper_passes import monthly_counts, recent_for

                        field_recent = recent_for(store, resolved_name, limit=10)
                        field_monthly = monthly_counts(store, resolved_name)
                    except Exception:  # noqa: BLE001 - no literature yet is a stated gap
                        field_topics, field_papers, field_monthly, field_recent = [], [], [], []
                    # Reports are independent of the literature: a field with no papers still has a
                    # failure record, so this is computed outside the literature try.
                    try:
                        from .specialty import failure_shape

                        field_failures = failure_shape(store, resolved_name)
                    except Exception:  # noqa: BLE001 - no failure index is a stated gap
                        field_failures = {}
                    # The same measure /areas sorts by, computed once per field page (5 ms).
                    field_recency: dict[str, Any] = {}
                    try:
                        from .paper_passes import field_coverage, recency_by_specialty

                        field_recency = recency_by_specialty(store).get(resolved_name) or {}
                        # How much of the corpus the field pages speak for at all: audit 09 asked for it.
                        literature_coverage = field_coverage(store)
                    except Exception:  # noqa: BLE001 - no literature is an empty note
                        field_recency = {}
                        literature_coverage = {}
            finally:
                store.close()
            return area_page(specialty=resolved_name, summary=summary, companies=companies,
                             data={"field_topics": field_topics, "field_papers": field_papers,
                                   "field_recent": field_recent, "field_monthly": field_monthly,
                                   "field_failures": field_failures,
                                   "field_recency": field_recency,
                                   "literature_coverage": literature_coverage,
                                   "resolved_from": resolved_from})

        return HTMLResponse(cached(f"area:{name}", 300.0, render))

    @router.get("/radar", response_class=HTMLResponse)
    def radar_view() -> Any:
        def render() -> str:
            feed: dict[str, Any] = {"items": [], "note": ""}
            stats: dict[str, Any] = {}
            try:
                from .health import change_stream

                with service.ledger() as ledger:
                    feed = change_stream(ledger, limit=40)
                    stats["observations"] = int(
                        ledger.raw("SELECT COUNT(*) AS n FROM observation")[0]["n"] or 0)
                    stats["changes"] = int(ledger.raw(
                        "SELECT COUNT(*) AS n FROM observation_change "
                        "WHERE change_state IN ('NEW','UPDATED','REMOVED_OR_UNAVAILABLE')"
                    )[0]["n"] or 0)
                    stats["sources"] = int(ledger.raw(
                        "SELECT COUNT(DISTINCT source) AS n FROM observation_change"
                    )[0]["n"] or 0)
            except Exception as error:  # noqa: BLE001 - no ledger is a state, and the page says so
                feed = {"items": [], "note": f"读不到雷达台账：{type(error).__name__}"}
            return radar_page(feed=feed, stats=stats)

        # 60 s was shorter than the thing it caches: the scheduler cycle is 300 s, so the feed could not
        # change between two refresh intervals, and priming it at startup was wasted - measured /radar at
        # 1.06 s a hundred seconds after a restart, i.e. after its own warm entry had expired.
        return HTMLResponse(cached("radar", 300.0, render))

    @router.get("/map", response_class=HTMLResponse)
    def map_view() -> Any:
        # Served from a snapshot, not computed per request. Measured: the live call walks 122k nodes
        # and 107k edges and took longer than two minutes cold, and the answer cannot change faster
        # than the 300-second scheduler cycle anyway. tools/build_map.py writes the snapshot; the
        # nightly job refreshes it. An absent snapshot says so, and says what to run.
        snapshot = Path(str(getattr(service.paths, "root", ""))) / "map_page.json"
        if not snapshot.is_file():
            return HTMLResponse(layout(
                title="科技地图 · MedRadar",
                body=('<h1>科技地图还没有生成</h1>'
                      + gap_note("technology_map_unavailable",
                                 extra='<p class="small muted">运行 '
                                       '<code>tools/build_map.py</code> 生成快照；'
                                       '夜间任务也会刷新。</p>')),
                active="map"), status_code=503)
        try:
            payload = json.loads(snapshot.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            return HTMLResponse(layout(
                title="科技地图 · MedRadar",
                body=('<h1>科技地图快照读取失败</h1>'
                      + gap_note("technology_map_unavailable",
                                 extra=f'<span class="small muted">{esc(str(error)[:200])}</span>')),
                active="map"), status_code=503)
        return HTMLResponse(map_page(payload=payload if isinstance(payload, Mapping) else {}))

    # Canonical requests, in the order a first reader is likely to need them. Each one goes through
    # cached(), so the page is rendered once at startup instead of on the first click.
    # Only the pages that are expensive cold. Measured on the 2-vCPU box: priming all seven made the
    # first requests *slower* (compare 4.6 s, radar 3.9 s) because the warm-up thread was competing with
    # them for both cores. home, areas and map answer in 0.27-0.39 s cold and need nothing.
    global _AREA_PRIMER
    _AREA_PRIMER = area_view
    _PAGE_ROUTES.clear()
    _PAGE_ROUTES.update({
        "sources": lambda: sources_view(),
        "radar": lambda: radar_view(),
        "company": lambda: company_view("Medtronic"),
        # The cache key is built from the raw q values, so the priming call must use the shape a browser
        # sends: one comma-separated string. Passing two list items produced the key "Medtronic|Stryker"
        # while the page asks for "Medtronic,Stryker" - primed under a name nobody requests.
        "compare": lambda: compare_view(["Medtronic,Stryker"]),
    })

    return router


__all__ = ["CSS", "device_dossier", "esc", "gap_note", "landing", "layout", "map_page",
           "pages_router", "sources_page"]
