#!/usr/bin/env python3
"""Generate the versioned MedRadar platform-architecture diagrams.

Outputs (deterministic, stdlib only):

    docs/assets/architecture/architecture-en-light.svg
    docs/assets/architecture/architecture-en-dark.svg
    docs/assets/architecture/architecture-zh-light.svg
    docs/assets/architecture/architecture-zh-dark.svg

Content is a fixed inventory of what exists on ``main`` (after the REFOUNDATION-003
integration) versus what is a labelled draft. The status vocabulary is the same one
used in ``README.md`` and the site: implemented / limited / draft. Nothing here is a
claim about runtime behaviour; it is a map of code that is in the repository.

Run:  python tools/homepage/build_architecture.py          # write files
      python tools/homepage/build_architecture.py --check   # exit 1 if stale
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "assets" / "architecture"

W, H = 1000, 590
MARGIN = 24
COL_W = 214
GAP = 26

THEMES = {
    "light": {
        "bg": "#FFFFFF",
        "panel": "#FBFCFE",
        "panel_alt": "#F5F8FC",
        "ink": "#0B1220",
        "ink2": "#334155",
        "ink3": "#64748B",
        "line": "#E3E9F1",
        "line_strong": "#CBD5E1",
        "accent": "#2B7FC4",
        "accent_soft": "#EAF3FA",
        "warn": "#A9762A",
        "warn_soft": "#FBF3E5",
        "draft": "#7C8CA1",
        "draft_soft": "#F3F5F9",
        "grid": "rgba(43,127,196,0.05)",
    },
    "dark": {
        "bg": "#0B1730",
        "panel": "#101F3A",
        "panel_alt": "#0E1B33",
        "ink": "#E8F0F8",
        "ink2": "#B9CBDE",
        "ink3": "#8CA2B8",
        "line": "rgba(126,164,204,0.20)",
        "line_strong": "rgba(126,164,204,0.38)",
        "accent": "#6FB6E8",
        "accent_soft": "rgba(111,182,232,0.12)",
        "warn": "#D9A552",
        "warn_soft": "rgba(217,165,82,0.10)",
        "draft": "#8CA2B8",
        "draft_soft": "rgba(140,162,184,0.08)",
        "grid": "rgba(111,182,232,0.05)",
    },
}

TEXT = {
    "en": {
        "title": "MedRadar platform architecture",
        "subtitle": "Solid rows ship on main and are exercised by the offline suite. "
        "Dashed is a labelled draft, not wired to the live site.",
        "columns": [
            "01 \u00b7 Public sources",
            "02 \u00b7 Evidence infrastructure",
            "03 \u00b7 Research engine",
            "04 \u00b7 Intelligence & applications",
        ],
        "sources": [
            ("openFDA device", "510(k) \u00b7 PMA \u00b7 recall \u00b7 classification", "ok"),
            ("openFDA drug", "drugsfda approvals", "ok"),
            ("ClinicalTrials.gov v2", "trial registrations and results", "ok"),
            ("SEC EDGAR 8-K", "full-text corporate filings", "ok"),
            ("FDA AdCom calendar", "experimental adapter, 0 rows parsed", "ltd"),
            ("NMPA China", "manual CSV adapter only, never scraped", "ltd"),
        ],
        "infra": [
            ("HTTP client", "rate limit \u00b7 retries \u00b7 disk cache", "ok"),
            ("Event store", "SQLite events \u00b7 event_date \u00b7 available_at", "ok"),
            ("Revision ledger", "append-only write path; not tamper-proofing", "ltd"),
            ("Registries", "company \u00b7 subsidiary \u00b7 track \u00b7 product code", "ltd"),
            ("Bitemporal TKG", "valid time vs knowledge time; mechanism only", "ltd"),
            ("Forecast registry", "append-only, as-of scoring; 0 matured", "ltd"),
        ],
        "engine": [
            ("Track heat \u00b7 mix shift \u00b7 novelty", "descriptive, in-sample scores", "ltd"),
            ("Event study \u00b7 replay", "simulated long-only book", "ltd"),
            ("Statistics", "block bootstrap \u00b7 Holm correction", "ok"),
            ("Research agent", "cited retrieval, no free generation", "ok"),
            ("Frozen experiments", "reverse-R&D \u00b7 E1b \u00b7 early-signal study", "ok"),
        ],
        "apps": [
            ("Weekly report (zh/en)", "generated artefacts, metrics.json contract", "ok"),
            ("Interactive dashboard", "zero-dependency single HTML file", "ok"),
            ("GitHub Pages", "built from docs/; not a live service", "ok"),
        ],
        "draft_title": "NOT ON MAIN \u00b7 DRAFT",
        "draft_note": "labelled open PRs, not served by the live site",
        "draft_items": [
            "MedRadar 2.0 #12",
            "Live Observatory #13/#14",
            "S-028 / S-029 #15/#16",
            "PHOENIX #23\u2013#26",
            "ATLAS \u00b7 HORIZON \u00b7",
            "CONVERGENCE #27\u2013#30",
        ],
        "not_wired": "not wired",
        "legend": [
            ("ok", "Implemented", "exercised by the 1,160-test offline suite"),
            ("ltd", "Limited", "works, with a named and measured gap"),
            ("draft", "Draft", "open PR or branch, not on main"),
        ],
        "footnote": "Left to right: ingest \u2192 normalise \u2192 test \u2192 publish. "
        "Data snapshot 2026-10-31 \u00b7 375,378 events \u00b7 sources: docs/INDEX.md, PROJECT_STATE.yaml",
    },
    "zh": {
        "title": "MedRadar 平台架构",
        "subtitle": "实线为 main 上已实现、并由离线测试覆盖的模块；虚线是标注清楚的 Draft，未接入线上站点。",
        "columns": [
            "01 \u00b7 公开数据源",
            "02 \u00b7 证据基础设施",
            "03 \u00b7 研究引擎",
            "04 \u00b7 智能与应用",
        ],
        "sources": [
            ("openFDA 器械", "510(k) \u00b7 PMA \u00b7 召回 \u00b7 分类", "ok"),
            ("openFDA 药品", "drugsfda 批准记录", "ok"),
            ("ClinicalTrials.gov v2", "临床试验注册与结果", "ok"),
            ("SEC EDGAR 8-K", "公司披露全文", "ok"),
            ("FDA AdCom 日历", "实验性适配器，解析 0 行", "ltd"),
            ("NMPA 中国", "仅手动 CSV 适配器，不抓取", "ltd"),
        ],
        "infra": [
            ("HTTP 客户端", "限速 \u00b7 重试 \u00b7 磁盘缓存", "ok"),
            ("事件库", "SQLite events \u00b7 event_date \u00b7 available_at", "ok"),
            ("修订账本", "仅应用写入路径，非防篡改", "ltd"),
            ("实体注册表", "公司 \u00b7 子公司 \u00b7 赛道 \u00b7 产品码", "ltd"),
            ("双时相 TKG", "有效时间 vs 知识时间；仅机制", "ltd"),
            ("预测注册表", "追加式、as-of 评分；0 条到期", "ltd"),
        ],
        "engine": [
            ("赛道热度 \u00b7 结构迁移 \u00b7 新颖度", "描述性、样本内打分", "ltd"),
            ("事件研究 \u00b7 回放", "模拟多头组合", "ltd"),
            ("统计方法", "分块 bootstrap \u00b7 Holm 校正", "ok"),
            ("研究代理", "引用式检索，不做自由生成", "ok"),
            ("冻结实验", "reverse-R&D \u00b7 E1b \u00b7 早期信号研究", "ok"),
        ],
        "apps": [
            ("周报（中/英）", "生成物，metrics.json 数据契约", "ok"),
            ("交互看板", "零依赖单文件 HTML", "ok"),
            ("GitHub Pages", "由 docs/ 构建；不是实时服务", "ok"),
        ],
        "draft_title": "未进入 MAIN \u00b7 DRAFT",
        "draft_note": "已标注的开放 PR，线上站点不提供",
        "draft_items": [
            "MedRadar 2.0 #12",
            "Live Observatory #13/#14",
            "S-028 / S-029 #15/#16",
            "PHOENIX #23\u2013#26",
            "ATLAS \u00b7 HORIZON \u00b7",
            "CONVERGENCE #27\u2013#30",
        ],
        "not_wired": "未接入",
        "legend": [
            ("ok", "已实现", "由 1,160 项离线测试覆盖"),
            ("ltd", "有限", "可用，但有明确且可度量的缺口"),
            ("draft", "草案", "开放 PR 或分支，不在 main"),
        ],
        "footnote": "从左到右：采集 \u2192 归一 \u2192 检验 \u2192 发布。数据快照 2026-10-31 \u00b7 "
        "375,378 条事件 \u00b7 来源：docs/INDEX.md、PROJECT_STATE.yaml",
    },
}

# --------------------------------------------------------------------------- helpers
def esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def estimate_width(text: str, size: float) -> float:
    """Rough advance width: CJK ~1.0em, narrow latin ~0.30em, digits/caps ~0.60em."""
    total = 0.0
    for ch in text:
        code = ord(ch)
        if code >= 0x2E80:
            total += size * 1.02
        elif ch in "iljtfr.,:;'()|![] ":
            total += size * 0.29
        elif ch.isupper() or ch.isdigit():
            total += size * 0.60
        else:
            total += size * 0.50
    return total


def wrap(text: str, size: float, width: float, max_lines: int = 2) -> list[str]:
    """Wrap on word boundaries (CJK falls back to characters) into at most max_lines."""
    words = text.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else current + " " + word
        if estimate_width(candidate, size) <= width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        head = lines[: max_lines - 1]
        tail = " ".join(lines[max_lines - 1 :])
        head.append(fit(tail, size, width))
        return head
    return lines


def fit(text: str, size: float, width: float) -> str:
    """Clip with an ellipsis when the estimate would overflow the available width."""
    if estimate_width(text, size) <= width:
        return text
    while text and estimate_width(text + "\u2026", size) > width:
        text = text[:-1]
    return text.rstrip() + "\u2026"


def status_dot(x: float, y: float, status: str, theme: dict) -> str:
    """Non-colour-only status marks: solid disc / half disc / dashed ring."""
    if status == "ok":
        color = theme["accent"]
        return (
            f'<circle cx="{x}" cy="{y}" r="4.6" fill="{color}"/>'
            f'<circle cx="{x}" cy="{y}" r="7.2" fill="none" stroke="{color}" stroke-opacity=".28" stroke-width="1"/>'
        )
    if status == "ltd":
        color = theme["warn"]
        return (
            f'<circle cx="{x}" cy="{y}" r="5.2" fill="none" stroke="{color}" stroke-width="1.5"/>'
            f'<path d="M {x} {y - 5.2} A 5.2 5.2 0 0 1 {x} {y + 5.2} Z" fill="{color}"/>'
        )
    color = theme["draft"]
    return (
        f'<circle cx="{x}" cy="{y}" r="5.2" fill="none" stroke="{color}" stroke-width="1.4" '
        f'stroke-dasharray="2.6 2.2"/>'
    )


def row(
    x: float,
    y: float,
    w: float,
    title: str,
    meta: str,
    status: str,
    theme: dict,
) -> str:
    h = 56
    fill = theme["panel"]
    stroke = theme["line"]
    if status == "ltd":
        stroke = theme["line_strong"]
    parts = [
        f'<g><title>{esc(title)} \u2014 {esc(meta)} ({status})</title>',
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" stroke="{stroke}"/>',
    ]
    if status != "ok":
        accent = theme["warn"] if status == "ltd" else theme["draft"]
        parts.append(
            f'<rect x="{x}" y="{y + 10}" width="2" height="{h - 20}" rx="1" fill="{accent}" opacity=".65"/>'
        )
    parts.append(status_dot(x + 15, y + 19, status, theme))
    parts.append(
        f'<text x="{x + 27}" y="{y + 23}" font-size="12.5" font-weight="600" fill="{theme["ink"]}">'
        f"{esc(fit(title, 12.5, w - 38))}</text>"
    )
    meta_lines = wrap(meta, 9.7, w - 38, max_lines=2)
    for i, line in enumerate(meta_lines):
        parts.append(
            f'<text x="{x + 27}" y="{y + 39 + i * 12.5}" font-size="9.7" fill="{theme["ink3"]}">'
            f"{esc(line)}</text>"
        )
    parts.append("</g>")
    return "".join(parts)


def arrow(x1: float, y: float, x2: float, color: str) -> str:
    mid = (x1 + x2) / 2
    return (
        f'<g opacity=".75"><line x1="{x1}" y1="{y}" x2="{x2 - 5}" y2="{y}" stroke="{color}" '
        f'stroke-width="1.2"/><path d="M {x2 - 6} {y - 3.2} L {x2} {y} L {x2 - 6} {y + 3.2}" '
        f'fill="none" stroke="{color}" stroke-width="1.2" stroke-linecap="round"/></g>'
    )


# --------------------------------------------------------------------------- build
def build(theme_name: str, lang: str) -> str:
    theme = THEMES[theme_name]
    text = TEXT[lang]
    col_x = [MARGIN + i * (COL_W + GAP) for i in range(4)]
    row_h, row_gap = 56, 9
    first_y = 106
    rows_y = [first_y + i * (row_h + row_gap) for i in range(6)]

    out: list[str] = []
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        f'role="img" aria-labelledby="arch-title arch-desc" '
        f'font-family="Inter, -apple-system, \'Segoe UI\', Helvetica, Arial, sans-serif">'
    )
    out.append(f"<title id=\"arch-title\">{esc(text['title'])}</title>")
    out.append(f"<desc id=\"arch-desc\">{esc(text['subtitle'])}</desc>")
    out.append(f'<rect width="{W}" height="{H}" fill="{theme["bg"]}"/>')

    # faint coordinate grid
    grid = "".join(
        f'<line x1="{x}" y1="0" x2="{x}" y2="{H}" stroke="{theme["grid"]}" stroke-width="1"/>'
        for x in range(0, W, 50)
    ) + "".join(
        f'<line x1="0" y1="{y}" x2="{W}" y2="{y}" stroke="{theme["grid"]}" stroke-width="1"/>'
        for y in range(0, H, 50)
    )
    out.append(f'<g>{grid}</g>')

    # header
    out.append(
        f'<text x="{MARGIN}" y="32" font-size="16.5" font-weight="650" fill="{theme["ink"]}">'
        f"{esc(text['title'])}</text>"
    )
    out.append(
        f'<text x="{MARGIN}" y="51" font-size="10.6" fill="{theme["ink3"]}">{esc(text["subtitle"])}</text>'
    )

    # column headers
    for i, label in enumerate(text["columns"]):
        x = col_x[i]
        out.append(
            f'<text x="{x}" y="86" font-size="10" letter-spacing="1.33" fill="{theme["ink3"]}" '
            f'font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace">'
            f"{esc(label.upper() if lang == 'en' else label)}</text>"
        )
        out.append(
            f'<line x1="{x}" y1="95" x2="{x + COL_W}" y2="95" stroke="{theme["line_strong"]}" stroke-width="1"/>'
        )

    # rows
    groups = [("sources", 0), ("infra", 1), ("engine", 2), ("apps", 3)]
    for group, col in groups:
        x = col_x[col]
        for i, (title, meta, status) in enumerate(text[group]):
            out.append(row(x, rows_y[i], COL_W, title, meta, status, theme))

    # arrows between columns (three connectors per gap)
    for col in range(3):
        x1 = col_x[col] + COL_W + 3
        x2 = col_x[col + 1] - 3
        for idx in (1, 2, 3):
            y = rows_y[idx] + row_h / 2
            out.append(arrow(x1, y, x2, theme["line_strong"]))

    # draft lane box occupying rows 4..6 of column 4
    box_y = rows_y[3]
    box_h = rows_y[5] + row_h - box_y
    x = col_x[3]
    out.append(
        f'<g><rect x="{x}" y="{box_y}" width="{COL_W}" height="{box_h}" rx="8" fill="{theme["draft_soft"]}" '
        f'stroke="{theme["draft"]}" stroke-width="1.1" stroke-dasharray="4 3"/>'
    )
    out.append(
        f'<text x="{x + 14}" y="{box_y + 19}" font-size="9.4" letter-spacing="1.1" fill="{theme["ink3"]}" '
        f'font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace">'
        f"{esc(text['draft_title'])}</text>"
    )
    out.append(
        f'<text x="{x + 14}" y="{box_y + 33}" font-size="9.4" fill="{theme["ink3"]}">'
        f"{esc(fit(text['draft_note'], 9.4, COL_W - 28))}</text>"
    )
    for i, item in enumerate(text["draft_items"]):
        out.append(
            f'<text x="{x + 14}" y="{box_y + 52 + i * 13.5}" font-size="9.9" fill="{theme["ink2"]}">'
            f"{esc(item)}</text>"
        )
    # dashed connector: the draft lane has no edge into the shipped engine
    stub_y = box_y + box_h / 2
    out.append(
        f'<path d="M {x} {stub_y} L {x - 16} {stub_y}" stroke="{theme["draft"]}" stroke-width="1.1" '
        f'stroke-dasharray="3 3"/>'
    )
    out.append(
        f'<circle cx="{x - 19}" cy="{stub_y}" r="2.1" fill="{theme["draft"]}" opacity=".8"/>'
    )
    out.append("</g>")

    # legend
    legend_y = 524
    legend_x = [MARGIN, MARGIN + 296, MARGIN + 586]
    for (status, label, note), lx in zip(text["legend"], legend_x):
        out.append(status_dot(lx + 6, legend_y - 3.5, status, theme))
        out.append(
            f'<text x="{lx + 20}" y="{legend_y}" font-size="11" font-weight="600" fill="{theme["ink"]}">'
            f"{esc(label)}</text>"
        )
        out.append(
            f'<text x="{lx + 20}" y="{legend_y + 14}" font-size="9.6" fill="{theme["ink3"]}">'
            f"{esc(note)}</text>"
        )

    out.append(
        f'<line x1="{MARGIN}" y1="556" x2="{W - MARGIN}" y2="556" stroke="{theme["line"]}" stroke-width="1"/>'
    )
    out.append(
        f'<text x="{MARGIN}" y="576" font-size="9.6" fill="{theme["ink3"]}">{esc(text["footnote"])}</text>'
    )

    out.append("</svg>")
    return "\n".join(out) + "\n"


def main(argv: list[str]) -> int:
    check = "--check" in argv
    OUT.mkdir(parents=True, exist_ok=True)
    stale: list[str] = []
    for theme_name in ("light", "dark"):
        for lang in ("en", "zh"):
            path = OUT / f"architecture-{lang}-{theme_name}.svg"
            content = build(theme_name, lang)
            if check:
                if not path.is_file() or path.read_text(encoding="utf-8") != content:
                    stale.append(str(path.relative_to(ROOT)))
            else:
                path.write_text(content, encoding="utf-8", newline="\n")
                print(f"wrote {path.relative_to(ROOT)} ({len(content):,} chars)")
    if check:
        if stale:
            print("stale architecture assets:", *stale, sep="\n  ")
            return 1
        print("architecture assets are up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
