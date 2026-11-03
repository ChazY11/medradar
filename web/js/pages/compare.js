/* #/compare — 2-5 company comparison: grouped chart, totals, track matrix,
   pathway structure and every comparability warning returned by the API. */
import { api } from "../api.js";
import {
  el, fmtInt, fmtPct, fmtPctSigned, fmtSigned, fmtNum, toneForDelta,
  buildHash, periodRange, normalizeCompanyList, SERIES_COLORS,
} from "../util.js";
import {
  pageHead, panel, badge, dataTable, notice, list, segmented, linkButton,
  errorState, skeletonBlock, emptyState, textButton, disclosure,
} from "../components.js";
import { lineChart } from "../charts.js";

const SEVERITY_TONE = { high: "red", medium: "amber", low: "muted" };
const SEVERITY_LABEL = { high: "高", medium: "中", low: "低" };

export async function mount(root, ctx) {
  const featured = (ctx.companies.featured || []).map((company) => company.key);
  const roster = ctx.companies.companies || [];
  const rosterByKey = new Map(roster.map((company) => [company.key, company]));
  const metricMeta = ctx.meta.metrics || {};
  const windowChoices = (ctx.meta.window_choices || []).filter((value) => [3, 5, 10].includes(Number(value)));
  const windows = windowChoices.length ? windowChoices.map(Number) : [3, 5, 10];

  let selected = normalizeCompanyList(ctx.query.get("companies"));
  if (!selected.length) selected = featured.slice(0, 2);
  selected = selected.filter((key) => rosterByKey.has(key)).slice(0, 5);
  if (!selected.length) selected = featured.slice(0, 2);
  let metric = ctx.query.get("metric") || "approvals";
  if (!metricMeta[metric]) metric = "approvals";
  let years = Number(ctx.query.get("years") || 5);
  if (!windows.includes(years)) years = 5;
  let granularity = ctx.query.get("granularity") || "quarter";
  if (!["quarter", "year"].includes(granularity)) granularity = "quarter";

  root.append(pageHead({
    title: "企业对比",
    subtitle: "同一指标、同一时间窗的横向比较。绝对记录数受监管路径与产品组合影响，因此同时给出企业内赛道占比与相对全行业的专业化指数。",
    captions: [
      { label: "指标", value: metricMeta[metric]?.label_zh || metric },
      { label: "窗口", value: `近 ${years} 年` },
      { label: "粒度", value: granularity === "quarter" ? "季度" : "年度" },
    ],
    actions: [linkButton("#/companies", "企业情报"), linkButton("#/radar", "技术雷达")],
  }));

  /* ------------------------------------------------------------ selector */
  const chipRow = el("div", { class: "chip-row" });
  const selectedRow = el("div", { class: "chip-row mt-8" });
  const validation = el("div", { class: "mt-8" });

  const metricSelect = el("select", { "aria-label": "指标", value: metric });
  for (const [key, value] of Object.entries(metricMeta)) {
    metricSelect.append(el("option", { value: key, text: `${value.label_zh}（${value.unit || ""}）`, selected: key === metric }));
  }
  metricSelect.addEventListener("change", () => { metric = metricSelect.value; });

  const granularitySeg = el("div", { class: "seg" });
  for (const option of [{ value: "quarter", label: "季度" }, { value: "year", label: "年度" }]) {
    granularitySeg.append(el("button", {
      type: "button",
      class: `seg-btn${granularity === option.value ? " active" : ""}`,
      text: option.label,
      onclick: () => {
        granularity = option.value;
        for (const button of granularitySeg.children) button.classList.toggle("active", button.textContent === option.label);
      },
    }));
  }

  const windowSeg = el("div", { class: "seg" });
  for (const value of windows) {
    windowSeg.append(el("button", {
      type: "button",
      class: `seg-btn${value === years ? " active" : ""}`,
      text: `${value} 年`,
      dataset: { testid: `window-${value}` },
      onclick: () => {
        years = Number(value);
        for (const button of windowSeg.children) button.classList.toggle("active", Number(button.textContent.replace(" 年", "")) === years);
      },
    }));
  }

  const extraSelect = el("select", { "aria-label": "添加其他企业" });
  extraSelect.append(el("option", { value: "", text: "添加其他名册企业…" }));
  for (const company of roster) {
    if (!selected.includes(company.key)) {
      extraSelect.append(el("option", { value: company.key, text: `${company.name_zh}（${company.name_en || company.key}）` }));
    }
  }
  extraSelect.addEventListener("change", () => {
    const key = extraSelect.value;
    if (!key) return;
    if (selected.length >= 5) {
      renderValidation("最多选择 5 家企业");
      extraSelect.value = "";
      return;
    }
    selected.push(key);
    renderSelection();
  });

  const runButton = textButton("应用对比", () => apply(), { primary: true, small: false, testid: "compare-run" });

  function renderValidation(message) {
    validation.replaceChildren();
    if (message) validation.append(notice({ tone: "amber", title: "选择无效", body: message }));
    const valid = selected.length >= 2 && selected.length <= 5;
    // never show stale chart/warnings next to a "selection invalid" message
    results.hidden = !valid;
    invalidPanel.hidden = valid;
    if (!valid) {
      invalidPanel.replaceChildren(panel({
        title: "选择无效",
        sub: "需要 2–5 家企业才能计算对比",
        body: [
          notice({
            tone: "amber",
            title: `当前已选 ${selected.length} 家企业`,
            body: "请重新选择至少 2 家、最多 5 家企业，然后点击「应用对比」。下方的旧图表与警告已被清除，避免与当前选择冲突。",
          }),
          el("div", { class: "mt-8" }, textButton("恢复默认（美敦力 + 飞利浦）", () => {
            selected = featured.slice(0, 2);
            rebuildExtraSelect();
            renderSelection();
            renderValidation("");
          }, { testid: "compare-reset-selection" })),
        ],
      }));
    } else {
      invalidPanel.replaceChildren();
    }
  }

  function renderSelection() {
    chipRow.replaceChildren();
    for (const key of featured) {
      const company = rosterByKey.get(key);
      const active = selected.includes(key);
      const chipButton = el("button", {
        type: "button",
        class: `chip${active ? " active" : ""}`,
        "aria-pressed": active ? "true" : "false",
        title: company ? `${company.name_zh} · 事件 ${fmtInt(company.events)}` : key,
        onclick: () => {
          const index = selected.indexOf(key);
          if (index >= 0) selected.splice(index, 1);
          else if (selected.length >= 5) {
            renderValidation("最多选择 5 家企业");
            return;
          } else selected.push(key);
          rebuildExtraSelect();
          renderSelection();
          renderValidation(selected.length >= 2 && selected.length <= 5 ? "" : "请选择 2–5 家企业");
        },
      }, el("span", { text: company ? company.name_zh : key }));
      chipButton.dataset.testid = "compare-toggle";
      chipButton.dataset.companyKey = key;
      chipButton.dataset.selected = active ? "true" : "false";
      chipRow.append(chipButton);
    }

    selectedRow.replaceChildren();
    for (const key of selected) {
      const company = rosterByKey.get(key);
      selectedRow.append(el("span", { class: "chip active" },
        el("span", { text: `${company ? company.name_zh : key} · ${company ? company.name_en || key : key}` }),
        el("span", {
          class: "x", title: "移除",
          text: "✕",
          onclick: (event) => {
            event.stopPropagation();
            selected = selected.filter((item) => item !== key);
            renderValidation(selected.length >= 2 ? "" : "请选择 2–5 家企业");
            rebuildExtraSelect();
            renderSelection();
          },
        }),
      ));
    }
    if (!selected.length) selectedRow.append(el("span", { class: "muted small", text: "尚未选择企业" }));
  }

  function rebuildExtraSelect() {
    extraSelect.replaceChildren(el("option", { value: "", text: "添加其他名册企业…" }));
    for (const company of roster) {
      if (!selected.includes(company.key)) {
        extraSelect.append(el("option", { value: company.key, text: `${company.name_zh}（${company.name_en || company.key}）` }));
      }
    }
  }

  function apply() {
    if (selected.length < 2 || selected.length > 5) {
      renderValidation("请选择 2–5 家企业后再应用。");
      return;
    }
    ctx.go("/compare", {
      companies: selected.join(","),
      metric,
      years,
      granularity,
    });
  }

  const results = el("div");
  const invalidPanel = el("div");
  invalidPanel.hidden = true;

  renderSelection();
  renderValidation(selected.length >= 2 && selected.length <= 5 ? "" : "请选择 2–5 家企业");

  const filterBody = el("div", { class: "filter-bar" },
    el("div", { class: "filter-field" }, el("span", { class: "filter-label", text: "重点企业（点击切换）" }), chipRow),
    el("div", { class: "filter-field" }, el("span", { class: "filter-label", text: "指标" }), metricSelect),
    el("div", { class: "filter-field" }, el("span", { class: "filter-label", text: "窗口" }), windowSeg),
    el("div", { class: "filter-field" }, el("span", { class: "filter-label", text: "粒度" }), granularitySeg),
    el("div", { class: "filter-field" }, el("span", { class: "filter-label", text: "更多企业" }), extraSelect),
    el("div", { class: "filter-field" }, el("span", { class: "filter-label", text: " " }), runButton),
  );
  root.append(panel({
    title: "选择对比组合",
    sub: "2–5 家企业 · 指标 · 窗口 · 粒度；应用后刷新全部结果",
    body: [filterBody, el("div", { class: "small mt-8" }, el("span", { class: "muted", text: "已选：" }), selectedRow), validation],
  }));
  root.append(invalidPanel, results);

  /* --------------------------------------------------------------- fetch */
  results.append(panel({ title: "对比结果", body: skeletonBlock(6) }));

  let data;
  try {
    data = await api.compare({ companies: selected, metric, years, granularity });
  } catch (error) {
    results.replaceChildren(errorState(error, () => ctx.refresh(), { title: "对比数据加载失败" }));
    return { title: "企业对比" };
  }

  results.replaceChildren();
  const responseMetric = data.metric && typeof data.metric === "object" ? data.metric : metricMeta[metric] || {};

  /* ------------------------------------------------------------ warnings */
  const warningNodes = (data.warnings || []).map((warning) => notice({
    tone: SEVERITY_TONE[warning.severity] || "amber",
    title: warning.text_zh,
    label: `${warning.code} · ${SEVERITY_LABEL[warning.severity] || warning.severity}`,
    testid: "compare-warning",
  }));
  if (warningNodes.length) {
    const warningPanel = panel({
      title: "可比性警告（必须与结果一起阅读）",
      sub: "API 在该筛选下返回的警告；不可比之处优先于数字本身",
      body: warningNodes,
    });
    results.append(warningPanel);
  }

  /* --------------------------------------------------------------- chart */
  const companySeries = data.companies || [];
  const periodSet = [];
  for (const company of companySeries) {
    for (const point of company.series || []) {
      if (!periodSet.includes(point.period)) periodSet.push(point.period);
    }
  }
  periodSet.sort();
  const chartHost = el("div");
  const partialFlags = periodSet.map(() => false);
  companySeries.forEach((company) => {
    for (const point of company.series || []) {
      if (point.partial) partialFlags[periodSet.indexOf(point.period)] = true;
    }
  });
  if (periodSet.length) {
    lineChart(chartHost, {
      categories: periodSet,
      series: companySeries.map((company, index) => {
        const values = new Map((company.series || []).map((point) => [point.period, point.count]));
        return {
          key: company.key,
          label: company.name_zh,
          color: SERIES_COLORS[index % SERIES_COLORS.length],
          values: periodSet.map((period) => (values.has(period) ? values.get(period) : null)),
        };
      }),
      height: 250,
      partialFlags,
      svgTestid: "compare-chart",
      ariaLabel: "企业指标对比图",
      onSelect: (period) => {
        const range = periodRange(period);
        ctx.go("/evidence", {
          companies: selected.join(","),
          metric,
          start: range?.start,
          end: range?.end,
        });
      },
      legendNote: `指标：${responseMetric.label_zh || metric}（${responseMetric.unit || "记录"}） · 点击任意周期 → 打开该窗口的原始记录 · 虚线/空心点为不完整周期`,
    });
  } else {
    chartHost.append(emptyState("该窗口内没有可绘制的记录。", { title: "无对比数据" }));
  }
  results.append(panel({
    title: `对比趋势：${responseMetric.label_zh || metric}`,
    sub: `${data.window?.start || "—"} → ${data.window?.end || "—"} · 粒度 ${data.granularity === "year" ? "年度" : "季度"}`,
    body: chartHost,
    note: responseMetric.definition_zh || null,
  }));

  /* --------------------------------------------------------------- totals */
  results.append(panel({
    title: "总量与路径结构",
    sub: "绝对记录数 + 监管路径结构 + 未映射记录",
    dense: true,
    body: dataTable({
      columns: [
        { key: "name_zh", label: "企业", format: (row) => el("span", null, el("b", { text: row.name_zh }), el("span", { class: "muted", text: `  ${row.name_en || ""}` })) },
        { key: "total", label: "窗口内合计", num: true, format: (row) => fmtInt(row.total) },
        { key: "total_complete", label: "仅完整周期", num: true, format: (row) => fmtInt(row.total_complete) },
        { key: "prior_total", label: "前窗", num: true, format: (row) => fmtInt(row.prior_total) },
        { key: "delta", label: "Δ", num: true, format: (row) => el("span", { class: toneForDelta(row.total - row.prior_total), text: fmtSigned(row.total - row.prior_total) }) },
        { key: "pct", label: "变化", num: true, format: (row) => el("span", { class: toneForDelta(row.total - row.prior_total), text: fmtPctSigned(row.prior_total ? (row.total - row.prior_total) / row.prior_total : null) }) },
        { key: "pathway", label: "PMA / 510(k) 结构", format: (row) => (row.pathway ? el("span", { class: "mono small", text: `${fmtPct(row.pathway.pma_share, 0)} / ${fmtPct(row.pathway["510k_share"], 0)}` }) : "—") },
        { key: "unmapped", label: "未映射", num: true, format: (row) => fmtInt(row.unmapped) },
        { key: "coverage", label: "覆盖来源", num: true, format: (row) => `${(row.coverage || []).length} 个` },
      ],
      rows: companySeries,
    }),
    note: "「窗口内合计」包含数据截止所在的不完整周期（partial_total）；「仅完整周期」用于趋势比较。未映射记录不进入赛道统计，但也不代表零活动。PMA 与 510(k) 是不同监管路径。",
  }));

  /* ---------------------------------------------------------- track matrix */
  const companyKeys = companySeries.map((company) => company.key);
  const companyLabels = new Map(companySeries.map((company) => [company.key, company.name_zh]));
  const trackRows = (data.track_table || []).slice().sort((a, b) => (b.industry_total || 0) - (a.industry_total || 0));
  const matrixColumns = [
    { key: "name_zh", label: "技术赛道", format: (row) => el("span", null, el("span", { text: row.name_zh }), el("span", { class: "muted tiny", text: `  ${row.domain || ""}` })) },
    { key: "industry_total", label: "全行业", num: true, format: (row) => fmtInt(row.industry_total) },
    { key: "industry_share", label: "行业占比", num: true, format: (row) => fmtPct(row.industry_share, 1) },
    ...companyKeys.map((key) => ({
      key,
      label: companyLabels.get(key) || key,
      num: true,
      format: (row) => {
        const cell = (row.companies || []).find((item) => item.key === key);
        if (!cell) return el("span", { class: "muted", text: "—" });
        return el("span", { class: "nowrap" },
          el("span", { text: fmtInt(cell.n) }),
          el("span", { class: "muted tiny", text: ` ${fmtPct(cell.share, 0)} · LQ ` }),
          el("span", {
            class: cell.location_quotient != null && cell.location_quotient >= 1 ? "tone-up" : "tone-down",
            text: cell.location_quotient == null ? "—" : fmtNum(cell.location_quotient, 2),
          }),
        );
      },
    })),
  ];
  results.append(panel({
    title: "技术赛道矩阵",
    sub: "单元格：记录数 · 企业内赛道占比 · 专业化指数 LQ（= 企业占比 / 全行业占比）",
    dense: true,
    right: el("span", { class: "muted tiny", text: "LQ > 1 表示高于全行业结构" }),
    body: dataTable({
      columns: matrixColumns,
      rows: trackRows,
      rowClick: (row) => ctx.go("/evidence", { companies: selected.join(","), track: row.track, metric }),
      empty: "该窗口内没有赛道映射记录",
    }),
    note: "LQ 不是创新能力或市场地位；它只描述该企业在这条赛道上相对全行业的记录结构差异。",
  }));

  /* --------------------------------------------------------------- notes */
  const noteItems = [...(data.notes || []), ...(ctx.meta.comparability_notes || [])];
  if (noteItems.length) {
    results.append(panel({
      title: "可比性说明",
      sub: "指标口径与跨企业比较的限制",
      body: [
        list(noteItems),
        responseMetric.caveats && responseMetric.caveats.length
          ? disclosure(`指标口径限制（${responseMetric.caveats.length} 条）`, list(responseMetric.caveats))
          : null,
      ].filter(Boolean),
    }));
  }

  return { title: "企业对比" };
}
