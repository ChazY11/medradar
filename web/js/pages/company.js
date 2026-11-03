/* #/companies/{key} — company profile: KPIs, evidence-linked claims,
   technology mix, trend windows, source coverage, milestones, limits. */
import { api } from "../api.js";
import {
  el, fmtInt, fmtPct, fmtPctSigned, fmtSigned, fmtRange, fmtDate, fmtNum,
  toneForDelta, kindLabel, buildHash, periodRange, analysisWindow, analysisRange,
  priorAnalysisRange, periodFlags, approvalTypeTone,
} from "../util.js";
import {
  pageHead, panel, kpi, badge, tierBadge, dataTable, notice, list,
  disclosure, segmented, linkButton, errorState, skeletonBlock, emptyState, textButton,
  approvalBadges, shareBar, kvList,
} from "../components.js";
import { lineChart, barChart } from "../charts.js";
import { openEvent, eventRowAttrs, eventRowButton, matchBadge } from "../event.js";

const KIND_METRIC = {
  "510k": "510k",
  pma: "pma",
  device_recall: "recalls",
  trial: "trials",
  "8k_catalyst": "corporate",
};

const DIRECTION_LABEL = { up: "上升", down: "下降", flat: "基本持平" };
const DIRECTION_TONE = { up: "badge-green", down: "badge-amber", flat: "badge-muted" };
const CONFIDENCE_LABEL = { high: "高", medium: "中", low: "低" };

export async function mount(root, ctx) {
  const key = ctx.params.key;
  const yearsParam = Number(ctx.query.get("years") || 5);
  const windowChoices = (ctx.meta.window_choices || []).filter((value) => [3, 5, 10].includes(Number(value)));
  const windows = windowChoices.length ? windowChoices.map(Number) : [3, 5, 10];
  const years = windows.includes(yearsParam) ? yearsParam : 5;

  root.replaceChildren(skeletonBlock(8));
  let data;
  try {
    data = await api.company(key, years);
  } catch (error) {
    root.replaceChildren(errorState(error, () => ctx.refresh(), { title: "企业画像加载失败" }));
    return { title: "企业画像" };
  }

  const wrapper = el("div");
  wrapper.dataset.testid = "company-profile";
  root.replaceChildren(wrapper);

  const info = data.info || {};
  const headline = data.headline || {};
  const windowInfo = data.window || {};
  const tracks = data.tracks || { rows: [] };
  const completeness = windowInfo.completeness || {};
  const analysis = analysisWindow({ ...windowInfo, ...(tracks.analysis_window || {}) });
  const pmaBreakdown = headline.pma_breakdown || {};
  const windowBreakdown = pmaBreakdown.window || headline.pathway_mix_counts || {};
  const allTimeBreakdown = pmaBreakdown.all_time || {};
  const pathwayAllTime = headline.pathway_mix_all_time || {};
  const industry = headline.industry_coverage || {};
  const pmaWindowTotal = Number(windowBreakdown.pma_total ?? windowBreakdown.pma) || 0;
  const k510WindowTotal = Number(windowBreakdown.k510_total ?? windowBreakdown["510k"]) || 0;
  const approvalsWindowTotal = Number(windowBreakdown.approvals_total) || pmaWindowTotal + k510WindowTotal;
  const windowShareOfApprovals = (value) => (approvalsWindowTotal ? fmtPct((Number(value) || 0) / approvalsWindowTotal, 1) : "—");
  const windowShareOfPma = (value) => (pmaWindowTotal ? fmtPct((Number(value) || 0) / pmaWindowTotal, 1) : "—");
  const approvalsWindowAll = headline.approvals_window_all ?? headline.approvals_window_complete;
  const unmappedWindowComplete = headline.unmapped_window_complete ?? tracks.unmapped_recent;
  const unmappedWindowAll = headline.unmapped_window ?? tracks.unmapped_recent_all;

  /* ------------------------------------------------------------- header */
  wrapper.append(pageHead({
    kicker: el("span", null,
      el("a", { href: "#/companies", text: "企业情报" }),
      el("span", { class: "sep", text: "/" }),
      el("span", { text: info.name_zh || key }),
    ),
    title: info.name_zh || key,
    badges: [
      info.name_en ? badge(info.name_en, "muted") : null,
      info.ticker ? badge(info.ticker, "blue") : null,
      info.featured ? badge("重点企业", "blue") : null,
      data.flags && data.flags.roster_absent ? badge("补充映射 · 待人工复核", "amber") : null,
      badge("完整季度口径", "teal", "近窗/前窗比较、份额与 PMA 拆分均使用完整自然季度"),
    ].filter(Boolean),
    subtitle: `${info.profile_zh ? `${info.profile_zh}${info.curated_note ? `（${info.curated_note}）` : ""} ` : ""}同比、份额与监管路径结构按完整自然季度计算；请求窗口起止的不完整季度只展示、不参与比较。`,
    captions: [
      { label: "交易所", value: info.exchange || "—" },
      { label: "总部", value: info.hq_zh || "—" },
      { label: "请求窗口", value: `${windowInfo.start || "—"} → ${windowInfo.end || "—"}` },
      { label: "完整季度分析窗口", value: `${analysisRange(analysis)} · 对照 ${priorAnalysisRange(analysis)}` },
      { label: "完整周期", value: analysis.periods != null ? `${analysis.periods} 个季度` : "—" },
      { label: "覆盖期", value: fmtRange(data.coverage_span?.first, data.coverage_span?.last) },
      { label: "归属方法", value: (data.entity_review && data.entity_review[0] && data.entity_review[0].method_zh) || "仓库名册" },
    ],
    actions: [
      segmented(windows.map((value) => ({ label: `${value} 年`, value, testid: `window-${value}` })), years, (nextYears) => {
        ctx.go(`/companies/${key}`, { years: nextYears });
      }),
      linkButton(buildHash("/compare", { companies: key }), "加入对比"),
      linkButton(buildHash("/evidence", { companies: key }), "该企业证据"),
    ],
  }));

  /* --------------------------------------------- entity review warnings */
  for (const review of data.entity_review || []) {
    if (!review || !review.note_zh) continue;
    // roster mappings are the warehouse baseline (high confidence) — only flag
    // mappings that are explicitly pending human review (e.g. Dräger / Mindray).
    if (review.status !== "PENDING_HUMAN_REVIEW") continue;
    const body = el("div");
    body.append(el("div", { text: review.note_zh }));
    body.append(el("div", { class: "muted tiny mt-4", text: `方法：${review.method_zh || review.method || "—"} · 置信度：${review.confidence || "—"} · 状态：${review.status || "—"}` }));
    if (review.accept_exact && review.accept_exact.length) {
      body.append(disclosure(`接受匹配的申请人字符串（${review.accept_exact.length} 条）`, el("div", null,
        review.accept_exact.map((alias) => el("div", { class: "mono tiny", text: alias })),
      )));
    }
    if (review.reject_exact && review.reject_exact.length) {
      body.append(disclosure(`已排除的字符串（${review.reject_exact.length} 条）`, el("div", null,
        review.reject_exact.map((alias) => el("div", { class: "mono tiny", text: alias })),
      )));
    }
    wrapper.append(notice({
      tone: "amber",
      title: "实体归属待人工复核",
      label: review.status || "PENDING_HUMAN_REVIEW",
      body,
    }));
  }
  if (data.flags && data.flags.track_mapping_note) {
    wrapper.append(el("div", { class: "mt-8" }, notice({ tone: "muted", title: "赛道映射说明", body: data.flags.track_mapping_note })));
  }
  wrapper.append(el("div", { class: "mt-8" }, notice({
    tone: "blue",
    title: "完整季度口径（起止不完整季度只展示、不参与比较）",
    body: `${completeness.reason_zh || headline.window_basis_zh || ""} 请求窗口 ${windowInfo.start || "—"} → ${windowInfo.end || "—"}；窗口全部记录 ${fmtInt(approvalsWindowAll)} 条（含起止不完整季度），其中完整窗口全部记录 ${fmtInt(headline.approvals_window_complete)} 条（已映射 ${fmtInt(headline.approvals_window)} + 未映射 ${fmtInt(unmappedWindowComplete)}）；未映射（窗口全部口径）${fmtInt(unmappedWindowAll)} 条。未映射不等于零活动。`,
    testid: "company-window-basis",
  })));

  /* ---------------------------------------------------------------- KPIs */
  const kpiGrid = el("div", { class: "kpi-grid mt-12" });
  const approvalsDelta = headline.delta;
  kpiGrid.append(
    kpi({
      label: `已映射赛道审批（完整季度，近 ${years} 年）`,
      value: fmtInt(headline.approvals_window),
      sub: el("span", null,
        el("span", { class: toneForDelta(approvalsDelta), text: `${fmtSigned(approvalsDelta)} / ${fmtPctSigned(headline.pct_change)}` }),
        document.createTextNode(` vs 前窗 · 窗口全部 ${fmtInt(approvalsWindowAll)} 条（含起止不完整季度）`),
      ),
      hint: `完整自然季度 ${analysisRange(analysis)} 内，已映射到赛道的 510(k)+PMA 记录；窗口起止不完整季度不参与比较。`,
      testid: "kpi-approvals-window",
    }),
    kpi({
      label: `窗口全部记录（近 ${years} 年）`,
      value: fmtInt(approvalsWindowAll),
      sub: `含起止不完整季度 · 完整窗口全部 ${fmtInt(headline.approvals_window_complete)} 条（已映射+未映射）`,
      hint: "来自 headline.approvals_window_all；完整窗口全部记录 = headline.approvals_window_complete（已映射 + 未映射）。",
      testid: "kpi-approvals-window-all",
    }),
    kpi({
      label: `原始 PMA 批准（完整季度，近 ${years} 年）`,
      value: fmtInt(headline.pma_original_window),
      sub: `全时 ${fmtInt(headline.pma_original_all_time)} 条 · 新器械进入候选`,
      hint: "原始 PMA（supplement_number 为空）是新技术/新器械进入市场的候选事件。",
      testid: "kpi-pma-original-window",
    }),
    kpi({
      label: `PMA 补充申请（完整季度，近 ${years} 年）`,
      value: fmtInt(headline.pma_supplement_window),
      sub: `全时 ${fmtInt(headline.pma_supplement_all_time)} 条 · 补充申请 ≠ 新器械批准`,
      hint: "PMA 补充申请是已批准器械的变更（工艺/标签/适应证扩展），不是新器械进入。",
      testid: "kpi-pma-supplement-window",
    }),
    kpi({ label: "审批记录（全时）", value: fmtInt(headline.approvals_all_time), sub: "数据覆盖期内全部 510(k)+PMA 记录" }),
    kpi({ label: "活跃赛道", value: fmtInt(headline.tracks_active), sub: `完整季度内 ${fmtInt(tracks.total_recent)} 条已映射记录` }),
    kpi({ label: "召回记录（全时）", value: fmtInt(headline.recalls_all_time), sub: "安全性事件，不是技术活动" }),
    kpi({ label: "临床试验（全时）", value: fmtInt(headline.trials_all_time), sub: "ClinicalTrials.gov 注册" }),
  );
  wrapper.append(kpiGrid);

  wrapper.append(el("div", { class: "mt-8" }, notice({
    tone: "amber",
    title: `PMA 拆分：原始 PMA ${fmtInt(headline.pma_original_window)} 条 / PMA 补充申请 ${fmtInt(headline.pma_supplement_window)} 条（完整季度）`,
    body: `${pmaBreakdown.note_zh || ""} 全时口径：原始 PMA ${fmtInt(headline.pma_original_all_time)} 条、PMA 补充申请 ${fmtInt(headline.pma_supplement_all_time)} 条。PMA 补充申请 ≠ 新器械批准。`,
    testid: "company-pma-split",
  })));

  if (industry && industry.all_records != null) {
    wrapper.append(el("div", { class: "mt-8" }, notice({
      tone: "muted",
      title: "全行业口径：企业内占比与 LQ 的分母都是已映射赛道记录",
      body: `完整窗口全行业已映射 ${fmtInt(industry.mapped_records)} / ${fmtInt(industry.all_records)} 条（映射覆盖率 ${fmtPct(industry.mapping_coverage, 1)}），未映射 ${fmtInt(industry.unmapped_records)} 条（${industry.start || "—"} → ${industry.end || "—"}）。未映射记录不进入赛道统计，也不代表零活动。`,
      testid: "company-industry-coverage",
    })));
  }

  /* --------------------------------------------- pathway structure */
  const pmaOriginalWindow = Number(windowBreakdown.pma_original) || 0;
  const pmaSupplementWindow = Number(windowBreakdown.pma_supplement) || 0;
  const pmaUnknownWindow = Number(windowBreakdown.pma_unknown) || 0;
  const k510TraditionalWindow = Number(windowBreakdown.k510_traditional) || 0;
  const k510SpecialWindow = Number(windowBreakdown.k510_special) || 0;
  const k510AbbreviatedWindow = Number(windowBreakdown.k510_abbreviated) || 0;
  const k510OtherWindow = (Number(windowBreakdown.k510_other) || 0) + (Number(windowBreakdown.k510_unknown) || 0);
  const windowSegments = [
    { label: "PMA 补充申请", value: pmaSupplementWindow, color: "#d29922" },
    { label: "原始 PMA", value: pmaOriginalWindow, color: "#2dd4bf" },
    { label: "Traditional 510(k)", value: k510TraditionalWindow, color: "#2f81f7" },
    { label: "Special/Abbreviated 510(k)", value: k510SpecialWindow + k510AbbreviatedWindow, color: "#a371f7" },
    { label: "其他/不可判定 510(k)", value: k510OtherWindow, color: "#8296ab" },
  ];
  const pathwayWindowBody = el("div");
  pathwayWindowBody.append(
    el("div", { class: "pathway-label" },
      el("b", { text: "窗口结构（主口径）" }),
      el("span", { class: "muted tiny mono", text: `${analysisRange(analysis)} · basis=${headline.pathway_mix?.basis || "window_approvals_only"}` }),
    ),
    shareBar(windowSegments, { ariaLabel: "所选窗口的监管路径结构" }),
    el("div", { class: "mt-8" }, kvList([
      { key: "PMA 合计", value: `${fmtInt(pmaWindowTotal)} 条 · 占审批记录 ${windowShareOfApprovals(pmaWindowTotal)}` },
      { key: "· 原始 PMA", value: `${fmtInt(pmaOriginalWindow)} 条 · 占 PMA ${windowShareOfPma(pmaOriginalWindow)} · 新器械进入候选` },
      { key: "· PMA 补充申请", value: `${fmtInt(pmaSupplementWindow)} 条 · 占 PMA ${windowShareOfPma(pmaSupplementWindow)} · 补充申请 ≠ 新器械批准` },
      pmaUnknownWindow > 0 ? { key: "· PMA 类型不可判定", value: `${fmtInt(pmaUnknownWindow)} 条` } : null,
      { key: "510(k) 合计", value: `${fmtInt(k510WindowTotal)} 条 · 占审批记录 ${windowShareOfApprovals(k510WindowTotal)}` },
      { key: "· Traditional 510(k)", value: `${fmtInt(k510TraditionalWindow)} 条` },
      { key: "· Special 510(k)", value: `${fmtInt(k510SpecialWindow)} 条` },
      { key: "· Abbreviated 510(k)", value: `${fmtInt(k510AbbreviatedWindow)} 条` },
      { key: "· 其他/不可判定 510(k)", value: `${fmtInt(k510OtherWindow)} 条` },
      { key: "分母", value: `${fmtInt(approvalsWindowTotal)} 条（510(k)+PMA，召回/试验/8-K 不计入）` },
    ].filter(Boolean))),
  );

  const allTimePma = Number(allTimeBreakdown.pma_total ?? allTimeBreakdown.pma) || 0;
  const allTime510k = Number(allTimeBreakdown.k510_total ?? allTimeBreakdown["510k"]) || 0;
  const allTimeApprovals = Number(allTimeBreakdown.approvals_total) || allTimePma + allTime510k;
  const allTimeShare = (value) => (allTimeApprovals ? fmtPct((Number(value) || 0) / allTimeApprovals, 1) : "—");
  const allTimePmaOriginal = Number(allTimeBreakdown.pma_original) || 0;
  const allTimePmaSupplement = Number(allTimeBreakdown.pma_supplement) || 0;
  const pathwayAllTimeBody = el("div");
  pathwayAllTimeBody.append(
    el("div", { class: "pathway-label" },
      el("b", { text: "All-time Regulatory Pathway Mix" }),
      badge("全历史 · 仅背景", "muted", "basis=all_time_approvals_only；不能解释为当前窗口结构"),
    ),
    shareBar([
      { label: "PMA（含补充申请）", value: allTimePma, color: "#d29922" },
      { label: "510(k)", value: allTime510k, color: "#2f81f7" },
    ], { ariaLabel: "全历史监管路径结构" }),
    el("div", { class: "mt-8" }, kvList([
      { key: "PMA（含补充申请）", value: `${fmtInt(allTimePma)} 条 · 占全时审批记录 ${pathwayAllTime.pma != null ? fmtPct(pathwayAllTime.pma, 1) : allTimeShare(allTimePma)}` },
      { key: "510(k)", value: `${fmtInt(allTime510k)} 条 · 占全时审批记录 ${pathwayAllTime["510k"] != null ? fmtPct(pathwayAllTime["510k"], 1) : allTimeShare(allTime510k)}` },
      { key: "· 原始 PMA", value: `${fmtInt(allTimePmaOriginal)} 条 · 占 PMA ${fmtPct(headline.pma_original_share_of_pma_all_time, 2)}` },
      { key: "· PMA 补充申请", value: `${fmtInt(allTimePmaSupplement)} 条` },
      { key: "分母", value: `${fmtInt(allTimeApprovals)} 条（全历史 510(k)+PMA）` },
    ])),
  );

  const pathwayGrid = el("div", { class: "grid grid-2 mt-12" });
  pathwayGrid.append(
    panel({
      title: "监管路径结构 · 窗口（主口径）",
      sub: `完整季度 ${analysisRange(analysis)}；分母为 510(k)+PMA 记录，召回/试验/8-K 不计入`,
      testid: "company-pathway-window",
      body: pathwayWindowBody,
      note: "PMA 补充申请 ≠ 新器械批准：补充申请是已批准器械的变更（如工艺、标签、适应证扩展），两者都计入监管活动，但不能都当作“新器械”。",
    }),
    panel({
      title: "All-time Regulatory Pathway Mix",
      sub: "全历史监管路径结构，仅作背景参考；不能解释为所选窗口内的结构",
      testid: "company-pathway-alltime",
      body: pathwayAllTimeBody,
      note: pathwayAllTime.note_zh || "全历史结构不能解释为当前窗口结构。",
    }),
  );
  wrapper.append(pathwayGrid);

  /* -------------------------------------------------------------- claims */
  const claimsHost = el("div");
  claimsHost.dataset.testid = "company-claims";
  const claimsPanel = panel({
    title: "证据化结论",
    sub: "每条结论都由可复算的指标生成，并可展开到逐条事件；等级为「观察到的事实」时代表直接计数",
    right: linkButton(buildHash("/evidence", { companies: key }), "在证据浏览器中核查"),
    body: claimsHost,
  });
  if (!(data.claims || []).length) {
    claimsHost.append(emptyState("该企业当前窗口内没有可生成的证据化结论。", { title: "暂无可核查结论" }));
  } else {
    const grid = el("div", { class: "grid grid-2" });
    for (const claim of data.claims) grid.append(renderClaim(claim, ctx, years));
    claimsHost.append(grid);
  }
  wrapper.append(claimsPanel);

  /* --------------------------------------------------------- trend chart */
  const series = data.series || {};
  const approvalPoints = (series.approvals && series.approvals.points) || [];
  const trendBody = el("div");
  const trendPanel = panel({
    title: `审批记录趋势（近 ${years} 年，按季度）`,
    sub: `请求窗口 ${windowInfo.start || "—"} → ${windowInfo.end || "—"} · 完整季度分析窗口 ${analysisRange(analysis)}；点击任意周期 → 打开该企业该季度的原始记录`,
    body: trendBody,
  });
  if (approvalPoints.length) {
    const trendFlags = periodFlags(approvalPoints);
    lineChart(trendBody, {
      categories: approvalPoints.map((point) => point.period),
      series: [{ key: "approvals", label: "审批记录（510(k)+PMA）", color: "#2f81f7", values: approvalPoints.map((point) => point.count) }],
      height: 230,
      partialFlags: trendFlags.partialFlags,
      lagFlags: trendFlags.lagFlags,
      svgTestid: "company-chart",
      onSelect: (period) => {
        const range = periodRange(period);
        ctx.go("/evidence", { companies: key, metric: "approvals", start: range?.start, end: range?.end });
      },
      legendNote: `粒度：${series.approvals.granularity || "quarter"} · 不完整周期与临近数据截止周期只展示、不参与同比 · 计数为公开审批记录条数`,
    });
  } else {
    trendBody.append(emptyState("该窗口内没有审批记录。", { title: "无趋势数据" }));
  }
  wrapper.append(trendPanel);

  /* --------------------------------------------------- yearly kind chart */
  const byKind = series.by_kind_year || { periods: [], series: {} };
  const kindKeys = Object.keys(byKind.series || {});
  if (byKind.periods && byKind.periods.length && kindKeys.length) {
    const kindBody = el("div");
    const colors = ["#2f81f7", "#f85149", "#2dd4bf", "#d29922"];
    barChart(kindBody, {
      categories: byKind.periods,
      series: kindKeys.map((kind, index) => ({
        key: kind,
        label: kindLabel(kind),
        color: colors[index % colors.length],
        values: (byKind.series[kind] || []).map((point) => point.count),
      })),
      height: 210,
      svgTestid: "company-kind-chart",
      onSelect: (period, index, seriesKey) => {
        const range = periodRange(period);
        const kind = seriesKey || kindKeys[0];
        ctx.go("/evidence", {
          companies: key,
          metric: KIND_METRIC[kind] || "approvals",
          start: range?.start,
          end: range?.end,
        });
      },
      ariaLabel: "按事件类型的年度分布",
    });
    wrapper.append(panel({
      title: "按事件类型的年度分布",
      sub: "510(k)/PMA 与召回的口径不同，请勿直接相加解读",
      body: kindBody,
      note: "点击柱子 → 打开该企业该年份该类型的原始记录。末年为不完整年度。",
    }));
  }

  /* -------------------------------------------------------- tech mix */
  const rows = (tracks.rows || []).slice().sort((a, b) => (b.recent || 0) - (a.recent || 0));
  const techBody = el("div");
  if (!rows.length) {
    techBody.append(emptyState("该窗口内没有可映射到赛道的记录。", { title: "无赛道记录" }));
  } else {
    techBody.append(dataTable({
      columns: [
        {
          key: "name_zh", label: "技术赛道",
          format: (row) => el("div", null,
            el("span", { text: row.name_zh || row.track }),
            el("span", { class: "muted tiny", text: `  ${row.domain_label_zh || row.domain || ""}` })),
        },
        { key: "recent", label: "完整季度近窗", num: true, format: (row) => fmtInt(row.recent) },
        { key: "recent_all", label: "近窗全部", num: true, format: (row) => fmtInt(row.recent_all), cellClass: "td-muted" },
        { key: "prior", label: "完整季度前窗", num: true, format: (row) => fmtInt(row.prior) },
        { key: "delta", label: "Δ", num: true, format: (row) => el("span", { class: toneForDelta(row.delta), text: fmtSigned(row.delta) }) },
        { key: "pct_change", label: "变化", num: true, format: (row) => el("span", { class: toneForDelta(row.delta), text: fmtPct(row.pct_change, 0) }) },
        { key: "share_recent", label: "企业内占比", num: true, format: (row) => fmtPct(row.share_recent, 1) },
        { key: "industry_pct_change", label: "全行业变化", num: true, format: (row) => el("span", { class: toneForDelta(row.industry_delta), text: fmtPct(row.industry_pct_change, 0) }) },
        { key: "z", label: "前后窗 z", num: true, format: (row) => (row.z == null ? "—" : fmtNum(row.z, 2)) },
        { key: "pma_original_recent", label: "原始 PMA", num: true, format: (row) => el("span", { title: "完整季度近窗内的原始 PMA（新器械进入候选）", text: fmtInt(row.pma_original_recent) }) },
        { key: "pma_supplement_recent", label: "PMA 补充", num: true, format: (row) => el("span", { title: "完整季度近窗内的 PMA 补充申请；补充申请 ≠ 新器械批准", text: fmtInt(row.pma_supplement_recent) }) },
        { key: "k510_traditional_recent", label: "Traditional 510(k)", num: true, format: (row) => fmtInt(row.k510_traditional_recent) },
        {
          key: "first_approval", label: "首个原始批准（Traditional 510k / 原始 PMA）",
          format: (row) => el("span", {
            title: `首个原始批准：${fmtDate(row.first_approval)}；首个任一批准（含补充申请）：${fmtDate(row.first_any_approval)}`,
            text: fmtDate(row.first_approval),
          }),
        },
        { key: "new_in_window", label: "新进入", format: (row) => (row.new_in_window ? badge("是", "teal") : el("span", { class: "muted", text: "—" })) },
      ],
      rows,
      rowClick: (row) => ctx.go("/evidence", { companies: key, track: row.track || row.id, metric: "approvals" }),
    }));
  }
  wrapper.append(panel({
    title: "技术赛道结构",
    sub: `完整自然季度 ${analysisRange(analysis)} vs 对照 ${priorAnalysisRange(analysis)} · 占比为企业内份额（分母为企业已映射赛道记录）；“前后窗 z”为相对前后等长窗口记录数的泊松近似 z（仅描述性，不是专业化指数）`,
    body: techBody,
    note: `未映射赛道：完整季度近窗 ${fmtInt(tracks.unmapped_recent)} 条 / 前窗 ${fmtInt(tracks.unmapped_prior)} 条；窗口全部口径近窗 ${fmtInt(tracks.unmapped_recent_all)} 条。全行业完整季度近窗 ${fmtInt(tracks.industry_total_recent)} 条已映射记录。PMA 补充申请不等于新器械批准；未映射不等于零活动。`,
  }));

  /* ------------------------------------------------ coverage + milestones */
  const bottomGrid = el("div", { class: "grid grid-2 mt-12" });

  const coverageBody = el("div");
  coverageBody.append(dataTable({
    columns: [
      { key: "label_zh", label: "来源", format: (row) => el("div", null, el("div", { text: row.label_zh || row.source }), el("div", { class: "muted tiny", text: row.coverage_zh || "" })) },
      { key: "n", label: "记录", num: true, format: (row) => fmtInt(row.n) },
      { key: "span", label: "实际观测窗口", format: (row) => fmtRange(row.first, row.last) },
      { key: "caveat_zh", label: "口径说明", format: (row) => el("span", { class: "muted tiny", text: row.caveat_zh || "—" }) },
    ],
    rows: data.coverage || [],
    empty: "该企业在数据层没有覆盖记录",
  }));
  bottomGrid.append(panel({
    title: "数据来源覆盖",
    sub: `覆盖期 ${fmtRange(data.coverage_span?.first, data.coverage_span?.last)} · 共 ${fmtInt(data.coverage_span?.events)} 条事件`,
    dense: true,
    body: coverageBody,
  }));

  const milestoneBody = el("div");
  const milestones = data.milestones || [];
  if (!milestones.length) milestoneBody.append(emptyState("没有可展示的里程碑。", { title: "无里程碑" }));
  else {
    const timeline = el("div", { class: "timeline" });
    for (const milestone of milestones) {
      const derived = milestone.derived || !milestone.event_id;
      const item = el("div", { class: `tl-item ${derived ? "derived" : "observed"}` });
      if (!derived) {
        item.dataset.testid = "event-row";
        item.dataset.eventId = milestone.event_id;
        item.dataset.eventHref = buildHash("/evidence", { event: milestone.event_id });
        item.style.cursor = "pointer";
        item.addEventListener("click", () => openEvent(milestone.event_id));
      }
      item.append(
        el("div", { class: "tl-date", text: fmtDate(milestone.event_date) }),
        el("div", { class: "tl-title", text: milestone.title || "—", title: milestone.title || "" }),
        el("div", { class: "tl-meta" },
          badge(milestone.label_zh || kindLabel(milestone.kind), derived ? "violet" : "blue"),
          milestone.approval_type_label_zh ? approvalBadges(milestone, { firstEntry: false }) : null,
          milestone.track_name_zh ? el("span", { text: milestone.track_name_zh }) : null,
          derived ? el("span", { text: "派生项 · 不可点击" }) : el("span", { text: "点击查看事件" }),
        ),
      );
      timeline.append(item);
    }
    milestoneBody.append(timeline);
  }
  bottomGrid.append(panel({
    title: "里程碑时间线",
    sub: "首次记录 / 首次进入赛道等；审批类里程碑标注子类型（原始 PMA / PMA 补充申请 / Traditional 510(k)），派生项没有单条事件",
    body: milestoneBody,
    note: "PMA 补充申请是已批准器械的变更，不应读作新器械首次批准；「数据覆盖期内首次观察到原始批准」只统计原始 PMA 与 Traditional 510(k)。",
  }));
  wrapper.append(bottomGrid);

  /* ------------------------------------------------------- recent events */
  const recent = data.recent_events || [];
  wrapper.append(panel({
    title: "最近事件",
    sub: "窗口内最近的公开记录，点击行打开事件详情（含映射来源与原始链接）",
    dense: true,
    right: linkButton(buildHash("/evidence", { companies: key }), "全部记录"),
    body: dataTable({
      columns: [
        { key: "event_date", label: "日期", format: (row) => fmtDate(row.event_date) },
        { key: "kind", label: "类型", format: (row) => badge(kindLabel(row.kind), "muted") },
        { key: "track_name_zh", label: "赛道", format: (row) => row.track_name_zh || "未映射" },
        { key: "title", label: "标题", format: (row) => el("div", { class: "cell-title", text: row.title || "—", title: row.title || "" }) },
        { key: "company_match", label: "归属", format: (row) => matchBadge(row.company_match) },
      ],
      rows: recent,
      rowClick: (row) => openEvent(row.event_id),
      rowAttrs: (row) => eventRowAttrs(row),
      empty: "该企业没有最近事件",
    }),
  }));

  /* --------------------------------------------------------- limitations */
  wrapper.append(panel({
    title: "该视图的限制",
    sub: "计数口径与可比性说明（与总览中的全局限制一并阅读）",
    body: list((data.limitations || []).map((item) => item.text_zh)),
  }));

  return { title: `${info.name_zh || key} · 企业画像` };
}

/* ---------------------------------------------------- claim + evidence */
function renderClaim(claim, ctx, years) {
  const card = el("div", { class: "claim-card" });
  card.dataset.testid = "claim-card";

  const head = el("div", { class: "claim-head" });
  head.append(...[
    tierBadge(claim.tier, claim.tier_label_zh),
    badge(`置信度：${CONFIDENCE_LABEL[claim.confidence] || claim.confidence || "—"}`, claim.confidence === "high" ? "teal" : claim.confidence === "medium" ? "amber" : "muted", claim.confidence ? `confidence: ${claim.confidence}` : null),
    badge(DIRECTION_LABEL[claim.direction] || claim.direction || "—", DIRECTION_TONE[claim.direction] || "muted"),
    badge(claim.track_name_zh || claim.track || "—", "violet"),
    claim.metrics && claim.metrics.low_volume ? badge("低样本量", "red", "两期合计记录数过少，仅作观察记录") : null,
    claim.metrics && claim.metrics.basis === "complete_quarters" || claim.window && claim.window.basis === "complete_quarters"
      ? badge("完整季度口径", "teal", "claim.metrics.basis / claim.window.basis = complete_quarters")
      : null,
  ].filter(Boolean));
  card.append(head);

  card.append(el("div", { class: "claim-statement", text: claim.statement_zh || "" }));

  const m = claim.metrics || {};
  const metrics = el("div", { class: "claim-metrics" });
  for (const [label, value, hint] of [
    ["完整季度近窗", fmtInt(m.recent), "完整自然季度口径"],
    ["完整季度前窗", fmtInt(m.prior), "完整自然季度口径"],
    ["Δ", fmtSigned(m.delta), null],
    ["变化", fmtPctSigned(m.pct_change), null],
    ["全行业变化", fmtPctSigned(m.industry_pct_change), null],
    ["份额", `${fmtPct(m.share_prior, 0)} → ${fmtPct(m.share_recent, 0)}`, null],
    ["原始 PMA", fmtInt(m.pma_original_recent), "原始 PMA（新器械进入候选）"],
    ["PMA 补充申请", fmtInt(m.pma_supplement_recent), "补充申请是已上市器械的变更，不是新器械"],
    ["Traditional 510(k)", fmtInt(m.k510_traditional_recent), null],
    ["前后窗 z", m.z == null ? "—" : fmtNum(m.z, 2), "相对前后等长窗口记录数的泊松近似 z，仅描述性；不是专业化指数。"],
  ]) {
    metrics.append(el("span", { title: hint || null }, `${label} `, el("b", { text: value })));
  }
  card.append(metrics);
  if (claim.window) {
    card.append(el("div", {
      class: "claim-window muted tiny mono",
      text: `完整季度窗口 ${fmtDate(claim.window.recent_start)} → ${fmtDate(claim.window.recent_end)} · 对照 ${fmtDate(claim.window.prior_start)} → ${fmtDate(claim.window.prior_end)}${claim.window.basis ? ` · basis=${claim.window.basis}` : ""}`,
    }));
  }

  if (claim.caveats && claim.caveats.length) {
    card.append(el("div", { class: "claim-caveats" },
      disclosure(`口径说明（${claim.caveats.length} 条）`, list(claim.caveats)),
    ));
  }

  const actions = el("div", { class: "claim-actions" });
  const button = textButton("查看证据", null, { testid: "claim-evidence-btn", title: "用该结论的证据参数重新检索并列出全部事件" });
  button.addEventListener("click", () => toggleClaimEvidence({ card, button, claim, ctx }));
  actions.append(button);
  if (claim.window) {
    actions.append(el("a", {
      class: "btn btn-sm",
      href: buildHash("/evidence", {
        companies: claim.company,
        track: claim.track,
        metric: m.metric || "approvals",
        start: claim.window.recent_start,
        end: claim.window.recent_end,
      }),
      text: "在证据浏览器中筛选",
    }));
  }
  card.append(actions);
  return card;
}

async function toggleClaimEvidence({ card, button, claim, ctx }) {
  let host = card.querySelector('[data-testid="claim-evidence-panel"]');
  if (host && !host.hidden) {
    host.hidden = true;
    button.textContent = "查看证据";
    return;
  }
  if (!host) {
    host = el("div", { class: "claim-evidence" });
    host.dataset.testid = "claim-evidence-panel";
    card.append(host);
  }
  host.hidden = false;
  host.replaceChildren(skeletonBlock(3));
  button.disabled = true;
  button.textContent = "检索中…";
  try {
    const data = await api.claim(claim.evidence_params || {});
    host.replaceChildren(renderClaimEvidence(data, claim, ctx));
    button.textContent = "收起证据";
  } catch (error) {
    host.replaceChildren(errorState(error, () => {
      host.replaceChildren();
      host.remove();
      toggleClaimEvidence({ card, button, claim, ctx });
    }, { title: "证据检索失败" }));
    button.textContent = "重试";
  } finally {
    button.disabled = false;
  }
}

function renderClaimEvidence(data, claim, ctx) {
  const body = el("div");
  const windowInfo = data.window || {};
  const metric = data.metric || {};

  const head = el("div", { class: "row wrap between" });
  head.append(
    el("span", { class: "small" },
      el("b", { text: "复算结果：" }),
      document.createTextNode(`近窗 ${fmtInt(data.recomputed?.recent)} 条 / 对照窗 ${fmtInt(data.recomputed?.prior)} 条`),
    ),
    el("span", { class: "muted tiny mono", text: `${windowInfo.recent_start || "—"} → ${windowInfo.recent_end || "—"} vs ${windowInfo.prior_start || "—"} → ${windowInfo.prior_end || "—"}` }),
  );
  body.append(head);
  if (metric.definition_zh) body.append(el("div", { class: "muted tiny mt-4", text: metric.definition_zh }));

  const columns = el("div", { class: "ev-cols mt-8" });
  columns.append(
    renderEventColumn("近期窗口", data.recent_events || [], data.recomputed?.recent, windowInfo.recent_start, windowInfo.recent_end),
    renderEventColumn("对照窗口", data.prior_events || [], data.recomputed?.prior, windowInfo.prior_start, windowInfo.prior_end),
  );
  body.append(columns);

  if (data.note_zh) body.append(el("div", { class: "muted tiny mt-8", text: data.note_zh }));
  if (data.limitations && data.limitations.length) body.append(list(data.limitations));

  const actions = el("div", { class: "row wrap mt-8" });
  actions.append(el("a", {
    class: "btn btn-sm",
    href: buildHash("/evidence", {
      companies: claim.company,
      track: claim.track,
      metric: claim.metrics?.metric || "approvals",
      start: windowInfo.recent_start,
      end: windowInfo.recent_end,
    }),
    text: "在证据浏览器中打开该筛选",
  }));
  body.append(actions);
  return body;
}

function renderEventColumn(title, events, count, start, end) {
  const column = el("div", { class: "ev-col" });
  const head = el("div", { class: "row between" });
  head.append(
    el("h5", { text: `${title}（${fmtInt(count == null ? events.length : count)} 条）` }),
    el("span", { class: "muted tiny mono", text: `${fmtDate(start)} → ${fmtDate(end)}` }),
  );
  column.append(head);
  if (!events.length) {
    column.append(el("div", { class: "empty", style: "padding:10px", text: "该窗口没有记录" }));
    return column;
  }
  const listNode = el("div", { class: "ev-list" });
  const pageSize = 20;
  let shown = Math.min(pageSize, events.length);
  const paint = () => {
    listNode.replaceChildren();
    events.slice(0, shown).forEach((event) => listNode.append(eventRowButton(event)));
    if (shown < events.length) {
      listNode.append(el("button", {
        type: "button", class: "ev-more btn btn-ghost btn-sm",
        text: `显示全部 ${events.length} 条（当前 ${shown}）`,
        onclick: () => { shown = events.length; paint(); },
      }));
    }
  };
  paint();
  column.append(listNode);
  return column;
}
