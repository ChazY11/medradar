/* #/radar/{track} — track detail: quarterly composition chart, company mix,
   first-time entrants, detected signals, recent events, coverage captions. */
import { api } from "../api.js";
import { el, fmtInt, fmtPct, fmtPctSigned, fmtSigned, fmtDate, buildHash, periodRange, toneForDelta } from "../util.js";
import {
  pageHead, panel, badge, dataTable, notice, list, errorState, skeletonBlock,
  linkButton, emptyState, kpi,
} from "../components.js";
import { barChart } from "../charts.js";
import { openEvent, eventRowAttrs, eventRowButton } from "../event.js";

export async function mount(root, ctx) {
  const trackId = ctx.params.track;
  const choices = (ctx.meta.window_choices || []).filter((value) => Number(value) > 0);
  const windows = choices.length ? choices.map(Number) : [3, 5, 10];
  let years = Number(ctx.query.get("years") || 10);
  if (!windows.includes(years)) {
    years = windows.includes(10) ? 10 : windows[windows.length - 1];
  }

  const wrapper = el("div");
  wrapper.dataset.testid = "track-detail";
  wrapper.append(el("div", { class: "panel" }, el("div", { class: "panel-body" }, skeletonBlock(6))));
  root.replaceChildren(wrapper);

  let data;
  try {
    data = await api.radarTrack(trackId, years);
  } catch (error) {
    wrapper.replaceChildren(errorState(error, () => ctx.refresh(), { title: "赛道数据加载失败" }));
    return { title: "赛道详情" };
  }

  wrapper.replaceChildren();
  const track = data.track || {};
  const domain = data.domain || {};
  const totals = data.totals || {};
  const windowInfo = data.window || {};
  const series = data.series || {};

  /* --------------------------------------------------------------- header */
  wrapper.append(pageHead({
    kicker: el("span", null,
      el("a", { href: "#/radar", text: "技术雷达" }),
      el("span", { class: "sep", text: "/" }),
      el("a", { href: buildHash("/radar", { years }), text: domain.label_zh || "领域" }),
      el("span", { class: "sep", text: "/" }),
      el("span", { text: track.name_zh || trackId }),
    ),
    title: track.name_zh || trackId,
    badges: [
      track.name_en ? badge(track.name_en, "muted") : null,
      track.domain_label_zh ? badge(track.domain_label_zh, "violet") : null,
      totals.series_total_complete != null && totals.series_total_complete !== totals.recent
        ? badge(`序列合计 ${fmtInt(totals.series_total_complete)} ≠ 近窗 ${fmtInt(totals.recent)}`, "amber", "序列为季度粒度；与窗口合计存在边界差异")
        : null,
    ].filter(Boolean),
    subtitle: domain.blurb_zh || `该赛道的公开审批记录（510(k) + PMA）与统计探测信号。`,
    captions: [
      { label: "窗口", value: `${windowInfo.start || "—"} → ${windowInfo.end || "—"}` },
      { label: "对照窗口", value: `${windowInfo.prior_start || "—"} → ${windowInfo.prior_end || "—"}` },
      { label: "全时记录", value: fmtInt(totals.all_time) },
      { label: "粒度", value: "季度" },
    ],
    actions: [
      windowSeg(windows, years, (value) => ctx.go(`/radar/${trackId}`, { years: value })),
      linkButton(buildHash("/evidence", { track: trackId, metric: "approvals" }), "该赛道证据"),
    ],
  }));

  /* ----------------------------------------------------------------- KPIs */
  const kpiGrid = el("div", { class: "kpi-grid", style: "grid-template-columns:repeat(6,minmax(0,1fr))" });
  kpiGrid.append(
    kpi({ label: `近 ${years} 年记录`, value: fmtInt(totals.recent), sub: `510(k) + PMA · 含数据截止所在未完整季度` }),
    kpi({ label: "前窗记录", value: fmtInt(totals.prior), sub: `${windowInfo.prior_start || "—"} 起` }),
    kpi({
      label: "变化",
      value: fmtPctSigned(totals.pct_change),
      tone: toneForDelta(totals.delta),
      sub: `Δ ${fmtSigned(totals.delta)}`,
    }),
    kpi({ label: "全时记录", value: fmtInt(totals.all_time), sub: "数据覆盖期内" }),
    kpi({ label: "活跃企业", value: fmtInt((data.companies || []).length), sub: "窗口内有记录的企业" }),
    kpi({ label: "新进入企业", value: fmtInt((data.entrants || []).length), sub: "窗口内首次出现该赛道" }),
  );
  wrapper.append(kpiGrid);

  /* ---------------------------------------------------------------- chart */
  const chartBody = el("div");
  const categories = series.periods || [];
  const approvalByPeriod = new Map(((series.approvals || [])).map((point) => [point.period, point]));
  const kindSeries = series.by_kind || {};
  const kindKeys = Object.keys(kindSeries);
  const partialFlags = categories.map((period) => Boolean(approvalByPeriod.get(period)?.partial));

  if (!categories.length) {
    chartBody.append(emptyState("该窗口内没有季度记录。", { title: "无季度数据" }));
  } else if (kindKeys.length) {
    const colors = { "510k": "#2f81f7", pma: "#2dd4bf", device_recall: "#f85149" };
    barChart(chartBody, {
      categories,
      stacked: true,
      series: kindKeys.map((kind) => {
        const byPeriod = new Map((kindSeries[kind] || []).map((point) => [point.period, point.count]));
        return {
          key: kind,
          label: kind === "510k" ? "510(k)" : kind === "pma" ? "PMA" : kind,
          color: colors[kind] || "#d29922",
          values: categories.map((period) => byPeriod.get(period) ?? 0),
        };
      }),
      height: 250,
      svgTestid: "track-chart",
      ariaLabel: "赛道季度记录构成",
      onSelect: (period) => {
        const range = periodRange(period);
        ctx.go("/evidence", { track: trackId, metric: "approvals", start: range?.start, end: range?.end });
      },
    });
    const partialPeriods = categories.filter((period, index) => partialFlags[index]);
    const edgePeriod = quarterForDate(windowInfo.end);
    const partialText = partialPeriods.length
      ? `未完整周期：${partialPeriods.join("、")}（API partial 标记；计数仍显示，勿与完整季度直接比较）`
      : (edgePeriod && categories.includes(edgePeriod)
        ? `数据截止所在季度 ${edgePeriod} 未标记为完整（API 未返回 partial，比较时请谨慎）`
        : "所有周期均为完整季度");
    chartBody.append(el("div", { class: "chart-note" },
      el("span", { text: "堆叠：510(k) + PMA；点击季度 → 打开该季度的原始记录" }),
      el("span", { text: partialText }),
      el("span", { text: `${categories.length} 个季度（完整 ${categories.length - partialPeriods.length} 个）` }),
    ));
  } else {
    const approvals = series.approvals || [];
    lineChartFallback(chartBody, categories, approvals);
  }
  wrapper.append(panel({
    title: "季度审批记录构成",
    sub: `${windowInfo.start || "—"} → ${windowInfo.end || "—"} · 悬停查看精确值，点击打开证据`,
    body: chartBody,
  }));

  /* -------------------------------------------------------------- signals */
  const signals = data.signals || [];
  const signalBody = el("div");
  if (!signals.length) {
    signalBody.append(notice({
      tone: "muted",
      title: "该窗口内没有达到阈值的统计探测信号",
      body: data.method?.signal || "规则：季度记录数相对前 8 季度均值的 z 分数，|z| ≥ 2.5 且计数 ≥ 5 时标记。",
    }));
  } else {
    signalBody.append(list(signals.map((signal) => {
      const row = el("div", { class: "row wrap" });
      row.append(
        badge("Detected Signal", "amber"),
        el("b", { class: "mono", text: signal.period || "—" }),
        el("span", { text: `z = ${signal.z == null ? "—" : Number(signal.z).toFixed(2)}` }),
        el("span", { text: `当前季度 ${fmtInt(signal.current)}` }),
        el("span", { class: "muted", text: `基线均值 ${signal.baseline_mean == null ? "—" : Number(signal.baseline_mean).toFixed(2)}${signal.baseline_sd != null ? ` ± ${Number(signal.baseline_sd).toFixed(2)}` : ""}` }),
        badge(signal.direction === "up" ? "高于基线" : "低于基线", signal.direction === "up" ? "green" : "amber"),
      );
      return row;
    })));
    signalBody.append(el("div", { class: "panel-note", text: data.method?.signal || "" }));
  }
  wrapper.append(panel({
    title: "统计探测信号",
    sub: "检出 ≠ 因果 ≠ 预测；信号只描述记录数相对历史基线的偏离",
    body: signalBody,
  }));

  /* ---------------------------------------------------- company composition */
  const companyRows = data.companies || [];
  const totalRecent = Number(data.totals?.recent) || 0;
  const unattributed = Number(data.attribution?.unattributed_recent) || 0;
  const compositionRows = companyRows.slice();
  if (unattributed > 0) {
    compositionRows.push({
      company: null,
      name_zh: "未归属企业",
      n: unattributed,
      share: totalRecent ? unattributed / totalRecent : null,
      first: null,
      last: null,
      unattributed: true,
    });
  }
  const maxShare = compositionRows.reduce((max, row) => Math.max(max, row.share || 0), 0) || 1;
  const attributed = Number(data.attribution?.attributed_recent) || companyRows.reduce((sum, row) => sum + (Number(row.n) || 0), 0);
  const composition = dataTable({
    columns: [
      {
        key: "name_zh", label: "企业",
        format: (row) => el("span", null,
          row.company ? el("a", { class: "plain", href: buildHash(`/companies/${row.company}`) }, el("b", { text: row.name_zh || row.company })) : el("span", { class: "muted", text: row.name_zh || "未归属企业" }),
          row.featured ? badge("重点", "blue") : null,
        ),
      },
      { key: "n", label: "记录", num: true, format: (row) => fmtInt(row.n) },
      {
        key: "share", label: "赛道内份额", num: true,
        format: (row) => el("div", { class: "cell-bar" },
          el("span", { class: "mono tiny", text: fmtPct(row.share, 1) }),
          el("span", { class: "bar-track" }, el("span", { class: "bar-fill", style: `width:${Math.max(1, ((row.share || 0) / maxShare) * 100)}%` })),
        ),
      },
      { key: "first", label: "首次记录", format: (row) => (row.first ? fmtDate(row.first) : "—") },
      { key: "last", label: "最近记录", format: (row) => (row.last ? fmtDate(row.last) : "—") },
    ],
    rows: compositionRows,
    rowClick: (row) => {
      if (row.company) ctx.go("/evidence", { companies: row.company, track: trackId, metric: "approvals" });
    },
    empty: "该窗口内没有映射到该赛道的企业记录",
  });
  wrapper.append(panel({
    title: "企业构成",
    sub: `点击行 → 该企业在该赛道的原始记录 · 已归属 ${fmtInt(attributed)} / 赛道合计 ${fmtInt(totalRecent)} 条`,
    dense: true,
    body: composition,
    note: data.attribution?.note_zh || "企业构成只统计能归到具体企业的记录；未归属记录仍计入赛道总量与份额分母。",
  }));

  /* ------------------------------------------------------------- entrants */
  const entrants = data.entrants || [];
  wrapper.append(panel({
    title: "首次进入企业",
    sub: data.method?.entrant || "企业在窗口内出现该赛道的首条 510(k)/PMA 记录（数据覆盖期内）",
    dense: true,
    body: dataTable({
      columns: [
        { key: "name_zh", label: "企业", format: (row) => row.name_zh || row.company },
        { key: "first_date", label: "首次记录日", format: (row) => fmtDate(row.first_date) },
        { key: "n", label: "窗口内记录", num: true, format: (row) => fmtInt(row.n) },
      ],
      rows: entrants,
      rowClick: (row) => ctx.go("/evidence", { companies: row.company, track: trackId, metric: "approvals" }),
      empty: "该窗口内没有首次进入的企业",
    }),
    note: "「首次进入」受数据覆盖起点限制：更早的历史记录可能不在语料窗口内。",
  }));

  /* -------------------------------------------------------- recent events */
  const events = data.events || [];
  wrapper.append(panel({
    title: "最近事件",
    sub: `窗口内最近 ${events.length} 条该赛道记录，点击行打开事件详情`,
    dense: true,
    right: linkButton(buildHash("/evidence", { track: trackId, metric: "approvals" }), "全部记录"),
    body: dataTable({
      columns: [
        { key: "event_date", label: "日期", format: (row) => fmtDate(row.event_date) },
        { key: "kind", label: "类型", format: (row) => badge(kindLabelLocal(row.kind), "muted") },
        { key: "company_name_zh", label: "企业", format: (row) => row.company_name_zh || el("span", { class: "muted", text: "未映射" }) },
        { key: "title", label: "标题", format: (row) => el("div", { class: "cell-title", text: row.title || "—", title: row.title || "" }) },
      ],
      rows: events,
      rowClick: (row) => openEvent(row.event_id),
      rowAttrs: (row) => eventRowAttrs(row),
      empty: "该赛道没有最近事件",
    }),
  }));

  /* --------------------------------------------------------- coverage note */
  wrapper.append(panel({
    title: "覆盖与口径",
    sub: "该视图的窗口、序列与映射边界",
    body: [
      notice({
        tone: "muted",
        title: "窗口与序列",
        body: `${windowInfo.start || "—"} → ${windowInfo.end || "—"}（对照 ${windowInfo.prior_start || "—"} → ${windowInfo.prior_end || "—"}）。序列为季度粒度，共 ${categories.length} 个季度；序列合计 ${fmtInt(totals.series_total_complete)} 与窗口合计 ${fmtInt(totals.recent)} 可能因窗口边界存在差异，两者都按 API 实际返回展示。`,
      }),
      data.method?.signal ? notice({ tone: "blue", title: "信号方法", body: data.method.signal }) : null,
      notice({
        tone: "amber",
        title: "映射边界",
        body: "赛道由 FDA 产品代码映射得到。未映射记录既不计入该赛道，也不表示该赛道没有活动；企业归属存在错配风险，补充映射企业标注为待复核。",
      }),
    ].filter(Boolean),
  }));

  return { title: `${track.name_zh || trackId} · 技术赛道` };
}

function windowSeg(windows, years, onChange) {
  const node = el("div", { class: "seg" });
  for (const value of windows) {
    node.append(el("button", {
      type: "button",
      class: `seg-btn${value === years ? " active" : ""}`,
      text: `${value} 年`,
      onclick: () => onChange(value),
    }));
  }
  return node;
}

function kindLabelLocal(kind) {
  const labels = { "510k": "510(k)", pma: "PMA", device_recall: "器械召回", trial: "临床试验", "8k_catalyst": "8-K" };
  return labels[kind] || kind || "—";
}

function quarterForDate(value) {
  const match = /^(\d{4})-(\d{2})/.exec(String(value || ""));
  if (!match) return null;
  return `${match[1]}-Q${Math.floor((Number(match[2]) - 1) / 3) + 1}`;
}

function lineChartFallback(host, categories, points) {
  // defensive fallback if the API ever omits by_kind
  const byPeriod = new Map(points.map((point) => [point.period, point.count]));
  const values = categories.map((period) => byPeriod.get(period) || 0);
  const max = Math.max(1, ...values);
  const bars = el("div", { class: "row wrap", style: "align-items:flex-end;gap:2px;height:200px" });
  categories.forEach((period, index) => {
    bars.append(el("div", {
      title: `${period}: ${values[index]}`,
      style: `flex:1;min-width:2px;height:${Math.max(1, (values[index] / max) * 100)}%;background:#2f81f7`,
    }));
  });
  host.append(bars);
}
