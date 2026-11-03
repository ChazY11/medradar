/* #/overview — product purpose, data foundation, evidence chain and limits. */
import { api } from "../api.js";
import { el, fmtInt, fmtPct, fmtRange, fmtSigned, toneForDelta, buildHash } from "../util.js";
import { pageHead, panel, kpi, badge, dataTable, notice, list, linkButton, skeletonBlock, errorState, tierBadge } from "../components.js";

const KIND_ORDER = ["510k", "device_recall", "pma", "trial", "8k_catalyst", "drug_approval"];
const KIND_NAMES = {
  "510k": "510(k) 器械记录",
  device_recall: "器械召回记录",
  pma: "PMA 器械记录",
  trial: "临床试验注册",
  "8k_catalyst": "8-K 公司事件",
  drug_approval: "药品批准记录",
};

export async function mount(root, ctx) {
  const meta = ctx.meta;
  const companies = ctx.companies;
  const featured = companies.featured || [];
  const counts = meta.dataset?.counts || {};
  const dataset = meta.dataset || {};
  const windowYears = (meta.window_choices && meta.window_choices[0]) || 3;

  root.append(pageHead({
    title: "证据驱动的医疗技术情报终端",
    subtitle:
      "把美国 FDA 监管记录、临床试验注册与 SEC 8-K 语料整理成可逐条核查的企业×技术赛道观察层。" +
      "每个数字都能拆到具体事件与原始来源；产品只陈述观察到的事实与统计探测信号，不把假设包装成预测。",
    captions: [
      { label: "数据截止", value: dataset.date_range?.last || "—" },
      { label: "数据集快照", value: dataset.modified_utc ? String(dataset.modified_utc).slice(0, 19).replace("T", " ") : "—" },
      { label: "来源", value: `${(meta.sources || []).length} 个公开数据源` },
      { label: "口径", value: "记录条数，不是产品数" },
    ],
    actions: [
      linkButton("#/evidence", "打开证据浏览器", { primary: true }),
      linkButton(buildHash("/companies", {}), "企业情报"),
    ],
  }));

  /* ---------------------------------------------------------- KPI strip */
  const kpiGrid = el("div", { class: "kpi-grid" });
  kpiGrid.append(
    kpi({ label: "收录企业（名册）", value: fmtInt(companies.total), sub: `其中重点企业 ${fmtInt(featured.length)} 家` }),
    kpi({ label: "事件总数", value: fmtInt(counts.events), sub: `${(meta.sources || []).length} 个来源合并去重口径` }),
    kpi({ label: "技术赛道", value: fmtInt(counts.tracks), sub: `${(meta.domains || []).length} 个技术领域` }),
    kpi({
      label: "赛道映射覆盖",
      value: fmtPct(dataset.track_mapping_coverage, 1),
      sub: `已映射 ${fmtInt(dataset.track_mapped_events)} / 未映射 ${fmtInt(dataset.track_unmapped_events)}`,
    }),
    kpi({ label: "产品代码", value: fmtInt(counts.product_codes), sub: "FDA 产品代码分类表" }),
    kpi({ label: "数据截止", value: dataset.date_range?.last || "—", sub: `起于 ${dataset.date_range?.first || "—"}`, sm: true }),
  );
  root.append(kpiGrid);

  /* -------------------------------------------------------- explainer */
  const steps = [
    { no: "01", name: "结论", desc: "产品只给两类结论：逐条可核查的「观察到的事实」，以及基于历史基线的「统计探测信号」。没有经过验证的预测。", href: buildHash("/companies/medtronic") },
    { no: "02", name: "指标", desc: "结论由指标支撑：企业×赛道的记录计数、相对等长历史窗口的变化、赛道内占比与相对全行业的专业化指数。", href: buildHash("/compare") },
    { no: "03", name: "事件", desc: "每个指标都能拆回具体事件：510(k)、PMA、器械召回、临床试验注册与 8-K，带事件日与数据可用日。", href: buildHash("/evidence") },
    { no: "04", name: "原始来源", desc: "每条事件都附带可回溯的原始来源链接（FDA / ClinicalTrials.gov / SEC）；没有可用链接时明确标注，不臆造 URL。", href: buildHash("/evidence") },
  ];
  const explainer = el("div", { class: "explainer" });
  for (const step of steps) {
    explainer.append(el("a", { class: "explainer-step", href: step.href, style: "color:inherit;text-decoration:none" },
      el("div", { class: "step-no", text: step.no }),
      el("div", { class: "step-name", text: step.name }),
      el("div", { class: "step-desc", text: step.desc }),
    ));
  }
  root.append(panel({
    title: "从结论到证据：四层可核查链路",
    sub: "结论 → 指标 → 事件 → 原始来源",
    body: explainer,
  }));

  /* -------------------------------------------------- radar + tier legend */
  const grid = el("div", { class: "grid grid-sidebar mt-12" });
  const radarBody = el("div", null, skeletonBlock(6));
  const radarPanel = panel({
    title: "技术雷达 · 领域概况",
    sub: `近 ${windowYears} 年 vs 之前 ${windowYears} 年`,
    right: linkButton(buildHash("/radar", { years: windowYears }), "进入技术雷达"),
    body: radarBody,
  });
  grid.append(radarPanel);

  const tierPanel = panel({
    title: "证据等级图例",
    sub: "所有结论都带等级标签，等级决定它可以被怎样解读",
    body: renderTierLegend(meta),
  });
  grid.append(tierPanel);
  root.append(grid);

  /* ------------------------------------------------- featured companies */
  root.append(panel({
    title: "重点企业",
    sub: "五家重点企业；点击进入企业画像，查看证据链与赛道结构",
    right: linkButton("#/companies", "全部企业"),
    dense: true,
    body: dataTable({
      columns: [
        { key: "name_zh", label: "企业", format: (row) => el("a", { class: "plain", href: buildHash(`/companies/${row.key}`) }, el("b", { text: row.name_zh }), el("span", { class: "muted", text: `  ${row.name_en}` })) },
        { key: "ticker", label: "代码", format: (row) => row.ticker || "—" },
        { key: "events", label: "事件", num: true, format: (row) => fmtInt(row.events) },
        { key: "approvals", label: "审批", num: true, format: (row) => fmtInt(row.approvals) },
        { key: "recalls", label: "召回", num: true, format: (row) => fmtInt(row.recalls) },
        { key: "trials", label: "试验", num: true, format: (row) => fmtInt(row.trials) },
        { key: "tracks", label: "赛道", num: true, format: (row) => fmtInt(row.tracks) },
        { key: "span", label: "覆盖期", format: (row) => fmtRange(row.first_event, row.last_event) },
        { key: "status", label: "归属", format: (row) => row.roster_present ? badge("名册映射", "teal") : badge("补充映射", "amber", "该企业不在仓库原有名册中，事件归属来自精确名称匹配，待人工复核。") },
      ],
      rows: featured,
      rowClick: (row) => ctx.go(`/companies/${row.key}`),
      rowAttrs: (row) => ({ testid: "company-card", dataset: { companyKey: row.key } }),
    }),
  }));

  /* --------------------------------------------------------- limitations */
  root.append(panel({
    title: "必须与数字一起阅读的限制",
    sub: `${(meta.limitations || []).length} 条已声明的数据与方法限制`,
    body: [
      notice({
        tone: "amber",
        title: "美国记录 ≠ 全球业务；记录数 ≠ 创新能力",
        body: "本产品的所有计数都是公开记录条数。召回反映安全性事件而非技术活动；赛道由 FDA 产品代码映射，部分记录无法映射（不会当作零活动）。跨源比较必须先对齐时间窗。",
        label: "READ ME",
      }),
      el("div", { class: "mt-8" }, list((meta.limitations || []).map((item) => item.text_zh))),
    ],
  }));

  /* ---------------------------------------------------- data foundation */
  const sources = meta.sources || [];
  const eventsByKind = dataset.events_by_kind || {};
  const kindRows = KIND_ORDER.filter((kind) => eventsByKind[kind] != null).map((kind) => ({
    kind,
    name: KIND_NAMES[kind] || kind,
    count: eventsByKind[kind],
  }));
  const foundation = el("div", { class: "grid grid-2 mt-12" });
  foundation.append(panel({
    title: "数据来源与观测窗口",
    sub: "每个来源的历史起点不同，跨期总量上升可能只是覆盖扩大",
    dense: true,
    body: dataTable({
      columns: [
        { key: "label_zh", label: "来源", format: (row) => row.label_zh },
        { key: "market", label: "市场", format: (row) => row.market || "—" },
        { key: "observed_count", label: "记录", num: true, format: (row) => fmtInt(row.observed_count) },
        { key: "span", label: "实际观测窗口", format: (row) => fmtRange(row.observed_first, row.observed_last) },
        { key: "coverage_zh", label: "声明覆盖", format: (row) => el("span", { class: "muted", text: row.coverage_zh || "—" }) },
      ],
      rows: sources,
    }),
    note: `dataset.modified_utc：${dataset.modified_utc || "—"} · 数据库文件 ${dataset.path ? dataset.path.split(/[\\/]/).pop() : "—"}`,
  }));
  foundation.append(panel({
    title: "事件类型构成",
    sub: "同一事件层按来源类型统计",
    dense: true,
    body: dataTable({
      columns: [
        { key: "name", label: "事件类型" },
        { key: "count", label: "记录数", num: true, format: (row) => fmtInt(row.count) },
        { key: "share", label: "占比", num: true, format: (row) => fmtPct(counts.events ? row.count / counts.events : null, 1) },
      ],
      rows: kindRows,
    }),
    note: "药品批准记录不属于医疗器械分析范围，仅作为来源完整性的说明保留。",
  }));
  root.append(foundation);

  /* ------------------------------------------------------ radar content */
  try {
    const radar = await api.radar(windowYears);
    const domains = radar.domains || [];
    radarBody.replaceChildren();
    radarBody.append(dataTable({
      columns: [
        {
          key: "label_zh", label: "领域",
          format: (row) => el("div", null,
            el("a", { class: "plain", href: buildHash("/radar") }, el("b", { text: row.label_zh })),
            el("div", { class: "muted tiny", text: row.blurb_zh || "" })),
        },
        { key: "recent", label: "近窗", num: true, format: (row) => fmtInt(row.recent) },
        { key: "prior", label: "前窗", num: true, format: (row) => fmtInt(row.prior) },
        { key: "delta", label: "Δ", num: true, format: (row) => el("span", { class: toneForDelta(row.delta), text: fmtSigned(row.delta) }) },
        { key: "pct_change", label: "变化", num: true, format: (row) => el("span", { class: toneForDelta(row.delta), text: fmtPct(row.pct_change, 1) }) },
        { key: "companies_active", label: "活跃企业", num: true, format: (row) => fmtInt(row.companies_active) },
        { key: "signals", label: "探测信号", num: true, format: (row) => (row.signal_tracks && row.signal_tracks.length ? badge(`${row.signal_tracks.length} 个赛道`, "amber") : el("span", { class: "muted", text: "—" })) },
      ],
      rows: domains,
      rowClick: () => ctx.go("/radar"),
    }));
    radarPanel.append(el("div", { class: "panel-note" },
      el("span", { text: `已映射 ${fmtInt(radar.mapped_records)} 条 / 未映射 ${fmtInt(radar.unmapped_records)} 条（覆盖 ${fmtPct(radar.track_mapping_coverage, 1)}）` }),
      el("span", { text: radar.method?.caveat || "" }),
    ));
  } catch (error) {
    radarBody.replaceChildren(errorState(error, () => ctx.refresh(), { title: "雷达数据加载失败" }));
  }

  return { title: "总览" };
}

function renderTierLegend(meta) {
  const tiers = meta.evidence_tiers || {};
  const order = ["observed", "detected", "hypothesis"];
  const node = el("div", { class: "stack tight" });
  for (const key of order) {
    const tier = tiers[key];
    if (!tier) continue;
    const card = el("div", { class: "claim-card" });
    const head = el("div", { class: "claim-head" });
    head.append(tierBadge(key, tier.label_zh));
    if (tier.label_en) head.append(el("span", { class: "muted tiny", text: tier.label_en }));
    card.append(head, el("div", { class: "small", text: tier.desc_zh || "" }));
    node.append(card);
  }
  node.append(el("div", { class: "muted tiny", text: "「Detected Signal」只说明记录数偏离历史基线，不等于因果，也不是预测。" }));
  return node;
}
