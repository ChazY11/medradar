/* #/radar/{track} — track detail: quarterly composition chart, company mix,
   first-time entrants, detected signals, recent events, coverage captions. */
import { api } from "../api.js";
import {
  el, fmtInt, fmtPct, fmtPctSigned, fmtSigned, fmtDate, buildHash, periodRange, toneForDelta,
  analysisWindow, analysisRange, priorAnalysisRange, periodFlags,
} from "../util.js";
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
  const analysis = analysisWindow(windowInfo);

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
      badge("完整周期口径", "teal", "recent/prior 使用完整自然季度；窗口起止不完整季度只展示"),
      totals.partial_total > 0 ? badge(`序列含 ${fmtInt(totals.partial_total)} 条不完整周期记录`, "amber") : null,
    ].filter(Boolean),
    subtitle: domain.blurb_zh || `该赛道的公开审批记录（510(k) + PMA）与统计探测信号。`,
    captions: [
      { label: "请求窗口", value: `${windowInfo.start || "—"} → ${windowInfo.end || "—"}` },
      { label: "完整季度分析窗口", value: `${analysisRange(analysis)} · 对照 ${priorAnalysisRange(analysis)}` },
      { label: "完整周期", value: analysis.periods != null ? `${analysis.periods} 个季度` : "—" },
      { label: "全时记录", value: fmtInt(totals.all_time) },
      { label: "粒度", value: "季度" },
    ],
    actions: [
      windowSeg(windows, years, (value) => ctx.go(`/radar/${trackId}`, { years: value })),
      linkButton(buildHash("/evidence", { track: trackId, metric: "approvals" }), "该赛道证据"),
    ],
  }));

  /* ----------------------------------------------------------------- KPIs */
  const kpiGrid = el("div", { class: "kpi-grid" });
  const kpiCards = [
    kpi({
      label: `完整周期合计（近 ${years} 年）`,
      value: fmtInt(totals.recent),
      sub: `完整自然季度 · 窗口全部 ${fmtInt(totals.recent_all)} 条（含起止不完整季度）`,
      hint: "totals.recent：完整自然季度内的 510(k)+PMA 记录；totals.recent_all：请求窗口全部记录（含起止不完整季度）。",
      testid: "track-kpi-recent-complete",
    }),
    kpi({
      label: "前窗（完整周期）",
      value: fmtInt(totals.prior),
      sub: `窗口全部 ${fmtInt(totals.prior_all)} 条 · ${windowInfo.prior_start || "—"} 起`,
      hint: "totals.prior / totals.prior_all",
      testid: "track-kpi-prior-complete",
    }),
    kpi({
      label: "变化（完整周期）",
      value: fmtPctSigned(totals.pct_change),
      tone: toneForDelta(totals.delta),
      sub: `Δ ${fmtSigned(totals.delta)}`,
    }),
    kpi({
      label: "序列部分周期合计",
      value: fmtInt(totals.partial_total),
      sub: `序列合计 ${fmtInt(totals.series_total)} · 完整周期序列合计 ${fmtInt(totals.series_total_complete)}`,
      hint: "partial_total：季度序列中起止不完整周期的记录数，只展示、不参与同比与信号基线。",
      testid: "track-kpi-partial",
    }),
    kpi({ label: "全时记录", value: fmtInt(totals.all_time), sub: "数据覆盖期内该赛道已映射记录" }),
    kpi({ label: "活跃企业", value: fmtInt((data.companies || []).length), sub: "完整周期内有记录的企业" }),
    kpi({
      label: "新进入企业",
      value: fmtInt((data.entrants || []).length),
      sub: "数据覆盖期内首次观察到原始批准",
      hint: "只统计原始 PMA 与 Traditional 510(k)；PMA 补充申请与 Special/Abbreviated 510(k) 不计入。",
    }),
    totals.pma_unknown > 0
      ? kpi({
        label: "PMA 类型不可判定",
        value: fmtInt(totals.pma_unknown),
        sub: "原始 payload 无法解析，不猜测类型",
        tone: "tone-down",
      })
      : null,
  ].filter(Boolean);
  kpiGrid.append(...kpiCards);
  wrapper.append(kpiGrid);

  /* ---------------------------------------------------------------- chart */
  const chartBody = el("div");
  const categories = series.periods || [];
  const approvalByPeriod = new Map(((series.approvals || [])).map((point) => [point.period, point]));
  const kindSeries = series.by_kind || {};
  const kindKeys = Object.keys(kindSeries);
  const flowFlags = periodFlags(series.approvals || [], categories);
  const partialFlags = flowFlags.partialFlags;
  const lagFlags = flowFlags.lagFlags;

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
      partialFlags,
      lagFlags,
      svgTestid: "track-chart",
      ariaLabel: "赛道季度记录构成",
      onSelect: (period) => {
        const range = periodRange(period);
        ctx.go("/evidence", { track: trackId, metric: "approvals", start: range?.start, end: range?.end });
      },
    });
    const partialPeriods = categories.filter((period, index) => partialFlags[index]);
    const lagPeriods = categories.filter((period, index) => lagFlags[index]);
    const edgePeriod = quarterForDate(windowInfo.end);
    const partialText = partialPeriods.length
      ? `不完整周期（*）：${partialPeriods.join("、")}（API partial 标记；计数仍显示，不参与同比与信号基线）`
      : (edgePeriod && categories.includes(edgePeriod)
        ? `数据截止所在季度 ${edgePeriod} 未标记为完整（API 未返回 partial，比较时请谨慎）`
        : "所有周期均为完整季度");
    const lagText = lagPeriods.length
      ? `日历完整但临近数据截止（†，source_lag_risk）：${lagPeriods.join("、")}；源数据可能仍会修订/补录`
      : "没有临近数据截止的周期";
    chartBody.append(el("div", { class: "chart-note" },
      el("span", { text: "堆叠：510(k) + PMA；点击季度 → 打开该季度的原始记录" }),
      el("span", { text: partialText }),
      el("span", { text: lagText }),
      el("span", { text: `${categories.length} 个季度（完整 ${categories.length - partialPeriods.length} 个，其中 ${lagPeriods.length} 个临近数据截止）` }),
    ));
  } else {
    const approvals = series.approvals || [];
    lineChartFallback(chartBody, categories, approvals);
  }
  wrapper.append(panel({
    title: "季度审批记录构成",
    sub: `请求窗口 ${windowInfo.start || "—"} → ${windowInfo.end || "—"} · 完整季度分析 ${analysisRange(analysis)} · 悬停查看精确值与周期状态，点击打开证据`,
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
    sub: `点击行 → 该企业在该赛道的原始记录 · 已归属 ${fmtInt(attributed)} / 赛道合计 ${fmtInt(totalRecent)} 条 · 未归属 ${fmtInt(unattributed)} 条（attributed_share ${fmtPct(data.attribution?.attributed_share, 1)}）`,
    dense: true,
    body: composition,
    note: `${data.attribution?.note_zh || "企业构成只统计能归到具体企业的记录；未归属记录仍计入赛道总量与份额分母。"} attribution.track_total_records_recent = ${fmtInt(data.attribution?.track_total_records_recent ?? totalRecent)}。`,
  }));

  /* ------------------------------------------------------------- entrants */
  const entrants = data.entrants || [];
  wrapper.append(panel({
    title: "首次进入企业（原始批准）",
    sub: "数据覆盖期内首次观察到原始批准（Traditional 510(k) 或原始 PMA）",
    dense: true,
    body: dataTable({
      columns: [
        { key: "name_zh", label: "企业", format: (row) => row.name_zh || row.company },
        { key: "first_date", label: "首次原始批准日", format: (row) => fmtDate(row.first_date) },
        { key: "n", label: "完整周期内记录", num: true, format: (row) => fmtInt(row.n) },
      ],
      rows: entrants,
      rowClick: (row) => ctx.go("/evidence", { companies: row.company, track: trackId, metric: "approvals" }),
      empty: "该窗口内没有首次进入的企业",
    }),
    note: `${data.method?.entrant || "企业在本窗口内出现该赛道数据覆盖期内的首条原始批准（Traditional 510(k) 或原始 PMA）"} PMA 补充申请与 Special/Abbreviated 510(k) 不计入首次进入；「首次进入」受数据覆盖起点限制，更早的历史记录可能不在语料窗口内。`,
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
        title: "窗口与序列（完整季度 vs 窗口全部）",
        body: `请求窗口 ${windowInfo.start || "—"} → ${windowInfo.end || "—"}（对照 ${windowInfo.prior_start || "—"} → ${windowInfo.prior_end || "—"}）。完整季度分析窗口 ${analysisRange(analysis)}，对照 ${priorAnalysisRange(analysis)}，共 ${analysis.periods ?? categories.length} 个季度。完整周期合计 ${fmtInt(totals.recent)} / 前窗 ${fmtInt(totals.prior)}；窗口全部记录 ${fmtInt(totals.recent_all)} / 前窗 ${fmtInt(totals.prior_all)}；序列部分周期合计 ${fmtInt(totals.partial_total)} 条（序列合计 ${fmtInt(totals.series_total)}，完整周期序列合计 ${fmtInt(totals.series_total_complete)}）。${data.method?.comparison || "recent/prior 使用完整自然季度口径；窗口起止不完整季度仅展示，不参与同比。"}`,
      }),
      data.method?.signal ? notice({ tone: "blue", title: "信号方法", body: data.method.signal }) : null,
      notice({
        tone: "amber",
        title: "映射边界",
        body: "赛道由 FDA 产品代码映射得到。未映射记录既不计入该赛道，也不表示该赛道没有活动；企业归属存在错配风险，补充映射企业标注为待复核。首次进入只统计原始批准（原始 PMA / Traditional 510(k)）；PMA 补充申请是已批准器械的变更，不代表新器械或技术首次进入。",
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
