"""Interactive, single-file dashboard for the MedRadar data.

The dashboard is a small, dependency-free single page application:

* one HTML file with inlined CSS, vanilla JS and the input JSON (``script
  type="application/json"``),
* seven views (overview / tracks / companies / products / cases / replay /
  data) with client-side search, table sorting, case-library filters and a
  detail drawer, replay cost switching with an SVG equity curve, URL hash
  routing and a dark/light theme,
* no CDN, no external fonts, no network requests - it works over ``file://``
  and on GitHub Pages.

``build_dashboard`` is deliberately side-effect free apart from writing the
output file; it returns a small summary the CLI can print.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import DEFAULT_METRICS, OUT_DIR
from .util import ensure_dir, read_json, utc_now_iso, write_text

#: View ids, also used by the navigation and by ``tests/test_dashboard.py``.
VIEWS: tuple[str, ...] = (
    "overview",
    "tracks",
    "companies",
    "products",
    "cases",
    "replay",
    "data",
)

VIEW_TITLES = {
    "overview": "概览",
    "tracks": "赛道",
    "companies": "公司",
    "products": "产品",
    "cases": "案例库",
    "replay": "回放",
    "data": "数据",
}

DEFAULT_CASES = Path("out/cases/cases.json")
DEFAULT_REPLAY = Path("out/replay/replay.json")


# --------------------------------------------------------------------------- helpers
def _json_for_script(payload: Any) -> str:
    """Compact JSON that is safe to inline inside a ``<script>`` element."""
    text = json.dumps(
        payload,
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    )
    # ``</script>`` anywhere in user data would close the element early.
    return (
        text.replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _load(path: str | Path | None, default: Any) -> Any:
    if not path:
        return default
    payload = read_json(path, default=None)
    return default if payload is None else payload


def _file_info(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {"path": "", "bytes": 0, "exists": False}
    target = Path(path)
    return {
        "path": str(target),
        "bytes": target.stat().st_size if target.exists() else 0,
        "exists": target.exists(),
    }


def _audit_guess(metrics_path: Path, audit_path: str | Path | None) -> Any:
    if audit_path:
        return read_json(audit_path, default=None)
    candidates = (
        metrics_path.parent / "audit.json",
        metrics_path.parent / "audit_20261031" / "results.json",
    )
    for candidate in candidates:
        payload = read_json(candidate, default=None)
        if payload:
            return payload
    return None


def render_dashboard_html(payload: Any) -> str:
    """Render the full HTML document for an already assembled payload."""
    data_json = _json_for_script(payload)
    html_doc = (
        _HTML.replace("__CSS__", _CSS)
        .replace("__JS__", _JS)
        .replace("__TITLE__", "MedRadar · 交互式看板")
        .replace("__BUILT_AT__", str(payload.get("generated_at", "")) if isinstance(payload, dict) else "")
        .replace("__DATA__", data_json)
    )
    return html_doc


def build_dashboard(
    metrics_path: str | Path = DEFAULT_METRICS,
    cases_path: str | Path = DEFAULT_CASES,
    replay_path: str | Path = DEFAULT_REPLAY,
    out_path: str | Path | None = None,
    audit_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build the single-file interactive dashboard and write it to ``out_path``.

    ``out_path`` defaults to ``out/dashboard.html``. All inputs are optional at
    the JS level: missing or empty blocks render "暂无数据" instead of failing.
    """
    metrics_input = Path(metrics_path)
    cases_input = Path(cases_path)
    replay_input = Path(replay_path)
    target = Path(out_path) if out_path else Path(OUT_DIR) / "dashboard.html"

    metrics = _load(metrics_input, {})
    cases = _load(cases_input, {})
    replay = _load(replay_input, {})
    data_stats = _load(metrics_input.parent / "data_stats.json", None)
    audit = _audit_guess(metrics_input, audit_path)

    if not isinstance(metrics, dict):
        metrics = {}
    if not isinstance(cases, dict):
        cases = {"selected": cases} if isinstance(cases, list) else {}
    if not isinstance(replay, dict):
        replay = {}

    payload = {
        "generated_at": utc_now_iso(),
        "views": list(VIEWS),
        "metrics": metrics,
        "cases": cases,
        "replay": replay,
        "data_stats": data_stats if isinstance(data_stats, dict) else None,
        "audit": audit,
        "sources": {
            "metrics": _file_info(metrics_input),
            "cases": _file_info(cases_input),
            "replay": _file_info(replay_input),
            "data_stats": _file_info(metrics_input.parent / "data_stats.json"),
            "audit": _file_info(audit_path) if audit_path else {"path": "", "bytes": 0, "exists": audit is not None},
        },
    }

    html_doc = render_dashboard_html(payload)
    ensure_dir(Path(target).parent)
    written = write_text(target, html_doc)
    return {
        "out": str(written),
        "bytes": len(html_doc.encode("utf-8")),
        "views": list(VIEWS),
        "cases": len(cases.get("selected") or []),
        "negative_cases": len(cases.get("negative_examples") or []),
        "replay_steps": len(replay.get("steps") or []),
        "inline_data_bytes": len(_json_for_script(payload).encode("utf-8")),
        "generated_at": payload["generated_at"],
    }


# --------------------------------------------------------------------------- CSS
_CSS = r"""
:root{
  --bg:#0d1117;--panel:#161b22;--panel2:#1c2330;--panel3:#222b39;
  --ink:#e6edf3;--muted:#8b949e;--line:#30363d;--line2:#3d444d;
  --accent:#58a6ff;--accent2:#2dd4bf;--up:#3fb950;--down:#f85149;--warn:#d29922;
  --chip:#21262d;--shadow:0 10px 30px rgba(0,0,0,.35);--radius:10px;
}
html[data-theme="light"]{
  --bg:#f6f8fa;--panel:#ffffff;--panel2:#f1f4f8;--panel3:#eaeef2;
  --ink:#1f2328;--muted:#656d76;--line:#d0d7de;--line2:#c8d1da;
  --accent:#0969da;--accent2:#0f766e;--up:#116329;--down:#b42318;--warn:#9a6700;
  --chip:#eef2f6;--shadow:0 10px 30px rgba(31,35,40,.12);
}
*{box-sizing:border-box}
html,body{margin:0;max-width:100%;overflow-x:hidden}
body{background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
font-size:14px;line-height:1.6;-webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
button{font-family:inherit;font-size:inherit;color:inherit;cursor:pointer}
.app{display:grid;grid-template-columns:238px minmax(0,1fr);min-height:100vh}
.sidebar{background:var(--panel);border-right:1px solid var(--line);padding:18px 14px;position:sticky;top:0;height:100vh;
display:flex;flex-direction:column;gap:14px;overflow-y:auto}
.brand{display:flex;align-items:center;gap:9px;font-size:19px;font-weight:700;color:var(--accent);letter-spacing:.3px;white-space:nowrap}
.brand .dot{width:8px;height:8px;border-radius:50%;background:var(--accent2);display:inline-block}
.brand small{font-size:11px;font-weight:500;color:var(--muted);letter-spacing:0}
.nav{display:flex;flex-direction:column;gap:3px}
.nav-btn{display:flex;align-items:center;justify-content:space-between;gap:8px;background:transparent;border:1px solid transparent;
border-radius:8px;padding:8px 11px;text-align:left;color:var(--muted);white-space:nowrap}
.nav-btn .ico{width:18px;text-align:center;opacity:.85}
.nav-btn:hover{background:var(--panel2);color:var(--ink)}
.nav-btn.active{background:var(--panel3);color:var(--ink);border-color:var(--line2);font-weight:600}
.nav-btn .badge-n{font-size:11px;color:var(--muted);background:var(--chip);border-radius:999px;padding:0 6px}
.side-foot{margin-top:auto;display:flex;flex-direction:column;gap:8px;font-size:12px;color:var(--muted)}
.side-actions{display:flex;gap:8px;flex-wrap:wrap}
.btn{background:var(--panel2);border:1px solid var(--line2);border-radius:7px;padding:5px 10px;color:var(--ink)}
.btn:hover{border-color:var(--accent)}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600}
html[data-theme="light"] .btn.primary{color:#fff}
.btn.active{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600}
.main{min-width:0;padding:0 0 30px}
.topbar{position:sticky;top:0;z-index:20;background:color-mix(in srgb, var(--bg) 88%, transparent);
backdrop-filter:blur(8px);border-bottom:1px solid var(--line);padding:12px 22px;display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.view-title{font-size:18px;font-weight:700;margin:0;white-space:nowrap}
.search-wrap{flex:1 1 260px;min-width:160px;display:flex;align-items:center;gap:8px;background:var(--panel);border:1px solid var(--line2);
border-radius:9px;padding:6px 11px}
.search-wrap input{flex:1;min-width:0;background:transparent;border:0;outline:0;color:var(--ink);font-size:14px}
.search-wrap input::placeholder{color:var(--muted)}
.search-count{font-size:12px;color:var(--muted);white-space:nowrap}
.content{padding:18px 22px 10px;min-width:0}
.view{display:none}
.view.active{display:block}
.grid{display:grid;gap:14px}
.kpis{grid-template-columns:repeat(auto-fit,minmax(180px,1fr));margin-bottom:16px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:14px 16px;min-width:0}
.kpi .k{font-size:12px;color:var(--muted);letter-spacing:.3px}
.kpi .v{font-size:23px;font-weight:700;margin-top:3px;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
.kpi .v.small{font-size:16px}
.kpi .s{font-size:12px;color:var(--muted);margin-top:2px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:16px 18px;margin-bottom:16px;min-width:0}
.panel h2{font-size:15px;margin:0 0 12px;padding-bottom:8px;border-bottom:1px solid var(--line)}
.panel h3{font-size:13.5px;margin:14px 0 8px;color:var(--ink)}
.muted{color:var(--muted)}
.small{font-size:12px}
.mt8{margin-top:8px}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap;min-width:0}
.spread{justify-content:space-between}
.filters{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:0 0 12px}
.filters label{font-size:12px;color:var(--muted)}
select,input[type="search"],input[type="text"]{background:var(--panel2);border:1px solid var(--line2);border-radius:7px;color:var(--ink);
padding:5px 9px;font-family:inherit;font-size:13px;max-width:100%}
select:focus,input:focus{outline:1px solid var(--accent)}
.table-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:8px;min-width:0}
table{border-collapse:collapse;width:100%;min-width:640px;font-size:12.8px}
th,td{padding:6px 9px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap;vertical-align:top}
th{background:var(--panel2);color:var(--muted);font-weight:600;position:sticky;top:0;z-index:1}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover td{background:var(--panel2)}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
th button.th-sort{all:unset;cursor:pointer;display:inline-flex;align-items:center;gap:4px;color:inherit;font-weight:600}
th button.th-sort:hover{color:var(--accent)}
.arrow{font-size:10px;color:var(--accent)}
.empty{color:var(--muted);font-size:13px;padding:8px 2px}
.v{font-variant-numeric:tabular-nums;font-weight:600}
.v.up{color:var(--up)}
.v.down{color:var(--down)}
.v.flat{color:var(--muted)}
.badge{display:inline-block;border:1px solid var(--line2);background:var(--chip);border-radius:999px;padding:0 8px;font-size:11px;line-height:19px;white-space:nowrap}
.badge.up{background:color-mix(in srgb,var(--up) 14%,transparent);border-color:color-mix(in srgb,var(--up) 45%,var(--line2));color:var(--up)}
.badge.down{background:color-mix(in srgb,var(--down) 14%,transparent);border-color:color-mix(in srgb,var(--down) 45%,var(--line2));color:var(--down)}
.badge.warn{background:color-mix(in srgb,var(--warn) 16%,transparent);border-color:color-mix(in srgb,var(--warn) 45%,var(--line2));color:var(--warn)}
.badge.hit{background:color-mix(in srgb,var(--up) 16%,transparent);border-color:color-mix(in srgb,var(--up) 45%,var(--line2));color:var(--up)}
.badge.miss{background:color-mix(in srgb,var(--down) 16%,transparent);border-color:color-mix(in srgb,var(--down) 45%,var(--line2));color:var(--down)}
.badge.mixed{background:color-mix(in srgb,var(--warn) 16%,transparent);border-color:color-mix(in srgb,var(--warn) 45%,var(--line2));color:var(--warn)}
.chip{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line2);border-radius:999px;padding:2px 10px;font-size:12px;background:var(--chip);color:var(--muted)}
.chip .dot{width:8px;height:8px;border-radius:50%;background:var(--muted)}
.chip.ok .dot{background:var(--up)}.chip.warn .dot{background:var(--warn)}.chip.bad .dot{background:var(--down)}
canvas{max-width:100%}
svg.chart{display:block;width:100%;height:auto;overflow:visible}
svg.chart text{fill:var(--muted);font-size:11px;font-family:inherit}
svg.chart .grid{stroke:var(--line);stroke-width:1}
svg.chart .axis{stroke:var(--line2);stroke-width:1}
svg.chart .bars{fill:var(--accent);opacity:.85}
svg.chart .bars:hover{opacity:1}
svg.chart .line{fill:none;stroke:var(--accent);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
svg.chart .area{fill:color-mix(in srgb,var(--accent) 18%,transparent);stroke:none}
svg.chart .dot{fill:var(--panel);stroke:var(--accent);stroke-width:2}
svg.chart .val{fill:var(--ink);font-weight:600}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
.case-card{background:var(--panel2);border:1px solid var(--line);border-radius:9px;padding:12px 14px;cursor:pointer;min-width:0;
transition:border-color .12s ease,transform .12s ease}
.case-card:hover{border-color:var(--accent);transform:translateY(-1px)}
.case-card.negative{border-left:3px solid var(--warn)}
.case-card .head{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;align-items:center}
.case-card .date{font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums}
.case-card .company{font-weight:700;font-size:14px}
.case-card .event{font-size:12.8px;color:var(--ink);margin:6px 0;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.case-card .quote{font-size:12px;color:var(--muted);border-left:2px solid var(--line2);padding-left:8px;margin:6px 0;
display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}
.case-card .foot{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:8px;font-size:12px;color:var(--muted)}
.radar-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:12px}
.radar-card{background:var(--panel2);border:1px solid var(--line);border-radius:9px;padding:12px 14px;min-width:0}
.radar-card .name{font-weight:650;font-size:14px}
.radar-card .line{font-size:12.5px;color:var(--ink);margin-top:3px;overflow-wrap:anywhere}
.radar-card .line b{color:var(--muted);font-weight:600;margin-right:4px}
.radar-card .src{font-size:11.5px;color:var(--muted);overflow-wrap:anywhere}
.radar-card .src a{overflow-wrap:anywhere}
.timeline-note{font-size:12px;color:var(--muted);margin:4px 0 10px;overflow-wrap:anywhere}
dialog{border:1px solid var(--line2);border-radius:12px;background:var(--panel);color:var(--ink);padding:0;max-width:min(820px,94vw);
width:820px;max-height:88vh;box-shadow:var(--shadow)}
dialog::backdrop{background:rgba(0,0,0,.6);backdrop-filter:blur(2px)}
.dlg-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding:16px 20px 10px;border-bottom:1px solid var(--line)}
.dlg-head h2{margin:0;font-size:17px;overflow-wrap:anywhere}
.dlg-body{padding:14px 20px 22px;overflow-y:auto;max-height:calc(88vh - 70px)}
.dlg-close{background:var(--panel2);border:1px solid var(--line2);border-radius:7px;padding:4px 10px;font-size:13px}
blockquote{margin:8px 0;padding:8px 12px;border-left:3px solid var(--accent);background:var(--panel2);border-radius:0 6px 6px 0;
font-size:13px;line-height:1.6;overflow-wrap:anywhere}
.pricebars{display:flex;flex-direction:column;gap:6px;margin:12px 0}
.pricebar{display:grid;grid-template-columns:58px minmax(0,1fr) 102px;gap:10px;align-items:center;font-size:12.5px}
.pricebar .track{height:12px;background:var(--panel3);border-radius:6px;position:relative;overflow:hidden}
.pricebar .fill{position:absolute;top:0;bottom:0;border-radius:6px}
.pricebar .fill.up{left:50%;background:var(--up)}
.pricebar .fill.down{right:50%;background:var(--down)}
.pricebar .fill.flat{left:calc(50% - 2px);width:4px;background:var(--muted)}
.pricebar .val{text-align:right}
.case-detail-meta{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 12px}
.kv{width:100%;border-collapse:collapse;font-size:12.5px;min-width:0}
.kv th{width:150px;background:transparent;color:var(--muted);font-weight:600;border-bottom:1px solid var(--line);position:static}
.kv td{overflow-wrap:anywhere;white-space:normal}
.callout{border-left:3px solid var(--warn);background:color-mix(in srgb,var(--warn) 9%,var(--panel));border-radius:0 7px 7px 0;
padding:9px 12px;font-size:12.8px;margin:0 0 12px;color:var(--ink)}
.callout.ok{border-left-color:var(--up);background:color-mix(in srgb,var(--up) 8%,var(--panel))}
.callout.bad{border-left-color:var(--down);background:color-mix(in srgb,var(--down) 8%,var(--panel))}
.noscript{max-width:720px;margin:60px auto;padding:20px 24px;border:1px solid var(--warn);border-radius:10px;background:var(--panel);
color:var(--ink);font-size:14px}
.src-badge{font-size:11px}
.statgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:0 0 12px}
.stat{background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:9px 12px}
.stat .k{font-size:11.5px;color:var(--muted)}
.stat .v{font-size:18px;font-weight:700;font-variant-numeric:tabular-nums}
.note{font-size:12px;color:var(--muted);overflow-wrap:anywhere}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px}
.wrap-any{overflow-wrap:anywhere}
@media (max-width:900px){
  .app{grid-template-columns:1fr}
  .sidebar{position:static;height:auto;flex-direction:row;align-items:center;gap:10px;overflow-x:auto;padding:10px 12px;
  border-right:0;border-bottom:1px solid var(--line)}
  .brand{font-size:16px}
  .brand small{display:none}
  .nav{flex-direction:row;overflow-x:auto;padding-bottom:2px}
  .nav-btn{padding:6px 9px;flex:0 0 auto}
  .nav-btn .badge-n{display:none}
  .side-foot{display:none}
  .topbar{position:static;padding:10px 14px}
  .content{padding:12px 14px 8px}
  .cards,.radar-grid{grid-template-columns:1fr}
  .panel{padding:12px 13px}
  .kpis{grid-template-columns:repeat(2,minmax(0,1fr))}
  table{min-width:560px}
}
@media (max-width:480px){
  .kpis{grid-template-columns:1fr}
  .view-title{font-size:16px}
  .pricebar{grid-template-columns:48px minmax(0,1fr) 90px}
}
@media print{.sidebar,.topbar,.search-wrap{display:none}.app{display:block}}
"""


# --------------------------------------------------------------------------- JS
_JS = r"""
(function () {
  'use strict';
  var DATA = {};
  try {
    DATA = JSON.parse(document.getElementById('dashboard-data').textContent || '{}');
  } catch (err) {
    DATA = {};
  }
  var M = DATA.metrics || {};
  var C = DATA.cases || {};
  var R = DATA.replay || {};
  var DS = DATA.data_stats || null;
  var AUDIT = DATA.audit || null;
  var VIEWS = ['overview', 'tracks', 'companies', 'products', 'cases', 'replay', 'data'];
  var TITLES = {overview: '概览', tracks: '赛道', companies: '公司', products: '产品',
                cases: '案例库', replay: '回放', data: '数据'};
  var CAT_LABELS = {approval: '批准', crl: 'CRL（完整回复函）', trial_result: '试验结果',
                    device_novel_code: '新产品码', device_new_track: '新赛道',
                    drug_approval: '药品批准', trial_start: '试验启动', recall_cluster: '召回聚集',
                    recall: '召回', trial: '临床试验', device_clearance: '器械清关'};
  var OUTCOME_LABELS = {hit: '命中', miss: '未命中', mixed: '部分命中'};
  var KIND_LABELS = {device_novel_code: '新产品码', device_new_track: '新赛道进入',
                     drug_approval: '药品批准', trial_start: '试验启动', recall_cluster: '召回聚集',
                     '8k_catalyst': '8-K 催化剂', earnings: '财报', ma: '并购'};
  var SOURCE_LABELS = {daily: '日线', intraday: '盘中', db: '本地库', yahoo: 'Yahoo 日线'};
  var state = {
    view: 'overview', theme: 'dark', q: '',
    sort: {},
    cases: {category: 'all', year: 'all', outcome: 'all', sort: 'date_desc'},
    replay: {cost: '10', year: 'all', kind: 'all'}
  };

  // ------------------------------------------------------------------ utils
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function num(v) {
    if (typeof v === 'number') { return isFinite(v) ? v : null; }
    if (typeof v === 'string' && v.trim() !== '') {
      var n = parseFloat(v.replace(/,/g, ''));
      return isFinite(n) ? n : null;
    }
    return null;
  }
  function esc(v) {
    return String(v === null || v === undefined ? '' : v).replace(/[&<>"']/g, function (ch) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch];
    });
  }
  function arr(v) { return Array.isArray(v) ? v : []; }
  function obj(v) { return v && typeof v === 'object' && !Array.isArray(v) ? v : {}; }
  function fmtInt(v) {
    var n = num(v);
    return n === null ? '暂无数据' : Math.round(n).toLocaleString('zh-CN');
  }
  function fmtNum(v, d) {
    var n = num(v);
    return n === null ? '暂无数据' : n.toFixed(d === undefined ? 1 : d);
  }
  function pct(v, d) {
    var n = num(v);
    return n === null ? '暂无数据' : (n * 100).toFixed(d === undefined ? 1 : d) + '%';
  }
  function signed(v, d) {
    var n = num(v);
    if (n === null) { return {text: '暂无数据', cls: 'flat', value: null}; }
    var p = n * 100;
    var arrow = p > 0 ? '▲' : (p < 0 ? '▼' : '→');
    var text = (p > 0 ? '+' : '') + p.toFixed(d === undefined ? 1 : d) + '% ' + arrow;
    return {text: text, cls: p > 0 ? 'up' : (p < 0 ? 'down' : 'flat'), value: p};
  }
  function signHtml(v, d) {
    var s = signed(v, d);
    return '<span class="v ' + s.cls + '">' + esc(s.text) + '</span>';
  }
  function trendOf(row) {
    var ci = arr(row.ci);
    var lo = num(ci[0]), hi = num(ci[1]), thi = num(row.thi);
    if (lo !== null && lo > 1) { return {text: '升温', cls: 'up'}; }
    if (hi !== null && hi < 1) { return {text: '降温', cls: 'down'}; }
    if (thi !== null) {
      if (thi > 1.05) { return {text: '升温', cls: 'up'}; }
      if (thi < 0.95) { return {text: '降温', cls: 'down'}; }
    }
    return {text: '平稳', cls: 'flat'};
  }
  function categoryLabel(v) { var s = String(v || ''); return CAT_LABELS[s] || s || '暂无数据'; }
  function outcomeLabel(v) { var s = String(v || ''); return OUTCOME_LABELS[s] || s || '暂无数据'; }
  function hash(text) { return String(text || '').toLowerCase(); }
  function matches(parts) {
    if (!state.q) { return true; }
    for (var i = 0; i < parts.length; i += 1) {
      if (hash(parts[i]).indexOf(state.q) !== -1) { return true; }
    }
    return false;
  }
  function empty(text) { return '<div class="empty">' + esc(text || '暂无数据') + '</div>'; }

  // ---------------------------------------------------------------- data maps
  var trackList = arr(obj(M.device).tracks);
  var companyList = arr(obj(M.device).companies);
  var migrationList = arr(obj(M.device).migration);
  var familyList = arr(obj(M.products).families);
  var newProductList = arr(obj(M.products).new_products);
  var portfolioList = arr(obj(M.products).company_portfolio);
  var allCases = (function () {
    var negativeList = arr(C.negative_examples);
    var negativeKeys = {};
    negativeList.forEach(function (c) { if (c.case_id) { negativeKeys[c.case_id] = true; } });
    var selected = arr(C.selected).filter(function (c) { return !(c.case_id && negativeKeys[c.case_id]); });
    return selected.concat(negativeList);
  })();
  var replaySteps = arr(R.steps);
  var caseIndex = {};
  allCases.forEach(function (c, i) {
    var key = String(c.case_id || ('case-' + i));
    c.__negative = arr(C.negative_examples).indexOf(c) !== -1;
    c.__key = key;
    caseIndex[key] = c;
  });
  var migrationByKey = {};
  migrationList.forEach(function (m) { if (m.key) { migrationByKey[m.key] = m; } });
  var portfolioByName = {};
  portfolioList.forEach(function (p, i) {
    if (p.company_zh) { portfolioByName[hash(p.company_zh)] = p; }
    if (p.ticker) { portfolioByName[hash(p.ticker)] = p; }
    portfolioByName['#' + i] = p;
  });

  // ---------------------------------------------------------------- rendering
  function renderTable(container, tableId, columns, rows, defaultSort) {
    var el = typeof container === 'string' ? $(container) : container;
    if (!el) { return; }
    if (!rows.length) { el.innerHTML = empty(); return; }
    var sort = state.sort[tableId] || defaultSort || null;
    if (sort) {
      var col = null;
      for (var c = 0; c < columns.length; c += 1) { if (columns[c].key === sort.key) { col = columns[c]; } }
      if (col) {
        rows = rows.slice().sort(function (a, b) {
          var va = col.get ? col.get(a) : a[sort.key];
          var vb = col.get ? col.get(b) : b[sort.key];
          var na = num(va), nb = num(vb);
          var cmp;
          if (na !== null && nb !== null) { cmp = na - nb; }
          else { cmp = String(va === null || va === undefined ? '' : va).localeCompare(String(vb === null || vb === undefined ? '' : vb), 'zh-CN'); }
          return cmp * sort.dir;
        });
      }
    }
    var thead = '<thead><tr>';
    columns.forEach(function (col) {
      var cls = col.cls || '';
      var active = sort && sort.key === col.key;
      var arrow = active ? (sort.dir > 0 ? '▲' : '▼') : '';
      var label = col.sortable === false
        ? esc(col.label)
        : '<button class="th-sort" data-sort-table="' + esc(tableId) + '" data-sort-key="' + esc(col.key) + '">'
          + esc(col.label) + ' <span class="arrow">' + arrow + '</span></button>';
      thead += '<th class="' + esc(cls) + '">' + label + '</th>';
    });
    thead += '</tr></thead>';
    var body = '<tbody>';
    rows.forEach(function (row) {
      body += '<tr>';
      columns.forEach(function (col) {
        var raw = col.get ? col.get(row) : row[col.key];
        var cls = col.cls || '';
        var value;
        if (col.html) { value = col.html(raw, row); }
        else if (col.fmt) { value = col.fmt(raw, row); }
        else { value = esc(raw === null || raw === undefined ? '暂无数据' : raw); }
        body += '<td class="' + esc(cls) + '">' + value + '</td>';
      });
      body += '</tr>';
    });
    body += '</tbody>';
    el.innerHTML = '<div class="table-wrap"><table>' + thead + body + '</table></div>';
  }

  function metricCards(items) {
    var html = '<div class="grid kpis">';
    items.forEach(function (item) {
      html += '<div class="card kpi"><div class="k">' + esc(item.label) + '</div>'
        + '<div class="v' + (item.small ? ' small' : '') + '">' + (item.html || esc(item.value)) + '</div>'
        + '<div class="s">' + esc(item.sub || '') + '</div></div>';
    });
    return html + '</div>';
  }

  function statGrid(items) {
    var html = '<div class="statgrid">';
    items.forEach(function (item) {
      html += '<div class="stat"><div class="k">' + esc(item.label) + '</div><div class="v">'
        + (item.html || esc(item.value)) + '</div></div>';
    });
    return html + '</div>';
  }

  function yearSeries(caseRows, steps) {
    var years = {};
    function add(date) {
      var m = /^(\d{4})/.exec(String(date || ''));
      if (m) { years[m[1]] = (years[m[1]] || 0) + 1; }
    }
    if (DS && DS.events && DS.events.by_year) {
      Object.keys(DS.events.by_year).forEach(function (y) { years[y] = num(DS.events.by_year[y]) || 0; });
      return {source: 'events.by_year', data: years, label: '事件年度分布'};
    }
    caseRows.forEach(function (c) { add(c.date); });
    steps.forEach(function (s) { add(s.signal_date || s.fill_date); });
    return {source: 'cases+replay', data: years, label: '样本年度分布（案例 + 回放）'};
  }

  function barChart(series, options) {
    var data = series.data || {};
    var years = Object.keys(data).sort();
    if (options && options.lastN) { years = years.slice(-options.lastN); }
    if (!years.length) { return empty(); }
    var values = years.map(function (y) { return num(data[y]) || 0; });
    var max = Math.max.apply(null, values) || 1;
    var width = 920, height = 240, left = 56, right = width - 14, top = 18, bottom = height - 34;
    var step = (right - left) / Math.max(1, years.length);
    var barW = Math.max(4, Math.min(38, step * 0.62));
    var svg = '<svg class="chart" viewBox="0 0 ' + width + ' ' + height + '" role="img" aria-label="' + esc(series.label) + '">';
    for (var g = 0; g <= 3; g += 1) {
      var y = top + (bottom - top) * g / 3;
      var v = max * (1 - g / 3);
      svg += '<line class="grid" x1="' + left + '" y1="' + y.toFixed(1) + '" x2="' + right + '" y2="' + y.toFixed(1) + '"/>';
      svg += '<text x="' + (left - 8) + '" y="' + (y + 4).toFixed(1) + '" text-anchor="end">' + esc(compactInt(v)) + '</text>';
    }
    years.forEach(function (year, i) {
      var h = Math.max(2, (values[i] / max) * (bottom - top));
      var x = left + step * i + (step - barW) / 2;
      svg += '<rect class="bars" x="' + x.toFixed(1) + '" y="' + (bottom - h).toFixed(1) + '" width="' + barW.toFixed(1)
        + '" height="' + h.toFixed(1) + '" rx="2"><title>' + esc(year + '：' + fmtInt(values[i])) + '</title></rect>';
      if (years.length <= 18 || i % Math.ceil(years.length / 14) === 0) {
        svg += '<text x="' + (x + barW / 2).toFixed(1) + '" y="' + (bottom + 16) + '" text-anchor="middle">' + esc(year) + '</text>';
      }
    });
    svg += '<line class="axis" x1="' + left + '" y1="' + bottom + '" x2="' + right + '" y2="' + bottom + '"/></svg>';
    return '<p class="note">' + esc(series.label) + '（数据源：' + esc(series.source) + '）</p>' + svg;
  }

  function compactInt(v) {
    var n = Math.round(v);
    if (Math.abs(n) >= 1000000) { return (n / 1000000).toFixed(1) + 'M'; }
    if (Math.abs(n) >= 1000) { return (n / 1000).toFixed(1) + 'k'; }
    return String(n);
  }

  // ----------------------------------------------------------------- overview
  function renderOverview() {
    var meta = obj(M.meta);
    var status = obj(meta.data_status);
    var trading = obj(M.trading);
    var summary = obj(trading.summary);
    var counts = obj(meta.counts);
    var total = num(meta.event_total);
    if (total === null) {
      total = 0;
      Object.keys(counts).forEach(function (k) { total += num(counts[k]) || 0; });
    }
    var reg = obj(meta.registry);
    var regText = reg.companies_total
      ? ('注册表 ' + fmtInt(reg.companies_total) + ' 家 / ' + fmtInt(reg.tracks_device) + ' 赛道')
      : '注册表规模见数据页';
    var casesTotal = num(obj(C.stats).total);
    if (casesTotal === null) { casesTotal = allCases.length; }
    var html = metricCards([
      {label: '事件总数', value: fmtInt(total) + ' 件', sub: '窗口 ' + esc(obj(meta.window).start || '暂无数据') + ' → ' + esc(obj(meta.window).end || '暂无数据')},
      {label: '赛道 / 公司（展示）', value: trackList.length + ' / ' + companyList.length, sub: regText + '；产品族 ' + familyList.length + ' 个'},
      {label: '案例库', value: fmtInt(casesTotal) + ' 条', sub: '反例 ' + fmtInt(arr(C.negative_examples).length) + ' 条，命中率 ' + pct(obj(C.stats).hit_rate_20d)},
      {label: '回放步骤', value: fmtInt(replaySteps.length) + ' 步', sub: '成交 ' + fmtInt(obj(R.summary).n_trades) + ' 笔'},
      {label: '模拟盘收益', value: signed(summary.total_return).text, sub: '最大回撤 ' + signed(summary.max_drawdown).text},
      {label: '信号', value: fmtInt(arr(M.signals).length) + ' 条', sub: '实时告警源 openFDA / CT.gov'},
      {label: '数据源', value: Object.keys(status).filter(function (k) { return status[k] === 'ok' || status[k] === 'loaded' || status[k] === 'partial'; }).length + ' / ' + Object.keys(status).length, sub: 'NMPA：' + esc(status.nmpa || '未知')}
    ]);
    html += '<div class="panel"><h2>事件年度分布</h2><div id="overview-bars">'
      + barChart(yearSeries(allCases, replaySteps), {lastN: 20}) + '</div></div>';
    var chips = '<div class="panel"><h2>数据来源状态</h2><div class="row">';
    Object.keys(status).forEach(function (key) {
      var value = status[key];
      var cls = (value === 'ok' || value === 'loaded') ? 'ok' : (value === 'partial' || value === 'demo' ? 'warn' : 'bad');
      chips += '<span class="chip ' + cls + '"><span class="dot"></span>' + esc(key) + '：' + esc(value) + '</span>';
    });
    chips += '</div></div>';
    html += chips;
    var alerts = obj(M.alerts);
    var alertRows = [];
    arr(alerts.accelerating_tracks).slice(0, 4).forEach(function (t) {
      alertRows.push('热度加速：' + esc(t.name_zh) + '（THI ' + fmtNum(t.thi, 2) + '，P ' + pct(t.prob_up) + '，窗口 ' + fmtInt(t.recent) + ' 件）');
    });
    arr(alerts.company_movers).slice(0, 3).forEach(function (t) {
      alertRows.push('大厂异动：' + esc(t.name_zh) + '（THI ' + fmtNum(t.thi, 2) + '，12 个月新产品码 ' + fmtInt(t.novelty_12m) + '）');
    });
    arr(alerts.recall_clusters).slice(0, 3).forEach(function (t) {
      alertRows.push('召回聚集：' + esc(t.name_zh) + '（' + fmtInt(t.recent) + ' 次）');
    });
    html += '<div class="panel"><h2>自动预警</h2>' + (alertRows.length
      ? '<ul class="muted">' + alertRows.map(function (x) { return '<li>' + x + '</li>'; }).join('') + '</ul>'
      : empty()) + '</div>';
    $('#overview-body').innerHTML = html;
  }

  // ------------------------------------------------------------------- tracks
  function renderTracks() {
    var rows = trackList.filter(function (t) {
      return matches([t.name_zh, t.name_en, t.track_id]);
    });
    $('#tracks-count').textContent = rows.length + ' / ' + trackList.length + ' 个赛道';
    renderTable('#tracks-table', 'tracks', [
      {key: 'rank', label: '#', cls: 'num', get: function (t) { return t.rank; }, fmt: function (v) { return esc(fmtInt(v)); }},
      {key: 'name_zh', label: '赛道', get: function (t) { return t.name_zh; }, fmt: function (v) { return esc(v || '暂无数据'); }},
      {key: 'thi', label: 'THI', cls: 'num', get: function (t) { return num(t.thi); }, fmt: function (v) { return esc(fmtNum(v, 2)); }},
      {key: 'ci', label: '95% CI', cls: 'num', get: function (t) { return num(arr(t.ci)[0]); }, fmt: function (v, t) {
        return esc('[' + fmtNum(arr(t.ci)[0], 2) + ', ' + fmtNum(arr(t.ci)[1], 2) + ']'); }},
      {key: 'prob_up', label: 'P(高于基线)', cls: 'num', get: function (t) { return num(t.prob_up); }, fmt: function (v) { return esc(pct(v)); }},
      {key: 'recent', label: '窗口事件', cls: 'num', get: function (t) { return num(t.recent); }, fmt: function (v) { return esc(fmtInt(v)); }},
      {key: 'recent_per_q', label: '近期/季', cls: 'num', get: function (t) { return num(t.recent_per_q); }, fmt: function (v) { return esc(fmtNum(v, 2)); }},
      {key: 'baseline_per_q', label: '基线/季', cls: 'num', get: function (t) { return num(t.baseline_per_q); }, fmt: function (v) { return esc(fmtNum(v, 2)); }},
      {key: 'major_share_recent', label: '大厂占比', cls: 'num', get: function (t) { return num(t.major_share_recent); }, fmt: function (v) { return esc(pct(v, 0)); }},
      {key: 'new_entrants_12m', label: '12月新进入', cls: 'num', get: function (t) { return num(t.new_entrants_12m); }, fmt: function (v) { return esc(fmtInt(v)); }},
      {key: 'trend', label: '趋势', sortable: false, get: function (t) { return t; }, fmt: function (v, t) {
        var tr = trendOf(t); return '<span class="badge ' + tr.cls + '">' + esc(tr.text) + '</span>'; }}
    ], rows, {key: 'thi', dir: -1});
  }

  // ---------------------------------------------------------------- companies
  function renderCompanies() {
    var rows = companyList.filter(function (c) { return matches([c.name_zh, c.name_en, c.key, c.ticker]); });
    $('#companies-count').textContent = rows.length + ' / ' + companyList.length + ' 家公司';
    renderTable('#companies-table', 'companies', [
      {key: 'name_zh', label: '公司', get: function (c) { return c.name_zh; }, fmt: function (v) { return esc(v || '暂无数据'); }},
      {key: 'ticker', label: '代码', get: function (c) { return c.ticker; }, fmt: function (v) { return esc(v || '—'); }},
      {key: 'thi', label: 'THI', cls: 'num', get: function (c) { return num(c.thi); }, fmt: function (v) { return esc(fmtNum(v, 2)); }},
      {key: 'prob_up', label: 'P(高于基线)', cls: 'num', get: function (c) { return num(c.prob_up); }, fmt: function (v) { return esc(pct(v)); }},
      {key: 'recent', label: '窗口事件', cls: 'num', get: function (c) { return num(c.recent); }, fmt: function (v) { return esc(fmtInt(v)); }},
      {key: 'recent_per_q', label: '近期/季', cls: 'num', get: function (c) { return num(c.recent_per_q); }, fmt: function (v) { return esc(fmtNum(v, 2)); }},
      {key: 'js', label: 'JS 迁移', cls: 'num', get: function (c) { var m = migrationByKey[c.key] || {}; return num(m.js); },
        fmt: function (v) { return esc(v === null ? '暂无数据' : fmtNum(v, 3)); }},
      {key: 'portfolio', label: '产品族组合', sortable: false, get: function (c) {
        var p = portfolioByName[hash(c.name_zh)] || (c.ticker ? portfolioByName[hash(c.ticker)] : null);
        return p || null;
      }, fmt: function (v) {
        if (!v || !arr(v.top_families).length) { return '<span class="muted">暂无数据</span>'; }
        return esc(arr(v.top_families).slice(0, 2).map(function (pair) {
          return String(pair[0]) + ' ' + pct(pair[1], 0);
        }).join('、'));
      }}
    ], rows, {key: 'thi', dir: -1});
  }

  // ----------------------------------------------------------------- products
  function renderProducts() {
    var families = familyList.filter(function (f) { return matches([f.name_zh, f.name_en, f.family_id, f.category]); });
    $('#families-count').textContent = families.length + ' / ' + familyList.length + ' 个产品族';
    renderTable('#families-table', 'families', [
      {key: 'name_zh', label: '产品族', get: function (f) { return f.name_zh; }, fmt: function (v) { return esc(v || '暂无数据'); }},
      {key: 'category', label: '品类', get: function (f) { return f.category; }, fmt: function (v) { return esc(v || '暂无数据'); }},
      {key: 'thi', label: 'THI', cls: 'num', get: function (f) { return num(f.thi); }, fmt: function (v) { return esc(fmtNum(v, 2)); }},
      {key: 'prob_up', label: 'P(高于基线)', cls: 'num', get: function (f) { return num(f.prob_up); }, fmt: function (v) { return esc(pct(v)); }},
      {key: 'recent', label: '窗口事件', cls: 'num', get: function (f) { return num(f.recent); }, fmt: function (v) { return esc(fmtInt(v)); }},
      {key: 'companies', label: '公司数', cls: 'num', get: function (f) { return num(f.companies); }, fmt: function (v) { return esc(fmtInt(v)); }},
      {key: 'code_count', label: '产品码', cls: 'num', get: function (f) { return num(f.code_count); }, fmt: function (v) { return esc(fmtInt(v)); }},
      {key: 'new_entrants_12m', label: '12月新进入', cls: 'num', get: function (f) { return num(f.new_entrants_12m); }, fmt: function (v) { return esc(fmtInt(v)); }},
      {key: 'first_seen', label: '首次出现', get: function (f) { return f.first_seen; }, fmt: function (v) { return esc(v || '暂无数据'); }},
      {key: 'family_id', label: 'ID', get: function (f) { return f.family_id; }, fmt: function (v) { return '<span class="mono">' + esc(v || '—') + '</span>'; }}
    ], families, {key: 'thi', dir: -1});

    var radar = newProductList.filter(function (p) {
      return matches([p.device_name_zh, p.company_zh, p.family_zh, p.code, p.k_number, p.definition_zh, p.title]);
    });
    $('#radar-count').textContent = radar.length + ' / ' + newProductList.length + ' 条新品';
    if (!radar.length) { $('#radar-grid').innerHTML = empty(); return; }
    $('#radar-grid').innerHTML = radar.map(function (p) {
      var link = p.url
        ? '<a href="' + esc(p.url) + '" target="_blank" rel="noopener">' + esc(shortUrl(p.url)) + '</a>'
        : '<span class="muted">暂无数据</span>';
      return '<div class="radar-card">'
        + '<div class="name">' + esc(p.device_name_zh || p.title || '暂无数据') + '</div>'
        + '<div class="line"><b>公司</b>' + esc(p.company_zh || '—') + ' · <b>产品族</b>' + esc(p.family_zh || '—')
        + ' · <b>产品码</b>' + esc(p.code || '—') + '</div>'
        + '<div class="line"><b>用途</b>' + esc(p.definition_zh || '暂无数据') + '</div>'
        + '<div class="line"><b>日期</b>' + esc(p.date || '暂无数据') + ' · <b>510(k)/PMA</b>' + esc(p.k_number || '—') + '</div>'
        + '<div class="src">来源：' + link + '</div></div>';
    }).join('');
  }

  function shortUrl(url) {
    var text = String(url || '').replace(/^https?:\/\//i, '');
    return text.length > 90 ? text.slice(0, 89) + '…' : text;
  }

  // -------------------------------------------------------------------- cases
  function caseYear(c) { var m = /^(\d{4})/.exec(String(c.date || '')); return m ? m[1] : ''; }

  function renderCases() {
    var categories = {}, years = {};
    allCases.forEach(function (c) {
      if (c.category) { categories[c.category] = true; }
      if (caseYear(c)) { years[caseYear(c)] = true; }
    });
    var catSel = $('#case-category'), yearSel = $('#case-year'), outSel = $('#case-outcome');
    function fill(sel, values, allLabel, current) {
      if (!sel) { return; }
      sel.innerHTML = '<option value="all">' + esc(allLabel) + '</option>' + values.map(function (v) {
        return '<option value="' + esc(v) + '">' + esc(v) + '</option>';
      }).join('');
      sel.value = current;
    }
    fill(catSel, Object.keys(categories).sort(), '全部分类', state.cases.category);
    fill(yearSel, Object.keys(years).sort().reverse(), '全部年份', state.cases.year);
    fill(outSel, ['hit', 'miss', 'mixed'], '全部结果', state.cases.outcome);
    var rows = allCases.filter(function (c) {
      if (state.cases.category !== 'all' && c.category !== state.cases.category) { return false; }
      if (state.cases.year !== 'all' && caseYear(c) !== state.cases.year) { return false; }
      if (state.cases.outcome !== 'all' && c.outcome !== state.cases.outcome) { return false; }
      return matches([c.company_zh, c.ticker, c.event_zh, c.category, c.verdict_zh, arr(c.evidence_quotes).join(' ')]);
    });
    rows = rows.slice().sort(function (a, b) {
      if (state.cases.sort === 'p20_desc') { return (num(b.price_20d) || -9) - (num(a.price_20d) || -9); }
      if (state.cases.sort === 'p60_desc') { return (num(b.price_60d) || -9) - (num(a.price_60d) || -9); }
      if (state.cases.sort === 'p20_asc') { return (num(a.price_20d) || 9) - (num(b.price_20d) || 9); }
      return String(b.date || '').localeCompare(String(a.date || ''));
    });
    $('#cases-count').textContent = rows.length + ' / ' + allCases.length + ' 条案例'
      + (state.q ? '（搜索：' + state.q + '）' : '');
    if (!rows.length) { $('#cases-grid').innerHTML = empty(); return; }
    $('#cases-grid').innerHTML = rows.slice(0, 300).map(function (c) {
      var s20 = signed(c.price_20d);
      var neg = c.__negative ? ' negative' : '';
      return '<article class="case-card' + neg + '" data-case-id="' + esc(c.__key) + '" tabindex="0" role="button">'
        + '<div class="head"><span class="date">' + esc(c.date || '暂无数据') + '</span>'
        + '<span class="badge ' + esc(c.outcome || 'mixed') + '">' + esc(outcomeLabel(c.outcome)) + '</span></div>'
        + '<div class="company">' + esc(c.company_zh || '暂无数据') + '<span class="muted small"> ' + esc(c.ticker || '') + '</span></div>'
        + '<div class="event">' + esc(c.event_zh || '暂无数据') + '</div>'
        + (arr(c.evidence_quotes).length ? '<div class="quote">“' + esc(String(arr(c.evidence_quotes)[0]).slice(0, 160)) + '”</div>' : '')
        + '<div class="foot"><span class="badge">' + esc(categoryLabel(c.category)) + '</span>'
        + '<span class="v ' + s20.cls + '">20 日 ' + esc(s20.text) + '</span>'
        + (c.__negative ? '<span class="badge warn">反例</span>' : '')
        + '<span class="muted">点击查看证据 →</span></div></article>';
    }).join('') + (rows.length > 300 ? '<p class="note">仅展示前 300 条，请用筛选缩小范围。</p>' : '');
  }

  function openCase(key) {
    var c = caseIndex[key];
    if (!c) { return; }
    var dlg = $('#case-dialog');
    var body = $('#case-dialog-body');
    var quotes = arr(c.evidence_quotes);
    var priceRows = [['1 日', c.price_1d], ['5 日', c.price_5d], ['20 日', c.price_20d], ['60 日', c.price_60d]];
    var maxAbs = 0.0001;
    priceRows.forEach(function (p) { var n = num(p[1]); if (n !== null) { maxAbs = Math.max(maxAbs, Math.abs(n)); } });
    var bars = priceRows.map(function (p) {
      var n = num(p[1]);
      if (n === null) {
        return '<div class="pricebar"><span>' + esc(p[0]) + '</span><div class="track"><span class="fill flat"></span></div>'
          + '<span class="val muted">暂无数据</span></div>';
      }
      var s = signed(n);
      var width = Math.max(2, Math.abs(n) / maxAbs * 50);
      var fill = s.cls === 'up'
        ? '<span class="fill up" style="width:' + width.toFixed(1) + '%;left:50%"></span>'
        : (s.cls === 'down' ? '<span class="fill down" style="width:' + width.toFixed(1) + '%;right:50%"></span>'
          : '<span class="fill flat"></span>');
      return '<div class="pricebar"><span>' + esc(p[0]) + '</span><div class="track">' + fill + '</div>'
        + '<span class="val v ' + s.cls + '">' + esc(s.text) + '</span></div>';
    }).join('');
    var source = c.source_url
      ? '<a href="' + esc(c.source_url) + '" target="_blank" rel="noopener">' + esc(shortUrl(c.source_url)) + '</a>'
      : '<span class="muted">暂无数据</span>';
    body.innerHTML = '<div class="case-detail-meta">'
      + '<span class="badge ' + esc(c.outcome || 'mixed') + '">' + esc(outcomeLabel(c.outcome)) + '</span>'
      + '<span class="badge">' + esc(categoryLabel(c.category)) + '</span>'
      + '<span class="badge">' + esc((num(c.direction) || 0) > 0 ? '做多 ▲' : ((num(c.direction) || 0) < 0 ? '做空 ▼' : '中性 →')) + '</span>'
      + (c.__negative ? '<span class="badge warn">反例</span>' : '')
      + '<span class="muted small">' + esc(c.date || '暂无数据') + ' · ' + esc(c.ticker || '') + '</span></div>'
      + '<p class="wrap-any"><b>事件</b>：' + esc(c.event_zh || '暂无数据') + '</p>'
      + '<h3>逐字证据（' + quotes.length + ' 条）</h3>'
      + (quotes.length ? quotes.map(function (q) { return '<blockquote>' + esc(q) + '</blockquote>'; }).join('') : empty())
      + '<h3>价格反应</h3><div class="pricebars">' + bars + '</div>'
      + '<p class="note">涨跌同时用颜色、正负号与 ▲/▼ 标注；20 日 raw=' + esc(fmtNum(c.raw_20d, 2) + '%') + '（原始涨跌，未对齐基准/方向）。</p>'
      + '<p><b>系统判定</b>：' + esc(c.verdict_zh || '暂无数据') + '</p>'
      + '<p class="wrap-any"><b>原文链接</b>：' + source + '</p>'
      + '<p class="note">样本内回看，仅用于展示证据链，不是策略业绩。</p>';
    $('#case-dialog-title').textContent = (c.company_zh || '案例详情') + ' · ' + (c.date || '');
    if (typeof dlg.showModal === 'function') { dlg.showModal(); } else { dlg.setAttribute('open', ''); }
  }

  // ------------------------------------------------------------------- replay
  function replayCapital() {
    return num(obj(R.meta).capital) || num(obj(obj(M.trading).meta).capital) || 100000;
  }
  function replayTrades(cost) {
    var byCost = obj(R.trades_by_cost);
    var list = arr(byCost[cost]);
    if (!list.length && replaySteps.length) {
      list = replaySteps.filter(function (s) { return s.pnl_by_cost && s.pnl_by_cost[cost] !== undefined; })
        .map(function (s) {
          return {ticker: s.ticker, company_zh: s.company_zh, kind: s.kind, kind_zh: s.kind_zh,
                  entry_date: s.fill_date, exit_date: s.exit_date, ret: s.gross_return,
                  pnl: num(obj(s.pnl_by_cost)[cost]), price_source: s.price_source,
                  url: s.url, side: s.side, timestamp_quality: s.timestamp_quality};
        });
    }
    return list;
  }
  function filteredReplayTrades() {
    var rows = replayTrades(state.replay.cost);
    return rows.filter(function (t) {
      var year = (/^(\d{4})/.exec(String(t.entry_date || t.exit_date || '')) || [])[1] || '';
      if (state.replay.year !== 'all' && year !== state.replay.year) { return false; }
      if (state.replay.kind !== 'all' && String(t.kind || '') !== state.replay.kind) { return false; }
      return matches([t.ticker, t.company_zh, t.kind, t.kind_zh]);
    });
  }
  function equityPoints(trades) {
    var capital = replayCapital();
    var rows = trades.slice().sort(function (a, b) {
      return String(a.exit_date || a.entry_date || '').localeCompare(String(b.exit_date || b.entry_date || ''));
    });
    var points = [{date: String(obj(R.window).start || ''), equity: capital}];
    var equity = capital;
    rows.forEach(function (t) {
      var pnl = num(t.pnl);
      if (pnl === null) { return; }
      equity += pnl;
      points.push({date: String(t.exit_date || t.entry_date || ''), equity: equity});
    });
    return points;
  }
  function equitySvg(points) {
    if (points.length < 2) { return empty('暂无净值数据'); }
    var width = 920, height = 280, left = 70, right = width - 16, top = 20, bottom = height - 34;
    var values = points.map(function (p) { return p.equity; });
    var low = Math.min.apply(null, values), high = Math.max.apply(null, values);
    if (high - low < 1) { low -= 1; high += 1; }
    function x(i) { return left + (right - left) * i / (points.length - 1); }
    function y(v) { return top + (bottom - top) * (1 - (v - low) / (high - low)); }
    var svg = '<svg class="chart" viewBox="0 0 ' + width + ' ' + height + '" role="img" aria-label="回放净值曲线">';
    for (var g = 0; g <= 4; g += 1) {
      var v = high - (high - low) * g / 4;
      var yy = y(v);
      svg += '<line class="grid" x1="' + left + '" y1="' + yy.toFixed(1) + '" x2="' + right + '" y2="' + yy.toFixed(1) + '"/>';
      svg += '<text x="' + (left - 8) + '" y="' + (yy + 4).toFixed(1) + '" text-anchor="end">' + esc(compactInt(v)) + '</text>';
    }
    var line = points.map(function (p, i) { return x(i).toFixed(1) + ',' + y(p.equity).toFixed(1); }).join(' ');
    var area = 'M ' + x(0).toFixed(1) + ',' + bottom + ' L ' + line.replace(/ /g, ' L ') + ' L ' + x(points.length - 1).toFixed(1) + ',' + bottom + ' Z';
    svg += '<path class="area" d="' + area + '"/><polyline class="line" points="' + line + '"/>';
    svg += '<circle class="dot" cx="' + x(points.length - 1).toFixed(1) + '" cy="' + y(points[points.length - 1].equity).toFixed(1) + '" r="3.5"/>';
    svg += '<text class="val" x="' + (x(points.length - 1) - 4).toFixed(1) + '" y="' + (y(points[points.length - 1].equity) - 10).toFixed(1)
      + '" text-anchor="end">' + esc(fmtInt(points[points.length - 1].equity)) + '</text>';
    svg += '<text x="' + left + '" y="' + (height - 10) + '">' + esc(points[0].date || '') + '</text>';
    svg += '<text x="' + right + '" y="' + (height - 10) + '" text-anchor="end">' + esc(points[points.length - 1].date || '') + '</text>';
    return svg + '</svg>';
  }
  function replayStats(trades) {
    var capital = replayCapital();
    var pnls = trades.map(function (t) { return num(t.pnl); }).filter(function (v) { return v !== null; });
    var total = pnls.reduce(function (a, b) { return a + b; }, 0);
    var wins = pnls.filter(function (v) { return v > 0; }).length;
    var points = equityPoints(trades);
    var peak = capital, maxDd = 0;
    points.forEach(function (p) {
      peak = Math.max(peak, p.equity);
      maxDd = Math.min(maxDd, p.equity / peak - 1);
    });
    return {
      n: pnls.length,
      total_return: total / capital,
      max_drawdown: maxDd,
      win_rate: pnls.length ? wins / pnls.length : null,
      final_equity: capital + total
    };
  }
  function renderReplay() {
    var trades = replayTrades(state.replay.cost);
    var years = {};
    replaySteps.forEach(function (s) {
      var y = (/^(\d{4})/.exec(String(s.signal_date || s.fill_date || '')) || [])[1];
      if (y) { years[y] = true; }
    });
    var kinds = {};
    replaySteps.forEach(function (s) { if (s.kind) { kinds[s.kind] = s.kind_zh || s.kind; } });
    var yearSel = $('#replay-year'), kindSel = $('#replay-kind');
    if (yearSel && !yearSel.getAttribute('data-filled')) {
      yearSel.innerHTML = '<option value="all">全部年份</option>' + Object.keys(years).sort().reverse().map(function (y) {
        return '<option value="' + esc(y) + '">' + esc(y) + '</option>';
      }).join('');
      yearSel.value = state.replay.year;
      yearSel.setAttribute('data-filled', '1');
    }
    if (kindSel && !kindSel.getAttribute('data-filled')) {
      kindSel.innerHTML = '<option value="all">全部类型</option>' + Object.keys(kinds).sort().map(function (k) {
        return '<option value="' + esc(k) + '">' + esc(kinds[k]) + '</option>';
      }).join('');
      kindSel.value = state.replay.kind;
      kindSel.setAttribute('data-filled', '1');
    }
    $$('#replay-costs .btn').forEach(function (b) {
      b.classList.toggle('active', b.getAttribute('data-cost') === state.replay.cost);
    });
    var filtered = filteredReplayTrades();
    var stats = replayStats(filtered);
    $('#replay-stats').innerHTML = statGrid([
      {label: '成本档', value: state.replay.cost + ' bps'},
      {label: '筛选后成交', value: fmtInt(stats.n) + ' 笔', html: esc(fmtInt(stats.n)) + ' 笔'},
      {label: '区间总收益', html: signHtml(stats.total_return)},
      {label: '最大回撤', html: signHtml(stats.max_drawdown)},
      {label: '胜率', value: pct(stats.win_rate)},
      {label: '期末净值', value: fmtInt(stats.final_equity)}
    ]);
    $('#replay-chart').innerHTML = equitySvg(equityPoints(filtered));
    $('#replay-count').textContent = '筛选 ' + filtered.length + ' / ' + trades.length + ' 笔成交';
    renderTable('#replay-table', 'replay', [
      {key: 'entry_date', label: '入场日', get: function (t) { return t.entry_date; }, fmt: function (v) { return esc(v || '暂无数据'); }},
      {key: 'ticker', label: '代码', get: function (t) { return t.ticker; }, fmt: function (v) { return esc(v || '—'); }},
      {key: 'company_zh', label: '公司', get: function (t) { return t.company_zh; }, fmt: function (v) { return esc(v || '暂无数据'); }},
      {key: 'kind', label: '类型', get: function (t) { return t.kind; }, fmt: function (v, t) {
        return esc(KIND_LABELS[String(v)] || t.kind_zh || String(v || '暂无数据')); }},
      {key: 'side', label: '方向', get: function (t) { return t.side; }, fmt: function (v) { return esc(v === 'short' ? '做空 ▼' : '做多 ▲'); }},
      {key: 'entry_price', label: '成交价', cls: 'num', get: function (t) { return num(t.entry_price); }, fmt: function (v) { return esc(fmtNum(v, 2)); }},
      {key: 'gross_return', label: '毛收益', cls: 'num', get: function (t) { return num(t.ret); }, fmt: function (v) { return signHtml(v); }},
      {key: 'pnl', label: '成本后 PnL', cls: 'num', get: function (t) { return num(t.pnl); }, fmt: function (v) {
        return '<span class="v ' + (num(v) > 0 ? 'up' : (num(v) < 0 ? 'down' : 'flat')) + '">' + esc(v === null ? '暂无数据' : (num(v) > 0 ? '+' : '') + fmtInt(v)) + '</span>'; }},
      {key: 'price_source', label: '价格来源', get: function (t) { return t.price_source; }, fmt: function (v) {
        var label = SOURCE_LABELS[String(v)] || String(v || '暂无数据');
        var cls = v === 'intraday' ? 'warn' : 'ok';
        return '<span class="badge ' + (v ? cls : '') + '">' + esc(label) + '</span>'; }},
      {key: 'exit_date', label: '出场日', get: function (t) { return t.exit_date; }, fmt: function (v) { return esc(v || '暂无数据'); }}
    ], filtered, {key: 'entry_date', dir: -1});
    var skipped = replaySteps.filter(function (s) { return !s.pnl_by_cost || !Object.keys(s.pnl_by_cost).length; });
    $('#replay-skipped').innerHTML = skipped.length
      ? '<p class="note">回放共 ' + replaySteps.length + ' 步，其中 ' + skipped.length + ' 步观望/跳过（无价格、无仓位或方向不支持），不计入成交表。</p>'
      : '';
  }

  // --------------------------------------------------------------------- data
  function kvTable(rows) {
    if (!rows.length) { return empty(); }
    return '<div class="table-wrap"><table class="kv"><tbody>' + rows.map(function (row) {
      return '<tr><th>' + esc(row[0]) + '</th><td>' + (row[2] ? row[1] : esc(row[1])) + '</td></tr>';
    }).join('') + '</tbody></table></div>';
  }
  function renderData() {
    var meta = obj(M.meta);
    var status = obj(meta.data_status);
    var parts = [];
    var sourceRows = Object.keys(status).map(function (key) { return [key, status[key]]; });
    parts.push('<div class="panel"><h2>数据源状态</h2>' + kvTable(sourceRows) + '</div>');

    var coverage = [];
    var dc = obj(obj(M.device).coverage);
    if (Object.keys(dc).length) {
      Object.keys(dc).forEach(function (k) { coverage.push(['device.coverage.' + k, fmtInt(dc[k])]); });
    }
    var pc = obj(obj(M.products).coverage);
    if (Object.keys(pc).length) {
      Object.keys(pc).forEach(function (k) { coverage.push(['products.coverage.' + k, pc[k]]); });
    }
    parts.push('<div class="panel"><h2>覆盖率</h2>' + kvTable(coverage) + '</div>');

    var ts = obj(M.timestamps);
    var quality = obj(ts.by_quality);
    var qualityRows = Object.keys(quality).map(function (k) { return [k, fmtInt(quality[k])]; });
    if (ts.excluded_from_trading !== undefined) { qualityRows.push(['excluded_from_trading', fmtInt(ts.excluded_from_trading)]); }
    if (ts.policy) { qualityRows.push(['口径', ts.policy]); }
    var rq = obj(R.quality);
    if (rq.by_quality) {
      Object.keys(rq.by_quality).forEach(function (k) { qualityRows.push(['回放.' + k, fmtInt(rq.by_quality[k])]); });
    }
    parts.push('<div class="panel"><h2>时间质量</h2>' + kvTable(qualityRows) + '</div>');

    var auditRows = [];
    if (AUDIT) {
      Object.keys(AUDIT).forEach(function (k) {
        var v = AUDIT[k];
        auditRows.push([k, typeof v === 'object' ? JSON.stringify(v) : String(v)]);
      });
    }
    var ra = obj(R.audit);
    if (Object.keys(ra).length) {
      Object.keys(ra).forEach(function (k) { auditRows.push(['回放审计.' + k, String(ra[k])]); });
    }
    var skipped = obj(obj(C.stats).skipped);
    if (Object.keys(skipped).length) {
      Object.keys(skipped).forEach(function (k) { auditRows.push(['案例跳过.' + k, fmtInt(skipped[k])]); });
    }
    parts.push('<div class="panel"><h2>审计检查</h2>' + (auditRows.length ? kvTable(auditRows) : empty()) + '</div>');

    var split = obj(obj(M.research).sample_split);
    var splitRows = [];
    var bounds = obj(split.bounds);
    if (Object.keys(bounds).length) {
      Object.keys(bounds).forEach(function (label) {
        var b = obj(bounds[label]);
        splitRows.push([label, (b.start || '') + ' → ' + (b.end || '') + '，n=' + fmtInt(b.n) + '（' + fmtInt(b.n_days) + ' 天）']);
      });
      if (split.key) { splitRows.push(['切分键', split.key]); }
      if (split.no_overlap !== undefined) { splitRows.push(['无重叠', split.no_overlap ? '是' : '否']); }
    } else {
      Object.keys(split).forEach(function (k) { splitRows.push([k, typeof split[k] === 'object' ? JSON.stringify(split[k]) : String(split[k])]); });
    }
    parts.push('<div class="panel"><h2>样本划分</h2>' + kvTable(splitRows) + '</div>');

    var method = obj(R.method);
    var methodRows = [];
    Object.keys(method).forEach(function (k) {
      var v = method[k];
      if (v && typeof v === 'object') { return; }
      methodRows.push([k, String(v)]);
    });
    arr(obj(R.meta).notes_zh).forEach(function (note, i) { methodRows.push(['备注 ' + (i + 1), note]); });
    parts.push('<div class="panel"><h2>回放方法与假设</h2>' + kvTable(methodRows) + '</div>');

    var gapRows = [];
    gapRows.push(['NMPA / 中国侧', status.nmpa === 'loaded' ? '已加载' : '不可用（NMPA 数据未加载）——中国空白度不推断，缺失值保持 null']);
    gapRows.push(['赛道未映射事件', fmtInt(dc.unmapped_track_events)]);
    gapRows.push(['公司未匹配事件', fmtInt(dc.unmapped_company_events)]);
    arr(obj(obj(R.meta).skip_reasons) && Object.keys(obj(R.meta).skip_reasons).map(function (k) {
      return ['回放跳过：' + k, fmtInt(obj(R.meta).skip_reasons[k])];
    })).forEach(function (row) { gapRows.push(row); });
    gapRows.push(['说明', '未映射/未匹配事件保留在事实库中，不计入赛道或公司动量，属已知口径缺口。']);
    parts.push('<div class="panel"><h2>缺口说明</h2>' + kvTable(gapRows) + '</div>');

    var sources = obj(DATA.sources);
    var sourceRows2 = Object.keys(sources).map(function (key) {
      var s = obj(sources[key]);
      return [key, (s.exists ? '已加载' : '缺失') + ' · ' + fmtInt(s.bytes) + ' B · ' + (s.path || '')];
    });
    parts.push('<div class="panel"><h2>输入文件</h2>' + kvTable(sourceRows2) + '<p class="note">构建时间：'
      + esc(DATA.generated_at || '暂无数据') + '；所有数据内联在单个 HTML 中，无网络请求。</p></div>');
    $('#data-body').innerHTML = parts.join('');
  }

  // ------------------------------------------------------------------- router
  function activate(view, push) {
    if (VIEWS.indexOf(view) === -1) { view = 'overview'; }
    state.view = view;
    $$('.nav-btn').forEach(function (b) { b.classList.toggle('active', b.getAttribute('data-nav') === view); });
    $$('.view').forEach(function (v) { v.classList.toggle('active', v.getAttribute('data-view') === view); });
    var title = $('#view-title');
    if (title) { title.textContent = TITLES[view] || view; }
    if (push !== false && location.hash !== '#' + view) { location.hash = view; }
    renderCurrentView();
    var content = $('#content');
    if (content && content.scrollIntoView) { /* keep scroll position; no jump */ }
  }
  function renderCurrentView() {
    if (state.view === 'overview') { renderOverview(); }
    else if (state.view === 'tracks') { renderTracks(); }
    else if (state.view === 'companies') { renderCompanies(); }
    else if (state.view === 'products') { renderProducts(); }
    else if (state.view === 'cases') { renderCases(); }
    else if (state.view === 'replay') { renderReplay(); }
    else if (state.view === 'data') { renderData(); }
    updateSearchCount();
  }
  function updateSearchCount() {
    var el = $('#search-count');
    if (!el) { return; }
    if (!state.q) { el.textContent = ''; return; }
    var n = 0;
    trackList.forEach(function (t) { if (matches([t.name_zh, t.name_en, t.track_id])) { n += 1; } });
    companyList.forEach(function (c) { if (matches([c.name_zh, c.name_en, c.key, c.ticker])) { n += 1; } });
    familyList.forEach(function (f) { if (matches([f.name_zh, f.name_en, f.family_id, f.category])) { n += 1; } });
    newProductList.forEach(function (p) { if (matches([p.device_name_zh, p.company_zh, p.family_zh, p.code, p.k_number])) { n += 1; } });
    allCases.forEach(function (c) { if (matches([c.company_zh, c.ticker, c.event_zh, c.category])) { n += 1; } });
    el.textContent = '全局匹配 ' + n + ' 条';
  }
  function updateTheme(theme) {
    state.theme = theme;
    document.documentElement.setAttribute('data-theme', theme);
    var btn = $('#theme-toggle');
    if (btn) { btn.textContent = theme === 'dark' ? '☀ 浅色' : '🌙 深色'; }
    try { localStorage.setItem('medradar-theme', theme); } catch (err) { /* ignore */ }
  }

  // ------------------------------------------------------------------- events
  document.addEventListener('click', function (event) {
    var target = event.target;
    var nav = target.closest ? target.closest('[data-nav]') : null;
    if (nav) { activate(nav.getAttribute('data-nav'), true); return; }
    var sortBtn = target.closest ? target.closest('[data-sort-table]') : null;
    if (sortBtn) {
      var tableId = sortBtn.getAttribute('data-sort-table');
      var key = sortBtn.getAttribute('data-sort-key');
      var current = state.sort[tableId];
      state.sort[tableId] = {key: key, dir: current && current.key === key ? -current.dir : -1};
      renderCurrentView();
      return;
    }
    var costBtn = target.closest ? target.closest('[data-cost]') : null;
    if (costBtn) {
      state.replay.cost = costBtn.getAttribute('data-cost');
      renderReplay();
      return;
    }
    var caseCard = target.closest ? target.closest('[data-case-id]') : null;
    if (caseCard) { openCase(caseCard.getAttribute('data-case-id')); return; }
    var themeBtn = target.closest ? target.closest('#theme-toggle') : null;
    if (themeBtn) { updateTheme(state.theme === 'dark' ? 'light' : 'dark'); return; }
    var closeBtn = target.closest ? target.closest('[data-close-dialog]') : null;
    if (closeBtn) { var dlg = $('#case-dialog'); if (dlg && dlg.close) { dlg.close(); } return; }
  });

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') {
      var openDialog = $('#case-dialog');
      if (openDialog && openDialog.open) { openDialog.close(); event.preventDefault(); }
      return;
    }
    if (event.key === 'Enter' || event.key === ' ') {
      var card = event.target.closest ? event.target.closest('[data-case-id]') : null;
      if (card) { event.preventDefault(); openCase(card.getAttribute('data-case-id')); }
    }
  });

  var search = $('#global-search');
  if (search) {
    search.addEventListener('input', function (e) {
      state.q = String(e.target.value || '').trim().toLowerCase();
      renderCurrentView();
    });
    search.addEventListener('keydown', function (e) { if (e.key === 'Escape') { search.value = ''; state.q = ''; renderCurrentView(); } });
  }
  ['case-category', 'case-year', 'case-outcome', 'case-sort'].forEach(function (id) {
    var el = document.getElementById(id);
    if (!el) { return; }
    el.addEventListener('change', function (e) {
      var key = id.replace('case-', '');
      state.cases[key === 'sort' ? 'sort' : key] = e.target.value;
      renderCases();
    });
  });
  ['replay-year', 'replay-kind'].forEach(function (id) {
    var el = document.getElementById(id);
    if (!el) { return; }
    el.addEventListener('change', function (e) {
      state.replay[id === 'replay-year' ? 'year' : 'kind'] = e.target.value;
      renderReplay();
    });
  });
  var dialog = $('#case-dialog');
  if (dialog) {
    dialog.addEventListener('click', function (event) {
      var rect = dialog.getBoundingClientRect();
      var inside = event.clientX >= rect.left && event.clientX <= rect.right && event.clientY >= rect.top && event.clientY <= rect.bottom;
      if (!inside) { dialog.close(); }
    });
  }
  window.addEventListener('hashchange', function () {
    var view = location.hash.replace('#', '');
    if (view !== state.view) { activate(view, false); }
  });

  // -------------------------------------------------------------------- boot
  var stored = null;
  try { stored = localStorage.getItem('medradar-theme'); } catch (err) { stored = null; }
  updateTheme(stored === 'light' ? 'light' : 'dark');
  var initial = location.hash.replace('#', '');
  activate(VIEWS.indexOf(initial) !== -1 ? initial : 'overview', false);
  if (location.hash === '' && history.replaceState) {
    history.replaceState(null, '', '#' + state.view);
  }
})();
"""


# --------------------------------------------------------------------------- HTML
_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="MedRadar dashboard.py">
<meta name="description" content="MedRadar 交互式看板：赛道、公司、产品、案例库、回放与数据审计。">
<title>__TITLE__</title>
<link rel="icon" href="data:,">
<style>__CSS__</style>
</head>
<body>
<noscript><div class="noscript"><strong>需要启用 JavaScript。</strong><br>
本看板是交互式单页应用，所有数据已内联在 HTML 中；请启用 JavaScript 后刷新页面。静态报告见 <a href="index.html">docs/index.html</a>。</div></noscript>
<div class="app">
  <aside class="sidebar">
    <div class="brand"><span class="dot"></span>MedRadar<small>交互式看板</small></div>
    <nav class="nav" aria-label="视图导航">
      <button class="nav-btn" data-nav="overview"><span><span class="ico">◎</span> 概览</span><span class="badge-n">KPI</span></button>
      <button class="nav-btn" data-nav="tracks"><span><span class="ico">◇</span> 赛道</span></button>
      <button class="nav-btn" data-nav="companies"><span><span class="ico">▣</span> 公司</span></button>
      <button class="nav-btn" data-nav="products"><span><span class="ico">⬡</span> 产品</span></button>
      <button class="nav-btn" data-nav="cases"><span><span class="ico">❝</span> 案例库</span></button>
      <button class="nav-btn" data-nav="replay"><span><span class="ico">↗</span> 回放</span></button>
      <button class="nav-btn" data-nav="data"><span><span class="ico">⚙</span> 数据</span></button>
    </nav>
    <div class="side-foot">
      <div class="side-actions"><button class="btn" id="theme-toggle" type="button">☀ 浅色</button>
      <a class="btn" href="index.html">静态报告</a></div>
      <div>构建：__BUILT_AT__</div>
      <div>零外部依赖 · 可离线打开</div>
      <div>由 DeepSeek Harness · deepseek-flash 全程自主构建</div>
    </div>
  </aside>
  <div class="main">
    <div class="topbar">
      <h1 class="view-title" id="view-title">概览</h1>
      <div class="search-wrap">
        <span aria-hidden="true">⌕</span>
        <input id="global-search" type="search" placeholder="全局搜索：赛道 / 公司 / 产品 / 案例…" autocomplete="off" aria-label="全局搜索">
      </div>
      <span class="search-count" id="search-count"></span>
    </div>
    <main class="content" id="content">
      <section class="view" id="view-overview" data-view="overview" aria-label="概览"><div id="overview-body"></div></section>
      <section class="view" id="view-tracks" data-view="tracks" aria-label="赛道">
        <div class="panel"><div class="row spread"><h2>赛道热度榜</h2><span class="note" id="tracks-count"></span></div>
        <div class="table-wrap-note note">点击表头排序；THI 与 95% CI 需一起解读。搜索框为全局搜索。</div>
        <div id="tracks-table"></div></div>
      </section>
      <section class="view" id="view-companies" data-view="companies" aria-label="公司">
        <div class="panel"><div class="row spread"><h2>大厂与公司动量</h2><span class="note" id="companies-count"></span></div>
        <div id="companies-table"></div></div>
      </section>
      <section class="view" id="view-products" data-view="products" aria-label="产品">
        <div class="panel"><div class="row spread"><h2>产品族热度</h2><span class="note" id="families-count"></span></div>
        <div id="families-table"></div></div>
        <div class="panel"><div class="row spread"><h2>新品雷达</h2><span class="note" id="radar-count"></span></div>
        <div class="radar-grid" id="radar-grid"></div></div>
      </section>
      <section class="view" id="view-cases" data-view="cases" aria-label="案例库">
        <div class="panel">
          <div class="row spread"><h2>案例库与证据</h2><span class="note" id="cases-count"></span></div>
          <div class="filters">
            <label>分类 <select id="case-category"></select></label>
            <label>年份 <select id="case-year"></select></label>
            <label>结果 <select id="case-outcome"></select></label>
            <label>排序 <select id="case-sort">
              <option value="date_desc">日期（新→旧）</option>
              <option value="p20_desc">20 日涨幅（高→低）</option>
              <option value="p20_asc">20 日涨幅（低→高）</option>
              <option value="p60_desc">60 日涨幅（高→低）</option>
            </select></label>
          </div>
          <div class="cards" id="cases-grid"></div>
        </div>
      </section>
      <section class="view" id="view-replay" data-view="replay" aria-label="回放">
        <div class="panel">
          <div class="row spread"><h2>回放研究</h2><span class="note" id="replay-count"></span></div>
          <div class="row" id="replay-costs" style="margin-bottom:10px">
            <span class="note">交易成本（单边 bps）：</span>
            <button class="btn" type="button" data-cost="10">10 bps</button>
            <button class="btn" type="button" data-cost="25">25 bps</button>
            <button class="btn" type="button" data-cost="50">50 bps</button>
          </div>
          <div class="filters">
            <label>年份 <select id="replay-year"></select></label>
            <label>类型 <select id="replay-kind"></select></label>
            <span class="note">成本档影响 PnL / 净值；年份与类型同时过滤成交表与曲线。</span>
          </div>
          <div id="replay-stats"></div>
          <div id="replay-chart"></div>
          <div id="replay-table" style="margin-top:10px"></div>
          <div id="replay-skipped"></div>
        </div>
      </section>
      <section class="view" id="view-data" data-view="data" aria-label="数据"><div id="data-body"></div></section>
    </main>
  </div>
</div>
<dialog id="case-dialog" aria-labelledby="case-dialog-title">
  <div class="dlg-head"><h2 id="case-dialog-title">案例详情</h2>
  <button class="dlg-close" type="button" data-close-dialog>关闭 ✕</button></div>
  <div class="dlg-body" id="case-dialog-body"></div>
</dialog>
<script type="application/json" id="dashboard-data">__DATA__</script>
<script>__JS__</script>
</body>
</html>
"""


if __name__ == "__main__":  # pragma: no cover - local build example
    import argparse

    parser = argparse.ArgumentParser(description="Build the MedRadar interactive dashboard.")
    parser.add_argument("--metrics", default=str(DEFAULT_METRICS))
    parser.add_argument("--cases", default=str(DEFAULT_CASES))
    parser.add_argument("--replay", default=str(DEFAULT_REPLAY))
    parser.add_argument("--out", default="out/dashboard.html")
    parser.add_argument("--audit", default=None)
    args = parser.parse_args()
    result = build_dashboard(
        metrics_path=args.metrics,
        cases_path=args.cases,
        replay_path=args.replay,
        out_path=args.out,
        audit_path=args.audit,
    )
    print(json.dumps(result, ensure_ascii=False, indent=1))
