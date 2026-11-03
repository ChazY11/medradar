/* Reusable presentation components: page headers, panels, tables, badges,
   states, notices, chips, segmented switches and the event drawer shell. */
import { el, esc, fmtInt, keyValueText } from "./util.js";
import { friendlyError } from "./api.js";

/* ------------------------------------------------------------- headers */
export function pageHead({ title, kicker, badges = [], subtitle, captions = [], actions = [], testid = null }) {
  const head = el("div", { class: "page-head" });
  const main = el("div", { class: "page-head-main" });
  if (kicker) main.append(el("div", { class: "breadcrumb" }, kicker));
  const titleRow = el("h1", { class: "page-title" });
  titleRow.append(document.createTextNode(title));
  for (const item of badges) titleRow.append(item);
  main.append(titleRow);
  if (subtitle) main.append(el("div", { class: "page-sub", text: subtitle }));
  if (captions.length) {
    const row = el("div", { class: "page-captions" });
    for (const caption of captions) {
      if (!caption) continue;
      const node = el("span", { class: "cap" });
      if (caption.label) node.append(el("span", { class: "muted", text: caption.label }));
      if (caption.value instanceof Node) node.append(caption.value);
      else node.append(el("b", { text: String(caption.value == null ? "—" : caption.value) }));
      row.append(node);
    }
    main.append(row);
  }
  head.append(main);
  if (actions.length) head.append(el("div", { class: "page-actions" }, ...actions));
  if (testid) head.dataset.testid = testid;
  return head;
}

export function breadcrumb(items) {
  const node = el("span");
  items.forEach((item, index) => {
    if (index > 0) node.append(el("span", { class: "sep", text: "/" }));
    if (item.href) node.append(el("a", { href: item.href, text: item.label }));
    else node.append(el("span", { text: item.label }));
  });
  return node;
}

/* -------------------------------------------------------------- panels */
export function panel({ title = null, sub = null, right = null, body = null, note = null, foot = null, className = "", dense = false, testid = null }) {
  const node = el("section", { class: `panel ${className}`.trim() });
  if (testid) node.dataset.testid = testid;
  if (title || right) {
    const head = el("div", { class: "panel-head" });
    const text = el("div");
    if (title) text.append(el("div", { class: "panel-title", text: title }));
    if (sub) text.append(el("div", { class: "panel-sub", text: sub }));
    head.append(text);
    if (right) head.append(el("div", { class: "panel-right" }, ...(Array.isArray(right) ? right : [right])));
    node.append(head);
  }
  if (body) {
    const bodyNode = el("div", { class: `panel-body${dense ? " dense" : ""}` });
    if (body instanceof Node) bodyNode.append(body);
    else if (Array.isArray(body)) bodyNode.append(...body);
    else bodyNode.append(document.createTextNode(String(body)));
    node.append(bodyNode);
  }
  if (note) node.append(el("div", { class: "panel-note" }, ...(Array.isArray(note) ? note : [note])));
  if (foot) node.append(el("div", { class: "panel-foot" }, ...(Array.isArray(foot) ? foot : [foot])));
  return node;
}

/* ----------------------------------------------------------------- KPI */
export function kpi({ label, value, sub = null, tone = null, sm = false, hint = null, testid = null }) {
  const node = el("div", { class: "kpi", title: hint || null });
  if (testid) node.dataset.testid = testid;
  node.append(el("div", { class: "kpi-label", text: label }));
  const valueNode = el("div", { class: `kpi-value${sm ? " sm" : ""}${tone ? ` ${tone}` : ""}` });
  if (value instanceof Node) valueNode.append(value);
  else valueNode.textContent = String(value == null ? "—" : value);
  node.append(valueNode);
  if (sub) {
    const subNode = el("div", { class: "kpi-sub" });
    if (sub instanceof Node) subNode.append(sub);
    else subNode.textContent = sub;
    node.append(subNode);
  }
  return node;
}

/* --------------------------------------------------------------- badges */
export const TIER_TONES = { observed: "badge-blue", detected: "badge-amber", hypothesis: "badge-violet" };

export function badge(text, tone = "muted", title = null) {
  const cls = tone && tone !== "muted" ? `badge badge-${tone}` : "badge";
  return el("span", { class: cls, text: String(text == null ? "—" : text), title });
}

export function tierBadge(tier, label) {
  const tone = TIER_TONES[tier] || "muted";
  return badge(label || tier || "未标注", tone, `证据等级：${label || tier}`);
}

export function toneBadge(tone) {
  const map = { blocked: ["badge-red", "blocked"], mixed: ["badge-amber", "mixed"], negative: ["badge-red", "negative"], positive: ["badge-green", "positive"] };
  return map[tone] || map.negative;
}

/* --------------------------------------------------------------- tables */
function cellValue(column, row, index) {
  if (typeof column.format === "function") return column.format(row, index);
  const value = column.key.split(".").reduce((acc, key) => (acc == null ? acc : acc[key]), row);
  return value;
}

export function dataTable({
  columns,
  rows,
  rowClick = null,
  empty = "该筛选下没有记录",
  className = "",
  caption = null,
  rowAttrs = null,
  testid = null,
  compact = true,
}) {
  if (!rows || !rows.length) {
    return el("div", { class: "empty" }, el("div", { class: "empty-title", text: "没有记录" }), el("div", { text: empty }));
  }
  const wrap = el("div", { class: "table-wrap" });
  if (testid) wrap.dataset.testid = testid;
  const table = el("table", { class: `data${compact ? " compact" : ""} ${className}`.trim() });
  const thead = el("thead");
  const headRow = el("tr");
  for (const column of columns) {
    headRow.append(el("th", {
      class: [column.align === "right" || column.num ? "num" : "", column.className || ""].join(" ").trim() || null,
      style: column.width ? `width:${column.width}` : null,
      text: column.label,
    }));
  }
  thead.append(headRow);
  table.append(thead);
  const tbody = el("tbody");
  rows.forEach((row, index) => {
    const tr = el("tr");
    if (rowClick) {
      tr.classList.add("clickable");
      tr.tabIndex = 0;
      tr.addEventListener("click", () => rowClick(row, index));
      tr.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          rowClick(row, index);
        }
      });
    }
    if (rowAttrs) {
      const attrs = rowAttrs(row, index) || {};
      for (const [key, value] of Object.entries(attrs)) {
        if (value == null) continue;
        if (key === "testid") tr.dataset.testid = value;
        else if (key === "dataset") Object.assign(tr.dataset, value);
        else tr.setAttribute(key, value);
      }
    }
    for (const column of columns) {
      const td = el("td", {
        class: [column.align === "right" || column.num ? "num" : "", column.cellClass || ""].join(" ").trim() || null,
      });
      const value = cellValue(column, row, index);
      if (value instanceof Node) td.append(value);
      else td.textContent = value == null || value === "" ? "—" : String(value);
      tr.append(td);
    }
    tbody.append(tr);
  });
  table.append(tbody);
  wrap.append(table);
  if (caption) wrap.append(el("div", { class: "panel-note", text: caption }));
  return wrap;
}

export function kvList(rows) {
  const node = el("div");
  for (const row of rows) {
    if (!row) continue;
    const line = el("div", { class: "kv-row" });
    line.append(el("div", { class: "kv-key", text: row.key }));
    const value = el("div", { class: "kv-val" });
    if (row.value instanceof Node) value.append(row.value);
    else value.textContent = row.value == null || row.value === "" ? "—" : String(row.value);
    line.append(value);
    node.append(line);
  }
  return node;
}

export function defList(items) {
  const dl = el("dl", { class: "def-list" });
  for (const item of items) {
    if (!item) continue;
    dl.append(el("div", { class: "def" },
      el("dt", { text: item.key }),
      el("dd", null, item.value instanceof Node ? item.value : document.createTextNode(item.value == null ? "—" : String(item.value))),
    ));
  }
  return dl;
}

/* --------------------------------------------------------------- states */
export function skeletonPage() {
  const node = el("div");
  node.append(el("div", { class: "skeleton" },
    el("div", { class: "sk-line", style: "width:34%;height:14px" }),
    el("div", { class: "sk-line", style: "width:18%;width:22%" }),
  ));
  const kpis = el("div", { class: "kpi-grid mt-12" });
  for (let index = 0; index < 6; index += 1) kpis.append(el("div", { class: "kpi" }, el("div", { class: "sk-line", style: "width:60%" }), el("div", { class: "sk-line", style: "width:40%;height:18px" })));
  node.append(kpis);
  const grid = el("div", { class: "grid grid-2 mt-12" });
  for (let index = 0; index < 2; index += 1) grid.append(el("div", { class: "skeleton" }, el("div", { class: "sk-block" })));
  node.append(grid);
  return node;
}

export function skeletonBlock(lines = 4, height = null) {
  const node = el("div", { class: "skeleton" });
  if (height) node.append(el("div", { class: "sk-block", style: `height:${height}px` }));
  else {
    for (let index = 0; index < lines; index += 1) {
      node.append(el("div", { class: "sk-line", style: `width:${88 - index * 9}%` }));
    }
  }
  return node;
}

export function loadingInline(label = "加载中…") {
  return el("div", { class: "panel" }, el("div", { class: "panel-body" }, el("div", { class: "empty", text: label })));
}

export function emptyState(text, { title = "没有记录", actionLabel = null, onAction = null } = {}) {
  const node = el("div", { class: "empty" });
  node.append(el("div", { class: "empty-title", text: title }), el("div", { text }));
  if (actionLabel && onAction) {
    node.append(el("div", { class: "mt-8" }, el("button", { type: "button", class: "btn btn-sm", text: actionLabel, onclick: onAction })));
  }
  return node;
}

export function errorState(error, onRetry = null, { title = "数据加载失败" } = {}) {
  const box = el("div", { class: "error-box" });
  box.append(el("div", { class: "error-title", text: title }));
  box.append(el("div", { text: friendlyError(error) }));
  if (error && error.detail) box.append(el("div", { class: "error-detail", text: String(error.detail) }));
  if (onRetry) {
    box.append(el("button", { type: "button", class: "btn btn-sm", text: "重试", onclick: onRetry }));
  }
  return el("div", { class: "panel" }, el("div", { class: "panel-body" }, box));
}

/* -------------------------------------------------------------- notices */
export function notice({ tone = "muted", title = null, body = null, items = null, label = null, testid = null }) {
  const node = el("div", { class: `notice notice-${tone}` });
  if (testid) node.dataset.testid = testid;
  if (title || label) {
    const head = el("div", { class: "notice-title" });
    if (title) head.append(document.createTextNode(title));
    if (label) head.append(badge(label, tone === "muted" ? "muted" : tone));
    node.append(head);
  }
  if (body) node.append(el("div", { class: "notice-body" }, body instanceof Node ? body : document.createTextNode(String(body))));
  if (items && items.length) {
    const ul = el("ul");
    for (const item of items) ul.append(el("li", null, item instanceof Node ? item : document.createTextNode(String(item))));
    node.append(ul);
  }
  return node;
}

/* --------------------------------------------------------------- chips */
export function chip(label, { active = false, onClick = null, title = null, testid = null, dataset = null } = {}) {
  const node = el("button", {
    type: "button",
    class: `chip${active ? " active" : ""}`,
    title: title || null,
    onclick: onClick || null,
  });
  if (testid) node.dataset.testid = testid;
  if (dataset) Object.assign(node.dataset, dataset);
  node.append(el("span", { text: label }));
  return node;
}

export function staticChip(label, { tone = null, title = null } = {}) {
  return el("span", { class: `chip chip-static${tone ? ` badge-${tone}` : ""}`, text: label, title: title || null });
}

export function segmented(options, value, onChange) {
  const node = el("div", { class: "seg", role: "group" });
  for (const option of options) {
    const optionValue = typeof option === "object" ? option.value : option;
    const label = typeof option === "object" ? option.label : String(option);
    const button = el("button", {
      type: "button",
      class: `seg-btn${String(optionValue) === String(value) ? " active" : ""}`,
      text: label,
      title: typeof option === "object" ? option.title || null : null,
      onclick: () => onChange(optionValue),
    });
    if (typeof option === "object" && option.testid) button.dataset.testid = option.testid;
    node.append(button);
  }
  return node;
}

/* ------------------------------------------------------------ disclosure */
export function disclosure(summary, content, { open = false } = {}) {
  const details = el("details", { class: "disclosure" });
  if (open) details.open = true;
  details.append(el("summary", { text: summary }));
  const body = el("div", { class: "disclosure-body" });
  if (content instanceof Node) body.append(content);
  else body.append(document.createTextNode(String(content)));
  details.append(body);
  return details;
}

/* ---------------------------------------------------------------- misc */
export function codeBlock(lines) {
  const list = Array.isArray(lines) ? lines : [lines];
  return el("pre", { class: "code-block", text: list.filter((line) => line != null && line !== "").join("\n") });
}

export function list(items) {
  const ul = el("ul", { class: "bullets" });
  for (const item of items || []) {
    if (item == null) continue;
    ul.append(el("li", null, item instanceof Node ? item : document.createTextNode(String(item))));
  }
  return ul;
}

export function linkButton(href, label, { primary = false, title = null, testid = null } = {}) {
  const node = el("a", {
    class: `btn${primary ? " btn-primary" : ""}`,
    href,
    text: label,
    title: title || null,
  });
  if (testid) node.dataset.testid = testid;
  return node;
}

export function textButton(label, onClick, { primary = false, small = true, testid = null, title = null, disabled = false } = {}) {
  const node = el("button", {
    type: "button",
    class: `btn${primary ? " btn-primary" : ""}${small ? " btn-sm" : ""}`,
    text: label,
    title: title || null,
    disabled,
    onclick: onClick,
  });
  if (testid) node.dataset.testid = testid;
  return node;
}

export function valueTable(value, depth = 0) {
  if (value == null) return el("span", { class: "muted", text: "—" });
  if (Array.isArray(value)) {
    if (!value.length) return el("span", { class: "muted", text: "（空）" });
    if (value.every((item) => item == null || typeof item !== "object")) {
      return el("div", null, value.map((item) => el("div", { class: "mono", text: keyValueText(item) })));
    }
    return el("div", null, value.map((item, index) => disclosure(`[${index}] ${typeof item === "object" ? keyValueText(Object.keys(item)[0]) : ""}`, valueTable(item, depth + 1))));
  }
  if (typeof value === "object") {
    const entries = Object.entries(value);
    if (!entries.length) return el("span", { class: "muted", text: "（空）" });
    const rows = el("div");
    for (const [key, item] of entries) {
      const row = el("div", { class: "kv-row" });
      row.append(el("div", { class: "kv-key", text: key }));
      const val = el("div", { class: "kv-val" });
      if (item != null && typeof item === "object") val.append(valueTable(item, depth + 1));
      else val.textContent = keyValueText(item);
      row.append(val);
      rows.append(row);
    }
    return rows;
  }
  return el("span", { text: keyValueText(value) });
}

/* --------------------------------------------------------------- drawer */
export function openDrawer({ title, sub = null, body = null, wide = false }) {
  const drawer = document.getElementById("drawer");
  const backdrop = document.getElementById("drawer-backdrop");
  if (!drawer || !backdrop) return;
  drawer.replaceChildren();
  drawer.classList.toggle("wide", Boolean(wide));
  const head = el("div", { class: "drawer-head" });
  const text = el("div");
  text.append(el("div", { class: "drawer-title", text: title || "详情" }));
  if (sub) text.append(el("div", { class: "drawer-sub", text: sub }));
  head.append(text, el("button", { type: "button", class: "drawer-close", text: "✕", title: "关闭 (Esc)", onclick: () => closeDrawer() }));
  const bodyNode = el("div", { class: "drawer-body" });
  if (body instanceof Node) bodyNode.append(body);
  else if (body) bodyNode.append(document.createTextNode(body));
  drawer.append(head, bodyNode);
  drawer.hidden = false;
  backdrop.hidden = false;
  document.body.style.overflow = "hidden";
  const close = drawer.querySelector(".drawer-close");
  if (close) close.focus();
}

export function closeDrawer() {
  const drawer = document.getElementById("drawer");
  const backdrop = document.getElementById("drawer-backdrop");
  if (drawer && !drawer.hidden) {
    drawer.hidden = true;
    drawer.replaceChildren();
  }
  if (backdrop) backdrop.hidden = true;
  document.body.style.overflow = "";
}

export function drawerIsOpen() {
  const drawer = document.getElementById("drawer");
  return Boolean(drawer && !drawer.hidden);
}
