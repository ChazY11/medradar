/* Small DOM / formatting / routing helpers shared by every page. */

export const KIND_LABELS = {
  "510k": "510(k)",
  pma: "PMA",
  device_recall: "器械召回",
  trial: "临床试验",
  "8k_catalyst": "8-K 公司事件",
  drug_approval: "药品批准",
  track_first: "赛道首次记录",
};

export const SERIES_COLORS = ["#2f81f7", "#2dd4bf", "#d29922", "#f85149", "#3fb950", "#a371f7"];

export function esc(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[c]));
}

/** Create an element: el('div', {class:'x', text:'y', onclick: fn, dataset:{k:'v'}}, child, ...) */
export function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  if (attrs) {
    for (const [key, value] of Object.entries(attrs)) {
      if (value == null || value === false) continue;
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else if (key === "html") node.innerHTML = value;
      else if (key === "dataset") Object.assign(node.dataset, value);
      else if (key.startsWith("on") && typeof value === "function") {
        node.addEventListener(key.slice(2), value);
      } else if (key in node && key !== "title" && key !== "href" && key !== "for") {
        try { node[key] = value; } catch { node.setAttribute(key, value); }
      } else {
        node.setAttribute(key, value === true ? "" : value);
      }
    }
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function frag(...children) {
  const node = document.createDocumentFragment();
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

/** Delegate an event on root: on(root, 'click', '[data-x]', handler) */
export function on(root, type, selector, handler, options) {
  root.addEventListener(type, (event) => {
    const target = event.target.closest(selector);
    if (!target || !root.contains(target)) return;
    handler(event, target);
  }, options);
}

export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

export function debounce(fn, ms) {
  let timer = null;
  return function debounced(...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), ms);
  };
}

export function fmtInt(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return Number(value).toLocaleString("en-US");
}

export function fmtNum(value, digits = 2) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return Number(value).toFixed(digits);
}

export function fmtSigned(value, formatter = fmtInt) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  const n = Number(value);
  return (n > 0 ? "+" : "") + formatter(n);
}

export function fmtPct(value, digits = 1) {
  if (value == null || Number.isNaN(Number(value)) || !Number.isFinite(Number(value))) return "—";
  return `${(Number(value) * 100).toFixed(digits)}%`;
}

export function fmtPctSigned(value, digits = 1) {
  if (value == null || Number.isNaN(Number(value)) || !Number.isFinite(Number(value))) return "—";
  const n = Number(value) * 100;
  return `${n > 0 ? "+" : ""}${n.toFixed(digits)}%`;
}

export function fmtDate(value) {
  if (!value) return "—";
  return String(value).slice(0, 10);
}

export function fmtDateTime(value) {
  if (!value) return "—";
  return String(value).replace("T", " ").replace(/(\.\d+)?(Z|[+-]\d\d:?\d\d)$/, "").slice(0, 16);
}

export function fmtRange(first, last) {
  if (!first && !last) return "—";
  if (!first || !last) return `${fmtDate(first || last)}`;
  return `${fmtDate(first)} → ${fmtDate(last)}`;
}

export function toneForDelta(delta) {
  if (delta == null || Number.isNaN(Number(delta)) || Number(delta) === 0) return "tone-flat";
  return Number(delta) > 0 ? "tone-up" : "tone-down";
}

export function truncate(text, max = 120) {
  const value = String(text == null ? "" : text);
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}

export function kindLabel(kind) {
  return KIND_LABELS[kind] || kind || "—";
}

export function keyValueText(value) {
  if (value == null || value === "") return "—";
  if (Array.isArray(value)) return value.length ? value.map((v) => keyValueText(v)).join("、") : "—";
  if (typeof value === "object") return JSON.stringify(value);
  if (typeof value === "boolean") return value ? "是" : "否";
  return String(value);
}

export function qs(params) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params || {})) {
    if (value == null || value === "" || value === false) continue;
    if (Array.isArray(value)) {
      if (!value.length) continue;
      search.set(key, value.join(","));
    } else if (typeof value === "boolean") {
      search.set(key, value ? "true" : "false");
    } else {
      search.set(key, String(value));
    }
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export function buildHash(path, params) {
  return `#${path.startsWith("/") ? path : `/${path}`}${qs(params)}`;
}

export function parseHash() {
  const raw = location.hash || "#/overview";
  const withoutHash = raw.slice(1);
  const qIndex = withoutHash.indexOf("?");
  const path = (qIndex === -1 ? withoutHash : withoutHash.slice(0, qIndex)) || "/overview";
  const query = new URLSearchParams(qIndex === -1 ? "" : withoutHash.slice(qIndex + 1));
  return { raw, path, query };
}

/** Convert '2024-Q1' or '2024' into inclusive ISO date range. */
export function periodRange(period) {
  const match = /^(\d{4})(?:-Q([1-4]))?$/.exec(String(period || ""));
  if (!match) return null;
  const year = Number(match[1]);
  const quarter = match[2] ? Number(match[2]) : null;
  if (quarter) {
    const startMonth = (quarter - 1) * 3 + 1;
    const endMonth = startMonth + 2;
    const endDay = new Date(Date.UTC(year, endMonth, 0)).getUTCDate();
    return {
      start: `${year}-${String(startMonth).padStart(2, "0")}-01`,
      end: `${year}-${String(endMonth).padStart(2, "0")}-${String(endDay).padStart(2, "0")}`,
    };
  }
  return { start: `${year}-01-01`, end: `${year}-12-31` };
}

export function normalizeCompanyList(value) {
  if (!value) return [];
  if (Array.isArray(value)) return value.filter(Boolean);
  return String(value).split(",").map((part) => part.trim()).filter(Boolean);
}

export function sum(values) {
  return (values || []).reduce((total, value) => total + (Number(value) || 0), 0);
}

export function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

export function unique(list) {
  return Array.from(new Set(list));
}
