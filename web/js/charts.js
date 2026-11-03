/* Inline SVG charts: hover tooltips with exact values + click-through.
   No external chart library, no canvas. */
import { el, esc, fmtInt, clamp } from "./util.js";

const SVG_NS = "http://www.w3.org/2000/svg";
const active = [];
let resizeTimer = null;

function svgEl(tag, attrs) {
  const node = document.createElementNS(SVG_NS, tag);
  if (attrs) {
    for (const [key, value] of Object.entries(attrs)) {
      if (value == null) continue;
      node.setAttribute(key, String(value));
    }
  }
  return node;
}

/* ----------------------------------------------------------- tooltip */
function tipNode() {
  let node = document.getElementById("chart-tip");
  if (!node) {
    node = el("div", { class: "chart-tip", id: "chart-tip" });
    node.hidden = true;
    document.body.append(node);
  }
  return node;
}

export function showTip(html, clientX, clientY) {
  const node = tipNode();
  node.innerHTML = html;
  node.hidden = false;
  const rect = node.getBoundingClientRect();
  let left = clientX + 14;
  let top = clientY + 16;
  if (left + rect.width > window.innerWidth - 8) left = clientX - rect.width - 12;
  if (top + rect.height > window.innerHeight - 8) top = clientY - rect.height - 12;
  node.style.left = `${Math.max(6, left)}px`;
  node.style.top = `${Math.max(6, top)}px`;
}

export function hideTip() {
  const node = document.getElementById("chart-tip");
  if (node) node.hidden = true;
}

function tipRow(label, value, color) {
  return `<div class="tip-row"><span>${color ? `<span class="tip-swatch" style="background:${color}"></span>` : ""}${esc(label)}</span><b>${esc(value)}</b></div>`;
}

/* ---------------------------------------------------------- registry */
const observers = [];

export function reset() {
  active.length = 0;
  for (const observer of observers) observer.disconnect();
  observers.length = 0;
  hideTip();
}

export function register(host, redraw) {
  active.push({ host, redraw });
}

function observeSize(host, redraw) {
  if (typeof ResizeObserver === "undefined") return;
  let lastWidth = host.clientWidth;
  const observer = new ResizeObserver(() => {
    const width = host.clientWidth;
    if (!host.isConnected || width <= 0) return;
    if (Math.abs(width - lastWidth) < 4) return;
    lastWidth = width;
    try { redraw(); } catch { /* keep the page alive */ }
  });
  observer.observe(host);
  observers.push(observer);
}

function chartWidth(host) {
  const own = host.clientWidth;
  if (own > 0) return own;
  const parent = host.parentElement;
  if (parent && parent.clientWidth > 0) return Math.max(260, parent.clientWidth - 24);
  return 600;
}

if (typeof window !== "undefined") {
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      for (const item of active) {
        if (item.host.isConnected) {
          try { item.redraw(); } catch { /* keep the page alive */ }
        }
      }
    }, 120);
  });
}

/* ------------------------------------------------------------- scales */
function niceTicks(maxValue, count = 4) {
  const max = Number(maxValue) > 0 ? Number(maxValue) : 1;
  const rough = max / count;
  const magnitude = Math.pow(10, Math.floor(Math.log10(rough)));
  const normalized = rough / magnitude;
  let step;
  if (normalized <= 1) step = magnitude;
  else if (normalized <= 2) step = 2 * magnitude;
  else if (normalized <= 5) step = 5 * magnitude;
  else step = 10 * magnitude;
  const top = Math.max(step, Math.ceil(max / step) * step);
  const ticks = [];
  for (let value = 0; value <= top + step * 1e-9; value += step) ticks.push(value);
  return { ticks, top, step };
}

function xLabelIndices(count, width) {
  if (count <= 1) return [0];
  const maxLabels = width < 420 ? 5 : width < 720 ? 7 : 10;
  const step = Math.max(1, Math.ceil(count / maxLabels));
  const indices = [];
  for (let i = 0; i < count; i += step) indices.push(i);
  if (indices[indices.length - 1] !== count - 1) {
    if (count - 1 - indices[indices.length - 1] < step * 0.6) indices.pop();
    indices.push(count - 1);
  }
  return indices;
}

function yAxis(svg, { left, top, plotW, plotH, ticks, topValue, format }) {
  const g = svgEl("g");
  for (const tick of ticks) {
    const y = top + plotH - (tick / topValue) * plotH;
    g.append(svgEl("line", { class: "grid-line", x1: left, x2: left + plotW, y1: y, y2: y }));
    const label = svgEl("text", {
      class: "axis-label", x: left - 6, y: y + 3.5, "text-anchor": "end",
    });
    label.textContent = format(tick);
    g.append(label);
  }
  svg.append(g);
}

/* ------------------------------------------------------- period flags */
let patternSeq = 0;

function lagHatch(svg) {
  const id = `lag-hatch-${++patternSeq}`;
  const defs = svgEl("defs");
  const pattern = svgEl("pattern", {
    id, width: 6, height: 6, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)",
  });
  pattern.append(svgEl("line", { x1: 0, y1: 0, x2: 0, y2: 6, stroke: "#d29922", "stroke-width": 1.3, "stroke-opacity": 0.55 }));
  defs.append(pattern);
  svg.append(defs);
  return `url(#${id})`;
}

/** Shade partial and source-lag periods behind the plotted series. */
function renderPeriodBands(svg, { pad, plotH, bands, partialFlags = [], lagFlags = [] }) {
  const hasPartial = partialFlags.some(Boolean);
  const hasLag = lagFlags.some(Boolean);
  if (!hasPartial && !hasLag) return;
  const pattern = hasLag ? lagHatch(svg) : null;
  for (const band of bands) {
    const { index, x, width } = band;
    const partial = Boolean(partialFlags[index]);
    const lag = Boolean(lagFlags[index]);
    if (partial) {
      const rect = svgEl("rect", {
        class: "period-partial", x, y: pad.top, width, height: plotH,
        fill: "rgba(210, 153, 34, 0.07)",
      });
      rect.append(svgEl("title"));
      rect.lastChild.textContent = "不完整周期：窗口边界截断，仅展示，不参与同比/份额/LQ";
      svg.append(rect);
    } else if (lag) {
      const rect = svgEl("rect", {
        class: "period-lag", x, y: pad.top, width, height: plotH, fill: pattern,
      });
      rect.append(svgEl("title"));
      rect.lastChild.textContent = "日历周期完整，但临近数据截止，源数据可能仍会修订/补录";
      svg.append(rect);
    }
  }
}

function periodFlagNoteHtml(index, partialFlags, lagFlags) {
  let html = "";
  if (partialFlags && partialFlags[index]) {
    html += `<div class="tip-row tip-flag"><span>周期状态</span><b>不完整（仅展示）</b></div>`;
  }
  if (lagFlags && lagFlags[index]) {
    html += `<div class="tip-row tip-flag"><span>周期状态</span><b>临近数据截止 · 源可能修订</b></div>`;
  }
  return html;
}

function flagLegendNode(partialFlags = [], lagFlags = []) {
  const hasPartial = partialFlags.some(Boolean);
  const hasLag = lagFlags.some(Boolean);
  if (!hasPartial && !hasLag) return null;
  const node = el("div", { class: "chart-note chart-flags" });
  if (hasPartial) {
    node.append(el("span", { class: "flag-item" },
      el("span", { class: "flag-swatch flag-partial", "aria-hidden": "true" }),
      el("span", { text: "浅色底/空心点 = 不完整周期（仅展示，不参与比较）" }),
    ));
  }
  if (hasLag) {
    node.append(el("span", { class: "flag-item" },
      el("span", { class: "flag-swatch flag-lag", "aria-hidden": "true" }),
      el("span", { text: "斜线底/琥珀点 = 日历完整但临近数据截止，源数据可能修订" }),
    ));
  }
  return node;
}

function lineBands(categories, x, plotW) {
  const count = categories.length;
  if (!count) return [];
  if (count === 1) return [{ index: 0, x: x(0), width: plotW }];
  const step = plotW / (count - 1);
  return categories.map((_, index) => {
    const left = Math.max(x(0), x(index) - step / 2);
    const right = Math.min(x(count - 1), x(index) + step / 2);
    return { index, x: left, width: Math.max(1, right - left) };
  });
}

/* --------------------------------------------------------- line chart */
export function lineChart(host, cfg) {
  host.classList.add("chart");
  host.replaceChildren();
  const {
    categories = [],
    series = [],
    height = 220,
    valueFormat = fmtInt,
    onSelect = null,
    showLegend = true,
    legendNote = null,
  } = cfg;
  const partialFlags = cfg.partialFlags || [];
  const lagFlags = cfg.lagFlags || [];

  if (!categories.length || !series.length) {
    host.append(el("div", { class: "empty", text: "该窗口内没有可绘制的数据" }));
    return;
  }

  const state = { hidden: new Set(), hover: -1 };
  const legend = el("div", { class: "chart-legend" });
  const svgWrap = el("div");
  host.append(legend, svgWrap);
  if (legendNote) host.append(el("div", { class: "chart-note" }, legendNote));
  const lineFlags = flagLegendNode(partialFlags, lagFlags);
  if (lineFlags) host.append(lineFlags);

  function renderLegend() {
    legend.replaceChildren();
    for (const item of series) {
      const off = state.hidden.has(item.key);
      const button = el("button", {
        type: "button",
        class: `legend-item${off ? " off" : ""}`,
        title: off ? "点击显示该系列" : "点击隐藏该系列",
        onclick: () => {
          if (state.hidden.has(item.key)) state.hidden.delete(item.key);
          else state.hidden.add(item.key);
          renderLegend();
          draw();
        },
      }, el("span", { class: "legend-swatch", style: `background:${item.color || "#2f81f7"}` }), el("span", { text: item.label || item.key }));
      legend.append(button);
    }
  }

  function render(width) {
    const visible = series.filter((item) => !state.hidden.has(item.key));
    const pad = { top: 10, right: 14, bottom: 26, left: 48 };
    const plotW = Math.max(60, width - pad.left - pad.right);
    const plotH = Math.max(70, height - pad.top - pad.bottom);
    let maxValue = 0;
    for (const item of visible) {
      for (const value of item.values || []) {
        if (value != null && Number.isFinite(Number(value))) maxValue = Math.max(maxValue, Number(value));
      }
    }
    const { ticks, top } = niceTicks(maxValue);
    const count = categories.length;
    const x = (index) => pad.left + (count === 1 ? plotW / 2 : (index / (count - 1)) * plotW);
    const y = (value) => pad.top + plotH - (Number(value) / top) * plotH;

    const svg = svgEl("svg", {
      viewBox: `0 0 ${width} ${height}`, width: "100%", height,
      role: "img", "aria-label": cfg.ariaLabel || "趋势图",
    });
    if (cfg.svgTestid) svg.dataset.testid = cfg.svgTestid;
    svg.style.height = `${height}px`;
    yAxis(svg, { left: pad.left, top: pad.top, plotW, plotH, ticks, topValue: top, format: valueFormat });
    renderPeriodBands(svg, {
      pad, plotH,
      bands: lineBands(categories, x, plotW),
      partialFlags, lagFlags,
    });

    for (const index of xLabelIndices(count, width)) {
      const text = svgEl("text", { class: "axis-label", x: x(index), y: height - 8, "text-anchor": "middle" });
      text.textContent = categories[index];
      svg.append(text);
    }

    for (const item of visible) {
      const values = item.values || [];
      const points = [];
      let segment = [];
      const flush = () => {
        if (segment.length) {
          points.push(segment);
          segment = [];
        }
      };
      for (let index = 0; index < count; index += 1) {
        const value = values[index];
        if (value == null || !Number.isFinite(Number(value))) {
          flush();
          continue;
        }
        segment.push([x(index), y(value), index]);
      }
      flush();
      points.forEach((part, partIndex) => {
        const dashed = partialFlags[part[0][2]] || partialFlags[part[part.length - 1][2]];
        const d = part.map((point, index) => `${index === 0 ? "M" : "L"}${point[0].toFixed(1)},${point[1].toFixed(1)}`).join(" ");
        const path = svgEl("path", {
          class: "series-line", d,
          stroke: item.color || "#2f81f7",
          "stroke-linejoin": "round", "stroke-linecap": "round",
        });
        if (dashed) path.setAttribute("stroke-dasharray", "3 3");
        svg.append(path);
      });
      if (count <= 60) {
        for (let index = 0; index < count; index += 1) {
          const value = values[index];
          if (value == null || !Number.isFinite(Number(value))) continue;
          const partial = partialFlags[index];
          const lag = lagFlags[index];
          const cx = x(index);
          const cy = y(value);
          if (lag && !partial) {
            const size = 3.1;
            const diamond = svgEl("path", {
              class: "series-dot series-lag",
              d: `M${cx} ${cy - size}L${cx + size} ${cy}L${cx} ${cy + size}L${cx - size} ${cy}Z`,
              fill: "#0a0f16", stroke: "#d29922", "stroke-width": 1.2,
            });
            diamond.append(svgEl("title"));
            diamond.lastChild.textContent = "日历周期完整，但临近数据截止，源数据可能修订";
            svg.append(diamond);
          } else {
            svg.append(svgEl("circle", {
              class: "series-dot", cx, cy, r: 2.4,
              fill: partial ? "#0a0f16" : (item.color || "#2f81f7"),
              stroke: item.color || "#2f81f7",
            }));
          }
        }
      }
    }

    const crosshair = svgEl("line", {
      class: "crosshair", x1: 0, x2: 0, y1: pad.top, y2: pad.top + plotH, visibility: "hidden",
    });
    svg.append(crosshair);

    const bandWidth = plotW / Math.max(1, count);
    for (let index = 0; index < count; index += 1) {
      const rect = svgEl("rect", {
        class: "hit", x: pad.left + index * bandWidth, y: pad.top,
        width: bandWidth, height: plotH,
      });
      rect.addEventListener("mousemove", (event) => {
        state.hover = index;
        const cx = x(index);
        crosshair.setAttribute("x1", cx);
        crosshair.setAttribute("x2", cx);
        crosshair.setAttribute("visibility", "visible");
        const rows = visible
          .filter((item) => item.values && item.values[index] != null)
          .map((item) => tipRow(item.label || item.key, valueFormat(item.values[index]), item.color));
        if (!rows.length) {
          hideTip();
          return;
        }
        const total = visible.reduce((acc, item) => acc + (Number(item.values?.[index]) || 0), 0);
        let html = `<div class="tip-title">${esc(categories[index])}</div>${rows.join("")}`;
        if (visible.length > 1) {
          html += `<div class="tip-row" style="border-top:1px solid #1e2a3a;margin-top:3px;padding-top:3px"><span>合计</span><b>${esc(valueFormat(total))}</b></div>`;
        }
        html += periodFlagNoteHtml(index, partialFlags, lagFlags);
        showTip(html, event.clientX, event.clientY);
      });
      rect.addEventListener("mouseleave", () => {
        state.hover = -1;
        crosshair.setAttribute("visibility", "hidden");
        hideTip();
      });
      rect.addEventListener("click", () => {
        if (onSelect) onSelect(categories[index], index);
      });
      svg.append(rect);
    }

    svgWrap.replaceChildren(svg);
  }

  function draw() {
    if (!host.isConnected) return;
    render(chartWidth(host));
  }

  renderLegend();
  register(host, () => render(chartWidth(host)));
  observeSize(host, () => render(chartWidth(host)));
  draw();
  setTimeout(draw, 0);
  setTimeout(draw, 120);
}

/* ---------------------------------------------------- grouped bar chart */
export function barChart(host, cfg) {
  host.classList.add("chart");
  host.replaceChildren();
  const {
    categories = [],
    series = [],
    height = 230,
    valueFormat = fmtInt,
    onSelect = null,
    stacked = false,
    ariaLabel = "柱状图",
    legendNote = null,
  } = cfg;
  const partialFlags = cfg.partialFlags || [];
  const lagFlags = cfg.lagFlags || [];

  if (!categories.length || !series.length) {
    host.append(el("div", { class: "empty", text: "该窗口内没有可绘制的数据" }));
    return;
  }

  const state = { hidden: new Set() };
  const legend = el("div", { class: "chart-legend" });
  const svgWrap = el("div");
  host.append(legend, svgWrap);
  if (legendNote) host.append(el("div", { class: "chart-note" }, legendNote));
  const barFlags = flagLegendNode(partialFlags, lagFlags);
  if (barFlags) host.append(barFlags);

  function renderLegend() {
    legend.replaceChildren();
    if (series.length <= 1) return;
    for (const item of series) {
      const off = state.hidden.has(item.key);
      legend.append(el("button", {
        type: "button",
        class: `legend-item${off ? " off" : ""}`,
        onclick: () => {
          if (state.hidden.has(item.key)) state.hidden.delete(item.key);
          else state.hidden.add(item.key);
          renderLegend();
          draw();
        },
      }, el("span", { class: "legend-swatch", style: `background:${item.color || "#2f81f7"}` }), el("span", { text: item.label || item.key })));
    }
  }

  function render(width) {
    const visible = series.filter((item) => !state.hidden.has(item.key));
    const pad = { top: 10, right: 14, bottom: 26, left: 48 };
    const plotW = Math.max(60, width - pad.left - pad.right);
    const plotH = Math.max(70, height - pad.top - pad.bottom);
    const count = categories.length;
    let maxValue = 0;
    if (stacked) {
      for (let index = 0; index < count; index += 1) {
        maxValue = Math.max(maxValue, visible.reduce((acc, item) => acc + (Number(item.values?.[index]) || 0), 0));
      }
    } else {
      for (const item of visible) {
        for (const value of item.values || []) {
          if (value != null) maxValue = Math.max(maxValue, Number(value));
        }
      }
    }
    const { ticks, top } = niceTicks(maxValue);
    const band = plotW / count;
    const groupPad = stacked ? band * 0.22 : band * 0.16;
    const innerW = band - groupPad * 2;
    const barW = stacked ? innerW : Math.max(2, innerW / Math.max(1, visible.length));

    const svg = svgEl("svg", {
      viewBox: `0 0 ${width} ${height}`, width: "100%", height,
      role: "img", "aria-label": ariaLabel,
    });
    if (cfg.svgTestid) svg.dataset.testid = cfg.svgTestid;
    svg.style.height = `${height}px`;
    yAxis(svg, { left: pad.left, top: pad.top, plotW, plotH, ticks, topValue: top, format: valueFormat });
    renderPeriodBands(svg, {
      pad, plotH,
      bands: categories.map((_, index) => ({ index, x: pad.left + index * band, width: band })),
      partialFlags, lagFlags,
    });

    const y = (value) => pad.top + plotH - (Number(value) / top) * plotH;
    for (const index of xLabelIndices(count, width)) {
      const text = svgEl("text", {
        class: "axis-label", x: band * index + band / 2, y: height - 8, "text-anchor": "middle",
      });
      const partial = partialFlags[index];
      const lag = lagFlags[index];
      text.textContent = partial ? `${categories[index]} *` : lag ? `${categories[index]} †` : categories[index];
      if (partial || lag) {
        text.append(svgEl("title"));
        text.lastChild.textContent = partial
          ? "不完整周期：窗口边界截断，仅展示，不参与同比/份额/LQ"
          : "日历周期完整，但临近数据截止，源数据可能修订";
      }
      svg.append(text);
    }

    for (let index = 0; index < count; index += 1) {
      let stackTop = 0;
      visible.forEach((item, seriesIndex) => {
        const value = Number(item.values?.[index]) || 0;
        if (value <= 0) return;
        let barX;
        let barY;
        let barH;
        if (stacked) {
          barX = pad.left + index * band + groupPad;
          barH = (value / top) * plotH;
          barY = pad.top + plotH - (stackTop + value) / top * plotH;
          stackTop += value;
        } else {
          barX = pad.left + index * band + groupPad + seriesIndex * barW;
          barH = (value / top) * plotH;
          barY = pad.top + plotH - barH;
        }
        const rect = svgEl("rect", {
          class: "bar", x: barX, y: barY, width: Math.max(1, barW - 0.5), height: Math.max(1, barH),
          fill: item.color || "#2f81f7", rx: 0.5,
        });
        rect.addEventListener("mousemove", (event) => {
          const rows = [tipRow(item.label || item.key, valueFormat(value), item.color)];
          if (stacked) {
            const total = visible.reduce((acc, other) => acc + (Number(other.values?.[index]) || 0), 0);
            rows.push(`<div class="tip-row" style="border-top:1px solid #1e2a3a;margin-top:3px;padding-top:3px"><span>合计</span><b>${esc(valueFormat(total))}</b></div>`);
          }
          showTip(`<div class="tip-title">${esc(categories[index])}</div>${rows.join("")}${periodFlagNoteHtml(index, partialFlags, lagFlags)}`, event.clientX, event.clientY);
        });
        rect.addEventListener("mouseleave", hideTip);
        rect.addEventListener("click", () => {
          if (onSelect) onSelect(categories[index], index, item.key);
        });
        svg.append(rect);
      });
      // full-band hit area: gaps between bars are still clickable for the category
      const hit = svgEl("rect", {
        class: "hit", x: pad.left + index * band, y: pad.top, width: band, height: plotH,
      });
      hit.addEventListener("mousemove", (event) => {
        const rows = visible.map((item) => tipRow(item.label || item.key, valueFormat(Number(item.values?.[index]) || 0), item.color));
        const total = visible.reduce((acc, item) => acc + (Number(item.values?.[index]) || 0), 0);
        if (visible.length > 1 && !stacked) {
          rows.push(`<div class="tip-row" style="border-top:1px solid #1e2a3a;margin-top:3px;padding-top:3px"><span>合计</span><b>${esc(valueFormat(total))}</b></div>`);
        }
        showTip(`<div class="tip-title">${esc(categories[index])}</div>${rows.join("")}${periodFlagNoteHtml(index, partialFlags, lagFlags)}`, event.clientX, event.clientY);
      });
      hit.addEventListener("mouseleave", hideTip);
      hit.addEventListener("click", () => {
        if (onSelect) onSelect(categories[index], index, null);
      });
      svg.append(hit);
    }

    svgWrap.replaceChildren(svg);
  }

  function draw() {
    if (!host.isConnected) return;
    render(chartWidth(host));
  }

  renderLegend();
  register(host, () => render(chartWidth(host)));
  observeSize(host, () => render(chartWidth(host)));
  draw();
  setTimeout(draw, 0);
  setTimeout(draw, 120);
}

/* ----------------------------------------------------------- sparkline */
export function sparkline(values, { width = 120, height = 26, color = "#2f81f7", labels = null } = {}) {
  const svg = svgEl("svg", {
    class: "spark", viewBox: `0 0 ${width} ${height}`, width, height,
    preserveAspectRatio: "none", role: "img", "aria-label": "季度趋势迷你图",
  });
  const numbers = (values || []).map((value) => (value == null ? null : Number(value)));
  const valid = numbers.filter((value) => value != null);
  if (valid.length < 2) {
    const text = svgEl("text", { x: width / 2, y: height / 2 + 3, "text-anchor": "middle", class: "axis-label" });
    text.textContent = "无数据";
    svg.append(text);
    return svg;
  }
  const min = Math.min(...valid);
  const max = Math.max(...valid);
  const span = max - min || 1;
  const stepX = width / (numbers.length - 1);
  const points = [];
  numbers.forEach((value, index) => {
    if (value == null) return;
    const px = index * stepX;
    const py = height - 3 - ((value - min) / span) * (height - 6);
    points.push([px, py]);
  });
  const d = points.map((point, index) => `${index === 0 ? "M" : "L"}${point[0].toFixed(1)},${point[1].toFixed(1)}`).join(" ");
  svg.append(svgEl("path", { d, fill: "none", stroke: color, "stroke-width": 1.3, "stroke-linejoin": "round" }));
  const last = points[points.length - 1];
  svg.append(svgEl("circle", { cx: last[0], cy: last[1], r: 1.8, fill: color }));
  const title = svgEl("title");
  const seriesLabels = labels || numbers.map((_, index) => `第 ${index + 1} 期`);
  title.textContent = numbers
    .map((value, index) => `${seriesLabels[index] || index}: ${value == null ? "—" : value}`)
    .join(" · ");
  svg.append(title);
  return svg;
}

export { SVG_NS, svgEl };
